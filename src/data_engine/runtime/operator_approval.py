"""Trusted operator-approval evidence for human-dependency readiness
gates (P0-P3 master audit FIX-9 / B-P0-03).

WHY THIS MODULE EXISTS. The readiness-gate evidence bus
(:mod:`data_engine.runtime.readiness`) accepts ``GateEvidence``
objects whose ``passed`` flag and free-text ``evidence`` string are
CALLER-SUPPLIED. For component gates that is sound (the composition
root verifies those first-hand and its evidence is submitted LAST, so
it overrides any caller bundle entry). For the three HUMAN gates —
``REAL_DATA_READY``, ``OPERATIONAL_FEED_READY``, ``GOVERNANCE_READY``
— the caller-supplied bundle was previously the ONLY source, so any
code able to call ``compose_operational_session`` could mark a human
gate passed with arbitrary free text (B-P0-03, proven by the old test
helper that fabricated ``passed=True`` for all 32 gates).

TRUST BOUNDARY (same discipline as keyed-MAC ledger custody, F-25):

- The operator provisions an APPROVAL SIGNING KEY through the
  environment channel (``OPERATOR_APPROVAL_MAC_KEY`` or
  ``OPERATOR_APPROVAL_MAC_KEY_FILE``) at launch time. The repository
  NEVER contains key material; it is never logged and never appears in
  ``repr``/``str`` (only a truncated SHA-256 fingerprint ``key_id``).
- Every approval is a TYPED ``OperatorApprovalRecord`` (principal,
  decision, gate scope, optional instrument/source scope, issued_at,
  expires_at, artifact digest, reason) signed with HMAC-SHA256 over
  its canonical serialization.
- The composition root RE-VERIFIES every human-gate approval against
  the environment-provisioned key at compose time (expiry, scope,
  decision, digest, signature). A caller that cannot produce the
  operator's key cannot forge a passing human gate — fabricating
  ``passed=True`` free-text evidence now fails closed with the stable
  reason code ``E_EVIDENCE_UNTRUSTED``.

FAIL-CLOSED VERIFICATION (stable reason codes, never secrets):

===============================  ==========================================
reason code                       meaning
===============================  ==========================================
``E_APPROVAL_MISSING``            required approval absent from the bundle
``E_APPROVAL_MALFORMED``          record failed typed validation
``E_APPROVAL_UNKNOWN_GATE``       record targets a gate that does not exist
``E_APPROVAL_NOT_HUMAN_GATE``     record targets a non-human gate (approval
                                  cannot substitute for first-hand code
                                  evidence)
``E_APPROVAL_BAD_DECISION``       decision is not APPROVE
``E_APPROVAL_SCOPE_MISMATCH``     instrument/source scope does not match the
                                  session's scope
``E_APPROVAL_DIGEST_MISMATCH``    artifact digest does not match the
                                  session config digest
``E_APPROVAL_NOT_YET_VALID``      issued_at is in the future (clock skew or
                                  forgery)
``E_APPROVAL_EXPIRED``            expires_at is in the past
``E_APPROVAL_SIGNATURE_INVALID``  HMAC verification failed
``E_APPROVAL_KEY_UNAVAILABLE``    approval key not provisioned through the
                                  environment channel
``E_EVIDENCE_UNTRUSTED``          human-gate evidence is not a verified
                                  TrustedGateEvidence
===============================  ==========================================

This module reads the environment ONLY inside
:func:`OperatorApprovalKey.from_environment` (the operator
provisioning channel). Readiness gates and every other runtime
component remain environment-free (structural tests hold).
"""

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.pit.serialization import canonical_serialize
from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.readiness import GATE_NAMES, GateEvidence

__all__ = [
    "APPROVAL_KINDS",
    "OPERATOR_APPROVAL_ENV_KEY",
    "OPERATOR_APPROVAL_ENV_KEY_FILE",
    "MIN_APPROVAL_KEY_BYTES",
    "HUMAN_GATES",
    "OperatorApprovalError",
    "OperatorApprovalRecord",
    "OperatorApprovalKey",
    "ApprovalVerification",
    "TrustedGateEvidence",
    "approval_signature_payload",
    "sign_approval",
    "verify_approval",
    "build_trusted_evidence",
    "verify_human_gate_evidence",
]

#: Environment channel for direct key provisioning (hex or raw bytes).
#: NEVER a default value — absence raises (fail closed).
OPERATOR_APPROVAL_ENV_KEY = "OPERATOR_APPROVAL_MAC_KEY"

#: Environment channel for indirect provisioning: absolute path to a
#: key file OUTSIDE the repository (custody transfer by file).
OPERATOR_APPROVAL_ENV_KEY_FILE = "OPERATOR_APPROVAL_MAC_KEY_FILE"

#: Minimum decoded key length (bytes) — HMAC-SHA256 strength floor
#: (same floor as keyed-MAC ledger custody, F-25).
MIN_APPROVAL_KEY_BYTES = 32

#: Fingerprint length (hex chars) of the approval key id.
_KEY_ID_LEN = 16

#: The auditable approval kinds an operator may record (Task 7 of the
#: P0-P3 master audit: source approval, paper-environment
#: authorization, risk-limit changes, kill-switch reset, soak
#: start/stop — plus the recorded-evidence kind used for readiness
#: bundles).
APPROVAL_KINDS = (
    "SOURCE_APPROVAL",
    "PAPER_ENVIRONMENT_AUTHORIZATION",
    "RISK_LIMIT_CHANGE",
    "KILLSWITCH_RESET",
    "SOAK_START",
    "SOAK_STOP",
    "RECORDED_EVIDENCE",
)

#: The gates ONLY a human decision can satisfy (mirrors
#: ``composition.HUMAN_EVIDENCE_GATES`` — re-declared locally to keep
#: this module import-light and avoid a circular import; the pin test
#: ``test_operator_approval.py::test_human_gate_sets_agree`` enforces
#: the two definitions cannot drift).
HUMAN_GATES = frozenset({
    "REAL_DATA_READY",
    "OPERATIONAL_FEED_READY",
    "GOVERNANCE_READY",
})

#: Approval kinds that are CONTROL records for other audited actions
#: (risk-limit changes, kill-switch reset, soak start/stop) rather
#: than readiness-evidence approvals.
_CONTROL_KINDS = frozenset({
    "RISK_LIMIT_CHANGE",
    "KILLSWITCH_RESET",
    "SOAK_START",
    "SOAK_STOP",
})


class OperatorApprovalError(RuntimeContractError):
    """Raised on operator-approval trust violations. ``reason_code``
    is one of the stable ``E_APPROVAL_*`` / ``E_EVIDENCE_*`` codes
    above; ``detail`` never contains key material."""

    def __init__(self, reason_code: str, detail: str) -> None:
        super().__init__(f"[{reason_code}] {detail}")
        self.reason_code = reason_code
        self.detail = detail


def _ensure_utc(value: datetime, *, what: str) -> datetime:
    """Normalize a datetime to UTC (a naive value is interpreted as
    UTC — deterministic; an aware value is converted). Every
    comparison in this module runs in UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class OperatorApprovalRecord(BaseModel):
    """One auditable human decision (Task 7): identifies the approving
    principal, the decision, the gate scope (and optional
    instrument/source scope), validity window, the artifact/config
    digest the decision covers, and the reason. Frozen and
    ``extra="forbid"`` — an approval is exactly these fields or it is
    malformed (fail closed)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str
    approval_kind: str
    principal: str
    decision: str
    gate: str
    scope: str = "*"
    issued_at: datetime
    expires_at: datetime
    artifact_digest: str = ""
    reason: str

    @field_validator("record_id", "principal", "reason")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise OperatorApprovalError(
                "E_APPROVAL_MALFORMED",
                "record_id/principal/reason must be non-empty strings",
            )
        return v.strip()

    @field_validator("approval_kind")
    @classmethod
    def _kind(cls, v: str) -> str:
        if v not in APPROVAL_KINDS:
            raise OperatorApprovalError(
                "E_APPROVAL_MALFORMED",
                f"unknown approval_kind {v!r} (allowed: {APPROVAL_KINDS})",
            )
        return v

    @field_validator("decision")
    @classmethod
    def _decision(cls, v: str) -> str:
        if v not in ("APPROVE", "REJECT"):
            raise OperatorApprovalError(
                "E_APPROVAL_MALFORMED",
                f"decision must be APPROVE or REJECT (got {v!r})",
            )
        return v

    @field_validator("gate")
    @classmethod
    def _gate(cls, v: str) -> str:
        if v not in GATE_NAMES:
            raise OperatorApprovalError(
                "E_APPROVAL_UNKNOWN_GATE",
                f"approval targets unknown gate {v!r}",
            )
        return v

    @field_validator("issued_at", "expires_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise OperatorApprovalError(
                "E_APPROVAL_MALFORMED",
                "issued_at/expires_at must be timezone-aware datetimes "
                "(UTC recommended — a naive timestamp is ambiguous)",
            )
        return v

    @model_validator(mode="after")
    def _cross_fields(self) -> "OperatorApprovalRecord":
        if self.expires_at <= self.issued_at:
            raise OperatorApprovalError(
                "E_APPROVAL_MALFORMED",
                f"expires_at must be after issued_at (record "
                f"{self.record_id!r})",
            )
        if (
            self.gate not in HUMAN_GATES
            and self.approval_kind not in _CONTROL_KINDS
        ):
            # Readiness approvals only make sense for human gates;
            # control approvals (risk/kill/soak) are recorded for
            # OTHER audited actions and may reference any gate they
            # affect.
            raise OperatorApprovalError(
                "E_APPROVAL_NOT_HUMAN_GATE",
                f"approval record {self.record_id!r} targets "
                f"{self.gate!r} which is not a human-dependency gate "
                f"({sorted(HUMAN_GATES)}) — an approval cannot "
                "substitute for first-hand code evidence",
            )
        return self


class OperatorApprovalKey:
    """The operator's approval-signing key (HMAC-SHA256). Follows the
    keyed-MAC custody discipline: material NEVER exposed via
    repr/str/logs; only a truncated fingerprint ``key_id``."""

    __slots__ = ("_material", "_key_id", "_status")

    def __init__(self, material: bytes, *, status: str = "OPERATIONAL") -> None:
        if not isinstance(material, (bytes, bytearray)) or len(material) < MIN_APPROVAL_KEY_BYTES:
            raise OperatorApprovalError(
                "E_APPROVAL_MALFORMED",
                f"approval key material must be at least "
                f"{MIN_APPROVAL_KEY_BYTES} bytes (got "
                f"{len(material) if isinstance(material, (bytes, bytearray)) else type(material).__name__})",
            )
        self._material = bytes(material)
        self._key_id = "appkey-" + hashlib.sha256(self._material).hexdigest()[:_KEY_ID_LEN]
        self._status = status

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def status(self) -> str:
        return self._status

    @classmethod
    def from_environment(cls) -> "OperatorApprovalKey":
        """Load the approval key from the operator environment channel
        (direct hex/raw variable or absolute key-file path). Fail
        closed when neither is provisioned. The ONLY environment read
        in this module (structural test pins this)."""
        raw = os.environ.get(OPERATOR_APPROVAL_ENV_KEY)
        file_path = os.environ.get(OPERATOR_APPROVAL_ENV_KEY_FILE)
        if raw is None and file_path is None:
            raise OperatorApprovalError(
                "E_APPROVAL_KEY_UNAVAILABLE",
                "no operator approval key provisioned: set "
                f"{OPERATOR_APPROVAL_ENV_KEY} (hex or raw) or "
                f"{OPERATOR_APPROVAL_ENV_KEY_FILE} (absolute path to a "
                "key file outside the repository) through the "
                "documented operator secure channel (see "
                "docs/PAPER_OPERATOR_RUNBOOK.md)",
            )
        if raw is not None:
            material = cls._decode_material(raw, OPERATOR_APPROVAL_ENV_KEY)
            return cls(material)
        path = Path(file_path)
        if not path.is_absolute():
            raise OperatorApprovalError(
                "E_APPROVAL_KEY_UNAVAILABLE",
                f"{OPERATOR_APPROVAL_ENV_KEY_FILE} must be an ABSOLUTE "
                f"path outside the repository (got {file_path!r})",
            )
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise OperatorApprovalError(
                "E_APPROVAL_KEY_UNAVAILABLE",
                f"approval key file unreadable: {type(exc).__name__} "
                "(the file must exist and be readable by this process)",
            ) from exc
        material = cls._decode_material(text, str(path))
        return cls(material)

    @staticmethod
    def _decode_material(text: str, source: str) -> bytes:
        stripped = text.strip()
        try:
            material = bytes.fromhex(stripped)
        except ValueError:
            material = stripped.encode("utf-8")
        if len(material) < MIN_APPROVAL_KEY_BYTES:
            raise OperatorApprovalError(
                "E_APPROVAL_MALFORMED",
                f"approval key from {source} is below the "
                f"{MIN_APPROVAL_KEY_BYTES}-byte strength floor — "
                "provision a genuinely strong key",
            )
        return material

    def sign(self, data: bytes) -> str:
        """HMAC-SHA256 over ``data`` with this key (hex digest)."""
        return hmac.new(self._material, data, hashlib.sha256).hexdigest()

    def verify(self, data: bytes, mac: str) -> bool:
        """Constant-time MAC verification (``hmac.compare_digest``)."""
        if not isinstance(mac, str) or len(mac) != 64:
            return False
        expected = self.sign(data)
        return hmac.compare_digest(expected, mac)

    def __repr__(self) -> str:  # pragma: no cover - safety surface
        return (
            f"OperatorApprovalKey(key_id={self._key_id!r}, "
            "material=MASKED, status=MASKED)"
        )

    __str__ = __repr__


def approval_signature_payload(record: OperatorApprovalRecord) -> bytes:
    """Canonical bytes covered by the approval signature: every
    identity-bearing field of the record (the signature covers the
    FULL decision — principal, kind, decision, gate, scope, validity
    window, artifact digest and reason)."""
    return canonical_serialize(
        {
            "record_id": record.record_id,
            "approval_kind": record.approval_kind,
            "principal": record.principal,
            "decision": record.decision,
            "gate": record.gate,
            "scope": record.scope,
            "issued_at": record.issued_at,
            "expires_at": record.expires_at,
            "artifact_digest": record.artifact_digest,
            "reason": record.reason,
        }
    )


def sign_approval(
    record: OperatorApprovalRecord, key: OperatorApprovalKey
) -> str:
    """Operator-side signing helper (the operator's launcher signs
    approval records; the composition root only verifies)."""
    return key.sign(approval_signature_payload(record))


def verify_approval(
    record: OperatorApprovalRecord,
    signature: str,
    key: OperatorApprovalKey,
    *,
    as_of: datetime,
    expected_gate: str,
    expected_scope: str = "*",
    expected_digest: str = "",
) -> "ApprovalVerification":
    """Full fail-closed verification of one approval record.

    Checks, in order: gate scope, decision, validity window (as_of
    strictly inside [issued_at, expires_at)), optional session-scope
    match (``"*"`` in the record approves any scope), optional
    artifact-digest pin, and the HMAC signature. Returns an
    :class:`ApprovalVerification` receipt; raises
    :class:`OperatorApprovalError` with the stable reason code on any
    failure. NEVER raises with key material in the message."""
    as_of = _ensure_utc(as_of, what="as_of")
    if record.gate != expected_gate:
        raise OperatorApprovalError(
            "E_APPROVAL_SCOPE_MISMATCH",
            f"approval {record.record_id!r} is scoped to gate "
            f"{record.gate!r}, not {expected_gate!r}",
        )
    if record.decision != "APPROVE":
        raise OperatorApprovalError(
            "E_APPROVAL_BAD_DECISION",
            f"approval {record.record_id!r} decision is "
            f"{record.decision!r} — only APPROVE can satisfy a gate",
        )
    if as_of < record.issued_at:
        raise OperatorApprovalError(
            "E_APPROVAL_NOT_YET_VALID",
            f"approval {record.record_id!r} is not valid until "
            f"{record.issued_at.isoformat()} (as_of="
            f"{as_of.isoformat()})",
        )
    if as_of >= record.expires_at:
        raise OperatorApprovalError(
            "E_APPROVAL_EXPIRED",
            f"approval {record.record_id!r} expired at "
            f"{record.expires_at.isoformat()} (as_of="
            f"{as_of.isoformat()})",
        )
    if record.scope != "*" and record.scope != expected_scope:
        raise OperatorApprovalError(
            "E_APPROVAL_SCOPE_MISMATCH",
            f"approval {record.record_id!r} scope {record.scope!r} does "
            f"not cover the session scope {expected_scope!r}",
        )
    if expected_digest and record.artifact_digest not in ("", expected_digest):
        # An empty artifact_digest in the record means "unpinned";
        # a pinned record MUST match the expected digest exactly.
        raise OperatorApprovalError(
            "E_APPROVAL_DIGEST_MISMATCH",
            f"approval {record.record_id!r} pins artifact digest "
            f"{record.artifact_digest[:16]!r}... which does not match "
            "the session config digest (stale or wrong-scope approval)",
        )
    if not key.verify(approval_signature_payload(record), signature):
        raise OperatorApprovalError(
            "E_APPROVAL_SIGNATURE_INVALID",
            f"approval {record.record_id!r} failed HMAC verification "
            f"under key {key.key_id} (fabricated, tampered, or signed "
            "under a different key)",
        )
    return ApprovalVerification(
        record_id=record.record_id,
        gate=record.gate,
        verified_at=as_of,
        key_id=key.key_id,
        signature_hex_prefix=signature[:12],
    )


class ApprovalVerification(BaseModel):
    """Receipt proving a record was verified (attributable,
    timestamped; contains NO key material — only the key fingerprint
    and a 12-char signature prefix for cross-referencing operator
    logs)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str
    gate: str
    verified_at: datetime
    key_id: str
    signature_hex_prefix: str


class TrustedGateEvidence(GateEvidence):
    """GateEvidence for a HUMAN gate, carrying the validated approval
    record, its signature, and the verification receipt. Construct via
    :func:`build_trusted_evidence` (which verifies) — the composition
    root re-verifies at compose time regardless, so a hand-crafted
    instance cannot shortcut the trust boundary.

    Subclass note: pydantic v2 subclassing of GateEvidence with an
    added ``extra="forbid"`` field set works because GateEvidence
    declares ``model_config = ConfigDict(frozen=True, extra="forbid")``
    and the subclass only ADDS fields with defaults (records/signature
    always provided by the builder)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approval_record: OperatorApprovalRecord
    approval_signature: str
    verification: ApprovalVerification

    @field_validator("approval_signature")
    @classmethod
    def _sig_shape(cls, v: str) -> str:
        if not isinstance(v, str) or len(v) != 64:
            raise OperatorApprovalError(
                "E_APPROVAL_SIGNATURE_INVALID",
                "approval signature must be a 64-char hex MAC",
            )
        return v


def build_trusted_evidence(
    record: OperatorApprovalRecord,
    signature: str,
    key: OperatorApprovalKey,
    *,
    as_of: datetime,
    expected_scope: str = "*",
    expected_digest: str = "",
) -> TrustedGateEvidence:
    """Verify one approval record and build the TRUSTED evidence
    object for its human gate. Raises :class:`OperatorApprovalError`
    (stable reason code) on any failure — there is no path that
    forces ``passed=True`` without a verified approval."""
    receipt = verify_approval(
        record,
        signature,
        key,
        as_of=as_of,
        expected_gate=record.gate,
        expected_scope=expected_scope,
        expected_digest=expected_digest,
    )
    return TrustedGateEvidence(
        gate=record.gate,
        component="operator-approval",
        check="verify_operator_approval",
        evidence=(
            f"SIGNED operator approval {record.record_id} "
            f"(kind={record.approval_kind} principal={record.principal} "
            f"scope={record.scope} issued={record.issued_at.isoformat()} "
            f"expires={record.expires_at.isoformat()} "
            f"digest_pin={record.artifact_digest[:16] or 'unpinned'}... "
            f"verified_at={receipt.verified_at.isoformat()} "
            f"key={receipt.key_id} reason={record.reason})"
        ),
        passed=True,
        approval_record=record,
        approval_signature=signature,
        verification=receipt,
    )


def verify_human_gate_evidence(
    evidence: GateEvidence,
    *,
    key: Optional[OperatorApprovalKey],
    as_of: datetime,
    expected_scope: str = "*",
    expected_digest: str = "",
) -> TrustedGateEvidence:
    """Composition-root entry point: decide whether ONE human-gate
    evidence object is trusted.

    - A plain :class:`GateEvidence` (free text, caller-supplied
      ``passed``) is REFUSED with ``E_EVIDENCE_UNTRUSTED`` — the
      B-P0-03 regression surface.
    - A :class:`TrustedGateEvidence` is RE-VERIFIED against the
      operator key (signature, expiry at ``as_of``, scope, digest) —
      hand-crafting the subclass without the key does not help.

    Returns the re-verified trusted evidence; raises otherwise."""
    if not isinstance(evidence, TrustedGateEvidence):
        raise OperatorApprovalError(
            "E_EVIDENCE_UNTRUSTED",
            f"gate {getattr(evidence, 'gate', '?')!r} is a human-"
            "dependency gate: plain caller-supplied GateEvidence "
            "(free-text, caller-set passed flag) cannot satisfy it — "
            "supply a SIGNED OperatorApprovalRecord bundle built "
            "through build_trusted_evidence (see "
            "runtime/operator_approval.py)",
        )
    if key is None:
        raise OperatorApprovalError(
            "E_APPROVAL_KEY_UNAVAILABLE",
            "trusted evidence present but no operator approval key is "
            "provisioned — the composition root cannot re-verify "
            "signatures (provision OPERATOR_APPROVAL_MAC_KEY or "
            "OPERATOR_APPROVAL_MAC_KEY_FILE through the operator "
            "secure channel)",
        )
    # Re-verify from first principles — never trust the embedded
    # receipt alone (the caller controls the object graph; the key
    # controls the verdict).
    verify_approval(
        evidence.approval_record,
        evidence.approval_signature,
        key,
        as_of=as_of,
        expected_gate=evidence.gate,
        expected_scope=expected_scope,
        expected_digest=expected_digest,
    )
    return evidence
