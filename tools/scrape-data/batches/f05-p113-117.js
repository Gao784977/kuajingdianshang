async () => {
  const PAGES = [113, 114, 115, 116, 117];
  const out = [];
  const scrapeDoc = (doc) => [...doc.querySelectorAll('li.product')].map(li => {
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
  for (const p of PAGES) {
      try {
      const ifr = document.createElement('iframe');
      ifr.style.cssText = 'width:1px;height:1px;position:fixed;left:-9999px;';
      ifr.src = '/shop/page/' + p + '/';
      const ok = await new Promise(res => {
        const t = setTimeout(() => res('timeout'), 18000);
        ifr.onload = () => { clearTimeout(t); setTimeout(() => res('ok'), 500); };
        ifr.onerror = () => { clearTimeout(t); res('err'); };
        document.body.appendChild(ifr);
      });
      if (ok !== 'ok') { out.push([p, 'ERR:iframe-' + ok]); ifr.remove(); continue; }
      const doc = ifr.contentDocument;
      if (!doc || /checking your browser|just a moment/i.test(doc.title)) { out.push([p, 'ERR:challenge']); ifr.remove(); continue; }
      out.push([p, scrapeDoc(doc)]);
      ifr.remove();
    } catch (e) { out.push([p, 'ERR:' + String(e).slice(0, 60)]); }
  }
  return JSON.stringify(out);
}
