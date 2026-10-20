# P0-P3 SECRETS / GOVERNANCE CHECKLIST (Task 7)

No secret values appear in this checklist (by construction).

## 1. Repository hygiene — verified this task

- [x] **Current tree + full history secret scan clean.** CI runs the
  all-history scan with the FIX-5/F-18b filter pipeline; verified
  green on this task's final commits. The synthetic-marker allowlist
  is pinned by `tests/test_secret_scan_allowlist.py` (a real-shaped
  `ghp_`/`github_pat_` token still FAILS the scan — negative control
  tested).
- [x] **No secrets in the new code.** `operator_approval.py` /
  `session_launch.py` / `soak_preflight.py` were written under the
  no-secrets rule; their tests generate keys with `secrets.*` at
  runtime and never embed literals (the Stage-F redaction-fixture
  discipline).
- [x] **`.gitignore` covers secret patterns**; `deploy/config/
  secrets.env.example` is placeholders-only (validated by
  `scripts/validate_deployment_templates.py` + tests).
- [x] **No credential in logs/exports**: MAC/approval keys never
  appear in `repr`/`str`/errors (`test_repr_never_leaks_material`,
  `test_error_messages_never_contain_key_material`).
- [x] **Token used for this task's push** is stored OUTSIDE the repo
  (`/home/z/my-project/.secrets/`, 0600), never printed, and the
  owner will revoke it after project completion (owner plan).
- [x] **Previously exposed credentials:** the audit found NO
  credential-shaped string in history requiring rotation beyond
  what the repo already tracks (GOV-03 tracks an earlier
  rotation-confirmation dependency — still open, owner-side; do not
  assume revocation happened without evidence).

## 2. Key custody model (two operator keys, same discipline)

| Key | Channel | Strength floor | Used by | Never |
|---|---|---|---|---|
| `RUNTIME_LEDGER_MAC_KEY[_FILE]` | env var or absolute key file outside repo | ≥ 32 bytes (hex or raw) | `MacCustody.from_environment` (ledger event HMAC) | logged, committed, defaulted |
| `OPERATOR_APPROVAL_MAC_KEY[_FILE]` (NEW, FIX-9) | same channels | ≥ 32 bytes | `OperatorApprovalKey.from_environment` (approval-record HMAC) | logged, committed, defaulted |

Both keys are read ONLY inside their `from_environment` loaders
(structural tests pin this; the readiness gates themselves read no
environment at all).

## 3. Auditable human approval records (FIX-9 model)

Every approval that can satisfy a HUMAN gate
(`REAL_DATA_READY`, `OPERATIONAL_FEED_READY`, `GOVERNANCE_READY`)
must be an `OperatorApprovalRecord`:

- `record_id`, `approval_kind` (SOURCE_APPROVAL /
  PAPER_ENVIRONMENT_AUTHORIZATION / RISK_LIMIT_CHANGE /
  KILLSWITCH_RESET / SOAK_START / SOAK_STOP / RECORDED_EVIDENCE),
  `principal`, `decision` (APPROVE/REJECT), `gate` (+ optional
  `scope`), `issued_at`, `expires_at` (tz-aware), `artifact_digest`
  (pins the approval to one session config when set), `reason`.
- Signed with the operator approval key (HMAC-SHA256 over the
  canonical serialization); re-verified by the composition root AND
  the soak preflight (expiry, scope, digest, signature).
- Fail-closed reason codes are stable and documented
  (`E_APPROVAL_*`, `E_EVIDENCE_UNTRUSTED`).
- **Not forgeable via arbitrary text**: plain free-text evidence for
  human gates is refused end-to-end (adversarial tests).

## 4. Approval records still required from the owner (GOV-03/04/05)

1. GOV-03: credential-rotation confirmation decision.
2. GOV-04: keyed-MAC provisioning record (key id + date + principal).
3. GOV-05: data-source approval decision (which feed source is
   approved for the operational feed, with scope).
Each must now be recorded AND SIGNED with the approval key to be
machine-verifiable at launch (see the owner action checklist).

## 5. Least-privilege posture (verified / documented)

- [x] Public-market-data credentials, if ever used, are read-only by
  design: the Binance public adapter REFUSES an api-key config
  (`api_key_env_var` set → construction error) — it physically
  cannot place orders.
- [x] Live order placement is structurally refused at four layers
  (L1-L4 proofs); no live credentials exist or are requested.
- [x] Monitoring/admin surfaces are token-gated, loopback-default,
  TLS-at-proxy; the admin registry is read-only with server-side
  data minimization (Stage F tests).
- [x] The owner is never asked to paste secrets into chat; keys are
  provisioned through env/file channels per the runbook
  (`docs/PAPER_OPERATOR_RUNBOOK.md`).

## 6. Local provisioning recipe (owner-side, no values in chat)

```
# 1. generate two strong keys OUTSIDE the repo (example sizes):
#    ledger MAC key + operator approval key (>= 32 bytes each)
# 2. store them in your secret store; export at launch time:
export RUNTIME_LEDGER_MAC_KEY_FILE=/secure/aitl-ledger-mac.key
export OPERATOR_APPROVAL_MAC_KEY_FILE=/secure/aitl-approval.key
chmod 600 /secure/aitl-*.key
# 3. sign approval records with the approval key (records + hex
#    signatures go into the launch plan's approvals file)
# 4. verify: data-engine soak-preflight <launch-plan.json>
```

## 7. Dependency / supply-chain checks (verified this run)

- [x] CI dependency audit job green on final commits.
- [x] Lockfile (`uv.lock`) consistent; Windows package installs with
  `--require-hashes` (validated package: see the Windows report).
- [x] SAST + lint jobs green (CI).
