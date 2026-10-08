"""Output file listing and secure download.

Security:
- Download requires project ownership.
- Path traversal is blocked.
- Only whitelisted output types are served.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List

from backend.api import Request, Response, Router
from backend.api.deps import require_auth
from backend.storage.database import get_job_store, get_storage

router = Router()

ALLOWED_OUTPUT_TYPES = {
    "market_research_excel", "product_development_excel", "markdown_report",
    "json_report", "intermediate_data", "data_quality_report",
}


@router.get("/api/projects/{project_id}/outputs")
@require_auth
def list_outputs(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    # Ownership check
    proj = get_job_store()._query_one(
        "SELECT owner_id FROM projects WHERE project_id = ?", (project_id,)
    )
    if not proj:
        return Response.error(404, "project not found")
    if proj["owner_id"] != request.current_user:
        return Response.error(403, "forbidden")

    rows = get_job_store()._query_all(
        "SELECT * FROM outputs WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    outputs = []
    for row in rows:
        data = dict(row)
        if data["output_type"] in ALLOWED_OUTPUT_TYPES:
            outputs.append(data)
    return Response.json(outputs)


@router.get("/api/outputs/{output_id}/download")
@require_auth
def download_output(request: Request) -> Response:
    output_id = request.path_params["output_id"]
    row = get_job_store()._query_one(
        "SELECT * FROM outputs WHERE output_id = ?", (output_id,)
    )
    if not row:
        return Response.error(404, "output not found")

    # Ownership check
    proj = get_job_store()._query_one(
        "SELECT owner_id FROM projects WHERE project_id = ?", (row["project_id"],)
    )
    if not proj or proj["owner_id"] != request.current_user:
        return Response.error(403, "forbidden")

    if row["output_type"] not in ALLOWED_OUTPUT_TYPES:
        return Response.error(400, "output type not allowed")

    storage_key = row["storage_key"]
    # Path traversal protection
    if ".." in storage_key or storage_key.startswith("/"):
        return Response.error(400, "invalid storage key")

    try:
        data = get_storage().read_file(storage_key)
    except OSError:
        return Response.error(404, "file not found")

    return Response.file(data, row["file_name"])
