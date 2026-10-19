# FEATURE-VERIFICATION-REPORT (Stage G, Part 10 — 2026-10-20)

Audit-then-extend discipline applied throughout: every feature was
audited for what ALREADY existed before anything was added. Nothing
was duplicated; nothing was fabricated. Suite evidence for this
report: **2685 passed + 1 skipped (138.76s, exit 0)** on the Stage G
tree.

Legend: EXISTED (pre-Stage-G, cited), ADDED (this run, cited),
PARTIAL (core complete, named residual), NOT_IMPLEMENTED (explicit).

## G1 — Trade confirmation + spacing

| Item | Status | Evidence |
| --- | --- | --- |
| Min 1s between SUBMISSIONS (B2 governor) | EXISTED | submission_ledger.py `min_spacing_seconds=1.0`; tests/test_submission_ledger.py |
| Confirmed-trade events wired into the spacing model | **ADDED** | `SubmissionLedger.record_fill_confirmation()` — durable fill confirmations; reserve() spacing reference = LATER of last submission and last confirmed trade; restart-conservative |
| Differential proof (fill re-arms spacing where submission spacing alone would allow) | **ADDED** | tests/test_g1_confirmed_trade_spacing.py (9 tests) |
| Documented timing model | **ADDED** | submission_ledger.py docstrings + G1 method docstring |

## G2 — Trade ledger reporting

| Item | Status | Evidence |
| --- | --- | --- |
| Ledgers + PnL modules (foundation) | EXISTED | runtime/ledgers.py (9-ledger family, hash chains, MAC custody), runtime/pnl.py |
| Reporting API (totals, per-trade P&L, win rate, per-strategy/per-broker breakdowns, session summaries) | **ADDED** | runtime/reporting.py `build_trade_report()` — journal-verified (chain verification FIRST; ReportRefused on failure); attribution honest (payload field → session context → UNATTRIBUTED) |
| Every number reconciles against the journal | **ADDED** (tested) | tests/test_g2_trade_reporting.py (12 tests incl. fail-closed refusals) |

## G3 — Instrument registry (multi-asset)

| Item | Status | Evidence |
| --- | --- | --- |
| Venue discovery + provenance + registry sync | EXISTED | brokers/instruments.py (fail-closed discovery, capability snapshots, sync) |
| Stocks / crypto / metals / forex per-class validation rules | **ADDED** | brokers/instrument_registry.py `MultiAssetInstrumentRegistry` — per-class rule sets (crypto base/quote + power-of-ten lots; forex 3-letter codes + lot band + pip ticks; metals XAU/XAG/... + USD quote + ounce fractions; equity quote + lot floor + cent ticks); provenance REQUIRED; class-drift refused; unknown-class rules BLOCKED |
| Default 4-class reference registry | **ADDED** | `default_multi_asset_registry()` |
| Tests | **ADDED** | tests/test_g3_instrument_registry.py (19 tests) |

## G4 — Multi-broker allocation

| Item | Status | Evidence |
| --- | --- | --- |
| Capability registry (foundation) | EXISTED | brokers/capabilities.py `CapabilityRegistry` (startup-only, drift-refusing) |
| Allocation engine (weights + limits + capability-aware routing + fail-closed config) | **ADDED** | brokers/allocation.py — weights sum EXACTLY 1; per-broker open-order/notional caps; capability-aware (kind/TIF/reduce-only); UNKNOWN broker BLOCKED; deterministic tie-break; no-fallback refusal |
| Per-broker ledger entries | **ADDED** | `AllocationDecision.ledger_payload()` |
| Audited allocation changes | **ADDED** | `AllocationConfigChange` + `validate_allocation_change()` |
| Tests | **ADDED** | tests/test_g4_broker_allocation.py (19 tests) |

## G5 — Custom broker option

| Item | Status | Evidence |
| --- | --- | --- |
| Adapter ABC + deterministic venue base | EXISTED | brokers/interface.py, adapters/_mock_core.py |
| Unknown/unverified capabilities = UNKNOWN = BLOCKED | EXISTED (layered) + **ADDED** (routing) | capabilities.py registry refusals; allocation.py refuses unregistered ids; test_g4 + test_paper_mode_selection_proof.py |
| Documented plugin interface | **ADDED** | docs/CUSTOM-BROKER-ADAPTER.md (interface table, capability declaration, registration path, MANDATORY mock-first test families, worked example, REAL-review path documented out-of-scope) |

## G6 — Strategy chatbot + activation gate

| Item | Status | Evidence |
| --- | --- | --- |
| Backtest + validation + leakage detection (foundation) | EXISTED | strategy/backtest.py, strategy/validation.py (+ StrategyValidator, LeakageDetector) |
| Submission pipeline (structured form + free text; LLM assist PARSE-ONLY vocabulary) | **ADDED** | runtime/strategy_activation.py `StrategyActivationGate.submit()` (parse_source USER \| LLM_ASSIST_PARSE_ONLY; anything else refused) |
| Automated backtest step (evidence-object required) | **ADDED** | `record_backtest(BacktestEvidence)` — objective evidence only, never claims |
| 30-day validation cycle scheduling (short-cycle dev simulations JOURNALED as deviations) | **ADDED** | `schedule_validation(cycle_days=30)`; short cycles journaled with `short_cycle_deviation: true` |
| Explicit activation gate (backtest + validation + explicit YES) | **ADDED** | `activate()` — re-checks the evidence chain AT the gate; ambiguous/no/absent ⇒ INACTIVE; activation is PAPER_EVALUATION_ONLY, live_trading NOT_AUTHORIZED journaled |
| API surface (chat-form submit / status / activate) | **ADDED** | monitoring.py POST /api/strategy/submit, GET /api/strategy/{id}, POST /api/strategy/{id}/activate (requires {"confirm": "YES"}; endpoint can NEVER bypass the gate) |
| Mobile chat UI (APK screen) | **PARTIAL** | Engine-side API + gate complete and tested; the Flutter Strategies screen is a thin client over these endpoints — listed as residual mobile polish (dashboard/alerts/kill-switch screens shipped in Stage F) |
| Admin-panel strategy chat | **DELIBERATELY OMITTED** | The owner's registry heartbeat is data-minimized to identity+health by ratified mandate; routing user strategy data to the OWNER's panel would violate it. Strategy submission lives on each USER's own server + app. Design decision documented here. |
| Tests | **ADDED** | tests/test_g6_strategy_activation.py (17 tests) + monitoring strategy endpoints (5 tests) |

## G7 — Crash and event predictions

| Item | Status | Evidence |
| --- | --- | --- |
| crash.py + calibration (Brier/log loss/ECE/reliability/Platt) + drift (PSI, STABLE→INVALID with mandated actions) + evaluation | EXISTED (audited vs spec §9/§10: compliant) | prediction/{crash,calibration,drift,evaluation}.py; 13 prediction test files |
| Prediction status through the monitoring API | **ADDED** | GET /api/prediction (honest ABSENT default; injected provider when wired) |
| Prediction status in the heartbeat + admin panel | **ADDED** | `prediction_status` joined the TEST-ENFORCED minimized vocabulary (still NO positions/PnL/orders/broker/credentials); registry stores + panel renders a prediction row; roster CSV includes it |
| Prediction status in the APK | **PARTIAL** | The dashboard consumes /api/health (which can carry prediction fields when wired); a dedicated prediction card is residual mobile polish |
| Calibration/drift/evaluation gaps vs spec | **NONE FOUND in audit** | Spec §9/§10 requirements verified present (metrics + state machine + fail-closed monitor); residual: live operational drift data requires the soak |

## Cross-cutting

- PAPER_READY remains FALSE throughout. LIVE TRADING REMAINS NOT
  AUTHORIZED everywhere (all new surfaces carry the marker + tests).
- No risk control was weakened: every addition is fail-closed
  (refusals over defaults; evidence over claims; UNKNOWN = BLOCKED).
- New dependencies: NONE (all stdlib + existing declared deps).
