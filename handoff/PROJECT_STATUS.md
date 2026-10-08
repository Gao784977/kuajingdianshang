# PROJECT_STATUS — 功能状态分类

> 评分标准:
> - **DONE**: 有代码和测试证据
> - **PARTIAL**: 部分实现、只有 mock 或测试覆盖不足
> - **NOT_VERIFIED**: 无法通过现有代码和测试证明
> - **NOT_IMPLEMENTED**: 明确没有实现
> - **BLOCKED**: 因外部资源或配置缺失无法继续

---

## 1. 本地后端

- **状态**: DONE
- **证据文件**: [backend/app.py](file:///backend/app.py)、[backend/config.py](file:///backend/config.py)、[backend/api/](file:///backend/api/)
- **证据函数或测试**: `MAIN_ROUTER` 聚合 10 个子路由；`tests/test_health.py`；`tests/test_backend_app.py`
- **当前限制**: 基于 `http.server.ThreadingHTTPServer`，单进程，无生产级并发
- **下一步**: 生产部署前替换为 veFaaS + 队列架构

## 2. 前端工作台

- **状态**: DONE
- **证据文件**: [frontend/index.html](file:///frontend/index.html)、[frontend/app.js](file:///frontend/app.js)、[frontend/api.js](file:///frontend/api.js)
- **证据函数或测试**: 后端 `frontend/` 静态服务；浏览器流程测试 8/11 步通过
- **当前限制**: 静态文件无 SSR；3 步未验证（候选确认交互、Phase 2 启动、实际下载点击）
- **下一步**: 补全浏览器端到端验证

## 3. 用户登录

- **状态**: DONE
- **证据文件**: [backend/services/auth_service.py](file:///backend/services/auth_service.py)、[backend/api/auth.py](file:///backend/api/auth.py)
- **证据函数或测试**: `AuthService.login`、`AuthService.create_session`；`tests/test_auth_invitation.py`
- **当前限制**: 邀请码需通过 `ADMIN_BOOTSTRAP_TOKEN` 引导创建
- **下一步**: 生产环境用 OAuth/SSO 替代

## 4. 用户隔离

- **状态**: DONE
- **证据文件**: [backend/services/auth_service.py](file:///backend/services/auth_service.py)（`require_session` 装饰器）
- **证据函数或测试**: `tests/test_cross_user_isolation.py`（25 个测试，双用户双 Session 真实路由）
- **当前限制**: 仅本地单进程验证
- **下一步**: 多实例场景需共享 DB

## 5. 项目管理

- **状态**: DONE
- **证据文件**: [backend/api/projects.py](file:///backend/api/projects.py)
- **证据函数或测试**: `tests/test_projects_api.py`、`tests/test_cross_user_isolation.py`
- **当前限制**: SQLite 单文件
- **下一步**: 生产迁移到共享数据库

## 6. 文件上传

- **状态**: DONE
- **证据文件**: [backend/api/uploads.py](file:///backend/api/uploads.py)、[backend/services/file_detection.py](file:///backend/services/file_detection.py)
- **证据函数或测试**: `tests/test_uploads_api.py`、`tests/test_file_detection.py`
- **当前限制**: 上限 50MB（`MAX_UPLOAD_SIZE_MB`）
- **下一步**: 生产用 TOS 替代本地存储

## 7. xlsx/csv/json 文件检测

- **状态**: DONE
- **证据文件**: [backend/services/file_detection.py](file:///backend/services/file_detection.py)、[src/modules/amazon/importers/detector.py](file:///src/modules/amazon/importers/detector.py)
- **证据函数或测试**: `tests/test_file_detection.py`
- **当前限制**: 无
- **下一步**: 无

## 8. xls 拒绝

- **状态**: DONE
- **证据文件**: [backend/config.py](file:///backend/config.py#L69) `ALLOWED_UPLOAD_EXTENSIONS = {"xlsx", "csv", "json"}`
- **证据函数或测试**: `tests/test_uploads_api.py` 中 xls 拒绝用例
- **当前限制**: 无
- **下一步**: 无

## 9. URL 默认关闭

- **状态**: DONE
- **证据文件**: [backend/config.py](file:///backend/config.py#L78) `URL_FETCH_ENABLED = _env_bool("URL_FETCH_ENABLED", False)`
- **证据函数或测试**: `tests/test_ssrf_dns.py`（默认关闭用例）
- **当前限制**: 无
- **下一步**: 无

## 10. SSRF 防护

- **状态**: DONE
- **证据文件**: [backend/services/url_security.py](file:///backend/services/url_security.py)
- **证据函数或测试**: `tests/test_ssrf_dns.py`（9 个测试：DNS mock 到 127.0.0.1/私有 IPv4/IPv6 回环、重定向到内网）
- **当前限制**: 使用 mock transport，未对真实环境验证
- **下一步**: 生产部署时配合出网防火墙

## 11. 异步任务

- **状态**: DONE（本地 threading 实现）
- **证据文件**: [backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)、[backend/storage/job_store.py](file:///backend/storage/job_store.py)
- **证据函数或测试**: `tests/test_jobs_api.py`
- **当前限制**: 单进程线程模型，生产不可用
- **下一步**: 替换为真实消息队列 + Worker

## 12. 任务取消

- **状态**: DONE
- **证据文件**: [backend/storage/base.py](file:///backend/storage/base.py)（`CancellationToken`、`_TaskCancelled`）、[backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)（`cancel`）
- **证据函数或测试**: `tests/test_task_cancellation.py`（16 个测试：CancellationToken 读取、后续 Agent 不启动、状态 cancelled、事件写入、无正式输出）
- **当前限制**: 无
- **下一步**: 生产环境需队列级取消

## 13. WorkflowCheckpoint

- **状态**: DONE
- **证据文件**: [backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)（`_save_checkpoint`、`_load_checkpoint`）
- **证据函数或测试**: `tests/test_phase2_checkpoint.py`（15 个测试）
- **当前限制**: 仅本地 SQLite 存储
- **下一步**: 生产迁移到共享 DB

## 14. Phase 1

- **状态**: DONE
- **证据文件**: [backend/config.py](file:///backend/config.py#L88-L117) `WORKFLOW_DEFINITION`、[backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)（`submit_phase_1`、`_run_phase_1`）
- **证据函数或测试**: `tests/test_phase2_checkpoint.py`、`tests/test_jobs_api.py`
- **当前限制**: 12 个 Agent（input_validation/workbook_detection/schema_mapping/excel_import/url_fetch/keyword/market/competitor/brand_seller/review/opportunity/product_candidate）
- **下一步**: 无

## 15. Phase 2

- **状态**: DONE
- **证据文件**: [backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)（`submit_phase_2`、`_run_phase_2`）
- **证据函数或测试**: `tests/test_phase2_checkpoint.py`（验证不重跑 Phase 1、读取原 checkpoint、使用已确认 candidate）
- **当前限制**: 4 个 Agent（product_development/profit/report/excel）
- **下一步**: 无

## 16. 产品候选确认

- **状态**: DONE
- **证据文件**: [backend/api/candidates.py](file:///backend/api/candidates.py)、[backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)（候选门禁）
- **证据函数或测试**: `tests/test_candidates_api.py`、`tests/test_phase2_checkpoint.py`
- **当前限制**: 状态仅 `pending_review`/`confirmed`/`rejected`
- **下一步**: 无

## 17. 人工供应链输入

- **状态**: DONE
- **证据文件**: [backend/api/manual_inputs.py](file:///backend/api/manual_inputs.py)
- **证据函数或测试**: `tests/test_manual_inputs_api.py`、`tests/test_manual_inputs_empty.py`（5 个测试：空值不被替换为 0/默认/mock）
- **当前限制**: 无
- **下一步**: 无

## 18. 模板上传

- **状态**: DONE
- **证据文件**: [backend/api/templates.py](file:///backend/api/templates.py)
- **证据函数或测试**: `tests/test_templates_api.py`
- **当前限制**: 无
- **下一步**: 无

## 19. 模板绑定

- **状态**: DONE
- **证据文件**: [backend/api/templates.py](file:///backend/api/templates.py)（绑定到 project）
- **证据函数或测试**: `tests/test_templates_api.py`
- **当前限制**: 无
- **下一步**: 无

## 20. 模板保真

- **状态**: PARTIAL
- **证据文件**: [src/modules/amazon/template_builder.py](file:///src/modules/amazon/template_builder.py)
- **证据函数或测试**: `tests/test_template_integration.py`（6 个测试）；Sheet 名/顺序 + 原模板 SHA-256 不变已验证
- **当前限制**: **未逐项对比**: 合并单元格、样式、公式、批注、行高列宽、图片、图表、数据验证、冻结窗格、页面设置
- **下一步**: 补齐逐项结构对比测试

## 21. 报告生成

- **状态**: DONE
- **证据文件**: [src/modules/amazon/v31_workflow.py](file:///src/modules/amazon/v31_workflow.py)（`_write_reports`）、[backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)
- **证据函数或测试**: `tests/test_template_integration.py`（验证用户上传模板实际进入报告生成）
- **当前限制**: 无
- **下一步**: 无

## 22. 输出下载

- **状态**: DONE
- **证据文件**: [backend/api/outputs.py](file:///backend/api/outputs.py)
- **证据函数或测试**: `tests/test_download_security.py`（6 个测试：跨用户 403、路径穿越 400、未登记路径、无效 output_id）
- **当前限制**: 本地文件存储
- **下一步**: 生产用 TOS + 签名 URL

## 23. CLI 兼容性

- **状态**: DONE
- **证据文件**: [src/modules/analyze_opportunities.py](file:///src/modules/analyze_opportunities.py)（V2）、[src/modules/amazon/workflow.py](file:///src/modules/amazon/workflow.py)（V3）
- **证据函数或测试**: CLI 冒烟 `--help` exit 0；`tests/test_amazon_v31_workflow.py`
- **当前限制**: 无 `src/cli` 模块
- **下一步**: 无

## 24. veFaaS API Handler

- **状态**: DONE（真实可用）
- **证据文件**: [deploy/veFaaS/handler.py](file:///deploy/veFaaS/handler.py)
- **证据函数或测试**: `handler()` 通过 `MAIN_ROUTER` 真实派发；复用本地路由
- **当前限制**: 不含后台线程（veFaaS 函数限制）；长任务需走队列
- **下一步**: Worker 接入真实队列

## 25. veFaaS Worker Handler

- **状态**: PARTIAL（骨架）
- **证据文件**: [deploy/veFaaS/worker_handler.py](file:///deploy/veFaaS/worker_handler.py)
- **证据函数或测试**: `handler()` 仅返回 "Worker handler skeleton. Real queue/DB/TOS integration required."
- **当前限制**: **无真实队列消费、无生产 DB、无 TOS、无重试/死信/超时恢复**
- **下一步**: 接入 RocketMQ + 生产 DB + TOS

## 26. 生产数据库

- **状态**: NOT_IMPLEMENTED
- **证据文件**: 无（仅 [backend/storage/local_storage.py](file:///backend/storage/local_storage.py) 本地 SQLite）
- **证据函数或测试**: 无
- **当前限制**: 阻塞生产部署
- **下一步**: 选择并接入生产数据库（MySQL/PostgreSQL/Redis）

## 27. TOS（对象存储）

- **状态**: NOT_IMPLEMENTED
- **证据文件**: 无（仅本地文件系统 `data/web_storage/`、`data/output/`）
- **证据函数或测试**: 无
- **当前限制**: 阻塞生产部署
- **下一步**: 接入火山引擎 TOS

## 28. RocketMQ 或其他队列

- **状态**: NOT_IMPLEMENTED
- **证据文件**: 无（仅 `threading.Thread` 本地异步）
- **证据函数或测试**: 无
- **当前限制**: 阻塞生产部署
- **下一步**: 接入火山引擎 RocketMQ

## 29. 多实例并发

- **状态**: NOT_IMPLEMENTED
- **证据文件**: 无（本地 SQLite + 本地文件无法跨实例共享）
- **证据函数或测试**: 无
- **当前限制**: 本地单实例
- **下一步**: 完成生产 DB + TOS + 队列后验证

## 30. 生产监控和恢复

- **状态**: NOT_IMPLEMENTED
- **证据文件**: 无
- **证据函数或测试**: 无
- **当前限制**: 阻塞生产部署
- **下一步**: 实现结构化日志、监控告警、任务超时恢复
