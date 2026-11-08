async () => {
  const PAGES = [8, 9, 10, 11, 12, 13, 14];
  const out = [];
  for (const p of PAGES) {
    try {
      const r = await fetch('/shop/page/' + p + '/', {credentials: 'include'});
      const html = await r.text();
      const doc = new DOMParser().parseFromString(html, 'text/html');
      const items = [...doc.querySelectorAll('li.product')].map(li => {
        const a = li.querySelector('a.woocommerce-LoopProduct-link') || li.querySelector('a[href*="/product/"]');
        let slug = '';
        try { slug = decodeURIComponent((new URL(a.href).pathname).replace(/^\/product\//, '').replace(/\/+$/, '')); } catch(e) {}
        const amts = [...li.querySelectorAll('.price .woocommerce-Price-amount')].map(x => (x.textContent.match(/\d+/g) || []).join('')).filter(x => x);
        const img = li.querySelector('img');
        let ip = '';
        if (img) {
          const s = img.currentSrc || img.src || img.getAttribute('data-lazy-src') || img.getAttribute('data-src') || '';
          const m = s.match(/uploads\/(.+?)(?:-\d+x\d+)?(\.(?:webp|jpe?g|png))/i);
          if (m) ip = m[1] + m[2];
        }
        return [slug, amts[0] || '', amts[1] || '', ip, li.classList.contains('outofstock') ? 0 : 1, li.classList.contains('sale') ? 1 : 0];
      });
      out.push([p, items]);
    } catch (e) { out.push([p, 'ERR:' + String(e).slice(0, 60)]); }
  }
  return JSON.stringify(out);
}