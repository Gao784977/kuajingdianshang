"""V3.1.3 — multi-axis analysis layer.

Sits above the V3.1.1 loaders and V3.1.2 normaliser. Each analyzer
consumes typed records (``KeywordMetric``, ``CategoryMetric``,
``BrandMetric``, ``SellerMetric``, ``AmazonSearchAppearance``,
``AmazonProduct``) and emits a structured result with source
traceability (``source_files`` list, ``requires_review`` flag).

Public entry points:

* :func:`analyze_keywords`           — multi-keyword ranking + opportunity score
* :func:`analyze_categories`         — cross-category comparison
* :func:`analyze_brands`             — brand concentration (CR4/CR8/HHI)
* :func:`analyze_sellers`            — seller concentration + FBA/FBM ratio
* :func:`analyze_search_positions`   — keyword x ASIN matrix, sponsored vs organic

All functions are pure and import stdlib only. No openpyxl dependency.
"""

from __future__ import annotations

from .brand_analysis import BrandAnalysis, analyze_brands
from .multi_category_analyzer import (
    CategoryComparison,
    MultiCategoryAnalysis,
    analyze_categories,
)
from .multi_keyword_analyzer import (
    KeywordRanking,
    MultiKeywordAnalysis,
    analyze_keywords,
)
from .search_position_analysis import (
    SearchPositionAnalysis,
    SearchPositionMatrix,
    analyze_search_positions,
)
from .seller_analysis import SellerAnalysis, analyze_sellers

__all__ = [
    "BrandAnalysis",
    "CategoryComparison",
    "KeywordRanking",
    "MultiCategoryAnalysis",
    "MultiKeywordAnalysis",
    "SearchPositionAnalysis",
    "SearchPositionMatrix",
    "SellerAnalysis",
    "analyze_brands",
    "analyze_categories",
    "analyze_keywords",
    "analyze_search_positions",
    "analyze_sellers",
]
