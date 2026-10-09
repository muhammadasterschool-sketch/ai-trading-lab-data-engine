"""Platform package tests — instrument registry (Phase E)."""

from datetime import UTC, datetime, timedelta

import pytest

from data_engine.platform import (
    AuditLog,
    Capability,
    EligibilityStatus,
    InstrumentRecord,
    InstrumentRegistry,
    OperatorApprovalRecord,
    ProviderSymbolMapping,
    canonical_instrument_id,
)
from data_engine.prediction.datasets import DatasetState
from data_engine.schemas import AssetClass, Instrument

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
T1 = T0 + timedelta(minutes=1)


def gold() -> Instrument:
    return Instrument(
        symbol="XAU/USD", asset_class=AssetClass.METAL, base_asset="XAU", quote_asset="USD"
    )


def btc() -> Instrument:
    return Instrument(
        symbol="BTC/USD", asset_class=AssetClass.CRYPTO, base_asset="BTC", quote_asset="USD"
    )


class TestCanonicalId:
    def test_deterministic_across_processes(self):
        assert canonical_instrument_id(gold()) == canonical_instrument_id(gold())

    def test_distinguishes_different_instruments(self):
        assert canonical_instrument_id(gold()) != canonical_instrument_id(btc())

    def test_distinguishes_venue(self):
        a = gold().model_copy(update={"venue": "OTC"})
        b = gold().model_copy(update={"venue": "exchange"})
        assert canonical_instrument_id(a) != canonical_instrument_id(b)


class TestRegistration:
    def test_register_creates_record_with_unknown_eligibility(self):
        reg = InstrumentRegistry()
        res = reg.register(gold(), "csv:metals_daily", T0)
        assert res.duplicate is False
        rec = res.record
        assert rec.data_state is None
        assert rec.eligibility(Capability.RESEARCH) is EligibilityStatus.DISCOVERED
        assert rec.eligibility(Capability.PAPER_TRADING) is EligibilityStatus.DISCOVERED

    def test_duplicate_registration_flags_and_merges_provider_symbols(self):
        reg = InstrumentRegistry()
        reg.register(gold(), "csv:metals_daily", T0)
        res2 = reg.register(
            gold(),
            "mt5:BrokerX",
            T1,
            provider_symbols=(ProviderSymbolMapping(provider="mt5:BrokerX", provider_symbol="XAUUSD"),),
        )
        assert res2.duplicate is True
        assert len(reg) == 1
        assert any(m.provider == "mt5:BrokerX" for m in res2.record.provider_symbols)

    def test_different_instruments_never_merged(self):
        reg = InstrumentRegistry()
        reg.register(gold(), "csv:metals_daily", T0)
        reg.register(btc(), "csv:crypto_daily", T0)
        assert len(reg) == 2

    def test_registration_requires_provenance_source(self):
        reg = InstrumentRegistry()
        with pytest.raises(ValueError, match="discovery_source"):
            reg.register(gold(), "", T0)

    def test_record_is_immutable(self):
        rec = InstrumentRecord(
            internal_id=canonical_instrument_id(gold()),
            instrument=gold(),
            discovery_source="csv:metals_daily",
            first_discovered=T0,
        )
        with pytest.raises(Exception):
            rec.monitoring = True  # type: ignore[misc]


class TestDataState:
    def test_real_verified_requires_evidence(self):
        reg = InstrumentRegistry()
        reg.register(gold(), "csv:metals_daily", T0)
        iid = canonical_instrument_id(gold())
        with pytest.raises(ValueError, match="REAL_VERIFIED promotion requires"):
            reg.set_data_state(iid, DatasetState.REAL_VERIFIED, T1)

    def test_real_verified_with_evidence_unlocks_paper_path(self):
        reg = InstrumentRegistry()
        reg.register(gold(), "csv:metals_daily", T0)
        iid = canonical_instrument_id(gold())
        rec = reg.set_data_state(
            iid, DatasetState.REAL_VERIFIED, T1, coverage_years=19.8, verified=True
        )
        assert rec.coverage_years == pytest.approx(19.8)
        # strategy eligibility is still required for paper trading
        assert rec.eligibility(Capability.PAPER_TRADING) is EligibilityStatus.BLOCKED
        rec = reg.set_eligibility(iid, True, T1)
        assert rec.eligibility(Capability.PAPER_TRADING) is EligibilityStatus.ELIGIBLE

    def test_real_unverified_allows_research_but_not_paper(self):
        reg = InstrumentRegistry()
        reg.register(gold(), "csv:metals_daily", T0)
        iid = canonical_instrument_id(gold())
        rec = reg.set_data_state(iid, DatasetState.REAL_UNVERIFIED, T1)
        assert rec.eligibility(Capability.RESEARCH) is EligibilityStatus.ELIGIBLE
        assert rec.eligibility(Capability.PAPER_TRADING) is EligibilityStatus.BLOCKED

    def test_synthetic_blocks_research_eligibility(self):
        reg = InstrumentRegistry()
        reg.register(gold(), "csv:metals_daily", T0)
        iid = canonical_instrument_id(gold())
        rec = reg.set_data_state(iid, DatasetState.SYNTHETIC, T1)
        assert rec.eligibility(Capability.BACKTESTING) is EligibilityStatus.BLOCKED


class TestLivePolicy:
    def test_live_trading_always_not_authorized(self):
        reg = InstrumentRegistry()
        reg.register(gold(), "csv:metals_daily", T0)
        iid = canonical_instrument_id(gold())
        rec = reg.set_data_state(
            iid, DatasetState.REAL_VERIFIED, T1, coverage_years=20.0, verified=True
        )
        assert rec.eligibility(Capability.LIVE_TRADING) is EligibilityStatus.NOT_AUTHORIZED

    def test_operator_approval_cannot_activate_live(self):
        reg = InstrumentRegistry(audit_log=AuditLog())
        reg.register(gold(), "csv:metals_daily", T0)
        iid = canonical_instrument_id(gold())
        approval = OperatorApprovalRecord(
            actor="operator",
            approved_at=T1,
            scope="live:gold",
            signature="sig-123",
        )
        rec = reg.authorize_live(iid, approval)
        assert rec.eligibility(Capability.LIVE_TRADING) is EligibilityStatus.NOT_AUTHORIZED


class TestVerificationAndQueries:
    def test_provider_verification_updates_mappings(self):
        reg = InstrumentRegistry()
        reg.register(
            gold(),
            "mt5:BrokerX",
            T0,
            provider_symbols=(
                ProviderSymbolMapping(provider="mt5:BrokerX", provider_symbol="XAUUSD"),
                ProviderSymbolMapping(provider="tradingview", provider_symbol="OANDA:XAUUSD"),
            ),
        )
        iid = canonical_instrument_id(gold())
        rec = reg.record_verification(
            iid, "mt5:BrokerX", T1, verified_symbols=("XAUUSD",)
        )
        mt5_map = [m for m in rec.provider_symbols if m.provider == "mt5:BrokerX"]
        tv_map = [m for m in rec.provider_symbols if m.provider == "tradingview"]
        assert mt5_map[0].verified is True and mt5_map[0].last_verified == T1
        assert tv_map[0].verified is False

    def test_monitoring_toggle(self):
        reg = InstrumentRegistry()
        reg.register(gold(), "csv:metals_daily", T0)
        iid = canonical_instrument_id(gold())
        rec = reg.set_monitoring(iid, True, T1)
        assert rec.eligibility(Capability.MONITORING) is EligibilityStatus.ELIGIBLE

    def test_find_by_symbol_and_provider_symbol(self):
        reg = InstrumentRegistry()
        reg.register(
            gold(),
            "mt5:BrokerX",
            T0,
            provider_symbols=(ProviderSymbolMapping(provider="mt5:BrokerX", provider_symbol="XAUUSD"),),
        )
        assert len(reg.find_by_symbol("XAU/USD")) == 1
        assert len(reg.find_by_symbol("EUR/USD")) == 0
        assert len(reg.find_by_provider_symbol("mt5:BrokerX", "XAUUSD")) == 1
        assert len(reg.find_by_provider_symbol("mt5:Other", "XAUUSD")) == 0

    def test_unknown_id_raises(self):
        reg = InstrumentRegistry()
        with pytest.raises(KeyError):
            reg.get("nope")

    def test_audit_events_recorded(self):
        log = AuditLog()
        reg = InstrumentRegistry(audit_log=log)
        reg.register(gold(), "csv:metals_daily", T0)
        assert len(log) == 1
        assert log.events()[0].component == "registry"
        assert log.events()[0].event == "instrument_registered"


class TestCrossProcessDeterminism:
    def test_id_is_subprocess_stable(self):
        import subprocess
        import sys

        code = (
            "from data_engine.platform import canonical_instrument_id;"
            "from data_engine.schemas import Instrument, AssetClass;"
            "print(canonical_instrument_id(Instrument(symbol='XAU/USD',"
            "asset_class=AssetClass.METAL, base_asset='XAU', quote_asset='USD')))"
        )
        out1 = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        ).stdout.strip()
        out2 = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True
        ).stdout.strip()
        assert out1 == out2 == canonical_instrument_id(gold())
