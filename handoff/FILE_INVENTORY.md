# FILE_INVENTORY — 文件清单

> 列出重要文件（路径/职责/状态/可否修改/依赖/风险），不只列目录。

---

## 标记说明

- **禁止修改**: 受保护文件，未经用户明确授权不得修改
- **谨慎修改**: 核心文件，修改需说明原因并保留测试基线
- **可修改**: 普通业务代码、测试、文档

---

## 顶层配置与文档

| 路径 | 职责 | 状态 | 可否修改 | 依赖 | 风险 |
|---|---|---|---|---|---|
| [requirements.txt](file:///requirements.txt) | 依赖声明（仅 `openpyxl>=3.1.0`） | DONE | 可修改 | 无 | 无 pyproject.toml/setup.py |
| [.env.example](file:///.env.example) | 环境变量样例（OUTPUT_DIR/SCORING_VERSION/CALCULATION_VERSION） | DONE | 可修改 | 无 | 无密钥 |
| [.trae/specs/v3_2_web_backend/tasks.md](file:///.trae/specs/v3_2_web_backend/tasks.md) | V3.2 任务清单 | DONE | 可修改 | 无 | 设计文档 |
| [.trae/specs/v3_2_web_backend/spec.md](file:///.trae/specs/v3_2_web_backend/spec.md) | V3.2 规范 | DONE | 可修改 | 无 | 设计文档 |

---

## backend/ — 后端 API 与服务

| 路径 | 职责 | 状态 | 可否修改 | 依赖 | 风险 |
|---|---|---|---|---|---|
| [backend/app.py](file:///backend/app.py) | HTTP 入口 + MAIN_ROUTER | DONE | 谨慎修改 | backend/api/* | 单进程 |
| [backend/config.py](file:///backend/config.py) | 环境变量配置 | DONE | 谨慎修改 | os | 密钥只从 env 读 |
| [backend/api/__init__.py](file:///backend/api/__init__.py) | build_request/Response | DONE | 谨慎修改 | 无 | 无 |
| [backend/api/auth.py](file:///backend/api/auth.py) | 登录/登出/me | DONE | 可修改 | auth_service | 无 |
| [backend/api/projects.py](file:///backend/api/projects.py) | 项目 CRUD | DONE | 可修改 | storage | 无 |
| [backend/api/uploads.py](file:///backend/api/uploads.py) | 文件上传 + 检测 | DONE | 可修改 | file_detection | 无 |
| [backend/api/jobs.py](file:///backend/api/jobs.py) | 任务查询 + cancel | DONE | 可修改 | workflow_runner | 无 |
| [backend/api/candidates.py](file:///backend/api/candidates.py) | 候选确认/拒绝 | DONE | 可修改 | workflow_runner | 无 |
| [backend/api/manual_inputs.py](file:///backend/api/manual_inputs.py) | 人工输入 | DONE | 可修改 | storage | 无 |
| [backend/api/outputs.py](file:///backend/api/outputs.py) | 输出列表 + 下载 | DONE | 可修改 | storage | 路径穿越防护 |
| [backend/api/templates.py](file:///backend/api/templates.py) | 模板上传/绑定 | DONE | 可修改 | storage | 无 |
| [backend/api/validation.py](file:///backend/api/validation.py) | 校验规则 | DONE | 可修改 | 无 | 无 |
| [backend/api/health.py](file:///backend/api/health.py) | /api/health + /api/workflow/definition | DONE | 可修改 | config | 无 |
| [backend/services/auth_service.py](file:///backend/services/auth_service.py) | 邀请码/Session/CSRF/RateLimit | DONE | 谨慎修改 | storage | 安全核心 |
| [backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py) | WorkflowRunner + Phase 1/2 + cancel | DONE | 谨慎修改 | job_store/storage | 工作流核心 |
| [backend/services/url_security.py](file:///backend/services/url_security.py) | SSRF 防护 + DNS + 重定向 | DONE | 谨慎修改 | urllib | 安全核心 |
| [backend/services/file_detection.py](file:///backend/services/file_detection.py) | 文件类型检测 | DONE | 可修改 | 无 | 无 |
| [backend/storage/base.py](file:///backend/storage/base.py) | CancellationToken + 抽象基类 | DONE | 谨慎修改 | 无 | 取消机制核心 |
| [backend/storage/local_storage.py](file:///backend/storage/local_storage.py) | LocalStorageBackend | DONE | 可修改 | 文件系统 | 本地限 |
| [backend/storage/job_store.py](file:///backend/storage/job_store.py) | LocalJobStore + SQLite schema | DONE | 谨慎修改 | sqlite3 | 本地限 |
| [backend/storage/database.py](file:///backend/storage/database.py) | configure_paths + 单例 | DONE | 谨慎修改 | job_store/local_storage | 无 |

---

## frontend/ — 前端工作台

| 路径 | 职责 | 状态 | 可否修改 | 依赖 | 风险 |
|---|---|---|---|---|---|
| [frontend/index.html](file:///frontend/index.html) | 入口 HTML | DONE | 可修改 | app.js/api.js | 无 |
| [frontend/app.js](file:///frontend/app.js) | 主逻辑 + 动态 Agent 渲染 | DONE | 可修改 | api.js | 硬编码 Agent 顺序禁止 |
| [frontend/api.js](file:///frontend/api.js) | API 调用封装 | DONE | 可修改 | 无 | 无 |
| [frontend/styles.css](file:///frontend/styles.css) | 样式 | DONE | 可修改 | 无 | 无 |

---

## deploy/ — 部署适配

| 路径 | 职责 | 状态 | 可否修改 | 依赖 | 风险 |
|---|---|---|---|---|---|
| [deploy/veFaaS/handler.py](file:///deploy/veFaaS/handler.py) | veFaaS API Handler（真实可用） | DONE | 可修改 | backend/app | 不含后台线程 |
| [deploy/veFaaS/worker_handler.py](file:///deploy/veFaaS/worker_handler.py) | veFaaS Worker Handler（**骨架**） | PARTIAL | 可修改 | 无 | 真实队列未接入 |
| [deploy/tos/static_hosting.md](file:///deploy/tos/static_hosting.md) | TOS 静态托管文档 | DONE | 可修改 | 无 | 仅文档 |
| [deploy/api_gateway/routes.md](file:///deploy/api_gateway/routes.md) | API Gateway 路由文档 | DONE | 可修改 | 无 | 仅文档 |

---

## src/modules/amazon/ — V3.1 工作流业务

| 路径 | 职责 | 状态 | 可否修改 | 依赖 | 风险 |
|---|---|---|---|---|---|
| [src/modules/amazon/v31_workflow.py](file:///src/modules/amazon/v31_workflow.py) | V31Workflow 主类 | DONE | 谨慎修改 | 各子模块 | 含 template_path 参数 |
| [src/modules/amazon/importers/detector.py](file:///src/modules/amazon/importers/detector.py) | 文件检测 | DONE | 可修改 | openpyxl | 无 |
| [src/modules/amazon/template_builder.py](file:///src/modules/amazon/template_builder.py) | 模板处理 | PARTIAL | 可修改 | openpyxl | 保真未逐项验证 |
| 其他 analyzer/url_sources/product_candidate_agent/master_agent 等 | 子模块 | DONE | 可修改 | 无 | 无 |

---

## src/core/ — 核心占位符

| 路径 | 职责 | 状态 | 可否修改 | 依赖 | 风险 |
|---|---|---|---|---|---|
| [src/core/agent.py](file:///src/core/agent.py) | 核心占位符 | DONE | **禁止修改** | 无 | 受保护 |

> **禁止修改：src/core/agent.py**
> 除非用户明确授权，否则 GPT-5.6-terra 不应修改该文件。

---

## tests/ — 测试套件

| 路径 | 职责 | 状态 | 可否修改 | 依赖 | 风险 |
|---|---|---|---|---|---|
| [tests/](file:///tests/) | 38 个测试文件，699 个用例 | DONE（699/699 pass） | 可修改 | backend/src | 无 |
| [tests/test_cross_user_isolation.py](file:///tests/test_cross_user_isolation.py) | 双用户双 Session 隔离（25） | DONE | 可修改 | backend | 无 |
| [tests/test_ssrf_dns.py](file:///tests/test_ssrf_dns.py) | DNS/重定向 SSRF（9） | DONE | 可修改 | backend | 无 |
| [tests/test_task_cancellation.py](file:///tests/test_task_cancellation.py) | 任务取消（16） | DONE | 可修改 | backend | 无 |
| [tests/test_phase2_checkpoint.py](file:///tests/test_phase2_checkpoint.py) | Phase 2 checkpoint（15） | DONE | 可修改 | backend | 无 |
| [tests/test_manual_inputs_empty.py](file:///tests/test_manual_inputs_empty.py) | 人工输入空值（5） | DONE | 可修改 | backend | 无 |
| [tests/test_download_security.py](file:///tests/test_download_security.py) | 下载安全（6） | DONE | 可修改 | backend | 无 |
| [tests/test_template_integration.py](file:///tests/test_template_integration.py) | 模板集成（6） | DONE | 可修改 | backend | 无 |
| 其他 31 个测试文件 | V3.1 + 既有用例 | DONE | 可修改 | 无 | 无 |

---

## data/ — 数据目录

| 路径 | 职责 | 状态 | 可否修改 | 依赖 | 风险 |
|---|---|---|---|---|---|
| [data/output/](file:///data/output/) | 报告输出（带时间戳） | DONE | 可追加 | 无 | 不覆盖历史 |
| [data/web_storage/](file:///data/web_storage/) | 用户上传文件 | DONE | 可追加 | 无 | 本地限 |
| [data/web.db](file:///data/web.db) | SQLite 数据库 | DONE | 自动生成 | sqlite3 | 本地限，不入交接包 |

---

## 现有报告和交付文档

| 路径 | 职责 | 状态 | 可否修改 | 依赖 | 风险 |
|---|---|---|---|---|---|
| 上一轮交付报告 | V3.2 本地功能补齐报告 | DONE | 可修改 | 无 | 历史文档 |
| [examples/v312-v318](file:///examples/) 共 7 个 demo | V3.1 各子版本示例 | DONE | 可修改 | 无 | 无 |

---

## handoff/ — 本交接包

| 路径 | 职责 | 状态 | 可否修改 | 依赖 | 风险 |
|---|---|---|---|---|---|
| [handoff/README.md](file:///handoff/README.md) | 入口说明 | DONE | 可修改 | 无 | 无 |
| [handoff/PROJECT_STATUS.md](file:///handoff/PROJECT_STATUS.md) | 功能状态 | DONE | 可修改 | 无 | 无 |
| [handoff/ARCHITECTURE.md](file:///handoff/ARCHITECTURE.md) | 真实架构 | DONE | 可修改 | 无 | 无 |
| [handoff/FILE_INVENTORY.md](file:///handoff/FILE_INVENTORY.md) | 文件清单（本文件） | DONE | 可修改 | 无 | 无 |
| 其他 10 份文件 | 见 README.md | DONE | 可修改 | 无 | 无 |

---

## 禁止修改清单

```
禁止修改：src/core/agent.py
```

## 谨慎修改清单（需说明原因 + 保留测试基线）

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
