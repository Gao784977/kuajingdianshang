# SECURITY_STATUS — 安全实现和缺口

> 每项使用: **已实现** / **部分实现** / **未验证** / **未实现**
> 存在函数名**不等于**完整安全防护。

---

## 1. 邀请码

- **状态**: 已实现
- **文件**: [backend/services/auth_service.py](file:///backend/services/auth_service.py)
- **说明**: 邀请码创建 + 验证 + 失效；首次通过 `ADMIN_BOOTSTRAP_TOKEN` 引导创建
- **测试**: `tests/test_auth_invitation.py`
- **限制**: 首次引导需手动设置环境变量

## 2. 邀请码哈希

- **状态**: 已实现
- **文件**: [backend/services/auth_service.py](file:///backend/services/auth_service.py)
- **说明**: 邀请码使用 SHA-256 哈希存储，不存明文
- **测试**: `tests/test_auth_invitation.py`
- **限制**: 无

## 3. user_id

- **状态**: 已实现
- **文件**: [backend/services/auth_service.py](file:///backend/services/auth_service.py)
- **说明**: 每个 invitation 关联独立 user_id；Session 隔离
- **测试**: `tests/test_cross_user_isolation.py`
- **限制**: 无

## 4. Session

- **状态**: 已实现
- **文件**: [backend/services/auth_service.py](file:///backend/services/auth_service.py)
- **说明**: Session 服务端存储，session_id 通过 Cookie 下发，TTL 24h
- **测试**: `tests/test_auth_invitation.py`
- **限制**: 本地单进程内存存储，多实例需共享存储

## 5. Cookie

- **状态**: 已实现
- **文件**: [backend/config.py](file:///backend/config.py#L56-L62)、[backend/services/auth_service.py](file:///backend/services/auth_service.py)
- **说明**: `SESSION_COOKIE_NAME` 可配置；`SESSION_COOKIE_SECURE` 在 production 默认 True；`SESSION_COOKIE_SAMESITE` 默认 Lax
- **测试**: `tests/test_auth_invitation.py`
- **限制**: 生产需 HTTPS 配合 Secure

## 6. CSRF

- **状态**: 已实现
- **文件**: [backend/services/auth_service.py](file:///backend/services/auth_service.py)
- **说明**: CSRF Token 机制 + SameSite Cookie 双重防护
- **测试**: `tests/test_auth_invitation.py`
- **限制**: 无

## 7. CORS

- **状态**: 已实现
- **文件**: [backend/config.py](file:///backend/config.py#L65) `ALLOWED_ORIGINS`
- **说明**: 默认空（不允许跨域），可通过环境变量配置白名单
- **测试**: 部分（`tests/test_health.py`）
- **限制**: 无

## 8. owner_id

- **状态**: 已实现
- **文件**: [backend/services/auth_service.py](file:///backend/services/auth_service.py)（`require_session` 装饰器）
- **说明**: owner_id 从 Session 取，**不接受**前端传入的 owner_id/user_id 绕过
- **测试**: `tests/test_cross_user_isolation.py`（25 个用例真实路由验证）
- **限制**: 无

## 9. 文件扩展名

- **状态**: 已实现
- **文件**: [backend/config.py](file:///backend/config.py#L69) `ALLOWED_UPLOAD_EXTENSIONS = {"xlsx", "csv", "json"}`
- **说明**: 白名单机制，xls 明确拒绝并提示转换
- **测试**: `tests/test_uploads_api.py`
- **限制**: 无

## 10. 文件大小

- **状态**: 已实现
- **文件**: [backend/config.py](file:///backend/config.py#L68) `MAX_UPLOAD_SIZE_MB = 50`
- **说明**: 默认 50MB，可环境变量配置
- **测试**: `tests/test_uploads_api.py`
- **限制**: 无

## 11. 路径穿越

- **状态**: 已实现
- **文件**: [backend/api/outputs.py](file:///backend/api/outputs.py)、[backend/api/uploads.py](file:///backend/api/uploads.py)
- **说明**: 输出下载接口对 output_id 校验 + 路径穿越字符串拦截（400）
- **测试**: `tests/test_download_security.py`
- **限制**: 无

## 12. SHA-256

- **状态**: 已实现
- **文件**: [backend/services/auth_service.py](file:///backend/services/auth_service.py)（邀请码哈希）、[src/modules/amazon/template_builder.py](file:///src/modules/amazon/template_builder.py)（原模板 SHA 不变）
- **说明**: 邀请码哈希 + 模板 SHA-256 校验
- **测试**: `tests/test_auth_invitation.py`、`tests/test_template_integration.py`
- **限制**: 无

## 13. URL 默认关闭

- **状态**: 已实现
- **文件**: [backend/config.py](file:///backend/config.py#L78) `URL_FETCH_ENABLED = _env_bool("URL_FETCH_ENABLED", False)`
- **说明**: 默认 False；仅当 CLI 参数 `--allow-url-fetch` 或环境变量显式开启时才访问
- **测试**: `tests/test_ssrf_dns.py`
- **限制**: 无

## 14. DNS 解析后的 IP 检查

- **状态**: 已实现
- **文件**: [backend/services/url_security.py](file:///backend/services/url_security.py)
- **说明**: 解析后 IPv4/IPv6 地址校验，禁止回环、私有、元数据等风险地址
- **测试**: `tests/test_ssrf_dns.py`（mock DNS 到 127.0.0.1/私有 IPv4/IPv6 回环均被阻止）
- **限制**: 使用 mock transport，未对真实 DNS 服务器验证

## 15. 重定向重新检查

- **状态**: 已实现
- **文件**: [backend/services/url_security.py](file:///backend/services/url_security.py)
- **说明**: 重定向目标重新经过 DNS/IP 校验，内网目标未请求
- **测试**: `tests/test_ssrf_dns.py`
- **限制**: 无

## 16. 代理环境变量隔离

- **状态**: 已实现
- **文件**: [backend/services/url_security.py](file:///backend/services/url_security.py)
- **说明**: URL fetch 时清理代理环境变量，防止代理绕过
- **测试**: 部分
- **限制**: 无

## 17. Content-Type 和响应大小限制

- **状态**: 已实现
- **文件**: [backend/config.py](file:///backend/config.py#L79-L82) `URL_FETCH_MAX_BYTES=5MB`、`URL_FETCH_CONNECT_TIMEOUT=5`、`URL_FETCH_READ_TIMEOUT=10`
- **说明**: 大小 + 超时双重限制
- **测试**: 部分
- **限制**: 无

## 18. 下载权限

- **状态**: 已实现
- **文件**: [backend/api/outputs.py](file:///backend/api/outputs.py)
- **说明**: owner_id 校验 + 已登记路径校验 + 路径穿越防护
- **测试**: `tests/test_download_security.py`（6 个用例：跨用户 403、路径穿越 400、未登记路径、无效 output_id）
- **限制**: 生产需签名 URL 替代直接文件流

## 19. 生产密钥

- **状态**: 未实现
- **文件**: 无
- **说明**: 无生产密钥管理（KMS/Secret Manager）
- **限制**: 当前仅 `ADMIN_BOOTSTRAP_TOKEN` 通过环境变量传入，无轮换/审计
- **下一步**: 接入云密钥管理服务

## 20. 日志脱敏

- **状态**: 部分实现
- **文件**: [backend/services/auth_service.py](file:///backend/services/auth_service.py)
- **说明**: 邀请码明文不入日志；但其他字段（URL、文件名等）未系统性脱敏
- **限制**: 缺少结构化日志脱敏中间件
- **下一步**: 增加日志脱敏过滤器

---

## 安全缺口汇总

| 项 | 状态 |
|---|---|
| 生产密钥管理 | 未实现 |
| 日志系统性脱敏 | 部分实现 |
| HTTPS 强制 | 未实现（生产需 API Gateway + HTTPS） |
| API Gateway 限流 | 未实现（仅本地 rate limit） |
| 生产 Session 共享 | 未实现 |
| 多实例安全状态同步 | 未实现 |
| 签名下载 URL | 未实现 |
| 审计日志 | 部分实现（job_events） |

> **不能把存在函数名等同于完整安全防护**。生产部署前需进行完整安全审计。
