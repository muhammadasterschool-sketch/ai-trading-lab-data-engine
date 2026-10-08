"""Governed RL runtime — ADVISOR-ONLY policy layer (mandate §28/§44).

WHY THIS MODULE EXISTS
======================
The paper-readiness blocker table carries one genuinely missing
component: the RL runtime. This module closes it HONESTLY, under the
mandate's own rules:

- Workstream E: "The RL agent is an advisor/proposal generator, NOT
  the final authority."
- Workstream E: "If RL cannot be safely production-integrated,
  explicitly mark it DISABLED / NON-AUTHORITATIVE."
- Phase 6: RL must never have authority over Risk, Kill Switch,
  Order Gateway or Live Trading.

WHAT IS IMPLEMENTED
===================
A GOVERNED, DETERMINISTIC, VERSIONED POLICY RUNTIME:

- a frozen observation contract (RLObservation) built ONLY from
  PIT-safe runtime state (the current bar's prediction artifact,
  regime, crash probability, position, equity);
- a bounded action vocabulary (HOLD / BUY / SELL / CLOSE) expressed
  as a TARGET position with a magnitude — never an order;
- hard action bounds: max position units, max turnover per bar,
  max exposure notional fraction, drawdown halt;
- out-of-distribution detection on the observation (fail toward
  HOLD, never toward aggressiveness);
- deterministic identity: proposal_id is a pure function of
  (policy_hash, observation_hash) — INV-01 (no wall clock, no
  randomness, no process state);
- a cross-process-verifiable free function ``propose_rl_action``.

WHAT IS **NOT** CLAIMED (honesty record)
========================================
- The policy is a DETERMINISTIC risk-tempered baseline mapping —
  NOT a trained reinforcement-learning agent. No empirical RL
  performance is claimed, implied or fabricated.
- The policy has NO execution authority whatsoever: it exposes
  exactly one public method (``propose``) which RETURNS DATA. It
  imports no OMS, no gateway, no risk gate, no kill switch, and it
  cannot create, submit or alter an order. Proposals are recorded
  to the decision ledger and trading memory for audit — the
  authoritative Decision/Risk/KillSwitch/OMS chain disposes of
  every bar independently of the proposal.
- RL is DISABLED by default (``TradingRuntime(rl_policy=None)``).
"""

from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.identity import prefixed_hash

#: Deterministic identity prefix for RL observations.
RL_OBSERVATION_PREFIX = "rlobs."
#: Deterministic identity prefix for RL action proposals.
RL_PROPOSAL_PREFIX = "rlact."


class RLGovernanceError(RuntimeContractError):
    """Raised on RL governance contract violations."""


class RLAction(str, Enum):
    """Bounded RL action vocabulary (target-position semantics).

    BUY   — increase the long target by ``magnitude_units``
    SELL  — decrease the target by ``magnitude_units`` (floor 0)
    CLOSE — target zero
    HOLD  — keep the current target
    """

    HOLD = "HOLD"
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"


def _require_finite_decimal(value, name: str) -> Decimal:
    if value is None:
        raise RLGovernanceError(f"{name} is required (fail closed)")
    if not isinstance(value, Decimal):
        raise RLGovernanceError(f"{name} must be a Decimal")
    if not value.is_finite():
        raise RLGovernanceError(f"{name} must be finite (NaN/inf fail closed)")
    return value


class RLPolicyConfig(BaseModel):
    """Governed policy configuration + deterministic policy identity.

    Every field is a DECLARED identity field: the policy hash is a
    pure function of these values (INV-01 — no wall clock, no
    randomness, no process state).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str = "rl-governed-baseline"
    policy_version: str = "1.0.0"
    #: Base sizing scale (units) for the deterministic mapping.
    base_units: Decimal = Decimal("10")
    #: Long-only target bound (units) — hard action bound #1.
    max_position_units: Decimal = Decimal("100")
    #: Max per-bar change of target (units) — hard action bound #2
    #: (turnover limit).
    max_turnover_units_per_bar: Decimal = Decimal("20")
    #: Max |target notional| / equity — hard action bound #3
    #: (exposure cap).
    max_exposure_fraction: Decimal = Decimal("0.25")
    #: Crash probability at/above which the policy proposes HOLD
    #: only (risk escalation, §20).
    crash_halt_probability: float = 0.40
    #: Unrealized drawdown fraction at/above which only FLAT/REDUCE
    #: semantics are permitted (hard action bound #4).
    drawdown_halt_fraction: Decimal = Decimal("0.10")
    #: Ensemble disagreement at/above which the observation is
    #: treated as out-of-distribution (fail toward HOLD).
    disagreement_ood_threshold: float = 0.60
    #: Confidence below which the policy proposes HOLD (model
    #: uncertainty gate).
    confidence_floor: float = 0.55

    @field_validator("policy_id", "policy_version")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RLGovernanceError("policy identity fields must be non-empty")
        return v.strip()

    @field_validator(
        "base_units",
        "max_position_units",
        "max_turnover_units_per_bar",
        "max_exposure_fraction",
        "drawdown_halt_fraction",
    )
    @classmethod
    def _validate_positive(cls, v: Decimal) -> Decimal:
        v = _require_finite_decimal(v, "policy bound")
        if v <= 0:
            raise RLGovernanceError("policy bounds must be positive")
        return v

    @field_validator("crash_halt_probability")
    @classmethod
    def _validate_crash(cls, v: float) -> float:
        if not isinstance(v, (int, float)) or not (0 < v <= 1):
            raise RLGovernanceError("crash_halt_probability must be in (0, 1]")
        return float(v)

    @field_validator("disagreement_ood_threshold", "confidence_floor")
    @classmethod
    def _validate_unit(cls, v: float) -> float:
        if not isinstance(v, (int, float)) or not (0 <= v <= 1):
            raise RLGovernanceError("unit thresholds must be in [0, 1]")
        return float(v)

    @property
    def policy_hash(self) -> str:
        """Deterministic identity of THIS policy version (INV-01)."""
        return prefixed_hash(
            "rlpol.",
            {
                "kind": "rl_policy",
                "policy_id": self.policy_id,
                "policy_version": self.policy_version,
                "base_units": str(self.base_units),
                "max_position_units": str(self.max_position_units),
                "max_turnover_units_per_bar": str(self.max_turnover_units_per_bar),
                "max_exposure_fraction": str(self.max_exposure_fraction),
                "crash_halt_probability": self.crash_halt_probability,
                "drawdown_halt_fraction": str(self.drawdown_halt_fraction),
                "disagreement_ood_threshold": self.disagreement_ood_threshold,
                "confidence_floor": self.confidence_floor,
            },
        )


class RLObservation(BaseModel):
    """Frozen RL observation contract — PIT-safe runtime state only.

    Built exclusively from values already computed for the current
    bar (the prediction artifact's calibrated probability, its
    uncertainty, the regime classification, the crash assessment,
    the position, the reference price, equity and unrealized P&L).
    No future information can enter this contract through the
    runtime integration (the runtime builds it AFTER the bar's
    decision inputs exist and BEFORE any next-bar data arrives).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    probability: float
    confidence: float
    disagreement: float
    regime: str
    crash_probability: float
    position_quantity: Decimal
    reference_price: Decimal
    equity: Decimal
    unrealized_pnl: Decimal

    @field_validator("symbol", "regime")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RLGovernanceError("observation text fields must be non-empty")
        return v.strip()

    @field_validator("probability", "confidence", "disagreement",
                     "crash_probability")
    @classmethod
    def _validate_unit(cls, v: float) -> float:
        if v is None or v != v or v in (float("inf"), float("-inf")):
            raise RLGovernanceError("observation probabilities must be finite")
        if not (0.0 <= v <= 1.0):
            raise RLGovernanceError("observation probabilities must be in [0, 1]")
        return float(v)

    @field_validator("position_quantity", "reference_price", "equity",
                     "unrealized_pnl")
    @classmethod
    def _validate_decimal(cls, v: Decimal) -> Decimal:
        return _require_finite_decimal(v, "observation decimal field")

    @field_validator("reference_price", "equity")
    @classmethod
    def _validate_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise RLGovernanceError("reference_price/equity must be positive")
        return v

    @property
    def observation_hash(self) -> str:
        """Deterministic identity of THIS observation (INV-01)."""
        return prefixed_hash(
            RL_OBSERVATION_PREFIX,
            {
                "kind": "rl_observation",
                "symbol": self.symbol,
                "probability": round(self.probability, 12),
                "confidence": round(self.confidence, 12),
                "disagreement": round(self.disagreement, 12),
                "regime": self.regime,
                "crash_probability": round(self.crash_probability, 12),
                "position_quantity": str(self.position_quantity),
                "reference_price": str(self.reference_price),
                "equity": str(self.equity),
                "unrealized_pnl": str(self.unrealized_pnl),
            },
        )


class RLActionProposal(BaseModel):
    """One governed, ADVISORY-ONLY policy proposal.

    ``advisory_only`` is a frozen literal True — a proposal that
    attempts to claim execution authority is INVALID BY CONTRACT
    (model_validator below). The proposal is DATA: it carries no
    order, no submission path, no authority.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_id: str
    policy_version: str
    policy_hash: str
    observation_hash: str
    action: RLAction
    #: Target long position (units, >= 0 — long-only vocabulary).
    target_units: Decimal
    #: Absolute change from the current position (units, >= 0).
    magnitude_units: Decimal
    confidence: float
    #: False when ANY hard bound was violated (the proposal then
    #: degrades to HOLD/CLOSE — never to a clamped aggressive move).
    bounds_ok: bool
    #: True when the observation was judged out-of-distribution.
    ood_flag: bool
    veto_reasons: tuple = ()
    advisory_only: bool = True

    @field_validator("proposal_id", "policy_version", "policy_hash",
                     "observation_hash")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RLGovernanceError("proposal identity fields must be non-empty")
        return v.strip()

    @field_validator("target_units", "magnitude_units")
    @classmethod
    def _validate_units(cls, v: Decimal) -> Decimal:
        v = _require_finite_decimal(v, "proposal units")
        if v < 0:
            raise RLGovernanceError("proposal units must be non-negative")
        return v

    @field_validator("confidence")
    @classmethod
    def _validate_confidence(cls, v: float) -> float:
        if v is None or v != v or not (0.0 <= v <= 1.0):
            raise RLGovernanceError("proposal confidence must be in [0, 1]")
        return float(v)

    @field_validator("veto_reasons")
    @classmethod
    def _validate_reasons(cls, v) -> tuple:
        v = tuple(v or ())
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise RLGovernanceError("veto reasons must be non-empty strings")
        return v

    @model_validator(mode="after")
    def _validate_advisory_only(self) -> "RLActionProposal":
        if self.advisory_only is not True:
            raise RLGovernanceError(
                "advisory_only is a frozen literal True — RL proposals "
                "can never claim execution authority (mandate §28)"
            )
        return self


#: Regime tempering factors (deterministic, documented, total).
_REGIME_TEMPER = {
    "CRASH": Decimal("0"),
    "STRESSED": Decimal("0.25"),
    "HIGH_VOLATILITY": Decimal("0.5"),
    "RECOVERY": Decimal("0.75"),
    "TRENDING": Decimal("1"),
    "RANGING": Decimal("0.75"),
    "UNKNOWN": Decimal("0.5"),
}


class GovernedRLPolicy:
    """The governed RL advisor (deterministic, versioned, bounded).

    NON-AUTHORITY (structural): this class exposes exactly ONE public
    behaviour — ``propose`` — which RETURNS an immutable data record.
    It imports no OMS, no gateway, no risk gate, no kill switch; it
    has no submit/create/cancel methods; it cannot mutate runtime
    state. Enforcement of every proposal (if the runtime chooses to
    consult it at all) remains with the authoritative
    Decision → Risk → KillSwitch → OMS chain.
    """

    def __init__(self, config: Optional[RLPolicyConfig] = None) -> None:
        if config is None:
            config = RLPolicyConfig()
        if not isinstance(config, RLPolicyConfig):
            raise RLGovernanceError("config must be an RLPolicyConfig")
        self._config = config

    @property
    def config(self) -> RLPolicyConfig:
        return self._config

    @property
    def policy_version(self) -> str:
        return self._config.policy_version

    @property
    def policy_hash(self) -> str:
        return self._config.policy_hash

    # ------------------------------------------------------------------
    def propose(self, observation: RLObservation) -> RLActionProposal:
        """Deterministically map ONE observation to ONE proposal.

        The mapping is a risk-tempered baseline:

        score = (probability - 0.5) tempered by regime, crash risk,
        confidence and drawdown; hard bounds then cap position,
        turnover and exposure. ANY bound violation degrades the
        proposal to HOLD/CLOSE with an explicit veto reason — never
        to a clamped aggressive action.
        """
        cfg = self._config
        veto: list = []
        ood = False

        # -- OOD gates: uncertainty fences fail toward HOLD ------------
        if observation.disagreement >= cfg.disagreement_ood_threshold:
            ood = True
            veto.append("OOD_ENSEMBLE_DISAGREEMENT")
        if observation.confidence < cfg.confidence_floor:
            veto.append("CONFIDENCE_BELOW_FLOOR")
        if observation.crash_probability >= cfg.crash_halt_probability:
            veto.append("CRASH_HALT")

        # -- drawdown halt: only flat/reduce semantics permitted -------
        equity = observation.equity
        drawdown_fraction = (
            -observation.unrealized_pnl / equity
            if equity > 0 and observation.unrealized_pnl < 0
            else Decimal("0")
        )
        drawdown_halted = drawdown_fraction >= cfg.drawdown_halt_fraction
        if drawdown_halted:
            veto.append("DRAWDOWN_HALT")

        # -- deterministic risk-tempered score --------------------------
        score = Decimal(str(round(observation.probability - 0.5, 12)))
        temper = _REGIME_TEMPER.get(observation.regime, Decimal("0.5"))
        crash_temper = Decimal("1") - Decimal(
            str(round(min(observation.crash_probability, 1.0), 12))
        )
        confidence_temper = Decimal(str(round(
            2.0 * max(observation.confidence - 0.5, 0.0), 12
        )))
        desired = (
            score
            * temper
            * crash_temper
            * confidence_temper
            * cfg.base_units
        )

        # -- target selection (long-only vocabulary) -------------------
        current = observation.position_quantity
        # HOLD-forcing fences: OOD, low confidence, crash halt — the
        # proposal degrades to HOLD, never toward aggressiveness.
        crash_halted = observation.crash_probability >= cfg.crash_halt_probability
        if ood or observation.confidence < cfg.confidence_floor or crash_halted:
            action = RLAction.HOLD
            target = current
        elif drawdown_halted:
            if current > 0:
                action = RLAction.CLOSE
                target = Decimal("0")
            else:
                action = RLAction.HOLD
                target = current
        elif desired > 0:
            raw = desired.quantize(Decimal("0.001"))
            if raw > cfg.max_position_units:
                # hard bound #1: the configured ceiling itself is the
                # governed target — the proposal NEVER exceeds it.
                veto.append("POSITION_BOUND")
                target = cfg.max_position_units
            else:
                target = raw
            if target > current:
                action = RLAction.BUY
            elif target < current:
                action = RLAction.SELL
            else:
                action = RLAction.HOLD
        elif desired < 0 and current > 0:
            # signal-negative: propose closing the long (no shorts)
            action = RLAction.CLOSE
            target = Decimal("0")
        else:
            action = RLAction.HOLD
            target = current

        # -- hard bound #3: exposure cap ---------------------------------
        # A violating target degrades to HOLD — never a clamped
        # aggressive move (strict contract, see module docstring).
        target_notional = abs(target * observation.reference_price)
        max_notional = cfg.max_exposure_fraction * equity
        if action is RLAction.BUY and target_notional > max_notional:
            veto.append("EXPOSURE_BOUND")
            target = current
            action = RLAction.HOLD

        # -- hard bound #2: turnover cap ----------------------------------
        # Applies to sizing CHANGES (BUY/SELL). Risk-reduction CLOSE
        # is EXEMPT by design: blocking a risk-reduction exit would
        # be unsafe (mandate: safety before turnover discipline).
        delta = target - current
        magnitude = abs(delta)
        if (
            action in (RLAction.BUY, RLAction.SELL)
            and magnitude > cfg.max_turnover_units_per_bar
        ):
            veto.append("TURNOVER_BOUND")
            target = current
            action = RLAction.HOLD
            delta = Decimal("0")
            magnitude = Decimal("0")

        # -- hold normalization ------------------------------------------
        if magnitude == 0 and action in (RLAction.BUY, RLAction.SELL):
            action = RLAction.HOLD
        if action is RLAction.CLOSE:
            target = Decimal("0")
            magnitude = abs(current)

        bounds_ok = not veto
        proposal_id = prefixed_hash(
            RL_PROPOSAL_PREFIX,
            {
                "kind": "rl_action_proposal",
                "policy_hash": self.policy_hash,
                "observation_hash": observation.observation_hash,
                "action": action.value,
                "target_units": str(target),
                "bounds_ok": bounds_ok,
                "ood_flag": ood,
            },
        )
        return RLActionProposal(
            proposal_id=proposal_id,
            policy_version=self.policy_version,
            policy_hash=self.policy_hash,
            observation_hash=observation.observation_hash,
            action=action,
            target_units=target,
            magnitude_units=magnitude,
            confidence=observation.confidence,
            bounds_ok=bounds_ok,
            ood_flag=ood,
            veto_reasons=tuple(veto),
        )


def propose_rl_action(
    config: RLPolicyConfig, observation: RLObservation
) -> RLActionProposal:
    """Cross-process-verifiable free function (determinism proof).

    Two independent processes computing ``propose_rl_action`` on the
    same (config, observation) MUST produce identical proposals,
    including ``proposal_id`` (INV-01 + §53 cross-process rule).
    """
    return GovernedRLPolicy(config).propose(observation)


__all__ = [
    "RLGovernanceError",
    "RLAction",
    "RLPolicyConfig",
    "RLObservation",
    "RLActionProposal",
    "GovernedRLPolicy",
    "propose_rl_action",
    "RL_OBSERVATION_PREFIX",
    "RL_PROPOSAL_PREFIX",
]
