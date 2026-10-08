"""Workflow execution service: runs V31Workflow, tracks progress,
saves checkpoints, and supports cooperative cancellation.

Phase model:
- Phase 1: input -> excel import -> analysis -> candidates
- Phase 2: read checkpoint + confirmed candidates + manual inputs
           -> product development -> profit -> report

The local runner executes V31Workflow in a background thread. A
:class:`CancellationToken` is checked between stages. For Phase 2,
``confirmed_candidate_ids`` is passed to V31Workflow so the candidate
gate is skipped and product development proceeds directly.
"""
from __future__ import annotations

import json
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.storage.base import CancellationToken, _TaskCancelled
from backend.storage.database import get_job_store, get_storage

# Agent progress mapping for the workflow stages
PHASE_1_AGENTS = [
    "input_validation", "workbook_detection", "schema_mapping", "excel_import",
    "url_fetch", "keyword", "market", "competitor", "brand_seller",
    "review", "opportunity", "product_candidate",
]

PHASE_2_AGENTS = ["product_development", "profit", "report", "excel"]


class WorkflowRunner:
    """Runs V31Workflow in a background thread with progress tracking."""

    def __init__(self) -> None:
        self._store = get_job_store()
        self._storage = get_storage()
        self._cancel_tokens: Dict[str, CancellationToken] = {}
        self._lock = threading.Lock()

    def get_cancel_token(self, job_id: str) -> Optional[CancellationToken]:
        with self._lock:
            return self._cancel_tokens.get(job_id)

    def cancel(self, job_id: str) -> None:
        token = self.get_cancel_token(job_id)
        if token:
            token.cancel()
        self._store.update_job(job_id, {"status": "cancelling"})
        self._store.add_event(job_id, "system", "cancel_requested", "User requested cancellation")

    def submit_phase_1(
        self,
        job_id: str,
        project_id: str,
        project_name: str,
        excel_files: List[str],
        user_input: Dict[str, Any],
        config: Dict[str, Any],
        cli_args: Dict[str, Any],
        output_dir: str,
        template_path: Optional[str] = None,
    ) -> None:
        token = CancellationToken()
        with self._lock:
            self._cancel_tokens[job_id] = token
        thread = threading.Thread(
            target=self._run_phase_1,
            args=(job_id, project_id, project_name, excel_files, user_input,
                  config, cli_args, output_dir, token, template_path),
            daemon=True,
        )
        thread.start()

    def submit_phase_2(
        self,
        job_id: str,
        project_id: str,
        project_name: str,
        excel_files: List[str],
        user_input: Dict[str, Any],
        config: Dict[str, Any],
        cli_args: Dict[str, Any],
        output_dir: str,
        phase_1_job_id: str,
        confirmed_candidate_ids: List[str],
        template_path: Optional[str] = None,
    ) -> None:
        token = CancellationToken()
        with self._lock:
            self._cancel_tokens[job_id] = token
        thread = threading.Thread(
            target=self._run_phase_2,
            args=(job_id, project_id, project_name, excel_files, user_input,
                  config, cli_args, output_dir, token, phase_1_job_id,
                  confirmed_candidate_ids, template_path),
            daemon=True,
        )
        thread.start()

    # -- Phase 1 -----------------------------------------------------------

    def _run_phase_1(
        self, job_id, project_id, project_name, excel_files, user_input,
        config, cli_args, output_dir, token, template_path=None,
    ):
        try:
            self._store.update_job(job_id, {"status": "running", "started_at": time.time()})
            self._store.add_event(job_id, "input_validation", "started", "Validating inputs")
            self._check_cancel(token)

            # Agent progress updates (simulated stage boundaries)
            for agent in PHASE_1_AGENTS[:4]:
                self._store.update_job(job_id, {"current_agent": agent})
                self._store.add_event(job_id, agent, "completed", "")
                self._check_cancel(token)

            # Run the actual V31Workflow
            from src.modules.amazon.v31_workflow import V31Workflow

            tpl_arg = Path(template_path) if template_path else None
            workflow = V31Workflow(
                project_name=project_name,
                excel_files=[Path(p) for p in excel_files],
                user_input=user_input,
                config=config,
                cli_args=cli_args,
                output_dir=Path(output_dir),
                template_path=tpl_arg,
            )
            result = workflow.run()

            self._check_cancel(token)

            for agent in PHASE_1_AGENTS[4:]:
                self._store.update_job(job_id, {"current_agent": agent})
                self._store.add_event(job_id, agent, "completed", "")

            # Save candidates
            self._save_candidates(project_id, job_id, result.candidates)

            # Save checkpoint
            self._save_checkpoint(project_id, job_id, result)

            # Save outputs
            self._save_outputs(project_id, job_id, result)

            completed = PHASE_1_AGENTS
            self._store.update_job(job_id, {
                "status": "completed",
                "current_agent": None,
                "completed_agents": completed,
                "progress": 100,
                "warnings": result.warnings,
                "errors": result.errors,
                "finished_at": time.time(),
            })
            self._store.add_event(job_id, "phase_1", "completed", "Phase 1 complete")

        except _TaskCancelled:
            self._store.update_job(job_id, {
                "status": "cancelled", "finished_at": time.time(),
            })
            self._store.add_event(job_id, "system", "cancelled", "Task was cancelled")
        except Exception as exc:
            self._store.update_job(job_id, {
                "status": "failed", "finished_at": time.time(),
                "errors": [str(exc)],
            })
            self._store.add_event(job_id, "system", "failed", str(exc))
        finally:
            with self._lock:
                self._cancel_tokens.pop(job_id, None)

    # -- Phase 2 -----------------------------------------------------------

    def _run_phase_2(
        self, job_id, project_id, project_name, excel_files, user_input,
        config, cli_args, output_dir, token, phase_1_job_id, confirmed_candidate_ids,
        template_path=None,
    ):
        try:
            self._store.update_job(job_id, {
                "status": "running", "started_at": time.time(),
                "phase_1_job_id": phase_1_job_id,
            })

            # Load checkpoint from Phase 1
            checkpoint = self._store._query_one(
                "SELECT * FROM workflow_checkpoints WHERE job_id = ?",
                (phase_1_job_id,),
            )
            if not checkpoint:
                raise RuntimeError(f"No checkpoint found for phase_1_job_id={phase_1_job_id}")

            self._check_cancel(token)

            # Run V31Workflow with confirmed candidates to skip the gate
            from src.modules.amazon.v31_workflow import V31Workflow

            tpl_arg = Path(template_path) if template_path else None
            workflow = V31Workflow(
                project_name=project_name,
                excel_files=[Path(p) for p in excel_files],
                user_input=user_input,
                config=config,
                cli_args=cli_args,
                output_dir=Path(output_dir),
                confirmed_candidate_ids=confirmed_candidate_ids,
                template_path=tpl_arg,
            )
            result = workflow.run()

            self._check_cancel(token)

            for agent in PHASE_2_AGENTS:
                self._store.update_job(job_id, {"current_agent": agent})
                self._store.add_event(job_id, agent, "completed", "")

            self._save_outputs(project_id, job_id, result)

            self._store.update_job(job_id, {
                "status": "completed",
                "current_agent": None,
                "completed_agents": PHASE_2_AGENTS,
                "progress": 100,
                "warnings": result.warnings,
                "errors": result.errors,
                "finished_at": time.time(),
            })
            self._store.add_event(job_id, "phase_2", "completed", "Phase 2 complete")

        except _TaskCancelled:
            self._store.update_job(job_id, {
                "status": "cancelled", "finished_at": time.time(),
            })
            self._store.add_event(job_id, "system", "cancelled", "Task was cancelled")
        except Exception as exc:
            self._store.update_job(job_id, {
                "status": "failed", "finished_at": time.time(),
                "errors": [str(exc)],
            })
            self._store.add_event(job_id, "system", "failed", str(exc))
        finally:
            with self._lock:
                self._cancel_tokens.pop(job_id, None)

    # -- helpers -----------------------------------------------------------

    def _check_cancel(self, token: CancellationToken) -> None:
        token.raise_if_cancelled()

    def _save_candidates(self, project_id, job_id, candidates):
        for c in candidates:
            cid = c.candidate_id if hasattr(c, "candidate_id") else str(uuid.uuid4())
            self._store._execute(
                """
                INSERT INTO product_candidates (candidate_id, project_id, job_id,
                    candidate_data, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'pending_review', ?, ?)
                """,
                (cid, project_id, job_id, json.dumps(c.to_dict() if hasattr(c, "to_dict") else str(c), ensure_ascii=False),
                 time.time(), time.time()),
            )

    def _save_checkpoint(self, project_id, job_id, result):
        import hashlib
        checkpoint_id = str(uuid.uuid4())
        now = time.time()
        candidate_results = [c.to_dict() if hasattr(c, "to_dict") else str(c) for c in result.candidates]
        self._store._execute(
            """
            INSERT INTO workflow_checkpoints (checkpoint_id, project_id, job_id,
                workflow_version, input_sha256, config_sha256,
                candidate_results, completed_agents, current_phase, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'phase_1', ?, ?)
            """,
            (
                checkpoint_id, project_id, job_id, "v3.2",
                hashlib.sha256(str(project_id).encode()).hexdigest()[:16],
                hashlib.sha256(str(job_id).encode()).hexdigest()[:16],
                json.dumps(candidate_results, ensure_ascii=False),
                json.dumps(PHASE_1_AGENTS, ensure_ascii=False),
                now, now,
            ),
        )

    def _save_outputs(self, project_id, job_id, result):
        # Get owner_id from project
        proj = self._store._query_one(
            "SELECT owner_id FROM projects WHERE project_id = ?", (project_id,)
        )
        owner_id = proj["owner_id"] if proj else ""

        output_paths = []
        if result.market_research_report_path:
            output_paths.append(("market_research_excel", result.market_research_report_path))
        if result.markdown_report_path:
            output_paths.append(("markdown_report", result.markdown_report_path))
        if result.json_report_path:
            output_paths.append(("json_report", result.json_report_path))

        for output_type, path in output_paths:
            try:
                p = Path(path)
                if p.is_file():
                    data = p.read_bytes()
                    output_id = str(uuid.uuid4())
                    storage_key = self._storage.save_output(project_id, output_id, data, p.name)
                    self._store._execute(
                        """
                        INSERT INTO outputs (output_id, project_id, job_id, owner_id,
                            output_type, file_name, storage_key, sha256, size_bytes, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            output_id, project_id, job_id, owner_id,
                            output_type, p.name, storage_key,
                            self._storage.sha256(data), len(data), time.time(),
                        ),
                    )
            except Exception as exc:
                self._store.add_event(job_id, "output_save", "warning", f"Failed to save output {output_type}: {exc}")


# Module-level singleton
_runner: Optional[WorkflowRunner] = None
_runner_lock = threading.Lock()


def get_workflow_runner() -> WorkflowRunner:
    global _runner
    if _runner is None:
        with _runner_lock:
            if _runner is None:
                _runner = WorkflowRunner()
    return _runner
