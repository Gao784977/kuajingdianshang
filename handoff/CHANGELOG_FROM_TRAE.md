# CHANGELOG_FROM_TRAE — Trae Work 在当前工作区完成的工作

> 当前环境未安装 git，无法提供 commit/diff 级别的变更记录。
> 以下内容基于当前文件扫描和实际测试命令整理。
> 不编造不存在的提交记录。

---

## 1. 新增文件

### backend/ — Web 后端（V3.2 新增）

```
backend/app.py                              — HTTP 入口 + MAIN_ROUTER
backend/config.py                           — 环境变量配置
backend/__init__.py
backend/api/__init__.py                     — build_request/Response
backend/api/auth.py                         — 登录/登出/me
backend/api/projects.py                     — 项目 CRUD
backend/api/uploads.py                     — 文件上传 + 检测
backend/api/jobs.py                         — 任务查询 + cancel
backend/api/candidates.py                   — 候选确认/拒绝
backend/api/manual_inputs.py                — 人工输入
backend/api/outputs.py                      — 输出列表 + 下载
backend/api/templates.py                    — 模板上传/绑定
backend/api/validation.py                   — 校验规则
backend/api/health.py                       — /api/health + /api/workflow/definition
backend/services/auth_service.py            — 邀请码/Session/CSRF/RateLimit
backend/services/workflow_runner.py         — WorkflowRunner + Phase 1/2 + cancel
backend/services/url_security.py            — SSRF 防护 + DNS + 重定向
backend/services/file_detection.py          — 文件类型检测
backend/storage/__init__.py
backend/storage/base.py                     — CancellationToken + 抽象基类
backend/storage/local_storage.py            — LocalStorageBackend
backend/storage/job_store.py                — LocalJobStore + SQLite schema
backend/storage/database.py                 — configure_paths + 单例
```

### frontend/ — 前端工作台（V3.2 新增）

```
frontend/index.html                         — 入口 HTML
frontend/app.js                             — 主逻辑 + 动态 Agent 渲染
frontend/api.js                             — API 调用封装
frontend/styles.css                         — 样式
```

### deploy/ — 部署适配（V3.2 新增）

```
deploy/veFaaS/handler.py                     — veFaaS API Handler（真实可用）
deploy/veFaaS/worker_handler.py             — veFaaS Worker Handler（骨架）
deploy/tos/static_hosting.md                — TOS 静态托管文档
deploy/api_gateway/routes.md                — API Gateway 路由文档
```

### tests/ — V3.2 新增测试（82 用例）

```
tests/test_cross_user_isolation.py           — 25 用例 双用户双 Session 隔离
tests/test_ssrf_dns.py                      — 9 用例 DNS/重定向 SSRF
tests/test_task_cancellation.py             — 16 用例 任务取消
tests/test_phase2_checkpoint.py             — 15 用例 Phase 2 checkpoint
tests/test_manual_inputs_empty.py           — 5 用例 人工输入空值
tests/test_download_security.py             — 6 用例 下载安全
tests/test_template_integration.py           — 6 用例 模板集成
```

### handoff/ — 本交接包（本轮新增）

```
handoff/README.md
handoff/PROJECT_STATUS.md
handoff/ARCHITECTURE.md
handoff/FILE_INVENTORY.md
handoff/API_INVENTORY.md
handoff/WORKFLOW_STATUS.md
handoff/TEST_STATUS.md
handoff/SECURITY_STATUS.md
handoff/DEPLOYMENT_STATUS.md
handoff/KNOWN_ISSUES.md
handoff/NEXT_TASKS.md
handoff/DECISIONS.md
handoff/CHANGELOG_FROM_TRAE.md
handoff/MANIFEST.json
```

### 配置/文档（V3.2 新增）

```
.env.example                                — 环境变量样例（无密钥）
.trae/specs/v3_2_web_backend/tasks.md       — V3.2 任务清单
.trae/specs/v3_2_web_backend/spec.md       — V3.2 规范
```

---

## 2. 修改文件

> 无 git 历史，无法提供 diff。
> 基于 V3.1 → V3.2 期间的工作记录，以下文件被修改或扩展:

- `src/modules/amazon/v31_workflow.py` — 增加 `template_path` 参数支持，接入用户上传模板
- `requirements.txt` — 维持 `openpyxl>=3.1.0`（无新增依赖）

> **本轮（交接包生成）未修改任何业务代码**。

---

## 3. 新增 API

| HTTP 方法 | 路径 | 模块 |
|---|---|---|
| GET | /api/health | backend/api/health.py |
| GET | /api/workflow/definition | backend/api/health.py |
| POST | /api/auth/login | backend/api/auth.py |
| POST | /api/auth/logout | backend/api/auth.py |
| GET | /api/auth/me | backend/api/auth.py |
| GET | /api/projects | backend/api/projects.py |
| POST | /api/projects | backend/api/projects.py |
| GET | /api/projects/{project_id} | backend/api/projects.py |
| POST | /api/projects/{project_id}/files | backend/api/uploads.py |
| POST | /api/projects/{project_id}/templates | backend/api/templates.py |
| GET | /api/projects/{project_id}/jobs | backend/api/jobs.py |
| POST | /api/projects/{project_id}/jobs | backend/api/jobs.py |
| GET | /api/jobs/{job_id} | backend/api/jobs.py |
| POST | /api/jobs/{job_id}/cancel | backend/api/jobs.py |
| GET | /api/projects/{project_id}/candidates | backend/api/candidates.py |
| POST | /api/projects/{project_id}/candidates/{candidate_id}/confirm | backend/api/candidates.py |
| POST | /api/projects/{project_id}/candidates/{candidate_id}/reject | backend/api/candidates.py |
| GET | /api/projects/{project_id}/manual-inputs | backend/api/manual_inputs.py |
| POST | /api/projects/{project_id}/manual-inputs | backend/api/manual_inputs.py |
| GET | /api/projects/{project_id}/outputs | backend/api/outputs.py |
| GET | /api/outputs/{output_id}/download | backend/api/outputs.py |

---

## 4. 新增测试

- **新增测试文件数**: 7（V3.2 本轮）
- **新增测试用例数**: 82
- **基线**: 617 → **当前总数**: 699
- **测试结果**: 699/699 pass（exit 0）

详见 [TEST_STATUS.md](file:///handoff/TEST_STATUS.md)。

---

## 5. 新增前端功能

- 邀请码登录界面
- 项目管理（创建/列表）
- 文件上传 + 类型检测显示
- 任务启动 + 状态轮询
- 候选列表 + 确认/拒绝交互
- 人工输入表单
- 输出列表 + 下载
- 动态 Agent 渲染（从 `/api/workflow/definition` 获取顺序）

---

## 6. 新增部署骨架

- veFaaS API Handler（真实可用）
- veFaaS Worker Handler（骨架，无真实队列）
- TOS 静态托管文档
- API Gateway 路由文档

---

## 7. 已知未完成项

- veFaaS Worker Handler 仅为骨架（无真实队列消费）
- 生产数据库未接入
- TOS 未接入
- RocketMQ 未接入
- 多实例不支持
- 任务超时恢复未实现
- 签名下载未实现
- 生产 Session Secret 未配置
- HTTPS 未配置
- API Gateway 仅文档
- 监控告警未实现
- 模板保真逐项对比测试未完成
- 浏览器端到端 3 步未验证

详见 [KNOWN_ISSUES.md](file:///handoff/KNOWN_ISSUES.md)。

---

## 8. 未执行的工作

- 生产云服务接入（TOS、生产数据库、RocketMQ）
- veFaaS Worker 真实队列消费实现
- 多实例并发验证
- 生产监控告警
- HTTPS 部署
- 模板保真逐项对比测试
- 浏览器端到端 3 步补测

---

## 9. 没有做出的承诺

- **不声称生产可用**: 当前仅本地可用，生产部署未完成
- **不声称浏览器端到端完整验证**: 8/11 步通过，3 步 NOT VERIFIED
- **不声称模板 100% 保真**: 仅 Sheet 名/顺序 + SHA-256 不变已验证
- **不声称所有测试覆盖所有场景**: 高风险生产场景未覆盖
- **不声称 veFaaS Worker 已完成**: 仅为骨架
- **不修改 src/core/agent.py**: 保持占位符状态
- **不接入云服务**: 本轮不接入 TOS/RocketMQ/生产数据库
- **不实现新功能**: 本轮（交接包生成）仅做工程盘点和文档

---

## 10. 本轮（交接包生成）工作

- 创建 `handoff/` 目录
- 生成 14 份交接文件
- 执行全量测试（699/699 pass）
- CLI 冒烟测试（V2 + V3 通过）
- 密钥扫描（无硬编码）
- 确认 `src/core/agent.py` 未修改
- **未修改任何业务代码**
- **未删除任何现有文件**
- **未接入云服务**
- **未部署**
