"""Product candidate endpoints: list, confirm, reject.

Status names are unified as: pending_review, confirmed, rejected.
Only ``confirmed`` candidates allow Phase 2 (continue-development).
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict

from backend.api import Request, Response, Router
from backend.api.deps import check_ownership, require_auth, require_csrf
from backend.storage.database import get_job_store

router = Router()


@router.get("/api/projects/{project_id}/candidates")
@require_auth
def list_candidates(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    rows = get_job_store()._query_all(
        "SELECT * FROM product_candidates WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    candidates = []
    for row in rows:
        data = dict(row)
        try:
            data["candidate_data"] = json.loads(data["candidate_data"])
        except (TypeError, ValueError):
            data["candidate_data"] = {}
        candidates.append(data)
    return Response.json(candidates)


@router.post("/api/projects/{project_id}/candidates/{candidate_id}/confirm")
@require_auth
@require_csrf
def confirm_candidate(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    candidate_id = request.path_params["candidate_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    get_job_store()._execute(
        """
        UPDATE product_candidates SET status = 'confirmed', updated_at = ?
        WHERE candidate_id = ? AND project_id = ?
        """,
        (time.time(), candidate_id, project_id),
    )
    return Response.json({"candidate_id": candidate_id, "status": "confirmed"})


@router.post("/api/projects/{project_id}/candidates/{candidate_id}/reject")
@require_auth
@require_csrf
def reject_candidate(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    candidate_id = request.path_params["candidate_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    get_job_store()._execute(
        """
        UPDATE product_candidates SET status = 'rejected', updated_at = ?
        WHERE candidate_id = ? AND project_id = ?
        """,
        (time.time(), candidate_id, project_id),
    )
    return Response.json({"candidate_id": candidate_id, "status": "rejected"})
