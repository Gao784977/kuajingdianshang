"""Keyword analysis agent for the V3 Amazon workflow.

Decision #7 (source/confidence): mock data is tagged
``source="mock_data"``, ``confidence="low"`` — never ``high``. Same
input → same output (deterministic).

The agent reads the user-provided keyword from
:class:`WorkflowContext.product_input` and returns the deterministic
mock keyword cluster from :func:`mock_data.get_mock_keyword`. Because
real search-volume data requires an external API (out of scope for
the offline V3 runtime), ``search_volume`` stays ``None`` and
``confidence`` stays ``low``.
"""

from __future__ import annotations

from typing import Any, Dict

from .mock_data import get_mock_keyword
from .models import AgentResult, KeywordOutput, WorkflowContext


class KeywordAgent:
    """Produce a deterministic keyword analysis for the product keyword."""

    NAME = "keyword"
    VERSION = "keyword_agent_v1"

    def run(self, context: WorkflowContext) -> AgentResult:
        """Run keyword analysis.

        Args:
            context: Workflow context; reads ``product_input.keyword``.

        Returns:
            :class:`AgentResult` whose ``output`` is a
            :class:`KeywordOutput`. Status is ``"completed"`` even when
            the keyword is empty (mock data still returns a default
            cluster); an empty keyword is recorded as a warning.
        """
        warnings: list[str] = []
        assumptions: list[str] = []

        product_input = context.product_input
        keyword = product_input.keyword if product_input else ""

        if not keyword:
            warnings.append(
                "Product input has no keyword; using mock default "
                "'chicken coop door'."
            )
            keyword = "chicken coop door"

        # Deterministic mock output — no API call, no randomness.
        mock_output: KeywordOutput = get_mock_keyword()
        # Override the normalized keyword so it reflects the user input
        # when one was provided. The related-keyword cluster still comes
        # from mock data (deterministic).
        output = KeywordOutput(
            normalized_keyword=keyword,
            related_keywords=list(mock_output.related_keywords),
            keyword_intent=mock_output.keyword_intent,
            keyword_type=mock_output.keyword_type,
            competition=mock_output.competition,
            trend=mock_output.trend,
            search_volume=None,  # mock data: real volume requires an API
            source="mock_data",
            confidence="low",
        )

        assumptions.append(
            "Keyword analysis uses deterministic mock data; "
            "search_volume is null because real search-volume data "
            "requires an external API."
        )

        return AgentResult(
            agent_name=self.NAME,
            status="completed",
            input_summary={"keyword": keyword},
            output=output,
            warnings=warnings,
            assumptions=assumptions,
            source="mock_data",
            version=self.VERSION,
        )
