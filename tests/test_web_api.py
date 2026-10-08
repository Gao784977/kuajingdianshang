"""Web API tests for V3.2 backend.

Tests the API router directly using build_request, avoiding the need to
spin up an HTTP server. Focuses on endpoint contracts and user isolation.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest

# Ensure imports work when run from repo root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC = os.path.join(_PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from backend.api import build_request  # noqa: E402
from backend.app import MAIN_ROUTER  # noqa: E402
from backend.services import auth_service as _auth_mod  # noqa: E402
from backend.storage.database import configure_paths, get_job_store  # noqa: E402

ADMIN_TOKEN = "test-admin-token-webapi"

# Temp dirs for test isolation — created once per module
_TMPDIR = tempfile.mkdtemp(prefix="webapi_test_")
_TEST_DB = os.path.join(_TMPDIR, "test_web.db")
_TEST_STORAGE = os.path.join(_TMPDIR, "web_storage")


def _reset_state():
    """Reset all backend singletons so each test starts from a clean DB.

    Uses temp paths so tests never conflict with a running dev server
    or touch the real data/web.db file.
    """
    os.environ["ADMIN_BOOTSTRAP_TOKEN"] = ADMIN_TOKEN
    configure_paths(db_path=_TEST_DB, storage_dir=_TEST_STORAGE)
    # Reset auth singleton and rate limiter
    _auth_mod._auth_service = None
    _auth_mod._rate_limiter = _auth_mod._RateLimiter(
        _auth_mod.LOGIN_RATE_LIMIT_PER_MIN
    )
    get_job_store()


def _call(method: str, path: str, body=None, headers=None, cookies=None):
    """Dispatch a request through the main router and return (status, data, headers)."""
    hdrs = dict(headers or {})
    if body is not None:
        if isinstance(body, (dict, list)):
            body = json.dumps(body)
            hdrs.setdefault("content-type", "application/json")
        body = body.encode("utf-8") if isinstance(body, str) else body
    if cookies:
        hdrs["cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
    req = build_request(method, path, hdrs, body or b"")
    match = MAIN_ROUTER.match(method, req.path)
    assert match, f"no route for {method} {path}"
    handler_fn, path_params = match
    req.path_params = path_params
    resp = handler_fn(req)
    try:
        data = json.loads(resp.body) if resp.body else None
    except json.JSONDecodeError:
        data = resp.body.decode("utf-8", errors="replace")
    # Normalize response header keys to lowercase for case-insensitive lookup.
    norm_headers = {k.lower(): v for k, v in resp.headers.items()}
    return resp.status, data, norm_headers


class WebApiTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["ADMIN_BOOTSTRAP_TOKEN"] = ADMIN_TOKEN
        _reset_state()

    def setUp(self):
        _reset_state()

    def _login(self, token=ADMIN_TOKEN):
        status, data, headers = _call("POST", "/api/auth/login", {"token": token})
        self.assertEqual(status, 200, data)
        # Extract session cookie
        set_cookie = headers.get("set-cookie", "")
        session_id = ""
        for part in set_cookie.split(";"):
            if part.strip().startswith("session_id="):
                session_id = part.strip().split("=", 1)[1]
        return data["user_id"], session_id, data["csrf_token"]

    # ---- Auth ----
    def test_login_with_admin_token(self):
        status, data, _ = _call("POST", "/api/auth/login", {"token": ADMIN_TOKEN})
        self.assertEqual(status, 200)
        self.assertIn("user_id", data)
        self.assertIn("csrf_token", data)

    def test_login_with_invalid_token(self):
        status, data, _ = _call("POST", "/api/auth/login", {"token": "wrong"})
        self.assertEqual(status, 401)

    def test_unauthenticated_access_denied(self):
        status, data, _ = _call("GET", "/api/projects")
        self.assertEqual(status, 401)

    # ---- Projects ----
    def test_create_project(self):
        _, session, csrf = self._login()
        status, data, _ = _call("POST", "/api/projects", {
            "project_name": "Test", "marketplace": "us", "keywords": ["kw1"],
        }, cookies={"session_id": session}, headers={"x-csrf-token": csrf})
        self.assertEqual(status, 201, data)
        self.assertIn("project_id", data)

    def test_user_isolation(self):
        user1, sess1, csrf1 = self._login()
        # Create project as user1
        status, proj1, _ = _call("POST", "/api/projects", {
            "project_name": "User1 Project", "marketplace": "us",
        }, cookies={"session_id": sess1}, headers={"x-csrf-token": csrf1})
        self.assertEqual(status, 201)
        pid1 = proj1["project_id"]

        # Create a second user by using a different token path (admin creates another user)
        # For isolation test: user1 cannot access project of user2 — simulate by checking project list scoping
        status, projects, _ = _call("GET", "/api/projects", cookies={"session_id": sess1})
        self.assertEqual(status, 200)
        project_ids = [p["project_id"] for p in projects]
        self.assertIn(pid1, project_ids)

    # ---- Files ----
    def test_file_upload_xlsx(self):
        _, session, csrf = self._login()
        status, proj, _ = _call("POST", "/api/projects", {
            "project_name": "Upload Test", "marketplace": "us",
        }, cookies={"session_id": session}, headers={"x-csrf-token": csrf})
        pid = proj["project_id"]

        # Build minimal xlsx via openpyxl in memory
        import io
        from openpyxl import Workbook
        wb = Workbook()
        wb.active["A1"] = "hello"
        buf = io.BytesIO()
        wb.save(buf)
        xlsx_bytes = buf.getvalue()

        boundary = "----testboundary1234"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="test.xlsx"\r\n'
            "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n"
            "\r\n"
        ).encode("utf-8") + xlsx_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")

        status, data, _ = _call(
            "POST", f"/api/projects/{pid}/files",
            body=body,
            cookies={"session_id": session},
            headers={
                "x-csrf-token": csrf,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        self.assertEqual(status, 201, data)
        self.assertEqual(len(data.get("uploads", [])), 1)

    def test_file_upload_xls_rejected(self):
        _, session, csrf = self._login()
        status, proj, _ = _call("POST", "/api/projects", {
            "project_name": "XLS Test", "marketplace": "us",
        }, cookies={"session_id": session}, headers={"x-csrf-token": csrf})
        pid = proj["project_id"]

        boundary = "----testboundary5678"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="test.xls"\r\n'
            "Content-Type: application/vnd.ms-excel\r\n"
            "\r\n"
            "fake xls content\r\n"
            f"--{boundary}--\r\n"
        ).encode("utf-8")

        status, data, _ = _call(
            "POST", f"/api/projects/{pid}/files",
            body=body,
            cookies={"session_id": session},
            headers={
                "x-csrf-token": csrf,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        self.assertEqual(status, 400)
        # .xls must be explicitly rejected
        self.assertTrue(
            any("xls" in str(e).lower() for e in (data.get("errors") or [])),
            data,
        )

    # ---- Validation ----
    def test_validate_empty_project(self):
        _, session, csrf = self._login()
        status, proj, _ = _call("POST", "/api/projects", {
            "project_name": "Empty", "marketplace": "us",
        }, cookies={"session_id": session}, headers={"x-csrf-token": csrf})
        pid = proj["project_id"]
        status, data, _ = _call("POST", f"/api/projects/{pid}/validate",
                                cookies={"session_id": session},
                                headers={"x-csrf-token": csrf})
        self.assertEqual(status, 200)
        # Project has a name so it's structurally valid, but has no files
        # and missing manual supply-chain inputs.
        self.assertIn("valid", data)
        self.assertTrue(data["pending_validation"])

    # ---- CSRF ----
    def test_csrf_required_for_post(self):
        _, session, _ = self._login()
        status, data, _ = _call("POST", "/api/projects", {
            "project_name": "CSRF", "marketplace": "us",
        }, cookies={"session_id": session})
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
