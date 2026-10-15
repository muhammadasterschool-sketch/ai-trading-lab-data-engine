# BATCH 8 — INDEPENDENT RUNTIME AUDIT, SAFETY-GATE VERIFICATION, AND PAPER-READINESS EVIDENCE

```text
Task:           Batch 8 of the continuation mandate — independent audit
Repository:     muhammadasterschool-sketch/ai-trading-lab-data-engine
Session date:   2026-10-13 (Asia/Karachi)
Starting commit: 423715161a676421a0bd2e521cd44de83c3ca15a (Batch 7 head)
Working branch:  audit/batch-8-independent-runtime-audit (from 4237151)
Environment:    uv 0.13.0 · Python 3.12.15 · Linux container
Method:         every claim below was re-established FIRST-HAND this
                session (code tracing + executed commands); prior-session
                reports were treated as claims, not facts
```

---

## 1. Repository state and evidence chain (Phase 0)

| Check | First-hand result |
|---|---|
| Working tree at start | clean on `feat/runtime-risk-broker-neutral-tenancy` @ `4237151` |
| Batch 6 commit exists | `39e793990b6ee8348cc54a9263c6a800d211687f` — diff inspected (`git show --stat`): 6 files, runtime safety residuals |
| Batch 7 commit exists | `423715161a676421a0bd2e521cd44de83c3ca15a` — diff inspected: 11 files, instrument discovery + Bitget mock |
| Remote verification | `git ls-remote origin` (authenticated): `feat/runtime-risk-broker-neutral-tenancy` remote head == `4237151` — Batches 2–7 (`ff5f7d3`, `9796831`, `9c02682`, `7b532bb`, `39e7939`, `4237151`) are all on the remote as ancestors |
| All local branch tips | every local branch head exactly matches its remote counterpart (`feat/broker-neutral-execution-architecture` d945833, `feat/master-market-data-import` 7f384e6, both `fix/paper-runtime-*`, `fix/ingestion-*`, `main` d49b822, `phase-4a/4a1-architecture-correction` d49b822) — zero unpushed commits at audit start |
| Open PRs | PR #1 head `7f384e6` (feat/master-market-data-import), PR #2 head `d945833` (feat/broker-neutral-execution-architecture) — both still open, neither merged; `refs/pull/*/merge` present |
| PR CI results | NOT VERIFIED for current heads: the session PAT authenticates git push (verified by `git push --dry-run`) but returns HTTP 401 for the REST API, so check-run state could not be queried. Historical evidence on record: PR #1 platform CI run 38147316090 SUCCESS (3.11+3.12) at `4e6dfc5`. No CI claim is made for the advanced head `7f384e6` |
| Batch 5 report | read in full (`/home/z/my-project/download/BATCH_5_AUTHORITATIVE_VENUE_INTEGRATION_REPORT.md`, 152 lines) — every property it claims was re-verified against code and executable tests below |

**Baseline reproduction (documented command, CI-identical):**
`uv run pytest -q -p no:cacheprovider` → **2,215 passed + 1 skipped, 31 warnings, 80.52s** — exactly the reported Batch 7 baseline. The single skip is `tests/test_runtime_models.py:92` ("baseline is seed-free by design") — a documented, pre-existing, benign parametrization skip, not a hidden failure.

No discrepancy between reported and actual state was found at Phase 0, so the audit proceeded on the real checkout. No branch was silently switched, no history rewritten, no PR merged, no deploy performed.

## 2. Authoritative broker execution path (Phase 1) — **VERIFIED**

Path traced end-to-end in source (`src/data_engine/runtime/runtime.py`, `broker_execution.py`, `oms.py`, `risk_gate.py`, `kill_switch.py`; `src/data_engine/brokers/session.py`):

1. **Single submission path, no side-band leak.** `_execute_plan` (runtime.py:2087) is the ONE order path: `RiskGate.evaluate` (all 22 checks incl. RUN-DD-1) → `OMS.create_order` (idempotent duplicate refusal) → `validate` → `risk_approve` → **venue boundary when attached** (runtime.py:2160–2241: block-reason check → `RuntimeAuthoritativeVenue.submit_order` → refused ⇒ OMS REJECTED + ledgered; uncertain ⇒ OMS UNKNOWN+RECONCILING + runtime EXECUTION_UNCERTAIN) → `OMS.submit` + `acknowledge`. `attach_authoritative_paper_venue` (broker_execution.py:1556) refuses: un-started runtime, live pre-venue orders, missing spec for the runtime's symbol, credential/account mismatch, non-`RuntimePaperExecutionAdapter` factories, double attachment. The Batch 3 side-band factory remains separate and does not touch the runtime OMS.
2. **One coherent risk decision.** The session's risk gate is `RuntimeOrderPathRiskGate` (broker_execution.py:1003): an identity-binding VERIFICATION that the request maps 1:1 onto an OMS order in `RISK_APPROVED` state with matching fingerprint fields (symbol/side/kind/quantity/limit). It never re-decides risk; foreign identities, non-approved states, divergent parameters ⇒ REFUSED. `client_order_id` IS the OMS order id — one identity from decision to venue.
3. **Deterministic paper fills.** The venue hosts the runtime's own fill model (`RuntimePaperExecutionAdapter`); `test_venue_fills_bit_identical_to_internal_path` and `test_organic_full_chain_through_the_venue` pin venue-mode == internal-mode.
4. **No duplicate fills/ledger effects.** `poll_order` returns only the delta beyond OMS-held fills; book divergence (OMS > venue) raises `BridgeContractError` (fail closed); OMS `create_order` refuses idempotent-key reuse; `test_partial_fills_accounted_exactly_once`, `test_key_reuse_with_different_details_refused`.
5. **UNKNOWN is never an inferred fill.** Ambiguous submission/poll ⇒ UNKNOWN + RECONCILING + EXECUTION_UNCERTAIN (bars, polls, submissions blocked); recovery only through ledgered reconciliation adopting venue truth (`resolve_ambiguity`, phantom cross-check, `adopt_venue_order`); `test_unknown_ack_blocks_until_reconciled`, `test_timeout_exhaustion_adopts_venue_truth`, `test_unexplainable_phantom_stays_blocked`, `test_restart_inside_unknown_stays_blocked`.
6. **Restart recovery.** `_recover_existing_state` (runtime.py:1339): LOAD → VERIFY identity → RESTORE OMS/orders/fills/positions/kill-switch/ledger/pending state → RECONCILE; unprovable state ⇒ RECOVERY_REQUIRED/HALTED, never auto-resume. Venue book rebuild with deterministic-regeneration verification (split run == whole run); `test_restart_is_idempotent_and_deterministic`, `test_recovered_halt_is_not_silently_running`, plus the 10 mandated restart points in `tests/test_runtime_recovery_integration.py` (44 tests).
7. **Capability/precision fail closed.** Lot-misaligned quantity ⇒ PRECISION_INVALID (QUANTITY); tick-misaligned LIMIT price ⇒ PRECISION_INVALID (PRICE); attach without spec refused; Bitget lot-step/min-notional refusals; `test_precision_refusals_distinguish_price_and_quantity`, `test_tick_misaligned_limit_price_refused`, `test_missing_instrument_spec_refuses_attach`.
8. **Broker failure modes explicit.** Definitive refusal ⇒ OMS REJECTED (venue never saw it); ambiguity ⇒ UNKNOWN; execution-adapter exceptions ⇒ UNKNOWN + RECONCILING + incident; degraded session / unhealthy adapter / non-RUNNING runtime refuse with NAMED reasons; kill-switch fill-time cancellation routed through the venue boundary.
9. **Mock cannot be mistaken for real.** `BrokerSession.__init__` (session.py:309) REFUSES any adapter whose `execution_mode` is not `MOCK_DETERMINISTIC`; `test_venue_execution_mode_is_paper_mock_only`, `test_descriptor_is_registered_and_mock_only`; the adapter package docstring states NO network / NO real credentials / NO real orders.

**Verdict: the authoritative integration claimed by Batch 5 is REAL in code and pinned by 26 RED-first venue tests + 44 recovery tests + 52 session-guard tests + the shared parametrized contract suite (156 adapter-contract tests across all five mock venues).**

## 3. Batch 6 safety controls (Phase 2) — all **CLOSED/VERIFIED**

| Control | Code evidence | Test evidence |
|---|---|---|
| RUN-ST-1 feed watchdog | `_feed_is_stale`/`_stale_bar` (runtime.py:3408–3546); default OFF (`max_feed_staleness_seconds=None`) documented as deterministic-replay posture; missing/unusable timestamp ⇒ STALE when enabled (fail closed); future-dated bars not stale (pre-start gate's domain); stale bar ADMITTED (fills/TTL/drawdown/protection/persistence continue) with decision/entry chain skipped; ledger payload deterministic (INV-01: bar ts + limit only); bridge `_bridge_bar_age` (runtime.py:3054) honest wall-clock age so external orders fail the `data_staleness` check on stalled feeds | 10 tests incl. recovery-when-feed-catches-up, stale-settles-inflight, stale-submits-protective-exits, stale-enforcement-survives-halting-drawdown, bridge honesty ×2 |
| RUN-CA-1 operator cancel/close | `operator_cancel_order` (runtime.py:765): unknown/terminal ids loud refusals; §28 states refuse; real OMS request→finalize pair + venue boundary; ORDER_CANCELLED_OPERATOR incident + counter + immediate persistence. `operator_close_position` (runtime.py:862): RUNNING ⇒ MANUAL_CLOSE through the authoritative gate→OMS path (closing carve-outs; risk failure = loud refusal, no override); HALTED ⇒ immediate settlement at latest admitted bar, cancels every live order for the symbol first, ONE full MARKET fill through `_apply_execution_fills`, venue deliberately not consulted under HALT and that is RECORDED as an operator-owned out-of-band settlement; all other states refuse | 15 tests: reason required, unknown/terminal refusals, live cancel, under-HALT cancel, refused-while-uncertain ×2, flat refusal, running authoritative, risk-failure loud, halted immediate, frozen-exit cancellation, before-start refusal |
| RUN-PM-1 partial-fill metric | `_apply_execution_fills` re-queries the LIVE OMS order after each fill; completing fill not counted; metric unprovable ⇒ not counted | `test_completing_fill_not_counted_as_partial` |
| RUN-OBS-1 exit-risk observability | `_submit_protection_exits` returns `(orders, failed)`; failures surface in `BarOutcome.risk_failed_checks` on both the normal (runtime.py:1995) and stale-bar (3542) paths; gate already ledgers RISK_ASSESSMENT_FAIL | `test_exit_risk_failure_surfaced_in_outcome` |
| RUN-DA-1 dead state | `_entry_orders_by_symbol` absent from `src/` (grep: zero source hits) | `test_dead_entry_orders_map_removed` (asserts absence) |
| RUN-DD-1 account drawdown | `_peak_account_equity` (3118) pure replay function of persisted state (unanchorable fill ⇒ None ⇒ fail closed); `_enforce_account_drawdown` (3185) on EVERY admitted bar; strict breach ⇒ ACCOUNT kill-switch trip + terminal HALT + IMMEDIATE persistence; unknown ⇒ no trip but gate refuses new orders; restart never clears a critical trip | 14 tests incl. exact-limit boundary (entry permitted, no trip), above-limit refusal, price-driven breach, inflight freeze, closing-permitted-during-breach, unknown-fails-closed, trip-survives-restart, recomputed-identically |
| Snapshot config compat | `_config_evolution_match` (1273): exact field-wise decomposition with persisted-view digest re-verification (tamper evidence); shared-field diff / removed field / undeclared drift ⇒ hard refusal; legacy suffix-strip recomputation; opt-in `allow_snapshot_config_evolution` default FALSE; `SNAPSHOT_CONFIG_EVOLUTION` contains only `max_feed_staleness_seconds` + the opt-in flag itself — **no risk-policy field can be silently overridden by evolution**; loud `SNAPSHOT_CONFIG_EVOLVED` incident on resume | 6 tests: same-config restart, shared-field refusal, config-view persisted, legacy default refused, legacy opt-in resumes, flag validation |

Default posture confirmed: incompatible snapshots fail closed without the explicit operator opt-in; the opt-in never overrides active risk policy.

## 4. Batch 7 instrument discovery and catalog (Phase 3) — **VERIFIED**

`src/data_engine/brokers/instruments.py` (342 lines) + `tests/test_broker_instrument_discovery.py` (21 RED-first tests):

- **Discovery fail-closed**: disconnected adapter refused (a fabricated catalog is worse than none); foreign `broker_id` in spec refused; duplicate venue symbols refused; capability DRIFT vs `CapabilityRegistry` refused (changes are explicit versioned events); unknown-symbol catalog lookup fails closed; catalog immutable.
- **Registration ≠ eligibility**: `sync_catalog_to_platform_registry` lands instruments DISCOVERED; the sync NEVER touches data state, verification, monitoring or eligibility; provider mappings start UNVERIFIED; second-venue discovery merges into the ONE canonical identity (flagged-duplicate path, mapping merged — identity never forks).
- **Registry discipline** (`tests/test_platform_registry.py`, 28 tests): `REAL_VERIFIED` requires evidence; `REAL_UNVERIFIED` allows research but NOT paper; `SYNTHETIC` blocks research eligibility; live trading always NOT AUTHORIZED; operator approval cannot activate live; records immutable with audit events.
- **Data-state honesty** (`tests/test_platform_datasets.py`): fabrication evidence (pre-listing OHLC, anachronistic venues, uniform grids) marks SYNTHETIC; `REAL_UNVERIFIED` never becomes `REAL_VERIFIED` without evidence; invalid records are not repaired.
- **Counts**: the platform registry exposes registration/eligibility/monitoring as DISTINCT explicit fields (`strategy_eligible` default False, `monitoring` toggle, data state); trade counts are projections fed from the runtime's confirmed-fill ledger (`TradeRecord` is caller-supplied; `fills`/`partial_fill_events` metrics increment ONLY inside `_apply_execution_fills` — requested/enabled/watchlisted instruments are never counted as executed trades).
- **Idempotency/persistence**: repeated discovery + resync is the flagged-duplicate merge path (idempotent by construction); restart escalation is impossible because sync never touches eligibility/verification state.
- **Bitget status — EXACT**: `BitgetSpotMockAdapter` is a **mock spot-v2 semantics venue** (the fifth deterministic mock): MARKET/LIMIT only; SL/TP as SEPARATE trigger orders (attached stops refused with the venue-native alternative); NATIVE_CLIENT_ID idempotency; BALANCES_ONLY spot account; tick/lot/min-notional filters; representative v2 error codes (40001/43007/43025/42911) documented for re-verification when a real-adapter phase is authorized. **There is NO real Bitget adapter, NO Bitget market-data provider, NO trading permission.** Mock semantic coverage is not claimed as real broker support.

## 5. Multi-tenant security boundary (Phase 4) — **VERIFIED at contract level; infrastructure limits stated**

`src/data_engine/tenancy/` + `tests/test_tenancy_security.py` (46 tests):

- Cross-user read/write denial in both directions with positive controls; control-plane service cannot read tenant trading data; owner manages records/licenses only.
- Tenant-ID manipulation: claimed-vs-authenticated mismatch denied AND audited, checked BEFORE resource lookup.
- Mobile read-only: cannot write anything, cannot read secret store or database, no order-placement path exists, short-lived sessions. The Batch 6 operator APIs (`operator_cancel_order`/`operator_close_position`) exist ONLY on `TradingRuntime` (grep: zero references elsewhere in `src/`) — in-process operator surface, unreachable through the tenancy authorization layer.
- Secret hygiene: reveal requires an allowing decision; cross-tenant reveal refused; values never in audit/decisions; vault repr redacted; fingerprint is a digest; redaction placeholder not storable; duplicates refused.
- License/session gating: SUSPENDED/REVOKED/EXPIRED deny everything; revocation immediate; expired session denied; unknown resource denied by default.
- Provisioning: approved tenant gets a contract PLAN; `execute_plan` refused BY DESIGN (dry-run only).

**Honest infrastructure limitations (unchanged, per docs/MULTI_USER_TENANCY_SECURITY_FOUNDATION.md):** no identity provider, no token-issuing service, no network surface, no per-tenant deployment exists. The tenancy layer is a fail-closed in-process contract foundation; production-grade isolation additionally requires the unimplemented infrastructure plus end-to-end tests. No such claim is made.

## 6. Regression, determinism, strategy integrity (Phase 5)

| Verification | Command | Result |
|---|---|---|
| Full suite ×3 consecutive | `uv run pytest -q -p no:cacheprovider` | **2,215 passed + 1 skipped** — 80.52s / 81.08s / 81.22s, identical outcomes |
| Focused subsystems | 5 files (residuals/drawdown/venue/discovery/tenancy) | **141 passed** in 20.03s |
| Frozen Phase 3 blobs | `final_gate_verify.py` check 1 | **11/11 byte-identical to `main@13fdc7e`** |
| SUB-18 manifest pin | check 2 | **13/13 manifest hashes match committed state** |
| Secret scan (CI-identical, ALL history) | `git grep -nE "github_pat_[A-Za-z0-9_]{20,}\|ghp_…\|AKIA…\|sk-…" $(git rev-list --all)` | **0 hits** — working tree likewise clean |
| Mock-literal note | — | the stricter local heuristic in `final_gate_verify.py` flags 6 occurrences of the intentional redaction-test fixture `"mock-secret-material-DO-NOT-PRINT"` in 3 broker test files. These are deliberate test constants proving secrets never render — NOT credentials. The CI credential-shape scan (authoritative) returns 0 |
| Skip/flake audit | `-rs` run + skip source | single documented skip (seed-free baseline model); zero flaky, zero weakened assertions, zero disabled checks observed across the three runs |
| Live-execution enablement | session.py:309 + pins | no test or fixture can construct a REAL execution-mode adapter against a session; venue execution mode pinned paper-mock-only |
| System posture | `PAPER_TRADING_READINESS_FINAL_REPORT.md` | **PAPER_READY = FALSE; LIVE NOT AUTHORIZED; real venue execution disabled** — unchanged through Batch 8 |

## 7. Readiness gate audit (Phase 6)

Verdict formula: `PAPER_READY = ALL 32 GATE_NAMES TRUE` (readiness.py:55–92; no shortcut, no override; one FALSE/absent gate ⇒ runtime start REFUSED — pinned by `test_readiness_false_refuses_start` and per-gate refusal tests).

| Gate | Status | Reason (first-hand this session) |
|---|---|---|
| DATA_READY, PIT/SEQUENCE/BASELINE/MODEL/PREDICTION/CALIBRATION/UNCERTAINTY/REGIME/CRASH/RL_GOV (10) | PASS | objective evidence re-executed inside the 2,215-test suite ×3 |
| DECISION/TRADE_PLAN/RISK/KILLSWITCH/OMS/EXECUTION/PERSISTENCE/RECOVERY/PARTIAL_FILL/SLTP (10) | PASS | re-audited this session (§2–§3); no weakening found; fail-closed posture intact |
| RECONCILIATION/LEDGER/MEMORY/AUDIT/REPLAY/OBSERVABILITY/SECURITY/TESTS (8) | PASS | same suite + secret scans + ledger integrity tests |
| REAL_DATA_READY | **FAIL** | 0 REAL_VERIFIED datasets; VERIFIED_YEARS = 0; master bundle 3× REAL_UNVERIFIED + 1× INVALID — external data dependency, honestly blocked |
| OPERATIONAL_FEED_READY | **FAIL** | machinery complete and integration-proven, but `binance-public-spot` is UNVETTED (no human SRC-APPROVAL), no feed provisioned, no continuity evidence |
| GOVERNANCE_READY | **FAIL** | open human actions: PAT rotation confirmation, keyed-MAC key provisioning, data-source approval decision |

**PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY.** Batch 8 deliberately did NOT attempt to flip any gate: no approval records, coverage, key provisioning, source approvals, connectivity, or sign-off were fabricated. External requirements remain BLOCKED, as required.

## 8. Real-versus-mock broker capability matrix (truthful scope)

| Venue | Adapter shipped | Execution mode | Real-execution-ready? |
|---|---|---|---|
| Paper/simulation (reference) | `PaperBrokerAdapter` | MOCK_DETERMINISTIC | NO — by design |
| MT5-class (Exness/XM-style) | `MT5StyleMockAdapter` | MOCK_DETERMINISTIC | NO — MT5 semantics simulated |
| Binance spot | `BinanceSpotMockAdapter` | MOCK_DETERMINISTIC | NO — REST/filter semantics simulated |
| Bybit v5 | `BybitV5MockAdapter` | MOCK_DETERMINISTIC | NO — spot/linear semantics simulated |
| Bitget spot v2 | `BitgetSpotMockAdapter` | MOCK_DETERMINISTIC | NO — clientOrderId semantics simulated |
| Runtime-authoritative venue | `RuntimePaperExecutionAdapter` | MOCK_DETERMINISTIC | NO — hosts the runtime's own fill model |
| Real brokers (any) | none | — | **NOT STARTED** (future, separately-reviewed phases M3–M6) |

No network, no real credentials, no real orders anywhere in this repository. LIVE TRADING NOT AUTHORIZED.

## 9. Defects found, fixed, and regression tests (Phase 7)

**Zero reproducible defects were found; therefore zero fixes and zero new regression tests were applied.** Two suspicions were investigated to closure without code changes:

1. *CI workflow YAML suspected corrupt* (trigger lines displayed as `branches: ain, "phase-4a/**"]`) — **refuted by byte-level hexdump**: the file genuinely contains `branches: [main, "phase-4a/**"]` / `branches: [main]`; the anomaly was an output-display artifact. No change made (no-defect).
2. *`final_gate_verify.py` secret-scan FAIL* — **classified as tool sensitivity, not a defect**: the 6 hits are the intentional mock redaction fixture; the CI-equivalent credential-shape scan over all history returns 0. Recorded here rather than "fixed" by weakening either the scan or the fixtures.

Per the mandate, no test was deleted, relaxed, or re-pinned; no expected value was changed; no failure was suppressed to obtain a green result.

## 10. Remaining operator actions (ranked)

1. **ROTATE THE session PAT (exposure #19)** — a fine-grained GitHub PAT was pasted in chat AGAIN this session. It was used ONLY for authenticated git operations via the local credential store (file mode 0600, outside the repository; never echoed in commands, logs, reports, or source; never committed). Revoke and rotate it at GitHub → Settings → Developer settings → Fine-grained tokens now.
2. **SRC-APPROVAL** for `binance-public-spot` (docs/OPERATOR_SOURCE_APPROVAL_PACK.md) — unlocks OPERATIONAL_FEED_READY's human half.
3. **Provision the operational feed** on the paper-session host; let `build_paper_feed_evidence` evaluate freshness/mapping/continuity live.
4. **Supply + verify REAL data** through the nine-stage chain (REAL_DATA_READY; VERIFIED_YEARS > 0).
5. **Provision the keyed-MAC custody key** (mechanism + runbook ready; no key exists).
6. Decide PR #1 / PR #2 merges (both open, base `main` at `d49b822`; PR #1's head was advanced to `7f384e6` by the Batch-7-session push — CI on that head NOT VERIFIED this session; review before merging).
7. Watchdog opt-in for any live-clock paper session (`max_feed_staleness_seconds`, runbook §7).

## 11. Final verdict

The authoritative paper-trading execution path is **safe, correctly integrated, recoverable, observable, and supported by reproducible evidence** at the code level this session: single coherent risk admission, deterministic fills, exactly-once accounting, UNKNOWN-reconciles-from-venue-truth, restart-idempotent recovery, fail-closed capability/precision, mock-only venues, tenant contract isolation — all pinned by executable tests that were re-run first-hand (2,215+1 ×3 deterministic, 141 focused, frozen 11/11, secrets 0 across all history).

**PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY. LIVE TRADING NOT AUTHORIZED.** The remaining distance to TRUE is exactly the three human/data gates above; no code blocker was found by this audit, and none was manufactured.
