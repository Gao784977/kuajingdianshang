async () => {
  const path = "/product-category/%E9%A6%99%E7%83%9F/"; // 香烟
  const out = [];
  for (let pg = 1; pg <= 40; pg++) {
    try {
      const url = pg === 1 ? path : path + "page/" + pg + "/";
      const r = await fetch(url, { credentials: "include" });
      if (!r.ok) { out.push([pg, "ERR:" + r.status]); continue; }
      const t = await r.text();
      const d = new DOMParser().parseFromString(t, "text/html");
      const slugs = [...d.querySelectorAll("li.product a.woocommerce-LoopProduct-link, li.product h2 a, li.product .woo-loop-title a, li.product a[href*='/product/']")]
        .map(a => { try { return decodeURIComponent(new URL(a.href).pathname.replace(/\/product\/([^/]+)\/?$/, "$1")); } catch (e) { return ""; } })
        .filter(s => s);
      out.push([pg, [...new Set(slugs)]]);
      if (slugs.length === 0) break;
    } catch (e) { out.push([pg, "ERR:" + String(e).slice(0, 50)]); }
    await new Promise(res => setTimeout(res, 600));
  }
  return JSON.stringify(out);
}
