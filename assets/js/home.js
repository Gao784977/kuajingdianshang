/* 首页渲染 */

(function () {
  function render() {
    // 分类典藏卡
    const wrap = document.getElementById("home-collections");
    if (wrap && typeof CATEGORIES !== "undefined") {
      const homeCats = CATEGORIES.filter((c) => c.home);
      wrap.innerHTML = homeCats
        .map(
          (c) => `
        <a class="collection-card" href="category.html?cat=${c.key}">
          <div class="cc-img"><img src="${c.img}" alt="${escHtml(c.name)}" loading="lazy"
            onerror="if('${escAttr(c.imgRemote || "")}'&&this.src.indexOf('kasugashoji.net')<0){this.src='${escAttr(c.imgRemote || "")}'}else{this.style.display='none';this.parentNode.style.background='var(--bg-alt)'}"></div>
          <div class="cc-body">
            <div class="cc-en">${escHtml(c.nameEn)}</div>
            <div class="cc-name">${escHtml(c.name)}</div>
            <div class="cc-desc">${escHtml(c.desc)}</div>
            <span class="cc-go">查看系列 <span style="transition:margin .25s">→</span></span>
          </div>
        </a>`
        )
        .join("");
      wrap.querySelectorAll(".collection-card").forEach((a) => {
        a.addEventListener("mouseenter", () => (a.querySelector(".cc-go span").style.marginLeft = "6px"));
        a.addEventListener("mouseleave", () => (a.querySelector(".cc-go span").style.marginLeft = "0"));
      });
    }

    // 统计数字
    const stat = document.getElementById("hero-stats");
    if (stat && typeof PRODUCTS !== "undefined") {
      stat.children[0].firstElementChild.textContent = PRODUCTS.length.toLocaleString() + "+";
      stat.children[1].firstElementChild.textContent = (typeof CATEGORIES !== "undefined" ? CATEGORIES.length : 9);
      const brands = new Set(PRODUCTS.map((p) => p.brand).filter(Boolean));
      stat.children[2].firstElementChild.textContent = brands.size + "+";
    }

    // 本周推荐：促销中的在售商品
    const feat = document.getElementById("home-featured");
    if (feat && typeof PRODUCTS !== "undefined") {
      const featured = PRODUCTS.filter((p) => p.isSale && p.stock).slice(0, 8);
      const list = featured.length ? featured : PRODUCTS.filter((p) => p.stock).slice(0, 8);
      feat.innerHTML = list.map(renderProductCard).join("");
    }

    // 新品入馆：按上架时间倒序
    const nw = document.getElementById("home-new");
    if (nw && typeof PRODUCTS !== "undefined") {
      const news = [...PRODUCTS]
        .sort((a, b) => (b.date || "").localeCompare(a.date || ""))
        .filter((p) => p.stock)
        .slice(0, 8);
      nw.innerHTML = news.map(renderProductCard).join("");
    }
  }

  if (document.readyState === "DOMContentLoaded") render();
  else document.addEventListener("DOMContentLoaded", render);
})();
