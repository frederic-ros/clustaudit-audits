"""
Publishing audits on the static site
====================================

``publish`` adds one audit to the site folder (``docs/`` for GitHub Pages):

* ``audits/<id>.json``  the audit itself;
* ``methods/<id>.py``   the method file that was audited;
* ``badge/<id>.svg``    a README badge;
* ``audits/index.json`` the gallery index, rebuilt from every audit present.
"""
from __future__ import annotations

import json
import re
import shutil
from html import escape
from pathlib import Path
from typing import Dict, List, Optional

from .score import SCHEMA

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,60}$")


def validate(a: Dict) -> List[str]:
    """Structural checks on an audit (the site renders only what passes)."""
    p = []
    if a.get("schema") != SCHEMA:
        p.append(f"schema must be {SCHEMA}")
    if not ID_RE.match(str(a.get("id", ""))):
        p.append("id must be lowercase letters, digits and dashes")
    for k in ("method", "battery", "card", "sweeps", "suite", "counts"):
        if not isinstance(a.get(k), dict):
            p.append(f"missing section {k}")
    if p:
        return p
    for g in ("overlap", "anisotropy", "inter_density", "intra_density", "imbalance", "eta_int"):
        s = a["sweeps"].get(g)
        if not s or len(s.get("values", [])) != len(s.get("ari_mean", [])):
            p.append(f"sweep {g} incomplete")
    if len(a["card"].get("row", [])) != 6:
        p.append("card row must have 6 cells")
    if not isinstance(a["method"].get("name"), str) or len(a["method"]["name"]) > 60:
        p.append("method name missing or too long")
    return p


def badge_svg(a: Dict) -> str:
    c = a["card"]
    mode = c["failure"]["mode"]
    colour = {"silent": "#B5540B", "detectable": "#2853C7", "ok": "#1D6B4F"}.get(mode, "#6B7280")
    sig = c["sigma_crit"]["text"].split(" ")[0]
    left, right = "clustaudit", f"σ_crit {sig} · fails {mode}" if mode in ("silent", "detectable") else f"σ_crit {sig} · {mode}"
    w = lambda s: int(len(s) * 6.6 + 14)
    lw, rw = w(left), w(right)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{lw + rw}" height="20" role="img" '
            f'aria-label="{escape(left)}: {escape(right)}"><title>{escape(left)}: {escape(right)}</title>'
            f'<rect width="{lw}" height="20" rx="3" fill="#14171F"/><rect x="{lw}" width="{rw}" height="20" rx="3" fill="{colour}"/>'
            f'<rect x="{lw - 4}" width="8" height="20" fill="{colour}"/>'
            f'<g fill="#fff" font-family="Verdana,DejaVu Sans,sans-serif" font-size="11">'
            f'<text x="{lw / 2:.0f}" y="14" text-anchor="middle">{escape(left)}</text>'
            f'<text x="{lw + rw / 2:.0f}" y="14" text-anchor="middle">{escape(right)}</text></g></svg>')


def index_entry(a: Dict) -> Dict:
    c, s = a["card"], a["sweeps"]
    return {
        "id": a["id"], "name": a["method"]["name"], "family": a["method"]["family"],
        "needs_k": a["method"]["needs_k"], "reference": bool(a["method"].get("reference_audit")),
        "created": a.get("created", ""), "issue": a.get("issue"),
        "sigma": c["sigma_crit"]["text"], "alpha": c["alpha_crit"]["text"], "delta": c["delta_crit"]["text"],
        "f1": c["imbalance"]["f1_min"], "failure": c["failure"]["mode"], "failure_fraction": c["failure"]["fraction"],
        "overlap": {"values": s["overlap"]["values"], "ari": s["overlap"]["ari_mean"]},
        "eta_int": {"values": s["eta_int"]["values"], "ari": s["eta_int"]["ari_mean"]},
        "suite_ari": a["suite"]["ari_mean"], "wall_time_s": a.get("run", {}).get("wall_time_s"),
    }


ORDER = ["kmeans", "gmm", "spectral", "ward", "average", "dbscan", "hdbscan", "optics", "dpc"]


def rebuild_index(site: Path) -> Dict:
    entries = []
    for f in sorted((site / "audits").glob("*.json")):
        if f.name == "index.json":
            continue
        a = json.loads(f.read_text(encoding="utf-8"))
        if validate(a):
            continue
        entries.append(index_entry(a))
    entries.sort(key=lambda e: (not e["reference"], ORDER.index(e["id"]) if e["id"] in ORDER else 99,
                                e["created"] if not e["reference"] else ""), reverse=False)
    # submitted audits: most recent first
    ref = [e for e in entries if e["reference"]]
    sub = sorted([e for e in entries if not e["reference"]], key=lambda e: e["created"], reverse=True)
    idx = {"schema": "clustaudit-audit-index/1", "battery": "paper-v2.2", "audits": ref + sub}
    (site / "audits" / "index.json").write_text(json.dumps(idx, ensure_ascii=False, indent=1), encoding="utf-8")
    return idx


def publish(audit_path: str, site: str = "docs", method_file: Optional[str] = None,
            issue: Optional[int] = None) -> Path:
    site_p = Path(site)
    a = json.loads(Path(audit_path).read_text(encoding="utf-8"))
    if issue is not None:
        a["issue"] = int(issue)
    problems = validate(a)
    if problems:
        raise ValueError("audit not published: " + "; ".join(problems))
    for d in ("audits", "methods", "badge"):
        (site_p / d).mkdir(parents=True, exist_ok=True)
    out = site_p / "audits" / f"{a['id']}.json"
    out.write_text(json.dumps(a, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    if method_file:
        shutil.copyfile(method_file, site_p / "methods" / f"{a['id']}.py")
    (site_p / "badge" / f"{a['id']}.svg").write_text(badge_svg(a), encoding="utf-8")
    rebuild_index(site_p)
    return out
