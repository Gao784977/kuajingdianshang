"""Web storage layer tests for V3.2.

Tests the StorageBackend abstraction (local file system) and SQLite job store.
All tests use temporary directories so they never conflict with a running
dev server or touch the real data/web.db file.
"""

from __future__ import annotations

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

from backend.storage.job_store import LocalJobStore  # noqa: E402
from backend.storage.local_storage import LocalStorageBackend  # noqa: E402


class LocalStorageTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = LocalStorageBackend(self.tmpdir)

    def test_save_and_read_upload(self):
        key = self.store.save_upload("project-1", "upload-1", b"hello world", "test.txt")
        self.assertTrue(key)
        data = self.store.read_file(key)
        self.assertEqual(data, b"hello world")

    def test_original_name_preserved(self):
        key = self.store.save_upload("project-1", "upload-1", b"data", "my-report.xlsx")
        self.assertEqual(self.store.original_name(key), "my-report.xlsx")

    def test_storage_path_not_user_filename(self):
        # The storage key must NOT contain the user-supplied filename
        # (path traversal prevention). It uses upload_id instead.
        key = self.store.save_upload("project-1", "upload-1", b"data", "../../etc/passwd")
        self.assertNotIn("passwd", key)
        self.assertNotIn("..", key)

    def test_delete_file(self):
        key = self.store.save_upload("project-1", "upload-1", b"data", "f.txt")
        self.assertTrue(self.store.delete_file(key))
        self.assertFalse(self.store.delete_file(key))  # already gone

    def test_sha256(self):
        self.assertEqual(
            LocalStorageBackend.sha256(b"hello"),
            "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824",
        )

    def test_save_output(self):
        key = self.store.save_output("project-1", "output-1", b"report", "report.xlsx")
        data = self.store.read_file(key)
        self.assertEqual(data, b"report")


class JobStoreTests(unittest.TestCase):
    """Tests for LocalJobStore using independent temp SQLite files.

    Each test gets a fresh temp directory and SQLite file, so there is
    no dependency on the global data/web.db and no conflict with a
    running dev server.
    """

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="jobstore_test_")
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.store = LocalJobStore(self.db_path)
        self.store.init_schema()
        # Insert a user and project to satisfy foreign keys
        _t = time.time()
        self.store._execute(
            "INSERT INTO users (user_id, username, created_at) VALUES (?, ?, ?)",
            ("user-1", "tester", _t),
        )
        self.store._execute(
            "INSERT INTO projects (project_id, owner_id, project_name, marketplace, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("project-1", "user-1", "Test", "us", _t, _t),
        )

    def tearDown(self):
        self.store.close()

    def test_create_and_get_job(self):
        job_id = self.store.create_job({
            "project_id": "project-1",
            "owner_id": "user-1",
            "phase": "phase_1",
            "status": "queued",
        })
        fetched = self.store.get_job(job_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["project_id"], "project-1")
        self.assertEqual(fetched["status"], "queued")

    def test_update_job_status(self):
        job_id = self.store.create_job({
            "project_id": "project-1", "owner_id": "user-1",
        })
        self.store.update_job(job_id, {"status": "running", "current_agent": "A1"})
        fetched = self.store.get_job(job_id)
        self.assertEqual(fetched["status"], "running")
        self.assertEqual(fetched["current_agent"], "A1")

    def test_add_and_list_events(self):
        job_id = self.store.create_job({
            "project_id": "project-1", "owner_id": "user-1",
        })
        self.store.add_event(job_id, "A1", "start", "agent started", {"k": "v"})
        self.store.add_event(job_id, "A1", "done", "agent done")
        events = self.store.list_events(job_id)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["agent_name"], "A1")
        self.assertEqual(events[0]["status"], "start")
        self.assertEqual(events[0]["payload"], {"k": "v"})

    def test_completed_agents_persisted(self):
        job_id = self.store.create_job({
            "project_id": "project-1", "owner_id": "user-1",
            "completed_agents": ["A1", "A2"],
        })
        fetched = self.store.get_job(job_id)
        self.assertEqual(fetched["completed_agents"], ["A1", "A2"])


if __name__ == "__main__":
    unittest.main()
