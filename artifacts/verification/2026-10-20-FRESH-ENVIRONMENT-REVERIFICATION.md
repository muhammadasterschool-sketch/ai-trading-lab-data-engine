# Fresh-Environment Re-Verification Record — 2026-10-20

Independent re-verification of the final Milestone A tree from a CLEAN
environment (no prior local checkout, venv, worklog, or cached state) —
the strongest form of the repo's "verify, never re-assume" rule.
Performed by a continuation session after all implementation stages
(A–G, P1–P9) and the post-final hardening supplement (FIX-7/FIX-8)
were pushed, merged, and released.

## 1. Environment

- Date: 2026-10-20 (UTC). Fresh sandbox: no pre-existing
  `audit-work/repo` checkout, no prior `.venv`, no worklog carried
  over from earlier sessions.
- Anonymous `git clone` of the public URL (no credentials in any git
  config; authenticated operations used one-time inline URLs only).
- uv 0.13.0; `uv sync --extra dev` resolved Python 3.12.15 (CI runs
  an identical 3.12 job green; the package floor is >=3.11).

## 2. Repository identity (CONFIRMED)

- Remote: https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine
- `main` HEAD: `ac06f2b0f66ea13aaf357cd8e4b66b0b95563f5e`
  ("docs(final): CHANGELOG/FIX-LOG/PROJECT-STATE-REPORT supplement +
  FIX-7/FIX-8 records", 2026-10-19 20:58:51 +0000). Working tree
  clean after sync.
- Tags: `v0.3.0` and `apk-bab12c7aa768`, both resolving to
  `bab12c7aa76864575afcb323b96e5b26dcc29aad`.
- PR ledger: #1–#6 plus #7 (Stage B) and #8 (Stage C) merged; #9, #10,
  #11 closed with their content landed on `main` via direct merges
  (b764e35 Stage D, 3e57704 Stage E, ddb4a2b Stage F, 07514ac Stage G,
  0906279 supplement) — all verified present in `main` first-parent
  history.
- Stale-branch note: `fix/manual-dependency-audit-trigger-20261014`
  retains 3 pre-squash commits not reachable from `main`; PR #4 is
  merged and its content (the `audit-dependencies` CI job) is present
  and green at `main` HEAD. The branch is left intact as history
  evidence.

## 3. Full test suite (CONFIRMED — matches documented 2735+1)

Command:

```
env -u VIRTUAL_ENV -u UV_PYTHON .venv/bin/python -m pytest tests/ -q --no-header
```

Result: **2735 passed, 1 skipped**, 34 warnings in **141.12s** — exit
code 0. Exactly matches the documented final suite
(PROJECT-STATE-REPORT §7b).

## 4. CI at main HEAD (CONFIRMED)

All six check-runs on `ac06f2b` completed/success:
`test (3.11)`, `test (3.12)`, `test (3.13)`, `test (3.14)`,
`lint-sast-coverage`, `audit-dependencies`.

## 5. Release asset integrity (CONFIRMED)

Both release assets downloaded fresh and digests verified:

- `ai-trading-lab-data-engine-windows-v0.3.0.zip` (17,908,197 bytes)
  SHA256 `d32f81b3a20d95ec768696ca909090da35c8ef68f95768e09e6296ce11d66631`
  — `sha256sum -c` OK (matches published SHA256SUMS.txt).
- `ai-trading-lab-monitor.apk` (21,156,320 bytes)
  SHA256 `dfea6d83228519e573dc5cd9483f469b34a6f4bc8d42be8be47fbfd0a6f5cd92`
  — `sha256sum -c` OK (matches published SHA256SUMS.apk.txt).
- `scripts/validate_windows_package.py` run on the downloaded zip:
  **VALIDATION OK (8 passed, 0 failed)** — "SHA256SUMS.txt covers +
  matches all 534 packaged files", version agreement 0.3.0, fail-closed
  posture pins present, no forbidden members, no credential-shaped
  content, all paths traversal-free.

## 6. Release provenance claim (CONFIRMED — byte level)

The v0.3.0 release notes state the zip was REBUILT from the final
commit `ac06f2b` (not from the tag commit `bab12c7`). Verified
independently: `source/scripts/validate_windows_package.py` inside
the zip (359 lines, SHA256 prefix `6029ae3c`) is byte-identical to
`ac06f2b`'s copy, and that file did not exist at `bab12c7`
("exists on disk, but not in 'bab12c7'"). The published zip is the
final-tree build exactly as disclosed. The `v0.3.0` tag itself
remains at `bab12c7` — published tags are immutable and moving it
would require history rewrite, which is forbidden; the release notes
are the authoritative build descriptor for the asset.

## 7. Fail-closed posture spot checks (CONFIRMED)

- `data-engine serve` in a bare process: "[serve] REFUSING TO START:
  PAPER_READY = FALSE (fail-closed startup — the paper readiness gate
  holds no passing evidence in this process)…" — **exit code 2**.
- `tests/test_paper_mode_selection_proof.py` (D1 four-layer
  paper-only selection proof): **10 passed** in 2.04s.
- PAPER_READY / LIVE TRADING posture statements present across
  `runtime/readiness.py`, `runtime/service.py`,
  `runtime/submission_ledger.py`, `runtime/monitoring.py`,
  `runtime/composition.py`, `brokers/catalog_report.py`; readiness is
  evidence-driven over 32 gates, and absent evidence defaults FALSE.

## 8. Statuses after re-verification (unchanged)

- CORE_ENGINE_VERIFIED: TRUE (independent suite re-run green)
- INTEGRATION_VERIFIED: TRUE (CI 6/6 at main HEAD)
- PAPER_EVIDENCE_COMPLETE: TRUE (dev-run scope)
- PAPER_READY: **FALSE** (owner soak decision pending — unchanged)
- LIVE TRADING: **NOT AUTHORIZED** — permanently out of scope.

## 9. Verification commands (reproducible)

```
git clone https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine.git
cd ai-trading-lab-data-engine && uv sync --extra dev
env -u VIRTUAL_ENV -u UV_PYTHON .venv/bin/python -m pytest tests/ -q --no-header
env -u VIRTUAL_ENV -u UV_PYTHON .venv/bin/python scripts/validate_windows_package.py <zip>
```

No credentials appear in this record; the session token was used only
as one-time inline push URLs, never stored in any file, config, or
commit.
