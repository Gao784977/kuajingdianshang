"""Review analysis agent for the V3 Amazon workflow.

Classifies each review into one or more of the 7 pain categories
configured in ``config.review_categories`` using deterministic
keyword rules:

* installation — install, setup, mount, wire, wiring, drill, instructions
* quality — broke, failed, warped, quality, motor, flimsy, broke, jam
* packaging — packaging, damaged, missing, broken, cracked, parts
* feature_request — wish, would love, app, wifi, scheduling, next version
* price — expensive, overpriced, value, affordable, worth
* shipping — shipping, delivery, arrived, transit
* customer_service — service, support, refund, return, customer service

Sentiment is derived from the rating: 4-5 → positive, 3 → neutral,
1-2 → negative. The agent also derives:

* ``positive_themes`` — recurring positive phrases from 4-5 star reviews
* ``negative_themes`` — recurring negative phrases from 1-3 star reviews
* ``feature_requests`` — phrases from feature_request reviews
* ``quality_issues`` — phrases from quality reviews
* ``packaging_issues`` — phrases from packaging reviews
* ``product_improvement_directions`` — actionable improvements derived
  from the negative themes and feature requests

Same input rows → same output (deterministic). Source and confidence
follow the same rule as :mod:`competitor_agent`.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

from .models import AgentResult, ReviewOutput, ReviewRow, WorkflowContext


# Category -> keyword patterns (case-insensitive substring match).
_CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "installation": [
        "install", "setup", "set up", "mount", "wire", "wiring", "drill",
        "instructions", "directions",
    ],
    "quality": [
        "broke", "broken", "failed", "fail", "warp", "warped", "quality",
        "motor", "flimsy", "jam", "jammed", "defective", "durability",
    ],
    "packaging": [
        "packaging", "package", "damaged", "damage", "missing", "cracked",
        "crack", "parts missing", "missing parts", "missing screws",
        "arrived broken",
    ],
    "feature_request": [
        "wish", "would love", "would be nice", "app", "wifi", "wi-fi",
        "bluetooth", "scheduling", "remote", "next version", "future",
        "smart", "phone",
    ],
    "price": [
        "expensive", "overpriced", "pricey", "value", "affordable",
        "worth", "cheap", "price",
    ],
    "shipping": [
        "shipping", "delivery", "delivered", "arrived", "transit",
        "shipping took", "weeks",
    ],
    "customer_service": [
        "customer service", "support", "refund", "return", "rma",
        "warranty", "contacted",
    ],
}


def _classify_review(text: str) -> List[str]:
    """Return the list of categories a review text matches."""
    if not text:
        return []
    lowered = text.lower()
    categories: List[str] = []
    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            categories.append(category)
    return categories


def _sentiment_for_rating(rating: int) -> str:
    if rating >= 4:
        return "positive"
    if rating == 3:
        return "neutral"
    return "negative"


def _phrases(text: str) -> List[str]:
    """Split a review into lowercase phrases."""
    if not text:
        return []
    # Sentence-aware split — keep punctuation out of phrases.
    parts = re.split(r"[.\n]+", text)
    out: List[str] = []
    for p in parts:
        p = p.strip().rstrip(",").strip()
        if p:
            out.append(p.lower())
    return out


class ReviewAgent:
    """Aggregate review rows into a structured review analysis."""

    NAME = "review"
    VERSION = "review_agent_v1"

    def run(
        self,
        context: WorkflowContext,
        *,
        reviews: Optional[List[ReviewRow]] = None,
    ) -> AgentResult:
        """Run review analysis.

        Args:
            context: Workflow context.
            reviews: List of review rows (user CSV + mock fills).
                If ``None``, returns ``status="incomplete"``.

        Returns:
            :class:`AgentResult` whose ``output`` is a
            :class:`ReviewOutput`.
        """
        warnings: list[str] = []
        assumptions: list[str] = []

        if not reviews:
            warnings.append(
                "No review rows provided; review analysis incomplete."
            )
            return AgentResult(
                agent_name=self.NAME,
                status="incomplete",
                warnings=warnings,
                version=self.VERSION,
                source="calculated",
            )

        # Pull configured categories so the output reflects config even
        # if a category isn't represented in the data.
        configured_categories: List[str] = list(
            context.config.get("review_categories", []) or []
        )

        review_count = len(reviews)

        # Sentiment summary
        sentiment = Counter(_sentiment_for_rating(r.rating) for r in reviews)
        sentiment_summary: Dict[str, Any] = {
            "positive": sentiment.get("positive", 0),
            "neutral": sentiment.get("neutral", 0),
            "negative": sentiment.get("negative", 0),
        }

        # Issue categories — count reviews per category
        issue_categories: Dict[str, int] = {c: 0 for c in configured_categories}
        # Track reviews classified into each category so we can extract themes
        category_texts: Dict[str, List[str]] = {c: [] for c in configured_categories}

        for r in reviews:
            cats = _classify_review(r.review_text)
            for c in cats:
                # Only count configured categories (unknown categories
                # are silently dropped to match the spec's enum).
                if c in issue_categories:
                    issue_categories[c] += 1
                    category_texts[c].append(r.review_text)

        # Positive / negative themes
        positive_phrases: List[str] = []
        negative_phrases: List[str] = []
        for r in reviews:
            phrases = _phrases(r.review_text)
            if _sentiment_for_rating(r.rating) == "positive":
                positive_phrases.extend(phrases)
            else:
                negative_phrases.extend(phrases)

        positive_counter = Counter(positive_phrases)
        negative_counter = Counter(negative_phrases)

        positive_themes = [p for p, _ in positive_counter.most_common(5)]
        negative_themes = [p for p, _ in negative_counter.most_common(5)]

        # Category-specific issue lists — top phrases from each category
        def _top_phrases(texts: List[str], limit: int = 5) -> List[str]:
            counter: Counter[str] = Counter()
            for t in texts:
                counter.update(_phrases(t))
            return [p for p, _ in counter.most_common(limit)]

        feature_requests = _top_phrases(category_texts.get("feature_request", []))
        quality_issues = _top_phrases(category_texts.get("quality", []))
        packaging_issues = _top_phrases(category_texts.get("packaging", []))

        # Product improvement directions — derived actionable statements
        improvement_directions: List[str] = []
        if issue_categories.get("installation", 0) > 0:
            improvement_directions.append(
                "Improve installation experience: pre-assembled parts, "
                "illustrated quick-start guide, video QR code"
            )
        if issue_categories.get("quality", 0) > 0:
            improvement_directions.append(
                "Upgrade motor and material quality: UV-resistant housing, "
                "brushless motor, 12-month minimum durability target"
            )
        if issue_categories.get("packaging", 0) > 0:
            improvement_directions.append(
                "Reinforce packaging: double-wall box, molded pulp inserts, "
                "hardware count checklist enclosed"
            )
        if issue_categories.get("feature_request", 0) > 0:
            improvement_directions.append(
                "Add WiFi/app connectivity for remote monitoring and scheduling"
            )
        if issue_categories.get("price", 0) > 0:
            improvement_directions.append(
                "Hold price below $30 to maintain value perception while "
                "improving quality"
            )
        if issue_categories.get("shipping", 0) > 0:
            improvement_directions.append(
                "Use FBA for 2-day shipping; reduce box size to lower DIM weight"
            )
        if issue_categories.get("customer_service", 0) > 0:
            improvement_directions.append(
                "Offer 2-year warranty, 30-day returns, responsive support"
            )

        if not improvement_directions:
            improvement_directions.append(
                "No specific improvement directions — review data did not "
                "trigger any category rules."
            )

        # Source / confidence
        sources = {r.source for r in reviews}
        if "imported_csv" in sources or "user_input" in sources:
            agent_source = "imported_csv"
            confidence = "medium"
        else:
            agent_source = "mock_data"
            confidence = "low"

        output = ReviewOutput(
            review_count=review_count,
            sentiment_summary=sentiment_summary,
            issue_categories=issue_categories,
            positive_themes=positive_themes,
            negative_themes=negative_themes,
            feature_requests=feature_requests,
            quality_issues=quality_issues,
            packaging_issues=packaging_issues,
            product_improvement_directions=improvement_directions,
            source=agent_source,
            confidence=confidence,
        )

        assumptions.append(
            f"Classified {review_count} reviews using deterministic keyword "
            f"rules into 7 configured categories."
        )

        return AgentResult(
            agent_name=self.NAME,
            status="completed",
            input_summary={
                "review_count": review_count,
                "sentiment": sentiment_summary,
                "sources": sorted(sources),
            },
            output=output,
            warnings=warnings,
            assumptions=assumptions,
            source=agent_source,
            version=self.VERSION,
        )
