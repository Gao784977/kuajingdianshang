"""V3.1.6 demo — product candidate agent and confirmation gate.

Shows the two-stage product flow per spec section 九:

1. ProductCandidateAgent generates a candidate list (market evidence
   only — no supplier/cost/SKU data).
2. Without confirmation, the product-agent gate stays closed and
   returns ``status="pending_manual_confirmation"``.
3. Confirming one candidate opens the gate so ProductAgent may run.
4. Rejecting a candidate keeps the gate closed.

Run: ``python -B examples/v316_product_candidate_demo.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from modules.amazon.product_candidate_agent import (  # noqa: E402
    ProductCandidate,
    ProductCandidateAgent,
    STATUS_CONFIRMED,
    STATUS_PENDING,
    STATUS_REJECTED,
    can_proceed_to_product_agent,
    confirm_candidate,
    gate_product_agent,
    reject_candidate,
)


def _sample_analyzer_results() -> dict:
    return {
        "multi_keyword": {
            "rankings": [
                {
                    "keyword": "chicken saddle",
                    "opportunity_score": "78.5",
                    "source_files": ["products_export.xlsx"],
                },
                {
                    "keyword": "chicken coop",
                    "opportunity_score": "65.0",
                    "source_files": ["products_export.xlsx"],
                },
                {
                    "keyword": "chicken feeder",
                    "opportunity_score": "52.0",
                    "source_files": ["products_export.xlsx"],
                },
            ],
        },
        "products": [
            {"asin": "B0DNVW368Z", "title": "Mother Hen Chicken Saddle Protector"},
            {"asin": "B0CS9LV4RD", "title": "PETSFIT Chicken Roost"},
            {"asin": "B0GKV239MP", "title": "Esmorah Chicken Saddle"},
        ],
        "brand": {
            "new_brand_opportunities": [{"brand": "NewBrand"}],
        },
    }


def main() -> int:
    print("=" * 70)
    print("V3.1.6 demo — product candidate agent + confirmation gate")
    print("=" * 70)

    # Step 1: generate candidates
    print("\n[1/4] Generate product candidates from analyzer results")
    agent = ProductCandidateAgent(max_candidates=3)
    result = agent.run(_sample_analyzer_results())
    candidates = [
        ProductCandidate(
            candidate_id=c["candidate_id"],
            product_name=c["product_name"],
            top_keyword=c["top_keyword"],
            opportunity_score=__import__("decimal").Decimal(c["opportunity_score"] or "0"),
            reference_asins=c["reference_asins"],
            suggested_differentiation=c["suggested_differentiation"],
            source_files=c["source_files"],
        )
        for c in result.output["candidates"]
    ]
    print(f"      generated {len(candidates)} candidates:")
    for c in candidates:
        print(
            f"        - {c.candidate_id}: {c.product_name}\n"
            f"          keyword={c.top_keyword}, score={c.opportunity_score}, "
            f"status={c.status}\n"
            f"          ref_asins={c.reference_asins}\n"
            f"          diff_direction={c.suggested_differentiation}"
        )

    # Step 2: gate closed (no confirmed candidates)
    print("\n[2/4] Gate check with NO confirmed candidates")
    gate = gate_product_agent(candidates)
    print(f"      status={gate.status}")
    print(f"      gate={gate.output['gate']}")
    print(f"      confirmed={gate.output['confirmed_count']}, "
          f"pending={gate.output['pending_count']}")
    print(f"      can_proceed_to_product_agent={can_proceed_to_product_agent(candidates)}")

    # Step 3: confirm one candidate
    print("\n[3/4] Confirm candidate PC-0001")
    confirm_candidate(candidates[0], reviewer="product_manager", notes="approved for development")
    print(f"      {candidates[0].candidate_id} status={candidates[0].status}, "
          f"reviewer={candidates[0].reviewer}")
    gate = gate_product_agent(candidates)
    print(f"      gate={gate.output['gate']}, confirmed={gate.output['confirmed_count']}")
    print(f"      can_proceed_to_product_agent={can_proceed_to_product_agent(candidates)}")

    # Step 4: reject a candidate
    print("\n[4/4] Reject candidate PC-0002")
    reject_candidate(candidates[1], reviewer="product_manager", reason="market too competitive")
    print(f"      {candidates[1].candidate_id} status={candidates[1].status}, "
          f"reason={candidates[1].review_notes}")
    print(f"      statuses: {[c.status for c in candidates]}")

    print("\n" + "=" * 70)
    print("V3.1.6 demo complete.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
