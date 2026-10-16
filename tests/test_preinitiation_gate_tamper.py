"""演示门禁 · 客户端篡改测试（S3 验收新增，经实际 HTTP 服务）。

验证要求（验收三）：门禁必须是**服务端行为**，不只依赖 UI/水印/字段展示：
- 客户端在请求体中篡改 demo / mode / verification / approved_for_decision /
  watermark 等字段，不能把演示结果提升为真实结果；
- 实际存在的确认入口（real-confirm）不接受演示结果；
- 真实计算入口（/api/calc/real）在公式/参数/对账证据缺失时返回
  blocked + 明确原因清单，不输出任何数值；
- 导出内容（preview_notice / watermark / machine_readable.approved_for_decision）
  由服务端无条件生成，请求体无法去除或改写。

入口存在性（验收三·NOT_IMPLEMENTED 清单）：
- HTTP 层**不存在**审批入口、**不存在**转待开发产品路由（POST_ROUTES 全集
  见 webapp.py）；转产品仅存在服务层方法且要求 real_confirmed（当前必拒）。
  本文件不新增任何业务入口。
"""
from __future__ import annotations

import http.client
import json
import threading
import unittest

from src.modules.preinitiation.webapp import DemoWorkspace, serve

TASK = 'dev-task-1001'
ASIN = 'B0TESTASIN01'

# 篡改字段集合：尝试把演示结果"提升"为真实结果的各种客户端写法
_TAMPER = {
    'demo': False, 'mode': 'real', 'verification': 'verified',
    'approved_for_decision': True, 'watermark': None, 'preview_notice': '',
    'force': True, 'sample_parameters': False,
}


class GateTamperHarness:
    """单工作区 HTTP 夹具（与浏览器演示同一模式）。"""

    def __init__(self):
        self.ws = DemoWorkspace()
        self.server = serve('127.0.0.1', 0, workspace=self.ws)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.05), daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def _conn(self):
        return http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)

    def _headers(self):
        return {'Content-Type': 'application/json', 'Connection': 'close',
                'Origin': f'http://127.0.0.1:{self.port}',
                'X-Preinitiation-Token': self.ws.token}

    def post(self, path, payload):
        conn = self._conn()
        conn.request('POST', path, body=json.dumps(payload).encode('utf-8'),
                     headers=self._headers())
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data


class TestGateTamperingOverHttp(unittest.TestCase):
    def setUp(self):
        self.h = GateTamperHarness()

    def tearDown(self):
        self.h.stop()

    def _flow_to_snapshot(self) -> str:
        status, _ = self.h.post('/api/workspace/load-sample', {})
        self.assertEqual(status, 200)
        self.h.post('/api/calc/first', {})
        self.h.post('/api/candidates/select',
                    {'task_id': TASK, 'asin': ASIN,
                     'offer_id': 'offer-8801', 'sku_id': 'sku-red'})
        self.h.post('/api/calc/recalc', {})
        status, data = self.h.post('/api/snapshot/create',
                                   {'task_id': TASK, 'asin': ASIN,
                                    'created_by': 'tester'})
        self.assertEqual(status, 200, data)
        state = json.loads(data.decode('utf-8'))['state']
        return state['snapshots'][-1]['snapshot_id']

    def test_tampered_calc_payload_cannot_elevate(self):
        """计算请求体携带 mode=real/verification=verified → 结果仍 demo/test_only。"""
        self.h.post('/api/workspace/load-sample', {})
        status, data = self.h.post('/api/calc/first', dict(_TAMPER))
        self.assertEqual(status, 200)
        calc = json.loads(data.decode('utf-8'))['result']
        self.assertEqual(calc['mode'], 'demo')
        self.assertEqual(calc['verification'], 'test_only')
        self.assertTrue(calc['sample_parameters'])

    def test_tampered_snapshot_create_stays_demo(self):
        """快照创建请求体篡改等级字段 → 快照内容仍 demo/test_only。"""
        self.h.post('/api/workspace/load-sample', {})
        self.h.post('/api/calc/first', {})
        self.h.post('/api/candidates/select',
                    {'task_id': TASK, 'asin': ASIN,
                     'offer_id': 'offer-8801', 'sku_id': 'sku-red'})
        self.h.post('/api/calc/recalc', {})
        payload = {'task_id': TASK, 'asin': ASIN, 'created_by': 'tester'}
        payload.update(_TAMPER)
        status, data = self.h.post('/api/snapshot/create', payload)
        self.assertEqual(status, 200)
        snap = json.loads(data.decode('utf-8'))['result']
        content = snap['content'] if 'content' in snap else snap
        self.assertEqual(content.get('mode'), 'demo')
        self.assertEqual(content.get('verification'), 'test_only')

    def test_tampered_real_confirm_still_rejected(self):
        """real-confirm 请求体篡改（含 force/approved_for_decision）→ 仍被门禁拒绝。"""
        sid = self._flow_to_snapshot()
        payload = {'snapshot_id': sid, 'actor': 'attacker'}
        payload.update(_TAMPER)
        status, data = self.h.post('/api/snapshot/real-confirm', payload)
        self.assertEqual(status, 200)
        result = json.loads(data.decode('utf-8'))['result']
        self.assertFalse(result['ok'])
        self.assertIn('formula_not_verified:test_only', result['reasons'])
        self.assertIn('sample_parameters_not_allowed_for_real', result['reasons'])
        # 快照状态未被篡改载荷改变
        state = json.loads(data.decode('utf-8'))['state']
        self.assertEqual(state['snapshots'][0]['status'], 'pending_confirm')

    def test_tampered_export_cannot_strip_markers(self):
        """导出请求体篡改标识字段 → 服务端仍无条件写入全部非正式标识。"""
        sid = self._flow_to_snapshot()
        payload = {'snapshot_id': sid}
        payload.update(_TAMPER)
        status, data = self.h.post('/api/export', payload)
        self.assertEqual(status, 200)
        export = json.loads(data.decode('utf-8'))['result']
        self.assertEqual(export['document_kind'], 'pending_verification_preview')
        self.assertIn('非正式测算', export['preview_notice'])
        self.assertIn('禁止用于审批或采购决策', export['preview_notice'])
        self.assertIsNotNone(export['watermark'])
        self.assertEqual(export['machine_readable']['demo'], True)
        self.assertEqual(export['machine_readable']['mode'], 'demo')
        self.assertEqual(export['machine_readable']['verification'], 'test_only')
        self.assertEqual(export['machine_readable']['approved_for_decision'], False)

    def test_tampered_input_save_unknown_fields_rejected(self):
        """输入保存的 calc_fields 携带等级字段 → 服务端按未知字段拒绝。"""
        self.h.post('/api/workspace/load-sample', {})
        status, data = self.h.post('/api/input/save',
                                   {'task_id': TASK, 'asin': ASIN,
                                    'calc_fields': {'selling_price_usd': '39.99',
                                                    'mode': 'real',
                                                    'verification': 'verified'}})
        self.assertEqual(status, 400)
        body = json.loads(data.decode('utf-8'))
        self.assertIn('unknown_field:mode', body['code'])

    def test_real_calc_route_blocked_with_reasons_no_numbers(self):
        """真实计算入口：blocked + 明确原因，不输出任何数值。"""
        self.h.post('/api/workspace/load-sample', {})
        status, data = self.h.post('/api/calc/real', {})
        self.assertEqual(status, 200)
        calc = json.loads(data.decode('utf-8'))['result']
        self.assertEqual(calc['calc_status'], 'blocked')
        reasons = calc['reasons']
        self.assertIn('formula_branch_blocked:D1', reasons)
        self.assertIn('formula_branch_blocked:D2', reasons)
        self.assertIn('formula_branch_blocked:D5', reasons)
        self.assertIn('op_params_unavailable:B1', reasons)
        self.assertIsNone(calc['company_margin'])       # 无任何数值输出
        self.assertIsNone(calc['purchase_price_cny'])
        self.assertEqual(calc['verification'], 'unverified')


if __name__ == '__main__':
    unittest.main()
