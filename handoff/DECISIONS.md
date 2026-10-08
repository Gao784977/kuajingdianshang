# DECISIONS — 已做出的重要决策

> 每条决策: 决策 / 原因 / 影响 / 相关文件 / 是否可变更

---

## 决策 1: 不修改 src/core/agent.py

- **决策**: src/core/agent.py 保持占位符状态，业务逻辑全部下沉到 src/modules/
- **原因**: 保持核心 Agent 契约稳定，避免功能工作污染核心
- **影响**: 核心文件永不修改，所有业务在 modules
- **相关文件**: [src/core/agent.py](file:///src/core/agent.py)
- **是否可变更**: NO — 除非用户明确授权

## 决策 2: 本地先使用 Python 标准库、SQLite、本地文件和 threading

- **决策**: 本地开发环境使用 Python 标准库 + SQLite + 本地文件 + threading.Thread
- **原因**: 减少依赖、便于单机调试、符合"默认标准库"约束
- **影响**: 本地单进程，无生产并发能力
- **相关文件**: [backend/storage/job_store.py](file:///backend/storage/job_store.py)、[backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)、[requirements.txt](file:///requirements.txt)
- **是否可变更**: YES — 生产适配层另起

## 决策 3: 生产环境不能依赖本地线程、本地文件和单实例内存

- **决策**: 生产部署必须替换为生产数据库 + TOS + 真实队列
- **原因**: 本地方案无法跨实例共享，veFaaS 函数不能依赖后台线程
- **影响**: 阻塞生产部署，需实现 ProductionStorageBackend/ProductionJobStore/ProductionTaskRunner
- **相关文件**: [deploy/veFaaS/worker_handler.py](file:///deploy/veFaaS/worker_handler.py)
- **是否可变更**: NO — 硬性约束

## 决策 4: xlsx/csv/json 正式支持

- **决策**: 文件上传白名单为 xlsx、csv、json
- **原因**: 覆盖 Excel/CSV/JSON 三种主流输入格式
- **影响**: 三种格式有完整检测 + 导入逻辑
- **相关文件**: [backend/config.py](file:///backend/config.py#L69)、[backend/services/file_detection.py](file:///backend/services/file_detection.py)、[src/modules/amazon/importers/](file:///src/modules/amazon/importers/)
- **是否可变更**: YES — 可扩展其他格式

## 决策 5: xls 当前拒绝

- **决策**: xls 文件明确拒绝并提示转换为 xlsx
- **原因**: xls 为旧格式，openpyxl 不支持，安全风险高
- **影响**: 上传 xls 返回 400 + 提示
- **相关文件**: [backend/config.py](file:///backend/config.py#L69)、[backend/api/uploads.py](file:///backend/api/uploads.py)
- **是否可变更**: YES — 如需支持可引入 xlrd

## 决策 6: URL 默认关闭

- **决策**: URL_FETCH_ENABLED 默认 False，需 CLI 参数 `--allow-url-fetch` 或环境变量显式开启
- **原因**: 防止意外网络访问、避免 SSRF 风险
- **影响**: 默认不访问任何 URL，测试用 mock transport
- **相关文件**: [backend/config.py](file:///backend/config.py#L78)、[backend/services/url_security.py](file:///backend/services/url_security.py)
- **是否可变更**: NO — 硬性安全约束

## 决策 7: 产品候选统一使用 pending_review、confirmed、rejected

- **决策**: candidate 状态枚举固定为 pending_review/confirmed/rejected，禁止 approved
- **原因**: 避免状态命名不一致、明确审核语义
- **影响**: 前端、后端、测试统一使用该枚举
- **相关文件**: [backend/api/candidates.py](file:///backend/api/candidates.py)、[backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)
- **是否可变更**: NO — 硬性约束

## 决策 8: Phase 1 和 Phase 2 使用 checkpoint

- **决策**: Phase 1 完成后保存 checkpoint，Phase 2 读取复用，不重跑 Phase 1
- **原因**: 性能、断点恢复、避免重复计算
- **影响**: Phase 2 必须有 checkpoint，缺失报错不静默重跑
- **相关文件**: [backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)（`_save_checkpoint`/`_load_checkpoint`）
- **是否可变更**: NO — 硬性约束

## 决策 9: 模板必须复制后处理，不能修改原始模板

- **决策**: 报告生成时复制模板副本，原模板 SHA-256 不变
- **原因**: 保护用户上传模板、可重复使用
- **影响**: template_builder 复制副本后填充
- **相关文件**: [src/modules/amazon/template_builder.py](file:///src/modules/amazon/template_builder.py)
- **是否可变更**: NO — 硬性约束

## 决策 10: 生产云服务尚未接入时不能声称生产可用

- **决策**: 当前版本仅本地可用，不能声称生产可用
- **原因**: 缺少 TOS、生产数据库、真实队列、签名下载、HTTPS、多实例
- **影响**: DEPLOYMENT_STATUS.md 明确声明
- **相关文件**: [handoff/DEPLOYMENT_STATUS.md](file:///handoff/DEPLOYMENT_STATUS.md)
- **是否可变更**: NO — 硬性约束

## 决策 11: 前端 Agent 顺序必须从 GET /api/workflow/definition 动态获取

- **决策**: 前端不硬编码 Agent 顺序，从 `/api/workflow/definition` 接口动态获取
- **原因**: 后端 WORKFLOW_DEFINITION 为唯一真相源
- **影响**: 前端 app.js 动态渲染
- **相关文件**: [backend/api/health.py](file:///backend/api/health.py#L19)、[backend/config.py](file:///backend/config.py#L88)、[frontend/app.js](file:///frontend/app.js)
- **是否可变更**: NO — 硬性约束

## 决策 12: 任务取消需通过 CancellationToken 实现

- **决策**: Agent 执行前及循环中检查 CancellationToken，不只改 DB 状态
- **原因**: 真实协作取消，避免后续 Agent 继续启动
- **影响**: 工作流含取消检查点
- **相关文件**: [backend/storage/base.py](file:///backend/storage/base.py)、[backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py)
- **是否可变更**: NO — 硬性约束

## 决策 13: 配置中的枚举值必须与输入校验规则一致

- **决策**: 后端 config 与前端校验规则统一枚举
- **原因**: 避免前后端不一致
- **影响**: candidate 状态、validation_status、review_status 等枚举统一
- **相关文件**: [backend/config.py](file:///backend/config.py)、[backend/api/validation.py](file:///backend/api/validation.py)
- **是否可变更**: NO — 硬性约束

## 决策 14: 不允许覆盖历史报告，输出文件名必须带时间戳或版本号

- **决策**: 输出文件名格式 `{project_name}_market_research_report_{timestamp}.xlsx`
- **原因**: 保留历史、可追溯
- **影响**: V31Workflow `_write_reports()` 自动带时间戳
- **相关文件**: [src/modules/amazon/v31_workflow.py](file:///src/modules/amazon/v31_workflow.py)
- **是否可变更**: NO — 硬性约束
