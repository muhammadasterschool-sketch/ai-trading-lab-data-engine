# PHASE 4A.1 — ARCHITECTURE CORRECTION CHECKLIST AND DIFF PLAN

**Document Version:** 1.0.0
**Date:** 2026-10-01
**Branch:** `phase-4a/4a1-temporal-foundation`
**HEAD Commit:** `13fdc7e`
**Authoritative Specification:** `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md`
**Stage:** Architecture Correction (Stage 1 of §14)
**Mode:** DOCUMENTATION-ONLY — NO IMPLEMENTATION

---

## 0. STAGE BOUNDARY

### 0.1 Permitted in this stage

Architecture specifications · governance documents · requirements/acceptance specifications · test specifications · blocker registers · authoritative documentation.

### 0.2 Prohibited in this stage

Frozen Phase 3 implementation · production Python implementation · existing PIT implementation artifacts (unless required solely to correct documentation references) · Phase 3 frozen tests.

### 0.3 Authorization state

```
IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
```

No blocker may close on documentation alone (INV-07). This stage produces **specification corrections only**. Every blocker remains OPEN pending implementation-stage evidence and independent re-audit.

---

## 1. BASELINE RE-ESTABLISHED AT STAGE ENTRY

| Check | Result | Command |
|---|---|---|
| Frozen 13-file SHA-256 manifest | **ALL UNCHANGED** | `sha256sum -c` |
| Full suite | **464 passed** (0.94s) | `.venv/Scripts/python.exe -m pytest tests/ --tb=no -q` |
| Authorized baseline | **367 passed** (0.79s) | `... --ignore=tests/test_pit.py` |
| Unauthorized PIT delta | **97** (all in untracked `tests/test_pit.py`) | per-file collection |
| Untracked artifacts at entry | **28** (21 `.md`, 6 `src/`, 1 `tests/`) | `git ls-files --others --exclude-standard` |
| Tracked modifications | **2** (pre-existing) | `git diff --name-only` |

**Baseline delta note:** the count moved from 27 to 28 because `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` was created in the preceding stage. This document makes it 29. §9.2 of the authoritative specification requires the count be re-declared; the correction below updates it.

---

## 2. CHECKLIST MAPPED TO ALL 8 BLOCKERS

Each item is **specification-level**. `[SPEC]` = documentation correction applied in this stage. `[DEFER]` = requires implementation-stage evidence; cannot be completed here.

### Blocker 1 — Phase ownership contradictions

| # | Task | Type | State |
|---|------|------|-------|
| 1.1 | Single-owner table for every 4A.1 component | `[SPEC]` | §1.2 ratified — **19 components, one owner each** |
| 1.2 | Retain Venue/DataSource/CalendarRef in 4A.1 | `[SPEC]` | §1.3 R-01 ratified |
| 1.3 | Resolve `EvidenceProvenance` duplication | `[SPEC]`+`[DEFER]` | R-03 ratified; **code change deferred** (production code out of scope) |
| 1.4 | Identify superseded contradictory documents | `[SPEC]` | §12.1 complete |
| 1.5 | Preserve contradictory history | `[SPEC]` | GOV-02; originals unmodified |
| 1.6 | Repository-wide reconciliation evidence | — | **Executed** — see §3.1 |

### Blocker 2 — Identity-contract specification gaps

| # | Task | Type | State |
|---|------|------|-------|
| 2.1 | Explicit allowlists | `[SPEC]` | §2.3 |
| 2.2 | Audit-only fields | `[SPEC]` | §2.4 + 6 prohibited fields |
| 2.3 | Deterministic canonical representation | `[SPEC]` | §2.5, §3 |
| 2.4 | Wall-clock exclusion | `[SPEC]` | ID-WC-01…03 |
| 2.5 | Type + numeric normalization | `[SPEC]` | §3.1, §3.3 |
| 2.6 | Versioned SHA-256 identity | `[SPEC]` | §2.5, §2.6 (`pit4.` prefix) |
| 2.7 | Identity free function | `[SPEC]` | §2.8 — `to_deterministic_hash()` prohibited on Phase 3 |
| 2.8 | No frozen-method modification | — | Verified: 13-file manifest unchanged |

### Blocker 3 — Temporal-contract gaps

| # | Task | Type | State |
|---|------|------|-------|
| 3.1 | Six temporal fields specified | `[SPEC]` | §4.1 |
| 3.2 | Cross-field ordering | `[SPEC]` | §4.3 — `event ≤ observation ≤ publication ≤ revision` |
| 3.3 | Required-field semantics | `[SPEC]` | §4.2 — `ALLOW_NULL` prohibited |
| 3.4 | Cutoff boundary | `[SPEC]` | §4.6 — inclusive, normative |
| 3.5 | Future-data exclusion | `[SPEC]` | §4.7 |
| 3.6 | Legacy-data semantics | `[SPEC]` | §6 |

### Blocker 4 — Canonical serialization alignment

| # | Task | Type | State |
|---|------|------|-------|
| 4.1 | Eliminate datetime/string ambiguity | `[SPEC]` | §3.1 — `{"t":…}` vs `{"s":…}` |
| 4.2 | Eliminate int-key/string-key ambiguity | `[SPEC]` | §3.1 + §3.2 — non-string keys raise |
| 4.3 | Float policy | `[SPEC]` | §3.3 — `.10f` adopted |
| 4.4 | Null behaviour | `[SPEC]` | §3.4 |
| 4.5 | Ordering | `[SPEC]` | §3.2 |
| 4.6 | Unsupported types | `[SPEC]` | §3.6 |
| 4.7 | `extra="forbid"` | `[SPEC]` | §3.7 |

### Blocker 5 — PIT component specification gaps

| # | Task | Type | State |
|---|------|------|-------|
| 5.1 | All 13 components fully specified | `[SPEC]` | §7.1–7.13 complete |
| 5.2 | AvailabilityPolicy discriminated | `[SPEC]` | §5.2–5.3 |
| 5.3 | Mismatched pairing fails at construction | `[SPEC]` | §5.3 |
| 5.4 | Unknown fields fail | `[SPEC]` | §5.4, §3.7 |
| 5.5 | Exact acceptance behaviour | `[SPEC]` | §8 |

### Blocker 6 — P0/T-PIT acceptance gaps

| # | Task | Type | State |
|---|------|------|-------|
| 6.1 | All 19 P0 IDs mapped to explicit tests | `[SPEC]` | §8.2 — **correction applied**, see §3.2 |
| 6.2 | True subprocess determinism | `[SPEC]` | T-H05 |
| 6.3 | Serializer collision matrix | `[SPEC]` | SUB-04…06 |
| 6.4 | AvailabilityPolicy mismatch ×4 | `[SPEC]` | SUB-01 |
| 6.5 | Legacy-sidecar reproducibility | `[SPEC]` | SUB-09…11 |
| 6.6 | Filesystem containment | `[SPEC]` | SUB-12…16 |
| 6.7 | Frozen Phase 3 SHA manifest | `[SPEC]` | SUB-18 + §10.2 |

### Blocker 7 — Regression-baseline ambiguity

| # | Task | Type | State |
|---|------|------|-------|
| 7.1 | Declare 367 / 464 / 97 | `[SPEC]` | §9.1 |
| 7.2 | Define measurement and freezing | `[SPEC]` | §9.2 — **correction applied**, see §3.3 |
| 7.3 | Design-doc authorization record | `[SPEC]` | §12.3 — **record required, not yet made** |
| 7.4 | Weak-test replacement specification | `[SPEC]` | §8.4 |

### Blocker 8 — Filesystem-security concern

| # | Task | Type | State |
|---|------|------|-------|
| 8.1 | Canonical path resolution | `[SPEC]` | §11.1 |
| 8.2 | Approved-root containment | `[SPEC]` | §11.2 |
| 8.3 | Traversal + absolute-path rejection | `[SPEC]` | §11.3 |
| 8.4 | Symlink/reparse-point handling | `[SPEC]` | §11.4 |
| 8.5 | Instrument allowlisting | `[SPEC]` | §11.5 |
| 8.6 | Strict configuration | `[SPEC]` | §11.6 |
| 8.7 | Fail-closed behaviour | `[SPEC]` | §11.8 |
| 8.8 | Security audit logging | `[SPEC]` | §11.8 |

---

## 3. DEFECTS FOUND IN THE AUTHORITATIVE SPECIFICATION ITSELF

Three defects were found by self-audit. All are documentation defects. All are corrected in this stage.

### 3.1 DEFECT-A — Ownership reconciliation evidence was asserted, not executed (Blocker 1)

**Defect.** §13 Blocker 1 requires "repository-wide reconciliation: `grep` yields exactly one phase assignment per component across all 4A.1 documents." The specification asserted this condition without recording the result. A grep across all `.md` files yields:

```
InstrumentIdentity       4A.1,4A.2      <- CONTRADICTION
InstrumentSpecification  4A.1,4A.2      <- CONTRADICTION
Venue                    4A.1,4A.2      <- CONTRADICTION
DataSource               4A.1,4A.2      <- CONTRADICTION
CalendarRef              4A.1,4A.2      <- CONTRADICTION
PitSidecar               4A.1
RevisionChain            4A.1
TieBreakerPolicy         4A.1
PitView / Builder / Validator   4A.1
ExperimentIdentity       4A.1
PitExperimentConfig      4A.1
```

The contradictions originate in `PHASE_4A1_IMPLEMENTATION_FORENSIC_AUDIT.md` (lines 1185–1189) and `PHASE_4A1_IMPLEMENTATION_SPEC.md` (lines 834–836, 857).

**Correction.** Record the executed reconciliation result in §12.5 as closure evidence. Per GOV-02 the contradicting documents are **retained unmodified**; the reconciliation is recorded, not applied to the originals. Blocker 1 therefore remains OPEN pending SUB-22 and re-audit.

### 3.2 DEFECT-B — §7 references 18 undefined test identifiers (Blocker 6)

**Defect.** §7 component contracts name component-level test IDs that §8 never defines:

```
CAL-01 CAL-02  CFG-01 CFG-02  EXP-01 EXP-02 EXP-03  INST-01 INST-02
SPEC-01 SPEC-02  SRC-01 SRC-02  TIE-01  VAL-01  VEN-01
```

Plus `TIE-01…04`, `VAL-01…04`, `EXP-01…03`, `INST-01/02`, `SPEC-01/02`, `SRC-01/02`, `CAL-01/02`, `CFG-01/02` are referenced in ranges. None exist in §8.2 or §8.3. A test identifier that is referenced but never defined is an unenforceable requirement — the same class of defect as F-21 (zero P0 identifiers in tests), and it recurred inside the corrective document.

Additionally, `LEG-REP-01` is used in §7.1 and §7.5 as a test name but is never defined; the defined legacy tests are `SUB-09`, `SUB-10`, `SUB-11`. And `LEG-01`/`LEG-03` are **prohibition IDs** (§6.2) that collide with the `LEG-*` test-ID namespace.

**Correction.** Add §8.5 defining all 19 component-level tests and mapping `LEG-REP-01` → `SUB-09`. Rename prohibition IDs to `PROH-LEG-*` to remove the namespace collision.

### 3.3 DEFECT-C — Stale untracked-artifact count (Blocker 7)

**Defect.** §9.2 step 1 states "all **27** untracked artifacts (20 `.md`, 6 `src/data_engine/pit/*.py`, 1 `tests/test_pit.py`)". Measured at stage entry: **28** (21 `.md`, 6 src, 1 test), because `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` was added in the prior stage.

**Correction.** Restate as a measured count with the governing rule: *the count is measured at every stage entry; it is not a fixed constant.* This is the correct fix — pinning a hard-coded number would immediately go stale again.

---

## 4. CORRECTION DIFF PLAN

Reported **before** any file is changed, per the stage instruction.

| # | FILE | CURRENT DEFECT | REQUIRED CHANGE | REASON | BLOCKER | RISK | FROZEN-STATUS |
|---|------|-----------------|-----------------|--------|---------|------|---------------|
| 1 | `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` | §13 Blocker 1 asserts reconciliation evidence without recording the executed result | Add §12.5 recording the measured ownership reconciliation (5 components show `4A.1,4A.2`) | Closure condition requires evidence, not assertion (INV-07) | 1 | **LOW** — additive section only; no existing text altered | NOT frozen (this doc) |
| 2 | `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` | §7 references 18 undefined test IDs; `LEG-REP-01` undefined; `LEG-*` namespace collision | Add §8.5 with 19 component test definitions; map `LEG-REP-01`→`SUB-09`; rename prohibitions to `PROH-LEG-*` | Undefined test IDs are unenforceable requirements — the F-21 defect recurring | 5, 6 | **LOW** — additive section; ID renames are prose-only references | NOT frozen (this doc) |
| 3 | `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` | §9.2 hard-codes "27 untracked artifacts"; actual is 28 | Replace fixed count with a measurement rule + measured value at stage entry | A hard-coded artifact count goes stale on every stage | 7 | **LOW** — prose-only | NOT frozen (this doc) |
| 4 | `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` | §13.1 blocker state table lacks the compact closure table required by the stage instruction | Add §13.3 compact closure table (BLOCKER / CLOSE CONDITION / REQUIRED EVIDENCE / REQUIRED TESTS / RE-AUDIT / STATUS) | Required deliverable of this stage | all | **LOW** — additive section | NOT frozen (this doc) |
| 5 | `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` | §15.2 status block predates this stage's correction record | Append correction-stage provenance: corrections applied, blockers still 8/8 OPEN | Status must reflect current stage | all | **LOW** — additive | NOT frozen (this doc) |
| 6 | `PHASE_4A1_ARCHITECTURE_CORRECTION_CHECKLIST.md` | Does not exist | **CREATE** — this document | Stage deliverable #2 (checklist) + #14 (diff plan) | all | **LOW** — new doc, no prior content | NOT frozen |
| 7 | `PHASE_4A1_ARCHITECTURE_CORRECTION_REPORT.md` | Does not exist | **CREATE** — stage report A–H | Stage final output | all | **LOW** — new doc | NOT frozen |

### 4.1 Files explicitly NOT modified

| FILE | REASON |
|---|---|
| `docs/strategy_engine_design.md` | Frozen Phase 3 design contract (§10). Its line-2238 content is correct; only an authorization record is missing, which requires a **human decision**, not a documentation edit |
| `src/data_engine/**` (all) | Production implementation — out of scope. Includes `schemas.py:47` `EvidenceProvenance` (R-03 code change deferred), `pit/*.py` (6 files) |
| `tests/**` (all) | Phase 3 frozen tests; `test_pit.py` authorization unresolved; **no new test created** (§8 matrix is a specification, not a test file) |
| `pyproject.toml` | Pre-existing unauthorized modification; not this stage's to resolve |
| All 11 prior audit/spec documents | GOV-02 — retained unmodified as historical evidence |

---

## 5. WHAT THIS STAGE DOES NOT DO

| Prohibited | Status |
|---|---|
| Create PIT classes | **Not done** — 13 components remain MISSING |
| Implement production code | **Not done** — zero `.py` files created or modified |
| Modify frozen Phase 3 | **Not done** — manifest verified unchanged |
| Add or modify tests | **Not done** — no test file created; `test_pit_view.py` still absent |
| Grant implementation authorization | **Not done** — `NOT_AUTHORIZED` |
| Close any blocker | **Not done** — 8 of 8 remain OPEN |

---

## 6. BLOCKER STATE AT STAGE COMPLETION

Specification-level conditions are satisfied for blockers 1–8. **Every blocker remains OPEN**, because closure requires condition + evidence + independent re-audit, and the evidence is implementation-stage work.

| # | Blocker | Spec complete? | Evidence complete? | Re-audited? | STATUS |
|---|---------|----------------|--------------------|-------------|--------|
| 1 | Phase ownership contradictions | YES | **NO** — SUB-22 not implemented; `EvidenceProvenance` still dual-defined in code | NO | **OPEN** |
| 2 | Identity-contract specification gaps | YES | **NO** — no identity test suite; contracts unratified | NO | **OPEN** |
| 3 | Temporal-contract gaps | YES | **NO** — no temporal tests | NO | **OPEN** |
| 4 | Canonical serialization alignment | YES | **NO** — collision matrix not implemented | NO | **OPEN** |
| 5 | PIT component specification gaps | YES | **NO** — 13 components unimplemented; §8.5 tests undefined in code | NO | **OPEN** |
| 6 | P0/T-PIT acceptance gaps | YES | **NO** — `tests/test_pit_view.py` does not exist | NO | **OPEN** |
| 7 | Regression-baseline ambiguity | PARTIAL — design-doc authorization record still missing | **NO** — weak tests unreplaced | NO | **OPEN** |
| 8 | Filesystem-security concern | YES | **NO** — no controls implemented | NO | **OPEN** |

**8 of 8 OPEN.**

---

## 7. FINAL STATUS

```
ARCHITECTURE STATUS:      CORRECTED (specification level)
IMPLEMENTATION READINESS: NOT_READY
IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
MANDATORY BLOCKERS:       8 of 8 OPEN
FROZEN PHASE 3:           UNMODIFIED — 13-file manifest verified
PRODUCTION CODE CHANGED:  NONE
TESTS ADDED:              NONE
```

**No implementation authorization has been granted. The next action is Design Lock, then independent re-audit.**

---

*END DOCUMENT — PHASE 4A.1 ARCHITECTURE CORRECTION CHECKLIST AND DIFF PLAN*
