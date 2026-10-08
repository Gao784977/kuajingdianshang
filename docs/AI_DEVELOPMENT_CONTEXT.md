# AI_DEVELOPMENT_CONTEXT — AI 编程代理交接说明

```text
当前文档只描述工程约定，不代表所有业务功能已经完成。
AI 编程代理必须以当前源代码、测试和实际命令输出为准。
开始修改前必须检查 git status，并保留现有用户修改。
```

本文件为 AI 编程代理（如 GPT-5.6-terra）提供项目上下文，让其快速理解项目并继续开发。

## 1. 项目目标

**Amazon 选品机会分析工具（V3.2）**：基于 Python 标准库的亚马逊市场调研与产品开发规划工具，支持 Excel/CSV/JSON 输入、多 Agent 工作流、双阶段（Phase 1 调研 / Phase 2 开发）执行、模板化报告生成。V3.2 增加本地 Web 后端、用户隔离、邀请码登录、异步任务、断点恢复和 veFaaS 部署适配骨架。

更详细的工程状态见 [handoff/](handoff/) 目录的 14 份交接文件。

## 2. 目录结构

```
项目根/
├── backend/            # V3.2 Web 后端（API、服务、存储）
│   ├── api/            # HTTP 接口
│   ├── services/       # 业务服务（auth, workflow_runner, url_security）
│   ├── storage/        # LocalJobStore, LocalStorageBackend
│   ├── app.py          # HTTP 入口
│   └── config.py       # 环境变量读取（唯一读取 .env 的地方）
├── frontend/           # 静态前端工作台（HTML/JS/CSS，无构建）
├── src/
│   ├── core/
│   │   └── agent.py    # 占位符【禁止修改】
│   └── modules/
│       ├── analyze_opportunities.py  # V1/V2 CLI
│       └── amazon/                  # V3/V3.1 工作流
│           ├── v31_workflow.py       # V31Workflow 编排器
│           ├── importers/            # Excel 导入
│           ├── analyzers/            # 多关键词/类目/品牌/卖家分析
│           ├── url_sources/          # URL 抓取（默认关闭）
│           └── ...
├── tests/              # 38 个测试文件，699 个用例
├── config/             # 评分规则、Amazon 工作流配置
├── data/               # 本地数据（不入 Git，除固定样例外）
│   ├── raw/            # 固定 CSV 样例【入 Git】
│   ├── amazon/         # Amazon 固定样例和模板【入 Git】
│   ├── web.db          # 本地 SQLite【不入 Git】
│   ├── web_storage/    # 用户上传【不入 Git】
│   └── output/         # 生成报告【不入 Git】
├── deploy/             # veFaaS 部署适配（handler 真实可用，worker 骨架）
├── docs/               # 本目录：多端开发、本地初始化、Git 设置、AI 上下文
├── handoff/            # 工程交接包（14 份文件）
├── scripts/            # 本地初始化、环境检查、数据重置脚本
├── requirements.txt    # 依赖：仅 openpyxl>=3.1.0（可选）
├── .env.example        # 环境变量模板【入 Git】
├── .gitignore          # Git 忽略规则
├── README.md           # 项目入口文档
└── CONTRIBUTING.md     # 贡献规范
```

## 3. 启动命令

```bash
# 安装依赖（可选 openpyxl，未安装时 Excel 输出跳过）
python -m pip install -r requirements.txt

# 启动 Web 后端（默认 0.0.0.0:8000，建议本机开发设 HOST=127.0.0.1）
python -m backend.app
```

访问 `http://127.0.0.1:8000/`，首次需用 `ADMIN_BOOTSTRAP_TOKEN` 登录创建邀请码。

## 4. 测试命令

```bash
# 全量测试
python -m unittest discover -s tests -p "test_*.py"

# 详细输出
python -m unittest discover -s tests -p "test_*.py" -v
```

基线：699 个用例全部通过。

## 5. CLI 冒烟命令

```bash
python -m src.modules.analyze_opportunities --help     # V1/V2 CLI
python -m src.modules.amazon.workflow --help           # V3/V3.1 CLI
```

两者均应 exit 0。

## 6. 配置来源

- **环境变量**：[backend/config.py](../backend/config.py) 是唯一读取 `.env` 的地方。变量名清单见 [.env.example](../.env.example)。
- **评分规则**：`config/opportunity_config.json`（V1/V2）
- **Amazon 工作流**：`config/amazon_workflow.json`（V3/V3.1）
- **工作流定义**：[backend/config.py](../backend/config.py) 的 `WORKFLOW_DEFINITION` 字典（前端 Agent 顺序的唯一来源，禁止硬编码到前端）

## 7. 本地数据位置

| 类别 | 路径 | 说明 |
| --- | --- | --- |
| SQLite 数据库 | `data/web.db` | 自动创建，不入 Git |
| 用户上传 | `data/web_storage/` | 不入 Git |
| 报告输出 | `data/output/` | 带时间戳，不入 Git |
| Amazon 输出 | `data/amazon/output/` | 带时间戳，不入 Git |
| 日志 | `logs/` | 不入 Git |
| 临时文件 | `temp/` | 不入 Git |

## 8. 不应修改的文件

**禁止修改**（除非用户明确授权）：

```
src/core/agent.py
```

**谨慎修改**（需说明原因并保留测试基线）：

```
backend/app.py
backend/config.py
backend/api/__init__.py
backend/services/auth_service.py
backend/services/workflow_runner.py
backend/services/url_security.py
backend/storage/base.py
backend/storage/job_store.py
backend/storage/database.py
src/modules/amazon/v31_workflow.py
```

详见 [handoff/FILE_INVENTORY.md](handoff/FILE_INVENTORY.md)。

## 9. 当前已知问题

详见 [handoff/KNOWN_ISSUES.md](handoff/KNOWN_ISSUES.md)。摘要：

- **P0**: 0 个
- **P1**: 5 个（双用户隔离测试、SSRF DNS mock、跨用户下载测试、模板保真逐项比较、浏览器完整端到端验证）
- **P2**: 若干（生产队列、生产数据库、TOS、多实例、监控）

## 10. 当前未完成的功能

详见 [handoff/NEXT_TASKS.md](handoff/NEXT_TASKS.md) 和 [handoff/PROJECT_STATUS.md](handoff/PROJECT_STATUS.md)：

- 生产数据库未接入
- TOS 未接入
- 真实异步队列未接入
- veFaaS Worker 仅为骨架
- 模板保真逐项比较测试未完成
- 浏览器完整端到端验证未完成（3 步 NOT VERIFIED）

## 11. 修改前必须执行的检查

1. `git status` — 确认工作区状态，保留用户未提交修改
2. `python -m unittest discover -s tests -p "test_*.py"` — 建立测试基线
3. 阅读相关 [handoff/](handoff/) 文件，理解当前状态
4. 检查 [CONTRIBUTING.md](CONTRIBUTING.md) 的分支规范

## 12. 修改后必须执行的测试

1. `python scripts/check_environment.py` — 环境检查
2. `python -m unittest discover -s tests -p "test_*.py"` — 全量测试
3. `python -m src.modules.analyze_opportunities --help` — V1/V2 CLI 冒烟
4. `python -m src.modules.amazon.workflow --help` — V3 CLI 冒烟
5. 测试数量必须 ≥ 基线（当前 699）。新增功能必须新增测试。

## 13. 多端开发注意事项

- 详见 [docs/MULTI_DEVICE_DEVELOPMENT.md](MULTI_DEVICE_DEVELOPMENT.md) 和 [docs/LOCAL_SETUP.md](LOCAL_SETUP.md)
- 每台电脑使用独立的 `.env` 和本地数据
- 不要把 `data/web.db`、`data/web_storage/`、`data/output/` 提交到 Git
- 不要把 `.env` 提交到 Git
- 切换电脑时使用 `git pull --rebase`，不复制本地数据

## 14. 哪些文件可以提交

- 源代码：`src/`, `backend/`, `frontend/`
- 测试：`tests/`
- 配置模板：`.env.example`, `config/*.json`
- 固定测试样例：`data/raw/`, `data/amazon/demo_*`, `data/amazon/templates/`
- 文档：`README.md`, `CONTRIBUTING.md`, `docs/`, `handoff/`
- 脚本：`scripts/`
- 依赖锁定：`requirements.txt`
- 部署骨架：`deploy/`

## 15. 哪些文件绝不能提交

- `.env`（含密钥）
- `data/web.db`, `data/web.db-wal`, `data/web.db-shm`（本地数据库）
- `data/web_storage/`（用户上传）
- `data/output/`（生成报告，带时间戳）
- `data/amazon/output/`（Amazon 生成报告）
- `.venv/`, `venv/`（虚拟环境）
- `__pycache__/`, `*.pyc`（缓存）
- `logs/`（日志）
- `temp/`（临时文件）
- 真实密钥、Access Key、Secret Key、Cookie、Session、Token

`.gitignore` 已经覆盖以上所有路径。如新增本地运行时数据，请同步更新 `.gitignore`。
