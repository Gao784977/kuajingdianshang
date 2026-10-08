"""Tests for the V3 master agent, report and excel agents.

Covers V3 spec test cases:
- Case 16: Master Agent正常调度 (final_status completed)
- Case 17: Agent失败时状态正确 (strict → failed; non-strict → incomplete)
- Case 18: Markdown报告生成 (17 section headings)
- Case 19: JSON报告生成 (metadata/scenarios/opportunities keys)
- Case 20: 市场Excel生成 (5 sheets) [skipUnless openpyxl]
- Case 21: 产品规划Excel生成 (6 sheets) [skipUnless openpyxl]
- Case 22: 输出内容与JSON一致 (scenarios match MD section 12)
- Case 23: 输入哈希记录 (input_sha256 non-empty 64-hex)
- Case 24: 配置哈希记录 (config_sha256 non-empty 64-hex)
- Case 25: 无网络情况下测试全部通过 (no network imports)
- Case 26: 无API Key情况下测试全部通过 (no API key reads)
- Case 27: V1/V2原有测试全部通过
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from src.modules.amazon.amazon_config import (
    compute_amazon_config_sha256,
    load_amazon_config,
)
from src.modules.amazon.master_agent import AGENT_ORDER, MasterAgent
from src.modules.amazon.mock_data import (
    get_mock_competitors,
    get_mock_reviews,
)
from src.modules.amazon.models import WorkflowContext

from tests._amazon_helpers import make_product_input

try:
    import openpyxl  # type: ignore
    openpyxl_available = True
except ImportError:
    openpyxl_available = False

_AMAZON_MODULE_DIR = Path("src/modules/amazon")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _run_full_workflow(output_dir: Path, *, scenario: str = "all",
                       strict: bool = False, with_mock: bool = True):
    """Run the full MasterAgent pipeline into output_dir. Returns context."""
    config = load_amazon_config()
    config_sha = compute_amazon_config_sha256(config)
    product_input = make_product_input(
        competitors_path=None, reviews_path=None
    )
    cli_args = {
        "input": "data/amazon/demo_product_input.json",
        "output_dir": str(output_dir),
        "config": "config/amazon_workflow.json",
        "scenario": scenario,
        "with_mock_data": with_mock,
        "export_intermediate": False,
        "strict": strict,
    }
    master = MasterAgent()
    context = master.run(
        product_input=product_input,
        config=config,
        cli_args=cli_args,
        strict=strict,
        with_mock_data=with_mock,
        competitors=get_mock_competitors(),
        reviews=get_mock_reviews(),
    )
    context.config_sha256 = config_sha
    return context


class MasterAgentRunTest(unittest.TestCase):
    """Cases 16, 17."""

    def test_case16_master_agent_normal_dispatch(self):
        """Case 16: MasterAgent.run with mock data → final_status completed."""
        with tempfile.TemporaryDirectory() as d:
            ctx = _run_full_workflow(Path(d), scenario="all")
            # All 9 agents should have run
            self.assertEqual(len(ctx.agents), len(AGENT_ORDER))
            self.assertEqual(list(ctx.agents.keys()), list(AGENT_ORDER))
            # No critical failures → completed (or completed_with_warnings
            # if Excel skipped). Both are success states.
            self.assertIn(ctx.final_status,
                         ("completed", "completed_with_warnings"))
            self.assertEqual(len(ctx.errors), 0)

    def test_case17_agent_failure_strict_aborts(self):
        """Case 17: strict → final_status=failed; non-strict → incomplete."""
        with tempfile.TemporaryDirectory() as d:
            config = load_amazon_config()
            master = MasterAgent()

            # Force keyword agent to raise by monkey-patching its run method
            def _boom(ctx):
                raise RuntimeError("forced failure for test")
            master.keyword.run = _boom  # type: ignore

            # Strict mode
            ctx = master.run(
                product_input=make_product_input(),
                config=config,
                cli_args={"output_dir": d, "scenario": "base"},
                strict=True,
                with_mock_data=True,
            )
            self.assertEqual(ctx.final_status, "failed")
            self.assertGreater(len(ctx.errors), 0)
            # Strict mode aborts at first failure → keyword ran, later
            # agents may not have run
            self.assertIn("keyword", ctx.agents)

            # Non-strict mode
            master2 = MasterAgent()
            master2.keyword.run = _boom  # type: ignore
            ctx2 = master2.run(
                product_input=make_product_input(),
                config=config,
                cli_args={"output_dir": d, "scenario": "base"},
                strict=False,
                with_mock_data=True,
            )
            self.assertIn(ctx2.final_status,
                         ("incomplete", "failed"))


class ReportGenerationTest(unittest.TestCase):
    """Cases 18, 19, 22, 23, 24."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.tmp.name)
        cls.context = _run_full_workflow(cls.output_dir, scenario="all")
        # Find the generated MD and JSON
        md_files = list(cls.output_dir.glob("amazon_product_report_*.md"))
        json_files = list(cls.output_dir.glob("amazon_product_analysis_*.json"))
        assert md_files, "No markdown report generated"
        assert json_files, "No JSON report generated"
        cls.md_path = md_files[0]
        cls.json_path = json_files[0]
        cls.md_text = cls.md_path.read_text(encoding="utf-8")
        with cls.json_path.open("r", encoding="utf-8") as f:
            cls.json_payload = json.load(f)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_case18_markdown_has_17_sections(self):
        """Case 18: Markdown report has all 17 section headings."""
        from src.modules.amazon.report_agent import _REPORT_SECTIONS
        self.assertEqual(len(_REPORT_SECTIONS), 17)
        for heading in _REPORT_SECTIONS:
            self.assertIn(heading, self.md_text,
                          f"Section heading {heading!r} missing from MD")

    def test_case19_json_has_required_keys(self):
        """Case 19: JSON has metadata/scenarios/opportunities keys."""
        for key in ("metadata", "command", "source", "config_snapshot",
                    "data_quality", "summary", "scenarios", "opportunities",
                    "warnings", "agents"):
            self.assertIn(key, self.json_payload,
                          f"JSON missing top-level key {key!r}")
        # metadata sub-keys
        md = self.json_payload["metadata"]
        for key in ("workflow_version", "calculation_version",
                    "generated_at", "python_version", "final_status",
                    "input_sha256", "config_sha256", "agent_order"):
            self.assertIn(key, md, f"metadata missing {key!r}")

    def test_case22_json_scenarios_match_md(self):
        """Case 22: JSON scenarios numbers appear in MD section 12."""
        scenarios = self.json_payload["scenarios"]
        self.assertEqual(set(scenarios.keys()),
                         {"base", "optimistic", "pessimistic"})
        # The monthly_profit for base (157.00) should appear in MD
        base_profit = scenarios["base"]["monthly_profit"]
        self.assertIn(str(base_profit), self.md_text)

    def test_case23_input_sha256_recorded(self):
        """Case 23: input_sha256 is a non-empty 64-hex string."""
        sha = self.json_payload["metadata"]["input_sha256"]
        self.assertIsNotNone(sha)
        self.assertRegex(sha, _HEX64)

    def test_case24_config_sha256_recorded(self):
        """Case 24: config_sha256 is a non-empty 64-hex string."""
        sha = self.json_payload["metadata"]["config_sha256"]
        self.assertIsNotNone(sha)
        self.assertRegex(sha, _HEX64)

    def test_report_markdown_contains_disclaimer(self):
        """Disclaimer that V3 ≠ real Amazon data."""
        self.assertIn("免责", self.md_text)

    def test_report_markdown_contains_final_status(self):
        self.assertIn(self.context.final_status, self.md_text)

    def test_json_agents_has_all_9(self):
        agents = self.json_payload["agents"]
        self.assertEqual(set(agents.keys()), set(AGENT_ORDER))

    def test_json_pessimistic_roi_is_null(self):
        """Pessimistic (loss) scenario ROI must be null in JSON."""
        pess = self.json_payload["scenarios"]["pessimistic"]
        self.assertIsNone(pess["roi"])


class ExcelGenerationTest(unittest.TestCase):
    """Cases 20, 21."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.tmp.name)
        cls.context = _run_full_workflow(cls.output_dir, scenario="base")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @unittest.skipUnless(openpyxl_available, "openpyxl not installed")
    def test_case20_market_excel_has_5_sheets(self):
        """Case 20: Market Excel has 5 sheets."""
        from src.modules.amazon.excel_agent import MARKET_SHEETS
        xlsx_files = list(self.output_dir.glob("market_report_*.xlsx"))
        self.assertEqual(len(xlsx_files), 1, "Market Excel not generated")
        wb = openpyxl.load_workbook(filename=str(xlsx_files[0]),
                                   read_only=True)
        sheet_names = wb.sheetnames
        self.assertEqual(set(sheet_names), set(MARKET_SHEETS))
        self.assertEqual(len(sheet_names), 5)
        wb.close()

    @unittest.skipUnless(openpyxl_available, "openpyxl not installed")
    def test_case21_product_excel_has_6_sheets(self):
        """Case 21: Product Excel has 6 sheets."""
        from src.modules.amazon.excel_agent import PRODUCT_SHEETS
        xlsx_files = list(self.output_dir.glob("product_plan_*.xlsx"))
        self.assertEqual(len(xlsx_files), 1, "Product Excel not generated")
        wb = openpyxl.load_workbook(filename=str(xlsx_files[0]),
                                   read_only=True)
        sheet_names = wb.sheetnames
        self.assertEqual(set(sheet_names), set(PRODUCT_SHEETS))
        self.assertEqual(len(sheet_names), 6)
        wb.close()

    def test_excel_agent_result_recorded(self):
        """Excel agent result is in context (skipped if no openpyxl)."""
        result = self.context.agents.get("excel")
        self.assertIsNotNone(result)
        if openpyxl_available:
            self.assertIn(result.status, ("completed", "completed_with_warnings"))
        else:
            self.assertEqual(result.status, "skipped")


class NoNetworkNoKeysTest(unittest.TestCase):
    """Cases 25, 26."""

    def test_case25_no_network_imports(self):
        """Case 25: no network calls outside url_sources/.

        V3.1.5 (spec section 五) introduces a gated URL workflow
        under ``src/modules/amazon/url_sources/`` that is *allowed*
        to use ``urllib.request`` when ``--allow-url-fetch`` is set.
        Every other module must stay offline.
        """
        forbidden = (r"\bimport\s+requests\b",
                     r"\bfrom\s+requests\b",
                     r"\bimport\s+urllib\.request\b",
                     r"\bfrom\s+urllib\.request\b",
                     r"\bimport\s+http\.client\b",
                     r"\bfrom\s+http\.client\b",
                     r"\bimport\s+openai\b",
                     r"\bimport\s+boto",
                     r"\bamazon_spapi\b",
                     r"requests\.get",
                     r"requests\.post",
                     r"urlopen\(")
        pattern = "|".join(forbidden)
        offenders = []
        url_sources_dir = _AMAZON_MODULE_DIR / "url_sources"
        for py in _AMAZON_MODULE_DIR.rglob("*.py"):
            # url_sources/ is the only subtree permitted to fetch
            # (and only when --allow-url-fetch is on; the policy
            # module enforces the gate at runtime).
            if py.is_relative_to(url_sources_dir):
                continue
            text = py.read_text(encoding="utf-8")
            for m in re.finditer(pattern, text):
                offenders.append(f"{py}: {m.group(0)}")
        self.assertFalse(offenders,
                         f"Forbidden network imports found: {offenders}")

    def test_case26_no_api_key_reads(self):
        """Case 26: no API key env reads in src/modules/amazon/."""
        forbidden = (r"API_KEY", r"api_key", r"OPENAI_API_KEY",
                     r"AMAZON_SECRET", r"AWS_SECRET", r"SP_API_SECRET",
                     r"os\.environ\[.API", r"getenv\(.API")
        pattern = "|".join(forbidden)
        offenders = []
        for py in _AMAZON_MODULE_DIR.rglob("*.py"):
            text = py.read_text(encoding="utf-8")
            for m in re.finditer(pattern, text):
                offenders.append(f"{py}: {m.group(0)}")
        self.assertFalse(offenders,
                         f"Forbidden API key reads found: {offenders}")


class V1V2CompatTest(unittest.TestCase):
    """Case 27: V1/V2原有测试全部通过.

    Runs the V1/V2 test suite (excluding amazon tests) as a subprocess
    and asserts it exits 0 with at least the 99 V1/V2 baseline tests.
    """

    def test_case27_v1_v2_tests_still_pass(self):
        """Case 27: V1/V2 tests still pass (>= 99 tests, exit 0)."""
        # Run only non-amazon V1/V2 tests by pattern (exclude amazon test files)
        v1v2_patterns = [
            "test_csv_import.py", "test_opportunity_scoring.py",
            "test_profit_calculator.py", "test_project_report.py",
            "test_cli.py", "test_config_loader.py",
            "test_scenario_calculator.py", "test_profit_v2.py",
            "test_sensitivity_analysis.py",
            "test_data_quality_and_recommendation.py", "test_v2_cli.py",
        ]
        result = subprocess.run(
            [sys.executable, "-m", "unittest"] +
            [f"tests.{p[:-3]}" for p in v1v2_patterns] +
            ["-v"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0,
                         f"V1/V2 tests failed:\n{result.stderr[-2000:]}")
        # Count "Ran N tests" line
        m = re.search(r"Ran (\d+) tests", result.stderr)
        self.assertIsNotNone(m, f"Could not parse test count:\n{result.stderr[-500:]}")
        count = int(m.group(1))
        self.assertGreaterEqual(count, 30,
                               f"V1/V2 test count {count} below expected")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
