"""Download permission and path traversal prevention tests.

Covers:
- Cross-user download is forbidden (403).
- Invalid output_id returns 404.
- Path traversal in storage_key is blocked (400).
- Missing file on disk returns 404.
- Owner can download their own output (200).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
import uuid

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
from backend.services.auth_service import get_auth_service  # noqa: E402
from backend.storage.database import (  # noqa: E402
    configure_paths,
    get_job_store,
    get_storage,
)

ADMIN_TOKEN = "test-download-security-token"

# Temp dirs for test isolation -- created once per module
_TMPDIR = tempfile.mkdtemp(prefix="dl_sec_test_")
_TEST_DB = os.path.join(_TMPDIR, "test.db")
_TEST_STORAGE = os.path.join(_TMPDIR, "web_storage")


def _reset_state():
    """Reset all backend singletons so each test starts from a clean DB."""
    os.environ["ADMIN_BOOTSTRAP_TOKEN"] = ADMIN_TOKEN
    configure_paths(db_path=_TEST_DB, storage_dir=_TEST_STORAGE)
    _auth_mod._auth_service = None
    _auth_mod._rate_limiter = _auth_mod._RateLimiter(
        _auth_mod.LOGIN_RATE_LIMIT_PER_MIN
    )
    get_job_store()


def _call(method, path, body=None, headers=None, cookies=None):
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
    norm_headers = {k.lower(): v for k, v in resp.headers.items()}
    return resp.status, data, norm_headers


def _login(token=ADMIN_TOKEN):
    """Log in and return (user_id, session_id, csrf_token)."""
    status, data, headers = _call("POST", "/api/auth/login", {"token": token})
    assert status == 200, f"login failed: {data}"
    set_cookie = headers.get("set-cookie", "")
    session_id = ""
    for part in set_cookie.split(";"):
        if part.strip().startswith("session_id="):
            session_id = part.strip().split("=", 1)[1]
    return data["user_id"], session_id, data["csrf_token"]


def _create_project(session, csrf, name="Download Security Test"):
    status, proj, _ = _call("POST", "/api/projects", {
        "project_name": name, "marketplace": "us",
    }, cookies={"session_id": session}, headers={"x-csrf-token": csrf})
    assert status == 201, f"project create failed: {proj}"
    return proj["project_id"]


def _insert_output(pid, owner_id, storage_key):
    """Insert an output row directly into the DB (bypasses the API)."""
    store = get_job_store()
    oid = f"out-{uuid.uuid4().hex[:12]}"
    jid = f"job-{uuid.uuid4().hex[:12]}"
    store._execute(
        "INSERT INTO outputs (output_id, project_id, job_id, owner_id, output_type, "
        "file_name, storage_key, sha256, size_bytes, created_at) "
        "VALUES (?, ?, ?, ?, 'market_research_excel', 'report.xlsx', ?, ?, 0, ?)",
        (oid, pid, jid, owner_id, storage_key, "fake_hash", time.time()),
    )
    return oid


class DownloadSecurityTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["ADMIN_BOOTSTRAP_TOKEN"] = ADMIN_TOKEN
        _reset_state()

    def setUp(self):
        _reset_state()

    # ------------------------------------------------------------------
    # Test 1: cross-user download -> 403
    # ------------------------------------------------------------------
    def test_cross_user_download_forbidden(self):
        # User A logs in and creates a project
        user_a, sess_a, csrf_a = _login()
        pid = _create_project(sess_a, csrf_a, name="User A Project")
        # Insert an output under user A's project
        oid = _insert_output(pid, user_a, "outputs/report_a.xlsx")
        # Create user B via invitation
        _, invite_token = get_auth_service().create_invitation(max_uses=1)
        user_b, sess_b, _ = _login(invite_token)
        self.assertNotEqual(user_a, user_b, "users must differ")
        # User B tries to download user A's output
        status, data, _ = _call(
            "GET", f"/api/outputs/{oid}/download",
            cookies={"session_id": sess_b},
        )
        self.assertEqual(status, 403, data)

    # ------------------------------------------------------------------
    # Test 2: invalid output_id -> 404
    # ------------------------------------------------------------------
    def test_invalid_output_id_returns_404(self):
        _, session, _ = _login()
        status, data, _ = _call(
            "GET", "/api/outputs/nonexistent-output-id/download",
            cookies={"session_id": session},
        )
        self.assertEqual(status, 404, data)

    # ------------------------------------------------------------------
    # Test 3: path traversal with ".." -> 400
    # ------------------------------------------------------------------
    def test_path_traversal_dotdot_blocked(self):
        user_a, sess_a, csrf_a = _login()
        pid = _create_project(sess_a, csrf_a, name="Traversal DotDot")
        oid = _insert_output(pid, user_a, "../../etc/passwd")
        # Owner downloads -- ownership passes, but traversal is caught
        status, data, _ = _call(
            "GET", f"/api/outputs/{oid}/download",
            cookies={"session_id": sess_a},
        )
        self.assertEqual(status, 400, data)

    # ------------------------------------------------------------------
    # Test 4: path traversal with leading "/" -> 400
    # ------------------------------------------------------------------
    def test_path_traversal_leading_slash_blocked(self):
        user_a, sess_a, csrf_a = _login()
        pid = _create_project(sess_a, csrf_a, name="Traversal Slash")
        oid = _insert_output(pid, user_a, "/etc/passwd")
        status, data, _ = _call(
            "GET", f"/api/outputs/{oid}/download",
            cookies={"session_id": sess_a},
        )
        self.assertEqual(status, 400, data)

    # ------------------------------------------------------------------
    # Test 5: valid storage_key but file doesn't exist -> 404
    # ------------------------------------------------------------------
    def test_missing_file_returns_404(self):
        user_a, sess_a, csrf_a = _login()
        pid = _create_project(sess_a, csrf_a, name="Missing File")
        # Relative key with no traversal -- file doesn't exist on disk
        oid = _insert_output(pid, user_a, "outputs/missing_report.xlsx")
        status, data, _ = _call(
            "GET", f"/api/outputs/{oid}/download",
            cookies={"session_id": sess_a},
        )
        self.assertEqual(status, 404, data)

    # ------------------------------------------------------------------
    # Test 6: owner downloads their own output -> 200
    # ------------------------------------------------------------------
    def test_owner_can_download_own_output(self):
        user_a, sess_a, csrf_a = _login()
        pid = _create_project(sess_a, csrf_a, name="Owner Download")
        # Create the file on disk via the storage backend so it exists
        file_content = b"fake excel content for owner download test"
        storage_key = get_storage().save_output(
            pid, uuid.uuid4().hex, file_content, "report.xlsx",
        )
        oid = _insert_output(pid, user_a, storage_key)
        status, data, headers = _call(
            "GET", f"/api/outputs/{oid}/download",
            cookies={"session_id": sess_a},
        )
        self.assertEqual(status, 200, data)
        self.assertIn("content-disposition", headers)
        self.assertIn("report.xlsx", headers["content-disposition"])


if __name__ == "__main__":
    unittest.main()
