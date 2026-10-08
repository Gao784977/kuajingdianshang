```text
这是 Trae Work 生成的工程交接包，供 GPT-5.6-terra 继续开发。
本文档不是代码正确性的保证。下一位代理必须以当前代码、测试和实际命令输出为准。
```

# 工程交接包 README

## 1. 项目名称和目标

- **项目名称**: Amazon 选品机会分析工具（V3.2 Web Backend + V3.1 工作流）
- **目标**: 基于 Python 标准库实现的亚马逊市场调研与产品开发规划工具，支持 Excel/CSV/JSON 输入、多 Agent 工作流、双阶段（Phase 1 调研 / Phase 2 开发）执行、模板化报告生成。V3.2 增加本地 Web 后端、用户隔离、邀请码登录、异步任务、断点恢复和 veFaaS 部署适配骨架。

## 2. 当前版本

- **APP_VERSION**: `v3.2`（见 [backend/config.py](file:///backend/config.py#L12)）
- **工作流版本**: V3.1（V31Workflow）
- **交接包版本**: 1.0
- **生成时间**: 2026-09-23

## 3. 当前实现阶段

- 本地开发环境：**可用**（699/699 测试通过）
- 生产部署：**未就绪**（veFaaS Worker 仅为骨架，TOS/生产数据库/RocketMQ 未接入）
- 浏览器端到端：**部分验证**（8/11 步通过，3 步 NOT VERIFIED）

## 4. 推荐阅读顺序

1. 本 README
2. [PROJECT_STATUS.md](file:///handoff/PROJECT_STATUS.md) — 功能状态分类
3. [KNOWN_ISSUES.md](file:///handoff/KNOWN_ISSUES.md) — 已知问题（P0/P1/P2/P3）
4. [NEXT_TASKS.md](file:///handoff/NEXT_TASKS.md) — 下一步任务
5. [ARCHITECTURE.md](file:///handoff/ARCHITECTURE.md) — 真实架构
6. [WORKFLOW_STATUS.md](file:///handoff/WORKFLOW_STATUS.md) — 工作流细节
7. [TEST_STATUS.md](file:///handoff/TEST_STATUS.md) — 测试结果
8. [API_INVENTORY.md](file:///handoff/API_INVENTORY.md) — API 清单
9. [FILE_INVENTORY.md](file:///handoff/FILE_INVENTORY.md) — 文件清单
10. [SECURITY_STATUS.md](file:///handoff/SECURITY_STATUS.md) — 安全状态
11. [DEPLOYMENT_STATUS.md](file:///handoff/DEPLOYMENT_STATUS.md) — 部署状态
12. [DECISIONS.md](file:///handoff/DECISIONS.md) — 决策记录
13. [CHANGELOG_FROM_TRAE.md](file:///handoff/CHANGELOG_FROM_TRAE.md) — Trae 变更总结
14. [MANIFEST.json](file:///handoff/MANIFEST.json) — 机器可读清单

## 5. 本地启动命令

```powershell
# 设置管理员引导 Token（首次创建邀请码用）
$env:ADMIN_BOOTSTRAP_TOKEN = "<SET_IN_ENV>"

# 启动后端（默认 0.0.0.0:8000）
python -m backend.app
```

## 6. 全量测试命令

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

- **最新结果**: Ran 699 tests in ~15.8s — OK（exit 0）
- **测试文件数**: 38
- **基线**: 617（V3.2 之前） + 82（V3.2 新增） = 699

## 7. CLI 验证命令

```powershell
# V2 CLI
python -m src.modules.analyze_opportunities --help

# V3 CLI（V31Workflow 入口）
python -m src.modules.amazon.workflow --help
# 支持: --input --output-dir --config --scenario --with-mock-data --export-intermediate --strict
```

## 8. 前端访问地址

- 后端启动后：`http://localhost:8000/`
- 前端由后端从 `frontend/` 目录静态服务（[backend/app.py](file:///backend/app.py)）
- 入口文件: [frontend/index.html](file:///frontend/index.html)
- 首次使用需通过邀请码登录

## 9. 当前不能做的事情

- ❌ 不能部署到公网生产环境（缺少 TOS、生产数据库、真实队列、签名下载、HTTPS、多实例）
- ❌ 不能声明 veFaaS Worker 已完成（仅为骨架）
- ❌ 不能修改 [src/core/agent.py](file:///src/core/agent.py)
- ❌ 不能把浏览器流程称作已完整验证（3 步 NOT VERIFIED）
- ❌ 不能声称模板 100% 保真（仅 Sheet 名/顺序 + SHA 已验证）
- ❌ 不能依赖多实例共享本地 SQLite/文件

## 10. 明确声明

- 本交接包**不代表**所有功能已经完成。
- **不能只相信历史总结**：必须以当前代码、测试和实际命令输出为准。
- 开始修改前**必须重新检查代码和测试**：建议先运行全量测试建立基线。
- 所有未验证项**必须重新验证**：不要把"应该工作"等同于"已验证工作"。
- 交接文件中所有敏感示例值已替换为 `<REDACTED>` / `<SET_IN_ENV>` / `<LOCAL_ONLY>`。
- 本轮交接未修改任何业务代码、未删除任何现有文件、未接入云服务。

---

**交接包文件清单**:

| 文件 | 用途 |
|---|---|
| README.md | 入口说明（本文件） |
| PROJECT_STATUS.md | 功能状态分类（DONE/PARTIAL/NOT_VERIFIED/NOT_IMPLEMENTED/BLOCKED） |
| ARCHITECTURE.md | 真实架构（本地实现 vs 生产适配） |
| FILE_INVENTORY.md | 文件清单（路径/职责/状态/可否修改） |
| API_INVENTORY.md | API 清单（实际存在的接口） |
| WORKFLOW_STATUS.md | 工作流细节（Agent 顺序、checkpoint、取消） |
| TEST_STATUS.md | 测试结果（699/699 pass） |
| SECURITY_STATUS.md | 安全状态（已实现/部分/未验证/未实现） |
| DEPLOYMENT_STATUS.md | 部署状态（本地/局域网/互联网/veFaaS） |
| KNOWN_ISSUES.md | 已知问题（P0/P1/P2/P3） |
| NEXT_TASKS.md | 下一步任务（按推荐顺序） |
| DECISIONS.md | 决策记录 |
| CHANGELOG_FROM_TRAE.md | Trae Work 变更总结 |
| MANIFEST.json | 机器可读清单 |
