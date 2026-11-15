"""Plain-text rendering of an audit card (terminal, issue comments)."""
from __future__ import annotations

from typing import Dict

from .schema import PROFILE_ORDER, note_of

SYM = {"overlap": "σ", "anisotropy": "α", "inter_density": "δ", "intra_density": "κ", "imbalance": "ρ", "eta_int": "η_int"}
HEAD = ["σ_crit [seeds]", "α_crit [seeds]", "δ_crit [seeds]", "noise dist / bridge", "ρ=5 ARI / F1_min", "failure at σ_max"]


def profile(a: Dict) -> Dict:
    p = a["card"].get("profile")
    return p if p else {g: note_of(a["sweeps"][g]["ari_mean"]) for g in PROFILE_ORDER}


def render(a: Dict, markdown: bool = False) -> str:
    c, m = a["card"], a["method"]
    n = a["counts"]
    prof = profile(a)
    lines = []
    if markdown:
        lines.append(f"**{m['name']}** · {m['family']} · {m['protocol']} · battery {a['battery']['name']} "
                     f"({n['runs']} runs: {n['ok']} ok, {n['silent']} silent, {n['declared']} detectable, {n['error']} errors)")
        lines.append("")
        lines.append("| " + " | ".join(HEAD) + " |")
        lines.append("|" + "---|" * len(HEAD))
        lines.append("| " + " | ".join(x.replace("|", "/") for x in c["row"]) + " |")
        lines.append("")
        lines.append("Notes per factor (mean inlier ARI over the sweep, 0 to 1):")
        lines.append("")
        lines.append("| " + " | ".join(f"{a['sweeps'][g]['label']} ({SYM[g]})" for g in PROFILE_ORDER) + " |")
        lines.append("|" + "---|" * len(PROFILE_ORDER))
        lines.append("| " + " | ".join(f"{prof[g]:.2f}" for g in PROFILE_ORDER) + " |")
        lines.append("")
        for t in c["tiles"]:
            lines.append(f"- **{t['k']}**: {t['v']}. {t['d']}")
        lines.append("")
        lines.append("**What the audit says**")
        lines.append("")
        lines.extend("- " + r for r in c["reading"])
        return "\n".join(lines)
    lines.append(f"{m['name']}  ({m['family']}, {m['protocol']}), battery {a['battery']['name']}, "
                 f"{n['runs']} runs: ok {n['ok']}, silent {n['silent']}, detectable {n['declared']}, error {n['error']}")
    w = max(len(h) for h in HEAD)
    for h, v in zip(HEAD, c["row"]):
        lines.append(f"  {h:<{w}}  {v}")
    lines.append(f"  {'notes':<{w}}  " + "  ".join(f"{SYM[g]} {prof[g]:.2f}" for g in PROFILE_ORDER))
    s = a["suite"]
    lines.append(f"  {'suite mean ARI':<{w}}  {s['ari_mean']:.2f} (easy {s['by_regime']['easy']:.2f}, "
                 f"medium {s['by_regime']['medium']:.2f}, hard {s['by_regime']['hard']:.2f})")
    for r in c["reading"]:
        lines.append("  - " + r)
    return "\n".join(lines)
