# READINESS EVIDENCE INVENTORY

```text
Document ID:     GOV-REI-001
Version:         1.0.0
Date:            2026-10-13 (Asia/Karachi)
Document Type:   Documentation-only evidence inventory (no code path,
                 no gate logic, no verdict computation)
Authority:       B — CURRENT SUPPORTING (the readiness AUTHORITY is
                 readiness.py + PAPER_TRADING_READINESS_FINAL_REPORT.md;
                 this inventory RECORDS evidence, it never manufactures,
                 upgrades, or substitutes it)
Status:          CURRENT — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY
Scope:           the THREE unresolved gates of the 32-gate paper-
                 readiness system (the 29 PASS gates are recorded in
                 the final report §16 and are deliberately NOT
                 duplicated here)
Companion docs:  docs/PAPER_READINESS_GATE.md (v2.2.0 — gate spec)
                 PAPER_TRADING_READINESS_FINAL_REPORT.md (§15 blockers,
                 §16 verdict — this inventory is the per-evidence-item
                 expansion of §15, not a replacement)
                 docs/reports/BATCH_8_INDEPENDENT_RUNTIME_AUDIT.md
                 (§7 gate audit, §10 operator actions)
Pinning tests:   tests/test_readiness_evidence_inventory.py
                 (structural integrity — see §8)
```

---

## 1. Purpose and scope

This inventory gives the operator ONE place to see, for every evidence
item required by the three unresolved readiness gates, its exact
status, where its evidence lives, who owns or may approve it, when it
was last verified, whether it expires, why it is unresolved, and what
the next authorized action is. It exists so that release readiness is
tracked at the evidence level rather than the gate level: a gate
verdict is a consequence, and every consequence in this inventory
traces back to named evidence items that either exist or do not.

The three tracked gates and their gate-level verdicts as of this
version (unchanged from Batch 8, re-verified first-hand in Batch 9 —
see §9):

- **REAL_DATA_READY — FAIL**
- **OPERATIONAL_FEED_READY — FAIL**
- **GOVERNANCE_READY — FAIL**

`PAPER_READY = FALSE` — `BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY`.
**LIVE TRADING NOT AUTHORIZED** — nothing in this inventory touches
the live boundary, and this inventory can never authorize it.

## 2. How to read the item tables

Every evidence item is one row with ten fields:

| Field | Meaning |
|---|---|
| Item | Stable ID (`RDR-*` real data, `OFR-*` operational feed, `GOV-*` governance) |
| Evidence required | The concrete requirement this item tracks |
| Status | `PASS`, `FAIL`, or `UNVERIFIED` — closed vocabulary, no soft statuses |
| Evidence class | `VERIFIED_EVIDENCE` (machine-checked / executed first-hand), `RECORDED_DECISION` (human decision recorded in-repo, cited by decision ID), `OPERATOR_ACTION_REQUIRED` (open human action — the assertion has NOT been made), `UNVERIFIED_EXTERNAL` (an external check that has not been performed) |
| Evidence location / reference | Where the evidence lives, or where it will live once produced |
| Owner / approver role | Who owns the evidence or is authorized to approve it |
| Verified at | Verification timestamp where available; `—` where nothing has been verified |
| Expiry / revalidation | When the evidence must be revalidated; `—` where not applicable |
| Unresolved reason | The explicit reason the status is not PASS |
| Next operator action | The next authorized action; `none …` where the item is closed or nothing is actionable |

Items are stably ordered: ascending item ID within each gate, gates in
the order REAL_DATA_READY → OPERATIONAL_FEED_READY → GOVERNANCE_READY.
The ordering is deterministic by construction so that any future
reordering is a deliberate, reviewable diff.

## 3. Evidence integrity rules (binding on this inventory)

1. **Verified evidence is distinguished from operator assertions.**
   Every row declares its evidence class. Only `VERIFIED_EVIDENCE`
   (machine-checked, first-hand executed, reproducible) and
   `RECORDED_DECISION` (a human decision that exists as a citable
   in-repo record with a decision ID) may carry status `PASS`.
   An `OPERATOR_ACTION_REQUIRED` or `UNVERIFIED_EXTERNAL` row is an
   assertion that has NOT been made or a check that has NOT been run —
   it can never be `PASS`.
2. **Missing evidence never converts to PASS.** An absent, stale,
   partial, or unverifiable item is recorded `FAIL` or `UNVERIFIED`
   with its explicit reason — never silently promoted, never dropped
   from the inventory to make a gate look better.
3. **Registration is not trading eligibility.** An instrument or
   dataset being REGISTERED (discovered, catalogued, imported) is a
   weaker fact than being eligible for trading; the inventory never
   records registration, discovery, or import as evidence of trading
   eligibility or paper activation.
4. **`REAL_UNVERIFIED` is not `REAL_VERIFIED`.** Unverified or
   incomplete market data is never recorded as real verified data;
   synthetic data can never satisfy a real-data item (structurally
   refused by the data gate).
5. **A mock broker adapter is never a real broker integration.**
   Mock-deterministic adapters (paper, MT5-style, Binance, Bybit,
   Bitget, runtime-authoritative) prove semantics only — no real
   connectivity, no real credentials, no real orders — and are never
   recorded as real-broker evidence. No real broker adapter exists in
   this repository.
6. **Source approval, key provisioning, and human sign-off are
   recorded as completed ONLY when independently evidenced** — a
   recorded decision ID, a provisioning log entry, or an executed
   verification. An intention, a plan, or machinery being "ready" is
   not completion.
7. **No secrets in this inventory.** No tokens, API keys, passwords,
   private key material, or sensitive account information may appear
   here or be added here; credential items reference their custody
   records (fingerprint-only) instead of any secret value.
8. **Frozen artifacts and compatibility contracts are preserved.**
   This inventory changes no code, no frozen blob, no manifest, and
   no gate logic; it is documentation-only and pinned by structural
   tests (§8) so that its weakening is detectable.

## 4. Gate evidence inventories

### Gate REAL_DATA_READY

Requirement: at least one dataset that passed the complete nine-stage
chain `DATA_SOURCE_APPROVED → ACQUIRED → VALIDATED → QUALITY_GATE →
PIT_VERIFIED → PROVENANCE_VERIFIED → COVERAGE_VERIFIED → REPLAYABLE →
REAL_VERIFIED` (REAL_DATA_READINESS_CONTRACT.md; synthetic promotion
structurally refused). The long-term research corpus
(`VERIFIED_YEARS > 0`) is tracked separately under GOV-HDD-001 and is
not a paper-activation requirement.

| Item | Evidence required | Status | Evidence class | Evidence location / reference | Owner / approver role | Verified at | Expiry / revalidation | Unresolved reason | Next operator action |
|---|---|---|---|---|---|---|---|---|---|
| RDR-01 | Human SRC-APPROVAL for a real dataset source (policy §7.1 decision record) | FAIL | OPERATOR_ACTION_REQUIRED | docs/OPERATOR_SOURCE_APPROVAL_PACK.md §5–§6; PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md §7.1; src/data_engine/prediction/source_registry.py (human-only approval API) | Named human operator | — | Revalidate on provider or licence change | No SRC-APPROVAL decision exists for any dataset source; the registry structurally rejects AI approvals | Review the candidate evidence, fill the §5 template EXACTLY, record the decision via the §6 commands |
| RDR-02 | Licence and provider identity confirmed for the operator master bundle | UNVERIFIED | UNVERIFIED_EXTERNAL | MASTER_MARKET_DATA_IMPORT_RECORD.md §5; data/manifests/master/ provenance blocks | Named human operator | — | Revalidate per dataset before promotion | Provider, licence, download URL and timezone are UNKNOWN for all four files (licence_verified=false); user-supplied files carry approval-to-use, which is NOT a source approval | Identify the original provider and confirm the licence basis for each dataset considered for promotion |
| RDR-03 | One dataset through the nine-stage chain to REAL_VERIFIED | FAIL | VERIFIED_EVIDENCE | src/data_engine/runtime/data_gate.py; REAL_DATA_READINESS_CONTRACT.md §4; tests/test_data_engine.py | Engineering (chain execution); operator (source approval) | 2026-10-13 (in-suite; Batch 8 §7 re-verification) | Revalidate per dataset acquisition (content hash pinned) | Zero REAL_VERIFIED datasets exist; RealDataReadiness.report() records datasets_registered = 0, gate = BLOCKED_ON_REAL_DATA — the chain machinery is implemented and green but no dataset has entered it | Acquire data from an approved source and run the chain (ingest, validate, quality, PIT, provenance, manifest, replay, register) |
| RDR-04 | Master-bundle registration state recorded honestly | FAIL | VERIFIED_EVIDENCE | MASTER_MARKET_DATA_IMPORT_RECORD.md §4 and §8; data/manifests/master/; tests/test_master_datasets.py (55 tests) | Engineering | 2026-10-11 (registration); re-verified 2026-10-13 (in-suite) | Re-audited on every suite run by the committed-bundle integration tests | 3 REAL_UNVERIFIED + 1 INVALID datasets registered (521 instruments); REAL_UNVERIFIED may back research eligibility but never paper activation; registration is not trading eligibility | None for this item (honest state recorded); the promotion path is RDR-01, RDR-02, RDR-03 |
| RDR-05 | Metals impossible-OHLC rows corrected or provider-resolved | FAIL | VERIFIED_EVIDENCE | MASTER_MARKET_DATA_IMPORT_RECORD.md §4.4 (19 quarantined rows) | Engineering (quarantine); operator (provider data) | 2026-10-11 (audit); re-verified 2026-10-13 (in-suite) | Revalidate if provider data is supplied | 19 impossible-OHLC rows are quarantined INVALID; correction requires original provider data that was never supplied | Obtain provider-derived corrections before any metals promotion |
| RDR-06 | Research-history corpus verified years above zero | FAIL | RECORDED_DECISION | HISTORICAL_DATA_DEFERRAL_RECORD.md (GOV-HDD-001, 2026-10-10); feed_gate.py RESEARCH_HISTORY_STATUS | Named human operator (deferral decision) | Decision recorded 2026-10-10 | Revalidate when the deferral is revisited | VERIFIED_YEARS = 0; the long-term corpus is DEFERRED by operator decision GOV-HDD-001 — honestly reported, never claimed satisfied, and not a paper-activation blocker | None required for paper activation; acquisition remains a future operator decision |

**Gate verdict: FAIL** — zero REAL_VERIFIED datasets; every promotion
prerequisite (RDR-01, RDR-02) is an open human/data action.

### Gate OPERATIONAL_FEED_READY

Requirement: a genuine, validated, fresh, correctly-mapped current
market feed for the traded symbol and timeframe from a
human-approved source (APPROVED_FOR_PRODUCTION with
production-ingestion scope), with enough bars for the strategy's
indicator warm-up window — evaluated fail-closed by
`src/data_engine/runtime/feed_gate.py`
(`evaluate_operational_feed`), which reads no environment and never
fabricates an approval.

| Item | Evidence required | Status | Evidence class | Evidence location / reference | Owner / approver role | Verified at | Expiry / revalidation | Unresolved reason | Next operator action |
|---|---|---|---|---|---|---|---|---|---|
| OFR-01 | SRC-APPROVAL for the binance-public-spot candidate (APPROVED_FOR_PRODUCTION, production-ingestion scope) | FAIL | OPERATOR_ACTION_REQUIRED | docs/OPERATOR_SOURCE_APPROVAL_PACK.md §3, §5, §6; src/data_engine/platform/feed_source_candidates.py | Named human operator | — | Revalidate on Binance terms or endpoint change | The candidate remains UNVETTED — no human approval decision recorded; the registry structurally rejects AI approvals | Review the §3 evidence, fill the §5 template EXACTLY, record via the §6 commands on the paper-session host |
| OFR-02 | Binance Terms of Use and API Terms reviewed and confirmed | UNVERIFIED | UNVERIFIED_EXTERNAL | docs/OPERATOR_SOURCE_APPROVAL_PACK.md §3 (UNKNOWN list) | Named human operator | — | Revalidate on document revision | Terms are NOT reviewed and NOT confirmed; a licence basis of UNKNOWN is not approvable | Review the current documents and record the exact document identity and review date |
| OFR-03 | Jurisdiction and availability check from the actual paper-session host | UNVERIFIED | UNVERIFIED_EXTERNAL | scripts/binance_public_smoke.py; docs/PAPER_OPERATOR_RUNBOOK.md §3 | Paper-session host operator | — | Revalidate per deployment environment change | The single manual connectivity observation (five BTCUSDT 15m klines) was NOT taken from the deployment host and proves nothing about continuity | Run the smoke script on the actual paper-session host and record the result |
| OFR-04 | Reliability and continuity observation over an operator-chosen period | UNVERIFIED | UNVERIFIED_EXTERNAL | docs/OPERATOR_SOURCE_APPROVAL_PACK.md §3 (evidence item 3) | Operator (environment) | — | Continuous once provisioned (feed watchdog opt-in, RUN-ST-1) | UNMEASURED — the repository ships no scheduler; a single successful fetch says nothing about continuity | Schedule smoke runs for an observation period the operator considers sufficient |
| OFR-05 | Provisioned operational feed and an evaluate_operational_feed PASS on live inputs | FAIL | VERIFIED_EVIDENCE | src/data_engine/runtime/feed_gate.py; tests/test_feed_composition.py (29 tests); PAPER_TRADING_READINESS_FINAL_REPORT.md §15.1 | Engineering (machinery); operator (provisioning) | 2026-10-13 (machinery re-verified in-suite) | Per-session evaluation (freshness tolerance default 900 s; warm-up bars; canonical mapping) | Machinery COMPLETE and integration-proven — an UNVETTED source refuses runtime start — but no feed is provisioned and no live evaluation has been run | Provision the feed on the paper-session host, run the gate evaluation, record the OperationalFeedReport |
| OFR-06 | Blocked-market register current and honest (forex, stocks, metals 15 m) | FAIL | VERIFIED_EVIDENCE | docs/OPERATOR_SOURCE_APPROVAL_PACK.md §4 | Engineering (register); operator (future source decisions) | 2026-10-11 (pack v1.0.0) | Revalidate when a genuine candidate source is identified | No genuine 15-minute OHLC source identified or validated for any of the three markets; approving without a source would fabricate readiness | Identify and validate genuine intraday sources before any approval consideration for these markets |

**Gate verdict: FAIL** — no human-approved genuine feed source exists
and no feed is provisioned; the machinery is complete and honest, and
that is all that can be said.

### Gate GOVERNANCE_READY

Requirement: the governance evidence class — recorded human
decisions and their operational consequences (no code path can
fabricate them). Closed components are recorded as PASS with their
decision IDs; open components stay FAIL/UNVERIFIED.

| Item | Evidence required | Status | Evidence class | Evidence location / reference | Owner / approver role | Verified at | Expiry / revalidation | Unresolved reason | Next operator action |
|---|---|---|---|---|---|---|---|---|---|
| GOV-01 | H-1 hypothesis-framework ratification recorded | PASS | RECORDED_DECISION | H1_RATIFICATION_DECISION_RECORD.md (GOV-H1-002-RATIFY, Option A containment) | Repository operator (decision recorded) | Recorded 2026-10-10; re-verified 2026-10-13 (Batch 8 §7) | None — immutable historical decision | — (closed) | None — the decision is recorded and closed |
| GOV-02 | CI and WP-12 authorization recorded and installed | PASS | RECORDED_DECISION | CI_WP12_GATE_DECISION_RECORD.md (WP-12-CI-ENABLE); MASTER_MARKET_DATA_IMPORT_RECORD.md §10.4 (platform CI run 38147316090 SUCCESS observed at 4e6dfc5) | Repository operator (decision recorded) | Decision recorded 2026-10-10; platform execution observed 2026-10-11 | CI status revalidates per push or PR (current advanced heads UNVERIFIED — see GOV-06) | — (closed: decision recorded, workflow installed, one platform run observed to conclusion) | None for the decision itself; see GOV-06 for current-head CI verification |
| GOV-03 | Exposed-PAT revocation and rotation confirmed | FAIL | OPERATOR_ACTION_REQUIRED | PAPER_TRADING_READINESS_FINAL_REPORT.md §15.3a; docs/reports/BATCH_8_INDEPENDENT_RUNTIME_AUDIT.md §10.1 (exposure count 19) | Repository operator (token owner) | — | Immediate; re-opens on any future exposure | A fine-grained GitHub PAT was exposed in operator chat (exposure count 19, still present in conversation history); no revocation or rotation has been confirmed through any authorized secure channel, so authenticated repository operations remain prohibited for agents | Revoke the exposed token at GitHub Settings → Developer settings → Fine-grained tokens; establish a replacement credential OUTSIDE chat; confirm rotation through a secure channel |
| GOV-04 | Keyed-MAC custody operational (genuine key provisioned) | FAIL | OPERATOR_ACTION_REQUIRED | KEYED_MAC_CUSTODY_DECISION_RECORD.md §4–§6 (GOV-KMC-001); docs/PAPER_OPERATOR_RUNBOOK.md §5; tests/test_mac_custody.py (28 tests) | Operator-appointed key custodian | Decision and mechanism verified 2026-10-10; re-verified 2026-10-13 (in-suite) | Rotate on custodian or host change; append fingerprint-only log entry per provisioning | Custody status is IMPLEMENTED and NOT OPERATIONAL — the §6 provisioning log records none provisioned; no key was invented | Generate at least 32 random bytes on a trusted machine; provision RUNTIME_LEDGER_MAC_KEY or RUNTIME_LEDGER_MAC_KEY_FILE (absolute path outside the repository); record the FINGERPRINT only in §6 |
| GOV-05 | Data-source approval decision recorded | FAIL | OPERATOR_ACTION_REQUIRED | docs/OPERATOR_SOURCE_APPROVAL_PACK.md §5–§6 (shared with RDR-01 and OFR-01) | Named human operator | — | Revalidate on licence or terms change | The decision template and the recording commands are ready; no decision has been recorded | Decide on the binance-public-spot candidate per the pack's evidence requirements (terms review, host availability, continuity observation) |
| GOV-06 | CI check-runs verified for the current open PR heads (PR 1 at 7f384e6, PR 2 at d945833) | UNVERIFIED | UNVERIFIED_EXTERNAL | docs/reports/BATCH_8_INDEPENDENT_RUNTIME_AUDIT.md §1 (API 401); docs/reports/BATCH_9_RELEASE_READINESS_EVIDENCE_AUDIT.md Task 1 (API 403, rate-limited) | Repository operator | — | Revalidates per push or PR state change | Check-run state could not be retrieved — unauthenticated REST probes returned HTTP 403 (rate limit), the exposed PAT cannot be used because rotation is unconfirmed (GOV-03), and no replacement credential exists; the historical platform CI run 38147316090 SUCCESS was observed at 4e6dfc5, which is not either current head | Verify CI status via the GitHub interface or an authenticated API call with a valid rotated credential before any merge decision |

**Gate verdict: FAIL** — two of the governance components are closed
with recorded decisions (GOV-01, GOV-02); the open components
(GOV-03, GOV-04, GOV-05, GOV-06) are human or credential dependencies
that no code may fabricate.

## 5. What would and would not change the verdicts

Closing RDR-01 + RDR-02 + RDR-03 (a genuinely approved source, a
confirmed licence, one dataset through the nine-stage chain) would
set REAL_DATA_READY toward PASS — registration alone (RDR-04) never
would. Closing OFR-01 + OFR-05 (a recorded production approval plus a
provisioned, live-evaluated feed) is necessary but STILL requires the
gate's own live evaluation to pass; approval alone is necessary, not
sufficient. Closing GOV-03 + GOV-04 + GOV-05 (rotation confirmed, key
provisioned, source approved) plus the already-closed GOV-01/GOV-02
is what GOVERNANCE_READY requires; GOV-06 records CI visibility, not
a gate precondition. No combination of the above authorizes live
trading: `PAPER_READY` gates paper sessions only, and LIVE TRADING
NOT AUTHORIZED remains in force unconditionally.

## 6. No-secrets statement

This inventory deliberately contains no secrets, API keys, tokens,
private key material, or sensitive account information. Credential
items (GOV-03, GOV-04) reference their custody and decision records,
which store fingerprints and exposure counts only. The pinning tests
structurally enforce the absence of credential-shaped strings in this
document.

## 7. Frozen artifacts and compatibility

This document changes no code, no frozen Phase 3 blob, no SUB-18
manifest entry, no snapshot schema, and no gate logic. The frozen
artifact checks and the full suite are re-run in the batch that
delivers any change to this inventory (see the Batch 9 report for the
executed commands and results).

## 8. Structural pinning

`tests/test_readiness_evidence_inventory.py` pins, with regression
force: the inventory's existence and three-gate scope; the ten-column
shape and stable ordering of every item row; the closed status and
evidence-class vocabularies; the rule that PASS is legal only for
verified evidence or recorded decisions (missing evidence never
converts to PASS); explicit unresolved reasons for every non-PASS
item; verification timestamps on verified evidence; decision-ID
citations on recorded decisions; the mandated integrity-rule
distinctions; the absence of credential-shaped strings; and
cross-document agreement with the authoritative final report
(PAPER_READY = FALSE). Weakening any of these properties breaks the
suite.

## 9. Verification log (first-hand)

| When | What was verified |
|---|---|
| 2026-10-13 (Batch 9, Task 1) | Repository truth: branch `audit/batch-8-independent-runtime-audit` at 30ff1ce, clean tree, in sync with origin; `main` at d49b822 locally and remotely (unauthenticated ls-remote — no stored credential exists, none was used); PR 1 head 7f384e6 and PR 2 head d945833 both open and unmerged (refs/pull/*/merge present); REST API probes returned HTTP 403 (rate limited) — CI check-runs UNVERIFIED |
| 2026-10-13 (Batch 9, Task 4) | Baseline suite re-run on the clean tree BEFORE any change: 2,215 passed + 1 skipped (79.56 s) — exactly the reported baseline; full validation after the change is recorded in the Batch 9 report |
| 2026-10-13 (Batch 9, Task 2) | Every evidence reference in §4 was checked against the cited document or module on this checkout before the inventory was written |

## 10. Change log

| Version | Date | Change |
|---|---|---|
| 1.0.0 | 2026-10-13 | Initial inventory (Batch 9): per-evidence-item tracking for REAL_DATA_READY (6 items), OPERATIONAL_FEED_READY (6 items), GOVERNANCE_READY (6 items); integrity rules; structural pinning tests; no gate status changed — all three gates remain FAIL |
