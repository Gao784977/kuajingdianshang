# 01 · 事实核查与复用取舍（Evidence & Reuse）

> 项目：简化整合预立项/立项流程（一期）
> 核查日期：2026-10-15（S0 评审整改同日修订；S2 同日二次修订）
> 核查环境：Python 3.14.8 / 沙箱可写克隆（S2 起仓库含本轮新增模块）
> 结论标记：**[已核查实现]** 代码可读且测试可运行｜**[文档描述未验证]** 仅文档声称｜**[仅原型]** HTML demo/产品方案｜**[本次建议新增]**
> **S0 修订要点**：OP 前端公式二次取证（`nl()` 全分支提取），更正两处误记，新发现 D5 代数矛盾（Amazon SC 反推公式与其正算不一致）——详见 03 §1 与 05 文档。
> **S2 修订要点**（本轮）：① §2.1 更新 backend/storage 缺失的**穷尽式根因核查结论**（非 .gitignore 误伤，系从未提交，恢复途径穷尽后记录阻塞）；② §2.8 新增**对接状态三态区分**（页面可见 ≠ 接口契约已知 ≠ 接口已对接），明确审批中心仅页面级观察；③ 测试现状更新为 S2 后实测（704/9）。
> **S3 验收修正（2026-10-15 验收轮）**：§2.1 此前"仅 1 个提交/从未提交/虚假声明/唯一找回途径"等结论**证据不足，已修正**——仓库实为**浅克隆**（`git rev-parse --is-shallow-repository` = true），`git fetch --unshallow` 后完整历史为 **2 个提交**；storage 缺失的准确表述改为三级区分（当前提交缺少/当前可访问历史未找到/MANIFEST 与当前内容不一致），详见 §2.1 S3 修正表。

---

## 1. 材料清单与访问状态

| 材料 | 位置 | 状态 |
|---|---|---|
| 01·OP利润计算器公式档案 | /workspace/01-OP利润计算器公式.md | 可读，本文引用为财务基线（文案级） |
| 02·参考项目对比分析 | /workspace/02-参考项目对比分析.md | 可读；**其中"699 测试通过"系 README 历史声称，本次实测已修正（见 §2.1）** |
| OP 前端原始 JS | /workspace/opfe/（app.js / chunk-libs.js） | 可读；2026-10-15 两次取证（初次公式文案 + S0 `nl()` 全分支复核） |
| 旧项目 kuajingdianshang | /workspace/repo-kuajingdianshang/（S3 验收轮 unshallow 后：完整历史 2 个提交，HEAD 6d02e36） | 已克隆可读（初始为浅克隆，S3 已获取完整历史） |
| 1688 溯源原型 + 一期方案 | florahhying-droid.github.io/product-prototypes/1688-sourcing-demo/ | 可访问（4 页：接口说明/一期方案/3 版原型） |
| 无产品导入模板 | /workspace/.uploads/…无产品导入试.xlsx（22 字段 + 全品类 12086 行） | 可读 |
| 品牌中心（brand.starmerx.com） | 浏览器实测（SSO 会话） | 只读核查通过 |
| OP 系统（op.starmerx.com） | 浏览器实测 + JS 逆向 | 只读核查通过 |

无未访问的已知材料。**无运行权限的生产接口**：OP 后端 API、品牌中心后端 API、1688 OpenAPI（寻源通）均未调用，仅页面/前端代码级核查。

---

## 2. 关键事实（附证据）

### 2.1 旧项目测试现状 — [已核查实现，但非文档声称的状态]

- **S0 实测基线**：`python3 -m unittest discover` → **Ran 605 tests, FAILED (errors=9)**。605 为可加载测试数，9 个为模块导入错误，**实际通过 596**。
- 9 个失败模块及原因：`test_web_api / test_phase2_checkpoint / test_manual_inputs_empty / test_task_cancellation / test_cross_user_isolation / test_download_security / test_security / test_template_integration / test_web_storage` 全部因 `ModuleNotFoundError: No module named 'backend.storage'`（auth_service.py:33 等）。
- **根因**：仓库中 `backend/storage/` 目录（database.py / job_store.py / local_storage.py / base.py）**不存在**——handoff/ARCHITECTURE.md 与 PROJECT_STATUS.md 大量引用这些文件，但当前可访问历史（S3 unshallow 后 2 个提交）中均无该目录（S0 时误记为"单 commit 快照"，系浅克隆假象，见下方 S3 修正）。
- 结论：**v3.2 Web 后端（登录/隔离/任务/门禁/checkpoint 的运行层）在当前仓库不可运行**；其 API 层代码（backend/api/、backend/services/workflow_runner.py）存在且可读。handoff 文档中"699/699 通过"为作者本地历史状态（tests/ 共定义 699 个 test 函数，grep 计数），**不得作为当前结果引用**。

**S2 根因穷尽式核查结论（2026-10-15，本轮新增；S3 验收轮已修正其中受浅克隆影响的表述）**：

| 核查途径 | 命令/位置 | 结果 |
|---|---|---|
| .gitignore 规则 | `git check-ignore -v --no-index backend/storage/base.py` | **返回码 1（不被忽略）**；`storage/*` 规则仅匹配仓库根级 `storage/`，**不是丢失原因** |
| Git 跟踪清单 | `git ls-files backend/` | backend/storage/ 下无任何文件被跟踪 |
| 交接包声明 | handoff/MANIFEST.json | 声明 4 个 storage 文件 status=tracked 并给出 sha256/size，**与当前仓库内容不一致**（S3 交叉验证：MANIFEST 声明的其余 46 个文件全部存在于仓库、其中 31 个源码文件 sha256 完全匹配、15 个文档类内容有漂移——**唯一缺失的即 4 个 storage 文件**） |
| Git 历史（S3 修正） | 初始为**浅克隆**（`git rev-parse --is-shallow-repository` = true，仅见 1 个提交）；`git fetch --unshallow` 后完整历史为 **2 个提交**（baa890c → 6d02e36），`git log --all -- backend/storage/` 为空，两提交树中均无该目录 | **当前可访问历史（全部 2 个提交）中未找到该目录** |
| 远程引用（S3 修正） | `git ls-remote --heads origin`：远程仅 main 一个分支且与本地 HEAD 相同；`git tag` / `git stash list` 为空 | 远程可访问范围内同样缺失 |
| 本地其他工作区 | /workspace/preinitiation/、沙箱全盘检索 | 无 backend/storage 副本 |
| GitHub 代码搜索 | 仓库可见范围内搜索 `backend.storage` / `job_store` | 无结果 |

**S3 验收修正的三级区分（准确表述，取代 S2 的"从未提交/虚假声明/唯一找回途径"等过度结论）**：
1. **当前提交缺少文件**：是——HEAD 6d02e36 树中无 backend/storage/ 4 个文件；
2. **当前可访问历史未找到文件**：是——unshallow 后完整历史（2 个提交）、远程唯一分支、无标签/stash、对象库全文检索均无；**无法排除**原仓库维护者本地存在未推送提交或未提交工作区副本（该范围超出本沙箱可访问能力）；
3. **MANIFEST 与当前内容不一致**：是——MANIFEST 生成时点所依据的工作区状态包含这 4 个文件（附 sha256），与推送至远程的历史不一致；sha256 可作为找回后的完整性校验依据。

**处置（按授权边界）**：在当前可访问范围内未找到源码，**记录阻塞，不编造替代存储层**——9 个导入错误保持原样作为阻塞证据；依赖该模块的功能（旧项目 v3.2 Web 运行层）本轮不实现。仓库其余 596 个原有测试全部通过，本轮新增预立项模块测试全部通过（S2 时 99 项，**S3 验收轮增至 108 项**）；**S3 验收轮全量实测：Ran 713 tests, FAILED (errors=9)**——9 个错误仍全部且仅为 backend.storage 导入错误，无断言失败（命令证据与干净副本验证见 07 交付报告，验收过程见 08 验收报告）。

**VCS 守护（防复发）**：本轮在仓库内新增 `tests/test_preinitiation_vcs_guard.py`——守护模块源码不被忽略规则覆盖、模块目录不含运行期产物、backend/storage 路径不被未来规则误伤（找回源码后可直接 `git add`）。

### 2.2 两阶段确认门禁 — [已核查实现（API 层代码），运行层缺失]

- 候选确认/拒绝/列表：`backend/api/candidates.py` L19-38（list + check_ownership 403）、L41-57（confirm→'confirmed'）、L60-77（reject→'rejected'）。状态枚举仅 pending_review/confirmed/rejected。
- Phase 2 门禁：`backend/api/manual_inputs.py` L59-80 `continue_development`——无 confirmed 候选时返回 `waiting_for_confirmation`，不启动 Phase 2。
- 状态机约束（rejected 不可直接 confirmed，需 reset）：文档描述于 handoff/WORKFLOW_STATUS.md §7，**代码中未见 reset 端点** → 该约束为 [文档描述未验证]。

### 2.3 checkpoint — [已核查实现（保存/读取），**无失效规则**]

- 保存：`workflow_runner.py` L148（Phase 1 完成）→ L271 `_save_checkpoint`（写 SQLite workflow_checkpoints 表）。
- 读取：`_run_phase_2` L193-199（按 phase_1_job_id 查 checkpoint，缺失即 RuntimeError）。
- **核查结论（用户关注点）**：全仓库 grep `invalidat|stale|过期|失效` 仅命中 Session/邀请码过期与测试注释——**checkpoint 无输入哈希、无输入版本比对、无过期标记**。Phase 2 接收全新传入的 excel_files/user_input（L207-217），若与 Phase 1 输入不同，系统不感知、不复算、不警告。**失效规则属 [本次建议新增]**。

### 2.4 字段来源/置信度/缺失值 — [已核查实现]

- 来源标注：`src/modules/amazon/importers/normalized_models.py` L32-39 `ALLOWED_SOURCE_TYPES = (imported_excel, user_input, fetched_url, calculated, agent_inference, mock_data)`；SourceInfo 携带 file/sheet/row/source_hash；金额一律 Decimal，序列化为 str 保精度。
- 缺失值：`manual_inputs.py` L34-39 空值保留为 `""` 不替换 0；`normalized_models._to_decimal` 空白返回 None。
- mock 使用范围：`src/modules/amazon/mock_data.py`——仅在无用户 CSV 时兜底填充 keyword/market/competitor/review，且 confidence 强制非 high（文档+测试声称，测试属 596 通过集，[已核查实现]）。

### 2.5 Excel 导入与真实数据路径 — [已核查实现]

- `src/modules/amazon/importers/` 8 个 loader + workbook_detector + column_aliases + normalizer（ASIN 去重、搜索曝光保留）。对应测试属通过集。
- 真实数据路径仅两条：用户 Excel（卖家精灵/Brand Analytics）与用户公开 URL 抓取（url_sources/，默认关闭）。**无任何电商平台 API 真实数据源**。

### 2.6 旧项目利润计算 — [已核查实现，但口径不可用于本项目]

- 入口：`profit_agent.calculate_amazon_profit(profit_input, scenario_multipliers, scenario_name)`；版本 `amazon_calculation_v1`（L52）；13 成本字段 + 9 情景乘数；Decimal `_q2/_q4` ROUND_HALF_UP（L56-67）；亏损时 ROI=None。
- **公式为公司口径之外的自创简化式**。按禁止事项：**不采用该公式替代公司口径**，仅借鉴其"版本号 + Decimal 精度 + 情景乘数 + 不可计算返回 None"的工程结构（该结构已在 S1 中借鉴实现）。

### 2.7 1688 能力 — [仅原型]

- 旧项目中 1688 相关仅 `url_sources/ali1688_parser.py`（`parse_ali1688_product_page`，L88，HTML 解析器）——**无候选/批次/offer/SKU/转待开发产品的任何实现**。
- 候选→批次→选择→生成流程全部来自 1688 溯源一期方案（sourcing-design-v1.html）：4 个 OpenAPI 编排（§4.1）、价格判断（§3.2）、生命周期矩阵（§7）、权限表（§8）、数据字段建议（§A.3）。**全部为 [仅原型]，接口可用性、额度、凭证、字段实际返回均未验证。**

### 2.8 公司现有系统实体 — [已核查实现（页面级），接口级未验证]

**对接状态三态区分（S2 修订，本报告全篇统一口径）**：

| 状态 | 定义 | 本项目当前证据 |
|---|---|---|
| ① 页面可见 | 浏览器登录后能观察到页面/Tab/表头/按钮 | 品牌中心 4 页面、审批中心 9 类待审 Tab、OP 计算器页面——**已达到** |
| ② 接口契约已知 | 拿到接口文档/字段定义/权限矩阵（纸面或只读导出） | **未达到**（B4 未解；无任何后端 API 文档） |
| ③ 接口已对接 | 本系统实际调用对方接口并验证返回 | **未达到**（本轮零调用；真实测算/审批/写入均 blocked） |

**三态不可互相冒充**：①→② 需要研发提供文档；②→③ 需要联调验证。本项目所有"复用现有审批/待开发产品"的表述均处于①；凡文档写"待对接"处即②未达成。

- **品牌中心**（浏览器实测 2026-10-15，**全部仅为①页面可见级**）：
  - 预立项阶段（/#/project-management/establishment-stage）：表头 = 项目编号/名称/类型/开发/项目部门/项目运营/项目组/发起时间/品牌/品线/状态/操作；操作 = 详情/编辑/撤回 + 创建新项目；**观察到状态值：预立项待审核、预立项待调研**。
  - 立项阶段（/#/project-management/commodity-creation）：表头同上，列表为空，状态枚举未能观察。
  - 审批管理（/#/project-management/approve-management）：**9 类待审 Tab：预立项待审/立项待审/SPU待审/offer修改待审/设计任务待审/推广需求待审/翻译需求待审/备货待审/正式供应商待审** → 现有审批体系存在且分类明确，本项目**不新建审批**。**本报告对该审批中心的核查目前仅完成页面级观察（三态之①）：接口契约（②）与接口权限（③）均待核实（B4）；Tab 存在仅证明入口存在，不能证明其与本项目节点的先后/父子关系一致（未决冲突见 02 §2.3，Q8）。**
  - 项目时效管理、立项管理报表（跨阶段进展视图）存在。
  - 列表页未见"参考ASIN/待开发产品"独立字段（在详情/其他模块内，未进入编辑）。
- **OP 利润计算器**（浏览器实测 + JS 逆向）：字段、测算方式、9 市场、结果表 24 列、公司利润率 10%/15% 阈值筛选——页面级 [已核查实现]；**计算参数（佣金率表、仓租、尾程单价、汇率）由后端 API 返回，未抓取** → [文档描述未验证]。**OP 公式存在已知冲突（D1/D2/D5，见 §2.9 与 03 §8）且缺少标准对账样例（B3 无供给）——正式计算在本项目中尚未通过验收，真实测算入口一律 blocked 返回原因，不输出数值。**
- 品牌中心/OP 的后端 API 文档、权限矩阵文档：**未获得**（阻塞项 B4）。

### 2.9 OP 公式二次取证与代数一致性复核 — [已核查实现（文案级），S0 新增]

- 2026-10-15 对 chunk-libs.js `nl(e,t)` 公式展示函数做全分支逐字提取（偏移 ~3650300–3651000），产出六分支公式全表（见 03 §1.2）。
- **更正上版两处误记**：①Amazon SC 美区成本清单含「所得税」「汇率调节因子」（上版误记为"美区不含所得税"）；②Overstock/Wayfair 家族正算分母为**售价**。
- **新发现 D5**：Amazon SC 美区/日本分支的展示反推公式与其正算公式**代数不一致**（活动营销费重复计入反推分子）；同函数内欧区/Temu 分支却自洽——三种反推结构互不兼容，无法判定 OP 后端真实计算口径。**处置：反推类公式全部 blocked，待 Q1 扩展裁决 + B3 样例（详见 03 §1.3/§8）。**
- **验证分级**：当前所有 OP 公式均为 (a) 原始文案级；不存在 (c) 已验证级公式——**OP 计算器的真实计算代码（后端）未获取，前端文案 ≠ 计算实现**。

---

## 3. 能力矩阵与复用取舍

| # | 能力 | 核查状态 | 取舍 | 理由 / 依赖 / 工作量 |
|---|---|---|---|---|
| R1 | 两阶段确认门禁（候选确认→下游） | API 代码已核查；运行层(storage)缺失 | **提取改造** | 状态机思想直接映射快照事件模型；需挂接品牌中心登录与实体，不搬 SQLite 运行层。工作量 M |
| R2 | checkpoint 复用 | 保存/读取已核查；**失效规则不存在** | **只借鉴设计** | 保留"阶段产物供下阶段复用"思想；失效规则为本次新增（S1 已实现版本比对失效）。工作量 S |
| R3 | 字段来源/置信度/空值保留 | 已核查（normalized_models / manual_inputs） | **提取改造** | 来源标注与"空值不填0"规则已沿用于 S1；Decimal+str 序列化沿用。工作量 S |
| R4 | Excel 导入管道（8 loader） | 已核查 | **一期不采用**（列入后续） | 一期最小输入为手工表单+候选，不依赖卖家精灵 Excel；保留代码备查。理由：范围收敛 |
| R5 | 旧利润公式 | 已核查（amazon_calculation_v1） | **不采用** | 违反公司口径；仅借鉴版本号/精度/不可计算结构（S1 已借鉴）。 |
| R6 | OP 口径计算内核 | 文案已二次取证（03 §1.2）；**公式分支 blocked（D1/D2/D5/Q1）**；参数未获取（B1） | **本次建议新增（blocked 状态实现）** | 真实计算入口实现为 blocked 返回原因（S1 实现，S2 已随模块移植入仓库 src/modules/preinitiation/）；正算分支待 Q1 裁决+B1+B3 对账后解封。工作量 L（解封后） |
| R7 | 0%毛利推算采购价 | 1688 方案 §3.2 描述；OP 侧无显式公式 | **blocked（不实现）** | 定义（Q3）与反推类公式裁决（D5）均未决；一期溯源价格上限仅用目标采购价。 |
| R8 | 1688 溯源管道（批次/候选/offer/SKU） | 仅原型 | **只借鉴设计 + 本次建议新增** | 借鉴：批次不可变、四元组防重、准入/限量规则；实现依赖 1688 API 凭证（B2）。工作量 L（接口阻塞时先手工候选降级路径，S1 已实现手工候选） |
| R9 | 品牌中心身份/权限/审批 | 页面级已核查；接口级未验证 | **直接复用（待对接确认）** | 复用现有 SSO、审批中心；对接方式待研发确认（B4）。工作量：适配层 M |
| R10 | 品牌中心开发任务/待开发产品实体 | 页面级已核查；字段级未验证；**与"项目"实体的挂载关系未确认（Q8）** | **直接复用（待对接确认）** | 1688 方案 §A.3 声称复用现有主键/状态字段，[文档描述未验证]。阻塞 B4/Q8 |
| R11 | CancellationToken 任务取消 | 代码已核查（workflow_runner L50-55） | **只借鉴设计** | 一期同步短任务为主，暂不需要 |
| R12 | 旧项目 v3.2 Web 骨架 | 运行层缺失不可运行 | **不采用** | 禁止新建独立登录系统；storage 层未提交，恢复成本>重写成本 |

---

## 4. 未知项与阻塞项（移交 04/05 文档跟踪）

| ID | 阻塞/未知 | 影响 | 所需材料/动作 |
|---|---|---|---|
| B1 | OP 计算参数表（品类佣金率、仓租基数、尾程分区单价、操作费/入库费、提现费、所得税适用性、汇率来源、"其他杂费"兜底） | 真实测算无法产出数值 | 业务/OP 研发提供参数表或只读接口 |
| B2 | 1688 OpenAPI 凭证、测试环境、额度、返回字段样例 | API 溯源无法实施 | 寻源通/AC 研发对接 |
| B3 | 公司标准测算对账样例（≥1 组完整输入+输出） | **唯一能产生 (c) 级验证公式的途径** | 业务提供 |
| B4 | 品牌中心接口文档/权限矩阵/待开发产品创建接口 | R9/R10 对接方式未定 | 研发提供文档或联调窗口 |
| B5 | backend/storage 缺失 | 仅影响旧项目运行层（已决策不复活） | **S3 验收修正（§2.1）：非忽略规则所致；当前提交、unshallow 后完整历史（2 提交）、远程、标签/stash、本地副本、代码搜索均未找到——保持阻塞，不编造替代**；无法排除维护者本地未推送提交/工作区副本（超出本沙箱可访问范围）；MANIFEST 附 sha256 可作找回后校验；vcs_guard 测试已守护路径不被未来忽略规则误伤 |
| B6 | "0%毛利推算采购价"公司定义 | R7 口径 | 业务确认（Q3） |
| B7 | 立项阶段状态枚举（页面为空未观察到） | 状态契约完整性 | 业务补充或提供文档 |
| B8 | OP 公式歧义 D1–D5（**含 S0 新发现 D5 代数矛盾**，见 03 §8） | 正算分支 blocked（D1/D2）；反推类公式全部 blocked（D5） | 业务确认（Q1 扩展/Q2/Q3）+ B3 对账 |

---

## 5. 引用证据索引

- 代码：`backend/api/candidates.py`、`backend/api/manual_inputs.py`、`backend/services/workflow_runner.py`、`src/modules/amazon/profit_agent.py`、`src/modules/amazon/importers/normalized_models.py`、`src/modules/amazon/mock_data.py`、`src/modules/amazon/url_sources/ali1688_parser.py`（均在 /workspace/repo-kuajingdianshang/）
- 测试：当前运行 605 loaded / 596 pass / 9 import errors（2026-10-15 实测）；失败清单见 §2.1
- 文档：handoff/WORKFLOW_STATUS.md §7/§12/§13、handoff/PROJECT_STATUS.md §25-30、README「V3.2 当前状态」
- 前端逆向（初次，2026-10-15 上午）：/workspace/opfe/chunk-libs.js 模块 "1c39"（SmProfitPlugin），公式文案偏移 ~3650000、~3667000-3670500
- 前端逆向（S0 二次取证，2026-10-15）：同文件 `nl(e,t)` 公式分支函数全量提取（偏移 ~3650300–3651000），产出 03 §1.2 六分支公式全表；更正"美区不含所得税"误记；发现 D5
- 浏览器实测记录：品牌中心 4 页面（establishment-stage / commodity-creation / approve-management / prescription-management）、OP price-calculator（2026-10-15）
- 原型：sourcing-design-v1.html §3.2/§4/§7/§8/§A.3；prototype-v1-optimized.html（任务详情四模块）
