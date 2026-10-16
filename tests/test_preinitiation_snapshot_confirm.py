"""快照/确认/导出/转产品测试（03 §4.6/§4.7/§6；AC1-D/AC3/AC7/AC10/AC11）。"""
import unittest

from tests._preinitiation_helpers import TASK, ASIN, make_service, run_demo_flow


class TestDemoConfirm(unittest.TestCase):
    def test_demo_confirm_idempotent(self):
        """重复模拟确认不重复产生事件；展示「模拟确认」（AC7）。"""
        _, service = make_service()
        _, _, _, snapshot = run_demo_flow(service)
        r1 = service.demo_confirm(snapshot.snapshot_id, actor='tester')
        r2 = service.demo_confirm(snapshot.snapshot_id, actor='tester')
        self.assertTrue(r1['ok'])
        self.assertEqual(r1['status'], 'demo_confirmed')
        self.assertEqual(r1['display'], '模拟确认')
        self.assertTrue(r2['ok'])
        self.assertTrue(r2.get('already'))
        self.assertEqual(len(snapshot.events), 1)
        self.assertEqual(snapshot.events[0].kind, 'demo_confirmed')
        self.assertEqual(snapshot.derived_status(), 'demo_confirmed')

    def test_demo_confirmed_not_upgradeable_to_real(self):
        """模拟确认永不升级为正式确认（03 §4.6）。"""
        _, service = make_service()
        _, _, _, snapshot = run_demo_flow(service)
        service.demo_confirm(snapshot.snapshot_id, actor='tester')
        result = service.real_confirm(snapshot.snapshot_id, actor='tester')
        self.assertFalse(result['ok'])
        self.assertIn('demo_confirmed_not_upgradeable_to_real', result['reasons'])
        self.assertEqual(snapshot.derived_status(), 'demo_confirmed')


class TestRealConfirmGates(unittest.TestCase):
    def test_gate_reasons_formula_and_sample_params(self):
        """未确认公式/样例参数阻止正式确认，返回原因清单（AC11）。"""
        _, service = make_service()
        # target_qty=500 命中阶梯 → qty_check=passed，隔离出公式/参数门禁
        _, _, _, snapshot = run_demo_flow(service)
        result = service.real_confirm(snapshot.snapshot_id, actor='tester')
        self.assertFalse(result['ok'])
        self.assertIn('formula_not_verified:test_only', result['reasons'])
        self.assertIn('sample_parameters_not_allowed_for_real', result['reasons'])

    def test_stale_snapshot_blocks_real_confirm(self):
        """陈旧快照不能被新的正式确认操作使用（AC3）。"""
        _, service = make_service()
        _, _, _, snapshot = run_demo_flow(service)
        service.update_input(TASK, ASIN, calc_fields={'selling_price_usd': '42.99'})
        result = service.real_confirm(snapshot.snapshot_id, actor='tester')
        self.assertFalse(result['ok'])
        self.assertIn('result_stale', result['reasons'])

    def test_rejected_snapshot_is_terminal(self):
        """拒绝为终态：拒绝后模拟/正式确认均被阻止。"""
        _, service = make_service()
        _, _, _, snapshot = run_demo_flow(service)
        result = service.reject_snapshot(snapshot.snapshot_id, actor='reviewer',
                                         note='竞品价格下行')
        self.assertTrue(result['ok'])
        self.assertEqual(snapshot.derived_status(), 'rejected')
        demo = service.demo_confirm(snapshot.snapshot_id, actor='tester')
        self.assertFalse(demo['ok'])
        real = service.real_confirm(snapshot.snapshot_id, actor='tester')
        self.assertFalse(real['ok'])
        self.assertEqual(real['reasons'], ['snapshot_rejected'])


class TestSnapshotImmutability(unittest.TestCase):
    def test_history_snapshot_immutable_after_input_change(self):
        """历史快照内容不因后续输入修改而变化；is_current 仅派生标志（AC10）。"""
        _, service = make_service()
        _, _, _, v1 = run_demo_flow(service)
        service.demo_confirm(v1.snapshot_id, actor='tester')
        before = v1.content()
        events_before = list(v1.events)

        service.update_input(TASK, ASIN, calc_fields={'selling_price_usd': '42.99'})
        service.recalculate(TASK, ASIN)
        v2 = service.create_snapshot(TASK, ASIN, created_by='tester')

        self.assertEqual(v1.content(), before)              # 内容不可变
        self.assertEqual(list(v1.events), events_before)    # 事件历史保留
        self.assertEqual(len(v1.events), 1)
        v = service.versions(TASK, ASIN)
        self.assertFalse(v1.is_current(2, v['params_version'], v['sourcing_version']))
        self.assertTrue(v2.is_current(2, v['params_version'], v['sourcing_version']))
        self.assertEqual(v2.content()['input_version_ref'], 2)
        self.assertEqual(v2.content()['snapshot_id'] != v1.content()['snapshot_id'], True)


class TestExportAndConvert(unittest.TestCase):
    def test_demo_export_watermark_and_machine_readable(self):
        """演示导出带显著水印 + 机器可读 demo 字段（03 §6）。

        本轮扩展：machine_readable 增加 approved_for_decision=False
        （待核验预览单恒不可用于正式决策）；并强制携带 preview_notice
        与快照版本、过期状态（断言随之加强，未放宽）。
        """
        _, service = make_service()
        _, _, _, snapshot = run_demo_flow(service)
        service.demo_confirm(snapshot.snapshot_id, actor='tester')
        export = service.export_snapshot(snapshot.snapshot_id)
        self.assertEqual(export['watermark'], '演示数据——不可用于真实立项')
        self.assertEqual(export['machine_readable'],
                         {'demo': True, 'mode': 'demo', 'verification': 'test_only',
                          'approved_for_decision': False})
        self.assertEqual(export['confirm_display'], '模拟确认')
        # 待核验预览单强制标识（本轮新增契约）
        self.assertEqual(export['document_kind'], 'pending_verification_preview')
        self.assertIn('非正式测算', export['preview_notice'])
        self.assertIn('禁止用于审批或采购决策', export['preview_notice'])
        self.assertFalse(export['expired'])
        self.assertEqual(export['snapshot_versions']['snapshot_seq'], 1)

    def test_convert_blocked_without_real_confirm(self):
        """转待开发产品要求 real 确认——当前必 blocked，无真实产品生成。"""
        repo, service = make_service()
        _, _, _, snapshot = run_demo_flow(service)
        service.demo_confirm(snapshot.snapshot_id, actor='tester')
        result = service.convert_to_pending_product(snapshot.snapshot_id,
                                                    created_by='tester')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reasons'], ['real_confirmation_required'])
        self.assertEqual(result['current_status'], 'demo_confirmed')
        self.assertEqual(len(repo.pending_products()), 0)


if __name__ == '__main__':
    unittest.main()
