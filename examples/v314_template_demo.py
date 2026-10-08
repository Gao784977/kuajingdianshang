"""V3.1.4 demo — template extraction and report generation.

Walks through the two responsibilities of
:mod:`src.modules.amazon.template_builder`:

1. :func:`extract_templates` — turns a synthetic reference workbook
   (mirroring 家禽护理-市调.xlsx structure) into two blank templates
   under ``data/amazon/templates/``.
2. :func:`build_market_research_report` — fills a template with
   sample analyzer output to produce a 9-sheet
   ``{project_name}_market_research_report_{ts}.xlsx`` report.

Run: ``python -B examples/v314_template_demo.py``
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from modules.amazon.template_builder import (  # noqa: E402
    REPORT_SHEETS,
    build_market_research_report,
    extract_templates,
)


def _build_reference_workbook(path: Path) -> None:
    """Build a synthetic reference xlsx mirroring 家禽护理-市调.xlsx.

    Simplified compared to the test fixture but enough to demonstrate
    the cleanup logic end-to-end.
    """
    import openpyxl
    from openpyxl.drawing.image import Image as XlImage
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    if wb.active is not None:
        wb.remove(wb.active)

    # Sheet 1: US-类目分析
    ws1 = wb.create_sheet("US-类目分析")
    ws1["A1"] = "US-类目分析"
    ws1["A1"].font = Font(bold=True, size=14)
    ws1.merge_cells("A1:B1")
    ws1["A2"] = "一、市场规模与概况"
    ws1.merge_cells("A2:B2")
    ws1["A3"] = '=_xlfn.DISPIMG("ID_FAKE_1",1)'
    ws1["B3"] = "增长趋势：类目具备明显年度淡旺季循环，每年 2–5 月销量与销售额快速冲高，6–12 月回落。"
    ws1["A4"] = "二、市场趋势/流量周期"
    ws1.merge_cells("A4:B4")
    ws1["A5"] = '=_xlfn.DISPIMG("ID_FAKE_2",1)'
    ws1["B5"] = "鸡舍主词搜索量远高于配套词，全类目每年 2–4 月迎来搜索高峰，呈稳定年周期波动。"
    ws1["A6"] = "=SUM(B3:B5)"  # non-DISPIMG formula — should survive
    ws1.column_dimensions["A"].width = 30
    ws1.column_dimensions["B"].width = 50
    ws1.row_dimensions[1].height = 22

    # Sheet 2: 市场分析
    ws2 = wb.create_sheet("市场分析")
    ws2["A1"] = "亚马逊品类"
    ws2["B1"] = "产品详情"
    ws2.merge_cells("B1:E1")
    ws2["A2"] = "亚马逊品类"
    ws2["B2"] = "产品名称"
    ws2["C2"] = "产品图片"
    ws2["D2"] = "竞品售价"
    ws2["E2"] = "月销量"
    header_fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
    for col in ("A", "B", "C", "D", "E"):
        ws2[f"{col}1"].font = Font(bold=True)
        ws2[f"{col}1"].fill = header_fill
        ws2[f"{col}2"].font = Font(bold=True)
    ws2["A3"] = "Patio, Lawn & Garden"
    ws2["B3"] = "示例产品 ABC"
    ws2["C3"] = '=_xlfn.DISPIMG("ID_FAKE_P",1)'
    ws2["D3"] = 22.84
    ws2["E3"] = 100
    ws2["A4"] = "填写品类"
    ws2["B4"] = "填写产品名称"
    ws2["C4"] = "黏贴图片"
    ws2["D4"] = "填写售价"
    ws2["E4"] = "填写月销量"

    # Sheet 3: 产品信息
    ws3 = wb.create_sheet("产品信息")
    ws3["A1"] = "基础信息"
    ws3["B1"] = "产品标题"
    ws3["A2"] = "产品品类"
    ws3["B2"] = "SPU/SKU"
    ws3["C2"] = "标题"
    ws3["D2"] = "图片"
    ws3["E2"] = "采购单价"
    for col in ("A", "B", "C", "D", "E"):
        ws3[f"{col}1"].font = Font(bold=True)
        ws3[f"{col}2"].font = Font(bold=True)
    ws3["A3"] = "Patio, Lawn & Garden"
    ws3["B3"] = "PPG_FAKE"
    ws3["C3"] = "示例标题"
    ws3["D3"] = '=_xlfn.DISPIMG("ID_FAKE_PROD",1)'
    ws3["E3"] = 21.5
    ws3["A4"] = "填写品类"
    ws3["B4"] = "填写 SPU"
    ws3["C4"] = "填写标题"
    ws3["D4"] = "填入图片"
    ws3["E4"] = "填写单价"

    # Attach a real image to sheet 1 to demonstrate image stripping
    try:
        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c636000000000020001e221bc330000000049454e44ae426082"
        )
        img = XlImage(io.BytesIO(png_bytes))
        ws1.add_image(img, "A3")
    except Exception:
        pass

    wb.save(str(path))


def _sample_analyzer_results() -> dict:
    """Sample analyzer output for the report demo."""
    return {
        "multi_keyword": {
            "rankings": [
                {
                    "keyword": "chicken saddle",
                    "search_volume": "9416",
                    "search_growth": "0.05",
                    "click_share": "0.18",
                    "conversion_share": "0.22",
                    "competition": "medium",
                    "rank_by_search_volume": 1,
                    "rank_by_click_share": 1,
                    "rank_by_conversion_share": 1,
                    "opportunity_score": "78.5",
                    "source_files": ["products_export.xlsx"],
                    "requires_review": False,
                },
                {
                    "keyword": "chicken coop",
                    "search_volume": "32000",
                    "search_growth": "0.08",
                    "click_share": "0.25",
                    "conversion_share": "0.15",
                    "competition": "high",
                    "rank_by_search_volume": 1,
                    "rank_by_click_share": 1,
                    "rank_by_conversion_share": 2,
                    "opportunity_score": "65.0",
                    "source_files": ["products_export.xlsx"],
                    "requires_review": False,
                },
            ],
            "total_keywords": 2,
            "total_search_volume": "41416",
            "avg_click_share": "0.215",
            "avg_conversion_share": "0.185",
            "high_potential_keywords": [],
            "source_files": ["products_export.xlsx"],
            "requires_review": False,
        },
        "multi_category": {
            "comparisons": [
                {
                    "category": "Poultry Habitat Supplies",
                    "product_count": 50,
                    "market_sales": "1500",
                    "market_revenue": "45000",
                    "average_price": "30",
                    "median_price": "28",
                    "growth": "0.08",
                    "competition": "medium",
                    "market_capacity_rank": 1,
                    "growth_rank": 1,
                    "competition_rank": 1,
                    "opportunity_score": "82.0",
                    "source_files": ["category_export.xlsx"],
                    "requires_review": False,
                }
            ],
            "total_categories": 1,
            "total_market_revenue": "45000",
            "fastest_growing": [],
            "least_competitive": [],
            "source_files": ["category_export.xlsx"],
            "requires_review": False,
        },
        "brand": {
            "total_brands": 10,
            "cr4": "0.45",
            "cr8": "0.70",
            "hhi": "950.00",
            "market_concentration": "unconcentrated",
            "top4_brands": [
                {"brand": "PETSFIT", "share": "0.20"},
                {"brand": "Esmorah", "share": "0.15"},
                {"brand": "Umisun", "share": "0.06"},
                {"brand": "Other", "share": "0.04"},
            ],
            "top8_brands": [{"brand": "PETSFIT", "share": "0.20"}],
            "new_brand_opportunities": [],
            "share_basis": "market_share",
            "source_files": ["brand_export.xlsx"],
            "requires_review": False,
        },
        "seller": {
            "total_sellers": 8,
            "cr4": "0.50",
            "cr8": "0.80",
            "hhi": "1100.00",
            "market_concentration": "moderately_concentrated",
            "top4_sellers": [{"seller": "SellerA", "share": "0.20"}],
            "top8_sellers": [{"seller": "SellerA", "share": "0.20"}],
            "fba_count": 5,
            "fbm_count": 3,
            "unknown_fulfillment_count": 0,
            "fba_ratio": "0.6250",
            "seller_locations": {"US": 3, "CN": 5},
            "share_basis": "market_share",
            "source_files": ["seller_export.xlsx"],
            "requires_review": False,
        },
        "search_position": {
            "matrix": [
                {
                    "keyword": "chicken saddle",
                    "unique_asin_count": 5,
                    "total_appearances": 10,
                    "sponsored_count": 3,
                    "organic_count": 7,
                    "unknown_placement_count": 0,
                    "top_asins": [{"asin": "B0DNVW368Z", "appearances": 3}],
                    "source_files": ["search_export.xlsx"],
                }
            ],
            "total_appearances": 10,
            "total_sponsored": 3,
            "total_organic": 7,
            "total_unknown_placement": 0,
            "sponsored_ratio": "0.3000",
            "keyword_count": 1,
            "unique_asin_count": 5,
            "avg_asin_per_keyword": "5.0000",
            "top_keywords_by_sponsored": [],
            "top_keywords_by_organic": [],
            "source_files": ["search_export.xlsx"],
            "requires_review": False,
        },
        "products": [
            {
                "asin": "B0DNVW368Z",
                "parent_asin": "B0DNVW368Z",
                "title": "Mother Hen Chicken Saddle Protector",
                "brand": "PETSFIT",
                "seller": "PETSFIT",
                "price": "22.84",
                "monthly_sales": "100",
                "monthly_revenue": "2284",
                "rating": "4.5",
                "review_count": "446",
                "bsr_rank": "#29 in Poultry Habitat Supplies",
                "fulfillment": "FBA",
                "listing_date": "2025-01-17",
                "source_type": "imported_excel",
                "source_file": "products_export.xlsx",
                "confidence": "high",
                "requires_review": False,
            }
        ],
        "market": {
            "marketplace": "US",
            "category": "Patio, Lawn & Garden",
            "product_line": "Poultry Habitat Supplies",
            "source": "agent_inference",
            "confidence": "medium",
        },
    }


def main() -> int:
    print("=" * 70)
    print("V3.1.4 demo — template extraction + market research report")
    print("=" * 70)

    project_root = Path(__file__).resolve().parent.parent
    tmp_dir = project_root / "temp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: build a synthetic reference workbook
    ref_path = tmp_dir / "v314_reference_poultry.xlsx"
    print(f"\n[1/4] Building synthetic reference workbook: {ref_path.name}")
    _build_reference_workbook(ref_path)
    print(f"      saved {ref_path.stat().st_size} bytes")

    # Step 2: extract templates
    templates_dir = project_root / "data" / "amazon" / "templates"
    print(f"\n[2/4] Extracting templates to {templates_dir}")
    extraction = extract_templates(ref_path, templates_dir)
    print(f"      market_research_template: {extraction.market_research_template}")
    print(f"      product_development_template: {extraction.product_development_template}")
    print(f"      cleaned {len(extraction.cleaned_sheets)} sheets")
    for entry in extraction.cleaned_sheets:
        b = entry["before"]
        a = entry["after"]
        print(
            f"        - {entry['template']}/{entry['sheet']}: "
            f"images {b['image_count']}→{a['image_count']}, "
            f"DISPIMG {b['dispimg_cells']}→{a['dispimg_cells']}, "
            f"non_empty {b['non_empty_cells']}→{a['non_empty_cells']}, "
            f"merged {a['merged_count']}"
        )

    # Step 3: build a market research report from the template
    output_dir = project_root / "data" / "output"
    print(f"\n[3/4] Building market research report to {output_dir}")
    result = build_market_research_report(
        project_name="poultry_care",
        analyzer_results=_sample_analyzer_results(),
        template_path=extraction.market_research_template,
        output_dir=output_dir,
    )
    print(f"      output: {result.output_path}")
    print(f"      sheets: {len(result.sheets_written)}")
    for name in result.sheets_written:
        print(f"        - {name}")
    print(f"      rows written: {result.rows_written}")

    # Step 4: verify the report opens and has 9 sheets + 2 template sheets
    print(f"\n[4/4] Verifying report structure")
    try:
        import openpyxl

        wb = openpyxl.load_workbook(str(result.output_path))
        print(f"      total sheets: {len(wb.sheetnames)}")
        for name in wb.sheetnames:
            ws = wb[name]
            print(f"        - {name}: {ws.max_row} rows × {ws.max_column} cols")
        expected = list(REPORT_SHEETS) + ["US-类目分析", "市场分析"]
        missing = [n for n in expected if n not in wb.sheetnames]
        if missing:
            print(f"      MISSING: {missing}")
            return 1
        print("      all expected sheets present")
    except Exception as exc:
        print(f"      ERROR: {exc}")
        return 1

    print("\n" + "=" * 70)
    print("V3.1.4 demo complete.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
