/* 购物车页 */

function renderCart() {
  const items = Cart.get();
  const empty = document.getElementById("cart-empty");
  const main = document.getElementById("cart-main");
  if (!empty || !main) return;

  if (!items.length) {
    empty.style.display = "block";
    main.style.display = "none";
    return;
  }
  empty.style.display = "none";
  main.style.display = "";

  const body = document.getElementById("cart-body");
  body.innerHTML = items
    .map((it) => {
      const p = findProduct(it.id);
      if (!p) return "";
      const { price, regular } = calcPrice(p);
      return `
      <tr data-id="${p.id}">
        <td>
          <div class="cart-prod">
            <img src="${productImg(p)}" alt="" onerror="this.src='${escAttr(p.img || "")}'">
            <div>
              <a class="cp-name" href="product.html?id=${p.id}">${escHtml(p.name)}</a>
              <div class="cp-price">${fmtYen(price)}${regular ? "（促销价）" : ""}</div>
            </div>
          </div>
        </td>
        <td>${fmtYen(price)}</td>
        <td>
          <div class="cart-qty">
            <button onclick="cartQty(${p.id}, -1)">−</button>
            <input value="${it.qty}" onchange="cartQty(${p.id}, 0, this.value)">
            <button onclick="cartQty(${p.id}, 1)">＋</button>
          </div>
        </td>
        <td><b>${fmtYen(price * it.qty)}</b></td>
        <td><button class="cart-remove" onclick="cartRemove(${p.id})">移除</button></td>
      </tr>`;
    })
    .join("");

  const goods = Cart.subtotal();
  const ship = goods >= SITE_CONFIG.shipping.freeOver || goods === 0 ? 0 : SITE_CONFIG.shipping.flat;
  document.getElementById("sum-goods").textContent = fmtYen(goods);
  document.getElementById("sum-ship").textContent = ship === 0 ? "免费" : fmtYen(ship);
  document.getElementById("sum-total").textContent = fmtYen(goods + ship);
  document.getElementById("ship-hint").textContent =
    ship === 0
      ? "已满足满额包邮条件"
      : `再购 ${fmtYen(SITE_CONFIG.shipping.freeOver - goods)} 即可免运费`;
}

function cartQty(id, delta, absVal) {
  const items = Cart.get();
  const f = items.find((i) => i.id === id);
  if (!f) return;
  if (delta) f.qty = Math.max(1, f.qty + delta);
  else f.qty = Math.max(1, Math.min(99, Math.floor(Number(absVal)) || 1));
  Cart.save(items);
  renderCart();
}

function cartRemove(id) {
  Cart.remove(id);
  renderCart();
  showToast("已从购物车移除");
}

document.addEventListener("DOMContentLoaded", renderCart);
