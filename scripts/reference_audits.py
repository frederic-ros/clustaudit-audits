#!/usr/bin/env python
"""Audit the nine reference methods (methods/reference/*.py) and publish their cards in docs/.

    python scripts/reference_audits.py --jobs 4
    python scripts/compare_with_paper.py --results ../clustaudit/benchmarks/classical/results
"""
import argparse, json, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from auditkit.label import run_labels          # noqa: E402
from auditkit.method import read_info          # noqa: E402
from auditkit.score import score               # noqa: E402
from auditkit.site import publish              # noqa: E402

ORDER = ["kmeans", "gmm", "spectral", "ward", "average", "dbscan", "hdbscan", "optics", "dpc"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=2)
    ap.add_argument("--only", nargs="*", default=ORDER)
    ap.add_argument("--site", default=str(ROOT / "docs"))
    a = ap.parse_args()
    battery = str(ROOT / "battery" / "paper-v2.2")
    with tempfile.TemporaryDirectory() as tmp:
        for m in a.only:
            src = ROOT / "methods" / "reference" / f"{m}.py"
            labels = Path(tmp) / f"{m}.npz"
            meta = run_labels(str(src), battery, str(labels), jobs=a.jobs)
            audit = score(battery, str(labels), read_info(src), m, run_meta=meta, reference=True)
            out = Path(tmp) / f"{m}.json"
            out.write_text(json.dumps(audit, ensure_ascii=False), encoding="utf-8")
            publish(str(out), a.site, method_file=str(src))
            print(f"{m:9s} {' | '.join(audit['card']['row'])}")


if __name__ == "__main__":
    main()
