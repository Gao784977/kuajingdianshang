# API_INVENTORY — 实际存在的 API 清单

> 基于 [backend/app.py](file:///backend/app.py) `MAIN_ROUTER` 与各 [backend/api/](file:///backend/api/) 模块实际注册的路由。
> 设计文档有但代码无的，标记 NOT_IMPLEMENTED。

---

## 标记说明

- **已实现**: 代码中真实存在且路由注册
- **有测试**: 至少一个测试覆盖
- **NOT_IMPLEMENTED**: 设计文档有但代码无

---

## 认证相关

### GET /api/health
- **方法**: GET
- **路径**: `/api/health`
- **已实现**: YES（[backend/api/health.py](file:///backend/api/health.py)）
- **有测试**: YES（`tests/test_health.py`）
- **登录要求**: NO
- **owner_id 校验**: NO
- **请求参数**: 无
- **返回值**: `{"status": "ok", "version": "v3.2"}`
- **错误状态**: 无
- **当前限制**: 无

### GET /api/workflow/definition
- **方法**: GET
- **路径**: `/api/workflow/definition`
- **已实现**: YES（[backend/api/health.py](file:///backend/api/health.py#L19)）
- **有测试**: YES（`tests/test_health.py`）
- **登录要求**: NO
- **owner_id 校验**: NO
- **请求参数**: 无
- **返回值**: `WORKFLOW_DEFINITION`（phase_1/phase_2 Agent 顺序）
- **错误状态**: 无
- **当前限制**: 前端必须从此接口动态获取 Agent 顺序，禁止硬编码

### POST /api/auth/login
- **方法**: POST
- **路径**: `/api/auth/login`
- **已实现**: YES（[backend/api/auth.py](file:///backend/api/auth.py)）
- **有测试**: YES（`tests/test_auth_invitation.py`）
- **登录要求**: NO（登录入口）
- **owner_id 校验**: NO
- **请求参数**: `{"invitation_code": "..."}`
- **返回值**: `{"session_id": "...", "user_id": "..."}`
- **错误状态**: 401（无效邀请码）、429（限流）
- **当前限制**: 首次需 `ADMIN_BOOTSTRAP_TOKEN` 引导

### POST /api/auth/logout
- **方法**: POST
- **路径**: `/api/auth/logout`
- **已实现**: YES
- **有测试**: YES
- **登录要求**: YES
- **owner_id 校验**: NO
- **请求参数**: 无
- **返回值**: `{"status": "ok"}`
- **错误状态**: 401（未登录）
- **当前限制**: 无

### GET /api/auth/me
- **方法**: GET
- **路径**: `/api/auth/me`
- **已实现**: YES
- **有测试**: YES
- **登录要求**: YES
- **owner_id 校验**: NO
- **请求参数**: 无
- **返回值**: `{"user_id": "...", "session_id": "..."}`
- **错误状态**: 401
- **当前限制**: 无

---

## 项目管理

### GET /api/projects
- **方法**: GET
- **路径**: `/api/projects`
- **已实现**: YES（[backend/api/projects.py](file:///backend/api/projects.py)）
- **有测试**: YES（`tests/test_projects_api.py`、`tests/test_cross_user_isolation.py`）
- **登录要求**: YES
- **owner_id 校验**: YES（仅返回当前用户项目）
- **请求参数**: 无
- **返回值**: `{"projects": [...]}`
- **错误状态**: 401
- **当前限制**: 无

### POST /api/projects
- **方法**: POST
- **路径**: `/api/projects`
- **已实现**: YES
- **有测试**: YES
- **登录要求**: YES
- **owner_id 校验**: YES（owner_id 从 Session 取，不接受前端传入）
- **请求参数**: `{"name": "...", "keywords": [...], "categories": [...], "url": "..."}`
- **返回值**: `{"project_id": "..."}`
- **错误状态**: 400（参数缺失）、401
- **当前限制**: 无

### GET /api/projects/{project_id}
- **方法**: GET
- **路径**: `/api/projects/{project_id}`
- **已实现**: YES
- **有测试**: YES
- **登录要求**: YES
- **owner_id 校验**: YES（非 owner 返回 403/404）
- **请求参数**: path param `project_id`
- **返回值**: 项目详情
- **错误状态**: 401、403、404
- **当前限制**: 无

---

## 文件上传

### POST /api/projects/{project_id}/files
- **方法**: POST
- **路径**: `/api/projects/{project_id}/files`
- **已实现**: YES（[backend/api/uploads.py](file:///backend/api/uploads.py)）
- **有测试**: YES（`tests/test_uploads_api.py`）
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: multipart/form-data，字段 `file`
- **返回值**: `{"file_id": "...", "detected_type": "xlsx|csv|json", "rows": N, ...}`
- **错误状态**: 400（xls 拒绝、超大小）、401、403、404
- **当前限制**: 上限 50MB

---

## 模板

### POST /api/projects/{project_id}/templates
- **方法**: POST
- **路径**: `/api/projects/{project_id}/templates`
- **已实现**: YES（[backend/api/templates.py](file:///backend/api/templates.py)）
- **有测试**: YES（`tests/test_templates_api.py`）
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: multipart/form-data，字段 `file` + `template_type`（`market_research_template`/`product_development_template`）
- **返回值**: `{"template_id": "..."}`
- **错误状态**: 400、401、403、404
- **当前限制**: 无

---

## 任务

### GET /api/projects/{project_id}/jobs
- **方法**: GET
- **路径**: `/api/projects/{project_id}/jobs`
- **已实现**: YES（[backend/api/jobs.py](file:///backend/api/jobs.py)）
- **有测试**: YES（`tests/test_jobs_api.py`）
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: path param `project_id`
- **返回值**: `{"jobs": [...]}`
- **错误状态**: 401、403、404
- **当前限制**: 无

### POST /api/projects/{project_id}/jobs
- **方法**: POST
- **路径**: `/api/projects/{project_id}/jobs`（同一端点，POST 启动任务）
- **已实现**: YES
- **有测试**: YES
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: `{"phase": "phase_1|phase_2", "candidate_id": "...", "manual_inputs": {...}}`
- **返回值**: `{"job_id": "..."}`
- **错误状态**: 400（候选未确认）、401、403、404
- **当前限制**: Phase 2 需 candidate_id + manual_inputs

### GET /api/jobs/{job_id}
- **方法**: GET
- **路径**: `/api/jobs/{job_id}`
- **已实现**: YES
- **有测试**: YES
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: path param `job_id`
- **返回值**: `{"job_id": "...", "status": "...", "phase": "...", ...}`
- **错误状态**: 401、403、404
- **当前限制**: 无

### POST /api/jobs/{job_id}/cancel
- **方法**: POST
- **路径**: `/api/jobs/{job_id}/cancel`
- **已实现**: YES
- **有测试**: YES（`tests/test_task_cancellation.py`）
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: 无
- **返回值**: `{"status": "cancelled"}`
- **错误状态**: 401、403、404、409（已完成）
- **当前限制**: 无

---

## 候选

### GET /api/projects/{project_id}/candidates
- **方法**: GET
- **路径**: `/api/projects/{project_id}/candidates`
- **已实现**: YES（[backend/api/candidates.py](file:///backend/api/candidates.py)）
- **有测试**: YES（`tests/test_candidates_api.py`）
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: path param `project_id`
- **返回值**: `{"candidates": [...]}`
- **错误状态**: 401、403、404
- **当前限制**: 无

### POST /api/projects/{project_id}/candidates/{candidate_id}/confirm
- **方法**: POST
- **路径**: `/api/projects/{project_id}/candidates/{candidate_id}/confirm`
- **已实现**: YES
- **有测试**: YES（`tests/test_phase2_checkpoint.py`）
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: 无
- **返回值**: `{"status": "confirmed"}`
- **错误状态**: 401、403、404、409
- **当前限制**: 无

### POST /api/projects/{project_id}/candidates/{candidate_id}/reject
- **方法**: POST
- **路径**: `/api/projects/{project_id}/candidates/{candidate_id}/reject`
- **已实现**: YES
- **有测试**: YES
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: 无
- **返回值**: `{"status": "rejected"}`
- **错误状态**: 401、403、404、409
- **当前限制**: 无

---

## 人工输入

### GET /api/projects/{project_id}/manual-inputs
- **方法**: GET
- **路径**: `/api/projects/{project_id}/manual-inputs`
- **已实现**: YES（[backend/api/manual_inputs.py](file:///backend/api/manual_inputs.py)）
- **有测试**: YES（`tests/test_manual_inputs_api.py`、`tests/test_manual_inputs_empty.py`）
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: path param `project_id`
- **返回值**: `{"manual_inputs": {...}}`
- **错误状态**: 401、403、404
- **当前限制**: 无

### POST /api/projects/{project_id}/manual-inputs
- **方法**: POST
- **路径**: `/api/projects/{project_id}/manual-inputs`
- **已实现**: YES
- **有测试**: YES
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: `{"supplier": "...", "cost": ..., "moq": ..., "logistics": ..., "tariff": ...}`（空值允许）
- **返回值**: `{"status": "ok"}`
- **错误状态**: 400、401、403、404
- **当前限制**: 空值不替换为 0/默认/mock

---

## 输出

### GET /api/projects/{project_id}/outputs
- **方法**: GET
- **路径**: `/api/projects/{project_id}/outputs`
- **已实现**: YES（[backend/api/outputs.py](file:///backend/api/outputs.py)）
- **有测试**: YES（`tests/test_download_security.py`）
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: path param `project_id`
- **返回值**: `{"outputs": [...]}`
- **错误状态**: 401、403、404
- **当前限制**: 无

### GET /api/outputs/{output_id}/download
- **方法**: GET
- **路径**: `/api/outputs/{output_id}/download`
- **已实现**: YES
- **有测试**: YES（`tests/test_download_security.py` — 跨用户 403、路径穿越 400、未登记路径、无效 output_id）
- **登录要求**: YES
- **owner_id 校验**: YES
- **请求参数**: path param `output_id`
- **返回值**: 文件流
- **错误状态**: 400（路径穿越）、401、403（跨用户）、404
- **当前限制**: 本地文件，生产需签名 URL

---

## 设计文档中未实现的接口

> 以下接口在 tasks.md/spec.md 中提及，但**当前代码无实现**:

| 接口 | 状态 | 说明 |
|---|---|---|
| 生产签名下载 `/api/outputs/{output_id}/signed-url` | NOT_IMPLEMENTED | 仅本地文件流下载 |
| WebSocket 任务进度推送 | NOT_IMPLEMENTED | 仅轮询 `/api/jobs/{job_id}` |
| 管理员邀请码管理 API | NOT_IMPLEMENTED | 仅 `ADMIN_BOOTSTRAP_TOKEN` 引导 |
| 用户注册 API | NOT_IMPLEMENTED | 仅邀请码登录 |
| 密码重置 API | NOT_IMPLEMENTED | 无密码体系 |
