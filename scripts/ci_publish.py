#!/usr/bin/env python
"""Trusted side of the Audit workflow: never executes the submitted code.

Reads the submission from the issue body (environment variable ISSUE_BODY) as text,
reads the labels produced by the untrusted job with numpy (no pickle), scores them
against this repository's battery and writes, in --work:

* method.py      the method file, rebuilt from the issue (published next to the card);
* audit.json     the audit card (when the run produced labels for the whole battery);
* comment.md     the comment posted in the issue.

It sets the step outputs ``published`` (true/false) and ``id``.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from auditkit.card_text import render                       # noqa: E402
from auditkit.issue import SubmissionError, audit_id, method_source, parse_issue  # noqa: E402
from auditkit.method import read_info                       # noqa: E402

MAX_LABELS_BYTES = 20 * 1024 * 1024


def safe(text: str, n: int = 300) -> str:
    """Untrusted text for a Markdown comment: no mentions, no HTML, no fences."""
    t = str(text)[:n].replace("`", "'").replace("<", "‹").replace(">", "›")
    return re.sub(r"@(?=\w)", "@​", t)


def output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    lines = [f"{k}={v}" for k, v in kv.items()]
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    print("\n".join(lines))


def check_report(untrusted: Path) -> str:
    p = untrusted / "check.json"
    if not p.exists():
        return ""
    try:
        rep = json.loads(p.read_text(encoding="utf-8")[:200_000])
        rows = []
        for c in rep.get("checks", [])[:12]:
            mark = "✅" if c.get("ok") else ("❌" if c.get("blocking", True) else "⚠️")
            rows.append(f"- {mark} {safe(c.get('label', ''), 80)}" + (f": {safe(c.get('detail', ''), 300)}" if c.get("detail") else ""))
        return "\n".join(rows)
    except Exception:
        return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--number", type=int, required=True)
    ap.add_argument("--run-result", default="")
    ap.add_argument("--run-url", default="")
    ap.add_argument("--repo", default="")
    ap.add_argument("--untrusted", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--battery", default=str(HERE.parent / "battery" / "paper-v2.2"))
    a = ap.parse_args()
    work, untrusted = Path(a.work), Path(a.untrusted)
    work.mkdir(parents=True, exist_ok=True)
    comment = work / "comment.md"
    run_link = f"[workflow run]({a.run_url})" if a.run_url else "workflow run"

    try:
        sub = parse_issue(os.environ.get("ISSUE_BODY", ""))
    except SubmissionError as e:
        comment.write_text(f"The submission could not be read: {safe(e)}.\n\nEdit the issue, then ask a maintainer "
                           f"to add the label `audit` again.", encoding="utf-8")
        output(published="false", id="")
        return 0
    aid = audit_id(sub, a.number)
    (work / "method.py").write_text(method_source(sub), encoding="utf-8")
    info = read_info(work / "method.py")

    labels = untrusted / "labels.npz"
    report = check_report(untrusted)
    if a.run_result != "success" or not labels.exists():
        msg = [f"The audit of **{safe(sub['name'], 60)}** did not complete ({safe(a.run_result or 'no result', 30)}, see the {run_link})."]
        if report:
            msg += ["", "Pre-audit:", "", report]
        msg += ["", "Fix the code (test it on the site, or locally with `python -m auditkit check my_method.py`), "
                    "edit the issue, and ask a maintainer to add the label `audit` again."]
        comment.write_text("\n".join(msg), encoding="utf-8")
        output(published="false", id=aid)
        return 0
    if labels.stat().st_size > MAX_LABELS_BYTES:
        comment.write_text(f"The labels file is larger than expected; audit not scored ({run_link}).", encoding="utf-8")
        output(published="false", id=aid)
        return 0

    from auditkit.score import score
    meta_p = untrusted / "labels.npz.json"
    run_meta = None
    if meta_p.exists() and meta_p.stat().st_size < 200_000:
        try:
            run_meta = json.loads(meta_p.read_text(encoding="utf-8"))
            run_meta = {k: run_meta.get(k) for k in ("wall_time_s", "jobs", "timeout_s", "environment")}
            if not isinstance(run_meta.get("wall_time_s"), (int, float)):
                run_meta["wall_time_s"] = None
        except Exception:
            run_meta = None
    try:
        audit = score(a.battery, str(labels), info, aid, run_meta=run_meta, reference=False,
                      extra={"issue": a.number})
    except Exception as e:
        comment.write_text(f"The labels could not be scored: {safe(e)} ({run_link}).", encoding="utf-8")
        output(published="false", id=aid)
        return 0
    (work / "audit.json").write_text(json.dumps(audit, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    owner, _, repo = a.repo.partition("/")
    site = f"https://{owner}.github.io/{repo}/" if owner and repo else ""
    body = [f"## Audit card: {safe(sub['name'], 60)}", "", render(audit, markdown=True).replace("@", "@​"), ""]
    if site:
        body += [f"Card page: {site}audit.html?id={aid} (online once the site has been redeployed, about a minute).",
                 "", "Badge for your README:", "", "```markdown",
                 f"[![audited by clustaudit]({site}badge/{aid}.svg)]({site}audit.html?id={aid})", "```", ""]
    body += [f"Battery {audit['battery']['name']}, scored with clustaudit {audit['scoring']['clustaudit']} ({run_link})."]
    comment.write_text("\n".join(body), encoding="utf-8")
    output(published="true", id=aid)
    return 0


if __name__ == "__main__":
    sys.exit(main())
