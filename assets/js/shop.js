/* 商店页：搜索 / 筛选 / 排序 / 分页（全部客户端即时运算） */

(function () {
  const PER_PAGE = 36;
  let state = {
    q: "",
    cat: "",
    sale: false,
    instock: false,
    sort: "default",
    page: 1,
  };

  function readParams() {
    if (qs("cat")) state.cat = qs("cat");
    if (qs("sale") === "1") state.sale = true;
    if (qs("instock") === "1") state.instock = true;
    if (qs("sort")) state.sort = qs("sort");
    if (qs("q")) state.q = qs("q");
  }

  function parsePrice(p) {
    const { price } = calcPrice(p);
    return price;
  }

  function getFiltered() {
    let list = PRODUCTS.slice();
    if (state.cat) list = list.filter((p) => p.cat === state.cat);
    if (state.sale) list = list.filter((p) => p.isSale);
    if (state.instock) list = list.filter((p) => p.stock);
    if (state.q) {
      const k = state.q.toLowerCase();
      list = list.filter((p) =>
        (p.name || "").toLowerCase().includes(k) ||
        (p.nameEn || "").toLowerCase().includes(k) ||
        (p.brand || "").toLowerCase().includes(k) ||
        (p.spec || "").toLowerCase().includes(k)
      );
    }
    switch (state.sort) {
      case "price-asc": list.sort((a, b) => parsePrice(a) - parsePrice(b)); break;
      case "price-desc": list.sort((a, b) => parsePrice(b) - parsePrice(a)); break;
      case "new": list.sort((a, b) => (b.date || "").localeCompare(a.date || "")); break;
      case "name": list.sort((a, b) => (a.name || "").localeCompare(b.name || "", "zh-Hans")); break;
    }
    return list;
  }

  function renderSide() {
    const wrap = document.getElementById("side-cats");
    if (!wrap) return;
    let html = `<a class="side-link ${state.cat === "" ? "active" : ""}" href="shop.html">全部商品<span class="cnt">${PRODUCTS.length}</span></a>`;
    CATEGORIES.forEach((c) => {
      const n = PRODUCTS.filter((p) => p.cat === c.key).length;
      if (!n) return;
      html += `<a class="side-link ${state.cat === c.key ? "active" : ""}" href="shop.html?cat=${c.key}">${escHtml(c.name)}<span class="cnt">${n}</span></a>`;
    });
    wrap.innerHTML = html;
  }

  function renderChips() {
    const wrap = document.getElementById("active-chips");
    const chips = [];
    if (state.q) chips.push(["搜索：“" + state.q + "”", () => (state.q = "")]);
    if (state.cat) {
      const c = catByKey(state.cat);
      chips.push(["分类：" + (c ? c.name : state.cat), () => (state.cat = "")]);
    }
    if (state.sale) chips.push(["本周促销", () => (state.sale = false)]);
    if (state.instock) chips.push(["仅有货", () => (state.instock = false)]);
    if (!chips.length) { wrap.innerHTML = ""; return; }
    wrap.innerHTML =
      chips.map((c, i) => `<button class="filter-chip active" data-i="${i}">${escHtml(c[0])} ✕</button>`).join("") +
      `<a class="filter-chip" href="shop.html" style="text-decoration:none">清空全部</a>`;
    wrap.querySelectorAll("button").forEach((b) => {
      b.onclick = () => { chips[+b.dataset.i][1](); render(); };
    });
  }

  function renderPager(totalPages) {
    const pager = document.getElementById("pager");
    if (totalPages <= 1) { pager.innerHTML = ""; return; }
    let html = "";
    html += `<button class="page-btn" ${state.page === 1 ? "disabled" : ""} data-go="${state.page - 1}">←</button>`;
    const pages = new Set([1, totalPages, state.page - 1, state.page, state.page + 1]);
    let prev = 0;
    [...pages].filter((p) => p >= 1 && p <= totalPages).sort((a, b) => a - b).forEach((p) => {
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
    document.getElementById("empty").style.display = list.length ? "none" : "block";
    document.getElementById("grid").style.display = list.length ? "" : "none";
    document.getElementById("result-info").innerHTML =
      `显示 <b>${list.length ? (state.page - 1) * PER_PAGE + 1 : 0}–${Math.min(state.page * PER_PAGE, list.length)}</b> 件 / 共 <b>${list.length.toLocaleString()}</b> 件`;
    document.getElementById("total-count").textContent = PRODUCTS.length.toLocaleString();
    document.getElementById("q").value = state.q;
    document.getElementById("sort").value = state.sort;

    renderChips();
    renderPager(totalPages);
    renderSide();
  }

  document.addEventListener("DOMContentLoaded", () => {
    readParams();
    const qEl = document.getElementById("q");
    let timer;
    qEl.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => { state.q = qEl.value.trim(); state.page = 1; render(); }, 240);
    });
    document.getElementById("sort").addEventListener("change", (e) => {
      state.sort = e.target.value; state.page = 1; render();
    });
    render();
  });
})();
