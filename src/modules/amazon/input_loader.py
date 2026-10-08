"""User input loaders for the V3 Amazon workflow.

Three loaders and a merge layer:

* :func:`load_product_input` — reads the user product JSON, validates
  required fields (``keyword``, ``marketplace`` ∈ supported marketplaces,
  ``target_price_min <= target_price_max``). Strict mode raises on any
  invalid enum or missing required field.
* :func:`load_competitors_csv` — reads a competitor CSV with columns
  matching :class:`CompetitorRow`. Each row is tagged
  ``source="imported_csv"``.
* :func:`load_reviews_csv` — reads a review CSV with columns matching
  :class:`ReviewRow`. Each row is tagged ``source="imported_csv"``.
* :func:`merge_product_input` — decision #13: when both user input and
  mock data supply a field, user input wins; the merged record tags
  overrides as ``source="user_input"`` and fills as ``source="mock_data"``.

CSV loaders are tolerant of extra columns and column order — they read
by header name, not by position. Missing optional columns default to
empty/zero per :class:`CompetitorRow` / :class:`ReviewRow` defaults.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import CompetitorRow, ProductInput, ReviewRow


class InputLoaderError(Exception):
    """Raised when user input cannot be loaded or validated."""


# ---------------------------------------------------------------------------
# ProductInput loader (JSON)
# ---------------------------------------------------------------------------


def load_product_input(
    path: str,
    *,
    supported_marketplaces: Optional[List[str]] = None,
    strict: bool = True,
) -> ProductInput:
    """Load and validate a product input JSON file.

    Args:
        path: Path to the JSON file.
        supported_marketplaces: Allowed marketplace values (from config).
            If ``None``, validation is skipped.
        strict: When True, missing required fields or invalid enums raise
            :class:`InputLoaderError`. When False, warnings are recorded
            but the record is still returned.

    Returns:
        A validated :class:`ProductInput`.

    Raises:
        InputLoaderError: If the file is missing, invalid JSON, or (in
            strict mode) required fields are missing or marketplace is
            not in ``supported_marketplaces``.
    """
    p = Path(path)
    if not p.exists():
        raise InputLoaderError(f"Product input file not found: {path}")
    try:
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise InputLoaderError(f"Product input is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise InputLoaderError("Product input JSON root must be an object.")

    # Required fields
    keyword = str(data.get("keyword", "")).strip()
    marketplace = str(data.get("marketplace", "")).strip()

    if not keyword:
        msg = "Product input missing required field 'keyword'."
        if strict:
            raise InputLoaderError(msg)
    if not marketplace:
        msg = "Product input missing required field 'marketplace'."
        if strict:
            raise InputLoaderError(msg)

    if supported_marketplaces and marketplace and marketplace not in supported_marketplaces:
        msg = (
            f"Product input 'marketplace' value {marketplace!r} is not in "
            f"supported_marketplaces {supported_marketplaces}."
        )
        if strict:
            raise InputLoaderError(msg)

    # target_price_min <= target_price_max
    tmin = data.get("target_price_min")
    tmax = data.get("target_price_max")
    if tmin is not None and tmax is not None:
        if Decimal(str(tmin)) > Decimal(str(tmax)):
            msg = (
                f"Product input 'target_price_min' ({tmin}) exceeds "
                f"'target_price_max' ({tmax})."
            )
            if strict:
                raise InputLoaderError(msg)

    return ProductInput.from_dict(data)


# ---------------------------------------------------------------------------
# Competitor CSV loader
# ---------------------------------------------------------------------------


# Column name aliases so the loader is tolerant of slightly different
# header spellings (e.g. "price" vs "price_usd").
_COMPETITOR_ALIASES: Dict[str, List[str]] = {
    "brand": ["brand"],
    "asin": ["asin", "as_in", "id"],
    "product_name": ["product_name", "name", "title"],
    "price": ["price", "price_usd", "cost"],
    "rating": ["rating", "stars", "star_rating"],
    "review_count": ["review_count", "reviews", "num_reviews"],
    "selling_points": ["selling_points", "pros", "highlights"],
    "negative_points": ["negative_points", "cons", "negatives"],
    "source": ["source", "data_source"],
}

# Default source for CSV-loaded competitors.
_DEFAULT_COMPETITOR_SOURCE = "imported_csv"


def load_competitors_csv(path: str) -> List[CompetitorRow]:
    """Load a competitor CSV file by header name (order-independent).

    Each row is tagged ``source="imported_csv"`` unless the CSV itself
    provides a ``source`` column. Missing optional columns default to
    empty string / zero per :class:`CompetitorRow` defaults.
    """
    p = Path(path)
    if not p.exists():
        raise InputLoaderError(f"Competitors CSV file not found: {path}")

    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise InputLoaderError(f"Competitors CSV {path} has no header row.")
        # Build a mapping from actual column name -> canonical field
        col_map: Dict[str, str] = {}
        for field, aliases in _COMPETITOR_ALIASES.items():
            for alias in aliases:
                if alias in reader.fieldnames:
                    col_map[alias] = field
                    break

        rows: List[CompetitorRow] = []
        for i, raw in enumerate(reader):
            row_data: Dict[str, Any] = {}
            for alias, field in col_map.items():
                row_data[field] = (raw.get(alias) or "").strip()
            # Ensure source defaults to imported_csv
            if not row_data.get("source"):
                row_data["source"] = _DEFAULT_COMPETITOR_SOURCE

            # Validate required fields
            if not row_data.get("asin"):
                raise InputLoaderError(
                    f"Competitors CSV {path} row {i + 2} missing 'asin'."
                )
            if not row_data.get("brand"):
                raise InputLoaderError(
                    f"Competitors CSV {path} row {i + 2} missing 'brand'."
                )

            # Parse numeric fields
            price_str = str(row_data.get("price") or "0")
            rating_str = str(row_data.get("rating") or "0")
            try:
                price = Decimal(price_str)
            except Exception as exc:
                raise InputLoaderError(
                    f"Competitors CSV {path} row {i + 2} invalid price "
                    f"{price_str!r}: {exc}"
                ) from exc
            try:
                rating = Decimal(rating_str)
            except Exception as exc:
                raise InputLoaderError(
                    f"Competitors CSV {path} row {i + 2} invalid rating "
                    f"{rating_str!r}: {exc}"
                ) from exc
            try:
                review_count = int(row_data.get("review_count") or 0)
            except ValueError as exc:
                raise InputLoaderError(
                    f"Competitors CSV {path} row {i + 2} invalid review_count: {exc}"
                ) from exc

            rows.append(
                CompetitorRow(
                    brand=row_data.get("brand", ""),
                    asin=row_data.get("asin", ""),
                    product_name=row_data.get("product_name", ""),
                    price=price,
                    rating=rating,
                    review_count=review_count,
                    selling_points=row_data.get("selling_points", ""),
                    negative_points=row_data.get("negative_points", ""),
                    source=row_data.get("source", _DEFAULT_COMPETITOR_SOURCE),
                )
            )
        return rows


# ---------------------------------------------------------------------------
# Review CSV loader
# ---------------------------------------------------------------------------


_REVIEW_ALIASES: Dict[str, List[str]] = {
    "review_id": ["review_id", "id", "rid"],
    "asin": ["asin", "as_in", "product_id"],
    "rating": ["rating", "stars", "star_rating"],
    "review_text": ["review_text", "text", "review", "content"],
    "review_date": ["review_date", "date", "reviewed_at"],
    "source": ["source", "data_source"],
}

_DEFAULT_REVIEW_SOURCE = "imported_csv"


def load_reviews_csv(path: str) -> List[ReviewRow]:
    """Load a review CSV file by header name (order-independent).

    Each row is tagged ``source="imported_csv"`` unless the CSV provides
    a ``source`` column. Missing optional columns default to empty.
    """
    p = Path(path)
    if not p.exists():
        raise InputLoaderError(f"Reviews CSV file not found: {path}")

    with p.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise InputLoaderError(f"Reviews CSV {path} has no header row.")

        col_map: Dict[str, str] = {}
        for field, aliases in _REVIEW_ALIASES.items():
            for alias in aliases:
                if alias in reader.fieldnames:
                    col_map[alias] = field
                    break

        rows: List[ReviewRow] = []
        for i, raw in enumerate(reader):
            row_data: Dict[str, Any] = {}
            for alias, field in col_map.items():
                row_data[field] = (raw.get(alias) or "").strip()
            if not row_data.get("source"):
                row_data["source"] = _DEFAULT_REVIEW_SOURCE

            if not row_data.get("review_id"):
                raise InputLoaderError(
                    f"Reviews CSV {path} row {i + 2} missing 'review_id'."
                )
            if not row_data.get("asin"):
                raise InputLoaderError(
                    f"Reviews CSV {path} row {i + 2} missing 'asin'."
                )

            try:
                rating = int(float(row_data.get("rating") or 0))
            except ValueError as exc:
                raise InputLoaderError(
                    f"Reviews CSV {path} row {i + 2} invalid rating: {exc}"
                ) from exc

            rows.append(
                ReviewRow(
                    review_id=row_data.get("review_id", ""),
                    asin=row_data.get("asin", ""),
                    rating=rating,
                    review_text=row_data.get("review_text", ""),
                    review_date=row_data.get("review_date", ""),
                    source=row_data.get("source", _DEFAULT_REVIEW_SOURCE),
                )
            )
        return rows


# ---------------------------------------------------------------------------
# Merge layer (decision #13: user input wins, mock fills gaps)
# ---------------------------------------------------------------------------


def merge_product_input(
    user_input: Optional[ProductInput],
    mock_input: ProductInput,
) -> ProductInput:
    """Merge user product input with mock data.

    Decision #13: when both supply a field, user input wins. The merged
    record's ``source`` is ``"user_input"`` (because the user provided
    the record) and ``confidence`` is ``"high"``. Fields the user left
    blank are filled from ``mock_input`` and remain tagged at the field
    level via downstream agents (e.g. market analysis from mock).

    If ``user_input`` is ``None``, the mock input is returned unchanged.
    """
    if user_input is None:
        return mock_input

    return ProductInput(
        keyword=user_input.keyword or mock_input.keyword,
        marketplace=user_input.marketplace or mock_input.marketplace,
        target_price_min=(
            user_input.target_price_min
            if user_input.target_price_min is not None
            else mock_input.target_price_min
        ),
        target_price_max=(
            user_input.target_price_max
            if user_input.target_price_max is not None
            else mock_input.target_price_max
        ),
        direction=user_input.direction or mock_input.direction,
        constraints=user_input.constraints or mock_input.constraints,
        notes=user_input.notes or mock_input.notes,
        source="user_input",
        confidence="high",
        competitors_path=user_input.competitors_path,
        reviews_path=user_input.reviews_path,
    )


def merge_competitors(
    user_rows: Optional[List[CompetitorRow]],
    mock_rows: List[CompetitorRow],
) -> List[CompetitorRow]:
    """Merge user competitor rows with mock rows.

    User rows take priority and keep their own ``source`` tag
    (``imported_csv``). Mock rows fill the remaining slots so the
    competitor analysis always has enough data. If the user provides
    no CSV, all mock rows are returned.
    """
    if not user_rows:
        return list(mock_rows)
    return list(user_rows) + list(mock_rows)


def merge_reviews(
    user_rows: Optional[List[ReviewRow]],
    mock_rows: List[ReviewRow],
) -> List[ReviewRow]:
    """Merge user review rows with mock rows.

    Same semantics as :func:`merge_competitors`: user rows first,
    mock fills the rest.
    """
    if not user_rows:
        return list(mock_rows)
    return list(user_rows) + list(mock_rows)
