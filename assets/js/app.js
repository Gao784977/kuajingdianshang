/* ============================================================
   KASUGA 典藏馆 — 核心逻辑
   购物车 / 年龄验证 / 加价计算 / 渲染工具
   ============================================================ */

/* ---------- 价格计算（中间商差价） ---------- */
function applyMarkup(basePrice) {
  const p = Number(basePrice);
  if (!p || isNaN(p)) return 0;
  let out = p * SITE_CONFIG.markup;
  const r = SITE_CONFIG.rounding || 1;
  out = Math.ceil(out / r) * r;
  return out;
}

/* 返回 {price, regular}：均为加价后的展示价 */
function calcPrice(p) {
  const sale = Number(p.price) || 0;
  const regular = Number(p.regular) || 0;
  let price = applyMarkup(sale);
  let reg = applyMarkup(regular);
  if (!reg || reg <= price) reg = 0;
  return { price, regular: reg };
}

function fmtYen(n) {
  return Number(n).toLocaleString("ja-JP") + SITE_CONFIG.currencySymbol;
}

/* ---------- 购物车（localStorage） ---------- */
const Cart = {
  key: "kasuga_cart_v1",
  get() {
    try { return JSON.parse(localStorage.getItem(this.key)) || []; }
    catch (e) { return []; }
  },
  save(items) {
    localStorage.setItem(this.key, JSON.stringify(items));
    updateCartCount();
  },
  add(id, qty = 1) {
    const p = findProduct(id);
    if (!p) return false;
    if (!p.stock) { showToast("该商品已售罄", "warn"); return false; }
    const items = this.get();
    const found = items.find((i) => i.id === id);
    if (found) found.qty += qty;
    else items.push({ id, qty });
    this.save(items);
    return true;
  },
  updateQty(id, qty) {
    const items = this.get();
    const f = items.find((i) => i.id === id);
    if (!f) return;
    f.qty = Math.max(1, Math.floor(qty) || 1);
    this.save(items);
  },
  remove(id) {
    this.save(this.get().filter((i) => i.id !== id));
  },
  clear() { this.save([]); },
  count() {
    return this.get().reduce((s, i) => s + i.qty, 0);
  },
  subtotal() {
    return this.get().reduce((s, i) => {
      const p = findProduct(i.id);
      if (!p) return s;
      const { price } = calcPrice(p);
      return s + price * i.qty;
    }, 0);
  },
};

function updateCartCount() {
  document.querySelectorAll(".cart-count").forEach((el) => {
    const n = Cart.count();
    el.textContent = n;
    el.style.display = n > 0 ? "flex" : "none";
  });
}

/* ---------- Toast ---------- */
let toastTimer = null;
function showToast(msg, type = "ok") {
  let t = document.querySelector(".toast");
  if (!t) {
    t = document.createElement("div");
    t.className = "toast";
    document.body.appendChild(t);
  }
  const icon = type === "warn" ? "⚠️" : type === "ok" ? "✓" : "🛒";
  t.innerHTML = `<span>${icon}</span><span>${msg}</span>`;
  requestAnimationFrame(() => t.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 2200);
}

/* ---------- 年龄验证 ---------- */
function initAgeGate() {
  const passed = localStorage.getItem("kasuga_age_ok") === "1";
  if (passed) return;
  const gate = document.createElement("div");
  gate.className = "age-gate show";
  gate.innerHTML = `
    <div class="age-gate-card">
      <div class="gate-mark">加</div>
      <h2>您已满 ${SITE_CONFIG.ageLimit} 岁了吗？</h2>
      <p>本站销售烟草及相关商品。依据法规，仅向年满 ${SITE_CONFIG.ageLimit} 周岁的成年顾客提供服务。<br>未满年龄者请立即离开。</p>
      <div class="age-gate-actions">
        <button class="btn btn-primary" id="age-yes">已满 ${SITE_CONFIG.ageLimit} 岁，进入</button>
        <button class="btn btn-ghost" id="age-no">未满，离开</button>
      </div>
    </div>`;
  document.body.appendChild(gate);
  gate.querySelector("#age-yes").onclick = () => {
    localStorage.setItem("kasuga_age_ok", "1");
    gate.classList.remove("show");
    setTimeout(() => gate.remove(), 300);
  };
  gate.querySelector("#age-no").onclick = () => {
    document.body.innerHTML = `
      <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:#191714;color:#fff;text-align:center;padding:20px;">
        <div>
          <h1 style="font-family:serif;font-size:26px;margin-bottom:12px;">感谢您的诚实</h1>
          <p style="opacity:.6;font-size:14px;">本站内容仅对成年人开放。请在年满 ${SITE_CONFIG.ageLimit} 岁后再来访问。</p>
        </div>
      </div>`;
  };
}

/* ---------- 商品查找 ---------- */
let _productIndex = null;
function getProductIndex() {
  if (_productIndex) return _productIndex;
  _productIndex = {};
  (typeof PRODUCTS !== "undefined" ? PRODUCTS : []).forEach((p) => {
    _productIndex[p.id] = p;
    if (p.slug) _productIndex["slug:" + p.slug] = p;
  });
  return _productIndex;
}
function findProduct(id) { return getProductIndex()[id] || null; }
function findProductBySlug(slug) { return getProductIndex()["slug:" + slug] || null; }

/* ---------- 分类工具 ---------- */
function catByKey(key) {
  const cats = typeof CATEGORIES !== "undefined" ? CATEGORIES : [];
  for (const c of cats) {
    if (c.key === key) return c;
    const ch = (c.children || []).find((k) => k.key === key);
    if (ch) return ch;
  }
  return null;
}
function catTopOf(key) {
  return (typeof CATEGORIES !== "undefined" ? CATEGORIES : []).find(
    (c) => c.key === key || (c.children || []).some((k) => k.key === key)
  ) || null;
}
function catName(key) { const c = catByKey(key); return c ? c.name : key; }

/* ---------- 图片（本地优先，原站兜底） ---------- */
function productImg(p, size = "") {
  if (p.imgLocal) return p.imgLocal;
  return p.img || "";
}

/* ---------- 渲染：商品卡 ---------- */
function renderProductCard(p) {
  const { price, regular } = calcPrice(p);
  const c = catByKey(p.cat);
  const off = regular ? Math.round((1 - price / regular) * 100) : 0;
  const badge = !p.stock
    ? `<span class="badge badge-out">售罄</span>`
    : p.isNew
      ? `<span class="badge badge-new">新品</span>`
      : p.isSale
        ? `<span class="badge badge-sale">促销中</span>`
        : "";
  return `
  <article class="product-card" data-id="${p.id}">
    <a class="pc-img" href="product.html?id=${p.id}">
      ${badge ? `<span class="pc-badges">${badge}</span>` : ""}
      <img src="${productImg(p)}" alt="${escHtml(p.name)}" loading="lazy"
           onerror="this.onerror=null;this.src='${escAttr(p.img || "")}';">
    </a>
    <div class="pc-body">
      <span class="pc-cat">${escHtml(c ? c.nameEn || c.name : "")}</span>
      <h3 class="pc-name"><a href="product.html?id=${p.id}">${escHtml(p.name)}</a></h3>
      ${p.spec ? `<p class="pc-spec">${escHtml(p.spec)}</p>` : ""}
      <div class="pc-price-row">
        <span class="pc-price">${fmtYen(price)}</span>
        ${regular ? `<span class="pc-regular">${fmtYen(regular)}</span><span class="pc-off">-${off}%</span>` : ""}
      </div>
      ${p.stock
        ? `<button class="pc-add" onclick="addToCart(${p.id}, this)">加入购物车</button>`
        : `<button class="pc-add" disabled>暂时售罄</button>`}
    </div>
  </article>`;
}

function addToCart(id, btn) {
  if (Cart.add(id, 1)) {
    if (btn) {
      btn.classList.add("added");
      btn.textContent = "已加入 ✓";
      setTimeout(() => { btn.classList.remove("added"); btn.textContent = "加入购物车"; }, 1400);
    }
    showToast("已加入购物车");
  }
}

/* ---------- 渲染工具 ---------- */
function escHtml(s) {
  return String(s || "").replace(/[&<>"']/g, (m) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[m]);
}
function escAttr(s) { return escHtml(s); }

function qs(name) {
  return new URLSearchParams(location.search).get(name);
}

function starStr(n) {
  n = Math.round(n || 0);
  return "★★★★★".slice(0, n) + "☆☆☆☆☆".slice(0, 5 - n);
}

/* ---------- 评论区（localStorage 演示） ---------- */
const Reviews = {
  key: "kasuga_reviews_v1",
  getAll() {
    try { return JSON.parse(localStorage.getItem(this.key)) || {}; }
    catch (e) { return {}; }
  },
  forProduct(id) {
    return this.getAll()[id] || [];
  },
  add(id, review) {
    const all = this.getAll();
    if (!all[id]) all[id] = [];
    all[id].unshift({
      user: review.user,
      stars: review.stars,
      text: review.text,
      date: new Date().toISOString().slice(0, 10),
    });
    localStorage.setItem(this.key, JSON.stringify(all));
  },
};

/* ---------- 页面公共初始化 ---------- */
function initCommon() {
  initAgeGate();
  updateCartCount();
  const y = new Date().getFullYear();
  document.querySelectorAll(".js-year").forEach((el) => (el.textContent = y));
}
