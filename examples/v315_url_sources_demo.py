"""V3.1.5 demo — URL registry, default-off policy, and fetcher.

Walks through the URL workflow layer:

1. Build a registry from user input (URLs only, never invented).
2. Show the default-off policy blocking fetches.
3. Enable --allow-url-fetch and fetch via a fake transport (no
   network access in the demo).
4. Show failure paths: unregistered URL, HTTP 404, transport error.
5. Parse the fetched HTML with the Amazon product parser.

Run: ``python -B examples/v315_url_sources_demo.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from modules.amazon.url_sources import (  # noqa: E402
    FetchPolicy,
    UrlFetcher,
    UrlRegistry,
    classify_url,
    parse_amazon_product_page,
)
from modules.amazon.url_sources.url_registry import registry_from_input  # noqa: E402


# Fake transport that returns a sample Amazon product page.
_SAMPLE_PRODUCT_HTML = b"""
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


def _fake_transport(body=_SAMPLE_PRODUCT_HTML, status=200):
    def transport(url, *, headers, timeout, max_bytes):
        return status, body, {"Content-Type": "text/html"}

    return transport


def _fake_transport_404():
    def transport(url, *, headers, timeout, max_bytes):
        return 404, b"<html>not found</html>", {"Content-Type": "text/html"}

    return transport


def _fake_transport_dns_error():
    def transport(url, *, headers, timeout, max_bytes):
        raise ConnectionError("simulated DNS failure")

    return transport


def main() -> int:
    print("=" * 70)
    print("V3.1.5 demo — URL registry, default-off policy, fetcher")
    print("=" * 70)

    # Step 1: build registry from user input
    user_input = {
        "urls": [
            {
                "url": "https://www.amazon.com/dp/B0DNVW368Z",
                "notes": "primary product",
            },
            {
                "url": "https://detail.1688.com/offer/1002172377422.html",
                "notes": "supplier source",
            },
        ],
        "product_candidates": [
            {"url": "https://www.amazon.com/dp/B0CS9LV4RD"},
        ],
    }
    print("\n[1/5] Building registry from user input")
    registry = registry_from_input(user_input)
    print(f"      registered {len(registry)} URLs:")
    for entry in registry:
        c = entry.classification
        print(
            f"        - {entry.source_url}\n"
            f"          kind={c.kind}, confidence={c.confidence}, "
            f"provided_by={entry.provided_by}"
        )

    # Step 2: default-off policy
    print("\n[2/5] Default-off policy (no --allow-url-fetch)")
    policy_off = FetchPolicy()  # allow_url_fetch=False
    url = "https://www.amazon.com/dp/B0DNVW368Z"
    decision = policy_off.evaluate(url)
    print(f"      evaluate({url})")
    print(f"      allowed={decision.allowed}, reason={decision.reason}")

    # Step 3: enable --allow-url-fetch and fetch via fake transport
    print("\n[3/5] Enable --allow-url-fetch, fetch via fake transport")
    policy_on = FetchPolicy(allow_url_fetch=True)
    fetcher = UrlFetcher(
        policy=policy_on,
        registry=registry,
        transport=_fake_transport(),
    )
    result = fetcher.fetch(url)
    print(f"      success={result.success}")
    print(f"      http_status={result.http_status}")
    print(f"      content_hash={result.content_hash[:16]}...")
    print(f"      source_type={result.source_type}")
    print(f"      content_len={len(result.content)} bytes")

    # Step 4: failure paths
    print("\n[4/5] Failure paths")
    # 4a: unregistered URL
    result_unreg = fetcher.fetch("https://www.amazon.com/dp/UNREGISTERED1")
    print(
        f"      unregistered URL: success={result_unreg.success}, "
        f"error={result_unreg.error}"
    )
    # 4b: HTTP 404
    fetcher_404 = UrlFetcher(
        policy=policy_on,
        registry=registry,
        transport=_fake_transport_404(),
    )
    result_404 = fetcher_404.fetch(url)
    print(
        f"      HTTP 404: success={result_404.success}, "
        f"error={result_404.error}, http_status={result_404.http_status}"
    )
    # 4c: transport exception
    fetcher_exc = UrlFetcher(
        policy=policy_on,
        registry=registry,
        transport=_fake_transport_dns_error(),
    )
    result_exc = fetcher_exc.fetch(url)
    print(
        f"      transport error: success={result_exc.success}, "
        f"error={result_exc.error}, msg={result_exc.error_message}"
    )

    # Step 5: parse the fetched HTML
    print("\n[5/5] Parse fetched Amazon product page")
    parsed = parse_amazon_product_page(result.content, source_url=url)
    print(f"      asin: {parsed.asin}")
    print(f"      title: {parsed.title}")
    print(f"      brand: {parsed.brand}")
    print(f"      price: {parsed.price}")
    print(f"      rating: {parsed.rating}")
    print(f"      review_count: {parsed.review_count}")
    print(f"      bsr_rank: {parsed.bsr_rank}")
    print(f"      availability: {parsed.availability}")
    print(f"      requires_review: {parsed.requires_review}")
    print(f"      confidence: {parsed.confidence}")

    # Classify the 1688 URL too
    print("\n[bonus] Classify 1688 URL")
    ali_url = "https://detail.1688.com/offer/1002172377422.html"
    c = classify_url(ali_url)
    print(f"      {ali_url}")
    print(f"      kind={c.kind}, confidence={c.confidence}, detail={c.detail}")

    print("\n" + "=" * 70)
    print("V3.1.5 demo complete.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
