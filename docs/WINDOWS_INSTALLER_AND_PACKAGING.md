# WINDOWS INSTALLER AND APPLICATION PACKAGING (BATCH 18 — ITEM C-4)

> **Document type:** packaging specification + reproducible build
> process (mandate §7). Defines what is TECHNICALLY SUPPORTED today
> and what a Windows installer must do. Honest verification status is
> marked per item — nothing is claimed that was not actually run.
>
> **Version:** 1.0.0 · **Date:** 2026-10-13
>
> **PAPER_READY = FALSE. LIVE TRADING NOT AUTHORIZED.** A packaged
> installation NEVER silently enables live trading (enforced + smoke-
> tested below).

## 1. What the application actually is (scope finding)

The repository is a **Python engine/library** (`src/data_engine`,
`uv_build` backend, platform-independent wheel `py3-none-any`) — not a
Windows GUI application. The ONLY Windows-specific element is the
optional `MetaTrader5` data-plane dependency (`platform/mt5.py`,
read-only, orders refused unconditionally) which requires the
operator's Windows MT5 terminal. Packaging therefore means:
distributing and installing the Python engine + its locked
dependencies on Windows with governed data directories — which the
wheel + procedure below fully supports.

## 2. Reproducible build (VERIFIED in the agent environment)

```bash
uv build          # from the repository root
```

Produces (verified 2026-10-13, agent environment, uv 0.13.0):

| Artifact | Size | SHA256 |
|---|---|---|
| `dist/ai_trading_lab_data_engine-0.1.0-py3-none-any.whl` | 689,373 B | `93cd883a50fb62375300efdf26778f92124bce93cd1cbf0dfc56614a959ea7c0` |
| `dist/ai_trading_lab_data_engine-0.1.0.tar.gz` | 569,496 B | `284e2a9bb388907a24a51d3f50007dc66dcaf9be0e7f5c1943514755cf95eebe` |

`dist/` is gitignored (binary artifacts are never committed); the
SHA256s above are the build-provenance record. **Known honest finding
(LOW, build provenance):** `pyproject.toml`/`uv.lock`/wheel carry
version `0.1.0` while `data_engine.__version__` reports `0.3.0`
(pinned by tests). Aligning them requires a lock regeneration +
operator review — recorded, not silently changed.

## 3. Windows installation procedure (reproducible; execution NOT VERIFIED in the agent environment)

On a Windows 10/11 host with Python 3.11+ and internet access:

```powershell
# 1. fresh, isolated environment (per-user, no admin required)
python -m venv "%LOCALAPPDATA%\AITradingLab\venv"

# 2. install the built wheel + locked runtime dependencies
"%LOCALAPPDATA%\AITradingLab\venv\Scripts\python" -m pip install --upgrade pip
"%LOCALAPPDATA%\AITradingLab\venv\Scripts\python" -m pip install ^
    ai_trading_lab_data_engine-0.1.0-py3-none-any.whl

# 3. OPTIONAL data-plane extras (requires the operator's MT5 terminal):
#    pip install "ai-trading-lab-data-engine[...]"  — only if the
#    MetaTrader5 extra is declared at operator review; the engine runs
#    WITHOUT it (mock/governed-synthetic posture).

# 4. validate the installation (fail-closed smoke test)
"%LOCALAPPDATA%\AITradingLab\venv\Scripts\python" scripts\windows_smoke_test.py
```

**Data directories:** the engine writes runtime artifacts (audit
trail, ledgers, exports) relative to the working directory /
configured paths only (`data/exports`, `src/audit.log` patterns — all
gitignored, FS-21/22 governed). An installer must create
`%LOCALAPPDATA%\AITradingLab\data` and run the engine with that CWD;
nothing writes outside the configured roots (FileDataProvider FS-01..06
fail-closed filesystem containment — approved roots only).

**Secrets:** NEVER packaged. No credential exists in the wheel, the
sdist, the repository, or defaults (0 credential-shaped strings across
all history — forensic gate). Any provider credential is supplied at
runtime via the environment-variable boundary (fail at construction
if unset) — never in the installer, defaults, or logs (redaction layer).

**Startup errors, safe shutdown, diagnostics:** the engine fails
closed with typed errors and recorded reasons at every gate
(readiness verdict, feed gate, risk gate, kill switch); the dashboard
exposes a `shutdown()` that is safe whether or not serving; smoke
check 5/6 verifies bind + shutdown. Clear startup errors are the
existing fail-closed contract — an unconfigured install refuses work
loudly rather than half-running.

**Live trading:** impossible to silently enable — REAL execution-mode
descriptors are refused at construction, the session refuses REAL
adapters, `authorize_live` structurally refuses, PAPER_READY=TRUE with
failing gates is structurally impossible. Smoke checks 2 and 3 pin
exactly this on every installation.

**Version + build provenance:** wheel filename + SHA256 (§2) +
`data_engine.__version__` + the git commit of the build (recorded in
the release batch ledger).

## 4. Upgrade, rollback, backup, recovery

- **Upgrade:** install the new wheel into a FRESH venv
  (`venv-next`), run the smoke test, then swap a junction/symlink or
  update the launcher — never in-place mutation of a running
  environment.
- **Rollback:** keep the previous venv + wheel (SHA-recorded) until
  the new version is validated; rollback = repoint the launcher.
- **Backup:** the engine's persistent state (ledgers, journals,
  audit trail) lives under the data directory — back it up with any
  standard file backup; recovery follows the runtime's own
  LOAD→VERIFY→RESTORE→RECONCILE→RESUME protocol with HALT on
  corruption (fail-closed, tested).
- **Uninstall:** delete `%LOCALAPPDATA%\AITradingLab` (venv + data)
  — no registry keys, no services, no drivers are created by this
  procedure.

## 5. Verification status summary (honest)

| Item | Status |
|---|---|
| Reproducible wheel + sdist build (uv build) | **VERIFIED** (agent environment, SHAs above) |
| Smoke-test script logic (7 fail-closed checks) | **VERIFIED** (agent environment — all PASS) |
| Clean installation + startup ON WINDOWS | **NOT VERIFIED** — requires a Windows host; the operator runs §3 steps 1–4 and records the output |
| Packaged app never silently enables live trading | **VERIFIED by design + smoke checks 2/3** (structural refusals, pinned by tests) |
| Windows installer executable (MSI/EXE/InnoSetup/NSIS) | **NOT IMPLEMENTED — deliberate**: the venv+wheel procedure is the technically supported packaging; a signed installer is an operator product decision (signing keys must come from secure external processes) |

No Windows artifact was built or tested in the agent environment —
no such claim is made anywhere.

---

# STAGE E ADDENDUM — Windows zip package (Part 8, E1-E3, 2026-10-20)

The Batch 18 procedure above (wheel + governed install) is EXTENDED —
not replaced — by the Stage E zip package:

## E.1 Package layout + build

`scripts/build_windows_package.py` builds a DETERMINISTIC zip from the
exact commit (dirty tree refused):

```
<package>/install.ps1, run-tests.ps1, run-paper.ps1, README-WINDOWS-PACKAGE.md
          requirements-windows.txt   (uv export --frozen --no-dev, hash-pinned)
          dist/<wheel>               (uv build from the same commit)
          source/                    (git archive of HEAD)
          SHA256SUMS.txt             (sha256 of every packaged file)
```

Contract pinned by `tests/test_windows_package.py` (13 tests):
components present; builder fail-closed on dirty tree; NO secret
material embedded anywhere (env-var-only handling); README documents
state/log layout, secrets, backup/restore, safe shutdown, firewall/AV;
`run-paper.ps1` refuses without `-Confirm` AND without
`RUNTIME_LEDGER_MAC_KEY[_FILE]`; install uses `--require-hashes`.

## E.2 Validation evidence (this run)

- Locked deps install into a FRESH venv with `--require-hashes`:
  VERIFIED (Linux, Python 3.12.15) — see the Stage E report for the
  exact command transcript.
- Full suite green from the packaged source tree: VERIFIED (Linux,
  same interpreter family as the CI matrix).
- PowerShell scripts ON A WINDOWS HOST: **NOT VERIFIED in this run**
  (no Windows VM in the build environment) — the operator runs
  `install.ps1` → `run-tests.ps1` and records the output as final
  packaging evidence. This is the SAME honest posture as Batch 18 §5.
- Required Python: >=3.11 (declared runtime 3.14; 3.12+ recommended).

## E.3 Release

The zip + its SHA256 are published as a GitHub Release asset of this
repository (release link recorded in PROJECT-STATE-REPORT.md).
