/* ============================================================
   KASUGA 典藏馆 — 公共头尾注入
   页面里放 <div id="header"></div> / <div id="footer"></div>
   即可自动获得导航与页脚，改这里全站生效
   ============================================================ */

function injectLayout() {
  const nav = (active) => `
    <nav class="main-nav">
      <a href="shop.html" class="${active === "shop" ? "active" : ""}">全部商品</a>
      <a href="category.html?cat=japanese" class="${active === "jp" ? "active" : ""}">日本香烟</a>
      <a href="category.html?cat=heated" class="${active === "heated" ? "active" : ""}">加热式</a>
      <a href="category.html?cat=pipe-tobacco" class="${active === "pipe" ? "active" : ""}">烟斗丝</a>
      <a href="category.html?cat=cigar" class="${active === "cigar" ? "active" : ""}">雪茄</a>
      <a href="category.html?cat=rolling-tobacco" class="${active === "handroll" ? "active" : ""}">手卷</a>
      <a href="category.html?cat=accessory" class="${active === "acc" ? "active" : ""}">烟具</a>
      <a href="brands.html" class="${active === "brands" ? "active" : ""}">品牌目录</a>
      <a href="buyback.html" class="${active === "buyback" ? "active" : ""}">贵金属回收</a>
      <a href="community.html" class="${active === "community" ? "active" : ""}">社区</a>
    </nav>`;

  const header = document.getElementById("header");
  if (header) {
    const active = header.dataset.active || "";
    header.outerHTML = `
    <header class="site-header" id="header">
      <div class="topbar">
        <div class="container">
          <span>${SITE_CONFIG.tagline}</span>
          <span><a href="guide.html">购物指南</a> · <a href="faq.html">常见问题</a> · <a href="contact.html">联系我们</a></span>
        </div>
      </div>
      <div class="container">
        <a class="logo" href="index.html">
          <span class="logo-mark">加</span>
          <span class="logo-text">
            <span class="logo-name">${SITE_CONFIG.nameCn}</span>
            <span class="logo-sub">YOKOHAMA COLLECTION · ${SITE_CONFIG.name}</span>
          </span>
        </a>
        ${nav(active)}
        <div class="header-actions">
          <form class="search-box" id="header-search" action="shop.html" method="get" role="search">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
            <input type="search" name="q" placeholder="搜索商品…" aria-label="搜索商品" autocomplete="off">
          </form>
          <button type="button" class="icon-btn" id="search-toggle" title="搜索" aria-label="搜索">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
          </button>
          <a class="icon-btn" href="account.html" title="会员中心" aria-label="会员中心">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5"/></svg>
          </a>
          <a class="icon-btn" href="cart.html" title="购物车" aria-label="购物车">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 7h14l-1.5 13h-11z"/><path d="M6 7 5 3H2"/><circle cx="9" cy="21" r="1.4"/><circle cx="17" cy="21" r="1.4"/></svg>
            <span class="cart-count" style="display:none">0</span>
          </a>
        </div>
      </div>
    </header>`;

    // 头部搜索：点放大镜展开/收起，回车原生提交 → shop.html?q=关键词
    const st = document.getElementById("search-toggle");
    if (st) {
      const sb = document.getElementById("header-search");
      const inp = sb.querySelector("input");
      st.addEventListener("click", () => {
        const show = sb.style.display !== "flex";
        sb.style.display = show ? "flex" : "none";
        if (show) inp.focus();
        else inp.value = "";
      });
      document.addEventListener("keydown", (e) => {
        if (e.key === "Escape" && sb.style.display === "flex") {
          sb.style.display = "none";
          inp.value = "";
        }
      });
    }
  }

  const footer = document.getElementById("footer");
  if (footer) {
    footer.outerHTML = `
    <footer class="site-footer" id="footer">
      <div class="footer-main">
        <div class="container" style="display:contents">
          <div class="footer-brand">
            <span class="logo-mark">加</span>
            <p>${SITE_CONFIG.nameCn}<br>${SITE_CONFIG.tagline}</p>
            <p class="small" style="opacity:.55">本站仅供年满 ${SITE_CONFIG.ageLimit} 周岁的成年人访问。<br>吸烟有害健康。未成年人禁止购买与使用烟草制品。</p>
          </div>
          <div>
            <h4>商品分类</h4>
            <div class="footer-links">
              <a href="category.html?cat=japanese">日本香烟</a>
              <a href="category.html?cat=heated">加热式烟草</a>
              <a href="category.html?cat=rolling-tobacco">手卷烟丝</a>
              <a href="category.html?cat=pipe-tobacco">烟斗丝</a>
              <a href="category.html?cat=cigar">雪茄</a>
              <a href="category.html?cat=accessory">烟具耗材</a>
            </div>
          </div>
          <div>
            <h4>购物帮助</h4>
            <div class="footer-links">
              <a href="guide.html">购物指南</a>
              <a href="guide.html#shipping">配送说明</a>
              <a href="guide.html#returns">退换说明</a>
              <a href="faq.html">常见问题</a>
              <a href="contact.html">联系我们</a>
              <a href="about.html">关于我们</a>
            </div>
          </div>
          <div>
            <h4>特色服务</h4>
            <div class="footer-links">
              <a href="buyback.html">贵金属回收</a>
              <a href="brands.html">品牌目录</a>
              <a href="community.html">藏家社区</a>
              <a href="shop.html?sort=new">新品入馆</a>
              <a href="shop.html?sale=1">本周促销</a>
            </div>
          </div>
        </div>
      </div>
      <div class="footer-bottom">
        <div class="container">
          <span>© <span class="js-year"></span> ${SITE_CONFIG.name} · 横滨典藏馆</span>
          <span>演示站点 · 购物流程为模拟，未接入真实支付</span>
        </div>
      </div>
    </footer>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  injectLayout();
  initCommon();
});
