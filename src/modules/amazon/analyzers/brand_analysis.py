"""Brand concentration analysis.

Computes market concentration metrics (CR4, CR8, HHI) from a list of
:class:`BrandMetric` records, and — when an optional
:class:`AmazonProduct` list is supplied — surfaces new-brand
opportunities (brands whose listings are < 365 days old and have low
market share).

Share selection order:

1. ``market_share`` (already on the BrandMetric, expected 0-1).
2. ``monthly_revenue`` ratio (when market_share is missing across all
   brands).
3. ``monthly_sales`` ratio (when revenue is also missing).

HHI follows the US DOJ convention: sum of squared market shares
expressed on a 0-10000 scale. Concentration labels:

* HHI >= 2500  -> ``highly_concentrated``
* HHI 1500-2500 -> ``moderately_concentrated``
* HHI < 1500   -> ``unconcentrated``

When fewer than 4 brands are present, CR4 = CR8 = sum of all
available shares (still a valid concentration indicator).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..importers.normalized_models import AmazonProduct, BrandMetric
from ..importers.normalizer import source_priority


def _d(value: Optional[Decimal]) -> Decimal:
    return value if value is not None else Decimal("0")


def _d_to_str(value: Optional[Decimal]) -> Optional[str]:
    return str(value) if value is not None else None


def _quantize_share(value: Decimal) -> Decimal:
    """Clamp share to 0-1 and quantise to 4 decimal places."""
    if value < 0:
        return Decimal("0")
    if value > 1:
        return Decimal("1")
    return value.quantize(Decimal("0.0001"))


def _compute_hhi(shares: List[Decimal]) -> Decimal:
    """HHI on the 0-10000 DOJ scale. Shares are 0-1 fractions.

    Multiplies *before* quantising so we don't lose precision to
    2-decimal-place rounding (e.g. 0.365 must reach 3650.00, not
    3600.00).
    """
    if not shares:
        return Decimal("0")
    return (sum((s * s) for s in shares) * Decimal("10000")).quantize(
        Decimal("0.01")
    )


def _concentration_label(hhi: Decimal) -> str:
    if hhi >= Decimal("2500"):
        return "highly_concentrated"
    if hhi >= Decimal("1500"):
        return "moderately_concentrated"
    return "unconcentrated"


@dataclass
class BrandAnalysis:
    """Output of :func:`analyze_brands`."""

    total_brands: int = 0
    cr4: Optional[Decimal] = None
    cr8: Optional[Decimal] = None
    hhi: Optional[Decimal] = None
    market_concentration: str = "unconcentrated"
    top4_brands: List[Dict[str, Any]] = field(default_factory=list)
    top8_brands: List[Dict[str, Any]] = field(default_factory=list)
    new_brand_opportunities: List[Dict[str, Any]] = field(default_factory=list)
    share_basis: str = "market_share"
    source_files: List[str] = field(default_factory=list)
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_brands": self.total_brands,
            "cr4": _d_to_str(self.cr4),
            "cr8": _d_to_str(self.cr8),
            "hhi": _d_to_str(self.hhi),
            "market_concentration": self.market_concentration,
            "top4_brands": [dict(b) for b in self.top4_brands],
            "top8_brands": [dict(b) for b in self.top8_brands],
            "new_brand_opportunities": [dict(b) for b in self.new_brand_opportunities],
            "share_basis": self.share_basis,
            "source_files": list(self.source_files),
            "requires_review": self.requires_review,
        }


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _brand_share(
    metric: BrandMetric,
    basis: str,
    total_revenue: Decimal,
    total_sales: Decimal,
) -> Decimal:
    """Return a 0-1 share for ``metric`` using the chosen basis."""
    if basis == "market_share":
        if metric.market_share is not None:
            return _quantize_share(metric.market_share)
        return Decimal("0")
    if basis == "monthly_revenue":
        if total_revenue <= 0 or metric.monthly_revenue is None:
            return Decimal("0")
        return _quantize_share(metric.monthly_revenue / total_revenue)
    if basis == "monthly_sales":
        if total_revenue <= 0 or metric.monthly_sales is None:
            # monthly_sales uses total_sales, not total_revenue.
            return Decimal("0")
        return _quantize_share(metric.monthly_sales / total_sales)
    return Decimal("0")


def analyze_brands(
    brand_metrics: List[BrandMetric],
    products: Optional[List[AmazonProduct]] = None,
    today: Optional[date] = None,
) -> BrandAnalysis:
    """Compute brand concentration and surface new-brand opportunities.

    Args:
        brand_metrics: List of :class:`BrandMetric`. Duplicates are
            expected to have been collapsed by
            :func:`src.modules.amazon.importers.normalizer.dedup_by_key`
            already; this function does not re-dedup.
        products: Optional product-level records used to identify
            recently-launched brands. When omitted, the
            ``new_brand_opportunities`` list is empty.
        today: Override "now" for deterministic testing. Defaults to
            :func:`date.today`.
    """
    if not brand_metrics:
        return BrandAnalysis()

    today = today or date.today()

    # Determine share basis. Prefer market_share when present on
    # *all* records; fall back to monthly_revenue, then monthly_sales.
    has_market_share = all(m.market_share is not None for m in brand_metrics)
    has_revenue = any(m.monthly_revenue is not None for m in brand_metrics)
    has_sales = any(m.monthly_sales is not None for m in brand_metrics)

    if has_market_share:
        basis = "market_share"
    elif has_revenue:
        basis = "monthly_revenue"
    elif has_sales:
        basis = "monthly_sales"
    else:
        # No usable share axis — nothing meaningful to compute.
        return BrandAnalysis(
            total_brands=len(brand_metrics),
            share_basis="none",
            requires_review=True,
            source_files=sorted(
                {m.source_file for m in brand_metrics if m.source_file}
            ),
        )

    total_revenue = sum((_d(m.monthly_revenue) for m in brand_metrics), Decimal("0"))
    total_sales = sum((_d(m.monthly_sales) for m in brand_metrics), Decimal("0"))

    # (brand, share, metric) sorted by share desc.
    ranked: List[tuple] = []
    source_files_set: set = set()
    any_review = False
    for m in brand_metrics:
        share = _brand_share(m, basis, total_revenue, total_sales)
        ranked.append((m.brand or "", share, m))
        if m.source_file:
            source_files_set.add(m.source_file)
        if source_priority(m.source_type) >= source_priority("agent_inference"):
            any_review = True
        if basis == "market_share" and m.market_share is None:
            any_review = True

    ranked.sort(key=lambda t: (-t[1], t[0]))

    shares = [r[1] for r in ranked]
    cr4 = sum(shares[:4]) if shares else Decimal("0")
    cr8 = sum(shares[:8]) if shares else Decimal("0")
    hhi = _compute_hhi(shares)

    def _brand_dict(brand: str, share: Decimal, metric: BrandMetric) -> Dict[str, Any]:
        return {
            "brand": brand,
            "market_share": _d_to_str(share),
            "monthly_sales": _d_to_str(metric.monthly_sales),
            "monthly_revenue": _d_to_str(metric.monthly_revenue),
            "average_price": _d_to_str(metric.average_price),
            "click_share": _d_to_str(metric.click_share),
            "conversion_share": _d_to_str(metric.conversion_share),
            "source_file": metric.source_file,
            "source_sheet": metric.source_sheet,
        }

    top4 = [_brand_dict(b, s, m) for b, s, m in ranked[:4]]
    top8 = [_brand_dict(b, s, m) for b, s, m in ranked[:8]]

    # New-brand opportunities: brands whose earliest listing is < 365
    # days old AND whose market share is in the bottom half.
    opportunities: List[Dict[str, Any]] = []
    if products:
        # Group products by brand, find earliest launch_date per brand.
        brand_launch: Dict[str, Optional[date]] = {}
        for p in products:
            if not p.brand:
                continue
            launch = _parse_date(p.launch_date)
            current = brand_launch.get(p.brand)
            if launch is not None and (current is None or launch < current):
                brand_launch[p.brand] = launch

        # Bottom-half brands (by share).
        median_share = (
            shares[len(shares) // 2] if shares else Decimal("0")
        )
        for brand, share, metric in ranked:
            launch = brand_launch.get(brand)
            if launch is None:
                continue
            age_days = (today - launch).days
            if age_days < 0:
                age_days = 0
            if age_days <= 365 and share <= median_share:
                opportunities.append(
                    {
                        "brand": brand,
                        "market_share": _d_to_str(share),
                        "listing_age_days": age_days,
                        "launch_date": launch.isoformat(),
                        "monthly_revenue": _d_to_str(metric.monthly_revenue),
                        "source_file": metric.source_file,
                    }
                )
        opportunities.sort(key=lambda d: d.get("listing_age_days", 0))

    return BrandAnalysis(
        total_brands=len(brand_metrics),
        cr4=cr4.quantize(Decimal("0.0001")) if cr4 else None,
        cr8=cr8.quantize(Decimal("0.0001")) if cr8 else None,
        hhi=hhi,
        market_concentration=_concentration_label(hhi),
        top4_brands=top4,
        top8_brands=top8,
        new_brand_opportunities=opportunities,
        share_basis=basis,
        source_files=sorted(source_files_set),
        requires_review=any_review,
    )


__all__ = [
    "BrandAnalysis",
    "analyze_brands",
]
