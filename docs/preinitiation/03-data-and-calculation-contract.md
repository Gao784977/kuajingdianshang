# 03 · 数据契约与计算口径（Data & Calculation Contract）

> 前置：01-evidence-and-reuse.md、02-mvp-scope-and-flow.md
> 财务基线：01-OP利润计算器公式.md + OP 前端 JS 复核（2026-10-15 二次取证，见 §1.1）
> 冲突处理原则：**列出差异交业务确认，不自行选择或补造公式。数学自洽/内部往返测试 ≠ OP 口径已验证。**
> **S2 修订（2026-10-15 本轮）**：① §1.1 明确"OP 公式存在冲突且缺少标准对账样例，正式计算尚未通过验收"；② §4.2/§4.6 契约新增 `calc_version`（计算结果版本）与 `snapshot_seq`（快照序列版本）及快照幂等规则（与实现同步）；③ §9 接口缺口表引入对接三态（页面可见/接口契约已知/接口已对接，定义见 01 §2.8）。

## 0. S0 修订说明（2026-10-15 评审整改）

本版按评审意见重写：公式按验证分级（§1.1–1.3）；新增成本依赖表（§1.4）；输入集按计算类型拆分（§2）；采购价语义增加首轮估算价（§3）；target_qty 语义修正（§2.2）；新增 demo/real 隔离契约（§6）；快照改为不可变内容+可追加事件（§4.6）；存储保证边界（§7）；手工候选字段补全（§4.5）。修订溯源见 05 文档。

---

## 1. 财务口径

### 1.1 公式验证分级（关键修订）

| 级别 | 定义 | 当前状态 |
|---|---|---|
| **(a) 原始文案** | OP 前端 JS `nl(e,t)` 函数逐字提取的公式展示文案（chunk-libs.js 偏移 ~3650300–3651000，2026-10-15 二次取证） | 已取证，见 §1.2 |
| **(b) 推导表达式** | 由 (a) 代数变形得到（如由正算解出反推售价） | 仅代数推导，**不代表 OP 实际计算行为** |
| **(c) 已验证公式** | 通过 OP 标准样例（B3）逐项对账的公式 | **当前不存在任何 (c) 级公式** |

**重要更正（相对上一版）**：二次取证发现上一版两处错误——①Amazon SC 美区成本清单**含「所得税」与「汇率调节因子」**（此前误记为"美区不含所得税"）；②Overstock/Wayfair 家族正算分母为**售价**（非"售价−活动营销费"），该家族公式代数自洽。

**验收状态声明（S2 明确）**：OP 公式存在已知冲突（D1/D2/D5，§8）且缺少标准对账样例（B3 无供给）——**正式计算在本项目中尚未通过验收**。因此：真实测算入口实现为 blocked 返回原因不输出数值；任何分支在获得 (c) 级验证前不得标记 verified；本项目产生的任何数值均为 demo 域（test_only/样例参数），不得用于正式业务确认、审批或产品转换（§6）。

### 1.2 (a) 级原始文案：OP `nl()` 公式分支全表

记号：P=售价，A=活动营销费，C=Σ成本项（各分支清单不同），J=消费税，V=增值税，m=利润率。

| 平台家族 | 市场 | 正算（文案） | 反推（文案） | 代数一致性 |
|---|---|---|---|---|
| Overstock/Wayfair/VC | 美区等(f)/欧区等(h) | m=(P−A−C)/P | P=(A+C)/(1−m) | ✅ 一致 |
| Overstock/Wayfair/VC | 日本(d) | m=(P−A−C−J)/P | P=(A+C+J)/(1−m) | ✅ 一致 |
| Temu/Shopify/AliExpress/Fruugo/Shein2 | — | m=(P−A−C)/(P−A) | P=C/(1−m)+A | ✅ 一致 |
| **其余平台（含 Amazon SC、ebay）** | **美区等(f)** | **m=(P−A−C)/(P−A)** | **P=(A+C)/(1−m)+A** | ❌ **不一致（D5）** |
| 其余平台（含 Amazon SC） | 日本(d) | m=(P−A−C−J)/(P−A) | P=(A+C+J)/(1−m)+A | ❌ 不一致（D5 同型） |
| 其余平台（含 Amazon SC） | 欧区等(h) | m=(P−A−C−V)/(P−A−V) | P=C/(1−m)+A+V | ✅ 一致 |

Amazon SC 美区 C 的文案清单：`产品成本+立项人奖励+尾程+操作费+入库费+平台佣金+仓租+广告费+线下推广费+退货费+提现费+PayPal费+其他杂费+所得税+汇率调节因子`（活动营销费单列于 A）。

### 1.3 **D5（新发现的代数矛盾，S0 核心产出）**

对 Amazon SC 美区正算 m=(P−A−C)/(P−A) 求解 P：
`(P−A)(1−m)=C → P = C/(1−m) + A`（与 Temu 家族反推形态相同）。
而文案反推为 `P=(A+C)/(1−m)+A`，比正确解**多出 A/(1−m) 项（活动营销费被重复计入）**。矛盾仅在 A=0 或 m→1 时消失。
同一函数内欧区分支反推却与正算一致、Temu 分支也一致——**三种反推结构互不兼容，说明文案存在错误或正算/反推口径不对称，无法判断 OP 后端真实计算采用哪个**。
**处置：反推售价（Amazon SC 全市场）标记 blocked，不实现为正式能力，直至业务给出 (c) 级确认（Q1 扩展）。**

### 1.4 成本依赖表（Amazon SC 美区，公司口径候选清单）

| 成本项 | 币种/单位 | 依赖售价 | 依赖采购量 | 依赖重量/尺寸 | 依赖品类 | 费率来源 | 生效时间 | 缺失处理 |
|---|---|---|---|---|---|---|---|---|
| 采购价（产品成本组成） | CNY/件，不含税 | 否 | 是（SKU阶梯价） | 否 | 否 | 1688 报价（API/手工） | 报价获取时间 | 缺→not_computable(missing_purchase_price) |
| 头程（产品成本组成） | CNY/件 | 否 | 否 | 是（分摊） | 否 | OP 参数表 **B1** | B1 | **缺→not_computable(missing_first_leg)，禁止按 0** |
| 设计费（产品成本组成） | CNY/件 | 否 | 否 | 否 | 否 | 业务输入 | 即时 | 缺→not_computable(missing_design_fee)，禁止按 0 |
| 活动营销费 A | USD/件 | 是（占比×P） | 否 | 否 | 否 | 用户输入占比 | 即时 | 缺→not_computable(missing_promotion_ratio) |
| 平台佣金 | USD/件 | 是（率×P） | 否 | 否 | 是（品类佣金率） | OP 品类佣金表 **B1** | B1 | missing_referral_rate |
| 仓租 | USD/件 | 是？（"固定3%"基数未确认） | 否 | 否 | 否 | OP **B1** | B1 | missing_storage_rate |
| 尾程 | USD/件 | 否 | 否 | 是（体积重） | 否 | OP 分区单价表 **B1** | B1 | missing_last_mile |
| 操作费/入库费 | USD/件 | 否 | 否 | 部分相关 | 否 | OP **B1** | B1 | missing_operation/inbound |
| 广告费/退货费 | USD/件 | 可能（占比） | 否 | 否 | 否 | 用户输入/OP 默认 | 待确认 | missing（不默认 0） |
| 提现费/PayPal费 | USD/件 | 是 | 否 | 否 | 否 | OP/平台规则 **B1** | B1 | missing |
| 所得税 | USD/件 | ？ | ？ | ？ | ？ | OP——**美区 SC 是否适用待确认（Q1）** | — | missing |
| 汇率调节因子 | CNY/件 | 否（依赖星商成本CNY+现汇率） | 否 | 否 | 否 | 公式见 01 档案 D | 汇率时点 | missing_fx |
| 其他杂费 | USD/件 | 否 | 否 | 否 | 否 | 用户输入 | 即时 | 未填→not_computable（是否允许 OP 默认 0 待 Q1 附带确认） |
| 立项人奖励 | CNY/件 | 否 | 否 | 否 | 否 | 规则 4 条（01 档案 D） | 立项时 | **公司口径不含**（预立项阶段不计算个人口径，Q2） |

### 1.5 总则

| 项 | 约定 |
|---|---|
| 售价币种/口径 | USD，前台售价（美区 SC 无 VAT 分支） |
| 采购价币种/口径 | CNY，不含税（对齐模板「不含税采购价(￥)」）；候选报价需记录 `tax_inclusive` 口径，未知即标未知 |
| 汇率方向 | `usd_to_cny`：1 USD = X CNY；一期手工输入并记录 `fx_fetched_at`（来源待 Q7） |
| 精度/舍入 | Decimal 全程；金额 2 位、比率 4 位，ROUND_HALF_UP |
| 百分比 | 存储 0–1，展示 ×100 保留 2 位 |
| 不可计算 | 关键参数缺失/非法 → 状态+原因码，**任何字段不默认填 0** |
| 负利润率 | **合法结果**（公司利润率可为负），与目标利润率校验（below/meets/above）分离 |
| 公式版本 | `op_profit_formula_v1`（标识保留）；分支 `branch_us_amazon_sc` 当前 **blocked**（D1/D2/D5/Q1 未决），真实计算入口返回 blocked 原因（S1 已实现该行为） |

---

## 2. 输入集

### 2.1 前端最小填写 vs 计算所需完整字段（分离，修订）

**前端最小填写**（让流程可开始）：参考ASIN、市场、售价 或 目标利润率（二选一）、汇率、目标采购量（可空=未知）。
**注意：二选一规则仅是录入互斥约束，不构成"输入完整"的判据。** 计算完整性按下表逐项判定：

| 计算类型 | 所需输入（用户侧） | 所需参数（系统侧） | 当前状态 |
|---|---|---|---|
| 正算公司利润率 | selling_price、promotion_ratio、fx、采购价（首轮估算价或有效采购价） | §1.4 全部成本项费率 | 公式 **blocked（D1/D2/Q1）**；S1 仅 test_only 提供者 |
| 反推售价 | target_margin、promotion_ratio、fx、采购价 | 同上 | **blocked（D5 代数矛盾）**，不实现 |
| 反推采购价（0%毛利上限） | target_margin(=0)、selling_price、promotion_ratio、fx | 同上 + 头程/设计费是否计入的口径（Q3） | **blocked（Q3）**，不实现 |

### 2.2 target_qty 语义（修订）

- `target_qty: Optional[int]`，**None=未维护（未知）**；0 不承载任何语义，禁止用 0 同时表达未知和不限量。
- 采购量未知时：`qty_check = unknown`，**MOQ/阶梯价校验状态必须显示 unknown，不得标记 passed**。
- qty_check 枚举：`unknown | passed | violated | not_applicable`。
- "不限量"是溯源筛选行为（未维护目标量→不限起批量），与 qty_check 校验状态是两个概念。

### 2.3 首轮估算采购价 vs 有效采购价（修订，并入 §3 语义表）

---

## 3. 采购价语义（六种，严格区分）

| # | 名称 | 字段 | 定义 | 来源 | 用途 |
|---|---|---|---|---|---|
| 1 | 目标采购价 | `target_purchase_price[min,max]` | 人工维护区间 | manual | 溯源价格上限优先项 |
| 2 | 0%毛利推算采购价 | `zero_margin_price` | 公司利润率=0 反解 | derived | **blocked（Q3）**，一期不产出 |
| 3 | 目标利润率对应采购价 | `target_margin_price` | 目标利润率下反解 | derived | 二期，blocked |
| 4 | **首轮估算采购价** | `estimated_purchase_price_cny` | 开发人手工填写的预估采购价 | manual | **首轮正算利润率的采购价输入**（选 SKU 前） |
| 5 | 搜索报价 | `offer_price` | 1688 offer 级摘要价 | 1688_api/manual | **仅展示**，不得自动充当有效采购价 |
| 6 | **有效采购价** | `effective_purchase_price_cny` | 所选 SKU 在对应采购量档位下的单价 | 1688_api/manual(SKU级) | 复算与快照**唯一**采用的采购价 |

规则：无 SKU 级价格 → 有效采购价为空并显示 `--`，复算返回 not_computable(missing_effective_price)；搜索报价永不自动升级为有效价。

---

## 4. 数据契约（实体与字段）

### 4.1 输入集 InputSet（任务×ASIN）
```
task_id, asin
input_version            # 计算相关字段任何修改 +1（触发失效）
meta_version             # 非计算字段（备注等）修改 +1（不触发失效）
market/platform          # 一期固定 US / amazon_sc
selling_price_usd | target_margin_pct   # 互斥（提供两者→invalid）
promotion_fee_ratio      # 0–1
fx_usd_to_cny, fx_fetched_at
target_purchase_price_min/max_cny       # 可空
target_qty               # Optional[int]，None=未知（§2.2）
estimated_purchase_price_cny            # 首轮估算采购价（可空）
note                     # meta 字段
updated_at, updated_by
```

### 4.2 测算结果 Calculation（不可变记录）
```
calc_id, task_id, asin
input_version_ref, params_version_ref
calc_version           # 计算结果版本：同一任务×ASIN 内每次计算递增（S2 新增，
                       # 区别于引用的输入/参数/候选版本——版本语义不混用）
formula_version, branch, verification     # verified|unverified|test_only
mode                                      # demo|real
calc_status            # input_incomplete | ok | not_computable | blocked
reason / missing[]     # 原因码/缺失清单（含成本参数缺失项）
company_margin         # Decimal，可为负（合法结果）
target_margin_check    # below|meets|above|None（与结果有效性分离）
purchase_price_ref{value, kind}           # kind: estimated|effective
sample_parameters      # bool
calculated_at
```

### 4.3 采购约束 PurchaseConstraint
```
constraint_id, task_id, asin, input_version_ref, params_version_ref
max_purchase_price_cny
price_basis            # target_price_upper（一期唯一可用）；zero_margin_price（blocked）
created_at
```

### 4.4 溯源批次 SourcingBatch（不可变）
```
sourcing_batch_id, task_id, asin
sourcing_status        # pending|running|succeeded_with_results|succeeded_zero|partial_failed|failed|not_auto_sourced
max_purchase_price_used, source_mode    # api|manual
sourcing_at, candidate_count, failure_detail_json
```

### 4.5 候选 Candidate（offer 级 + SKU 子级；手工来源字段补全）
```
sourcing_batch_id_ref, offer_id, seller_open_id, company_name
source_type            # image_search|keyword|both|manual
offer_price_cny        # 搜索/摘要报价——仅展示（§3#5）
quote_source           # 报价来源（链接/截图/口头等，manual 必填）
quoted_at              # 报价获取时间（必填）
currency, tax_inclusive  # 含税口径，未知=None（不得臆断）
moq                    # Optional[int]（未知=None）
skus[]: {sku_id, spec, sku_price_cny, price_basis, stock, fetched_at}
ladder_prices[]        # (qty_from, qty_to, price_cny)
candidate_status       # pending_selection|selected|discarded|converted
admission_status       # unknown|passed|failed —— manual 来源固定 unknown
                       # （手工录入 ≠ 已满足 1688 准入条件）
qty_check              # unknown|passed|violated|not_applicable（按当前 target_qty 动态计算）
internal_supplier_id
```

### 4.6 决策快照 DecisionSnapshot（**内容不可变 + 事件仅追加**，修订）
```
# —— 不可变内容 SnapshotContent ——
snapshot_id, task_id, asin
input_version_ref, params_version_ref, formula_version, verification
sourcing_batch_id_ref, offer_id, sku_id
effective_purchase_price_cny, price_basis, qty_check
calc_id_ref, company_margin_recalced, breakdown
snapshot_seq           # 快照序列版本：同一任务×ASIN 内每创建一个新快照递增
                       # （S2 新增；与 calc_version 语义不同——一次计算对应至多一个快照）
mode                   # demo|real
sample_parameters
created_at, created_by

# —— 可追加事件 SnapshotEvent（仅 append，不改内容）——
event_id, snapshot_id
kind                   # demo_confirmed | real_confirmed | rejected
actor, at, note
```
- 快照**状态**由事件序列派生：`pending_confirm → demo_confirmed(模拟确认) | real_confirmed | rejected`；`demo_confirmed` 与 `real_confirmed` 是**不同状态**，模拟确认永不升级为正式确认。
- **is_current（是否代表当前版本）**为派生属性：`input_version_ref/params_version_ref 与当前一致`；输入变更只使旧快照"不再代表当前版本"（派生标志），**不改写其内容与事件历史**。
- **快照幂等（S2 新增）**：对同一计算结果（calc_id）重复请求创建快照，返回既有快照，不重复创建、不重复递增 snapshot_seq。
- 新输入 → 新测算 → 新快照；历史快照（含已确认/已拒绝）永久保留可追溯；审批引用提交时的 snapshot_id。

### 4.7 待开发产品关系（防重复四元组）
```
pending_product_id, task_id, asin, offer_id, sku_id
snapshot_id_ref, sourcing_batch_id_ref, created_by, created_at
```
**保证边界（修订）**：四元组防重复在 S1 为**服务层+进程内检查**（内存实现，见 §7）；"生产级数据库唯一约束"须待存储方案批准后实现，此前文档一律不声称"已实现唯一约束"。

### 4.8 来源枚举
`1688_api | op_system | brand_center | manual | derived`；关键数值字段携带 `source`、`fetched_at`（derived 附 formula_version 与 verification）。

---

## 5. 失效规则

| 变更项 | 测算 | 采购约束 | 溯源批次/候选 | 快照 |
|---|---|---|---|---|
| 售价/目标利润率/活动营销费占比/汇率/估算采购价 | stale（须重算） | stale | 标 constraint_outdated（提示，不自动重溯源） | is_current=False；正式确认被阻止 |
| 目标采购价/目标采购量 | price_basis=target 时 stale；qty_check 重算 | 视 basis | qty_check 重算 | qty_check 嵌入值不回写（内容不可变），确认门禁按最新动态值判定 |
| 成本参数版本变化（params_version+1） | 全部 stale | stale | 同第一行 | 同第一行 |
| 仅 meta 字段（备注等） | 不失效（meta_version+1） | 不失效 | 不失效 | 不失效 |

幂等与防重复（S3 验收修正表述）：确认接口幂等（重复确认不重复产生事件）；**快照创建按 calc_id 幂等（重复保存同一请求不重复创建快照）——注意这是"按 calc 幂等"，不是完整请求幂等**：幂等键为服务端派生的 calc_id（无客户端幂等键），快照内容由服务端状态唯一决定，重复请求携带不同 created_by 时首写胜出、返回原快照不改写内容；**若未来引入客户端幂等键，契约要求：相同键配不同内容必须显式冲突（错误返回），不得静默返回错误结果**（本轮未引入，NOT_IMPLEMENTED）；转待开发产品按四元组防重（保证边界见 §4.7）。并发：仓储层不保证并发安全（GUARANTEE），HTTP 服务层以工作区锁将同工作区请求串行化——并发保存同一请求实测仅产生一个快照（测试固化），属服务层实际行为而非仓储层承诺。

---

## 6. demo / real 隔离契约（新增）

| 机制 | 规则 |
|---|---|
| 模式标记 | calc/snapshot/导出均携带 `mode: demo\|real` 与 `verification` |
| test_only/样例参数 | 来源为 test_only 提供者或 `sample_parameters=true` 的结果，**只能进入 demo 流程**；真实确认门禁直接拒绝 |
| 模拟确认 | 事件 kind=`demo_confirmed`，展示文案必须为"**模拟确认**"；不产生真实产品、不提交正式审批 |
| 演示导出 | 顶部显著标识"演示数据——不可用于真实立项"+ 机器可读字段 `{"demo": true, "mode": "demo", "verification": "test_only"}` |
| 真实确认门禁（全部通过才可 real_confirmed） | ① 公式 verification=verified；② 参数完整且版本为当前版；③ 关键输入完整（calc_status=ok）；④ 有效采购价存在；⑤ qty_check=passed（或经确认的 not_applicable）；⑥ 结果未过期（is_current）；⑦ 快照未被拒绝/未重复确认 |
| 真实计算入口 | 公式未达 (c) 级验证时，真实入口返回 `blocked` + 原因（D1/D2/D5/Q1/Q3），不输出任何数值 |

---

## 7. 存储保证边界（修订）

| 阶段 | 实现 | 保证 | 不保证 |
|---|---|---|---|
| S1 本地验证（当前） | 进程内内存 Repository | 单进程内状态一致、快照内容不可变（frozen 结构+服务层约定）、四元组进程内防重 | **无持久化、无跨进程唯一性、无并发保障——不得用于生产或真实决策** |
| 持久化试点（未批准） | — | — | 需独立存储方案评审后方可实施 |
| 生产集成（未批准） | — | — | 生产级唯一约束/审计在此阶段实现 |

"不做数据库迁移"修订为**当前阶段限制**（内存验证够用）；后续如需生产存储，提交独立方案待批准，不在本方案内默认完成。

---

## 8. OP 公式歧义点全集（B8，业务裁决）

| # | 歧义 | 证据位置 | 待确认 |
|---|---|---|---|
| D1 | 公司利润率（`ql` 文案）与通用利润率（`nl` 展示）成本清单不一致：ql 含增值税/消费税、不含立项人奖励/汇率调节因子；美区分母 (P−A−V) 在无 VAT 时退化为 (P−A) | 01档案 B/C；JS `nl()` vs `ql` | Q1 |
| D2 | ql 清单含「消费税」不含「汇率调节因子」是否笔误；所得税在美区 SC 是否适用 | 同上 | Q1 |
| D3 | 0%毛利推算采购价是否计入头程/设计费 | 01档案 D | Q3 |
| D4 | 预立项阶段是否输出个人利润率（尚无立项人/库存归属） | 01档案 C | Q2 |
| **D5** | **Amazon SC 美区/日本反推公式与其正算代数不一致（活动营销费重复计入分子）；三种平台家族反推结构互不兼容** | JS `nl()` 偏移 ~3650365（§1.2/1.3） | **Q1（扩展）：以正算解出的 C/(1−m)+A 为准，还是文案 (A+C)/(1−m)+A 为准，或以后端实现为准（需 (c) 级样例）** |

---

## 9. 现有接口缺口（对接清单，非对接完成声明）

对接状态三态（定义见 01 §2.8）：**页面可见 ≠ 接口契约已知 ≠ 接口已对接**。下表现状均处于三态之①；②③未达成前，本清单是"缺口声明"而非"对接完成声明"。

| 需要 | 现状（三态定位） | 缺口动作 |
|---|---|---|
| OP 费率参数 | ①页面级可见（参数由后端返回，未获取） | 只读接口或参数表（B1）→ 达② |
| 1688 四接口 | ①都未达到（原型文档命名，未验证） | 凭证/测试环境/字段样例（B2）→ 达② |
| 品牌中心任务/待开发产品/审批 API | ①页面级存在（审批中心仅页面级观察，接口与权限待核实） | 接口文档/联调（B4）→ 达② |
| 汇率来源 | 未查明 | Q7 |
| 标准对账样例 | 无 | 业务提供 ≥1 组（B3）——**唯一能产生 (c) 级公式的途径** |

## 10. 对账测试要求

- 获 B3 样例后：同输入跑本实现，与 OP 计算器输出逐项比对（利润率+各成本项金额），通过后才可将分支从 blocked → verified。
- **无样例则永远不宣称"已对账 OP"**；S1 的 test_only 结果与"OP 口径已验证"无关（内部往返测试亦然）。
