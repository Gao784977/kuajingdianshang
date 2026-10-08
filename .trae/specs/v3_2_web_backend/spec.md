# V3.2 Web 端与 veFaaS 部署 - Product Requirements Document

## Overview
- **Summary**: 在现有 V3.0/V3.1 Amazon 产品开发工作流基础上，新增一个简单可用的 HTML Web 端（浏览器操作）和 Python 后端 API，并为后续部署到火山引擎 veFaaS 做好准备。
- **Purpose**: 让用户和朋友通过浏览器而非命令行完成 Amazon 产品调研全流程（创建项目、上传 Excel/CSV/JSON、输入关键词/类目/URL、查看 Agent 进度、确认产品候选、下载报告）。
- **Target Users**: 产品开发人员及其朋友（多人通过浏览器使用，需基本访问保护与用户隔离）。

## Goals
- 提供一个本地可运行的 HTML + CSS + JS 前端页面，覆盖从创建项目到下载报告的完整流程。
- 提供一个 Python 后端 API，复用现有 `src/modules/amazon/v31_workflow.py` 工作流，不重写业务逻辑。
- 实现异步任务执行（本地后台线程 + 轮询），不让 HTTP 请求等待完整分析结束。
- 实现 **WorkflowCheckpoint** 两阶段工作流：Phase 1（调研到候选）完成后保存断点，候选确认后 Phase 2 从断点继续，不重复执行前置 Agent。
- 实现产品候选人工确认门禁：只有至少一个 `confirmed` 候选才允许继续产品开发。
- 实现用户访问保护（独立邀请码 + Session，用户隔离）。
- 实现文件上传/下载安全（SHA-256、路径穿越防护、白名单扩展、归属校验）。
- 实现模板上传、绑定、校验与保真填充（市场调研模板、产品开发规划模板）。
- 实现 URL 访问安全（SSRF 防护含 DNS 解析后 IP 校验、默认关闭、失败不伪造数据）。
- 实现任务协作式取消（CancellationToken）。
- 准备 veFaaS 部署文件（API Handler、Worker Handler、requirements、function.yaml、env.example、API Gateway 路由、TOS 静态托管说明）。
- 保留全部现有 V1/V2/V3/V3.1 功能和测试，现有 CLI 继续可用。

## Non-Goals
- 不重写现有 Amazon 工作流（`src/modules/amazon/` 下的业务逻辑）。
- 不修改 `src/core/agent.py`。
- 不删除已有 V1/V2/V3 功能。
- 不引入 React/Vue 等复杂前端框架（第一阶段使用原生 HTML/CSS/JS）。
- 不实现完整的用户注册系统（第一阶段使用邀请码 + Session 的临时方案，但必须支持独立 user_id 隔离）。
- 不接入真实火山引擎密钥（本地开发不使用；密钥仅从环境变量读取）。
- 不在前端或 HTML 中包含任何 API Key / Access Key / Secret Key。
- 本阶段不声称已完成生产云部署（真实队列、生产数据库、TOS 仍需接入验证）。

## Background & Context
- 现有项目已完成 V3.0（9 Agent 管道）和 V3.1（Excel 导入、多关键词/类目分析、URL 抓取、产品候选门禁、Markdown/JSON/Excel 报告）。
- 现有依赖仅有 `openpyxl>=3.1.0`，其余均为 Python 标准库。
- CLI 入口为 `python -m src.modules.analyze_opportunities`。
- V3.1 工作流入口为 `src.modules.amazon.v31_workflow.V31Workflow`，其 `run()` 方法返回 `V31WorkflowResult`。
- 产品候选状态机统一为：`pending_review` → `confirmed` / `rejected`（被拒候选需 reset 才能重新确认）。**全局不使用 `approved` 状态名。**
- 文件检测按类型分流：`xlsx` → `detect_workbook()`；`csv` → `detect_csv()`；`json` → `detect_json()`。**本阶段不支持 `.xls`，上传时明确拒绝并提示转换为 `.xlsx`。**
- 沙箱环境无法 `pip install`，因此本地后端必须使用 Python 标准库（`http.server` + `sqlite3` + `threading`）。veFaaS 部署时提供 FastAPI handler 作为可选入口。

### 本地 vs 生产异步任务架构边界

**本地开发（LocalTaskRunner）**：
- SQLite 持久化任务状态
- `LocalStorageBackend` 本地文件系统存储上传/输出文件
- `LocalJobStore` SQLite 任务存储
- `threading.Thread` 后台执行工作流
- 前端每 2 秒轮询 `GET /api/jobs/{job_id}`

**生产适配（ProductionTaskRunner，接口骨架，未接入真实队列）**：
- `ProductionStorageBackend` → 对象存储（TOS）
- `ProductionJobStore` → 持久化数据库
- 异步任务消息 / 事件触发器
- veFaaS Worker Function 消费消息
- 任务重试、幂等、取消、死信处理

> **重要声明**：当前只完成 veFaaS Handler 和生产适配接口，真实队列、生产数据库和 TOS 仍需配置或接入。**不得声称生产异步已经完成。** 将数据库状态改成 `cancelled` 不等于后台任务已经停止，必须由工作流主动检查取消标记。

## Functional Requirements

### FR-1: 健康检查 API
- `GET /api/health` 返回 `{status: "ok", version: "v3.2", environment: "local"|"production"}`。

### FR-2: 工作流定义 API
- `GET /api/workflow/definition` 返回当前工作流版本和 Phase 1/Phase 2 的 Agent 顺序。
- 前端根据此接口渲染 Agent 列表，**不得在 JavaScript 中硬编码 Agent 数量或顺序**。
- 返回结构：`{workflow_version, phases:[{name, agents:[]}]}`，Phase 1 agents 为 `input_validation, workbook_detection, schema_mapping, excel_import, url_fetch, keyword, market, competitor, brand_seller, review, opportunity, product_candidate`；Phase 2 agents 为 `product_development, profit, report, excel`。

### FR-3: 项目管理 API
- `POST /api/projects` 创建项目（project_name, marketplace, keywords, categories, target_price_range, urls, manual_inputs）。
- `GET /api/projects/{project_id}` 获取项目。
- `PUT /api/projects/{project_id}` 更新项目。
- 项目归属校验：owner_id = 当前 Session 用户，用户只能查看/修改自己的项目。

### FR-4: 文件上传与类型分流检测 API
- `POST /api/projects/{project_id}/files` 多文件上传（multipart/form-data）。
- **支持类型：`xlsx`、`csv`、`json`**。**`.xls` 明确拒绝**，返回 400 并提示转换为 `.xlsx`。
- 限制大小（`MAX_UPLOAD_SIZE_MB`，默认 50MB），计算 SHA-256，保存原始文件到隔离目录（`project_id/upload_id`），返回 upload_id。
- 不使用用户文件名作为存储路径；禁止可执行文件；防路径穿越。
- `POST /api/projects/{project_id}/files/detect` 按文件类型分流：
  - `xlsx` → 调用 `detect_workbook()`
  - `csv` → 调用 `detect_csv()`
  - `json` → 调用 `detect_json()`
  - 返回 detected_type/confidence/recognized_columns/unmapped_columns/warnings
- `POST /api/projects/{project_id}/files/{upload_id}/confirm` 确认/修改文件类型。

### FR-5: 模板上传、绑定、校验与保真填充
- 支持模板类型：`market_research_template`、`product_development_template`。
- `POST /api/projects/{project_id}/templates` 上传模板；`GET` 列出；`PUT` 更新。
- 模板字段：template_id, project_id, template_type, original_name, sha256, version, validation_status, created_at。
- 模板校验：Sheet 是否存在、Sheet 名称、必需表头、文件可读性、合并单元格、样式、公式、数据验证、页面设置。
- 生成报告时：复制原始模板（不修改原模板）→ 删除示例业务数据/图片/图表 → 保留 Sheet 名称和顺序、表头、样式、公式、合并单元格、数据验证、批注、列宽、行高、冻结窗格、页面设置 → 写入分析结果 → 输出文件记录 template_id、job_id、project_id。

### FR-6: 校验 API
- `POST /api/projects/{project_id}/validate` 校验输入，返回 valid/errors/warnings/pending_manual_inputs/pending_validation。

### FR-7: 任务执行 API
- `POST /api/projects/{project_id}/jobs` 创建 Phase 1 分析任务（scenario, allow_url_fetch, export_intermediate, strict, use_mock_data），返回 job_id + queued，后台执行。
- `GET /api/jobs/{job_id}` 查询任务状态（status, current_agent, completed_agents, progress, warnings, errors, started_at, updated_at）。
- `POST /api/jobs/{job_id}/cancel` 协作式取消任务（设置 CancellationToken，工作流主动检查）。
- `GET /api/jobs/{job_id}/intermediate` 获取 Agent 中间结果。
- 前端每 2 秒轮询任务状态。

### FR-8: WorkflowCheckpoint 两阶段工作流
- Phase 1 完成后保存 `WorkflowCheckpoint`，至少包含：checkpoint_id, project_id, job_id(phase_1), workflow_version, input_sha256, config_sha256, normalized_data_reference, agent_results_reference, candidate_results, data_quality_reference, source_provenance_reference, completed_agents, current_phase, created_at, updated_at。
- Phase 1 agents：input_validation → workbook_detection → schema_mapping → excel_import → url_fetch → keyword → market → competitor → brand_seller → review → opportunity → product_candidate。
- Phase 2：读取 Phase 1 checkpoint → 读取 confirmed 候选 → 读取 manual_inputs → product_development → profit → report → excel。
- `POST /api/projects/{project_id}/continue-development` 启动 Phase 2：不重新执行 Phase 1，不重新导入 Excel，不重新访问 URL，不重新执行关键词/市场/竞品/Review 分析；保存新的 phase_2_job_id，关联 phase_1_job_id 和 phase_2_job_id。

### FR-9: 产品候选 API
- `GET /api/projects/{project_id}/candidates` 获取候选列表。
- `POST /api/projects/{project_id}/candidates/{candidate_id}/confirm` 确认候选（状态 → `confirmed`）。
- `POST /api/projects/{project_id}/candidates/{candidate_id}/reject` 拒绝候选（状态 → `rejected`）。
- **只有至少一个 `confirmed` 候选时，才允许继续产品开发。** `rejected` 候选不能进入产品开发。

### FR-10: 人工供应链信息 API
- `PUT /api/projects/{project_id}/manual-inputs` 保存供应商、采购成本、MOQ、物流、利润等人工字段。**空值保留为空，不自动填充 0 或模拟值。**

### FR-11: 输出文件 API
- `GET /api/projects/{project_id}/outputs` 列出输出文件（市场调研 Excel、产品开发规划 Excel、Markdown、JSON、中间数据、数据质量报告）。
- `GET /api/outputs/{output_id}/download` 下载：校验归属、白名单路径、防路径穿越、正确 Content-Type。

### FR-12: HTML 前端
- 单页工作台，包含区域：顶部导航、项目输入、URL 输入、文件上传、文件识别结果、模板管理、工作流控制、任务进度、产品候选、人工信息、报告下载。
- 关键词/类目支持添加、删除、编辑、空值校验、去重、回车创建标签。
- URL 支持 URL/类型/用途/启用/备注；URL 访问开关默认关闭，显示安全说明。
- **Agent 顺序从 `GET /api/workflow/definition` 动态获取，不硬编码。**
- 所有按钮防重复提交；危险操作（删除文件、删除项目、拒绝候选、取消运行中任务）需确认。
- 移动端和桌面端可用。

### FR-13: 权限与访问控制（邀请码 + Session + 用户隔离）
- `ADMIN_BOOTSTRAP_TOKEN` **只用于初始化管理员或创建邀请记录**，不作为所有用户共用的登录凭证。
- 新增 `invitations` 表：invitation_id, token_hash, max_uses, used_count, expires_at, status, created_at。
- 每个朋友通过**独立邀请码**创建独立 `user_id`；邀请码只保存哈希，支持过期时间和最大使用次数。
- 登录后创建独立 Session；后端从 Session 获取 user_id，**不信任前端传入的 user_id**。
- 项目、上传文件、任务、候选、输出都进行 owner_id 校验。
- 登录失败支持基本速率限制；Session 支持过期、注销和撤销。
- 若第一阶段只实现临时管理员邀请码，必须明确：**临时管理员邀请码不代表多人用户隔离已经完成。多人使用必须通过独立邀请码或正式账户系统实现。**

### FR-14: URL 访问安全（SSRF 含 DNS 解析后校验）
- 仅 http/https；禁止 file://。
- **DNS 解析后校验 IPv4/IPv6 地址**：禁止回环地址、私有地址、链路本地地址、保留地址、CGNAT 地址、云元数据地址（169.254.169.254 等）。
- **每次重定向后重新校验目标地址**。
- 不继承不受控的 HTTP_PROXY / HTTPS_PROXY 环境变量。
- 限制连接超时、读取超时、最大响应字节数、最大重定向次数、允许的 Content-Type。
- 记录最终 URL、HTTP 状态、content_hash、解析警告。
- URL 抓取失败时：不生成虚构数据、不覆盖 Excel 数据、保留失败状态、继续处理其他文件和 URL；strict 模式按配置失败或停止。

### FR-15: Cookie、CSRF 与 CORS
- Session Cookie：HttpOnly、明确过期时间、注销失效。
- 本地环境：`SESSION_COOKIE_SECURE=false`，`SameSite=Lax`。
- 生产环境：`SESSION_COOKIE_SECURE=true`。
- 严格 `ALLOWED_ORIGINS`，不允许 `Access-Control-Allow-Origin: *` 搭配 Cookie。
- 修改状态的 API 使用 CSRF Token 或 Origin 校验，不允许任意 Origin。

### FR-16: 任务协作式取消（CancellationToken）
- 每个 Agent 开始前检查取消标记；文件处理循环中检查；URL 请求前后检查；长时间计算中检查。
- 取消后不再生成正式输出；已生成的中间结果标记为 `partial`；最终任务状态为 `cancelled`。
- 取消事件写入 `job_events`。
- **将数据库状态改成 cancelled 不等于后台任务已经停止，必须由工作流主动检查取消标记。**

### FR-17: veFaaS 部署准备
- `deploy/veFaaS/handler.py`（API Handler）+ `worker_handler.py`（Worker Handler）作为 veFaaS 入口。
- `deploy/veFaaS/requirements.txt`、`function.yaml`、`env.example`、`README.md`。
- `deploy/api_gateway/routes.md`、`deploy/tos/static_hosting.md`。
- 密钥仅从环境变量读取；不依赖本地永久磁盘；不依赖单实例内存；输出文件支持对象存储；短期签名下载 URL。
- 生产异步适配层（`ProductionTaskRunner`）接口骨架包含：生产任务消息结构、Worker Handler、持久化任务状态、任务重试、任务幂等、任务取消、失败和死信处理、函数超时处理。
- **明确声明：当前只完成 veFaaS Handler 和生产适配接口，真实队列、生产数据库和 TOS 仍需配置或接入。**

## Non-Functional Requirements
- **NFR-1**: 本地后端使用 Python 标准库（`http.server` + `sqlite3` + `threading`），不新增第三方依赖（openpyxl 已存在）。
- **NFR-2**: 实施前先运行全量测试，记录实际基线数量 N。实施后必须保留全部基线测试，并新增 V3.2 测试。最终所有基线测试和新增测试必须通过。不修改 `src/core/agent.py`。
- **NFR-3**: 现有 CLI（`python -m src.modules.analyze_opportunities`）继续可用。
- **NFR-4**: API Key / Access Key / Secret Key 不出现在前端、HTML、日志、README 示例中。
- **NFR-5**: `.env` 加入 `.gitignore`，`.env.example` 仅使用空值或占位符。
- **NFR-6**: 存储和任务接口抽象（`StorageBackend` / `JobStore` / `TaskRunner`），允许未来替换为对象存储、持久化数据库和异步任务队列。
- **NFR-7**: 前端不直接调用任何火山引擎密钥，只访问本项目后端 API。
- **NFR-8**: Agent 顺序由 `GET /api/workflow/definition` 提供，前端不硬编码。

## Constraints
- **Technical**: 沙箱无法 pip install，本地后端必须用标准库；veFaaS handler 可使用 FastAPI。
- **Business**: 不破坏现有功能；不修改核心 Agent；密钥仅在后端。
- **Dependencies**: 复用 `V31Workflow`、`detect_workbook`、`ProductCandidateAgent`、`build_market_research_report`。
- **文件类型**: 本阶段仅支持 `xlsx`/`csv`/`json`，不支持 `xls`。

## Assumptions
- 本地开发使用 SQLite 存储项目/任务/上传/输出/邀请/Session 元数据。
- 本地开发使用文件系统存储上传文件和输出文件（按 project_id/upload_id 隔离）。
- 本地后台任务使用线程执行。
- 邀请码通过环境变量 `ADMIN_BOOTSTRAP_TOKEN` 配置管理员初始化。
- veFaaS 部署时，用户将自行配置火山引擎密钥、对象存储、数据库和异步队列。

## Open Questions
- 无（需求文档已足够详细）。

## Local vs Production Boundary

### 本地版本完成后可以声明
- HTML 前端可以运行
- Python API 可以运行
- SQLite 可以运行
- 本地文件上传可以运行
- 本地后台线程可以运行
- 本地任务轮询可以运行
- 产品候选可以确认
- 报告可以下载
- V1/V2/V3/V3.1 CLI 保持兼容

### 只有真正接入并验证以下组件后，才可以声明生产可用
- 生产数据库
- 对象存储 TOS
- 真实异步任务队列或事件触发器
- veFaaS Worker
- API Gateway
- 生产域名和 HTTPS
- 用户邀请和 Session 配置
- CORS/CSRF 配置
- 生产监控和日志
- 任务重试和失败恢复

> **README 和部署文档必须明确写**：当前版本完成本地 Web 工作台和 veFaaS 适配骨架，不代表已经完成生产云部署。

## Acceptance Criteria

### AC-1: 健康检查
- **Type**: `rule`
- **Given**: 后端服务已启动
- **When**: 发送 `GET /api/health`
- **Then**: 返回 200，JSON 包含 `status: "ok"`、`version`、`environment`
- **Pass Condition**: 响应状态码 200 且 JSON 字段正确
- **Evidence**: `tests/test_web_api.py::test_health`

### AC-2: 项目创建与归属
- **Type**: `rule`
- **Given**: 用户已登录
- **When**: 发送 `POST /api/projects` 带有效项目数据
- **Then**: 返回 201，包含 project_id 和 status；项目归属当前用户
- **Pass Condition**: 其他用户无法通过 GET 访问该项目
- **Evidence**: `tests/test_web_api.py::test_create_project` + `test_project_isolation`

### AC-3: 未登录访问限制
- **Type**: `rule`
- **Given**: 用户未登录（无有效 Session）
- **When**: 发送 `POST /api/projects` 或其他业务 API
- **Then**: 返回 401
- **Pass Condition**: 所有业务 API 在无 Session 时返回 401
- **Evidence**: `tests/test_web_api.py::test_unauthorized_access`

### AC-4: 文件上传与 SHA-256
- **Type**: `rule`
- **Given**: 已登录用户有一个项目
- **When**: 上传 xlsx 文件
- **Then**: 返回 upload_id，文件保存，SHA-256 正确，原始文件不被修改
- **Pass Condition**: SHA-256 与文件内容哈希一致；存储路径不含用户原始文件名
- **Evidence**: `tests/test_web_api.py::test_file_upload_sha256`

### AC-5: 非法扩展名和路径穿越
- **Type**: `rule`
- **Given**: 已登录用户
- **When**: 上传 .exe 或文件名含 `../`
- **Then**: 返回 400 拒绝
- **Pass Condition**: 可执行文件和路径穿越均被拒绝
- **Evidence**: `tests/test_web_api.py::test_illegal_extension` + `test_path_traversal`

### AC-6: 文件类型分流检测
- **Type**: `rule`
- **Given**: 项目已有上传的 xlsx/csv/json 文件
- **When**: 调用 `POST /api/projects/{id}/files/detect`
- **Then**: xlsx 调用 `detect_workbook`，csv 调用 `detect_csv`，json 调用 `detect_json`，返回 detected_type/confidence/recognized_columns/unmapped_columns/warnings
- **Pass Condition**: 三种类型调用对应检测函数并返回结构化结果
- **Evidence**: `tests/test_web_api.py::test_file_detect_by_type`

### AC-7: XLS 明确拒绝
- **Type**: `rule`
- **Given**: 已登录用户
- **When**: 上传 `.xls` 文件
- **Then**: 返回 400，提示转换为 `.xlsx`，不静默接受
- **Pass Condition**: `.xls` 上传被拒绝且提示明确
- **Evidence**: `tests/test_web_api.py::test_xls_rejected`

### AC-8: 任务创建与异步执行
- **Type**: `rule`
- **Given**: 项目已校验通过
- **When**: 调用 `POST /api/projects/{id}/jobs`
- **Then**: 立即返回 job_id + queued，后台开始执行
- **Pass Condition**: HTTP 响应在工作流完成前返回；`GET /api/jobs/{job_id}` 可查询进度
- **Evidence**: `tests/test_web_api.py::test_create_job_async`

### AC-9: 任务状态轮询与 Agent 进度
- **Type**: `rule`
- **Given**: 任务正在运行
- **When**: 轮询 `GET /api/jobs/{job_id}`
- **Then**: 返回 status、current_agent、completed_agents、progress、warnings、errors
- **Pass Condition**: 进度随时间递增，最终状态为 completed/completed_with_warnings/failed
- **Evidence**: `tests/test_web_api.py::test_job_status_polling`

### AC-10: 产品候选确认门禁
- **Type**: `rule`
- **Given**: 任务完成且生成了候选
- **When**: 未确认任何候选就调用 continue-development
- **Then**: 返回 waiting_for_confirmation，不生成产品开发规划
- **Pass Condition**: 确认至少一个 `confirmed` 候选后，continue-development 才生成产品规划
- **Evidence**: `tests/test_web_api.py::test_candidate_gate`

### AC-11: 候选确认与拒绝
- **Type**: `rule`
- **Given**: 有 `pending_review` 候选
- **When**: 调用 confirm 或 reject
- **Then**: 候选状态变为 `confirmed` 或 `rejected`
- **Pass Condition**: `rejected` 候选不能直接进入产品开发；接口为 `/confirm` 和 `/reject`
- **Evidence**: `tests/test_web_api.py::test_candidate_confirm_reject`

### AC-12: 人工供应链字段保存
- **Type**: `rule`
- **Given**: 已确认候选
- **When**: 调用 `PUT /api/projects/{id}/manual-inputs` 带部分字段
- **Then**: 空值保留为空，不自动填充 0
- **Pass Condition**: 未提供的字段为空而非 0
- **Evidence**: `tests/test_web_api.py::test_manual_inputs_preserve_empty`

### AC-13: 输出文件列表与下载权限
- **Type**: `rule`
- **Given**: 任务完成生成了报告
- **When**: 调用 `GET /api/projects/{id}/outputs` 和 `GET /api/outputs/{output_id}/download`
- **Then**: 列出文件；下载校验归属，其他用户无法下载
- **Pass Condition**: 跨用户下载返回 403；路径穿越返回 400
- **Evidence**: `tests/test_web_api.py::test_outputs_download_permission`

### AC-14: URL 默认关闭与 SSRF 防护（含 DNS 解析）
- **Type**: `rule`
- **Given**: 任务 allow_url_fetch=false
- **When**: 工作流执行
- **Then**: 不访问任何 URL；开启后，解析 DNS 后的内网/回环/元数据 IP 被拒绝
- **Pass Condition**: 默认不发 HTTP 请求；SSRF 测试 URL（含 DNS 解析到内网的情况）返回失败且不伪造数据
- **Evidence**: `tests/test_web_api.py::test_url_default_off` + `test_url_ssrf_dns_protection`

### AC-15: 前端页面可用
- **Type**: `rule`
- **Given**: 后端服务运行
- **When**: 浏览器访问前端地址
- **Then**: 页面加载，包含全部区域，可创建项目、上传文件、查看进度
- **Pass Condition**: 页面无 JS 错误；核心交互可用
- **Evidence**: 浏览器手动验证 + 前端自检

### AC-16: 测试基线动态记录与 CLI 兼容
- **Type**: `rule`
- **Given**: V3.2 代码已合并
- **When**: 运行全部测试和 CLI
- **Then**: 全部基线测试通过；CLI 正常运行；验收报告列出 baseline_test_count/new_test_count/final_test_count/passed_count/failed_count
- **Pass Condition**: `python -m unittest discover` 全绿；CLI 生成报告；报告含动态计数
- **Evidence**: 全量测试输出 + CLI 冒烟测试 + 验收报告

### AC-17: 密钥不出现在前端/日志
- **Type**: `rule`
- **Given**: 配置了环境变量密钥
- **When**: 检查前端 HTML/JS 和日志
- **Then**: 不包含任何密钥值
- **Pass Condition**: grep 前端文件和日志无密钥
- **Evidence**: `tests/test_web_api.py::test_no_secrets_in_frontend`

### AC-18: veFaaS 部署文件存在
- **Type**: `rule`
- **Given**: V3.2 实现完成
- **When**: 检查 deploy/ 目录
- **Then**: handler.py、worker_handler.py、requirements.txt、function.yaml、env.example、README.md、api_gateway/routes.md、tos/static_hosting.md 均存在
- **Pass Condition**: 文件存在且内容符合规范（密钥仅占位符）
- **Evidence**: 文件存在性检查

### AC-19: 前端整体可用性（移动端+桌面端）
- **Type**: `rubric`
- **Dimension**: 前端页面在移动端和桌面端的可用性
- **Scale**: 1-5
- **Anchors**: 1 = 布局错乱不可用；3 = 桌面端可用，移动端有明显问题；5 = 两端均流畅可用，交互清晰
- **Pass Threshold**: >= 4
- **Evidence**: 浏览器响应式测试

### AC-20: 后端架构清晰度
- **Type**: `rubric`
- **Dimension**: 后端分层（api/services/storage）与现有工作流的解耦程度
- **Scale**: 1-5
- **Anchors**: 1 = 业务逻辑混入 HTTP 层；3 = 有分层但耦合较重；5 = 清晰分层，StorageBackend/JobStore/TaskRunner 抽象完整，可替换
- **Pass Threshold**: >= 4
- **Evidence**: 代码审查

### AC-21: 用户身份真正隔离
- **Type**: `rule`
- **Given**: 两个不同用户通过独立邀请码登录
- **When**: 用户 A 创建项目，用户 B 尝试访问
- **Then**: 用户 B 得到 403；每个用户有独立 user_id 和 Session
- **Pass Condition**: 独立邀请码产生独立 user_id；跨用户访问所有资源均被拒绝
- **Evidence**: `tests/test_web_api.py::test_user_isolation_independent_invites`

### AC-22: 模板上传与绑定
- **Type**: `rule`
- **Given**: 已登录用户有项目
- **When**: 上传市场调研模板或产品开发规划模板
- **Then**: 返回 template_id，记录 template_type、sha256、validation_status，绑定到项目
- **Pass Condition**: 模板元数据正确保存；可按 project_id 查询
- **Evidence**: `tests/test_web_api.py::test_template_upload_bind`

### AC-23: 模板样式和结构保真
- **Type**: `rule`
- **Given**: 已上传并校验通过的模板
- **When**: 生成报告时填充模板副本
- **Then**: 原始模板未被修改；副本保留 Sheet 名称/顺序、表头、样式、公式、合并单元格、数据验证；示例数据和图片被删除
- **Pass Condition**: 原始模板 SHA-256 不变；副本样式/公式/合并单元格保留
- **Evidence**: `tests/test_web_api.py::test_template_fidelity`

### AC-24: WorkflowCheckpoint 保存
- **Type**: `rule`
- **Given**: Phase 1 任务完成
- **When**: 查询 checkpoint
- **Then**: checkpoint 包含 checkpoint_id、project_id、phase_1_job_id、input_sha256、config_sha256、agent_results_reference、candidate_results、completed_agents、current_phase
- **Pass Condition**: 所有必需字段存在且可用于 Phase 2 恢复
- **Evidence**: `tests/test_web_api.py::test_checkpoint_saved`

### AC-25: 候选确认后不重复执行 Phase 1
- **Type**: `rule`
- **Given**: Phase 1 已完成并保存 checkpoint，有 confirmed 候选
- **When**: 调用 continue-development 启动 Phase 2
- **Then**: Phase 1 的 Agent（excel_import/url_fetch/keyword/market/competitor/review/opportunity）不被重新执行
- **Pass Condition**: Phase 2 job 的 completed_agents 只含 Phase 2 agents；phase_1_job_id 被关联
- **Evidence**: `tests/test_web_api.py::test_phase2_no_repeat_phase1`

### AC-26: 任务协作式取消
- **Type**: `rule`
- **Given**: 任务正在运行
- **When**: 调用 cancel
- **Then**: 工作流检查 CancellationToken 后停止；最终状态为 cancelled；不发布正式报告；取消事件写入 job_events
- **Pass Condition**: 任务最终 cancelled；无正式输出文件；job_events 含取消事件
- **Evidence**: `tests/test_web_api.py::test_cancellation_token`

### AC-27: 任务幂等
- **Type**: `rule`
- **Given**: 同一项目用相同输入创建任务
- **When**: 重复创建
- **Then**: 返回已有 job_id 或创建幂等的新任务，不产生重复输出冲突
- **Pass Condition**: 相同 input_sha256 的任务可识别已有结果
- **Evidence**: `tests/test_web_api.py::test_job_idempotency`

### AC-28: 生产异步适配接口存在
- **Type**: `rule`
- **Given**: V3.2 实现完成
- **When**: 检查 backend/storage 和 backend/services
- **Then**: 存在 ProductionStorageBackend、ProductionJobStore、ProductionTaskRunner 接口（或抽象类），以及 worker_handler.py
- **Pass Condition**: 接口定义完整（消息结构、重试、幂等、取消、死信、超时）；文档明确真实队列尚未接入
- **Evidence**: 代码 + `deploy/veFaaS/README.md` 声明

### AC-29: 前端根据 workflow definition 动态渲染
- **Type**: `rule`
- **Given**: 后端返回 workflow definition
- **When**: 前端渲染任务进度区
- **Then**: Agent 列表来自 API 响应，JS 中无硬编码的 17 个 Agent 常量
- **Pass Condition**: 修改后端 agents 列表后前端自动反映
- **Evidence**: 前端代码审查 + 浏览器验证

### AC-30: CSV/JSON 检测不调用 detect_workbook
- **Type**: `rule`
- **Given**: 上传 csv 和 json 文件
- **When**: 调用 detect
- **Then**: csv 调用 detect_csv，json 调用 detect_json，均不调用 detect_workbook
- **Pass Condition**: 检测函数按扩展名分流
- **Evidence**: `tests/test_web_api.py::test_csv_json_detect_routing`

### AC-31: 不支持 XLS 时明确拒绝
- **Type**: `rule`
- **Given**: 上传 .xls 文件
- **When**: 后端处理
- **Then**: 返回 400 错误，明确提示转换为 .xlsx，不静默接受
- **Pass Condition**: .xls 不进入检测流程
- **Evidence**: `tests/test_web_api.py::test_xls_rejected`

### AC-32: DNS 解析后的 SSRF 防护
- **Type**: `rule`
- **Given**: allow_url_fetch=true，URL 的 DNS 解析结果为内网 IP
- **When**: 执行 URL 抓取
- **Then**: 请求被拒绝，不发送到内网，记录失败状态
- **Pass Condition**: 解析到私有/回环/链路本地/保留/CGNAT/元数据地址均被拦截；重定向后重新校验
- **Evidence**: `tests/test_web_api.py::test_ssrf_dns_resolution_block`

### AC-33: Cookie、CSRF、CORS 安全配置
- **Type**: `rule`
- **Given**: 后端服务运行
- **When**: 检查响应头和跨域行为
- **Then**: Session Cookie 为 HttpOnly；修改状态 API 校验 CSRF Token 或 Origin；ALLOWED_ORIGINS 严格，无 `*` 配 Cookie
- **Pass Condition**: Cookie 安全标志正确；CSRF 校验生效；CORS 不允许任意 Origin
- **Evidence**: `tests/test_web_api.py::test_cookie_csrf_cors`

### AC-34: 测试基线动态记录
- **Type**: `rule`
- **Given**: 实施完成
- **When**: 运行全量测试
- **Then**: 验收报告列出 baseline_test_count、new_test_count、final_test_count、passed_count、failed_count，不硬编码固定数字
- **Pass Condition**: 报告含动态计数字段
- **Evidence**: 验收报告
