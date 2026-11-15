"""
A method under audit
====================

A method is one Python file that defines::

    def cluster(X, seed, n_clusters=None):
        ...
        return labels          # one integer per row of X, -1 = point left unassigned

and, optionally, a header of comments read by the audit::

    # name: My method
    # family: Density            (Centroid | Connectivity | Density | Graph | Deep | Other)
    # needs-k: yes               (yes: the method receives the true number of clusters)
    # requirements: numpy scikit-learn
    # reference: https://doi.org/...

``seed`` is the seed of the dataset; use it for every random choice, so that the audit
can be re-run identically. ``n_clusters`` is the true K when ``needs-k`` is yes
(protocol F of the paper) and ``None`` otherwise.
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np

FAMILIES = ["Centroid", "Connectivity", "Density", "Graph", "Deep", "Other"]
PREINSTALLED = {"numpy", "scipy", "scikit-learn", "sklearn", "pandas", "threadpoolctl", "joblib"}
_HEADER = re.compile(r"^\s*#\s*(name|family|needs-k|needs_k|requirements|reference)\s*:\s*(.*?)\s*$", re.I)
# a requirement is a bare distribution name with optional extras and version bounds: no URL, no option
_REQ = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,60}(\[[A-Za-z0-9,._-]{1,60}\])?"
                  r"((==|>=|<=|~=|!=|<|>)[A-Za-z0-9.*+!_-]{1,30}(,(==|>=|<=|~=|!=|<|>)[A-Za-z0-9.*+!_-]{1,30})*)?$")


class InvalidOutput(ValueError):
    """The method returned something that is not one integer label per point."""


@dataclass
class MethodInfo:
    path: str
    name: str
    family: str = "Other"
    needs_k: bool = False
    requirements: List[str] = field(default_factory=list)
    reference: str = ""
    source_sha256: str = ""


def slug(name: str, maxlen: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s[:maxlen].strip("-") or "method")


def _yes(v: str) -> bool:
    return v.strip().lower() in {"yes", "y", "true", "1", "oui"}


def read_info(path: str | Path) -> MethodInfo:
    """Read the header of a method file (no code is executed)."""
    path = Path(path)
    src = path.read_text(encoding="utf-8")
    meta = {}
    for line in src.splitlines()[:40]:
        m = _HEADER.match(line)
        if m:
            meta[m.group(1).lower().replace("_", "-")] = m.group(2)
    fam = meta.get("family", "Other").strip().capitalize()
    reqs = meta.get("requirements", "").replace(",", " ").split()
    bad = [r for r in reqs if not _REQ.match(r)]
    if bad:
        raise ValueError(f"requirements not accepted (a name with optional version bounds only): {bad}")
    return MethodInfo(path=str(path), name=meta.get("name", path.stem).strip()[:60] or path.stem,
                      family=fam if fam in FAMILIES else "Other",
                      needs_k=_yes(meta.get("needs-k", "no")), requirements=reqs,
                      reference=meta.get("reference", "")[:300],
                      source_sha256=hashlib.sha256(src.encode("utf-8")).hexdigest())


def extra_requirements(info: MethodInfo) -> List[str]:
    """Requirements to install on top of the runner environment."""
    return [r for r in info.requirements
            if re.split(r"[\[<>=!~]", r)[0].lower().replace("_", "-") not in PREINSTALLED]


def load_function(path: str | Path) -> Callable:
    """Import the method file and return its ``cluster`` function. This executes the file."""
    path = Path(path).resolve()
    name = f"_audited_method_{hashlib.sha1(str(path).encode()).hexdigest()[:10]}"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    fn = getattr(mod, "cluster", None)
    if not callable(fn):
        raise AttributeError("the file must define a function `cluster(X, seed, n_clusters=None)`")
    return fn


def call_signature_problem(fn: Callable, needs_k: bool) -> Optional[str]:
    """A message when ``fn`` cannot be called the way the audit calls it, else None."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return None
    try:
        if needs_k:
            sig.bind(np.zeros((2, 2)), 0, n_clusters=2)
        else:
            sig.bind(np.zeros((2, 2)), 0)
    except TypeError as e:
        how = "cluster(X, seed, n_clusters=K)" if needs_k else "cluster(X, seed)"
        return f"the audit calls {how}: {e}"
    return None


def call(fn: Callable, X: np.ndarray, seed: int, K: Optional[int], needs_k: bool) -> np.ndarray:
    out = fn(X, seed, n_clusters=K) if needs_k else fn(X, seed)
    return as_labels(out, len(X))


def as_labels(out, n: int) -> np.ndarray:
    """Check and normalise a method output: one integer >= -1 per point."""
    if isinstance(out, tuple):
        raise InvalidOutput("returned a tuple; return the labels only")
    try:
        a = np.asarray(out)
    except Exception as e:  # pragma: no cover
        raise InvalidOutput(f"output is not array-like: {e}")
    if a.ndim == 2 and 1 in a.shape:
        a = a.reshape(-1)
    if a.ndim != 1 or len(a) != n:
        raise InvalidOutput(f"expected {n} labels, got an array of shape {a.shape}")
    if a.dtype.kind == "b" or a.dtype.kind not in "iuf":
        raise InvalidOutput(f"labels must be integers, got dtype {a.dtype}")
    if a.dtype.kind == "f":
        if not np.all(np.isfinite(a)) or not np.all(a == np.round(a)):
            raise InvalidOutput("labels must be integers (got non-integer or non-finite values)")
    a = a.astype(np.int64)
    if a.min(initial=0) < -1:
        raise InvalidOutput("labels must be >= -1 (-1 marks an unassigned point)")
    return a
