"""Tests for V3.1.6 :mod:`src.modules.amazon.product_candidate_agent`.

Covers spec section 十一 candidate-confirmation test cases:

* ProductCandidateAgent generates candidates from analyzer results
* Every candidate starts in ``pending_review``
* Candidates carry market-evidence fields only — no supplier/cost/SKU
* Unconfirmed candidates do not enter product development
* Confirmed candidates unlock the product agent gate
* Rejected candidates keep the gate closed
* ``gate_product_agent`` returns ``pending_manual_confirmation``
  when no candidate is confirmed
* Candidate state machine: confirm / reject / reset and invalid
  transitions raise
"""

from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _THIS_DIR.parent
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from modules.amazon.models import AgentResult  # noqa: E402
from modules.amazon.product_candidate_agent import (  # noqa: E402
    ALLOWED_STATUSES,
    CandidateStatusError,
    ProductCandidate,
    ProductCandidateAgent,
    STATUS_CONFIRMED,
    STATUS_PENDING,
    STATUS_REJECTED,
    can_proceed_to_product_agent,
    confirm_candidate,
    gate_product_agent,
    get_confirmed_candidates,
    reject_candidate,
    reset_candidate,
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
            {"asin": "B0ABC12345", "title": "Generic Chicken Feeder"},
        ],
        "brand": {
            "new_brand_opportunities": [{"brand": "NewBrand"}],
        },
    }


class TestProductCandidateModel(unittest.TestCase):
    """Tests for the :class:`ProductCandidate` data class."""

    def test_default_status_is_pending(self):
        c = ProductCandidate(
            candidate_id="PC-0001",
            product_name="Test",
            top_keyword="test",
        )
        self.assertEqual(c.status, STATUS_PENDING)

    def test_requires_review_default_true(self):
        c = ProductCandidate(candidate_id="PC-0001", product_name="T", top_keyword="t")
        self.assertTrue(c.requires_review)

    def test_source_type_is_agent_inference(self):
        c = ProductCandidate(candidate_id="PC-0001", product_name="T", top_keyword="t")
        self.assertEqual(c.source_type, "agent_inference")

    def test_to_dict_round_trip(self):
        c = ProductCandidate(
            candidate_id="PC-0001",
            product_name="Chicken Saddle",
            top_keyword="chicken saddle",
            opportunity_score=Decimal("78.5"),
            reference_asins=["B0DNVW368Z"],
            source_files=["products.xlsx"],
        )
        d = c.to_dict()
        self.assertEqual(d["candidate_id"], "PC-0001")
        self.assertEqual(d["opportunity_score"], "78.5")
        self.assertEqual(d["status"], STATUS_PENDING)
        self.assertTrue(d["requires_review"])

    def test_no_supplier_or_cost_fields(self):
        c = ProductCandidate(candidate_id="PC-0001", product_name="T", top_keyword="t")
        d = c.to_dict()
        # Spec: candidates must not carry supplier/cost/SKU data
        for forbidden in ("supplier", "cost", "sku", "moq", "purchase_price"):
            self.assertNotIn(forbidden, d)


class TestProductCandidateAgent(unittest.TestCase):
    """Tests for :class:`ProductCandidateAgent`."""

    def test_generates_candidates(self):
        agent = ProductCandidateAgent(max_candidates=3)
        result = agent.run(_sample_analyzer_results())
        self.assertIsInstance(result, AgentResult)
        self.assertEqual(result.status, "completed")
        candidates = result.output["candidates"]
        self.assertEqual(len(candidates), 3)

    def test_all_candidates_start_pending(self):
        agent = ProductCandidateAgent()
        result = agent.run(_sample_analyzer_results())
        for c in result.output["candidates"]:
            self.assertEqual(c["status"], STATUS_PENDING)
            self.assertTrue(c["requires_review"])

    def test_candidates_sorted_by_opportunity(self):
        agent = ProductCandidateAgent(max_candidates=3)
        result = agent.run(_sample_analyzer_results())
        scores = [
            Decimal(c["opportunity_score"] or "0")
            for c in result.output["candidates"]
        ]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_candidate_ids_incrementing(self):
        agent = ProductCandidateAgent(max_candidates=3)
        result = agent.run(_sample_analyzer_results())
        ids = [c["candidate_id"] for c in result.output["candidates"]]
        self.assertEqual(ids, ["PC-0001", "PC-0002", "PC-0003"])

    def test_reference_asins_from_products(self):
        agent = ProductCandidateAgent()
        result = agent.run(_sample_analyzer_results())
        first = result.output["candidates"][0]
        self.assertGreater(len(first["reference_asins"]), 0)
        self.assertIn("B0DNVW368Z", first["reference_asins"])

    def test_reference_asins_prefer_keyword_matches(self):
        # "chicken saddle" candidate should prefer the two products
        # whose titles contain "chicken saddle".
        agent = ProductCandidateAgent()
        result = agent.run(_sample_analyzer_results())
        first = result.output["candidates"][0]
        asins = set(first["reference_asins"])
        self.assertIn("B0DNVW368Z", asins)  # "Mother Hen Chicken Saddle"
        self.assertIn("B0GKV239MP", asins)  # "Esmorah Chicken Saddle"

    def test_no_supplier_data_in_output(self):
        agent = ProductCandidateAgent()
        result = agent.run(_sample_analyzer_results())
        for c in result.output["candidates"]:
            for forbidden in ("supplier", "cost", "sku", "moq", "purchase_price"):
                self.assertNotIn(forbidden, c)

    def test_max_candidates_respected(self):
        agent = ProductCandidateAgent(max_candidates=2)
        result = agent.run(_sample_analyzer_results())
        self.assertEqual(len(result.output["candidates"]), 2)

    def test_empty_analyzer_results_returns_empty(self):
        agent = ProductCandidateAgent()
        result = agent.run({})
        self.assertEqual(result.output["candidates"], [])

    def test_pre_confirmed_candidates_marked(self):
        agent = ProductCandidateAgent(max_candidates=3)
        result = agent.run(
            _sample_analyzer_results(),
            confirmed_candidates=["PC-0001"],
        )
        candidates = result.output["candidates"]
        self.assertEqual(candidates[0]["status"], STATUS_CONFIRMED)
        self.assertEqual(candidates[1]["status"], STATUS_PENDING)

    def test_invalid_max_candidates_raises(self):
        with self.assertRaises(ValueError):
            ProductCandidateAgent(max_candidates=0)


class TestConfirmRejectReset(unittest.TestCase):
    """Tests for the candidate state machine."""

    def setUp(self):
        self.candidate = ProductCandidate(
            candidate_id="PC-0001",
            product_name="Chicken Saddle",
            top_keyword="chicken saddle",
        )

    def test_confirm_sets_status(self):
        confirm_candidate(self.candidate, reviewer="alice", notes="looks good")
        self.assertEqual(self.candidate.status, STATUS_CONFIRMED)
        self.assertEqual(self.candidate.reviewer, "alice")
        self.assertEqual(self.candidate.review_notes, "looks good")
        self.assertFalse(self.candidate.requires_review)

    def test_confirm_requires_reviewer(self):
        with self.assertRaises(ValueError):
            confirm_candidate(self.candidate, reviewer="")

    def test_reject_sets_status_and_reason(self):
        reject_candidate(self.candidate, reviewer="bob", reason="too competitive")
        self.assertEqual(self.candidate.status, STATUS_REJECTED)
        self.assertEqual(self.candidate.reviewer, "bob")
        self.assertEqual(self.candidate.review_notes, "too competitive")
        self.assertFalse(self.candidate.requires_review)

    def test_reject_requires_reason(self):
        with self.assertRaises(ValueError):
            reject_candidate(self.candidate, reviewer="bob", reason="")

    def test_reject_requires_reviewer(self):
        with self.assertRaises(ValueError):
            reject_candidate(self.candidate, reviewer="", reason="x")

    def test_cannot_confirm_rejected(self):
        reject_candidate(self.candidate, reviewer="bob", reason="x")
        with self.assertRaises(CandidateStatusError):
            confirm_candidate(self.candidate, reviewer="alice")

    def test_reset_returns_to_pending(self):
        confirm_candidate(self.candidate, reviewer="alice")
        reset_candidate(self.candidate)
        self.assertEqual(self.candidate.status, STATUS_PENDING)
        self.assertEqual(self.candidate.reviewer, "")
        self.assertTrue(self.candidate.requires_review)

    def test_reset_after_reject(self):
        reject_candidate(self.candidate, reviewer="bob", reason="x")
        reset_candidate(self.candidate)
        self.assertEqual(self.candidate.status, STATUS_PENDING)
        # After reset we can confirm again
        confirm_candidate(self.candidate, reviewer="alice")
        self.assertEqual(self.candidate.status, STATUS_CONFIRMED)


class TestGateProductAgent(unittest.TestCase):
    """Tests for the product-agent gate."""

    def setUp(self):
        self.candidates = [
            ProductCandidate(
                candidate_id="PC-0001",
                product_name="A",
                top_keyword="kw_a",
            ),
            ProductCandidate(
                candidate_id="PC-0002",
                product_name="B",
                top_keyword="kw_b",
            ),
        ]

    def test_no_confirmed_gates_closed(self):
        result = gate_product_agent(self.candidates)
        self.assertEqual(result.status, "pending_manual_confirmation")
        self.assertEqual(result.output["gate"], "closed")
        self.assertEqual(result.output["confirmed_count"], 0)
        self.assertEqual(result.output["pending_count"], 2)

    def test_confirmed_opens_gate(self):
        confirm_candidate(self.candidates[0], reviewer="alice")
        result = gate_product_agent(self.candidates)
        self.assertEqual(result.status, "completed")
        self.assertEqual(result.output["gate"], "open")
        self.assertEqual(result.output["confirmed_count"], 1)

    def test_rejected_keeps_gate_closed(self):
        reject_candidate(self.candidates[0], reviewer="bob", reason="x")
        reject_candidate(self.candidates[1], reviewer="bob", reason="y")
        result = gate_product_agent(self.candidates)
        self.assertEqual(result.status, "pending_manual_confirmation")
        self.assertEqual(result.output["rejected_count"], 2)

    def test_can_proceed_to_product_agent_false_when_pending(self):
        self.assertFalse(can_proceed_to_product_agent(self.candidates))

    def test_can_proceed_to_product_agent_true_when_confirmed(self):
        confirm_candidate(self.candidates[0], reviewer="alice")
        self.assertTrue(can_proceed_to_product_agent(self.candidates))

    def test_get_confirmed_candidates_filters(self):
        confirm_candidate(self.candidates[1], reviewer="alice")
        confirmed = get_confirmed_candidates(self.candidates)
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0].candidate_id, "PC-0002")

    def test_gate_returns_candidates_in_output(self):
        result = gate_product_agent(self.candidates)
        self.assertIn("candidates", result.output)
        self.assertEqual(len(result.output["candidates"]), 2)

    def test_gate_emits_warning_when_closed(self):
        result = gate_product_agent(self.candidates)
        self.assertTrue(
            any("pending manual confirmation" in w.lower() for w in result.warnings)
        )


class TestAllowedStatuses(unittest.TestCase):
    def test_three_statuses(self):
        self.assertEqual(
            set(ALLOWED_STATUSES),
            {STATUS_PENDING, STATUS_CONFIRMED, STATUS_REJECTED},
        )


class TestIntegrationWithProductAgent(unittest.TestCase):
    """End-to-end: candidates → confirm → gate opens.

    Verifies that an unconfirmed candidate list produces a
    ``pending_manual_confirmation`` gate result, while confirming
    one candidate flips the gate to open.
    """

    def test_full_flow_unconfirmed_blocks(self):
        agent = ProductCandidateAgent(max_candidates=3)
        result = agent.run(_sample_analyzer_results())
        candidates = [
            ProductCandidate(
                candidate_id=c["candidate_id"],
                product_name=c["product_name"],
                top_keyword=c["top_keyword"],
            )
            for c in result.output["candidates"]
        ]
        gate = gate_product_agent(candidates)
        self.assertEqual(gate.status, "pending_manual_confirmation")

    def test_full_flow_confirmed_unblocks(self):
        agent = ProductCandidateAgent(max_candidates=3)
        result = agent.run(_sample_analyzer_results())
        candidates = [
            ProductCandidate(
                candidate_id=c["candidate_id"],
                product_name=c["product_name"],
                top_keyword=c["top_keyword"],
            )
            for c in result.output["candidates"]
        ]
        confirm_candidate(candidates[0], reviewer="product_manager")
        gate = gate_product_agent(candidates)
        self.assertEqual(gate.status, "completed")


if __name__ == "__main__":
    unittest.main()
