"""计算提供者接口 —— verification 三级区分（verified/unverified/test_only，03 §6）。

真实公式未确认前：真实入口返回 blocked + 原因清单，不输出任何数值；
test_only 仅用于验证编排，不得宣称已实现或已对账 OP 计算（03 §10）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from .domain import CalcStatus, Mode, Verification

FORMULA_VERSION = 'op_profit_formula_v1'
BRANCH_US_AMAZON_SC = 'branch_us_amazon_sc'


@dataclass
class CalcRequest:
    task_id: str
    asin: str
    input_version: int
    params_version: Optional[int]
    mode: Mode
    selling_price_usd: Optional[Decimal]
    promotion_fee_ratio: Optional[Decimal]
    fx_usd_to_cny: Optional[Decimal]
    purchase_price_cny: Optional[Decimal]
    purchase_price_kind: str
    params_values: dict = field(default_factory=dict)


@dataclass
class ProviderResult:
    calc_status: CalcStatus
    company_margin: Optional[Decimal] = None   # blocked 时不输出任何数值
    reasons: list = field(default_factory=list)


class CalculationProvider(ABC):
    """计算提供者接口（S1 §二·计算部分）。"""

    verification: Verification
    formula_version: str = FORMULA_VERSION
    branch: str = BRANCH_US_AMAZON_SC

    @abstractmethod
    def calculate(self, request: CalcRequest) -> ProviderResult:
        """执行计算并返回结果。"""


class TestOnlyProvider(CalculationProvider):
    """固定结果测试提供者 —— verification=test_only。

    返回值为构造时给定的固定利润率（可为负，验证"负利润率合法"路径），
    与任何真实口径无关：
    - 不得用于正式确认（真实确认门禁①②强制拒绝）；
    - 不得宣称已实现或已对账 OP 计算（03 §10）。
    """

    verification = Verification.TEST_ONLY

    def __init__(self, fixed_margin: Decimal = Decimal('0.18')):
        self._fixed_margin = fixed_margin

    def calculate(self, request: CalcRequest) -> ProviderResult:
        return ProviderResult(
            calc_status=CalcStatus.OK,
            company_margin=self._fixed_margin,
            reasons=[],
        )


class RealOpProvider(CalculationProvider):
    """真实 OP 计算入口 —— 当前 blocked（03 §1.3/§1.5/§6）。

    branch_us_amazon_sc 未通过 (c) 级验证（当前不存在任何 (c) 级公式）：
    - D1/D2：成本清单歧义（公司口径 vs 通用口径）；
    - D5：反推公式代数矛盾（三种平台家族反推结构互不兼容）；
    - Q1：口径未裁决；Q3：反推采购价口径未确认（反推公式一律不实现）；
    - B1：OP 费率参数表未获得。
    故入口返回 blocked + 原因清单，不输出任何数值。
    """

    verification = Verification.UNVERIFIED

    def calculate(self, request: CalcRequest) -> ProviderResult:
        return ProviderResult(
            calc_status=CalcStatus.BLOCKED,
            company_margin=None,
            reasons=[
                'formula_branch_blocked:D1',
                'formula_branch_blocked:D2',
                'formula_branch_blocked:D5',
                'formula_branch_not_verified:Q1',
                'reverse_formulas_not_implemented:Q3',
                'op_params_unavailable:B1',
            ],
        )
