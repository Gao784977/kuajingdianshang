"""输入集与版本管理测试（03 §2/§4.1/§5）。"""
import unittest

from tests._preinitiation_helpers import ASIN, TASK, make_service, run_demo_flow


class TestInputValidation(unittest.TestCase):
    def test_mutual_exclusion_rejected(self):
        """售价与目标利润率同时提供 → 互斥约束拒绝（03 §4.1）。"""
        _, service = make_service()
        with self.assertRaises(ValueError) as ctx:
            service.create_input_set(TASK, ASIN,
                                     selling_price_usd='39.99', target_margin_pct='0.15')
        self.assertIn('mutual_exclusion_violated', str(ctx.exception))

    def test_target_qty_zero_rejected(self):
        """target_qty=0 非法——不得用 0 同时表达未知和不限量（03 §2.2）。"""
        _, service = make_service()
        with self.assertRaises(ValueError) as ctx:
            service.create_input_set(TASK, ASIN, target_qty=0)
        self.assertIn('invalid_target_qty', str(ctx.exception))

    def test_input_completeness_missing_codes(self):
        """关键输入缺失 → input_incomplete + 缺失码；无任何数值输出（AC2）。"""
        _, service = make_service()
        service.create_input_set(TASK, ASIN, selling_price_usd='39.99')
        service.load_sample_params()
        calc = service.calculate(TASK, ASIN)
        self.assertEqual(calc.calc_status, 'input_incomplete')
        for code in ('missing_promotion_ratio', 'missing_fx', 'missing_purchase_price'):
            self.assertIn(code, calc.missing)
        self.assertIsNone(calc.company_margin)
        self.assertIsNone(calc.purchase_price_cny)

    def test_target_margin_only_adds_reverse_blocked_hint(self):
        """仅填目标利润率：正算缺售价；反推 blocked（D5）作为原因提示。"""
        _, service = make_service()
        service.create_input_set(TASK, ASIN, target_margin_pct='0.15',
                                 promotion_fee_ratio='0.10', fx_usd_to_cny='7.10',
                                 estimated_purchase_price_cny='25.00')
        service.load_sample_params()
        calc = service.calculate(TASK, ASIN)
        self.assertEqual(calc.calc_status, 'input_incomplete')
        self.assertIn('missing_selling_price', calc.missing)
        self.assertIn('reverse_price_calc_blocked:D5', calc.missing)


class TestVersioning(unittest.TestCase):
    def test_calc_field_change_bumps_input_version_and_stales(self):
        """计算字段修改 → input_version+1，测算/快照过期（AC3）。"""
        _, service = make_service()
        _, _, recalc, snapshot = run_demo_flow(service)
        updated = service.update_input(TASK, ASIN,
                                       calc_fields={'selling_price_usd': '42.99'})
        self.assertEqual(updated.input_version, 2)
        v = service.versions(TASK, ASIN)
        self.assertFalse(recalc.is_current(updated.input_version, v['params_version'],
                                           v['sourcing_version']))
        self.assertFalse(snapshot.is_current(updated.input_version, v['params_version'],
                                             v['sourcing_version']))

    def test_meta_change_does_not_stale(self):
        """仅 meta 字段修改 → meta_version+1，不触发失效（03 §5）。"""
        _, service = make_service()
        _, _, recalc, snapshot = run_demo_flow(service)
        updated = service.update_input(TASK, ASIN, meta_fields={'note': '竞品备注'})
        self.assertEqual(updated.input_version, 1)
        self.assertEqual(updated.meta_version, 2)
        v = service.versions(TASK, ASIN)
        self.assertTrue(recalc.is_current(updated.input_version, v['params_version'],
                                          v['sourcing_version']))
        self.assertTrue(snapshot.is_current(updated.input_version, v['params_version'],
                                            v['sourcing_version']))

    def test_params_version_change_stales(self):
        """参数版本变化 → 测算/快照过期（03 §5）。"""
        _, service = make_service()
        _, _, recalc, snapshot = run_demo_flow(service)
        self.assertEqual(service.current_params().params_version, 1)
        service.load_sample_params()  # 重新载入 → params_version=2
        self.assertEqual(service.current_params().params_version, 2)
        v = service.versions(TASK, ASIN)
        self.assertFalse(recalc.is_current(1, 2, v['sourcing_version']))
        self.assertFalse(snapshot.is_current(1, 2, v['sourcing_version']))


if __name__ == '__main__':
    unittest.main()
