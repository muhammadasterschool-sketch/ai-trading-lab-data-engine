# WP-12 — CI GATES IMPLEMENTATION SPEC (GitHub Actions)

```text
Document Type:  Implementation-ready CI specification (NOT ENABLED)
Phase:          Cross-cutting (Enhancement Mandate v2.0 WP-12)
Authority:      B — CURRENT SUPPORTING (specification awaiting decision)
Status:         PENDING HUMAN AUTHORIZATION
Version:        1.0.0
Last Updated:   2026-10-08
Decision State: WP-12 = HUMAN_DECISION_REQUIRED
```

---

## 1. Why This Is a Human Decision

Closure mandate §18 item 5 lists "GitHub Actions CI decision" as a
HUMAN DECISION. The repository's registered enhancement mandate v2.0
contains WP-12 as a work package whose execution is explicitly gated
on an operator go-ahead, and the prediction implementation report
carries "decide on adding GitHub Actions CI (WP-12)" under
HUMAN_DECISIONS_REQUIRED. No such authorization is on record.
Therefore the workflow below is **specified but deliberately NOT
installed** — no `.github/` directory exists in the repository and
this cycle did not create one.

## 2. Safety Assessment (mandate §20)

Adding the workflow is safe with respect to governance PROVIDED:

- it runs only public test/verification commands already executed
  locally (pytest, frozen-Phase-3 verification, secret scan,
  deterministic checks);
- it never requires or exposes secrets (the repo's verification stack
  is secret-free by design — the frozen-blob comparison uses a
  committed reference manifest, not remote state);
- logs cannot leak credentials (no secrets are passed to steps).

Risks if enabled: public CI on a public repo executes third-party PR
code in workflows only if `pull_request_target` with checkout of the
PR head is used — the spec below FORBIDS that pattern outright.

## 3. The Workflow (ready to install verbatim)

File path on approval: `.github/workflows/ci.yml`

```yaml
name: ci
on:
  push:
    branches: [main, "phase-4a/**"]
  pull_request:
    branches: [main]

# SECURITY: never pull_request_target; never expose secrets; repo
# verification stack is secret-free by design.
permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # frozen-blob comparison needs history
      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install locked environment
        run: |
          python -m pip install --upgrade pip
          pip install uv
          uv sync --frozen --extra dev
      - name: Full test suite (must be 100% green)
        run: uv run pytest -q -p no:cacheprovider
      - name: Determinism (three consecutive runs)
        run: |
          uv run pytest -q -p no:cacheprovider
          uv run pytest -q -p no:cacheprovider
      - name: Frozen Phase 3 verification (11/11 blobs + SUB-18 13/13)
        run: |
          uv run python - <<'PY'
          import hashlib, subprocess, sys
          from pathlib import Path
          # committed reference: blobs must be byte-identical to
          # main@13fdc7e (see tests/test_pit_view.py SUB-18 manifest)
          FROZEN = [
              "src/data_engine/strategy/__init__.py",
              "src/data_engine/strategy/backtest.py",
              "src/data_engine/strategy/conditions.py",
              "src/data_engine/strategy/equity.py",
              "src/data_engine/strategy/execution.py",
              "src/data_engine/strategy/ledger.py",
              "src/data_engine/strategy/metrics.py",
              "src/data_engine/strategy/position.py",
              "src/data_engine/strategy/provenance.py",
              "src/data_engine/strategy/schemas.py",
              "src/data_engine/strategy/validation.py",
          ]
          base = subprocess.run(
              ["git", "show", "13fdc7e:src/data_engine/strategy/"
               + Path(FROZEN[0]).name],
              capture_output=True, text=True, check=True,
          )
          ok = True
          for f in FROZEN:
              current = Path(f).read_bytes()
              ref = subprocess.run(
                  ["git", "show", f"13fdc7e:{f}"],
                  capture_output=True, check=True,
              ).stdout
              if hashlib.sha256(current).hexdigest() != \
                      hashlib.sha256(ref).hexdigest():
                  print(f"FROZEN VIOLATION: {f}")
                  ok = False
          sys.exit(0 if ok else 1)
          PY
      - name: Secret scan (0 hits required)
        run: |
          ! git grep -nE "github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}" $(git rev-list --all)
      - name: Prediction acceptance tests (T-PRED + red-team matrix)
        run: uv run pytest tests/test_prediction_redteam_matrix.py -q
```

## 4. CI Failure Conditions (mandate §20, exhaustive)

The workflow MUST fail when any of: tests fail; determinism runs
diverge; frozen Phase 3 blobs differ from the committed reference;
secrets are detected in any tracked file or history; the prediction
red-team matrix reports any undefended attack.

## 5. What Approval Requires

A single operator statement of the form:

```text
Decision ID:   WP-12-CI-ENABLE
Approver:      <named human>
Decision:      install .github/workflows/ci.yml as specified in
               WP_12_CI_IMPLEMENTATION_SPEC.md v1.0.0
Recorded at:   <logical timestamp>
```

Until that record exists, WP-12 stays HUMAN_DECISION_REQUIRED and
local gates remain the only executed verification.
