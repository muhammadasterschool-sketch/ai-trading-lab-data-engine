# PHASE 4A.1 — INDEPENDENT READ-ONLY RE-AUDIT REPORT

**Document Version:** 1.0.0
**Date:** 2026-10-01
**Branch:** `phase-4a/4a1-temporal-foundation`
**Repository HEAD:** `13fdc7ee55a022a9be36ad910e524dcfa429954c`
**Audit type:** INDEPENDENT READ-ONLY RE-AUDIT (Stage 3, per authoritative spec §14)
**Mode:** READ-ONLY — no implementation, no source modification, no test modification

**AUTHORITATIVE BASELINE**
- `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` v1.1.0
- `PHASE_4A1_DESIGN_LOCK_RECORD.md` v1.0.0

---

## 1. AUDIT INDEPENDENCE

This audit was conducted **read-only against repository evidence**. No conclusion
below is inherited from a prior document's assertion.

| Independence control | Result |
|---|---|
| Production source modified | **NONE** |
| Tests created or modified | **NONE** |
| Frozen Phase 3 contracts modified | **NONE** |
| Implementation created | **NONE** |
| Temporary forensic probes | Created outside the repository (`hermes/cache/scratch`), **all deleted immediately** after each probe; repository working tree verified clean of probe residue |
| Persistent files created | **NONE** |
| Prior audit conclusions accepted without re-measurement | **NONE** — the manifest, the 367/464/97 baseline, the §8.5.12 reconciliation, and every behavioral probe were re-executed from source |

**Two prior claims were tested and one was found overstated by this audit:**

1. The Design Lock Record §11 states that the `{1:"a"}` vs `{"1":"a"}` case showed
   *"no collision at this layer"*. **This audit measured the actual serialized
   bytes and found a true collision** (`b'{"1":"a"}'` for both inputs). The prior
   characterization was too lenient; recorded here as **RA-NF-01**.
2. The Design Lock Record §11 lists `float 100.5` behaviour implicitly under the
   `.10f` finding; this audit measured it explicitly and additionally found that
   bare `date` objects are rejected although §3.1 mandates a `{"D": …}` encoding
   (**RA-NF-02**).

Neither correction alters any governance conclusion. Both are recorded as
findings; neither was repaired.

---

## 2. REPOSITORY STATE

```
HEAD                    : 13fdc7ee55a022a9be36ad910e524dcfa429954c
Branch                  : phase-4a/4a1-temporal-foundation
Branches                : master, phase-4a/4a1-temporal-foundation (checked out)
git status --porcelain  : 27 entries
Tracked modifications   : 2  (docs/strategy_engine_design.md, pyproject.toml)
Untracked artifacts     : 30 (23 .md, 6 src/data_engine/pit/*.py, 1 tests/test_pit.py)
pyproject.toml diff     : +[tool.uv.build-backend] module-name = "data_engine"  (pre-existing, unauthorized)
design doc diff         : line 2238  COMPLETE -> NO-GO                            (pre-existing, unauthorized)
```

Both tracked modifications **predate this re-audit** and are recorded as
pre-existing unauthorized changes. Neither was created nor altered by this audit.

Untracked `src/data_engine/pit/*.py` and `tests/test_pit.py` mtimes are
`2026-09-25 19:49–19:52`, predating the 2026-10-01 specification work. They are
**pre-existing, not created by any correction or lock stage**.

`tests/test_pit_view.py` — the file mandated by §8.1 — **does not exist**.

---

## 3. FROZEN CONTRACT VERIFICATION

Re-executed independently via `sha256sum -c`:

```
1c5ed4a7369a9a9e7f11ad0a10b914369d6550df912bc913828982c5c72d39b6  src/data_engine/schemas.py            OK
4a27cc9aa20464e8255f7853828956378b57669188bf3908b575597586d3be6c  src/data_engine/strategy/schemas.py    OK
dda729bf6591046daae29961c727f0f59d1b03642273735b57c382da5923c8f2  src/data_engine/strategy/provenance.py OK
3b5aacab4640229c9e997f053868fc0a8b9b789078e4d69a933a3ac623f59613  src/data_engine/strategy/backtest.py  OK
853aba15aeba441c966bc3b14feca40bbcdbee887ba730be73d5a56789fe10e7  src/data_engine/strategy/execution.py OK
312ed94a91b92c7145547b5c5b13c3e2e8a349f2aadfae7fb72efd6e32cecd2a  src/data_engine/strategy/ledger.py    OK
9ecd12e51a5f1cf046af0b3dc9434f58d409e7eef2e5779c6226cbedf315e844  src/data_engine/strategy/equity.py    OK
d1ef8b83090827228c9866036d953f9b89491fcdafd045aaf650e0e7d39c94ae  src/data_engine/strategy/position.py  OK
868a3a56a826eaca328c6b1030be8831387d80368e932608265d4b37e4b2f667  src/data_engine/strategy/conditions.py OK
6e30932c179554f27e7980f0b0c6956fd419669cacf79f4d2c8d879b78470e6d  src/data_engine/strategy/metrics.py   OK
9a589f26b4f89a10775a919bfe5ddc8c5a4754a0f10c44ef46fbf85576bfdc59  src/data_engine/strategy/validation.py OK
47aed9c6d932801b584f6bd3ddcafd36015d926deb43d0b725fc8e0f04bcee17  src/data_engine/strategy/__init__.py  OK
8efd870ed0149b0cc96d66d82643cb5f3efdb9176b8183896e1696c347802c84  docs/strategy_engine_design.md       OK

RESULT: 13 of 13 OK. Zero frozen-source modifications. Zero frozen-test modifications.
```

| Frozen-contract check | Result |
|---|---|
| Manifest unchanged | **PASS** — 13/13 |
| Frozen source modified by this re-audit | **NONE** |
| Frozen tests modified by this re-audit | **NONE** |
| Unauthorized production changes created by this re-audit | **NONE** |
| `Candle.to_hash()` wall-clock contamination (F-04) | **CONFIRMED LIVE** — two constructions of an identical candle yield different hashes; `provider_timestamp` differs per instance |
| Phase 3 immunity claim (§10.3) | **CONSISTENT** — `_compute_dataset_hash()` never calls `Candle.to_hash()`; `ingestion_time` correctly excluded from `temporal_hash_input()` |

**Note on the frozen manifest.** The recorded `docs/strategy_engine_design.md` hash
is of the **working-tree** state, which contains the unauthorized line-2238 change.
The committed-state hash is not separately recorded — this is the known §12.3
prerequisite, still outstanding.

---

## 4. IDENTITY / SERIALIZATION FINDINGS

Independently probed against `src/data_engine/pit/serialization.py`,
`src/data_engine/pit/hashing.py`, and the §2–§3 contracts.

| ID | Check | Measured | Spec | Verdict |
|---|---|---|---|---|
| A-01 | `datetime` vs its ISO-8601 string | both → `b'"2024-01-01T00:00:00+00:00"'` | §3.1 type-tagged | **FAIL — COLLISION** |
| A-02 | `Decimal('1.0')` vs `1.0` | `b'"1.0"'` vs `b'1.0'` — identical text, different type, **no type tag** | §3.1 / ID-COL-02 | **FAIL — not distinguished** |
| A-03 | `Decimal` exact string, no float conversion | `Decimal('1.10')` → `b'"1.10"'` (trailing zero preserved) | §3.3 | **PASS** |
| A-04 | bool vs int | `b'true'` vs `b'1'` | §3.1 | **PASS** |
| A-05 | `None` vs `"<NULL>"` vs `""` | `b'null'` \| `b'"<NULL>"'` \| `b'""'` | §3.4 | **PASS** |
| A-06 | dict key ordering | `{'b':1,'a':2,'C':3}` → `b'{"C":3,"a":2,"b":1}'` | §3.2 sorted by code point | **PASS** |
| A-07 | nested dict sorted recursively | `b'{"z":{"b":2,"y":1}}'` | §3.2 | **PASS** |
| A-08 | list order preserved and significant | `[3,1,2]` → `b'[3,1,2]'` | §3.2 | **PASS** |
| A-09 | int-key vs str-key dict | `{1:'a'}` → `b'{"1":"a"}'`; `{'1':'a'}` → `b'{"1":"a"}'` — **COLLISION**; non-string key did **not** raise | §3.2 / ID-COL-04 | **FAIL — COLLISION** |
| A-10 | float `.10f` policy | `0.1+0.2` → `b'0.30000000000000004'` | §3.3 `.10f` | **FAIL** |
| A-11 | float `.10f` form | `100.5` → `b'100.5'` (not `100.5000000000`) | §3.3 | **FAIL** |
| A-12 | `-0.0` → `0.0` | `b'0.0'` | §3.3 | **PASS** |
| A-13 | bare `date` object | raises `SerializationError: Unsupported canonical type: date` | §3.1 mandates `{"D": "<ISO-8601>"}` | **FAIL — encoding absent** |
| A-14 | unsupported types: `set`, `frozenset`, `bytes`, arbitrary object, lambda | all raise `SerializationError` | §3.6 | **PASS — fails closed** |
| A-15 | `NaN` | `SerializationError` | §3.3 | **PASS** |
| A-16 | `+Inf` / `-Inf` | `SerializationError` | §3.3 | **PASS** |
| A-17 | non-ASCII emitted literally | `b'"XAU/USD"'` | §3.5 | **PASS** |
| A-18 | canonical form is single-line JSON | `b'{"a":[1,{"b":2}]}'` | §3.5 | **PASS** |
| A-19 | empty containers | `b'[]'`, `b'{}'` | §3.5 | **PASS** |
| A-20 | `extra="forbid"` on any PIT model | **no `extra=` config anywhere in `src/data_engine/pit/`** | §3.7 / §5.4 / FS-17 | **FAIL** |
| A-21 | `identity_hash()` free function mandated by §2.8 | **absent**; only `deterministic_hash`, `deterministic_hash_bytes`, `verify_hash_determinism`, `verify_cross_process_hash` | §2.8 | **FAIL — MISSING** |
| A-22 | `deterministic_hash` repeatability | identical for identical input | §2.5 | **PASS** |
| A-23 | True subprocess determinism (T-H05) | `'subprocess' in inspect.getsource(hashing)` → **False**; `verify_hash_determinism` loops 3× **in one process** | §8.3 / §8.4 | **FAIL — absent, as §8.4 requires** |

**Serialization summary:** 14 PASS / 9 FAIL / 0 UNVERIFIED. The canonical serializer
is **NON-CONFORMANT** to §3 exactly as §3.1 predicted, with two *more* collisions
than the specification enumerated: `Decimal` vs `float` (A-02) and the
`date`-encoding gap (A-13), in addition to the int-key/str-key collision (A-09)
and the datetime/string collision (A-01).

---

## 5. TEMPORAL / PIT FINDINGS

Independently probed against `src/data_engine/pit/temporal.py`,
`contract.py`, `availability.py`, and the §4–§6 contracts.

| ID | Check | Measured | Spec | Verdict |
|---|---|---|---|---|
| B-01 | cross-field ordering `event ≤ observation ≤ publication ≤ revision` | `event_time=T+5d, observation_time=T` **constructs without error**; no `model_validator` and no ordering constraint exist in `temporal.py` | §4.3 (F-12) | **FAIL — UNENFORCED** |
| B-02 | naive datetime rejected (all 6 fields) | `ValidationError` raised | §4.4 | **PASS** |
| B-03 | aware datetimes normalized to UTC | validator normalizes via `astimezone(UTC)` | §4.4 | **PASS** |
| B-04 | `timezone_requirement` restricted to `Literal["UTC"]` | non-UTC raises | §4.4 | **PASS** |
| B-05 | `ingestion_time` excluded from eligibility | `temporal_hash_input()` with `ingestion_time=2030` contains **no** 2030 value | §2.4 / §2.7 | **PASS** |
| B-06 | `ALLOW_NULL` + `required_fields` must be prohibited | `TemporalContract(required_fields=['publication_time'], missing_field_policy=ALLOW_NULL)` then validating a null `publication_time` → **no raise** | §4.2 (F-13) | **FAIL — required semantics weakened** |
| B-07 | publication cutoff inclusive | `publication_time == cutoff` → `is_available` = **True** | §4.6 | **PASS** |
| B-08 | publication cutoff exclusive beyond boundary | `cutoff + 1µs` → `False` | §4.6 | **PASS** |
| B-09 | effective-time exclusion from views | `effective_time` **is present** in `temporal_hash_input()`; no view-exclusion rule exists | §4.7 (T-P04) | **PARTIAL — rule absent** |
| B-10 | future publication silent exclusion | no `PitViewBuilder` exists | §4.7 | **UNVERIFIED — unimplemented** |
| B-11 | future revision invisible / prior revision governs | no `RevisionChain` exists | §4.6, §4.7 | **UNVERIFIED — unimplemented** |
| B-12 | legacy sidecar reproducibility (PROH-LEG-06) | no `PitSidecar`, no builder | §6.4 | **UNVERIFIED — unimplemented** |
| B-13 | legacy classification `PIT_INELIGIBLE` / `ASSUMED_PUBLICATION` | neither enum nor logic exists | §6.3 | **UNVERIFIED — unimplemented** |
| B-14 | deterministic PIT reconstruction (`view_hash`) | no `PitView` | §7.4 | **UNVERIFIED — unimplemented** |
| B-15 | tie-breaker total order | no `TieBreakerPolicy` | §7.3 | **UNVERIFIED — unimplemented** |
| B-16 | AvailabilityPolicy pairing #1 `publication_controlled` + `PublicationControlledAvailability` | constructs (correct pairing) | §5.2 | **PASS** |
| B-17 | AvailabilityPolicy pairing #2 `publication_controlled` + `RevisionAwareAvailability` — **MISMATCH** | **constructs without error**; `is_available(pub=T, eff=T, rev=T+3d, T)` = **True** — the future `revision_time` is consumed as an argument in the wrong position | §5.3 (F-16) | **FAIL — future-revision leakage** |
| B-18 | AvailabilityPolicy pairing #3 `revision_aware` + `PublicationControlledAvailability` — **MISMATCH** | **constructs without error**; `is_available(...)` = **False** — the future `revision_time` is silently **ignored** | §5.3 | **FAIL — future-revision leakage** |
| B-19 | AvailabilityPolicy pairing #4 `revision_aware` + `RevisionAwareAvailability` | constructs (correct pairing) | §5.2 | **PASS** |
| B-20 | unknown policy key rejected | `PublicationControlledAvailability(require_publication=True, evil=1)` **constructs; `evil` silently dropped** | §5.4 / §3.7 (F-17) | **FAIL — silent weakening** |
| B-21 | policies contain no callables/lambdas | verified declarative | §5.5 | **PASS** |

**Temporal summary:** 7 PASS / 6 FAIL / 1 PARTIAL / 7 UNVERIFIED.

**Both mismatched AvailabilityPolicy pairings reproduce live.** Each computes under
the wrong rule, and in the `revision_aware` + `PublicationControlled` case a
**future `revision_time` is silently ignored** — the exact future-revision leakage
PIT exists to prevent. §5.1's defect analysis is independently confirmed as accurate.

---

## 6. TEST FINDINGS

Classification distinguishes **SPECIFIED** / **EXISTING** / **PASSING** / **MISSING**.

| Namespace | SPECIFIED | EXISTING | PASSING | MISSING |
|---|---|---|---|---|
| Mandatory P0 (`T-*`, §8.2) | 19 | **0** | **0** | **19** |
| Supplementary (`SUB-*`, §8.3) | 25 | **0** | **0** | **25** |
| Component-level (§8.5.1–8.5.9) | 33 | **0** | **0** | **33** |
| Legacy semantics (`LEG-T*`, §8.5.10) | 3 | **0** | **0** | **3** |
| **TOTAL** | **80** | **0** | **0** | **80** |

| ID | Check | Result |
|---|---|---|
| C-01 | `tests/test_pit_view.py` exists | **NO — absent** |
| C-02 | P0 identifiers present anywhere in `tests/` | **0 files** match `T-H0[1-5]|T-P0[1-4]|T-R0[1-4]|T-M0[16]|T-O01|T-X0[17]` |
| C-03 | SUB identifiers present anywhere in `tests/` | **0 files** match `SUB-[0-9]{2}` |
| C-04 | Component tests (`TIE-*`,`VAL-*`,`INST-*`,`SPEC-*`,`VEN-*`,`SRC-*`,`CAL-*`,`EXP-*`,`CFG-*`) present | **NONE** |
| C-05 | Legacy tests present | **NONE** (`legacy`/`LEG` → 0 matches) |
| C-06 | True subprocess determinism | **ABSENT** — `subprocess` → 0 matches in `tests/test_pit.py` |
| C-07 | §8.5.12 component-ID reconciliation | **EMPTY — zero undefined**, independently re-run |
| C-08 | §7 → §8 `T-*` and `SUB-*` reconciliation | **EMPTY — zero undefined** |
| C-09 | Test count 80 in specification | **CONFIRMED** — 19 + 25 + 33 + 3 |
| C-10 | Undefined pre-correction finding documented as **23** | **CONFIRMED** — §8.5.13, with the 18→23 reconciliation table |

### Category-D weak tests — independently confirmed still present in `tests/test_pit.py`

| Test | Line | Independent finding | Spec verdict |
|---|---|---|---|
| `test_hash_cross_process_determinism` | 653 | calls `verify_hash_determinism()` which loops **in one process** | weak — §8.4 requires ≥5 real subprocesses |
| `test_hash_no_timestamp` | 672 | hashes the same literal twice; cannot detect timestamp injection into entity identity | **tautological** — weak |
| `test_hash_no_uuid` | 680 | asserts `"-" not in h`; SHA-256 hex never contains `-` regardless of input | **vacuous** — weak |
| `test_no_phase3_source_modified` | 728 | asserts `os.path.exists(f)` for 11 files; **cannot detect any modification** | **vacuous** — weak |

**All four weak tests remain in place. None has been replaced.** Their presence
means the unauthorized 97-test delta includes tests that *pass while the defects
they nominally cover remain present*.

---

## 7. FILESYSTEM SECURITY FINDINGS

Re-tested live against `FileDataProvider` using a temporary directory outside the
repository. **All probe files deleted immediately; no persistent file created.**

| ID | Check | Measured | Spec | Verdict |
|---|---|---|---|---|
| D-01 | `endpoint` escape outside the data root | **ESCAPE SUCCEEDED — 1 candle read** | §11.2 FS-05 / §11.7 T1 | **FAIL — vulnerability live** |
| D-02 | containment enforcement (`resolve`, `realpath`, `commonpath`) | **none present** in `provider.py` | §11.1 FS-01…03 | **FAIL — absent** |
| D-03 | approved-root declared on `ProviderConfig` | **no** `approved_root` / `data_root` / `root` field | §11.2 FS-04 | **FAIL — absent** |
| D-04 | rejection before `os.path.exists()` | `os.path.join` → `os.path.exists` → `pd.read_csv`, **no gate** | §11.3 FS-09/FS-10 | **FAIL** |
| D-05 | absolute path via `instrument` | **blocked** (incidentally, by the `_4h.csv` filename suffix, not by a control) | §11.5 T2 | **PASS incidentally — not a control** |
| D-06 | `../` traversal via `instrument` | **blocked** (incidentally, 0 candles) | §11.3 T3 | **PASS incidentally — not a control** |
| D-07 | symlink / reparse handling | `islink` **not present** in `provider.py`; symlink creation blocked on this host (`OSError 1314`, no `SeCreateSymbolicLinkPrivilege`) | §11.4 FS-11…13 | **UNVERIFIED — structurally absent, empirically untestable here (F-29)** |
| D-08 | fail-closed when no root configured | `endpoint=None` silently defaults to `"./data"` — **no fail-closed** | §11.2 FS-06 / FS-19 | **FAIL** |
| D-09 | `extra="forbid"` on `ProviderConfig` | `model_config.get('extra')` → `None` | §11.6 FS-17 | **FAIL** |
| D-10 | arbitrary directory enumeration | `check_connectivity("C:/Windows")` → **True** | §11.7 T5 | **FAIL — information disclosure** |
| D-11 | security audit trail | `src/audit.log` is 90 bytes: `{"timestamp": "...", "action": "test", "details": {"x": 1}}` — no actor, no path, no decision, no rule, no fail-closed binding | §11.8 FS-21/FS-22 | **FAIL — not a security audit trail** |

**Filesystem summary:** 2 PASS (both incidental) / 8 FAIL / 1 UNVERIFIED.
**Zero containment controls are implemented.** The §11.7 attack results reproduce
independently and exactly as recorded in the specification.

---

## 8. DOCUMENTATION FINDINGS

Inspected without repair. **No documentation was modified by this re-audit.**

### DL-D1 — §12.3 line-ending verification claim is FALSE (MATERIAL)

`PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md:1181` states:

```
| Line endings | LF only (CRLF count = 0) ✓ |
```

Independently re-measured at byte level on `docs/strategy_engine_design.md`:

| Metric | Measured | Claimed |
|---|---|---|
| CRLF count | **2238** | **0** |
| Lone CR count | 0 | — |
| LF count | 2238 | — |
| Final bytes | `...FINAL REVIEW\r\n` | LF-terminated |

**The claim is false.** The file is CRLF throughout. The design document's own
verification checklist requires LF-only endings, so this is material, not
cosmetic. This is the DEFECT-A class — a verification result asserted rather than
measured — recurring inside the document written to eliminate it.

### DL-D2 — §14 stale stage status, and a re-introduced hard-coded count (MATERIAL)

| Line | Text | Contradiction |
|---|---|---|
| 1395 | "The next authorized stage is **Architecture Correction** … **Stage 1 has not begun.**" | §15.2 of the same document records Stage 1 corrections as **applied**; the correction checklist §7 records the stage **complete** |
| 1397 | "### Stage 1 — Architecture Correction (NEXT AUTHORIZED STAGE)" | Stage 1 is finished; Stage 2 (Design Lock) is the stage in progress |
| 1401 | "Resolve authorization for all **27** untracked artifacts" | **Measured: 30.** Re-introduces the exact hard-coded-count defect DEFECT-C / REG-06 exists to eliminate |

### DL-D3 — Correction checklist retains the superseded "18" figure outside the supersession list (MINOR)

`PHASE_4A1_ARCHITECTURE_CORRECTION_CHECKLIST.md:171` (heading) and `:201` (diff
plan) both state "18 undefined test identifiers". The authoritative specification
§8.5.13 declares that figure **erroneous** and corrects it to **23**.

Neither the checklist nor `PHASE_4A1_ARCHITECTURE_CORRECTION_REPORT.md` appears in
the §12.1 supersession list (11 documents). They are therefore neither governing
nor formally superseded — an authority-hierarchy gap under GOV-04.

### DL-D4 — Component count contradiction: 19 vs 13 (MINOR)

| Line | Text |
|---|---|
| 121 | "**Component count: 19** (supersedes the '13 primitives' count …)" |
| 1223 | "Result: 5 of **13** components carry contradictory ownership assignments." |
| 1366 | "All **13** components fully specified" |
| 1410 | "Ratify §7 component contracts (**13** components)" |
| 1486 | "COMPONENTS IMPLEMENTED: **0 of 13**" |

The counts reconcile only by inferring that 13 §7 contracts + 6 foundation
components (§2–§5) = 19. **The specification never states this reconciliation**, so
a document that supersedes the number 13 still uses it in five places.

### Governance coherence checks

| Check | Result |
|---|---|
| Authority hierarchy coherent | **PARTIAL** — §0.1 is well-formed, but DL-D3 leaves two documents neither governing nor superseded |
| Blocker table internally consistent | **PASS** — §13.1 and §13.3 both show 8 OPEN / 0 CLOSED |
| No contradictory status claims | **FAIL** — DL-D2 (§14 "has not begun" vs §15.2 applied) |
| Implementation stated NOT_AUTHORIZED | **PASS** — §15.2, checklist §0.3, Design Lock Record §13 |
| Design Lock Record implies authorization | **NO** — §13 states explicitly it grants none |
| Design Lock Record contains false verification claims | **NO** — its CRLF finding and manifest results re-verified accurate |

---

## 9. NEW FINDINGS

Three findings surfaced during this re-audit that were not recorded by the
Architecture Correction stage.

### RA-NF-01 — Integer-key / string-key dictionary collision is REAL at the byte level (MATERIAL)

`{1: "a"}` and `{"1": "a"}` both serialize to `b'{"1":"a"}'`.

The specification §3.1 predicted this collision at the `_canonical_value` layer.
This audit measured the actual `canonical_serialize()` output and confirms the
collision **survives to the canonical bytes** — the two inputs are
**indistinguishable in any Phase 4 identity**. §3.2's requirement that non-string
keys MUST raise is not implemented: the integer key is silently coerced to `"1"`.
This directly violates **ID-COL-04**.

Note this refines, and does not contradict, the Design Lock Record §11, which had
characterized the `_canonical_value`-level distinction as sufficient.

### RA-NF-02 — `date` objects are unsupported despite an explicit §3.1 mandate (MINOR)

`canonical_serialize(date(2024,1,1))` raises
`SerializationError: Unsupported canonical type: date`. §3.1 mandates the encoding
`{"D": "<ISO-8601>"}` for `date`. The mandated encoding was never implemented, and
the specification's own collision analysis did not notice this gap. Any Phase 4
entity carrying a `date` (notably a `CalendarRef` calendar version boundary or an
`InstrumentSpecification` effective-dated boundary, §7.8/§7.11) is currently
unserializable.

### RA-NF-03 — `Decimal` and `float` are not type-distinguished (MINOR)

`Decimal('1.0')` → `b'"1.0"'` and `1.0` → `b'1.0'`. The **type tags differ**
(`"s"`-style quoted string vs bare number) so these two are in fact
distinguishable at the byte level — this is **not** a collision. However §3.1
mandates explicit `{"d": …}` and `{"f": …}` tags, and the implementation relies on
incidental JSON formatting rather than the mandated explicit tags. Recorded as a
conformance gap against §3.1, classified **not** as a collision.

---

## 10. EIGHT-BLOCKER RECONCILIATION

Closure requires **all four**: condition satisfied **AND** implementation evidence
exists **AND** required tests pass **AND** independent re-audit confirms.
No blocker meets any of these four. **None is closed.**

| # | BLOCKER | CURRENT | SPECIFICATION | IMPLEMENTATION | EVIDENCE | RE-AUDIT | NEW FINDINGS | CLOSURE ELIGIBILITY |
|---|---|---|---|---|---|---|---|---|
| 1 | Phase ownership contradictions | **OPEN** | **COMPLETE** — §1.2 single-owner table for 19 components; R-01 resolves the 5 contradictions; §12.5 records executed reconciliation | **ABSENT** — R-03 re-export not implemented; `EvidenceProvenance` dual-defined: `schemas.py:47 is evidence.py:18` → **False**; `schemas` copy lacks `is_strong_evidence()` | **ABSENT** — SUB-22 does not exist | **CONFIRMS OPEN** — spec is coherent; code contradicts spec | DL-D3, DL-D4 | **NOT ELIGIBLE** |
| 2 | Identity-contract specification gaps | **OPEN** | **COMPLETE** — §2 Identity Contract with allowlists, ID-WC-01…03, `pit4.` versioning, §2.8 free function | **ABSENT** — `identity_hash` missing; no allowlist enforcement; no wall-clock rejection | **ABSENT** — T-H01/02/03/04, SUB-21/24/25 do not exist | **CONFIRMS OPEN** — A-20, A-21, A-22 fail | RA-NF-01, RA-NF-02 | **NOT ELIGIBLE** |
| 3 | Temporal-contract gaps | **OPEN** | **COMPLETE** — §4.1 six fields, §4.2 required semantics, §4.3 ordering, §4.6 inclusive cutoff | **ABSENT** — no ordering validator; `ALLOW_NULL` weakens `required_fields` | **ABSENT** — T-P01/02/04, T-M01/06, SUB-09/10/11/19/20 do not exist | **CONFIRMS OPEN** — B-01, B-06 FAIL; B-07/B-08 PASS | — | **NOT ELIGIBLE** |
| 4 | Canonical serialization alignment | **OPEN** | **COMPLETE** — §3.1 type-tagged encoding, §3.3 `.10f`, §3.6 fail-closed | **NON-CONFORMANT** — datetime/string and int-key/str-key collisions; `.10f` absent; `date` unsupported | **ABSENT** — SUB-04…08 do not exist | **CONFIRMS OPEN** — 9 FAIL / 14 PASS | RA-NF-01, RA-NF-02, RA-NF-03 | **NOT ELIGIBLE** |
| 5 | PIT component specifications | **OPEN** | **COMPLETE** — §7.1–7.13 contracts; §5 discriminated-union mandate | **ABSENT** — **13 of 13 required components MISSING**; both mismatched AvailabilityPolicy pairings construct silently and leak | **ABSENT** — SUB-01/02/03 + 33 component tests do not exist | **CONFIRMS OPEN** — B-17, B-18, B-20 reproduce live | — | **NOT ELIGIBLE** |
| 6 | P0/T-PIT acceptance gaps | **OPEN** | **COMPLETE** — §8 matrix, 80 tests, clean §8.5.12 reconciliation | **N/A** — specification stage | **ABSENT** — `tests/test_pit_view.py` does not exist; 0 of 80 identifiers present; true subprocess determinism absent | **CONFIRMS OPEN** — C-01…C-06 | — | **NOT ELIGIBLE** |
| 7 | Regression-baseline ambiguity | **OPEN (PARTIAL spec)** | **PARTIAL** — §9 baseline declared; §12.3 authorization record still missing; DL-D4 count contradiction | **N/A** | **ABSENT** — SUB-18 + the four §8.4 replacements do not exist; all four weak tests still in place | **CONFIRMS OPEN** — 367/464/97 independently reproduced; weak tests C-07 confirmed | DL-D1, DL-D2 | **NOT ELIGIBLE** |
| 8 | Filesystem security | **OPEN** | **COMPLETE** — §11 FS-01…FS-24; §11.7 measured attack results | **ABSENT** — zero containment controls; endpoint escape live; `check_connectivity` enumerates arbitrary directories | **ABSENT** — SUB-12…SUB-17 do not exist; audit trail is not a security trail | **CONFIRMS OPEN** — D-01…D-11 | DL-D1 | **NOT ELIGIBLE** |

```
BLOCKERS OPEN:          8
BLOCKERS CLOSED:        0
SATISFIED:              0
PARTIAL:                0  (specification-partial only; no blocker closure-eligible)
```

---

## 11. DESIGN LOCK DECISION

Design/specification integrity criteria, evaluated against the authoritative
specification and independently re-measured:

| Criterion | Result |
|---|---|
| Single ownership for every 4A.1 component | **PASS** |
| Phase 4 Identity Contract present | **PASS** |
| Canonical serialization contract present | **PASS** |
| Temporal semantics present | **PASS** |
| AvailabilityPolicy discrimination mandated | **PASS** |
| Legacy PIT rules present | **PASS** |
| PIT component contracts present | **PASS** |
| Complete acceptance-test matrix (80) | **PASS** |
| Regression baseline definition | **PASS** |
| Frozen Phase 3 manifest recorded | **PASS** |
| Filesystem-security contract present | **PASS** |
| Compact blocker-closure table present | **PASS** |
| Section references resolve | **PARTIAL** — DL-D2 |
| §7 test identifiers defined in §8 | **PASS** |
| §8.5.12 zero undefined component IDs | **PASS** |
| Test count exactly 80 | **PASS** |
| Undefined pre-correction finding = 23 | **PASS** |
| No contradictory ownership in the authoritative spec | **PASS** |
| Blocker table 8 OPEN / 0 CLOSED | **PASS** |
| Implementation NOT_AUTHORIZED | **PASS** |
| No false verification claims | **FAIL** — DL-D1 |
| Internally consistent stage state | **FAIL** — DL-D2 |
| Component count internally consistent | **FAIL** — DL-D4 |
| Authority hierarchy fully closed | **FAIL** — DL-D3 |

Four unresolved Design Lock defects remain: **DL-D1, DL-D2, DL-D3, DL-D4**.
DL-D1 is a false verified claim; DL-D2 is a self-contradictory stage state. Both
would propagate into any later authorization review, which resolves authority
through the §0.1 hierarchy rather than by re-measuring.

```
DESIGN_LOCK = FAILED
```

This audit **concurs** with the Design Lock Record's own verdict. The prior record
is therefore confirmed accurate on its central conclusion.

**All four defects are documentation-only.** None requires production code, none
changes an architectural decision, none touches a frozen Phase 3 contract.

---

## 12. IMPLEMENTATION READINESS

```
IMPLEMENTATION READINESS: NOT_READY
```

| Prerequisite (§15.1) | State |
|---|---|
| P-1 All 8 blockers CLOSED, each re-audited | **FAIL** — 8 OPEN |
| P-2 Stages 1–3 complete | **FAIL** — Stage 1 has unresolved defects; Stage 2 FAILED; Stage 3 not complete |
| P-3 Authorization Review explicitly granted authorization | **FAIL** — not granted |
| P-4 §10.2 manifest verified unchanged at moment of implementation | **PASS** — 13/13 verified now |
| P-5 §9 baseline re-established and declared | **PASS** — 367/464/97 verified now |
| P-6 `tests/test_pit_view.py` exists with all mandatory P0 tests | **FAIL** — absent |
| P-7 No UNKNOWN-authorization artifact in the working tree | **FAIL** — 7 untracked `.py` (6 PIT source + 1 test) plus 2 unauthorized tracked modifications |
| P-8 Design-document authorization decision recorded | **FAIL** — absent; requires a human decision |

**2 of 8 prerequisites met. 6 unmet.**

---

## 13. AUTHORIZATION STATUS

```
IMPLEMENTATION_AUTHORIZATION = NOT_AUTHORIZED
```

This report **does not grant authorization** and cannot. Per §15.1 P-3, an
authorization review may only *recommend*; the grant itself requires an explicit
human authorization mechanism invoked under the project's governance
requirements. No such mechanism has been invoked.

No blocker was closed by this audit. All eight remain OPEN with zero closure
eligibility.

---

## 14. REQUIRED NEXT ACTION

**Documentation correction pass on the authoritative specification** (re-opening
Stage 1 per §14 Stage 2). Correct, and **only**, the following — all documentation:

| Item | Correction |
|---|---|
| DL-D1 | Replace the false `CRLF count = 0 ✓` claim at spec line 1181 with the measured value, or normalize the design document to LF and re-measure. Do **not** touch the frozen manifest hash without recording the change. |
| DL-D2 | Update §14 to reflect that Stage 1 has **completed**; remove "Stage 1 has not begun" and the "NEXT AUTHORIZED STAGE" label; replace the hard-coded "27 untracked artifacts" with a REG-06-compliant measurement rule |
| DL-D3 | Add `PHASE_4A1_ARCHITECTURE_CORRECTION_CHECKLIST.md` and `PHASE_4A1_ARCHITECTURE_CORRECTION_REPORT.md` to the §12.1 supersession list, or correct the retained "18" figure, so the authority hierarchy is closed |
| DL-D4 | State the 13 §7 contracts + 6 foundation components = 19 reconciliation explicitly, or unify the count used in §12.5, §13.3, §14.1.10 and §15.2 |

Additionally, record RA-NF-01, RA-NF-02 and RA-NF-03 in the specification's
finding register (§0.2), since RA-NF-01 shows the §3.1 collision analysis was
incomplete — it predicted the int-key collision but did not verify that the
collision survives to canonical bytes, nor detect the `date`-encoding gap.

**Explicitly NOT authorized and NOT to be started:** any production-code
implementation, any test creation, any blocker closure, any frozen Phase 3 change,
any authorization grant.

---

```
RE-AUDIT_RESULT: RE-AUDIT_FAIL
DESIGN_LOCK: FAILED
BLOCKERS: 8 OPEN / 0 CLOSED
IMPLEMENTATION READINESS: NOT_READY
IMPLEMENTATION_AUTHORIZATION: NOT_AUTHORIZED
```

A `RE-AUDIT_FAIL` does not assert the architecture is unsound. It records that the
**design baseline is not yet free of internal contradiction and false verification
claims**, which is the precondition the Design Lock exists to establish. The
substantive architecture content — ownership, identity contract, serialization
contract, temporal contract, availability discrimination, legacy rules, component
contracts, 80-test matrix, 367/464/97 baseline, 13-file manifest, filesystem
contract, compact closure table — verifies correctly and was independently
re-confirmed. The four defects are documentation defects, and correcting them is
the next stage.

---

*END DOCUMENT — PHASE 4A.1 INDEPENDENT READ-ONLY RE-AUDIT REPORT v1.0.0*

*This audit implemented nothing, modified no source file, modified no test, and
altered no frozen Phase 3 contract. All temporary forensic probes were created
outside the repository and deleted immediately. No blocker was closed.*