/* P3 Memory state and growth: list + entity graph, replay slider (from the logs) or live stores (Qdrant + Neo4j) */
PAGES.memory = {
  async render(el, p, ctx) {
    const S = { c: +(p.conv ?? 0), u: 0, mode: p.mode || 'replay', k: null, play: false, all: false, open: p.mem || null };
    const cv0 = () => META.convs.find(x => x.idx === S.c);
    if (p.user) S.u = p.user === `${cv0().b}_${S.c}` ? 1 : 0;
    const user = () => S.u ? `${cv0().b}_${S.c}` : `${cv0().a}_${S.c}`;
    const bar = h('div', { class: 'bar' }), info = h('div', { class: 'note' });
    const list = h('div', { class: 'card list', style: 'max-height:72vh' }), box = h('div', { class: 'canvas tall' });
    el.append(bar, info, h('div', { class: 'split left' }, list, h('div', {}, legend(), box)));
    let R = null, ST = null, timer = null;

    function replayState(k) {
      const mem = new Map(), edges = new Map(), d = { newM: new Set(), updM: new Set(), delM: new Set(), newE: new Set(), delE: [] };
      for (let i = 0; i <= k; i++) {
        const st = R.steps[i], cur = i === k;
        for (const [id, ev, text, prev] of st.mem) {
          if (ev === 'ADD') { mem.set(id, { id, text, alive: true, vers: [{ event: ev, text, step: i }] }); if (cur) d.newM.add(id); }
          else if (ev === 'UPDATE') { const m = mem.get(id) || { id, vers: [], alive: true }; m.text = text; m.alive = true; m.vers.push({ event: ev, text, prev, step: i }); mem.set(id, m); if (cur) d.updM.add(id); }
          else if (ev === 'DELETE') { const m = mem.get(id) || { id, vers: [], text }; m.alive = false; m.vers.push({ event: ev, text, step: i }); mem.set(id, m); if (cur) d.delM.add(id); }
        }
        for (const [s, r, t] of st.gadd) { const key = `${s}|${r}|${t}`; edges.set(key, { s, r, t, last: i }); if (cur) d.newE.add(key); }
        for (const [s, r, t] of st.gdel) { const key = `${s}|${r}|${t}`; if (edges.delete(key) && cur) d.delE.push({ s, r, t }); else if (cur) d.delE.push({ s, r, t, unseen: true }); }
      }
      return { mem, edges, d };
    }
    function graphSpec(edges, d, cap = 150) {
      const nodes = new Map();
      const touch = (n, last) => nodes.set(n, Math.max(nodes.get(n) ?? -1, last));
      for (const e of edges.values()) { touch(e.s, e.last); touch(e.t, e.last); }
      for (const e of d.delE) { touch(e.s, 1e9); touch(e.t, 1e9); }
      let keep = [...nodes.entries()].sort((a, b) => b[1] - a[1]).slice(0, cap).map(x => x[0]); const ks = new Set(keep);
      const newN = new Set(); for (const k of d.newE) { const e = edges.get(k); if (e) { newN.add(e.s); newN.add(e.t); } }
      const el = keep.map(n => ({ data: { id: 'n:' + n, label: n, kind: 'mem' }, classes: newN.has(n) ? 'add' : '' }));
      for (const [k, e] of edges) if (ks.has(e.s) && ks.has(e.t)) el.push({ data: { id: 'e:' + k, source: 'n:' + e.s, target: 'n:' + e.t, label: e.r }, classes: d.newE.has(k) ? 'kept' : '' });
      for (const [i, e] of d.delE.entries()) if (ks.has(e.s) && ks.has(e.t)) el.push({ data: { id: 'x:' + i, source: 'n:' + e.s, target: 'n:' + e.t, label: e.r + ' (deleted)' }, classes: 'loss' });
      return { elements: el, details: {}, capped: nodes.size > cap, total: nodes.size };
    }
    function memRow(m, cls, vers) {
      const row = h('div', { class: 'memrow ' + cls, id: 'm-' + m.id }, h('div', {}, m.text), h('div', { class: 'note' }, `id ${m.id.slice(0, 8)} · ${vers.length} version(s)`,
        ' ', h('a', { href: '#', onclick: e => { e.preventDefault(); const v = row.querySelector('.vers'); v.classList.toggle('hidden'); } }, 'history')));
      const v = h('div', { class: 'vers hidden' });
      vers.forEach((x, i) => v.append(h('div', {}, `v${i + 1} ${x.event}` + (x.step != null ? ` (step ${x.step + 1})` : ''), ' ', x.event === 'UPDATE' && x.prev ? h('span', {}, ...wordDiff(x.prev, x.text)) : x.text)));
      row.append(v); if (S.open === m.id) { v.classList.remove('hidden'); setTimeout(() => row.scrollIntoView({ block: 'center' }), 50); }
      return row;
    }
    function drawReplay() {
      const n = R.steps.length;
      if (!n) { info.textContent = 'No finished batches in the logs yet for this user.'; list.innerHTML = ''; return; }
      if (S.k == null || S.k >= n) S.k = n - 1;
      const { mem, edges, d } = replayState(S.k), st = R.steps[S.k];
      const alive = [...mem.values()].filter(m => m.alive).length;
      info.textContent = `step ${S.k + 1} of ${n} finished batches (${st.skey}, batch ${st.bi + 1}, ${st.date}) · ${alive} live memories, ${[...mem.values()].filter(m => !m.alive).length} deleted · ${edges.size} graph relations · replay of ${R.total_batches} batches in total`;
      list.innerHTML = ''; list.append(h('h3', {}, 'Memory store (from the add() logs)'),
        h('label', { class: 'note' }, h('input', { type: 'checkbox', checked: S.all, onchange: e => { S.all = e.target.checked; drawReplay(); } }), ' include deleted'));
      const rows = [...mem.values()].filter(m => S.all || m.alive || d.delM.has(m.id)).reverse();
      for (const m of rows) list.append(memRow(m, d.newM.has(m.id) ? 'new flashN' : d.updM.has(m.id) ? 'upd flashU' : !m.alive ? 'gone' : '', m.vers));
      const spec = graphSpec(edges, d);
      drawGraph(box, spec, { force: true, layout: { name: 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 80, padding: 20 } });
      if (spec.capped) info.textContent += ` · graph drawing capped at 150 of ${spec.total} entities (most recently touched kept)`;
    }
    async function drawLive() {
      const r = await api('memory/live', { conv: S.c, user: user() });
      list.innerHTML = ''; list.append(h('h3', {}, 'Live stores (read-only)'));
      const q = r.qdrant, n = r.neo4j;
      info.textContent = q.error ? 'Qdrant: ' + q.error : `Qdrant ${q.collection}: ${q.count} points for ${user()} · logs say ${r.log_alive} live memories` + (r.log_alive != null && r.log_alive !== q.count ? ' — DIFFERENT (batches still running, or a log gap)' : ' — consistent');
      for (const pt of (q.points || []).sort((a, b) => (a.created_at || '') < (b.created_at || '') ? -1 : 1)) list.append(memRow({ id: String(pt.id), text: pt.memory || '(no text)' }, '', [{ event: 'live', text: `created ${pt.created_at || '?'} · updated ${pt.updated_at || '–'}` }]));
      if (n.error) { box.innerHTML = '<p class="pad muted">Neo4j: ' + esc(n.error) + '</p>'; box._cy = null; box._hash = null; return; }
      const el = n.nodes.map(x => ({ data: { id: 'n:' + x.name, label: x.name, kind: 'mem' } })), ids = new Set(n.nodes.map(x => x.name));
      n.relationships.forEach((r2, i) => { if (ids.has(r2.source) && ids.has(r2.target)) el.push({ data: { id: 'e' + i, source: 'n:' + r2.source, target: 'n:' + r2.target, label: r2.relationship } }); });
      drawGraph(box, { elements: el, details: {} }, { force: true, layout: { name: 'cose', animate: false, nodeRepulsion: 9000, idealEdgeLength: 80, padding: 20 } });
      info.textContent += ` · Neo4j: ${n.node_count} nodes${n.capped ? ' (drawing capped at 150)' : ''}, ${n.relationships.length} relationships read`;
    }
    function controls() {
      bar.innerHTML = '';
      const n = R ? R.steps.length : 0;
      bar.append(h('label', {}, 'conversation'), convSelect(S.c, v => { S.c = v; S.k = null; load(); }), h('label', {}, 'store'),
        h('select', { onchange: e => { S.u = +e.target.value; S.k = null; load(); } }, h('option', { value: 0, selected: !S.u }, cv0().a + '_' + S.c), h('option', { value: 1, selected: !!S.u }, cv0().b + '_' + S.c)),
        h('button', { class: 'btn' + (S.mode === 'replay' ? ' on' : ''), onclick: () => { S.mode = 'replay'; load(); } }, 'Replay from logs'),
        h('button', { class: 'btn' + (S.mode === 'live' ? ' on' : ''), onclick: () => { S.mode = 'live'; load(); } }, 'Live stores'));
      if (S.mode === 'replay') {
        bar.append(h('input', { type: 'range', class: 'slider', min: 0, max: Math.max(0, n - 1), value: S.k ?? n - 1, oninput: e => { S.k = +e.target.value; drawReplay(); } }),
          h('button', { class: 'btn', onclick: ev => { S.play = !S.play; ev.target.textContent = S.play ? '⏸ pause' : '▶ play'; clearInterval(timer); if (S.play) { if (S.k >= n - 1) S.k = 0; timer = setInterval(() => { if (S.k < n - 1) { S.k++; drawReplay(); const s = bar.querySelector('input[type=range]'); if (s) s.value = S.k; } else { S.play = false; clearInterval(timer); controls(); } }, 700); } } }, S.play ? '⏸ pause' : '▶ play'),
          h('span', { class: 'note' }, 'new = green · updated = amber flash · deleted = red, struck through'));
      }
      bar.append(fitButton(box));
    }
    async function load() {
      if (S.mode === 'replay') { R = await api('memory/replay', { conv: S.c, user: user() }); controls(); drawReplay(); }
      else { controls(); await drawLive(); }
      setParams({ conv: S.c, u: S.u, mode: S.mode });
    }
    ctx.onLeave(() => clearInterval(timer));
    ctx.every(25000, () => { if (!S.play && (S.mode === 'live' || S.k == null || (R && S.k >= R.steps.length - 1))) { const k = S.k; load().then(() => { }); } });
    await load();
  },
};
