"""Fetch policy — the single gate that decides whether a URL may be
fetched.

Per spec section 五, the default is **off**. ``--allow-url-fetch`` is
the only way to enable network access, and even then only URLs the
user explicitly provided in their input JSON are eligible. The
:class:`UrlRegistry` is consulted separately by the fetcher; this
module only answers "is fetching enabled at all?".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass
class PolicyDecision:
    """Outcome of :meth:`FetchPolicy.evaluate`.

    Attributes:
        allowed: True if the fetch may proceed.
        reason: Machine-readable reason code (always present, even
            when allowed). Examples: ``"allowed"``,
            ``"url_fetch_disabled"``, ``"scheme_blocked"``.
        detail: Human-readable detail, optional.
    """

    allowed: bool
    reason: str
    detail: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "detail": self.detail,
        }


# Schemes we will fetch. ``file://`` and ``ftp://`` are refused —
# only public HTTP/HTTPS pages are eligible per spec.
_ALLOWED_SCHEMES = {"http", "https"}


@dataclass
class FetchPolicy:
    """Decide whether a URL fetch is permitted.

    Args:
        allow_url_fetch: Master switch, mirrors the
            ``--allow-url-fetch`` CLI flag. Defaults False — no
            fetches are allowed.
        strict: When True, fetch failures are raised; when False
            (the project default), failures are recorded and the
            workflow continues with Excel data.
        timeout_seconds: Per-request timeout. Default 15s.
        max_bytes: Maximum response body size in bytes. Default 1 MiB
            to prevent runaway downloads; parsers only need the first
            chunk of the page.
    """

    allow_url_fetch: bool = False
    strict: bool = False
    timeout_seconds: int = 15
    max_bytes: int = 1024 * 1024

    def evaluate(self, url: str) -> PolicyDecision:
        """Decide if ``url`` may be fetched.

        This does *not* check the registry — that is the fetcher's
        responsibility. This method only evaluates policy gates that
        apply to every URL regardless of registry membership:
        master switch and URL scheme.
        """
        if not self.allow_url_fetch:
            return PolicyDecision(
                allowed=False,
                reason="url_fetch_disabled",
                detail=(
                    "URL fetch is disabled by default; pass "
                    "--allow-url-fetch to enable."
                ),
            )
        scheme = self._scheme_of(url)
        if scheme not in _ALLOWED_SCHEMES:
            return PolicyDecision(
                allowed=False,
                reason="scheme_blocked",
                detail=(
                    f"scheme '{scheme}' is not in {sorted(_ALLOWED_SCHEMES)}"
                ),
            )
        return PolicyDecision(allowed=True, reason="allowed")

    @staticmethod
    def _scheme_of(url: str) -> str:
        """Lower-cased scheme of ``url``, or "" when missing."""
        if "://" not in url:
            return ""
        return url.split("://", 1)[0].lower()


__all__ = ["FetchPolicy", "PolicyDecision"]
