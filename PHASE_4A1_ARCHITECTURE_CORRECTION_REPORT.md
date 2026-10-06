# PHASE 4A.1 — ARCHITECTURE CORRECTION REPORT

> **SUPERSESSION NOTICE (added 2026-10-01, post-re-audit correction pass).**
> This document is now **REFERENCE ONLY — status superseded** per
> `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` §12.1 (DL-D3′).
>
> Its report of the Stage 1 Architecture Correction remains **valid historical
> evidence** for that stage. Two of its status claims no longer hold:
>
> | Claim in this document | Current state |
> |---|---|
> | The Architecture Correction stage produced a specification ready for Design Lock | **SUPERSEDED.** The subsequent Design Lock returned `DESIGN_LOCK = FAILED`; the independent re-audit returned `RE-AUDIT_FAIL` |
> | Its companion checklist records "18 undefined test identifiers" (checklist §3.2, §4) | **SUPERSEDED.** The correct figure is **23** (authoritative spec §8.5.13) |
>
> **An independent re-audit on 2026-10-01 discovered three further findings this
> document did not identify**, registered as RA-NF-01, RA-NF-02 and RA-NF-03 in
> authoritative spec §0.2.2:
>
> | Finding | Severity | Summary |
> |---|---|---|
> | **RA-NF-01** | **HIGH / BLOCKER** | Integer-key/string-key canonical-byte collision: `{1:"a"}` and `{"1":"a"}` both serialize to `b'{"1":"a"}'`. Distinct inputs, identical Phase 4 identity, no error raised. Violates ID-COL-01 and ID-COL-04 |
> | **RA-NF-02** | MINOR | Bare `date` objects are rejected by the serializer although §3.1 mandates a `{"D": …}` encoding, making date-bearing identity fields unserializable |
> | **RA-NF-03** | MINOR | `Decimal`/`float` distinction relies on incidental `json.dumps` quoting rather than the mandated explicit tags. **Not** a collision |
>
> **All eight blockers remain OPEN.** This stage's statement that specification
> conditions were satisfied stands; its implicit readiness for Design Lock did not
> survive verification. See authoritative spec §14.0 for the current stage history.

---

**Document Version:** 1.0.0
**Date:** 2026-10-01
**Branch:** `phase-4a/4a1-temporal-foundation`
**HEAD Commit:** `13fdc7e`
**Stage:** Architecture Correction (Stage 1 of §14)
**Authoritative Specification:** `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` v1.1.0
**Mode:** DOCUMENTATION-ONLY — NO IMPLEMENTATION

---

## A. ARCHITECTURE CORRECTION REPORT

### A.1 Stage Outcome

The Architecture Correction stage is complete. **Closure criteria and required specifications have been defined for all 8 blockers.**

Defining a closure criterion is not meeting it. Each blocker requires four distinct things, and this stage delivered only the first:

| Layer | What it means | State |
|---|---|---|
| 1. Specification / contract definition | The criterion and required contract are written down | **DEFINED (8/8)** |
| 2. Implementation evidence | The contract exists as working code | **ABSENT (0/8)** |
| 3. Closure evidence | Tests demonstrate the contract holds | **ABSENT (0/8)** |
| 4. Independent re-audit | A separate reviewer verifies closure | **NOT PERFORMED (0/8)** |

**No blocker was closed.** Closure requires layers 2–4, which are implementation-stage work this stage may not produce (INV-07).

### A.2 What Was Corrected

Five documentation corrections were applied to `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md`, promoting it v1.0.0 → v1.1.0.

| # | Correction | Type | Defect corrected |
|---|-----------|------|------------------|
| A | §12.5 added | Self-audit | Blocker 1 required reconciliation evidence; v1.0.0 **asserted** it without recording the result |
| B | §8.5 added + ID renames | Self-audit | §7 referenced **23 undefined test identifiers** (corrected count — see §A.3); `LEG-*` prohibitions collided with the `LEG-*` test namespace |
| C | §9.2 + REG-06 | Self-audit | Hard-coded stale untracked-artifact count (27 declared; 28 measured) |
| D | §13.3–13.4 added | Stage deliverable | Compact blocker-closure table absent |
| E | §15.2 + header | Stage deliverable | Status block predated the correction stage |

### A.3 Self-Audit Defects Found in the Corrective Document

Three defects were found in the specification this stage was meant to execute. They are the same class of failure the remediation specification was written to eliminate:

**DEFECT-A — asserted evidence.** §13 Blocker 1 required "repository-wide reconciliation" as closure evidence. v1.0.0 stated the condition without recording a result. An unexecuted verification requirement is not a verification.

**DEFECT-B — unenforceable requirements.** §7 component contracts named `TIE-01…04`, `VAL-01…04`, `INST-01/02`, `SPEC-01/02`, `VEN-01`, `SRC-01/02`, `CAL-01/02`, `EXP-01…03`, `CFG-01/02`, and `LEG-REP-01`. None existed in §8. This is **F-21 recurring inside the corrective document**: a test identifier that is referenced but never defined constrains nothing. Compounding it, `LEG-01`…`LEG-09` were *prohibitions* sharing a prefix with *test identifiers*.

**DEFECT-B — corrected count: 23, not 18.** The initial report stated 18. That figure was wrong on three counts and has been recomputed by direct enumeration of the pre-correction §7 acceptance-test cells against the §8.2/§8.3 definitions.

| Component | Count | Identifiers |
|---|---|---|
| Explicitly named, never defined | 14 | `CAL-01` `CAL-02` `CFG-01` `CFG-02` `EXP-01` `EXP-02` `INST-01` `INST-02` `LEG-REP-01` `SPEC-01` `SPEC-02` `SRC-01` `SRC-02` `VEN-01` |
| Implied by range notation (`…04`), never defined | 8 | `TIE-01` `TIE-02` `TIE-03` `TIE-04` `VAL-01` `VAL-02` `VAL-03` `VAL-04` |
| **TOTAL** | **23** | |

**Methodology and reconciliation of the earlier "18":**

1. **Overstated by 2.** The original grep pattern `\b(...|LEG)-[0-9]+` matched `LEG-01` and `LEG-03`. These are **prohibition IDs** (§6.2), not test IDs, and were wrongly counted.
2. **Understated by 8.** `TIE-01…04` and `VAL-01…04` are range expressions. A token grep sees only `TIE-01` and `VAL-01`, missing the six implied members `TIE-02/03/04` and `VAL-02/03/04`. All eight were undefined.
3. **Omitted 1.** `LEG-REP-01` does not match the pattern at all — the pattern requires `LEG-` followed by digits, and `LEG-REP-01` has `REP` in between. It was invisible to the method.

**Arithmetic:** 14 (explicit, excluding prohibitions) + 8 (range-implied) + 1 (`LEG-REP-01`) = **23**.

**Method note (REG-06).** Counting identifiers requires a method that can see ranges and non-numeric suffixes. Token grep alone is insufficient and produced this error. The §8.5.12 reconciliation command in the authoritative specification is the standing guard.

**DEFECT-C — stale constant.** §9.2 hard-coded "27 untracked artifacts." Measured: 28. A hard-coded artifact count goes stale the moment a stage adds a document — which this stage did.

### A.4 Ownership Resolution (Blocker 1)

Reconciliation executed across all repository `.md` files:

| Components | Result |
|---|---|
| `PitSidecar`, `RevisionChain`, `TieBreakerPolicy`, `PitView`, `PitViewBuilder`, `PitViewValidator`, `ExperimentIdentity`, `PitExperimentConfig` (8) | `4A.1` only — **consistent** |
| `InstrumentIdentity`, `InstrumentSpecification`, `Venue`, `DataSource`, `CalendarRef` (5) | `4A.1` **and** `4A.2` — **CONTRADICTION** |

Resolved by §1.2 R-01: all five belong to **4A.1**. Contradicting documents retained unmodified per GOV-02; the supersession is recorded in §12.1 and the measured result in §12.5.

**Blocker 1 remains OPEN:** SUB-22 is unimplemented, and `EvidenceProvenance` is still defined twice in production code (`schemas.py:47`, `evidence.py:18`). The R-03 re-export is a code change, outside this stage's boundary.

---

## B. FILES MODIFIED

| File | Change | Lines |
|---|---|---|
| `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` | v1.0.0 → v1.1.0. Added §12.5, §8.5, §13.3, §13.4, GOV-07, REG-06. Renamed `LEG-01…09` → `PROH-LEG-01…09`; `LEG-REP-01` → `SUB-09`. Updated §9.2, §15.2, header | 1,253 → 1,479 |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_CHECKLIST.md` | **CREATED** — checklist mapped to 8 blockers; correction diff plan | 0 → 320 |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_REPORT.md` | **CREATED** — this report | 0 → this file |

**Total: 1 documentation file modified, 2 documentation files created. 0 code files modified.**

---

## C. FILES LEFT UNCHANGED

| Path | Reason |
|---|---|
| `docs/strategy_engine_design.md` | Frozen Phase 3 design contract (§10.1). Content is correct; only a **human authorization record** is missing. Not a documentation edit. |
| `src/data_engine/schemas.py` | Frozen manifest + production code. `EvidenceProvenance` R-03 deferred. |
| `src/data_engine/strategy/**` (11 files) | Frozen manifest + production code. |
| `src/data_engine/pit/**` (6 files) | Existing PIT artifacts. No documentation-reference defect requiring edit. |
| `tests/**` (7 files) | Phase 3 frozen tests. **No test added or modified.** `test_pit_view.py` still absent. |
| `pyproject.toml` | Pre-existing unauthorized modification. Not this stage's to resolve. |
| `src/audit.log`, `uv.lock`, `README.md`, `docs/quant_engine.md`, `docs/strategy_engine.md` | No correction required. |
| 11 prior audit/spec documents | GOV-02 — retained unmodified as historical evidence. |

---

## D. BLOCKER-CLOSURE TABLE

| # | BLOCKER | CLOSE CONDITION | REQUIRED EVIDENCE | REQUIRED TESTS | RE-AUDIT | STATUS |
|---|---------|-----------------|-------------------|----------------|----------|--------|
| 1 | **Phase ownership contradictions** | One owner per component; `EvidenceProvenance` single definition; contradictions superseded | §12.5 executed reconciliation; GOV-02 supersession record | SUB-22 | Required | **OPEN** |
| 2 | **Identity-contract specification gaps** | Versioned contract: allowlists, audit-only fields, canonical form, type/null/TZ/numeric rules, wall-clock excluded | §2 + §3 ratified; `pit4.` versioning; identity free function; §10.2 manifest | T-H01–T-H04, SUB-21, SUB-24, SUB-25 | Required | **OPEN** |
| 3 | **Temporal-contract gaps** | Cross-field ordering, required-field semantics, legacy rules, cutoff boundary defined and tested | §4 + §6 ratified; inclusive cutoff normative; PROH-LEG-01…09 | T-P01, T-P02, T-P04, T-M01, T-M06, SUB-09/10/11/19/20 | Required | **OPEN** |
| 4 | **Canonical serialization alignment** | No type collisions; numeric policy explicit; unknown fields rejected; deterministic | §3 ratified; type-tagged encoding; `.10f`; measured collision matrix | SUB-04–SUB-08, T-H05 | Required | **OPEN** |
| 5 | **PIT component specification gaps** | 13 components fully specified; availability pairing type-safe | §7.1–7.13; §5 discriminated-union mandate | SUB-01/02/03 + 33 component tests | Required | **OPEN** |
| 6 | **P0/T-PIT acceptance gaps** | Every mandatory requirement maps to an actual test | §8 matrix (80 tests specified); `tests/test_pit_view.py` | 19 P0 + 25 SUB + 33 component + 3 legacy = **80** | Required | **OPEN** |
| 7 | **Regression-baseline ambiguity** | 367 authorized; 97 delta identified; weak tests replaced; design-doc change authorized | §9 ratified; manifest recorded; REG-06 measurement rule | SUB-18 + 4 §8.4 replacements | Required | **OPEN** |
| 8 | **Filesystem-security concern** | Root containment, traversal/absolute rejection, symlink handling, strict config, fail-closed | §11 ratified; FS-01…FS-24; §11.7 measured attacks | SUB-12–SUB-17, SUB-24 | Required | **OPEN** |

**8 of 8 OPEN. 0 closed.**

---

## E. EVIDENCE FOR EACH CORRECTION

| Correction | Verification command | Result |
|---|---|---|
| **A** §12.5 executed reconciliation | `grep -rl "<component>" --include="*.md" .` + phase-token extraction | **5 contradictions measured**: InstrumentIdentity, InstrumentSpecification, Venue, DataSource, CalendarRef each show `4A.1,4A.2` |
| **B** §8.5 test definitions | `comm -23 <(§7 refs) <(§8 defs)` — the §8.5.12 regression guard | **EMPTY output = PASS.** Zero referenced-but-undefined identifiers |
| **B** ID namespace | `grep -oE 'PROH-LEG-0[0-9]' \| sort -u \| wc -l` | **9** prohibitions defined. Only 2 bare `LEG-0x` remain, both inside the changelog sentence describing the rename |
| **C** REG-06 | `git ls-files --others --exclude-standard \| wc -l` | **29** at stage exit (was 27 in v1.0.0, 28 at entry). Count is now declared as a measurement, not a constant |
| **D/E** structural | `grep -c "^## SECTION"` | **15** sections intact; §12.5, §8.5, §13.3 each present exactly once |
| **Count discipline** | `sed -n '/### 8.5.1/,/### 8.5.11/p' \| grep -oE` per prefix | TIE 6, VAL 4, INST 4, SPEC 3, VEN 2, SRC 3, CAL 2, EXP 5, CFG 4 = **33** component + **3** legacy = **36**. Table corrected from an erroneous 38 → **80 total** |

### E.1 Integrity Verification (all PASS)

| Check | Expected | Actual |
|---|---|---|
| Frozen 13-file SHA-256 manifest | unchanged | **ALL 13 UNCHANGED** |
| `src/data_engine/pit/*.py` SHA | unchanged | **6/6 unchanged** |
| Tracked `.py` modifications | 0 | **0** |
| Tests added or modified | 0 | **0** |
| `tests/test_pit_view.py` | absent | **absent** |
| Full suite | 464 passed | **464 passed** (1.16s) |
| Authorized baseline | 367 passed | **367 passed** (0.86s) |
| Tracked file modifications | 2 (pre-existing) | **2** — `docs/strategy_engine_design.md`, `pyproject.toml` |

---

## F. REMAINING BLOCKERS

**8 of 8 remain OPEN.** None was closed by assertion (INV-07).

| Layer | Count | State |
|---|---|---|
| 1. Specification / contract definition | 8 | **DEFINED** — closure criteria and required contracts written (§1–§13) |
| 2. Implementation evidence | 8 | **ABSENT** — no contract implemented as code |
| 3. Closure evidence | 8 | **ABSENT** — no tests demonstrating the contracts |
| 4. Independent re-audit | 8 | **NOT PERFORMED** |
| **Blockers closed** | **0 of 8** | — |

**Complete blocker-closure evidence: 0/8.** (Layers 2 + 3 + 4 all absent.)

Partial evidence *does* exist and is recorded, but it is not closure evidence:

| Blocker | Partial evidence produced | Still required for closure |
|---|---|---|
| 1 | **Ownership reconciliation executed** — 5 contradictions measured and resolved to 4A.1 (§12.5); superseded records applied per GOV-02 | SUB-22; `EvidenceProvenance` de-duplicated in code; re-audit |
| 2 | Identity + serialization contracts specified; frozen 13-file manifest recorded | Identity test suite; manifest re-verification; re-audit |
| 4 | Serializer collision pairs enumerated from live execution | Collision matrix implemented as a passing test; re-audit |
| 7 | 367/464/97 baseline measured live; REG-06 measurement rule adopted | **Human authorization record** for `docs/strategy_engine_design.md` line 2238 — outstanding; weak tests unreplaced; re-audit |
| 8 | Attack vectors executed against live `FileDataProvider` (§11.7) | Controls implemented; containment tests; audit-log verification; re-audit |
| 3, 5, 6 | Contracts and test matrix specified only | Implementation, tests, re-audit |

**Blocker 7 remains PARTIAL**: its closure condition includes a human authorization decision that no agent can produce.

**Why specification sufficiency is not closure.** Each blocker names concrete artifacts — `tests/test_pit_view.py`, `SUB-22`, collision-matrix evidence, containment tests, a design-doc authorization record. None can exist without production code that this stage is forbidden to write. A blocker whose condition is met but whose evidence is absent is **open**, not closed.

### F.1 Outstanding Work by Owner

| Owner | Outstanding |
|---|---|
| Human approver | Authorization decision for the `docs/strategy_engine_design.md` line-2238 change (§12.3) — **cannot be produced by an agent** |
| Repository governance | Disposition of 29 untracked artifacts |
| Implementation stage (Stage 4) | All 13 PIT components; serializer correction; availability discrimination; filesystem controls; `EvidenceProvenance` re-export |
| Test stage (Stages 5–6) | 80 specified tests; 4 weak-test replacements |
| Independent auditor | Re-audit of all 8 blockers |

---

## G. RE-AUDIT REQUIREMENTS

An independent re-audit must verify, at minimum:

| # | Requirement |
|---|---|
| R-1 | §12.5 ownership reconciliation reproduces — 5 contradictions, 8 consistent |
| R-2 | §8.5.12 reconciliation command returns empty |
| R-3 | All 80 test identifiers are defined exactly once and referenced coherently |
| R-4 | §8.5.11 counts recompute to 19 + 25 + 33 + 3 = 80 |
| R-5 | No `PROH-*` identifier is used as a test ID; no test ID is used as a prohibition |
| R-6 | Frozen 13-file manifest unchanged |
| R-7 | Zero production `.py` modifications across all stage boundaries |
| R-8 | Baseline re-measured live: 464 total / 367 authorized / 97 delta |
| R-9 | Untracked-artifact count re-measured, not copied forward |
| R-10 | §1.2 ownership table has exactly one owner per component |
| R-11 | Every superseded document retained unmodified (GOV-02) |
| R-12 | Blocker table internally consistent: conditions ⇄ evidence ⇄ tests ⇄ status |

**Re-audit is mandatory.** No blocker closes without it.

---

## H. IMPLEMENTATION READINESS

```
ARCHITECTURE STATUS:      CORRECTED — SPECIFICATION LEVEL
IMPLEMENTATION READINESS: NOT_READY
IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
MANDATORY BLOCKERS:       8 of 8 OPEN
BLOCKERS CLOSED:          0 of 8
COMPONENTS IMPLEMENTED:   0 of 13
TESTS EXISTING:           0

CLOSURE CRITERIA + REQUIRED SPECS DEFINED:  8 of 8
IMPLEMENTATION EVIDENCE:                     0 of 8
CLOSURE EVIDENCE:                            0 of 8
INDEPENDENT RE-AUDIT:                        0 of 8
COMPLETE BLOCKER-CLOSURE EVIDENCE:           0 of 8

REGRESSION BASELINE:      367 authorized / 464 current / 97 unauthorized delta
FROZEN PHASE 3:           UNMODIFIED — 13-file manifest verified
PRODUCTION CODE CHANGED:  NONE
TESTS ADDED:              NONE
```

### H.1 Readiness Assessment

| Category | Classification |
|---|---|
| Specification completeness | **READY** — 15 sections, 19 components, 80 tests, all ratified |
| Ownership determinacy | **READY** — 19 components, one owner each |
| Internal consistency | **READY_AFTER_CORRECTION** — 3 defects found and fixed this stage |
| Implementation readiness | **NOT_READY** — 0 of 13 components exist |
| Acceptance readiness | **NOT_READY** — 0 of 80 specified tests exist |
| Security readiness | **NOT_READY** — no controls implemented; `endpoint` escape still succeeds |
| Authorization | **NOT_AUTHORIZED** |

### H.2 Next Action

NEXT ACTION:
DESIGN LOCK → INDEPENDENT RE-AUDIT → AUTHORIZATION REVIEW

**Design Lock is NOT implementation authorization.** It ratifies §1–§13 into a versioned locked design with a recorded SHA-256, and nothing more. Implementation remains prohibited until an Authorization Review — a distinct, later stage — explicitly grants it, which requires all 8 blockers closed **and** independently re-audited.

---

## FINAL STATUS

**NOT_READY**

**NOT_AUTHORIZED**

No implementation authorization has been granted. The next action is Design Lock, then independent re-audit.

---

*END REPORT — PHASE 4A.1 ARCHITECTURE CORRECTION REPORT*
