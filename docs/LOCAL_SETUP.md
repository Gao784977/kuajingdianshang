# LOCAL_SETUP — 本地环境初始化指南

本文件面向首次拉取代码后的开发者，说明如何从干净目录恢复项目并启动。

## 1. 前置依赖

| 依赖 | 版本要求 | 说明 |
| --- | --- | --- |
| Python | 3.10+ | 测试通过 3.10.11 |
| Git | 任意最近版本 | 用于代码同步 |
| openpyxl | 3.1.0+（可选） | Excel 输出需要；未安装时 MD/JSON 仍可用 |

无需 Node.js（前端为静态文件，无构建步骤）。

## 2. 首次初始化

### 2.1 Windows（PowerShell）

```powershell
# 安装 Git 和 Python 3.10+（如未安装，先安装）
git clone <PRIVATE_REPOSITORY_URL>
cd 项目目录

# 运行自动化初始化（创建 .venv、安装依赖、创建目录、环境检查、测试）
.\scripts\setup_local.ps1

# 编辑 .env 填入本机密钥
notepad .env

# 启动后端
python -m backend.app
# 或使用 venv
.\.venv\Scripts\python.exe -m backend.app
```

### 2.2 macOS / Linux（bash）

```bash
# 安装 Git 和 Python 3.10+（如未安装，先安装）
git clone <PRIVATE_REPOSITORY_URL>
cd 项目目录

# 运行自动化初始化
PYTHON=python3 bash scripts/setup_local.sh

# 编辑 .env 填入本机密钥
$EDITOR .env

# 启动后端
python3 -m backend.app
# 或使用 venv
./.venv/bin/python -m backend.app
```

## 3. 手动初始化（如不使用脚本）

```bash
git clone <PRIVATE_REPOSITORY_URL>
cd 项目目录

# 1. 创建虚拟环境
python -m venv .venv
# Windows: .\.venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

# 2. 安装依赖
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 3. 创建 .env
cp .env.example .env
# 编辑 .env，至少设置 ADMIN_BOOTSTRAP_TOKEN=<本机强随机值>

# 4. 创建必要目录
mkdir -p data/web_storage data/output logs temp

# 5. 环境检查
python scripts/check_environment.py
# 必须全部 PASS

# 6. 全量测试
python -m unittest discover -s tests -p "test_*.py"
# 预期 699/699 pass

# 7. 启动后端
python -m backend.app
# 访问 http://127.0.0.1:8000/
```

## 4. 环境变量配置

所有环境变量定义在 [.env.example](../.env.example)，对应 [backend/config.py](../backend/config.py) 的实际读取项。

**必填项**：

| 变量 | 说明 | 示例 |
| --- | --- | --- |
| `ADMIN_BOOTSTRAP_TOKEN` | 首次创建邀请码的管理员 Token | `<本机强随机值>` |

**常用项**：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `local` | 环境标签 |
| `HOST` | `0.0.0.0` | 监听地址；本机开发建议 `127.0.0.1` |
| `PORT` | `8000` | 监听端口 |
| `URL_FETCH_ENABLED` | `false` | URL 抓取总开关，默认关闭 |
| `MOCK_DATA_ENABLED` | `false` | 演示数据开关 |

**不要修改**：`SESSION_COOKIE_NAME`, `SESSION_TTL_SECONDS`, `LOGIN_RATE_LIMIT_PER_MIN` 等安全相关参数，除非明确理解影响。

## 5. 数据库初始化

SQLite 数据库在首次启动后端时**自动创建**，位于 `data/web.db`。无需手动执行迁移脚本。

首次启动后，使用 `ADMIN_BOOTSTRAP_TOKEN` 登录，创建邀请码，分发给开发者。

## 6. 验证步骤

### 6.1 环境检查

```bash
python scripts/check_environment.py
```

预期输出末尾：

```
RESULT: PASS — environment is ready for development.
```

### 6.2 全量测试

```bash
python -m unittest discover -s tests -p "test_*.py"
```

预期：699 个测试全部通过（exit 0）。

### 6.3 CLI 冒烟测试

```bash
# V2 CLI
python -m src.modules.analyze_opportunities --help

# V3 CLI
python -m src.modules.amazon.workflow --help
```

两个命令都应 exit 0。

### 6.4 后端启动

```bash
python -m backend.app
```

访问 `http://127.0.0.1:8000/api/health` 应返回 JSON。

## 7. 重置本地数据

如需清空本机运行时数据（数据库、上传、报告、日志）：

```bash
# 干跑（只显示将删除什么，不实际删除）
python scripts/reset_local_data.py

# 确认后实际删除
python scripts/reset_local_data.py --confirm
```

该脚本**不会删除**：源代码、模板、测试、配置、`.env`、文档。

## 8. 切换电脑流程

从电脑 A 切换到电脑 B：

1. 在电脑 A 上：`git push`（提交未推送的代码修改）
2. 在电脑 B 上：`git pull --rebase`
3. 在电脑 B 上：`python scripts/check_environment.py` 确认环境就绪
4. 在电脑 B 上：运行测试确认基线
5. 开始开发

**不要**复制电脑 A 的 `data/web.db` 或 `.env` 到电脑 B。两台电脑的本地数据保持独立。

## 9. 常见问题

### Q: 启动时报 "ADMIN_BOOTSTRAP_TOKEN is empty"

A: 编辑 `.env`，设置 `ADMIN_BOOTSTRAP_TOKEN=<强随机值>`，重启后端。

### Q: 测试失败，提示 SQLite 锁定

A: 确认没有正在运行的后端进程占用 `data/web.db`。必要时运行 `python scripts/reset_local_data.py --confirm` 清空后重试。

### Q: Excel 输出被跳过

A: 未安装 openpyxl。运行 `pip install openpyxl>=3.1.0`。MD/JSON 报告不受影响。

### Q: 端口 8000 被占用

A: 修改 `.env` 中 `PORT=8001`，或终止占用进程。

### Q: git pull 出现冲突

A: 不要 `git reset --hard`。检查 `git status`，手动解决冲突，重新运行测试后提交。
