"""Tests for V3.1.5 :mod:`src.modules.amazon.url_sources`.

Covers spec section 十一 URL-related test cases:

* URL 默认关闭 — :class:`FetchPolicy` defaults to off
* --allow-url-fetch — the master switch enables fetches
* URL 失败 — non-2xx and transport errors return a
  :class:`FetchResult` with the error details and no fabricated
  fields
* URL 结果记录 source_url 和 content_hash
* URL 与 Excel 冲突时同时保留两个值 (tested at the merge layer;
  here we verify the fetcher records both)
* 未注册 URL — fetcher refuses URLs not in the registry
* classify_url — all six URL kinds
* parsers — defensive extraction, never fabricates fields

No test touches the network. The fetcher's transport is swapped for
a fake callable that returns canned bytes.
"""

from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from modules.amazon.url_sources import (  # noqa: E402
    FetchPolicy,
    FetchResult,
    URLKind,
    UrlFetcher,
    UrlRegistry,
    classify_url,
    fetch_url,
    parse_ali1688_product_page,
    parse_amazon_brand_page,
    parse_amazon_category_page,
    parse_amazon_product_page,
    parse_amazon_search_page,
)
from modules.amazon.url_sources.url_registry import registry_from_input  # noqa: E402


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _fake_transport_ok(status=200, body=b"<html>ok</html>"):
    """Return a fake transport that succeeds with ``body``."""

    def transport(url, *, headers, timeout, max_bytes):
        return status, body, {"Content-Type": "text/html"}

    return transport


def _fake_transport_http_error(status=404):
    def transport(url, *, headers, timeout, max_bytes):
        return status, b"<html>not found</html>", {"Content-Type": "text/html"}

    return transport


def _fake_transport_exc(exc):
    def transport(url, *, headers, timeout, max_bytes):
        raise exc

    return transport


# ---------------------------------------------------------------------------
# FetchPolicy
# ---------------------------------------------------------------------------


class TestFetchPolicy(unittest.TestCase):
    """Tests for the policy gate."""

    def test_default_is_off(self):
        policy = FetchPolicy()
        decision = policy.evaluate("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "url_fetch_disabled")

    def test_allow_url_fetch_enables(self):
        policy = FetchPolicy(allow_url_fetch=True)
        decision = policy.evaluate("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "allowed")

    def test_blocks_non_http_scheme(self):
        policy = FetchPolicy(allow_url_fetch=True)
        decision = policy.evaluate("file:///etc/passwd")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "scheme_blocked")

    def test_blocks_ftp_scheme(self):
        policy = FetchPolicy(allow_url_fetch=True)
        decision = policy.evaluate("ftp://example.com/data.zip")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "scheme_blocked")

    def test_blocks_missing_scheme(self):
        policy = FetchPolicy(allow_url_fetch=True)
        decision = policy.evaluate("www.amazon.com/dp/B0DNVW368Z")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "scheme_blocked")

    def test_allows_https(self):
        policy = FetchPolicy(allow_url_fetch=True)
        decision = policy.evaluate("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertTrue(decision.allowed)

    def test_allows_http(self):
        policy = FetchPolicy(allow_url_fetch=True)
        decision = policy.evaluate("http://www.amazon.com/dp/B0DNVW368Z")
        self.assertTrue(decision.allowed)


# ---------------------------------------------------------------------------
# URL classifier
# ---------------------------------------------------------------------------


class TestClassifyUrl(unittest.TestCase):
    """Tests for :func:`classify_url`."""

    def test_amazon_product_dp(self):
        c = classify_url("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertEqual(c.kind, "amazon_product")
        self.assertEqual(c.confidence, "high")

    def test_amazon_product_gp(self):
        c = classify_url("https://www.amazon.com/gp/product/B0DNVW368Z")
        self.assertEqual(c.kind, "amazon_product")

    def test_amazon_product_with_query(self):
        c = classify_url("https://www.amazon.com/dp/B0DNVW368Z?psc=1")
        self.assertEqual(c.kind, "amazon_product")

    def test_amazon_search(self):
        c = classify_url("https://www.amazon.com/s?k=chicken+saddle")
        self.assertEqual(c.kind, "amazon_search")

    def test_amazon_category(self):
        c = classify_url("https://www.amazon.com/b?node=123456")
        self.assertEqual(c.kind, "amazon_category")

    def test_amazon_brand(self):
        c = classify_url("https://www.amazon.com/stores/PETSFIT")
        self.assertEqual(c.kind, "amazon_brand")

    def test_amazon_uk_host(self):
        c = classify_url("https://www.amazon.co.uk/dp/B0DNVW368Z")
        self.assertEqual(c.kind, "amazon_product")

    def test_amazon_de_host(self):
        c = classify_url("https://www.amazon.de/dp/B0DNVW368Z")
        self.assertEqual(c.kind, "amazon_product")

    def test_ali1688_product(self):
        c = classify_url("https://detail.1688.com/offer/1002172377422.html")
        self.assertEqual(c.kind, "ali1688_product")
        self.assertEqual(c.confidence, "high")

    def test_other_for_unknown_host(self):
        c = classify_url("https://example.com/some-page")
        self.assertEqual(c.kind, "other")
        self.assertEqual(c.confidence, "low")

    def test_other_for_amazon_unrecognised_path(self):
        c = classify_url("https://www.amazon.com/help")
        self.assertEqual(c.kind, "other")
        self.assertEqual(c.confidence, "medium")

    def test_empty_url_returns_other(self):
        c = classify_url("")
        self.assertEqual(c.kind, "other")
        self.assertEqual(c.confidence, "low")

    def test_none_url_returns_other(self):
        c = classify_url(None)  # type: ignore[arg-type]
        self.assertEqual(c.kind, "other")

    def test_classification_preserves_source_url(self):
        url = "https://www.amazon.com/dp/B0DNVW368Z?psc=1"
        c = classify_url(url)
        self.assertEqual(c.source_url, url)


# ---------------------------------------------------------------------------
# UrlRegistry
# ---------------------------------------------------------------------------


class TestUrlRegistry(unittest.TestCase):
    """Tests for :class:`UrlRegistry` and :func:`registry_from_input`."""

    def test_register_adds_entry(self):
        reg = UrlRegistry()
        entry = reg.register("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertEqual(len(reg), 1)
        self.assertEqual(entry.source_url, "https://www.amazon.com/dp/B0DNVW368Z")
        self.assertEqual(entry.kind, "amazon_product")

    def test_contains_returns_true_for_registered(self):
        reg = UrlRegistry()
        reg.register("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertTrue(reg.contains("https://www.amazon.com/dp/B0DNVW368Z"))

    def test_contains_returns_false_for_unregistered(self):
        reg = UrlRegistry()
        reg.register("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertFalse(reg.contains("https://www.amazon.com/dp/OTHERASIN"))

    def test_no_dedup_on_re_register(self):
        reg = UrlRegistry()
        url = "https://www.amazon.com/dp/B0DNVW368Z"
        reg.register(url)
        reg.register(url)
        self.assertEqual(len(reg), 2)

    def test_register_many(self):
        reg = UrlRegistry()
        urls = [
            "https://www.amazon.com/dp/B0DNVW368Z",
            "https://www.amazon.com/s?k=chicken+saddle",
            "https://detail.1688.com/offer/1002172377422.html",
        ]
        reg.register_many(urls)
        self.assertEqual(len(reg), 3)

    def test_registry_from_input_urls(self):
        user_input = {
            "urls": [
                {"url": "https://www.amazon.com/dp/B0DNVW368Z", "notes": "primary"},
            ]
        }
        reg = registry_from_input(user_input)
        self.assertEqual(len(reg), 1)
        self.assertEqual(reg.entries[0].provided_by, "urls")
        self.assertEqual(reg.entries[0].notes, "primary")

    def test_registry_from_input_product_candidates(self):
        user_input = {
            "product_candidates": [
                {"url": "https://www.amazon.com/dp/B0DNVW368Z"},
                {"url": "https://www.amazon.com/dp/OTHERASIN0"},
            ]
        }
        reg = registry_from_input(user_input)
        self.assertEqual(len(reg), 2)
        self.assertTrue(all(e.provided_by == "product_candidates" for e in reg))

    def test_registry_from_input_supplier_information(self):
        user_input = {
            "supplier_information": [
                {"url": "https://detail.1688.com/offer/1002172377422.html"},
            ]
        }
        reg = registry_from_input(user_input)
        self.assertEqual(len(reg), 1)
        self.assertEqual(reg.entries[0].kind, "ali1688_product")

    def test_registry_from_input_handles_empty(self):
        reg = registry_from_input({})
        self.assertEqual(len(reg), 0)

    def test_registry_from_input_handles_bare_strings(self):
        user_input = {
            "urls": ["https://www.amazon.com/dp/B0DNVW368Z"],
        }
        reg = registry_from_input(user_input)
        self.assertEqual(len(reg), 1)


# ---------------------------------------------------------------------------
# UrlFetcher — the core behaviour tests
# ---------------------------------------------------------------------------


class TestUrlFetcher(unittest.TestCase):
    """Tests for :class:`UrlFetcher` covering the spec test cases."""

    def setUp(self):
        self.registry = UrlRegistry()
        self.registry.register("https://www.amazon.com/dp/B0DNVW368Z")
        self.registry.register("https://detail.1688.com/offer/1002172377422.html")

    def test_default_off_returns_disabled(self):
        # Without --allow-url-fetch, the fetcher refuses immediately.
        fetcher = UrlFetcher(
            policy=FetchPolicy(),  # allow_url_fetch=False
            registry=self.registry,
            transport=_fake_transport_ok(),
        )
        result = fetcher.fetch("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "url_fetch_disabled")
        self.assertEqual(result.content, b"")
        self.assertEqual(result.content_hash, "")

    def test_allow_url_fetch_enables_fetch(self):
        fetcher = UrlFetcher(
            policy=FetchPolicy(allow_url_fetch=True),
            registry=self.registry,
            transport=_fake_transport_ok(body=b"<html>hello</html>"),
        )
        result = fetcher.fetch("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertTrue(result.success)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.content, b"<html>hello</html>")

    def test_unregistered_url_refused(self):
        fetcher = UrlFetcher(
            policy=FetchPolicy(allow_url_fetch=True),
            registry=self.registry,
            transport=_fake_transport_ok(),
        )
        result = fetcher.fetch("https://www.amazon.com/dp/UNREGISTERED1")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "url_not_registered")
        self.assertIn("not provided", result.error_message)

    def test_http_error_returns_failure(self):
        fetcher = UrlFetcher(
            policy=FetchPolicy(allow_url_fetch=True),
            registry=self.registry,
            transport=_fake_transport_http_error(status=404),
        )
        result = fetcher.fetch("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "http_error")
        self.assertEqual(result.http_status, 404)
        # No fabricated fields
        self.assertEqual(result.content, b"")
        self.assertEqual(result.content_hash, "")

    def test_transport_exception_captured(self):
        fetcher = UrlFetcher(
            policy=FetchPolicy(allow_url_fetch=True),
            registry=self.registry,
            transport=_fake_transport_exc(ConnectionError("dns fail")),
        )
        result = fetcher.fetch("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertFalse(result.success)
        self.assertEqual(result.error, "transport_error")
        self.assertIn("dns fail", result.error_message)

    def test_success_records_source_url(self):
        fetcher = UrlFetcher(
            policy=FetchPolicy(allow_url_fetch=True),
            registry=self.registry,
            transport=_fake_transport_ok(body=b"<html>page</html>"),
        )
        url = "https://www.amazon.com/dp/B0DNVW368Z"
        result = fetcher.fetch(url)
        self.assertEqual(result.source_url, url)
        self.assertEqual(result.source_type, "fetched_url")

    def test_success_records_content_hash(self):
        body = b"<html>page</html>"
        fetcher = UrlFetcher(
            policy=FetchPolicy(allow_url_fetch=True),
            registry=self.registry,
            transport=_fake_transport_ok(body=body),
        )
        result = fetcher.fetch("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertEqual(result.content_hash, hashlib.sha256(body).hexdigest())

    def test_success_hash_distinguishes_different_bodies(self):
        fetcher1 = UrlFetcher(
            policy=FetchPolicy(allow_url_fetch=True),
            registry=self.registry,
            transport=_fake_transport_ok(body=b"<html>v1</html>"),
        )
        fetcher2 = UrlFetcher(
            policy=FetchPolicy(allow_url_fetch=True),
            registry=self.registry,
            transport=_fake_transport_ok(body=b"<html>v2</html>"),
        )
        r1 = fetcher1.fetch("https://www.amazon.com/dp/B0DNVW368Z")
        r2 = fetcher2.fetch("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertNotEqual(r1.content_hash, r2.content_hash)

    def test_failure_does_not_fabricate_content(self):
        # Spec: "不伪造字段" — failures must not invent content.
        fetcher = UrlFetcher(
            policy=FetchPolicy(allow_url_fetch=True),
            registry=self.registry,
            transport=_fake_transport_http_error(status=500),
        )
        result = fetcher.fetch("https://www.amazon.com/dp/B0DNVW368Z")
        self.assertEqual(result.content, b"")
        self.assertEqual(result.content_hash, "")

    def test_functional_fetch_url_helper(self):
        body = b"<html>via helper</html>"
        result = fetch_url(
            "https://www.amazon.com/dp/B0DNVW368Z",
            policy=FetchPolicy(allow_url_fetch=True),
            registry=self.registry,
            transport=_fake_transport_ok(body=body),
        )
        self.assertIsInstance(result, FetchResult)
        self.assertTrue(result.success)
        self.assertEqual(result.content_hash, hashlib.sha256(body).hexdigest())


# ---------------------------------------------------------------------------
# Amazon parsers
# ---------------------------------------------------------------------------


_SAMPLE_AMAZON_PRODUCT_HTML = b"""
<html>
<head><title>Amazon.com: Mother Hen Chicken Saddle</title></head>
<body>
  <span id="productTitle">Mother Hen Chicken Saddle Protector with Adjustable Straps</span>
  <a id="bylineInfo">Visit the PETSFIT Store</a>
  <span class="a-price"><span class="a-offscreen">$22.84</span></span>
  <span class="a-icon-alt">4.5 out of 5 stars</span>
  <span id="acrCustomerReviewText">446 ratings</span>
  #29 in Poultry Habitat Supplies
  <span class="a-size-medium a-color-success">In Stock</span>
</body>
</html>
"""


_SAMPLE_AMAZON_SEARCH_HTML = b"""
<html>
<head><title>Amazon.com: chicken saddle</title></head>
<body>
  <div>1-16 of 500 results for "chicken saddle"</div>
  <a href="/dp/B0DNVW368Z">Product 1</a>
  <a href="/dp/B0CS9LV4RD">Product 2</a>
  <a href="/dp/B0GKV239MP">Product 3</a>
  <a href="/dp/B0DNVW368Z?th=1">Duplicate of Product 1</a>
</body>
</html>
"""


_SAMPLE_AMAZON_CATEGORY_HTML = b"""
<html>
<head><title>Poultry Habitat Supplies: Amazon.com</title></head>
<body>
  <a href="/dp/B0DNVW368Z">A</a>
  <a href="/dp/B0CS9LV4RD">B</a>
</body>
</html>
"""


_SAMPLE_AMAZON_BRAND_HTML = b"""
<html>
<head><title>PETSFIT Store: Amazon.com</title></head>
<body>
  <a href="/dp/B0DNVW368Z">A</a>
  <a href="/dp/B0CS9LV4RD">B</a>
</body>
</html>
"""


class TestAmazonProductParser(unittest.TestCase):
    def test_parses_all_fields(self):
        result = parse_amazon_product_page(
            _SAMPLE_AMAZON_PRODUCT_HTML,
            source_url="https://www.amazon.com/dp/B0DNVW368Z",
        )
        self.assertEqual(result.asin, "B0DNVW368Z")
        self.assertEqual(result.title, "Mother Hen Chicken Saddle Protector with Adjustable Straps")
        self.assertEqual(result.brand, "PETSFIT")
        self.assertEqual(result.price, "$22.84")
        self.assertEqual(result.rating, "4.5")
        self.assertEqual(result.review_count, "446 ratings")
        self.assertIn("Poultry Habitat Supplies", result.bsr_rank)
        self.assertEqual(result.availability, "In Stock")
        self.assertFalse(result.requires_review)
        self.assertEqual(result.confidence, "high")

    def test_missing_asin_flags_review(self):
        html = b"<html><span id='productTitle'>Title</span></html>"
        result = parse_amazon_product_page(html, source_url="https://www.amazon.com/no-asin-here")
        self.assertIsNone(result.asin)
        self.assertTrue(result.requires_review)

    def test_missing_title_flags_review(self):
        html = b"<html></html>"
        result = parse_amazon_product_page(
            html,
            source_url="https://www.amazon.com/dp/B0DNVW368Z",
        )
        self.assertEqual(result.asin, "B0DNVW368Z")
        self.assertIsNone(result.title)
        self.assertTrue(result.requires_review)

    def test_empty_html_does_not_fabricate(self):
        result = parse_amazon_product_page(b"", source_url="")
        self.assertIsNone(result.asin)
        self.assertIsNone(result.title)
        self.assertTrue(result.requires_review)
        self.assertEqual(result.confidence, "medium")

    def test_source_url_preserved(self):
        url = "https://www.amazon.com/dp/B0DNVW368Z?psc=1"
        result = parse_amazon_product_page(_SAMPLE_AMAZON_PRODUCT_HTML, source_url=url)
        self.assertEqual(result.source_url, url)


class TestAmazonSearchParser(unittest.TestCase):
    def test_parses_keyword_from_url(self):
        result = parse_amazon_search_page(
            _SAMPLE_AMAZON_SEARCH_HTML,
            source_url="https://www.amazon.com/s?k=chicken+saddle",
        )
        self.assertEqual(result.keyword, "chicken saddle")
        self.assertEqual(result.total_results, "500")
        self.assertEqual(len(result.results), 3)  # deduped
        self.assertEqual(result.results[0]["asin"], "B0DNVW368Z")
        self.assertFalse(result.requires_review)

    def test_no_keyword_flags_review(self):
        result = parse_amazon_search_page(
            _SAMPLE_AMAZON_SEARCH_HTML,
            source_url="https://www.amazon.com/s?rh=n%3A123456",
        )
        self.assertIsNone(result.keyword)
        self.assertTrue(result.requires_review)

    def test_dedups_asins(self):
        # Product 1 appears twice; should be deduped.
        result = parse_amazon_search_page(
            _SAMPLE_AMAZON_SEARCH_HTML,
            source_url="https://www.amazon.com/s?k=test",
        )
        asins = [r["asin"] for r in result.results]
        self.assertEqual(len(asins), len(set(asins)))


class TestAmazonCategoryParser(unittest.TestCase):
    def test_parses_category_and_asins(self):
        result = parse_amazon_category_page(
            _SAMPLE_AMAZON_CATEGORY_HTML,
            source_url="https://www.amazon.com/b?node=12345",
        )
        self.assertEqual(result.category_name, "Poultry Habitat Supplies: Amazon.com")
        self.assertEqual(len(result.products), 2)
        self.assertFalse(result.requires_review)


class TestAmazonBrandParser(unittest.TestCase):
    def test_parses_brand_and_asins(self):
        result = parse_amazon_brand_page(
            _SAMPLE_AMAZON_BRAND_HTML,
            source_url="https://www.amazon.com/stores/PETSFIT",
        )
        self.assertEqual(result.brand_name, "PETSFIT Store: Amazon.com")
        self.assertEqual(len(result.products), 2)


# ---------------------------------------------------------------------------
# 1688 parser
# ---------------------------------------------------------------------------


_SAMPLE_1688_HTML = b"""
<html>
<head>
  <meta name="keywords" content="chicken saddle, hen protector, poultry care">
  <title>3pcs chicken saddle hen protector - 1688</title>
</head>
<body>
  <script>
    window.runParams = {
      "unitPrice": "21.50",
      "beginAmount": 100,
      "companyName": "Yiwu Chengxin Technology Co., Ltd.",
      "image": "https://cbu01.1688.com/img/ibank/12345.jpg"
    };
  </script>
</body>
</html>
"""


class TestAli1688Parser(unittest.TestCase):
    def test_parses_all_fields(self):
        result = parse_ali1688_product_page(
            _SAMPLE_1688_HTML,
            source_url="https://detail.1688.com/offer/1002172377422.html",
        )
        self.assertEqual(result.offer_id, "1002172377422")
        self.assertIn("chicken saddle", result.title)
        self.assertEqual(result.price, "21.50")
        self.assertEqual(result.moq, "100")
        self.assertEqual(result.supplier, "Yiwu Chengxin Technology Co., Ltd.")
        self.assertIn("ibank", result.image_url or "")
        self.assertFalse(result.requires_review)
        self.assertEqual(result.confidence, "high")

    def test_missing_offer_id_flags_review(self):
        result = parse_ali1688_product_page(
            _SAMPLE_1688_HTML,
            source_url="https://detail.1688.com/offers/invalid.html",
        )
        self.assertIsNone(result.offer_id)
        self.assertTrue(result.requires_review)

    def test_empty_html_does_not_fabricate(self):
        result = parse_ali1688_product_page(b"", source_url="")
        self.assertIsNone(result.offer_id)
        self.assertIsNone(result.title)
        self.assertTrue(result.requires_review)


if __name__ == "__main__":
    unittest.main()
