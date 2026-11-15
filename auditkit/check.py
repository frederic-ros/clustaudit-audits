"""
Pre-audit
=========

Fast checks run before the full audit, on two datasets of the battery (an easy suite
dataset and the hardest overlap level). They catch what would waste a full run:

* the file imports and defines ``cluster`` with a usable signature;
* the requirements header is acceptable;
* the output is one integer label per point (-1 allowed);
* the same seed gives the same labels (a warning only: some methods are not
  deterministic, the audit then reports their spread over seeds);
* the projected time of the full audit fits in the limit.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Dict, List

import numpy as np

from .battery import Battery
from .method import InvalidOutput, as_labels, call, call_signature_problem, load_function, read_info

PROBE = ["suite/dataset_000_easy_v0_s42", "overlap/overlap_1.4_s42"]


def check(method_path: str, battery_root: str, jobs: int = 4, limit_s: float = 5 * 3600,
          log=print) -> Dict:
    items: List[Dict] = []

    def add(key, label, ok, detail="", blocking=True):
        items.append({"key": key, "label": label, "ok": bool(ok), "blocking": blocking, "detail": str(detail)[:400]})
        log(f"  [{'ok' if ok else ('FAIL' if blocking else 'warn')}] {label}{(': ' + str(detail)) if detail else ''}")
        return ok

    try:
        info = read_info(method_path)
        add("header", "Header and requirements accepted", True,
            f"name '{info.name}', family {info.family}, needs K: {'yes' if info.needs_k else 'no'}")
    except Exception as e:
        add("header", "Header and requirements accepted", False, e)
        return _report(method_path, items, None)

    try:
        fn = load_function(method_path)
        add("imports", "Imports and defines cluster()", True)
    except Exception as e:
        add("imports", "Imports and defines cluster()", False, f"{type(e).__name__}: {e}")
        return _report(method_path, items, info)
    prob = call_signature_problem(fn, info.needs_k)
    if not add("signature", "Signature matches how the audit calls it", prob is None, prob or ""):
        return _report(method_path, items, info)

    bat = Battery(battery_root)
    times, outs, ok_labels, msg = [], [], True, ""
    for i in PROBE:
        e = bat[i]
        X, y = bat.load(e)
        t0 = time.perf_counter()
        try:
            outs.append(call(fn, X, e.seed, e.K, info.needs_k))
        except InvalidOutput as ex:
            ok_labels, msg = False, str(ex); break
        except Exception as ex:
            ok_labels, msg = False, f"{type(ex).__name__}: {ex}"; break
        times.append(time.perf_counter() - t0)
    if not add("labels", "One integer label per point", ok_labels,
               msg or "{0} cluster{1} found on an easy dataset".format(
                   len(np.unique(outs[0][outs[0] >= 0])), "" if len(np.unique(outs[0][outs[0] >= 0])) == 1 else "s")):
        return _report(method_path, items, info)

    e = bat[PROBE[0]]
    X, _ = bat.load(e)
    again = call(fn, X, e.seed, e.K, info.needs_k)
    from sklearn.metrics import adjusted_rand_score
    same = bool(np.array_equal(again, outs[0]) or adjusted_rand_score(outs[0], again) == 1.0)  # up to a permutation
    add("deterministic", "Same result with the same seed", same,
        "" if same else "two runs with the same seed give different partitions; the audit will still run",
        blocking=False)

    per = float(np.mean(times))
    projected = per * len(bat) / max(1, jobs)
    add("time", "Time per dataset within the limit", projected <= limit_s,
        f"{per:.2f} s per dataset (1000 x 20), "
        + ("under a minute" if projected < 60 else f"about {projected / 60:.0f} min")
        + f" for the {len(bat)} datasets with {jobs} workers")
    return _report(method_path, items, info, per)


def _report(path, items, info, per=None) -> Dict:
    return {"method": path, "name": getattr(info, "name", None),
            "passed": all(i["ok"] for i in items if i["blocking"]),
            "seconds_per_dataset": per, "checks": items}


def write_report(rep: Dict, out: str):
    Path(out).write_text(json.dumps(rep, indent=1), encoding="utf-8")
