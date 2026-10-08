"""Tests for src/modules/amazon/market_agent.py.

Covers V3 spec test case:
- Case 5: 市场Agent输出字段完整 (MarketOutput has all required fields)
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from src.modules.amazon.market_agent import MarketAgent
from src.modules.amazon.models import MarketOutput, WorkflowContext

from tests._amazon_helpers import make_product_input


class MarketAgentTest(unittest.TestCase):
    """Case 5: 市场Agent输出字段完整."""

    def _ctx(self, **overrides):
        pi = make_product_input(**overrides)
        return WorkflowContext(
            product_input=pi,
            config={"supported_marketplaces": ["amazon_us"]},
            cli_args={},
        )

    def test_case5_market_output_fields_complete(self):
        agent = MarketAgent()
        result = agent.run(self._ctx())
        self.assertEqual(result.status, "completed")
        m = result.output
        self.assertIsInstance(m, MarketOutput)
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

    def test_user_price_range_overrides_mock(self):
        agent = MarketAgent()
        result = agent.run(self._ctx(
            target_price_min=Decimal("20"), target_price_max=Decimal("50")
        ))
        self.assertIn("20", result.output.price_range)
        self.assertIn("50", result.output.price_range)

    def test_unsupported_marketplace_warns_and_falls_back(self):
        agent = MarketAgent()
        result = agent.run(self._ctx(marketplace="amazon_jp"))
        self.assertEqual(result.status, "completed")
        self.assertTrue(any("amazon_jp" in w for w in result.warnings))

    def test_market_confidence_not_high(self):
        """Case 10: mock market confidence is 'low'."""
        agent = MarketAgent()
        result = agent.run(self._ctx())
        self.assertNotEqual(result.output.confidence, "high")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
