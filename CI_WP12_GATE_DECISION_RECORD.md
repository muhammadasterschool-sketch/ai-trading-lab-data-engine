# CI / WP-12 GATE DECISION RECORD

**Document ID:** GOV-CIW-001 · **Version:** 2.0.0 · **Date:** 2026-10-10
**Status:** AUTHORIZED + IMPLEMENTED — `.github/workflows/ci.yml`
installed verbatim per WP_12_CI_IMPLEMENTATION_SPEC.md §3. The workflow
file is COMMITTED; it has NOT yet executed on GitHub Actions (no push
occurred this cycle — see §5), and NOTHING in this record claims any
external CI platform approval, run, or pass.
**Supersedes:** v1.0.0 (sha256
`6df8d890968b867e54b0dbd8555a7ed5a95700338797e4568048e4684c6d6308` at
commit `f1bfe02fab36724a439702e82dc83f9a851444fb` — the record whose
authorization block is completed below)

---

## 1. Current State (verified 2026-10-10)

- `.github/workflows/ci.yml` EXISTS as of this cycle (installed
  verbatim from the spec — byte-compared against the spec's §3 block).
- WP_12_CI_IMPLEMENTATION_SPEC.md v1.0.0 specified the approved CI gate
  design: full tests, deterministic repeat, frozen Phase 3 integrity,
  security/credential scan, untracked-file check, PIT checks,
  governance checks.
- Every gate the workflow encodes was executed LOCALLY this cycle (see
  §4) — local gates remain the executed verification of record until
  the workflow actually runs on the platform.

## 2. Operator Authorization Record (human principal's decision)

```text
Decision ID:     WP-12-CI-ENABLE
Decision:        install .github/workflows/ci.yml as specified in
                 WP_12_CI_IMPLEMENTATION_SPEC.md v1.0.0
Approver:        The repository operator (human principal)
Approver kind:   human (in-session operator authorization; no
                 signature fabricated)
Evidence:        Operator mandate, quoted verbatim:
                 "CI/WP-12: I authorize implementation of the
                 documented CI/WP-12 scope. Follow its authoritative
                 specification, security controls, and required
                 verification. Record this operator authorization
                 without fabricating a digital signature or claiming
                 that an external CI platform has approved or passed
                 anything it has not."
Channel:         zai-web (IM session web-a816f89a-8d02-42d6-b1a7-
                 6577eb1dc53e, chat 218858c8-6142-48a8-b177-
                 8668467ef6c4)
Recorded at:     2026-10-10 (PKT)
Executed by:     ZAI (controlled agent) — recording + implementation
                 only; the authorization is the operator's.
```

This satisfies the spec §5 approval-record format exactly (Decision ID
`WP-12-CI-ENABLE`; the spec's `<named human>` / `<logical timestamp>`
slots are filled by the operator's in-session authorization and the
2026-10-10 recording respectively — the mechanism every other
governance record in this repository uses; no digital signature is
invented).

## 3. What Was Installed (and NOT claimed)

- Installed: `.github/workflows/ci.yml` — VERBATIM the spec §3 YAML:
  push/PR triggers (main + phase-4a/**), `contents: read` permission,
  no `pull_request_target`, no secrets, Python 3.11/3.12 matrix,
  locked `uv sync --frozen --extra dev`, full suite + two determinism
  repeats, frozen-Phase-3 blob verification vs `main@13fdc7e`,
  history-wide secret scan, prediction red-team matrix.
- NOT claimed: any GitHub Actions run, pass, or platform approval. The
  workflow executes only after the commit carrying it is pushed; this
  cycle's commits remain LOCAL (the exposed PAT is compromised and
  unusable — operator §4 — and no secure credential channel is
  available in-session).

## 4. Local Mirror Verification (executed this cycle, 2026-10-10)

| WP-12 gate | Local execution result (this cycle) |
|---|---|
| full tests | 1,621 passed + 1 skipped (`uv run --frozen pytest -p no:cacheprovider -q`) |
| deterministic repeat | full suite ×2 identical counts (45.69s / second run recorded in the cycle report) |
| frozen Phase 3 integrity | 11/11 blobs identical to `main@13fdc7e` + 13/13 manifest (independent scripts, before AND after changes) |
| secret scan (history-wide, the workflow's own regex) | 0 matches — `git grep -qE "<workflow regex>" $(git rev-list --all)` exit 1 (no hits), verified locally BEFORE committing the workflow |
| prediction red-team matrix | included in the full-suite green run |
| untracked artifacts | `git ls-files --others --exclude-standard` empty |

## 5. Push/Execution Status (honest)

- Commits this cycle are LOCAL ONLY. Pushing requires a valid, secure,
  authorized credential; the chat-exposed PAT is compromised and is
  never used (operator mandate §4). The operator must push via a safe
  channel after PAT revocation/rotation, at which point the workflow's
  first push-triggered run will occur.
- Until an actual GitHub Actions run completes green, CI_GATE state
  remains: **AUTHORIZED + IMPLEMENTED (committed) — PLATFORM EXECUTION
  PENDING FIRST PUSH.** Nothing here reports a CI pass that did not
  happen.

## 6. Effect on Readiness

GOVERNANCE_READY's CI/WP-12 component is now SATISFIED by recorded
human decision + verbatim implementation. GOVERNANCE_READY as a whole
remains FALSE while its other documented components stay open
(real-data source approval, credential rotation confirmation,
keyed-MAC custody operational status — see the cycle's final report).
