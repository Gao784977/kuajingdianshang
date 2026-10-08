"""Data quality checks for opportunities.

Produces a list of :class:`DataQualityIssue` with severity levels
(``error`` / ``warning`` / ``info``) so the report can surface data
problems that need human attention without blocking the analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, List

from .csv_import import Opportunity
from .profit_calculator import ProfitResult

_EXTREME_MARGIN = Decimal("1.0")  # |gross_margin| > 1.0 is suspicious


@dataclass
class DataQualityIssue:
    opportunity_id: str
    severity: str  # "error" | "warning" | "info"
    check: str
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "severity": self.severity,
            "check": self.check,
            "message": self.message,
        }


def check_data_quality(
    opportunities: List[Opportunity],
    profits: List[ProfitResult],
    payback_warning_months: Decimal = Decimal("24"),
    revenue_consistency_threshold: Decimal = Decimal("0.10"),
) -> List[DataQualityIssue]:
    """Run all data quality checks and return the list of issues."""
    issues: List[DataQualityIssue] = []
    profit_by_id = {p.opportunity_id: p for p in profits}

    for opp in opportunities:
        oid = opp.opportunity_id
        p = profit_by_id.get(oid)
        if p is None:
            continue

        # --- missing values (info) ---
        for attr in ("customer_segment", "industry", "region", "risk_notes"):
            if not getattr(opp, attr):
                issues.append(
                    DataQualityIssue(oid, "info", "missing_value", f"字段 '{attr}' 为空。")
                )

        # --- zero revenue (warning) ---
        if p.revenue <= 0:
            issues.append(
                DataQualityIssue(oid, "warning", "zero_revenue", "月收入为零，无法计算毛利率。")
            )

        # --- negative profit (warning) ---
        if p.gross_profit < 0:
            issues.append(
                DataQualityIssue(
                    oid, "warning", "negative_profit", "毛利为负，该机会预计亏损。"
                )
            )

        # --- extreme gross margin (warning) ---
        if p.revenue > 0 and abs(p.gross_margin) > _EXTREME_MARGIN:
            issues.append(
                DataQualityIssue(
                    oid,
                    "warning",
                    "extreme_margin",
                    f"毛利率 {p.gross_margin:.4f} 超出合理范围（>100%），请核对数据。",
                )
            )

        # --- initial investment zero (info) ---
        if opp.initial_investment <= 0:
            issues.append(
                DataQualityIssue(
                    oid, "info", "zero_investment", "初始投资为零，回本周期无意义。"
                )
            )

        # --- revenue inconsistency (warning) ---
        if p.revenue_consistency_warning:
            issues.append(
                DataQualityIssue(
                    oid,
                    "warning",
                    "revenue_inconsistency",
                    "输入月收入与数量乘单价存在差异，当前测算采用 expected_monthly_revenue。",
                )
            )

        # --- high competition + high delivery difficulty (warning) ---
        if opp.competition_level == "high" and opp.delivery_difficulty == "high":
            issues.append(
                DataQualityIssue(
                    oid,
                    "warning",
                    "high_risk_delivery",
                    "高竞争且高交付难度，执行风险较高。",
                )
            )

        # --- operating cost above revenue (warning) ---
        if p.revenue > 0 and p.monthly_operating_cost > p.revenue:
            issues.append(
                DataQualityIssue(
                    oid,
                    "warning",
                    "operating_cost_exceeds_revenue",
                    "月运营成本高于月收入，净利润为负。",
                )
            )

        # --- payback > 24 months (warning) ---
        if p.net_payback_months is not None and p.net_payback_months > payback_warning_months:
            issues.append(
                DataQualityIssue(
                    oid,
                    "warning",
                    "long_payback",
                    f"净回本周期 {p.net_payback_months:.2f} 个月超过 {payback_warning_months} 个月。",
                )
            )

    return issues


def summarize_issues(issues: List[DataQualityIssue]) -> Dict[str, int]:
    """Return counts by severity."""
    counts = {"error": 0, "warning": 0, "info": 0}
    for issue in issues:
        counts[issue.severity] = counts.get(issue.severity, 0) + 1
    return counts
