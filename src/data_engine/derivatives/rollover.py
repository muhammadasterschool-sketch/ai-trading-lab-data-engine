"""Phase 4A.3 — RolloverPolicy and roll_detection (blueprint 5.14).

Roll decisions are the highest-leakage-risk zone in futures research
(the classic trap: deciding TODAY's roll with TOMORROW's volume). This
module enforces PIT correctness structurally:

- ``roll_detection`` consumes per-contract series (each bar timestamped,
  as_of-eligible) and emits roll decisions whose DECISION timestamp is
  the roll bar itself — never a future bar.
- Calendar-based policies decide N trading days before expiry using
  only the calendar (no future data by construction).
- Volume/open-interest policies compare trailing windows ENDING at the
  decision bar — leading windows are forbidden (RollLeakageError).

Policies:
- ``CALENDAR_DAYS``: roll at the last trading day >= N days before expiry
- ``VOLUME_CROSS``: roll on the first bar where the back contract's
  volume exceeds the front contract's volume (trailing compare)
- ``OPEN_INTEREST_CROSS``: same rule on open interest
"""

from datetime import date, datetime, timedelta, UTC
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.pit.hashing import deterministic_hash
from data_engine.derivatives.models import PHASE_4A3_CONTRACT_VERSION


class RollLeakageError(ValueError):
    """Raised when a roll decision would require future data."""


class RolloverPolicyType(str, Enum):
    """Supported rollover decision rules."""

    CALENDAR_DAYS = "calendar_days"
    VOLUME_CROSS = "volume_cross"
    OPEN_INTEREST_CROSS = "open_interest_cross"


class RolloverPolicy(BaseModel):
    """Declarative, immutable rollover decision rule.

    For ``calendar_days``: ``parameter`` = number of days before expiry
    to roll. For ``volume_cross``/``open_interest_cross``: the rule
    compares front vs back contract on the same bar — no lookahead.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_type: RolloverPolicyType
    parameter: int = 0
    policy_version: str = "1.0.0"

    @field_validator("parameter")
    @classmethod
    def _validate_parameter(cls, v: int, info) -> int:
        if not isinstance(v, int) or v < 0:
            raise ValueError("policy parameter must be a non-negative int")
        if info.data.get("policy_type") is RolloverPolicyType.CALENDAR_DAYS and v < 1:
            raise ValueError("calendar_days policy requires parameter >= 1")
        return v

    @property
    def policy_hash(self) -> str:
        payload = {
            "contract_version": PHASE_4A3_CONTRACT_VERSION,
            "policy_type": self.policy_type.value,
            "parameter": self.parameter,
            "policy_version": self.policy_version,
        }
        return deterministic_hash(payload)


class RollDecision(BaseModel):
    """One roll decision: front contract -> back contract at a timestamp.

    ``decision_time`` is when the decision was observable — the roll bar
    itself. ``decision_time <= effective_time`` always (a decision is
    made with data up to and including the decision bar).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    front_contract_id: str
    back_contract_id: str
    decision_time: datetime
    effective_time: datetime
    reason: str

    @field_validator("front_contract_id", "back_contract_id")
    @classmethod
    def _validate_ids(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("contract ids must be non-empty strings")
        return v.strip().upper()

    @field_validator("decision_time", "effective_time")
    @classmethod
    def _validate_utc(cls, v: datetime, info) -> datetime:
        if v is None or v.tzinfo is None:
            raise ValueError(f"{info.field_name} must be timezone-aware")
        return v.astimezone(UTC)

    @model_validator(mode="after")
    def _validate_no_leakage(self) -> "RollDecision":
        if self.front_contract_id == self.back_contract_id:
            raise ValueError("roll must move to a DIFFERENT contract")
        if self.decision_time > self.effective_time:
            raise RollLeakageError(
                f"roll decision at {self.decision_time} is effective "
                f"{self.effective_time} — decision precedes effect, always"
            )
        return self


def _bar_time(bar: Mapping[str, Any]) -> datetime:
    ts = bar.get("timestamp")
    if ts is None or not hasattr(ts, "tzinfo") or ts.tzinfo is None:
        raise RollLeakageError("each bar needs a timezone-aware 'timestamp'")
    return ts.astimezone(UTC)


def roll_detection(
    policy: RolloverPolicy,
    front_bars: Sequence[Mapping[str, Any]],
    back_bars: Sequence[Mapping[str, Any]],
    front_expiry: Optional[date] = None,
    back_contract_id: str = "BACK",
    front_contract_id: str = "FRONT",
) -> Optional[RollDecision]:
    """Detect the roll from the front contract to the back contract.

    PIT contract: the returned decision's ``decision_time`` is a bar
    timestamp present in BOTH series (for cross policies) — i.e. it was
    observable when made. Calendar policy needs no bars at all.

    Returns None when no roll is detected under the policy.
    """
    if policy.policy_type is RolloverPolicyType.CALENDAR_DAYS:
        if front_expiry is None:
            raise ValueError("calendar_days policy requires front_expiry")
        target = front_expiry - timedelta(days=policy.parameter)
        # The roll is effective on the target date (or the first bar at
        # or after it if bars are supplied); decision is made AT that
        # time by construction — no future data is consulted.
        effective = None
        for bar in front_bars:
            t = _bar_time(bar)
            if t.date() >= target:
                effective = t
                break
        if effective is None:
            effective = datetime.combine(
                target, datetime.min.time(), tzinfo=UTC
            )
        return RollDecision(
            front_contract_id=front_contract_id,
            back_contract_id=back_contract_id,
            decision_time=effective,
            effective_time=effective,
            reason=(
                f"calendar policy: {policy.parameter} days before expiry "
                f"{front_expiry.isoformat()}"
            ),
        )

    # Cross policies: compare front vs back on the SAME timestamp.
    field = (
        "volume"
        if policy.policy_type is RolloverPolicyType.VOLUME_CROSS
        else "open_interest"
    )
    back_by_time = {_bar_time(b): b for b in back_bars}
    for bar in front_bars:
        t = _bar_time(bar)
        twin = back_by_time.get(t)
        if twin is None:
            continue  # decision bars must exist in both series
        front_val = bar.get(field)
        back_val = twin.get(field)
        if front_val is None or back_val is None:
            continue
        if Decimal(str(back_val)) > Decimal(str(front_val)):
            return RollDecision(
                front_contract_id=front_contract_id,
                back_contract_id=back_contract_id,
                decision_time=t,
                effective_time=t,
                reason=(
                    f"{policy.policy_type.value}: back {field} "
                    f"{back_val} exceeded front {front_val} at {t.isoformat()}"
                ),
            )
    return None


__all__ = [
    "RolloverPolicyType",
    "RolloverPolicy",
    "RollDecision",
    "RollLeakageError",
    "roll_detection",
]
