"""S2 本地可视化演示 —— 仅监听 127.0.0.1 的本地 HTTP 服务。

安全与技术约束（S2 任务）：
- 仅 Python 标准库 http.server + HTML/CSS/原生 JS；不新增登录/数据库/队列/第三方 CDN。
- 前端只调用本服务的接口，业务规则全部复用 preinitiation.service，不在 JS 重实现。
- 仅监听 127.0.0.1，不对局域网开放；不调用 OP/1688/公司生产接口。
- 写接口：只接受 JSON、限制请求体大小、同源校验、随机会话令牌（经请求头传递，不入 URL）。
- http.server 与内存 Repository 仅供本地演示，不可用于生产（见 repository.GUARANTEE）。

启动：python3 -m preinitiation.webapp
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .domain import Mode
from .providers import TestOnlyProvider
from .repository import GUARANTEE, InMemoryRepository
from .service import DEMO_WATERMARK, PreinitiationService

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
MAX_BODY_BYTES = 64 * 1024  # 写请求体上限（64KB）
DEFAULT_TASK_ID = 'dev-task-1001'
DEFAULT_ASIN = 'B0TESTASIN01'

STATIC_FILES = {
    '/': ('index.html', 'text/html; charset=utf-8'),
    '/index.html': ('index.html', 'text/html; charset=utf-8'),
    '/static/app.css': ('app.css', 'text/css; charset=utf-8'),
    '/static/app.js': ('app.js', 'application/javascript; charset=utf-8'),
}

# 机器原因码 → 中文说明（错误提示同时给出中文说明与原因码）
REASON_MESSAGES = {
    'mutual_exclusion_violated': '售价与目标利润率互斥：只能填写其中之一。',
    'invalid_selling_price': '售价必须大于 0。',
    'invalid_target_margin': '目标利润率取值非法（应在 -100%~100% 之间）。',
    'invalid_promotion_ratio': '活动营销费占比应在 0~1 之间。',
    'invalid_fx': '汇率必须大于 0。',
    'invalid_target_qty': '目标采购量必须为正整数；未知请留空（不得填 0）。',
    'invalid_target_price_range': '目标采购价下限不得大于上限。',
    'invalid_estimated_purchase_price': '首轮估算采购价必须大于 0。',
    'unknown_field': '存在不被支持的字段。',
    'nothing_to_update': '没有可保存的变更。',
    'input_set_not_found': '输入集不存在，请先保存输入。',
    'manual_candidate_requires_quote_source': '手工候选必须填写报价来源。',
    'manual_candidate_requires_quoted_at': '手工候选必须填写报价获取时间。',
    'unsupported_candidate_currency': '一期仅支持 CNY 报价，其他币种不自动换算。',
    'duplicate_offer_candidate': '该 offer 已存在，请改用编辑。',
    'candidate_not_found': '候选不存在。',
    'sku_not_found': '所选 SKU 不存在。',
    'duplicate_sku_id': '候选内 SKU 编号重复。',
    'invalid_sku_price': 'SKU 单价非法。',
    'invalid_ladder_qty_from': '阶梯价起始量必须 ≥ 1。',
    'invalid_ladder_range': '阶梯价区间非法（上界小于下界）。',
    'invalid_ladder_price': '阶梯价单价必须大于 0。',
    'duplicate_ladder_tier': '阶梯价档位起始量重复。',
    'overlapping_ladder_tier': '阶梯价档位区间重叠。',
    'multiple_open_ladder_tier': '存在多个无上限档位。',
    'no_calculation': '尚未测算。',
    'calc_not_ok': '当前测算状态不可用于生成快照（需先完成有效采购价复算）。',
    'effective_price_required': '快照必须基于有效采购价复算，搜索摘要价不能替代。',
    'calc_stale': '结果已过期，请重新测算后再生成快照。',
    'result_stale': '结果已过期：输入/参数/候选发生变化，请重新测算。',
    'no_selection': '尚未选择候选与 SKU。',
    'snapshot_not_found': '快照不存在。',
    'snapshot_rejected': '该快照已被拒绝（终态），不能再确认。',
    'already_real_confirmed': '该快照已完成正式确认。',
    'demo_confirmed_not_upgradeable_to_real': '模拟确认不可升级为正式确认（不同事件、不同状态）。',
    'formula_not_verified': '公式未通过 (c) 级验证，不能正式确认。',
    'formula_branch_blocked': '公式分支存在未决矛盾，真实入口 blocked。',
    'formula_branch_not_verified': '公式口径未裁决（Q1 未决），真实入口 blocked。',
    'reverse_formulas_not_implemented': '反推类公式未实现（Q3 未决）。',
    'op_params_unavailable': 'OP 费率参数表未获得（B1），真实入口 blocked。',
    'params_not_loaded': '尚未载入成本参数。',
    'params_version_stale': '成本参数版本已过期。',
    'sample_parameters_not_allowed_for_real': '样例参数不得用于正式确认。',
    'missing_effective_price': '缺少 SKU 级有效采购价（搜索摘要价不可替代）。',
    'missing_selling_price': '缺少售价（正算必需；反推售价 blocked·D5）。',
    'missing_promotion_ratio': '缺少活动营销费占比。',
    'missing_fx': '缺少汇率。',
    'missing_purchase_price': '缺少采购价（首轮估算采购价）。',
    'reverse_price_calc_blocked': '反推售价未实现（D5 未决）。',
    'missing_first_leg': '缺少参数：头程费用。',
    'missing_design_fee': '缺少参数：设计费。',
    'missing_referral_rate': '缺少参数：平台佣金率。',
    'missing_storage_rate': '缺少参数：仓储费率。',
    'missing_last_mile': '缺少参数：尾程配送费。',
    'missing_operation_fee': '缺少参数：操作费。',
    'missing_inbound_fee': '缺少参数：入库费。',
    'missing_withdrawal_rate': '缺少参数：提现费率。',
    'qty_check_not_passed': '采购量适用性校验未通过。',
    'input_set_missing': '输入集缺失。',
    'real_confirmation_required': '需先完成正式确认。',
    'no_candidate_selected': '尚未选择候选。',
    'target_qty_unknown': '目标采购量未知，数量适用性无法校验。',
    'target_qty_unknown_for_ladder': '目标采购量未知，无法定位阶梯档位。',
    'no_sku_selected': '尚未选择 SKU。',
    'no_moq_or_ladder': '该 SKU 无 MOQ 也无阶梯价，数量适用性不适用。',
    'below_moq': '目标采购量低于 MOQ。',
    'qty_out_of_ladder_range': '目标采购量不在任何阶梯档位区间内。',
    'ok': '通过。',
    'invalid_json': '请求体不是合法 JSON。',
    'unauthorized': '会话令牌缺失或错误。',
    'invalid_owner_id': 'X-Owner-Id 缺失或非法（仅允许字母数字与 -_. ，长度 1~64）。',
    'too_many_owners': '工作区数量超出本地演示上限。',
    'cross_origin': '请求来源校验失败（仅允许本地同源）。',
    'unsupported_media_type': '写请求必须使用 application/json。',
    'body_too_large': '请求体过大。',
    'length_required': '缺少 Content-Length。',
    'invalid_request': '请求格式非法。',
    'not_found': '接口或资源不存在。',
}


def message_for(code: str) -> str:
    if code in REASON_MESSAGES:
        return REASON_MESSAGES[code]
    base = code.split(':', 1)[0]
    if base in REASON_MESSAGES:
        return f"{REASON_MESSAGES[base]}（原因码：{code}）"
    return f"操作被拒绝（原因码：{code}）"


def _s(value) -> str | None:
    """Decimal/数值 → 字符串（保精度）；None 原样返回。"""
    return None if value is None else str(value)


class DemoWorkspace:
    """本地演示工作区：单个内存 Repository + Service，进程内单锁（并发说明见 GUARANTEE）。

    保证范围与 repository 一致：无持久化、无跨进程唯一性、无生产保障。
    服务重启即丢失全部数据。
    """

    def __init__(self, task_id: str = DEFAULT_TASK_ID, asin: str = DEFAULT_ASIN):
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.task_id = task_id
        self.asin = asin
        self.repo = InMemoryRepository()
        self.service = PreinitiationService(self.repo, demo_provider=TestOnlyProvider())
        self._reset_state()

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def _reset_state(self) -> None:
        self.repo = InMemoryRepository()
        self.service = PreinitiationService(self.repo, demo_provider=TestOnlyProvider())

    def reset(self) -> dict:
        """清空演示数据（内存数据全部丢失，服务重启同样丢失）。"""
        with self.lock:
            self._reset_state()
            return {'cleared': True}

    def load_sample(self) -> dict:
        """加载样例：重置工作区后写入固定演示数据（覆盖前由前端确认）。"""
        with self.lock:
            self._reset_state()
            self.service.create_input_set(
                self.task_id, self.asin,
                selling_price_usd='39.99',
                promotion_fee_ratio='0.10',
                fx_usd_to_cny='7.10',
                fx_fetched_at='2026-10-15T09:00:00+08:00',
                target_qty=500,
                estimated_purchase_price_cny='25.00',
                note='本地演示样例数据（流程验证用，非完整 OP 输入集）',
            )
            self.service.load_sample_params()
            self.service.add_manual_candidate(
                self.task_id, self.asin, 'offer-8801',
                quote_source='https://detail.1688.com/offer/8801.html（页面截图存档）',
                quoted_at='2026-10-15T10:30:00+08:00',
                offer_price_cny='24.80',
                tax_inclusive=None,          # 含税口径未知——不臆断
                moq=1000,                     # 高于目标采购量 → 演示"修正数量适用性"
                skus=[
                    {'sku_id': 'sku-red', 'spec': '红色', 'sku_price_cny': '25.50',
                     'ladder_prices': [
                         {'qty_from': 100, 'qty_to': 499, 'price_cny': '25.50'},
                         {'qty_from': 500, 'qty_to': None, 'price_cny': '24.20'},
                     ]},
                    {'sku_id': 'sku-blue', 'spec': '蓝色', 'sku_price_cny': None},
                ],
            )
            return {'loaded': True}

    # ------------------------------------------------------------------
    # 写操作（全部经 service，前端不重复实现业务规则）
    # ------------------------------------------------------------------

    def save_input(self, task_id: str, asin: str, calc_fields: dict, meta_fields: dict) -> dict:
        with self.lock:
            self.task_id, self.asin = task_id, asin
            existing = self.service.versions(task_id, asin)['input_version']
            if existing is None:
                merged = dict(calc_fields or {})
                merged.update(meta_fields or {})
                input_set = self.service.create_input_set(task_id, asin, **merged)
            else:
                input_set = self.service.update_input(task_id, asin,
                                                      calc_fields=calc_fields or {},
                                                      meta_fields=meta_fields or {})
            return self._input_view(input_set)

    def add_candidate(self, payload: dict) -> dict:
        with self.lock:
            self.service.add_manual_candidate(
                payload['task_id'], payload['asin'], payload['offer_id'],
                quote_source=payload.get('quote_source', ''),
                quoted_at=payload.get('quoted_at', ''),
                offer_price_cny=payload.get('offer_price_cny'),
                tax_inclusive=payload.get('tax_inclusive'),
                moq=payload.get('moq'),
                currency=payload.get('currency', 'CNY'),
                skus=payload.get('skus') or [],
            )
            return {'added': payload['offer_id']}

    def edit_candidate(self, payload: dict) -> dict:
        with self.lock:
            changes = payload.get('changes') or {}
            self.service.edit_candidate(payload['task_id'], payload['asin'],
                                        payload['offer_id'], changes)
            return {'edited': payload['offer_id']}

    def select_candidate(self, payload: dict) -> dict:
        with self.lock:
            return self.service.select_candidate(
                payload['task_id'], payload['asin'], payload['offer_id'], payload['sku_id'])

    def load_sample_params(self) -> dict:
        with self.lock:
            params = self.service.load_sample_params()
            return {'params_version': params.params_version,
                    'sample_parameters': params.sample_parameters}

    def calc(self, kind: str, task_id: str, asin: str) -> dict:
        with self.lock:
            if kind == 'first':
                calc = self.service.calculate(task_id, asin, Mode.DEMO)
            elif kind == 'real':
                calc = self.service.calculate(task_id, asin, Mode.REAL)
            else:
                calc = self.service.recalculate(task_id, asin, Mode.DEMO)
            return self._calc_view(calc)

    def create_snapshot(self, payload: dict) -> dict:
        with self.lock:
            snapshot = self.service.create_snapshot(
                payload['task_id'], payload['asin'], created_by=payload.get('created_by', 'demo-user'))
            return self._snapshot_view(snapshot)

    def confirm(self, op: str, payload: dict) -> dict:
        with self.lock:
            sid = payload['snapshot_id']
            actor = payload.get('actor', 'demo-user')
            note = payload.get('note', '')
            if op == 'demo':
                result = self.service.demo_confirm(sid, actor, note)
            elif op == 'real':
                result = self.service.real_confirm(sid, actor, note)
            else:
                result = self.service.reject_snapshot(sid, actor, note)
            result = dict(result)
            if not result.get('ok'):
                result['reasons_detail'] = [
                    {'code': r, 'message': message_for(r)} for r in result.get('reasons', [])]
            return result

    def export(self, payload: dict) -> dict:
        with self.lock:
            return self.service.export_snapshot(payload['snapshot_id'])

    # ------------------------------------------------------------------
    # 状态聚合（GET）
    # ------------------------------------------------------------------

    def state(self) -> dict:
        with self.lock:
            task_id, asin = self.task_id, self.asin
            input_set = self.repo.get_input_set(task_id, asin)
            params = self.service.current_params()
            selection = self.repo.get_selection(task_id, asin)
            versions = self.service.versions(task_id, asin)
            calcs = [c for c in self.repo._calcs if c.task_id == task_id and c.asin == asin]
            latest = calcs[-1] if calcs else None
            candidate_views = [self._candidate_view(c, input_set, selection)
                               for c in self.repo.list_candidates(task_id, asin)]
            snapshot_views = [self._snapshot_view(s)
                              for s in self.repo.snapshots(task_id, asin)]
            return {
                'workspace': {
                    'task_id': task_id, 'asin': asin,
                    'demo': True, 'connected_to_production': False,
                },
                'guarantee': GUARANTEE,
                'demo_notice': '所有测算数值为固定测试结果，不可用于真实立项',
                'versions': versions,
                'input': self._input_view(input_set) if input_set else None,
                'params': (None if params is None else {
                    'params_version': params.params_version,
                    'sample_parameters': params.sample_parameters,
                    'source': params.source,
                    'missing': params.missing_codes(),
                }),
                'candidates': candidate_views,
                'selection': (None if selection is None else {
                    'offer_id': selection[0], 'sku_id': selection[1]}),
                'latest_calc': self._calc_view(latest) if latest else None,
                'calc_history': [self._calc_view(c) for c in calcs],
                'snapshots': snapshot_views,
                'real_entry': self._real_entry_view(),
                'zero_margin_price': {'enabled': False,
                                      'note': '0% 毛利推算采购价未启用（Q3 + D5 未决）'},
                'watermark': DEMO_WATERMARK,
            }

    def _real_entry_view(self) -> dict:
        view = self.service.real_entry_status()
        view['reasons_detail'] = [{'code': r, 'message': message_for(r)}
                                  for r in view['reasons']]
        return view

    # ------------------------------------------------------------------
    # 视图构造
    # ------------------------------------------------------------------

    @staticmethod
    def _input_view(input_set) -> dict:
        return {
            'task_id': input_set.task_id, 'asin': input_set.asin,
            'market': input_set.market, 'platform': input_set.platform,
            'selling_price_usd': _s(input_set.selling_price_usd),
            'target_margin_pct': _s(input_set.target_margin_pct),
            'promotion_fee_ratio': _s(input_set.promotion_fee_ratio),
            'fx_usd_to_cny': _s(input_set.fx_usd_to_cny),
            'fx_fetched_at': input_set.fx_fetched_at,
            'target_purchase_price_min_cny': _s(input_set.target_purchase_price_min_cny),
            'target_purchase_price_max_cny': _s(input_set.target_purchase_price_max_cny),
            'target_qty': input_set.target_qty,
            'estimated_purchase_price_cny': _s(input_set.estimated_purchase_price_cny),
            'note': input_set.note,
            'input_version': input_set.input_version,
            'meta_version': input_set.meta_version,
            'updated_at': input_set.updated_at,
            'updated_by': input_set.updated_by,
        }

    @staticmethod
    def _candidate_view(candidate, input_set, selection) -> dict:
        target_qty = input_set.target_qty if input_set else None
        selected_sku = selection[1] if (selection and selection[0] == candidate.offer_id) else None
        skus = []
        for sku in candidate.skus:
            price, reason = candidate.effective_price(target_qty, sku)
            qty, qty_reason = candidate.qty_check_detail(target_qty, sku)
            skus.append({
                'sku_id': sku.sku_id, 'spec': sku.spec,
                'sku_price_cny': _s(sku.sku_price_cny),
                'ladder_prices': [
                    {'qty_from': t.qty_from, 'qty_to': t.qty_to, 'price_cny': _s(t.price_cny)}
                    for t in sku.ladder_prices],
                'effective_purchase_price_cny': _s(price),
                'effective_price_reason': reason,
                'effective_price_reason_message': message_for(reason) if reason else None,
                'qty_check': qty.value,
                'qty_check_reason': qty_reason,
                'qty_check_reason_message': message_for(qty_reason),
                'selected': sku.sku_id == selected_sku,
            })
        return {
            'candidate_id': candidate.candidate_id,
            'offer_id': candidate.offer_id,
            'source_type': candidate.source_type,
            'offer_price_cny': _s(candidate.offer_price_cny),
            'quote_source': candidate.quote_source,
            'quoted_at': candidate.quoted_at,
            'currency': candidate.currency,
            'tax_inclusive': candidate.tax_inclusive,
            'moq': candidate.moq,
            'admission_status': candidate.admission_status,
            'candidate_status': candidate.candidate_status,
            'skus': skus,
        }

    def _calc_view(self, calc) -> dict:
        versions = self.service.versions(calc.task_id, calc.asin)
        return {
            'calc_id': calc.calc_id,
            'calc_status': calc.calc_status,
            'reasons': list(calc.reasons),
            'reasons_detail': [{'code': r, 'message': message_for(r)} for r in calc.reasons],
            'missing': list(calc.missing),
            'missing_detail': [{'code': m, 'message': message_for(m)} for m in calc.missing],
            'company_margin': _s(calc.company_margin),
            'target_margin_check': calc.target_margin_check,
            'purchase_price_cny': _s(calc.purchase_price_cny),
            'purchase_price_kind': calc.purchase_price_kind,
            'verification': calc.verification,
            'mode': calc.mode,
            'sample_parameters': calc.sample_parameters,
            'formula_version': calc.formula_version,
            'branch': calc.branch,
            'input_version_ref': calc.input_version_ref,
            'params_version_ref': calc.params_version_ref,
            'sourcing_version_ref': calc.sourcing_version_ref,
            'is_current': calc.is_current(versions['input_version'],
                                          versions['params_version'],
                                          versions['sourcing_version']),
            'calculated_at': calc.calculated_at,
        }

    def _snapshot_view(self, snapshot) -> dict:
        content = snapshot.content()
        versions = self.service.versions(content['task_id'], content['asin'])
        status = snapshot.derived_status()
        display = {'demo_confirmed': '模拟确认', 'real_confirmed': '正式确认',
                   'rejected': '已拒绝'}.get(status, '待确认')
        is_current = snapshot.is_current(versions['input_version'],
                                         versions['params_version'],
                                         versions['sourcing_version'])
        return {
            'snapshot_id': snapshot.snapshot_id,
            'content': content,
            'events': [{'event_id': e.event_id, 'kind': e.kind, 'actor': e.actor,
                        'at': e.at, 'note': e.note} for e in snapshot.events],
            'status': status,
            'confirm_display': display,
            'is_current': is_current,
            'demo': content.get('mode') == 'demo' or content.get('verification') != 'verified',
        }


# ---------------------------------------------------------------------------
# HTTP 处理器
# ---------------------------------------------------------------------------

class _Handler(BaseHTTPRequestHandler):
    server_version = 'PreinitiationDemo/0.1'
    protocol_version = 'HTTP/1.1'

    # —— 静态与读取 ——
    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path == '/api/health':
            return self._json(200, {'ok': True, 'demo': True})
        if path in ('/api/session', '/api/state'):
            try:
                workspace = self._workspace_for()
            except _RequestError as exc:
                return self._json(exc.status, {'ok': False, 'code': exc.code,
                                               'message': message_for(exc.code)})
            if path == '/api/session':
                # 本地演示契约：向任何提交该 owner 头的调用方发放该工作区
                # 的写令牌——因此 X-Owner-Id 不构成安全身份（可被任意冒用，
                # 见 workspace.py 模块注释与 TestHttpImpersonation）。
                return self._json(200, {'token': workspace.token, 'demo': True})
            return self._json(200, {'ok': True, 'state': workspace.state()})
        if path == '/favicon.ico':
            return self._send(204, b'', 'text/plain')
        if path in STATIC_FILES:
            filename, content_type = STATIC_FILES[path]
            return self._serve_static(filename, content_type)
        return self._json(404, {'ok': False, 'code': 'not_found',
                                'message': REASON_MESSAGES['not_found']})

    # —— 写操作 ——
    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        handler = POST_ROUTES.get(path)
        if handler is None:
            return self._json(404, {'ok': False, 'code': 'not_found',
                                    'message': REASON_MESSAGES['not_found']})
        try:
            workspace = self._workspace_for()
        except _RequestError as exc:
            return self._json(exc.status, {'ok': False, 'code': exc.code,
                                           'message': message_for(exc.code)})
        guard = self._guard_write(workspace)
        if guard is not None:
            return guard
        try:
            payload = self._read_json()
        except _RequestError as exc:
            return self._json(exc.status, {'ok': False, 'code': exc.code,
                                           'message': message_for(exc.code)})
        try:
            result = handler(workspace, payload)
        except ValueError as exc:
            code = str(exc)
            return self._json(400, {'ok': False, 'code': code, 'message': message_for(code)})
        except KeyError as exc:
            code = f"missing_field:{exc.args[0]}"
            return self._json(400, {'ok': False, 'code': code,
                                    'message': f"缺少必填字段：{exc.args[0]}"})
        except Exception as exc:  # 兜底：不泄露堆栈，返回统一原因码
            sys.stderr.write(f'[preinitiation-demo] internal error: {exc!r}\n')
            return self._json(500, {'ok': False, 'code': 'internal_error',
                                    'message': '服务内部错误（本地演示环境）。'})
        return self._json(200, {'ok': True, 'result': result,
                                'state': workspace.state()})

    # —— 校验 ——
    @property
    def workspace(self) -> DemoWorkspace:
        """单工作区模式（serve 未传 registry 时）直接返回服务级工作区。"""
        return self.server.workspace

    def _workspace_for(self) -> DemoWorkspace:
        """解析本次请求的工作区。

        - 单工作区模式：返回服务级 DemoWorkspace（行为与旧版一致）；
        - registry 模式：按 X-Owner-Id 解析该 owner 的独立工作区
          （owner 数据分区见 workspace.WorkspaceRegistry——**不是安全隔离**，
          X-Owner-Id 由客户端自报、可被任意冒用；非法/缺失 → 400）。
        """
        registry = getattr(self.server, 'registry', None)
        if registry is None:
            return self.server.workspace
        owner_id = self.headers.get('X-Owner-Id', '')
        if not owner_id:
            raise _RequestError(400, 'invalid_owner_id')
        try:
            return registry.get(owner_id)
        except ValueError as exc:
            raise _RequestError(400, str(exc))

    def _guard_write(self, workspace: DemoWorkspace):
        port = self.server.server_address[1]
        host = self.headers.get('Host', '')
        allowed_hosts = (f'127.0.0.1:{port}', f'localhost:{port}')
        origin = self.headers.get('Origin')
        allowed_origins = (f'http://127.0.0.1:{port}', f'http://localhost:{port}')
        # Host 必须为本机地址；Origin 若存在则必须同源（同源 POST 部分浏览器不带 Origin，
        # 此时仍受 Host 校验 + 会话令牌 + application/json 三重约束）。
        if host not in allowed_hosts:
            return self._json(403, {'ok': False, 'code': 'cross_origin',
                                    'message': REASON_MESSAGES['cross_origin']})
        if origin is not None and origin not in allowed_origins:
            return self._json(403, {'ok': False, 'code': 'cross_origin',
                                    'message': REASON_MESSAGES['cross_origin']})
        content_type = self.headers.get('Content-Type', '')
        if not content_type.lower().startswith('application/json'):
            return self._json(415, {'ok': False, 'code': 'unsupported_media_type',
                                    'message': REASON_MESSAGES['unsupported_media_type']})
        token = self.headers.get('X-Preinitiation-Token')
        if not token or not secrets.compare_digest(token, workspace.token):
            return self._json(401, {'ok': False, 'code': 'unauthorized',
                                    'message': REASON_MESSAGES['unauthorized']})
        return None

    def _read_json(self):
        raw_length = self.headers.get('Content-Length')
        if raw_length is None:
            raise _RequestError(411, 'length_required')
        try:
            length = int(raw_length)
        except ValueError:
            raise _RequestError(400, 'invalid_request')
        if length < 0:
            raise _RequestError(400, 'invalid_request')
        if length > MAX_BODY_BYTES:
            raise _RequestError(413, 'body_too_large')
        body = self.rfile.read(length)
        if len(body) != length:
            raise _RequestError(400, 'invalid_request')
        try:
            return json.loads(body.decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise _RequestError(400, 'invalid_json')

    # —— 响应 ——
    def _serve_static(self, filename, content_type):
        full = os.path.join(WEB_DIR, filename)
        if not os.path.isfile(full) or os.path.commonpath([WEB_DIR, full]) != WEB_DIR:
            return self._json(404, {'ok': False, 'code': 'not_found',
                                    'message': REASON_MESSAGES['not_found']})
        with open(full, 'rb') as fh:
            return self._send(200, fh.read(), content_type)

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        return self._send(status, body, 'application/json; charset=utf-8')

    def _send(self, status, body: bytes, content_type: str):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.end_headers()
        if body:
            self.wfile.write(body)
        return None

    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write('[preinitiation-demo] %s - %s\n' %
                         (self.address_string(), fmt % args))


class _RequestError(Exception):
    def __init__(self, status: int, code: str):
        super().__init__(code)
        self.status = status
        self.code = code


def _payload_task(payload: dict) -> tuple:
    return payload.get('task_id', DEFAULT_TASK_ID), payload.get('asin', DEFAULT_ASIN)


POST_ROUTES = {
    '/api/input/save': lambda ws, p: ws.save_input(
        p.get('task_id', ws.task_id), p.get('asin', ws.asin),
        p.get('calc_fields') or {}, p.get('meta_fields') or {}),
    '/api/params/sample': lambda ws, p: ws.load_sample_params(),
    '/api/candidates/add': lambda ws, p: ws.add_candidate(p),
    '/api/candidates/edit': lambda ws, p: ws.edit_candidate(p),
    '/api/candidates/select': lambda ws, p: ws.select_candidate(p),
    '/api/calc/first': lambda ws, p: ws.calc('first', p.get('task_id', ws.task_id), p.get('asin', ws.asin)),
    '/api/calc/real': lambda ws, p: ws.calc('real', p.get('task_id', ws.task_id), p.get('asin', ws.asin)),
    '/api/calc/recalc': lambda ws, p: ws.calc('recalc', p.get('task_id', ws.task_id), p.get('asin', ws.asin)),
    '/api/snapshot/create': lambda ws, p: ws.create_snapshot(p),
    '/api/snapshot/demo-confirm': lambda ws, p: ws.confirm('demo', p),
    '/api/snapshot/real-confirm': lambda ws, p: ws.confirm('real', p),
    '/api/snapshot/reject': lambda ws, p: ws.confirm('reject', p),
    '/api/export': lambda ws, p: ws.export(p),
    '/api/workspace/load-sample': lambda ws, p: ws.load_sample(),
    '/api/workspace/reset': lambda ws, p: ws.reset(),
}


class DemoServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, workspace: DemoWorkspace | None, registry=None):
        super().__init__(address, _Handler)
        self.workspace = workspace
        # registry 模式：每个 X-Owner-Id 解析到独立工作区（owner 数据分区，
        # **不是安全隔离**——X-Owner-Id 客户端自报可冒用，见 workspace.py）。
        # None = 单工作区模式（本地演示默认，浏览器端即此模式）。
        self.registry = registry

    def handle_error(self, request, client_address):
        """客户端提前断开（本地演示/被拒的超大请求）不打印堆栈。"""
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def serve(host: str = '127.0.0.1', port: int = 0,
          workspace: DemoWorkspace | None = None,
          registry=None) -> DemoServer:
    """启动本地演示服务；返回 server 对象（调用方负责 shutdown）。

    - workspace：单工作区模式（默认自动创建一个 DemoWorkspace）；
    - registry：传入 WorkspaceRegistry 时启用 owner 数据分区模式
      （每个请求按 X-Owner-Id 解析独立工作区；仅演示键空间分区语义，
      **不是安全隔离**——X-Owner-Id 客户端自报，可被任意冒用）。
    """
    if registry is None and workspace is None:
        workspace = DemoWorkspace()
    return DemoServer((host, port), workspace, registry=registry)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description='预立项工作台 · 本地演示（仅监听本机）')
    parser.add_argument('--host', default='127.0.0.1', help='监听地址（默认 127.0.0.1，勿改为对外地址）')
    parser.add_argument('--port', type=int, default=0, help='监听端口（默认 0=自动分配空闲端口）')
    args = parser.parse_args()
    if args.host != '127.0.0.1':
        print('警告：本演示仅应监听 127.0.0.1，不对局域网开放。')

    server = serve(args.host, args.port)
    host, port = server.server_address[0], server.server_address[1]
    base = f'http://127.0.0.1:{port}'
    print('=' * 64)
    print('预立项工作台 · 本地演示（S2）')
    print('=' * 64)
    print(f'访问地址：{base}')
    print('仅监听 127.0.0.1，未对局域网开放。')
    print('本地演示 / 未连接生产系统：所有测算为固定测试结果，不可用于真实立项。')
    print('数据保存在进程内存中，服务重启即全部丢失。')
    print('停止：Ctrl+C（或关闭本终端）。')
    print('=' * 64, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\n已停止本地演示服务。')
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
