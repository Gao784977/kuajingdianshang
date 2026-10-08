"""Project management endpoints."""
from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List

from backend.api import Request, Response, Router
from backend.api.deps import check_ownership, require_auth, require_csrf
from backend.storage.database import get_job_store

router = Router()


def _row_to_project(row) -> Dict[str, Any]:
    data = dict(row)
    for key in ("keywords", "categories", "urls"):
        try:
            data[key] = json.loads(data[key])
        except (TypeError, ValueError):
            data[key] = []
    for key in ("target_price_range", "manual_inputs"):
        try:
            data[key] = json.loads(data[key])
        except (TypeError, ValueError):
            data[key] = {}
    return data


@router.post("/api/projects")
@require_auth
@require_csrf
def create_project(request: Request) -> Response:
    body = request.json
    if not isinstance(body, dict):
        return Response.error(400, "invalid json body")

    project_name = (body.get("project_name") or "").strip()
    if not project_name:
        return Response.error(400, "project_name is required")

    project_id = str(uuid.uuid4())
    now = time.time()
    store = get_job_store()
    store._execute(
        """
        INSERT INTO projects (project_id, owner_id, project_name, marketplace,
            keywords, categories, target_price_range, urls, manual_inputs,
            status, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?)
        """,
        (
            project_id,
            request.current_user,
            project_name,
            body.get("marketplace", "us"),
            json.dumps(body.get("keywords", []), ensure_ascii=False),
            json.dumps(body.get("categories", []), ensure_ascii=False),
            json.dumps(body.get("target_price_range", {}), ensure_ascii=False),
            json.dumps(body.get("urls", []), ensure_ascii=False),
            json.dumps(body.get("manual_inputs", {}), ensure_ascii=False),
            now,
            now,
        ),
    )
    return Response.json({
        "project_id": project_id,
        "project_name": project_name,
        "status": "draft",
    }, status=201)


@router.get("/api/projects/{project_id}")
@require_auth
def get_project(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    store = get_job_store()
    row = store._query_one(
        "SELECT * FROM projects WHERE project_id = ?", (project_id,)
    )
    if not row:
        return Response.error(404, "project not found")
    if row["owner_id"] != request.current_user:
        return Response.error(403, "forbidden")
    return Response.json(_row_to_project(row))


@router.put("/api/projects/{project_id}")
@require_auth
@require_csrf
def update_project(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    store = get_job_store()
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    body = request.json
    if not isinstance(body, dict):
        return Response.error(400, "invalid json body")

    allowed = {"project_name", "marketplace", "keywords", "categories",
               "target_price_range", "urls", "manual_inputs", "status"}
    sets: List[str] = []
    params: List[Any] = []
    for key in allowed:
        if key in body:
            value = body[key]
            if key in ("keywords", "categories", "urls"):
                value = json.dumps(value, ensure_ascii=False)
            elif key in ("target_price_range", "manual_inputs"):
                value = json.dumps(value, ensure_ascii=False)
            sets.append(f"{key} = ?")
            params.append(value)
    if not sets:
        return Response.error(400, "no updatable fields provided")

    sets.append("updated_at = ?")
    params.append(time.time())
    params.append(project_id)
    store._execute(
        f"UPDATE projects SET {', '.join(sets)} WHERE project_id = ?",
        tuple(params),
    )
    row = store._query_one(
        "SELECT * FROM projects WHERE project_id = ?", (project_id,)
    )
    return Response.json(_row_to_project(row))


@router.get("/api/projects")
@require_auth
def list_projects(request: Request) -> Response:
    store = get_job_store()
    rows = store._query_all(
        "SELECT * FROM projects WHERE owner_id = ? ORDER BY updated_at DESC",
        (request.current_user,),
    )
    return Response.json([_row_to_project(r) for r in rows])
