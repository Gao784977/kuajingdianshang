"""Normalised, source-traceable data models for the V3.1 Excel import layer.

Each model carries a :class:`SourceInfo` describing where the record
came from (file path, sheet name, 1-based row index, source type), so
downstream agents can distinguish imported Excel data from
mock_data / user_input / fetched_url / calculated values without
inspecting the row contents.

Conventions:

* All money / ratio fields are :class:`decimal.Decimal` (never
  :class:`float`). ``to_dict`` serialises Decimals as ``str`` to keep
  precision round-trippable.
* All structured models inherit from :class:`SourceInfo` so the four
  source fields plus ``source_hash`` are always present.
* :meth:`AmazonProduct.dedup_key` returns the ASIN if present,
  otherwise a synthetic ``brand|title`` key so callers can dedup
  across files without losing track of which file a row came from.

This module imports stdlib only.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional


# Allowed values for ``SourceInfo.source_type``.
ALLOWED_SOURCE_TYPES = (
    "imported_excel",
    "user_input",
    "fetched_url",
    "calculated",
    "agent_inference",
    "mock_data",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Coerce a numeric/string cell to Decimal, returning ``None`` for blanks."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        # str() avoids 1.10000000001 noise.
        return Decimal(str(value))
    s = str(value).strip()
    if not s:
        return None
    # Tolerate thousands separators and a leading currency symbol.
    cleaned = s.replace(",", "").replace("$", "").replace("￥", "").replace("¥", "")
    if cleaned.endswith("%"):
        try:
            return Decimal(cleaned[:-1]) / Decimal("100")
        except Exception:
            return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _to_int(value: Any) -> Optional[int]:
    """Coerce a cell to int, returning ``None`` for blanks/non-numbers."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return int(value)
    s = str(value).strip().replace(",", "")
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return None


def _to_str(value: Any) -> Optional[str]:
    """Coerce a cell to a stripped string, returning ``None`` for blanks."""
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _to_bool(value: Any) -> bool:
    """Coerce a cell to bool. Empty/None/0/'no'/'false' -> False."""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    s = str(value).strip().lower()
    return s not in ("", "0", "no", "n", "false", "f", "否", "false")


def _decimal_to_str(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _list_to_str_list(value: Any) -> List[str]:
    """Coerce a cell to a list[str].

    Accepts lists/tuples directly, or strings split on ``|``, ``;``,
    ``\\n`` (newlines common in Seller Sprite cells).
    """
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value)
    if not s.strip():
        return []
    parts = s.replace("\n", "|").replace(";", "|").split("|")
    return [p.strip() for p in parts if p.strip()]


def _compute_source_hash(*parts: Any) -> str:
    """Stable short hash of source file + sheet + row + identifying fields."""
    payload = "|".join(str(p) for p in parts)
    return hashlib.md5(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# SourceInfo base
# ---------------------------------------------------------------------------


@dataclass
class SourceInfo:
    """Common source-traceability fields mixed into every record."""

    source_file: str = ""
    source_sheet: str = ""
    source_row: int = 0
    source_type: str = "imported_excel"
    source_hash: Optional[str] = None

    def __post_init__(self) -> None:
        if self.source_type not in ALLOWED_SOURCE_TYPES:
            # Be lenient: silently fall back to the default rather than
            # raising, since loader input comes from arbitrary Excel files.
            object.__setattr__(self, "source_type", "imported_excel")
        if not self.source_hash:
            object.__setattr__(
                self,
                "source_hash",
                _compute_source_hash(
                    self.source_file, self.source_sheet, self.source_row
                ),
            )

    def source_to_dict(self) -> Dict[str, Any]:
        return {
            "source_file": self.source_file,
            "source_sheet": self.source_sheet,
            "source_row": self.source_row,
            "source_type": self.source_type,
            "source_hash": self.source_hash,
        }


# ---------------------------------------------------------------------------
# Product
# ---------------------------------------------------------------------------


@dataclass
class AmazonProduct(SourceInfo):
    """A single Amazon product row from a seller sprite / Brand Analytics file."""

    asin: str = ""
    sku: str = ""
    parent_asin: str = ""
    brand: str = ""
    brand_link: str = ""
    title: str = ""
    bullet_points: List[str] = field(default_factory=list)
    product_url: str = ""
    main_image_url: str = ""
    category_path: List[str] = field(default_factory=list)
    category: str = ""
    main_category: str = ""
    subcategory: str = ""
    main_bsr: Optional[int] = None
    subcategory_bsr: Optional[int] = None
    monthly_sales: Optional[Decimal] = None
    monthly_sales_growth: Optional[Decimal] = None
    monthly_revenue: Optional[Decimal] = None
    child_sales: Optional[Decimal] = None
    child_revenue: Optional[Decimal] = None
    variation_count: Optional[int] = None
    price: Optional[Decimal] = None
    prime_price: Optional[Decimal] = None
    coupon: Optional[Decimal] = None
    qa_count: Optional[int] = None
    review_count: Optional[int] = None
    monthly_new_reviews: Optional[int] = None
    rating: Optional[Decimal] = None
    review_rate: Optional[Decimal] = None
    fba_fee: Optional[Decimal] = None
    margin_rate: Optional[Decimal] = None
    launch_date: Optional[str] = None
    listing_age_days: Optional[int] = None
    fulfillment_method: str = ""
    sellers_count: Optional[int] = None
    buybox_seller: str = ""
    seller_location: str = ""
    weight: Optional[Decimal] = None
    dimensions: str = ""
    package_weight: Optional[Decimal] = None
    package_dimensions: str = ""

    def dedup_key(self) -> str:
        """Return ASIN if present, else ``brand|title`` synthetic key."""
        if self.asin:
            return f"asin:{self.asin}"
        brand = self.brand or "?"
        title = self.title or "?"
        return f"bt:{brand}|{title}"

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "asin": self.asin,
            "sku": self.sku,
            "parent_asin": self.parent_asin,
            "brand": self.brand,
            "brand_link": self.brand_link,
            "title": self.title,
            "bullet_points": list(self.bullet_points),
            "product_url": self.product_url,
            "main_image_url": self.main_image_url,
            "category_path": list(self.category_path),
            "category": self.category,
            "main_category": self.main_category,
            "subcategory": self.subcategory,
            "main_bsr": self.main_bsr,
            "subcategory_bsr": self.subcategory_bsr,
            "monthly_sales": _decimal_to_str(self.monthly_sales),
            "monthly_sales_growth": _decimal_to_str(self.monthly_sales_growth),
            "monthly_revenue": _decimal_to_str(self.monthly_revenue),
            "child_sales": _decimal_to_str(self.child_sales),
            "child_revenue": _decimal_to_str(self.child_revenue),
            "variation_count": self.variation_count,
            "price": _decimal_to_str(self.price),
            "prime_price": _decimal_to_str(self.prime_price),
            "coupon": _decimal_to_str(self.coupon),
            "qa_count": self.qa_count,
            "review_count": self.review_count,
            "monthly_new_reviews": self.monthly_new_reviews,
            "rating": _decimal_to_str(self.rating),
            "review_rate": _decimal_to_str(self.review_rate),
            "fba_fee": _decimal_to_str(self.fba_fee),
            "margin_rate": _decimal_to_str(self.margin_rate),
            "launch_date": self.launch_date,
            "listing_age_days": self.listing_age_days,
            "fulfillment_method": self.fulfillment_method,
            "sellers_count": self.sellers_count,
            "buybox_seller": self.buybox_seller,
            "seller_location": self.seller_location,
            "weight": _decimal_to_str(self.weight),
            "dimensions": self.dimensions,
            "package_weight": _decimal_to_str(self.package_weight),
            "package_dimensions": self.package_dimensions,
        }
        out.update(self.source_to_dict())
        return out


# ---------------------------------------------------------------------------
# Search appearance
# ---------------------------------------------------------------------------


@dataclass
class AmazonSearchAppearance(SourceInfo):
    """A single keyword-ASIN search-appearance row."""

    keyword: str = ""
    asin: str = ""
    search_rank: Optional[int] = None
    placement_type: str = "unknown"
    placement_detail: str = ""
    is_sponsored: bool = False
    is_organic: bool = False
    page_number: Optional[int] = None
    brand: str = ""
    title: str = ""
    price: Optional[Decimal] = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.placement_type not in ("sponsored", "organic", "unknown"):
            object.__setattr__(self, "placement_type", "unknown")

    def dedup_key(self) -> str:
        return f"{self.keyword}|{self.asin}|{self.search_rank}"

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "keyword": self.keyword,
            "asin": self.asin,
            "search_rank": self.search_rank,
            "placement_type": self.placement_type,
            "placement_detail": self.placement_detail,
            "is_sponsored": self.is_sponsored,
            "is_organic": self.is_organic,
            "page_number": self.page_number,
            "brand": self.brand,
            "title": self.title,
            "price": _decimal_to_str(self.price),
        }
        out.update(self.source_to_dict())
        return out


# ---------------------------------------------------------------------------
# Keyword metric
# ---------------------------------------------------------------------------


@dataclass
class KeywordMetric(SourceInfo):
    """A keyword aggregate row."""

    keyword: str = ""
    search_volume: Optional[Decimal] = None
    search_growth: Optional[Decimal] = None
    click_share: Optional[Decimal] = None
    conversion_share: Optional[Decimal] = None
    competition: str = ""
    related_keywords: List[str] = field(default_factory=list)

    def dedup_key(self) -> str:
        return f"kw:{self.keyword}"

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "keyword": self.keyword,
            "search_volume": _decimal_to_str(self.search_volume),
            "search_growth": _decimal_to_str(self.search_growth),
            "click_share": _decimal_to_str(self.click_share),
            "conversion_share": _decimal_to_str(self.conversion_share),
            "competition": self.competition,
            "related_keywords": list(self.related_keywords),
        }
        out.update(self.source_to_dict())
        return out


# ---------------------------------------------------------------------------
# Category metric
# ---------------------------------------------------------------------------


@dataclass
class CategoryMetric(SourceInfo):
    """A category aggregate row."""

    category: str = ""
    category_path: List[str] = field(default_factory=list)
    product_count: Optional[int] = None
    market_sales: Optional[Decimal] = None
    market_revenue: Optional[Decimal] = None
    average_price: Optional[Decimal] = None
    median_price: Optional[Decimal] = None
    growth: Optional[Decimal] = None
    competition: str = ""

    def dedup_key(self) -> str:
        return f"cat:{self.category}"

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "category": self.category,
            "category_path": list(self.category_path),
            "product_count": self.product_count,
            "market_sales": _decimal_to_str(self.market_sales),
            "market_revenue": _decimal_to_str(self.market_revenue),
            "average_price": _decimal_to_str(self.average_price),
            "median_price": _decimal_to_str(self.median_price),
            "growth": _decimal_to_str(self.growth),
            "competition": self.competition,
        }
        out.update(self.source_to_dict())
        return out


# ---------------------------------------------------------------------------
# Brand metric
# ---------------------------------------------------------------------------


@dataclass
class BrandMetric(SourceInfo):
    """A brand aggregate row."""

    brand: str = ""
    monthly_sales: Optional[Decimal] = None
    monthly_revenue: Optional[Decimal] = None
    annual_sales: Optional[Decimal] = None
    annual_revenue: Optional[Decimal] = None
    average_price: Optional[Decimal] = None
    market_share: Optional[Decimal] = None
    # Brand Analytics signature fields. Absent on the seller-sprite
    # "Brands" export, but always present on Amazon Brand Analytics.
    click_share: Optional[Decimal] = None
    conversion_share: Optional[Decimal] = None

    def dedup_key(self) -> str:
        return f"brand:{self.brand}"

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "brand": self.brand,
            "monthly_sales": _decimal_to_str(self.monthly_sales),
            "monthly_revenue": _decimal_to_str(self.monthly_revenue),
            "annual_sales": _decimal_to_str(self.annual_sales),
            "annual_revenue": _decimal_to_str(self.annual_revenue),
            "average_price": _decimal_to_str(self.average_price),
            "market_share": _decimal_to_str(self.market_share),
            "click_share": _decimal_to_str(self.click_share),
            "conversion_share": _decimal_to_str(self.conversion_share),
        }
        out.update(self.source_to_dict())
        return out


# ---------------------------------------------------------------------------
# Seller metric
# ---------------------------------------------------------------------------


@dataclass
class SellerMetric(SourceInfo):
    """A seller aggregate row."""

    seller: str = ""
    monthly_sales: Optional[Decimal] = None
    monthly_revenue: Optional[Decimal] = None
    annual_sales: Optional[Decimal] = None
    annual_revenue: Optional[Decimal] = None
    average_price: Optional[Decimal] = None
    market_share: Optional[Decimal] = None

    def dedup_key(self) -> str:
        return f"seller:{self.seller}"

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "seller": self.seller,
            "monthly_sales": _decimal_to_str(self.monthly_sales),
            "monthly_revenue": _decimal_to_str(self.monthly_revenue),
            "annual_sales": _decimal_to_str(self.annual_sales),
            "annual_revenue": _decimal_to_str(self.annual_revenue),
            "average_price": _decimal_to_str(self.average_price),
            "market_share": _decimal_to_str(self.market_share),
        }
        out.update(self.source_to_dict())
        return out


# ---------------------------------------------------------------------------
# Conversion helpers used by the loaders
# ---------------------------------------------------------------------------


def to_decimal(value: Any) -> Optional[Decimal]:
    """Public alias for :func:`_to_decimal` (used by the loader modules)."""
    return _to_decimal(value)


def to_int(value: Any) -> Optional[int]:
    """Public alias for :func:`_to_int`."""
    return _to_int(value)


def to_str(value: Any) -> Optional[str]:
    """Public alias for :func:`_to_str`."""
    return _to_str(value)


def to_bool(value: Any) -> bool:
    """Public alias for :func:`_to_bool`."""
    return _to_bool(value)


def to_str_list(value: Any) -> List[str]:
    """Public alias for :func:`_list_to_str_list`."""
    return _list_to_str_list(value)


__all__ = [
    "ALLOWED_SOURCE_TYPES",
    "SourceInfo",
    "AmazonProduct",
    "AmazonSearchAppearance",
    "KeywordMetric",
    "CategoryMetric",
    "BrandMetric",
    "SellerMetric",
    "to_decimal",
    "to_int",
    "to_str",
    "to_bool",
    "to_str_list",
]
