"""Tests for src/modules/amazon/mock_data.py.

Covers V3 spec test cases:
- Case 4: 关键词Agent输出稳定 (get_mock_keyword same call → same object)
- Case 5: 市场Agent输出字段完整 (MarketOutput has all required fields)
- Case 10: 无真实数据时confidence不为high (mock_data confidence is "low")
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from src.modules.amazon.mock_data import (
    get_mock_competitors,
    get_mock_keyword,
    get_mock_market,
    get_mock_profit_input,
    get_mock_reviews,
)


class MockKeywordTest(unittest.TestCase):
    """Case 4: 关键词Agent输出稳定 — same call → same object."""

    def test_case4_keyword_deterministic(self):
        a = get_mock_keyword()
        b = get_mock_keyword()
        self.assertEqual(a, b)
        self.assertEqual(a.normalized_keyword, "chicken coop door")
        self.assertEqual(a.source, "mock_data")
        self.assertEqual(a.confidence, "low")
        self.assertEqual(a.search_volume, None)

    def test_case10_keyword_confidence_not_high(self):
        """Case 10: mock_data confidence is 'low', never 'high'."""
        kw = get_mock_keyword()
        self.assertNotEqual(kw.confidence, "high")


class MockMarketTest(unittest.TestCase):
    """Case 5: 市场Agent输出字段完整."""

    def test_case5_market_fields_complete(self):
        m = get_mock_market("amazon_us")
        self.assertEqual(m.marketplace, "amazon_us")
        self.assertTrue(m.category)
        self.assertTrue(m.product_line)
        self.assertTrue(m.consumption_scenario)
        self.assertTrue(m.target_customer)
        self.assertEqual(m.market_capacity, "qualitative")
        self.assertTrue(m.growth_trend)
        self.assertTrue(m.price_range)
        self.assertTrue(m.competition_level)
        self.assertGreater(m.opportunity_score, 0)
        self.assertGreater(len(m.market_assumptions), 0)
        self.assertEqual(m.source, "mock_data")
        self.assertEqual(m.confidence, "low")

    def test_case10_market_confidence_not_high(self):
        self.assertNotEqual(get_mock_market().confidence, "high")


class MockCompetitorsTest(unittest.TestCase):

    def test_four_mock_competitors(self):
        rows = get_mock_competitors()
        self.assertEqual(len(rows), 4)
        for row in rows:
            self.assertTrue(row.asin.startswith("MOCK-ASIN-"))
            self.assertEqual(row.source, "mock_data")
            self.assertIsInstance(row.price, Decimal)

    def test_case10_competitor_confidence_not_high(self):
        for row in get_mock_competitors():
            self.assertEqual(row.source, "mock_data")


class MockReviewsTest(unittest.TestCase):

    def test_twelve_mock_reviews(self):
        rows = get_mock_reviews()
        self.assertEqual(len(rows), 12)
        for row in rows:
            self.assertTrue(row.review_id.startswith("MOCK-REV-"))
            self.assertEqual(row.source, "mock_data")

    def test_case10_review_confidence_not_high(self):
        for row in get_mock_reviews():
            self.assertEqual(row.source, "mock_data")


class MockProfitInputTest(unittest.TestCase):

    def test_profit_input_from_config(self):
        config = {
            "profit_cost_defaults": {
                "selling_price": 29.99,
                "unit_cost": 8.50,
                "inbound_shipping": 1.20,
                "international_shipping": 2.80,
                "customs_duty": 0.60,
                "fba_fee": 3.90,
                "referral_fee": 4.50,
                "storage_fee": 0.30,
                "advertising_cost": 3.00,
                "return_cost": 1.50,
                "other_variable_cost": 0.50,
                "fixed_development_cost": 5000.00,
                "initial_investment": 12000.00,
                "estimated_monthly_units": 300,
                "monthly_fixed_cost": 800.00,
            }
        }
        pi = get_mock_profit_input(config)
        self.assertEqual(pi.selling_price, Decimal("29.99"))
        self.assertEqual(pi.unit_cost, Decimal("8.50"))
        self.assertEqual(pi.estimated_monthly_units, 300)
        self.assertEqual(pi.initial_investment, Decimal("12000.00"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
