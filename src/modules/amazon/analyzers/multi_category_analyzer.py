"""Cross-category comparison and opportunity scoring.

Consumes a list of :class:`CategoryMetric` records (typically after
:func:`src.modules.amazon.importers.normalizer.dedup_by_key`) and
ranks each category by market capacity, growth and competition. A
composite ``opportunity_score`` (0-100) combines the three so
downstream agents can pick the most attractive category.

Opportunity score weighting:

* 40% market capacity (``market_revenue`` normalised to 0-1 against
  the maximum across the input set)
* 40% growth (``growth`` normalised to 0-1 against the maximum,
  clamped to non-negative)
* 20% competition inverse (``low`` -> 1.0, ``medium`` -> 0.6,
  ``high`` -> 0.2, missing -> 0.5)

Missing values contribute 0 (conservative). A category is flagged
"fastest growing" when its growth is positive, and "least competitive"
when its competition label is ``low`` or ``medium``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..importers.normalized_models import CategoryMetric
from ..importers.normalizer import source_priority


def _d(value: Optional[Decimal]) -> Decimal:
    return value if value is not None else Decimal("0")


def _d_to_str(value: Optional[Decimal]) -> Optional[str]:
    return str(value) if value is not None else None


def _normalise(value: Optional[Decimal], max_value: Decimal) -> Decimal:
    if value is None or max_value <= 0:
        return Decimal("0")
    return (value / max_value).quantize(Decimal("0.0001"))


_COMPETITION_SCORE: Dict[str, Decimal] = {
    "low": Decimal("1.0"),
    "medium": Decimal("0.6"),
    "high": Decimal("0.2"),
    "very high": Decimal("0.1"),
}


@dataclass
class CategoryComparison:
    """A single category's ranked position across the input set."""

    category: str
    product_count: Optional[int]
    market_sales: Optional[Decimal]
    market_revenue: Optional[Decimal]
    average_price: Optional[Decimal]
    median_price: Optional[Decimal]
    growth: Optional[Decimal]
    competition: str
    market_capacity_rank: int
    growth_rank: int
    competition_rank: int
    opportunity_score: Optional[Decimal]
    source_files: List[str] = field(default_factory=list)
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "product_count": self.product_count,
            "market_sales": _d_to_str(self.market_sales),
            "market_revenue": _d_to_str(self.market_revenue),
            "average_price": _d_to_str(self.average_price),
            "median_price": _d_to_str(self.median_price),
            "growth": _d_to_str(self.growth),
            "competition": self.competition,
            "market_capacity_rank": self.market_capacity_rank,
            "growth_rank": self.growth_rank,
            "competition_rank": self.competition_rank,
            "opportunity_score": _d_to_str(self.opportunity_score),
            "source_files": list(self.source_files),
            "requires_review": self.requires_review,
        }


@dataclass
class MultiCategoryAnalysis:
    comparisons: List[CategoryComparison] = field(default_factory=list)
    total_categories: int = 0
    total_market_revenue: Optional[Decimal] = None
    fastest_growing: List[CategoryComparison] = field(default_factory=list)
    least_competitive: List[CategoryComparison] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "comparisons": [c.to_dict() for c in self.comparisons],
            "total_categories": self.total_categories,
            "total_market_revenue": _d_to_str(self.total_market_revenue),
            "fastest_growing": [c.to_dict() for c in self.fastest_growing],
            "least_competitive": [c.to_dict() for c in self.least_competitive],
            "source_files": list(self.source_files),
            "requires_review": self.requires_review,
        }


def _rank(
    items: List[CategoryMetric],
    key_func,
    descending: bool = True,
) -> Dict[str, int]:
    """1-based ranks; ties share the first member's rank."""
    sorted_items = sorted(items, key=key_func, reverse=descending)
    ranks: Dict[str, int] = {}
    last_key = None
    last_rank = 0
    for i, item in enumerate(sorted_items, start=1):
        k = key_func(item)
        if last_key is None or k != last_key:
            last_rank = i
            last_key = k
        ranks[item.category] = last_rank
    return ranks


def _competition_rank_key(m: CategoryMetric) -> int:
    """Lower rank number = less competitive (lower competition level)."""
    level = (m.competition or "").strip().lower()
    order = {"low": 1, "medium": 2, "high": 3, "very high": 4}
    return order.get(level, 5)  # missing -> worst


def analyze_categories(
    category_metrics: List[CategoryMetric],
) -> MultiCategoryAnalysis:
    """Aggregate multiple category metrics into a ranked comparison."""
    if not category_metrics:
        return MultiCategoryAnalysis()

    max_revenue = max(
        (_d(m.market_revenue) for m in category_metrics), default=Decimal("0")
    )
    max_growth = max(
        (_d(m.growth) for m in category_metrics), default=Decimal("0")
    )

    cap_ranks = _rank(
        category_metrics,
        lambda m: _d(m.market_revenue),
        descending=True,
    )
    growth_ranks = _rank(
        category_metrics,
        lambda m: _d(m.growth),
        descending=True,
    )
    comp_ranks = _rank(
        category_metrics,
        _competition_rank_key,
        descending=False,  # 1 (low competition) ranks first
    )

    comparisons: List[CategoryComparison] = []
    fastest_growing: List[CategoryComparison] = []
    least_competitive: List[CategoryComparison] = []
    source_files_set: set = set()
    any_review = False

    for metric in category_metrics:
        rev_n = _normalise(metric.market_revenue, max_revenue)
        growth_n = _normalise(
            metric.growth if metric.growth and metric.growth > 0 else None,
            max_growth,
        )
        comp_score = _COMPETITION_SCORE.get(
            (metric.competition or "").strip().lower(), Decimal("0.5")
        )
        opportunity_score = (
            (rev_n * Decimal("0.4")
             + growth_n * Decimal("0.4")
             + comp_score * Decimal("0.2")) * Decimal("100")
        ).quantize(Decimal("0.01"))

        files = [metric.source_file] if metric.source_file else []
        needs_review = not (metric.competition or "").strip()
        if source_priority(metric.source_type) >= source_priority("agent_inference"):
            needs_review = True
        if needs_review:
            any_review = True

        comparison = CategoryComparison(
            category=metric.category,
            product_count=metric.product_count,
            market_sales=metric.market_sales,
            market_revenue=metric.market_revenue,
            average_price=metric.average_price,
            median_price=metric.median_price,
            growth=metric.growth,
            competition=metric.competition,
            market_capacity_rank=cap_ranks.get(metric.category, 1),
            growth_rank=growth_ranks.get(metric.category, 1),
            competition_rank=comp_ranks.get(metric.category, 1),
            opportunity_score=opportunity_score,
            source_files=files,
            requires_review=needs_review,
        )
        comparisons.append(comparison)
        if metric.growth is not None and metric.growth > 0:
            fastest_growing.append(comparison)
        level = (metric.competition or "").strip().lower()
        if level in ("low", "medium"):
            least_competitive.append(comparison)
        if metric.source_file:
            source_files_set.add(metric.source_file)

    comparisons.sort(
        key=lambda c: (-(_d(c.opportunity_score)), c.category)
    )
    fastest_growing.sort(
        key=lambda c: (-(_d(c.growth)), c.category)
    )
    least_competitive.sort(
        key=lambda c: (c.competition_rank, c.category)
    )

    total_revenue = sum(
        (_d(m.market_revenue) for m in category_metrics),
        Decimal("0"),
    )

    return MultiCategoryAnalysis(
        comparisons=comparisons,
        total_categories=len(category_metrics),
        total_market_revenue=total_revenue if total_revenue else None,
        fastest_growing=fastest_growing,
        least_competitive=least_competitive,
        source_files=sorted(source_files_set),
        requires_review=any_review,
    )


__all__ = [
    "CategoryComparison",
    "MultiCategoryAnalysis",
    "analyze_categories",
]
