#!/usr/bin/env python3
"""OPTIONAL LIVE-FEED SMOKE — Binance public BTCUSDT 15m klines.

EXPLICITLY LABELLED SMOKE, NOT A TEST, NOT READINESS EVIDENCE:

- Contacts the REAL public endpoint api.binance.com exactly ONCE per
  run (connectivity probe) and once for a 5-kline window. This is
  network-dependent and is NEVER collected or executed by pytest/CI
  (it lives in scripts/, outside the test tree).
- What it CAN honestly show: the endpoint responded over the network
  right now, and the returned rows passed the project adapter's
  parsing + OHLC + ordering + closed-candle machinery.
- What it can NEVER show: continuous feed reliability, licence
  compliance, jurisdictional availability, source approval, or
  OPERATIONAL_FEED_READY / PAPER_READY. The source
  `binance-public-spot` remains UNVETTED in the governed source
  registry until the operator records the human SRC-APPROVAL
  decision (docs/OPERATOR_SOURCE_APPROVAL_PACK.md).

Run (desktop/Linux environment with network access):

    cd <repo root>
    uv run python scripts/binance_public_smoke.py

Exit code 0 = smoke observations completed (regardless of verdicts —
this script never claims readiness). Failures print typed diagnostics.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, UTC

from data_engine.platform.feed_source_candidates import (
    build_feed_source_registry,
)
from data_engine.providers.binance_public import (
    BINANCE_PUBLIC_PROVIDER_NAME,
    BinancePublicError,
    BinancePublicKlinesProvider,
)
from data_engine.schemas import ProviderConfig, Timeframe

SYMBOL = "BTCUSDT"
TIMEFRAME = Timeframe.M15
FETCH_BARS = 5


def main() -> int:
    print("=== Binance public spot klines — LIVE SMOKE (optional) ===")
    print("SMOPE SCOPE: endpoint connectivity + adapter mechanics ONLY.")
    print("NOT source approval. NOT operational-feed readiness.")
    print("NOT a CI test. Source stays UNVETTED (human SRC-APPROVAL")
    print("required — see docs/OPERATOR_SOURCE_APPROVAL_PACK.md).")
    print()

    registry = build_feed_source_registry()
    record = registry.get(BINANCE_PUBLIC_PROVIDER_NAME)
    print(f"governed source registry status : {record.verification_status.value}")
    print(f"approved scopes                 : {record.approved_usage_scopes or '()'}")
    print()

    config = ProviderConfig(
        provider_name=BINANCE_PUBLIC_PROVIDER_NAME,
        provider_type="api",
        endpoint="https://api.binance.com/api/v3",
        rate_limit_per_minute=60,
    )
    provider = BinancePublicKlinesProvider(config)

    # -- 1. connectivity probe (one request) --------------------------
    ok = provider.check_connectivity()
    probe = provider.last_fetch_raw.get("last_connectivity", {})
    print(f"[1] connectivity probe           : {'OK' if ok else 'FAILED'}")
    if not ok:
        print(f"    diagnostic: {probe.get('error', 'n/a')}")
        print()
        print("SMOKE RESULT: endpoint unreachable from this environment.")
        print("No readiness implication either way — connectivity is one")
        print("input among many, and it is NOT approval evidence.")
        return 0

    # -- 2. closed-kline window through the REAL adapter ---------------
    now = datetime.now(UTC)
    window_bars = FETCH_BARS + 2  # headroom so >=5 closed bars exist
    start = now - timedelta(minutes=15 * window_bars)
    print(f"[2] fetching {window_bars} x 15m klines ending {now.isoformat()}")
    try:
        candles = provider.fetch_candles(SYMBOL, TIMEFRAME, start, now)
    except BinancePublicError as exc:
        print(f"    ADAPTER FAILURE (typed): {type(exc).__name__}: {exc}")
        print()
        print("SMOKE RESULT: adapter refused the live payload — the")
        print("fail-closed machinery did its job. Inspect the reason")
        print("above; nothing was fabricated or dropped silently.")
        return 0

    meta = provider.last_fetch_raw
    print(f"    rows received               : {meta['raw_row_count']}")
    print(f"    closed candles kept          : {meta['candle_count']}")
    print(f"    still-open candles excluded  : {meta['open_candles_excluded']}")
    print(f"    gaps reported                : {len(meta['gaps_reported'])}")
    print(f"    pages (raw sha256 kept)      : {len(meta['pages'])}")
    for candle in candles[-FETCH_BARS:]:
        print(
            f"      {candle.timestamp.isoformat()}  "
            f"O={candle.open:<10} H={candle.high:<10} "
            f"L={candle.low:<10} C={candle.close:<10} V={candle.volume}"
        )

    # -- 3. feed-gate honesty check (expect FALSE: source UNVETTED) ----
    from data_engine.runtime.feed_composition import evaluate_paper_feed

    canonical_id = f"{SYMBOL[:-4]}/{SYMBOL[-4:]}"
    print()
    print("[3] operational-feed gate evaluation (EXPECTED: FAIL — unapproved)")
    from data_engine.providers import interval_for_timeframe

    try:
        report, bars, canonical, confirmed = evaluate_paper_feed(
            provider,
            source_registry=registry,
            source_name=BINANCE_PUBLIC_PROVIDER_NAME,
            instrument=SYMBOL,
            timeframe=TIMEFRAME,
            interval=interval_for_timeframe(TIMEFRAME),
            as_of=now,
            required_warmup_bars=FETCH_BARS,
        )
    except BinancePublicError as exc:
        print(f"    composition could not evaluate (typed): {exc}")
        return 0
    print(f"    verdict                      : {'PASS' if report.passed else 'FAIL'}")
    for reason in report.reasons:
        print(f"      reason: {reason}")
    print()
    print("SMOKE RESULT: connectivity + mechanics observed; gate verdict")
    print(f"is {'PASS' if report.passed else 'FALSE'} with the reasons above —")
    print("the UNVETTED source status is the honest blocker. Only the")
    print("operator's SRC-APPROVAL decision (plus a provisioned feed and")
    print("keyed-MAC key) can ever change PAPER_READY.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
