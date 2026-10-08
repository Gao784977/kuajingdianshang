"""Tests for src.modules.profit_calculator."""

from __future__ import annotations

import unittest
from decimal import Decimal

from src.modules.profit_calculator import calculate_profit

from tests._helpers import make_opportunity


class TestProfitCalculator(unittest.TestCase):
    def test_revenue_fallback_when_expected_monthly_revenue_empty(self) -> None:
        # expected_monthly_revenue is None -> revenue = units * price
        opp = make_opportunity(
            estimated_units=Decimal("1000"),
            unit_price=Decimal("100"),
            expected_monthly_revenue=None,
        )
        result = calculate_profit(opp)
        self.assertEqual(result.revenue, Decimal("100000.00"))

    def test_revenue_uses_expected_monthly_revenue_when_present(self) -> None:
        opp = make_opportunity(
            estimated_units=Decimal("1000"),
            unit_price=Decimal("100"),
            expected_monthly_revenue=Decimal("120000"),
        )
        result = calculate_profit(opp)
        self.assertEqual(result.revenue, Decimal("120000.00"))

    def test_gross_margin_calculation(self) -> None:
        # revenue 100000, variable 30000, fixed 10000, marketing 5000, impl 5000
        # total 50000, gross 50000, margin 0.5
        opp = make_opportunity()
        result = calculate_profit(opp)
        self.assertEqual(result.gross_profit, Decimal("50000.00"))
        self.assertEqual(result.gross_margin, Decimal("0.5000"))

    def test_gross_margin_zero_when_no_revenue(self) -> None:
        opp = make_opportunity(
            estimated_units=Decimal("0"),
            unit_price=Decimal("100"),
            expected_monthly_revenue=None,
        )
        result = calculate_profit(opp)
        self.assertEqual(result.revenue, Decimal("0.00"))
        self.assertEqual(result.gross_margin, Decimal("0.0000"))

    def test_payback_null_when_negative_profit(self) -> None:
        opp = make_opportunity(
            estimated_units=Decimal("100"),
            unit_price=Decimal("50"),
            variable_cost_per_unit=Decimal("60"),
            fixed_cost=Decimal("2000"),
            marketing_cost=Decimal("1000"),
            implementation_cost=Decimal("1000"),
            expected_monthly_operating_cost=Decimal("3000"),
            initial_investment=Decimal("50000"),
        )
        result = calculate_profit(opp)
        # net_monthly_profit = 5000 - 6000 - 3000 = -4000 <= 0 -> payback null
        self.assertLess(result.net_monthly_profit, 0)
        self.assertIsNone(result.payback_months)

    def test_payback_calculation_when_positive_profit(self) -> None:
        # revenue 100000, variable 30000, operating 20000
        # net_monthly_profit = 100000 - 30000 - 20000 = 50000
        # initial_investment 100000 -> payback = 2.0
        opp = make_opportunity(
            initial_investment=Decimal("100000"),
            expected_monthly_operating_cost=Decimal("20000"),
        )
        result = calculate_profit(opp)
        self.assertEqual(result.net_monthly_profit, Decimal("50000.00"))
        self.assertEqual(result.payback_months, Decimal("2.00"))

    def test_annualized_profit(self) -> None:
        opp = make_opportunity()
        result = calculate_profit(opp)
        # net_monthly = 100000 - 30000 - 20000 = 50000; annual = 600000
        self.assertEqual(result.annualized_profit, Decimal("600000.00"))

    def test_total_cost_breakdown(self) -> None:
        opp = make_opportunity()
        result = calculate_profit(opp)
        self.assertEqual(result.variable_cost, Decimal("30000.00"))
        self.assertEqual(result.fixed_cost, Decimal("10000.00"))
        self.assertEqual(result.marketing_cost, Decimal("5000.00"))
        self.assertEqual(result.implementation_cost, Decimal("5000.00"))
        self.assertEqual(result.total_cost, Decimal("50000.00"))

    def test_calculation_version(self) -> None:
        result = calculate_profit(make_opportunity())
        self.assertEqual(result.calculation_version, "calculation_v1")


if __name__ == "__main__":
    unittest.main()
