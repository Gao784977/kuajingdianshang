"""Opportunity scoring model (config-driven, scoring_v1 / scoring_v2).

Total score is 100 points, composed of four sub-scores whose weights are
defined in the config and must sum to 100:

* Market demand          - derived from ``customer_need``
* Economic return        - derived from gross margin and payback months
* Strategic fit          - derived from ``strategic_fit``
* Execution feasibility  - derived from ``delivery_difficulty`` and
  ``competition_level``

The economic sub-score uses a payback metric chosen by the scoring
version: ``scoring_v1`` uses ``gross_payback_months`` (gross profit),
``scoring_v2`` uses ``net_payback_months`` (net monthly profit).

Scoring rules are read from the config. A hardcoded v1 fallback is kept
only so that the module remains importable even if the config is
temporarily unavailable during tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, Optional

from .csv_import import Opportunity

DEFAULT_SCORING_VERSION = "scoring_v1"

# Hardcoded v1 fallback used only when no config is supplied. Kept for
# backward compatibility and to avoid breaking v1 tests that call
# score_opportunity without a config.
_V1_FALLBACK = {
    "score_weights": {"demand": 30, "economics": 30, "strategy": 20, "feasibility": 20},
    "customer_need_scores": {"high": 30, "medium": 20, "low": 10},
    "strategic_fit_scores": {"high": 20, "medium": 13, "low": 6},
    "delivery_difficulty_scores": {"low": 20, "medium": 13, "high": 6},
    "competition_penalties": {"low": 0, "medium": 3, "high": 6},
    "economics_score_bands": [
        {"min_margin": 0.40, "max_payback": 6, "score": 30},
        {"min_margin": 0.30, "max_payback": 12, "score": 24},
        {"min_margin": 0.20, "max_payback": 18, "score": 18},
    ],
    "economics_positive_score": 10,
    "economics_zero_score": 0,
    "grade_thresholds": {"A": 80, "B": 60, "C": 40, "D": 0},
    "payback_metric": "gross_profit",
}

_V2_FALLBACK = dict(_V1_FALLBACK, payback_metric="net_monthly_profit")


@dataclass
class EconomicsInput:
    """Economic metrics used to compute the economics sub-score.

    Allows scenarios to pass adjusted metrics instead of recomputing from
    the raw Opportunity.
    """

    revenue: Decimal
    gross_profit: Decimal
    gross_margin: Decimal
    gross_payback_months: Optional[Decimal]
    net_payback_months: Optional[Decimal]


@dataclass
class ScoringResult:
    """Result of scoring a single opportunity."""

    opportunity_id: str
    demand_score: int
    economics_score: int
    strategy_score: int
    feasibility_score: int
    total_score: int
    grade: str
    scoring_version: str
    payback_metric: str
    raw_fields: Dict[str, Any] = field(default_factory=dict)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "demand_score": self.demand_score,
            "economics_score": self.economics_score,
            "strategy_score": self.strategy_score,
            "feasibility_score": self.feasibility_score,
            "total_score": self.total_score,
            "grade": self.grade,
            "scoring_version": self.scoring_version,
            "payback_metric": self.payback_metric,
            "raw_fields": self.raw_fields,
            "explanation": self.explanation,
        }


def _get_rules(scoring_version: str, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return the scoring rules dict for the given version."""
    if config is not None:
        from .config_loader import get_scoring_rules

        return get_scoring_rules(config, scoring_version)
    # Fallback for backward compatibility when no config is provided.
    if scoring_version == "scoring_v1":
        return _V1_FALLBACK
    return _V2_FALLBACK


def _economics_score_from_metrics(
    rules: Dict[str, Any],
    gross_margin: Decimal,
    payback_months: Optional[Decimal],
) -> int:
    if gross_margin <= 0:
        return int(rules.get("economics_zero_score", 0))
    bands = rules.get("economics_score_bands", [])
    if payback_months is not None:
        for band in bands:
            if (
                gross_margin >= Decimal(str(band["min_margin"]))
                and payback_months <= Decimal(str(band["max_payback"]))
            ):
                return int(band["score"])
    return int(rules.get("economics_positive_score", 10))


def _grade_from_rules(total: int, rules: Dict[str, Any]) -> str:
    thresholds = rules["grade_thresholds"]
    for grade in ("A", "B", "C"):
        if total >= int(thresholds[grade]):
            return grade
    return "D"


def _compute_base_economics(opp: Opportunity) -> EconomicsInput:
    """Compute economics metrics directly from the Opportunity (base case)."""
    if opp.expected_monthly_revenue is not None:
        revenue = opp.expected_monthly_revenue
    else:
        revenue = opp.estimated_units * opp.unit_price
    variable_cost = opp.estimated_units * opp.variable_cost_per_unit
    total_cost = (
        variable_cost + opp.fixed_cost + opp.marketing_cost + opp.implementation_cost
    )
    gross_profit = revenue - total_cost
    gross_margin = (gross_profit / revenue) if revenue > 0 else Decimal("0")
    gross_payback = (
        opp.initial_investment / gross_profit if gross_profit > 0 else None
    )
    net_profit = revenue - variable_cost - opp.expected_monthly_operating_cost
    net_payback = (
        opp.initial_investment / net_profit if net_profit > 0 else None
    )
    return EconomicsInput(
        revenue=revenue,
        gross_profit=gross_profit,
        gross_margin=gross_margin,
        gross_payback_months=gross_payback,
        net_payback_months=net_payback,
    )


def score_opportunity(
    opp: Opportunity,
    scoring_version: str = DEFAULT_SCORING_VERSION,
    config: Optional[Dict[str, Any]] = None,
    economics: Optional[EconomicsInput] = None,
) -> ScoringResult:
    """Compute the full scoring result for one opportunity.

    Args:
        opp: The opportunity record.
        scoring_version: Which scoring rules to use (scoring_v1 / scoring_v2).
        config: Optional config dict. If None, a hardcoded fallback is used.
        economics: Optional pre-computed economics metrics (for scenarios).
            If None, metrics are computed from the opportunity directly.
    """
    rules = _get_rules(scoring_version, config)
    payback_metric = rules.get("payback_metric", "gross_profit")

    demand = int(rules["customer_need_scores"][opp.customer_need])
    strategy = int(rules["strategic_fit_scores"][opp.strategic_fit])

    feasibility_raw = int(
        rules["delivery_difficulty_scores"][opp.delivery_difficulty]
    ) - int(rules["competition_penalties"][opp.competition_level])
    feasibility = max(0, feasibility_raw)

    if economics is None:
        economics = _compute_base_economics(opp)

    if payback_metric == "net_monthly_profit":
        payback = economics.net_payback_months
    else:
        payback = economics.gross_payback_months

    economics_score = _economics_score_from_metrics(
        rules, economics.gross_margin, payback
    )

    total = demand + economics_score + strategy + feasibility
    grade = _grade_from_rules(total, rules)

    payback_text = (
        f"{payback:.2f}" if payback is not None else "null (no profit)"
    )
    explanation = (
        f"需求得分 {demand} (customer_need={opp.customer_need}); "
        f"经济收益得分 {economics_score} (gross_margin={economics.gross_margin:.4f}, "
        f"payback_metric={payback_metric}, payback_months={payback_text}); "
        f"战略匹配得分 {strategy} (strategic_fit={opp.strategic_fit}); "
        f"执行可行性得分 {feasibility} "
        f"(delivery_difficulty={opp.delivery_difficulty}, "
        f"competition_level={opp.competition_level})."
    )

    raw_fields = {
        "customer_need": opp.customer_need,
        "strategic_fit": opp.strategic_fit,
        "delivery_difficulty": opp.delivery_difficulty,
        "competition_level": opp.competition_level,
        "estimated_units": str(opp.estimated_units),
        "unit_price": str(opp.unit_price),
        "variable_cost_per_unit": str(opp.variable_cost_per_unit),
        "fixed_cost": str(opp.fixed_cost),
        "marketing_cost": str(opp.marketing_cost),
        "implementation_cost": str(opp.implementation_cost),
        "initial_investment": str(opp.initial_investment),
        "expected_monthly_revenue": (
            str(opp.expected_monthly_revenue)
            if opp.expected_monthly_revenue is not None
            else None
        ),
        "gross_margin": f"{economics.gross_margin:.4f}",
        "gross_payback_months": (
            f"{economics.gross_payback_months:.2f}"
            if economics.gross_payback_months is not None
            else None
        ),
        "net_payback_months": (
            f"{economics.net_payback_months:.2f}"
            if economics.net_payback_months is not None
            else None
        ),
        "payback_metric": payback_metric,
    }

    return ScoringResult(
        opportunity_id=opp.opportunity_id,
        demand_score=demand,
        economics_score=economics_score,
        strategy_score=strategy,
        feasibility_score=feasibility,
        total_score=total,
        grade=grade,
        scoring_version=scoring_version,
        payback_metric=payback_metric,
        raw_fields=raw_fields,
        explanation=explanation,
    )
