# DEPLOYMENT_STATUS — 部署状态

> 明确当前是否可以部署。

---

## 本地开发

- **是否能启动**: YES
- **监听地址**: `0.0.0.0:8000`（[backend/config.py](file:///backend/config.py#L51-L52)）
- **数据库位置**: `data/web.db`（SQLite）
- **文件存储位置**: `data/web_storage/`（上传）、`data/output/`（报告）
- **测试账号或邀请码来源**: 首次启动需设置 `ADMIN_BOOTSTRAP_TOKEN=<SET_IN_ENV>`，调用引导接口创建邀请码
- **是否适合个人本地使用**: YES — 单机调试、功能验证、Demo 均可

```powershell
$env:ADMIN_BOOTSTRAP_TOKEN = "<SET_IN_ENV>"
python -m backend.app
# 访问 http://localhost:8000/
```

## 局域网使用

- **是否支持**: PARTIAL — 监听 0.0.0.0 可被局域网访问
- **需要修改哪些绑定地址**: 无需修改（默认 0.0.0.0）
- **是否需要 HTTPS**: YES — 局域网传输 Cookie/邀请码需 HTTPS，当前无 HTTPS
- **是否存在安全限制**: YES — 无 HTTPS、无 API Gateway 限流、无生产级审计

## 互联网使用

- **当前是否允许**: **NO**
- **缺少什么**:
  - HTTPS 终端
  - API Gateway 限流 + WAF
  - 生产数据库（替代 SQLite）
  - TOS（替代本地文件）
  - 真实异步队列（替代 threading）
  - 多实例支持
  - 签名下载
  - 生产 Session Secret 共享
  - 生产密钥管理
  - 监控告警
- **是否存在隐私或数据安全风险**: YES — 当前本地文件 + SQLite + 单进程，公网暴露会有数据泄露风险

## veFaaS

### API Handler 状态
- **状态**: DONE（真实可用）
- **文件**: [deploy/veFaaS/handler.py](file:///deploy/veFaaS/handler.py)
- **说明**: 通过 `MAIN_ROUTER` 真实派发，复用本地路由
- **限制**: 不含后台线程（veFaaS 函数限制），长任务需走队列

### Worker Handler 状态
- **状态**: PARTIAL（**骨架**）
- **文件**: [deploy/veFaaS/worker_handler.py](file:///deploy/veFaaS/worker_handler.py)
- **说明**: 仅返回 `"Worker handler skeleton. Real queue/DB/TOS integration required."`
- **限制**: **无真实队列消费、无生产 DB、无 TOS、无重试/死信/超时恢复**

### 真实队列状态
- **状态**: NOT_IMPLEMENTED
- **说明**: 无 RocketMQ/Kafka 接入

### 生产数据库状态
- **状态**: NOT_IMPLEMENTED
- **说明**: 仅本地 SQLite

### TOS 状态
- **状态**: NOT_IMPLEMENTED
- **说明**: 仅本地文件系统

### 签名下载状态
- **状态**: NOT_IMPLEMENTED
- **说明**: 仅本地文件流，无 TOS 签名 URL

### Session Secret 状态
- **状态**: 未配置生产
- **说明**: 本地单进程内存 Session，多实例需共享存储

### API Gateway 状态
- **状态**: PARTIAL（仅文档 [deploy/api_gateway/routes.md](file:///deploy/api_gateway/routes.md)）
- **说明**: 无实际网关配置

### HTTPS 状态
- **状态**: NOT_IMPLEMENTED
- **说明**: 需配合 API Gateway/CDN 配置

### 多实例状态
- **状态**: NOT_IMPLEMENTED
- **说明**: 本地 SQLite + 本地文件 + threading.Thread 无法跨实例共享

### 任务重试和死信状态
- **状态**: NOT_IMPLEMENTED
- **说明**: Worker Handler 仅骨架

### 监控和告警状态
- **状态**: NOT_IMPLEMENTED
- **说明**: 无结构化日志、无监控指标、无告警通道

---

## 明确声明

```
Handler 文件存在不等于已经完成生产部署。
如果 TOS、生产数据库和真实异步队列尚未接入，当前版本不能声明生产可用。
```

- `deploy/veFaaS/handler.py` 真实可用，但**仅适合短请求**（API 派发）
- `deploy/veFaaS/worker_handler.py` **仅为骨架**，不消费任何真实队列
- 生产部署完整路径: API Gateway → veFaaS API Handler → RocketMQ → veFaaS Worker Handler → 生产 DB + TOS
- 当前完整路径中**仅 API Handler 一环真实可用**，其余 NOT_IMPLEMENTED
