# KASUGA SHOJI 横滨典藏馆 — 静态克隆站

以 [kasugashoji.net](https://kasugashoji.net/)（日本横滨的烟草、雪茄、烟具电商）为蓝本重建的**纯静态演示站点**：零框架、零构建、零后端，打开即用。

> 演示声明：本站为学习用途的克隆项目。商品数据整理自原站公开页面；**未接入真实支付**，购物流程为本地模拟；请以原站为准获取真实购买服务。吸烟有害健康，本站仅面向 20 岁以上成年人。

## 特性

- **纯静态**：HTML/CSS/JS + 单一数据文件 `assets/js/data.js`，任意静态托管（nginx / GitHub Pages / Vercel）直接部署
- **秒开**：无框架无依赖，商品数据按需过滤，分页渲染（36/页）
- **价格加成可调**：前端动态加价，`assets/js/config.js` 中 `markup: 1.15` 一处调节全局售价（含进位到 10 円）
- **完整购物流程**：年龄门 → 浏览/搜索/筛选 → 加购 → 购物车 → 结算 → 模拟下单 → 订单中心（localStorage 持久化）
- **社区与评价**：商品评价 + 藏家社区发帖（本地存储演示）
- **图片本地化**：1,950 张商品图已全部下载落盘（本地优先、原站兜底 onerror 回退），附批量下载脚本
- **部署就绪**：robots.txt、404.html、sitemap.xml（1,990 URL）、favicon 齐备，任意静态托管即用

## 目录结构

```
kasuga-clone/
├── index.html            # 首页（精选、典藏分类、热销榜）
├── shop.html             # 全部商品（搜索/分类/排序/分页）
├── product.html          # 商品详情（?id=）+ 评价
├── category.html         # 分类页（?cat= 一级或二级 key）
├── brands.html           # 品牌目录（动态聚合）
├── cart.html             # 购物车
├── checkout.html         # 结算台
├── order-success.html    # 下单成功
├── account.html          # 会员中心（订单/评价/资料）
├── community.html        # 藏家社区
├── about / guide / faq / contact / buyback / adult.html
├── assets/
│   ├── css/style.css     # 日式极简设计系统（单文件）
│   └── js/
│       ├── config.js     # 站点配置（加价系数/运费/包邮线）
│       ├── data.js       # 商品数据（由 tools/build-data.py 生成）
│       ├── app.js        # 公共（加价计算/购物车/评价/年龄门）
│       ├── layout.js     # 头尾布局注入
│       └── home/shop/product/category/cart.js
└── tools/
    ├── build-data.py        # 抓取结果 + sitemap → data.js
    ├── download-images.py  # 图片批量本地化
    └── scrape-data/         # 原站抓取脚本与结果存档
```

## 快速开始

```bash
# 本地预览
python3 -m http.server 8040
# 打开 http://127.0.0.1:8040
```

## 价格加成

编辑 `assets/js/config.js`：

```js
markup: 1.15,        // 原价 → 售价 = ceil(原价 × 1.15 / 10) × 10
shipping: { flat: 800, freeOver: 20000, expressMult: 2 },
```

改一处，全站（列表、详情、购物车、结算、订单）即时生效。

## 数据更新

```bash
# 1. 生成/更新 data.js（读取 tools/scrape-data/ 下的 sitemap 与批次抓取结果）
python3 tools/build-data.py

# 2. 商品图已全部本地化（assets/img/products/，1,950 张 WebP）；如需补下/重下：
python3 tools/download-images.py            # 增量
python3 tools/download-images.py --force   # 全量重下
```

图片下载完成后站点自动优先加载本地图片；未下载时自动回退原站图床。

## localStorage 键一览

| 键 | 用途 |
|---|---|
| `kasuga_age_ok` | 年龄确认 |
| `kasuga_cart_v1` | 购物车 |
| `kasuga_orders` / `kasuga_last_order` | 订单记录 |
| `kasuga_reviews_v1` | 商品评价 |
| `kasuga_community_v1` | 社区帖子 |
| `kasuga_nickname` | 会员昵称 |

## 当前数据覆盖

- 商店列表 **全部 166 页已抓取完毕**（84円 GIZEH 烟纸 → 245,000円 大卫杜夫皇家珍藏），含价格/促销价/库存/图片/在售标记
- 最终收录 **1,975 件商品**（与原站在售规模一致），价格区间经逐页无缝衔接校验
- 商品图 **1,950 张已全部本地化**（WebP）；26 件无图/原站死链商品使用本地占位图 placeholder.svg
- 原站约 17 件 sitemap 商品已下架/不在列表（按"抓不到即省略"原则剔除）；另有 500+ 件新上架商品不在旧 sitemap 中，均以实抓数据为准
- 抓取工具与原始数据见 `tools/scrape-data/`（分批脚本 + 结果 JSON 存档）；补抓后重跑 `python3 tools/build-data.py` 即可重建 `data.js`
