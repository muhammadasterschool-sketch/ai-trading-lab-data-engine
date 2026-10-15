# BATCH 17 — SECURITY, MULTI-TENANCY AND PRIVATE ACCESS

> **Batch type:** audit + two verified-gap closures (opt-in dependency
> vulnerability scanning in CI; licensing/private-distribution boundary
> definition — dependency-map items C-5 + the mandate §6 dependency-
> scanning bullet). No source code was modified; no push, merge,
> rebase, reset, or history rewrite was performed.
>
> **Repository:** `muhammadasterschool-sketch/ai-trading-lab-data-engine`
> **Base commit:** `51c08ed` (Batch 16 tip)
> **Dedicated branch:** `audit/batch-17-security-tenancy-private-access`
> **Date:** 2026-10-13
>
> **PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY.**
> **LIVE TRADING NOT AUTHORIZED.** Nothing in this batch changes either.

## 1. Per-area audit (mandate §6 — first-hand anchors)

| # | Area | Status | Anchor evidence | Verdict |
|---|---|---|---|---|
| 1 | Authentication and authorization | IMPLEMENTED | `tenancy/identity.py`: tenant binding established AT AUTHENTICATION TIME inside the server-side `AuthenticatedPrincipal`; client-supplied tenant identifiers NEVER trusted (compared against the binding, mismatch = DENY + `TENANT_ID_MANIPULATION` incident). `tenancy/authorization.py`: deny-by-default closed vocabulary (`Action`/`DenyReason` enums); every decision allow AND deny recorded append-only | **PASS** |
| 2 | Tenant and account ownership boundaries | IMPLEMENTED | `TestControlPlaneBoundary`: owner manages tenant records/licenses; tenant READS own license/record only; tenant cannot manage records or control plane; control-plane service cannot read trading data | **PASS** |
| 3 | Cross-user resource access and isolation | IMPLEMENTED | `TestCrossUserAccessDenial`: alice↔bob mutual invisibility both directions; recipient cannot see owner data; positive control (own-tenant access works) | **PASS** |
| 4 | Secret provisioning, storage, rotation and redaction | IMPLEMENTED (provisioning/storage/redaction); rotation = documented operator procedure, no dedicated API | `tenancy/secrets.py` `SecretVault`: SHA-256 fingerprints (integrity, not values), `REDACTED` placeholder (never storable as a value), redacted `repr`, duplicate-secret refusal, reveal requires an ALLOWING decision, cross-tenant reveal refused; `brokers/redaction.py` scrub/redact machinery; env-var-only provider boundary (fail at construction if unset); 0 credential-shaped strings across ALL history (forensic gate). Advisory (LOW): an explicit `rotate()` API does not exist — the vault is in-process test-grade infrastructure; production secret storage/rotation is an external deploy-time concern (see the licensing boundary doc §3) | **PASS (rotation classified honestly)** |
| 5 | Session management and API access controls | IMPLEMENTED | Sessions are SHORT-LIVED with expiry; expired sessions denied everywhere (no forever tokens); dashboard: loopback-only stdlib server, exactly 2 GET routes, non-GET → 405, unknown → 404, no write surface, no template engine; `TestMobileReadOnly`: mobile cannot write anything, cannot read secret store/database, NO order-placement path exists, short-lived sessions | **PASS** |
| 6 | Audit-log integrity and sensitive-data minimization | IMPLEMENTED | Append-only authorization decisions with `security_incident` flags; secret values NEVER in audit records or decisions (tested); 9 hash-chained runtime ledgers; audit-log tamper evidence | **PASS** |
| 7 | Configuration validation and unsafe defaults | IMPLEMENTED | Frozen `extra="forbid"` config models (FS-17 — unknown keys raise); runtime validators (e.g. `max_feed_staleness_seconds` None-or-positive with refuse-otherwise); fail-closed defaults everywhere (no gate wired → no trading; unregistered venue → discovery refused); CI is secret-free by design with `contents: read` and no `pull_request_target` | **PASS** |
| 8 | Dependency and vulnerability scanning | **GAP CLOSED THIS BATCH (opt-in, honestly NOT VERIFIED locally)** | BEFORE: no vulnerability scanning existed anywhere (pip-audit absent locally; no scan step in CI). NOW: `audit-dependencies` job appended to `.github/workflows/ci.yml`, gated `workflow_dispatch` ONLY — never runs on push/PR, so the existing CI gate is bit-for-bit unchanged until an operator explicitly triggers it; exports ALL locked pins (`uv export --frozen`) and runs `pip-audit --strict --disable-pip` (fail-closed on ANY known vulnerability). VERIFICATION STATUS: **NOT VERIFIED in this environment** — no network/scanner available offline; the job must be triggered by the operator on GitHub (requires the pending push). Dependency surface itself is small and fully locked: direct deps pydantic/numpy/pandas/pytest (+ dev extras), `uv.lock` pinned | **PASS (mechanism added; execution EXTERNAL/NOT VERIFIED — no false claim)** |
| 9 | Access restrictions for administrative functions | IMPLEMENTED | Control-plane boundary (§2 above); kill-switch reset is unprivileged-refused (ARCH-F1); operator cancel/close are audited, loud refusals (RUN-CA-1); `authorize_live` structurally refuses live authorization from the platform package | **PASS** |
| 10 | Negative tests: unauthorized access / cross-tenant exposure / credential leakage rejected | IMPLEMENTED | `tests/test_tenancy_security.py` (46 tests): every category above has explicit negative tests incl. manipulation-before-lookup ordering, redaction-placeholder storage refusal, fingerprint-is-not-value; brokers: secret-leak `find_secret_leak`/`assert_no_secret_material` tests; suite green 2,333+1 | **PASS** |
| 11 | Private distribution: licensing/entitlement checks with explicit failure behavior; no unapproved DRM; no silent data collection; no legal-compliance claim | DEFINED + security level IMPLEMENTED | NEW `docs/LICENSING_PRIVATE_DISTRIBUTION_BOUNDARY.md` (item C-5): license-state gating is implemented and test-pinned (inactive denies everything; revocation immediate; DENY with recorded reason, closed vocabulary — never silent); commercial entitlement issuance/billing deliberately NOT built (operator product decision); NO DRM created; NO user-data collection path exists; NO legal-compliance claim made | **PASS (as boundary definition)** |
| 12 | Signing keys / production credentials / IdP config via secure external processes | BOUNDARY DOCUMENTED | Licensing doc §3: signing keys + production credentials + IdP configuration supplied only through approved external secret processes; NEVER in-repo (0-secret forensic gate enforces); values from chat are forbidden credential channels (exposures #19–#22 protocol) | **PASS (as boundary)** |

## 2. Changes made (smallest safe change)

1. `.github/workflows/ci.yml` — appended an OPT-IN
   `audit-dependencies` job (`workflow_dispatch` only; `contents: read`;
   fail-closed `pip-audit --strict` over the full locked export). The
   existing `test` job and all triggers are byte-unchanged; no test
   pins ci.yml (verified — zero references in `tests/`).
2. `docs/LICENSING_PRIVATE_DISTRIBUTION_BOUNDARY.md` — new boundary
   definition (C-5) with the tested implemented surface, the explicit
   DENY failure semantics, the deliberately-unbuilt commercial layer,
   and the secure-external-process requirements.
3. This report + index v2.21.0 → v2.22.0.

No `src/` changes; no behavior changes; no new claims beyond tested
surfaces.

## 3. Verification results (actual)

| Check | Result |
|---|---|
| Tenancy security suite | 46 tests green (within full suite) |
| Full suite at this batch's commit | recorded post-commit (worklog) — base was 2,333 + 1 skipped (79.14s) |
| Frozen contracts / manifest / secret scan | **PASS 11/11, 13/13, 0** across all history + working tree (re-run post-commit) |
| YAML sanity of the appended CI job | reviewed line-by-line; standard actions/steps; NOT executed (no network) — honestly NOT VERIFIED |
| Diff review | 4 files (ci.yml + licensing doc + report + index); no unrelated changes |

## 4. Commands executed (exact)

```bash
rg -n "LicenseState|LICENSE" src/data_engine/tenancy/identity.py
rg -n "^class |deny|incident" src/data_engine/tenancy/authorization.py
rg -n "^class |    def test_" tests/test_tenancy_security.py     # 46-test inventory
rg -n "run:|matrix|pytest" .github/workflows/ci.yml
rg -n "^class |rotate|provision|redact" src/data_engine/tenancy/secrets.py
rg -n "^name = " uv.lock; which pip-audit                        # NOT installed → gap confirmed
uv run pytest -q -p no:cacheprovider                             # post-commit (worklog)
python3 /home/z/my-project/scripts/batch9_gate_verify.py
```

## 5. Final verification verdict (per mandate §6)

| Mandate item | Status |
|---|---|
| Audit + close verified security gaps | **PASS** — dependency-vulnerability scanning gap closed with an opt-in fail-closed CI job (execution externally gated, honestly marked); licensing boundary defined (C-5) |
| Negative tests prove unauthorized access / cross-tenant exposure / credential leakage rejected | **PASS** — 46 tenancy tests + broker redaction tests, green |
| No unapproved DRM, no silent data collection, no legal-compliance claim | **PASS** — licensing doc §2 |
| Signing keys / credentials / IdP via secure external processes only | **PASS** — licensing doc §3; 0-secret gate |
| Read-only discipline for src/; PAPER_READY = FALSE / LIVE NOT AUTHORIZED preserved | **PASS** — 29 PASS / 3 FAIL unchanged |

**PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY. LIVE
TRADING NOT AUTHORIZED.** Batch 17 stops here. Next per the dependency
map: **Batch 18 — Windows installer and application packaging**.
