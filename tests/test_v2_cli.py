"""V2 CLI integration tests.

Covers:
- Case 16: sorting (--sort-by)
- Case 17: portfolio summary
- Case 18: human review field validation (strict mode)
- Case 19: result CSV output
- Case 20: report contains config SHA-256
- Case 21: report contains CLI args
- Case 22: report contains data quality stats
- Case 23: old CSV (v1) still works
- Case 24: invalid review fields fail in strict mode
- Case 25: non-existent config returns non-zero exit code
"""

from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest

from tests._helpers import CSV_HEADER, VALID_CSV_ROW, write_csv

# Full v2 CSV header including the 9 optional review fields.
V2_HEADER = (
    "opportunity_id,opportunity_name,customer_segment,industry,region,"
    "estimated_units,unit_price,variable_cost_per_unit,fixed_cost,marketing_cost,"
    "implementation_cost,expected_monthly_growth,competition_level,customer_need,"
    "delivery_difficulty,strategic_fit,initial_investment,"
    "expected_monthly_operating_cost,expected_monthly_revenue,risk_notes,"
    "owner,source,validation_status,customer_validation_notes,"
    "pricing_validation_notes,cost_validation_notes,reviewer,review_status,review_notes"
)


def _v2_row(
    opp_id="T-001",
    review_status="",
    reviewer="",
    review_notes="",
    validation_status="",
):
    base = (
        f"{opp_id},测试机会,中小企业,互联网,华东,1000,100,30,10000,5000,5000,"
        f"0.10,low,high,low,high,100000,20000,,测试风险,"
        f"张三,内部,{validation_status},,,,"
        f"{reviewer},{review_status},{review_notes}"
    )
    return base


class TestV2CLI(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._output_dir = os.path.join(self._tmpdir, "out")

    def tearDown(self) -> None:
        for root, _dirs, files in os.walk(self._tmpdir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            os.rmdir(root)

    def _input(self, name="demo.csv") -> str:
        return os.path.join(self._tmpdir, name)

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        cmd = [sys.executable, "-m", "src.modules.analyze_opportunities", *args]
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_old_csv_still_works(self) -> None:
        # Case 23: v1 CSV without review fields should load fine
        path = self._input("old.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run("--input", path, "--output-dir", self._output_dir)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_invalid_scenario_returns_nonzero(self) -> None:
        path = self._input("demo.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--scenario", "fantasy"
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown scenario", result.stderr)

    def test_invalid_sort_by_returns_nonzero(self) -> None:
        path = self._input("demo.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--sort-by", "nope"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_nonexistent_config_returns_nonzero(self) -> None:
        # Case 25
        path = self._input("demo.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run(
            "--input",
            path,
            "--output-dir",
            self._output_dir,
            "--config",
            "/no/such/config.json",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr.lower())

    def test_v2_scenario_all_produces_csv(self) -> None:
        # Case 19: CSV output
        path = self._input("demo.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--scenario", "all"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        csv_files = [f for f in os.listdir(self._output_dir) if f.endswith(".csv")]
        self.assertEqual(len(csv_files), 1)
        with open(
            os.path.join(self._output_dir, csv_files[0]), encoding="utf-8-sig"
        ) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        # 1 opportunity * 3 scenarios = 3 rows
        self.assertEqual(len(rows), 3)
        scenarios = {r["scenario"] for r in rows}
        self.assertEqual(scenarios, {"base", "optimistic", "pessimistic"})
        # Required fields present
        for r in rows:
            self.assertIn("opportunity_id", r)
            self.assertIn("total_score", r)
            self.assertIn("grade", r)
            self.assertIn("human_review_required", r)

    def test_report_contains_config_sha256(self) -> None:
        # Case 20
        path = self._input("demo.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--scenario", "base"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        md_files = [f for f in os.listdir(self._output_dir) if f.endswith(".md")]
        with open(
            os.path.join(self._output_dir, md_files[0]), encoding="utf-8"
        ) as f:
            md = f.read()
        self.assertIn("配置文件 SHA-256", md)
        # Also check JSON has config snapshot sha256
        json_files = [f for f in os.listdir(self._output_dir) if f.endswith(".json")]
        with open(
            os.path.join(self._output_dir, json_files[0]), encoding="utf-8"
        ) as f:
            data = json.load(f)
        self.assertTrue(data["config_snapshot"]["sha256"])

    def test_report_contains_cli_args(self) -> None:
        # Case 21
        path = self._input("demo.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--sort-by", "profit"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        json_files = [f for f in os.listdir(self._output_dir) if f.endswith(".json")]
        with open(
            os.path.join(self._output_dir, json_files[0]), encoding="utf-8"
        ) as f:
            data = json.load(f)
        self.assertEqual(data["command"]["sort_by"], "profit")
        self.assertIn("cli_string", data["command"])

    def test_report_contains_data_quality_stats(self) -> None:
        # Case 22
        path = self._input("demo.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--scenario", "base"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        md_files = [f for f in os.listdir(self._output_dir) if f.endswith(".md")]
        with open(
            os.path.join(self._output_dir, md_files[0]), encoding="utf-8"
        ) as f:
            md = f.read()
        self.assertIn("数据质量检查", md)
        self.assertIn("error", md)
        self.assertIn("warning", md)

    def test_strict_mode_rejects_invalid_review_status(self) -> None:
        # Case 24: invalid review_status in strict mode
        path = self._input("demo.csv")
        row = _v2_row(review_status="bogus")
        write_csv(path, [row], header=V2_HEADER)
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--strict"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_strict_mode_approved_requires_reviewer(self) -> None:
        # Case 18/24: approved without reviewer fails in strict mode
        path = self._input("demo.csv")
        row = _v2_row(review_status="approved", reviewer="")
        write_csv(path, [row], header=V2_HEADER)
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--strict"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_strict_mode_rejected_requires_notes(self) -> None:
        path = self._input("demo.csv")
        row = _v2_row(review_status="rejected", review_notes="")
        write_csv(path, [row], header=V2_HEADER)
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--strict"
        )
        self.assertNotEqual(result.returncode, 0)

    def test_strict_mode_valid_review_passes(self) -> None:
        path = self._input("demo.csv")
        row = _v2_row(
            review_status="approved",
            reviewer="李四",
            review_notes="同意立项",
            validation_status="verified",
        )
        write_csv(path, [row], header=V2_HEADER)
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--strict"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_non_strict_mode_allows_invalid_review_fields(self) -> None:
        # Old / lenient mode should not fail on bad review_status
        path = self._input("demo.csv")
        row = _v2_row(review_status="bogus")
        write_csv(path, [row], header=V2_HEADER)
        result = self._run("--input", path, "--output-dir", self._output_dir)
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_sensitivity_flag_runs(self) -> None:
        path = self._input("demo.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run(
            "--input",
            path,
            "--output-dir",
            self._output_dir,
            "--scenario",
            "base",
            "--sensitivity",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        json_files = [f for f in os.listdir(self._output_dir) if f.endswith(".json")]
        with open(
            os.path.join(self._output_dir, json_files[0]), encoding="utf-8"
        ) as f:
            data = json.load(f)
        self.assertIn("sensitivity", data)
        self.assertTrue(len(data["sensitivity"]) > 0)

    def test_portfolio_summary_present(self) -> None:
        # Case 17
        path = self._input("demo.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run(
            "--input", path, "--output-dir", self._output_dir, "--scenario", "base"
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        json_files = [f for f in os.listdir(self._output_dir) if f.endswith(".json")]
        with open(
            os.path.join(self._output_dir, json_files[0]), encoding="utf-8"
        ) as f:
            data = json.load(f)
        summary = data["summary"]
        self.assertIn("total_count", summary)
        self.assertIn("total_initial_investment", summary)
        self.assertIn("total_monthly_revenue", summary)
        self.assertIn("avg_gross_margin", summary)
        self.assertIn("weighted_gross_margin", summary)
        self.assertIn("fastest_payback", summary)
        self.assertIn("highest_profit", summary)
        self.assertIn("highest_risk", summary)

    def test_sort_by_profit(self) -> None:
        # Case 16: sort by profit
        path = self._input("demo.csv")
        row2 = VALID_CSV_ROW.replace("T-001", "T-002").replace("1000,100", "500,80")
        write_csv(path, [VALID_CSV_ROW, row2])
        result = self._run(
            "--input",
            path,
            "--output-dir",
            self._output_dir,
            "--scenario",
            "base",
            "--sort-by",
            "profit",
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        json_files = [f for f in os.listdir(self._output_dir) if f.endswith(".json")]
        with open(
            os.path.join(self._output_dir, json_files[0]), encoding="utf-8"
        ) as f:
            data = json.load(f)
        rankings = data["rankings"]
        # T-001 has higher profit (1000*100) than T-002 (500*80)
        self.assertEqual(rankings[0]["opportunity_id"], "T-001")

    def test_invalid_sensitivity_parameter(self) -> None:
        path = self._input("demo.csv")
        write_csv(path, [VALID_CSV_ROW])
        result = self._run(
            "--input",
            path,
            "--output-dir",
            self._output_dir,
            "--sensitivity",
            "--sensitivity-parameters",
            "bogus_param",
        )
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
