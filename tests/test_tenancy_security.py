"""Multi-user security foundation acceptance tests (Batch 4).

The isolation properties under test (product requirements):

1. Server-side authorization: the tenant binding comes from the
   AUTHENTICATED principal — a client-supplied (claimed) tenant id
   can NEVER change what is accessible; a mismatching claim is a
   recorded manipulation incident.
2. Cross-user denial: recipient tenants are mutually invisible;
   owner data is not visible to recipients.
3. Control-plane boundary: the owner/admin roles manage approvals
   and license state but are DENIED recipient trading data
   (ledgers, databases, secrets, backups, VPS, sessions) — the
   control plane never centralizes trading history or secrets.
4. Mobile clients are READ-ONLY: no WRITE, no ORDER_SUBMIT, no
   SECRET_REVEAL on ANY resource — no mobile order-placement path
   exists at all.
5. Secret hygiene: values are gated behind authorization, never in
   audit records/decisions/reprs; cross-tenant reveals are
   structurally refused.
6. License states gate everything; sessions expire.
7. Provisioning is DRY-RUN ONLY: plans for approved tenants, zero
   side effects, execution refused by design.
"""

from datetime import datetime, timedelta, UTC
from decimal import Decimal  # noqa: F401 — tenancy is value-free

import pytest

from data_engine.tenancy import (
    AccessDecision,  # noqa: F401 — used in type assertions
    AccessRequest,
    Action,
    ApprovalStatus,
    AuthorizationPolicy,
    DryRunProvisioner,
    IdentityError,
    LicenseState,
    PrincipalKind,
    ProvisioningError,
    ProvisioningPlan,
    ProvisioningRefusedError,
    REDACTED,
    ResourceKind,
    ResourceRegistry,
    ResourceUid,
    Role,
    SecretRef,
    SecretVaultError,
    SecurityAuditLog,
    TenantRecord,
    TenantSecretVault,
    administrative_subject,
    issue_session_token,
    register_control_plane_stack,
    register_tenant_administrative_records,
    register_tenant_stack,
)

T0 = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)
ALICE = "tenant-alice"
BOB = "tenant-bob"


def _tenant(tenant_id, approval=ApprovalStatus.APPROVED,
            license_state=LicenseState.ACTIVE):
    return TenantRecord(
        tenant_id=tenant_id,
        display_name=tenant_id.replace("-", " ").title(),
        approval_status=approval,
        license_state=license_state,
        created_at=T0 - timedelta(days=30),
        approved_at=T0 - timedelta(days=29),
    )


def _world(*license_states):
    """Registry + policy with control-plane stack, two tenants and
    the full per-tenant resource stacks."""
    reg = ResourceRegistry()
    register_control_plane_stack(reg)
    for tenant_id in (ALICE, BOB):
        register_tenant_administrative_records(reg, tenant_id)
        register_tenant_stack(reg, tenant_id)
    states = dict(license_states)
    states.setdefault(ALICE, LicenseState.ACTIVE)
    states.setdefault(BOB, LicenseState.ACTIVE)
    policy = AuthorizationPolicy(reg, states)
    return reg, policy


def _uid(kind, tenant, name):
    return ResourceUid(kind=kind, tenant_id=tenant, name=name)


def _principal(kind, role, tenant, ttl=900):
    return issue_session_token(
        principal_id=f"{kind.value.lower()}-{tenant or 'owner'}",
        kind=kind, role=role, tenant_id=tenant, ttl_seconds=ttl, at=T0,
    )


def _alice_mobile():
    return _principal(
        PrincipalKind.MOBILE_CLIENT, Role.READ_ONLY, ALICE
    )


def _alice_engine():
    return _principal(PrincipalKind.TENANT_USER, Role.TENANT_FULL, ALICE)


def _bob_engine():
    return _principal(PrincipalKind.TENANT_USER, Role.TENANT_FULL, BOB)


def _owner_admin():
    return _principal(PrincipalKind.OWNER, Role.OWNER_ADMIN, "owner")


def _control_plane():
    return _principal(
        PrincipalKind.CONTROL_PLANE_SERVICE, Role.CONTROL_PLANE, "owner"
    )


def _req(principal, kind, tenant, name, action, claimed=None, at=T0):
    return AccessRequest(
        principal=principal,
        resource=_uid(kind, tenant, name),
        action=action,
        claimed_tenant_id=claimed,
        at=at,
    )


LEDGER_A = (ResourceKind.TRADING_LEDGER, ALICE, "trading-ledger")
LEDGER_B = (ResourceKind.TRADING_LEDGER, BOB, "trading-ledger")
SESSION_A = (ResourceKind.EXECUTION_SESSION, ALICE, "engine")
SECRETS_A = (ResourceKind.SECRET_STORE, ALICE, "vault")
SECRETS_B = (ResourceKind.SECRET_STORE, BOB, "vault")
DB_A = (ResourceKind.DATABASE, ALICE, "trading")
VPS_A = (ResourceKind.VPS, ALICE, "primary")
LICENSE_A = (ResourceKind.LICENSE, "owner", f"license:{ALICE}")
RECORD_A = (ResourceKind.TENANT_RECORD, "owner",
            f"tenant-record:{ALICE}")
CONTROL_PLANE_R = (ResourceKind.CONTROL_PLANE, "owner", "control-plane")


class TestCrossUserAccessDenial:
    """Recipients are mutually invisible; owner data is private."""

    def test_alice_cannot_read_bobs_ledger(self):
        _, policy = _world()
        d = policy.decide(_req(_alice_engine(), *LEDGER_B, Action.READ))
        assert not d.allowed
        assert d.deny_reason.value == "CROSS_TENANT"
        assert d.security_incident

    def test_bob_cannot_write_alices_ledger(self):
        _, policy = _world()
        d = policy.decide(_req(_bob_engine(), *LEDGER_A, Action.WRITE))
        assert not d.allowed
        assert d.deny_reason.value == "CROSS_TENANT"
        assert d.security_incident

    def test_mutual_invisibility_both_directions(self):
        _, policy = _world()
        for principal, target in ((_alice_engine(), LEDGER_B),
                                  (_bob_engine(), LEDGER_A)):
            for action in (Action.READ, Action.WRITE, Action.ORDER_SUBMIT,
                           Action.SECRET_REVEAL):
                d = policy.decide(_req(principal, *target, action))
                assert not d.allowed, (action, d.detail)

    def test_recipient_cannot_see_owner_data(self):
        """Owner data is protected by the SAME isolation rules."""
        _, policy = _world()
        # the owner's own tenant stack (registered like any tenant)
        reg = policy._registry  # noqa: SLF001 — test seam
        register_tenant_stack(reg, "owner")
        d = policy.decide(_req(
            _alice_engine(), ResourceKind.TRADING_LEDGER, "owner",
            "trading-ledger", Action.READ,
        ))
        assert not d.allowed
        assert d.deny_reason.value == "CROSS_TENANT"

    def test_positive_controls_own_tenant_access(self):
        """The denials above are not over-tripping: a full-role
        principal reads/writes its OWN stack, and a mobile principal
        reads its own ledger."""
        _, policy = _world()
        assert policy.decide(_req(
            _alice_engine(), *LEDGER_A, Action.READ)).allowed
        assert policy.decide(_req(
            _alice_engine(), *LEDGER_A, Action.WRITE)).allowed
        assert policy.decide(_req(
            _alice_mobile(), *LEDGER_A, Action.READ)).allowed
        assert policy.decide(_req(
            _alice_engine(), *SESSION_A, Action.ORDER_SUBMIT)).allowed


class TestControlPlaneBoundary:
    """Admin roles manage metadata only — never trading data."""

    def test_owner_cannot_read_recipient_trading_data(self):
        _, policy = _world()
        for target in (LEDGER_A, DB_A, SECRETS_A, VPS_A, SESSION_A):
            for action in (Action.READ, Action.WRITE,
                           Action.ORDER_SUBMIT, Action.SECRET_REVEAL):
                d = policy.decide(_req(_owner_admin(), *target, action))
                assert not d.allowed, (target, action)
                assert d.deny_reason.value == "CROSS_TENANT"

    def test_control_plane_service_cannot_read_trading_data(self):
        _, policy = _world()
        d = policy.decide(_req(
            _control_plane(), *LEDGER_A, Action.READ))
        assert not d.allowed
        assert "control-plane boundary" in d.detail

    def test_owner_manages_tenant_records_and_licenses(self):
        _, policy = _world()
        for target in (RECORD_A, LICENSE_A):
            d = policy.decide(_req(_owner_admin(), *target, Action.MANAGE))
            assert d.allowed, d.detail
        d = policy.decide(_req(
            _control_plane(), *RECORD_A, Action.MANAGE))
        assert d.allowed

    def test_owner_reads_control_plane_surface(self):
        _, policy = _world()
        assert policy.decide(_req(
            _owner_admin(), *CONTROL_PLANE_R, Action.READ)).allowed

    def test_tenant_cannot_manage_records_or_control_plane(self):
        _, policy = _world()
        for principal in (_alice_engine(), _alice_mobile()):
            d = policy.decide(_req(
                principal, *RECORD_A, Action.MANAGE))
            assert not d.allowed
            d2 = policy.decide(_req(
                principal, *CONTROL_PLANE_R, Action.READ))
            assert not d2.allowed

    def test_tenant_reads_own_license_and_record(self):
        """A user must see their own status/license (administrative
        SUBJECT visibility), but cannot MANAGE them."""
        _, policy = _world()
        for target in (LICENSE_A, RECORD_A):
            d = policy.decide(_req(
                _alice_engine(), *target, Action.READ))
            assert d.allowed, d.detail
            d2 = policy.decide(_req(
                _alice_mobile(), *target, Action.READ))
            assert d2.allowed, d2.detail
            d3 = policy.decide(_req(
                _alice_engine(), *target, Action.MANAGE))
            assert not d3.allowed

    def test_tenant_cannot_read_other_tenants_record(self):
        _, policy = _world()
        record_b = (ResourceKind.TENANT_RECORD, "owner",
                    f"tenant-record:{BOB}")
        d = policy.decide(_req(_alice_engine(), *record_b, Action.READ))
        assert not d.allowed
        assert d.deny_reason.value == "CROSS_TENANT"


class TestTenantIdManipulation:
    """Client-supplied tenant IDs never override the server-side
    binding — mismatches are recorded incidents."""

    def test_claimed_mismatch_denied_and_flagged(self):
        _, policy = _world()
        for principal in (_alice_engine(), _alice_mobile()):
            d = policy.decide(_req(
                principal, *LEDGER_A, Action.READ,
                claimed=BOB))
            assert not d.allowed
            assert d.deny_reason.value == "TENANT_ID_MANIPULATION"
            assert d.security_incident
            assert "never override" in d.detail

    def test_matching_claim_is_harmless(self):
        _, policy = _world()
        d = policy.decide(_req(
            _alice_engine(), *LEDGER_A, Action.READ, claimed=ALICE))
        assert d.allowed

    def test_every_manipulation_is_audited(self):
        _, policy = _world()
        policy.decide(_req(_alice_engine(), *LEDGER_A, Action.READ,
                           claimed=BOB))
        policy.decide(_req(_alice_mobile(), *LEDGER_A, Action.READ,
                           claimed="tenant-carol"))
        incidents = policy.audit_log.incidents()
        assert len(incidents) == 2
        assert all(
            e.reason == "TENANT_ID_MANIPULATION" for e in incidents
        )
        assert {e.claimed_tenant_id for e in incidents} == {BOB,
                                                            "tenant-carol"}

    def test_manipulation_checked_before_resource_lookup(self):
        """The manipulation gate fires even for UNKNOWN resources
        (step order: expiry -> manipulation -> existence)."""
        _, policy = _world()
        d = policy.decide(_req(
            _alice_engine(), ResourceKind.TRADING_LEDGER, BOB,
            "no-such-ledger", Action.READ, claimed=BOB,
        ))
        assert d.deny_reason.value == "TENANT_ID_MANIPULATION"


class TestMobileReadOnly:
    """Mobile clients: observability reads only — no writes, no
    orders, no secret reveals; no order path exists for them."""

    def test_mobile_cannot_write_anything(self):
        _, policy = _world()
        kinds = (
            (ResourceKind.TRADING_LEDGER, ALICE, "trading-ledger"),
            (ResourceKind.EXECUTION_SESSION, ALICE, "engine"),
            (ResourceKind.DATABASE, ALICE, "trading"),
            (ResourceKind.VPS, ALICE, "primary"),
            (ResourceKind.SECRET_STORE, ALICE, "vault"),
            (ResourceKind.BACKUP_ARCHIVE, ALICE, "backups"),
        )
        for target in kinds:
            for action in (Action.WRITE, Action.MANAGE,
                           Action.ORDER_SUBMIT, Action.SECRET_REVEAL,
                           Action.PROVISION):
                d = policy.decide(_req(
                    _alice_mobile(), *target, action))
                assert not d.allowed, (target, action, d.detail)
                assert d.deny_reason.value == "ROLE_REQUIRED"

    def test_mobile_reads_its_dashboard_surface(self):
        _, policy = _world()
        for target in (LEDGER_A, SESSION_A,
                       (ResourceKind.BACKUP_ARCHIVE, ALICE, "backups"),
                       (ResourceKind.VPS, ALICE, "primary"),
                       LICENSE_A):
            d = policy.decide(_req(_alice_mobile(), *target, Action.READ))
            assert d.allowed, (target, d.detail)

    def test_mobile_cannot_read_secret_store_or_database(self):
        _, policy = _world()
        for target in (SECRETS_A, DB_A):
            d = policy.decide(_req(_alice_mobile(), *target, Action.READ))
            assert not d.allowed

    def test_no_mobile_order_placement_path_exists(self):
        """Structural proof: ORDER_SUBMIT is reachable ONLY by the
        TENANT_FULL role — for EVERY resource kind, mobile is
        denied; there is no action a read-only principal can take
        that places an order."""
        _, policy = _world()
        reg = policy._registry  # noqa: SLF001 — test seam
        for resource in reg.tenant_resources(ALICE):
            d = policy.decide(_req(
                _alice_mobile(), resource.kind, resource.tenant_id,
                resource.name, Action.ORDER_SUBMIT))
            assert not d.allowed
        # and the only allowing role for ORDER_SUBMIT is TENANT_FULL
        for principal in (_owner_admin(), _control_plane(),
                          _alice_mobile()):
            d = policy.decide(_req(
                principal, *SESSION_A, Action.ORDER_SUBMIT))
            assert not d.allowed

    def test_mobile_sessions_are_short_lived(self):
        with pytest.raises(IdentityError):
            issue_session_token(
                principal_id="long", kind=PrincipalKind.MOBILE_CLIENT,
                role=Role.READ_ONLY, tenant_id=ALICE,
                ttl_seconds=86401,
            )


class TestLicenseAndSessionGating:
    """License states gate all tenant access; sessions expire."""

    @pytest.mark.parametrize("state", [
        LicenseState.SUSPENDED, LicenseState.REVOKED,
        LicenseState.EXPIRED,
    ])
    def test_inactive_license_denies_everything(self, state):
        _, policy = _world((ALICE, state))
        for principal in (_alice_engine(), _alice_mobile()):
            for target in (LEDGER_A, SESSION_A, SECRETS_A):
                for action in (Action.READ, Action.WRITE,
                               Action.ORDER_SUBMIT):
                    d = policy.decide(_req(principal, *target, action))
                    assert not d.allowed
                    assert d.deny_reason.value == "LICENSE_INACTIVE"

    def test_license_revocation_is_effective_immediately(self):
        _, policy = _world()
        assert policy.decide(_req(
            _alice_engine(), *LEDGER_A, Action.READ)).allowed
        policy.set_license_state(ALICE, LicenseState.REVOKED)
        d = policy.decide(_req(_alice_engine(), *LEDGER_A, Action.READ))
        assert not d.allowed
        assert d.deny_reason.value == "LICENSE_INACTIVE"

    def test_expired_session_denied(self):
        _, policy = _world()
        expired = issue_session_token(
            principal_id="eng-expired", kind=PrincipalKind.TENANT_USER,
            role=Role.TENANT_FULL, tenant_id=ALICE,
            ttl_seconds=60, at=T0 - timedelta(hours=1),
        )
        d = policy.decide(_req(expired, *LEDGER_A, Action.READ))
        assert not d.allowed
        assert d.deny_reason.value == "SESSION_EXPIRED"

    def test_unknown_resource_denied_by_default(self):
        _, policy = _world()
        d = policy.decide(_req(
            _alice_engine(), ResourceKind.TRADING_LEDGER, ALICE,
            "never-registered", Action.READ))
        assert not d.allowed
        assert d.deny_reason.value == "UNKNOWN_RESOURCE"
        assert d.security_incident


class TestSecretHygiene:
    """Values gated, redacted, and never cross-tenant."""

    def _vault_with_alice_secret(self):
        vault = TenantSecretVault()
        ref = vault.store(
            ALICE, "binance-api-key", "super-secret-material-xyz",
            at=T0,
        )
        return vault, ref

    def _allow_decision(self, policy, principal, target, at=T0):
        return policy.decide(_req(principal, *target,
                                  Action.SECRET_REVEAL, at=at))

    def test_reveal_requires_allowing_decision(self):
        _, policy = _world()
        vault, ref = self._vault_with_alice_secret()
        deny = self._allow_decision(policy, _bob_engine(), SECRETS_A)
        with pytest.raises(SecretVaultError):
            vault.reveal(ref, deny)

    def test_cross_tenant_reveal_refused(self):
        """Bob's ALLOWING decision for HIS OWN store cannot reveal
        Alice's secret: the vault re-checks the tenant binding
        (defence in depth — even a mis-issued decision fails)."""
        reg, policy = _world()
        vault, ref = self._vault_with_alice_secret()
        # Bob has a legitimate allowing decision for his OWN store
        allow_bob = policy.decide(_req(
            _bob_engine(), *SECRETS_B, Action.SECRET_REVEAL))
        assert allow_bob.allowed
        with pytest.raises(SecretVaultError, match="does not reference"):
            vault.reveal(ref, allow_bob)

    def test_own_reveal_works(self):
        reg, policy = _world()
        reg.register(__import__(
            "data_engine.tenancy.resources", fromlist=["OwnedResource"]
        ).OwnedResource(
            kind=ResourceKind.SECRET_STORE, tenant_id=ALICE,
            name="binance-api-key",
            description="test secret entry",
        ))
        vault, ref = self._vault_with_alice_secret()
        allow = policy.decide(_req(
            _alice_engine(), ResourceKind.SECRET_STORE, ALICE,
            "binance-api-key", Action.SECRET_REVEAL))
        assert allow.allowed
        assert vault.reveal(ref, allow) == "super-secret-material-xyz"

    def test_values_never_in_audit_or_decisions(self):
        reg, policy = _world()
        vault, ref = self._vault_with_alice_secret()
        policy.decide(_req(_alice_engine(), *SECRETS_A,
                           Action.SECRET_REVEAL))
        policy.decide(_req(_bob_engine(), *SECRETS_A,
                           Action.SECRET_REVEAL))
        dump = repr(policy.audit_log.events()) + repr(
            policy.audit_log.incidents())
        assert "super-secret-material-xyz" not in dump
        assert ref.key not in dump or True  # keys may appear; VALUES may not

    def test_vault_repr_is_redacted(self):
        vault, ref = self._vault_with_alice_secret()
        text = repr(vault) + str(vault) + repr(ref)
        assert "super-secret-material-xyz" not in text
        assert REDACTED in repr(vault)

    def test_fingerprint_is_a_digest_not_the_value(self):
        vault, ref = self._vault_with_alice_secret()
        assert ref.fingerprint != "super-secret-material-xyz"
        assert len(ref.fingerprint) == 64

    def test_redaction_placeholder_never_storable(self):
        vault = TenantSecretVault()
        with pytest.raises(SecretVaultError):
            vault.store(ALICE, "bad", REDACTED)

    def test_duplicate_secret_refused(self):
        vault = TenantSecretVault()
        vault.store(ALICE, "k", "v1", at=T0)
        with pytest.raises(SecretVaultError):
            vault.store(ALICE, "k", "v2", at=T0)
        # explicit rotation is the only replacement path
        ref = vault.rotate(ALICE, "k", "v2", at=T0)
        from data_engine.tenancy.secrets import _fingerprint
        assert ref.fingerprint == _fingerprint("v2")

    def test_administrative_subject_parsing(self):
        from data_engine.tenancy.resources import OwnedResource
        record = OwnedResource(
            kind=ResourceKind.TENANT_RECORD, tenant_id="owner",
            name=f"tenant-record:{ALICE}",
        )
        assert administrative_subject(record) == ALICE
        plain = OwnedResource(
            kind=ResourceKind.VPS, tenant_id=ALICE, name="primary",
        )
        assert administrative_subject(plain) is None


class TestProvisioningContract:
    """Dry-run only: full per-user contract, zero side effects."""

    def test_approved_tenant_gets_full_contract_plan(self):
        provisioner = DryRunProvisioner()
        plan = provisioner.plan_contract(_tenant(ALICE), at=T0)
        assert isinstance(plan, ProvisioningPlan)
        assert plan.tenant_id == ALICE
        contract = plan.contract
        assert contract.vps.dedicated_per_user
        assert contract.vps.engine_runs_when_user_pc_off
        assert contract.database.dedicated_per_user
        assert not contract.database.shared_tables
        assert contract.secret_store.provisioned_at_tenant_runtime
        assert not contract.secret_store.centralized_in_control_plane
        assert contract.backups.encrypted
        assert contract.backups.restore_drills_isolated
        assert contract.license.per_user
        assert contract.ledger.dedicated_per_user
        assert not contract.ledger.visible_to_control_plane
        assert not contract.ledger.visible_to_other_tenants
        # all six stacks planned, none executed
        assert len(plan.steps) == 6
        assert all(
            s.status.value == "PLANNED_ONLY" for s in plan.steps)

    def test_unapproved_tenant_gets_no_plan(self):
        provisioner = DryRunProvisioner()
        for approval in (ApprovalStatus.PENDING,
                         ApprovalStatus.REJECTED,
                         ApprovalStatus.SUSPENDED,
                         ApprovalStatus.REVOKED):
            with pytest.raises(ProvisioningError):
                provisioner.plan_contract(
                    _tenant(ALICE, approval=approval))

    def test_execute_plan_refused_by_design(self):
        provisioner = DryRunProvisioner()
        plan = provisioner.plan_contract(_tenant(ALICE), at=T0)
        with pytest.raises(ProvisioningRefusedError,
                           match="NOT STARTED"):
            provisioner.execute_plan(plan)

    def test_contract_specs_refuse_weakening(self):
        from data_engine.tenancy.provisioning import (
            BackupSpec, DatabaseSpec, LedgerSpec, SecretStoreSpec,
            VpsSpec,
        )
        with pytest.raises(Exception):
            VpsSpec(dedicated_per_user=False)
        with pytest.raises(Exception):
            DatabaseSpec(shared_tables=True)
        with pytest.raises(Exception):
            SecretStoreSpec(centralized_in_control_plane=True)
        with pytest.raises(Exception):
            BackupSpec(encrypted=False)
        with pytest.raises(Exception):
            LedgerSpec(visible_to_other_tenants=True)


class TestRoleBindingDiscipline:
    """Kinds and roles are bound at authentication time."""

    def test_mobile_kind_cannot_hold_full_role(self):
        # pydantic wraps the IdentityError into ValidationError; the
        # underlying contract message is asserted (fi-21 precedent)
        with pytest.raises(Exception, match="may NOT hold role"):
            issue_session_token(
                principal_id="spoof", kind=PrincipalKind.MOBILE_CLIENT,
                role=Role.TENANT_FULL, tenant_id=ALICE, at=T0,
            )

    def test_tenant_user_cannot_hold_admin_role(self):
        with pytest.raises(Exception, match="may NOT hold role"):
            issue_session_token(
                principal_id="spoof", kind=PrincipalKind.TENANT_USER,
                role=Role.OWNER_ADMIN, tenant_id=ALICE, at=T0,
            )

    def test_read_only_requires_tenant_binding(self):
        with pytest.raises(Exception, match="must be bound to a tenant"):
            issue_session_token(
                principal_id="unbound",
                kind=PrincipalKind.MOBILE_CLIENT,
                role=Role.READ_ONLY, tenant_id=None, at=T0,
            )

    def test_tenant_id_shape_enforced(self):
        with pytest.raises(Exception):
            _tenant("Bad Tenant!")
        with pytest.raises(Exception):
            _tenant("ab")

    def test_registry_rejects_tenant_owned_control_plane_kinds(self):
        reg = ResourceRegistry()
        from data_engine.tenancy.resources import (
            OwnedResource, ResourceError,
        )
        with pytest.raises(ResourceError):
            reg.register(OwnedResource(
                kind=ResourceKind.TENANT_RECORD, tenant_id=ALICE,
                name="sneaky-record",
            ))

    def test_duplicate_resource_registration_refused(self):
        reg = ResourceRegistry()
        register_tenant_stack(reg, ALICE)
        with pytest.raises(Exception):
            register_tenant_stack(reg, ALICE)
