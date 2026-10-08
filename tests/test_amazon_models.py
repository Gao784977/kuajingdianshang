"""Tests for src/modules/amazon/models.py dataclasses.

Covers V3 spec test cases:
- dataclass to_dict/from_dict round-trips
- AmazonDecimalEncoder serializes Decimal as string.
"""

from __future__ import annotations

import json
import unittest
from decimal import Decimal

from src.modules.amazon.models import (
    AgentResult,
    AmazonDecimalEncoder,
    AmazonProfitInput,
    AmazonProfitResult,
    CompetitorRow,
    KeywordOutput,
    MarketOutput,
    OpportunityOutput,
    ProductInput,
    ProductOutput,
    ReviewOutput,
    ReviewRow,
    Sourced,
)


class RoundTripTest(unittest.TestCase):
    """Case: dataclass to_dict/from_dict round-trips."""

    def _roundtrip(self, obj, cls):
        d = obj.to_dict()
        back = cls.from_dict(d)
        self.assertEqual(back.to_dict(), d)
        return back

    def test_product_input_roundtrip(self):
        self._roundtrip(ProductInput(keyword="x", marketplace="amazon_us"),
                        ProductInput)

    def test_competitor_row_roundtrip(self):
        self._roundtrip(CompetitorRow(brand="b", asin="a",
                                      product_name="p", price=Decimal("1.0"),
                                      rating=Decimal("4.0"), review_count=5),
                        CompetitorRow)

    def test_review_row_roundtrip(self):
        self._roundtrip(ReviewRow(review_id="r1", asin="a", rating=4,
                                  review_text="good"), ReviewRow)

    def test_keyword_output_roundtrip(self):
        self._roundtrip(KeywordOutput(normalized_keyword="kw"), KeywordOutput)

    def test_market_output_roundtrip(self):
        self._roundtrip(MarketOutput(marketplace="amazon_us"), MarketOutput)

    def test_opportunity_output_roundtrip(self):
        self._roundtrip(OpportunityOutput(market_opportunity=4), OpportunityOutput)

    def test_amazon_profit_input_roundtrip(self):
        self._roundtrip(
            AmazonProfitInput(selling_price=Decimal("29.99"),
                              unit_cost=Decimal("8.50")),
            AmazonProfitInput,
        )

    def test_amazon_profit_result_roundtrip(self):
        r = AmazonProfitResult(
            scenario="base", selling_price=Decimal("29.99"),
            unit_cost=Decimal("8.50"), inbound_shipping=Decimal("1.20"),
            international_shipping=Decimal("2.80"), customs_duty=Decimal("0.60"),
            fba_fee=Decimal("3.90"), referral_fee=Decimal("4.50"),
            storage_fee=Decimal("0.30"), advertising_cost=Decimal("3.00"),
            return_cost=Decimal("1.50"), other_variable_cost=Decimal("0.50"),
            fixed_development_cost=Decimal("5000.00"),
            initial_investment=Decimal("12000.00"),
            estimated_monthly_units=300,
            monthly_fixed_cost=Decimal("800.00"),
            total_variable_cost_per_unit=Decimal("26.80"),
            unit_profit=Decimal("3.19"), unit_margin=Decimal("0.1064"),
            monthly_profit=Decimal("157.00"),
            annualized_profit=Decimal("1884.00"), roi=Decimal("0.1570"),
        )
        back = self._roundtrip(r, AmazonProfitResult)
        self.assertEqual(back.scenario, "base")
        self.assertEqual(back.monthly_profit, Decimal("157.00"))

    def test_agent_result_roundtrip(self):
        r = AgentResult(agent_name="x", status="completed",
                        output=KeywordOutput(normalized_keyword="k").to_dict())
        back = self._roundtrip(r, AgentResult)
        self.assertEqual(back.agent_name, "x")

    def test_sourced_roundtrip(self):
        s = Sourced(value=Decimal("1.5"), source="mock_data", confidence="low")
        d = s.to_dict()
        self.assertEqual(d["value"], "1.5")
        back = Sourced.from_dict(d)
        self.assertEqual(back.source, "mock_data")
        self.assertEqual(back.confidence, "low")


class AmazonDecimalEncoderTest(unittest.TestCase):
    """Case: AmazonDecimalEncoder serializes Decimal as string."""

    def test_decimal_serialized_as_string(self):
        data = {"price": Decimal("29.99"), "count": 3}
        s = json.dumps(data, cls=AmazonDecimalEncoder)
        back = json.loads(s)
        self.assertEqual(back["price"], "29.99")
        self.assertEqual(back["count"], 3)

    def test_none_decimal_serialized_as_null(self):
        from src.modules.amazon.models import _decimal_to_str
        self.assertIsNone(_decimal_to_str(None))

    def test_nested_decimal(self):
        data = {"a": {"b": Decimal("1.10")}}
        s = json.dumps(data, cls=AmazonDecimalEncoder)
        self.assertIn('"1.10"', s)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
