# 01 — Architecture & Threat-Model Note

Status: implemented on `feat/exness-mt5-demo-market-data` (plan commit
`169b655`, implementation commit `79f3f49`, base `4cc6782`).

## 1. Where this fits (no parallel architecture)

The genuine Exness MT5 DEMO feed is the structural sibling of the
already-proven crypto pilot (`providers/binance_public.py`):

| Concern | Binance pilot | MT5 feed |
|---|---|---|
| Framework | `MarketDataProvider` + `ProviderFactory` | same (registered `exness-mt5-demo`) |
| Output schema | `schemas.Candle` | same |
| Injectable boundary | HTTP transport | `platform/mt5_terminal.py` (the MetaTrader5 module) |
| Error style | structured hierarchy | structured `MT5_E_*` hierarchy |
| Closed-candle rule | `close_time < reference` | `open_time + tf_seconds <= now` |
| Provenance | raw-page SHA-256 + params | per-batch `MT5FeedProvenance` model |
| Source governance | candidate UNVETTED + SRC-APPROVAL | same mechanism, new candidate |

The pre-existing `platform/mt5.py` fail-closed adapter remains the
mock-contract read surface used by platform tests; it gained a
backward-compatible `require_demo` hardening. The genuine feed does
NOT double-wrap it — raw-field fidelity (MT5-native epochs, tick
volume, spread) and the terminal-boundary allowlist demand the direct
boundary; both surfaces share models (`AccountMode`), the refusal
exception (`MT5OrderRefusedError`) and the same refusal pattern.

## 2. Component map

```
ExnessMT5DemoFeed (platform/mt5_market_data.py)
  ├─ policy layer: positive DEMO verification, server match,
  │   closed-candle filter, freshness (raise/flag), provenance,
  │   structured errors, reconnect orchestration, refusal trio
  ├─ symbol map (platform/mt5_symbol_map.py)
  │     canonical → broker_symbol, validated against OBSERVED
  │     symbol_info, SHA-256 digest-stamped, re-checked at every connect
  └─ terminal boundary (platform/mt5_terminal.py)
        RealMT5Terminal: initialize/login/shutdown + read methods only,
        dispatched through ONE choke point that refuses any function
        outside MT5_READ_METHODS; numpy/namedtuple → dict conversion;
        constants resolved FROM the installed module (never copied)
              │
              ▼ (Windows only)
        MetaTrader5 package ↔ running MT5 terminal ↔ Exness DEMO server
```

## 3. Threat model (STRIDE-flavoured, paper-only scope)

| Threat | Control |
|---|---|
| **T1 Order submission through the terminal** | The feed NEVER references order functions; `RealMT5Terminal._call` refuses any name outside the closed read allowlist; the fake module's order functions record + raise, and the negative suite proves zero attempts across full workflows; an AST scan forbids order calls in the three modules. The repo-wide venue layer additionally refuses REAL-mode descriptors at registration. |
| **T2 REAL account masquerading as DEMO** | `connect()` compares the OBSERVED `account_info().trade_mode` against the INSTALLED module's own `ACCOUNT_TRADE_MODE_DEMO` constant. REAL (2), CONTEST (1), unknown and None are refused. Every reconnect repeats the full verification. `expected_server_substring` cross-check protects against connecting to an unexpected server. |
| **T3 Fabricated/assumed market data** | Empty terminal answers are structured errors; no conversion, interpolation or rate-series-to-OHLC path exists; the map is observation-only (an unobserved symbol is refused; identity mappings go through the same observation); OHLC relations are validated per bar; forming bars are excluded by default. |
| **T4 Broker-side symbol/spec drift** | Validated entries carry SHA-256 digests of the observed specification; `recheck()` at every connect refuses on any drift (digits/point/contract size/name/path) until the operator re-validates. |
| **T5 Stale data accepted as fresh** | Explicit staleness threshold (default 300 s, operator-configurable) with `raise` (default) or `flag` policy; weekend/closed-market behaviour is a documented, visible condition — never silent. |
| **T6 Credential leakage** | Env-only configuration (`MT5_TERMINAL_PATH/LOGIN/PASSWORD/SERVER[+MT5_EXPECTED_SERVER]`), `SecretStr` password, redacted `__repr__`, errors name only missing VARIABLE names; provenance/health payloads are credential-free; probe prints no values. Tests assert every one of these. |
| **T7 Mock data relabelled as real** | The feed fails closed with `MT5_E_MODULE_UNAVAILABLE` when the package/terminal is absent; integration checks auto-SKIP with `BLOCKED_ON_OPERATOR_ENV`; nothing in the codebase can turn mock data into feed output. |
| **T8 Governance bypass** | The feed flips no gate: candidate enters UNVETTED, BLOCKED_MARKETS unchanged, approvals untouched; `status --gates` re-verified identical post-implementation; soak preflight untouched. |

Residual risks (honest): MT5 timestamps are broker-server epochs —
session/timezone semantics need operator validation before any
freshness claim is treated as market fact (provenance carries raw
epochs verbatim); MN1 freshness uses a nominal ~30-day bar length; no
SLA on terminal availability. All documented in the runbook.
