"""手工候选与有效采购价测试（03 §2.2/§3/§4.5；AC6/AC13）。"""
import unittest

from tests._preinitiation_helpers import ASIN, TASK, make_service, seed_candidate, seed_full_input


class TestManualCandidate(unittest.TestCase):
    def test_requires_quote_source_and_quoted_at(self):
        """手工候选报价溯源字段必填（03 §4.5）。"""
        _, service = make_service()
        seed_full_input(service)
        with self.assertRaises(ValueError) as ctx:
            service.add_manual_candidate(TASK, ASIN, 'offer-x',
                                         quote_source='', quoted_at='2026-10-15')
        self.assertIn('quote_source', str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            service.add_manual_candidate(TASK, ASIN, 'offer-x',
                                         quote_source='https://x', quoted_at='')
        self.assertIn('quoted_at', str(ctx.exception))

    def test_manual_admission_unknown_and_tax_unknown(self):
        """manual 来源准入=unknown；含税口径未知保持 None（03 §4.5）。"""
        _, service = make_service()
        seed_full_input(service)
        candidate = seed_candidate(service)
        self.assertEqual(candidate.admission_status, 'unknown')
        self.assertIsNone(candidate.tax_inclusive)


class TestOfferPriceNotEffective(unittest.TestCase):
    def test_offer_price_never_becomes_effective(self):
        """搜索报价仅展示：SKU 无级价格 → 有效采购价缺失，不可复算/快照（AC6）。"""
        _, service = make_service()
        seed_full_input(service)
        service.load_sample_params()
        seed_candidate(service, with_sku_price=False)
        service.calculate(TASK, ASIN)
        selection = service.select_candidate(TASK, ASIN, 'offer-1', 'sku-1')
        self.assertIsNotNone(selection['offer_price_cny_display'])  # 摘要价可展示
        self.assertIsNone(selection['effective_purchase_price_cny'])
        self.assertEqual(selection['effective_price_reason'], 'missing_effective_price')
        recalc = service.recalculate(TASK, ASIN)
        self.assertEqual(recalc.calc_status, 'not_computable')
        self.assertIn('missing_effective_price', recalc.missing)
        with self.assertRaises(ValueError) as ctx:
            service.create_snapshot(TASK, ASIN, created_by='tester')
        self.assertIn('calc_not_ok', str(ctx.exception))


class TestQtyCheck(unittest.TestCase):
    def _prepare(self, service, **input_overrides):
        seed_full_input(service, **input_overrides)
        service.load_sample_params()

    def test_unknown_qty_never_passed_blocks_real_confirm(self):
        """target_qty 未维护 → qty_check=unknown 永不 passed；real 确认被 qty 门禁阻止（AC13）。"""
        _, service = make_service()
        self._prepare(service, target_qty=None)
        # 无阶梯（仅 SKU 单价）时有效采购价可用，但 MOQ 校验仍为 unknown
        seed_candidate(service, ladder=False, moq=100)
        service.calculate(TASK, ASIN)
        selection = service.select_candidate(TASK, ASIN, 'offer-1', 'sku-1')
        self.assertEqual(selection['qty_check'], 'unknown')
        self.assertIsNotNone(selection['effective_purchase_price_cny'])
        service.recalculate(TASK, ASIN)
        snapshot = service.create_snapshot(TASK, ASIN, created_by='tester')
        result = service.real_confirm(snapshot.snapshot_id, actor='tester')
        self.assertFalse(result['ok'])
        self.assertTrue(any(r.startswith('qty_check_not_passed:')
                            for r in result['reasons']),
                        msg=f"reasons={result['reasons']}")

    def test_unknown_qty_with_ladder_blocks_effective_price(self):
        """有阶梯但采购量未知 → 无法定位档位，有效采购价缺失。"""
        _, service = make_service()
        self._prepare(service, target_qty=None)
        seed_candidate(service, ladder=True)
        service.calculate(TASK, ASIN)
        selection = service.select_candidate(TASK, ASIN, 'offer-1', 'sku-1')
        self.assertEqual(selection['qty_check'], 'unknown')
        self.assertEqual(selection['effective_price_reason'],
                         'target_qty_unknown_for_ladder')

    def test_ladder_tier_effective_price(self):
        """采购量命中阶梯档位 → 档位价为有效采购价；qty_check=passed。"""
        _, service = make_service()
        self._prepare(service, target_qty=500)
        seed_candidate(service, ladder=True, moq=100)
        service.calculate(TASK, ASIN)
        selection = service.select_candidate(TASK, ASIN, 'offer-1', 'sku-1')
        self.assertEqual(selection['effective_purchase_price_cny'], '24.20')
        self.assertEqual(selection['qty_check'], 'passed')

    def test_qty_below_moq_violated(self):
        """目标采购量低于 MOQ → violated。"""
        _, service = make_service()
        self._prepare(service, target_qty=500)
        seed_candidate(service, ladder=False, moq=1000)
        service.calculate(TASK, ASIN)
        selection = service.select_candidate(TASK, ASIN, 'offer-1', 'sku-1')
        self.assertEqual(selection['qty_check'], 'violated')

    def test_qty_out_of_ladder_range(self):
        """采购量超出阶梯覆盖范围 → violated + 有效采购价缺失。"""
        _, service = make_service()
        self._prepare(service, target_qty=50)
        seed_candidate(service, ladder=True, moq=None)
        service.calculate(TASK, ASIN)
        selection = service.select_candidate(TASK, ASIN, 'offer-1', 'sku-1')
        self.assertEqual(selection['qty_check'], 'violated')
        self.assertEqual(selection['effective_price_reason'],
                         'qty_out_of_ladder_range')


if __name__ == '__main__':
    unittest.main()
