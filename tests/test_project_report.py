"""Tests for src.modules.project_report."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal

from src.modules.opportunity_scoring import score_opportunity
from src.modules.profit_calculator import calculate_profit
from src.modules.project_report import (
    build_json_payload,
    build_report_markdown,
    compute_file_sha256,
    write_reports,
)

from tests._helpers import make_opportunity


class TestProjectReport(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self.opp = make_opportunity(opportunity_id="R-001")
        self.score = score_opportunity(self.opp)
        self.profit = calculate_profit(self.opp)

    def tearDown(self) -> None:
        for name in os.listdir(self._tmpdir):
            os.remove(os.path.join(self._tmpdir, name))
        os.rmdir(self._tmpdir)

    def test_report_contains_input_hash(self) -> None:
        input_path = os.path.join(self._tmpdir, "input.csv")
        with open(input_path, "w", encoding="utf-8") as f:
            f.write("hello")
        input_hash = compute_file_sha256(input_path)
        md = build_report_markdown(
            [self.opp],
            [self.score],
            [self.profit],
            input_path=input_path,
            input_hash=input_hash,
            scoring_version="scoring_v1",
            calculation_version="calculation_v1",
            generated_at=datetime(2026, 1, 1, 0, 0, 0),
            json_relative_path="opportunity_analysis_x.json",
        )
        self.assertIn(input_hash, md)

    def test_report_contains_versions(self) -> None:
        md = build_report_markdown(
            [self.opp],
            [self.score],
            [self.profit],
            input_path="data/raw/demo.csv",
            input_hash="abc123",
            scoring_version="scoring_v1",
            calculation_version="calculation_v1",
            generated_at=datetime(2026, 1, 1, 0, 0, 0),
            json_relative_path="x.json",
        )
        self.assertIn("scoring_v1", md)
        self.assertIn("calculation_v1", md)

    def test_report_contains_summary_and_details(self) -> None:
        md = build_report_markdown(
            [self.opp],
            [self.score],
            [self.profit],
            input_path="data/raw/demo.csv",
            input_hash="abc123",
            scoring_version="scoring_v1",
            calculation_version="calculation_v1",
            generated_at=datetime(2026, 1, 1, 0, 0, 0),
            json_relative_path="x.json",
        )
        self.assertIn("R-001", md)
        self.assertIn("汇总表", md)
        self.assertIn("建议立项结论", md)
        self.assertIn("风险和假设", md)

    def test_json_payload_structure(self) -> None:
        payload = build_json_payload(
            [self.opp],
            [self.score],
            [self.profit],
            input_path="data/raw/demo.csv",
            input_hash="abc123",
            scoring_version="scoring_v1",
            calculation_version="calculation_v1",
            generated_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        self.assertIn("metadata", payload)
        self.assertIn("source", payload)
        self.assertIn("scoring", payload)
        self.assertIn("calculations", payload)
        self.assertIn("opportunities", payload)
        self.assertIn("summary", payload)
        self.assertEqual(payload["source"]["sha256"], "abc123")
        self.assertEqual(payload["scoring"]["version"], "scoring_v1")
        self.assertEqual(payload["calculations"]["version"], "calculation_v1")
        self.assertEqual(len(payload["opportunities"]), 1)

    def test_write_reports_creates_files(self) -> None:
        input_path = os.path.join(self._tmpdir, "input.csv")
        with open(input_path, "w", encoding="utf-8") as f:
            f.write("data")
        md_path, json_path = write_reports(
            opportunities=[self.opp],
            scores=[self.score],
            profits=[self.profit],
            input_path=input_path,
            input_hash=compute_file_sha256(input_path),
            output_dir=self._tmpdir,
            scoring_version="scoring_v1",
            calculation_version="calculation_v1",
        )
        self.assertTrue(os.path.exists(md_path))
        self.assertTrue(os.path.exists(json_path))
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("opportunities", data)

    def test_deterministic_summary_sorted_by_id(self) -> None:
        opp2 = make_opportunity(opportunity_id="R-002")
        opp3 = make_opportunity(opportunity_id="R-003")
        score2 = score_opportunity(opp2)
        score3 = score_opportunity(opp3)
        profit2 = calculate_profit(opp2)
        profit3 = calculate_profit(opp3)
        # Pass in reverse order; summary rows must be sorted by id.
        payload = build_json_payload(
            [opp3, opp2, self.opp],
            [score3, score2, self.score],
            [profit3, profit2, self.profit],
            input_path="x",
            input_hash="h",
            scoring_version="scoring_v1",
            calculation_version="calculation_v1",
            generated_at=datetime(2026, 1, 1, 0, 0, 0),
        )
        ids = [o["opportunity"]["opportunity_id"] for o in payload["opportunities"]]
        self.assertEqual(ids, ["R-001", "R-002", "R-003"])


if __name__ == "__main__":
    unittest.main()
