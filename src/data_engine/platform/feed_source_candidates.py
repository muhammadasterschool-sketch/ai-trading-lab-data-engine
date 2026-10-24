"""Governed FEED-SOURCE CANDIDATE declarations (Phase C — UNVETTED).

This module declares every PROPOSED operational-feed source as an
in-memory :class:`~data_engine.prediction.source_registry.DataSourceRecord`
with ``verification_status = UNVETTED``. It is the machine-readable
companion to ``docs/OPERATOR_SOURCE_APPROVAL_PACK.md`` (the human
evidence pack + SRC-APPROVAL template).

Hard rules honoured here:

- NOTHING is approved by this module. Records enter UNVETTED; only
  the registry's human-only ``submit_approval`` (approver_kind=
  "human") can change that — and this module never calls it.
- No credentials appear anywhere (the registry is credential-free by
  schema, ``extra="forbid"``).
- The four evidence classes stay distinct and are never conflated:
  endpoint connectivity / basic OHLCV validity / operational feed
  readiness / research-dataset verification.
- Markets with no validated genuine 15-minute source are declared as
  BLOCKED candidates whose licence/coverage honestly states the
  dependency is MISSING — they cannot pass the feed gate even if
  bars existed, because their status is UNVETTED and no approval
  path exists yet.

Usage (composition / evidence)::

    from data_engine.platform.feed_source_candidates import (
        build_feed_source_registry,
    )
    registry = build_feed_source_registry()   # all candidates UNVETTED
"""

from data_engine.prediction.source_registry import (
    DataSourceRecord,
    DataSourceRegistry,
)

__all__ = [
    "CANDIDATE_SOURCES",
    "BLOCKED_MARKETS",
    "build_feed_source_registry",
    "candidate_record",
]


def candidate_record(source_name: str) -> DataSourceRecord:
    """Build one UNVETTED candidate record by source name."""

    if source_name == "binance-public-spot":
        return DataSourceRecord(
            source_name="binance-public-spot",
            source_type="exchange-api",
            license_basis=(
                "UNKNOWN — Binance Terms of Use / API Terms have NOT "
                "been reviewed or confirmed by the operator; "
                "jurisdictional availability and public-data use "
                "conditions UNVERIFIED"
            ),
            coverage=(
                "Binance spot public klines; pilot scope exactly "
                "BTCUSDT (instrument allowlist enforced in the "
                "adapter); ~24/7 trading; endpoint stability over "
                "time UNMEASURED"
            ),
            granularity=(
                "1m/5m/15m/1h/4h/1d klines (OHLCV, base-asset volume)"
            ),
            expected_limitations=(
                "public REST rate limits (HTTP 429/418, IP weight "
                "budget — client-side rolling budget also enforced)",
                "no bid/ask on the klines endpoint (no spread data)",
                "still-open kline excluded until closed (adapter "
                "enforces closed_only by default)",
                "no SLA — availability can change without notice",
                "api.binance.com reachability varies by jurisdiction; "
                "no fallback endpoints validated",
                "no signed/account/order endpoints used (public data "
                "only — structurally incapable of trading)",
            ),
            revision_behavior=(
                "Binance klines are append-mostly; a closed kline CAN "
                "be revised by the exchange in rare cases — revisions "
                "are NOT announced on the endpoint; REVISION POLICY "
                "UNVERIFIED"
            ),
            corporate_action_behavior=(
                "not applicable to spot crypto pairs (no corporate "
                "actions); delistings end the series without migration"
            ),
            provenance_mechanism=(
                "per-page raw JSON SHA-256 content hashes + request "
                "params + retrieval timestamps retained by the "
                "adapter (raw-response preservation); kline "
                "open_time/close_time carried verbatim"
            ),
            notes=(
                "CANDIDATE ONLY — one manual connectivity observation "
                "exists (five BTCUSDT 15m klines: four closed, one "
                "open, basic OHLCV checks passed; operator Pydroid 3 "
                "diagnostic). That is endpoint-connectivity evidence "
                "ONLY: NOT continuous-feed reliability, NOT licence "
                "compliance, NOT source approval.",
                "REQUIRED FOR APPROVAL: operator review of Binance "
                "Terms of Use + API Terms, jurisdiction check, "
                "licence/permitted-use confirmation, then a recorded "
                "SRC-APPROVAL decision (see "
                "docs/OPERATOR_SOURCE_APPROVAL_PACK.md).",
            ),
        )

    if source_name == "forex-15m-ohlc":
        return DataSourceRecord(
            source_name="forex-15m-ohlc",
            source_type="exchange-api",
            license_basis=(
                "MISSING DEPENDENCY — no genuine 15-minute forex OHLC "
                "provider has been identified or validated"
            ),
            coverage=(
                "NONE VALIDATED — the operator's Forex master bundle is "
                "a USD-base DAILY RATE SERIES (research-only; see "
                "data_engine.providers.rate_series) and CANNOT serve "
                "as an OHLC candle feed"
            ),
            granularity="required: 15-minute OHLC bid/ask-capable bars",
            expected_limitations=(
                "forex trades ~24/5 with weekend gaps and session "
                "structure (Sydney/Tokyo/London/NY) — session calendar "
                "handling required",
                "symbol conventions differ across providers "
                "(EURUSD vs EUR/USD vs EUR_USD)",
                "rate-series-to-OHLC conversion is FORBIDDEN "
                "(fabrication)",
            ),
            revision_behavior=(
                "UNKNOWN — no candidate provider selected"
            ),
            corporate_action_behavior=(
                "not applicable (no corporate actions in FX); "
                "currency redenominations are rare manual events"
            ),
            provenance_mechanism=(
                "NONE — no provider validated; the rate-series reader "
                "carries its own honest REAL_UNVERIFIED provenance"
            ),
            notes=(
                "BLOCKED MARKET — forex paper execution stays blocked "
                "until a genuine 15m OHLC source is proposed, vetted "
                "and HUMAN-APPROVED.",
            ),
        )

    if source_name == "stocks-15m":
        return DataSourceRecord(
            source_name="stocks-15m",
            source_type="exchange-api",
            license_basis=(
                "MISSING DEPENDENCY — no intraday equities provider "
                "identified or validated; intraday equity data is "
                "typically licence-restricted and PAID"
            ),
            coverage=(
                "NONE VALIDATED — the operator's Stocks master bundle "
                "is monthly/quarterly (0/9 assets D1-suitable) and is "
                "NOT intraday data"
            ),
            granularity="required: 15-minute OHLCV bars per exchange",
            expected_limitations=(
                "exchange calendars + holidays required (regular vs "
                "extended sessions)",
                "corporate actions and symbol changes require handling",
                "free API tiers generally do NOT provide sufficient "
                "15-minute coverage — UNVERIFIED for every candidate "
                "and never assumed",
            ),
            revision_behavior=(
                "UNKNOWN — no candidate provider selected"
            ),
            corporate_action_behavior=(
                "REQUIRED — splits/dividends/ticker changes must come "
                "from the provider verbatim; no synthetic adjustment"
            ),
            provenance_mechanism="NONE — no provider validated",
            notes=(
                "BLOCKED MARKET — equities paper execution stays "
                "blocked until a genuine 15m source is proposed, "
                "vetted and HUMAN-APPROVED.",
            ),
        )

    if source_name == "metals-15m":
        return DataSourceRecord(
            source_name="metals-15m",
            source_type="exchange-api",
            license_basis=(
                "MISSING DEPENDENCY — no metals intraday provider "
                "identified or validated"
            ),
            coverage=(
                "NONE VALIDATED — the operator's Metals master bundle "
                "is monthly/quarterly with 19 impossible-OHLC rows "
                "QUARANTINED (INVALID state) and is NOT intraday data"
            ),
            granularity="required: 15-minute OHLC bars",
            expected_limitations=(
                "instrument identity must be pinned precisely: spot "
                "XAU/USD vs COMEX futures vs ETFs are NOT "
                "interchangeable",
                "tick size / contract specifications / trading hours / "
                "quote currency must be documented from provider "
                "evidence",
                "volume availability varies (spot OTC has no central "
                "volume)",
            ),
            revision_behavior=(
                "UNKNOWN — no candidate provider selected"
            ),
            corporate_action_behavior=(
                "futures roll/expiration handling required if futures "
                "are chosen (contango/roll calendar from provider "
                "evidence only)"
            ),
            provenance_mechanism=(
                "NONE — no provider validated; quarantined rows can "
                "only be corrected from ORIGINAL provider evidence "
                "(never guessed)"
            ),
            notes=(
                "BLOCKED MARKET — metals paper execution stays blocked "
                "until a genuine 15m source is proposed, vetted and "
                "HUMAN-APPROVED.",
            ),
        )

    if source_name == "exness-mt5-demo":
        return DataSourceRecord(
            source_name="exness-mt5-demo",
            source_type="broker-terminal",
            license_basis=(
                "UNKNOWN — Exness client agreement / market-data terms "
                "have NOT been reviewed or confirmed by the operator; "
                "DEMO-account data-use conditions UNVERIFIED"
            ),
            coverage=(
                "Requires a Windows host running the MetaTrader 5 "
                "terminal with a POSITIVELY VERIFIED Exness DEMO "
                "account; instrument coverage (forex, metals, indices, "
                "stock CFDs) is whatever the connected terminal "
                "OBSERVES — NONE VALIDATED yet; forex ~24/5 with "
                "weekend gaps"
            ),
            granularity=(
                "M1/M5/M15/M30/H1/H4/D1/W1/MN1 OHLC bars + raw ticks, "
                "as offered by the terminal (timeframe constants are "
                "resolved from the installed MetaTrader5 module, never "
                "hardcoded)"
            ),
            expected_limitations=(
                "Windows-only: the official MetaTrader5 Python package "
                "requires the terminal running locally; availability "
                "ends when the terminal closes",
                "bar/tick timestamps are broker-server epoch values — "
                "session/timezone semantics require operator "
                "validation before any freshness claim",
                "markets closed at weekends trip the staleness "
                "threshold by design (raise or flag policy — never a "
                "silent acceptance)",
                "symbol names and contract specifications differ per "
                "Exness account family — the mapping is OBSERVED, "
                "digest-stamped and re-verified at every connect, "
                "never assumed",
                "no SLA — terminal/booking-server behaviour can change "
                "without notice",
                "READ-ONLY: the feed has no order path and the terminal "
                "allowlist makes every trade function unreachable",
            ),
            revision_behavior=(
                "MT5 history can be adjusted by the broker (rare, "
                "unannounced); the symbol-map digest re-check detects "
                "specification drift and refuses the feed until the "
                "operator re-validates — revision policy otherwise "
                "UNVERIFIED"
            ),
            corporate_action_behavior=(
                "CFD index membership and broker symbol changes are "
                "broker-side events; no synthetic adjustment is "
                "performed — specification drift is refused via the "
                "digest re-check"
            ),
            provenance_mechanism=(
                "per-batch provenance model: venue server, terminal "
                "name/build, broker company, verified environment "
                "(DEMO), row counts, first/last timestamps, staleness "
                "age and payload SHA-256, retrieval timestamp; symbol "
                "map entries carry SHA-256 digests of OBSERVED "
                "specifications"
            ),
            notes=(
                "CANDIDATE ONLY — zero terminal observations exist yet "
                "(no Windows host has run the probe); this record "
                "grants NOTHING.",
                "REQUIRED FOR APPROVAL: (1) genuine Exness DEMO "
                "terminal session on the operator's Windows host; "
                "(2) mt5-probe self-test evidence (connect + positive "
                "DEMO verification + catalogue + bars + ticks); "
                "(3) validated symbol map with observed digests; "
                "(4) freshness observations; (5) operator review of "
                "Exness terms — then a recorded SRC-APPROVAL decision "
                "(see docs/OPERATOR_SOURCE_APPROVAL_PACK.md).",
                "BLOCKED MARKETS (forex-15m-ohlc / metals-15m / "
                "stocks-15m) stay BLOCKED until this candidate is "
                "HUMAN-APPROVED and real coverage is verified — "
                "registering the candidate does NOT unblock them.",
            ),
        )

    raise KeyError(
        f"unknown candidate source {source_name!r} (declared: "
        f"{sorted(CANDIDATE_SOURCES)})"
    )


#: All declared candidate source names.
CANDIDATE_SOURCES = (
    "binance-public-spot",
    "exness-mt5-demo",
    "forex-15m-ohlc",
    "stocks-15m",
    "metals-15m",
)

#: Markets with NO validated genuine 15-minute source (honest blockers).
BLOCKED_MARKETS = (
    "forex-15m-ohlc",
    "stocks-15m",
    "metals-15m",
)


def build_feed_source_registry() -> DataSourceRegistry:
    """Build the governed registry holding every candidate UNVETTED.

    The registry starts EMPTY of approvals by construction: every
    record is registered UNVETTED and no approval is ever submitted
    here. The operator's human SRC-APPROVAL decision is recorded
    separately through the registry's ``submit_approval`` API on the
    paper-session host (see docs/OPERATOR_SOURCE_APPROVAL_PACK.md).
    """
    registry = DataSourceRegistry()
    for name in CANDIDATE_SOURCES:
        registry.register(candidate_record(name))
    return registry
