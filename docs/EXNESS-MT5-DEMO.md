# EXNESS MT5 DEMO — honest status

## Verdict: `IMPLEMENTED_BUT_NOT_OPERATOR_VERIFIED` (data path) · orders NOT_AUTHORIZED

No Exness DEMO account was positively verified in any run of this project (the
integration requires a Windows PC with a MetaTrader5 terminal and operator-provided
demo credentials). No claim of working Exness connectivity is made.

## What actually exists

| Piece | Location | State |
|---|---|---|
| MT5-style symbol universe (27 halal commodities) | `EngineCore.HALAL_COMMODITIES` + `MT5_FEED` | ACTIVE — but the DATA source is Yahoo futures (unofficial), NOT an MT5 terminal. Labels in the UI say "MT5-style feed" honestly |
| Optional Windows bridge v2.0 | `public/downloads/mt5-bridge.py` (NOT in APK) | IMPLEMENTED — `/health`, `/candles` (data), `/order`, `/close`, `/positions` (owner-gated live mirror). Requires a Windows PC running the MetaTrader5 desktop terminal |
| Android-side bridge client | `EngineCore.fetchFromBridge/bridgeOrder/bridgeClose` | bridge OFF by default (`mt5_bridge` empty; `bridge_live=0`); setting it is ADMIN-only since v3.0.2 |
| Historical Python adapter lineage | remote branch `feat/exness-mt5-demo-market-data` (`src/data_engine/...`, `*_mock.py`) | OLD architecture, not part of the Android app; mock files clearly named; not maintained here |

## Mobile-only limitation (documented, NOT bypassed)

The `MetaTrader5` Python package requires the Windows desktop terminal — it cannot run
inside a normal Android app. Therefore: **the phone cannot reach Exness MT5 directly.**
The bridge makes the user's PC an optional data/order relay. This is stated in the UI
registry (`EXNESS_MT5_BRIDGE` limitations) and here. The Binance/Android engine does
NOT require the PC — the bridge is strictly optional.

## DEMO verification requirements (for the future)

When an operator runs the bridge against an Exness terminal, the adapter MUST (before
any trust): positively verify `ACCOUNT_TRADE_MODE` is DEMO (reject REAL/CONTEST and
any unverifiable type), verify broker server name, re-verify after reconnect, keep a
read-only allowlist (account metadata, symbol metadata, ticks, bars), never call order
functions in the data path, never transmit credentials to the Android engine or logs.
None of this is claimed as done — the bridge currently reports account info but does
not implement the DEMO-mode refusal gate. That gate is a prerequisite for the
`exness-mt5-demo` source approval, which remains a separate human decision.

## Operator checklist (when a PC + Exness demo terminal is available)

1. Run `mt5-bridge.py` on Windows with a DEMO login.
2. `GET /health` → verify server + trade_mode==DEMO evidence before configuring the app.
3. Configure `mt5_bridge` URL in-app (owner only) → check `/api/brokers/registry`
   shows `CONFIGURED_DATA_ONLY_DEMO_UNVERIFIED`.
4. Record terminal screenshots + JSON responses as evidence files.
5. Only then update this document's verdict.
