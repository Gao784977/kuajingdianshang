"""Authentication endpoints: login, logout, session info."""
from __future__ import annotations

from backend.api import Request, Response, Router
from backend.api.deps import get_current_user
from backend.services.auth_service import get_auth_service

router = Router()


@router.post("/api/auth/login")
def login(request: Request) -> Response:
    """Authenticate with an invitation code (or admin bootstrap token).

    Sets an HttpOnly session cookie and returns a CSRF token for
    subsequent state-changing requests.
    """
    body = request.json
    token = body.get("token", "") if isinstance(body, dict) else ""
    if not token:
        return Response.error(400, "token is required")

    client_ip = request.headers.get("x-forwarded-for", "") or request.headers.get(
        "x-real-ip", ""
    ) or "127.0.0.1"

    session_id, user_id, csrf_token = get_auth_service().login(token, client_ip)
    if not session_id:
        return Response.error(401, "invalid or expired invitation code")

    response = Response.json({"user_id": user_id, "csrf_token": csrf_token})
    response.headers["Set-Cookie"] = get_auth_service().build_session_cookie(session_id)
    return response


@router.post("/api/auth/logout")
def logout(request: Request) -> Response:
    session_id = request.cookies.get("session_id")
    if session_id:
        get_auth_service().logout(session_id)
    response = Response.json({"status": "logged_out"})
    response.headers["Set-Cookie"] = get_auth_service().clear_session_cookie()
    return response


@router.get("/api/auth/me")
def me(request: Request) -> Response:
    user_id = get_current_user(request)
    if not user_id:
        return Response.error(401, "not authenticated")
    csrf = request.cookies.get("session_id")
    return Response.json({
        "user_id": user_id,
        "csrf_token": get_auth_service().get_csrf_token(csrf or ""),
    })
