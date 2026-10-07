"""Phase 8 — Risk limits and exposure management (blueprint 5.29/5.30).

Hard limits with zero-override semantics:

- ``RiskLimits``: immutable limit set (max position size, max leverage,
  max single-asset weight, max sector weight, max portfolio heat).
  Limits are CONSTRUCTION-validated (positive, coherent).
- ``RiskEngine``: evaluates orders/portfolios against limits. Any
  breach raises :class:`RiskViolationError` — there is no warn-and-
  continue path (blueprint 5.29: 'zero tolerance for limit breaches',
  'no override'). Violations are recorded in a hash-chained log.
- ``ExposureManager``: aggregates exposures by asset and sector and
  checks them against the limits (blueprint 5.30).

The kill switch (blueprint 5.54) is modeled as engine state: once
tripped, every subsequent evaluation raises until explicitly reset by
an external controller.
"""

from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash

#: Phase 8 contract version.
PHASE_8_CONTRACT_VERSION = "1.0.0"


class RiskViolationError(ValueError):
    """A hard risk limit was breached — there is no override path."""


class KillSwitchActiveError(RiskViolationError):
    """The kill switch is tripped; all evaluation refuses."""


def _positive_decimal(v: Decimal) -> Decimal:
    if v is None or not v.is_finite() or v <= 0:
        raise ValueError("risk limits must be positive finite Decimals")
    return v


def _fraction(v: Decimal) -> Decimal:
    if v is None or not v.is_finite() or not 0 < v <= 1:
        raise ValueError("weight limits must be in (0, 1]")
    return v


class RiskLimits(BaseModel):
    """Immutable hard limit set. Coherent by construction."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    max_position_units: Decimal
    max_leverage: Decimal
    max_single_asset_weight: Decimal
    max_sector_weight: Decimal
    max_portfolio_heat: Decimal  # total notional / equity, fraction

    @field_validator(
        "max_position_units", "max_leverage", "max_portfolio_heat"
    )
    @classmethod
    def _validate_positive(cls, v: Decimal) -> Decimal:
        return _positive_decimal(v)

    @field_validator("max_single_asset_weight", "max_sector_weight")
    @classmethod
    def _validate_fraction(cls, v: Decimal) -> Decimal:
        return _fraction(v)

    @model_validator(mode="after")
    def _validate_coherence(self) -> "RiskLimits":
        if self.max_single_asset_weight > self.max_sector_weight:
            raise ValueError(
                "incoherent limits: single-asset weight cap exceeds the "
                "sector weight cap"
            )
        return self

    @property
    def limits_hash(self) -> str:
        return "risk8." + deterministic_hash(
            {
                "contract_version": PHASE_8_CONTRACT_VERSION,
                "max_position_units": str(self.max_position_units),
                "max_leverage": str(self.max_leverage),
                "max_single_asset_weight": str(self.max_single_asset_weight),
                "max_sector_weight": str(self.max_sector_weight),
                "max_portfolio_heat": str(self.max_portfolio_heat),
            }
        )


class ViolationRecord(BaseModel):
    """One recorded limit violation (audit trail entry)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule: str
    detail: str
    record_index: int
    prev_record_hash: str
    record_hash: str

    @field_validator("rule", "detail", "record_hash")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v:
            raise ValueError("violation record fields must be non-empty")
        return v


class ExposureReport(BaseModel):
    """Aggregated exposure snapshot with limit verdicts."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    by_asset: dict[str, str]
    by_sector: dict[str, str]
    single_asset_breaches: tuple[str, ...]
    sector_breaches: tuple[str, ...]
    total_exposure: str

    @property
    def report_hash(self) -> str:
        return "expo8." + deterministic_hash(
            {
                "contract_version": PHASE_8_CONTRACT_VERSION,
                "by_asset": self.by_asset,
                "by_sector": self.by_sector,
                "single_asset_breaches": list(self.single_asset_breaches),
                "sector_breaches": list(self.sector_breaches),
                "total_exposure": self.total_exposure,
            }
        )


class RiskEngine:
    """Hard-limit enforcement with hash-chained violation log and
    kill switch.

    The engine evaluates proposed ORDERS and WEIGHT VECTORS. Every
    breach raises (fail closed) AND is recorded. The kill switch trips
    on any breach when configured ``trip_on_breach=True`` (the default
    for production posture; testing may disable).
    """

    def __init__(
        self,
        limits: RiskLimits,
        trip_on_breach: bool = True,
    ) -> None:
        self._limits = limits
        self._trip_on_breach = trip_on_breach
        self._kill_switch = False
        self._records: list[ViolationRecord] = []

    # ------------------------------------------------------------------
    @property
    def limits(self) -> RiskLimits:
        return self._limits

    @property
    def kill_switch_active(self) -> bool:
        return self._kill_switch

    def trip_kill_switch(self) -> None:
        """Trip the kill switch (external controller action)."""
        self._kill_switch = True

    def reset_kill_switch(self) -> None:
        """Reset the kill switch (external controller action)."""
        self._kill_switch = False

    @property
    def violation_log(self) -> tuple[ViolationRecord, ...]:
        return tuple(self._records)

    def _record(self, rule: str, detail: str) -> None:
        prev = (
            self._records[-1].record_hash if self._records else "0" * 64
        )
        record_hash = deterministic_hash(
            {
                "contract_version": PHASE_8_CONTRACT_VERSION,
                "rule": rule,
                "detail": detail,
                "record_index": len(self._records),
                "prev_record_hash": prev,
            }
        )
        self._records.append(
            ViolationRecord(
                rule=rule,
                detail=detail,
                record_index=len(self._records),
                prev_record_hash=prev,
                record_hash=record_hash,
            )
        )

    def _guard(self) -> None:
        if self._kill_switch:
            raise KillSwitchActiveError(
                "kill switch active: all risk evaluation refuses until "
                "externally reset (blueprint 5.54)"
            )

    # ------------------------------------------------------------------
    def check_order(
        self,
        symbol: str,
        units: Decimal,
        current_units: Optional[Decimal] = None,
    ) -> None:
        """Validate a proposed order's position size (raises on breach)."""
        self._guard()
        if not isinstance(units, Decimal) or not units.is_finite() or units == 0:
            raise RiskViolationError(
                "order units must be a non-zero finite Decimal"
            )
        projected = abs(units) + (
            abs(current_units) if current_units is not None else Decimal(0)
        )
        if projected > self._limits.max_position_units:
            detail = (
                f"position {symbol}: projected {projected} units exceeds "
                f"max {self._limits.max_position_units}"
            )
            self._record("max_position_units", detail)
            if self._trip_on_breach:
                self._kill_switch = True
            raise RiskViolationError(detail)

    def check_weights(
        self,
        weights: Mapping[str, Decimal],
        sectors: Optional[Mapping[str, str]] = None,
        gross_leverage: Optional[Decimal] = None,
    ) -> None:
        """Validate a weight vector: single-asset, sector, leverage, heat.

        ``weights``: symbol -> signed weight (fraction of equity).
        ``sectors``: optional symbol -> sector mapping.
        ``gross_leverage``: total notional / equity (portfolio heat).
        """
        self._guard()
        for symbol, weight in weights.items():
            if abs(weight) > self._limits.max_single_asset_weight:
                detail = (
                    f"single-asset weight {symbol}: {abs(weight)} exceeds "
                    f"max {self._limits.max_single_asset_weight}"
                )
                self._record("max_single_asset_weight", detail)
                if self._trip_on_breach:
                    self._kill_switch = True
                raise RiskViolationError(detail)
        if sectors:
            sector_totals: dict[str, Decimal] = {}
            for symbol, weight in weights.items():
                sector = sectors.get(symbol, "UNKNOWN")
                sector_totals[sector] = (
                    sector_totals.get(sector, Decimal(0)) + abs(weight)
                )
            for sector, total in sector_totals.items():
                if total > self._limits.max_sector_weight:
                    detail = (
                        f"sector weight {sector}: {total} exceeds max "
                        f"{self._limits.max_sector_weight}"
                    )
                    self._record("max_sector_weight", detail)
                    if self._trip_on_breach:
                        self._kill_switch = True
                    raise RiskViolationError(detail)
        if gross_leverage is not None:
            if gross_leverage > self._limits.max_leverage:
                detail = (
                    f"gross leverage {gross_leverage} exceeds max "
                    f"{self._limits.max_leverage}"
                )
                self._record("max_leverage", detail)
                if self._trip_on_breach:
                    self._kill_switch = True
                raise RiskViolationError(detail)
            if gross_leverage > self._limits.max_portfolio_heat:
                detail = (
                    f"portfolio heat {gross_leverage} exceeds max "
                    f"{self._limits.max_portfolio_heat}"
                )
                self._record("max_portfolio_heat", detail)
                if self._trip_on_breach:
                    self._kill_switch = True
                raise RiskViolationError(detail)


class ExposureManager:
    """Aggregate exposures by asset/sector and evaluate limits."""

    def __init__(self, limits: RiskLimits) -> None:
        self._limits = limits

    def build_report(
        self,
        positions: Mapping[str, Decimal],  # symbol -> signed units
        prices: Mapping[str, Decimal],  # symbol -> unit price
        equity: Decimal,
        sectors: Optional[Mapping[str, str]] = None,
    ) -> ExposureReport:
        """Build the exposure report (fractions of equity)."""
        if equity is None or equity <= 0:
            raise ValueError("equity must be a positive Decimal")
        by_asset: dict[str, str] = {}
        for symbol, units in positions.items():
            price = prices.get(symbol)
            if price is None:
                raise ValueError(f"missing price for {symbol}")
            notional = abs(units) * price
            by_asset[symbol] = str(notional / equity)
        by_sector: dict[str, str] = {}
        for symbol, frac_str in by_asset.items():
            sector = (sectors or {}).get(symbol, "UNKNOWN")
            current = Decimal(by_sector.get(sector, "0"))
            by_sector[sector] = str(current + Decimal(frac_str))
        total = sum((Decimal(v) for v in by_asset.values()), Decimal(0))

        asset_breaches = tuple(
            sorted(
                s for s, f in by_asset.items()
                if Decimal(f) > self._limits.max_single_asset_weight
            )
        )
        sector_breaches = tuple(
            sorted(
                sec for sec, f in by_sector.items()
                if Decimal(f) > self._limits.max_sector_weight
            )
        )
        return ExposureReport(
            by_asset=by_asset,
            by_sector=by_sector,
            single_asset_breaches=asset_breaches,
            sector_breaches=sector_breaches,
            total_exposure=str(total),
        )


__all__ = [
    "RiskLimits",
    "RiskViolationError",
    "KillSwitchActiveError",
    "ViolationRecord",
    "ExposureReport",
    "RiskEngine",
    "ExposureManager",
    "PHASE_8_CONTRACT_VERSION",
]
