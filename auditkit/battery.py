"""
The audit battery
=================

A battery is a frozen set of labelled datasets plus a manifest. Every method is run on
exactly the same files, so audits made months apart, on different machines, stay
comparable. Battery ``paper-v2.2`` is the one behind the audit cards of the paper
(Table 8):

* ``suite``: the 75-dataset suite (three regimes x five variants x five seeds);
* six single-factor sweeps, five seeds per level, n = 1000, d = 20, K = 5:

  ============== ======================================== ===========================
  group          levels                                   operating point
  ============== ======================================== ===========================
  overlap        sigma 0.2 ... 1.4                        sweep base (clustaudit 2.2)
  anisotropy     alpha 1 ... 10 (range alpha, alpha+0.5)  exp2 base
  inter_density  delta 0 ... 1                            sweep base
  intra_density  0 ... 2 (core-dense)                     sweep base
  imbalance      rho 1 ... 5                              sweep base
  eta_int        0 ... 1, total noise eta = 0.3           sweep base, eta = 0.3
  ============== ======================================== ===========================

Loading and verifying a battery needs numpy only. Building one (``build``) needs
clustaudit 2.2.0, which holds the generator.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np

NAME = "paper-v2.2"
SEEDS = [42, 123, 456, 789, 1011]

# order = order of display on the audit card
GROUPS: Dict[str, Dict] = {
    "overlap":       {"label": "Overlap", "symbol": "σ", "values": [0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4],
                      "what": "cluster spread (standard deviation); larger values make the clusters overlap"},
    "anisotropy":    {"label": "Elongation", "symbol": "α", "values": [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0],
                      "what": "anisotropy factor: clusters are stretched along random directions"},
    "inter_density": {"label": "Density heterogeneity", "symbol": "δ", "values": [0.0, 0.25, 0.5, 0.75, 1.0],
                      "what": "variation of density between clusters"},
    "intra_density": {"label": "Dense cores", "symbol": "κ", "values": [0.0, 0.5, 1.0, 2.0],
                      "what": "density contrast inside each cluster (dense core, sparse rim)"},
    "imbalance":     {"label": "Size imbalance", "symbol": "ρ", "values": [1.0, 1.5, 2.0, 3.0, 5.0],
                      "what": "ratio between the largest and the smallest cluster"},
    "eta_int":       {"label": "Noise placement", "symbol": "η_int", "values": [0.0, 0.25, 0.5, 0.75, 1.0],
                      "what": "share of the noise (total 30%) placed between clusters rather than far from them"},
}
SUITE = {"label": "Suite", "levels": ["easy", "medium", "hard"],
         "what": "75 datasets: three difficulty regimes, five variants each, five seeds"}


def content_hash(X: np.ndarray, y: np.ndarray) -> str:
    """SHA-256 of the arrays themselves (not of the .npz container, whose zip headers
    carry a time stamp)."""
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(X, dtype="<f8").tobytes())
    h.update(np.ascontiguousarray(y, dtype="<i8").tobytes())
    return h.hexdigest()


@dataclass
class Entry:
    id: str
    group: str
    value: object          # float for a sweep, regime name for the suite
    seed: int
    file: str
    sha256: str
    n: int
    d: int
    K: int
    D: Optional[float] = None
    extra: Dict = field(default_factory=dict)


class Battery:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)
        man = self.root / "manifest.json"
        if not man.exists():
            raise FileNotFoundError(f"no battery manifest at {man}")
        self.manifest = json.loads(man.read_text(encoding="utf-8"))
        self.name = self.manifest["name"]
        self.entries: List[Entry] = [Entry(**e) for e in self.manifest["datasets"]]
        self._by_id = {e.id: e for e in self.entries}

    def __len__(self):
        return len(self.entries)

    def __iter__(self) -> Iterator[Entry]:
        return iter(self.entries)

    def __getitem__(self, i: str) -> Entry:
        return self._by_id[i]

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256((self.root / "manifest.json").read_bytes()).hexdigest()

    def load(self, e: Entry | str, verify: bool = False) -> Tuple[np.ndarray, np.ndarray]:
        e = self[e] if isinstance(e, str) else e
        with np.load(self.root / e.file, allow_pickle=False) as z:
            X, y = z["X"].astype(float), z["y"].astype(int)
        if verify and content_hash(X, y) != e.sha256:
            raise ValueError(f"battery file {e.file} does not match the manifest")
        return X, y

    def verify(self) -> List[str]:
        """Return the list of problems (empty when every file matches the manifest)."""
        bad = []
        for e in self.entries:
            try:
                X, y = self.load(e)
                if content_hash(X, y) != e.sha256:
                    bad.append(f"{e.file}: content differs from the manifest")
                elif X.shape != (e.n, e.d):
                    bad.append(f"{e.file}: shape {X.shape} != ({e.n}, {e.d})")
            except Exception as ex:  # missing or unreadable
                bad.append(f"{e.file}: {type(ex).__name__}: {ex}")
        return bad

    def groups(self) -> Dict[str, List[Entry]]:
        out: Dict[str, List[Entry]] = {}
        for e in self.entries:
            out.setdefault(e.group, []).append(e)
        return out


# --------------------------------------------------------------------------- building
def _sweep_base():
    from clustaudit.audit.runner import _base_config
    return _base_config()


def _exp2_base():
    """Operating point of the paper's anisotropy sweep (benchmarks/classical/exp2_sensitivity_analysis.py)."""
    from clustaudit.config.params import StructuralParams, NoiseParams, AmbiguityParams, DensityParams
    return {
        "structural": StructuralParams(
            hypercube_connectivity=0.5, enable_anisotropy=True, anisotropy_factor_range=(1.5, 2.5),
            enable_rotation=True, cluster_std_range=(0.15, 0.25), cluster_size_imbalance=1.3,
            density_params=DensityParams(inter_density_variation=0.3, intra_density_strength=0.5)),
        "noise": NoiseParams(noise_ratio=0.1),
        "ambiguity": AmbiguityParams(enable_pre_refinement=True, enable_post_refinement=True),
    }


def _config_for(group: str, value: float):
    from clustaudit.audit.runner import SWEEPS
    if group == "anisotropy":
        cfg = _exp2_base()
        cfg["structural"].anisotropy_factor_range = (value, value + 0.5)
        return cfg
    cfg = copy.deepcopy(_sweep_base())
    if group == "eta_int":
        cfg["noise"].noise_ratio = 0.3
    SWEEPS[group](cfg, value)
    return cfg


def _fmt(v) -> str:
    return f"{v:g}"


def build(out_dir: str | os.PathLike, suite_dir: str | os.PathLike, n: int = 1000, d: int = 20,
          K: int = 5, log=print) -> Path:
    """Generate the battery with clustaudit and write the files and the manifest."""
    import clustaudit
    from clustaudit.core.pipeline import generate_dataset
    from clustaudit.metrics import profile_from_state

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    entries: List[Dict] = []

    # the stored suite of the clustaudit release (identical to what exp1 generates)
    suite_dir = Path(suite_dir)
    (out / "suite").mkdir(exist_ok=True)
    files = sorted(f for f in os.listdir(suite_dir) if f.endswith(".npz"))
    if len(files) != 75:
        raise ValueError(f"{suite_dir}: expected 75 suite files, found {len(files)}")
    for f in files:
        with np.load(suite_dir / f, allow_pickle=False) as z:
            X, y = z["X"].astype(float), z["y"].astype(int)
            D, seed = float(z["difficulty_param"]), int(z["seed"])
        parts = f[:-4].split("_")      # dataset_000_easy_v0_s42
        shutil.copyfile(suite_dir / f, out / "suite" / f)
        entries.append(dict(id=f"suite/{f[:-4]}", group="suite", value=parts[2], seed=seed,
                            file=f"suite/{f}", sha256=content_hash(X, y), n=len(X), d=X.shape[1],
                            K=int(len(np.unique(y[y >= 0]))), D=D, extra={"variant": int(parts[3][1:])}))
    log(f"suite: {len(files)} datasets copied from {suite_dir}")

    for group, meta in GROUPS.items():
        (out / group).mkdir(exist_ok=True)
        for v in meta["values"]:
            for seed in SEEDS:
                cfg = _config_for(group, float(v))
                state = generate_dataset(n, d, K, structural=cfg["structural"], noise=cfg["noise"],
                                         ambiguity=cfg["ambiguity"], random_seed=seed)
                try:
                    D = float(profile_from_state(state, seed=seed).score)
                except ValueError as ex:   # the paper's sweeps skip such a dataset; none occurs in paper-v2.2
                    log(f"  ! {group}={v} seed={seed}: {ex} (skipped, as in the paper)")
                    continue
                X, y = state.Z.astype(float), state.y.astype(int)
                name = f"{group}_{_fmt(v)}_s{seed}"
                np.savez_compressed(out / group / f"{name}.npz", X=X, y=y)
                entries.append(dict(id=f"{group}/{name}", group=group, value=float(v), seed=seed,
                                    file=f"{group}/{name}.npz", sha256=content_hash(X, y), n=n, d=d,
                                    K=int(len(np.unique(y[y >= 0]))), D=D, extra={}))
        log(f"{group}: {sum(e['group'] == group for e in entries)} datasets")

    manifest = {
        "name": NAME,
        "description": "Battery of the audit cards of Ros, Riad, Nasser, Interventional Auditing of "
                       "Clustering Algorithms (Table 8): the 75-dataset suite and six single-factor sweeps.",
        "generator": f"clustaudit {getattr(clustaudit, '__version__', '?')}",
        "software_doi": "10.5281/zenodo.24239816",
        "seeds": SEEDS,
        "groups": {"suite": SUITE, **GROUPS},
        "datasets": entries,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    log(f"{len(entries)} datasets -> {out}")
    return out
