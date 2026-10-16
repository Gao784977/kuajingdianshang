"""S2 审计新增测试：阶梯价边界与非法数据、候选币种、候选/选择依赖、快照不可变性。

对应 S2 任务"先核查现有交付"发现的缺陷最小修复：
- 阶梯价无校验（重复/重叠/非法区间/非法单价/多开区间）；
- 候选币种未校验（有效采购价口径必须 CNY）；
- 候选新增/编辑/选择变化未纳入结果依赖（sourcing_version）；
- 快照事件对象可被调用方改写（应为 frozen）。
"""
import dataclasses
import unittest
from decimal import Decimal

from src.modules.preinitiation.providers import TestOnlyProvider
from src.modules.preinitiation.repository import InMemoryRepository
from src.modules.preinitiation.service import PreinitiationService
from tests._preinitiation_helpers import ASIN, TASK, make_service, run_demo_flow, seed_candidate, seed_full_input


def _svc(fixed_margin=Decimal('0.18')):
    repo = InMemoryRepository()
    return repo, PreinitiationService(repo, demo_provider=TestOnlyProvider(fixed_margin))


def _add_with_ladder(service, ladder, sku_price='25.50', offer='offer-L'):
    # 仅在尚无输入集时初始化，避免覆盖测试已设定的 target_qty
    if service.versions(TASK, ASIN)['input_version'] is None:
        seed_full_input(service)
    return service.add_manual_candidate(
        TASK, ASIN, offer,
        quote_source='https://detail.1688.com/offer/L.html', quoted_at='2026-10-15T10:00:00+08:00',
        offer_price_cny='24.80', moq=100,
        skus=[{'sku_id': 'sku-1', 'spec': '红色', 'sku_price_cny': sku_price,
               'ladder_prices': ladder}])


class TestLadderValidation(unittest.TestCase):
    def test_invalid_range_rejected(self):
        _, service = _svc()
        with self.assertRaises(ValueError) as ctx:
            _add_with_ladder(service, [{'qty_from': 100, 'qty_to': 50, 'price_cny': '25'}])
        self.assertIn('invalid_ladder_range', str(ctx.exception))

    def test_qty_from_zero_rejected(self):
        _, service = _svc()
        with self.assertRaises(ValueError) as ctx:
            _add_with_ladder(service, [{'qty_from': 0, 'qty_to': 99, 'price_cny': '25'}])
        self.assertIn('invalid_ladder_qty_from', str(ctx.exception))

    def test_duplicate_tier_rejected(self):
        _, service = _svc()
        with self.assertRaises(ValueError) as ctx:
            _add_with_ladder(service, [
                {'qty_from': 100, 'qty_to': 199, 'price_cny': '25'},
                {'qty_from': 100, 'qty_to': None, 'price_cny': '24'},
            ])
        self.assertIn('duplicate_ladder_tier', str(ctx.exception))

    def test_overlapping_tier_rejected(self):
        _, service = _svc()
        with self.assertRaises(ValueError) as ctx:
            _add_with_ladder(service, [
                {'qty_from': 100, 'qty_to': 499, 'price_cny': '25'},
                {'qty_from': 400, 'qty_to': None, 'price_cny': '24'},
            ])
        self.assertIn('overlapping_ladder_tier', str(ctx.exception))

    def test_multiple_open_tier_rejected(self):
        _, service = _svc()
        with self.assertRaises(ValueError) as ctx:
            _add_with_ladder(service, [
                {'qty_from': 100, 'qty_to': None, 'price_cny': '25'},
                {'qty_from': 500, 'qty_to': None, 'price_cny': '24'},
            ])
        self.assertIn('multiple_open_ladder_tier', str(ctx.exception))

    def test_invalid_ladder_price_rejected(self):
        _, service = _svc()
        with self.assertRaises(ValueError) as ctx:
            _add_with_ladder(service, [{'qty_from': 100, 'qty_to': None, 'price_cny': '0'}])
        self.assertIn('invalid_ladder_price', str(ctx.exception))

    def test_duplicate_sku_id_rejected(self):
        _, service = _svc()
        seed_full_input(service)
        with self.assertRaises(ValueError) as ctx:
            service.add_manual_candidate(
                TASK, ASIN, 'offer-D',
                quote_source='https://x', quoted_at='2026-10-15',
                skus=[{'sku_id': 's', 'sku_price_cny': '10'},
                      {'sku_id': 's', 'sku_price_cny': '11'}])
        self.assertIn('duplicate_sku_id', str(ctx.exception))

    def test_invalid_sku_price_rejected(self):
        _, service = _svc()
        seed_full_input(service)
        with self.assertRaises(ValueError) as ctx:
            service.add_manual_candidate(
                TASK, ASIN, 'offer-P',
                quote_source='https://x', quoted_at='2026-10-15',
                skus=[{'sku_id': 's', 'sku_price_cny': '-1'}])
        self.assertIn('invalid_sku_price', str(ctx.exception))

    def test_boundary_qty_selects_correct_tier(self):
        """阶梯价边界：qty=499/500 分别命中相邻档位（边界含上界）。"""
        _, service = _svc()
        seed_full_input(service, target_qty=499)
        service.load_sample_params()
        _add_with_ladder(service, [
            {'qty_from': 100, 'qty_to': 499, 'price_cny': '25.50'},
            {'qty_from': 500, 'qty_to': None, 'price_cny': '24.20'},
        ])
        service.calculate(TASK, ASIN)
        s499 = service.select_candidate(TASK, ASIN, 'offer-L', 'sku-1')
        self.assertEqual(s499['effective_purchase_price_cny'], '25.50')
        self.assertEqual(s499['qty_check'], 'passed')

        service.update_input(TASK, ASIN, calc_fields={'target_qty': 500})
        s500 = service.select_candidate(TASK, ASIN, 'offer-L', 'sku-1')
        self.assertEqual(s500['effective_purchase_price_cny'], '24.20')
        self.assertEqual(s500['qty_check'], 'passed')

    def test_gap_in_ladder_violated(self):
        """阶梯价区间存在空档 → 采购量落在空档 → violated + 原因码。"""
        _, service = _svc()
        seed_full_input(service, target_qty=550)
        service.load_sample_params()
        _add_with_ladder(service, [
            {'qty_from': 100, 'qty_to': 499, 'price_cny': '25.50'},
            {'qty_from': 600, 'qty_to': None, 'price_cny': '24.20'},
        ])
        service.calculate(TASK, ASIN)
        sel = service.select_candidate(TASK, ASIN, 'offer-L', 'sku-1')
        self.assertEqual(sel['qty_check'], 'violated')
        self.assertEqual(sel['qty_check_reason'], 'qty_out_of_ladder_range')


class TestCandidateCurrency(unittest.TestCase):
    def test_non_cny_currency_rejected(self):
        """非 CNY 候选币种拒绝——有效采购价口径为 CNY（03 §1.5）。"""
        _, service = _svc()
        seed_full_input(service)
        with self.assertRaises(ValueError) as ctx:
            service.add_manual_candidate(
                TASK, ASIN, 'offer-U',
                quote_source='https://x', quoted_at='2026-10-15', currency='USD')
        self.assertIn('unsupported_candidate_currency', str(ctx.exception))


class TestSourcingDependency(unittest.TestCase):
    def test_candidate_add_bumps_sourcing_version(self):
        _, service = _svc()
        seed_full_input(service)
        self.assertEqual(service.versions(TASK, ASIN)['sourcing_version'], 0)
        seed_candidate(service)
        self.assertEqual(service.versions(TASK, ASIN)['sourcing_version'], 1)

    def test_select_bumps_sourcing_version(self):
        _, service = _svc()
        seed_full_input(service)
        service.load_sample_params()
        seed_candidate(service)
        before = service.versions(TASK, ASIN)['sourcing_version']
        service.select_candidate(TASK, ASIN, 'offer-1', 'sku-1')
        self.assertEqual(service.versions(TASK, ASIN)['sourcing_version'], before + 1)

    def test_candidate_edit_stales_result(self):
        """编辑候选（MOQ/价格）→ sourcing_version+1 → 旧测算/快照过期。"""
        _, service = _svc()
        _, _, recalc, snapshot = run_demo_flow(service)
        service.edit_candidate(TASK, ASIN, 'offer-1', {'moq': 100})
        v = service.versions(TASK, ASIN)
        self.assertFalse(recalc.is_current(v['input_version'], v['params_version'],
                                           v['sourcing_version']))
        self.assertFalse(snapshot.is_current(v['input_version'], v['params_version'],
                                             v['sourcing_version']))

    def test_candidate_edit_fixes_qty_applicability(self):
        """修正候选数量适用性：MOQ 下调后 qty_check 由 violated 变 passed。"""
        _, service = _svc()
        seed_full_input(service, target_qty=500)
        sequence = service.load_sample_params()
        seed_candidate(service, ladder=False, moq=1000)
        service.calculate(TASK, ASIN)
        sel = service.select_candidate(TASK, ASIN, 'offer-1', 'sku-1')
        self.assertEqual(sel['qty_check'], 'violated')
        service.edit_candidate(TASK, ASIN, 'offer-1', {'moq': 100})
        service.recalculate(TASK, ASIN)
        sel2 = service.select_candidate(TASK, ASIN, 'offer-1', 'sku-1')
        self.assertEqual(sel2['qty_check'], 'passed')
        self.assertIsNotNone(sequence)  # 保持参数引用，避免未使用告警


class TestSnapshotImmutability(unittest.TestCase):
    def test_content_and_events_not_corruptible(self):
        """快照内容/事件对调用方只读：篡改返回值不影响快照与失效判定。"""
        _, service = _svc()
        _, _, _, snapshot = run_demo_flow(service)
        v_before = service.versions(TASK, ASIN)

        tampered = snapshot.content()
        tampered['qty_check'] = 'tampered'
        tampered['effective_purchase_price_cny'] = '0.01'
        self.assertEqual(snapshot.content()['qty_check'], 'passed')       # 未被污染
        self.assertNotEqual(snapshot.content()['effective_purchase_price_cny'], '0.01')
        self.assertTrue(snapshot.is_current(v_before['input_version'],
                                            v_before['params_version'],
                                            v_before['sourcing_version']))

    def test_event_objects_are_frozen(self):
        """事件对象为 frozen dataclass——追加后不可改写。"""
        _, service = _svc()
        _, _, _, snapshot = run_demo_flow(service)
        service.demo_confirm(snapshot.snapshot_id, actor='tester')
        event = snapshot.events[0]
        with self.assertRaises(dataclasses.FrozenInstanceError):
            event.kind = 'real_confirmed'


if __name__ == '__main__':
    unittest.main()
