"""
auditkit command line
=====================

    python -m auditkit check  my_method.py                 # pre-audit (a few seconds)
    python -m auditkit audit  my_method.py --out my.json   # full audit: labels + card
    python -m auditkit label  my_method.py --out labels.npz
    python -m auditkit score  labels.npz --method my_method.py --id my-method --out my.json
    python -m auditkit show   my.json                      # the card in the terminal
    python -m auditkit publish my.json --site docs         # add to the site (index, badge)
    python -m auditkit from-issue --body-file body.md --out submission/
    python -m auditkit requirements my_method.py           # extra packages to install
    python -m auditkit battery build --suite ../clustaudit/datasets/suite
    python -m auditkit battery verify

The default battery is battery/paper-v2.2 next to this package.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BATTERY = str(HERE.parent / "battery" / "paper-v2.2")


def _jobs(v):
    return max(1, int(v)) if v else max(1, (os.cpu_count() or 2))


def cmd_check(a):
    from .check import check, write_report
    rep = check(a.method, a.battery, jobs=_jobs(a.jobs), limit_s=a.limit_minutes * 60)
    if a.report:
        write_report(rep, a.report)
    print("pre-audit:", "PASSED" if rep["passed"] else "FAILED")
    return 0 if rep["passed"] else 1


def cmd_label(a):
    from .label import run_labels
    meta = run_labels(a.method, a.battery, a.out, jobs=_jobs(a.jobs), threads=a.threads,
                      timeout=a.timeout, groups=a.groups)
    return 0 if meta["n_datasets"] else 1


def _score(a, labels, run_meta_path):
    from .method import read_info, slug
    from .score import score
    info = read_info(a.method)
    meta = json.loads(Path(run_meta_path).read_text()) if run_meta_path and Path(run_meta_path).exists() else None
    audit = score(a.battery, labels, info, a.id or slug(info.name), run_meta=meta, reference=a.reference)
    Path(a.out).write_text(json.dumps(audit, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    from .card_text import render
    print(render(audit))
    print(f"-> {a.out}")
    return 0


def cmd_score(a):
    return _score(a, a.labels, a.labels + ".json")


def cmd_audit(a):
    from .label import run_labels
    labels = a.labels or (str(Path(a.out).with_suffix("")) + ".labels.npz")
    run_labels(a.method, a.battery, labels, jobs=_jobs(a.jobs), threads=a.threads, timeout=a.timeout)
    return _score(a, labels, labels + ".json")


def cmd_show(a):
    from .card_text import render
    print(render(json.loads(Path(a.audit).read_text(encoding="utf-8"))))
    return 0


def cmd_publish(a):
    from .site import publish
    publish(a.audit, a.site, method_file=a.method_file, issue=a.issue)
    return 0


def cmd_from_issue(a):
    from .issue import parse_issue, write_submission
    body = Path(a.body_file).read_text(encoding="utf-8") if a.body_file else os.environ.get(a.body_env, "")
    sub = parse_issue(body)
    write_submission(sub, a.out, issue=a.number)
    print(json.dumps({k: v for k, v in sub.items() if k != "code"}, indent=1))
    return 0


def cmd_requirements(a):
    from .method import read_info, extra_requirements
    print("\n".join(extra_requirements(read_info(a.method))))
    return 0


def cmd_battery(a):
    from .battery import Battery, build
    if a.action == "build":
        build(a.battery, a.suite)
        return 0
    bad = Battery(a.battery).verify()
    print("battery OK" if not bad else "\n".join(bad))
    return 0 if not bad else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m auditkit", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, method=True):
        if method:
            p.add_argument("method", help="the method file (defines cluster(X, seed, n_clusters=None))")
        p.add_argument("--battery", default=DEFAULT_BATTERY)
        return p

    p = common(sub.add_parser("check", help="pre-audit"))
    p.add_argument("--jobs", type=int, default=4, help="workers assumed for the time projection")
    p.add_argument("--limit-minutes", type=float, default=300)
    p.add_argument("--report", help="write the report as JSON")
    p.set_defaults(func=cmd_check)

    for name, fn in (("label", cmd_label), ("audit", cmd_audit)):
        p = common(sub.add_parser(name, help="run the method on the battery" + (" and score it" if name == "audit" else "")))
        p.add_argument("--out", required=True)
        p.add_argument("--jobs", type=int, default=0, help="worker processes (default: all CPUs)")
        p.add_argument("--threads", type=int, default=1, help="BLAS/OpenMP threads per worker")
        p.add_argument("--timeout", type=float, default=600, help="seconds per dataset")
        if name == "label":
            p.add_argument("--groups", nargs="*", help="restrict to some groups (testing only)")
        else:
            p.add_argument("--labels", help="where to keep the labels (default: next to --out)")
            p.add_argument("--id"); p.add_argument("--reference", action="store_true")
        p.set_defaults(func=fn)

    p = common(sub.add_parser("score", help="score a labels file (never imports the method)"), method=False)
    p.add_argument("labels"); p.add_argument("--method", required=True, help="method file, read as text only")
    p.add_argument("--id"); p.add_argument("--out", required=True); p.add_argument("--reference", action="store_true")
    p.set_defaults(func=cmd_score)

    p = sub.add_parser("show", help="print an audit card"); p.add_argument("audit"); p.set_defaults(func=cmd_show)

    p = sub.add_parser("publish", help="add an audit to the static site")
    p.add_argument("audit"); p.add_argument("--site", default="docs")
    p.add_argument("--method-file"); p.add_argument("--issue", type=int)
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("from-issue", help="extract a submission from a GitHub issue body")
    p.add_argument("--body-file"); p.add_argument("--body-env", default="ISSUE_BODY")
    p.add_argument("--number", type=int); p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_from_issue)

    p = sub.add_parser("requirements", help="extra packages a method needs")
    p.add_argument("method"); p.set_defaults(func=cmd_requirements)

    p = sub.add_parser("battery", help="build or verify the battery")
    p.add_argument("action", choices=["build", "verify"]); p.add_argument("--battery", default=DEFAULT_BATTERY)
    p.add_argument("--suite", help="datasets/suite of the clustaudit 2.2.0 release (build only)")
    p.set_defaults(func=cmd_battery)

    a = ap.parse_args(argv)
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
