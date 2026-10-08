# API Gateway 路由配置

本文件描述将 veFaaS API Handler 接入火山引擎 API Gateway 的路由规划。

## 路由表

| 方法 | 路径 | 后端函数 | 说明 |
|------|------|----------|------|
| GET | `/` | api_handler | 前端静态页面 |
| GET | `/api/health` | api_handler | 健康检查 |
| GET | `/api/workflow/definition` | api_handler | 工作流定义 |
| POST | `/api/auth/login` | api_handler | 邀请码登录 |
| POST | `/api/auth/logout` | api_handler | 登出 |
| GET | `/api/auth/me` | api_handler | 当前用户 |
| GET | `/api/projects` | api_handler | 项目列表 |
| POST | `/api/projects` | api_handler | 创建项目 |
| GET | `/api/projects/{id}` | api_handler | 项目详情 |
| PUT | `/api/projects/{id}` | api_handler | 更新项目 |
| POST | `/api/projects/{id}/validate` | api_handler | 校验输入 |
| GET | `/api/projects/{id}/files` | api_handler | 文件列表 |
| POST | `/api/projects/{id}/files` | api_handler | 上传文件 |
| POST | `/api/projects/{id}/files/detect` | api_handler | 文件检测 |
| GET | `/api/projects/{id}/templates` | api_handler | 模板列表 |
| POST | `/api/projects/{id}/templates` | api_handler | 上传模板 |
| POST | `/api/projects/{id}/jobs` | api_handler | 启动任务 |
| GET | `/api/jobs/{id}` | api_handler | 任务状态 |
| POST | `/api/jobs/{id}/cancel` | api_handler | 取消任务 |
| GET | `/api/projects/{id}/candidates` | api_handler | 候选列表 |
| POST | `/api/projects/{id}/candidates/{cid}/confirm` | api_handler | 确认候选 |
| POST | `/api/projects/{id}/candidates/{cid}/reject` | api_handler | 拒绝候选 |
| PUT | `/api/projects/{id}/manual-inputs` | api_handler | 保存人工信息 |
| POST | `/api/projects/{id}/continue-development` | api_handler | 继续开发 |
| GET | `/api/projects/{id}/outputs` | api_handler | 输出列表 |
| GET | `/api/outputs/{id}/download` | api_handler | 下载输出 |

## API Gateway 配置要点

### 1. 超时设置
- API Handler 函数超时: 30 秒
- API Gateway 超时: 35 秒（略大于函数超时）
- 长任务通过异步 Worker 处理，API 仅返回 job_id

### 2. CORS
- 允许源: 生产域名
- 允许方法: GET, POST, PUT, DELETE, OPTIONS
- 允许头: Content-Type, X-CSRF-Token
- 凭证模式: include（携带 Cookie）

### 3. 限流
- 登录接口: 10 次/分钟/IP（防暴力破解）
- 文件上传: 5 次/分钟/用户
- 任务启动: 1 次/分钟/用户

### 4. 请求体大小限制
- 默认: 10 MB
- 文件上传接口: 50 MB（对应 MAX_UPLOAD_SIZE_MB）

## 示例：API Gateway 到 veFaaS 的映射

```json
{
  "routes": [
    {
      "path": "/api/projects",
      "method": "POST",
      "backend": {
        "type": "vefaas",
        "function": "api_handler",
        "region": "cn-beijing"
      }
    }
  ]
}
```
