"""Scenario calculation (base / optimistic / pessimistic).

Applies configurable multipliers to the opportunity inputs and computes
profit + scoring for each requested scenario. Scenarios do not change
demand, strategy or feasibility scores; only the economics sub-score and
final grade vary.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .config_loader import get_scenario_multipliers
from .csv_import import Opportunity
from .opportunity_scoring import EconomicsInput, ScoringResult, score_opportunity
from .profit_calculator import ProfitResult, calculate_profit

_SCENARIO_ORDER = ("base", "optimistic", "pessimistic")


@dataclass
class ScenarioResult:
    """Profit + scoring outcome for a single scenario."""

    scenario: str
    profit: ProfitResult
    score: ScoringResult

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario": self.scenario,
            "profit": self.profit.to_dict(),
            "score": self.score.to_dict(),
        }


def resolve_scenarios(scenario_arg: str) -> List[str]:
    """Resolve the --scenario argument into a list of scenario names."""
    if scenario_arg == "all":
        return list(_SCENARIO_ORDER)
    if scenario_arg not in _SCENARIO_ORDER:
        raise ValueError(
            f"Unknown scenario '{scenario_arg}'. "
            f"Choose from: {', '.join(_SCENARIO_ORDER)}, all."
        )
    return [scenario_arg]


def calculate_scenarios(
    opp: Opportunity,
    config: Dict[str, Any],
    scenarios: List[str],
    scoring_version: str,
    calculation_version: str,
    revenue_consistency_threshold: Decimal = Decimal("0.10"),
) -> List[ScenarioResult]:
    """Compute profit and score for each requested scenario."""
    results: List[ScenarioResult] = []
    for name in scenarios:
        multipliers = get_scenario_multipliers(config, name)
        profit = calculate_profit(
            opp,
            calculation_version=calculation_version,
            scenario_multipliers=multipliers,
            scenario_name=name,
            revenue_consistency_threshold=revenue_consistency_threshold,
        )
        economics = EconomicsInput(
            revenue=profit.revenue,
            gross_profit=profit.gross_profit,
            gross_margin=profit.gross_margin,
            gross_payback_months=profit.gross_payback_months,
            net_payback_months=profit.net_payback_months,
        )
        score = score_opportunity(
            opp,
            scoring_version=scoring_version,
            config=config,
            economics=economics,
        )
        results.append(ScenarioResult(scenario=name, profit=profit, score=score))
    return results
