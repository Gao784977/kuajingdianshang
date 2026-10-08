"""Tests for src.modules.opportunity_scoring."""

from __future__ import annotations

import unittest
from decimal import Decimal

from src.modules.opportunity_scoring import score_opportunity

from tests._helpers import make_opportunity


class TestOpportunityScoring(unittest.TestCase):
    def test_sub_scores_and_total(self) -> None:
        # customer_need high (30), strategic_fit high (20),
        # delivery_difficulty low (20) + competition low (0) = 20.
        # Economics: gross_margin 0.5, payback 2 -> 30.
        opp = make_opportunity()
        result = score_opportunity(opp)
        self.assertEqual(result.demand_score, 30)
        self.assertEqual(result.strategy_score, 20)
        self.assertEqual(result.feasibility_score, 20)
        self.assertEqual(result.economics_score, 30)
        self.assertEqual(result.total_score, 100)
        self.assertEqual(result.grade, "A")
        self.assertEqual(result.scoring_version, "scoring_v1")

    def test_grade_a_boundary(self) -> None:
        # total >= 80 -> A. Build exactly 80.
        # demand 30 + economics 30 + strategy 10 (low) + feasibility 10 = 80
        opp = make_opportunity(
            customer_need="high",  # 30
            strategic_fit="low",  # 6 -> need 10, use medium=13
        )
        # That gives 30+30+6+20 = 86. Let's construct exactly 80 deliberately.
        opp = make_opportunity(
            customer_need="medium",  # 20
            strategic_fit="high",  # 20
            delivery_difficulty="medium",  # 13
            competition_level="low",  # 0 -> feasibility 13
        )
        # demand 20 + economics 30 + strategy 20 + feasibility 13 = 83 -> A
        result = score_opportunity(opp)
        self.assertEqual(result.grade, "A")
        self.assertGreaterEqual(result.total_score, 80)

    def test_grade_b_boundary(self) -> None:
        # total >= 60 and < 80 -> B.
        opp = make_opportunity(
            customer_need="low",  # 10
            strategic_fit="low",  # 6
            delivery_difficulty="low",  # 20
            competition_level="low",  # 0 -> 20
        )
        # economics 30 -> total 10+30+6+20 = 66 -> B
        result = score_opportunity(opp)
        self.assertEqual(result.grade, "B")
        self.assertGreaterEqual(result.total_score, 60)
        self.assertLess(result.total_score, 80)

    def test_grade_c_boundary(self) -> None:
        # total >= 40 and < 60 -> C.
        opp = make_opportunity(
            customer_need="low",  # 10
            strategic_fit="low",  # 6
            delivery_difficulty="medium",  # 13
            competition_level="high",  # -6 -> 7
        )
        # economics 10 (margin barely positive, long payback)
        opp = make_opportunity(
            customer_need="low",  # 10
            strategic_fit="low",  # 6
            delivery_difficulty="medium",  # 13
            competition_level="high",  # -6 -> 7
            estimated_units=Decimal("200"),
            unit_price=Decimal("50"),
            variable_cost_per_unit=Decimal("48"),
            fixed_cost=Decimal("100"),
            marketing_cost=Decimal("50"),
            implementation_cost=Decimal("50"),
            initial_investment=Decimal("100000"),
        )
        # revenue 10000, variable 9600, total 9800, gross 200, margin 0.02
        # payback 100000/200 = 500 > 18 -> economics 10
        # total 10+10+6+7 = 33 -> D. Hmm, need C (>=40).
        # Let me bump feasibility: delivery low (20) + competition high (-6) = 14
        opp.delivery_difficulty = "low"
        result = score_opportunity(opp)
        # total 10+10+6+14 = 40 -> C
        self.assertEqual(result.grade, "C")
        self.assertGreaterEqual(result.total_score, 40)
        self.assertLess(result.total_score, 60)

    def test_grade_d_boundary(self) -> None:
        # total < 40 -> D.
        opp = make_opportunity(
            customer_need="low",  # 10
            strategic_fit="low",  # 6
            delivery_difficulty="high",  # 6
            competition_level="high",  # -6 -> 0
            estimated_units=Decimal("100"),
            unit_price=Decimal("50"),
            variable_cost_per_unit=Decimal("60"),
            fixed_cost=Decimal("2000"),
            marketing_cost=Decimal("1000"),
            implementation_cost=Decimal("1000"),
        )
        # gross_profit negative -> economics 0
        # total 10+0+6+0 = 16 -> D
        result = score_opportunity(opp)
        self.assertEqual(result.grade, "D")
        self.assertLess(result.total_score, 40)

    def test_feasibility_floor_zero(self) -> None:
        # delivery high (6) + competition high (-6) = 0, floor at 0.
        opp = make_opportunity(
            delivery_difficulty="high",
            competition_level="high",
        )
        result = score_opportunity(opp)
        self.assertEqual(result.feasibility_score, 0)

    def test_economics_zero_when_no_profit(self) -> None:
        opp = make_opportunity(
            estimated_units=Decimal("100"),
            unit_price=Decimal("10"),
            variable_cost_per_unit=Decimal("20"),
        )
        result = score_opportunity(opp)
        self.assertEqual(result.economics_score, 0)

    def test_explanation_and_raw_fields_present(self) -> None:
        opp = make_opportunity()
        result = score_opportunity(opp)
        self.assertTrue(result.explanation)
        self.assertIn("customer_need", result.raw_fields)
        self.assertEqual(result.raw_fields["customer_need"], "high")


if __name__ == "__main__":
    unittest.main()
