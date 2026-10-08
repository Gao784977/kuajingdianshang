"""URL classifier — categorise a URL by inspecting its host and path.

Pure, no network access. Recognises:

* ``amazon_product``   — ``amazon.{tld}/dp/{ASIN}``, ``/gp/product/{ASIN}``
* ``amazon_search``    — ``amazon.{tld}/s?...`` or ``/s?k=...``
* ``amazon_category``  — ``amazon.{tld}/b?node=...`` or ``/b?...``
* ``amazon_brand``     — ``amazon.{tld}/stores/{slug}`` or ``/stores?...``
* ``ali1688_product``  — ``detail.1688.com/offer/{id}.html``
* ``other``            — anything else (kept for traceability, but
  the fetcher will still respect the policy gates)

ASIN pattern: 10 chars, uppercase alphanumeric. The classifier does
not validate ASIN existence — it only matches the shape.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List


# The kind is a short string tag used by downstream code. It is NOT
# an enum to keep the module dependency-free and extensible: parsers
# can add new kinds without touching this file.
URLKind = str

# Kinds that target the Amazon product page family.
AMAZON_KINDS: List[URLKind] = [
    "amazon_product",
    "amazon_search",
    "amazon_category",
    "amazon_brand",
]


@dataclass
class UrlClassification:
    """Result of :func:`classify_url`.

    Attributes:
        kind: One of the kind strings described above.
        source_url: The exact URL that was classified (preserved so
            downstream records carry the original, not a normalised
            variant).
        confidence: ``high`` for pattern matches, ``medium`` for
            ambiguous Amazon pages, ``low`` for ``other``.
        detail: Free-text rationale (e.g. ``"matched /dp/<ASIN>"``).
    """

    kind: URLKind
    source_url: str
    confidence: str
    detail: str

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "detail": self.detail,
        }


# Hosts we treat as Amazon storefronts. The list is intentionally
# permissive — Amazon uses many country-code TLDs.
_AMAZON_HOST_RE = re.compile(
    r"^(?:www\.|smile\.)?amazon\.(?:com|co\.[a-z]{2}|[a-z]{2,3}|com\.[a-z]{2})$",
    re.IGNORECASE,
)

# 1688 product detail host.
_ALI1688_HOST_RE = re.compile(
    r"^(?:detail\.|m\.)?1688\.com$",
    re.IGNORECASE,
)

_ASIN_RE = re.compile(r"/(?:dp|gp/product|product)/([A-Z0-9]{10})(?:[/?#\"']|$)")
_SEARCH_PATH_RE = re.compile(r"^/s(?:[/?#]|$)")
_CATEGORY_PATH_RE = re.compile(r"^/b(?:[/?#]|$)")
_BRAND_PATH_RE = re.compile(r"^/stores(?:[/?#]|$)")
_ALI1688_OFFER_RE = re.compile(r"/offer/(\d+)\.html")


def classify_url(url: str) -> UrlClassification:
    """Classify ``url`` into a :class:`UrlClassification`.

    The function never raises. Garbage input returns kind
    ``"other"`` with confidence ``"low"`` and a detail explaining
    what was missing. This makes it safe to call on arbitrary
    user-supplied strings.
    """
    if not url or not isinstance(url, str):
        return UrlClassification(
            kind="other",
            source_url=str(url) if url is not None else "",
            confidence="low",
            detail="empty or non-string url",
        )

    source_url = url
    parsed = _split_url(url)
    if parsed is None:
        return UrlClassification(
            kind="other",
            source_url=source_url,
            confidence="low",
            detail="missing scheme or host",
        )

    scheme, host, path, query = parsed
    host_lower = host.lower()

    # --- Amazon family ---
    if _AMAZON_HOST_RE.match(host_lower):
        # Product page check first (most specific).
        asin_match = _ASIN_RE.search(path) or _ASIN_RE.search(path + "?" + query)
        if asin_match:
            return UrlClassification(
                kind="amazon_product",
                source_url=source_url,
                confidence="high",
                detail=f"matched /dp/ or /gp/product/ with ASIN {asin_match.group(1)}",
            )
        if _SEARCH_PATH_RE.match(path):
            return UrlClassification(
                kind="amazon_search",
                source_url=source_url,
                confidence="high",
                detail="matched /s search path",
            )
        if _CATEGORY_PATH_RE.match(path):
            return UrlClassification(
                kind="amazon_category",
                source_url=source_url,
                confidence="high",
                detail="matched /b category path",
            )
        if _BRAND_PATH_RE.match(path):
            return UrlClassification(
                kind="amazon_brand",
                source_url=source_url,
                confidence="high",
                detail="matched /stores brand path",
            )
        # Amazon host but unrecognised path — still Amazon, but
        # low confidence so downstream parsers know to be defensive.
        return UrlClassification(
            kind="other",
            source_url=source_url,
            confidence="medium",
            detail=f"amazon host but unrecognised path {path[:60]!r}",
        )

    # --- 1688 product page ---
    if _ALI1688_HOST_RE.match(host_lower):
        offer_match = _ALI1688_OFFER_RE.search(path)
        if offer_match:
            return UrlClassification(
                kind="ali1688_product",
                source_url=source_url,
                confidence="high",
                detail=f"matched 1688 /offer/<id>.html id={offer_match.group(1)}",
            )
        return UrlClassification(
            kind="other",
            source_url=source_url,
            confidence="medium",
            detail="1688 host but not an /offer/<id>.html path",
        )

    return UrlClassification(
        kind="other",
        source_url=source_url,
        confidence="low",
        detail=f"unrecognised host {host_lower!r}",
    )


def _split_url(url: str):
    """Split URL into (scheme, host, path, query). Returns None on failure."""
    if "://" not in url:
        return None
    scheme, rest = url.split("://", 1)
    scheme = scheme.lower()
    # Split host from path at the first /, ?, or #.
    host_end = len(rest)
    for i, ch in enumerate(rest):
        if ch in "/?#":
            host_end = i
            break
    host = rest[:host_end]
    remainder = rest[host_end:]
    # Remainder may start with /, ?, or #. Pull path and query apart.
    if remainder.startswith("?"):
        path = ""
        query = remainder[1:]
    elif remainder.startswith("#"):
        path = ""
        query = ""
    else:
        # remainder starts with / or is empty.
        path = remainder
        query = ""
        if "?" in path:
            path, _, query = path.partition("?")
    if not host:
        return None
    return scheme, host, path, query


__all__ = ["AMAZON_KINDS", "URLKind", "UrlClassification", "classify_url"]
