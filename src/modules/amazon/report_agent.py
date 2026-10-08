"""Report agent for the V3 Amazon workflow.

Builds two output files per run:

* ``amazon_product_report_<ts>.md`` — Markdown with 17 locked sections
  (see :data:`_REPORT_SECTIONS`).
* ``amazon_product_analysis_<ts>.json`` — full JSON snapshot.

The report includes the traceability metadata required by the spec
(input SHA-256, config SHA-256, CLI args, agent versions, python
version, generated_at, record counts, final_status).

The 17-section order is locked as a tuple so tests can assert count
and order without re-reading the spec (decision #11). Timestamp format
follows V1/V2: ``%Y%m%d_%H%M%S`` (decision #12).

This module imports stdlib only plus :mod:`.models` (for
:class:`AmazonDecimalEncoder`). It reuses the **public**
:func:`src.modules.project_report.compute_file_sha256` for input file
SHA-256 (architecture decision #4 — never import V1/V2 private code).
"""

from __future__ import annotations

import json
import platform
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import (
    AgentResult,
    AmazonDecimalEncoder,
    CompetitorOutput,
    KeywordOutput,
    MarketOutput,
    OpportunityOutput,
    ProductOutput,
    ReviewOutput,
    WorkflowContext,
)

# Reuse the PUBLIC compute_file_sha256 from V1/V2 project_report (not a
# private import; it's an explicitly public function per the spec).
from src.modules.project_report import compute_file_sha256  # noqa: IPC

# ---------------------------------------------------------------------------
# Locked 17-section order (decision #11). Tests assert this tuple's
# length and order. Do not renumber or rename without updating tests.
# ---------------------------------------------------------------------------
_REPORT_SECTIONS = (
    "1. 执行摘要",
    "2. 输入信息",
    "3. 工作流执行状态",
    "4. 数据来源与可信度",
    "5. 关键词分析",
    "6. 市场分析",
    "7. 竞品矩阵",
    "8. Review痛点分析",
    "9. 产品机会判断",
    "10. 产品开发规划",
    "11. Amazon利润测算",
    "12. 三种情景比较",
    "13. 风险和验证计划",
    "14. 人工复核事项",
    "15. 最终建议",
    "16. 数据限制和免责声明",
    "17. 可追溯信息",
)
assert len(_REPORT_SECTIONS) == 17, "V3 report must have exactly 17 sections"

NAME = "report"
VERSION = "report_agent_v1"
_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"


def build_report(
    context: WorkflowContext,
    output_dir: Path,
    *,
    input_file_path: Optional[str] = None,
) -> AgentResult:
    """Build the Markdown + JSON reports.

    Args:
        context: Workflow context with all agent results populated.
        output_dir: Directory to write the report files into.
        input_file_path: Optional path to the input JSON, for SHA-256.
            If None, falls back to ``context.cli_args.input``.

    Returns:
        :class:`AgentResult` with ``output`` containing ``markdown_path``
        and ``json_path``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    ts = context.generated_at or datetime.now().strftime(_TIMESTAMP_FMT)

    os_cfg = context.config.get("output_settings", {})
    md_name = os_cfg.get(
        "markdown_template", "amazon_product_report_{timestamp}.md"
    ).format(timestamp=ts)
    json_name = os_cfg.get(
        "json_template", "amazon_product_analysis_{timestamp}.json"
    ).format(timestamp=ts)

    md_path = output_dir / md_name
    json_path = output_dir / json_name

    # Compute input SHA-256 if an input file path is available
    input_path = input_file_path or context.cli_args.get("input")
    input_sha: Optional[str] = None
    if input_path:
        try:
            input_sha = compute_file_sha256(str(input_path))
        except Exception:
            input_sha = None
    context.input_sha256 = input_sha

    # Python version
    context.python_version = platform.python_version()

    # Build Markdown
    md_text = _build_markdown(context, input_sha)
    md_path.write_text(md_text, encoding="utf-8")

    # Build JSON
    json_payload = _build_json(context, input_sha)
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(json_payload, f, ensure_ascii=False, indent=2,
                  cls=AmazonDecimalEncoder)

    return AgentResult(
        agent_name=NAME,
        status="completed",
        input_summary={
            "input_sha256": input_sha or "",
            "config_sha256": context.config_sha256,
            "agents_run": len(context.agents),
        },
        output={
            "markdown_path": str(md_path),
            "json_path": str(json_path),
            "sections": list(_REPORT_SECTIONS),
        },
        warnings=[],
        assumptions=[
            "Report sections follow locked 17-section order (decision #11).",
            "Timestamp format %Y%m%d_%H%M%S matches V1/V2 convention.",
        ],
        source="calculated",
        version=VERSION,
    )


# ---------------------------------------------------------------------------
# Markdown builder
# ---------------------------------------------------------------------------


def _build_markdown(
    context: WorkflowContext,
    input_sha: Optional[str],
) -> str:
    """Render the full 17-section Markdown report."""
    lines: List[str] = []
    lines.append("# Amazon US 产品开发多Agent分析报告")
    lines.append("")
    lines.append(f"生成时间: {context.generated_at}")
    lines.append(f"工作流状态: `{context.final_status}`")
    lines.append("")

    # Each section function appends its own heading + content
    section_funcs = (
        _section_1_summary,
        _section_2_input,
        _section_3_workflow_status,
        _section_4_sources,
        _section_5_keyword,
        _section_6_market,
        _section_7_competitor,
        _section_8_review,
        _section_9_opportunity,
        _section_10_product,
        _section_11_profit,
        _section_12_scenarios,
        _section_13_risks,
        _section_14_review_fields,
        _section_15_final_recommendation,
        _section_16_disclaimer,
        _section_17_traceability,
    )
    assert len(section_funcs) == len(_REPORT_SECTIONS)

    for heading, func in zip(_REPORT_SECTIONS, section_funcs):
        lines.append(f"## {heading}")
        lines.append("")
        func(lines, context, input_sha)
        lines.append("")

    return "\n".join(lines)


# --- helpers used by multiple sections -----------------------------------


def _get_output(context: WorkflowContext, name: str, cls: Any) -> Optional[Any]:
    """Typed access wrapper. Returns None if agent didn't run.

    If ``cls`` is ``None``, returns the raw stored output (the agent
    stores a dict, e.g. the profit agent's per-scenario dict).
    """
    if cls is None:
        result = context.agents.get(name)
        if result is None or result.output is None:
            return None
        return result.output
    return context.get_output(name, cls)


def _kv_table(lines: List[str], rows: List[tuple]) -> None:
    """Append a 2-column key/value table."""
    lines.append("| 字段 | 值 |")
    lines.append("| --- | --- |")
    for k, v in rows:
        lines.append(f"| {k} | {v} |")


def _bullet_list(lines: List[str], items: List[str], indent: str = "") -> None:
    for it in items:
        lines.append(f"{indent}- {it}")


# --- section 1: 执行摘要 -------------------------------------------------


def _section_1_summary(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    pi = context.product_input
    keyword = pi.keyword if pi else ""
    marketplace = pi.marketplace if pi else ""
    lines.append(
        "本报告由 V3 Amazon US 产品开发多 Agent 工作流自动生成。"
        "工作流依次执行 9 个分析 Agent（关键词、市场、竞品、Review、"
        "机会判断、产品规划、利润测算、报告、Excel），输出 Markdown、"
        "JSON 以及两份 Excel 工作簿。所有数据来源于确定性 Mock 数据或"
        "用户输入，无网络调用、无 API Key、无 Amazon SP-API 调用。"
    )
    lines.append("")
    lines.append("**核心结论摘要：**")
    lines.append("")
    opp = _get_output(context, "opportunity", OpportunityOutput)
    if opp:
        lines.append(
            f"- 关键词: `{keyword}`；市场: `{marketplace}`"
        )
        lines.append(
            f"- 机会评分（市场/竞争/供应链/差异化）: "
            f"{opp.market_opportunity}/{opp.competition}/"
            f"{opp.supply_chain_feasibility}/{opp.differentiation_potential}"
        )
        lines.append(
            f"- 立项建议: `{opp.development_recommendation}`"
        )
        lines.append(
            f"- 是否需要人工复核: `{opp.human_review_required}`"
        )
    else:
        lines.append("- 机会判断 Agent 未运行或被跳过。")
    lines.append("")
    profit_result = _get_output(context, "profit", None)
    if profit_result and isinstance(profit_result, dict):
        base = profit_result.get("base", {})
        if base:
            lines.append(
                f"- 基准情景月利润: {base.get('monthly_profit', 'N/A')}；"
                f"年化利润: {base.get('annualized_profit', 'N/A')}"
            )


# --- section 2: 输入信息 -------------------------------------------------


def _section_2_input(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    pi = context.product_input
    if not pi:
        lines.append("未提供产品输入。")
        return
    _kv_table(lines, [
        ("keyword", pi.keyword),
        ("marketplace", pi.marketplace),
        ("target_price_min", pi.target_price_min),
        ("target_price_max", pi.target_price_max),
        ("direction", pi.direction or "未指定"),
        ("constraints", ", ".join(pi.constraints) or "无"),
        ("notes", pi.notes or "无"),
        ("source", pi.source),
        ("confidence", pi.confidence),
    ])


# --- section 3: 工作流执行状态 ------------------------------------------


def _section_3_workflow_status(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    lines.append(f"最终状态: `{context.final_status}`")
    lines.append("")
    lines.append("| Agent | 状态 | 版本 | 警告数 |")
    lines.append("| --- | --- | --- | --- |")
    for name in context.agent_order:
        r = context.agents.get(name)
        if not r:
            lines.append(f"| {name} | 未运行 | - | - |")
            continue
        lines.append(
            f"| {name} | {r.status} | {r.version} | {len(r.warnings)} |"
        )
    if context.errors:
        lines.append("")
        lines.append("**错误：**")
        _bullet_list(lines, [e.get("error", "") for e in context.errors])


# --- section 4: 数据来源与可信度 ----------------------------------------


def _section_4_sources(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    cr = context.config.get("confidence_rules", {})
    lines.append("**配置的数据源 → 可信度映射：**")
    lines.append("")
    _kv_table(lines, [(src, conf) for src, conf in cr.items()])
    lines.append("")
    lines.append(
        "说明：Mock 数据的可信度恒为 `low`（架构决策 #7）；用户输入"
        "为 `high`；CSV 导入为 `medium`。下游 Agent 在融合多个数据"
        "源时取最低可信度作为最终输出可信度。"
    )


# --- section 5: 关键词分析 -----------------------------------------------


def _section_5_keyword(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    kw = _get_output(context, "keyword", KeywordOutput)
    if not kw:
        lines.append("关键词 Agent 未运行。")
        return
    _kv_table(lines, [
        ("normalized_keyword", kw.normalized_keyword),
        ("keyword_intent", kw.keyword_intent),
        ("keyword_type", kw.keyword_type),
        ("competition", kw.competition),
        ("trend", kw.trend),
        ("search_volume", kw.search_volume if kw.search_volume is not None else "N/A (Mock)"),
        ("source", kw.source),
        ("confidence", kw.confidence),
    ])
    lines.append("")
    lines.append("**相关关键词：**")
    _bullet_list(lines, kw.related_keywords)


# --- section 6: 市场分析 -------------------------------------------------


def _section_6_market(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    m = _get_output(context, "market", MarketOutput)
    if not m:
        lines.append("市场 Agent 未运行。")
        return
    _kv_table(lines, [
        ("marketplace", m.marketplace),
        ("category", m.category),
        ("product_line", m.product_line),
        ("consumption_scenario", m.consumption_scenario),
        ("target_customer", m.target_customer),
        ("market_capacity", m.market_capacity),
        ("growth_trend", m.growth_trend),
        ("price_range", m.price_range),
        ("competition_level", m.competition_level),
        ("opportunity_score", m.opportunity_score),
        ("source", m.source),
        ("confidence", m.confidence),
    ])
    lines.append("")
    lines.append("**市场假设：**")
    _bullet_list(lines, m.market_assumptions)


# --- section 7: 竞品矩阵 -------------------------------------------------


def _section_7_competitor(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    c = _get_output(context, "competitor", CompetitorOutput)
    if not c:
        lines.append("竞品 Agent 未运行。")
        return
    lines.append("**竞品矩阵：**")
    lines.append("")
    lines.append("| Brand | ASIN | Price | Rating | Reviews | Source |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in c.competitor_matrix:
        lines.append(
            f"| {row.get('brand','')} | {row.get('asin','')} | "
            f"{row.get('price','')} | {row.get('rating','')} | "
            f"{row.get('review_count','')} | {row.get('source','')} |"
        )
    lines.append("")
    pd_ = c.price_distribution
    rd_ = c.rating_distribution
    rv = c.review_distribution
    _kv_table(lines, [
        ("price_min", pd_.get("min")),
        ("price_max", pd_.get("max")),
        ("price_avg", pd_.get("average")),
        ("rating_min", rd_.get("min")),
        ("rating_max", rd_.get("max")),
        ("rating_avg", rd_.get("average")),
        ("review_total", rv.get("total")),
        ("review_avg", rv.get("average")),
        ("source", c.source),
        ("confidence", c.confidence),
    ])
    lines.append("")
    lines.append("**共同卖点：**")
    _bullet_list(lines, c.common_selling_points)
    lines.append("**共同负面点：**")
    _bullet_list(lines, c.common_negative_points)
    lines.append("**市场空白：**")
    _bullet_list(lines, c.market_gaps)
    lines.append("**差异化机会：**")
    _bullet_list(lines, c.differentiation_opportunities)


# --- section 8: Review 痛点分析 -----------------------------------------


def _section_8_review(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    r = _get_output(context, "review", ReviewOutput)
    if not r:
        lines.append("Review Agent 未运行。")
        return
    lines.append(f"Review 总数: {r.review_count}")
    lines.append("")
    lines.append("**问题分类统计：**")
    lines.append("")
    _kv_table(lines, [(cat, n) for cat, n in r.issue_categories.items()])
    lines.append("")
    lines.append(f"情感摘要: {r.sentiment_summary}")
    lines.append("")
    lines.append("**正面主题：**")
    _bullet_list(lines, r.positive_themes)
    lines.append("**负面主题：**")
    _bullet_list(lines, r.negative_themes)
    lines.append("**功能请求：**")
    _bullet_list(lines, r.feature_requests)
    lines.append("**质量问题：**")
    _bullet_list(lines, r.quality_issues)
    lines.append("**包装问题：**")
    _bullet_list(lines, r.packaging_issues)
    lines.append("**产品改进方向：**")
    _bullet_list(lines, r.product_improvement_directions)


# --- section 9: 产品机会判断 --------------------------------------------


def _section_9_opportunity(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    o = _get_output(context, "opportunity", OpportunityOutput)
    if not o:
        lines.append("机会判断 Agent 未运行。")
        return
    _kv_table(lines, [
        ("market_opportunity (1-5)", o.market_opportunity),
        ("competition (1-5)", o.competition),
        ("supply_chain_feasibility (1-5)", o.supply_chain_feasibility),
        ("differentiation_potential (1-5)", o.differentiation_potential),
        ("development_recommendation", o.development_recommendation),
        ("human_review_required", o.human_review_required),
        ("confidence", o.confidence),
        ("source", o.source),
    ])
    lines.append("")
    lines.append("**立项理由：**")
    _bullet_list(lines, o.reasons)
    lines.append("**风险：**")
    _bullet_list(lines, o.risks)
    lines.append("**需要补充验证：**")
    _bullet_list(lines, o.required_validation)


# --- section 10: 产品开发规划 -------------------------------------------


def _section_10_product(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    p = _get_output(context, "product", ProductOutput)
    if not p:
        lines.append("产品规划 Agent 未运行。")
        return
    _kv_table(lines, [
        ("product_name", p.product_name),
        ("product_positioning", p.product_positioning),
        ("target_customer", p.target_customer),
        ("use_scenario", p.use_scenario),
        ("target_price", p.target_price),
        ("target_cost", p.target_cost),
        ("target_gross_margin", p.target_gross_margin),
        ("packaging_direction", p.packaging_direction),
        ("installation_direction", p.installation_direction),
        ("development_cycle_days", p.development_cycle_days),
        ("confidence", p.confidence),
        ("source", p.source),
    ])
    lines.append("")
    lines.append("**核心卖点：**")
    _bullet_list(lines, p.core_selling_points)
    lines.append("**功能设计：**")
    _bullet_list(lines, p.functional_design)
    lines.append("**差异化方案：**")
    _bullet_list(lines, p.differentiation_plan)
    lines.append("**上市风险：**")
    _bullet_list(lines, p.launch_risks)
    lines.append("**验证计划：**")
    _bullet_list(lines, p.validation_plan)
    lines.append("**供应商必问清单：**")
    _bullet_list(lines, p.required_supplier_questions)


# --- section 11: Amazon 利润测算 ---------------------------------------


def _section_11_profit(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    p = _get_output(context, "profit", None)
    if not p or not isinstance(p, dict):
        lines.append("利润 Agent 未运行。")
        return
    lines.append("本节展示 **基准情景** 的利润测算结果；其他情景见下一节。")
    lines.append("")
    base = p.get("base", {})
    if not base:
        lines.append("基准情景未计算。")
        return
    _kv_table(lines, [
        ("selling_price", base.get("selling_price")),
        ("unit_cost", base.get("unit_cost")),
        ("total_variable_cost_per_unit", base.get("total_variable_cost_per_unit")),
        ("unit_profit", base.get("unit_profit")),
        ("unit_margin", base.get("unit_margin")),
        ("estimated_monthly_units", base.get("estimated_monthly_units")),
        ("monthly_profit", base.get("monthly_profit")),
        ("annualized_profit", base.get("annualized_profit")),
        ("initial_investment", base.get("initial_investment")),
        ("roi", base.get("roi") if base.get("roi") is not None else "N/A (亏损或零投资)"),
        ("calculation_version", base.get("calculation_version")),
    ])
    lines.append("")
    lines.append(
        "**口径说明：** FBA 费、推荐费、仓储费、广告费、退货成本均"
        "计入单位变动成本；月固定成本包含月度运营开支；ROI 仅在"
        "初始投资 > 0 且月利润 > 0 时计算（亏损情景为 null）。"
    )


# --- section 12: 三种情景比较 -------------------------------------------


def _section_12_scenarios(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    p = _get_output(context, "profit", None)
    if not p or not isinstance(p, dict):
        lines.append("利润 Agent 未运行。")
        return
    lines.append("| 指标 | 基准 | 乐观 | 悲观 |")
    lines.append("| --- | --- | --- | --- |")
    metrics = [
        ("selling_price", "售价"),
        ("unit_cost", "单位成本"),
        ("unit_profit", "单位利润"),
        ("unit_margin", "毛利率"),
        ("monthly_profit", "月利润"),
        ("annualized_profit", "年化利润"),
        ("roi", "ROI"),
    ]
    for key, label in metrics:
        base_v = p.get("base", {}).get(key, "")
        opt_v = p.get("optimistic", {}).get(key, "")
        pes_v = p.get("pessimistic", {}).get(key, "")
        lines.append(f"| {label} | {base_v} | {opt_v} | {pes_v} |")
    lines.append("")
    lines.append(
        "**情景参数：** 三种情景的 9 个乘数（selling_price / units / "
        "unit_cost / fba_fee / referral_fee / storage_fee / "
        "advertising_cost / return_cost / fixed_development_cost）"
        "全部来自 `config/amazon_workflow.json:scenarios`，可在配置中"
        "调整，不需修改代码。"
    )


# --- section 13: 风险和验证计划 ----------------------------------------


def _section_13_risks(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    p = _get_output(context, "product", ProductOutput)
    o = _get_output(context, "opportunity", OpportunityOutput)
    lines.append("**主要风险：**")
    lines.append("")
    if p:
        _bullet_list(lines, p.launch_risks)
    else:
        lines.append("- 产品规划 Agent 未运行。")
    lines.append("")
    lines.append("**验证计划：**")
    lines.append("")
    if p:
        _bullet_list(lines, p.validation_plan)
    if o:
        lines.append("")
        lines.append("**Agent 建议补充验证：**")
        _bullet_list(lines, o.required_validation)


# --- section 14: 人工复核事项 -------------------------------------------


def _section_14_review_fields(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    o = _get_output(context, "opportunity", OpportunityOutput)
    if o and o.human_review_required:
        lines.append(
            "本机会被标记为 **需要人工复核**。以下情况触发人工复核："
        )
        lines.append("")
        lines.append("- 任一主要情景为负利润")
        lines.append("- 回本周期超过 24 个月")
        lines.append("- 收入来源存在较大差异")
        lines.append("- 高竞争且高交付难度")
        lines.append("- 敏感性分析中轻微参数变化导致等级下降两级或以上")
        lines.append("- 输入数据存在边界值或缺失关键数据")
        lines.append("")
        lines.append(
            "**注意：** 本工具是辅助决策工具，**不是最终投资决策系统**。"
            "所有 Agent 输出的建议必须经过人工复核后方可作为立项依据。"
        )
    else:
        lines.append("本机会未被标记为强制人工复核。")
        lines.append(
            "请注意：即使未被强制标记，本工具输出仍属于辅助决策参考，"
            "人工判断仍是必要环节。"
        )


# --- section 15: 最终建议 -----------------------------------------------


def _section_15_final_recommendation(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    o = _get_output(context, "opportunity", OpportunityOutput)
    if not o:
        lines.append("机会判断 Agent 未运行，无法给出最终建议。")
        return
    rec = o.development_recommendation
    lines.append(f"**Agent 建议: `{rec}`**")
    lines.append("")
    rec_text = {
        "develop": "建议进入正式开发阶段。所有评分维度均达标，且使用了真实数据。",
        "validate_first": "建议先完成关键假设的验证（客户需求、价格、成本、交付），再进入正式评审。",
        "monitor": "建议持续观察市场，暂不投入较大资源。",
        "reject_or_hold": "建议暂不立项，存在重大风险或价格无法覆盖成本。",
    }
    lines.append(rec_text.get(rec, "未知建议类型。"))
    lines.append("")
    if o.human_review_required:
        lines.append(
            "⚠ 该建议需人工复核后方可作为最终商业决策依据。"
        )
    lines.append("")
    lines.append(
        "**重要提示：** 本工具的输出属于辅助决策参考，最终是否立项需"
        "结合人工判断、市场调研和实际供应商报价综合决定。"
    )


# --- section 16: 数据限制和免责声明 ------------------------------------


def _section_16_disclaimer(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    lines.append(
        "1. **辅助决策工具**：本工具是辅助决策工具，不是最终投资决策系统。"
    )
    lines.append(
        "2. **数据来源**：V3 当前版本使用确定性 Mock 数据 + 用户输入，"
        "**不代表真实 Amazon 市场数据**。未来接入真实数据源（SP-API、"
        "第三方爬虫、广告 API）后才能产生有实际参考价值的结论。"
    )
    lines.append(
        "3. **未纳入内容**：本工具未纳入税费、融资成本、现金流时间"
        "价值和汇率风险。"
    )
    lines.append(
        "4. **情景参数**：三种情景的参数只是可配置假设，不代表真实"
        "市场预测。"
    )
    lines.append(
        "5. **人工复核**：人工复核仍然是必要环节，不能仅凭本工具"
        "输出做最终决策。"
    )
    lines.append(
        "6. **V1/V2 兼容**：V3 与 V1/V2 机会评估工具并存，使用独立的"
        "配置文件 `config/amazon_workflow.json` 与独立的输出目录，"
        "不影响 V1/V2 的 99 个测试。"
    )


# --- section 17: 可追溯信息 --------------------------------------------


def _section_17_traceability(
    lines: List[str], context: WorkflowContext, input_sha: Optional[str]
) -> None:
    av = context.config.get("agent_versions", {})
    agents_str = ", ".join(f"{n}={v}" for n, v in av.items())
    _kv_table(lines, [
        ("input_file_path", context.cli_args.get("input", "N/A")),
        ("input_sha256", input_sha or "N/A"),
        ("config_sha256", context.config_sha256 or "N/A"),
        ("workflow_version", context.config.get("workflow_version", "")),
        ("calculation_version", context.config.get("calculation_version", "")),
        ("agent_versions", agents_str),
        ("generated_at", context.generated_at),
        ("python_version", context.python_version),
        ("cli_args", json.dumps(context.cli_args, ensure_ascii=False)),
        ("final_status", context.final_status),
        ("agent_order", ", ".join(context.agent_order)),
        ("agents_run", len(context.agents)),
        ("errors_count", len(context.errors)),
        ("warnings_count", sum(len(r.warnings) for r in context.agents.values()) + len(context.warnings)),
    ])


# ---------------------------------------------------------------------------
# JSON builder
# ---------------------------------------------------------------------------


def _build_json(
    context: WorkflowContext,
    input_sha: Optional[str],
) -> Dict[str, Any]:
    """Build the JSON snapshot payload."""
    pi = context.product_input
    summary: Dict[str, Any] = {
        "final_status": context.final_status,
        "agents_run": len(context.agents),
        "errors_count": len(context.errors),
    }

    # Add opportunity summary if available
    opp = _get_output(context, "opportunity", OpportunityOutput)
    if opp:
        summary["opportunity"] = {
            "market_opportunity": opp.market_opportunity,
            "competition": opp.competition,
            "supply_chain_feasibility": opp.supply_chain_feasibility,
            "differentiation_potential": opp.differentiation_potential,
            "development_recommendation": opp.development_recommendation,
            "human_review_required": opp.human_review_required,
        }

    return {
        "metadata": {
            "workflow_version": context.config.get("workflow_version", ""),
            "calculation_version": context.config.get("calculation_version", ""),
            "agent_versions": dict(context.config.get("agent_versions", {})),
            "generated_at": context.generated_at,
            "python_version": context.python_version,
            "final_status": context.final_status,
            "input_sha256": input_sha,
            "config_sha256": context.config_sha256,
            "agent_order": list(context.agent_order),
        },
        "command": {
            "cli_args": dict(context.cli_args),
            "input_file_path": context.cli_args.get("input"),
        },
        "source": {
            "product_input": pi.to_dict() if pi else None,
        },
        "config_snapshot": dict(context.config),
        "data_quality": {
            "errors": list(context.errors),
            "warnings": list(context.warnings),
            "agent_warnings": {
                name: list(r.warnings) for name, r in context.agents.items()
            },
        },
        "summary": summary,
        "rankings": [],  # V3 has only one product; rankings reserved for future
        "scenarios": _extract_scenarios(context),
        "sensitivity": {},  # Reserved — sensitivity analysis not in V3 scope
        "opportunities": _extract_opportunities(context),
        "warnings": list(context.warnings),
        "agents": {
            name: r.to_dict() for name, r in context.agents.items()
        },
    }


def _extract_scenarios(context: WorkflowContext) -> Dict[str, Any]:
    """Pull profit scenarios from the profit agent's output dict."""
    p = _get_output(context, "profit", None)
    if not p or not isinstance(p, dict):
        return {}
    return {name: dict(scn) for name, scn in p.items()}


def _extract_opportunities(context: WorkflowContext) -> List[Dict[str, Any]]:
    """V3 has one opportunity per run; pack it as a single-element list."""
    o = _get_output(context, "opportunity", OpportunityOutput)
    if not o:
        return []
    return [o.to_dict()]
