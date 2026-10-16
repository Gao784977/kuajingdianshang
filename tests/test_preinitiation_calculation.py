"""测算测试：缺失不默认 0、负利润率合法、真实入口 blocked、test_only 标注
（03 §1.4/§1.5/§6/§10；AC2/AC11/AC12）。"""
import unittest
from decimal import Decimal

from src.modules.preinitiation.domain import Mode
from src.modules.preinitiation.service import SAMPLE_PARAM_VALUES, PreinitiationService
from tests._preinitiation_helpers import ASIN, TASK, make_service, run_demo_flow, seed_full_input


class TestMissingCostParams(unittest.TestCase):
    def test_missing_cost_param_not_zero_default(self):
        """关键成本参数缺失 → not_computable+缺失码，绝不默认为 0（03 §1.4）。"""
        for missing_key in ('first_leg_cny', 'design_fee_cny'):
            with self.subTest(missing_key=missing_key):
                _, service = make_service()
                seed_full_input(service)
                values = {k: v for k, v in SAMPLE_PARAM_VALUES.items() if k != missing_key}
                service.load_params(values)
                # 参数值本身保持缺失（未被 0 填充）
                self.assertIsNone(service.current_params().values.get(missing_key))
                calc = service.calculate(TASK, ASIN)
                self.assertEqual(calc.calc_status, 'not_computable')
                expected = {
                    'first_leg_cny': 'missing_first_leg',
                    'design_fee_cny': 'missing_design_fee',
                }[missing_key]
                self.assertIn(expected, calc.missing)
                self.assertIsNone(calc.company_margin)
                self.assertIsNone(calc.purchase_price_cny)

    def test_params_not_loaded_all_missing(self):
        """未载入任何参数 → 全部缺失码，不产生数值。"""
        _, service = make_service()
        seed_full_input(service)
        calc = service.calculate(TASK, ASIN)
        self.assertEqual(calc.calc_status, 'not_computable')
        self.assertIn('missing_first_leg', calc.missing)
        self.assertIn('missing_withdrawal_rate', calc.missing)
        self.assertIsNone(calc.company_margin)


class TestNegativeMargin(unittest.TestCase):
    def test_negative_margin_is_valid_result(self):
        """负公司利润率是合法结果；不因低于目标而视为不可计算（AC12）。

        注：售价与目标利润率互斥录入（03 §4.1），正算路径无目标利润率，
        target_margin_check=None（该字段独立于结果有效性，见下一测试）。
        """
        _, service = make_service(fixed_margin=Decimal('-0.05'))
        seed_full_input(service)
        service.load_sample_params()
        calc = service.calculate(TASK, ASIN)
        self.assertEqual(calc.calc_status, 'ok')
        self.assertIsNotNone(calc.company_margin)
        self.assertLess(calc.company_margin, 0)
        self.assertIsNone(calc.target_margin_check)

    def test_target_margin_check_pure_logic(self):
        """below/meets/above 为独立校验字段（03 §1.5）——纯逻辑直测。"""
        check = PreinitiationService._target_margin_check
        self.assertEqual(check(Decimal('-0.05'), Decimal('0.15')), 'below')
        self.assertEqual(check(Decimal('0.15'), Decimal('0.15')), 'meets')
        self.assertEqual(check(Decimal('0.20'), Decimal('0.15')), 'above')
        self.assertIsNone(check(None, Decimal('0.15')))   # 无结果不校验
        self.assertIsNone(check(Decimal('0.20'), None))   # 无目标不校验


class TestRealEntryBlocked(unittest.TestCase):
    def test_real_entry_blocked_no_numbers(self):
        """真实测算入口：公式未验证 → blocked+原因清单，不输出任何数值（03 §6）。"""
        _, service = make_service()
        seed_full_input(service)
        service.load_sample_params()
        calc = service.calculate(TASK, ASIN, Mode.REAL)
        self.assertEqual(calc.calc_status, 'blocked')
        self.assertIn('formula_branch_blocked:D5', calc.reasons)
        self.assertIn('reverse_formulas_not_implemented:Q3', calc.reasons)
        self.assertIn('op_params_unavailable:B1', calc.reasons)
        self.assertIsNone(calc.company_margin)
        self.assertIsNone(calc.purchase_price_cny)

    def test_demo_result_flagged_test_only(self):
        """demo 测算结果显式标注 test_only + sample_parameters（AC11）。"""
        _, service = make_service()
        first, _, recalc, _ = run_demo_flow(service)
        self.assertEqual(first.verification, 'test_only')
        self.assertTrue(first.sample_parameters)
        self.assertEqual(recalc.verification, 'test_only')
        self.assertTrue(recalc.sample_parameters)


if __name__ == '__main__':
    unittest.main()
