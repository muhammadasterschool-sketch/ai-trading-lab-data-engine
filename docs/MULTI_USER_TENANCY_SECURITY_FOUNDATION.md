# MULTI-USER TENANCY SECURITY FOUNDATION — DESIGN AND CONTRACTS

```text
Document Type:  Security design + contracts + enforcement primitives (Batch 4)
Phase:          Multi-User Security Foundation (runtime-risk-safety mandate Batch 4)
Authority:      A — AUTHORITATIVE for the tenancy security design
Status:         CURRENT (foundation implemented: identity, ownership,
                 authorization, secrets, dry-run provisioning contracts;
                 NO production multi-tenancy — see the non-claims)
Version:        1.0.0
Last Updated:   2026-10-12
```

---

## 0. Product context and honest scope

The platform's product goal: a privately distributed, secure
multi-user trading platform serving **one owner plus a small set of
individually approved recipients** (target ~20+ users, each
individually approved). Every user receives a DEDICATED, isolated
stack (VPS, database, secrets, backups, license, trading ledger);
owner data is not visible to recipients; recipients are mutually
invisible.

**What this document's implementation IS:**

- The FOUNDATION layer: tenant identity + approval/license
  lifecycle, short-lived authenticated principals, a server-side
  authoritative resource-ownership registry, a deny-by-default
  authorization policy with a complete capability matrix, a
  per-tenant secret vault contract, and the per-user infrastructure
  provisioning CONTRACT with a dry-run-only provisioner.
- Executable security tests for every isolation property
  (46 tests in `tests/test_tenancy_security.py`).

**What this implementation is NOT (explicit non-claims):**

- NOT production-ready multi-tenancy: there is no authentication
  provider, no token issuing service, no network surface, no public
  API, no real VPS/database provisioning, no mobile application,
  and no end-to-end deployment. Claiming otherwise would require
  that infrastructure plus end-to-end tests that do not exist.
- NO paid infrastructure is provisioned or contacted from this
  code; `DryRunProvisioner.execute_plan` refuses by design.
- Mobile clients exist ONLY as the READ_ONLY role in the
  authorization matrix — there is no order-placement path reachable
  by a read-only principal, and mobile order placement is NOT
  implemented (product decision: read-only dashboard first).

---

## 1. Threat model (abbreviated, control-mapped)

| Threat | Control |
|---|---|
| A recipient reads another recipient's trading data | Cross-tenant denial (ownership matrix) + dedicated per-tenant stores (no shared database) |
| A recipient reads the owner's data | Same isolation rules protect the owner tenant |
| A client spoofs a tenant id (header/payload) to reach foreign data | The tenant binding comes from the AUTHENTICATED principal only; a divergent claim is denied + recorded as a security incident |
| The control plane becomes a honeypot of everyone's secrets/history | Control-plane boundary: admin roles are structurally denied tenant trading data; secrets provision at each tenant's own VPS |
| A revoked/suspended/expired user keeps trading | License gate on EVERY tenant-scoped access; revocation is effective immediately |
| A stolen long-lived token | Short-lived sessions (max 24 h, default 15 min; renewal = re-authentication) |
| A mobile client submits orders | READ_ONLY role: no WRITE/ORDER_SUBMIT/SECRET_REVEAL action is allowed for any resource kind — no order path exists for mobile |
| Secret values leak into logs/audit/decisions | Vault: authorization-gated reveals, redacted reprs, fingerprints instead of values, values never recorded |

---

## 2. Tenant identity, approval and license lifecycle

`src/data_engine/tenancy/identity.py`

- `TenantRecord` — the ONLY per-tenant control-plane record
  (tenant slug, display name, approval + license state). It
  deliberately contains no trading data, no secrets, no history.
- `ApprovalStatus`: PENDING → APPROVED (owner-approved; the only
  state that may be provisioned) / REJECTED / SUSPENDED / REVOKED.
- `LicenseState`: ACTIVE / SUSPENDED / REVOKED / EXPIRED — gates
  ALL tenant-scoped access.
- `AuthenticatedPrincipal` — short-lived (TTL ≤ 24 h, helper
  default 15 min); carries the server-side tenant binding; the
  role/kind binding is validated at construction (a mobile
  principal can never hold TENANT_FULL, a tenant user can never
  hold OWNER_ADMIN, read-only principals must be tenant-bound).

## 3. Server-side resource ownership

`src/data_engine/tenancy/resources.py`

- `ResourceKind`: TENANT_RECORD, VPS, DATABASE, SECRET_STORE,
  BACKUP_ARCHIVE, LICENSE, TRADING_LEDGER, EXECUTION_SESSION,
  CONTROL_PLANE.
- `ResourceRegistry` — the authoritative, deny-by-default registry:
  unregistered resource ⇒ no owner ⇒ no access. TENANT_RECORD and
  CONTROL_PLANE kinds belong to the control-plane namespace by
  construction (registration of tenant-owned copies is refused).
- `register_tenant_stack()` — the standard per-user stack (VPS +
  database + secret store + backup archive + isolated trading
  ledger + engine session); `register_tenant_administrative_records()`
  registers the control-plane-owned tenant record + license with the
  SUBJECT tenant encoded in the name (`license:<tenant>`).
- `administrative_subject()` — administrative ownership is NOT data
  ownership: the subject tenant keeps read visibility of its own
  record/license; only admin roles manage them.

## 4. Authorization (deny-by-default, server-side)

`src/data_engine/tenancy/authorization.py`

Decision procedure (fail-closed at every step, every decision
audited to `SecurityAuditLog`):

1. session validity (SESSION_EXPIRED),
2. claimed-tenant consistency — the client-supplied
   `claimed_tenant_id` is compared against the authenticated
   binding; mismatch ⇒ TENANT_ID_MANIPULATION + security incident
   (checked BEFORE resource lookup, so probes cannot enumerate),
3. resource existence (UNKNOWN_RESOURCE, incident-flagged),
4. license gate for the SUBJECT tenant (LICENSE_INACTIVE),
5. the role/ownership matrix (CROSS_TENANT / ROLE_REQUIRED /
   NOT_ALLOWED_BY_POLICY / DENY_DEFAULT).

Capability matrix:

- **READ_ONLY (mobile)**: READ only, on TRADING_LEDGER,
  EXECUTION_SESSION, LICENSE, TENANT_RECORD (own subject),
  BACKUP_ARCHIVE, VPS — the dashboard surface (P&L, equity,
  drawdown, positions, history, fees, health, alerts). No WRITE of
  any kind; no ORDER_SUBMIT; no SECRET_REVEAL; no DATABASE reads.
- **TENANT_FULL (recipient engine/desktop)**: READ/WRITE all own
  tenant resources; ORDER_SUBMIT on the own EXECUTION_SESSION;
  SECRET_REVEAL on the own SECRET_STORE; READ own license/record;
  no MANAGE/PROVISION.
- **CONTROL_PLANE / OWNER_ADMIN**: MANAGE tenant records + licenses
  of any tenant; PROVISION (dry-run); READ/WRITE/MANAGE the
  CONTROL_PLANE surface; the owner's OWN tenant stack via the
  tenant matrix (the owner is a tenant too). DENIED all recipient
  trading-data access (ledgers, databases, secrets, backups, VPS,
  sessions) — the control-plane boundary.

## 5. Secrets

`src/data_engine/tenancy/secrets.py` — per-tenant vault
(in-memory foundation): opaque `SecretRef` handles (sha256
fingerprint, never the value); `reveal` requires a PRIOR ALLOWING
authorization decision for the exact ref (the vault re-checks the
tenant binding — defence in depth: even a mis-issued decision for
another tenant cannot reveal); redacted reprs; the redaction
placeholder is not storable; explicit rotation only.

## 6. Per-user provisioning contract (dry-run only)

`src/data_engine/tenancy/provisioning.py`

- `TenantResourceContract`: VPS (dedicated, cloud-resident — the
  engine runs while the user's PC is off), DATABASE (dedicated, no
  shared tables), SECRET_STORE (provisioned at the tenant's own
  runtime, never centralized), BACKUP_ARCHIVE (encrypted, isolated
  restore drills), LICENSE (per-user, revocable), TRADING_LEDGER
  (isolated; invisible to other tenants AND to the control plane).
  Every spec REFUSES weakening at construction.
- `DryRunProvisioner`: `plan_contract` (APPROVED tenants only) → a
  validated plan with PLANNED_ONLY steps; `execute_plan` ALWAYS
  raises `ProvisioningRefusedError` — real provisioning is NOT
  STARTED and no paid infrastructure may be touched from this code.

## 7. Control-plane boundary (the design rule)

The control plane (owner + administrative service) owns and
manages: tenant approval records, license states, provisioning
PLANS. It is structurally denied: recipient trading ledgers,
databases, secret values, backups, VPS internals and execution
sessions. Trading state and secrets live ONLY in each tenant's
dedicated stack (provisioned at the tenant's own VPS at runtime).
Consequences: a control-plane compromise exposes administrative
metadata, NOT trading history or credentials; owner data is
protected by the same tenant isolation as everyone else's.

## 8. Mobile read-only policy

Mobile clients authenticate as `MOBILE_CLIENT` principals with the
`READ_ONLY` role. The dashboard reads (ledger, session health,
license, backup status, VPS health) are the ONLY allowed actions.
There is no order-placement code path for any read-only principal —
the matrix denies ORDER_SUBMIT for every resource kind, and only
TENANT_FULL (the recipient's own engine on their own VPS) may ever
submit orders. Mobile order placement is NOT implemented and would
require an explicit product + security review to add.

## 9. Verification

`tests/test_tenancy_security.py` — 46 tests: cross-user denial
(mutual invisibility both directions, owner-data protection,
positive controls), the control-plane boundary (owner/admin denied
trading data; admin record/license management works; tenant status
visibility), tenant-ID manipulation (mismatch denied + audited,
matching claim harmless, gate precedes resource lookup), mobile
read-only (no writes on any kind, dashboard surface readable, no
order path exists — structural proof over the registry, short-lived
tokens only), license/session gating (all inactive states, instant
revocation, expiry, unknown resources), secret hygiene (gated
reveals, cross-tenant refusal even with a foreign ALLOWING
decision, values never in audit/decisions/reprs, fingerprint
discipline, rotation), provisioning contract (full six-stack plan,
unapproved refusal, execution refused by design, specs refuse
weakening), role-binding discipline (kind↔role binding, tenant-id
shape, registry namespace rules).

## 10. Remaining work (explicit, NOT claimed)

- Real authentication/token service, public API surface, transport
  security: NOT STARTED.
- Real per-user VPS/database/backup provisioning: NOT STARTED
  (dry-run only; operator authorization required).
- Durable, tamper-evident security audit log (currently in-memory):
  NOT STARTED.
- Mobile application + Apple/Android distribution investigation:
  NOT STARTED.
- Windows signed private installer: NOT STARTED.
- End-to-end multi-tenant deployment tests: NOT STARTED — until
  they exist, production-ready multi-tenancy is NOT claimed.
