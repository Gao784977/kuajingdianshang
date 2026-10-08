# SSH 密钥配置指南（第二台电脑）

本指南面向需要在第二台电脑上克隆本项目并配置 SSH 推送权限的开发者。

> **背景**：本项目的 HTTPS git push 流量在网络层被重置（常见于中国大陆网络环境），SSH 协议不受影响。因此两台电脑都通过 SSH 协议推送代码。

---

## 前置条件

| 依赖 | 说明 |
| --- | --- |
| Git for Windows | 包含 `ssh-keygen` 和 `ssh`；下载 https://git-scm.com/download/win |
| GitHub 账号 | 拥有 `Gao784977/kuajingdianshang` 仓库访问权限 |
| Python 3.10+ | 用于运行项目（克隆后安装依赖） |

---

## 步骤 1：安装 Git

如果第二台电脑还没安装 Git：

1. 访问 https://git-scm.com/download/win 下载 Git for Windows
2. 运行安装程序，使用默认选项
3. 安装完成后**重新打开终端**（PowerShell 或 Git Bash），验证：

```bash
git --version
```

应输出版本号（如 `git version 2.55.0`）。

---

## 步骤 2：生成 SSH 密钥

**每台电脑生成自己独立的密钥对**，不要复用第一台电脑的私钥。

### 2.1 打开终端

推荐使用 **Git Bash**（安装 Git 后，右键文件夹 → "Open Git Bash here"），也可用 PowerShell。

### 2.2 生成 ed25519 密钥

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

- 将 `your_email@example.com` 替换为你的邮箱（建议用 GitHub 邮箱或 `用户名@users.noreply.github.com`）
- 当提示 `Enter file in which to save the key` 时，**直接按回车**使用默认路径 `~/.ssh/id_ed25519`
- 当提示 `Enter passphrase` 时，可直接按回车（无密码，方便自动化）或输入一个保护密码

### 2.3 验证密钥生成

```bash
ls ~/.ssh/
# 应看到 id_ed25519（私钥）和 id_ed25519.pub（公钥）
```

**私钥 `id_ed25519` 永远不要分享、不要提交到 Git、不要复制到其他电脑。**

---

## 步骤 3：添加公钥到 GitHub

### 3.1 复制公钥内容

```bash
cat ~/.ssh/id_ed25519.pub
```

输出形如：

```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAI...你的邮箱@example.com
```

**复制完整的一行**（以 `ssh-ed25519` 开头，以邮箱结尾）。

### 3.2 在 GitHub 添加密钥

1. 打开 https://github.com/settings/ssh/new
2. **Title**：填入一个便于识别的名称，如 `个人电脑 - ThinkPad` 或 `公司电脑 - MacBook`
3. **Key type**：选择 `Authentication Key`
4. **Key**：粘贴刚才复制的公钥
5. 点击 **Add SSH key**

### 3.3 验证 SSH 连接

```bash
ssh -T git@github.com
```

首次连接会提示：

```
Are you sure you want to continue connecting (yes/no)? yes
```

输入 `yes`。成功后会看到：

```
Hi Gao784977! You've successfully authenticated, but GitHub does not provide shell access.
```

如果看到 `Permission denied (publickey)`，说明公钥未正确添加，回到步骤 3.2 检查。

---

## 步骤 4：配置 Git 身份

```bash
# 全局配置（一次即可，所有项目通用）
git config --global user.name "你的名字"
git config --global user.email "your_email@example.com"

# 可选：默认分支名
git config --global init.defaultBranch main
```

---

## 步骤 5：克隆项目

### 5.1 选择克隆目录

```bash
# 例如克隆到 ~/projects/
mkdir -p ~/projects
cd ~/projects
```

### 5.2 通过 SSH 克隆

```bash
git clone git@github.com:Gao784977/kuajingdianshang.git
```

如果网络较慢，可能需要等待 30 秒到几分钟。

### 5.3 验证克隆成功

```bash
cd kuajingdianshang
git status
# 应看到 "On branch main"
git log --oneline -1
# 应看到首次提交 "chore: prepare multi-device development"
```

---

## 步骤 6：初始化本地开发环境

### 6.1 Windows（PowerShell）

```powershell
# 在项目根目录运行
.\scripts\setup_local.ps1
```

脚本会自动完成：
- 创建 `.venv` 虚拟环境
- 安装依赖（`requirements.txt`）
- 复制 `.env.example` 为 `.env`
- 创建 `data/web_storage/`、`data/output/`、`logs/`、`temp/` 目录
- 运行环境检查（`scripts/check_environment.py`）
- 运行全量测试（699 个用例）

### 6.2 macOS / Linux（bash）

```bash
# 在项目根目录运行
PYTHON=python3 bash scripts/setup_local.sh
```

### 6.3 手动初始化（如不使用脚本）

```bash
# 1. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate    # macOS/Linux
# 或 .\.venv\Scripts\activate  # Windows

# 2. 安装依赖
pip install -r requirements.txt

# 3. 创建 .env
cp .env.example .env
# 编辑 .env，设置 ADMIN_BOOTSTRAP_TOKEN=<本机强随机值>

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

---

## 步骤 7：配置本机 `.env`

每台电脑使用**独立的密钥和数据库**，不要复制第一台电脑的 `.env`。

```bash
# 编辑 .env
notepad .env          # Windows
# 或 nano .env         # macOS/Linux
```

至少设置：

```env
ADMIN_BOOTSTRAP_TOKEN=<本机强随机值>
HOST=127.0.0.1
PORT=8000
APP_ENV=local
URL_FETCH_ENABLED=false
MOCK_DATA_ENABLED=false
```

生成强随机值的简单方法：

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 日常同步流程

### 开始开发前

```bash
git pull --rebase
```

### 开发完成后

```bash
# 运行测试
python -m unittest discover -s tests -p "test_*.py"

# 暂存修改（只添加实际修改的文件）
git add src/... backend/... tests/...

# 提交
git commit -m "描述本次修改"

# 推送
git push
```

### 切换电脑时

在电脑 A 上完成开发并推送后，切到电脑 B：

```bash
# 在电脑 B 上
git pull --rebase
```

---

## 故障排查

### Q: `ssh -T git@github.com` 报 `Connection timed out`

A: 网络封锁了 SSH 22 端口。尝试使用 GitHub 的 443 端口 SSH：

```bash
# 编辑 ~/.ssh/config（不存在则创建）
Host github.com
  Hostname ssh.github.com
  Port 443
  User git
```

保存后重新测试 `ssh -T git@github.com`。

### Q: `git clone` 报 `Permission denied (publickey)`

A: SSH 公钥未正确添加到 GitHub。检查：

1. `cat ~/.ssh/id_ed25519.pub` 确认公钥存在
2. 在 https://github.com/settings/keys 检查公钥已添加
3. 确认克隆地址是 `git@github.com:Gao784977/kuajingdianshang.git` 而非 HTTPS

### Q: `git push` 报 `Connection was reset`

A: 如果你正在用 HTTPS 地址（`https://github.com/...`），改为 SSH：

```bash
git remote set-url origin git@github.com:Gao784977/kuajingdianshang.git
git push -u origin main
```

### Q: 测试失败，提示 SQLite 锁定

A: 确认没有正在运行的后端进程占用 `data/web.db`。必要时：

```bash
python scripts/reset_local_data.py --confirm
python -m unittest discover -s tests -p "test_*.py"
```

### Q: 环境检查报 `backend package not importable`

A: 在项目根目录运行，不要在 `scripts/` 子目录运行：

```bash
cd /path/to/kuajingdianshang
python scripts/check_environment.py
```

---

## 重要约束

- **`.env` 不入 Git**：每台电脑使用独立密钥
- **`data/web.db` 不入 Git**：每台电脑使用独立数据库
- **`data/web_storage/` 不入 Git**：用户上传文件不跨电脑同步
- **`data/output/` 不入 Git**：生成报告不跨电脑同步
- **`.venv/` 不入 Git**：虚拟环境跨平台不兼容
- **SSH 私钥 `~/.ssh/id_ed25519` 不入 Git**：永远不要分享或复制到其他电脑

两台电脑的本地数据默认互不相同。如果需要共享业务数据，应接入生产数据库或对象存储，不能依赖 Git 同步。

---

## 参考文档

- [本地初始化详细指南](LOCAL_SETUP.md)
- [多端开发规范](MULTI_DEVICE_DEVELOPMENT.md)
- [AI 编程代理交接说明](AI_DEVELOPMENT_CONTEXT.md)
- [Git 安装与远程仓库配置](GIT_SETUP.md)
- [贡献规范](../CONTRIBUTING.md)
