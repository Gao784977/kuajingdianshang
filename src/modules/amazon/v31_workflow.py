"""V3.1.7 — V3.1 workflow orchestrator integrating Excel import,
URL fetch, multi-keyword analysis, candidate confirmation, and the
V3.0 :class:`MasterAgent` for product development + profit.

This module sits *above* the V3.0 :class:`MasterAgent` and the V3.1
sub-systems. It does not modify either; it composes them.

Pipeline (spec sections 二-九):

1. **Excel load** (V3.1.1 importers + V3.1.2 normaliser) — read the
   seller-sprite / Brand Analytics workbooks the user supplied.
2. **Analyse** (V3.1.3 analyzers) — multi-keyword, multi-category,
   brand, seller, search-position.
3. **URL fetch** (V3.1.5 url_sources) — gated by
   ``--allow-url-fetch``; only user-provided URLs are fetched.
4. **Market research report** (V3.1.4 template_builder) — always
   produced, even when no candidate is confirmed.
5. **Candidate generation** (V3.1.6 ProductCandidateAgent) —
   produces the candidate list.
6. **Confirmation gate** (V3.1.6 gate_product_agent) — closed until
   the user confirms at least one candidate.
7. **Product + profit** (V3.0 MasterAgent) — only run when the gate
   is open. Each confirmed candidate becomes a :class:`ProductInput`
   for MasterAgent.

When no candidate is confirmed, steps 1-5 still run; step 7 is
replaced with ``status="pending_manual_confirmation"``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from .analyzers import (
    analyze_brands,
    analyze_categories,
    analyze_keywords,
    analyze_search_positions,
    analyze_sellers,
)
from .importers.normalized_models import (
    AmazonProduct,
    AmazonSearchAppearance,
    BrandMetric,
    CategoryMetric,
    KeywordMetric,
    SellerMetric,
)
from .importers.normalizer import (
    normalize_products,
    normalize_search_appearances,
)
from .product_candidate_agent import (
    ProductCandidate,
    ProductCandidateAgent,
    can_proceed_to_product_agent,
    gate_product_agent,
)
from .template_builder import build_market_research_report
from .url_sources import FetchPolicy, UrlFetcher, UrlRegistry
from .url_sources.url_registry import registry_from_input

NAME = "v31_workflow"
VERSION = "v31_workflow_v3_1_7"

_TIMESTAMP_FMT = "%Y%m%d_%H%M%S"


@dataclass
class V31WorkflowResult:
    """Aggregate result of a full V3.1 workflow run.

    Attributes:
        project_name: Echo of the input project name.
        analyzer_results: Dict passed to / produced for every
            downstream consumer (report builder, candidate agent).
        market_research_report_path: Path to the
            ``{project_name}_market_research_report_{ts}.xlsx``.
        candidates: List of :class:`ProductCandidate`.
        candidate_gate_status: ``"open"`` when at least one candidate
            is confirmed; ``"closed"`` otherwise.
        product_plans: List of MasterAgent run outputs, one per
            confirmed candidate. Empty when the gate is closed.
        profit_results: List of profit agent outputs, parallel to
            ``product_plans``. Empty when the gate is closed.
        warnings: Workflow-level warnings.
        errors: Workflow-level errors.
        generated_at: Timestamp string.
    """

    project_name: str = ""
    analyzer_results: Dict[str, Any] = field(default_factory=dict)
    market_research_report_path: Optional[Path] = None
    json_report_path: Optional[Path] = None
    markdown_report_path: Optional[Path] = None
    candidates: List[ProductCandidate] = field(default_factory=list)
    candidate_gate_status: str = "closed"
    product_plans: List[Dict[str, Any]] = field(default_factory=list)
    profit_results: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "analyzer_results_keys": list(self.analyzer_results.keys()),
            "market_research_report_path": (
                str(self.market_research_report_path)
                if self.market_research_report_path
                else None
            ),
            "json_report_path": (
                str(self.json_report_path) if self.json_report_path else None
            ),
            "markdown_report_path": (
                str(self.markdown_report_path) if self.markdown_report_path else None
            ),
            "candidates": [c.to_dict() for c in self.candidates],
            "candidate_gate_status": self.candidate_gate_status,
            "product_plans": list(self.product_plans),
            "profit_results": list(self.profit_results),
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "generated_at": self.generated_at,
        }


@dataclass
class V31Workflow:
    """Orchestrate the V3.1 pipeline.

    Args:
        project_name: Used in the output filename (never hardcoded).
        excel_files: List of user-supplied Excel paths.
        user_input: The full user input JSON dict (for URLs,
            manual_inputs, supplier_information, product_candidates).
        config: V3.0 config dict (used by MasterAgent when invoked).
        cli_args: CLI arguments dict. Recognised keys:

            * ``allow_url_fetch`` (bool) — master switch for URL
              fetching.
            * ``strict`` (bool) — strict mode.
            * ``export_intermediate`` (bool) — write per-stage JSON.
            * ``with_mock_data`` (bool) — pass-through to MasterAgent.
        output_dir: Destination for the market research report and
            (when produced) product plans. Defaults to
            ``data/output/``.
        template_path: Optional pre-built template path from
            :func:`extract_templates`. When None, the report is
            built from scratch with the 9 sheet names.
        confirmed_candidate_ids: Optional list of candidate IDs the
            user has confirmed in a prior run. These are marked
            ``confirmed`` on the new candidates so MasterAgent may
            proceed without re-confirmation.
        url_transport: Optional transport for URL fetcher (test seam).
    """

    project_name: str = "project"
    excel_files: List[Path] = field(default_factory=list)
    user_input: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    cli_args: Dict[str, Any] = field(default_factory=dict)
    output_dir: Path = field(default_factory=lambda: Path("data/output"))
    template_path: Optional[Path] = None
    confirmed_candidate_ids: List[str] = field(default_factory=list)
    url_transport: Optional[Any] = None

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def run(self) -> V31WorkflowResult:
        """Run the full V3.1 pipeline and return the aggregate result."""
        ts = datetime.now().strftime(_TIMESTAMP_FMT)
        result = V31WorkflowResult(
            project_name=self.project_name,
            generated_at=ts,
        )

        # 1. Load Excel files
        products, search_appearances, keywords, categories, brands, sellers = (
            self._load_excel()
        )
        result.warnings.append(
            f"Loaded {len(products)} products, {len(search_appearances)} search "
            f"appearances, {len(keywords)} keywords from {len(self.excel_files)} files."
        )
        if self._missing_files:
            result.warnings.append(
                f"Missing Excel files (skipped): "
                f"{', '.join(self._missing_files)}"
            )
        if self._load_errors:
            result.errors.extend(self._load_errors)

        # 2. Normalise
        norm_products = normalize_products(products)
        norm_searches = normalize_search_appearances(search_appearances)

        # 3. Analyse
        analyzer_results: Dict[str, Any] = {}
        analyzer_results["multi_keyword"] = analyze_keywords(keywords).to_dict()
        analyzer_results["multi_category"] = analyze_categories(categories).to_dict()
        analyzer_results["brand"] = analyze_brands(brands).to_dict()
        analyzer_results["seller"] = analyze_sellers(sellers).to_dict()
        analyzer_results["search_position"] = analyze_search_positions(
            norm_searches.appearances
        ).to_dict()
        analyzer_results["products"] = [
            p.to_dict() if hasattr(p, "to_dict") else dict(p)
            for p in norm_products.deduped_products
        ]
        result.analyzer_results = analyzer_results

        # 4. URL fetch (if allowed)
        if self.cli_args.get("allow_url_fetch"):
            url_results = self._fetch_urls()
            analyzer_results["url_fetches"] = url_results
            result.warnings.append(
                f"Fetched {sum(1 for u in url_results if u.get('success'))} URLs "
                f"({sum(1 for u in url_results if not u.get('success'))} failed)."
            )
        else:
            result.warnings.append(
                "URL fetch disabled (--allow-url-fetch not set); "
                "continuing with Excel data only."
            )

        # 5. Market research report (always produced)
        report_result = build_market_research_report(
            project_name=self.project_name,
            analyzer_results=analyzer_results,
            template_path=self.template_path,
            output_dir=self.output_dir,
        )
        if report_result.output_path:
            result.market_research_report_path = report_result.output_path
            result.warnings.append(
                f"Market research report: {report_result.output_path.name} "
                f"({len(report_result.sheets_written)} sheets)."
            )
        else:
            result.errors.extend(report_result.errors)

        # 6. Product candidates
        candidate_agent = ProductCandidateAgent()
        candidate_result = candidate_agent.run(
            analyzer_results,
            confirmed_candidates=self.confirmed_candidate_ids,
        )
        candidates_dicts = candidate_result.output.get("candidates", [])
        result.candidates = [
            self._dict_to_candidate(c) for c in candidates_dicts
        ]

        # 7. Gate + product/profit
        if can_proceed_to_product_agent(result.candidates):
            result.candidate_gate_status = "open"
            confirmed = [
                c for c in result.candidates
                if c.status == "confirmed"
            ]
            plans, profits = self._run_product_and_profit(confirmed)
            result.product_plans = plans
            result.profit_results = profits
            result.warnings.append(
                f"Product/profit run for {len(confirmed)} confirmed candidates."
            )
        else:
            result.candidate_gate_status = "closed"
            gate = gate_product_agent(result.candidates)
            result.warnings.append(
                f"Product/profit gated off ({gate.status}); "
                f"{gate.output.get('pending_count', 0)} candidates pending "
                f"manual confirmation."
            )

        # 8. Write Markdown + JSON reports (always, even when gate closed)
        self._write_reports(result)

        return result

    # ------------------------------------------------------------------
    # Stage implementations
    # ------------------------------------------------------------------

    def _load_excel(self):
        """Load all Excel files and return the six typed lists.

        Uses :func:`detect_workbook` to classify each file, then
        dispatches to the matching loader's :func:`load` function. All
        loaders return a :class:`LoaderResult` whose ``records`` list
        is merged into the matching typed list. Market files contribute
        category metrics (not products/searches).
        """
        from .importers.brand_loader import load as load_brands
        from .importers.category_loader import load as load_categories
        from .importers.keyword_loader import load as load_keywords
        from .importers.market_loader import load as load_market
        from .importers.product_loader import load as load_products
        from .importers.search_loader import load as load_search
        from .importers.seller_loader import load as load_sellers
        from .importers.workbook_detector import detect_workbook

        products: List[AmazonProduct] = []
        search_appearances: List[AmazonSearchAppearance] = []
        keywords: List[KeywordMetric] = []
        categories: List[CategoryMetric] = []
        brands: List[BrandMetric] = []
        sellers: List[SellerMetric] = []

        for excel_path in self.excel_files:
            path = Path(excel_path)
            if not path.exists():
                self._missing_files.append(str(path))
                continue
            try:
                detection = detect_workbook(str(path))
                kind = detection.detected_type
                if kind == "products":
                    products.extend(load_products(str(path)).records)
                elif kind == "search":
                    search_appearances.extend(load_search(str(path)).records)
                elif kind == "keyword":
                    keywords.extend(load_keywords(str(path)).records)
                elif kind == "category":
                    categories.extend(load_categories(str(path)).records)
                elif kind in ("brand_analytics", "brands"):
                    brands.extend(load_brands(str(path)).records)
                elif kind == "sellers":
                    sellers.extend(load_sellers(str(path)).records)
                elif kind == "market":
                    # Market files contribute category-level metrics.
                    categories.extend(load_market(str(path)).records)
            except Exception as exc:  # noqa: BLE001
                self._load_errors.append(f"{path}: {type(exc).__name__}: {exc}")

        return products, search_appearances, keywords, categories, brands, sellers

    def _fetch_urls(self) -> List[Dict[str, Any]]:
        """Fetch all registered URLs. Returns a list of FetchResult dicts."""
        registry = registry_from_input(self.user_input)
        policy = FetchPolicy(
            allow_url_fetch=True,
            strict=bool(self.cli_args.get("strict", False)),
        )
        fetcher = UrlFetcher(
            policy=policy,
            registry=registry,
            transport=self.url_transport,
        )
        results = []
        for entry in registry:
            result = fetcher.fetch(entry.source_url)
            results.append(result.to_dict())
        return results

    def _run_product_and_profit(
        self,
        confirmed_candidates: List[ProductCandidate],
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Run V3.0 MasterAgent for each confirmed candidate.

        Returns (product_plans, profit_results) — two parallel lists.
        """
        # Lazy imports — MasterAgent pulls in V3.0 deps that are
        # heavier than the V3.1 sub-systems.
        from .master_agent import MasterAgent
        from .models import AmazonProfitResult, ProductInput, ProductOutput

        plans: List[Dict[str, Any]] = []
        profits: List[Dict[str, Any]] = []
        master = MasterAgent()

        for candidate in confirmed_candidates:
            product_input = ProductInput(
                keyword=candidate.top_keyword,
                marketplace=self.user_input.get("marketplace", "US"),
                source="user_input",
                confidence="high",
                notes=candidate.suggested_differentiation,
            )
            try:
                context = master.run(
                    product_input=product_input,
                    config=self.config,
                    cli_args=self.cli_args,
                    strict=bool(self.cli_args.get("strict", False)),
                    with_mock_data=bool(self.cli_args.get("with_mock_data", True)),
                )
                product_out = context.get_output("product", ProductOutput)
                profit_out = context.get_output("profit", AmazonProfitResult)
                plans.append({
                    "candidate_id": candidate.candidate_id,
                    "final_status": context.final_status,
                    "product_output": (
                        product_out.to_dict() if product_out else None
                    ),
                })
                profits.append({
                    "candidate_id": candidate.candidate_id,
                    "profit_output": (
                        profit_out.to_dict() if profit_out else None
                    ),
                })
            except Exception as exc:  # noqa: BLE001
                plans.append({
                    "candidate_id": candidate.candidate_id,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                profits.append({
                    "candidate_id": candidate.candidate_id,
                    "error": "profit not run (product failed)",
                })
        return plans, profits

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # Populated by _load_excel on missing-file / loader errors.
    _missing_files: List[str] = field(default_factory=list, init=False, repr=False)
    _load_errors: List[str] = field(default_factory=list, init=False, repr=False)

    @staticmethod
    def _dict_to_candidate(d: Dict[str, Any]) -> ProductCandidate:
        """Reconstruct a ProductCandidate from its dict form."""
        score = d.get("opportunity_score")
        return ProductCandidate(
            candidate_id=d.get("candidate_id", ""),
            product_name=d.get("product_name", ""),
            top_keyword=d.get("top_keyword", ""),
            opportunity_score=Decimal(str(score)) if score is not None else None,
            reference_asins=list(d.get("reference_asins") or []),
            suggested_differentiation=d.get("suggested_differentiation", ""),
            status=d.get("status", "pending_review"),
            reviewer=d.get("reviewer", ""),
            review_notes=d.get("review_notes", ""),
            source_files=list(d.get("source_files") or []),
            confidence=d.get("confidence", "medium"),
            requires_review=d.get("requires_review", True),
        )

    # ------------------------------------------------------------------
    # Report writing (V3.1.8)
    # ------------------------------------------------------------------

    def _write_reports(self, result: "V31WorkflowResult") -> None:
        """Write the Markdown and JSON reports to ``self.output_dir``.

        Filenames:
        * JSON: ``{project_name}_v31_workflow_{ts}.json``
        * MD:   ``{project_name}_v31_workflow_{ts}.md``

        Both are always written (even when the candidate gate is
        closed), so the user has an audit trail of every workflow run.
        """
        ts = result.generated_at or datetime.now().strftime(_TIMESTAMP_FMT)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        safe_name = _sanitize_filename(result.project_name)

        # Pre-set the paths so they are included in the JSON output.
        json_path = self.output_dir / f"{safe_name}_v31_workflow_{ts}.json"
        md_path = self.output_dir / f"{safe_name}_v31_workflow_{ts}.md"
        result.json_report_path = json_path
        result.markdown_report_path = md_path

        # JSON report — full serialisable snapshot
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2, ensure_ascii=False,
                          default=str)
        except Exception as exc:  # noqa: BLE001
            result.json_report_path = None
            result.errors.append(f"JSON report write failed: {type(exc).__name__}: {exc}")

        # Markdown report — human-readable summary
        try:
            md_content = _build_markdown_report(result, version=VERSION)
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(md_content)
        except Exception as exc:  # noqa: BLE001
            result.markdown_report_path = None
            result.errors.append(f"Markdown report write failed: {type(exc).__name__}: {exc}")


def _sanitize_filename(name: str) -> str:
    """Sanitize a project name for use in a filename.

    Keeps alphanumeric, CJK, hyphen, underscore, space. Replaces
    everything else (including path separators / ?) with underscore.
    """
    if not name:
        return "project"
    out = []
    for ch in name:
        if ch.isalnum() or ch in "-_ " or "\u4e00" <= ch <= "\u9fff":
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip() or "project"


def _build_markdown_report(result: "V31WorkflowResult", *, version: str) -> str:
    """Build the V3.1 workflow Markdown report.

    Sections (locked order, spec section 八/九):
    1. 执行摘要
    2. 项目信息
    3. 分析器结果概览
    4. 产品候选列表
    5. 候选确认门禁状态
    6. 产品开发规划（仅 gate open 时）
    7. 利润测算结果（仅 gate open 时）
    8. 警告与错误
    9. 输出文件清单
    10. 可追溯信息
    """
    lines: List[str] = []
    L = lines.append

    L(f"# V3.1 市场调研与产品开发工作流报告")
    L("")
    L(f"**项目名称**: {result.project_name}")
    L(f"**生成时间**: {result.generated_at}")
    L(f"**工作流版本**: {version}")
    L("")

    # 1. 执行摘要
    L("## 1. 执行摘要")
    L("")
    n_candidates = len(result.candidates)
    n_confirmed = sum(1 for c in result.candidates if c.status == "confirmed")
    L(f"- 候选产品数量: **{n_candidates}**")
    L(f"- 已确认候选: **{n_confirmed}**")
    L(f"- 候选门禁状态: **{result.candidate_gate_status}**")
    L(f"- 产品规划数量: **{len(result.product_plans)}**")
    L(f"- 利润测算数量: **{len(result.profit_results)}**")
    L(f"- 警告数: {len(result.warnings)}")
    L(f"- 错误数: {len(result.errors)}")
    L("")

    # 2. 项目信息
    L("## 2. 项目信息")
    L("")
    L(f"- 项目名称: {result.project_name}")
    L(f"- 生成时间: {result.generated_at}")
    L(f"- 市场调研报告: "
      f"{result.market_research_report_path.name if result.market_research_report_path else '未生成'}")
    L("")

    # 3. 分析器结果概览
    L("## 3. 分析器结果概览")
    L("")
    for key in result.analyzer_results.keys():
        if key == "products":
            n = len(result.analyzer_results.get("products", []))
            L(f"- **{key}**: {n} 条商品记录")
        elif key == "url_fetches":
            fetches = result.analyzer_results.get("url_fetches", [])
            ok = sum(1 for f in fetches if f.get("success"))
            L(f"- **{key}**: {ok}/{len(fetches)} 成功")
        else:
            L(f"- **{key}**: 已生成")
    L("")

    # 4. 产品候选列表
    L("## 4. 产品候选列表")
    L("")
    if not result.candidates:
        L("_暂无候选产品（未加载关键词数据）_")
    else:
        L("| 候选ID | 产品名称 | 主关键词 | 机会分 | 状态 | 建议差异化 |")
        L("| --- | --- | --- | --- | --- | --- |")
        for c in result.candidates:
            score = c.opportunity_score
            L(f"| {c.candidate_id} | {c.product_name} | {c.top_keyword} "
              f"| {score} | {c.status} | {c.suggested_differentiation} |")
    L("")

    # 5. 候选确认门禁状态
    L("## 5. 候选确认门禁状态")
    L("")
    if result.candidate_gate_status == "open":
        L(f"门禁状态: **open** — 已确认 {n_confirmed} 个候选，产品开发 Agent 已运行。")
    else:
        L("门禁状态: **closed** — 无已确认候选。")
        L("")
        L("> 产品开发规划和利润测算已被门禁阻断。")
        L("> 请在候选列表中确认至少一个候选（设置 `confirmed_candidate_ids`），")
        L("> 然后重新运行工作流以生成产品规划和利润测算。")
    L("")

    # 6. 产品开发规划
    L("## 6. 产品开发规划")
    L("")
    if result.candidate_gate_status == "open" and result.product_plans:
        for plan in result.product_plans:
            cid = plan.get("candidate_id", "")
            L(f"### 候选 {cid}")
            L("")
            if "error" in plan:
                L(f"**运行失败**: {plan['error']}")
                L("")
                continue
            L(f"- 最终状态: {plan.get('final_status', 'N/A')}")
            po = plan.get("product_output") or {}
            if po:
                L(f"- 产品名称: {po.get('product_name', 'N/A')}")
                L(f"- 目标价格: {po.get('target_price', 'N/A')}")
                L(f"- 目标成本: {po.get('target_cost', 'N/A')}")
                L(f"- 目标毛利率: {po.get('target_gross_margin', 'N/A')}")
            L("")
    else:
        L("_门禁关闭（无已确认候选），产品开发规划未生成。_")
        L("")

    # 7. 利润测算结果
    L("## 7. 利润测算结果")
    L("")
    if result.candidate_gate_status == "open" and result.profit_results:
        for profit in result.profit_results:
            cid = profit.get("candidate_id", "")
            L(f"### 候选 {cid}")
            L("")
            if "error" in profit:
                L(f"**运行失败**: {profit['error']}")
                L("")
                continue
            pf = profit.get("profit_output") or {}
            if pf:
                L(f"- 情景: {pf.get('scenario', 'N/A')}")
                L(f"- 单价: {pf.get('selling_price', 'N/A')}")
                L(f"- 月利润: {pf.get('monthly_profit', 'N/A')}")
                L(f"- 年化利润: {pf.get('annualized_profit', 'N/A')}")
                L(f"- ROI: {pf.get('roi', 'N/A')}")
            L("")
    else:
        L("_门禁关闭（无已确认候选），利润测算未生成。_")
        L("")

    # 8. 警告与错误
    L("## 8. 警告与错误")
    L("")
    if result.warnings:
        L("### 警告")
        L("")
        for w in result.warnings:
            L(f"- {w}")
        L("")
    if result.errors:
        L("### 错误")
        L("")
        for e in result.errors:
            L(f"- {e}")
        L("")
    if not result.warnings and not result.errors:
        L("_无警告或错误_")
        L("")

    # 9. 输出文件清单
    L("## 9. 输出文件清单")
    L("")
    if result.market_research_report_path:
        L(f"- 市场调研报告 (Excel): `{result.market_research_report_path.name}`")
    if result.markdown_report_path:
        L(f"- 工作流报告 (Markdown): `{result.markdown_report_path.name}`")
    if result.json_report_path:
        L(f"- 工作流结果 (JSON): `{result.json_report_path.name}`")
    L("")

    # 10. 可追溯信息
    L("## 10. 可追溯信息")
    L("")
    L(f"- 工作流版本: {version}")
    L(f"- 生成时间: {result.generated_at}")
    L(f"- 候选门禁: {result.candidate_gate_status}")
    L(f"- 警告数: {len(result.warnings)}")
    L(f"- 错误数: {len(result.errors)}")
    L("")
    L("---")
    L("")
    L("_本报告由 V3.1 工作流自动生成。候选产品需人工确认后方可进入产品开发阶段。_")

    return "\n".join(lines)


__all__ = ["NAME", "VERSION", "V31Workflow", "V31WorkflowResult"]
