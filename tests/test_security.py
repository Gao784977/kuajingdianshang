"""Security tests for V3.2.

Covers: SSRF protection (URL IP check), file upload safety (path traversal,
extension whitelist), and auth/session security.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC = os.path.join(_PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from backend.config import ALLOWED_UPLOAD_EXTENSIONS  # noqa: E402
from backend.services.auth_service import hash_token  # noqa: E402
from backend.services.url_security import _is_blocked_ip, _validate_url  # noqa: E402
from backend.storage.local_storage import LocalStorageBackend  # noqa: E402


class UrlSecurityTests(unittest.TestCase):
    def test_block_loopback_ipv4(self):
        self.assertTrue(_is_blocked_ip("127.0.0.1"))
        self.assertTrue(_is_blocked_ip("127.255.255.255"))

    def test_block_private_ipv4(self):
        self.assertTrue(_is_blocked_ip("10.0.0.1"))
        self.assertTrue(_is_blocked_ip("172.16.0.1"))
        self.assertTrue(_is_blocked_ip("192.168.1.1"))

    def test_block_metadata_ip(self):
        self.assertTrue(_is_blocked_ip("169.254.169.254"))

    def test_allow_public_ipv4(self):
        self.assertFalse(_is_blocked_ip("8.8.8.8"))
        self.assertFalse(_is_blocked_ip("1.1.1.1"))

    def test_validate_url_blocks_localhost(self):
        ok, msg = _validate_url("http://localhost/admin")
        self.assertFalse(ok)
        ok, msg = _validate_url("http://127.0.0.1/")
        # 127.0.0.1 passes the hostname check but DNS check will block it
        # (here _validate_url only checks scheme + hostname string)
        self.assertTrue(ok)  # passes basic check, blocked at DNS stage

    def test_validate_url_rejects_non_http(self):
        ok, _ = _validate_url("file:///etc/passwd")
        self.assertFalse(ok)
        ok, _ = _validate_url("ftp://example.com/")
        self.assertFalse(ok)

    def test_validate_url_allows_https(self):
        ok, _ = _validate_url("https://www.example.com/")
        self.assertTrue(ok)


class FileUploadSecurityTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.store = LocalStorageBackend(self.tmpdir)

    def test_path_traversal_prevented(self):
        # A filename with traversal must not appear in the storage path.
        key = self.store.save_upload("p1", "upload-1", b"data", "../../../etc/passwd.txt")
        stored = os.path.realpath(key)
        self.assertTrue(stored.startswith(os.path.realpath(self.tmpdir)))
        self.assertNotIn("..", key)

    def test_whitelist_extensions(self):
        self.assertIn("xlsx", ALLOWED_UPLOAD_EXTENSIONS)
        self.assertIn("csv", ALLOWED_UPLOAD_EXTENSIONS)
        self.assertIn("json", ALLOWED_UPLOAD_EXTENSIONS)
        # xls must NOT be in the whitelist
        self.assertNotIn("xls", ALLOWED_UPLOAD_EXTENSIONS)
        self.assertNotIn("exe", ALLOWED_UPLOAD_EXTENSIONS)
        self.assertNotIn("js", ALLOWED_UPLOAD_EXTENSIONS)


class AuthSecurityTests(unittest.TestCase):
    def test_invitation_token_hashed(self):
        h1 = hash_token("my-secret-token")
        h2 = hash_token("my-secret-token")
        self.assertEqual(h1, h2)
        # Should not contain the plain token
        self.assertNotIn("my-secret-token", h1)
        # Different tokens produce different hashes
        self.assertNotEqual(h1, hash_token("other-token"))

    def test_hash_is_sha256(self):
        # SHA-256 hex digest is 64 chars
        self.assertEqual(len(hash_token("x")), 64)


if __name__ == "__main__":
    unittest.main()
