"""Tests for v2 revenue source, payback, and profit features.

Covers:
- Case 9: revenue source = input value
- Case 10: revenue source = units * unit_price
- Case 11: revenue difference warning
- Case 12: gross_payback_months
- Case 13: net_payback_months
- Case 14: negative profit -> payback null
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from src.modules.profit_calculator import calculate_profit

from tests._helpers import make_opportunity


class TestRevenueSource(unittest.TestCase):
    def test_revenue_source_input(self) -> None:
        # Case 9: expected_monthly_revenue present -> source = "input"
        opp = make_opportunity(
            estimated_units=Decimal("1000"),
            unit_price=Decimal("100"),
            expected_monthly_revenue=Decimal("120000"),
        )
        result = calculate_profit(opp)
        self.assertEqual(result.revenue_source, "input")
        self.assertEqual(result.revenue, Decimal("120000.00"))
        self.assertEqual(result.input_expected_monthly_revenue, Decimal("120000.00"))
        self.assertEqual(result.final_revenue, Decimal("120000.00"))

    def test_revenue_source_calculated(self) -> None:
        # Case 10: expected_monthly_revenue None -> source = "calculated"
        opp = make_opportunity(
            estimated_units=Decimal("1000"),
            unit_price=Decimal("100"),
            expected_monthly_revenue=None,
        )
        result = calculate_profit(opp)
        self.assertEqual(result.revenue_source, "calculated")
        self.assertEqual(result.calculated_units_revenue, Decimal("100000.00"))
        self.assertEqual(result.final_revenue, Decimal("100000.00"))

    def test_revenue_consistency_warning(self) -> None:
        # Case 11: input revenue differs from units*price by > 10%
        opp = make_opportunity(
            estimated_units=Decimal("1000"),
            unit_price=Decimal("100"),
            expected_monthly_revenue=Decimal("150000"),  # 50% diff
        )
        result = calculate_profit(opp)
        self.assertTrue(result.revenue_consistency_warning)

    def test_no_warning_when_close(self) -> None:
        opp = make_opportunity(
            estimated_units=Decimal("1000"),
            unit_price=Decimal("100"),
            expected_monthly_revenue=Decimal("102000"),  # 2% diff
        )
        result = calculate_profit(opp)
        self.assertFalse(result.revenue_consistency_warning)


class TestPaybackMetrics(unittest.TestCase):
    def test_gross_and_net_payback(self) -> None:
        # Cases 12 & 13
        opp = make_opportunity(
            estimated_units=Decimal("1000"),
            unit_price=Decimal("100"),
            variable_cost_per_unit=Decimal("30"),
            fixed_cost=Decimal("10000"),
            marketing_cost=Decimal("5000"),
            implementation_cost=Decimal("5000"),
            initial_investment=Decimal("100000"),
            expected_monthly_operating_cost=Decimal("20000"),
        )
        result = calculate_profit(opp)
        # gross_profit = 100000 - 30000 - 10000 - 5000 - 5000 = 50000
        # gross_payback = 100000 / 50000 = 2.0
        self.assertEqual(result.gross_profit, Decimal("50000.00"))
        self.assertEqual(result.gross_payback_months, Decimal("2.00"))
        # net_monthly_profit = 100000 - 30000 - 20000 = 50000
        # net_payback = 100000 / 50000 = 2.0
        self.assertEqual(result.net_monthly_profit, Decimal("50000.00"))
        self.assertEqual(result.net_payback_months, Decimal("2.00"))

    def test_gross_payback_null_when_gross_negative(self) -> None:
        opp = make_opportunity(
            estimated_units=Decimal("100"),
            unit_price=Decimal("50"),
            variable_cost_per_unit=Decimal("60"),
            fixed_cost=Decimal("2000"),
            marketing_cost=Decimal("1000"),
            implementation_cost=Decimal("1000"),
            initial_investment=Decimal("50000"),
        )
        result = calculate_profit(opp)
        self.assertIsNone(result.gross_payback_months)

    def test_net_payback_null_when_net_negative(self) -> None:
        # Case 14
        opp = make_opportunity(
            estimated_units=Decimal("100"),
            unit_price=Decimal("50"),
            variable_cost_per_unit=Decimal("20"),
            fixed_cost=Decimal("1000"),
            marketing_cost=Decimal("500"),
            implementation_cost=Decimal("500"),
            expected_monthly_operating_cost=Decimal("5000"),
            initial_investment=Decimal("50000"),
        )
        result = calculate_profit(opp)
        # net = 5000 - 2000 - 5000 = -2000
        self.assertLess(result.net_monthly_profit, 0)
        self.assertIsNone(result.net_payback_months)
        # backward-compat alias
        self.assertIsNone(result.payback_months)


if __name__ == "__main__":
    unittest.main()
