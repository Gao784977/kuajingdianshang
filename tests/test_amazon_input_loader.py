"""Tests for src/modules/amazon/input_loader.py.

Covers V3 spec test cases:
- Case 1: 用户JSON正常读取 (load_product_input succeeds on valid demo)
- Case 2: 缺少keyword raises InputLoaderError
- Case 3: 非法marketplace raises InputLoaderError
- Case 6: 竞品CSV正常读取 (load_competitors_csv on demo_competitors.csv)
- Case 7: 模拟ASIN标记正确 (MOCK vs USER tagged correctly)
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.modules.amazon.input_loader import (
    InputLoaderError,
    load_competitors_csv,
    load_product_input,
    load_reviews_csv,
)

DEMO_INPUT = "data/amazon/demo_product_input.json"
DEMO_COMPETITORS = "data/amazon/demo_competitors.csv"
DEMO_REVIEWS = "data/amazon/demo_reviews.csv"


class ProductInputLoadTest(unittest.TestCase):
    """Cases 1, 2, 3."""

    def test_case1_load_valid_demo_input(self):
        """Case 1: 用户JSON正常读取."""
        pi = load_product_input(
            DEMO_INPUT,
            supported_marketplaces=["amazon_us"],
            strict=True,
        )
        self.assertEqual(pi.keyword, "chicken coop door")
        self.assertEqual(pi.marketplace, "amazon_us")
        self.assertEqual(pi.target_price_min, 20)
        self.assertEqual(pi.target_price_max, 50)
        self.assertEqual(pi.competitors_path, DEMO_COMPETITORS)
        self.assertEqual(pi.reviews_path, DEMO_REVIEWS)

    def test_case2_missing_keyword_raises(self):
        """Case 2: 缺少keyword."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in.json"
            p.write_text(json.dumps({"marketplace": "amazon_us"}),
                         encoding="utf-8")
            with self.assertRaises(InputLoaderError) as cm:
                load_product_input(str(p),
                                   supported_marketplaces=["amazon_us"],
                                   strict=True)
            self.assertIn("keyword", str(cm.exception))

    def test_case3_invalid_marketplace_raises(self):
        """Case 3: 非法marketplace."""
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in.json"
            p.write_text(json.dumps({"keyword": "x",
                                     "marketplace": "amazon_jp"}),
                         encoding="utf-8")
            with self.assertRaises(InputLoaderError) as cm:
                load_product_input(str(p),
                                   supported_marketplaces=["amazon_us"],
                                   strict=True)
            self.assertIn("marketplace", str(cm.exception))

    def test_target_price_min_gt_max_raises(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in.json"
            p.write_text(json.dumps({"keyword": "x",
                                     "marketplace": "amazon_us",
                                     "target_price_min": 100,
                                     "target_price_max": 20}),
                         encoding="utf-8")
            with self.assertRaises(InputLoaderError):
                load_product_input(str(p),
                                   supported_marketplaces=["amazon_us"],
                                   strict=True)

    def test_missing_file_raises(self):
        with self.assertRaises(InputLoaderError):
            load_product_input("nonexistent_input.json")


class CompetitorsCsvLoadTest(unittest.TestCase):
    """Cases 6, 7."""

    def test_case6_load_demo_competitors_csv(self):
        """Case 6: 竞品CSV正常读取."""
        rows = load_competitors_csv(DEMO_COMPETITORS)
        self.assertEqual(len(rows), 4)
        from decimal import Decimal
        self.assertEqual(rows[0].brand, "PetsFit")
        self.assertEqual(rows[0].asin, "USER-ASIN-001")
        self.assertEqual(rows[0].price, Decimal("32.99"))
        self.assertEqual(rows[0].source, "imported_csv")

    def test_case7_asin_source_tags(self):
        """Case 7: USER-ASIN tagged imported_csv, MOCK-ASIN would be mock.

        The demo CSV uses USER-ASIN-* identifiers tagged imported_csv.
        Mock data uses MOCK-ASIN-* tagged mock_data (verified in
        test_amazon_mock_data).
        """
        rows = load_competitors_csv(DEMO_COMPETITORS)
        for row in rows:
            self.assertTrue(row.asin.startswith("USER-ASIN-"))
            self.assertEqual(row.source, "imported_csv")

    def test_competitors_csv_missing_file_raises(self):
        with self.assertRaises(InputLoaderError):
            load_competitors_csv("nonexistent_competitors.csv")


class ReviewsCsvLoadTest(unittest.TestCase):

    def test_load_demo_reviews_csv(self):
        rows = load_reviews_csv(DEMO_REVIEWS)
        self.assertEqual(len(rows), 12)
        self.assertTrue(rows[0].review_id.startswith("USER-REV-"))
        # Demo reviews CSV tags source imported_csv (user override).
        for row in rows:
            self.assertEqual(row.source, "imported_csv")

    def test_reviews_csv_missing_file_raises(self):
        with self.assertRaises(InputLoaderError):
            load_reviews_csv("nonexistent_reviews.csv")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
