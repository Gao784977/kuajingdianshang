"""Tests for src.modules.scenario_calculator.

Covers:
- Case 5: base scenario calculation
- Case 6: optimistic scenario calculation
- Case 7: pessimistic scenario calculation
- Case 8: --scenario all
"""

from __future__ import annotations

import unittest
from decimal import Decimal

from src.modules.config_loader import load_config
from src.modules.opportunity_scoring import score_opportunity
from src.modules.profit_calculator import calculate_profit
from src.modules.scenario_calculator import (
    calculate_scenarios,
    resolve_scenarios,
)

from tests._helpers import make_opportunity


class TestScenarioCalculator(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config()
        self.opp = make_opportunity()

    def test_resolve_base(self) -> None:
        self.assertEqual(resolve_scenarios("base"), ["base"])

    def test_resolve_all(self) -> None:
        self.assertEqual(
            resolve_scenarios("all"), ["base", "optimistic", "pessimistic"]
        )

    def test_resolve_unknown_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_scenarios("fantasy")

    def test_base_scenario(self) -> None:
        # Case 5
        results = calculate_scenarios(
            self.opp,
            config=self.config,
            scenarios=["base"],
            scoring_version="scoring_v2",
            calculation_version="calculation_v2",
        )
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertEqual(r.scenario, "base")
        # base multipliers are 1.0, so revenue = units * price = 100000
        self.assertEqual(r.profit.revenue, Decimal("100000.00"))

    def test_optimistic_scenario(self) -> None:
        # Case 6: optimistic has higher price and units
        results = calculate_scenarios(
            self.opp,
            config=self.config,
            scenarios=["optimistic"],
            scoring_version="scoring_v2",
            calculation_version="calculation_v2",
        )
        r = results[0]
        self.assertEqual(r.scenario, "optimistic")
        # optimistic: units*1.2 * price*1.05 = 1200 * 105 = 126000
        self.assertEqual(r.profit.revenue, Decimal("126000.00"))

    def test_pessimistic_scenario(self) -> None:
        # Case 7: pessimistic has lower price and units, higher costs
        results = calculate_scenarios(
            self.opp,
            config=self.config,
            scenarios=["pessimistic"],
            scoring_version="scoring_v2",
            calculation_version="calculation_v2",
        )
        r = results[0]
        self.assertEqual(r.scenario, "pessimistic")
        # pessimistic: units*0.7 * price*0.9 = 700 * 90 = 63000
        self.assertEqual(r.profit.revenue, Decimal("63000.00"))

    def test_scenario_all(self) -> None:
        # Case 8
        results = calculate_scenarios(
            self.opp,
            config=self.config,
            scenarios=["base", "optimistic", "pessimistic"],
            scoring_version="scoring_v2",
            calculation_version="calculation_v2",
        )
        names = [r.scenario for r in results]
        self.assertEqual(names, ["base", "optimistic", "pessimistic"])
        # revenue ordering: optimistic > base > pessimistic
        revenues = [r.profit.revenue for r in results]
        self.assertGreater(revenues[1], revenues[0])
        self.assertGreater(revenues[0], revenues[2])

    def test_scenarios_do_not_change_demand_score(self) -> None:
        results = calculate_scenarios(
            self.opp,
            config=self.config,
            scenarios=["base", "optimistic", "pessimistic"],
            scoring_version="scoring_v2",
            calculation_version="calculation_v2",
        )
        demand_scores = [r.score.demand_score for r in results]
        # All scenarios should have the same demand score
        self.assertEqual(len(set(demand_scores)), 1)


if __name__ == "__main__":
    unittest.main()
