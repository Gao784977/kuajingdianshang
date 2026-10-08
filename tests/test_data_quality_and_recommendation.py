"""Tests for src.modules.data_quality and recommendation.

Covers:
- Data quality checks (error/warning/info)
- Recommendation detail and human_review_required logic
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from src.modules.data_quality import check_data_quality, summarize_issues
from src.modules.profit_calculator import calculate_profit
from src.modules.recommendation import build_recommendation
from src.modules.scenario_calculator import ScenarioResult

from tests._helpers import make_opportunity


class TestDataQuality(unittest.TestCase):
    def test_zero_revenue_warning(self) -> None:
        opp = make_opportunity(
            estimated_units=Decimal("0"),
            expected_monthly_revenue=None,
        )
        p = calculate_profit(opp)
        issues = check_data_quality([opp], [p])
        checks = {i.check for i in issues}
        self.assertIn("zero_revenue", checks)

    def test_negative_profit_warning(self) -> None:
        opp = make_opportunity(
            estimated_units=Decimal("100"),
            unit_price=Decimal("50"),
            variable_cost_per_unit=Decimal("60"),
        )
        p = calculate_profit(opp)
        issues = check_data_quality([opp], [p])
        checks = {i.check for i in issues}
        self.assertIn("negative_profit", checks)

    def test_revenue_inconsistency_warning(self) -> None:
        opp = make_opportunity(
            estimated_units=Decimal("1000"),
            unit_price=Decimal("100"),
            expected_monthly_revenue=Decimal("150000"),
        )
        p = calculate_profit(opp)
        issues = check_data_quality([opp], [p])
        checks = {i.check for i in issues}
        self.assertIn("revenue_inconsistency", checks)

    def test_high_risk_delivery_warning(self) -> None:
        opp = make_opportunity(
            competition_level="high",
            delivery_difficulty="high",
        )
        p = calculate_profit(opp)
        issues = check_data_quality([opp], [p])
        checks = {i.check for i in issues}
        self.assertIn("high_risk_delivery", checks)

    def test_long_payback_warning(self) -> None:
        opp = make_opportunity(
            initial_investment=Decimal("2000000"),
            expected_monthly_operating_cost=Decimal("10000"),
        )
        p = calculate_profit(opp)
        # net = 100000 - 30000 - 10000 = 60000; payback = 2000000/60000 ~ 33 > 24
        issues = check_data_quality([opp], [p], payback_warning_months=Decimal("24"))
        checks = {i.check for i in issues}
        self.assertIn("long_payback", checks)

    def test_summarize_issues(self) -> None:
        opp = make_opportunity()
        p = calculate_profit(opp)
        issues = check_data_quality([opp], [p])
        summary = summarize_issues(issues)
        self.assertIn("error", summary)
        self.assertIn("warning", summary)
        self.assertIn("info", summary)


class TestRecommendation(unittest.TestCase):
    def _make_scenarios(self, opp, base_net, pessimistic_net):
        """Build minimal ScenarioResult list for recommendation tests."""
        from src.modules.profit_calculator import ProfitResult
        from src.modules.opportunity_scoring import ScoringResult

        def _profit(net):
            return ProfitResult(
                opportunity_id=opp.opportunity_id,
                revenue=Decimal("100000"),
                variable_cost=Decimal("30000"),
                fixed_cost=Decimal("10000"),
                marketing_cost=Decimal("5000"),
                implementation_cost=Decimal("5000"),
                total_cost=Decimal("50000"),
                gross_profit=Decimal("50000"),
                gross_margin=Decimal("0.5"),
                initial_investment=Decimal("100000"),
                payback_months=Decimal("2"),
                monthly_operating_cost=Decimal("20000"),
                net_monthly_profit=net,
                annualized_profit=net * 12,
                calculation_version="calculation_v2",
            )

        base = ScenarioResult(
            scenario="base",
            profit=_profit(base_net),
            score=ScoringResult(
                opportunity_id=opp.opportunity_id,
                demand_score=30, economics_score=30, strategy_score=20,
                feasibility_score=20, total_score=100, grade="A",
                scoring_version="scoring_v2", payback_metric="net_monthly_profit",
            ),
        )
        pess = ScenarioResult(
            scenario="pessimistic",
            profit=_profit(pessimistic_net),
            score=base.score,
        )
        return [base, pess]

    def test_a_grade_high_confidence_when_pessimistic_positive(self) -> None:
        opp = make_opportunity()
        scens = self._make_scenarios(opp, Decimal("50000"), Decimal("10000"))
        rec = build_recommendation(opp, "A", scens)
        self.assertEqual(rec.recommendation, "proceed_to_review")
        self.assertEqual(rec.confidence, "high")
        self.assertFalse(rec.human_review_required)

    def test_a_grade_human_review_when_pessimistic_negative(self) -> None:
        opp = make_opportunity()
        scens = self._make_scenarios(opp, Decimal("50000"), Decimal("-5000"))
        rec = build_recommendation(opp, "A", scens)
        self.assertTrue(rec.human_review_required)
        self.assertIn("悲观情景", "".join(rec.blockers))

    def test_high_risk_triggers_human_review(self) -> None:
        opp = make_opportunity(competition_level="high", delivery_difficulty="high")
        scens = self._make_scenarios(opp, Decimal("50000"), Decimal("10000"))
        rec = build_recommendation(opp, "A", scens)
        self.assertTrue(rec.human_review_required)

    def test_revenue_inconsistency_triggers_human_review(self) -> None:
        opp = make_opportunity(
            expected_monthly_revenue=Decimal("150000"),
            estimated_units=Decimal("1000"),
            unit_price=Decimal("100"),
        )
        from src.modules.profit_calculator import calculate_profit

        p = calculate_profit(opp)
        # craft scenarios with the consistency warning
        from src.modules.profit_calculator import ProfitResult
        from src.modules.opportunity_scoring import ScoringResult

        p2 = ProfitResult(
            opportunity_id=opp.opportunity_id,
            revenue=p.revenue, variable_cost=p.variable_cost,
            fixed_cost=p.fixed_cost, marketing_cost=p.marketing_cost,
            implementation_cost=p.implementation_cost, total_cost=p.total_cost,
            gross_profit=p.gross_profit, gross_margin=p.gross_margin,
            initial_investment=p.initial_investment, payback_months=p.payback_months,
            monthly_operating_cost=p.monthly_operating_cost,
            net_monthly_profit=p.net_monthly_profit,
            annualized_profit=p.annualized_profit,
            calculation_version="calculation_v2",
            revenue_consistency_warning=True,
        )
        s = ScoringResult(
            opportunity_id=opp.opportunity_id,
            demand_score=30, economics_score=30, strategy_score=20,
            feasibility_score=20, total_score=100, grade="A",
            scoring_version="scoring_v2", payback_metric="net_monthly_profit",
        )
        scens = [ScenarioResult(scenario="base", profit=p2, score=s)]
        rec = build_recommendation(opp, "A", scens)
        self.assertTrue(rec.human_review_required)

    def test_b_grade_requires_validation(self) -> None:
        opp = make_opportunity()
        scens = self._make_scenarios(opp, Decimal("50000"), Decimal("10000"))
        rec = build_recommendation(opp, "B", scens)
        self.assertEqual(rec.recommendation, "validate_before_review")
        self.assertTrue(len(rec.required_validation) > 0)

    def test_d_grade_reject(self) -> None:
        opp = make_opportunity()
        scens = self._make_scenarios(opp, Decimal("50000"), Decimal("10000"))
        rec = build_recommendation(opp, "D", scens)
        self.assertEqual(rec.recommendation, "reject_or_hold")

    def test_sensitivity_grade_drop_triggers_review(self) -> None:
        opp = make_opportunity()
        scens = self._make_scenarios(opp, Decimal("50000"), Decimal("10000"))
        rec = build_recommendation(opp, "A", scens, sensitivity_grade_drop=True)
        self.assertTrue(rec.human_review_required)


if __name__ == "__main__":
    unittest.main()
