"""Tests for V3.1.4 :mod:`src.modules.amazon.template_builder`.

Covers (per spec section 十一):

* 模板示例清除 — example business data cleared
* 图片删除 — images stripped
* 样式保留 — cell styles preserved
* 公式保留 — non-DISPIMG formulas preserved
* Sheet 名称保留 — sheet names unchanged
* 报告生成 — :func:`build_market_research_report` produces 9 sheets
* DISPIMG 公式清除 — image-placeholder formulas removed
* 填表说明行保留 — instruction rows kept
* 原模板不被修改 — source file content hash unchanged
* 项目名出现在输出文件名 — project_name in filename
* 模板缺失时仍可生成报告 — fallback when template missing

Tests never touch the user-provided attachment path; each test
builds a synthetic reference workbook with openpyxl that mirrors the
家禽护理-市调.xlsx structure (3 sheets, merges, images, DISPIMG
formulas, business data, instruction rows).
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

# Make ``src`` importable when run from the project root.
_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from modules.amazon.template_builder import (  # noqa: E402
    NAME,
    REPORT_SHEETS,
    VERSION,
    ReportBuildResult,
    TemplateExtraction,
    build_market_research_report,
    extract_templates,
    _is_dispimg_formula,
    _row_is_instruction,
    _strip_category_sheet,
    _strip_market_data_sheet,
)


def _import_openpyxl():
    """Lazy import of openpyxl shared by tests."""
    try:
        import openpyxl

        from openpyxl.styles import Alignment, Font, PatternFill

        return openpyxl, Font, PatternFill, Alignment
    except ImportError:
        return None


def _sha256(path: Path) -> str:
    """File-level SHA-256 to detect whether the source was modified."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _build_reference_workbook(path: Path) -> None:
    """Build a synthetic reference xlsx mirroring 家禽护理-市调.xlsx.

    Structure:
    * Sheet "US-类目分析" (A1:B12) — section titles + DISPIMG + text
    * Sheet "市场分析" (A1:E8)   — two-row header + data + 填写 row
    * Sheet "产品信息" (A1:E8)   — two-row header + data + 填写 row

    The workbook includes:
    * Merged cells (section headers in sheet 1)
    * Cell styles (bold font, fill) on header rows
    * A non-DISPIMG formula (=SUM(C1:C3)) to verify formula retention
    * DISPIMG image-placeholder formulas
    * Real openpyxl Image objects (1x1 png) to verify image stripping
    * Business data rows to verify example clearing
    * Instruction rows (填写...) to verify retention
    """
    openpyxl, Font, PatternFill, Alignment = _import_openpyxl()
    wb = openpyxl.Workbook()
    # Remove the default sheet.
    if wb.active is not None:
        wb.remove(wb.active)

    # ----- Sheet 1: US-类目分析 -----
    ws1 = wb.create_sheet("US-类目分析")
    title_font = Font(bold=True, size=14)
    header_fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")
    ws1["A1"] = "US-类目分析"
    ws1["A1"].font = title_font
    ws1.merge_cells("A1:B1")
    ws1["A2"] = "亚马逊一二三（四）级类目："
    ws1.merge_cells("A2:B2")
    ws1["A4"] = "一、市场规模与概况（分析最小级类目）"
    ws1.merge_cells("A4:B4")
    # DISPIMG image placeholder formula (would normally embed an image)
    ws1["A5"] = '=_xlfn.DISPIMG("ID_FAKE_IMAGE_1",1)'
    # Long analysis text (>50 chars) — should be cleared
    ws1["B5"] = "增长趋势：类目具备明显年度淡旺季循环，每年 2–5 月销量与销售额快速冲高，6–12 月回落。" * 1
    ws1["A6"] = "二、市场趋势/流量周期"
    ws1.merge_cells("A6:B6")
    ws1["A7"] = '=_xlfn.DISPIMG("ID_FAKE_IMAGE_2",1)'
    ws1["B7"] = "鸡舍主词搜索量远高于配套词，全类目每年 2–4 月迎来搜索高峰，呈稳定年周期波动。"
    # A non-DISPIMG formula to verify formula retention
    ws1["A10"] = "=SUM(B5:B7)"
    # Short title to verify it stays
    ws1["A12"] = "短标题"
    ws1.column_dimensions["A"].width = 30
    ws1.column_dimensions["B"].width = 50
    ws1.row_dimensions[1].height = 22

    # ----- Sheet 2: 市场分析 -----
    ws2 = wb.create_sheet("市场分析")
    ws2["A1"] = "亚马逊品类"
    ws2["B1"] = "产品详情"
    ws2.merge_cells("B1:E1")
    ws2["A2"] = "亚马逊品类"
    ws2["B2"] = "产品名称"
    ws2["C2"] = "产品图片"
    ws2["D2"] = "竞品售价（USD）"
    ws2["E2"] = "月销量"
    for col in ("A", "B", "C", "D", "E"):
        ws2[f"{col}1"].font = Font(bold=True)
        ws2[f"{col}1"].fill = header_fill
        ws2[f"{col}2"].font = Font(bold=True)
    # Business data row 3 (example data — should be cleared)
    ws2["A3"] = "Patio, Lawn & Garden"
    ws2["B3"] = "示例产品名称 ABC"
    ws2["C3"] = '=_xlfn.DISPIMG("ID_FAKE_IMG_P",1)'
    ws2["D3"] = 22.84
    ws2["E3"] = 100
    # Business data row 4 (example data — should be cleared)
    ws2["A4"] = "Home & Kitchen"
    ws2["B4"] = "另一个示例"
    ws2["D4"] = 19.99
    ws2["E4"] = 50
    # Instruction row 5 (填写说明 — should be kept)
    ws2["A5"] = "填写品类，与项目组类目保持一致"
    ws2["B5"] = "填写产品名称"
    ws2["C5"] = "黏贴图片，嵌入单元格"
    ws2["D5"] = "填写竞品售价"
    ws2["E5"] = "填写月销量"
    # An ordinary formula to verify formula retention in the kept row
    ws2["F5"] = "=SUM(D3:D4)"
    ws2.column_dimensions["A"].width = 25

    # ----- Sheet 3: 产品信息 -----
    ws3 = wb.create_sheet("产品信息")
    ws3["A1"] = "基础信息"
    ws3["B1"] = "产品标题"
    ws3.merge_cells("A1:A1")  # no-op but exercises merge API
    ws3["A2"] = "产品品类"
    ws3["B2"] = "SPU/SKU"
    ws3["C2"] = "标题"
    ws3["D2"] = "图片"
    ws3["E2"] = "采购单价"
    for col in ("A", "B", "C", "D", "E"):
        ws3[f"{col}1"].font = Font(bold=True)
        ws3[f"{col}2"].font = Font(bold=True)
    # Business data row 3 (example — should be cleared)
    ws3["A3"] = "Patio, Lawn & Garden"
    ws3["B3"] = "PPG_FAKE_SKU"
    ws3["C3"] = "示例标题 XYZ"
    ws3["D3"] = '=_xlfn.DISPIMG("ID_FAKE_PROD_IMG",1)'
    ws3["E3"] = 21.5
    # Instruction row 4 (填写 — should be kept)
    ws3["A4"] = "填写品类"
    ws3["B4"] = "填写 SPU/SKU"
    ws3["C4"] = "填写标题"
    ws3["D4"] = "填入产品图片"
    ws3["E4"] = "填写采购单价"

    # Try to attach a real Image so _images is non-empty (some
    # openpyxl versions need a bytes payload). Use a 1x1 PNG if
    # available; skip otherwise — the DISPIMG formula tests still
    # cover the "image placeholder removed" case.
    try:
        from openpyxl.drawing.image import Image as XlImage

        # Minimal 1x1 transparent PNG (67 bytes).
        png_bytes = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
            "890000000d49444154789c636000000000020001e221bc330000000049454e44ae426082"
        )
        import io

        img = XlImage(io.BytesIO(png_bytes))
        ws1.add_image(img, "A5")
        img2 = XlImage(io.BytesIO(png_bytes))
        ws2.add_image(img2, "C3")
    except Exception:
        # Image attach is best-effort; tests below still verify
        # DISPIMG formula removal which is the primary image channel.
        pass

    wb.save(str(path))


class TestDispimgDetection(unittest.TestCase):
    """Unit tests for the DISPIMG formula detector."""

    def test_recognises_dispimg(self):
        self.assertTrue(_is_dispimg_formula('=_xlfn.DISPIMG("ID_X",1)'))

    def test_recognises_dispimg_lowercase(self):
        self.assertTrue(_is_dispimg_formula("=dispimg(id_x)"))

    def test_rejects_normal_formula(self):
        self.assertFalse(_is_dispimg_formula("=SUM(A1:A3)"))

    def test_rejects_plain_text(self):
        self.assertFalse(_is_dispimg_formula("hello world"))

    def test_none_is_not_dispimg(self):
        self.assertFalse(_is_dispimg_formula(None))

    def test_empty_string_is_not_dispimg(self):
        self.assertFalse(_is_dispimg_formula(""))


class TestRowIsInstruction(unittest.TestCase):
    """Tests for the 填表说明 row heuristic."""

    def setUp(self):
        self.openpyxl = _import_openpyxl()
        if self.openpyxl is None:
            self.skipTest("openpyxl not installed")
        openpyxl = self.openpyxl[0]
        self.wb = openpyxl.Workbook()
        self.ws = self.wb.active

    def test_instruction_row_detected(self):
        self.ws["A1"] = "填写品类"
        self.ws["B1"] = "填写 SPU"
        self.ws["C1"] = "填写标题"
        self.assertTrue(_row_is_instruction(self.ws, 1, 3))

    def test_data_row_not_instruction(self):
        self.ws["A1"] = "Patio"
        self.ws["B1"] = "SKU123"
        self.ws["C1"] = "Title"
        self.assertFalse(_row_is_instruction(self.ws, 1, 3))

    def test_empty_row_not_instruction(self):
        self.assertFalse(_row_is_instruction(self.ws, 1, 3))

    def test_mixed_row_not_instruction(self):
        # Only 1 of 5 cells starts with 填写 → not an instruction row.
        self.ws["A1"] = "填写"
        self.ws["B1"] = "data"
        self.ws["C1"] = "data"
        self.ws["D1"] = "data"
        self.ws["E1"] = "data"
        self.assertFalse(_row_is_instruction(self.ws, 1, 5))


class TestStripCategorySheet(unittest.TestCase):
    """Tests for the US-类目分析 sheet cleanup routine."""

    def setUp(self):
        self.openpyxl = _import_openpyxl()
        if self.openpyxl is None:
            self.skipTest("openpyxl not installed")
        openpyxl = self.openpyxl[0]
        self.wb = openpyxl.Workbook()
        self.ws = self.wb.active
        self.ws.title = "US-类目分析"
        # Build a minimal category sheet
        self.ws["A1"] = "US-类目分析"
        self.ws["A2"] = "一、市场规模与概况"
        self.ws["A3"] = '=_xlfn.DISPIMG("ID_X",1)'
        self.ws["B3"] = "增长趋势：类目具备明显年度淡旺季循环，每年 2–5 月销量与销售额快速冲高，6–12 月回落。"
        self.ws["A4"] = "短标题"

    def test_images_stripped(self):
        _strip_category_sheet(self.ws)
        self.assertEqual(len(getattr(self.ws, "_images", [])), 0)

    def test_dispimg_formula_removed(self):
        _strip_category_sheet(self.ws)
        self.assertIsNone(self.ws["A3"].value)

    def test_long_analysis_text_removed(self):
        _strip_category_sheet(self.ws)
        self.assertIsNone(self.ws["B3"].value)

    def test_short_title_kept(self):
        _strip_category_sheet(self.ws)
        self.assertEqual(self.ws["A4"].value, "短标题")

    def test_main_title_kept(self):
        _strip_category_sheet(self.ws)
        self.assertEqual(self.ws["A1"].value, "US-类目分析")

    def test_section_title_kept(self):
        _strip_category_sheet(self.ws)
        self.assertEqual(self.ws["A2"].value, "一、市场规模与概况")

    def test_normal_formula_kept(self):
        # Non-DISPIMG formulas must survive the cleanup.
        self.ws["A5"] = "=SUM(B1:B4)"
        _strip_category_sheet(self.ws)
        self.assertEqual(self.ws["A5"].value, "=SUM(B1:B4)")


class TestStripMarketDataSheet(unittest.TestCase):
    """Tests for the 市场分析 / 产品信息 cleanup routine."""

    def setUp(self):
        self.openpyxl = _import_openpyxl()
        if self.openpyxl is None:
            self.skipTest("openpyxl not installed")
        openpyxl = self.openpyxl[0]
        self.wb = openpyxl.Workbook()
        self.ws = self.wb.active
        self.ws.title = "市场分析"
        # Two-row header
        self.ws["A1"] = "亚马逊品类"
        self.ws["B1"] = "产品名称"
        self.ws["A2"] = "亚马逊品类"
        self.ws["B2"] = "产品名称"
        # Business data row 3
        self.ws["A3"] = "Patio, Lawn & Garden"
        self.ws["B3"] = "示例产品"
        self.ws["C3"] = '=_xlfn.DISPIMG("ID_P",1)'
        # Instruction row 4
        self.ws["A4"] = "填写品类"
        self.ws["B4"] = "填写产品名称"
        self.ws["C4"] = "黏贴图片"

    def test_headers_kept(self):
        _strip_market_data_sheet(self.ws)
        self.assertEqual(self.ws["A1"].value, "亚马逊品类")
        self.assertEqual(self.ws["B2"].value, "产品名称")

    def test_business_data_cleared(self):
        _strip_market_data_sheet(self.ws)
        self.assertIsNone(self.ws["A3"].value)
        self.assertIsNone(self.ws["B3"].value)

    def test_dispimg_cleared(self):
        _strip_market_data_sheet(self.ws)
        self.assertIsNone(self.ws["C3"].value)

    def test_instruction_row_kept(self):
        _strip_market_data_sheet(self.ws)
        self.assertEqual(self.ws["A4"].value, "填写品类")
        self.assertEqual(self.ws["B4"].value, "填写产品名称")
        self.assertEqual(self.ws["C4"].value, "黏贴图片")

    def test_images_stripped(self):
        _strip_market_data_sheet(self.ws)
        self.assertEqual(len(getattr(self.ws, "_images", [])), 0)


class TestExtractTemplates(unittest.TestCase):
    """End-to-end tests for :func:`extract_templates`."""

    def setUp(self):
        self.openpyxl = _import_openpyxl()
        if self.openpyxl is None:
            self.skipTest("openpyxl not installed")
        self.tmp = tempfile.TemporaryDirectory()
        self.src_dir = Path(self.tmp.name) / "src"
        self.src_dir.mkdir(parents=True, exist_ok=True)
        self.src_path = self.src_dir / "reference.xlsx"
        _build_reference_workbook(self.src_path)
        self.out_dir = Path(self.tmp.name) / "templates"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.src_hash_before = _sha256(self.src_path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_returns_two_template_paths(self):
        result = extract_templates(self.src_path, self.out_dir)
        self.assertIsInstance(result, TemplateExtraction)
        self.assertIsNotNone(result.market_research_template)
        self.assertIsNotNone(result.product_development_template)
        self.assertTrue(Path(result.market_research_template).exists())
        self.assertTrue(Path(result.product_development_template).exists())

    def test_market_template_has_two_sheets(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        self.assertEqual(wb.sheetnames, ["US-类目分析", "市场分析"])

    def test_product_template_has_one_sheet(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.product_development_template))
        self.assertEqual(wb.sheetnames, ["产品信息"])

    def test_sheet_names_preserved(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        for name in ("US-类目分析", "市场分析"):
            self.assertIn(name, wb.sheetnames)
        wb2 = openpyxl.load_workbook(str(result.product_development_template))
        self.assertIn("产品信息", wb2.sheetnames)

    def test_images_removed_in_market_template(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        for ws in wb.worksheets:
            self.assertEqual(len(getattr(ws, "_images", [])), 0)

    def test_dispimg_removed_in_market_template(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                for cell in row:
                    if cell.value is None:
                        continue
                    self.assertFalse(
                        _is_dispimg_formula(cell.value),
                        f"DISPIMG formula left in {ws.title}!{cell.coordinate}: {cell.value}",
                    )

    def test_business_data_removed_in_market_template(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        ws = wb["市场分析"]
        # Row 3 had Patio data — should be cleared
        self.assertIsNone(ws["A3"].value)
        self.assertIsNone(ws["B3"].value)
        # Row 4 had another example — should be cleared
        self.assertIsNone(ws["A4"].value)
        self.assertIsNone(ws["B4"].value)

    def test_instruction_row_kept_in_market_template(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        ws = wb["市场分析"]
        # Row 5 was the instruction row (填写 / 黏贴 ...)
        self.assertEqual(ws["A5"].value, "填写品类，与项目组类目保持一致")
        self.assertEqual(ws["B5"].value, "填写产品名称")
        self.assertEqual(ws["C5"].value, "黏贴图片，嵌入单元格")

    def test_headers_kept_in_market_template(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        ws = wb["市场分析"]
        self.assertEqual(ws["A1"].value, "亚马逊品类")
        self.assertEqual(ws["B2"].value, "产品名称")

    def test_non_dispimg_formula_preserved(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        ws_cat = wb["US-类目分析"]
        # A10 held =SUM(B5:B7) — verify it survived
        self.assertEqual(ws_cat["A10"].value, "=SUM(B5:B7)")
        ws_mkt = wb["市场分析"]
        # F5 held =SUM(D3:D4) — verify it survived
        self.assertEqual(ws_mkt["F5"].value, "=SUM(D3:D4)")

    def test_styles_preserved(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        ws = wb["市场分析"]
        # Header row 1 should still be bold (font preservation)
        self.assertTrue(ws["A1"].font.bold)
        # Fill should still be applied
        self.assertIsNotNone(ws["A1"].fill)

    def test_merged_cells_preserved(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        ws = wb["US-类目分析"]
        # A1:B1 was merged — should still be
        merged_ranges = [str(r) for r in ws.merged_cells.ranges]
        self.assertIn("A1:B1", merged_ranges)

    def test_column_widths_preserved(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        ws = wb["US-类目分析"]
        self.assertEqual(ws.column_dimensions["A"].width, 30)
        self.assertEqual(ws.column_dimensions["B"].width, 50)

    def test_row_heights_preserved(self):
        openpyxl = self.openpyxl[0]
        result = extract_templates(self.src_path, self.out_dir)
        wb = openpyxl.load_workbook(str(result.market_research_template))
        ws = wb["US-类目分析"]
        self.assertEqual(ws.row_dimensions[1].height, 22)

    def test_source_file_not_modified(self):
        extract_templates(self.src_path, self.out_dir)
        src_hash_after = _sha256(self.src_path)
        self.assertEqual(self.src_hash_before, src_hash_after)

    def test_audit_captures_before_after(self):
        result = extract_templates(self.src_path, self.out_dir)
        self.assertGreater(len(result.cleaned_sheets), 0)
        for entry in result.cleaned_sheets:
            self.assertIn("before", entry)
            self.assertIn("after", entry)
            self.assertIn("image_count", entry["before"])
            self.assertIn("dispimg_cells", entry["before"])
            # After cleanup: no images, no DISPIMG formulas
            self.assertEqual(entry["after"]["image_count"], 0)
            self.assertEqual(entry["after"]["dispimg_cells"], 0)

    def test_source_not_found_returns_error(self):
        result = extract_templates(Path("does_not_exist.xlsx"), self.out_dir)
        self.assertIsNone(result.market_research_template)
        self.assertGreater(len(result.errors), 0)


class TestBuildMarketResearchReport(unittest.TestCase):
    """Tests for :func:`build_market_research_report`."""

    def setUp(self):
        self.openpyxl = _import_openpyxl()
        if self.openpyxl is None:
            self.skipTest("openpyxl not installed")
        self.tmp = tempfile.TemporaryDirectory()
        self.out_dir = Path(self.tmp.name) / "output"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _sample_analyzer_results(self) -> dict:
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
                    }
                ],
                "total_keywords": 1,
                "total_search_volume": "9416",
                "avg_click_share": "0.18",
                "avg_conversion_share": "0.22",
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
                        "competition_rank": 2,
                        "opportunity_score": "72.0",
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
                "top4_brands": [{"brand": "PETSFIT", "share": "0.20"}],
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
                    "title": "Mother Hen Chicken Saddle",
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
                "source": "agent_inference",
                "confidence": "medium",
            },
        }

    def test_report_has_nine_sheets(self):
        result = build_market_research_report(
            "poultry_care",
            self._sample_analyzer_results(),
            None,
            self.out_dir,
        )
        self.assertIsInstance(result, ReportBuildResult)
        self.assertIsNotNone(result.output_path)
        self.assertEqual(len(result.sheets_written), 9)
        for name in REPORT_SHEETS:
            self.assertIn(name, result.sheets_written)

    def test_project_name_in_filename(self):
        result = build_market_research_report(
            "poultry_care",
            self._sample_analyzer_results(),
            None,
            self.out_dir,
        )
        filename = Path(result.output_path).name
        self.assertIn("poultry_care", filename)
        self.assertIn("market_research_report", filename)

    def test_filename_has_timestamp(self):
        import re

        result = build_market_research_report(
            "demo_proj",
            self._sample_analyzer_results(),
            None,
            self.out_dir,
        )
        filename = Path(result.output_path).name
        # Expect YYYYMMDD_HHMMSS pattern
        match = re.search(r"(\d{8}_\d{6})", filename)
        self.assertIsNotNone(match, f"timestamp missing in {filename}")

    def test_output_file_exists(self):
        result = build_market_research_report(
            "poultry_care",
            self._sample_analyzer_results(),
            None,
            self.out_dir,
        )
        self.assertTrue(Path(result.output_path).exists())

    def test_report_data_populated(self):
        openpyxl = self.openpyxl[0]
        result = build_market_research_report(
            "poultry_care",
            self._sample_analyzer_results(),
            None,
            self.out_dir,
        )
        wb = openpyxl.load_workbook(str(result.output_path))
        # Keyword sheet should have ranking data
        kw_sheet = wb[REPORT_SHEETS[2]]
        # Header row + at least one data row
        self.assertGreaterEqual(kw_sheet.max_row, 2)
        # Verify a value from the sample data appears
        found = False
        for row in kw_sheet.iter_rows(values_only=True):
            for cell in row:
                if cell == "chicken saddle":
                    found = True
                    break
            if found:
                break
        self.assertTrue(found, "keyword data not written to report")

    def test_competitor_detail_sheet_has_product(self):
        openpyxl = self.openpyxl[0]
        result = build_market_research_report(
            "poultry_care",
            self._sample_analyzer_results(),
            None,
            self.out_dir,
        )
        wb = openpyxl.load_workbook(str(result.output_path))
        ws = wb[REPORT_SHEETS[3]]
        found = False
        for row in ws.iter_rows(values_only=True):
            for cell in row:
                if cell == "B0DNVW368Z":
                    found = True
                    break
            if found:
                break
        self.assertTrue(found, "product ASIN not written to competitor sheet")

    def test_data_quality_sheet_has_entries(self):
        openpyxl = self.openpyxl[0]
        result = build_market_research_report(
            "poultry_care",
            self._sample_analyzer_results(),
            None,
            self.out_dir,
        )
        wb = openpyxl.load_workbook(str(result.output_path))
        ws = wb[REPORT_SHEETS[7]]
        # Header + 5 analyzer rows
        self.assertGreaterEqual(ws.max_row, 6)

    def test_source_traceability_sheet_has_entries(self):
        openpyxl = self.openpyxl[0]
        result = build_market_research_report(
            "poultry_care",
            self._sample_analyzer_results(),
            None,
            self.out_dir,
        )
        wb = openpyxl.load_workbook(str(result.output_path))
        ws = wb[REPORT_SHEETS[8]]
        # Header + at least one source file row
        self.assertGreaterEqual(ws.max_row, 2)

    def test_empty_analyzer_results_still_produces_report(self):
        result = build_market_research_report(
            "empty_proj",
            {},
            None,
            self.out_dir,
        )
        self.assertIsNotNone(result.output_path)
        self.assertEqual(len(result.sheets_written), 9)
        # Every sheet should still exist (with "no data" placeholder)
        openpyxl = self.openpyxl[0]
        wb = openpyxl.load_workbook(str(result.output_path))
        for name in REPORT_SHEETS:
            self.assertIn(name, wb.sheetnames)

    def test_report_with_template_preserves_template_sheets(self):
        # Build a template first
        src_dir = Path(self.tmp.name) / "src2"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_path = src_dir / "reference.xlsx"
        _build_reference_workbook(src_path)
        tpl_dir = Path(self.tmp.name) / "tpl"
        tpl_dir.mkdir(parents=True, exist_ok=True)
        ext = extract_templates(src_path, tpl_dir)
        self.assertIsNotNone(ext.market_research_template)

        # Now build a report from the template
        result = build_market_research_report(
            "poultry_care",
            self._sample_analyzer_results(),
            ext.market_research_template,
            self.out_dir,
        )
        self.assertIsNotNone(result.output_path)
        openpyxl = self.openpyxl[0]
        wb = openpyxl.load_workbook(str(result.output_path))
        # Template sheets (US-类目分析 + 市场分析) must still be present
        self.assertIn("US-类目分析", wb.sheetnames)
        self.assertIn("市场分析", wb.sheetnames)
        # And all 9 report sheets must also be present
        for name in REPORT_SHEETS:
            self.assertIn(name, wb.sheetnames)

    def test_template_not_modified_when_building_report(self):
        src_dir = Path(self.tmp.name) / "src3"
        src_dir.mkdir(parents=True, exist_ok=True)
        src_path = src_dir / "reference.xlsx"
        _build_reference_workbook(src_path)
        tpl_dir = Path(self.tmp.name) / "tpl3"
        tpl_dir.mkdir(parents=True, exist_ok=True)
        ext = extract_templates(src_path, tpl_dir)
        tpl_hash_before = _sha256(ext.market_research_template)
        build_market_research_report(
            "poultry_care",
            self._sample_analyzer_results(),
            ext.market_research_template,
            self.out_dir,
        )
        tpl_hash_after = _sha256(ext.market_research_template)
        self.assertEqual(tpl_hash_before, tpl_hash_after)

    def test_sanitises_project_name(self):
        result = build_market_research_report(
            "poultry/care?special",
            {},
            None,
            self.out_dir,
        )
        filename = Path(result.output_path).name
        # Slashes and question marks must not appear (sanitised)
        self.assertNotIn("/", filename)
        self.assertNotIn("?", filename)

    def test_empty_project_name_uses_default(self):
        result = build_market_research_report(
            "",
            {},
            None,
            self.out_dir,
        )
        filename = Path(result.output_path).name
        self.assertTrue(filename.startswith("project_"))


class TestModuleConstants(unittest.TestCase):
    """Sanity checks on module-level constants."""

    def test_name(self):
        self.assertEqual(NAME, "template_builder")

    def test_version(self):
        self.assertEqual(VERSION, "template_builder_v3_1_4")

    def test_report_sheets_count(self):
        self.assertEqual(len(REPORT_SHEETS), 9)

    def test_report_sheets_unique(self):
        self.assertEqual(len(set(REPORT_SHEETS)), 9)


if __name__ == "__main__":
    unittest.main()
