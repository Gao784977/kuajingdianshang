# TOS 静态资源托管

本文件描述如何将前端静态文件部署到火山引擎 TOS（对象存储）并开启静态网站托管。

## 方案

将 `frontend/` 目录下的静态文件（`index.html`、`styles.css`、`app.js`、`api.js`）上传到 TOS Bucket，并开启静态网站托管。

## 步骤

### 1. 创建 TOS Bucket

```
Bucket 名称: product-research-frontend
区域: cn-beijing
存储类型: 标准存储
```

### 2. 开启静态网站托管

在 TOS 控制台 → Bucket → 基础配置 → 静态网站托管：

```
首页: index.html
404 页面: index.html (SPA 回退)
默认文档: index.html
```

### 3. 上传文件

```bash
# 使用 tosutil 或控制台上传
tosutil cp frontend/ tos://product-research-frontend/ -r
```

### 4. 配置 CORS（API 跨域）

如果前端和 API 不同域，需要在 API Gateway 配置 CORS。
参考 `../api_gateway/routes.md` 中的 CORS 配置。

### 5. 配置自定义域名（可选）

绑定自定义域名并开启 HTTPS：

```
域名: app.your-domain.com
CNAME: product-research-frontend.tos-cn-beijing.volces.com
证书: 上传 SSL 证书到火山引擎证书中心
```

### 6. 配置缓存策略

```
index.html:  Cache-Control: no-cache    (每次请求最新版)
*.js:        Cache-Control: max-age=300  (5 分钟)
*.css:       Cache-Control: max-age=300  (5 分钟)
```

## 备选方案：CDN 加速

如需全球加速，可在 TOS 前接入火山引擎 CDN：

1. 创建 CDN 加速域名
2. 源站设为 TOS Bucket 域名
3. 配置 HTTPS 证书
4. 配置缓存规则
