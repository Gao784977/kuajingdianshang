"""Tests for src/modules/amazon/keyword_agent.py.

Covers V3 spec test case:
- Case 4: 关键词Agent输出稳定 (two calls produce equal output)
"""

from __future__ import annotations

import unittest

from src.modules.amazon.keyword_agent import KeywordAgent
from src.modules.amazon.models import KeywordOutput, WorkflowContext

from tests._amazon_helpers import make_product_input


class KeywordAgentTest(unittest.TestCase):
    """Case 4: 关键词Agent输出稳定."""

    def _ctx(self):
        return WorkflowContext(
            product_input=make_product_input(),
            config={"supported_marketplaces": ["amazon_us"]},
            cli_args={},
        )

    def test_case4_two_calls_produce_equal_output(self):
        agent = KeywordAgent()
        r1 = agent.run(self._ctx())
        r2 = agent.run(self._ctx())
        self.assertEqual(r1.status, "completed")
        self.assertEqual(r1.output.normalized_keyword, "chicken coop door")
        self.assertEqual(r1.output, r2.output)
        self.assertEqual(r1.output.source, "mock_data")
        self.assertEqual(r1.output.confidence, "low")
        self.assertIsNone(r1.output.search_volume)
        self.assertGreater(len(r1.output.related_keywords), 0)

    def test_keyword_output_is_keyword_output_type(self):
        agent = KeywordAgent()
        ctx = self._ctx()
        result = agent.run(ctx)
        self.assertIsInstance(result.output, KeywordOutput)

    def test_empty_keyword_uses_default_and_warns(self):
        agent = KeywordAgent()
        ctx = WorkflowContext(
            product_input=make_product_input(keyword=""),
            config={"supported_marketplaces": ["amazon_us"]},
            cli_args={},
        )
        result = agent.run(ctx)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output.normalized_keyword, "chicken coop door")
        self.assertTrue(any("keyword" in w.lower() for w in result.warnings))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
