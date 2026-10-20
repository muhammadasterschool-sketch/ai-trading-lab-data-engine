# P0-P3 WINDOWS / PLATFORM COMPATIBILITY REPORT

## 1. Claimed platform matrix (from project configuration + CI)

| Combination | Claim | Evidence class |
|---|---|---|
| Linux / Python 3.11, 3.12, 3.13, 3.14 | **TESTED** (CI matrix runs the full suite on all four) | CI runs green on this task's final commits |
| Windows / Python 3.11+ | **PACKAGE + SCRIPTS VALIDATED (Linux-side); WINDOWS-HOST RUNS NOT VERIFIED** | Stage E validation: package built deterministically, installed from hash-pinned requirements + wheel into a fresh venv on Linux, full suite executed from the packaged source; the ps1 scripts are contract-tested as text. No Windows host executed anything. |

## 2. POSIX-dependency inventory (audited this task)

| Module | POSIX dependency | Windows behavior AFTER this task | Before |
|---|---|---|---|
| `runtime/state.py` | `fcntl.flock` | graceful fallback to `msvcrt.locking` (LK_NBLCK) — single-writer lock still enforced | already cross-platform |
| `runtime/submission_ledger.py` | `fcntl.flock` | module IMPORTS cleanly (FIX-12: conditional import); `SubmissionLedger(...)` REFUSES with the documented fail-closed message ("POSIX flock support … WSL/Linux guidance") | **BUG (B-P1-09)**: top-level `import fcntl` crashed the module import on Windows (ModuleNotFoundError), breaking every importer including the composition root and CLI; the documented constructor refusal was unreachable dead code |
| everything else | none found (audit sweep of `fcntl`/`msvcrt`/`os.fork`/signals) | signals degrade gracefully in non-main threads (existing tests); no other POSIX-only API is imported by the runtime path | — |

## 3. Deployment scripts (audited + hardened this task)

- `deploy/windows/run-paper.ps1` (FIX-13):
  - refuses without `-Confirm` (fail-closed paper start);
  - refuses without `RUNTIME_LEDGER_MAC_KEY[_FILE]`;
  - `status --gates` tool failure aborts with exit 5 (never a
    green-looking startup on a broken tool);
  - `-SessionPlan <path>` passes `--session-launch` to the CLI;
    missing plan file refuses with exit 4; a refused launch surfaces
    the engine's exit code verbatim;
  - dashboard remains loopback-only.
- `deploy/windows/install.ps1` / `run-tests.ps1`: unchanged this task
  (hash-pinned dependency install; smoke test). Contract-tested by
  `tests/test_windows_package.py` (16 tests).
- Honest markers preserved: the package README and this report keep
  the "Windows-host NOT-VERIFIED" wording — the repo does not claim
  host runs it has not done.

## 4. What Windows users can honestly do today

1. Install the package (hash-pinned, offline-capable wheel) and run
   the full test suite (`run-tests.ps1`) — the suite is expected to
   pass on Windows for everything except the POSIX-flock ledger
   constructor tests, which fail closed with the documented refusal
   (this is the honest posture: the durable ledger requires
   flock/WSL/Linux).
2. Run the supervisor shell (`run-paper.ps1 -Confirm`) — it will
   refuse readiness (exit 2) exactly as on Linux until the evidence
   chain exists.
3. Run a full operational session: **only under WSL/Linux today**
   (the submission ledger's durability guarantee is flock-based by
   design; FIX-12 makes that limitation explicit instead of a crash).

## 5. Required evidence to upgrade the claim

- A real Windows host (or CI windows runner) executing:
  `install.ps1` → `run-tests.ps1` (expected: green with the
  documented ledger-refusal skips) → `run-paper.ps1` refusal paths
  (no -Confirm; no MAC key; missing -SessionPlan).
- Until then, no document may say "Windows supported" beyond the
  package/scripts scope above (pinned by the
  `test_honest_windows_host_verification_marker` contract test).
