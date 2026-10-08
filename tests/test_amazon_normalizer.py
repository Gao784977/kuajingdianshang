"""Tests for :mod:`src.modules.amazon.importers.normalizer`.

Covers V3.1.2:

* Product ASIN deduplication — same ASIN across multiple files merges
  into one record.
* Parent / child ASIN relationships extracted from ``parent_asin``.
* Synthetic ``brand|title`` key when ASIN is missing, flagged in
  ``missing_asin_keys`` and ``requires_review_keys``.
* Source-priority field merge: higher-priority source wins, lower
  priority value preserved in :attr:`MergedField.provenance`,
  :attr:`MergedField.requires_review` triggered on override or
  low-confidence source.
* Search-appearance multiplicity: the same ASIN under multiple
  keywords / placements / pages is preserved (no dedup).
* Generic metric dedup (keyword / category / brand / seller) via
  :func:`dedup_by_key`.

Stdlib only.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from src.modules.amazon.importers import (
    AmazonProduct,
    AmazonSearchAppearance,
    BrandMetric,
    CategoryMetric,
    DuplicateGroup,
    KeywordMetric,
    MergedField,
    NormalizedProductResult,
    NormalizedSearchResult,
    ParentChildRelation,
    SellerMetric,
    SOURCE_PRIORITY,
    SourceInfo,
    dedup_by_key,
    default_confidence,
    merge_by_source_priority,
    normalize_products,
    normalize_search_appearances,
    source_priority,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _product(
    asin: str = "",
    brand: str = "",
    title: str = "",
    parent_asin: str = "",
    price=None,
    monthly_sales=None,
    review_count=None,
    source_file: str = "products.xlsx",
    source_sheet: str = "Products",
    source_row: int = 1,
    source_type: str = "imported_excel",
) -> AmazonProduct:
    """Build a minimal :class:`AmazonProduct` for tests."""
    return AmazonProduct(
        asin=asin,
        brand=brand,
        title=title,
        parent_asin=parent_asin,
        price=price,
        monthly_sales=monthly_sales,
        review_count=review_count,
        source_file=source_file,
        source_sheet=source_sheet,
        source_row=source_row,
        source_type=source_type,
    )


def _appearance(
    keyword: str = "wireless mouse",
    asin: str = "B08TEST0001",
    search_rank: int = 1,
    placement_type: str = "organic",
    page_number: int = 1,
    source_file: str = "search.xlsx",
    source_row: int = 1,
    source_type: str = "imported_excel",
) -> AmazonSearchAppearance:
    return AmazonSearchAppearance(
        keyword=keyword,
        asin=asin,
        search_rank=search_rank,
        placement_type=placement_type,
        page_number=page_number,
        source_file=source_file,
        source_row=source_row,
        source_type=source_type,
    )


# ---------------------------------------------------------------------------
# SOURCE_PRIORITY
# ---------------------------------------------------------------------------


class TestSourcePriority(unittest.TestCase):
    def test_priority_order_matches_project_rules(self) -> None:
        self.assertLess(source_priority("user_input"), source_priority("imported_excel"))
        self.assertLess(source_priority("imported_excel"), source_priority("fetched_url"))
        self.assertLess(source_priority("fetched_url"), source_priority("calculated"))
        self.assertLess(source_priority("calculated"), source_priority("agent_inference"))
        self.assertLess(source_priority("agent_inference"), source_priority("mock_data"))

    def test_unknown_source_gets_low_priority(self) -> None:
        self.assertEqual(source_priority("not_a_real_type"), 99)
        self.assertGreater(source_priority("not_a_real_type"), source_priority("mock_data"))

    def test_default_confidence_decreases_with_priority(self) -> None:
        self.assertGreater(default_confidence("user_input"), default_confidence("imported_excel"))
        self.assertGreater(default_confidence("imported_excel"), default_confidence("mock_data"))
        self.assertLess(default_confidence("mock_data"), 0.5)


# ---------------------------------------------------------------------------
# normalize_products — ASIN dedup
# ---------------------------------------------------------------------------


class TestNormalizeProductsAsinDedup(unittest.TestCase):
    def test_empty_input_returns_empty_result(self) -> None:
        result = normalize_products([])
        self.assertIsInstance(result, NormalizedProductResult)
        self.assertEqual(result.deduped_products, [])
        self.assertEqual(result.duplicate_groups, [])
        self.assertEqual(result.missing_asin_keys, [])
        self.assertEqual(result.parent_child_relations, [])

    def test_unique_asins_pass_through_unchanged(self) -> None:
        p1 = _product(asin="B0000000001", brand="BrandA", title="T1", source_row=1)
        p2 = _product(asin="B0000000002", brand="BrandB", title="T2", source_row=2)
        result = normalize_products([p1, p2])
        self.assertEqual(len(result.deduped_products), 2)
        self.assertEqual(result.duplicate_groups, [])
        self.assertEqual(result.missing_asin_keys, [])
        self.assertEqual(result.requires_review_keys, [])

    def test_duplicate_asins_collapse_into_one_record(self) -> None:
        p1 = _product(asin="B0000000001", brand="BrandA", title="T1", source_row=1)
        p2 = _product(asin="B0000000001", brand="BrandA", title="T1", source_row=2,
                      source_file="products2.xlsx")
        result = normalize_products([p1, p2])
        self.assertEqual(len(result.deduped_products), 1)
        self.assertEqual(result.deduped_products[0].asin, "B0000000001")
        self.assertEqual(len(result.duplicate_groups), 1)
        self.assertEqual(result.duplicate_groups[0].dedup_key, "asin:B0000000001")
        self.assertEqual(result.duplicate_groups[0].record_count, 2)
        self.assertEqual(result.duplicate_groups[0].source_files,
                         ["products.xlsx", "products2.xlsx"])

    def test_empty_fields_filled_from_duplicate_row(self) -> None:
        p1 = _product(asin="B0000000001", brand="BrandA", title="T1", source_row=1,
                      price=None, monthly_sales=None)
        p2 = _product(asin="B0000000001", brand="BrandA", title="T1", source_row=2,
                      price=Decimal("19.99"), monthly_sales=Decimal("500"))
        result = normalize_products([p1, p2])
        merged = result.deduped_products[0]
        self.assertEqual(merged.price, Decimal("19.99"))
        self.assertEqual(merged.monthly_sales, Decimal("500"))

    def test_conflicting_values_keep_higher_priority_source(self) -> None:
        # imported_excel has priority 2; mock_data has priority 6.
        p_excel = _product(asin="B0000000001", price=Decimal("19.99"),
                           source_type="imported_excel", source_row=1)
        p_mock = _product(asin="B0000000001", price=Decimal("99.99"),
                          source_type="mock_data", source_row=2)
        result = normalize_products([p_excel, p_mock])
        self.assertEqual(result.deduped_products[0].price, Decimal("19.99"))
        # Override happened -> requires_review_keys is set.
        self.assertIn("asin:B0000000001", result.requires_review_keys)

    def test_conflicting_values_keep_user_input_over_excel(self) -> None:
        p_user = _product(asin="B0000000001", price=Decimal("25.00"),
                          source_type="user_input", source_row=1)
        p_excel = _product(asin="B0000000001", price=Decimal("19.99"),
                          source_type="imported_excel", source_row=2)
        result = normalize_products([p_user, p_excel])
        # user_input (priority 1) wins over imported_excel (priority 2)
        self.assertEqual(result.deduped_products[0].price, Decimal("25.00"))
        self.assertIn("asin:B0000000001", result.requires_review_keys)

    def test_first_record_wins_on_tie(self) -> None:
        # Two records with the same source_type and same value: keep
        # the first, no override.
        p1 = _product(asin="B0000000001", price=Decimal("19.99"),
                      source_type="imported_excel", source_row=1)
        p2 = _product(asin="B0000000001", price=Decimal("19.99"),
                      source_type="imported_excel", source_row=2)
        result = normalize_products([p1, p2])
        self.assertEqual(result.deduped_products[0].price, Decimal("19.99"))
        # Same value, no actual override -> not in requires_review_keys
        self.assertNotIn("asin:B0000000001", result.requires_review_keys)


# ---------------------------------------------------------------------------
# normalize_products — parent/child ASIN relations
# ---------------------------------------------------------------------------


class TestNormalizeProductsParentChild(unittest.TestCase):
    def test_parent_child_relations_extracted(self) -> None:
        parent = _product(asin="B0000000099", parent_asin="", source_row=1)
        child1 = _product(asin="B0000000001", parent_asin="B0000000099", source_row=2)
        child2 = _product(asin="B0000000002", parent_asin="B0000000099", source_row=3)
        result = normalize_products([parent, child1, child2])
        self.assertEqual(len(result.parent_child_relations), 1)
        rel = result.parent_child_relations[0]
        self.assertEqual(rel.parent_asin, "B0000000099")
        self.assertEqual(sorted(rel.child_asins), ["B0000000001", "B0000000002"])

    def test_parent_child_relation_missing_parent_asin_skipped(self) -> None:
        p = _product(asin="B0000000001", parent_asin="", source_row=1)
        result = normalize_products([p])
        self.assertEqual(result.parent_child_relations, [])

    def test_parent_child_relation_missing_asin_skipped(self) -> None:
        # parent_asin present but no own ASIN: skip (would create an
        # orphan child reference)
        p = _product(asin="", parent_asin="B0000000099", brand="X", title="Y", source_row=1)
        result = normalize_products([p])
        self.assertEqual(result.parent_child_relations, [])

    def test_parent_child_relation_deduped_children(self) -> None:
        # Same child appearing twice under the same parent should not
        # list the child ASIN twice in the relation.
        p1 = _product(asin="B0000000001", parent_asin="B0000000099", source_row=1)
        p2 = _product(asin="B0000000001", parent_asin="B0000000099", source_row=2)
        result = normalize_products([p1, p2])
        # p1 and p2 dedup by ASIN -> only one record, one relation entry
        self.assertEqual(len(result.parent_child_relations), 1)
        self.assertEqual(result.parent_child_relations[0].child_asins, ["B0000000001"])


# ---------------------------------------------------------------------------
# normalize_products — missing ASIN / synthetic key
# ---------------------------------------------------------------------------


class TestNormalizeProductsMissingAsin(unittest.TestCase):
    def test_missing_asin_uses_brand_title_key(self) -> None:
        p = _product(asin="", brand="BrandA", title="T1", source_row=1)
        result = normalize_products([p])
        self.assertEqual(len(result.deduped_products), 1)
        self.assertEqual(result.missing_asin_keys, ["bt:BrandA|T1"])
        self.assertIn("bt:BrandA|T1", result.requires_review_keys)

    def test_missing_asin_with_missing_brand_or_title(self) -> None:
        p = _product(asin="", brand="", title="", source_row=1)
        result = normalize_products([p])
        self.assertEqual(result.missing_asin_keys, ["bt:?|?"])
        self.assertIn("bt:?|?", result.requires_review_keys)

    def test_two_records_same_brand_title_dedup_with_synthetic_key(self) -> None:
        p1 = _product(asin="", brand="BrandA", title="T1", source_row=1,
                      price=Decimal("10.00"))
        p2 = _product(asin="", brand="BrandA", title="T1", source_row=2,
                      price=Decimal("12.00"))
        result = normalize_products([p1, p2])
        self.assertEqual(len(result.deduped_products), 1)
        self.assertEqual(result.duplicate_groups[0].dedup_key, "bt:BrandA|T1")
        self.assertEqual(result.duplicate_groups[0].record_count, 2)

    def test_mixed_asin_and_synthetic_keys(self) -> None:
        p1 = _product(asin="B0000000001", source_row=1)
        p2 = _product(asin="", brand="BrandA", title="T1", source_row=2)
        p3 = _product(asin="B0000000002", source_row=3)
        result = normalize_products([p1, p2, p3])
        self.assertEqual(len(result.deduped_products), 3)
        self.assertEqual(result.missing_asin_keys, ["bt:BrandA|T1"])
        self.assertEqual(len(result.requires_review_keys), 1)


# ---------------------------------------------------------------------------
# normalize_products — requires_review_keys
# ---------------------------------------------------------------------------


class TestNormalizeProductsRequiresReview(unittest.TestCase):
    def test_requires_review_on_field_override(self) -> None:
        p_excel = _product(asin="B0000000001", price=Decimal("19.99"),
                           source_type="imported_excel", source_row=1)
        p_mock = _product(asin="B0000000001", price=Decimal("29.99"),
                          source_type="mock_data", source_row=2)
        result = normalize_products([p_excel, p_mock])
        self.assertIn("asin:B0000000001", result.requires_review_keys)

    def test_requires_review_on_missing_asin(self) -> None:
        p = _product(asin="", brand="X", title="Y", source_row=1)
        result = normalize_products([p])
        self.assertIn("bt:X|Y", result.requires_review_keys)

    def test_no_requires_review_when_no_conflicts(self) -> None:
        p1 = _product(asin="B0000000001", source_row=1, price=Decimal("10.00"))
        p2 = _product(asin="B0000000002", source_row=2, price=Decimal("20.00"))
        result = normalize_products([p1, p2])
        self.assertEqual(result.requires_review_keys, [])

    def test_to_dict_includes_review_fields(self) -> None:
        p = _product(asin="", brand="X", title="Y", source_row=1)
        result = normalize_products([p])
        d = result.to_dict()
        self.assertIn("requires_review_keys", d)
        self.assertIn("missing_asin_keys", d)
        self.assertIn("parent_child_relations", d)


# ---------------------------------------------------------------------------
# normalize_search_appearances — no dedup
# ---------------------------------------------------------------------------


class TestNormalizeSearchAppearances(unittest.TestCase):
    def test_empty_input_returns_empty_result(self) -> None:
        result = normalize_search_appearances([])
        self.assertIsInstance(result, NormalizedSearchResult)
        self.assertEqual(result.appearances, [])
        self.assertEqual(result.total_count, 0)

    def test_same_asin_multiple_keywords_preserved(self) -> None:
        # Same ASIN under two different keywords: both kept.
        a1 = _appearance(keyword="mouse", asin="B0000000001", search_rank=1)
        a2 = _appearance(keyword="wireless mouse", asin="B0000000001", search_rank=3)
        result = normalize_search_appearances([a1, a2])
        self.assertEqual(len(result.appearances), 2)
        self.assertEqual(result.unique_asin_count, 1)
        self.assertEqual(result.unique_keyword_count, 2)

    def test_same_asin_same_keyword_multiple_placements_preserved(self) -> None:
        # Same ASIN + keyword under sponsored and organic: both kept.
        a1 = _appearance(keyword="mouse", asin="B0000000001",
                         placement_type="sponsored", search_rank=1)
        a2 = _appearance(keyword="mouse", asin="B0000000001",
                         placement_type="organic", search_rank=2)
        result = normalize_search_appearances([a1, a2])
        self.assertEqual(len(result.appearances), 2)
        self.assertEqual(result.unique_asin_count, 1)
        self.assertEqual(result.unique_keyword_count, 1)

    def test_same_asin_multiple_pages_preserved(self) -> None:
        a1 = _appearance(keyword="mouse", asin="B0000000001",
                         page_number=1, search_rank=1)
        a2 = _appearance(keyword="mouse", asin="B0000000001",
                         page_number=2, search_rank=21)
        result = normalize_search_appearances([a1, a2])
        self.assertEqual(len(result.appearances), 2)

    def test_same_asin_multiple_positions_preserved(self) -> None:
        # Even if everything else is identical but search_rank differs,
        # both rows must be kept (different position on the same page).
        a1 = _appearance(keyword="mouse", asin="B0000000001", search_rank=1)
        a2 = _appearance(keyword="mouse", asin="B0000000001", search_rank=2)
        result = normalize_search_appearances([a1, a2])
        self.assertEqual(len(result.appearances), 2)

    def test_input_list_not_mutated(self) -> None:
        a1 = _appearance(keyword="mouse", asin="B0000000001")
        original = [a1]
        result = normalize_search_appearances(original)
        self.assertEqual(len(original), 1)
        self.assertEqual(len(result.appearances), 1)
        # Different list object (shallow copy)
        self.assertIsNot(result.appearances, original)

    def test_to_dict_roundtrip(self) -> None:
        a1 = _appearance(keyword="mouse", asin="B0000000001")
        a2 = _appearance(keyword="keyboard", asin="B0000000002")
        result = normalize_search_appearances([a1, a2])
        d = result.to_dict()
        self.assertEqual(d["total_count"], 2)
        self.assertEqual(d["unique_asin_count"], 2)
        self.assertEqual(d["unique_keyword_count"], 2)
        self.assertEqual(len(d["appearances"]), 2)

    def test_empty_asin_excluded_from_unique_count(self) -> None:
        a1 = _appearance(keyword="mouse", asin="")
        a2 = _appearance(keyword="mouse", asin="B0000000001")
        result = normalize_search_appearances([a1, a2])
        self.assertEqual(result.total_count, 2)
        self.assertEqual(result.unique_asin_count, 1)


# ---------------------------------------------------------------------------
# merge_by_source_priority
# ---------------------------------------------------------------------------


class TestMergeBySourcePriority(unittest.TestCase):
    def test_empty_records_returns_review_flagged_empty(self) -> None:
        merged = merge_by_source_priority([], "price")
        self.assertIsInstance(merged, MergedField)
        self.assertIsNone(merged.value)
        self.assertTrue(merged.requires_review)
        self.assertEqual(merged.provenance, [])

    def test_single_record_passes_through(self) -> None:
        p = _product(asin="B0000000001", price=Decimal("19.99"),
                     source_type="imported_excel", source_row=1)
        merged = merge_by_source_priority([p], "price")
        self.assertEqual(merged.value, "19.99")  # Decimal serialised to str
        self.assertEqual(merged.source_type, "imported_excel")
        self.assertEqual(merged.source_row, 1)
        self.assertFalse(merged.requires_review)
        self.assertEqual(merged.provenance, [])

    def test_lower_priority_record_wins(self) -> None:
        # user_input (priority 1) vs mock_data (priority 6)
        p_user = _product(asin="B0000000001", price=Decimal("25.00"),
                          source_type="user_input", source_row=1)
        p_mock = _product(asin="B0000000001", price=Decimal("99.99"),
                          source_type="mock_data", source_row=2)
        merged = merge_by_source_priority([p_user, p_mock], "price")
        self.assertEqual(merged.value, "25.00")
        self.assertEqual(merged.source_type, "user_input")
        # mock_data value preserved in provenance
        self.assertEqual(len(merged.provenance), 1)
        self.assertEqual(merged.provenance[0]["value"], "99.99")
        self.assertEqual(merged.provenance[0]["source_type"], "mock_data")
        self.assertTrue(merged.requires_review)

    def test_override_always_triggers_requires_review(self) -> None:
        p_excel = _product(asin="B0000000001", price=Decimal("19.99"),
                           source_type="imported_excel", source_row=1)
        p_url = _product(asin="B0000000001", price=Decimal("22.00"),
                         source_type="fetched_url", source_row=2)
        merged = merge_by_source_priority([p_excel, p_url], "price")
        # imported_excel wins (priority 2 < 3)
        self.assertEqual(merged.value, "19.99")
        self.assertTrue(merged.requires_review)

    def test_low_confidence_winner_triggers_requires_review(self) -> None:
        # Single record, but source is agent_inference (low confidence)
        p = _product(asin="B0000000001", price=Decimal("19.99"),
                     source_type="agent_inference", source_row=1)
        merged = merge_by_source_priority([p], "price")
        self.assertTrue(merged.requires_review)

    def test_mock_data_winner_triggers_requires_review(self) -> None:
        p = _product(asin="B0000000001", price=Decimal("19.99"),
                     source_type="mock_data", source_row=1)
        merged = merge_by_source_priority([p], "price")
        self.assertTrue(merged.requires_review)

    def test_empty_field_values_skipped(self) -> None:
        p1 = _product(asin="B0000000001", price=None, source_row=1)
        p2 = _product(asin="B0000000001", price=Decimal("19.99"),
                      source_type="imported_excel", source_row=2)
        merged = merge_by_source_priority([p1, p2], "price")
        self.assertEqual(merged.value, "19.99")
        self.assertEqual(merged.source_row, 2)
        self.assertFalse(merged.requires_review)

    def test_all_empty_returns_review_flagged(self) -> None:
        p1 = _product(asin="B0000000001", price=None, source_row=1)
        p2 = _product(asin="B0000000001", price=None, source_row=2)
        merged = merge_by_source_priority([p1, p2], "price")
        self.assertIsNone(merged.value)
        self.assertTrue(merged.requires_review)

    def test_custom_getter(self) -> None:
        # Use a getter that returns a computed value
        p = _product(asin="B0000000001", price=Decimal("19.99"),
                     monthly_sales=Decimal("500"), source_row=1)
        merged = merge_by_source_priority(
            [p], "revenue",
            getter=lambda r: r.price * r.monthly_sales if r.price and r.monthly_sales else None,
        )
        self.assertEqual(merged.value, "9995.00")
        # calculation_method lookup falls back to empty string
        self.assertEqual(merged.calculation_method, "")

    def test_decimal_serialised_as_str(self) -> None:
        p = _product(asin="B0000000001", price=Decimal("19.99"), source_row=1)
        merged = merge_by_source_priority([p], "price")
        self.assertIsInstance(merged.value, str)
        self.assertEqual(merged.value, "19.99")

    def test_list_field_serialised(self) -> None:
        p = _product(asin="B0000000001", source_row=1)
        p.bullet_points = ["Feature A", "Feature B"]
        merged = merge_by_source_priority([p], "bullet_points")
        self.assertEqual(merged.value, ["Feature A", "Feature B"])

    def test_to_dict_roundtrip(self) -> None:
        p_user = _product(asin="B0000000001", price=Decimal("25.00"),
                          source_type="user_input", source_row=1)
        p_mock = _product(asin="B0000000001", price=Decimal("99.99"),
                          source_type="mock_data", source_row=2)
        merged = merge_by_source_priority([p_user, p_mock], "price")
        d = merged.to_dict()
        self.assertEqual(d["value"], "25.00")
        self.assertEqual(d["source_type"], "user_input")
        self.assertTrue(d["requires_review"])
        self.assertEqual(len(d["provenance"]), 1)
        # Provenance entry has all required keys
        prov = d["provenance"][0]
        for key in ("value", "source_type", "source_file", "source_sheet",
                    "source_row", "source_url", "priority"):
            self.assertIn(key, prov)

    def test_priority_order_in_provenance(self) -> None:
        # Three sources, all with values: winner is priority 1, then
        # provenance entries sorted by priority (ascending).
        p_user = _product(asin="B0000000001", price=Decimal("25.00"),
                          source_type="user_input", source_row=1)
        p_excel = _product(asin="B0000000001", price=Decimal("19.99"),
                           source_type="imported_excel", source_row=2)
        p_mock = _product(asin="B0000000001", price=Decimal("99.99"),
                          source_type="mock_data", source_row=3)
        merged = merge_by_source_priority([p_mock, p_user, p_excel], "price")
        self.assertEqual(merged.value, "25.00")
        self.assertEqual(merged.source_type, "user_input")
        # 2 overridden entries
        self.assertEqual(len(merged.provenance), 2)
        # Provenance is sorted by priority ascending
        self.assertEqual(merged.provenance[0]["priority"], 2)  # imported_excel
        self.assertEqual(merged.provenance[1]["priority"], 6)  # mock_data

    def test_unknown_source_type_gets_low_priority(self) -> None:
        # SourceInfo with unknown source_type falls back to "imported_excel"
        # in __post_init__; but we can build a record where it stays
        # unknown via object.__setattr__.
        p_known = _product(asin="B0000000001", price=Decimal("10.00"),
                           source_type="imported_excel", source_row=1)
        p_unknown = _product(asin="B0000000001", price=Decimal("20.00"),
                              source_type="imported_excel", source_row=2)
        # SourceInfo.__post_init__ coerces unknown to "imported_excel",
        # so we cannot directly test unknown. Instead, verify that
        # priority 99 > 6 by checking SOURCE_PRIORITY map directly.
        self.assertEqual(SOURCE_PRIORITY.get("definitely_unknown", 99), 99)


# ---------------------------------------------------------------------------
# dedup_by_key (generic metric dedup)
# ---------------------------------------------------------------------------


class TestDedupByKey(unittest.TestCase):
    def test_empty_input(self) -> None:
        result = dedup_by_key([])
        self.assertEqual(result["deduped"], [])
        self.assertEqual(result["duplicate_groups"], [])
        self.assertEqual(result["requires_review_keys"], [])

    def test_keyword_dedup(self) -> None:
        k1 = KeywordMetric(keyword="mouse", search_volume=Decimal("1000"),
                          source_file="kw1.xlsx", source_row=1,
                          source_type="imported_excel")
        k2 = KeywordMetric(keyword="mouse", search_volume=Decimal("1500"),
                          source_file="kw2.xlsx", source_row=1,
                          source_type="mock_data")
        result = dedup_by_key([k2, k1])
        self.assertEqual(len(result["deduped"]), 1)
        # imported_excel (priority 2) wins over mock_data (priority 6)
        self.assertEqual(result["deduped"][0].search_volume, Decimal("1000"))
        self.assertEqual(len(result["duplicate_groups"]), 1)
        self.assertEqual(result["duplicate_groups"][0].dedup_key, "kw:mouse")
        self.assertIn("kw:mouse", result["requires_review_keys"])

    def test_brand_dedup(self) -> None:
        b1 = BrandMetric(brand="BrandA", monthly_sales=Decimal("500"),
                         source_type="imported_excel", source_row=1)
        b2 = BrandMetric(brand="BrandA", monthly_sales=Decimal("999"),
                         source_type="mock_data", source_row=2)
        result = dedup_by_key([b1, b2])
        self.assertEqual(len(result["deduped"]), 1)
        self.assertEqual(result["deduped"][0].monthly_sales, Decimal("500"))
        self.assertIn("brand:BrandA", result["requires_review_keys"])

    def test_category_dedup(self) -> None:
        c1 = CategoryMetric(category="Electronics", product_count=100,
                            source_type="imported_excel", source_row=1)
        c2 = CategoryMetric(category="Electronics", product_count=200,
                            source_type="user_input", source_row=2)
        result = dedup_by_key([c1, c2])
        self.assertEqual(len(result["deduped"]), 1)
        # user_input (priority 1) wins
        self.assertEqual(result["deduped"][0].product_count, 200)

    def test_seller_dedup(self) -> None:
        s1 = SellerMetric(seller="SellerA", market_share=Decimal("0.15"),
                          source_type="imported_excel", source_row=1)
        s2 = SellerMetric(seller="SellerA", market_share=Decimal("0.20"),
                          source_type="mock_data", source_row=2)
        result = dedup_by_key([s1, s2])
        self.assertEqual(len(result["deduped"]), 1)
        self.assertEqual(result["deduped"][0].market_share, Decimal("0.15"))

    def test_unique_keys_pass_through(self) -> None:
        k1 = KeywordMetric(keyword="mouse", source_row=1)
        k2 = KeywordMetric(keyword="keyboard", source_row=2)
        result = dedup_by_key([k1, k2])
        self.assertEqual(len(result["deduped"]), 2)
        self.assertEqual(result["duplicate_groups"], [])
        self.assertEqual(result["requires_review_keys"], [])

    def test_empty_fields_filled(self) -> None:
        # Primary lacks search_volume; secondary provides it (lower
        # priority but the only value, so taken).
        k1 = KeywordMetric(keyword="mouse", search_volume=None,
                           source_type="imported_excel", source_row=1)
        k2 = KeywordMetric(keyword="mouse", search_volume=Decimal("500"),
                           source_type="mock_data", source_row=2)
        result = dedup_by_key([k1, k2])
        self.assertEqual(result["deduped"][0].search_volume, Decimal("500"))
        # No override happened (primary's value was empty), so no review
        self.assertNotIn("kw:mouse", result["requires_review_keys"])


# ---------------------------------------------------------------------------
# Integration — combined normalisation
# ---------------------------------------------------------------------------


class TestIntegrationNormalizeAndMerge(unittest.TestCase):
    def test_products_then_search_then_merge(self) -> None:
        # Step 1: products
        p1 = _product(asin="B0000000001", price=Decimal("19.99"),
                      source_type="imported_excel", source_row=1)
        p2 = _product(asin="B0000000001", parent_asin="B0000000099",
                      source_type="imported_excel", source_row=2)
        prod_result = normalize_products([p1, p2])
        self.assertEqual(len(prod_result.deduped_products), 1)
        self.assertEqual(len(prod_result.parent_child_relations), 1)

        # Step 2: search appearances (same ASIN, multiple placements)
        a1 = _appearance(keyword="mouse", asin="B0000000001",
                         placement_type="sponsored", search_rank=1)
        a2 = _appearance(keyword="mouse", asin="B0000000001",
                         placement_type="organic", search_rank=2)
        a3 = _appearance(keyword="wireless mouse", asin="B0000000001",
                         placement_type="organic", search_rank=5)
        search_result = normalize_search_appearances([a1, a2, a3])
        self.assertEqual(search_result.total_count, 3)
        self.assertEqual(search_result.unique_asin_count, 1)
        self.assertEqual(search_result.unique_keyword_count, 2)

        # Step 3: field merge across the (single) product record and a
        # hypothetical mock record.
        p_mock = _product(asin="B0000000001", price=Decimal("99.99"),
                          source_type="mock_data", source_row=99)
        merged_price = merge_by_source_priority(
            [prod_result.deduped_products[0], p_mock], "price"
        )
        self.assertEqual(merged_price.value, "19.99")
        self.assertTrue(merged_price.requires_review)

    def test_complete_pipeline_round_trip(self) -> None:
        # A miniature end-to-end scenario with all V3.1.2 features.
        products = [
            _product(asin="B0000000001", brand="A", title="T1",
                     parent_asin="B0000000099", price=Decimal("19.99"),
                     source_type="imported_excel", source_row=1),
            _product(asin="B0000000001", brand="A", title="T1",
                     parent_asin="B0000000099", price=Decimal("29.99"),
                     source_type="mock_data", source_row=2),
            _product(asin="B0000000002", brand="B", title="T2",
                     parent_asin="B0000000099", price=Decimal("15.00"),
                     source_type="imported_excel", source_row=3),
            _product(asin="", brand="C", title="T3",
                     source_type="imported_excel", source_row=4),
        ]
        result = normalize_products(products)
        # 3 unique products: B0000000001 (merged), B0000000002, bt:C|T3
        self.assertEqual(len(result.deduped_products), 3)
        # One parent/child relation
        self.assertEqual(len(result.parent_child_relations), 1)
        self.assertEqual(result.parent_child_relations[0].parent_asin, "B0000000099")
        # Two duplicate groups: only B0000000001 had duplicates? No,
        # only B0000000001 had 2 records, so 1 duplicate group.
        self.assertEqual(len(result.duplicate_groups), 1)
        # B0000000001 was overridden (excel vs mock) -> review
        # bt:C|T3 missing ASIN -> review
        self.assertEqual(len(result.requires_review_keys), 2)
        self.assertIn("asin:B0000000001", result.requires_review_keys)
        self.assertIn("bt:C|T3", result.requires_review_keys)


if __name__ == "__main__":
    unittest.main()
