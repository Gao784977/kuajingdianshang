"""Profit calculation for opportunities (calculation_v1 / v2).

Computes revenue, costs, gross profit, gross margin, net monthly profit,
annualized profit and payback months for each opportunity. All monetary
values use :class:`decimal.Decimal` and are quantized to two decimal
places; ratios are quantized to four decimal places.

v2 additions:
* ``revenue_source`` / ``input_expected_monthly_revenue`` /
  ``calculated_units_revenue`` / ``final_revenue`` make the revenue
  selection explicit and traceable.
* ``gross_payback_months`` and ``net_payback_months`` distinguish the two
  payback口径 (the v1 ``payback_months`` field is kept as a backward-
  compatible alias of ``net_payback_months``).
* ``revenue_consistency_warning`` flags when the input monthly revenue
  differs from units * unit_price by more than the configured threshold.
* ``scenario_multipliers`` allow base / optimistic / pessimistic scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional

from .csv_import import Opportunity

DEFAULT_CALCULATION_VERSION = "calculation_v1"

_TWO_PLACES = Decimal("0.01")
_FOUR_PLACES = Decimal("0.0001")


def _q2(value: Decimal) -> Decimal:
    """Quantize to two decimal places (money)."""
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    """Quantize to four decimal places (ratios)."""
    return value.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class ProfitResult:
    """Profit metrics for a single opportunity."""

    opportunity_id: str
    revenue: Decimal
    variable_cost: Decimal
    fixed_cost: Decimal
    marketing_cost: Decimal
    implementation_cost: Decimal
    total_cost: Decimal
    gross_profit: Decimal
    gross_margin: Decimal
    initial_investment: Decimal
    payback_months: Optional[Decimal]  # backward-compat alias = net_payback
    monthly_operating_cost: Decimal
    net_monthly_profit: Decimal
    annualized_profit: Decimal
    calculation_version: str
    # --- v2 fields ---
    revenue_source: str = "calculated"  # "input" or "calculated"
    input_expected_monthly_revenue: Optional[Decimal] = None
    calculated_units_revenue: Decimal = Decimal("0")
    final_revenue: Decimal = Decimal("0")
    gross_payback_months: Optional[Decimal] = None
    net_payback_months: Optional[Decimal] = None
    revenue_consistency_warning: bool = False
    scenario: str = "base"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "opportunity_id": self.opportunity_id,
            "revenue": str(self.revenue),
            "variable_cost": str(self.variable_cost),
            "fixed_cost": str(self.fixed_cost),
            "marketing_cost": str(self.marketing_cost),
            "implementation_cost": str(self.implementation_cost),
            "total_cost": str(self.total_cost),
            "gross_profit": str(self.gross_profit),
            "gross_margin": str(self.gross_margin),
            "initial_investment": str(self.initial_investment),
            "payback_months": (
                str(self.payback_months) if self.payback_months is not None else None
            ),
            "monthly_operating_cost": str(self.monthly_operating_cost),
            "net_monthly_profit": str(self.net_monthly_profit),
            "annualized_profit": str(self.annualized_profit),
            "calculation_version": self.calculation_version,
            "revenue_source": self.revenue_source,
            "input_expected_monthly_revenue": (
                str(self.input_expected_monthly_revenue)
                if self.input_expected_monthly_revenue is not None
                else None
            ),
            "calculated_units_revenue": str(self.calculated_units_revenue),
            "final_revenue": str(self.final_revenue),
            "gross_payback_months": (
                str(self.gross_payback_months)
                if self.gross_payback_months is not None
                else None
            ),
            "net_payback_months": (
                str(self.net_payback_months)
                if self.net_payback_months is not None
                else None
            ),
            "revenue_consistency_warning": self.revenue_consistency_warning,
            "scenario": self.scenario,
        }


def _apply_multipliers(
    opp: Opportunity, multipliers: Optional[Dict[str, float]]
) -> Dict[str, Decimal]:
    """Return scenario-adjusted input values as Decimals."""
    if multipliers is None:
        multipliers = {}

    def mul(name: str, value: Decimal) -> Decimal:
        m = multipliers.get(name, 1.0)
        return (value * Decimal(str(m))).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)

    return {
        "estimated_units": mul("units_multiplier", opp.estimated_units),
        "unit_price": mul("unit_price_multiplier", opp.unit_price),
        "variable_cost_per_unit": mul(
            "variable_cost_multiplier", opp.variable_cost_per_unit
        ),
        "fixed_cost": mul("fixed_cost_multiplier", opp.fixed_cost),
        "marketing_cost": mul("marketing_cost_multiplier", opp.marketing_cost),
        "implementation_cost": mul(
            "implementation_cost_multiplier", opp.implementation_cost
        ),
        "operating_cost": mul(
            "operating_cost_multiplier", opp.expected_monthly_operating_cost
        ),
    }


def calculate_profit(
    opp: Opportunity,
    calculation_version: str = DEFAULT_CALCULATION_VERSION,
    scenario_multipliers: Optional[Dict[str, float]] = None,
    scenario_name: str = "base",
    revenue_consistency_threshold: Decimal = Decimal("0.10"),
) -> ProfitResult:
    """Compute all profit metrics for an opportunity.

    Args:
        opp: The opportunity record.
        calculation_version: Version label for the calculation rules.
        scenario_multipliers: Optional dict of multipliers applied to the
            input cost/price/quantity fields for scenario analysis.
        scenario_name: Name of the scenario (base/optimistic/pessimistic).
        revenue_consistency_threshold: Relative difference above which a
            revenue consistency warning is raised (default 10%).
    """
    adj = _apply_multipliers(opp, scenario_multipliers)

    estimated_units = adj["estimated_units"]
    unit_price = adj["unit_price"]
    variable_cost_per_unit = adj["variable_cost_per_unit"]
    fixed_cost = adj["fixed_cost"]
    marketing_cost = adj["marketing_cost"]
    implementation_cost = adj["implementation_cost"]
    operating_cost = adj["operating_cost"]

    calculated_units_revenue = estimated_units * unit_price
    input_revenue = opp.expected_monthly_revenue

    if input_revenue is not None:
        revenue = input_revenue
        revenue_source = "input"
    else:
        revenue = calculated_units_revenue
        revenue_source = "calculated"

    # Revenue consistency warning: both values present and differ by > threshold.
    consistency_warning = False
    if input_revenue is not None and calculated_units_revenue > 0:
        diff = abs(input_revenue - calculated_units_revenue)
        if calculated_units_revenue > 0:
            relative = diff / calculated_units_revenue
            if relative > revenue_consistency_threshold:
                consistency_warning = True

    variable_cost = estimated_units * variable_cost_per_unit
    total_cost = variable_cost + fixed_cost + marketing_cost + implementation_cost
    gross_profit = revenue - total_cost

    if revenue <= 0:
        gross_margin = Decimal("0")
    else:
        gross_margin = gross_profit / revenue

    net_monthly_profit = revenue - variable_cost - operating_cost
    annualized_profit = net_monthly_profit * Decimal("12")

    if gross_profit <= 0:
        gross_payback = None
    else:
        gross_payback = opp.initial_investment / gross_profit

    if net_monthly_profit <= 0:
        net_payback = None
    else:
        net_payback = opp.initial_investment / net_monthly_profit

    return ProfitResult(
        opportunity_id=opp.opportunity_id,
        revenue=_q2(revenue),
        variable_cost=_q2(variable_cost),
        fixed_cost=_q2(fixed_cost),
        marketing_cost=_q2(marketing_cost),
        implementation_cost=_q2(implementation_cost),
        total_cost=_q2(total_cost),
        gross_profit=_q2(gross_profit),
        gross_margin=_q4(gross_margin),
        initial_investment=_q2(opp.initial_investment),
        payback_months=_q2(net_payback) if net_payback is not None else None,
        monthly_operating_cost=_q2(operating_cost),
        net_monthly_profit=_q2(net_monthly_profit),
        annualized_profit=_q2(annualized_profit),
        calculation_version=calculation_version,
        revenue_source=revenue_source,
        input_expected_monthly_revenue=(
            _q2(input_revenue) if input_revenue is not None else None
        ),
        calculated_units_revenue=_q2(calculated_units_revenue),
        final_revenue=_q2(revenue),
        gross_payback_months=_q2(gross_payback) if gross_payback is not None else None,
        net_payback_months=_q2(net_payback) if net_payback is not None else None,
        revenue_consistency_warning=consistency_warning,
        scenario=scenario_name,
    )
