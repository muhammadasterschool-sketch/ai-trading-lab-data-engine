# PHASE 4A.1 — BLOCKER 1 POST-IMPLEMENTATION MANIFEST INTEGRITY REVIEW

**Review Date:** 2026-10-05 (Pakistan Standard Time, UTC+05:00)
**Review Type:** READ-ONLY — no files modified
**Documents Reviewed:** 6
**Repository Inspected:** Live

---

## A. IS `src/data_engine/schemas.py` FROZEN?

**File-level freeze:** The §10.2 SHA-256 manifest lists `src/data_engine/schemas.py` with hash `1c5ed4a7369a9a9e7f11ad0a10b914369d6550df912bc913828982c5c72d39b6`. The manifest treats it as a frozen artifact.

**Contract/method-level freeze:** §10.1 Frozen Methods lists only these methods in `schemas.py`:
- `Candle.to_hash()` at `src/data_engine/schemas.py:130`
- `ProvenanceRecord.to_hash()` at `src/data_engine/schemas.py:200`

The `EvidenceProvenance` class is **NOT** in the §10.1 frozen-methods list.

**R-04 explicitly resolves the file-level vs contract-level ambiguity:**
> "Phase 0 does **not** own `schemas.py`, `provider.py`, `validation.py`, `timeframes.py`, `instruments.py` as frozen files. Freeze is **contract-level**, not file-level. File-level freeze claims are SUPERSEDED."

**Conclusion:** `src/data_engine/schemas.py` is frozen at the contract/method level (Candle.to_hash, ProvenanceRecord.to_hash) but NOT at the file level for non-frozen-method content. The EvidenceProvenance class is not a frozen method per §10.1.

---

## B. IS THE R-03 CHANGE TO `EvidenceProvenance` EXPLICITLY AUTHORIZED?

**Yes.** The authoritative remediation specification (§1.3 R-03):
> "`EvidenceProvenance` has **exactly one definition**. `src/data_engine/evidence.py:18` is canonical (it carries `is_strong_evidence()` / `is_valid_for_research()`). `src/data_engine/schemas.py:47` must become a **re-export**, not a second `class` statement. Acceptance: `assert A is B`."

The execution plan (Blocker 1, Phase B, item 1):
> "Implement R-03 re-export (`src/data_engine/schemas.py:47` becomes re-export of `evidence.py:18`). Assert `schemas.EvidenceProvenance is evidence.EvidenceProvenance`."

The change implemented is exactly the R-03 mandate: replace the duplicate class definition with a re-import from evidence.py:18.

**Governing clause:** Spec §1.3 R-03, execution plan §4 Phase B item 1, Blocker 1 closure plan.

---

## C. IS THE §10.2 MANIFEST ALLOWED TO BECOME TEMPORARILY NON-MATCHING?

The spec does not contain an explicit clause saying "the manifest may temporarily mismatch during implementation." However, the following clauses govern this situation:

1. **§10.2 note:** "the recorded hash is of the working-tree state" — the manifest records working-tree SHAs, not committed-state SHAs.
2. **R-04:** "Freeze is contract-level, not file-level. File-level freeze claims are SUPERSEDED." — modifying a non-frozen method in a frozen file is not a frozen-contract violation.
3. **§10.2 manifest requirement:** "SUB-18 MUST recompute and compare this exact manifest. Any mismatch fails the gate immediately." — SUB-18 is a Phase C test that does not exist yet. The manifest re-verification gate is a future-stage gate, not a real-time constraint during implementation.
4. **Execution plan Phase E item 5:** "Re-record §10.2 manifest if any authorized change occurred." — the plan explicitly anticipates manifest re-recording after authorized changes.

**The manifest mismatch is governed but not explicitly described as "temporary."** The governing framework is: the change is authorized (R-03), the file's frozen-method content is unchanged (§10.1), and the plan schedules manifest re-recording in Phase E.

---

## D. DOES THE EXECUTION PLAN AUTHORIZE MANIFEST RE-RECORDING IN PHASE E?

**Yes.** Execution plan §4 Phase E, item 5:
> "Re-record §10.2 manifest if any authorized change occurred."

And §4 Phase F precondition P-DL-9:
> "Frozen manifest unchanged (SATISFIED — 13/13)"

The plan sequences manifest re-recording as Phase E work, after Blocker 1 implementation and before Design Lock re-attempt.

**Governing clause:** Execution plan §4 Phase E item 5, §4 Phase F P-DL-9.

---

## E. DOES ANY RULE REQUIRE 13/13 AT ALL TIMES?

**No explicit rule requires 13/13 at all times during intermediate implementation stages.** The relevant rules:

- **§10.2:** "SUB-18 MUST recompute and compare this exact manifest. Any mismatch fails the gate immediately." — SUB-18 is a test that does not yet exist (Phase C). This is a future-stage gate.
- **§10.4 FRZ-04:** "Any manifest mismatch fails all gates; no partial credit" — this applies to the §10.2 manifest verification gate (SUB-18), not to intermediate implementation states.
- **INV-01:** "No Phase 3 frozen contract is modified. Any change invalidates all downstream gates." — R-03 changes a non-frozen contract element (EvidenceProvenance class is not in §10.1 frozen methods). The change is authorized per R-03.
- **Execution plan Phase E item 5** explicitly schedules manifest re-recording for after authorized changes.

**No rule states "the manifest must remain 13/13 at every moment during implementation."** The manifest mismatch is a consequence of the authorized R-03 change, and the plan provides the governed resolution path (Phase E re-recording).

---

## F. DOES R-03 CONFLICT WITH INV-01, FRZ-01…FRZ-05?

| Rule | Application to R-03 | Conflict? |
|------|---------------------|-----------|
| INV-01 | "No Phase 3 frozen contract is modified" | No — EvidenceProvenance is not a frozen Phase 3 contract per §10.1 |
| FRZ-01 | "No frozen method may be edited" | No — EvidenceProvenance is not in §10.1 frozen-methods list |
| FRZ-02 | "Phase 4 consumes frozen hashes as opaque strings only" | No — not relevant to EvidenceProvenance |
| FRZ-03 | "to_deterministic_hash() MUST NOT be added" | No — not relevant |
| FRZ-04 | "Any manifest mismatch fails all gates" | Governs the future SUB-18 gate, not the intermediate state |
| FRZ-05 | "Frozen-contract regression checked before/after every stage" | The R-03 change is a re-export preserving identity — no regression risk |

**No conflict.** R-03 is explicitly authorized by the spec. The manifest SHA change is a consequence of the authorized change, not a frozen-contract violation.

---

## G. IS THE REPORT'S STATEMENT SUPPORTED?

The report states: "schemas.py SHA changed ... manifest re-recording is scheduled for Phase E."

**Supported by:**
- Execution plan §4 Phase E item 5: "Re-record §10.2 manifest if any authorized change occurred."
- Execution plan §4 Phase E: entry criteria "All Phase B implementation evidence documented"; exit criteria "no frozen Phase 3 contract modified" — schemas.py change is a non-frozen-method re-export, not a frozen-contract modification.

**Partially supported — the plan says "if any authorized change occurred" and R-03 is authorized, so re-recording is explicitly scheduled.** However, the plan does not specify "schemas.py" by name — it uses the general "if any authorized change occurred" clause.

---

## H. CURRENT 12/13 MANIFEST STATE — DETERMINATION

Based on the governing clauses above:

1. **The schemas.py change is explicitly authorized** by spec §1.3 R-03 and the execution plan Blocker 1 Phase B item 1.
2. **The change does not modify a frozen Phase 3 contract method** per §10.1 and R-04.
3. **The manifest re-recording is explicitly scheduled** for Phase E per execution plan §4 Phase E item 5.
4. **No rule requires 13/13 at every intermediate moment** — the governing rules are stage-gated (SUB-18 in Phase C, Phase E re-recording, Phase F P-DL-9).
5. **The mismatch is a known, governed, authorized intermediate state** — not a surprise, not a violation, not requiring human decision at this stage.

**Determination: 1. EXPECTED AND GOVERNED / 2. TEMPORARY BUT AUTHORIZED INTERMEDIATE STATE**

The 12/13 state is the expected consequence of the authorized R-03 change, governed by the spec's contract-level freeze (R-04), and scheduled for resolution in Phase E per the execution plan. It is not a governance violation and does not require a human decision now — the human decision (Option A) is already recorded for DL-D1, and the R-03 change is part of the authorized implementation scope.

---

## I. VERIFICATION RESULTS (READ-ONLY)

| Check | Result |
|-------|--------|
| docs/strategy_engine_design.md SHA | `8efd870ed0149b0cc96d66d82643cb5f3efdb9176b8183896e1696c347802c84` — UNCHANGED ✓ |
| CRLF count | 2238 — UNCHANGED ✓ |
| File size | 95,358 — UNCHANGED ✓ |
| Frozen manifest (other 12) | All SHAs match ✓ |
| schemas.py SHA | Changed (authorized R-03) |
| Other source files | UNCHANGED ✓ |
| Test files | UNCHANGED ✓ |
| tests/test_pit_view.py | ABSENT ✓ |
| Full test suite | 464 passed ✓ |
| Authorized baseline | 367 passed ✓ |
| Delta | 97 (unchanged) ✓ |
| Blocker 1 | IMPLEMENTED — NOT CLOSED ✓ |
| All 8 blockers | OPEN ✓ |
| Phase 4.2 | NOT AUTHORIZED ✓ |

---

## J. EXACT MANIFEST MISMATCH

| Artifact | Pre-change SHA | Post-change SHA | Status |
|----------|---------------|-----------------|--------|
| src/data_engine/schemas.py | `1c5ed4a7…39b6` | `25cdbf0f…4c` | **MISMATCH (authorized)** |
| src/data_engine/evidence.py | `67dd308f…9f` | `67dd308f…9f` | unchanged |
| src/data_engine/strategy/schemas.py | `4a27cc9a…6c` | `4a27cc9a…6c` | unchanged |
| src/data_engine/strategy/provenance.py | `dda729bf…2c` | `dda729bf…2c` | unchanged |
| src/data_engine/strategy/backtest.py | `3b5aacab…613` | `3b5aacab…613` | unchanged |
| src/data_engine/strategy/execution.py | `853aba15…7` | `853aba15…7` | unchanged |
| src/data_engine/strategy/ledger.py | `312ed94a…2a` | `312ed94a…2a` | unchanged |
| src/data_engine/strategy/equity.py | `9ecd12e5…44` | `9ecd12e5…44` | unchanged |
| src/data_engine/strategy/position.py | `d1ef8b83…4e` | `d1ef8b83…4e` | unchanged |
| src/data_engine/strategy/conditions.py | `868a3a56…7` | `868a3a56…7` | unchanged |
| src/data_engine/strategy/metrics.py | `6e30932c…6d` | `6e30932c…6d` | unchanged |
| src/data_engine/strategy/validation.py | `9a589f26…59` | `9a589f26…59` | unchanged |
| src/data_engine/strategy/__init__.py | `47aed9c6…17` | `47aed9c6…17` | unchanged |
| docs/strategy_engine_design.md | `8efd870e…c84` | `8efd870e…c84` | unchanged |

**Mismatch count: 1 of 13 (schemas.py only, authorized R-03 change).**

---

## K. RECOMMENDED NEXT GOVERNANCE ACTION

1. **Proceed to Phase B (Blockers 2–8 implementation)** per the execution plan's dependency graph — Blocker 2 depends on Blocker 1 (R-03 complete, ownership resolved).
2. **Phase E manifest re-recording** — when all implementation is complete, re-record the §10.2 manifest with the new schemas.py SHA.
3. **No human authorization required for the 12/13 state** — the R-03 change is explicitly authorized by the spec and the implementation-start command.

---

## MACHINE-READABLE STATE

```
MANIFEST_STATE__AUTHORIZED_INTERMEDIATE_MISMATCH
BLOCKER_1__IMPLEMENTED__NOT_CLOSED
BLOCKERS_CLOSED__0
BLOCKERS_OPEN__8
PHASE_4_2__NOT_AUTHORIZED
```

---

*Review completed 2026-10-05. Read-only. No files modified. The 12/13 manifest state is governed and authorized per spec §1.3 R-03, R-04, §10.1, and execution plan §4 Phase E item 5. Manifest re-recording scheduled for Phase E.*