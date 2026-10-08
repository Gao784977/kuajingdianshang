"""Seller concentration and fulfillment analysis.

Computes:

* CR4 / CR8 / HHI from seller market shares (or revenue fallback).
* FBA vs FBM ratio — derived from :class:`AmazonProduct.fulfillment_method`
  when a product list is supplied. Values are normalised case-
  insensitively: ``FBA`` / ``AMZ`` / ``AMAZON`` count as FBA;
  ``FBM`` / ``MFN`` / ``MERCHANT`` / ``3P`` count as FBM.
* Seller geography — counts of :class:`AmazonProduct.seller_location`
  values (raw strings; downstream code is responsible for country
  normalisation).

Shares follow the same fallback order as :mod:`brand_analysis`:
``market_share`` -> ``monthly_revenue`` -> ``monthly_sales``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..importers.normalized_models import AmazonProduct, SellerMetric
from ..importers.normalizer import source_priority


def _d(value: Optional[Decimal]) -> Decimal:
    return value if value is not None else Decimal("0")


def _d_to_str(value: Optional[Decimal]) -> Optional[str]:
    return str(value) if value is not None else None


def _quantize_share(value: Decimal) -> Decimal:
    if value < 0:
        return Decimal("0")
    if value > 1:
        return Decimal("1")
    return value.quantize(Decimal("0.0001"))


def _compute_hhi(shares: List[Decimal]) -> Decimal:
    if not shares:
        return Decimal("0")
    # Multiply before quantising to avoid 2-dp rounding loss
    # (see brand_analysis._compute_hhi for the rationale).
    return (sum((s * s) for s in shares) * Decimal("10000")).quantize(
        Decimal("0.01")
    )


_FBA_TOKENS = {"fba", "amz", "amazon", "prime", "amazon fulfilled"}
_FBM_TOKENS = {"fbm", "mfn", "merchant", "merchant fulfilled", "3p", "seller"}


def _classify_fulfillment(value: Optional[str]) -> str:
    """Normalise a fulfillment string into ``fba``/``fbm``/``unknown``."""
    if not value:
        return "unknown"
    token = value.strip().lower()
    if not token:
        return "unknown"
    # Exact-token match first.
    if token in _FBA_TOKENS:
        return "fba"
    if token in _FBM_TOKENS:
        return "fbm"
    # Substring fallback (e.g. "FBA (Amazon)").
    if any(t in token for t in _FBA_TOKENS if len(t) > 2):
        return "fba"
    if any(t in token for t in _FBM_TOKENS if len(t) > 2):
        return "fbm"
    return "unknown"


@dataclass
class SellerAnalysis:
    """Output of :func:`analyze_sellers`."""

    total_sellers: int = 0
    cr4: Optional[Decimal] = None
    cr8: Optional[Decimal] = None
    hhi: Optional[Decimal] = None
    market_concentration: str = "unconcentrated"
    top4_sellers: List[Dict[str, Any]] = field(default_factory=list)
    top8_sellers: List[Dict[str, Any]] = field(default_factory=list)
    fba_count: int = 0
    fbm_count: int = 0
    unknown_fulfillment_count: int = 0
    fba_ratio: Optional[Decimal] = None
    seller_locations: Dict[str, int] = field(default_factory=dict)
    share_basis: str = "market_share"
    source_files: List[str] = field(default_factory=list)
    requires_review: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_sellers": self.total_sellers,
            "cr4": _d_to_str(self.cr4),
            "cr8": _d_to_str(self.cr8),
            "hhi": _d_to_str(self.hhi),
            "market_concentration": self.market_concentration,
            "top4_sellers": [dict(s) for s in self.top4_sellers],
            "top8_sellers": [dict(s) for s in self.top8_sellers],
            "fba_count": self.fba_count,
            "fbm_count": self.fbm_count,
            "unknown_fulfillment_count": self.unknown_fulfillment_count,
            "fba_ratio": _d_to_str(self.fba_ratio),
            "seller_locations": dict(self.seller_locations),
            "share_basis": self.share_basis,
            "source_files": list(self.source_files),
            "requires_review": self.requires_review,
        }


def _concentration_label(hhi: Decimal) -> str:
    if hhi >= Decimal("2500"):
        return "highly_concentrated"
    if hhi >= Decimal("1500"):
        return "moderately_concentrated"
    return "unconcentrated"


def _seller_share(
    metric: SellerMetric,
    basis: str,
    total_revenue: Decimal,
    total_sales: Decimal,
) -> Decimal:
    if basis == "market_share":
        if metric.market_share is not None:
            return _quantize_share(metric.market_share)
        return Decimal("0")
    if basis == "monthly_revenue":
        if total_revenue <= 0 or metric.monthly_revenue is None:
            return Decimal("0")
        return _quantize_share(metric.monthly_revenue / total_revenue)
    if basis == "monthly_sales":
        if total_sales <= 0 or metric.monthly_sales is None:
            return Decimal("0")
        return _quantize_share(metric.monthly_sales / total_sales)
    return Decimal("0")


def _seller_dict(seller: str, share: Decimal, metric: SellerMetric) -> Dict[str, Any]:
    return {
        "seller": seller,
        "market_share": _d_to_str(share),
        "monthly_sales": _d_to_str(metric.monthly_sales),
        "monthly_revenue": _d_to_str(metric.monthly_revenue),
        "annual_sales": _d_to_str(metric.annual_sales),
        "annual_revenue": _d_to_str(metric.annual_revenue),
        "average_price": _d_to_str(metric.average_price),
        "source_file": metric.source_file,
        "source_sheet": metric.source_sheet,
    }


def analyze_sellers(
    seller_metrics: List[SellerMetric],
    products: Optional[List[AmazonProduct]] = None,
) -> SellerAnalysis:
    """Compute seller concentration + fulfillment distribution.

    Args:
        seller_metrics: List of :class:`SellerMetric` records
            (typically post-dedup).
        products: Optional product rows used to compute FBA/FBM ratio
            and seller geography. When omitted, those fields are
            zero/empty.
    """
    if not seller_metrics:
        # Still attempt fulfillment analysis if products are provided.
        return _analyze_fulfillment_only(products) if products else SellerAnalysis()

    has_market_share = all(m.market_share is not None for m in seller_metrics)
    has_revenue = any(m.monthly_revenue is not None for m in seller_metrics)
    has_sales = any(m.monthly_sales is not None for m in seller_metrics)

    if has_market_share:
        basis = "market_share"
    elif has_revenue:
        basis = "monthly_revenue"
    elif has_sales:
        basis = "monthly_sales"
    else:
        return SellerAnalysis(
            total_sellers=len(seller_metrics),
            share_basis="none",
            requires_review=True,
            source_files=sorted(
                {m.source_file for m in seller_metrics if m.source_file}
            ),
        )

    total_revenue = sum((_d(m.monthly_revenue) for m in seller_metrics), Decimal("0"))
    total_sales = sum((_d(m.monthly_sales) for m in seller_metrics), Decimal("0"))

    ranked: List[tuple] = []
    source_files_set: set = set()
    any_review = False
    for m in seller_metrics:
        share = _seller_share(m, basis, total_revenue, total_sales)
        ranked.append((m.seller or "", share, m))
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

    top4 = [_seller_dict(s, sh, m) for s, sh, m in ranked[:4]]
    top8 = [_seller_dict(s, sh, m) for s, sh, m in ranked[:8]]

    # Fulfillment + geography from products.
    fba_count = 0
    fbm_count = 0
    unknown_count = 0
    locations: Dict[str, int] = {}
    if products:
        for p in products:
            kind = _classify_fulfillment(p.fulfillment_method)
            if kind == "fba":
                fba_count += 1
            elif kind == "fbm":
                fbm_count += 1
            else:
                unknown_count += 1
            if p.seller_location:
                loc = p.seller_location.strip()
                if loc:
                    locations[loc] = locations.get(loc, 0) + 1

    fulfillment_total = fba_count + fbm_count + unknown_count
    if fulfillment_total > 0:
        fba_ratio = (Decimal(fba_count) / Decimal(fulfillment_total)).quantize(
            Decimal("0.0001")
        )
    else:
        fba_ratio = None

    return SellerAnalysis(
        total_sellers=len(seller_metrics),
        cr4=cr4.quantize(Decimal("0.0001")) if cr4 else None,
        cr8=cr8.quantize(Decimal("0.0001")) if cr8 else None,
        hhi=hhi,
        market_concentration=_concentration_label(hhi),
        top4_sellers=top4,
        top8_sellers=top8,
        fba_count=fba_count,
        fbm_count=fbm_count,
        unknown_fulfillment_count=unknown_count,
        fba_ratio=fba_ratio,
        seller_locations=dict(sorted(locations.items())),
        share_basis=basis,
        source_files=sorted(source_files_set),
        requires_review=any_review,
    )


def _analyze_fulfillment_only(
    products: Optional[List[AmazonProduct]],
) -> SellerAnalysis:
    """Build a partial :class:`SellerAnalysis` from product rows alone.

    Used when no seller metrics were provided but products are. CR4 /
    HHI are left as ``None``; only fulfillment + geography are filled.
    """
    result = SellerAnalysis(share_basis="none", requires_review=True)
    if not products:
        return result
    fba_count = 0
    fbm_count = 0
    unknown_count = 0
    locations: Dict[str, int] = {}
    source_files_set: set = set()
    for p in products:
        kind = _classify_fulfillment(p.fulfillment_method)
        if kind == "fba":
            fba_count += 1
        elif kind == "fbm":
            fbm_count += 1
        else:
            unknown_count += 1
        if p.seller_location:
            loc = p.seller_location.strip()
            if loc:
                locations[loc] = locations.get(loc, 0) + 1
        if p.source_file:
            source_files_set.add(p.source_file)
    total = fba_count + fbm_count + unknown_count
    result.fba_count = fba_count
    result.fbm_count = fbm_count
    result.unknown_fulfillment_count = unknown_count
    result.seller_locations = dict(sorted(locations.items()))
    result.source_files = sorted(source_files_set)
    if total > 0:
        result.fba_ratio = (Decimal(fba_count) / Decimal(total)).quantize(
            Decimal("0.0001")
        )
    return result


__all__ = [
    "SellerAnalysis",
    "analyze_sellers",
]
