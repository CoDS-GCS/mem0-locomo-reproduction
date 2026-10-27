/* P5 Judge */
PAGES.judge = {
  async render(el, p, ctx) {
    let c = +(p.conv ?? 0), q = p.q != null ? +p.q : 0;
    const pick = h('div', { class: 'card' }), main = h('div', {}), top = h('div', { class: 'bar' });
    el.append(top, h('div', { class: 'split left' }, pick, main));
    const qp = questionPicker(pick, c, q, v => { q = v; load(); });
    top.append(h('label', {}, 'conversation'), convSelect(c, v => go('judge', { conv: v, q: 0 })));
    function toks(arr) { return h('div', {}, ...arr.map(([t, m]) => h('span', { class: 'tok' + (m ? ' m' : '') }, t + ' '))); }
    async function load() {
      setParams({ conv: c, q }); qp.setSel(q);
      const d = await api('judge', { conv: c, q });
      main.innerHTML = '';
      main.append(h('div', { class: 'card' }, h('b', {}, d.question.question), ' ', h('span', { class: 'cat' }, `cat ${d.question.category} ${CATS[d.question.category] || ''}`), h('div', {}, 'gold: ', h('b', {}, d.question.answer)),
        h('div', { class: 'note' }, h('a', { href: `#/journey?qs=${c}:${q}` }, 'Journey'), ' · ', h('a', { href: `#/question?conv=${c}&q=${q}` }, 'Search page'))));
      if (d.pending) { main.append(h('div', { class: 'card' }, 'This question has no answer yet (search stage not reached).')); return; }
      main.append(h('div', { class: 'card' }, h('h3', {}, 'Model answer'), h('div', {}, d.response)));
      const runs = h('div', { class: 'card' }, h('h3', {}, `Judge verdicts (${d.n_runs} of 10 runs finished)`));
      for (let k = 1; k <= 10; k++) { const v = d.verdicts[String(k)]; runs.append(h('span', { class: 'verd ' + (v == null ? 'p' : v ? 'c' : 'w') }, `run ${k}: ` + (v == null ? 'pending' : v ? 'CORRECT' : 'WRONG'))); }
      main.append(runs);
      if (d.f1 != null) main.append(h('div', { class: 'card' }, h('h3', {}, `F1 ${(100 * d.f1).toFixed(1)} · BLEU-1 ${(100 * d.bleu1).toFixed(1)}`), h('div', { class: 'lbl' }, 'answer tokens (green = also in the gold answer; F1 uses these set tokens)'), toks(d.pred_tokens),
        h('div', { class: 'lbl', style: 'margin-top:6px' }, 'gold tokens'), toks(d.gold_tokens), h('div', { class: 'note' }, `precision ${(d.precision ?? 0).toFixed(2)}, recall ${(d.recall ?? 0).toFixed(2)}. BLEU-1 is read from the eval file; it uses NLTK tokens, so its matches can differ slightly from the highlighted tokens.`)));
      else main.append(h('div', { class: 'card note' }, 'F1 and BLEU-1 appear when the first judge run has finished.'));
      main.append(h('div', { class: 'card' }, h('h3', {}, `Exact judge prompt (ACCURACY_PROMPT from ${d.template.file})`), h('pre', { class: 'tall' }, d.prompt || '(template not readable)')));
      const J = d.j;
      const tb = h('table', { class: 't' }, h('tr', {}, ...['category', 'J so far (mean ± std over finished runs)', 'runs'].map(x => h('th', {}, x))));
      for (const k of ['1', '2', '3', '4']) if (J.cats[k]) tb.append(h('tr', {}, h('td', { class: d.category == k ? 'on' : '' }, `${k} ${CATS[k]}`), h('td', {}, `${J.cats[k].mean.toFixed(2)} ± ${J.cats[k].std.toFixed(2)}`), h('td', {}, J.cats[k].n_runs)));
      if (J.overall) tb.append(h('tr', {}, h('td', {}, h('b', {}, 'overall')), h('td', {}, h('b', {}, `${J.overall.mean.toFixed(2)} ± ${J.overall.std.toFixed(2)}`)), h('td', {}, J.overall.n_runs)));
      main.append(h('div', { class: 'card' }, h('h3', {}, 'Category and overall J so far'), J.overall ? tb : h('div', { class: 'note' }, 'No finished judge run yet.')));
    }
    await qp.refresh(); await load();
    ctx.every(25000, async () => { await qp.refresh(); await load(); });
  },
};
