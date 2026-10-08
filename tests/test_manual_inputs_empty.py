"""Tests that empty/null manual input values are preserved as empty strings.

The manual-inputs handler (PUT /api/projects/{project_id}/manual-inputs)
must NOT replace empty values with 0, defaults, or mock values -- empty
means "user has not provided this yet" and the report pipeline must
surface it as pending manual confirmation.
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

ADMIN_TOKEN = "test-manual-input-token"

# Temp dirs for test isolation -- created once per module
_TMPDIR = tempfile.mkdtemp(prefix="manual_test_")
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


# Fields exercised by these tests. The first three mirror the
# required-manual-input fields checked by the validation endpoint
# (supplier_name, purchase_cost, moq); logistics and customs are
# additional supply-chain fields that the handler stores verbatim.
MANUAL_FIELDS = ["supplier_name", "purchase_cost", "moq", "logistics", "customs"]


class ManualInputsEmptyTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ["ADMIN_BOOTSTRAP_TOKEN"] = ADMIN_TOKEN
        _reset_state()

    def setUp(self):
        _reset_state()

    def _login(self, token=ADMIN_TOKEN):
        status, data, headers = _call("POST", "/api/auth/login", {"token": token})
        self.assertEqual(status, 200, data)
        set_cookie = headers.get("set-cookie", "")
        session_id = ""
        for part in set_cookie.split(";"):
            if part.strip().startswith("session_id="):
                session_id = part.strip().split("=", 1)[1]
        return data["user_id"], session_id, data["csrf_token"]

    def _create_project(self, session, csrf):
        status, proj, _ = _call("POST", "/api/projects", {
            "project_name": "Manual Inputs Test", "marketplace": "us",
        }, cookies={"session_id": session}, headers={"x-csrf-token": csrf})
        self.assertEqual(status, 201, proj)
        return proj["project_id"]

    def _save_manual_inputs(self, pid, session, csrf, payload):
        status, data, _ = _call(
            "PUT", f"/api/projects/{pid}/manual-inputs", payload,
            cookies={"session_id": session}, headers={"x-csrf-token": csrf},
        )
        self.assertEqual(status, 200, data)
        return data

    def _read_stored_manual_inputs(self, pid):
        """Read the raw manual_inputs row directly from the DB."""
        row = get_job_store()._query_one(
            "SELECT data FROM manual_inputs WHERE project_id = ?", (pid,)
        )
        if not row:
            return {}
        return json.loads(row["data"])

    # ------------------------------------------------------------------
    # Test 1: empty strings are preserved as ""
    # ------------------------------------------------------------------
    def test_empty_strings_preserved_as_empty(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf)
        payload = {field: "" for field in MANUAL_FIELDS}
        data = self._save_manual_inputs(pid, session, csrf, payload)
        # Response echoes the cleaned values
        saved = data["manual_inputs"]
        for field in MANUAL_FIELDS:
            self.assertEqual(saved[field], "", f"{field} should be ''")
            self.assertIsInstance(
                saved[field], str,
                f"{field} should be str, not int/None",
            )
        # Verify what's actually persisted in the DB
        stored = self._read_stored_manual_inputs(pid)
        for field in MANUAL_FIELDS:
            self.assertEqual(stored[field], "", f"DB: {field} should be ''")
            self.assertIsNotNone(stored[field])
            self.assertNotIn(
                stored[field], (0, "0", "N/A", "n/a"),
                f"DB: {field} must not be defaulted to 0/N/A",
            )

    # ------------------------------------------------------------------
    # Test 2: null values are normalized to ""
    # ------------------------------------------------------------------
    def test_null_values_normalized_to_empty_string(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf)
        payload = {field: None for field in MANUAL_FIELDS}
        data = self._save_manual_inputs(pid, session, csrf, payload)
        saved = data["manual_inputs"]
        for field in MANUAL_FIELDS:
            self.assertEqual(saved[field], "", f"{field} should be ''")
            self.assertIsInstance(
                saved[field], str,
                f"{field} must be str (not None)",
            )
        stored = self._read_stored_manual_inputs(pid)
        for field in MANUAL_FIELDS:
            self.assertEqual(stored[field], "", f"DB: {field} should be ''")
            self.assertIsNotNone(stored[field])

    # ------------------------------------------------------------------
    # Test 3: only provided fields are saved
    # ------------------------------------------------------------------
    def test_only_provided_fields_are_saved(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf)
        payload = {"supplier_name": "Acme Corp", "purchase_cost": 10}
        data = self._save_manual_inputs(pid, session, csrf, payload)
        saved = data["manual_inputs"]
        self.assertEqual(saved["supplier_name"], "Acme Corp")
        self.assertEqual(saved["purchase_cost"], 10)
        # Fields NOT provided must not appear (handler iterates body.items())
        self.assertNotIn("moq", saved)
        self.assertNotIn("logistics", saved)
        self.assertNotIn("customs", saved)
        stored = self._read_stored_manual_inputs(pid)
        self.assertEqual(stored["supplier_name"], "Acme Corp")
        self.assertEqual(stored["purchase_cost"], 10)
        self.assertNotIn("moq", stored)
        self.assertNotIn("logistics", stored)
        self.assertNotIn("customs", stored)

    # ------------------------------------------------------------------
    # Test 4: read back -- empty values are "" not 0 / "N/A" / null
    # ------------------------------------------------------------------
    def test_read_back_empty_values_are_empty_string(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf)
        # Mix of empty string and null across fields
        payload = {
            "supplier_name": "",
            "purchase_cost": None,
            "moq": "",
            "logistics": None,
            "customs": "",
        }
        self._save_manual_inputs(pid, session, csrf, payload)
        stored = self._read_stored_manual_inputs(pid)
        for field in MANUAL_FIELDS:
            self.assertEqual(
                stored[field], "",
                f"{field} must be persisted as '' not {stored[field]!r}",
            )
            # Guard against regressions: 0, "0", "N/A", null.
            self.assertNotEqual(stored[field], 0)
            self.assertNotEqual(stored[field], "0")
            self.assertNotEqual(stored[field], "N/A")
            self.assertIsNotNone(stored[field])
            self.assertIsInstance(stored[field], str)

    # ------------------------------------------------------------------
    # Test 5: validate endpoint marks empty inputs as pending
    # ------------------------------------------------------------------
    def test_validate_marks_empty_inputs_as_pending(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf)
        # Save all required manual inputs as empty
        payload = {field: "" for field in MANUAL_FIELDS}
        self._save_manual_inputs(pid, session, csrf, payload)
        # Call validate -- it should flag required fields as pending
        status, data, _ = _call(
            "POST", f"/api/projects/{pid}/validate",
            cookies={"session_id": session},
        )
        self.assertEqual(status, 200, data)
        self.assertTrue(
            data["pending_validation"],
            "empty manual inputs must keep the project pending",
        )
        pending = data.get("pending_manual_inputs", [])
        # The three required fields must be flagged
        for field in ("supplier_name", "purchase_cost", "moq"):
            self.assertTrue(
                any(field in entry for entry in pending),
                f"{field} must appear in pending_manual_inputs: {pending}",
            )


if __name__ == "__main__":
    unittest.main()
