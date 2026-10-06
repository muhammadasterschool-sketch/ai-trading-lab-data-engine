# PHASE 4A.1 — MANDATORY BLOCKER CLOSURE EXECUTION PLAN

**Document Version:** 1.0.0
**Date:** 2026-10-01
**Branch:** `phase-4a/4a1-temporal-foundation`
**Repository HEAD:** `13fdc7ee55a022a9be36ad910e524dcfa429954c`
**Mode:** GOVERNANCE / PLANNING ONLY — no implementation, no file modification
**Preceded by:** PHASE_4A1_DL_D1_OPTION_A_DECISION_RECORD.md, PHASE_4A1_OPTION_A_CLOSURE_STATE_RECONCILIATION.md
**Authority:** PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md v1.1.0 (sole working spec, §0.1 hierarchy)

---

## 1. AUTHORITATIVE CURRENT STATE

```
HUMAN_DECISION__OPTION_A__RECORDED
DL_D1__OPEN
DESIGN_LOCK__FAILED
IMPLEMENTATION_AUTHORIZATION__NOT_AUTHORIZED
PHASE_4_2__NOT_AUTHORIZED
BLOCKERS_CLOSED__0
BLOCKERS_OPEN__8
```

FROZEN DESIGN DOC: SHA `8efd870ed0149b0cc96d66d82643cb5f3efdb9176b8183896e1696c347802c84`, 95,358 bytes, CRLF=2238. **UNCHANGED.**
FROZEN MANIFEST: 13/13 verified. **UNCHANGED.**
AUTHORIZED BASELINE: 367. TOTAL: 464. DELTA: 97. **Preserved.**

---

## 2. GOVERNANCE CONSTRAINTS (absolute, non-negotiable)

1. Documentation is not implementation evidence.
2. A passing test cannot close a blocker if the test itself is non-conforming.
3. No blocker closes without condition + evidence + independent verification (INV-07).
4. Any failed independent verification reopens the relevant blocker.
5. Frozen Phase 3 contracts remain untouched (INV-01, FRZ-01…FRZ-05, §10).
6. DL-D1 Option A remains in force — no CRLF normalization, no design-doc modification.
7. This planning document grants no implementation authorization.
8. Phase 4.2 remains forbidden until the final 4A.1 architecture/forensic gate authorizes it.
9. No agent may fabricate authorization, person names, timestamps, ticket numbers, or approval references.
10. All counts are measured from the spec at time of statement (REG-06), never carried forward as fixed constants.

---

## 3. DEPENDENCY GRAPH

```
BLOCKER 1 (Ownership) ──────┐
                             ├─► BLOCKER 2 (Identity Contract)
BLOCKER 3 (Temporal) ───────┤    because identity allowlist depends on
                             │    ownership of primitives (R-01)
                             │
BLOCKER 4 (Serialization) ───┤    because serializer must use identity contract
                             │
BLOCKER 5 (PIT Components) ──┤    because components implement contracts
                             │    defined by blockers 2, 3, 4
                             │
BLOCKER 6 (Acceptance) ──────┘    because tests validate all above
                                    
BLOCKER 7 (Baseline) ─────── depends on blockers 1-6 evidence + DL-D1 record
BLOCKER 8 (Filesystem) ───── independent of 1-7 (separate domain)
```

**Sequencing consequence:** Blockers 1, 3, 4, 8 can begin in parallel at specification level. Blocker 2 depends on 1 (R-01 ownership). Blocker 5 depends on 2, 3, 4 (component contracts). Blocker 6 depends on 1-5 (tests validate components). Blocker 7 depends on 1-6 + DL-D1 record. Blocker 8 is independent.

---

## 4. PHASE SEQUENCING

### Phase A — Prerequisite Contract/Foundation Work

**Entry criteria:** All 8 blockers OPEN (current state). Design Lock FAILED. Option A in force.
**Exit criteria:** All §2-§7 contract specifications ratified; ownership table authoritative; serialization contract conformance rules defined; PIT component contracts complete; no production code changed.

**Work:**
- Ratify §1.2 ownership table (19 components, single owner each)
- Execute R-01 through R-04 ownership resolutions in spec
- Ratify §2 Identity Contract (allowlists, ID-WC-01…03, `pit4.` versioning, §2.8 free function)
- Ratify §3 Serialization Contract (type-tagged encoding, `.10f` numeric policy, §3.1a conformance SER-KEY-01…05, RA-NF-01…04)
- Ratify §4 Temporal Contract (6-field semantics, cross-field ordering, ALLOW_NULL prohibition, cutoff inclusive, legacy rules)
- Ratify §5 AvailabilityPolicy discriminated-union mandate
- Ratify §6 Legacy PIT rules (PROH-LEG-01…09)
- Ratify §7 PIT component contracts (§7.1–7.13, all 13 components)
- Ratify §11 Filesystem security contract (FS-01…FS-24)
- Register RA-NF-01…04 in §0.2.2 with SPECIFIED disposition
- Close DL-D2, DL-D3, DL-D4 documentation defects (already corrected in spec)
- Record DL-D1 Option A decision (already recorded)

**Permitted to change:** Only the authoritative specification document (PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md) for corrections that do not modify frozen Phase 3 contracts. No source, test, or design-doc changes.
**Forbidden:** Any modification to `docs/strategy_engine_design.md`, any Phase 3 source file, any test file, any frozen manifest entry, CRLF normalization.

**Independent verification:** Re-read spec §0.1 hierarchy; confirm all contract sections present; confirm no frozen contract modified; confirm 13/13 manifest still matches.

### Phase B — Implementation Work

**Entry criteria:** Phase A complete; all contracts ratified; implementation authorization pending (NOT granted); Design Lock re-attempt preconditions P-DL-1…P-DL-9 checked.
**Exit criteria:** All 13 PIT components implemented per §7 contracts; serializer conformant; availability pairing type-safe; filesystem controls implemented; no frozen Phase 3 contract modified; `src/` changes only in Phase 4 components.

**Work:**
1. **Blocker 1 — Ownership:** Implement R-03 re-export (`src/data_engine/schemas.py:47` becomes re-export of `evidence.py:18`). Assert `schemas.EvidenceProvenance is evidence.EvidenceProvenance`. Resolve 5 contradictory ownership claims in retained superseded documents (documentation-only; retain per GOV-02).
2. **Blocker 2 — Identity Contract:** Implement `identity_hash()` free function (§2.8). Implement identity-field allowlists for all identity-bearing entities. Implement `extra="forbid"` on all Phase 4 models. Implement wall-clock field rejection (ID-WC-01…03).
3. **Blocker 3 — Temporal Contract:** Implement `model_validator(mode="after")` for cross-field ordering (§4.3). Implement ALLOW_NULL + required_fields prohibition (§4.2). Implement cutoff inclusive boundary (§4.6). Implement legacy classification `PIT_INELIGIBLE`/`ASSUMED_PUBLICATION` (§6.3).
4. **Blocker 4 — Serialization:** Fix `_canonical_value` to reject non-string mapping keys (SER-KEY-01…05). Implement type-tagged encoding for all scalar types. Implement `.10f` float policy. Implement `date` encoding (`{"D":…}` distinct from dict `{"D":{…}}` — assign distinct tag letter per RA-NF-04). Implement Decimal tagged encoding (`{"d":…}`) and float tagged encoding (`{"f":…}`). Implement true subprocess determinism (T-H05 / COL-PROC-01).
5. **Blocker 5 — PIT Components:** Implement all 13 missing §7 components: `InstrumentIdentity`, `InstrumentSpecification`, `Venue`, `DataSource`, `CalendarRef` (minimal), `PitSidecar`, `RevisionChain`, `TieBreakerPolicy`, `PitView`, `PitViewBuilder`, `PitViewValidator`, `ExperimentIdentity`, `PitExperimentConfig`. Implement AvailabilityPolicy discriminated union with mismatched-pair rejection (§5.2, §5.3).
6. **Blocker 8 — Filesystem Security:** Implement canonical path resolution (FS-01…FS-03). Implement approved-root containment (FS-04…FS-06). Implement absolute-path and traversal rejection (FS-07…FS-10). Implement symlink/reparse-point handling (FS-11…FS-13). Implement instrument allowlisting (FS-14…FS-16). Implement config strictness `extra="forbid"` (FS-17…FS-19). Implement security audit logging (FS-20…FS-24).

**Permitted to change:** `src/data_engine/pit/*` (Phase 4 components only). No `src/data_engine/schemas.py`, `provider.py`, `validation.py`, `timeframes.py`, `instruments.py` Phase 3 frozen files. No `tests/` changes in this phase.
**Forbidden:** Any modification to `docs/strategy_engine_design.md`. Any Phase 3 frozen source modification. Any CRLF normalization. Any test creation (Phase C only).

**Dependencies:** Blocker 2 implementation depends on Blocker 1 ownership resolution (R-01 assigns primitives to 4A.1; R-03 re-export must precede identity contract). Blocker 5 implementation depends on blockers 2, 3, 4 (components consume identity, temporal, serialization contracts). Blocker 8 is independent.

**Independent verification:** Re-run behavioral probes against live `src/data_engine/pit/` code. Verify: `{1:"a"}` vs `{"1":"a"}` raises (not merely differs); `datetime` vs ISO string distinct; `.10f` policy; `date` encoding works; AvailabilityPolicy mismatches raise; ordering constraint enforced; `ALLOW_NULL` + required raises; endpoint escape blocked; `check_connectivity("C:/Windows")` does not enumerate.

### Phase C — Mandatory Test Implementation

**Entry criteria:** Phase B complete; all implementation evidence exists; test file `tests/test_pit_view.py` created.
**Exit criteria:** All 95 specified tests exist as named tests in `tests/test_pit_view.py`; all 95 pass; all mutation-verification requirements satisfied.

**Required test namespaces (exact IDs from spec §8):**

| Namespace | Count | Spec Section |
|-----------|-------|-------------|
| Mandatory P0 (`T-*`) | 19 | §8.2 |
| Supplementary (`SUB-*`) | 25 | §8.3 |
| Component-level (`TIE-01…06`, `VAL-01…04`, `INST-01…04`, `SPEC-01…03`, `VEN-01…02`, `SRC-01…03`, `CAL-01…02`, `EXP-01…05`, `CFG-01…04`) | 33 | §8.5.1–8.5.9 |
| Legacy semantics (`LEG-T01…03`) | 3 | §8.5.10 |
| Post-re-audit COL-* | 15 | §8.6 |
| **TOTAL** | **95** | — |

**Exact P0 IDs (§8.2):** T-H01, T-H02 (2 tests), T-H03, T-H04, T-H05, T-P01, T-P02, T-P03, T-P04, T-R01, T-R02, T-R03 (2 tests), T-R04, T-M01, T-M06, T-O01, T-X01, T-X02, T-X07.

**Exact SUB IDs (§8.3):** SUB-01…SUB-25 (including SUB-09 legacy reproducibility, SUB-12 filesystem containment, SUB-15 symlink skip if WinError 1314, SUB-18 frozen manifest, SUB-25 no Phase-3-hash-in-Phase-4-identity).

**Exact COL-* IDs (§8.6):** COL-KEY-01…05, COL-DT-01/02, COL-DATE-01…03, COL-NUM-01…04, COL-PROC-01.

**Exact component test IDs (§8.5):** TIE-01…06, VAL-01…04, INST-01…04, SPEC-01…03, VEN-01…02, SRC-01…03, CAL-01…02, EXP-01…05, CFG-01…04.

**Exact legacy IDs (§8.5.10):** LEG-T01, LEG-T02, LEG-T03.

**Replacement of weak Category-D tests (§8.4):**
- `test_hash_cross_process_determinism` → SUB-04/`test_t_h05_...` (≥5 real subprocesses)
- `test_no_phase3_source_modified` → SUB-18: SHA-256 manifest comparison
- `test_hash_no_timestamp` → SUB-21, SUB-24: entity-level wall-clock exclusion
- `test_hash_no_uuid` → SUB-24: assert identity invariant under changed `run_timestamp`

**Forbidden:** Do not weaken any test to make it pass. Do not create tests that only assert inequality where rejection is mandated (COL-KEY-01 mutation rule). Do not absorb the 97-test delta into the authorized baseline.

**Independent verification:** Count identifiers from `tests/test_pit_view.py` and compare against spec §8.5.11 table. Verify zero undefined test identifiers (§8.5.12 reconciliation). Verify all P0 identifiers present.

### Phase D — Independent Verification

**Entry criteria:** Phase C complete; all 95 tests exist and pass; implementation evidence documented.
**Exit criteria:** Independent re-audit performed; all 8 blockers confirmed closed; RE-AUDIT_PASS (not RE-AUDIT_FAIL); Design Lock re-attempt preconditions P-DL-1…P-DL-9 all SATISFIED.

**Work:**
1. Independent re-audit of all 8 blockers against repository evidence (not document assertions).
2. Re-verify frozen manifest (13/13 SHA-256).
3. Re-verify regression baseline (367/464/97).
4. Re-verify §8.5.12 reconciliation (zero undefined component IDs).
5. Re-verify behavioral probes.
6. Verify each blocker's closure condition per §13.3.
7. Verify DL-D1 remains OPEN (CRLF non-conformance still present; Option A preserved).
8. Record re-audit results.

**Permitted to change:** Only the independent re-audit report document. No source, test, design-doc, or frozen-contract changes.
**Forbidden:** Closing any blocker on documentation alone. Declaring closure without evidence. Modifying frozen Phase 3 contracts. Normalizing CRLF.

**Invalid closure indicators (any one reopens the blocker):**
- Test passes but mutation verification fails (test would pass even if defect reintroduced).
- Evidence is a document assertion, not a measurement against live code.
- Frozen manifest mismatch.
- Baseline arithmetic incorrect (464 − 97 ≠ 367).
- Any Phase 3 frozen file SHA changed.
- DL-D1 resolved (CRLF normalized) without explicit human authorization for normalization.
- Test count does not match 95 (spec §8.5.11).

### Phase E — Blocker Closure

**Entry criteria:** Phase D complete; all 8 blockers independently confirmed closed; RE-AUDIT_PASS.
**Exit criteria:** All 8 blockers CLOSED; closure evidence documented per §13.3; blocker-closure table updated.

**Work:**
1. Update blocker table in authoritative specification (§13.3) with closure evidence.
2. Record independent re-audit confirmation for each blocker.
3. Update stage history (§14.0).
4. Record design-doc authorization decision for line 2238 (NO-GO line — separate human authorization, not this plan).
5. Re-record §10.2 manifest if any authorized change occurred.

**Critical:** Blocker closure requires all four: condition satisfied AND implementation evidence exists AND required tests pass AND independent re-audit confirms. Documentation alone does not close a blocker (INV-07).

### Phase F — Design Lock Re-attempt

**Entry criteria:** Phase E complete; all 8 blockers CLOSED; P-DL-1…P-DL-9 all SATISFIED; design-doc authorization for line 2238 recorded and committed; manifest re-recorded if needed.
**Exit criteria:** Design Lock PASS or FAIL (measured, not asserted).

**Preconditions (spec §14.0.1):**
- P-DL-1: DL-D1 false claim corrected (SATISFIED — measurement recorded; frozen file unchanged)
- P-DL-2: DL-D2 stale stage status (SATISFIED — §14.0 corrected)
- P-DL-3: DL-D3 hard-coded count (SATISFIED — REG-06 restored)
- P-DL-4: DL-D4 count contradiction (SATISFIED — §1.2 reconciliation stated)
- P-DL-5: DL-D3′ supersession gap (SATISFIED — §12.1 entries added)
- P-DL-6: RA-NF-01…04 registered with mandatory tests (SATISFIED — §0.2.2, §3.1a, §8.6)
- P-DL-7: No new false verification claims (verified at stage exit)
- P-DL-8: §8.5.12 reconciliation returns zero undefined (SATISFIED — verified in Phase D)
- P-DL-9: Frozen manifest unchanged (SATISFIED — 13/13)

**Additional requirement for Design Lock PASS:** The NO-GO line change (line 2238) must be authorized and committed with a new manifest event per §12.3. This requires a separate explicit human authorization decision (not this plan).

**Design Lock criteria (spec §13):** All 20 criteria must PASS. Current failures: "No false verification claims" (DL-D1 unresolved — still open per Option A), "Internally consistent stage state" (DL-D2 corrected), "Component count internally consistent" (DL-D4 corrected), "Authority hierarchy fully closed" (DL-D3 corrected). DL-D1 remains OPEN under Option A, so Design Lock cannot PASS until either normalization is authorized (Option B) or DL-D1 is downgraded/reclassified by explicit human decision.

### Phase G — Final 4A.1 Architecture/Forensic Gate

**Entry criteria:** Phase F complete; Design Lock PASS; all prerequisites P-1…P-8 met.
**Exit criteria:** Final gate verdict; implementation authorization granted (by explicit human mechanism per §15.1 P-3); Phase 4.2 eligibility determined.

**Prerequisites (spec §15.1):**
- P-1: All 8 blockers CLOSED, each independently re-audited
- P-2: Stages 1–3 complete
- P-3: Authorization Review explicitly granted implementation authorization
- P-4: §10.2 manifest verified unchanged at moment of implementation
- P-5: §9 baseline re-established and declared (367/464/97)
- P-6: `tests/test_pit_view.py` exists with all mandatory P0 tests
- P-7: No UNKNOWN-authorization artifact in working tree
- P-8: Design-document authorization decision recorded

**Final gate verdicts possible:**
- ALL PASS → implementation authorized → Phase 4.2 eligible
- Any FAIL → NOT_READY → Phase 4.2 forbidden

---

## 5. BLOCKER-BY-BLOCKER CLOSURE PLAN

### Blocker 1 — Phase Ownership Contradictions

| Field | Value |
|-------|-------|
| **Current evidence** | §12.5 executed reconciliation: 5 of 13 components carry contradictory ownership assignments (`InstrumentIdentity`, `InstrumentSpecification`, `Venue`, `DataSource`, `CalendarRef` each assigned `4A.1,4A.2` in retained superseded documents) |
| **Current failure condition** | `EvidenceProvenance` dual-defined: `schemas.py:47 is evidence.py:18` → **False**; `schemas` copy lacks `is_strong_evidence()` |
| **Required implementation work** | R-03: `src/data_engine/schemas.py:47` becomes re-export of `evidence.py:18`; assert `A is B`; R-01: confirm components 7–11 owned by 4A.1 |
| **Permitted to change** | `src/data_engine/schemas.py` (re-export only — this is NOT a frozen Phase 3 method per R-04: freeze is contract-level, not file-level) |
| **Forbidden to change** | `src/data_engine/evidence.py` canonical definition; any Phase 3 frozen method; `docs/strategy_engine_design.md` |
| **Required tests** | SUB-22 (`test_evidence_provenance_single_definition`) |
| **Required evidence artifacts** | `assert schemas.EvidenceProvenance is evidence.EvidenceProvenance` passes; grep yields exactly one phase assignment per component |
| **Independent verification** | Re-audit measures `schemas.EvidenceProvenance is evidence.EvidenceProvenance`; confirms single definition |
| **Exact closure condition** | One authoritative owner per component (§1.2); `EvidenceProvenance` has exactly one definition; contradictory documents superseded/corrected per GOV-02 |
| **Dependencies** | None (can begin in Phase A) |
| **Invalid/false closure** | `assert A is B` fails; dual definition persists; retained superseded documents not marked SUPERSEDED |
| **Rollback condition** | If `schemas.EvidenceProvenance is evidence.EvidenceProvenance` → False, reopen blocker; do not proceed to Blocker 2 identity contract |

**19 ownership rows (spec §1.2):**
1. `TemporalSemantics` — 4A.1 — EXISTS
2. `AvailabilityPolicy` — 4A.1 — EXISTS (defective)
3. `TemporalContract` — 4A.1 — EXISTS
4. Canonical serializer — 4A.1 — EXISTS (defective)
5. Identity hash function — 4A.1 — EXISTS
6. Phase 4 Identity Contract — 4A.1 — DEFINED §2
7. `InstrumentIdentity` — 4A.1 — MISSING
8. `InstrumentSpecification` — 4A.1 — MISSING
9. `Venue` — 4A.1 — MISSING
10. `DataSource` — 4A.1 — MISSING
11. `CalendarRef` — 4A.1 (minimal, id+version only) — MISSING
12. `PitSidecar` — 4A.1 — MISSING
13. `RevisionChain` — 4A.1 — MISSING
14. `TieBreakerPolicy` — 4A.1 — MISSING
15. `PitView` — 4A.1 — MISSING
16. `PitViewBuilder` — 4A.1 — MISSING
17. `PitViewValidator` — 4A.1 — MISSING
18. `ExperimentIdentity` — 4A.1 — MISSING
19. `PitExperimentConfig` — 4A.1 — MISSING

### Blocker 2 — Identity-Contract Specification Gaps

| Field | Value |
|-------|-------|
| **Current evidence** | `identity_hash()` free function ABSENT; no allowlist enforcement; no wall-clock rejection; `extra="forbid"` absent from all `src/data_engine/pit/*` models |
| **Current failure condition** | No Phase 4 identity contract exists; frozen Phase 3 hash methods would contaminate Phase 4 identity if used |
| **Required implementation work** | Implement `identity_hash()` free function (§2.8); implement identity-field allowlists for all identity-bearing entities; implement `extra="forbid"` on all Phase 4 models; implement wall-clock field rejection (ID-WC-01…03) |
| **Permitted to change** | `src/data_engine/pit/*` (Phase 4 components only) |
| **Forbidden to change** | Any Phase 3 frozen method (`Candle.to_hash()`, `ProvenanceRecord.to_hash()`, `StrategySpec.to_hash()`, etc.); `docs/strategy_engine_design.md` |
| **Required tests** | T-H01, T-H02 (2 tests), T-H03, T-H04, SUB-21, SUB-24, SUB-25, TIE-06, EXP-01…05 |
| **Required evidence artifacts** | `identity_hash()` exists and is used by all Phase 4 entities; allowlist enforcement verified; wall-clock fields rejected; `extra="forbid"` on all models |
| **Independent verification** | Re-audit probes: `identity_hash()` called for every entity; `extra="forbid"` present on all models; wall-clock field in allowlist raises (ID-WC-02) |
| **Exact closure condition** | Versioned Phase 4 Identity Contract defines explicit allowlists, audit-only fields, canonical form, type/null/TZ/numeric rules, wall-clock excluded; `pit4.` prefix; contract version `1.0.0` |
| **Dependencies** | Blocker 1 (R-01 ownership of primitives; R-03 re-export must precede identity contract) |
| **Invalid/false closure** | `identity_hash()` absent; `extra="forbid"` missing; wall-clock field accepted; `Candle.to_hash()` enters Phase 4 identity |
| **Rollback condition** | If `identity_hash()` absent or `extra="forbid"` missing from any model, reopen blocker; do not proceed to Blocker 5 PIT components |

### Blocker 3 — Temporal-Contract Gaps

| Field | Value |
|-------|-------|
| **Current evidence** | No ordering validator exists; `ALLOW_NULL` weakens `required_fields`; cutoff boundary behavior measured but untested |
| **Current failure condition** | `TemporalContract(ALLOW_NULL, required_fields=['publication_time'])` accepts null `publication_time` without error; `event_time > observation_time` constructs silently; no composite cutoff evaluation |
| **Required implementation work** | Implement `model_validator(mode="after")` for cross-field ordering (§4.3: `event_time ≤ observation_time ≤ publication_time ≤ revision_time`, null skip, equality valid); implement ALLOW_NULL + required_fields prohibition (§4.2); implement cutoff inclusive boundary (§4.6); implement legacy classification `PIT_INELIGIBLE`/`ASSUMED_PUBLICATION` (§6.3); implement legacy reproducibility (PROH-LEG-06…09) |
| **Permitted to change** | `src/data_engine/pit/temporal.py`, `src/data_engine/pit/contract.py`, `src/data_engine/pit/availability.py` |
| **Forbidden to change** | Phase 3 frozen contracts; `docs/strategy_engine_design.md`; any existing Phase 3 behavior that Phase 4 depends on |
| **Required tests** | T-P01, T-P02, T-P04, T-M01, T-M06, SUB-09, SUB-10, SUB-11, SUB-19, SUB-20, TIE-01…06, VAL-01…04, LEG-T01…03 |
| **Required evidence artifacts** | Ordering constraint enforced (raises on violation); ALLOW_NULL + required_fields raises; cutoff inclusive boundary verified; legacy sidecar reproducibility proven (two builds at different wall-clock times → identical `view_hash`) |
| **Independent verification** | Re-audit probes: `event_time=T+5d, observation_time=T` raises; `ALLOW_NULL` + `required_fields` raises; `publication_time == cutoff` → eligible; `publication_time == cutoff + 1µs` → excluded |
| **Exact closure condition** | Cross-field ordering, required-field semantics, legacy-data rules, cutoff boundary defined and tested; all temporal contracts validated; legacy classification implemented |
| **Dependencies** | Blocker 2 (identity fields for eligibility hash); Blocker 4 (serialization of temporal fields) |
| **Invalid/false closure** | Ordering violation constructs without error; `ALLOW_NULL` + `required_fields` accepts; cutoff boundary exclusive instead of inclusive; legacy sidecar non-reproducible |
| **Rollback condition** | If any temporal constraint not enforced, reopen blocker; do not proceed to Blocker 5 |

### Blocker 4 — Canonical Serialization Alignment

| Field | Value |
|-------|-------|
| **Current evidence** | Serializer NON-CONFORMANT: datetime/string collision; int-key/str-key collision (RA-NF-01, HIGH/BLOCKER); `.10f` absent; `date` unsupported; true subprocess determinism absent |
| **Current failure condition** | `{1:"a"}` and `{"1":"a"}` both serialize to `b'{"1":"a"}'` (RA-NF-01, violates ID-COL-01/ID-COL-04); `datetime` vs ISO string collision; `Decimal('1.0')` → `b'"1.0"'` vs `1.0` → `b'1.0'` not type-distinguished (RA-NF-03); `date` raises `SerializationError` despite §3.1 mandate (RA-NF-02); `date`/`dict` share tag letter `D` (RA-NF-04) |
| **Required implementation work** | Fix `_canonical_value` to reject non-string mapping keys before coercion (SER-KEY-01…05); implement type-tagged encoding for all scalar types; implement `.10f` float policy; implement `date` encoding with distinct tag letter from dict; implement Decimal tagged encoding (`{"d":…}`) and float tagged encoding (`{"f":…}`); implement true subprocess determinism (≥5 subprocesses, COL-PROC-01) |
| **Permitted to change** | `src/data_engine/pit/serialization.py`; `src/data_engine/pit/hashing.py` (subprocess determinism) |
| **Forbidden to change** | Phase 3 frozen contracts; `docs/strategy_engine_design.md`; the canonical encoding contract itself (do not silently weaken or redefine type-tagged encoding) |
| **Required tests** | SUB-04…SUB-08, T-H05, COL-KEY-01…05, COL-DT-01/02, COL-DATE-01…03, COL-NUM-01…04, COL-PROC-01 |
| **Required evidence artifacts** | Collision matrix with all pairs distinct; numeric-policy decision recorded; `{1:"a"}` raises `SerializationError`; `date` serializes to `{"D":"..."}`; `Decimal('1.0')` → `{"d":"1.0"}`, `1.0` → `{"f":"1.0000000000"}`; ≥5 subprocess digests match |
| **Independent verification** | Re-audit probes: `{1:"a"}` raises (not merely differs); `datetime` vs ISO string distinct; `.10f` policy; `date` encoding works; `Decimal` vs `float` distinct by tag; subprocess determinism with ≥5 processes |
| **Exact closure condition** | No type collisions/ambiguity remain; numeric policy explicit; unknown fields rejected; serialization deterministic; all COL-* tests pass; mutation verification satisfied (COL-KEY-01 fails if integer-key coercion restored) |
| **Dependencies** | Blocker 2 (identity contract uses serialization); Blocker 3 (temporal fields serialized) |
| **Invalid/false closure** | `{1:"a"}` coerces instead of raises; `date` unsupported; `Decimal`/`float` not type-distinguished; `.10f` absent; subprocess determinism uses single process; mutation verification fails |
| **Rollback condition** | If any collision confirmed at byte level or mutation verification fails, reopen blocker; do not proceed to Blocker 5 |

### Blocker 5 — PIT Component Specification Gaps

| Field | Value |
|-------|-------|
| **Current evidence** | 13 of 13 required PIT components MISSING from `src/`; both mismatched AvailabilityPolicy pairings construct silently and leak future revision_time; unknown policy key silently dropped |
| **Current failure condition** | No `PitSidecar`, `PitView`, `PitViewBuilder`, `PitViewValidator`, `RevisionChain`, `TieBreakerPolicy`, `ExperimentIdentity`, `PitExperimentConfig`, `InstrumentIdentity`, `InstrumentSpecification`, `Venue`, `DataSource`, `CalendarRef` exist |
| **Required implementation work** | Implement all 13 §7 components per their contracts: `InstrumentIdentity` (§7.7), `InstrumentSpecification` (§7.8), `Venue` (§7.9), `DataSource` (§7.10), `CalendarRef` minimal (§7.11), `PitSidecar` (§7.1), `RevisionChain` (§7.2), `TieBreakerPolicy` (§7.3), `PitView` (§7.4), `PitViewBuilder` (§7.5), `PitViewValidator` (§7.6), `ExperimentIdentity` (§7.12), `PitExperimentConfig` (§7.13). Implement AvailabilityPolicy discriminated union with mismatched-pair rejection (§5.2, §5.3). |
| **Permitted to change** | `src/data_engine/pit/*` (new Phase 4 components) |
| **Forbidden to change** | Phase 3 frozen contracts; `docs/strategy_engine_design.md`; any component outside its authoritative §7 contract |
| **Required tests** | SUB-01…SUB-03, T-R01…T-R04, T-O01, TIE-01…06, VAL-01…04, INST-01…04, SPEC-01…03, VEN-01…02, SRC-01…03, CAL-01…02, EXP-01…05, CFG-01…04 |
| **Required evidence artifacts** | All 13 components exist with correct contracts; mismatched AvailabilityPolicy pairings raise at construction; unknown policy key raises; component-level tests all pass |
| **Independent verification** | Re-audit measures: 13 of 13 components present; mismatched pairings raise; availability policy pairing correct; `PitViewBuilder` reproducibility proven |
| **Exact closure condition** | All 13 §7 contract components fully specified AND implemented; availability pairing type-safe; all component tests pass |
| **Dependencies** | Blockers 2, 3, 4 (components consume identity, temporal, serialization contracts) |
| **Invalid/false closure** | Any component missing; mismatched pairing constructs silently; component implemented outside its contract; `PitViewBuilder` non-reproducible |
| **Rollback condition** | If any component missing or mismatched pairing constructs, reopen blocker; do not proceed to Blocker 6 |

### Blocker 6 — P0/T-PIT Acceptance Gaps

| Field | Value |
|-------|-------|
| **Current evidence** | `tests/test_pit_view.py` absent; 0 of 95 identifiers present anywhere in `tests/`; 4 Category-D weak tests still in `tests/test_pit.py` |
| **Current failure condition** | No Phase 4 acceptance tests exist; the 97-test delta in `tests/test_pit.py` does not contain any P0/T-PIT identifiers |
| **Required implementation work** | Create `tests/test_pit_view.py` with all 95 specified tests (19 P0 + 25 SUB + 33 component + 3 legacy + 15 COL). Replace 4 weak Category-D tests per §8.4. |
| **Permitted to change** | `tests/test_pit_view.py` (new file); `tests/test_pit.py` (replace weak tests only, per §8.4) |
| **Forbidden to change** | Any committed test file other than the 4 weak tests being replaced; any source file in this phase (source is Blocker 5 work) |
| **Required tests** | All 95: T-H01…T-H05, T-P01…T-P04, T-R01…T-R04, T-M01, T-M06, T-O01, T-X01, T-X02, T-X07, SUB-01…SUB-25, TIE-01…06, VAL-01…04, INST-01…04, SPEC-01…03, VEN-01…02, SRC-01…03, CAL-01…02, EXP-01…05, CFG-01…04, LEG-T01…03, COL-KEY-01…05, COL-DT-01/02, COL-DATE-01…03, COL-NUM-01…04, COL-PROC-01 |
| **Required evidence artifacts** | `tests/test_pit_view.py` exists; all 95 tests pass; §8.5.12 reconciliation returns zero undefined; §7→§8 reconciliation empty; mutation verification satisfied for all COL-* tests |
| **Independent verification** | Count identifiers from `tests/test_pit_view.py` against spec §8.5.11; verify 95 = 19+25+33+3+15; verify zero undefined; verify all P0 identifiers present |
| **Exact closure condition** | All 95 specified tests exist as named tests in `tests/test_pit_view.py`; all 95 pass; test count exactly 95; §8.5.12 reconciliation zero undefined |
| **Dependencies** | Blockers 1-5 (tests validate all above) |
| **Invalid/false closure** | Test count ≠ 95; undefined test identifiers; P0 identifiers missing; weak tests unreplaced; tests pass but mutation verification fails |
| **Rollback condition** | If test count ≠ 95 or undefined identifiers exist, reopen blocker; do not proceed to Blocker 7 |

### Blocker 7 — Regression-Baseline Ambiguity

| Field | Value |
|-------|-------|
| **Current evidence** | 367/464/97 independently reproduced; all four weak tests still present; design-doc authorization record still absent |
| **Current failure condition** | Baseline ambiguity: 464 total includes 97 unauthorized delta; weak tests pass while defects they nominally cover remain present; design-doc change (line 2238) unauthorized |
| **Required implementation work** | Declare 367 as authorized baseline with 97 delta separately identified (§9). Replace 4 weak Category-D tests per §8.4. Record design-doc authorization decision for line 2238 (separate human authorization, NOT this plan). Record CRLF normalization decision (DL-D1 Option A already recorded). |
| **Permitted to change** | Documentation records only; test replacement per §8.4 |
| **Forbidden to change** | Absorb 97-test delta into authorized baseline; modify frozen Phase 3 contracts; normalize CRLF; modify design-doc line 2238 without explicit human authorization |
| **Required tests** | SUB-18 (frozen manifest match); §8.4 replacements (all 4); all 95 tests from Blocker 6 |
| **Required evidence artifacts** | Baseline record: 367 authorized / 464 current / 97 delta; weak tests replaced; design-doc authorization artifact; manifest re-recorded if any authorized change |
| **Independent verification** | Re-audit re-runs baseline: 367 passed (--ignore=tests/test_pit.py), 464 total, 97 delta; arithmetic 464−97=367 verified |
| **Exact closure condition** | 367 formally declared authorized baseline; 97 unauthorized delta separately identified; weak tests replaced; design-doc change authorized and committed; manifest re-recorded |
| **Dependencies** | Blockers 1-6; DL-D1 Option A decision record |
| **Invalid/false closure** | 97 delta absorbed into baseline; weak tests unreplaced; design-doc authorization absent; manifest mismatch; baseline arithmetic wrong |
| **Rollback condition** | If baseline arithmetic wrong or design-doc authorization absent, reopen blocker; do not proceed to Design Lock re-attempt |

### Blocker 8 — Filesystem-Security Concern

| Field | Value |
|-------|-------|
| **Current evidence** | Endpoint escape REPRODUCED (1 candle read); `check_connectivity("C:/Windows")` → True; zero containment controls present; audit trail is 90-byte test artifact, not security audit trail |
| **Current failure condition** | No FS-01…FS-24 controls implemented; `ProviderConfig` has no `approved_root`; no `islink()` check; `os.path.exists()` used without containment |
| **Required implementation work** | Implement canonical path resolution (FS-01…FS-03); approved-root containment (FS-04…FS-06); absolute-path and traversal rejection (FS-07…FS-10); symlink/reparse-point handling (FS-11…FS-13); instrument allowlisting (FS-14…FS-16); config strictness `extra="forbid"` (FS-17…FS-19); security audit logging append-only tamper-evident (FS-20…FS-24) |
| **Permitted to change** | `src/data_engine/provider.py`, `src/data_engine/security.py` |
| **Forbidden to change** | Frozen Phase 3 contracts; `docs/strategy_engine_design.md`; security contract itself (do not weaken to make tests pass) |
| **Required tests** | SUB-12…SUB-17, SUB-24, VAL-04 |
| **Required evidence artifacts** | Endpoint escape blocked; `check_connectivity("C:/Windows")` → False; containment enforced; audit trail has actor, path, decision, rule, timestamp; append-only and tamper-evident |
| **Independent verification** | Re-audit re-tests all §11.7 attack vectors; verifies containment; verifies audit trail structure |
| **Exact closure condition** | File access enforces approved-root containment, traversal/absolute-path rejection, symlink handling, strict config, fail-closed behaviour; security tests green |
| **Dependencies** | Independent of blockers 1-7 (separate domain); can proceed in parallel |
| **Invalid/false closure** | Endpoint escape succeeds; `check_connectivity` enumerates arbitrary directories; audit trail missing actor/path/decision/rule; security tests weaken contract to pass |
| **Rollback condition** | If any §11.7 attack reproduces or audit trail is not a security audit trail, reopen blocker |

---

## 6. CLOSURE EVIDENCE REQUIREMENTS (ALL BLOCKERS)

Per INV-07, every blocker closure requires ALL FOUR:
1. **Condition satisfied** — the stated closure criterion is met
2. **Implementation evidence exists** — measurement against live code, not document assertion
3. **Required tests pass** — all blocker-specific tests green, mutation-verified
4. **Independent re-audit confirms** — separate measurement re-confirms closure

No blocker closes on documentation alone. A passing test cannot close a blocker if the test itself is non-conforming (e.g., asserts inequality rather than rejection, loops in one process rather than spawning subprocesses).

---

## 7. DL-D1 THROUGH DL-D5 STATUS IN PLAN

| DL | Status | Plan Action |
|----|--------|-------------|
| DL-D1 | OPEN | Option A in force: no normalization, no design-doc modification, frozen SHA preserved. DL-D1 remains OPEN throughout all phases. |
| DL-D2 | CORRECTED | Already corrected in spec §14.0. Verify at Phase D. |
| DL-D3 | CORRECTED | Already corrected in spec §14.1. Verify at Phase D. |
| DL-D4 | CORRECTED | Already corrected in spec §1.2. Verify at Phase D. |
| DL-D5 | CORRECTED | Already corrected and verified. Verify at Phase D. |

**DL-D1 is the sole unresolved Design Lock defect.** Option A records the human decision to preserve the frozen artifact unchanged. DL-D1 is NOT closed by this plan. Design Lock re-attempt (Phase F) requires DL-D1 resolution OR explicit human decision to downgrade/reclassify DL-D1.

---

## 8. RA-NF-01 THROUGH RA-NF-04 STATUS IN PLAN

| RA-NF | Severity | Status | Plan Action |
|-------|----------|--------|-------------|
| RA-NF-01 | HIGH/BLOCKER | OPEN | Blocker 4: implement SER-KEY-01…05; `{1:"a"}` raises; COL-KEY-01…05 pass; mutation-verified |
| RA-NF-02 | MINOR | OPEN | Blocker 4: implement `date` encoding; COL-DATE-01…03 pass |
| RA-NF-03 | MINOR | OPEN | Blocker 4: implement Decimal/float tagged encoding; COL-NUM-01…04 pass |
| RA-NF-04 | MINOR | OPEN | Blocker 4: assign distinct tag letter for `date` vs `dict`; COL-DATE-03 pass |

---

## 9. BASELINE PRESERVATION

| Metric | Value | Protection |
|--------|-------|------------|
| Authorized baseline | 367 | Committed files only; never absorb delta |
| Current total | 464 | All passing tests in working tree |
| Unauthorized PIT delta | 97 | Kept separate; never merged into baseline |
| Arithmetic | 464 − 97 = 367 | Verified at every phase transition |
| Frozen manifest | 13/13 | Re-verified at Phase D and Phase F |
| Design doc SHA | `8efd870e…802c84` | Preserved per Option A; CRLF=2238 unchanged |

**New Phase 4A.1 tests (95 in `tests/test_pit_view.py`) are NOT part of the authorized baseline** until authorized by explicit human decision. They are specified tests, not baseline tests, per REG-02 and REG-03.

---

## 10. PHASE TRANSITION CRITERIA

| Phase | Entry Criteria | Exit Criteria |
|-------|---------------|---------------|
| A → B | All contracts ratified; no frozen contract modified; 13/13 manifest verified | All Phase B implementation evidence documented; behavioral probes pass |
| B → C | All 13 PIT components implemented; serializer conformant; availability pairing type-safe; filesystem controls implemented | `tests/test_pit_view.py` created; all 95 tests pass |
| C → D | All 95 tests exist and pass; mutation verification satisfied; §8.5.12 reconciliation zero undefined | Independent re-audit RE-AUDIT_PASS; all 8 blockers confirmed closed |
| D → E | All blockers confirmed closed; RE-AUDIT_PASS | Blocker table updated; closure evidence documented; stage history updated |
| E → F | All 8 blockers CLOSED; P-DL-1…P-DL-9 SATISFIED; design-doc authorization for line 2238 recorded and committed; manifest re-recorded if needed | Design Lock PASS or FAIL (measured) |
| F → G | Design Lock PASS; all P-1…P-8 prerequisites met | Final gate verdict; implementation authorization granted (human mechanism); Phase 4.2 eligibility determined |

---

## 11. READ-ONLY SELF-AUDIT OF THIS PLAN

| Check | Result |
|-------|--------|
| All 8 blockers present | ✅ Blockers 1-8 each with full closure plan |
| 19 ownership rows accounted for | ✅ Listed in Blocker 1 section |
| 13 PIT components accounted for | ✅ Listed in Blocker 5 section |
| 95 test IDs/namespaces accounted for | ✅ 19 P0 + 25 SUB + 33 component + 3 legacy + 15 COL = 95 |
| RA-NF-01…04 accounted for | ✅ Blocker 4; RA-NF-01 HIGH/BLOCKER escalated |
| DL-D1…05 accounted for | ✅ Section 7; DL-D1 remains OPEN per Option A |
| 367/464/97 baseline preserved | ✅ Section 9; delta never absorbed |
| Frozen Phase 3 unchanged | ✅ Multiple "Forbidden" entries; INV-01 reaffirmed |
| No implementation occurred | ✅ Planning-only document; no source/test/doc modified |
| All spec terminology used exactly | ✅ SER-KEY-01…05, ID-WC-01…03, PROH-LEG-01…09, FS-01…FS-24, COL-*, T-*, SUB-* |
| Dependency graph explicit | ✅ Section 3; phases sequenced |
| DL-D1 Option A preserved | ✅ Sections 2, 7, 10 |
| No blocker declared closed | ✅ All 8 OPEN; BLOCKERS_CLOSED__0 |
| Design Lock state | ✅ FAILED; DL-D1 OPEN |
| Implementation authorization | ✅ NOT_AUTHORIZED; not granted by this plan |
| Phase 4.2 status | ✅ NOT_AUTHORIZED |

---

## 12. MACHINE-READABLE FINAL STATE

```
PLAN_ONLY__IMPLEMENTATION_NOT_AUTHORIZED
BLOCKERS_CLOSED__0
BLOCKERS_OPEN__8
PHASE_4_2__NOT_AUTHORIZED
```

---

*END DOCUMENT — PHASE 4A.1 MANDATORY BLOCKER CLOSURE EXECUTION PLAN v1.0.0*

*Planning-only document. No code implemented. No test created or modified. No source modified. No design document modified. No frozen Phase 3 contract altered. No CRLF normalization performed. No blocker closed. No authorization granted. No Phase 4.2 authorized.*