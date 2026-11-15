"""
Submissions through a GitHub issue form
=======================================

The form ``.github/ISSUE_TEMPLATE/audit.yml`` renders its answers as Markdown::

    ### Method name

    my-kmeans

    ### Family

    Centroid
    ...
    ### Method code

    ```python
    def cluster(X, seed, n_clusters=None): ...
    ```

``parse_issue`` reads that text back (the field labels below must match the form);
``write_submission`` writes ``method.py`` with a normalised header, the header being
taken from the form fields (they override any header in the code).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, Optional

from .method import FAMILIES, _REQ, slug

LABELS = {
    "name": "Method name",
    "family": "Family",
    "needs_k": "Does the method need the number of clusters?",
    "requirements": "Extra Python packages (optional)",
    "code": "Method code",
    "reference": "Reference (optional)",
    "consent": "Publication",
}
MAX_CODE = 60_000


class SubmissionError(ValueError):
    pass


def _sections(body: str) -> Dict[str, str]:
    out, cur, buf = {}, None, []
    for line in body.replace("\r\n", "\n").split("\n"):
        m = re.match(r"^###\s+(.*?)\s*$", line)
        if m and m.group(1) in LABELS.values():
            if cur is not None:
                out[cur] = "\n".join(buf).strip()
            cur, buf = m.group(1), []
        elif cur is not None:
            buf.append(line)
    if cur is not None:
        out[cur] = "\n".join(buf).strip()
    return out


def _strip_fence(text: str) -> str:
    t = text.strip()
    m = re.match(r"^```[a-zA-Z]*\n(.*?)\n?```\s*$", t, re.S)
    return m.group(1) if m else t


def parse_issue(body: str) -> Dict:
    s = _sections(body or "")
    get = lambda k: "" if s.get(LABELS[k], "").strip() == "_No response_" else s.get(LABELS[k], "").strip()
    # letters, digits and a few separators only: the name ends up in comments, file names and pages
    name = re.sub(r"[^\w .,+()/-]", "", re.sub(r"\s+", " ", get("name")))[:60].strip()
    if not name:
        raise SubmissionError("the method name is missing")
    code = _strip_fence(get("code"))
    if "def cluster" not in code:
        raise SubmissionError("the code must define `def cluster(X, seed, n_clusters=None)`")
    if len(code) > MAX_CODE:
        raise SubmissionError(f"the code is longer than {MAX_CODE} characters")
    fam = get("family").strip()
    reqs = get("requirements").replace(",", " ").split()
    m = re.search(r"^\s*#\s*requirements\s*:\s*(.*)$", code, re.I | re.M)   # a header in the code counts too
    for r in (m.group(1).replace(",", " ").split() if m else []):
        if r not in reqs:
            reqs.append(r)
    bad = [r for r in reqs if not _REQ.match(r)]
    if bad:
        raise SubmissionError(f"requirements not accepted (name and version bounds only): {bad}")
    consent = get("consent")
    if not re.search(r"-\s*\[[xX]\]", consent):
        raise SubmissionError("the publication box is not ticked")
    return {"name": name, "slug": slug(name), "family": fam if fam in FAMILIES else "Other",
            "needs_k": get("needs_k").lower().startswith("yes"), "requirements": reqs,
            "reference": re.sub(r"\s+", " ", get("reference"))[:300], "code": code}


def method_source(sub: Dict) -> str:
    # the form fields win: header lines already in the code are dropped
    code = "\n".join(l for l in sub["code"].split("\n")
                     if not re.match(r"^\s*#\s*(name|family|needs-k|needs_k|requirements|reference)\s*:", l, re.I))
    head = [f"# name: {sub['name']}", f"# family: {sub['family']}",
            f"# needs-k: {'yes' if sub['needs_k'] else 'no'}"]
    if sub["requirements"]:
        head.append(f"# requirements: {' '.join(sub['requirements'])}")
    if sub["reference"]:
        head.append(f"# reference: {sub['reference']}")
    return "\n".join(head) + "\n" + code.strip("\n") + "\n"


def audit_id(sub: Dict, issue: Optional[int]) -> str:
    return f"{sub['slug']}-{issue}" if issue else sub["slug"]


def write_submission(sub: Dict, out: str, issue: Optional[int] = None) -> Path:
    o = Path(out)
    o.mkdir(parents=True, exist_ok=True)
    (o / "method.py").write_text(method_source(sub), encoding="utf-8")
    meta = {k: v for k, v in sub.items() if k != "code"}
    meta.update(issue=issue, id=audit_id(sub, issue))
    (o / "submission.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return o
