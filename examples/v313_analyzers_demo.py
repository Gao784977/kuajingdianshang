"""V3.1.3 demo — run all 5 analyzers against the xlsx fixtures.

Loads the V3.1.1 fixture workbooks via the importers, normalises
them via the V3.1.2 normaliser, then runs the 5 V3.1.3 analyzers
(keywords, categories, brands, sellers, search positions) and prints
a compact summary of each.

Run from the project root:

    python examples/v313_analyzers_demo.py

No network, no API keys, no openpyxl-at-import-time surprises.
"""

from __future__ import annotations

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

# Ensure the project root is importable when run via ``python examples/...``.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.modules.amazon.importers import (  # noqa: E402
    AmazonProduct,
    BrandMetric,
    CategoryMetric,
    KeywordMetric,
    SellerMetric,
    detect_workbook,
    get_loader,
)
from src.modules.amazon.importers.normalizer import (  # noqa: E402
    dedup_by_key,
    normalize_products,
    normalize_search_appearances,
)
from src.modules.amazon.analyzers import (  # noqa: E402
    analyze_brands,
    analyze_categories,
    analyze_keywords,
    analyze_search_positions,
    analyze_sellers,
)


FIXTURES = ROOT / "tests" / "fixtures"


def _load(file_name: str):
    """Detect + load a fixture workbook, returning the LoaderResult."""
    path = FIXTURES / file_name
    if not path.exists():
        print(f"  [skip] fixture not found: {path}")
        return None
    detection = detect_workbook(str(path))
    if detection.detected_type == "unknown":
        print(f"  [skip] unknown type: {file_name}")
        return None
    loader = get_loader(detection.detected_type)
    if loader is None:
        print(f"  [skip] no loader for type: {detection.detected_type}")
        return None
    return loader.load(str(path))


def _print_section(title: str, payload: dict, max_lines: int = 12) -> None:
    print(f"\n--- {title} ---")
    # Pretty-print but truncate to keep the demo readable.
    formatted = json.dumps(payload, indent=2, ensure_ascii=False)
    lines = formatted.splitlines()
    for line in lines[:max_lines]:
        print(line)
    if len(lines) > max_lines:
        print(f"  ... ({len(lines) - max_lines} more lines)")


def main() -> int:
    print("=" * 70)
    print("V3.1.3 analyzers demo")
    print("=" * 70)

    # --- Load fixtures -------------------------------------------------------
    print("\n[1] Loading xlsx fixtures via V3.1.1 importers")
    keyword_result = _load("keyword_analysis.xlsx")
    category_result = _load("category_analysis.xlsx")
    brand_result = _load("brands.xlsx")
    seller_result = _load("sellers.xlsx")
    search_result = _load("search.xlsx")
    product_result = _load("products.xlsx")

    keyword_metrics = list(keyword_result.records) if keyword_result else []
    category_metrics = list(category_result.records) if category_result else []
    brand_metrics = list(brand_result.records) if brand_result else []
    seller_metrics = list(seller_result.records) if seller_result else []
    search_appearances = list(search_result.records) if search_result else []
    products = list(product_result.records) if product_result else []

    print(f"  keywords:  {len(keyword_metrics)}")
    print(f"  categories: {len(category_metrics)}")
    print(f"  brands:    {len(brand_metrics)}")
    print(f"  sellers:   {len(seller_metrics)}")
    print(f"  search:    {len(search_appearances)}")
    print(f"  products:  {len(products)}")

    # --- Normalise ----------------------------------------------------------
    print("\n[2] Normalising via V3.1.2 normaliser")
    deduped_kw = dedup_by_key(keyword_metrics)
    deduped_cat = dedup_by_key(category_metrics)
    deduped_brand = dedup_by_key(brand_metrics)
    deduped_seller = dedup_by_key(seller_metrics)
    norm_products = normalize_products(products)
    norm_search = normalize_search_appearances(search_appearances)

    print(
        f"  keywords (deduped): {len(deduped_kw['deduped'])} "
        f"(review: {len(deduped_kw['requires_review_keys'])})"
    )
    print(
        f"  categories (deduped): {len(deduped_cat['deduped'])}"
    )
    print(
        f"  brands (deduped): {len(deduped_brand['deduped'])}"
    )
    print(
        f"  sellers (deduped): {len(deduped_seller['deduped'])}"
    )
    print(
        f"  products (deduped): {len(norm_products.deduped_products)} "
        f"(dup groups: {len(norm_products.duplicate_groups)}, "
        f"parent/child: {len(norm_products.parent_child_relations)})"
    )
    print(
        f"  search (no dedup): {norm_search.total_count} appearances, "
        f"{norm_search.unique_asin_count} unique ASINs, "
        f"{norm_search.unique_keyword_count} keywords"
    )

    # --- Run analyzers ------------------------------------------------------
    print("\n[3] Running V3.1.3 analyzers")

    print("\n[3.1] Multi-keyword analysis")
    kw_analysis = analyze_keywords(deduped_kw["deduped"])
    _print_section(
        "Keyword analysis summary",
        kw_analysis.to_dict(),
        max_lines=20,
    )

    print("\n[3.2] Multi-category analysis")
    cat_analysis = analyze_categories(deduped_cat["deduped"])
    _print_section(
        "Category analysis summary",
        cat_analysis.to_dict(),
        max_lines=20,
    )

    print("\n[3.3] Brand analysis")
    brand_analysis = analyze_brands(
        deduped_brand["deduped"],
        products=norm_products.deduped_products,
    )
    _print_section(
        "Brand analysis summary",
        brand_analysis.to_dict(),
        max_lines=20,
    )

    print("\n[3.4] Seller analysis")
    seller_analysis = analyze_sellers(
        deduped_seller["deduped"],
        products=norm_products.deduped_products,
    )
    _print_section(
        "Seller analysis summary",
        seller_analysis.to_dict(),
        max_lines=20,
    )

    print("\n[3.5] Search-position analysis")
    sp_analysis = analyze_search_positions(norm_search.appearances)
    _print_section(
        "Search-position analysis summary",
        sp_analysis.to_dict(),
        max_lines=20,
    )

    print("\n" + "=" * 70)
    print("Demo complete.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
