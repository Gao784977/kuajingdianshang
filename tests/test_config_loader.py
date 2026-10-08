"""Tests for src.modules.config_loader.

Covers:
- Case 1: config file loads normally
- Case 2: config file missing -> ConfigError
- Case 3: weights do not sum to 100 -> ConfigError
- Case 4: scoring_v1 and scoring_v2 both load
- Case 25: non-existent config path returns ConfigError (CLI -> non-zero)
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from pathlib import Path

from src.modules.config_loader import (
    ConfigError,
    compute_config_sha256,
    get_scenario_multipliers,
    get_sensitivity_config,
    load_config,
)

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parent.parent
    / "config"
    / "opportunity_config.json"
)


class TestConfigLoader(unittest.TestCase):
    def test_load_default_config(self) -> None:
        # Case 1: normal load
        config = load_config()
        self.assertIn("scoring_rules", config)
        self.assertIn("scenarios", config)
        self.assertEqual(config["scoring_version"], "scoring_v2")

    def test_load_explicit_path(self) -> None:
        config = load_config(str(DEFAULT_CONFIG_PATH))
        self.assertIn("scoring_rules", config)

    def test_missing_config_raises(self) -> None:
        # Case 2 & 25: missing file
        with self.assertRaises(ConfigError) as ctx:
            load_config("/no/such/config.json")
        self.assertIn("not found", str(ctx.exception))

    def test_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            bad = os.path.join(td, "bad.json")
            with open(bad, "w", encoding="utf-8") as f:
                f.write("{not valid json")
            with self.assertRaises(ConfigError) as ctx:
                load_config(bad)
        self.assertIn("not valid JSON", str(ctx.exception))

    def test_weights_not_sum_100_raises(self) -> None:
        # Case 3: weight sum != 100
        base = load_config()
        broken = copy.deepcopy(base)
        broken["scoring_rules"]["scoring_v2"]["score_weights"]["demand"] = 31
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "cfg.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(broken, f)
            with self.assertRaises(ConfigError) as ctx:
                load_config(p)
        self.assertIn("sum to", str(ctx.exception))

    def test_scoring_v1_and_v2_both_present(self) -> None:
        # Case 4: both versions load
        config = load_config()
        v1 = config["scoring_rules"]["scoring_v1"]
        v2 = config["scoring_rules"]["scoring_v2"]
        self.assertEqual(v1["payback_metric"], "gross_profit")
        self.assertEqual(v2["payback_metric"], "net_monthly_profit")

    def test_invalid_thresholds_raise(self) -> None:
        base = load_config()
        broken = copy.deepcopy(base)
        broken["scoring_rules"]["scoring_v2"]["grade_thresholds"] = {
            "A": 60, "B": 80, "C": 40, "D": 0,
        }
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "cfg.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(broken, f)
            with self.assertRaises(ConfigError):
                load_config(p)

    def test_unknown_scoring_version_raises(self) -> None:
        from src.modules.config_loader import get_scoring_rules

        config = load_config()
        with self.assertRaises(ConfigError):
            get_scoring_rules(config, "scoring_v99")

    def test_get_scenario_multipliers(self) -> None:
        config = load_config()
        base = get_scenario_multipliers(config, "base")
        self.assertEqual(base["unit_price_multiplier"], 1.0)
        opt = get_scenario_multipliers(config, "optimistic")
        self.assertGreater(opt["unit_price_multiplier"], 1.0)

    def test_unknown_scenario_raises(self) -> None:
        config = load_config()
        with self.assertRaises(ConfigError):
            get_scenario_multipliers(config, "fantasy")

    def test_sensitivity_config(self) -> None:
        config = load_config()
        sens = get_sensitivity_config(config)
        self.assertIn("unit_price", sens["parameters"])
        self.assertIn(-20, sens["range_percents"])

    def test_config_sha256_is_hex(self) -> None:
        h = compute_config_sha256()
        self.assertEqual(len(h), 64)
        int(h, 16)  # hex parse check


if __name__ == "__main__":
    unittest.main()
