"""V3.1.6 — Product candidate agent and manual confirmation gate.

Splits the V3.0 product flow into two stages per spec section 九:

1. **ProductCandidateAgent** — runs *before* :class:`ProductAgent`.
   Reads the V3.1 analyzer results (multi-keyword, multi-category,
   brand, seller, search-position) and produces a list of
   :class:`ProductCandidate` records. Each candidate carries only
   market-evidence fields (opportunity score, top keyword, reference
   ASINs, suggested differentiation direction) — **never** a full
   product plan, supplier, or cost data.

2. **Confirmation gate** — every candidate starts in
   ``pending_review``. The user must call :func:`confirm_candidate`
   to move it to ``confirmed`` (or :func:`reject_candidate` to move
   it to ``rejected``). Only ``confirmed`` candidates may enter
   :class:`ProductAgent`.

When no candidate is confirmed:

* Market research report (V3.1.4) is still produced.
* Product candidate list is still produced.
* Product development plan is **not** produced — the caller receives
  a :class:`AgentResult` with ``status="pending_manual_confirmation"``.
* No supplier / cost / SKU data is generated.

This module never modifies :class:`ProductAgent` or
:mod:`src.core.agent` — V3.0 behaviour is preserved.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

from .models import AgentResult


NAME = "product_candidate"
VERSION = "product_candidate_agent_v3_1_6"


# ---------------------------------------------------------------------------
# Status enum (string-based so JSON / Excel can carry it directly)
# ---------------------------------------------------------------------------

STATUS_PENDING = "pending_review"
STATUS_CONFIRMED = "confirmed"
STATUS_REJECTED = "rejected"

ALLOWED_STATUSES = (STATUS_PENDING, STATUS_CONFIRMED, STATUS_REJECTED)


# ---------------------------------------------------------------------------
# ProductCandidate
# ---------------------------------------------------------------------------


@dataclass
class ProductCandidate:
    """A single product candidate awaiting manual confirmation.

    Fields are deliberately market-evidence only — no supplier, no
    cost, no SKU. The full product plan is produced by
    :class:`ProductAgent` only after this candidate is confirmed.

    Attributes:
        candidate_id: Stable identifier (e.g. ``"PC-0001"``).
        product_name: Working name, derived from the top keyword.
        top_keyword: Highest-opportunity keyword for this candidate.
        opportunity_score: 0-100, carried from the keyword analysis.
        reference_asins: Up to 5 ASINs whose listings informed the
            candidate. Source: ``imported_excel``.
        suggested_differentiation: One-line direction suggestion
            (e.g. "tool-free assembly"). Not a final spec.
        status: ``pending_review`` / ``confirmed`` / ``rejected``.
        reviewer: Name of the reviewer when confirmed/rejected.
        review_notes: Reason when rejected, or notes when confirmed.
        source_type: Always ``"agent_inference"`` for candidates.
        source_files: Files the evidence came from.
        confidence: ``medium`` (candidate evidence is inferential).
        requires_review: Always True — every candidate needs manual
            confirmation before entering ProductAgent.
    """

    candidate_id: str
    product_name: str
    top_keyword: str
    opportunity_score: Optional[Decimal] = None
    reference_asins: List[str] = field(default_factory=list)
    suggested_differentiation: str = ""
    status: str = STATUS_PENDING
    reviewer: str = ""
    review_notes: str = ""
    source_type: str = "agent_inference"
    source_files: List[str] = field(default_factory=list)
    confidence: str = "medium"
    requires_review: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "product_name": self.product_name,
            "top_keyword": self.top_keyword,
            "opportunity_score": str(self.opportunity_score) if self.opportunity_score is not None else None,
            "reference_asins": list(self.reference_asins),
            "suggested_differentiation": self.suggested_differentiation,
            "status": self.status,
            "reviewer": self.reviewer,
            "review_notes": self.review_notes,
            "source_type": self.source_type,
            "source_files": list(self.source_files),
            "confidence": self.confidence,
            "requires_review": self.requires_review,
        }


# ---------------------------------------------------------------------------
# ProductCandidateAgent
# ---------------------------------------------------------------------------


class ProductCandidateAgent:
    """Generate product candidates from V3.1 analyzer results.

    The agent reads the same analyzer output dict that
    :func:`build_market_research_report` consumes, and surfaces the
    top N keywords (by opportunity_score) as candidates. Each
    candidate is seeded with up to 5 reference ASINs from the
    normalised product list so the user can review the evidence
    before confirming.

    The agent never invents supplier data, cost data, or SKUs. It
    produces market-evidence candidates only.
    """

    NAME = NAME
    VERSION = VERSION

    def __init__(self, max_candidates: int = 5) -> None:
        if max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")
        self.max_candidates = max_candidates

    def run(
        self,
        analyzer_results: Dict[str, Any],
        *,
        confirmed_candidates: Optional[List[str]] = None,
    ) -> AgentResult:
        """Generate the candidate list.

        Args:
            analyzer_results: Dict with keys ``multi_keyword``,
                ``products`` (optional), ``brand`` (optional).
            confirmed_candidates: Optional list of candidate IDs the
                user has already confirmed in a prior run. These are
                marked ``confirmed`` on the new candidates so a
                subsequent :class:`ProductAgent` run may proceed
                without re-confirmation.

        Returns:
            :class:`AgentResult` with ``output={"candidates": [...]}``.
        """
        confirmed_set = set(confirmed_candidates or [])
        candidates = self.generate(analyzer_results)
        for c in candidates:
            if c.candidate_id in confirmed_set:
                c.status = STATUS_CONFIRMED
                c.reviewer = "prior_run"
        return AgentResult(
            agent_name=self.NAME,
            status="completed",
            output={"candidates": [c.to_dict() for c in candidates]},
            version=self.VERSION,
            source="agent_inference",
        )

    def generate(
        self,
        analyzer_results: Dict[str, Any],
    ) -> List[ProductCandidate]:
        """Build the candidate list from analyzer results."""
        kw_block = analyzer_results.get("multi_keyword") or {}
        rankings = kw_block.get("rankings") or []
        # Sort by opportunity_score (descending). Missing score → 0.
        def _score(r: Dict[str, Any]) -> Decimal:
            s = r.get("opportunity_score")
            if s is None:
                return Decimal("0")
            try:
                return Decimal(str(s))
            except Exception:
                return Decimal("0")
        rankings_sorted = sorted(rankings, key=_score, reverse=True)

        products = analyzer_results.get("products") or []
        if isinstance(products, dict):
            products = products.get("products", [])
        # Pre-pull reference ASINs grouped by keyword match so we
        # can seed each candidate without re-scanning the list.
        asin_pool = self._collect_asins(products)

        brand_block = analyzer_results.get("brand") or {}
        new_brand_opps = brand_block.get("new_brand_opportunities") or []

        candidates: List[ProductCandidate] = []
        for idx, r in enumerate(rankings_sorted[: self.max_candidates]):
            cid = f"PC-{idx + 1:04d}"
            keyword = r.get("keyword") or ""
            product_name = self._derive_product_name(keyword)
            ref_asins = self._pick_reference_asins(asin_pool, keyword, limit=5)
            diff = self._suggest_differentiation(
                keyword, new_brand_opps, rankings_sorted, idx
            )
            candidates.append(
                ProductCandidate(
                    candidate_id=cid,
                    product_name=product_name,
                    top_keyword=keyword,
                    opportunity_score=_score(r),
                    reference_asins=ref_asins,
                    suggested_differentiation=diff,
                    source_files=list(r.get("source_files") or []),
                )
            )
        return candidates

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_asins(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for p in products:
            if not isinstance(p, dict):
                continue
            asin = p.get("asin")
            if not asin or asin in seen:
                continue
            seen.add(asin)
            out.append(p)
        return out

    @staticmethod
    def _pick_reference_asins(
        asin_pool: List[Dict[str, Any]],
        keyword: str,
        limit: int,
    ) -> List[str]:
        if not asin_pool:
            return []
        # Prefer products whose title contains the keyword;
        # otherwise take the first ``limit`` from the pool.
        matches = [
            p for p in asin_pool
            if keyword and keyword.lower() in (p.get("title") or "").lower()
        ]
        picks = matches or asin_pool
        return [p.get("asin", "") for p in picks[:limit]]

    @staticmethod
    def _derive_product_name(keyword: str) -> str:
        if not keyword:
            return "Unnamed Candidate"
        return " ".join(part.capitalize() for part in keyword.split())

    @staticmethod
    def _suggest_differentiation(
        keyword: str,
        new_brand_opps: List[Dict[str, Any]],
        rankings_sorted: List[Dict[str, Any]],
        idx: int,
    ) -> str:
        if new_brand_opps:
            return "Leverage new-brand entry window; differentiate on materials and bundle"
        if idx == 0:
            return "Lead product: differentiate on quality and reviews"
        return "Follow-up product: differentiate on price or accessory bundle"


# ---------------------------------------------------------------------------
# Confirmation state machine
# ---------------------------------------------------------------------------


class CandidateNotfoundError(KeyError):
    """Raised when a candidate ID is not found in the registry."""


class CandidateStatusError(ValueError):
    """Raised when a status transition is invalid (e.g. confirming a
    rejected candidate)."""


def confirm_candidate(
    candidate: ProductCandidate,
    *,
    reviewer: str,
    notes: str = "",
) -> ProductCandidate:
    """Move ``candidate`` to ``confirmed``.

    A rejected candidate cannot be confirmed (call
    :func:`reset_candidate` first if you really need to).
    """
    if not reviewer:
        raise ValueError("reviewer must not be empty when confirming")
    if candidate.status == STATUS_REJECTED:
        raise CandidateStatusError(
            f"candidate {candidate.candidate_id} is rejected; "
            "reset before confirming"
        )
    candidate.status = STATUS_CONFIRMED
    candidate.reviewer = reviewer
    candidate.review_notes = notes
    candidate.requires_review = False
    return candidate


def reject_candidate(
    candidate: ProductCandidate,
    *,
    reviewer: str,
    reason: str,
) -> ProductCandidate:
    """Move ``candidate`` to ``rejected`` with a reason."""
    if not reviewer:
        raise ValueError("reviewer must not be empty when rejecting")
    if not reason:
        raise ValueError("reason must not be empty when rejecting")
    candidate.status = STATUS_REJECTED
    candidate.reviewer = reviewer
    candidate.review_notes = reason
    candidate.requires_review = False
    return candidate


def reset_candidate(candidate: ProductCandidate) -> ProductCandidate:
    """Return a candidate to ``pending_review`` (clears reviewer)."""
    candidate.status = STATUS_PENDING
    candidate.reviewer = ""
    candidate.review_notes = ""
    candidate.requires_review = True
    return candidate


def get_confirmed_candidates(
    candidates: List[ProductCandidate],
) -> List[ProductCandidate]:
    """Filter ``candidates`` to only those with ``status=confirmed``."""
    return [c for c in candidates if c.status == STATUS_CONFIRMED]


def can_proceed_to_product_agent(
    candidates: List[ProductCandidate],
) -> bool:
    """True when at least one candidate is confirmed.

    Used by the workflow gate before :class:`ProductAgent` runs.
    """
    return any(c.status == STATUS_CONFIRMED for c in candidates)


def gate_product_agent(
    candidates: List[ProductCandidate],
) -> AgentResult:
    """Return the AgentResult to emit when :class:`ProductAgent` is
    gated off (no confirmed candidates).

    Per spec: do not produce supplier/cost/SKU data; mark the plan
    ``pending_manual_confirmation``.
    """
    if can_proceed_to_product_agent(candidates):
        # Caller should not have invoked the gate; return a no-op
        # sentinel so the workflow can detect misuse.
        return AgentResult(
            agent_name=NAME,
            status="completed",
            output={"gate": "open", "confirmed_count": len(get_confirmed_candidates(candidates))},
            version=VERSION,
            source="calculated",
        )
    return AgentResult(
        agent_name=NAME,
        status="pending_manual_confirmation",
        output={
            "gate": "closed",
            "confirmed_count": 0,
            "pending_count": sum(1 for c in candidates if c.status == STATUS_PENDING),
            "rejected_count": sum(1 for c in candidates if c.status == STATUS_REJECTED),
            "candidates": [c.to_dict() for c in candidates],
        },
        warnings=[
            "No confirmed product candidates; product development plan "
            "is gated off pending manual confirmation per spec section 九.",
        ],
        version=VERSION,
        source="calculated",
    )


__all__ = [
    "ALLOWED_STATUSES",
    "CandidateStatusError",
    "NAME",
    "ProductCandidate",
    "ProductCandidateAgent",
    "STATUS_CONFIRMED",
    "STATUS_PENDING",
    "STATUS_REJECTED",
    "VERSION",
    "can_proceed_to_product_agent",
    "confirm_candidate",
    "gate_product_agent",
    "get_confirmed_candidates",
    "reject_candidate",
    "reset_candidate",
]
