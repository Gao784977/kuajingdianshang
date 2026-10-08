"""Tests for the V3.1.3 analyzers.

Covers:

* :func:`analyze_keywords`           — multi-keyword ranking + opportunity score
* :func:`analyze_categories`         — cross-category comparison
* :func:`analyze_brands`             — CR4/CR8/HHI + new-brand opportunities
* :func:`analyze_sellers`            — seller concentration + FBA/FBM
* :func:`analyze_search_positions`   — keyword x ASIN matrix

All tests construct typed records directly (no Excel loading) so the
suite is deterministic and runs without openpyxl.
"""

from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from src.modules.amazon.importers.normalized_models import (
    AmazonProduct,
    AmazonSearchAppearance,
    BrandMetric,
    CategoryMetric,
    KeywordMetric,
    SellerMetric,
)
from src.modules.amazon.analyzers import (
    analyze_brands,
    analyze_categories,
    analyze_keywords,
    analyze_search_positions,
    analyze_sellers,
)
from src.modules.amazon.analyzers.seller_analysis import _classify_fulfillment


def _kw(
    keyword: str,
    search_volume=None,
    click_share=None,
    conversion_share=None,
    competition="",
    source_file="",
    source_type="imported_excel",
):
    return KeywordMetric(
        keyword=keyword,
        search_volume=search_volume,
        click_share=click_share,
        conversion_share=conversion_share,
        competition=competition,
        source_file=source_file,
        source_type=source_type,
    )


def _cat(
    category: str,
    market_revenue=None,
    growth=None,
    competition="",
    source_file="",
    source_type="imported_excel",
):
    return CategoryMetric(
        category=category,
        market_revenue=market_revenue,
        growth=growth,
        competition=competition,
        source_file=source_file,
        source_type=source_type,
    )


def _brand(
    brand: str,
    market_share=None,
    monthly_revenue=None,
    monthly_sales=None,
    source_file="",
    source_type="imported_excel",
):
    return BrandMetric(
        brand=brand,
        market_share=market_share,
        monthly_revenue=monthly_revenue,
        monthly_sales=monthly_sales,
        source_file=source_file,
        source_type=source_type,
    )


def _seller(
    seller: str,
    market_share=None,
    monthly_revenue=None,
    monthly_sales=None,
    source_file="",
    source_type="imported_excel",
):
    return SellerMetric(
        seller=seller,
        market_share=market_share,
        monthly_revenue=monthly_revenue,
        monthly_sales=monthly_sales,
        source_file=source_file,
        source_type=source_type,
    )


def _appearance(
    keyword="kw",
    asin="A1",
    placement_type="organic",
    placement_detail="",
    is_sponsored=False,
    is_organic=False,
    page_number=None,
    source_file="",
    source_type="imported_excel",
):
    return AmazonSearchAppearance(
        keyword=keyword,
        asin=asin,
        placement_type=placement_type,
        placement_detail=placement_detail,
        is_sponsored=is_sponsored,
        is_organic=is_organic,
        page_number=page_number,
        source_file=source_file,
        source_type=source_type,
    )


def _product(
    asin="A1",
    brand="BrandA",
    fulfillment_method="",
    seller_location="",
    launch_date=None,
    source_file="",
    source_type="imported_excel",
):
    return AmazonProduct(
        asin=asin,
        brand=brand,
        fulfillment_method=fulfillment_method,
        seller_location=seller_location,
        launch_date=launch_date,
        source_file=source_file,
        source_type=source_type,
    )


# ===========================================================================
# Multi-keyword analyzer
# ===========================================================================


class TestMultiKeywordAnalyzer(unittest.TestCase):

    def test_empty_input_returns_empty_result(self):
        result = analyze_keywords([])
        self.assertEqual(result.total_keywords, 0)
        self.assertEqual(result.rankings, [])
        self.assertIsNone(result.total_search_volume)
        self.assertFalse(result.requires_review)

    def test_single_keyword_ranks_first(self):
        kms = [_kw("solo", Decimal("1000"), Decimal("0.1"), Decimal("0.05"), "low")]
        result = analyze_keywords(kms)
        self.assertEqual(result.total_keywords, 1)
        self.assertEqual(result.rankings[0].keyword, "solo")
        self.assertEqual(result.rankings[0].rank_by_search_volume, 1)
        self.assertEqual(result.rankings[0].rank_by_click_share, 1)
        self.assertEqual(result.rankings[0].rank_by_conversion_share, 1)

    def test_ranking_by_search_volume_descending(self):
        kms = [
            _kw("low", Decimal("100")),
            _kw("high", Decimal("900")),
            _kw("mid", Decimal("500")),
        ]
        result = analyze_keywords(kms)
        ranks = {r.keyword: r.rank_by_search_volume for r in result.rankings}
        self.assertEqual(ranks["high"], 1)
        self.assertEqual(ranks["mid"], 2)
        self.assertEqual(ranks["low"], 3)

    def test_ranking_by_click_share_descending(self):
        kms = [
            _kw("a", click_share=Decimal("0.05")),
            _kw("b", click_share=Decimal("0.20")),
            _kw("c", click_share=Decimal("0.10")),
        ]
        result = analyze_keywords(kms)
        ranks = {r.keyword: r.rank_by_click_share for r in result.rankings}
        self.assertEqual(ranks["b"], 1)
        self.assertEqual(ranks["c"], 2)
        self.assertEqual(ranks["a"], 3)

    def test_ranking_by_conversion_share_descending(self):
        kms = [
            _kw("a", conversion_share=Decimal("0.01")),
            _kw("b", conversion_share=Decimal("0.15")),
        ]
        result = analyze_keywords(kms)
        ranks = {r.keyword: r.rank_by_conversion_share for r in result.rankings}
        self.assertEqual(ranks["b"], 1)
        self.assertEqual(ranks["a"], 2)

    def test_opportunity_score_capped_at_100(self):
        # Max on every axis + low competition -> base 100 * 1.2 = 120,
        # but the cap should bring it back to 100.
        kms = [
            _kw(
                "perfect",
                Decimal("1000"),
                Decimal("0.5"),
                Decimal("0.5"),
                "low",
            )
        ]
        result = analyze_keywords(kms)
        self.assertEqual(result.rankings[0].opportunity_score, Decimal("100"))

    def test_high_potential_threshold_default(self):
        # low competition + max volume + max click + max conv -> 100.
        kms = [
            _kw("good", Decimal("1000"), Decimal("0.5"), Decimal("0.5"), "low"),
            _kw("bad", Decimal("10"), Decimal("0.01"), Decimal("0.01"), "high"),
        ]
        result = analyze_keywords(kms)
        high = {r.keyword for r in result.high_potential_keywords}
        self.assertIn("good", high)
        self.assertNotIn("bad", high)

    def test_high_potential_threshold_override(self):
        kms = [
            _kw("a", Decimal("1000"), Decimal("0.5"), Decimal("0.5"), "low"),
        ]
        result = analyze_keywords(kms, high_potential_threshold=Decimal("150"))
        # Score capped at 100 < 150 threshold -> no high-potential entries.
        self.assertEqual(result.high_potential_keywords, [])

    def test_missing_competition_flags_review(self):
        kms = [_kw("x", Decimal("100"), competition="")]
        result = analyze_keywords(kms)
        self.assertTrue(result.rankings[0].requires_review)
        self.assertTrue(result.requires_review)

    def test_low_confidence_source_flags_review(self):
        kms = [
            _kw(
                "x",
                Decimal("100"),
                competition="low",
                source_type="mock_data",
            )
        ]
        result = analyze_keywords(kms)
        self.assertTrue(result.rankings[0].requires_review)
        self.assertTrue(result.requires_review)

    def test_user_input_source_does_not_flag_review(self):
        kms = [
            _kw(
                "x",
                Decimal("100"),
                competition="low",
                source_type="user_input",
            )
        ]
        result = analyze_keywords(kms)
        self.assertFalse(result.rankings[0].requires_review)

    def test_source_files_propagated(self):
        kms = [
            _kw("a", Decimal("100"), source_file="kw1.xlsx"),
            _kw("b", Decimal("200"), source_file="kw2.xlsx"),
        ]
        result = analyze_keywords(kms)
        self.assertEqual(result.source_files, ["kw1.xlsx", "kw2.xlsx"])
        # Rankings are sorted by opportunity_score desc, so the
        # higher-volume keyword "b" comes first.
        self.assertEqual(result.rankings[0].keyword, "b")
        self.assertEqual(result.rankings[0].source_files, ["kw2.xlsx"])

    def test_aggregates_total_volume(self):
        kms = [
            _kw("a", Decimal("100")),
            _kw("b", Decimal("200")),
            _kw("c", Decimal("300")),
        ]
        result = analyze_keywords(kms)
        self.assertEqual(result.total_search_volume, Decimal("600"))

    def test_aggregates_avg_click_share(self):
        kms = [
            _kw("a", click_share=Decimal("0.10")),
            _kw("b", click_share=Decimal("0.30")),
        ]
        result = analyze_keywords(kms)
        self.assertEqual(result.avg_click_share, Decimal("0.20"))

    def test_aggregates_avg_conversion_share_ignores_missing(self):
        kms = [
            _kw("a", conversion_share=Decimal("0.10")),
            _kw("b"),  # no conversion_share
            _kw("c", conversion_share=Decimal("0.20")),
        ]
        result = analyze_keywords(kms)
        self.assertEqual(result.avg_conversion_share, Decimal("0.15"))

    def test_tie_ranking_shares_rank(self):
        # Two keywords with the same search_volume should share rank 1.
        kms = [
            _kw("a", Decimal("500")),
            _kw("b", Decimal("500")),
            _kw("c", Decimal("100")),
        ]
        result = analyze_keywords(kms)
        ranks = {r.keyword: r.rank_by_search_volume for r in result.rankings}
        self.assertEqual(ranks["a"], 1)
        self.assertEqual(ranks["b"], 1)
        self.assertEqual(ranks["c"], 3)

    def test_to_dict_round_trip(self):
        kms = [_kw("a", Decimal("100"), competition="low", source_file="x.xlsx")]
        d = analyze_keywords(kms).to_dict()
        self.assertEqual(d["total_keywords"], 1)
        self.assertEqual(d["rankings"][0]["keyword"], "a")
        self.assertEqual(d["rankings"][0]["source_files"], ["x.xlsx"])
        self.assertIn("opportunity_score", d["rankings"][0])


# ===========================================================================
# Multi-category analyzer
# ===========================================================================


class TestMultiCategoryAnalyzer(unittest.TestCase):

    def test_empty_input(self):
        result = analyze_categories([])
        self.assertEqual(result.total_categories, 0)
        self.assertEqual(result.comparisons, [])
        self.assertFalse(result.requires_review)

    def test_market_capacity_rank_by_revenue(self):
        cats = [
            _cat("low", market_revenue=Decimal("1000")),
            _cat("high", market_revenue=Decimal("9000")),
            _cat("mid", market_revenue=Decimal("5000")),
        ]
        result = analyze_categories(cats)
        ranks = {c.category: c.market_capacity_rank for c in result.comparisons}
        self.assertEqual(ranks["high"], 1)
        self.assertEqual(ranks["mid"], 2)
        self.assertEqual(ranks["low"], 3)

    def test_growth_rank_descending(self):
        cats = [
            _cat("a", growth=Decimal("0.05")),
            _cat("b", growth=Decimal("0.20")),
            _cat("c", growth=Decimal("-0.10")),
        ]
        result = analyze_categories(cats)
        ranks = {c.category: c.growth_rank for c in result.comparisons}
        self.assertEqual(ranks["b"], 1)
        self.assertEqual(ranks["a"], 2)
        self.assertEqual(ranks["c"], 3)

    def test_competition_rank_low_is_one(self):
        cats = [
            _cat("high_comp", competition="high"),
            _cat("low_comp", competition="low"),
            _cat("med_comp", competition="medium"),
        ]
        result = analyze_categories(cats)
        ranks = {c.category: c.competition_rank for c in result.comparisons}
        self.assertEqual(ranks["low_comp"], 1)
        self.assertEqual(ranks["med_comp"], 2)
        self.assertEqual(ranks["high_comp"], 3)

    def test_fastest_growing_filters_non_positive(self):
        cats = [
            _cat("growing", growth=Decimal("0.10")),
            _cat("shrinking", growth=Decimal("-0.05")),
            _cat("flat", growth=Decimal("0.00")),
        ]
        result = analyze_categories(cats)
        names = [c.category for c in result.fastest_growing]
        self.assertEqual(names, ["growing"])

    def test_least_competitive_filters_high(self):
        cats = [
            _cat("low", competition="low"),
            _cat("medium", competition="medium"),
            _cat("high", competition="high"),
        ]
        result = analyze_categories(cats)
        names = {c.category for c in result.least_competitive}
        self.assertEqual(names, {"low", "medium"})

    def test_opportunity_score_combines_three_axes(self):
        cats = [
            _cat(
                "best",
                market_revenue=Decimal("10000"),
                growth=Decimal("0.20"),
                competition="low",
            )
        ]
        result = analyze_categories(cats)
        # All axes maxed -> 40 + 40 + 20 = 100.
        self.assertEqual(result.comparisons[0].opportunity_score, Decimal("100"))

    def test_missing_competition_flags_review(self):
        cats = [_cat("x", market_revenue=Decimal("1000"), competition="")]
        result = analyze_categories(cats)
        self.assertTrue(result.comparisons[0].requires_review)
        self.assertTrue(result.requires_review)

    def test_total_market_revenue(self):
        cats = [
            _cat("a", market_revenue=Decimal("100")),
            _cat("b", market_revenue=Decimal("200")),
        ]
        result = analyze_categories(cats)
        self.assertEqual(result.total_market_revenue, Decimal("300"))

    def test_source_files_propagated(self):
        cats = [
            _cat("a", source_file="c1.xlsx"),
            _cat("b", source_file="c2.xlsx"),
        ]
        result = analyze_categories(cats)
        self.assertEqual(result.source_files, ["c1.xlsx", "c2.xlsx"])

    def test_to_dict_round_trip(self):
        cats = [_cat("a", market_revenue=Decimal("100"), competition="low")]
        d = analyze_categories(cats).to_dict()
        self.assertEqual(d["total_categories"], 1)
        self.assertEqual(d["comparisons"][0]["category"], "a")
        self.assertIn("opportunity_score", d["comparisons"][0])


# ===========================================================================
# Brand analysis
# ===========================================================================


class TestBrandAnalysis(unittest.TestCase):

    def test_empty_input(self):
        result = analyze_brands([])
        self.assertEqual(result.total_brands, 0)
        self.assertEqual(result.cr4, None)
        self.assertEqual(result.hhi, None)

    def test_cr4_cr8_hhi_from_market_share(self):
        # 4 brands each with 25% share.
        brands = [
            _brand("A", market_share=Decimal("0.25")),
            _brand("B", market_share=Decimal("0.25")),
            _brand("C", market_share=Decimal("0.25")),
            _brand("D", market_share=Decimal("0.25")),
        ]
        result = analyze_brands(brands)
        self.assertEqual(result.cr4, Decimal("1.0000"))
        self.assertEqual(result.cr8, Decimal("1.0000"))
        # HHI = 4 * 0.25^2 = 0.25 -> 2500 on the DOJ scale.
        self.assertEqual(result.hhi, Decimal("2500.00"))
        self.assertEqual(result.market_concentration, "highly_concentrated")
        self.assertEqual(result.share_basis, "market_share")

    def test_concentration_labels(self):
        # Monopoly: 1 brand 100%.
        monopoly = [_brand("only", market_share=Decimal("1.0"))]
        result = analyze_brands(monopoly)
        self.assertEqual(result.hhi, Decimal("10000.00"))
        self.assertEqual(result.market_concentration, "highly_concentrated")

        # Oligopoly-ish: 2 brands 50/50 -> HHI 5000.
        duo = [
            _brand("a", market_share=Decimal("0.5")),
            _brand("b", market_share=Decimal("0.5")),
        ]
        result = analyze_brands(duo)
        self.assertEqual(result.hhi, Decimal("5000.00"))
        self.assertEqual(result.market_concentration, "highly_concentrated")

        # Fragmented: 10 brands 10% each -> HHI 1000.
        fragmented = [
            _brand(f"b{i}", market_share=Decimal("0.1")) for i in range(10)
        ]
        result = analyze_brands(fragmented)
        self.assertEqual(result.hhi, Decimal("1000.00"))
        self.assertEqual(result.market_concentration, "unconcentrated")

    def test_fallback_to_monthly_revenue(self):
        brands = [
            _brand("a", monthly_revenue=Decimal("800")),
            _brand("b", monthly_revenue=Decimal("200")),
        ]
        result = analyze_brands(brands)
        self.assertEqual(result.share_basis, "monthly_revenue")
        self.assertEqual(result.cr4, Decimal("1.0000"))
        # top4_brands[0] should be the one with revenue 800.
        self.assertEqual(result.top4_brands[0]["brand"], "a")

    def test_fallback_to_monthly_sales(self):
        brands = [
            _brand("a", monthly_sales=Decimal("900")),
            _brand("b", monthly_sales=Decimal("100")),
        ]
        result = analyze_brands(brands)
        self.assertEqual(result.share_basis, "monthly_sales")
        self.assertEqual(result.top4_brands[0]["brand"], "a")

    def test_no_share_data_returns_review(self):
        brands = [_brand("a"), _brand("b")]
        result = analyze_brands(brands)
        self.assertEqual(result.share_basis, "none")
        self.assertTrue(result.requires_review)
        self.assertIsNone(result.cr4)
        self.assertIsNone(result.hhi)

    def test_top4_top8_brands(self):
        brands = [
            _brand(f"b{i}", market_share=Decimal(str(0.1 - i * 0.01)))
            for i in range(10)
        ]
        result = analyze_brands(brands)
        self.assertEqual(len(result.top4_brands), 4)
        self.assertEqual(len(result.top8_brands), 8)
        # Sorted by share desc.
        self.assertEqual(result.top4_brands[0]["brand"], "b0")
        self.assertEqual(result.top4_brands[3]["brand"], "b3")

    def test_new_brand_opportunities_with_products(self):
        brands = [
            _brand("old", market_share=Decimal("0.5")),
            _brand("new", market_share=Decimal("0.01")),
        ]
        # "new" launched 30 days ago -> opportunity.
        # "old" launched 1000 days ago -> filtered.
        products = [
            _product(
                asin="A1",
                brand="old",
                launch_date="2023-01-01",
            ),
            _product(
                asin="A2",
                brand="new",
                launch_date=(date(2024, 1, 1) + __import__("datetime").timedelta(days=-30)).isoformat(),
            ),
        ]
        result = analyze_brands(brands, products=products, today=date(2024, 1, 1))
        opp_brands = [o["brand"] for o in result.new_brand_opportunities]
        self.assertIn("new", opp_brands)
        self.assertNotIn("old", opp_brands)

    def test_no_products_means_no_opportunities(self):
        brands = [_brand("a", market_share=Decimal("0.5"))]
        result = analyze_brands(brands, products=None)
        self.assertEqual(result.new_brand_opportunities, [])

    def test_recent_launch_outside_window_filtered(self):
        # Brand launched 400 days ago -> not an opportunity (window 365).
        brands = [
            _brand("top", market_share=Decimal("0.9")),
            _brand("bot", market_share=Decimal("0.01")),
        ]
        products = [
            _product(brand="bot", launch_date="2023-01-01"),
        ]
        result = analyze_brands(brands, products=products, today=date(2024, 1, 1))
        # 2023-01-01 to 2024-01-01 = 365 days, edge case — use 400 days ago.
        products2 = [
            _product(brand="bot", launch_date="2022-11-01"),  # > 365 days
        ]
        result2 = analyze_brands(brands, products=products2, today=date(2024, 1, 1))
        self.assertEqual(result2.new_brand_opportunities, [])

    def test_source_files_propagated(self):
        brands = [
            _brand("a", market_share=Decimal("0.5"), source_file="b1.xlsx"),
            _brand("b", market_share=Decimal("0.5"), source_file="b2.xlsx"),
        ]
        result = analyze_brands(brands)
        self.assertEqual(result.source_files, ["b1.xlsx", "b2.xlsx"])

    def test_to_dict_round_trip(self):
        brands = [_brand("a", market_share=Decimal("1.0"))]
        d = analyze_brands(brands).to_dict()
        self.assertEqual(d["total_brands"], 1)
        self.assertEqual(d["market_concentration"], "highly_concentrated")
        self.assertIn("hhi", d)


# ===========================================================================
# Seller analysis
# ===========================================================================


class TestSellerAnalysis(unittest.TestCase):

    def test_empty_input(self):
        result = analyze_sellers([])
        self.assertEqual(result.total_sellers, 0)
        self.assertIsNone(result.cr4)

    def test_cr4_cr8_hhi_from_market_share(self):
        sellers = [
            _seller("S1", market_share=Decimal("0.5")),
            _seller("S2", market_share=Decimal("0.3")),
            _seller("S3", market_share=Decimal("0.15")),
            _seller("S4", market_share=Decimal("0.05")),
        ]
        result = analyze_sellers(sellers)
        self.assertEqual(result.cr4, Decimal("1.0000"))
        # HHI = 0.25 + 0.09 + 0.0225 + 0.0025 = 0.365 -> 3650.
        self.assertEqual(result.hhi, Decimal("3650.00"))
        self.assertEqual(result.market_concentration, "highly_concentrated")

    def test_fba_fbm_classification_via_products(self):
        sellers = [_seller("S1", market_share=Decimal("1.0"))]
        products = [
            _product(asin="A1", fulfillment_method="FBA"),
            _product(asin="A2", fulfillment_method="FBM"),
            _product(asin="A3", fulfillment_method="AMZ"),
            _product(asin="A4", fulfillment_method="MFN"),
            _product(asin="A5", fulfillment_method="weird"),
        ]
        result = analyze_sellers(sellers, products=products)
        self.assertEqual(result.fba_count, 2)  # FBA, AMZ
        self.assertEqual(result.fbm_count, 2)   # FBM, MFN
        self.assertEqual(result.unknown_fulfillment_count, 1)

    def test_fba_ratio(self):
        sellers = [_seller("S1", market_share=Decimal("1.0"))]
        products = [
            _product(asin="A1", fulfillment_method="FBA"),
            _product(asin="A2", fulfillment_method="FBA"),
            _product(asin="A3", fulfillment_method="FBM"),
            _product(asin="A4", fulfillment_method="FBM"),
        ]
        result = analyze_sellers(sellers, products=products)
        self.assertEqual(result.fba_ratio, Decimal("0.5000"))

    def test_seller_locations(self):
        sellers = [_seller("S1", market_share=Decimal("1.0"))]
        products = [
            _product(asin="A1", seller_location="US"),
            _product(asin="A2", seller_location="CN"),
            _product(asin="A3", seller_location="US"),
        ]
        result = analyze_sellers(sellers, products=products)
        self.assertEqual(result.seller_locations, {"CN": 1, "US": 2})

    def test_no_products_means_zero_fulfillment(self):
        sellers = [_seller("S1", market_share=Decimal("1.0"))]
        result = analyze_sellers(sellers, products=None)
        self.assertEqual(result.fba_count, 0)
        self.assertEqual(result.fbm_count, 0)
        self.assertIsNone(result.fba_ratio)
        self.assertEqual(result.seller_locations, {})

    def test_fulfillment_only_when_no_seller_metrics(self):
        # When no seller metrics are provided but products are, we
        # still compute FBA/FBM + geography.
        products = [
            _product(asin="A1", fulfillment_method="FBA", source_file="p.xlsx"),
            _product(asin="A2", fulfillment_method="FBM", source_file="p.xlsx"),
        ]
        result = analyze_sellers([], products=products)
        self.assertEqual(result.share_basis, "none")
        self.assertTrue(result.requires_review)
        self.assertEqual(result.fba_count, 1)
        self.assertEqual(result.fbm_count, 1)
        self.assertEqual(result.fba_ratio, Decimal("0.5000"))
        self.assertEqual(result.source_files, ["p.xlsx"])

    def test_no_share_data_returns_review(self):
        sellers = [_seller("a"), _seller("b")]
        result = analyze_sellers(sellers)
        self.assertEqual(result.share_basis, "none")
        self.assertTrue(result.requires_review)

    def test_classify_fulfillment_helper(self):
        cases = [
            ("FBA", "fba"),
            ("fba", "fba"),
            ("AMZ", "fba"),
            ("Amazon", "fba"),
            ("FBM", "fbm"),
            ("MFN", "fbm"),
            ("Merchant", "fbm"),
            ("3P", "fbm"),
            ("", "unknown"),
            (None, "unknown"),
            ("weird", "unknown"),
        ]
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(_classify_fulfillment(value), expected)

    def test_top4_top8_sellers(self):
        sellers = [
            _seller(f"s{i}", market_share=Decimal(str(0.4 - i * 0.05)))
            for i in range(10)
        ]
        result = analyze_sellers(sellers)
        self.assertEqual(len(result.top4_sellers), 4)
        self.assertEqual(len(result.top8_sellers), 8)
        self.assertEqual(result.top4_sellers[0]["seller"], "s0")

    def test_source_files_propagated(self):
        sellers = [
            _seller("s1", market_share=Decimal("0.5"), source_file="s1.xlsx"),
            _seller("s2", market_share=Decimal("0.5"), source_file="s2.xlsx"),
        ]
        result = analyze_sellers(sellers)
        self.assertEqual(result.source_files, ["s1.xlsx", "s2.xlsx"])

    def test_to_dict_round_trip(self):
        sellers = [_seller("s", market_share=Decimal("1.0"))]
        d = analyze_sellers(sellers).to_dict()
        self.assertEqual(d["total_sellers"], 1)
        self.assertIn("hhi", d)
        self.assertIn("fba_ratio", d)


# ===========================================================================
# Search-position analysis
# ===========================================================================


class TestSearchPositionAnalysis(unittest.TestCase):

    def test_empty_input(self):
        result = analyze_search_positions([])
        self.assertEqual(result.total_appearances, 0)
        self.assertEqual(result.matrix, [])
        self.assertIsNone(result.sponsored_ratio)
        self.assertEqual(result.keyword_count, 0)

    def test_single_keyword_single_appearance(self):
        appearances = [_appearance(keyword="kw", asin="A1", placement_type="organic")]
        result = analyze_search_positions(appearances)
        self.assertEqual(result.keyword_count, 1)
        self.assertEqual(result.matrix[0].keyword, "kw")
        self.assertEqual(result.matrix[0].unique_asin_count, 1)
        self.assertEqual(result.matrix[0].organic_count, 1)
        self.assertEqual(result.matrix[0].sponsored_count, 0)

    def test_sponsored_vs_organic_classification(self):
        appearances = [
            _appearance(keyword="k", asin="A", placement_type="sponsored"),
            _appearance(keyword="k", asin="B", placement_type="organic"),
            _appearance(keyword="k", asin="C", placement_type="unknown"),
        ]
        result = analyze_search_positions(appearances)
        self.assertEqual(result.total_sponsored, 1)
        self.assertEqual(result.total_organic, 1)
        self.assertEqual(result.total_unknown_placement, 1)

    def test_sponsored_ratio(self):
        appearances = [
            _appearance(keyword="k", asin="A", placement_type="sponsored"),
            _appearance(keyword="k", asin="B", placement_type="sponsored"),
            _appearance(keyword="k", asin="C", placement_type="organic"),
            _appearance(keyword="k", asin="D", placement_type="organic"),
        ]
        result = analyze_search_positions(appearances)
        self.assertEqual(result.sponsored_ratio, Decimal("0.5000"))

    def test_sponsored_ratio_zero_when_no_classified(self):
        appearances = [
            _appearance(keyword="k", asin="A", placement_type="unknown"),
        ]
        result = analyze_search_positions(appearances)
        self.assertIsNone(result.sponsored_ratio)

    def test_page_distribution(self):
        appearances = [
            _appearance(keyword="k", asin="A", page_number=1),
            _appearance(keyword="k", asin="B", page_number=1),
            _appearance(keyword="k", asin="C", page_number=2),
            _appearance(keyword="k", asin="D", page_number=3),
        ]
        result = analyze_search_positions(appearances)
        page_dist = result.matrix[0].page_distribution
        self.assertEqual(page_dist, {1: 2, 2: 1, 3: 1})

    def test_top_asins_by_frequency(self):
        # A appears 3 times, B 2 times, C 1 time.
        appearances = [
            _appearance(keyword="k", asin="A"),
            _appearance(keyword="k", asin="A"),
            _appearance(keyword="k", asin="A"),
            _appearance(keyword="k", asin="B"),
            _appearance(keyword="k", asin="B"),
            _appearance(keyword="k", asin="C"),
        ]
        result = analyze_search_positions(appearances)
        top = result.matrix[0].top_asins
        self.assertEqual(top[0]["asin"], "A")
        self.assertEqual(top[0]["appearance_count"], 3)
        self.assertEqual(top[1]["asin"], "B")
        self.assertEqual(top[1]["appearance_count"], 2)

    def test_avg_asin_per_keyword(self):
        # kw1: 3 unique ASINs, kw2: 2 unique ASINs -> avg = 2.5
        appearances = [
            _appearance(keyword="kw1", asin="A"),
            _appearance(keyword="kw1", asin="B"),
            _appearance(keyword="kw1", asin="C"),
            _appearance(keyword="kw2", asin="D"),
            _appearance(keyword="kw2", asin="E"),
        ]
        result = analyze_search_positions(appearances)
        self.assertEqual(result.avg_asin_per_keyword, Decimal("2.5000"))
        self.assertEqual(result.unique_asin_count, 5)

    def test_top_keywords_by_sponsored(self):
        appearances = [
            _appearance(keyword="kw1", asin="A", placement_type="sponsored"),
            _appearance(keyword="kw1", asin="B", placement_type="sponsored"),
            _appearance(keyword="kw2", asin="C", placement_type="sponsored"),
            _appearance(keyword="kw3", asin="D", placement_type="organic"),
        ]
        result = analyze_search_positions(appearances)
        top = result.top_keywords_by_sponsored
        self.assertEqual(top[0]["keyword"], "kw1")
        self.assertEqual(top[0]["sponsored_count"], 2)
        self.assertEqual(top[1]["keyword"], "kw2")
        # kw3 has no sponsored -> not in the list.
        sponsored_kws = {k["keyword"] for k in top}
        self.assertNotIn("kw3", sponsored_kws)

    def test_top_keywords_by_organic(self):
        appearances = [
            _appearance(keyword="kw1", asin="A", placement_type="organic"),
            _appearance(keyword="kw2", asin="B", placement_type="organic"),
            _appearance(keyword="kw2", asin="C", placement_type="organic"),
        ]
        result = analyze_search_positions(appearances)
        top = result.top_keywords_by_organic
        self.assertEqual(top[0]["keyword"], "kw2")
        self.assertEqual(top[0]["organic_count"], 2)

    def test_same_asin_multiple_times_is_not_deduplicated(self):
        # The whole point of search-position analysis: do NOT collapse
        # rows. The same ASIN appearing under multiple keywords /
        # placements / pages must be preserved.
        appearances = [
            _appearance(keyword="kw1", asin="A", placement_type="organic", page_number=1),
            _appearance(keyword="kw1", asin="A", placement_type="sponsored", page_number=1),
            _appearance(keyword="kw2", asin="A", placement_type="organic", page_number=2),
        ]
        result = analyze_search_positions(appearances)
        self.assertEqual(result.total_appearances, 3)
        self.assertEqual(result.unique_asin_count, 1)
        # kw1 has A twice: once organic, once sponsored.
        kw1 = result.matrix[0]
        self.assertEqual(kw1.total_appearances, 2)
        self.assertEqual(kw1.unique_asin_count, 1)
        self.assertEqual(kw1.organic_count, 1)
        self.assertEqual(kw1.sponsored_count, 1)

    def test_placement_detail_sponsored_detection(self):
        # "Sponsored Ad" in placement_detail should flag sponsored
        # even when placement_type is "unknown".
        appearances = [
            _appearance(
                keyword="k",
                asin="A",
                placement_type="unknown",
                placement_detail="Sponsored Ad",
            ),
            _appearance(
                keyword="k",
                asin="B",
                placement_type="unknown",
                placement_detail="Top of Search",
            ),
        ]
        result = analyze_search_positions(appearances)
        self.assertEqual(result.total_sponsored, 1)
        # "Top of Search" doesn't contain "sponsor" or "ad" alone — but
        # actually "ad" is in "Top of Search"? No: "Top of Search" has
        # no "ad" substring. Let me check: "Top of Search" -> contains
        # "ad"? No, "Search" doesn't contain "ad". So B is unknown.
        # Wait, "Sponsored Ad" contains "ad" -> A is sponsored.
        self.assertEqual(result.total_organic, 0)
        self.assertEqual(result.total_unknown_placement, 1)

    def test_is_sponsored_flag_overrides_placement_type(self):
        appearances = [
            _appearance(
                keyword="k",
                asin="A",
                placement_type="unknown",
                is_sponsored=True,
            ),
        ]
        result = analyze_search_positions(appearances)
        self.assertEqual(result.total_sponsored, 1)

    def test_is_organic_flag_overrides_placement_type(self):
        appearances = [
            _appearance(
                keyword="k",
                asin="A",
                placement_type="unknown",
                is_organic=True,
            ),
        ]
        result = analyze_search_positions(appearances)
        self.assertEqual(result.total_organic, 1)

    def test_source_files_propagated(self):
        appearances = [
            _appearance(keyword="k", asin="A", source_file="s1.xlsx"),
            _appearance(keyword="k", asin="B", source_file="s2.xlsx"),
        ]
        result = analyze_search_positions(appearances)
        self.assertEqual(result.source_files, ["s1.xlsx", "s2.xlsx"])
        self.assertEqual(result.matrix[0].source_files, ["s1.xlsx", "s2.xlsx"])

    def test_to_dict_round_trip(self):
        appearances = [_appearance(keyword="k", asin="A", placement_type="organic")]
        d = analyze_search_positions(appearances).to_dict()
        self.assertEqual(d["total_appearances"], 1)
        self.assertEqual(d["keyword_count"], 1)
        self.assertEqual(d["matrix"][0]["keyword"], "k")

    def test_low_confidence_source_flags_review(self):
        appearances = [
            _appearance(keyword="k", asin="A", source_type="mock_data"),
        ]
        result = analyze_search_positions(appearances)
        self.assertTrue(result.requires_review)

    def test_user_input_source_does_not_flag_review(self):
        appearances = [
            _appearance(keyword="k", asin="A", source_type="user_input"),
        ]
        result = analyze_search_positions(appearances)
        self.assertFalse(result.requires_review)


# ===========================================================================
# Integration — analyzers consume normaliser output
# ===========================================================================


class TestAnalyzersWithNormalizer(unittest.TestCase):

    def test_keywords_from_dedup_then_analyze(self):
        from src.modules.amazon.importers.normalizer import dedup_by_key

        # Two metrics for the same keyword from different files.
        kms = [
            _kw("chicken", Decimal("1000"), source_file="a.xlsx"),
            _kw("chicken", Decimal("1000"), source_file="b.xlsx"),
            _kw("feeder", Decimal("500"), source_file="a.xlsx"),
        ]
        deduped = dedup_by_key(kms)
        result = analyze_keywords(deduped["deduped"])
        # Both keywords preserved.
        self.assertEqual(result.total_keywords, 2)
        # Chicken still ranks first.
        self.assertEqual(result.rankings[0].keyword, "chicken")

    def test_search_appearances_normalized_then_analyzed(self):
        from src.modules.amazon.importers.normalizer import (
            normalize_search_appearances,
        )

        appearances = [
            _appearance(keyword="kw1", asin="A", placement_type="organic"),
            _appearance(keyword="kw1", asin="A", placement_type="sponsored"),
            _appearance(keyword="kw2", asin="B", placement_type="organic"),
        ]
        normalized = normalize_search_appearances(appearances)
        result = analyze_search_positions(normalized.appearances)
        self.assertEqual(result.total_appearances, 3)
        self.assertEqual(result.unique_asin_count, 2)


if __name__ == "__main__":
    unittest.main()
