"""Master orchestration agent for the V3 Amazon workflow.

Runs the 9 analysis agents in spec order:

1. keyword   2. market    3. competitor  4. review     5. opportunity
6. product   7. profit    8. report      9. excel

Per architecture decision #10 failure semantics:

* ``--strict``: any agent failure → ``final_status="failed"`` and abort.
* non-strict: a failed agent → ``final_status="incomplete"`` (later
  agents still run); Excel skip alone → ``completed_with_warnings``.
* Status enum: {completed, completed_with_warnings, failed, incomplete}.

When ``--export-intermediate`` is set, one JSON per agent is written to
``data/amazon/output/intermediate/`` named
``<order>_<agent_name>_<ts>.json`` (decision #9). Skipped agents emit a
``{"status":"skipped"}`` stub so the file count is deterministic.

Profit agent receives ``profit_input`` (built by the orchestrator from
config when ``with_mock_data`` is true). Competitor / review agents
receive the merged rows (user CSV wins, mock fills per decision #13).

This module never modifies V1/V2 code or ``src/core/agent.py``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .amazon_config import compute_amazon_config_sha256
from .competitor_agent import CompetitorAgent
from .excel_agent import generate_market_excel, generate_product_excel
from .keyword_agent import KeywordAgent
from .market_agent import MarketAgent
from .mock_data import get_mock_profit_input
from .models import (
    ALLOWED_FINAL_STATUS,
    AgentResult,
    AmazonProfitInput,
    CompetitorRow,
    ProductInput,
    ReviewRow,
    WorkflowContext,
)
from .opportunity_agent import OpportunityAgent
from .product_agent import ProductAgent
from .profit_agent import ProfitAgent
from .report_agent import build_report
from .review_agent import ReviewAgent

# Spec order — locked. Tests assert the length and sequence.
AGENT_ORDER: List[str] = [
    "keyword",
    "market",
    "competitor",
    "review",
    "opportunity",
    "product",
    "profit",
    "report",
    "excel",
]

_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"


class MasterAgent:
    """Orchestrate the 9-agent pipeline.

    Instantiate once per workflow run. :meth:`run` is the entry point.
    """

    NAME = "master"
    VERSION = "master_agent_v1"

    def __init__(self) -> None:
        self.keyword = KeywordAgent()
        self.market = MarketAgent()
        self.competitor = CompetitorAgent()
        self.review = ReviewAgent()
        self.opportunity = OpportunityAgent()
        self.product = ProductAgent()
        self.profit = ProfitAgent()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        product_input: ProductInput,
        config: Dict[str, Any],
        cli_args: Dict[str, Any],
        *,
        strict: bool = False,
        with_mock_data: bool = True,
        profit_input: Optional[AmazonProfitInput] = None,
        competitors: Optional[List[CompetitorRow]] = None,
        reviews: Optional[List[ReviewRow]] = None,
    ) -> WorkflowContext:
        """Run the full pipeline.

        Args:
            product_input: User product input (keyword, marketplace, etc.).
            config: Loaded Amazon workflow config dict.
            cli_args: CLI arguments dict (used by report agent and
                profit scenario resolution).
            strict: If True, any agent failure aborts the workflow.
            with_mock_data: If True, mock profit input is built from
                config when no explicit profit_input is passed.
            profit_input: Optional explicit profit input. If None and
                with_mock_data is True, built from config defaults.
            competitors: Merged competitor rows (user CSV + mock fills).
            reviews: Merged review rows (user CSV + mock fills).

        Returns:
            :class:`WorkflowContext` with ``final_status`` set per
            decision #10. Agent results, warnings, errors and metadata
            are populated.
        """
        context = WorkflowContext(
            product_input=product_input,
            config=config,
            config_sha256=compute_amazon_config_sha256(config),
            cli_args=dict(cli_args),
            final_status="incomplete",
            agent_order=list(AGENT_ORDER),
            generated_at=datetime.now().strftime(_TIMESTAMP_FMT),
        )

        # Resolve profit input
        if profit_input is None and with_mock_data:
            profit_input = get_mock_profit_input(config)

        export_intermediate = bool(cli_args.get("export_intermediate", False))
        output_dir = self._output_dir(config, cli_args)
        intermediate_dir = output_dir / "intermediate"
        if export_intermediate:
            intermediate_dir.mkdir(parents=True, exist_ok=True)

        export_ts = context.generated_at or datetime.now().strftime(_TIMESTAMP_FMT)

        # Run each agent in spec order
        for order, agent_name in enumerate(AGENT_ORDER, start=1):
            result = self._run_one(
                agent_name,
                context,
                profit_input=profit_input,
                competitors=competitors,
                reviews=reviews,
                cli_args=cli_args,
                output_dir=output_dir,
            )
            context.set_result(agent_name, result)

            # Write intermediate JSON
            if export_intermediate:
                self._write_intermediate(
                    intermediate_dir, order, agent_name, export_ts, result
                )

            # Apply failure semantics
            if result.status == "failed":
                context.errors.append({
                    "agent": agent_name,
                    "error": result.error or "",
                })
                if strict:
                    context.final_status = "failed"
                    break
                # non-strict: mark incomplete and continue
                context.final_status = "incomplete"
            elif result.status == "skipped":
                # Excel skip alone is a warning, not a hard failure.
                if context.final_status != "failed":
                    context.final_status = "completed_with_warnings"
            elif result.status == "incomplete":
                if context.final_status != "failed":
                    context.final_status = "incomplete"
            # completed / completed_with_warnings fall through

        # If we never broke out and no failures/skips, mark completed
        if not context.errors and not any(
            r.status in ("skipped", "incomplete", "failed")
            for r in context.agents.values()
        ):
            context.final_status = "completed"
        elif context.final_status not in ALLOWED_FINAL_STATUS:
            context.final_status = "incomplete"

        # Safety: if final_status got set to completed_with_warnings but
        # errors exist, downgrade to incomplete (per decision #10).
        if context.errors and context.final_status == "completed":
            context.final_status = "incomplete"

        # Final report refresh — when the report agent ran in-loop, it
        # could not see its own or later agents' status in section 3.
        # Rebuild the MD/JSON now that all agents have populated their
        # results so the traceability section reflects the final state.
        report_result = context.agents.get("report")
        if report_result and report_result.status == "completed":
            try:
                refresh = build_report(context, output_dir)
                # Preserve the original intermediate-export stub for
                # the report step (already written in-loop).
                context.agents["report"] = refresh
            except Exception as exc:  # noqa: BLE001
                context.warnings.append(
                    f"Final report refresh failed: {type(exc).__name__}: {exc}"
                )

        return context

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _output_dir(self, config: Dict[str, Any], cli_args: Dict[str, Any]) -> Path:
        os_cfg = config.get("output_settings", {})
        default_dir = os_cfg.get("default_output_dir", "data/amazon/output")
        out = cli_args.get("output_dir") or default_dir
        return Path(out)

    def _run_one(
        self,
        agent_name: str,
        context: WorkflowContext,
        *,
        profit_input: Optional[AmazonProfitInput],
        competitors: Optional[List[CompetitorRow]],
        reviews: Optional[List[ReviewRow]],
        cli_args: Dict[str, Any],
        output_dir: Path,
    ) -> AgentResult:
        """Dispatch to the named agent. Catches all exceptions."""
        try:
            if agent_name == "keyword":
                return self.keyword.run(context)
            if agent_name == "market":
                return self.market.run(context)
            if agent_name == "competitor":
                return self.competitor.run(context, competitors=competitors)
            if agent_name == "review":
                return self.review.run(context, reviews=reviews)
            if agent_name == "opportunity":
                return self.opportunity.run(context)
            if agent_name == "product":
                return self.product.run(context)
            if agent_name == "profit":
                return self.profit.run(
                    context, profit_input=profit_input
                )
            if agent_name == "report":
                return build_report(context, output_dir)
            if agent_name == "excel":
                return self._run_excel(context, output_dir)
        except Exception as exc:  # noqa: BLE001 — orchestration must not crash
            return AgentResult(
                agent_name=agent_name,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                version=self._agent_version(context, agent_name),
                source="calculated",
            )
        # Unknown agent name — treat as skipped
        return AgentResult(
            agent_name=agent_name,
            status="skipped",
            warnings=[f"Unknown agent {agent_name!r}"],
            version=self._agent_version(context, agent_name),
            source="calculated",
        )

    def _agent_version(self, context: WorkflowContext, name: str) -> str:
        av = context.config.get("agent_versions", {})
        return str(av.get(name, ""))

    def _run_excel(self, context: WorkflowContext, output_dir: Path) -> AgentResult:
        """Run both Excel generators. Returns AgentResult."""
        warnings: List[str] = []
        assumptions: List[str] = []
        ts = context.generated_at or datetime.now().strftime(_TIMESTAMP_FMT)
        os_cfg = context.config.get("output_settings", {})
        market_name = os_cfg.get(
            "market_excel_template", "market_report_{timestamp}.xlsx"
        ).format(timestamp=ts)
        product_name = os_cfg.get(
            "product_excel_template", "product_plan_{timestamp}.xlsx"
        ).format(timestamp=ts)
        market_path = output_dir / market_name
        product_path = output_dir / product_name

        market_res = generate_market_excel(context, market_path)
        prod_res = generate_product_excel(context, product_path)

        if market_res.status == "skipped":
            warnings.append(f"Market Excel skipped: {market_res.error or ''}")
        if prod_res.status == "skipped":
            warnings.append(f"Product Excel skipped: {prod_res.error or ''}")

        if market_res.status == "failed" or prod_res.status == "failed":
            return AgentResult(
                agent_name="excel",
                status="failed",
                error=market_res.error or prod_res.error or "Excel generation failed",
                warnings=warnings,
                assumptions=assumptions,
                version="excel_agent_v1",
                source="calculated",
            )
        if market_res.status == "skipped" or prod_res.status == "skipped":
            return AgentResult(
                agent_name="excel",
                status="skipped",
                warnings=warnings,
                assumptions=assumptions,
                output={"market_excel": str(market_path), "product_excel": str(product_path)},
                version="excel_agent_v1",
                source="calculated",
            )
        return AgentResult(
            agent_name="excel",
            status="completed",
            warnings=warnings,
            assumptions=assumptions,
            output={"market_excel": str(market_path), "product_excel": str(product_path)},
            version="excel_agent_v1",
            source="calculated",
        )

    def _write_intermediate(
        self,
        intermediate_dir: Path,
        order: int,
        agent_name: str,
        ts: str,
        result: AgentResult,
    ) -> None:
        """Write a per-agent JSON stub for --export-intermediate."""
        path = intermediate_dir / f"{order:02d}_{agent_name}_{ts}.json"
        try:
            payload = result.to_dict()
        except Exception:
            payload = {"agent_name": agent_name, "status": "skipped"}
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
