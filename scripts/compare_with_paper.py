#!/usr/bin/env python
"""Compare the reference audits, run by auditkit as user methods, with the paper's result
files, run by run (ARI, smallest-cluster F1, failure mode), and their cards with Table 8.

    python scripts/compare_with_paper.py --results ../clustaudit/benchmarks/classical/results --audits docs/audits
"""
import argparse, json, re, sys
from pathlib import Path
import numpy as np
import pandas as pd

ALG = {"KMeans": "kmeans", "GMM": "gmm", "Spectral": "spectral", "Ward": "ward", "Average": "average",
       "DBSCAN": "dbscan", "HDBSCAN": "hdbscan", "OPTICS": "optics", "DPC": "dpc"}
FILES = {"overlap": "sweeps_v2/sweep_overlap_fixed.csv", "imbalance": "sweeps_v2/sweep_imbalance_fixed.csv",
         "inter_density": "sweeps_v2/sweep_inter_density_fixed.csv", "intra_density": "sweeps_v2/sweep_intra_density_fixed.csv",
         "eta_int": "sweeps_v2/sweep_eta_int_fixed_eta0.3.csv", "anisotropy": "exp2_sensitivity_analysis/exp2_results_fixed_anisotropy.csv",
         "suite": "exp1_difficulty_validation/exp1_results_fixed.csv"}
# Table 8 of the paper (protocol F); DPC was not run on the anisotropy sweep in the paper
TABLE8 = {
    "kmeans":   ["1 [0.8, 1]", "8 [5, >max]", ">max [0.75, >max]", "0.04 / 1.00", "0.89 / 0.06", "silent (1.00)"],
    "gmm":      ["0.2 [0.2, 0.4]", "4 [1, 5]", "0 [0, >max]", "0.00 / 0.92", "0.73 / 0.05", "silent"],
    "spectral": ["1.2 [1, 1.4]", "10 [8, 10]", ">max", "1.00 / 0.99", "1.00 / 0.50", "silent (0.80)"],
    "ward":     ["0.4 [0.2, 0.8]", "6 [1, 6]", "0 [0, >max]", "0.00 / 0.97", "0.87 / 0.04", "silent"],
    "average":  ["≤0.2", "≤1", "≤0", "0.00 / 0.97", "0.00 / 0.02", "silent"],
    "dbscan":   ["0.4 [0.4, 0.4]", "2 [1, 3]", "0.5 [0.25, 0.5]", "0.00 / 0.45", "0.98 / 0.00", "detectable (1.00)"],
    "hdbscan":  ["0.4 [0.2, 0.4]", "3 [1, 3]", ">max [0, >max]", "1.00 / 0.34", "0.97 / 0.39", "detectable"],
    "optics":   ["0.2 [0.2, 0.4]", "1.5 [1, 1.5]", "0 [0, 0.25]", "0.91 / 0.00", "0.46 / 0.54", "detectable"],
    "dpc":      ["0.6 [0.4, 0.6]", None, "0.75 [0.5, >max]", "1.00 / 0.81", "0.13 / 0.05", "silent"],
}


def key_of(group, r):
    if group == "suite":
        return f"suite::{r['difficulty']}_v{int(r['variant'])}_s{int(r['seed'])}"
    return f"{group}::{float(r['value']):g}_s{int(r['seed'])}"


def audit_key(rid):
    g, name = rid.split("/")
    if g == "suite":
        m = re.match(r"dataset_\d+_(\w+)_v(\d+)_s(\d+)", name)
        return f"suite::{m.group(1)}_v{m.group(2)}_s{m.group(3)}"
    m = re.match(rf"{g}_([\d.]+)_s(\d+)", name)
    return f"{g}::{float(m.group(1)):g}_s{m.group(2)}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True); ap.add_argument("--audits", default="docs/audits")
    ap.add_argument("--tol", type=float, default=5e-7, help="audit.json stores ARI with 6 decimals")
    a = ap.parse_args()
    ok = True
    for alg, aid in ALG.items():
        A = json.loads((Path(a.audits) / f"{aid}.json").read_text(encoding="utf-8"))
        cols = A["rows"]["columns"]
        rows = {audit_key(r[0]): dict(zip(cols, r)) for r in A["rows"]["data"]}
        n = same = 0; worst = 0.0; modes = 0
        for group, f in FILES.items():
            P = pd.read_csv(Path(a.results) / f, float_precision="round_trip")
            P = P[P.algorithm == alg]
            for _, r in P.iterrows():
                k = key_of(group, r)
                if k not in rows:
                    print(f"  {aid}: {k} missing from the audit"); ok = False; continue
                q = rows[k]; n += 1
                d = abs(q["ARI"] - r["ARI"]); worst = max(worst, d)
                same += d <= a.tol
                modes += q["mode"] == r["failure_mode"]
        card = A["card"]["row"]
        t8 = TABLE8[aid]
        cmp = [("✓" if (t is None or c == t or (t in (">max", "silent", "detectable") and c.startswith(t))) else "✗") for c, t in zip(card, t8)]
        ok &= "✗" not in cmp
        print(f"{aid:9s} runs compared {n:3d}, identical ARI {same:3d}, max |dARI| {worst:.2e}, same failure mode {modes:3d} | "
              f"card vs Table 8: {' '.join(cmp)}  {' | '.join(card)}")
        ok &= same == n
    print("ALL MATCH" if ok else "DIFFERENCES FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
