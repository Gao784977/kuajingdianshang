"""URL fetcher — performs an HTTP GET via a swappable transport.

Strict design rules (per spec section 五):

* No cookies, no Authorization headers, no tokens, no credentials.
  The fetch sends only ``User-Agent`` (a generic identifier) and
  ``Accept`` headers.
* The fetcher refuses any URL not present in the :class:`UrlRegistry`
  — this enforces "禁止访问未由用户提供的 URL".
* On any failure (DNS, connection, timeout, non-2xx status), the
  fetcher returns a :class:`FetchResult` with the error details and
  no fabricated fields. The caller decides whether to continue
  (non-strict) or abort (strict).
* Successful fetches record ``source_url`` and ``content_hash``
  (SHA-256 hex of the response body) so downstream merges can detect
  conflicts with Excel data and keep both values.

Transport abstraction
----------------------

The default transport is :func:`_urllib_transport` (stdlib
``urllib.request``). Tests inject a fake transport that returns
canned bytes — the test suite never touches the network.

A transport is any callable ``(url, headers, timeout, max_bytes) ->
(status_code: int, body: bytes, response_headers: dict)``. It must
raise on network failure so the fetcher can capture the error.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from .fetch_policy import FetchPolicy
from .url_registry import UrlRegistry

Transport = Callable[..., "tuple[int, bytes, dict]"]


@dataclass
class FetchResult:
    """Outcome of a single :meth:`UrlFetcher.fetch` call.

    Attributes:
        source_url: The URL that was fetched.
        success: True if the fetch returned a 2xx and a body.
        http_status: Integer HTTP status code, or 0 when the request
            never reached the server (DNS / connection error).
        content_hash: SHA-256 hex of the response body, or "" on
            failure. Always recorded on success so downstream code
            can compare with Excel content hashes.
        content: The response body as bytes on success, empty on
            failure. Parsers receive this.
        error: Machine-readable error code on failure
            (``"url_fetch_disabled"``, ``"url_not_registered"``,
            ``"scheme_blocked"``, ``"http_error"``, ``"transport_error"``).
        error_message: Human-readable detail on failure.
        source_type: Always ``"fetched_url"`` on success — matches
            the V3.1 source priority order.
    """

    source_url: str
    success: bool
    http_status: int = 0
    content_hash: str = ""
    content: bytes = b""
    error: str = ""
    error_message: str = ""
    source_type: str = "fetched_url"
    response_headers: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_url": self.source_url,
            "success": self.success,
            "http_status": self.http_status,
            "content_hash": self.content_hash,
            "content_len": len(self.content),
            "error": self.error,
            "error_message": self.error_message,
            "source_type": self.source_type,
            "response_headers": dict(self.response_headers),
        }


# Generic UA — identifies the bot as a research tool. Does NOT
# impersonate a browser (no fake Chrome version), since impersonating
# a browser to bypass bot detection would violate "禁止绕过访问限制".
_USER_AGENT = "Mozilla/5.0 (compatible; AmazonMarketResearchBot/3.1; +research)"
_ACCEPT = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"


@dataclass
class UrlFetcher:
    """Fetch URLs subject to a :class:`FetchPolicy` and registry.

    Args:
        policy: The fetch policy (master switch, scheme gates).
        registry: The registry of user-supplied URLs.
        transport: Optional callable used to perform the HTTP GET.
            If None, :func:`_urllib_transport` is used.
    """

    policy: FetchPolicy
    registry: UrlRegistry
    transport: Optional[Transport] = None

    def fetch(self, url: str) -> FetchResult:
        """Fetch ``url`` and return a :class:`FetchResult`.

        Order of checks (each returns early on failure):

        1. Policy: ``--allow-url-fetch`` must be on and the scheme
           must be http/https. Else ``error="url_fetch_disabled"``
           or ``error="scheme_blocked"``.
        2. Registry: ``url`` must be present in the registry. Else
           ``error="url_not_registered"``.
        3. Transport: perform the HTTP GET. Any exception is captured
           into ``error="transport_error"``; a non-2xx status is
           ``error="http_error"``.
        4. Success: compute ``content_hash`` and return the body.
        """
        decision = self.policy.evaluate(url)
        if not decision.allowed:
            return FetchResult(
                source_url=url,
                success=False,
                error=decision.reason,
                error_message=decision.detail,
            )
        if not self.registry.contains(url):
            return FetchResult(
                source_url=url,
                success=False,
                error="url_not_registered",
                error_message=(
                    "URL was not provided in user input; refusing to fetch "
                    "unregistered URLs per spec section 五."
                ),
            )

        transport = self.transport or _urllib_transport
        try:
            status, body, headers = transport(
                url,
                headers={"User-Agent": _USER_AGENT, "Accept": _ACCEPT},
                timeout=self.policy.timeout_seconds,
                max_bytes=self.policy.max_bytes,
            )
        except Exception as exc:  # noqa: BLE001
            return FetchResult(
                source_url=url,
                success=False,
                error="transport_error",
                error_message=f"{type(exc).__name__}: {exc}",
            )

        if not (200 <= status < 300):
            return FetchResult(
                source_url=url,
                success=False,
                http_status=status,
                error="http_error",
                error_message=f"HTTP {status}",
                response_headers=_stringify_headers(headers),
            )

        return FetchResult(
            source_url=url,
            success=True,
            http_status=status,
            content_hash=hashlib.sha256(body).hexdigest(),
            content=body,
            response_headers=_stringify_headers(headers),
        )


def fetch_url(
    url: str,
    *,
    policy: FetchPolicy,
    registry: UrlRegistry,
    transport: Optional[Transport] = None,
) -> FetchResult:
    """Functional wrapper around :meth:`UrlFetcher.fetch`."""
    fetcher = UrlFetcher(policy=policy, registry=registry, transport=transport)
    return fetcher.fetch(url)


def _urllib_transport(
    url: str,
    *,
    headers: Dict[str, str],
    timeout: int,
    max_bytes: int,
):
    """Default HTTP transport using stdlib urllib.

    Sends only the supplied headers — no cookies, no auth. Caps the
    response body at ``max_bytes`` to avoid runaway downloads.
    """
    import urllib.request

    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        status = resp.status
        body = resp.read(max_bytes)
        response_headers = {k: v for k, v in resp.headers.items()}
    return status, body, response_headers


def _stringify_headers(headers: Any) -> Dict[str, str]:
    """Coerce a headers mapping into ``Dict[str, str]``."""
    if not headers:
        return {}
    out: Dict[str, str] = {}
    if isinstance(headers, dict):
        for k, v in headers.items():
            out[str(k)] = str(v)
    else:
        # email.message.Message or similar
        try:
            for k, v in headers.items():
                out[str(k)] = str(v)
        except Exception:
            pass
    return out


__all__ = [
    "FetchResult",
    "Transport",
    "UrlFetcher",
    "fetch_url",
]
