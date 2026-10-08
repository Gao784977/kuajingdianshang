"""V3.1.2 demo — exercise the normalizer end-to-end.

Loads fixture xlsx files via the V3.1.1 importers, then runs the
V3.1.2 normalizer (normalize_products, normalize_search_appearances,
merge_by_source_priority) on the result. Prints a summary that
demonstrates:

* ASIN dedup with parent/child relations
* Synthetic brand|title key for ASIN-less records
* Source-priority field merge with provenance
* requires_review flagging on conflicts
* Search-appearance multiplicity preservation

Run::

    python examples/v312_normalizer_demo.py
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from typing import List

# Make ``src`` importable when running from project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.modules.amazon.importers import (
    AmazonProduct,
    AmazonSearchAppearance,
    detect_workbook,
    get_loader,
    merge_by_source_priority,
    normalize_products,
    normalize_search_appearances,
)
from src.modules.amazon.importers.normalized_models import SourceInfo

FIXTURE_DIR = os.path.join("tests", "fixtures")


def _fixture(name: str) -> str:
    return os.path.join(FIXTURE_DIR, name)


def demo_product_dedup() -> None:
    """Load products.xlsx twice (simulating two source files) and dedup."""
    print("\n" + "=" * 70)
    print("Demo 1: Product ASIN deduplication + parent/child relations")
    print("=" * 70)

    path = _fixture("products.xlsx")
    if not os.path.exists(path):
        print(f"  (skip: {path} not found)")
        return

    detection = detect_workbook(path)
    print(f"  Detected type: {detection.detected_type} (confidence={detection.confidence})")
    if detection.detected_type != "products":
        print(f"  Expected 'products', got '{detection.detected_type}'. Aborting.")
        return

    loader = get_loader("products")
    result = loader.load(path)
    products: List[AmazonProduct] = list(result.records)
    print(f"  Loaded {len(products)} product rows from {os.path.basename(path)}")

    # Simulate a second source by re-loading the same file but
    # overriding source_file (as if it came from another workbook).
    products_dup: List[AmazonProduct] = []
    for p in products:
        # Build a near-duplicate with mock_data source type and a
        # slightly different price, so we can show conflict resolution.
        dup = AmazonProduct(
            asin=p.asin,
            brand=p.brand,
            title=p.title,
            parent_asin=p.parent_asin,
            price=p.price + Decimal("1.00") if p.price else Decimal("1.00"),
            source_file="products_copy.xlsx",
            source_sheet=p.source_sheet,
            source_row=p.source_row,
            source_type="mock_data",
        )
        products_dup.append(dup)

    all_products = products + products_dup
    print(f"  Total input rows (real + mock duplicates): {len(all_products)}")

    normalized = normalize_products(all_products)
    print(f"  Deduped products: {len(normalized.deduped_products)}")
    print(f"  Duplicate groups: {len(normalized.duplicate_groups)}")
    print(f"  Missing-ASIN keys: {len(normalized.missing_asin_keys)}")
    print(f"  Parent/child relations: {len(normalized.parent_child_relations)}")
    print(f"  Requires-review keys: {len(normalized.requires_review_keys)}")

    for g in normalized.duplicate_groups[:3]:
        print(f"    - {g.dedup_key}: {g.record_count} rows, "
              f"files={g.source_files}")
    for r in normalized.parent_child_relations[:3]:
        print(f"    - parent {r.parent_asin} -> children {r.child_asins}")
    for k in normalized.requires_review_keys[:3]:
        print(f"    - review: {k}")


def demo_search_appearances() -> None:
    """Load search.xlsx and verify multiplicity is preserved."""
    print("\n" + "=" * 70)
    print("Demo 2: Search-appearance multiplicity (no dedup)")
    print("=" * 70)

    path = _fixture("search.xlsx")
    if not os.path.exists(path):
        print(f"  (skip: {path} not found)")
        return

    detection = detect_workbook(path)
    print(f"  Detected type: {detection.detected_type} (confidence={detection.confidence})")
    if detection.detected_type != "search":
        print(f"  Expected 'search', got '{detection.detected_type}'. Aborting.")
        return

    loader = get_loader("search")
    result = loader.load(path)
    appearances: List[AmazonSearchAppearance] = list(result.records)
    print(f"  Loaded {len(appearances)} search-appearance rows")

    normalized = normalize_search_appearances(appearances)
    print(f"  Total count (preserved): {normalized.total_count}")
    print(f"  Unique ASINs: {normalized.unique_asin_count}")
    print(f"  Unique keywords: {normalized.unique_keyword_count}")

    # Show the first few appearances to demonstrate placement diversity
    placements = {}
    for a in appearances:
        key = a.placement_type
        placements[key] = placements.get(key, 0) + 1
    print(f"  Placement breakdown: {placements}")


def demo_field_merge() -> None:
    """Show source-priority field merge with provenance."""
    print("\n" + "=" * 70)
    print("Demo 3: Source-priority field merge with provenance")
    print("=" * 70)

    # Three records for the same ASIN, same field, different sources.
    p_user = AmazonProduct(
        asin="B00DEMO0001", price=Decimal("25.00"),
        source_file="user_input.json", source_row=1, source_type="user_input",
    )
    p_excel = AmazonProduct(
        asin="B00DEMO0001", price=Decimal("19.99"),
        source_file="products.xlsx", source_row=10, source_type="imported_excel",
    )
    p_mock = AmazonProduct(
        asin="B00DEMO0001", price=Decimal("99.99"),
        source_file="mock.py", source_row=99, source_type="mock_data",
    )

    merged = merge_by_source_priority([p_mock, p_user, p_excel], "price")
    print(f"  Field: price")
    print(f"  Winning value: {merged.value}")
    print(f"  Winning source: {merged.source_type} ({merged.source_file} row {merged.source_row})")
    print(f"  Confidence: {merged.confidence:.2f}")
    print(f"  Requires review: {merged.requires_review}")
    print(f"  Provenance (overridden sources): {len(merged.provenance)}")
    for prov in merged.provenance:
        print(f"    - {prov['source_type']}: value={prov['value']} "
              f"(file={prov['source_file']}, row={prov['source_row']}, "
              f"priority={prov['priority']})")


def main() -> None:
    print("V3.1.2 Normalizer Demo")
    print(f"  Working dir: {os.getcwd()}")
    print(f"  Fixture dir: {os.path.abspath(FIXTURE_DIR)}")

    demo_product_dedup()
    demo_search_appearances()
    demo_field_merge()

    print("\n" + "=" * 70)
    print("Demo complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
