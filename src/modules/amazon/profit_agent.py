"""Amazon profit calculation kernel for the V3 workflow.

Owns :func:`calculate_amazon_profit` which applies the 9 Amazon-specific
scenario multipliers (defined in :data:`_AMAZON_MULTIPLIER_KEYS`) to the
13 cost fields and derives unit profit, unit margin, monthly profit,
annualized profit and ROI.

Lineage note: the ``_q2`` / ``_q4`` Decimal quantization helpers are
replicated from :mod:`src.modules.profit_calculator` (V1/V2 lines 34-41).
They are 2-line helpers kept private there; we replicate rather than
import to honour the V3 constraint of not modifying or depending on
V1/V2 internals. The lineage is documented for auditability.

Formulas (V3 spec section 12)::

    revenue_per_unit            = selling_price
    total_variable_cost_per_unit = unit_cost + inbound_shipping
                                   + international_shipping + customs_duty
                                   + fba_fee + referral_fee + storage_fee
                                   + advertising_cost + return_cost
                                   + other_variable_cost
    unit_profit                 = selling_price - total_variable_cost_per_unit
    unit_margin                 = unit_profit / selling_price    (None if <=0)
    monthly_profit              = unit_profit * estimated_monthly_units
                                   - monthly_fixed_cost
    annualized_profit           = monthly_profit * 12
    roi                         = annualized_profit / initial_investment
                                   (None if initial_investment <= 0
                                    or monthly_profit <= 0 — loss scenario)

The 9 multipliers map to: selling_price, units, unit_cost, fba_fee,
referral_fee, storage_fee, advertising_cost, return_cost,
fixed_development_cost. Fields without multipliers (inbound_shipping,
international_shipping, customs_duty, other_variable_cost,
monthly_fixed_cost, initial_investment) stay at their base values.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict, List, Optional

from .amazon_config import _AMAZON_MULTIPLIER_KEYS
from .models import (
    AmazonProfitInput,
    AmazonProfitResult,
    AgentResult,
    WorkflowContext,
)

# Calculation version (mirrors config calculation_version).
_CALCULATION_VERSION = "amazon_calculation_v1"

# Decimal quantization helpers — replicated from V1/V2
# profit_calculator.py:34-41 (2-line helpers, documented lineage).
_TWO_PLACES = Decimal("0.01")
_FOUR_PLACES = Decimal("0.0001")


def _q2(value: Decimal) -> Decimal:
    """Quantize to two decimal places (money)."""
    return value.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


def _q4(value: Decimal) -> Decimal:
    """Quantize to four decimal places (ratios)."""
    return value.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)


# Fields that get multiplied by scenario multipliers (field_name -> multiplier_key).
# Single source of truth: _AMAZON_MULTIPLIER_KEYS in amazon_config.py.
_MULTIPLIER_FIELD_MAP: Dict[str, str] = {
    "selling_price": "selling_price_multiplier",
    "unit_cost": "unit_cost_multiplier",
    "fba_fee": "fba_fee_multiplier",
    "referral_fee": "referral_fee_multiplier",
    "storage_fee": "storage_fee_multiplier",
    "advertising_cost": "advertising_cost_multiplier",
    "return_cost": "return_cost_multiplier",
    "fixed_development_cost": "fixed_development_cost_multiplier",
    # estimated_monthly_units uses units_multiplier (handled separately as int)
}


def _apply_amazon_multipliers(
    base: AmazonProfitInput,
    multipliers: Dict[str, float],
) -> Dict[str, Any]:
    """Apply scenario multipliers to the base profit input.

    Returns a dict of adjusted field values. Fields without multipliers
    pass through unchanged. ``estimated_monthly_units`` is converted to
    int after applying the units multiplier.
    """
    adjusted: Dict[str, Any] = {}

    # Multiplied Decimal fields
    for field, mult_key in _MULTIPLIER_FIELD_MAP.items():
        base_val = getattr(base, field)
        mult = Decimal(str(multipliers.get(mult_key, 1.0)))
        adjusted[field] = _q2(base_val * mult)

    # estimated_monthly_units (int, uses units_multiplier)
    units_mult = Decimal(str(multipliers.get("units_multiplier", 1.0)))
    adjusted["estimated_monthly_units"] = int(
        (Decimal(base.estimated_monthly_units) * units_mult).to_integral_value(
            rounding=ROUND_HALF_UP
        )
    )

    # Fields without multipliers — pass through as-is (quantized to 2dp)
    for field in (
        "inbound_shipping",
        "international_shipping",
        "customs_duty",
        "other_variable_cost",
        "monthly_fixed_cost",
        "initial_investment",
    ):
        adjusted[field] = _q2(getattr(base, field))

    return adjusted


def calculate_amazon_profit(
    profit_input: AmazonProfitInput,
    scenario_multipliers: Dict[str, float],
    scenario_name: str,
) -> AmazonProfitResult:
    """Calculate Amazon profit for one scenario.

    Args:
        profit_input: Base cost/price inputs (from config defaults or user).
        scenario_multipliers: The 9 multiplier values for this scenario
            (from config ``scenarios.<name>``).
        scenario_name: ``"base"``, ``"optimistic"`` or ``"pessimistic"``.

    Returns:
        An :class:`AmazonProfitResult` with all cost fields, derived
        metrics and ``calculation_version``.
    """
    adj = _apply_amazon_multipliers(profit_input, scenario_multipliers)

    selling_price: Decimal = adj["selling_price"]
    unit_cost: Decimal = adj["unit_cost"]
    inbound_shipping: Decimal = adj["inbound_shipping"]
    international_shipping: Decimal = adj["international_shipping"]
    customs_duty: Decimal = adj["customs_duty"]
    fba_fee: Decimal = adj["fba_fee"]
    referral_fee: Decimal = adj["referral_fee"]
    storage_fee: Decimal = adj["storage_fee"]
    advertising_cost: Decimal = adj["advertising_cost"]
    return_cost: Decimal = adj["return_cost"]
    other_variable_cost: Decimal = adj["other_variable_cost"]
    fixed_development_cost: Decimal = adj["fixed_development_cost"]
    initial_investment: Decimal = adj["initial_investment"]
    estimated_monthly_units: int = adj["estimated_monthly_units"]
    monthly_fixed_cost: Decimal = adj["monthly_fixed_cost"]

    # total_variable_cost_per_unit
    total_variable_cost_per_unit = _q2(
        unit_cost
        + inbound_shipping
        + international_shipping
        + customs_duty
        + fba_fee
        + referral_fee
        + storage_fee
        + advertising_cost
        + return_cost
        + other_variable_cost
    )

    # unit_profit
    unit_profit = _q2(selling_price - total_variable_cost_per_unit)

    # unit_margin (None if selling_price <= 0)
    if selling_price > 0:
        unit_margin = _q4(unit_profit / selling_price)
    else:
        unit_margin = Decimal("0")

    # monthly_profit
    monthly_profit = _q2(
        unit_profit * Decimal(estimated_monthly_units) - monthly_fixed_cost
    )

    # annualized_profit
    annualized_profit = _q2(monthly_profit * Decimal("12"))

    # roi: None when initial_investment <= 0 OR monthly_profit <= 0 (loss)
    if initial_investment <= 0 or monthly_profit <= 0:
        roi: Optional[Decimal] = None
    else:
        roi = _q4(annualized_profit / initial_investment)

    return AmazonProfitResult(
        scenario=scenario_name,
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
        total_variable_cost_per_unit=total_variable_cost_per_unit,
        unit_profit=unit_profit,
        unit_margin=unit_margin,
        monthly_profit=monthly_profit,
        annualized_profit=annualized_profit,
        roi=roi,
        calculation_version=_CALCULATION_VERSION,
    )


def _resolve_scenarios(
    cli_scenario: str,
    config_scenarios: Dict[str, Any],
) -> List[str]:
    """Determine which scenario names to calculate.

    ``--scenario all`` → ``["base", "optimistic", "pessimistic"]``.
    A single name → ``[name]``. Unknown names raise ``ValueError``.
    """
    if cli_scenario == "all":
        return ["base", "optimistic", "pessimistic"]
    if cli_scenario not in config_scenarios:
        raise ValueError(
            f"Unknown scenario {cli_scenario!r}. "
            f"Available: {list(config_scenarios.keys())}"
        )
    return [cli_scenario]


class ProfitAgent:
    """Agent wrapper that runs profit calculation for requested scenarios."""

    NAME = "profit"
    VERSION = "profit_agent_v1"

    def run(
        self,
        context: WorkflowContext,
        *,
        profit_input: Optional[AmazonProfitInput] = None,
        scenarios: Optional[List[str]] = None,
    ) -> AgentResult:
        """Run the profit calculation.

        Args:
            context: The workflow context (for reading config and CLI args).
            profit_input: Optional explicit profit input. If ``None``,
                the agent tries to read it from context (set by the
                workflow orchestrator).
            scenarios: Optional explicit scenario list. If ``None``,
                reads ``cli_args.scenario`` from context (default ``base``).

        Returns:
            An :class:`AgentResult` whose ``output`` is a dict mapping
            scenario name → :class:`AmazonProfitResult.to_dict()`.
        """
        config = context.config
        config_scenarios: Dict[str, Any] = config.get("scenarios", {})

        # Resolve scenario list
        if scenarios is None:
            cli_scenario = context.cli_args.get("scenario", "base")
            try:
                scenarios = _resolve_scenarios(cli_scenario, config_scenarios)
            except ValueError as exc:
                return AgentResult(
                    agent_name=self.NAME,
                    status="failed",
                    error=str(exc),
                    version=self.VERSION,
                    source="calculated",
                )

        if profit_input is None:
            # In the full workflow, the orchestrator sets this on context
            # via a private attribute. For standalone use, we return
            # an incomplete status.
            return AgentResult(
                agent_name=self.NAME,
                status="incomplete",
                warnings=["No profit_input provided and none found on context."],
                version=self.VERSION,
                source="calculated",
            )

        results: Dict[str, Any] = {}
        warnings: List[str] = []
        assumptions: List[str] = []

        for scenario_name in scenarios:
            if scenario_name not in config_scenarios:
                warnings.append(
                    f"Scenario {scenario_name!r} not in config; skipped."
                )
                continue
            multipliers = config_scenarios[scenario_name]
            result = calculate_amazon_profit(
                profit_input, multipliers, scenario_name
            )
            results[scenario_name] = result.to_dict()

            # Flag loss scenarios
            if result.monthly_profit <= 0:
                warnings.append(
                    f"Scenario {scenario_name!r}: monthly profit is "
                    f"non-positive ({result.monthly_profit}); ROI is null."
                )

        assumptions.append(
            f"Profit calculated using {_CALCULATION_VERSION}; "
            f"9 Amazon-specific scenario multipliers applied."
        )

        return AgentResult(
            agent_name=self.NAME,
            status="completed",
            input_summary={
                "selling_price": str(profit_input.selling_price),
                "unit_cost": str(profit_input.unit_cost),
                "estimated_monthly_units": profit_input.estimated_monthly_units,
                "initial_investment": str(profit_input.initial_investment),
                "scenarios": list(scenarios),
            },
            output=results,
            warnings=warnings,
            assumptions=assumptions,
            source="calculated",
            version=self.VERSION,
        )
