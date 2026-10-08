# KNOWN_ISSUES — 已知问题

> 按优先级分类:
> - **P0**: 安全、数据泄露、任务数据错误
> - **P1**: 核心流程无法完成
> - **P2**: 可靠性、测试或部署缺口
> - **P3**: 体验、文档或优化问题

---

## P0 问题

> 当前无 P0 问题。所有安全问题（SSRF、跨用户隔离、下载权限、路径穿越、邀请码哈希、CSRF）均有测试覆盖且通过。

---

## P1 问题

### P1-01: veFaaS Worker 仅为骨架

```text
编号: P1-01
优先级: P1
问题: deploy/veFaaS/worker_handler.py 仅返回骨架消息，无真实队列消费
影响: 生产长任务无法执行，阻塞生产部署
复现方式: 调用 worker_handler.handler() 查看返回消息
相关文件: deploy/veFaaS/worker_handler.py
当前状态: 骨架，未实现
建议修复方式: 接入 RocketMQ + 生产 DB + TOS，实现消费/重试/死信/超时恢复
验收标准: Worker 真实消费队列消息、执行 V31Workflow 阶段、状态持久化、失败重试
```

### P1-02: 生产数据库未接入

```text
编号: P1-02
优先级: P1
问题: 仅本地 SQLite，无生产数据库
影响: 多实例无法共享状态，阻塞生产部署
复现方式: 启动两个后端实例，状态不互通
相关文件: backend/storage/job_store.py、backend/storage/local_storage.py
当前状态: NOT_IMPLEMENTED
建议修复方式: 选择并接入生产数据库（MySQL/PostgreSQL），实现 ProductionJobStore
验收标准: 多实例共享状态、并发安全、事务保证
```

### P1-03: TOS 未接入

```text
编号: P1-03
优先级: P1
问题: 仅本地文件存储，无 TOS 对象存储
影响: 多实例无法访问文件，阻塞生产部署
复现方式: 启动两个实例，文件不互通
相关文件: backend/storage/local_storage.py
当前状态: NOT_IMPLEMENTED
建议修复方式: 接入火山引擎 TOS，实现 ProductionStorageBackend + 签名下载
验收标准: 文件上传/下载/签名 URL、多实例共享
```

### P1-04: RocketMQ 未接入

```text
编号: P1-04
优先级: P1
问题: 仅 threading.Thread 本地异步，无真实消息队列
影响: 长任务无法跨实例执行，阻塞生产部署
复现方式: 启动两个实例，任务只在创建实例执行
相关文件: backend/services/workflow_runner.py
当前状态: NOT_IMPLEMENTED
建议修复方式: 接入火山引擎 RocketMQ，实现队列生产/消费
验收标准: 任务跨实例执行、幂等、重试、死信
```

### P1-05: 多实例无法共享本地 SQLite 和本地文件

```text
编号: P1-05
优先级: P1
问题: 本地 SQLite + 本地文件 + threading.Thread 无跨实例共享
影响: 多实例部署失败
复现方式: 启动多实例，状态/文件不互通
相关文件: backend/storage/*、backend/services/workflow_runner.py
当前状态: NOT_IMPLEMENTED
建议修复方式: 完成 P1-02/03/04 后自动解决
验收标准: 多实例并发 + 状态一致
```

---

## P2 问题

### P2-01: 模板保真深度测试缺失

```text
编号: P2-01
优先级: P2
问题: 模板保真仅验证 Sheet 名/顺序 + SHA-256 不变，未逐项对比合并单元格/样式/公式/批注/行高列宽/图片/图表/数据验证/冻结窗格/页面设置
影响: 模板可能存在未被发现的样式丢失
复现方式: tests/test_template_integration.py 仅 6 个用例
相关文件: src/modules/amazon/template_builder.py、tests/test_template_integration.py
当前状态: PARTIAL
建议修复方式: 补充逐项结构对比测试（合并单元格范围、单元格样式、公式字符串、批注、行高列宽、图片布局、图表对象、数据验证规则、冻结窗格、页面设置）
验收标准: 所有模板保真项有自动化测试覆盖且通过
```

### P2-02: 浏览器端到端未完整验证

```text
编号: P2-02
优先级: P2
问题: 浏览器流程 8/11 步通过，3 步 NOT VERIFIED（候选确认交互、Phase 2 启动、实际下载点击）
影响: 完整用户流程未端到端验证
复现方式: 见 TEST_STATUS.md 第 14 节
相关文件: frontend/app.js、tests/（无浏览器测试文件）
当前状态: PARTIAL
建议修复方式: 使用 TRAE-browseruse skill 补完 3 步交互测试
验收标准: 11/11 步通过，记录页面/控制台错误
```

### P2-03: 任务超时恢复未实现

```text
编号: P2-03
优先级: P2
问题: 无任务超时自动恢复机制
影响: running 状态任务崩溃后不会自动恢复
复现方式: 模拟进程崩溃，running 状态 job 不会恢复
相关文件: backend/services/workflow_runner.py
当前状态: NOT_IMPLEMENTED
建议修复方式: 实现超时检测 + checkpoint 恢复 + 死信转移
验收标准: 超时任务自动标记 failed，可选重试
```

### P2-04: 测试日志 sqlite3 closed-DB 异常

```text
编号: P2-04
优先级: P2
问题: 测试 teardown 阶段可能出现 sqlite3 closed-DB 异常
影响: 不影响测试 OK 结果，但日志噪音
复现方式: 运行全量测试，查看 stderr
相关文件: tests/test_*.py、backend/storage/job_store.py
当前状态: 已捕获，不影响结果
建议修复方式: 改进 teardown 顺序，确保连接关闭前完成所有操作
验收标准: 测试日志无 closed-DB 异常
```

---

## P3 问题

### P3-01: 日志系统性脱敏缺失

```text
编号: P3-01
优先级: P3
问题: 邀请码已脱敏，但其他字段（URL、文件名等）未系统性脱敏
影响: 生产日志可能含敏感信息
相关文件: backend/services/auth_service.py
当前状态: 部分实现
建议修复方式: 增加日志脱敏过滤器中间件
验收标准: 所有日志字段经脱敏处理
```

### P3-02: 无 pyproject.toml/setup.py

```text
编号: P3-02
优先级: P3
问题: 仅有 requirements.txt，无 pyproject.toml 或 setup.py
影响: 包管理不规范
相关文件: requirements.txt
当前状态: 无
建议修复方式: 增加 pyproject.toml
验收标准: 支持 pip install -e .
```

---

## 历史问题（已修复）

> 用户指令中提到的一些历史问题已在 V3.2 本轮修复，附证据:

| 历史问题 | 状态 | 证据 |
|---|---|---|
| 双用户隔离缺少真实测试 | DONE | `tests/test_cross_user_isolation.py`（25 用例真实路由） |
| SSRF 缺 DNS mock 和重定向测试 | DONE | `tests/test_ssrf_dns.py`（9 用例 mock DNS + 重定向） |
| 取消任务缺完整行为测试 | DONE | `tests/test_task_cancellation.py`（16 用例含无正式输出验证） |
| Phase 2 不重复执行缺测试 | DONE | `tests/test_phase2_checkpoint.py`（15 用例含调用次数验证） |
| 跨用户下载缺测试 | DONE | `tests/test_download_security.py`（6 用例跨用户 403 + 路径穿越） |
| Web 上传模板可能没有传入报告生成 | DONE | `tests/test_template_integration.py`（验证实际进入报告生成） |

---

## P0/P1 计数

- **P0**: 0
- **P1**: 5
- **P2**: 4
- **P3**: 2
