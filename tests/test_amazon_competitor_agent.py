"""Tests for src/modules/amazon/competitor_agent.py.

Covers V3 spec test cases:
- Case 6: 竞品CSV正常读取 (CompetitorAgent with merged rows)
- Case 7: 模拟ASIN标记正确 (competitor_matrix rows preserve source)
"""

from __future__ import annotations

import unittest

from src.modules.amazon.competitor_agent import CompetitorAgent
from src.modules.amazon.mock_data import get_mock_competitors
from src.modules.amazon.models import CompetitorOutput, WorkflowContext

from tests._amazon_helpers import make_competitor_row


class CompetitorAgentTest(unittest.TestCase):
    """Cases 6, 7."""

    def _ctx(self):
        return WorkflowContext(
            config={"supported_marketplaces": ["amazon_us"]},
            cli_args={},
        )

    def test_case6_mock_competitors_loaded(self):
        """Case 6: CompetitorAgent with mock rows produces full output."""
        agent = CompetitorAgent()
        rows = get_mock_competitors()
        result = agent.run(self._ctx(), competitors=rows)
        self.assertEqual(result.status, "completed")
        out = result.output
        self.assertIsInstance(out, CompetitorOutput)
        self.assertEqual(len(out.competitor_matrix), 4)
        self.assertEqual(out.price_distribution["count"], 4)
        self.assertEqual(out.rating_distribution["count"], 4)
        self.assertEqual(out.review_distribution["count"], 4)
        self.assertGreater(len(out.market_gaps), 0)
        self.assertGreater(len(out.differentiation_opportunities), 0)

    def test_case7_asin_source_tags_preserved(self):
        """Case 7: MOCK-ASIN rows tagged mock_data; USER-ASIN tagged imported_csv."""
        agent = CompetitorAgent()
        mock_rows = get_mock_competitors()
        user_rows = [make_competitor_row(
            asin="USER-ASIN-005", brand="UserBrand", source="imported_csv"
        )]
        result = agent.run(self._ctx(), competitors=mock_rows + user_rows)
        matrix = result.output.competitor_matrix
        mock_entry = next(r for r in matrix if r["asin"].startswith("MOCK-ASIN-"))
        user_entry = next(r for r in matrix if r["asin"].startswith("USER-ASIN-"))
        self.assertEqual(mock_entry["source"], "mock_data")
        self.assertEqual(user_entry["source"], "imported_csv")
        # When any imported_csv row is present, agent source is imported_csv
        self.assertEqual(result.output.source, "imported_csv")
        self.assertEqual(result.output.confidence, "medium")

    def test_no_competitors_returns_incomplete(self):
        agent = CompetitorAgent()
        result = agent.run(self._ctx(), competitors=None)
        self.assertEqual(result.status, "incomplete")

    def test_mock_only_confidence_low(self):
        agent = CompetitorAgent()
        result = agent.run(self._ctx(), competitors=get_mock_competitors())
        self.assertEqual(result.output.source, "mock_data")
        self.assertEqual(result.output.confidence, "low")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
