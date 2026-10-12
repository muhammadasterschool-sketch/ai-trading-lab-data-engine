"""Tenant identity, approval/license lifecycle, authenticated
principals and the role vocabulary (Batch 4).

Product context this encodes (from the platform mandate):

- The platform serves ONE owner plus a SMALL set of individually
  approved recipients (a private distribution, not a public SaaS).
- A recipient tenant exists ONLY after the owner approves it
  (PENDING -> APPROVED; REJECTED/SUSPENDED/REVOKED are the other
  lifecycle states).
- Every tenant carries a LICENSE whose state gates ALL tenant-
  scoped access (ACTIVE / SUSPENDED / REVOKED / EXPIRED).
- Sessions are SHORT-LIVED: an authenticated principal carries an
  expiry and expired sessions are denied everywhere (no forever
  tokens).

The tenant binding of a principal is established AT AUTHENTICATION
TIME and is part of the server-side ``AuthenticatedPrincipal``
record. Client-supplied tenant identifiers are NEVER trusted —
the authorization layer compares them against this binding and
treats any mismatch as a manipulation attempt (see
:mod:`data_engine.tenancy.authorization`).
"""

import re
from datetime import datetime, timedelta, UTC
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, field_validator

#: Valid tenant identifier shape (lowercase slug, 3-64 chars).
TENANT_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")

#: The owner's own tenant namespace (the owner is a tenant too —
#: owner DATA is protected by the same isolation rules).
OWNER_TENANT_ID = "owner"


class IdentityError(ValueError):
    """Raised on identity contract violations."""


class ApprovalStatus(str, Enum):
    """Owner-approval lifecycle of one tenant (private distribution)."""
    PENDING = "PENDING"        # requested, NOT yet approved — no access
    APPROVED = "APPROVED"      # owner-approved — tenant may be provisioned
    REJECTED = "REJECTED"      # refused — terminal
    SUSPENDED = "SUSPENDED"    # temporarily disabled by the owner
    REVOKED = "REVOKED"        # permanently removed — terminal


class LicenseState(str, Enum):
    """License state of one tenant; gates ALL tenant-scoped access."""
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class PrincipalKind(str, Enum):
    """What kind of authenticated actor is making a request."""
    OWNER = "OWNER"                          # the platform owner (human)
    TENANT_USER = "TENANT_USER"             # approved recipient (human)
    MOBILE_CLIENT = "MOBILE_CLIENT"         # recipient's mobile app (READ-ONLY)
    CONTROL_PLANE_SERVICE = "CONTROL_PLANE_SERVICE"  # owner's admin service


class Role(str, Enum):
    """Server-assigned capability roles (the authorization matrix's
    ONLY input — roles are assigned at token-issue time and can be
    revoked by expiry).

    - ``READ_ONLY`` — the mobile-dashboard role: observability reads
      of the OWN tenant only. There is NO action in the vocabulary
      that a read-only principal may use to place orders — mobile
      order placement does not exist in this system by design.
    - ``TENANT_FULL`` — the recipient's desktop/engine role on their
      OWN dedicated VPS: full read/write incl. order submission and
      secret reveals for their own tenant only.
    - ``CONTROL_PLANE`` — the administrative service role: manages
      approvals, license state and provisioning PLANS. It can NEVER
      read tenant trading data (ledgers, positions, secrets): the
      control plane stores administrative metadata only — it does
      not centralize trading history or secrets.
    - ``OWNER_ADMIN`` — the owner human: identical administrative
      powers to CONTROL_PLANE plus owner-data access. The owner
      cannot read recipient trading data either.
    """
    READ_ONLY = "READ_ONLY"
    TENANT_FULL = "TENANT_FULL"
    CONTROL_PLANE = "CONTROL_PLANE"
    OWNER_ADMIN = "OWNER_ADMIN"


#: Roles that may hold administrative power over tenant records.
ADMIN_ROLES = frozenset({Role.CONTROL_PLANE, Role.OWNER_ADMIN})

#: The principal kinds allowed per role (binding at authentication).
ROLE_ALLOWED_KINDS = {
    Role.READ_ONLY: frozenset({PrincipalKind.MOBILE_CLIENT}),
    Role.TENANT_FULL: frozenset({PrincipalKind.TENANT_USER}),
    Role.CONTROL_PLANE: frozenset({PrincipalKind.CONTROL_PLANE_SERVICE}),
    Role.OWNER_ADMIN: frozenset({PrincipalKind.OWNER}),
}


class TenantRecord(BaseModel):
    """One tenant's administrative identity (control-plane metadata).

    This is the ONLY per-tenant record the control plane owns. It
    deliberately contains NO trading data, NO positions, NO secrets
    and NO market history — the control plane does not centralize
    tenant trading state (see the control-plane boundary in
    ``docs/MULTI_USER_TENANCY_SECURITY_FOUNDATION.md``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str
    display_name: str
    approval_status: ApprovalStatus
    license_state: LicenseState
    created_at: datetime
    approved_at: Optional[datetime] = None

    @field_validator("tenant_id")
    @classmethod
    def _validate_tenant_id(cls, v: str) -> str:
        if not isinstance(v, str) or not TENANT_ID_PATTERN.match(v):
            raise IdentityError(
                f"tenant_id {v!r} must match {TENANT_ID_PATTERN.pattern}"
            )
        return v

    @field_validator("display_name")
    @classmethod
    def _validate_display(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise IdentityError("display_name must be non-empty")
        return v.strip()


class AuthenticatedPrincipal(BaseModel):
    """A short-lived authenticated actor (the server-side source of
    truth for WHO is acting and FOR WHICH tenant).

    The ``tenant_id`` binding is established at authentication
    (token-issue) time. Requests may carry a *claimed* tenant id;
    the authorization layer compares the claim against THIS binding
    — a mismatch is a manipulation attempt, never a silent
    re-binding.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal_id: str
    kind: PrincipalKind
    role: Role
    tenant_id: Optional[str]
    authenticated_at: datetime
    expires_at: datetime

    @field_validator("principal_id")
    @classmethod
    def _validate_pid(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise IdentityError("principal_id must be non-empty")
        return v.strip()

    @field_validator("tenant_id")
    @classmethod
    def _validate_tenant(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and (
            not isinstance(v, str) or not TENANT_ID_PATTERN.match(v)
        ):
            raise IdentityError(
                f"tenant_id {v!r} must match {TENANT_ID_PATTERN.pattern}"
            )
        return v

    @field_validator("role")
    @classmethod
    def _validate_role_kind_binding(cls, v: Role) -> Role:
        # cross-checked with kind in the model validator below
        return v

    @field_validator("expires_at")
    @classmethod
    def _validate_expiry(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise IdentityError("expires_at must be timezone-aware")
        return v.astimezone(UTC)

    @field_validator("authenticated_at")
    @classmethod
    def _validate_auth_at(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise IdentityError(
                "authenticated_at must be timezone-aware"
            )
        return v.astimezone(UTC)

    def model_post_init(self, __context) -> None:
        allowed = ROLE_ALLOWED_KINDS.get(self.role, frozenset())
        if self.kind not in allowed:
            raise IdentityError(
                f"principal kind {self.kind.value} may NOT hold role "
                f"{self.role.value} (allowed kinds: "
                f"{sorted(k.value for k in allowed)})"
            )
        if self.role is Role.READ_ONLY and self.tenant_id is None:
            raise IdentityError(
                "a read-only (mobile) principal must be bound to a tenant"
            )
        if self.role is Role.TENANT_FULL and self.tenant_id is None:
            raise IdentityError(
                "a tenant-full principal must be bound to a tenant"
            )

    def is_expired(self, at: Optional[datetime] = None) -> bool:
        """True when the session token has expired (short-lived)."""
        now = at.astimezone(UTC) if at is not None else datetime.now(UTC)
        return now >= self.expires_at


def issue_session_token(
    *,
    principal_id: str,
    kind: PrincipalKind,
    role: Role,
    tenant_id: Optional[str],
    ttl_seconds: int = 900,
    at: Optional[datetime] = None,
) -> AuthenticatedPrincipal:
    """Mint a SHORT-LIVED authenticated principal (default TTL 15
    minutes — long-lived tokens are deliberately not constructible
    through this helper; renewal is re-authentication)."""
    if ttl_seconds <= 0 or ttl_seconds > 86400:
        raise IdentityError(
            "session TTL must be in (0, 86400] seconds — short-lived "
            "tokens only (renewal means re-authentication)"
        )
    now = at.astimezone(UTC) if at is not None else datetime.now(UTC)
    return AuthenticatedPrincipal(
        principal_id=principal_id,
        kind=kind,
        role=role,
        tenant_id=tenant_id,
        authenticated_at=now,
        expires_at=now + timedelta(seconds=ttl_seconds),
    )


__all__ = [
    "IdentityError",
    "TENANT_ID_PATTERN",
    "OWNER_TENANT_ID",
    "ApprovalStatus",
    "LicenseState",
    "PrincipalKind",
    "Role",
    "ADMIN_ROLES",
    "ROLE_ALLOWED_KINDS",
    "TenantRecord",
    "AuthenticatedPrincipal",
    "issue_session_token",
]
