"""预立项决策预览 · 最小可执行示例 —— demo 模式全链路走查（test_only 提供者）。

运行：cd /workspace/repo-kuajingdianshang && python3 -c \
    "from src.modules.preinitiation import example; example.main()"

本示例全程演示域（demo）：固定测试结果、样例参数、模拟确认。
不产生真实产品、不提交正式审批、不调用任何外部系统。
真实测算入口与正式确认当前均 blocked（原因见输出）。
"""
from __future__ import annotations

from decimal import Decimal

from .domain import Mode
from .providers import TestOnlyProvider
from .repository import InMemoryRepository
from .service import PreinitiationService

TASK_ID = 'dev-task-1001'
ASIN = 'B0TESTASIN01'


def line(title: str) -> None:
    print(f"\n{'=' * 64}\n{title}\n{'=' * 64}")


def main() -> None:
    repo = InMemoryRepository()
    service = PreinitiationService(repo, demo_provider=TestOnlyProvider(fixed_margin=Decimal('0.18')))

    line('[0] 内存 Repository 保证范围（显式声明）')
    print(repo.guarantee)

    line('[1] 创建输入集（双版本管理；售价与目标利润率互斥录入）')
    input_set = service.create_input_set(
        TASK_ID, ASIN,
        selling_price_usd='39.99',         # 正算路径：录入售价（目标利润率互斥，不可同填）
        promotion_fee_ratio='0.10',
        fx_usd_to_cny='7.10', fx_fetched_at='2026-10-15T09:00:00+08:00',
        target_qty=500,
        estimated_purchase_price_cny='25.00',   # 首轮估算采购价
        updated_by='dev-user-1',
    )
    print(f"input_version={input_set.input_version} meta_version={input_set.meta_version}")
    try:
        service.update_input(TASK_ID, ASIN, calc_fields={'target_margin_pct': '0.15'})
    except ValueError as exc:
        print(f"互斥校验: 同时提供售价与目标利润率 → 拒绝（{exc}）")

    line('[2] 载入样例参数（sample_parameters=True，仅 demo 域可用）')
    params = service.load_sample_params()
    print(f"params_version={params.params_version} sample_parameters={params.sample_parameters} source={params.source}")

    line('[3] 首轮测算（demo，使用首轮估算采购价；test_only 固定结果）')
    first = service.calculate(TASK_ID, ASIN, Mode.DEMO)
    print(f"calc_status={first.calc_status} verification={first.verification}")
    print(f"company_margin={first.company_margin} target_margin_check={first.target_margin_check}"
          "（未录目标利润率，校验字段独立于结果有效性）")
    print(f"purchase_price={first.purchase_price_cny}({first.purchase_price_kind}) sample_parameters={first.sample_parameters}")

    line('[4] 真实测算入口（real）——公式未验证，blocked 并返回原因清单')
    real = service.calculate(TASK_ID, ASIN, Mode.REAL)
    print(f"calc_status={real.calc_status}")
    for reason in real.reasons:
        print(f"  - {reason}")
    print(f"company_margin={real.company_margin}（blocked 不输出任何数值）")

    line('[5] 录入手工候选（quote_source/quoted_at 必填；准入=unknown）')
    candidate = service.add_manual_candidate(
        TASK_ID, ASIN, 'offer-8801',
        quote_source='https://detail.1688.com/offer/8801.html（页面截图存档）',
        quoted_at='2026-10-15T10:30:00+08:00',
        offer_price_cny='24.80',           # 搜索/摘要报价——仅展示
        tax_inclusive=None,                # 含税口径未知（不得臆断）
        moq=100,
        skus=[
            {'sku_id': 'sku-red', 'spec': '红色', 'sku_price_cny': '25.50',
             'ladder_prices': [
                 {'qty_from': 100, 'qty_to': 499, 'price_cny': '25.50'},
                 {'qty_from': 500, 'qty_to': None, 'price_cny': '24.20'},
             ]},
            {'sku_id': 'sku-blue', 'spec': '蓝色', 'sku_price_cny': None},  # 无 SKU 级价格
        ],
    )
    print(f"offer_id={candidate.offer_id} admission_status={candidate.admission_status}（manual ≠ 已满足准入）")
    print(f"tax_inclusive={candidate.tax_inclusive}（未知） moq={candidate.moq}")

    line('[6] 选择 SKU（有效采购价只取 SKU 级；搜索报价仅展示）')
    selection = service.select_candidate(TASK_ID, ASIN, 'offer-8801', 'sku-red')
    print(f"offer 摘要价（仅展示）={selection['offer_price_cny_display']}")
    print(f"有效采购价={selection['effective_purchase_price_cny']}（target_qty=500 命中阶梯档 24.20）")
    print(f"qty_check={selection['qty_check']} admission_status={selection['admission_status']}")

    line('[7] 有效采购价复算（demo）')
    recalc = service.recalculate(TASK_ID, ASIN, Mode.DEMO)
    print(f"calc_status={recalc.calc_status} margin={recalc.company_margin} "
          f"purchase_price={recalc.purchase_price_cny}({recalc.purchase_price_kind})")

    line('[8] 生成决策快照（内容不可变 + 事件仅追加）')
    snapshot = service.create_snapshot(TASK_ID, ASIN, created_by='dev-user-1')
    content = snapshot.content()
    print(f"snapshot_id={content['snapshot_id']} snapshot_seq={content['snapshot_seq']}")
    print(f"input_version_ref={content['input_version_ref']} params_version_ref={content['params_version_ref']}")
    print(f"calc_version_ref={content['calc_version_ref']}（计算结果版本，区别于输入/参数/候选版本）")
    print(f"effective_price={content['effective_purchase_price_cny']} qty_check={content['qty_check']}")
    print(f"verification={content['verification']} mode={content['mode']} sample_parameters={content['sample_parameters']}")

    line('[8b] 快照幂等：同一计算结果重复请求不重复创建')
    again = service.create_snapshot(TASK_ID, ASIN, created_by='dev-user-1')
    print(f"重复请求返回同一快照={again.snapshot_id == snapshot.snapshot_id}"
          f" 快照总数={len(repo.snapshots(TASK_ID, ASIN))}（snapshot_seq 不重复递增）")

    line('[9] 模拟确认（幂等；事件 demo_confirmed，展示「模拟确认」）')
    r1 = service.demo_confirm(snapshot.snapshot_id, actor='dev-user-1')
    r2 = service.demo_confirm(snapshot.snapshot_id, actor='dev-user-1')
    print(f"第一次: ok={r1['ok']} status={r1['status']} display={r1['display']}")
    print(f"第二次: ok={r2['ok']} already={r2.get('already', False)}（幂等，不重复产生事件）")
    print(f"事件数={len(snapshot.events)} kinds={[e.kind for e in snapshot.events]}")

    line('[10] 正式确认——七项门禁（当前必拒，返回原因清单）')
    r = service.real_confirm(snapshot.snapshot_id, actor='dev-user-1')
    print(f"ok={r['ok']}")
    for reason in r['reasons']:
        print(f"  - {reason}")

    line('[11] 导出「待核验预览单」（强制水印 + 版本 + 过期状态）')
    export = service.export_snapshot(snapshot.snapshot_id)
    print(f"preview_notice={export['preview_notice']}")
    print(f"watermark={export['watermark']}")
    print(f"snapshot_versions={export['snapshot_versions']}")
    print(f"expired={export['expired']}（导出时刻是否仍代表当前版本）")
    print(f"machine_readable={export['machine_readable']}")
    print(f"confirm_display={export['confirm_display']}")

    line('[12] 转待开发产品占位——要求 real 确认，当前 blocked')
    r = service.convert_to_pending_product(snapshot.snapshot_id, created_by='dev-user-1')
    print(f"ok={r['ok']} reasons={r['reasons']} current_status={r['current_status']}")
    print(f"已生成待开发产品数={len(repo.pending_products())}（无真实产品生成）")

    line('[13] 修改输入 → input_version+1：旧快照不再代表当前版本（内容不变）')
    before = snapshot.content()
    updated = service.update_input(TASK_ID, ASIN, calc_fields={'selling_price_usd': '42.99'})
    print(f"input_version: {input_set.input_version} -> {updated.input_version}")
    v = service.versions(TASK_ID, ASIN)
    print(f"旧快照 is_current={snapshot.is_current(updated.input_version, v['params_version'], v['sourcing_version'])}（派生属性）")
    print(f"旧快照内容未变={snapshot.content() == before}（历史快照保留原始内容）")
    stale_real = service.real_confirm(snapshot.snapshot_id, actor='dev-user-1')
    print(f"旧快照正式确认被拒（含 result_stale）={'result_stale' in stale_real['reasons']}")

    line('[14] 备注（meta）修改 → 仅 meta_version+1，不触发失效')
    meta_updated = service.update_input(TASK_ID, ASIN, meta_fields={'note': '竞品对标备注'})
    print(f"input_version={meta_updated.input_version}（不变） meta_version={meta_updated.meta_version}（+1）")

    print('\n示例结束：以上全部为演示域（demo/test_only/样例参数），'
          '不可用于真实立项。')


if __name__ == '__main__':
    main()
