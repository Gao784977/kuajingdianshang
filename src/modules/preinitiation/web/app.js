/* 预立项工作台 · 本地演示（S2）
 * 规则：前端只调用本地接口，业务规则全部由服务端 preinitiation.service 提供；
 * 用户输入一律用 textContent / createTextNode 展示，不拼入 innerHTML。
 */
'use strict';

const CALC_FIELDS = [
  'selling_price_usd', 'target_margin_pct', 'promotion_fee_ratio', 'fx_usd_to_cny',
  'fx_fetched_at', 'target_purchase_price_min_cny', 'target_purchase_price_max_cny',
  'target_qty', 'estimated_purchase_price_cny'
];
const META_FIELDS = ['note'];

const STATUS_LABEL = {
  ok: '可计算', input_incomplete: '输入不完整',
  not_computable: '不可计算', blocked: '已阻断'
};
const QTY_LABEL = { passed: '通过', violated: '不满足', unknown: '未知', not_applicable: '不适用' };
const QTY_CLASS = {
  passed: 'badge-ok', violated: 'badge-danger',
  unknown: 'badge-unknown', not_applicable: 'badge-unknown'
};
const PRICE_KIND_LABEL = {
  estimated: '首轮估算采购价', effective: '有效采购价（SKU 级）'
};
const MARGIN_CHECK_LABEL = { below: '低于目标', meets: '达到目标', above: '高于目标' };

const App = { state: null, token: null, dirty: false, saved: {} };

/* ------------------------------- 通用工具 ------------------------------- */

function el(tag, attrs, kids) {
  const node = document.createElement(tag);
  if (attrs) {
    for (const key of Object.keys(attrs)) {
      const val = attrs[key];
      if (val === null || val === undefined || val === false) continue;
      if (key === 'class') node.className = val;
      else if (key === 'text') node.textContent = String(val);
      else if (key === 'dataset') Object.assign(node.dataset, val);
      else if (key.startsWith('on') && typeof val === 'function') node.addEventListener(key.slice(2), val);
      else node.setAttribute(key, String(val));
    }
  }
  const list = kids === undefined || kids === null ? [] : [].concat(kids);
  for (const kid of list) {
    if (kid === null || kid === undefined || kid === false) continue;
    node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return node;
}

function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); }

function norm(v) { return v === undefined || v === null || String(v).trim() === '' ? null : String(v).trim(); }

function fieldInput(k, labelText, value, required) {
  const input = el('input', { type: 'text', 'data-k': k, value: value === null || value === undefined ? '' : String(value) });
  return el('label', { class: 'field' }, [
    el('span', { class: 'lbl', text: required ? labelText + ' *' : labelText }),
    input
  ]);
}

function toast(msg, kind, ms) {
  const box = document.getElementById('toast');
  box.className = 'toast ' + (kind || '');
  box.textContent = msg;
  box.classList.remove('hidden');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => box.classList.add('hidden'), ms || 3500);
}

function showError(err) {
  const code = err && err.code ? err.code : 'unknown_error';
  toast(`${err && err.message ? err.message : '操作失败'}（原因码：${code}）`, 'error', 6000);
}

/* 对话框：info 模式只有一个「确定」；confirm 模式返回 Promise<boolean> */
function openDialog(bodyNodes, opts) {
  const o = opts || {};
  const dlg = document.getElementById('dialog');
  const body = document.getElementById('dialog-body');
  const okBtn = document.getElementById('dialog-ok');
  const cancelBtn = document.getElementById('dialog-cancel');
  clear(body);
  for (const n of [].concat(bodyNodes)) body.append(n);
  cancelBtn.classList.toggle('hidden', !!o.single);
  okBtn.textContent = o.okText || '确定';
  dlg.classList.remove('hidden');
  return new Promise((resolve) => {
    const done = (val) => { dlg.classList.add('hidden'); okBtn.onclick = null; cancelBtn.onclick = null; resolve(val); };
    okBtn.onclick = () => done(true);
    cancelBtn.onclick = () => done(false);
  });
}

function confirmDialog(message) {
  return openDialog([el('p', { text: message })], { okText: '确定' });
}

function infoDialog(title, items) {
  const nodes = [el('p', { text: title })];
  if (items && items.length) {
    nodes.push(el('ul', { class: 'reason-list' }, items.map((it) =>
      el('li', {}, [el('span', { text: it.message || it.code }), el('code', { text: ' ' + (it.code || '') })]))));
  }
  return openDialog(nodes, { single: true });
}

/* ---------------------------------- API ---------------------------------- */

const Api = {
  token: null,
  async init() {
    const res = await fetch('/api/session', { cache: 'no-store' });
    const data = await res.json();
    this.token = data.token;
  },
  async getState() {
    const res = await fetch('/api/state', { cache: 'no-store' });
    const data = await res.json();
    if (!res.ok || !data.ok) throw Object.assign(new Error(data.message || '请求失败'), { code: data.code });
    return data.state;
  },
  async post(path, body) {
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Preinitiation-Token': this.token },
      body: JSON.stringify(body || {})
    });
    let data;
    try { data = await res.json(); } catch (e) { data = { ok: false, code: 'invalid_json', message: '响应不是合法 JSON。' }; }
    if (!res.ok || !data.ok) {
      throw Object.assign(new Error(data.message || '请求被拒绝'), { code: data.code || ('http_' + res.status) });
    }
    return data; // { ok, result, state }
  }
};

/* ------------------------------ 基础输入（A） ------------------------------ */

function readForm() {
  const out = {};
  document.querySelectorAll('#input-form [data-field]').forEach((inp) => {
    out[inp.dataset.field] = norm(inp.value);
  });
  return out;
}

function fillForm(input) {
  document.querySelectorAll('#input-form [data-field]').forEach((inp) => {
    const f = inp.dataset.field;
    const v = input ? input[f] : null;
    inp.value = v === null || v === undefined ? '' : String(v);
  });
}

function savedSnapshot(input) {
  const snap = {};
  if (!input) return snap;
  for (const f of CALC_FIELDS.concat(META_FIELDS)) snap[f] = norm(input[f]);
  return snap;
}

function refreshDirty() {
  const desired = readForm();
  const dirty = CALC_FIELDS.concat(META_FIELDS).some((f) => norm(desired[f]) !== norm(App.saved[f]));
  App.dirty = dirty;
  document.getElementById('dirty-badge').classList.toggle('hidden', !dirty);
  document.getElementById('dirty-calc-warn').classList.toggle('hidden', !dirty);
}

async function saveInput(event) {
  event.preventDefault();
  const state = App.state;
  if (!state) return;
  const desired = readForm();
  const hasSaved = !!(state.input && Object.keys(App.saved).length);
  const calc = {}, meta = {};
  for (const f of CALC_FIELDS) {
    if (hasSaved) { if (norm(desired[f]) !== norm(App.saved[f])) calc[f] = desired[f]; }
    else if (desired[f] !== null) calc[f] = desired[f];
  }
  for (const f of META_FIELDS) {
    if (hasSaved) { if (norm(desired[f]) !== norm(App.saved[f])) meta[f] = desired[f]; }
    else if (desired[f] !== null) meta[f] = desired[f];
  }
  if (!Object.keys(calc).length && !Object.keys(meta).length) { toast('没有可保存的变更。', 'warn'); return; }
  try {
    const data = await Api.post('/api/input/save', {
      task_id: state.workspace.task_id, asin: state.workspace.asin,
      calc_fields: calc, meta_fields: meta
    });
    App.dirty = false;
    renderAll(data.state);
    const input = data.state.input;
    document.getElementById('input-save-hint').textContent =
      `已保存：input_version=${input.input_version}，meta_version=${input.meta_version}`;
    const staleCalc = data.state.latest_calc && !data.state.latest_calc.is_current;
    const staleSnap = data.state.snapshots.some((s) => !s.is_current);
    if (staleCalc || staleSnap) toast('输入已更新：已有测算/快照结果已过期，请重新测算。', 'warn', 7000);
    else toast('输入已保存。', 'ok');
  } catch (err) { showError(err); }
}

/* ------------------------------ 手工候选（B） ------------------------------ */

const SkuEditor = {
  build(container, skus) {
    clear(container);
    (skus || []).forEach((sku) => container.append(this.block(sku)));
  },
  block(sku) {
    const s = sku || {};
    const block = el('div', { class: 'sku-block' });
    block.append(el('div', { class: 'grid' }, [
      fieldInput('sku_id', 'SKU 编号（必填）', s.sku_id, true),
      fieldInput('spec', '规格 / 颜色', s.spec),
      fieldInput('sku_price_cny', 'SKU 级采购价 (CNY)', s.sku_price_cny)
    ]));
    const ladderWrap = el('div');
    const addTier = el('button', {
      type: 'button', class: 'ghost small', text: '添加档位',
      onclick: () => ladderWrap.append(this.tierRow())
    });
    block.append(el('div', { class: 'subhead' }, [el('span', { text: '阶梯价' }), addTier]));
    block.append(ladderWrap);
    (s.ladder_prices || []).forEach((t) => ladderWrap.append(this.tierRow(t)));
    block.append(el('div', { class: 'row' }, [
      el('button', { type: 'button', class: 'ghost small', text: '删除该 SKU', onclick: () => block.remove() })
    ]));
    return block;
  },
  tierRow(tier) {
    const t = tier || {};
    const row = el('div', { class: 'ladder-row' });
    row.append(fieldInput('qty_from', '起始量（必填）', t.qty_from));
    row.append(fieldInput('qty_to', '上限（空=无上限）', t.qty_to));
    row.append(fieldInput('price_cny', '档位单价 (CNY)', t.price_cny));
    row.append(el('button', { type: 'button', class: 'ghost small', text: '删除', onclick: () => row.remove() }));
    return row;
  },
  collect(container) {
    const skus = [];
    container.querySelectorAll(':scope > .sku-block').forEach((block) => {
      const get = (k) => {
        const n = block.querySelector('[data-k="' + k + '"]');
        return n ? norm(n.value) : null;
      };
      const ladders = [];
      block.querySelectorAll('.ladder-row').forEach((row) => {
        const g = (k) => { const n = row.querySelector('[data-k="' + k + '"]'); return n ? norm(n.value) : null; };
        const from = g('qty_from'), to = g('qty_to'), price = g('price_cny');
        if (from === null && to === null && price === null) return;
        ladders.push({
          qty_from: from === null ? null : Number(from),
          qty_to: to === null ? null : Number(to),
          price_cny: price === null ? null : price
        });
      });
      skus.push({
        sku_id: get('sku_id') || '',
        spec: get('spec') || '',
        sku_price_cny: get('sku_price_cny'),
        ladder_prices: ladders
      });
    });
    return skus;
  }
};

function validateSkus(skus) {
  for (const sku of skus) {
    if (!sku.sku_id) return '每个 SKU 必须填写 SKU 编号。';
    for (const l of sku.ladder_prices) {
      if (l.qty_from === null || Number.isNaN(l.qty_from)) return '阶梯价必须填写起始量。';
      if (l.price_cny === null) return '阶梯价必须填写档位单价。';
      if (l.qty_to !== null && Number.isNaN(l.qty_to)) return '阶梯价上限需为数字或留空。';
    }
  }
  return null;
}

function readCandidateForm() {
  const get = (k) => { const n = document.querySelector('#candidate-form [data-c="' + k + '"]'); return n ? norm(n.value) : null; };
  return {
    offer_id: get('offer_id'), quote_source: get('quote_source'), quoted_at: get('quoted_at'),
    offer_price_cny: get('offer_price_cny'), tax_inclusive: get('tax_inclusive') || 'unknown',
    moq: get('moq')
  };
}

function resetCandidateForm() {
  document.querySelectorAll('#candidate-form [data-c]').forEach((n) => {
    if (n.tagName === 'SELECT') n.value = 'unknown'; else n.value = '';
  });
  SkuEditor.build(document.getElementById('sku-editor'), []);
}

async function addCandidate(event) {
  event.preventDefault();
  const state = App.state;
  const f = readCandidateForm();
  if (!f.offer_id) { toast('请填写 offer 编号。', 'error'); return; }
  if (!f.quote_source) { toast('手工候选必须填写报价来源。', 'error'); return; }
  if (!f.quoted_at) { toast('手工候选必须填写报价获取时间。', 'error'); return; }
  const skus = SkuEditor.collect(document.getElementById('sku-editor'));
  const invalid = validateSkus(skus);
  if (invalid) { toast(invalid, 'error'); return; }
  const body = {
    task_id: state.workspace.task_id, asin: state.workspace.asin,
    offer_id: f.offer_id, quote_source: f.quote_source, quoted_at: f.quoted_at,
    offer_price_cny: f.offer_price_cny || null,
    tax_inclusive: f.tax_inclusive === 'unknown' ? null : (f.tax_inclusive === 'true'),
    moq: f.moq || null, currency: 'CNY', skus: skus
  };
  try {
    const data = await Api.post('/api/candidates/add', body);
    renderAll(data.state);
    resetCandidateForm();
    toast('候选已保存。', 'ok');
  } catch (err) { showError(err); }
}

async function selectCandidate(offerId, skuId) {
  const state = App.state;
  try {
    const data = await Api.post('/api/candidates/select', {
      task_id: state.workspace.task_id, asin: state.workspace.asin, offer_id: offerId, sku_id: skuId
    });
    renderAll(data.state);
    const r = data.result;
    const priceNote = r.effective_purchase_price_cny
      ? `有效采购价 ${r.effective_purchase_price_cny} CNY`
      : `有效采购价缺失：${r.effective_price_reason_message || r.effective_price_reason}`;
    toast(`已选择 ${offerId} / ${skuId}。${priceNote}`, 'ok', 5000);
  } catch (err) { showError(err); }
}

async function editCandidate(offerId, changes) {
  const state = App.state;
  try {
    const data = await Api.post('/api/candidates/edit', {
      task_id: state.workspace.task_id, asin: state.workspace.asin, offer_id: offerId, changes: changes
    });
    renderAll(data.state);
    toast(`候选 ${offerId} 已更新（旧测算/快照已过期）。`, 'warn', 6000);
  } catch (err) { showError(err); }
}

/* ------------------------------ 演示测算（C） ------------------------------ */

async function runCalc(kind) {
  const state = App.state;
  if (App.dirty) {
    const ok = await confirmDialog('当前有未保存修改：测算将基于「已保存内容」，而不是当前表单内容。是否继续？');
    if (!ok) return;
  }
  try {
    const data = await Api.post('/api/calc/' + kind, { task_id: state.workspace.task_id, asin: state.workspace.asin });
    renderAll(data.state);
    toast('演示测算完成（固定测试结果，不可用于真实立项）。', 'ok', 4500);
  } catch (err) { showError(err); }
}

/* ------------------------------ 快照与事件（D） ------------------------------ */

async function createSnapshot() {
  const state = App.state;
  try {
    const data = await Api.post('/api/snapshot/create', {
      task_id: state.workspace.task_id, asin: state.workspace.asin, created_by: 'demo-user'
    });
    renderAll(data.state);
    toast('已生成不可变快照。', 'ok');
  } catch (err) { showError(err); }
}

async function confirmSnapshot(snapshotId, op) {
  const state = App.state;
  const path = op === 'demo' ? '/api/snapshot/demo-confirm'
    : op === 'real' ? '/api/snapshot/real-confirm' : '/api/snapshot/reject';
  try {
    const data = await Api.post(path, { snapshot_id: snapshotId, actor: 'demo-user' });
    const result = data.result;
    renderAll(data.state);
    if (result.ok) {
      const label = op === 'demo' ? '模拟确认' : op === 'real' ? '正式确认' : '标记拒绝';
      toast(result.already ? `${label}：已完成（幂等）。` : `${label}：完成。`, 'ok');
    } else {
      const items = result.reasons_detail || (result.reasons || []).map((c) => ({ code: c }));
      const title = op === 'real'
        ? '正式确认不可用——门禁未通过（未产生任何真实结果）：'
        : '操作被拒绝：';
      infoDialog(title, items);
    }
  } catch (err) { showError(err); }
}

/* --------------------------------- 导出（E） --------------------------------- */

async function exportSnapshot(snapshotId) {
  try {
    const data = await Api.post('/api/export', { snapshot_id: snapshotId });
    const payload = data.result;
    renderExportPreview(payload);
    downloadJson(`预立项待核验预览单-${snapshotId}-禁止用于审批或采购决策.json`, payload);
    toast('已导出「待核验预览单」（非正式测算；浏览器下载 ≠ 已提交审批）。', 'ok', 5000);
  } catch (err) { showError(err); }
}

function renderExportPreview(payload) {
  const notice = document.getElementById('export-notice');
  clear(notice);
  notice.append(el('div', { class: 'export-notice-main', text: payload.preview_notice || '' }));
  const meta = [];
  if (payload.watermark) meta.push(payload.watermark);
  const sv = payload.snapshot_versions || {};
  meta.push(`快照序号 snapshot_seq=${sv.snapshot_seq ?? '-'}，计算结果版本 calc_version=${sv.calc_version_ref ?? '-'}`);
  meta.push(payload.expired
    ? '本快照已过期：输入/参数/候选版本已变化，不再代表当前结果（旧快照仍可追溯）'
    : '本快照当前未过期（仍代表当前版本）');
  notice.append(el('div', { class: 'export-notice-meta', text: meta.join('；') }));
  notice.classList.remove('hidden');
  const pre = document.getElementById('export-preview');
  pre.textContent = JSON.stringify(payload, null, 2);
  pre.classList.remove('hidden');
}

function downloadJson(filename, payload) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = el('a', { href: url, download: filename });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/* -------------------------------- 渲染函数 -------------------------------- */

function renderVersions(state) {
  const v = state.versions || {};
  const box = document.getElementById('versions');
  clear(box);
  const chip = (label, val) => el('span', { class: 'vchip', text: `${label} v${val === null ? '-' : val}` });
  box.append(
    chip('输入 input_version', v.input_version),
    chip('meta_version', v.meta_version),
    chip('参数 params_version', v.params_version),
    chip('候选 sourcing_version', v.sourcing_version),
    chip('计算结果 calc_version', v.calc_version),
    chip('快照 snapshot_seq', v.snapshot_seq)
  );
  const params = state.params;
  box.append(el('span', {
    class: 'vchip',
    text: params ? (params.sample_parameters ? '参数来源：样例参数（虚构值）' : `参数来源：${params.source}`) : '参数：未载入'
  }));
}

function renderInput(state) {
  const box = document.getElementById('input-meta');
  clear(box);
  const input = state.input;
  if (!input) {
    box.append(el('span', { class: 'muted', text: '尚无输入。可点击「加载样例」或填写后保存。' }));
    return;
  }
  const kv = (k, val) => [el('span', { class: 'k', text: k + '：' }), el('span', { text: val })];
  box.append(
    el('span', {}, kv('input_version', input.input_version)),
    el('span', {}, kv('meta_version', input.meta_version)),
    el('span', {}, kv('updated_at', input.updated_at)),
    el('span', {}, kv('updated_by', input.updated_by || '（未记录）'))
  );
}

function renderCandidates(state) {
  const list = document.getElementById('candidate-list');
  clear(list);
  const cans = state.candidates || [];
  if (!cans.length) { list.append(el('p', { class: 'empty', text: '暂无候选。' })); return; }
  cans.forEach((c) => list.append(candidateCard(c)));
}

function candidateCard(c) {
  const isSelected = c.candidate_status === 'selected';
  const card = el('div', { class: 'cand' + (isSelected ? ' selected' : '') });

  const head = el('div', { class: 'cand-head' }, [
    el('span', { class: 'offer', text: c.offer_id }),
    el('span', { class: 'badge badge-info', text: '来源：手工录入' }),
    el('span', { class: 'badge badge-unknown', text: '准入未验证' }),
    isSelected ? el('span', { class: 'badge badge-ok', text: '已选择' }) : null
  ]);
  card.append(head);

  const meta = el('div', { class: 'cand-meta' });
  const kv = (k, val) => meta.append(el('span', {}, [el('span', { class: 'k', text: k + '：' }), el('span', { text: val })]));
  kv('报价来源', c.quote_source || '（缺失）');
  kv('报价获取时间', c.quoted_at || '（缺失）');
  kv('币种', c.currency);
  kv('含税口径', c.tax_inclusive === null ? '未知（不臆断）' : (c.tax_inclusive ? '含税' : '不含税'));
  kv('MOQ', c.moq === null ? '未知' : c.moq);
  kv('搜索/摘要报价', (c.offer_price_cny === null ? '无' : c.offer_price_cny + ' CNY') + '（仅展示，不参与计算）');
  card.append(meta);

  const table = el('table');
  table.append(el('thead', {}, el('tr', {}, [
    el('th', { text: 'SKU 编号' }), el('th', { text: '规格' }),
    el('th', { text: 'SKU 级采购价 (CNY)' }), el('th', { text: '阶梯价' }),
    el('th', { text: '有效采购价 (CNY)' }), el('th', { text: '数量适用性' }),
    el('th', { text: '操作' })
  ])));
  const tbody = el('tbody');
  (c.skus || []).forEach((sku) => {
    const tierText = (sku.ladder_prices || []).length
      ? sku.ladder_prices.map((t) => `${t.qty_from}–${t.qty_to === null ? '∞' : t.qty_to}: ${t.price_cny}`).join('；')
      : '无阶梯价';
    const effCell = sku.effective_purchase_price_cny === null
      ? el('div', {}, [
        el('span', { class: 'badge badge-warn', text: '无有效采购价' }),
        el('div', { class: 'tip', text: sku.effective_price_reason_message || sku.effective_price_reason || '' })
      ])
      : el('div', {}, [
        el('span', { text: sku.effective_purchase_price_cny }),
        el('div', { class: 'tip', text: 'SKU 级价格 · 参与复算/快照' })
      ]);
    const qtyCell = el('div', {}, [
      el('span', { class: 'badge ' + (QTY_CLASS[sku.qty_check] || 'badge-unknown'), text: QTY_LABEL[sku.qty_check] || sku.qty_check }),
      el('div', { class: 'tip', text: sku.qty_check_reason_message || sku.qty_check_reason || '' })
    ]);
    const selectBtn = el('button', {
      type: 'button', class: sku.selected ? 'ghost small' : 'small',
      text: sku.selected ? '已选择' : '选择此 SKU',
      onclick: () => selectCandidate(c.offer_id, sku.sku_id)
    });
    const tr = el('tr', { class: sku.selected ? 'sel-row' : '' }, [
      el('td', { text: sku.sku_id }),
      el('td', { text: sku.spec || '-' }),
      el('td', { class: 'num', text: sku.sku_price_cny === null ? '—（无 SKU 级价格）' : sku.sku_price_cny }),
      el('td', { text: tierText }),
      el('td', {}, effCell),
      el('td', {}, qtyCell),
      el('td', {}, selectBtn)
    ]);
    tbody.append(tr);
  });
  table.append(tbody);
  card.append(table);

  const editor = el('div', { class: 'hidden' });
  const editBtn = el('button', {
    type: 'button', class: 'ghost small', text: '编辑候选',
    onclick: () => { editor.classList.toggle('hidden'); editBtn.textContent = editor.classList.contains('hidden') ? '编辑候选' : '收起编辑'; }
  });
  card.append(el('div', { class: 'row' }, [editBtn]));
  card.append(editor);

  const editorForm = el('form', { class: 'stack' });
  const eGet = (k) => el('input', { type: 'text', 'data-e': k, value: '' });
  const offerPriceI = eGet('offer_price_cny');
  const moqI = eGet('moq');
  const sourceI = eGet('quote_source');
  const timeI = eGet('quoted_at');
  offerPriceI.value = c.offer_price_cny === null ? '' : c.offer_price_cny;
  moqI.value = c.moq === null ? '' : String(c.moq);
  sourceI.value = c.quote_source || '';
  timeI.value = c.quoted_at || '';
  const taxSel = el('select', { 'data-e': 'tax_inclusive' }, [
    el('option', { value: 'unknown', text: '未知（不臆断）' }),
    el('option', { value: 'true', text: '含税' }),
    el('option', { value: 'false', text: '不含税' })
  ]);
  taxSel.value = c.tax_inclusive === null ? 'unknown' : (c.tax_inclusive ? 'true' : 'false');

  editorForm.append(el('div', { class: 'grid' }, [
    el('label', { class: 'field' }, [el('span', { class: 'lbl', text: '报价来源' }), sourceI]),
    el('label', { class: 'field' }, [el('span', { class: 'lbl', text: '报价获取时间' }), timeI]),
    el('label', { class: 'field' }, [el('span', { class: 'lbl', text: '搜索/摘要报价 (CNY，仅展示)' }), offerPriceI]),
    el('label', { class: 'field' }, [el('span', { class: 'lbl', text: 'MOQ（未知留空）' }), moqI]),
    el('label', { class: 'field' }, [el('span', { class: 'lbl', text: '含税口径' }), taxSel])
  ]));

  const skuWrap = el('div', { class: 'sku-editor' });
  SkuEditor.build(skuWrap, c.skus || []);
  editorForm.append(el('div', { class: 'subhead' }, [
    el('span', { text: 'SKU 与阶梯价（修正数量适用性）' }),
    el('button', { type: 'button', class: 'ghost small', text: '添加 SKU', onclick: () => skuWrap.append(SkuEditor.block({})) })
  ]));
  editorForm.append(skuWrap);

  editorForm.append(el('div', { class: 'row' }, [
    el('button', { type: 'submit', class: 'primary', text: '保存修改' }),
    el('span', { class: 'muted', text: '修改后旧测算/快照会立即过期。' })
  ]));
  editorForm.addEventListener('submit', (e) => {
    e.preventDefault();
    const skus = SkuEditor.collect(skuWrap);
    const invalid = validateSkus(skus);
    if (invalid) { toast(invalid, 'error'); return; }
    const tax = taxSel.value;
    editCandidate(c.offer_id, {
      quote_source: sourceI.value.trim(), quoted_at: timeI.value.trim(),
      offer_price_cny: norm(offerPriceI.value), moq: norm(moqI.value),
      tax_inclusive: tax, skus: skus
    });
  });
  editor.append(editorForm);

  return card;
}

function renderCalc(state) {
  // 真实入口阻断原因
  const realBox = document.getElementById('real-entry-reasons');
  clear(realBox);
  const real = state.real_entry;
  realBox.append(el('div', { class: 'blocked-box' }, [
    el('div', {}, [el('strong', { text: '真实计算入口：不可用（blocked）' }),
      el('span', { class: 'muted', text: ' ' + (real.note || '') })]),
    el('ul', { class: 'reason-list' }, (real.reasons_detail || []).map((r) =>
      el('li', {}, [el('span', { text: r.message }), el('code', { text: ' ' + r.code })])))
  ]));

  // 结果
  const box = document.getElementById('calc-result');
  clear(box);
  const calc = state.latest_calc;
  if (!calc) { box.append(el('p', { class: 'empty', text: '尚未测算。' })); }
  else {
    const stale = !calc.is_current;
    const wrap = el('div', { class: 'result-box' + (stale ? ' stale' : '') });
    wrap.append(el('div', { class: 'result-head' }, [
      el('span', { class: 'badge ' + statusClass(calc.calc_status), text: '状态：' + (STATUS_LABEL[calc.calc_status] || calc.calc_status) }),
      el('span', { class: 'badge badge-demo', text: '固定测试结果（test_only）' }),
      stale ? el('span', { class: 'badge badge-warn', text: '结果已过期' }) : el('span', { class: 'badge badge-ok', text: '代表当前版本' })
    ]));
    if (calc.company_margin !== null) {
      const val = Number(calc.company_margin) * 100;
      wrap.append(el('div', { class: 'result-head', style: 'margin-top:8px' }, [
        el('span', { class: 'margin' + (val < 0 ? ' neg' : ''), text: `${val.toFixed(2)}%` }),
        el('span', { class: 'muted', text: '公司利润率（演示固定值，允许为负）' })
      ]));
    }
    if (calc.target_margin_check) {
      wrap.append(el('div', { class: 'muted', text: '目标利润率校验：' + (MARGIN_CHECK_LABEL[calc.target_margin_check] || calc.target_margin_check) }));
    }
    if (calc.purchase_price_cny !== null) {
      wrap.append(el('div', { text: `采用采购价：${calc.purchase_price_cny} CNY（${PRICE_KIND_LABEL[calc.purchase_price_kind] || calc.purchase_price_kind}）` }));
    }
    if ((calc.missing_detail || []).length) {
      wrap.append(el('div', {}, [el('strong', { text: '缺失项：' }), el('ul', { class: 'reason-list' },
        calc.missing_detail.map((m) => el('li', {}, [el('span', { text: m.message }), el('code', { text: ' ' + m.code })])))]));
    }
    if ((calc.reasons_detail || []).length) {
      wrap.append(el('div', {}, [el('strong', { text: '原因：' }), el('ul', { class: 'reason-list' },
        calc.reasons_detail.map((m) => el('li', {}, [el('span', { text: m.message }), el('code', { text: ' ' + m.code })])))]));
    }
    wrap.append(el('div', { class: 'refs' }, [
      el('span', { text: `引用 input_version v${calc.input_version_ref}` }),
      el('span', { text: `params_version v${calc.params_version_ref === null ? '-' : calc.params_version_ref}` }),
      el('span', { text: `sourcing_version v${calc.sourcing_version_ref === null ? '-' : calc.sourcing_version_ref}` }),
      el('span', { text: `formula=${calc.formula_version}` }),
      el('span', { text: `verification=${calc.verification}` }),
      el('span', { text: `mode=${calc.mode}` }),
      el('span', { text: `时间=${calc.calculated_at}` })
    ]));
    box.append(wrap);
    if (state.calc_history && state.calc_history.length > 1) {
      box.append(el('div', { class: 'muted', text: `测算历史共 ${state.calc_history.length} 条（仅展示最新一条的详情）。` }));
    }
  }

  const zm = document.getElementById('zero-margin');
  clear(zm);
  zm.textContent = '0% 毛利采购价上限：未启用（不展示虚构数值）—— ' + state.zero_margin_price.note;
}

function statusClass(status) {
  return { ok: 'badge-ok', input_incomplete: 'badge-warn', not_computable: 'badge-warn', blocked: 'badge-danger' }[status] || 'badge-unknown';
}

function renderSnapshots(state) {
  const list = document.getElementById('snapshot-list');
  clear(list);
  const snaps = (state.snapshots || []).slice().reverse();
  if (!snaps.length) { list.append(el('p', { class: 'empty', text: '暂无快照。' })); return; }
  snaps.forEach((s) => list.append(snapshotCard(s)));
}

function snapshotCard(s) {
  const c = s.content;
  const card = el('div', { class: 'snap' + (s.is_current ? '' : ' history') });
  card.append(el('div', { class: 'snap-head' }, [
    el('span', { class: 'sid', text: s.snapshot_id }),
    el('span', { class: 'badge ' + statusBadge(s.status), text: '状态：' + s.confirm_display }),
    s.is_current
      ? el('span', { class: 'badge badge-ok', text: '当前版本' })
      : el('span', { class: 'badge badge-warn', text: '历史（已过期，不代表当前版本）' })
  ]));
  card.append(el('div', { class: 'cand-meta' }, [
    el('span', {}, [el('span', { class: 'k', text: 'offer/SKU：' }), el('span', { text: `${c.offer_id} / ${c.sku_id}` })]),
    el('span', {}, [el('span', { class: 'k', text: '有效采购价：' }), el('span', { text: c.effective_purchase_price_cny + ' CNY' })]),
    el('span', {}, [el('span', { class: 'k', text: '数量适用性：' }), el('span', { class: 'badge ' + (QTY_CLASS[c.qty_check] || 'badge-unknown'), text: QTY_LABEL[c.qty_check] || c.qty_check })]),
    el('span', {}, [el('span', { class: 'k', text: '利润率：' }), el('span', { text: Number(c.company_margin_recalced) * 100 + '%（演示固定值）' })]),
    el('span', {}, [el('span', { class: 'k', text: '模式/验证：' }), el('span', { text: `${c.mode} / ${c.verification}` })]),
    el('span', {}, [el('span', { class: 'k', text: '创建：' }), el('span', { text: `${c.created_by} @ ${c.created_at}` })])
  ]));

  // 事件
  if ((s.events || []).length) {
    card.append(el('ul', { class: 'event-list' }, s.events.map((e) =>
      el('li', {}, [el('span', { text: `事件：${eventLabel(e.kind)}` }),
        el('code', { text: ` ${e.kind}` }),
        el('span', { text: ` · ${e.actor} @ ${e.at}${e.note ? ' · ' + e.note : ''}` })]))));
  } else {
    card.append(el('div', { class: 'muted', text: '尚无事件（待确认）。' }));
  }

  // 历史内容详情（显示当时内容，而非当前表单）
  const pre = el('pre', { class: 'json-preview', text: JSON.stringify(c, null, 2) });
  card.append(el('details', { class: 'history-detail' }, [
    el('summary', { text: '查看快照当时内容（不可变）' }), pre
  ]));

  // 操作
  const terminal = s.status === 'rejected' || s.status === 'real_confirmed';
  const actions = el('div', { class: 'snap-actions' });
  const demoBtn = el('button', {
    type: 'button', class: 'primary', text: '模拟确认',
    disabled: !s.is_current || s.status === 'demo_confirmed' || terminal,
    onclick: () => confirmSnapshot(s.snapshot_id, 'demo')
  });
  const realBtn = el('button', {
    type: 'button', text: '正式确认（不可用，查看门禁原因）',
    disabled: terminal,
    onclick: () => confirmSnapshot(s.snapshot_id, 'real')
  });
  const rejectBtn = el('button', {
    type: 'button', class: 'ghost small', text: '标记拒绝',
    disabled: !s.is_current || terminal,
    onclick: () => confirmSnapshot(s.snapshot_id, 'reject')
  });
  actions.append(demoBtn, realBtn, rejectBtn);
  if (!s.is_current) actions.append(el('span', { class: 'na', text: '该快照已过期，禁止新的确认操作。' }));
  card.append(actions);

  return card;
}

function statusBadge(status) {
  return { pending_confirm: 'badge-unknown', demo_confirmed: 'badge-info', real_confirmed: 'badge-ok', rejected: 'badge-danger' }[status] || 'badge-unknown';
}

function eventLabel(kind) {
  return { demo_confirmed: '模拟确认', real_confirmed: '正式确认', rejected: '拒绝' }[kind] || kind;
}

function renderExport(state) {
  const list = document.getElementById('export-list');
  clear(list);
  const snaps = (state.snapshots || []).slice().reverse();
  if (!snaps.length) { list.append(el('p', { class: 'empty', text: '暂无可导出的快照。' })); return; }
  snaps.forEach((s) => list.append(el('div', { class: 'snap' }, [
    el('div', { class: 'snap-head' }, [
      el('span', { class: 'sid', text: s.snapshot_id }),
      el('span', { class: 'badge ' + statusBadge(s.status), text: s.confirm_display }),
      s.is_current ? el('span', { class: 'badge badge-ok', text: '当前版本' }) : el('span', { class: 'badge badge-warn', text: '历史' })
    ]),
    el('div', { class: 'row' }, [
      el('button', {
        type: 'button', class: 'primary', text: '导出演示 JSON',
        onclick: () => exportSnapshot(s.snapshot_id)
      }),
      el('span', { class: 'muted', text: '文件名与内容均标注「演示，不可用于真实立项」；下载不代表已提交审批。' })
    ])
  ])));
}

/* -------------------------------- 整体渲染 -------------------------------- */

function renderAll(state) {
  App.state = state;
  document.getElementById('taskId').textContent = state.workspace.task_id;
  document.getElementById('asin').textContent = state.workspace.asin;
  document.getElementById('guarantee').textContent = state.guarantee;
  renderVersions(state);
  renderInput(state);
  renderCandidates(state);
  renderCalc(state);
  renderSnapshots(state);
  renderExport(state);
  if (!App.dirty) { fillForm(state.input); }
  App.saved = savedSnapshot(state.input);
  refreshDirty();
}

function hasData(state) {
  return !!(state.input || (state.candidates && state.candidates.length) || (state.snapshots && state.snapshots.length));
}

/* -------------------------------- 事件接线 -------------------------------- */

function wireEvents() {
  document.getElementById('input-form').addEventListener('submit', saveInput);
  document.getElementById('input-form').addEventListener('input', refreshDirty);

  document.getElementById('candidate-form').addEventListener('submit', addCandidate);
  document.getElementById('btn-add-sku').addEventListener('click', () => {
    document.getElementById('sku-editor').append(SkuEditor.block({}));
  });

  document.getElementById('btn-calc-first').addEventListener('click', () => runCalc('first'));
  document.getElementById('btn-calc-recalc').addEventListener('click', () => runCalc('recalc'));
  document.getElementById('btn-snapshot').addEventListener('click', createSnapshot);

  document.getElementById('btn-load-sample').addEventListener('click', async () => {
    if (App.state && hasData(App.state)) {
      const ok = await confirmDialog('加载样例会覆盖当前工作区（输入/候选/测算/快照全部被替换）。是否继续？');
      if (!ok) return;
    }
    try { const data = await Api.post('/api/workspace/load-sample', {}); App.dirty = false; renderAll(data.state); toast('已加载演示样例。', 'ok'); }
    catch (err) { showError(err); }
  });

  document.getElementById('btn-reset').addEventListener('click', async () => {
    const ok = await confirmDialog('清空演示数据将删除全部内存数据（输入/候选/测算/快照），且无法恢复。服务重启后同样会丢失。是否继续？');
    if (!ok) return;
    try { const data = await Api.post('/api/workspace/reset', {}); App.dirty = false; renderAll(data.state); toast('演示数据已清空。', 'ok'); }
    catch (err) { showError(err); }
  });
}

async function init() {
  await Api.init();
  wireEvents();
  SkuEditor.build(document.getElementById('sku-editor'), []);
  const state = await Api.getState();
  App.dirty = false;
  renderAll(state);
}

init().catch((err) => {
  toast('初始化失败：' + (err && err.message ? err.message : '未知错误'), 'error', 8000);
});
