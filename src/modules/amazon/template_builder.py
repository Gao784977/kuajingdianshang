"""V3.1.4 — Template extractor and market research report builder.

Two responsibilities per the V3.1 spec section 七 (template extraction)
and section 八 (market research report output):

1. :func:`extract_templates` — take a user-provided reference workbook
   (e.g. 家禽护理-市调.xlsx) and produce two clean, reusable blank
   templates under ``data/amazon/templates/``:

   * ``market_research_template.xlsx`` — the *US-类目分析* + *市场分析*
     sheets (category analysis + market analysis structure).
   * ``product_development_template.xlsx`` — the *产品信息* sheet
     (product development planning structure).

   Cleanup is strict per project memory:

   * DELETE: example business data, products, ASINs, brands, analysis
     text, suppliers, links, images, charts, ``=_xlfn.DISPIMG(...)``
     image-placeholder formulas.
   * KEEP: sheet names, order, headers, merged cells, styles,
     non-DISPIMG formulas, data validation, comments, row heights,
     column widths, page setup, hidden rows/cols, image layout
     position (the image itself is deleted).

2. :func:`build_market_research_report` — copy a template and fill it
   with analyzer results to produce a project-named report. At least 9
   sheet categories per spec section 八:

   类目分析 / 市场分析 / 关键词分析 / 竞品明细 / 品牌分析 /
   卖家分析 / 搜索位置分析 / 数据质量 / 来源和追溯

   Output filename: ``{project_name}_market_research_report_{ts}.xlsx``.

The original template is never modified. ``openpyxl`` is lazy-imported
to preserve the V3.0 lazy-load contract (decision #8).
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

NAME = "template_builder"
VERSION = "template_builder_v3_1_4"

_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"

# Sheet-name constants for the 9 report sheets. Locked so tests can
# assert against them. Names combine a Chinese label (so the spec's 9
# categories are obvious) with an English suffix (so downstream tooling
# can address sheets by ASCII id).
REPORT_SHEETS: Tuple[str, ...] = (
    "类目分析_Category_Analysis",
    "市场分析_Market_Analysis",
    "关键词分析_Keyword_Analysis",
    "竞品明细_Competitor_Detail",
    "品牌分析_Brand_Analysis",
    "卖家分析_Seller_Analysis",
    "搜索位置分析_Search_Position",
    "数据质量_Data_Quality",
    "来源和追溯_Source_Traceability",
)

# Role tags used to drive per-sheet cleanup behaviour in
# :func:`_strip_worksheet`. Tied to the structure of the reference
# workbook, not to a specific file name.
_ROLE_CATEGORY = "category_analysis"
_ROLE_MARKET = "market_data"
_ROLE_PRODUCT = "product_development"


# ---------------------------------------------------------------------------
# Lazy openpyxl import helper (mirrors excel_agent._import_openpyxl)
# ---------------------------------------------------------------------------


def _import_openpyxl() -> Optional[Any]:
    """Lazy-import openpyxl. Returns None if unavailable."""
    try:
        import openpyxl  # type: ignore[import]

        return openpyxl
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Cleanup primitives
# ---------------------------------------------------------------------------


def _is_dispimg_formula(value: Any) -> bool:
    """True when ``value`` is a ``=_xlfn.DISPIMG(...)`` image placeholder.

    These formulas embed an image into the cell in WPS/钉钉 documents.
    Per spec section 七 we delete images, so the placeholder formula is
    cleared (the cell stays, retaining its style and merge membership).

    Match is case-insensitive so ``=dispimg(...)`` (lowercase) and
    ``=DISPIMG(...)`` (uppercase) are both recognised — different
    spreadsheet apps emit different casings.
    """
    if value is None:
        return False
    s = str(value).strip().upper()
    return s.startswith("=_XLFN.DISPIMG") or "DISPIMG" in s


def _strip_images(ws: Any) -> None:
    """Remove all image and chart objects from ``ws`` in place.

    Per spec: keep image layout position (i.e. the cell anchors the
    image occupied) but delete the image itself. Removing the
    ``_images`` / ``_charts`` lists drops the embedded media while
    leaving every other worksheet property (merges, styles, dims)
    untouched.
    """
    if hasattr(ws, "_images"):
        # Assign a fresh list rather than ``.clear()`` so we don't
        # mutate a list shared with the parent workbook if any.
        ws._images = []
    if hasattr(ws, "_charts"):
        ws._charts = []


def _row_is_instruction(ws: Any, row: int, max_col: int) -> bool:
    """Heuristic: a row is a "填表说明" instruction row when at least
    3 of its non-empty cells start with ``填`` or ``截图``.

    Such rows are guidance text, not example data, and are kept per
    spec (they document how to fill the column).
    """
    if max_col < 1:
        return False
    hits = 0
    non_empty = 0
    for c in range(1, max_col + 1):
        v = ws.cell(row, c).value
        if v is None:
            continue
        s = str(v).strip()
        if not s:
            continue
        non_empty += 1
        if s.startswith("填") or s.startswith("截图") or s.startswith("黏贴"):
            hits += 1
    if non_empty == 0:
        return False
    return hits >= 3 and hits >= (non_empty // 2)


def _strip_category_sheet(ws: Any) -> None:
    """Clean a *US-类目分析* style sheet (single-column section layout).

    Sheet 1 of the reference workbook: column A holds section titles
    and DISPIMG image placeholders, column B holds analysis text. Rows
    where A:B is merged are section headers (kept). DISPIMG formulas
    and long analysis text (>50 chars) are cleared.
    """
    _strip_images(ws)
    max_row = ws.max_row or 1
    max_col = ws.max_column or 1
    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            cell = ws.cell(r, c)
            v = cell.value
            if v is None:
                continue
            s = str(v).strip()
            if _is_dispimg_formula(s):
                cell.value = None
                continue
            # Long body text (analysis paragraphs) is example data.
            # Section titles are short (typically < 20 chars); keep
            # them. Use 30 as the threshold so ~44-char analysis
            # sentences are cleared while real titles survive.
            if len(s) > 30:
                cell.value = None


def _strip_market_data_sheet(ws: Any) -> None:
    """Clean a *市场分析* / *产品信息* style sheet (two-row header).

    Sheets 2 and 3 of the reference workbook: rows 1-2 are the two-row
    header (kept). Rows whose every non-empty cell starts with ``填``
    / ``截图`` are instruction rows (kept). All other rows are example
    business data — their cell values are cleared but styles, merges
    and dimensions are preserved.
    """
    _strip_images(ws)
    max_row = ws.max_row or 1
    max_col = ws.max_column or 1
    for r in range(1, max_row + 1):
        # Rows 1 and 2 are headers — keep untouched.
        if r in (1, 2):
            continue
        # Instruction rows (填写说明) — keep untouched.
        if _row_is_instruction(ws, r, max_col):
            continue
        # Everything else is example data — clear values, keep style.
        for c in range(1, max_col + 1):
            cell = ws.cell(r, c)
            if cell.value is None:
                continue
            cell.value = None


def _strip_worksheet(ws: Any, role: str) -> None:
    """Dispatch to the right cleanup routine for ``role``.

    Unknown roles still get images stripped (defensive).
    """
    if role == _ROLE_CATEGORY:
        _strip_category_sheet(ws)
    elif role in (_ROLE_MARKET, _ROLE_PRODUCT):
        _strip_market_data_sheet(ws)
    else:
        _strip_images(ws)


# ---------------------------------------------------------------------------
# Template extraction
# ---------------------------------------------------------------------------


# Sheet-name -> role mapping for the reference workbook. The keys are
# exact sheet titles in the user-provided 家禽护理-市调.xlsx; tests
# build synthetic workbooks that reuse these names so the mapping is
# stable regardless of which physical file is supplied.
_SHEET_ROLES: Dict[str, str] = {
    "US-类目分析": _ROLE_CATEGORY,
    "市场分析": _ROLE_MARKET,
    "产品信息": _ROLE_PRODUCT,
}


@dataclass
class TemplateExtraction:
    """Result of :func:`extract_templates`.

    Captures the two output paths and a per-sheet audit of what was
    cleaned, so callers (and tests) can verify that images were
    removed, headers retained, etc.
    """

    market_research_template: Optional[Path] = None
    product_development_template: Optional[Path] = None
    cleaned_sheets: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "market_research_template": (
                str(self.market_research_template)
                if self.market_research_template
                else None
            ),
            "product_development_template": (
                str(self.product_development_template)
                if self.product_development_template
                else None
            ),
            "cleaned_sheets": list(self.cleaned_sheets),
            "errors": list(self.errors),
        }


def extract_templates(
    source_xlsx_path: Path,
    output_dir: Path,
) -> TemplateExtraction:
    """Extract two blank templates from a reference workbook.

    Args:
        source_xlsx_path: Path to the user-provided reference xlsx
            (e.g. 家禽护理-市调.xlsx). The file is read-only; never
            modified.
        output_dir: Destination directory for the two templates.
            Created if missing. Per project memory templates live
            under ``data/amazon/templates/``.

    Returns:
        :class:`TemplateExtraction` with the two output paths and a
        per-sheet audit. If openpyxl is unavailable, both paths are
        None and ``errors`` explains why.
    """
    openpyxl = _import_openpyxl()
    if openpyxl is None:
        return TemplateExtraction(
            errors=["openpyxl not installed; template extraction skipped."]
        )

    src = Path(source_xlsx_path)
    if not src.exists():
        return TemplateExtraction(errors=[f"source not found: {src}"])

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    wb_src = openpyxl.load_workbook(str(src), data_only=False)
    # Build the two template workbooks by copying sheets from the
    # source. We can't use wb_src.copy_worksheet across workbooks, so
    # we load the source twice and delete the sheets we don't want.
    # This preserves styles/merges/dims faithfully (openpyxl reload
    # carries the full style table).

    market_path = out / "market_research_template.xlsx"
    product_path = out / "product_development_template.xlsx"

    cleaned: List[Dict[str, Any]] = []

    # --- market_research_template.xlsx: US-类目分析 + 市场分析 ---
    wb_market = openpyxl.load_workbook(str(src), data_only=False)
    for ws_name in list(wb_market.sheetnames):
        if ws_name not in ("US-类目分析", "市场分析"):
            del wb_market[ws_name]
            continue
        ws = wb_market[ws_name]
        role = _SHEET_ROLES.get(ws_name, "unknown")
        audit = _audit_sheet(ws)
        _strip_worksheet(ws, role)
        audit_after = _audit_sheet(ws)
        cleaned.append(
            {
                "template": "market_research",
                "sheet": ws_name,
                "role": role,
                "before": audit,
                "after": audit_after,
            }
        )
    # Ensure sheet order matches the reference (US-类目分析 first).
    wb_market.save(str(market_path))

    # --- product_development_template.xlsx: 产品信息 ---
    wb_product = openpyxl.load_workbook(str(src), data_only=False)
    for ws_name in list(wb_product.sheetnames):
        if ws_name != "产品信息":
            del wb_product[ws_name]
            continue
        ws = wb_product[ws_name]
        role = _SHEET_ROLES.get(ws_name, "unknown")
        audit = _audit_sheet(ws)
        _strip_worksheet(ws, role)
        audit_after = _audit_sheet(ws)
        cleaned.append(
            {
                "template": "product_development",
                "sheet": ws_name,
                "role": role,
                "before": audit,
                "after": audit_after,
            }
        )
    wb_product.save(str(product_path))

    return TemplateExtraction(
        market_research_template=market_path,
        product_development_template=product_path,
        cleaned_sheets=cleaned,
    )


def _audit_sheet(ws: Any) -> Dict[str, Any]:
    """Snapshot of a sheet's structural state for before/after compare."""
    max_row = ws.max_row or 0
    max_col = ws.max_column or 0
    image_count = len(getattr(ws, "_images", []))
    chart_count = len(getattr(ws, "_charts", []))
    merged_count = len(ws.merged_cells.ranges) if ws.merged_cells else 0
    non_empty_cells = 0
    dispimg_cells = 0
    long_text_cells = 0
    for r in range(1, max_row + 1):
        for c in range(1, max_col + 1):
            v = ws.cell(r, c).value
            if v is None:
                continue
            s = str(v).strip()
            if not s:
                continue
            non_empty_cells += 1
            if _is_dispimg_formula(s):
                dispimg_cells += 1
            if len(s) > 50:
                long_text_cells += 1
    return {
        "sheet_title": ws.title,
        "max_row": max_row,
        "max_col": max_col,
        "image_count": image_count,
        "chart_count": chart_count,
        "merged_count": merged_count,
        "non_empty_cells": non_empty_cells,
        "dispimg_cells": dispimg_cells,
        "long_text_cells": long_text_cells,
    }


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------


@dataclass
class ReportBuildResult:
    """Result of :func:`build_market_research_report`."""

    output_path: Optional[Path] = None
    sheets_written: List[str] = field(default_factory=list)
    rows_written: int = 0
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output_path": (
                str(self.output_path) if self.output_path else None
            ),
            "sheets_written": list(self.sheets_written),
            "rows_written": self.rows_written,
            "errors": list(self.errors),
        }


def build_market_research_report(
    project_name: str,
    analyzer_results: Dict[str, Any],
    template_path: Optional[Path],
    output_dir: Path,
) -> ReportBuildResult:
    """Build a project-named market research Excel report.

    The report contains the 9 spec sheets (:data:`REPORT_SHEETS`) filled
    from ``analyzer_results``. When ``template_path`` is supplied and
    exists, the template is *copied* first (the original is never
    modified) and the 9 analysis sheets are appended to the copy. When
    the template is missing or openpyxl is unavailable, the function
    still produces a fresh workbook with the 9 sheets.

    Args:
        project_name: Project name used in the output filename. Per
            spec section 八 the filename is
            ``{project_name}_market_research_report_{ts}.xlsx``;
            ``project_name`` must not be hardcoded.
        analyzer_results: Dict mapping analyzer keys to their
            ``to_dict()`` output. Recognised keys (any may be missing):

            * ``multi_keyword``  — :func:`analyze_keywords` output
            * ``multi_category`` — :func:`analyze_categories` output
            * ``brand``          — :func:`analyze_brands` output
            * ``seller``         — :func:`analyze_sellers` output
            * ``search_position`` — :func:`analyze_search_positions` output
            * ``products``       — list of normalised product dicts
            * ``market``         — V3.0 MarketOutput.to_dict() (optional)

        template_path: Path to a clean template produced by
            :func:`extract_templates`. May be None.
        output_dir: Destination directory. Per project memory final
            output lives under ``data/output/``.

    Returns:
        :class:`ReportBuildResult` with the output path and audit. If
        openpyxl is unavailable, ``output_path`` is None.
    """
    openpyxl = _import_openpyxl()
    if openpyxl is None:
        return ReportBuildResult(
            errors=["openpyxl not installed; report build skipped."]
        )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # Load workbook: copy template if provided, else fresh.
    if template_path is not None and Path(template_path).exists():
        # Copy first — never modify the original template.
        ts = datetime.now().strftime(_TIMESTAMP_FMT)
        filename = f"{_sanitize(project_name)}_market_research_report_{ts}.xlsx"
        dest = out / filename
        shutil.copy2(str(template_path), str(dest))
        wb = openpyxl.load_workbook(str(dest))
    else:
        ts = datetime.now().strftime(_TIMESTAMP_FMT)
        filename = f"{_sanitize(project_name)}_market_research_report_{ts}.xlsx"
        dest = out / filename
        wb = openpyxl.Workbook()
        # Remove the default sheet; we'll add named ones.
        if wb.active is not None:
            wb.remove(wb.active)

    sheets_written: List[str] = []
    rows_written = 0

    # 1. 类目分析
    rows_written += _write_category_sheet(
        wb, REPORT_SHEETS[0], analyzer_results.get("multi_category")
    )
    sheets_written.append(REPORT_SHEETS[0])

    # 2. 市场分析
    rows_written += _write_market_sheet(
        wb, REPORT_SHEETS[1], analyzer_results.get("market")
    )
    sheets_written.append(REPORT_SHEETS[1])

    # 3. 关键词分析
    rows_written += _write_keyword_sheet(
        wb, REPORT_SHEETS[2], analyzer_results.get("multi_keyword")
    )
    sheets_written.append(REPORT_SHEETS[2])

    # 4. 竞品明细
    rows_written += _write_competitor_sheet(
        wb, REPORT_SHEETS[3], analyzer_results.get("products")
    )
    sheets_written.append(REPORT_SHEETS[3])

    # 5. 品牌分析
    rows_written += _write_brand_sheet(
        wb, REPORT_SHEETS[4], analyzer_results.get("brand")
    )
    sheets_written.append(REPORT_SHEETS[4])

    # 6. 卖家分析
    rows_written += _write_seller_sheet(
        wb, REPORT_SHEETS[5], analyzer_results.get("seller")
    )
    sheets_written.append(REPORT_SHEETS[5])

    # 7. 搜索位置分析
    rows_written += _write_search_position_sheet(
        wb, REPORT_SHEETS[6], analyzer_results.get("search_position")
    )
    sheets_written.append(REPORT_SHEETS[6])

    # 8. 数据质量
    rows_written += _write_data_quality_sheet(
        wb, REPORT_SHEETS[7], analyzer_results
    )
    sheets_written.append(REPORT_SHEETS[7])

    # 9. 来源和追溯
    rows_written += _write_source_traceability_sheet(
        wb, REPORT_SHEETS[8], analyzer_results
    )
    sheets_written.append(REPORT_SHEETS[8])

    wb.save(str(dest))
    return ReportBuildResult(
        output_path=dest,
        sheets_written=sheets_written,
        rows_written=rows_written,
    )


def _sanitize(name: str) -> str:
    """Make ``name`` safe for a filename (ASCII + underscores).

    Keeps alphanumerics, ``-``, ``_``, spaces (→ ``_``) and CJK
    characters. Every other character (``/``, ``?``, ``\\``, ``:``,
    ``*``, ``<``, ``>``, ``|``, quotes, etc.) is replaced with
    ``_`` so the filename never implies a subdirectory or violates
    Windows/POSIX naming rules.
    """
    if not name:
        return "project"
    out_chars = []
    for ch in str(name):
        if ch.isalnum() or ch in ("-", "_"):
            out_chars.append(ch)
        elif ch.isspace():
            out_chars.append("_")
        elif "\u4e00" <= ch <= "\u9fff":
            # CJK Unified Ideograph — keep (filesystems handle it).
            out_chars.append(ch)
        else:
            # Path separators and other unsafe chars get replaced.
            out_chars.append("_")
    result = "".join(out_chars).strip("_") or "project"
    return result


# ---------------------------------------------------------------------------
# Sheet writers — each returns the number of data rows written.
# ---------------------------------------------------------------------------


def _new_sheet(wb: Any, name: str) -> Any:
    """Create or reuse a sheet named ``name`` in ``wb``."""
    if name in wb.sheetnames:
        return wb[name]
    return wb.create_sheet(name)


def _write_rows(ws: Any, rows: List[List[Any]]) -> int:
    """Write a 2D list to ``ws`` starting at A1. Returns row count."""
    for r_idx, row in enumerate(rows, start=1):
        for c_idx, val in enumerate(row, start=1):
            ws.cell(r_idx, c_idx, val)
    return len(rows)


def _write_category_sheet(
    wb: Any, name: str, data: Optional[Dict[str, Any]]
) -> int:
    ws = _new_sheet(wb, name)
    if not data:
        return _write_rows(ws, [["类目分析 Category Analysis"], ["无数据 no data"]])
    rows: List[List[Any]] = [
        [
            "category",
            "product_count",
            "market_sales",
            "market_revenue",
            "average_price",
            "median_price",
            "growth",
            "competition",
            "market_capacity_rank",
            "growth_rank",
            "competition_rank",
            "opportunity_score",
            "source_files",
            "requires_review",
        ]
    ]
    for c in data.get("comparisons", []):
        rows.append(
            [
                c.get("category"),
                c.get("product_count"),
                c.get("market_sales"),
                c.get("market_revenue"),
                c.get("average_price"),
                c.get("median_price"),
                c.get("growth"),
                c.get("competition"),
                c.get("market_capacity_rank"),
                c.get("growth_rank"),
                c.get("competition_rank"),
                c.get("opportunity_score"),
                ", ".join(c.get("source_files", [])),
                c.get("requires_review"),
            ]
        )
    # Summary block
    rows.append([])
    rows.append(["total_categories", data.get("total_categories", 0)])
    rows.append(["total_market_revenue", data.get("total_market_revenue")])
    rows.append(["requires_review", data.get("requires_review", False)])
    return _write_rows(ws, rows)


def _write_market_sheet(
    wb: Any, name: str, data: Optional[Dict[str, Any]]
) -> int:
    ws = _new_sheet(wb, name)
    if not data:
        return _write_rows(ws, [["市场分析 Market Analysis"], ["无数据 no data"]])
    rows: List[List[Any]] = [
        ["字段 field", "值 value", "来源 source", "置信度 confidence"],
    ]
    for k, v in data.items():
        if isinstance(v, (dict, list)):
            v = str(v)
        rows.append(
            [
                k,
                v,
                data.get("source", "agent_inference"),
                data.get("confidence", "low"),
            ]
        )
    return _write_rows(ws, rows)


def _write_keyword_sheet(
    wb: Any, name: str, data: Optional[Dict[str, Any]]
) -> int:
    ws = _new_sheet(wb, name)
    if not data:
        return _write_rows(ws, [["关键词分析 Keyword Analysis"], ["无数据 no data"]])
    rows: List[List[Any]] = [
        [
            "keyword",
            "search_volume",
            "search_growth",
            "click_share",
            "conversion_share",
            "competition",
            "rank_by_search_volume",
            "rank_by_click_share",
            "rank_by_conversion_share",
            "opportunity_score",
            "source_files",
            "requires_review",
        ]
    ]
    for r in data.get("rankings", []):
        rows.append(
            [
                r.get("keyword"),
                r.get("search_volume"),
                r.get("search_growth"),
                r.get("click_share"),
                r.get("conversion_share"),
                r.get("competition"),
                r.get("rank_by_search_volume"),
                r.get("rank_by_click_share"),
                r.get("rank_by_conversion_share"),
                r.get("opportunity_score"),
                ", ".join(r.get("source_files", [])),
                r.get("requires_review"),
            ]
        )
    rows.append([])
    rows.append(["total_keywords", data.get("total_keywords", 0)])
    rows.append(["total_search_volume", data.get("total_search_volume")])
    rows.append(["avg_click_share", data.get("avg_click_share")])
    rows.append(["avg_conversion_share", data.get("avg_conversion_share")])
    rows.append(["high_potential_count", len(data.get("high_potential_keywords", []))])
    rows.append(["requires_review", data.get("requires_review", False)])
    return _write_rows(ws, rows)


def _write_competitor_sheet(
    wb: Any, name: str, data: Optional[Any]
) -> int:
    ws = _new_sheet(wb, name)
    if not data:
        return _write_rows(ws, [["竞品明细 Competitor Detail"], ["无数据 no data"]])
    # ``data`` may be a list of product dicts or a dict containing
    # a ``products`` key.
    if isinstance(data, dict):
        products = data.get("products", [])
    else:
        products = list(data)
    rows: List[List[Any]] = [
        [
            "asin",
            "parent_asin",
            "title",
            "brand",
            "seller",
            "price",
            "monthly_sales",
            "monthly_revenue",
            "rating",
            "review_count",
            "bsr_rank",
            "fulfillment",
            "listing_date",
            "source_type",
            "source_file",
            "confidence",
            "requires_review",
        ]
    ]
    for p in products:
        rows.append(
            [
                p.get("asin"),
                p.get("parent_asin"),
                p.get("title"),
                p.get("brand"),
                p.get("seller"),
                p.get("price"),
                p.get("monthly_sales"),
                p.get("monthly_revenue"),
                p.get("rating"),
                p.get("review_count"),
                p.get("bsr_rank"),
                p.get("fulfillment"),
                p.get("listing_date"),
                p.get("source_type"),
                p.get("source_file"),
                p.get("confidence"),
                p.get("requires_review"),
            ]
        )
    return _write_rows(ws, rows)


def _write_brand_sheet(
    wb: Any, name: str, data: Optional[Dict[str, Any]]
) -> int:
    ws = _new_sheet(wb, name)
    if not data:
        return _write_rows(ws, [["品牌分析 Brand Analysis"], ["无数据 no data"]])
    rows: List[List[Any]] = [
        ["指标 metric", "值 value", "来源 source"],
        ["total_brands", data.get("total_brands", 0), "calculated"],
        ["cr4", data.get("cr4"), "calculated"],
        ["cr8", data.get("cr8"), "calculated"],
        ["hhi", data.get("hhi"), "calculated"],
        ["market_concentration", data.get("market_concentration"), "calculated"],
        ["share_basis", data.get("share_basis"), "calculated"],
        ["requires_review", data.get("requires_review", False), "calculated"],
        [],
        ["品牌 brand", "份额 share", "来源 source"],
    ]
    for b in data.get("top8_brands", []):
        rows.append(
            [
                b.get("brand") or b.get("seller"),
                b.get("share"),
                ", ".join(data.get("source_files", [])),
            ]
        )
    rows.append([])
    rows.append(["新品牌机会 new brand opportunities"])
    for n in data.get("new_brand_opportunities", []):
        rows.append(
            [
                n.get("brand"),
                n.get("share"),
                n.get("launch_date"),
            ]
        )
    return _write_rows(ws, rows)


def _write_seller_sheet(
    wb: Any, name: str, data: Optional[Dict[str, Any]]
) -> int:
    ws = _new_sheet(wb, name)
    if not data:
        return _write_rows(ws, [["卖家分析 Seller Analysis"], ["无数据 no data"]])
    rows: List[List[Any]] = [
        ["指标 metric", "值 value", "来源 source"],
        ["total_sellers", data.get("total_sellers", 0), "calculated"],
        ["cr4", data.get("cr4"), "calculated"],
        ["cr8", data.get("cr8"), "calculated"],
        ["hhi", data.get("hhi"), "calculated"],
        ["market_concentration", data.get("market_concentration"), "calculated"],
        ["fba_count", data.get("fba_count", 0), "calculated"],
        ["fbm_count", data.get("fbm_count", 0), "calculated"],
        ["unknown_fulfillment_count", data.get("unknown_fulfillment_count", 0), "calculated"],
        ["fba_ratio", data.get("fba_ratio"), "calculated"],
        ["share_basis", data.get("share_basis"), "calculated"],
        ["requires_review", data.get("requires_review", False), "calculated"],
        [],
        ["卖家 seller", "份额 share", "来源 source"],
    ]
    for s in data.get("top8_sellers", []):
        rows.append(
            [
                s.get("seller") or s.get("brand"),
                s.get("share"),
                ", ".join(data.get("source_files", [])),
            ]
        )
    rows.append([])
    rows.append(["卖家地区 seller_locations"])
    for loc, cnt in (data.get("seller_locations") or {}).items():
        rows.append([loc, cnt, "calculated"])
    return _write_rows(ws, rows)


def _write_search_position_sheet(
    wb: Any, name: str, data: Optional[Dict[str, Any]]
) -> int:
    ws = _new_sheet(wb, name)
    if not data:
        return _write_rows(ws, [["搜索位置分析 Search Position Analysis"], ["无数据 no data"]])
    rows: List[List[Any]] = [
        [
            "keyword",
            "unique_asin_count",
            "total_appearances",
            "sponsored_count",
            "organic_count",
            "unknown_placement_count",
            "top_asins",
            "source_files",
        ]
    ]
    for m in data.get("matrix", []):
        top_asins_str = ", ".join(
            f"{a.get('asin','')}({a.get('appearances','')})"
            for a in (m.get("top_asins") or [])
        )
        rows.append(
            [
                m.get("keyword"),
                m.get("unique_asin_count"),
                m.get("total_appearances"),
                m.get("sponsored_count"),
                m.get("organic_count"),
                m.get("unknown_placement_count"),
                top_asins_str,
                ", ".join(m.get("source_files", [])),
            ]
        )
    rows.append([])
    rows.append(["total_appearances", data.get("total_appearances", 0)])
    rows.append(["total_sponsored", data.get("total_sponsored", 0)])
    rows.append(["total_organic", data.get("total_organic", 0)])
    rows.append(["sponsored_ratio", data.get("sponsored_ratio")])
    rows.append(["keyword_count", data.get("keyword_count", 0)])
    rows.append(["unique_asin_count", data.get("unique_asin_count", 0)])
    rows.append(["avg_asin_per_keyword", data.get("avg_asin_per_keyword")])
    rows.append(["requires_review", data.get("requires_review", False)])
    return _write_rows(ws, rows)


def _write_data_quality_sheet(
    wb: Any, name: str, analyzer_results: Dict[str, Any]
) -> int:
    ws = _new_sheet(wb, name)
    rows: List[List[Any]] = [
        ["分析器 analyzer", "requires_review", "source_files_count", "notes"]
    ]
    keys = (
        ("multi_keyword", "关键词分析"),
        ("multi_category", "类目分析"),
        ("brand", "品牌分析"),
        ("seller", "卖家分析"),
        ("search_position", "搜索位置分析"),
    )
    for key, label in keys:
        block = analyzer_results.get(key)
        if not block:
            rows.append([label, "N/A", 0, "analyzer not run"])
            continue
        requires = block.get("requires_review", False)
        src_count = len(block.get("source_files", []))
        rows.append(
            [
                label,
                requires,
                src_count,
                "needs manual review" if requires else "passed",
            ]
        )
    return _write_rows(ws, rows)


def _write_source_traceability_sheet(
    wb: Any, name: str, analyzer_results: Dict[str, Any]
) -> int:
    ws = _new_sheet(wb, name)
    rows: List[List[Any]] = [
        ["分析器 analyzer", "source_file", "source_type", "confidence"]
    ]
    keys = (
        ("multi_keyword", "关键词分析"),
        ("multi_category", "类目分析"),
        ("brand", "品牌分析"),
        ("seller", "卖家分析"),
        ("search_position", "搜索位置分析"),
    )
    for key, label in keys:
        block = analyzer_results.get(key)
        if not block:
            continue
        src_files = block.get("source_files", []) or []
        if not src_files:
            rows.append([label, "N/A", "calculated", "low"])
            continue
        for sf in src_files:
            rows.append([label, sf, "imported_excel", "high"])
    return _write_rows(ws, rows)


__all__ = [
    "NAME",
    "VERSION",
    "REPORT_SHEETS",
    "TemplateExtraction",
    "ReportBuildResult",
    "extract_templates",
    "build_market_research_report",
]
