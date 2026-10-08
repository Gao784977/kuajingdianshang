# WORKFLOW_STATUS — 工作流细节

> 所有"是否完成"判断附测试名称或代码路径。

---

## 1. Phase 1 的实际 Agent 顺序

**来源**: [backend/config.py](file:///backend/config.py#L88-L117) `WORKFLOW_DEFINITION["phases"][0]["agents"]`

```
phase_1_research:
  1. input_validation
  2. workbook_detection
  3. schema_mapping
  4. excel_import
  5. url_fetch
  6. keyword
  7. market
  8. competitor
  9. brand_seller
  10. review
  11. opportunity
  12. product_candidate
```

**执行**: [backend/services/workflow_runner.py](file:///backend/services/workflow_runner.py) `_run_phase_1` 按 list 顺序调用，每个 Agent 执行前检查 `CancellationToken`。

## 2. Phase 2 的实际 Agent 顺序

**来源**: [backend/config.py](file:///backend/config.py#L108-L116) `WORKFLOW_DEFINITION["phases"][1]["agents"]`

```
phase_2_development:
  1. product_development
  2. profit
  3. report
  4. excel
```

**执行**: `_run_phase_2` 按顺序调用，含 `template_path` 参数。

## 3. workflow_runner.py 的入口

- **类**: `WorkflowRunner`
- **入口方法**:
  - `submit_phase_1(project_id, ...)` — 创建 job、启动线程、返回 `job_id`
  - `submit_phase_2(project_id, candidate_id, manual_inputs, ...)` — 读取 checkpoint、创建 job、启动线程
  - `cancel(job_id)` — 设置 CancellationToken

## 4. V31Workflow 的调用位置

- **Phase 1**: `_run_phase_1` 内部调用 `V31Workflow(...)` 执行调研，产出 candidates
- **Phase 2**: `_run_phase_2` 内部调用 `V31Workflow(...)` 并传入 `template_path`，执行开发规划 + 报告生成
- **V31Workflow 文件**: [src/modules/amazon/v31_workflow.py](file:///src/modules/amazon/v31_workflow.py)
- **测试**: `tests/test_phase2_checkpoint.py` 验证 Phase 2 真实调用 V31Workflow

## 5. checkpoint 的保存位置

- **保存触发**: Phase 1 完成（candidates 产出后）
- **保存方法**: `WorkflowRunner._save_checkpoint(job_id, checkpoint_data)`
- **存储位置**: `LocalJobStore` SQLite 表（`backend/storage/job_store.py`）
- **内容**: Phase 1 中间结果 + candidates + 输入参数

## 6. checkpoint 的读取位置

- **读取触发**: Phase 2 启动（`submit_phase_2` 调用后）
- **读取方法**: `WorkflowRunner._load_checkpoint(job_id)`
- **存储位置**: 同上 SQLite 表
- **测试**: `tests/test_phase2_checkpoint.py` 验证 Phase 2 读取原 checkpoint

## 7. 候选确认门禁

- **门禁位置**: `_run_phase_2` 开头检查 candidate 状态
- **状态**: 仅 `confirmed` 的 candidate 允许进入 Phase 2
- **状态枚举**: `pending_review`、`confirmed`、`rejected`（禁止 `approved`）
- **API**: `POST /api/projects/{project_id}/candidates/{candidate_id}/confirm`
- **测试**: `tests/test_candidates_api.py`、`tests/test_phase2_checkpoint.py`

## 8. Phase 2 是否真的避免重复执行 Phase 1

- **实现**: `_run_phase_2` 调用 `_load_checkpoint`，复用 Phase 1 结果，不再调用 Phase 1 Agent
- **测试**: `tests/test_phase2_checkpoint.py`（15 个测试，包含验证 Phase 1 Agent 调用次数不增加）
- **结论**: **DONE** — Phase 2 不重跑 Phase 1

## 9. 人工输入如何进入 Phase 2

- **提交**: `POST /api/projects/{project_id}/manual-inputs`
- **存储**: `LocalJobStore` 关联到 project_id
- **读取**: `_run_phase_2` 从 `manual_inputs` 参数接收
- **空值处理**: 空值保持空，不替换为 0/默认/mock
- **测试**: `tests/test_manual_inputs_empty.py`（5 个测试）

## 10. report/excel 输出如何生成

- **入口**: V31Workflow `_write_reports()` 方法
- **Markdown**: `_build_markdown_report()` — 10 节锁定顺序
- **JSON**: `to_dict()` 序列化
- **Excel**: 模板副本填充（[src/modules/amazon/template_builder.py](file:///src/modules/amazon/template_builder.py)）
- **输出目录**: `data/output/`，文件名带时间戳 `{project_name}_market_research_report_{timestamp}.xlsx`
- **测试**: `tests/test_template_integration.py`（验证用户上传模板实际进入报告生成）

## 11. 任务取消如何传递

- **API**: `POST /api/jobs/{job_id}/cancel`
- **机制**: `CancellationToken`（[backend/storage/base.py](file:///backend/storage/base.py)）
- **检查点**: 每个 Agent 执行前 + 循环中检查 `CancellationToken.is_cancelled()`
- **抛出**: 取消时抛出 `_TaskCancelled` 异常
- **状态**: job 状态置为 `cancelled`
- **事件**: 取消事件写入 `job_events` 表
- **测试**: `tests/test_task_cancellation.py`（16 个测试，验证后续 Agent 不启动、状态 cancelled、事件写入、无正式输出）

## 12. 任务失败如何处理

- **异常捕获**: `_run_phase_1`/`_run_phase_2` try/except 包裹
- **状态**: 失败时 job 状态置为 `failed`
- **事件**: 错误信息写入 `job_events`
- **输出**: 失败任务不生成正式报告
- **重试**: **未实现**（无自动重试机制）
- **死信**: **未实现**
- **超时恢复**: **未实现**

## 13. 当前是否支持断点恢复

- **本地**: YES — Phase 1 → Phase 2 通过 checkpoint 衔接
- **崩溃恢复**: PARTIAL — 若 Phase 1 完成、Phase 2 未启动，可重新提交 Phase 2
- **进程内恢复**: NO — 进程崩溃后，running 状态的 job 不会自动恢复
- **测试**: `tests/test_phase2_checkpoint.py` 验证 checkpoint 读取

## 14. 当前是否支持多实例恢复

- **NOT_IMPLEMENTED**
- **原因**: 本地 SQLite + 本地文件 + threading.Thread 无法跨实例共享
- **依赖**: 需生产数据库 + TOS + 真实队列
- **测试**: 无

---

## 任务状态枚举

- `pending` — 已创建未启动
- `running` — 执行中
- `waiting_for_confirmation` — Phase 1 完成，等待候选确认（Phase 1 专属）
- `cancelled` — 已取消
- `failed` — 失败
- `completed` — 完成（Phase 2 专属，含输出）

## candidate 状态枚举

- `pending_review` — 待审核
- `confirmed` — 已确认（可进入 Phase 2）
- `rejected` — 已拒绝（禁止 `approved`）
