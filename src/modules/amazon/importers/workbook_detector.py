"""Detect the file type of an Amazon Excel workbook (V3.1 import layer).

A workbook can be one of several shapes — products listing, search-term
appearance, keyword aggregate, market overview, category aggregate,
brand analytics, brands list, sellers list — and each maps to a
different loader. Detection combines four weak signals so a single
misleading cue (e.g. a filename that says "products" but the headers
don't include ASIN) does not misroute the file:

1. filename keywords (:func:`_detect_by_filename`)
2. sheet names (:func:`_detect_by_sheet_names`)
3. header normalisation against :mod:`column_aliases` (:func:`_detect_by_headers`)
4. spot-check on the first few data rows (:func:`_detect_by_data`)

If filename disagrees with headers/sheet names the confidence drops
to ``"low"`` and the type may be ``"unknown"`` so the caller can ask
the user to clarify rather than silently misparse rows.

This module imports stdlib only at module level. ``openpyxl`` is
imported lazily inside :func:`detect_workbook` so importing this
module does not require the optional dependency.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .column_aliases import (
    OPTIONAL_FIELDS_BY_TYPE,
    REQUIRED_FIELDS_BY_TYPE,
    STANDARD_FIELDS,
    build_column_mapping,
    normalize_header,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SUPPORTED_TYPES: Tuple[str, ...] = (
    "products",
    "search",
    "keyword",
    "market",
    "category",
    "brand_analytics",
    "brands",
    "sellers",
    "unknown",
)


# Header field requirements used by header-based detection. Each entry
# is (file_type, required_header_fields, optional_header_fields). When
# all ``required_header_fields`` match the detected headers AND at
# least one of ``optional_header_fields`` is also present, the file is
# recognised at ``high`` confidence.
#
# Ordering rule: more specific types (longer required list) come first
# so that a brands file (brand + monthly_sales + monthly_revenue) is
# not misrouted to brand_analytics (which only requires brand) and a
# search file (keyword + asin) is not misrouted to products (asin +
# title + price). The detector walks this list in order and returns
# the first high-confidence match.
_HEADER_REQUIREMENTS: List[Tuple[str, List[str], List[str]]] = [
    (
        "brand_analytics",
        ["brand"],
        # click_share / conversion_share are BA-only signature fields;
        # market_share alone is NOT enough because the brands export
        # also carries it.
        ["click_share", "conversion_share"],
    ),
    (
        "sellers",
        ["seller", "monthly_sales", "monthly_revenue"],
        ["annual_sales", "annual_revenue", "market_share"],
    ),
    (
        "brands",
        ["brand", "monthly_sales", "monthly_revenue"],
        ["annual_sales", "annual_revenue", "market_share"],
    ),
    (
        "search",
        ["keyword", "asin"],
        ["search_rank", "placement_type", "page_number", "is_sponsored"],
    ),
    (
        "keyword",
        ["keyword", "search_volume"],
        ["click_share", "conversion_share", "search_growth", "competition"],
    ),
    (
        "market",
        ["category", "market_sales", "market_revenue"],
        ["product_count", "average_price", "growth"],
    ),
    (
        "category",
        ["category", "product_count", "average_price"],
        ["market_sales", "market_revenue", "median_price", "growth"],
    ),
    (
        "products",
        ["asin", "title", "price"],
        [
            "monthly_sales", "review_count", "rating", "fba_fee",
            "brand", "category", "main_bsr", "fulfillment_method",
        ],
    ),
]


# Filename keyword table (lower-cased substring match).
_FILENAME_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("brand_analytics", ["brand_analytics", "brandanalytics", "品牌分析"]),
    ("brands", ["brands", "brand_list", "品牌列表", "brand-list"]),
    ("sellers", ["sellers", "seller_list", "卖家", "sellers_list"]),
    ("products", ["products", "product_list", "商品", "商品列表", "listings"]),
    ("search", ["search", "搜索词", "search_term", "搜索"]),
    ("keyword", ["keyword", "关键词", "keywords"]),
    ("market", ["market", "市场", "market_analysis"]),
    ("category", ["category", "类目", "categories"]),
]


# Sheet name keyword table.
_SHEET_NAME_KEYWORDS: List[Tuple[str, List[str]]] = [
    ("brand_analytics", ["brand analytics", "brandanalytics", "品牌分析"]),
    ("brands", ["brand", "品牌"]),
    ("sellers", ["seller", "卖家"]),
    ("products", ["product", "商品", "listing"]),
    ("search", ["search", "搜索"]),
    ("keyword", ["keyword", "关键词"]),
    ("market", ["market", "市场"]),
    ("category", ["category", "类目"]),
]


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class SheetInfo:
    """Summary of a single sheet relevant for detection."""

    sheet_name: str
    row_count: int
    col_count: int
    headers: List[str] = field(default_factory=list)
    detected_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sheet_name": self.sheet_name,
            "row_count": self.row_count,
            "col_count": self.col_count,
            "headers": list(self.headers),
            "detected_type": self.detected_type,
        }


@dataclass
class WorkbookDetectionResult:
    """Final detection report for a workbook."""

    file_path: str
    detected_type: str = "unknown"
    confidence: str = "low"
    sheets: List[SheetInfo] = field(default_factory=list)
    recognized_columns: List[str] = field(default_factory=list)
    unmapped_columns: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    detection_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_path": self.file_path,
            "detected_type": self.detected_type,
            "confidence": self.confidence,
            "sheets": [s.to_dict() for s in self.sheets],
            "recognized_columns": list(self.recognized_columns),
            "unmapped_columns": list(self.unmapped_columns),
            "warnings": list(self.warnings),
            "detection_reasons": list(self.detection_reasons),
        }


# ---------------------------------------------------------------------------
# Detection primitives
# ---------------------------------------------------------------------------


def _detect_by_filename(filename: str) -> Tuple[str, str]:
    """Match filename (basename) against known keyword substrings.

    Returns ``(file_type, confidence)`` where confidence is ``"medium"``
    for a hit (filename alone is not enough to be ``high``) or
    ``("unknown", "low")`` for no match.
    """
    if not filename:
        return ("unknown", "low")
    name = os.path.basename(filename).lower()
    # Drop extension.
    if "." in name:
        name_noext = name.rsplit(".", 1)[0]
    else:
        name_noext = name
    for ftype, keywords in _FILENAME_KEYWORDS:
        for kw in keywords:
            if kw in name_noext:
                return (ftype, "medium")
    return ("unknown", "low")


def _detect_by_sheet_names(sheet_names: List[str]) -> Tuple[str, str]:
    """Match any sheet name against keyword substrings.

    Returns ``(file_type, confidence)``. ``"medium"`` on a single
    keyword hit; ``("unknown", "low")`` otherwise. We deliberately
    keep this weaker than header-based detection since users often
    rename sheets to their preferred wording.
    """
    if not sheet_names:
        return ("unknown", "low")
    lowered = [s.lower() for s in sheet_names if s]
    for ftype, keywords in _SHEET_NAME_KEYWORDS:
        for kw in keywords:
            for s in lowered:
                if kw in s:
                    return (ftype, "medium")
    return ("unknown", "low")


def _match_headers(
    headers: List[str],
) -> Tuple[str, str, List[str]]:
    """Return ``(file_type, confidence, matched_fields)`` from header set."""
    if not headers:
        return ("unknown", "low", [])
    mapping = build_column_mapping(headers, "unknown")
    matched_fields = {m.standard_field for m in mapping.mappings}
    # First pass: any file type whose REQUIRED set is fully satisfied
    # AND has at least one optional match -> high confidence.
    best_type = "unknown"
    best_conf = "low"
    best_matched: List[str] = []
    for ftype, required, optional in _HEADER_REQUIREMENTS:
        required_hits = [f for f in required if f in matched_fields]
        optional_hits = [f for f in optional if f in matched_fields]
        if len(required_hits) == len(required) and optional_hits:
            best_type = ftype
            best_conf = "high"
            best_matched = sorted(required_hits + optional_hits)
            break
        if len(required_hits) >= max(1, len(required) - 1) and optional_hits:
            # Near-complete: medium.
            if best_conf != "high":
                best_type = ftype
                best_conf = "medium"
                best_matched = sorted(required_hits + optional_hits)
    return (best_type, best_conf, best_matched)


def _detect_by_headers(
    headers: List[str],
    file_type_hints: List[str],
) -> Tuple[str, str]:
    """Match a header row to a file type using column_aliases."""
    if not headers:
        return ("unknown", "low")
    ftype, conf, matched = _match_headers(headers)
    if conf == "high":
        return (ftype, "high")
    # If a hint is present and consistent with a near-match, boost.
    if conf == "medium" and ftype in file_type_hints:
        return (ftype, "high")
    return (ftype, conf)


def _detect_by_data(
    sample_rows: List[List[Any]],
    headers: List[str],
) -> Tuple[str, str]:
    """Spot-check the first few data rows to confirm or refute a guess.

    This function never raises the confidence above ``"medium"`` — it
    is a confirmation layer, not a primary signal. Its main job is to
    catch the "filename says products but the rows look like keyword
    aggregates" case so we don't misroute.
    """
    if not sample_rows or not headers:
        return ("unknown", "low")
    mapping = build_column_mapping(headers, "unknown")
    field_to_col = mapping.column_to_field
    # Invert: standard_field -> original header (use first mapping).
    inv: Dict[str, str] = {m.standard_field: m.original_header for m in mapping.mappings}

    def cell(field_name: str) -> Any:
        col_header = inv.get(field_name)
        if not col_header:
            return None
        try:
            idx = headers.index(col_header)
        except ValueError:
            return None
        for row in sample_rows:
            if idx < len(row):
                v = row[idx]
                if v is not None and str(v).strip():
                    return v
        return None

    # Strong signal: keyword column populated. We check keyword BEFORE
    # ASIN because a search-appearance file has both keyword and ASIN
    # but is semantically a "search" sheet, not a products sheet.
    kw_val = cell("keyword")
    if kw_val is not None and str(kw_val).strip():
        if "search_volume" in inv or "click_share" in inv:
            return ("keyword", "medium")
        if "asin" in inv:
            return ("search", "medium")
        return ("keyword", "low")
    # ASIN column has values that look like ASINs (10-char alphanumeric
    # starting with B; we accept 9-10 chars so synthetic fixture ASINs
    # also qualify) — only reach this branch when there is no keyword
    # column, so the file is genuinely products-shaped.
    asin_val = cell("asin")
    if asin_val is not None:
        s = str(asin_val).strip().upper()
        if re.fullmatch(r"B[0-9A-Z]{8,9}", s):
            return ("products", "medium")
    # Category column has any string.
    cat_val = cell("category")
    if cat_val is not None and str(cat_val).strip():
        if "market_revenue" in inv or "market_sales" in inv:
            return ("market", "medium")
        if "product_count" in inv:
            return ("category", "medium")
    # Brand.
    brand_val = cell("brand")
    if brand_val is not None and str(brand_val).strip():
        if "market_share" in inv or "click_share" in inv:
            return ("brand_analytics", "medium")
        if "monthly_revenue" in inv and "seller" not in inv:
            return ("brands", "medium")
    # Seller.
    seller_val = cell("seller")
    if seller_val is not None and str(seller_val).strip():
        return ("sellers", "medium")
    return ("unknown", "low")


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def detect_workbook(file_path: str) -> WorkbookDetectionResult:
    """Detect the type of an Amazon Excel workbook.

    Args:
        file_path: Path to the ``.xlsx`` file.

    Returns:
        A :class:`WorkbookDetectionResult`. Always returns; never
        raises on a missing file (the file_path is recorded and
        ``confidence`` is ``"low"``). ``openpyxl`` is imported lazily;
        if it is missing the result is ``"unknown"`` with a warning.
    """
    result = WorkbookDetectionResult(file_path=file_path)
    if not file_path or not os.path.exists(file_path):
        result.warnings.append(f"File not found: {file_path}")
        result.detection_reasons.append("file-missing")
        return result

    # Filename signal.
    fn_type, fn_conf = _detect_by_filename(file_path)
    result.detection_reasons.append(
        f"filename -> {fn_type} ({fn_conf})"
    )

    # Read workbook structure.
    try:
        from openpyxl import load_workbook  # type: ignore[import]
    except ImportError as exc:
        result.warnings.append(
            f"openpyxl not available; cannot read workbook ({exc})."
        )
        result.detection_reasons.append("openpyxl-missing")
        result.detected_type = fn_type if fn_type != "unknown" else "unknown"
        result.confidence = "low" if result.detected_type != "unknown" else "low"
        return result

    try:
        wb = load_workbook(filename=file_path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - tolerate broken files.
        result.warnings.append(f"Failed to open workbook: {exc}")
        result.detection_reasons.append("open-failed")
        return result

    try:
        sheet_names = wb.sheetnames or []
        sheet_signal_type, sheet_signal_conf = _detect_by_sheet_names(sheet_names)
        result.detection_reasons.append(
            f"sheet-names -> {sheet_signal_type} ({sheet_signal_conf})"
        )

        # Inspect each sheet to build SheetInfo and gather best header/data match.
        best_header_type = "unknown"
        best_header_conf = "low"
        best_matched_fields: List[str] = []
        best_sheet_index = 0
        best_data_type = "unknown"
        best_data_conf = "low"
        all_unmapped: List[str] = []

        for i, name in enumerate(sheet_names):
            try:
                ws = wb[name]
            except Exception:  # noqa: BLE001 - tolerate broken sheets.
                continue
            rows_iter = ws.iter_rows(values_only=True)
            try:
                header_row = next(rows_iter, None)
            except Exception:  # noqa: BLE001
                header_row = None
            data_rows: List[List[Any]] = []
            for _ in range(5):
                try:
                    r = next(rows_iter, None)
                except Exception:  # noqa: BLE001
                    r = None
                if r is None:
                    break
                row_list = list(r) if isinstance(r, tuple) else (list(r) if r else [])
                data_rows.append(row_list)

            headers = [str(h).strip() if h is not None else "" for h in (header_row or [])]
            row_count = ws.max_row or 0
            col_count = ws.max_column or 0
            sheet_info = SheetInfo(
                sheet_name=name,
                row_count=row_count,
                col_count=col_count,
                headers=headers,
            )
            result.sheets.append(sheet_info)

            # Header detection for this sheet.
            hints: List[str] = []
            if fn_type != "unknown":
                hints.append(fn_type)
            if sheet_signal_type != "unknown":
                hints.append(sheet_signal_type)
            h_type, h_conf = _detect_by_headers(headers, hints)
            sheet_info.detected_type = h_type if h_conf != "low" else None
            if h_conf == "high" and best_header_conf != "high":
                best_header_type, best_header_conf = h_type, h_conf
                best_matched_fields = _match_headers(headers)[2]
                best_sheet_index = i
            elif h_conf == "medium" and best_header_conf == "low":
                best_header_type, best_header_conf = h_type, h_conf
                best_matched_fields = _match_headers(headers)[2]
                best_sheet_index = i

            # Data spot-check on the chosen sheet.
            if best_sheet_index == i and data_rows:
                d_type, d_conf = _detect_by_data(data_rows, headers)
                best_data_type, best_data_conf = d_type, d_conf
                result.detection_reasons.append(
                    f"data[{name}] -> {d_type} ({d_conf})"
                )

            # Track unmapped columns for the chosen sheet.
            mapping_for_sheet = build_column_mapping(headers, "unknown")
            all_unmapped.extend(mapping_for_sheet.unmapped_columns)

        # Combine signals.
        # 1) Header match is the strongest signal.
        if best_header_conf == "high":
            candidate = best_header_type
            # Confirm with filename / sheet / data.
            consistency_hits = 0
            consistency_checks = 0
            if fn_type == candidate:
                consistency_hits += 1
            consistency_checks += 1
            if sheet_signal_type == candidate:
                consistency_hits += 1
            consistency_checks += 1
            if best_data_type == candidate or best_data_type == "unknown":
                if best_data_type == candidate:
                    consistency_hits += 1
                consistency_checks += 1
            elif best_data_type != "unknown":
                # Data signal contradicts the header.
                consistency_checks += 1
            result.detected_type = candidate
            result.confidence = "high"
            result.recognized_columns = best_matched_fields
            if consistency_hits == consistency_checks:
                result.detection_reasons.append(
                    "all signals consistent with header"
                )
            elif consistency_hits == 0 and fn_type not in ("unknown", candidate):
                # Filename actively disagrees.
                result.confidence = "low"
                result.warnings.append(
                    f"Filename hints '{fn_type}' but headers detect "
                    f"'{candidate}'; downgrading confidence to low."
                )
            else:
                result.confidence = "medium"
                result.detection_reasons.append(
                    "header match with partial corroboration"
                )
        elif best_header_conf == "medium":
            # Fall back to the medium header signal.
            candidate = best_header_type
            # If filename / sheet names agree, bump to high.
            if fn_type == candidate or sheet_signal_type == candidate:
                result.detected_type = candidate
                result.confidence = "high"
                result.detection_reasons.append(
                    "header medium + filename/sheet agreement"
                )
            else:
                result.detected_type = candidate
                result.confidence = "medium"
            result.recognized_columns = best_matched_fields
        else:
            # Header signal is low/unknown. Fall back to filename or sheet.
            if fn_type != "unknown":
                # Filename-only is suspicious; downrate to low.
                result.detected_type = fn_type
                result.confidence = "low"
                result.warnings.append(
                    "Header signal was low; using filename only. "
                    "Manual verification recommended."
                )
            elif sheet_signal_type != "unknown":
                result.detected_type = sheet_signal_type
                result.confidence = "low"
                result.warnings.append(
                    "Header signal was low; using sheet name only. "
                    "Manual verification recommended."
                )
            else:
                result.detected_type = "unknown"
                result.confidence = "low"

        result.unmapped_columns = list(dict.fromkeys(all_unmapped))
    finally:
        try:
            wb.close()
        except Exception:  # noqa: BLE001 - best effort cleanup.
            pass

    return result


__all__ = [
    "SUPPORTED_TYPES",
    "SheetInfo",
    "WorkbookDetectionResult",
    "detect_workbook",
    "_detect_by_filename",
    "_detect_by_sheet_names",
    "_detect_by_headers",
    "_detect_by_data",
]
