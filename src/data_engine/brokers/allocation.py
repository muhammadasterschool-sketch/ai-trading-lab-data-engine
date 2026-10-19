"""Multi-broker ALLOCATION engine (Stage G, Part 9B G4 — owner mandate).

Broker registry with per-broker allocation weights and limits;
capability-aware order routing; fail-closed allocation config
validation; per-broker trade ledger entries; allocation changes
audited.

Fail-closed contract (never weakened to make anything pass):

- config validation: entries REQUIRED, broker ids UNIQUE, weights
  strictly positive and summing to EXACTLY 1, limits non-negative;
- routing consults ONLY registered capability descriptors — an
  unknown broker id is UNKNOWN and therefore BLOCKED
  (``AllocationRefused``; mirrors the G5 plugin discipline);
- capability awareness: a broker is eligible only if its descriptor
  supports the order's kind + time-in-force + reduce-only needs;
- per-broker limits (open orders, open notional) are hard gates —
  a broker at its cap is skipped, and with NO eligible broker the
  routing REFUSES (no fallback-to-any-broker);
- selection is DETERMINISTIC: the eligible broker with the highest
  weight wins; exact ties break by ascending broker_id (documented,
  reproducible);
- every routing decision returns a structured rationale suitable
  for a per-broker ledger entry; allocation CONFIG changes emit an
  auditable record the caller journals.

LIVE TRADING REMAINS NOT AUTHORIZED (all registered venues are
MOCK_DETERMINISTIC in this repository).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.brokers.capabilities import (
    BrokerCapabilities,
    CapabilityRegistry,
    CapabilityRegistryError,
    ExecutionMode,
)
from data_engine.brokers.models import OrderKind, TimeInForce

#: Tolerance for the weight sum: EXACT (allocation shares must be
#: explicit, never "close enough").
WEIGHT_SUM = Decimal("1")


class AllocationError(ValueError):
    """Raised on allocation-contract violations (fail closed)."""


class AllocationRefused(AllocationError):
    """Routing refused — no eligible broker (fail closed)."""


class BrokerAllocationEntry(BaseModel):
    """One broker's allocation share + hard limits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    broker_id: str
    weight: Decimal
    max_open_orders: int = 10
    max_open_notional: Optional[Decimal] = None

    @field_validator("broker_id")
    @classmethod
    def _validate_broker(cls, v: str) -> str:
        if not v or not v.strip():
            raise AllocationError("broker_id must be non-empty")
        return v.strip()

    @field_validator("weight")
    @classmethod
    def _validate_weight(cls, v) -> Decimal:
        if v is None or not isinstance(v, Decimal) or v <= 0:
            raise AllocationError(
                "allocation weight must be a strictly positive Decimal"
            )
        return v

    @field_validator("max_open_orders")
    @classmethod
    def _validate_open_orders(cls, v: int) -> int:
        if v is None or v < 1:
            raise AllocationError("max_open_orders must be >= 1")
        return v


class AllocationConfig(BaseModel):
    """The validated multi-broker allocation configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: Tuple[BrokerAllocationEntry, ...]

    @field_validator("entries")
    @classmethod
    def _validate_entries(cls, v) -> Tuple[BrokerAllocationEntry, ...]:
        if not v:
            raise AllocationError(
                "an allocation config requires at least one broker entry "
                "(fail closed — no implicit default broker)"
            )
        ids = [entry.broker_id for entry in v]
        if len(set(ids)) != len(ids):
            duplicates = sorted(
                {b for b in ids if ids.count(b) > 1}
            )
            raise AllocationError(
                f"duplicate broker entries: {duplicates} (one entry per "
                "broker — capability drift must be explicit)"
            )
        total = sum((entry.weight for entry in v), Decimal("0"))
        if total != WEIGHT_SUM:
            raise AllocationError(
                f"allocation weights must sum to exactly 1 (got {total}) — "
                "explicit shares only, never 'close enough'"
            )
        return tuple(v)

    def entry_for(self, broker_id: str) -> BrokerAllocationEntry:
        for entry in self.entries:
            if entry.broker_id == broker_id:
                return entry
        raise AllocationError(f"no allocation entry for {broker_id!r}")


@dataclass(frozen=True)
class OrderRequestSpec:
    """The routing-relevant projection of an order request."""

    order_kind: OrderKind
    time_in_force: TimeInForce = TimeInForce.GTC
    reduce_only: bool = False
    notional: Optional[Decimal] = None
    symbol: str = ""


@dataclass(frozen=True)
class BrokerLoad:
    """Current per-broker load (open orders / open notional)."""

    broker_id: str
    open_orders: int = 0
    open_notional: Decimal = Decimal("0")


@dataclass(frozen=True)
class AllocationDecision:
    """One routing decision — fully auditable."""

    broker_id: str
    weight: Decimal
    eligible_brokers: Tuple[str, ...]
    skipped: Tuple[Tuple[str, str], ...]  # (broker_id, reason)
    rationale: str

    def ledger_payload(self) -> dict:
        """Per-broker trade-ledger entry payload (G4 mandate)."""
        return {
            "selected_broker": self.broker_id,
            "weight": str(self.weight),
            "eligible": list(self.eligible_brokers),
            "skipped": [
                {"broker": broker, "reason": reason}
                for broker, reason in self.skipped
            ],
            "rationale": self.rationale,
        }


def _capabilities_support(
    caps: BrokerCapabilities, request: OrderRequestSpec
) -> Optional[str]:
    """None when supported; otherwise a human-readable refusal reason."""
    if request.order_kind not in caps.order_kinds:
        return (
            f"order kind {request.order_kind.value} unsupported "
            f"(supports: {[k.value for k in caps.order_kinds]})"
        )
    if request.time_in_force not in caps.time_in_force:
        return (
            f"time-in-force {request.time_in_force.value} unsupported"
        )
    if request.reduce_only and not caps.supports_reduce_only:
        return "reduce-only unsupported"
    return None


def route_order(
    request: OrderRequestSpec,
    *,
    config: AllocationConfig,
    registry: CapabilityRegistry,
    loads: Optional[Mapping[str, BrokerLoad]] = None,
) -> AllocationDecision:
    """Route one order to a broker — deterministic, fail-closed.

    Unknown broker ids in the CONFIG are refused outright (UNKNOWN
    capabilities are BLOCKED); brokers whose capabilities do not
    support the request are skipped with recorded reasons; brokers at
    their limits are skipped; the highest-weight ELIGIBLE broker wins
    (ties break by ascending broker_id).
    """
    if not isinstance(config, AllocationConfig):
        raise AllocationError("an AllocationConfig is required (fail closed)")
    if not isinstance(registry, CapabilityRegistry):
        raise AllocationError(
            "a CapabilityRegistry is required — routing consults ONLY "
            "registered descriptors"
        )
    loads = loads or {}

    # G5 discipline FIRST: every configured broker must be registered —
    # unknown capabilities are UNKNOWN and therefore BLOCKED.
    for entry in config.entries:
        try:
            registry.get(entry.broker_id)
        except CapabilityRegistryError as exc:
            raise AllocationRefused(
                f"allocation config references {entry.broker_id!r} but no "
                f"capability descriptor is registered — unknown "
                f"capabilities are BLOCKED (fail closed): {exc}"
            ) from exc

    eligible: list = []
    skipped: list = []
    for entry in config.entries:
        caps = registry.get(entry.broker_id)
        # operational-safety invariant: only MOCK_DETERMINISTIC venues
        # are routable in this repository (live trading NOT AUTHORIZED)
        if caps.execution_mode is not ExecutionMode.MOCK_DETERMINISTIC:
            skipped.append((entry.broker_id, "non-MOCK execution mode"))
            continue
        reason = _capabilities_support(caps, request)
        if reason is not None:
            skipped.append((entry.broker_id, reason))
            continue
        load = loads.get(entry.broker_id, BrokerLoad(entry.broker_id))
        if load.open_orders >= entry.max_open_orders:
            skipped.append(
                (
                    entry.broker_id,
                    f"open-order cap reached "
                    f"({load.open_orders}/{entry.max_open_orders})",
                )
            )
            continue
        if (
            entry.max_open_notional is not None
            and request.notional is not None
            and load.open_notional + request.notional
            > entry.max_open_notional
        ):
            skipped.append(
                (
                    entry.broker_id,
                    "open-notional cap exceeded "
                    f"({load.open_notional}+{request.notional} > "
                    f"{entry.max_open_notional})",
                )
            )
            continue
        eligible.append(entry)

    if not eligible:
        raise AllocationRefused(
            "no eligible broker for this order (eligible set empty; "
            f"skipped: {skipped or 'none configured'} — routing never "
            "falls back to an unsupported broker)"
        )

    winner = max(
        eligible,
        key=lambda e: (e.weight, [-ord(c) for c in e.broker_id]),
    )
    # deterministic tie-break: equal weights -> ascending broker_id
    top_weight = winner.weight
    tied = [e for e in eligible if e.weight == top_weight]
    if len(tied) > 1:
        winner = min(tied, key=lambda e: e.broker_id)

    return AllocationDecision(
        broker_id=winner.broker_id,
        weight=winner.weight,
        eligible_brokers=tuple(e.broker_id for e in eligible),
        skipped=tuple(skipped),
        rationale=(
            f"highest weight {winner.weight} among eligible "
            f"{[e.broker_id for e in eligible]}; "
            + (
                f"tie among {[e.broker_id for e in tied]} broken by "
                "ascending broker_id (deterministic)"
                if len(tied) > 1 else "no tie"
            )
        ),
    )


@dataclass(frozen=True)
class AllocationConfigChange:
    """An auditable allocation-config change (G4: changes are audited)."""

    old: Optional[AllocationConfig]
    new: AllocationConfig
    actor: str
    reason: str

    def ledger_payload(self) -> dict:
        def _entries(config: Optional[AllocationConfig]) -> list:
            if config is None:
                return []
            return [
                {
                    "broker_id": e.broker_id,
                    "weight": str(e.weight),
                    "max_open_orders": e.max_open_orders,
                    "max_open_notional": str(e.max_open_notional)
                    if e.max_open_notional is not None else None,
                }
                for e in config.entries
            ]

        return {
            "change": "allocation-config",
            "actor": self.actor,
            "reason": self.reason,
            "old": _entries(self.old),
            "new": _entries(self.new),
        }


def validate_allocation_change(
    old: Optional[AllocationConfig], new: AllocationConfig
) -> AllocationConfigChange:
    """Validate an allocation change (both configs fully validated)."""
    if not isinstance(new, AllocationConfig):
        raise AllocationError("new config must be an AllocationConfig")
    if old is not None and not isinstance(old, AllocationConfig):
        raise AllocationError("old config must be an AllocationConfig or None")
    return AllocationConfigChange(old=old, new=new, actor="", reason="")


__all__ = [
    "BrokerAllocationEntry",
    "AllocationConfig",
    "AllocationError",
    "AllocationRefused",
    "OrderRequestSpec",
    "BrokerLoad",
    "AllocationDecision",
    "AllocationConfigChange",
    "route_order",
    "validate_allocation_change",
]
