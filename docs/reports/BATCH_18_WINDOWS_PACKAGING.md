# BATCH 18 — WINDOWS INSTALLER AND APPLICATION PACKAGING

> **Batch type:** packaging scaffold with honest verification markers
> (mandate §7; dependency-map item C-4). Built artifacts were produced
> and verified where the environment supports it; Windows-host
> execution is explicitly NOT VERIFIED. No push, merge, rebase, reset,
> or history rewrite was performed.
>
> **Repository:** `muhammadasterschool-sketch/ai-trading-lab-data-engine`
> **Base commit:** `40bde4b` (Batch 17 tip)
> **Dedicated branch:** `feat/batch-18-windows-packaging`
> **Date:** 2026-10-13
>
> **PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY.**
> **LIVE TRADING NOT AUTHORIZED.** Nothing in this batch changes either.

## 1. Scope determination (mandate §7 first requirement)

Inspected the actual application structure first-hand: the project is
a platform-independent Python engine (`uv_build` backend; wheel
`py3-none-any`), NOT a Windows GUI application. The only Windows-
specific element is the optional `MetaTrader5` data-plane dependency
(`platform/mt5.py`, read-only, orders refused unconditionally —
operator's Windows MT5 terminal). This matches Batch 11 §5 ("installer
NOT IMPLEMENTED/NOT SPECIFIED") and determines the honest packaging
scope: **wheel + governed Windows installation procedure + fail-closed
smoke validation**, with a signed installer executable remaining an
operator product decision (signing keys = secure external processes).

## 2. Delivered

1. **Reproducible build — VERIFIED:** `uv build` executed in the agent
   environment producing
   `ai_trading_lab_data_engine-0.1.0-py3-none-any.whl` (689,373 B,
   SHA256 `93cd883a…95ea7c0`) and `…-0.1.0.tar.gz` (569,496 B, SHA256
   `284e2a9b…f95eebe`). `dist/` is gitignored — binaries are never
   committed; the SHA256s in `docs/WINDOWS_INSTALLER_AND_PACKAGING.md`
   §2 are the provenance record.
2. **Windows packaging spec — NEW** `docs/WINDOWS_INSTALLER_AND_
   PACKAGING.md`: installation procedure (fresh per-user venv under
   `%LOCALAPPDATA%`, wheel install, optional MT5 extra, smoke
   validation), data-directory handling (FS-01..06 fail-closed
   containment; runtime artifacts stay under configured roots), secret
   boundary (never packaged — env-var-only at runtime, redaction
   enforced), startup errors / safe shutdown / diagnostics (existing
   fail-closed contracts + dashboard `shutdown()`), upgrade / rollback
   / backup / uninstall procedures, version + build provenance, and a
   per-item honest verification-status table.
3. **Windows smoke test — NEW** `scripts/windows_smoke_test.py`:
   7 fail-closed checks (import + version; readiness contract —
   PAPER_READY=TRUE with failing gates structurally refused; REAL
   execution-mode descriptor refused; all 7 venues MOCK_DETERMINISTIC;
   dashboard default bind loopback; ephemeral bind; safe shutdown).
   **Script logic VERIFIED in the agent environment (all 7 PASS —
   they are platform-independent engine checks); Windows-host
   execution NOT VERIFIED** (agent environment is Linux).

## 3. Mandate §7 requirement verdicts

| Mandate item | Status |
|---|---|
| Inspect existing structure; determine technically supported packaging | **PASS** — §1 (wheel + procedure; installer exe = operator decision) |
| Reproducible build and packaging process | **PASS** — `uv build`, SHA-pinned (§2) |
| Dependency installation, configuration, data-directory handling | **PASS** — spec §3 (locked deps via wheel install; FS-contained data dirs) |
| Secrets outside source code, packaged defaults and logs | **PASS** — 0 credential-shaped strings across all history (forensic gate re-run this batch); env-var-only runtime boundary |
| Clear startup errors, safe shutdown, diagnostic reporting | **PASS** — existing fail-closed typed errors + dashboard shutdown (smoke checks 5/6) |
| Upgrade, rollback, backup and recovery documented | **PASS** — spec §4 (fresh-venv upgrades; SHA-recorded rollback; runtime recovery protocol) |
| Validate clean installation and startup in a Windows environment | **NOT VERIFIED — EXTERNAL** — requires a Windows host; operator runs spec §3 steps and records output (mandate: "clearly mark the missing verification") |
| Packaged application does not silently enable live trading | **PASS** — structural refusals + smoke checks 2/3 (VERIFIED in agent env; re-verified on Windows by the operator) |
| Software-version and build provenance information | **PASS** — wheel SHAs + `__version__` + commit ledger; honest LOW finding recorded: pyproject/lock `0.1.0` vs `data_engine.__version__` `0.3.0` mismatch (lock-frozen + test-pinned — alignment deferred to operator review, not silently changed) |
| "Do not claim a Windows installer is tested if the build or smoke test was not actually run" | **PASS** — every claim carries its honest status; NO Windows-host claim is made |

## 4. Verification results (actual)

| Check | Result |
|---|---|
| `uv build` | wheel + sdist built; SHAs recorded in spec §2 |
| `uv run python scripts/windows_smoke_test.py` (agent env) | **SMOKE RESULT: PASS — 7/7 checks** |
| Full suite post-commit | recorded in the worklog (base at Batch 17: 2,333 + 1 skipped) |
| Frozen contracts / manifest / secret scan | **PASS 11/11, 13/13, 0** (re-run post-commit) |
| Diff review | 4 files (spec + smoke script + report + index); no unrelated changes; `dist/` untracked by design |

## 5. Commands executed (exact)

```bash
uv build                                   # wheel + sdist (SHAs recorded)
sha256sum dist/*
uv run python scripts/windows_smoke_test.py     # 7/7 PASS (agent env)
rg -n "build-system|uv_build" pyproject.toml
rg -n "__version__" src/data_engine/__init__.py tests/   # 0.3.0 vs 0.1.0 finding
python3 /home/z/my-project/scripts/batch9_gate_verify.py
uv run pytest -q -p no:cacheprovider            # post-commit (worklog)
```

## 6. Commit record

- New: `docs/WINDOWS_INSTALLER_AND_PACKAGING.md`,
  `scripts/windows_smoke_test.py`, this report.
- Modified: `MASTER_DOCUMENTATION_INDEX.md` v2.22.0 → v2.23.0.
- Branch: `feat/batch-18-windows-packaging` from `40bde4b`. The built
  wheel/sdist stay untracked (`dist/` gitignored). Nothing pushed
  (B11-R-04 credential blocker).

## 7. Final verdict

**PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY. LIVE
TRADING NOT AUTHORIZED.** Batch 18 stops here. Next per the dependency
map: **Batch 19 — per-user VPS and operational deployment**.
