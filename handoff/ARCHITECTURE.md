# ARCHITECTURE — 真实架构

> 区分**本地实现**（可用）与**生产适配**（骨架/未实现）。
> 生产适配类只是接口、骨架或抛出 NotImplementedError 时，**不描述为生产可用**。

---

## 1. 浏览器前端

- **位置**: [frontend/](file:///frontend/)
- **文件**: `index.html`、`app.js`、`api.js`、`styles.css`
- **加载方式**: 由本地后端从 `frontend/` 目录静态服务
- **Agent 顺序**: 从 `GET /api/workflow/definition` 接口动态获取（[backend/api/health.py](file:///backend/api/health.py#L19)），**禁止硬编码**

## 2. HTTP API

- **位置**: [backend/api/](file:///backend/api/)
- **入口**: [backend/app.py](file:///backend/app.py) `MAIN_ROUTER` 聚合 10 个子路由
- **实现**: `http.server.ThreadingHTTPServer`（单进程多线程）
- **路由模块**: auth、projects、uploads、jobs、candidates、manual_inputs、outputs、templates、validation、health
- **请求/响应**: `backend/api/__init__.py` 的 `build_request`、`Response`

## 3. SQLite

- **位置**: `data/web.db`（[backend/config.py](file:///backend/config.py#L75)）
- **Schema 定义**: [backend/storage/job_store.py](file:///backend/storage/job_store.py)
- **配置入口**: [backend/storage/database.py](file:///backend/storage/database.py) `configure_paths`、`get_job_store`、`get_storage` 单例
- **限制**: 单文件、单实例、不能跨实例共享

## 4. 本地文件存储

- **目录**:
  - `data/web_storage/` — 用户上传文件
  - `data/output/` — 报告输出
- **配置**: [backend/config.py](file:///backend/config.py#L72-L74)
- **限制**: 本地文件系统，无对象存储

## 5. JobStore

- **位置**: [backend/storage/job_store.py](file:///backend/storage/job_store.py)
- **类**: `LocalJobStore`（实现 `JobStore` 抽象基类）
- **职责**: 任务记录、状态变更、事件记录、checkpoint 存储（全部 SQLite）
- **生产适配**: `ProductionJobStore` **未实现**

## 6. TaskRunner

- **位置**: [backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)
- **类**: `LocalTaskRunner`（隐含在 `WorkflowRunner` 中）
- **实现**: `threading.Thread` 启动后台任务
- **生产适配**: `ProductionTaskRunner` **未实现**（veFaaS Worker 仅为骨架）

## 7. WorkflowRunner

- **位置**: [backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)
- **关键方法**:
  - `submit_phase_1(project_id, ...)` — 提交 Phase 1
  - `submit_phase_2(project_id, candidate_id, manual_inputs, ...)` — 提交 Phase 2
  - `_run_phase_1(job_id, ...)` — Phase 1 执行体
  - `_run_phase_2(job_id, ...)` — Phase 2 执行体（含 `template_path` 参数）
  - `cancel(job_id)` — 任务取消
- **依赖**: `LocalJobStore`、`LocalStorageBackend`、`CancellationToken`

## 8. Agent 调用关系

- **Phase 1**（12 个 Agent，[backend/config.py](file:///backend/config.py#L93-L106)）:
  1. `input_validation`
  2. `workbook_detection`
  3. `schema_mapping`
  4. `excel_import`
  5. `url_fetch`
  6. `keyword`
  7. `market`
  8. `competitor`
  9. `brand_seller`
  10. `review`
  11. `opportunity`
  12. `product_candidate`
- **Phase 2**（4 个 Agent）:
  1. `product_development`
  2. `profit`
  3. `report`
  4. `excel`
- **核心 Agent**: [src/core/agent.py](file:///src/core/agent.py) — **占位符，不修改**
- **业务实现**: [src/modules/amazon/](file:///src/modules/amazon/) 下各子模块

## 9. Phase 1 和 Phase 2

- **Phase 1**: 调研阶段，产出 candidates + checkpoint
- **Phase 2**: 开发阶段，依赖 candidates 确认 + 人工输入，产出报告
- **门禁**: 候选确认前不可启动 Phase 2
- **入口**: `WorkflowRunner.submit_phase_1` / `submit_phase_2`

## 10. WorkflowCheckpoint

- **保存**: `_save_checkpoint(job_id, checkpoint_data)`（Phase 1 完成时）
- **读取**: `_load_checkpoint(job_id)`（Phase 2 启动时）
- **存储位置**: `LocalJobStore` SQLite
- **作用**: Phase 2 复用 Phase 1 结果，避免重跑
- **测试**: `tests/test_phase2_checkpoint.py`（15 个测试）

## 11. 模板处理

- **上传**: [backend/api/templates.py](file:///backend/api/templates.py)
- **绑定**: 项目级绑定 `market_research_template` / `product_development_template`
- **应用**: `WorkflowRunner._run_phase_2` 通过 `template_path` 参数传入 V31Workflow
- **执行**: [src/modules/amazon/template_builder.py](file:///src/modules/amazon/template_builder.py) 复制模板副本后填充
- **保护**: 原模板 SHA-256 不变（已验证）
- **缺口**: 合并单元格、样式、公式、批注、行高列宽等未逐项对比

## 12. 输出下载

- **API**: [backend/api/outputs.py](file:///backend/api/outputs.py)
- **权限**: owner_id 校验 + 路径穿越防护 + 已登记路径校验
- **存储**: 本地 `data/output/`
- **生产适配**: 签名下载 **未实现**

## 13. veFaaS 适配层

- **API Handler**: [deploy/veFaaS/handler.py](file:///deploy/veFaaS/handler.py) — **真实可用**，通过 `MAIN_ROUTER` 派发
- **Worker Handler**: [deploy/veFaaS/worker_handler.py](file:///deploy/veFaaS/worker_handler.py) — **骨架**，无真实队列消费
- **部署文档**: [deploy/tos/static_hosting.md](file:///deploy/tos/static_hosting.md)、[deploy/api_gateway/routes.md](file:///deploy/api_gateway/routes.md)

---

## 本地实现 vs 生产适配

### 本地实现（可用）

```
LocalStorageBackend       — backend/storage/local_storage.py
LocalJobStore             — backend/storage/job_store.py
LocalTaskRunner           — backend/services/workflow_runner.py（隐含）
SQLite                    — data/web.db
本地文件系统              — data/web_storage/、data/output/
threading.Thread          — backend/services/workflow_runner.py
```

### 生产适配（未实现/骨架）

```
ProductionStorageBackend  — 未实现（TOS 适配）
ProductionJobStore        — 未实现（生产数据库适配）
ProductionTaskRunner      — 未实现（队列 + Worker）
TOS                       — 未接入
生产数据库                — 未接入
异步队列（RocketMQ）      — 未接入
veFaaS Worker             — 骨架（worker_handler.py 仅返回提示消息）
签名下载                  — 未实现
生产 Session Secret      — 未配置
API Gateway               — 仅文档
HTTPS                     — 未配置
多实例                    — 不支持
任务重试/死信/超时恢复    — 未实现
监控告警                  — 未实现
```

**明确声明**:
- Handler 文件存在**不等于**已经完成生产部署。
- 如果 TOS、生产数据库和真实异步队列尚未接入，当前版本**不能**声明生产可用。
- `ProductionStorageBackend`、`ProductionJobStore`、`ProductionTaskRunner` 类**不存在**于当前代码中。
