# V3 Implementation Plan — Amazon US Product Development Multi-Agent Workflow

## Context

V1/V2 of the opportunity analysis tool is complete and verified (99 tests pass). V3 adds an **offline** Amazon US product development Multi-Agent workflow on top of the existing codebase. The user provides a JSON product input (keyword, marketplace, target price, constraints); the system runs 9 analysis agents in sequence and produces Markdown + JSON + 2 Excel workbooks. All data is deterministic mock data or user input — no network, no API keys, no Amazon/SP-API/LLM calls. The architecture preserves a clean seam so a future "data provider" layer can replace mock data without touching agent logic.

Hard constraints: do not modify V1/V2 modules or `src/core/agent.py`; keep all V1/V2 tests green; stay runnable in a no-network, no-key environment.

## Architecture decisions (locked)

1. **Module home**: `src/modules/amazon/` (matches existing `src/modules/` convention; spec allowed `src/agents/amazon/` but consistency wins).
2. **Profit reuse**: V1/V2 `calculate_profit` is hardwired to the `Opportunity` dataclass and a fixed 7-key scenario multiplier set that is structurally incompatible with Amazon's cost taxonomy (FBA fee, referral fee, etc.). We do **not** modify V1/V2. Instead `profit_agent.py` owns `AmazonProfitResult` + `calculate_amazon_profit`, replicating the 2-line `_q2`/`_q4` Decimal quantization helpers (documented lineage). `profit_agent.py` imports only stdlib — never `csv_import` — to avoid any future import cycle.
3. **Config**: new `src/modules/amazon/amazon_config.py` with `load_amazon_config`, `AmazonConfigError`, SHA-256. Never touches V1/V2 `config_loader.py` or `opportunity_config.json`.
4. **Decimal JSON encoder**: replicate `_DecimalEncoder` as `AmazonDecimalEncoder` in `report_agent.py` (it's private in V1/V2; cross-module import would violate convention). Reuse the **public** `compute_file_sha256` from `project_report.py`.
5. **Typed agent data flow**: `AgentResult.output: Any` stays loose for JSON serialization, but `WorkflowContext.get_output(agent_name, cls)` does typed access via `isinstance`/`cls.from_dict`. Downstream agents never poke dicts with `.get()`.
6. **Amazon scenario multipliers**: new keys under `amazon_workflow.json:scenarios` — `selling_price_multiplier`, `units_multiplier`, `unit_cost_multiplier`, `fba_fee_multiplier`, `referral_fee_multiplier`, `storage_fee_multiplier`, `advertising_cost_multiplier`, `return_cost_multiplier`, `fixed_development_cost_multiplier`. Single source of truth: `_AMAZON_MULTIPLIER_KEYS` constant shared by `profit_agent.py` (apply) and `amazon_config.py` (validate). Typos raise `AmazonConfigError` loudly.
7. **Source/confidence propagation**: every major field carries `(value, source, confidence)` via a `Sourced[T]` generic dataclass in `models.py`. Sources ∈ {user_input, mock_data, calculated, imported_csv, imported_xlsx, manual_review}; confidence ∈ {high, medium, low, unknown}. `mock_data` confidence never `high`.
8. **Excel**: `openpyxl` (3.1.5 installed) is **optional** — lazy-imported inside `excel_agent.py` functions. If missing, agent returns `status="skipped"` with warning; MD/JSON unaffected. Add `openpyxl>=3.1.0` to `requirements.txt` with comment "V3 Excel output (optional)". Generate timestamped workbooks directly to `data/amazon/output/` — **no separate `templates/` directory** (templates dir is dead weight; the timestamped files are the deliverables). Convert `Decimal` → `float` at the Excel boundary (document precision loss).
9. **`--export-intermediate`**: write one JSON per agent to `data/amazon/output/intermediate/`, named `<order>_<agent_name>_<ts>.json` (e.g. `01_keyword_<ts>.json`). Skipped agents emit a `{"status":"skipped"}` stub so counts are deterministic.
10. **Failure semantics**: `WorkflowContext.final_status` transitions — any agent failure in `--strict` → `failed` and abort. In non-strict → `incomplete` (even if later agents succeed); Excel skip alone → `completed_with_warnings`. Status enum: {completed, completed_with_warnings, failed, incomplete}.
11. **Report sections**: lock the 17-section order as `_REPORT_SECTIONS` tuple in `report_agent.py` so tests assert count/order without re-reading spec.
12. **Timestamp format**: `%Y%m%d_%H%M%S` (matches V1/V2 `data/output/` convention).
13. **Mock-vs-user merge**: when both `--with-mock-data` and user JSON supply a field, user input wins; merged record tags overrides as `source=user_input` and fills as `source=mock_data`.

## New files (in execution order)

### Phase 1: foundation
- `src/modules/amazon/__init__.py` — empty package marker
- `src/modules/amazon/models.py` — all dataclasses: `Sourced[T]`, `AgentResult`, `WorkflowContext`, `ProductInput`, `CompetitorRow`, `ReviewRow`, `KeywordOutput`, `MarketOutput`, `CompetitorOutput`, `ReviewOutput`, `OpportunityOutput`, `ProductOutput`, `AmazonProfitInput`, `AmazonProfitResult`, `AmazonDecimalEncoder`. `from_dict`/`to_dict` on each.
- `src/modules/amazon/amazon_config.py` — `load_amazon_config(path)`, `_validate_amazon_config`, `compute_amazon_config_sha256`, `AmazonConfigError`. Validates: scenario multiplier keys ∈ `_AMAZON_MULTIPLIER_KEYS`, values numeric ≥0; `confidence_rules` enum ∈ {high,medium,low,unknown}; `profit_cost_defaults` non-negative; `supported_marketplaces` non-empty; `score_rules` weights sum to 100.
- `config/amazon_workflow.json` — workflow_version, agent_versions, supported_marketplaces, score_rules (opportunity scoring weights), mock_data_settings, profit_cost_defaults, scenarios (base/optimistic/pessimistic with Amazon multiplier keys), review_categories (the 7 spec categories), output_settings, confidence_rules.

### Phase 2: data layer
- `src/modules/amazon/mock_data.py` — deterministic chicken coop door mock: 4 competitors (MOCK-ASIN-001..004), 12 reviews covering Installation/Quality/Packaging/Feature Request categories, keyword related_terms, market qualitative values. Pure functions, same input → same output.
- `src/modules/amazon/input_loader.py` — `load_product_input(path) -> ProductInput` (validates required `keyword`, `marketplace` ∈ supported_marketplaces, target_price_min ≤ max); `load_competitors_csv(path)`, `load_reviews_csv(path)`. Strict mode: invalid enum/missing required → raise. Merges user input with mock per decision #13.
- `data/amazon/demo_product_input.json` — chicken coop door, Amazon US, $20-50, pet/home/outdoor.
- `data/amazon/demo_competitors.csv` — brand, asin, product_name, price, rating, review_count, selling_points, negative_points, source columns (4 rows, MOCK-ASIN-* identifiers).
- `data/amazon/demo_reviews.csv` — review_id, asin, rating, review_text, review_date, source (12 rows covering 3+ pain categories).

### Phase 3: calculation kernel
- `src/modules/amazon/profit_agent.py` — `AmazonProfitResult` (selling_price, unit_cost, all 13 cost fields, unit_profit, unit_margin, monthly_profit, annualized_profit, roi: Optional[Decimal], scenario, source per cost field), `calculate_amazon_profit(input, scenario_multipliers, scenario_name)`, `_apply_amazon_multipliers`, replicated `_q2`/`_q4`. ROI null when `initial_investment ≤ 0`.

### Phase 4: leaf agents
- `keyword_agent.py` — `KeywordAgent.run(context) -> AgentResult`. Output: `KeywordOutput` (normalized_keyword, related_keywords, keyword_intent, keyword_type, competition, trend, search_volume=None, source=mock_data, confidence=low). Same input → same output.
- `market_agent.py` — `MarketOutput` (marketplace, category, product_line, consumption_scenario, target_customer, market_capacity="qualitative", growth_trend, price_range, competition_level, opportunity_score 1-100 from config score_rules, market_assumptions, source, confidence).
- `competitor_agent.py` — `CompetitorOutput` (competitor_matrix, price_distribution, rating_distribution, review_distribution, common_selling_points, common_negative_points, market_gaps, differentiation_opportunities). Reads from context (user CSV or mock).
- `review_agent.py` — `ReviewOutput` (review_count, sentiment_summary, issue_categories, positive_themes, negative_themes, feature_requests, quality_issues, packaging_issues, product_improvement_directions, confidence, source). Rule-based classification into the 7 categories.
- `opportunity_agent.py` — `OpportunityOutput` (market_opportunity 1-5, competition 1-5, supply_chain_feasibility 1-5, differentiation_potential 1-5, development_recommendation ∈ {develop, validate_first, monitor, reject_or_hold}, reasons, risks, required_validation, confidence, human_review_required). Rules: target price can't cover cost → not `develop`; mock-only data → confidence ≤ medium; no real user validation → `human_review_required=True`.
- `product_agent.py` — `ProductOutput` (product_name, product_positioning, target_customer, use_scenario, core_selling_points derived from prior agents' negative points/feature requests, functional_design, differentiation_plan, target_price, target_cost, target_gross_margin, packaging_direction, installation_direction, development_cycle_days, launch_risks, validation_plan, required_supplier_questions). Degrades to `status=incomplete` if any of keyword/market/competitor/review skipped.

### Phase 5: orchestration + output
- `src/modules/amazon/master_agent.py` — `MasterAgent.run(product_input, config, cli_args, strict, with_mock_data) -> WorkflowContext`. Creates context, runs agents in spec order, catches exceptions per agent, applies strict/non-strict semantics from decision #10, writes intermediate JSONs if requested, returns final context with `final_status`.
- `src/modules/amazon/report_agent.py` — builds `amazon_product_report_<ts>.md` (17 sections, locked `_REPORT_SECTIONS`) and `amazon_product_analysis_<ts>.json` (metadata: input SHA-256, config SHA-256, CLI args, agent_versions, python_version, generated_at, record_counts, final_status). Uses `AmazonDecimalEncoder`, reuses `compute_file_sha256` from `project_report`.
- `src/modules/amazon/excel_agent.py` — `generate_market_excel(context, path)`, `generate_product_excel(context, path)`. Lazy `import openpyxl` inside functions. Market sheets: Market_Analysis, Keyword_Analysis, Competitor_Matrix, Review_Analysis, Data_Quality. Product sheets: Product_Positioning, Product_Features, Differentiation, Cost_Target, Development_Timeline, Risks_Validation. Freeze first row, auto-width (max 60), money/percent/date formats, Decimal→float at boundary. Returns `AgentResult` with `status="skipped"` if openpyxl missing.
- `src/modules/amazon/workflow.py` — CLI: `--input`, `--output-dir` (default `data/amazon/output`), `--config` (default `config/amazon_workflow.json`), `--scenario` (base/optimistic/pessimistic/all), `--with-mock-data`, `--export-intermediate`, `--strict`, `--help`. Orchestrates: load config → validate → load product input → merge mock → MasterAgent.run → report_agent writes MD/JSON → excel_agent writes workbooks. Prints summary (input path, agents run, final_status, MD/JSON/Excel paths). Non-zero exit on failure.

### Phase 6: tests + docs
- 11 test files in `tests/` (listed in spec section 18). Reuse `tests/_helpers.py` fixture pattern (add `make_product_input`, `make_competitor_row`, `make_review_row`, `make_amazon_profit_input` helpers there or in a new `tests/_amazon_helpers.py`). Excel tests use `@unittest.skipUnless(openpyxl_available, "openpyxl not installed")`. The 27 required cases are tracked as `_TEST_CASE_IDS` comments in each test module.
- Update `README.md` — add V3 sections: positioning, V1/V2 relationship, agent architecture, offline runtime note, input JSON format, mock data disclaimer, Excel output, profit calculation口径, three scenarios, CLI examples, test commands, future API integration plan, current limitations, disclaimer that V3 ≠ real Amazon data.
- Update `requirements.txt` — add `openpyxl>=3.1.0  # V3 Excel output (optional; MD/JSON work without it)`.

## Reuse from V1/V2 (do NOT modify these)

- `src/modules/project_report.py:compute_file_sha256(file_path)` — public, reuse for input/config SHA-256.
- Patterns (replicate, don't import): `_q2`/`_q4` Decimal quantization (profit_calculator.py:34-41); `_DecimalEncoder` (project_report.py:34-40, replicate as `AmazonDecimalEncoder`); `ConfigError` style + SHA-256 (config_loader.py:24,236-243); scenario multiplier application pattern (profit_calculator.py:115-140); `resolve_scenarios` shape (scenario_calculator.py:38-83); test fixture pattern (tests/_helpers.py).

## Verification plan

End-to-end acceptance (15 steps from spec section 22):

1. `python -m unittest discover -s tests -p "test_*.py"` → all V1/V2 + V3 tests pass (27 new + 99 existing = 126+).
2. `python -m src.modules.amazon.workflow --input data/amazon/demo_product_input.json --with-mock-data --scenario all --export-intermediate` → exits 0, prints MD/JSON/Excel paths.
3. Verify `data/amazon/output/` contains: `amazon_product_report_<ts>.md`, `amazon_product_analysis_<ts>.json`, `market_report_<ts>.xlsx`, `product_plan_<ts>.xlsx`, `intermediate/01_keyword_<ts>.json` ... `10_excel_<ts>.json`.
4. MD report has all 17 sections in `_REPORT_SECTIONS` order; contains input SHA-256, config SHA-256, CLI args, data source summary (counts by source: user_input/mock_data/calculated), final_status, disclaimer.
5. JSON has `metadata`, `agents` (per-agent AgentResult), `profit` (3 scenarios), `final_status`; Decimals serialized as strings via `AmazonDecimalEncoder`; ROI null in loss scenario.
6. Market Excel opens (openpyxl) with 5 sheets, frozen first row, no empty required cells. Product Excel has 6 sheets.
7. Cross-check: same opportunity_score, target_price, unit_profit, monthly_profit, roi values appear in MD, JSON, and Excel.
8. Failure tests: missing keyword → nonzero exit, clear error; missing config → nonzero exit, `AmazonConfigError`; invalid marketplace → nonzero exit.
9. `--strict` with a forced agent failure → abort, `final_status=failed`; non-strict → `final_status=incomplete`, later independent agents still run.
10. `grep -r "requests\|urllib\|http\|openai\|boto\|amazon_spapi" src/modules/amazon/` → no network imports.
11. `git diff src/core/agent.py` → no changes.
12. `python -m src.modules.analyze_opportunities --input data/raw/demo_opportunities.csv` → V1/V2 CLI still works, exits 0.
13. No API key read from env or files (`grep -r "API_KEY\|api_key\|OPENAI\|AMAZON_SECRET" src/modules/amazon/` → no hits).
14. Excel skip path: temporarily hide openpyxl → MD/JSON still produced, `final_status=completed_with_warnings`.
15. Determinism: run demo twice → identical MD/JSON/Excel content except timestamps.

## Risks

- **openpyxl not on target machine**: mitigated by lazy import + skip status + `@skipUnless` in tests.
- **Source/confidence bookkeeping explosion**: mitigated by `Sourced[T]` generic + helper; agents set defaults once.
- **Decimal→float precision loss in Excel**: documented in excel_agent docstring; JSON/MD keep full Decimal precision.
- **Test isolation**: Amazon tests must not import V1/V2 modules that trigger config defaults; `profit_agent.py` stays stdlib-only.

## Out of scope (per spec)

- Real Amazon/SP-API/OpenAI integration (future "data provider" layer).
- Real market data, search volumes, sales estimates, review scraping.
- Templates directory (generating directly to output).
