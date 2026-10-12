"""Regression tests: operational-feed composition (Phase D integration).

These tests prove the REAL adapter integrates into the ACTUAL runtime
composition path — not a standalone diagnostic:

    provider (Binance adapter, offline sanitized fixtures)
      → fetch_feed_window (closed bars, no look-ahead)
      → resolve_canonical_instrument (registry-confirmed mapping)
      → evaluate_operational_feed (the 32nd gate checklist)
      → operational_feed_evidence (honest GateEvidence)
      → PaperReadinessGate.evaluate()
      → TradingRuntime.start() (REFUSED on FALSE — fail closed)

The source registry is exercised in BOTH honest states:

- UNVETTED source (the CURRENT repository truth): the composition
  produces passed=False evidence and the runtime REFUSES to start —
  exactly as the governance requires. Nothing here fabricates an
  approval.
- HUMAN-approved fixture source with production-ingestion scope:
  the composition CAN pass legitimately (proving the machinery works
  end-to-end) — the approval is an explicit TEST FIXTURE recorded
  through the registry's human-only API, never claimed as an operator
  decision.

Also covered: rate-series abuse is structurally refused, provider
outages fail closed, open/future bars are refused at composition,
stale/insufficient-warm-up feeds produce FALSE verdicts with reasons,
and an AI approval attempt is structurally rejected (cannot unlock
the gate).
"""

from datetime import datetime, timedelta, UTC
from pathlib import Path

import pytest

from data_engine.instruments import InstrumentRegistry
from data_engine.prediction.source_registry import (
    DataSourceRegistry,
    SourceVerificationStatus,
)
from data_engine.provider import MarketDataProvider
from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.feed_composition import (
    FeedCompositionError,
    build_paper_feed_evidence,
    evaluate_paper_feed,
    fetch_feed_window,
    operational_feed_evidence,
    resolve_canonical_instrument,
)
from data_engine.runtime.readiness import GATE_NAMES, GateEvidence, PaperReadinessGate
from data_engine.schemas import (
    AssetClass,
    Instrument,
    ProviderConfig,
    Timeframe,
)
from data_engine.providers.binance_public import (
    BinancePublicKlinesProvider,
    BinanceTransportError,
)
from data_engine.providers.rate_series import (
    ForexRateSeriesAdapter,
    RateSeriesError,
)
from data_engine.platform.feed_source_candidates import (
    BLOCKED_MARKETS,
    CANDIDATE_SOURCES,
    build_feed_source_registry,
    candidate_record,
)
from data_engine.providers.transport import TransportConnectError

# ── shared fixtures ────────────────────────────────────────────────

AS_OF = datetime(2026, 10, 11, 12, 0, 0, tzinfo=UTC)
INTERVAL_MS = 900_000
INTERVAL = timedelta(minutes=15)
WARMUP = 30
SYMBOL = "BTCUSDT"
CANONICAL = "BTC/USDT"
SOURCE_NAME = "binance-public-spot"


def _kline_row(open_ms, o=100.0, h=101.0, low=99.0, c=100.5, volume=12.5):
    return [
        open_ms, str(o), str(h), str(low), str(c), str(volume),
        open_ms + INTERVAL_MS - 1, "1234.5", 96, "6.2", "6.1", "0",
    ]


def _closed_rows(n, *, end_ms=None):
    if end_ms is None:
        end_ms = int(AS_OF.timestamp() * 1000)
    end_ms = (end_ms // INTERVAL_MS) * INTERVAL_MS
    first = end_ms - n * INTERVAL_MS
    return [_kline_row(first + i * INTERVAL_MS) for i in range(n)]


class FakeTransport:
    def __init__(self, pages, failures=None):
        self.pages = list(pages)
        self.failures = list(failures or [])
        self.calls = []
        self.sleeps = []
        self.timeout = 10.0

    def backoff_sleep(self, seconds):
        self.sleeps.append(seconds)

    def get(self, base_url, params):
        self.calls.append((base_url, dict(params)))
        if self.failures:
            raise self.failures.pop(0)
        return self.pages.pop(0) if self.pages else "[]"


def _provider(pages, failures=None, registry=None):
    import json

    transport = FakeTransport(
        [json.dumps(_closed_rows(WARMUP))] if isinstance(pages, int)
        else pages,
        failures=failures,
    )
    config = ProviderConfig(
        provider_name="binance-public-spot",
        provider_type="api",
        endpoint="https://api.binance.com/api/v3",
        rate_limit_per_minute=10_000,
    )
    kwargs = dict(transport=transport, as_of=AS_OF, max_attempts=1)
    if registry is not None:
        return BinancePublicKlinesProvider(config, registry, **kwargs), transport
    return BinancePublicKlinesProvider(config, **kwargs), transport


def _registry_with_instrument():
    registry = InstrumentRegistry()
    registry.register(Instrument(
        symbol=CANONICAL,
        asset_class=AssetClass.CRYPTO,
        base_asset="BTC",
        quote_asset="USDT",
        exchange="BINANCE",
        venue="BINANCE-SPOT",
        provider_symbol=SYMBOL,
    ))
    return registry


def _approved_registry():
    """Test FIXTURE: human approval recorded via the registry's
    human-only API (never claimed as an operator decision)."""
    registry = build_feed_source_registry()
    registry.submit_approval(
        SOURCE_NAME,
        approver="test-operator-fixture",
        approver_kind="human",
        target_status=SourceVerificationStatus.APPROVED_FOR_PRODUCTION,
        approved_usage_scopes=("production-ingestion",),
        recorded_at="2026-10-11T00:00:00+00:00",
    )
    return registry


# ════════════════════════════════════════════════════════════════════
# 1. Candidate declarations (Phase C) — all UNVETTED
# ════════════════════════════════════════════════════════════════════

class TestCandidates:
    def test_all_candidates_registered_unvetted(self):
        registry = build_feed_source_registry()
        for record in registry.list_records():
            assert record.verification_status is (
                SourceVerificationStatus.UNVETTED
            )
            assert record.approved_usage_scopes == ()

    def test_candidate_names_match_declared_set(self):
        registry = build_feed_source_registry()
        assert {r.source_name for r in registry.list_records()} == set(
            CANDIDATE_SOURCES
        )

    def test_blocked_markets_have_missing_dependency_records(self):
        for name in BLOCKED_MARKETS:
            record = candidate_record(name)
            assert "MISSING DEPENDENCY" in record.license_basis
            assert "NONE VALIDATED" in record.coverage
            assert any("BLOCKED MARKET" in n for n in record.notes)

    def test_binance_candidate_documents_terms_uncertainty(self):
        record = candidate_record("binance-public-spot")
        assert "UNKNOWN" in record.license_basis
        assert "BTCUSDT" in record.coverage  # narrow pilot scope pinned
        assert "UNMEASURED" in record.coverage  # stability honestly unproven

    def test_no_credentials_in_any_candidate_record(self):
        for name in CANDIDATE_SOURCES:
            blob = candidate_record(name).model_dump_json().lower()
            for forbidden in ("api_key", "apikey", "token", "secret",
                              "password"):
                assert forbidden not in blob, (name, forbidden)


# ════════════════════════════════════════════════════════════════════
# 2. fetch_feed_window (closed bars, no look-ahead)
# ════════════════════════════════════════════════════════════════════

class TestFetchWindow:
    def test_closed_window_fetched(self):
        provider, _ = _provider(WARMUP)
        bars = fetch_feed_window(
            provider, instrument=SYMBOL, timeframe=Timeframe.M15,
 interval=INTERVAL,
            as_of=AS_OF, required_warmup_bars=WARMUP,
        )
        assert len(bars) == WARMUP
        assert bars[-1].timestamp < AS_OF

    @staticmethod
    def _stub_provider(bar_timestamp):
        """A genuine MarketDataProvider stub that bypasses the real
        adapter's validation — used to prove the composition layer's
        own look-ahead defences are independent."""
        from data_engine.schemas import Candle

        config = ProviderConfig(
            provider_name="stub-lookahead", provider_type="api"
        )

        class _StubProvider(MarketDataProvider):
            def fetch_candles(self, instrument, timeframe, start, end):
                return [
                    Candle(
                        timestamp=bar_timestamp,
                        open=100.0, high=101.0, low=99.0, close=100.5,
                        volume=1.0, timeframe=Timeframe.M15,
 interval=INTERVAL,
                    )
                ]

            def fetch_instrument_info(self, symbol):
                return None

            def check_connectivity(self):
                return True

        return _StubProvider(config)

    def test_open_bar_refused_at_composition(self):
        # A bar still OPEN by grid math at the session reference
        # (opens 11:55, grid-close 12:10 > as_of 12:00) — the
        # composition must refuse it independently of the adapter.
        stub = self._stub_provider(AS_OF - timedelta(minutes=5))
        with pytest.raises(FeedCompositionError, match="look-ahead"):
            fetch_feed_window(
                stub, instrument=SYMBOL,
                timeframe=Timeframe.M15, interval=INTERVAL,
                as_of=AS_OF,
                required_warmup_bars=WARMUP,
            )

    def test_future_dated_bar_refused_at_composition(self):
        stub = self._stub_provider(AS_OF + timedelta(minutes=1))
        with pytest.raises(FeedCompositionError, match="future-dated"):
            fetch_feed_window(
                stub, instrument=SYMBOL,
                timeframe=Timeframe.M15, interval=INTERVAL,
                as_of=AS_OF,
                required_warmup_bars=WARMUP,
            )

    def test_provider_outage_fails_closed(self):
        provider, _ = _provider(
            [], failures=[TransportConnectError("u", RuntimeError("dns"))]
        )
        with pytest.raises(BinanceTransportError):
            fetch_feed_window(
                provider, instrument=SYMBOL, timeframe=Timeframe.M15,
 interval=INTERVAL,
                as_of=AS_OF, required_warmup_bars=WARMUP,
            )

    def test_naive_as_of_refused(self):
        provider, _ = _provider(WARMUP)
        with pytest.raises(FeedCompositionError, match="timezone-aware"):
            fetch_feed_window(
                provider, instrument=SYMBOL, timeframe=Timeframe.M15,
 interval=INTERVAL,
                as_of=datetime(2026, 10, 11, 12, 0),  # naive
                required_warmup_bars=WARMUP,
            )

    def test_zero_warmup_refused(self):
        provider, _ = _provider(WARMUP)
        with pytest.raises(FeedCompositionError, match="warm"):
            fetch_feed_window(
                provider, instrument=SYMBOL, timeframe=Timeframe.M15,
 interval=INTERVAL,
                as_of=AS_OF, required_warmup_bars=0,
            )

    def test_rate_series_cannot_enter_candle_composition(self):
        class _Reader:
            def read_text(self):
                return (
                    "Currency_Pair,Date,Exchange_Rate\n"
                    "USD/PKR,2026-01-02,278.5\n"
                )

        rate_series = ForexRateSeriesAdapter(reader=_Reader())
        with pytest.raises(FeedCompositionError, match="candle provider"):
            fetch_feed_window(
                rate_series, instrument="USD/PKR",
                timeframe=Timeframe.M15, interval=INTERVAL,
                as_of=AS_OF,
                required_warmup_bars=WARMUP,
            )

    def test_rate_series_fetch_candles_always_refused(self):
        class _Reader:
            def read_text(self):
                return (
                    "Currency_Pair,Date,Exchange_Rate\n"
                    "USD/PKR,2026-01-02,278.5\n"
                )

        adapter = ForexRateSeriesAdapter(reader=_Reader())
        with pytest.raises(RateSeriesError, match="FORBIDDEN"):
            adapter.fetch_candles("USD/PKR")


# ════════════════════════════════════════════════════════════════════
# 3. Canonical instrument mapping
# ════════════════════════════════════════════════════════════════════

class TestMapping:
    def test_registry_confirmed_mapping(self):
        registry = _registry_with_instrument()
        provider, _ = _provider(WARMUP, registry=registry)
        canonical, confirmed = resolve_canonical_instrument(
            provider, instrument=SYMBOL
        )
        assert canonical == CANONICAL
        assert confirmed is True

    def test_unregistered_mapping_fails_closed_in_gate(self):
        provider, _ = _provider(WARMUP)  # empty instrument registry
        canonical, confirmed = resolve_canonical_instrument(
            provider, instrument=SYMBOL
        )
        assert canonical == CANONICAL
        assert confirmed is False

    def test_no_instrument_info_refused(self):
        provider, _ = _provider(WARMUP)

        class _NoneInfo:
            config = provider.config

            def fetch_instrument_info(self, symbol):
                return None

        with pytest.raises(FeedCompositionError, match="no instrument"):
            resolve_canonical_instrument(
                _NoneInfo(), instrument=SYMBOL
            )


# ════════════════════════════════════════════════════════════════════
# 4. Full composition verdicts (fail-closed matrix)
# ════════════════════════════════════════════════════════════════════

class TestCompositionVerdicts:
    def _evaluate(self, *, registry, provider=None, warmup=WARMUP,
                  instrument_registry=None):
        if provider is None:
            provider, _ = _provider(
                WARMUP, registry=instrument_registry
                or _registry_with_instrument()
            )
        return evaluate_paper_feed(
            provider,
            source_registry=registry,
            source_name=SOURCE_NAME,
            instrument=SYMBOL,
            timeframe=Timeframe.M15,
            interval=INTERVAL,
            as_of=AS_OF,
            required_warmup_bars=warmup,
        )

    def test_unvetted_source_fails_with_reasons(self):
        report, bars, canonical, confirmed = self._evaluate(
            registry=build_feed_source_registry()
        )
        assert report.passed is False
        assert report.bar_count == WARMUP
        assert canonical == CANONICAL and confirmed is True
        assert any("UNVETTED" in r for r in report.reasons)
        assert any("production-ingestion" in r for r in report.reasons)

    def test_approved_fixture_source_passes(self):
        report, _bars, _canonical, _confirmed = self._evaluate(
            registry=_approved_registry()
        )
        assert report.passed is True, list(report.reasons)
        assert report.source_status == "APPROVED_FOR_PRODUCTION"

    def test_ai_approval_cannot_unlock(self):
        registry = build_feed_source_registry()
        decision = registry.submit_approval(
            SOURCE_NAME,
            approver="agent",
            approver_kind="ai",
            target_status=(
                SourceVerificationStatus.APPROVED_FOR_PRODUCTION
            ),
            approved_usage_scopes=("production-ingestion",),
        )
        assert decision.accepted is False
        report, _bars, _c, _f = self._evaluate(registry=registry)
        assert report.passed is False

    def test_unregistered_instrument_fails(self):
        report, _bars, _canonical, confirmed = self._evaluate(
            registry=_approved_registry(),
            instrument_registry=InstrumentRegistry(),
        )
        assert report.passed is False
        assert confirmed is False
        assert any("unconfirmed" in r.lower() for r in report.reasons)

    def test_insufficient_warmup_fails(self):
        report, _bars, _c, _f = self._evaluate(
            registry=_approved_registry(), warmup=WARMUP + 10
        )
        assert report.passed is False
        assert any("warm-up" in r for r in report.reasons)

    def test_stale_feed_fails(self):
        stale_as_of = AS_OF + timedelta(hours=2)
        provider, _ = _provider(WARMUP, registry=_registry_with_instrument())
        report, _bars, _c, _f = evaluate_paper_feed(
            provider,
            source_registry=_approved_registry(),
            source_name=SOURCE_NAME,
            instrument=SYMBOL,
            timeframe=Timeframe.M15,
            interval=INTERVAL,
            as_of=stale_as_of,
            required_warmup_bars=WARMUP,
        )
        assert report.passed is False
        assert any("STALE" in r for r in report.reasons)

    def test_gap_rejection_fails(self):
        import json

        rows = _closed_rows(WARMUP + 2)
        del rows[10]  # one-interval gap inside the window
        provider, _ = _provider(
            [json.dumps(rows)], registry=_registry_with_instrument()
        )
        report, _bars, _c, _f = evaluate_paper_feed(
            provider,
            source_registry=_approved_registry(),
            source_name=SOURCE_NAME,
            instrument=SYMBOL,
            timeframe=Timeframe.M15,
            interval=INTERVAL,
            as_of=AS_OF,
            required_warmup_bars=WARMUP,
        )
        assert report.passed is False
        assert any("gap" in r for r in report.reasons)

    def test_wrong_symbol_mapping_fails(self):
        # ETHUSDT is outside the pilot allowlist — composition cannot
        # even fetch it (fail closed before evaluation).
        provider, _ = _provider(WARMUP, registry=_registry_with_instrument())
        with pytest.raises(Exception, match="allowlist"):
            evaluate_paper_feed(
                provider,
                source_registry=_approved_registry(),
                source_name=SOURCE_NAME,
                instrument="ETHUSDT",
                timeframe=Timeframe.M15,
                interval=INTERVAL,
                as_of=AS_OF,
                required_warmup_bars=WARMUP,
            )


# ════════════════════════════════════════════════════════════════════
# 5. Evidence shape (honest, never forced)
# ════════════════════════════════════════════════════════════════════

class TestEvidence:
    def test_false_verdict_yields_false_evidence(self):
        provider, _ = _provider(WARMUP, registry=_registry_with_instrument())
        evidence, report, bars = build_paper_feed_evidence(
            provider,
            source_registry=build_feed_source_registry(),
            source_name=SOURCE_NAME,
            instrument=SYMBOL,
            timeframe=Timeframe.M15,
            interval=INTERVAL,
            as_of=AS_OF,
            required_warmup_bars=WARMUP,
        )
        assert evidence.gate == "OPERATIONAL_FEED_READY"
        assert evidence.passed is False
        assert report.passed is False
        assert len(bars) == WARMUP
        assert "UNVETTED" in evidence.evidence

    def test_true_verdict_yields_true_evidence(self):
        provider, _ = _provider(WARMUP, registry=_registry_with_instrument())
        evidence, report, _bars = build_paper_feed_evidence(
            provider,
            source_registry=_approved_registry(),
            source_name=SOURCE_NAME,
            instrument=SYMBOL,
            timeframe=Timeframe.M15,
            interval=INTERVAL,
            as_of=AS_OF,
            required_warmup_bars=WARMUP,
        )
        assert evidence.passed is True
        assert report.passed is True
        assert "verdict=PASS" in evidence.evidence


# ════════════════════════════════════════════════════════════════════
# 6. RUNTIME end-to-end: the composition feeds the authoritative gate
# ════════════════════════════════════════════════════════════════════

class TestRuntimeIntegration:
    @staticmethod
    def _gate_with_feed_evidence(feed_evidence):
        """All 32 gates carry objective evidence EXCEPT the feed gate,
        which carries the composition's real verdict."""
        gate = PaperReadinessGate()
        for name in GATE_NAMES:
            if name == "OPERATIONAL_FEED_READY":
                gate.submit(feed_evidence)
                continue
            gate.submit(GateEvidence(
                gate=name,
                component=f"component:{name.lower()}",
                check="evidence_submitted",
                evidence="objective evidence on record",
                passed=True,
            ))
        return gate

    def test_unvetted_source_refuses_runtime_start(self, tmp_path):
        from data_engine.runtime import ExecutionStateStore, TradingRuntime
        from test_runtime_recovery_integration import _op_config
        from test_runtime_e2e import _fit_world

        provider, _ = _provider(WARMUP, registry=_registry_with_instrument())
        evidence, report, _bars = build_paper_feed_evidence(
            provider,
            source_registry=build_feed_source_registry(),
            source_name=SOURCE_NAME,
            instrument=SYMBOL,
            timeframe=Timeframe.M15,
            interval=INTERVAL,
            as_of=AS_OF,
            required_warmup_bars=WARMUP,
        )
        assert report.passed is False  # the honest current truth

        ens, cal = _fit_world()
        rt = TradingRuntime(
            _op_config("feed-comp-unvetted"), ens, calibrator=cal,
            state_store=ExecutionStateStore(Path(tmp_path) / "store"),
            readiness_gate=self._gate_with_feed_evidence(evidence),
        )
        with pytest.raises(RuntimeContractError,
                           match="OPERATIONAL_FEED_READY"):
            rt.start()

    def test_approved_fixture_source_starts_runtime(self, tmp_path):
        from data_engine.runtime import ExecutionStateStore, TradingRuntime
        from test_runtime_recovery_integration import _op_config
        from test_runtime_e2e import _fit_world

        provider, _ = _provider(WARMUP, registry=_registry_with_instrument())
        evidence, report, _bars = build_paper_feed_evidence(
            provider,
            source_registry=_approved_registry(),
            source_name=SOURCE_NAME,
            instrument=SYMBOL,
            timeframe=Timeframe.M15,
            interval=INTERVAL,
            as_of=AS_OF,
            required_warmup_bars=WARMUP,
        )
        assert report.passed is True

        ens, cal = _fit_world()
        rt = TradingRuntime(
            _op_config("feed-comp-approved"), ens, calibrator=cal,
            state_store=ExecutionStateStore(Path(tmp_path) / "store"),
            readiness_gate=self._gate_with_feed_evidence(evidence),
        )
        rt.start()
        assert rt.ledgers.verify()

    def test_evidence_text_is_diagnostic_not_just_boolean(self, tmp_path):
        provider, _ = _provider(WARMUP, registry=_registry_with_instrument())
        evidence, _report, _bars = build_paper_feed_evidence(
            provider,
            source_registry=build_feed_source_registry(),
            source_name=SOURCE_NAME,
            instrument=SYMBOL,
            timeframe=Timeframe.M15,
            interval=INTERVAL,
            as_of=AS_OF,
            required_warmup_bars=WARMUP,
        )
        # The evidence must carry the failure reasons verbatim — a
        # readiness reviewer sees WHY, not just that, it failed.
        for fragment in ("UNVETTED", "production-ingestion",
                         "binance-public-spot", "BTCUSDT", "15m"):
            assert fragment in evidence.evidence
