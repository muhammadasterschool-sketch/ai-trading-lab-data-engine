# ORDER LIFECYCLE SPEC

**Document ID:** TRA-OLS-001 · **Version:** 1.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/oms.py`, `runtime/execution.py`
**Mandate:** §27/§28/§29/§30/§39

---

## 1. The 14-State Machine (§27)

```
CREATED → VALIDATED → RISK_APPROVED → SUBMITTED → ACKNOWLEDGED
    → PARTIALLY_FILLED ⇄ (more fills) → FILLED
SUBMITTED/ACKNOWLEDGED/PARTIALLY_FILLED → CANCEL_PENDING → CANCELLED
live states → EXPIRED (TTL §39) | UNKNOWN (ambiguous) → RECONCILING
    → FILLED | PARTIALLY_FILLED | CANCELLED | FAILED | SUBMITTED
CREATED/VALIDATED/RISK_APPROVED → REJECTED | FAILED
Terminal: FILLED, CANCELLED, REJECTED, EXPIRED, FAILED
```

`TRANSITIONS` in `oms.py` is the authoritative table. **No order may
jump from decision to filled**: CREATED cannot reach
PARTIALLY_FILLED/FILLED (pinned by test). Every transition is ledgered
(`ORDER_LEDGER_EVENTS` vocabulary).

## 2. Idempotency (§28)

Order id = deterministic hash of governed fields (session, plan,
decision, correlation, symbol, side, type, quantity, limit). Duplicate
`create_order` calls return the EXISTING order (`created=False`) —
never a duplicate. Resubmission of an UNKNOWN/RECONCILING order raises
`AmbiguousOrderError` — the only legal path is reconciliation first,
retry after resolution.

## 3. Partial Fills (§30)

- Fills accumulate: `filled_quantity`, `remaining_quantity`,
  `average_fill_price` (VWAP), `total_fees`.
- Overfills are REFUSED (`fill quantity exceeds remaining`).
- Cancel-after-partial cancels only the remainder
  (`ORDER_CANCELLED_AFTER_PARTIAL` event).
- Mandate §30 example pinned by test: 100 = 20 + 30 + 50 with
  filled=100, remaining=0 at the end.

## 4. TTL / Expiry (§39)

`expire_if_elapsed(order_id, current_bar_index)`: live orders past
`submitted_at_bar + ttl_bars` transition to EXPIRED with the ledger
record (ttl, submitted bar, current bar, filled/expired quantities).
RT-F10 closure: unfilled orders now EXPIRE loudly instead of silently
never filling.

**Re-audit correction (BLOCKER 17):** `PARTIALLY_FILLED → EXPIRED` is
now a legal transition (partial-fill-then-expiry). v1.0.0 omitted it
from the authoritative transition table while `expire_if_elapsed`
accepted partially-filled orders — the combination raised
`InvalidTransitionError` at expiry. Pinned by
`test_restart_around_ttl_expiry`: every fill of an expired order
happened on bars within its TTL window (never executes post-expiry).

## 5. Execution Realism (§38, `runtime/execution.py`)

- **Latency**: filling starts at `submit bar + fill_lag_bars` — never
  same-bar.
- **Per-bar liquidity**: at most `participation_cap × bar_volume` units
  per bar; remainders spill to later bars (partial fills by market
  structure, not by accident).
- **MARKET price**: open ± half-spread ± impact (adverse stack);
  impact computed on THIS partial fill's quantity.
- **LIMIT price**: BUG-001 protection — BUY never above the limit,
  SELL never below; fills only on crossing bars.
- Every fill records the full cost decomposition (commission,
  slippage, spread) — nothing hidden.
- Cursor-based re-invocation (`from_bar`, `start_index`) prevents
  duplicate fills/fill-identities across bars.

## 6. Paper Isolation (§59)

`PAPER_MODE_STRUCTURAL_ISOLATION = True`: the adapter has no
credential, endpoint, network, or account surface anywhere (tested by
attribute scan + source conventions). No perfect fills: every fill
carries explicit adverse costs.
