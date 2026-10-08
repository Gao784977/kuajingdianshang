"""V3.1.5 — URL workflow layer.

Public surface:

* :class:`FetchPolicy` — decides whether a URL may be fetched.
  Default is **off**; only ``--allow-url-fetch`` enables network
  access, and only for URLs the user explicitly provided in their
  input JSON.
* :func:`classify_url` — categorises a URL as
  ``amazon_product`` / ``amazon_search`` / ``amazon_category`` /
  ``amazon_brand`` / ``ali1688_product`` / ``other`` based on path
  patterns. Pure, no network.
* :class:`UrlRegistry` — append-only registry of user-supplied URLs.
  The fetcher only ever fetches URLs that were registered here.
* :func:`fetch_url` — performs an HTTP GET via a swappable
  transport. Never sends cookies, tokens, or credentials; on failure
  returns a :class:`FetchResult` with the error details and no
  fabricated fields.
* :func:`parse_amazon_product_page` /
  :func:`parse_amazon_search_page` — parse Amazon HTML.
* :func:`parse_ali1688_product_page` — parse 1688 HTML.

Design rules (per spec section 五):

* Default off: ``FetchPolicy(allow_url_fetch=False)`` blocks every
  fetch attempt with reason ``"url_fetch_disabled"``.
* Only user-provided URLs may be fetched. The registry is the single
  source of truth — the fetcher refuses anything not registered.
* No login, no cookies, no tokens, no captcha bypass, no
  access-restriction circumvention.
* On failure: record URL, status, HTTP code, error message; do not
  invent fields; non-strict mode continues with Excel data; strict
  mode propagates per config.
* Every successful fetch records ``source_url`` and ``content_hash``
  (SHA-256 of the response body) so downstream merges can detect
  conflicts with Excel data and keep both values.
"""

from __future__ import annotations

from .ali1688_parser import parse_ali1688_product_page
from .amazon_parser import (
    parse_amazon_brand_page,
    parse_amazon_category_page,
    parse_amazon_product_page,
    parse_amazon_search_page,
)
from .fetch_policy import FetchPolicy, PolicyDecision
from .url_classifier import (
    AMAZON_KINDS,
    URLKind,
    UrlClassification,
    classify_url,
)
from .url_fetcher import FetchResult, UrlFetcher, fetch_url
from .url_registry import UrlEntry, UrlRegistry

__all__ = [
    "AMAZON_KINDS",
    "FetchPolicy",
    "FetchResult",
    "PolicyDecision",
    "URLKind",
    "UrlClassification",
    "UrlEntry",
    "UrlFetcher",
    "UrlRegistry",
    "classify_url",
    "fetch_url",
    "parse_ali1688_product_page",
    "parse_amazon_brand_page",
    "parse_amazon_category_page",
    "parse_amazon_product_page",
    "parse_amazon_search_page",
]
