"""Platform package tests — news intelligence core (Phase H)."""

from datetime import UTC, datetime, timedelta

import pytest

from data_engine.platform import (
    InstrumentRegistry,
    NewsCategory,
    NewsIntelligenceService,
    ProviderSymbolMapping,
    Sentiment,
)
from data_engine.platform.news import EconomicEvent, VerificationStatus
from data_engine.schemas import AssetClass, Instrument

T0 = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)


@pytest.fixture()
def registry():
    reg = InstrumentRegistry()
    gold = Instrument(
        symbol="XAU/USD", asset_class=AssetClass.METAL, base_asset="XAU", quote_asset="USD"
    )
    reg.register(
        gold,
        "csv:metals_daily",
        T0,
        provider_symbols=(ProviderSymbolMapping(provider="mt5:BrokerX", provider_symbol="XAUUSD"),),
    )
    # a deliberately colliding second instrument sharing the provider symbol
    gold2 = Instrument(
        symbol="XAUUSD.c", asset_class=AssetClass.COMMODITY, base_asset="XAU", quote_asset="USD"
    )
    reg.register(
        gold2,
        "mt5:BrokerX",
        T0,
        provider_symbols=(ProviderSymbolMapping(provider="mt5:BrokerX", provider_symbol="XAUUSD"),),
    )
    return reg


class TestRegistrationAndDedup:
    def test_register_returns_item_and_no_duplicate(self):
        svc = NewsIntelligenceService()
        item, dup = svc.register(
            headline="Fed holds rates",
            source="reuters",
            url="https://e.com/1",
            published_at=T0 - timedelta(hours=1),
            retrieved_at=T0,
        )
        assert dup is False and len(svc) == 1
        assert item.news_id.startswith("NWS-")

    def test_exact_duplicate_refused_and_counted(self):
        svc = NewsIntelligenceService()
        args = dict(
            headline="Fed holds rates",
            source="reuters",
            url="https://e.com/1",
            published_at=T0 - timedelta(hours=1),
            retrieved_at=T0,
        )
        svc.register(**args)
        _, dup = svc.register(**args)
        assert dup is True
        assert len(svc) == 1 and svc.duplicate_count == 1

    def test_syndicated_copy_same_story_different_source_is_distinct(self):
        svc = NewsIntelligenceService()
        svc.register(
            headline="Fed holds rates",
            source="reuters",
            url="https://e.com/1",
            published_at=T0 - timedelta(hours=1),
            retrieved_at=T0,
        )
        _, dup = svc.register(
            headline="Fed holds rates",
            source="bloomberg",
            url="https://e.com/2",
            published_at=T0 - timedelta(hours=1),
            retrieved_at=T0,
        )
        # same headline from another outlet is a distinct record (source is part of identity)
        assert dup is False and len(svc) == 2

    def test_retrieval_before_publication_refused(self):
        svc = NewsIntelligenceService()
        with pytest.raises(ValueError, match="precedes publication"):
            svc.register(
                headline="x",
                source="s",
                url="https://e.com/3",
                published_at=T0,
                retrieved_at=T0 - timedelta(minutes=1),
            )


class TestPitVisibility:
    def test_visible_at_boundary_is_inclusive(self):
        svc = NewsIntelligenceService()
        published = T0 - timedelta(hours=2)
        svc.register(
            headline="h", source="s", url="https://e.com/4",
            published_at=published, retrieved_at=T0,
        )
        assert svc.items_visible_at(published)
        assert not svc.items_visible_at(published - timedelta(seconds=1))

    def test_backtest_cannot_see_future_news(self):
        svc = NewsIntelligenceService()
        svc.register(
            headline="future", source="s", url="https://e.com/5",
            published_at=T0 + timedelta(days=1), retrieved_at=T0 + timedelta(days=1),
        )
        assert svc.items_visible_at(T0) == ()


class TestStaleness:
    def test_old_news_marked_stale(self):
        svc = NewsIntelligenceService(stale_after=timedelta(hours=24))
        svc.register(
            headline="old", source="s", url="https://e.com/6",
            published_at=T0 - timedelta(hours=48), retrieved_at=T0 - timedelta(hours=47),
        )
        updated = svc.mark_stale(T0)
        assert len(updated) == 1
        assert updated[0].verification is VerificationStatus.STALE


class TestEntityResolution:
    def test_unique_canonical_symbol_resolves(self, registry):
        svc = NewsIntelligenceService(registry=registry)
        res = svc.resolve_entity("XAU/USD")
        assert not res.ambiguous and len(res.resolved_instrument_ids) == 1

    def test_ambiguous_provider_symbol_flagged_not_assigned(self, registry):
        svc = NewsIntelligenceService(registry=registry)
        res = svc.resolve_entity("XAUUSD")
        assert res.ambiguous and len(res.resolved_instrument_ids) == 2
        assert "human review" in res.reason

    def test_unknown_mention_resolves_to_nothing(self, registry):
        svc = NewsIntelligenceService(registry=registry)
        res = svc.resolve_entity("NOT-A-SYMBOL")
        assert res.resolved_instrument_ids == () and not res.ambiguous


class TestEconomicCalendar:
    def test_surprise_requires_both_consensus_and_actual(self):
        ev = EconomicEvent(
            event_id="EV-1", name="US CPI", region="US", scheduled_at=T0,
            previous_value=3.0, consensus_forecast=None, actual_result=3.2,
        )
        assert ev.surprise is None  # never invented
        ev2 = EconomicEvent(
            event_id="EV-2", name="US CPI", region="US", scheduled_at=T0,
            previous_value=3.0, consensus_forecast=3.1, actual_result=3.2,
        )
        assert ev2.surprise == pytest.approx(0.1)

    def test_duplicate_event_refused(self):
        svc = NewsIntelligenceService()
        ev = EconomicEvent(event_id="EV-1", name="CPI", region="US", scheduled_at=T0)
        svc.add_economic_event(ev)
        with pytest.raises(ValueError, match="duplicate economic event"):
            svc.add_economic_event(ev)

    def test_events_in_window(self):
        svc = NewsIntelligenceService()
        svc.add_economic_event(EconomicEvent(event_id="EV-1", name="A", region="US", scheduled_at=T0))
        svc.add_economic_event(EconomicEvent(event_id="EV-2", name="B", region="US", scheduled_at=T0 + timedelta(days=2)))
        window = svc.events_in_window(T0 - timedelta(hours=1), T0 + timedelta(hours=1))
        assert [e.event_id for e in window] == ["EV-1"]


class TestInstrumentQueries:
    def test_items_for_instrument(self):
        svc = NewsIntelligenceService()
        svc.register(
            headline="gold!", source="s", url="https://e.com/7",
            published_at=T0, retrieved_at=T0, affected_instruments=("iid-gold",),
            category=NewsCategory.COMMODITIES if hasattr(NewsCategory, "COMMODITIES") else NewsCategory.OTHER,
            sentiment=Sentiment.POSITIVE,
        )
        assert len(svc.items_for_instrument("iid-gold")) == 1
        assert svc.items_for_instrument("iid-other") == ()
