"""Multi-user tenancy security foundation (Batch 4, 2026-10-12).

Package layout:

- :mod:`data_engine.tenancy.identity` — tenant identity, approval
  and license states, authenticated principals (short-lived
  sessions), the role vocabulary.
- :mod:`data_engine.tenancy.resources` — the server-side
  authoritative resource-ownership registry (the access-control
  object layer).
- :mod:`data_engine.tenancy.authorization` — the deny-by-default
  authorization policy: server-side enforcement where the tenant
  binding comes from the AUTHENTICATED principal, never from
  client-supplied input.
- :mod:`data_engine.tenancy.secrets` — the per-tenant secret vault
  contract: opaque references, authorization-gated reveals, values
  never in logs or decisions.
- :mod:`data_engine.tenancy.provisioning` — the per-user resource
  provisioning CONTRACT (dedicated VPS / database / secrets /
  backups / license / isolated trading ledger) with a DRY-RUN-ONLY
  provisioner: real provisioning is NOT STARTED and no paid
  infrastructure may be touched from this code.

Design authority: ``docs/MULTI_USER_TENANCY_SECURITY_FOUNDATION.md``
(the control-plane boundary, threat model, and the explicit
non-claims).

HONEST SCOPE: this package is the FOUNDATION — identity, ownership
and enforcement primitives with executable security tests. It is
NOT a production multi-tenant platform: there is no public API, no
network surface, no authentication provider, no real infrastructure
provisioning, and no mobile application. Mobile clients are
READ-ONLY by construction (no order-placement action is reachable
by a read-only principal).
"""

from data_engine.tenancy.identity import (
    ApprovalStatus,
    LicenseState,
    PrincipalKind,
    Role,
    TenantRecord,
    AuthenticatedPrincipal,
    IdentityError,
    TENANT_ID_PATTERN,
    issue_session_token,
)
from data_engine.tenancy.resources import (
    ResourceKind,
    OwnedResource,
    ResourceRegistry,
    ResourceUid,
    ResourceError,
    register_tenant_stack,
    register_control_plane_stack,
    register_tenant_administrative_records,
    administrative_subject,
)
from data_engine.tenancy.authorization import (
    Action,
    AccessRequest,
    AccessDecision,
    DenyReason,
    AuthorizationPolicy,
    SecurityAuditLog,
    SecurityEvent,
    AuthorizationError,
)
from data_engine.tenancy.secrets import (
    REDACTED,
    SecretRef,
    SecretVaultError,
    TenantSecretVault,
)
from data_engine.tenancy.provisioning import (
    BackupSpec,
    DatabaseSpec,
    DryRunProvisioner,
    LedgerSpec,
    LicenseSpec,
    ProvisioningError,
    ProvisioningPlan,
    ProvisioningRefusedError,
    ProvisioningStep,
    ProvisioningStepStatus,
    SecretStoreSpec,
    TenantResourceContract,
    VpsSpec,
)

__all__ = [
    # identity
    "ApprovalStatus", "LicenseState", "PrincipalKind", "Role",
    "TenantRecord", "AuthenticatedPrincipal", "IdentityError",
    "TENANT_ID_PATTERN", "issue_session_token",
    # resources
    "ResourceKind", "OwnedResource", "ResourceRegistry",
    "ResourceUid", "ResourceError", "register_tenant_stack",
    "register_control_plane_stack",
    "register_tenant_administrative_records",
    "administrative_subject",
    # authorization
    "Action", "AccessRequest", "AccessDecision", "DenyReason",
    "AuthorizationPolicy", "SecurityAuditLog", "SecurityEvent",
    "AuthorizationError",
    # secrets
    "SecretRef", "SecretVaultError", "TenantSecretVault", "REDACTED",
    # provisioning
    "BackupSpec", "DatabaseSpec", "DryRunProvisioner", "LedgerSpec",
    "LicenseSpec", "ProvisioningError", "ProvisioningPlan",
    "ProvisioningRefusedError", "ProvisioningStep",
    "ProvisioningStepStatus", "SecretStoreSpec",
    "TenantResourceContract", "VpsSpec",
]
