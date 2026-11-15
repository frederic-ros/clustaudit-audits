#!/usr/bin/env python
"""Build docs/data/quicktest.json: the three small 2-D datasets of the in-browser quick test.

They are a smoke test, not part of the audit: four clusters, 2-D, a few hundred points,
generated with numpy (seed 7) so that the browser needs nothing but the JSON."""
import json, sys
from pathlib import Path
import numpy as np

def blobs(rng, centres, std, n_per):
    X = np.vstack([rng.normal(c, std, size=(n_per, 2)) for c in centres])
    y = np.repeat(np.arange(len(centres)), n_per)
    return X, y

def build(seed=7):
    rng = np.random.default_rng(seed)
    sq = np.array([[0.25, 0.25], [0.75, 0.25], [0.25, 0.75], [0.75, 0.75]])
    A = blobs(rng, sq, 0.06, 75)
    B = blobs(rng, sq, 0.16, 75)
    inner = np.array([[0.42, 0.42], [0.58, 0.42], [0.42, 0.58], [0.58, 0.58]])
    Xc, yc = blobs(rng, inner, 0.035, 60)
    out = np.vstack([rng.normal(c, 0.012, size=(8, 2)) for c in ([0.03, 0.03], [0.97, 0.97])])
    C = (np.vstack([Xc, out]), np.concatenate([yc, -np.ones(len(out), int)]))
    sets = [("separated", "Separated clusters", "Four well-separated groups.", A),
            ("overlap", "Strong overlap", "The same four groups, spread until they overlap.", B),
            ("noise", "Distant noise", "Four compact groups and 16 distant outliers in two corners.", C)]
    return {"seed": seed, "n_clusters": 4, "datasets": [
        {"id": i, "name": n, "what": w, "X": np.round(X, 4).tolist(), "y": y.astype(int).tolist()} for i, n, w, (X, y) in sets]}

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/data/quicktest.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build(), separators=(",", ":")), encoding="utf-8")
    print("->", out)
