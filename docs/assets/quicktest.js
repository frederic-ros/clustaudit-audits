/* Test-your-method page: code editor, in-browser quick test (Web Worker + Pyodide) and the
   prefilled GitHub issue that launches the full audit. */
(function () {
  'use strict';
  const EXAMPLES = {
    kmeans: { name: 'my-kmeans', needsK: true, family: 'Centroid', code:
`# requirements: numpy scikit-learn
def cluster(X, seed, n_clusters=None):
    """X: array (n, d). Return one integer label per row;
    -1 = point left unassigned. n_clusters is given when
    your method needs the number of clusters."""
    from sklearn.cluster import KMeans
    k = n_clusters or 5
    return KMeans(k, n_init=10, random_state=seed).fit_predict(X)
` },
    hdbscan: { name: 'my-hdbscan', needsK: false, family: 'Density', code:
`# requirements: scikit-learn
def cluster(X, seed, n_clusters=None):
    """Density-based: chooses the number of clusters itself and
    labels the points it rejects -1."""
    from sklearn.cluster import HDBSCAN
    return HDBSCAN(min_cluster_size=10, min_samples=5).fit_predict(X)
` },
    blank: { name: 'my-method', needsK: false, family: 'Other', code:
`# requirements: numpy
import numpy as np


def cluster(X, seed, n_clusters=None):
    """X: array (n, d) of floats. seed: use it for every random choice.
    n_clusters: the true number of clusters if your method needs it, else None.
    Return one integer label per row of X; -1 marks a point left unassigned."""
    rng = np.random.default_rng(seed)
    labels = np.zeros(len(X), dtype=int)
    # ... your method here ...
    return labels
` },
  };
  const TIMEOUT_MS = 120000;
  let worker = null, last = null, data = null, cfg = null;

  const $ = id => document.getElementById(id);
  const val = () => ({
    code: $('code').value, name: $('mname').value.trim() || 'my-method', family: $('mfam').value,
    needsK: document.querySelector('input[name="needk"]:checked').value === 'yes',
  });
  const reqs = code => {
    const m = code.match(/^\s*#\s*requirements\s*:\s*(.*)$/im);
    return m ? m[1].replace(/,/g, ' ').split(/\s+/).filter(Boolean) : [];
  };

  function setExample(k) {
    const e = EXAMPLES[k];
    $('code').value = e.code; $('mname').value = e.name; $('mfam').value = e.family;
    document.querySelector(`input[name="needk"][value="${e.needsK ? 'yes' : 'no'}"]`).checked = true;
  }

  function checkItem(c) {
    const { el, sv } = window.CA;
    const cls = c.ok ? '' : (c.blocking ? 'fail' : 'warn');
    const icon = c.ok
      ? sv('svg', { width: 18, height: 18, viewBox: '0 0 18 18', 'aria-hidden': 'true' }, sv('circle', { cx: 9, cy: 9, r: 9, fill: '#1D6B4F' }), sv('path', { d: 'M5 9.2l2.6 2.6L13 6.4', fill: 'none', stroke: '#fff', 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }))
      : sv('svg', { width: 18, height: 18, viewBox: '0 0 18 18', 'aria-hidden': 'true' }, sv('circle', { cx: 9, cy: 9, r: 9, fill: c.blocking ? '#8A3D00' : '#8A6A00' }), sv('path', { d: 'M9 4.5v6M9 13.2v.3', stroke: '#fff', 'stroke-width': 2, 'stroke-linecap': 'round' }));
    return el('li', { class: cls }, icon, el('span', {}, (c.ok ? '' : c.blocking ? 'Failed: ' : 'Warning: ') + c.label, c.detail ? el('small', { text: c.detail }) : null));
  }

  function panel(ds, p) {
    const { el, sv, scatter, f2 } = window.CA;
    const pal = ['#2853C7', '#C2660E', '#00897B', '#9B4DCA'];
    const sizes = {};
    p.labels.forEach(l => { if (l >= 0) sizes[l] = (sizes[l] || 0) + 1; });
    const rank = Object.keys(sizes).sort((a, b) => sizes[b] - sizes[a]);
    const colorOf = Object.fromEntries(rank.map((l, i) => [l, i < 4 ? i : 4]));
    const colors = pal.concat(['#C4CAD4']);
    const xs = ds.X.map(r => r[0]), ys = ds.X.map(r => r[1]);
    const lo = Math.min(...xs, ...ys), hi = Math.max(...xs, ...ys);
    const pts = ds.X.map((r, i) => [r[0], r[1], p.labels[i] >= 0 ? colorOf[p.labels[i]] : 9]);
    const fig = scatter({ points: pts.filter(q => q[2] !== 9), colors, xDomain: [lo, hi], yDomain: [lo, hi],
      aria: `${ds.name}: ${p.n_found} clusters found, ARI ${f2(p.ari)}`, ring: 0.8,
      decorate: (svgN, X, Y) => { pts.filter(q => q[2] === 9).forEach(q => svgN.append(sv('circle', { cx: X(q[0]), cy: Y(q[1]), r: 3.2, fill: 'none', stroke: '#8A93A6', 'stroke-width': 1.2 }))); } });
    const note = `${ds.what} ${p.n_found} cluster${p.n_found === 1 ? '' : 's'} found` + (p.rejected > 0 ? `, ${Math.round(p.rejected * 100)}% of the points left unassigned.` : '.');
    return el('figure', { class: 'panel' }, fig, el('figcaption', { class: 'stack', style: 'gap:4px' },
      el('div', { class: 'row', style: 'justify-content:space-between' }, el('span', { style: 'font-weight:600;font-size:15px', text: ds.name }), el('span', { class: 'mono small', text: 'ARI ' + f2(p.ari) })),
      el('span', { class: 'tiny', text: note })));
  }

  function narrative(res) {
    const [a, b, c] = res.panels;
    if (!a || !c) return '';
    if (c.ari < a.ari - 0.3) return `The third panel already shows something the audit measures: a few distant outliers change how the four real clusters are split (ARI ${a.ari.toFixed(2)} without them, ${c.ari.toFixed(2)} with them). The full audit says at which noise placement this starts, and for which other factors.`;
    if (b && b.ari < a.ari - 0.3) return `Overlap already costs your method here (ARI ${a.ari.toFixed(2)} on separated clusters, ${b.ari.toFixed(2)} with overlap). The full audit finds the level at which it breaks, seed by seed.`;
    if (a.ari < 0.5) return 'Your method does not recover four well-separated groups. Check the code (and whether it needs the number of clusters) before launching the full audit.';
    return 'Three small datasets are a smoke test, not an audit: the full battery varies one factor at a time on 250 datasets in 20 dimensions and reports where and how your method breaks.';
  }

  async function run() {
    const v = val();
    const { el } = window.CA;
    $('results').hidden = false; $('panels').replaceChildren(); $('checks').replaceChildren(); $('note').textContent = '';
    $('panel-legend').hidden = true; $('s2').textContent = 'Quick test: running…';
    $('run').disabled = true;
    try { data = data || await window.CA.getJSON('data/quicktest.json'); } catch (e) { fail('The quick-test datasets could not be loaded: ' + e.message); return; }
    if (!worker) worker = new Worker('assets/qt-worker.js');
    const timer = setTimeout(() => { worker.terminate(); worker = null; fail(`Stopped after ${TIMEOUT_MS / 1000} s: the method is too slow on 300 points (or loops).`); }, TIMEOUT_MS);
    worker.onmessage = ev => {
      const m = ev.data;
      if (m.type === 'progress') { $('progress').textContent = m.text; return; }
      clearTimeout(timer); $('run').disabled = false;
      if (m.type === 'error') { fail('The quick test could not run: ' + m.text + '. You can still run the pre-audit locally (python -m auditkit check my_method.py).'); return; }
      const res = m.data; last = { ...v, res };
      const passed = res.checks.every(c => c.ok || !c.blocking);
      $('s2').textContent = passed ? 'Quick test: passed' : 'Quick test: not passed';
      $('progress').textContent = res.missing && res.missing.length ? `Not installable in the browser: ${res.missing.join(', ')}. The full audit installs them with pip.` : '';
      $('panels').replaceChildren(...res.panels.map((p, i) => panel(data.datasets[i], p)));
      $('panel-legend').hidden = !res.panels.length;
      $('checks').replaceChildren(...res.checks.map(checkItem));
      $('note').textContent = passed ? narrative(res) : 'Fix the failed check, then run the quick test again.';
      updateLaunch();
    };
    worker.onerror = e => { clearTimeout(timer); worker = null; fail('The quick test stopped: ' + (e.message || 'worker error')); };
    worker.postMessage({ indexURL: cfg.pyodide_index, code: v.code, data: JSON.stringify(data), needsK: v.needsK, requirements: reqs(v.code) });
  }
  function fail(msg) {
    $('run').disabled = false; $('s2').textContent = 'Quick test: not run'; $('progress').textContent = msg;
  }

  function issueUrl(v) {
    const base = `https://github.com/${cfg.repo}/issues/new`;
    const p = new URLSearchParams({ template: 'audit.yml', title: 'Audit: ' + v.name, name: v.name, family: v.family,
      needs_k: v.needsK ? 'Yes, give it the true K (protocol F)' : 'No, it chooses K itself',
      requirements: reqs(v.code).join(' '), code: v.code });
    const full = base + '?' + p.toString();
    if (full.length <= 7500) return { url: full, long: false };
    p.delete('code');
    return { url: base + '?' + p.toString(), long: true };
  }

  function updateLaunch() {
    const ok = $('consent').checked;
    const v = val();
    const a = $('launch');
    if (ok && cfg) { a.href = issueUrl(v).url; a.setAttribute('aria-disabled', 'false'); }
    else { a.removeAttribute('href'); a.setAttribute('aria-disabled', 'true'); }
    const tested = last && last.code === v.code && last.needsK === v.needsK;
    const passed = tested && last.res.checks.every(c => c.ok || !c.blocking);
    $('launch-note').textContent = !ok ? 'Tick the box to continue.' : passed ? 'Quick test passed.' : tested ? 'The quick test did not pass: the audit will probably fail.' : 'Tip: run the quick test first.';
  }

  function launch(e) {
    // a real link (opened outside the page); a long code is copied for pasting into the issue
    if ($('launch').getAttribute('aria-disabled') === 'true') { e.preventDefault(); return; }
    const v = val();
    if (issueUrl(v).long) {
      if (navigator.clipboard) navigator.clipboard.writeText(v.code).catch(() => {});
      $('launch-note').textContent = 'Your code is long: it was copied to the clipboard. Paste it in the "Method code" field of the issue.';
    }
  }

  async function estimate() {
    try {
      const idx = await window.CA.getJSON('audits/index.json');
      const t = idx.audits.filter(a => a.reference && a.wall_time_s).map(a => a.wall_time_s).sort((a, b) => a - b);
      if (t.length) {
        const mx = t.at(-1);
        $('est').textContent = mx < 120 ? 'under 5 min' : `about ${Math.ceil(mx / 60) + 3} min`;
        $('est').title = `The nine reference methods take ${Math.round(t[0])} s to ${Math.round(mx)} s on 2 cores, plus about 2 minutes to set up the runner.`;
      }
    } catch (e) { /* keep the default */ }
  }

  document.addEventListener('DOMContentLoaded', async () => {
    if (document.body.dataset.page !== 'test') return;
    cfg = await window.CA.config();
    $('repo-slug').textContent = cfg.repo;
    setExample('kmeans');
    $('example').addEventListener('change', e => setExample(e.target.value));
    $('code').addEventListener('keydown', e => {
      // Tab indents; Escape then Tab leaves the editor (keyboard users are not trapped)
      if (e.key === 'Escape') { e.target.dataset.esc = '1'; return; }
      if (e.key === 'Tab' && !e.shiftKey && !e.target.dataset.esc) { e.preventDefault(); const t = e.target, s = t.selectionStart; t.setRangeText('    ', s, t.selectionEnd, 'end'); }
      delete e.target.dataset.esc;
    });
    $('run').addEventListener('click', run);
    $('consent').addEventListener('change', updateLaunch);
    ['code', 'mname'].forEach(i => $(i).addEventListener('input', updateLaunch));
    document.querySelectorAll('input[name="needk"]').forEach(r => r.addEventListener('change', updateLaunch));
    $('launch').addEventListener('click', launch);
    updateLaunch(); estimate();
  });
})();
