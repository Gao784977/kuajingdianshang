"""Tests for cooperative task cancellation in the workflow runner.

Verifies that:
- CancellationToken behaves correctly in isolation (cancel / is_cancelled /
  raise_if_cancelled).
- WorkflowRunner.cancel() flips the job status to ``cancelling`` and records a
  ``cancel_requested`` event.
- WorkflowRunner._check_cancel() raises _TaskCancelled once the token is set.
- A job cancelled mid-flight ends up with status ``cancelled`` (not
  ``completed``) and writes a ``cancelled`` system event.
- A cancelled job never persists formal output rows.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC = os.path.join(_PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import backend.services.workflow_runner as _wf_mod  # noqa: E402
from backend.services import auth_service as _auth_mod  # noqa: E402
from backend.services.workflow_runner import (  # noqa: E402
    PHASE_1_AGENTS,
    WorkflowRunner,
)
from backend.storage.base import CancellationToken, _TaskCancelled  # noqa: E402
from backend.storage.database import configure_paths, get_job_store  # noqa: E402

ADMIN_TOKEN = "test-cancel-token"

# Temp dirs for test isolation — created once per module.
_TMPDIR = tempfile.mkdtemp(prefix="cancel_test_")
_TEST_DB = os.path.join(_TMPDIR, "test.db")
_TEST_STORAGE = os.path.join(_TMPDIR, "web_storage")


def _reset_state():
    """Reset all backend singletons so each test starts from a clean DB.

    configure_paths closes any existing job-store connection; we then delete
    the SQLite file (plus WAL/SHM sidecars) so the next get_job_store() call
    builds a fresh schema with no leftover rows from a previous test.
    """
    os.environ["ADMIN_BOOTSTRAP_TOKEN"] = ADMIN_TOKEN
    configure_paths(db_path=_TEST_DB, storage_dir=_TEST_STORAGE)
    # Wipe the on-disk DB so each test starts with empty tables.
    for _suffix in ("", "-wal", "-shm"):
        _p = _TEST_DB + _suffix
        if os.path.exists(_p):
            try:
                os.remove(_p)
            except OSError:
                pass
    _auth_mod._auth_service = None
    _auth_mod._rate_limiter = _auth_mod._RateLimiter(_auth_mod.LOGIN_RATE_LIMIT_PER_MIN)
    # Reset the workflow runner singleton so a fresh instance is built against
    # the freshly reset job store.
    _wf_mod._runner = None
    get_job_store()


def _setup_user_and_project():
    """Insert a user and project row to satisfy foreign keys."""
    store = get_job_store()
    now = time.time()
    store._execute(
        "INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
        ("user-test", "tester", now),
    )
    store._execute(
        "INSERT INTO projects (project_id, owner_id, project_name, marketplace, "
        "created_at, updated_at) VALUES (?, ?, ?, 'us', ?, ?)",
        ("proj-test", "user-test", "CancelTest", now, now),
    )


def _create_job(job_id="job-cancel", phase="phase_1"):
    """Insert a job row and return its id."""
    store = get_job_store()
    store._execute(
        "INSERT INTO jobs (job_id, project_id, owner_id, phase, status, "
        "completed_agents, progress, warnings, errors, started_at, updated_at) "
        "VALUES (?, ?, ?, ?, 'queued', '[]', 0, '[]', '[]', ?, ?)",
        (job_id, "proj-test", "user-test", phase, time.time(), time.time()),
    )
    return job_id


def _job_status(job_id):
    row = get_job_store()._query_one(
        "SELECT status FROM jobs WHERE job_id = ?", (job_id,)
    )
    return row["status"] if row else None


def _job_errors(job_id):
    row = get_job_store()._query_one(
        "SELECT errors FROM jobs WHERE job_id = ?", (job_id,)
    )
    if not row:
        return []
    try:
        return json.loads(row["errors"])
    except (TypeError, ValueError):
        return []


def _events_for(job_id):
    return get_job_store()._query_all(
        "SELECT agent_name, status, message FROM job_events WHERE job_id = ? "
        "ORDER BY created_at ASC",
        (job_id,),
    )


def _output_count_for(job_id):
    row = get_job_store()._query_one(
        "SELECT COUNT(*) AS n FROM outputs WHERE job_id = ?", (job_id,)
    )
    return row["n"] if row else 0


# ---------------------------------------------------------------------------
# Unit tests for CancellationToken
# ---------------------------------------------------------------------------

class CancellationTokenTests(unittest.TestCase):
    """Pure unit tests for the CancellationToken primitive."""

    def test_token_starts_uncancelled(self):
        token = CancellationToken()
        self.assertFalse(token.is_cancelled)

    def test_cancel_sets_is_cancelled(self):
        token = CancellationToken()
        token.cancel()
        self.assertTrue(token.is_cancelled)

    def test_raise_if_cancelled_raises_task_cancelled(self):
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(_TaskCancelled):
            token.raise_if_cancelled()

    def test_raise_if_cancelled_noop_when_not_cancelled(self):
        token = CancellationToken()
        # Should not raise.
        token.raise_if_cancelled()

    def test_cancel_is_idempotent(self):
        token = CancellationToken()
        token.cancel()
        token.cancel()
        self.assertTrue(token.is_cancelled)


# ---------------------------------------------------------------------------
# Unit tests for WorkflowRunner._check_cancel
# ---------------------------------------------------------------------------

class CheckCancelTests(unittest.TestCase):
    """Tests that WorkflowRunner._check_cancel honours the token."""

    def setUp(self):
        _reset_state()
        _setup_user_and_project()
        self.runner = WorkflowRunner()

    def test_check_cancel_passes_when_not_cancelled(self):
        token = CancellationToken()
        # Should not raise.
        self.runner._check_cancel(token)

    def test_check_cancel_raises_task_cancelled_when_cancelled(self):
        token = CancellationToken()
        token.cancel()
        with self.assertRaises(_TaskCancelled):
            self.runner._check_cancel(token)


# ---------------------------------------------------------------------------
# Integration tests for WorkflowRunner.cancel()
# ---------------------------------------------------------------------------

class CancelMethodTests(unittest.TestCase):
    """Tests for the synchronous side-effects of WorkflowRunner.cancel()."""

    def setUp(self):
        _reset_state()
        _setup_user_and_project()
        self.runner = WorkflowRunner()
        self.job_id = _create_job()

    def test_cancel_sets_status_to_cancelling(self):
        self.runner.cancel(self.job_id)
        self.assertEqual(_job_status(self.job_id), "cancelling")

    def test_cancel_adds_cancel_requested_event(self):
        self.runner.cancel(self.job_id)
        events = _events_for(self.job_id)
        statuses = [(e["agent_name"], e["status"]) for e in events]
        self.assertIn(("system", "cancel_requested"), statuses)

    def test_cancel_sets_token_cancelled(self):
        # Manually register a token so cancel() has something to flip.
        token = CancellationToken()
        self.runner._cancel_tokens[self.job_id] = token
        self.runner.cancel(self.job_id)
        self.assertTrue(token.is_cancelled)

    def test_cancel_without_token_still_updates_status(self):
        # No token registered — cancel() should still mark the job.
        self.assertNotIn(self.job_id, self.runner._cancel_tokens)
        self.runner.cancel(self.job_id)
        self.assertEqual(_job_status(self.job_id), "cancelling")


# ---------------------------------------------------------------------------
# Integration tests: submit_phase_1 then cancel
# ---------------------------------------------------------------------------

class SubmitAndCancelTests(unittest.TestCase):
    """End-to-end cancellation: submit phase 1, cancel, verify outcome."""

    def setUp(self):
        _reset_state()
        _setup_user_and_project()
        self.runner = WorkflowRunner()
        self.job_id = _create_job()

    def _submit_and_cancel(self):
        """Submit phase 1, immediately cancel, and wait for the thread."""
        self.runner.submit_phase_1(
            job_id=self.job_id,
            project_id="proj-test",
            project_name="CancelTest",
            excel_files=[],
            user_input={},
            config={},
            cli_args={},
            output_dir=_TEST_STORAGE,
        )
        # Cancel as soon as submit returns. The runner thread has many
        # cooperative cancellation points before it ever touches V31Workflow,
        # so this reliably stops the workflow before any output is produced.
        self.runner.cancel(self.job_id)
        # Give the background thread time to observe the token and finalise.
        time.sleep(0.5)

    def test_cancelled_job_reaches_cancelled_status(self):
        self._submit_and_cancel()
        status = _job_status(self.job_id)
        # The job should have moved through "cancelling" to "cancelled".
        self.assertEqual(status, "cancelled",
                         f"expected 'cancelled', got '{status}'")

    def test_cancelled_job_writes_cancelled_event(self):
        self._submit_and_cancel()
        events = _events_for(self.job_id)
        statuses = [(e["agent_name"], e["status"]) for e in events]
        # The cancel_requested event from cancel()…
        self.assertIn(("system", "cancel_requested"), statuses)
        # …and the cancelled event from the worker thread.
        self.assertIn(("system", "cancelled"), statuses)

    def test_cancelled_job_produces_no_outputs(self):
        self._submit_and_cancel()
        self.assertEqual(
            _output_count_for(self.job_id), 0,
            "cancelled job must not persist formal outputs",
        )

    def test_cancelled_job_does_not_reach_completed(self):
        self._submit_and_cancel()
        status = _job_status(self.job_id)
        self.assertNotEqual(status, "completed",
                            "cancelled job must not be marked completed")

    def test_cancelled_job_does_not_save_phase1_completion_event(self):
        self._submit_and_cancel()
        events = _events_for(self.job_id)
        statuses = [(e["agent_name"], e["status"]) for e in events]
        # A fully-completed Phase 1 would record ("phase_1", "completed").
        self.assertNotIn(("phase_1", "completed"), statuses)


if __name__ == "__main__":
    unittest.main()
