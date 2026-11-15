"""
Scoring: from labels to an audit card
=====================================

``score`` reads the labels written by ``auditkit.label`` and the battery, evaluates
every run with clustaudit's evaluation (``clustaudit.audit.evaluation.evaluate_run``,
the function used for the paper), and computes the audit card with the rules of the
paper's Table 8 (analysis/make_paper_tables_v2.py):

* critical level of a sweep = first level where the mean inlier ARI over the five
  seeds falls below 0.5, with the range of the per-seed critical levels; ">max" when
  the mean never falls below 0.5; "<= first level" when it is below 0.5 from the first
  level in every seed;
* noise placement = mean ARI with all the noise distant (eta_int = 0) and all of it
  between clusters (eta_int = 1), at a total noise of 30%;
* imbalance = mean ARI and mean smallest-cluster F1 at rho = 5;
* failure at sigma_max = the most frequent failure mode at the largest overlap
  ("declared" degenerate outputs are reported as "detectable");
* note of a factor = mean inlier ARI over the levels of its sweep (0 to 1). There is
  deliberately no overall score: a mean over factors would hide how a method fails.

This module never imports the audited method. Runs that raised, exceeded the time
limit, returned an invalid output or crashed are kept: their failure mode is "error"
and they count as ARI 0 and F1 0 in every aggregate.
"""
from __future__ import annotations

import datetime as _dt
import math
import platform
from typing import Dict, List, Optional

import numpy as np

from .battery import Battery, GROUPS
from .label import read_labels
from .method import MethodInfo
from .schema import SCHEMA, PROFILE_ORDER, note_of
from .views import method_views
THRESHOLD = 0.5
MODES = ["ok", "silent", "declared", "error"]
TIE_ORDER = ["silent", "declared", "error", "ok"]


def _g(v: float) -> str:
    return f"{v:g}"


def _f2(v) -> str:
    return "--" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v:.2f}"


def _num(v, nd=4):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), nd)


# ------------------------------------------------------------------ evaluation of runs
def evaluate(bat: Battery, labels: Dict[str, Dict]) -> List[Dict]:
    from clustaudit.audit.evaluation import evaluate_run, error_row
    rows = []
    for e in bat:
        if e.id not in labels:
            raise ValueError(f"no labels for dataset {e.id}: the labels file does not cover the battery")
        r = labels[e.id]
        X, y = bat.load(e)
        if r["status"] == "ok":
            lab = r["labels"]
            if len(lab) != len(y) or lab.min(initial=0) < -1:
                res = error_row("invalid labels")
                status = "invalid_output"
            else:
                res = evaluate_run(X, y, lab, "ok"); status = "ok"
        else:
            res = error_row(r["message"] or r["status"]); status = r["status"]
        ari, f1 = res["ARI"], res["min_cluster_f1"]
        rows.append({
            "id": e.id, "group": e.group, "value": e.value, "seed": e.seed, "D": e.D,
            "ARI": 0.0 if ari is None or np.isnan(ari) else float(ari),
            "F1": 0.0 if f1 is None or np.isnan(f1) else float(f1),
            "mode": res["failure_mode"], "status": status,
            "n_found": None if np.isnan(res["n_clusters_found"]) else int(res["n_clusters_found"]),
            "rejected": None if np.isnan(res["frac_noise_pred"]) else float(res["frac_noise_pred"]),
            "seconds": float(r["seconds"]), "message": r["message"] if status != "ok" else "",
        })
    return rows


# ------------------------------------------------------------------ sweep summaries
def critical(levels: List[float], seeds: List[int], ari: Dict) -> Dict:
    """ari[(value, seed)] -> ARI. Returns the critical level and the per-seed range."""
    def first_below(means):
        for v, m in zip(levels, means):
            if m < THRESHOLD:
                return v
        return math.inf
    mean = first_below([np.mean([ari[(v, s)] for s in seeds]) for v in levels])
    per = [first_below([ari[(v, s)] for v in levels]) for s in seeds]
    lo, hi = min(per), max(per)
    fmt = lambda v: ">max" if math.isinf(v) else _g(v)
    if mean == levels[0] and hi == levels[0]:
        text = f"≤{_g(levels[0])}"
    else:
        text = f"{fmt(mean)} [{fmt(lo)}, {fmt(hi)}]"
    enc = lambda v: ">max" if math.isinf(v) else float(v)
    return {"mean": enc(mean), "seed_min": enc(lo), "seed_max": enc(hi), "text": text,
            "first": float(levels[0]), "last": float(levels[-1])}


def summarise_sweep(rows: List[Dict], group: str) -> Dict:
    meta = GROUPS[group]
    rs = [r for r in rows if r["group"] == group]
    levels = sorted({float(r["value"]) for r in rs})
    seeds = sorted({r["seed"] for r in rs})
    ari = {(float(r["value"]), r["seed"]): r["ARI"] for r in rs}
    out = {"label": meta["label"], "symbol": meta["symbol"], "what": meta["what"], "values": levels,
           "seeds": seeds, "ari_mean": [], "ari_seeds": [], "f1_mean": [], "modes": {m: [] for m in MODES}}
    for v in levels:
        at = [r for r in rs if float(r["value"]) == v]
        out["ari_mean"].append(_num(np.mean([r["ARI"] for r in at])))
        out["ari_seeds"].append([_num(ari[(v, s)]) for s in seeds])
        out["f1_mean"].append(_num(np.mean([r["F1"] for r in at])))
        for m in MODES:
            out["modes"][m].append(_num(np.mean([r["mode"] == m for r in at])))
    out["crit"] = critical(levels, seeds, ari)
    out["note"] = note_of(out["ari_mean"])
    return out


def summarise_suite(rows: List[Dict]) -> Dict:
    rs = [r for r in rows if r["group"] == "suite"]
    from scipy.stats import spearmanr
    regimes = ["easy", "medium", "hard"]
    D = np.array([r["D"] for r in rs], float); A = np.array([r["ARI"] for r in rs], float)
    rho = spearmanr(D, A).statistic if np.ptp(A) > 0 else float("nan")
    return {
        "n": len(rs), "ari_mean": _num(A.mean()),
        "by_regime": {g: _num(np.mean([r["ARI"] for r in rs if r["value"] == g])) for g in regimes},
        "modes": {m: _num(np.mean([r["mode"] == m for r in rs])) for m in MODES},
        "spearman_D_ARI": _num(rho, 3),
        "points": [[_num(r["D"]), _num(r["ARI"]), regimes.index(r["value"])] for r in rs],
    }


# ------------------------------------------------------------------ the card
def _crit_tile(s: Dict, key: str) -> Dict:
    c, sym = s["crit"], s["symbol"]
    first, last = _g(c["first"]), _g(c["last"])
    if c["text"].startswith("≤"):
        return {"k": s["label"], "v": f"Fails from {sym} = {first}",
                "d": f"Mean ARI already below 0.5 at the first level, in every seed."}
    if c["mean"] == ">max":
        if c["seed_min"] == ">max":
            d = f"Mean ARI above 0.5 over the whole grid, up to {sym} = {last}, in every seed."
        else:
            d = f"Mean ARI above 0.5 over the whole grid; one seed or more already fails at {sym} = {_g(c['seed_min'])}."
        return {"k": s["label"], "v": "Holds on average", "d": d}
    lo, hi = c["seed_min"], c["seed_max"]
    if lo == hi:
        d = "The same limit in every seed."
    elif hi == ">max":
        d = f"Per-seed limits from {_g(lo)} to beyond the grid ({sym} = {last})."
    else:
        d = f"Per-seed limits between {_g(lo)} and {_g(hi)}."
    return {"k": s["label"], "v": f"Breaks at {sym} = {_g(c['mean'])}", "d": d}


def build_card(sw: Dict[str, Dict], n_runs: int, n_errors: int) -> Dict:
    ov, an, de, im, eta = (sw[k] for k in ("overlap", "anisotropy", "inter_density", "imbalance", "eta_int"))
    distant, bridge = eta["ari_mean"][0], eta["ari_mean"][-1]
    rho = im["values"][-1]; im_ari, im_f1 = im["ari_mean"][-1], im["f1_mean"][-1]
    fr = {m: ov["modes"][m][-1] for m in MODES}
    top = max(fr.values())
    mode = next(m for m in TIE_ORDER if fr[m] == top)
    shown = {"declared": "detectable", "silent": "silent", "ok": "ok", "error": "error"}[mode]
    smax = _g(ov["values"][-1])

    tiles = [_crit_tile(ov, "overlap"), _crit_tile(an, "anisotropy"), _crit_tile(de, "inter_density"),
             {"k": "Noise placement", "v": f"{_f2(distant)} → {_f2(bridge)}",
              "d": "From all-distant noise to noise between clusters, at η = 0.3."}]
    if im_ari >= 0.7 and im_f1 < 0.5:
        d_im = "The aggregate stays high while the smallest cluster is mostly lost."
    elif im_ari >= 0.7:
        d_im = "Both the aggregate and the smallest cluster are recovered."
    else:
        d_im = "The partition degrades as a whole."
    tiles.append({"k": f"Size imbalance, ρ = {_g(rho)}", "v": f"ARI {_f2(im_ari)} · F1 {_f2(im_f1)}", "d": d_im})
    pct = f"{fr[mode]:.0%}" if fr[mode] < 1 else "every"
    runs_txt = "runs" if pct != "every" else "run"
    fail_tile = {
        "detectable": ("Detectably", f"A single cluster or most points rejected, in {pct} {runs_txt} at the largest overlap."),
        "silent": ("Silently", f"A well-formed but wrong partition (ARI below 0.3), in {pct} {runs_txt} at the largest overlap."),
        "ok": ("It holds", f"ARI still at or above 0.3 in {pct} {runs_txt} at the largest overlap."),
        "error": ("With errors", f"The method raised or timed out in {pct} {runs_txt} at the largest overlap."),
    }[shown]
    tiles.append({"k": "How it fails", "v": fail_tile[0], "d": fail_tile[1]})

    reading = []
    if distant - bridge >= 0.3:
        reading.append(f"Robust to distant outliers, hurt by noise between clusters: inlier ARI {_f2(distant)} "
                       f"when all the noise is distant, {_f2(bridge)} when it bridges the clusters.")
    elif bridge - distant >= 0.3:
        reading.append(f"Hurt by distant outliers, not by noise between clusters: inlier ARI {_f2(distant)} "
                       f"when all the noise is distant, {_f2(bridge)} when it bridges the clusters.")
    else:
        reading.append(f"Where the noise lies matters little: inlier ARI {_f2(distant)} when all the noise is "
                       f"distant, {_f2(bridge)} when it bridges the clusters.")
    first_decl = next((v for v, f in zip(ov["values"], ov["modes"]["declared"]) if f and f > 0), None)
    if shown == "detectable":
        s = f"It fails visibly. At σ = {smax}, {'every run returns' if pct == 'every' else pct + ' of the runs return'} " \
            f"a single cluster or rejects most points: a user sees the failure without needing labels."
        if first_decl is not None and first_decl < ov["values"][-1]:
            s += f" Such outputs appear from σ = {_g(first_decl)}."
        reading.append(s)
    elif shown == "silent":
        reading.append(f"It fails silently. At σ = {smax}, {'every run returns' if pct == 'every' else pct + ' of the runs return'} "
                       f"a well-formed partition that is wrong (ARI below 0.3): nothing in the output warns the user.")
    elif shown == "ok":
        reading.append(f"At the largest overlap (σ = {smax}), {'every run' if pct == 'every' else pct + ' of the runs'} "
                       f"still reaches an ARI of 0.3 or more.")
    else:
        reading.append(f"At σ = {smax} the method mostly raised an error or exceeded the time limit.")
    if im_ari >= 0.7 and im_f1 < 0.5:
        reading.append(f"Imbalance flatters the aggregate. At ρ = {_g(rho)} the inlier ARI is {_f2(im_ari)}, "
                       f"while the smallest cluster is mostly lost (F1 {_f2(im_f1)}).")
    elif im_ari >= 0.7:
        reading.append(f"Imbalance is handled: at ρ = {_g(rho)}, inlier ARI {_f2(im_ari)} and smallest-cluster F1 {_f2(im_f1)}.")
    else:
        reading.append(f"Imbalance hurts the whole partition: at ρ = {_g(rho)}, inlier ARI {_f2(im_ari)}, "
                       f"smallest-cluster F1 {_f2(im_f1)}.")
    if n_errors:
        reading.append(f"{n_errors} of the {n_runs} runs raised an error, exceeded the time limit or returned an "
                       f"invalid output; they count as ARI 0.")

    return {
        "profile": {g: sw[g]["note"] for g in PROFILE_ORDER},
        "sigma_crit": ov["crit"], "alpha_crit": an["crit"], "delta_crit": de["crit"],
        "noise": {"eta": 0.3, "distant": distant, "bridge": bridge},
        "imbalance": {"rho": rho, "ari": im_ari, "f1_min": im_f1},
        "failure": {"at_sigma": ov["values"][-1], "mode": shown, "fraction": _num(fr[mode], 2)},
        "row": [ov["crit"]["text"], an["crit"]["text"], de["crit"]["text"],
                f"{_f2(distant)} / {_f2(bridge)}", f"{_f2(im_ari)} / {_f2(im_f1)}",
                f"{shown} ({fr[mode]:.2f})"],
        "tiles": tiles, "reading": reading,
    }


def score(battery_root: str, labels_path: str, info: MethodInfo, audit_id: str,
          run_meta: Optional[Dict] = None, reference: bool = False, extra: Optional[Dict] = None) -> Dict:
    import clustaudit
    bat = Battery(battery_root)
    problems = bat.verify()
    if problems:
        raise ValueError("the battery does not match its manifest: " + "; ".join(problems[:5]))
    labels = read_labels(labels_path)
    rows = evaluate(bat, labels)
    sw = {g: summarise_sweep(rows, g) for g in GROUPS}
    n_err = sum(r["mode"] == "error" for r in rows)
    rm = run_meta or {}
    env = rm.get("environment", {}) if isinstance(rm.get("environment"), dict) else {}
    audit = {
        "schema": SCHEMA,
        "id": audit_id,
        "created": _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "method": {"name": info.name, "family": info.family, "needs_k": info.needs_k,
                   "protocol": "F (true K given)" if info.needs_k else "K chosen by the method",
                   "requirements": info.requirements, "reference_url": info.reference,
                   "source_sha256": info.source_sha256, "reference_audit": reference},
        "battery": {"name": bat.name, "manifest_sha256": bat.manifest_sha256, "n_datasets": len(bat)},
        "scoring": {"clustaudit": getattr(clustaudit, "__version__", "?"), "python": platform.python_version(),
                    "threshold": THRESHOLD, "software_doi": "10.5281/zenodo.24239816"},
        "run": {"wall_time_s": _num(rm.get("wall_time_s"), 1), "jobs": rm.get("jobs"),
                "timeout_s": rm.get("timeout_s"),
                "environment": {k: str(env.get(k, ""))[:80] for k in ("python", "numpy", "scikit-learn", "platform", "cpu_count")}},
        "counts": {"runs": len(rows), **{m: sum(r["mode"] == m for r in rows) for m in MODES},
                   "by_status": {s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})}},
        "card": build_card(sw, len(rows), n_err),
        "sweeps": sw,
        "suite": summarise_suite(rows),
        "views": method_views(bat, labels),
        "rows": {"columns": ["id", "ARI", "F1", "mode", "n_found", "rejected", "seconds", "message"],
                 "data": [[r["id"], _num(r["ARI"], 6), _num(r["F1"], 6), r["mode"], r["n_found"], _num(r["rejected"], 3),
                           _num(r["seconds"], 3), r["message"]] for r in rows]},
    }
    if extra:
        audit.update(extra)
    return audit
