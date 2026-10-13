# LICENSING & PRIVATE-DISTRIBUTION BOUNDARY (BATCH 17 — ITEM C-5)

> **Document type:** boundary definition (mandate §6: "For private
> distribution, define licensing and entitlement checks with explicit
> failure behavior. Do not create an unapproved DRM mechanism, silently
> collect user data, or claim legal compliance without the relevant
> review.")
>
> **Version:** 1.0.0 · **Date:** 2026-10-13 · **Authority:** B —
> current supporting definition over the IMPLEMENTED tenancy surface
>
> **PAPER_READY = FALSE. LIVE TRADING NOT AUTHORIZED.**

## 1. What is IMPLEMENTED (security-level licensing — tested)

The repository implements **license-STATE access gating** as part of
the multi-user tenancy security foundation (Batch 4), pinned by
`tests/test_tenancy_security.py` (46 tests):

- Every tenant carries a **LICENSE** whose state gates ALL
  tenant-scoped access (`tenancy/identity.py:11-12`, states
  `ACTIVE / SUSPENDED / REVOKED / EXPIRED`; tenant lifecycle
  `PENDING → APPROVED` with `REJECTED / SUSPENDED / REVOKED`).
- The `LICENSE` resource is **control-plane-owned**: a tenant may READ
  its own license only; tenants cannot manage records, licenses or the
  control plane (`TestControlPlaneBoundary`).
- **Explicit failure behavior — DENY, never silent:**
  - inactive license denies EVERYTHING (`test_inactive_license_denies_everything`);
  - revocation is effective IMMEDIATELY
    (`test_license_revocation_is_effective_immediately`);
  - every allow AND deny decision is recorded in an append-only audit
    trail; denials carry `security_incident=True` where warranted;
  - expired sessions are denied everywhere — no forever tokens;
  - unknown resources are denied by default (closed vocabulary).
- Cross-tenant probing (claimed tenant-id manipulation) is DENIED and
  flagged as a `TENANT_ID_MANIPULATION` security incident.
- Secret hygiene under licensing: values never appear in audit records
  or decisions; vault repr is redacted; fingerprints are digests, not
  values; the redaction placeholder can never be stored as a value.

**Entitlement-check semantics (explicit failure behavior):** an access
request that fails licensing fails CLOSED with a recorded DENY reason
(`AuthorizationError` + `DenyReason`, closed vocabulary) — it never
falls back to allow, never silently degrades, and never leaks WHY
beyond the recorded audit channel.

## 2. What is NOT implemented (deliberately — operator product decisions)

- **Commercial entitlement issuance** — no payment integration,
  billing, plan/SKU management, seat counting, or license-key
  generation/verification exists. Building any of it without an
  operator-approved product design would be unapproved scope.
- **DRM of any kind** — none is created by this document or by the
  code. The implemented surface is server-side access gating for a
  privately distributed deployment; it makes no claim about preventing
  copying of software distributed to operator infrastructure.
- **No user-data collection** — nothing in the tenancy surface
  transmits telemetry or usage data anywhere; there is no collection
  path to disclose or opt out of. Any future analytics require an
  explicit operator decision and a privacy review.
- **No legal-compliance claim** — export-control, EULA, trademark,
  GDPR/DSA or other regulatory posture is NOT assessed here; that
  requires the relevant legal review (external dependency, see §4).

## 3. Required external inputs (secure processes only — never in-repo)

| Input | Process |
|---|---|
| Entitlement/product design (plans, issuance, billing) | Operator product decision recorded out-of-band; then a separately reviewed implementation batch |
| Signing keys (code/package/license signing) | Generated and held in an approved secret store; NEVER committed to this repository (secret scan enforces 0 credential-shaped strings across all history) |
| Production credentials | Provisioned through the tenancy secret vault / environment-variable boundary at deploy time; never in command histories, logs, or chat |
| Identity-provider configuration | If external IdP auth is adopted: operator-configured metadata delivered securely; the deny-default authorization layer stays the enforcement point |
| Legal review (EULA, distribution restrictions, privacy) | External counsel/operator review before any distribution event |

## 4. Verification commands (the implemented surface is test-pinned)

```bash
uv run pytest tests/test_tenancy_security.py -q      # 46 tests green
python3 scripts/batch9_gate_verify.py                # secret scan 0 across history
```

No claim in this document extends beyond the tested surface above.
