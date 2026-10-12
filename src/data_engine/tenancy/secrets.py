"""Per-tenant secret vault contract (Batch 4).

Rules encoded:

- Secrets are addressed by OPAQUE :class:`SecretRef` handles
  (tenant + key). A ref carries a SHA-256 *fingerprint* of the
  value for integrity/redaction-test purposes — the fingerprint is
  a one-way digest, never the value.
- ``reveal`` is AUTHORIZATION-GATED: the caller must supply an
  :class:`AccessDecision` that ALLOWED ``SECRET_REVEAL`` for the
  exact ref's resource uid, produced by the authoritative
  :class:`data_engine.tenancy.authorization.AuthorizationPolicy`.
  No allow, no value — fail closed.
- Secret VALUES never appear in: audit events, decisions,
  exceptions, ``repr``/``str``. The vault's own repr is redacted.
- Cross-tenant storage collisions are refused (one namespace per
  tenant — the isolation is structural, not just policy-level).

FOUNDATION SCOPE: in-memory vault only (values never persisted,
never transmitted). A real KMS/OS-keychain-backed vault for the
per-user VPS deployment is future, separately-reviewed work.
"""

import hashlib
from datetime import datetime, UTC
from typing import Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.tenancy.authorization import AccessDecision
from data_engine.tenancy.identity import TENANT_ID_PATTERN, IdentityError


class SecretVaultError(ValueError):
    """Raised on vault contract violations (fail closed)."""


#: Redaction placeholder (never a legal secret value — see store()).
REDACTED = "<redacted>"


class SecretRef(BaseModel):
    """Opaque handle for one tenant secret (no value material)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str
    key: str
    fingerprint: str  # sha256 hex of the value (integrity, not value)
    created_at: datetime

    @field_validator("tenant_id", "key")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise SecretVaultError("secret tenant/key must be non-empty")
        return v.strip()

    @field_validator("tenant_id")
    @classmethod
    def _validate_tenant(cls, v: str) -> str:
        if not TENANT_ID_PATTERN.match(v):
            raise IdentityError(
                f"tenant_id {v!r} must match {TENANT_ID_PATTERN.pattern}"
            )
        return v

    @field_validator("fingerprint")
    @classmethod
    def _validate_fingerprint(cls, v: str) -> str:
        if not isinstance(v, str) or len(v) != 64 \
                or any(c not in "0123456789abcdef" for c in v.lower()):
            raise SecretVaultError(
                "fingerprint must be a 64-hex sha256 digest"
            )
        return v.lower()

    def __repr__(self) -> str:  # defensive: never render internals
        return (
            f"SecretRef(tenant_id={self.tenant_id!r}, "
            f"key={self.key!r}, fingerprint={self.fingerprint[:8]}...)"
        )


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class TenantSecretVault:
    """The per-tenant secret vault (in-memory foundation).

    Storage is NAMESPACED per tenant: storing under tenant A can
    never read or overwrite tenant B's entries — cross-tenant
    isolation is structural (separate namespaces), and the
    authorization gate makes it policy-enforced too.
    """

    def __init__(self) -> None:
        self._values: Dict[Tuple[str, str], str] = {}

    def __repr__(self) -> str:
        return (
            f"TenantSecretVault(entries={len(self._values)}, "
            f"values={REDACTED!r})"
        )

    def __str__(self) -> str:  # same redaction as repr
        return repr(self)

    def store(self, tenant_id: str, key: str, value: str,
              at: Optional[datetime] = None) -> SecretRef:
        if not isinstance(value, str) or not value.strip():
            raise SecretVaultError("secret value must be non-empty")
        if value == REDACTED:
            raise SecretVaultError(
                "the redaction placeholder is never a legal secret value"
            )
        if "\x00" in value:
            raise SecretVaultError("secret values must not contain NUL")
        now = at.astimezone(UTC) if at is not None else datetime.now(UTC)
        slot = (tenant_id, key)
        if slot in self._values:
            raise SecretVaultError(
                f"secret {key!r} of tenant {tenant_id!r} already exists — "
                "rotation replaces explicitly, never silently"
            )
        self._values[slot] = value
        return SecretRef(
            tenant_id=tenant_id,
            key=key,
            fingerprint=_fingerprint(value),
            created_at=now,
        )

    def rotate(self, tenant_id: str, key: str, value: str,
               at: Optional[datetime] = None) -> SecretRef:
        """Explicit rotation (replace) of an existing secret."""
        if (tenant_id, key) not in self._values:
            raise SecretVaultError(
                f"secret {key!r} of tenant {tenant_id!r} does not exist — "
                "nothing to rotate"
            )
        if not isinstance(value, str) or not value.strip() \
                or value == REDACTED:
            raise SecretVaultError("rotation value must be a legal secret")
        self._values[(tenant_id, key)] = value
        now = at.astimezone(UTC) if at is not None else datetime.now(UTC)
        return SecretRef(
            tenant_id=tenant_id,
            key=key,
            fingerprint=_fingerprint(value),
            created_at=now,
        )

    def reveal(
        self,
        ref: SecretRef,
        decision: AccessDecision,
    ) -> str:
        """Reveal one secret's value — ONLY with a PRIOR ALLOWING
        authorization decision for SECRET_REVEAL on this exact ref.

        The decision must reference the same resource (tenant + key
        mapped to the vault's resource uid) and be an ALLOW; the
        vault itself re-checks the tenant binding (defence in
        depth: a decision for tenant A's store never reveals tenant
        B's value).
        """
        from data_engine.tenancy.resources import ResourceKind, ResourceUid
        if not isinstance(decision, AccessDecision):
            raise SecretVaultError(
                "reveal requires the AccessDecision from the "
                "authoritative AuthorizationPolicy"
            )
        expected_uid = ResourceUid(
            kind=ResourceKind.SECRET_STORE,
            tenant_id=ref.tenant_id,
            name=ref.key,
        )
        if decision.resource != expected_uid:
            raise SecretVaultError(
                "decision does not reference this secret's resource — "
                "refusing to reveal (fail closed)"
            )
        if not decision.allowed:
            raise SecretVaultError(
                f"authorization DENIED ({decision.reason}) — no reveal"
            )
        if decision.authenticated_tenant != ref.tenant_id:
            raise SecretVaultError(
                "decision tenant binding does not match the secret's "
                "tenant — cross-tenant reveal refused (fail closed)"
            )
        value = self._values.get((ref.tenant_id, ref.key))
        if value is None:
            raise SecretVaultError(
                f"secret {ref.key!r} of tenant {ref.tenant_id!r} is not "
                "stored (deny-by-default)"
            )
        return value

    def has(self, tenant_id: str, key: str) -> bool:
        return (tenant_id, key) in self._values

    def count(self, tenant_id: Optional[str] = None) -> int:
        if tenant_id is None:
            return len(self._values)
        return sum(1 for t, _ in self._values if t == tenant_id)


__all__ = [
    "SecretVaultError",
    "REDACTED",
    "SecretRef",
    "TenantSecretVault",
]
