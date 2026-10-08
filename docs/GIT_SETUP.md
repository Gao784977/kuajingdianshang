# GIT_SETUP — Git 安装与远程仓库配置指南

> **当前环境状态**：本机未安装 Git（执行 `git --version` 报 "git 项无法识别"）。
> 本文件描述安装 Git 后需要执行的步骤。本机当前无法执行 git 命令，不要伪造结果。

## 1. 安装 Git

### 1.1 Windows

1. 访问 https://git-scm.com/download/win 下载 Git for Windows
2. 运行安装程序，使用默认选项即可
3. 安装完成后重新打开 PowerShell 或终端
4. 验证：`git --version` 应输出版本号

### 1.2 macOS

```bash
# 方式一：使用 Homebrew（推荐）
brew install git

# 方式二：使用 Xcode Command Line Tools
xcode-select --install

# 验证
git --version
```

### 1.3 Linux

```bash
# Debian/Ubuntu
sudo apt-get update && sudo apt-get install git

# CentOS/RHEL/Fedora
sudo yum install git
# 或
sudo dnf install git

# 验证
git --version
```

## 2. 配置 Git 用户信息（首次使用）

```bash
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"

# 可选：默认分支名
git config --global init.defaultBranch main

# 可选：Windows 行尾处理
git config --global core.autocrlf true
```

## 3. 创建远程私有仓库

**不在本指南中自动创建远程仓库**。开发者需手动在 GitHub 或 Gitee 创建私有仓库，然后获取仓库 URL（形如 `https://github.com/<user>/<repo>.git`）。

推荐使用**私有仓库**，因为本项目可能包含业务逻辑和配置。

## 4. 首次推送到远程仓库

在项目根目录执行（替换 `<PRIVATE_REPOSITORY_URL>` 为实际地址）：

```bash
# 1. 初始化本地仓库
git init
git branch -M main

# 2. 添加远程仓库
git remote add origin <PRIVATE_REPOSITORY_URL>

# 3. 检查 .gitignore 是否正确忽略本地数据
#    确认 data/web.db, data/web_storage/, data/output/ 不会被提交
git status --short

# 4. 添加文件（只添加实际应入 Git 的文件）
git add .gitignore .env.example README.md CONTRIBUTING.md
git add backend/ frontend/ src/ tests/ config/ deploy/ docs/ handoff/ scripts/ examples/
git add requirements.txt
git add data/raw/ data/amazon/demo_product_input.json data/amazon/demo_competitors.csv
git add data/amazon/demo_reviews.csv data/amazon/input/ data/amazon/templates/
git add data/output/.gitkeep

# 5. 首次提交
git commit -m "chore: prepare multi-device development"

# 6. 推送到远程
git push -u origin main
```

**重要**：首次 `git add` 后，再次检查 `git status --short`，确认没有把 `data/web.db`、`data/web_storage/`、`data/output/` 中除 `.gitkeep` 外的任何文件加入暂存区。如果发现误添加，使用 `git rm --cached <file>` 移除（不会删除本地文件）。

## 5. 在另一台电脑克隆

```bash
git clone <PRIVATE_REPOSITORY_URL>
cd 项目目录

# 复制 .env.example 为 .env，填入本机密钥
cp .env.example .env

# 运行本地初始化脚本
# Windows: .\scripts\setup_local.ps1
# macOS/Linux: bash scripts/setup_local.sh

# 环境检查
python scripts/check_environment.py

# 全量测试
python -m unittest discover -s tests -p "test_*.py"

# 启动后端
python -m backend.app
```

## 6. 日常同步命令

### 6.1 开始开发前

```bash
git pull --rebase
```

### 6.2 开发完成后

```bash
# 查看修改
git status

# 运行测试
python -m unittest discover -s tests -p "test_*.py"

# 只提交实际修改的文件
git add src/... backend/... tests/...
git commit -m "描述本次修改"

# 推送
git push
```

### 6.3 另一台电脑继续开发前

```bash
git pull --rebase
```

## 7. 安全检查

**绝不提交以下文件**：

- `.env`（含密钥）
- `data/web.db`, `data/web.db-wal`, `data/web.db-shm`（本地数据库）
- `data/web_storage/`（用户上传）
- `data/output/`（除 `.gitkeep` 外的生成报告）
- `data/amazon/output/`（Amazon 生成报告）
- `.venv/`, `venv/`（虚拟环境）
- `__pycache__/`, `*.pyc`（缓存）
- `logs/`（日志）
- `temp/`（临时文件）

提交前检查：

```bash
git status --short
# 确认以上路径不出现在 Changes to be committed
```

如果误添加了本地数据文件，使用：

```bash
git rm --cached <file>
# 这会从 Git 索引中移除，但不会删除本地文件
```

## 8. 当前环境状态说明

- **本机 Git 未安装**：执行 `git --version` 返回 "git 项无法识别"
- **本机已完成工程配置**：`.gitignore`, `.env.example`, `scripts/`, `docs/` 等文件已生成
- **安装 Git 后需要重新执行**：第 4 节的初始化和推送步骤
- **不能自动执行推送**：开发者必须手动创建远程仓库并执行推送
- **不使用真实仓库地址**：本指南中所有 `<PRIVATE_REPOSITORY_URL>` 为占位符

## 9. 分支规范

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。
