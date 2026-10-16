"""预立项决策预览 · 本地纵向切片 — 预立项流程编排/状态机/门禁语义验证。

对应文档：docs/preinitiation/（02/03/04/05/06/07）
保证范围：仅本地验证。不含真实公式实现（真实入口 blocked）、
不含任何生产系统集成、持久化或并发保障。
本轮新增（对照用户要求）：
- 计算结果版本 calc_version 与快照序列版本 snapshot_seq（区别于
  输入/参数/候选版本，不混用单一 status 字段）；
- 快照幂等：同一计算结果重复请求不重复创建快照；
- 导出「待核验预览单」强制水印与版本/过期状态；
- owner 级工作区**数据分区**（workspace.WorkspaceRegistry，非登录体系、非安全隔离——
  X-Owner-Id 由客户端自报可被冒用；生产适配要求 owner 来自现有系统验证后的
  用户上下文，缺少可信身份时必须拒绝，见 workspace.py 生产适配契约）。
"""
from .repository import GUARANTEE, InMemoryRepository
from .service import PREVIEW_NOTICE, PreinitiationService

__all__ = ['GUARANTEE', 'InMemoryRepository', 'PreinitiationService', 'PREVIEW_NOTICE']
