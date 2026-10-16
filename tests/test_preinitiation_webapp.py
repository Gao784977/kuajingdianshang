"""S2 本地 HTTP 接口测试（webapp.py）。

覆盖：静态资源可访问、非法/超大/缺令牌请求被拒、同源校验、
演示测算/快照/模拟确认/导出正常、修改输入后结果过期、
test_only 无法正式确认、页面数据与领域服务状态一致。

约束同 webapp：仅监听 127.0.0.1，内存数据。
"""
from __future__ import annotations

import http.client
import json
import threading
import unittest

from src.modules.preinitiation.webapp import MAX_BODY_BYTES, DemoWorkspace, serve

TASK = 'dev-task-1001'
ASIN = 'B0TESTASIN01'


class Harness:
    def __init__(self):
        self.ws = DemoWorkspace()
        self.server = serve('127.0.0.1', 0, workspace=self.ws)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.05),
                                       daemon=True)
        self.thread.start()

    @property
    def token(self) -> str:
        return self.ws.token

    def origin(self) -> str:
        return f'http://127.0.0.1:{self.port}'

    def _conn(self):
        return http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)

    def get(self, path):
        conn = self._conn()
        conn.request('GET', path)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body, resp.getheader('Content-Type')

    def write_headers(self, token=None, origin=None, content_type='application/json'):
        headers = {'Content-Type': content_type, 'Connection': 'close'}
        headers['X-Preinitiation-Token'] = self.token if token is None else token
        origin = self.origin() if origin is None else origin
        if origin is not False:
            headers['Origin'] = origin
        return headers

    def post(self, path, payload=None, headers=None):
        body = payload if isinstance(payload, (bytes, bytearray)) else json.dumps(
            payload if payload is not None else {}).encode('utf-8')
        conn = self._conn()
        conn.request('POST', path, body=body, headers=headers or self.write_headers())
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    def post_manual(self, path, headers, content_length=None, body=b''):
        """手工构造请求：可省略/伪造 Content-Length，或伪造 Host。"""
        conn = self._conn()
        skip_host = headers.pop('_skip_host', False)
        conn.putrequest('POST', path, skip_host=skip_host)
        for key, value in headers.items():
            conn.putheader(key, value)
        if content_length is not None:
            conn.putheader('Content-Length', content_length)
        conn.endheaders(body)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


def json_body(data):
    return json.loads(data.decode('utf-8'))


class WebHarnessTestCase(unittest.TestCase):
    def setUp(self):
        self.h = Harness()

    def tearDown(self):
        self.h.stop()

    # 便捷操作（全部走真实 HTTP 接口）
    def load_sample(self):
        status, data = self.h.post('/api/workspace/load-sample',
                                   headers=self.h.write_headers())
        self.assertEqual(status, 200)
        return json_body(data)['state']

    def api_state(self):
        status, data, _ = self.h.get('/api/state')
        self.assertEqual(status, 200)
        return json_body(data)['state']

    def flow_to_snapshot(self, sku_id='sku-red'):
        """加载样例 → 首轮测算 → 选 SKU → 复算 → 生成快照。返回 (state, snapshot_id)。"""
        self.load_sample()
        self.h.post('/api/calc/first', headers=self.h.write_headers())
        self.h.post('/api/candidates/select',
                    {'task_id': TASK, 'asin': ASIN, 'offer_id': 'offer-8801', 'sku_id': sku_id},
                    headers=self.h.write_headers())
        self.h.post('/api/calc/recalc', headers=self.h.write_headers())
        status, data = self.h.post('/api/snapshot/create',
                                   {'task_id': TASK, 'asin': ASIN, 'created_by': 'tester'},
                                   headers=self.h.write_headers())
        self.assertEqual(status, 200, data)
        state = json_body(data)['state']
        return state, state['snapshots'][-1]['snapshot_id']


class TestStaticAndReads(WebHarnessTestCase):
    def test_page_and_assets_available(self):
        status, body, ctype = self.h.get('/')
        self.assertEqual(status, 200)
        self.assertIn('text/html', ctype)
        text = body.decode('utf-8')
        self.assertIn('预立项工作台', text)
        self.assertIn('不可用于真实立项', text)
        self.assertIn('未连接生产系统', text)

        self.assertEqual(self.h.get('/index.html')[0], 200)
        status, _, ctype = self.h.get('/static/app.css')
        self.assertEqual(status, 200)
        self.assertIn('text/css', ctype)
        status, _, ctype = self.h.get('/static/app.js')
        self.assertEqual(status, 200)
        self.assertIn('javascript', ctype)
        self.assertEqual(self.h.get('/favicon.ico')[0], 204)

    def test_health_and_session(self):
        status, body, _ = self.h.get('/api/health')
        self.assertEqual(status, 200)
        self.assertTrue(json_body(body)['ok'])
        status, body, _ = self.h.get('/api/session')
        self.assertEqual(status, 200)
        self.assertTrue(json_body(body)['token'])

    def test_state_shape_and_demo_flags(self):
        state = self.api_state()
        self.assertTrue(state['workspace']['demo'])
        self.assertFalse(state['workspace']['connected_to_production'])
        self.assertIn('不可用于真实立项', state['demo_notice'])
        self.assertIn('不得用于生产', state['guarantee'])
        self.assertFalse(state['real_entry']['enabled'])
        self.assertFalse(state['zero_margin_price']['enabled'])
        for key in ('input_version', 'meta_version', 'params_version', 'sourcing_version',
                    'calc_version', 'snapshot_seq'):
            self.assertIn(key, state['versions'])

    def test_unknown_route_404(self):
        self.assertEqual(self.h.get('/api/nope')[0], 404)
        status, data = self.h.post('/api/nope', headers=self.h.write_headers())
        self.assertEqual(status, 404)
        self.assertEqual(json_body(data)['code'], 'not_found')


class TestWriteSecurity(WebHarnessTestCase):
    def test_missing_token_rejected(self):
        status, data = self.h.post('/api/workspace/load-sample',
                                   headers=self.h.write_headers(token=''))
        self.assertEqual(status, 401)
        self.assertEqual(json_body(data)['code'], 'unauthorized')

    def test_wrong_token_rejected(self):
        status, data = self.h.post('/api/workspace/load-sample',
                                   headers=self.h.write_headers(token='wrong-token'))
        self.assertEqual(status, 401)
        self.assertEqual(json_body(data)['code'], 'unauthorized')

    def test_cross_origin_rejected(self):
        status, data = self.h.post('/api/workspace/reset',
                                   headers=self.h.write_headers(origin='http://evil.example'))
        self.assertEqual(status, 403)
        self.assertEqual(json_body(data)['code'], 'cross_origin')

    def test_bad_host_rejected(self):
        headers = self.h.write_headers()
        headers['_skip_host'] = True
        headers['Host'] = 'evil.example'
        status, data = self.h.post_manual('/api/workspace/reset', headers)
        self.assertEqual(status, 403)
        self.assertEqual(json_body(data)['code'], 'cross_origin')

    def test_non_json_content_type_rejected(self):
        status, data = self.h.post('/api/workspace/reset',
                                   headers=self.h.write_headers(content_type='text/plain'))
        self.assertEqual(status, 415)
        self.assertEqual(json_body(data)['code'], 'unsupported_media_type')

    def test_invalid_json_rejected(self):
        status, data = self.h.post('/api/workspace/reset', b'{not json',
                                   headers=self.h.write_headers())
        self.assertEqual(status, 400)
        self.assertEqual(json_body(data)['code'], 'invalid_json')

    def test_missing_content_length_rejected(self):
        headers = self.h.write_headers()
        status, data = self.h.post_manual('/api/workspace/reset', headers)
        self.assertEqual(status, 411)
        self.assertEqual(json_body(data)['code'], 'length_required')

    def test_bad_content_length_rejected(self):
        headers = self.h.write_headers()
        status, data = self.h.post_manual('/api/workspace/reset', headers, content_length='abc')
        self.assertEqual(status, 400)
        self.assertEqual(json_body(data)['code'], 'invalid_request')

    def test_body_too_large_rejected(self):
        big = b'{"x":"' + b'a' * (MAX_BODY_BYTES + 1024) + b'"}'
        self.assertGreater(len(big), MAX_BODY_BYTES)
        status, data = self.h.post('/api/workspace/reset', big,
                                   headers=self.h.write_headers())
        self.assertEqual(status, 413)
        self.assertEqual(json_body(data)['code'], 'body_too_large')


class TestDemoFlow(WebHarnessTestCase):
    def test_full_demo_flow(self):
        state = self.load_sample()
        self.assertEqual(state['versions']['input_version'], 1)
        self.assertEqual(len(state['candidates']), 1)
        cand = state['candidates'][0]
        self.assertEqual(cand['source_type'], 'manual')
        self.assertEqual(cand['admission_status'], 'unknown')
        self.assertEqual(cand['currency'], 'CNY')

        # 首轮测算：固定 test_only 结果，采用估算采购价
        status, data = self.h.post('/api/calc/first', headers=self.h.write_headers())
        calc = json_body(data)['state']['latest_calc']
        self.assertEqual(calc['calc_status'], 'ok')
        self.assertEqual(calc['verification'], 'test_only')
        self.assertEqual(calc['purchase_price_kind'], 'estimated')
        self.assertTrue(calc['is_current'])

        # 选择 SKU：有效采购价取 SKU 级阶梯价；MOQ=1000 > 目标量500 → 数量不满足
        status, data = self.h.post('/api/candidates/select',
                                   {'task_id': TASK, 'asin': ASIN,
                                    'offer_id': 'offer-8801', 'sku_id': 'sku-red'},
                                   headers=self.h.write_headers())
        result = json_body(data)['result']
        self.assertEqual(result['effective_purchase_price_cny'], '24.20')
        self.assertEqual(result['qty_check'], 'violated')
        self.assertEqual(result['qty_check_reason'], 'below_moq')

        # 复算：采用有效采购价
        status, data = self.h.post('/api/calc/recalc', headers=self.h.write_headers())
        calc = json_body(data)['state']['latest_calc']
        self.assertEqual(calc['calc_status'], 'ok')
        self.assertEqual(calc['purchase_price_kind'], 'effective')
        self.assertTrue(calc['is_current'])

        # 生成快照
        status, data = self.h.post('/api/snapshot/create',
                                   {'task_id': TASK, 'asin': ASIN, 'created_by': 'tester'},
                                   headers=self.h.write_headers())
        self.assertEqual(status, 200)
        snap = json_body(data)['state']['snapshots'][-1]
        self.assertEqual(snap['status'], 'pending_confirm')
        self.assertTrue(snap['is_current'])
        sid = snap['snapshot_id']
        self.assertEqual(snap['content']['price_basis'], 'sku_level')

        # 模拟确认成功
        status, data = self.h.post('/api/snapshot/demo-confirm', {'snapshot_id': sid},
                                   headers=self.h.write_headers())
        self.assertTrue(json_body(data)['result']['ok'])
        snap = json_body(data)['state']['snapshots'][-1]
        self.assertEqual(snap['status'], 'demo_confirmed')

        # 正式确认：test_only 无法正式确认
        status, data = self.h.post('/api/snapshot/real-confirm', {'snapshot_id': sid},
                                   headers=self.h.write_headers())
        result = json_body(data)['result']
        self.assertFalse(result['ok'])
        self.assertIn('demo_confirmed_not_upgradeable_to_real', result['reasons'])
        self.assertIn('formula_not_verified:test_only', result['reasons'])
        self.assertTrue(all('message' in d for d in result['reasons_detail']))
        # 状态未升级
        snap = json_body(data)['state']['snapshots'][-1]
        self.assertEqual(snap['status'], 'demo_confirmed')
        self.assertNotIn('real_confirmed', [e['kind'] for e in snap['events']])

        # 导出：machine_readable 明确 demo；待核验预览单强制标识（本轮新增契约）
        status, data = self.h.post('/api/export', {'snapshot_id': sid},
                                   headers=self.h.write_headers())
        export = json_body(data)['result']
        self.assertEqual(export['watermark'], '演示数据——不可用于真实立项')
        self.assertEqual(export['machine_readable'],
                         {'demo': True, 'mode': 'demo', 'verification': 'test_only',
                          'approved_for_decision': False})
        self.assertEqual(export['confirm_display'], '模拟确认')
        self.assertEqual(export['document_kind'], 'pending_verification_preview')
        self.assertIn('禁止用于审批或采购决策', export['preview_notice'])
        self.assertFalse(export['expired'])

    def test_input_change_stales_calc_and_snapshot(self):
        state, sid = self.flow_to_snapshot()
        self.assertTrue(state['snapshots'][-1]['is_current'])

        status, data = self.h.post('/api/input/save',
                                   {'calc_fields': {'target_qty': 300}},
                                   headers=self.h.write_headers())
        self.assertEqual(status, 200)
        new_state = json_body(data)['state']
        self.assertEqual(new_state['versions']['input_version'], 2)
        self.assertFalse(new_state['latest_calc']['is_current'])
        self.assertFalse(new_state['snapshots'][-1]['is_current'])

        # 过期快照禁止新的确认
        status, data = self.h.post('/api/snapshot/demo-confirm', {'snapshot_id': sid},
                                   headers=self.h.write_headers())
        result = json_body(data)['result']
        self.assertFalse(result['ok'])
        self.assertEqual(result['reasons'], ['result_stale'])

        # 过期结果不能生成快照
        status, data = self.h.post('/api/snapshot/create',
                                   {'task_id': TASK, 'asin': ASIN, 'created_by': 'tester'},
                                   headers=self.h.write_headers())
        self.assertEqual(status, 400)
        self.assertTrue(json_body(data)['code'].startswith('calc_stale'))

    def test_edit_candidate_repairs_qty_applicability(self):
        _, _ = self.flow_to_snapshot()  # 目标量 500，MOQ 1000 → 不满足
        before = self.api_state()
        self.assertEqual(before['candidates'][0]['skus'][0]['qty_check'], 'violated')

        status, data = self.h.post(
            '/api/candidates/edit',
            {'task_id': TASK, 'asin': ASIN, 'offer_id': 'offer-8801',
             'changes': {'moq': 100}},
            headers=self.h.write_headers())
        self.assertEqual(status, 200, data)
        state = json_body(data)['state']
        # 候选变化 → sourcing_version 递增，旧快照过期
        self.assertGreater(state['versions']['sourcing_version'], before['versions']['sourcing_version'])
        self.assertFalse(state['latest_calc']['is_current'])

        # 重新测算 + 生成新快照 → 数量适用性通过
        self.h.post('/api/calc/recalc', headers=self.h.write_headers())
        status, data = self.h.post('/api/snapshot/create',
                                   {'task_id': TASK, 'asin': ASIN, 'created_by': 'tester'},
                                   headers=self.h.write_headers())
        self.assertEqual(status, 200, data)
        state = json_body(data)['state']
        self.assertEqual(len(state['snapshots']), 2)
        self.assertEqual(state['snapshots'][-1]['content']['qty_check'], 'passed')
        self.assertTrue(state['snapshots'][-1]['is_current'])
        self.assertFalse(state['snapshots'][0]['is_current'])

    def test_history_snapshot_content_frozen(self):
        _, sid = self.flow_to_snapshot()
        first_content = self.api_state()['snapshots'][0]['content']

        self.h.post('/api/input/save', {'calc_fields': {'selling_price_usd': '42.99'}},
                    headers=self.h.write_headers())
        after = self.api_state()['snapshots'][0]
        self.assertEqual(after['content'], first_content)  # 内容不因表单/输入变化
        self.assertFalse(after['is_current'])


class TestValidationErrors(WebHarnessTestCase):
    def test_missing_required_field_reported(self):
        status, data = self.h.post('/api/candidates/add',
                                   {'task_id': TASK, 'asin': ASIN},
                                   headers=self.h.write_headers())
        self.assertEqual(status, 400)
        self.assertTrue(json_body(data)['code'].startswith('missing_field:'))

    def test_unverified_reason_codes_in_chinese(self):
        # 手工候选缺少报价来源 → 中文说明 + 原因码
        status, data = self.h.post('/api/candidates/add',
                                   {'task_id': TASK, 'asin': ASIN, 'offer_id': 'offer-x',
                                    'quoted_at': '2026-10-15T10:00:00+08:00'},
                                   headers=self.h.write_headers())
        self.assertEqual(status, 400)
        payload = json_body(data)
        self.assertEqual(payload['code'], 'manual_candidate_requires_quote_source')
        self.assertIn('报价来源', payload['message'])

    def test_non_cny_currency_rejected(self):
        status, data = self.h.post('/api/candidates/add',
                                   {'task_id': TASK, 'asin': ASIN, 'offer_id': 'offer-usd',
                                    'quote_source': 'x', 'quoted_at': 't',
                                    'currency': 'USD'},
                                   headers=self.h.write_headers())
        self.assertEqual(status, 400)
        self.assertEqual(json_body(data)['code'], 'unsupported_candidate_currency:USD')

    def test_mutual_exclusion_input_rejected(self):
        status, data = self.h.post('/api/input/save',
                                   {'calc_fields': {'selling_price_usd': '39.99',
                                                    'target_margin_pct': '0.2'}},
                                   headers=self.h.write_headers())
        self.assertEqual(status, 400)
        self.assertTrue(json_body(data)['code'].startswith('mutual_exclusion_violated'))

    def test_invalid_ladder_rejected(self):
        status, data = self.h.post('/api/candidates/add',
                                   {'task_id': TASK, 'asin': ASIN, 'offer_id': 'offer-bad',
                                    'quote_source': 'x', 'quoted_at': 't',
                                    'skus': [{'sku_id': 's1', 'sku_price_cny': '10',
                                              'ladder_prices': [
                                                  {'qty_from': 100, 'qty_to': 100, 'price_cny': '10'},
                                                  {'qty_from': 100, 'qty_to': None, 'price_cny': '9'}]}]},
                                   headers=self.h.write_headers())
        self.assertEqual(status, 400)
        self.assertTrue(json_body(data)['code'].startswith('duplicate_ladder_tier'))


class TestPageMatchesService(WebHarnessTestCase):
    def test_api_state_consistent_with_domain_service(self):
        self.load_sample()
        state = self.api_state()
        repo = self.h.ws.repo
        service = self.h.ws.service

        self.assertEqual(state['versions'], service.versions(TASK, ASIN))
        self.assertEqual(len(state['candidates']), len(repo.list_candidates(TASK, ASIN)))
        self.assertEqual(state['candidates'][0]['offer_id'],
                         repo.list_candidates(TASK, ASIN)[0].offer_id)
        self.assertIsNone(state['selection'])
        self.assertEqual(state['input']['input_version'],
                         repo.get_input_set(TASK, ASIN).input_version)
        # 与领域服务一致：真实入口恒 blocked
        self.assertFalse(service.real_entry_status()['enabled'])


if __name__ == '__main__':
    unittest.main()
