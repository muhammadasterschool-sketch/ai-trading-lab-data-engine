"""Server-side deny-by-default authorization (Batch 4).

THE RULE THIS MODULE ENFORCES: the tenant binding of an access
request comes from the AUTHENTICATED principal (server-side state
established at token-issue time) — NEVER from client-supplied
input. A request may carry a *claimed* tenant id (e.g. a header or
payload field); the policy compares the claim against the
authenticated binding and treats any mismatch as a manipulation
attempt: DENY + security incident. There is no code path anywhere
in this package where a client-supplied tenant identifier changes
what an authenticated principal may access.

Decision procedure (every step fail-closed, every denial audited):

1. Session validity — expired principals are denied
   (``SESSION_EXPIRED``).
2. Claimed-tenant consistency — a claimed tenant id that differs
   from the authenticated binding is denied
   (``TENANT_ID_MANIPULATION``) and flagged as a security incident.
3. Resource existence — unregistered resources are denied
   (``UNKNOWN_RESOURCE``): no owner, no access.
4. License gate — the SUBJECT tenant's license must be ACTIVE for
   tenant-scoped access (``LICENSE_INACTIVE``). The owner's own
   namespace is exempt (the owner administers licenses).
5. Role/ownership matrix — the capability matrix below; anything
   not explicitly allowed is denied (``ROLE_REQUIRED`` for
   insufficient role, ``CROSS_TENANT`` for foreign resources).

Capability matrix (role -> allowed (kind, action) pairs, own tenant
unless noted):

- READ_ONLY (mobile): READ TRADING_LEDGER, EXECUTION_SESSION,
  LICENSE (own administrative subject), TENANT_RECORD (own
  administrative subject), BACKUP_ARCHIVE (status), VPS (health).
  Nothing else — in particular NO WRITE of any kind, NO
  ORDER_SUBMIT, NO SECRET_REVEAL: the mobile dashboard is
  read-only and no order-placement path exists for it.
- TENANT_FULL (recipient engine/desktop): READ/WRITE on all own
  tenant resources (VPS, DATABASE, SECRET_STORE, BACKUP_ARCHIVE,
  TRADING_LEDGER, EXECUTION_SESSION) + ORDER_SUBMIT on
  EXECUTION_SESSION + SECRET_REVEAL on SECRET_STORE + READ own
  LICENSE/TENANT_RECORD.
- CONTROL_PLANE / OWNER_ADMIN: MANAGE TENANT_RECORD + LICENSE (the
  administrative subjects of any tenant — approvals and license
  state are the control plane's job), PROVISION (dry-run plans),
  READ/WRITE/MANAGE CONTROL_PLANE, plus the OWNER_ADMIN's own
  tenant access (the owner is a tenant too — owner DATA is
  protected by the same isolation). Administrative roles are
  DENIED trading-data reads/writes on recipient tenants (ledgers,
  positions, secrets, databases): the control plane does not
  centralize trading history or secrets.

Every decision — allow AND deny — is recorded in an append-only
:class:`SecurityAuditLog` with the principal, action, resource uid
and reason. Denials that indicate attack patterns (tenant-id
manipulation, cross-tenant probing) are flagged
``security_incident=True``.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.tenancy.identity import (
    ADMIN_ROLES,
    AuthenticatedPrincipal,
    LicenseState,
    Role,
)
from data_engine.tenancy.resources import (
    CONTROL_PLANE_OWNED,
    OwnedResource,
    ResourceKind,
    ResourceRegistry,
    ResourceUid,
    administrative_subject,
)


class AuthorizationError(ValueError):
    """Raised on authorization contract violations."""


class Action(str, Enum):
    """The closed vocabulary of protected actions.

    ``ORDER_SUBMIT`` exists ONLY for full tenant roles (the desktop
    engine on the user's own VPS). There is no mobile order
    placement: a READ_ONLY principal is structurally unable to
    reach it (see the matrix in this module's docstring).
    """
    READ = "READ"
    WRITE = "WRITE"
    MANAGE = "MANAGE"
    PROVISION = "PROVISION"
    ORDER_SUBMIT = "ORDER_SUBMIT"
    SECRET_REVEAL = "SECRET_REVEAL"


#: Actions reserved to administrative roles (control-plane duties).
ADMIN_ACTIONS = frozenset({Action.MANAGE, Action.PROVISION})

#: The mobile-dashboard (read-only) observable surface.
READ_ONLY_KINDS = frozenset({
    ResourceKind.TRADING_LEDGER,
    ResourceKind.EXECUTION_SESSION,
    ResourceKind.LICENSE,
    ResourceKind.TENANT_RECORD,
    ResourceKind.BACKUP_ARCHIVE,
    ResourceKind.VPS,
})

#: Tenant trading-data kinds — the control plane NEVER touches
#: these on recipient tenants (no centralization of trading state).
TENANT_TRADING_DATA = frozenset({
    ResourceKind.TRADING_LEDGER,
    ResourceKind.EXECUTION_SESSION,
    ResourceKind.DATABASE,
    ResourceKind.SECRET_STORE,
    ResourceKind.BACKUP_ARCHIVE,
    ResourceKind.VPS,
})


class DenyReason(str, Enum):
    """Why an access was denied (auditable, closed vocabulary)."""
    DENY_DEFAULT = "DENY_DEFAULT"
    SESSION_EXPIRED = "SESSION_EXPIRED"
    TENANT_ID_MANIPULATION = "TENANT_ID_MANIPULATION"
    UNKNOWN_RESOURCE = "UNKNOWN_RESOURCE"
    LICENSE_INACTIVE = "LICENSE_INACTIVE"
    CROSS_TENANT = "CROSS_TENANT"
    ROLE_REQUIRED = "ROLE_REQUIRED"
    NOT_ALLOWED_BY_POLICY = "NOT_ALLOWED_BY_POLICY"


#: Denial reasons that indicate an attack pattern (probe/spoof).
SECURITY_INCIDENT_REASONS = frozenset({
    DenyReason.TENANT_ID_MANIPULATION,
    DenyReason.CROSS_TENANT,
})


class AccessRequest(BaseModel):
    """One access request as seen by the SERVER.

    ``principal`` is the server-side authenticated actor. The
    optional ``claimed_tenant_id`` models a client-supplied tenant
    identifier (header/payload): it is COMPARED against the
    authenticated binding — it can never override it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    principal: AuthenticatedPrincipal
    resource: ResourceUid
    action: Action
    claimed_tenant_id: Optional[str] = None
    at: datetime

    @field_validator("at")
    @classmethod
    def _validate_at(cls, v: datetime) -> datetime:
        if v is None or v.tzinfo is None:
            raise AuthorizationError(
                "access requests must carry a timezone-aware timestamp"
            )
        return v.astimezone(UTC)


class AccessDecision(BaseModel):
    """The immutable outcome of one access request."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed: bool
    reason: str          # "ALLOW" or a DenyReason value
    detail: str = ""
    security_incident: bool = False
    principal_id: str
    role: str
    authenticated_tenant: Optional[str] = None
    resource: ResourceUid
    action: Action

    @property
    def deny_reason(self) -> Optional[DenyReason]:
        if self.allowed:
            return None
        try:
            return DenyReason(self.reason)
        except ValueError:
            return None


class SecurityEvent(BaseModel):
    """One security-audit record (allow or deny — both are
    auditable). Contains NO secret material and NO trading data:
    principal id, role, action, resource UID and reason only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    at: datetime
    allowed: bool
    reason: str
    security_incident: bool
    principal_id: str
    role: str
    authenticated_tenant: Optional[str] = None
    claimed_tenant_id: Optional[str] = None
    resource_kind: str
    resource_tenant: str
    resource_name: str
    action: str


class SecurityAuditLog:
    """Append-only in-memory security audit log.

    FOUNDATION SCOPE: in-memory only (no persistence, no network).
    Durable, tamper-evident security logging is future work — see
    the non-claims in the design document.
    """

    def __init__(self) -> None:
        self._events: List[SecurityEvent] = []

    def record(self, event: SecurityEvent) -> None:
        if not isinstance(event, SecurityEvent):
            raise AuthorizationError("audit records must be SecurityEvent")
        self._events.append(event)

    def events(self) -> tuple:
        return tuple(self._events)

    def incidents(self) -> tuple:
        return tuple(e for e in self._events if e.security_incident)

    def __len__(self) -> int:
        return len(self._events)


class AuthorizationPolicy:
    """The server-side authorization policy (pure decision logic +
    audit recording). Constructed with the authoritative
    :class:`ResourceRegistry` and a lookup of tenant license
    states (the control-plane administrative view)."""

    def __init__(
        self,
        registry: ResourceRegistry,
        license_states: dict = None,
        audit_log: Optional[SecurityAuditLog] = None,
    ) -> None:
        if not isinstance(registry, ResourceRegistry):
            raise AuthorizationError(
                "policy requires the authoritative ResourceRegistry"
            )
        self._registry = registry
        self._licenses = dict(license_states or {})
        self._audit = audit_log if audit_log is not None \
            else SecurityAuditLog()

    @property
    def audit_log(self) -> SecurityAuditLog:
        return self._audit

    def set_license_state(self, tenant_id: str, state: LicenseState) -> None:
        """Control-plane administrative update of one tenant's
        license state (the only mutable policy input)."""
        self._licenses[tenant_id] = state

    # ------------------------------------------------------------------
    def decide(self, request: AccessRequest) -> AccessDecision:
        principal = request.principal
        resource_uid = request.resource

        def outcome(allowed: bool, reason: str, detail: str = "",
                    incident: bool = False) -> AccessDecision:
            decision = AccessDecision(
                allowed=allowed,
                reason=reason,
                detail=detail,
                security_incident=incident,
                principal_id=principal.principal_id,
                role=principal.role.value,
                authenticated_tenant=principal.tenant_id,
                resource=resource_uid,
                action=request.action,
            )
            self._audit.record(SecurityEvent(
                at=request.at,
                allowed=allowed,
                reason=reason,
                security_incident=incident,
                principal_id=principal.principal_id,
                role=principal.role.value,
                authenticated_tenant=principal.tenant_id,
                claimed_tenant_id=request.claimed_tenant_id,
                resource_kind=resource_uid.kind.value,
                resource_tenant=resource_uid.tenant_id,
                resource_name=resource_uid.name,
                action=request.action.value,
            ))
            return decision

        # 1. session validity (short-lived tokens)
        if principal.is_expired(at=request.at):
            return outcome(
                False, DenyReason.SESSION_EXPIRED.value,
                f"session for {principal.principal_id!r} expired at "
                f"{principal.expires_at.isoformat()}",
            )

        # 2. claimed-tenant consistency — the SERVER-SIDE binding is
        #    the only truth; a divergent client claim is manipulation.
        if (
            request.claimed_tenant_id is not None
            and request.claimed_tenant_id != principal.tenant_id
        ):
            return outcome(
                False, DenyReason.TENANT_ID_MANIPULATION.value,
                f"client claimed tenant {request.claimed_tenant_id!r} "
                f"but the authenticated principal is bound to "
                f"{principal.tenant_id!r} — the claim can never "
                "override the server-side binding",
                incident=True,
            )

        # 3. resource existence (deny-by-default registry)
        resource = self._registry.get(resource_uid)
        if resource is None:
            return outcome(
                False, DenyReason.UNKNOWN_RESOURCE.value,
                f"resource {resource_uid!r} is not registered — "
                "no owner, no access",
                incident=True,
            )

        # 4. license gate for the SUBJECT tenant
        subject_tenant = self._subject_tenant(resource)
        if subject_tenant is not None:
            state = self._licenses.get(subject_tenant)
            if state is not None and state is not LicenseState.ACTIVE:
                return outcome(
                    False, DenyReason.LICENSE_INACTIVE.value,
                    f"tenant {subject_tenant!r} license is "
                    f"{state.value} — all tenant-scoped access denied",
                )

        # 5. role/ownership matrix
        return self._matrix(request, resource, outcome)

    # ------------------------------------------------------------------
    def _subject_tenant(self, resource: OwnedResource) -> Optional[str]:
        """The tenant whose license/state governs access to this
        resource: administrative records are ABOUT their subject;
        everything else is about its owner."""
        subject = administrative_subject(resource)
        return subject if subject is not None else resource.tenant_id

    def _matrix(self, request, resource, outcome):
        principal = request.principal
        role = principal.role
        action = request.action
        subject = administrative_subject(resource)

        # -- administrative roles (CONTROL_PLANE / OWNER_ADMIN) ------
        if role in ADMIN_ROLES:
            # administrative surface
            if resource.kind is ResourceKind.CONTROL_PLANE:
                if action in (Action.READ, Action.WRITE, Action.MANAGE,
                              Action.PROVISION):
                    return outcome(True, "ALLOW",
                                   "administrative access to the "
                                   "control-plane surface")
                return outcome(
                    False, DenyReason.NOT_ALLOWED_BY_POLICY.value,
                    f"action {action.value} is not defined for the "
                    "control-plane surface",
                )
            # administrative records: manage any tenant's approval/
            # license state; provision (dry-run) for any tenant
            if resource.kind in (ResourceKind.TENANT_RECORD,
                                 ResourceKind.LICENSE):
                if action is Action.MANAGE or (
                    action is Action.PROVISION
                    and resource.kind is ResourceKind.TENANT_RECORD
                ):
                    return outcome(
                        True, "ALLOW",
                        f"administrative {action.value} on the "
                        f"record of tenant {subject!r}",
                    )
                if action is Action.READ:
                    return outcome(
                        True, "ALLOW",
                        "administrative read of control-plane metadata "
                        "(no trading data)",
                    )
                return outcome(
                    False, DenyReason.NOT_ALLOWED_BY_POLICY.value,
                    "administrative roles may not WRITE tenant "
                    "administrative records through the data path "
                    "(use MANAGE)",
                )
            # CONTROL-PLANE BOUNDARY: administrative roles NEVER touch
            # tenant trading data (the owner's own tenant resources
            # are the exception — the owner is a tenant too).
            if resource.tenant_id != principal.tenant_id:
                if resource.kind in TENANT_TRADING_DATA:
                    return outcome(
                        False, DenyReason.CROSS_TENANT.value,
                        "control-plane boundary: administrative roles "
                        "cannot access tenant trading data (ledgers, "
                        "databases, secrets, backups, VPS, sessions) — "
                        "the control plane holds administrative metadata "
                        "only and never centralizes trading history or "
                        "secrets",
                        incident=True,
                    )
                return outcome(
                    False, DenyReason.CROSS_TENANT.value,
                    "administrative access is limited to control-plane "
                    "resources and the owner's own tenant",
                    incident=True,
                )
            # fall through: owner's own tenant resources via the
            # tenant matrix below (the owner acting as a tenant)

        # -- tenant roles (READ_ONLY / TENANT_FULL; owner-as-tenant) --
        own = resource.tenant_id == principal.tenant_id
        admin_record_of_self = (
            subject is not None and subject == principal.tenant_id
            and resource.kind in (ResourceKind.TENANT_RECORD,
                                  ResourceKind.LICENSE)
        )

        if not own and not admin_record_of_self:
            return outcome(
                False, DenyReason.CROSS_TENANT.value,
                f"principal of tenant {principal.tenant_id!r} cannot "
                f"access tenant {resource.tenant_id!r}'s "
                f"{resource.kind.value} — tenants are mutually "
                "invisible (and owner data is not visible to "
                "recipients)",
                incident=True,
            )

        if role is Role.READ_ONLY:
            if action is not Action.READ:
                return outcome(
                    False, DenyReason.ROLE_REQUIRED.value,
                    f"read-only (mobile) principals cannot {action.value} "
                    "ANYTHING — the mobile dashboard is read-only and "
                    "no order-placement path exists for it",
                )
            if resource.kind not in READ_ONLY_KINDS:
                return outcome(
                    False, DenyReason.ROLE_REQUIRED.value,
                    f"read-only (mobile) principals may not read "
                    f"{resource.kind.value} resources",
                )
            return outcome(
                True, "ALLOW",
                "read-only observability of the own tenant "
                "(mobile dashboard)",
            )

        if role is Role.TENANT_FULL:
            if action is Action.ORDER_SUBMIT:
                if resource.kind is ResourceKind.EXECUTION_SESSION:
                    return outcome(
                        True, "ALLOW",
                        "order submission by the tenant's own engine "
                        "(full role, own VPS session)",
                    )
                return outcome(
                    False, DenyReason.NOT_ALLOWED_BY_POLICY.value,
                    "order submission applies to execution sessions only",
                )
            if action is Action.SECRET_REVEAL:
                if resource.kind is ResourceKind.SECRET_STORE:
                    return outcome(
                        True, "ALLOW",
                        "secret reveal to the tenant's own full-role "
                        "engine",
                    )
                return outcome(
                    False, DenyReason.NOT_ALLOWED_BY_POLICY.value,
                    "secret reveals apply to secret stores only",
                )
            if action is Action.MANAGE or action is Action.PROVISION:
                return outcome(
                    False, DenyReason.ROLE_REQUIRED.value,
                    "tenant roles cannot manage records or provision",
                )
            if resource.kind in CONTROL_PLANE_OWNED and not (
                admin_record_of_self
            ):
                return outcome(
                    False, DenyReason.CROSS_TENANT.value,
                    "control-plane resources are not tenant-accessible",
                )
            if admin_record_of_self and action is Action.READ:
                return outcome(
                    True, "ALLOW",
                    "tenant read of its own administrative record "
                    "(status/license visibility)",
                )
            if resource.kind in (ResourceKind.VPS, ResourceKind.DATABASE,
                                 ResourceKind.SECRET_STORE,
                                 ResourceKind.BACKUP_ARCHIVE,
                                 ResourceKind.TRADING_LEDGER,
                                 ResourceKind.EXECUTION_SESSION):
                return outcome(
                    True, "ALLOW",
                    f"full-role {action.value} on the tenant's own "
                    f"{resource.kind.value}",
                )
            return outcome(
                False, DenyReason.NOT_ALLOWED_BY_POLICY.value,
                f"action {action.value} on {resource.kind.value} is "
                "not defined for tenant roles",
            )

        return outcome(
            False, DenyReason.DENY_DEFAULT.value,
            "no rule allowed this request (deny by default)",
        )


__all__ = [
    "AuthorizationError",
    "Action",
    "ADMIN_ACTIONS",
    "READ_ONLY_KINDS",
    "TENANT_TRADING_DATA",
    "DenyReason",
    "SECURITY_INCIDENT_REASONS",
    "AccessRequest",
    "AccessDecision",
    "SecurityEvent",
    "SecurityAuditLog",
    "AuthorizationPolicy",
]
