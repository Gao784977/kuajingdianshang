# 04 · 实施计划与验收（Implementation Plan & Acceptance）

> 前置：01/02/03 文档。工作量等级：S（≤1 人日）/ M（1–3 人日）/ L（>3 人日），不估算精确工期。
> 部署约束（S0 修订）：当前阶段不做数据库迁移/队列/部署平台升级——S1 为进程内内存验证；后续生产存储需求以**独立方案报批**（03 §7），不在本方案内默认完成。宿主系统待 Q4。
> **S0 状态（2026-10-15）**：S1 本地验证切片已实施（/workspace/preinitiation/，见 §4）；真实计算入口按 blocked 实现；反推类公式不实现。
> **S2 状态（2026-10-15 本轮；2026-10-16 S3 验收轮更新）**：S1+S2 模块已**移植入旧项目仓库** `repo-kuajingdianshang/src/modules/preinitiation/`（复用现有项目结构与测试约定，tests/ 下 11 个测试文件 + 1 个辅助器，108 项测试全通过）；新增 calc_version/snapshot_seq 版本体系、快照幂等、待核验预览单导出、owner 级工作区分区（X-Owner-Id，键空间分区非安全隔离——S3 修正）。仓库全量 713 项测试，errors=9（全部为既有 backend/storage 导入错误，见 01 §2.1；与本轮改动无关）。未 commit（待用户审阅）。详见 07 交付报告与 08 验收报告。

---

## 1. 任务拆分（按依赖排序）

### 阶段 T0 · 前置（阻塞解除，业务/研发配合）

| ID | 任务 | 负责 | 等级 | 依赖/阻塞 |
|---|---|---|---|---|
| T0.1 | 提供 OP 费率参数表或只读接口 | 业务/OP 研发 | — | B1 |
| T0.2 | 提供标准对账样例 ≥1 组 | 业务 | — | B3 |
| T0.3 | 确认公式歧义 D1–D5（Q1 扩展/Q2/Q3） | 业务 | — | B8 |
| T0.4 | 1688 API 凭证/测试环境/字段样例 | 寻源通研发 | — | B2 |
| T0.5 | 品牌中心接口文档（任务/待开发产品/审批）+ 流程顺序确认 | 品牌中心研发 | — | B4/Q8 |

### 阶段 T1 · 计算内核（S0 修订：按验证分级重新定界）

| ID | 任务 | 模块 | 等级 | 依赖/状态 |
|---|---|---|---|---|
| T1.1 | Decimal 精度/版本号/不可计算骨架 | calc/kernel | S | **已实施（S1 preinitiation 包）** |
| T1.2 | `branch_us_amazon_sc` 公司利润率正算 | calc/kernel | M | **blocked：待 Q1（D1/D2）+ B1 + B3 对账**；S1 真实入口已按 blocked 返回原因实现 |
| T1.3 | 反推售价 / 0%毛利推算采购价 | calc/kernel | — | **blocked：D5 代数矛盾 + Q3，不作为正式能力实现** |
| T1.4 | 输入校验：缺失/非法→原因码；互斥约束与完整性判定分离 | calc/kernel | S | **已实施（S1）** |
| T1.5 | OP 对账测试（样例逐项比对） | tests | M | **blocked：待 T0.2**；无样例不得宣称对账，内部往返测试不算 |

### 阶段 T2 · 状态机与快照

| ID | 任务 | 模块 | 等级 | 依赖/状态 |
|---|---|---|---|---|
| T2.1 | InputSet 双版本递增（input/meta）+ 失效矩阵 | core/state | M | **已实施（S1）** |
| T2.2 | 测算/约束/批次/候选/快照状态机 + 门禁判定 | core/state | M | **部分实施（S1：测算/候选/快照+确认门禁；批次态待 T3）** |
| T2.3 | 四元组防重 + 幂等确认 | core/state | S | **部分实施（S1：进程内防重+幂等事件；生产级约束待存储方案）** |
| T2.4 | 快照不可变存储与历史查询 | core/state | S | **已实施（S1：内存，frozen 内容+追加事件）** |

### 阶段 T3 · 1688 适配（API 阻塞时并行做降级路径）

| ID | 任务 | 模块 | 等级 | 依赖/状态 |
|---|---|---|---|---|
| T3.1 | 手工候选录入（降级路径） | sourcing/manual | M | **已实施（S1）** |
| T3.2 | 四接口编排客户端 + 批次状态机 | sourcing/api | L | T0.4 |
| T3.3 | 候选准入筛选 + 限量规则 | sourcing/api | M | T3.2 |
| T3.4 | offer/SKU 选择 → 有效采购价提取（价格基准规则） | sourcing | M | **部分实施（S1：手工候选的 SKU 级取价与 qty_check；API 版待 T3.2）** |

### 阶段 T4 · 流程编排与宿主接入

| ID | 任务 | 模块 | 等级 | 依赖/状态 |
|---|---|---|---|---|
| T4.1 | 纵向切片编排 | flow | M | **已实施（S1，demo 域）** |
| T4.2 | 预立项工作区页面 | ui | L | Q4 + T4.1 |
| T4.3 | 转待开发产品（复用品牌中心实体） | integration | M | T0.5/Q8（**顺序冲突未决，见 02 §2.3**） |
| T4.4 | 审批接入 | integration | M | T0.5/Q8 |

**依赖图**：T0 ─┬─→ T3.2 ─→ T3.3/T3.4 ─┐
　　　　　└─→ T0.5 ─→ T4.3/T4.4 ─┤→ T4.2
T1（blocked 项除外）─→ T2 ─→ T4.1 ──┘（S1 已通）

## 2. 风险与回滚

| 风险 | 缓解 | 回滚 |
|---|---|---|
| 公式/参数错误导致错误立项 | blocked 门禁（公式未验证不可 real 确认）；B3 对账强制；sample_parameters 标注 | 计算内核纯函数，回滚=禁用入口，无数据迁移 |
| 反推公式口径错误（D5） | 反推类公式一律不实现为正式能力 | 无需回滚（未上线） |
| 1688 接口额度/稳定性 | 限量规则 + partial_failed 明细 + 手工降级路径 | 关闭 API 模式退回手工候选 |
| 宿主/流程顺序对接超预期（Q8） | 流程顺序未确认前不固化 T4.3/T4.4；可先旁挂只读页交付 | UI 层独立，核心状态机不受影响 |
| 重复生成待开发产品 | 四元组防重（S1 进程内；生产级约束随存储方案）+ 幂等接口 | 数据层约束，无需运行时回滚 |
| 历史快照被篡改质疑 | 快照内容不可变 + 事件仅追加 + 确认人/时间/版本全记录 | 只读审计，无回滚需求 |
| demo 结果误用于真实决策 | demo/real 双轨 + 导出水印 + 机器可读 demo 字段 + real 门禁 | 门禁在服务层，禁用 demo 导出即可 |

## 3. 验收用例（Given/When/Then）

**AC1-D 演示闭环（S1 已覆盖，test_only）**
Given 完整输入+完整参数（样例参数显式标注）+手工候选（SKU 级价格，报价溯源字段齐全）
When 测算→选择→有效采购价复算→生成快照→模拟确认→导出
Then 快照事件=demo_confirmed（展示"模拟确认"）；导出含"演示数据"水印与 {"demo":true,"mode":"demo"} 机器字段；全程不产生真实产品、不提交审批

**AC1-R 真实闭环（blocked；解封条件：Q1 裁决+B1 参数+B3 对账通过+Q8 流程确认）**
Given 公式分支 verification=verified 且参数为当前版、输入完整、qty_check=passed
When 同上演示流程但走 real 确认
Then 快照事件=real_confirmed；按 Q8 裁决顺序接入待开发产品/审批；四元组防重生效（生产级约束已随存储方案落地）

**AC2 关键财务输入/参数缺失**
Given 售价与目标利润率均为空，或汇率缺失，或任一成本参数（头程/设计费/佣金率等）为 None
When 触发测算
Then calc_status=input_incomplete，missing 含对应原因码；不产生任何数值输出；**缺失成本项不得默认为 0**；快照生成被门禁阻止

**AC3 结果过期**
Given 快照v1已生成（input_version=5）
When 修改售价使 input_version=6（或 params_version 变更）
Then 测算/快照v1 的 is_current=False；real 确认被阻止（result_stale）；须重算生成快照v2；v1 内容与事件保留可查

**AC4 1688 返回零候选**
Given 溯源批次执行完成且准入筛选后无候选
Then sourcing_status=succeeded_zero；不自动重试；允许手动不限价重新溯源（新批次）

**AC5 部分接口失败**
Given 图搜成功、关键词接口超时
Then sourcing_status=partial_failed 且 failure_detail 记录失败接口；已获候选可继续选择并标 incomplete_detail

**AC6 SKU 无有效价格**
Given 所选 SKU 无 SKU 级价格（仅有 offer 搜索报价）
Then 有效采购价显示"--"；**搜索报价不得自动充当有效采购价**；复算=不可计算(missing_effective_price)；不可生成快照

**AC7 重复请求不重复生成**
Given 快照v1已确认且四元组已存在
When 重放确认请求或再次选择同 offer/sku 生成
Then 确认幂等（不重复产生事件）；生成被防重拒绝并提示

**AC8 重新溯源不破坏已转产品**
Given 批次A中offer-O已 converted
When 重新溯源产生批次B且再次召回offer-O
Then offer-O 在批次B中不可再选；批次A的待开发产品、供应商关系、快照均不变

**AC9 越权访问和确认被拒绝**
Given 用户U2对任务无开发权限
When U2调用确认/生成/溯源写接口
Then 返回403/权限拒绝；数据无变更（**注：S1 未实现权限层——属宿主接入范围，接口级权限待 B4**）

**AC10 历史决策快照可追溯**
Given 项目历经 input_version 3→7、快照v1被拒、v2已确认并转产品
When 打开快照历史
Then 按时间列出全部快照：各自输入版本、公式版本、批次、候选、价格、事件（确认人/时间/拒绝原因）；**v1/v2 内容不因后续输入修改而变化**；审批引用提交时的 snapshot_id

**AC11 样例参数禁止真实决策**
Given 测算使用样例参数或 test_only 提供者
Then 所有结果 sample_parameters=true / verification=test_only 显式标注；real 确认门禁拒绝；导出带演示水印

**AC12 负利润率是合法结果（S0 新增）**
Given 完整输入下测算得出公司利润率为负
Then calc_status=ok 且 company_margin 为负值；与目标利润率校验（below_target）分离呈现；不视为不可计算

**AC13 采购量未知（S0 新增）**
Given target_qty=None（未维护）
Then qty_check=unknown（**永不 passed**）；MOQ/阶梯价校验状态显示未知；real 确认被 qty 门禁阻止

## 4. 纵向切片 S1+S2（已实施，本地验证）

**位置（S2 起为正式位置）**：旧项目仓库 `repo-kuajingdianshang/src/modules/preinitiation/`——按本轮授权"优先复用现有项目结构和入口"移植入仓，复用其 `src/modules/` 结构与 `tests/` 平铺测试约定（`tests._preinitiation_helpers` 辅助器）。S1 阶段曾在 /workspace/preinitiation/ 独立开发（当时理由：旧项目运行层缺失、无共享模块）；S2 移植后仓库内模块为唯一维护副本，独立目录仅作历史参考、不再更新。纯 Python 标准库，无新框架、无独立登录。

```
输入(双版本管理/互斥校验/完整性校验/缺失不填0)
→ 测算(test_only 提供者返回固定结果；RealOpProvider 入口 blocked 返回 D1/D2/D5/Q1/Q3 原因)
→ 手工候选(报价来源/时间必填, 准入=unknown, tax_inclusive 可未知)
→ 选择(SKU级有效采购价+阶梯价；搜索报价仅展示)
→ 复算 → 快照(frozen 内容 + 追加事件；按 calc_id 幂等)
→ 模拟确认(幂等) / 正式确认(七项门禁，当前必拒并返回原因清单)
→ 导出(待核验预览单：强制水印+版本+过期状态+approved_for_decision=false)
→ 转待开发产品占位(要求 real 确认，当前 blocked)
```

- **已含**：输入校验与版本管理、依赖记录与失效判断、手工候选及有效采购价校验、快照内容生成、demo/real 确认门禁、内存 Repository（保证范围显式声明）、可执行示例、自动化测试；**S2 新增**：calc_version/snapshot_seq 六类版本体系、快照幂等、待核验预览单导出、owner 级工作区分区（WorkspaceRegistry + X-Owner-Id，键空间分区、非安全隔离——S3 修正）、VCS 守护测试；**S3 验收轮新增**：门禁字段篡改防提级测试、owner 冒用实测、幂等键冲突与并发验证（详见 08）
- **明确不含**：真实公式（blocked）、1688 API、品牌中心对接、审批提交、持久化/并发保障、真实"确认并转产品"操作
- **运行示例**：`cd /workspace/repo-kuajingdianshang && python3 -m src.modules.preinitiation.example`
- **启动本地预览**：`cd /workspace/repo-kuajingdianshang && python3 -m src.modules.preinitiation.webapp`（仅监听 127.0.0.1；操作步骤见 06 走查文档）
- **运行测试**：`cd /workspace/repo-kuajingdianshang && python3 -m unittest discover -s tests -t . -p "test_preinitiation_*.py"`（108 项）
- **全量测试**：`cd /workspace/repo-kuajingdianshang && python3 -m unittest discover`（713 项，errors=9 均为既有 backend.storage 导入错误，无断言失败；⚠ 环境须装 requirements.txt 声明的 openpyxl，否则另有 34+5 项无关失败）

## 5. 业务确认问题（最少集，评审用）

| # | 问题 | 关联 |
|---|---|---|
| Q1 | 公司利润率（ql 文案）与通用利润率（nl 展示）成本清单差异（D1/D2）以哪个为准？**扩展：Amazon SC 反推公式代数矛盾（D5）以正算解、文案式还是后端实现为准（需样例）？**美区所得税是否适用？ | B8/B3 |
| Q2 | 预立项阶段是否输出个人利润率（尚无立项人/库存归属）？ | D4 |
| Q3 | 0%毛利推算采购价是否计入头程/设计费？目标口径=公司利润率0%？ | B6/D3 |
| Q4 | 预立项工作区宿主：品牌中心新模块 or OP 常用工具扩展？ | B4 |
| Q5 | 快照确认角色；**是否将快照确认实现为现有提交动作前的校验门禁（而非新增审批节点）？** | 02 §4 |
| Q6 | 公司利润率阈值（10%/15%）是否作为一期硬门禁（低于即阻止快照生成/仅提示）？ | OP 页面现有提示 |
| Q7 | 汇率数据源（手工/接口）及更新频率？ | 03 §9 |
| Q8 | **产品生成时点与审批顺序**（快照确认→转产品→预立项审批 vs 预立项审批→建产品→SPU审）？开发任务与"项目"实体的挂载关系？ | 02 §2.3 |
| Q9 | **target_margin_check 的输入来源（S1 实施中新发现）**：互斥录入下正算路径无目标利润率，below/meets/above 校验何时触发（反推解封后计算？还是允许目标利润率与售价同填仅作校验目标）？ | 03 §4.1/§4.2；S1 tests |

## 6. 本轮禁止事项遵守声明（S0/S1/S2）

未新建登录/审批系统（owner 隔离仅为演示级请求头命名空间，非身份体系）；未引入多 Agent/自创评分；未以旧项目公式替代公司口径（真实入口 blocked，反推公式未实现，未自行推导未确认的采购价反算公式）；mock/test_only/样例参数全程显式标注且 real 门禁强制拒绝，未混入任何真实决策；"页面可见/接口契约已知/接口已对接"三态严格区分（01 §2.8），本轮对公司系统零调用（③未达成）；未执行数据库迁移/队列/部署平台升级（内存验证，保证范围显式声明）；未调用任何付费 1688 API、未读取或复制生产凭证、未调用生产审批或待开发产品写入接口、未生成真实产品、未提交正式审批；**未修改 src/core/agent.py**（本轮改动全部位于 src/modules/preinitiation/、tests/ 新增文件与文档，未触碰既有源码）；未为凑历史测试数量删改测试或放宽断言（既有 596 项测试原样通过，9 个导入错误原样保留为阻塞证据）；未自动 commit 或 push。
