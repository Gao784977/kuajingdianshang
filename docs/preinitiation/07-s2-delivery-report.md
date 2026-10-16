# 07 · S2 交付报告（仓库可复现性修复 + 预立项决策预览纵向切片）

> 本轮：2026-10-15（S2 实现）｜2026-10-16 **S3 验收轮更新**（§1.2/§1.3 结论修正、§2 干净副本复验、§4 清单与测试数更新、§5 表述修正；验收过程与新增验证详见 **[08-S3-acceptance-report.md](08-S3-acceptance-report.md)**）。授权范围：A. 核实并修复旧项目仓库的可复现性问题；B. 实现本地可运行的"预立项决策预览"最小纵向切片。
> **边界声明**：真实财务确认、生产审批、待开发产品写入均不在本轮授权内；本报告不声称已接入公司审批，不声称支持真实财务决策。未自动 commit / push。
> 工作区：/workspace/repo-kuajingdianshang（main，HEAD 6d02e36，与此前报告一致；本轮全部新增文件处于未跟踪状态，待用户审阅后自行提交）。

---

## 1. 仓库缺失问题的根因、修复文件和命令证据

### 1.1 现象

全量测试 9 个模块导入失败：`ModuleNotFoundError: No module named 'backend.storage'`（涉及 test_web_api / test_phase2_checkpoint / test_manual_inputs_empty / test_task_cancellation / test_cross_user_isolation / test_download_security / test_security / test_template_integration / test_web_storage）。handoff/MANIFEST.json 声明 backend/storage/ 下存在 database.py / job_store.py / local_storage.py / base.py 四个文件，实际不存在。

### 1.2 根因（穷尽式核查，全部为只读操作）

| # | 核查途径 | 命令/证据 | 结论 |
|---|---|---|---|
| 1 | 忽略规则 | `git check-ignore -v --no-index backend/storage/base.py` → 返回码 1（不被忽略） | **不是 .gitignore 误伤**：第 129 行 `storage/*` 含斜杠、锚定仓库根级，仅匹配根级 `storage/`，不匹配 `backend/storage/` |
| 2 | Git 跟踪清单 | `git ls-files backend/` | backend/storage/ 下零文件被跟踪 |
| 3 | 交接包声明 | handoff/MANIFEST.json | 声明 4 个文件 status=tracked 并附 sha256/size，**与当前仓库内容不一致**（验收轮交叉验证：其余 46 个声明文件全部存在、31 个源码 sha256 完全匹配——唯一缺失的即 4 个 storage 文件） |
| 4 | Git 历史 | **S3 验收修正**：初始为浅克隆（`--is-shallow-repository`=true，仅见 1 提交）；`git fetch --unshallow` 后完整历史 **2 个提交**（baa890c → 6d02e36），`git log --all -- backend/storage/` 为空 | **当前可访问历史中未找到该目录**；无法排除维护者本地未推送提交/工作区副本（超出沙箱可访问范围） |
| 5 | 远程 | `git ls-remote --heads origin`（https://github.com/Gao784977/kuajingdianshang.git） | 远程仅 main 一个分支、与本地 HEAD 相同；无 tag/stash |
| 6 | 本地其他副本 | /workspace/preinitiation/、沙箱全盘检索 | 无 backend/storage 副本 |
| 7 | 代码搜索 | GitHub 可见范围搜索 `backend.storage` / `job_store` | 无结果 |

**结论（S3 验收修正表述）**：三级区分——① 当前提交（HEAD 6d02e36）缺少这 4 个文件；② 当前可访问历史（unshallow 后全部 2 个提交、远程唯一分支、无标签/stash）未找到；③ MANIFEST 声明与当前仓库内容不一致（MANIFEST 附 sha256 可作找回后校验）。忽略规则无关（.gitignore 无需修改，也未修改）。**S2 版原文"从未提交/虚假声明/唯一找回途径"系证据不足的过度结论，已在验收轮修正**（修正过程见 08 验收报告）。

### 1.3 处置（按授权二的处理原则 6）

- **记录阻塞，不编造替代存储层**——9 个导入错误原样保留作为阻塞证据，未为让测试通过而伪造实现；
- 依赖该模块的旧项目 v3.2 Web 运行层（登录/隔离/任务/门禁/checkpoint）本轮不实现、不复活；
- 仓库其余 596 项原有测试不受影响，全部通过；
- **防复发修复**：新增 `tests/test_preinitiation_vcs_guard.py`（4 项守护测试）——① 模块全部源码与静态资源不被忽略规则覆盖（`git check-ignore --no-index` 逐文件断言）；② 模块目录无数据库/上传/日志/密钥运行期产物；③ backend/storage/ 路径不被忽略规则覆盖（未来找回源码可直接 `git add`）；④ 非 Git 工作树（如 git archive 干净副本）自动跳过而非误报。

## 2. 干净副本验证结果（S3 验收轮复验，2026-10-16）

构造方式（独立临时目录，不动原工作区数据）：

```bash
git archive HEAD | tar -x -C /tmp/cleancopy-s3        # 受版本管理内容
cp -r src/modules/preinitiation /tmp/cleancopy-s3/src/modules/   # + 未提交新模块
cp tests/_preinitiation_helpers.py tests/test_preinitiation_*.py /tmp/cleancopy-s3/tests/
```

**明确说明**：干净副本 = git archive HEAD（6d02e36 全部受版本管理内容）+ 上述**尚未提交**的本轮新增文件（src/modules/preinitiation/ 11 个文件 + tests/ 12 个文件，即 §4 清单；除此之外无其他未提交内容混入——`git status --short` 仅这些未跟踪条目，无已跟踪文件改动）。

| 验证项 | 工作区结果 | 干净副本结果 | 一致性 |
|---|---|---|---|
| 预立项模块测试 | Ran 108 — OK | Ran 108 — OK (skipped=4) | ✅ |
| 全量测试 | Ran 713 — FAILED (errors=9) | Ran 713 — FAILED (errors=9, skipped=4) | ✅ |
| 9 个 errors 构成 | 全部且仅为 backend.storage 导入错误（无断言失败） | 同左（9 个失败模块逐一比对相同） | ✅ |
| skipped=4 说明 | 0（Git 工作树内守护测试全跑） | 4（vcs_guard 在无 .git 的归档副本按设计跳过） | 按设计 |
| 副本启动冒烟 | — | `python3 -m src.modules.preinitiation.webapp --port 8799` 启动正常，`GET /api/state` 返回 200 | ✅ |

**环境依赖提示（S3 新增，如实记录）**：2026-10-16 复验时当前沙箱缺 `openpyxl`（requirements.txt 第 4 行声明项），全量测试会出现 **34 个与本模块无关的 fixture 读取失败 + 5 个关联 error**（amazon importer 类测试读 xlsx 返回 0 行）；`pip install openpyxl` 后即恢复上表基线（errors=9）。这不是代码回归，是环境依赖缺失——已在 06 §0 同步提示。

结论：**当前受版本管理内容 + 待提交新文件可完整复现基线**；仓库可复现性问题仅剩 backend.storage 一个既有阻塞（§1），与本轮改动无关。用户要求六中"干净副本可以导入 backend.storage 并运行相关测试"一项因源码不可恢复而不适用——已按授权改为上述等效验证并如实说明。

**旧副本处置说明（S3 核查）**：`/workspace/preinitiation/`（S2 移植前独立目录）为**过时草稿**——无 workspace.py、测试为旧命名（test_audit.py 等，无分区/门禁/幂等冲突用例）、导入路径指向旧包名。该目录不纳入交付、不参与验证，仓库 `src/modules/preinitiation/` 为唯一权威版本。

## 3. 本轮预览闭环的启动方式、入口和操作步骤

**入口**（复用现有项目结构：模块位于 `src/modules/preinitiation/`，纯 Python 标准库，无新依赖、无独立登录）：

```bash
cd /workspace/repo-kuajingdianshang
python3 -m src.modules.preinitiation.webapp            # 默认自动分配端口
python3 -m src.modules.preinitiation.webapp --port 8765
# 浏览器打开终端打印的 http://127.0.0.1:<port>（仅监听本机）
# 命令行示例（不走浏览器）：python3 -m src.modules.preinitiation.example
# 测试：python3 -m unittest discover -s tests -t . -p "test_preinitiation_*.py"
```

**操作步骤**（页面 A–E 五区块；对应最小流程"已有项目或参考 ASIN → 最小输入 → 手工录入候选 → 选择候选及采购数量 → 计算结果或不可计算原因 → 保存不可变快照 → 导出待核验预览单"）：

1. **加载样例/手工填写最小输入**（A 区）：演示任务 `dev-task-1001` × 参考 ASIN `B0TESTASIN01`；售价或目标利润率（互斥）、活动营销费占比、汇率（含获取时间）、目标采购量（可空=未知，禁止填 0 表未知）、首轮估算采购价、目标采购价区间。保存后 `input_version`/`meta_version` 递增可见。
2. **手工录入候选 offer/SKU**（B 区）：报价来源与获取时间必填（手工来源明确标记 `manual` + quoted_at）；准入状态固定 unknown（手工录入 ≠ 已满足 1688 准入）；含税口径未知可标未知；SKU 阶梯价（起止数量+单价）。
3. **选择候选及采购数量**（B 区）：区分**搜索报价（仅展示）**与**所选 SKU 在采购量档位下的有效采购价**；SKU 无有效价格时不默认填 0，有效价显示 `--` 且复算被阻止（missing_effective_price）；qty_check 显示 MOQ/阶梯适用性及原因。
4. **查看计算结果或不可计算原因**（C 区）：演示测算=TestOnlyProvider 固定测试输出（显式 test_only + sample_parameters 标注）；真实计算按钮不可用并列出 blocked 原因（D1/D2/D5/Q1/Q3）；缺少关键财务输入时返回结构化"不可计算"+缺失原因码（缺失项不默认 0）。
5. **保存不可变预览快照**（D 区）：frozen 内容 + 可追加事件；显示引用的全部版本；**同一计算结果重复请求不重复创建**（幂等）。
6. **修改输入观察失效**：改售价/汇率/采购量/候选后，旧计算与采购约束标过期（stale），旧快照内容不变仍可追溯（is_current=False），新结果关联新 input_version。
7. **导出"待核验预览单"**（E 区）：强制水印「待核验预览单——非正式测算，禁止用于审批或采购决策」；含六类版本、快照当前是否过期、`approved_for_decision: false`；文件名同样标注。

**多人演示（可选）**：请求头 `X-Owner-Id: <标识>` 映射独立工作区（输入/候选/快照相互隔离；非登录体系）。逐步走查清单见 06 文档。

## 4. 修改文件与测试结果

**仓库内（全部为新增未跟踪文件，未修改任何既有源码——`git status --short` 无已跟踪文件改动条目；`src/core/agent.py` 未触碰）**：

| 目录 | 文件（行数） | 说明 |
|---|---|---|
| src/modules/preinitiation/ | `__init__.py`(18)、`domain.py`(461)、`providers.py`(100)、`repository.py`(160)、`service.py`(701)、`webapp.py`(711)、`workspace.py`(63)、`example.py`(159) | 领域模型/计算提供者/内存仓储/服务编排/本地 HTTP 服务/owner 注册表/可执行示例 |
| src/modules/preinitiation/web/ | `index.html`(232)、`app.css`(271)、`app.js`(848) | 前端单页（无框架、无 CDN） |
| tests/ | `_preinitiation_helpers.py`(63)、`test_preinitiation_inputs.py`(7 测试)、`test_preinitiation_calculation.py`(6)、`test_preinitiation_candidate.py`(8)、`test_preinitiation_repository.py`(2)、`test_preinitiation_audit.py`(17)、`test_preinitiation_snapshot_confirm.py`(8)、`test_preinitiation_versions.py`(17)、`test_preinitiation_partition.py`(10)、`test_preinitiation_gate_tamper.py`(6)、`test_preinitiation_webapp.py`(23)、`test_preinitiation_vcs_guard.py`(4) | 合计 108 项行为测试 |

**S3 验收轮测试文件变更**：`test_preinitiation_isolation.py`(9) 更名 `test_preinitiation_partition.py`(10，+冒用实测)——更名反映真实语义（键空间分区非安全隔离）；新增 `test_preinitiation_gate_tamper.py`(6，服务端门禁篡改防护)；`test_preinitiation_versions.py` 15→17（+同键不同内容首写胜出、8 线程并发保存仅产生 1 快照）；顺带修复测试与 webapp 默认 TASK/ASIN 不一致的缺陷。

**工作区文档（/workspace/docs/preinitiation/）**：01/02/03/04 方案按本轮要求修订（三态区分/审批中心页面级观察/OP 验收状态/演示硬边界）；05 增补 §3A；06 走查清单更新至仓库模块（S3 增 §4A 浏览器走查实测与 §3a 分区表述修正）；07 即本报告；**08 为 S3 验收报告**（结论修正/冒用实测/门禁篡改验证/幂等范围/走查/副本复验）。

**测试结果（2026-10-16 S3 复验，未凑历史数量、未删改测试、未放宽断言）**：

| 命令 | 结果 |
|---|---|
| `python3 -m unittest discover -s tests -t . -p "test_preinitiation_*.py"` | **Ran 108 — OK** |
| `python3 -m unittest discover` | **Ran 713 — FAILED (errors=9)**；9 个全部为 backend.storage 导入错误（§1），既有 596 项测试无断言失败（704→713 系预立项测试 99→108 所致；⚠ 环境缺 openpyxl 时另有 34+5 项无关失败，见 §2 环境提示） |
| `git diff --check` | 干净（无空白错误） |

用户要求六的行为覆盖对照：手工候选预览并导出 → `test_preinitiation_versions.py`（导出契约）/`test_preinitiation_webapp.py::test_full_demo_flow`；缺关键财务输入不可计算 → `test_preinitiation_calculation.py`；SKU 无有效价阻止复算 → `test_preinitiation_candidate.py`；输入修改使结果过期 → `test_preinitiation_versions.py`/`test_preinitiation_webapp.py::test_input_change_stales_calc_and_snapshot`；旧快照不变 → `test_preinitiation_webapp.py::test_history_snapshot_content_frozen`；重复请求不重复快照 → `test_preinitiation_versions.py`（幂等，S3 增同键不同内容首写胜出与并发仅 1 快照）；演示无法正式确认/审批/转产品 → `test_preinitiation_snapshot_confirm.py`（real 门禁必拒）+ `test_preinitiation_gate_tamper.py`（S3：字段篡改不可提级）；用户隔离 → `test_preinitiation_partition.py`（S3 更名，+冒用实测）；干净副本验证 → §2。

## 5. 已实现 / 仅契约 / 仅演示（如实区分）

| 类别 | 内容 |
|---|---|
| **已实现（本地行为级）** | 输入校验与六类版本管理（input/meta/params/sourcing/calc_version/snapshot_seq，不混单一 status）；失效矩阵（输入/候选/参数变更→相关结果与约束过期，旧快照不可变可追溯）；手工候选及报价溯源字段（来源/时间/币种/含税口径必填或显式未知）；有效采购价=SKU 级价格规则（搜索报价仅展示、无价不填 0）；决策快照 frozen+事件+按 calc_id 幂等；模拟确认（幂等）；正式确认七项门禁（当前必拒并返回原因清单）；待核验预览单导出（水印/版本/过期状态/approved_for_decision=false）；owner 级工作区分区（演示级键空间分区，非登录体系、非安全隔离——S3 修正：客户端自报头可冒用，生产化须换用宿主验证上下文）；本地 HTTP 服务安全约束（127.0.0.1、同源/Host 校验、会话令牌、JSON-only、请求体上限）；VCS 守护测试 |
| **已实现（契约/骨架级，真实能力 blocked）** | RealOpProvider 真实测算入口——存在但恒返回 blocked + 原因清单（D1/D2/D5/Q1/Q3），不输出数值；转待开发产品占位——要求 real 确认，当前不可达；0%毛利推算采购价——不实现（Q3+D5） |
| **仅文档契约（未实现）** | 1688 OpenAPI 四接口编排（B2）；批次状态机 API 版；品牌中心任务/待开发产品/审批对接（B4/Q8——对接三态仅达①页面可见）；生产存储/持久化/并发保障（需独立方案报批）；反推售价与采购价公式（D5/Q3 裁决前不作为正式能力） |
| **仅演示（禁止真实使用）** | TestOnlyProvider 固定测算结果（test_only+sample_parameters 全程显式标注）；演示确认（demo_confirmed，永不升级为 real）；全部导出数值——仅可用于本地流程验证，**不能进行正式业务确认、审批或产品转换**（服务层门禁强制执行，非仅文档声明） |

## 6. OP 公式冲突对照表（B8，待业务裁决）

| # | 冲突 | 原始出处 | 口径 A | 口径 B | 影响项 | 待确认人 |
|---|---|---|---|---|---|---|
| D1 | 公司利润率 vs 通用利润率成本清单不一致 | 01-OP利润计算器公式.md 档案 B/C（`ql` 文案）；OP 前端 chunk-libs.js `nl()` 展示函数（偏移 ~3650300–3651000，2026-10-15 二次取证） | `ql`：含增值税/消费税、不含立项人奖励/汇率调节因子；美区分母 (P−A−V) | `nl`：含立项人奖励/汇率调节因子；分母 (P−A) | `branch_us_amazon_sc` 正算的分子构成与分母——影响全部真实测算结果 | 业务 + OP 研发（Q1） |
| D2 | 消费税/汇率调节因子清单疑笔误；美区 SC 所得税适用性 | 同 D1 | 清单含「消费税」不含「汇率调节因子」（按字面） | 视为笔误（两者应互换/取舍）；所得税适用 | 成本项清单与缺失原因码集合 | 业务 + OP 研发（Q1） |
| D5 | Amazon SC 反推公式与正算代数不一致（S0 新发现） | chunk-libs.js `nl()` 偏移 ~3650365（03 §1.2/§1.3） | 由正算 m=(P−A−C)/(P−A) 解出：**P = C/(1−m) + A** | 文案反推式：**P = (A+C)/(1−m) + A**（活动营销费重复计入，多出 A/(1−m)） | 反推售价、0%毛利推算采购价、目标利润率对应采购价——三者全部 blocked | 业务 + OP 研发（Q1 扩展；**需 B3 样例才能判定后端真实口径**） |
| D3 | 0%毛利推算采购价是否计入头程/设计费 | 01-OP利润计算器公式.md 档案 D | 计入（全成本口径） | 不计入（仅货款口径） | 溯源价格上限 R7（一期不产出，用目标采购价区间替代） | 业务（Q3） |
| D4 | 预立项阶段是否输出个人利润率 | 01-OP利润计算器公式.md 档案 C | 输出（含立项人奖励） | 不输出（预立项无立项人/库存归属，公司口径不含——S1 按此处理） | 个人口径字段与展示 | 业务（Q2） |

补充：Amazon SC 美区正算分母 (P−A)、欧区分母 (P−A−V)、日本含消费税 J——分支细节与成本依赖表见 03 §1.2/§1.4。**所有公式当前均为 (a) 文案级，无任何 (c) 已验证级**（03 §1.1）。

## 7. 进入真实测算所需的最少材料清单

| # | 材料 | 为什么必需 | 提供方 |
|---|---|---|---|
| 1 | **标准对账样例 ≥1 组**（完整输入 + OP 计算器完整输出：利润率+各成本项金额） | 唯一能产生 (c) 级验证公式的途径；无样例则永远不宣称"已对账 OP" | 业务（使用 OP 计算器的同事） |
| 2 | **D1/D2/D5 口径裁决**（Q1，含反推公式以正算解/文案式/后端实现何者为准） | 决定 branch_us_amazon_sc 的分子分母构成；D5 不决则反推类全部不可解封 | 业务 + OP 研发 |
| 3 | **OP 费率参数表**（品类佣金率、仓租基数、尾程分区单价、操作费/入库费、提现费、所得税适用性、"其他杂费"兜底规则） | 真实测算的参数输入（B1）；需带版本管理 | 业务 + OP 研发 |
| 4 | **汇率数据源**（手工/接口 + 更新频率，Q7） | fx_usd_to_cny 的来源与时效标注 | 业务/OP 研发 |
| 5 | 用户侧输入 | 售价（或裁决后允许的目标利润率路径）、活动营销费占比、有效采购价（手工 SKU 级报价已支持，API 版待 B2） | 任务开发人 |

**解封动作**（材料齐备后）：同输入跑本实现与 OP 输出逐项对账（03 §10）→ 通过后 branch_us_amazon_sc 由 blocked → verified → 真实测算入口开放。此前一切数值仅 demo 域。

## 8. 下一步建议及阻塞项

**建议优先级**（解锁链：材料 → 对账 → 解封）：
1. 业务侧先给 B3 样例 + Q1 裁决（成本最低、解锁面最大——真实测算的唯一通路）；
2. OP 研发给 B1 参数表（只读接口或导出均可）；
3. B4 接口文档 + Q8 流程顺序确认（解锁 T4.2–T4.4 宿主接入设计）；
4. B2 1688 凭证（解锁 API 溯源；手工降级路径已可用，不阻塞演示）。

**阻塞项全景**（详见 01 §4 / 05 §4）：B1 参数表｜B2 1688 凭证｜B3 对账样例｜B4 品牌中心接口文档｜**B5 backend/storage 源码（S3 修正：当前提交与可访问历史均未找到；可能的找回范围=维护者本地未推送提交/工作区/其他备份，超出本沙箱可访问能力；MANIFEST sha256 可作找回后校验；找回后可直接 git add——路径未被忽略）**｜B6 0%毛利口径（Q3）｜B7 立项状态枚举｜B8 公式歧义 D1–D5；业务问题 Q1–Q9（Q1/Q3/Q8 为关键路径）。

**本轮明确不做/未做**：未 commit/push（待审阅）；未修改任何既有源码与 src/core/agent.py；未调用付费 1688 API、未读取生产凭证、未调用生产审批或待开发产品写入接口；未新建登录/审批系统；未将演示结果用于或表述为真实决策依据。

---

*报告完。本闭环状态：本地预览纵向切片可运行、可测试、可追溯；真实财务与审批链路全部处于 blocked/待材料状态，未越权。*
