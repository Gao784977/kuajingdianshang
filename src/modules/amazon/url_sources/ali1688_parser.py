"""1688 product page parser — extract product fields from raw HTML.

Like :mod:`amazon_parser`, this module is defensive: it returns only
fields actually present in the HTML and never fabricates values.
1688 product pages embed data in ``window.runParams`` JSON blobs and
``<meta>`` tags; we extract from both.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class ParsedAli1688Product:
    """Fields extracted from a 1688 product detail page."""

    offer_id: Optional[str] = None
    title: Optional[str] = None
    price: Optional[str] = None
    moq: Optional[str] = None
    supplier: Optional[str] = None
    image_url: Optional[str] = None
    source_url: str = ""
    source_type: str = "fetched_url"
    confidence: str = "medium"
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "offer_id": self.offer_id,
            "title": self.title,
            "price": self.price,
            "moq": self.moq,
            "supplier": self.supplier,
            "image_url": self.image_url,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "confidence": self.confidence,
            "requires_review": self.requires_review,
        }


_OFFER_ID_RE = re.compile(r"/offer/(\d+)\.html")
_TITLE_META_RE = re.compile(
    r'<meta\s+name="keywords"[^>]*content="([^"]+)"',
    re.IGNORECASE,
)
_TITLE_TAG_RE = re.compile(r"<title[^>]*>([^<]+)</title>", re.IGNORECASE)
_PRICE_RE = re.compile(
    r'"unitPrice"\s*:\s*"([^"]+)"',
    re.IGNORECASE,
)
_MOQ_RE = re.compile(
    r'"beginAmount"\s*:\s*"?(\d+)"?',
    re.IGNORECASE,
)
_SUPPLIER_RE = re.compile(
    r'"companyName"\s*:\s*"([^"]+)"',
    re.IGNORECASE,
)
_IMAGE_RE = re.compile(
    r'"image"\s*:\s*"(https?://[^"]+)"',
    re.IGNORECASE,
)


def _safe_decode_html(body: bytes) -> str:
    """Decode HTML bytes to text, trying utf-8 first then latin-1."""
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return body.decode(encoding, errors="replace")
        except Exception:
            continue
    return body.decode("utf-8", errors="replace")


def _strip(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    s = s.strip()
    return s or None


def parse_ali1688_product_page(
    body: bytes,
    *,
    source_url: str = "",
) -> ParsedAli1688Product:
    """Parse a 1688 product detail page.

    Returns a :class:`ParsedAli1688Product` with whatever fields the
    regexes matched. ``requires_review`` is True when the offer_id
    or title is missing.
    """
    html = _safe_decode_html(body)
    offer_id_match = _OFFER_ID_RE.search(source_url) if source_url else None
    offer_id = offer_id_match.group(1) if offer_id_match else None

    title = _strip(_first_group(_TITLE_META_RE, html)) or _strip(
        _first_group(_TITLE_TAG_RE, html)
    )
    price = _strip(_first_group(_PRICE_RE, html))
    moq = _strip(_first_group(_MOQ_RE, html))
    supplier = _strip(_first_group(_SUPPLIER_RE, html))
    image_url = _strip(_first_group(_IMAGE_RE, html))

    requires_review = (offer_id is None) or (title is None)
    confidence = "high" if not requires_review else "medium"

    return ParsedAli1688Product(
        offer_id=offer_id,
        title=title,
        price=price,
        moq=moq,
        supplier=supplier,
        image_url=image_url,
        source_url=source_url,
        confidence=confidence,
        requires_review=requires_review,
    )


def _first_group(pattern: re.Pattern, text: str) -> Optional[str]:
    m = pattern.search(text)
    return m.group(1) if m else None


__all__ = ["ParsedAli1688Product", "parse_ali1688_product_page"]
