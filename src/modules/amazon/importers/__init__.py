"""V3.1 Amazon Excel import layer.

Public entry points:

* :func:`detect_workbook` — identify the type of an arbitrary .xlsx
  file (products / search / keyword / market / category /
  brand_analytics / brands / sellers / unknown).
* :func:`build_column_mapping` — normalise raw headers (Chinese,
  English, mixed) into canonical standard fields with mapping
  method and confidence.
* Per-type loaders (:func:`product_loader.load`,
  :func:`search_loader.load`, ...) — read an .xlsx file and return
  typed :class:`LoaderResult` records with full source traceability.
"""

from __future__ import annotations

from .column_aliases import (
    OPTIONAL_FIELDS_BY_TYPE,
    REQUIRED_FIELDS_BY_TYPE,
    STANDARD_FIELDS,
    ColumnMapping,
    ColumnMappingResult,
    build_column_mapping,
    normalize_header,
)
from .normalized_models import (
    ALLOWED_SOURCE_TYPES,
    AmazonProduct,
    AmazonSearchAppearance,
    BrandMetric,
    CategoryMetric,
    KeywordMetric,
    SellerMetric,
    SourceInfo,
    to_bool,
    to_decimal,
    to_int,
    to_str,
    to_str_list,
)
from .normalizer import (
    DuplicateGroup,
    MergedField,
    NormalizedProductResult,
    NormalizedSearchResult,
    ParentChildRelation,
    SOURCE_PRIORITY,
    dedup_by_key,
    default_confidence,
    merge_by_source_priority,
    normalize_products,
    normalize_search_appearances,
    source_priority,
)
from .workbook_detector import (
    SUPPORTED_TYPES,
    SheetInfo,
    WorkbookDetectionResult,
    detect_workbook,
)

# Per-type loaders. Imported lazily would also work, but every loader
# imports openpyxl lazily inside its own ``load`` function, so merely
# importing the module here is cheap (no openpyxl dependency at
# import time).
from . import (  # noqa: F401  re-export for callers
    brand_analytics_loader,
    brand_loader,
    category_loader,
    keyword_loader,
    market_loader,
    product_loader,
    search_loader,
    seller_loader,
)


def get_loader(file_type: str):
    """Return the loader module for ``file_type`` or ``None``."""
    mapping = {
        "products": product_loader,
        "search": search_loader,
        "keyword": keyword_loader,
        "market": market_loader,
        "category": category_loader,
        "brand_analytics": brand_analytics_loader,
        "brands": brand_loader,
        "sellers": seller_loader,
    }
    return mapping.get(file_type)


__all__ = [
    "ALLOWED_SOURCE_TYPES",
    "AmazonProduct",
    "AmazonSearchAppearance",
    "BrandMetric",
    "CategoryMetric",
    "ColumnMapping",
    "ColumnMappingResult",
    "DuplicateGroup",
    "KeywordMetric",
    "MergedField",
    "NormalizedProductResult",
    "NormalizedSearchResult",
    "OPTIONAL_FIELDS_BY_TYPE",
    "ParentChildRelation",
    "REQUIRED_FIELDS_BY_TYPE",
    "SOURCE_PRIORITY",
    "SellerMetric",
    "SheetInfo",
    "SourceInfo",
    "STANDARD_FIELDS",
    "SUPPORTED_TYPES",
    "WorkbookDetectionResult",
    "brand_analytics_loader",
    "brand_loader",
    "build_column_mapping",
    "category_loader",
    "dedup_by_key",
    "default_confidence",
    "detect_workbook",
    "get_loader",
    "keyword_loader",
    "market_loader",
    "merge_by_source_priority",
    "normalize_header",
    "normalize_products",
    "normalize_search_appearances",
    "product_loader",
    "search_loader",
    "seller_loader",
    "source_priority",
    "to_bool",
    "to_decimal",
    "to_int",
    "to_str",
    "to_str_list",
]
