# BATCH 19 — PER-USER VPS AND OPERATIONAL DEPLOYMENT

> **Batch type:** deployment design + versioned templates with a
> locally-validated fail-closed validator (mandate §8; dependency-map
> item C-6). NO deployment was performed: no VPS provisioned, no
> billable infrastructure created, no public exposure, no production
> credentials. No push, merge, rebase, reset, or history rewrite.
>
> **Repository:** `muhammadasterschool-sketch/ai-trading-lab-data-engine`
> **Base commit:** `af3e303` (Batch 18 tip)
> **Dedicated branch:** `feat/batch-19-vps-deployment`
> **Date:** 2026-10-13
>
> **PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY.**
> **LIVE TRADING NOT AUTHORIZED.** Nothing in this batch changes either.

## 1. Delivered

1. **Deployment design spec — NEW** `docs/PER_USER_VPS_DEPLOYMENT.md`:
   per-user VPS model (one unprivileged engine instance per user;
   logical tenancy + physical host isolation), least-privilege OS
   account + systemd sandboxing, secret injection via root-owned 0600
   `EnvironmentFile` (names only — never values, never command
   history; journald sees names only), health/readiness/safe-shutdown
   semantics (the engine's honest 32-gate verdict + `Type=exec` +
   fail-closed startup + dashboard `shutdown()`), persistent storage +
   backup/restore via the runtime's LOAD→VERIFY→RESTORE→RECONCILE→
   RESUME-or-HALT protocol, restart recovery + NTP prerequisite +
   feed-watchdog monitoring, resource limits + redacted journald logs
   + incident vocabulary, network posture (loopback-only default; any
   public exposure = explicit operator TLS/proxy decision), versioned
   config + SHA-pinned rollback, and an honest verification-status
   table separating SIMULATED / LOCALLY TESTED / EXTERNALLY VERIFIED
   (the last is NONE).
2. **Versioned templates — NEW** `deploy/systemd/ai-trading-lab@.service`
   (per-user `%i` templated unit: 20 mandated hardening keys incl.
   `User=aitl-%i`, `NoNewPrivileges`, `ProtectSystem=strict`,
   `IPAddressDeny=any` + `IPAddressAllow=localhost`, `MemoryMax`/
   `CPUQuota`/`TasksMax`, `Restart=on-failure`, SIGTERM safe stop) and
   `deploy/config/secrets.env.example` (placeholder names ONLY — every
   secret-named entry empty; non-secret host/port config allowed).
3. **Fail-closed validator — NEW** `scripts/validate_deployment_
   templates.py`: 20/20 unit hardening keys, no credential-shaped
   values in ANY committed template, secret-named entries empty,
   6/6 mandated spec sections, simulated/local/external separation.
   **VERIFIED in the agent environment: 6/6 checks PASS.**

## 2. Mandate §8 requirement verdicts

| Mandate item | Status |
|---|---|
| Explicit per-user/per-tenant configuration boundaries | **PASS** — spec §1 + `%i` templated unit + per-user data roots |
| Least-privilege service accounts | **PASS** — `aitl-%i` (no shell/sudo) + sandboxing keys (validator-pinned) |
| Secure secret injection without credentials in command histories or logs | **PASS** — 0600 root-owned `EnvironmentFile`, names only; redaction layer; 0-secret scan |
| Service health checks, readiness reporting, safe shutdown | **PASS** — honest 32-gate readiness verdict + `Type=exec` + fail-closed startup + tested safe shutdown |
| Persistent storage, backup and restore procedures | **PASS** — spec §3 (runtime recovery protocol is the restore semantics; tested) |
| Restart recovery, clock synchronization, data-feed health monitoring | **PASS** — NTP prerequisite (UTC-required engine), `Restart=on-failure`, RUN-ST-1 watchdog + feed-gate staleness (operator opt-in posture B11-R-11 recorded) |
| Resource limits, operational logs, alerting, incident procedures | **PASS** — template limits (validator-pinned); redacted journald; alerting = operator monitoring choice; incident vocabulary exists |
| Network access restrictions and documented firewall requirements | **PASS** — loopback-only default posture; public exposure explicitly deferred to operator TLS/proxy decision |
| Versioned deployment configuration and rollback instructions | **PASS** — git-versioned templates + SHA-pinned wheel rollback (Batch 18 §2) |
| "Do not deploy to a real VPS / create billable infrastructure / expose publicly / configure production credentials" | **PASS** — NONE of those happened; the spec's verification table says EXTERNALLY VERIFIED = NONE |
| "A deployment guide is not proof of a successful deployment; report simulated / locally tested / externally verified separately" | **PASS** — §4 of the spec + this report's §3 |

## 3. Verification results (actual, honestly separated)

| Outcome class | Result |
|---|---|
| Simulated (design only) | The spec + templates — no deployment exists |
| Locally tested | `scripts/validate_deployment_templates.py` **6/6 PASS** (agent environment); full suite post-commit (worklog); frozen 11/11, manifest 13/13, secret scan 0 |
| Externally verified | **NONE** — deploying requires explicit operator authorization (VPS, DNS, TLS, credentials) |

## 4. Commands executed (exact)

```bash
uv run python scripts/validate_deployment_templates.py   # 6/6 PASS
uv run pytest -q -p no:cacheprovider                     # post-commit (worklog)
python3 /home/z/my-project/scripts/batch9_gate_verify.py # 11/11, 13/13, 0
```

## 5. Commit record

- New: `docs/PER_USER_VPS_DEPLOYMENT.md`,
  `deploy/systemd/ai-trading-lab@.service`,
  `deploy/config/secrets.env.example`,
  `scripts/validate_deployment_templates.py`, this report.
- Modified: `MASTER_DOCUMENTATION_INDEX.md` v2.23.0 → v2.24.0.
- Branch: `feat/batch-19-vps-deployment` from `af3e303`. Nothing
  pushed (B11-R-04 credential blocker).

## 6. Final verdict

**PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY. LIVE
TRADING NOT AUTHORIZED.** Batch 19 stops here. Next per the dependency
map: **Batch 20 — read-only mobile dashboard and operations
visibility**.
