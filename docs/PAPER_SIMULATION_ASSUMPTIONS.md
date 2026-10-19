# PAPER SIMULATION ASSUMPTIONS (CONSOLIDATED)

```text
Document ID:     TRA-PSA-001
Version:         1.0.0
Date:            2026-10-19 (Asia/Karachi)
Document Type:   Consolidated simulation-assumption register (U-22,
                 Stage D, patch plan P6)
Authority:       B — CURRENT SUPPORTING. The AUTHORITATIVE
                 implementations are src/data_engine/paper/simulator.py
                 (fill model), src/data_engine/paper/gateway.py
                 (submission gateway), src/data_engine/brokers/session.py
                 (venue session outcomes) and
                 src/data_engine/runtime/broker_execution.py (the
                 authoritative paper venue). This document CONSOLIDATES
                 what those modules assume; it never overrides them.
Pinning tests:   tests/test_simulation_assumptions_doc.py
                 (structural + behavioral agreement with the code)
Status:          CURRENT — describes the PAPER path only
```

**PAPER_READY = FALSE. LIVE TRADING NOT AUTHORIZED.** Every assumption
below belongs to the paper simulation path; none of it describes or
enables a real market.

---

## 1. Fills

| Aspect | Assumption | Implementation |
|---|---|---|
| MARKET fill price | Next-bar open plus the FULL adverse cost stack (half-spread + impact) — never the triggering bar's price (no look-ahead) | `ExecutionSimulator._fill_market` |
| MARKET fill timing | Fills at bar index `submission_bar + fill_lag_bars` (default lag 1) | `ExecutionRealism.fill_lag_bars` |
| LIMIT fill crossing | Fills only on a bar (at/after the lag) whose price crosses the limit (buy: `low <= limit`; sell: `high >= limit`) | `ExecutionSimulator._fill_limit` |
| LIMIT fill price | Never through the limit: buy fills at `min(limit, open + half_spread + impact)`, sell at `max(limit, open − half_spread − impact)` (BUG-001) | `ExecutionSimulator._fill_limit` |
| Non-crossing LIMIT | No fill (`None`) — the order simply does not fill; it is not an error | `simulate()` |
| No same-bar fills | `fill_lag_bars >= 1` is enforced by the validator — latency 0 is not constructible | `ExecutionRealism._validate_lag` |

## 2. Rejections (fail-loud, never silent)

| Condition | Behavior | Implementation |
|---|---|---|
| Order quantity > `participation_cap × bar_volume` | `SimulationError` — the market could not absorb the fill; realism failure, not a feature | `simulate()` |
| Fill bar has no volume (`volume <= 0`) | `SimulationError` | `simulate()` |
| Order submitted before the first bar | `SimulationError` (no market context) | `simulate()` |
| Duplicate / non-increasing bar timestamps | `SimulationError` (BUG-007 — the scan refuses to mis-locate) | `_validate_bar_order` |
| Empty bar series | `SimulationError` | `simulate()` |

## 3. Partial fills

**There are none.** The simulator is all-or-nothing: every `Fill`
carries the order's full quantity, and an order the market could not
fully absorb raises `SimulationError` instead of partially filling.
The `PARTIAL_FILL_READY` readiness gate therefore concerns the OMS
outcome-transition machinery (durable handling of partial-fill EVENTS
at the order-lifecycle layer), not a simulator partial-fill mode.
This is a deliberate conservative choice: a partial paper fill with
invented remainders would fabricate realism the bar data cannot
support.

## 4. Slippage (market impact)

Deterministic per-unit impact: `impact_rate × (quantity / bar_volume)
× reference_price`, applied ADVERSELY (buy pays it, sell receives
less). For LIMIT orders impact is charged only up to the gap between
limit and base price (never through the limit). The model is
bar-volume-proportional — it is a deterministic realism knob, not a
stochastic process; the same order against the same bars always
produces the same impact.

## 5. Fees

Flat `commission_per_unit × quantity` per fill. No minimum-commission
tier, no exchange-tier differentiation, no overnight financing — the
paper path models none of these, and this absence is an explicit
assumption, not an oversight.

## 6. Latency

Bar-denominated: `fill_lag_bars` (default **1**) bars between
submission and fill. Sub-bar latency (milliseconds), queue position
and rejection-latency are NOT modeled. The submission ledger's
wall-clock spacing governor (min 1 s between submissions, max 5 per
60 s, max 10 open orders — owner-ratified) operates at the SUBMISSION
boundary and is independent of the simulator's bar-latency.

## 7. Cost decomposition identity

Every fill records its exact decomposition and satisfies
`price × qty == base × qty ± (spread_cost + slippage_cost)` with
`base = min(limit, open)` (buy) / `max(limit, open)` (sell) in exact
Decimal arithmetic. There is no unexplained residual.

## 8. Determinism

Given identical bars, realism config, order and submission timestamp,
the fill is bit-identical (Decimal arithmetic throughout; replay
pinned by the deterministic-replay suite). No RNG exists anywhere in
the paper fill path.

## 9. Venue-level submission outcomes (the session seam)

At the venue/session seam (paper venue hosted by the runtime's own
adapter), a submission resolves to exactly one of:

- **ACCEPTED** — journalled `ORDER_ACK`; the OMS order advances and
  the fill applies exactly once;
- **REFUSED** — journalled `ORDER_REFUSED` with a normalized reason
  (risk, capability, precision, kill-switch, rate limit); nothing
  executes;
- **UNKNOWN** — no ack within the retry window (timeout / crash
  window): ambiguity BLOCKS all new submissions until reconciliation
  resolves it from venue truth; a lost ack NEVER infers failure
  (fail-closed), and the reservation is NEVER released on timeout
  (only confirmed absence releases — Stage C C3).

## 10. What this document does not claim

- No real-market microstructure: no queue dynamics, no depth book, no
  stochastic volatility, no gapping model beyond bar boundaries.
- No real broker behavior: every venue shipped in this repository is
  `MOCK_DETERMINISTIC` (proof-pinned by
  `tests/test_paper_mode_selection_proof.py`).
- No readiness upgrade: documenting assumptions does not close any
  readiness gate. `PAPER_READY` stays FALSE.
