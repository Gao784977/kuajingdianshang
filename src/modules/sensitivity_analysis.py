"""Sensitivity analysis for opportunities.

For each opportunity, sweeps the configured parameters (unit_price,
estimated_units, variable_cost_per_unit, expected_monthly_operating_cost)
across the configured percentage range and records the resulting revenue,
net monthly profit, gross margin, payback, total score and grade.

The analysis does not modify the main result; it is purely additive.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .config_loader import get_sensitivity_config
from .csv_import import Opportunity
from .opportunity_scoring import EconomicsInput, score_opportunity
from .profit_calculator import calculate_profit

# Maps sensitivity parameter names to Opportunity attribute names.
_PARAM_TO_ATTR = {
    "unit_price": "unit_price",
    "estimated_units": "estimated_units",
    "variable_cost_per_unit": "variable_cost_per_unit",
    "expected_monthly_operating_cost": "expected_monthly_operating_cost",
}


@dataclass
class SensitivityPoint:
    """A single sensitivity data point."""

    parameter: str
    delta_percent: int
    revenue: Decimal
    net_monthly_profit: Decimal
    gross_margin: Decimal
    payback_months: Optional[Decimal]
    total_score: int
    grade: str
    recommendation_changed: bool


@dataclass
class OpportunitySensitivity:
    """Full sensitivity analysis for one opportunity."""

    opportunity_id: str
    base_grade: str
    base_score: int
    points: List[SensitivityPoint] = field(default_factory=list)
    most_impactful_parameter: str = ""
    grade_crossing_parameters: List[str] = field(default_factory=list)
    price_sensitive: bool = False
    cost_sensitive: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "base_grade": self.base_grade,
            "base_score": self.base_score,
            "most_impactful_parameter": self.most_impactful_parameter,
            "grade_crossing_parameters": self.grade_crossing_parameters,
            "price_sensitive": self.price_sensitive,
            "cost_sensitive": self.cost_sensitive,
            "points": [
                {
                    "parameter": p.parameter,
                    "delta_percent": p.delta_percent,
                    "revenue": str(p.revenue),
                    "net_monthly_profit": str(p.net_monthly_profit),
                    "gross_margin": str(p.gross_margin),
                    "payback_months": (
                        str(p.payback_months) if p.payback_months is not None else None
                    ),
                    "total_score": p.total_score,
                    "grade": p.grade,
                    "recommendation_changed": p.recommendation_changed,
                }
                for p in self.points
            ],
        }


def _adjust_param(opp: Opportunity, param: str, factor: Decimal) -> Opportunity:
    """Return a copy of opp with the given parameter multiplied by factor."""
    new_opp = deepcopy(opp)
    attr = _PARAM_TO_ATTR[param]
    setattr(new_opp, attr, (getattr(new_opp, attr) * factor))
    return new_opp


def analyze_sensitivity(
    opp: Opportunity,
    config: Dict[str, Any],
    scoring_version: str,
    calculation_version: str,
    parameters: Optional[List[str]] = None,
) -> OpportunitySensitivity:
    """Run sensitivity analysis for a single opportunity."""
    sens_cfg = get_sensitivity_config(config)
    if parameters is None:
        parameters = sens_cfg["parameters"]
    range_percents = sens_cfg["range_percents"]

    # Base case metrics (no adjustment).
    base_profit = calculate_profit(opp, calculation_version=calculation_version)
    base_econ = EconomicsInput(
        revenue=base_profit.revenue,
        gross_profit=base_profit.gross_profit,
        gross_margin=base_profit.gross_margin,
        gross_payback_months=base_profit.gross_payback_months,
        net_payback_months=base_profit.net_payback_months,
    )
    base_score = score_opportunity(
        opp, scoring_version=scoring_version, config=config, economics=base_econ
    )

    result = OpportunitySensitivity(
        opportunity_id=opp.opportunity_id,
        base_grade=base_score.grade,
        base_score=base_score.total_score,
    )

    # Track score range per parameter to find the most impactful.
    score_ranges: Dict[str, int] = {}
    grade_crossing: set = set()

    for param in parameters:
        scores: List[int] = []
        for delta in range_percents:
            factor = Decimal("1") + (Decimal(delta) / Decimal("100"))
            adj_opp = _adjust_param(opp, param, factor)
            profit = calculate_profit(adj_opp, calculation_version=calculation_version)
            econ = EconomicsInput(
                revenue=profit.revenue,
                gross_profit=profit.gross_profit,
                gross_margin=profit.gross_margin,
                gross_payback_months=profit.gross_payback_months,
                net_payback_months=profit.net_payback_months,
            )
            score = score_opportunity(
                adj_opp,
                scoring_version=scoring_version,
                config=config,
                economics=econ,
            )
            changed = score.grade != base_score.grade
            if changed:
                grade_crossing.add(param)
            scores.append(score.total_score)
            result.points.append(
                SensitivityPoint(
                    parameter=param,
                    delta_percent=int(delta),
                    revenue=profit.revenue,
                    net_monthly_profit=profit.net_monthly_profit,
                    gross_margin=profit.gross_margin,
                    payback_months=profit.net_payback_months,
                    total_score=score.total_score,
                    grade=score.grade,
                    recommendation_changed=changed,
                )
            )
        if scores:
            score_ranges[param] = max(scores) - min(scores)

    if score_ranges:
        result.most_impactful_parameter = max(
            score_ranges, key=lambda k: score_ranges[k]
        )
    result.grade_crossing_parameters = sorted(grade_crossing)
    result.price_sensitive = "unit_price" in grade_crossing
    result.cost_sensitive = any(
        p in grade_crossing
        for p in ("variable_cost_per_unit", "expected_monthly_operating_cost")
    )
    return result
