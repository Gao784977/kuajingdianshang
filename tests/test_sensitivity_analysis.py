"""Tests for src.modules.sensitivity_analysis.

Covers Case 15: sensitivity analysis.
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from src.modules.config_loader import load_config
from src.modules.sensitivity_analysis import analyze_sensitivity

from tests._helpers import make_opportunity


class TestSensitivityAnalysis(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.opp = make_opportunity()

    def test_sensitivity_produces_points(self) -> None:
        result = analyze_sensitivity(
            self.opp,
            config=self.config,
            scoring_version="scoring_v2",
            calculation_version="calculation_v2",
        )
        self.assertEqual(result.opportunity_id, "T-001")
        self.assertTrue(len(result.points) > 0)
        # 4 parameters * 5 deltas = 20 points
        self.assertEqual(len(result.points), 20)

    def test_sensitivity_includes_zero_delta(self) -> None:
        result = analyze_sensitivity(
            self.opp,
            config=self.config,
            scoring_version="scoring_v2",
            calculation_version="calculation_v2",
        )
        zero_points = [p for p in result.points if p.delta_percent == 0]
        self.assertTrue(len(zero_points) > 0)

    def test_sensitivity_most_impactful_parameter(self) -> None:
        result = analyze_sensitivity(
            self.opp,
            config=self.config,
            scoring_version="scoring_v2",
            calculation_version="calculation_v2",
        )
        self.assertIn(
            result.most_impactful_parameter,
            ("unit_price", "estimated_units", "variable_cost_per_unit", "expected_monthly_operating_cost"),
        )

    def test_sensitivity_custom_parameters(self) -> None:
        result = analyze_sensitivity(
            self.opp,
            config=self.config,
            scoring_version="scoring_v2",
            calculation_version="calculation_v2",
            parameters=["unit_price"],
        )
        params_in_result = {p.parameter for p in result.points}
        self.assertEqual(params_in_result, {"unit_price"})

    def test_sensitivity_to_dict_is_serializable(self) -> None:
        import json

        result = analyze_sensitivity(
            self.opp,
            config=self.config,
            scoring_version="scoring_v2",
            calculation_version="calculation_v2",
        )
        d = result.to_dict()
        # should not raise
        json.dumps(d)


if __name__ == "__main__":
    unittest.main()
