# CHANGELOG — AI Trading Lab Data Engine

All notable changes under the FULL PROJECT PROMPT v3.0 run
(2026-10-19 → 2026-10-20). History preserved throughout (no reset,
no rebase, no force-push; feature branches merged to main only on
green full suites).

## v1.5.0 — paper-ready full upgrade (feat/v1.5-paper-ready)

Owner mandate (2026-10-28): "jitne bhi upgrades karne hai sare karoo
... admin apk delete karo aur monitor app mein admin user + users
option ... email login two factors verification ke baghair na ho ...
backtest data real and verified kisi repo se fetch karlo agar na mile
to websites par jao ... top 5 strategy jo YouTubers use karte hai
from start ... 1 min timeframe ... 60 percent sure ... 1 trade per
sec after confirmation candle ... crash prediction ... sare kaam
karo till paper trading".

- quant top-50 pack (NEW: oscillators.py, bands.py,
  trend_indicators.py, volume_ta.py, statistics_ext.py): 40 more
  indicators (MACD, Stochastic, StochRSI, CCI, Williams %R, TRIX,
  UO, AO, Bollinger, Keltner, Donchian, rolling/anchored VWAP, ADX,
  Supertrend, Parabolic SAR, Ichimoku, Aroon, WMA/HMA/DEMA/TEMA/
  ZLEMA/KAMA, linreg slope/R2, OBV, MFI, Force, EOM, CMF, A/D,
  Chaikin Osc, volume z-score, Choppiness, Vortex, Hurst approx,
  variance ratio, skew/kurtosis, Kaufman ER) — 57 registered in the
  IndicatorRegistry (was 17); all pure/deterministic/None-padded.
- runtime/presets.py (NEW): TOP-5 YouTuber presets — EMA 9/21 scalp
  + 200 filter, RSI+Bollinger mean-reversion, VWAP reversion,
  Supertrend follow + ADX filter, opening-range breakout — all M1,
  confirmation-candle (closed-bar) semantics, popularity-is-not-edge
  disclaimer, same G6 gate as everything else.
- runtime/lab.py: five new backtester kinds (ema_scalp, rsi_bb,
  vwap_reversion, supertrend_follow, orb_breakout — ORB is
  PIT-disciplined, entries only after the range fully forms),
  optional cost model in run() (fees+slippage per side; NET is the
  headline with gross reported alongside; costs-off preserves the
  v1.1.0 contract exactly), per-family conservative cost defaults
  (crypto 10+2 bps, FX/metals 1+7 bps per side), AUTO-SCAN
  (deterministic 27-combo parameter scan, 70/30 IS/OOS split, net
  of costs, survivors become ORDINARY submissions), and preset
  bootstrap (idempotent; creates + backtests + opens the 30-day
  paper windows so paper trading STARTS with the presets).
- runtime/confidence.py (NEW): ConfidenceGate — the >=60%
  bullish/bearish confirmation assessor (strategy vote 0.45 +
  baseline 0.35 + trend 0.20, all components inspectable,
  confirmation-candle only, honest "not a calibrated probability"
  labeling).
- runtime/rapid_scalper.py (NEW): the PAPER-ONLY one-fill-per-second
  burst journal — after a CONFIRMED (>=60%) call on a closed
  confirmation candle, plans 60 hypothetical fills at 1/sec with a
  deterministic cost model, marks the exit at the NEXT closed
  candle, enforces cooldown + cumulative loss cap + kill-switch
  pause; journaled to the strategy's paper ledger, NO orders sent
  anywhere (live stays NOT_AUTHORIZED).
- runtime/crash_lab.py (NEW): LabCrashPredictor (heuristic
  vol-z/ATR-expansion/drawdown-speed gauge, NOT the governed §4F
  contract) + NextMoveEnsemble (baseline + trend + efficiency
  ensemble) wired to GET /api/lab/crash/{symbol} and
  /api/lab/predict-ensemble/{symbol}.
- platform/historical_data.py (NEW): HistoricalDataService — REAL
  VERIFIED backtest data: bundled repo datasets (datasets/:
  BTCUSDT + ETHUSDT 1m 2026-09 from data.binance.vision, sha256
  verified against the official .CHECKSUM at acquisition and
  re-verified on EVERY load, tamper = refusal) first, then the
  Binance Vision website fallback (downloads + verifies + caches).
  RESEARCH_BACKTEST_ONLY: the operational-feed approval chain
  (feed_source_candidates / SRC-APPROVAL / DATA_READINESS) is
  untouched. CLI: hist-datasets, hist-import. HTTP:
  GET /api/hist/datasets, POST /api/hist/import.
- runtime/totp.py + runtime/accounts.py (NEW): MANDATORY two-factor
  login — RFC 6238 TOTP (official test vectors pinned), PBKDF2
  passwords (200k iters), sticky enrollment handshake (password
  verified -> authenticator secret shown ONCE -> code confirms),
  12h sessions, 5-failure 15-minute lockout, per-account login
  history, admin ops (create user / reset 2FA / lock-unlock).
  NO session is ever issued without a valid TOTP code. CLI:
  add-admin, accounts-list. HTTP: POST /api/auth/login (pre-auth),
  /api/auth/logout, GET /api/auth/me, /api/admin/accounts*.
- runtime/monitoring.py: session tokens now authorize alongside the
  pairing bearer (owner level); /api/users + /api/registrations are
  admin-gated (trader sessions get 403); new routes as above; a
  dedicated 10/min/IP login rate limit; opt-in --bootstrap-presets
  auto-creates the TOP-5 presets when a symbol's first bars land.
- Mobile monitor app v1.5.0+8: EMAIL LOGIN (2FA) onboarding with
  in-dialog enrollment, admin Users page (online clients + accounts
  with login history + create user / reset 2FA / lock), and the
  "START PAPER TRADING" card (verified data import + presets +
  AUTO-SCAN). The separate ADMIN APK IS DELETED (admin/ and its CI
  workflow removed — the monitor app is now the single app; older
  admin APK releases remain historical artifacts of v1.0.0-v1.1.0).
- Governance UNCHANGED: PAPER_READY=FALSE,
  LIVE_AUTHORIZATION=NOT_AUTHORIZED, 32 readiness gates, G6 pipeline
  order, frozen-strategy-domain boundary (presets live in runtime/
  for exactly this reason), secret-scan and AST invariants intact.
- Tests: 3210 passed / 8 skipped (was 3098) — 112 new tests across
  quant extensions, lab v1.5.0, accounts/2FA, historical data and
  the new monitoring routes.

## v1.1.0 — owner AI lab (feat/v1-ai-lab)

Owner mandate (2026-10-27): "aik AI ho jiss se hum total profit and
loss puch sake ... koi strategy do toh backtest kare phir paper
trading kare phir results ke sath confirmation le ke live karde ...
next market ki move predict karne ki capabilities".

- runtime/lab.py (NEW): the owner lab surfaces, honest by design —
  BarStore (owner-uploaded OHLCV history, validated, deduped, bounded,
  atomic; the lab NEVER invents market data), AssistantEngine
  (DETERMINISTIC offline rule-based analytics over the trade ledger /
  client registry / kill-switch state — no external LLM, nothing
  fabricated, honest zeros stated), LabBacktester (deterministic
  long/flat runner: ema_trend / ema_cross / rsi_reversal / breakout;
  close fills; costs-not-modeled stated in every result), LabManager
  (durable driver of the EXISTING fail-closed G6
  StrategyActivationGate: create -> backtest -> paper window ->
  explicit YES; state mirrors to strategies.json and REPLAYS through
  the gate on boot; the window is enforced BY THE GATE — evidence
  before it elapses is refused), PredictBaseline (momentum/volatility
  logistic research baseline with explicit disclaimers), BrokerCatalog
  (the honest broker surface: 7 in-repo SIMULATION/PAPER adapters +
  the BrokerAdapter interface contract for adding new brokers).
- runtime/monitoring.py: lab routes (all 503 fail-closed when the lab
  is not wired) — GET /api/lab/strategies, /api/lab/bars/{symbol},
  /api/lab/predict/{symbol}, /api/lab/brokers; POST /api/lab/strategies,
  /api/lab/strategies/{id}/backtest | /paper/start | /paper/finish |
  /confirm, /api/lab/assistant, /api/lab/bars (2 MiB bounded upload
  that ALSO drives forward paper evaluation). LabError -> 400 with the
  gate's honest refusal message; gate refusals never surface as 500.
- cli.py: the serve path now wires the lab from --monitor-state-dir
  (bars/, strategies.json, paper journals) and attaches the
  AssistantEngine to the same trade ledger + registry + health the
  owner surfaces already use. The kill switch ALSO pauses forward
  paper evaluation (a standing STOP is a stop for the whole lab).
- mobile/ (monitor APK v1.1.0+7): new LAB tab — Assistant (chat-style
  Q&A over the ledgers), Strategies (create + run backtest + start/
  finish paper + explicit confirm dialog), Predict (per-symbol
  research baseline card with the disclaimer in the UI).
- admin/ (admin panel APK v1.1.0+2): new Strategies tab (read-only
  pipeline oversight: state, symbol, backtest evidence, window) — the
  admin panel observes the lab; it cannot drive it.
- deploy/windows/push-bars.ps1 (NEW): PC-side bar uploader — CSV ->
  POST /api/lab/bars in bounded chunks with the monitor token.
- Governance UNCHANGED: PAPER_READY=FALSE,
  LIVE_AUTHORIZATION=NOT_AUTHORIZED; ACTIVATED means
  PAPER_EVALUATION_ONLY and the live path still does not exist.
- Tests: tests/test_runtime_lab.py + tests/test_lab_api.py (51 new);
  full suite 3099 passed / 8 skipped / 0 failed (3.12, sandbox).

## v1.0.0 — owner control plane + admin panel (feat/v1-control-admin-panel)

Owner mandate: "full control on my AI trading lab" + a second APK that
is an ADMIN PANEL (who is logged in, registration ledger, trade
ledger) + the real STOP control. Version line moved to 1.0.0 across
the engine and both clients (pyproject == __version__ == uv.lock ==
monitor APK 1.0.0+6 == admin APK 1.0.0+1).

- runtime/control_state.py (NEW): DurableKillSwitch — the monitoring
  API's activator/state-provider contract finally gets a REAL
  implementation in the serve path: POST /api/killswitch/activate now
  PERSISTS a durable STOP flag (monitor-state/kill_switch_state.json,
  atomic writes, corrupt-file fail-safe to INACTIVE). Monitor-only
  mode composes no trading session, so the flag is the standing halt
  decision for the install — honest about what it is and is not.
  RESUME is deliberately PC-gated: new `control-reset` CLI command
  (human principal on the machine); the API has NO reset route.
- runtime/registry.py (NEW): ClientRegistry — self-reported identity
  (X-Client-Name/Email/Kind/Device headers) observed on every
  AUTHENTICATED request; /api/users (who is connected RIGHT NOW with
  a 90 s online window) + /api/registrations (durable first-contact
  ledger, registrations.json, bounded, atomic). Stripped +
  length-capped fields; unknown kinds collapse to "other"; the bearer
  token remains the only authentication factor.
- runtime/trade_ledger.py (NEW): TradeLedger — append-only JSONL
  per-trade ledger (symbol/side/quantity/price/pnl/strategy) with
  strict validation, bounded newest-first reads, corrupt-line
  tolerance, and honest zero stats in monitor-only mode. /api/ledger/
  trades + /api/ledger/stats (per-symbol counts = the dashboard mini
  chart data; total PnL; wins/losses).
- runtime/monitoring.py: four new GET routes (all 503 fail-closed
  until wired, mirroring the pairing posture); best-effort identity
  observation after auth (never breaks serving); root route list
  updated; the bare-CLI "kill switch NOT wired" era ends.
- cli.py: serve wires DurableKillSwitch + ClientRegistry + TradeLedger
  from --monitor-state-dir (default ./monitor-state); health now
  reports the REAL stop-flag state; new control-reset command.
- mobile/ (monitor APK v1.0.0+6): identity headers on every request;
  dashboard "Trades by instrument" mini chart (hand-rolled
  CustomPainter, zero new deps) + TradesPage (per-trade ledger, PnL
  color-coded); stats fetch is non-fatal on older engines; STOP
  button relabeled as the trading stop control it is.
- admin/ (NEW admin panel APK v1.0.0+1): connect-once setup (URL +
  token + admin name/email, probe-before-save, secure storage only);
  four tabs — Overview (health + STOP TRADING), Users (who is logged
  in, online dots), Registrations (first-contact ledger), Trades
  (summary + per-trade ledger); TLS default with an explicit
  per-config plain-LAN escape; .github/workflows/build-admin-apk.yml
  (admin-apk-<sha12> release tags, same pinned-tool discipline as
  build-apk.yml).
- Tests: test_client_registry.py, test_trade_ledger.py,
  test_control_state.py, test_owner_surfaces_api.py (HTTP-level),
  TestCliWiring updated to the wired reality (activate -> 200 +
  durable state file); mobile chart widget tests; admin validation
  tests.

## Stage C — runtime integration (merged 3750dab)

- runtime/composition.py: explicit composition root (documented,
  test-pinned order: config → mac_custody → state_store →
  submission_ledger → governor → runtime → paper_session_boundary →
  reconciliation_driver → readiness_evidence → lifecycle); 32-gate
  readiness evidence chain; ComposedSession.start fail-closed (lists
  exact failed gates); cli status --gates honest per-gate
  dispositions. F-05/F-13/F-14/F-25 closed.
- C3 ReservationReconciler (duplicate signal, ambiguous preservation,
  confirmed absence, timeout ≠ release).

## Stage D — paper-ready evidence (merged b764e35)

- tests/test_paper_mode_selection_proof.py: D1 four-layer
  paper-only selection proof (capabilities registration, venue
  construction, guarded session, vocabulary audit) + paper/live
  unambiguity.
- artifacts/stage-d/: PAPER-SIMULATION-ASSUMPTIONS.md (D2),
  PAPER-SOAK-PROCEDURE.md (D4, NOT STARTED),
  PAPER-TRADING-READINESS-REPORT.md (D5: 32-gate matrix, 30
  VERIFIED_IN_CODE, 2 PENDING_OPERATIONAL_EVIDENCE, PAPER_READY
  FALSE).

## Stage E — Windows package (merged 3e57704 + 7546477)

- deploy/windows/: install.ps1 (fail-closed installer; Python ≥3.11
  gate; isolated venv; --require-hashes locked deps; wheel; smoke
  test), run-tests.ps1, run-paper.ps1 (-Confirm + MAC-key
  enforcement; loopback dashboard), README-WINDOWS-PACKAGE.md
  (layout, secrets env-only, backup/restore, safe shutdown,
  firewall/AV, honest NOT-VERIFIED-on-Windows markers).
- scripts/build_windows_package.py: deterministic zip builder
  (git-archive source, uv-exported hash-pinned lock, wheel,
  SHA256SUMS, normalized mtimes, dirty-tree refusal).
- tests/test_windows_package.py (13 contract tests).
- Forensic git tests skip explicitly in packaged-source (no-.git)
  context (2 were previously vacuous passes — honesty fix).

## Stage F — monitoring + mobile + admin (merged ddb4a2b)

- runtime/monitoring.py: token-authenticated read-only monitoring
  API + kill-switch POST (explicit confirmation + wired activator;
  503 fail-closed otherwise); rate limiting; redacted logging;
  honest provider errors.
- runtime/heartbeat.py: one-way outbound health heartbeat; data
  minimization ENFORCED in builder; https-only; graceful
  degradation.
- CLI serve flags: --monitor-{port,bind,token-file},
  --registry-{url,token-file}, --user-label, --heartbeat-interval;
  tokens via 600-perm files only.
- deploy/admin/: admin_registry.py (server-side minimized ingest,
  read-only panel, offline detection, CSV export, atomic state) +
  admin-install.sh.
- deploy/server-install.sh: one-command per-user VPS deployment.
- mobile/: Flutter monitoring client (TLS-only, secure storage,
  multi-profile, dashboard/alerts/events, kill-switch double
  confirmation) + README-APK.md (release signing + iOS TestFlight
  path).
- .github/workflows/build-apk.yml: reproducible CI APK build
  (verified action SHAs), artifact + GitHub Release attach.
- deploy/MULTI-USER-DEPLOYMENT-GUIDE.md, deploy/ADMIN-PANEL-GUIDE.md.

## Stage G — product feature layer (merged 07514ac)

- submission_ledger.py: G1 confirmed-trade spacing
  (record_fill_confirmation; reserve() reference = later of last
  submission / last confirmed trade).
- runtime/reporting.py: G2 journal-verified trade report.
- brokers/instrument_registry.py: G3 multi-asset per-class rules +
  provenance.
- brokers/allocation.py: G4 capability-aware allocation engine.
- docs/CUSTOM-BROKER-ADAPTER.md: G5 plugin interface.
- runtime/strategy_activation.py + monitoring API strategy routes:
  G6 fail-closed strategy activation gate.
- G7 prediction status exposure (API endpoint + heartbeat field +
  panel row); prediction module audited spec-compliant.
- artifacts/stage-g/FEATURE-VERIFICATION-REPORT.md.

## Post-final hardening supplement (merged 0906279 + 0dcccc2, PR #10)

- U-23 fault battery (tests/test_paper_fault_battery.py, 393 lines):
  restart-with-outstanding-orders, duplicate signals/acks, timeout
  and reconciliation fault injection.
- Simulation behavioral pinning
  (tests/test_simulation_assumptions_doc.py, 278 lines): D2
  assumptions pinned to executable behavior.
- Tamper-proof Windows package validator
  (scripts/validate_windows_package.py, 347 lines +
  tests/test_windows_package_validation.py, 29 tests): structure,
  SHA256SUMS tamper-evidence, forbidden members, unsafe paths,
  version agreement, fail-closed posture pins.
- F-18b secret-scan baseline (FIX-7): named PATTERN + two exact
  synthetic markers (github_pat_11AAAA, github_pat_11REAL) +
  fail-closed git-grep error handling; FIX-5's embedded literal
  filter REMOVED (the literal itself was credential-shaped);
  tests/test_secret_scan_allowlist.py re-pinned (5 tests).
- FIX-8: validator parses the builder's real sha256sum format
  (digest-first) + TestBuilderValidatorFormatAgreement cross-pin;
  the real package validates 8/8 (534 files).
- Suite after supplement: 2735 passed + 1 skipped; CI green on all
  6 jobs (Python 3.11/3.12/3.13/3.14 + lint-sast-coverage +
  audit-dependencies).

## Dependencies

- New RUNTIME dependencies: none (stdlib + declared pydantic/numpy/
  pandas/openpyxl only).
- New DEV dependencies: none beyond the declared pytest (Stage B
  added ruff config per its changelog entry).


## P0-P3 Master Read+Write Audit (2026-10-20, this task)

- FIX-9: runtime/operator_approval.py — TRUSTED operator-approval
  evidence for the three human gates (typed records: principal,
  decision, scope, validity window, artifact digest, reason;
  HMAC-SHA256 signing; composition-root re-verification; stable
  reason codes E_APPROVAL_*/E_EVIDENCE_UNTRUSTED). Plain
  passed=True free-text evidence for human gates is refused
  end-to-end (B-P0-03 closed). 43 adversarial tests.
- FIX-10: runtime/session_launch.py + `cli serve --session-launch` —
  the REAL session wiring (typed launch plan, deterministic replay /
  provider bar sources, SessionTick driven by the supervisor loop,
  exit-code-4 refusals). 24 integration tests prove loop
  advancement, determinism, paper-venue-only routing and
  kill-switch no-new-orders (B-P0-01 closed).
- FIX-11: reports reconciled to the code's own gate classification —
  29 VERIFIED_IN_CODE + 3 PENDING_OPERATIONAL_EVIDENCE
  (REAL_DATA/OPERATIONAL_FEED/GOVERNANCE); 9 executable drift-pin
  tests (B-P0-02 closed).
- FIX-12: submission_ledger.py conditional fcntl import — module
  imports on Windows; constructor refuses with the documented
  fail-closed message (B-P1-09 closed). 4 simulated-absence tests.
- FIX-13: run-paper.ps1 hardening — -SessionPlan passthrough, status
  tool-failure abort, verbatim exit-code propagation (B-P1-10
  closed). +2 contract tests.
- FIX-14: runtime/soak_preflight.py + `cli soak-preflight` —
  executable fail-closed soak preflight (CI-irrelevant by
  structure); 17 tests incl. the MOCK DRY RUN; PAPER-SOAK-PROCEDURE
  updated (B-P2-16 closed). NO soak started.
- artifacts/p0-p3/: the 12-task deliverable set (master audit
  report, bug register, remediation plan, canonical gate matrix,
  market support matrix, secrets/governance checklist, Windows
  platform report, soak dry-run report, owner action checklist).
- PAPER_READY stays FALSE (3 human gates open, owner-side);
  LIVE_TRADING remains NOT AUTHORIZED; historical/backtest data work
  remained excluded throughout.

---

# v4.0 — LOCAL-FIRST ONBOARDING, DUAL-MODE APK + WINDOWS MONITOR (2026-10-23)

Owner-ratified pre-decisions P1–P10 (AI_TRADING_LAB_LOCAL_FIRST_UPGRADE_PROMPT_v4.0.md).
P8 plan approved in-session before implementation. History preserved
throughout (no reset, no rebase, no force-push).

## v4-Stage B — engine pairing + mDNS + CLI

- runtime/pairing.py (NEW): salted-SHA-256 invitation verification
  (constant-time, per-config random salt, committed template carries
  hash ONLY — never a plaintext code), per-IP pairing rate limiter
  (5/min default), stable reason codes (E_PAIRING_DISABLED /
  E_PAIRING_CODE_INVALID / E_PAIRING_RATE_LIMITED), email redaction
  (***@domain), audit lines that NEVER carry code or token.
- runtime/monitoring.py: POST /api/pair — the ONE onboarding endpoint
  handled BEFORE token auth, wired only when a PairingService is
  injected; absent = 503 fail-closed (cloud default). Every other
  route unchanged (token-first; kill-switch 503 honesty preserved).
- runtime/announce.py (NEW): `_aitl-monitor._tcp.local.` mDNS
  announcement via zeroconf; graceful no-mDNS fallback; never fatal.
- cli.py: serve `--pairing-config` / `--mdns-announce` /
  `--mdns-instance`; new `pair-status` subcommand (B4 — prints
  enabled/disabled + attempt cap, never the code); malformed pairing
  config at an explicitly-given path REFUSES startup (token-file
  posture).
- deploy/server-install.sh: `--invitation-code <code>` → salted hash
  at /etc/ai-trading-lab/invitation.hash (0640 root:engine; never
  plaintext, never logged); no flag = pairing disabled; systemd unit
  wired when present.
- Version 0.4.0; NEW runtime dependency `zeroconf` (+`ifaddr` transitively)
  — the only engine-side dependency additions in this release.

## v4-Stage C — APK dual-mode onboarding

- mobile/lib/pairing.dart (NEW): pairWithEngine() client + mDNS
  discovery with graceful manual fallback.
- mobile/lib/main.dart: first-run mode choice (exactly TWO options,
  P2), cloud form (name/https-URL/code, TLS-only), local form
  (name/email/code/PC-address, one-time unencrypted-LAN warning),
  per-profile isLocal transport flag (cloud TLS-only posture
  UNCHANGED), profile mode badges, dashboard Switch action (P6 —
  never deletes profiles/tokens), v0.3.x profile backward compat.
- mobile/pubspec.yaml: version 0.4.0+1; + multicast_dns (only new
  mobile dependency).
- mobile/test/pairing_test.dart (NEW): transport-policy matrix, model
  round-trip, form validation, mDNS prefill seam, pairing client
  contract (MockClient). CI runs `flutter test`; NOT RUN locally (no
  Flutter toolchain — honest).
- .github/workflows/build-apk.yml: idempotent release-manifest patch
  (INTERNET + CHANGE_WIFI_MULTICAST_STATE).

## v4-Stage D — Windows local monitor + packaging pins

- deploy/windows/run-monitor.ps1 (NEW): monitor-only entrypoint; first
  run creates local-monitor.json (salted-hash template) +
  monitor-token.txt; loopback default; -AllowLan = explicit bind +
  UNENCRYPTED-LAN warning + LAN IP + firewall hint + mDNS on.
- deploy/windows/install.ps1: +step 6 component presence check +
  beginner what-next (local-first path documented first).
- build/validate scripts: new required components (run-monitor.ps1,
  local-monitor-config.template.json, source pairing.py + announce.py),
  run-monitor posture pin, strict template shape check, and the
  AITL_INVITE_PROBE owner-side whole-package plaintext scan (structural
  when unset — honest CI posture). Local validation: BUILD-OK +
  VALIDATION OK 10/10 with the probe set (562 packaged files, zero
  plaintext).
- Windows-host execution remains operator evidence (unchanged).

## v4-Stage E — docs replacement

- mobile/README-APK.md: rewritten two-mode onboarding (E1).
- deploy/MULTI-USER-DEPLOYMENT-GUIDE.md: §0 "CLOUD IS OPTIONAL" +
  invitation issuance/rotation/status (E2).
- deploy/windows/LOCAL-MONITOR-RUNBOOK.md (NEW): beginner runbook
  (E3) incl. the code-rotation command.
- Readiness statuses UNTOUCHED: PAPER_READY = FALSE; the 3 human
  gates open; LIVE_TRADING = NOT AUTHORIZED (this task changed
  ONBOARDING, not trading readiness).

## Stage MT5 — genuine Exness MT5 DEMO read-only market-data feed (2026-10-24, branch feat/exness-mt5-demo-market-data)

- platform/mt5_terminal.py: injectable TERMINAL BOUNDARY for the official
  MetaTrader5 package (Windows-only, optional runtime import — never a
  dependency); closed READ ALLOWLIST of module functions (order functions
  structurally unreachable); env-only credentials (SecretStr, never
  rendered/logged); numpy structured array + namedtuple payload conversion.
- platform/mt5_symbol_map.py: exact canonical→broker symbol mapping —
  validated ONLY against OBSERVED symbol_info metadata, SHA-256
  digest-stamped, re-checked at every connect (broker-side spec drift
  refuses the feed until re-validation).
- platform/mt5_market_data.py: ExnessMT5DemoFeed registered as
  "exness-mt5-demo" in ProviderFactory — POSITIVE DEMO verification at
  every connect/reconnect (REAL/CONTEST/unverifiable refused), health
  report, observed catalogue, latest bars with closed-candle enforcement
  + freshness (raise/flag), historical ranges (explicitly not
  freshness-claimed), ticks, per-batch provenance (server/build/company/
  environment/counts/epochs/staleness/payload SHA-256), structured
  MT5_E_* errors, bounded-backoff reconnect with full re-verification,
  idempotent disconnect; order surface = refusal trio ONLY.
- platform/mt5.py: optional require_demo hardening on MT5Adapter
  (backward-compatible default False).
- cli.py: `mt5-probe` operator command (--self-test / --dump-catalogue /
  --validate-map / --symbol/--bars) with honest exit codes
  (0 verified / 2 config / 6 fail-closed refusal / 7 environment NOT RUN).
- platform/feed_source_candidates.py: candidate `exness-mt5-demo`
  registered UNVETTED; BLOCKED_MARKETS unchanged; no approvals created.
- docs/OPERATOR_SOURCE_APPROVAL_PACK.md §8: candidate evidence
  requirements (probe self-test, validated map, freshness observations,
  terms review).
- Tests: unit (fake module, mocked-external-service discipline),
  paper-only negative suite (read-allowlist spy + AST scan + venue
  refusal), symbol-mapping suite, and Windows-terminal integration
  checks that auto-SKIP with BLOCKED_ON_OPERATOR_ENV (never mock-passed).
- Governance untouched: 32 gates, PAPER_READY=FALSE,
  LIVE_AUTHORIZATION=NOT_AUTHORIZED, 30-day soak + preflight unchanged;
  no gate marked passed; no live-trading flag introduced.

## Fix — monitor-only serve no longer blocked by the readiness gate (2026-10-27)

- runtime/service.py: the fail-closed startup gate (exit 2) now guards
  trading-ABLE surfaces only — a composed session tick (tick_fn) and
  the unauthenticated read-only dashboard. The v4.0 monitor-only
  surface (`run-monitor.ps1` -> `serve --no-dashboard --monitor-*`:
  authenticated monitoring API + invitation pairing, NO session, NO
  dashboard, kill switch honestly 503) starts without readiness
  evidence, exactly as the v4 local-first plan specifies ("Starts
  (monitor-only, NO trading session ...)"). Previously the D-4/D-5
  default gate (structurally FALSE with no evidence) refused EVERY
  serve startup, which made the shipped local-monitor beginner path
  unusable — found first-hand on the owner's Windows Python 3.15.0
  install (smoke PASS, then serve refused at step 2 of the runbook).
- Bare supervisor shell, dashboard-enabled serve, and
  `--session-launch` keep the original refusal semantics (existing
  tests unchanged and still green: CLI subprocess pin, F-05 wiring).
- tests/test_runtime_service_lifecycle.py: new TestMonitorOnlySurface
  pins — monitor-only starts without evidence / with a session tick
  refuses / with the dashboard refuses.
- Governance untouched: PAPER_READY stays FALSE; LIVE_AUTHORIZATION
  NOT_AUTHORIZED; the gate still refuses every trading-capable serve
  configuration; no trading surface was added anywhere.

## Fix (mobile v0.4.3) — dashboard no longer fails on JSON-array collection responses (2026-10-27)

- mobile/lib/main.dart: `positions()` and `orders()` parsed every
  response through the Map-only `_getJson` cast (`as Map<String,
  dynamic>`). In monitor-only mode the API's default providers return
  JSON ARRAYS (`[]`), so the first `/api/positions` poll raised
  _TypeError AFTER pairing had succeeded — the dashboard then showed
  "connection error (_TypeError)" with every panel null even though
  the server log showed 200s (`POST /api/pair -> OK`, `/api/health ->
  200`, `/api/positions -> 200`, and pnl/risk/feed never reached).
  Latent since v4.0: monitor-only serve could not start at all until
  the readiness-gate fix above, so no real phone had ever exercised
  this path.
- New `_getDynamic` helper parses defensively (any JSON shape);
  `positions()`/`orders()` normalize null to an empty list; `pnl()`
  normalizes null to an empty map. health/risk/feed stay Map-typed
  (the API returns objects there). The dashboard UI already handled
  both shapes (`_positionsCard` renders an empty list as
  "open positions: 0").
- No server-side change; no API contract change; no governance
  surface touched (PAPER_READY FALSE / LIVE_AUTHORIZATION
  NOT_AUTHORIZED unchanged).

## Fix (v4.0.2) — monitor-only default providers + rate limit (2026-10-27)

- runtime/monitoring.py: the default `pnl_provider`, `feed_provider`,
  `risk_provider`, and `killswitch_state_provider` were bound DIRECTLY
  to `_absent`, an arity-1 function (`component` required). Every
  default-provider invocation therefore raised
  `TypeError: missing 1 required positional argument` and the
  fail-closed `_provider` wrapper honestly reported
  `{"state": "ERROR", "detail": "provider failure (redacted):
  TypeError"}` — which the phone dashboard displayed as
  Risk/PnL/Feed = ERROR + a red FEED banner even though nothing was
  actually wrong (the components are merely not wired in monitor-only
  mode). Defaults are now zero-arg lambdas
  (`lambda: _absent("pnl")` etc.), mirroring the already-correct
  `prediction_provider`. First exercised in the field once the
  monitor-only serve fix (above) made the surface reachable — the
  owner's screen recording shows exactly this symptom.
- runtime/monitoring.py: default `rate_limit_max` 60 -> 300 per
  60 s window. The real dashboard client polls 5 endpoints every
  10 s (30/min baseline) and legitimately exceeds 60 with the events
  page / manual refresh — owner-observed 429 bursts
  (`GET /api/health -> 429`). 300/min keeps the brute-force friction
  (still enforced on unauthenticated traffic too) with polling
  headroom. Injectable, so tests keep tiny explicit limits.
- tests/test_monitoring_api.py: TestDefaultProviderPins — HTTP + direct
  pins that pnl/feed/risk/killswitch defaults return ABSENT (never
  ERROR), and that the DEFAULT limiter absorbs a 40-request polling
  burst. Full suite at this commit: 3003 passed / 8 skipped / 0 failed
  (CPython 3.12, sandbox).
- Governance untouched: PAPER_READY=FALSE; LIVE_AUTHORIZATION
  NOT_AUTHORIZED; no trading surface added or enabled.

## Fix (mobile v0.4.4) — honest 429 handling + calmer poll cadence (2026-10-27)

- mobile/lib/main.dart: HTTP 429 was reported as raw
  "unexpected status" noise. It is a TRANSIENT server-side throttle,
  not a broken connection: `_statusException` now maps
  429 -> "server busy (rate limited) — retrying automatically" and the
  next poll cycle recovers (server default raised to 300/min in the
  same release, so 429s should effectively disappear in local use).
- Dashboard poll cadence 10 s -> 15 s: halves the request rate
  (5 endpoints per cycle) while staying responsive for a monitoring
  surface.
- No auth/contract change; pairing flow untouched; governance
  untouched (PAPER_READY=FALSE / LIVE_AUTHORIZATION=NOT_AUTHORIZED).
