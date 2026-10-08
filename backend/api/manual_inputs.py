"""Manual supply-chain inputs and Phase 2 continue-development.

Empty values are preserved as empty (not auto-filled with 0 or mock
data). Only ``confirmed`` candidates allow Phase 2 to proceed.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List

from backend.api import Request, Response, Router
from backend.api.deps import check_ownership, require_auth, require_csrf
from backend.config import OUTPUT_DIR
from backend.services.workflow_runner import get_workflow_runner
from backend.storage.database import get_job_store

router = Router()


@router.put("/api/projects/{project_id}/manual-inputs")
@require_auth
@require_csrf
def save_manual_inputs(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    body = request.json
    if not isinstance(body, dict):
        return Response.error(400, "invalid json body")

    # Preserve empty values as empty strings, not 0.
    cleaned: Dict[str, Any] = {}
    for key, value in body.items():
        if value is None or value == "":
            cleaned[key] = ""
        else:
            cleaned[key] = value

    existing = get_job_store()._query_one(
        "SELECT * FROM manual_inputs WHERE project_id = ?", (project_id,)
    )
    now = time.time()
    if existing:
        get_job_store()._execute(
            "UPDATE manual_inputs SET data = ?, updated_at = ? WHERE project_id = ?",
            (json.dumps(cleaned, ensure_ascii=False), now, project_id),
        )
    else:
        get_job_store()._execute(
            "INSERT INTO manual_inputs (project_id, data, updated_at) VALUES (?, ?, ?)",
            (project_id, json.dumps(cleaned, ensure_ascii=False), now),
        )
    return Response.json({"project_id": project_id, "manual_inputs": cleaned})


@router.post("/api/projects/{project_id}/continue-development")
@require_auth
@require_csrf
def continue_development(request: Request) -> Response:
    """Start Phase 2 (product development + profit).

    Returns ``waiting_for_confirmation`` if no candidate is confirmed.
    """
    project_id = request.path_params["project_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    store = get_job_store()
    # Check for at least one confirmed candidate
    confirmed = store._query_all(
        "SELECT candidate_id FROM product_candidates WHERE project_id = ? AND status = 'confirmed'",
        (project_id,),
    )
    if not confirmed:
        return Response.json({
            "status": "waiting_for_confirmation",
            "message": "At least one confirmed candidate is required to continue development.",
        })

    # Find the latest Phase 1 job with a checkpoint
    phase1_job = store._query_one(
        """
        SELECT j.job_id FROM jobs j
        INNER JOIN workflow_checkpoints c ON c.job_id = j.job_id
        WHERE j.project_id = ? AND j.phase = 'phase_1'
        ORDER BY j.created_at DESC LIMIT 1
        """,
        (project_id,),
    )
    if not phase1_job:
        return Response.error(400, "No completed Phase 1 job with checkpoint found")

    proj_row = store._query_one(
        "SELECT * FROM projects WHERE project_id = ?", (project_id,)
    )
    phase_1_job_id = phase1_job["job_id"]

    # Load manual inputs
    mi_row = store._query_one(
        "SELECT data FROM manual_inputs WHERE project_id = ?", (project_id,)
    )
    manual_inputs = json.loads(mi_row["data"]) if mi_row and mi_row["data"] else {}

    confirmed_ids = [r["candidate_id"] for r in confirmed]

    # Create Phase 2 job
    job_id = str(uuid.uuid4())
    job_id = store.create_job({
        "job_id": job_id,
        "project_id": project_id,
        "owner_id": request.current_user,
        "phase": "phase_2",
        "phase_1_job_id": phase_1_job_id,
        "status": "queued",
    })

    # Collect excel files (same as Phase 1)
    from backend.api.jobs import _collect_excel_files, _get_project_template
    excel_files = _collect_excel_files(project_id)
    from backend.api.jobs import _load_config
    user_input = {"manual_inputs": manual_inputs}

    # Read project-bound product development template (if any)
    template_path = _get_project_template(project_id, "product_development_template")

    get_workflow_runner().submit_phase_2(
        job_id=job_id,
        project_id=project_id,
        project_name=proj_row["project_name"],
        excel_files=excel_files,
        user_input=user_input,
        config=_load_config(),
        cli_args={"allow_url_fetch": False, "strict": False},
        output_dir=OUTPUT_DIR,
        phase_1_job_id=phase_1_job_id,
        confirmed_candidate_ids=confirmed_ids,
        template_path=template_path,
    )

    return Response.json({
        "job_id": job_id,
        "status": "queued",
        "phase": "phase_2",
        "phase_1_job_id": phase_1_job_id,
    }, status=201)
