# TEST_STATUS — 真实测试结果

> 执行时间: 2026-09-23
> 测试运行时无后端服务在运行；测试使用临时目录独立 SQLite，无共享 DB 文件依赖。

---

## 1. 全量测试命令

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## 2. 完整关键输出

```
Ran 699 tests in 15.817s

OK
```

- **exit code**: 0
- **日志副本**: `temp/handoff_test.log`

## 3. 测试文件总数

- **38** 个测试文件

## 4. 测试用例总数

- **699** 个测试用例

## 5. 通过数

- **699** 通过

## 6. 失败数

- **0** 失败

## 7. 跳过数

- **0** 跳过

## 8. 测试运行耗时

- **15.817 秒**

## 9. 是否依赖停止后端服务

- **NO** — 测试使用临时目录独立 SQLite（`tests/test_*.py` 中 `configure_paths(tmp_path)` 调用）
- 不要求手工先停止开发服务器才能通过

## 10. 是否依赖共享 SQLite 文件

- **NO** — 每个测试用例使用 `tempfile.mkdtemp()` 或 `tmp_path` fixture 独立数据库
- 无 `data/web.db` 共享依赖

## 11. 是否存在测试隔离问题

- **已修复** — V3.2 之前的测试存在共享 SQLite 文件依赖，已在本轮修复
- 当前每个测试清理自己的临时数据
- 测试日志中可能出现 `sqlite3` closed-DB 异常（teardown 触发，已被捕获，不影响 OK 结果）

## 12. 新增 V3.2 测试文件

| 测试文件 | 用例数 | 覆盖点 |
|---|---|---|
| [tests/test_cross_user_isolation.py](file:///tests/test_cross_user_isolation.py) | 25 | 双用户双 Session 真实路由隔离 |
| [tests/test_ssrf_dns.py](file:///tests/test_ssrf_dns.py) | 9 | DNS 解析后 IPv4/IPv6 私有地址、重定向到内网 |
| [tests/test_task_cancellation.py](file:///tests/test_task_cancellation.py) | 16 | CancellationToken 读取、后续 Agent 不启动、cancelled 状态、事件写入、无正式输出 |
| [tests/test_phase2_checkpoint.py](file:///tests/test_phase2_checkpoint.py) | 15 | checkpoint 保存/读取、Phase 1 调用次数不增加、candidate 确认门禁、checkpoint 缺失报错 |
| [tests/test_manual_inputs_empty.py](file:///tests/test_manual_inputs_empty.py) | 5 | 空字符串/null/未提供字段不替换为 0/默认/mock |
| [tests/test_download_security.py](file:///tests/test_download_security.py) | 6 | 跨用户 403、路径穿越 400、未登记路径、无效 output_id |
| [tests/test_template_integration.py](file:///tests/test_template_integration.py) | 6 | 用户上传模板实际进入报告生成、Sheet 名/顺序、原模板 SHA-256 不变 |
| **合计** | **82** | V3.2 新增 |

- **基线（V3.2 之前）**: 617
- **当前总数**: 617 + 82 = 699

## 13. CLI 测试结果

```powershell
# V2 CLI
python -m src.modules.analyze_opportunities --help
# exit 0 ✓

# V3 CLI（V31Workflow 入口）
python -m src.modules.amazon.workflow --help
# exit 0 ✓
# 支持: --input --output-dir --config --scenario --with-mock-data --export-intermediate --strict
```

- **`python -m src.cli`**: NOT_IMPLEMENTED（不存在该模块）

## 14. 浏览器测试结果

- **工具**: TRAE-browseruse skill（内置浏览器自动化）
- **测试环境**: 本地后端 `python -m backend.app` + `ADMIN_BOOTSTRAP_TOKEN=<LOCAL_ONLY>`
- **结果**: **8/11 步通过**

| 步骤 | 状态 | 说明 |
|---|---|---|
| 登录 | PASS | 邀请码登录成功 |
| 创建项目 | PASS | 项目创建成功 |
| 填写关键词/类目/URL | PASS | 表单提交成功 |
| 上传 xlsx/csv/json | PASS | 文件上传 + 检测成功 |
| 确认文件类型 | PASS | 文件检测结果正确 |
| 启动 Phase 1 | PASS | 任务创建 + running |
| 查看进度 | PASS | 轮询 job 状态 |
| 确认候选 | **NOT VERIFIED** | 未实际触发 UI 交互 |
| 填写人工信息 | **NOT VERIFIED** | 未实际触发 Phase 2 启动 |
| 启动 Phase 2 | **NOT VERIFIED** | 未实际触发 |
| 下载报告 | **NOT VERIFIED** | 未实际点击下载 |

- **页面错误**: 无
- **控制台错误**: 无
- **未验证原因**: 时间窗口内未完成候选确认交互的浏览器自动化；后续可补测

## 15. 未覆盖的高风险场景

- 模板保真逐项对比（合并单元格/样式/公式/批注/行高列宽/图片/图表/数据验证/冻结窗格/页面设置）
- 生产数据库并发
- TOS 存储适配
- RocketMQ 队列消费
- 多实例任务恢复
- 任务超时自动恢复
- 死信队列
- 生产监控告警
- HTTPS 部署
- API Gateway 路由

---

## 重点标记测试

### 双用户双 Session 隔离测试
- **文件**: `tests/test_cross_user_isolation.py`（25 个用例）
- **结论**: **PASS** — 真实双用户双 Session 路由验证，B 无法访问 A 的资源（403/404），A 仍可访问自己资源，API 不接受前端传入 owner_id/user_id 绕过 Session

### 跨用户下载测试
- **文件**: `tests/test_download_security.py`（6 个用例）
- **结论**: **PASS** — 跨用户下载 403、路径穿越 400、未登记路径、无效 output_id 均拦截

### DNS 解析后的 SSRF 测试
- **文件**: `tests/test_ssrf_dns.py`（9 个用例）
- **结论**: **PASS** — DNS 解析到 127.0.0.1/私有 IPv4/IPv6 回环均被阻止；URL 字符串检查与 DNS 解析后检查已区分

### 重定向到内网的 SSRF 测试
- **文件**: `tests/test_ssrf_dns.py`
- **结论**: **PASS** — 公网地址重定向到 localhost/内网地址，重定向目标重新经过 DNS/IP 校验，内网目标未请求

### 取消后不生成正式输出测试
- **文件**: `tests/test_task_cancellation.py`（16 个用例）
- **结论**: **PASS** — CancellationToken 被工作流读取，后续 Agent 不启动，状态 cancelled，事件写入 job_events，无正式报告/Excel 输出

### Phase 2 不重跑 Phase 1 测试
- **文件**: `tests/test_phase2_checkpoint.py`（15 个用例）
- **结论**: **PASS** — Phase 2 读取原 checkpoint，Phase 1 Agent 调用次数不增加，使用已确认 candidate 和人工输入，checkpoint 缺失返回明确错误不静默重跑

### 模板保真测试
- **文件**: `tests/test_template_integration.py`（6 个用例）
- **结论**: **PARTIAL** — Sheet 名/顺序 + 原模板 SHA-256 不变已验证；合并单元格/样式/公式/批注/行高列宽/图片/图表/数据验证/冻结窗格/页面设置**未逐项对比**

### 完整浏览器端到端测试
- **结论**: **PARTIAL** — 8/11 步通过，3 步 NOT VERIFIED（候选确认、Phase 2 启动、实际下载点击）
- **不能把静态 HTML 检查称作完整端到端验证**
