# veFaaS 部署指南

本目录包含将 Amazon Product Research V3.2 部署到火山引擎 veFaaS 的配置文件和骨架代码。

## 架构

```
                    ┌─────────────────┐
  用户 ──HTTPS──►   │  API Gateway    │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  api_handler    │  veFaaS HTTP 函数
                    │  (handler.py)   │  ── 快速响应请求
                    └────────┬────────┘
                             │ 提交任务到消息队列
                    ┌────────▼────────┐
                    │  RocketMQ       │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │ worker_handler  │  veFaaS 消息触发函数
                    │ (worker_handler)│  ── 执行 V31Workflow
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   TOS / RDS     │  持久化存储
                    └─────────────────┘
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `handler.py` | HTTP API 入口，复用后端路由 |
| `worker_handler.py` | 异步任务 Worker 入口（骨架） |
| `requirements.txt` | Python 依赖 |
| `function.yaml` | veFaaS 函数配置 |
| `env.example` | 环境变量模板 |

## 部署步骤

### 1. 准备依赖

```bash
cd deploy/veFaaS
pip install -r requirements.txt -t ./package
```

### 2. 配置环境变量

复制 `env.example` 并填入实际值。

### 3. 部署 API Handler

```bash
# 使用 veFaaS CLI 或控制台上传
vefaas deploy --config function.yaml --function api_handler
```

### 4. 部署 Worker Handler

```bash
vefaas deploy --config function.yaml --function worker_handler
```

### 5. 配置消息队列

创建 RocketMQ topic `product-research-tasks`，绑定 worker_handler 作为消费者。

### 6. 配置 API Gateway

参见 `../api_gateway/routes.md`。

## 生产集成 TODO

以下接口为骨架，生产部署时需对接真实云服务：

- [ ] `deploy/veFaaS/handler.py`: 接入真实 RDS 连接（替换 `backend/storage/database.py` 中的 SQLite）
- [ ] `deploy/veFaaS/worker_handler.py`: 实现 RocketMQ 消息消费、重试、死信队列
- [ ] `backend/storage/base.py`: 实现 `TosStorageBackend`（对接 TOS SDK）
- [ ] `backend/storage/database.py`: 实现 `RdsJobStore`（对接 MySQL/PostgreSQL）
- [ ] 配置 VPC 网络，确保函数可访问 RDS 和 RocketMQ
- [ ] 配置 IAM 角色，授权 TOS 读写和 RocketMQ 消费权限
