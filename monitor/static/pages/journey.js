/* P6 Journey graph: questions across ALL stages on one canvas */
PAGES.journey = {
  async render(el, p, ctx) {
    let qs = (p.qs || '').split(',').filter(x => /^\d+:\d+$/.test(x));
    if (!qs.length) qs = watch.list().slice(0, 6);
    const bar = h('div', { class: 'bar' }), sum = h('div', { class: 'card' }), box = h('div', { class: 'canvas tall' }), det = h('div', { class: 'card detail' });
    el.append(bar, sum, legend(), h('div', { class: 'split' }, box, det));
    renderDetail(det, null);
    const inp = h('input', { type: 'text', placeholder: 'conv:question, e.g. 0:0', size: 12 });
    bar.append(inp, h('button', { class: 'btn', onclick: () => { const v = inp.value.trim(); if (/^\d+:\d+$/.test(v) && !qs.includes(v)) { qs.push(v); inp.value = ''; load(true); } } }, 'add'),
      h('button', { class: 'btn', onclick: () => { qs = [...new Set([...qs, ...watch.list()])]; load(true); } }, 'add watchlist'),
      h('button', { class: 'btn', onclick: () => { qs = []; load(true); } }, 'clear'), fitButton(box),
      h('span', { class: 'note' }, 'Stages not reached yet are grey “pending” nodes and fill in as the experiment runs (refresh every 25 s).'));
    async function load(force) {
      setParams({ qs: qs.join(',') });
      if (!qs.length) { sum.innerHTML = 'Pick a question: in the Dataset page press “Follow”, or type conv:question above.'; box.innerHTML = ''; box._cy = null; box._hash = null; return; }
      const spec = await api('journey', { qs: qs.join(',') });
      sum.innerHTML = '';
      sum.append(h('table', { class: 't' }, h('tr', {}, ...['question', 'gold', 'cat', 'first lost link', 'also', 'judge', ''].map(x => h('th', {}, x))),
        ...spec.summary.map(s => h('tr', {}, h('td', {}, h('a', { href: `#/question?conv=${s.c}&q=${s.qi}` }, `${s.c}:${s.qi}`), ' ', s.question), h('td', {}, s.gold), h('td', {}, s.category),
          h('td', {}, reasonPill(s.reason, s.reason === 'unknown' ? 'cannot be known yet' : s.reason_text), s.answered_ok_despite_loss ? h('div', { class: 'note' }, 'answer still judged correct') : null),
          h('td', { class: 'note' }, (s.issues || []).slice(1).join('; ')), h('td', {}, s.n_runs ? `${s.correct ? 'correct' : 'wrong'} (majority of ${s.n_runs})` : 'pending'),
          h('td', {}, h('button', { class: 'btn small', onclick: () => { qs = qs.filter(x => x !== `${s.c}:${s.qi}`); load(true); } }, '×'))))));
      drawGraph(box, spec, { force, rankDir: 'TB', rankSep: 46, nodeSep: 26, onSelect: (id, d) => renderDetail(det, d) });
    }
    ctx.every(25000, () => load(false));
    await load(true);
  },
};
