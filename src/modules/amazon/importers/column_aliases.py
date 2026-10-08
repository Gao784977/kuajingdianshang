"""Column alias mapping for the V3.1 Excel import layer.

Seller Sprite / Brand Analytics Excel files often use mixed Chinese and
English column names with arbitrary spacing, capitalisation and unit
suffixes (``"FBA($)"``, ``"FBA费用"``, ``"FBA Fee"``). This module
normalises those raw headers into a single canonical field name space so
the downstream loaders can build typed records without hard-coding every
spelling.

Public surface:

* :data:`STANDARD_FIELDS` — canonical field name -> list of aliases
  (always including the canonical name itself).
* :func:`normalize_header` — strip / lower / collapse whitespace /
  drop common unit suffixes so ``"FBA($)"`` matches ``"fbafee"``.
* :func:`build_column_mapping` — turn a list of raw headers into a
  :class:`ColumnMappingResult` describing which column maps to which
  canonical field, with mapping method and confidence.
* :data:`REQUIRED_FIELDS_BY_TYPE` and :data:`OPTIONAL_FIELDS_BY_TYPE` —
  drive the ``required_missing`` / ``optional_missing`` lists in the
  mapping result.

The module imports stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Canonical field alias table
# ---------------------------------------------------------------------------

STANDARD_FIELDS: Dict[str, List[str]] = {
    # Product identifiers
    "asin": [
        "asin", "ASIN", "Asin", "商品ASIN", "ASIN码", "产品ASIN",
        "Product ASIN", "ASIN Code",
    ],
    "sku": [
        "sku", "SKU", "Seller SKU", "商家SKU", "店铺SKU", "SKU码",
    ],
    "parent_asin": [
        "parent_asin", "Parent ASIN", "父ASIN", "ParentASIN",
        "父商品ASIN", "Parent Item ASIN",
    ],
    # Brand
    "brand": [
        "brand", "Brand", "品牌", "品牌名", "品牌名称",
        "Brand Name", "Manufacturer",
    ],
    "brand_link": [
        "brand_link", "Brand Link", "品牌链接", "Brand URL",
        "品牌URL", "Brand Store URL",
    ],
    # Listing text
    "title": [
        "title", "Title", "标题", "商品标题", "产品标题",
        "Product Title", "Item Title", "Name",
    ],
    "bullet_points": [
        "bullet_points", "Bullet Points", "Bullet Point", "Bullets",
        "卖点", "五点描述", "商品卖点", "Feature Bullets",
    ],
    "product_url": [
        "product_url", "URL", "Product URL", "商品链接",
        "Listing URL", "链接", "产品URL", "Detail Page URL",
    ],
    "main_image_url": [
        "main_image_url", "Image", "Main Image", "主图",
        "主图URL", "Image URL", "Main Image URL", "图片",
    ],
    # Categories
    "category_path": [
        "category_path", "Category Path", "类目路径", "分类路径",
        "Category Tree", "Browse Path",
    ],
    "category": [
        "category", "Category", "类目", "分类", "Category Name",
        "Subcategory Path", "类目名",
    ],
    "main_category": [
        "main_category", "Main Category", "主类目", "一级类目",
        "Top Category", "Root Category",
    ],
    "subcategory": [
        "subcategory", "Subcategory", "子类目", "次级类目",
        "Sub Category", "Child Category",
    ],
    # BSR
    "main_bsr": [
        "main_bsr", "Main BSR", "Main BSR Rank", "主BSR",
        "大类目BSR", "Main Category Rank", "Main Best Seller Rank",
    ],
    "subcategory_bsr": [
        "subcategory_bsr", "Subcategory BSR", "Sub BSR", "子类目BSR",
        "Subcategory Rank", "Small BSR", "次级类目BSR",
    ],
    # Sales / revenue
    "monthly_sales": [
        "monthly_sales", "月销量", "月销售量", "近30天销量",
        "Monthly Sales", "Sales per Month", "Estimated Monthly Sales",
        "30天销量", "月销",
    ],
    "monthly_sales_growth": [
        "monthly_sales_growth", "月销量增长", "月增长", "Monthly Growth",
        "Sales Growth", "MoM Growth", "月销量增长率",
    ],
    "monthly_revenue": [
        "monthly_revenue", "月销售额($)", "月销售额", "Monthly Revenue",
        "Monthly Sales Revenue", "月收入", "30天销售额",
    ],
    "child_sales": [
        "child_sales", "Child Sales", "子商品销量", "变体销量",
        "Variant Sales", "Children Sales",
    ],
    "child_revenue": [
        "child_revenue", "Child Revenue", "子商品销售额", "变体销售额",
        "Variant Revenue", "Children Revenue",
    ],
    "variation_count": [
        "variation_count", "Variation Count", "变体数", "子体数量",
        "Number of Variations", "Variants",
    ],
    # Price
    "price": [
        "price", "Price", "价格", "售价", "Current Price",
        "Listing Price", "商品价格",
    ],
    "prime_price": [
        "prime_price", "Prime Price", "Prime专享价", "会员价",
        "Prime Exclusive Price", "Prime Deal Price",
    ],
    "coupon": [
        "coupon", "Coupon", "优惠券", "折扣", "Coupon Value",
        "Coupon Amount", "Discount",
    ],
    # Reviews / Q&A
    "qa_count": [
        "qa_count", "Q&A Count", "QA Count", "问答数",
        "Question Count", "Q&A", "问答数量",
    ],
    "review_count": [
        "review_count", "评分数", "Review数量", "Reviews",
        "Review Count", "Number of Reviews", "评论数",
    ],
    "monthly_new_reviews": [
        "monthly_new_reviews", "月新增评论", "月新评论数",
        "Monthly New Reviews", "New Reviews (30d)", "30天新增评论",
    ],
    "rating": [
        "rating", "评分", "星级", "Rating", "Star Rating",
        "Stars", "Average Rating",
    ],
    "review_rate": [
        "review_rate", "Review Rate", "评论率", "Review Growth Rate",
        "Monthly Review Rate", "月评论率",
    ],
    # Fees / margin
    "fba_fee": [
        "fba_fee", "FBA($)", "FBA费用", "FBA Fee", "Fulfillment Fee",
        "FBA Cost", "FBA运费",
    ],
    "margin_rate": [
        "margin_rate", "Margin Rate", "毛利率", "Margin",
        "Profit Margin", "Gross Margin",
    ],
    # Listing lifecycle
    "launch_date": [
        "launch_date", "Launch Date", "上架时间", "上架日期",
        "First Available", "Release Date", "Date First Available",
    ],
    "listing_age_days": [
        "listing_age_days", "Listing Age (days)", "Listing Age",
        "上架天数", "Product Age", "Days Listed",
    ],
    "fulfillment_method": [
        "fulfillment_method", "Fulfillment", "Fulfillment Channel",
        "FBA/FBM", "发货方式", "Fulfillment Method", "配送方式",
    ],
    # Sellers
    "sellers_count": [
        "sellers_count", "Sellers Count", "Seller Count", "卖家数",
        "Number of Sellers", "Sellers", "卖家数量",
    ],
    "buybox_seller": [
        "buybox_seller", "Buy Box Seller", "BuyBox Seller", "购物车卖家",
        "Buy Box Owner", "当前卖家", "BuyBox Owner",
    ],
    "seller": [
        "seller", "Seller", "卖家", "卖家名称", "Seller Name",
        "Shop Name", "店铺", "店铺名称", "Merchant", "Storefront",
    ],
    "seller_id": [
        "seller_id", "Seller ID", "卖家ID", "SellerId", "Merchant ID",
        "Store ID", "店铺ID",
    ],
    "seller_link": [
        "seller_link", "Seller Link", "卖家链接", "Seller URL",
        "Store URL", "店铺链接", "Seller Profile URL",
    ],
    "seller_location": [
        "seller_location", "Seller Location", "卖家所在地",
        "Ship From", "Seller Country", "卖家国家",
    ],
    # Physical attributes
    "weight": [
        "weight", "Weight", "重量", "Item Weight", "产品重量",
        "Package Weight (lbs)",
    ],
    "dimensions": [
        "dimensions", "Dimensions", "尺寸", "Item Dimensions",
        "Product Size", "产品尺寸",
    ],
    "package_weight": [
        "package_weight", "Package Weight", "包裹重量", "包装重量",
        "Shipping Weight", "Shipped Weight",
    ],
    "package_dimensions": [
        "package_dimensions", "Package Dimensions", "包裹尺寸",
        "包装尺寸", "Package Size", "Box Dimensions",
    ],
    # Search appearance
    "search_rank": [
        "search_rank", "Search Rank", "搜索排名", "Natural Rank",
        "Organic Rank", "Rank", "排名",
    ],
    "placement_type": [
        "placement_type", "Placement", "Placement Type", "展示位置",
        "Ad Placement", "展示位置类型",
    ],
    "placement_detail": [
        "placement_detail", "Placement Detail", "展示详情",
        "Placement Info", "Ad Position Detail",
    ],
    "is_sponsored": [
        "is_sponsored", "Sponsored", "Is Sponsored", "是否广告",
        "Ad", "Paid Placement", "是否赞助",
    ],
    "is_organic": [
        "is_organic", "Organic", "Is Organic", "自然位",
        "Natural Placement", "是否自然",
    ],
    "page_number": [
        "page_number", "Page", "Page Number", "页码",
        "Page No.", "Search Page",
    ],
    "keyword": [
        "keyword", "Keyword", "关键词", "搜索词", "Search Term",
        "Search Keyword", "Key Word",
    ],
    # Keyword metrics
    "search_volume": [
        "search_volume", "Search Volume", "搜索量", "搜索热度",
        "Monthly Searches", "Search Count", "搜索次数",
    ],
    "search_growth": [
        "search_growth", "Search Growth", "搜索增长", "搜索量增长",
        "Search Volume Growth", "Trend", "搜索趋势",
    ],
    "click_share": [
        "click_share", "Click Share", "点击份额", "点击占比",
        "Click Distribution", "Click Percentage",
    ],
    "conversion_share": [
        "conversion_share", "Conversion Share", "转化份额",
        "转化占比", "Conversion Distribution", "Conversion Percentage",
    ],
    "competition": [
        "competition", "Competition", "竞争度", "竞争指数",
        "Competition Level", "Competition Index",
    ],
    "related_keywords": [
        "related_keywords", "Related Keywords", "相关关键词",
        "Similar Keywords", "关联词", "Related Terms",
    ],
    # Market / category aggregates
    "product_count": [
        "product_count", "Product Count", "商品数", "产品数量",
        "Number of Products", "Listing Count", "ASIN Count",
    ],
    "market_sales": [
        "market_sales", "Market Sales", "市场销量", "类目销量",
        "Total Sales", "Category Sales",
    ],
    "market_revenue": [
        "market_revenue", "Market Revenue", "市场销售额", "类目销售额",
        "Total Revenue", "Category Revenue",
    ],
    "average_price": [
        "average_price", "Average Price", "均价", "平均价格",
        "Avg Price", "Mean Price",
    ],
    "median_price": [
        "median_price", "Median Price", "中位价", "中位数价格",
        "Middle Price", "Med Price",
    ],
    "growth": [
        "growth", "Growth", "增长率", "增长", "Growth Rate",
        "Category Growth",
    ],
    "annual_sales": [
        "annual_sales", "Annual Sales", "年销量", "年度销量",
        "Yearly Sales", "Year Sales",
    ],
    "annual_revenue": [
        "annual_revenue", "Annual Revenue", "年销售额", "年度销售额",
        "Yearly Revenue", "Year Revenue",
    ],
    "market_share": [
        "market_share", "Market Share", "市场份额", "市占率",
        "Share", "Brand Share",
    ],
}


# ---------------------------------------------------------------------------
# Required / optional fields per file type
# ---------------------------------------------------------------------------

REQUIRED_FIELDS_BY_TYPE: Dict[str, List[str]] = {
    "products": ["asin", "title", "price"],
    "search": ["keyword", "asin"],
    "keyword": ["keyword"],
    "market": ["category", "market_sales", "market_revenue"],
    "category": ["category", "product_count", "average_price"],
    "brand_analytics": ["brand", "market_share"],
    "brands": ["brand", "monthly_sales", "monthly_revenue"],
    "sellers": ["seller", "monthly_sales", "monthly_revenue"],
}

OPTIONAL_FIELDS_BY_TYPE: Dict[str, List[str]] = {
    "products": [
        "sku", "parent_asin", "brand", "main_image_url", "category",
        "main_category", "subcategory", "main_bsr", "subcategory_bsr",
        "monthly_sales", "monthly_revenue", "review_count", "rating",
        "fba_fee", "fulfillment_method",
    ],
    "search": [
        "search_rank", "placement_type", "is_sponsored", "page_number",
        "brand", "title", "price",
    ],
    "keyword": [
        "search_volume", "search_growth", "click_share", "conversion_share",
        "competition", "related_keywords",
    ],
    "market": [
        "product_count", "average_price", "median_price", "growth",
        "category_path",
    ],
    "category": [
        "category_path", "market_sales", "market_revenue", "median_price",
        "growth", "competition",
    ],
    "brand_analytics": [
        "click_share", "conversion_share", "monthly_sales", "monthly_revenue",
    ],
    "brands": [
        "annual_sales", "annual_revenue", "average_price", "market_share",
    ],
    "sellers": [
        "annual_sales", "annual_revenue", "average_price", "market_share",
    ],
}


# ---------------------------------------------------------------------------
# Header normalisation
# ---------------------------------------------------------------------------

# Unit suffixes commonly appended to header names. Strip these before
# matching, but never strip a bare unit (e.g. header == "$").
_UNIT_SUFFIXES: Tuple[str, ...] = (
    "($)", "($/unit)", "(%)", "(usd)", "(rmb)", "(￥)", "(¥)",
    "（$）", "（%）", "（￥）", "（¥）",
)

# Punctuation / whitespace characters to drop entirely.
_DROP_CHARS_PATTERN = re.compile(r"[\s\-_·•・\n\r\t]+")
# Parenthesised unit suffixes such as "(lbs)", "(kg)", "(in)", "(cm)".
# Both ASCII ``(...)`` and full-width ``（...）`` forms are stripped.
_PAREN_UNIT_PATTERN = re.compile(r"[\(（][^)）]*[\)）]")


def normalize_header(raw: str) -> str:
    """Normalise a raw header string for alias matching.

    Steps (each idempotent):

    1. Trim and unicode-normalise.
    2. Drop parenthesised unit suffixes such as ``"(lbs)"`` or
       ``"(USD)"``.
    3. Drop trailing unit tokens such as ``"($)"`` or ``"(%)`` (both
       ASCII and full-width variants).
    4. Lower-case.
    5. Remove whitespace, hyphens, underscores and bullet characters.

    The resulting token is what gets compared against
    :func:`normalize_header` of every alias in :data:`STANDARD_FIELDS`.

    Examples:
        >>> normalize_header("FBA($)")
        'fba'
        >>> normalize_header("Monthly  Sales")
        'monthlysales'
        >>> normalize_header("月 销\n量")
        '月销量'
    """
    if raw is None:
        return ""
    text = str(raw).strip()
    if not text:
        return ""
    # Strip parenthesised units.
    text = _PAREN_UNIT_PATTERN.sub("", text)
    # Strip trailing standalone unit suffixes.
    for suffix in _UNIT_SUFFIXES:
        if text.endswith(suffix):
            text = text[: -len(suffix)].rstrip()
    text = text.strip()
    # Lower-case.
    text = text.lower()
    # Drop whitespace / hyphens / underscores / bullets.
    text = _DROP_CHARS_PATTERN.sub("", text)
    return text


# Pre-compute normalised alias index for fast lookup.
_NORMALISED_ALIAS_INDEX: Dict[str, str] = {}


def _build_alias_index() -> None:
    """Populate :data:`_NORMALISED_ALIAS_INDEX` once."""
    if _NORMALISED_ALIAS_INDEX:
        return
    for std_field, aliases in STANDARD_FIELDS.items():
        for alias in aliases:
            key = normalize_header(alias)
            # First-seen-wins so the canonical name (which is listed
            # first) takes precedence when two fields share an alias.
            if key not in _NORMALISED_ALIAS_INDEX:
                _NORMALISED_ALIAS_INDEX[key] = std_field


# ---------------------------------------------------------------------------
# Fuzzy matching helpers
# ---------------------------------------------------------------------------


def _fuzzy_similarity(a: str, b: str) -> float:
    """Cheap character-trigram Jaccard similarity in [0.0, 1.0].

    Good enough for short header strings without pulling in a heavy
    dependency; the loader only uses fuzzy matches when no exact / alias
    match exists and always tags them ``confidence="low"``.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if len(a) < 3 or len(b) < 3:
        # Fall back to character-level containment for very short tokens.
        if a in b or b in a:
            return 0.6
        return 0.0
    a_trigrams = {a[i : i + 3] for i in range(len(a) - 2)}
    b_trigrams = {b[i : i + 3] for i in range(len(b) - 2)}
    if not a_trigrams or not b_trigrams:
        return 0.0
    intersection = len(a_trigrams & b_trigrams)
    union = len(a_trigrams | b_trigrams)
    return intersection / union if union else 0.0


_FUZZY_THRESHOLD = 0.65


# ---------------------------------------------------------------------------
# Mapping result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ColumnMapping:
    """A single raw-header -> standard-field assignment."""

    original_header: str
    standard_field: str
    mapping_method: str  # "exact" | "alias" | "fuzzy"
    confidence: str  # "high" | "medium" | "low"
    original_position: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "original_header": self.original_header,
            "standard_field": self.standard_field,
            "mapping_method": self.mapping_method,
            "confidence": self.confidence,
            "original_position": self.original_position,
        }


@dataclass
class ColumnMappingResult:
    """Full mapping report for one sheet."""

    mappings: List[ColumnMapping] = field(default_factory=list)
    unmapped_columns: List[str] = field(default_factory=list)
    required_missing: List[str] = field(default_factory=list)
    optional_missing: List[str] = field(default_factory=list)
    mapping_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "mappings": [m.to_dict() for m in self.mappings],
            "unmapped_columns": list(self.unmapped_columns),
            "required_missing": list(self.required_missing),
            "optional_missing": list(self.optional_missing),
            "mapping_warnings": list(self.mapping_warnings),
        }

    @property
    def field_to_column(self) -> Dict[str, str]:
        """Convenience: standard_field -> original_header."""
        return {m.standard_field: m.original_header for m in self.mappings}

    @property
    def column_to_field(self) -> Dict[str, str]:
        """Convenience: original_header -> standard_field."""
        return {m.original_header: m.standard_field for m in self.mappings}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def build_column_mapping(
    headers: List[str],
    file_type: str,
) -> ColumnMappingResult:
    """Map raw headers to standard fields.

    Args:
        headers: Raw header strings (any case, any whitespace, any
            language). Empty / None entries are skipped.
        file_type: One of the keys of
            :data:`REQUIRED_FIELDS_BY_TYPE` (or ``"unknown"``). Drives
            required / optional field detection.

    Returns:
        A :class:`ColumnMappingResult`. Mappings are returned in the
        same order as ``headers``; unmapped columns are kept in
        ``unmapped_columns`` (NOT dropped). Required fields absent from
        the headers are reported in ``required_missing``.
    """
    _build_alias_index()
    result = ColumnMappingResult()
    used_fields: set[str] = set()
    seen_normalised: Dict[str, int] = {}

    for idx, raw in enumerate(headers):
        if raw is None or not str(raw).strip():
            continue
        norm = normalize_header(raw)
        if not norm:
            continue
        if norm in seen_normalised:
            # Duplicate column — record as warning and skip.
            result.mapping_warnings.append(
                f"Duplicate header '{raw}' (position {idx}) skipped; "
                f"first seen at position {seen_normalised[norm]}."
            )
            continue
        seen_normalised[norm] = idx

        # 1) Exact canonical-name match (case/space-insensitive).
        std_field_exact: Optional[str] = None
        for std_field_name in STANDARD_FIELDS:
            if normalize_header(std_field_name) == norm:
                std_field_exact = std_field_name
                break
        if std_field_exact and std_field_exact not in used_fields:
            result.mappings.append(
                ColumnMapping(
                    original_header=str(raw).strip(),
                    standard_field=std_field_exact,
                    mapping_method="exact",
                    confidence="high",
                    original_position=idx,
                )
            )
            used_fields.add(std_field_exact)
            continue

        # 2) Alias match.
        std_field = _NORMALISED_ALIAS_INDEX.get(norm)
        if std_field and std_field not in used_fields:
            result.mappings.append(
                ColumnMapping(
                    original_header=str(raw).strip(),
                    standard_field=std_field,
                    mapping_method="alias",
                    confidence="high",
                    original_position=idx,
                )
            )
            used_fields.add(std_field)
            continue

        # 3) Fuzzy match against every alias (slow but headers are short).
        best_field: Optional[str] = None
        best_score: float = 0.0
        for std_field_name, aliases in STANDARD_FIELDS.items():
            if std_field_name in used_fields:
                continue
            for alias in aliases:
                score = _fuzzy_similarity(norm, normalize_header(alias))
                if score > best_score:
                    best_score = score
                    best_field = std_field_name
        if best_field is not None and best_score >= _FUZZY_THRESHOLD:
            result.mappings.append(
                ColumnMapping(
                    original_header=str(raw).strip(),
                    standard_field=best_field,
                    mapping_method="fuzzy",
                    confidence="low",
                    original_position=idx,
                )
            )
            used_fields.add(best_field)
            result.mapping_warnings.append(
                f"Fuzzy-matched header '{raw}' -> '{best_field}' "
                f"(similarity={best_score:.2f})."
            )
            continue

        # 4) Unmapped.
        result.unmapped_columns.append(str(raw).strip())

    # Required / optional missing.
    required = REQUIRED_FIELDS_BY_TYPE.get(file_type, [])
    optional = OPTIONAL_FIELDS_BY_TYPE.get(file_type, [])
    result.required_missing = [f for f in required if f not in used_fields]
    result.optional_missing = [f for f in optional if f not in used_fields]

    if result.required_missing:
        result.mapping_warnings.append(
            "Missing required fields: " + ", ".join(result.required_missing)
        )
    if result.unmapped_columns:
        result.mapping_warnings.append(
            f"{len(result.unmapped_columns)} unmapped column(s) kept as-is."
        )
    return result
