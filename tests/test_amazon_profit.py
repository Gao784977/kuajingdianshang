"""Tests for src/modules/amazon/profit_agent.py.

Covers V3 spec test cases:
- Case 12: Amazon利润计算 (base scenario monthly_profit = 157.00)
- Case 13: FBA和广告成本计算 (included in total_variable_cost_per_unit)
- Case 14: 三种利润情景 (base/optimistic/pessimistic all distinct)
- Case 15: 亏损时ROI为null (pessimistic monthly_profit <= 0 → roi is None)
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from src.modules.amazon.amazon_config import load_amazon_config
from src.modules.amazon.profit_agent import (
    ProfitAgent,
    _resolve_scenarios,
    calculate_amazon_profit,
)
from src.modules.amazon.models import AmazonProfitInput, WorkflowContext

from tests._amazon_helpers import make_amazon_profit_input


def _base_multipliers():
    config = load_amazon_config()
    return config["scenarios"]["base"], config["scenarios"]


class ProfitCalculationTest(unittest.TestCase):
    """Cases 12, 13, 14, 15."""

    def setUp(self):
        self.config = load_amazon_config()
        self.scenarios = self.config["scenarios"]
        self.profit_input = make_amazon_profit_input()

    def test_case12_base_monthly_profit(self):
        """Case 12: base scenario monthly_profit = 157.00."""
        result = calculate_amazon_profit(
            self.profit_input, self.scenarios["base"], "base"
        )
        # total_variable_cost_per_unit = 8.50+1.20+2.80+0.60+3.90+4.50+
        #                               0.30+3.00+1.50+0.50 = 26.80
        self.assertEqual(result.total_variable_cost_per_unit, Decimal("26.80"))
        # unit_profit = 29.99 - 26.80 = 3.19
        self.assertEqual(result.unit_profit, Decimal("3.19"))
        # monthly_profit = 3.19 * 300 - 800 = 157.00
        self.assertEqual(result.monthly_profit, Decimal("157.00"))
        # annualized = 157.00 * 12 = 1884.00
        self.assertEqual(result.annualized_profit, Decimal("1884.00"))
        # roi = 1884.00 / 12000.00 = 0.1570
        self.assertEqual(result.roi, Decimal("0.1570"))
        self.assertEqual(result.scenario, "base")
        self.assertEqual(result.calculation_version, "amazon_calculation_v1")

    def test_case13_fba_and_advertising_in_total_cost(self):
        """Case 13: fba_fee + advertising_cost included in total_variable."""
        result = calculate_amazon_profit(
            self.profit_input, self.scenarios["base"], "base"
        )
        # fba_fee=3.90, advertising_cost=3.00 → sum 6.90 must be in the total
        self.assertEqual(result.fba_fee, Decimal("3.90"))
        self.assertEqual(result.advertising_cost, Decimal("3.00"))
        # total_variable_cost includes both
        manual_total = (
            result.unit_cost + result.inbound_shipping
            + result.international_shipping + result.customs_duty
            + result.fba_fee + result.referral_fee + result.storage_fee
            + result.advertising_cost + result.return_cost
            + result.other_variable_cost
        )
        self.assertEqual(result.total_variable_cost_per_unit, manual_total)

    def test_case14_three_scenarios_distinct(self):
        """Case 14: base/optimistic/pessimistic all distinct."""
        base = calculate_amazon_profit(
            self.profit_input, self.scenarios["base"], "base"
        )
        opt = calculate_amazon_profit(
            self.profit_input, self.scenarios["optimistic"], "optimistic"
        )
        pess = calculate_amazon_profit(
            self.profit_input, self.scenarios["pessimistic"], "pessimistic"
        )
        self.assertEqual(base.scenario, "base")
        self.assertEqual(opt.scenario, "optimistic")
        self.assertEqual(pess.scenario, "pessimistic")
        # Optimistic should beat base; pessimistic should be worst
        self.assertGreater(opt.monthly_profit, base.monthly_profit)
        self.assertLess(pess.monthly_profit, base.monthly_profit)
        self.assertGreater(opt.selling_price, base.selling_price)
        self.assertLess(pess.selling_price, base.selling_price)

    def test_case15_loss_scenario_roi_null(self):
        """Case 15: pessimistic monthly_profit <= 0 → roi is None."""
        pess = calculate_amazon_profit(
            self.profit_input, self.scenarios["pessimistic"], "pessimistic"
        )
        self.assertLessEqual(pess.monthly_profit, Decimal("0"))
        self.assertIsNone(pess.roi)

    def test_roi_null_when_no_initial_investment(self):
        """ROI null when initial_investment <= 0."""
        pi = make_amazon_profit_input(initial_investment=Decimal("0"))
        result = calculate_amazon_profit(
            pi, self.scenarios["base"], "base"
        )
        self.assertIsNone(result.roi)

    def test_unit_margin_none_when_price_zero(self):
        """unit_margin is 0 when selling_price <= 0."""
        pi = make_amazon_profit_input(selling_price=Decimal("0"))
        result = calculate_amazon_profit(
            pi, self.scenarios["base"], "base"
        )
        self.assertEqual(result.unit_margin, Decimal("0"))


class ResolveScenariosTest(unittest.TestCase):

    def test_all_returns_three(self):
        self.assertEqual(
            _resolve_scenarios("all", {"base": {}, "optimistic": {},
                                        "pessimistic": {}}),
            ["base", "optimistic", "pessimistic"],
        )

    def test_single_name(self):
        self.assertEqual(
            _resolve_scenarios("base", {"base": {}, "optimistic": {}}),
            ["base"],
        )

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            _resolve_scenarios("bogus", {"base": {}})


class ProfitAgentRunTest(unittest.TestCase):

    def test_profit_agent_run_base(self):
        config = load_amazon_config()
        ctx = WorkflowContext(config=config, cli_args={"scenario": "base"})
        agent = ProfitAgent()
        result = agent.run(ctx, profit_input=make_amazon_profit_input())
        self.assertEqual(result.status, "completed")
        self.assertIn("base", result.output)
        self.assertEqual(result.output["base"]["monthly_profit"], "157.00")

    def test_profit_agent_run_all_scenarios(self):
        config = load_amazon_config()
        ctx = WorkflowContext(config=config, cli_args={"scenario": "all"})
        agent = ProfitAgent()
        result = agent.run(ctx, profit_input=make_amazon_profit_input())
        self.assertEqual(result.status, "completed")
        self.assertEqual(set(result.output.keys()),
                         {"base", "optimistic", "pessimistic"})
        # Pessimistic ROI must be null
        self.assertIsNone(result.output["pessimistic"]["roi"])

    def test_profit_agent_unknown_scenario_fails(self):
        config = load_amazon_config()
        ctx = WorkflowContext(config=config, cli_args={"scenario": "bogus"})
        agent = ProfitAgent()
        result = agent.run(ctx, profit_input=make_amazon_profit_input())
        self.assertEqual(result.status, "failed")
        self.assertIn("bogus", result.error)

    def test_profit_agent_no_input_incomplete(self):
        config = load_amazon_config()
        ctx = WorkflowContext(config=config, cli_args={"scenario": "base"})
        agent = ProfitAgent()
        result = agent.run(ctx, profit_input=None)
        self.assertEqual(result.status, "incomplete")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
