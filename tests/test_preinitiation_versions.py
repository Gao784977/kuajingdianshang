"""本轮新增行为测试：最小版本体系、失效规则、快照幂等、待核验预览单导出。

对照 2026-10-15 轮次验收要求（第五/六部分）：
- 至少区分输入版本 / 计算结果版本 / 候选选择版本 / 快照版本（命名对齐实现：
  input_version / calc_version / sourcing_version / snapshot_seq，另有
  meta_version / params_version，各自独立、不混用单一 status 字段）；
- 售价、汇率、采购数量、候选 SKU、有效采购价变更后，相关计算与采购约束过期；
- 旧快照保持不变仍可追溯；新结果必须关联新的输入版本；
- 导出时明确显示快照版本和当前是否过期；
- 重复保存同一请求不得重复创建快照。
"""
import unittest

from src.modules.preinitiation.service import PREVIEW_NOTICE
from tests._preinitiation_helpers import (
    ASIN, TASK, make_service, run_demo_flow, seed_candidate, seed_full_input,
)


class TestDistinctVersionCounters(unittest.TestCase):
    def test_versions_exposes_six_distinct_counters(self):
        """六类版本字段同时存在且语义独立（不是单一 status）。"""
        _, service = make_service()
        v = service.versions(TASK, ASIN)
        self.assertEqual(sorted(v), sorted([
            'input_version', 'meta_version', 'params_version',
            'sourcing_version', 'calc_version', 'snapshot_seq']))

    def test_calc_version_increments_per_calculation_snapshot_seq_per_snapshot(self):
        """每次计算 calc_version+1；快照不创建则 snapshot_seq 不变。"""
        _, service = make_service()
        seed_full_input(service)
        service.load_sample_params()
        self.assertIsNone(service.versions(TASK, ASIN)['calc_version'])
        service.calculate(TASK, ASIN)      # calc_version=1
        service.calculate(TASK, ASIN)      # calc_version=2
        v = service.versions(TASK, ASIN)
        self.assertEqual(v['calc_version'], 2)
        self.assertIsNone(v['snapshot_seq'])   # 尚无快照
        seed_candidate(service)
        service.select_candidate(TASK, ASIN, 'offer-1', 'sku-1')
        recalc = service.recalculate(TASK, ASIN)   # calc_version=3
        self.assertEqual(recalc.calc_version, 3)
        snapshot = service.create_snapshot(TASK, ASIN, created_by='tester')
        self.assertEqual(snapshot.content()['calc_version_ref'], 3)
        self.assertEqual(service.versions(TASK, ASIN)['snapshot_seq'], 1)

    def test_meta_change_bumps_only_meta_version(self):
        """仅 meta 修改：input/calc/snapshot 版本不受影响（互不混用）。"""
        _, service = make_service()
        run_demo_flow(service)
        before = service.versions(TASK, ASIN)
        updated = service.update_input(TASK, ASIN, meta_fields={'note': '备注'})
        after = service.versions(TASK, ASIN)
        self.assertEqual(updated.meta_version, 2)
        self.assertEqual(after['input_version'], before['input_version'])
        self.assertEqual(after['calc_version'], before['calc_version'])
        self.assertEqual(after['snapshot_seq'], before['snapshot_seq'])


class TestSnapshotIdempotency(unittest.TestCase):
    def test_duplicate_snapshot_request_returns_existing(self):
        """重复保存同一请求不重复创建快照（同一 calc 幂等返回）。"""
        repo, service = make_service()
        _, _, _, snapshot = run_demo_flow(service)
        again = service.create_snapshot(TASK, ASIN, created_by='tester-again')
        self.assertEqual(again.snapshot_id, snapshot.snapshot_id)
        self.assertEqual(len(repo.snapshots(TASK, ASIN)), 1)
        self.assertEqual(service.versions(TASK, ASIN)['snapshot_seq'], 1)

    def test_duplicate_request_with_different_created_by_keeps_original(self):
        """S3 验收：幂等键语义与"首写胜出"。

        当前幂等键 = 服务端派生的 calc_id（无客户端幂等键），快照内容由
        服务端状态唯一决定，不存在"同键不同内容"的静默混写：重复请求携带
        不同 created_by 时，返回**原快照**（创建人不被改写、不产生第二个快照）。
        注意：这是"按 calc 幂等"，不是完整请求幂等——若未来引入客户端
        幂等键，同键不同内容必须显式冲突（03 §4.6 契约）。
        """
        repo, service = make_service()
        _, _, _, snapshot = run_demo_flow(service)
        original_content = snapshot.content()
        again = service.create_snapshot(TASK, ASIN, created_by='someone-else')
        self.assertEqual(again.snapshot_id, snapshot.snapshot_id)
        self.assertEqual(again.content(), original_content)   # 内容未被改写
        self.assertEqual(len(repo.snapshots(TASK, ASIN)), 1)

    def test_new_snapshot_after_new_calc_gets_next_seq(self):
        """输入修改→重算→新快照：snapshot_seq 递增，旧快照保留可追溯。"""
        repo, service = make_service()
        _, _, _, v1 = run_demo_flow(service)
        service.update_input(TASK, ASIN, calc_fields={'selling_price_usd': '42.99'})
        recalc = service.recalculate(TASK, ASIN)
        v2 = service.create_snapshot(TASK, ASIN, created_by='tester')
        self.assertEqual(recalc.input_version_ref, 2)          # 新结果关联新输入版本
        self.assertEqual(v2.content()['snapshot_seq'], 2)
        self.assertEqual(v1.content()['snapshot_seq'], 1)
        self.assertEqual(len(repo.snapshots(TASK, ASIN)), 2)
        self.assertNotEqual(v1.snapshot_id, v2.snapshot_id)


class TestStalenessMatrix(unittest.TestCase):
    """售价 / 汇率 / 采购数量 / 候选 SKU / 有效采购价变更 → 相关结果过期。"""

    def _flow(self):
        repo, service = make_service()
        _, _, recalc, snapshot = run_demo_flow(service)
        return repo, service, recalc, snapshot

    def _assert_stale(self, service, recalc, snapshot):
        v = service.versions(TASK, ASIN)
        self.assertFalse(recalc.is_current(v['input_version'], v['params_version'],
                                           v['sourcing_version']))
        self.assertFalse(snapshot.is_current(v['input_version'], v['params_version'],
                                             v['sourcing_version']))

    def test_selling_price_change_stales(self):
        _, service, recalc, snapshot = self._flow()
        service.update_input(TASK, ASIN, calc_fields={'selling_price_usd': '42.99'})
        self._assert_stale(service, recalc, snapshot)

    def test_fx_change_stales(self):
        _, service, recalc, snapshot = self._flow()
        service.update_input(TASK, ASIN, calc_fields={'fx_usd_to_cny': '7.30'})
        self._assert_stale(service, recalc, snapshot)

    def test_target_qty_change_stales(self):
        _, service, recalc, snapshot = self._flow()
        service.update_input(TASK, ASIN, calc_fields={'target_qty': 600})
        self._assert_stale(service, recalc, snapshot)

    def test_candidate_price_edit_stales(self):
        """有效采购价（阶梯价）变更 → sourcing_version+1 → 旧结果过期。"""
        _, service, recalc, snapshot = self._flow()
        service.edit_candidate(TASK, ASIN, 'offer-1',
                               {'skus': [{'sku_id': 'sku-1', 'sku_price_cny': '25.50',
                                          'ladder_prices': [
                                              {'qty_from': 100, 'qty_to': 499, 'price_cny': '26.00'},
                                              {'qty_from': 500, 'qty_to': None, 'price_cny': '25.00'}]}]})
        self._assert_stale(service, recalc, snapshot)

    def test_switching_candidate_sku_stales(self):
        """切换候选 SKU → sourcing_version+1 → 旧结果过期。"""
        _, service, recalc, snapshot = self._flow()
        seed_candidate(service, offer_id='offer-2')
        service.select_candidate(TASK, ASIN, 'offer-2', 'sku-1')
        self._assert_stale(service, recalc, snapshot)

    def test_purchase_constraint_violated_after_qty_change(self):
        """采购数量落到阶梯范围外 → 复算不可计算（采购约束失效，不默认 0）。"""
        _, service, _, _ = self._flow()
        service.update_input(TASK, ASIN, calc_fields={'target_qty': 50})
        calc = service.recalculate(TASK, ASIN)
        self.assertEqual(calc.calc_status, 'not_computable')
        self.assertIn('qty_out_of_ladder_range', calc.missing)
        self.assertIsNone(calc.purchase_price_cny)

    def test_stale_snapshot_rejected_for_new_confirmation(self):
        _, service, _, snapshot = self._flow()
        service.update_input(TASK, ASIN, calc_fields={'selling_price_usd': '42.99'})
        result = service.demo_confirm(snapshot.snapshot_id, actor='tester')
        self.assertFalse(result['ok'])
        self.assertEqual(result['reasons'], ['result_stale'])


class TestConcurrentSnapshotCreation(unittest.TestCase):
    """S3 验收：并发保存同一请求不生成重复快照。

    保证范围如实声明：仓储层自身不保证并发安全（repository.GUARANTEE）；
    HTTP 服务层通过 DemoWorkspace.lock 将同一工作区的请求串行化。
    本测试经**实际 HTTP 服务**并发发起 N 个相同快照请求，验证最终仅
    产生 1 个快照（服务层加锁下的实际行为，非仓储层承诺）。
    """

    def test_concurrent_http_snapshot_creates_produce_single_snapshot(self):
        import http.client
        import json
        import threading

        from src.modules.preinitiation.webapp import DemoWorkspace, serve

        # webapp 默认任务/ASIN（load-sample 只为默认任务创建输入集）
        task_id, asin = 'dev-task-1001', 'B0TESTASIN01'
        ws = DemoWorkspace()
        server = serve('127.0.0.1', 0, workspace=ws)
        port = server.server_address[1]
        t = threading.Thread(
            target=lambda: server.serve_forever(poll_interval=0.05), daemon=True)
        t.start()
        try:
            headers = {'Content-Type': 'application/json', 'Connection': 'close',
                       'Origin': f'http://127.0.0.1:{port}',
                       'X-Preinitiation-Token': ws.token}

            def post(path, payload):
                conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
                conn.request('POST', path, body=json.dumps(payload).encode('utf-8'),
                             headers=dict(headers))
                resp = conn.getresponse()
                data = resp.read()
                conn.close()
                return resp.status, data

            # 走到"已有有效复算"状态
            self.assertEqual(post('/api/workspace/load-sample', {})[0], 200)
            post('/api/calc/first', {})
            post('/api/candidates/select',
                 {'task_id': task_id, 'asin': asin,
                  'offer_id': 'offer-8801', 'sku_id': 'sku-red'})
            post('/api/calc/recalc', {})

            results = []
            barrier = threading.Barrier(8)

            def worker(i):
                barrier.wait()
                status, data = post('/api/snapshot/create',
                                    {'task_id': task_id, 'asin': asin,
                                     'created_by': f'worker-{i}'})
                results.append((status, json.loads(data.decode('utf-8'))))

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
            for th in threads:
                th.start()
            for th in threads:
                th.join()

            self.assertEqual(len(results), 8)
            self.assertTrue(all(s == 200 for s, _ in results),
                            [r for s, r in results if s != 200])
            snap_ids = {r['result']['snapshot_id'] for _, r in results}
            self.assertEqual(len(snap_ids), 1)               # 同一快照
            state = results[0][1]['state']
            self.assertEqual(len(state['snapshots']), 1)      # 仅 1 条记录
        finally:
            server.shutdown()
            server.server_close()


class TestPreviewExportEnhancements(unittest.TestCase):
    def test_preview_notice_constant(self):
        """预览单强制文案：非正式测算、禁止用于审批或采购决策。"""
        self.assertIn('非正式测算', PREVIEW_NOTICE)
        self.assertIn('禁止用于审批或采购决策', PREVIEW_NOTICE)

    def test_export_shows_snapshot_versions_and_expiry(self):
        """导出明确显示快照版本与当前是否过期；过期不改动快照内容。"""
        _, service = make_service()
        _, _, _, snapshot = run_demo_flow(service)
        before = service.export_snapshot(snapshot.snapshot_id)
        self.assertFalse(before['expired'])
        self.assertEqual(before['expired_reasons'], [])
        self.assertEqual(before['snapshot_versions'], {
            'snapshot_seq': 1, 'calc_version_ref': 2,
            'input_version_ref': 1, 'params_version_ref': 1, 'sourcing_version_ref': 2})
        service.update_input(TASK, ASIN, calc_fields={'fx_usd_to_cny': '7.30'})
        after = service.export_snapshot(snapshot.snapshot_id)
        self.assertTrue(after['expired'])
        self.assertTrue(after['expired_reasons'])
        # 快照内容与版本引用不因过期而变化（不可变、可追溯）
        self.assertEqual(after['snapshot'], before['snapshot'])
        self.assertEqual(after['snapshot_versions'], before['snapshot_versions'])
        self.assertFalse(after['machine_readable']['approved_for_decision'])

    def test_export_marks_manual_source_and_quoted_at(self):
        """手工录入来源与获取时间必须随快照导出（可追溯）。"""
        _, service = make_service()
        _, _, _, snapshot = run_demo_flow(service)
        content = snapshot.content()
        self.assertIn('quote_source', content)
        self.assertIn('quoted_at', content)
        self.assertTrue(content['quote_source'])
        self.assertTrue(content['quoted_at'])


if __name__ == '__main__':
    unittest.main()
