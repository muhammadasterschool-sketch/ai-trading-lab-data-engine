# 01 — MASTER AUDIT REPORT (Stage A3/A4)

**Repo:** ai-trading-lab-data-engine @ `main` `4e9be355` (clean, fsck-clean)
**Scope:** Full source audit — every production module area, CLI, runtime construction, config, risk gates, OMS, brokers, throttling, persistence, provenance, logging/redaction, CI, deploy templates, audit docs cross-check.
**Method:** 4 parallel deep-dive explorations (broker/OMS routes; persistence; risk/runtime/config; deploy/CI/secrets/prediction/strategy) with exact file:line evidence, plus direct personal verification of the four most safety-critical claims by reading the actual control flow. READ+WRITE path map included per prompt A4.

---

## 0. Executive summary

The repository is a **structurally paper/mock-only trading-systems engine in excellent engineering condition**: all seven broker adapters are deterministic in-memory mocks with zero network code; live trading is refused at **four independent structural layers**; the risk-gate chain (24 mandatory checks → fingerprint-bound OMS approval → 9-gate venue submission pipeline → fill-time kill-switch re-check) is genuinely fail-closed; recovery is evidence-driven and conservative; no secrets exist anywhere in tree or history; the strategy activation gate makes `LIVE_ACTIVE` structurally unreachable; and the 2,403+1skip baseline is real (re-run, exit 0).

The systemic weaknesses are **compositional rather than gate-logical** — exactly the Milestone A / Stage C targets:

1. **Submission throttling is volatile and non-atomic** (Milestone A B1/B2 core gap): the only rate ledger is an in-memory list, absent from persisted state; no reservation system; no cross-process locking; restart wipes the submission budget (fail-open direction for throttling).
2. **Zero file locking anywhere in the codebase**: single-writer is a deployment assumption, not an enforced invariant.
3. **No production composition root exists**: `TradingRuntime` is constructed only in tests; the CLI `serve` command is an honest supervisor shell that certifies nothing and drives no trading session.
4. **Deployment template breaks its own state contract**: `ProtectSystem=strict` without `ReadWritePaths=` means the documented per-user state persistence cannot work as templated.
5. **A handful of fail-open edges** in otherwise fail-closed discipline (best-effort security audit log; feed-staleness watchdog off by default; uncapped authoritative venue).

Findings register: **25 findings** — 0 Critical-live-risk (system is paper-only and structurally refuses live), 6 High, 10 Medium, 9 Low/Info. Full detail in `02-FINDINGS-REGISTER.md`.

---

## 1. Architecture map (verified)

```
CLI (cli.py — validate/report/storage-report/status/check-boundary/serve)
  └─ serve → PaperRuntimeService (supervisor shell; readiness exit 2; loopback exit 3;
             drives NO trading session — tick_fn seam only)
Library composition (NO production root yet — tests only):
  TradingRuntime.__init__ (runtime.py:322-471): explicit constructor injection:
    MAC custody → LedgerFamily → OMS → KillSwitchManager → RiskLimits → RiskEngine
    → RiskGate → RuntimeRiskLimits → PaperExecutionAdapter → ExitManager
    → RuntimeReconciliation → TradingMemory → PnLEngine → DecisionEngine
    → TradePlanBuilder → RegimeEngine
  start() chain: self-check (pinned model hashes) → state store MANDATORY
    → readiness gate MANDATORY → recovery LOAD→VERIFY→RESTORE→RECONCILE
    → critical kill-switch ⇒ HALT → persisted HALTED terminal → RUNNING

THE ONE order path (runtime.py:2102-2283 _execute_plan):
  RiskGate.evaluate (24 checks, incl. order_rate_limit, max_open_orders)
    → OMS.create_order → validate_order → risk_approve (fingerprint-bound)
    → venue boundary: submission_block_reason() → venue.submit_order
        → RuntimeAuthoritativeVenue.submit_order (broker_execution.py:1238)
        → BrokerSession.submit_order (session.py:402 — 9-gate pipeline)
        → adapter.submit_order (deterministic mock; idempotent)
    → OMS.submit → acknowledge → fills deferred to later bars (venue polls only)

Module areas (21): actions, benchmarks, brokers (7 mock adapters + session +
capabilities + instruments + redaction + errors + interface), derivatives,
discovery, experiment_registry, hermes, infra, knowledge, paper, pit,
platform, prediction (31 modules, 11k lines), providers, quant, research,
research_validation, risk, runtime, strategy, tenancy.
```

## 2. READ + WRITE path map (prompt A4)

### 2.1 Every route that can reach a broker-submission function

| # | Route | Guards in front | Evidence |
|---|---|---|---|
| R1 | Decision path → `_execute_plan` (runtime.py:1930→2102) | Full 24-check RiskGate + fingerprint-bound OMS approval + venue block check | runtime.py:2102-2283 |
| R2 | Operator close (RUNNING) → `_execute_plan` (runtime.py:961) | Same gate chain + closing-order carve-outs (risk-reducing only) | runtime.py:874-996 |
| R3 | Protective exits (SL/TP/crash) `_submit_protection_exits` → `_execute_plan` (runtime.py:2713) | Same gate chain | runtime.py:2671-2800 |
| R4 | Side-band session `attach_runtime_paper_session` (broker_execution.py:1671) | RuntimeRiskGateBridge (22-check gate over live state, records capacity on pass — over-counting fail-safe) + RuntimeKillSwitchGate | broker_execution.py:210-348, 173-207 |
| R5 | Cancel paths (NOT submission): operator cancel runtime.py:838; HALT close :1026; TTL expiry :1701; KS fill enforcement :2372 | failures ledgered, never silenced | broker_execution.py:1315-1338 |

**Verified non-routes:** CLI has no trading command (cli.py:1-185; `status` honestly hardcodes `RUNTIME_HEALTH: ABSENT`, `RECONCILIATION_HEALTH: NOT_WIRED`); `platform/mt5.py:269-288` raises `MT5OrderRefusedError` "LIVE TRADING NOT AUTHORIZED"; `actions/`/`strategy/`/`hermes/`/`paper/` have no order-submission capability; `data_engine.brokers` is imported only by the brokers package itself and `runtime/broker_execution.py` (single seam, grep-verified). Only network code in repo: read-only public market data (`providers/transport.py`, `providers/binance_public.py` — which refuses any api key) and the Windows MetaTrader5 import inside the refusing read adapter.

**Guard pipeline inside BrokerSession.submit_order (fixed order, session.py:402-487):** account isolation → health → reconciliation/degraded → kill-switch (missing gate = refuse all) → risk gate (missing = refuse) → journal idempotency (same key+digest = exact replay; key reuse = refuse) → capability/precision pre-venue checks (kind, TIF, SL/TP, reduce-only, symbol, lot/tick/notional) → bounded retry (only CONNECTIVITY/TIMEOUT/RATE_LIMIT, deterministic backoff).

### 2.2 Every code path that mutates persistent state

| # | Path | Writes | Guarded? |
|---|---|---|---|
| W1 | Runtime start/restart (`start()` runtime.py:542) | state.json + journal.jsonl | Strong: refuses without store; self-check; readiness; recovery+reconcile (runtime.py:613-646, 1355-1615) |
| W2 | Per-bar processing (end-of-bar + post-fill snapshots) | state.json | Schema-validated; write failure ⇒ HALT (runtime.py:1992, 1746, 3356-3382) |
| W3 | Kill-switch trip / operator cancel/close | immediate persist | Fail-closed wrapper `_persist_safe` (runtime.py:740-1170) |
| W4 | Account drawdown breach | persist + ACCOUNT trip + terminal HALT | runtime.py:3273-3354 |
| W5 | Bad/stale bars | persist (DEGRADED persists across restart) | runtime.py:3449-3631 |
| W6 | Venue order submission | BrokerSession journal (atomic rewrite, no fsync, no lock) | session.py:706-816 |
| W7 | Venue attach/recovery | venue book rebuild; journal sync records | broker_execution.py:1477-1554 (fail-closed) |
| W8 | CLI `serve` | **nothing** (supervisor shell) | service.py |
| W9 | Ingest/export scripts | data/manifests/**, data/exports/** (direct write, no atomicity) | Weak — only FS-06 raw-copy divergence check |
| W10 | Provider FS audit trail | audit JSONL (unlocked RMW) | Chain verify on read; fork risk under concurrency |
| W11 | SecurityManager.audit_log | src/audit.log (best-effort, errors swallowed) | **None — fail-open** |
| W12 | Tests | test_storage* dirs (repo root), /tmp fixed paths | Hygiene only |

### 2.3 Fail-closed claim verification (control-flow read, not doc trust)

- **Paper-only posture:** VERIFIED at 4 layers — REAL execution-mode descriptors unregistrable (capabilities.py:163-172); BrokerSession refuses non-MOCK_DETERMINISTIC adapters (session.py:309-314); mock core refuses REAL execution + REAL account modes at construction (_mock_core.py:139-150); mt5 platform raises on execution (platform/mt5.py:269-288). Plus `LiveAuthorizationGate` always denies without human token from a registry that starts empty (paper/evaluation.py).
- **"Gate before order":** VERIFIED — RiskGate.evaluate at runtime.py:2152-2160 precedes OMS.create_order; non-passing ⇒ return with no order object created.
- **"Missing evidence = failure":** VERIFIED in readiness (32-gate evidence framework, absent evidence ⇒ explicit FALSE, no env bypass, consistency validator refuses TRUE-with-failures — readiness.py:55-209), risk gate (unknown ⇒ FAIL across data_staleness/crash_risk/concentration/liquidity/spread/volatility/drawdown/loss/rate/open-orders), and recovery (any verification failure ⇒ refusal to start).
- **"Restart never clears a kill switch":** VERIFIED — runtime.py:667-705; critical switch at start ⇒ HALTED.
- **"A lost ack NEVER infers failure":** VERIFIED — broker_execution.py:1488-1492; UNKNOWN journaling with replayable ack (session.py:725-753); ambiguous orders block retries (oms.py:443-448).
- **FAIL-CLOSED GAPS FOUND** (where claims do NOT hold): volatile rate ledger (F-01/F-02), best-effort security audit log (F-10), no locking (F-03), systemd state contract (F-04). See findings register.

## 3. Audit highlights by area

**Runtime/OMS (runtime/, 3,647-line runtime.py):** closed 17-state OMS machine (oms.py:49-100) with no skip transitions; fingerprint-bound risk approval (oms.py:379-422); EXECUTION_UNCERTAIN on ambiguity; identity-bound recovery (config digest + session id + ensemble hashes, runtime.py:1401-1464); fill replay invariants before resume (reconciliation.py). Residual: crash window between venue accept (2218) and OMS.submit (2269) leaves order in RISK_APPROVED ∉ LIVE_STATES → not polled post-recovery (F-07).

**Risk (risk/ + runtime/risk_gate.py + runtime/kill_switch.py):** 24 mandatory checks all fail-closed; zero-override semantics (breach raises + records in hash-chained violation log); kill switch 7 scopes, unprivileged trip, human-principal-gated reset with pre-authorization for ACCOUNT/GLOBAL; ARCH-F1 testing opt-out exists but is warning-pinned and never used by production wiring (runtime wires trip_on_breach=True default). Residual: hardcoded context values in internal path (market_open/paper_mode/model_valid=True — honest only in replay frame, F-14); hardcoded RuntimeRiskLimits (leverage 1.0, single-asset 0.30, F-14).

**Brokers (brokers/):** clean broker-neutral surface (interface.py) with contract-tested growth (BROKER_ADAPTER_SURFACE); deterministic mock core with per-instance rate windows + idempotency; capability registry fail-closed on unknown/drift; redaction layer complete (opaque credential holder, scrub, leak scanner). Residual: authoritative paper venue uncapped (F-06); TIMEOUT retry safety rests on idempotency contract assumption (F-24).

**Paper (paper/):** simulation-only, no credential fields anywhere; deterministic fill model (latency ≥1 bar, adverse half-spread, impact slippage, participation-cap rejection of oversized orders, LIMIT never fills through); duplicate client_order_id protection; three-way fail-closed reconciliation; unkeyed-SHA256 audit chain (keyed-MAC upgrade = pending human decision, F-25).

**Persistence (runtime/state.py, brokers/session.py, security.py):** ExecutionStateStore is the strongest writer (atomic tmp+os.replace, file fsync, digest-verified journal, fail-closed load) but lacks directory fsync and ALL locking; session journal atomic but not fsynced; security.py contains the weakest writers in the repo (fail-open audit_log; unlocked RMW chain). Torn journal tail bricks the store — fail-closed but availability-hostile (F-12).

**Provenance/feed:** hard bar-quality gates (data_gate.py:285-381); REAL_VERIFIED requires 9-stage chain, synthetic never promoted; operational feed gate with human-approved source registry + freshness (≤900s); in-session wall-clock watchdog exists but **disabled by default** (F-13).

**Config:** no file/env config loading — constructor-injected frozen pydantic, invalid ⇒ construction failure ⇒ process refuses to start. Only 4 env-var sites in src/, all audited. MAC key absence raises (never silently unkeyed).

**Deploy (deploy/):** systemd template-instance unit with genuine sandboxing but **missing ReadWritePaths** (breaks documented state contract under ProtectSystem=strict — F-04) and ~15 further hardening directives (SystemCallFilter, PrivateDevices, etc.); secrets.env.example clean (names-only, empty values); loopback-only enforcement consistent between unit, CLI, and service.

**CI (.github/workflows/ci.yml):** matrix 3.11/3.12 (omits declared 3.14 — F-15); determinism = 3 consecutive full runs; frozen Phase-3 blob verification (11 strategy files pinned to git show 13fdc7e — Stage G must not touch these); history-wide secret scan (4 prefixes only — F-18); pip-audit strict job but **not on push to main** (F-16); no lint/type/SAST/coverage. Actions pinned to SHAs; least-privilege permissions.

**Secrets:** ZERO hardcoded credentials found (repo-wide grep across 7 families, matching the repo's own forensic report); redaction layers verified at broker boundary, error taxonomy, tenancy vault, security config; MAC custody key-in/never-out discipline verified.

**Prediction (31 modules):** contract-complete vs spec (crash bands, calibration Brier/log-loss/ECE/Platt, PSI drift, chronological partitions with purge/embargo, 13-stage fail-closed estimator, human-only graduation registry, 45-attack red-team suite); honest BLOCKED empirical status (0 verified real years; 30-day paper evaluation never exercised). Gap: `dataset_version="UNRECORDED"` default (F-20).

**Strategy (strategy/ + platform/strategy_lab.py + paper/evaluation.py):** deterministic backtest engine with leakage detection; 20-state lifecycle machine with evidence-bound transitions; LIVE_ACTIVE structurally unreachable; 30-day paper rule + human-token graduation. Gaps for Stage G: no automated backtest API, no evidence auto-wiring, no validation-cycle scheduling.

**Instruments/Allocation (Stage G prep):** instrument discovery fail-closed but `_canonical_instrument` hardcodes CRYPTO/SPOT (F-17 — stocks/metals/forex cannot register via broker discovery); NO multi-broker allocation/routing engine exists (G4 greenfield).

**Audit docs cross-check (106 root docs):** 15 most important identified; 3 spot-checked (credential forensic "0 secrets" claim; CI WP-12 verbatim claim; readiness 32-gate claim) — **all 3 hold against code**. Doc drift noted: ci.yml has grown beyond the WP-12 snapshot (deployment-validator step + audit-dependencies job postdate the record).

## 4. Baseline (re-verified this session)

**2,404 collected → 2,403 passed, 1 skipped, 34 warnings, 88.5s, exit 0** on Python 3.14.8 with the declared dependency set. Historical claim VERIFIED.

## 5. What this means for Stage B (Milestone A)

The engine's gate logic is sound; Milestone A is a **durability + atomicity + composition** project, not a gate-logic project:

- **B1** must turn the volatile in-memory rate accounting into a durable, flock-protected, atomically-reserved ledger checked BEFORE any broker call, with crash-conservative reconstruction.
- **B2** must enforce owner-ratified spacing (≥1s between submissions, ≤5/60s, ≤10 open) at the actual submission boundary, wall-clock-regression-protected, restart-deterministic.
- **B3** must close the OMS durable-outcome edges (venue-accept/OMS-submit crash window; journal-failure-after-ack; fail-closed incident+halt on failed durable transitions).
- **B4** sweeps the remaining register findings (locking, fsync, systemd ReadWritePaths, CI matrix, fail-open audit log).

Ordered groups, tests, acceptance criteria, effort, and risk are in `04-PATCH-PLAN.md`.
