"""URL fetch security service with DNS-level SSRF protection.

Wraps the existing V3.1 fetch_policy and adds:
- DNS resolution before connection (IPv4 + IPv6)
- Block loopback, private, link-local, reserved, CGNAT, cloud metadata IPs
- Re-validation after every redirect
- No inheritance of HTTP_PROXY/HTTPS_PROXY env vars
- Connect/read timeouts, max response bytes, max redirects, content-type limits

URL fetch failures never fabricate data or overwrite Excel data.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from backend.config import (
    URL_FETCH_CONNECT_TIMEOUT,
    URL_FETCH_MAX_BYTES,
    URL_FETCH_MAX_REDIRECTS,
    URL_FETCH_READ_TIMEOUT,
)

# IP ranges that must never be fetched (SSRF protection)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),        # "this" network
    ipaddress.ip_network("10.0.0.0/8"),       # private
    ipaddress.ip_network("100.64.0.0/10"),    # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / cloud metadata
    ipaddress.ip_network("172.16.0.0/12"),    # private
    ipaddress.ip_network("192.0.0.0/24"),     # IETF protocol assignments
    ipaddress.ip_network("192.0.2.0/24"),     # TEST-NET-1
    ipaddress.ip_network("192.88.99.0/24"),   # 6to4 relay anycast
    ipaddress.ip_network("192.168.0.0/16"),   # private
    ipaddress.ip_network("198.18.0.0/15"),    # benchmarking
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3
    ipaddress.ip_network("224.0.0.0/4"),      # multicast
    ipaddress.ip_network("240.0.0.0/4"),      # reserved
    # IPv6
    ipaddress.ip_network("::1/128"),          # loopback
    ipaddress.ip_network("fc00::/7"),         # unique local
    ipaddress.ip_network("fe80::/10"),        # link-local
    ipaddress.ip_network("ff00::/8"),         # multicast
]

ALLOWED_CONTENT_TYPES = {
    "text/html", "text/plain", "application/json", "application/xml",
    "text/xml", "text/csv", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _is_blocked_ip(ip_str: str) -> bool:
    """Return True if the IP is in a blocked range."""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True
    for network in _BLOCKED_NETWORKS:
        if ip in network:
            return True
    return False


def _resolve_and_check(host: str) -> Tuple[bool, str]:
    """Resolve hostname and check all resolved IPs against blocklist.

    Returns (allowed, message).
    """
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        return False, f"DNS resolution failed: {exc}"

    for info in infos:
        ip_str = info[4][0]
        # Strip IPv6 zone index
        if "%" in ip_str:
            ip_str = ip_str.split("%")[0]
        if _is_blocked_ip(ip_str):
            return False, f"Resolved IP {ip_str} is in a blocked range"
    return True, ""


def _validate_url(url: str) -> Tuple[bool, str]:
    """Basic URL validation before DNS resolution."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False, f"Scheme '{parsed.scheme}' not allowed (only http/https)"
    if not parsed.hostname:
        return False, "URL has no hostname"
    # Block obvious localhost/metadata hostnames before DNS
    host_lower = parsed.hostname.lower()
    if host_lower in ("localhost", "metadata", "metadata.google.internal"):
        return False, f"Hostname '{host_lower}' is not allowed"
    return True, ""


def fetch_url(url: str, max_redirects: int = URL_FETCH_MAX_REDIRECTS) -> Dict[str, Any]:
    """Fetch a URL with full SSRF protection.

    Returns a dict with: url, final_url, http_status, content_hash,
    status (success/failed), warnings, content (truncated).
    """
    result: Dict[str, Any] = {
        "url": url,
        "final_url": None,
        "http_status": None,
        "content_hash": None,
        "status": "failed",
        "warnings": [],
        "content": b"",
    }

    ok, msg = _validate_url(url)
    if not ok:
        result["warnings"].append(msg)
        return result

    current_url = url
    redirects = 0

    # Build opener that does NOT inherit proxy env vars
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    while redirects <= max_redirects:
        parsed = urlparse(current_url)
        ok, msg = _resolve_and_check(parsed.hostname)
        if not ok:
            result["warnings"].append(f"SSRF block for {current_url}: {msg}")
            return result

        try:
            req = urllib.request.Request(current_url, headers={"User-Agent": "AmazonResearchBot/3.2"})
            resp = opener.open(
                req,
                timeout=URL_FETCH_CONNECT_TIMEOUT + URL_FETCH_READ_TIMEOUT,
            )
        except urllib.error.HTTPError as exc:
            result["http_status"] = exc.code
            result["warnings"].append(f"HTTP error {exc.code}")
            return result
        except urllib.error.URLError as exc:
            result["warnings"].append(f"URL error: {exc.reason}")
            return result
        except socket.timeout:
            result["warnings"].append("Request timed out")
            return result
        except Exception as exc:
            result["warnings"].append(f"Request failed: {exc}")
            return result

        # Check redirect
        if resp.status in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if not location:
                result["warnings"].append(f"Redirect {resp.status} without Location")
                return result
            current_url = urllib.request.urljoin(current_url, location)
            redirects += 1
            resp.close()
            continue

        # Successful response
        result["final_url"] = current_url
        result["http_status"] = resp.status

        # Content-Type check
        ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if ctype and ctype not in ALLOWED_CONTENT_TYPES:
            result["warnings"].append(f"Content-Type '{ctype}' not in allowed list")
            resp.close()
            return result

        # Read with size limit
        data = resp.read(URL_FETCH_MAX_BYTES + 1)
        resp.close()
        if len(data) > URL_FETCH_MAX_BYTES:
            result["warnings"].append(
                f"Response exceeds {URL_FETCH_MAX_BYTES} bytes limit"
            )
            return result

        import hashlib
        result["content"] = data
        result["content_hash"] = hashlib.sha256(data).hexdigest()
        result["status"] = "success"
        return result

    result["warnings"].append(f"Exceeded max redirects ({max_redirects})")
    return result
