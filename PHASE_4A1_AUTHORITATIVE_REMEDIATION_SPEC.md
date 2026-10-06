# PHASE 4A.1 — AUTHORITATIVE REMEDIATION SPECIFICATION v1

**Document Version:** 1.1.0 (Architecture Correction applied 2026-10-01)
**Date:** 2026-10-01
**Branch:** `phase-4a/4a1-temporal-foundation`
**HEAD Commit:** `13fdc7e`
**Source Forensic Gate:** PHASE 4A.1 READ-ONLY FORENSIC GATE REPORT, 2026-10-01 (findings F-01 … F-33)
**Correction Record:** `PHASE_4A1_ARCHITECTURE_CORRECTION_CHECKLIST.md`
**Mode:** SPECIFICATION ONLY — NO IMPLEMENTATION AUTHORIZED

> **v1.1.0 correction note.** Architecture Correction Stage 1 applied five documentation corrections, including three self-audit defects in v1.0.0 (DEFECT-A reconciliation asserted not executed; DEFECT-B undefined test identifiers and a `LEG-*` namespace collision; DEFECT-C stale artifact count).
>
> **Reporting-integrity correction (2026-10-01).** The DEFECT-B undefined-test-identifier count was re-measured: **23, not the 18 originally reported** (§8.5.13). The original figure was produced by a single token grep that counted 2 prohibition IDs as tests, missed 8 range-implied identifiers, and could not match `LEG-REP-01` at all. REG-07 now requires range expansion and namespace separation for any enumeration.
>
> **No blocker was closed. No production code was modified. No test was added.**

---

## 0. DOCUMENT CONTROL

### 0.1 Authority Hierarchy

This document is the **sole working specification** for the Phase 4A.1 architecture-correction stage. Where any pre-existing document conflicts with this document, **this document governs**. Conflicting documents are marked SUPERSEDED in Section 12 but are **retained unmodified** — contradictory history is not overwritten.

| Rank | Class | Documents |
|------|-------|-----------|
| 1 | **THIS DOCUMENT** (sole working spec) | `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` |
| 2 | Frozen Phase 3 design contract (immutable) | `docs/strategy_engine_design.md` |
| 3 | Authoritative evidence inputs (read-only) | Forensic gate report; `HASH_FORENSIC_AUDIT.md`; `PHASE_OWNERSHIP_FORENSIC_AUDIT.md`; `FILESYSTEM_SECURITY_FORENSIC_AUDIT.md` (mechanism claim corrected per Section 12) |
| 4 | Superseded working drafts (retained, non-binding) | See Section 12.1 |
| 5 | Incorrect historical claims (retained, corrected here) | See Section 12.2 |

### 0.2 Findings Incorporated

All 33 forensic findings are dispositioned below. No finding is silently resolved.

**Disposition vocabulary (added 2026-10-01, post-re-audit correction pass).**

| Disposition | Meaning |
|---|---|
| **SPECIFIED** | The requirement is written down. **NOT** evidence that it is implemented, tested, or verified |
| **VERIFIED** | Independently measured against repository evidence and confirmed |
| **RESOLVED** | Condition satisfied **AND** evidence exists **AND** independently re-audited (INV-07) — the only disposition that can affect a blocker |
| **CORRECTED-BY-RECORDATION** | A false or stale claim was replaced with an accurate measurement; the underlying condition remains open |
| **PENDING HUMAN AUTHORIZATION** | Requires a human decision; no agent may apply it |

Every `RESOLVED` disposition below is a **specification-level** resolution. **No
blocker is closed by any row in this table** (INV-07).

#### 0.2.1 Original 33 forensic findings (F-01 … F-33)

| Finding | Disposition | Section |
|---|---|---|
| F-01 phase ownership contradiction | RESOLVED — single owner assigned | §1 |
| F-02 `EvidenceProvenance` duplication | RESOLVED — single definition mandated | §1.3, §7.13 |
| F-03 contradictory audit artifact | RESOLVED — superseded | §12.1 |
| F-04 `Candle.to_hash()` wall-clock dependence | RESOLVED — declared identity-ineligible | §2.4, §10 |
| F-05 `ProvenanceRecord.to_hash()` contamination | RESOLVED — declared identity-ineligible | §2.4, §10 |
| F-06 no identity contract | RESOLVED — contract defined | §2 |
| F-07 serializer type collisions | RESOLVED — type-tagged form mandated | §3 |
| F-08 numeric policy divergence | RESOLVED — policy decided | §3.3 |
| F-09 `to_deterministic_hash()` undefined | RESOLVED — prohibited on Phase 3; free function mandated | §2.8 |
| F-10 wall-clock participation verdict | RESOLVED — prohibition table | §2.4 |
| F-11 temporal field semantics matrix | RESOLVED — 6-field contract defined | §4.1 |
| F-12 no cross-field temporal ordering | RESOLVED — ordering rule defined | §4.3 |
| F-13 `ALLOW_NULL` weakens required | RESOLVED — semantics redefined | §4.2 |
| F-14 legacy fallback fabricates publication | RESOLVED — legacy policy defined | §6 |
| F-15 cutoff boundary unstated | RESOLVED — inclusive rule normative | §4.6 |
| F-16 AvailabilityPolicy mis-pairing | RESOLVED — discriminated union mandated | §5 |
| F-17 extra fields silently ignored | RESOLVED — `extra="forbid"` mandated | §3.7 |
| F-18 missing PIT component specs | RESOLVED — contracts defined | §7 |
| F-19 asset primitives absent | RESOLVED — contracts defined | §7.7–7.11 |
| F-20 ownership of primitives | RESOLVED | §1 |
| F-21 zero P0 identifiers in tests | RESOLVED — matrix defined | §8 |
| F-22 seven missing P0 tests | RESOLVED — matrix defined | §8 |
| F-23 false cross-process test | RESOLVED — true subprocess test mandated | §8.3 |
| F-24 Category-D weak tests | RESOLVED — replacement mandated | §8.4 |
| F-25 baseline contamination | RESOLVED — 367/464/97 declared | §9 |
| F-26 frozen contracts | CONFIRMED FROZEN — manifest recorded | §10.2 |
| F-27 mandatory gates | RESOLVED — 19 gates defined | §8.2 |
| F-28 path traversal via `endpoint` | RESOLVED — containment contract | §11 |
| F-29 no symlink defense | RESOLVED — contract defined (UNVERIFIED on host) | §11.5 |
| F-30 H-14/H-16 security gates | RESOLVED — audit-log contract | §11.8 |
| F-31 design-doc authorization contradiction | RESOLVED — content correct, record required | §12.3 |
| F-32 Phase 3 immunity (verified) | CONFIRMED — no defect | §10.3 |
| F-33 `HASH_FORENSIC_AUDIT` false claim | RESOLVED — corrected, retained | §12.2 |

#### 0.2.2 Post-re-audit findings (RA-NF-01 … RA-NF-04) — registered 2026-10-01

**Provenance is not uniform across these four findings** (distinguished
2026-10-01, DL-D5):

| Finding | Discovered by | Method |
|---|---|---|
| **RA-NF-01, RA-NF-02, RA-NF-03** | `PHASE_4A1_INDEPENDENT_REAUDIT_REPORT.md` v1.0.0 | Independent **measurement** against the live encoder — **not** document review |
| **RA-NF-04** | **The Stage 3.5 post-re-audit documentation correction pass** (this document's own pass; recorded in `PHASE_4A1_POST_REAUDIT_CORRECTION_REPORT.md` v1.0.0) | **Document review** — observed while reading §3.1 in order to construct §3.1a. **NOT** discovered by the independent re-audit |

**Correction record (DL-D5).** An earlier revision of this subsection stated that all
four findings were *"Discovered by `PHASE_4A1_INDEPENDENT_REAUDIT_REPORT.md` v1.0.0
through independent measurement, **not** by document review."* That statement was
**false for RA-NF-04**: the Independent Re-Audit Report contains no RA-NF-04 finding
and its §9 states that it raised **three** findings (RA-NF-01…RA-NF-03). RA-NF-04 is
correctly attributed to the Stage 3.5 pass in §15.2 correction row M, so the earlier
statement also contradicted this document. The per-finding provenance table above is
authoritative. **No substantive RA-NF-04 content was changed by DL-D5** — severity,
disposition, specification reference, and mandate are unchanged.

| Finding | Severity | Disposition | Specification | Section |
|---|---|---|---|---|
| **RA-NF-01** integer-key/string-key canonical-byte collision — `{1:"a"}` and `{"1":"a"}` both serialize to `b'{"1":"a"}'`; distinct inputs, identical identity, no error raised | **HIGH / BLOCKER** | **SPECIFIED only — NOT resolved.** `SER-KEY-01…05` mandate string-only keys with mandatory rejection. Implementation absent | Rules written; tests specified | §3.1a.1, §8.6 |
| **RA-NF-02** bare `date` rejected by the encoder although §3.1 mandates a `{"D": …}` encoding; date-bearing identity fields (§7.8, §7.11) are currently unserializable | MINOR (conformance gap) | **SPECIFIED only — NOT resolved.** Supported representation defined normatively; implementation **deliberately not** performed in this documentation pass | Representation defined | §3.1a.2, §8.6 |
| **RA-NF-03** `Decimal`/`float` distinction relies on incidental `json.dumps` quoting rather than the mandated explicit `{"d":…}`/`{"f":…}` tags; **not** a collision | MINOR (conformance gap) | **SPECIFIED only — NOT resolved.** Normative representation defined; implementation **deliberately not** performed | Representation defined | §3.1a.3, §8.6 |
| **RA-NF-04** §3.1 `date` row and `dict` row share the tag letter `D`; distinguishable by JSON payload type, so **not** a proven collision, but an avoidable ambiguity | MINOR (specification clarity) | **SPECIFIED only — NOT resolved.** Distinct tag letter required before implementation | Clarity requirement | §3.1, §3.1a.2 |

**RA-NF-01 is classified HIGH / BLOCKER** under the existing identity-contract
rules: it violates **ID-COL-01** (semantically distinct values MUST NOT produce
identical canonical bytes) and **ID-COL-04** (integer and string dictionary keys
MUST NOT collide). It is a *silent* failure — distinct inputs, identical Phase 4
identity, no exception raised.

#### 0.2.3 Documentation-integrity defects found by the re-audit

| Defect | Disposition | Section |
|---|---|---|
| **DL-D1** false claim "Line endings \| LF only (CRLF count = 0) ✓" while the frozen design document measures CRLF = 2238 | **CORRECTED-BY-RECORDATION** in §12.3. Normalization **PENDING HUMAN AUTHORIZATION** (§12.3.1). Frozen file unchanged byte-for-byte | §12.3, §12.3.1 |
| **DL-D2** §14 stated "Stage 1 has not begun" and "NEXT AUTHORIZED STAGE" while §15.2 recorded Stage 1 complete | **CORRECTED** — stage history rewritten with measured states | §14.0 |
| **DL-D3** §14 re-introduced a hard-coded "27 untracked artifacts" as an active requirement, violating REG-06 | **CORRECTED** — hard-coded count demoted to a dated historical measurement; live count governed by REG-06 | §14.1 |
| **DL-D4** component-count contradiction: §1.2 declared 19 while five other locations used 13, with no stated reconciliation | **CORRECTED** — reconciliation stated explicitly (13 §7 contract sections + 6 foundation components = 19 owned) | §1.2, §14.1 |
| **DL-D3′** `PHASE_4A1_ARCHITECTURE_CORRECTION_CHECKLIST.md` and `..._REPORT.md` retained the superseded "18" figure while appearing in **no** supersession list — neither governing nor superseded (GOV-04 gap) | **CORRECTED** — both documents added to §12.1 with explicit supersession scope | §12.1 |
| **DL-D5** RA-NF-04 provenance misattributed: §0.2.2 and §12.1 credited the Independent Re-Audit Report with all four findings and claimed discovery "not by document review", while the re-audit report contains no RA-NF-04 and states it raised three findings — the specification also contradicted its own §15.2 (GOV-04 gap) | **CORRECTED** — §0.2.2 now states per-finding provenance (RA-NF-01…03 by re-audit measurement; RA-NF-04 by document review during the Stage 3.5 pass); §12.1 scoped the re-audit report to RA-NF-01…03 and recorded `PHASE_4A1_POST_REAUDIT_CORRECTION_REPORT.md` as RA-NF-04's source. Found by the Design Lock re-attempt, **not** by the re-audit | §0.2.2, §12.1 |

**DL-D1 is corrected by recordation, not by fix.** The underlying non-conformance
is real and remains open.

### 0.3 Global Invariants

| ID | Invariant |
|----|-----------|
| INV-01 | No Phase 3 frozen contract is modified. Any change invalidates all downstream gates. |
| INV-02 | No wall-clock value participates in any Phase 4 identity. |
| INV-03 | Identity is a pure function of declared identity fields. Same inputs → same hash, always, in any process, at any time. |
| INV-04 | PIT eligibility is determined solely by declared temporal semantics. Availability is never inferred from ingestion or retrieval. |
| INV-05 | Information unavailable at a historical cutoff MUST NOT influence any decision made at that cutoff. |
| INV-06 | A component with an unsatisfied dependency is BLOCKED, never partially implemented. |
| INV-07 | No blocker closes on documentation alone. Closure requires condition + evidence + independent re-audit. |

---

## SECTION 1 — AUTHORITATIVE SCOPE

### 1.1 Phase 4A.1 Definition

Phase 4A.1 delivers the **temporal and point-in-time foundation**: the minimum set of immutable, declarative contracts required to answer *"what was knowable at time T, and can that answer be reproduced exactly?"* for historical research.

Phase 4A.1 delivers **contracts and determinism guarantees only**. It does not deliver full multi-asset domain systems, calendar computation, corporate-action modelling, or live data.

### 1.2 Ownership Table — SINGLE OWNER PER COMPONENT

This table is the **sole ownership authority** for Phase 4A.1. Any statement elsewhere assigning a different phase to any row is SUPERSEDED.

| # | Component | Owner Phase | Status | Rationale |
|---|-----------|-------------|--------|-----------|
| 1 | `TemporalSemantics` | **4A.1** | EXISTS | Foundational temporal value type; no dependency on view construction |
| 2 | `AvailabilityPolicy` | **4A.1** | EXISTS (defective) | Declares availability semantics per data type |
| 3 | `TemporalContract` | **4A.1** | EXISTS | Declares per-type temporal requirements |
| 4 | Canonical serializer | **4A.1** | EXISTS (defective) | Identity substrate for all 4A.1 entities |
| 5 | Identity hash function | **4A.1** | EXISTS | SHA-256 over canonical bytes |
| 6 | Phase 4 Identity Contract | **4A.1** | DEFINED §2 | Sole identity authority |
| 7 | `InstrumentIdentity` | **4A.1** | MISSING | Required in `view_hash`/`experiment_id` (UQ-09/UQ-12) |
| 8 | `InstrumentSpecification` | **4A.1** | MISSING | Effective-dated contract specification; identity input |
| 9 | `Venue` | **4A.1** | MISSING | Exchange + timezone is an identity input |
| 10 | `DataSource` | **4A.1** | MISSING | Provider identity is an identity input |
| 11 | `CalendarRef` | **4A.1** (minimal, id+version only) | MISSING | Identity input only; **no calendar computation** |
| 12 | `PitSidecar` | **4A.1** | MISSING | Immutable temporal snapshot per dataset version |
| 13 | `RevisionChain` | **4A.1** | MISSING | Append-only revision history |
| 14 | `TieBreakerPolicy` | **4A.1** | MISSING | Deterministic equal-time ordering |
| 15 | `PitView` | **4A.1** | MISSING | Immutable PIT-filtered dataset |
| 16 | `PitViewBuilder` | **4A.1** | MISSING | View construction |
| 17 | `PitViewValidator` | **4A.1** | MISSING | View correctness verification |
| 18 | `ExperimentIdentity` | **4A.1** | MISSING | Deterministic experiment identity |
| 19 | `PitExperimentConfig` | **4A.1** | MISSING | PIT-aware experiment configuration |

**Component count: 19** (supersedes the "13 primitives" count in `PHASE_4A1_IMPLEMENTATION_SPEC.md` §2.1, which omitted the four existing foundation components and counted inconsistently).

**Reconciliation of "13" vs "19" (added 2026-10-01, post-re-audit correction — DL-D4).** Earlier revisions declared 19 here while five other locations used 13, with no stated reconciliation. The two numbers measure different things:

| Count | What it measures | Composition |
|---|---|---|
| **19** | Owned components in the Phase 4A.1 ownership table (rows 1–19 above) | 6 foundation (rows 1–6: `TemporalSemantics`, `AvailabilityPolicy`, `TemporalContract`, canonical serializer, identity hash function, Phase 4 Identity Contract) + 13 contract-defined components (rows 7–19) |
| **13** | Contract sections that carry a full contract body in §7 | §7.1–§7.13 |

**Therefore: 13 §7 contract sections + 6 foundation components = 19 owned
components.** Both counts are correct within their own scope. Every future
reference MUST state which count it uses. A bare "13 components" in a blocker or
status table means the §7 contract set; a bare "19" means the full ownership set.

### 1.3 Ownership Resolutions (F-01, F-02, F-03, F-20)

**R-01** — Components 7–11 (`InstrumentIdentity`, `InstrumentSpecification`, `Venue`, `DataSource`, `CalendarRef`) are **owned by 4A.1**. The contradictory statements "Not used in 4A.1 (deferred)" (`PHASE_4A1_IMPLEMENTATION_SPEC.md` lines 834–836) and "Deferred to 4A.2" (same file, line 857) are **SUPERSEDED**. Rationale: these are identity inputs to `view_hash` and `experiment_id`; a 4A.1 whose identity omits the venue cannot reproduce a historical result.

**R-02** — `CalendarRef` is **minimal in 4A.1**: `calendar_id` + `calendar_version` only. No holiday logic, no session determination, no trading-day computation. Full calendar infrastructure is 4A.2.

**R-03** — `EvidenceProvenance` has **exactly one definition**. `src/data_engine/evidence.py:18` is canonical (it carries `is_strong_evidence()` / `is_valid_for_research()`). `src/data_engine/schemas.py:47` must become a **re-export**, not a second `class` statement. Acceptance: `assert A is B`.

**R-04** — Phase 0 does **not** own `schemas.py`, `provider.py`, `validation.py`, `timeframes.py`, `instruments.py` as frozen files. Freeze is **contract-level**, not file-level. File-level freeze claims are SUPERSEDED.

### 1.4 Deferred Components and Their Owning Phases

| Component / Capability | Owning Phase | Notes |
|---|---|---|
| Full calendar registry, holiday engine, session determination | **4A.2** | Requires full `CalendarRef` infrastructure |
| `CorporateAction` engine | **4A.2** | Equity-specific |
| `PointInTimeUniverse` (survivorship-bias-free instrument universe) | **4A.2** | Depends on 4A.1 instrument primitives |
| `FuturesContract` | **4A.3** | Futures-specific |
| `ContinuousSeries` (rollover) | **4A.3** | Requires `FuturesContract` |
| FX financing / swap model | **4A.4** | FX-specific |
| `ResearchContract` | **4A.4** | Research governance |
| `ApprovalMetadata` (`approval_timestamp` introduced) | **4A.4** | Approval governance |
| Live execution, broker integration, real-money trading | **NEVER** | Permanently excluded |
| Automated strategy optimization | **4A+** | Out of scope |

**No 4A.2+ capability may leak backward into 4A.1.** Any 4A.1 component requiring calendar computation or universe membership is a scope violation (Section 7.11).

---

## SECTION 2 — PHASE 4 IDENTITY CONTRACT

### 2.1 Independence from Phase 3

Phase 4 identity is a **separate contract**. It MUST NOT reuse, wrap, extend, or modify any frozen Phase 3 hash method. Rationale: `Candle.to_hash()` and `ProvenanceRecord.to_hash()` are provably wall-clock dependent (F-04, F-05) and would contaminate any identity built on them.

### 2.2 Identity Field Classification

Every field of every identity-bearing entity MUST be classified into exactly one of three classes. **Classification is exhaustive and mutually exclusive.**

| Class | Definition | Participates in identity? |
|---|---|---|
| **IDENTITY** | Content or semantics that define *what the thing is* | **YES** |
| **ELIGIBILITY** | Fields that determine PIT availability (temporal semantics) | **YES** (via eligibility hash) |
| **AUDIT** | Wall-clock, operational, or provenance-of-retrieval metadata | **NO — NEVER** |

### 2.3 Identity-Field Allowlist Format

Each identity-bearing entity declares its allowlist as an **ordered tuple of field names**. Order is explicit and frozen; it is never alphabetical, never hash-ordered, never declaration-order-dependent.

```
identity_fields: tuple[str, ...]        # ordered, explicit, version-controlled
```

The allowlist is **positively declared**. Absence from the allowlist excludes a field. No deny-list, no "exclude known audit fields" pattern, no whole-model serialization.

### 2.4 Prohibited Wall-Clock Fields (MANDATORY)

The following fields are **AUDIT** class and MUST NOT appear in any Phase 4 identity allowlist:

| Field | Location | Verified status |
|---|---|---|
| `provider_timestamp` | `Candle` | **CONTAMINATED** — `default_factory` populates current wall clock; hash differs across constructions (F-04) |
| `retrieval_timestamp` | `ProvenanceRecord` | **CONTAMINATED** — hash differs on +365d (F-05) |
| `ingestion_time` | `TemporalSemantics` | SAFE — already excluded from `temporal_hash_input()` |
| `created_at` | `DatasetVersion` | POTENTIAL — `default_factory=_now_utc` |
| `run_timestamp` | `BacktestProvenance` | SAFE — popped in `provenance.py:112` |
| `approval_timestamp` | `ApprovalMetadata` (4A.4) | N/A — not present in repository |

**Rule ID-WC-01:** No field listed above may appear in any Phase 4 identity allowlist, directly or transitively.
**Rule ID-WC-02:** An allowlist containing any prohibited field MUST raise at construction.
**Rule ID-WC-03:** Identity MUST be a pure function of the allowlisted values. No ambient clock, RNG, PID, path, locale, or environment variable may be read.

### 2.5 Canonical Form

```
IDENTITY_HASH = "pit4." + SHA256_HEX(canonical_bytes(identity_payload))
```

- `identity_payload` = an ordered mapping built **only** from `identity_fields`
- `canonical_bytes` = the Phase 4 canonical serializer (Section 3)
- Encoding: UTF-8
- Hash: SHA-256, lowercase hex, 64 characters
- Output prefix: `pit4.` (6 characters) + 64 hex = 70 characters total

### 2.6 Versioning Rules

| Aspect | Rule |
|---|---|
| Hash version | `pit4` in the prefix; changing the prefix invalidates every Phase 4 identity |
| Contract version | `PHASE4_IDENTITY_CONTRACT_VERSION = "1.0.0"`, included in the identity payload for every entity |
| Entity schema version | Each entity declares its own `schema_version`, included in identity |
| Additive field | Bumping `schema_version` produces a different hash. **Old hashes are never silently reinterpreted** |
| Field removal / rename | Breaking change; requires major version bump and a documented migration |
| Reordering | **Breaking.** Field order is part of the contract |

### 2.7 Eligibility Hash

Temporal semantics that govern PIT availability are hashed separately and composed:

```
ELIGIBILITY_HASH = "pit4e." + SHA256_HEX(canonical_bytes({
    "event_time", "observation_time", "publication_time",
    "effective_time", "revision_time",     # ingestion_time EXCLUDED
}))
```

This is the existing `TemporalSemantics.temporal_hash_input()` principle, retained and formally specified.

### 2.8 Identity Function (F-09 resolution)

`to_deterministic_hash()` **MUST NOT** be added to `Candle`, `ProvenanceRecord`, or any other frozen Phase 3 class. Doing so would modify a frozen contract (INV-01).

The mandated form is a **free function**:

```python
def identity_hash(entity_type: str, schema_version: str,
                  identity_fields: tuple[str, ...],
                  values: Mapping[str, Any]) -> str: ...
```

It reads only the named fields. It never imports, calls, or reflects on any Phase 3 hash method.

### 2.9 Collision and Ambiguity Requirements

| ID | Requirement |
|----|-------------|
| ID-COL-01 | Two semantically distinct values MUST NOT produce identical canonical bytes |
| ID-COL-02 | Type is part of identity: `1` and `"1"` and `True` MUST serialize distinctly (F-07) |
| ID-COL-03 | A `datetime` and its ISO-8601 string MUST serialize distinctly (F-07) |
| ID-COL-04 | Integer and string dictionary keys MUST NOT collide (F-07) |
| ID-COL-05 | `None` MUST serialize distinctly from every non-null value |
| ID-COL-06 | The serializer MUST reject any value it cannot unambiguously encode |
| ID-COL-07 | Ambiguous input MUST fail closed, never default |

---

## SECTION 3 — CANONICAL SERIALIZATION CONTRACT

### 3.1 Type-Tagged Encoding (F-07 resolution)

The existing `canonical_serialize()` is **NON-CONFORMANT** because it erases type distinctions. Two provable collisions exist:

| Input pair | Current output | Verdict |
|---|---|---|
| `{1: "a"}` vs `{"1": "a"}` | `{"1":"a"}` both | **COLLISION** |
| `datetime(2024,1,1,tz=UTC)` vs `"2024-01-01T00:00:00+00:00"` | `"2024-01-01T00:00:00+00:00"` both | **COLLISION** |

**Mandate:** every scalar is emitted with an explicit type tag.

| Type | Encoded form | Example |
|---|---|---|
| `None` | `null` | `null` |
| `bool` | `{"b": <literal>}` | `{"b":true}` |
| `int` | `{"i": "<base-10>"}` | `{"i":"42"}` |
| `float` | `{"f": "<normalized>"}` | `{"f":"100.5000000000"}` |
| `Decimal` | `{"d": "<exact string>"}` | `{"d":"1.0"}` |
| `str` | `{"s": "<escaped>"}` | `{"s":"XAU/USD"}` |
| `datetime` | `{"t": "<ISO-8601 UTC>"}` | `{"t":"2024-01-01T00:00:00+00:00"}` |
| `date` | `{"D": "<ISO-8601>"}` | `{"D":"2024-01-01"}` |
| `list` / `tuple` | `{"L":[ ... ]}` | `{"L":[{"i":"1"}]}` |
| `dict` | `{"D":{"<key>":<value>}}` with string keys only | `{"D":{"a":{"i":"1"}}}` |

`tuple` is accepted and encoded identically to `list` (the current rejection of `tuple` is retained only where a *distinction* is required; by default tuple ≡ list, documented).

**Tag-collision observation on this table (recorded 2026-10-01, post-re-audit).** The
`date` row and the `dict` row both use the tag letter `D`. They remain
distinguishable because their payloads differ in JSON type (`{"D":"2024-01-01"}`
is a string payload, `{"D":{...}}` is an object payload), so this is **not** a
proven collision. It is nonetheless an avoidable ambiguity and is registered as
**RA-NF-04 (MINOR, specification clarity)** in §0.2. The `date` tag MUST be
changed to a distinct letter (`{"d_": ...}` is prohibited — see §3.1a) before
implementation, so that no implementer reproduces the ambiguity.

### 3.1a Canonical-Encoding Conformance — RA-NF-01, RA-NF-02, RA-NF-03

This subsection was added by the post-re-audit documentation correction pass
(2026-10-01) to close three conformance gaps discovered by independent
measurement. It is **specification only** — no encoder is implemented by this
document.

#### 3.1a.1 RA-NF-01 — Mapping keys MUST be strings; non-string keys MUST raise (HIGH / BLOCKER)

**Finding.** Independently measured: `{1: "a"}` and `{"1": "a"}` both serialize to
the identical canonical bytes `b'{"1":"a"}'`. The §3.1 table predicted this
collision at the value-normalization layer; measurement confirms it **survives to
the canonical bytes**, so the two inputs are indistinguishable in any Phase 4
identity. §3.2's requirement that non-string keys MUST raise is not implemented —
the integer key is silently coerced to `"1"`.

**Classification: HIGH / BLOCKER.** This violates **ID-COL-04** and **ID-COL-01**
directly. Two semantically distinct values producing identical canonical bytes is
the precise failure the identity contract exists to prevent, and it is a
*silent* one: no error, no warning, distinct inputs, identical identity.

**Mandate (normative):**

| Rule | Statement |
|---|---|
| SER-KEY-01 | Every mapping key MUST be a `str`. A non-string key MUST raise `SerializationError` **before** any coercion |
| SER-KEY-02 | Coercing `1` → `"1"`, `True` → `"True"`, `Decimal('1')` → `"1"`, `date` → ISO string, or any other implicit key conversion is **PROHIBITED** |
| SER-KEY-03 | Because the encoding is type-tagged (§3.1), keys are encoded as `{"s": <escaped key>}` inside the mapping wrapper, so a key can never be confused with a bare scalar |
| SER-KEY-04 | The encoder MUST fail closed: an unrepresentable key is an error, never a fallback (ID-COL-07) |
| SER-KEY-05 | This rule applies recursively at every nesting depth |

**Adversarial requirement.** A test MUST construct `{1: "a"}` and `{"1": "a"}` and
demonstrate that the non-string-key form **raises**, rather than demonstrating
merely that the two outputs differ. Both outcomes satisfy ID-COL-04; only
raising satisfies SER-KEY-01/02. A test that only asserts inequality is
**insufficient**.

#### 3.1a.2 RA-NF-02 — `date` representation defined explicitly (conformance gap)

**Finding.** Independently measured: `canonical_serialize(date(2024,1,1))` raises
`SerializationError: Unsupported canonical type: date`. §3.1 nonetheless mandates
a `{"D": "<ISO-8601>"}` encoding for `date`. The mandated encoding was never
implemented and the §3.1 collision analysis did not notice the gap.

**Classification: specification/implementation conformance gap.**

**Decision — the intended supported representation is defined here:**

| Aspect | Decision |
|---|---|
| Is `date` in scope for Phase 4 identity? | **YES.** `InstrumentSpecification.effective_from`/`effective_to` (§7.8) and `CalendarRef` boundaries (§7.11) are date-valued |
| Encoding | `{"D": "<ISO-8601 date>"}` — a **string** payload, ISO-8601 `YYYY-MM-DD`, no time component, no timezone suffix |
| Must it be distinct from `datetime`? | **YES** — a `date` and a `datetime` MUST serialize distinctly. The tag letter differs from the `datetime` tag `{"t": …}` |
| Naive/invalid dates | MUST raise `SerializationError` |
| Timezone-bearing conversion | A `date` MUST NOT be implicitly widened to `datetime`; a caller requiring a datetime MUST construct one explicitly |
| Future Phase 4 components carrying dates | MUST NOT be unserializable — this gap currently makes any date-bearing identity field unusable |

Per §3.1a's tag-collision observation, the `date` tag MUST be assigned a letter
distinct from the `dict` tag before implementation (RA-NF-04).

#### 3.1a.3 RA-NF-03 — `Decimal` and `float` representation defined explicitly (conformance gap)

**Finding.** Independently measured: `Decimal('1.0')` → `b'"1.0"'` and `1.0` →
`b'1.0'`. These two are in fact **distinguishable** at the byte level, because
JSON string-quoting differs from a bare number. This is therefore **NOT a
collision** and is not a BLOCKER.

**Classification: canonical-serialization conformance gap** against §3.1, which
mandates explicit `{"d": …}` and `{"f": …}` tags. The implementation relies on
*incidental* JSON formatting rather than the mandated explicit tags.

**Why the gap matters even though no collision exists.** The distinction is
currently an accident of `json.dumps`, not a designed guarantee. It is not stated
anywhere that `Decimal` MUST be encoded as a quoted string and `float` as a bare
number, so a future encoder change could silently remove the distinction. The
Phase 3 D4 numerical policy makes `Decimal`/`float` bridging a governed concern;
leaving this to incidental formatting is not acceptable in an identity substrate.

**Decision — normative representation:**

| Type | Encoding | Example | Never |
|---|---|---|---|
| `Decimal` | `{"d": "<exact str(Decimal)>"}` — quoted, exact, no float conversion, no rounding | `{"d":"1.10"}` | Never `float(d)`, never `.10f` |
| `float` | `{"f": "<.10f normalized>"}` — always 10 decimal places, `-0.0` → `0.0`, NaN/±Inf rejected | `{"f":"100.5000000000"}` | Never full binary64 `repr` |
| `int` | `{"i": "<base-10>"}` | `{"i":"42"}` | Never a bare JSON number |
| `bool` | `{"b": <literal>}` | `{"b":true}` | Never `{"i":"1"}` — `True` and `1` MUST differ |

`Decimal('1.0')` and `1.0` MUST therefore serialize to `{"d":"1.0"}` and
`{"f":"1.0000000000"}` respectively — distinct by tag *and* by value form.

### 3.2 Dictionary and List Ordering

| Rule | Statement |
|---|---|
| Dict keys | MUST be strings. Non-string keys MUST raise. Sorted by Unicode code point (deterministic across platforms and locales) |
| List order | **Preserved and significant.** `[1,2]` and `[2,1]` are different identities |
| No implicit sorting | Values inside lists are never sorted |
| Nested dicts | Sorted recursively at every depth |

### 3.3 Numeric Normalization (F-08 resolution)

**Decision: Phase 4 adopts the Phase 3 `.10f` float policy.**

| Aspect | Rule |
|---|---|
| `float` | Formatted `.10f` (10 decimal places) |
| `-0.0` | Normalized to `0.0` before formatting |
| `NaN` | **REJECTED** (`SerializationError`) |
| `+Inf` / `-Inf` | **REJECTED** (`SerializationError`) |
| `int` | Base-10, no leading zeros, no thousands separators |
| `Decimal` | Exact string via `str()`; **no rounding**, no float conversion |
| Rounding mode | Python default round-half-even at the 10th decimal. This is **explicit and documented**, not assumed downward |

**Rationale:** Phase 3 (`docs/strategy_engine_design.md` §I) mandates `.10f`. Phase 4 currently emits full binary64 repr (`0.1+0.2` → `0.30000000000000004`). Two policies in one system make cross-phase hash comparability undefined. Alignment removes the divergence at zero cost, because `experiment_id` composes frozen Phase 3 hashes with new Phase 4 hashes.

### 3.4 Null Representation

`None` → `null` (JSON null, inside the type-tagged form). It is distinct from the string `"<NULL>"`, from `""`, and from every other value. An entity with an absent optional field and one with an explicitly-empty optional field have **different** identities.

### 3.5 Encoding and Escaping

| Aspect | Rule |
|---|---|
| Encoding | UTF-8, no BOM |
| Separators | `,` and `:` with no whitespace |
| Control characters | `\uXXXX` escaped |
| Backslash / quote | `\\`, `\"` |
| Non-ASCII | Emitted literally as UTF-8 (not `\u`-escaped), so `XAU/USD` and `EUR/USD` are unambiguous |
| Line endings | Irrelevant — the canonical form is single-line JSON |

### 3.6 Unsupported Types (F-17, ID-COL-06)

`set`, `frozenset`, `bytes`, arbitrary objects, callables, and Pydantic models not explicitly whitelisted MUST raise `SerializationError`. **Fail closed.**

### 3.7 Extra-Field Behavior (F-17 resolution)

**Mandate:** every Phase 4 model declares:

```python
model_config = ConfigDict(frozen=True, extra="forbid")
```

Currently verified defect: `AvailabilityPolicy(rule_type="publication_controlled", policy={"require_publication":True,"evil":1})` is **accepted**, silently dropping `evil`. Under `extra="forbid"` this MUST raise. A misspelled policy key must never silently weaken enforcement.

---

## SECTION 4 — TEMPORAL SEMANTICS CONTRACT

### 4.1 Field Definitions (F-11)

| Field | Semantic meaning | Class | Required | Timezone |
|---|---|---|---|---|
| `event_time` | When the event actually occurred | IDENTITY/ELIGIBILITY | **Required** (all types) | UTC-aware, normalized |
| `observation_time` | When the observation was recorded by the source | ELIGIBILITY | **Required** (all types) | UTC-aware, normalized |
| `publication_time` | When the data became publicly available | ELIGIBILITY | Required for ECONOMIC, NEWS; optional for OHLCV | UTC-aware, normalized |
| `effective_time` | When the data becomes applicable/effective | ELIGIBILITY | Optional | UTC-aware, normalized |
| `revision_time` | When **this specific revision** was published | ELIGIBILITY | Required when a revision chain exists | UTC-aware, normalized |
| `ingestion_time` | When **this system** ingested the data | **AUDIT** | Optional | UTC-aware, normalized |

### 4.2 Required vs Optional Semantics (F-13 resolution)

The existing `MissingFieldPolicy` has three values, and `ALLOW_NULL` silently defeats `required_fields`. **Redefined:**

| Policy | Old behaviour | **New normative behaviour** |
|---|---|---|
| `REJECT` | Raises on missing required | **Unchanged** — raises |
| `REQUIRE_NON_NULL` | Raises on missing required | **Unchanged** — raises |
| `ALLOW_NULL` | Silently skipped the check | **PROHIBITED** — a contract MUST NOT contain a field in `required_fields` while `missing_field_policy = ALLOW_NULL`. Construction MUST raise |

Fields permitted to be null belong in `optional_fields`. A field MUST NOT appear in both lists, and MUST NOT appear in neither (except `ingestion_time`, which is AUDIT-class and exempt from eligibility).

### 4.3 Cross-Field Ordering Constraints (F-12 resolution)

The existing model has **one** validator (timezone). No ordering constraint exists. **Mandate a `model_validator(mode="after")` enforcing, when all operands are present:**

```
event_time      <= observation_time
observation_time <= publication_time     (when publication_time is present)
publication_time <= revision_time        (when both present)
```

Additional rules:

| Rule | Statement |
|---|---|
| Equality | Equality at any boundary is **valid** (zero-delay publication is legitimate) |
| Null operands | A null operand **skips** its constraint; it does not fail |
| `effective_time` | No ordering constraint against `publication_time`; a backdated effective date is legitimate. `max_delay_seconds` bounds it as a *quality* check, not an ordering rule |
| Failure | Raises `ValueError` naming both fields and both values |
| Scope | Applies to `TemporalSemantics` and `PitSidecar` |

### 4.4 Timezone Requirements

| Rule | Statement |
|---|---|
| Awareness | Naive datetimes are **rejected** at validation. No exception, no coercion |
| Normalization | All aware datetimes are converted to UTC on construction |
| `timezone_requirement` | `Literal["UTC"]` — any other value raises |
| Storage | Canonical form is UTC with explicit offset |

### 4.5 Null Behaviour

| Condition | Behaviour |
|---|---|
| Required field null | Raise per §4.2 |
| Optional field null | Permitted; serialized as `null`; **distinguishable from absent** |
| `ingestion_time` null | Permitted; never affects eligibility |
| Null in a revision chain | Chain validation MUST reject — a chain entry without `revision_time` is malformed |

### 4.6 Cutoff Semantics (F-15 resolution)

**NORMATIVE — inclusive boundary:**

```
publication_time <= cutoff   =>  ELIGIBLE
publication_time >  cutoff   =>  EXCLUDED
```

At exact equality the item **IS eligible**. `publication_time == cutoff` is included; `cutoff + 1µs` is excluded. This rule is normative for every availability policy, without exception.

Composite cutoff evaluation for a `RevisionChain` at cutoff `T`:

```
eligible(revision)  iff  revision.revision_time <= T
                    AND  revision.publication_time <= T
                    AND  revision is not superseded by a revision with revision_time <= T
selected            =  max(revision_time) among eligible
```

### 4.7 Future-Data Behaviour

| Condition | Behaviour |
|---|---|
| `event_time > cutoff` | Data about the future is **not an error**; it is excluded from the view |
| `publication_time > cutoff` | Excluded silently (T-X01, T-X07) |
| `revision_time > cutoff` | That revision is invisible; the prior revision governs (T-X02) |
| `effective_time > cutoff` | Excluded silently, no error (T-P04) |
| All exclusions | Silent, deterministic, **never** an exception. A backtest over a date range MUST NOT fail because future data exists in the store |

---

## SECTION 5 — AVAILABILITY POLICY

### 5.1 Discriminated Union (F-16 resolution)

**Proven defect:** `AvailabilityPolicy` declares `policy: PublicationControlledAvailability | RevisionAwareAvailability` with `rule_type` as an **independent** field. A mismatched pair constructs successfully and computes under the wrong rule.

Empirically verified:

```
rule_type=REVISION_AWARE + policy=PublicationControlledAvailability
  -> constructs WITHOUT error
  -> is_available(pub=T-1d, None, rev=T+3d, T) = False
     (the future revision_time is silently IGNORED — argument-order aliasing)

rule_type=PUBLICATION_CONTROLLED + policy=RevisionAwareAvailability
  -> is_available(pub=T-1d, None, rev=T+3d, T) = True
     (publication_time argument consumed as revision_time)
```

This is **future-revision leakage** — the exact defect PIT exists to prevent.

### 5.2 Mandated Structure

```
AvailabilityPolicy
    ├── rule_type: "publication_controlled"  → requires PublicationControlledAvailability
    └── rule_type: "revision_aware"          → requires RevisionAwareAvailability
```

**Mandate:** implement as a true discriminated union (tagged variants keyed on `rule_type`), or enforce with a `model_validator(mode="after")` that raises when `rule_type` and `type(policy)` disagree.

### 5.3 Construction-Failure Requirement

**Any mismatched `rule_type`/`policy` combination MUST raise at construction.** All four mismatched pairings MUST be tested (§8.3).

### 5.4 Unknown-Field Rejection

Per §3.7: `extra="forbid"` on every policy model. An unknown policy key MUST raise. A policy that is *intended* to be strict MUST NOT silently degrade to permissive through a typo.

### 5.5 Declarative Constraint

Policies are immutable data. They MUST NOT contain callables, lambdas, or dynamically supplied functions. (Currently satisfied — verified no `eval`/`exec`/callable fields.)

---

## SECTION 6 — LEGACY DATA / DEFAULT PIT SIDECAR

### 6.1 The Problem (F-14)

`PHASE_4A_FINAL_ARCHITECTURE_SPEC.md:54` specifies the default sidecar for legacy Phase 3 datasets as:

```
event_time = observation_time = publication_time = effective_time = revision_time
             = dataset.provenance.retrieval_timestamp
ingestion_time = datetime.now(UTC)
```

This rule contains **three independent defects**:

| # | Defect | Consequence |
|---|---|---|
| D-1 | `ingestion_time = now(UTC)` at view-build time | A historical `view_hash` changes on every rebuild. Reproducibility destroyed |
| D-2 | `publication_time` fabricated from `retrieval_timestamp` | Manufactures availability evidence that never existed |
| D-3 | No `PitViewBuilder` exists to enforce any of it | Rule is unenforceable |

### 6.2 Absolute Prohibitions

| ID | Prohibition |
|---|---|
| PROH-LEG-01 | **NEVER** inject current wall-clock time into any historical identity |
| PROH-LEG-02 | **NEVER** fabricate publication evidence |
| PROH-LEG-03 | **NEVER** silently treat `retrieval_timestamp` as `publication_time` |
| PROH-LEG-04 | **NEVER** default an unknown publication time to the event time |
| PROH-LEG-05 | **NEVER** allow a legacy default sidecar to be indistinguishable from an explicit one |

### 6.3 Mandated Legacy Classification

A legacy dataset (no `publication_time` metadata) MUST be assigned exactly one of:

| Classification | Meaning | PIT eligibility |
|---|---|---|
| **`PIT_INELIGIBLE`** | Publication time is unknown and cannot be determined | **EXCLUDED from every PIT view.** Reason recorded |
| **`ASSUMED_PUBLICATION`** | Publication time is *declared* to be an assumption, with the assumption and its basis recorded explicitly | Eligible, **and** the view is labelled `ASSUMED` in its identity |

**Selection rule (deterministic):**

1. If explicit `publication_time` exists → use it. Classification `EXPLICIT`.
2. Else if a declared assumption exists in `PitExperimentConfig` → `ASSUMED_PUBLICATION`, assumption text becomes an **identity field**.
3. Else → `PIT_INELIGIBLE`. The item is excluded and the exclusion is recorded in the view.

### 6.4 Reproducibility Requirement

| ID | Requirement |
|---|---|
| PROH-LEG-06 | A default/legacy sidecar MUST be a pure function of the dataset version. Two builds at different wall-clock times MUST produce identical `view_hash` |
| PROH-LEG-07 | `ingestion_time` in a sidecar MUST be `None`, or fixed at dataset-version creation and stored — never computed as `now()` at view-build time |
| PROH-LEG-08 | The legacy classification MUST participate in `view_hash`, so an assumed view never hashes equal to an explicit one |
| PROH-LEG-09 | `PIT_INELIGIBLE` items MUST be excluded **silently** from the view and counted, not raised |

---

## SECTION 7 — PIT COMPONENT CONTRACTS

### 7.1 `PitSidecar`

| Aspect | Contract |
|---|---|
| **Purpose** | Immutable temporal-metadata snapshot for exactly one dataset version |
| **Inputs** | `dataset_id`, `dataset_version`, per-field temporal values or classification, `TemporalContract`, legacy classification |
| **Outputs** | Frozen model with `eligibility_hash`, `sidecar_hash` |
| **Invariants** | Frozen after construction; one sidecar per dataset version; never overwrites an existing sidecar; schema evolution produces a **new** sidecar for a new dataset version |
| **Identity fields** | `dataset_id`, `dataset_version`, `event_time`, `observation_time`, `publication_time`, `effective_time`, `revision_time`, `legacy_classification`, `contract_version`. **`ingestion_time` EXCLUDED** |
| **Serialization** | §3 canonical form; type-tagged |
| **Validation** | §4.3 ordering; §4.2 required-field policy; timezone awareness; PROH-LEG-01…05 |
| **Failure modes** | Naive datetime → raise; ordering violation → raise; PROH-LEG-03 pattern in an explicit sidecar → raise |
| **Dependencies** | `TemporalSemantics`, `TemporalContract`, identity contract (§2) |
| **Acceptance tests** | T-M01, T-M06, T-P01, T-P02, T-R01, **SUB-09** |

### 7.2 `RevisionChain`

| Aspect | Contract |
|---|---|
| **Purpose** | Append-only, ordered history of all revisions of one logical datum |
| **Inputs** | Ordered sequence of revision entries, each with `revision_time`, `publication_time`, payload, optional `supersedes` |
| **Outputs** | Frozen chain with `chain_hash`, `select_at(cutoff)` |
| **Invariants** | **Append-only** — existing entries are immutable; `revision_time` strictly increasing within a chain; every entry except the first declares `supersedes`; chain integrity is hash-verifiable |
| **Identity fields** | Ordered `(revision_time, publication_time, entry_hash)` sequence. Payload content participates |
| **Serialization** | §3 canonical form; list order significant |
| **Validation** | Strict monotonicity; no gaps in `supersedes`; chain hash recomputation MUST match |
| **Failure modes** | Non-monotonic `revision_time` → raise; broken `supersedes` link → raise; tampered entry → chain-hash mismatch → raise |
| **Dependencies** | `PitSidecar`, §4.6 composite cutoff |
| **Acceptance tests** | T-R01, T-R02, T-R03, T-P03, T-X02 |

### 7.3 `TieBreakerPolicy`

| Aspect | Contract |
|---|---|
| **Purpose** | Total, deterministic ordering for observations sharing an identical temporal key |
| **Inputs** | `name`, `version`, an ordered tuple of sort keys |
| **Outputs** | A comparator over observation tuples |
| **Invariants** | **Total order** — any two distinct observations compare deterministically; the key tuple MUST be sufficient to break every tie; ordering MUST NOT depend on input order, dict iteration order, wall clock, RNG, or memory address |
| **Identity fields** | `name`, `version`, ordered key tuple. Participates in `experiment_id` so that changing it changes identity |
| **Serialization** | §3 canonical form |
| **Validation** | Non-empty key tuple; no duplicate keys; no wall-clock key permitted |
| **Failure modes** | Empty key tuple → raise; wall-clock sort key → raise; tie that remains unbreakable → raise (never an arbitrary fallback) |
| **Dependencies** | Identity contract (§2) |
| **Acceptance tests** | T-O01, TIE-01…04 |

### 7.4 `PitView`

| Aspect | Contract |
|---|---|
| **Purpose** | Immutable, point-in-time-correct view of a dataset as it was knowable at a cutoff |
| **Inputs** | `dataset_id`, `dataset_version`, `cutoff`, `PitSidecar(s)`, `TieBreakerPolicy`, `TemporalContract`, `InstrumentIdentity` |
| **Outputs** | Frozen view exposing filtered candles, `view_hash`, `excluded_count`, classification |
| **Invariants** | Frozen; `view_hash` is a pure function of `(dataset content, cutoff, sidecar, tie-breaker, instrument identity, contract versions)`; identical inputs → identical hash in any process; **no excluded item influences any included item** |
| **Identity fields** | Ordered: dataset identity hash, `cutoff`, sidecar eligibility hashes, `tie_breaker.name` + `version`, `instrument_identity`, `instrument_specification`, `venue`, `data_source`, `calendar_ref`, contract versions, legacy classification |
| **Serialization** | §3 canonical form |
| **Validation** | Delegated to `PitViewValidator` |
| **Failure modes** | Construction on a `PIT_INELIGIBLE`-only dataset → empty view + recorded reason, not an exception |
| **Dependencies** | All of the above |
| **Acceptance tests** | T-H01, T-H02, T-P01…T-P04, T-X01, T-X02, T-X07 |

### 7.5 `PitViewBuilder`

| Aspect | Contract |
|---|---|
| **Purpose** | Construct a `PitView` from a dataset and a cutoff |
| **Inputs** | `Dataset`, `cutoff`, `PitSidecar` set, `TieBreakerPolicy`, `TemporalContract`, legacy policy |
| **Outputs** | `PitView` |
| **Invariants** | **Deterministic** — no caching that varies with time, order, or process; **no `datetime.now()` anywhere in the build path** (PROH-LEG-01); output depends only on declared inputs |
| **Identity fields** | None (it constructs, it does not identify) |
| **Serialization** | N/A |
| **Validation** | Applies §4.6 cutoff rules per item; records exclusions |
| **Failure modes** | `PIT_INELIGIBLE` item → excluded + counted; missing required sidecar field → excluded + counted, or raise per contract; **never** a silent substitution |
| **Dependencies** | `PitView`, `PitSidecar`, `RevisionChain`, `TieBreakerPolicy` |
| **Acceptance tests** | **SUB-09**, T-P01, T-P02, T-X07 |

### 7.6 `PitViewValidator`

| Aspect | Contract |
|---|---|
| **Purpose** | Independently verify a constructed `PitView` is correct |
| **Inputs** | `PitView`, source dataset, sidecars, cutoff |
| **Outputs** | Structured validation result with per-check pass/fail and reasons |
| **Invariants** | Runs **after** `DataQualityGate` (which answers "is this data valid?"; this answers "was it available at the cutoff?"). It MUST NOT duplicate `DataQualityGate` and MUST NOT weaken it |
| **Identity fields** | None |
| **Serialization** | Result is serializable for audit |
| **Validation** | Independent re-derivation: no future item present; `view_hash` recomputes; ordering invariant holds; exclusions are complete |
| **Failure modes** | Any failed check → view rejected with a specific reason; **fail closed** |
| **Dependencies** | `PitView`, `DataQualityGate` |
| **Acceptance tests** | VAL-01…04, T-X07 |

### 7.7 `InstrumentIdentity`

| Aspect | Contract |
|---|---|
| **Purpose** | Stable instrument identity across its whole lifecycle, independent of provider naming |
| **Inputs** | `stable_identifier`, `asset_class`, `contract_type` |
| **Outputs** | Frozen model with `instrument_identity_hash` |
| **Invariants** | Stable across provider symbol renames; stable across venue re-listing where the economic instrument is unchanged; **no free-form symbol is an identity field** |
| **Identity fields** | `stable_identifier`, `asset_class`, `contract_type`, `schema_version` |
| **Serialization** | §3 canonical form |
| **Validation** | Non-empty `stable_identifier`; known enums; no wall-clock |
| **Failure modes** | Empty identifier → raise; unknown asset class → raise |
| **Dependencies** | Identity contract (§2) |
| **Acceptance tests** | INST-01, INST-02 (rename stability), T-H01 |

### 7.8 `InstrumentSpecification`

| Aspect | Contract |
|---|---|
| **Purpose** | Effective-dated trading specification required to interpret prices historically |
| **Inputs** | `instrument_identity`, `effective_from`, `effective_to`, `tick_size`, `contract_size`, `currency`, `venue` |
| **Outputs** | Frozen model with `specification_hash` |
| **Invariants** | **Effective-dated** — a specification has a validity interval; intervals for one instrument MUST NOT overlap; `effective_from < effective_to` |
| **Identity fields** | `instrument_identity`, `effective_from`, `tick_size`, `contract_size`, `currency`, `venue`, `schema_version`. **`effective_to` is EXCLUDED** (it is a consequence of the successor's start, not an independent fact) |
| **Serialization** | §3 canonical form |
| **Validation** | Overlap detection; positive `tick_size`/`contract_size`; interval well-formed |
| **Failure modes** | Overlapping intervals → raise; non-positive sizes → raise; unbounded interval → raise |
| **Dependencies** | `InstrumentIdentity`, `Venue` |
| **Acceptance tests** | SPEC-01, SPEC-02 (no overlap), T-P04 |

### 7.9 `Venue`

| Aspect | Contract |
|---|---|
| **Purpose** | Immutable exchange/market identifier with its timezone |
| **Inputs** | `venue_id`, `venue_name`, `timezone`, optional `mic` |
| **Outputs** | Frozen model with `venue_hash` |
| **Invariants** | Immutable; `timezone` is an IANA identifier; venue history is modelled via `InstrumentSpecification`, not by mutating a `Venue` |
| **Identity fields** | `venue_id`, `timezone`, `schema_version` |
| **Serialization** | §3 canonical form |
| **Validation** | Valid IANA timezone; non-empty id |
| **Failure modes** | Invalid timezone → raise |
| **Dependencies** | Identity contract (§2) |
| **Acceptance tests** | VEN-01 |

### 7.10 `DataSource`

| Aspect | Contract |
|---|---|
| **Purpose** | Immutable provider identity, and the versioned mapping to provider-specific symbols |
| **Inputs** | `source_id`, `provider_name`, `source_version`, symbol mappings |
| **Outputs** | Frozen model with `source_hash` |
| **Invariants** | A symbol mapping is **versioned** — a provider renaming an instrument produces a new mapping version, never a silent overwrite; this prevents symbol-reuse bias |
| **Identity fields** | `source_id`, `source_version`, `provider_name`, `schema_version` |
| **Serialization** | §3 canonical form |
| **Validation** | Mapping versions monotonic; no silent overwrite |
| **Failure modes** | Duplicate mapping version → raise |
| **Dependencies** | Identity contract (§2) |
| **Acceptance tests** | SRC-01, SRC-02 (rename creates a version) |

### 7.11 `CalendarRef` (MINIMAL — 4A.1)

| Aspect | Contract |
|---|---|
| **Purpose** | Identity reference to a calendar version. **Reference only** |
| **Inputs** | `calendar_id`, `calendar_version` |
| **Outputs** | Frozen model with `calendar_ref_hash` |
| **Invariants** | **No calendar computation in 4A.1.** No holiday logic, no session determination, no trading-day arithmetic. Any 4A.1 component requiring those is a scope violation (INV-06) |
| **Identity fields** | `calendar_id`, `calendar_version`, `schema_version` |
| **Serialization** | §3 canonical form |
| **Validation** | Non-empty both fields |
| **Failure modes** | A component requesting calendar computation → **scope violation, rejected at review** |
| **Dependencies** | Identity contract (§2) |
| **Acceptance tests** | CAL-01, CAL-02 (no computation surface) |

### 7.12 `ExperimentIdentity`

| Aspect | Contract |
|---|---|
| **Purpose** | Deterministic identity for one complete PIT experiment |
| **Inputs** | `strategy_hash`, `dataset_hash`, `view_hash`, `config_hash`, tie-breaker name+version, code/quant/backtest engine versions |
| **Outputs** | `experiment_id` |
| **Invariants** | A pure function of its inputs. **MUST NOT** depend on `run_timestamp`, `approval_timestamp`, `ingestion_time`, random UUIDs, wall clock, filesystem path, or environment |
| **Identity fields** | The ordered tuple above, plus `contract_version` |
| **Serialization** | §3 canonical form; composition of the component hashes |
| **Validation** | All component hashes well-formed (64 hex); all versions non-empty |
| **Failure modes** | Missing/blank component → raise. Changing the tie-breaker MUST change the `experiment_id` |
| **Dependencies** | All identity sources; frozen Phase 3 hashes consumed **as opaque strings** |
| **Acceptance tests** | EXP-01, EXP-02 (tie-breaker sensitivity), EXP-03 (wall-clock independence) |

### 7.13 `PitExperimentConfig`

| Aspect | Contract |
|---|---|
| **Purpose** | Configuration for a PIT-aware experiment |
| **Inputs** | `cutoff`, `TemporalContract`, `TieBreakerPolicy`, legacy policy, calendar ref, instrument identity/specification, venue, data source |
| **Outputs** | Frozen configuration with `config_identity_hash` |
| **Invariants** | Frozen; every legacy assumption is **explicit and declared**; the config alone determines the view |
| **Identity fields** | Ordered: cutoff, contract version, tie-breaker name+version, legacy policy, calendar ref, instrument identity, instrument specification, venue, data source |
| **Serialization** | §3 canonical form |
| **Validation** | `extra="forbid"`; cutoff is UTC-aware; legacy assumption text required when `ASSUMED_PUBLICATION` |
| **Failure modes** | `ASSUMED_PUBLICATION` without assumption text → raise; unknown key → raise |
| **Dependencies** | `EvidenceProvenance` (**single definition**, R-03/F-02), `TieBreakerPolicy`, `CalendarRef` |
| **Acceptance tests** | CFG-01, CFG-02 |

---

## SECTION 8 — ACCEPTANCE TEST MATRIX

### 8.1 Authority

This matrix is the **sole acceptance authority** for Phase 4A.1. Every mandatory P0 identifier MUST appear as a named test. A requirement satisfied only by a concept-similar test does **not** count (F-21: currently **zero** P0 identifiers exist anywhere in `tests/`).

Target file: **`tests/test_pit_view.py`** — does not currently exist (specified in `PHASE_4A1_IMPLEMENTATION_SPEC.md` §20.2).

### 8.2 Mandatory P0 Matrix

| P0 ID | Requirement | Test | Contract § | Gate |
|---|---|---|---|---|
| T-H01 | Phase 4 identity stable; frozen `result_hash` unchanged | `test_t_h01_phase4_identity_stable` | §2 | MANDATORY |
| T-H02 | Identity changes with data; **unchanged when only wall-clock fields change** | `test_t_h02_identity_data_sensitivity` + `test_t_h02_identity_wallclock_invariance` | §2.4 | MANDATORY |
| T-H03 | `StrategySpec.to_hash()` unchanged | `test_t_h03_strategy_hash_unchanged` | §10 | MANDATORY |
| T-H04 | `_compute_config_hash()` unchanged before/after 4A.1 | `test_t_h04_config_hash_unchanged` | §10 | MANDATORY |
| T-H05 | **True subprocess determinism** | `test_t_h05_cross_process_determinism` | §2.6 | MANDATORY |
| T-P01 | `publication_time == cutoff` → **eligible** | `test_t_p01_publication_at_cutoff_eligible` | §4.6 | MANDATORY |
| T-P02 | `publication_time == cutoff + 1µs` → **excluded** | `test_t_p02_publication_after_cutoff_excluded` | §4.6 | MANDATORY |
| T-P03 | `revision_time > cutoff` → that revision invisible | `test_t_p03_revision_after_cutoff_invisible` | §4.6 | MANDATORY |
| T-P04 | `effective_time > cutoff` → excluded, no error | `test_t_p04_effective_after_cutoff_excluded` | §4.6 | MANDATORY |
| T-R01 | Single revision chain | `test_t_r01_single_revision` | §7.2 | MANDATORY |
| T-R02 | Multiple revisions; latest ≤ cutoff selected | `test_t_r02_multiple_revisions_selects_latest` | §7.2 | MANDATORY |
| T-R03 | Chain integrity hash; tamper-detectable | `test_t_r03_chain_integrity` + `test_t_r03_tamper_detected` | §7.2 | MANDATORY |
| T-R04 | Latest-value-only dataset rejected | `test_t_r04_latest_only_rejected` | §7.2 | MANDATORY |
| T-M01 | Missing `event_time` rejected | `test_t_m01_missing_event_time_rejected` | §4.2 | MANDATORY |
| T-M06 | Naive datetime rejected (all 6 fields) | `test_t_m06_naive_datetime_rejected_all_fields` | §4.4 | MANDATORY |
| T-O01 | Equal timestamps → deterministic total order, stable across runs | `test_t_o01_equal_time_deterministic_order` | §7.3 | MANDATORY |
| T-X01 | Future publication silently excluded | `test_t_x01_future_publication_excluded` | §4.7 | MANDATORY |
| T-X02 | Future revision explicitly excluded | `test_t_x02_future_revision_excluded` | §4.7 | MANDATORY |
| T-X07 | Future data silently excluded, **distinguishable from T-X01** | `test_t_x07_future_data_silent_exclusion` | §4.7 | MANDATORY |

### 8.3 Supplementary Mandatory Tests

| ID | Requirement | Test |
|---|---|---|
| **SUB-01** | **AvailabilityPolicy mismatch — all four pairings raise at construction** | `test_availability_mismatch_rejected` |
| SUB-02 | Correct pairings behave per §5 | `test_availability_correct_pairings` |
| SUB-03 | Unknown policy field raises (`extra="forbid"`) | `test_policy_extra_field_forbidden` |
| **SUB-04** | **Serializer collision matrix — every distinct-typed pair yields distinct bytes** | `test_serializer_no_type_collision` |
| SUB-05 | `datetime` vs its ISO string distinct | `test_serializer_datetime_vs_string` |
| SUB-06 | int-key vs str-key dict distinct (or rejected) | `test_serializer_dict_key_collision` |
| SUB-07 | Numeric policy `.10f`; `-0.0` → `0.0`; NaN/Inf rejected | `test_serializer_numeric_policy` |
| SUB-08 | List order significant | `test_serializer_list_order_significant` |
| SUB-09 | **Legacy sidecar reproducibility — two builds at different wall-clock times → identical `view_hash`** | `test_legacy_sidecar_reproducible` |
| SUB-10 | `PIT_INELIGIBLE` excluded + counted, no exception | `test_legacy_ineligible_excluded` |
| SUB-11 | `ASSUMED_PUBLICATION` labels the view; hash differs from explicit | `test_legacy_assumption_labelled` |
| **SUB-12** | **Filesystem containment — `endpoint` escape blocked** | `test_provider_endpoint_containment` |
| SUB-13 | Absolute-path instrument rejected | `test_provider_absolute_instrument_rejected` |
| SUB-14 | `../` traversal rejected | `test_provider_traversal_rejected` |
| SUB-15 | Symlink escape rejected (**skip if unsupported privilege — Windows `WinError 1314`**) | `test_provider_symlink_rejected` |
| SUB-16 | Instrument allowlist enforced | `test_provider_instrument_allowlist` |
| SUB-17 | Fail-closed: SYNTHETIC cannot reach a backtest | `test_synthetic_cannot_reach_backtest` |
| **SUB-18** | **Frozen Phase 3 SHA-256 manifest matches** | `test_frozen_phase3_manifest` |
| SUB-19 | Cross-field temporal ordering enforced (4 orderings + null skip + equality valid) | `test_temporal_ordering_enforced` |
| SUB-20 | `ALLOW_NULL` + `required_fields` → construction raises | `test_allow_null_with_required_rejected` |
| SUB-21 | Wall-clock field in an allowlist raises (ID-WC-02) | `test_wallclock_in_allowlist_rejected` |
| SUB-22 | `EvidenceProvenance` is a single definition (F-02/R-03) | `test_evidence_provenance_single_definition` |
| SUB-23 | Instrument identity stable across provider symbol rename | `test_instrument_identity_survives_rename` |
| SUB-24 | `ExperimentIdentity` wall-clock independent | `test_experiment_identity_no_wallclock` |
| **SUB-25** | T-H05 must fail if `Candle.to_hash()` enters any Phase 4 identity | `test_no_phase3_hash_in_phase4_identity` |

### 8.4 Replacement of Weak Tests (F-24)

| Weak test | Defect | Replacement |
|---|---|---|
| `test_hash_cross_process_determinism` | Calls `verify_hash_determinism()` which loops 3× **in one process**. `verify_cross_process_hash()` only asserts `len(h)==64`. Neither spawns a process | SUB-04/`test_t_h05_...`: spawn ≥5 subprocesses, compare digests |
| `test_no_phase3_source_modified` | Asserts only `os.path.exists(f)` for 11 files; **cannot detect any modification**; omits `strategy/` entirely | SUB-18: SHA-256 manifest comparison |
| `test_hash_no_timestamp` | Hashes the same literal twice; cannot detect timestamp injection into entity identity | SUB-21, SUB-24: entity-level wall-clock exclusion |
| `test_hash_no_uuid` | Asserts `"-" not in h`; SHA-256 hex never contains `-` regardless of input | SUB-24: assert identity invariant under changed `run_timestamp` |

**Rule:** every replacement test MUST fail when its target defect is reintroduced (mutation-verified at §14, Reproducibility Audit).

### 8.5 Component-Level Tests (DEFECT-B correction, 2026-10-01)

**Defect corrected.** §7 component contracts referenced component-level test identifiers that §8.2 and §8.3 never defined. A referenced-but-undefined test identifier is an unenforceable requirement — the same class of defect as F-21, recurring inside the corrective document.

**Namespace rule (DEFECT-B correction).** Test identifiers use four disjoint namespaces:

| Prefix | Namespace | Defined in |
|---|---|---|
| `T-*` | Mandatory P0 gates | §8.2 |
| `SUB-*` | Supplementary mandatory tests | §8.3 |
| Component prefixes (`TIE`, `VAL`, `INST`, `SPEC`, `VEN`, `SRC`, `CAL`, `EXP`, `CFG`) | Component contract tests | §8.5 (this section) |
| `PROH-*` | **Prohibitions / invariants — NOT tests** | §6.2, §6.4, and throughout |

**Renamed in this correction:** `LEG-01`…`LEG-09` (prohibitions) → **`PROH-LEG-01`**…**`PROH-LEG-09`**. The `LEG-*` namespace collided with test identifiers and was ambiguous. **`LEG-REP-01`** (referenced in §7.1, §7.5 but never defined) → **`SUB-09`**, which is defined in §8.3.

#### 8.5.1 `TieBreakerPolicy` — §7.3

| ID | Requirement | Test |
|---|---|---|
| **TIE-01** | Equal timestamps order deterministically; repeated runs produce identical order | `test_tie_equal_time_deterministic` |
| **TIE-02** | Reversing input order does **not** change the resulting order (order-independence) | `test_tie_input_order_independent` |
| **TIE-03** | Empty key tuple raises at construction | `test_tie_empty_keys_rejected` |
| **TIE-04** | A wall-clock sort key raises at construction (PROH-LEG-01) | `test_tie_wallclock_key_rejected` |
| **TIE-05** | An unbreakable tie raises — never an arbitrary fallback | `test_tie_unbreakable_raises` |
| **TIE-06** | Changing `name` or `version` changes `experiment_id` | `test_tie_identity_participates` |

#### 8.5.2 `PitViewValidator` — §7.6

| ID | Requirement | Test |
|---|---|---|
| **VAL-01** | Independent re-derivation confirms no future item is present in the view | `test_validator_no_future_items` |
| **VAL-02** | `view_hash` recomputes and matches | `test_validator_hash_recomputes` |
| **VAL-03** | Any failed check rejects the view with a specific reason (**fail closed**) | `test_validator_fails_closed` |
| **VAL-04** | `DataQualityGate` rejection remains blocking; the validator neither duplicates nor weakens it | `test_validator_preserves_quality_gate` |

#### 8.5.3 `InstrumentIdentity` — §7.7

| ID | Requirement | Test |
|---|---|---|
| **INST-01** | Empty `stable_identifier` raises | `test_instrument_identity_empty_id_rejected` |
| **INST-02** | Identity is stable across a provider symbol rename | `test_instrument_identity_survives_rename` |
| **INST-03** | A free-form symbol is not an identity field; changing it alone does not change the hash | `test_instrument_identity_symbol_not_identity` |
| **INST-04** | Identity contains no wall-clock field | `test_instrument_identity_no_wallclock` |

#### 8.5.4 `InstrumentSpecification` — §7.8

| ID | Requirement | Test |
|---|---|---|
| **SPEC-01** | Overlapping validity intervals for one instrument raise | `test_spec_overlap_rejected` |
| **SPEC-02** | `effective_from < effective_to` enforced; non-positive tick/contract size raises | `test_spec_interval_and_sizes` |
| **SPEC-03** | `effective_to` is excluded from identity (successor's start is authoritative) | `test_spec_effective_to_excluded_from_identity` |

#### 8.5.5 `Venue` — §7.9

| ID | Requirement | Test |
|---|---|---|
| **VEN-01** | Invalid IANA timezone raises | `test_venue_invalid_timezone_rejected` |
| **VEN-02** | `Venue` is immutable and hash-stable | `test_venue_immutable_stable` |

#### 8.5.6 `DataSource` — §7.10

| ID | Requirement | Test |
|---|---|---|
| **SRC-01** | A provider symbol rename creates a **new mapping version**; it never silently overwrites | `test_source_rename_creates_version` |
| **SRC-02** | Duplicate mapping version raises | `test_source_duplicate_version_rejected` |
| **SRC-03** | Mapping versions are monotonic | `test_source_version_monotonic` |

#### 8.5.7 `CalendarRef` — §7.11 (minimal)

| ID | Requirement | Test |
|---|---|---|
| **CAL-01** | Empty `calendar_id` or `calendar_version` raises | `test_calendar_ref_empty_fields_rejected` |
| **CAL-02** | **No calendar computation surface exists** — no holiday logic, no session determination, no trading-day arithmetic (INV-06 scope guard) | `test_calendar_ref_no_computation_surface` |

#### 8.5.8 `ExperimentIdentity` — §7.12

| ID | Requirement | Test |
|---|---|---|
| **EXP-01** | `experiment_id` is a pure function of its declared inputs | `test_experiment_id_pure_function` |
| **EXP-02** | Changing the tie-breaker changes `experiment_id` | `test_experiment_id_tiebreak_sensitive` |
| **EXP-03** | `experiment_id` is unchanged under `run_timestamp`, wall clock, PID, path, and environment changes | `test_experiment_id_wallclock_independent` |
| **EXP-04** | A missing or blank component raises | `test_experiment_id_missing_component_raises` |
| **EXP-05** | No frozen Phase 3 hash method is invoked during identity computation | `test_experiment_id_no_phase3_hash_call` |

#### 8.5.9 `PitExperimentConfig` — §7.13

| ID | Requirement | Test |
|---|---|---|
| **CFG-01** | `ASSUMED_PUBLICATION` without assumption text raises | `test_config_assumption_text_required` |
| **CFG-02** | Unknown key raises (`extra="forbid"`) | `test_config_extra_field_forbidden` |
| **CFG-03** | Non-UTC-aware cutoff raises | `test_config_naive_cutoff_rejected` |
| **CFG-04** | The config alone determines the view | `test_config_determines_view` |

#### 8.5.10 Legacy semantics — §6

| ID | Requirement | Test |
|---|---|---|
| **LEG-T01** | A legacy default sidecar contains **no** wall-clock value; two builds at different times produce identical output | `test_legacy_sidecar_no_wallclock` (pairs with SUB-09) |
| **LEG-T02** | `retrieval_timestamp` is never used as `publication_time` (PROH-LEG-03) | `test_legacy_no_retrieval_as_publication` |
| **LEG-T03** | An assumed view never hashes equal to an explicit view (PROH-LEG-08) | `test_legacy_assumed_differs_from_explicit` |

#### 8.5.11 Component Test Count

| Namespace | Count | Section |
|---|---|---|
| Mandatory P0 (`T-*`) | 19 | §8.2 |
| Supplementary (`SUB-*`) | 25 | §8.3 |
| Component-level (`TIE` 6, `VAL` 4, `INST` 4, `SPEC` 3, `VEN` 2, `SRC` 3, `CAL` 2, `EXP` 5, `CFG` 4) | 33 | §8.5.1–8.5.9 |
| Legacy-semantics (`LEG-T*`) | 3 | §8.5.10 |
| **Subtotal — pre-re-audit specification** | **80** | — |
| Post-re-audit collision/conformance (`COL-*`, added 2026-10-01) | 15 | §8.6 |
| **TOTAL SPECIFIED** | **95** | — |

**Count provenance.** The subtotal **80** was measured from this document by the
Stage 1 correction pass. The **15** `COL-*` tests were added by the post-re-audit
correction pass (RA-NF-01…04) and counted from §8.6. Both figures are
measurements, not constants, per **REG-06**. The previous total of **80** was
accurate *before* §8.6 existed; it is now superseded by **95**.

**All 95 must exist as named tests in `tests/test_pit_view.py` before Blocker 6 can close.** None currently exists.

**Count discipline (REG-06).** These counts are **measured from this document**, not asserted. Any future edit that adds or removes a test MUST update this table, and the reconciliation command in §8.5.12 MUST return zero differences.

#### 8.5.12 Test-Definition Reconciliation Command

Run at every stage exit and at every re-audit. It MUST return zero differences between identifiers *referenced* in §7 and identifiers *defined* in §8.

```bash
# Referenced in §7 but never defined in §8  → MUST be empty
comm -23 \
  <(sed -n '/## SECTION 7/,/## SECTION 8/p' PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md \
     | grep -oE '\b(TIE|VAL|INST|SPEC|VEN|SRC|CAL|EXP|CFG)-[0-9]+' | sort -u) \
  <(sed -n '/## SECTION 8/,/## SECTION 9/p' PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md \
     | grep -oE '\b(TIE|VAL|INST|SPEC|VEN|SRC|CAL|EXP|CFG)-[0-9]+' | sort -u)
```

**Expected output:** empty. **This is the DEFECT-B regression guard.**

#### 8.5.13 DEFECT-B Corrected Enumeration — 23 Undefined Test Identifiers

The Architecture Correction report initially stated **18**. That figure was incorrect. The measured total is **23**.

**Method.** Every identifier appearing in a §7 acceptance-test cell was enumerated against the identifiers defined in §8.2 and §8.3 as they stood before this correction.

| Category | Count | Identifiers |
|---|---|---|
| Explicitly named in §7, never defined in §8 | 14 | `CAL-01` `CAL-02` `CFG-01` `CFG-02` `EXP-01` `EXP-02` `INST-01` `INST-02` `LEG-REP-01` `SPEC-01` `SPEC-02` `SRC-01` `SRC-02` `VEN-01` |
| Implied by range notation (`TIE-01…04`, `VAL-01…04`), never defined | 8 | `TIE-01` `TIE-02` `TIE-03` `TIE-04` `VAL-01` `VAL-02` `VAL-03` `VAL-04` |
| **TOTAL UNDEFINED** | **23** | |

**Reconciliation of the erroneous "18":**

| Error | Direction | Detail |
|---|---|---|
| `LEG-01`, `LEG-03` counted as test IDs | overstated by 2 | They are **prohibition IDs** (§6.2), not tests. The grep pattern `\b(...\|LEG)-[0-9]+` cannot distinguish the two namespaces |
| Range-implied members not enumerated | understated by 8 | A token grep sees `TIE-01` and `VAL-01` but not `TIE-02/03/04`, `VAL-02/03/04` |
| `LEG-REP-01` not matched at all | omitted by 1 | The pattern requires `LEG-` followed by digits; `LEG-REP-01` has `REP` in between and is invisible to it |
| **Net** | **18 → 23** | 14 + 8 + 1 = 23 |

**Method rule (REG-07).** Any enumeration of test identifiers MUST expand range notation and MUST distinguish test namespaces from prohibition namespaces. A single token grep is insufficient and has now demonstrably produced a wrong count once. The §8.5.12 command is the standing guard against regression of the *definitions*; this section is the record of the *enumeration*.

### 8.6 Post-Re-Audit Mandatory Tests (RA-NF-01 … RA-NF-04) — added 2026-10-01

Specified by the post-re-audit documentation correction pass. **None is
implemented.** These tests exist to close the gaps the independent re-audit
measured, and are additionally required by Blocker 4 (§13.3).

| ID | Severity | Requirement | Test | Spec |
|---|---|---|---|---|
| **COL-KEY-01** | **MANDATORY** | `canonical_serialize({1: "a"})` **RAISES** `SerializationError` — a non-string mapping key is rejected, never coerced | `test_serializer_nonstring_key_rejected` | SER-KEY-01 |
| **COL-KEY-02** | **MANDATORY** | `{"1": "a"}` serializes successfully and produces bytes **distinct from** any int-keyed form | `test_serializer_int_key_never_coerced` | SER-KEY-02 |
| **COL-KEY-03** | MANDATORY | Non-string keys rejected recursively at every nesting depth | `test_serializer_nonstring_key_nested` | SER-KEY-05 |
| **COL-KEY-04** | MANDATORY | `bool`, `Decimal`, and `date` keys are all rejected — no implicit key conversion of any kind | `test_serializer_no_implicit_key_conversion` | SER-KEY-02 |
| **COL-KEY-05** | MANDATORY | Mapping keys are encoded as `{"s": …}` so a key can never be confused with a bare scalar value | `test_serializer_key_type_tagged` | SER-KEY-03 |
| **COL-DT-01** | MANDATORY | `datetime` and its ISO-8601 string produce **distinct** canonical bytes | `test_serializer_datetime_vs_string_distinct` | §3.1 |
| **COL-DT-02** | MANDATORY | `date` and `datetime` produce **distinct** canonical bytes | `test_serializer_date_vs_datetime_distinct` | §3.1a.2 |
| **COL-DATE-01** | MANDATORY | A `date` serializes successfully to its defined ISO-8601 representation — it MUST NOT raise | `test_serializer_date_supported` | §3.1a.2 |
| **COL-DATE-02** | MANDATORY | A `date` is never implicitly widened to a `datetime` | `test_serializer_date_not_widened` | §3.1a.2 |
| **COL-DATE-03** | MANDATORY | The `date` tag letter is **distinct from the `dict` tag letter** (RA-NF-04) | `test_serializer_date_tag_distinct_from_dict` | RA-NF-04 |
| **COL-NUM-01** | MANDATORY | `float` is emitted in `.10f` form — `100.5` → `100.5000000000`, never `100.5` | `test_serializer_float_ten_places` | §3.1a.3 |
| **COL-NUM-02** | MANDATORY | `Decimal` is emitted as an exact tagged string — never float-converted, never rounded | `test_serializer_decimal_exact_tagged` | §3.1a.3 |
| **COL-NUM-03** | MANDATORY | `Decimal('1.0')` and `1.0` differ **by tag and by value form** — the distinction is explicit, not incidental | `test_serializer_decimal_float_tagged_distinct` | §3.1a.3 |
| **COL-NUM-04** | MANDATORY | `int` and `bool` are tagged `{"i":…}` / `{"b":…}`; `True` never equals `1` | `test_serializer_int_bool_tagged` | §3.1a.3 |
| **COL-PROC-01** | **MANDATORY** | **True subprocess** identity determinism: ≥5 separate OS processes each compute an identity and all digests match (T-H05) | `test_identity_determinism_true_subprocess` | §8.3, §14 Stage 10 |

**Mutation-verification requirement.** Per §8.4's rule, every test above MUST fail
when its target defect is reintroduced. In particular **COL-KEY-01 MUST fail** if
integer-key coercion is restored — a test asserting only that the two outputs
*differ* is **insufficient**, because coercion to the same string also makes them
"not equal" only by accident of the input; the mandated behaviour is rejection.

**Namespace.** `COL-*` is a fifth test namespace, disjoint from `T-*`, `SUB-*`, the
component prefixes, and `PROH-*` (§8.5).

---

## SECTION 9 — REGRESSION BASELINE

### 9.1 Declaration

| Metric | Value | Verified |
|---|---|---|
| **AUTHORIZED BASELINE** | **367** | `--ignore=tests/test_pit.py` → 367 passed |
| **CURRENT TOTAL** | **464** | Full suite → 464 passed in 1.71s |
| **UNAUTHORIZED PIT DELTA** | **97** | All delta tests live in untracked `tests/test_pit.py` |

Per-file counts (live): `test_data_engine.py` 62 · `test_pit.py` 97 · `test_quant.py` 134 · `test_redteam.py` 50 · `test_strategy.py` 82 · `test_strategy_independent.py` 39.

**No document may cite "464" as the frozen baseline.** Citing 464 without the 97-delta disclosure is a reporting defect.

### 9.2 Re-establishment Procedure

The baseline is re-established, in order, at the start of the architecture-correction stage:

1. Resolve the authorization status of **every untracked artifact**. The count is **measured**, never assumed: run `git ls-files --others --exclude-standard | wc -l` and break it down by category. Each artifact is either **authorized** (approval record + commit) or **removed**. UNKNOWN = BLOCKER.

   *Measured at Architecture Correction stage entry (2026-10-01):* **28** untracked — 21 `.md`, 6 `src/data_engine/pit/*.py`, 1 `tests/test_pit.py`. This count grows as stage artifacts are produced and is therefore a measurement, not a constant (REG-06).
2. Record a SHA-256 manifest of every authorized `src/` and `tests/` file.
3. Run the suite. Record exact collected/passed/failed/skipped counts.
4. Declare the authorized baseline as the count of tests in **committed** files only.
5. Record the unauthorized delta separately, with its file list.
6. Any test file whose authorization is unresolved MUST be excluded from the baseline and MUST NOT be reported as passing coverage.
7. The manifest and both counts are recorded in the re-audit report and re-verified after every subsequent stage.

### 9.3 Rules

| ID | Rule |
|---|---|
| REG-01 | The authorized baseline is a function of **committed** files only |
| REG-02 | Untracked tests are never counted as baseline coverage |
| REG-03 | The 97-test delta MUST be labelled unauthorized until authorized |
| REG-04 | Test weakening (assertion removal/loosening) is prohibited; any such change invalidates the baseline |
| REG-05 | Baseline is re-verified **live** in every session; prior counts are never trusted |
| REG-06 | Every count declared in this specification (untracked artifacts, test identifiers, component counts) is **measured by command at the time of statement**, and the measuring command is recorded alongside it. No count is carried forward as a fixed constant |
| REG-07 | Any enumeration of identifiers MUST expand range notation (`A-01…04`) and MUST separate test namespaces from prohibition namespaces. A single token grep is **not** an acceptable enumeration method — it has produced a wrong count (§8.5.13) |

---

## SECTION 10 — FROZEN PHASE 3 PROTECTION

### 10.1 Frozen Methods

The following remain **byte-for-byte frozen**:

| Method | Location | Mechanism |
|---|---|---|
| `Candle.to_hash()` | `src/data_engine/schemas.py:130` | `sha256(model_dump_json())` |
| `ProvenanceRecord.to_hash()` | `src/data_engine/schemas.py:200` | `sha256(model_dump_json())` |
| `StrategySpec.to_hash()` | `src/data_engine/strategy/schemas.py:458` | `sha256(canonical_serialize())` |
| `BacktestProvenance.compute_result_hash()` | `src/data_engine/strategy/provenance.py:84` | Explicit pipe formula |
| `BacktestProvenance.to_hash()` | `src/data_engine/strategy/provenance.py:108` | `model_dump(exclude_unset=True)` + pops |
| `BacktestConfig._compute_config_hash()` | `src/data_engine/strategy/backtest.py:629` | Explicit pipe string |
| `BacktestEngine._compute_dataset_hash()` | `src/data_engine/strategy/backtest.py:608` | Explicit pipe string |

### 10.2 SHA-256 Manifest (recorded 2026-10-01, verified unmodified)

```
1c5ed4a7369a9a9e7f11ad0a10b914369d6550df912bc913828982c5c72d39b6  src/data_engine/schemas.py
4a27cc9aa20464e8255f7853828956378b57669188bf3908b575597586d3be6c  src/data_engine/strategy/schemas.py
dda729bf6591046daae29961c727f0f59d1b03642273735b57c382da5923c8f2  src/data_engine/strategy/provenance.py
3b5aacab4640229c9e997f053868fc0a8b9b789078e4d69a933a3ac623f59613  src/data_engine/strategy/backtest.py
853aba15aeba441c966bc3b14feca40bbcdbee887ba730be73d5a56789fe10e7  src/data_engine/strategy/execution.py
312ed94a91b92c7145547b5c5b13c3e2e8a349f2aadfae7fb72efd6e32cecd2a  src/data_engine/strategy/ledger.py
9ecd12e51a5f1cf046af0b3dc9434f58d409e7eef2e5779c6226cbedf315e844  src/data_engine/strategy/equity.py
d1ef8b83090827228c9866036d953f9b89491fcdafd045aaf650e0e7d39c94ae  src/data_engine/strategy/position.py
868a3a56a826eaca328c6b1030be8831387d80368e932608265d4b37e4b2f667  src/data_engine/strategy/conditions.py
6e30932c179554f27e7980f0b0c6956fd419669cacf79f4d2c8d879b78470e6d  src/data_engine/strategy/metrics.py
9a589f26b4f89a10775a919bfe5ddc8c5a4754a0f10c44ef46fbf85576bfdc59  src/data_engine/strategy/validation.py
47aed9c6d932801b584f6bd3ddcafd36015d926deb43d0b725fc8e0f04bcee17  src/data_engine/strategy/__init__.py
8efd870ed0149b0cc96d66d82643cb5f3efdb9176b8183896e1696c347802c84  docs/strategy_engine_design.md
```

**Manifest requirement:** SUB-18 MUST recompute and compare this exact manifest. Any mismatch **fails the gate immediately** and invalidates every downstream result.

**Note on `docs/strategy_engine_design.md`:** the recorded hash is of the **working-tree** state, which contains the unauthorized line-2238 change (`COMPLETE` → `NO-GO`). The committed-state hash must be recorded separately when that change is authorized and committed (see §12.3).

### 10.3 Phase 3 Compatibility Evidence (F-32 — verified positive)

```
dataset_hash UNCHANGED when every candle.provider_timestamp -> 2030:  True
dataset_hash REAL vs SYNTHETIC distinct:                              True
```

`_compute_dataset_hash()` enumerates fields explicitly and never calls `Candle.to_hash()`. `compute_result_hash()` excludes `run_timestamp`. **The frozen Phase 3 hash chain is sound and immune to the F-04/F-05 PIT contamination.** This is a pass, not a defect.

### 10.4 Protection Rules

| ID | Rule |
|---|---|
| FRZ-01 | No frozen method may be edited, wrapped, subclassed for identity, or reflected on |
| FRZ-02 | Phase 4 consumes frozen hashes as **opaque strings** only |
| FRZ-03 | `to_deterministic_hash()` MUST NOT be added to any frozen class (§2.8) |
| FRZ-04 | Any manifest mismatch fails all gates; no partial credit |
| FRZ-05 | Frozen-contract regression is checked before and after every stage |

---

## SECTION 11 — FILESYSTEM SECURITY

**SPECIFICATION ONLY. No control is implemented by this document.** These are the required properties for the future authorized implementation stage.

### 11.1 Canonical Path Resolution

| ID | Requirement |
|---|---|
| FS-01 | Every path MUST be resolved to a canonical absolute form (`Path.resolve()`, resolving `..`, `.`, and symlinks) **before** any containment decision |
| FS-02 | Containment MUST be evaluated on the **resolved** path, never on the input string |
| FS-03 | Comparison MUST be performed on resolved path components, not string prefixes (avoids the `C:\dataevil` vs `C:\data` prefix bug) |

### 11.2 Approved-Root Containment

| ID | Requirement |
|---|---|
| FS-04 | `ProviderConfig` MUST declare an explicit **approved data root** |
| FS-05 | Every resolved path MUST be verified to be **inside** the approved root |
| FS-06 | If no approved root is configured → **fail closed**, no I/O |

### 11.3 Absolute-Path and Traversal Rejection

| ID | Requirement |
|---|---|
| FS-07 | Absolute paths in `endpoint` MUST be rejected unless inside the approved root |
| FS-08 | Any resolved path containing `..` that escapes the root MUST be rejected |
| FS-09 | Rejection MUST occur **before** `os.path.exists()` and before any read |
| FS-10 | `os.path.join()` alone is **NOT** a security control and MUST NOT be treated as one |

### 11.4 Symlink and Reparse-Point Handling

| ID | Requirement |
|---|---|
| FS-11 | Symlinks and Windows reparse points MUST be detected |
| FS-12 | If a path **or any parent** is a symlink/reparse point → reject, **or** resolve and re-verify containment |
| FS-13 | The resolved target MUST satisfy §11.2 containment |

*Verified defect: `os.path.exists()` and `pd.read_csv()` both follow symlinks; there is no `islink()` check. Symlink testing is blocked on this host (`WinError 1314`, no `SeCreateSymbolicLinkPrivilege`) — **structurally absent in code, empirically UNVERIFIED** (F-29).*

### 11.5 Instrument Allowlisting

| ID | Requirement |
|---|---|
| FS-14 | `instrument` MUST be validated against `InstrumentRegistry`/`InstrumentIdentity` **before** path construction |
| FS-15 | Path separators, `..`, drive letters, and UNC prefixes in `instrument` MUST be rejected |
| FS-16 | The filename MUST be constructed from a validated identifier, never from raw user input |

*Corrected mechanism note: the prior audit claimed absolute-path injection via `instrument` succeeds because `os.path.join`'s second argument wins. **This did not reproduce** — the `_4h.csv` suffix is appended to the filename component, so the concatenation remains relative. The escape is real, but via `config.endpoint` (§11.7), not via `instrument`. FS-14…16 remain required as defence in depth.*

### 11.6 Config Strictness

| ID | Requirement |
|---|---|
| FS-17 | `ProviderConfig` MUST declare `extra="forbid"` |
| FS-18 | `endpoint` MUST be validated at construction, not at first use |
| FS-19 | Provider-config validation MUST fail closed |

### 11.7 Verified Attack Results (2026-10-01)

| Test | Result |
|---|---|
| T1 `endpoint` pointing outside the data directory | **ESCAPE SUCCEEDED — 1 candle read** |
| T2 absolute path as `instrument` | blocked (incidentally, by the filename suffix — not by a control) |
| T3 relative `../` traversal via `instrument` | blocked (incidentally) |
| T5 `check_connectivity("C:/Windows")` | **True** — arbitrary directory enumeration |

### 11.8 Fail-Closed and Security Audit Logging

| ID | Requirement |
|---|---|
| FS-20 | Every rejection MUST raise a specific, typed error naming the rule violated |
| FS-21 | Every allow and every deny MUST be logged to a **structured security audit trail** with actor, path, decision, rule, timestamp |
| FS-22 | The audit trail MUST be **append-only and tamper-evident** |
| FS-23 | `DataQualityGate` rejection MUST block by default at **every** consumer (H-14) |
| FS-24 | SYNTHETIC data MUST NOT reach `BacktestEngine` by any call path |

*Current state: `security.py:60-70` writes operational output to `src/audit.log` (90 bytes) — **not** a security audit trail (no actor, no tamper resistance, no fail-closed binding). H-14 and H-16 remain FAIL (F-30).*

---

## SECTION 12 — DOCUMENT GOVERNANCE

### 12.1 Superseded Documents (retained, non-binding)

| Document | Version / Date | Status | Reason |
|---|---|---|---|
| `PHASE_4A1_IMPLEMENTATION_SPEC.md` | 1.0.0 / 2026-09-29 | **PARTIALLY SUPERSEDED** | §2.1's "13 primitives" count and lines 834–836/857's deferral of Venue/DataSource/CalendarRef are superseded by §1.2/§1.3. Its §20 acceptance-test intent is adopted into §8 |
| `PHASE_4A1_IMPLEMENTATION_FORENSIC_AUDIT.md` | 1.0.0 / 2026-09-29 | **SUPERSEDED on ownership** | Lines 1185–1189 defer InstrumentIdentity, InstrumentSpecification, Venue, CalendarRef to 4A.2, contradicting §1.2 (F-03) |
| `PHASE_4A1_FINAL_ARCHITECTURE_GATE.md` | 1.0.0 / 2026-09-28 | **SUPERSEDED** | Its §8.1/§8.4/§365 "no tracked files modified" claims are **false** (F-31); its Gate 3 pass rationale is invalidated by §10.2's manifest requirement |
| `PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md` | 1.0.0 / 2026-09-28 | **REFERENCE ONLY** | Cited as authority for component lists; its "PROPOSED" status remains accurate |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_SPEC.md` | 1.0.0 / 2026-09-28 | **REFERENCE ONLY** | Its §9.1 CalendarRef boundary is adopted into §7.11 |
| `PHASE_4A1_FORENSIC_RECONCILIATION.md` | 1.0.0 / 2026-09-29 | **REFERENCE ONLY** | Its ownership column conflicts with §1.2; the ownership matrix is adopted |
| `PHASE_4A1_SPEC_RECONCILIATION.md` | 1.0.0 / 2026-09-29 | **REFERENCE ONLY** | Historical reconciliation record |
| `PHASE_4A_FINAL_ARCHITECTURE_SPEC.md` | 1.0.0 / 2026-09-28 | **PARTIALLY SUPERSEDED** | Line 54's default-sidecar rule is superseded by §6 (F-14) |
| `DESIGN_REVIEW_PHASE_4A_MULTI_ASSET_PIT.md` | 2026-09-28 | **REFERENCE ONLY** | Source of UQ-01/05/09/12 requirements |
| `DESIGN_GATE_REPORT.md` | 2026-09-28 | **REFERENCE ONLY** | Historical design review |
| `MASTER_PHASE_STATUS_REPORT.md` | 2026-09-30 | **PARTIALLY SUPERSEDED** | Blocker IDs B-01…B-14 and contradiction IDs C-1…C-6 are adopted into §13; its per-file defect claims are superseded by this document's evidence |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_CHECKLIST.md` | 1.0.0 / 2026-10-01 | **REFERENCE ONLY — corrections superseded** | **Added 2026-10-01 (DL-D3′).** Retains the erroneous "18 undefined test identifiers" figure at its §3.2 heading and §4 diff-plan row; the correct figure is **23** (§8.5.13). Its DEFECT-A/B/C *discovery* records remain valid historical evidence of what the Stage 1 self-audit found. Its status block is superseded by §14.0 |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_REPORT.md` | 2026-10-01 | **REFERENCE ONLY — status superseded** | **Added 2026-10-01 (DL-D3′).** Its Stage 1 report remains valid for that stage. Its statement that the Architecture Correction stage produced a specification ready for Design Lock is superseded: the subsequent Design Lock returned `FAILED` and the re-audit returned `RE-AUDIT_FAIL` (§14.0) |
| `PHASE_4A1_DESIGN_LOCK_RECORD.md` | 1.0.0 / 2026-10-01 | **ATTEMPTED — FAILED** | Its `DESIGN_LOCK = FAILED` verdict stands. Its §11 characterization of the RA-NF-01 case as "no collision at this layer" is **superseded** by §3.1a.1: the collision survives to canonical bytes and is HIGH/BLOCKER |
| `PHASE_4A1_INDEPENDENT_REAUDIT_REPORT.md` | 1.0.0 / 2026-10-01 | **AUTHORITATIVE for re-audit findings** | Source of **RA-NF-01…RA-NF-03 only** (corrected 2026-10-01, DL-D5 — it is **not** the source of RA-NF-04). Its `RE-AUDIT_FAIL` verdict stands. Its measurement of DL-D1 (CRLF = 2238) is the governing measurement recorded in §12.3 |
| `PHASE_4A1_POST_REAUDIT_CORRECTION_REPORT.md` | 1.0.0 / 2026-10-01 | **AUTHORITATIVE for the Stage 3.5 correction pass** | **Provenance source for RA-NF-04** (added 2026-10-01, DL-D5), which was discovered in that documentation pass by document review of §3.1, not by the independent re-audit. The re-audit report raised three findings only. This report is documentation-only and closes no blocker |

### 12.2 Incorrect Historical Claims (corrected here, originals retained)

| Document | Claim | Correction |
|---|---|---|
| `FILESYSTEM_SECURITY_FORENSIC_AUDIT.md` | Absolute-path injection via `instrument` succeeds (`os.path.join` second-arg wins) | **Did not reproduce** (T2/T3). Escape is via `config.endpoint` (T1). FAIL verdict stands; mechanism is wrong |
| `HASH_FORENSIC_AUDIT.md:152` | `_compute_dataset_hash()` is "NOT content-based (only dataset_id, count, version)" | **FALSE.** Verified content-based: mutating the last close changes the hash; 30→31 candles changes the hash. It iterates every candle (`backtest.py:612-619`) |
| `PHASE_4A1_FINAL_ARCHITECTURE_GATE.md` §8.1/§8.4/§365 | "No tracked files modified"; design doc "still says COMPLETE" | **FALSE.** `docs/strategy_engine_design.md` and `pyproject.toml` are modified; the doc now says `NO-GO` |

**These originals are retained unmodified.** Corrections are recorded here only.

### 12.3 Design-Document Authorization Contradiction (F-31)

| Item | Value |
|---|---|
| Diff | `-IMPLEMENTATION STATUS: COMPLETE — DESIGN LOCK PENDING FINAL REVIEW` / `+IMPLEMENTATION STATUS: NO-GO — DESIGN LOCK PENDING FINAL REVIEW` |
| Current final line | `IMPLEMENTATION STATUS: NO-GO — DESIGN LOCK PENDING FINAL REVIEW` |
| Line endings — **MEASURED STATE (see DL-D1)** | **CRLF-BASED.** Measured 2026-10-01 by byte-level count: CRLF = 2238, lone CR = 0, LF = 2238, file terminates `...FINAL REVIEW\r\n`. The frozen design document is **NOT** LF-only. Its own verification checklist requires LF-only endings, so this is a **known non-conformance**, not a satisfied check |
| Content correctness | **CORRECT.** `NO-GO` is the required locked state per the design's own checklist item 13 |
| Missing | **Authorization record.** The change is correct but unapproved |

**Mandate:** **DO NOT REVERT** — reverting would restore the incorrect `COMPLETE`. Record an explicit human authorization decision for this one-line change, commit it, and re-record the manifest hash (§10.2 note). This is a prerequisite for blocker 7 closure.

#### 12.3.1 CRLF NORMALIZATION DECISION — PENDING HUMAN AUTHORIZATION

**Decision: PENDING HUMAN AUTHORIZATION.** No agent may make this change.

| Item | Value |
|---|---|
| Measured current state | `docs/strategy_engine_design.md` is **CRLF-based** (CRLF = 2238, lone CR = 0) |
| Design-document own requirement | LF only (its verification checklist item 12) |
| Conformance | **NON-CONFORMANT — known and recorded** |
| Normalization status | **NOT PERFORMED** |
| Authorization required | **Explicit human authorization** (§15.1 P-3) |
| Manifest consequence | Normalization **changes the file's SHA-256**, invalidating the §10.2 manifest entry `8efd870e…802c84`, and therefore requires a **new manifest event** in addition to the authorization |
| Current frozen-file state | **UNCHANGED — byte-for-byte preserved** |

**Rationale.** `docs/strategy_engine_design.md` is a frozen Phase 3 contract (INV-01, §10.1). Normalizing its line endings would (a) modify a frozen file, and (b) invalidate a recorded manifest hash, which per **FRZ-04** fails all gates with no partial credit. Both consequences require a human decision. Silently normalizing it — to make a checklist item read as satisfied — would trade a recorded, honest non-conformance for an unrecorded, unauthorized mutation of a frozen contract. **The non-conformance is therefore recorded rather than erased.**

**Consequence for the gates.** Because the frozen file cannot be normalized without authorization, the §10.2 manifest hash of `8efd870e…802c84` remains the governing entry and the file remains frozen as-is. Any future normalization must be performed as an authorized, separately recorded event that re-issues the §10.2 entry. This non-conformance is carried as a **known open documentation defect** (DL-D1, RESOLVED-BY-RECORDATION, not resolved-by-fix) and is listed in §13.4.

### 12.4 Governance Rules

| ID | Rule |
|---|---|
| GOV-01 | This document supersedes every conflicting document in §12.1 |
| GOV-02 | Superseded documents are **retained**, never deleted or rewritten |
| GOV-03 | Corrections to historical audits are recorded in §12.2, never applied to the original |
| GOV-04 | A superseded document MUST NOT be cited as authority without noting its supersession |
| GOV-05 | Any new specification MUST declare which document it supersedes |
| GOV-06 | Authority is resolved by this document's §0.1 hierarchy, never by document date alone |
| GOV-07 | Supersession applies to **claims**, not to files. A retained document may still be cited for facts it alone records; it may not be cited for ownership or scope |

### 12.5 Ownership Reconciliation — EXECUTED EVIDENCE (Blocker 1)

This section records the **executed result** of the repository-wide reconciliation required by §13 Blocker 1. It was measured, not asserted.

**Command:** `grep -rl "<component>" --include="*.md" .` followed by extraction of phase tokens adjacent to the component name.

**Measured 2026-10-01:**

| Component | Phase assignments found | Verdict |
|---|---|---|
| `InstrumentIdentity` | `4A.1`, `4A.2` | **CONTRADICTION** |
| `InstrumentSpecification` | `4A.1`, `4A.2` | **CONTRADICTION** |
| `Venue` | `4A.1`, `4A.2` | **CONTRADICTION** |
| `DataSource` | `4A.1`, `4A.2` | **CONTRADICTION** |
| `CalendarRef` | `4A.1`, `4A.2` | **CONTRADICTION** |
| `PitSidecar` | `4A.1` | consistent |
| `RevisionChain` | `4A.1` | consistent |
| `TieBreakerPolicy` | `4A.1` | consistent |
| `PitView` | `4A.1` | consistent |
| `PitViewBuilder` | `4A.1` | consistent |
| `PitViewValidator` | `4A.1` | consistent |
| `ExperimentIdentity` | `4A.1` | consistent |
| `PitExperimentConfig` | `4A.1` | consistent |

**Result: 5 of 13 components carry contradictory ownership assignments.**

**Contradiction sources (retained unmodified per GOV-02):**

| Source | Claim |
|---|---|| `PHASE_4A1_IMPLEMENTATION_FORENSIC_AUDIT.md` lines 1185-1189 | Defer `InstrumentIdentity`, `InstrumentSpecification`, `Venue`, `CalendarRef` to 4A.2 |
| `PHASE_4A1_IMPLEMENTATION_SPEC.md` lines 834-836 | "Venue / DataSource / Calendar — Not used in 4A.1 (deferred)" |
| `PHASE_4A1_IMPLEMENTATION_SPEC.md` line 857 | "For 4A.1, CalendarRef is NOT implemented… Deferred to 4A.2" |

**Resolution:** §1.2 R-01 assigns all five to **4A.1**. The contradicting claims are SUPERSEDED but retained.

**Important limitation — Blocker 1 remains OPEN.** This evidence establishes that the contradiction is *identified and resolved in the specification*. It does **not** establish blocker closure, because:

| Outstanding requirement | State |
|---|---|
| SUB-22 (`EvidenceProvenance` single definition) | **NOT IMPLEMENTED** |
| `EvidenceProvenance` still defined twice in code (`schemas.py:47`, `evidence.py:18`) | **UNRESOLVED in production code** |
| Independent re-audit | **PERFORMED 2026-10-01 — returned RE-AUDIT_FAIL; blocker confirmed OPEN** |

The R-03 re-export is a production-code change, which is outside this stage's permitted boundary (§0.2). **Blocker 1 stays OPEN.**

---

## SECTION 13 — BLOCKER CLOSURE CRITERIA

**Closure rule (INV-07):** a blocker is **OPEN** until its stated condition **and** required evidence are both satisfied **and independently re-audited**. **No blocker closes through documentation alone.**

### Blocker 1 — Phase ownership contradictions

| Aspect | Requirement |
|---|---|
| **Close only when** | One authoritative owner exists for every 4A.1 component (§1.2); `EvidenceProvenance` has exactly one definition; contradictory documents are superseded/corrected |
| **Required artifact** | This specification §1.2 ownership table; §12.1 supersession list; R-03 re-export change |
| **Required tests** | SUB-22 |
| **Required evidence** | Repository-wide reconciliation: `grep` yields exactly one phase assignment per component across all 4A.1 documents |
| **Responsible** | 4A.1 — architecture correction |
| **Re-audit** | **PERFORMED 2026-10-01 — CONFIRMS OPEN.** Spec coherent; code contradicts spec (`schemas.EvidenceProvenance is evidence.EvidenceProvenance` → False) |

### Blocker 2 — Identity-contract specification gaps

| Aspect | Requirement |
|---|---|
| **Close only when** | Versioned Phase 4 Identity Contract defines explicit allowlists, audit-only fields, canonical form, type/null/TZ/numeric rules, and excludes wall-clock fields |
| **Required artifact** | §2 contract; §3 serialization contract |
| **Required tests** | T-H01, T-H02, SUB-21, SUB-24, SUB-25, T-H03, T-H04 |
| **Required evidence** | Approved contract + identity test suite green + §10.2 manifest protecting frozen Phase 3 |
| **Responsible** | 4A.1 — identity contract |
| **Re-audit** | **PERFORMED 2026-10-01 — CONFIRMS OPEN.** `identity_hash()` free function ABSENT; no `extra="forbid"` anywhere in `src/data_engine/pit/` |

### Blocker 3 — Temporal-contract gaps

| Aspect | Requirement |
|---|---|
| **Close only when** | Cross-field ordering, required-field semantics, legacy-data rules, and cutoff boundary are explicitly defined and tested |
| **Required artifact** | §4 temporal contract; §6 legacy policy |
| **Required tests** | T-P01, T-P02, T-P04, T-M01, T-M06, SUB-19, SUB-20, SUB-09, SUB-10, SUB-11 |
| **Required evidence** | Temporal contract document + legacy reproducibility proof |
| **Responsible** | 4A.1 — temporal semantics |
| **Re-audit** | **PERFORMED 2026-10-01 — CONFIRMS OPEN.** Ordering constraint ABSENT (`event_time > observation_time` constructs silently); `ALLOW_NULL` weakens `required_fields`; cutoff boundary behaviour correctly measured |

### Blocker 4 — Canonical serialization alignment

| Aspect | Requirement |
|---|---|
| **Close only when** | No type collisions/ambiguity remain; numeric policy is explicit; unknown fields rejected; serialization deterministic |
| **Required artifact** | §3 contract (type-tagged encoding; `.10f` numeric policy) + **§3.1a conformance (SER-KEY-01…05; `date`; Decimal/float)** |
| **Required tests** | SUB-04, SUB-05, SUB-06, SUB-07, SUB-08, T-H05 + **COL-KEY-01…05, COL-DT-01/02, COL-DATE-01…03, COL-NUM-01…04, COL-PROC-01** |
| **Required evidence** | Collision matrix with all pairs distinct; numeric-policy decision recorded |
| **Responsible** | 4A.1 — serialization |
| **Re-audit** | **PERFORMED 2026-10-01 — CONFIRMS OPEN and ESCALATES.** datetime/string collision CONFIRMED at byte level; **RA-NF-01 int-key/str-key collision CONFIRMED at byte level — HIGH/BLOCKER**; `.10f` absent; `date` unsupported; true subprocess determinism absent |

### Blocker 5 — PIT component specification gaps

| Aspect | Requirement |
|---|---|
| **Close only when** | All 13 §7 contract components have complete contracts (inputs, outputs, invariants, failure modes, identity semantics); availability pairing is type-safe |
| **Required artifact** | §7.1–7.13 |
| **Required tests** | SUB-01, SUB-02, SUB-03, T-R01–T-R04, T-O01, TIE-01…04, INST-01/02, SPEC-01/02, VEN-01, SRC-01/02, CAL-01/02, EXP-01…03, CFG-01/02 |
| **Required evidence** | Component specifications + mismatch tests + PIT acceptance tests green |
| **Responsible** | 4A.1 — PIT components |
| **Re-audit** | **PERFORMED 2026-10-01 — CONFIRMS OPEN.** 13 of 13 components MISSING from `src/`; BOTH mismatched AvailabilityPolicy pairings construct silently and leak; unknown policy key silently dropped |

### Blocker 6 — P0/T-PIT acceptance gaps

| Aspect | Requirement |
|---|---|
| **Close only when** | Every mandatory P0/T-PIT requirement maps to an actual test, including true subprocess determinism and future-data exclusion |
| **Required artifact** | §8 matrix (**95 tests**); `tests/test_pit_view.py` |
| **Required tests** | All 19 P0 IDs + SUB-01…SUB-25 + 33 component + 3 legacy + 15 COL |
| **Required evidence** | Complete requirement→test matrix; `grep -c` on P0 identifiers = 19+; all mandatory tests green; **zero** P0 requirements satisfied only by concept-similar tests |
| **Responsible** | 4A.1 — acceptance tests |
| **Re-audit** | **PERFORMED 2026-10-01 — CONFIRMS OPEN.** `tests/test_pit_view.py` absent; 0 of 95 identifiers present; 4 Category-D weak tests still in place and un-replaced |

### Blocker 7 — Regression-baseline ambiguity

| Aspect | Requirement |
|---|---|
| **Close only when** | 367 formally declared the authorized baseline, the 97 unauthorized delta separately identified, weak tests replaced, design-doc change authorized |
| **Required artifact** | §9 baseline record; §12.3 authorization decision; §12.3.1 CRLF decision; §10.2 manifest |
| **Required tests** | SUB-18; §8.4 replacements (all four) |
| **Required evidence** | Baseline record + clean-suite run + frozen-contract SHA manifest + design-doc authorization artifact |
| **Responsible** | 4A.1 + repository governance |
| **Re-audit** | **PERFORMED 2026-10-01 — CONFIRMS OPEN.** 367/464/97 independently reproduced; all four weak tests still present; design-doc authorization record still absent |

### Blocker 8 — Filesystem-security concern

| Aspect | Requirement |
|---|---|
| **Close only when** | File access enforces approved-root containment, traversal/absolute-path rejection, symlink handling, strict config, and fail-closed behaviour |
| **Required artifact** | §11 security contract |
| **Required tests** | SUB-12…SUB-17, SUB-24 (audit-log verification) |
| **Required evidence** | Security tests green + containment evidence + audit-log verification (append-only, tamper-evident) |
| **Responsible** | 4A.1 (contract) → implementation stage (controls) |
| **Re-audit** | **PERFORMED 2026-10-01 — CONFIRMS OPEN.** Endpoint escape REPRODUCED (1 candle read); `check_connectivity("C:/Windows")` → True; zero containment controls present; audit trail is a 90-byte test artifact |

### 13.1 Current Blocker State

| # | Blocker | State |
|---|---|---|
| 1 | Phase ownership contradictions | **OPEN** |
| 2 | Identity-contract specification gaps | **OPEN** |
| 3 | Temporal-contract gaps | **OPEN** |
| 4 | Canonical serialization alignment | **OPEN** |
| 5 | PIT component specification gaps | **OPEN** |
| 6 | P0/T-PIT acceptance gaps | **OPEN** |
| 7 | Regression-baseline ambiguity | **OPEN** |
| 8 | Filesystem-security concern | **OPEN** |

**8 of 8 OPEN.**

### 13.2 Authorization Rule

**Implementation remains `NOT_AUTHORIZED` while any mandatory blocker is open.**

### 13.3 Compact Blocker-Closure Table (updated 2026-10-01, post-re-audit correction)

| # | BLOCKER | CLOSE CONDITION | REQUIRED EVIDENCE | REQUIRED TESTS | RE-AUDIT | STATUS |
|---|---------|-----------------|-------------------|----------------|----------|--------|
| 1 | **Phase ownership contradictions** | One authoritative owner per component (§1.2); `EvidenceProvenance` has one definition; contradictions superseded | §12.5 executed reconciliation; §12.1 SUPERSEDED record per GOV-02 | SUB-22 | **DONE — CONFIRMS OPEN** | **OPEN** |
| 2 | **Identity-contract specification gaps** | Versioned contract with explicit allowlists, audit-only fields, canonical form, type/null/TZ/numeric rules, wall-clock excluded | §2 + §3 ratified; `pit4.` versioning; identity free function specified; frozen manifest recorded (§10.2) | T-H01, T-H02, T-H03, T-H04, SUB-21, SUB-24, SUB-25 | **DONE — CONFIRMS OPEN** | **OPEN** |
| 3 | **Temporal-contract gaps** | Cross-field ordering, required-field semantics, legacy rules, cutoff boundary defined and tested | §4 + §6 ratified; inclusive cutoff normative; PROH-LEG-01…09 defined | T-P01, T-P02, T-P04, T-M01, T-M06, SUB-09, SUB-10, SUB-11, SUB-19, SUB-20 | **DONE — CONFIRMS OPEN** | **OPEN** |
| 4 | **Canonical serialization alignment** | No type collisions; numeric policy explicit; unknown fields rejected; deterministic | §3 ratified; **§3.1a added — SER-KEY-01…05, `date` and Decimal/float representations; RA-NF-01 = HIGH/BLOCKER** | SUB-04…SUB-08, T-H05 + **15 `COL-*` tests (§8.6)** | **DONE — CONFIRMS OPEN, ESCALATED** | **OPEN** |
| 5 | **PIT component specification gaps** | All 13 §7 components fully specified; availability pairing type-safe | §7.1–7.13 complete; §5 discriminated-union mandate | SUB-01, SUB-02, SUB-03 + 33 component tests (§8.5) | **DONE — CONFIRMS OPEN** | **OPEN** |
| 6 | **P0/T-PIT acceptance gaps** | Every mandatory requirement maps to an actual test, incl. true subprocess determinism and future-data exclusion | §8 matrix complete (**95 tests**); `tests/test_pit_view.py` | 19 P0 + 25 SUB + 33 component + 3 legacy + 15 COL = **95** | **DONE — CONFIRMS OPEN** | **OPEN** |
| 7 | **Regression-baseline ambiguity** | 367 declared authorized; 97 delta identified; weak tests replaced; design-doc change authorized | §9 ratified (367/464/97); manifest recorded; REG-06 measurement rule | SUB-18 + 4 §8.4 replacements | **DONE — CONFIRMS OPEN** | **OPEN** |
| 8 | **Filesystem-security concern** | Approved-root containment, traversal/absolute rejection, symlink handling, strict config, fail-closed | §11 ratified; FS-01…FS-24; measured attack results §11.7 | SUB-12…SUB-17, SUB-24 | **DONE — CONFIRMS OPEN** | **OPEN** |

**Why every blocker remains OPEN after the re-audit.** The independent re-audit was
performed on 2026-10-01 and returned **RE-AUDIT_FAIL**. For every blocker it
confirmed the specification layer is coherent while the **implementation layer is
absent** — 13 of 13 required components missing, 0 of 95 specified tests existing,
zero filesystem controls implemented, `EvidenceProvenance` still dual-defined.
Per INV-07, **no blocker closes on documentation alone**, and this correction pass
produced documentation only. **0 of 8 blockers closed.**

### 13.4 Four-Layer Closure Model (updated 2026-10-01)

| Layer | Meaning | State |
|---|---|---|
| 1. Specification / contract definition | The closure criterion and required contract are written down | **DEFINED — 8 of 8** (blocker 4 extended with §3.1a) |
| 2. Implementation evidence | The contract exists as working code | **ABSENT — 0 of 8** |
| 3. Closure evidence | Tests demonstrate the contract holds | **ABSENT — 0 of 8** |
| 4. Independent re-audit | A separate reviewer verifies closure | **PERFORMED 2026-10-01 — 0 of 8 confirmed closed (RE-AUDIT_FAIL)** |
| — | **Blockers closed** | **0 of 8** |

**Complete blocker-closure evidence: 0/8.**

### 13.5 Remaining Documentation Defects (post-correction status)

| ID | Defect | Status after this pass |
|---|---|---|
| DL-D1 | False CRLF verification claim | **CORRECTED-BY-RECORDATION.** Accurate measurement recorded (§12.3). Underlying non-conformance **remains open**, pending human authorization (§12.3.1) |
| DL-D2 | Stale Stage-1 status in §14 | **CORRECTED** (§14.0) |
| DL-D3 | Hard-coded artifact count in an active requirement | **CORRECTED** (§14.1, REG-06 restored) |
| DL-D4 | 19-vs-13 component-count contradiction | **CORRECTED** (§1.2 reconciliation stated) |
| DL-D3′ | Checklist/report absent from §12.1 supersession list | **CORRECTED** (§12.1) |
| RA-NF-01 | int-key/str-key canonical-byte collision | **SPECIFIED ONLY — not resolved.** HIGH/BLOCKER. Requires implementation + `COL-KEY-*` tests |
| RA-NF-02 | bare `date` rejected despite §3.1 mandate | **SPECIFIED ONLY — not resolved.** Requires implementation + `COL-DATE-*` tests |
| RA-NF-03 | Decimal/float rely on incidental formatting | **SPECIFIED ONLY — not resolved.** Requires implementation + `COL-NUM-*` tests |
| RA-NF-04 | `date` and `dict` share tag letter `D` | **SPECIFIED ONLY — not resolved.** Distinct letter required before implementation |

**None of the four RA-NF findings is closed.** Each requires implementation-stage
work and an independent re-audit, which this documentation pass may not perform.

---

## SECTION 14 — IMPLEMENTATION SEQUENCE

### 14.0 Stage History — AS OF 2026-10-01 (measured, see DL-D2)

This section previously stated "Stage 1 has not begun" and labelled Stage 1 as the
"NEXT AUTHORIZED STAGE" while §15.2 recorded Stage 1 corrections as applied. That
was a self-contradiction (DL-D2). The corrected stage history:

| Stage | Name | State | Evidence |
|---|---|---|---|
| 1 | Architecture Correction | **COMPLETED** | 5 corrections applied; §15.2 provenance |
| 2 | Design Lock | **ATTEMPTED — FAILED** | `PHASE_4A1_DESIGN_LOCK_RECORD.md` v1.0.0: `DESIGN_LOCK = FAILED` on DL-D1…DL-D4 |
| 3 | Independent Read-Only Re-Audit | **COMPLETED — FAILED** | `PHASE_4A1_INDEPENDENT_REAUDIT_REPORT.md` v1.0.0: `RE-AUDIT_FAIL`; RA-NF-01…03 registered; all 8 blockers confirmed OPEN |
| 3.5 | Post-Re-Audit Documentation Correction | **COMPLETED (this pass)** | This correction pass — documentation only |
| 2′ | **Design Lock re-attempt** | **NEXT AUTHORIZED STAGE** | Preconditions in §14.0.1 |

**Current stage:** Design Lock re-attempt is next (Stage 2′), **not** implementation.
Per §14 Stage 2's own rule — "Any subsequent change re-opens Stage 1" — the
corrections in this pass re-open Stage 1 in a documentation-only sense. No
production code, no test, and no frozen contract was touched.

#### 14.0.1 Design Lock Re-attempt Preconditions

| # | Precondition | State |
|---|---|---|
| P-DL-1 | DL-D1 — false CRLF verification claim | **SATISFIED** — accurate measurement recorded (§12.3); frozen file unchanged; normalization pending human authorization (§12.3.1) |
| P-DL-2 | DL-D2 — stale stage status | **SATISFIED** (§14.0) |
| P-DL-3 | DL-D3 — hard-coded artifact count | **SATISFIED** (§14.1, REG-06 restored) |
| P-DL-4 | DL-D4 — component-count contradiction | **SATISFIED** (§1.2) |
| P-DL-5 | DL-D3′ — supersession-list gap | **SATISFIED** (§12.1) |
| P-DL-6 | RA-NF-01/02/03/04 registered with mandatory tests | **SATISFIED** (§0.2.2, §3.1a, §8.6) |
| P-DL-7 | No new false verification claims introduced | Verified at stage exit |

**Satisfying these preconditions does NOT authorize implementation.** It makes the
specification eligible for a Design Lock re-attempt only. All 8 blockers remain OPEN.

### 14.1 Stage 1 — Architecture Correction (COMPLETED 2026-10-01)

Recorded for historical fidelity. The **27** in item 1.1 below is a **dated
historical measurement** taken at the original stage entry on 2026-09-29; it is
**not** an active requirement. Per **REG-06** the live count is measured at every
stage entry and is never carried forward as a constant.

| # | Action | Depends on | Closes | State |
|---|---|---|---|---|
| 1.1 | Resolve authorization for untracked artifacts — *historical measurement: 27 at 2026-09-29 entry; live count measured per REG-06* | — | Blocker 7 (partial) | **OPEN** — measured 32 at 2026-10-01 correction-pass entry, still unresolved |
| 1.2 | Record design-doc authorization decision (F-31); commit; re-record manifest | 1.1 | Blocker 7 | **OPEN** |
| 1.3 | Re-export `EvidenceProvenance` (R-03) | 1.1 | Blocker 1 | **OPEN** |
| 1.4 | Ratify §1.2 ownership table; apply §12.1 supersessions | 1.3 | Blocker 1 | **OPEN** |
| 1.5 | Ratify §2 identity contract | 1.4 | Blocker 2 | **OPEN** |
| 1.6 | Ratify §3 serialization contract (type-tagged; `.10f`; §3.1a conformance) | 1.5 | Blocker 4 | **OPEN** — RA-NF-01…04 now also required |
| 1.7 | Ratify §4 temporal contract (ordering, required semantics, cutoff) | 1.5 | Blocker 3 | **OPEN** |
| 1.8 | Ratify §5 discriminated availability contract | 1.7 | Blocker 5 | **OPEN** |
| 1.9 | Ratify §6 legacy sidecar policy | 1.7 | Blocker 3 | **OPEN** |
| 1.10 | Ratify §7 component contracts (13 §7 contract sections + 6 foundation = 19 owned components, §1.2) | 1.8, 1.9 | Blocker 5 | **OPEN** |
| 1.11 | Ratify §11 filesystem security contract | — | Blocker 8 | **OPEN** |
| 1.12 | Ratify §8 acceptance matrix (95 tests, §8.5.11) | 1.10 | Blocker 6 | **OPEN** |
| 1.13 | Declare §9 baseline (367 / 464 / 97) | 1.1 | Blocker 7 | **OPEN** — spec ratified, evidence still absent |

### Stage 2 — Design Lock

Ratified contracts are frozen into a versioned design document. SHA-256 recorded. Any subsequent change re-opens Stage 1.

**Attempted 2026-10-01 — FAILED** on DL-D1…DL-D4. Re-attempt pending §14.0.1.

### Stage 3 — Authorization Review

Independent review of the locked design against the §8 matrix and §13 closure criteria. **This review — not this document — is what may grant implementation authorization.**

**NOT REACHED.** Requires a successful Design Lock first.

### Stage 4 — Implementation

Only after Stage 3 grants authorization. Order: serializer → identity contract → temporal semantics → availability → sidecar/revision chain → tie-breaker → asset primitives → PitView layer → experiment identity → security controls. Phase 3 remains frozen throughout (§10).

**NOT AUTHORIZED. NOT STARTED.**

### Stage 5 — Unit Tests

Per-component unit tests; §8 SUB matrix implemented.

### Stage 6 — Acceptance Tests

All 19 P0 + SUB-01…SUB-25 + 33 component + 3 legacy + 15 COL green (95 total).

### Stage 7 — Full Regression

§10.2 manifest re-verified **first** (FRZ-04). Then full suite. Baseline re-declared per §9.

### Stage 8 — Security Audit

Filesystem containment, fail-closed behaviour, audit-trail integrity; SUB-12…SUB-17, SUB-24.

### Stage 9 — Red-Team Audit

Adversarial cases: forged timestamps, mutated sidecars, symlink/reparse escapes, unknown-field injection, type-collision forgery (including RA-NF-01 int-key/str-key), equal-time ambiguity, latest-value-only injection.

### Stage 10 — Reproducibility Audit

Cross-process and cross-platform identity stability (T-H05 / COL-PROC-01 with real subprocesses); legacy-sidecar reproducibility (SUB-09); two-build hash equality.

### Stage 11 — Final Acceptance

Independent verification of all §13 closure criteria. Any blocker still open → **NOT_READY**.

### Stage 12 — Freeze

Manifest recorded; contracts locked; branch created.

---

## SECTION 15 — FINAL OUTPUT

### 15.1 Implementation Prerequisites

Implementation MUST NOT begin until **all** of the following hold:

| # | Prerequisite | State 2026-10-01 |
|---|---|---|
| P-1 | All 8 mandatory blockers **CLOSED** per §13, each independently re-audited | **FAIL** — 8 OPEN, 0 closed |
| P-2 | Stages 1–3 complete: Architecture Correction → Design Lock → Authorization Review | **FAIL** — Stage 1 corrected; Stage 2 FAILED; Stage 3 not reached |
| P-3 | Authorization Review has **explicitly granted** implementation authorization | **FAIL** — not granted, no mechanism invoked |
| P-4 | §10.2 frozen-contract manifest verified unchanged at the moment of implementation | **PASS** — 13/13 verified |
| P-5 | §9 baseline re-established and declared | **PASS** — 367/464/97 verified |
| P-6 | `tests/test_pit_view.py` exists with all mandatory P0 tests | **FAIL** — absent |
| P-7 | No UNKNOWN-authorization artifact remains in the working tree | **FAIL** — 7 untracked `.py` + 2 unauthorized tracked modifications |
| P-8 | Design-document authorization decision recorded | **FAIL** — absent; requires a human decision |

**2 of 8 prerequisites met. 6 unmet.**

### 15.2 Final Status

```
ARCHITECTURE STATUS:      CORRECTED — SPECIFICATION LEVEL (post-re-audit pass applied)
DESIGN_LOCK:              FAILED  (attempt 1 of 2026-10-01; re-attempt pending)
RE-AUDIT:                 RE-AUDIT_FAIL  (independent read-only re-audit, 2026-10-01)
IMPLEMENTATION READINESS: NOT_READY
IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
BLOCKERS:                 8 OPEN
BLOCKERS CLOSED:          0 of 8
COMPONENTS IMPLEMENTED:   0 of 13 required PIT components
TESTS EXISTING:           0 of 95 specified

CLOSURE CRITERIA + REQUIRED SPECS DEFINED:  8 of 8
IMPLEMENTATION EVIDENCE:                     0 of 8
CLOSURE EVIDENCE:                            0 of 8
INDEPENDENT RE-AUDIT:                        PERFORMED — 0 of 8 confirmed closed
COMPLETE BLOCKER-CLOSURE EVIDENCE:           0 of 8

REGRESSION BASELINE:      367 authorized / 464 current / 97 unauthorized delta
FROZEN PHASE 3 CONTRACTS: UNMODIFIED — 13-file manifest verified
PRODUCTION CODE CHANGED:  NONE
TESTS ADDED:              NONE
DOCUMENTATION DEFECTS:    DL-D1..D4 CORRECTED; RA-NF-01..04 REGISTERED, NOT RESOLVED
```

**Correction-stage provenance (2026-10-01, Architecture Correction — Stage 1).** Five corrections applied during Stage 1 (§14), all documentation-only:

| Correction | Defect | Applied |
|---|---|---|
| A | §13 asserted reconciliation evidence without recording the executed result | §12.5 added with measured reconciliation (5 contradictions found) |
| B | §7 referenced **23** undefined test identifiers; `LEG-*` namespace collision | §8.5 added (33 component + 3 legacy tests); `LEG-*` → `PROH-LEG-*`; `LEG-REP-01` → `SUB-09` |
| C | §9.2 hard-coded a stale untracked-artifact count | Replaced with a measurement rule + REG-06 |
| D | Compact closure table absent | §13.3–13.4 added |
| E | Status block predated the correction stage | Updated with correction provenance |

**Post-re-audit correction provenance (2026-10-01, Stage 3.5).** Eight corrections applied, all documentation-only:

| Correction | Defect | Applied |
|---|---|---|
| F | DL-D1 — false `CRLF count = 0 ✓` claim | §12.3 replaced with measured CRLF state; §12.3.1 CRLF decision recorded; frozen file unchanged |
| G | DL-D2 — stale "Stage 1 has not begun" | §14.0 stage history rewritten with measured per-stage states |
| H | DL-D3 — hard-coded "27 untracked artifacts" in an active requirement | Demoted to a dated historical measurement; REG-06 restored |
| I | DL-D4 — 19-vs-13 component-count contradiction | §1.2 reconciliation stated explicitly |
| J | DL-D3′ — checklist/report in no supersession list | §12.1 entries added with explicit scope |
| K | RA-NF-01/02/03 unrecorded | §0.2.2 registered; §3.1a conformance rules added |
| L | No acceptance tests for the new findings | §8.6 added — 15 `COL-*` mandatory tests; total 80 → **95** |
| M | RA-NF-04 — `date`/`dict` tag letter ambiguity observed | §3.1 observation recorded; distinct letter mandated |

**All eight blockers remain OPEN.** RA-NF-01 through RA-NF-04 are registered and
specified but **unresolved** — each requires implementation-stage work and a
subsequent independent re-audit, neither of which this documentation pass may perform.

### 15.3 Final Statement

**No implementation authorization has been granted. The next action is a Design
Lock re-attempt against the corrected specification (§14.0.1).**

---

*END DOCUMENT — PHASE 4A.1 AUTHORITATIVE REMEDIATION SPECIFICATION v1*

*This document is specification only. It implements no code, modifies no production file, alters no frozen Phase 3 contract, and grants no authorization.*
