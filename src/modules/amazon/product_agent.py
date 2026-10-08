"""Product development plan agent for the V3 Amazon workflow.

Reads the four prior agent outputs (keyword, market, competitor,
review) from :class:`WorkflowContext` and produces a
:class:`ProductOutput` describing the proposed product:

* Product name, positioning, target customer, use scenario
* Core selling points — derived from competitor negative points and
  review feature_requests (turn complaints into selling points)
* Functional design — feature list
* Differentiation plan — actionable deltas vs. competitors
* Target price / cost / gross margin (from config.profit_cost_defaults
  and the user's target price range)
* Packaging direction, installation direction
* Development cycle days, launch risks, validation plan
* Required supplier questions

Degrade rule (spec): if any of keyword / market / competitor / review
is missing or skipped, the agent returns ``status="incomplete"`` with
an empty :class:`ProductOutput` and a warning.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List, Optional

from .models import (
    AgentResult,
    CompetitorOutput,
    KeywordOutput,
    MarketOutput,
    ProductOutput,
    ReviewOutput,
    WorkflowContext,
)


def _core_selling_points(
    competitor: Optional[CompetitorOutput],
    review: Optional[ReviewOutput],
) -> List[str]:
    """Derive selling points from competitor gaps and review requests."""
    points: List[str] = []

    # Reverse the negative themes into selling points
    neg = (competitor.common_negative_points if competitor else []) or []
    if any("install" in p for p in neg):
        points.append("Tool-free installation in under 15 minutes")
    if any("motor" in p and ("fail" in p or "noise" in p) for p in neg):
        points.append("Premium brushless motor with 2-year durability warranty")
    if any("packaging" in p or "missing" in p for p in neg):
        points.append("Reinforced packaging with hardware checklist enclosed")
    if any("price" in p or "expensive" in p for p in neg):
        points.append("Premium features at a $25-$30 price point")

    # Feature requests → selling points (if multiple reviewers ask, we deliver)
    feature_phrases = (review.feature_requests if review else []) or []
    if any("app" in p or "wifi" in p or "wi-fi" in p for p in feature_phrases):
        points.append("WiFi app control with remote monitoring and scheduling")
    if any("solar" in p for p in feature_phrases):
        points.append("Dual-power: solar + USB-C backup")

    # Always include a quality claim
    if not any("quality" in p.lower() for p in points):
        points.append("UV-resistant housing for all-weather durability")

    # Deduplicate while preserving order
    seen = set()
    unique: List[str] = []
    for p in points:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _functional_design(
    competitor: Optional[CompetitorOutput],
    review: Optional[ReviewOutput],
) -> List[str]:
    """Build a feature list from review improvement directions."""
    features: List[str] = []
    if review is not None:
        for direction in review.product_improvement_directions:
            # Compress each improvement direction to a short feature line
            features.append(direction)
    # Always include core chicken-coop-door features
    base_features = [
        "Light-sensor auto open/close at dawn/dusk",
        "Solar panel + USB-C dual-power backup",
        "Heavy-duty predator-proof latch (raccoon/fox tested)",
        "WiFi + app remote control with scheduling",
        "UV-resistant, IP65 weatherproof housing",
    ]
    seen = set(features)
    for f in base_features:
        if f not in seen:
            features.append(f)
            seen.add(f)
    return features


def _differentiation_plan(competitor: Optional[CompetitorOutput]) -> List[str]:
    """Use the competitor agent's differentiation_opportunities directly."""
    if competitor is None:
        return ["Unable to derive differentiation without competitor analysis."]
    return list(competitor.differentiation_opportunities)


def _target_price(
    context: WorkflowContext,
) -> Optional[Decimal]:
    """User-supplied target price wins; else config profit_cost_defaults.selling_price."""
    if context.product_input and context.product_input.target_price_max is not None:
        return context.product_input.target_price_max
    if context.product_input and context.product_input.target_price_min is not None:
        return context.product_input.target_price_min
    defaults = context.config.get("profit_cost_defaults", {}) or {}
    try:
        return Decimal(str(defaults.get("selling_price", "29.99")))
    except Exception:
        return Decimal("29.99")


def _target_cost(context: WorkflowContext) -> Optional[Decimal]:
    """Use config.profit_cost_defaults.unit_cost as the target cost."""
    defaults = context.config.get("profit_cost_defaults", {}) or {}
    try:
        return Decimal(str(defaults.get("unit_cost", "8.50")))
    except Exception:
        return Decimal("8.50")


def _target_gross_margin(
    target_price: Optional[Decimal],
    target_cost: Optional[Decimal],
) -> Optional[Decimal]:
    if target_price is None or target_cost is None or target_price <= 0:
        return None
    return (target_price - target_cost) / target_price


class ProductAgent:
    """Produce a product development plan from prior agent outputs."""

    NAME = "product"
    VERSION = "product_agent_v1"

    def run(self, context: WorkflowContext) -> AgentResult:
        """Run product planning.

        Reads keyword / market / competitor / review outputs from
        ``context``. Any missing or skipped prior agent makes this
        agent degrade to ``status="incomplete"``.

        Returns:
            :class:`AgentResult` whose ``output`` is a
            :class:`ProductOutput`.
        """
        warnings: list[str] = []
        assumptions: list[str] = []

        keyword = context.get_output("keyword", KeywordOutput)
        market = context.get_output("market", MarketOutput)
        competitor = context.get_output("competitor", CompetitorOutput)
        review = context.get_output("review", ReviewOutput)

        missing = [
            name
            for name, output in (
                ("keyword", keyword),
                ("market", market),
                ("competitor", competitor),
                ("review", review),
            )
            if output is None
        ]
        if missing:
            warnings.append(
                f"Prior agents missing/skipped: {missing}; product plan incomplete."
            )
            return AgentResult(
                agent_name=self.NAME,
                status="incomplete",
                warnings=warnings,
                version=self.VERSION,
                source="calculated",
            )

        # At this point all four prior outputs are present
        assert keyword is not None
        assert market is not None
        assert competitor is not None
        assert review is not None

        # Product name — derived from the keyword + a differentiator
        product_name = f"{keyword.normalized_keyword.title()} Pro (WiFi + Solar)"
        # Capitalize properly
        product_name = " ".join(
            part.capitalize() for part in keyword.normalized_keyword.split()
        ) + " Pro (WiFi + Solar)"

        product_positioning = (
            f"A premium yet affordable {keyword.normalized_keyword} with "
            f"WiFi app control, dual-power (solar + USB-C), and a "
            f"tool-free install. Targets the {market.competition_level} "
            f"competition band at ${_target_price(context)} — positioned "
            f"as 'premium features at mid-tier price'."
        )

        target_customer = market.target_customer
        use_scenario = market.consumption_scenario

        selling_points = _core_selling_points(competitor, review)
        functional_design = _functional_design(competitor, review)
        differentiation_plan = _differentiation_plan(competitor)

        target_price = _target_price(context)
        target_cost = _target_cost(context)
        target_gross_margin = _target_gross_margin(target_price, target_cost)

        # Packaging direction — derived from review packaging issues
        if (
            review.issue_categories.get("packaging", 0) > 0
            or any("packaging" in p for p in (competitor.common_negative_points or []))
        ):
            packaging_direction = (
                "Double-wall corrugated box with molded pulp inserts; "
                "hardware count checklist enclosed; ISTA 3A packaging test."
            )
        else:
            packaging_direction = (
                "Standard retail box with protective foam inserts."
            )

        # Installation direction — derived from review installation issues
        if review.issue_categories.get("installation", 0) > 0:
            installation_direction = (
                "Tool-free, pre-assembled design; illustrated quick-start "
                "card; QR code linking to 90-second install video."
            )
        else:
            installation_direction = (
                "Standard hardware kit with printed instructions."
            )

        # Development cycle — heuristic 60-90 days for this product class
        development_cycle_days = 75

        # Launch risks
        launch_risks: List[str] = []
        if any("price" in p or "expensive" in p for p in (competitor.common_negative_points or [])):
            launch_risks.append(
                "Price-sensitive niche; pricing above $30 may slow adoption."
            )
        if any("motor" in p and ("fail" in p or "noise" in p) for p in (competitor.common_negative_points or [])):
            launch_risks.append(
                "Motor reliability is a known category pain; supplier QC "
                "and 12-month durability testing are required."
            )
        if market.competition_level == "high":
            launch_risks.append(
                "High competition; PPC costs and review velocity may be "
                "elevated at launch."
            )
        if not launch_risks:
            launch_risks.append(
                "No specific launch risks identified from the mock data."
            )

        # Validation plan
        validation_plan = [
            "Order 50-100 unit pilot batch; run for 4-6 weeks on Amazon US",
            "Track conversion rate, ACoS, and organic review velocity",
            "Validate supplier QC on motor and housing before scaling to 500+ units",
            "After 30 days of live data, re-run this workflow with real data",
        ]

        # Required supplier questions
        required_supplier_questions = [
            "What is the FOB unit cost at 100 / 500 / 1000 units?",
            "Can you provide a brushless motor with 12+ month warranty?",
            "What is the lead time and MOQ for custom packaging?",
            "Can you provide a dual-power (solar + USB-C) variant?",
            "Do you have ISTA 3A or equivalent packaging test reports?",
            "What is the production capacity per month at peak?",
        ]

        # Confidence — product plan inherits the lowest prior confidence
        confidences = [
            keyword.confidence,
            market.confidence,
            competitor.confidence,
            review.confidence,
        ]
        if "low" in confidences:
            confidence = "low"
        elif "medium" in confidences:
            confidence = "medium"
        else:
            confidence = "high"

        output = ProductOutput(
            product_name=product_name,
            product_positioning=product_positioning,
            target_customer=target_customer,
            use_scenario=use_scenario,
            core_selling_points=selling_points,
            functional_design=functional_design,
            differentiation_plan=differentiation_plan,
            target_price=target_price,
            target_cost=target_cost,
            target_gross_margin=target_gross_margin,
            packaging_direction=packaging_direction,
            installation_direction=installation_direction,
            development_cycle_days=development_cycle_days,
            launch_risks=launch_risks,
            validation_plan=validation_plan,
            required_supplier_questions=required_supplier_questions,
            source="calculated",
            confidence=confidence,
        )

        assumptions.append(
            "Product plan derived from keyword / market / competitor / "
            "review outputs using deterministic rules."
        )

        return AgentResult(
            agent_name=self.NAME,
            status="completed",
            input_summary={
                "keyword": keyword.normalized_keyword,
                "marketplace": market.marketplace,
                "target_price": str(target_price) if target_price is not None else None,
                "target_cost": str(target_cost) if target_cost is not None else None,
                "target_gross_margin": str(target_gross_margin) if target_gross_margin is not None else None,
            },
            output=output,
            warnings=warnings,
            assumptions=assumptions,
            source="calculated",
            version=self.VERSION,
        )
