# clustaudit audits

Audit cards for clustering algorithms, on the battery of the paper

> F. Ros, R. Riad, Y. Nasser. *Interventional Auditing of Clustering Algorithms: Controlled
> Difficulty Sweeps Beyond Benchmarking* (submitted). Software: clustaudit 2.2.0,
> [doi:10.5281/zenodo.24239816](https://doi.org/10.5281/zenodo.24239816).

A ranking says which method scored best. An audit card says where a method breaks (the
critical level of each factor, with its range over seeds), how noise placement and size
imbalance affect it, and whether it fails **silently** (a well-formed but wrong partition)
or **detectably** (a degenerate output a user can see).

This repository holds:

* `auditkit/`: the audit engine, a thin layer over clustaudit 2.2.0;
* `battery/paper-v2.2/`: the frozen battery, 250 datasets (1000 points, 20 dimensions, 5 clusters);
* `methods/reference/`: the nine classical methods of the paper, written as ordinary submissions;
* `docs/`: the static site (GitHub Pages): gallery, audit cards, in-browser quick test;
* `.github/`: the submission form (an issue form) and the workflows that run and publish audits.

No server: the site is static, audits run on GitHub Actions.

## Audit a method on your machine

```bash
git clone https://github.com/frederic-ros/clustaudit-audits.git
cd clustaudit-audits
pip install -r requirements.txt          # Python 3.12 or 3.13
python -m auditkit check my_method.py    # pre-audit, a few seconds
python -m auditkit audit my_method.py --out my_method.audit.json
python -m auditkit show my_method.audit.json
```

`my_method.py` defines one function:

```python
# name: My method
# family: Density          (Centroid | Connectivity | Density | Graph | Deep | Other)
# needs-k: no              (yes: the method receives the true number of clusters, protocol F)
# requirements: numpy scikit-learn

def cluster(X, seed, n_clusters=None):
    """X: array (n, d). Return one integer label per row; -1 = point left unassigned.
    Use `seed` for every random choice."""
    ...
```

The audit runs the function on the 250 datasets in worker processes (all CPUs by default,
`--jobs`), with a time limit per dataset (`--timeout`, 600 s). No run is dropped: a run
that raises, exceeds the limit, returns an invalid output or kills its process is
recorded as an error and counts as ARI 0. The nine reference methods take 5 to 80 seconds
each on two cores.

## The battery and the card

| group | levels (five seeds each) | operating point |
|---|---|---|
| suite | 75 datasets: easy, medium, hard x 5 variants | clustaudit `datasets/suite` |
| overlap | σ = 0.2 … 1.4 | sweep base of clustaudit 2.2 |
| anisotropy | α = 1 … 10 (range α, α + 0.5) | base of the paper's anisotropy experiment |
| inter_density | δ = 0 … 1 | sweep base |
| intra_density | 0 … 2 (dense cores) | sweep base |
| imbalance | ρ = 1 … 5 | sweep base |
| eta_int | 0 … 1, total noise η = 0.3 | sweep base, η = 0.3 |

The card follows the rules of the paper's Table 8 (`auditkit/score.py`): the critical
level is the first level where the mean inlier ARI over the five seeds falls below 0.5,
reported with the range of the per-seed levels; noise placement is the mean ARI with all
the noise distant and all of it between clusters; imbalance is the ARI and the
smallest-cluster F1 at ρ = 5; the failure mode is the most frequent one at the largest
overlap. Runs are evaluated with clustaudit's own `evaluate_run`.

**Reproduction of the paper.** The reference methods, run by auditkit as submissions,
give the paper's results run by run: 2,205 runs compared, identical ARI (up to the
6-decimal rounding of `audit.json`) and identical failure mode, and the nine cards equal
Table 8 (DPC, which the paper did not run on the anisotropy sweep, gets an α value here).

```bash
python scripts/reference_audits.py --jobs 4      # rebuild docs/audits for the nine methods
python scripts/compare_with_paper.py --results ../clustaudit/benchmarks/classical/results
python -m pytest -q tests                        # 15 tests, about one minute
```

## The public service

1. **Quick test** (`docs/test.html`): the visitor's code runs in the browser (Pyodide, in a
   Web Worker) on three small 2-D datasets; nothing is uploaded.
2. **Submission**: the page opens a prefilled GitHub issue (form `.github/ISSUE_TEMPLATE/audit.yml`).
3. **Review**: a maintainer reads the code and adds the label `audit`.
4. **Run** (`.github/workflows/audit.yml`, job `run`): the method runs on the battery in a
   job with no token permission, no secret and no credentials; its only output is an
   artifact of labels.
5. **Scoring and publication** (job `publish`): this job never executes the submitted code.
   It rebuilds the method file from the issue text, reads the labels with numpy (no
   pickle), scores them against its own copy of the battery, commits
   `docs/audits/<id>.json`, the badge and the method file, comments the card in the issue
   and redeploys the site.

Keep the workflows free of caches (`actions/cache`, `cache:` in `setup-python`): code run
in the untrusted job could otherwise poison a cache restored by a trusted job.

### Setting up the repository (once)

1. Create a **public** repository (Actions minutes and Pages are free for public
   repositories), for example `clustaudit-audits`, and push this folder to `main`.
2. *Settings → Pages → Build and deployment → Source*: **GitHub Actions**.
3. *Issues → Labels*: create the labels `audit` (starts a run) and `audit-request`
   (added by the form).
4. *Actions → Pages → Run workflow* once: the site goes online at
   `https://<owner>.github.io/<repo>/`.
5. `docs/config.json` holds the repository name, the public address of the site
   (`site_url`, used in the issue comments and badges; with a custom domain on the
   account, project sites are served under it, e.g. `https://frederic-ros.com/clustaudit-audits/`)
   and the Pyodide version.

### Running an audit (maintainers)

Open the issue, read the code as it is at that moment, add the label `audit`. The run
takes a few minutes; the card is commented in the issue and appears in the gallery. To
run it again (after the author edited the issue), remove the label and add it again.

## Layout

```
auditkit/        battery.py  method.py  check.py  label.py  score.py  card_text.py  site.py  issue.py  __main__.py
battery/         paper-v2.2/manifest.json + 250 .npz (content SHA-256 in the manifest)
methods/         reference/*.py (K-Means, GMM, Spectral, Ward, Average, DBSCAN, HDBSCAN, OPTICS, Density peaks)
docs/            index.html  test.html  audit.html  assets/  audits/  badge/  methods/  data/quicktest.json  config.json
scripts/         reference_audits.py  compare_with_paper.py  ci_publish.py  build_quicktest.py
tests/           test_auditkit.py
```

The battery is rebuilt with `python -m auditkit battery build --suite <clustaudit>/datasets/suite`
(it needs clustaudit 2.2.0, which holds the generator); `python -m auditkit battery verify`
checks every file against the manifest.

MIT licence.
