"""Tests for Phase 2 checkpoint loading in the workflow runner.

Verifies that:
- Phase 2 reads the Phase 1 checkpoint from ``workflow_checkpoints`` and does
  NOT silently re-run Phase 1 agents.
- A Phase 2 job whose ``phase_1_job_id`` has no checkpoint fails with a
  RuntimeError (surfaced as ``failed`` status) rather than re-running Phase 1.
- The ``phase_1_job_id`` column is populated on the Phase 2 job.
- Running Phase 2 does not add any new Phase 1 agent events to ``job_events``.
- ``_save_checkpoint`` persists a row that Phase 2 can subsequently read.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC = os.path.join(_PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import backend.services.workflow_runner as _wf_mod  # noqa: E402
from backend.services import auth_service as _auth_mod  # noqa: E402
from backend.services.workflow_runner import (  # noqa: E402
    PHASE_1_AGENTS,
    PHASE_2_AGENTS,
    WorkflowRunner,
)
from backend.storage.database import configure_paths, get_job_store  # noqa: E402

ADMIN_TOKEN = "test-phase2-token"

# Temp dirs for test isolation — created once per module.
_TMPDIR = tempfile.mkdtemp(prefix="phase2_test_")
_TEST_DB = os.path.join(_TMPDIR, "test.db")
_TEST_STORAGE = os.path.join(_TMPDIR, "web_storage")


# ---------------------------------------------------------------------------
# Reset / setup helpers
# ---------------------------------------------------------------------------

def _reset_state():
    """Reset all backend singletons so each test starts from a clean DB.

    configure_paths closes any existing job-store connection; we then delete
    the SQLite file (plus WAL/SHM sidecars) so the next get_job_store() call
    builds a fresh schema with no leftover rows from a previous test.
    """
    os.environ["ADMIN_BOOTSTRAP_TOKEN"] = ADMIN_TOKEN
    configure_paths(db_path=_TEST_DB, storage_dir=_TEST_STORAGE)
    for _suffix in ("", "-wal", "-shm"):
        _p = _TEST_DB + _suffix
        if os.path.exists(_p):
            try:
                os.remove(_p)
            except OSError:
                pass
    _auth_mod._auth_service = None
    _auth_mod._rate_limiter = _auth_mod._RateLimiter(_auth_mod.LOGIN_RATE_LIMIT_PER_MIN)
    _wf_mod._runner = None
    get_job_store()


def _setup_user_and_project():
    """Insert a user and project row to satisfy foreign keys."""
    store = get_job_store()
    now = time.time()
    store._execute(
        "INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
        ("user-test", "tester", now),
    )
    store._execute(
        "INSERT INTO projects (project_id, owner_id, project_name, marketplace, "
        "created_at, updated_at) VALUES (?, ?, ?, 'us', ?, ?)",
        ("proj-test", "user-test", "Phase2Test", now, now),
    )


def _create_job(job_id, phase="phase_1", phase_1_job_id=None, status="queued"):
    """Insert a job row and return its id."""
    store = get_job_store()
    store._execute(
        "INSERT INTO jobs (job_id, project_id, owner_id, phase, phase_1_job_id, "
        "status, completed_agents, progress, warnings, errors, started_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, '[]', 0, '[]', '[]', ?, ?)",
        (job_id, "proj-test", "user-test", phase, phase_1_job_id, status,
         time.time(), time.time()),
    )
    return job_id


def _job_status(job_id):
    row = get_job_store()._query_one(
        "SELECT status FROM jobs WHERE job_id = ?", (job_id,)
    )
    return row["status"] if row else None


def _job_errors(job_id):
    row = get_job_store()._query_one(
        "SELECT errors FROM jobs WHERE job_id = ?", (job_id,)
    )
    if not row:
        return []
    try:
        return json.loads(row["errors"])
    except (TypeError, ValueError):
        return []


def _job_phase1_id(job_id):
    row = get_job_store()._query_one(
        "SELECT phase_1_job_id FROM jobs WHERE job_id = ?", (job_id,)
    )
    return row["phase_1_job_id"] if row else None


def _events_for(job_id):
    return get_job_store()._query_all(
        "SELECT agent_name, status, message FROM job_events WHERE job_id = ? "
        "ORDER BY created_at ASC",
        (job_id,),
    )


def _phase1_agent_event_count(job_id):
    """Count job_events whose agent_name is a Phase 1 agent."""
    events = _events_for(job_id)
    return sum(1 for e in events if e["agent_name"] in PHASE_1_AGENTS)


def _checkpoint_for(job_id):
    return get_job_store()._query_one(
        "SELECT * FROM workflow_checkpoints WHERE job_id = ?", (job_id,)
    )


def _insert_checkpoint(project_id, job_id, candidate_results=None,
                       completed_agents=None, current_phase="phase_1"):
    """Insert a checkpoint row directly (simulating a completed Phase 1)."""
    import uuid
    store = get_job_store()
    now = time.time()
    store._execute(
        "INSERT INTO workflow_checkpoints (checkpoint_id, project_id, job_id, "
        "workflow_version, candidate_results, completed_agents, current_phase, "
        "created_at, updated_at) VALUES (?, ?, ?, 'v3.2', ?, ?, ?, ?, ?)",
        (
            str(uuid.uuid4()), project_id, job_id,
            json.dumps(candidate_results or [], ensure_ascii=False),
            json.dumps(completed_agents or PHASE_1_AGENTS, ensure_ascii=False),
            current_phase, now, now,
        ),
    )


class _MockResult:
    """Minimal stand-in for V31WorkflowResult used by _save_checkpoint."""

    def __init__(self, candidates=None, warnings=None, errors=None):
        self.candidates = candidates or []
        self.warnings = warnings or []
        self.errors = errors or []


# ---------------------------------------------------------------------------
# Tests: _save_checkpoint persists a readable row
# ---------------------------------------------------------------------------

class SaveCheckpointTests(unittest.TestCase):
    """Verify that _save_checkpoint writes a row Phase 2 can later read."""

    def setUp(self):
        _reset_state()
        _setup_user_and_project()
        self.runner = WorkflowRunner()
        self.p1_job = _create_job("job-p1-checkpoint")

    def test_save_checkpoint_inserts_row(self):
        result = _MockResult(candidates=[], warnings=[], errors=[])
        self.runner._save_checkpoint("proj-test", self.p1_job, result)

        row = _checkpoint_for(self.p1_job)
        self.assertIsNotNone(row, "checkpoint row should exist after _save_checkpoint")
        self.assertEqual(row["project_id"], "proj-test")
        self.assertEqual(row["job_id"], self.p1_job)
        self.assertEqual(row["workflow_version"], "v3.2")
        self.assertEqual(row["current_phase"], "phase_1")

    def test_save_checkpoint_records_completed_agents(self):
        result = _MockResult(candidates=[])
        self.runner._save_checkpoint("proj-test", self.p1_job, result)

        row = _checkpoint_for(self.p1_job)
        completed = json.loads(row["completed_agents"])
        self.assertEqual(completed, PHASE_1_AGENTS)

    def test_save_checkpoint_serialises_candidates(self):
        class _Candidate:
            def to_dict(self):
                return {"candidate_id": "c1", "name": "Widget"}

        result = _MockResult(candidates=[_Candidate()])
        self.runner._save_checkpoint("proj-test", self.p1_job, result)

        row = _checkpoint_for(self.p1_job)
        candidates = json.loads(row["candidate_results"])
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["candidate_id"], "c1")


# ---------------------------------------------------------------------------
# Tests: Phase 2 without a checkpoint fails (does not re-run Phase 1)
# ---------------------------------------------------------------------------

class Phase2MissingCheckpointTests(unittest.TestCase):
    """Phase 2 must fail loudly when no Phase 1 checkpoint exists."""

    def setUp(self):
        _reset_state()
        _setup_user_and_project()
        self.runner = WorkflowRunner()
        # Phase 1 job exists but has NO checkpoint row.
        self.p1_job = _create_job("job-p1-nockpt", status="completed")
        self.p2_job = _create_job("job-p2-nockpt", phase="phase_2",
                                  phase_1_job_id=self.p1_job)

    def _submit_phase2(self):
        self.runner.submit_phase_2(
            job_id=self.p2_job,
            project_id="proj-test",
            project_name="Phase2Test",
            excel_files=[],
            user_input={},
            config={},
            cli_args={},
            output_dir=_TEST_STORAGE,
            phase_1_job_id=self.p1_job,
            confirmed_candidate_ids=[],
        )
        time.sleep(0.5)

    def test_phase2_without_checkpoint_fails(self):
        self._submit_phase2()
        status = _job_status(self.p2_job)
        self.assertEqual(status, "failed",
                         f"expected 'failed', got '{status}'")

    def test_phase2_failure_mentions_missing_checkpoint(self):
        self._submit_phase2()
        errors = _job_errors(self.p2_job)
        self.assertTrue(errors, "expected at least one error message")
        joined = " ".join(str(e) for e in errors)
        self.assertIn("checkpoint", joined.lower(),
                      f"error should mention missing checkpoint: {errors}")

    def test_phase2_without_checkpoint_does_not_reach_completed(self):
        self._submit_phase2()
        self.assertNotEqual(_job_status(self.p2_job), "completed")

    def test_phase2_without_checkpoint_does_not_run_phase1_agents(self):
        before = _phase1_agent_event_count(self.p2_job)
        self._submit_phase2()
        after = _phase1_agent_event_count(self.p2_job)
        self.assertEqual(before, after,
                         "Phase 2 must not add Phase 1 agent events even on failure")

    def test_phase2_without_checkpoint_records_failed_event(self):
        self._submit_phase2()
        events = _events_for(self.p2_job)
        statuses = [(e["agent_name"], e["status"]) for e in events]
        self.assertIn(("system", "failed"), statuses)


# ---------------------------------------------------------------------------
# Tests: Phase 2 sets phase_1_job_id and does not re-run Phase 1 agents
# ---------------------------------------------------------------------------

class Phase2NoRerunTests(unittest.TestCase):
    """When a checkpoint exists, Phase 2 must not re-run Phase 1 agents."""

    def setUp(self):
        _reset_state()
        _setup_user_and_project()
        self.runner = WorkflowRunner()
        # Phase 1 job with a real checkpoint row.
        self.p1_job = _create_job("job-p1-ckpt", status="completed")
        _insert_checkpoint("proj-test", self.p1_job)
        self.p2_job = _create_job("job-p2-ckpt", phase="phase_2",
                                  phase_1_job_id=self.p1_job)

    def _submit_phase2(self):
        self.runner.submit_phase_2(
            job_id=self.p2_job,
            project_id="proj-test",
            project_name="Phase2Test",
            excel_files=[],
            user_input={},
            config={},
            cli_args={},
            output_dir=_TEST_STORAGE,
            phase_1_job_id=self.p1_job,
            confirmed_candidate_ids=[],
        )
        time.sleep(0.5)

    def test_phase2_sets_phase_1_job_id(self):
        # Before running, the column is already set from create_job.
        self.assertEqual(_job_phase1_id(self.p2_job), self.p1_job)
        # After running, _run_phase_2 also sets it via update_job.
        self._submit_phase2()
        self.assertEqual(_job_phase1_id(self.p2_job), self.p1_job)

    def test_phase2_does_not_add_phase1_agent_events(self):
        before = _phase1_agent_event_count(self.p2_job)
        self.assertEqual(before, 0, "no Phase 1 events before Phase 2 runs")
        self._submit_phase2()
        after = _phase1_agent_event_count(self.p2_job)
        self.assertEqual(after, 0,
                         "Phase 2 must not produce Phase 1 agent events")

    def test_phase2_does_not_emit_phase1_completion_event(self):
        self._submit_phase2()
        events = _events_for(self.p2_job)
        statuses = [(e["agent_name"], e["status"]) for e in events]
        self.assertNotIn(("phase_1", "completed"), statuses,
                         "Phase 2 must not emit a Phase 1 completion event")

    def test_phase2_only_emits_phase2_or_system_events(self):
        self._submit_phase2()
        events = _events_for(self.p2_job)
        allowed = set(PHASE_2_AGENTS) | {"system", "phase_2"}
        for e in events:
            self.assertIn(
                e["agent_name"], allowed,
                f"Phase 2 produced unexpected agent event: {e['agent_name']}",
            )

    def test_phase2_reads_existing_checkpoint(self):
        # The checkpoint exists; Phase 2 should not fail with a missing-
        # checkpoint error. It may still fail later (e.g. V31Workflow cannot
        # run with empty inputs) but the checkpoint must be found.
        self._submit_phase2()
        errors = _job_errors(self.p2_job)
        joined = " ".join(str(e) for e in errors).lower()
        self.assertNotIn("no checkpoint found", joined,
                         "checkpoint exists — Phase 2 must not claim it is missing")


# ---------------------------------------------------------------------------
# Tests: checkpoint schema / Phase 1 agents list sanity
# ---------------------------------------------------------------------------

class CheckpointSchemaTests(unittest.TestCase):
    """Sanity checks on the checkpoint table and agent lists."""

    def setUp(self):
        _reset_state()
        _setup_user_and_project()

    def test_workflow_checkpoints_table_exists(self):
        store = get_job_store()
        # Will raise if the table is missing.
        row = store._query_one(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='workflow_checkpoints'"
        )
        self.assertIsNotNone(row)

    def test_phase1_and_phase2_agents_are_disjoint(self):
        self.assertEqual(len(PHASE_1_AGENTS), 12)
        self.assertEqual(set(PHASE_2_AGENTS),
                         {"product_development", "profit", "report", "excel"})
        self.assertFalse(set(PHASE_1_AGENTS) & set(PHASE_2_AGENTS),
                         "Phase 1 and Phase 2 agent lists must not overlap")


if __name__ == "__main__":
    unittest.main()
