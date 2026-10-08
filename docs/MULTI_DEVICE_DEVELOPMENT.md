# MULTI_DEVICE_DEVELOPMENT — 多端开发规范

本文件描述如何让"公司电脑 + 个人电脑"通过同一个 Git 远程仓库同步代码，且每台电脑使用独立的本地配置、数据库和文件存储。

## 1. 核心原则

- **Git 只同步源代码、测试、配置模板、文档、固定测试样例、依赖锁定文件**。
- **本地数据库（`data/web.db`）、用户上传（`data/web_storage/`）、生成报告（`data/output/`）、密钥（`.env`）、虚拟环境（`.venv/`）不进 Git**。
- 每台电脑从同一个远程仓库拉取代码，各自维护独立的 `.env` 和本地数据。
- 两台电脑的本地数据默认互不相同。如果需要共享业务数据，应设计独立的数据同步或生产数据库，不能依赖 Git。

## 2. 应该通过 Git 同步的内容

| 类别 | 示例 |
| --- | --- |
| 源代码 | `src/`, `backend/`, `frontend/` |
| 测试 | `tests/` |
| 配置模板 | `.env.example`, `config/*.json` |
| 固定测试样例 | `data/raw/*.csv`, `data/amazon/demo_*.json` |
| 固定模板 | `data/amazon/templates/*.xlsx` |
| 文档 | `README.md`, `CONTRIBUTING.md`, `docs/`, `handoff/` |
| 依赖锁定 | `requirements.txt` |
| 脚本 | `scripts/` |
| 部署骨架 | `deploy/` |

## 3. 不应该通过 Git 同步的内容

| 类别 | 路径 | 原因 |
| --- | --- | --- |
| 本地密钥 | `.env` | 每台电脑独立密钥，泄露风险 |
| 本地数据库 | `data/web.db`, `*.db-wal`, `*.db-shm` | 用户数据隔离 |
| 用户上传 | `data/web_storage/` | 用户隐私 |
| 生成报告 | `data/output/`, `data/amazon/output/` | 带时间戳的输出 |
| 虚拟环境 | `.venv/`, `venv/` | 跨平台不兼容 |
| 缓存 | `__pycache__/`, `.pytest_cache/` | 自动生成 |
| 日志 | `logs/` | 本地运行状态 |
| 临时文件 | `temp/` | 临时中间产物 |

`.gitignore` 已经覆盖以上所有路径。如果新增本地运行时数据，请同步更新 `.gitignore`。

## 4. 工作流程

### 4.1 首次使用（第一台电脑）

1. 安装 Git 和 Python 3.10+
2. `git clone <PRIVATE_REPOSITORY_URL>`
3. `cd 项目目录`
4. 复制 `.env.example` 为 `.env`
5. 为本机生成独立的 `ADMIN_BOOTSTRAP_TOKEN`（强随机值）
6. 运行 `scripts/setup_local.ps1`（Windows）或 `scripts/setup_local.sh`（macOS/Linux）
7. 编辑 `.env` 填入本机密钥
8. 运行 `python scripts/check_environment.py` 确认 PASS
9. 运行 `python -m unittest discover -s tests -p "test_*.py"` 确认测试通过
10. 启动 `python -m backend.app`，访问 `http://127.0.0.1:8000/`

### 4.2 第二台电脑

1. 安装 Git 和 Python 3.10+
2. `git clone <PRIVATE_REPOSITORY_URL>`
3. `cd 项目目录`
4. 复制 `.env.example` 为本机 `.env`
5. 使用本机独立的密钥（不要复制第一台电脑的 `.env`）
6. 运行 `scripts/setup_local.ps1` 或 `scripts/setup_local.sh`
7. 运行 `python scripts/check_environment.py`
8. 运行全量测试
9. 启动服务

### 4.3 日常同步

开始开发前：

```bash
git pull --rebase
```

查看状态：

```bash
git status
```

开发完成后：

```bash
# 运行测试确认通过
python -m unittest discover -s tests -p "test_*.py"

# 只提交实际修改的文件（不要 git add . ）
git add src/... backend/... tests/...
git commit -m "描述本次修改"
git push
```

另一台电脑继续开发前：

```bash
git pull --rebase
```

## 5. 冲突处理

- 拉取前先检查本地未提交修改：`git status`
- 发生冲突时不得直接覆盖用户修改
- 不使用 `git reset --hard` 或 `git checkout --` 覆盖工作区，除非开发者明确授权
- 冲突解决后必须重新运行全量测试

## 6. 分支规范

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

- `main` 只放可运行代码
- 新功能：`feature/<topic>`
- 修复：`fix/<topic>`
- 每次提交只包含一个逻辑主题

## 7. 数据共享策略

如果两台电脑需要共享业务数据（项目、上传文件、报告），**不能依赖 Git**。可选方案：

- 接入生产数据库（详见 [handoff/NEXT_TASKS.md](handoff/NEXT_TASKS.md) 第二阶段）
- 使用对象存储（TOS）保存上传文件和报告
- 设计独立的数据导入/导出接口

在本地开发阶段，两台电脑的本地数据库默认互不相同，这是预期行为。

## 8. 密钥管理

- `.env` 不进 Git
- `ADMIN_BOOTSTRAP_TOKEN` 仅用于首次创建邀请码，创建完成后可清空
- `SESSION_COOKIE_SECURE` 在 HTTPS 环境下设为 `true`
- 不要在代码、文档、提交信息、聊天记录中写入真实密钥
- 详见 [docs/AI_DEVELOPMENT_CONTEXT.md](AI_DEVELOPMENT_CONTEXT.md) 的"不应提交的文件"清单
