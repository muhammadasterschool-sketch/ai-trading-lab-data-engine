# PAPER OPERATOR RUNBOOK

```text
Document Type:  Operator procedures (setup, run, verify, recover)
Phase:          Paper-readiness engineering cycle (2026-10-11/12)
Authority:      B — CURRENT SUPPORTING (procedures; governance
                authority remains with the decision records)
Status:         CURRENT
Version:        1.0.0
Audience:       The human operator of a PAPER-ONLY trading session
Environment:    Desktop/Linux (Python 3.11 or 3.12, uv). Pydroid 3 is
                NOT supported for running this repository — see §12.
```

> **PAPER-ONLY.** This system routes orders to an in-process
> simulator. There is no broker credential, no live order route, and
> the `LiveAuthorizationGate` denies live trading unconditionally.
> Nothing in this runbook can change that.

---

## 1. Installation

```bash
git clone https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine.git
cd ai-trading-lab-data-engine
# Python >= 3.11 required (3.11 and 3.12 are CI-verified)
uv sync --frozen --extra dev
```

Configuration template — copy to a file OUTSIDE git (e.g.
`~/paper-session.env`) and fill placeholders only:

```bash
# ── paper-session environment (placeholders only) ──────────────
# Ledger MAC key (>= 32 bytes of GENUINE entropy — see §5)
export RUNTIME_LEDGER_MAC_KEY="<hex-encoded random key>"
#   or (absolute path OUTSIDE the repository):
# export RUNTIME_LEDGER_MAC_KEY_FILE="/secure/path/outside/repo.key"
# No other secrets exist: market-data adapters use PUBLIC endpoints
# only; there is no API key, broker login, or account identifier.
```

## 2. Run the offline test suite (no network)

```bash
uv run pytest -q -p no:cacheprovider
```

Expected today: **1,755 passed + 1 skipped** (deterministic; the
same command three times must agree — CI runs it thrice). Network is
never touched by the suite: all provider tests use sanitized
fixtures through an injected fake transport.

## 3. Optional live-feed smoke (explicitly NOT a test, NOT approval)

```bash
uv run python scripts/binance_public_smoke.py
```

- Contacts the real public Binance endpoint once or twice per run.
- Prints honest verdicts: connectivity + adapter mechanics observed;
  the operational-feed gate still evaluates FAIL while the source is
  UNVETTED.
- Exit code 0 means "observations completed", never "ready".
- Do NOT treat a successful smoke as source approval — see
  `docs/OPERATOR_SOURCE_APPROVAL_PACK.md`.

## 4. Interpret the readiness report

Authoritative verdict: `PAPER_TRADING_READINESS_FINAL_REPORT.md`
(currently §0C is the latest amendment).

- Verdict formula: `PAPER_READY = ALL 32 mandatory gates TRUE`.
- Today's verdict: **FALSE** — exact live blocker list in §0C §5.
- Gates cannot be forced: the gate reads no environment variable,
  has no override flag, and absent evidence defaults to FALSE.
- Per-gate PASS requires objective current evidence — a module
  existing, a fixture test passing, or a public API answering once
  is never sufficient (policy §7 of the report).

## 5. Provision the ledger MAC key securely (OUTSIDE git)

The runtime ledger chain signs events with a keyed MAC. Provision a
genuine key — never invent, hardcode, or commit one:

```bash
# generate >= 32 bytes of genuine entropy (OS CSPRNG)
openssl rand -hex 32 > /secure/path/outside/repo.key   # mode 600
export RUNTIME_LEDGER_MAC_KEY_FILE="/secure/path/outside/repo.key"
```

Rules enforced by `runtime/mac_custody.py` (tested):
- key file must be an ABSOLUTE path OUTSIDE the repository;
- the entropy floor rejects short/weak material;
- incorrect keys on restart are REJECTED (fail closed);
- only a KEY FINGERPRINT (never material) appears in logs/records.

Record the fingerprint in `KEYED_MAC_CUSTODY_DECISION_RECORD.md` §6
provisioning log (fingerprint only — never the key).

## 6. Record source approval (after YOU verify the terms)

Follow `docs/OPERATOR_SOURCE_APPROVAL_PACK.md` end-to-end: review the
candidate record, review the licence/terms yourself, fill the
SRC-APPROVAL template exactly, and record the decision through the
registry's human-only API (exact commands in that pack §6).

## 7. Start / stop paper trading safely

Starting a paper session is REFUSED unless every mandatory gate
passes — that is the design. The bootstrap path (with all inputs
genuinely satisfied) is:

```bash
uv run python - <<'PY'
from datetime import datetime, UTC
from data_engine.prediction.source_registry import SourceVerificationStatus
from data_engine.platform.feed_source_candidates import build_feed_source_registry
from data_engine.providers import BinancePublicKlinesProvider, interval_for_timeframe
from data_engine.runtime.feed_composition import build_paper_feed_evidence
from data_engine.schemas import ProviderConfig, Timeframe

# 1. YOUR approved registry (see docs/OPERATOR_SOURCE_APPROVAL_PACK.md §6)
registry = build_feed_source_registry()   # + your recorded approval

# 2. REAL feed, closed candles only
provider = BinancePublicKlinesProvider(ProviderConfig(
    provider_name="binance-public-spot", provider_type="api",
    endpoint="https://api.binance.com/api/v3",
))

# 3. Compose the 32nd-gate evidence (FAILS while anything is wrong)
evidence, report, bars = build_paper_feed_evidence(
    provider,
    source_registry=registry,
    source_name="binance-public-spot",
    instrument="BTCUSDT",
    timeframe=Timeframe.M15,
    interval=interval_for_timeframe(Timeframe.M15),
    as_of=datetime.now(UTC),
    required_warmup_bars=30,
)
print(report.passed, list(report.reasons))
# 4. Submit `evidence` to the PaperReadinessGate with the other 31
#    gates' evidence, then TradingRuntime.start() — see
#    tests/test_feed_composition.py::TestRuntimeIntegration for the
#    exact wiring the tests prove end-to-end.
PY
```

Stop: halt the session process; the kill-switch and durable state
store persist the exact position (recovery is proven at ten restart
points). The kill switch (trip reasons recorded in the incident
ledger) refuses new entries until cleared per governance.

## 8. Verify the paper broker cannot touch live execution

```bash
uv run pytest tests/test_paper_trading.py tests/test_runtime_safety.py -q
```

Structural guarantees (all test-pinned):
- `src/data_engine/paper/*` has no broker, no credentials, no
  account, no order route beyond the in-process simulator.
- `LiveAuthorizationGate` ALWAYS denies (paper/evaluation.py).
- The Binance adapter refuses any `api_key_env_var` configuration
  and only ever calls `/api/v3/ping` and `/api/v3/klines` (GET).
- MT5 adapter order submission is REFUSED ALWAYS (policy).

## 9. Inspect health, feed freshness, positions, orders, risk, audit

- Feed freshness: the `OperationalFeedReport` from §7 prints
  `latest_bar_timestamp`, `as_of`, staleness reasons, quality
  rejections, warm-up counts.
- Positions/orders/fills/risk: the durable `ExecutionStateStore`
  snapshot (session state directory) + `data_engine` CLI
  (`data-engine --help` for the platform surface: dashboard,
  workbook exports under `data/exports/`).
- Audit ledger: ledger chains verify via `runtime.ledgers.verify()`
  (wired into the runtime; MAC-verified when a key is provisioned).

## 10. Recover after restart or feed outage

- Restart: LOAD → VERIFY → RESTORE → RECONCILE is automatic and
  test-proven; a DEGRADED snapshot restarts DEGRADED (never cured by
  restart — fail closed).
- Feed outage: the adapter raises typed errors (timeout / connect /
  rate-limit); the composition surfaces them; new entries stop and
  the diagnostic reason is recorded. Stale windows (> 900 s by
  default) fail the feed gate — new entries stop until fresh data
  returns. Nothing is fabricated during the outage.

## 11. Disable a market that fails validation

Markets are enabled per instrument allowlist + approved source. To
disable crypto: remove the symbol from the adapter's
`instrument_allowlist` (default: exactly `["BTCUSDT"]`) or simply do
not approve the source — an UNVETTED source blocks activation by
construction. Forex/stocks/metals are ALREADY blocked (no validated
genuine 15m source — see the approval pack §4).

## 12. Pydroid 3 / mobile note

The full project requires a desktop/Linux environment (uv, Python
3.11/3.12, the pinned dependency lock). **Pydroid 3 cannot run the
suite and is not a supported execution environment.** It remains
useful only for isolated connectivity diagnostics (as already
recorded for the Binance endpoint) — those diagnostics are
connectivity evidence only, never readiness evidence.
