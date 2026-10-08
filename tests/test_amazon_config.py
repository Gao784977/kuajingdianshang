"""Tests for src/modules/amazon/amazon_config.py.

Covers V3 spec test cases:
- Config load OK; SHA-256 deterministic; score_rules sum=100 enforced;
  missing/malformed config raises AmazonConfigError with named field.

Cases tracked (spec section 18): config validation behaviour.
"""

from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from src.modules.amazon.amazon_config import (
    AmazonConfigError,
    _AMAZON_MULTIPLIER_KEYS,
    compute_amazon_config_sha256,
    load_amazon_config,
)

DEFAULT_CONFIG_PATH = "config/amazon_workflow.json"


class AmazonConfigLoadTest(unittest.TestCase):
    """Case: config file normal load."""

    def test_load_default_config_succeeds(self):
        config = load_amazon_config()
        self.assertEqual(config["workflow_version"], "amazon_workflow_v1")
        self.assertEqual(config["calculation_version"], "amazon_calculation_v1")
        self.assertIn("amazon_us", config["supported_marketplaces"])

    def test_score_rules_sum_to_100(self):
        config = load_amazon_config()
        total = sum(config["score_rules"].values())
        self.assertEqual(total, 100)

    def test_scenario_multiplier_keys_match_constant(self):
        config = load_amazon_config()
        for name in ("base", "optimistic", "pessimistic"):
            self.assertEqual(
                set(config["scenarios"][name].keys()),
                set(_AMAZON_MULTIPLIER_KEYS),
            )

    def test_config_sha256_deterministic(self):
        c1 = load_amazon_config()
        c2 = load_amazon_config()
        self.assertEqual(compute_amazon_config_sha256(c1),
                         compute_amazon_config_sha256(c2))
        self.assertEqual(len(compute_amazon_config_sha256(c1)), 64)


class AmazonConfigErrorTest(unittest.TestCase):
    """Cases: missing file, malformed JSON, bad fields."""

    def test_missing_config_file_raises(self):
        with self.assertRaises(AmazonConfigError) as cm:
            load_amazon_config("nonexistent_config_xyz.json")
        self.assertIn("not found", str(cm.exception))

    def test_malformed_json_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.json"
            p.write_text("{not valid json", encoding="utf-8")
            with self.assertRaises(AmazonConfigError) as cm:
                load_amazon_config(str(p))
            self.assertIn("not valid JSON", str(cm.exception))

    def test_weights_not_100_raises_with_field(self):
        config = load_amazon_config()
        bad = copy.deepcopy(config)
        bad["score_rules"]["market_opportunity"] = 10  # total now 80
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad_weights.json"
            p.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(AmazonConfigError) as cm:
                load_amazon_config(str(p))
            self.assertIn("score_rules", str(cm.exception))
            self.assertIn("100", str(cm.exception))

    def test_unknown_scenario_multiplier_raises(self):
        config = load_amazon_config()
        bad = copy.deepcopy(config)
        bad["scenarios"]["base"]["typo_multiplier"] = 1.0
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad_mult.json"
            p.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(AmazonConfigError) as cm:
                load_amazon_config(str(p))
            self.assertIn("unknown multiplier", str(cm.exception).lower())

    def test_mock_data_confidence_high_rejected(self):
        config = load_amazon_config()
        bad = copy.deepcopy(config)
        bad["confidence_rules"]["mock_data"] = "high"
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad_conf.json"
            p.write_text(json.dumps(bad), encoding="utf-8")
            with self.assertRaises(AmazonConfigError) as cm:
                load_amazon_config(str(p))
            self.assertIn("mock_data", str(cm.exception))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
