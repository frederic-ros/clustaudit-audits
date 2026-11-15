/* clustaudit audits: shared helpers, charts, home page and audit page.
   Every string that comes from an audit file is inserted with textContent. */
(function () {
  'use strict';
  const SVGNS = 'http://www.w3.org/2000/svg';
  const C = { c1: '#2853C7', c2: '#C2660E', c3: '#00897B', c4: '#9B4DCA', ref: '#8A93A6', grid: '#E1E5EC', axis: '#C9D0DB' };
  const ID_RE = /^[a-z0-9][a-z0-9-]{0,60}$/;

  function el(tag, attrs, ...kids) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') n.className = v; else if (k === 'text') n.textContent = v;
      else if (k.startsWith('on')) n.addEventListener(k.slice(2), v); else n.setAttribute(k, v === true ? '' : v);
    }
    for (const k of kids.flat()) if (k !== null && k !== undefined) n.append(k.nodeType ? k : document.createTextNode(String(k)));
    return n;
  }
  function sv(tag, attrs, ...kids) {
    const n = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) n.setAttribute(k, v);
    for (const k of kids.flat()) if (k) n.append(k.nodeType ? k : document.createTextNode(String(k)));
    return n;
  }
  const f2 = v => (v === null || v === undefined || Number.isNaN(v)) ? '--' : (Math.abs(v) < 0.005 ? 0 : v).toFixed(2);
  const g = v => (typeof v === 'number') ? String(+v.toFixed(4)) : String(v);
  async function getJSON(url) {
    const r = await fetch(url, { cache: 'no-cache' });
    if (!r.ok) throw new Error(url + ': HTTP ' + r.status);
    return r.json();
  }
  async function config() {
    let cfg = { repo: 'frederic-ros/clustaudit-audits', pyodide_index: 'https://cdn.jsdelivr.net/pyodide/v0.29.5/full/' };
    try { Object.assign(cfg, await getJSON('config.json')); } catch (e) { /* defaults */ }
    const h = location.hostname, seg = location.pathname.split('/').filter(Boolean)[0];
    if (h.endsWith('.github.io') && seg && !seg.endsWith('.html')) cfg.repo = h.split('.')[0] + '/' + seg;
    return cfg;
  }
  const modeChip = (mode, frac) => {
    const map = { silent: ['silent', 'Fails silently'], detectable: ['detectable', 'Fails detectably'], ok: ['ok', 'Holds at σ max'], error: ['error', 'Errors'] };
    const [cls, txt] = map[mode] || ['neutral', mode];
    return el('span', { class: 'chip ' + cls, title: frac !== undefined ? `at the largest overlap: ${Math.round(frac * 100)}% of the runs` : null, text: txt });
  };
  const lineKey = (color, dash) => sv('svg', { viewBox: '0 0 22 10', 'aria-hidden': 'true' },
    sv('line', { x1: 1, y1: 5, x2: 21, y2: 5, stroke: color, 'stroke-width': 2.5, 'stroke-dasharray': dash || null, 'stroke-linecap': 'round' }));
  function legend(series) {
    return el('div', { class: 'legend' }, series.map(s => el('span', {}, lineKey(s.color, s.dash), s.name)));
  }

  /* ------------------------------------------------------------ line chart with crosshair tooltip */
  function lineChart(o) {
    const W = o.width || 360, H = o.height || 220, m = { l: 34, r: 14, t: 12, b: o.xTitle ? 44 : 30 };
    const n = o.x.length, iw = W - m.l - m.r, ih = H - m.t - m.b;
    const yMin = o.yMin ?? 0, yMax = o.yMax ?? 1;
    const X = i => m.l + (n === 1 ? iw / 2 : i * iw / (n - 1));
    const Y = v => m.t + ih - (Math.max(yMin, Math.min(yMax, v)) - yMin) / (yMax - yMin) * ih;
    const wrap = el('div', { class: 'chart' });
    const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.aria || '', tabindex: 0 });
    const ticks = o.yTicks || [0, 0.5, 1];
    for (const t of ticks) {
      svg.append(sv('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), stroke: t === yMin ? C.axis : C.grid, 'stroke-width': 1 }));
      svg.append(sv('text', { x: m.l - 8, y: Y(t) + 4, 'text-anchor': 'end', class: 'lbl' }, String(t)));
    }
    const every = n > 7 ? 2 : 1;
    o.x.forEach((v, i) => { if (i % every === 0 || i === n - 1) svg.append(sv('text', { x: X(i), y: H - m.b + 18, 'text-anchor': 'middle', class: 'lbl' }, o.xFmt ? o.xFmt(v) : g(v))); });
    if (o.xTitle) svg.append(sv('text', { x: m.l + iw / 2, y: H - 6, 'text-anchor': 'middle', class: 'lbl' }, o.xTitle));
    if (o.band) {
      const up = o.band.hi.map((v, i) => `${X(i)},${Y(v)}`), dn = o.band.lo.map((v, i) => `${X(i)},${Y(v)}`).reverse();
      svg.append(sv('polygon', { points: up.concat(dn).join(' '), fill: o.band.color || C.c1, opacity: 0.12 }));
    }
    if (o.marker !== undefined && o.marker !== null) {
      svg.append(sv('line', { x1: X(o.marker), x2: X(o.marker), y1: m.t, y2: m.t + ih, stroke: C.axis, 'stroke-width': 1 }));
    }
    for (const s of o.series) {
      const pts = s.values.map((v, i) => (v === null || v === undefined) ? null : [X(i), Y(v)]).filter(Boolean);
      svg.append(sv('polyline', { points: pts.map(p => p.join(',')).join(' '), fill: 'none', stroke: s.color, 'stroke-width': s.width || 2,
        'stroke-dasharray': s.dash || null, 'stroke-linejoin': 'round', 'stroke-linecap': 'round' }));
      if (!s.noDots) for (const p of pts) svg.append(sv('circle', { cx: p[0], cy: p[1], r: 3.5, fill: s.hollow ? '#fff' : s.color, stroke: s.hollow ? s.color : '#fff', 'stroke-width': 2 }));
    }
    const cross = sv('line', { y1: m.t, y2: m.t + ih, stroke: '#14171F', 'stroke-width': 1, opacity: 0, 'pointer-events': 'none' });
    svg.append(cross);
    const hit = sv('rect', { x: m.l - 10, y: 0, width: iw + 20, height: H, fill: 'transparent' });
    svg.append(hit);
    const tip = el('div', { class: 'tip', role: 'status' });
    wrap.append(svg, tip);
    let cur = -1;
    function show(i) {
      cur = Math.max(0, Math.min(n - 1, i));
      cross.setAttribute('x1', X(cur)); cross.setAttribute('x2', X(cur)); cross.setAttribute('opacity', 0.35);
      tip.replaceChildren(el('div', { class: 'h', text: (o.xName ? o.xName + ' = ' : '') + (o.xFmt ? o.xFmt(o.x[cur]) : g(o.x[cur])) }),
        ...o.series.map(s => el('div', { class: 'r' }, lineKey(s.color, s.dash), el('b', { text: s.fmt ? s.fmt(s.values[cur], cur) : f2(s.values[cur]) }), el('span', { class: 'n', text: s.name }))));
      tip.style.display = 'block';
      const box = svg.getBoundingClientRect(), sx = box.width / W;
      const left = X(cur) * sx + 12, tw = tip.offsetWidth;
      const pos = left + tw > box.width ? X(cur) * sx - tw - 12 : left;
      tip.style.left = Math.max(0, Math.min(pos, box.width - tw)) + 'px';
      tip.style.top = '8px';
    }
    function hide() { cross.setAttribute('opacity', 0); tip.style.display = 'none'; }
    svg.addEventListener('pointermove', e => {
      const box = svg.getBoundingClientRect(), x = (e.clientX - box.left) * W / box.width;
      show(Math.round((x - m.l) / (n === 1 ? 1 : iw / (n - 1))));
    });
    svg.addEventListener('pointerleave', hide);
    svg.addEventListener('focus', () => show(cur < 0 ? 0 : cur));
    svg.addEventListener('blur', hide);
    svg.addEventListener('keydown', e => {
      if (e.key === 'ArrowRight') { show(cur + 1); e.preventDefault(); }
      if (e.key === 'ArrowLeft') { show(cur - 1); e.preventDefault(); }
    });
    return wrap;
  }

  function sparkline(values) {
    const n = values.length, X = i => 8 + i * (184 / (n - 1)), Y = v => 48 - Math.max(0, Math.min(1, v)) * 40;
    return sv('svg', { class: 'spark', viewBox: '0 0 200 56', role: 'img', preserveAspectRatio: 'none',
      'aria-label': `Inlier ARI from ${f2(values[0])} at the smallest overlap to ${f2(values[n - 1])} at the largest` },
      sv('line', { x1: 8, x2: 192, y1: Y(0.5), y2: Y(0.5), stroke: C.grid }),
      sv('polyline', { points: values.map((v, i) => `${X(i)},${Y(v)}`).join(' '), fill: 'none', stroke: C.c1, 'stroke-width': 2.5, 'stroke-linejoin': 'round', 'vector-effect': 'non-scaling-stroke' }));
  }

  function scatter(o) {
    /* o: points [[x, y, k]], colors[k], xDomain, yDomain, size, aria, tipFmt */
    const W = o.width || 220, H = o.height || 220, pad = o.pad ?? 10;
    const [x0, x1] = o.xDomain, [y0, y1] = o.yDomain;
    const m = o.margins || { l: pad, r: pad, t: pad, b: pad };
    const X = v => m.l + (v - x0) / (x1 - x0 || 1) * (W - m.l - m.r), Y = v => H - m.b - (v - y0) / (y1 - y0 || 1) * (H - m.t - m.b);
    const wrap = el('div', { class: 'chart' });
    const svg = sv('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': o.aria || '' });
    if (o.decorate) o.decorate(svg, X, Y, W, H, m);
    for (const p of o.points) svg.append(sv('circle', { cx: X(p[0]), cy: Y(p[1]), r: o.r || 3.4, fill: o.colors[p[2]] || '#9AA3B2', 'fill-opacity': 0.9, stroke: '#fff', 'stroke-width': o.ring ?? 0.8 }));
    wrap.append(svg);
    if (o.tipFmt) {
      const tip = el('div', { class: 'tip' }); wrap.append(tip);
      const ring = sv('circle', { r: 6, fill: 'none', stroke: '#14171F', 'stroke-width': 1.5, opacity: 0 }); svg.append(ring);
      svg.addEventListener('pointermove', e => {
        const box = svg.getBoundingClientRect(), sx = W / box.width, px = (e.clientX - box.left) * sx, py = (e.clientY - box.top) * sx;
        let best = -1, bd = 24 * 24 * sx * sx;
        o.points.forEach((p, i) => { const d = (X(p[0]) - px) ** 2 + (Y(p[1]) - py) ** 2; if (d < bd) { bd = d; best = i; } });
        if (best < 0) { tip.style.display = 'none'; ring.setAttribute('opacity', 0); return; }
        const p = o.points[best];
        ring.setAttribute('cx', X(p[0])); ring.setAttribute('cy', Y(p[1])); ring.setAttribute('opacity', 1);
        tip.replaceChildren(...o.tipFmt(p)); tip.style.display = 'block';
        const left = X(p[0]) / sx + 12;
        const pos = left + tip.offsetWidth > box.width ? X(p[0]) / sx - tip.offsetWidth - 12 : left;
        tip.style.left = Math.max(0, Math.min(pos, box.width - tip.offsetWidth)) + 'px';
        tip.style.top = Math.max(0, Y(p[1]) / sx - 20) + 'px';
      });
      svg.addEventListener('pointerleave', () => { tip.style.display = 'none'; ring.setAttribute('opacity', 0); });
    }
    return wrap;
  }

  function table(head, rows, numCols) {
    return el('table', { class: 'data' }, el('thead', {}, el('tr', {}, head.map(h => el('th', { scope: 'col', text: h })))),
      el('tbody', {}, rows.map(r => el('tr', {}, r.map((c, i) => el('td', { class: (numCols || []).includes(i) ? 'num' : null, text: c }))))));
  }

  /* ------------------------------------------------------------ home page */
  async function home() {
    let idx;
    try { idx = await getJSON('audits/index.json'); } catch (e) {
      document.getElementById('gallery-ref').replaceChildren(el('p', { class: 'empty', text: 'The audit index could not be loaded (' + e.message + ').' }));
      return;
    }
    const by = Object.fromEntries(idx.audits.map(a => [a.id, a]));
    const hero = document.getElementById('hero-chart');
    if (hero && by.kmeans && by.hdbscan) {
      const s = [{ name: 'K-Means', values: by.kmeans.eta_int.ari, color: C.c1 },
                 { name: 'HDBSCAN', values: by.hdbscan.eta_int.ari, color: C.c2, dash: '7 5', hollow: true }];
      hero.replaceChildren(legend(s), lineChart({
        x: by.kmeans.eta_int.values, series: s, width: 520, height: 250, xName: 'share of the noise between clusters',
        xFmt: v => v === 0 ? 'all distant' : v === 1 ? 'all between' : Math.round(v * 100) + '%',
        aria: `As the noise moves from distant outliers to points between clusters, K-Means rises from ${f2(s[0].values[0])} to ${f2(s[0].values.at(-1))} while HDBSCAN falls from ${f2(s[1].values[0])} to ${f2(s[1].values.at(-1))}`
      }));
    }
    const fams = ['All', 'Centroid', 'Connectivity', 'Density', 'Graph', 'Deep', 'Other'].filter(f => f === 'All' || idx.audits.some(a => a.family === f));
    const filt = document.getElementById('family-filter');
    let current = 'All';
    const render = () => {
      for (const [hostId, ref] of [['gallery-ref', true], ['gallery-sub', false]]) {
        const host = document.getElementById(hostId);
        const list = idx.audits.filter(a => a.reference === ref && (current === 'All' || a.family === current));
        host.replaceChildren(...(list.length ? list.map(card) : [el('p', { class: 'empty', text: ref ? 'No reference audit in this family.' : 'No submitted audit yet. Test your method and launch the first one.' })]));
      }
    };
    filt.replaceChildren(...fams.map(f => el('button', { type: 'button', 'aria-pressed': String(f === current), text: f, onclick: () => {
      current = f; filt.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.textContent === f))); render();
    } })));
    render();
  }

  function card(a) {
    return el('article', { class: 'card mcard' },
      el('div', { class: 'top' }, el('h3', { text: a.name }), el('span', { class: 'tiny', text: a.family })),
      el('div', { class: 'stack', style: 'gap:4px' }, sparkline(a.overlap.ari), el('span', { class: 'tiny', text: `Inlier ARI as overlap grows, σ from ${g(a.overlap.values[0])} to ${g(a.overlap.values.at(-1))}` })),
      el('dl', { class: 'kv' },
        el('dt', { text: 'Overlap: breaks at' }), el('dd', { text: 'σ ' + critShort(a.sigma) }),
        el('dt', { text: 'Elongation: breaks at' }), el('dd', { text: 'α ' + critShort(a.alpha) }),
        el('dt', { text: 'Smallest cluster, ρ = 5' }), el('dd', { text: 'F1 = ' + f2(a.f1) })),
      el('div', { class: 'bottom' }, modeChip(a.failure, a.failure_fraction),
        el('a', { href: 'audit.html?id=' + encodeURIComponent(a.id), text: 'Open audit →', 'aria-label': 'Open the audit of ' + a.name })));
  }
  function critShort(t) {
    const s = String(t).split(' ')[0];
    if (s.startsWith('≤')) return '≤ ' + s.slice(1);
    if (s === '>max') return 'beyond the grid';
    return '= ' + s;
  }

  /* ------------------------------------------------------------ audit page */
  async function auditPage() {
    const main = document.getElementById('audit');
    const id = new URLSearchParams(location.search).get('id') || location.hash.slice(1) || 'hdbscan';   // ?id= on the site, #id where query strings are not passed
    if (!ID_RE.test(id)) { main.replaceChildren(el('p', { class: 'empty', text: 'Unknown audit.' })); return; }
    let a, idx;
    try { [a, idx] = await Promise.all([getJSON(`audits/${id}.json`), getJSON('audits/index.json')]); }
    catch (e) { main.replaceChildren(el('p', { class: 'empty', text: `No audit "${id}" on this site.` })); return; }
    const cfg = await config();
    document.title = `${a.method.name} · clustaudit audit card`;
    const sw = a.sweeps, cd = a.card;
    const refs = idx.audits.filter(x => x.reference);
    const pool = sw.overlap.values.map((_, i) => Math.max(...refs.map(r => r.overlap.ari[i] ?? 0)));
    const site = location.origin + location.pathname.replace(/audit\.html$/, '');

    // header
    const isRef = a.method.reference_audit;
    const head = el('div', { class: 'audit-head' },
      el('div', { class: 'stack' },
        el('p', { class: 'crumbs' }, el('a', { href: 'index.html#gallery', text: 'Audits' }), ' / ', a.method.name),
        el('div', { class: 'row' }, el('h1', { text: a.method.name }),
          el('span', { class: 'chip ' + (isRef ? 'detectable' : 'ok'), text: isRef ? 'Reference audit' : 'Submitted audit' }),
          el('span', { class: 'chip neutral', text: a.method.family + ' family' })),
        el('p', { class: 'muted small', text: `Battery ${a.battery.name} (${a.battery.n_datasets} datasets) · ${a.method.needs_k ? 'protocol F: the true K is given' : 'the method chooses K itself'} · five seeds per condition · scored with clustaudit ${a.scoring.clustaudit} · ${a.created.slice(0, 10)}` }),
        a.issue ? el('p', { class: 'tiny' }, 'Submitted in ', el('a', { href: `https://github.com/${cfg.repo}/issues/${a.issue}`, text: 'issue #' + a.issue })) : null,
        a.method.reference_url ? el('p', { class: 'tiny', text: a.method.reference_url }) : null),
      el('div', { class: 'row' },
        el('a', { class: 'btn btn-ghost', href: `audits/${id}.json`, download: `${id}.audit.json`, text: 'Download audit.json' }),
        el('a', { class: 'btn btn-ghost', href: `methods/${id}.py`, text: 'Method code' }),
        el('a', { class: 'btn btn-ghost', href: '#cite-audit', text: 'Cite' })));

    const tiles = el('div', { class: 'tiles' }, cd.tiles.map(t => el('div', { class: 'card tile' },
      el('span', { class: 'k', text: t.k }), el('span', { class: 'v', text: t.v }), el('span', { class: 'd', text: t.d }))));

    // compare selector + the three charts of the card
    const cmpSel = el('select', { class: 'ctl', id: 'cmp', 'aria-label': 'Compare with another audit' },
      el('option', { value: '', text: 'Compare with…' }),
      idx.audits.filter(x => x.id !== id).map(x => el('option', { value: x.id, text: x.name + (x.reference ? '' : ' (submitted)') })));
    const charts = el('div', { class: 'charts3' });
    const cache = {};
    async function drawCharts(cmpId) {
      let other = null;
      if (cmpId) { try { other = cache[cmpId] || (cache[cmpId] = await getJSON(`audits/${cmpId}.json`)); } catch (e) { other = null; } }
      const me = a.method.name;
      const ov = [{ name: me + ' · ARI', values: sw.overlap.ari_mean, color: C.c1 },
                  { name: me + ' · smallest-cluster F1', values: sw.overlap.f1_mean, color: C.c1, dash: '6 4', hollow: true }];
      if (other) ov.push({ name: other.method.name + ' · ARI', values: other.sweeps.overlap.ari_mean, color: C.c2 });
      else ov.push({ name: 'best reference method · ARI', values: pool, color: C.ref, dash: '2 4', noDots: true });
      const etaOther = other || (id !== 'kmeans' ? cache.kmeans || (cache.kmeans = await getJSON('audits/kmeans.json').catch(() => null)) : (cache.hdbscan || (cache.hdbscan = await getJSON('audits/hdbscan.json').catch(() => null))));
      const eta = [{ name: me, values: sw.eta_int.ari_mean, color: C.c1 }];
      if (etaOther) eta.push({ name: etaOther.method.name + (other ? '' : ', for comparison'), values: etaOther.sweeps.eta_int.ari_mean, color: C.c2, dash: '7 5', hollow: true });
      const im = [{ name: me + ' · ARI', values: sw.imbalance.ari_mean, color: C.c1 },
                  { name: me + ' · smallest-cluster F1', values: sw.imbalance.f1_mean, color: C.c1, dash: '6 4', hollow: true }];
      if (other) im.push({ name: other.method.name + ' · smallest-cluster F1', values: other.sweeps.imbalance.f1_mean, color: C.c2, dash: '6 4', hollow: true });
      const box = (title, sub, series, o) => el('div', { class: 'card chart-card' }, el('h3', { text: title }), el('p', { class: 'tiny', text: sub }), legend(series), lineChart(Object.assign({ series }, o)));
      charts.replaceChildren(
        box('Overlap', 'Mean over five seeds; the 0.5 line is the breaking threshold.', ov, { x: sw.overlap.values, xName: 'σ', xTitle: 'cluster spread σ', aria: `Overlap sweep of ${me}: ARI ${sw.overlap.ari_mean.map(f2).join(', ')}` }),
        box('Noise placement, η = 0.3', 'From all-distant noise (left) to all of it between clusters (right).', eta, { x: sw.eta_int.values, xName: 'share between clusters', xTitle: 'share of the noise between clusters', xFmt: v => Math.round(v * 100) + '%', aria: `Noise placement sweep of ${me}: ARI ${sw.eta_int.ari_mean.map(f2).join(', ')}` }),
        box('Size imbalance', 'The aggregate ARI and the smallest cluster can diverge.', im, { x: sw.imbalance.values, xName: 'ρ', xTitle: 'size ratio ρ', aria: `Imbalance sweep of ${me}: ARI ${sw.imbalance.ari_mean.map(f2).join(', ')}, smallest-cluster F1 ${sw.imbalance.f1_mean.map(f2).join(', ')}` }));
    }
    cmpSel.addEventListener('change', () => drawCharts(cmpSel.value));
    await drawCharts('');

    const reading = el('section', { class: 'card reading', 'aria-labelledby': 'h-read' }, el('h2', { id: 'h-read', style: 'font-size:24px', text: 'What the audit says' }),
      el('ul', {}, cd.reading.map(r => el('li', { text: r }))));

    // every sweep, per-seed band
    const order = ['overlap', 'anisotropy', 'inter_density', 'intra_density', 'imbalance', 'eta_int'];
    const multiples = el('div', { class: 'charts3' }, order.map(k => {
      const s = sw[k], lo = s.ari_seeds.map(r => Math.min(...r)), hi = s.ari_seeds.map(r => Math.max(...r));
      const ci = typeof s.crit.mean === 'number' ? s.values.indexOf(s.crit.mean) : null;
      const series = [{ name: 'mean ARI', values: s.ari_mean, color: C.c1, fmt: (v, i) => `${f2(v)} (seeds ${f2(lo[i])}–${f2(hi[i])})` }];
      return el('div', { class: 'card chart-card' }, el('h3', { text: `${s.label} (${s.symbol})` }),
        el('p', { class: 'tiny', text: `Critical level ${s.crit.text}. Band: range over the five seeds.` }),
        lineChart({ x: s.values, series, band: { lo, hi }, marker: ci, xName: s.symbol, height: 190,
          xFmt: k === 'eta_int' ? (v => Math.round(v * 100) + '%') : null,
          aria: `${s.label}: mean ARI ${s.ari_mean.map(f2).join(', ')}; critical level ${s.crit.text}` }));
    }));

    // suite
    const su = a.suite, regC = [C.c1, C.c2, C.c3], regN = ['easy', 'medium', 'hard'];
    const xs = su.points.map(p => p[0]), xmax = Math.max(...xs) * 1.05;
    const suite = el('div', { class: 'card chart-card' },
      el('h3', { text: 'The 75-dataset suite' }),
      el('p', { class: 'tiny', text: `Mean ARI ${f2(su.ari_mean)}: easy ${f2(su.by_regime.easy)}, medium ${f2(su.by_regime.medium)}, hard ${f2(su.by_regime.hard)}. Spearman correlation between the difficulty D and the ARI: ${su.spearman_D_ARI === null ? 'n/a' : su.spearman_D_ARI.toFixed(2)}.` }),
      el('div', { class: 'legend' }, regN.map((r, i) => el('span', {}, sv('svg', { viewBox: '0 0 10 10', width: 10, height: 10, 'aria-hidden': 'true' }, sv('circle', { cx: 5, cy: 5, r: 4, fill: regC[i] })), r))),
      scatter({ points: su.points.map(p => [p[0], Math.max(-0.05, p[1]), p[2], p[1]]), colors: regC, xDomain: [0, xmax], yDomain: [-0.05, 1.05], width: 520, height: 230, r: 4.5, ring: 1.5,
        margins: { l: 34, r: 12, t: 10, b: 36 }, aria: `Suite: ARI against difficulty D for 75 datasets; mean ARI ${f2(su.ari_mean)}`,
        decorate: (svgN, X, Y, W, H, m) => {
          for (const t of [0, 0.5, 1]) { svgN.append(sv('line', { x1: m.l, x2: W - m.r, y1: Y(t), y2: Y(t), stroke: t ? C.grid : C.axis })); svgN.append(sv('text', { x: m.l - 8, y: Y(t) + 4, 'text-anchor': 'end', class: 'lbl' }, String(t))); }
          svgN.append(sv('text', { x: (m.l + W - m.r) / 2, y: H - 6, 'text-anchor': 'middle', class: 'lbl' }, 'difficulty D (clustaudit profile)'));
          svgN.append(sv('text', { x: m.l, y: H - 20, class: 'lbl' }, '0')); svgN.append(sv('text', { x: W - m.r, y: H - 20, 'text-anchor': 'end', class: 'lbl' }, xmax.toFixed(2)));
        },
        tipFmt: p => [el('div', { class: 'h', text: regN[p[2]] + ' regime' }), el('div', { class: 'r' }, el('b', { text: f2(p[3]) }), el('span', { class: 'n', text: 'ARI' })), el('div', { class: 'r' }, el('b', { text: p[0].toFixed(3) }), el('span', { class: 'n', text: 'D' }))] }));

    // numbers
    const head8 = ['σ_crit [seed range]', 'α_crit [seed range]', 'δ_crit [seed range]', 'noise: distant / bridge', 'ρ = 5: ARI / F1 min', 'failure at σ max'];
    const numbers = el('details', {}, el('summary', { text: 'The numbers (Table 8 format and every sweep level)' }), el('div', { class: 'stack' },
      table(head8, [cd.row]),
      ...order.map(k => { const s = sw[k]; return el('div', { class: 'stack', style: 'gap:6px;margin-top:10px' }, el('strong', { text: `${s.label} (${s.symbol}): ${s.what}` }),
        table(['level', 'mean ARI', 'per seed', 'smallest-cluster F1', 'ok', 'silent', 'detectable', 'error'],
          s.values.map((v, i) => [g(v), f2(s.ari_mean[i]), s.ari_seeds[i].map(f2).join(' · '), f2(s.f1_mean[i]), ...['ok', 'silent', 'declared', 'error'].map(mm => Math.round(s.modes[mm][i] * 100) + '%')]), [1, 3, 4, 5, 6, 7])); })));
    const cols = a.rows.columns;
    const runs = el('details', {}, el('summary', { text: `All ${a.counts.runs} runs (${a.counts.ok} ok, ${a.counts.silent} silent, ${a.counts.declared} detectable, ${a.counts.error} errors)` }),
      el('div', {}, table(['dataset', 'ARI', 'F1 min', 'mode', 'clusters', 'rejected', 'seconds', 'message'],
        a.rows.data.map(r => { const o = Object.fromEntries(cols.map((c, i) => [c, r[i]])); return [o.id, f2(o.ARI), f2(o.F1), o.mode === 'declared' ? 'detectable' : o.mode, o.n_found ?? '', o.rejected === null ? '' : Math.round(o.rejected * 100) + '%', o.seconds === null ? '' : o.seconds.toFixed(2), o.message || '']; }), [1, 2, 4, 5, 6])));

    // badge and citation
    const md = `[![audited by clustaudit](${site}badge/${id}.svg)](${site}audit.html?id=${id})`;
    const code = el('code', { text: md });
    const copyBtn = el('button', { class: 'btn btn-ghost', type: 'button', text: 'Copy', onclick: async () => { try { await navigator.clipboard.writeText(md); copyBtn.textContent = 'Copied'; } catch (e) { copyBtn.textContent = 'Select and copy'; } } });
    const badge = el('div', { class: 'card reading' }, el('h2', { style: 'font-size:22px', text: 'Badge for your README' }),
      el('img', { src: `badge/${id}.svg`, alt: `clustaudit badge for ${a.method.name}`, style: 'height:20px;align-self:flex-start' }),
      el('div', { class: 'snippet' }, code, copyBtn));
    const cite = el('div', { class: 'card reading', id: 'cite-audit' }, el('h2', { style: 'font-size:22px', text: 'Cite this audit' }),
      el('p', {}, 'F. Ros, R. Riad, Y. Nasser. ', el('em', { text: 'Interventional Auditing of Clustering Algorithms: Controlled Difficulty Sweeps Beyond Benchmarking' }), ' (submitted).'),
      el('p', {}, `Audit card "${a.method.name}", battery ${a.battery.name}, scored with clustaudit ${a.scoring.clustaudit}, `,
        el('a', { href: 'https://doi.org/' + a.scoring.software_doi, text: 'doi:' + a.scoring.software_doi }), `, ${a.created.slice(0, 10)}. `, el('a', { href: `${site}audit.html?id=${id}`, text: `${site}audit.html?id=${id}` })),
      el('p', { class: 'tiny', text: `Battery manifest SHA-256 ${a.battery.manifest_sha256.slice(0, 16)}…; method file SHA-256 ${a.method.source_sha256.slice(0, 16)}…` }));

    main.replaceChildren(head,
      el('div', { class: 'stack', style: 'gap:16px;margin-top:28px' }, tiles),
      el('div', { class: 'row', style: 'justify-content:space-between;margin-top:32px' }, el('h2', { style: 'font-size:26px', text: 'Three sweeps behind the card' }), cmpSel),
      el('div', { style: 'margin-top:14px' }, charts),
      el('div', { style: 'margin-top:20px' }, reading),
      el('h2', { style: 'font-size:26px;margin-top:40px', text: 'Every sweep' }),
      el('p', { class: 'muted small', style: 'margin:6px 0 14px', text: 'Mean inlier ARI over five seeds, with the range over seeds; the vertical line marks the critical level.' }),
      multiples,
      el('div', { class: 'grid2', style: 'margin-top:16px' }, suite, el('div', { class: 'stack' }, badge, cite)),
      el('div', { class: 'stack', style: 'margin-top:16px' }, numbers, runs));
  }

  window.CA = { el, sv, f2, g, getJSON, config, lineChart, scatter, legend, lineKey, table, C };
  document.addEventListener('DOMContentLoaded', () => {
    const p = document.body.dataset.page;
    if (p === 'home') home();
    if (p === 'audit') auditPage();
  });
})();
