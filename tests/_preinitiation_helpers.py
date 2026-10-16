"""预立项模块测试公共构造器（src/modules/preinitiation）。

自 S1/S2 独立验证包移植（/workspace/preinitiation/tests/helpers.py），
仅调整导入路径；构造语义与原实现一致。
"""
from __future__ import annotations

from decimal import Decimal

from src.modules.preinitiation.providers import TestOnlyProvider
from src.modules.preinitiation.repository import InMemoryRepository
from src.modules.preinitiation.service import PreinitiationService

TASK = 'task-1'
ASIN = 'B0TEST0001'


def make_service(fixed_margin: Decimal = Decimal('0.18')):
    repo = InMemoryRepository()
    service = PreinitiationService(repo, demo_provider=TestOnlyProvider(fixed_margin))
    return repo, service


def seed_full_input(service, task=TASK, asin=ASIN, **overrides):
    # 注意：selling_price 与 target_margin 互斥（03 §4.1）——正算路径不填目标利润率
    fields = dict(
        selling_price_usd='39.99',
        promotion_fee_ratio='0.10',
        fx_usd_to_cny='7.10',
        target_qty=500,
        estimated_purchase_price_cny='25.00',
    )
    fields.update(overrides)
    return service.create_input_set(task, asin, **fields)


def seed_candidate(service, task=TASK, asin=ASIN, offer_id='offer-1',
                   with_sku_price=True, moq=100, ladder=True):
    skus = [{
        'sku_id': 'sku-1', 'spec': '红色',
        'sku_price_cny': '25.50' if with_sku_price else None,
        'ladder_prices': ([
            {'qty_from': 100, 'qty_to': 499, 'price_cny': '25.50'},
            {'qty_from': 500, 'qty_to': None, 'price_cny': '24.20'},
        ] if ladder else []),
    }]
    return service.add_manual_candidate(
        task, asin, offer_id,
        quote_source='https://detail.1688.com/offer/1.html（截图存档）',
        quoted_at='2026-10-15T10:00:00+08:00',
        offer_price_cny='24.80', moq=moq, skus=skus)


def run_demo_flow(service, task=TASK, asin=ASIN):
    """完整 demo 链路：输入→样例参数→首轮测算→手工候选→选择→复算→快照。"""
    seed_full_input(service, task, asin)
    service.load_sample_params()
    first = service.calculate(task, asin)
    seed_candidate(service, task, asin)
    selection = service.select_candidate(task, asin, 'offer-1', 'sku-1')
    recalc = service.recalculate(task, asin)
    snapshot = service.create_snapshot(task, asin, created_by='tester')
    return first, selection, recalc, snapshot
