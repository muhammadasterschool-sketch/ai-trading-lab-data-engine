"""Authoritative paper-readiness gate (pre-paper mandate §52/§53).

FAIL-CLOSED BY CONSTRUCTION:

- 23 mandatory component gates, each backed by an OBJECTIVE evidence
  object (component + check + evidence) — never a boolean flag from
  a passing test run alone;
- ALL must be TRUE: one FALSE ⇒ ``PAPER_READY = FALSE``;
- there is NO manual override, NO environment-variable bypass
  (``FORCE_PAPER_READY`` is structurally impossible — the gate does
  not read the environment at all), and NO hidden default-true
  (absent evidence defaults to FALSE).

The gate evaluates the THREE evidence classes the mandate
distinguishes: component evidence (wired and exercised), test
evidence (executed suite results), and governance evidence (human
decisions — which no code can fabricate).
"""

from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.runtime.contracts import RuntimeContractError

#: The 23 mandatory component gates (mandate §52).
GATE_NAMES = (
    "DATA_READY",
    "PIT_READY",
    "SEQUENCE_READY",
    "MODEL_READY",
    "PREDICTION_READY",
    "CALIBRATION_READY",
    "UNCERTAINTY_READY",
    "REGIME_READY",
    "CRASH_READY",
    "DECISION_READY",
    "RISK_READY",
    "KILLSWITCH_READY",
    "OMS_READY",
    "EXECUTION_READY",
    "PERSISTENCE_READY",
    "RECONCILIATION_READY",
    "LEDGER_READY",
    "MEMORY_READY",
    "OBSERVABILITY_READY",
    "RECOVERY_READY",
    "SECURITY_READY",
    "TESTS_READY",
    "GOVERNANCE_READY",
)


class ReadinessError(RuntimeContractError):
    """Raised on readiness-gate contract violations."""


class GateEvidence(BaseModel):
    """Objective evidence backing one component gate (§52)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate: str
    component: str
    check: str
    evidence: str
    passed: bool

    @field_validator("gate")
    @classmethod
    def _validate_gate(cls, v: str) -> str:
        if v not in GATE_NAMES:
            raise ReadinessError(
                f"unknown gate {v!r} (allowed: {sorted(GATE_NAMES)})"
            )
        return v

    @field_validator("component", "check", "evidence")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ReadinessError("evidence fields must be non-empty")
        return v.strip()


class ReadinessReport(BaseModel):
    """Full gate verdict — the PAPER_READY decision record (§52/§66)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidences: tuple
    paper_ready: bool
    failed_gates: tuple

    @field_validator("evidences")
    @classmethod
    def _validate_evidences(cls, v) -> tuple:
        if not v:
            raise ReadinessError("a readiness report requires evidence")
        return tuple(v)

    @model_validator(mode="after")
    def _validate_consistency(self) -> "ReadinessReport":
        provided = {e.gate for e in self.evidences}
        missing = set(GATE_NAMES) - provided
        if missing:
            raise ReadinessError(
                f"missing mandatory gate evidence: {sorted(missing)} "
                "(every gate requires an explicit evidence object — "
                "absent evidence is FALSE, never neutral)"
            )
        failed = tuple(e.gate for e in self.evidences if not e.passed)
        if self.paper_ready and failed:
            raise ReadinessError(
                f"PAPER_READY=TRUE with failing gates {failed} — "
                "impossible (fail-closed, mandate §53)"
            )
        return self


class PaperReadinessGate:
    """Evaluate the 23 mandatory gates from submitted evidence (§52)."""

    def __init__(self) -> None:
        self._evidence: dict = {}

    def submit(self, evidence: GateEvidence) -> None:
        """Register objective evidence for one gate (re-registration
        replaces — the LAST evidence wins, and it is always explicit)."""
        self._evidence[evidence.gate] = evidence

    def evaluate(self) -> ReadinessReport:
        """Compute the fail-closed verdict over ALL 23 gates."""
        evidences = []
        for gate in GATE_NAMES:
            ev = self._evidence.get(gate)
            if ev is None:
                # Absent evidence ⇒ explicit FALSE with the reason.
                evidences.append(
                    GateEvidence(
                        gate=gate,
                        component="missing",
                        check="evidence_submitted",
                        evidence="NO EVIDENCE SUBMITTED — absent evidence "
                                 "defaults to FALSE (fail closed, §53)",
                        passed=False,
                    )
                )
            else:
                evidences.append(ev)
        failed = tuple(e.gate for e in evidences if not e.passed)
        return ReadinessReport(
            evidences=tuple(evidences),
            paper_ready=not failed,
            failed_gates=failed,
        )

    @property
    def submitted(self) -> tuple:
        return tuple(self._evidence.values())


__all__ = [
    "GATE_NAMES",
    "ReadinessError",
    "GateEvidence",
    "ReadinessReport",
    "PaperReadinessGate",
]
