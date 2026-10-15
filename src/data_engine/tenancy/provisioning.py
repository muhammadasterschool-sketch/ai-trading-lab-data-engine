"""Per-user resource provisioning CONTRACT (Batch 4) — dry-run only.

This module DEFINES the product's per-user infrastructure contract
(one dedicated, isolated stack per approved user) and provides a
DRY-RUN provisioner that VALIDATES and PLANS but provisions
NOTHING:

- no public API is exposed;
- no paid infrastructure is created, contacted or configured;
- ``execute_plan`` is REFUSED by design ("real provisioning NOT
  STARTED");
- a real provisioner (actual VPS/database/backup automation) is
  future, separately-reviewed, operator-authorized work.

The contract (per approved tenant):

- **VPS** — a DEDICATED virtual private server hosting the user's
  engine; the engine runs in the cloud while the user's PC is off.
- **DATABASE** — a DEDICATED per-user database (isolated store; no
  shared tables).
- **SECRET STORE** — a DEDICATED per-user vault; broker credentials
  and keyed-MAC material are provisioned at the user's OWN VPS at
  runtime and never centralize in the control plane.
- **BACKUP ARCHIVE** — DEDICATED per-user encrypted backups; restore
  drills are isolated per tenant (a restore never crosses tenants).
- **LICENSE** — the per-user license artifact (control-plane
  managed state).
- **TRADING LEDGER** — the ISOLATED per-user trading ledger (the
  authoritative trading history of exactly one user).
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.tenancy.identity import (
    ApprovalStatus,
    IdentityError,
    TenantRecord,
)


class ProvisioningError(ValueError):
    """Raised on provisioning-contract violations."""


class ProvisioningRefusedError(ProvisioningError):
    """Raised when REAL provisioning is attempted — by design."""


class ProvisioningStepStatus(str, Enum):
    """Status of one planned provisioning step (never 'done' here)."""
    PLANNED_ONLY = "PLANNED_ONLY"   # validated in the plan, NOT executed
    REFUSED = "REFUSED"             # refused by design / policy


class VpsSpec(BaseModel):
    """Per-user VPS contract: DEDICATED, isolated, cloud-resident."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dedicated_per_user: bool = True
    engine_runs_when_user_pc_off: bool = True
    isolation: str = "one engine host per tenant — no shared runtime"
    provisioning: str = "operator-managed (real provisioning NOT STARTED)"

    @field_validator("dedicated_per_user", "engine_runs_when_user_pc_off")
    @classmethod
    def _validate_flags(cls, v: bool) -> bool:
        if v is not True:
            raise ProvisioningError(
                "the per-user VPS contract is non-negotiable: dedicated "
                "and cloud-resident"
            )
        return v


class DatabaseSpec(BaseModel):
    """Per-user database contract: DEDICATED, isolated."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dedicated_per_user: bool = True
    shared_tables: bool = False
    isolation: str = "one database per tenant — no cross-tenant queries"

    @field_validator("dedicated_per_user")
    @classmethod
    def _validate_dedicated(cls, v: bool) -> bool:
        if v is not True:
            raise ProvisioningError(
                "the per-user database contract is non-negotiable"
            )
        return v

    @field_validator("shared_tables")
    @classmethod
    def _validate_no_shared(cls, v: bool) -> bool:
        if v is not False:
            raise ProvisioningError(
                "shared tables would break tenant isolation"
            )
        return v


class SecretStoreSpec(BaseModel):
    """Per-user secret store contract: values live at the USER's own
    VPS at runtime; the control plane never centralizes them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dedicated_per_user: bool = True
    provisioned_at_tenant_runtime: bool = True
    centralized_in_control_plane: bool = False
    isolation: str = (
        "broker credentials and keyed-MAC material are provisioned at "
        "the tenant's own VPS at runtime and never uploaded to the "
        "control plane"
    )

    @field_validator("centralized_in_control_plane")
    @classmethod
    def _validate_not_central(cls, v: bool) -> bool:
        if v is not False:
            raise ProvisioningError(
                "centralizing secrets in the control plane violates the "
                "control-plane boundary"
            )
        return v


class BackupSpec(BaseModel):
    """Per-user backup contract: encrypted, isolated restore drills."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dedicated_per_user: bool = True
    encrypted: bool = True
    restore_drills_isolated: bool = True
    isolation: str = (
        "backups restore into the OWN tenant's stack only — a restore "
        "never crosses tenants"
    )

    @field_validator("encrypted", "restore_drills_isolated")
    @classmethod
    def _validate_flags(cls, v: bool) -> bool:
        if v is not True:
            raise ProvisioningError(
                "the per-user backup contract is non-negotiable"
            )
        return v


class LicenseSpec(BaseModel):
    """Per-user license contract: individually issued and revocable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    per_user: bool = True
    revocable_by_owner: bool = True
    states: str = "ACTIVE / SUSPENDED / REVOKED / EXPIRED (gates access)"

    @field_validator("per_user", "revocable_by_owner")
    @classmethod
    def _validate_flags(cls, v: bool) -> bool:
        if v is not True:
            raise ProvisioningError(
                "the per-user license contract is non-negotiable"
            )
        return v


class LedgerSpec(BaseModel):
    """Per-user trading ledger contract: ISOLATED per user."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    dedicated_per_user: bool = True
    visible_to_other_tenants: bool = False
    visible_to_control_plane: bool = False
    isolation: str = (
        "the trading ledger of exactly one user — invisible to other "
        "tenants AND to the owner/control plane"
    )

    @field_validator("visible_to_other_tenants",
                     "visible_to_control_plane")
    @classmethod
    def _validate_invisible(cls, v: bool) -> bool:
        if v is not False:
            raise ProvisioningError(
                "ledger visibility beyond the owning tenant violates the "
                "isolation contract"
            )
        return v


class TenantResourceContract(BaseModel):
    """The COMPLETE per-user resource contract (all six stacks)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str
    vps: VpsSpec = VpsSpec()
    database: DatabaseSpec = DatabaseSpec()
    secret_store: SecretStoreSpec = SecretStoreSpec()
    backups: BackupSpec = BackupSpec()
    license: LicenseSpec = LicenseSpec()
    ledger: LedgerSpec = LedgerSpec()

    @field_validator("tenant_id")
    @classmethod
    def _validate_tenant(cls, v: str) -> str:
        from data_engine.tenancy.identity import TENANT_ID_PATTERN
        if not isinstance(v, str) or not TENANT_ID_PATTERN.match(v):
            raise IdentityError(f"tenant_id {v!r} is not a valid slug")
        return v


class ProvisioningStep(BaseModel):
    """One planned (never executed) provisioning step."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    status: ProvisioningStepStatus
    detail: str = ""

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ProvisioningError("step name must be non-empty")
        return v.strip()


class ProvisioningPlan(BaseModel):
    """A DRY-RUN provisioning plan: the validated per-user contract
    plus PLANNED_ONLY steps. Executing it is refused by design."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tenant_id: str
    contract: TenantResourceContract
    steps: Tuple[ProvisioningStep, ...]
    planned_at: datetime

    @field_validator("steps")
    @classmethod
    def _validate_steps(cls, v) -> tuple:
        if not v:
            raise ProvisioningError("a plan requires >= 1 step")
        for step in v:
            if step.status is not ProvisioningStepStatus.PLANNED_ONLY:
                raise ProvisioningError(
                    "dry-run plans contain PLANNED_ONLY steps — an "
                    "'executed' step cannot exist in this phase"
                )
        return tuple(v)


class DryRunProvisioner:
    """The ONLY provisioner in this phase: validates and PLANS.

    - ``plan_contract`` requires an APPROVED tenant record (pending,
      rejected, suspended or revoked tenants get NO plan).
    - ``execute_plan`` ALWAYS raises :class:`ProvisioningRefusedError`
      — real provisioning is NOT STARTED and no paid infrastructure
      may be touched from this code.
    """

    def plan_contract(
        self, tenant: TenantRecord,
        at: Optional[datetime] = None,
    ) -> ProvisioningPlan:
        if not isinstance(tenant, TenantRecord):
            raise ProvisioningError(
                "planning requires a TenantRecord (control-plane metadata)"
            )
        if tenant.approval_status is not ApprovalStatus.APPROVED:
            raise ProvisioningError(
                f"tenant {tenant.tenant_id!r} approval status is "
                f"{tenant.approval_status.value} — only owner-APPROVED "
                "tenants may be provisioned"
            )
        now = at.astimezone(UTC) if at is not None else datetime.now(UTC)
        contract = TenantResourceContract(tenant_id=tenant.tenant_id)
        steps = tuple(
            ProvisioningStep(
                name=name,
                status=ProvisioningStepStatus.PLANNED_ONLY,
                detail=detail,
            )
            for name, detail in (
                ("vps", "dedicated per-user VPS (engine runs while the "
                        "user's PC is off) — NOT provisioned"),
                ("database", "dedicated per-user database — NOT "
                             "provisioned"),
                ("secret-store", "per-user vault; secrets provisioned at "
                                 "the tenant VPS at runtime — NOT "
                                 "centralized"),
                ("backups", "per-user encrypted backups with isolated "
                            "restore drills — NOT provisioned"),
                ("license", "per-user license artifact issued via "
                            "control-plane state"),
                ("ledger", "isolated per-user trading ledger — NOT "
                           "provisioned"),
            )
        )
        return ProvisioningPlan(
            tenant_id=tenant.tenant_id,
            contract=contract,
            steps=steps,
            planned_at=now,
        )

    def execute_plan(self, plan: ProvisioningPlan) -> None:
        raise ProvisioningRefusedError(
            "REAL PROVISIONING IS NOT STARTED — executing a plan is "
            "refused by design. The per-user infrastructure contract "
            "exists (see TenantResourceContract); a real provisioner "
            "requires a separate operator authorization and review. "
            "No paid infrastructure may be created from this code."
        )


__all__ = [
    "ProvisioningError",
    "ProvisioningRefusedError",
    "ProvisioningStepStatus",
    "VpsSpec",
    "DatabaseSpec",
    "SecretStoreSpec",
    "BackupSpec",
    "LicenseSpec",
    "LedgerSpec",
    "TenantResourceContract",
    "ProvisioningStep",
    "ProvisioningPlan",
    "DryRunProvisioner",
]
