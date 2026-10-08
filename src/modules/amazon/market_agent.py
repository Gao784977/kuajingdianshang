"""Market analysis agent for the V3 Amazon workflow.

Returns a qualitative market analysis for the configured marketplace.
The agent reads the marketplace from
:class:`WorkflowContext.product_input` and uses
:func:`mock_data.get_mock_market` for the deterministic chicken-coop-door
niche. Opportunity score comes from the qualitative mock value (75),
which downstream agents can use as one input to opportunity scoring.

Per decision #7, mock-data confidence is ``low`` — never ``high``.
"""

from __future__ import annotations

from typing import Any, Dict

from .mock_data import get_mock_market
from .models import AgentResult, MarketOutput, WorkflowContext


class MarketAgent:
    """Produce a deterministic market analysis for the configured marketplace."""

    NAME = "market"
    VERSION = "market_agent_v1"

    def run(self, context: WorkflowContext) -> AgentResult:
        """Run market analysis.

        Args:
            context: Workflow context; reads ``product_input.marketplace``
                and ``config.supported_marketplaces``.

        Returns:
            :class:`AgentResult` whose ``output`` is a
            :class:`MarketOutput`. Status is ``"completed"``; an unknown
            marketplace is recorded as a warning and the analysis falls
            back to ``"amazon_us"``.
        """
        warnings: list[str] = []
        assumptions: list[str] = []

        product_input = context.product_input
        marketplace = product_input.marketplace if product_input else ""

        supported = context.config.get("supported_marketplaces", []) or []
        if marketplace and supported and marketplace not in supported:
            warnings.append(
                f"Marketplace {marketplace!r} not in supported_marketplaces "
                f"{supported}; falling back to 'amazon_us'."
            )
            marketplace = "amazon_us"

        if not marketplace:
            marketplace = "amazon_us"
            warnings.append(
                "Product input has no marketplace; defaulting to 'amazon_us'."
            )

        mock_output: MarketOutput = get_mock_market(marketplace)

        # Carry the user-supplied target price range forward into the
        # market output's price_range when provided (user input wins
        # per decision #13).
        price_range = mock_output.price_range
        if product_input and product_input.target_price_min is not None:
            tmin = product_input.target_price_min
            tmax = product_input.target_price_max
            if tmax is not None:
                price_range = f"${tmin} - ${tmax}"
            else:
                price_range = f"${tmin}+"

        output = MarketOutput(
            marketplace=mock_output.marketplace,
            category=mock_output.category,
            product_line=mock_output.product_line,
            consumption_scenario=mock_output.consumption_scenario,
            target_customer=mock_output.target_customer,
            market_capacity=mock_output.market_capacity,
            growth_trend=mock_output.growth_trend,
            price_range=price_range,
            competition_level=mock_output.competition_level,
            opportunity_score=mock_output.opportunity_score,
            market_assumptions=list(mock_output.market_assumptions),
            source="mock_data",
            confidence="low",
        )

        assumptions.append(
            "Market analysis uses deterministic mock data for the "
            "chicken-coop-door niche; real market capacity requires "
            "an external market-research API."
        )

        return AgentResult(
            agent_name=self.NAME,
            status="completed",
            input_summary={"marketplace": marketplace},
            output=output,
            warnings=warnings,
            assumptions=assumptions,
            source="mock_data",
            version=self.VERSION,
        )
