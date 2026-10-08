"""Job management endpoints: create, status, cancel, intermediate."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

from backend.api import Request, Response, Router
from backend.api.deps import check_ownership, require_auth, require_csrf
from backend.config import OUTPUT_DIR
from backend.services.workflow_runner import get_workflow_runner
from backend.storage.database import get_job_store

router = Router()


def _collect_excel_files(project_id: str) -> List[str]:
    """Return local storage paths for all confirmed uploads."""
    from backend.storage.database import get_storage
    storage = get_storage()
    rows = get_job_store()._query_all(
        "SELECT upload_id, original_name FROM uploads WHERE project_id = ?",
        (project_id,),
    )
    paths = []
    for row in rows:
        path = storage.get_upload_path(project_id, row["upload_id"])
        if path:
            paths.append(path)
    return paths


def _load_config() -> Dict[str, Any]:
    """Load the Amazon workflow config."""
    config_path = "config/amazon_workflow.json"
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}


def _get_project_template(project_id: str, template_type: str) -> Optional[str]:
    """Return the local storage path for a project's bound template.

    Returns None if no template is bound (the workflow will fall back
    to building the report from scratch).
    """
    row = get_job_store()._query_one(
        "SELECT storage_key, validation_status FROM templates "
        "WHERE project_id = ? AND template_type = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (project_id, template_type),
    )
    if not row:
        return None
    if row["validation_status"] == "invalid":
        return None  # Do not silently use an invalid template
    return row["storage_key"]


@router.post("/api/projects/{project_id}/jobs")
@require_auth
@require_csrf
def create_job(request: Request) -> Response:
    """Create a Phase 1 analysis job (runs asynchronously)."""
    project_id = request.path_params["project_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    body = request.json
    if not isinstance(body, dict):
        body = {}

    store = get_job_store()
    proj_row = store._query_one(
        "SELECT * FROM projects WHERE project_id = ?", (project_id,)
    )
    if not proj_row:
        return Response.error(404, "project not found")

    job_id = str(uuid.uuid4())
    cli_args = {
        "allow_url_fetch": bool(body.get("allow_url_fetch", False)),
        "strict": bool(body.get("strict", False)),
        "export_intermediate": bool(body.get("export_intermediate", True)),
        "with_mock_data": bool(body.get("use_mock_data", False)),
    }

    job_id = store.create_job({
        "job_id": job_id,
        "project_id": project_id,
        "owner_id": request.current_user,
        "phase": "phase_1",
        "status": "queued",
    })

    # Collect inputs
    excel_files = _collect_excel_files(project_id)
    keywords = json.loads(proj_row["keywords"])
    categories = json.loads(proj_row["categories"])
    urls = json.loads(proj_row["urls"])
    user_input = {
        "keywords": keywords,
        "categories": categories,
        "urls": urls,
    }

    # Read project-bound market research template (if any)
    template_path = _get_project_template(project_id, "market_research_template")

    get_workflow_runner().submit_phase_1(
        job_id=job_id,
        project_id=project_id,
        project_name=proj_row["project_name"],
        excel_files=excel_files,
        user_input=user_input,
        config=_load_config(),
        cli_args=cli_args,
        output_dir=OUTPUT_DIR,
        template_path=template_path,
    )

    return Response.json({"job_id": job_id, "status": "queued"}, status=201)


@router.get("/api/jobs/{job_id}")
@require_auth
def get_job(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    job = get_job_store().get_job(job_id)
    if not job:
        return Response.error(404, "job not found")
    if not check_ownership(job["project_id"], request.current_user):
        return Response.error(403, "forbidden")
    return Response.json(job)


@router.post("/api/jobs/{job_id}/cancel")
@require_auth
@require_csrf
def cancel_job(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    job = get_job_store().get_job(job_id)
    if not job:
        return Response.error(404, "job not found")
    if not check_ownership(job["project_id"], request.current_user):
        return Response.error(403, "forbidden")

    get_workflow_runner().cancel(job_id)
    return Response.json({"job_id": job_id, "status": "cancelling"})


@router.get("/api/jobs/{job_id}/intermediate")
@require_auth
def get_intermediate(request: Request) -> Response:
    job_id = request.path_params["job_id"]
    job = get_job_store().get_job(job_id)
    if not job:
        return Response.error(404, "job not found")
    if not check_ownership(job["project_id"], request.current_user):
        return Response.error(403, "forbidden")

    events = get_job_store().list_events(job_id)
    return Response.json({
        "job_id": job_id,
        "status": job["status"],
        "current_agent": job.get("current_agent"),
        "completed_agents": job.get("completed_agents", []),
        "events": events,
    })
