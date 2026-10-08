"""Command line entry point for the opportunity analysis tool.

Usage (v1 backward compatible)::

    python -m src.modules.analyze_opportunities --input data/raw/demo_opportunities.csv

Usage (v2 full)::

    python -m src.modules.analyze_opportunities \\
        --input data/raw/demo_opportunities_v2.csv \\
        --scenario all \\
        --sensitivity \\
        --sort-by score \\
        --descending \\
        --output-dir data/output/v2

Exit codes:
    0 - success
    1 - invalid arguments or runtime error
    2 - invalid CLI argument combination (e.g. both --ascending and --descending)
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from typing import List, Optional

from .config_loader import (
    ConfigError,
    compute_config_sha256,
    get_sensitivity_config,
    load_config,
)
from .csv_import import CSVImportError, load_opportunities
from .data_quality import check_data_quality
from .opportunity_scoring import EconomicsInput, score_opportunity
from .profit_calculator import calculate_profit
from .project_report import (
    compute_file_sha256,
    compute_portfolio_summary,
    write_reports,
)
from .recommendation import build_recommendation
from .scenario_calculator import calculate_scenarios, resolve_scenarios
from .sensitivity_analysis import analyze_sensitivity

# v2 CLI defaults differ from the module defaults (which stay at v1 for
# backward compatibility of the library API).
_CLI_DEFAULT_SCORING_VERSION = "scoring_v2"
_CLI_DEFAULT_CALCULATION_VERSION = "calculation_v2"

_VALID_SORT_FIELDS = ("score", "profit", "payback", "margin", "investment")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze_opportunities",
        description="Analyze opportunities from a CSV file and produce a "
        "traceable project report (supports v1 and v2 features).",
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the input CSV file (UTF-8 or UTF-8 BOM).",
    )
    parser.add_argument(
        "--output-dir",
        default="data/output",
        help="Directory for generated reports (default: data/output).",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to the config JSON file (default: config/opportunity_config.json).",
    )
    parser.add_argument(
        "--scoring-version",
        default=_CLI_DEFAULT_SCORING_VERSION,
        help=f"Scoring rule version (default: {_CLI_DEFAULT_SCORING_VERSION}). "
        "Use 'scoring_v1' for v1 compatibility.",
    )
    parser.add_argument(
        "--calculation-version",
        default=_CLI_DEFAULT_CALCULATION_VERSION,
        help=f"Calculation rule version (default: {_CLI_DEFAULT_CALCULATION_VERSION}).",
    )
    parser.add_argument(
        "--scenario",
        default="base",
        help="Scenario to calculate: base, optimistic, pessimistic, or all "
        "(default: base).",
    )
    parser.add_argument(
        "--sensitivity",
        action="store_true",
        help="Run sensitivity analysis for each opportunity.",
    )
    parser.add_argument(
        "--sensitivity-parameters",
        nargs="+",
        default=None,
        help="Parameters for sensitivity analysis. Defaults to config values.",
    )
    parser.add_argument(
        "--sort-by",
        default="score",
        choices=_VALID_SORT_FIELDS,
        help="Field to sort the opportunity ranking by (default: score).",
    )
    direction = parser.add_mutually_exclusive_group()
    direction.add_argument(
        "--descending",
        action="store_true",
        default=True,
        help="Sort ranking in descending order (default).",
    )
    direction.add_argument(
        "--ascending",
        action="store_true",
        default=False,
        help="Sort ranking in ascending order.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Strict mode: enforce human-review field constraints.",
    )
    return parser


def _sort_descending(args: argparse.Namespace) -> bool:
    """Return True if sorting should be descending.

    Handles the mutual-exclusion group so that --ascending wins when both
    would be true (argparse prevents both from being set simultaneously via
    the mutually exclusive group, but we keep the default-True behaviour for
    --descending).
    """
    if args.ascending:
        return False
    return True


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    cli_string = " ".join(sys.argv[1:]) if argv is None else " ".join(argv)

    # --- Load config ---
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: Failed to load config: {exc}", file=sys.stderr)
        return 1

    config_hash = compute_config_sha256(args.config)

    # --- Validate scenario ---
    try:
        scenarios = resolve_scenarios(args.scenario)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    # --- Validate sensitivity parameters ---
    sens_cfg = get_sensitivity_config(config)
    sens_params = args.sensitivity_parameters
    if sens_params is not None:
        allowed = sens_cfg["parameters"]
        invalid = [p for p in sens_params if p not in allowed]
        if invalid:
            print(
                f"ERROR: Invalid sensitivity parameter(s): {', '.join(invalid)}. "
                f"Allowed: {', '.join(allowed)}.",
                file=sys.stderr,
            )
            return 1

    # --- Load opportunities ---
    try:
        opportunities = load_opportunities(args.input, config=config, strict=args.strict)
    except CSVImportError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"ERROR: Input file not found: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: Failed to load opportunities: {exc}", file=sys.stderr)
        return 1

    # --- Base profit + score ---
    base_profits = [
        calculate_profit(o, calculation_version=args.calculation_version)
        for o in opportunities
    ]
    base_scores = []
    for o, p in zip(opportunities, base_profits):
        econ = EconomicsInput(
            revenue=p.revenue,
            gross_profit=p.gross_profit,
            gross_margin=p.gross_margin,
            gross_payback_months=p.gross_payback_months,
            net_payback_months=p.net_payback_months,
        )
        base_scores.append(
            score_opportunity(
                o, scoring_version=args.scoring_version, config=config, economics=econ
            )
        )

    # --- Scenarios ---
    scenario_results_by_id = {}
    if args.scenario != "base":
        for o in opportunities:
            scenario_results_by_id[o.opportunity_id] = calculate_scenarios(
                o,
                config=config,
                scenarios=scenarios,
                scoring_version=args.scoring_version,
                calculation_version=args.calculation_version,
                revenue_consistency_threshold=Decimal(
                    str(config.get("revenue_consistency_threshold", 0.10))
                ),
            )
    else:
        # Still store base scenario for the report.
        for o, p, s in zip(opportunities, base_profits, base_scores):
            from .scenario_calculator import ScenarioResult

            scenario_results_by_id[o.opportunity_id] = [
                ScenarioResult(scenario="base", profit=p, score=s)
            ]

    # --- Sensitivity ---
    sensitivity_by_id = {}
    sensitivity_grade_drop_by_id = {}
    if args.sensitivity:
        for o in opportunities:
            sens = analyze_sensitivity(
                o,
                config=config,
                scoring_version=args.scoring_version,
                calculation_version=args.calculation_version,
                parameters=sens_params,
            )
            sensitivity_by_id[o.opportunity_id] = sens
            # Determine if any parameter caused a 2+ grade drop.
            grade_order = {"A": 4, "B": 3, "C": 2, "D": 1}
            base_rank = grade_order.get(sens.base_grade, 0)
            max_drop = 0
            for pt in sens.points:
                drop = base_rank - grade_order.get(pt.grade, 0)
                if drop > max_drop:
                    max_drop = drop
            sensitivity_grade_drop_by_id[o.opportunity_id] = max_drop >= 2

    # --- Data quality ---
    dq_issues = check_data_quality(
        opportunities,
        base_profits,
        payback_warning_months=Decimal(str(config.get("payback_warning_months", 24))),
        revenue_consistency_threshold=Decimal(
            str(config.get("revenue_consistency_threshold", 0.10))
        ),
    )

    # --- Boundary / missing key data detection ---
    def _has_boundary_or_missing(opp) -> bool:
        if not opp.customer_segment or not opp.industry or not opp.region:
            return True
        if opp.initial_investment <= 0:
            return True
        return False

    # --- Recommendations ---
    recommendations_by_id = {}
    for o, s in zip(opportunities, base_scores):
        scens = scenario_results_by_id.get(o.opportunity_id, [])
        rec = build_recommendation(
            o,
            base_score_grade=s.grade,
            scenario_results=scens,
            sensitivity_grade_drop=sensitivity_grade_drop_by_id.get(o.opportunity_id, False),
            has_boundary_or_missing=_has_boundary_or_missing(o),
        )
        recommendations_by_id[o.opportunity_id] = rec

    # --- Portfolio summary ---
    portfolio_summary = compute_portfolio_summary(opportunities, base_profits, base_scores)

    # --- Input hash ---
    try:
        input_hash = compute_file_sha256(args.input)
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: Failed to compute input hash: {exc}", file=sys.stderr)
        return 1

    # --- Sort direction ---
    sort_desc = _sort_descending(args)

    command_args = {
        "input": args.input,
        "output_dir": args.output_dir,
        "config": args.config,
        "scoring_version": args.scoring_version,
        "calculation_version": args.calculation_version,
        "scenario": args.scenario,
        "sensitivity": args.sensitivity,
        "sensitivity_parameters": args.sensitivity_parameters,
        "sort_by": args.sort_by,
        "ascending": args.ascending,
        "descending": args.descending,
        "strict": args.strict,
        "cli_string": cli_string,
    }

    # --- Write reports ---
    try:
        result = write_reports(
            opportunities=opportunities,
            scores=base_scores,
            profits=base_profits,
            input_path=args.input,
            input_hash=input_hash,
            output_dir=args.output_dir,
            scoring_version=args.scoring_version,
            calculation_version=args.calculation_version,
            config=config,
            config_hash=config_hash,
            command_args=command_args,
            scenarios=scenario_results_by_id,
            sensitivity=sensitivity_by_id,
            data_quality_issues=dq_issues,
            recommendations=recommendations_by_id,
            portfolio_summary=portfolio_summary,
            sort_by=args.sort_by,
            sort_desc=sort_desc,
        )
    except Exception as exc:  # pragma: no cover - defensive
        print(f"ERROR: Failed to write report: {exc}", file=sys.stderr)
        return 1

    if len(result) == 3:
        md_path, json_path, csv_path = result
    else:
        md_path, json_path = result
        csv_path = ""

    grade_counts = {"A": 0, "B": 0, "C": 0, "D": 0}
    for s in base_scores:
        grade_counts[s.grade] += 1

    print(f"输入文件: {args.input}")
    print(f"分析机会数量: {len(opportunities)}")
    print(
        f"A/B/C/D 数量: A={grade_counts['A']}, B={grade_counts['B']}, "
        f"C={grade_counts['C']}, D={grade_counts['D']}"
    )
    print(f"Markdown 报告路径: {md_path}")
    print(f"JSON 结果路径: {json_path}")
    if csv_path:
        print(f"CSV 结果路径: {csv_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
