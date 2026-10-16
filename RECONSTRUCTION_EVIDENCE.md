# RECONSTRUCTION EVIDENCE FILE — 2026-10-17

**Branch:** `recovery/reconstructed-ci-hardening-20261017`
**Status:** RECONSTRUCTION — NOT the recovered original branch.

This file is the evidence backbone for the reconstructed recovery
branch. It records what was expected, what was verified, what was
lost, what informed the reconstruction, and which choices are
evidence-based versus decisions that still require human ratification.

---

## 1. Expected original work (UNAVAILABLE — never recovered)

| Item | Expected value | Verified status |
|---|---|---|
| Original branch | `fix/ci-triggers-and-audit-hardening-20261016` | **NOT PRESENT** — not on the remote (full `git ls-remote` 2026-10-16T20:30:28Z lists 12 heads; none match), never pushed from the original environment |
| Original HEAD | `047f140797a86241882fa897e3269619d42e900e` | **OBJECT MISSING** — absent from every accessible Git object store; exists in no remote ref |
| Original history | 7 commits on top of the base | **UNAVAILABLE** — no SHAs, messages, authorship, diffs or ancestry survive |
| Original base | `6d2f84d598fbb342558f5a5df7845eb19b30f969` | **VERIFIED — and it is the current remote `main` tip** (zero base deviation) |
| 464 unstaged file-mode changes | reported from the lost worktree | **UNRECOVERABLE** — working-tree state is not a Git object; nothing was committed, so nothing survives anywhere |

Per the operating mission: **no claim is made that the original branch
or its seven commits were recovered.** Nothing here is presented as
the original work. Commit dates and authorship on this branch are the
reconstruction's own (no fabricated historical timestamps, authors,
SHAs or ancestry).

## 2. Verified baseline (trustworthy)

- Remote: `https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine`
  (verified by `git ls-remote` against this exact URL; anonymous.
  REST identity call was rate-limited (0/60 shared egress), so identity
  is attested by content instead:)
- **Identity attestation:** codeload tarball of `6d2f84d…` re-downloaded
  2026-10-16T20:31:15Z → SHA-256
  `535d0e3734a5dff47d5bbf3f9a156e6080cfcc5018130d0aff9cb48e1eeafa36`
  — byte-exact match with the independently recorded provenance of the
  previously audited snapshot of the same commit.
- Baseline branch: `main` @ `6d2f84d598fbb342558f5a5df7845eb19b30f969`
  (98 commits, 0 tags, clean working tree, single worktree).
- The exact historical base IS available and IS the remote default
  branch tip → **no base deviation to record.**
- Pre-existing remote branches (owner's work; untouched by this branch):
  `audit/batch-23-release-readiness-review`, `audit/batch-8-independent-runtime-audit`,
  `feat/broker-neutral-execution-architecture`, `feat/master-market-data-import`,
  `feat/runtime-risk-broker-neutral-tenancy`, `fix/audit-export-command`,
  `fix/ingestion-classification-fail-closed`,
  `fix/manual-dependency-audit-trigger-20261014`,
  `fix/paper-runtime-killswitch-fill-enforcement`,
  `fix/paper-runtime-pnl-correctness`, `phase-4a/4a1-architecture-correction`,
  `phase-4a/4a1-temporal-foundation`.

## 3. Surviving records that informed this reconstruction

1. **M1 Gap Register v1 (G-01…G-05)** — a read-only audit performed at
   base `6d2f84d…`, with file:line evidence. Because the reconstruction
   base IS that exact commit, every finding was re-verified against the
   current tree before implementation (see §4). Findings are current
   facts for this tree, not stale historical claims.
2. **Policy directions D-1…D-8** — accepted provisionally for planning.
   Treated as implementation guidance, never as proof the changes
   already existed.
3. **Remote sibling branch `fix/manual-dependency-audit-trigger-20261014`**
   (3 commits, ci.yml-only, NOT an ancestor of main): documents the
   intended CI-trigger hardening direction ("enable manual dependency
   audit", "correct dependency audit export flag", "exclude editable
   project entry and audit dev extra"). Its substance was re-landed on
   main via PR #5 (`fix/audit-export-command`) + the manual-audit enable
   commit; the branch itself is untouched owner work.
4. **Repository batch history (B14–B23 commit messages)** — e.g. Batch 17
   introduced the opt-in `audit-dependencies` job; Batch 18 recorded the
   package-version mismatch as a deferred LOW finding; Batch 19 shipped
   the deployment templates + fail-closed validator.

## 4. Re-verification of the audit findings on THIS tree (all CONFIRMED)

| Finding | Current-tree evidence (re-verified 2026-10-16) |
|---|---|
| G-01: Master CSVs `REAL_UNVERIFIED`×3, `Metals INVALID`, source approval UNKNOWN | `data/manifests/master/master_import_summary.json` (datasets[].data_state; provenance_status line) — unchanged |
| G-01: 7 export CSVs + workbook + dashboard snapshot absent from manifest/DatasetState inventory | `data/exports/csv/*.csv` (7), `ai_trading_lab_workbook.xlsx`, `dashboard_snapshot.json`; no manifest anywhere covers `data/exports/` |
| G-02: validator implemented, 0 tests, not in CI | `scripts/validate_deployment_templates.py` (178 lines, fail-closed); no `test_*validate_deployment*` in `tests/`; not invoked by `.github/workflows/ci.yml` |
| G-03: systemd ExecStart bare module vs finite CLI | `deploy/systemd/ai-trading-lab@.service` L49 `-m data_engine.cli`; `src/data_engine/cli.py` has exactly 5 finite subcommands, no `run`/`serve`; no-arg → help + exit 0 |
| G-03/D-5: dashboard never wired to any entrypoint | `DashboardServer` (loopback-default, `platform/dashboard.py` L500+) referenced only by `platform/`, `tenancy/` — never by CLI/runtime |
| G-04: no runtime order-rate / max-open-order control | `runtime/risk_gate.py` `MANDATORY_CHECKS` (22 checks, none rate/open-order); `RiskContext` has no such fields; venue-side emulation only (`brokers/capabilities.py` `max_orders_per_window=5` profiles; authoritative paper venue uncapped) |
| G-05: dependency audit opt-in-only, unpinned tool, evidence destroyed | `ci.yml` L93 `if: github.event_name == 'workflow_dispatch'`; L109 `pip install pip-audit` (unpinned); L117 `rm -f requirements-audit.txt`; no artifact upload; no schedule |
| §6: package version mismatch | `pyproject.toml` `version = "0.1.0"` + `uv.lock` root `0.1.0` vs `src/data_engine/__init__.py` `__version__ = "0.3.0"` (Batch 18 deferred LOW finding) |
| §6: `MASTER_DOCUMENTATION_INDEX.md` "v2.28.0" | file IS tracked at repo root; its version is the documentation-series index version — a distinct series, not the package version (category distinction documented, not treated as a defect) |

## 5. Implementation choices: evidence-based vs. decision-requiring

**Evidence-based (surviving records justify them):**
- D-1/D-2: export inventory manifest + DERIVED marking + fail-closed
  consistency tests (pattern follows the repo's own committed-manifest
  and artifact-pin test conventions; classifications unchanged — no
  dataset is promoted, `REAL_VERIFIED` remains unreachable).
- D-3: validator tests + CI integration (validator exists, is
  deterministic, offline-runnable; tests are synthetic + secret-free).
- D-4: explicit `serve` subcommand + systemd ExecStart update (fixes the
  documented G-03 mismatch; fail-closed startup against the readiness
  gate — the service REFUSES to run while `PAPER_READY = FALSE`, which
  is the repo's own documented posture).
- D-5: loopback-only enforcement at the entrypoint (dashboard module
  already defaults to loopback; the entrypoint now refuses non-loopback
  binds outright — remote exposure stays an operator infrastructure
  decision requiring TLS/auth that is deliberately not built).
- D-7: scheduled + manual audit runs, pinned audit tool, retained
  machine-readable evidence, lockfile digest, INCONCLUSIVE-vs-clean
  distinction (implements the G-05 acceptance criteria; PR-blocking
  policy left bit-for-bit unchanged).
- §6: version alignment + a consistency pin test (corrects the Batch 18
  deferred LOW finding in the conservative direction: the code's
  self-reported `0.3.0` becomes the single version; pyproject + lock
  follow).

**Decision-requiring (operator ratification still needed):**
- **D-6 numeric limits.** `max_orders_per_window = 5` and
  `window_seconds = 60.0` mirror the repository's own venue-capability
  emulation defaults (existing design values). `max_open_orders = 10`
  has **no prior design value anywhere** — it is a deliberately
  conservative PAPER-MODE provisional default, loudly marked as
  requiring operator review; it is configurable per-runtime and
  strictly validated. None of these numbers is a production limit;
  none is approved for any real-money context (live trading remains
  unauthorized and structurally refused).
- D-6 semantics: rate/open-order checks throttle NEW exposure;
  risk-reducing (closing) orders are exempt — mirroring the existing
  kill-switch/drawdown carve-out discipline.
- Whether the reconstructed changes match what the original seven
  commits actually did — unknowable; the original diffs are lost.

## 6. Explicit non-goals (unchanged from the mission)

- No claim of recovered original history; no reuse of the original
  branch name; no substitute commits presented as the originals.
- No direct changes to `main`; no force-push; no PR/merge without
  separate authorization.
- No live trading, no real broker connection, no real orders.
- No fabricated test/CI/source-approval/production-readiness claims;
  readiness stays fail-closed wherever evidence is missing.
