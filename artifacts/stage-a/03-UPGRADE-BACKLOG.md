# 03 — UPGRADE BACKLOG (Stage A → all stages)

Everything that should be upgraded, ordered by engineering stage. Derived from the findings register (02) plus the Stage B-G mandates. Nothing here weakens a risk control; all upgrades preserve fail-closed posture.

## 1. Milestone A core (Stage B) — durability, atomicity, spacing

| # | Upgrade | Why | Findings |
|---|---|---|---|
| U-01 | Durable submission-rate ledger: flock-protected, atomic reserve-then-submit, durable order identity, crash-conservative reconstruction, capacity refusal BEFORE broker call | Rate budget currently volatile + non-atomic; owner-ratified defaults unenforceable across restart/processes | F-01, F-02, F-19 |
| U-02 | Submission-spacing governor at the actual submission boundary: ≥1s spacing, ≤5/60s, ≤10 open (owner-ratified paper defaults), wall-clock-regression protected, deterministic conservative restart, no bypass path | Spacing not enforced at the boundary; wall-clock regressions unhandled | B2 mandate |
| U-03 | Venue-level rate capability on the authoritative paper venue | Defense-in-depth backstop | F-06 |
| U-04 | OMS durable-outcome edges: venue-accept→OMS-submit crash window detection (EXECUTION_UNCERTAIN incident, fail-closed halt); any failed durable outcome transition ⇒ incident + halt | Ambiguity currently unflagged post-recovery | F-07, B3 mandate |
| U-05 | Converge authoritative + bridge accounting on the ledger | Asymmetric over/under-count today | F-19 |

## 2. Persistence + locking hardening (Stage B4)

| # | Upgrade | Findings |
|---|---|---|
| U-06 | Store-level exclusive flock at open (refuse concurrent open); unique tmp names (pid+counter) | F-03 |
| U-07 | fsync file+dir on session journal replace; dir fsync on state store replace | F-08, F-09 |
| U-08 | SecurityAuditTrail locked append (chain-fork prevention) | F-11 |
| U-09 | SecurityManager.audit_log: operator path, fail-closed, no repo-tree writes | F-10 |
| U-10 | Journal tail-repair runbook + audited recovery subcommand (explicit confirmation, never silent) | F-12 |

## 3. Deployment + CI (Stage B4 + E)

| # | Upgrade | Findings |
|---|---|---|
| U-11 | systemd: ReadWritePaths + StateDirectory + UMask + full hardening set (SystemCallFilter=@system-service, PrivateDevices, ProtectHostname/Clock/Proc, RestrictNamespaces, CapabilityBoundingSet=, MemoryDenyWriteExecute) | F-04 |
| U-12 | Template validator: require ReadWritePaths-under-strict coherence + new directives | F-04 |
| U-13 | CI: add Python 3.13/3.14 legs; ruff lint; coverage artifact; bandit SAST | F-15 |
| U-14 | CI: pip-audit on push to main; extend secret-scan prefixes (PEM/OPENSSH/EC, xox, AIza) | F-16, F-18 |
| U-15 | Tests: tmp_path for storage fixtures (no repo-root or fixed /tmp dirs) | F-22 |
| U-16 | CLI: register `validate <dataset_id>` argument (aligns with G2/G6 reporting) | F-21 |

## 4. Runtime integration (Stage C)

| # | Upgrade | Why |
|---|---|---|
| U-17 | Explicit production composition root (documented construction order, no hidden globals) wired to supervisor | F-05 |
| U-18 | Readiness gate evidence suppliers for: durable ledger, governor, reconciliation, state store, session+kill-switch, feed freshness/provenance, config validity, risk-limit disposition, deployment-storage capabilities, mode-appropriate broker capabilities | C2 mandate; 5 gates missing per audit |
| U-19 | Conservative reconciliation driver (journalled reservations vs OMS records; confirmed-absence vs timeout; preserve ambiguous; prevent duplicate submission; durable auditable decisions) | C3 mandate |
| U-20 | Operational config: feed staleness watchdog mandatory (900s paper default), gate context + risk limits injected from validated config, MAC key provisioning path | F-13, F-14, F-25 |

## 5. Paper evidence (Stage D)

| # | Upgrade |
|---|---|
| U-21 | Paper-mode-only venue selection proof (test-pinned: no code path selects live account in paper mode) |
| U-22 | Deterministic simulation assumption docs (fills, rejections, partials, slippage, fees, latency) consolidated + test-pinned |
| U-23 | Fault tests: restart with outstanding paper orders; duplicate signals; duplicate acks; timeouts; reconciliation behavior |
| U-24 | Paper soak PROCEDURE document (duration, success criteria, monitoring, abort conditions) — NOT started |
| U-25 | PAPER-TRADING-READINESS-REPORT.md gate-by-gate; PAPER_READY stays FALSE |

## 6. Packaging (Stage E/F)

| # | Upgrade |
|---|---|
| U-26 | Windows zip: source + locked reqs + install.ps1 + run-tests.ps1 + run-paper.ps1 + state/log layout docs + env-only secrets + backup/restore + safe shutdown |
| U-27 | Fresh-venv end-to-end validation of the Windows path (record exact Python, firewall/AV notes) |
| U-28 | GitHub Release assets + SHA256SUMS |
| U-29 | Authenticated read-only monitoring API (token auth, loopback default, rate-limited, redacted) + kill-switch endpoint with confirmation |
| U-30 | Flutter monitoring APK (server URL + token login, multi-profile, secure storage, TLS-only, zero embedded secrets) built via GitHub Actions |
| U-31 | deploy/server-install.sh one-command VPS deployment (per-user isolation) + MULTI-USER-DEPLOYMENT-GUIDE.md |
| U-32 | Admin registry + panel (one-way outbound heartbeat only, data-minimization enforced by tests) + admin-install.sh + ADMIN-PANEL-GUIDE.md |

## 7. Product feature layer (Stage G — audit-then-extend)

| # | Upgrade | Current state (verified) |
|---|---|---|
| U-33 | G1: confirmed-trade events wired into spacing model | Governor (U-02) is the enforcement point; wiring needed |
| U-34 | G2: trade-ledger reporting API (totals, per-trade P&L, win rate, per-strategy/per-broker breakdowns, session summaries) reconciling against journal | ledgers.py/pnl.py exist; reporting API missing |
| U-35 | G3: multi-asset instrument registry (stocks/crypto/metals/fx + per-class rules) | BLOCKED by F-17 hardcode; extend, don't duplicate |
| U-36 | G4: multi-broker allocation (registry, weights, capability-aware routing, fail-closed validation, audited changes) | Greenfield — nothing exists |
| U-37 | G5: custom-broker plugin interface (config + documented adapter class; UNKNOWN capabilities BLOCKED; mock-first testing path) | capabilities.py fail-closed core exists; plugin interface missing |
| U-38 | G6: strategy chatbot + activation gate automation (submit → auto-backtest → 30-day paper cycle scheduling → results → explicit YES/NO) | Gate exists (strategy_lab + evaluation); automation/scheduling/API missing |
| U-39 | G7: prediction status exposure via monitoring API/APK/admin alerts; close calibration/drift/evaluation gaps | Prediction module contract-complete; exposure missing; F-20 |

## 8. Known deferred / governance-owned

- iOS build (Stage F4): documented TestFlight path only — requires Apple Developer Program ($99/yr).
- Keyed-MAC ledger activation (F-25): owner provisions `RUNTIME_LEDGER_MAC_KEY` at deployment; soak evidence records key_id.
- Live trading: PERMANENTLY out of scope. Every upgrade keeps REAL execution modes structurally refused.
