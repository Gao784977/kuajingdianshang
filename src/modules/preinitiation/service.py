"""S1 编排服务 —— 输入/测算/候选/选择/复算/快照/确认/导出/转产品占位。

对应 docs/preinitiation/03（数据契约）、04 §4（S1 范围）。
明确不含：真实公式（真实入口 blocked）、1688 API、品牌中心对接、
审批提交、持久化/并发保障（见 repository.GUARANTEE）。
"""
from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from .domain import (
    CALC_FIELDS, META_FIELDS, REQUIRED_PARAMS,
    CalcStatus, Calculation, Candidate, CandidateStatus, CostParams,
    DecisionSnapshot, EventKind, InputSet, LadderPrice, Mode, PriceKind,
    QtyCheck, SkuQuote, Verification, dec, new_id, now_iso, validate_skus,
)
from .providers import CalcRequest, CalculationProvider, RealOpProvider, TestOnlyProvider
from .repository import DuplicatePendingProductError, InMemoryRepository

DEMO_WATERMARK = '演示数据——不可用于真实立项'
DEMO_CONFIRM_LABEL = '模拟确认'
PREVIEW_NOTICE = '待核验预览单——非正式测算，禁止用于审批或采购决策'

# 样例参数（虚构值，sample_parameters=True）——仅 demo 域可用；真实参数待 B1（03 §6/§9）
SAMPLE_PARAM_VALUES = {
    'first_leg_cny': Decimal('5.00'),
    'design_fee_cny': Decimal('2.00'),
    'referral_rate': Decimal('0.15'),
    'storage_rate': Decimal('0.03'),
    'last_mile_usd': Decimal('4.50'),
    'operation_fee_usd': Decimal('1.20'),
    'inbound_fee_usd': Decimal('0.80'),
    'withdrawal_fee_rate': Decimal('0.01'),
}

_DEC_FIELDS = {
    'selling_price_usd', 'target_margin_pct', 'promotion_fee_ratio', 'fx_usd_to_cny',
    'target_purchase_price_min_cny', 'target_purchase_price_max_cny',
    'estimated_purchase_price_cny',
}


class PreinitiationService:
    def __init__(self, repo: InMemoryRepository,
                 demo_provider: Optional[CalculationProvider] = None,
                 real_provider: Optional[CalculationProvider] = None):
        self._repo = repo
        self._demo_provider = demo_provider or TestOnlyProvider()
        self._real_provider = real_provider or RealOpProvider()

    # ------------------------------------------------------------------
    # 输入集（03 §4.1：双版本管理；互斥校验；缺失不默认 0）
    # ------------------------------------------------------------------

    def create_input_set(self, task_id: str, asin: str, **fields) -> InputSet:
        allowed = set(CALC_FIELDS) | set(META_FIELDS) | {'market', 'platform', 'updated_by'}
        input_set = InputSet(task_id=task_id, asin=asin,
                             **self._coerce(fields, allowed))
        input_set.validate()
        self._repo.save_input_set(input_set)
        return input_set

    def update_input(self, task_id: str, asin: str,
                     calc_fields: Optional[dict] = None,
                     meta_fields: Optional[dict] = None) -> InputSet:
        """calc 字段修改 → input_version+1（触发失效）；
        仅 meta 字段修改 → meta_version+1（不触发失效）（03 §5）。"""
        input_set = self._repo.get_input_set(task_id, asin)
        if input_set is None:
            raise ValueError('input_set_not_found')
        calc_fields = calc_fields or {}
        meta_fields = meta_fields or {}
        if not calc_fields and not meta_fields:
            raise ValueError('nothing_to_update')
        merged = dict(self._coerce(calc_fields, set(CALC_FIELDS)))
        merged.update(self._coerce(meta_fields, set(META_FIELDS)))
        new_set = replace(input_set, **merged)
        if calc_fields:
            new_set.input_version = input_set.input_version + 1
        if meta_fields:
            new_set.meta_version = input_set.meta_version + 1
        new_set.updated_at = now_iso()
        new_set.validate()
        self._repo.save_input_set(new_set)
        return new_set

    # ------------------------------------------------------------------
    # 成本参数（03 §1.4）
    # ------------------------------------------------------------------

    def load_sample_params(self) -> CostParams:
        """载入样例参数（虚构值）。sample_parameters=True——仅 demo 域可用，
        真实确认门禁②拒绝（03 §6）。重复载入会递增 params_version 并使旧结果过期。"""
        params = CostParams(
            params_version=self._repo.next_params_version(),
            values=dict(SAMPLE_PARAM_VALUES),
            sample_parameters=True,
            source='sample_demo',
        )
        self._repo.set_params(params)
        return params

    def load_params(self, values: dict, source: str = 'custom') -> CostParams:
        """载入自定义参数（测试/演示用，同样进入版本管理）。"""
        params = CostParams(
            params_version=self._repo.next_params_version(),
            values={k: dec(v) for k, v in values.items()},
            sample_parameters=True,
            source=source,
        )
        self._repo.set_params(params)
        return params

    def current_params(self) -> Optional[CostParams]:
        return self._repo.current_params()

    def real_entry_status(self) -> dict:
        """真实计算入口状态——当前恒 blocked：公式未通过验证，不输出任何数值（03 §6）。

        仅暴露真实提供者的状态与原因，不实现任何真实公式（D1/D2/D5/Q1/Q3/B1 未决）。
        """
        provider = self._real_provider
        result = provider.calculate(None)
        return {
            'enabled': False,
            'verification': provider.verification.value,
            'formula_version': provider.formula_version,
            'reasons': list(result.reasons),
            'note': '真实计算入口未启用：公式未通过 (c) 级验证，不输出任何数值。',
        }

    def versions(self, task_id: str, asin: str) -> dict:
        """当前版本集合（供界面展示与失效判定）。

        六类版本语义各不相同，不得合并为单一 status 字段：
        - input_version / meta_version：输入集双版本（03 §5）；
        - params_version：成本参数版本；
        - sourcing_version：候选/选择依赖版本（S2 审计修复）；
        - calc_version：计算结果版本——同一任务×ASIN 内每次计算递增（本轮新增）；
        - snapshot_seq：快照序列版本——同一任务×ASIN 内每创建一个新快照递增（本轮新增）。
        """
        input_set = self._repo.get_input_set(task_id, asin)
        params = self._repo.current_params()
        return {
            'input_version': input_set.input_version if input_set else None,
            'meta_version': input_set.meta_version if input_set else None,
            'params_version': params.params_version if params else None,
            'sourcing_version': self._repo.sourcing_version(task_id, asin),
            'calc_version': self._repo.calc_version(task_id, asin),
            'snapshot_seq': self._repo.snapshot_seq(task_id, asin),
        }

    # ------------------------------------------------------------------
    # 测算（03 §2.1/§4.2/§6）
    # ------------------------------------------------------------------

    def calculate(self, task_id: str, asin: str, mode: Mode = Mode.DEMO) -> Calculation:
        """首轮测算：使用首轮估算采购价（03 §3#4）。"""
        return self._run_calc(task_id, asin, Mode(mode), PriceKind.ESTIMATED)

    def recalculate(self, task_id: str, asin: str, mode: Mode = Mode.DEMO) -> Calculation:
        """选定 SKU 后复算：唯一采用有效采购价（03 §3#6）。

        无 SKU 级价格 → not_computable(missing_effective_price)——
        搜索报价（offer 摘要价）不得自动充当有效采购价（AC6）。
        """
        mode = Mode(mode)
        input_set = self._repo.get_input_set(task_id, asin)
        if input_set is None:
            raise ValueError('input_set_not_found')
        sel = self._repo.get_selection(task_id, asin)
        if sel is None:
            return self._run_calc(task_id, asin, mode, PriceKind.EFFECTIVE,
                                  effective_price_reason='no_candidate_selected')
        offer_id, sku_id = sel
        candidate = self._repo.get_candidate(task_id, asin, offer_id)
        sku = candidate.sku(sku_id) if candidate else None
        price, reason = candidate.effective_price(input_set.target_qty, sku) if candidate else (None, 'no_candidate_selected')
        return self._run_calc(task_id, asin, mode, PriceKind.EFFECTIVE,
                              effective_price=price, effective_price_reason=reason)

    def _run_calc(self, task_id: str, asin: str, mode: Mode, price_kind: PriceKind,
                  effective_price: Optional[Decimal] = None,
                  effective_price_reason: Optional[str] = None) -> Calculation:
        input_set = self._repo.get_input_set(task_id, asin)
        if input_set is None:
            raise ValueError('input_set_not_found')
        params = self._repo.current_params()
        params_version = params.params_version if params else None
        sourcing_version = self._repo.sourcing_version(task_id, asin)
        provider = self._real_provider if mode == Mode.REAL else self._demo_provider

        def record(status, reasons=None, missing=None, margin=None, price=None, sample=False):
            calc = Calculation(
                calc_id=new_id('calc'), task_id=task_id, asin=asin,
                calc_version=self._repo.next_calc_version(task_id, asin),
                input_version_ref=input_set.input_version,
                params_version_ref=params_version,
                sourcing_version_ref=sourcing_version,
                formula_version=provider.formula_version,
                branch=provider.branch,
                verification=provider.verification.value,
                mode=mode.value,
                calc_status=status.value,
                reasons=reasons or [],
                missing=missing or [],
                company_margin=margin,
                target_margin_check=self._target_margin_check(margin, input_set.target_margin_pct),
                purchase_price_cny=price,
                purchase_price_kind=price_kind.value if price is not None else None,
                sample_parameters=sample,
            )
            self._repo.add_calc(calc)
            return calc

        # 1) 输入完整性（03 §2.1）——互斥录入不是完整性判据；缺失不默认 0
        missing = input_set.forward_calc_missing(price_kind)
        if missing:
            return record(CalcStatus.INPUT_INCOMPLETE, missing=missing)

        # 2) 采购价解析
        if price_kind == PriceKind.ESTIMATED:
            price = input_set.estimated_purchase_price_cny
        else:
            price = effective_price
            if price is None:
                return record(CalcStatus.NOT_COMPUTABLE,
                              missing=[effective_price_reason or 'missing_effective_price'])

        # 3) 真实入口：公式未验证 → blocked，不输出任何数值（03 §6）
        if mode == Mode.REAL:
            result = provider.calculate(
                self._request(input_set, params, mode, price, price_kind))
            return record(result.calc_status, reasons=result.reasons, sample=False)

        # 4) demo：参数完整性（03 §1.4：缺→not_computable，禁止默认 0）
        if params is None:
            return record(CalcStatus.NOT_COMPUTABLE,
                          missing=sorted(REQUIRED_PARAMS.values()), sample=False)
        missing_params = params.missing_codes()
        if missing_params:
            return record(CalcStatus.NOT_COMPUTABLE, missing=missing_params,
                          sample=params.sample_parameters)

        # 5) test_only 提供者——固定结果验证编排，与 OP 口径无关（03 §10）
        result = provider.calculate(
            self._request(input_set, params, mode, price, price_kind))
        return record(result.calc_status, reasons=result.reasons,
                      margin=result.company_margin, price=price,
                      sample=params.sample_parameters)

    @staticmethod
    def _request(input_set: InputSet, params, mode, price, price_kind) -> CalcRequest:
        return CalcRequest(
            task_id=input_set.task_id, asin=input_set.asin,
            input_version=input_set.input_version,
            params_version=params.params_version if params else None,
            mode=mode,
            selling_price_usd=input_set.selling_price_usd,
            promotion_fee_ratio=input_set.promotion_fee_ratio,
            fx_usd_to_cny=input_set.fx_usd_to_cny,
            purchase_price_cny=price,
            purchase_price_kind=price_kind.value,
            params_values=dict(params.values) if params else {},
        )

    @staticmethod
    def _target_margin_check(margin: Optional[Decimal],
                             target_margin: Optional[Decimal]) -> Optional[str]:
        """目标利润率校验——与结果有效性分离（03 §1.5）。"""
        if margin is None or target_margin is None:
            return None
        quantize = lambda d: d.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
        if quantize(margin) < quantize(target_margin):
            return 'below'
        if quantize(margin) > quantize(target_margin):
            return 'above'
        return 'meets'

    # ------------------------------------------------------------------
    # 手工候选（03 §4.5 降级路径）
    # ------------------------------------------------------------------

    def add_manual_candidate(self, task_id: str, asin: str, offer_id: str, *,
                             quote_source: str, quoted_at: str,
                             offer_price_cny=None, tax_inclusive: Optional[bool] = None,
                             moq: Optional[int] = None, currency: str = 'CNY',
                             skus: Optional[list] = None) -> Candidate:
        """录入手工候选。

        - quote_source/quoted_at 必填（报价溯源，03 §4.5）；
        - admission_status 固定 unknown——manual 来源 ≠ 已满足 1688 准入；
        - offer_price_cny 仅展示，不得充当有效采购价（03 §3#5）。
        """
        if not quote_source:
            raise ValueError('manual_candidate_requires_quote_source')
        if not quoted_at:
            raise ValueError('manual_candidate_requires_quoted_at')
        if currency != 'CNY':
            # 有效采购价口径为 CNY（03 §1.5）；其他币种一期不支持，不做静默换算
            raise ValueError(f'unsupported_candidate_currency:{currency}')
        if self._repo.get_candidate(task_id, asin, offer_id) is not None:
            raise ValueError('duplicate_offer_candidate')
        sku_objects = [self._coerce_sku(s) for s in (skus or [])]
        validate_skus(sku_objects)
        candidate = Candidate(
            candidate_id=new_id('cand'), task_id=task_id, asin=asin, offer_id=offer_id,
            source_type='manual',
            offer_price_cny=dec(offer_price_cny),
            quote_source=quote_source, quoted_at=quoted_at,
            currency=currency, tax_inclusive=tax_inclusive,
            moq=int(moq) if moq is not None else None,
            skus=sku_objects,
        )
        self._repo.add_candidate(candidate)
        # 候选变化纳入结果依赖（S2 审计修复）：新增候选 → sourcing_version+1
        self._repo.bump_sourcing_version(task_id, asin)
        return candidate

    # 允许编辑的候选字段（S2 新增：支持"修正候选数量适用性"）
    CANDIDATE_EDITABLE = ('quote_source', 'quoted_at', 'offer_price_cny',
                          'tax_inclusive', 'moq', 'currency', 'skus')

    def edit_candidate(self, task_id: str, asin: str, offer_id: str,
                       changes: dict) -> Candidate:
        """编辑手工候选（MOQ/阶梯/SKU 价格/报价溯源等）。

        修改后 sourcing_version+1 → 引用旧版本的测算/快照过期（S2 审计修复）。
        非法阶梯价/币种一律拒绝并给出原因码。
        """
        candidate = self._repo.get_candidate(task_id, asin, offer_id)
        if candidate is None:
            raise ValueError('candidate_not_found')
        unknown = set(changes) - set(self.CANDIDATE_EDITABLE)
        if unknown:
            raise ValueError(f"unknown_field:{sorted(unknown)[0]}")
        if not changes:
            raise ValueError('nothing_to_update')
        if 'quote_source' in changes:
            if not changes['quote_source']:
                raise ValueError('manual_candidate_requires_quote_source')
            candidate.quote_source = changes['quote_source']
        if 'quoted_at' in changes:
            if not changes['quoted_at']:
                raise ValueError('manual_candidate_requires_quoted_at')
            candidate.quoted_at = changes['quoted_at']
        if 'offer_price_cny' in changes:
            candidate.offer_price_cny = dec(changes['offer_price_cny'])
        if 'tax_inclusive' in changes:
            value = changes['tax_inclusive']
            candidate.tax_inclusive = None if value in (None, '', 'unknown') else bool(value)
        if 'moq' in changes:
            value = changes['moq']
            candidate.moq = None if value in (None, '') else int(value)
        if 'currency' in changes:
            if changes['currency'] != 'CNY':
                raise ValueError(f"unsupported_candidate_currency:{changes['currency']}")
            candidate.currency = changes['currency']
        if 'skus' in changes:
            sku_objects = [self._coerce_sku(s) for s in changes['skus']]
            validate_skus(sku_objects)
            candidate.skus = sku_objects
        self._repo.bump_sourcing_version(task_id, asin)
        return candidate

    @staticmethod
    def _coerce_sku(sku: dict) -> SkuQuote:
        ladder = [LadderPrice(int(t['qty_from']),
                              int(t['qty_to']) if t.get('qty_to') is not None else None,
                              dec(t['price_cny']))
                  for t in sku.get('ladder_prices', [])]
        return SkuQuote(sku_id=sku['sku_id'], spec=sku.get('spec', ''),
                        sku_price_cny=dec(sku.get('sku_price_cny')),
                        ladder_prices=ladder)

    # ------------------------------------------------------------------
    # 选择（03 §3#6）
    # ------------------------------------------------------------------

    def select_candidate(self, task_id: str, asin: str, offer_id: str, sku_id: str) -> dict:
        candidate = self._repo.get_candidate(task_id, asin, offer_id)
        if candidate is None:
            raise ValueError('candidate_not_found')
        sku = candidate.sku(sku_id)
        if sku is None:
            raise ValueError('sku_not_found')
        candidate.candidate_status = CandidateStatus.SELECTED.value
        self._repo.set_selection(task_id, asin, offer_id, sku_id)
        # 选择变化纳入结果依赖（S2 审计修复）：切换候选/SKU → sourcing_version+1
        self._repo.bump_sourcing_version(task_id, asin)
        input_set = self._repo.get_input_set(task_id, asin)
        target_qty = input_set.target_qty if input_set else None
        price, reason = candidate.effective_price(target_qty, sku)
        qty, qty_reason = candidate.qty_check_detail(target_qty, sku)
        return {
            'offer_id': offer_id,
            'sku_id': sku_id,
            'offer_price_cny_display': (str(candidate.offer_price_cny)
                                        if candidate.offer_price_cny is not None
                                        else '--（仅展示，不参与计算）'),
            'effective_purchase_price_cny': str(price) if price is not None else None,
            'effective_price_reason': reason,
            'qty_check': qty.value,
            'qty_check_reason': qty_reason,
            'admission_status': candidate.admission_status,
        }

    # ------------------------------------------------------------------
    # 决策快照（03 §4.6）
    # ------------------------------------------------------------------

    def create_snapshot(self, task_id: str, asin: str, created_by: str) -> DecisionSnapshot:
        """生成决策快照。前置：最新复算 ok、基于有效采购价、未过期（AC6/AC2）。

        幂等：对同一计算结果（calc_id）重复请求返回既有快照，
        不重复创建、不重复递增 snapshot_seq。
        """
        input_set = self._repo.get_input_set(task_id, asin)
        if input_set is None:
            raise ValueError('input_set_not_found')
        latest = self._repo.latest_calc(task_id, asin)
        if latest is None:
            raise ValueError('no_calculation')
        if latest.calc_status != CalcStatus.OK.value:
            raise ValueError(
                f"calc_not_ok:{latest.calc_status}:{','.join(latest.missing + latest.reasons)}")
        if latest.purchase_price_kind != PriceKind.EFFECTIVE.value:
            raise ValueError('effective_price_required:快照必须基于有效采购价复算（AC6）')
        params = self._repo.current_params()
        params_version = params.params_version if params else None
        sourcing_version = self._repo.sourcing_version(task_id, asin)
        if not latest.is_current(input_set.input_version, params_version, sourcing_version):
            raise ValueError('calc_stale:结果已过期，须重算')
        # 幂等：同一计算结果已有快照 → 直接返回（重复保存不重复创建）
        existing = self._repo.snapshot_for_calc(latest.calc_id)
        if existing is not None:
            return existing
        sel = self._repo.get_selection(task_id, asin)
        if sel is None:
            raise ValueError('no_selection')
        offer_id, sku_id = sel
        candidate = self._repo.get_candidate(task_id, asin, offer_id)
        sku = candidate.sku(sku_id)
        qty_check, qty_reason = candidate.qty_check_detail(input_set.target_qty, sku)
        content = {
            'snapshot_id': new_id('snap'),
            'task_id': task_id, 'asin': asin,
            'snapshot_seq': self._repo.next_snapshot_seq(task_id, asin),
            'input_version_ref': latest.input_version_ref,
            'params_version_ref': latest.params_version_ref,
            'sourcing_version_ref': latest.sourcing_version_ref,
            'calc_version_ref': latest.calc_version,
            'formula_version': latest.formula_version,
            'verification': latest.verification,
            'sourcing_batch_id_ref': None,   # S1 手工候选降级路径，无溯源批次
            'offer_id': offer_id, 'sku_id': sku_id,
            'effective_purchase_price_cny': str(latest.purchase_price_cny),
            'price_basis': 'sku_level',
            'qty_check': qty_check.value,
            'qty_check_reason': qty_reason,
            # 候选溯源快照（冻结当时口径，便于历史详情展示）
            'offer_price_cny_display': (str(candidate.offer_price_cny)
                                        if candidate.offer_price_cny is not None else None),
            'candidate_currency': candidate.currency,
            'candidate_tax_inclusive': candidate.tax_inclusive,
            'candidate_moq': candidate.moq,
            'quote_source': candidate.quote_source,
            'quoted_at': candidate.quoted_at,
            'admission_status': candidate.admission_status,
            'calc_id_ref': latest.calc_id,
            'company_margin_recalced': str(latest.company_margin),
            'breakdown': {'note': 'test_only 提供者为固定结果，无成本细项'},
            'mode': latest.mode,
            'sample_parameters': latest.sample_parameters,
            'created_at': now_iso(), 'created_by': created_by,
        }
        snapshot = DecisionSnapshot(content)
        self._repo.add_snapshot(snapshot)
        return snapshot

    # ------------------------------------------------------------------
    # 确认（03 §6：模拟确认幂等；正式确认七项门禁）
    # ------------------------------------------------------------------

    def demo_confirm(self, snapshot_id: str, actor: str, note: str = '') -> dict:
        """模拟确认（幂等）。事件 demo_confirmed，展示文案固定「模拟确认」。

        永不产生真实产品、不提交正式审批；永不升级为 real_confirmed。
        """
        snapshot = self._require_snapshot(snapshot_id)
        status = snapshot.derived_status()
        if status == 'rejected':
            return {'ok': False, 'reasons': ['snapshot_rejected'], 'status': status}
        if status == 'real_confirmed':
            return {'ok': False, 'reasons': ['already_real_confirmed'], 'status': status}
        if status == 'demo_confirmed':
            # 幂等：重复模拟确认不重复产生事件
            return {'ok': True, 'already': True, 'status': status,
                    'display': DEMO_CONFIRM_LABEL}
        # 过期快照禁止新的确认操作（S2：输入/参数/候选变化后旧快照不再代表当前版本）
        if not self._snapshot_current(snapshot):
            return {'ok': False, 'reasons': ['result_stale'], 'status': status}
        snapshot.append_event(EventKind.DEMO_CONFIRMED.value, actor, note)
        return {'ok': True, 'status': 'demo_confirmed', 'display': DEMO_CONFIRM_LABEL}

    def real_confirm(self, snapshot_id: str, actor: str, note: str = '') -> dict:
        """正式确认——七项门禁全部通过才可 real_confirmed（03 §6）。

        当前公式未通过 (c) 级验证（verification≠verified），
        故真实确认必然被拒并返回原因清单。"""
        snapshot = self._require_snapshot(snapshot_id)
        status = snapshot.derived_status()
        if status == 'real_confirmed':
            return {'ok': True, 'already': True, 'status': status, 'display': '正式确认'}
        reasons = self._real_confirm_gate_reasons(snapshot)
        if reasons:
            return {'ok': False, 'reasons': reasons, 'status': status}
        snapshot.append_event(EventKind.REAL_CONFIRMED.value, actor, note)
        return {'ok': True, 'status': 'real_confirmed', 'display': '正式确认'}

    def _real_confirm_gate_reasons(self, snapshot: DecisionSnapshot) -> list:
        content = snapshot.content()
        reasons: list = []
        # ⑦ 未被拒绝/未重复确认（先判终态，同时封死 demo→real 升级路径）
        status = snapshot.derived_status()
        if status == 'rejected':
            return ['snapshot_rejected']
        if status == 'demo_confirmed':
            reasons.append('demo_confirmed_not_upgradeable_to_real')
        # ① 公式验证状态
        if content['verification'] != Verification.VERIFIED.value:
            reasons.append(f"formula_not_verified:{content['verification']}")
        # ② 参数完整性及版本
        params = self._repo.current_params()
        if params is None:
            reasons.append('params_not_loaded')
        else:
            if params.sample_parameters:
                reasons.append('sample_parameters_not_allowed_for_real')
            reasons.extend(params.missing_codes())
            if content['params_version_ref'] != params.params_version:
                reasons.append('params_version_stale')
        # ③ 关键输入完整性（引用测算 calc_status=ok）
        calc = self._repo.get_calc(content['calc_id_ref'])
        if calc is None or calc.calc_status != CalcStatus.OK.value:
            reasons.append('calc_not_ok')
        # ④ 有效采购价存在
        if content.get('effective_purchase_price_cny') is None:
            reasons.append('missing_effective_price')
        # ⑤ 采购量适用性——按当前 target_qty 对快照自身 offer/sku 动态判定（03 §5）
        qty = self._dynamic_qty_check(content)
        if qty != QtyCheck.PASSED.value:
            reasons.append(f'qty_check_not_passed:{qty}')
        # ⑥ 结果是否过期
        input_set = self._repo.get_input_set(content['task_id'], content['asin'])
        if input_set is None:
            reasons.append('input_set_missing')
        else:
            params_ver = params.params_version if params else None
            sourcing_ver = self._repo.sourcing_version(content['task_id'], content['asin'])
            if not snapshot.is_current(input_set.input_version, params_ver, sourcing_ver):
                reasons.append('result_stale')
        return reasons

    def _dynamic_qty_check(self, content: dict) -> str:
        input_set = self._repo.get_input_set(content['task_id'], content['asin'])
        if input_set is None or input_set.target_qty is None:
            return QtyCheck.UNKNOWN.value
        candidate = self._repo.get_candidate(content['task_id'], content['asin'],
                                             content['offer_id'])
        if candidate is None:
            return QtyCheck.UNKNOWN.value
        sku = candidate.sku(content['sku_id'])
        return candidate.qty_check(input_set.target_qty, sku).value

    def reject_snapshot(self, snapshot_id: str, actor: str, note: str = '') -> dict:
        """显式人工拒绝——追加 rejected 事件（终态）。"""
        snapshot = self._require_snapshot(snapshot_id)
        status = snapshot.derived_status()
        if status == 'rejected':
            return {'ok': True, 'already': True, 'status': status}
        if status == 'real_confirmed':
            return {'ok': False, 'reasons': ['already_real_confirmed'], 'status': status}
        snapshot.append_event(EventKind.REJECTED.value, actor, note)
        return {'ok': True, 'status': 'rejected'}

    # ------------------------------------------------------------------
    # 导出（03 §6：待核验预览单 + 演示水印 + 机器可读 demo 字段）
    # ------------------------------------------------------------------

    def export_snapshot(self, snapshot_id: str) -> dict:
        """导出「待核验预览单」。

        强制内容（无条件包含，浏览器/调用方无法去除）：
        - preview_notice：非正式测算，禁止用于审批或采购决策；
        - snapshot_versions：本快照引用的全部版本（快照序列/计算结果/输入/参数/候选）；
        - expired / expired_reasons：导出时刻该快照是否仍代表当前版本。
        """
        snapshot = self._require_snapshot(snapshot_id)
        content = snapshot.content()
        is_demo = (content['mode'] == Mode.DEMO.value
                   or content['verification'] != Verification.VERIFIED.value)
        status = snapshot.derived_status()
        if status == 'demo_confirmed':
            confirm_display = DEMO_CONFIRM_LABEL
        elif status == 'real_confirmed':
            confirm_display = '正式确认'
        elif status == 'rejected':
            confirm_display = '已拒绝'
        else:
            confirm_display = '待确认'
        expired = not self._snapshot_current(snapshot)
        return {
            'document_kind': 'pending_verification_preview',
            'preview_notice': PREVIEW_NOTICE,
            'watermark': DEMO_WATERMARK if is_demo else None,
            'snapshot_versions': {
                'snapshot_seq': content.get('snapshot_seq'),
                'calc_version_ref': content.get('calc_version_ref'),
                'input_version_ref': content.get('input_version_ref'),
                'params_version_ref': content.get('params_version_ref'),
                'sourcing_version_ref': content.get('sourcing_version_ref'),
            },
            'expired': expired,
            'expired_reasons': ([] if not expired else [
                '输入/参数/候选版本已变化，本快照不再代表当前结果；'
                '如需当前结果请重新测算并生成新快照（旧快照仍可追溯）。',
            ]),
            'machine_readable': {
                'demo': is_demo,
                'mode': content['mode'],
                'verification': content['verification'],
                'approved_for_decision': False,   # 恒 False：本轮不开放正式确认/审批/转产品
            },
            'confirm_display': confirm_display,
            'snapshot': content,
            'events': [{'event_id': e.event_id, 'kind': e.kind, 'actor': e.actor,
                        'at': e.at, 'note': e.note} for e in snapshot.events],
        }

    # ------------------------------------------------------------------
    # 转待开发产品占位（03 §4.7）
    # ------------------------------------------------------------------

    def convert_to_pending_product(self, snapshot_id: str, created_by: str) -> dict:
        """转待开发产品占位。要求 real_confirmed——当前公式未验证、real 确认
        必拒，故本操作当前恒 blocked；无真实产品生成。"""
        snapshot = self._require_snapshot(snapshot_id)
        status = snapshot.derived_status()
        if status != 'real_confirmed':
            return {'ok': False, 'reasons': ['real_confirmation_required'],
                    'current_status': status}
        content = snapshot.content()
        try:
            product = self._repo.add_pending_product(
                content['task_id'], content['asin'],
                content['offer_id'], content['sku_id'],
                snapshot.snapshot_id, created_by)
        except DuplicatePendingProductError:
            return {'ok': False, 'reasons': ['duplicate_four_tuple']}
        return {'ok': True, 'pending_product_id': product.pending_product_id}

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _require_snapshot(self, snapshot_id: str) -> DecisionSnapshot:
        snapshot = self._repo.get_snapshot(snapshot_id)
        if snapshot is None:
            raise ValueError('snapshot_not_found')
        return snapshot

    def _snapshot_current(self, snapshot: DecisionSnapshot) -> bool:
        """快照是否仍代表当前版本（输入/参数/候选三版本一致）。"""
        content = snapshot.content()
        input_set = self._repo.get_input_set(content['task_id'], content['asin'])
        if input_set is None:
            return False
        params = self._repo.current_params()
        return snapshot.is_current(
            input_set.input_version,
            params.params_version if params else None,
            self._repo.sourcing_version(content['task_id'], content['asin']))

    @staticmethod
    def _coerce(fields: dict, allowed: set) -> dict:
        out = {}
        for key, value in fields.items():
            if key not in allowed:
                raise ValueError(f'unknown_field:{key}')
            if value is None:
                out[key] = None
            elif key == 'target_qty':
                out[key] = int(value)
            elif key in _DEC_FIELDS:
                out[key] = dec(value)
            else:
                out[key] = value
        return out
