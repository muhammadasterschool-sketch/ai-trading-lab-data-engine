# READINESS GATES — v3.1 matrix (authoritative states)

Rules: missing gate = NOT READY · failed gate = NOT READY · stale evidence = NOT READY ·
mock ≠ real verification · build ≠ operational reliability · green CI ≠ human approval ·
Binance data ≠ Exness authorization · PAPER readiness ≠ installed APK.

| # | Gate | Status | Evidence | Expiry / blocker |
|---|---|---|---|---|
| 1 | Repository & build provenance | PASS | baseline `f3b8bda2` verified live; branch chain verified; builds reproduce from source | — |
| 2 | Android engine security (loopback, caps, gates) | PASS (host) | 7 loopback/cap tests + v3.0.3 admin gates | on-device LAN-isolation NOT RUN |
| 3 | Runtime lifecycle reliability | NOT RUN | source-verified FGS/watchdog/boot | physical device required |
| 4 | Market-data source approval | PARTIAL | Yahoo: ACTIVE_LEGACY · Binance: PENDING_OWNER_REVIEW · MT5 bridge: NOT_AUTHORIZED_FOR_LIVE | owner review required |
| 5 | Instrument-universe integrity | PASS (Binance) | dynamic discovery + delist sweep tests | — |
| 6 | Data freshness | PASS (mechanism) | SAFE MODE (strategy) + staleness counters (Binance) | thresholds need on-device tuning |
| 7 | Data completeness | PASS (mechanism) | gap detection + truthful counters; no synthetic fills | long-run soak pending |
| 8 | Timestamp & OHLC validity | PASS | validators + 0 violations on live smoke | — |
| 9 | Strategy validation | PASS (mechanism) | Lab: fees + IS/OOS + Monte Carlo; owner-only approval | strategy approval is a human decision |
| 10 | Risk configuration & enforcement | PASS (source) | entry pipeline trace; admin-gated config | instrumented race tests NOT RUN |
| 11 | Kill-switch verification | PASS (source) | daily_kill_pct + persistence + admin gate | device test NOT RUN |
| 12 | Virtual execution integrity | PASS (source) | lifecycle + journal + conservative fills | deterministic replay on device NOT RUN |
| 13 | Ledger consistency | PASS (source) | accounts/equity/trades/orders reconciliation code | long-run soak pending |
| 14 | Idempotency & duplicate prevention | PASS (source) | one-trade-per-setup + one-position-per-symbol | — |
| 15 | Persistence & crash recovery | PASS (source) | WAL + guard persistence + DB repair | process-death test NOT RUN |
| 16 | Auditability | PASS | logs table + audit.csv + admin-blocked events | — |
| 17 | Mobile performance | NOT RUN | bounds by design only | device profiling required |
| 18 | Monitoring & alerting | PASS (basic) | notifications + dashboard status + coverage | alert delivery on device NOT RUN |
| 19 | Security & access control | PASS (host) | admin gates + audit; secrets untracked | adb/backup probe NOT RUN; keystore rotation owner decision |
| 20 | Test evidence | PASS (host) | 54/54 host tests (7 loopback/caps + 20 Binance ×2 variants) | instrumented tests NOT RUN |
| 21 | Source-specific operator verification | NOT RUN | Binance live smoke PASS (data only) · Exness: no operator environment | owner/operator action |
| 22 | Human governance approval | PENDING | — | owner decisions list below |
| 23 | Soak-plan validity | NOT STARTED | runbook drafted (`docs/30-DAY-PAPER-SOAK-RUNBOOK.md`) | requires gates 1–22 first |
| 24 | Explicit soak-start authorization | NOT GIVEN | — | separate owner action |

## Decision state

- **PAPER_READY = FALSE** (gates 3, 17, 21 not satisfied; approval pending)
- **LIVE_AUTHORIZATION = NOT_AUTHORIZED**
- **30-day paper soak: NOT STARTED (and NOT auto-startable)**

## Outstanding owner decisions

1. Merge/publish policy for the v3.0.2 + v3.0.3 + v3.1.0 candidate branches.
2. Keystore rotation (old keystore is public in history; forward-only hygiene done).
3. WebView self-signed-cloud policy (`onReceivedSslError → proceed()` kept for owner
   workflow; real cert or pin recommended).
4. Binance source approval (PENDING_OWNER_REVIEW) — required before any strategy may
   consume Binance data.
5. Schedule the paper-soak readiness review AFTER on-device verification.
