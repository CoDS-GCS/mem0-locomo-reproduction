/* P2 Add stage: one batch as a pipeline graph */
PAGES.add = {
  async render(el, p, ctx) {
    const S = { c: +(p.conv ?? 0), u: +(p.u ?? 0), si: p.si != null ? +p.si : 0, bi: p.bi != null ? +p.bi : 0, play: false, live: p.live === '1' };
    if (p.user) { const conv = META.convs.find(x => x.idx === S.c); S.u = p.user === `${conv.b}_${S.c}` ? 1 : 0; }
    const user = () => { const cv = META.convs.find(x => x.idx === S.c); return S.u ? `${cv.b}_${S.c}` : `${cv.a}_${S.c}`; };
    const bar = h('div', { class: 'bar' }), ticks = h('div', { class: 'ticks' }), info = h('div', { class: 'note' });
    const box = h('div', { class: 'canvas tall' }), det = h('div', { class: 'card detail' });
    el.append(bar, ticks, info, legend(), h('div', { class: 'split' }, box, det));
    renderDetail(det, null);
    let batches = [], timer = null, nSessions = 0;

    function controls() {
      bar.innerHTML = '';
      const cv = META.convs.find(x => x.idx === S.c); nSessions = cv.sessions;
      const sSel = h('select', { onchange: e => { S.si = +e.target.value; S.bi = 0; load(); } });
      for (let i = 0; i < nSessions; i++) sSel.append(h('option', { value: i, selected: i === S.si }, `session ${i + 1}`));
      const uSel = h('select', { onchange: e => { S.u = +e.target.value; load(); } }, h('option', { value: 0, selected: !S.u }, cv.a + `_${S.c}`), h('option', { value: 1, selected: !!S.u }, cv.b + `_${S.c}`));
      const slider = h('input', { type: 'range', class: 'slider', min: 0, max: Math.max(0, batches.length - 1), value: S.bi, oninput: e => { S.bi = +e.target.value; S.live = false; liveBtn.classList.remove('on'); load(); } });
      const playBtn = h('button', { class: 'btn', onclick: () => { S.play = !S.play; playBtn.textContent = S.play ? '⏸ pause' : '▶ play'; schedule(); } }, S.play ? '⏸ pause' : '▶ play');
      const liveBtn = h('button', { class: 'btn' + (S.live ? ' on' : ''), title: 'follow the newest batch as the experiment runs', onclick: () => { S.live = !S.live; liveBtn.classList.toggle('on', S.live); if (S.live) followLive(); } }, '● Live');
      bar.append(h('label', {}, 'conversation'), convSelect(S.c, v => { S.c = v; S.si = 0; S.bi = 0; load(); }), h('label', {}, 'speaker store'), uSel, h('label', {}, 'session'), sSel,
        h('label', {}, 'batch'), slider, h('span', {}, `${S.bi + 1} / ${batches.length}`), playBtn, liveBtn, fitButton(box));
    }
    async function load() {
      const r = await api('add/session', { conv: S.c, user: user(), si: S.si });
      batches = r.batches; if (S.bi >= batches.length) S.bi = Math.max(0, batches.length - 1);
      controls();
      ticks.innerHTML = '';
      batches.forEach((b, i) => ticks.append(h('div', { class: `tick ${b.status}${i === S.bi ? ' cur' : ''}`, title: `batch ${i + 1}: ${b.turns.join(', ')} · ${b.status}` + (b.add || b.upd || b.del ? ` · +${b.add} ~${b.upd} -${b.del}` : ''), onclick: () => { S.bi = i; S.live = false; load(); } })));
      const spec = await api('add/batch', { conv: S.c, user: user(), si: S.si, bi: S.bi });
      if (spec.error) { info.textContent = spec.error; return; }
      info.textContent = `${user()} · ${spec.meta.status} · batch ${spec.meta.seq + 1} of ${spec.meta.total} for this user` + (spec.meta.seconds != null ? ` · add() took ${spec.meta.seconds} s` : '') + (spec.meta.time ? ` · ${spec.meta.time}` : '');
      drawGraph(box, spec, { onSelect: (id, d) => renderDetail(det, d) });
      setParams({ conv: S.c, u: S.u, si: S.si, bi: S.bi, live: S.live ? 1 : null });
    }
    function schedule() {
      clearInterval(timer);
      if (S.play) timer = setInterval(async () => {
        if (S.bi + 1 < batches.length) S.bi++; else if (S.si + 1 < nSessions) { S.si++; S.bi = 0; } else { S.play = false; schedule(); return; }
        await load();
      }, 1600);
    }
    async function followLive() {
      const r = await api('add/live');
      const n = r.newest; if (!n) return;
      if (n.c !== S.c || n.user !== user() || n.si !== S.si || n.bi !== S.bi) { S.c = n.c; S.u = n.user === `${META.convs[n.c].b}_${n.c}` ? 1 : 0; S.si = n.si; S.bi = n.bi; }
      await load();
    }
    ctx.onLeave(() => clearInterval(timer));
    ctx.every(25000, () => { if (S.live) followLive(); else load(); });
    if (S.live) await followLive(); else await load();
  },
};
