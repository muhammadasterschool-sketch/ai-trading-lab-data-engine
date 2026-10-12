"""Broker instrument discovery, catalog and platform-registry sync
(Batch 7 — the instrument half of the multi-broker mandate).

Three pieces, all fail-closed:

1. **Discovery** (:func:`discover_instruments`) walks a CONNECTED
   adapter's ``list_symbols`` / ``instrument_spec`` surface into an
   immutable :class:`InstrumentCatalog`. Discovery from a
   DISCONNECTED adapter is refused (a fabricated catalog is worse
   than none); a spec whose ``broker_id`` does not match the adapter
   refuses (foreign specs never enter the catalog); duplicate venue
   symbols refuse; and the adapter's LIVE capability descriptor is
   cross-checked against the :class:`CapabilityRegistry` when one is
   supplied — drift between what an adapter serves and what was
   registered for its broker id refuses (capability changes are
   explicit versioned events, never silent).

2. **Catalog** (:class:`InstrumentCatalog`, :class:`CatalogEntry`) —
   the immutable snapshot of one venue's served instruments, each
   entry carrying the venue's capability descriptor AT DISCOVERY
   TIME (provenance: what could this venue do when we looked), the
   discovered-at timestamp and the discovery broker id. Lookups are
   fail-closed on unknown symbols.

3. **Registry sync** (:func:`sync_catalog_to_platform_registry`) —
   registers every catalog entry into the CENTRAL platform
   :class:`~data_engine.platform.registry.InstrumentRegistry` as a
   canonical identity with a ``broker:<id>`` provider-symbol
   mapping. The sync honors the registry's own contracts verbatim:

   - registration ≠ eligibility — a synced instrument lands
     DISCOVERED (nothing is tradable until explicitly verified; the
     sync NEVER touches data state, verification or eligibility);
   - the SAME canonical instrument discovered at a second venue is
     the registry's flagged-duplicate path — the provider mapping is
     MERGED into the existing record (one canonical identity, many
     venue symbols — never two records);
   - broker provider mappings start UNVERIFIED (verification is the
     registry's own explicit evidence-driven action).

PAPER/TEST ONLY: the shipped mock adapters are deterministic and
credential-free; syncing a catalog grants NO trading permission of
any kind. LIVE TRADING REMAINS NOT AUTHORIZED.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from data_engine.brokers.capabilities import (
    BrokerCapabilities,
    CapabilityRegistry,
)
from data_engine.brokers.errors import (
    BrokerErrorCategory,
    BrokerExecutionError,
)
from data_engine.brokers.interface import BrokerAdapter
from data_engine.brokers.models import (
    ConnectionState,
    InstrumentSpec,
)
from data_engine.platform.registry import (
    InstrumentRegistry,
    ProviderSymbolMapping,
)

__all__ = [
    "CatalogEntry",
    "InstrumentCatalog",
    "RegistrySyncReport",
    "discover_instruments",
    "sync_catalog_to_platform_registry",
]


class CatalogEntry(BaseModel):
    """One discovered instrument with its discovery provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    spec: InstrumentSpec
    #: The venue's capability descriptor SNAPSHOT at discovery time.
    capabilities: BrokerCapabilities
    discovered_at: datetime = Field(
        ...,
        description="Discovery wall-clock (audit provenance; never an "
                    "identity input — INV-01).",
    )
    discovery_broker_id: str


class InstrumentCatalog:
    """Immutable catalog of ONE venue's served instruments."""

    def __init__(self, entries: tuple) -> None:
        if not isinstance(entries, tuple):
            raise BrokerExecutionError(
                "catalog entries must be an immutable tuple",
                category=BrokerErrorCategory.INTERNAL,
                broker_id="catalog",
            )
        seen: set = set()
        for entry in entries:
            if not isinstance(entry, CatalogEntry):
                raise BrokerExecutionError(
                    "catalog entries must be CatalogEntry records",
                    category=BrokerErrorCategory.INTERNAL,
                    broker_id="catalog",
                )
            if entry.spec.symbol in seen:
                raise BrokerExecutionError(
                    f"duplicate catalog symbol {entry.spec.symbol!r}",
                    category=BrokerErrorCategory.INTERNAL,
                    broker_id=entry.discovery_broker_id,
                )
            seen.add(entry.spec.symbol)
        self._entries: tuple = entries
        self._by_symbol = {e.spec.symbol: e for e in entries}

    @property
    def entries(self) -> tuple:
        return self._entries

    @property
    def broker_id(self) -> str:
        if not self._entries:
            raise BrokerExecutionError(
                "empty catalog has no broker id",
                category=BrokerErrorCategory.INTERNAL,
                broker_id="catalog",
            )
        return self._entries[0].discovery_broker_id

    def symbols(self) -> tuple:
        return tuple(sorted(self._by_symbol))

    def entry(self, symbol: str) -> CatalogEntry:
        found = self._by_symbol.get(symbol)
        if found is None:
            raise BrokerExecutionError(
                f"symbol {symbol!r} is not in this catalog (served: "
                + ", ".join(sorted(self._by_symbol)) + ")",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self.broker_id if self._entries else "catalog",
            )
        return found

    def __len__(self) -> int:
        return len(self._entries)

    def __iter__(self):
        return iter(self._entries)


def discover_instruments(
    adapter: BrokerAdapter,
    *,
    at: datetime,
    registry: Optional[CapabilityRegistry] = None,
) -> InstrumentCatalog:
    """Discover ONE venue's served instruments into a catalog.

    Fail-closed contract:

    - ``adapter`` must be a connected :class:`BrokerAdapter`
      (discovery from a disconnected venue fabricates a catalog);
    - the adapter's capability descriptor is cross-checked against
      ``registry`` when supplied: drift (adapter serves a descriptor
      differing from the registered one) refuses — capability
      changes are explicit versioned events;
    - every served spec must belong to THIS broker (foreign specs
      refuse) and duplicate venue symbols refuse;
    - ``at`` is the discovery timestamp (audit provenance only — it
      never participates in any identity hash, INV-01).
    """
    if not isinstance(adapter, BrokerAdapter):
        raise BrokerExecutionError(
            "discovery requires a BrokerAdapter",
            category=BrokerErrorCategory.INTERNAL,
            broker_id="discovery",
        )
    broker_id = adapter.broker_id
    if adapter.health() is not ConnectionState.CONNECTED:
        raise BrokerExecutionError(
            f"instrument discovery refused: {broker_id} is not CONNECTED "
            "(a catalog fabricated from a disconnected venue is worse "
            "than none — fail closed)",
            category=BrokerErrorCategory.CONNECTIVITY,
            broker_id=broker_id,
        )
    descriptor = adapter.capabilities
    if registry is not None:
        if not registry.has(broker_id):
            raise BrokerExecutionError(
                f"instrument discovery refused: broker {broker_id!r} is "
                "not registered in the capability registry — refusing to "
                "catalog an unknown venue (fail closed)",
                category=BrokerErrorCategory.INTERNAL,
                broker_id=broker_id,
            )
        registered = registry.get(broker_id)
        if registered != descriptor:
            raise BrokerExecutionError(
                f"instrument discovery refused: capability DRIFT — "
                f"{broker_id!r} serves a descriptor that differs from the "
                "registered one (capability changes are explicit "
                "versioned events, never silent)",
                category=BrokerErrorCategory.INTERNAL,
                broker_id=broker_id,
            )
    symbols = adapter.list_symbols()
    if len(set(symbols)) != len(symbols):
        raise BrokerExecutionError(
            f"instrument discovery refused: {broker_id} reports duplicate "
            "symbols — the venue surface is inconsistent (fail closed)",
            category=BrokerErrorCategory.INTERNAL,
            broker_id=broker_id,
        )
    entries: list = []
    for symbol in symbols:
        spec = adapter.instrument_spec(symbol)
        if not isinstance(spec, InstrumentSpec) or \
                spec.broker_id != broker_id:
            raise BrokerExecutionError(
                f"instrument discovery refused: symbol {symbol!r} at "
                f"{broker_id} returned a spec belonging to "
                f"{getattr(spec, 'broker_id', type(spec).__name__)!r} "
                "(foreign specs never enter a venue's catalog)",
                category=BrokerErrorCategory.INTERNAL,
                broker_id=broker_id,
            )
        entries.append(
            CatalogEntry(
                spec=spec,
                capabilities=descriptor,
                discovered_at=at,
                discovery_broker_id=broker_id,
            )
        )
    return InstrumentCatalog(tuple(entries))


class RegistrySyncReport(BaseModel):
    """Outcome of one catalog → platform-registry sync."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_id: str
    registered: int = 0
    duplicates: int = 0
    canonical_symbols: tuple = ()
    eligibility_granted: bool = Field(
        default=False,
        description="Always False — the sync NEVER grants eligibility "
                    "(registration ≠ eligibility; the registry's own "
                    "verification path is the only promotion surface).",
    )


def _canonical_instrument(spec: InstrumentSpec):
    """Canonical platform instrument for one broker spec.

    The canonical identity deliberately carries NO exchange/venue —
    the SAME asset pair discovered at different venues is ONE
    canonical instrument with MANY provider symbols (the registry's
    duplicate path merges the mappings; venues never fork identity).
    """
    from data_engine.schemas import AssetClass, ContractType, Instrument

    return Instrument(
        symbol=f"{spec.base_asset}/{spec.quote_asset}",
        asset_class=AssetClass.CRYPTO,
        base_asset=spec.base_asset,
        quote_asset=spec.quote_asset,
        venue=None,
        contract_type=ContractType.SPOT,
        currency=spec.quote_asset,
    )


def sync_catalog_to_platform_registry(
    catalog: InstrumentCatalog,
    registry: InstrumentRegistry,
    *,
    at: datetime,
    audit_timestamp: Optional[datetime] = None,
) -> RegistrySyncReport:
    """Register every catalog entry into the CENTRAL instrument
    registry with ``broker:<id>`` provider-symbol mappings.

    Honors the registry's own contracts verbatim: registration is
    DISTINCT from eligibility (the sync never touches data state,
    verification, monitoring or eligibility — a synced instrument
    lands DISCOVERED); the same canonical identity from another
    venue (or a re-sync) is the registry's flagged-duplicate path
    with the provider mapping MERGED; broker mappings start
    UNVERIFIED. Returns a report of what happened.
    """
    if not isinstance(catalog, InstrumentCatalog):
        raise BrokerExecutionError(
            "registry sync requires an InstrumentCatalog",
            category=BrokerErrorCategory.INTERNAL,
            broker_id="sync",
        )
    if registry is None:
        raise BrokerExecutionError(
            "registry sync requires the platform InstrumentRegistry",
            category=BrokerErrorCategory.INTERNAL,
            broker_id="sync",
        )
    provider = f"broker:{catalog.broker_id}"
    registered = 0
    duplicates = 0
    canonical: list = []
    for entry in catalog:
        spec = entry.spec
        mapping = ProviderSymbolMapping(
            provider=provider,
            provider_symbol=spec.broker_symbol,
            verified=False,
        )
        result = registry.register(
            _canonical_instrument(spec),
            discovery_source=provider,
            first_discovered=at,
            provider_symbols=(mapping,),
            audit_timestamp=audit_timestamp,
        )
        if result.duplicate:
            duplicates += 1
        else:
            registered += 1
        canonical.append(result.record.instrument.symbol)
    return RegistrySyncReport(
        broker_id=catalog.broker_id,
        registered=registered,
        duplicates=duplicates,
        canonical_symbols=tuple(sorted(set(canonical))),
        eligibility_granted=False,
    )
