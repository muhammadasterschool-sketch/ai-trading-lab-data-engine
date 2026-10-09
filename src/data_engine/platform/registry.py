"""Central Instrument Registry (platform mandate Phase E).

Distinct from ``data_engine.discovery`` (which is STRATEGY discovery).
This registry is the authoritative in-process record of every discovered
instrument: canonical identity, provider-specific symbols, provenance,
verification timestamps, data state and per-capability eligibility.

Design contracts (fail-closed, INV-01 discipline):
- ``internal_id`` is a PURE FUNCTION of the canonical identity fields —
  no wall-clock, no discovery order — so two independent processes
  register the same instrument with the same id.
- Registration is DISTINCT from eligibility. A newly discovered
  instrument lands with every capability UNKNOWN; nothing is tradable
  until explicitly verified.
- Different canonical identities are NEVER merged; the same identity
  registered twice is a duplicate (flagged, not duplicated).
- ``REAL_VERIFIED`` data state can ONLY be set with explicit
  verification evidence (verified coverage computed from real
  observations) — the registry never promotes on its own.
- LIVE_TRADING eligibility requires a human ``OperatorApprovalRecord``
  that this module cannot fabricate; the default is NOT_AUTHORIZED.
"""

import hashlib
from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from data_engine.prediction.datasets import DatasetState
from data_engine.schemas import Instrument

_CAPABILITIES = ("monitoring", "research", "backtesting", "paper_trading", "live_trading")


class Capability(str, Enum):
    """Platform capabilities an instrument can be eligible for."""

    MONITORING = "monitoring"
    RESEARCH = "research"
    BACKTESTING = "backtesting"
    PAPER_TRADING = "paper_trading"
    LIVE_TRADING = "live_trading"


class EligibilityStatus(str, Enum):
    """Per-capability eligibility (dashboard status vocabulary)."""

    DISCOVERED = "Discovered"
    REGISTERED = "Registered"
    ELIGIBLE = "Eligible"
    BLOCKED = "Blocked"
    NOT_AUTHORIZED = "Not Authorized"
    UNKNOWN = "Unknown"


class OperatorApprovalRecord(BaseModel):
    """Human approval for a privileged eligibility transition.

    Can only be constructed with an explicit actor signature — the
    platform never generates one on its own.
    """

    model_config = ConfigDict(frozen=True)

    actor: str
    approved_at: datetime
    scope: str = Field(..., description="Exact approved scope (e.g. capability + version)")
    signature: str = Field(..., min_length=1, description="Human-provided signature token")


class ProviderSymbolMapping(BaseModel):
    """Broker/provider-specific symbol for one instrument."""

    model_config = ConfigDict(frozen=True)

    provider: str = Field(..., description="e.g. 'mt5:BrokerX', 'tradingview', 'csv:source'")
    provider_symbol: str
    verified: bool = False
    last_verified: Optional[datetime] = None


def canonical_instrument_id(instrument: Instrument) -> str:
    """Deterministic internal ID from canonical identity (INV-01)."""
    payload = "|".join(
        (
            instrument.symbol,
            instrument.asset_class.value,
            instrument.base_asset,
            instrument.quote_asset,
            instrument.exchange or "",
            instrument.venue or "",
            instrument.contract_type.value,
            instrument.currency,
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class InstrumentRecord(BaseModel):
    """Registry record for one instrument (immutable; updates create copies)."""

    model_config = ConfigDict(frozen=True)

    internal_id: str
    instrument: Instrument
    provider_symbols: tuple[ProviderSymbolMapping, ...] = ()
    discovery_source: str
    first_discovered: datetime
    last_verified: Optional[datetime] = None
    monitoring: bool = False
    data_state: Optional[DatasetState] = None
    coverage_years: float = 0.0
    supported_timeframes: tuple[str, ...] = ()
    strategy_eligible: bool = False
    notes: tuple[str, ...] = ()

    def eligibility(self, capability: Capability) -> EligibilityStatus:
        """Derive the per-capability status from record state (honest)."""
        if capability is Capability.LIVE_TRADING:
            # No live authorization surface exists; honest default.
            return EligibilityStatus.NOT_AUTHORIZED
        if capability is Capability.MONITORING:
            return (
                EligibilityStatus.ELIGIBLE
                if self.monitoring
                else EligibilityStatus.REGISTERED
            )
        if self.data_state is None:
            return EligibilityStatus.DISCOVERED
        if capability is Capability.BACKTESTING:
            ok = self.data_state in (DatasetState.REAL_VERIFIED, DatasetState.REAL_UNVERIFIED)
            return EligibilityStatus.ELIGIBLE if ok else EligibilityStatus.BLOCKED
        if capability is Capability.RESEARCH:
            ok = self.data_state in (DatasetState.REAL_VERIFIED, DatasetState.REAL_UNVERIFIED)
            return EligibilityStatus.ELIGIBLE if ok else EligibilityStatus.BLOCKED
        if capability is Capability.PAPER_TRADING:
            ok = (
                self.data_state is DatasetState.REAL_VERIFIED
                and self.strategy_eligible
            )
            return EligibilityStatus.ELIGIBLE if ok else EligibilityStatus.BLOCKED
        return EligibilityStatus.UNKNOWN


class RegistrationResult(BaseModel):
    """Outcome of a register() call (duplicate-flagged, never merged)."""

    model_config = ConfigDict(frozen=True)

    record: InstrumentRecord
    duplicate: bool


class InstrumentRegistry:
    """Mutable registry service over immutable records (fail-closed)."""

    def __init__(self, audit_log: Optional[object] = None) -> None:
        self._records: dict[str, InstrumentRecord] = {}
        self._audit = audit_log

    # -- registration ---------------------------------------------------
    def register(
        self,
        instrument: Instrument,
        discovery_source: str,
        first_discovered: datetime,
        provider_symbols: tuple[ProviderSymbolMapping, ...] = (),
        audit_timestamp: Optional[datetime] = None,
    ) -> RegistrationResult:
        if not discovery_source:
            raise ValueError("discovery_source is required (provenance)")
        iid = canonical_instrument_id(instrument)
        duplicate = iid in self._records
        if duplicate:
            existing = self._records[iid]
            self._event(
                audit_timestamp or first_discovered,
                "duplicate_registration",
                f"canonical identity already registered from "
                f"{existing.discovery_source!r}; new source {discovery_source!r} "
                f"recorded as provider mapping only",
                iid,
            )
            merged_symbols = {
                (m.provider, m.provider_symbol): m for m in existing.provider_symbols
            }
            for m in provider_symbols:
                merged_symbols.setdefault((m.provider, m.provider_symbol), m)
            record = existing.model_copy(
                update={"provider_symbols": tuple(merged_symbols.values())}
            )
            self._records[iid] = record
            return RegistrationResult(record=record, duplicate=True)
        record = InstrumentRecord(
            internal_id=iid,
            instrument=instrument,
            provider_symbols=provider_symbols,
            discovery_source=discovery_source,
            first_discovered=first_discovered,
        )
        self._records[iid] = record
        self._event(
            audit_timestamp or first_discovered,
            "instrument_registered",
            f"{instrument.symbol} from {discovery_source}",
            iid,
        )
        return RegistrationResult(record=record, duplicate=False)

    # -- verification / data state --------------------------------------
    def record_verification(
        self,
        internal_id: str,
        provider: str,
        verified_at: datetime,
        verified_symbols: tuple[str, ...] = (),
    ) -> InstrumentRecord:
        rec = self._get(internal_id)
        symbols = []
        for m in rec.provider_symbols:
            if m.provider == provider and m.provider_symbol in verified_symbols:
                symbols.append(
                    m.model_copy(update={"verified": True, "last_verified": verified_at})
                )
            else:
                symbols.append(m)
        updated = rec.model_copy(
            update={"provider_symbols": tuple(symbols), "last_verified": verified_at}
        )
        self._records[internal_id] = updated
        self._event(verified_at, "provider_verification", f"provider={provider}", internal_id)
        return updated

    def set_data_state(
        self,
        internal_id: str,
        state: DatasetState,
        at: datetime,
        coverage_years: float = 0.0,
        verified: bool = False,
    ) -> InstrumentRecord:
        """Set the dataset state; REAL_VERIFIED requires explicit verified=True
        evidence plus a positive observation-derived coverage figure."""
        rec = self._get(internal_id)
        if state is DatasetState.REAL_VERIFIED and not (verified and coverage_years > 0):
            raise ValueError(
                "REAL_VERIFIED promotion requires verified=True evidence and "
                "coverage_years > 0 computed from real observations — "
                "refusing to promote without evidence"
            )
        updated = rec.model_copy(
            update={"data_state": state, "coverage_years": coverage_years}
        )
        self._records[internal_id] = updated
        self._event(at, "data_state", f"{state.value} coverage={coverage_years}", internal_id)
        return updated

    # -- eligibility ------------------------------------------------------
    def set_eligibility(
        self,
        internal_id: str,
        strategy_eligible: bool,
        at: datetime,
    ) -> InstrumentRecord:
        rec = self._get(internal_id)
        updated = rec.model_copy(update={"strategy_eligible": strategy_eligible})
        self._records[internal_id] = updated
        self._event(at, "strategy_eligibility", f"eligible={strategy_eligible}", internal_id)
        return updated

    def set_monitoring(
        self, internal_id: str, monitoring: bool, at: datetime
    ) -> InstrumentRecord:
        rec = self._get(internal_id)
        updated = rec.model_copy(update={"monitoring": monitoring})
        self._records[internal_id] = updated
        self._event(at, "monitoring", f"monitoring={monitoring}", internal_id)
        return updated

    def authorize_live(
        self, internal_id: str, approval: OperatorApprovalRecord
    ) -> InstrumentRecord:
        """LIVE eligibility is refused: no live surface exists or is
        authorized in this repository. The refusal is recorded."""
        rec = self._get(internal_id)
        self._event(
            approval.approved_at,
            "live_authorization_refused",
            "repository policy: LIVE TRADING NOT AUTHORIZED — no live execution "
            "surface exists; operator approval cannot activate one from the "
            "platform package",
            internal_id,
        )
        return rec

    # -- queries -----------------------------------------------------------
    def get(self, internal_id: str) -> InstrumentRecord:
        return self._get(internal_id)

    def find_by_symbol(self, symbol: str) -> tuple[InstrumentRecord, ...]:
        return tuple(
            r for r in self._records.values() if r.instrument.symbol == symbol
        )

    def find_by_provider_symbol(self, provider: str, provider_symbol: str):
        hits = tuple(
            r
            for r in self._records.values()
            for m in r.provider_symbols
            if m.provider == provider and m.provider_symbol == provider_symbol
        )
        return hits

    def find_by_any_provider_symbol(self, provider_symbol: str):
        """Search provider symbol mappings across ALL providers.

        Used by entity resolution, where the mention carries no provider
        context. Ambiguity across providers/instruments is the CALLER's
        problem — this returns every hit so it can be flagged, never
        silently resolved to the first match."""
        hits = tuple(
            r
            for r in self._records.values()
            for m in r.provider_symbols
            if m.provider_symbol == provider_symbol
        )
        return hits

    def all_records(self) -> tuple[InstrumentRecord, ...]:
        return tuple(self._records.values())

    def __len__(self) -> int:
        return len(self._records)

    # -- internals ---------------------------------------------------------
    def _get(self, internal_id: str) -> InstrumentRecord:
        if internal_id not in self._records:
            raise KeyError(f"unknown internal_id {internal_id!r}")
        return self._records[internal_id]

    def _event(self, at: datetime, event: str, detail: str, ref: str) -> None:
        if self._audit is None:
            return
        self._audit.record(at, "registry", event, detail, ref)
