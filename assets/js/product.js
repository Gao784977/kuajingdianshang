/* 商品详情页 */

(function () {
  let product = null;
  let selectedStars = 5;

  function render() {
    const id = qs("id") ? Number(qs("id")) : null;
    const slug = qs("slug");
    product = (id && findProduct(id)) || (slug && findProductBySlug(slug)) || null;

    document.getElementById("pd-loading").style.display = "none";
    if (!product) {
      document.getElementById("pd-notfound").style.display = "block";
      return;
    }
    document.getElementById("pd-wrap").style.display = "block";
    document.title = product.name + " — KASUGA SHOJI 横滨典藏馆";

    const cat = catByKey(product.cat);
    const { price, regular } = calcPrice(product);

    document.getElementById("bc-cat").textContent = cat ? cat.name : "商品";
    document.getElementById("bc-cat").href = "category.html?cat=" + product.cat;
    document.getElementById("bc-name").textContent = product.name;

    document.getElementById("pd-cat").textContent = cat ? cat.nameEn || cat.name : "";
    document.getElementById("pd-name").textContent = product.name;
    document.getElementById("pd-en").textContent = product.nameEn || "";
    document.getElementById("pd-spec").textContent = product.spec || "";

    const img = productImg(product);
    document.getElementById("pd-img").src = img;
    document.getElementById("pd-img").alt = product.name;
    document.getElementById("pd-img").onerror = function () {
      if (product.img) this.src = product.img;
    };

    document.getElementById("pd-price").textContent = fmtYen(price);
    document.getElementById("pd-regular").textContent = regular ? fmtYen(regular) : "";
    document.getElementById("pd-regular").style.display = regular ? "" : "none";

    document.getElementById("pd-stock").innerHTML = product.stock
      ? '<span class="in">● 有库存</span>'
      : '<span class="out">✕ 暂时售罄</span>';

    const addBtn = document.getElementById("pd-add");
    if (!product.stock) { addBtn.disabled = true; addBtn.textContent = "暂时售罄"; }
    addBtn.onclick = () => {
      const qty = Math.max(1, Number(document.getElementById("qty").value) || 1);
      if (Cart.add(product.id, qty)) showToast("已加入购物车（" + qty + " 件）");
    };

    document.getElementById("pd-meta").innerHTML = `
      <div><b>品牌</b>${escHtml(product.brand || "—")}</div>
      <div><b>分类</b>${escHtml(cat ? cat.name : "—")}</div>
      <div><b>商品编号</b>KSG-${String(product.id).padStart(5, "0")}</div>
      <div><b>上架时间</b>${escHtml((product.date || "—").replace(/T.*/, ""))}</div>`;

    // 相关推荐
    const related = PRODUCTS.filter((p) => p.cat === product.cat && p.id !== product.id && p.stock).slice(0, 4);
    if (related.length) {
      document.getElementById("related-wrap").hidden = false;
      document.getElementById("related").innerHTML = related.map(renderProductCard).join("");
    }

    renderStars();
    renderReviews();
  }

  function renderStars() {
    const wrap = document.getElementById("star-input");
    wrap.innerHTML = [1, 2, 3, 4, 5]
      .map((n) => `<span data-n="${n}" class="${n <= selectedStars ? "on" : ""}">★</span>`)
      .join("");
    wrap.querySelectorAll("span").forEach((s) => {
      s.onclick = () => { selectedStars = +s.dataset.n; renderStars(); };
    });
  }

  function renderReviews() {
    const list = Reviews.forProduct(product.id);
    const wrap = document.getElementById("review-list");
    if (!list.length) {
      wrap.innerHTML = '<p class="muted small" style="padding:24px 0">还没有评价，来做第一位分享的藏家。</p>';
      return;
    }
    wrap.innerHTML = list.map((r) => `
      <div class="review-item">
        <div class="ri-head">
          <div style="display:flex;gap:12px;align-items:center">
            <span class="ri-user">${escHtml(r.user || "匿名藏家")}</span>
            <span class="ri-stars">${starStr(r.stars)}</span>
          </div>
          <span class="ri-date">${escHtml(r.date)}</span>
        </div>
        <p>${escHtml(r.text)}</p>
      </div>`).join("");
  }

  document.addEventListener("DOMContentLoaded", () => {
    render();
    document.getElementById("qty-minus").onclick = () => {
      const el = document.getElementById("qty");
      el.value = Math.max(1, (Number(el.value) || 1) - 1);
    };
    document.getElementById("qty-plus").onclick = () => {
      const el = document.getElementById("qty");
      el.value = Math.min(99, (Number(el.value) || 1) + 1);
    };
    document.getElementById("review-form").addEventListener("submit", (e) => {
      e.preventDefault();
      if (!product) return;
      const text = document.getElementById("rv-text").value.trim();
      if (!text) return;
      Reviews.add(product.id, {
        user: document.getElementById("rv-user").value.trim() || "匿名藏家",
        stars: selectedStars,
        text,
      });
      document.getElementById("rv-text").value = "";
      renderReviews();
      showToast("评价已发布");
    });
  });
})();
