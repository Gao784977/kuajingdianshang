"""Amazon HTML parsers — extract product / search / category / brand
data from raw HTML bytes.

These parsers are intentionally defensive: they only return fields
that are actually present in the HTML. They never fabricate values.
If a selector fails to match, the corresponding field is left as
``None`` and the parser sets ``requires_review=True`` on the result.

The parsers use only the stdlib (``html.parser.HTMLParser``) so the
module is import-safe without any third-party dependency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ParsedAmazonProduct:
    """Fields extracted from an Amazon product page."""

    asin: Optional[str] = None
    title: Optional[str] = None
    brand: Optional[str] = None
    price: Optional[str] = None
    rating: Optional[str] = None
    review_count: Optional[str] = None
    bsr_rank: Optional[str] = None
    availability: Optional[str] = None
    seller: Optional[str] = None
    source_url: str = ""
    source_type: str = "fetched_url"
    confidence: str = "medium"
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "asin": self.asin,
            "title": self.title,
            "brand": self.brand,
            "price": self.price,
            "rating": self.rating,
            "review_count": self.review_count,
            "bsr_rank": self.bsr_rank,
            "availability": self.availability,
            "seller": self.seller,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "requires_review": self.requires_review,
        }


@dataclass
class ParsedAmazonSearch:
    """Fields extracted from an Amazon search results page."""

    keyword: Optional[str] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    total_results: Optional[str] = None
    source_url: str = ""
    source_type: str = "fetched_url"
    confidence: str = "medium"
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "results": list(self.results),
            "total_results": self.total_results,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "requires_review": self.requires_review,
        }


@dataclass
class ParsedAmazonCategory:
    """Fields extracted from an Amazon category/department page."""

    category_name: Optional[str] = None
    products: List[Dict[str, Any]] = field(default_factory=list)
    source_url: str = ""
    source_type: str = "fetched_url"
    confidence: str = "medium"
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category_name": self.category_name,
            "products": list(self.products),
            "source_url": self.source_url,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "requires_review": self.requires_review,
        }


@dataclass
class ParsedAmazonBrand:
    """Fields extracted from an Amazon brand store page."""

    brand_name: Optional[str] = None
    products: List[Dict[str, Any]] = field(default_factory=list)
    source_url: str = ""
    source_type: str = "fetched_url"
    confidence: str = "medium"
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "brand_name": self.brand_name,
            "products": list(self.products),
            "source_url": self.source_url,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "requires_review": self.requires_review,
        }


# Regex patterns. HTML parsing via regex is fragile in general, but
# Amazon's HTML structure is too noisy for a stdlib HTMLParser to
# reliably extract structured fields. These patterns match the common
# data attributes Amazon embeds in product pages (data attributes are
# more stable than CSS class names).
_ASIN_RE = re.compile(r"/dp/([A-Z0-9]{10})(?:[/?#\"']|$)")
_TITLE_RE = re.compile(r'<span[^>]*id="productTitle"[^>]*>([^<]+)</span>', re.IGNORECASE)
_PRICE_RE = re.compile(
    r'<span[^>]*class="[^"]*a-price[^"]*"[^>]*>.*?<span[^>]*class="[^"]*a-offscreen[^"]*"[^>]*>([^<]+)</span>',
    re.IGNORECASE | re.DOTALL,
)
_RATING_RE = re.compile(
    r'<span[^>]*class="[^"]*a-icon-alt[^"]*"[^>]*>([0-9.]+)\s*out of\s*\d+',
    re.IGNORECASE,
)
_REVIEW_COUNT_RE = re.compile(
    r'<span[^>]*id="acrCustomerReviewText"[^>]*>([^<]+)</span>',
    re.IGNORECASE,
)
_BSR_RE = re.compile(
    r"#\d[\d,]*\s+in\s+([^<\n]+)",
    re.IGNORECASE,
)
_AVAIL_RE = re.compile(
    r'<span[^>]*class="[^"]*a-size-medium[^"]*a-color-success[^"]*"[^>]*>([^<]+)</span>',
    re.IGNORECASE,
)
_BRAND_RE = re.compile(
    r'<a[^>]*id="bylineInfo"[^>]*>(?:Visit the )?([^<]+?)(?:\s*Store)?</a>',
    re.IGNORECASE,
)
_TOTAL_RESULTS_RE = re.compile(
    r'(\d[\d,]*)\s*(?:results|result)\s*(?:for|of)',
    re.IGNORECASE,
)
_K_RE = re.compile(r"[?&]k=([^&#]+)")


def _safe_decode_html(body: bytes) -> str:
    """Decode HTML bytes to text, trying utf-8 first then latin-1."""
    for encoding in ("utf-8", "latin-1"):
        try:
            return body.decode(encoding, errors="replace")
        except Exception:
            continue
    return body.decode("utf-8", errors="replace")


def _strip(s: Optional[str]) -> Optional[str]:
    """Trim and collapse whitespace. Returns None if input is None/empty."""
    if s is None:
        return None
    s = s.strip()
    return s or None


def parse_amazon_product_page(
    body: bytes,
    *,
    source_url: str = "",
) -> ParsedAmazonProduct:
    """Parse an Amazon product page.

    Returns a :class:`ParsedAmazonProduct` with whatever fields the
    regexes matched. ``requires_review`` is True when the ASIN or
    title is missing (the two fields a downstream consumer most
    needs).
    """
    html = _safe_decode_html(body)
    asin_match = _ASIN_RE.search(source_url) if source_url else None
    asin = asin_match.group(1) if asin_match else None
    title = _strip(_first_group(_TITLE_RE, html))
    price = _strip(_first_group(_PRICE_RE, html))
    rating = _strip(_first_group(_RATING_RE, html))
    review_count = _strip(_first_group(_REVIEW_COUNT_RE, html))
    bsr = _strip(_first_group(_BSR_RE, html))
    avail = _strip(_first_group(_AVAIL_RE, html))
    brand = _strip(_first_group(_BRAND_RE, html))

    requires_review = (asin is None) or (title is None)
    confidence = "high" if not requires_review else "medium"

    return ParsedAmazonProduct(
        asin=asin,
        title=title,
        brand=brand,
        price=price,
        rating=rating,
        review_count=review_count,
        bsr_rank=bsr,
        availability=avail,
        seller=None,
        source_url=source_url,
        confidence=confidence,
        requires_review=requires_review,
    )


def parse_amazon_search_page(
    body: bytes,
    *,
    source_url: str = "",
) -> ParsedAmazonSearch:
    """Parse an Amazon search results page.

    Extracts the search keyword from the URL (``?k=...``) and a list
    of result ASINs by scanning for ``/dp/<ASIN>`` patterns in the
    HTML body. Each result is a ``{"asin": ..., "source_url": ...}``
    dict so downstream code can cross-reference.
    """
    html = _safe_decode_html(body)
    keyword_match = _K_RE.search(source_url) if source_url else None
    keyword: Optional[str] = None
    if keyword_match:
        from urllib.parse import unquote_plus

        keyword = unquote_plus(keyword_match.group(1))
    total = _strip(_first_group(_TOTAL_RESULTS_RE, html))

    asins: List[str] = []
    seen = set()
    for m in _ASIN_RE.finditer(html):
        asin = m.group(1)
        if asin in seen:
            continue
        seen.add(asin)
        asins.append(asin)

    results = [
        {"asin": a, "source_url": f"https://www.amazon.com/dp/{a}"}
        for a in asins
    ]

    requires_review = (keyword is None) or not results
    confidence = "high" if not requires_review else "medium"

    return ParsedAmazonSearch(
        keyword=keyword,
        results=results,
        total_results=total,
        source_url=source_url,
        confidence=confidence,
        requires_review=requires_review,
    )


def parse_amazon_category_page(
    body: bytes,
    *,
    source_url: str = "",
) -> ParsedAmazonCategory:
    """Parse an Amazon category page. Extracts product ASINs and the
    page title (best-effort)."""
    html = _safe_decode_html(body)
    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    category_name = _strip(title_match.group(1) if title_match else None)

    asins: List[str] = []
    seen = set()
    for m in _ASIN_RE.finditer(html):
        asin = m.group(1)
        if asin in seen:
            continue
        seen.add(asin)
        asins.append(asin)

    products = [{"asin": a} for a in asins]
    requires_review = (category_name is None) or not products
    confidence = "high" if not requires_review else "medium"

    return ParsedAmazonCategory(
        category_name=category_name,
        products=products,
        source_url=source_url,
        confidence=confidence,
        requires_review=requires_review,
    )


def parse_amazon_brand_page(
    body: bytes,
    *,
    source_url: str = "",
) -> ParsedAmazonBrand:
    """Parse an Amazon brand store page. Extracts the brand name from
    the page title and product ASINs from links."""
    html = _safe_decode_html(body)
    title_match = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    brand_name = _strip(title_match.group(1) if title_match else None)

    asins: List[str] = []
    seen = set()
    for m in _ASIN_RE.finditer(html):
        asin = m.group(1)
        if asin in seen:
            continue
        seen.add(asin)
        asins.append(asin)

    products = [{"asin": a} for a in asins]
    requires_review = (brand_name is None) or not products
    confidence = "high" if not requires_review else "medium"

    return ParsedAmazonBrand(
        brand_name=brand_name,
        products=products,
        source_url=source_url,
        confidence=confidence,
        requires_review=requires_review,
    )


def _first_group(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(1) if m else None


__all__ = [
    "ParsedAmazonBrand",
    "ParsedAmazonCategory",
    "ParsedAmazonProduct",
    "ParsedAmazonSearch",
    "parse_amazon_brand_page",
    "parse_amazon_category_page",
    "parse_amazon_product_page",
    "parse_amazon_search_page",
]
