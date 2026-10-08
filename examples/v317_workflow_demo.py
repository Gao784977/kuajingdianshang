"""V3.1.7 — Workflow orchestrator demo.

Demonstrates the full V3.1 pipeline:

1. Load keyword + product fixtures (Excel)
2. Normalise + analyse
3. URL fetch is disabled by default (no --allow-url-fetch)
4. Market research report produced (9-sheet Excel)
5. Product candidates generated (all in pending_review)
6. Gate closed → product/profit agents do not run

Then a second run with confirmed_candidate_ids=["PC-0001"]:

7. Gate opens → MasterAgent runs for PC-0001
8. Product plan + profit result produced

Usage::

    python examples/v317_workflow_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from modules.amazon.v31_workflow import V31Workflow  # noqa: E402
from modules.amazon.amazon_config import load_amazon_config  # noqa: E402

_FIXTURE_DIR = _PROJECT_ROOT / "tests" / "fixtures"
_OUTPUT_DIR = _PROJECT_ROOT / "data" / "output"
_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _print_section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def main() -> None:
    config = load_amazon_config()
    kw_fixture = _FIXTURE_DIR / "keyword_analysis.xlsx"
    prod_fixture = _FIXTURE_DIR / "products.xlsx"
    excel_files = [f for f in (kw_fixture, prod_fixture) if f.exists()]

    # ------------------------------------------------------------------
    # Run 1: Gate closed (no confirmed candidates)
    # ------------------------------------------------------------------
    _print_section("Run 1: Gate closed (no confirmed candidates)")
    print(f"  Excel files: {[f.name for f in excel_files]}")
    print(f"  Output dir:  {_OUTPUT_DIR}")

    wf1 = V31Workflow(
        project_name="v317_demo_closed",
        excel_files=excel_files,
        config=config,
        output_dir=_OUTPUT_DIR,
    )
    result1 = wf1.run()

    print(f"\n  Project:              {result1.project_name}")
    print(f"  Generated at:         {result1.generated_at}")
    print(f"  Candidates:          {len(result1.candidates)}")
    print(f"  Gate status:         {result1.candidate_gate_status}")
    print(f"  Product plans:       {len(result1.product_plans)}")
    print(f"  Profit results:      {len(result1.profit_results)}")
    print(f"  Warnings:            {len(result1.warnings)}")
    print(f"  Errors:               {len(result1.errors)}")

    if result1.market_research_report_path:
        print(f"  Report path:         {result1.market_research_report_path.name}")

    print(f"\n  Analyzer keys:       {list(result1.analyzer_results.keys())}")

    if result1.candidates:
        print("\n  Candidates:")
        for c in result1.candidates:
            print(f"    {c.candidate_id}: {c.product_name} "
                  f"(score={c.opportunity_score}, status={c.status})")

    print("\n  Warnings:")
    for w in result1.warnings:
        print(f"    - {w}")

    # ------------------------------------------------------------------
    # Run 2: Gate open (PC-0001 confirmed)
    # ------------------------------------------------------------------
    _print_section("Run 2: Gate open (PC-0001 confirmed)")

    wf2 = V31Workflow(
        project_name="v317_demo_open",
        excel_files=excel_files,
        config=config,
        output_dir=_OUTPUT_DIR,
        confirmed_candidate_ids=["PC-0001"],
    )
    result2 = wf2.run()

    print(f"  Project:              {result2.project_name}")
    print(f"  Gate status:          {result2.candidate_gate_status}")
    print(f"  Product plans:        {len(result2.product_plans)}")
    print(f"  Profit results:      {len(result2.profit_results)}")

    if result2.product_plans:
        plan = result2.product_plans[0]
        print(f"\n  Plan 0:")
        print(f"    candidate_id:  {plan.get('candidate_id')}")
        print(f"    final_status:  {plan.get('final_status')}")
        if plan.get("product_output"):
            po = plan["product_output"]
            print(f"    product_name:  {po.get('product_name', 'N/A')}")
            print(f"    target_price:  {po.get('target_price', 'N/A')}")

    if result2.profit_results:
        profit = result2.profit_results[0]
        print(f"\n  Profit 0:")
        print(f"    candidate_id:  {profit.get('candidate_id')}")
        if profit.get("profit_output"):
            print(f"    has output:    yes")

    # ------------------------------------------------------------------
    # Run 3: URL fetch enabled (fake transport, no network)
    # ------------------------------------------------------------------
    _print_section("Run 3: URL fetch enabled (fake transport)")

    def fake_transport(url, *, headers, timeout, max_bytes):
        return 200, b"<html>fake product page</html>", {"Content-Type": "text/html"}

    user_input = {
        "urls": [
            {"url": "https://www.amazon.com/dp/B0DNVW368Z", "notes": "competitor 1"},
            {"url": "https://www.amazon.com/dp/B0CS9LV4RD", "notes": "competitor 2"},
        ],
    }
    wf3 = V31Workflow(
        project_name="v317_demo_url",
        excel_files=[],
        user_input=user_input,
        config=config,
        cli_args={"allow_url_fetch": True},
        output_dir=_OUTPUT_DIR,
        url_transport=fake_transport,
    )
    result3 = wf3.run()

    print(f"  URL fetches:          {len(result3.analyzer_results.get('url_fetches', []))}")
    for uf in result3.analyzer_results.get("url_fetches", []):
        status = "OK" if uf.get("success") else "FAIL"
        print(f"    [{status}] {uf.get('source_url', '')}")

    # ------------------------------------------------------------------
    # to_dict summary
    # ------------------------------------------------------------------
    _print_section("Result to_dict summary (Run 1)")
    d = result1.to_dict()
    print(json.dumps(d, indent=2, default=str)[:2000])

    print("\nDemo complete.")


if __name__ == "__main__":
    main()
