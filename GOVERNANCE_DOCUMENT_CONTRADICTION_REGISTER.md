# GOVERNANCE DOCUMENT CONTRADICTION REGISTER

> Live register of contradictory claims across repository documentation.
> Carries the construction-era reconciliation register (CR-01..CR-12) forward
> with current resolution status, and adds documentation-era entries (CRD-*).

```text
Document Type:  Governance contradiction register
Phase:          Cross-phase
Authority:      A — AUTHORITATIVE (contradiction tracking of record)
Status:         CURRENT
Version:        1.0.0
Last Updated:   2026-10-08
Supersedes:     PHASE_GOVERNANCE_RECONCILIATION.md §contradiction-register
                (for TRACKING purposes only — the original table is preserved
                verbatim in that document as historical evidence)
Superseded By:  —
Source Evidence: PHASE_GOVERNANCE_RECONCILIATION.md (CR-01..CR-12), git log,
                 commit 018d084 (governance docs committed), commits
                 3084dcb/78349e1/6d0ad30, doc_discovery.py reference graph
```

## Reading rules (mandate §13)

- Historical statements are **preserved, never rewritten** in their source
  documents. This register classifies them.
- A contradiction marked RESOLVED means the authoritative current record
  supersedes the historical statement — not that the historical document was
  edited.
- Required actions naming OPERATOR are pending human decisions.

## Construction-era contradictions (carried forward)

| ID | Document | Contradiction | Historical/Current | Authority | Required Action |
|---|---|---|---|---|---|
| CR-01 | `MASTER_FULL_SYSTEM_CONSTRUCTION_BLUEPRINT.md` (§2 + L1751) | "4A.1 BLOCKED (8 open)"; "Final Acceptance: 8 blockers OPEN — NOT READY" vs implementation records "8/8 CLOSED" | historical (stale) vs current | implementation records + `ZAI_PHASE_4A1_FINAL_STATUS.md` | Blueprint status columns remain STALE; addendum recommended, not applied (OPERATOR) |
| CR-02 | `MASTER_PHASE_STATUS_REPORT.md` | "NO PHASE MAY ADVANCE"; NOT_AUTHORIZED statuses vs phases advanced under authorization A3–A5 | historical (correct at 2026-09-30) vs current | reconciliation §8 authorization chain | Classified HISTORICAL/SUPERSEDED (this register + index) — DONE |
| CR-03 | `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` header | "NO IMPLEMENTATION AUTHORIZED" vs executed implementation | historical vs current | authorization A4 + implementation record | Classified SUPERSEDED (spec discharged; GOV rules retained) — DONE |
| CR-04 | Design Lock family (3 records) | Design Lock FAILED ×3 vs construction proceeded | historical vs current | reconciliation §7 (gate superseded by operator authorization) | Classified HISTORICAL — no PASS exists or is fabricated — DONE; OPERATOR awareness |
| CR-05 | `PHASE_4A1_DL_D1_AUTHORIZATION_IMPACT_ASSESSMENT.md` | "Phase 4.2 not authorized" vs 4A.2 delivered (`0ce78f6`) | historical vs current | authorization A5 + cycle record | Classified SUPERSEDED — DONE |
| CR-06 | `ZAI_WEEK_END_FULL_FORENSIC_INSPECTION.md` | "zero call sites" (Phase 4+ scope) vs H-1 artifact F-9: wired into dormant ingestion API | scope nuance — both true in their scopes | `H1_FORMAL_DECISION_ANALYSIS.md` (precise statement) | RECONCILED — scope distinction recorded — DONE; H-1 ruling pending (OPERATOR) |
| CR-07 | `PHASE_4A1_DL_D1_OPTION_A_DECISION_RECORD.md` | CRLF non-conformance OPEN vs committed state LF-only | historical (working-tree measurement) vs current | implementation record §5 byte measurements | Classified root-caused; Option A decision stands — DONE; Windows checkouts cosmetic |
| CR-08 | Remediation spec §10.2 manifest | 7/13 stale hashes (CRLF-era) vs SUB-18 re-recorded 13/13 | historical vs current | final_gate_verify.py (13/13 re-verified) | Classified SUPERSEDED per FRZ-04 — DONE |
| CR-09 | Blueprint baseline numbers | 367/464/97 "current" vs 692 (now 789) | historical vs current | cycle records + first-hand suite runs | Stale numbers classified; addendum recommended, not applied (OPERATOR) |
| CR-10 | Governance records living OUTSIDE repo | decision artifacts not under version control vs committed trail | **RESOLVED 2026-10-08**: all 10 governance/audit reports committed in `018d084` (operator authorization "Push all the files you made into the repo") | commit `018d084` + push verification | RESOLVED — DONE |
| CR-11 | Local `main` ref at `13fdc7e` (22 behind origin) | local/remote divergence | **RESOLVED 2026-10-08**: local main fast-forwarded and synced (`018d084`→`3084dcb`→`6d0ad30`) | `git ls-remote` verification each cycle | RESOLVED — DONE |
| CR-12 | "95/95 acceptance IDs" count phrasing | 87 docstring + 23 name-encoded = counting imprecision (L-4) | current nuance | week-end §8 traceability | Classified; coverage verified — DONE (recorded) |

## Documentation-era contradictions (new, this cycle)

| ID | Document | Contradiction | Historical/Current | Authority | Required Action |
|---|---|---|---|---|---|
| CRD-01 | `ZAI_PHASE_4A1_STATE_REAUDIT.md` (line 18) | Refers to operator-supplied `PHASE_4A1_FINAL_STATUS.md`; the committed file is `ZAI_PHASE_4A1_FINAL_STATUS.md` | historical narrative vs current filename | this index | No edit (audit evidence, bytes preserved); mapping recorded here — DONE |
| CRD-02 | `PHASE_4A1_IMPLEMENTATION_SPEC.md` / `PHASE_4A1_SPEC_RECONCILIATION.md` | Prose shorthand `BLOCKER_RESOLUTION_SPEC.md` (without `PHASE_4A1_` prefix) | historical shorthand | this index | No edit (historical evidence); disambiguation: `PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md` — DONE |
| CRD-03 | `PHASE_GOVERNANCE_RECONCILIATION.md` (line 482) | Recommends creating `CURRENT_PROJECT_STATUS.md` | forward-looking recommendation vs existing `ZAI_REPOSITORY_PROGRESS_BRIEF.md` | this index | Recommendation satisfied by the progress brief; no new file needed — DONE |
| CRD-04 | `MASTER_ENHANCEMENT_HARDENING_MANDATE.md` / `ZAI_ENHANCEMENT_MANDATE_REGISTRATION.md` | Reference `FINAL_ENHANCEMENT_VERIFICATION_REPORT.md` (does not exist yet) | intentional forward reference (execution-era deliverable) | mandate §45 | RESOLVED BY DESIGN — file is produced only when enhancement execution completes; not a broken reference |
| CRD-05 | `ZAI_WEEK_END_FULL_FORENSIC_INSPECTION.md` (§3 tree status) | States week-end report is "the ONLY untracked artifact" | was true at writing (2026-10-07); now committed (`018d084`) | commit history | Historical point-in-time statement, preserved; current truth in this register — DONE |
| CRD-06 | Test-count chronology across reports | 465 / 558 / 563 / 692 / 789 appear in different documents | all historical (each correct at its HEAD) | cycle records; current = 789 (re-verified this cycle) | Chronology recorded in progress brief §2; no edits to historical evidence — DONE |
| CRD-07 | `ZAI_REPOSITORY_PROGRESS_BRIEF.md` (pre-2026-10-08 versions) | Cited fixed HEADs (`018d084`) that age as new commits land | historical vs current | brief updated to "see git log" + timeline rows | RESOLVED by brief update this cycle — DONE |
| CRD-08 | `tests/AUDIT_REPORT.md` | Phase 3-era audit claims (pre-4A.1) located inside `tests/` | historical | this index | No edit (audit evidence preserved in place per §6); classified C-historical — DONE |

## Summary

```text
TOTAL REGISTERED:         20 (CR-01..CR-12 carried + CRD-01..CRD-08 new)
RESOLVED / CLASSIFIED:    20
UNRESOLVED (material):    0
PENDING OPERATOR ACTIONS: CR-01 addendum (blueprint status note)  [optional, recommended]
                          CR-04 awareness (Design Lock superseded)
                          CR-06 H-1 ruling (human ratification of containment)
                          CR-09 addendum (blueprint baseline numbers) [optional]
DOCTRINE:                 Historical statements are never rewritten; they are
                          classified here and superseded by current authority
                          documents listed in MASTER_DOCUMENTATION_INDEX.md.
```
