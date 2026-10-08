"""Phase 8 — Portfolio construction (blueprint 5.28).

Deterministic allocation from validated strategies with risk
constraints:

- ``PortfolioConstructor``: inverse-volatility weighting — a
  deterministic, explainable scheme requiring only per-strategy
  volatility estimates. Weights are normalized to a target gross
  exposure and validated against the risk limits BEFORE being
  returned (constraint satisfaction is a precondition, not a
  post-hoc check).
- Zero/negative volatilities fail closed (a strategy with zero
  measured volatility has an ill-defined inverse weight).
- Long-only construction by default; shorting requires explicit
  authorization flags and is subject to the same limit gauntlet.

Identity: ``port8.`` prefix over the allocation payload.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.pit.immutable import freeze
from data_engine.risk.engine import RiskEngine, RiskLimits

#: Phase 8 contract version.
PHASE_8_CONTRACT_VERSION = "1.0.0"

#: Satoshis of precision for weight rounding (8 dp).
_WEIGHT_QUANT = Decimal("0.00000001")


class PortfolioError(ValueError):
    """Raised on portfolio-construction violations."""


class Allocation(BaseModel):
    """A deterministic portfolio allocation with identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: dict[str, str]  # symbol -> Decimal string
    gross_exposure: str

    @field_validator("weights")
    @classmethod
    def _validate_weights(cls, v: dict) -> dict:
        if not v:
            raise PortfolioError("allocation must be non-empty")
        # BUG-008: deep-immutable record containers.
        return freeze(v)

    @property
    def allocation_hash(self) -> str:
        return "port8." + deterministic_hash(
            {
                "contract_version": PHASE_8_CONTRACT_VERSION,
                "weights": dict(sorted(self.weights.items())),
                "gross_exposure": self.gross_exposure,
            }
        )


class PortfolioConstructor:
    """Inverse-volatility allocation with limit enforcement."""

    def __init__(self, risk_engine: RiskEngine) -> None:
        self._engine = risk_engine

    @property
    def limits(self) -> RiskLimits:
        return self._engine.limits

    def allocate(
        self,
        volatilities: Mapping[str, Decimal],
        target_gross: Decimal,
        sectors: Optional[Mapping[str, str]] = None,
    ) -> Allocation:
        """Inverse-volatility weights scaled to ``target_gross``.

        Steps: (1) validate inputs; (2) raw weights w_i = 1/vol_i;
        (3) normalize to sum 1; (4) scale by target_gross; (5) run the
        FULL limit gauntlet (single-asset, sector, leverage, heat) —
        any breach raises and no allocation is produced.
        """
        if not volatilities:
            raise PortfolioError("volatilities must be non-empty")
        for symbol, vol in volatilities.items():
            if not isinstance(vol, Decimal) or not vol.is_finite() or vol <= 0:
                raise PortfolioError(
                    f"volatility for {symbol} must be a positive Decimal "
                    "(zero-volatility strategies have ill-defined "
                    "inverse weights)"
                )
        if not isinstance(target_gross, Decimal) or target_gross <= 0:
            raise PortfolioError("target_gross must be a positive Decimal")

        inverse = {
            symbol: Decimal(1) / vol for symbol, vol in volatilities.items()
        }
        total_inverse = sum(inverse.values(), Decimal(0))
        weights = {
            symbol: (
                inv / total_inverse * target_gross
            ).quantize(_WEIGHT_QUANT, rounding=ROUND_HALF_UP)
            for symbol, inv in inverse.items()
        }

        # Constraint satisfaction BEFORE returning (blueprint 5.28).
        self._engine.check_weights(
            weights,
            sectors=sectors,
            gross_leverage=target_gross,
        )

        return Allocation(
            weights={s: str(w) for s, w in sorted(weights.items())},
            gross_exposure=str(target_gross),
        )


__all__ = [
    "PortfolioError",
    "Allocation",
    "PortfolioConstructor",
    "PHASE_8_CONTRACT_VERSION",
]
