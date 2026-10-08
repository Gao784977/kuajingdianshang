"""V3.2 backend application entry point.

Runs a :class:`http.server.ThreadingHTTPServer` with a lightweight
Request/Response router. No third-party dependencies required for local
development.

Usage::

    python -m backend.app

Environment variables (see ``backend/config.py``):
    HOST, PORT, ADMIN_BOOTSTRAP_TOKEN, ALLOWED_ORIGINS, ...
"""
from __future__ import annotations

import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import List

# Ensure project root and src/ are importable
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
_src = _PROJECT_ROOT / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from backend.api import Request, Response, Router, build_request  # noqa: E402
from backend.api import auth as auth_api  # noqa: E402
from backend.api import candidates as candidates_api  # noqa: E402
from backend.api import health as health_api  # noqa: E402
from backend.api import jobs as jobs_api  # noqa: E402
from backend.api import manual_inputs as manual_inputs_api  # noqa: E402
from backend.api import outputs as outputs_api  # noqa: E402
from backend.api import projects as projects_api  # noqa: E402
from backend.api import templates as templates_api  # noqa: E402
from backend.api import uploads as uploads_api  # noqa: E402
from backend.api import validation as validation_api  # noqa: E402
from backend.config import ALLOWED_ORIGINS, APP_ENV, HOST, PORT  # noqa: E402
from backend.storage.database import get_job_store  # noqa: E402

FRONTEND_DIR = _PROJECT_ROOT / "frontend"

# Aggregate router: register all endpoint modules here.
ROUTERS: List[Router] = [
    health_api.router, auth_api.router, projects_api.router, uploads_api.router,
    jobs_api.router, candidates_api.router, manual_inputs_api.router, outputs_api.router,
    templates_api.router, validation_api.router,
]


def _aggregate_router() -> Router:
    combined = Router()
    for r in ROUTERS:
        combined._routes.extend(r._routes)  # noqa: SLF001
    return combined


MAIN_ROUTER = _aggregate_router()


class AppHandler(BaseHTTPRequestHandler):
    """HTTP request handler that dispatches to the API router or static files."""

    server_version = "AmazonResearchBackend/3.2"

    # Silence default request logging noise; tests and production logging
    # are handled separately.
    def log_message(self, format: str, *args) -> None:  # noqa: A002
        return

    # -- core dispatch -----------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._dispatch("DELETE")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._send_cors_preflight()

    # -- helpers -----------------------------------------------------------

    def _dispatch(self, method: str) -> None:
        headers = {k: v for k, v in self.headers.items()}
        content_length = int(headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(content_length) if content_length > 0 else b""

        request = build_request(method, self.path, headers, body)

        match = MAIN_ROUTER.match(method, request.path)
        if match:
            handler, path_params = match
            request.path_params = path_params
            try:
                response = handler(request)
            except Exception as exc:  # pragma: no cover - defensive
                response = Response.error(
                    HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {exc}"
                )
        else:
            response = self._try_static(method, request.path)

        self._write_response(response)

    def _try_static(self, method: str, path: str) -> Response:
        if method != "GET":
            return Response.error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")

        # Default to index.html for root
        rel_path = path.lstrip("/") or "index.html"
        # Prevent path traversal in static serving
        safe_path = os.path.normpath(rel_path).replace("\\", "/")
        if safe_path.startswith("..") or safe_path.startswith("/"):
            return Response.error(HTTPStatus.BAD_REQUEST, "invalid path")

        file_path = FRONTEND_DIR / safe_path
        if not file_path.is_file() or not str(file_path.resolve()).startswith(
            str(FRONTEND_DIR.resolve())
        ):
            return Response.error(HTTPStatus.NOT_FOUND, "not found")

        try:
            data = file_path.read_bytes()
        except OSError:
            return Response.error(HTTPStatus.NOT_FOUND, "not found")

        content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
        return Response(
            status=HTTPStatus.OK,
            body=data,
            headers={"Content-Type": content_type},
        )

    def _write_response(self, response: Response) -> None:
        self.send_response(response.status)
        for key, value in response.headers.items():
            self.send_header(key, value)
        self._apply_cors_headers()
        self.send_header("Content-Length", str(len(response.body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(response.body)

    def _apply_cors_headers(self) -> None:
        origin = self.headers.get("Origin")
        if origin and origin in ALLOWED_ORIGINS:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
            self.send_header(
                "Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS"
            )
            self.send_header(
                "Access-Control-Allow-Headers",
                "Content-Type, Authorization, X-CSRF-Token",
            )

    def _send_cors_preflight(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._apply_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()


def create_app() -> ThreadingHTTPServer:
    # Initialize database schema eagerly on startup.
    get_job_store()
    return ThreadingHTTPServer((HOST, PORT), AppHandler)


def main() -> None:
    server = create_app()
    print(f"[V3.2 backend] listening on http://{HOST}:{PORT} (env={APP_ENV})")
    print(f"[V3.2 backend] frontend served from {FRONTEND_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[V3.2 backend] shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
