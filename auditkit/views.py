"""
Views of the battery
====================

To show what the difficulty tests look like, each sweep dataset of seed 42 (and three
suite datasets) is drawn in 2-D from a fixed subsample of 300 of its points.

* ``view_index(entry_id, n)``: the subsample, a deterministic function of the dataset id,
  so that the scorer stores the method's labels on exactly the points the site draws.
* ``build_views(battery)``: the 2-D coordinates and the true labels of those points
  (``docs/data/battery.json``). The projection is the linear discriminant projection of
  the 20-D data fitted on the true clusters: the most separated linear view of the
  clusters, so that any overlap left in the picture is real. Noise points (label -1) are
  projected but not used for the fit.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .battery import Battery, GROUPS

VIEW_SEED = 42
VIEW_POINTS = 300
SUITE_EXAMPLES = ["easy", "medium", "hard"]


def view_index(entry_id: str, n: int, k: int = VIEW_POINTS) -> np.ndarray:
    seed = int(hashlib.sha256(entry_id.encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(n, size=min(k, n), replace=False))


def view_entries(bat: Battery) -> Dict[str, List]:
    """{group: [entries of seed 42 in level order]} for the sweeps, plus three suite examples."""
    out: Dict[str, List] = {}
    for g in GROUPS:
        es = [e for e in bat if e.group == g and e.seed == VIEW_SEED]
        out[g] = sorted(es, key=lambda e: float(e.value))
    suite = [e for e in bat if e.group == "suite" and e.seed == VIEW_SEED and e.extra.get("variant") == 0]
    out["suite"] = sorted(suite, key=lambda e: SUITE_EXAMPLES.index(e.value))
    return out


def _project(X: np.ndarray, y: np.ndarray) -> np.ndarray:
    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from sklearn.decomposition import PCA
    inl = y >= 0
    try:
        lda = LinearDiscriminantAnalysis(n_components=2).fit(X[inl], y[inl])
        Z = lda.transform(X)
    except Exception:
        Z = PCA(n_components=2, random_state=0).fit(X[inl]).transform(X)
    return Z


def build_views(battery_root: str, out: Optional[str] = None) -> Dict:
    bat = Battery(battery_root)
    groups = {}
    for g, es in view_entries(bat).items():
        items = []
        for e in es:
            X, y = bat.load(e)
            Z = _project(X, y)
            idx = view_index(e.id, len(X))
            items.append({"id": e.id, "value": e.value, "D": None if e.D is None else round(float(e.D), 3),
                          "xy": np.round(Z[idx], 3).tolist(), "y": y[idx].astype(int).tolist()})
        meta = GROUPS.get(g, {"label": "Suite", "symbol": "", "what": "three regimes of the 75-dataset suite (variant 0)"})
        groups[g] = {"label": meta["label"], "symbol": meta["symbol"], "what": meta["what"], "datasets": items}
    views = {"schema": "clustaudit-battery-views/1", "battery": bat.name, "seed": VIEW_SEED,
             "points": VIEW_POINTS, "projection": "linear discriminant projection fitted on the true clusters",
             "groups": groups}
    if out:
        Path(out).write_text(json.dumps(views, separators=(",", ":")), encoding="utf-8")
    return views


def method_views(bat: Battery, labels: Dict[str, Dict]) -> Dict:
    """The method's labels on the view points of the seed-42 sweep datasets (None when the run failed)."""
    out = {}
    for g, es in view_entries(bat).items():
        if g == "suite":
            continue
        lab = []
        for e in es:
            r = labels.get(e.id)
            if r is None or r["status"] != "ok":
                lab.append(None)
            else:
                idx = view_index(e.id, e.n)
                lab.append([int(v) for v in np.asarray(r["labels"])[idx]])
        out[g] = {"seed": VIEW_SEED, "values": [float(e.value) for e in es], "ids": [e.id for e in es], "labels": lab}
    return out
