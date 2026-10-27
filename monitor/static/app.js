/* Memory Journey: shared helpers, router, graph + detail renderers. Plain JS, no build step. */
const PAGES = {};
let META = null;
const state = { timers: [], cleanup: [] };

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === 'class') el.className = v;
    else if (k === 'html') el.innerHTML = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return el;
}
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

async function api(path, params) {
  const q = params ? '?' + new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null))) : '';
  const r = await fetch('/api/' + path + q);
  const d = await r.json();
  if (d && d.error) throw new Error(d.error);
  return d;
}

/* ---------- storage that may be unavailable ---------- */
const store = {
  get(k, dflt) { try { const v = localStorage.getItem('mj.' + k); return v == null ? dflt : JSON.parse(v); } catch (e) { return dflt; } },
  set(k, v) { try { localStorage.setItem('mj.' + k, JSON.stringify(v)); } catch (e) { /* private window: ignore */ } },
};

/* ---------- watchlist ---------- */
const watch = {
  list() { return store.get('watch', []); },
  has(c, q) { return this.list().includes(`${c}:${q}`); },
  toggle(c, q) {
    const l = this.list(), k = `${c}:${q}`, i = l.indexOf(k);
    if (i >= 0) l.splice(i, 1); else l.push(k);
    store.set('watch', l); this.render();
  },
  render() {
    const l = this.list();
    $('#watchn').textContent = l.length;
    const m = $('#watchmenu'); m.innerHTML = '';
    m.append(h('div', { class: 'note' }, 'Watched questions (saved in this browser). They share one canvas in the Journey page.'));
    for (const k of l) {
      const [c, q] = k.split(':');
      m.append(h('div', { class: 'row', onclick: () => { location.hash = `#/journey?qs=${k}`; m.classList.add('hidden'); } }, `${c}:${q}`, ' ',
        h('button', { class: 'btn small', onclick: e => { e.stopPropagation(); watch.toggle(+c, +q); } }, 'remove')));
    }
    if (l.length) m.append(h('div', { class: 'bar' }, h('button', { class: 'btn', onclick: () => { location.hash = `#/journey?qs=${l.join(',')}`; m.classList.add('hidden'); } }, 'Open all on one canvas')));
  },
};

/* ---------- router ---------- */
const NAV = [['overview', 'Overview'], ['dataset', 'Dataset'], ['add', 'Add batch'], ['memory', 'Memory'], ['question', 'Search'], ['judge', 'Judge'], ['journey', 'Journey'], ['about', 'About']];
function parseHash() {
  const [path, qs] = (location.hash.slice(2) || 'overview').split('?');
  return { page: path || 'overview', params: Object.fromEntries(new URLSearchParams(qs || '')) };
}
function go(page, params) {
  const q = new URLSearchParams(Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v != null && v !== '')));
  const target = `#/${page}${q.toString() ? '?' + q : ''}`;
  if (location.hash === target) route(); else location.hash = target;
}
function setParams(params) { // update the URL without re-rendering the page
  const { page } = parseHash();
  const q = new URLSearchParams(Object.fromEntries(Object.entries(params).filter(([, v]) => v != null && v !== '')));
  history.replaceState(null, '', `#/${page}?${q}`);
}
function leave() {
  state.timers.forEach(clearInterval); state.timers = [];
  state.cleanup.forEach(f => { try { f(); } catch (e) { } }); state.cleanup = [];
}
const ctx = {
  every(ms, fn) { state.timers.push(setInterval(fn, ms)); },
  onLeave(fn) { state.cleanup.push(fn); },
};
async function route() {
  leave();
  const { page, params } = parseHash();
  const P = PAGES[page] || PAGES.overview;
  document.querySelectorAll('#nav a').forEach(a => a.classList.toggle('on', a.dataset.p === page));
  const el = $('#page'); el.innerHTML = '';
  if (!META) return;
  try { await P.render(el, params, ctx); }
  catch (e) { el.append(h('div', { class: 'card' }, h('b', {}, 'This page could not be drawn: '), String(e.message || e))); console.error(e); }
}
async function loadMeta() {
  try {
    META = await api('meta');
    $('#expname').textContent = META.name + ' · ' + META.mode;
    const st = $('#status');
    st.textContent = META.ready ? `indexed ${META.refreshed ? META.refreshed.slice(11) : ''}` : 'indexing…';
    st.className = 'pill ' + (META.error ? 'bad' : META.ready ? 'ok' : 'warn');
    st.title = META.error || `stage: ${META.stage}`;
  } catch (e) { $('#status').textContent = 'server not reachable'; $('#status').className = 'pill bad'; }
}
async function start() {
  const nav = $('#nav');
  await loadMeta();
  for (const [p, label] of NAV) {
    if (META && !META.has_addlogs && (p === 'add' || p === 'memory')) continue;
    nav.append(h('a', { href: `#/${p}`, 'data-p': p }, label));
  }
  $('#watchbtn').addEventListener('click', () => $('#watchmenu').classList.toggle('hidden'));
  watch.render();
  window.addEventListener('hashchange', route);
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => document.querySelectorAll('.canvas').forEach(c => { if (c._cy) c._cy.style(cyStyle()); }));
  setInterval(loadMeta, 25000);
  route();
}

/* ---------- common widgets ---------- */
function convSelect(value, onchange) {
  const s = h('select', { onchange: e => onchange(+e.target.value) });
  for (const c of META.convs) s.append(h('option', { value: c.idx, selected: c.idx === +value }, `${c.idx} · ${c.a} & ${c.b}`));
  return s;
}
function legend() {
  return h('div', { class: 'legend' }, h('span', {}, h('i', { class: 'd' }), 'LOCOMO data'), h('span', {}, h('i', { class: 'm' }), 'stored / retrieved by Mem0'),
    h('span', {}, h('i', { class: 'l' }), 'LLM call (prompt in, answer out)'), h('span', {}, h('i', { class: 'c' }), 'answer model / judge'),
    h('span', {}, h('i', { class: 'r' }), 'red dashed edge = where information is lost'));
}
const CATS = { 1: 'single-hop', 2: 'temporal', 3: 'multi-hop', 4: 'open-domain', 5: 'adversarial' };
function reasonPill(r, text) { return h('span', { class: 'reason ' + (r === 'correct' ? 'correct' : r === 'unknown' ? 'unknown' : '') }, text || r); }

/* ---------- Cytoscape ---------- */
function cssVar(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function cyStyle() {
  const c = n => cssVar(n);
  const kind = (k, bg, bd) => ({ selector: `node[kind="${k}"]`, style: { 'background-color': c(bg), 'border-color': c(bd) } });
  return [
    { selector: 'node', style: { label: 'data(label)', 'text-wrap': 'wrap', 'text-max-width': 250, 'font-size': 12, 'text-valign': 'center', 'text-halign': 'center', shape: 'round-rectangle', width: 'label', height: 'label', padding: '9px', 'border-width': 1.5, color: c('--text'), 'background-color': c('--data-bg'), 'border-color': c('--data-bd') } },
    kind('data', '--data-bg', '--data-bd'), kind('mem', '--mem-bg', '--mem-bd'), kind('llm', '--llm-bg', '--llm-bd'), kind('coral', '--coral-bg', '--coral-bd'),
    { selector: '.pending', style: { 'border-style': 'dashed', opacity: 0.6 } },
    { selector: '.ghost', style: { 'border-style': 'dashed', 'background-opacity': 0.25 } },
    { selector: '.add', style: { 'border-color': c('--add'), 'border-width': 3 } },
    { selector: '.upd', style: { 'border-color': c('--upd'), 'border-width': 3 } },
    { selector: '.del', style: { 'border-color': c('--del'), 'border-width': 3 } },
    { selector: '.none', style: { 'border-style': 'dotted' } },
    { selector: '.error', style: { 'border-color': c('--del'), 'border-width': 4 } },
    { selector: '.evidence', style: { 'border-color': c('--mem-bd'), 'border-width': 6 } },
    { selector: '.hint', style: { 'border-color': c('--mem-bd'), 'border-width': 3, 'border-style': 'dotted' } },
    { selector: '.correct', style: { 'border-color': c('--add'), 'border-width': 4 } },
    { selector: '.wrong', style: { 'border-color': c('--del'), 'border-width': 4 } },
    { selector: '.fade', style: { opacity: 0.25 } },
    { selector: 'edge', style: { width: 1.6, 'line-color': c('--data-bd'), 'target-arrow-color': c('--data-bd'), 'target-arrow-shape': 'triangle', 'curve-style': 'bezier', label: 'data(label)', 'font-size': 9, color: c('--muted'), 'text-background-color': c('--panel'), 'text-background-opacity': 0.9, 'text-background-padding': 2, 'text-rotation': 'autorotate' } },
    { selector: 'edge.loss', style: { 'line-style': 'dashed', 'line-color': c('--loss'), 'target-arrow-color': c('--loss'), width: 3.5, color: c('--loss'), 'font-size': 11, 'font-weight': 'bold', 'text-max-width': 160, 'text-wrap': 'wrap' } },
    { selector: 'edge.kept', style: { 'line-color': c('--add'), 'target-arrow-color': c('--add') } },
    { selector: ':selected', style: { 'overlay-color': c('--accent'), 'overlay-opacity': 0.25, 'overlay-padding': 6 } },
  ];
}
let dagreReady = false;
function drawGraph(box, spec, opts = {}) {
  if (!dagreReady) { cytoscape.use(cytoscapeDagre); dagreReady = true; }
  const hash = JSON.stringify(spec.elements);
  box._spec = spec;
  if (box._cy && box._hash === hash && !opts.force) { box._cy.style(cyStyle()); return box._cy; }
  const keep = box._cy ? box._cy.$(':selected').map(n => n.id())[0] : null;
  if (box._cy) box._cy.destroy();
  const cy = cytoscape({ container: box, elements: JSON.parse(hash), style: cyStyle(), minZoom: 0.15, maxZoom: 2.5, wheelSensitivity: 0.25,
    layout: opts.layout || { name: 'dagre', rankDir: opts.rankDir || 'LR', nodeSep: opts.nodeSep || 18, rankSep: opts.rankSep || 70, edgeSep: 10, padding: 24, animate: false } });
  box._cy = cy; box._hash = hash;
  cy.on('tap', 'node, edge', e => {
    const id = e.target.id();
    if (opts.onSelect) opts.onSelect(id, box._spec.details[id], e.target);
  });
  if (keep && cy.getElementById(keep).length) { cy.getElementById(keep).select(); if (opts.onSelect) opts.onSelect(keep, spec.details[keep], cy.getElementById(keep)); }
  return cy;
}
function fitButton(box) { return h('button', { class: 'btn small', onclick: () => box._cy && box._cy.fit(undefined, 30) }, 'fit'); }

/* ---------- detail panel ---------- */
function wordDiff(a, b) {
  const x = a.split(/\s+/).filter(Boolean), y = b.split(/\s+/).filter(Boolean);
  const n = x.length, m = y.length, L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out = []; let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { out.push(document.createTextNode(x[i] + ' ')); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) { out.push(h('del', {}, x[i] + ' ')); i++; }
    else { out.push(h('ins', {}, y[j] + ' ')); j++; }
  }
  while (i < n) out.push(h('del', {}, x[i++] + ' '));
  while (j < m) out.push(h('ins', {}, y[j++] + ' '));
  return out;
}
function markedPre(text, marks) {
  const pre = h('pre', { class: 'tall' });
  let pos = 0;
  for (const m of marks || []) {
    if (m.start < pos) continue;
    pre.append(document.createTextNode(text.slice(pos, m.start)), h('mark', { class: m.cls }, text.slice(m.start, m.end)));
    pos = m.end;
  }
  pre.append(document.createTextNode(text.slice(pos)));
  return pre;
}
function renderDetail(el, d) {
  el.innerHTML = '';
  if (!d) { el.append(h('div', { class: 'note' }, 'Click a node or edge to see its details here.')); return; }
  el.append(h('h2', {}, d.title || ''), d.subtitle ? h('div', { class: 'sub' }, d.subtitle) : null);
  for (const b of d.blocks || []) {
    const w = h('div', { class: 'blk' });
    if (b.label && b.t !== 'llm' && b.t !== 'nav') w.append(h('div', { class: 'lbl' }, b.label));
    if (b.t === 'p') w.append(h('div', {}, b.v));
    else if (b.t === 'pre') w.append(h('pre', {}, b.v));
    else if (b.t === 'kv') w.append(h('table', {}, ...b.rows.map(r => h('tr', {}, h('td', { class: 'muted' }, r[0]), h('td', {}, String(r[1]))))));
    else if (b.t === 'list') w.append(b.items.length ? h('ul', {}, ...b.items.map(i => h('li', {}, i))) : h('div', { class: 'note' }, '(none)'));
    else if (b.t === 'table') w.append(h('table', {}, h('tr', {}, ...b.head.map(x => h('th', {}, x))), ...b.rows.map(r => h('tr', {}, ...r.map(x => h('td', {}, String(x)))))));
    else if (b.t === 'diff') w.append(h('div', {}, ...wordDiff(b.a, b.b)));
    else if (b.t === 'prompt') w.append(markedPre(b.text, b.marks));
    else if (b.t === 'nav') w.append(h('a', { href: b.href }, b.label));
    else if (b.t === 'llm') {
      const slot = h('div');
      w.append(h('button', { class: 'btn small', onclick: async ev => {
        ev.target.disabled = true; slot.innerHTML = 'loading…';
        try {
          const r = await api('llm', { ref: b.ref }); slot.innerHTML = '';
          for (const m of r.messages || []) slot.append(h('div', { class: 'lbl' }, `prompt · role: ${m.role}`), h('pre', { class: 'tall' }, m.content));
          slot.append(h('div', { class: 'lbl' }, `raw answer${r.error ? ' (ERROR)' : ''} · ${r.seconds}s`), h('pre', { class: 'tall' }, r.error || (typeof r.response === 'string' ? r.response : JSON.stringify(r.response, null, 2))));
        } catch (e) { slot.textContent = String(e.message); }
      } }, b.label), slot);
    }
    el.append(w);
  }
}

/* ---------- small helpers ---------- */
function fmtPct(a, b) { return b ? Math.round(100 * a / b) + '%' : '–'; }
function stateTick(status) { return status; }

/* ---------- question picker (used by the Search and Judge pages) ---------- */
function questionPicker(box, c, selected, onPick) {
  let cats = new Set([1, 2, 3, 4]), text = '', qs = [], sel = selected;
  const chips = h('div', { class: 'chips' }), list = h('div', { class: 'list' });
  const search = h('input', { type: 'search', placeholder: 'filter…', style: 'width:100%;margin-bottom:6px', oninput: e => { text = e.target.value.toLowerCase(); draw(); } });
  box.append(chips, search, list);
  function draw() {
    chips.innerHTML = '';
    for (const k of [1, 2, 3, 4, 5]) chips.append(h('span', { class: 'chip' + (cats.has(k) ? ' on' : ''), onclick: () => { cats.has(k) ? cats.delete(k) : cats.add(k); draw(); } }, `${k} ${CATS[k]}`));
    list.innerHTML = '';
    for (const q of qs) {
      if (!cats.has(q.category) || (text && !(q.question + ' ' + q.answer).toLowerCase().includes(text))) continue;
      const mark = !q.answered ? '○' : q.judged ? (q.correct * 2 >= q.judged ? '✔' : '✘') : '●';
      list.append(h('div', { class: 'row' + (q.qi === sel ? ' on' : ''), title: !q.answered ? 'not answered yet' : q.judged ? `${q.correct} of ${q.judged} judge runs CORRECT` : 'answered, not judged yet', onclick: () => { sel = q.qi; draw(); onPick(q.qi); } },
        h('span', { class: 'cat' }, q.category), `${mark} ${q.qi}  `, q.question, h('div', { class: 'note' }, 'gold: ' + q.answer)));
    }
  }
  async function refresh() { const r = await api('questions', { conv: c }); qs = r.questions; draw(); }
  return { refresh, setSel(v) { sel = v; draw(); } };
}
