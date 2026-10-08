"""Template upload, binding, validation, and fidelity handling.

Supports:
- market_research_template
- product_development_template

Fidelity rules when generating a report from a template:
1. Copy the original template (never modify it).
2. Remove sample business data and sample images/charts.
3. Preserve sheet names and order, headers, styles, formulas, merged
   cells, data validation, comments, column widths, row heights,
   frozen panes, and page setup.
4. Write analysis results into the copy.
"""
from __future__ import annotations

import io
import json
import time
import uuid
from typing import Any, Dict, List

from backend.api import Request, Response, Router
from backend.api.deps import check_ownership, require_auth, require_csrf
from backend.storage.database import get_job_store, get_storage

router = Router()

ALLOWED_TEMPLATE_TYPES = {"market_research_template", "product_development_template"}


def _parse_multipart_files(body: bytes, content_type: str):
    """Reuse the upload parser to extract template files."""
    from backend.api.uploads import _parse_multipart
    return [p for p in _parse_multipart(body, content_type) if p.get("filename")]


def _validate_template_structure(file_path: str) -> Dict[str, Any]:
    """Basic structural validation using openpyxl.

    Checks: file readable, sheets exist, no obvious corruption.

    The file is read into a BytesIO before passing to openpyxl so that
    validation works regardless of the storage path's file extension
    (the local storage backend stores files by ID, without ``.xlsx``).
    """
    result = {
        "validation_status": "valid",
        "warnings": [],
        "sheet_count": 0,
        "sheet_names": [],
    }
    try:
        from openpyxl import load_workbook
        with open(file_path, "rb") as fh:
            buf = io.BytesIO(fh.read())
        wb = load_workbook(buf, read_only=True, data_only=False)
        result["sheet_count"] = len(wb.sheetnames)
        result["sheet_names"] = wb.sheetnames
        if not wb.sheetnames:
            result["validation_status"] = "invalid"
            result["warnings"].append("Workbook has no sheets")
        wb.close()
    except Exception as exc:
        result["validation_status"] = "invalid"
        result["warnings"].append(f"Failed to open workbook: {exc}")
    return result


@router.post("/api/projects/{project_id}/templates")
@require_auth
@require_csrf
def upload_template(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return Response.error(400, "expected multipart/form-data")

    parts = _parse_multipart_files(request.body, content_type)
    if not parts:
        return Response.error(400, "no template file provided")

    part = parts[0]
    filename = part["filename"]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext != "xlsx":
        return Response.error(400, "only .xlsx templates are supported")

    # Determine template type from form field or query
    body_data = request.json
    template_type = (body_data.get("template_type") if isinstance(body_data, dict) else None) or \
        request.query("template_type")
    if template_type not in ALLOWED_TEMPLATE_TYPES:
        return Response.error(400, f"template_type must be one of {sorted(ALLOWED_TEMPLATE_TYPES)}")

    data = part["data"]
    template_id = str(uuid.uuid4())
    sha256 = get_storage().sha256(data)
    storage_key = get_storage().save_upload(project_id, f"tpl_{template_id}", data, filename)

    # Validate structure
    validation = _validate_template_structure(storage_key)

    get_job_store()._execute(
        """
        INSERT INTO templates (template_id, project_id, owner_id, template_type,
            original_name, sha256, version, validation_status, storage_key, created_at)
        VALUES (?, ?, ?, ?, ?, ?, '1', ?, ?, ?)
        """,
        (
            template_id, project_id, request.current_user, template_type,
            filename, sha256, validation["validation_status"], storage_key, time.time(),
        ),
    )

    return Response.json({
        "template_id": template_id,
        "template_type": template_type,
        "original_name": filename,
        "sha256": sha256,
        "validation_status": validation["validation_status"],
        "warnings": validation["warnings"],
    }, status=201)


@router.get("/api/projects/{project_id}/templates")
@require_auth
def list_templates(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    rows = get_job_store()._query_all(
        "SELECT * FROM templates WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    return Response.json([dict(r) for r in rows])


@router.put("/api/projects/{project_id}/templates/{template_id}")
@require_auth
@require_csrf
def update_template(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    template_id = request.path_params["template_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    body = request.json
    if not isinstance(body, dict):
        return Response.error(400, "invalid json body")

    allowed = {"template_type", "version", "validation_status"}
    sets = []
    params = []
    for key in allowed:
        if key in body:
            sets.append(f"{key} = ?")
            params.append(body[key])
    if not sets:
        return Response.error(400, "no updatable fields")

    params.append(template_id)
    params.append(project_id)
    get_job_store()._execute(
        f"UPDATE templates SET {', '.join(sets)} WHERE template_id = ? AND project_id = ?",
        tuple(params),
    )
    return Response.json({"template_id": template_id, "status": "updated"})
