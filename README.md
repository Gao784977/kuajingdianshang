# 机会分析工具 (Opportunity Analysis Tool)

一个通过命令行运行的机会分析工具，用于读取 CSV 机会数据、校验数据、计算机会评分与利润指标，并生成可追溯的 Markdown 立项报告、机器可读 JSON 结果和 CSV 结果表。

本工具仅使用 Python 标准库，无需安装第三方依赖，兼容 Python 3.10+。

---

## 多端开发（公司电脑 + 个人电脑）

本项目支持通过 Git 远程仓库在多台电脑之间同步代码。每台电脑使用独立的本地配置、数据库和文件存储。

### 快速开始

| 平台 | 初始化命令 |
| --- | --- |
| Windows (PowerShell) | `.\scripts\setup_local.ps1` |
| macOS / Linux (bash) | `bash scripts/setup_local.sh` |

脚本会自动：创建虚拟环境、安装依赖、创建目录、复制 `.env.example` 为 `.env`、运行环境检查、运行测试。

初始化后编辑 `.env` 设置 `ADMIN_BOOTSTRAP_TOKEN`，然后 `python -m backend.app` 启动。

### 关键文件

| 文件 | 用途 |
| --- | --- |
| [.env.example](.env.example) | 环境变量模板（提交到 Git） |
| [.gitignore](.gitignore) | Git 忽略规则 |
| [docs/MULTI_DEVICE_DEVELOPMENT.md](docs/MULTI_DEVICE_DEVELOPMENT.md) | 多端开发规范 |
| [docs/LOCAL_SETUP.md](docs/LOCAL_SETUP.md) | 本地初始化详细指南 |
| [docs/GIT_SETUP.md](docs/GIT_SETUP.md) | Git 安装与远程仓库配置 |
| [docs/AI_DEVELOPMENT_CONTEXT.md](docs/AI_DEVELOPMENT_CONTEXT.md) | AI 编程代理交接说明 |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 贡献规范与分支策略 |
| [scripts/check_environment.py](scripts/check_environment.py) | 本地环境检查 |
| [scripts/reset_local_data.py](scripts/reset_local_data.py) | 本地数据重置（默认干跑） |

### 环境要求

- **Python**: 3.10+（测试通过 3.10.11）
- **Git**: 任意最近版本（用于代码同步）
- **openpyxl**: 3.1.0+（可选，未安装时 Excel 输出跳过）
- **Node.js**: 不需要（前端为静态文件，无构建步骤）

### 日常同步

```bash
# 开始开发前
git pull --rebase

# 开发完成后
python -m unittest discover -s tests -p "test_*.py"
git add <实际修改的文件>
git commit -m "描述本次修改"
git push
```

### 不应提交到 Git 的内容

- `.env`（密钥）
- `data/web.db*`（本地 SQLite）
- `data/web_storage/`（用户上传）
- `data/output/`、`data/amazon/output/`（生成报告）
- `.venv/`、`__pycache__/`、`logs/`、`temp/`

`.gitignore` 已覆盖以上路径。详见 [docs/MULTI_DEVICE_DEVELOPMENT.md](docs/MULTI_DEVICE_DEVELOPMENT.md)。

---

## V3.2 Web 后端

V3.2 在 V3.1 工作流之上增加本地 Web 后端、用户隔离、邀请码登录、异步任务、断点恢复和 veFaaS 部署适配骨架。

### 启动 Web 后端

```bash
# 编辑 .env 设置 ADMIN_BOOTSTRAP_TOKEN
python -m backend.app
# 访问 http://127.0.0.1:8000/
```

### V3.2 关键能力

- 邀请码登录、Session、CSRF 防护
- 用户隔离（owner_id 校验）
- 项目管理、文件上传、xlsx/csv/json 检测、xls 拒绝
- 异步任务、任务取消（CancellationToken）
- WorkflowCheckpoint 断点恢复（Phase 1 调研 / Phase 2 开发）
- 产品候选确认门禁
- 模板上传与绑定
- 报告生成与输出下载
- veFaaS API Handler（真实可用）、Worker Handler（骨架）

### V3.2 当前状态

- 本地开发：**可用**（699/699 测试通过）
- 生产部署：**未就绪**（TOS、生产数据库、真实队列未接入）
- 详见 [handoff/](handoff/) 目录的 14 份交接文件

---


## 版本说明

- **v1**：基础评分与利润测算、Markdown + JSON 报告、CLI。
- **v2**：在 v1 基础上升级为"可配置、可比较、可解释、可复核"的机会评估工具，新增配置驱动评分、三种测算情景、敏感性分析、组合汇总、立项建议、人工复核字段、CSV 结果导出、13 节可追溯报告。
- **v3**：在 v1/v2 之上新增独立的"Amazon US 产品开发多 Agent 工作流"，面向亚马逊美国站选品与立项。9 个 Agent 顺序执行，产出 Markdown + JSON + 2 个 Excel 工作簿。完全离线运行，仅使用确定性模拟数据或用户输入，无网络、无 API Key、无 SP-API。
- **v3.1**：在 v3 基础上升级为支持卖家精灵/Brand Analytics Excel 导入、多关键词多类目分析、用户指定公开 URL、产品候选人工确认门禁的完整市场调研与产品开发工作流。8 个子版本（V3.1.1–V3.1.8）逐步交付，产出市场调研 Excel（9 Sheet）+ 工作流 Markdown + JSON 报告。不修改 v3 的 9 Agent 管道与 `src/core/agent.py`，全部 587 个测试通过。

v2 完全兼容 v1 的输入格式、评分版本（`scoring_v1`）和 CLI 用法。v3 是独立模块（`src/modules/amazon/`），拥有自己的配置（`config/amazon_workflow.json`）和 CLI（`python -m src.modules.amazon.workflow`），不修改 v1/v2 代码与 `src/core/agent.py`，v1/v2 的 99 个测试全部保持通过。v3.1 在 `src/modules/amazon/` 内新增 `importers/`、`analyzers/`、`url_sources/` 等子模块，复用 v3 的 MasterAgent 与利润计算，不修改 v3 现有 Agent。

## v1 与 v2 的差异

| 维度 | v1 | v2 |
| --- | --- | --- |
| 评分规则 | 硬编码在 Python 中 | 配置驱动（`config/opportunity_config.json`） |
| 评分版本 | `scoring_v1` | `scoring_v2`（默认），兼容 `scoring_v1` |
| 测算情景 | 仅基准 | base / optimistic / pessimistic / all |
| 收入口径 | 隐式回退 | 显式 `revenue_source` + 一致性警告 |
| 回本周期 | `payback_months`（净） | `gross_payback_months` + `net_payback_months` |
| 敏感性分析 | 无 | 支持参数扫描与等级跨越检测 |
| 排序 | 按 ID | 支持 score / profit / payback / margin / investment |
| 组合汇总 | 等级分布 | 投资、收入、利润、毛利率、最快回本等 |
| 立项建议 | 等级对应文字 | 结构化 `recommendation_detail`（含 confidence、human_review_required） |
| 人工复核字段 | 无 | owner / validation_status / reviewer 等 9 个可选字段 |
| 报告 | 基础章节 | 13 节可追溯报告（含配置 SHA-256、CLI 参数、数据质量） |
| 输出 | Markdown + JSON | Markdown + JSON + CSV |

## 第二版功能

1. **配置驱动的评分规则**：权重、枚举分值、经济分档、等级阈值全部从配置读取，权重和必须为 100。
2. **三种测算情景**：base / optimistic / pessimistic，参数可配置，报告并列展示。
3. **明确收入口径**：记录 `revenue_source`（input / calculated），差异超阈值时警告。
4. **统一回本周期口径**：区分 `gross_payback_months` 与 `net_payback_months`，评分默认使用净回本。
5. **敏感性分析**：对单价、数量、单位变动成本、月运营成本做 ±20% 扫描，找出最敏感参数和等级跨越点。
6. **机会排序和组合汇总**：支持多字段排序，输出总投资、总收入、总利润、平均/加权毛利率等。
7. **立项建议升级**：结构化 `recommendation_detail`，含 reasons / blockers / required_validation / confidence / human_review_required。
8. **人工复核字段**：9 个可选字段，严格模式下校验枚举与约束。
9. **结果导出 CSV**：每行一个机会-情景组合。
10. **13 节可追溯报告**：含输入/配置 SHA-256、CLI 参数、数据质量统计、可追溯信息。

## 目录与修改规则

- 新增业务代码优先放到 `src/modules/`
- 最终生成文件放到 `data/output/`
- 临时文件放到 `temp/`
- 日志追加到 `logs/`
- 不修改 `src/core/agent.py`，除非确实无法完成且先说明原因
- 不硬编码任何 API 密钥
- 使用相对路径
- 保持现有项目结构，不做无关重构
- 默认使用 Python 标准库，尽量不新增依赖
- 代码、字段名、文件名使用英文；报告内容可以使用中文
- 不覆盖历史报告，输出文件名带时间戳

## 第一版功能

1. 读取 CSV 机会数据（支持 UTF-8 / UTF-8 BOM）
2. 校验 CSV 字段与数据类型，一次性报告所有错误
3. 对每条机会计算 100 分制机会评分（需求 / 经济收益 / 战略匹配 / 执行可行性）
4. 计算收入、成本、毛利、毛利率、回本周期、月净利润、年化利润
5. 输出逐条分析结果（评分明细 + 利润测算）
6. 生成可追溯的 Markdown 立项报告（含输入文件 SHA-256、规则版本、汇总表、逐条分析、风险与结论）
7. 生成机器可读 JSON 结果文件
8. 提供 CSV 模板与覆盖 A/B/C/D 等级的演示数据
9. 提供完整单元测试（基于 `unittest`）

## 安装

无需安装第三方依赖。确保使用 Python 3.10+：

```bash
python --version
```

## 运行

### v1 兼容用法（默认输出到 data/output）

```bash
python -m src.modules.analyze_opportunities --input data/raw/demo_opportunities.csv
```

### v2 完整用法（三情景 + 敏感性 + 排序）

```bash
python -m src.modules.analyze_opportunities \
  --input data/raw/demo_opportunities_v2.csv \
  --scenario all \
  --sensitivity \
  --sort-by score \
  --descending \
  --output-dir data/output/v2
```

### 仅基准情景

```bash
python -m src.modules.analyze_opportunities \
  --input data/raw/demo_opportunities_v2.csv \
  --scenario base
```

### 使用 v1 评分规则（兼容第一版）

```bash
python -m src.modules.analyze_opportunities \
  --input data/raw/demo_opportunities.csv \
  --scoring-version scoring_v1 \
  --calculation-version calculation_v1
```

### 严格模式（校验人工复核字段约束）

```bash
python -m src.modules.analyze_opportunities --input data/raw/demo_opportunities_v2.csv --strict
```

### 自定义配置文件

```bash
python -m src.modules.analyze_opportunities \
  --input data/raw/demo_opportunities.csv \
  --config config/opportunity_config.json
```

查看帮助：

```bash
python -m src.modules.analyze_opportunities --help
```

### CLI 参数

| 参数 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--input` | 是 | - | 输入 CSV 路径 |
| `--output-dir` | 否 | `data/output` | 报告输出目录 |
| `--config` | 否 | `config/opportunity_config.json` | 配置文件路径 |
| `--scoring-version` | 否 | `scoring_v2` | 评分规则版本（`scoring_v1` / `scoring_v2`） |
| `--calculation-version` | 否 | `calculation_v2` | 测算规则版本 |
| `--scenario` | 否 | `base` | 测算情景：`base` / `optimistic` / `pessimistic` / `all` |
| `--sensitivity` | 否 | `False` | 开启敏感性分析 |
| `--sensitivity-parameters` | 否 | 配置默认值 | 敏感性分析参数列表 |
| `--sort-by` | 否 | `score` | 排序字段：`score` / `profit` / `payback` / `margin` / `investment` |
| `--ascending` | 否 | `False` | 升序排序 |
| `--descending` | 否 | `True` | 降序排序（默认） |
| `--strict` | 否 | `False` | 严格模式，校验人工复核字段约束 |
| `--help` | 否 | - | 显示帮助 |

参数冲突时给出清晰错误：同时指定 `--ascending` 和 `--descending`、不存在的 scenario、不存在的排序字段、不存在的敏感性参数。

运行成功后打印：输入文件、分析机会数量、A/B/C/D 数量、Markdown 报告路径、JSON 结果路径、CSV 结果路径。
运行失败时返回非零退出码并输出明确错误。

## 输入 CSV 字段

模板文件：[`data/raw/opportunity_template.csv`](data/raw/opportunity_template.csv)

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `opportunity_id` | 字符串，必填 | 机会唯一编号，不能为空，不能重复 |
| `opportunity_name` | 字符串，必填 | 机会名称，不能为空 |
| `customer_segment` | 字符串 | 客户类型 |
| `industry` | 字符串 | 行业 |
| `region` | 字符串 | 地区 |
| `estimated_units` | 非负数 | 预计销售数量 |
| `unit_price` | 非负数 | 单价 |
| `variable_cost_per_unit` | 非负数 | 单位变动成本 |
| `fixed_cost` | 非负数 | 固定成本 |
| `marketing_cost` | 非负数 | 营销成本 |
| `implementation_cost` | 非负数 | 实施成本 |
| `expected_monthly_growth` | 小数 | 预期月增长率，例如 `0.08` 表示 8% |
| `competition_level` | 枚举 | 竞争程度：`low` / `medium` / `high` |
| `customer_need` | 枚举 | 客户需求强度：`low` / `medium` / `high` |
| `delivery_difficulty` | 枚举 | 交付难度：`low` / `medium` / `high` |
| `strategic_fit` | 枚举 | 战略匹配度：`low` / `medium` / `high` |
| `initial_investment` | 非负数 | 初始投资额 |
| `expected_monthly_operating_cost` | 非负数 | 预计月运营成本 |
| `expected_monthly_revenue` | 非负数或空 | 预计月收入；为空时使用 `estimated_units * unit_price` |
| `risk_notes` | 字符串或空 | 风险备注 |
| `owner` | 字符串或空 | **（v2 可选）** 负责人 |
| `source` | 字符串或空 | **（v2 可选）** 机会来源 |
| `validation_status` | 枚举或空 | **（v2 可选）** `pending` / `partial` / `verified` / `rejected` |
| `customer_validation_notes` | 字符串或空 | **（v2 可选）** 客户需求验证备注 |
| `pricing_validation_notes` | 字符串或空 | **（v2 可选）** 价格验证备注 |
| `cost_validation_notes` | 字符串或空 | **（v2 可选）** 成本验证备注 |
| `reviewer` | 字符串或空 | **（v2 可选）** 复核人 |
| `review_status` | 枚举或空 | **（v2 可选）** `not_reviewed` / `in_review` / `approved` / `rejected` |
| `review_notes` | 字符串或空 | **（v2 可选）** 复核备注 |

v2 新增的 9 个人工复核字段均为可选，旧版 CSV 缺失这些字段时仍可正常加载，报告中显示"未提供人工复核信息"。

严格模式（`--strict`）下的人工复核字段校验规则：

- `validation_status` 只允许 `pending` / `partial` / `verified` / `rejected`
- `review_status` 只允许 `not_reviewed` / `in_review` / `approved` / `rejected`
- `review_status` 为 `approved` 时必须有非空 `reviewer`
- `review_status` 为 `rejected` 时必须有非空 `review_notes`

CSV 读取要求：

- 使用 `csv` 标准库，支持 UTF-8 与 UTF-8 BOM
- 文件不存在时给出清晰错误
- 缺少字段时列出所有缺失字段
- 数值字段非法时指出机会编号、字段名和原始值
- 枚举字段非法时指出允许值
- `opportunity_id` 不能重复
- 空行自动跳过
- 不静默吞掉错误

## 配置文件格式

配置文件：[`config/opportunity_config.json`](config/opportunity_config.json)

v2 的评分规则、情景参数、敏感性参数全部由配置驱动。主要字段：

| 字段 | 说明 |
| --- | --- |
| `scoring_version` | 默认评分版本（`scoring_v2`） |
| `calculation_version` | 默认测算版本（`calculation_v2`） |
| `fields` / `optional_fields` | CSV 字段定义 |
| `enum_fields` / `review_enum_fields` | 枚举字段允许值 |
| `scoring_rules` | 各评分版本的规则（权重、枚举分值、经济分档、等级阈值、回本口径） |
| `scenarios` | 三种情景的乘数 |
| `sensitivity` | 敏感性分析参数与变化范围 |
| `revenue_consistency_threshold` | 收入一致性警告阈值（默认 0.10） |
| `payback_warning_months` | 回本周期警告阈值（默认 24） |

配置校验规则：

- 配置文件不存在时给出清晰错误
- 配置格式错误时指出具体字段
- `score_weights` 总和必须为 100，否则拒绝运行
- `grade_thresholds` 必须满足 A > B > C >= D，否则拒绝运行
- 评分枚举值必须与输入校验规则一致
- 报告记录配置文件 SHA-256，不只是路径

### 评分规则（scoring_v1 / scoring_v2）

总分 100 分，由四部分组成：

| 子项 | 满分 | 依据 |
| --- | --- | --- |
| 市场需求 | 30 | `customer_need` |
| 经济收益 | 30 | 毛利率 + 回本周期 |
| 战略匹配 | 20 | `strategic_fit` |
| 执行可行性 | 20 | `delivery_difficulty` + `competition_level` |

### 需求分（30）

| `customer_need` | 得分 |
| --- | --- |
| high | 30 |
| medium | 20 |
| low | 10 |

### 战略匹配分（20）

| `strategic_fit` | 得分 |
| --- | --- |
| high | 20 |
| medium | 13 |
| low | 6 |

### 执行可行性分（20）

基础分由 `delivery_difficulty` 决定，再根据 `competition_level` 调整，最低为 0：

| `delivery_difficulty` | 基础分 | `competition_level` | 调整 |
| --- | --- | --- | --- |
| low | 20 | low | +0 |
| medium | 13 | medium | -3 |
| high | 6 | high | -6 |

### 经济收益分（30）

先计算（评分内部使用简化口径）：

- `revenue = expected_monthly_revenue`，为空则 `estimated_units * unit_price`
- `variable_cost = estimated_units * variable_cost_per_unit`
- `total_cost = variable_cost + fixed_cost + marketing_cost + implementation_cost`
- `gross_profit = revenue - total_cost`
- `gross_margin = gross_profit / revenue`（`revenue <= 0` 时为 0）
- `payback_months = initial_investment / gross_profit`（`gross_profit <= 0` 时为 null）

经济收益分：

| 条件 | 得分 |
| --- | --- |
| `gross_margin >= 0.40` 且 `payback_months <= 6` | 30 |
| `gross_margin >= 0.30` 且 `payback_months <= 12` | 24 |
| `gross_margin >= 0.20` 且 `payback_months <= 18` | 18 |
| `gross_margin > 0`（不满足上述） | 10 |
| `gross_margin <= 0` | 0 |

### 等级

| 总分 | 等级 | 建议 |
| --- | --- | --- |
| >= 80 | A | 建议进入正式立项评审 |
| >= 60 | B | 建议补充客户、价格或成本验证后再评审 |
| >= 40 | C | 建议保留观察，暂不投入较大资源 |
| < 40 | D | 建议暂不立项 |

## 利润公式（calculation_v1）

| 指标 | 公式 |
| --- | --- |
| `revenue` | `expected_monthly_revenue`，为空则 `estimated_units * unit_price` |
| `variable_cost` | `estimated_units * variable_cost_per_unit` |
| `total_cost` | `variable_cost + fixed_cost + marketing_cost + implementation_cost` |
| `gross_profit` | `revenue - total_cost` |
| `gross_margin` | `gross_profit / revenue`（`revenue <= 0` 时为 0） |
| `net_monthly_profit` | `revenue - variable_cost - expected_monthly_operating_cost` |
| `annualized_profit` | `net_monthly_profit * 12` |
| `payback_months` | `initial_investment / net_monthly_profit`（`net_monthly_profit <= 0` 时为 null） |

金额保留两位小数；比例保留四位小数，报告中显示为百分比。

### v2 回本周期口径

v2 明确区分两个回本周期指标：

| 指标 | 公式 | 说明 |
| --- | --- | --- |
| `gross_payback_months` | `initial_investment / gross_profit` | 基于毛利的回本周期 |
| `net_payback_months` | `initial_investment / net_monthly_profit` | 基于净利润的回本周期 |

分母小于等于 0 时为 `null`。报告中同时展示两个指标。

评分使用的回本口径由配置中 `payback_metric` 决定：

- `scoring_v1`：使用 `gross_profit`（毛利回本）
- `scoring_v2`：使用 `net_monthly_profit`（净回本，默认）

### v2 收入口径

利润计算明确记录收入来源：

- `revenue_source`：`input`（使用 `expected_monthly_revenue`）或 `calculated`（使用 `estimated_units * unit_price`）
- `input_expected_monthly_revenue`：输入的月收入
- `calculated_units_revenue`：数量乘单价
- `final_revenue`：最终采用的收入

规则：

1. 如果 `expected_monthly_revenue` 有值，使用该值
2. 如果为空，使用 `estimated_units * unit_price`
3. 不允许静默覆盖两个不同的收入值
4. 如果两个值都存在且差异超过配置阈值（默认 10%），增加 `revenue_consistency_warning` 警告

## 三种测算情景

通过 `--scenario` 参数选择情景：`base`（默认）/ `optimistic` / `pessimistic` / `all`。

情景参数在配置 `scenarios` 中定义，对单价、数量、各项成本施加乘数：

| 乘数 | base | optimistic | pessimistic |
| --- | --- | --- | --- |
| `unit_price_multiplier` | 1.0 | 1.05 | 0.90 |
| `units_multiplier` | 1.0 | 1.20 | 0.70 |
| `variable_cost_multiplier` | 1.0 | 0.95 | 1.10 |
| `fixed_cost_multiplier` | 1.0 | 1.0 | 1.10 |
| `marketing_cost_multiplier` | 1.0 | 1.0 | 1.15 |
| `implementation_cost_multiplier` | 1.0 | 1.0 | 1.10 |
| `operating_cost_multiplier` | 1.0 | 1.0 | 1.15 |

情景不会改变需求、战略和交付评分，只改变经济收益部分和最终经济结论。

## 敏感性分析

通过 `--sensitivity` 开启。默认扫描以下参数：

- `unit_price`（单价）
- `estimated_units`（数量）
- `variable_cost_per_unit`（单位变动成本）
- `expected_monthly_operating_cost`（月运营成本）

默认变化范围：-20% / -10% / 0% / 10% / 20%。

可用 `--sensitivity-parameters` 指定参数子集。

输出：参数名称、变化比例、月收入、月净利润、毛利率、回本周期、总分、等级、是否改变立项建议。报告指出最敏感参数、等级跨越参数、对价格/成本的敏感性。敏感性分析不改变主结果。

## 机会排序和组合汇总

排序通过 `--sort-by` 指定：`score`（默认）/ `profit` / `payback` / `margin` / `investment`，配合 `--ascending` / `--descending`。

组合汇总额外输出：

- 机会总数、总初始投资、总月收入、总月净利润、总年化利润
- A/B/C/D 数量、A/B 级机会预计投资与年化利润
- 平均毛利率、加权毛利率
- 最快回本机会、最高利润机会、最高风险机会

## 立项建议

每条机会生成结构化 `recommendation_detail`：

- `recommendation`：`proceed_to_review`（A）/ `validate_before_review`（B）/ `monitor`（C）/ `reject_or_hold`（D）
- `reasons` / `blockers` / `required_validation`
- `confidence`：`high` / `medium` / `low`
- `human_review_required`：是否需要人工复核

以下情况必须设置 `human_review_required = true`：

- 任一主要情景为负利润
- 回本周期超过 24 个月
- 收入来源存在较大差异
- 高竞争且高交付难度
- 敏感性分析中轻微参数变化导致等级下降两级或以上
- 输入数据存在边界值或缺失关键数据

## 输出文件

输出目录默认 `data/output/`，文件名带时间戳，不会覆盖历史报告：

- Markdown 报告：`opportunity_report_YYYYMMDD_HHMMSS.md`
- JSON 结果：`opportunity_analysis_YYYYMMDD_HHMMSS.json`
- CSV 结果（v2，每行一个机会-情景）：`opportunity_analysis_YYYYMMDD_HHMMSS.csv`

### Markdown 报告章节（v2）

1. 执行摘要
2. 运行参数
3. 配置摘要
4. 数据质量检查
5. 机会排名
6. 组合汇总
7. 情景比较
8. 敏感性分析
9. 每个机会的详细分析
10. 风险和人工复核
11. 计算口径
12. 可追溯信息
13. 限制和免责声明

可追溯信息包括：输入文件路径、输入文件 SHA-256、配置文件 SHA-256、评分版本、测算版本、情景版本、运行时间、Python 版本、CLI 参数、输入记录数、有效记录数、错误记录数、警告数量。

### JSON 结构（v2）

包含：`metadata`、`command`、`source`、`config_snapshot`、`scoring`、`calculations`、`data_quality`、`summary`、`rankings`、`scenarios`、`sensitivity`、`opportunities`、`warnings`。

### CSV 结果字段

`opportunity_id`, `opportunity_name`, `scenario`, `total_score`, `grade`, `recommendation`, `revenue`, `gross_profit`, `gross_margin`, `net_monthly_profit`, `annualized_profit`, `gross_payback_months`, `net_payback_months`, `initial_investment`, `human_review_required`。

## 测试

运行全部测试：

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

测试覆盖（v1 + v2）：

- v1：正常读取、UTF-8 BOM、缺字段、重复 ID、非法数值、非法枚举、空行跳过、收入回退计算、毛利率、负利润回本周期为 null、正利润回本周期、评分子项与总分、A/B/C/D 等级边界、报告哈希、规则版本、CLI 成功、CLI 文件不存在返回非零退出码。
- v2：配置加载、配置缺失、权重不等于 100、scoring_v1/v2 兼容、base/optimistic/pessimistic 情景、`--scenario all`、收入来源为输入值/数量乘单价、收入差异警告、gross/net 回本周期、负利润回本周期为 null、敏感性分析、排序、组合汇总、人工复核字段校验、结果 CSV 输出、报告包含配置 SHA-256、报告包含 CLI 参数、报告包含数据质量统计、旧版 CSV 兼容、非法字段严格模式报错、不存在的配置文件返回非零退出码。

## 演示数据

- [`data/raw/demo_opportunities.csv`](data/raw/demo_opportunities.csv)：第一版演示数据，5 条机会，覆盖 A/B/C/D 等级与高竞争高交付难度。
- [`data/raw/demo_opportunities_v2.csv`](data/raw/demo_opportunities_v2.csv)：第二版演示数据，5 条机会，覆盖：
  - 三情景差异明显的机会（V2-001）
  - 悲观情景亏损但基准情景盈利的机会（V2-002）
  - 收入来源存在明显差异的机会（V2-003）
  - 需要人工复核的机会（V2-004，高竞争 + 高交付难度）
  - 敏感性分析中跨越等级边界的机会（V2-005）

## 当前限制与后续方向

- 本工具为**辅助决策工具，不是最终投资决策系统**。
- 结果依赖输入数据质量。
- 未纳入税费、融资成本、现金流时间价值和汇率风险。
- 情景参数只是可配置假设。
- 人工复核仍然是必要环节。
- `expected_monthly_growth` 仅记录，未纳入评分与测算。
- 评分与测算为静态快照，未考虑市场波动与概率分布。
- 枚举字段为人工评估，存在主观性。
- 回本周期以月为单位静态计算，未考虑现金流折现。
- 报告生成确定性：相同输入与规则下，除生成时间、文件名、输入文件哈希外结果一致。
- 本版暂不实现：Web 前端、数据库、登录权限、在线 API、大模型自动决策、自动修改原始 CSV、网络搜索、复杂财务模型、税务和会计口径核算。

---

# V3 — Amazon US 产品开发多 Agent 工作流

V3 在 v1/v2 之上新增一个**完全离线**的亚马逊美国站产品开发分析工作流。用户提供一份 JSON 产品输入（关键词、站点、目标价格、约束），系统按固定顺序运行 9 个分析 Agent，产出 Markdown 报告、JSON 结果和 2 个 Excel 工作簿。所有数据来自确定性模拟数据或用户输入，无网络调用、无 API Key、无 SP-API、无 LLM 自动决策。

> **重要免责声明**：V3 ≠ 真实亚马逊数据。模拟数据围绕"chicken coop door（鸡舍门）"品类构造，仅用于驱动工作流并验证各 Agent 之间的数据流。所有市场容量、搜索量、竞品销量均为定性/假设值，不可作为真实投资决策依据。V3 是辅助决策工具，不是最终投资决策系统。

## V3 与 V1/V2 的关系

| 维度 | 说明 |
| --- | --- |
| 模块位置 | `src/modules/amazon/`（独立目录，不改动 v1/v2 的 `src/modules/`） |
| 配置 | `config/amazon_workflow.json`（独立配置，不碰 `config/opportunity_config.json`） |
| CLI | `python -m src.modules.amazon.workflow`（独立入口） |
| 评分口径 | Amazon 利润 13 个成本字段 + 9 个情景乘数（不复用 v1/v2 `calculate_profit`） |
| 测试 | 92 个 V3 测试 + v1/v2 的 99 个测试全部保持通过（共 191 个测试） |
| 核心文件保护 | 不修改 `src/core/agent.py`，不修改 v1/v2 任何模块 |

## Agent 架构

9 个 Agent 按以下固定顺序执行（顺序锁定，测试断言）：

1. `keyword` — 关键词分析（模拟相关词簇，search_volume 为 null）
2. `market` — 市场定性分析（品类、目标客户、竞争级别、机会分 1-100）
3. `competitor` — 竞品矩阵（价格/评分/评论分布、共性好/差评、市场空白、差异化机会）
4. `review` — Review 痛点分类（7 类：installation/quality/packaging/feature_request/price/shipping/customer_service）
5. `opportunity` — 机会评分（市场/竞争/供应链/差异化各 1-5 分）+ 立项建议
6. `product` — 产品开发规划（卖点、功能设计、差异化方案、目标价/成本/毛利率、包装/安装方向、开发周期、风险、验证计划、供应商问题清单）
7. `profit` — Amazon 利润测算（13 成本字段、base/optimistic/pessimistic 三情景）
8. `report` — Markdown + JSON 报告（17 节锁定顺序）
9. `excel` — 市场报告 + 产品规划两个 Excel 工作簿（可选 openpyxl）

### 失败语义（决策 #10）

- `--strict`：任一 Agent 失败 → `final_status=failed` 并中止。
- 非 strict：某 Agent 失败 → `final_status=incomplete`（后续 Agent 仍继续运行）。
- Excel 单独被跳过（openpyxl 未安装）→ `final_status=completed_with_warnings`。
- 状态枚举：`completed` / `completed_with_warnings` / `failed` / `incomplete`。

### 数据来源与可信度（决策 #7）

每个主要字段携带 `(value, source, confidence)`。来源 ∈ {`user_input`, `mock_data`, `calculated`, `imported_csv`, `imported_xlsx`, `manual_review`}；可信度 ∈ {`high`, `medium`, `low`, `unknown`}。**模拟数据可信度永远不为 `high`**。当用户 CSV 与模拟数据同时存在时，用户输入优先，覆盖标记为 `source=user_input`，填充标记为 `source=mock_data`（决策 #13）。

## 离线运行说明

V3 在无网络、无 API Key 的环境中运行：

- 无 `requests` / `urllib.request` / `http.client` / `openai` / `boto` / `amazon_spapi` 等网络导入（测试用 grep 验证）。
- 不读取任何 `API_KEY` / `OPENAI_API_KEY` / `AMAZON_SECRET` / `AWS_SECRET` 等环境变量。
- 未来接入真实 SP-API / Ads API 时，只需替换 `src/modules/amazon/mock_data.py` 这一数据提供层，Agent 逻辑无需改动（干净接缝）。

## 输入 JSON 格式

输入文件示例：[`data/amazon/demo_product_input.json`](data/amazon/demo_product_input.json)

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `keyword` | 字符串 | 是 | 产品关键词，如 `chicken coop door` |
| `marketplace` | 字符串 | 是 | 站点，必须在 `config.supported_marketplaces` 中（默认 `amazon_us`） |
| `target_price_min` | 数字 | 否 | 目标价格下限 |
| `target_price_max` | 数字 | 否 | 目标价格上限（须 ≥ min） |
| `direction` | 字符串 | 否 | 方向描述 |
| `constraints` | 字符串数组 | 否 | 约束条件 |
| `notes` | 字符串 | 否 | 备注 |
| `competitors_path` | 字符串 | 否 | 竞品 CSV 路径（不填则用模拟竞品） |
| `reviews_path` | 字符串 | 否 | 评论 CSV 路径（不填则用模拟评论） |

竞品 CSV 列：`brand, asin, product_name, price, rating, review_count, selling_points, negative_points, source`。评论 CSV 列：`review_id, asin, rating, review_text, review_date, source`。CSV 按列名读取（与列顺序无关）。

## 模拟数据说明

模拟数据围绕"chicken coop door"品类构造，确定性（相同输入 → 相同输出）：

- 4 个模拟竞品（`MOCK-ASIN-001..004`，`source=mock_data`）
- 12 条模拟评论（`MOCK-REV-001..012`，覆盖 installation/quality/packaging/feature_request/price/shipping 6 类痛点）
- 关键词簇、市场定性值均来自 `src/modules/amazon/mock_data.py`
- 利润输入来自 `config.profit_cost_defaults`，与配置保持同步

模拟数据的 `confidence` 一律为 `low`。当用户提供了竞品/评论 CSV 时，对应 Agent 的 `source` 升级为 `imported_csv`、`confidence` 升级为 `medium`。

## Excel 输出（可选）

Excel 生成依赖 `openpyxl`（3.1.0+），在 `excel_agent.py` 内**懒加载**。未安装时 Excel Agent 返回 `status=skipped`，Markdown/JSON 报告不受影响，`final_status=completed_with_warnings`。

- 市场报告：`market_report_<ts>.xlsx`，5 个 Sheet：`Market_Analysis` / `Keyword_Analysis` / `Competitor_Matrix` / `Review_Analysis` / `Data_Quality`
- 产品规划：`product_plan_<ts>.xlsx`，6 个 Sheet：`Product_Positioning` / `Product_Features` / `Differentiation` / `Cost_Target` / `Development_Timeline` / `Risks_Validation`
- 首行冻结；列宽自动（上限 60 字符）；`Decimal` → `float` 在 Excel 边界转换（有精度损失，JSON/Markdown 保留完整 `Decimal` 精度）

## Amazon 利润测算口径

利润公式（`src/modules/amazon/profit_agent.py`）：

```
total_variable_cost_per_unit = unit_cost + inbound_shipping + international_shipping
                              + customs_duty + fba_fee + referral_fee + storage_fee
                              + advertising_cost + return_cost + other_variable_cost
unit_profit   = selling_price - total_variable_cost_per_unit
unit_margin   = unit_profit / selling_price    (selling_price <= 0 时为 0)
monthly_profit = unit_profit * estimated_monthly_units - monthly_fixed_cost
annualized_profit = monthly_profit * 12
roi           = annualized_profit / initial_investment
                (initial_investment <= 0 或 monthly_profit <= 0 时为 null)
```

13 个成本字段：`selling_price`、`unit_cost`、`inbound_shipping`、`international_shipping`、`customs_duty`、`fba_fee`、`referral_fee`、`storage_fee`、`advertising_cost`、`return_cost`、`other_variable_cost`、`fixed_development_cost`、`initial_investment` + `estimated_monthly_units`、`monthly_fixed_cost`。

金额保留 2 位小数（`_q2`）；比率保留 4 位小数（`_q4`），Decimal 量化逻辑复制自 v1/v2 `profit_calculator.py`（已记录来源血缘）。

## 三种情景

`--scenario` 选择 `base`（默认）/ `optimistic` / `pessimistic` / `all`。9 个 Amazon 专用情景乘数在 `config/amazon_workflow.json:scenarios` 中定义：

| 乘数 | base | optimistic | pessimistic |
| --- | --- | --- | --- |
| `selling_price_multiplier` | 1.0 | 1.10 | 0.88 |
| `units_multiplier` | 1.0 | 1.25 | 0.70 |
| `unit_cost_multiplier` | 1.0 | 0.92 | 1.12 |
| `fba_fee_multiplier` | 1.0 | 0.95 | 1.10 |
| `referral_fee_multiplier` | 1.0 | 1.0 | 1.0 |
| `storage_fee_multiplier` | 1.0 | 0.90 | 1.20 |
| `advertising_cost_multiplier` | 1.0 | 0.85 | 1.30 |
| `return_cost_multiplier` | 1.0 | 0.80 | 1.40 |
| `fixed_development_cost_multiplier` | 1.0 | 1.0 | 1.10 |

情景只改变经济收益部分，不改变需求/战略/交付评分。`--scenario all` 时三情景并列计算与展示。亏损情景（`monthly_profit <= 0`）的 `roi` 为 `null`。

## V3 运行示例

### 基本用法（默认基准情景，使用模拟数据）

```bash
python -m src.modules.amazon.workflow --input data/amazon/demo_product_input.json
```

### 完整用法（三情景 + 中间产物 + 严格模式）

```bash
python -m src.modules.amazon.workflow \
  --input data/amazon/demo_product_input.json \
  --scenario all \
  --with-mock-data \
  --export-intermediate \
  --strict
```

### V3 CLI 参数

| 参数 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--input` | 是 | - | 产品输入 JSON 路径 |
| `--output-dir` | 否 | `data/amazon/output` | 输出目录 |
| `--config` | 否 | `config/amazon_workflow.json` | 配置文件路径 |
| `--scenario` | 否 | `base` | `base` / `optimistic` / `pessimistic` / `all` |
| `--with-mock-data` | 否 | `True` | 用模拟数据填充缺失字段（默认） |
| `--no-mock-data` | 否 | - | 禁用模拟数据填充 |
| `--export-intermediate` | 否 | `False` | 每个 Agent 写一个 JSON 到 `intermediate/` |
| `--strict` | 否 | `False` | 严格模式，任一 Agent 失败即中止 |
| `--help` | 否 | - | 显示帮助 |

非法 `--scenario` 值返回退出码 2；配置加载失败返回 2；输入加载失败返回 2；`final_status=failed` 返回 1；其余返回 0。

## V3 输出文件

输出目录默认 `data/amazon/output/`，文件名带时间戳（`%Y%m%d_%H%M%S`，与 v1/v2 一致）：

- Markdown 报告：`amazon_product_report_<ts>.md`（17 节锁定顺序）
- JSON 结果：`amazon_product_analysis_<ts>.json`
- 市场报告：`market_report_<ts>.xlsx`（需 openpyxl）
- 产品规划：`product_plan_<ts>.xlsx`（需 openpyxl）
- 中间产物（`--export-intermediate`）：`intermediate/<order>_<agent>_<ts>.json`（如 `01_keyword_<ts>.json`），跳过的 Agent 写 `{"status":"skipped"}` 占位

### Markdown 报告 17 节（V3 锁定顺序）

1. 执行摘要 / 2. 输入信息 / 3. 工作流执行状态 / 4. 数据来源与可信度 / 5. 关键词分析 / 6. 市场分析 / 7. 竞品矩阵 / 8. Review 痛点分析 / 9. 产品机会判断 / 10. 产品开发规划 / 11. Amazon 利润测算 / 12. 三种情景比较 / 13. 风险和验证计划 / 14. 人工复核事项 / 15. 最终建议 / 16. 数据限制和免责声明 / 17. 可追溯信息

可追溯信息包括：输入文件 SHA-256、配置 SHA-256、工作流版本、测算版本、Agent 版本、生成时间、Python 版本、CLI 参数、Agent 顺序、`final_status`。JSON 顶层键：`metadata` / `command` / `source` / `config_snapshot` / `data_quality` / `summary` / `rankings` / `scenarios` / `sensitivity` / `opportunities` / `warnings` / `agents`。`Decimal` 经 `AmazonDecimalEncoder` 序列化为字符串。

## V3 测试

运行全部测试（v1 + v2 + v3）：

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

预期 191 个测试全部通过（v1/v2 共 99 个 + V3 共 92 个）。V3 测试文件：

- `tests/_amazon_helpers.py` — 测试夹具（`make_product_input` / `make_competitor_row` / `make_review_row` / `make_amazon_profit_input`）
- `tests/test_amazon_config.py` — 配置加载、缺失/非法配置、权重和=100
- `tests/test_amazon_models.py` — dataclass 往返、`AmazonDecimalEncoder`
- `tests/test_amazon_input_loader.py` — Case 1/2/3（JSON 读取、缺 keyword、非法 marketplace）、Case 6/7（竞品 CSV、ASIN 来源标记）
- `tests/test_amazon_mock_data.py` — Case 4/5/10（关键词稳定、市场字段完整、模拟数据 confidence 非 high）
- `tests/test_amazon_profit.py` — Case 12/13/14/15（基准月利 157.00、FBA+广告入成本、三情景相异、亏损 ROI 为 null）
- `tests/test_amazon_keyword_agent.py` — Case 4（关键词 Agent 输出稳定）
- `tests/test_amazon_market_agent.py` — Case 5（市场 Agent 字段完整）
- `tests/test_amazon_competitor_agent.py` — Case 6/7（竞品 CSV、ASIN 标记保留）
- `tests/test_amazon_review_agent.py` — Case 8（12 条评论分类：installation=3/quality=5/packaging=2/feature_request=2/price=4/shipping=2/customer_service=0）
- `tests/test_amazon_opportunity_agent.py` — Case 9/10/11（评分 4/3/4/5、模拟数据 confidence 非 high、Product Agent 缺前置则降级）
- `tests/test_amazon_master_report_excel.py` — Case 16-27（Master 调度、失败语义、MD 17 节、JSON 键、Excel 5+6 Sheet、输入/配置哈希、无网络/无 Key、v1/v2 兼容）

Excel 相关测试用 `@unittest.skipUnless(openpyxl_available, ...)` 跳过。

## V3 未来 API 集成方向

V3 保留了干净接缝，未来接入真实数据时：

- 用真实 SP-API / Ads API 调用替换 `src/modules/amazon/mock_data.py`（数据提供层）
- Agent 逻辑（关键词/市场/竞品/评论/机会/产品/利润）无需改动
- 配置中 `confidence_rules` 可将 `imported_csv` 等来源调到 `high`
- 报告/Excel 输出层无需改动

## V3 当前限制

- 所有市场数据为模拟/假设，非真实亚马逊数据。
- 无真实搜索量、销量估计、评论抓取（需未来接入 SP-API / Helium 10 等）。
- 未纳入税费、融资成本、现金流时间价值、汇率风险。
- 情景参数只是可配置假设。
- 人工复核仍是必要环节，系统建议不可作为最终商业决策。
- Excel 在 `Decimal` → `float` 转换时有精度损失（JSON/Markdown 保留完整精度）。
- V3 不实现敏感性分析（v2 的敏感性分析保留在 v1/v2 工作流中）。

---

# V3.1 — 市场调研与产品开发工作流（Excel 导入 + URL + 候选确认）

V3.1 在 V3 的 9 Agent 管道之上，新增**真实 Excel 数据导入**（卖家精灵 / Brand Analytics 导出）、**多关键词多类目分析**、**用户指定公开 URL 抓取**、**产品候选人工确认门禁**，形成从市场调研到产品开发的完整闭环。

> **核心设计**：V3.1 不修改 V3 的任何 Agent 或 `src/core/agent.py`。它通过 `V31Workflow` 编排器组合 V3.1 子系统（导入、分析、URL、候选）与 V3 的 `MasterAgent`。未确认候选时，产品开发与利润测算被门禁阻断；确认后，每个候选作为一个 `ProductInput` 输入 V3 `MasterAgent`，复用其产品规划与利润计算。

## V3.1 与 V3 的关系

| 维度 | V3 | V3.1 |
| --- | --- | --- |
| 数据来源 | 确定性模拟数据 / 用户 JSON | **卖家精灵/Brand Analytics Excel** + 用户 JSON + 可选公开 URL |
| 关键词 | 单关键词输入 | **多关键词 Excel 导入 + 机会评分排序** |
| 类目 | 无 | **多类目对比分析** |
| 竞品 | 模拟 4 个 | **Excel 导入商品，按 ASIN 去重，保留父子关系** |
| 搜索位置 | 无 | **搜索曝光记录保留（不去重），生成关键词×ASIN 矩阵** |
| URL | 禁止网络 | **`--allow-url-fetch` 开启后抓取用户指定公开 URL** |
| 产品开发 | 直接生成 | **候选 → 人工确认门禁 → 产品开发（未确认则门禁关闭）** |
| 报告 | MD + JSON + 2 Excel | **市场调研 Excel（9 Sheet）+ 工作流 MD + JSON** |
| 测试 | 92 个 V3 测试 | **+ 384 个 V3.1 测试（共 587）** |

## V3.1 子版本交付

| 子版本 | 内容 | 关键模块 |
| --- | --- | --- |
| V3.1.1 | Excel 文件识别 + 表头映射 | `importers/workbook_detector.py`、`column_aliases.py`、8 个 loader |
| V3.1.2 | 标准化数据模型 + ASIN 去重 | `importers/normalized_models.py`、`normalizer.py` |
| V3.1.3 | 多关键词/类目/品牌/卖家/搜索位置分析 | `analyzers/` 6 个分析器 |
| V3.1.4 | 通用市场调研模板 + 产品开发模板 | `template_builder.py` |
| V3.1.5 | URL 注册 + 默认关闭 + `--allow-url-fetch` | `url_sources/` 6 个模块 |
| V3.1.6 | 产品候选人工确认门禁 | `product_candidate_agent.py` |
| V3.1.7 | 工作流编排器（集成 V3.1 + V3 MasterAgent） | `v31_workflow.py` |
| V3.1.8 | Markdown + JSON + Excel 完整报告 + README | `v31_workflow._write_reports()` |

## V3.1 工作流管道

`V31Workflow.run()` 按以下顺序执行：

1. **Excel 加载** — `detect_workbook` 识别文件类型，分发到对应 loader（products / search / keyword / category / brand / sellers / market）
2. **标准化** — 商品按 ASIN 去重（保留父子关系），搜索曝光不去重
3. **分析** — 多关键词排序、多类目对比、品牌集中度（CR4/CR8/HHI）、卖家集中度、搜索位置矩阵
4. **URL 抓取**（可选） — 仅当 `--allow-url-fetch` 开启；仅抓取用户在 JSON 中明确提供的公开 URL
5. **市场调研报告** — 始终生成 9 Sheet Excel（即使无候选确认）
6. **产品候选** — 从关键词排序生成候选（市场证据字段，不含供应商/成本/SKU）
7. **确认门禁** — 无已确认候选则门禁关闭，产品/利润不运行
8. **产品 + 利润**（仅门禁开启） — 每个已确认候选调用 V3 `MasterAgent`
9. **报告输出** — 写 Markdown + JSON 报告

## 数据来源优先级

`user_input` > `imported_excel` > `fetched_url` > `calculated` > `agent_inference` > `mock_data`

所有关键字段记录 `value / source_type / source_file / source_sheet / source_row / source_url / confidence / calculation_method / requires_review`。

## 产品候选人工确认门禁

每个候选初始状态为 `pending_review`。用户需通过 `confirmed_candidate_ids` 指定已确认候选 ID。

- **门禁关闭**（无已确认候选）：市场调研报告仍生成，产品开发规划与利润测算不生成，报告标注 `pending_manual_confirmation`
- **门禁开启**（至少一个已确认候选）：每个已确认候选运行 V3 MasterAgent，产出产品规划与利润测算

候选状态机：`pending_review` → `confirmed` / `rejected`，`rejected` 不可直接 `confirmed`（需先 `reset`）。

## URL 抓取规则

- **默认关闭**：不设置 `--allow-url-fetch` 时不访问任何 URL
- **仅用户提供的 URL**：从 `user_input.urls` / `product_candidates` / `supplier_information` 读取
- **仅公开页面**：支持 Amazon 商品/搜索/类目/品牌页、1688 商品页；禁止登录、Cookie、Token、绕过验证码
- **失败不伪造**：URL 失败记录 URL、HTTP 状态、错误信息，不生成虚假字段
- **可测试**：`UrlFetcher` 支持注入 `transport` 回调，测试无需网络

## V3.1 输出文件

输出目录 `data/output/`，文件名带时间戳：

- 市场调研报告（Excel）：`{project_name}_market_research_report_{ts}.xlsx`（9 Sheet）
- 工作流报告（Markdown）：`{project_name}_v31_workflow_{ts}.md`（10 节）
- 工作流结果（JSON）：`{project_name}_v31_workflow_{ts}.json`

### 市场调研 Excel 9 Sheet

`类目分析_Category_Analysis` / `市场分析_Market_Analysis` / `关键词分析_Keyword_Analysis` / `竞品明细_Competitor_Detail` / `品牌分析_Brand_Analysis` / `卖家分析_Seller_Analysis` / `搜索位置分析_Search_Position` / `数据质量_Data_Quality` / `来源和追溯_Source_Traceability`

### 工作流 Markdown 10 节

1. 执行摘要 / 2. 项目信息 / 3. 分析器结果概览 / 4. 产品候选列表 / 5. 候选确认门禁状态 / 6. 产品开发规划 / 7. 利润测算结果 / 8. 警告与错误 / 9. 输出文件清单 / 10. 可追溯信息

## V3.1 用法示例

```python
from pathlib import Path
from modules.amazon.v31_workflow import V31Workflow
from modules.amazon.amazon_config import load_amazon_config

config = load_amazon_config()

# 门禁关闭：生成市场调研 + 候选列表，不生成产品规划
wf = V31Workflow(
    project_name="家禽护理调研",
    excel_files=[Path("data/raw/keyword_analysis.xlsx"), Path("data/raw/products.xlsx")],
    config=config,
    output_dir=Path("data/output"),
)
result = wf.run()
print(result.candidate_gate_status)  # "closed"

# 门禁开启：确认 PC-0001 后运行产品开发 + 利润测算
wf2 = V31Workflow(
    project_name="家禽护理调研",
    excel_files=[Path("data/raw/keyword_analysis.xlsx")],
    config=config,
    output_dir=Path("data/output"),
    confirmed_candidate_ids=["PC-0001"],
)
result2 = wf2.run()
print(result2.candidate_gate_status)  # "open"
print(len(result2.product_plans))    # 1
```

启用 URL 抓取（仅用户提供的公开 URL）：

```python
wf = V31Workflow(
    project_name="带URL的调研",
    excel_files=[],
    user_input={"urls": [{"url": "https://www.amazon.com/dp/B0DNVW368Z"}]},
    config=config,
    cli_args={"allow_url_fetch": True},
    output_dir=Path("data/output"),
)
```

## V3.1 测试

运行全部测试：

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

预期 587 个测试全部通过。V3.1 测试文件：

- `tests/test_amazon_importers.py` — Excel 识别、表头映射、8 个 loader
- `tests/test_amazon_normalizer.py` — ASIN 去重、搜索曝光保留
- `tests/test_amazon_analyzers.py` — 多关键词/类目/品牌/卖家/搜索位置
- `tests/test_amazon_template_builder.py` — 模板提取、报告生成
- `tests/test_amazon_url_sources.py` — URL 策略、分类、抓取、解析
- `tests/test_amazon_product_candidate.py` — 候选生成、状态机、门禁
- `tests/test_amazon_v31_workflow.py` — 工作流编排、报告输出

## V3.1 当前限制

- Excel 导入依赖 openpyxl（懒加载，未安装时 loader 返回空）。
- URL 抓取仅解析公开页面的有限字段，不登录、不绕过限制。
- 候选产品机会评分基于导入的关键词数据，无数据时候选列表为空。
- 产品开发规划复用 V3 MasterAgent，其竞品/评论数据仍为模拟（除非用户提供 CSV）。
- 所有分析结论需人工复核，系统不可作为最终商业决策依据。

