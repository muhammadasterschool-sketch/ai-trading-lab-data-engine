# RISK ENGINE — controls inventory (verified by source trace)

Status: **PRESERVED UNCHANGED in v3.1** (v3.0 QUANT PRO stack + v3.0.3 governance).
The Binance phase added data plumbing only — no risk thresholds were invented,
ratified, or weakened.

## Entry pipeline (fail-closed order, `EngineCore.openTrade3C`)

1. `freshData()` — SAFE MODE: stale feed → NO entry (threshold `safe_mode_bars`,
   default 3 bars ≈ 15 min; market-closed aware since v3.0.1)
2. `entryBlocked()` — cooldown (`cooldown_min`) + consecutive-loss pause (`consec_loss`)
   + daily kill switch (`daily_kill_pct`, opt-in default 0 = owner's UNLIMITED choice)
3. `tradingAllowed()` — v2.1 OWNER TRADING GATE (per-user `trade_ok`, owner-granted)
4. CME halt window (17:00–18:00 ET) + weekend awareness
5. Event gate — HIGH-impact news pause (opt-in)
6. One-position-per-symbol + duplicate-setup dedup (idempotency)
7. Signal Council minimum (`council_min`, opt-in)
8. Position sizing: `risk_pct` of balance; portfolio heat cap + bucket cap (opt-in)
9. Slippage/spread model (`slip_bps`), fees modeled in Lab backtests
10. Journal columns (risk_amt, decision, council, win_prob, features) + orders row

All mutation of these controls is ADMIN-only since v3.0.3 (403 + audit on attempt).

## Verification status per master prompt

| Control | Status |
|---|---|
| Sizing / per-trade / heat / bucket / daily-kill / consec-loss / cooldown / dedup | source-traced PASS (prior audits + this run's spot-check) |
| Stale-data rejection | PASS (source) — live stale-injection test NOT RUN |
| Instrument precision validation | Yahoo universe: not required (paper sizing); Binance registry stores tick/step/minNotional for FUTURE strategy use — enforcement pending a strategy that consumes Binance data |
| Persistence / restart recovery | guards persisted (`guard_state_v1`); DB WAL; on-device restart test NOT RUN |
| Clock/session constraints | `marketClosedET()` + CME halt; exchange-side clock-skew check added for Binance (reported, informational) |
| Kill switch verification | source-traced; device-level kill test NOT RUN |

## Missing/invalid risk configuration

`riskPct()` falls back to defaults on parse failure; entry pipeline requires the owner
trading gate. A deliberately corrupted config cannot enable trading (fail toward OFF).

## What v3.1 changed in risk

Nothing. Deliberately. The Binance integration is read-only market data in separate
tables; the strategy universe is untouched; UNLIMITED daily P/L default (owner choice)
and every opt-in cap are exactly as before.
