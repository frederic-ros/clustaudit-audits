"""Tests of auditkit: battery, method contract, runs that fail, scoring, publication, the
issue pipeline, and the reproduction of the published reference cards."""
import json
import os
import re
import subprocess
import sys
import xml.dom.minidom
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from auditkit.battery import Battery, GROUPS                       # noqa: E402
from auditkit.issue import SubmissionError, method_source, parse_issue  # noqa: E402
from auditkit.label import read_labels, run_labels                 # noqa: E402
from auditkit.method import InvalidOutput, as_labels, extra_requirements, read_info  # noqa: E402
from auditkit.score import critical, score                         # noqa: E402
from auditkit.site import badge_svg, publish, validate             # noqa: E402

BATTERY = str(ROOT / "battery" / "paper-v2.2")
REF = ROOT / "methods" / "reference"
PUBLISHED = ROOT / "docs" / "audits"

BODY = """### Method name

{name}

### Family

Density

### Does the method need the number of clusters?

{needs}

### Extra Python packages (optional)

_No response_

### Method code

```python
{code}
```

### Reference (optional)

_No response_

### Publication

- [{tick}] I agree that my function and its audit card are published on this site under the MIT licence.
"""
KM_CODE = """# requirements: numpy scikit-learn
def cluster(X, seed, n_clusters=None):
    from sklearn.cluster import KMeans
    return KMeans(n_clusters=n_clusters, n_init=10, random_state=seed).fit_predict(X)"""


def body(name="my method", needs="Yes, give it the true K (protocol F)", code=KM_CODE, tick="X"):
    return BODY.format(name=name, needs=needs, code=code, tick=tick)


@pytest.fixture(scope="session")
def kmeans_labels(tmp_path_factory):
    out = tmp_path_factory.mktemp("km") / "labels.npz"
    run_labels(str(REF / "kmeans.py"), BATTERY, str(out), jobs=2, log=lambda *a: None)
    return out


# ------------------------------------------------------------------ battery and contract
def test_battery_matches_manifest():
    bat = Battery(BATTERY)
    assert len(bat) == 250
    sizes = {g: len(v) for g, v in bat.groups().items()}
    assert sizes == {"suite": 75, "overlap": 35, "anisotropy": 45, "inter_density": 25,
                     "intra_density": 20, "imbalance": 25, "eta_int": 25}
    assert bat.verify() == []
    assert all(e.n == 1000 and e.d == 20 and e.K == 5 for e in bat)


def test_header_and_requirements(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("# name: Toy\n# family: density\n# needs-k: yes\n# requirements: numpy hdbscan==0.8.40\n"
                 "def cluster(X, seed, n_clusters=None):\n    return [0] * len(X)\n")
    info = read_info(f)
    assert (info.name, info.family, info.needs_k) == ("Toy", "Density", True)
    assert extra_requirements(info) == ["hdbscan==0.8.40"]
    for bad in ("--index-url=https://evil", "git+https://x/y", "pkg;rm", "http://x"):
        f.write_text(f"# requirements: {bad}\ndef cluster(X, seed):\n    return 0\n")
        with pytest.raises(ValueError):
            read_info(f)


def test_label_contract():
    assert as_labels([0, 1, -1], 3).tolist() == [0, 1, -1]
    assert as_labels(np.array([0.0, 2.0, 1.0]), 3).dtype == np.int64
    assert as_labels(np.array([[0], [1]]), 2).tolist() == [0, 1]
    for out, n in (([0, 1], 3), ([0.5, 1, 2], 3), ([0, -2, 1], 3), ([True, False], 2),
                   (["a", "b"], 2), (([0, 1], "ok"), 2), ([np.nan, 1], 2)):
        with pytest.raises(InvalidOutput):
            as_labels(out, n)


# ------------------------------------------------------------------ runs that go wrong
def test_every_failure_is_recorded(tmp_path):
    m = tmp_path / "bad.py"
    m.write_text("""# needs-k: yes
import os, time
import numpy as np
def cluster(X, seed, n_clusters=None):
    if seed == 42: raise RuntimeError("boom")
    if seed == 123: time.sleep(30)
    if seed == 456: return np.zeros(3, int)
    if seed == 789: os._exit(1)
    return np.arange(len(X)) % n_clusters
""")
    out = tmp_path / "l.npz"
    meta = run_labels(str(m), BATTERY, str(out), jobs=2, timeout=1.0, groups=["imbalance"], log=lambda *a: None)
    assert meta["n_datasets"] == 25
    assert meta["status_counts"] == {"ok": 5, "error": 5, "timeout": 5, "invalid_output": 5, "crashed": 5}
    lab = read_labels(str(out))
    boom = [v for k, v in lab.items() if k.endswith("_s42")]
    assert all(v["status"] == "error" and "RuntimeError: boom" in v["message"] for v in boom)


def test_import_error_does_not_break_the_run(tmp_path):
    m = tmp_path / "broken.py"
    m.write_text("def cluster(X, seed:\n    pass\n")
    out = tmp_path / "l.npz"
    meta = run_labels(str(m), BATTERY, str(out), jobs=2, groups=["intra_density"], log=lambda *a: None)
    assert meta["status_counts"]["error"] == 20
    assert all("could not be imported" in v["message"] for v in read_labels(str(out)).values())


# ------------------------------------------------------------------ scoring
def test_critical_level_rules():
    lv, seeds = [1.0, 2.0, 3.0], [1, 2]
    always = {(v, s): 0.9 for v in lv for s in seeds}
    assert critical(lv, seeds, always)["text"] == ">max [>max, >max]"
    never = {(v, s): 0.1 for v in lv for s in seeds}
    assert critical(lv, seeds, never)["text"] == "≤1"
    mixed = {(1.0, 1): .9, (2.0, 1): .2, (3.0, 1): .0, (1.0, 2): .9, (2.0, 2): .9, (3.0, 2): .9}
    c = critical(lv, seeds, mixed)
    assert c["text"] == "3 [2, >max]" and c["mean"] == 3.0 and c["seed_max"] == ">max"


@pytest.mark.parametrize("ref", ["kmeans", "dbscan"])
def test_reference_audit_reproduces_the_published_card(ref, tmp_path, kmeans_labels):
    labels = kmeans_labels if ref == "kmeans" else tmp_path / "l.npz"
    if ref != "kmeans":
        run_labels(str(REF / f"{ref}.py"), BATTERY, str(labels), jobs=2, log=lambda *a: None)
    a = score(BATTERY, str(labels), read_info(REF / f"{ref}.py"), ref, reference=True)
    pub = json.loads((PUBLISHED / f"{ref}.json").read_text(encoding="utf-8"))
    assert a["card"]["row"] == pub["card"]["row"]
    got = {r[0]: r[1] for r in a["rows"]["data"]}
    want = {r[0]: r[1] for r in pub["rows"]["data"]}
    assert got.keys() == want.keys()
    assert max(abs(got[k] - want[k]) for k in got) < 1e-6


def test_paper_table8_rows_are_published():
    # Table 8 of the paper, protocol F (DPC: the paper did not run the anisotropy sweep)
    t8 = {"kmeans": ["1 [0.8, 1]", "8 [5, >max]", ">max [0.75, >max]", "0.04 / 1.00", "0.89 / 0.06", "silent (1.00)"],
          "hdbscan": ["0.4 [0.2, 0.4]", "3 [1, 3]", ">max [0, >max]", "1.00 / 0.34", "0.97 / 0.39", "detectable (1.00)"],
          "average": ["≤0.2", "≤1", "≤0", "0.00 / 0.97", "0.00 / 0.02", "silent (1.00)"],
          "optics": ["0.2 [0.2, 0.4]", "1.5 [1, 1.5]", "0 [0, 0.25]", "0.91 / 0.00", "0.46 / 0.54", "detectable (1.00)"]}
    for k, row in t8.items():
        assert json.loads((PUBLISHED / f"{k}.json").read_text(encoding="utf-8"))["card"]["row"] == row


def test_scoring_never_imports_the_method(tmp_path, kmeans_labels):
    sentinel = tmp_path / "imported"
    m = tmp_path / "evil.py"
    m.write_text(f"# needs-k: yes\nopen({str(sentinel)!r}, 'w').write('x')\ndef cluster(X, seed, n_clusters=None):\n    return 0\n")
    score(BATTERY, str(kmeans_labels), read_info(m), "evil")
    assert not sentinel.exists()


def test_incomplete_labels_are_refused(tmp_path):
    out = tmp_path / "l.npz"
    run_labels(str(REF / "kmeans.py"), BATTERY, str(out), jobs=1, groups=["imbalance"], log=lambda *a: None)
    with pytest.raises(ValueError, match="does not cover the battery"):
        score(BATTERY, str(out), read_info(REF / "kmeans.py"), "x")


# ------------------------------------------------------------------ issue pipeline and site
def test_issue_parsing():
    sub = parse_issue(body(name="My <b>method</b> @bob"))
    assert sub["name"] == "My bmethod/b bob" and sub["slug"] == "my-bmethod-b-bob"
    assert sub["needs_k"] and sub["requirements"] == ["numpy", "scikit-learn"]
    src = method_source(sub)
    assert src.startswith("# name: My bmethod/b bob\n# family: Density\n# needs-k: yes\n# requirements: numpy scikit-learn\n")
    assert src.count("# requirements") == 1 and "def cluster" in src
    assert not parse_issue(body(needs="No, it chooses K itself"))["needs_k"]
    with pytest.raises(SubmissionError, match="not ticked"):
        parse_issue(body(tick=" "))
    with pytest.raises(SubmissionError, match="def cluster"):
        parse_issue(body(code="print(1)"))
    with pytest.raises(SubmissionError, match="name"):
        parse_issue(body(name="_No response_"))


def test_publish_builds_index_and_badge(tmp_path, kmeans_labels):
    a = score(BATTERY, str(kmeans_labels), read_info(REF / "kmeans.py"), "my-km-3")
    p = tmp_path / "a.json"
    p.write_text(json.dumps(a), encoding="utf-8")
    publish(str(p), str(tmp_path / "site"), method_file=str(REF / "kmeans.py"), issue=3)
    idx = json.loads((tmp_path / "site" / "audits" / "index.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in idx["audits"]] == ["my-km-3"] and idx["audits"][0]["issue"] == 3
    xml.dom.minidom.parseString((tmp_path / "site" / "badge" / "my-km-3.svg").read_text(encoding="utf-8"))
    assert (tmp_path / "site" / "methods" / "my-km-3.py").exists()
    bad = dict(a, id="../x")
    assert validate(bad)
    assert "<script" not in badge_svg(dict(a, card=dict(a["card"], sigma_crit={"text": "<script>"})))


def _ci(tmp_path, issue_body, run_result, untrusted):
    env = dict(os.environ, ISSUE_BODY=issue_body, GITHUB_OUTPUT=str(tmp_path / "out.txt"))
    subprocess.run([sys.executable, str(ROOT / "scripts" / "ci_publish.py"), "--number", "7", "--run-result", run_result,
                    "--run-url", "https://example.invalid/run", "--repo", "owner/clustaudit-audits",
                    "--untrusted", str(untrusted), "--work", str(tmp_path / "work")], check=True, env=env, cwd=ROOT)
    out = dict(l.split("=", 1) for l in (tmp_path / "out.txt").read_text().split())
    return out, (tmp_path / "work" / "comment.md").read_text(encoding="utf-8")


def test_trusted_job_end_to_end(tmp_path, kmeans_labels):
    untrusted = tmp_path / "untrusted"
    untrusted.mkdir()
    (untrusted / "labels.npz").write_bytes(Path(kmeans_labels).read_bytes())
    out, comment = _ci(tmp_path, body(name="KM @alice"), "success", untrusted)
    assert out == {"published": "true", "id": "km-alice-7"}
    assert "@alice" not in comment and "| 1 [0.8, 1] |" in comment
    a = json.loads((tmp_path / "work" / "audit.json").read_text(encoding="utf-8"))
    assert a["issue"] == 7 and not a["method"]["reference_audit"] and validate(a) == []
    # a failed run is reported, with the pre-audit, and nothing is published
    (untrusted / "check.json").write_text(json.dumps({"checks": [{"label": "Imports", "ok": False, "blocking": True,
                                                                  "detail": "SyntaxError `x` <img> @eve"}]}))
    out, comment = _ci(tmp_path / "f", body(), "failure", untrusted)
    assert out["published"] == "false" and "did not complete" in comment
    assert "<img>" not in comment and "@eve" not in comment and "`x`" not in comment
    out, comment = _ci(tmp_path / "g", body(tick=" "), "success", untrusted)
    assert out["published"] == "false" and "not ticked" in comment


# ------------------------------------------------------------------ the in-browser quick test
def test_browser_quick_test_harness():
    src = (ROOT / "docs" / "assets" / "qt-worker.js").read_text(encoding="utf-8")
    ns = {}
    exec(re.search(r"const HARNESS = `(.*?)`;", src, re.S).group(1), ns)
    data = (ROOT / "docs" / "data" / "quicktest.json").read_text(encoding="utf-8")
    res = json.loads(ns["quicktest"](KM_CODE.replace("n_clusters=n_clusters", "n_clusters=n_clusters or 5"), data, True))
    assert all(c["ok"] for c in res["checks"])
    assert [round(p["ari"], 2) for p in res["panels"]] == [1.0, 0.72, 0.48]
    res = json.loads(ns["quicktest"]("def cluster(X, seed):\n    raise ValueError('no')", data, False))
    assert [c["ok"] for c in res["checks"]] == [True, False] and "line 2" in res["checks"][1]["detail"]
