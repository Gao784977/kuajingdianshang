#!/usr/bin/env python3
"""下载全部商品图片到本地 assets/img/products/

用法（在你的服务器上、IP 未被原站拦截的环境运行）:
    python3 tools/download-images.py            # 增量下载（跳过已存在文件）
    python3 tools/download-images.py --workers 8
    python3 tools/download-images.py --force     # 重新下载全部

说明:
  - 图片 URL 来自 assets/js/data.js（PRODUCTS[].img 与 CATEGORIES[].imgRemote）
  - 保存路径 = data.js 中的 imgLocal（assets/img/products/<原站 uploads 相对路径>）
  - 下载成功后前端自动优先加载本地图片（imgLocal），失败时 onerror 回退原站
"""
import argparse
import os
import re
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_JS = os.path.join(BASE, "assets", "js", "data.js")
IMG_ROOT = os.path.join(BASE, "assets", "img", "products")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def load_urls():
    with open(DATA_JS, encoding="utf-8") as f:
        src = f.read()
    urls = re.findall(r'"(https://kasugashoji\.net/wp-content/uploads/[^"]+)"', src)
    # 去重并按路径排序
    return sorted(set(urls))


def url_to_path(url):
    m = re.search(r"/wp-content/uploads/(.+)$", url)
    return os.path.join(IMG_ROOT, m.group(1))


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://kasugashoji.net/"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def download_one(url, force=False):
    dest = url_to_path(url)
    if not force and os.path.exists(dest) and os.path.getsize(dest) > 0:
        return url, "skip", 0
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    for attempt in range(3):
        try:
            data = fetch(url)
            with open(dest, "wb") as f:
                f.write(data)
            return url, "ok", len(data)
        except (urllib.error.URLError, urllib.error.HTTPError, OSError) as e:
            if attempt == 2:
                return url, "fail:%s" % str(e)[:60], 0
            time.sleep(1.5 * (attempt + 1))
    return url, "fail", 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    urls = load_urls()
    print(f"待处理图片: {len(urls)} 张（输出目录 {IMG_ROOT}）")
    if not urls:
        print("data.js 中没有找到图片 URL，请先运行 tools/build-data.py")
        return 1

    stats = {"ok": 0, "skip": 0, "fail": 0}
    fails = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(download_one, u, args.force): u for u in urls}
        for i, fut in enumerate(as_completed(futs), 1):
            url, status, size = fut.result()
            key = status.split(":")[0]
            stats[key] += 1
            if key == "fail":
                fails.append((url, status))
            if i % 50 == 0 or i == len(urls):
                print(f"  进度 {i}/{len(urls)}  ok={stats['ok']} skip={stats['skip']} fail={stats['fail']}")

    dt = time.time() - t0
    print(f"完成: 下载 {stats['ok']}，跳过 {stats['skip']}，失败 {stats['fail']}（{dt:.0f}s）")
    if fails:
        print("\n失败列表（可重跑脚本增量重试）:")
        for u, s in fails[:20]:
            print(f"  [{s}] {u}")
        if len(fails) > 20:
            print(f"  …共 {len(fails)} 条")
    return 0 if not fails else 2


if __name__ == "__main__":
    sys.exit(main())
