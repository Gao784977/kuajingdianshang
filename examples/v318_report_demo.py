"""V3.1.8 — 完整报告输出演示。

演示 V3.1 工作流的三种输出：
1. 市场调研报告（Excel，9 Sheet）— V3.1.4 template_builder
2. 工作流报告（Markdown，10 节）— V3.1.8 _build_markdown_report
3. 工作流结果（JSON）— V3.1.8 to_dict + 文件写入

运行：
    python examples/v318_report_demo.py
"""

from __future__ import annotations

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
    excel_files = [f for f in (kw_fixture,) if f.exists()]

    # ------------------------------------------------------------------
    # 门禁关闭 — 完整报告仍生成
    # ------------------------------------------------------------------
    _print_section("Run: 门禁关闭（完整报告生成）")
    wf = V31Workflow(
        project_name="v318_report_demo",
        excel_files=excel_files,
        config=config,
        output_dir=_OUTPUT_DIR,
    )
    result = wf.run()

    print(f"  项目:                 {result.project_name}")
    print(f"  候选门禁:             {result.candidate_gate_status}")
    print(f"  候选数量:             {len(result.candidates)}")
    print(f"  产品规划:             {len(result.product_plans)}")
    print(f"  利润测算:             {len(result.profit_results)}")

    if result.market_research_report_path:
        print(f"  市场调研 Excel:       {result.market_research_report_path.name}")
    if result.markdown_report_path:
        print(f"  工作流 Markdown:      {result.markdown_report_path.name}")
    if result.json_report_path:
        print(f"  工作流 JSON:          {result.json_report_path.name}")

    # ------------------------------------------------------------------
    # Markdown 报告预览
    # ------------------------------------------------------------------
    if result.markdown_report_path:
        _print_section("Markdown 报告预览（前 40 行）")
        content = result.markdown_report_path.read_text(encoding="utf-8")
        for line in content.splitlines()[:40]:
            print(f"  {line}")

    # ------------------------------------------------------------------
    # 门禁开启 — 产品规划 + 利润测算写入报告
    # ------------------------------------------------------------------
    _print_section("Run: 门禁开启（PC-0001 确认，产品规划写入报告）")
    wf2 = V31Workflow(
        project_name="v318_report_open",
        excel_files=excel_files,
        config=config,
        output_dir=_OUTPUT_DIR,
        confirmed_candidate_ids=["PC-0001"],
    )
    result2 = wf2.run()

    print(f"  候选门禁:             {result2.candidate_gate_status}")
    print(f"  产品规划:             {len(result2.product_plans)}")
    print(f"  利润测算:             {len(result2.profit_results)}")

    if result2.markdown_report_path:
        print(f"  Markdown 报告:        {result2.markdown_report_path.name}")
    if result2.json_report_path:
        print(f"  JSON 结果:            {result2.json_report_path.name}")

    print("\nV3.1.8 演示完成。三种报告已生成到 data/output/。")


if __name__ == "__main__":
    main()
