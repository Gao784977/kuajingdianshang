"""Opportunity scoring agent for the V3 Amazon workflow.

Reads prior agent outputs (keyword, market, competitor, review) from
:class:`WorkflowContext` and produces an :class:`OpportunityOutput`
with four 1-5 scores and a development recommendation.

Scoring rubric (deterministic, rule-based; no LLM):

* ``market_opportunity`` (1-5): driven by
  :attr:`MarketOutput.opportunity_score` (0-100) — see ``_score_market``.
* ``competition`` (1-5): driven by
  :attr:`MarketOutput.competition_level` and the average competitor
  review count — see ``_score_competition``.
* ``supply_chain_feasibility`` (1-5): base 4; drop to 3 if a user-supplied
  target price exists and is below the cost floor; drop to 2 if multiple
  competitors report high review counts (>1500, signalling entrenched
  supply).
* ``differentiation_potential`` (1-5): driven by
  :attr:`CompetitorOutput.market_gaps` count and
  :attr:`CompetitorOutput.differentiation_opportunities` count.

Development recommendation rules (spec section 8):

* ``develop`` — all four scores ≥ 4 AND user-supplied real data
  (at least one of competitor / review confidence is ``medium``).
* ``validate_first`` — scores mixed but no hard blocker; this is the
  default for mock-only data with positive scores.
* ``monitor`` — at least one score ≤ 2 but no critical blocker.
* ``reject_or_hold`` — target price below the cost floor (covered cost
  test fails) OR two or more scores ≤ 1.

Per spec rule: "mock-only data → confidence ≤ medium"; the agent always
sets ``human_review_required=True`` when there is no real user-validated
data (i.e. competitor and review confidence are both ``low``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from .models import (
    AgentResult,
    CompetitorOutput,
    MarketOutput,
    OpportunityOutput,
    ReviewOutput,
    WorkflowContext,
)


def _score_market(opportunity_score_100: int) -> int:
    """Map the 0-100 market opportunity score to a 1-5 band."""
    if opportunity_score_100 >= 80:
        return 5
    if opportunity_score_100 >= 60:
        return 4
    if opportunity_score_100 >= 40:
        return 3
    if opportunity_score_100 >= 20:
        return 2
    return 1


def _score_competition(competition_level: str, avg_review_count: Decimal) -> int:
    """Score competition (1 = saturated, 5 = wide open).

    Low review counts and "low" competition level → higher score.
    High review counts and "high" competition level → lower score.
    """
    base = {"low": 5, "medium": 3, "high": 2}.get(competition_level, 3)
    # Penalize entrenched competitors (high review counts)
    if avg_review_count >= Decimal("1500"):
        base = max(1, base - 1)
    elif avg_review_count <= Decimal("300"):
        base = min(5, base + 1)
    return base


def _score_feasibility(
    product_input_target_price_min: Optional[Decimal],
    unit_cost: Decimal,
    avg_review_count: Decimal,
) -> int:
    """Score supply-chain feasibility.

    Base 4. Drop to 3 if the user's target price is below the cost floor
    (target_price_min < unit_cost + small margin). Drop to 2 if multiple
    competitors have very high review counts (>1500, signalling
    entrenched supply).
    """
    base = 4
    if (
        product_input_target_price_min is not None
        and product_input_target_price_min < unit_cost
    ):
        base = min(base, 2)
    elif (
        product_input_target_price_min is not None
        and product_input_target_price_min < (unit_cost * Decimal("1.5"))
    ):
        base = min(base, 3)
    if avg_review_count >= Decimal("1500"):
        base = min(base, 3)
    return base


def _score_differentiation(
    gap_count: int,
    opportunity_count: int,
) -> int:
    """Score differentiation potential.

    More gaps and more differentiation opportunities → higher score
    (we have more places to win).
    """
    total = gap_count + opportunity_count
    if total >= 8:
        return 5
    if total >= 5:
        return 4
    if total >= 3:
        return 3
    if total >= 1:
        return 2
    return 1


def _review_count_avg(reviews: Optional[ReviewOutput]) -> Decimal:
    """Best-effort estimate of average competitor review count from the
    review agent's count. Used only as a fallback; the real signal comes
    from competitor_agent. We return a neutral 1000 when unknown so
    downstream rules behave reasonably."""
    if reviews is None:
        return Decimal("1000")
    return Decimal("1000")


def _competitor_review_avg(competitor: Optional[CompetitorOutput]) -> Decimal:
    """Return the average competitor review count, or 1000 if unknown."""
    if competitor is None:
        return Decimal("1000")
    avg_str = competitor.review_distribution.get("average")
    if avg_str is None:
        return Decimal("1000")
    try:
        return Decimal(str(avg_str))
    except Exception:
        return Decimal("1000")


def _unit_cost_floor(context: WorkflowContext) -> Decimal:
    """Pull the unit cost from config.profit_cost_defaults (used for
    the feasibility price test). Falls back to 8.50 if absent."""
    defaults = context.config.get("profit_cost_defaults", {}) or {}
    try:
        return Decimal(str(defaults.get("unit_cost", "8.50")))
    except Exception:
        return Decimal("8.50")


class OpportunityAgent:
    """Score the four opportunity dimensions and emit a recommendation."""

    NAME = "opportunity"
    VERSION = "opportunity_agent_v1"

    def run(self, context: WorkflowContext) -> AgentResult:
        """Run opportunity scoring.

        Reads keyword / market / competitor / review outputs from
        ``context``. Any missing or skipped prior agent makes this
        agent degrade to ``status="incomplete"``.

        Returns:
            :class:`AgentResult` whose ``output`` is an
            :class:`OpportunityOutput`.
        """
        warnings: list[str] = []
        assumptions: list[str] = []
        reasons: list[str] = []
        risks: list[str] = []
        required_validation: list[str] = []

        market = context.get_output("market", MarketOutput)
        competitor = context.get_output("competitor", CompetitorOutput)
        review = context.get_output("review", ReviewOutput)

        # Hard dependency on market (provides opportunity_score + competition)
        if market is None:
            warnings.append(
                "Market analysis missing; opportunity scoring incomplete."
            )
            return AgentResult(
                agent_name=self.NAME,
                status="incomplete",
                warnings=warnings,
                version=self.VERSION,
                source="calculated",
            )

        # Scores
        market_score = _score_market(market.opportunity_score)
        review_avg = _competitor_review_avg(competitor)
        competition_score = _score_competition(
            market.competition_level, review_avg
        )
        unit_cost = _unit_cost_floor(context)
        target_min = (
            context.product_input.target_price_min
            if context.product_input
            else None
        )
        feasibility_score = _score_feasibility(target_min, unit_cost, review_avg)

        gap_count = len(competitor.market_gaps) if competitor else 0
        opp_count = (
            len(competitor.differentiation_opportunities) if competitor else 0
        )
        differentiation_score = _score_differentiation(gap_count, opp_count)

        # Confidence — mock-only data → at most medium
        any_real_data = (
            (competitor is not None and competitor.confidence != "low")
            or (review is not None and review.confidence != "low")
        )
        if any_real_data:
            confidence = "medium"
        else:
            confidence = "low"

        # Recommendation rules (spec section 8)
        scores = [
            market_score,
            competition_score,
            feasibility_score,
            differentiation_score,
        ]
        low_count = sum(1 for s in scores if s <= 2)
        very_low_count = sum(1 for s in scores if s <= 1)
        all_high = all(s >= 4 for s in scores)

        # Hard blocker: target price below cost floor
        price_below_cost = (
            target_min is not None and target_min < unit_cost
        )

        if price_below_cost or very_low_count >= 2:
            recommendation = "reject_or_hold"
            reasons.append(
                "Target price is below the unit cost floor or two or more "
                "scores are at the lowest band (1)."
            )
        elif all_high and any_real_data:
            recommendation = "develop"
            reasons.append(
                "All four opportunity scores ≥ 4 and real competitor/review "
                "data is available."
            )
        elif low_count >= 1:
            recommendation = "monitor"
            reasons.append(
                "At least one opportunity score ≤ 2; monitor the niche and "
                "revisit after validating the weak dimension."
            )
        else:
            recommendation = "validate_first"
            reasons.append(
                "Scores are mixed but no hard blocker; validate before "
                "committing to development."
            )

        # Human review required when no real validated data
        human_review_required = not any_real_data
        if human_review_required:
            warnings.append(
                "No real (non-mock) competitor or review data; "
                "human_review_required=True."
            )

        # Risks — derived from low scores and data gaps
        if market_score <= 2:
            risks.append("Market opportunity is weak (score ≤ 2).")
        if competition_score <= 2:
            risks.append("Competition is intense (score ≤ 2).")
        if feasibility_score <= 2:
            risks.append(
                "Supply-chain feasibility is low; target price may not cover "
                "the cost floor."
            )
        if differentiation_score <= 2:
            risks.append(
                "Differentiation potential is limited; few gaps or "
                "opportunities identified."
            )
        if not any_real_data:
            risks.append(
                "All data is mock; real competitor and review data is "
                "required before a final go/no-go decision."
            )

        # Required validation — what the user must verify
        required_validation.append(
            "Validate competitor pricing and review counts with real "
            "Amazon US ASINs (SP-API or Helium 10)."
        )
        required_validation.append(
            "Validate unit cost and FBA fee assumptions with a real supplier "
            "quote and the Amazon FBA revenue calculator."
        )
        if recommendation == "validate_first":
            required_validation.append(
                "Run a small initial order (50-100 units) and run PPC for "
                "4-6 weeks to validate demand and conversion rate."
            )
        if recommendation == "monitor":
            required_validation.append(
                "Recheck the niche in 60 days; revisit if competitors exit "
                "or new market demand emerges."
            )

        output = OpportunityOutput(
            market_opportunity=market_score,
            competition=competition_score,
            supply_chain_feasibility=feasibility_score,
            differentiation_potential=differentiation_score,
            development_recommendation=recommendation,
            reasons=reasons,
            risks=risks,
            required_validation=required_validation,
            confidence=confidence,
            human_review_required=human_review_required,
            source="calculated",
        )

        assumptions.append(
            "Scoring uses deterministic rules; weights for each dimension "
            "are in config.score_rules (30/20/20/30)."
        )

        return AgentResult(
            agent_name=self.NAME,
            status="completed",
            input_summary={
                "market_opportunity": market_score,
                "competition": competition_score,
                "supply_chain_feasibility": feasibility_score,
                "differentiation_potential": differentiation_score,
                "recommendation": recommendation,
                "any_real_data": any_real_data,
            },
            output=output,
            warnings=warnings,
            assumptions=assumptions,
            source="calculated",
            version=self.VERSION,
        )
