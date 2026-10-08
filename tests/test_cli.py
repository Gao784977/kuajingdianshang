"""Tests for the CLI entry point src.modules.analyze_opportunities."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest

from tests._helpers import CSV_HEADER, VALID_CSV_ROW, write_csv


class TestCLI(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._input = os.path.join(self._tmpdir, "demo.csv")
        self._output_dir = os.path.join(self._tmpdir, "out")
        write_csv(self._input, [VALID_CSV_ROW])

    def tearDown(self) -> None:
        for root, _dirs, files in os.walk(self._tmpdir, topdown=False):
            for f in files:
                os.remove(os.path.join(root, f))
            os.rmdir(root)

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        cmd = [
            sys.executable,
            "-m",
            "src.modules.analyze_opportunities",
            *args,
        ]
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_cli_success(self) -> None:
        result = self._run("--input", self._input, "--output-dir", self._output_dir)
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("分析机会数量", result.stdout)
        outputs = os.listdir(self._output_dir)
        md_files = [f for f in outputs if f.endswith(".md")]
        json_files = [f for f in outputs if f.endswith(".json")]
        self.assertEqual(len(md_files), 1)
        self.assertEqual(len(json_files), 1)

    def test_cli_missing_input_returns_nonzero(self) -> None:
        missing = os.path.join(self._tmpdir, "does_not_exist.csv")
        result = self._run("--input", missing, "--output-dir", self._output_dir)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found", result.stderr.lower())

    def test_cli_invalid_csv_returns_nonzero(self) -> None:
        bad = os.path.join(self._tmpdir, "bad.csv")
        # Header missing several required fields.
        write_csv(bad, ["T-001,测试,100"], header="opportunity_id,opportunity_name,estimated_units")
        result = self._run("--input", bad, "--output-dir", self._output_dir)
        self.assertNotEqual(result.returncode, 0)

    def test_cli_help(self) -> None:
        result = self._run("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("--input", result.stdout)
        self.assertIn("--output-dir", result.stdout)


if __name__ == "__main__":
    unittest.main()
