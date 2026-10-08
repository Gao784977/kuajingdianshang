"""CLI entry point for the V3 Amazon workflow.

Invoked as:

    python -m src.modules.amazon.workflow --input data/amazon/demo_product_input.json
    python -m src.modules.amazon.workflow --input data/amazon/demo_product_input.json \
        --scenario all --with-mock-data --export-intermediate --strict

Supported arguments:

* ``--input``          Path to product input JSON (required).
* ``--output-dir``     Override output dir (default: data/amazon/output).
* ``--config``         Override config path (default: config/amazon_workflow.json).
* ``--scenario``       base | optimistic | pessimistic | all (default: base).
* ``--with-mock-data`` Enable mock-data fills (default: true).
* ``--no-mock-data``   Disable mock-data fills.
* ``--export-intermediate`` Write per-agent JSON stubs.
* ``--strict``         Abort on first agent failure.
* ``--help``           Show usage.

Argument-conflict errors (e.g. ``--with-mock-data`` + ``--no-mock-data``,
unknown scenario, unknown sort-by) print a clear message and exit with
non-zero status. The CLI never modifies V1/V2 code or ``src/core/agent.py``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .amazon_config import (
    AmazonConfigError,
    compute_amazon_config_sha256,
    load_amazon_config,
)
from .input_loader import InputLoaderError, load_product_input
from .master_agent import MasterAgent
from .models import CompetitorRow, ReviewRow, WorkflowContext


_VALID_SCENARIOS = ("base", "optimistic", "pessimistic", "all")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.modules.amazon.workflow",
        description="V3 Amazon US product development multi-agent workflow (offline).",
    )
    p.add_argument(
        "--input", required=True,
        help="Path to the product input JSON file.",
    )
    p.add_argument(
        "--output-dir", default=None,
        help="Output directory (default: data/amazon/output).",
    )
    p.add_argument(
        "--config", default=None,
        help="Path to the Amazon workflow config JSON "
             "(default: config/amazon_workflow.json).",
    )
    p.add_argument(
        "--scenario", default="base",
        help="Scenario to run: base | optimistic | pessimistic | all "
             "(default: base).",
    )
    mock_group = p.add_mutually_exclusive_group()
    mock_group.add_argument(
        "--with-mock-data", dest="with_mock_data", action="store_true",
        default=True,
        help="Fill missing competitor/review/profit data with mock data "
             "(default).",
    )
    mock_group.add_argument(
        "--no-mock-data", dest="with_mock_data", action="store_false",
        help="Disable mock-data fills; agent will degrade to incomplete.",
    )
    p.add_argument(
        "--export-intermediate", action="store_true",
        help="Write per-agent JSON stubs to data/amazon/output/intermediate/.",
    )
    p.add_argument(
        "--strict", action="store_true",
        help="Abort on first agent failure (otherwise mark incomplete).",
    )
    return p


def _load_optional_csvs(
    product_input: Any,
) -> "tuple[List[CompetitorRow], List[ReviewRow]]":
    """Load competitors/reviews CSV if paths are set on product input."""
    competitors: List[CompetitorRow] = []
    reviews: List[ReviewRow] = []
    if product_input.competitors_path:
        try:
            from .input_loader import load_competitors_csv
            competitors = load_competitors_csv(product_input.competitors_path)
        except InputLoaderError as exc:
            print(f"Warning: failed to load competitors CSV: {exc}",
                  file=sys.stderr)
    if product_input.reviews_path:
        try:
            from .input_loader import load_reviews_csv
            reviews = load_reviews_csv(product_input.reviews_path)
        except InputLoaderError as exc:
            print(f"Warning: failed to load reviews CSV: {exc}",
                  file=sys.stderr)
    return competitors, reviews


def main(argv: Optional[List[str]] = None) -> int:
    """CLI main entry point. Returns exit code (0 success, non-zero fail)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    # --- validate scenario ---
    if args.scenario not in _VALID_SCENARIOS:
        print(
            f"Error: unknown scenario {args.scenario!r}. "
            f"Allowed: {list(_VALID_SCENARIOS)}",
            file=sys.stderr,
        )
        return 2

    # --- load config ---
    try:
        config = load_amazon_config(args.config)
    except AmazonConfigError as exc:
        print(f"Config error: {exc}", file=sys.stderr)
        return 2
    config_sha = compute_amazon_config_sha256(config)

    # --- load product input ---
    try:
        product_input = load_product_input(
            args.input,
            supported_marketplaces=config.get("supported_marketplaces", []),
            strict=True,
        )
    except InputLoaderError as exc:
        print(f"Input error: {exc}", file=sys.stderr)
        return 2
    except FileNotFoundError as exc:
        print(f"Input file not found: {exc}", file=sys.stderr)
        return 2

    # --- load optional competitor/review CSVs ---
    competitors, reviews = _load_optional_csvs(product_input)

    # --- resolve output dir ---
    output_dir_str = args.output_dir or config.get(
        "output_settings", {}
    ).get("default_output_dir", "data/amazon/output")
    output_dir = Path(output_dir_str)

    # --- build CLI args snapshot for traceability ---
    cli_args: Dict[str, Any] = {
        "input": args.input,
        "output_dir": str(output_dir),
        "config": args.config or "config/amazon_workflow.json",
        "scenario": args.scenario,
        "with_mock_data": bool(args.with_mock_data),
        "export_intermediate": bool(args.export_intermediate),
        "strict": bool(args.strict),
    }

    # --- run workflow ---
    master = MasterAgent()
    context: WorkflowContext = master.run(
        product_input=product_input,
        config=config,
        cli_args=cli_args,
        strict=bool(args.strict),
        with_mock_data=bool(args.with_mock_data),
        competitors=competitors or None,
        reviews=reviews or None,
    )
    context.config_sha256 = config_sha

    # --- print summary ---
    print("=" * 60)
    print("V3 Amazon US Product Development Workflow — Run Summary")
    print("=" * 60)
    print(f"Input file      : {args.input}")
    print(f"Output dir      : {output_dir}")
    print(f"Config SHA-256 : {config_sha}")
    print(f"Scenario        : {args.scenario}")
    print(f"Strict mode     : {bool(args.strict)}")
    print(f"With mock data  : {bool(args.with_mock_data)}")
    print(f"Final status    : {context.final_status}")
    print(f"Agents run      : {len(context.agents)}")
    print(f"Errors          : {len(context.errors)}")
    if context.errors:
        print("--- Errors ---")
        for e in context.errors:
            print(f"  [{e.get('agent', '?')}] {e.get('error', '')}")
    # Report agent path
    report_result = context.agents.get("report")
    if report_result and report_result.output:
        out_dict = report_result.output
        if isinstance(out_dict, dict):
            print(f"Markdown report : {out_dict.get('markdown_path', '?')}")
            print(f"JSON report     : {out_dict.get('json_path', '?')}")
    # Excel agent path
    excel_result = context.agents.get("excel")
    if excel_result and excel_result.output:
        out_dict = excel_result.output
        if isinstance(out_dict, dict):
            print(f"Market Excel    : {out_dict.get('market_excel', '?')}")
            print(f"Product Excel   : {out_dict.get('product_excel', '?')}")
    print("=" * 60)

    # Exit code semantics: failed → 1, incomplete → 0 (output still useful),
    # completed → 0, completed_with_warnings → 0.
    if context.final_status == "failed":
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
