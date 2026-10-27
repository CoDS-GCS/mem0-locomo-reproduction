/* P4 Search stage: one question as a graph */
PAGES.question = {
  async render(el, p, ctx) {
    let c = +(p.conv ?? 0), q = p.q != null ? +p.q : 0, all = p.all === '1';
    const pick = h('div', { class: 'card' }), top = h('div', { class: 'bar' }), strip = h('div', { class: 'card' }), box = h('div', { class: 'canvas tall' }), det = h('div', { class: 'card detail' });
    el.append(top, h('div', { class: 'split3' }, pick, h('div', {}, strip, legend(), box), det));
    renderDetail(det, null);
    const qp = questionPicker(pick, c, q, v => { q = v; load(); });
    top.append(h('label', {}, 'conversation'), convSelect(c, v => go('question', { conv: v, q: 0 })),
      h('label', {}, h('input', { type: 'checkbox', checked: all, onchange: e => { all = e.target.checked; load(true); } }), ' draw all 30 ranks'), fitButton(box));
    async function load(force) {
      setParams({ conv: c, q, all: all ? 1 : null }); qp.setSel(q);
      const spec = await api('question', { conv: c, q, all: all ? 1 : 0 });
      const m = spec.meta, A = m.analysis || {};
      strip.innerHTML = '';
      strip.append(h('div', {}, h('b', {}, m.question.question), ' ', h('span', { class: 'cat' }, `cat ${m.question.category} ${CATS[m.question.category] || ''}`), ' gold: ', h('b', {}, m.question.answer)),
        h('div', { class: 'bar' }, m.has_row ? h('span', { class: 'note' }, `search latency ${m.search_s.map(x => x.toFixed(2)).join(' s / ')} s (one per speaker) · answer latency ${m.answer_s.toFixed(2)} s`) : h('span', { class: 'note' }, 'search stage has not reached this question yet'),
          reasonPill(A.reason, A.reason === 'unknown' ? 'cannot be known yet' : A.reason_text), A.issues && A.issues.length > 1 ? h('span', { class: 'note' }, ' also: ' + A.issues.slice(1).join(', ')) : null,
          h('button', { class: 'btn small', onclick: ev => { watch.toggle(c, q); ev.target.textContent = watch.has(c, q) ? '★ following' : '☆ Follow'; } }, watch.has(c, q) ? '★ following' : '☆ Follow'),
          h('a', { href: `#/journey?qs=${c}:${q}` }, 'Journey'), ' · ', h('a', { href: `#/judge?conv=${c}&q=${q}` }, 'Judge')));
      drawGraph(box, spec, { force, rankDir: 'LR', onSelect: (id, d) => renderDetail(det, d) });
    }
    await qp.refresh(); await load(true);
    ctx.every(25000, async () => { await qp.refresh(); await load(false); });
  },
};
