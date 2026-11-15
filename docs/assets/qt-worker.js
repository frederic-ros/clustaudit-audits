/* Web Worker of the quick test: runs Pyodide and the user's code off the page's thread,
   so that a slow or looping method can be stopped (the page terminates the worker). */
let py = null;

const HARNESS = `
import json, time, inspect, traceback
import numpy as np
from sklearn.metrics import adjusted_rand_score

def _labels(out, n):
    if isinstance(out, tuple):
        raise ValueError("returned a tuple; return the labels only")
    a = np.asarray(out)
    if a.ndim == 2 and 1 in a.shape:
        a = a.reshape(-1)
    if a.ndim != 1 or len(a) != n:
        raise ValueError(f"expected {n} labels, got an array of shape {a.shape}")
    if a.dtype.kind == "b" or a.dtype.kind not in "iuf":
        raise ValueError(f"labels must be integers, got dtype {a.dtype}")
    if a.dtype.kind == "f" and (not np.all(np.isfinite(a)) or not np.all(a == np.round(a))):
        raise ValueError("labels must be integers (got non-integer or non-finite values)")
    a = a.astype(int)
    if a.min(initial=0) < -1:
        raise ValueError("labels must be >= -1 (-1 marks an unassigned point)")
    return a

def _where(e):
    tb = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == "my_method.py"]
    return f" (line {tb[-1].lineno})" if tb else ""

def quicktest(code, data_json, needs_k):
    data = json.loads(data_json)
    res = {"checks": [], "panels": []}
    add = lambda key, label, ok, detail="", blocking=True: res["checks"].append(
        {"key": key, "label": label, "ok": bool(ok), "blocking": blocking, "detail": str(detail)[:300]})
    ns = {"__name__": "my_method"}
    try:
        exec(compile(code, "my_method.py", "exec"), ns)
        fn = ns.get("cluster")
        if not callable(fn):
            raise AttributeError("the code must define a function cluster(X, seed, n_clusters=None)")
        add("imports", "Imports and runs", True)
    except Exception as e:
        add("imports", "Imports and runs", False, f"{type(e).__name__}: {e}{_where(e)}")
        return json.dumps(res)
    try:
        sig = inspect.signature(fn)
        sig.bind(np.zeros((2, 2)), 0, n_clusters=2) if needs_k else sig.bind(np.zeros((2, 2)), 0)
    except TypeError as e:
        how = "cluster(X, seed, n_clusters=K)" if needs_k else "cluster(X, seed)"
        add("signature", "Signature", False, f"the audit calls {how}: {e}")
        return json.dumps(res)
    except ValueError:
        pass
    K, seed, first, times = data["n_clusters"], data["seed"], None, []
    for ds in data["datasets"]:
        X = np.asarray(ds["X"], float); y = np.asarray(ds["y"], int)
        t0 = time.perf_counter()
        try:
            lab = _labels(fn(X, seed, n_clusters=K) if needs_k else fn(X, seed), len(X))
        except Exception as e:
            add("labels", "One integer label per point", False, f"{ds['name']}: {type(e).__name__}: {e}{_where(e)}")
            return json.dumps(res)
        times.append(time.perf_counter() - t0)
        if first is None:
            first = lab
        inl = y >= 0
        res["panels"].append({"id": ds["id"], "labels": lab.tolist(), "ari": float(adjusted_rand_score(y[inl], lab[inl])),
                              "n_found": int(len(np.unique(lab[lab >= 0]))), "rejected": float(np.mean(lab == -1)),
                              "seconds": times[-1]})
    nf = res['panels'][0]['n_found']
    add("labels", "One integer label per point", True, f"{nf} cluster{'' if nf == 1 else 's'} found on the separated dataset")
    ds = data["datasets"][0]
    X = np.asarray(ds["X"], float)
    again = _labels(fn(X, seed, n_clusters=K) if needs_k else fn(X, seed), len(X))
    same = bool(np.array_equal(again, first) or adjusted_rand_score(first, again) == 1.0)   # same partition, labels may be permuted
    add("deterministic", "Same result with the same seed", same,
        "" if same else "two runs with the same seed differ: use the seed argument for every random choice", blocking=False)
    worst = max(times)
    add("time", "Time per dataset within the limit", worst < 30,
        f"{worst * 1000:.0f} ms on {len(X)} points in 2-D here; the battery datasets are 1000 x 20")
    return json.dumps(res)
`;

self.onmessage = async (ev) => {
  const m = ev.data;
  try {
    if (!py) {
      self.postMessage({ type: 'progress', text: 'Downloading Python for the browser (Pyodide, about 30 MB the first time)…' });
      importScripts(m.indexURL + 'pyodide.js');
      py = await loadPyodide({ indexURL: m.indexURL });
      self.postMessage({ type: 'progress', text: 'Loading numpy, SciPy and scikit-learn…' });
      await py.loadPackage(['numpy', 'scipy', 'scikit-learn', 'micropip']);
      py.runPython(HARNESS);
    }
    const extra = (m.requirements || []).filter(r => !/^(numpy|scipy|scikit-learn|sklearn|pandas)\b/i.test(r));
    const missing = [];
    if (extra.length) {
      self.postMessage({ type: 'progress', text: 'Installing ' + extra.join(', ') + '…' });
      const micropip = py.pyimport('micropip');
      for (const r of extra) { try { await micropip.install(r); } catch (e) { missing.push(r); } }
    }
    self.postMessage({ type: 'progress', text: 'Running your method on the three datasets…' });
    const fn = py.globals.get('quicktest');
    const out = JSON.parse(fn(m.code, m.data, m.needsK));
    fn.destroy();
    out.missing = missing;
    self.postMessage({ type: 'result', data: out });
  } catch (e) {
    self.postMessage({ type: 'error', text: String(e && e.message || e) });
  }
};
