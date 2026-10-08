"""Generate the traceable opportunity report (Markdown + JSON + CSV).

v1 compatibility: the public functions (``build_report_markdown``,
``build_json_payload``, ``write_reports``) keep their original positional
signatures. When the optional v2 keyword arguments are supplied, the full
v2 report (13 sections, scenario comparison, sensitivity, data quality,
portfolio summary, CSV export) is produced; otherwise a v1-style report
is emitted so existing tests keep passing.
"""

from __future__ import annotations

import csv as _csv
import hashlib
import json
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .csv_import import Opportunity
from .opportunity_scoring import ScoringResult
from .profit_calculator import ProfitResult

_GRADE_RECOMMENDATIONS = {
    "A": "建议进入正式立项评审",
    "B": "建议补充客户、价格或成本验证后再评审",
    "C": "建议保留观察，暂不投入较大资源",
    "D": "建议暂不立项",
}


class _DecimalEncoder(json.JSONEncoder):
    """JSON encoder that serializes Decimal values as strings."""

    def default(self, o):
        if isinstance(o, Decimal):
            return str(o)
        return super().default(o)


def compute_file_sha256(file_path: str) -> str:
    path = Path(file_path)
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _pct(margin: Decimal) -> str:
    return f"{(margin * Decimal('100')):.2f}%"


def _fmt(value: Decimal) -> str:
    return f"{value:.2f}"


def _fmt_or_null(value) -> str:
    if value is None:
        return "null"
    return f"{value:.2f}"


def recommendation_for(grade: str) -> str:
    return _GRADE_RECOMMENDATIONS.get(grade, "暂不立项")


# ---------------------------------------------------------------------------
# v1 helpers
# ---------------------------------------------------------------------------


def build_summary(
    opportunities: List[Opportunity],
    scores: List[ScoringResult],
    profits: List[ProfitResult],
) -> Dict[str, Any]:
    by_id = {o.opportunity_id: o for o in opportunities}
    score_by_id = {s.opportunity_id: s for s in scores}
    profit_by_id = {p.opportunity_id: p for p in profits}
    ordered_ids = sorted(by_id.keys())
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    rows = []
    for oid in ordered_ids:
        o = by_id[oid]
        s = score_by_id[oid]
        p = profit_by_id[oid]
        grade_counts[s.grade] += 1
        rows.append(
            {
                "opportunity_id": oid,
                "opportunity_name": o.opportunity_name,
                "total_score": s.total_score,
                "grade": s.grade,
                "revenue": str(p.revenue),
                "gross_profit": str(p.gross_profit),
                "gross_margin": str(p.gross_margin),
                "payback_months": (
                    str(p.payback_months) if p.payback_months is not None else None
                ),
                "recommendation": recommendation_for(s.grade),
            }
        )
    return {"total": len(ordered_ids), "grade_counts": grade_counts, "rows": rows}


def _render_summary_table(rows: List[Dict[str, Any]]) -> str:
    headers = [
        "opportunity_id", "opportunity_name", "total_score", "grade",
        "revenue", "gross_profit", "gross_margin", "payback_months", "recommendation",
    ]
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        margin = _pct(Decimal(r["gross_margin"]))
        payback = r["payback_months"] if r["payback_months"] is not None else "null"
        cells = [
            r["opportunity_id"], r["opportunity_name"], str(r["total_score"]),
            r["grade"], r["revenue"], r["gross_profit"], margin, payback,
            r["recommendation"],
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _render_opportunity_detail(
    opp: Opportunity, score: ScoringResult, profit: ProfitResult
) -> str:
    lines = []
    lines.append(f"### {opp.opportunity_id} - {opp.opportunity_name}")
    lines.append("")
    lines.append("**原始关键输入**")
    lines.append("")
    lines.append(
        f"- customer_segment: {opp.customer_segment} | industry: {opp.industry} | "
        f"region: {opp.region}"
    )
    lines.append(
        f"- estimated_units: {opp.estimated_units} | unit_price: {opp.unit_price} | "
        f"variable_cost_per_unit: {opp.variable_cost_per_unit}"
    )
    lines.append(
        f"- fixed_cost: {opp.fixed_cost} | marketing_cost: {opp.marketing_cost} | "
        f"implementation_cost: {opp.implementation_cost}"
    )
    lines.append(
        f"- competition_level: {opp.competition_level} | customer_need: {opp.customer_need} | "
        f"delivery_difficulty: {opp.delivery_difficulty} | strategic_fit: {opp.strategic_fit}"
    )
    lines.append(
        f"- initial_investment: {opp.initial_investment} | "
        f"expected_monthly_operating_cost: {opp.expected_monthly_operating_cost} | "
        f"expected_monthly_revenue: {opp.expected_monthly_revenue}"
    )
    lines.append("")
    lines.append("**评分明细**")
    lines.append("")
    lines.append(f"- 需求得分: {score.demand_score} / 30 (customer_need={opp.customer_need})")
    lines.append(
        f"- 经济收益得分: {score.economics_score} / 30 "
        f"(gross_margin={_pct(profit.gross_margin)}, "
        f"payback_months={_fmt_or_null(profit.payback_months)})"
    )
    lines.append(f"- 战略匹配得分: {score.strategy_score} / 20 (strategic_fit={opp.strategic_fit})")
    lines.append(
        f"- 执行可行性得分: {score.feasibility_score} / 20 "
        f"(delivery_difficulty={opp.delivery_difficulty}, competition_level={opp.competition_level})"
    )
    lines.append(f"- **总分: {score.total_score} / 100 | 等级: {score.grade}**")
    lines.append("")
    lines.append("**收入与成本明细**")
    lines.append("")
    lines.append(f"- revenue (月收入): {_fmt(profit.revenue)}")
    lines.append(f"- variable_cost: {_fmt(profit.variable_cost)}")
    lines.append(f"- fixed_cost: {_fmt(profit.fixed_cost)}")
    lines.append(f"- marketing_cost: {_fmt(profit.marketing_cost)}")
    lines.append(f"- implementation_cost: {_fmt(profit.implementation_cost)}")
    lines.append(f"- total_cost: {_fmt(profit.total_cost)}")
    lines.append(f"- gross_profit: {_fmt(profit.gross_profit)}")
    lines.append(f"- gross_margin: {_pct(profit.gross_margin)}")
    lines.append(f"- monthly_operating_cost: {_fmt(profit.monthly_operating_cost)}")
    lines.append(f"- net_monthly_profit: {_fmt(profit.net_monthly_profit)}")
    lines.append(f"- annualized_profit: {_fmt(profit.annualized_profit)}")
    lines.append(f"- payback_months: {_fmt_or_null(profit.payback_months)}")
    lines.append("")
    lines.append(f"**风险备注**: {opp.risk_notes or '(无)'}")
    lines.append("")
    lines.append(f"**自动建议**: {recommendation_for(score.grade)}")
    lines.append("")
    lines.append("**计算公式说明**")
    lines.append("")
    lines.append("- revenue = expected_monthly_revenue（若为空则 estimated_units * unit_price）")
    lines.append("- variable_cost = estimated_units * variable_cost_per_unit")
    lines.append("- total_cost = variable_cost + fixed_cost + marketing_cost + implementation_cost")
    lines.append("- gross_profit = revenue - total_cost")
    lines.append("- gross_margin = gross_profit / revenue（revenue<=0 时为 0）")
    lines.append("- net_monthly_profit = revenue - variable_cost - expected_monthly_operating_cost")
    lines.append("- annualized_profit = net_monthly_profit * 12")
    lines.append("- payback_months = initial_investment / net_monthly_profit（<=0 时为 null）")
    lines.append("")
    lines.append(f"评分解释: {score.explanation}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public builders (backward-compatible signatures + v2 kwargs)
# ---------------------------------------------------------------------------


def build_report_markdown(
    opportunities, scores, profits, input_path, input_hash,
    scoring_version, calculation_version, generated_at, json_relative_path,
    *, config=None, config_hash=None, command_args=None,
    scenarios=None, sensitivity=None, data_quality_issues=None,
    recommendations=None, portfolio_summary=None,
    sort_by="score", sort_desc=True,
):
    if scenarios is None and sensitivity is None and portfolio_summary is None:
        return _build_report_markdown_v1(
            opportunities, scores, profits, input_path, input_hash,
            scoring_version, calculation_version, generated_at, json_relative_path,
        )
    return _build_report_markdown_v2(
        opportunities, scores, profits, input_path, input_hash,
        scoring_version, calculation_version, generated_at, json_relative_path,
        config, config_hash, command_args, scenarios, sensitivity,
        data_quality_issues, recommendations, portfolio_summary,
        sort_by, sort_desc,
    )


def _build_report_markdown_v1(
    opportunities, scores, profits, input_path, input_hash,
    scoring_version, calculation_version, generated_at, json_relative_path,
):
    summary = build_summary(opportunities, scores, profits)
    by_id = {o.opportunity_id: o for o in opportunities}
    score_by_id = {s.opportunity_id: s for s in scores}
    profit_by_id = {p.opportunity_id: p for p in profits}
    ordered_ids = sorted(by_id.keys())
    grade_counts = summary["grade_counts"]
    parts = []
    parts.append("# 机会分析立项报告")
    parts.append("")
    parts.append(f"- 报告生成时间: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    parts.append(f"- 输入文件: {input_path}")
    parts.append(f"- 输入文件 SHA-256: {input_hash}")
    parts.append(f"- 评分规则版本: {scoring_version}")
    parts.append(f"- 测算规则版本: {calculation_version}")
    parts.append(f"- 分析机会总数: {summary['total']}")
    parts.append(
        f"- 等级分布: A={grade_counts['A']}, B={grade_counts['B']}, "
        f"C={grade_counts['C']}, D={grade_counts['D']}"
    )
    parts.append("")
    parts.append("## 汇总表")
    parts.append("")
    parts.append(_render_summary_table(summary["rows"]))
    parts.append("")
    parts.append("## 机会详细分析")
    parts.append("")
    for oid in ordered_ids:
        parts.append(_render_opportunity_detail(by_id[oid], score_by_id[oid], profit_by_id[oid]))
    parts.append("## 风险和假设")
    parts.append("")
    parts.append("- 所有收入、成本和数量均基于 CSV 输入，未经过第三方核实。")
    parts.append("- 毛利率、回本周期和年化利润为静态估算，未考虑市场波动、汇率、税费和资金时间价值。")
    parts.append("- expected_monthly_growth 仅记录，第一版评分与测算未将其纳入计算。")
    parts.append("- 枚举字段为人工评估，存在主观性。")
    parts.append("")
    parts.append("## 不确定性说明")
    parts.append("")
    parts.append("本报告为自动化测算结果，结论仅供立项参考。")
    parts.append("")
    parts.append("## 建议立项结论")
    parts.append("")
    for grade in ["A", "B", "C", "D"]:
        ids = [r["opportunity_id"] for r in summary["rows"] if r["grade"] == grade]
        if not ids:
            continue
        parts.append(f"### {grade} 级机会（{recommendation_for(grade)}）")
        parts.append("")
        parts.append("、".join(ids))
        parts.append("")
    parts.append("## 机器可读结果")
    parts.append("")
    parts.append(f"完整 JSON 结果文件: `{json_relative_path}`")
    parts.append("")
    return "\n".join(parts)


def build_json_payload(
    opportunities, scores, profits, input_path, input_hash,
    scoring_version, calculation_version, generated_at,
    *, config=None, config_hash=None, command_args=None,
    scenarios=None, sensitivity=None, data_quality_issues=None,
    recommendations=None, portfolio_summary=None,
    data_quality_summary=None, input_record_count=0, error_record_count=0,
):
    if scenarios is None and sensitivity is None and portfolio_summary is None:
        return _build_json_payload_v1(
            opportunities, scores, profits, input_path, input_hash,
            scoring_version, calculation_version, generated_at,
        )
    return _build_json_payload_v2(
        opportunities, scores, profits, input_path, input_hash,
        scoring_version, calculation_version, generated_at,
        config, config_hash, command_args, scenarios, sensitivity,
        data_quality_issues, recommendations, portfolio_summary,
        data_quality_summary, input_record_count, error_record_count,
    )


def _build_json_payload_v1(
    opportunities, scores, profits, input_path, input_hash,
    scoring_version, calculation_version, generated_at,
):
    summary = build_summary(opportunities, scores, profits)
    by_id = {o.opportunity_id: o for o in opportunities}
    score_by_id = {s.opportunity_id: s for s in scores}
    profit_by_id = {p.opportunity_id: p for p in profits}
    ordered_ids = sorted(by_id.keys())
    opp_payload = []
    for oid in ordered_ids:
        o = by_id[oid]
        s = score_by_id[oid]
        p = profit_by_id[oid]
        opp_payload.append(
            {
                "opportunity": o.to_dict(),
                "scoring": s.to_dict(),
                "calculation": p.to_dict(),
                "recommendation": recommendation_for(s.grade),
            }
        )
    return {
        "metadata": {
            "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "tool": "opportunity-analysis",
        },
        "source": {"input_path": input_path, "sha256": input_hash},
        "scoring": {"version": scoring_version},
        "calculations": {"version": calculation_version},
        "opportunities": opp_payload,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# v2 report
# ---------------------------------------------------------------------------


def _summarize_dq(issues) -> Dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0}
    for i in issues or []:
        counts[i.severity] = counts.get(i.severity, 0) + 1
    return counts


def _build_ranked_rows(opportunities, scores, profits, sort_by, sort_desc):
    by_id = {o.opportunity_id: o for o in opportunities}
    score_by_id = {s.opportunity_id: s for s in scores}
    profit_by_id = {p.opportunity_id: p for p in profits}
    rows = []
    for oid in by_id:
        o = by_id[oid]
        s = score_by_id[oid]
        p = profit_by_id[oid]
        rows.append(
            {
                "opportunity_id": oid,
                "opportunity_name": o.opportunity_name,
                "total_score": s.total_score,
                "grade": s.grade,
                "revenue": str(p.revenue),
                "gross_profit": str(p.gross_profit),
                "gross_margin": str(p.gross_margin),
                "payback_months": (str(p.net_payback_months) if p.net_payback_months is not None else None),
                "recommendation": recommendation_for(s.grade),
                "_sort_score": s.total_score,
                "_sort_profit": p.net_monthly_profit,
                "_sort_payback": p.net_payback_months if p.net_payback_months is not None else Decimal("999999"),
                "_sort_margin": p.gross_margin,
                "_sort_investment": p.initial_investment,
            }
        )
    sort_map = {
        "score": "_sort_score", "profit": "_sort_profit", "payback": "_sort_payback",
        "margin": "_sort_margin", "investment": "_sort_investment",
    }
    key = sort_map.get(sort_by, "_sort_score")
    rows.sort(key=lambda r: r[key], reverse=sort_desc)
    for r in rows:
        for k in list(r.keys()):
            if k.startswith("_sort_"):
                del r[k]
    return rows


def compute_portfolio_summary(opportunities, profits, scores) -> Dict[str, Any]:
    profit_by_id = {p.opportunity_id: p for p in profits}
    score_by_id = {s.opportunity_id: s for s in scores}
    total_investment = Decimal("0")
    total_revenue = Decimal("0")
    total_net = Decimal("0")
    total_annualized = Decimal("0")
    ab_investment = Decimal("0")
    ab_annualized = Decimal("0")
    margins = []
    wm_num = Decimal("0")
    wm_den = Decimal("0")
    fastest_payback = None
    fastest_id = ""
    highest_profit = Decimal("-Infinity")
    highest_profit_id = ""
    highest_risk_id = ""
    highest_risk_score = 999
    for opp in opportunities:
        p = profit_by_id[opp.opportunity_id]
        s = score_by_id[opp.opportunity_id]
        total_investment += p.initial_investment
        total_revenue += p.revenue
        total_net += p.net_monthly_profit
        total_annualized += p.annualized_profit
        if p.revenue > 0:
            margins.append(p.gross_margin)
            wm_num += p.gross_margin * p.revenue
            wm_den += p.revenue
        if s.grade in ("A", "B"):
            ab_investment += p.initial_investment
            ab_annualized += p.annualized_profit
        if p.net_payback_months is not None:
            if fastest_payback is None or p.net_payback_months < fastest_payback:
                fastest_payback = p.net_payback_months
                fastest_id = opp.opportunity_id
        if p.net_monthly_profit > highest_profit:
            highest_profit = p.net_monthly_profit
            highest_profit_id = opp.opportunity_id
        if s.total_score < highest_risk_score:
            highest_risk_score = s.total_score
            highest_risk_id = opp.opportunity_id
    avg_margin = (sum(margins) / len(margins)) if margins else Decimal("0")
    weighted_margin = (wm_num / wm_den) if wm_den > 0 else Decimal("0")
    return {
        "total_count": len(opportunities),
        "total_initial_investment": total_investment,
        "total_monthly_revenue": total_revenue,
        "total_monthly_net_profit": total_net,
        "total_annualized_profit": total_annualized,
        "ab_investment": ab_investment,
        "ab_annualized_profit": ab_annualized,
        "avg_gross_margin": avg_margin,
        "weighted_gross_margin": weighted_margin,
        "fastest_payback": fastest_id,
        "highest_profit": highest_profit_id,
        "highest_risk": highest_risk_id,
    }


def _render_v2_opportunity_detail(opp, score, profit, rec, scens) -> str:
    lines = []
    lines.append(f"### {opp.opportunity_id} - {opp.opportunity_name}")
    lines.append("")
    lines.append("**原始关键输入**")
    lines.append("")
    lines.append(f"- customer_segment: {opp.customer_segment} | industry: {opp.industry} | region: {opp.region}")
    lines.append(f"- estimated_units: {opp.estimated_units} | unit_price: {opp.unit_price} | variable_cost_per_unit: {opp.variable_cost_per_unit}")
    lines.append(f"- fixed_cost: {opp.fixed_cost} | marketing_cost: {opp.marketing_cost} | implementation_cost: {opp.implementation_cost}")
    lines.append(f"- competition_level: {opp.competition_level} | customer_need: {opp.customer_need} | delivery_difficulty: {opp.delivery_difficulty} | strategic_fit: {opp.strategic_fit}")
    lines.append(f"- initial_investment: {opp.initial_investment} | expected_monthly_operating_cost: {opp.expected_monthly_operating_cost} | expected_monthly_revenue: {opp.expected_monthly_revenue}")
    lines.append("")
    lines.append("**评分明细**")
    lines.append("")
    lines.append(f"- 需求得分: {score.demand_score} / 30")
    lines.append(f"- 经济收益得分: {score.economics_score} / 30 (payback_metric={score.payback_metric})")
    lines.append(f"- 战略匹配得分: {score.strategy_score} / 20")
    lines.append(f"- 执行可行性得分: {score.feasibility_score} / 20")
    lines.append(f"- **总分: {score.total_score} / 100 | 等级: {score.grade}**")
    lines.append("")
    lines.append("**收入与成本明细**")
    lines.append("")
    lines.append(f"- revenue_source: {profit.revenue_source}")
    lines.append(f"- input_expected_monthly_revenue: {_fmt_or_null(profit.input_expected_monthly_revenue)}")
    lines.append(f"- calculated_units_revenue: {_fmt(profit.calculated_units_revenue)}")
    lines.append(f"- final_revenue: {_fmt(profit.final_revenue)}")
    if profit.revenue_consistency_warning:
        lines.append("- ⚠️ 输入月收入与数量乘单价存在差异，当前测算采用 expected_monthly_revenue。")
    lines.append(f"- variable_cost: {_fmt(profit.variable_cost)}")
    lines.append(f"- total_cost: {_fmt(profit.total_cost)}")
    lines.append(f"- gross_profit: {_fmt(profit.gross_profit)}")
    lines.append(f"- gross_margin: {_pct(profit.gross_margin)}")
    lines.append(f"- net_monthly_profit: {_fmt(profit.net_monthly_profit)}")
    lines.append(f"- annualized_profit: {_fmt(profit.annualized_profit)}")
    lines.append(f"- gross_payback_months: {_fmt_or_null(profit.gross_payback_months)}")
    lines.append(f"- net_payback_months: {_fmt_or_null(profit.net_payback_months)}")
    lines.append("")
    lines.append(f"**风险备注**: {opp.risk_notes or '(无)'}")
    lines.append("")
    if rec:
        lines.append(f"**自动建议**: {rec.recommendation} (confidence={rec.confidence})")
        if rec.human_review_required:
            lines.append("- 需要人工复核")
    else:
        lines.append(f"**自动建议**: {recommendation_for(score.grade)}")
    lines.append("")
    lines.append(f"评分解释: {score.explanation}")
    lines.append("")
    return "\n".join(lines)


def _build_report_markdown_v2(
    opportunities, scores, profits, input_path, input_hash,
    scoring_version, calculation_version, generated_at, json_relative_path,
    config, config_hash, command_args, scenarios, sensitivity,
    data_quality_issues, recommendations, portfolio_summary,
    sort_by, sort_desc,
):
    by_id = {o.opportunity_id: o for o in opportunities}
    score_by_id = {s.opportunity_id: s for s in scores}
    profit_by_id = {p.opportunity_id: p for p in profits}
    rec_by_id = recommendations or {}
    rows = _build_ranked_rows(opportunities, scores, profits, sort_by, sort_desc)
    ordered_ids = [r["opportunity_id"] for r in rows]
    dq_summary = _summarize_dq(data_quality_issues or [])
    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for s in scores:
        grade_counts[s.grade] += 1

    parts = []
    parts.append("# 机会分析立项报告 (v2)")
    parts.append("")
    parts.append("## 1. 执行摘要")
    parts.append("")
    parts.append(f"- 分析机会总数: {len(opportunities)}")
    parts.append(f"- 等级分布: A={grade_counts['A']}, B={grade_counts['B']}, C={grade_counts['C']}, D={grade_counts['D']}")
    if portfolio_summary:
        parts.append(f"- 总初始投资: {_fmt(portfolio_summary.get('total_initial_investment', Decimal(0)))}")
        parts.append(f"- 总月收入: {_fmt(portfolio_summary.get('total_monthly_revenue', Decimal(0)))}")
        parts.append(f"- 总月净利润: {_fmt(portfolio_summary.get('total_monthly_net_profit', Decimal(0)))}")
        parts.append(f"- 总年化利润: {_fmt(portfolio_summary.get('total_annualized_profit', Decimal(0)))}")
        parts.append(f"- 平均毛利率: {_pct(portfolio_summary.get('avg_gross_margin', Decimal(0)))}")
        parts.append(f"- 加权毛利率: {_pct(portfolio_summary.get('weighted_gross_margin', Decimal(0)))}")
    parts.append("")
    parts.append("## 2. 运行参数")
    parts.append("")
    parts.append(f"- 报告生成时间: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    parts.append(f"- Python 版本: {sys.version.split()[0]}")
    parts.append(f"- 评分规则版本: {scoring_version}")
    parts.append(f"- 测算规则版本: {calculation_version}")
    parts.append(f"- 排序字段: {sort_by} ({'降序' if sort_desc else '升序'})")
    if command_args:
        parts.append(f"- CLI 参数: `{command_args.get('cli_string', '')}`")
    parts.append("")
    parts.append("## 3. 配置摘要")
    parts.append("")
    parts.append(f"- 配置文件 SHA-256: {config_hash or '(未提供)'}")
    if config:
        parts.append(f"- schema_version: {config.get('schema_version')}")
        parts.append(f"- 情景: {', '.join(config.get('scenarios', {}).keys())}")
        parts.append(f"- 评分权重: {config.get('scoring_rules', {}).get(scoring_version, {}).get('score_weights')}")
    parts.append("")
    parts.append("## 4. 数据质量检查")
    parts.append("")
    parts.append(f"- error: {dq_summary['error']}, warning: {dq_summary['warning']}, info: {dq_summary['info']}")
    parts.append("")
    for issue in data_quality_issues or []:
        parts.append(f"- [{issue.severity}] {issue.opportunity_id}: {issue.message}")
    parts.append("")
    parts.append("## 5. 机会排名")
    parts.append("")
    parts.append(_render_summary_table(rows))
    parts.append("")
    if portfolio_summary:
        parts.append("## 6. 组合汇总")
        parts.append("")
        for k, v in portfolio_summary.items():
            if isinstance(v, Decimal):
                parts.append(f"- {k}: {_fmt(v)}")
            elif isinstance(v, str) and k in ("fastest_payback", "highest_profit", "highest_risk"):
                parts.append(f"- {k}: {v}")
            elif isinstance(v, int):
                parts.append(f"- {k}: {v}")
        parts.append("")
    if scenarios:
        parts.append("## 7. 情景比较")
        parts.append("")
        for oid in ordered_ids:
            opp = by_id[oid]
            scens = scenarios.get(oid, [])
            parts.append(f"### {oid} - {opp.opportunity_name}")
            parts.append("")
            parts.append("| 情景 | revenue | gross_profit | gross_margin | net_monthly_profit | net_payback | total_score | grade |")
            parts.append("| --- | --- | --- | --- | --- | --- | --- | --- |")
            for sr in scens:
                p = sr.profit
                s = sr.score
                parts.append(
                    f"| {sr.scenario} | {_fmt(p.revenue)} | {_fmt(p.gross_profit)} | "
                    f"{_pct(p.gross_margin)} | {_fmt(p.net_monthly_profit)} | "
                    f"{_fmt_or_null(p.net_payback_months)} | {s.total_score} | {s.grade} |"
                )
            parts.append("")
    if sensitivity:
        parts.append("## 8. 敏感性分析")
        parts.append("")
        for oid in ordered_ids:
            sens = sensitivity.get(oid)
            if not sens:
                continue
            parts.append(f"### {oid}")
            parts.append("")
            parts.append(f"- 最敏感参数: {sens.most_impactful_parameter}")
            parts.append(f"- 等级跨越参数: {', '.join(sens.grade_crossing_parameters) or '(无)'}")
            parts.append(f"- 对价格敏感: {'是' if sens.price_sensitive else '否'}")
            parts.append(f"- 对成本敏感: {'是' if sens.cost_sensitive else '否'}")
            parts.append("")
            parts.append("| 参数 | 变化% | revenue | net_monthly_profit | gross_margin | payback | 总分 | 等级 | 建议变化 |")
            parts.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
            for pt in sens.points:
                parts.append(
                    f"| {pt.parameter} | {pt.delta_percent}% | {_fmt(pt.revenue)} | "
                    f"{_fmt(pt.net_monthly_profit)} | {_pct(pt.gross_margin)} | "
                    f"{_fmt_or_null(pt.payback_months)} | {pt.total_score} | {pt.grade} | "
                    f"{'是' if pt.recommendation_changed else '否'} |"
                )
            parts.append("")
    parts.append("## 9. 每个机会的详细分析")
    parts.append("")
    for oid in ordered_ids:
        opp = by_id[oid]
        s = score_by_id[oid]
        p = profit_by_id[oid]
        parts.append(_render_v2_opportunity_detail(opp, s, p, rec_by_id.get(oid), scenarios.get(oid) if scenarios else None))
    parts.append("## 10. 风险和人工复核")
    parts.append("")
    for oid in ordered_ids:
        rec = rec_by_id.get(oid)
        opp = by_id[oid]
        parts.append(f"### {oid} - {opp.opportunity_name}")
        parts.append("")
        if rec:
            parts.append(f"- recommendation: {rec.recommendation}")
            parts.append(f"- confidence: {rec.confidence}")
            parts.append(f"- human_review_required: {'是' if rec.human_review_required else '否'}")
            if rec.reasons:
                parts.append(f"- 理由: {'；'.join(rec.reasons)}")
            if rec.blockers:
                parts.append(f"- 阻碍: {'；'.join(rec.blockers)}")
            if rec.required_validation:
                parts.append(f"- 需验证: {'；'.join(rec.required_validation)}")
        else:
            parts.append("- 未提供人工复核信息")
        parts.append(f"- 人工复核字段: owner={opp.owner or '(无)'}, validation_status={opp.validation_status or '(无)'}, review_status={opp.review_status or '(无)'}, reviewer={opp.reviewer or '(无)'}")
        parts.append("")
    parts.append("## 11. 计算口径")
    parts.append("")
    parts.append("- revenue = expected_monthly_revenue（若为空则 estimated_units * unit_price）")
    parts.append("- variable_cost = estimated_units * variable_cost_per_unit")
    parts.append("- total_cost = variable_cost + fixed_cost + marketing_cost + implementation_cost")
    parts.append("- gross_profit = revenue - total_cost")
    parts.append("- gross_margin = gross_profit / revenue（revenue<=0 时为 0）")
    parts.append("- net_monthly_profit = revenue - variable_cost - expected_monthly_operating_cost")
    parts.append("- annualized_profit = net_monthly_profit * 12")
    parts.append("- gross_payback_months = initial_investment / gross_profit（<=0 时为 null）")
    parts.append("- net_payback_months = initial_investment / net_monthly_profit（<=0 时为 null）")
    payback_metric = ""
    if config:
        payback_metric = config.get("scoring_rules", {}).get(scoring_version, {}).get("payback_metric", "")
    parts.append(f"- 评分使用回本口径: {payback_metric}")
    parts.append("")
    parts.append("## 12. 可追溯信息")
    parts.append("")
    parts.append(f"- 输入文件路径: {input_path}")
    parts.append(f"- 输入文件 SHA-256: {input_hash}")
    parts.append(f"- 配置文件 SHA-256: {config_hash or '(未提供)'}")
    parts.append(f"- 评分版本: {scoring_version}")
    parts.append(f"- 测算版本: {calculation_version}")
    parts.append(f"- 情景版本: {config.get('schema_version') if config else ''}")
    parts.append(f"- 运行时间: {generated_at.strftime('%Y-%m-%d %H:%M:%S')}")
    parts.append(f"- Python 版本: {sys.version.split()[0]}")
    if command_args:
        parts.append(f"- CLI 参数: {command_args.get('cli_string', '')}")
    parts.append(f"- 输入记录数: {len(opportunities)}")
    parts.append(f"- 有效记录数: {len(opportunities)}")
    parts.append(f"- 错误记录数: 0")
    parts.append(f"- 警告数量: {dq_summary['warning']}")
    parts.append("")
    parts.append("## 13. 限制和免责声明")
    parts.append("")
    parts.append("- 本工具为辅助决策工具，不是最终投资决策系统。")
    parts.append("- 结果依赖输入数据质量。")
    parts.append("- 未纳入税费、融资成本、现金流时间价值和汇率风险。")
    parts.append("- 情景参数只是可配置假设。")
    parts.append("- 人工复核仍然是必要环节。")
    parts.append("")
    parts.append(f"完整 JSON 结果文件: `{json_relative_path}`")
    parts.append("")
    return "\n".join(parts)


def _build_json_payload_v2(
    opportunities, scores, profits, input_path, input_hash,
    scoring_version, calculation_version, generated_at,
    config, config_hash, command_args, scenarios, sensitivity,
    data_quality_issues, recommendations, portfolio_summary,
    data_quality_summary, input_record_count, error_record_count,
):
    by_id = {o.opportunity_id: o for o in opportunities}
    score_by_id = {s.opportunity_id: s for s in scores}
    profit_by_id = {p.opportunity_id: p for p in profits}
    ordered_ids = sorted(by_id.keys())
    opp_payload = []
    for oid in ordered_ids:
        o = by_id[oid]
        s = score_by_id[oid]
        p = profit_by_id[oid]
        entry = {
            "opportunity": o.to_dict(),
            "scoring": s.to_dict(),
            "calculation": p.to_dict(),
            "recommendation": recommendation_for(s.grade),
        }
        if recommendations and oid in recommendations:
            entry["recommendation_detail"] = recommendations[oid].to_dict()
        if scenarios and oid in scenarios:
            entry["scenarios"] = [sr.to_dict() for sr in scenarios[oid]]
        if sensitivity and oid in sensitivity:
            entry["sensitivity"] = sensitivity[oid].to_dict()
        opp_payload.append(entry)
    dq_summary = (
        data_quality_summary
        if data_quality_summary is not None
        else _summarize_dq(data_quality_issues or [])
    )
    dq_issues_list = [i.to_dict() for i in (data_quality_issues or [])]
    return {
        "metadata": {
            "generated_at": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "tool": "opportunity-analysis",
            "python_version": sys.version.split()[0],
        },
        "command": command_args or {},
        "source": {
            "input_path": input_path,
            "sha256": input_hash,
            "input_record_count": input_record_count,
            "valid_record_count": len(opportunities),
            "error_record_count": error_record_count,
        },
        "config_snapshot": {
            "sha256": config_hash,
            "schema_version": (config or {}).get("schema_version"),
            "scoring_rules": (config or {}).get("scoring_rules", {}).get(scoring_version),
            "scenarios": (config or {}).get("scenarios"),
        },
        "scoring": {"version": scoring_version},
        "calculations": {"version": calculation_version},
        "data_quality": {"summary": dq_summary, "issues": dq_issues_list},
        "summary": portfolio_summary or {},
        "rankings": _build_ranked_rows(opportunities, scores, profits, "score", True),
        "scenarios": {
            oid: [sr.to_dict() for sr in scenarios.get(oid, [])]
            for oid in ordered_ids
        } if scenarios else {},
        "sensitivity": {
            oid: sensitivity[oid].to_dict()
            for oid in ordered_ids
            if sensitivity and oid in sensitivity
        },
        "opportunities": opp_payload,
        "warnings": [i.message for i in (data_quality_issues or []) if i.severity == "warning"],
    }


def write_results_csv(opportunities, scenarios, recommendations, csv_path) -> None:
    fieldnames = [
        "opportunity_id", "opportunity_name", "scenario", "total_score", "grade",
        "recommendation", "revenue", "gross_profit", "gross_margin",
        "net_monthly_profit", "annualized_profit", "gross_payback_months",
        "net_payback_months", "initial_investment", "human_review_required",
    ]
    opp_by_id = {o.opportunity_id: o for o in opportunities}
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = _csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for oid in sorted(scenarios.keys()):
            opp = opp_by_id.get(oid)
            name = opp.opportunity_name if opp else ""
            rec = recommendations.get(oid) if recommendations else None
            for sr in scenarios[oid]:
                writer.writerow(
                    {
                        "opportunity_id": oid,
                        "opportunity_name": name,
                        "scenario": sr.scenario,
                        "total_score": sr.score.total_score,
                        "grade": sr.score.grade,
                        "recommendation": rec.recommendation if rec else recommendation_for(sr.score.grade),
                        "revenue": str(sr.profit.revenue),
                        "gross_profit": str(sr.profit.gross_profit),
                        "gross_margin": str(sr.profit.gross_margin),
                        "net_monthly_profit": str(sr.profit.net_monthly_profit),
                        "annualized_profit": str(sr.profit.annualized_profit),
                        "gross_payback_months": (
                            str(sr.profit.gross_payback_months)
                            if sr.profit.gross_payback_months is not None else ""
                        ),
                        "net_payback_months": (
                            str(sr.profit.net_payback_months)
                            if sr.profit.net_payback_months is not None else ""
                        ),
                        "initial_investment": str(sr.profit.initial_investment),
                        "human_review_required": "true" if (rec and rec.human_review_required) else "false",
                    }
                )


def write_reports(
    opportunities, scores, profits, input_path, input_hash, output_dir,
    scoring_version, calculation_version,
    *, config=None, config_hash=None, command_args=None,
    scenarios=None, sensitivity=None, data_quality_issues=None,
    recommendations=None, portfolio_summary=None,
    sort_by="score", sort_desc=True,
):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    md_name = f"opportunity_report_{timestamp}.md"
    json_name = f"opportunity_analysis_{timestamp}.json"
    csv_name = f"opportunity_analysis_{timestamp}.csv"
    md_path = out / md_name
    json_path = out / json_name
    csv_path = out / csv_name
    generated_at = datetime.now()

    is_v2 = any(
        v is not None
        for v in (scenarios, sensitivity, data_quality_issues, recommendations, portfolio_summary)
    )
    dq_summary = _summarize_dq(data_quality_issues or []) if data_quality_issues else None

    payload = build_json_payload(
        opportunities, scores, profits, input_path, input_hash,
        scoring_version, calculation_version, generated_at,
        config=config, config_hash=config_hash, command_args=command_args,
        scenarios=scenarios, sensitivity=sensitivity,
        data_quality_issues=data_quality_issues,
        recommendations=recommendations, portfolio_summary=portfolio_summary,
        data_quality_summary=dq_summary,
        input_record_count=len(opportunities), error_record_count=0,
    )
    markdown = build_report_markdown(
        opportunities, scores, profits, input_path, input_hash,
        scoring_version, calculation_version, generated_at, json_name,
        config=config, config_hash=config_hash, command_args=command_args,
        scenarios=scenarios, sensitivity=sensitivity,
        data_quality_issues=data_quality_issues,
        recommendations=recommendations, portfolio_summary=portfolio_summary,
        sort_by=sort_by, sort_desc=sort_desc,
    )

    with json_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, cls=_DecimalEncoder)
    with md_path.open("w", encoding="utf-8") as f:
        f.write(markdown)

    if is_v2:
        csv_out = ""
        if scenarios:
            write_results_csv(opportunities, scenarios, recommendations, str(csv_path))
            csv_out = str(csv_path)
        return str(md_path), str(json_path), csv_out
    return str(md_path), str(json_path)
