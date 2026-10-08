# veFaaS API Handler
#
# Entry point for the veFaaS HTTP-triggered function. Translates the
# veFaaS event format into a Request object and dispatches it through
# the same router used by the local http.server backend.
#
# IMPORTANT: This is the production API entry point. It does NOT run
# background threads (veFaaS functions cannot rely on post-response
# threads). Long-running workflows are submitted to a message queue
# and consumed by worker_handler.py.

from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict

# Ensure project root is importable
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC = os.path.join(_PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from backend.api import build_request  # noqa: E402
from backend.app import MAIN_ROUTER  # noqa: E402


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """veFaaS HTTP handler.

    Expected event shape (veFaaS HTTP trigger):
        {
            "method": "GET|POST|...",
            "path": "/api/health",
            "headers": {"Content-Type": "..."},
            "body": "..." (base64 or raw string),
            "queryStringParameters": {...}
        }
    """
    method = (event.get("method") or event.get("httpMethod") or "GET").upper()
    path = event.get("path") or "/"
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    # Decode body
    body = event.get("body", "") or ""
    if event.get("isBase64Encoded") and isinstance(body, str):
        import base64
        body = base64.b64decode(body)
    elif isinstance(body, str):
        body = body.encode("utf-8")

    request = build_request(method, path, headers, body or b"")

    match = MAIN_ROUTER.match(method, request.path)
    if match:
        handler_fn, path_params = match
        request.path_params = path_params
        try:
            response = handler_fn(request)
        except Exception as exc:
            response = _json_response(500, {"error": f"internal error: {exc}"})
    else:
        response = _json_response(404, {"error": "not found"})

    return {
        "statusCode": response.status,
        "headers": response.headers,
        "body": response.body.decode("utf-8", errors="replace"),
        "isBase64Encoded": False,
    }


def _json_response(status: int, data: Dict) -> Any:
    from backend.api import Response
    return Response.json(data, status=status)
