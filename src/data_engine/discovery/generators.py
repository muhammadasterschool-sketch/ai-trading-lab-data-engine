"""Deterministic rule-based strategy generation (blueprint 5.20).

The generator enumerates a bounded, declarative parameter grid and
emits frozen Phase 3 ``StrategySpec`` instances wrapped in
``StrategyCandidate`` records with full governance metadata.

Determinism contract:

- Output is a pure function of (templates, hypothesis hash, dataset
  hash, seed, grid). The seed selects the grid POINT ORDER via a
  deterministic permutation (sorted-then-rotated) — never an RNG.
- No wall clock, no environment, no network, no code execution.
- Grid size is bounded: ``max_grid_points`` (fail-closed if exceeded)
  so a template cannot silently explode into an unbounded search.

Governance contract:

- Generated candidates are DRAFT — nothing is auto-promoted.
- A candidate whose spec fails Phase 3 parsing is emitted as REJECTED
  with a reason (strategies are allowed to fail; evidence preserved).
"""

import json
from itertools import product
from typing import Optional, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator

from data_engine.discovery.models import (
    DISCOVERY_CONTRACT_VERSION,
    CandidateStatus,
    DataDependencies,
    DiscoveryProvenance,
    ExecutionAssumptions,
    ParameterField,
    ParameterSchema,
    RiskAssumptions,
    StrategyCandidate,
    ValidationRequirements,
)
from data_engine.strategy.schemas import EntryCondition, StrategySpec

#: Hard bound on enumerated grid points per generation call.
MAX_GRID_POINTS = 64


class GeneratorError(ValueError):
    """Raised when a generation request violates the grid contract."""


class RuleTemplate(BaseModel):
    """One declarative rule-based strategy family (bounded grid)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    template_id: str
    description: str = ""
    indicator: str
    entry_operator: str = Field(pattern="^(>|<|>=|<=|==)$")
    entry_thresholds: tuple[float, ...] = ()
    exit_indicator: Optional[str] = None
    exit_operator: str = Field(default="<", pattern="^(>|<|>=|<=|==)$")
    exit_thresholds: tuple[float, ...] = ()
    stop_loss_pcts: tuple[Optional[float], ...] = (None,)
    take_profit_pcts: tuple[Optional[float], ...] = (None,)
    min_history_bars: int = Field(default=20, gt=0)

    @field_validator("template_id", "indicator")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("template ids/indicators must be non-empty")
        return v.strip()

    @field_validator("entry_thresholds", "exit_thresholds")
    @classmethod
    def _validate_thresholds(cls, v: tuple[float, ...]) -> tuple[float, ...]:
        if not v:
            raise ValueError("threshold grids must be non-empty")
        if any(x is None for x in v):
            raise ValueError("threshold grids must be concrete numbers")
        if len(set(v)) != len(v):
            raise ValueError("threshold grids must be distinct")
        if list(v) != sorted(v):
            raise ValueError("threshold grids must be sorted ascending")
        return tuple(float(x) for x in v)

    @field_validator("stop_loss_pcts", "take_profit_pcts")
    @classmethod
    def _validate_pct_grids(cls, v: tuple[Optional[float], ...]) -> tuple[Optional[float], ...]:
        concrete = [x for x in v if x is not None]
        if any(x <= 0 or x > 100 for x in concrete):
            raise ValueError("percent grids must lie in (0, 100]")
        if len(set(concrete)) != len(concrete):
            raise ValueError("percent grids must be distinct")
        if not v:
            return (None,)
        return v

    def grid_size(self) -> int:
        """Total number of grid points (entries × exits × stops × tps)."""
        exits = self.exit_thresholds if self.exit_indicator else (None,)
        return (
            len(self.entry_thresholds)
            * len(exits)
            * len(self.stop_loss_pcts)
            * len(self.take_profit_pcts)
        )

    def parameter_schema(self) -> ParameterSchema:
        """Declarative schema for this template's parameter space."""
        fields = [
            ParameterField(
                name="entry_threshold",
                type="number",
                low=min(self.entry_thresholds),
                high=max(self.entry_thresholds),
                grid=self.entry_thresholds,
            )
        ]
        if self.exit_indicator:
            fields.append(
                ParameterField(
                    name="exit_threshold",
                    type="number",
                    low=min(self.exit_thresholds),
                    high=max(self.exit_thresholds),
                    grid=self.exit_thresholds,
                )
            )
        stop_concrete = [x for x in self.stop_loss_pcts if x is not None]
        if stop_concrete:
            fields.append(
                ParameterField(
                    name="stop_loss_pct",
                    type="number",
                    low=min(stop_concrete),
                    high=max(stop_concrete),
                    grid=tuple(stop_concrete),
                )
            )
        return ParameterSchema(fields=tuple(fields))


class RuleBasedGenerator:
    """Deterministic bounded-grid generator over rule templates."""

    generator_id = "rule-based-v1"

    def __init__(self, templates: Sequence[RuleTemplate]) -> None:
        if not templates:
            raise GeneratorError("at least one RuleTemplate is required")
        ids = [t.template_id for t in templates]
        if len(set(ids)) != len(ids):
            raise GeneratorError("template ids must be unique")
        self._templates = tuple(templates)

    @property
    def templates(self) -> tuple[RuleTemplate, ...]:
        return self._templates

    def generate(
        self,
        hypothesis_hash: str,
        dataset_hash: str,
        instrument: str,
        timeframe: str,
        seed: int = 0,
    ) -> tuple[StrategyCandidate, ...]:
        """Generate candidates deterministically from the bounded grids.

        The seed rotates the enumeration order (sorted points rotated by
        ``seed % N``) so different seeds surface different first-points
        without introducing nondeterminism or an RNG.
        """
        if len(hypothesis_hash) < 16 or len(dataset_hash) < 16:
            raise GeneratorError(
                "hypothesis/dataset hashes must be verifiable (>= 16 chars)"
            )
        candidates: list[StrategyCandidate] = []
        for template in self._templates:
            n = template.grid_size()
            if n > MAX_GRID_POINTS:
                raise GeneratorError(
                    f"template {template.template_id!r} grid exceeds the "
                    f"bound ({n} > {MAX_GRID_POINTS})"
                )
            points = self._grid_points(template)
            rotation = seed % len(points) if points else 0
            # Canonical indices travel with their points: the spec id
            # reflects the grid POINT (stable across seeds), while the
            # candidate id reflects the rotated enumeration position.
            indexed = list(enumerate(points))
            ordered = indexed[rotation:] + indexed[:rotation]
            for position, (index, point) in enumerate(ordered):
                candidate = self._build_candidate(
                    template=template,
                    point=point,
                    index=index,
                    position=position,
                    hypothesis_hash=hypothesis_hash,
                    dataset_hash=dataset_hash,
                    instrument=instrument,
                    timeframe=timeframe,
                    seed=seed,
                )
                candidates.append(candidate)
        return tuple(candidates)

    def _grid_points(self, template: RuleTemplate) -> tuple[dict, ...]:
        """Enumerate grid points in canonical (sorted) order."""
        exits = (
            template.exit_thresholds
            if template.exit_indicator
            else (None,)
        )
        combos = list(
            product(
                template.entry_thresholds,
                exits,
                template.stop_loss_pcts,
                template.take_profit_pcts,
            )
        )
        return tuple(
            {
                "entry_threshold": entry,
                "exit_threshold": exit_t,
                "stop_loss_pct": stop,
                "take_profit_pct": take,
            }
            for entry, exit_t, stop, take in combos
        )

    def _build_candidate(
        self,
        template: RuleTemplate,
        point: dict,
        index: int,
        position: int,
        hypothesis_hash: str,
        dataset_hash: str,
        instrument: str,
        timeframe: str,
        seed: int,
    ) -> StrategyCandidate:
        entry = EntryCondition(
            indicator=template.indicator,
            operator=template.entry_operator,
            threshold=point["entry_threshold"],
        )
        entry_serialized = json.dumps([entry.to_dict()], sort_keys=True)
        exit_serialized = ""
        if template.exit_indicator and point["exit_threshold"] is not None:
            # ExitCondition (frozen Phase 3) shape: type/indicator/
            # operator/threshold — declarative, no code execution.
            exit_payload = {
                "type": "condition",
                "indicator": template.exit_indicator,
                "operator": template.exit_operator,
                "threshold": point["exit_threshold"],
            }
            exit_serialized = json.dumps([exit_payload], sort_keys=True)

        spec = StrategySpec(
            strategy_id=(
                f"{template.template_id}-{index:03d}-"
                f"{DISCOVERY_CONTRACT_VERSION}"
            ),
            strategy_version="3.0.0",
            strategy_name=f"discovery:{template.template_id}",
            instrument=instrument,
            timeframe=timeframe,
            entry_conditions_serialized=entry_serialized,
            exit_conditions_serialized=exit_serialized,
            position_sizing_serialized=json.dumps(
                {"method": "fixed", "fixed_quantity": 1.0}, sort_keys=True
            ),
            stop_loss_pct=point["stop_loss_pct"],
            take_profit_pct=point["take_profit_pct"],
            max_position_size=1.0,
            max_exposure_pct=100.0,
            required_indicators=[template.indicator],
            description=(
                f"Generated by {self.generator_id} from template "
                f"{template.template_id!r} ({template.description})."
            ),
            author=self.generator_id,
        )
        provenance = DiscoveryProvenance(
            generator_id=self.generator_id,
            template_id=template.template_id,
            hypothesis_hash=hypothesis_hash,
            dataset_hash=dataset_hash,
            seed=seed,
        )
        return StrategyCandidate(
            candidate_id=(
                f"{template.template_id}:{position:03d}:{seed}"
            ),
            spec=spec,
            parameter_schema=template.parameter_schema(),
            data_dependencies=DataDependencies(
                instrument=instrument,
                timeframe=timeframe,
                feature_outputs=(template.indicator,),
            ),
            risk_assumptions=RiskAssumptions(
                max_position_units=1.0,
                stop_loss_pct=point["stop_loss_pct"],
                take_profit_pct=point["take_profit_pct"],
            ),
            execution_assumptions=ExecutionAssumptions(
                execution_semantics=spec.execution_semantics,
                cost_included=True,
                slippage_included=True,
            ),
            validation_requirements=ValidationRequirements(
                min_history_bars=template.min_history_bars,
                require_walk_forward=True,
                require_out_of_sample=True,
            ),
            provenance=provenance,
        )


def reject_candidate(
    candidate: StrategyCandidate,
    reason: str,
) -> StrategyCandidate:
    """Mark a candidate REJECTED with its reason (evidence preserved)."""
    if not reason or not reason.strip():
        raise ValueError("rejection reason must be non-empty")
    return candidate.with_status(CandidateStatus.REJECTED, reason.strip())
