"""V3.1.2 — record-level normalisation, ASIN deduplication and
multi-source field merging.

This module is the second layer above the typed loaders in
:mod:`src.modules.amazon.importers`. The loaders return typed records
(:class:`AmazonProduct`, :class:`AmazonSearchAppearance`, ...); this
module turns those raw lists into the canonical, deduplicated,
source-prioritised structures that downstream agents consume.

Three responsibilities:

1. **Product deduplication** — :func:`normalize_products` collapses
   rows that share an ASIN (or, when ASIN is missing, the synthetic
   ``brand|title`` key) into a single record, preserving parent/child
   ASIN relationships and tracking every duplicate group with its
   source files. ASIN-less records are flagged in
   :attr:`NormalizedProductResult.missing_asin_keys`.

2. **Search-appearance multiplicity** — :func:`normalize_search_appearances`
   deliberately does **not** deduplicate. Amazon reports the same ASIN
   under multiple keywords, placements (sponsored vs organic), pages
   and positions; collapsing those would erase signal. The function
   only computes aggregates (unique ASIN / keyword counts) and passes
   the list through unchanged.

3. **Field-level source-priority merge** — :func:`merge_by_source_priority`
   resolves a single field across multiple source records into a
   :class:`MergedField` carrying ``value`` + full provenance. The
   priority order is hard-coded to match the project rules:

       user_input > imported_excel > fetched_url >
        calculated > agent_inference > mock_data

   Lower-priority values are kept in :attr:`MergedField.provenance`
   (never silently dropped), and :attr:`MergedField.requires_review`
   is set ``True`` whenever a value was overridden or the winning
   source is low-confidence (``agent_inference`` / ``mock_data``).

Stdlib only. No openpyxl dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from .normalized_models import (
    AmazonProduct,
    AmazonSearchAppearance,
    SourceInfo,
)


# ---------------------------------------------------------------------------
# Source priority — matches project rules in project_memory.md.
# Lower number = higher priority. Unknown source types get 99 so they
# never win against a known type.
# ---------------------------------------------------------------------------

SOURCE_PRIORITY: Dict[str, int] = {
    "user_input": 1,
    "imported_excel": 2,
    "fetched_url": 3,
    "calculated": 4,
    "agent_inference": 5,
    "mock_data": 6,
}


def source_priority(source_type: str) -> int:
    """Return the numeric priority for ``source_type`` (lower wins)."""
    return SOURCE_PRIORITY.get(source_type, 99)


# Confidence defaults by source type. Imported / user-supplied data is
# trustworthy; inferred and mock data are not.
_DEFAULT_CONFIDENCE: Dict[str, float] = {
    "user_input": 1.0,
    "imported_excel": 0.95,
    "fetched_url": 0.9,
    "calculated": 0.85,
    "agent_inference": 0.5,
    "mock_data": 0.2,
}


def default_confidence(source_type: str) -> float:
    return _DEFAULT_CONFIDENCE.get(source_type, 0.5)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class MergedField:
    """Result of merging a single field across multiple source records.

    The :attr:`value` is the winning value (already serialised —
    Decimals become ``str``, lists become ``list`` of serialised
    items). :attr:`provenance` records every overridden source so
    downstream review tooling can show "we kept X from file A but file B
    also had Y".
    """

    value: Any
    source_type: str = "mock_data"
    source_file: str = ""
    source_sheet: str = ""
    source_row: int = 0
    source_url: str = ""
    confidence: float = 0.0
    calculation_method: str = ""
    requires_review: bool = False
    # Each entry: {"value","source_type","source_file","source_sheet",
    # "source_row","source_url","priority"}
    provenance: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "value": self.value,
            "source_type": self.source_type,
            "source_file": self.source_file,
            "source_sheet": self.source_sheet,
            "source_row": self.source_row,
            "source_url": self.source_url,
            "confidence": self.confidence,
            "calculation_method": self.calculation_method,
            "requires_review": self.requires_review,
            "provenance": [dict(p) for p in self.provenance],
        }


@dataclass
class ParentChildRelation:
    """Parent ASIN -> child ASINs mapping extracted from product rows."""

    parent_asin: str
    child_asins: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parent_asin": self.parent_asin,
            "child_asins": list(self.child_asins),
        }


@dataclass
class DuplicateGroup:
    """Records that shared a dedup key during normalisation."""

    dedup_key: str
    record_count: int = 0
    source_files: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dedup_key": self.dedup_key,
            "record_count": self.record_count,
            "source_files": list(self.source_files),
        }


@dataclass
class NormalizedProductResult:
    """Output of :func:`normalize_products`."""

    deduped_products: List[AmazonProduct] = field(default_factory=list)
    duplicate_groups: List[DuplicateGroup] = field(default_factory=list)
    missing_asin_keys: List[str] = field(default_factory=list)
    parent_child_relations: List[ParentChildRelation] = field(default_factory=list)
    # Per-dedup-key review flag: True whenever ASIN was missing or a
    # field was overridden across sources.
    requires_review_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "deduped_products": [p.to_dict() for p in self.deduped_products],
            "duplicate_groups": [g.to_dict() for g in self.duplicate_groups],
            "missing_asin_keys": list(self.missing_asin_keys),
            "parent_child_relations": [r.to_dict() for r in self.parent_child_relations],
            "requires_review_keys": list(self.requires_review_keys),
        }


@dataclass
class NormalizedSearchResult:
    """Output of :func:`normalize_search_appearances`.

    Search appearances are NOT deduplicated: the same ASIN can appear
    under multiple keywords, placements (sponsored + organic), pages
    and positions. Every row is preserved; only aggregates are added.
    """

    appearances: List[AmazonSearchAppearance] = field(default_factory=list)
    total_count: int = 0
    unique_asin_count: int = 0
    unique_keyword_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "appearances": [a.to_dict() for a in self.appearances],
            "total_count": self.total_count,
            "unique_asin_count": self.unique_asin_count,
            "unique_keyword_count": self.unique_keyword_count,
        }


# ---------------------------------------------------------------------------
# Serialisation helper
# ---------------------------------------------------------------------------


def _serialize(value: Any) -> Any:
    """Normalise a value for storage in :class:`MergedField`.

    Decimals become ``str`` (round-trippable), lists/tuples become
    lists of serialised items, ``None`` stays ``None``.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _is_empty(value: Any) -> bool:
    """True when a field value should be treated as "absent"."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, (list, tuple, dict)) and len(value) == 0:
        return True
    return False


# ---------------------------------------------------------------------------
# Field-level merge
# ---------------------------------------------------------------------------


def merge_by_source_priority(
    records: List[SourceInfo],
    field_name: str,
    getter: Optional[Callable[[Any], Any]] = None,
) -> MergedField:
    """Merge one field across multiple source records by priority.

    Args:
        records: Records carrying the field (any subclass of
            :class:`SourceInfo`).
        field_name: Attribute name on each record. Used for the
            ``calculation_method`` lookup (``<field>_calc_method``)
            and reported back on :class:`MergedField`.
        getter: Optional callable ``(record) -> value``. Defaults to
            ``getattr(record, field_name, None)``. Useful when the
            field is computed rather than stored.

    Returns:
        A :class:`MergedField` whose ``value`` is the winning value and
        whose ``provenance`` lists every overridden source. If no
        record has a non-empty value, returns a review-flagged empty
        :class:`MergedField` carrying the first record's source info.
    """
    if not records:
        return MergedField(
            value=None,
            source_type="mock_data",
            confidence=0.0,
            requires_review=True,
        )

    getter_fn = getter or (lambda r: getattr(r, field_name, None))

    # (priority, original_index, record, value) for every non-empty value
    candidates: List[tuple] = []
    for idx, record in enumerate(records):
        raw = getter_fn(record)
        if _is_empty(raw):
            continue
        priority = source_priority(record.source_type)
        candidates.append((priority, idx, record, raw))

    if not candidates:
        first = records[0]
        return MergedField(
            value=None,
            source_type=first.source_type,
            source_file=first.source_file,
            source_sheet=first.source_sheet,
            source_row=first.source_row,
            source_url=getattr(first, "source_url", "") or "",
            confidence=0.0,
            calculation_method=getattr(first, f"{field_name}_calc_method", "") or "",
            requires_review=True,
        )

    # Stable sort: lower priority number wins; ties broken by original order
    candidates.sort(key=lambda c: (c[0], c[1]))
    win_priority, _win_idx, winner, win_value = candidates[0]

    provenance: List[Dict[str, Any]] = []
    for priority, _idx, record, _val in candidates[1:]:
        provenance.append(
            {
                "value": _serialize(_val),
                "source_type": record.source_type,
                "source_file": record.source_file,
                "source_sheet": record.source_sheet,
                "source_row": record.source_row,
                "source_url": getattr(record, "source_url", "") or "",
                "priority": priority,
            }
        )

    # requires_review when:
    #   - any lower-priority value was overridden, OR
    #   - the winning source is low-confidence (agent_inference / mock_data)
    requires_review = bool(provenance) or win_priority >= SOURCE_PRIORITY["agent_inference"]

    return MergedField(
        value=_serialize(win_value),
        source_type=winner.source_type,
        source_file=winner.source_file,
        source_sheet=winner.source_sheet,
        source_row=winner.source_row,
        source_url=getattr(winner, "source_url", "") or "",
        confidence=default_confidence(winner.source_type),
        calculation_method=getattr(winner, f"{field_name}_calc_method", "") or "",
        requires_review=requires_review,
        provenance=provenance,
    )


# ---------------------------------------------------------------------------
# Product deduplication
# ---------------------------------------------------------------------------


# Fields considered when merging a duplicate product row into the
# primary record. Anything not in this list (e.g. ``source_hash``) is
# left untouched on the primary.
_PRODUCT_MERGE_FIELDS: tuple = (
    "asin", "sku", "parent_asin", "brand", "brand_link", "title",
    "bullet_points", "product_url", "main_image_url",
    "category_path", "category", "main_category", "subcategory",
    "main_bsr", "subcategory_bsr", "monthly_sales", "monthly_sales_growth",
    "monthly_revenue", "child_sales", "child_revenue", "variation_count",
    "price", "prime_price", "coupon", "qa_count", "review_count",
    "monthly_new_reviews", "rating", "review_rate", "fba_fee", "margin_rate",
    "launch_date", "listing_age_days", "fulfillment_method", "sellers_count",
    "buybox_seller", "seller_location", "weight", "dimensions",
    "package_weight", "package_dimensions",
)


def _merge_product(primary: AmazonProduct, secondary: AmazonProduct) -> bool:
    """Fill empty fields on ``primary`` from ``secondary``.

    Source-priority aware: when both records have a value for the same
    field and the values differ, the higher-priority source wins
    (lower number) and the dedup key is flagged for review. Returns
    ``True`` if any genuine conflict was found (so the caller can add
    the key to :attr:`requires_review_keys`).
    """
    primary_priority = source_priority(primary.source_type)
    secondary_priority = source_priority(secondary.source_type)
    overridden = False

    for fname in _PRODUCT_MERGE_FIELDS:
        p_val = getattr(primary, fname)
        s_val = getattr(secondary, fname)
        if _is_empty(s_val):
            continue
        if _is_empty(p_val):
            # Primary lacks this field; take secondary's value wholesale.
            setattr(primary, fname, s_val)
            continue
        # Both have values -> potential conflict.
        if p_val == s_val:
            # Same value, no conflict.
            continue
        # Values differ -> genuine conflict, flag for review.
        overridden = True
        if secondary_priority < primary_priority:
            # Secondary has higher priority (lower number); override.
            setattr(primary, fname, s_val)
        # else: keep primary's value (primary has higher/equal priority).
    return overridden


def normalize_products(products: List[AmazonProduct]) -> NormalizedProductResult:
    """Deduplicate products by ASIN (or ``brand|title`` fallback).

    Behaviour:

    * Rows sharing an ASIN are merged into the first occurrence. Empty
      fields on the primary are filled from later rows; if both rows
      have a value, the higher-priority source wins and the dedup key
      is added to :attr:`requires_review_keys`.
    * When ASIN is missing, the synthetic ``brand|title`` key is used
      and the key is recorded in :attr:`missing_asin_keys`. Such keys
      are always flagged for review.
    * Parent/child ASIN relationships are extracted from
      ``parent_asin`` and exposed via :attr:`parent_child_relations`.
    * :attr:`duplicate_groups` records every key that had >1 input
      row, with the source files involved.

    The input list is not mutated; a new list of
    :class:`AmazonProduct` (the primary records) is returned.
    """
    if not products:
        return NormalizedProductResult()

    deduped: Dict[str, AmazonProduct] = {}
    duplicate_groups_map: Dict[str, List[AmazonProduct]] = {}
    missing_asin_keys: List[str] = []
    requires_review_keys: List[str] = []
    overridden_keys: set = set()

    for product in products:
        key = product.dedup_key()
        if not product.asin:
            if key not in missing_asin_keys:
                missing_asin_keys.append(key)

        if key in deduped:
            # Duplicate: merge into the existing primary.
            duplicate_groups_map.setdefault(key, [deduped[key]])
            duplicate_groups_map[key].append(product)
            overridden = _merge_product(deduped[key], product)
            if overridden:
                overridden_keys.add(key)
        else:
            deduped[key] = product

    # ASIN-less records always require review.
    for key in missing_asin_keys:
        requires_review_keys.append(key)
    # Records with overridden fields require review.
    for key in overridden_keys:
        if key not in requires_review_keys:
            requires_review_keys.append(key)

    # Parent/child relations from the deduped products.
    parent_to_children: Dict[str, List[str]] = {}
    for product in deduped.values():
        if product.parent_asin and product.asin:
            children = parent_to_children.setdefault(product.parent_asin, [])
            if product.asin not in children:
                children.append(product.asin)
    parent_child_relations = [
        ParentChildRelation(parent_asin=p, child_asins=sorted(children))
        for p, children in parent_to_children.items()
    ]
    parent_child_relations.sort(key=lambda r: r.parent_asin)

    duplicate_groups = [
        DuplicateGroup(
            dedup_key=key,
            record_count=len(records),
            source_files=sorted({r.source_file for r in records if r.source_file}),
        )
        for key, records in duplicate_groups_map.items()
    ]
    duplicate_groups.sort(key=lambda g: g.dedup_key)

    return NormalizedProductResult(
        deduped_products=list(deduped.values()),
        duplicate_groups=duplicate_groups,
        missing_asin_keys=missing_asin_keys,
        parent_child_relations=parent_child_relations,
        requires_review_keys=requires_review_keys,
    )


# ---------------------------------------------------------------------------
# Search-appearance normalisation (no dedup)
# ---------------------------------------------------------------------------


def normalize_search_appearances(
    appearances: List[AmazonSearchAppearance],
) -> NormalizedSearchResult:
    """Pass-through normaliser for search appearances.

    Search-appearance rows are **never** deduplicated. The same ASIN
    can legitimately appear under multiple keywords, multiple
    placements (sponsored + organic), multiple pages, and multiple
    positions; collapsing those would erase the search-position
    signal that downstream agents need.

    This function only:

    * returns the list unchanged (a shallow copy),
    * computes :attr:`unique_asin_count` / :attr:`unique_keyword_count`
      aggregates,
    * sets :attr:`total_count`.
    """
    if not appearances:
        return NormalizedSearchResult()

    unique_asins = {a.asin for a in appearances if a.asin}
    unique_keywords = {a.keyword for a in appearances if a.keyword}

    return NormalizedSearchResult(
        appearances=list(appearances),
        total_count=len(appearances),
        unique_asin_count=len(unique_asins),
        unique_keyword_count=len(unique_keywords),
    )


# ---------------------------------------------------------------------------
# Generic record dedup (used by keyword/category/brand/seller metrics)
# ---------------------------------------------------------------------------


def dedup_by_key(records: List[Any]) -> Dict[str, Any]:
    """Deduplicate generic metric records by their ``dedup_key``.

    For :class:`KeywordMetric`, :class:`CategoryMetric`,
    :class:`BrandMetric`, :class:`SellerMetric` — these all expose a
    ``dedup_key()`` method returning a unique identifier. Later rows
    fill empty fields on the primary; conflicting values keep the
    higher-priority source.

    Returns a dict with ``deduped`` (list), ``duplicate_groups``
    (list[DuplicateGroup]) and ``requires_review_keys`` (list[str]).
    """
    if not records:
        return {"deduped": [], "duplicate_groups": [], "requires_review_keys": []}

    deduped: Dict[str, Any] = {}
    duplicate_groups_map: Dict[str, List[Any]] = {}
    requires_review_keys: List[str] = []
    overridden_keys: set = set()

    # Fields common to the four metric classes. We rely on
    # ``getattr`` returning ``None`` for absent attributes, which is
    # safe because all of these are Optional with ``None`` default.
    metric_fields = (
        "search_volume", "search_growth", "click_share", "conversion_share",
        "competition", "related_keywords",
        "category", "category_path", "product_count", "market_sales",
        "market_revenue", "average_price", "median_price", "growth",
        "brand", "monthly_sales", "monthly_revenue", "annual_sales",
        "annual_revenue", "market_share",
        "seller",
    )

    for record in records:
        key = record.dedup_key()
        if key in deduped:
            duplicate_groups_map.setdefault(key, [deduped[key]])
            duplicate_groups_map[key].append(record)
            primary = deduped[key]
            primary_priority = source_priority(primary.source_type)
            secondary_priority = source_priority(record.source_type)
            for fname in metric_fields:
                p_val = getattr(primary, fname, None)
                s_val = getattr(record, fname, None)
                if _is_empty(s_val):
                    continue
                if _is_empty(p_val):
                    setattr(primary, fname, s_val)
                    continue
                # Both have values -> potential conflict.
                if p_val == s_val:
                    continue
                # Values differ -> genuine conflict, flag for review.
                overridden_keys.add(key)
                if secondary_priority < primary_priority:
                    setattr(primary, fname, s_val)
        else:
            deduped[key] = record

    for key in overridden_keys:
        requires_review_keys.append(key)

    duplicate_groups = [
        DuplicateGroup(
            dedup_key=key,
            record_count=len(records),
            source_files=sorted({r.source_file for r in records if r.source_file}),
        )
        for key, records in duplicate_groups_map.items()
    ]
    duplicate_groups.sort(key=lambda g: g.dedup_key)

    return {
        "deduped": list(deduped.values()),
        "duplicate_groups": duplicate_groups,
        "requires_review_keys": requires_review_keys,
    }


__all__ = [
    "DuplicateGroup",
    "MergedField",
    "NormalizedProductResult",
    "NormalizedSearchResult",
    "ParentChildRelation",
    "SOURCE_PRIORITY",
    "dedup_by_key",
    "default_confidence",
    "merge_by_source_priority",
    "normalize_products",
    "normalize_search_appearances",
    "source_priority",
]
