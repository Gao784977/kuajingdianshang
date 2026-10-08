"""SSF protection tests at the DNS resolution and redirect level.

All tests use mocked ``socket.getaddrinfo`` and a mocked urllib opener so that
no real DNS lookups or HTTP requests to external (or internal) hosts are made.
The goal is to prove that the URL security service blocks SSRF attempts at the
DNS-resolution stage and re-validates the target after every redirect.
"""

from __future__ import annotations

import importlib
import os
import socket
import sys
import unittest
from unittest.mock import MagicMock, patch

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_SRC = os.path.join(_PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

import backend.config as _cfg  # noqa: E402
from backend.config import URL_FETCH_ENABLED  # noqa: E402
from backend.services.url_security import (  # noqa: E402
    _is_blocked_ip,
    _resolve_and_check,
    _validate_url,
    fetch_url,
)


def _v4_info(ip: str):
    """Build a getaddrinfo IPv4 entry."""
    return (socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))


def _v6_info(ip: str):
    """Build a getaddrinfo IPv6 entry (host, port, flowinfo, scope_id)."""
    return (socket.AF_INET6, socket.SOCK_STREAM, 6, "", (ip, 0, 0, 0))


class UrlFetchEnabledDefaultTests(unittest.TestCase):
    def test_url_fetch_enabled_default_false(self):
        """URL_FETCH_ENABLED must default to False (opt-in via CLI arg).

        The fetch_url function itself does not consult URL_FETCH_ENABLED; the
        workflow gates URL fetching behind an ``allow_url_fetch`` CLI argument
        whose default mirrors this config value. Verifying the config default
        is False therefore proves fetching is opt-in by default.
        """
        # Reload the config module with the env var unset to exercise the
        # default branch of _env_bool("URL_FETCH_ENABLED", False).
        saved = os.environ.pop("URL_FETCH_ENABLED", None)
        try:
            importlib.reload(_cfg)
            self.assertFalse(
                _cfg.URL_FETCH_ENABLED,
                "URL_FETCH_ENABLED must default to False so URL fetching "
                "stays opt-in until explicitly enabled via CLI arg.",
            )
        finally:
            if saved is not None:
                os.environ["URL_FETCH_ENABLED"] = saved
            importlib.reload(_cfg)


class DnsResolutionBlockedTests(unittest.TestCase):
    """Tests 2-4: mocked DNS resolution behaviour."""

    @patch("backend.services.url_security.socket.getaddrinfo")
    def test_dns_resolves_to_loopback_and_private_ipv4(self, mock_getaddrinfo):
        """A host whose DNS resolves to loopback/private IPv4 must be blocked."""
        mock_getaddrinfo.return_value = [
            _v4_info("127.0.0.1"),
            _v4_info("10.0.0.1"),
            _v4_info("192.168.1.1"),
            _v4_info("172.16.0.1"),
        ]
        ok, msg = _resolve_and_check("internal.example.com")
        self.assertFalse(ok)
        self.assertIn("blocked", msg.lower())

    @patch("backend.services.url_security.socket.getaddrinfo")
    def test_dns_resolves_to_ipv6_loopback_and_private(self, mock_getaddrinfo):
        """A host whose DNS resolves to IPv6 loopback/private must be blocked."""
        mock_getaddrinfo.return_value = [
            _v6_info("::1"),      # loopback
            _v6_info("fe80::1"),  # link-local
            _v6_info("fc00::1"),  # unique local (fc00::/7)
        ]
        ok, msg = _resolve_and_check("ipv6.example.com")
        self.assertFalse(ok)
        self.assertIn("blocked", msg.lower())

    @patch("backend.services.url_security.socket.getaddrinfo")
    def test_dns_resolves_to_public_ip_allowed(self, mock_getaddrinfo):
        """A host whose DNS resolves to a public IP must be allowed."""
        mock_getaddrinfo.return_value = [_v4_info("8.8.8.8")]
        ok, msg = _resolve_and_check("dns.google")
        self.assertTrue(ok)
        self.assertEqual(msg, "")

    @patch("backend.services.url_security.socket.getaddrinfo")
    def test_dns_resolution_failure_blocked(self, mock_getaddrinfo):
        """If DNS resolution itself fails, the host must be treated as blocked."""
        mock_getaddrinfo.side_effect = socket.gaierror("name resolution failed")
        ok, msg = _resolve_and_check("nonexistent.invalid")
        self.assertFalse(ok)
        self.assertIn("dns", msg.lower())


class RedirectSsrfTests(unittest.TestCase):
    """Tests 5-7: redirect targets are re-validated at the DNS level."""

    def _build_redirect_opener(self, location: str, status: int = 302):
        """Return a (build_opener mock, opener mock) pair serving a redirect."""
        fake_resp = MagicMock()
        fake_resp.status = status
        # Use a real dict so .get("Location") returns the plain string.
        fake_resp.headers = {"Location": location}
        opener_instance = MagicMock()
        opener_instance.open.return_value = fake_resp
        build_opener_mock = MagicMock(return_value=opener_instance)
        return build_opener_mock, opener_instance

    @patch("backend.services.url_security.urllib.request.build_opener")
    @patch("backend.services.url_security.socket.getaddrinfo")
    def test_redirect_to_localhost_blocked(self, mock_dns, mock_build_opener):
        """A 302 redirect to 127.0.0.1 must be blocked after re-resolution."""
        # First lookup (initial URL): public IP -> allowed.
        # Second lookup (redirect target 127.0.0.1): loopback -> blocked.
        mock_dns.side_effect = [
            [_v4_info("93.184.216.34")],
            [_v4_info("127.0.0.1")],
        ]
        build_mock, _ = self._build_redirect_opener("http://127.0.0.1:9999/")
        mock_build_opener.return_value = build_mock.return_value

        result = fetch_url("http://example.com/")
        self.assertEqual(result["status"], "failed")
        warnings = " ".join(result["warnings"])
        self.assertIn("SSRF", warnings)
        self.assertIn("127.0.0.1", warnings)

    @patch("backend.services.url_security.urllib.request.build_opener")
    @patch("backend.services.url_security.socket.getaddrinfo")
    def test_redirect_to_private_ip_blocked(self, mock_dns, mock_build_opener):
        """A 302 redirect to a private IPv4 range must be blocked."""
        mock_dns.side_effect = [
            [_v4_info("93.184.216.34")],   # initial URL: public
            [_v4_info("192.168.1.1")],     # redirect target: private
        ]
        build_mock, _ = self._build_redirect_opener("http://192.168.1.1/")
        mock_build_opener.return_value = build_mock.return_value

        result = fetch_url("http://example.com/")
        self.assertEqual(result["status"], "failed")
        warnings = " ".join(result["warnings"])
        self.assertIn("SSRF", warnings)
        self.assertIn("192.168.1.1", warnings)

    @patch("backend.services.url_security.urllib.request.build_opener")
    @patch("backend.services.url_security.socket.getaddrinfo")
    def test_redirect_revalidates_target_via_dns(self, mock_dns, mock_build_opener):
        """After a redirect the target must pass DNS validation again.

        The redirect target here is a benign-looking hostname that is NOT
        'localhost' (so it would pass a naive string check), yet its DNS
        resolves to a private IP. Blocking it proves the re-validation is
        DNS-level, not a mere string match.
        """
        mock_dns.side_effect = [
            [_v4_info("93.184.216.34")],  # initial URL resolves to public IP
            [_v4_info("10.0.0.1")],      # redirect target resolves to private
        ]
        build_mock, _ = self._build_redirect_opener("http://rebind.example.net/")
        mock_build_opener.return_value = build_mock.return_value

        result = fetch_url("http://example.com/")
        self.assertEqual(result["status"], "failed")
        warnings = " ".join(result["warnings"])
        # The redirect target hostname is not 'localhost', so a pure string
        # check would not flag it; the DNS re-resolution must catch 10.0.0.1.
        self.assertIn("SSRF", warnings)
        self.assertIn("10.0.0.1", warnings)
        # getaddrinfo must have been called twice: initial URL + redirect target.
        self.assertEqual(mock_dns.call_count, 2)


class StringCheckVsDnsCheckTests(unittest.TestCase):
    """Test 8: URL string validation is separate from DNS-level checking."""

    def test_string_check_passes_but_dns_check_blocks(self):
        """``http://127.0.0.1/`` passes the URL string check but is blocked
        once DNS resolution returns the loopback address.

        This proves the DNS/IP check is a distinct, stronger layer than the
        basic URL-scheme/hostname string validation.
        """
        # String-level validation: 127.0.0.1 is a syntactically valid http
        # host and is not the literal string 'localhost', so it passes.
        ok_str, _ = _validate_url("http://127.0.0.1/")
        self.assertTrue(
            ok_str,
            "127.0.0.1 should pass the basic URL string check; "
            "blocking must happen at the DNS/IP level instead.",
        )

        # DNS-level validation: resolving 127.0.0.1 yields a blocked IP.
        with patch("backend.services.url_security.socket.getaddrinfo") as mock_dns:
            mock_dns.return_value = [_v4_info("127.0.0.1")]
            ok_dns, msg = _resolve_and_check("127.0.0.1")
            self.assertFalse(ok_dns)
            self.assertIn("blocked", msg.lower())
            self.assertIn("127.0.0.1", msg)


if __name__ == "__main__":
    unittest.main()
