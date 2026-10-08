"""Competitor analysis agent for the V3 Amazon workflow.

Aggregates a list of :class:`CompetitorRow` (user CSV merged with mock
rows per decision #13) into a :class:`CompetitorOutput`:

* ``competitor_matrix`` — one dict per competitor (brand, ASIN, price,
  rating, review_count, source).
* ``price_distribution`` — min / max / average / count.
* ``rating_distribution`` — min / max / average / count.
* ``review_distribution`` — total / min / max / average / count.
* ``common_selling_points`` — top recurring phrases across competitors.
* ``common_negative_points`` — top recurring negative phrases.
* ``market_gaps`` — features competitors fail to deliver (derived from
  negative points and missing selling points).
* ``differentiation_opportunities`` — actionable product, design, or
  service directions inferred from the gaps.

The agent is deterministic: same input rows → same output. Source and
confidence are derived from the highest-confidence source in the input
rows (``imported_csv`` → ``medium``, ``mock_data`` only → ``low``).
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .models import AgentResult, CompetitorOutput, CompetitorRow, WorkflowContext


def _avg(values: List[Decimal]) -> Optional[Decimal]:
    if not values:
        return None
    return sum(values) / Decimal(len(values))


def _split_phrases(text: str) -> List[str]:
    """Split a selling-points / negative-points cell into phrases."""
    if not text:
        return []
    # Split on common delimiters: semicolon, comma, period.
    parts: List[str] = []
    for chunk in text.replace(";", ",").split(","):
        chunk = chunk.strip().rstrip(".").strip()
        if chunk:
            parts.append(chunk.lower())
    return parts


class CompetitorAgent:
    """Aggregate competitor rows into a structured competitor analysis."""

    NAME = "competitor"
    VERSION = "competitor_agent_v1"

    def run(
        self,
        context: WorkflowContext,
        *,
        competitors: Optional[List[CompetitorRow]] = None,
    ) -> AgentResult:
        """Run competitor analysis.

        Args:
            context: Workflow context (for config / CLI args).
            competitors: List of competitor rows (user CSV + mock fills).
                If ``None``, the agent returns ``status="incomplete"``.

        Returns:
            :class:`AgentResult` whose ``output`` is a
            :class:`CompetitorOutput`.
        """
        warnings: list[str] = []
        assumptions: list[str] = []

        if not competitors:
            warnings.append(
                "No competitor rows provided; competitor analysis incomplete."
            )
            return AgentResult(
                agent_name=self.NAME,
                status="incomplete",
                warnings=warnings,
                version=self.VERSION,
                source="calculated",
            )

        # Build the competitor matrix (lightweight view)
        matrix: List[Dict[str, Any]] = [row.to_dict() for row in competitors]

        # Price / rating / review distributions
        prices = [row.price for row in competitors]
        ratings = [row.rating for row in competitors]
        review_counts = [row.review_count for row in competitors]

        price_avg = _avg(prices)
        rating_avg = _avg(ratings)
        review_avg_dec = (
            sum(Decimal(r) for r in review_counts) / Decimal(len(review_counts))
            if review_counts
            else None
        )

        price_distribution: Dict[str, Any] = {
            "min": str(min(prices)) if prices else None,
            "max": str(max(prices)) if prices else None,
            "average": str(price_avg) if price_avg is not None else None,
            "count": len(prices),
        }
        rating_distribution: Dict[str, Any] = {
            "min": str(min(ratings)) if ratings else None,
            "max": str(max(ratings)) if ratings else None,
            "average": str(rating_avg) if rating_avg is not None else None,
            "count": len(ratings),
        }
        review_distribution: Dict[str, Any] = {
            "total": sum(review_counts),
            "min": min(review_counts) if review_counts else 0,
            "max": max(review_counts) if review_counts else 0,
            "average": str(review_avg_dec) if review_avg_dec is not None else None,
            "count": len(review_counts),
        }

        # Phrase aggregation
        selling_phrases: List[str] = []
        negative_phrases: List[str] = []
        for row in competitors:
            selling_phrases.extend(_split_phrases(row.selling_points))
            negative_phrases.extend(_split_phrases(row.negative_points))

        # Common = phrases that appear in >=2 competitors
        selling_counter = Counter(selling_phrases)
        negative_counter = Counter(negative_phrases)

        common_selling = [
            phrase
            for phrase, count in selling_counter.most_common()
            if count >= 2
        ]
        # If no phrase repeats, fall back to the most frequent single phrases
        if not common_selling and selling_phrases:
            common_selling = [
                phrase
                for phrase, _ in selling_counter.most_common(5)
            ]

        common_negative = [
            phrase
            for phrase, count in negative_counter.most_common()
            if count >= 2
        ]
        if not common_negative and negative_phrases:
            common_negative = [
                phrase
                for phrase, _ in negative_counter.most_common(5)
            ]

        # Market gaps — features competitors fail on
        market_gaps: List[str] = []
        # Common negative themes become gaps
        for phrase in common_negative:
            market_gaps.append(f"Address: {phrase}")
        # Specific well-known gaps for the chicken coop door niche
        # (derived deterministically from the mock competitor set)
        if not any("wifi" in p or "app" in p for p in selling_phrases):
            market_gaps.append("No competitor offers wifi / app remote control")
        if not any("solar" in p and "plug" in p for p in selling_phrases):
            market_gaps.append("Few competitors offer dual power (solar + plug)")

        # Differentiation opportunities — actionable product directions
        differentiation_opportunities: List[str] = []
        if any("install" in p for p in negative_phrases):
            differentiation_opportunities.append(
                "Tool-free, pre-assembled mounting system with clear instructions"
            )
        if any("motor" in p and ("fail" in p or "noise" in p) for p in negative_phrases):
            differentiation_opportunities.append(
                "Higher-grade motor with 12+ month durability testing"
            )
        if any("packaging" in p or "missing" in p for p in negative_phrases):
            differentiation_opportunities.append(
                "Reinforced packaging with hardware count checklist"
            )
        if any("price" in p or "expensive" in p for p in negative_phrases):
            differentiation_opportunities.append(
                "Aggressive price point with feature parity at $25-$30"
            )
        if any("warranty" not in p for p in selling_phrases):
            differentiation_opportunities.append(
                "Extended warranty (2 years) as a trust signal"
            )
        # Always include connectivity gap if no competitor mentions wifi/app
        if not any("wifi" in p or "app" in p for p in selling_phrases):
            differentiation_opportunities.append(
                "WiFi + app control for remote monitoring and scheduling"
            )

        # Source / confidence: if any row is imported_csv, source is
        # imported_csv (medium confidence). Otherwise mock_data (low).
        sources = {row.source for row in competitors}
        if "imported_csv" in sources or "user_input" in sources:
            agent_source = "imported_csv"
            confidence = "medium"
        else:
            agent_source = "mock_data"
            confidence = "low"

        output = CompetitorOutput(
            competitor_matrix=matrix,
            price_distribution=price_distribution,
            rating_distribution=rating_distribution,
            review_distribution=review_distribution,
            common_selling_points=common_selling,
            common_negative_points=common_negative,
            market_gaps=market_gaps,
            differentiation_opportunities=differentiation_opportunities,
            source=agent_source,
            confidence=confidence,
        )

        assumptions.append(
            f"Aggregated {len(competitors)} competitor rows; "
            f"sources={sorted(sources)}."
        )

        return AgentResult(
            agent_name=self.NAME,
            status="completed",
            input_summary={
                "competitor_count": len(competitors),
                "sources": sorted(sources),
            },
            output=output,
            warnings=warnings,
            assumptions=assumptions,
            source=agent_source,
            version=self.VERSION,
        )
