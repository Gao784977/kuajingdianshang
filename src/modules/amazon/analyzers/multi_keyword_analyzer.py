"""Multi-keyword aggregator and opportunity scorer.

Consumes a list of :class:`KeywordMetric` records (typically after
:func:`src.modules.amazon.importers.normalizer.dedup_by_key` has
collapsed duplicates across files) and produces a ranked view that
downstream agents can use to pick which keywords to chase.

Opportunity score (0-100, higher is better) combines:

* search_volume (normalised 0-1 against the max in the input set)
* click_share (normalised 0-1)
* conversion_share (normalised 0-1)
* competition label — ``low`` boosts, ``high`` penalises, missing is
  neutral. ``medium`` is neutral.

When any input value is missing, that axis contributes 0 (so the
opportunity score is conservative). A keyword is "high potential"
when its opportunity_score is >= 70.

Source traceability: every ranking records the ``source_files`` the
keyword came from, and ``requires_review`` is True when competition
label is missing or the winning source type is low-confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..importers.normalized_models import KeywordMetric
from ..importers.normalizer import default_confidence, source_priority


def _d(value: Optional[Decimal]) -> Decimal:
    """Return ``value`` or ``Decimal(0)`` when None."""
    return value if value is not None else Decimal("0")


def _d_to_str(value: Optional[Decimal]) -> Optional[str]:
    return str(value) if value is not None else None


def _normalise(value: Optional[Decimal], max_value: Decimal) -> Decimal:
    """Scale ``value`` to 0-1 against ``max_value``; missing -> 0."""
    if value is None or max_value <= 0:
        return Decimal("0")
    return (value / max_value).quantize(Decimal("0.0001"))


_COMPETITION_WEIGHTS: Dict[str, Decimal] = {
    "low": Decimal("1.2"),     # 20% boost
    "medium": Decimal("1.0"),  # neutral
    "high": Decimal("0.7"),   # 30% penalty
    "very high": Decimal("0.5"),
}


@dataclass
class KeywordRanking:
    """A single keyword's ranked position across the input set."""

    keyword: str
    search_volume: Optional[Decimal]
    search_growth: Optional[Decimal]
    click_share: Optional[Decimal]
    conversion_share: Optional[Decimal]
    competition: str
    rank_by_search_volume: int
    rank_by_click_share: int
    rank_by_conversion_share: int
    opportunity_score: Optional[Decimal]
    source_files: List[str] = field(default_factory=list)
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "search_volume": _d_to_str(self.search_volume),
            "search_growth": _d_to_str(self.search_growth),
            "click_share": _d_to_str(self.click_share),
            "conversion_share": _d_to_str(self.conversion_share),
            "competition": self.competition,
            "rank_by_search_volume": self.rank_by_search_volume,
            "rank_by_click_share": self.rank_by_click_share,
            "rank_by_conversion_share": self.rank_by_conversion_share,
            "opportunity_score": _d_to_str(self.opportunity_score),
            "source_files": list(self.source_files),
            "requires_review": self.requires_review,
        }


@dataclass
class MultiKeywordAnalysis:
    """Output of :func:`analyze_keywords`."""

    rankings: List[KeywordRanking] = field(default_factory=list)
    total_keywords: int = 0
    total_search_volume: Optional[Decimal] = None
    avg_click_share: Optional[Decimal] = None
    avg_conversion_share: Optional[Decimal] = None
    high_potential_keywords: List[KeywordRanking] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rankings": [r.to_dict() for r in self.rankings],
            "total_keywords": self.total_keywords,
            "total_search_volume": _d_to_str(self.total_search_volume),
            "avg_click_share": _d_to_str(self.avg_click_share),
            "avg_conversion_share": _d_to_str(self.avg_conversion_share),
            "high_potential_keywords": [r.to_dict() for r in self.high_potential_keywords],
            "source_files": list(self.source_files),
            "requires_review": self.requires_review,
        }


# Threshold above which a keyword is flagged "high potential".
HIGH_POTENTIAL_THRESHOLD = Decimal("70")


def analyze_keywords(
    keyword_metrics: List[KeywordMetric],
    high_potential_threshold: Optional[Decimal] = None,
) -> MultiKeywordAnalysis:
    """Aggregate multiple keyword metrics into a ranked analysis.

    Args:
        keyword_metrics: One or more :class:`KeywordMetric` records
            (typically post-dedup). The function does not mutate its
            input.
        high_potential_threshold: Override the default 70-point cutoff
            for ``high_potential_keywords``. Useful for testing.

    Returns:
        A :class:`MultiKeywordAnalysis`. Always non-None; empty input
        produces an empty result with ``requires_review=False``.
    """
    if not keyword_metrics:
        return MultiKeywordAnalysis()

    threshold = (
        high_potential_threshold
        if high_potential_threshold is not None
        else HIGH_POTENTIAL_THRESHOLD
    )

    # Max values for normalisation.
    max_volume = max((_d(m.search_volume) for m in keyword_metrics), default=Decimal("0"))
    max_click = max((_d(m.click_share) for m in keyword_metrics), default=Decimal("0"))
    max_conv = max((_d(m.conversion_share) for m in keyword_metrics), default=Decimal("0"))

    # Compute opportunity scores first so ranking ties can use them.
    scored: List[tuple] = []  # (metric, opportunity_score)
    for m in keyword_metrics:
        vol_n = _normalise(m.search_volume, max_volume)
        click_n = _normalise(m.click_share, max_click)
        conv_n = _normalise(m.conversion_share, max_conv)
        # Each axis contributes 1/3 of the final score; scaled to 0-100.
        base_score = (vol_n + click_n + conv_n) / Decimal("3") * Decimal("100")
        comp_weight = _COMPETITION_WEIGHTS.get(
            (m.competition or "").strip().lower(), Decimal("1.0")
        )
        opportunity_score = (base_score * comp_weight).quantize(Decimal("0.01"))
        # Cap at 100 so the score stays on the documented 0-100 scale;
        # a low-competition keyword can still score 100 (never above).
        if opportunity_score > Decimal("100"):
            opportunity_score = Decimal("100")
        scored.append((m, opportunity_score))

    # Rankings (1-based; ties share the rank of the first member).
    def _rank(items, key_func, descending=True):
        sorted_items = sorted(items, key=key_func, reverse=descending)
        ranks: Dict[str, int] = {}
        last_key = None
        last_rank = 0
        for i, item in enumerate(sorted_items, start=1):
            k = key_func(item)
            if last_key is None or k != last_key:
                last_rank = i
                last_key = k
            ranks[item.keyword] = last_rank
        return ranks

    by_vol = _rank(
        keyword_metrics, lambda m: _d(m.search_volume), descending=True
    )
    by_click = _rank(
        keyword_metrics, lambda m: _d(m.click_share), descending=True
    )
    by_conv = _rank(
        keyword_metrics, lambda m: _d(m.conversion_share), descending=True
    )

    rankings: List[KeywordRanking] = []
    high_potential: List[KeywordRanking] = []
    source_files_set: set = set()
    any_review = False

    for metric, opportunity_score in scored:
        # Each KeywordMetric is a single record; its source_files list
        # has at most one entry (the Excel file it came from).
        files: List[str] = [metric.source_file] if metric.source_file else []
        # competition missing -> review flag.
        needs_review = not (metric.competition or "").strip()
        # Low-confidence source types also flag review.
        if source_priority(metric.source_type) >= source_priority("agent_inference"):
            needs_review = True
        if needs_review:
            any_review = True
        ranking = KeywordRanking(
            keyword=metric.keyword,
            search_volume=metric.search_volume,
            search_growth=metric.search_growth,
            click_share=metric.click_share,
            conversion_share=metric.conversion_share,
            competition=metric.competition,
            rank_by_search_volume=by_vol.get(metric.keyword, 1),
            rank_by_click_share=by_click.get(metric.keyword, 1),
            rank_by_conversion_share=by_conv.get(metric.keyword, 1),
            opportunity_score=opportunity_score,
            source_files=files,
            requires_review=needs_review,
        )
        rankings.append(ranking)
        if opportunity_score >= threshold:
            high_potential.append(ranking)
        if metric.source_file:
            source_files_set.add(metric.source_file)

    # Sort the public ranking by opportunity_score desc, then keyword.
    rankings.sort(
        key=lambda r: (-(_d(r.opportunity_score)), r.keyword)
    )
    high_potential.sort(
        key=lambda r: (-(_d(r.opportunity_score)), r.keyword)
    )

    # Aggregates.
    volumes = [_d(m.search_volume) for m in keyword_metrics]
    total_volume = sum(volumes) if volumes else None
    clicks = [m.click_share for m in keyword_metrics if m.click_share is not None]
    convs = [m.conversion_share for m in keyword_metrics if m.conversion_share is not None]
    avg_click = (
        sum(clicks) / Decimal(len(clicks)) if clicks else None
    )
    avg_conv = sum(convs) / Decimal(len(convs)) if convs else None

    return MultiKeywordAnalysis(
        rankings=rankings,
        total_keywords=len(keyword_metrics),
        total_search_volume=total_volume,
        avg_click_share=avg_click,
        avg_conversion_share=avg_conv,
        high_potential_keywords=high_potential,
        source_files=sorted(source_files_set),
        requires_review=any_review,
    )


__all__ = [
    "HIGH_POTENTIAL_THRESHOLD",
    "KeywordRanking",
    "MultiKeywordAnalysis",
    "analyze_keywords",
]
