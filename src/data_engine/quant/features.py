"""Phase 6 — Feature Engineering pipeline (blueprint 5.21).

Transforms raw market data into model features with PIT correctness:

- ``FeatureSpec``: declarative feature (indicator name + parameters +
  output name). Immutable, hash-pinned.
- ``FeaturePipeline``: computes features over duck-typed candle lists
  with a hard AS-OF discipline: only candles with ``timestamp <= as_of``
  are visible to the pipeline. A feature referencing data beyond the
  cutoff is a leakage defect — the pipeline refuses it (fail closed)
  rather than computing a contaminated feature.

Invariants (blueprint 5.21):
- PIT-correct feature computation (as-of cutoff enforced)
- No future data in features (structural: the pipeline slices first,
  computes second)
- Deterministic output (identical candles + identical specs ->
  identical feature dataset hash, any process)
- Provenance: the feature dataset hash covers input candles AND specs
  AND the as-of cutoff (``feat6.`` identity)
"""

from datetime import datetime, UTC
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.pit.immutable import freeze
from data_engine.quant.registry import get_registry

#: Identity prefix for feature dataset hashes.
FEATURE_PREFIX = "feat6."

#: Phase 6 component contract version.
PHASE_6_CONTRACT_VERSION = "1.0.0"


class FeaturePipelineError(ValueError):
    """Raised on feature-pipeline contract violations."""


def _candle_time(candle: Mapping[str, Any]) -> datetime:
    ts = candle.get("timestamp")
    if ts is None or not hasattr(ts, "tzinfo") or ts.tzinfo is None:
        raise FeaturePipelineError(
            "candles need timezone-aware 'timestamp' fields"
        )
    return ts.astimezone(UTC)


class FeatureSpec(BaseModel):
    """One declarative feature: indicator + parameters + output name."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    output_name: str
    indicator: str
    parameters: dict[str, Any] = Field(
        default_factory=dict, validate_default=True
    )

    @field_validator("output_name", "indicator")
    @classmethod
    def _validate_names(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("feature names must be non-empty strings")
        return v.strip()

    @field_validator("parameters")
    @classmethod
    def _freeze_parameters(cls, v: dict) -> dict:
        # BUG-008: deep-immutable record containers.
        return freeze(v) if v is not None else v

    @property
    def spec_hash(self) -> str:
        payload = {
            "contract_version": PHASE_6_CONTRACT_VERSION,
            "output_name": self.output_name,
            "indicator": self.indicator,
            "parameters": self.parameters,
        }
        return deterministic_hash(payload)


class FeatureDataset(BaseModel):
    """Computed feature rows with full provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    as_of: datetime
    spec_hashes: tuple[str, ...]
    output_names: tuple[str, ...]
    rows: tuple[dict, ...]
    input_candles_hash: str

    @field_validator("as_of")
    @classmethod
    def _validate_as_of(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        return v.astimezone(UTC)

    @property
    def feature_dataset_hash(self) -> str:
        """Deterministic identity: ``feat6.`` + SHA-256 hex (70 chars)."""
        payload = {
            "contract_version": PHASE_6_CONTRACT_VERSION,
            "as_of": self.as_of,
            "spec_hashes": list(self.spec_hashes),
            "output_names": list(self.output_names),
            "input_candles_hash": self.input_candles_hash,
            "rows": [
                {
                    "timestamp": row["timestamp"].isoformat(),
                    "features": {
                        k: _freeze(v) for k, v in row["features"].items()
                    },
                }
                for row in self.rows
            ],
        }
        return FEATURE_PREFIX + deterministic_hash(payload)


def _freeze(value: Any) -> Any:
    """Freeze a feature value into a hashable canonical form."""
    if isinstance(value, float):
        if value != value:  # NaN
            return "NaN"
        return round(value, 12)
    return value


class FeaturePipeline:
    """PIT-correct feature computation over duck-typed candles.

    Usage:
        pipeline = FeaturePipeline(specs=(FeatureSpec(...), ...))
        dataset = pipeline.compute(candles, as_of=utc_cutoff)
    """

    def __init__(self, specs: Sequence[FeatureSpec]) -> None:
        if not specs:
            raise FeaturePipelineError(
                "a feature pipeline needs at least one FeatureSpec"
            )
        names = [s.output_name for s in specs]
        if len(set(names)) != len(names):
            raise FeaturePipelineError(
                f"duplicate feature output names: {names}"
            )
        registry = get_registry()
        for spec in specs:
            if not registry.has_indicator(spec.indicator):
                raise FeaturePipelineError(
                    f"unknown indicator {spec.indicator!r} (not registered)"
                )
        self._specs = tuple(specs)

    @property
    def specs(self) -> tuple[FeatureSpec, ...]:
        return self._specs

    def compute(
        self,
        candles: Sequence[Mapping[str, Any]],
        as_of: datetime,
    ) -> FeatureDataset:
        """Compute features over the PIT-visible candle prefix.

        Hard rule: candles with ``timestamp > as_of`` are INVISIBLE.
        The pipeline slices first and computes second — features are
        structurally incapable of referencing future data.
        """
        if as_of is None or as_of.tzinfo is None:
            raise FeaturePipelineError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(UTC)

        visible = [c for c in candles if _candle_time(c) <= cutoff]
        if not visible:
            raise FeaturePipelineError(
                "no candles visible at the as_of cutoff — refusing to "
                "compute features over an empty window"
            )

        candles_payload = [
            {
                "timestamp": _candle_time(c).isoformat(),
                "close": str(c.get("close")),
            }
            for c in visible
        ]
        input_hash = deterministic_hash(candles_payload)
        closes = [
            float(c["close"]) for c in visible if c.get("close") is not None
        ]
        if len(closes) != len(visible):
            raise FeaturePipelineError(
                "every visible candle must carry a close price"
            )

        registry = get_registry()
        computed: dict[str, Optional[list[float]]] = {}
        for spec in self._specs:
            result = registry.get(spec.indicator).function(
                closes, **spec.parameters
            )
            computed[spec.output_name] = result

        rows = []
        for idx, candle in enumerate(visible):
            features: dict[str, Any] = {}
            for spec in self._specs:
                series = computed[spec.output_name]
                value = series[idx] if series is not None else None
                features[spec.output_name] = _freeze(value)
            rows.append(
                {
                    "timestamp": _candle_time(candle),
                    "features": features,
                }
            )

        return FeatureDataset(
            as_of=cutoff,
            spec_hashes=tuple(s.spec_hash for s in self._specs),
            output_names=tuple(s.output_name for s in self._specs),
            rows=tuple(rows),
            input_candles_hash=input_hash,
        )


__all__ = [
    "FeatureSpec",
    "FeatureDataset",
    "FeaturePipeline",
    "FeaturePipelineError",
    "FEATURE_PREFIX",
    "PHASE_6_CONTRACT_VERSION",
]
