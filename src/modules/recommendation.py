"""Recommendation detail generation for opportunities.

Produces a structured recommendation (proceed_to_review /
validate_before_review / monitor / reject_or_hold) with reasons,
blockers, required validation, confidence and a human-review flag.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .csv_import import Opportunity
from .scenario_calculator import ScenarioResult

_RECOMMENDATION_BY_GRADE = {
    "A": "proceed_to_review",
    "B": "validate_before_review",
    "C": "monitor",
    "D": "reject_or_hold",
}

_GRADE_REASONS = {
    "A": "总分达到 A 级，建议进入正式立项评审。",
    "B": "总分达到 B 级，建议补充客户、价格或成本验证后再评审。",
    "C": "总分处于 C 级，建议保留观察，暂不投入较大资源。",
    "D": "总分低于 40，建议暂不立项。",
}

_PAYBACK_WARN_MONTHS = Decimal("24")


@dataclass
class RecommendationDetail:
    opportunity_id: str
    recommendation: str
    grade: str
    reasons: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    required_validation: List[str] = field(default_factory=list)
    confidence: str = "medium"  # high | medium | low
    human_review_required: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "recommendation": self.recommendation,
            "grade": self.grade,
            "reasons": self.reasons,
            "blockers": self.blockers,
            "required_validation": self.required_validation,
            "confidence": self.confidence,
            "human_review_required": self.human_review_required,
        }


def build_recommendation(
    opp: Opportunity,
    base_score_grade: str,
    scenario_results: List[ScenarioResult],
    sensitivity_grade_drop: bool = False,
    has_boundary_or_missing: bool = False,
) -> RecommendationDetail:
    """Build the recommendation detail for one opportunity.

    Args:
        opp: The opportunity record.
        base_score_grade: The grade of the base scenario.
        scenario_results: All computed scenario results for this opp.
        sensitivity_grade_drop: True if sensitivity analysis caused the
            grade to drop by two or more levels.
        has_boundary_or_missing: True if input data has boundary values
            or missing key data.
    """
    rec = _RECOMMENDATION_BY_GRADE.get(base_score_grade, "reject_or_hold")
    detail = RecommendationDetail(
        opportunity_id=opp.opportunity_id,
        recommendation=rec,
        grade=base_score_grade,
    )
    detail.reasons.append(_GRADE_REASONS.get(base_score_grade, ""))

    profit_by_scenario = {s.scenario: s.profit for s in scenario_results}
    score_by_scenario = {s.scenario: s.score for s in scenario_results}

    base_profit = profit_by_scenario.get("base")
    pessimistic_profit = profit_by_scenario.get("pessimistic")

    # Confidence & human review for A grade based on pessimistic scenario.
    if base_score_grade == "A":
        if pessimistic_profit is not None and pessimistic_profit.net_monthly_profit > 0:
            detail.confidence = "high"
        if pessimistic_profit is not None and pessimistic_profit.net_monthly_profit <= 0:
            detail.human_review_required = True
            detail.blockers.append("悲观情景下月净利润为负。")
            detail.confidence = "medium"

    # B grade requires validation.
    if base_score_grade == "B":
        detail.required_validation.extend(
            ["客户需求验证", "价格验证", "成本验证", "交付可行性验证"]
        )
        detail.confidence = "medium"

    if base_score_grade == "C":
        detail.required_validation.append("持续观察市场与竞争变化。")
        detail.confidence = "low"

    if base_score_grade == "D":
        detail.blockers.append("综合评分过低，暂不具备立项条件。")
        detail.confidence = "low"

    # Universal human-review triggers.
    if pessimistic_profit is not None and pessimistic_profit.net_monthly_profit <= 0:
        detail.human_review_required = True
        if "悲观情景下月净利润为负。" not in detail.blockers:
            detail.blockers.append("悲观情景下月净利润为负。")

    if base_profit is not None:
        if (
            base_profit.net_payback_months is not None
            and base_profit.net_payback_months > _PAYBACK_WARN_MONTHS
        ):
            detail.human_review_required = True
            detail.blockers.append(
                f"净回本周期超过 {_PAYBACK_WARN_MONTHS} 个月。"
            )
        if base_profit.revenue_consistency_warning:
            detail.human_review_required = True
            detail.blockers.append("输入月收入与数量乘单价存在较大差异。")

    if opp.competition_level == "high" and opp.delivery_difficulty == "high":
        detail.human_review_required = True
        detail.blockers.append("高竞争且高交付难度。")

    if sensitivity_grade_drop:
        detail.human_review_required = True
        detail.blockers.append("敏感性分析中参数轻微变化导致等级显著下降。")

    if has_boundary_or_missing:
        detail.human_review_required = True
        detail.blockers.append("输入数据存在边界值或缺失关键数据。")

    return detail
