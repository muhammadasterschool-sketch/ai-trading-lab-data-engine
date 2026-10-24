# 05 — Evidence From a Genuine Exness DEMO Terminal

## Status: **BLOCKED — NO GENUINE-TERMINAL EVIDENCE EXISTS YET**

This implementation was developed and verified on a non-Windows host.
The official `MetaTrader5` Python package is Windows-only and requires
a running MT5 terminal with a real Exness DEMO account. Therefore:

| Evidence item | Status |
|---|---|
| Terminal connect + health against a real Exness DEMO server | **NOT RUN (BLOCKED_ON_OPERATOR_ENV)** |
| Positive DEMO verification against a real account | **NOT RUN (BLOCKED_ON_OPERATOR_ENV)** — verified only against the fake module's real-shaped payloads in unit tests |
| Observed symbol catalogue (real terminal) | **NOT RUN** |
| Real M1/M15 bars + ticks + freshness observation | **NOT RUN** |
| Validated symbol map with observed digests | **NOT RUN** — no real catalogue exists yet; any map authored today would be invention |
| Observed terminal build / server name in provenance | **NOT RUN** |

## What was verified WITHOUT a terminal (and is therefore NOT terminal evidence)

- Adapter contract + full fail-closed behaviour against an injected
  fake module (85 tests, all green, full suite 2994/8 skip/0 fail).
- The feed refuses to degrade into mock data when the package/terminal
  is absent (`MT5_E_MODULE_UNAVAILABLE`; probe exit 7).
- No order path exists (spy + AST + allowlist evidence).

These are CODE-CONTRACT evidence only. They do NOT verify Exness
behaviour, symbol naming, contract specifications, server names,
session times or data quality. Nothing in this repository may present
them as real-feed evidence.

## How to flip this document's status (operator, Windows host)

1. Execute `artifacts/mt5-integration/03-WINDOWS-HOST-SETUP.md` §2–§6.
2. Archive in THIS directory:
   - `self-test-<date>.json` (probe `--self-test --symbol <S>`)
   - `catalogue.json` (probe `--dump-catalogue`)
   - `map.json.validated.json` (probe `--validate-map`)
   - one bar-sample JSON per intended symbol
   - `pytest tests/test_mt5_terminal_integration.py -v` output
3. Update the table above from NOT RUN → RUN (with dates + commit SHA).

Until that happens, the `exness-mt5-demo` source candidate stays
UNVETTED, the blocked markets stay blocked, and no real-data or
operational-feed gate may claim anything from this work.
