"""Tests for src/modules/amazon/opportunity_agent.py.

Covers V3 spec test cases:
- Case 9: Opportunity Agent评分 (scores 4/3/4/5, rec=validate_first)
- Case 10: 无真实数据时confidence不为high (confidence ≤ medium)
- Case 11: Product Agent reads prior agent results (degrades if prior missing)
"""

from __future__ import annotations

import unittest

from src.modules.amazon.competitor_agent import CompetitorAgent
from src.modules.amazon.market_agent import MarketAgent
from src.modules.amazon.mock_data import (
    get_mock_competitors,
    get_mock_keyword,
    get_mock_market,
    get_mock_reviews,
)
from src.modules.amazon.models import (
    AgentResult,
    OpportunityOutput,
    ProductOutput,
    WorkflowContext,
)
from src.modules.amazon.opportunity_agent import OpportunityAgent
from src.modules.amazon.product_agent import ProductAgent
from src.modules.amazon.review_agent import ReviewAgent

from tests._amazon_helpers import make_product_input


def _build_context_with_priors():
    """Run keyword/market/competitor/review and populate a context."""
    config = {
        "supported_marketplaces": ["amazon_us"],
        "review_categories": [
            "installation", "quality", "packaging", "feature_request",
            "price", "shipping", "customer_service",
        ],
        "profit_cost_defaults": {"unit_cost": 8.50},
        "score_rules": {
            "market_opportunity": 30, "competition": 20,
            "supply_chain_feasibility": 20, "differentiation_potential": 30,
        },
    }
    ctx = WorkflowContext(
        product_input=make_product_input(),
        config=config,
        cli_args={},
    )
    # Use mock outputs directly (they're deterministic)
    ctx.set_result("keyword", AgentResult(
        agent_name="keyword", status="completed",
        output=get_mock_keyword(), source="mock_data",
    ))
    ctx.set_result("market", AgentResult(
        agent_name="market", status="completed",
        output=get_mock_market("amazon_us"), source="mock_data",
    ))
    comp_agent = CompetitorAgent()
    ctx.set_result("competitor", comp_agent.run(
        ctx, competitors=get_mock_competitors()
    ))
    rev_agent = ReviewAgent()
    ctx.set_result("review", rev_agent.run(
        ctx, reviews=get_mock_reviews()
    ))
    return ctx


class OpportunityAgentTest(unittest.TestCase):
    """Cases 9, 10."""

    def test_case9_opportunity_scores(self):
        """Case 9: scores 4/3/4/5, rec=validate_first (mock-only data)."""
        ctx = _build_context_with_priors()
        agent = OpportunityAgent()
        result = agent.run(ctx)
        self.assertEqual(result.status, "completed")
        o = result.output
        self.assertIsInstance(o, OpportunityOutput)
        # market_opportunity: score 75 → band 4
        self.assertEqual(o.market_opportunity, 4)
        # competition: medium level, avg review ~799 → 3
        self.assertEqual(o.competition, 3)
        # supply_chain_feasibility: target 20 >= cost 8.50 → 4
        self.assertEqual(o.supply_chain_feasibility, 4)
        # differentiation: gaps + opportunities >= 8 → 5
        self.assertEqual(o.differentiation_potential, 5)
        # Mock-only data → validate_first (no real validated data)
        self.assertEqual(o.development_recommendation, "validate_first")

    def test_case10_confidence_not_high(self):
        """Case 10: mock-only data → confidence ≤ medium, never high."""
        ctx = _build_context_with_priors()
        agent = OpportunityAgent()
        result = agent.run(ctx)
        self.assertNotEqual(result.output.confidence, "high")
        self.assertIn(result.output.confidence, ("low", "medium"))

    def test_human_review_required_when_mock_only(self):
        ctx = _build_context_with_priors()
        agent = OpportunityAgent()
        result = agent.run(ctx)
        self.assertTrue(result.output.human_review_required)

    def test_market_missing_returns_incomplete(self):
        ctx = WorkflowContext(
            product_input=make_product_input(),
            config={"profit_cost_defaults": {"unit_cost": 8.50}},
            cli_args={},
        )
        agent = OpportunityAgent()
        result = agent.run(ctx)
        self.assertEqual(result.status, "incomplete")

    def test_required_validation_populated(self):
        ctx = _build_context_with_priors()
        agent = OpportunityAgent()
        result = agent.run(ctx)
        self.assertGreater(len(result.output.required_validation), 0)


class ProductAgentDegradeTest(unittest.TestCase):
    """Case 11: ProductAgent degrades to incomplete if any prior missing."""

    def test_case11_product_agent_degrades_when_prior_missing(self):
        ctx = WorkflowContext(
            product_input=make_product_input(),
            config={"profit_cost_defaults": {"unit_cost": 8.50,
                                              "selling_price": 29.99}},
            cli_args={},
        )
        # No prior agents set → product agent must degrade
        agent = ProductAgent()
        result = agent.run(ctx)
        self.assertEqual(result.status, "incomplete")
        self.assertTrue(any("missing" in w.lower() or "incomplete" in w.lower()
                            for w in result.warnings))

    def test_product_agent_completes_with_all_priors(self):
        ctx = _build_context_with_priors()
        agent = ProductAgent()
        result = agent.run(ctx)
        self.assertEqual(result.status, "completed")
        p = result.output
        self.assertIsInstance(p, ProductOutput)
        self.assertTrue(p.product_name)
        self.assertGreater(len(p.core_selling_points), 0)
        self.assertGreater(len(p.functional_design), 0)
        self.assertEqual(p.development_cycle_days, 75)
        self.assertGreater(len(p.validation_plan), 0)
        self.assertGreater(len(p.required_supplier_questions), 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
