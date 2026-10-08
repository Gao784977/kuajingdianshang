"""Search-position analysis — keyword x ASIN matrix.

Consumes the *non-deduplicated* :class:`AmazonSearchAppearance`
list (as returned by
:func:`src.modules.amazon.importers.normalizer.normalize_search_appearances`)
and produces:

* Per-keyword matrix (unique ASINs, sponsored vs organic counts,
  page distribution).
* Aggregate counts (total appearances, sponsored ratio, average
  ASINs per keyword).
* Top keywords by sponsored appearances (heaviest ad spend).

The input list is **never** deduplicated here. The whole point of
keeping every appearance row is to preserve the multi-keyword /
multi-placement / multi-page signal that Amazon reports natively.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from ..importers.normalized_models import AmazonSearchAppearance
from ..importers.normalizer import source_priority


def _d(value: Optional[Decimal]) -> Decimal:
    return value if value is not None else Decimal("0")


def _d_to_str(value: Optional[Decimal]) -> Optional[str]:
    return str(value) if value is not None else None


@dataclass
class SearchPositionMatrix:
    """Per-keyword search-appearance aggregate."""

    keyword: str
    unique_asin_count: int = 0
    total_appearances: int = 0
    sponsored_count: int = 0
    organic_count: int = 0
    unknown_placement_count: int = 0
    page_distribution: Dict[int, int] = field(default_factory=dict)
    # Top 10 (by frequency) ASINs under this keyword.
    top_asins: List[Dict[str, Any]] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "unique_asin_count": self.unique_asin_count,
            "total_appearances": self.total_appearances,
            "sponsored_count": self.sponsored_count,
            "organic_count": self.organic_count,
            "unknown_placement_count": self.unknown_placement_count,
            "page_distribution": dict(self.page_distribution),
            "top_asins": [dict(a) for a in self.top_asins],
            "source_files": list(self.source_files),
        }


@dataclass
class SearchPositionAnalysis:
    """Output of :func:`analyze_search_positions`."""

    matrix: List[SearchPositionMatrix] = field(default_factory=list)
    total_appearances: int = 0
    total_sponsored: int = 0
    total_organic: int = 0
    total_unknown_placement: int = 0
    sponsored_ratio: Optional[Decimal] = None
    keyword_count: int = 0
    unique_asin_count: int = 0
    avg_asin_per_keyword: Optional[Decimal] = None
    top_keywords_by_sponsored: List[Dict[str, Any]] = field(default_factory=list)
    top_keywords_by_organic: List[Dict[str, Any]] = field(default_factory=list)
    source_files: List[str] = field(default_factory=list)
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "matrix": [m.to_dict() for m in self.matrix],
            "total_appearances": self.total_appearances,
            "total_sponsored": self.total_sponsored,
            "total_organic": self.total_organic,
            "total_unknown_placement": self.total_unknown_placement,
            "sponsored_ratio": _d_to_str(self.sponsored_ratio),
            "keyword_count": self.keyword_count,
            "unique_asin_count": self.unique_asin_count,
            "avg_asin_per_keyword": _d_to_str(self.avg_asin_per_keyword),
            "top_keywords_by_sponsored": [dict(k) for k in self.top_keywords_by_sponsored],
            "top_keywords_by_organic": [dict(k) for k in self.top_keywords_by_organic],
            "source_files": list(self.source_files),
            "requires_review": self.requires_review,
        }


def _is_sponsored(a: AmazonSearchAppearance) -> bool:
    if a.placement_type == "sponsored":
        return True
    if a.is_sponsored:
        return True
    detail = (a.placement_detail or "").lower()
    if "sponsor" in detail or "ad" in detail:
        return True
    return False


def _is_organic(a: AmazonSearchAppearance) -> bool:
    if a.placement_type == "organic":
        return True
    if a.is_organic:
        return True
    return False


def analyze_search_positions(
    appearances: List[AmazonSearchAppearance],
) -> SearchPositionAnalysis:
    """Build the keyword x ASIN search-position matrix.

    Args:
        appearances: The full, non-deduplicated search-appearance
            list. Pass-through from
            :func:`normalize_search_appearances` is the expected
            source.

    Returns:
        Always non-None; empty input produces an empty analysis with
        all counts at 0 and ``sponsored_ratio=None``.
    """
    if not appearances:
        return SearchPositionAnalysis()

    # Group by keyword.
    by_keyword: Dict[str, List[AmazonSearchAppearance]] = {}
    source_files_set: set = set()
    any_review = False
    all_asins: set = set()
    for a in appearances:
        key = a.keyword or ""
        by_keyword.setdefault(key, []).append(a)
        if a.asin:
            all_asins.add(a.asin)
        if a.source_file:
            source_files_set.add(a.source_file)
        if source_priority(a.source_type) >= source_priority("agent_inference"):
            any_review = True

    matrix: List[SearchPositionMatrix] = []
    top_sponsored: List[Dict[str, Any]] = []
    top_organic: List[Dict[str, Any]] = []

    total_sponsored = 0
    total_organic = 0
    total_unknown = 0

    for keyword, rows in by_keyword.items():
        asin_counts: Dict[str, int] = {}
        sponsored = 0
        organic = 0
        unknown = 0
        pages: Dict[int, int] = {}
        keyword_sources: set = set()
        for a in rows:
            if a.asin:
                asin_counts[a.asin] = asin_counts.get(a.asin, 0) + 1
            if _is_sponsored(a):
                sponsored += 1
            elif _is_organic(a):
                organic += 1
            else:
                unknown += 1
            if a.page_number is not None:
                pages[a.page_number] = pages.get(a.page_number, 0) + 1
            if a.source_file:
                keyword_sources.add(a.source_file)

        top_asins = [
            {"asin": asin, "appearance_count": cnt}
            for asin, cnt in sorted(
                asin_counts.items(), key=lambda kv: (-kv[1], kv[0])
            )[:10]
        ]
        entry = SearchPositionMatrix(
            keyword=keyword,
            unique_asin_count=len(asin_counts),
            total_appearances=len(rows),
            sponsored_count=sponsored,
            organic_count=organic,
            unknown_placement_count=unknown,
            page_distribution=dict(sorted(pages.items())),
            top_asins=top_asins,
            source_files=sorted(keyword_sources),
        )
        matrix.append(entry)
        total_sponsored += sponsored
        total_organic += organic
        total_unknown += len(rows) - sponsored - organic

        if sponsored > 0:
            top_sponsored.append(
                {
                    "keyword": keyword,
                    "sponsored_count": sponsored,
                    "total_appearances": len(rows),
                }
            )
        if organic > 0:
            top_organic.append(
                {
                    "keyword": keyword,
                    "organic_count": organic,
                    "total_appearances": len(rows),
                }
            )

    matrix.sort(key=lambda m: (-m.total_appearances, m.keyword))
    top_sponsored.sort(
        key=lambda d: (-d["sponsored_count"], d["keyword"])
    )
    top_organic.sort(
        key=lambda d: (-d["organic_count"], d["keyword"])
    )

    total_appearances = len(appearances)
    classified = total_sponsored + total_organic
    sponsored_ratio = (
        (Decimal(total_sponsored) / Decimal(classified)).quantize(Decimal("0.0001"))
        if classified > 0
        else None
    )
    avg_asin_per_keyword = (
        (Decimal(sum(m.unique_asin_count for m in matrix))
         / Decimal(len(matrix))).quantize(Decimal("0.0001"))
        if matrix
        else None
    )

    return SearchPositionAnalysis(
        matrix=matrix,
        total_appearances=total_appearances,
        total_sponsored=total_sponsored,
        total_organic=total_organic,
        total_unknown_placement=total_unknown,
        sponsored_ratio=sponsored_ratio,
        keyword_count=len(matrix),
        unique_asin_count=len(all_asins),
        avg_asin_per_keyword=avg_asin_per_keyword,
        top_keywords_by_sponsored=top_sponsored[:10],
        top_keywords_by_organic=top_organic[:10],
        source_files=sorted(source_files_set),
        requires_review=any_review,
    )


__all__ = [
    "SearchPositionAnalysis",
    "SearchPositionMatrix",
    "analyze_search_positions",
]
