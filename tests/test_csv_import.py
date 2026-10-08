"""Tests for src.modules.csv_import."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src.modules.csv_import import CSVImportError, load_opportunities

from tests._helpers import CSV_HEADER, VALID_CSV_ROW, write_csv


class TestCSVImport(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self) -> None:
        for name in os.listdir(self._tmpdir):
            os.remove(os.path.join(self._tmpdir, name))
        os.rmdir(self._tmpdir)

    def _path(self, name: str) -> str:
        return os.path.join(self._tmpdir, name)

    def test_normal_read(self) -> None:
        path = self._path("normal.csv")
        write_csv(path, [VALID_CSV_ROW])
        opps = load_opportunities(path)
        self.assertEqual(len(opps), 1)
        opp = opps[0]
        self.assertEqual(opp.opportunity_id, "T-001")
        self.assertEqual(opp.opportunity_name, "测试机会")
        self.assertEqual(opp.customer_need, "high")
        self.assertEqual(str(opp.estimated_units), "1000")
        self.assertIsNone(opp.expected_monthly_revenue)
        self.assertEqual(opp.risk_notes, "测试风险")

    def test_utf8_bom(self) -> None:
        path = self._path("bom.csv")
        content = "\ufeff" + CSV_HEADER + "\n" + VALID_CSV_ROW + "\n"
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        opps = load_opportunities(path)
        self.assertEqual(len(opps), 1)
        self.assertEqual(opps[0].opportunity_id, "T-001")

    def test_missing_fields(self) -> None:
        path = self._path("missing.csv")
        bad_header = "opportunity_id,opportunity_name,estimated_units"
        write_csv(path, ["T-001,测试,100"], header=bad_header)
        with self.assertRaises(CSVImportError) as ctx:
            load_opportunities(path)
        msg = str(ctx.exception)
        self.assertIn("missing required field", msg)
        # It should list several missing fields, not just one.
        self.assertIn("industry", msg)
        self.assertIn("customer_segment", msg)

    def test_duplicate_opportunity_id(self) -> None:
        path = self._path("dup.csv")
        write_csv(path, [VALID_CSV_ROW, VALID_CSV_ROW])
        with self.assertRaises(CSVImportError) as ctx:
            load_opportunities(path)
        self.assertIn("duplicate opportunity_id", str(ctx.exception))

    def test_invalid_numeric_value(self) -> None:
        path = self._path("badnum.csv")
        bad_row = VALID_CSV_ROW.replace("1000", "abc", 1)  # estimated_units
        write_csv(path, [bad_row])
        with self.assertRaises(CSVImportError) as ctx:
            load_opportunities(path)
        msg = str(ctx.exception)
        self.assertIn("estimated_units", msg)
        self.assertIn("invalid numeric value", msg)
        self.assertIn("abc", msg)

    def test_negative_numeric_value(self) -> None:
        path = self._path("neg.csv")
        bad_row = VALID_CSV_ROW.replace("10000", "-1", 1)  # fixed_cost
        write_csv(path, [bad_row])
        with self.assertRaises(CSVImportError) as ctx:
            load_opportunities(path)
        msg = str(ctx.exception)
        self.assertIn("fixed_cost", msg)
        self.assertIn("non-negative", msg)

    def test_invalid_enum_value(self) -> None:
        path = self._path("badenum.csv")
        bad_row = VALID_CSV_ROW.replace("low,high,low,high", "extreme,high,low,high", 1)
        write_csv(path, [bad_row])
        with self.assertRaises(CSVImportError) as ctx:
            load_opportunities(path)
        msg = str(ctx.exception)
        self.assertIn("competition_level", msg)
        self.assertIn("Allowed values", msg)

    def test_file_not_found(self) -> None:
        with self.assertRaises(CSVImportError) as ctx:
            load_opportunities(os.path.join(self._tmpdir, "nope.csv"))
        self.assertIn("Input file not found", str(ctx.exception))

    def test_blank_rows_skipped(self) -> None:
        path = self._path("blank.csv")
        write_csv(path, [VALID_CSV_ROW, "", "   ", VALID_CSV_ROW.replace("T-001", "T-002")])
        opps = load_opportunities(path)
        self.assertEqual(len(opps), 2)
        ids = {o.opportunity_id for o in opps}
        self.assertEqual(ids, {"T-001", "T-002"})

    def test_empty_required_text(self) -> None:
        path = self._path("emptyid.csv")
        bad_row = VALID_CSV_ROW.replace("T-001", "", 1)
        write_csv(path, [bad_row])
        with self.assertRaises(CSVImportError) as ctx:
            load_opportunities(path)
        self.assertIn("opportunity_id", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
