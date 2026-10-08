"""Project input validation endpoint."""
from __future__ import annotations

import json

from backend.api import Request, Response, Router
from backend.api.deps import check_ownership, require_auth
from backend.storage.database import get_job_store

router = Router()


@router.post("/api/projects/{project_id}/validate")
@require_auth
def validate_project(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    store = get_job_store()
    proj = store._query_one(
        "SELECT * FROM projects WHERE project_id = ?", (project_id,)
    )
    if not proj:
        return Response.error(404, "project not found")

    errors = []
    warnings = []
    pending_manual_inputs = []

    keywords = json.loads(proj["keywords"] or "[]")
    categories = json.loads(proj["categories"] or "[]")

    if not proj["project_name"].strip():
        errors.append("project_name is required")

    if not keywords and not categories:
        warnings.append("No keywords or categories provided; analysis may be limited")

    uploads = store._query_all(
        "SELECT upload_id, detected_type, confirmed_type FROM uploads WHERE project_id = ?",
        (project_id,),
    )
    if not uploads:
        warnings.append("No data files uploaded; analysis will use mock/empty data")
    else:
        unconfirmed = [u for u in uploads if not u["confirmed_type"]]
        if unconfirmed:
            pending_manual_inputs.append(
                f"{len(unconfirmed)} file(s) need type confirmation"
            )

    # Check manual inputs
    mi = store._query_one(
        "SELECT data FROM manual_inputs WHERE project_id = ?", (project_id,)
    )
    mi_data = json.loads(mi["data"]) if mi and mi["data"] else {}
    required_manual = ["supplier_name", "purchase_cost", "moq"]
    for field in required_manual:
        if not mi_data.get(field):
            pending_manual_inputs.append(f"manual input '{field}' is empty")

    valid = len(errors) == 0
    return Response.json({
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "pending_manual_inputs": pending_manual_inputs,
        "pending_validation": not valid or len(pending_manual_inputs) > 0,
    })
