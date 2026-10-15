"""Deterministic broker catalog + capability-matrix artifacts (Batch 15).

Batch 11 §9 recorded two missing GENERATED artifacts over the governed
broker layer:

- a **broker capability matrix** — the
  :class:`~data_engine.brokers.capabilities.CapabilityRegistry` holds
  the descriptors, but no rendered matrix artifact existed;
- an **instrument catalog report** — discovery/sync
  (:mod:`data_engine.brokers.instruments`) hold the venue catalogs and
  platform-registry state, but no rendered catalog artifact existed.

This module closes both gaps with DETERMINISTIC builders and renderers:
the same registry + catalogs + fixed discovery timestamp always render
BYTE-IDENTICAL markdown (sorted order everywhere; no wall-clock, no
RNG, no process-dependent state — the discovery timestamp is an
explicit input used as audit provenance only, never as identity).

What the artifacts honestly document:

- every registered venue's capability descriptor (order kinds, TIFs,
  SL/TP semantics, position mode, idempotency mechanism, reduce-only,
  account modes, rate-limit shape, reconciliation style, execution
  mode — with MOCK_DETERMINISTIC enforced and REAL refused);
- every venue's served instruments (canonical symbol, venue symbol,
  filters, reference price);
- the platform-registry state after sync: canonical identities, venue
  symbol mappings (UNVERIFIED), duplicate merges, and the honest
  per-capability eligibility statuses (registration is DISTINCT from
  eligibility; LIVE TRADING is NOT AUTHORIZED);
- the unsupported order kinds per venue (what the session refuses
  BEFORE the venue is reached) and the fail-closed discovery behaviors
  (all covered by existing tests — nothing new is claimed).

PAPER/TEST ONLY. NO network, NO credentials, NO real orders, NO real
broker connectivity is claimed or implied by these artifacts.
LIVE TRADING IS NOT AUTHORIZED.
"""

from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.brokers.capabilities import CapabilityRegistry
from data_engine.brokers.models import OrderKind
from data_engine.brokers.instruments import InstrumentCatalog
from data_engine.platform.registry import (
    Capability as PlatformCapability,
    InstrumentRegistry,
)

__all__ = [
    "CapabilityMatrixRow",
    "CapabilityMatrixReport",
    "CatalogInstrumentRow",
    "CatalogVenueSection",
    "CanonicalMappingRow",
    "CanonicalRecordRow",
    "CatalogReport",
    "build_capability_matrix",
    "render_capability_matrix_markdown",
    "build_catalog_report",
    "render_catalog_report_markdown",
]


# ---------------------------------------------------------------------------
# Capability matrix (Batch 15, item C-3)
# ---------------------------------------------------------------------------

class CapabilityMatrixRow(BaseModel):
    """One venue's rendered capability matrix row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_id: str
    display_name: str
    execution_mode: str
    order_kinds: Tuple[str, ...]
    time_in_force: Tuple[str, ...]
    sl_tp: str
    position_mode: str
    idempotency_key: str
    supports_reduce_only: bool
    account_modes: Tuple[str, ...]
    max_orders_per_window: int
    max_requests_per_window: int
    window_seconds: float
    reconciliation_style: str
    provides_market_data: bool
    venue_notes: str


class CapabilityMatrixReport(BaseModel):
    """Rendered capability matrix over a whole registry."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    venue_count: int
    rows: Tuple[CapabilityMatrixRow, ...]
    live_trading_authorized: bool = False

    def validate_semantics(self) -> None:
        """Cross-check the honest invariants the matrix asserts."""
        if self.live_trading_authorized:
            raise ValueError("LIVE TRADING IS NOT AUTHORIZED — the matrix "
                             "cannot render an authorized-live state")
        for row in self.rows:
            if row.execution_mode != "MOCK_DETERMINISTIC":
                raise ValueError(
                    f"venue {row.broker_id!r} is not MOCK_DETERMINISTIC — "
                    "REAL execution modes are refused in this phase"
                )


def build_capability_matrix(
    registry: CapabilityRegistry,
) -> CapabilityMatrixReport:
    """Build the capability matrix from a registry (sorted by broker id)."""
    rows = tuple(
        CapabilityMatrixRow(
            broker_id=d.broker_id,
            display_name=d.display_name,
            execution_mode=d.execution_mode.value,
            order_kinds=tuple(k.value for k in d.order_kinds),
            time_in_force=tuple(t.value for t in d.time_in_force),
            sl_tp=d.sl_tp.value,
            position_mode=d.position_mode.value,
            idempotency_key=d.idempotency_key.value,
            supports_reduce_only=d.supports_reduce_only,
            account_modes=tuple(m.value for m in d.account_modes),
            max_orders_per_window=d.rate_limit.max_orders_per_window,
            max_requests_per_window=d.rate_limit.max_requests_per_window,
            window_seconds=d.rate_limit.window_seconds,
            reconciliation_style=d.reconciliation_style.value,
            provides_market_data=d.provides_market_data,
            venue_notes=" ".join(d.venue_notes.split()),
        )
        for d in registry.descriptors()  # sorted by broker_id
    )
    report = CapabilityMatrixReport(venue_count=len(rows), rows=rows)
    report.validate_semantics()
    return report


def render_capability_matrix_markdown(report: CapabilityMatrixReport) -> str:
    """Render the capability matrix as deterministic markdown."""
    lines: list = []
    lines.append("# BROKER CAPABILITY MATRIX (GENERATED ARTIFACT)")
    lines.append("")
    lines.append(
        "> GENERATED, DETERMINISTIC artifact — rendered by "
        "`data_engine.brokers.catalog_report.build_capability_matrix` over the "
        "governed `CapabilityRegistry` (see "
        "`scripts/generate_broker_catalog_artifacts.py`; tests byte-compare "
        "regeneration). NO real broker connectivity exists or is claimed: "
        "every venue below is a MOCK_DETERMINISTIC in-memory adapter; REAL "
        "execution-mode descriptors are refused at registration and by the "
        "session. **LIVE TRADING IS NOT AUTHORIZED.**"
    )
    lines.append("")
    lines.append(f"Registered venues: **{report.venue_count}**")
    lines.append("")
    lines.append(
        "| Broker ID | Display name | Execution mode | Order kinds | TIF | "
        "SL/TP | Position mode | Idempotency key | Reduce-only | "
        "Account modes | Rate limit (orders/requests per window s) | "
        "Reconciliation | Market data |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for row in report.rows:
        rate = (
            f"{row.max_orders_per_window}/{row.max_requests_per_window} "
            f"per {row.window_seconds:g}s"
        )
        lines.append(
            f"| `{row.broker_id}` | {row.display_name} | {row.execution_mode} | "
            f"{', '.join(row.order_kinds)} | {', '.join(row.time_in_force)} | "
            f"{row.sl_tp} | {row.position_mode} | {row.idempotency_key} | "
            f"{'yes' if row.supports_reduce_only else 'no'} | "
            f"{', '.join(row.account_modes)} | {rate} | "
            f"{row.reconciliation_style} | "
            f"{'yes' if row.provides_market_data else 'no'} |"
        )
    lines.append("")
    lines.append("## Venue notes (per-venue audit narrative)")
    lines.append("")
    for row in report.rows:
        lines.append(f"### `{row.broker_id}` — {row.display_name}")
        lines.append("")
        lines.append(row.venue_notes)
        lines.append("")
    lines.append("## Unsupported order kinds per venue (session refuses BEFORE the venue)")
    lines.append("")
    lines.append(
        "Unsupported requests fail closed at the session boundary — the "
        "venue never sees them (`session.py` pre-venue capability checks; "
        "covered by `tests/test_broker_session_guards.py`)."
    )
    lines.append("")
    all_kinds = tuple(k.value for k in OrderKind)
    lines.append("| Broker ID | Unsupported order kinds |")
    lines.append("|---|---|")
    for row in report.rows:
        unsupported = tuple(
            k for k in all_kinds if k not in row.order_kinds
        )
        lines.append(
            f"| `{row.broker_id}` | "
            + (", ".join(unsupported) if unsupported else "(none — all kinds)")
            + " |"
        )
    lines.append("")
    lines.append(
        "PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY. "
        "LIVE TRADING NOT AUTHORIZED."
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Instrument catalog report (Batch 15, item C-2)
# ---------------------------------------------------------------------------

class CatalogInstrumentRow(BaseModel):
    """One served instrument at one venue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    broker_symbol: str
    base_asset: str
    quote_asset: str
    tick_size: str
    lot_step: str
    min_quantity: str
    max_quantity: str
    min_notional: str
    reference_price: str


class CatalogVenueSection(BaseModel):
    """One venue's catalog section."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_id: str
    display_name: str
    execution_mode: str
    discovered_at: str
    instrument_count: int
    instruments: Tuple[CatalogInstrumentRow, ...]


class CanonicalMappingRow(BaseModel):
    """One venue mapping on one canonical platform identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    provider_symbol: str
    verified: bool


class CanonicalRecordRow(BaseModel):
    """One canonical platform-registry record as rendered."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    canonical_symbol: str
    asset_class: str
    contract_type: str
    currency: str
    internal_id: str
    first_discovered_from: str
    provider_mappings: Tuple[CanonicalMappingRow, ...]
    data_state: Optional[str]
    monitoring: str
    paper_trading: str
    live_trading: str


class CatalogReport(BaseModel):
    """Rendered instrument-catalog + platform-registry state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    discovered_at: str
    venue_count: int
    venues: Tuple[CatalogVenueSection, ...]
    canonical_count: int
    canonical_records: Tuple[CanonicalRecordRow, ...]
    eligibility_granted: bool = False
    known_limitations: Tuple[str, ...] = ()

    def validate_semantics(self) -> None:
        if self.eligibility_granted:
            raise ValueError("the catalog report NEVER grants eligibility "
                             "(registration is DISTINCT from eligibility)")
        for record in self.canonical_records:
            if record.live_trading != "Not Authorized":
                raise ValueError("LIVE TRADING IS NOT AUTHORIZED — the "
                                 "catalog cannot render an authorized-live "
                                 "record")


def build_catalog_report(
    catalogs: Tuple[InstrumentCatalog, ...],
    platform_registry: InstrumentRegistry,
    *,
    at,
) -> CatalogReport:
    """Build the catalog report from discovered catalogs + the synced
    platform registry (all ordering deterministic: venues by broker id,
    instruments by symbol, canonical records by canonical symbol)."""
    sections: list = []
    for catalog in sorted(catalogs, key=lambda c: c.broker_id):
        entries = sorted(catalog.entries, key=lambda e: e.spec.symbol)
        capabilities = entries[0].capabilities
        sections.append(
            CatalogVenueSection(
                broker_id=catalog.broker_id,
                display_name=capabilities.display_name,
                execution_mode=capabilities.execution_mode.value,
                discovered_at=at.isoformat(),
                instrument_count=len(entries),
                instruments=tuple(
                    CatalogInstrumentRow(
                        symbol=e.spec.symbol,
                        broker_symbol=e.spec.broker_symbol,
                        base_asset=e.spec.base_asset,
                        quote_asset=e.spec.quote_asset,
                        tick_size=str(e.spec.tick_size),
                        lot_step=str(e.spec.lot_step),
                        min_quantity=str(e.spec.min_quantity),
                        max_quantity=str(e.spec.max_quantity),
                        min_notional=str(e.spec.min_notional),
                        reference_price=str(e.spec.reference_price),
                    )
                    for e in entries
                ),
            )
        )

    records: list = []
    for record in sorted(
        platform_registry.all_records(),
        key=lambda r: r.instrument.symbol,
    ):
        records.append(
            CanonicalRecordRow(
                canonical_symbol=record.instrument.symbol,
                asset_class=record.instrument.asset_class.value,
                contract_type=record.instrument.contract_type.value,
                currency=record.instrument.currency,
                internal_id=record.internal_id,
                first_discovered_from=record.discovery_source,
                provider_mappings=tuple(
                    CanonicalMappingRow(
                        provider=m.provider,
                        provider_symbol=m.provider_symbol,
                        verified=m.verified,
                    )
                    for m in sorted(
                        record.provider_symbols,
                        key=lambda m: (m.provider, m.provider_symbol),
                    )
                ),
                data_state=(
                    record.data_state.value
                    if record.data_state is not None else None
                ),
                monitoring=record.eligibility(PlatformCapability.MONITORING).value,
                paper_trading=record.eligibility(PlatformCapability.PAPER_TRADING).value,
                live_trading=record.eligibility(PlatformCapability.LIVE_TRADING).value,
            )
        )

    report = CatalogReport(
        discovered_at=at.isoformat(),
        venue_count=len(sections),
        venues=tuple(sections),
        canonical_count=len(records),
        canonical_records=tuple(records),
        eligibility_granted=False,
        known_limitations=(
            "Canonical platform identity is currently modeled uniformly as "
            "CRYPTO/SPOT by the broker-catalog sync (brokers/instruments.py "
            "_canonical_instrument) — FX and metals canonical records "
            "(EUR/USD, XAU/USD, BTC/USD from the MT5-class venues) inherit "
            "that simplification. Canonical identity and venue mappings are "
            "correct; the asset-class label is a documented modeling "
            "simplification, not a connectivity claim.",
            "All venue mappings are UNVERIFIED by construction — provider "
            "verification is the platform registry's explicit evidence-"
            "driven action, never granted by discovery or by this report.",
        ),
    )
    report.validate_semantics()
    return report


def render_catalog_report_markdown(report: CatalogReport) -> str:
    """Render the catalog report as deterministic markdown."""
    lines: list = []
    lines.append("# INSTRUMENT CATALOG REPORT (GENERATED ARTIFACT)")
    lines.append("")
    lines.append(
        "> GENERATED, DETERMINISTIC artifact — rendered by "
        "`data_engine.brokers.catalog_report.build_catalog_report` from the "
        "discovered venue catalogs (fail-closed discovery) and the synced "
        "platform `InstrumentRegistry` (see "
        "`scripts/generate_broker_catalog_artifacts.py`; tests byte-compare "
        "regeneration). Discovery timestamp (audit provenance ONLY — never "
        "an identity input, INV-01): "
        f"`{report.discovered_at}`. NO real broker connectivity exists or "
        "is claimed; every venue is a MOCK_DETERMINISTIC in-memory adapter. "
        "**LIVE TRADING IS NOT AUTHORIZED.**"
    )
    lines.append("")
    lines.append(
        f"Venues cataloged: **{report.venue_count}** · canonical platform "
        f"identities: **{report.canonical_count}** · eligibility granted by "
        "this report: **NONE** (registration is DISTINCT from eligibility)."
    )
    lines.append("")
    lines.append("## 1. Venue catalogs (served instruments)")
    lines.append("")
    for section in report.venues:
        lines.append(
            f"### `{section.broker_id}` — {section.display_name}"
        )
        lines.append("")
        lines.append(
            f"Execution mode: {section.execution_mode} · instruments: "
            f"{section.instrument_count} · discovered at "
            f"`{section.discovered_at}`"
        )
        lines.append("")
        lines.append(
            "| Symbol | Venue symbol | Base | Quote | Tick size | Lot step | "
            "Min qty | Max qty | Min notional | Reference price |"
        )
        lines.append("|---|---|---|---|---|---|---|---|---|---|")
        for row in section.instruments:
            lines.append(
                f"| `{row.symbol}` | `{row.broker_symbol}` | {row.base_asset} | "
                f"{row.quote_asset} | {row.tick_size} | {row.lot_step} | "
                f"{row.min_quantity} | {row.max_quantity} | {row.min_notional} | "
                f"{row.reference_price} |"
            )
        lines.append("")
    lines.append("## 2. Platform-registry canonical state (after sync)")
    lines.append("")
    lines.append(
        "The SAME canonical identity discovered at multiple venues is ONE "
        "record with MANY venue mappings (duplicate-merge; identity is "
        "never forked). All broker mappings start UNVERIFIED."
    )
    lines.append("")
    lines.append(
        "| Canonical symbol | Asset class | Contract | Currency | "
        "Internal ID | First discovered from | Venue mappings | "
        "Data state | Monitoring | Paper trading | Live trading |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for record in report.canonical_records:
        mappings = "; ".join(
            f"`{m.provider}`→`{m.provider_symbol}`"
            + (" (verified)" if m.verified else " (UNVERIFIED)")
            for m in record.provider_mappings
        )
        lines.append(
            f"| `{record.canonical_symbol}` | {record.asset_class} | "
            f"{record.contract_type} | {record.currency} | `{record.internal_id}` | "
            f"`{record.first_discovered_from}` | {mappings} | "
            f"{record.data_state or 'none'} | {record.monitoring} | "
            f"{record.paper_trading} | {record.live_trading} |"
        )
    lines.append("")
    lines.append("## 3. Fail-closed discovery behaviors (tested, referenced)")
    lines.append("")
    lines.append(
        "- Discovery from a DISCONNECTED adapter is REFUSED (a fabricated "
        "catalog is worse than none). — `tests/test_broker_instrument_discovery.py`"
    )
    lines.append(
        "- Foreign specs (broker_id mismatch) are REFUSED — a venue's "
        "catalog only contains its OWN instruments. — same suite"
    )
    lines.append(
        "- Duplicate venue symbols are REFUSED — the venue surface must be "
        "consistent. — same suite"
    )
    lines.append(
        "- Capability DRIFT (adapter serves a descriptor differing from the "
        "registered one) is REFUSED — capability changes are explicit "
        "versioned events. — same suite"
    )
    lines.append(
        "- Unregistered venues are REFUSED at discovery (fail closed — "
        "refusing to assume capabilities). — same suite"
    )
    lines.append(
        "- Precision/lot-step/minimum violations are DEFINITIVE rejections "
        "carrying venue-native codes (e.g. MT5 retcode 10014) BEFORE any "
        "execution. — `tests/test_broker_adapter_contract.py`"
    )
    lines.append(
        "- Unknown symbols fail closed on lookup (INVALID_ORDER-category "
        "error, never a guessed spec). — same suite"
    )
    lines.append("")
    lines.append("## 4. Known limitations (documented honestly)")
    lines.append("")
    for limitation in report.known_limitations:
        lines.append(f"- {limitation}")
    lines.append("")
    lines.append(
        "PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY. "
        "LIVE TRADING NOT AUTHORIZED."
    )
    lines.append("")
    return "\n".join(lines)
