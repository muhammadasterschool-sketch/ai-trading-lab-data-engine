# AI TRADING LAB — LOCAL-FIRST ONBOARDING v4.0 — IMPLEMENTATION PLAN (P8 GATE)

Document: `artifacts/v4/00-LOCAL-FIRST-IMPLEMENTATION-PLAN.md`
Plan version: 1.0 (Stage A output — posted in-session for owner approval BEFORE any
implementation code, per PART 3 P8 of the v4.0 mandate).
Reference date: 22 October 2026 (re-verified 2026-10-23 against the live repo).

---

## 0. STAGE A RE-VERIFICATION RECORD (A1–A3, verified live)

| PART 0 fact | Re-verified value | Method |
|---|---|---|
| Branch / HEAD | `main` @ `3fcab194ee702b947157d9a068b91260c7c5b657` "fix(ci): use pytest-importable sibling module references (CI red fix)" | `git log -1` on fresh clone |
| Working tree | clean (`git status --short` empty) | fresh clone |
| CI on `3fcab19` | 6/6 jobs green: test (3.11), test (3.12), test (3.13), test (3.14), lint-sast-coverage, audit-dependencies | GitHub check-runs API |
| Release v0.3.0 | `ai-trading-lab-data-engine-windows-v0.3.0.zip`, 18,014,638 bytes, asset updated 2026-10-20T18:53:58Z + `SHA256SUMS.txt` | GitHub releases API |
| Release APK | `apk-bab12c7aa768` — `ai-trading-lab-monitor.apk` (21,156,320 bytes) + `SHA256SUMS.apk.txt` | GitHub releases API |
| Suite baseline | **2834 passed, 1 skipped** (2835 collected) in 171.34 s, `uv run pytest -q -p no:cacheprovider` on Python 3.12.15 / uv 0.13.0 | local run, fresh `uv sync --frozen --extra dev` |
| Flutter tests | **NOT RUN locally** — no Flutter toolchain in this workspace; APK is built by CI (`.github/workflows/build-apk.yml`, Flutter 3.24.5 pinned) | `which flutter` → absent |
| APK login fields | 3 fields today: Label, Server URL (https), Personal token (`mobile/lib/main.dart` ServerProfile + profile dialog) | read |
| APK TLS posture | `normalizeServerUrl()` refuses `http://`, bare host → `https://` (`main.dart:144-161`) | read |
| Monitoring API | stdlib `ThreadingHTTPServer`, loopback default `host="127.0.0.1"` (`monitoring.py:142`), bearer auth `hmac.compare_digest`, endpoints `/api/{health,positions,orders,pnl,feed,risk,events,killswitch,prediction,strategy/*}`, kill-switch 503 when unwired (`monitoring.py:506-513`) | read |
| CLI serve | `_build_monitoring_api()` (`cli.py:60-93`), `--monitor-bind` default 127.0.0.1, `--monitor-token-file` (tokens via files only), kill-switch honestly `NOT_WIRED_IN_BARE_CLI_PATH` | read |
| Pairing/invitation machinery | **NONE exists** — repo-wide grep for `invitation|pairing|/api/pair` finds only unrelated ML feature-pairing terms (prediction/PIT) | grep |
| Windows package | `build_windows_package.py` EXPECTED_COMPONENTS = {install.ps1, run-tests.ps1, run-paper.ps1, README-WINDOWS-PACKAGE.md}; `git archive HEAD` source, `uv export --frozen --no-dev` requirements, wheel via `uv build`, deterministic zip + SHA256SUMS | read |
| Package validator | structure/integrity/safety/version/posture checks (digest-first, credential-content scan incl. `github_pat_` regex, zip-bomb guards, `$ErrorActionPreference = "Stop"` pins, README honesty pins) | read |
| Cloud install | `server-install.sh` generates `monitor.token` + `mac.key` via `openssl rand -hex 32` (0640, root:engine); systemd unit sets `RUNTIME_LEDGER_MAC_KEY_FILE`, serves `--monitor-bind 127.0.0.1` | read |
| Posture | PAPER_READY = FALSE; gates REAL_DATA_READY / OPERATIONAL_FEED_READY / GOVERNANCE_READY open; LIVE_TRADING = NOT AUTHORIZED — **unchanged by this task** | read |

**Verdict: every PART 0 fact re-verified. No mismatches. Proceeding to the plan (no implementation code written yet).**

---

## 1. DESIGN — INVITATION / PAIRING PROTOCOL (B1)

### 1.1 Hash format (salted SHA-256, constant-time)

- Stored config (JSON, version 1):
  ```json
  {
    "version": 1,
    "enabled": true,
    "salt_hex": "<32 hex chars = 16 random bytes>",
    "code_sha256_hex": "<64 hex chars = SHA256(salt_hex || code_utf8)>",
    "max_attempts_per_minute": 5
  }
  ```
- Verification: `digest = SHA256(salt_hex + supplied_code)` compared with
  `hmac.compare_digest` against `code_sha256_hex`. Constant-time, fail-closed.
- Salt uniqueness: generated per config (`secrets.token_hex(16)` /
  `openssl rand -hex 16`), so two installs with the same code never share a hash
  (regression-tested).
- The invitation code VALUE is never stored, logged, echoed, or committed.
  Only the salt + hash above are committed config data.

### 1.2 Local default (P4) — committed values

The Windows package's local config template ships PRE-SET with the salted
hash of the owner's local default code. Committed values (Stage B pins these
in `deploy/windows/local-monitor-config.template.json`):

```
salt_hex:         60b67c81d07813d2b9a9f2d99b629a0b
code_sha256_hex:  bdbc68cfbcab89ce2e91335be58340caa02180cb81b12c4ec31f6f13a05c17a6
```

These are NON-REVERSIBLE config data. The plaintext default is documented
only in the owner's out-of-band onboarding record — never in any committed
file, never in `mobile/`, never in the APK.

### 1.3 Reason codes (stable, fail-closed)

| Code | Meaning | HTTP |
|---|---|---|
| `E_PAIRING_DISABLED` | no/absent pairing config wired (cloud default; any misconfiguration) | 503 |
| `E_PAIRING_CODE_INVALID` | wrong or missing invitation code | 403 |
| `E_PAIRING_RATE_LIMITED` | > `max_attempts_per_minute` (default 5) from one IP | 429 |

Wrong/missing/absent code NEVER fabricates a pairing. No partial success.

### 1.4 Rate limiting

Per-client-IP fixed-window limiter, default 5 attempts/min, configurable via
`max_attempts_per_minute`, reusing the `_RateLimiter` pattern from
`monitoring.py`. Independent from the existing 60/min general monitoring rate
limit (pairing attempts are counted separately — brute-force friction on the
onboarding secret specifically).

### 1.5 Redaction & audit (P7, Rule 3)

- The invitation code is NEVER logged in any form (not even a digest).
- Email is redacted to `***@domain` in every log/audit line.
- The returned bearer token is NEVER logged (existing posture).
- Audit entry per attempt: timestamp, client IP, mode, outcome reason code,
  redacted email, profile name (name is operator-visible identity, kept).

### 1.6 Honest trust statement (documented in README + guide)

Whoever holds the invitation code AND network access to the monitor endpoint
can obtain the monitoring bearer token. The code is the onboarding secret;
rotation is available (owner regenerates config). Documented verbatim in
Stage E docs.

---

## 2. ENDPOINT CONTRACT — `POST /api/pair` (B1)

Wired in `monitoring.py` `do_POST` BEFORE the bearer-token check (the
endpoint is the only unauthenticated-then-authenticated surface; every other
route is unchanged and stays token-first).

- **Rate limit first** (per-IP pairing limiter), then body validation, then
  code verification, then success.
- Request (JSON, max 8 KiB):
  ```json
  {"name": "alice-laptop", "email": "alice@example.com",
   "invitation_code": "<code>", "mode": "local" | "cloud"}
  ```
  - `name`: required, non-empty (profile label).
  - `email`: required by the APK in LOCAL mode (identity only, P7); the
    engine treats it as optional-but-redacted (cloud users may omit).
  - `invitation_code`: required, non-empty.
  - `mode`: required, one of `local` / `cloud` (audit only; enforcement of
    TLS-for-cloud lives in the APK profile flag and existing server TLS
    posture — the endpoint itself never downgrades anything).
- Responses:
  - `200` — `{"status":"paired","token":"<monitoring bearer token>",
    "health":{...engine health snapshot...},
    "pairing":{"email_redacted":"***@example.com","mode":"local"}}`
    (the token is the same bearer token the monitor API authenticates with;
    documented honestly in §1.6).
  - `403` — `{"error":"E_PAIRING_CODE_INVALID"}`
  - `429` — `{"error":"E_PAIRING_RATE_LIMITED","retry_after_seconds":<int>}`
  - `503` — `{"error":"E_PAIRING_DISABLED"}`
  - `400` — malformed JSON / missing required fields (no reason-code leakage).
- Pairing is wired ONLY when the server is started with
  `--pairing-config <path>`; absent flag or disabled config → 503
  fail-closed (cloud default = pairing disabled, tested).
- `GET /` route listing gains `POST /api/pair`.

## 3. ENGINE-SIDE FILES (Stage B)

| File | Change |
|---|---|
| `src/data_engine/runtime/pairing.py` (NEW) | config loader (strict JSON schema; malformed/missing → startup refusal when the flag was given, per existing token-file posture), salted-SHA256 constant-time verifier, per-IP limiter, reason-code constants, email redaction helper, `attempt_pair()` producing the endpoint response + audit line |
| `src/data_engine/runtime/monitoring.py` | add `pairing` optional param + `POST /api/pair` route before auth (only this addition; no weakening of any existing check; heartbeat field set untouched) |
| `src/data_engine/runtime/announce.py` (NEW) | `try_announce_mdns()` — registers `_aitl-monitor._tcp.local.` via zeroconf when importable; graceful "mDNS unavailable" status + manual-address fallback when not; never fatal |
| `src/data_engine/cli.py` | serve gains `--pairing-config PATH`, `--mdns-announce`, `--mdns-instance NAME`; new `pair-status` subcommand (B4): prints enabled/disabled, configured attempts/min, config path validity — NEVER the code; live in-window attempt counters are printed by the serve console (same-process honesty) |
| `pyproject.toml` | version `0.4.0`; runtime dep `zeroconf` (mDNS; minimal, noted in CHANGELOG — Rule 8) |
| `uv.lock` | refreshed via `uv lock` (project version entry + zeroconf only; diff reviewed, no unrelated bumps) |
| `src/data_engine/__init__.py` | `__version__ = "0.4.0"` (validator version-agreement pin) |

## 4. CLOUD PATH (B2)

`deploy/server-install.sh`:
- New `--invitation-code <code>` flag. When set: generates
  `salt=$(openssl rand -hex 16)` and the salted SHA-256 of the code, writes
  `/etc/ai-trading-lab/invitation.hash` (JSON §1.1, mode 0640 root:engine,
  never plaintext, never logged).
- No flag → no hash file → the systemd unit omits `--pairing-config` →
  `/api/pair` answers 503 `E_PAIRING_DISABLED` (fail-closed default).
- Systemd unit: appends `--pairing-config $ETC_DIR/invitation.hash` only when
  that file exists.
- `deploy/MULTI-USER-DEPLOYMENT-GUIDE.md`: §1 gains "Cloud is OPTIONAL — the
  local-first alternative" (E2) + invitation-code issuance/rotation steps
  (rotation = regenerate salt+hash, restart service).

## 5. WINDOWS LOCAL MONITOR (B3, Stage D packaging)

### 5.1 `deploy/windows/run-monitor.ps1` (NEW)

- First run: if `.\local-monitor.json` absent → copy
  `.\local-monitor-config.template.json` → it (invitation salt+hash pre-set,
  §1.2) and generate `.\monitor-token.txt` (32-hex via the venv Python)
  with restrictive-ACL note; prints "change the invitation code: see
  LOCAL-MONITOR-RUNBOOK.md §rotate".
- Starts (monitor-only, NO trading session — no `-Confirm` needed, no
  session launch):
  `.\.venv\Scripts\python.exe -m data_engine.cli serve --no-dashboard --monitor-bind 127.0.0.1 --monitor-port 8018 --monitor-token-file .\monitor-token.txt --pairing-config .\local-monitor.json`
- Default = loopback. Prints: "same device (emulator): use `127.0.0.1:8018`".
- `-AllowLan` switch: binds `0.0.0.0` explicitly, prints the PC's LAN IPv4
  (`Get-NetIPAddress`), an explicit UNENCRYPTED-LAN warning, the manual
  connect address (`http://<lan-ip>:8018`), a firewall-check hint
  (`netsh advfirewall firewall add rule ...`), and adds `--mdns-announce`.
- mDNS status is echoed from the engine's startup line; failure of mDNS
  NEVER blocks serving (manual address always works).
- Kill-switch honesty preserved: bare serve wires no activator → 503 until a
  composed session exists (existing behavior, kept + re-tested).
- `run-paper.ps1`: UNTOUCHED in behavior.

### 5.2 `deploy/windows/local-monitor-config.template.json` (NEW, committed)

The §1.1 JSON with the §1.2 salt+hash, `"enabled": true`, 5 attempts/min.
No plaintext code anywhere.

### 5.3 `deploy/windows/install.ps1` (upgraded, D1)

- Adds step 5b: verify `run-monitor.ps1` + `local-monitor-config.template.json`
  exist (fail-closed packaging check), and a beginner "what next" block:
  run-monitor → connect APK (Cloud or Local) → switch later.

### 5.4 Build/validate updates (D2)

- `scripts/build_windows_package.py`: EXPECTED_COMPONENTS += `run-monitor.ps1`,
  `local-monitor-config.template.json`.
- `scripts/validate_windows_package.py`:
  - REQUIRED_SUFFIXES += the two new members;
  - `source/src/data_engine/runtime/pairing.py` + `.../announce.py` presence
    pins (mDNS module present);
  - posture pin: `run-monitor.ps1` has `$ErrorActionPreference = "Stop"`;
  - template check: valid 32-hex salt + 64-hex hash, `enabled` boolean;
  - no-plaintext-code check: when env `AITL_INVITE_PROBE` is set (owner-side
    validation runs), assert the probe string appears in NO text member
    (repo-wide, incl. `source/mobile/`); CI runs this check without the
    probe (structural checks only) — recorded honestly.
  - tamper control unchanged (digest-first SHA256SUMS must still fail a
    modified zip — re-tested).
- Windows-host execution remains operator evidence (unchanged honest marker).

## 6. APK DUAL-MODE ONBOARDING (Stage C, Flutter)

### 6.1 Model & storage

- `ServerProfile` gains `isLocal` (bool) + `email` (String?, local profiles).
  JSON serialization versioned by additive fields (old profiles load as
  cloud profiles — existing data never deleted, P6).
- Token stays in `flutter_secure_storage` ONLY; the invitation code is
  typed, used for the pairing POST, then discarded — never stored, never
  logged, never in the binary (C6). No code value may appear anywhere under
  `mobile/` (test-pinned + package probe).

### 6.2 Screens (text wireframes)

1. **ModeChoicePage** (first run only, P2):

   ```
   +--------------------------------------+
   |  AI Trading Lab - how will you run?  |
   |  +--------------------------------+  |
   |  |  CLOUD SERVER                  |  |
   |  |  Your own VPS over https.      |  |
   |  +--------------------------------+  |
   |  +--------------------------------+  |
   |  |  LOCAL COMPUTER                |  |
   |  |  No server rental. Pair with   |  |
   |  |  the engine on this Windows PC. |  |
   |  +--------------------------------+  |
   +--------------------------------------+
   ```

   Choice persisted (`atl_onboarding_mode`), changeable later by adding a
   profile of the other kind (P6).
2. **Cloud pairing form** (C2): Name* / Server URL* (https enforced) /
   Invitation Code* → `POST {url}/api/pair` → token stored → dashboard.
   "Advanced: paste token manually" stays (existing manual path).
3. **Local pairing form** (C3): Name* / Gmail-email* / Invitation Code* /
   PC address* (auto-filled via mDNS discovery; manual entry fallback;
   `127.0.0.1` allowed) → one-time warning dialog:
   "Local mode traffic on your LAN is UNENCRYPTED outside the host PC." →
   `POST http://<pc>/api/pair` → token stored → dashboard.
4. **Profile list** (existing gate page, extended): mode badge chips
   `[CLOUD]` / `[LOCAL]`, "Switch" preserves every profile (P6), one active.

### 6.3 TLS posture (C3 — scoped, never global)

- `normalizeServerUrl(raw, {required bool isLocal})`:
  - cloud: EXACTLY today's behavior (`http://` refused; bare host → `https://`);
  - local: `http://` and `https://` allowed, bare host → `http://`.
- `isLocal` is a per-profile flag stored WITH the profile; a cloud profile
  can never be coerced to http and vice-versa. No global toggle exists.
- Widget tests pin both directions (TLS refusal for cloud; local http only
  with `isLocal: true`).

### 6.4 mDNS discovery (P5)

- `mobile/pubspec.yaml` gains `multicast_dns` (pinned version; the only new
  mobile dependency — noted in CHANGELOG).
- Discovery helper: resolve `_aitl-monitor._tcp.local.` with a ~4 s timeout →
  prefill PC address; ANY failure → silent fallback to manual entry
  (never blocks onboarding).
- `.github/workflows/build-apk.yml`: after `flutter create`, patch the
  generated AndroidManifest to add `CHANGE_WIFI_MULTICAST_STATE` (graceful:
  discovery still falls back without it).

### 6.5 Files (mobile/)

| File | Change |
|---|---|
| `mobile/lib/main.dart` | profile model + `isLocal`; scoped `normalizeServerUrl`; mode choice gate; two pairing forms; mode badges + switch; one-time LAN warning; mDNS prefill |
| `mobile/lib/pairing.dart` (NEW) | pairing POST client + mDNS discovery helper (isolated for testability) |
| `mobile/test/pairing_test.dart` (NEW) | widget tests: 3-field compulsory validation per mode; cloud http refused; local http only with isLocal; switching preserves profiles |
| `mobile/pubspec.yaml` | + `multicast_dns` |
| `mobile/README-APK.md` | rewritten two-mode onboarding (E1) |

## 7. DOCS REPLACEMENT (Stage E)

| File | Change |
|---|---|
| `mobile/README-APK.md` | two-mode onboarding, local LAN honesty, invitation-code model, release-signing note unchanged |
| `deploy/MULTI-USER-DEPLOYMENT-GUIDE.md` | §1 "Cloud is OPTIONAL — local-first alternative"; cloud stays for remote/multi-user; `--invitation-code` issuance + rotation |
| `deploy/windows/LOCAL-MONITOR-RUNBOOK.md` (NEW) | beginner runbook: rent nothing → install → run-monitor → connect APK (local) → switch to cloud later; code rotation command |
| `CHANGELOG.md` | v0.4.0 section (features + the two new dependencies) |
| `FIX-LOG.md` | v4.0 entries |
| `PROJECT-STATE-REPORT.md` | supplement; readiness statuses UNTOUCHED (PAPER_READY = FALSE; 3 human gates open; LIVE_TRADING NOT AUTHORIZED) |

## 8. TEST LIST (Stage F)

### 8.1 Engine (`tests/test_pairing.py` NEW + `tests/test_monitoring_api.py` additions)

- happy path: correct code → 200, token matches monitor token, health snapshot included;
- wrong code → 403 `E_PAIRING_CODE_INVALID`, no token in any response field;
- missing/absent config (no `--pairing-config`) → 503 `E_PAIRING_DISABLED`
  (cloud default = disabled);
- malformed config passed via flag → serve refuses to start (fail-closed, exit 1);
- rate limit: 6th attempt within window from one IP → 429 + retry_after; different IPs independent;
- salt uniqueness: same code, two salts → different `code_sha256_hex`, both verify;
- redaction: email `***@domain` in the audit line; code + token NEVER in captured logs;
- `POST /api/pair` unreachable through bearer-auth-only when pairing not wired (no surface change);
- kill-switch 503 honesty preserved (bare serve, monitor-only) — existing suite + explicit re-pin;
- loopback default binding preserved; explicit `--monitor-bind 0.0.0.0` requires the explicit flag (existing CLI contract re-pinned);
- mDNS: `try_announce_mdns` builds correct ServiceInfo; zeroconf-absent → graceful status, serve continues;
- `pair-status` CLI: enabled/disabled + attempts/min printed; code NEVER printed;
- no-plaintext pin: with `AITL_INVITE_PROBE` set, assert the probe appears in no tracked file under `mobile/` and in the packaged zip (skips without the env, honestly recorded).

### 8.2 Package validator (`tests/test_windows_package_validation.py` additions)

- new required members pin (run-monitor.ps1 + template);
- template salt/hash shape pin; posture pin for run-monitor.ps1;
- tamper control: modified zip still FAILS (digest-first, unchanged);
- probe-scan when `AITL_INVITE_PROBE` set.

### 8.3 Flutter (`mobile/test/`, CI-run; NOT RUN locally — no toolchain)

- form validation: all fields compulsory per mode (3 fields each);
- cloud: `http://` refused by `normalizeServerUrl(isLocal: false)`;
- local: `http://` allowed ONLY with `isLocal: true`;
- switching: profiles persist, one active, no deletions.

### 8.4 CI

- Full suite green on the feature branch, then on `main` after merge;
- exact counts recorded in the final response (PART 11 §4).

## 9. RELEASE PLAN (P9, D5) — v0.4.0

1. Branch `feat/v4-local-first` from `3fcab19`; commit per stage (B, C, D, E,
   F) — every stage lands with its regression tests, full suite green each
   time (Rule 7). No reset/rebase/force (Rule 1).
2. Merge to `main` only when the full suite + CI are green (merge commit,
   history preserved).
3. Bump version 0.4.0 (pyproject + `__init__` + uv.lock) as part of the
   release commit (validator version-agreement pin requires it).
4. Windows package: `scripts/build_windows_package.py` on the clean merged
   tree → `ai-trading-lab-data-engine-windows-v0.4.0.zip` → validate with
   `scripts/validate_windows_package.py` (all pins + `AITL_INVITE_PROBE` set
   for the local run) → zip SHA256 recorded.
5. GitHub Release `v0.4.0`: zip + `SHA256SUMS.txt` (zip digest).
6. APK: dispatch `build-apk.yml` with `release_tag=v0.4.0` → CI builds
   debug-signed APK (Flutter 3.24.5, reproducible) + `SHA256SUMS.apk.txt`
   attached to the SAME release.
7. Post in chat: exact browser-download links for BOTH assets + SHA256
   digests (P9). Debug-signed APK + release-signing documented (P10: no
   iOS).

Expected link format:
- `https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/v0.4.0/ai-trading-lab-data-engine-windows-v0.4.0.zip`
- `https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine/releases/download/v0.4.0/ai-trading-lab-monitor.apk`

## 10. HONEST LIMITATIONS (carried into the final response)

- Windows-host execution of `install.ps1` / `run-monitor.ps1` / `run-paper.ps1`
  remains OPERATOR EVIDENCE (this workspace is Linux; packaging is validated
  structurally + digest-verified, as before).
- Flutter tests are NOT RUN locally (no toolchain); CI runs them — recorded.
- APK stays debug-signed; release signing documented-only. No iOS (P10).
- mDNS on Android can silently fail on some devices (multicast restrictions);
  manual PC-address entry is the always-available fallback.
- CI probe-scan for the invitation plaintext runs only with the owner-side
  env probe set (CI runs structural checks) — recorded honestly.
- PAPER_READY = FALSE unchanged; no real order path touched; the 3 human
  gates unchanged; LIVE_TRADING = NOT AUTHORIZED.

## 11. SECRETS-HANDLING RECORD (this session)

- The owner's PAT was pasted IN-CHAT (contrary to P9's "never in chat").
  It is stored only in this workspace at
  `/home/z/my-project/scripts/.gh-token` (mode 0600, OUTSIDE the repo),
  used exclusively for `git push` / GitHub API reads, never committed,
  never written into any repo file, never in any log. The remote URL is
  sanitized to the clean https form.
- **Recommendation: rotate/revoke this PAT after the task completes.**
- The invitation-code plaintext was handled only in transient shell
  variables during hash generation; the committed artifacts contain only
  salt + SHA-256 digest.

---

## STOP — P8 GATE

Per PART 3 P8 and PART 4 A4: this plan is posted in-session and NO
implementation code will be written until the owner explicitly replies
**"APPROVED"** (or requests plan changes first).
