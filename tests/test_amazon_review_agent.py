"""Tests for src/modules/amazon/review_agent.py.

Covers V3 spec test case:
- Case 8: Review分类 (12 mock reviews → installation=3, quality=5,
  packaging=2, feature_request=2, price=4, shipping=2, customer_service=0)
"""

from __future__ import annotations

import unittest

from src.modules.amazon.mock_data import get_mock_reviews
from src.modules.amazon.models import ReviewOutput, WorkflowContext
from src.modules.amazon.review_agent import ReviewAgent


class ReviewAgentTest(unittest.TestCase):
    """Case 8: Review classification into the 7 categories."""

    def _ctx(self):
        config = {
            "review_categories": [
                "installation", "quality", "packaging", "feature_request",
                "price", "shipping", "customer_service",
            ],
        }
        return WorkflowContext(config=config, cli_args={})

    def test_case8_mock_review_classification(self):
        """Case 8: 12 mock reviews classified into expected categories."""
        agent = ReviewAgent()
        reviews = get_mock_reviews()
        result = agent.run(self._ctx(), reviews=reviews)
        self.assertEqual(result.status, "completed")
        out = result.output
        self.assertIsInstance(out, ReviewOutput)
        self.assertEqual(out.review_count, 12)

        # Expected category counts (verified against mock review texts):
        # installation=3, quality=5, packaging=2, feature_request=2,
        # price=4, shipping=2, customer_service=0
        cats = out.issue_categories
        self.assertEqual(cats["installation"], 3)
        self.assertEqual(cats["quality"], 5)
        self.assertEqual(cats["packaging"], 2)
        self.assertEqual(cats["feature_request"], 2)
        self.assertEqual(cats["price"], 4)
        self.assertEqual(cats["shipping"], 2)
        self.assertEqual(cats["customer_service"], 0)

        # Sentiment: ratings 5,4,4,4,4 = 5 positive; 3,3,3 = 3 neutral;
        # 2,2,2,1,2 = 4 negative. Wait: 12 reviews, ratings are
        # 2,5,3,3,3,4,2,1,4,4,2,4 → positive(>=4)=5, neutral(=3)=3, negative=4
        self.assertEqual(out.sentiment_summary["positive"], 5)
        self.assertEqual(out.sentiment_summary["neutral"], 3)
        self.assertEqual(out.sentiment_summary["negative"], 4)

        # Improvement directions derived from categories present
        self.assertGreater(len(out.product_improvement_directions), 0)

    def test_no_reviews_returns_incomplete(self):
        agent = ReviewAgent()
        result = agent.run(self._ctx(), reviews=None)
        self.assertEqual(result.status, "incomplete")

    def test_mock_only_confidence_low(self):
        agent = ReviewAgent()
        result = agent.run(self._ctx(), reviews=get_mock_reviews())
        self.assertEqual(result.output.source, "mock_data")
        self.assertEqual(result.output.confidence, "low")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
