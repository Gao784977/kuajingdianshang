# V3.2 Web 端与 veFaaS 部署 - Implementation Plan

## Task 1: 后端骨架和健康检查
- **Status**: `pending`
- **Priority**: high
- **Depends On**: None
- **Description**:
  - 创建 `backend/` 目录结构：`app.py`（标准库 `http.server` 入口）、`api/`、`services/`、`storage/`。
  - 实现 `GET /api/health` 返回 `{status, version: "v3.2", environment}`。
  - 实现 `GET /api/workflow/definition` 返回 Phase 1/Phase 2 Agent 顺序（供前端动态渲染）。
  - 实现静态文件托管（`frontend/` 目录）。
  - 启动命令：`python -m backend.app`，监听 0.0.0.0:8000。
- **Acceptance Criteria Addressed**: AC-1, AC-29
- **Test Requirements**:
  - `rule` TR-1.1: `GET /api/health` 返回 200 且 JSON 包含 status/version/environment；证据：`tests/test_web_api.py::test_health`
  - `rule` TR-1.2: `GET /api/workflow/definition` 返回 phases 和 agents 列表；证据：`tests/test_web_api.py::test_workflow_definition`
- **Local Scope**: http.server + 静态文件托管
- **Production Scope**: veFaaS API Handler 包装相同路由
- **Known Limitations**: 无

## Task 2: SQLite 存储与 StorageBackend 抽象
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 1
- **Description**:
  - 创建 `backend/storage/base.py`：`StorageBackend`、`JobStore`、`TaskRunner` 抽象类。
  - 创建 `backend/storage/local_storage.py`：`LocalStorageBackend`（文件系统）。
  - 创建 `backend/storage/job_store.py`：`LocalJobStore`（SQLite）。
  - 创建表：users, projects, uploads, jobs, job_events, outputs, product_candidates, manual_inputs, url_fetches, sessions, invitations, templates, workflow_checkpoints。
  - 文件存储：`data/web_storage/{project_id}/uploads/{upload_id}`，输出文件同理隔离。
- **Acceptance Criteria Addressed**: AC-2, AC-13
- **Test Requirements**:
  - `rule` TR-2.1: SQLite 初始化创建全部表；证据：`tests/test_web_storage.py::test_db_init`
  - `rule` TR-2.2: 上传文件存储路径不含用户原始文件名，使用 upload_id；证据：`tests/test_web_storage.py::test_storage_path_isolation`
- **Local Scope**: SQLite + 本地文件系统
- **Production Scope**: `ProductionStorageBackend`（TOS）、`ProductionJobStore`（生产 DB）接口骨架在 Task 18 实现
- **Known Limitations**: 本任务只实现本地实现，生产实现为接口骨架

## Task 3: 邀请码、Session、用户隔离、CSRF
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 2
- **Description**:
  - 创建 `backend/services/auth_service.py`。
  - `invitations` 表：invitation_id, token_hash, max_uses, used_count, expires_at, status, created_at。
  - `ADMIN_BOOTSTRAP_TOKEN` 仅用于初始化管理员/创建邀请记录，不作为通用登录凭证。
  - 独立邀请码创建独立 user_id；邀请码只存哈希，支持过期和最大使用次数。
  - `POST /api/auth/login`（邀请码）→ HttpOnly Session Cookie；`POST /api/auth/logout`。
  - `get_current_user` 从 Session 取 user_id，不信任前端 user_id。
  - Session 过期、注销、撤销；登录失败速率限制。
  - Cookie：HttpOnly；本地 `Secure=false`/`SameSite=Lax`，生产 `Secure=true`。
  - CSRF：修改状态 API 校验 CSRF Token 或 Origin；严格 ALLOWED_ORIGINS，无 `*` 配 Cookie。
- **Acceptance Criteria Addressed**: AC-3, AC-21, AC-33
- **Test Requirements**:
  - `rule` TR-3.1: 无 Session 调用业务 API 返回 401；证据：`tests/test_web_api.py::test_unauthorized_access`
  - `rule` TR-3.2: 错误邀请码返回 401；独立邀请码产生独立 user_id；证据：`tests/test_web_api.py::test_user_isolation_independent_invites`
  - `rule` TR-3.3: Cookie HttpOnly，CSRF 校验生效，CORS 无 `*`；证据：`tests/test_web_api.py::test_cookie_csrf_cors`
- **Local Scope**: SQLite 存邀请/Session，内存速率限制
- **Production Scope**: 生产 DB 存邀请/Session，Redis 速率限制（接口预留）
- **Known Limitations**: 若只实现临时管理员邀请码，需明确多人隔离未完成

## Task 4: 项目管理 API
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 3
- **Description**:
  - `POST /api/projects`、`GET /api/projects/{id}`、`PUT /api/projects/{id}`。
  - 字段：project_name, marketplace, keywords, categories, target_price_range, urls, manual_inputs。
  - owner_id = 当前 Session 用户；跨用户访问返回 403。
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `rule` TR-4.1: 创建项目返回 project_id；其他用户 GET 返回 403；证据：`tests/test_web_api.py::test_create_project` + `test_project_isolation`
- **Local Scope**: SQLite projects 表
- **Production Scope**: 生产 DB projects 表
- **Known Limitations**: 无

## Task 5: 文件上传和文件安全
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 4
- **Description**:
  - `POST /api/projects/{id}/files`（multipart/form-data，多文件）。
  - 支持扩展名：`xlsx`、`csv`、`json`。**`.xls` 明确拒绝**（400 + 提示转 xlsx）。
  - 禁止可执行文件；限制大小（`MAX_UPLOAD_SIZE_MB`，默认 50MB）。
  - 计算 SHA-256，保存原始文件到隔离目录，记录 upload_id。
  - 防路径穿越：不使用用户文件名作为存储路径。
- **Acceptance Criteria Addressed**: AC-4, AC-5, AC-7, AC-31
- **Test Requirements**:
  - `rule` TR-5.1: 上传 xlsx 返回 upload_id，SHA-256 正确；证据：`tests/test_web_api.py::test_file_upload_sha256`
  - `rule` TR-5.2: .exe 返回 400；`../` 返回 400；证据：`tests/test_web_api.py::test_illegal_extension` + `test_path_traversal`
  - `rule` TR-5.3: .xls 返回 400 并提示转 xlsx；证据：`tests/test_web_api.py::test_xls_rejected`
- **Local Scope**: 本地文件系统存储
- **Production Scope**: TOS 存储（ProductionStorageBackend）
- **Known Limitations**: .xls 不支持；需用户自行转换

## Task 6: 按文件类型分流检测与字段识别
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 5
- **Description**:
  - `POST /api/projects/{id}/files/detect` 按扩展名分流：
    - `xlsx` → `detect_workbook()`
    - `csv` → `detect_csv()`
    - `json` → `detect_json()`
  - 返回 detected_type/confidence/recognized_columns/unmapped_columns/warnings。
  - `POST /api/projects/{id}/files/{upload_id}/confirm` 确认/修改文件类型。
  - 复用 `src/modules/amazon/importers/workbook_detector.py`；csv/json 检测为新增轻量实现。
- **Acceptance Criteria Addressed**: AC-6, AC-30
- **Test Requirements**:
  - `rule` TR-6.1: xlsx/csv/json 分别调用对应检测函数；证据：`tests/test_web_api.py::test_file_detect_by_type` + `test_csv_json_detect_routing`
- **Local Scope**: 调用本地检测函数
- **Production Scope**: 相同检测逻辑
- **Known Limitations**: csv/json 检测为基础实现，复杂格式可能识别为 unknown

## Task 7: 模板上传、绑定、校验和模板保真处理
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 5
- **Description**:
  - 模板类型：`market_research_template`、`product_development_template`。
  - `POST /api/projects/{id}/templates`、`GET`、`PUT /{template_id}`。
  - templates 表：template_id, project_id, template_type, original_name, sha256, version, validation_status, created_at。
  - 模板校验：Sheet 存在性、Sheet 名称、必需表头、可读性、合并单元格、样式、公式、数据验证、页面设置。
  - 保真填充流程：复制原模板（不修改原文件）→ 删除示例数据/图片/图表 → 保留 Sheet 名/顺序、表头、样式、公式、合并单元格、数据验证、批注、列宽、行高、冻结窗格、页面设置 → 写入分析结果 → 输出记录 template_id/job_id/project_id。
- **Acceptance Criteria Addressed**: AC-22, AC-23
- **Test Requirements**:
  - `rule` TR-7.1: 模板上传返回 template_id，元数据正确；证据：`tests/test_web_api.py::test_template_upload_bind`
  - `rule` TR-7.2: 原模板 SHA-256 不变，副本保留样式/公式/合并单元格，示例数据删除；证据：`tests/test_web_api.py::test_template_fidelity`
- **Local Scope**: 本地模板文件 + openpyxl 处理
- **Production Scope**: TOS 存模板，相同处理逻辑
- **Known Limitations**: 复杂宏/ActiveX 不在保真范围内

## Task 8: 项目输入校验 API
- **Status**: `pending`
- **Priority**: medium
- **Depends On**: Task 6
- **Description**:
  - `POST /api/projects/{id}/validate`：校验项目输入和文件，返回 valid/errors/warnings/pending_manual_inputs/pending_validation。
- **Acceptance Criteria Addressed**: AC-2（部分）
- **Test Requirements**:
  - `rule` TR-8.1: 有效项目返回 valid=true；缺关键词返回 warnings；证据：`tests/test_web_api.py::test_validate_project`
- **Local Scope**: 本地校验逻辑
- **Production Scope**: 相同
- **Known Limitations**: 无

## Task 9: WorkflowCheckpoint 和两阶段工作流
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 8
- **Description**:
  - 定义 `WorkflowCheckpoint` 数据结构和 workflow_checkpoints 表。
  - 字段：checkpoint_id, project_id, job_id(phase_1), workflow_version, input_sha256, config_sha256, normalized_data_reference, agent_results_reference, candidate_results, data_quality_reference, source_provenance_reference, completed_agents, current_phase, created_at, updated_at。
  - Phase 1：input_validation → workbook_detection → schema_mapping → excel_import → url_fetch → keyword → market → competitor → brand_seller → review → opportunity → product_candidate。完成后保存 checkpoint。
  - Phase 2：读取 checkpoint → 读取 confirmed 候选 → 读取 manual_inputs → product_development → profit → report → excel。关联 phase_1_job_id 和 phase_2_job_id。
  - `POST /api/projects/{id}/continue-development` 启动 Phase 2，不重跑 Phase 1。
- **Acceptance Criteria Addressed**: AC-24, AC-25
- **Test Requirements**:
  - `rule` TR-9.1: Phase 1 完成后 checkpoint 含全部必需字段；证据：`tests/test_web_api.py::test_checkpoint_saved`
  - `rule` TR-9.2: Phase 2 不重复执行 Phase 1 agents，关联 phase_1_job_id；证据：`tests/test_web_api.py::test_phase2_no_repeat_phase1`
- **Local Scope**: SQLite checkpoint 表 + 本地文件引用
- **Production Scope**: 生产 DB checkpoint + 对象存储引用
- **Known Limitations**: checkpoint 引用的大对象在本地存文件，生产需存 TOS

## Task 10: 本地异步任务执行和进度事件
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 9
- **Description**:
  - `backend/services/job_service.py`：`LocalTaskRunner` 用 `threading.Thread` 执行 Phase 1/Phase 2 工作流。
  - `POST /api/projects/{id}/jobs` 创建 Phase 1 任务，立即返回 job_id + queued。
  - `GET /api/jobs/{job_id}` 查询状态（status/current_agent/completed_agents/progress/warnings/errors）。
  - `GET /api/jobs/{job_id}/intermediate` 中间结果。
  - 任务状态和事件写入 SQLite jobs/job_events。
- **Acceptance Criteria Addressed**: AC-8, AC-9
- **Test Requirements**:
  - `rule` TR-10.1: 创建任务立即返回 queued，后台运行；证据：`tests/test_web_api.py::test_create_job_async`
  - `rule` TR-10.2: 轮询可见进度递增和最终状态；证据：`tests/test_web_api.py::test_job_status_polling`
- **Local Scope**: threading.Thread + SQLite
- **Production Scope**: ProductionTaskRunner（消息队列 + Worker），接口骨架在 Task 18
- **Known Limitations**: 本地线程不能作为生产任务系统

## Task 11: 任务取消、幂等和失败恢复
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 10
- **Description**:
  - `CancellationToken`：每个 Agent 开始前、文件循环中、URL 请求前后、长计算中检查取消标记。
  - `POST /api/jobs/{job_id}/cancel` 设置取消标记；工作流主动检查后停止。
  - 取消后不生成正式输出；中间结果标记 partial；最终状态 cancelled；取消事件写入 job_events。
  - 幂等：相同 input_sha256 的任务可识别已有结果，避免重复输出冲突。
  - 失败恢复：任务失败记录 error_message，支持重试（不重跑已完成阶段）。
- **Acceptance Criteria Addressed**: AC-26, AC-27
- **Test Requirements**:
  - `rule` TR-11.1: 运行中取消 → 最终 cancelled，无正式输出，job_events 含取消事件；证据：`tests/test_web_api.py::test_cancellation_token`
  - `rule` TR-11.2: 相同输入重复创建任务幂等；证据：`tests/test_web_api.py::test_job_idempotency`
- **Local Scope**: 内存 CancellationToken + SQLite 状态
- **Production Scope**: 分布式取消信号 + 持久化幂等键
- **Known Limitations**: 取消是协作式，长阻塞 I/O 可能需等待超时

## Task 12: 产品候选确认门禁
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 10
- **Description**:
  - `GET /api/projects/{id}/candidates` 从 job 结果获取候选。
  - `POST /api/projects/{id}/candidates/{cid}/confirm` → `confirmed`。
  - `POST /api/projects/{id}/candidates/{cid}/reject` → `rejected`。
  - 复用 `ProductCandidate` 状态机（pending_review/confirmed/rejected）。
  - **只有至少一个 confirmed 候选才允许 continue-development。**
- **Acceptance Criteria Addressed**: AC-10, AC-11
- **Test Requirements**:
  - `rule` TR-12.1: 无 confirmed 候选时 continue-development 返回 waiting_for_confirmation；证据：`tests/test_web_api.py::test_candidate_gate`
  - `rule` TR-12.2: confirm/reject 改变状态，rejected 不能进入开发；证据：`tests/test_web_api.py::test_candidate_confirm_reject`
- **Local Scope**: SQLite product_candidates 表
- **Production Scope**: 生产 DB
- **Known Limitations**: 无（状态机与 V3.1 一致）

## Task 13: 人工供应链输入和 Phase 2 继续开发
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 12
- **Description**:
  - `PUT /api/projects/{id}/manual-inputs` 保存供应商/成本/MOQ/物流等字段，空值保留为空（不填 0）。
  - `POST /api/projects/{id}/continue-development`：读取 Phase 1 checkpoint + confirmed 候选 + manual_inputs，执行 Phase 2（product_development → profit → report → excel），生成产品规划和利润报告。
- **Acceptance Criteria Addressed**: AC-12, AC-25
- **Test Requirements**:
  - `rule` TR-13.1: 未提供字段为空而非 0；证据：`tests/test_web_api.py::test_manual_inputs_preserve_empty`
  - `rule` TR-13.2: 确认候选后 continue-development 生成产品规划；证据：`tests/test_web_api.py::test_continue_development`
- **Local Scope**: SQLite manual_inputs + 本地 Phase 2 执行
- **Production Scope**: 生产 DB + Worker 执行 Phase 2
- **Known Limitations**: 无

## Task 14: 输出文件和安全下载
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 10
- **Description**:
  - `GET /api/projects/{id}/outputs` 列出输出文件。
  - `GET /api/outputs/{output_id}/download` 下载：校验 owner_id 归属、白名单路径、防路径穿越、正确 Content-Type。
  - outputs 表：id, project_id, job_id, output_type, file_name, storage_key, sha256, size, created_at。
- **Acceptance Criteria Addressed**: AC-13
- **Test Requirements**:
  - `rule` TR-14.1: 跨用户下载返回 403；路径穿越返回 400；证据：`tests/test_web_api.py::test_outputs_download_permission`
- **Local Scope**: 本地文件下载
- **Production Scope**: TOS 短期签名 URL 下载
- **Known Limitations**: 本地下载直接读文件，生产需签名 URL

## Task 15: URL 默认关闭、SSRF 和数据来源冲突处理
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 10
- **Description**:
  - 默认 allow_url_fetch=false 不访问 URL。
  - SSRF 防护：DNS 解析后校验 IPv4/IPv6，禁止回环/私有/链路本地/保留/CGNAT/云元数据地址；每次重定向后重新校验；不继承 HTTP_PROXY/HTTPS_PROXY；限制超时/大小/重定向次数/Content-Type。
  - 记录最终 URL、HTTP 状态、content_hash、解析警告。
  - URL 失败不伪造数据、不覆盖 Excel 数据、保留失败状态；strict 模式按配置处理。
- **Acceptance Criteria Addressed**: AC-14, AC-32
- **Test Requirements**:
  - `rule` TR-15.1: 默认不访问 URL；DNS 解析到内网被拦截；证据：`tests/test_web_api.py::test_url_default_off` + `test_ssrf_dns_resolution_block`
- **Local Scope**: 标准库 socket/urllib + DNS 校验
- **Production Scope**: 相同逻辑，生产环境额外加固
- **Known Limitations**: IPv6 完整覆盖需测试；DNS rebinding 需额外 TTL 处理

## Task 16: HTML 前端工作台
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 14, Task 15
- **Description**:
  - `frontend/index.html`、`styles.css`、`app.js`、`api.js`。
  - 区域：导航、项目输入、URL 输入、文件上传、识别结果、模板管理、工作流控制、任务进度、候选、人工信息、报告下载。
  - 关键词/类目标签输入（添加/删除/编辑/去重/回车）。
  - **Agent 列表从 `GET /api/workflow/definition` 动态渲染，不硬编码。**
  - 防重复提交、危险操作确认。
  - 移动端 + 桌面端响应式。
- **Acceptance Criteria Addressed**: AC-15, AC-19, AC-29
- **Test Requirements**:
  - `rule` TR-16.1: 页面加载无 JS 错误，含全部区域；证据：浏览器验证
  - `rule` TR-16.2: Agent 列表来自 API，JS 无硬编码常量；证据：前端代码审查
  - `rubric` TR-16.3: 移动端+桌面端可用性；scale 1-5；threshold >= 4；证据：响应式测试
- **Local Scope**: 原生 HTML/CSS/JS，由后端静态托管
- **Production Scope**: TOS 静态托管 + API Gateway
- **Known Limitations**: 无复杂可视化

## Task 17: 前后端完整联调
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 16
- **Description**:
  - `api.js` 封装所有后端 API。
  - 全流程联通：登录 → 创建项目 → 上传文件 → 识别 → 模板绑定 → 开始分析 → 轮询进度 → 确认候选 → 人工信息 → 继续开发 → 下载报告。
- **Acceptance Criteria Addressed**: AC-15
- **Test Requirements**:
  - `rule` TR-17.1: 完整流程可在浏览器走通；证据：端到端手动测试
- **Local Scope**: 本地浏览器 + 本地后端
- **Production Scope**: 生产域名 + HTTPS
- **Known Limitations**: 无

## Task 18: 生产异步任务适配层
- **Status**: `pending`
- **Priority**: medium
- **Depends On**: Task 11
- **Description**:
  - `backend/storage/base.py` 中 `ProductionTaskRunner` 抽象类。
  - 生产任务消息结构定义（job_id, phase, input_ref, checkpoint_ref, retry_count, idempotency_key）。
  - Worker Handler 消费消息的接口。
  - 持久化任务状态、任务重试、任务幂等、任务取消、失败和死信处理、函数超时处理的接口定义。
  - **明确文档声明：当前只完成接口骨架，真实队列/DB/TOS 仍需接入。**
- **Acceptance Criteria Addressed**: AC-28
- **Test Requirements**:
  - `rule` TR-18.1: ProductionTaskRunner/ProductionStorageBackend/ProductionJobStore 接口存在且完整；证据：代码 + `deploy/veFaaS/README.md` 声明
- **Local Scope**: 仅接口定义，无真实实现
- **Production Scope**: 需接入火山引擎消息队列、TOS、生产 DB
- **Known Limitations**: 本任务不接入真实云服务

## Task 19: veFaaS API Handler 和 Worker Handler
- **Status**: `pending`
- **Priority**: medium
- **Depends On**: Task 18
- **Description**:
  - `deploy/veFaaS/handler.py`：API Handler，将 veFaaS HTTP 事件转换为后端 API 请求。
  - `deploy/veFaaS/worker_handler.py`：Worker Handler，消费异步任务消息执行工作流。
  - `deploy/veFaaS/requirements.txt`、`function.yaml`、`env.example`（密钥仅占位符）、`README.md`。
- **Acceptance Criteria Addressed**: AC-18, AC-28
- **Test Requirements**:
  - `rule` TR-19.1: deploy/veFaaS/ 下文件齐全，env.example 无真实密钥；证据：文件检查
- **Local Scope**: 不运行（需 veFaaS 环境）
- **Production Scope**: veFaaS 部署入口
- **Known Limitations**: 未在真实 veFaaS 验证

## Task 20: API Gateway 和 TOS 部署文档
- **Status**: `pending`
- **Priority**: medium
- **Depends On**: Task 19
- **Description**:
  - `deploy/api_gateway/routes.md`：API 路由配置说明。
  - `deploy/tos/static_hosting.md`：TOS 静态前端托管说明。
  - 明确本地/生产边界声明。
- **Acceptance Criteria Addressed**: AC-18
- **Test Requirements**:
  - `rule` TR-20.1: 文档存在且含本地/生产边界声明；证据：文件检查
- **Local Scope**: 文档
- **Production Scope**: 部署参考
- **Known Limitations**: 需用户按文档实际配置

## Task 21: 安全测试、模板测试和 Web API 测试
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 17, Task 7, Task 15, Task 11, Task 3
- **Description**:
  - 编写 `tests/test_web_api.py`、`tests/test_web_storage.py`、`tests/test_template.py`、`tests/test_security.py`。
  - 覆盖：健康检查、项目 CRUD、隔离、上传安全、类型分流检测、xls 拒绝、模板保真、checkpoint、Phase 2 不重复、取消、幂等、候选门禁、人工字段、输出权限、URL SSRF（DNS）、Cookie/CSRF/CORS、无密钥。
- **Acceptance Criteria Addressed**: AC-1 ~ AC-34
- **Test Requirements**:
  - `rule` TR-21.1: 所有 Web API 测试通过；证据：`python -m unittest tests.test_web_api`
- **Local Scope**: 本地测试
- **Production Scope**: 相同测试在 CI 运行
- **Known Limitations**: 浏览器交互测试为手动验证

## Task 22: 全量回归测试和 CLI 兼容性
- **Status**: `pending`
- **Priority**: high
- **Depends On**: Task 17, Task 20, Task 7, Task 18
- **Description**:
  - 运行全量测试，记录 baseline_test_count / new_test_count / final_test_count / passed_count / failed_count。
  - CLI 冒烟测试：`python -m src.modules.analyze_opportunities` 仍可用。
  - 确认 `src/core/agent.py` 未被修改。
  - 最终回归必须在 Web 本地功能、模板、部署文件和安全任务完成后执行。
- **Acceptance Criteria Addressed**: AC-16, AC-20, AC-34
- **Test Requirements**:
  - `rule` TR-22.1: 全量测试通过（基线 + 新增）；证据：测试输出
  - `rule` TR-22.2: CLI 生成报告正常；证据：CLI 冒烟
  - `rubric` TR-22.3: 后端架构清晰度；scale 1-5；threshold >= 4；证据：代码审查
  - `rubric` TR-22.4: 安全防护完整性；scale 1-5；threshold >= 4；证据：安全测试
- **Local Scope**: 本地全量测试
- **Production Scope**: CI 全量测试
- **Known Limitations**: 生产环境集成测试需真实云资源
