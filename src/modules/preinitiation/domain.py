"""S1 领域模型 —— 对应 docs/preinitiation/03-data-and-calculation-contract.md。

本模块只定义数据结构与纯领域行为（互斥校验、完整性缺失码、
qty_check / 有效采购价推导、快照不可变内容+追加事件），不含 I/O。

保证范围（03 §7）：仅本地验证。无持久化、无跨进程唯一性、无并发保障。
"""
from __future__ import annotations

import uuid
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def dec(value) -> Optional[Decimal]:
    """宽松 Decimal 转换；None 透传——缺失就是缺失，禁止默认 0（03 §1.4）。"""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid_decimal:{value}") from exc


# ---------------------------------------------------------------------------
# 枚举（值与 03 契约一致）
# ---------------------------------------------------------------------------

class Mode(str, Enum):
    DEMO = 'demo'
    REAL = 'real'


class Verification(str, Enum):
    VERIFIED = 'verified'      # (c) 级：OP 标准样例对账通过——当前不存在（03 §1.1）
    UNVERIFIED = 'unverified'  # (b) 级：仅推导/未对账
    TEST_ONLY = 'test_only'    # 固定测试结果，与 OP 口径无关


class CalcStatus(str, Enum):
    INPUT_INCOMPLETE = 'input_incomplete'  # 用户侧关键输入缺失/非法（03 §2.1）
    OK = 'ok'
    NOT_COMPUTABLE = 'not_computable'      # 系统侧参数缺失（03 §1.4，禁止默认 0）
    BLOCKED = 'blocked'                    # 真实入口：公式未验证（D1/D2/D5/Q1/Q3）


class QtyCheck(str, Enum):
    UNKNOWN = 'unknown'          # target_qty 未维护——永不 passed（03 §2.2）
    PASSED = 'passed'
    VIOLATED = 'violated'
    NOT_APPLICABLE = 'not_applicable'


class PriceKind(str, Enum):
    ESTIMATED = 'estimated'      # 03 §3#4 首轮估算采购价
    EFFECTIVE = 'effective'      # 03 §3#6 有效采购价（SKU 级，唯一可用于复算/快照）


class EventKind(str, Enum):
    DEMO_CONFIRMED = 'demo_confirmed'  # 模拟确认——永不升级为 real_confirmed（03 §4.6）
    REAL_CONFIRMED = 'real_confirmed'
    REJECTED = 'rejected'


class CandidateStatus(str, Enum):
    PENDING_SELECTION = 'pending_selection'
    SELECTED = 'selected'
    DISCARDED = 'discarded'


# ---------------------------------------------------------------------------
# 输入集（03 §4.1）
# ---------------------------------------------------------------------------

# 修改任一计算相关字段 → input_version+1（触发失效，03 §5）
CALC_FIELDS = (
    'selling_price_usd', 'target_margin_pct', 'promotion_fee_ratio',
    'fx_usd_to_cny', 'fx_fetched_at',
    'target_purchase_price_min_cny', 'target_purchase_price_max_cny',
    'target_qty', 'estimated_purchase_price_cny',
)
# 仅修改 meta 字段 → meta_version+1（不触发失效，03 §5）
META_FIELDS = ('note',)


@dataclass
class InputSet:
    task_id: str
    asin: str
    market: str = 'US'                # 一期固定
    platform: str = 'amazon_sc'       # 一期固定
    selling_price_usd: Optional[Decimal] = None
    target_margin_pct: Optional[Decimal] = None     # 存储 0–1；与售价互斥录入
    promotion_fee_ratio: Optional[Decimal] = None   # 0–1
    fx_usd_to_cny: Optional[Decimal] = None
    fx_fetched_at: Optional[str] = None
    target_purchase_price_min_cny: Optional[Decimal] = None
    target_purchase_price_max_cny: Optional[Decimal] = None
    target_qty: Optional[int] = None                # None=未维护（未知）；0 不承载语义
    estimated_purchase_price_cny: Optional[Decimal] = None  # 首轮估算采购价（03 §3#4）
    note: Optional[str] = None                      # meta 字段
    input_version: int = 1
    meta_version: int = 1
    updated_at: str = field(default_factory=now_iso)
    updated_by: str = ''

    def validate(self) -> None:
        """录入互斥与取值校验（03 §4.1）。注意：互斥约束不是完整性判据（03 §2.1）。"""
        if self.selling_price_usd is not None and self.target_margin_pct is not None:
            raise ValueError('mutual_exclusion_violated:selling_price+target_margin')
        if self.selling_price_usd is not None and self.selling_price_usd <= 0:
            raise ValueError('invalid_selling_price')
        if self.target_margin_pct is not None and not (Decimal(-1) < self.target_margin_pct < Decimal(1)):
            raise ValueError('invalid_target_margin')
        if self.promotion_fee_ratio is not None and not (Decimal(0) <= self.promotion_fee_ratio <= Decimal(1)):
            raise ValueError('invalid_promotion_ratio')
        if self.fx_usd_to_cny is not None and self.fx_usd_to_cny <= 0:
            raise ValueError('invalid_fx')
        if self.target_qty is not None and self.target_qty <= 0:
            # 0 禁止：不得用 0 同时表达未知和不限量（03 §2.2）；未知请用 None
            raise ValueError('invalid_target_qty:use_none_for_unknown')
        if (self.target_purchase_price_min_cny is not None
                and self.target_purchase_price_max_cny is not None
                and self.target_purchase_price_min_cny > self.target_purchase_price_max_cny):
            raise ValueError('invalid_target_price_range')
        if self.estimated_purchase_price_cny is not None and self.estimated_purchase_price_cny <= 0:
            raise ValueError('invalid_estimated_purchase_price')

    def forward_calc_missing(self, price_kind: PriceKind) -> list:
        """正算公司利润率所需输入缺失码（03 §2.1）。

        反推售价 blocked（D5），故正算始终要求 selling_price；
        target_margin 仅用于结果校验（below/meets/above），不是正算输入。
        """
        missing = []
        if self.selling_price_usd is None:
            missing.append('missing_selling_price')
            if self.target_margin_pct is not None:
                missing.append('reverse_price_calc_blocked:D5')
        if self.promotion_fee_ratio is None:
            missing.append('missing_promotion_ratio')
        if self.fx_usd_to_cny is None:
            missing.append('missing_fx')
        if price_kind == PriceKind.ESTIMATED and self.estimated_purchase_price_cny is None:
            missing.append('missing_purchase_price')
        return missing


# ---------------------------------------------------------------------------
# 成本参数（系统侧，03 §1.4）
# ---------------------------------------------------------------------------

# key -> 缺失原因码。缺→not_computable，禁止按 0（03 §1.4/§1.5）。
REQUIRED_PARAMS = {
    'first_leg_cny': 'missing_first_leg',
    'design_fee_cny': 'missing_design_fee',
    'referral_rate': 'missing_referral_rate',
    'storage_rate': 'missing_storage_rate',
    'last_mile_usd': 'missing_last_mile',
    'operation_fee_usd': 'missing_operation_fee',
    'inbound_fee_usd': 'missing_inbound_fee',
    'withdrawal_fee_rate': 'missing_withdrawal_rate',
}


@dataclass
class CostParams:
    params_version: int
    values: dict                    # key -> Decimal
    sample_parameters: bool         # True=样例参数（仅 demo 域可用，03 §6）
    source: str                     # 'sample_demo' | 'op_B1'（后者当前未获得）

    def missing_codes(self) -> list:
        return [code for key, code in REQUIRED_PARAMS.items()
                if self.values.get(key) is None]


# ---------------------------------------------------------------------------
# 测算结果（不可变记录，03 §4.2）
# ---------------------------------------------------------------------------

@dataclass
class Calculation:
    calc_id: str
    calc_version: int                # 计算结果版本：同一任务×ASIN 内每次计算递增（区别于引用的输入/参数/候选版本）
    task_id: str
    asin: str
    input_version_ref: int
    params_version_ref: Optional[int]
    formula_version: str
    branch: str
    verification: str               # verified | unverified | test_only
    mode: str                       # demo | real
    calc_status: str
    reasons: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    company_margin: Optional[Decimal] = None   # 可为负——合法结果（03 §1.5，AC12）
    target_margin_check: Optional[str] = None  # below|meets|above——与结果有效性分离
    purchase_price_cny: Optional[Decimal] = None
    purchase_price_kind: Optional[str] = None  # estimated | effective
    sample_parameters: bool = False
    calculated_at: str = field(default_factory=now_iso)
    sourcing_version_ref: Optional[int] = None   # 候选/选择版本依赖（S2 审计修复）

    def is_current(self, input_version: int, params_version: Optional[int],
                   sourcing_version: Optional[int] = None) -> bool:
        """派生属性：引用版本与当前版本一致才代表当前结果（03 §5）。

        sourcing_version：候选新增/编辑/选择会使其变化 → 旧结果过期（S2 审计修复）。
        """
        if self.input_version_ref != input_version:
            return False
        if not self._version_matches(self.params_version_ref, params_version):
            return False
        return self._version_matches(self.sourcing_version_ref, sourcing_version)

    @staticmethod
    def _version_matches(ref: Optional[int], current: Optional[int]) -> bool:
        if current is None:
            return ref is None
        return ref == current


# ---------------------------------------------------------------------------
# 手工候选（03 §4.5 降级路径）
# ---------------------------------------------------------------------------

@dataclass
class LadderPrice:
    qty_from: int
    qty_to: Optional[int]           # None=无上限
    price_cny: Decimal


@dataclass
class SkuQuote:
    sku_id: str
    spec: str = ''
    sku_price_cny: Optional[Decimal] = None  # None=无 SKU 级价格；搜索报价不得替代（03 §3）
    ladder_prices: list = field(default_factory=list)  # list[LadderPrice]


def _validate_ladder(sku_id: str, tiers: list) -> None:
    """阶梯价边界/重复/非法校验（S2 审计最小修复）。

    规则：qty_from≥1；qty_to≥qty_from；单价>0；qty_from 不重复；
    区间不重叠；最多一个开区间（qty_to=None）且必须在末尾。
    非法数据一律拒绝并给出原因码，不做静默兜底。
    """
    seen_from = set()
    open_seen = False
    prev: Optional[LadderPrice] = None
    for tier in tiers:
        if tier.qty_from < 1:
            raise ValueError(f'invalid_ladder_qty_from:{sku_id}:{tier.qty_from}')
        if tier.qty_from in seen_from:
            raise ValueError(f'duplicate_ladder_tier:{sku_id}:{tier.qty_from}')
        seen_from.add(tier.qty_from)
        if tier.qty_to is not None and tier.qty_to < tier.qty_from:
            raise ValueError(f'invalid_ladder_range:{sku_id}:{tier.qty_from}-{tier.qty_to}')
        if tier.price_cny is None or tier.price_cny <= 0:
            raise ValueError(f'invalid_ladder_price:{sku_id}')
        if tier.qty_to is None:
            if open_seen:
                raise ValueError(f'multiple_open_ladder_tier:{sku_id}')
            open_seen = True
        if prev is not None:
            if prev.qty_to is None:
                raise ValueError(f'overlapping_ladder_tier:{sku_id}:{tier.qty_from}')
            if tier.qty_from <= prev.qty_to:
                raise ValueError(f'overlapping_ladder_tier:{sku_id}:{tier.qty_from}')
        prev = tier


def validate_skus(skus: list) -> None:
    """SKU 集合校验：id 不重复、单价合法、阶梯价合法（S2 审计最小修复）。"""
    seen = set()
    for sku in skus:
        if sku.sku_id in seen:
            raise ValueError(f'duplicate_sku_id:{sku.sku_id}')
        seen.add(sku.sku_id)
        if sku.sku_price_cny is not None and sku.sku_price_cny <= 0:
            raise ValueError(f'invalid_sku_price:{sku.sku_id}')
        _validate_ladder(sku.sku_id, sku.ladder_prices)


@dataclass
class Candidate:
    candidate_id: str
    task_id: str
    asin: str
    offer_id: str
    source_type: str = 'manual'
    offer_price_cny: Optional[Decimal] = None  # 搜索/摘要报价——仅展示（03 §3#5）
    quote_source: str = ''                     # 报价来源（manual 必填）
    quoted_at: str = ''                        # 报价获取时间（必填）
    currency: str = 'CNY'
    tax_inclusive: Optional[bool] = None       # 含税口径，未知=None（不得臆断）
    moq: Optional[int] = None                  # 未知=None
    skus: list = field(default_factory=list)   # list[SkuQuote]
    candidate_status: str = CandidateStatus.PENDING_SELECTION.value
    admission_status: str = 'unknown'          # manual 来源固定 unknown——≠已满足 1688 准入

    def sku(self, sku_id: str) -> Optional[SkuQuote]:
        for s in self.skus:
            if s.sku_id == sku_id:
                return s
        return None

    def qty_check(self, target_qty: Optional[int], sku: Optional[SkuQuote]) -> QtyCheck:
        """按当前 target_qty 动态计算（03 §2.2/§4.5）。

        target_qty=None → 永远 unknown（不得宣称 MOQ/阶梯价校验通过）。
        """
        return self.qty_check_detail(target_qty, sku)[0]

    def qty_check_detail(self, target_qty: Optional[int],
                         sku: Optional[SkuQuote]) -> tuple:
        """返回 (QtyCheck, 原因码)——供界面展示具体原因（S2）。

        原因码：target_qty_unknown / no_sku_selected / no_moq_or_ladder /
        below_moq / qty_out_of_ladder_range / ok。
        """
        if target_qty is None:
            return QtyCheck.UNKNOWN, 'target_qty_unknown'
        if sku is None:
            return QtyCheck.UNKNOWN, 'no_sku_selected'
        has_moq = self.moq is not None
        has_ladder = bool(sku.ladder_prices)
        if not has_moq and not has_ladder:
            return QtyCheck.NOT_APPLICABLE, 'no_moq_or_ladder'
        if has_moq and target_qty < self.moq:
            return QtyCheck.VIOLATED, 'below_moq'
        if has_ladder and self._tier_for(sku, target_qty) is None:
            return QtyCheck.VIOLATED, 'qty_out_of_ladder_range'
        return QtyCheck.PASSED, 'ok'

    def effective_price(self, target_qty: Optional[int],
                        sku: Optional[SkuQuote]) -> tuple:
        """有效采购价（03 §3#6）：仅取 SKU 级价格；offer 摘要价永不自动升级。

        返回 (price, reason)：price=None 时 reason 说明原因。
        """
        if sku is None:
            return None, 'no_sku_selected'
        if sku.sku_price_cny is None:
            # 无 SKU 级价格——搜索报价不得充当有效采购价（AC6）
            return None, 'missing_effective_price'
        if sku.ladder_prices:
            if target_qty is None:
                return None, 'target_qty_unknown_for_ladder'
            tier = self._tier_for(sku, target_qty)
            if tier is None:
                return None, 'qty_out_of_ladder_range'
            return tier.price_cny, None
        return sku.sku_price_cny, None

    def _tier_for(self, sku: SkuQuote, qty: int) -> Optional[LadderPrice]:
        for tier in sku.ladder_prices:
            upper_ok = tier.qty_to is None or qty <= tier.qty_to
            if qty >= tier.qty_from and upper_ok:
                return tier
        return None


# ---------------------------------------------------------------------------
# 决策快照：不可变内容 + 可追加事件（03 §4.6）
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SnapshotEvent:
    """事件不可变（frozen）——追加后不得被调用方改写（S2 审计修复）。"""

    event_id: str
    kind: str                  # demo_confirmed | real_confirmed | rejected
    actor: str
    at: str
    note: str = ''


class DecisionSnapshot:
    """决策快照（03 §4.6）。

    - content() 返回深拷贝——历史快照内容不因后续输入修改而变化；
    - is_current 为派生属性：版本不一致只意味着"不再代表当前版本"，
      不改写内容与事件历史；
    - 事件仅追加（append_event），状态由事件序列派生。
    """

    def __init__(self, content: dict):
        self._content: dict = deepcopy(content)
        self._events: list = []

    @property
    def snapshot_id(self) -> str:
        return self._content['snapshot_id']

    def content(self) -> dict:
        return deepcopy(self._content)

    @property
    def events(self) -> tuple:
        return tuple(self._events)

    def derived_status(self) -> str:
        kinds = {e.kind for e in self._events}
        if EventKind.REAL_CONFIRMED.value in kinds:
            return 'real_confirmed'
        if EventKind.REJECTED.value in kinds:
            return 'rejected'
        if EventKind.DEMO_CONFIRMED.value in kinds:
            return 'demo_confirmed'
        return 'pending_confirm'

    def is_current(self, input_version: int, params_version: Optional[int],
                   sourcing_version: Optional[int] = None) -> bool:
        if self._content['input_version_ref'] != input_version:
            return False
        if not Calculation._version_matches(self._content.get('params_version_ref'),
                                            params_version):
            return False
        return Calculation._version_matches(self._content.get('sourcing_version_ref'),
                                            sourcing_version)

    def append_event(self, kind: str, actor: str, note: str = '') -> SnapshotEvent:
        """仅追加事件（服务层调用）。"""
        if kind not in {k.value for k in EventKind}:
            raise ValueError(f'invalid_event_kind:{kind}')
        event = SnapshotEvent(new_id('evt'), kind, actor, now_iso(), note)
        self._events.append(event)
        return event


# ---------------------------------------------------------------------------
# 待开发产品占位（03 §4.7，四元组防重）
# ---------------------------------------------------------------------------

@dataclass
class PendingProduct:
    pending_product_id: str
    task_id: str
    asin: str
    offer_id: str
    sku_id: str
    snapshot_id_ref: str
    created_by: str
    created_at: str = field(default_factory=now_iso)
