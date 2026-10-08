"""Excel output agent for the V3 Amazon workflow.

Generates two Excel workbooks:

* **Market report** — Market_Analysis, Keyword_Analysis,
  Competitor_Matrix, Review_Analysis, Data_Quality sheets.
* **Product plan** — Product_Positioning, Product_Features,
  Differentiation, Cost_Target, Development_Timeline,
  Risks_Validation sheets.

Per architecture decision #8:

* ``openpyxl`` is **optional** — lazy-imported inside each function.
  If the import fails, the agent returns ``status="skipped"`` with a
  warning; MD/JSON are unaffected.
* Workbooks are written directly to ``data/amazon/output/`` (no
  separate ``templates/`` directory).
* :class:`Decimal` → :class:`float` conversion happens at the Excel
  boundary (documented precision loss; the JSON report preserves full
  precision via :class:`AmazonDecimalEncoder`).
* First row is frozen; columns auto-width (capped at 60 chars).
* Money/percent/date formats applied where applicable.

This module imports stdlib only at module level. ``openpyxl`` is
imported lazily inside :func:`generate_market_excel` and
:func:`generate_product_excel`.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    AgentResult,
    CompetitorOutput,
    KeywordOutput,
    MarketOutput,
    OpportunityOutput,
    ProductOutput,
    ReviewOutput,
    WorkflowContext,
)

NAME = "excel"
VERSION = "excel_agent_v1"

# Sheet name constants (locked so tests can assert)
MARKET_SHEETS: Tuple[str, ...] = (
    "Market_Analysis",
    "Keyword_Analysis",
    "Competitor_Matrix",
    "Review_Analysis",
    "Data_Quality",
)
PRODUCT_SHEETS: Tuple[str, ...] = (
    "Product_Positioning",
    "Product_Features",
    "Differentiation",
    "Cost_Target",
    "Development_Timeline",
    "Risks_Validation",
)

_MAX_COL_WIDTH = 60


# ---------------------------------------------------------------------------
# Decimal → float boundary conversion
# ---------------------------------------------------------------------------


def _to_float(value: Any) -> Any:
    """Convert Decimal values to float at the Excel boundary.

    Per decision #8 this loses precision (e.g. Decimal('1.10') → 1.1),
    but the JSON report keeps full precision via
    :class:`AmazonDecimalEncoder`. Strings, ints and None pass through.
    """
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, list):
        return [_to_float(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_float(v) for k, v in value.items()}
    return value


def _try_float(value: Any) -> Optional[float]:
    """Best-effort float conversion; None if not numeric."""
    if value is None:
        return None
    try:
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return float(str(value))
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Lazy openpyxl import helper
# ---------------------------------------------------------------------------


def _import_openpyxl() -> Optional[Any]:
    """Lazy-import openpyxl. Returns None if unavailable."""
    try:
        import openpyxl  # type: ignore[import]
        from openpyxl.styles import Alignment, Font, PatternFill  # noqa: F401
        return openpyxl
    except ImportError:
        return None


def _apply_formatting(openpyxl_module: Any, ws: Any) -> None:
    """Apply standard formatting to a sheet: freeze first row + widths."""
    ws.freeze_panes = "A2"
    # Auto-width capped at _MAX_COL_WIDTH
    for col_cells in ws.columns:
        max_len = 0
        col_letter = col_cells[0].column_letter
        for cell in col_cells:
            v = cell.value
            if v is None:
                continue
            s = str(v)
            if len(s) > max_len:
                max_len = len(s)
        width = min(max_len + 2, _MAX_COL_WIDTH)
        ws.column_dimensions[col_letter].width = width


def _write_rows(ws: Any, rows: List[List[Any]]) -> None:
    """Write a list of rows to the worksheet."""
    for r_idx, row in enumerate(rows, start=1):
        for c_idx, val in enumerate(row, start=1):
            cell = ws.cell(row=r_idx, column=c_idx)
            fval = _to_float(val)
            # Numeric formatting heuristic
            if isinstance(fval, float):
                cell.value = fval
                if fval >= 100 or fval == 0:
                    cell.number_format = "#,##0.00"
                elif 0 < fval < 10:
                    cell.number_format = "0.0000"
                else:
                    cell.number_format = "0.00"
            else:
                cell.value = fval


# ---------------------------------------------------------------------------
# Market Excel
# ---------------------------------------------------------------------------


def generate_market_excel(
    context: WorkflowContext, path: Path
) -> AgentResult:
    """Generate the Market Analysis Excel workbook.

    Sheets: Market_Analysis, Keyword_Analysis, Competitor_Matrix,
    Review_Analysis, Data_Quality.

    Returns:
        :class:`AgentResult` with status ``completed`` on success,
        ``skipped`` if openpyxl is missing.
    """
    openpyxl_module = _import_openpyxl()
    if openpyxl_module is None:
        return AgentResult(
            agent_name=NAME,
            status="skipped",
            error="openpyxl not installed; Excel generation skipped.",
            version=VERSION,
            source="calculated",
        )

    wb = openpyxl_module.Workbook()
    # Remove default sheet; we'll add named ones.
    default = wb.active
    wb.remove(default)

    _sheet_market_analysis(wb, context)
    _sheet_keyword_analysis(wb, context)
    _sheet_competitor_matrix(wb, context)
    _sheet_review_analysis(wb, context)
    _sheet_data_quality(wb, context)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return AgentResult(
        agent_name=NAME,
        status="completed",
        output={"market_excel": str(path)},
        assumptions=[
            "Decimal→float conversion at Excel boundary (decision #8).",
        ],
        version=VERSION,
        source="calculated",
    )


def _sheet_market_analysis(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(MARKET_SHEETS[0])
    m = context.get_output("market", MarketOutput)
    if not m:
        _write_rows(ws, [["Market_Analysis"], ["Agent not run"]])
        _apply_formatting(openpyxl=None, ws=ws)
        return
    rows: List[List[Any]] = [
        ["字段", "值"],
        ["marketplace", m.marketplace],
        ["category", m.category],
        ["product_line", m.product_line],
        ["consumption_scenario", m.consumption_scenario],
        ["target_customer", m.target_customer],
        ["market_capacity", m.market_capacity],
        ["growth_trend", m.growth_trend],
        ["price_range", m.price_range],
        ["competition_level", m.competition_level],
        ["opportunity_score", m.opportunity_score],
        ["source", m.source],
        ["confidence", m.confidence],
    ]
    _write_rows(ws, rows)
    _apply_formatting(None, ws)


def _sheet_keyword_analysis(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(MARKET_SHEETS[1])
    kw = context.get_output("keyword", KeywordOutput)
    if not kw:
        _write_rows(ws, [["Keyword_Analysis"], ["Agent not run"]])
        _apply_formatting(None, ws)
        return
    rows: List[List[Any]] = [
        ["字段", "值"],
        ["normalized_keyword", kw.normalized_keyword],
        ["keyword_intent", kw.keyword_intent],
        ["keyword_type", kw.keyword_type],
        ["competition", kw.competition],
        ["trend", kw.trend],
        ["search_volume", kw.search_volume if kw.search_volume is not None else "N/A"],
        ["source", kw.source],
        ["confidence", kw.confidence],
        [],
        ["相关关键词"],
    ]
    for r in kw.related_keywords:
        rows.append([r])
    _write_rows(ws, rows)
    _apply_formatting(None, ws)


def _sheet_competitor_matrix(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(MARKET_SHEETS[2])
    c = context.get_output("competitor", CompetitorOutput)
    if not c:
        _write_rows(ws, [["Competitor_Matrix"], ["Agent not run"]])
        _apply_formatting(None, ws)
        return
    header = ["Brand", "ASIN", "Product", "Price", "Rating", "Reviews",
              "Source"]
    rows: List[List[Any]] = [header]
    for row in c.competitor_matrix:
        rows.append([
            row.get("brand", ""),
            row.get("asin", ""),
            row.get("product_name", ""),
            row.get("price", ""),
            row.get("rating", ""),
            row.get("review_count", ""),
            row.get("source", ""),
        ])
    _write_rows(ws, rows)
    _apply_formatting(None, ws)


def _sheet_review_analysis(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(MARKET_SHEETS[3])
    r = context.get_output("review", ReviewOutput)
    if not r:
        _write_rows(ws, [["Review_Analysis"], ["Agent not run"]])
        _apply_formatting(None, ws)
        return
    rows: List[List[Any]] = [
        ["字段", "值"],
        ["review_count", r.review_count],
        ["source", r.source],
        ["confidence", r.confidence],
        [],
        ["问题分类", "数量"],
    ]
    for cat, n in r.issue_categories.items():
        rows.append([cat, n])
    rows.append([])
    rows.append(["正面主题"])
    for t in r.positive_themes:
        rows.append([t])
    rows.append([])
    rows.append(["负面主题"])
    for t in r.negative_themes:
        rows.append([t])
    _write_rows(ws, rows)
    _apply_formatting(None, ws)


def _sheet_data_quality(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(MARKET_SHEETS[4])
    rows: List[List[Any]] = [
        ["字段", "值"],
        ["errors_count", len(context.errors)],
        ["warnings_count", sum(len(r.warnings) for r in context.agents.values())],
        ["final_status", context.final_status],
        [],
        ["错误详情"],
    ]
    for e in context.errors:
        rows.append([e.get("agent", ""), e.get("error", "")])
    rows.append([])
    rows.append(["Agent 警告"])
    for name in context.agent_order:
        r = context.agents.get(name)
        if not r:
            continue
        for w in r.warnings:
            rows.append([name, w])
    _write_rows(ws, rows)
    _apply_formatting(None, ws)


# ---------------------------------------------------------------------------
# Product Excel
# ---------------------------------------------------------------------------


def generate_product_excel(
    context: WorkflowContext, path: Path
) -> AgentResult:
    """Generate the Product Plan Excel workbook.

    Sheets: Product_Positioning, Product_Features, Differentiation,
    Cost_Target, Development_Timeline, Risks_Validation.

    Returns:
        :class:`AgentResult` with status ``completed`` on success,
        ``skipped`` if openpyxl is missing.
    """
    openpyxl_module = _import_openpyxl()
    if openpyxl_module is None:
        return AgentResult(
            agent_name=NAME,
            status="skipped",
            error="openpyxl not installed; Excel generation skipped.",
            version=VERSION,
            source="calculated",
        )

    wb = openpyxl_module.Workbook()
    default = wb.active
    wb.remove(default)

    _sheet_product_positioning(wb, context)
    _sheet_product_features(wb, context)
    _sheet_differentiation(wb, context)
    _sheet_cost_target(wb, context)
    _sheet_development_timeline(wb, context)
    _sheet_risks_validation(wb, context)

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return AgentResult(
        agent_name=NAME,
        status="completed",
        output={"product_excel": str(path)},
        assumptions=[
            "Decimal→float conversion at Excel boundary (decision #8).",
        ],
        version=VERSION,
        source="calculated",
    )


def _sheet_product_positioning(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(PRODUCT_SHEETS[0])
    p = context.get_output("product", ProductOutput)
    if not p:
        _write_rows(ws, [["Product_Positioning"], ["Agent not run"]])
        _apply_formatting(None, ws)
        return
    rows: List[List[Any]] = [
        ["字段", "值"],
        ["product_name", p.product_name],
        ["product_positioning", p.product_positioning],
        ["target_customer", p.target_customer],
        ["use_scenario", p.use_scenario],
        ["target_price", p.target_price],
        ["target_cost", p.target_cost],
        ["target_gross_margin", p.target_gross_margin],
        ["confidence", p.confidence],
        ["source", p.source],
    ]
    _write_rows(ws, rows)
    _apply_formatting(None, ws)


def _sheet_product_features(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(PRODUCT_SHEETS[1])
    p = context.get_output("product", ProductOutput)
    if not p:
        _write_rows(ws, [["Product_Features"], ["Agent not run"]])
        _apply_formatting(None, ws)
        return
    rows: List[List[Any]] = [
        ["核心卖点"],
    ]
    for s in p.core_selling_points:
        rows.append([s])
    rows.append([])
    rows.append(["功能设计"])
    for f in p.functional_design:
        rows.append([f])
    _write_rows(ws, rows)
    _apply_formatting(None, ws)


def _sheet_differentiation(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(PRODUCT_SHEETS[2])
    p = context.get_output("product", ProductOutput)
    c = context.get_output("competitor", CompetitorOutput)
    rows: List[List[Any]] = []
    rows.append(["差异化方案"])
    if p:
        for d in p.differentiation_plan:
            rows.append([d])
    rows.append([])
    rows.append(["市场空白"])
    if c:
        for g in c.market_gaps:
            rows.append([g])
    _write_rows(ws, rows)
    _apply_formatting(None, ws)


def _sheet_cost_target(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(PRODUCT_SHEETS[3])
    p = context.get_output("product", ProductOutput)
    profit_result = context.agents.get("profit")
    profit = profit_result.output if profit_result else None
    if not p:
        _write_rows(ws, [["Cost_Target"], ["Agent not run"]])
        _apply_formatting(None, ws)
        return
    rows: List[List[Any]] = [
        ["字段", "值"],
        ["target_price", p.target_price],
        ["target_cost", p.target_cost],
        ["target_gross_margin", p.target_gross_margin],
    ]
    if profit and isinstance(profit, dict):
        base = profit.get("base", {})
        rows.append([])
        rows.append(["— 基准情景利润测算 —", ""])
        rows.append(["selling_price", base.get("selling_price", "")])
        rows.append(["unit_cost", base.get("unit_cost", "")])
        rows.append(["total_variable_cost_per_unit", base.get("total_variable_cost_per_unit", "")])
        rows.append(["unit_profit", base.get("unit_profit", "")])
        rows.append(["unit_margin", base.get("unit_margin", "")])
        rows.append(["monthly_profit", base.get("monthly_profit", "")])
        rows.append(["annualized_profit", base.get("annualized_profit", "")])
        rows.append(["initial_investment", base.get("initial_investment", "")])
        rows.append(["roi", base.get("roi") if base.get("roi") is not None else "N/A"])
    _write_rows(ws, rows)
    _apply_formatting(None, ws)


def _sheet_development_timeline(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(PRODUCT_SHEETS[4])
    p = context.get_output("product", ProductOutput)
    if not p:
        _write_rows(ws, [["Development_Timeline"], ["Agent not run"]])
        _apply_formatting(None, ws)
        return
    rows: List[List[Any]] = [
        ["字段", "值"],
        ["development_cycle_days", p.development_cycle_days],
        ["packaging_direction", p.packaging_direction],
        ["installation_direction", p.installation_direction],
    ]
    _write_rows(ws, rows)
    _apply_formatting(None, ws)


def _sheet_risks_validation(wb: Any, context: WorkflowContext) -> None:
    ws = wb.create_sheet(PRODUCT_SHEETS[5])
    p = context.get_output("product", ProductOutput)
    o = context.get_output("opportunity", OpportunityOutput)
    rows: List[List[Any]] = []
    rows.append(["上市风险"])
    if p:
        for r in p.launch_risks:
            rows.append([r])
    rows.append([])
    rows.append(["验证计划"])
    if p:
        for v in p.validation_plan:
            rows.append([v])
    rows.append([])
    rows.append(["Agent 建议补充验证"])
    if o:
        for v in o.required_validation:
            rows.append([v])
    rows.append([])
    rows.append(["供应商必问清单"])
    if p:
        for q in p.required_supplier_questions:
            rows.append([q])
    _write_rows(ws, rows)
    _apply_formatting(None, ws)
