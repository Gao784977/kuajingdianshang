#!/usr/bin/env python3
"""合并抓取数据 + sitemap slug 解码 → 生成 assets/js/data.js

输入:
  - scrape-data/sitemaps/sitemap-*.txt        产品 URL + lastmod（全量 slug）
  - scrape-data/evaluates/pages-1-8.json.log  旧格式商店页数据（页1-7，页8截断丢弃）
  - scrape-data/batches/results/shop-*.json   新格式批次数据 [[page,[[slug,p0,p1,img,st,sa],..]],..]

输出:
  - assets/js/data.js   window.CATEGORIES / window.PRODUCTS（价格存原站原价，加价由前端 config.js 动态应用）

用法: python3 tools/build-data.py [--all]
  默认只收录有价格+图片的商品；--all 连缺价商品一起收（标记 stock=0）
"""
import glob
import json
import os
import re
import sys
from urllib.parse import unquote

BASE = os.path.dirname(os.path.abspath(__file__))  # → tools/
SD = os.path.join(BASE, "scrape-data")
OUT = os.path.normpath(os.path.join(BASE, "..", "assets", "js", "data.js"))

# ---------------- 品牌表（slug 小写 → 标准写法） ----------------
BRANDS = {
    "gizeh": "GIZEH", "zig zag": "ZIG-ZAG", "zig-zag": "ZIG-ZAG", "ocb": "OCB",
    "smoking": "SMOKING", "mascotte": "MASCOTTE", "elements": "ELEMENTS",
    "pure hemp": "PURE HEMP", "pure-hemp": "PURE HEMP", "pay pay": "PAY-PAY",
    "pay-pay": "PAY-PAY", "colts": "COLTS", "raw": "RAW", "iqos": "IQOS",
    "ploom": "PLOOM", "glo": "GLO", "camel": "CAMEL", "marlboro": "MARLBORO",
    "mevius": "MEVIUS", "seven stars": "SEVEN STARS", "seven-stars": "SEVEN STARS",
    "winston": "WINSTON", "caster": "CASTER", "parliament": "PARLIAMENT",
    "lark": "LARK", "kent": "KENT", "hope": "HOPE", "echo": "ECHO",
    "mild seven": "MILD SEVEN", "mild-seven": "MILD SEVEN",
    "american spirit": "AMERICAN SPIRIT", "american-spirit": "AMERICAN SPIRIT",
    "black devil": "BLACK DEVIL", "black-devil": "BLACK DEVIL",
    "gauloises": "GAULOISES", "gitanes": "GITANES", "bali hai": "BALI HAI",
    "ashford": "ASHFORD", "captain black": "CAPTAIN BLACK", "captain-black": "CAPTAIN BLACK",
    "partagas": "PARTAGAS", "cohiba": "COHIBA", "montecristo": "MONTECRISTO",
    "romeo y julieta": "ROMEO Y JULIETA", "upmann": "UPMANN", "hoyo": "HOYO",
    "peterson": "PETERSON", "dunhill": "DUNHILL", "f&d": "F&D",
    "sansho": "SANSHO", "karel": "KAREL", "tasteful": "TASTEFUL",
    "zen": "ZEN", "top": "TOP", "bugler": "BUGLER", "gambler": "GAMBLER",
    "villiger": "VILLIGER", "shargio": "SHARGIO", "juicy jay": "JUICY JAY",
    "juicy-jay": "JUICY JAY", "ryocigarette": "RYO", "sante": "SANTE",
    "clippers": "CLIPPERS", "clipper": "CLIPPER", "zippo": "ZIPPO", "s.t.dupont": "S.T. DUPONT",
    "fumo": "FUMO", "cigmate": "CIGMATE", "usb": "USB",
}

# ---------------- 分类关键词规则（顺序即优先级） ----------------
CAT_RULES = [
    # 雪茄配件（剪/保湿箱/烟灰缸等）须先于"雪茄"规则判定，归入烟具
    ("case",       r"雪茄剪|雪茄保湿|雪茄钻|雪茄烟灰缸|雪茄配件|cigar.?(?:cutter|scissors|saver|punch|ashtray)|humidor|ashtray"),
    ("cigarillo",  r"小雪茄|cigarillo|シガリロ|little.?cigar"),
    ("cigar",      r"雪茄|cigar(?!illo|ette)|cohiba|partagas|montecristo|upmann|romeo.?y.?julieta"),
    ("pipe-tobacco", r"烟斗丝|烟斗葉|pipe.?tobacco|パイプタバコ|パイプ葉"),
    ("rolling-tobacco", r"手卷烟丝|手巻|刻烟丝|刻み|刻煙草|shag|ローリングタバコ|leaf"),
    ("heated",     r"iqos|ploom|glo(?!ve)|加热|ヒートスティック|heatstick|スティック"),
    ("snus",       r"snus|口含|口含烟|ニコチン.?パウチ|パウチ|nicotine.?pouch"),
    ("snuff",      r"鼻烟|snuff|スナッフ"),
    ("coffee",     r"咖啡|coffee|コーヒー"),
    ("alcohol",    r"威士忌|whisky|whiskey|\bwine\b|ワイン|ビール|beer|焼酎|日本酒|果酒|梅酒|\bsake\b|ラム|\bgin\b|ジン|vodka|ウォッカ|brandy|ブランデー|liqueur|リキュール"),
    ("rolling-paper", r"卷烟纸|卷紙|煙紙|rolling.?paper|リングペーパー|ペーパー"),
    ("filter",     r"滤嘴|滤咀|过滤嘴|filter|フィルター|フィルターチップ|tips"),
    ("lighter",    r"打火机|ライター|lighter|火柴|オイル|フリント"),
    ("case",       r"烟盒|ケース|烟灰缸|灰皿|收纳| pouch|ポーチ|ホルダー|剪切器|カッター|罐|チューブ"),
    ("foreign",    r"marlboro|camel|winston|american.?spirit|gauloises|gitanes|black.?devil|kent|parliament|lark|dunhill"),
    ("japanese",   r"seven.?stars|mevius|mild.?seven|caster|hope|echo|lark|ピース|peace"),
]

CAT_META = {
    "heated": ("加热烟", "Heated Tobacco", "cigarette"),
    "snus": ("口含烟", "Snus", "cigarette"),
    "snuff": ("鼻烟", "Snuff", "cigarette"),
    "kizami": ("刻烟丝", "Chopped Tobacco", "cigarette"),
    "rolling-tobacco": ("手卷烟丝", "Rolling Tobacco", "cigarette"),
    "pipe-tobacco": ("烟斗丝", "Pipe Tobacco", "cigarette"),
    "foreign": ("外国香烟", "Foreign Cigarettes", "cigarette"),
    "japanese": ("日本香烟", "Japanese Cigarettes", "cigarette"),
    "cigarillo": ("小雪茄", "Cigarillo", "cigarette"),
    "cigar": ("雪茄", "Cigar", None),
    "rolling-paper": ("卷烟纸", "Rolling Papers", "accessory"),
    "filter": ("滤嘴/烟嘴", "Filters & Tips", "accessory"),
    "lighter": ("打火机/火源", "Lighters", "accessory"),
    "case": ("烟具/收纳", "Cases & Holders", "accessory"),
    "accessory-other": ("其他烟具", "Other Accessories", "accessory"),
    "coffee": ("咖啡", "Coffee", None),
    "alcohol": ("酒类", "Alcohol", None),
}

CATEGORIES_DEF = [
    {"key": "cigarette", "name": "香烟", "nameEn": "Cigarette & Tobacco", "home": True,
     "desc": "从加热式到传统卷烟的主流与进口谱系",
     "children": ["heated", "snus", "snuff", "kizami", "rolling-tobacco", "pipe-tobacco", "foreign", "japanese", "cigarillo"]},
    {"key": "cigar", "name": "雪茄", "nameEn": "Cigar", "home": True, "desc": "恒温恒湿柜照料的典藏级雪茄"},
    {"key": "accessory", "name": "烟具耗材", "nameEn": "Accessories", "home": True, "desc": "卷烟纸、滤嘴、火源与收纳工具",
     "children": ["rolling-paper", "filter", "lighter", "case", "accessory-other"]},
    {"key": "coffee", "name": "咖啡", "nameEn": "Coffee", "desc": "与烟草同样讲究的烘焙咖啡"},
    {"key": "alcohol", "name": "酒类", "nameEn": "Alcohol", "desc": "成年人的佐烟之选"},
]


def slug_to_name(slug):
    """slug → 展示名称（中文保持、品牌词大写、中英边界补空格）"""
    parts = slug.split("-")
    out = []
    for p in parts:
        low = p.lower()
        if low in BRANDS:
            p = BRANDS[low]
        out.append(p)
    s = " ".join(out)
    # 中日文字符与拉丁字母边界补空格（如 "50張gizeh" → "50張 GIZEH"）
    s = re.sub(r"([^\x00-\x7f\d])([A-Za-z])", r"\1 \2", s)
    s = re.sub(r"([A-Za-z])([^\x00-\x7f])", r"\1 \2", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def detect_brand(name):
    low = name.lower()
    for k, v in BRANDS.items():
        if k in low:
            return v
    m = re.match(r"^([A-Za-z][\w&.\- ]{0,20}?)\s", name)
    return m.group(1).upper() if m else ""


def detect_cat(name):
    low = name.lower()
    for key, pat in CAT_RULES:
        if re.search(pat, low):
            return key
    return "accessory-other"


def parse_sitemaps():
    """sitemap markdown 表格 → {slug: lastmod}"""
    products = {}
    pat = re.compile(r"\|\s*\d+\s*\|\s*<https://kasugashoji\.net/product/([^>]+)/?>\s*\|\s*<?(\d{4}-\d{2}-\d{2})")
    for f in glob.glob(os.path.join(SD, "sitemaps", "sitemap-*.txt")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                m = pat.search(line)
                if m:
                    slug = unquote(m.group(1)).strip("/")
                    products[slug] = m.group(2)
    return products


def load_shop_data():
    """返回 {slug: {price, regular, stock, sale, img}}"""
    data = {}

    def put(slug, p0, p1, img, st, sa):
        if not slug or not (p0 or p1):
            return
        p0, p1 = int(p0 or 0), int(p1 or 0) if p1 else 0
        price = p1 if (p1 and p0 and p1 < p0) else (p0 or p1)
        regular = p0 if (p1 and p0 and p1 < p0) else 0
        img_full = ""
        if img:
            # 使用原站基础文件名（不带 -WxH 尺寸后缀）：WordPress 原图必定存在，
            # 且与 download-images.py 的本地保存路径一致（imgLocal 不含后缀）
            base = img if img.startswith("http") else "https://kasugashoji.net/wp-content/uploads/" + img
            img_full = base
        data[slug] = {"price": price, "regular": regular, "stock": st, "sale": sa, "img": img_full}

    # 新格式批次结果
    for f in sorted(glob.glob(os.path.join(SD, "batches", "results", "shop-*.json"))):
        with open(f, encoding="utf-8") as fh:
            rows = json.load(fh)
        for row in rows:
            if not isinstance(row, list) or len(row) < 2 or not isinstance(row[1], list):
                continue
            for it in row[1]:
                if isinstance(it, list) and len(it) >= 6:
                    put(it[0], it[1], it[2], it[3], it[4], it[5])

    # 旧格式（页1-7；解析失败即截断处停止）
    old = os.path.join(SD, "evaluates", "pages-1-8.json.log")
    if os.path.exists(old):
        with open(old, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        m = re.search(r"Result:\s*", content)
        if m:
            raw = content[m.end():]
            try:
                pages = json.loads(raw)
            except Exception:
                # 截断容错：回退到最后一个完整 item
                last = raw.rfind("}]},")
                if last > 0:
                    try:
                        pages = json.loads(raw[: last + 3] + "]")
                    except Exception:
                        pages = []
                else:
                    pages = []
            for pg in pages:
                if pg.get("page", 99) >= 8:  # 页 8 已截断，丢弃等重抓
                    continue
                for it in pg.get("items", []):
                    nums = re.findall(r"[\d,]+", it.get("p", ""))
                    nums = [int(n.replace(",", "")) for n in nums if n]
                    p0 = nums[0] if nums else 0
                    p1 = nums[-1] if len(nums) > 1 else 0
                    if len(set(nums)) == 1:
                        p1 = 0
                    put(unquote(it.get("u", "").replace("https://kasugashoji.net/product/", "").strip("/")),
                        p0, p1, it.get("i", ""), it.get("st", 1), it.get("sa", 0))
    return data


def main():
    include_all = "--all" in sys.argv
    sitemap = parse_sitemaps()
    shop = load_shop_data()
    print(f"sitemap products: {len(sitemap)}, shop rows w/ price: {len(shop)}")

    # 商店数据与 sitemap 取并集：shop 行有价有图即收录（不在 sitemap 的用空日期）
    seen_slugs, products = set(), []
    all_slugs = sorted(set(shop) | set(sitemap))
    # 原站已删除、各尺寸变体均 404 的图片（2026-11-08 核验）→ 按占位图处理
    DEAD_IMGS = {"2026/08/pdavidoff-6-cigar-figurado-assortment-6-count-tin.webp"}
    for slug in all_slugs:
        s = shop.get(slug)
        lastmod = sitemap.get(slug, "")
        if not s or (not include_all and (not s["price"] or not s["img"])):
            continue
        name = slug_to_name(slug)
        cat = detect_cat(name)
        is_ph = "woocommerce-placeholder" in s["img"] or s["img"].split("/uploads/")[-1].lower() in DEAD_IMGS
        products.append({
            "id": 0, "slug": slug, "name": name,
            "brand": detect_brand(name), "cat": cat,
            "price": s["price"], "regular": s["regular"],
            "stock": s["stock"], "isSale": s["sale"],
            "img": "" if is_ph else s["img"],
            "imgLocal": "assets/img/placeholder.svg" if is_ph else (
                "assets/img/products/" + s["img"].split("/uploads/")[-1] if s["img"] else ""),
            "date": lastmod, "isNew": False,
        })

    # 重排 id：按价格升序（与原站默认一致）
    products.sort(key=lambda p: p["price"])
    for i, p in enumerate(products, 1):
        p["id"] = i
        d = p.pop("date", "")
        p["date"] = d

    cats = []
    for c in CATEGORIES_DEF:
        row = dict(c)
        # 首页典藏卡封面：取该家族第一件有货商品的图
        fam_keys = [row["key"]] + [k for k in row.get("children", [])]
        first = next((p for p in products if p["cat"] in fam_keys and p["stock"] and p["imgLocal"]), None)
        if first:
            row["img"] = first["imgLocal"]
            row["imgRemote"] = first["img"]
        if "children" in row:
            row["children"] = [{"key": k, "name": CAT_META[k][0], "nameEn": CAT_META[k][1]} for k in c["children"]]
        cats.append(row)

    out = ("/* 自动生成：python3 tools/build-data.py ｜ 价格为原站原价，前端按 config.js markup 加价 */\n"
            "const CATEGORIES = " + json.dumps(cats, ensure_ascii=False, separators=(",", ":")) + ";\n"
            "const PRODUCTS = " + json.dumps(products, ensure_ascii=False, separators=(",", ":")) + ";\n")

    outpath = OUT
    with open(outpath, "w", encoding="utf-8") as fh:
        fh.write(out)
    print(f"OK: wrote {len(products)} products -> {outpath} ({os.path.getsize(outpath)//1024} KB)")

    # 统计
    from collections import Counter
    cc = Counter(p["cat"] for p in products)
    print("category stats:", dict(cc.most_common()))


if __name__ == "__main__":
    main()
