"""Integration tests for template upload and workflow binding.

Verifies that user-uploaded templates are actually passed through to
the workflow and used in report generation, not silently dropped.

Covers:
1. Template upload and binding (response contract + listing)
2. template_path is forwarded to WorkflowRunner.submit_phase_1
3. No template bound -> template_path is None
4. Invalid template -> template_path is None (not silently used)
5. Original template file is never modified (SHA-256 unchanged)
6. Template fidelity: sheet names and order are preserved on storage
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ensure imports work when run from repo root
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC = os.path.join(_PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from backend.api import build_request  # noqa: E402
from backend.app import MAIN_ROUTER  # noqa: E402
from backend.api import jobs as _jobs_mod  # noqa: E402
from backend.services import auth_service as _auth_mod  # noqa: E402
from backend.services import workflow_runner as _wf_mod  # noqa: E402
from backend.storage.database import (  # noqa: E402
    configure_paths,
    get_job_store,
    get_storage,
)

ADMIN_TOKEN = "test-tpl-token"
_TMPDIR = tempfile.mkdtemp(prefix="tpl_test_")
_TEST_DB = os.path.join(_TMPDIR, "test.db")
_TEST_STORAGE = os.path.join(_TMPDIR, "web_storage")


def _reset_state():
    """Reset all backend singletons so each test starts from a clean DB."""
    os.environ["ADMIN_BOOTSTRAP_TOKEN"] = ADMIN_TOKEN
    configure_paths(db_path=_TEST_DB, storage_dir=_TEST_STORAGE)
    _auth_mod._auth_service = None
    _auth_mod._rate_limiter = _auth_mod._RateLimiter(_auth_mod.LOGIN_RATE_LIMIT_PER_MIN)
    _wf_mod._runner = None
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


def _make_template_xlsx(sheet_names=None):
    """Build a minimal xlsx in memory; optionally with custom sheet names."""
    from openpyxl import Workbook
    wb = Workbook()
    if sheet_names:
        wb.remove(wb.active)
        for name in sheet_names:
            wb.create_sheet(name)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _upload_template(session, csrf, pid, xlsx_bytes, filename="template.xlsx",
                     template_type="market_research_template"):
    """Upload a template via multipart/form-data.

    template_type is passed as a query parameter because the API reads it
    from request.query('template_type') (request.json returns {} for
    multipart bodies). The multipart body contains only the file part to
    avoid the email parser mangling binary xlsx data when multiple parts
    are present.
    """
    boundary = "----tplboundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        "Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n"
        "\r\n"
    ).encode("utf-8") + xlsx_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    path = f"/api/projects/{pid}/templates?template_type={template_type}"
    return _call(
        "POST", path, body=body,
        cookies={"session_id": session},
        headers={
            "x-csrf-token": csrf,
            "content-type": f"multipart/form-data; boundary={boundary}",
        },
    )


class TemplateIntegrationTestCase(unittest.TestCase):
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

    def _create_project(self, session, csrf, name="Tpl Project"):
        status, data, _ = _call("POST", "/api/projects", {
            "project_name": name, "marketplace": "us", "keywords": ["kw1"],
        }, cookies={"session_id": session}, headers={"x-csrf-token": csrf})
        self.assertEqual(status, 201, data)
        return data["project_id"]

    def _list_templates(self, session, pid):
        status, data, _ = _call(
            "GET", f"/api/projects/{pid}/templates",
            cookies={"session_id": session},
        )
        self.assertEqual(status, 200, data)
        return data

    def _create_job(self, session, csrf, pid):
        return _call("POST", f"/api/projects/{pid}/jobs", {},
                     cookies={"session_id": session},
                     headers={"x-csrf-token": csrf})

    # ------------------------------------------------------------------
    # Test 1: Template upload and binding
    # ------------------------------------------------------------------
    def test_template_upload_and_binding(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf, "Upload Bind Test")

        xlsx_bytes = _make_template_xlsx()
        status, data, _ = _upload_template(session, csrf, pid, xlsx_bytes)
        self.assertEqual(status, 201, data)
        self.assertIn("template_id", data)
        self.assertEqual(data["validation_status"], "valid")
        self.assertEqual(data["template_type"], "market_research_template")
        self.assertIn("sha256", data)
        # SHA-256 returned by the API should match the uploaded bytes
        self.assertEqual(data["sha256"], hashlib.sha256(xlsx_bytes).hexdigest())

        # GET /api/projects/{pid}/templates should list the template
        templates = self._list_templates(session, pid)
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0]["template_id"], data["template_id"])
        self.assertEqual(templates[0]["template_type"], "market_research_template")
        self.assertEqual(templates[0]["validation_status"], "valid")
        self.assertEqual(templates[0]["sha256"], data["sha256"])

    # ------------------------------------------------------------------
    # Test 2: Template path passed to workflow
    # ------------------------------------------------------------------
    def test_template_path_passed_to_workflow(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf, "Tpl Path Test")

        xlsx_bytes = _make_template_xlsx()
        status, tpl_data, _ = _upload_template(session, csrf, pid, xlsx_bytes)
        self.assertEqual(status, 201, tpl_data)
        self.assertEqual(tpl_data["validation_status"], "valid")

        # Confirm the stored storage_key from the templates list
        templates = self._list_templates(session, pid)
        self.assertEqual(len(templates), 1)
        storage_key = templates[0]["storage_key"]
        self.assertTrue(os.path.isfile(storage_key))

        # Mock the workflow runner to capture the template_path argument.
        # Patch the local reference in backend.api.jobs (not the source
        # module) because jobs.py does `from ... import get_workflow_runner`.
        with patch.object(_jobs_mod, "get_workflow_runner") as mock_get_runner:
            mock_runner = MagicMock()
            mock_get_runner.return_value = mock_runner

            status, data, _ = self._create_job(session, csrf, pid)
            self.assertEqual(status, 201, data)

            self.assertTrue(mock_runner.submit_phase_1.called)
            call_kwargs = mock_runner.submit_phase_1.call_args.kwargs
            template_path = call_kwargs.get("template_path")
            self.assertIsNotNone(
                template_path,
                "template_path must be forwarded when a valid template is bound",
            )
            # The path must point to the stored template's storage_key
            self.assertEqual(template_path, storage_key)
            self.assertTrue(os.path.isfile(template_path))

    # ------------------------------------------------------------------
    # Test 3: No template -> None passed
    # ------------------------------------------------------------------
    def test_no_template_none_passed(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf, "No Tpl Test")

        # No template uploaded for this project
        with patch.object(_jobs_mod, "get_workflow_runner") as mock_get_runner:
            mock_runner = MagicMock()
            mock_get_runner.return_value = mock_runner

            status, data, _ = self._create_job(session, csrf, pid)
            self.assertEqual(status, 201, data)

            self.assertTrue(mock_runner.submit_phase_1.called)
            call_kwargs = mock_runner.submit_phase_1.call_args.kwargs
            self.assertIsNone(
                call_kwargs.get("template_path"),
                "template_path must be None when no template is bound",
            )

    # ------------------------------------------------------------------
    # Test 4: Invalid template -> None passed
    # ------------------------------------------------------------------
    def test_invalid_template_none_passed(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf, "Invalid Tpl Test")

        # Upload a corrupt file with a .xlsx extension. The API stores it
        # but openpyxl validation fails, so validation_status = "invalid".
        corrupt_bytes = b"not a real xlsx file"
        status, tpl_data, _ = _upload_template(
            session, csrf, pid, corrupt_bytes, filename="corrupt.xlsx",
        )
        self.assertEqual(status, 201, tpl_data)
        self.assertEqual(tpl_data["validation_status"], "invalid")

        # Confirm the template is recorded with "invalid" status
        templates = self._list_templates(session, pid)
        self.assertEqual(len(templates), 1)
        self.assertEqual(templates[0]["validation_status"], "invalid")

        with patch.object(_jobs_mod, "get_workflow_runner") as mock_get_runner:
            mock_runner = MagicMock()
            mock_get_runner.return_value = mock_runner

            status, data, _ = self._create_job(session, csrf, pid)
            self.assertEqual(status, 201, data)

            self.assertTrue(mock_runner.submit_phase_1.called)
            call_kwargs = mock_runner.submit_phase_1.call_args.kwargs
            self.assertIsNone(
                call_kwargs.get("template_path"),
                "invalid templates must not be silently used",
            )

    # ------------------------------------------------------------------
    # Test 5: Original template unchanged
    # ------------------------------------------------------------------
    def test_original_template_unchanged(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf, "Unchanged Tpl Test")

        xlsx_bytes = _make_template_xlsx()
        original_sha = hashlib.sha256(xlsx_bytes).hexdigest()

        status, tpl_data, _ = _upload_template(session, csrf, pid, xlsx_bytes)
        self.assertEqual(status, 201, tpl_data)

        # Mock the workflow so the actual run does not execute (and thus
        # cannot modify the stored template).
        with patch.object(_jobs_mod, "get_workflow_runner") as mock_get_runner:
            mock_runner = MagicMock()
            mock_get_runner.return_value = mock_runner

            status, data, _ = self._create_job(session, csrf, pid)
            self.assertEqual(status, 201, data)

            call_kwargs = mock_runner.submit_phase_1.call_args.kwargs
            template_path = call_kwargs.get("template_path")
            self.assertIsNotNone(template_path)

        # The stored template file's SHA-256 must match the original upload.
        # The original template file is never modified by the workflow.
        with open(template_path, "rb") as fh:
            stored_sha = hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(
            stored_sha, original_sha,
            "stored template file must be identical to the original upload",
        )

    # ------------------------------------------------------------------
    # Test 6: Template fidelity (sheet names and order)
    # ------------------------------------------------------------------
    def test_template_fidelity_sheet_names(self):
        _, session, csrf = self._login()
        pid = self._create_project(session, csrf, "Fidelity Tpl Test")

        sheet_names = ["Category Analysis", "Market Analysis", "Keyword Analysis"]
        xlsx_bytes = _make_template_xlsx(sheet_names=sheet_names)

        status, tpl_data, _ = _upload_template(session, csrf, pid, xlsx_bytes)
        self.assertEqual(status, 201, tpl_data)
        self.assertEqual(tpl_data["validation_status"], "valid")

        # Read the stored template file and verify sheet names + order.
        # Use BytesIO because the storage path has no .xlsx extension
        # (the local storage backend stores files by ID, not by name).
        templates = self._list_templates(session, pid)
        self.assertEqual(len(templates), 1)
        storage_key = templates[0]["storage_key"]

        from openpyxl import load_workbook
        with open(storage_key, "rb") as fh:
            buf = io.BytesIO(fh.read())
        wb = load_workbook(buf, read_only=True)
        try:
            self.assertEqual(
                wb.sheetnames, sheet_names,
                "template sheet names and order must be preserved on storage",
            )
        finally:
            wb.close()


if __name__ == "__main__":
    unittest.main()
