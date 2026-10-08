"""File upload endpoints with security controls.

Security controls:
- Allowed extensions: xlsx, csv, json only. ``.xls`` is explicitly
  rejected with a message to convert to ``.xlsx``.
- Executable extensions are rejected.
- Max upload size enforced (MAX_UPLOAD_SIZE_MB).
- SHA-256 computed for every upload.
- Storage path uses upload_id (never the user-supplied filename) to
  prevent path traversal.
"""
from __future__ import annotations

import io
import time
import uuid
from email.parser import BytesParser
from email.policy import default as email_policy
from typing import Any, Dict, List, Optional, Tuple

from backend.api import Request, Response, Router
from backend.api.deps import check_ownership, require_auth, require_csrf
from backend.config import ALLOWED_UPLOAD_EXTENSIONS, MAX_UPLOAD_SIZE_MB
from backend.services.file_detection import detect_by_type
from backend.storage.database import get_job_store, get_storage

router = Router()

MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# Extensions that are never allowed (executables, scripts, etc.)
BLOCKED_EXTENSIONS = {
    "exe", "bat", "cmd", "sh", "ps1", "vbs", "js", "jar", "com", "scr",
    "msi", "dll", "so", "dylib", "py", "pyc", "pyd", "app", "apk", "deb",
    "rpm", "dmg", "iso",
}


def _get_extension(filename: str) -> str:
    """Return lowercase extension without the dot."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[-1].lower()


def _is_path_traversal(filename: str) -> bool:
    """Detect path traversal attempts in the filename."""
    return ".." in filename or "/" in filename or "\\" in filename


def _validate_extension(filename: str) -> Tuple[bool, Optional[str]]:
    """Return (ok, error_message)."""
    ext = _get_extension(filename)
    if not ext:
        return False, "file extension is required"
    if _is_path_traversal(filename):
        return False, "invalid filename"
    if ext in BLOCKED_EXTENSIONS:
        return False, f"file type '.{ext}' is not allowed"
    if ext == "xls":
        return False, "'.xls' is not supported; please convert to '.xlsx'"
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return False, f"file type '.{ext}' is not allowed"
    return True, None


def _parse_multipart(body: bytes, content_type: str) -> List[Dict[str, Any]]:
    """Parse multipart/form-data body into a list of parts.

    Each part is a dict with keys: name, filename, content_type, data.
    """
    if not body:
        return []
    # Build a full email message for parsing
    header = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
    msg = BytesParser(policy=email_policy).parsebytes(header + body)

    parts: List[Dict[str, Any]] = []
    if not msg.is_multipart():
        return parts

    for part in msg.walk():
        if part.is_multipart():
            continue
        disp = part.get("Content-Disposition", "")
        if not disp or "form-data" not in disp:
            continue
        # Parse name and filename from Content-Disposition
        name = ""
        filename = ""
        for param in disp.split(";"):
            param = param.strip()
            if param.startswith("name="):
                name = param[5:].strip().strip('"')
            elif param.startswith("filename="):
                filename = param[9:].strip().strip('"')
        data = part.get_payload(decode=True) or b""
        parts.append({
            "name": name,
            "filename": filename,
            "content_type": part.get_content_type(),
            "data": data,
        })
    return parts


@router.post("/api/projects/{project_id}/files")
@require_auth
@require_csrf
def upload_files(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        return Response.error(400, "expected multipart/form-data")

    # Check total size
    if len(request.body) > MAX_UPLOAD_BYTES:
        return Response.error(413, "file too large")

    parts = _parse_multipart(request.body, content_type)
    file_parts = [p for p in parts if p.get("filename")]
    if not file_parts:
        return Response.error(400, "no files provided")

    storage = get_storage()
    store = get_job_store()
    results: List[Dict[str, Any]] = []
    errors: List[str] = []

    for part in file_parts:
        filename = part["filename"]
        ok, err = _validate_extension(filename)
        if not ok:
            errors.append(f"{filename}: {err}")
            continue

        data = part["data"]
        upload_id = str(uuid.uuid4())
        sha256 = storage.sha256(data)
        storage_key = storage.save_upload(project_id, upload_id, data, filename)

        store._execute(
            """
            INSERT INTO uploads (upload_id, project_id, owner_id, original_name,
                sha256, size_bytes, storage_key, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                upload_id, project_id, request.current_user, filename,
                sha256, len(data), storage_key, time.time(),
            ),
        )
        results.append({
            "upload_id": upload_id,
            "original_name": filename,
            "sha256": sha256,
            "size_bytes": len(data),
        })

    status = 201 if results else 400
    return Response.json({"uploads": results, "errors": errors}, status=status)


@router.get("/api/projects/{project_id}/files")
@require_auth
def list_files(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    rows = get_job_store()._query_all(
        "SELECT * FROM uploads WHERE project_id = ? ORDER BY created_at DESC",
        (project_id,),
    )
    files = []
    for row in rows:
        data = dict(row)
        for key in ("recognized_columns", "unmapped_columns", "warnings"):
            try:
                import json
                data[key] = json.loads(data[key])
            except (TypeError, ValueError):
                data[key] = []
        files.append(data)
    return Response.json(files)


@router.post("/api/projects/{project_id}/files/detect")
@require_auth
@require_csrf
def detect_files(request: Request) -> Response:
    """Run type-specific detection on every uploaded file.

    - xlsx -> detect_workbook()
    - csv  -> detect_csv()
    - json -> detect_json()
    """
    project_id = request.path_params["project_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    store = get_job_store()
    storage = get_storage()
    rows = store._query_all(
        "SELECT * FROM uploads WHERE project_id = ?", (project_id,)
    )

    results = []
    for row in rows:
        upload = dict(row)
        path = storage.get_upload_path(project_id, upload["upload_id"])
        if not path:
            results.append({
                "upload_id": upload["upload_id"],
                "original_name": upload["original_name"],
                "error": "file not found on disk",
            })
            continue

        ext = upload["original_name"].rsplit(".", 1)[-1].lower() if "." in upload["original_name"] else ""
        detection = detect_by_type(path, ext)

        # Persist detection result
        import json as _json
        store._execute(
            """
            UPDATE uploads SET detected_type = ?, recognized_columns = ?,
                unmapped_columns = ?, warnings = ?
            WHERE upload_id = ?
            """,
            (
                detection["detected_type"],
                _json.dumps(detection["recognized_columns"], ensure_ascii=False),
                _json.dumps(detection["unmapped_columns"], ensure_ascii=False),
                _json.dumps(detection["warnings"], ensure_ascii=False),
                upload["upload_id"],
            ),
        )
        results.append({
            "upload_id": upload["upload_id"],
            "original_name": upload["original_name"],
            "detected_type": detection["detected_type"],
            "confidence": detection["confidence"],
            "recognized_columns": detection["recognized_columns"],
            "unmapped_columns": detection["unmapped_columns"],
            "warnings": detection["warnings"],
        })

    return Response.json({"files": results})


@router.post("/api/projects/{project_id}/files/{upload_id}/confirm")
@require_auth
@require_csrf
def confirm_file_type(request: Request) -> Response:
    project_id = request.path_params["project_id"]
    upload_id = request.path_params["upload_id"]
    if not check_ownership(project_id, request.current_user):
        return Response.error(403, "forbidden")

    body = request.json
    confirmed_type = (body.get("confirmed_type") or "").strip() if isinstance(body, dict) else ""
    if not confirmed_type:
        return Response.error(400, "confirmed_type is required")

    get_job_store()._execute(
        "UPDATE uploads SET confirmed_type = ? WHERE upload_id = ? AND project_id = ?",
        (confirmed_type, upload_id, project_id),
    )
    return Response.json({
        "upload_id": upload_id,
        "confirmed_type": confirmed_type,
    })
