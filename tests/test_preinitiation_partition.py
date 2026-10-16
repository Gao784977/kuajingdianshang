"""owner 数据分区测试（命名空间键空间分区，非用户权限隔离）——S3 验收修正。

背景（验收结论）：X-Owner-Id 完全由客户端自报，不是安全身份：
- 任何客户端提交 A 的 owner 值即可冒充 A（见 TestHttpImpersonation，
  该测试**固化冒用可行这一事实**，作为已知边界而非安全能力）；
- 因此本文件测试的是**数据分区**（不同 owner 值的键空间互不串扰），
  **不是**经认证后的用户授权。

- 服务层：不同 owner 的内存仓储键空间完全分区 → 跨 owner（用各自
  owner 值）读取/修改一律 snapshot_not_found，且不污染原快照事件；
- HTTP 层（registry 模式）：他人令牌访问他人 owner → 401；
  自己令牌 + 自己 owner 头 → 只能操作自己的数据；
  非法/缺失 X-Owner-Id → 400；
- 冒用（TestHttpImpersonation）：B 提交 A 的 owner 头 → 可读取、
  可导出、可修改 A 的内容（本地演示已知边界，生产适配必须以
  现有系统验证后的用户上下文替代，见 workspace.py 生产适配契约）。

原系统双用户权限测试（tests/test_cross_user_isolation.py，经邀请码+
会话+CSRF 的认证后越权测试）与本文件**性质不同**，且因 backend.storage
缺失（B5 阻塞）当前无法运行——两者在验收报告中分别报告。
"""
import http.client
import json
import threading
import unittest

from src.modules.preinitiation.webapp import serve
from src.modules.preinitiation.workspace import WorkspaceRegistry
from tests._preinitiation_helpers import ASIN, TASK, run_demo_flow


class TestServiceLevelPartition(unittest.TestCase):
    def setUp(self):
        self.registry = WorkspaceRegistry()
        self.alice = self.registry.get('alice')
        self.bob = self.registry.get('bob')

    def test_distinct_repos_and_tokens(self):
        self.assertIsNot(self.alice.repo, self.bob.repo)
        self.assertNotEqual(self.alice.token, self.bob.token)

    def test_bob_namespace_cannot_read_or_modify_alice_snapshot(self):
        """bob 用自己的 owner 值（非冒用）：键空间分区，读/改均 not_found。"""
        run_demo_flow(self.alice.service)
        alice_snapshot = self.alice.repo.snapshots(TASK, ASIN)[0]
        sid = alice_snapshot.snapshot_id

        # 读取（导出预览单）被拒
        with self.assertRaises(ValueError) as ctx:
            self.bob.service.export_snapshot(sid)
        self.assertIn('snapshot_not_found', str(ctx.exception))
        # 修改（模拟确认 / 拒绝 / 转产品）被拒
        with self.assertRaises(ValueError):
            self.bob.service.demo_confirm(sid, actor='bob')
        with self.assertRaises(ValueError):
            self.bob.service.reject_snapshot(sid, actor='bob')
        with self.assertRaises(ValueError):
            self.bob.service.convert_to_pending_product(sid, created_by='bob')
        # alice 的快照未被污染：无事件、状态不变
        self.assertEqual(alice_snapshot.derived_status(), 'pending_confirm')
        self.assertEqual(len(alice_snapshot.events), 0)
        # bob 工作区为空
        self.assertEqual(self.bob.repo.snapshots(TASK, ASIN), [])

    def test_independent_flows_per_owner(self):
        run_demo_flow(self.alice.service)
        run_demo_flow(self.bob.service)
        a = self.alice.repo.snapshots(TASK, ASIN)
        b = self.bob.repo.snapshots(TASK, ASIN)
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)
        self.assertNotEqual(a[0].snapshot_id, b[0].snapshot_id)

    def test_invalid_owner_ids_rejected(self):
        for bad in ('', '   ', 'bad id', 'a;b', 'x' * 65, 123, None):
            with self.assertRaises(ValueError):
                self.registry.get(bad)

    def test_registry_lists_owners(self):
        self.registry.get('alice')
        self.registry.get('bob')
        self.assertEqual(self.registry.owners(), ['alice', 'bob'])


class RegistryHttpHarness:
    """registry 模式 HTTP 测试夹具：每个请求必须携带 X-Owner-Id + 该 owner 令牌。"""

    def __init__(self):
        self.registry = WorkspaceRegistry()
        self.server = serve('127.0.0.1', 0, registry=self.registry)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.05), daemon=True)
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def _conn(self):
        return http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)

    def session_token(self, owner: str):
        """向 /api/session 索取该 owner 工作区的写令牌（无需任何认证）。"""
        conn = self._conn()
        conn.request('GET', '/api/session', headers={'X-Owner-Id': owner,
                                                     'Connection': 'close'})
        resp = conn.getresponse()
        body = json.loads(resp.read().decode('utf-8'))
        conn.close()
        return resp.status, body

    def token_of(self, owner: str) -> str:
        status, body = self.session_token(owner)
        if status != 200:
            raise AssertionError(f'session for {owner!r} failed: {status} {body}')
        return body['token']

    def write_headers(self, owner: str, token: str = None):
        return {
            'Content-Type': 'application/json',
            'Connection': 'close',
            'Origin': f'http://127.0.0.1:{self.port}',
            'X-Owner-Id': owner,
            'X-Preinitiation-Token': self.token_of(owner) if token is None else token,
        }

    def get(self, path: str, owner: str = None):
        headers = {'Connection': 'close'}
        if owner is not None:
            headers['X-Owner-Id'] = owner
        conn = self._conn()
        conn.request('GET', path, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    def post(self, path: str, payload: dict, owner: str, token: str = None):
        body = json.dumps(payload).encode('utf-8')
        conn = self._conn()
        conn.request('POST', path, body=body,
                     headers=self.write_headers(owner, token))
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data


class TestHttpLevelPartition(unittest.TestCase):
    def setUp(self):
        self.h = RegistryHttpHarness()

    def tearDown(self):
        self.h.stop()

    def _alice_flow_to_snapshot(self) -> str:
        """alice 走完整流程生成快照，返回 snapshot_id。"""
        status, _ = self.h.post('/api/workspace/load-sample', {}, 'alice')
        self.assertEqual(status, 200)
        self.h.post('/api/calc/first', {}, 'alice')
        self.h.post('/api/candidates/select',
                    {'task_id': 'dev-task-1001', 'asin': 'B0TESTASIN01',
                     'offer_id': 'offer-8801', 'sku_id': 'sku-red'}, 'alice')
        self.h.post('/api/calc/recalc', {}, 'alice')
        status, data = self.h.post('/api/snapshot/create',
                                   {'task_id': 'dev-task-1001',
                                    'asin': 'B0TESTASIN01', 'created_by': 'alice'},
                                   'alice')
        self.assertEqual(status, 200, data)
        state = json.loads(data.decode('utf-8'))['state']
        return state['snapshots'][-1]['snapshot_id']

    def test_owner_scoped_flow_and_state(self):
        sid = self._alice_flow_to_snapshot()
        status, data = self.h.get('/api/state', owner='alice')
        self.assertEqual(status, 200)
        state = json.loads(data.decode('utf-8'))['state']
        self.assertEqual(len(state['snapshots']), 1)
        self.assertEqual(state['snapshots'][0]['snapshot_id'], sid)
        # alice/bob 令牌互不相同
        self.assertNotEqual(self.h.token_of('alice'), self.h.token_of('bob'))

    def test_bob_namespace_cannot_read_or_modify_alice_snapshot(self):
        """bob 用自己的 owner 值 + 自己的令牌（非冒用）：读不到 alice 的快照。"""
        sid = self._alice_flow_to_snapshot()
        # bob 用自己的 owner 头 + 自己的令牌：读不到 alice 的快照
        status, data = self.h.post('/api/export', {'snapshot_id': sid}, 'bob')
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(data.decode('utf-8'))['code'], 'snapshot_not_found')
        # 修改同样被拒
        status, data = self.h.post('/api/snapshot/demo-confirm',
                                   {'snapshot_id': sid, 'actor': 'bob'}, 'bob')
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(data.decode('utf-8'))['code'], 'snapshot_not_found')
        # bob 的状态里没有 alice 的任何数据
        status, data = self.h.get('/api/state', owner='bob')
        state = json.loads(data.decode('utf-8'))['state']
        self.assertEqual(state['snapshots'], [])
        self.assertIsNone(state['input'])

    def test_bob_token_cannot_act_as_alice(self):
        """bob 的令牌 + alice 的 owner 头 → 令牌不匹配，401（注意：这只覆盖
        「拿错令牌」的情形，不覆盖冒用——冒用见 TestHttpImpersonation）。"""
        bob_token = self.h.token_of('bob')
        status, data = self.h.post('/api/workspace/load-sample', {}, 'alice',
                                   token=bob_token)
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(data.decode('utf-8'))['code'], 'unauthorized')

    def test_missing_or_invalid_owner_header_rejected(self):
        status, data = self.h.get('/api/state')            # 缺 X-Owner-Id
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(data.decode('utf-8'))['code'], 'invalid_owner_id')
        status, data = self.h.get('/api/state', owner='bad id')   # 非法字符
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(data.decode('utf-8'))['code'], 'invalid_owner_id')
        status, data = self.h.get('/api/state', owner='a;b')
        self.assertEqual(status, 400)
        # 健康检查不需要 owner
        status, _ = self.h.get('/api/health')
        self.assertEqual(status, 200)


class TestHttpImpersonation(unittest.TestCase):
    """冒用测试（S3 验收新增）：独立客户端 B 提交 A 的 X-Owner-Id。

    结论（测试固化的事实）：B **可以**读取、修改、导出 A 的全部内容——
    X-Owner-Id 不构成安全身份。这不是待修 bug，而是本地演示的已知边界：
    生产适配必须以现有系统验证后的用户上下文替代客户端自报的 owner
    （见 workspace.py 生产适配契约）。因此 registry 模式不得称为
    「用户权限隔离」，独立本地演示定位为单用户。
    """

    def setUp(self):
        self.h = RegistryHttpHarness()

    def tearDown(self):
        self.h.stop()

    def _alice_flow_to_snapshot(self) -> str:
        status, _ = self.h.post('/api/workspace/load-sample', {}, 'alice')
        self.assertEqual(status, 200)
        self.h.post('/api/calc/first', {}, 'alice')
        self.h.post('/api/candidates/select',
                    {'task_id': 'dev-task-1001', 'asin': 'B0TESTASIN01',
                     'offer_id': 'offer-8801', 'sku_id': 'sku-red'}, 'alice')
        self.h.post('/api/calc/recalc', {}, 'alice')
        status, data = self.h.post('/api/snapshot/create',
                                   {'task_id': 'dev-task-1001',
                                    'asin': 'B0TESTASIN01', 'created_by': 'alice'},
                                   'alice')
        self.assertEqual(status, 200, data)
        state = json.loads(data.decode('utf-8'))['state']
        return state['snapshots'][-1]['snapshot_id']

    def test_bob_impersonating_alice_owner_header_gets_full_access(self):
        """B 仅凭 A 的 owner 值：读状态 → 拿令牌 → 导出 → 修改，全部成功。"""
        sid = self._alice_flow_to_snapshot()

        # 1) 仅凭 A 的 owner 头（无令牌）：读取 A 的全部状态
        status, data = self.h.get('/api/state', owner='alice')
        self.assertEqual(status, 200)
        state = json.loads(data.decode('utf-8'))['state']
        self.assertEqual(len(state['snapshots']), 1)
        self.assertEqual(state['snapshots'][0]['snapshot_id'], sid)

        # 2) B 向 /api/session 提交 A 的 owner 头：服务直接发放 A 工作区写令牌
        status, body = self.h.session_token('alice')
        self.assertEqual(status, 200)
        forged_token = body['token']
        self.assertEqual(forged_token, self.h.token_of('alice'))  # 同一令牌

        # 3) B 用 (A 的 owner 头 + 冒领令牌)：导出 A 的预览单 → 成功
        status, data = self.h.post('/api/export', {'snapshot_id': sid},
                                   'alice', token=forged_token)
        self.assertEqual(status, 200, data)
        exported = json.loads(data.decode('utf-8'))['result']
        self.assertIn('preview_notice', exported)

        # 4) B 修改 A 的快照（模拟确认）→ 成功，事件被写入 A 的快照
        status, data = self.h.post('/api/snapshot/demo-confirm',
                                   {'snapshot_id': sid, 'actor': 'bob'},
                                   'alice', token=forged_token)
        self.assertEqual(status, 200, data)
        state = json.loads(data.decode('utf-8'))['state']
        self.assertEqual(state['snapshots'][0]['status'], 'demo_confirmed')

        # 结论固化：以上全部成功 = X-Owner-Id 可被完全冒用。
        # 本断言组的存在意义是把「冒用可行」记录为受控事实，防止被误述为安全能力。


if __name__ == '__main__':
    unittest.main()
