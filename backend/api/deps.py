"""Request dependency helpers (auth, CSRF, ownership)."""
from __future__ import annotations

from typing import Optional, Tuple

from backend.api import Request, Response
from backend.config import SESSION_COOKIE_NAME
from backend.services.auth_service import get_auth_service
from backend.storage.database import get_job_store


def get_current_user(request: Request) -> Optional[str]:
    """Return the authenticated user_id from the session cookie, or None."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None
    return get_auth_service().get_user_id_from_session(session_id)


def require_auth(handler):
    """Decorator: reject unauthenticated requests with 401."""
    def wrapper(request: Request) -> Response:
        user_id = get_current_user(request)
        if not user_id:
            return Response.error(401, "authentication required")
        request.current_user = user_id  # type: ignore[attr-defined]
        return handler(request)
    return wrapper


def require_csrf(handler):
    """Decorator: validate CSRF token for state-changing requests.

    Falls back to Origin validation when no CSRF token is supplied.
    """
    def wrapper(request: Request) -> Response:
        session_id = request.cookies.get(SESSION_COOKIE_NAME)
        csrf_token = request.headers.get("x-csrf-token")
        origin = request.headers.get("origin", "")
        # If a CSRF token is provided, validate it strictly.
        if csrf_token:
            if not get_auth_service().validate_csrf(session_id or "", csrf_token):
                return Response.error(403, "invalid csrf token")
        else:
            # Fall back to Origin check for same-origin requests.
            if not origin:
                return Response.error(403, "missing origin")
            # Origin must be one of the allowed origins or same host.
            host = request.headers.get("host", "")
            allowed = origin.endswith(host) if host else False
            if not allowed:
                return Response.error(403, "origin not allowed")
        return handler(request)
    return wrapper


def check_ownership(project_id: str, user_id: str) -> bool:
    """Return True if the project belongs to the given user."""
    row = get_job_store()._query_one(
        "SELECT owner_id FROM projects WHERE project_id = ?", (project_id,)
    )
    return bool(row and row["owner_id"] == user_id)
