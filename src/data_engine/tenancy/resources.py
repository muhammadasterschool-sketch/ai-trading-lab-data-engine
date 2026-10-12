"""Server-side authoritative resource ownership (Batch 4).

The access-control OBJECT layer: every protected thing in the
platform is an :class:`OwnedResource` registered in exactly ONE
:class:`ResourceRegistry`, and the registry — SERVER-SIDE state —
is the only authority for "which tenant owns what". Lookups are
deny-by-default: an unregistered resource has no owner, and no
owner means no access, ever.

Resource kinds (the per-user product contract):

- ``TENANT_RECORD`` — the control-plane administrative record of a
  tenant (approval/license state). Owned by the CONTROL PLANE (the
  owner's administrative namespace), managed via admin roles.
- ``VPS`` — the tenant's DEDICATED virtual private server hosting
  their engine (runs while the user's PC is off).
- ``DATABASE`` — the tenant's DEDICATED database (isolated store).
- ``SECRET_STORE`` — the tenant's DEDICATED secret vault (broker
  credentials etc.; values never leave the vault un-revealed).
- ``BACKUP_ARCHIVE`` — the tenant's DEDICATED encrypted backups.
- ``LICENSE`` — the tenant's license artifact (readable by the
  tenant, managed by the control plane).
- ``TRADING_LEDGER`` — the tenant's ISOLATED trading ledger (the
  authoritative per-user trading history; invisible to other
  tenants AND to the owner's control plane).
- ``EXECUTION_SESSION`` — a tenant engine session (status/health
  observable read-only; order submission is a full-role action).
- ``CONTROL_PLANE`` — the owner's own administrative surface.
"""

from enum import Enum
from typing import Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.tenancy.identity import IdentityError, OWNER_TENANT_ID


class ResourceError(ValueError):
    """Raised on resource-registry contract violations."""


class ResourceKind(str, Enum):
    """The closed vocabulary of protected resource kinds."""
    TENANT_RECORD = "TENANT_RECORD"
    VPS = "VPS"
    DATABASE = "DATABASE"
    SECRET_STORE = "SECRET_STORE"
    BACKUP_ARCHIVE = "BACKUP_ARCHIVE"
    LICENSE = "LICENSE"
    TRADING_LEDGER = "TRADING_LEDGER"
    EXECUTION_SESSION = "EXECUTION_SESSION"
    CONTROL_PLANE = "CONTROL_PLANE"


#: Kinds whose ownership lives in the owner/control-plane namespace
#: but which tenants may still READ in limited ways (LICENSE) —
#: administrative ownership is NOT data ownership.
CONTROL_PLANE_OWNED = frozenset({
    ResourceKind.TENANT_RECORD,
    ResourceKind.CONTROL_PLANE,
})


class OwnedResource(BaseModel):
    """One protected, tenant-owned resource (immutable descriptor)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ResourceKind
    tenant_id: str
    name: str
    description: str = ""

    @field_validator("tenant_id", "name")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ResourceError(
                "resource tenant_id/name must be non-empty"
            )
        return v.strip()

    @property
    def uid(self) -> "ResourceUid":
        return ResourceUid(
            kind=self.kind, tenant_id=self.tenant_id, name=self.name
        )


class ResourceUid(BaseModel):
    """The canonical identifier of one resource (kind, tenant, name)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ResourceKind
    tenant_id: str
    name: str

    @field_validator("tenant_id", "name")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ResourceError("uid fields must be non-empty")
        return v.strip()


class ResourceRegistry:
    """The SERVER-SIDE authoritative ownership registry.

    - ``register`` is the only way a resource comes to exist; the
      control plane/administrative layer calls it during (future,
      separately-reviewed) provisioning — never a client.
    - ``owner_of`` is deny-by-default: unregistered -> ``None``
      -> the authorization layer DENIES (no owner, no access).
    - The registry carries descriptors ONLY — never secret values,
      never trading data (those live in the tenant's own stores).
    """

    def __init__(self) -> None:
        self._resources: Dict[Tuple[str, str, str], OwnedResource] = {}

    def register(self, resource: OwnedResource) -> OwnedResource:
        if not isinstance(resource, OwnedResource):
            raise ResourceError("register requires an OwnedResource")
        key = self._key(resource.uid)
        if key in self._resources:
            raise ResourceError(
                f"resource {resource.uid!r} is already registered — "
                "uids are unique and immutable"
            )
        if resource.kind in CONTROL_PLANE_OWNED and \
                resource.tenant_id != OWNER_TENANT_ID:
            raise ResourceError(
                f"{resource.kind.value} resources belong to the "
                f"control-plane namespace ({OWNER_TENANT_ID!r}), not to "
                f"tenant {resource.tenant_id!r}"
            )
        self._resources[key] = resource
        return resource

    def owner_of(self, uid: ResourceUid) -> Optional[str]:
        """The owning tenant id, or None when unregistered
        (deny-by-default — the caller must treat None as DENY)."""
        resource = self._resources.get(self._key(uid))
        return resource.tenant_id if resource is not None else None

    def get(self, uid: ResourceUid) -> Optional[OwnedResource]:
        return self._resources.get(self._key(uid))

    def require(self, uid: ResourceUid) -> OwnedResource:
        resource = self.get(uid)
        if resource is None:
            raise ResourceError(
                f"resource {uid!r} is not registered (deny-by-default)"
            )
        return resource

    def tenant_resources(
        self, tenant_id: str, kind: Optional[ResourceKind] = None,
    ) -> Tuple[OwnedResource, ...]:
        """All registered resources of one tenant (optionally one
        kind) — administrative enumeration only."""
        found: List[OwnedResource] = []
        for resource in self._resources.values():
            if resource.tenant_id != tenant_id:
                continue
            if kind is not None and resource.kind is not kind:
                continue
            found.append(resource)
        return tuple(
            sorted(found, key=lambda r: (r.kind.value, r.name))
        )

    def __len__(self) -> int:
        return len(self._resources)

    @staticmethod
    def _key(uid: ResourceUid) -> Tuple[str, str, str]:
        return (uid.kind.value, uid.tenant_id, uid.name)


def register_tenant_stack(
    registry: ResourceRegistry,
    tenant_id: str,
    *,
    vps_name: str = "primary",
    database_name: str = "trading",
    secret_store_name: str = "vault",
    backup_name: str = "backups",
    ledger_name: str = "trading-ledger",
    execution_name: str = "engine",
) -> Tuple[OwnedResource, ...]:
    """Register the STANDARD per-tenant resource stack (the product
    contract: one dedicated VPS + database + secret store + backup
    archive + isolated trading ledger + engine session per user).

    Called by the (future, separately-reviewed) provisioning layer;
    exposed for the dry-run provisioner and tests. The LICENSE and
    TENANT_RECORD resources are registered in the control-plane
    namespace separately (they are administratively owned)."""
    stack = (
        OwnedResource(
            kind=ResourceKind.VPS, tenant_id=tenant_id, name=vps_name,
            description="dedicated per-user VPS hosting the engine "
                        "(runs while the user's PC is off)",
        ),
        OwnedResource(
            kind=ResourceKind.DATABASE, tenant_id=tenant_id,
            name=database_name,
            description="dedicated per-user database (isolated store)",
        ),
        OwnedResource(
            kind=ResourceKind.SECRET_STORE, tenant_id=tenant_id,
            name=secret_store_name,
            description="dedicated per-user secret vault (broker "
                        "credentials; values never leave un-revealed)",
        ),
        OwnedResource(
            kind=ResourceKind.BACKUP_ARCHIVE, tenant_id=tenant_id,
            name=backup_name,
            description="dedicated per-user encrypted backups "
                        "(isolated restore drills)",
        ),
        OwnedResource(
            kind=ResourceKind.TRADING_LEDGER, tenant_id=tenant_id,
            name=ledger_name,
            description="isolated per-user trading ledger (invisible "
                        "to other tenants AND to the control plane)",
        ),
        OwnedResource(
            kind=ResourceKind.EXECUTION_SESSION, tenant_id=tenant_id,
            name=execution_name,
            description="per-user engine session (read-only status "
                        "views for mobile; order submission is a "
                        "full-role action)",
        ),
    )
    for resource in stack:
        registry.register(resource)
    return stack


def register_control_plane_stack(
    registry: ResourceRegistry,
) -> Tuple[OwnedResource, ...]:
    """Register the control-plane namespace resources (owner-owned):
    the control-plane surface itself plus one TENANT_RECORD and one
    LICENSE per approved tenant id supplied later via
    ``register_tenant_administrative_records``."""
    return (
        registry.register(OwnedResource(
            kind=ResourceKind.CONTROL_PLANE,
            tenant_id=OWNER_TENANT_ID,
            name="control-plane",
            description="the owner's administrative surface "
                        "(approvals, license state, provisioning plans)",
        )),
    )


def register_tenant_administrative_records(
    registry: ResourceRegistry, tenant_id: str,
) -> Tuple[OwnedResource, ...]:
    """Register the control-plane-owned TENANT_RECORD + LICENSE
    resources FOR one tenant (administrative ownership — the tenant
    may READ its own license; only admin roles manage both)."""
    return (
        registry.register(OwnedResource(
            kind=ResourceKind.TENANT_RECORD,
            tenant_id=OWNER_TENANT_ID,
            name=f"tenant-record:{tenant_id}",
            description=f"administrative record of tenant {tenant_id} "
                        "(approval/license state — control-plane "
                        "metadata only, no trading data)",
        )),
        registry.register(OwnedResource(
            kind=ResourceKind.LICENSE,
            tenant_id=OWNER_TENANT_ID,
            name=f"license:{tenant_id}",
            description=f"license artifact of tenant {tenant_id}",
        )),
    )


__all__ = [
    "ResourceError",
    "ResourceKind",
    "CONTROL_PLANE_OWNED",
    "OwnedResource",
    "ResourceUid",
    "ResourceRegistry",
    "register_tenant_stack",
    "register_control_plane_stack",
    "register_tenant_administrative_records",
    "administrative_subject",
]


def administrative_subject(resource: OwnedResource) -> Optional[str]:
    """The tenant a control-plane-owned administrative record is
    ABOUT (``tenant-record:<id>`` / ``license:<id>``), or None.

    Administrative ownership is NOT data ownership: the control
    plane OWNS these records, but the SUBJECT tenant retains
    read-only visibility of its own record/license (a user must be
    able to see their own status); only admin roles may manage
    them."""
    if resource.kind not in (
        ResourceKind.TENANT_RECORD, ResourceKind.LICENSE,
    ):
        return None
    name = resource.name
    for prefix in ("tenant-record:", "license:"):
        if name.startswith(prefix):
            subject = name[len(prefix):]
            return subject if subject else None
    return None
