/* P1 Dataset explorer */
PAGES.dataset = {
  async render(el, p) {
    let c = +(p.conv ?? 0), si = p.si != null ? +p.si : 0, selQ = p.q != null ? +p.q : null, hiDia = p.dia || null;
    let catSel = new Set([1, 2, 3, 4]), text = '';
    const left = h('div', { class: 'card' }), mid = h('div', { class: 'card' }), right = h('div', { class: 'card' });
    const bar = h('div', { class: 'bar' }, h('label', {}, 'conversation'), convSelect(c, v => go('dataset', { conv: v })));
    el.append(bar, h('div', { class: 'split3' }, left, mid, right));
    const conv = await api('dataset/conv/' + c);
    const evOf = q => (q.evidence || []).flatMap(e => String(e).match(/D\d+:\d+/g) || []);
    const sessionOfDia = d => conv.sessions.findIndex(s => s.key === 'session_' + d.slice(1).split(':')[0]);
    if (hiDia && p.si == null) { const i = sessionOfDia(hiDia); if (i >= 0) si = i; }
    const qsel = () => conv.questions.find(q => q.qi === selQ);
    if (qsel() && p.si == null) { const e = evOf(qsel())[0]; if (e && sessionOfDia(e) >= 0) si = sessionOfDia(e); }

    function drawLeft() {
      left.innerHTML = ''; left.append(h('h3', {}, `${conv.a} & ${conv.b} — ${conv.sessions.length} sessions, ${conv.n_turns} turns`));
      conv.sessions.forEach((s, i) => left.append(h('div', { class: 'row' + (i === si ? ' on' : ''), onclick: () => { si = i; hiDia = null; drawLeft(); drawTurns(); } },
        `S${i + 1} · ${s.date}`, h('div', { class: 'note' }, `${s.n} turns` + (s.rel ? ` · ⏱ ${s.rel} with relative time words` : '')))));
    }
    async function drawTurns() {
      const s = await api(`dataset/session/${c}/${si}`);
      mid.innerHTML = ''; mid.append(h('h3', {}, `${s.key} · ${s.date}`));
      const ev = new Set(qsel() ? evOf(qsel()) : []); if (hiDia) ev.add(hiDia);
      for (const t of s.turns) {
        const row = h('div', { class: 'turn' + (ev.has(t.dia) ? ' ev' : ''), id: 'turn-' + t.dia.replace(':', '_') },
          h('span', { class: 'id' }, t.dia), h('b', {}, t.speaker), h('span', {}, t.text, t.rel.length ? h('span', { class: 'badge', title: 'relative time words: ' + t.rel.join(', ') }, '⏱ ' + t.rel.join(', ')) : null));
        mid.append(row);
      }
      const other = [...ev].filter(d => sessionOfDia(d) !== si);
      if (other.length) mid.prepend(h('div', { class: 'chips' }, h('span', { class: 'note' }, 'evidence in other sessions: '), ...other.map(d => h('span', { class: 'chip', onclick: () => { si = sessionOfDia(d); drawLeft(); drawTurns(); } }, `${d} → S${sessionOfDia(d) + 1}`))));
      const first = mid.querySelector('.turn.ev'); if (first) first.scrollIntoView({ block: 'center' });
    }
    function drawQs() {
      right.innerHTML = ''; right.append(h('h3', {}, `Questions (${conv.questions.length})`));
      right.append(h('div', { class: 'chips' }, ...[1, 2, 3, 4, 5].map(k => h('span', { class: 'chip' + (catSel.has(k) ? ' on' : ''), onclick: () => { catSel.has(k) ? catSel.delete(k) : catSel.add(k); drawQs(); } }, `${k} ${CATS[k]}`))));
      right.append(h('input', { type: 'search', placeholder: 'filter text…', value: text, style: 'width:100%;margin-bottom:6px', oninput: e => { text = e.target.value.toLowerCase(); drawList(); } }));
      const list = h('div', { class: 'list' }); right.append(list);
      const sel = qsel();
      if (sel) right.append(h('div', { class: 'bar' }, h('button', { class: 'btn', onclick: ev => { watch.toggle(c, sel.qi); ev.target.textContent = watch.has(c, sel.qi) ? '★ following' : '☆ Follow'; } }, watch.has(c, sel.qi) ? '★ following' : '☆ Follow'),
        h('a', { href: `#/journey?qs=${c}:${sel.qi}` }, 'open Journey'), ' · ', h('a', { href: `#/question?conv=${c}&q=${sel.qi}` }, 'Search page')));
      function drawList() {
        list.innerHTML = '';
        for (const q of conv.questions) {
          if (!catSel.has(q.category) || (text && !(q.question + ' ' + q.answer).toLowerCase().includes(text))) continue;
          list.append(h('div', { class: 'row' + (q.qi === selQ ? ' on' : ''), onclick: () => { selQ = q.qi; hiDia = null; const e = evOf(q)[0]; if (e && sessionOfDia(e) >= 0) si = sessionOfDia(e); drawLeft(); drawTurns(); drawQs(); setParams({ conv: c, q: selQ }); } },
            h('span', { class: 'cat' }, q.category), q.question, h('div', { class: 'note' }, `gold: ${q.answer} · evidence ${evOf(q).join(', ') || '–'}`)));
        }
      }
      drawList();
    }
    drawLeft(); await drawTurns(); drawQs();
  },
};
