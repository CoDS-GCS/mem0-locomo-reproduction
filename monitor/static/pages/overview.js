/* P7 Overview and "where answers get lost" */
PAGES.overview = {
  async render(el, p, ctx) {
    const top = h('div', {}), funnelBox = h('div', { class: 'card' }), lensBox = h('div', { class: 'card' });
    el.append(top, funnelBox, lensBox);
    let cat = store.get('funnelcat', 'all');
    const LABELS = { kept_word: 'kept the relative word', dropped: 'dropped the date', correct: 'correct date', invented: 'invented date', unverified: 'date present, not verifiable', no_memory: 'no memory created', pending: 'not added yet' };
    const COL = { kept_word: '--llm-bd', dropped: '--upd', correct: '--add', invented: '--del', unverified: '--data-bd', no_memory: '--coral-bd', pending: '--line' };

    async function drawTop() {
      const o = await api('overview');
      top.innerHTML = '';
      const k = (v, l, cls) => h('div', { class: 'card kpi' }, h('div', { class: 'v' }, v), h('div', { class: 'k' }, l));
      const idle = o.idle_min == null ? '–' : o.idle_min < 1 ? '< 1 min' : o.idle_min + ' min';
      top.append(h('div', { class: 'kpis' }, k(o.stage, 'current stage' + (o.stage_detail ? ' · ' + o.stage_detail : '')),
        h('div', { class: 'card kpi' }, h('div', { class: 'v' }, idle), h('div', { class: 'k' }, 'since the last log change'), o.warn_idle ? h('span', { class: 'pill warn' }, '⚠ more than 20 min: is the run stuck?') : null),
        k(`${o.search.answered} / ${o.search.total}`, 'questions answered (search stage)'), k(`${o.judge_runs} / 10`, 'judge runs finished'),
        ...(o.has_addlogs ? [k(o.counts.ADD, 'memories ADDED'), k(o.counts.UPDATE, 'memories UPDATED'), k(o.counts.DELETE, 'memories DELETED'), k(o.counts.NONE, 'NONE decisions (existing entries left unchanged)'),
          k(o.errors, 'add() attempts with an error'), k(o.skipped_batches, 'batches skipped after retries')] : [])));
      if (o.j && o.j.overall) top.append(h('div', { class: 'card' }, h('b', {}, `Overall J so far: ${o.j.overall.mean.toFixed(2)} ± ${o.j.overall.std.toFixed(2)}`), ` over ${o.j.overall.n_runs} judge run(s). `,
        ...['1', '2', '3', '4'].filter(c => o.j.cats[c]).map(c => h('span', { class: 'cat' }, `${CATS[c]} ${o.j.cats[c].mean.toFixed(1)}`))));
      if (o.has_addlogs) {
        const t = h('table', { class: 't' }, h('tr', {}, ...['conversation', 'store A', 'store B', 'add log', 'runner'].map(x => h('th', {}, x))));
        for (const c of o.convs) {
          const cell = u => h('td', {}, h('div', { class: 'prog' }, h('div', { style: `width:${100 * u.ok / Math.max(1, u.total)}%` })), `${u.ok}/${u.total} batches`, Object.entries(u.status).filter(([s]) => ['skipped', 'retrying', 'running'].includes(s)).map(([s, n]) => h('span', { class: 'pill warn' }, `${n} ${s}`)));
          t.append(h('tr', {}, h('td', {}, `${c.c} ${META.convs[c.c].a} & ${META.convs[c.c].b}`), cell(c.users[0]), cell(c.users[1]),
            h('td', { class: 'note' }, Object.entries(c.bar).map(([k2, v]) => `${k2}: ${v.done}/${v.total}`).join(' · '), c.crashes ? h('span', { class: 'pill bad' }, `${c.crashes} thread crash(es)`) : null, c.skipped_lines.length ? h('div', {}, c.skipped_lines[c.skipped_lines.length - 1].slice(0, 90)) : null),
            h('td', { class: 'note' }, c.finished ? c.finished.replace(/^\S+ \S+ /, '') : '')));
        }
        top.append(h('div', { class: 'card' }, h('h3', {}, 'Per-conversation progress (add stage)'), t));
      }
      top.append(h('details', { class: 'card' }, h('summary', {}, 'Last runner log lines'), h('pre', {}, o.runner_tail.join('\n'))));
    }
    async function drawFunnel() {
      const f = await api('funnel');
      funnelBox.innerHTML = '';
      funnelBox.append(h('h3', {}, 'Where answers get lost: evidence turn → answered correctly'),
        h('div', { class: 'note' }, 'Counted over scored questions (categories 1-4) that list evidence. A question passes a step only if it passed all earlier steps (for several evidence turns: all of them). Hatched = not yet known (that stage has not run). Click a step to list its questions.'));
      funnelBox.append(h('div', { class: 'chips' }, ...['all', '1', '2', '3', '4'].map(c => h('span', { class: 'chip' + (c === cat ? ' on' : ''), onclick: () => { cat = c; store.set('funnelcat', c); drawFunnel(); } }, c === 'all' ? 'all categories' : `${c} ${CATS[c]}`))));
      const F = f.cats[cat] || f.cats.all, n = F.n || 1;
      f.steps.forEach((name, i) => {
        if ((f.na || []).includes(i)) { funnelBox.append(h('div', { class: 'fr', style: 'cursor:default;opacity:.55' }, h('div', {}, `${i + 1}. ${name}`), h('div', { class: 'note' }, 'n/a: this run has no add-stage logs'), h('div', {})));  return; }
        const reach = F.reach[i], unk = F.unknown[i + 1] || 0;
        funnelBox.append(h('div', { class: 'fr', onclick: () => openList(i + 1) }, h('div', {}, `${i + 1}. ${name}`),
          h('div', { class: 'fbar' }, h('div', { style: `width:${100 * reach / n}%` }), h('div', { class: 'unk', style: `left:${100 * reach / n}%;width:${100 * Math.min(unk, F.n - reach) / n}%` })),
          h('div', { class: 'note' }, `${reach} of ${F.n} (${fmtPct(reach, F.n)})`)));
      });
      if (f.caveat) funnelBox.append(h('div', { class: 'pill warn', style: 'white-space:normal;margin-top:8px' }, f.caveat));
      if (F.despite) funnelBox.append(h('div', { class: 'note' }, `${F.despite} questions were judged correct although the evidence was lost somewhere (the answer was found elsewhere).`));
    }
    async function openList(step) {
      const modal = h('div', { class: 'modal', onclick: e => { if (e.target === modal) modal.remove(); } });
      const inner = h('div', {}), mode = { v: step === 1 ? 'reach' : 'drop' };
      modal.append(inner); document.body.append(modal);
      async function fill() {
        inner.innerHTML = 'loading…';
        const r = await api('funnel/list', { cat, step, mode: mode.v });
        inner.innerHTML = '';
        inner.append(h('div', { class: 'bar' }, h('b', {}, `Step ${step}`), ...['drop', 'reach', 'unknown'].map(m => h('span', { class: 'chip' + (mode.v === m ? ' on' : ''), onclick: () => { mode.v = m; fill(); } },
          { drop: 'lost at this step', reach: 'reached this step', unknown: 'not known yet' }[m])), h('span', { class: 'note' }, `${r.n} question(s)` + (r.n > r.items.length ? ` (first ${r.items.length} shown)` : '')),
          h('button', { class: 'btn small', onclick: () => modal.remove() }, 'close'),
          r.items.length ? h('button', { class: 'btn small', onclick: () => { location.hash = '#/journey?qs=' + r.items.slice(0, 8).map(x => `${x.c}:${x.qi}`).join(','); modal.remove(); } }, 'open first 8 on one canvas') : null));
        inner.append(h('table', { class: 't' }, ...r.items.map(x => h('tr', { class: 'row', onclick: () => { location.hash = `#/journey?qs=${x.c}:${x.qi}`; modal.remove(); } }, h('td', {}, `${x.c}:${x.qi}`), h('td', {}, x.question), h('td', {}, x.gold), h('td', {}, x.reason)))));
      }
      fill();
    }
    async function drawLens() {
      const L = await api('lens');
      lensBox.innerHTML = '';
      lensBox.append(h('h3', {}, 'Temporal lens: what the memories did with relative time words'));
      if (!L.available) { lensBox.append(h('div', { class: 'note' }, 'This run has no add-stage logs, so the memories cannot be compared with the turns they came from.')); return; }
      lensBox.append(h('div', { class: 'note' }, 'For evidence turns that contain a relative time word (yesterday, last week, … ago), one count per speaker store, judged on the memory created in that batch. Rules and limits: About page.'));
      const tot = Object.values(L.counts).reduce((a, b) => a + b, 0) || 1;
      lensBox.append(h('div', { class: 'fbar', style: 'height:26px;display:flex;margin:8px 0' }, ...Object.entries(L.counts).filter(([, v]) => v).map(([k2, v]) => h('div', { style: `width:${100 * v / tot}%;background:var(${COL[k2]})`, title: `${LABELS[k2]}: ${v}` }))));
      const tb = h('table', { class: 't' });
      for (const [k2, v] of Object.entries(L.counts)) {
        const tr = h('tr', { class: 'row' }, h('td', {}, h('i', { style: `display:inline-block;width:10px;height:10px;background:var(${COL[k2]});margin-right:6px` }), LABELS[k2]), h('td', {}, v), h('td', { class: 'note' }, fmtPct(v, tot)));
        tr.addEventListener('click', () => {
          const ex = L.examples[k2]; if (!ex.length) return;
          const modal = h('div', { class: 'modal', onclick: e => { if (e.target === modal) modal.remove(); } });
          modal.append(h('div', {}, h('b', {}, LABELS[k2]), h('button', { class: 'btn small', style: 'margin-left:10px', onclick: () => modal.remove() }, 'close'),
            ...ex.map(x => h('div', { class: 'card', style: 'margin:6px 0' }, h('div', { class: 'note' }, `${x.user} · ${x.dia} · session ${x.session} · words: ${x.words.join(', ')}`), h('div', {}, 'turn: ', x.turn), x.memory ? h('div', {}, 'memory: ', x.memory) : null,
              h('a', { href: `#/dataset?conv=${x.c}&dia=${x.dia}` }, 'dataset'), ' · ', h('a', { href: `#/add?conv=${x.c}&user=${x.user}&si=${(+x.dia.slice(1).split(':')[0]) - 1}&bi=0` }, 'add stage')))));
          document.body.append(modal);
        });
        tb.append(tr);
      }
      lensBox.append(tb);
    }
    const all = () => Promise.all([drawTop(), drawFunnel(), drawLens()]);
    await all();
    ctx.every(25000, all);
  },
};
