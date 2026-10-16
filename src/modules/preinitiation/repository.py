"""内存 Repository —— 仅用于 S1 本地验证（03 §7 保证边界）。

GUARANTEE 是本实现保证范围的显式声明，任何使用方必须能读到它。
"""
from __future__ import annotations

from typing import Optional

from .domain import PendingProduct, new_id

GUARANTEE = (
    '【S1 内存实现保证范围】仅保证：单进程内状态一致、快照内容不可变'
    '（frozen 内容+深拷贝读取）、四元组进程内防重。'
    '不保证：持久化、跨进程唯一性、并发安全。'
    '不得用于生产或真实决策；生产级唯一约束/审计需独立存储方案批准后方可实现。'
)


class DuplicatePendingProductError(Exception):
    """四元组 (task_id, asin, offer_id, sku_id) 重复——进程内防重（03 §4.7）。"""


class InMemoryRepository:
    """进程内内存仓储。

    简化说明：成本参数为全局单份+版本递增（真实按品类/重量取数的
    参数表待 B1，见 03 §9）；无任何持久化。
    """

    def __init__(self):
        self.guarantee: str = GUARANTEE
        self._input_sets = {}
        self._params = None
        self._params_version_seq = 0
        self._sourcing_versions = {}
        self._calc_versions = {}
        self._snapshot_seqs = {}
        self._candidates = {}
        self._selections = {}
        self._calcs = []
        self._snapshots = {}
        self._pending_products = []
        self._four_tuples = set()

    # —— 候选/选择依赖版本（S2 审计修复：候选与选择变化纳入结果依赖）——
    def sourcing_version(self, task_id: str, asin: str) -> int:
        return self._sourcing_versions.get((task_id, asin), 0)

    def bump_sourcing_version(self, task_id: str, asin: str) -> int:
        key = (task_id, asin)
        self._sourcing_versions[key] = self._sourcing_versions.get(key, 0) + 1
        return self._sourcing_versions[key]

    # —— 计算结果版本：同一任务×ASIN 内每次计算递增（本轮新增）——
    def next_calc_version(self, task_id: str, asin: str) -> int:
        key = (task_id, asin)
        self._calc_versions[key] = self._calc_versions.get(key, 0) + 1
        return self._calc_versions[key]

    def calc_version(self, task_id: str, asin: str) -> Optional[int]:
        return self._calc_versions.get((task_id, asin))

    # —— 快照版本序列：同一任务×ASIN 内递增（本轮新增）——
    def next_snapshot_seq(self, task_id: str, asin: str) -> int:
        key = (task_id, asin)
        self._snapshot_seqs[key] = self._snapshot_seqs.get(key, 0) + 1
        return self._snapshot_seqs[key]

    def snapshot_seq(self, task_id: str, asin: str) -> Optional[int]:
        return self._snapshot_seqs.get((task_id, asin))

    # —— 成本参数（全局单份，S1 简化）——
    def next_params_version(self) -> int:
        self._params_version_seq += 1
        return self._params_version_seq

    def set_params(self, params) -> None:
        self._params = params

    def current_params(self):
        return self._params

    # —— 输入集 ——
    def save_input_set(self, input_set) -> None:
        self._input_sets[(input_set.task_id, input_set.asin)] = input_set

    def get_input_set(self, task_id: str, asin: str):
        return self._input_sets.get((task_id, asin))

    # —— 候选 ——
    def add_candidate(self, candidate) -> None:
        key = (candidate.task_id, candidate.asin, candidate.offer_id)
        self._candidates[key] = candidate

    def get_candidate(self, task_id: str, asin: str, offer_id: str):
        return self._candidates.get((task_id, asin, offer_id))

    def list_candidates(self, task_id: str, asin: str) -> list:
        return [c for (t, a, _), c in self._candidates.items()
                if t == task_id and a == asin]

    # —— 选择（任务×ASIN 唯一）——
    def set_selection(self, task_id: str, asin: str, offer_id: str, sku_id: str) -> None:
        self._selections[(task_id, asin)] = (offer_id, sku_id)

    def get_selection(self, task_id: str, asin: str):
        return self._selections.get((task_id, asin))

    # —— 测算记录 ——
    def add_calc(self, calc) -> None:
        self._calcs.append(calc)

    def latest_calc(self, task_id: str, asin: str):
        for calc in reversed(self._calcs):
            if calc.task_id == task_id and calc.asin == asin:
                return calc
        return None

    def get_calc(self, calc_id: str):
        for calc in self._calcs:
            if calc.calc_id == calc_id:
                return calc
        return None

    # —— 快照 ——
    def add_snapshot(self, snapshot) -> None:
        self._snapshots[snapshot.snapshot_id] = snapshot

    def get_snapshot(self, snapshot_id: str):
        return self._snapshots.get(snapshot_id)

    def snapshot_for_calc(self, calc_id: str):
        """查找引用某计算结果的既有快照（快照幂等：同一 calc 不重复建快照）。"""
        for snapshot in self._snapshots.values():
            if snapshot.content().get('calc_id_ref') == calc_id:
                return snapshot
        return None

    def snapshots(self, task_id: str, asin: str) -> list:
        return [s for s in self._snapshots.values()
                if s.content()['task_id'] == task_id
                and s.content()['asin'] == asin]

    # —— 待开发产品（四元组防重，进程内，03 §4.7 保证边界）——
    def add_pending_product(self, task_id: str, asin: str, offer_id: str,
                            sku_id: str, snapshot_id_ref: str, created_by: str) -> PendingProduct:
        key = (task_id, asin, offer_id, sku_id)
        if key in self._four_tuples:
            raise DuplicatePendingProductError(f'duplicate_four_tuple:{key}')
        self._four_tuples.add(key)
        product = PendingProduct(
            pending_product_id=new_id('pp'),
            task_id=task_id, asin=asin, offer_id=offer_id, sku_id=sku_id,
            snapshot_id_ref=snapshot_id_ref, created_by=created_by,
        )
        self._pending_products.append(product)
        return product

    def pending_products(self) -> list:
        return list(self._pending_products)
