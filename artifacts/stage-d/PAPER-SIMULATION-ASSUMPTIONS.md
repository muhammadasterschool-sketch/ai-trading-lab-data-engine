# PAPER-SIMULATION-ASSUMPTIONS (Stage D / D2 — Part 7 mandate)

Status: DOCUMENTED (deterministic simulation model, pinned by tests).
Scope: every deterministic assumption governing fills, rejections,
partial fills, slippage, fees, and latency in PAPER mode.
PAPER_READY stays FALSE. No paper execution has been started in this
run. LIVE TRADING REMAINS NOT AUTHORIZED (permanently out of scope
under the current prompt).

Two simulation surfaces exist and BOTH are documented here:

| Surface | Role | Authority |
| --- | --- | --- |
| `src/data_engine/runtime/execution.py` | The OPERATIONAL paper execution gateway wired by the composition root | Authoritative paper engine (frozen 22-module runtime) |
| `src/data_engine/brokers/adapters/_mock_core.py` + `adapters/paper.py` | Broker-neutral mock venue family (paper + per-broker mocks) | Capability-proof surface (Phase M1/M2); also simulation-only |

---

## 1. Runtime paper execution gateway (`runtime/execution.py`)

### 1.1 Structural isolation (mandate §59)

The runtime execution adapter is structurally paper-only
(`runtime/execution.py:1-30`, `PAPER_MODE_STRUCTURAL_ISOLATION`):

- no broker credentials (no credential field anywhere in the module);
- no production endpoints (no network import, no URL field);
- no real capital (notional is play-money by construction);
- no account mutation (fills exist only inside this simulator).

### 1.2 Fill model (deterministic; docstring `runtime/execution.py:9-29`)

- **Latency**: filling starts at `submit bar + fill_lag_bars`
  (`execution.py:205`, `ExecutionRealism.fill_lag_bars` default 1 —
  `paper/simulator.py:69`).
- **Per-bar liquidity cap**: at most
  `participation_cap * bar_volume` units fill per bar; the remainder
  spills to subsequent bars — never one unrealistic perfect fill
  (mandate §38). `participation_cap` is validated to `(0, 1]`
  (`paper/simulator.py:78-83`).
- **MARKET price**: `open ± half_spread ± impact` (adverse stack),
  with impact computed on THIS partial fill's quantity:
  `impact = impact_rate * (qty / bar_volume)`
  (`execution.py:228-237`).
- **LIMIT price (BUG-001 protection)**: BUY never above the limit,
  SELL never below it; fills occur only on bars that cross the limit
  (`execution.py:243-245`).
- **Cost decomposition**: every fill records commission, slippage /
  impact, and spread cost separately — nothing hidden (§36;
  `execution.py:70-72`, `RuntimeFill` fields `commission`,
  `slippage_cost`, `spread_cost`; non-negative Decimal validation at
  `execution.py:97`).
- **TTL expiry**: an order whose quantity exceeds every bar's
  capacity leaves an unfilled remainder → EXPIRED by TTL and
  LEDGERED — never a fake perfect fill and never a silent drop
  (`execution.py:26-28`, TTL window bounded by `max_bars` at
  `execution.py:170-171`).
- **Timezone discipline**: bars must carry timezone-aware timestamps;
  fill times are normalized to UTC (`execution.py:40-45`).

### 1.3 Realism parameters (`paper/simulator.py:60-87`)

`ExecutionRealism` is an immutable (`frozen=True`, `extra="forbid"`)
model — every cost is explicit, none hidden:

| Parameter | Meaning | Validation |
| --- | --- | --- |
| `half_spread` | half-spread cost component | non-negative finite Decimal |
| `commission_per_unit` | per-unit commission | non-negative finite Decimal |
| `impact_rate` | slippage fraction per (qty/volume) | non-negative finite Decimal |
| `participation_cap` | max fraction of bar volume fillable per bar | strictly in (0, 1] |
| `fill_lag_bars` | bars until a market order starts filling | non-negative int, default 1 |

Spread/slippage split at fill time: `spread_cost =
min(half_spread, adverse)`; `slippage_cost = adverse − spread_cost`
(`execution.py:250-251`) — the adverse stack is decomposed, never
lumped.

### 1.4 Determinism

Fills are a pure function of (order, bar series, realism parameters,
clock). The clock is injectable and REQUIRED; replay of the same
inputs yields the same fills, the same cost decomposition, and the
same ledger state. Pinned by the frozen runtime suite
(`tests/test_runtime_oms.py`, `tests/test_runtime_pnl_correctness.py`,
`tests/test_runtime_e2e.py`).

---

## 2. Broker-neutral mock venue family (`brokers/adapters/`)

### 2.1 Construction-time refusal (fail closed)

- `DeterministicMockVenue` REFUSES to construct against any
  capability descriptor whose `execution_mode` is not
  `MOCK_DETERMINISTIC` (`_mock_core.py:139-143`).
- REAL account modes are refused by construction
  (`_mock_core.py:144-152`).
- `BrokerCapabilities` pydantic validation REFUSES to register
  REAL execution-mode + REAL account-mode descriptors at all
  (`brokers/capabilities.py:163-171`).
- `BrokerSession` REFUSES to construct against a REAL execution-mode
  adapter (`brokers/session.py:325-331`).

Selection proof for all four layers:
`tests/test_paper_mode_selection_proof.py` (10 tests).

### 2.2 Paper venue defaults (`brokers/adapters/paper.py:51-72`)

- Play-money initial balances: 100,000 USDT / 100,000 USD / 1 BTC /
  100,000 EUR (`paper.py:62-68`).
- `fee_rate = 0` on the paper venue (`paper.py:70`) — the paper
  broker-neutral surface charges no commission by default; costs are
  modeled authoritatively by the runtime gateway's `ExecutionRealism`
  instead. Any non-zero fee study must pass an explicit `fee_rate`.
- Instruments: BTCUSDT and EURUSD reference specs with tick/lot/min
  constraints (`paper.py:20-49`).

### 2.3 Fill / rejection semantics (`_mock_core.py`)

- **Definitive rejections are REJECTED acks** with venue-native
  codes (`_mock_core.py:19`, `421-429`): precision violations,
  insufficient funds, unknown symbol, unknown order.
- **Partial fills**: multi-step fill accounting with resting
  remainder (`_mock_core.py:547-555` `Execute one (possibly partial)
  fill`); `fill_remaining` completes a resting/partial order
  (`_mock_core.py:940-948`).
- **Fees**: `fee = fee_rate * notional`, quantized to 1e-8
  (`_mock_core.py:555`, `631`).
- **Rate limits**: request-level and open-order limits are venue
  policy, refused with typed `RateLimitError` when exceeded
  (capabilities `RateLimitPolicy`, `_mock_core.py` guards; runtime
  B1/B2 enforce the owner-ratified spacing before any venue call).
- **Idempotency**: the same `client_order_id` returns the SAME
  acknowledgement and never executes twice
  (`brokers/interface.py:59-61`); pinned across restarts by
  `tests/test_broker_session_guards.py:354,373,517`.
- **UNKNOWN outcomes**: transport failures raise typed errors;
  `UnknownOrderStateError` forces journal-UNKNOWN + reconcile before
  any retry (`brokers/interface.py:62-64`; runtime §28 handling pinned
  in `tests/test_oms_durable_outcomes.py`).

### 2.4 Determinism

Every mock venue requires an INJECTABLE clock (`session.py`:
"a REQUIRED injectable clock (journal timestamps — determinism)").
No wall-clock reads inside venue logic; all timestamps flow from the
injected clock.

---

## 3. What is deliberately NOT simulated

- No queue-position modeling, no order-book depth beyond per-bar
  volume participation, no venue-side latency jitter (latency is
  exactly `fill_lag_bars`), no reject-on-flash-move, no exchange
  outage simulation in the runtime gateway.
- These omissions are ACCEPTED for paper-readiness evidence but are
  listed as residual simulation-fidelity risks for the soak decision
  (see PAPER-SOAK-PROCEDURE.md §Monitoring).

## 4. Evidence index

- `tests/test_paper_mode_selection_proof.py` — D1 selection proof
  (4 enforcement layers + vocabulary audit).
- `tests/test_oms_durable_outcomes.py` — D3 fault battery (crash
  matrix, UNKNOWN, duplicate intent).
- `tests/test_broker_session_guards.py` — duplicate acks, idempotency
  across restart, bounded retry, reconnect refusal.
- `tests/test_submission_ledger.py` — durable reservations, crash
  conservatism, restart budget reconstruction.
- `tests/test_runtime_recovery_integration.py` — restart with
  outstanding state; no duplicate identities post-restart.
- `tests/test_composition_root.py` — C3 reconciliation driver
  scenarios (duplicate signal, ambiguous preservation, confirmed
  absence, timeout ≠ release).
