# MULTI-BROKER EXECUTION ARCHITECTURE — AUDIT, DESIGN AND IMPLEMENTATION PLAN

```text
Document Type:  Architecture proposal + audit + implementation plan (Phase M1)
Phase:          Multi-Broker Architecture Mandate (operator-issued 2026-10-12)
Authority:      A — AUTHORITATIVE for the broker-neutral execution design
Status:         CURRENT (Phase M1 implemented; Phase M2 implemented
                 TWICE-STAGED — Batch 3 side-band bridge §6a, then
                 Batch 5 AUTHORITATIVE runtime integration §6b which
                 completes the phase; Batch 7 §6c added the fifth mock
                 venue (Bitget) + instrument discovery/catalog/
                 platform-registry sync; Phases M3–M6 planned, NOT
                 started)
Version:        1.3.0
Last Updated:   2026-10-13 (Batch 7 — Bitget mock + instrument
                 discovery/catalog/registry sync)
```

---

## 0. Mandate scope and honest status

The operator mandate: design the platform to support multiple brokers
and exchanges through a **broker-neutral execution interface** —
never assuming MT5 is the only execution venue. Adapters: MT5-compatible
brokers (Exness/XM only where account support is verified), Binance,
Bybit, paper/simulation. Mock adapters and deterministic tests FIRST.
No real orders, no live credentials. Frozen contracts preserved.
Paper readiness may NOT be marked true until the full runtime chain is
integrated and independently tested.

**What this cycle delivered (Phase M1):**

- A current-architecture audit (§1) with exact file references.
- A normalized broker-neutral execution interface (§2) implemented as
  `src/data_engine/brokers/` (models, errors, capabilities, redaction,
  interface, guarded session).
- Four DETERMINISTIC MOCK adapters (paper / MT5-style / Binance-spot-style /
  Bybit-v5-style) implementing real venue semantics in memory — zero
  network, zero real credentials, zero real orders.
- An explicit capability registry + capability matrix (§3).
- Regression + failure-injection tests (§5): 236 new tests; full suite
  1,769 + 1 skipped → **2,005 + 1 skipped** (zero regressions; frozen
  contracts byte-identical; secret scan 0).
- A risk-ordered implementation plan (§4) for the REAL integrations —
  all of them deliberately NOT STARTED pending review of this document.

**What this cycle deliberately did NOT do (by mandate):**

- No real Binance/Bybit/MT5 network adapters (mocks only — Phase M3/M4/M5).
- No rewiring of the frozen 22-module paper runtime onto the new
  interface (Phase M2 — separately reviewed).
- No live credentials, no real orders, no broker connections.
  **LIVE TRADING REMAINS NOT AUTHORIZED. PAPER_READY = FALSE (unchanged).**

---

## 1. Current architecture audit (as inspected, first-hand)

The repository already contains a substantial, frozen-contract
execution stack. The audit below lists what EXISTS, with exact
references, and the GAP the multi-broker layer must close.

### 1.1 Execution interfaces (existing)

| Component | File | Surface |
|---|---|---|
| Paper execution adapter (runtime-side) | `src/data_engine/runtime/execution.py` | `PaperExecutionAdapter.execute(...)` — deterministic multi-bar partial fills over a bar series; `PAPER_MODE_STRUCTURAL_ISOLATION = True`; no credentials/endpoints/network by construction |
| Phase-11 paper simulator + gateway | `src/data_engine/paper/simulator.py`, `src/data_engine/paper/gateway.py` | `PaperOrderGateway` (duplicate client-order-id protection), `ExecutionSimulator`, `ReconciliationEngine`, hash-chained `AuditLogger` |
| MT5 read-only adapter | `src/data_engine/platform/mt5.py` | `MT5Adapter` — fail-closed market-data/account reads via injectable `MT5TerminalSession`; **order surface ALWAYS refused** (`MT5OrderRefusedError`); DEMO/REAL/UNKNOWN account discipline |
| Market-data providers | `src/data_engine/providers/transport.py`, `binance_public.py`, `rate_series.py` | single-attempt stdlib HTTP transport (typed failures, injectable sleeper), Binance public spot klines (closed-candle enforcement, allowlist), forex rate-series (structurally not a candle feed) |
| Trading runtime | `src/data_engine/runtime/runtime.py` | `TradingRuntime` — the authoritative orchestration path (`start`, `_execute_plan`, `_process_pending_orders`, `_apply_fill_to_position`, `_recover_existing_state`, `_persist`) |

### 1.2 Order models (existing)

- `src/data_engine/paper/models.py` (frozen Phase 11):
  `PaperOrder` (MARKET/LIMIT only, `client_order_id`, no broker/account/
  credential fields anywhere), `Fill` (full cost decomposition),
  `PaperPosition` (BUG-002-corrected average-cost engine).
- `src/data_engine/runtime/oms.py`: `OMSOrder` (MARKET/LIMIT only) and
  the authoritative 14-state lifecycle machine (CREATED → VALIDATED →
  RISK_APPROVED → SUBMITTED → ACKNOWLEDGED → PARTIALLY_FILLED ⇄ FILLED;
  CANCEL_PENDING → CANCELLED; EXPIRED; UNKNOWN → RECONCILING; REJECTED;
  FAILED), deterministic `idempotent_order_id`, RT-F1 fingerprint-bound
  risk approval, overfill refusal, TTL expiry, `export_state`/
  `restore_state`.

### 1.3 Risk controls (existing — and already broker-agnostic)

- `src/data_engine/runtime/risk_gate.py`: 21 mandatory fail-closed
  checks (`paper_mode` … `risk_reward`); any failure ⇒ `passed=False` ⇒
  the order MUST NOT be sent; the OMS structurally refuses
  `RISK_APPROVED` without a passing assessment bound to the SAME order
  fingerprint.
- `src/data_engine/runtime/kill_switch.py`: 7-scope hierarchical
  `KillSwitchManager` (ORDER/STRATEGY/SYMBOL/MODEL/PORTFOLIO/ACCOUNT/
  GLOBAL); unprivileged trip, human-gated reset, critical-scope
  authorization, persisted; fill-time enforcement closed RUN-KS-1/2 in
  commit `1c286d2`.
- `src/data_engine/risk/engine.py`, `risk/portfolio.py`:
  `RiskEngine` (signed-netting BUG-003-corrected position limits).

### 1.4 Persistence and reconciliation (existing)

- `src/data_engine/runtime/state.py`: `EXECUTION_STATE_SCHEMA v1.1.0` —
  atomic snapshots (tmp + `os.replace`), append-only hash-chained
  journal, tamper-evident, `StateStoreError` fail-closed.
- `src/data_engine/runtime/reconciliation.py`: three-way
  OMS ↔ fills ↔ positions reconciliation; mismatch ⇒
  `RECONCILIATION_REQUIRED` ⇒ new orders STOP (§32 discipline).
- `src/data_engine/runtime/recovery.py`: restart recovery integrated
  into `TradingRuntime.start()` (LOAD → VERIFY → RESTORE → RECONCILE →
  RESUME; persisted HALT is terminal).

### 1.5 Market-data models (existing)

- `src/data_engine/provider.py`: `MarketDataProvider` /
  `ProviderFactory` framework (dataset-oriented).
- `src/data_engine/providers/binance_public.py`: Binance public spot
  klines as a governed data source (NOT an execution venue).
- `src/data_engine/runtime/feed_gate.py`, `feed_composition.py`,
  `readiness.py`: the operational-feed gate (32nd readiness gate) and
  the 30+ fail-closed readiness gates.
- `src/data_engine/platform/registry.py`: instrument registry with
  multi-provider symbol resolution (`find_by_any_provider_symbol`).

### 1.6 The GAP (why a broker-neutral layer is needed)

The existing stack assumes exactly ONE execution venue: the internal
paper simulator. Concretely:

1. **Order vocabulary is MARKET/LIMIT only** (`OMSOrder`, `PaperOrder`
   validators) — no STOP/STOP_LIMIT, no time-in-force, no attached
   SL/TP at the order boundary, no reduce-only.
2. **No instrument metadata model** — tick size / lot step / minimum
   notional / max quantity live nowhere; nothing refuses an unaligned
   or under-minimum order at a venue boundary.
3. **No capability concept** — nothing records that Binance spot has no
   plain STOP, that MT5 is hedging/ticket-based while Bybit is
   one-way/netting, or that Binance carries SL/TP as separate orders.
4. **No account model / isolation** — the paper engine has no accounts
   at all (by design); nothing binds one adapter instance to exactly
   one broker account.
5. **No credential redaction machinery** — existing modules are proudly
   credential-FREE (correct for paper); the day real credentials exist,
   the boundary must already be redaction-safe.
6. **No normalized error taxonomy** — venue-native codes (-1013, 10004,
   10019, …) have nowhere to be translated; retry policy cannot
   discriminate without swallowing.
7. **No venue-level idempotency mechanism model** — MT5 comment-field
   vs Binance `newClientOrderId` vs Bybit `orderLinkId`.
8. **No venue reconciliation contract** — the runtime reconciles its
   own internal books; nothing reconciles journal ↔ venue truth.

Phase M1 closes ALL of these gaps at the INTERFACE level — without
touching a single frozen file.

---

## 2. The broker-neutral interface (implemented)

Package: `src/data_engine/brokers/` (new, additive; nothing existing
was modified). Contract version: `BROKER_NEUTRAL_CONTRACT_VERSION =
"1.0.0"`.

```
strategy / runtime ──► central RiskGate + KillSwitch ──► BrokerSession
                                                              │ (gates BEFORE venue)
                                                              ▼
                                                    BrokerAdapter (interface.py)
                                                              │
              ┌──────────────┬───────────────┬───────────────┬──────────────┐
              ▼              ▼               ▼               ▼              
        paper-mock       mt5-mock        binance-mock     bybit-mock    (future real
      (PaperBroker-   (MT5StyleMock-  (BinanceSpot-   (BybitV5Mock-    adapters, M3–M5)
       Adapter)         Adapter)        MockAdapter)     Adapter)
```

### 2.1 Normalized domain models (`models.py`)

- `Side` (BUY/SELL), `OrderKind` (MARKET/LIMIT/STOP/STOP_LIMIT),
  `TimeInForce` (GTC/IOC/FOK/DAY), `VenueOrderStatus`
  (PENDING_NEW/OPEN/PARTIALLY_FILLED/FILLED/CANCELLED/REJECTED/EXPIRED/
  **UNKNOWN** — ambiguous outcomes are first-class, never guessed away),
  `ConnectionState`, `AccountMode` (DEMO/REAL/UNKNOWN — REAL refused
  everywhere this phase), `PositionMode` (NETTING/HEDGING/
  BALANCES_ONLY).
- `InstrumentSpec` — the ONE precision/lot/notional truth
  (`tick_size`, `lot_step`, `min/max_quantity`, `min_notional`,
  `contract_size`) with `quantize_price/quantize_quantity` helpers and
  a fail-closed `order_problems()` check (misalignment is a REFUSAL —
  a silently modified order would diverge from the risk-approved
  fingerprint).
- `OrderRequest` — `client_order_id` (MANDATORY idempotency key) +
  `account_id` (MANDATORY isolation key) + full normalized order
  shape (attached SL/TP capability-gated, `reduce_only`).
- `OrderAck`, `VenueFill`, `PositionRecord` (netting per symbol /
  hedging per ticket / balances-only), `BalanceRecord`, `AccountInfo`.
- Reconciliation models: `ExpectedOrderState`,
  `ReconciliationMismatchKind` (ORDER_MISSING_AT_VENUE /
  PHANTOM_ORDER_AT_VENUE / STATUS_DIVERGENCE / FILL_QUANTITY_DIVERGENCE),
  `VenueReconciliationReport`.

### 2.2 Normalized error taxonomy (`errors.py`)

`BrokerErrorCategory` (closed set): CONNECTIVITY / TIMEOUT / RATE_LIMIT
(the only RETRYABLE three) / AUTH / INVALID_ORDER / UNSUPPORTED /
INSUFFICIENT_FUNDS / MARKET_CLOSED / GATE_REFUSED / **UNKNOWN_STATE** /
INTERNAL. Typed errors carry `broker_id` + the venue-native code
verbatim in `venue_code` for audit. `UnknownOrderStateError` must name
the `client_order_id` — it means "the venue MAY hold a live order";
the session journals UNKNOWN and blocks everything until
reconciliation. Defense-in-depth `scrub_text`/`redact_mapping` keep
composed diagnostics secret-free.

### 2.3 Capability registry (`capabilities.py`)

`BrokerCapabilities` descriptors (frozen, coherence-validated):
`order_kinds`, `time_in_force`, `sl_tp` semantics (ATTACHED vs
SEPARATE_ORDERS vs UNSUPPORTED), `position_mode`, `idempotency_key`
mechanism (NATIVE_CLIENT_ID / COMMENT_FIELD / INTERNAL_JOURNAL),
`supports_reduce_only`, `account_modes`, `RateLimitPolicy`
(orders/window + requests/window + retry_after),
`ReconciliationStyle`, `ExecutionMode` (**MOCK_DETERMINISTIC** for all
four shipped adapters; REAL descriptors are REFUSED at registration —
live trading is NOT AUTHORIZED). `CapabilityRegistry` refuses
duplicates-with-drift (capability changes must be explicit versioned
events, never silent overwrites).

### 2.4 Credential redaction (`redaction.py`)

`BrokerCredential` — per-account opaque holder: `__slots__`, redacted
`__repr__`/`__str__` by construction, equality over ACCOUNT ONLY.
`scrub_secrets` / `redact_mapping` / `find_secret_leak` /
`assert_no_secret_material` — the test-facing scanner proves journal
files, error messages and serialized acks contain no secret material.
(Mock-phase credentials are arbitrary strings; the machinery exists so
future real adapters inherit an already-safe boundary.)

### 2.5 The adapter interface (`interface.py`)

`BrokerAdapter` (ABC) — exactly this surface, enforced by
`BROKER_ADAPTER_SURFACE` (contract tests fail closed on accidental
growth):

- lifecycle: `connect(credential)` / `disconnect()` / `health()`
- account + instruments: `account_info()` / `instrument_spec(symbol)` /
  `list_symbols()`
- orders: `submit_order(request)` (idempotent) / `cancel_order` /
  `order_status` / `order_fills`
- state: `positions()` / `balances()`
- reconciliation: `reconcile(expected)` — reports, never repairs

### 2.6 The guarded session (`session.py`)

`BrokerSession` binds ONE (adapter, account). Submission pipeline
(fixed order, all fail-closed):

1. account isolation (request.account_id == session account)
2. health gate (CONNECTED only)
3. reconciliation gate (degraded sessions refuse EVERYTHING)
4. kill-switch gate (injectable `kill_switch_fn`; ABSENT ⇒ refuse)
5. risk gate (injectable `risk_decision_fn`; ABSENT ⇒ refuse —
   "no gate, no trading")
6. journal-backed idempotency (same key + same digest ⇒ exact ack
   replay, no venue call; same key + different digest ⇒
   IDEMPOTENCY_KEY_REUSE refusal)
7. capability + precision pre-checks (unsupported shapes NEVER reach
   the venue)
8. bounded retry (CONNECTIVITY/TIMEOUT/RATE_LIMIT only; deterministic
   backoff via injectable sleeper; UNKNOWN_STATE never retried)
9. journaling (ORDER_ACK / ORDER_REFUSED / VENUE_SYNC; atomic
   tmp+rename writes; per-record digests verified on load — a tampered
   or foreign journal refuses to load)

UNKNOWN outcomes degrade the session; `reconcile()` resolves them from
venue truth (venue is the execution authority) and clears the
degradation ONLY on a clean report — any mismatch (including phantom
orders) DEGRADES and stops new orders (§32 discipline), with
`sync_order_state()` as the explicit, ledgered accept-venue-truth
action. Degraded state and duplicate protection SURVIVE RESTART
(journal reload).

---

## 3. Capability matrix (the four planned integrations)

The matrix below is EXECUTABLE: every row is pinned by tests in
`tests/test_broker_adapter_contract.py` and encoded in the
corresponding `BrokerCapabilities` descriptor.

| Capability | paper-mock | mt5-mock (Exness/XM-class) | binance-mock (spot) | bybit-mock (v5) |
|---|---|---|---|---|
| Order kinds | MARKET, LIMIT, STOP, STOP_LIMIT | MARKET, LIMIT, STOP, STOP_LIMIT | MARKET, LIMIT | MARKET, LIMIT |
| Time-in-force | GTC, IOC, FOK, DAY | GTC, IOC | GTC, IOC, FOK | GTC, IOC, FOK |
| SL/TP semantics | ATTACHED | ATTACHED | SEPARATE_ORDERS | ATTACHED |
| Position mode | NETTING | HEDGING (per-ticket) | BALANCES_ONLY | NETTING (one-way) |
| Idempotency key | internal journal | COMMENT_FIELD (order comment) | NATIVE (`newClientOrderId`) | NATIVE (`orderLinkId`) |
| Reduce-only | yes | no (tickets close instead) | no (futures-only concept) | yes |
| Precision model | tick + lot step | volume_min/step/max | tickSize/stepSize/MIN_NOTIONAL | lotSizeFilter + minOrderAmt |
| Min notional | none | none (volume_min governs) | 10 quote | 5 quote |
| Rate-limit shape | uncapped | 5 orders / 60s (retcode 10027) | 10 requests / 60s weight (HTTP 429) | 5 orders / 60s (retCode 10004) |
| Representative native codes | descriptive | 10014 / 10019 / 10027 / 10036 | -1013 / -2010 / -2013 / -1121 / 429 | 110007 / 10014 / 10004 / 10010 |
| Reconciliation style | order+fill poll | positions + history poll | balance snapshot + fills | position statement + fills |
| Account modes | DEMO | DEMO (REAL refused) | DEMO (REAL refused) | DEMO (REAL refused) |
| Market data | none (execution-only) | existing read-only `platform/mt5.py` | existing `providers/binance_public.py` | none (future phase) |
| Execution mode | MOCK_DETERMINISTIC | MOCK_DETERMINISTIC | MOCK_DETERMINISTIC | MOCK_DETERMINISTIC |

**Exness/XM verification boundary (explicit):** the MT5 mock encodes
only COMMON MT5 terminal semantics. Actual Exness/XM account support —
symbol suffixes (e.g. `EURUSDm`-style), server names, hedging vs
netting account setup, available leverage — is an OPERATOR verification
step per account BEFORE any real adapter activation. UNVERIFIED
brokers are not connectable by design. The existing read-only
`platform/mt5.py` adapter (order surface ALWAYS refused) remains the
only real MT5 surface in this repository until Phase M5 is explicitly
authorized.

---

## 4. Implementation plan (ordered by risk)

| Phase | Scope | Risk | Status |
|---|---|---|---|
| **M1** | Broker-neutral core (models/errors/capabilities/redaction/interface) + guarded session + four deterministic mocks + failure-injection tests. Purely ADDITIVE; zero frozen files touched. | MINIMAL (no runtime path changes; no network) | **DELIVERED this cycle** |
| **M2** | Wire the paper runtime's execution boundary onto `BrokerSession` behind a `PaperBrokerAdapter` that hosts the existing `PaperExecutionAdapter` fill model; bridge `RiskGate`/`KillSwitchManager` into the session's injectable gates; prove EXECUTION_STATE_SCHEMA compatibility. | MEDIUM (touches the live order path; must preserve all frozen contracts and the 1,769-test behaviour) | **DELIVERED (Batch 3 side-band §6a + Batch 5 AUTHORITATIVE §6b, 2026-10-12)** — the runtime's order path itself now flows through the guarded session when a venue is attached |
| **M3** | Real Binance spot TESTNET adapter behind the same interface (REST + filters + weights; env-injected credentials, never in repo; testnet funds only). | MEDIUM-HIGH (first real network execution surface) | NOT STARTED — requires operator authorization + SRC-APPROVAL-style review |
| **M4** | Real Bybit v5 demo/testnet adapter (orderLinkId, one-way mode, lotSizeFilter). | MEDIUM-HIGH | NOT STARTED |
| **M5** | Real MT5-compatible adapter (Exness/XM DEMO accounts, Windows terminal session injection per `platform/mt5.py` protocol; REAL account mode structurally refused until an explicit operator LIVE-authorization protocol exists). | HIGH (real broker terminals) | NOT STARTED |
| **M6** | Cross-venue risk aggregation + unified reconciliation daemon + multi-account portfolio guards (central controls dominate ALL venues simultaneously). | HIGH | NOT STARTED |

Every phase lands on a dedicated feature branch with the same
discipline as this one: acceptance tests first, full-suite green,
frozen-blob verification, secret scan 0, honest verdict.

---

## 6a. Phase M2 delivery record (Batch 3 — 2026-10-12)

**Branch:** `feat/runtime-risk-broker-neutral-tenancy` (from `82f46d9`,
continuing the Batch-2 commit `ff5f7d3`). **Module:**
`src/data_engine/runtime/broker_execution.py` (the ONLY
runtime<->brokers seam; exported from `data_engine.runtime`).

**What was built (the smallest maintainable integration layer):**

- `RuntimeRiskGateBridge` — the session's injectable risk gate,
  backed by the runtime's REAL `RiskGate` instance (all 22 mandatory
  checks incl. RUN-DD-1 account drawdown). One `OrderRequest` is
  translated into the runtime's canonical `TradePlan` +
  live-state `RiskContext` (TRUE equity, live position, drawdown,
  volatility, daily return at the latest admitted bar); the
  assessment is ledgered into the runtime's ledger family.
  Refused translations (fail closed): STOP/STOP_LIMIT kinds
  (`paper_oms_order_kind`), foreign symbols
  (`bridge_symbol_context` — no authoritative market context),
  zero admitted bars (`no_market_context`).
- `RuntimeKillSwitchGate` — the session's injectable kill-switch
  gate, backed by the runtime's REAL `KillSwitchManager` (any
  governing trip refuses venue submissions; the runtime stays
  authoritative).
- `RuntimePaperExecutionAdapter` — a `BrokerAdapter` hosting the
  runtime's OWN `PaperExecutionAdapter` fill model over the
  runtime's admitted bar history (identical latency, participation
  partial fills, LIMIT protection, cost decomposition — aggregated
  into the venue-neutral `fee` field exactly once). MARKET/LIMIT +
  GTC + ATTACHED SL/TP only (exactly what the frozen paper OMS
  supports); integrator-supplied instrument specs (never guessed);
  execution advances on venue polls; venue-side netting book +
  §32 reconciliation (ORDER_MISSING / PHANTOM / STATUS_DIVERGENCE /
  FILL_QUANTITY_DIVERGENCE + UNKNOWN resolutions).
- `attach_runtime_paper_session(...)` — the factory wiring the
  bridges into a guarded `BrokerSession` (journal idempotency,
  bounded deterministic retry, UNKNOWN degradation, capability and
  precision pre-checks, account isolation).

**Deliberate design decision — SIDE-BAND integration:** the
runtime's authoritative order path (`_execute_plan` -> OMS ->
runtime fills) is UNTOUCHED. Venue orders live in the session
journal + the adapter's venue book, never in the runtime
OMS/position book. The M2 table row's original wording ("wire the
runtime's execution boundary ONTO BrokerSession") is satisfied by
governance + hosting, not by re-routing the live order path —
re-routing would have risked the frozen contracts for zero safety
gain. The runtime-side properties added: `TradingRuntime.risk_gate`
(read-only seam) only.

**Tests:** `tests/test_runtime_broker_integration.py` — 22 tests:
market lifecycle (OPEN -> FILLED with cost decomposition), multi-bar
partial fills, resting LIMIT + BUG-001 price protection, cancel
freeze, central-gate governance (runtime kill-switch trip refuses
venue orders; no-SL refused by the REAL gate; RUN-DD-1 drawdown
refused through the bridge; no-market-context refusal; foreign
symbol refusal), idempotency (exact ack replay, key-reuse refusal,
journal survives session restart), timeout retry with deterministic
backoff evidence, UNKNOWN degrade -> reconcile -> resume,
unsupported TIF/STOP-kind refusals, account isolation, unknown
symbol, STATUS_DIVERGENCE -> sync_order_state -> clean re-reconcile,
phantom-order degradation, side-band preservation (runtime OMS
untouched), MOCK_DETERMINISTIC-only enforcement.

**Verification:** suite 2,039 + 1 skipped -> **2,061 + 1 skipped**
(+22, zero regressions, zero existing tests modified).

**Remaining adapter work (explicit, NOT claimed):** M3 (Binance
spot TESTNET), M4 (Bybit v5 demo), M5 (MT5-compatible Exness/XM
DEMO), M6 (cross-venue aggregation) are all NOT STARTED — no real
broker adapter exists or is claimed; MT5/Exness/Binance/Bitget/XM
remain UNSUPPORTED for real execution. Executing runtime orders
through a real venue (replacing the side-band venue) remains
future, separately-reviewed work.

---

## 6b. Phase M2 completion record (Batch 5 — 2026-10-12)

**Branch:** `feat/runtime-risk-broker-neutral-tenancy` (continuing
from the Batch-4 commit `9c02682`). **Module:**
`src/data_engine/runtime/broker_execution.py` (extended) +
surgical `runtime.py` seams + one additive `BrokerSession` method.

**What was built (the AUTHORITATIVE integration):**

- `attach_authoritative_paper_venue(...)` — the factory binding a
  guarded `BrokerSession` ONTO the runtime's AUTHORITATIVE order
  path. With a venue attached, `_execute_plan` submits every order
  (entries AND protective exits) through the full session pipeline
  between OMS risk-approval and OMS submission, and
  `_process_pending_orders` fills orders EXCLUSIVELY from venue
  polls. There is NO hidden direct-execution fallback: a runtime
  with live pre-venue internal orders REFUSES the attachment.
- `RuntimeOrderPathRiskGate` — the session's risk gate as an
  identity-binding VERIFICATION (not a re-decision): the request
  must map 1:1 onto an OMS order in RISK_APPROVED state with exactly
  matching fingerprint fields — the structural RT-F1 evidence of the
  runtime's ONE authoritative 22-check assessment. The venue
  `client_order_id` IS the OMS order id.
- `RuntimeAuthoritativeVenue` — the seam owning: the fail-closed
  submission-block reasons (degraded session / unhealthy adapter /
  non-RUNNING runtime); the narrow risk-reduction carve-out at the
  venue kill-switch gate (exclusively for seam-driven reduce-only
  orders that verifiably reduce the live position — the mirror of
  the runtime gate's documented closing-order carve-out, so
  protective exits traverse the SAME boundary under an active
  switch); exactly-once `poll_order` deltas; venue-cancel routing
  for kill-switch fill-time enforcement and TTL expiry;
  `resolve_ambiguity` (ledgered reconciliation-only recovery —
  cross-checked phantom adoption, never an inferred failure) and
  `recover` (venue-book rebuild from persisted OMS + journal truth
  with deterministic-regeneration verification; journaled UNKNOWN
  orders are never fabricated into the venue book).
- `RuntimePaperExecutionAdapter(authoritative=True)` — hosted fills
  carry the OMS order identity and the OMS TTL fill window, so
  venue-mode fills are BIT-IDENTICAL to the internal path (same
  fill ids, quantities, prices, cost decomposition); a submission
  without a matching RISK_APPROVED OMS order is refused by the
  adapter itself (defence in depth). `register_recovered_order`
  rebuilds one venue order from persisted state, verifying the
  deterministic regeneration of every fill.
- `BrokerSession.adopt_venue_order(request)` — the ONE additive
  brokers-package change: an explicit, LEDGERED lost-ack re-adoption
  action (journal ORDER_ACK + venue-truth sync) used exclusively by
  the cross-checked phantom-adoption recovery. The session still
  never fabricates adoption on its own.
- Runtime seams: `TradingRuntime.venue` (read-only),
  `_bind_authoritative_venue`, `_apply_execution_fills` (the ONE
  fill-application path, shared verbatim by internal and venue
  modes — bit-identical accounting), `_flag_execution_uncertain`,
  `_resolve_venue_order`, `_resume_after_venue_reconciliation`;
  venue counters registered in the closed metrics vocabulary.

**Ambiguity discipline (the §28 mapping):** a definitive venue
refusal REJECTS the OMS order (the venue never saw it); an ambiguous
submission (UNKNOWN ack or exhausted TIMEOUT retries) submits + marks
UNKNOWN + RECONCILING and sets EXECUTION_UNCERTAIN — bars, polls and
new submissions all stop until reconciliation adopts venue truth
through the ledgered actions. A restart inside the ambiguity stays
fail-closed (the fresh in-memory venue honestly does not hold the
order; nothing infers an outcome).

**Tests:** `tests/test_runtime_authoritative_venue.py` — 26 tests,
RED-first (the interface did not exist): approved orders reach the
session under their OMS identity and fill; venue-mode ==
internal-mode bit-identical (twin runs); organic full-chain equality
with the internal control; risk refusal never reaches the venue;
kill-switch blocks new venue orders; in-flight cancellation at BOTH
books; protective exits traverse the boundary under the carve-out;
precision refusals distinguish price vs quantity (ledgered with the
dimension named); missing-spec attach refused; degraded/unhealthy
venue blocks all submissions (reconnect recovers); UNKNOWN blocks
until reconciled then resumes with exactly-once fills; lost-ack
adoption (ledgered) and unexplainable-phantom blocked; restart
idempotency (split run == whole run, no duplicate submissions, venue
book rebuilt identically); key reuse refused; restart-inside-UNKNOWN
stays blocked; recovered HALT never silently RUNNING; live
pre-venue orders refuse attach; partial fills accounted exactly once
(redundant poll is a no-op); zero credential leakage (executable
scan over ledgers/state/journal/OMS); RUN-DD-1 through the venue;
side-band factory preserved; MOCK_DETERMINISTIC pin.

**Verification:** suite 2,107 + 1 skipped -> **2,133 + 1 skipped**
(+26, zero regressions, ZERO existing tests modified) x3 consecutive
runs (73.2s / 71.2s / 71.7s); frozen Phase 3 blobs 11/11
byte-identical to `13fdc7e`; secret scan 0 hits across ALL history.

**Honest limitations (explicit):** paper-mock venue only
(MOCK_DETERMINISTIC enforced; REAL adapters refused — live trading
NOT AUTHORIZED); the in-memory venue book is a deterministic
rebuild from persisted state, not durable venue truth (Phase M3+
tests against real venues); venue-journal growth is O(polls)
(atomic full-file rewrites per record — acceptable for paper, a real
concern only for real venues with their own persistence);
`BrokerSession.adopt_venue_order` is authoritative-path machinery
(the side-band sessions never call it). Executing runtime orders
through a REAL venue remains M3-M6 work, NOT STARTED.

## 6c. Batch 7 delivery record — Bitget mock + instrument
       discovery/catalog/registry sync (2026-10-13)

**Branch:** `feat/runtime-risk-broker-neutral-tenancy` (continuing
from the Batch-6 commit `39e7939`). **Modules:**
`src/data_engine/brokers/adapters/bitget_mock.py` (new fifth mock
venue), `src/data_engine/brokers/instruments.py` (new discovery /
catalog / registry-sync layer), capability-registry extension.

**What was built:**

1. **Bitget spot v2 mock** (`BitgetSpotMockAdapter` +
   `BITGET_MOCK_CAPABILITIES`, registered in `default_registry`) —
   the Phase-1 discovery audit's broker matrix had recorded Bitget
   as "NOTHING — no adapter, no mock, no market-data provider".
   Semantics encoded: MARKET/LIMIT only; SL/TP as SEPARATE trigger
   (plan) orders (`SEPARATE_ORDERS`); `clientOrderId` native
   idempotency; balances-only account (spot has no position
   object); trade filters (tick/lot/minimum notional with
   `minTradeUSDT`-class minimum); request + order rate limits.
   Representative v2 native codes preserved for audit (40001 param
   error / 43007 filter violation / 43025 order-not-exist / 42911
   frequency limit — re-verified against the live docs when the
   real-adapter phase is authorized). The adapter joins the SHARED
   parametrized contract suite, so the whole normalized surface is
   proven against it like every other venue.

2. **Instrument discovery + catalog** (`discover_instruments` →
   immutable `InstrumentCatalog` of `CatalogEntry` records) —
   fail-closed: discovery from a DISCONNECTED adapter refuses (a
   fabricated catalog is worse than none); foreign-broker specs
   refuse; duplicate venue symbols refuse; the adapter's LIVE
   capability descriptor is cross-checked against the
   `CapabilityRegistry` when supplied (DRIFT refuses — capability
   changes are explicit versioned events, never silent); lookups
   fail closed on unknown symbols; every entry snapshots the
   venue's descriptor AT DISCOVERY TIME (provenance).

3. **Platform-registry sync** (`sync_catalog_to_platform_registry`)
   — registers every catalog entry into the CENTRAL platform
   `InstrumentRegistry` as a canonical identity with
   `broker:<id>` provider-symbol mappings, honoring the registry's
   own contracts verbatim: registration ≠ eligibility (a synced
   instrument lands DISCOVERED — the sync NEVER touches data state,
   verification, monitoring or eligibility); the same canonical
   instrument from a SECOND venue is the registry's flagged-duplicate
   path with the provider mapping MERGED (one canonical identity,
   many venue symbols — never two records; the canonical identity
   deliberately carries no exchange/venue so venues never fork
   identity); broker mappings start UNVERIFIED.

**Verification:** suite 2,167 + 1 skipped → **2,215 + 1 skipped**
(+48: 21 new discovery/sync/Bitget tests + 27 shared-contract tests
newly parametrized over bitget-mock; one existing inventory pin
updated four→five mocks — a documented strengthening, zero
assertions weakened) x3 consecutive runs (80.3s / 81.0s / 80.4s);
frozen Phase 3 blobs 11/11 byte-identical to `13fdc7e`; manifest
pins 13/13; real-credential scan 0 hits on changed files.

**Honest limitations (explicit):** the Bitget adapter is a
DETERMINISTIC MOCK (MOCK_DETERMINISTIC; REAL execution modes
structurally refused at descriptor registration — live trading NOT
AUTHORIZED); its native error codes are representative and will be
re-verified against the live Bitget v2 docs when a real-adapter
phase is operator-authorized; discovery/sync grant NO trading
permission of any kind (registration ≠ eligibility, broker
mappings unverified); no market-data provider for Bitget exists
(the Phase-1 audit's gap stands in that dimension).

## 5. Tests (the executable evidence)

| File | Coverage |
|---|---|
| `tests/test_broker_neutral_core.py` | model validators (fail-closed shapes), error taxonomy (retryability derivation, redacted messages), capability registry discipline (drift refusal, REAL refusal, coherence), interface surface pinning, credential redaction |
| `tests/test_broker_adapter_contract.py` | the SAME contract suite PARAMETRIZED over all four adapters: lifecycle/isolation, submission/idempotency/cancel/partial fills, determinism (identical runs → identical ids), failure injection (disconnect, rate-limit, ack-timeout, definitive rejection, extra fill), venue reconciliation, venue-specific semantics per the capability matrix |
| `tests/test_broker_session_guards.py` | the fail-closed pipeline: gate ordering (kill-switch BEFORE risk), absent-gate refusals, parametrized central-gate independence across all four brokers, journal-backed idempotency (incl. across restart), bounded deterministic retry, UNKNOWN degradation + reconciliation recovery + degraded-state persistence across restart, divergence handling, journal tamper-evidence, reconnect behaviour, secret-free persistence |

Failure-injection surface (deterministic, explicit):
`inject_disconnect`, `inject_rate_limit(n)`, `inject_ack_timeout`
(accepted-but-unacknowledged), `inject_rejection`, `inject_extra_fill`,
`configure_market_fill_fraction`, `fill_remaining`, `trigger_fill`,
`clear_injections`.

**Suite evidence:** baseline 1,769 passed + 1 skipped (HEAD `1c286d2`,
55.30s) → **2,005 passed + 1 skipped** after this change (54.76s).
+236 tests, zero regressions, zero existing tests modified.

---

## 6. Reproducibility

```bash
# baseline (before this change), at 1c286d2:
uv run pytest -q                     # 1769 passed, 1 skipped

# after this change, on feat/broker-neutral-execution-architecture:
uv run pytest -q                     # 2005 passed, 1 skipped
uv run pytest tests/test_broker_neutral_core.py \
              tests/test_broker_adapter_contract.py \
              tests/test_broker_session_guards.py -q   # 236 passed
```

Frozen Phase 3 blobs: 11/11 byte-identical to `13fdc7e` (verified
locally and by platform CI on the pushed branch). Secret scan across
ALL history: 0 hits.

---

## 7. Honest limitations

1. The four adapters are MOCKS. They model venue SEMANTICS (filters,
   position modes, native error codes, rate-limit shapes) but perform
   no real network I/O and hold no real accounts.
2. The operational paper pipeline (frozen 22-module runtime) does NOT
   yet route through the broker-neutral interface — that is Phase M2
   and changes nothing until independently reviewed. Until then the
   new layer is machinery + proof, not the trading path.
3. Venue persistence is in-memory: mock venues lose their books across
   processes (restart tests exercise journal-side recovery semantics —
   the resolution "venue never received it ⇒ REJECTED" is honest for a
   fresh in-memory venue; real venues are durable and Phase M3+ will
   test against real venue truth).
4. Rate limits are representative counts, not the real venues' current
   numbers; real adapters must load their limits from venue metadata.
5. No async/threading: the interface is synchronous by design
   (determinism first); real adapters bridge with their SDK models in
   their own phases.
6. Locked funds (spot balance locking) are not modelled (free/locked
   with locked=0); margin/leverage checks are absent — the central
   RiskGate owns pre-trade risk; venue-side margin behaviour is a
   Phase M3+ concern.

---

## 8. Verdict

The broker-neutral execution architecture is DESIGNED, IMPLEMENTED at
the interface/mock level, and regression-proven (2,005 + 1 skipped).
Real integrations are planned by risk order and NONE is started.
**PAPER_READY = FALSE (unchanged). LIVE TRADING NOT AUTHORIZED.** The
readiness verdict can only change through Phase M2 integration +
independent testing of the full runtime chain, and the standing human
blockers (SRC-APPROVAL, operational feed provisioning, keyed-MAC key,
PAT rotation confirmation, REAL_DATA_READY chain) remain exactly as
recorded in `PAPER_TRADING_READINESS_FINAL_REPORT.md` §15.
