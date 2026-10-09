"""Real-time Web News Intelligence core (platform mandate Phase H).

The offline-buildable core of the news subsystem: immutable news items
with STRICT publication-vs-retrieval timestamp separation, content-hash
deduplication, entity-to-instrument resolution with ambiguous-match
flagging, an economic-calendar model that never invents missing values,
pluggable analysis, and a PIT availability boundary for backtests.

Security posture: all external content is UNTRUSTED DATA. NewsItem is a
pure data record — headlines/summaries are stored and classified by
explicit code paths only; they are never executed, never treated as
instructions, never able to touch credentials, risk limits, orders or
authorization. Real source connections (APIs/RSS) are BLOCKED on
operator credentials — nothing here claims live news coverage.
"""

import hashlib
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

from data_engine.platform.registry import InstrumentRegistry


class NewsCategory(str, Enum):
    EARNINGS = "earnings"
    MONETARY_POLICY = "monetary_policy"
    MACRO = "macro"
    GEOPOLITICAL = "geopolitical"
    REGULATORY = "regulatory"
    COMPANY = "company"
    MARKET_DISRUPTION = "market_disruption"
    OTHER = "other"


class Sentiment(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    UNKNOWN = "unknown"


class ImpactEstimate(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class VerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    INDEPENDENTLY_CORROBORATED = "independently_corroborated"
    FLAGGED_UNRELIABLE = "flagged_unreliable"
    STALE = "stale"


def news_id(headline: str, source: str, published_at: datetime, url: str) -> str:
    """Deterministic content identity (dedup key) — INV-01 discipline."""
    payload = "|".join((headline.strip(), source.strip(), published_at.isoformat(), url.strip()))
    return "NWS-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class NewsItem(BaseModel):
    """One immutable news record."""

    model_config = ConfigDict(frozen=True)

    news_id: str
    headline: str = Field(..., min_length=1)
    source: str = Field(..., min_length=1)
    url: str
    published_at: datetime
    retrieved_at: datetime
    affected_instruments: tuple[str, ...] = ()
    category: NewsCategory = NewsCategory.OTHER
    sentiment: Sentiment = Sentiment.UNKNOWN
    impact_estimate: ImpactEstimate = ImpactEstimate.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    verification: VerificationStatus = VerificationStatus.UNVERIFIED
    alert_status: str = "none"
    analysis_version: str = "rule-based-v1"
    audit_reference: Optional[str] = None
    summary: Optional[str] = None

    @model_validator(mode="after")
    def _retrieval_not_before_publication(self) -> "NewsItem":
        if self.retrieved_at < self.published_at:
            raise ValueError(
                f"retrieved_at ({self.retrieved_at}) precedes publication "
                f"time ({self.published_at}) — retrieval cannot precede "
                f"publication"
            )
        return self

    def visible_at(self, t: datetime) -> bool:
        """PIT boundary: the item is consumable only at/after publication."""
        return t >= self.published_at


class EconomicEvent(BaseModel):
    """Scheduled economic event. Missing values stay None — NEVER invented."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    name: str
    region: str
    scheduled_at: datetime
    timezone: str = "UTC"
    previous_value: Optional[float] = None
    consensus_forecast: Optional[float] = None
    actual_result: Optional[float] = None
    affected_instruments: tuple[str, ...] = ()
    category: NewsCategory = NewsCategory.MACRO

    @property
    def surprise(self) -> Optional[float]:
        """Surprise only when BOTH consensus and actual are available."""
        if self.consensus_forecast is None or self.actual_result is None:
            return None
        return self.actual_result - self.consensus_forecast

    def is_scheduled(self) -> bool:
        return True  # structurally a scheduled event, distinct from breaking news


class EntityResolution(BaseModel):
    """Result of mapping a text mention to registry instruments."""

    model_config = ConfigDict(frozen=True)

    mention: str
    resolved_instrument_ids: tuple[str, ...] = ()
    ambiguous: bool = False
    reason: str = ""


class NewsIntelligenceService:
    """Registry of news items + economic calendar + entity resolution."""

    def __init__(
        self,
        registry: Optional[InstrumentRegistry] = None,
        audit_log: Optional[object] = None,
        stale_after: timedelta = timedelta(hours=48),
    ) -> None:
        self._items: dict[str, NewsItem] = {}
        self._calendar: dict[str, EconomicEvent] = {}
        self._registry = registry
        self._audit = audit_log
        self._stale_after = stale_after
        self._duplicate_count = 0

    # -- ingestion ------------------------------------------------------
    def register(
        self,
        headline: str,
        source: str,
        url: str,
        published_at: datetime,
        retrieved_at: datetime,
        **kwargs,
    ) -> tuple[NewsItem, bool]:
        """Register a news item. Returns (item, duplicate). Duplicates are
        counted and refused — never re-added (syndication detection)."""
        nid = news_id(headline, source, published_at, url)
        if nid in self._items:
            self._duplicate_count += 1
            return self._items[nid], True
        item = NewsItem(
            news_id=nid,
            headline=headline,
            source=source,
            url=url,
            published_at=published_at,
            retrieved_at=retrieved_at,
            **kwargs,
        )
        self._items[nid] = item
        self._event(
            retrieved_at, "news_registered", f"{source}: {headline[:80]}", nid
        )
        return item, False

    def mark_stale(self, as_of: datetime) -> tuple[NewsItem, ...]:
        """Mark items older than the staleness window."""
        updated = []
        for nid, item in self._items.items():
            age = as_of - item.published_at
            if age > self._stale_after and item.verification is not VerificationStatus.STALE:
                refreshed = item.model_copy(update={"verification": VerificationStatus.STALE})
                self._items[nid] = refreshed
                updated.append(refreshed)
        if updated:
            self._event(as_of, "news_staleness", f"{len(updated)} items marked stale", "")
        return tuple(updated)

    # -- entity resolution --------------------------------------------------
    def resolve_entity(self, mention: str) -> EntityResolution:
        """Resolve a symbol/name mention against the instrument registry.
        Ambiguous matches are FLAGGED for review — never auto-assigned."""
        if self._registry is None:
            return EntityResolution(mention=mention, reason="no registry configured")
        mention_clean = mention.strip().upper()
        by_symbol = self._registry.find_by_symbol(mention_clean)
        if len(by_symbol) == 1:
            return EntityResolution(
                mention=mention,
                resolved_instrument_ids=(by_symbol[0].internal_id,),
                reason="unique canonical symbol match",
            )
        if len(by_symbol) > 1:
            return EntityResolution(
                mention=mention,
                resolved_instrument_ids=tuple(r.internal_id for r in by_symbol),
                ambiguous=True,
                reason=f"{len(by_symbol)} canonical symbol collisions — human review required",
            )
        provider_hits = self._registry.find_by_any_provider_symbol(mention_clean)
        if len(provider_hits) == 1:
            return EntityResolution(
                mention=mention,
                resolved_instrument_ids=(provider_hits[0].internal_id,),
                reason="unique provider symbol match",
            )
        if len(provider_hits) > 1:
            return EntityResolution(
                mention=mention,
                resolved_instrument_ids=tuple(r.internal_id for r in provider_hits),
                ambiguous=True,
                reason=f"{len(provider_hits)} provider symbol collisions — human review required",
            )
        return EntityResolution(mention=mention, reason="no match")

    # -- economic calendar -----------------------------------------------------
    def add_economic_event(self, event: EconomicEvent) -> EconomicEvent:
        if event.event_id in self._calendar:
            raise ValueError(f"duplicate economic event {event.event_id!r}")
        self._calendar[event.event_id] = event
        self._event(
            event.scheduled_at, "economic_event_registered", event.name, event.event_id
        )
        return event

    def economic_events(self) -> tuple[EconomicEvent, ...]:
        return tuple(self._calendar.values())

    def events_in_window(
        self, start: datetime, end: datetime
    ) -> tuple[EconomicEvent, ...]:
        return tuple(
            e for e in self._calendar.values() if start <= e.scheduled_at <= end
        )

    # -- PIT queries ---------------------------------------------------------
    def items_visible_at(self, t: datetime) -> tuple[NewsItem, ...]:
        """News consumable by a backtest decision at time t (no look-ahead)."""
        return tuple(i for i in self._items.values() if i.visible_at(t))

    def items_for_instrument(self, internal_id: str) -> tuple[NewsItem, ...]:
        return tuple(i for i in self._items.values() if internal_id in i.affected_instruments)

    def all_items(self) -> tuple[NewsItem, ...]:
        return tuple(self._items.values())

    @property
    def duplicate_count(self) -> int:
        return self._duplicate_count

    def __len__(self) -> int:
        return len(self._items)

    # -- internals -------------------------------------------------------------
    def _event(self, at: datetime, event: str, detail: str, ref: str) -> None:
        if self._audit is None:
            return
        self._audit.record(at, "news", event, detail, ref)
