"""Cross-user isolation tests for V3.2 backend.

Verifies that one authenticated user cannot access another user's
projects, files, jobs, candidates, outputs, templates, or manual inputs.
Every request goes through the real API router (MAIN_ROUTER) via
``build_request`` — there is no direct call to ``check_ownership``.

Two real users are created via independent invitation codes, each with
its own session cookie and CSRF token. User B then attempts to reach
User A's resources and must be denied (403) on every ownership-scoped
endpoint.
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
from backend.services import workflow_runner as _wf_mod  # noqa: E402
from backend.services.auth_service import get_auth_service  # noqa: E402
from backend.storage.database import configure_paths, get_job_store  # noqa: E402

ADMIN_TOKEN = "test-admin-token-isolation"

# Temp dirs for test isolation — created once per module
_TMPDIR = tempfile.mkdtemp(prefix="isol_test_")
_TEST_DB = os.path.join(_TMPDIR, "test.db")
_TEST_STORAGE = os.path.join(_TMPDIR, "web_storage")


def _reset_state():
    """Reset all backend singletons so each test starts from a clean DB.

    Also resets the workflow runner singleton so its captured store/storage
    references point at the freshly-configured temp paths — otherwise the
    background job thread would write to a stale (closed) connection.
    """
    os.environ["ADMIN_BOOTSTRAP_TOKEN"] = ADMIN_TOKEN
    configure_paths(db_path=_TEST_DB, storage_dir=_TEST_STORAGE)
    _auth_mod._auth_service = None
    _auth_mod._rate_limiter = _auth_mod._RateLimiter(
        _auth_mod.LOGIN_RATE_LIMIT_PER_MIN
    )
    _wf_mod._runner = None
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
    norm_headers = {k.lower(): v for k, v in resp.headers.items()}
    return resp.status, data, norm_headers


def _extract_session_id(set_cookie: str) -> str:
    for part in set_cookie.split(";"):
        if part.strip().startswith("session_id="):
            return part.strip().split("=", 1)[1]
    return ""


class CrossUserIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["ADMIN_BOOTSTRAP_TOKEN"] = ADMIN_TOKEN

    def setUp(self):
        _reset_state()

        # --- Create two independent invitation codes ---
        auth = get_auth_service()
        _, token_a = auth.create_invitation()
        _, token_b = auth.create_invitation()

        # --- Login with each token (two real users, two sessions) ---
        self.user_a_id, self.sess_a, self.csrf_a = self._login(token_a)
        self.user_b_id, self.sess_b, self.csrf_b = self._login(token_b)

        # Sanity: distinct users and sessions
        self.assertNotEqual(self.user_a_id, self.user_b_id)
        self.assertNotEqual(self.sess_a, self.sess_b)

        # --- Create a project for User A ---
        status, data, _ = _call("POST", "/api/projects", {
            "project_name": "A's Project", "marketplace": "us",
        }, cookies={"session_id": self.sess_a},
           headers={"x-csrf-token": self.csrf_a})
        self.assertEqual(status, 201, data)
        self.pid_a = data["project_id"]

        # --- Upload a file for User A (CSV, no external deps) ---
        boundary = "----isolboundary"
        csv_bytes = b"col1,col2\nhello,world\n"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="data.csv"\r\n'
            "Content-Type: text/csv\r\n"
            "\r\n"
        ).encode("utf-8") + csv_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
        status, data, _ = _call(
            "POST", f"/api/projects/{self.pid_a}/files",
            body=body,
            cookies={"session_id": self.sess_a},
            headers={
                "x-csrf-token": self.csrf_a,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        self.assertEqual(status, 201, data)
        self.uploads_a = data.get("uploads", [])
        self.assertEqual(len(self.uploads_a), 1)

        # --- Create a job for User A (runs in background; job_id is immediate) ---
        status, data, _ = _call(
            "POST", f"/api/projects/{self.pid_a}/jobs", {},
            cookies={"session_id": self.sess_a},
            headers={"x-csrf-token": self.csrf_a},
        )
        self.assertEqual(status, 201, data)
        self.jid_a = data["job_id"]

        # --- Insert a candidate directly in DB for A's project ---
        self.cid_a = str(uuid.uuid4())
        store = get_job_store()
        store._execute(
            "INSERT INTO product_candidates (candidate_id, project_id, job_id, "
            "candidate_data, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, 'pending_review', ?, ?)",
            (self.cid_a, self.pid_a, self.jid_a, "{}", time.time(), time.time()),
        )

        # --- Insert an output directly in DB for A's project ---
        self.oid_a = str(uuid.uuid4())
        store._execute(
            "INSERT INTO outputs (output_id, project_id, job_id, owner_id, "
            "output_type, file_name, storage_key, sha256, size_bytes, created_at) "
            "VALUES (?, ?, ?, ?, 'market_research_excel', 'report.xlsx', ?, ?, 0, ?)",
            (self.oid_a, self.pid_a, self.jid_a, self.user_a_id,
             "fake_key", "fake_hash", time.time()),
        )

    def _login(self, token: str):
        status, data, headers = _call("POST", "/api/auth/login", {"token": token})
        self.assertEqual(status, 200, data)
        session_id = _extract_session_id(headers.get("set-cookie", ""))
        self.assertTrue(session_id, "session cookie not set")
        return data["user_id"], session_id, data["csrf_token"]

    # ------------------------------------------------------------------
    # Identity / session separation
    # ------------------------------------------------------------------
    def test_two_users_have_distinct_ids_and_sessions(self):
        self.assertNotEqual(self.user_a_id, self.user_b_id)
        self.assertNotEqual(self.sess_a, self.sess_b)
        self.assertTrue(self.csrf_a)
        self.assertTrue(self.csrf_b)
        self.assertNotEqual(self.csrf_a, self.csrf_b)

    # ------------------------------------------------------------------
    # Project list scoping
    # ------------------------------------------------------------------
    def test_user_b_cannot_see_user_a_project_in_list(self):
        # B lists projects — must NOT include A's project
        status, data, _ = _call("GET", "/api/projects",
                                cookies={"session_id": self.sess_b})
        self.assertEqual(status, 200)
        pids = [p["project_id"] for p in data]
        self.assertNotIn(self.pid_a, pids)

    def test_user_a_can_see_own_project_in_list(self):
        status, data, _ = _call("GET", "/api/projects",
                                cookies={"session_id": self.sess_a})
        self.assertEqual(status, 200)
        pids = [p["project_id"] for p in data]
        self.assertIn(self.pid_a, pids)

    # ------------------------------------------------------------------
    # Single project access
    # ------------------------------------------------------------------
    def test_user_b_cannot_get_user_a_project(self):
        status, _, _ = _call("GET", f"/api/projects/{self.pid_a}",
                             cookies={"session_id": self.sess_b})
        self.assertEqual(status, 403)

    def test_user_a_can_access_own_project(self):
        status, data, _ = _call("GET", f"/api/projects/{self.pid_a}",
                                cookies={"session_id": self.sess_a})
        self.assertEqual(status, 200)
        self.assertEqual(data["project_id"], self.pid_a)
        self.assertEqual(data["owner_id"], self.user_a_id)

    # ------------------------------------------------------------------
    # Files
    # ------------------------------------------------------------------
    def test_user_b_cannot_upload_to_user_a_project(self):
        boundary = "----isolboundaryB"
        csv_bytes = b"hax,hax\n1,2\n"
        body = (
            f"--{boundary}\r\n"
            'Content-Disposition: form-data; name="file"; filename="evil.csv"\r\n'
            "Content-Type: text/csv\r\n"
            "\r\n"
        ).encode("utf-8") + csv_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
        status, _, _ = _call(
            "POST", f"/api/projects/{self.pid_a}/files",
            body=body,
            cookies={"session_id": self.sess_b},
            headers={
                "x-csrf-token": self.csrf_b,
                "content-type": f"multipart/form-data; boundary={boundary}",
            },
        )
        self.assertEqual(status, 403)

    def test_user_b_cannot_list_user_a_files(self):
        status, _, _ = _call("GET", f"/api/projects/{self.pid_a}/files",
                             cookies={"session_id": self.sess_b})
        self.assertEqual(status, 403)

    def test_user_a_can_list_own_files(self):
        status, data, _ = _call("GET", f"/api/projects/{self.pid_a}/files",
                                cookies={"session_id": self.sess_a})
        self.assertEqual(status, 200)
        self.assertEqual(len(data), 1)

    def test_user_b_cannot_detect_user_a_files(self):
        status, _, _ = _call(
            "POST", f"/api/projects/{self.pid_a}/files/detect",
            cookies={"session_id": self.sess_b},
            headers={"x-csrf-token": self.csrf_b},
        )
        self.assertEqual(status, 403)

    # ------------------------------------------------------------------
    # Jobs
    # ------------------------------------------------------------------
    def test_user_b_cannot_create_job_in_user_a_project(self):
        status, _, _ = _call(
            "POST", f"/api/projects/{self.pid_a}/jobs", {},
            cookies={"session_id": self.sess_b},
            headers={"x-csrf-token": self.csrf_b},
        )
        self.assertEqual(status, 403)

    def test_user_b_cannot_get_user_a_job(self):
        status, _, _ = _call("GET", f"/api/jobs/{self.jid_a}",
                             cookies={"session_id": self.sess_b})
        self.assertEqual(status, 403)

    def test_user_a_can_get_own_job(self):
        status, data, _ = _call("GET", f"/api/jobs/{self.jid_a}",
                                cookies={"session_id": self.sess_a})
        self.assertEqual(status, 200)
        self.assertEqual(data["job_id"], self.jid_a)
        self.assertEqual(data["project_id"], self.pid_a)

    def test_user_b_cannot_cancel_user_a_job(self):
        status, _, _ = _call(
            "POST", f"/api/jobs/{self.jid_a}/cancel",
            cookies={"session_id": self.sess_b},
            headers={"x-csrf-token": self.csrf_b},
        )
        self.assertEqual(status, 403)

    def test_user_b_cannot_get_user_a_job_intermediate(self):
        status, _, _ = _call("GET", f"/api/jobs/{self.jid_a}/intermediate",
                             cookies={"session_id": self.sess_b})
        self.assertEqual(status, 403)

    # ------------------------------------------------------------------
    # Candidates
    # ------------------------------------------------------------------
    def test_user_b_cannot_list_user_a_candidates(self):
        status, _, _ = _call("GET", f"/api/projects/{self.pid_a}/candidates",
                             cookies={"session_id": self.sess_b})
        self.assertEqual(status, 403)

    def test_user_a_can_list_own_candidates(self):
        status, data, _ = _call("GET", f"/api/projects/{self.pid_a}/candidates",
                                cookies={"session_id": self.sess_a})
        self.assertEqual(status, 200)
        cids = [c["candidate_id"] for c in data]
        self.assertIn(self.cid_a, cids)

    def test_user_b_cannot_confirm_user_a_candidate(self):
        status, _, _ = _call(
            "POST",
            f"/api/projects/{self.pid_a}/candidates/{self.cid_a}/confirm",
            cookies={"session_id": self.sess_b},
            headers={"x-csrf-token": self.csrf_b},
        )
        self.assertEqual(status, 403)

    # ------------------------------------------------------------------
    # Outputs
    # ------------------------------------------------------------------
    def test_user_b_cannot_list_user_a_outputs(self):
        status, _, _ = _call("GET", f"/api/projects/{self.pid_a}/outputs",
                             cookies={"session_id": self.sess_b})
        self.assertEqual(status, 403)

    def test_user_a_can_list_own_outputs(self):
        status, data, _ = _call("GET", f"/api/projects/{self.pid_a}/outputs",
                                cookies={"session_id": self.sess_a})
        self.assertEqual(status, 200)
        oids = [o["output_id"] for o in data]
        self.assertIn(self.oid_a, oids)

    def test_user_b_cannot_download_user_a_output(self):
        status, _, _ = _call("GET", f"/api/outputs/{self.oid_a}/download",
                             cookies={"session_id": self.sess_b})
        self.assertEqual(status, 403)

    # ------------------------------------------------------------------
    # Manual inputs
    # ------------------------------------------------------------------
    def test_user_b_cannot_save_user_a_manual_inputs(self):
        status, _, _ = _call(
            "PUT", f"/api/projects/{self.pid_a}/manual-inputs",
            {"supplier_cost": "10"},
            cookies={"session_id": self.sess_b},
            headers={"x-csrf-token": self.csrf_b},
        )
        self.assertEqual(status, 403)

    def test_user_a_can_save_own_manual_inputs(self):
        status, data, _ = _call(
            "PUT", f"/api/projects/{self.pid_a}/manual-inputs",
            {"supplier_cost": "10"},
            cookies={"session_id": self.sess_a},
            headers={"x-csrf-token": self.csrf_a},
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["manual_inputs"]["supplier_cost"], "10")

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------
    def test_user_b_cannot_list_user_a_templates(self):
        status, _, _ = _call("GET", f"/api/projects/{self.pid_a}/templates",
                             cookies={"session_id": self.sess_b})
        self.assertEqual(status, 403)

    def test_user_a_can_list_own_templates(self):
        status, _, _ = _call("GET", f"/api/projects/{self.pid_a}/templates",
                             cookies={"session_id": self.sess_a})
        self.assertEqual(status, 200)

    # ------------------------------------------------------------------
    # Body-injected owner_id must not bypass session identity
    # ------------------------------------------------------------------
    def test_body_owner_id_does_not_bypass_session(self):
        # User B attempts to create a project owned by A via body injection.
        status, data, _ = _call("POST", "/api/projects", {
            "project_name": "B's Project",
            "marketplace": "us",
            "owner_id": self.user_a_id,
        }, cookies={"session_id": self.sess_b},
           headers={"x-csrf-token": self.csrf_b})
        self.assertEqual(status, 201, data)
        new_pid = data["project_id"]

        # The actual owner must be B (from the session), not A.
        store = get_job_store()
        row = store._query_one(
            "SELECT owner_id FROM projects WHERE project_id = ?", (new_pid,)
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["owner_id"], self.user_b_id)
        self.assertNotEqual(row["owner_id"], self.user_a_id)

        # A cannot access the project (it belongs to B), proving the
        # body-injected owner_id was ignored.
        status, _, _ = _call("GET", f"/api/projects/{new_pid}",
                             cookies={"session_id": self.sess_a})
        self.assertEqual(status, 403)

        # B can access the project — it is really B's.
        status, data, _ = _call("GET", f"/api/projects/{new_pid}",
                               cookies={"session_id": self.sess_b})
        self.assertEqual(status, 200)
        self.assertEqual(data["owner_id"], self.user_b_id)


if __name__ == "__main__":
    unittest.main()
