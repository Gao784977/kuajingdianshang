/* 分类页：按分类（一级/二级）浏览商品 */

(function () {
  const PER_PAGE = 36;
  let state = { cat: "", sort: "default", page: 1 };
  let family = null; // 一级分类对象
  let active = "";    // 当前选中的 key（可为一级或二级）

  const CAT_DESC = {
    cigarette: "从加热式到传统卷烟，覆盖主流与进口烟草原的全部谱系。",
    cigar: "从日常口粮到典藏级雪茄，由恒温恒湿柜妥善照料。",
    accessory: "卷烟纸、滤嘴、打火机到收纳烟具，一应俱全的耗材与工具。",
    coffee: "与烟草同样讲究的烘焙咖啡豆与挂耳精选。",
    alcohol: "威士忌、利口酒等成年人的佐烟之选。",
  };

  function keysOfTop(t) {
    return [t.key, ...(t.children || []).map((c) => c.key)];
  }

  function getFiltered() {
    if (!active) return [];
    let list;
    if (family && active === family.key) {
      const keys = keysOfTop(family);
      list = PRODUCTS.filter((p) => keys.includes(p.cat));
    } else {
      list = PRODUCTS.filter((p) => p.cat === active);
    }
    const price = (p) => calcPrice(p).price;
    switch (state.sort) {
      case "price-asc": list.sort((a, b) => price(a) - price(b)); break;
      case "price-desc": list.sort((a, b) => price(b) - price(a)); break;
      case "new": list.sort((a, b) => (b.date || "").localeCompare(a.date || "")); break;
      case "name": list.sort((a, b) => (a.name || "").localeCompare(b.name || "", "zh-Hans")); break;
    }
    return list;
  }

  function renderChips() {
    const wrap = document.getElementById("cat-chips");
    if (!family) { wrap.innerHTML = ""; return; }
    const total = PRODUCTS.filter((p) => keysOfTop(family).includes(p.cat)).length;
    let html = `<a class="filter-chip ${active === family.key ? "active" : ""}" href="category.html?cat=${family.key}">全部 ${escHtml(family.name)} · ${total}</a>`;
    (family.children || []).forEach((c) => {
      const n = PRODUCTS.filter((p) => p.cat === c.key).length;
      if (!n) return;
      html += `<a class="filter-chip ${active === c.key ? "active" : ""}" href="category.html?cat=${c.key}">${escHtml(c.name)} · ${n}</a>`;
    });
    wrap.innerHTML = html;
  }

  function renderPager(totalPages) {
    const pager = document.getElementById("pager");
    if (totalPages <= 1) { pager.innerHTML = ""; return; }
    let html = `<button class="page-btn" ${state.page === 1 ? "disabled" : ""} data-go="${state.page - 1}">←</button>`;
    const pages = [...new Set([1, totalPages, state.page - 1, state.page, state.page + 1])]
      .filter((p) => p >= 1 && p <= totalPages).sort((a, b) => a - b);
    let prev = 0;
    pages.forEach((p) => {
      if (p - prev > 1) html += `<span class="page-btn" style="border:none;background:none">…</span>`;
      html += `<button class="page-btn ${p === state.page ? "active" : ""}" data-go="${p}">${p}</button>`;
      prev = p;
    });
    html += `<button class="page-btn" ${state.page === totalPages ? "disabled" : ""} data-go="${state.page + 1}">→</button>`;
    pager.innerHTML = html;
    pager.querySelectorAll("button[data-go]").forEach((b) => {
      b.onclick = () => {
        state.page = +b.dataset.go;
        render();
        window.scrollTo({ top: 0, behavior: "smooth" });
      };
    });
  }

  function render() {
    const list = getFiltered();
    const totalPages = Math.max(1, Math.ceil(list.length / PER_PAGE));
    if (state.page > totalPages) state.page = totalPages;
    const slice = list.slice((state.page - 1) * PER_PAGE, state.page * PER_PAGE);

    document.getElementById("grid").innerHTML = slice.map(renderProductCard).join("");
    document.getElementById("grid").style.display = list.length ? "" : "none";
    document.getElementById("empty").style.display = list.length ? "none" : "block";
    document.getElementById("result-info").innerHTML =
      `显示 <b>${list.length ? (state.page - 1) * PER_PAGE + 1 : 0}–${Math.min(state.page * PER_PAGE, list.length)}</b> 件 / 共 <b>${list.length.toLocaleString()}</b> 件`;
    renderChips();
    renderPager(totalPages);
  }

  function renderOverview() {
    /* 无 cat 参数时：展示全部分类的总览卡片 */
    document.getElementById("cat-en").textContent = "All Collections";
    document.getElementById("cat-name").textContent = "全部典藏分类";
    document.getElementById("cat-desc").textContent = "从香烟、雪茄到烟具耗材，浏览馆内全部典藏分类。";
    document.title = "分类浏览 — KASUGA SHOJI 横滨典藏馆";
    document.getElementById("cat-chips").innerHTML = "";
    const bar = document.querySelector(".shop-toolbar");
    if (bar) bar.style.display = "none";
    document.getElementById("result-info").textContent = "";
    document.getElementById("pager").innerHTML = "";
    document.getElementById("empty").style.display = "none";
    const grid = document.getElementById("grid");
    grid.className = "collections-grid";
    grid.style.display = "";
    grid.innerHTML = CATEGORIES.map((c) => {
      const keys = keysOfTop(c);
      const n = PRODUCTS.filter((p) => keys.includes(p.cat)).length;
      return `
      <a class="collection-card" href="category.html?cat=${c.key}">
        <div class="cc-img"><img src="${escAttr(c.img || "")}" loading="lazy" alt=""
             onerror="this.onerror=null;this.src='${escAttr(c.imgRemote || "")}';"></div>
        <div class="cc-body">
          <span class="cc-en">${escHtml(c.nameEn || c.name)}</span>
          <h3 class="cc-name">${escHtml(c.name)}</h3>
          <p class="cc-desc">${escHtml(c.desc || "")} · ${n} 件在册</p>
        </div>
      </a>`;
    }).join("");
  }

  function resolve() {
    const key = qs("cat") || "";
    const top = catTopOf(key);
    if (!top) return false;
    family = top;
    active = key;
    return true;
  }

  function paintHero() {
    const c = catByKey(active);
    const en = document.getElementById("cat-en");
    const nm = document.getElementById("cat-name");
    const ds = document.getElementById("cat-desc");
    if (family && active === family.key) {
      en.textContent = family.nameEn || family.name;
      nm.textContent = family.name;
      ds.textContent = CAT_DESC[family.key] || "精选典藏分类。";
    } else if (c) {
      en.textContent = family ? family.nameEn : c.nameEn;
      nm.textContent = (family ? family.name + " · " : "") + c.name;
      ds.textContent = `${c.nameEn || c.name} 分类下的全部在册商品。`;
    }
    document.title = nm.textContent + " — KASUGA SHOJI 横滨典藏馆";
  }

  document.addEventListener("DOMContentLoaded", () => {
    if (typeof PRODUCTS === "undefined" || !PRODUCTS.length) {
      document.getElementById("cat-desc").textContent = "商品数据尚未生成，请先运行 tools/build-data.py。";
      document.getElementById("grid").style.display = "none";
      return;
    }
    if (!resolve()) {
      if (!qs("cat")) { renderOverview(); return; }
      document.getElementById("cat-name").textContent = "分类不存在";
      document.getElementById("cat-desc").innerHTML = '没有找到这个分类，<a href="shop.html">去看看全部商品</a> 或 <a href="category.html">浏览全部分类</a>';
      return;
    }
    if (qs("sort")) state.sort = qs("sort");
    document.getElementById("sort").addEventListener("change", (e) => {
      state.sort = e.target.value; state.page = 1; render();
    });
    paintHero();
    render();
  });
})();
