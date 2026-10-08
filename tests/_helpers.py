"""Shared test helpers for the opportunity analysis test suite."""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from src.modules.csv_import import Opportunity


def make_opportunity(
    opportunity_id: str = "T-001",
    opportunity_name: str = "测试机会",
    customer_segment: str = "中小企业",
    industry: str = "互联网",
    region: str = "华东",
    estimated_units: Decimal = Decimal("1000"),
    unit_price: Decimal = Decimal("100"),
    variable_cost_per_unit: Decimal = Decimal("30"),
    fixed_cost: Decimal = Decimal("10000"),
    marketing_cost: Decimal = Decimal("5000"),
    implementation_cost: Decimal = Decimal("5000"),
    expected_monthly_growth: Decimal = Decimal("0.10"),
    competition_level: str = "low",
    customer_need: str = "high",
    delivery_difficulty: str = "low",
    strategic_fit: str = "high",
    initial_investment: Decimal = Decimal("100000"),
    expected_monthly_operating_cost: Decimal = Decimal("20000"),
    expected_monthly_revenue: Optional[Decimal] = None,
    risk_notes: Optional[str] = None,
) -> Opportunity:
    """Build an Opportunity with sensible defaults for testing."""
    return Opportunity(
        opportunity_id=opportunity_id,
        opportunity_name=opportunity_name,
        customer_segment=customer_segment,
        industry=industry,
        region=region,
        estimated_units=estimated_units,
        unit_price=unit_price,
        variable_cost_per_unit=variable_cost_per_unit,
        fixed_cost=fixed_cost,
        marketing_cost=marketing_cost,
        implementation_cost=implementation_cost,
        expected_monthly_growth=expected_monthly_growth,
        competition_level=competition_level,
        customer_need=customer_need,
        delivery_difficulty=delivery_difficulty,
        strategic_fit=strategic_fit,
        initial_investment=initial_investment,
        expected_monthly_operating_cost=expected_monthly_operating_cost,
        expected_monthly_revenue=expected_monthly_revenue,
        risk_notes=risk_notes,
    )


# A single valid CSV data row (matching the template header) for import tests.
VALID_CSV_ROW = (
    "T-001,测试机会,中小企业,互联网,华东,1000,100,30,10000,5000,5000,"
    "0.10,low,high,low,high,100000,20000,,测试风险"
)

CSV_HEADER = (
    "opportunity_id,opportunity_name,customer_segment,industry,region,"
    "estimated_units,unit_price,variable_cost_per_unit,fixed_cost,marketing_cost,"
    "implementation_cost,expected_monthly_growth,competition_level,customer_need,"
    "delivery_difficulty,strategic_fit,initial_investment,"
    "expected_monthly_operating_cost,expected_monthly_revenue,risk_notes"
)


def write_csv(path: str, rows: list[str], header: str = CSV_HEADER) -> None:
    """Write a CSV file with the given header and data rows."""
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(header + "\n")
        for row in rows:
            f.write(row + "\n")
