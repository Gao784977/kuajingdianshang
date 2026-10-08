"""File type detection routed by extension.

- ``xlsx`` -> :func:`src.modules.amazon.importers.workbook_detector.detect_workbook`
- ``csv``  -> :func:`detect_csv`
- ``json`` -> :func:`detect_json`

Each function returns a dict with the same shape as
``WorkbookDetectionResult.to_dict()``:
``detected_type, confidence, recognized_columns, unmapped_columns, warnings``.
"""
from __future__ import annotations

import csv
import io
import json
from typing import Any, Dict, List

# Known Amazon data column aliases (subset for detection; full mapping
# lives in the importers module).
_KEYWORD_COLUMNS = {
    "keyword", "keywords", "search_term", "search terms", "search_query",
    "query", "phrase", "search keyword",
}
_ASIN_COLUMNS = {
    "asin", "asins", "product asin", "parent asin", "child asin",
}
_PRICE_COLUMNS = {
    "price", "prices", "unit price", "sale price", "buybox price",
    "current price", "amazon price",
}
_SALES_COLUMNS = {
    "sales", "monthly sales", "estimated sales", "units sold",
    "bought in past month",
}
_REVENUE_COLUMNS = {
    "revenue", "monthly revenue", "estimated revenue", "sales revenue",
}
_BRAND_COLUMNS = {
    "brand", "brands", "brand name", "seller brand",
}
_SELLER_COLUMNS = {
    "seller", "seller name", "sold by", "merchant",
}
_RATING_COLUMNS = {
    "rating", "ratings", "star rating", "average rating",
    "review rating",
}
_REVIEW_COLUMNS = {
    "reviews", "review count", "number of reviews", "ratings count",
}

_TYPE_SIGNATURES = {
    "search_volume": _KEYWORD_COLUMNS,
    "product_listing": _ASIN_COLUMNS,
    "brand_analytics": _BRAND_COLUMNS | _KEYWORD_COLUMNS,
    "seller_analytics": _SELLER_COLUMNS | _ASIN_COLUMNS,
}


def _normalize_col(name: str) -> str:
    return (name or "").strip().lower().replace(" ", "_")


def _match_columns(columns: List[str]) -> Dict[str, Any]:
    normalized = [_normalize_col(c) for c in columns]
    recognized: List[str] = []
    detected_type = "unknown"
    confidence = "low"

    for c in columns:
        nc = _normalize_col(c)
        for known_set in (
            _KEYWORD_COLUMNS, _ASIN_COLUMNS, _PRICE_COLUMNS, _SALES_COLUMNS,
            _REVENUE_COLUMNS, _BRAND_COLUMNS, _SELLER_COLUMNS,
            _RATING_COLUMNS, _REVIEW_COLUMNS,
        ):
            if nc in {_normalize_col(x) for x in known_set}:
                recognized.append(c)
                break

    # Determine type by best signature match
    best_type = "unknown"
    best_count = 0
    for ftype, sig_cols in _TYPE_SIGNATURES.items():
        sig_norm = {_normalize_col(x) for x in sig_cols}
        count = sum(1 for nc in normalized if nc in sig_norm)
        if count > best_count:
            best_count = count
            best_type = ftype

    if best_count >= 3:
        detected_type = best_type
        confidence = "high"
    elif best_count >= 1:
        detected_type = best_type
        confidence = "medium"

    unmapped = [c for c in columns if c not in recognized]
    return {
        "detected_type": detected_type,
        "confidence": confidence,
        "recognized_columns": recognized,
        "unmapped_columns": unmapped,
        "warnings": [],
    }


def detect_csv(file_path: str) -> Dict[str, Any]:
    """Detect the type of a CSV file by inspecting its header row."""
    result = {
        "detected_type": "unknown",
        "confidence": "low",
        "recognized_columns": [],
        "unmapped_columns": [],
        "warnings": [],
    }
    try:
        with open(file_path, "rb") as fh:
            raw = fh.read(64 * 1024)  # read first 64 KB
    except OSError as exc:
        result["warnings"].append(f"Failed to read file: {exc}")
        return result

    try:
        text = raw.decode("utf-8-sig", errors="replace")
    except Exception as exc:
        result["warnings"].append(f"Failed to decode CSV: {exc}")
        return result

    try:
        sample = text[:8192]
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect)
    try:
        header = next(reader)
    except StopIteration:
        result["warnings"].append("CSV file is empty")
        return result

    columns = [c.strip() for c in header if c.strip()]
    if not columns:
        result["warnings"].append("No header columns found")
        return result

    matched = _match_columns(columns)
    result.update(matched)
    if not result["recognized_columns"]:
        result["warnings"].append(
            "No recognized Amazon data columns found; "
            "confirm the file type manually."
        )
    return result


def detect_json(file_path: str) -> Dict[str, Any]:
    """Detect the type of a JSON file by inspecting its structure."""
    result = {
        "detected_type": "unknown",
        "confidence": "low",
        "recognized_columns": [],
        "unmapped_columns": [],
        "warnings": [],
    }
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        result["warnings"].append(f"Failed to parse JSON: {exc}")
        return result

    columns: List[str] = []
    if isinstance(data, list) and data and isinstance(data[0], dict):
        columns = list(data[0].keys())
    elif isinstance(data, dict):
        columns = list(data.keys())
    else:
        result["warnings"].append(
            "JSON structure is not a list of objects or an object; "
            "cannot detect columns."
        )
        return result

    matched = _match_columns(columns)
    result.update(matched)
    if not result["recognized_columns"]:
        result["warnings"].append(
            "No recognized Amazon data columns found; "
            "confirm the file type manually."
        )
    return result


def detect_by_type(file_path: str, extension: str) -> Dict[str, Any]:
    """Route detection based on file extension."""
    ext = extension.lower().lstrip(".")
    if ext == "xlsx":
        from src.modules.amazon.importers.workbook_detector import detect_workbook
        return detect_workbook(file_path).to_dict()
    if ext == "csv":
        return detect_csv(file_path)
    if ext == "json":
        return detect_json(file_path)
    return {
        "detected_type": "unknown",
        "confidence": "low",
        "recognized_columns": [],
        "unmapped_columns": [],
        "warnings": [f"Unsupported file type: {ext}"],
    }
