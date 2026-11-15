"""
Running a method on the battery
===============================

``run_labels`` runs the method on every dataset of the battery and stores the labels
it returns, nothing else. Scoring is a separate step (``auditkit.score``) that never
imports the method: on the public service the two steps run in different jobs, and the
method's code only ever runs in the job that has no write access and no secrets.

The method runs in worker processes; the calling process does not import it. A run
that raises, exceeds the time limit, returns an invalid output or kills its worker is
recorded with that status: no run is dropped.
"""
from __future__ import annotations

import json
import os
import platform
import signal
import sys
import time
import traceback
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
import multiprocessing as mp
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .battery import Battery
from .method import InvalidOutput, call, load_function, read_info

STATUSES = ("ok", "error", "timeout", "invalid_output", "crashed")
_FN = None
_NEEDS_K = False
_INIT_ERROR = ""


class _Timeout(Exception):
    pass


def _alarm(signum, frame):
    raise _Timeout()


def _init(method_path: str, needs_k: bool, threads: int):
    global _FN, _NEEDS_K, _INIT_ERROR
    for v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        os.environ[v] = str(threads)
    try:
        from threadpoolctl import threadpool_limits
        threadpool_limits(threads)
    except Exception:
        pass
    import warnings
    warnings.filterwarnings("ignore")
    _NEEDS_K = needs_k
    try:
        _FN = load_function(method_path)
    except BaseException as e:        # reported on every run instead of breaking the pool
        _INIT_ERROR = f"the method file could not be imported: {type(e).__name__}: {e}"


def _task(root: str, file: str, seed: int, K: int, timeout: float):
    if _FN is None:
        return None, "error", _INIT_ERROR or "the method could not be loaded", 0.0
    with np.load(os.path.join(root, file), allow_pickle=False) as z:
        X = z["X"].astype(float)
    t0 = time.perf_counter()
    use_alarm = timeout and hasattr(signal, "SIGALRM")
    if use_alarm:
        signal.signal(signal.SIGALRM, _alarm)
        signal.setitimer(signal.ITIMER_REAL, float(timeout))
    try:
        labels = call(_FN, X, seed, K, _NEEDS_K)
        return labels, "ok", "", time.perf_counter() - t0
    except _Timeout:
        return None, "timeout", f"time limit of {timeout:g} s exceeded", time.perf_counter() - t0
    except InvalidOutput as e:
        return None, "invalid_output", str(e), time.perf_counter() - t0
    except Exception as e:
        tb = traceback.extract_tb(e.__traceback__)
        where = f" (line {tb[-1].lineno})" if tb else ""
        return None, "error", f"{type(e).__name__}: {e}{where}", time.perf_counter() - t0
    finally:
        if use_alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)


def _pool(method_path, needs_k, jobs, threads):
    return ProcessPoolExecutor(max_workers=jobs, mp_context=mp.get_context("spawn"),
                               initializer=_init, initargs=(method_path, needs_k, threads))


def run_labels(method_path: str, battery_root: str, out: str, jobs: int = 1, threads: int = 1,
               timeout: float = 600.0, groups: Optional[List[str]] = None, log=print) -> Dict:
    """Run the method on the battery; write ``out`` (.npz with the labels) and ``out``.json."""
    info = read_info(method_path)
    bat = Battery(battery_root)
    entries = [e for e in bat if (groups is None or e.group in groups)]
    results: Dict[str, tuple] = {}
    t_start = time.time()

    def record(e, res):
        results[e.id] = res
        if len(results) % 25 == 0 or len(results) == len(entries):
            log(f"  {len(results)}/{len(entries)} datasets ({time.time() - t_start:.0f} s)")

    log(f"{info.name}: {len(entries)} datasets of battery {bat.name}, {jobs} worker(s)")
    todo = list(entries)
    with _pool(str(Path(method_path).resolve()), info.needs_k, jobs, threads) as ex:
        futs = {ex.submit(_task, str(bat.root), e.file, e.seed, e.K, timeout): e for e in todo}
        broken = []
        for f in as_completed(futs):
            e = futs[f]
            try:
                record(e, f.result())
            except BrokenProcessPool:
                broken.append(e)
            except Exception as ex_:   # e.g. the worker could not import the method
                record(e, (None, "error", f"{type(ex_).__name__}: {ex_}", 0.0))
    # a worker died (segfault, out of memory, os._exit): find the culprit(s) one at a time
    for e in broken:
        try:
            with _pool(str(Path(method_path).resolve()), info.needs_k, 1, threads) as ex:
                record(e, ex.submit(_task, str(bat.root), e.file, e.seed, e.K, timeout).result())
        except BrokenProcessPool:
            record(e, (None, "crashed", "the process running the method died", 0.0))
        except Exception as ex_:
            record(e, (None, "error", f"{type(ex_).__name__}: {ex_}", 0.0))

    ids = [e.id for e in entries]
    lab, offs = [], [0]
    for e in entries:
        l = results[e.id][0]
        l = np.full(e.n, -2, dtype=np.int64) if l is None else l   # -2: no output
        lab.append(l.astype(np.int64)); offs.append(offs[-1] + len(l))
    np.savez_compressed(out, ids=np.array(ids), labels=np.concatenate(lab), offsets=np.array(offs),
                        status=np.array([results[i][1] for i in ids]),
                        message=np.array([results[i][2][:300] for i in ids]),
                        seconds=np.array([results[i][3] for i in ids], dtype=float))
    import sklearn
    meta = {
        "method": info.__dict__, "battery": bat.name, "battery_manifest_sha256": bat.manifest_sha256,
        "n_datasets": len(entries), "groups": groups, "jobs": jobs, "threads": threads, "timeout_s": timeout,
        "wall_time_s": round(time.time() - t_start, 1),
        "status_counts": {s: sum(r[1] == s for r in results.values()) for s in STATUSES},
        "environment": {"python": platform.python_version(), "numpy": np.__version__,
                        "scikit-learn": sklearn.__version__, "platform": platform.platform(),
                        "cpu_count": os.cpu_count()},
    }
    Path(str(out) + ".json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    log(f"done in {meta['wall_time_s']} s: {meta['status_counts']} -> {out}")
    return meta


def read_labels(path: str) -> Dict[str, Dict]:
    """Read a labels file written by ``run_labels`` (no pickle, no code)."""
    with np.load(path, allow_pickle=False) as z:
        ids, lab, offs = z["ids"], z["labels"], z["offsets"]
        st, msg, sec = z["status"], z["message"], z["seconds"]
        if not (len(ids) + 1 == len(offs) == len(st) + 1 == len(msg) + 1 == len(sec) + 1):
            raise ValueError("inconsistent labels file")
        out = {}
        for i, k in enumerate(ids):
            s = str(st[i])
            out[str(k)] = {"labels": lab[offs[i]:offs[i + 1]].astype(int), "status": s if s in STATUSES else "error",
                           "message": str(msg[i])[:300], "seconds": float(sec[i])}
    return out
