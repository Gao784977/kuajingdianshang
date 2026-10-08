# CONTRIBUTING — 贡献规范

本文件规定对 Opportunity Analysis Tool (V3.2) 项目贡献的流程和分支规范。

## 1. 分支规范

### 1.1 main 分支

- `main` 分支只放**可运行代码**
- 不得直接在 `main` 上开发
- 合并到 `main` 前必须通过全量测试

### 1.2 功能分支

- 新功能使用独立分支，命名：`feature/<topic>`
- 示例：
  - `feature/template-workflow`
  - `feature/user-isolation-tests`
  - `feature/production-database`

### 1.3 修复分支

- 修复问题使用 `fix/` 前缀，命名：`fix/<topic>`
- 示例：
  - `fix/ssrf-dns-mock`
  - `fix/cross-user-download-test`

## 2. 提交规范

### 2.1 提交粒度

- 每次提交只包含一个**逻辑主题**
- 不要把无关修改混在同一个提交
- 不要把格式化、重构和功能修改混在一起

### 2.2 提交信息

- 使用简洁描述，说明"为什么"而不只是"做了什么"
- 示例：
  - `add SSRF DNS resolution mock test`
  - `fix: prevent cross-user download by validating owner_id`
  - `docs: update multi-device development guide`

### 2.3 提交前检查

每次提交前必须：

1. `git status` — 确认只暂存了应提交的文件
2. `python -m unittest discover -s tests -p "test_*.py"` — 测试通过
3. `python scripts/check_environment.py` — 环境检查 PASS
4. 确认没有暂存以下文件：
   - `.env`
   - `data/web.db`, `data/web.db-wal`, `data/web.db-shm`
   - `data/web_storage/`
   - `data/output/`（除 `.gitkeep`）
   - `.venv/`, `__pycache__/`
   - `logs/`, `temp/`

## 3. 不应提交的文件

详见 [docs/AI_DEVELOPMENT_CONTEXT.md](docs/AI_DEVELOPMENT_CONTEXT.md) 第 15 节和 [.gitignore](.gitignore)。

摘要：

- `.env`（密钥）
- `data/web.db*`（本地数据库）
- `data/web_storage/`（用户上传）
- `data/output/`（生成报告，除 `.gitkeep`）
- `data/amazon/output/`（Amazon 生成报告）
- `.venv/`, `venv/`（虚拟环境）
- `__pycache__/`, `*.pyc`（缓存）
- `logs/`, `temp/`
- 真实密钥、Token、Cookie、Access Key

## 4. 拉取与同步

### 4.1 拉取前

```bash
git status
# 检查本地未提交修改
```

如果有未提交修改，先 `git stash` 或提交到功能分支，再拉取。

### 4.2 拉取

```bash
git pull --rebase
```

### 4.3 冲突处理

- 发生冲突时**不得直接覆盖用户修改**
- 不使用 `git reset --hard` 或 `git checkout --` 覆盖工作区，除非开发者明确授权
- 手动解决冲突后，重新运行全量测试

## 5. 测试要求

- 新增功能必须新增测试
- 修改功能必须更新对应测试
- 提交前测试必须全部通过
- 测试数量不得低于基线（当前 699）
- 不得删除既有测试用例（除非对应功能已移除且有明确说明）

## 6. 代码规范

- 代码必须使用类型标注
- 优先使用 dataclasses 或清晰的结构化对象
- 函数职责必须单一
- 金额计算必须避免明显浮点误差，优先使用 Decimal
- 所有异常必须提供可定位信息
- 代码、字段名和文件名使用英文；报告内容可以使用中文
- 必须使用相对路径
- 默认使用 Python 标准库，尽量不新增依赖

## 7. 受保护文件

### 7.1 禁止修改

```
src/core/agent.py
```

除非用户明确授权，否则不得修改此文件。

### 7.2 谨慎修改

修改以下文件需说明原因并保留测试基线：

```
backend/app.py
backend/config.py
backend/api/__init__.py
backend/services/auth_service.py
backend/services/workflow_runner.py
backend/services/url_security.py
backend/storage/base.py
backend/storage/job_store.py
backend/storage/database.py
src/modules/amazon/v31_workflow.py
```

详见 [handoff/FILE_INVENTORY.md](handoff/FILE_INVENTORY.md)。

## 8. 多端开发注意事项

- 详见 [docs/MULTI_DEVICE_DEVELOPMENT.md](docs/MULTI_DEVICE_DEVELOPMENT.md)
- 每台电脑使用独立的 `.env` 和本地数据
- 不要在提交中包含本地数据
- 切换电脑时使用 `git pull --rebase`
- 不复制本地数据库或 `.env` 到其他电脑
