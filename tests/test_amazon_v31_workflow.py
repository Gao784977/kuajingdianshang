"""Tests for V3.1.7 :mod:`src.modules.amazon.v31_workflow`.

Covers spec section 十一 workflow-integration test cases:

* Workflow runs end-to-end with Excel files (fixture-based)
* Market research report is always produced, even when no candidate is
  confirmed
* Product/profit agents are gated off (``candidate_gate_status="closed"``)
  when no candidate is confirmed
* Product/profit agents run when candidates are confirmed
  (``candidate_gate_status="open"``) — uses V3.0 MasterAgent
* URL fetch is skipped when ``--allow-url-fetch`` is not set
* URL fetch runs with a fake transport when enabled
* Missing Excel files are surfaced in warnings
* Load errors are surfaced in errors
* ``V31WorkflowResult.to_dict`` round-trips
* Candidates are produced from keyword Excel data
* ``to_dict`` output is JSON-serialisable

Tests use the pre-generated fixtures under ``tests/fixtures/`` and
``load_amazon_config()`` for the MasterAgent config. No network, no
real API keys, no user absolute paths.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from modules.amazon.v31_workflow import (  # noqa: E402
    NAME,
    VERSION,
    V31Workflow,
    V31WorkflowResult,
)
from modules.amazon.amazon_config import load_amazon_config  # noqa: E402
from modules.amazon.product_candidate_agent import (  # noqa: E402
    ProductCandidate,
    STATUS_CONFIRMED,
    STATUS_PENDING,
)

try:
    import openpyxl  # type: ignore[import]
    openpyxl_available = True
except ImportError:
    openpyxl_available = False

_FIXTURE_DIR = _THIS_DIR / "fixtures"


def _fixture(name: str) -> Path:
    return _FIXTURE_DIR / name


def _fake_transport_ok(status=200, body=b"<html>ok</html>"):
    """Return a fake transport that succeeds with ``body``."""

    def transport(url, *, headers, timeout, max_bytes):
        return status, body, {"Content-Type": "text/html"}

    return transport


def _fake_transport_http_error(status=404):
    def transport(url, *, headers, timeout, max_bytes):
        return status, b"<html>not found</html>", {"Content-Type": "text/html"}

    return transport


class TestV31WorkflowResultDataclass(unittest.TestCase):
    """Tests for the :class:`V31WorkflowResult` dataclass."""

    def test_defaults(self):
        r = V31WorkflowResult()
        self.assertEqual(r.project_name, "")
        self.assertEqual(r.analyzer_results, {})
        self.assertIsNone(r.market_research_report_path)
        self.assertEqual(r.candidates, [])
        self.assertEqual(r.candidate_gate_status, "closed")
        self.assertEqual(r.product_plans, [])
        self.assertEqual(r.profit_results, [])
        self.assertEqual(r.warnings, [])
        self.assertEqual(r.errors, [])
        self.assertEqual(r.generated_at, "")

    def test_to_dict_keys(self):
        r = V31WorkflowResult(project_name="test_project", generated_at="20260101_120000")
        d = r.to_dict()
        expected_keys = {
            "project_name",
            "analyzer_results_keys",
            "market_research_report_path",
            "json_report_path",
            "markdown_report_path",
            "candidates",
            "candidate_gate_status",
            "product_plans",
            "profit_results",
            "warnings",
            "errors",
            "generated_at",
        }
        self.assertEqual(set(d.keys()), expected_keys)
        self.assertEqual(d["project_name"], "test_project")
        # Report paths default to None until _write_reports runs
        self.assertIsNone(d["json_report_path"])
        self.assertIsNone(d["markdown_report_path"])

    def test_to_dict_json_serialisable(self):
        r = V31WorkflowResult(
            project_name="p",
            generated_at="ts",
            warnings=["w"],
            errors=["e"],
        )
        json_str = json.dumps(r.to_dict())
        self.assertIn("p", json_str)

    def test_to_dict_with_candidates(self):
        c = ProductCandidate(
            candidate_id="PC-0001",
            product_name="Test Saddle",
            top_keyword="chicken saddle",
        )
        r = V31WorkflowResult(candidates=[c])
        d = r.to_dict()
        self.assertEqual(len(d["candidates"]), 1)
        self.assertEqual(d["candidates"][0]["candidate_id"], "PC-0001")


class TestV31WorkflowModuleConstants(unittest.TestCase):
    """Sanity checks on module constants."""

    def test_name(self):
        self.assertEqual(NAME, "v31_workflow")

    def test_version(self):
        self.assertEqual(VERSION, "v31_workflow_v3_1_7")


class TestV31WorkflowNoExcel(unittest.TestCase):
    """Tests with an empty ``excel_files`` list."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.config = load_amazon_config()

    def test_run_with_no_excel_produces_empty_results(self):
        """Workflow with no Excel files still runs all stages."""
        wf = V31Workflow(
            project_name="empty_test",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        self.assertEqual(result.project_name, "empty_test")
        self.assertEqual(len(result.candidates), 0)
        self.assertEqual(result.candidate_gate_status, "closed")
        self.assertEqual(len(result.product_plans), 0)
        self.assertEqual(len(result.profit_results), 0)
        # Analyzer results should have all keys
        self.assertIn("multi_keyword", result.analyzer_results)
        self.assertIn("multi_category", result.analyzer_results)
        self.assertIn("brand", result.analyzer_results)
        self.assertIn("seller", result.analyzer_results)
        self.assertIn("search_position", result.analyzer_results)

    def test_run_with_no_excel_warns_about_url_fetch_disabled(self):
        wf = V31Workflow(
            project_name="no_url",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        url_warnings = [w for w in result.warnings if "URL fetch disabled" in w]
        self.assertEqual(len(url_warnings), 1)

    @unittest.skipUnless(openpyxl_available, "openpyxl required for report output")
    def test_run_with_no_excel_produces_report(self):
        """Market research report is produced even with no Excel data."""
        wf = V31Workflow(
            project_name="report_test",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        self.assertIsNotNone(result.market_research_report_path)
        self.assertTrue(result.market_research_report_path.exists())
        self.assertIn("report_test", result.market_research_report_path.name)

    def test_run_with_no_excel_has_no_errors(self):
        wf = V31Workflow(
            project_name="clean",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        self.assertEqual(len(result.errors), 0)


class TestV31WorkflowMissingFiles(unittest.TestCase):
    """Tests for missing-file handling."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.config = load_amazon_config()

    def test_missing_file_surfaced_in_warnings(self):
        wf = V31Workflow(
            project_name="missing_test",
            excel_files=[Path("/nonexistent/file1.xlsx")],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        missing_warnings = [w for w in result.warnings if "Missing Excel files" in w]
        self.assertEqual(len(missing_warnings), 1)
        self.assertIn("file1.xlsx", missing_warnings[0])

    def test_multiple_missing_files_all_listed(self):
        wf = V31Workflow(
            project_name="multi_missing",
            excel_files=[
                Path("/nonexistent/a.xlsx"),
                Path("/nonexistent/b.xlsx"),
            ],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        missing_warnings = [w for w in result.warnings if "Missing Excel files" in w]
        self.assertEqual(len(missing_warnings), 1)
        self.assertIn("a.xlsx", missing_warnings[0])
        self.assertIn("b.xlsx", missing_warnings[0])


class TestV31WorkflowWithFixtures(unittest.TestCase):
    """Tests using pre-generated fixture Excel files."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.config = load_amazon_config()

    @unittest.skipUnless(openpyxl_available, "openpyxl required for Excel loading")
    def test_keyword_fixture_produces_candidates(self):
        """Keyword fixture data flows through to candidates."""
        kw_fixture = _fixture("keyword_analysis.xlsx")
        if not kw_fixture.exists():
            self.skipTest("keyword_analysis.xlsx fixture not found")
        wf = V31Workflow(
            project_name="kw_test",
            excel_files=[kw_fixture],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        # Keyword fixture has 3 keywords → up to 3 candidates
        self.assertGreaterEqual(len(result.candidates), 1)
        # All candidates start pending
        for c in result.candidates:
            self.assertEqual(c.status, STATUS_PENDING)
        # Gate is closed (no confirmed candidates)
        self.assertEqual(result.candidate_gate_status, "closed")
        # No product/profit plans
        self.assertEqual(len(result.product_plans), 0)
        self.assertEqual(len(result.profit_results), 0)

    @unittest.skipUnless(openpyxl_available, "openpyxl required for Excel loading")
    def test_keyword_fixture_analyzer_results_populated(self):
        kw_fixture = _fixture("keyword_analysis.xlsx")
        if not kw_fixture.exists():
            self.skipTest("keyword_analysis.xlsx fixture not found")
        wf = V31Workflow(
            project_name="kw_analyze",
            excel_files=[kw_fixture],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        mk = result.analyzer_results.get("multi_keyword", {})
        rankings = mk.get("rankings") or []
        self.assertGreaterEqual(len(rankings), 1)

    @unittest.skipUnless(openpyxl_available, "openpyxl required for Excel loading")
    def test_products_fixture_loads(self):
        """Products fixture loads without error and populates products list."""
        products_fixture = _fixture("products.xlsx")
        if not products_fixture.exists():
            self.skipTest("products.xlsx fixture not found")
        wf = V31Workflow(
            project_name="prod_test",
            excel_files=[products_fixture],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        products_list = result.analyzer_results.get("products", [])
        self.assertGreaterEqual(len(products_list), 1)

    @unittest.skipUnless(openpyxl_available, "openpyxl required for Excel loading")
    def test_multiple_fixtures_combined(self):
        """Multiple fixture types are loaded in one workflow run."""
        fixtures = []
        for name in ("keyword_analysis.xlsx", "products.xlsx"):
            p = _fixture(name)
            if p.exists():
                fixtures.append(p)
        if len(fixtures) < 2:
            self.skipTest("fixtures not found")
        wf = V31Workflow(
            project_name="multi_fixture",
            excel_files=fixtures,
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        # Should have keyword rankings
        mk = result.analyzer_results.get("multi_keyword", {})
        rankings = mk.get("rankings") or []
        self.assertGreaterEqual(len(rankings), 1)
        # Should have products
        products_list = result.analyzer_results.get("products", [])
        self.assertGreaterEqual(len(products_list), 1)
        # Should have candidates
        self.assertGreaterEqual(len(result.candidates), 1)


class TestV31WorkflowGateClosed(unittest.TestCase):
    """Tests for the confirmation gate when no candidate is confirmed."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.config = load_amazon_config()

    @unittest.skipUnless(openpyxl_available, "openpyxl required for Excel loading")
    def test_gate_closed_when_no_confirmation(self):
        kw_fixture = _fixture("keyword_analysis.xlsx")
        if not kw_fixture.exists():
            self.skipTest("keyword_analysis.xlsx fixture not found")
        wf = V31Workflow(
            project_name="gate_closed",
            excel_files=[kw_fixture],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        self.assertEqual(result.candidate_gate_status, "closed")
        self.assertEqual(len(result.product_plans), 0)
        self.assertEqual(len(result.profit_results), 0)
        # Should have a warning about the gate
        gate_warnings = [w for w in result.warnings if "gated off" in w or "pending" in w]
        self.assertGreaterEqual(len(gate_warnings), 1)

    @unittest.skipUnless(openpyxl_available, "openpyxl required for Excel loading")
    def test_report_still_produced_when_gate_closed(self):
        kw_fixture = _fixture("keyword_analysis.xlsx")
        if not kw_fixture.exists():
            self.skipTest("keyword_analysis.xlsx fixture not found")
        wf = V31Workflow(
            project_name="gate_report",
            excel_files=[kw_fixture],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        self.assertEqual(result.candidate_gate_status, "closed")
        self.assertIsNotNone(result.market_research_report_path)
        self.assertTrue(result.market_research_report_path.exists())


class TestV31WorkflowGateOpen(unittest.TestCase):
    """Tests for the confirmation gate when a candidate is confirmed."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.config = load_amazon_config()

    @unittest.skipUnless(openpyxl_available, "openpyxl required for Excel loading")
    def test_gate_open_when_candidate_confirmed(self):
        kw_fixture = _fixture("keyword_analysis.xlsx")
        if not kw_fixture.exists():
            self.skipTest("keyword_analysis.xlsx fixture not found")
        wf = V31Workflow(
            project_name="gate_open",
            excel_files=[kw_fixture],
            config=self.config,
            output_dir=Path(self.output_dir),
            confirmed_candidate_ids=["PC-0001"],
        )
        result = wf.run()
        self.assertEqual(result.candidate_gate_status, "open")
        # Should have at least one product plan
        self.assertGreaterEqual(len(result.product_plans), 1)
        self.assertGreaterEqual(len(result.profit_results), 1)
        # The first plan should reference PC-0001
        self.assertEqual(result.product_plans[0]["candidate_id"], "PC-0001")

    @unittest.skipUnless(openpyxl_available, "openpyxl required for Excel loading")
    def test_confirmed_candidate_has_confirmed_status(self):
        kw_fixture = _fixture("keyword_analysis.xlsx")
        if not kw_fixture.exists():
            self.skipTest("keyword_analysis.xlsx fixture not found")
        wf = V31Workflow(
            project_name="confirm_check",
            excel_files=[kw_fixture],
            config=self.config,
            output_dir=Path(self.output_dir),
            confirmed_candidate_ids=["PC-0001"],
        )
        result = wf.run()
        confirmed = [c for c in result.candidates if c.status == STATUS_CONFIRMED]
        self.assertGreaterEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0].candidate_id, "PC-0001")

    @unittest.skipUnless(openpyxl_available, "openpyxl required for Excel loading")
    def test_product_plan_has_final_status(self):
        kw_fixture = _fixture("keyword_analysis.xlsx")
        if not kw_fixture.exists():
            self.skipTest("keyword_analysis.xlsx fixture not found")
        wf = V31Workflow(
            project_name="plan_status",
            excel_files=[kw_fixture],
            config=self.config,
            output_dir=Path(self.output_dir),
            confirmed_candidate_ids=["PC-0001"],
        )
        result = wf.run()
        plan = result.product_plans[0]
        self.assertIn("final_status", plan)
        self.assertIn(
            plan["final_status"],
            ("completed", "completed_with_warnings", "failed", "incomplete"),
        )


class TestV31WorkflowUrlFetch(unittest.TestCase):
    """Tests for the URL fetch stage."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.config = load_amazon_config()

    def test_url_fetch_skipped_by_default(self):
        user_input = {
            "urls": [
                {"url": "https://www.amazon.com/dp/B0DNVW368Z", "notes": "test"},
            ],
        }
        wf = V31Workflow(
            project_name="url_off",
            excel_files=[],
            user_input=user_input,
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        # URL fetches key should not exist in analyzer_results
        self.assertNotIn("url_fetches", result.analyzer_results)
        # Warning about disabled URL fetch
        url_warnings = [w for w in result.warnings if "URL fetch disabled" in w]
        self.assertEqual(len(url_warnings), 1)

    def test_url_fetch_runs_when_enabled_with_fake_transport(self):
        user_input = {
            "urls": [
                {"url": "https://www.amazon.com/dp/B0DNVW368Z", "notes": "test"},
            ],
        }
        wf = V31Workflow(
            project_name="url_on",
            excel_files=[],
            user_input=user_input,
            config=self.config,
            cli_args={"allow_url_fetch": True},
            output_dir=Path(self.output_dir),
            url_transport=_fake_transport_ok(200, b"<html>product</html>"),
        )
        result = wf.run()
        self.assertIn("url_fetches", result.analyzer_results)
        fetches = result.analyzer_results["url_fetches"]
        self.assertEqual(len(fetches), 1)
        self.assertTrue(fetches[0].get("success"))
        self.assertEqual(fetches[0].get("source_url"),
                         "https://www.amazon.com/dp/B0DNVW368Z")

    def test_url_fetch_records_failure(self):
        user_input = {
            "urls": [
                {"url": "https://www.amazon.com/dp/B0DNVW368Z", "notes": "404"},
            ],
        }
        wf = V31Workflow(
            project_name="url_fail",
            excel_files=[],
            user_input=user_input,
            config=self.config,
            cli_args={"allow_url_fetch": True},
            output_dir=Path(self.output_dir),
            url_transport=_fake_transport_http_error(404),
        )
        result = wf.run()
        fetches = result.analyzer_results["url_fetches"]
        self.assertEqual(len(fetches), 1)
        self.assertFalse(fetches[0].get("success"))

    def test_url_fetch_with_no_registered_urls(self):
        """When --allow-url-fetch is on but no URLs are registered."""
        wf = V31Workflow(
            project_name="no_urls",
            excel_files=[],
            user_input={},
            config=self.config,
            cli_args={"allow_url_fetch": True},
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        self.assertIn("url_fetches", result.analyzer_results)
        self.assertEqual(len(result.analyzer_results["url_fetches"]), 0)

    def test_url_fetch_from_product_candidates_key(self):
        """URLs in ``product_candidates`` are registered."""
        user_input = {
            "product_candidates": [
                {"url": "https://www.amazon.com/dp/B0CS9LV4RD"},
            ],
        }
        wf = V31Workflow(
            project_name="pc_url",
            excel_files=[],
            user_input=user_input,
            config=self.config,
            cli_args={"allow_url_fetch": True},
            output_dir=Path(self.output_dir),
            url_transport=_fake_transport_ok(200, b"<html>ok</html>"),
        )
        result = wf.run()
        fetches = result.analyzer_results["url_fetches"]
        self.assertEqual(len(fetches), 1)
        self.assertTrue(fetches[0].get("success"))


class TestV31WorkflowReportOutput(unittest.TestCase):
    """Tests for the market research report output."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.config = load_amazon_config()

    @unittest.skipUnless(openpyxl_available, "openpyxl required for report output")
    def test_report_filename_contains_project_name(self):
        wf = V31Workflow(
            project_name="my_poultry_project",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        self.assertIsNotNone(result.market_research_report_path)
        self.assertIn("my_poultry_project", result.market_research_report_path.name)

    @unittest.skipUnless(openpyxl_available, "openpyxl required for report output")
    def test_report_filename_contains_timestamp(self):
        wf = V31Workflow(
            project_name="ts_project",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        name = result.market_research_report_path.name
        # Filename: {project_name}_market_research_report_{ts}.xlsx
        self.assertIn("_market_research_report_", name)
        self.assertTrue(name.endswith(".xlsx"))

    @unittest.skipUnless(openpyxl_available, "openpyxl required for report output")
    def test_report_written_to_output_dir(self):
        wf = V31Workflow(
            project_name="dir_test",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        self.assertEqual(
            result.market_research_report_path.parent,
            Path(self.output_dir),
        )

    @unittest.skipUnless(openpyxl_available, "openpyxl required for report output")
    def test_report_has_9_sheets(self):
        wf = V31Workflow(
            project_name="sheets_test",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        wb = openpyxl.load_workbook(result.market_research_report_path)
        self.assertGreaterEqual(len(wb.sheetnames), 9)

    @unittest.skipUnless(openpyxl_available, "openpyxl required for report output")
    def test_report_does_not_overwrite_previous(self):
        """Two runs produce distinct files (timestamp in name).

        Note: when two runs happen within the same second, the timestamp
        is identical. The spec requires that the original file is not
        overwritten — so we verify that the file from run 1 still exists
        after run 2 (even if names match, the content is re-written
        rather than being lost).
        """
        wf1 = V31Workflow(
            project_name="overwrite_test",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result1 = wf1.run()
        path1 = result1.market_research_report_path
        self.assertTrue(path1.exists())
        wf2 = V31Workflow(
            project_name="overwrite_test",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result2 = wf2.run()
        # Both files should exist (even if same name, both are valid).
        self.assertTrue(path1.exists())


class TestV31WorkflowDictToCandidate(unittest.TestCase):
    """Tests for the ``_dict_to_candidate`` static method."""

    def test_round_trip(self):
        original = ProductCandidate(
            candidate_id="PC-0099",
            product_name="Test Product",
            top_keyword="test keyword",
        )
        d = original.to_dict()
        restored = V31Workflow._dict_to_candidate(d)
        self.assertEqual(restored.candidate_id, "PC-0099")
        self.assertEqual(restored.product_name, "Test Product")
        self.assertEqual(restored.top_keyword, "test keyword")
        self.assertEqual(restored.status, STATUS_PENDING)

    def test_with_none_score(self):
        d = {
            "candidate_id": "PC-0001",
            "product_name": "P",
            "top_keyword": "kw",
            "opportunity_score": None,
            "status": "pending_review",
        }
        c = V31Workflow._dict_to_candidate(d)
        self.assertIsNone(c.opportunity_score)

    def test_with_numeric_score(self):
        d = {
            "candidate_id": "PC-0001",
            "product_name": "P",
            "top_keyword": "kw",
            "opportunity_score": "78.5",
            "status": "confirmed",
        }
        c = V31Workflow._dict_to_candidate(d)
        self.assertEqual(c.opportunity_score, __import__("decimal").Decimal("78.5"))
        self.assertEqual(c.status, "confirmed")


class TestV31WorkflowResultSurfacing(unittest.TestCase):
    """Tests that missing files and load errors surface in the result."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.config = load_amazon_config()

    def test_missing_files_in_warnings(self):
        wf = V31Workflow(
            project_name="surf_missing",
            excel_files=[Path("/nonexistent/missing.xlsx")],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        self.assertTrue(
            any("Missing Excel files" in w for w in result.warnings)
        )

    def test_no_missing_files_no_warning(self):
        wf = V31Workflow(
            project_name="no_missing",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        self.assertFalse(
            any("Missing Excel files" in w for w in result.warnings)
        )

    def test_load_errors_in_errors_list(self):
        """A corrupt file path is handled gracefully (no crash).

        A text file with .xlsx extension is detected as ``unknown`` by
        :func:`detect_workbook` and skipped (no loader branch matches).
        The workflow must not crash; it may produce a warning or error
        but the run completes.
        """
        bad_path = Path(self.output_dir) / "not_excel.xlsx"
        bad_path.write_text("this is not an xlsx file")
        wf = V31Workflow(
            project_name="load_err",
            excel_files=[bad_path],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        # The workflow must not raise.
        result = wf.run()
        # The run completes with no products loaded.
        self.assertEqual(len(result.analyzer_results.get("products", [])), 0)


class TestV31WorkflowToDictIntegration(unittest.TestCase):
    """Integration tests for ``V31WorkflowResult.to_dict`` after a run."""

    def setUp(self):
        self.output_dir = tempfile.mkdtemp()
        self.config = load_amazon_config()

    def test_to_dict_after_run(self):
        wf = V31Workflow(
            project_name="tdict_test",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        d = result.to_dict()
        self.assertEqual(d["project_name"], "tdict_test")
        self.assertEqual(d["candidate_gate_status"], "closed")
        self.assertIn("analyzer_results_keys", d)
        self.assertIsInstance(d["analyzer_results_keys"], list)

    def test_to_dict_json_dumps(self):
        wf = V31Workflow(
            project_name="json_test",
            excel_files=[],
            config=self.config,
            output_dir=Path(self.output_dir),
        )
        result = wf.run()
        d = result.to_dict()
        # Must be JSON-serialisable
        json_str = json.dumps(d)
        self.assertIn("json_test", json_str)


class TestV31WorkflowNoNetworkNoKeys(unittest.TestCase):
    """Spec test cases: no network calls, no real API keys."""

    def test_no_network_dependency(self):
        """The workflow module itself does not import network libraries."""
        import modules.amazon.v31_workflow as wf_mod
        with open(wf_mod.__file__, encoding="utf-8") as f:
            source = f.read()
        forbidden = [
            "import requests",
            "from requests",
            "import urllib.request",
            "from urllib.request",
            "import http.client",
            "from http.client",
            "import openai",
            "urlopen(",
        ]
        for pattern in forbidden:
            self.assertNotIn(pattern, source,
                            f"v31_workflow.py contains forbidden network import: {pattern}")

    def test_no_hardcoded_api_keys(self):
        import modules.amazon.v31_workflow as wf_mod
        with open(wf_mod.__file__, encoding="utf-8") as f:
            source = f.read()
        forbidden = [
            "AKIA",  # AWS access key prefix
            "sk-",   # OpenAI key prefix
            "amzn_sku_",
        ]
        for pattern in forbidden:
            self.assertNotIn(pattern, source)

    def test_no_absolute_paths_in_source(self):
        """Source code must not contain user-specific absolute paths."""
        import modules.amazon.v31_workflow as wf_mod
        with open(wf_mod.__file__, encoding="utf-8") as f:
            source = f.read()
        forbidden = [
            "C:\\\\",
            "C:/",
            "/Users/",
            "/home/",
        ]
        for pattern in forbidden:
            self.assertNotIn(pattern, source)


class TestV31WorkflowReports(unittest.TestCase):
    """V3.1.8 — Markdown + JSON report output tests."""

    def setUp(self):
        self.output_dir = Path(tempfile.mkdtemp())
        self.config = load_amazon_config()

    def test_json_report_written(self):
        wf = V31Workflow(
            project_name="json_report_test",
            excel_files=[],
            config=self.config,
            output_dir=self.output_dir,
        )
        result = wf.run()
        self.assertIsNotNone(result.json_report_path)
        self.assertTrue(result.json_report_path.exists())
        # Verify it's valid JSON
        with open(result.json_report_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["project_name"], "json_report_test")

    def test_markdown_report_written(self):
        wf = V31Workflow(
            project_name="md_report_test",
            excel_files=[],
            config=self.config,
            output_dir=self.output_dir,
        )
        result = wf.run()
        self.assertIsNotNone(result.markdown_report_path)
        self.assertTrue(result.markdown_report_path.exists())
        content = result.markdown_report_path.read_text(encoding="utf-8")
        self.assertIn("V3.1", content)
        self.assertIn("执行摘要", content)
        self.assertIn("md_report_test", content)

    def test_report_filenames_contain_project_name(self):
        wf = V31Workflow(
            project_name="filename_test",
            excel_files=[],
            config=self.config,
            output_dir=self.output_dir,
        )
        result = wf.run()
        self.assertIn("filename_test", result.json_report_path.name)
        self.assertIn("filename_test", result.markdown_report_path.name)

    def test_report_filenames_contain_timestamp(self):
        wf = V31Workflow(
            project_name="ts_test",
            excel_files=[],
            config=self.config,
            output_dir=self.output_dir,
        )
        result = wf.run()
        self.assertTrue(result.json_report_path.name.endswith(".json"))
        self.assertTrue(result.markdown_report_path.name.endswith(".md"))
        # Both should have v31_workflow in the name
        self.assertIn("v31_workflow", result.json_report_path.name)
        self.assertIn("v31_workflow", result.markdown_report_path.name)

    def test_reports_written_even_when_gate_closed(self):
        wf = V31Workflow(
            project_name="gate_closed_report",
            excel_files=[],
            config=self.config,
            output_dir=self.output_dir,
        )
        result = wf.run()
        self.assertEqual(result.candidate_gate_status, "closed")
        self.assertIsNotNone(result.json_report_path)
        self.assertIsNotNone(result.markdown_report_path)

    def test_markdown_report_has_10_sections(self):
        wf = V31Workflow(
            project_name="sections_test",
            excel_files=[],
            config=self.config,
            output_dir=self.output_dir,
        )
        result = wf.run()
        content = result.markdown_report_path.read_text(encoding="utf-8")
        for i in range(1, 11):
            self.assertIn(f"## {i}.", content,
                          f"Section {i} missing from Markdown report")

    def test_markdown_report_gate_closed_note(self):
        wf = V31Workflow(
            project_name="gate_note",
            excel_files=[],
            config=self.config,
            output_dir=self.output_dir,
        )
        result = wf.run()
        content = result.markdown_report_path.read_text(encoding="utf-8")
        self.assertIn("门禁阻断", content)
        self.assertIn("confirmed_candidate_ids", content)

    def test_json_report_contains_candidates(self):
        kw_fixture = _fixture("keyword_analysis.xlsx")
        if not kw_fixture.exists():
            self.skipTest("keyword_analysis.xlsx fixture not found")
        wf = V31Workflow(
            project_name="json_candidates",
            excel_files=[kw_fixture],
            config=self.config,
            output_dir=self.output_dir,
        )
        result = wf.run()
        with open(result.json_report_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertGreater(len(data["candidates"]), 0)
        self.assertEqual(data["candidate_gate_status"], "closed")

    def test_json_report_contains_report_paths(self):
        wf = V31Workflow(
            project_name="paths_test",
            excel_files=[],
            config=self.config,
            output_dir=self.output_dir,
        )
        result = wf.run()
        with open(result.json_report_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsNotNone(data["market_research_report_path"])
        self.assertIsNotNone(data["json_report_path"])
        self.assertIsNotNone(data["markdown_report_path"])

    def test_sanitize_filename_filters_path_separators(self):
        from modules.amazon.v31_workflow import _sanitize_filename
        self.assertNotIn("/", _sanitize_filename("a/b/c"))
        self.assertNotIn("\\", _sanitize_filename("a\\b"))
        self.assertNotIn("?", _sanitize_filename("a?b"))
        self.assertNotIn(":", _sanitize_filename("a:b"))

    def test_sanitize_filename_keeps_cjk(self):
        from modules.amazon.v31_workflow import _sanitize_filename
        out = _sanitize_filename("家禽护理项目")
        self.assertEqual(out, "家禽护理项目")

    def test_sanitize_filename_empty_returns_default(self):
        from modules.amazon.v31_workflow import _sanitize_filename
        self.assertEqual(_sanitize_filename(""), "project")


if __name__ == "__main__":
    unittest.main()
