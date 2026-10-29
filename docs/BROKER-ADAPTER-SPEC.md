# BROKER ADAPTER SPEC — v3.1

## Contract (`engine/BrokerAdapter.java`)

- `id()`, `displayName()`, `adapterVersion()`, `capabilities()`, `statusLabel()`,
  `freshnessPolicy()`, `credentialRequirements()`, `limitations()`, `sourceApproval()`.
- **Capability enum:** INSTRUMENT_DISCOVERY, MARKET_DATA_LIVE, MARKET_DATA_HISTORICAL,
  ACCOUNT_METADATA, READ_ONLY_CONNECTION_TEST, ORDER_PLACEMENT.
- **Unknown capabilities default to disabled** (`has(c)` false unless declared).
- **The interface has NO order method.** ORDER_PLACEMENT is only a declaration flag;
  the sole real-order surface (MT5 bridge mirror) is declared so nothing is hidden,
  and it is OFF by default + owner-gated.
- Status labels are honest evidence-based strings: CONNECTED…, READ_ONLY, UNVERIFIED,
  STALE, BLOCKED, SIMULATED, NOT_RUN, NOT_AUTHORIZED, DISABLED_BY_DEFAULT… Never
  LIVE/READY/VERIFIED without operational evidence.

## Registry (`engine/BrokerRegistry.java`)

Explicit registration (no scanning). Current adapters:

| id | Capabilities declared | Status | Approval |
|---|---|---|---|
| YAHOO_CME_FUTURES | MARKET_DATA_LIVE, MARKET_DATA_HISTORICAL | CONNECTED_READ_ONLY_UNOFFICIAL | ACTIVE_LEGACY (owner v2.1) |
| BINANCE_SPOT | INSTRUMENT_DISCOVERY, MARKET_DATA_LIVE, MARKET_DATA_HISTORICAL, READ_ONLY_CONNECTION_TEST | READ_ONLY (per-run truth via coverage) | PENDING_OWNER_REVIEW |
| EXNESS_MT5_BRIDGE | MARKET_DATA_LIVE, ACCOUNT_METADATA, ORDER_PLACEMENT (declared honestly) | DISABLED_BY_DEFAULT / CONFIGURED_DATA_ONLY_DEMO_UNVERIFIED / ORDER_MIRROR_ON_OWNER_GATED | NOT_AUTHORIZED_FOR_LIVE |

Inspection: `GET /api/brokers/registry` and dashboard → Insights → 🌐 Markets.

## Implementation order (per master prompt)

1. ✅ Binance Spot (v3.1, read-only, live-smoke PASS)
2. ✅/⚠️ Exness MT5 demo/read-only — bridge implemented; DEMO verification gate NOT
   implemented; operator environment unavailable → NOT operator-verified
3. ⬜ Additional crypto exchanges — require compatibility review (official API, Android
   compatibility, data permissions, rate limits, read-only feasibility) BEFORE any code
4. ⬜ Additional Forex/CFD brokers — same gate
5. ⬜ Other markets — only when instrument semantics, sessions, data permissions and
   risk modeling are implemented

## Cross-provider integrity rules

- Native symbol, canonical identity, provider, market category, quote currency,
  timestamp semantics, precision and provenance are preserved per provider.
- Prices from different venues are NEVER combined as interchangeable; no synthetic
  candles from merging providers (no such code exists).
- Approval is per-adapter; no adapter inherits another's approval; a new adapter
  starts at PENDING_OWNER_REVIEW with unknown capabilities disabled.
