# VIRTUAL EXECUTION — deterministic paper model

## What exists (source-traced, preserved)

- Paper fills only. `testBroker` performs ZERO network calls (verbatim code comment:
  "this build runs paper trading only").
- Simulated order lifecycle: intent → risk validation → accepted/rejected →
  fill at trigger price with slippage model (`slipBps`, default 2 bps/side) →
  position/balance updates → realized P/L; orders table records the lifecycle.
- Journal per trade: r_mult, mfe, mae, risk_amt, decision, tca_bps (realized TCA),
  council score, win_prob, features (JSON) — the audit trail for every simulated fill.
- Idempotency: one trade per setup per account; one open position per symbol;
  duplicate intents rejected by dedup query.
- Reconciliation: equity snapshots (`equity` table, TRUE-HWM peak ratchet), accounts
  balance vs trade sum; manual close recomputes pnl and appends logs.
- Restart recovery: guards persisted; trades/orders/accounts survive process death
  (SQLite WAL); open-trade management resumes (`manageOpenTrades`).

## Explicit limits of the fill model (no overclaiming)

- Fills are candle-driven (5m closed bars). There is NO intrabar tick path — a stop and
  a target inside the same candle are resolved conservatively (worst-case ordering);
  exchange-level fill fidelity is NOT claimed.
- The Yahoo feed is closed-bars with ~5–11 min lag: live-trigger fills occur on the
  NEXT observation after the trigger — by construction no look-ahead: the engine only
  sees candles with ts ≤ now (SAFE MODE additionally blocks stale data).
- Slippage/fees are modeled parameters, not measured fills.

## Determinism

Strategy logic is a pure function of stored candles + config (no wall-clock inside the
signal computation beyond explicit session gates). Backtests (StrategyLab) run
deterministic simulations with fees, IS70/OOS30 walk-forward and Monte Carlo shuffle
(seedless shuffle = reproducible per dataset). Host-JVM regression suite (54 tests)
locks parser/validator behavior.

## Hard separation from broker orders

- No order method exists in `BrokerAdapter` (interface-level separation).
- Binance module contains zero order code (grep-verifiable; unit-tested surface).
- The ONLY real-order surface remains the optional MT5 bridge mirror:
  `bridgeOrder/bridgeClose` first line `if (!bridgeLive()) return;`, `bridge_live`
  settable ONLY by the owner (ADMIN gate + audit log), default OFF.
- Paper results are labeled simulated in the UI and API (`source: PAPER`).
