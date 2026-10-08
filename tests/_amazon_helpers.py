"""Shared test helpers for the V3 Amazon workflow test suite.

Mirrors the pattern of ``tests/_helpers.py`` (V1/V2): pure factory
functions returning sensible defaults so tests can override only the
fields they care about. No network, no real API keys, no absolute paths.
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from src.modules.amazon.models import (
    AmazonProfitInput,
    CompetitorRow,
    ProductInput,
    ReviewRow,
)


def make_product_input(
    keyword: str = "chicken coop door",
    marketplace: str = "amazon_us",
    target_price_min: Optional[Decimal] = Decimal("20"),
    target_price_max: Optional[Decimal] = Decimal("50"),
    direction: str = "pet/home/outdoor",
    constraints: Optional[List[str]] = None,
    notes: str = "test input",
    competitors_path: Optional[str] = None,
    reviews_path: Optional[str] = None,
) -> ProductInput:
    """Build a ProductInput with sensible defaults for testing."""
    return ProductInput(
        keyword=keyword,
        marketplace=marketplace,
        target_price_min=target_price_min,
        target_price_max=target_price_max,
        direction=direction,
        constraints=constraints if constraints is not None else ["solar", "predator proof"],
        notes=notes,
        source="user_input",
        confidence="high",
        competitors_path=competitors_path,
        reviews_path=reviews_path,
    )


def make_competitor_row(
    brand: str = "TestBrand",
    asin: str = "TEST-ASIN-001",
    product_name: str = "Test Coop Door",
    price: Decimal = Decimal("29.99"),
    rating: Decimal = Decimal("4.0"),
    review_count: int = 500,
    selling_points: str = "Solar powered; waterproof",
    negative_points: str = "Hard to install; motor noise",
    source: str = "mock_data",
) -> CompetitorRow:
    """Build a CompetitorRow with sensible defaults for testing."""
    return CompetitorRow(
        brand=brand,
        asin=asin,
        product_name=product_name,
        price=price,
        rating=rating,
        review_count=review_count,
        selling_points=selling_points,
        negative_points=negative_points,
        source=source,
    )


def make_review_row(
    review_id: str = "TEST-REV-001",
    asin: str = "TEST-ASIN-001",
    rating: int = 4,
    review_text: str = "Good product, works well.",
    review_date: str = "2026-09-01",
    source: str = "mock_data",
) -> ReviewRow:
    """Build a ReviewRow with sensible defaults for testing."""
    return ReviewRow(
        review_id=review_id,
        asin=asin,
        rating=rating,
        review_text=review_text,
        review_date=review_date,
        source=source,
    )


def make_amazon_profit_input(
    selling_price: Decimal = Decimal("29.99"),
    unit_cost: Decimal = Decimal("8.50"),
    inbound_shipping: Decimal = Decimal("1.20"),
    international_shipping: Decimal = Decimal("2.80"),
    customs_duty: Decimal = Decimal("0.60"),
    fba_fee: Decimal = Decimal("3.90"),
    referral_fee: Decimal = Decimal("4.50"),
    storage_fee: Decimal = Decimal("0.30"),
    advertising_cost: Decimal = Decimal("3.00"),
    return_cost: Decimal = Decimal("1.50"),
    other_variable_cost: Decimal = Decimal("0.50"),
    fixed_development_cost: Decimal = Decimal("5000.00"),
    initial_investment: Decimal = Decimal("12000.00"),
    estimated_monthly_units: int = 300,
    monthly_fixed_cost: Decimal = Decimal("800.00"),
) -> AmazonProfitInput:
    """Build an AmazonProfitInput matching config.profit_cost_defaults."""
    return AmazonProfitInput(
        selling_price=selling_price,
        unit_cost=unit_cost,
        inbound_shipping=inbound_shipping,
        international_shipping=international_shipping,
        customs_duty=customs_duty,
        fba_fee=fba_fee,
        referral_fee=referral_fee,
        storage_fee=storage_fee,
        advertising_cost=advertising_cost,
        return_cost=return_cost,
        other_variable_cost=other_variable_cost,
        fixed_development_cost=fixed_development_cost,
        initial_investment=initial_investment,
        estimated_monthly_units=estimated_monthly_units,
        monthly_fixed_cost=monthly_fixed_cost,
    )
