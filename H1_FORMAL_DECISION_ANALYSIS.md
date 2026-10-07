# H-1 Formal Decision Analysis and Authorization Record

| Field | Value |
|---|---|
| Record ID | H1-FDA-2026-10-07 |
| Subject | H-1 — F-04 wall-clock contamination of frozen Phase 3 `Candle.to_hash()` |
| Repository | `ai-trading-lab-data-engine` (local clone: `/home/z/my-project/workspace/repo`) |
| Inspected commit (HEAD) | `a7fba96433b3858f49e0c96a113332f11078bbc8` |
| Branch | `phase-4a/4a1-architecture-correction` |
| Mode | **READ-ONLY forensic governance analysis — no implementation performed** |
| Prepared by | ZAI (controlled construction agent) — decision authority reserved to the HUMAN principal |
| Date of record | 2026-10-07 |
| Location of this record | `/home/z/my-project/download/H1_FORMAL_DECISION_ANALYSIS.md` (written OUTSIDE the repository working tree; the repository is untouched by this analysis) |

**Authorization scope of this document.** This record ANALYZES and RECOMMENDS. It does not
grant, imply, or pre-authorize any implementation work, any Phase 3 contract amendment, any
test modification, any commit, push, or merge, any WP-2/WP-3/WP-5 activity, or any closure
of H-1. Final disposition authority is reserved exclusively to the governing human decision.

---

## 1. Executive Decision Summary

H-1 concerns a real, reproducible, **pre-existing** determinism defect inside a **frozen
Phase 3 contract**: `Candle.to_hash()` (defined at `src/data_engine/schemas.py:130-133`)
hashes the full Pydantic model dump, including the `provider_timestamp` field, whose
default factory stamps the current wall-clock time whenever the field is omitted at
construction (`src/data_engine/schemas.py:84`, `default_factory=_now_utc`). The defect was
reproduced **first-hand during this analysis** at HEAD `a7fba96`: two candles carrying
byte-identical OHLCV content produced digests `fec31014…` and `d1556110…` (unset path),
while the same construction with an explicit `provider_timestamp` produced the identical
digest `884e2ce9…` twice. The defect therefore exists, is mechanical in origin, and is not
a reporting artifact.

The controlling governance facts are these. First, the defect predates the current
construction cycle: the `Candle` class region (lines 61-134 of `src/data_engine/schemas.py`)
is byte-identical between `main@13fdc7e` and HEAD, the contamination was documented as
**CONTAMINATED** in the pre-remediation `HASH_FORENSIC_AUDIT.md`, and it was formally
registered as finding **F-04** in the authoritative remediation specification with the
disposition *RESOLVED — declared identity-ineligible* (§2.4, §10). Second, containment is
not merely declared policy; it is machine-enforced in three independent layers: the Phase 4
identity contract prohibits the field outright (`PROHIBITED_IDENTITY_FIELDS` at
`src/data_engine/pit/hashing.py:50-57`, with direct and transitive enforcement at lines
137-169), the SUB-25 acceptance test detonates a monkeypatched bomb if `Candle.to_hash()`
is invoked anywhere in the Phase 4 identity path (`tests/test_pit_view.py:1201-1231`), and
the mutation gate MUT-13 verifies the suite detects an injected `Candle.to_hash()` call
(`scripts/mutation_gate.py:285-300`). Third, the frozen Phase 3 backtest hash chain is
**immune by construction**: `BacktestEngine._compute_dataset_hash()`
(`src/data_engine/strategy/backtest.py:608-627`) serializes candle fields explicitly and
never calls `Candle.to_hash()` — a property measured in the specification (§10.3, "dataset
hash UNCHANGED when every candle.provider_timestamp -> 2030: True") and re-measured by the
week-end inspection (3/3 subprocess runs deterministic).

This analysis adds one **precision finding** beyond the week-end inspection's summary
wording. The inspection's residual-risk statement was scoped to "zero such call sites in
Phase 4+ modules," which is accurate; read more broadly as "zero current call sites
relying on the defective unset-timestamp path," it is incomplete. There is exactly **one**
production call site of `Candle.to_hash()` in `src/`: `DataIngester._compute_raw_hash()`
(`src/data_engine/ingestion.py:165-168`), whose input candles are constructed by
`FileDataProvider.fetch_candles()` **without** an explicit `provider_timestamp`
(`src/data_engine/provider.py:270-281`) — i.e. every candle on that path is wall-clock
stamped. That call site is nonetheless **dormant**: `DataIngester.ingest()` has no caller
in `src/` other than the `ingest_from_file()` convenience wrapper (itself uncalled), the
CLI only prints advisory text (`src/data_engine/cli.py:47-49`), and no test invokes
`ingest()` at all. The chain is reachable by any future or external caller of the public
ingestion API, and would contaminate the audit-class outputs `Dataset.raw_data_hash` and
`ProvenanceRecord.source_hash` — not any identity path. This nuance raises residual risk
above zero but does **not** invalidate containment, because no active identity,
reproducibility, or PIT-correctness path consumes those values.

**Recommendation: OPTION A — CONTAINMENT.** Frozen Phase 3 remains byte- and
behavior-preserved; H-1 remains registered as a known frozen-contract limitation; the
unset-timestamp path remains prohibited for identity use; no amendment work is authorized.
This recommendation is not a closure: **H-1 = OPEN / HUMAN-REVIEWED / CONTAINED**, and
final disposition remains a human decision. Eight of ten decision criteria evaluate
PASS or CONTAINED with LOW risk; the two UNVERIFIED components (historical artifacts
outside the repository, and hypothetical amendment migration outcomes) both argue for
deferred, separately-authorized analysis rather than immediate action.

---

## 2. H-1 Statement of Facts

Each fact below was verified directly against repository evidence during this read-only
analysis at HEAD `a7fba96433b3858f49e0c96a113332f11078bbc8` unless explicitly attributed
to another measured source. No fact is inferred from a report claim without a code-level
or command-level check.

**F-1 (Repository ground truth).** HEAD is `a7fba96433b3858f49e0c96a113332f11078bbc8`
on branch `phase-4a/4a1-architecture-correction` (`git rev-parse HEAD`; `git branch
--show-current`). The working tree is clean apart from ONE pre-existing untracked file,
`ZAI_WEEK_END_FULL_FORENSIC_INSPECTION.md` (the prior week-end inspection report,
documented as the only untracked artifact in the worklog of that inspection). No stash
entries exist; `git diff --stat HEAD` is empty. Local `main` sits at `13fdc7e` (behind);
`origin/main` was previously fast-forwarded to `a7fba96`.

**F-2 (Test suite state is reported, not re-run).** The authoritative current state
reports 692 passed / 0 failed / 0 errors / 0 skipped / 0 xfailed. This analysis did not
re-execute the suite (read-only forensic mode; prior inspections measured it 3×
deterministic). Nothing in this record depends on the suite having been re-run.

**F-3 (The defect exists).** `Candle.to_hash()` returns
`sha256(self.model_dump_json())` (`src/data_engine/schemas.py:130-133`).
`model_dump_json()` serializes **all** model fields, including `provider_timestamp`
(`src/data_engine/schemas.py:84`). First-hand reproduction at HEAD, this analysis
(2026-10-07): identical OHLCV inputs with the field omitted produced
`fec310147c18f178dd2b3e10fa4716d2a25e83eb9ca5a0cae7afab979d1ce575` and
`d1556110e579256f8e70fef288f6981d364ff7f619d6d0c028078c136891d14d`; with the field
explicitly set, two constructions produced the identical digest
`884e2ce970db581ace0924c20b1da4e6f8b1d18431a62bdb8441ec865b84cd21`. The week-end
inspection independently measured the same divergence in 3 fresh subprocesses
(`c2c578…`, `b7ea2c…`, `d8d592…`) and stability on the explicit path (`84ed9d0c…`, 2/2).

**F-4 (The contract is frozen and untouched).** Eleven frozen Phase 3 strategy files are
blob-identical to `main@13fdc7e` — `git log 13fdc7e..a7fba96 -- src/data_engine/strategy/`
is EMPTY (no commit in the cycle touches any frozen path). The `Candle` class region
(lines 61-134 of `src/data_engine/schemas.py`) is byte-identical between `13fdc7e` and
`a7fba96` (verified by direct diff of `git show` extractions). The only cycle commit
touching `schemas.py` is `b100418` (B8 filesystem security), whose hunks are confined to
the `EvidenceProvenance` re-export and `ProviderConfig`; no `Candle` hunk exists.

**F-5 (SUB-18 manifest integrity).** The 13-file committed-state manifest recorded in
`PHASE_4A1_IMPLEMENTATION_RECORD.md` §3 re-verified **13/13** SHA-256 pins match at HEAD
during this analysis (including `9aa07004…` for `src/data_engine/schemas.py`). The same
pins are independently re-asserted inside `tests/test_pit_view.py` (SUB-18, lines
1011/1044), so any drift fails the suite.

**F-6 (The defect predates the current cycle).** It is present at `13fdc7e` (F-4), was
documented pre-remediation in `HASH_FORENSIC_AUDIT.md` ("STATUS: CONTAMINATED —
wall-clock field enters identity; no canonical serialization; no allowlist"), was
measured at design lock (`PHASE_4A1_DESIGN_LOCK_RECORD.md:352`: "`Candle.to_hash()`
across two constructions | differs"), and was registered as **F-04** in the authoritative
remediation spec §0.2 with disposition "RESOLVED — declared identity-ineligible" (§2.4,
§10). The current Phase 4A.1 construction work did not introduce it and never claimed to
fix it.

**F-7 (Phase 4 identity containment is machine-enforced).** Three independent layers:
(i) contract — `PROHIBITED_IDENTITY_FIELDS` includes `provider_timestamp` with the
comment "Candle — CONTAMINATED (F-04)" (`src/data_engine/pit/hashing.py:50-57`),
enforced directly and transitively by `_assert_no_prohibited_fields`
(`pit/hashing.py:137-169`, ID-WC-01/02); (ii) code — `dataset_content_hash()` reads
candle attributes directly and its docstring prohibits the frozen hash
(`src/data_engine/pit/view.py:60-80`, prohibition text at line 65); (iii) tests —
SUB-25 `test_no_phase3_hash_in_phase4_identity` monkeypatches `Candle.to_hash` with a
bomb and drives the full view path over REAL Phase 3 candles
(`tests/test_pit_view.py:1199-1231`). The mutation gate MUT-13 confirms the suite detects
an injected `to_hash()` call inside `dataset_content_hash`
(`scripts/mutation_gate.py:285-300`), and MUT-05 confirms wall-clock field injection into
sidecar identity is detected (T-H02).

**F-8 (The frozen backtest chain is immune).** `BacktestEngine._compute_dataset_hash()`
(`src/data_engine/strategy/backtest.py:608-627`) serializes
timestamp/open/high/low/close/volume per candle with explicit formatting — it neither
calls `Candle.to_hash()` nor includes `provider_timestamp`. The specification measured
this (§10.3 / F-32 "Phase 3 immunity — CONFIRMED": dataset hash UNCHANGED when every
`provider_timestamp` is moved to 2030), and the week-end inspection re-measured it
(3/3 subprocess determinism). `compute_result_hash()` additionally excludes
`run_timestamp` (`strategy/provenance.py:112` region).

**F-9 (Precision finding — the dormant Phase 3 ingestion path does rely on the unset
path).** The ONLY `src/` call site of `Candle.to_hash()` outside its own definition is
`DataIngester._compute_raw_hash()` (`src/data_engine/ingestion.py:165-168`), invoked at
`ingestion.py:98` (as `ProvenanceRecord.source_hash`) and `ingestion.py:121` (as
`Dataset.raw_data_hash`). Its candles originate from
`MarketDataProvider.retrieve_raw()` → `FileDataProvider.fetch_candles()`, which constructs
`Candle(...)` WITHOUT `provider_timestamp` (`src/data_engine/provider.py:270-281`), so
every candle is wall-clock stamped by the default factory. The base `retrieve_raw()`
additionally stamps its own wall-clock `retrieval_timestamp`
(`src/data_engine/provider.py:101`). **However, the path is dormant**: no `src/` code
calls `DataIngester.ingest()` except the `ingest_from_file()` wrapper
(`ingestion.py:219`, itself uncalled); the CLI prints advisory text only
(`src/data_engine/cli.py:47-49`); no test instantiates `DataIngester` or calls `ingest()`
(verified by grep — imports only). The week-end inspection's claim "zero current call
sites relying on the defective unset-timestamp path" is accurate **as scoped to Phase 4+
modules**; at whole-repository granularity the correct statement is "one dormant
production call site, zero active callers, zero identity consumers."

**F-10 (Test-suite relationship to the defect).** The suite touches the defective method
exactly once, as a smoke assertion: `test_phase3_candle_temporal_compatibility`
(`tests/test_pit.py:914-922`) constructs a candle WITHOUT `provider_timestamp` and asserts
only `c.to_hash() is not None`. There is no determinism assertion on the unset path
anywhere in the suite — correctly so, since such an assertion would FAIL against the
frozen contract. Consequently "692 tests pass" is evidence of containment health, not of
defect resolution.

**F-11 (No Phase 3 amendment authorization exists).** No document in the repository
authorizes modification of frozen Phase 3 hash behavior. The specification's stated
resolution for F-04 is prohibition and identity-ineligibility, not modification; the
week-end inspection explicitly left the containment-vs-amendment disposition as a human
decision point (§23.1).

**F-12 (No live/production exposure).** The repository contains no broker connectivity,
the live-execution boundary is deny-by-default with an empty human-only token registry
(week-end inspection §19; `paper/evaluation.py`), and no production dataset artifacts are
tracked in the repository. Nothing in the current system executes trades or serves
production traffic.

**F-13 (Adjacent dead code, noted for completeness — NOT part of H-1).**
`StrategyDataValidator.verify_no_dataset_mutation()` (frozen
`src/data_engine/strategy/validation.py:260-267`) computes
`dataset.to_hash() if hasattr(dataset, 'to_hash') else str(id(dataset))`; `Dataset`
defines no `to_hash`, so the branch degrades to memory-address identity. The method has
zero callers. It is a frozen-file latent weakness of a different class (non-wall-clock)
and is recorded here only so that any future amendment program inventories it; it does
not affect this decision.

**F-14 (Defect family).** F-04 is not isolated: `ProvenanceRecord.to_hash()` is
contaminated by `retrieval_timestamp` (F-05, per `HASH_FORENSIC_AUDIT.md` and spec §2.4
"CONTAMINATED — hash differs on +365d"; production always sets it to `datetime.now(UTC)`
at `ingestion.py:188`), and `DatasetVersion.created_at` carries a
`default_factory=_now_utc` (spec §2.4 class POTENTIAL). All are prohibited from Phase 4
identity (`pit/hashing.py:50-57`). Any amendment decision must therefore address scope
(single field vs. family), not just `Candle.to_hash()`.

**F-15 (Report verdict context).** The week-end forensic inspection's overall verdict was
READY_WITH_FINDINGS with 0 critical and 1 HIGH finding (H-1, pre-existing and adjudicated),
explicitly stating that no security, frozen-contract, autonomy, or live-boundary defect
was introduced by the construction run, and that H-1's disposition was left to human
review. This record is the analysis that inspection called for.

---

## 3. Defect Mechanism

### 3.1 The contaminated construction path

The relevant source, quoted exactly from `src/data_engine/schemas.py` at HEAD:

```python
def _now_utc() -> datetime:                       # schemas.py:61-62
    return datetime.now(UTC)

class Candle(BaseModel):                          # schemas.py:65
    ...
    provider_timestamp: Optional[datetime] = Field(default_factory=_now_utc)  # :84

    def to_hash(self) -> str:                     # schemas.py:130-133
        """Return a SHA-256 hash of this candle's contents."""
        data = self.model_dump_json()
        return hashlib.sha256(data.encode()).hexdigest()
```

`to_hash()` is a whole-model hash: `model_dump_json()` emits every field, and SHA-256 is
computed over the serialized bytes. `provider_timestamp` is an **audit-arrival** field —
its intent is to record when the provider delivered the candle — but it is equipped with
a default factory that reads the ambient wall clock at construction time. The compositional
consequence is that `to_hash()` is not a pure function of candle content: it is a function
of (content, construction-time wall clock).

### 3.2 The three construction modes

| Mode | Construction | `provider_timestamp` value | `to_hash()` behavior |
|---|---|---|---|
| (a) Omitted | `Candle(timestamp=…, open=…, …)` | `datetime.now(UTC)` via default factory | **NON-DETERMINISTIC across constructions** (the defective path; "unset" in all inspection reports means precisely this mode) |
| (b) Explicit value | `Candle(…, provider_timestamp=PT)` | `PT` | Deterministic — pure function of inputs |
| (c) Explicit `None` | `Candle(…, provider_timestamp=None)` | `None` (serialized `"provider_timestamp": null`) | Deterministic |

The defect is therefore exactly mode (a). Modes (b) and (c) are stable, which is why the
week-end probe's explicit-timestamp case measured 2/2 identical digests. Note that the
defect is invisible to any single-run smoke test — including the suite's only touch of the
method (`tests/test_pit.py:922`, `is not None`) — and becomes observable only under
repeated construction or cross-process re-derivation.

### 3.3 Measured manifestation (this analysis, HEAD a7fba96, 2026-10-07)

```
[UNSET]    provider_timestamp a = 2026-10-07 09:09:01.567897+00:00
[UNSET]    provider_timestamp b = 2026-10-07 09:09:01.618032+00:00
[UNSET]    to_hash() a = fec310147c18f178dd2b3e10fa4716d2a25e83eb9ca5a0cae7afab979d1ce575
[UNSET]    to_hash() b = d1556110e579256f8e70fef288f6981d364ff7f619d6d0c028078c136891d14d
[UNSET]    identical inputs -> identical hash? False
[EXPLICIT] to_hash() c = 884e2ce970db581ace0924c20b1da4e6f8b1d18431a62bdb8441ec865b84cd21
[EXPLICIT] to_hash() d = 884e2ce970db581ace0924c20b1da4e6f8b1d18431a62bdb8441ec865b84cd21
[EXPLICIT] identical inputs -> identical hash? True
VERDICT: F-04 REPRODUCED — unset path NON-DETERMINISTIC; explicit path deterministic.
```

Probe script: `/home/z/my-project/scripts/h1_f04_repro.py` (read-only; run with the
repository virtual environment; no repository file modified).

### 3.4 Why the defect exists (design origin)

Phase 3 predates the Phase 4A.1 identity-contract discipline. Its hash methods were
written as whole-model conveniences (`sha256(model_dump_json())`) without field
classification, while its schema legitimately carried audit-arrival metadata with
wall-clock defaults. The two design decisions are individually defensible and were never
contradictory **as long as the hashes were used only as informal fingerprints**; they
become a defect class the moment such a hash is used for identity, reproducibility, or
cross-process verification. That is precisely the boundary the Phase 4A.1 specification
drew: F-04/F-05 were declared identity-ineligible (spec §0.2, §2.4), and Phase 4 built an
independent, allowlist-based, type-tagged canonical identity contract
(`pit/hashing.py`, `pit/serialization.py`) that never reads the frozen methods. The defect
thus exists because a frozen historical contract encodes a pre-identity-discipline design,
and it remains because the freeze is honored.

### 3.5 What the defect is NOT

It is not a security vulnerability (no injection, privilege, or information-disclosure
surface — the leaked quantity is construction timing, and the hash is not used for
authentication); it is not data corruption (candle OHLCV content is unaffected); and it is
not a PIT-correctness defect (point-in-time semantics consume event/publication times,
which the PIT layer normalizes and hashes explicitly, never `provider_timestamp`). It is
exactly and only a **determinism/reproducibility defect of a frozen whole-model hash**,
bounded by containment to non-identity, non-reproducibility-critical uses.

---

## 4. Current Reachability Analysis

### 4.1 Complete call graph of `Candle.to_hash()` at HEAD

All edges verified by grep and direct source reading during this analysis:

```
FileDataProvider.fetch_candles()          provider.py:216-286
  └─ Candle(...) constructed WITHOUT provider_timestamp   provider.py:270-281
       → default_factory=_now_utc() stamps wall clock     schemas.py:84
MarketDataProvider.retrieve_raw()         provider.py:80-105
  └─ wraps fetch_candles(); adds its own wall-clock retrieval_timestamp  :92,:101
DataIngester.ingest()                     ingestion.py:40-156
  ├─ _compute_raw_hash(candles) → c.to_hash() per candle  ingestion.py:165-168   ← ONLY src call site
  │    ├─ feeds ProvenanceRecord.source_hash               ingestion.py:98
  │    └─ feeds Dataset.raw_data_hash                       ingestion.py:121
  └─ callers of ingest():
       ├─ ingest_from_file()              ingestion.py:195-219   (itself has ZERO callers)
       ├─ CLI                              cli.py:47-49           (advisory text only — no call)
       └─ tests                            (imports only; ZERO invocations of ingest())
```

No other `src/` module references `Candle.to_hash` except the containment comment at
`src/data_engine/pit/view.py:65` and the prohibition constant at `pit/hashing.py:51`.
The remaining `to_hash` definitions belong to other classes (`ProvenanceRecord`,
`StrategySpec`, `BacktestProvenance`) and are not H-1 subjects.

### 4.2 Layer-by-layer reachability verdict

| Layer | Consumers of `Candle.to_hash()` | Reachability | Evidence |
|---|---|---|---|
| L1 — Phase 4 identity (view_hash, sidecar_hash, identity_hash, eligibility_hash) | **NONE — prohibited** | **UNREACHABLE (proven)** | `pit/view.py:60-80` attribute-only reads; `pit/hashing.py:50-57,137-169` prohibition + fail-closed enforcement; SUB-25 bomb test `test_pit_view.py:1201-1231` over REAL Phase 3 candles; MUT-13 mutation detected; MUT-05/T-H02 wall-clock invariance |
| L2 — Frozen Phase 3 backtest provenance chain (dataset_hash → result_hash → BacktestProvenance) | **NONE — immune by construction** | **UNREACHABLE (proven)** | `backtest.py:608-627` field-explicit serialization excluding `provider_timestamp`; spec §10.3 measured invariance (provider_timestamp → 2030 leaves dataset_hash unchanged); week-end probe 3/3 deterministic |
| L3 — Phase 3 ingestion API (raw_data_hash / source_hash) | **ONE call site — dormant** | **REACHABLE BY INVOCATION, DORMANT IN SYSTEM** | `ingestion.py:165-168` via `provider.py:270-281` unset construction; zero src/test/CLI callers (F-9) |
| L4 — Test suite | **ONE smoke touch** | Non-load-bearing | `test_pit.py:914-922` asserts `is not None` only |

**Verdict: CONTAINED.** Every active identity, reproducibility, and PIT path in the system
provably avoids the defective method. The single production call site sits behind a public
but dormant API with no callers anywhere in the current codebase. If a future caller
activates Layer 3, the contaminated values are `raw_data_hash` and `source_hash` —
audit-class dataset fingerprint fields — never an identity input.

### 4.3 Epistemic discipline (per the governing instruction)

- "Zero call sites" is treated as a **reachability** statement only, not as evidence that
  the frozen contract is correct. The contract is defective regardless of call volume
  (F-3, §3.3).
- "Contained by prohibition" is treated as **suppression of use**, not elimination of the
  defect. The wall-clock injection remains fully present in the frozen bytes (F-4).
- "692 tests pass" is treated as evidence that containment has not regressed and that no
  active path depends on the defective behavior — nothing more (F-10).
- No modification of the frozen contract was made, considered, or recommended **in order
  to make a determinism test pass**. The absence of such a test is the honest consequence
  of the freeze, not a gap to be papered over.

### 4.4 The dormant-path precondition (registered for governance)

Any future activation of `DataIngester.ingest()` / `ingest_from_file()` — by new tooling,
a data-rehydration script, or an operator notebook — silently produces datasets whose
`raw_data_hash` and `source_hash` change on every re-ingestion of identical input files.
This does not corrupt the candles or any identity, but it makes raw-layer fingerprint
comparison across runs meaningless. This precondition is the concrete monitoring target
for containment adequacy (see §6, Residual Risk, and §12, flip triggers).

---

## 5. Historical/Compatibility Risk

**Frozen backtest provenance chain — NO historical reproducibility exposure.** The chain
that would be cited when reproducing a historical Phase 3 backtest
(`StrategySpec.to_hash` → `_compute_dataset_hash` → `_compute_config_hash` →
`compute_result_hash` → `BacktestProvenance.to_hash`) contains no `Candle.to_hash()` and
no `provider_timestamp` input (F-8). The week-end inspection measured all of these
deterministic across fresh subprocesses (3/3, and 2/2 for the explicit-candle case), with
stable digests recorded (`4579fde8…`, `35b9bcf0…`, `3920669d…`, `6007563d…`,
`4a1d0031…`, `ae3d7c67…`). Golden pins exist in the suite for `StrategySpec.to_hash()`
(T-H03, `test_pit_view.py:218-230`, digest `f056e51ba2e275f4…`) and for the SUB-18 file
manifest. A historical backtest re-run from frozen data therefore re-derives the same
hash chain.

**Raw-layer fingerprints — mechanism-level non-reproducibility, artifact-level UNVERIFIED.**
Any `raw_data_hash`/`source_hash` ever produced through the Phase 3 ingestion path is, by
mechanism (§3), a function of ingestion wall-clock time and cannot be re-derived from the
same input. The repository contains **no tracked dataset artifacts** (no persisted
datasets, no recorded raw-layer digests in any governing document reviewed), so there is
no in-repository object whose re-verification is broken by H-1. Whether any such digests
exist **outside** the repository (operator notebooks, prior sandboxes, archived runs) is
**UNVERIFIED** — no evidence either way is available to this analysis, and none is
invented here. This is precisely the class of evidence Option B would have to produce
before any amendment (§10, item 4).

**Amendment blast radius on current pins (if Option B were ever executed).** A change to
`Candle.to_hash()` or to the `provider_timestamp` default necessarily changes the
`src/data_engine/schemas.py` blob → the SUB-18 pin `9aa07004…` becomes stale and must be
re-recorded through an authorized manifest cycle; the AST-freeze assertions and the
week-end frozen-behavior probe baselines change; and the family scope decision (F-14:
F-05, `created_at`) determines whether sibling pins move in the same cycle or are
explicitly deferred with recorded rationale. No existing golden vector pins a
`Candle.to_hash()` value (T-H03 pins `StrategySpec` only), so no in-repo golden test
breaks — but that absence is also why old-vs-new compatibility is UNVERIFIED rather than
proven safe.

**Live/production compatibility — NONE.** No live system, no broker code, no production
dataset store exists (F-12); the live boundary is deny-by-default with an empty registry.
There is no production compatibility surface to damage today.

---

## 6. Option A — Containment

**Definition.** KEEP THE FROZEN PHASE 3 CONTRACT UNCHANGED. `Candle.to_hash()` remains
byte-for-byte frozen (including its `provider_timestamp` default factory and whole-model
serialization); the unset-timestamp construction path remains prohibited for any identity
use; Phase 4 identity continues to never depend on `Candle.to_hash()`; no new caller may
rely on the defective path; the suite continues to prove the prohibition (SUB-25, T-H02,
MUT-13, SUB-18); the defect remains registered as a known frozen-contract limitation; and
any future remediation proceeds only through a separately authorized Phase 3 amendment.

### BENEFITS
1. **Zero regression surface.** Nothing executable changes; the 692-test suite, all golden
   pins, the SUB-18 manifest, and every measured frozen-behavior digest remain valid
   without re-verification work.
2. **Freeze discipline preserved intact.** The repo's core governance asset — provable
   byte-integrity of frozen Phase 3 (11/11 blobs, 13/13 pins, zero touching commits) — is
   never voluntarily broken, and the precedent "frozen means frozen" is never diluted.
3. **Containment is already machine-enforced**, not aspirational: contract-level
   prohibition (ID-WC-01/02, direct and transitive), a bomb test over real Phase 3
   candles (SUB-25), and mutation-verified detection (MUT-13, MUT-05). Option A costs
   nothing new to maintain beyond keeping those gates green.
4. **The active system gains nothing from amendment.** Every identity, reproducibility,
   and PIT-correctness path that exists today is already independent of the defect (§4.2
   L1/L2). Option A accepts a limitation that has no current functional cost.
5. **Decision reversibility.** Choosing A now does not foreclose B later; the amendment
   path can be opened whenever its evidence burden is actually met. The converse
   (amending prematurely) is far harder to walk back.

### RISKS
1. **Dormant API reactivation (F-9/§4.4):** a future caller of the ingestion path gets
   silently unstable `raw_data_hash`/`source_hash`. Mitigation: this record registers the
   precondition; any ingestion reactivation must clear an authorized design gate that
   either fixes construction at `provider.py:270` (itself a Phase 3-layer change requiring
   authorization) or accepts and documents audit-class instability.
2. **Containment decay:** a future contributor could delete the prohibition comment, weaken
   SUB-25, or add a `to_hash()` call in new code outside the tested identity path.
   Mitigation: SUB-25/MUT-13 cover the identity path; code review and the week-end
   forensic cadence cover the rest; residual exposure is real but LOW.
3. **Known-defect register debt:** the defect persists indefinitely as documented
   governance debt. This is acceptable debt — it is priced, bounded, and monitored — but
   it must not be forgotten; H-1 stays OPEN precisely to carry it.
4. **Test-suite optics:** "all green" can be misread as "no defect" (F-10). Mitigation:
   this record states the distinction explicitly; governance documents already classify
   H-1 as pre-existing and adjudicated rather than resolved.

### RESIDUAL RISK
After Option A, the residual exposure is exactly: (i) hypothetical future misuse of the
defective path by code not covered by the identity-prohibition tests (LOW likelihood —
public API is dormant, prohibition is documented in three layers; MEDIUM impact if it
occurred — contaminated audit fingerprints, no identity impact); plus (ii) the UNVERIFIED
external-artifact question (§5), which Option A neither improves nor worsens. Overall
residual risk: **LOW**, with the single concrete watch-item being ingestion-path
reactivation.

### COMPATIBILITY IMPACT
None. No API, serialization, byte layout, manifest, golden vector, or test expectation
changes. Frozen Phase 3 remains interchangeable with `main@13fdc7e` semantics at the
contract level, as re-verified by this analysis (F-4, F-5).

### REPRODUCIBILITY IMPACT
Neutral for everything active: the frozen backtest chain remains deterministic and
re-derivable; Phase 4 identity remains cross-process deterministic (T-H05: true subprocess
verification, 5 OS processes). The **known limitation** stands: any fingerprint produced
by the dormant ingestion path is not re-derivable — this is the defect itself, accepted
and registered, not amplified by Option A.

### PIT IMPACT
None. Point-in-time correctness consumes event/observation/publication/effective/revision
times, normalized and hashed explicitly by the PIT layer; `provider_timestamp` is audit
class and prohibited from eligibility and identity hashes (`pit/hashing.py:50-57`).
`dataset_content_hash` reads only timestamp/OHLCV/volume attributes (`pit/view.py:60-80`).
Cutoff semantics, tie-breaking, and revision chains are untouched by H-1.

### DOWNSTREAM IMPACT
Current downstream consumers of `Candle.to_hash()`: none active (§4). Downstream
consumers of the values it would contaminate (`raw_data_hash`, `source_hash`): none
active — these fields ride on `Dataset`/`ProvenanceRecord` objects but are not read by any
Phase 4+ module (datasets are consumed duck-typed by attribute access on candle
sequence). Future downstream designs must treat the frozen method as a non-identity
fingerprint at most, per the recorded prohibition.

### GOVERNANCE IMPACT
Option A keeps the governance chain unbroken: the freeze contract, the manifest regime,
the acceptance-matrix discipline, and the audit trail all remain exactly as verified. It
formalizes H-1 as a permanent-or-until-amended registered limitation with a named owner
(the human principal) and a defined re-open condition (§12). The cost is continued
attention: every future forensic cycle must keep re-verifying the three containment
layers, and every future phase plan must keep excluding the defective path.

---

## 7. Option B — Phase 3 Contract Amendment

**Definition.** AUTHORIZE A FUTURE, SEPARATELY-SPECIFIED AMENDMENT TO `Candle.to_hash()`
(and possibly its defect family). **This option MUST NOT be implemented now.** This
section defines only what would have to exist — with evidence — before any amendment
commit could be lawfully made. Nothing in this section is authorized by this document.

### 7.1 Mandatory pre-amendment evidence (all currently NOT STARTED / UNVERIFIED)

| # | Required evidence | Current status | Notes |
|---|---|---|---|
| 1 | Explicit human authorization record (named principal, dated, scope-bounded) | **ABSENT** | No such instrument exists in the repository (F-11) |
| 2 | Phase 3 contract amendment specification | **ABSENT** | Must fix scope: (i) replace `default_factory` only; (ii) make `to_hash()` field-explicit; (iii) full family (F-04 + F-05 + `created_at`); (iv) deprecate-and-parallel approach. Each has different blast radius |
| 3 | Compatibility analysis (API, serialization, byte format, Pydantic dump changes) | **UNVERIFIED** | No analysis artifact exists; must not be invented |
| 4 | Historical hash impact analysis — inventory of every persisted `Candle.to_hash()` digest anywhere (in-repo: **none found**; external: **UNVERIFIED**) | **UNVERIFIED** | Governs whether old values must remain re-derivable |
| 5 | Downstream cache/hash consumer inventory | Partially available (this record, §4: one dormant consumer; zero identity consumers) | Must be re-run at amendment time against then-current HEAD |
| 6 | Result reproducibility impact analysis | Partially available (frozen backtest chain proven immune, §5) | Amendment must prove it does not *break* this immunity |
| 7 | Dataset identity impact analysis | Partially available (Phase 4 identity independent, SUB-25) | Must re-prove at amendment time |
| 8 | Migration strategy (staged rollout, re-ingestion policy, consumer transition) | **ABSENT** | No consumers today; strategy still required for external unknowns |
| 9 | Old/new hash versioning strategy | **ABSENT** | Candidate designs (decision required, none chosen): explicit hash-version prefix (e.g., `c3h1.`/`c3h2.`), algorithm tag in payload, or field-list version constant. Must prevent silent old/new comparison |
| 10 | Golden vectors — old-form AND new-form, both directions | **ABSENT** | Old-form vectors must be captured BEFORE any code change (they are only derivable from the frozen implementation) |
| 11 | Regression tests (unset-path determinism becomes assertable post-amendment; cross-process stability; explicit/None modes preserved) | **ABSENT** | Adding them today would fail against the frozen contract — this is why they are deferred, not skipped |
| 12 | Independent forensic review by an agent other than the implementer | **ABSENT** | Required by the repo's own multi-AI governance pattern |
| 13 | Full regression (suite ≥ 692 green at the amendment commit) | **NOT APPLICABLE YET** | To be measured then |
| 14 | Reproducibility audit (≥ 3 fresh subprocesses, all frozen + amended methods) | **NOT APPLICABLE YET** | Extends the week-end frozen-behavior probe to the amended method |
| 15 | Final acceptance by the human principal | **ABSENT** | Terminal gate |
| 16 | New frozen manifest re-record (SUB-18 successor; FRZ-04 tamper test re-pinned; supersession entries per spec §12.1) | **ABSENT** | Must land in the same authorized cycle as the code change |

**Compatibility results are NOT invented here.** Items 3, 4, 8, 9, 10 are UNVERIFIED by
design: no evidence exists in the repository, and this record refuses to fabricate
favorable outcomes. The only established facts usable by a future amendment are the
in-repo ones: zero identity consumers, one dormant ingestion consumer, no golden vector
pinning a Candle digest, and the immune backtest chain.

### 7.2 Why Option B is not recommended now

1. **No authorization instrument exists** (F-11) — beginning amendment work now would be a
   governance violation, not merely a technical choice.
2. **The functional benefit is zero today** — every active path is already defect-free by
   construction (§4.2); the amendment would repair a path nobody uses.
3. **The evidence burden is unmet** — four of the sixteen items are UNVERIFIED and two
   require capturing old-form golden vectors that only exist while the contract is frozen.
4. **The family scope is undecided** (F-14) — a `Candle`-only fix that leaves F-05 and
   `created_at` untouched would reproduce the same governance cycle a second time.
5. **Material hash/reproducibility consequences** — any change to a frozen hash alters
   every future digest it produces; without the inventory of item 4, the blast radius is
   unknowable, which is exactly the condition under which frozen contracts must NOT be
   edited.

---

## 8. Decision Criteria Matrix

Summary table followed by per-criterion evidence blocks. Risk grades the H-1 exposure
under the recommended option (containment) unless stated otherwise.

| ID | Criterion | STATUS | RISK |
|---|---|---|---|
| D1 | Frozen contract integrity | **PASS** | LOW |
| D2 | Current reachability | **CONTAINED** | MEDIUM (latent API surface) |
| D3 | Historical reproducibility | **CONTAINED** (external artifacts: UNVERIFIED) | LOW |
| D4 | Identity determinism | **PASS** (Phase 4 identity; frozen method itself: defective by record) | LOW |
| D5 | Downstream hash compatibility | **UNVERIFIED** (no persisted consumers found; external unknown) | LOW (current) |
| D6 | PIT correctness | **PASS** | LOW |
| D7 | Security impact | **PASS** (none identified) | LOW |
| D8 | Current production/live impact | **PASS** (none — no live system exists) | NONE |
| D9 | Migration complexity (if amendment attempted) | **UNVERIFIED — assessed HIGH** | MEDIUM |
| D10 | Governance risk | **CONTAINED** under Option A; **HIGH under unauthorized amendment** | LOW (A) |

### D1 — Frozen contract integrity — PASS / LOW
**EVIDENCE:** 11/11 frozen strategy blobs blob-identical to `main@13fdc7e`
(`git log 13fdc7e..a7fba96 -- src/data_engine/strategy/` is empty); `Candle` region
(schemas.py lines 61-134) byte-identical between `13fdc7e` and `a7fba96` (direct diff of
`git show` extractions, this analysis); the only `schemas.py`-touching cycle commit
(`b100418`) confined to `ProviderConfig`/`EvidenceProvenance` re-export hunks; SUB-18
manifest re-verified 13/13 pins at HEAD (this analysis); zero Phase 3 contract amendments
authorized or performed.
**RISK:** LOW — the freeze is intact and machine-checked from three directions (blob IDs,
manifest pins, in-suite re-assertion).

### D2 — Current reachability — CONTAINED / MEDIUM
**EVIDENCE:** Phase 4 identity paths provably never invoke `Candle.to_hash()`
(`pit/view.py:60-80`; `pit/hashing.py:50-57,137-169`; SUB-25 bomb test
`test_pit_view.py:1201-1231`; MUT-13 detection). Frozen backtest chain immune
(`backtest.py:608-627` field-explicit; spec §10.3 measured; week-end 3/3). The single
`src/` call site (`ingestion.py:165-168`) is dormant: its only internal caller is the
uncalled `ingest_from_file()` wrapper; CLI is advisory-only; tests import but never
invoke. **Precision finding F-9**: the defective unset-construction path IS wired into
that dormant site via `provider.py:270-281`.
**RISK:** MEDIUM — not for what is reachable today (nothing active), but for the latent
public-API surface that any future code could activate without touching a prohibited
identity path.

### D3 — Historical reproducibility — CONTAINED (external: UNVERIFIED) / LOW
**EVIDENCE:** Frozen backtest hash chain re-derivable (week-end measured digests stable
3/3; T-H03/T-H04 golden pins in suite). No tracked dataset artifacts or recorded
raw-layer digests exist in the repository. Whether external artifacts persist
`raw_data_hash`/`source_hash` values is **UNVERIFIED** — no evidence available, none
invented.
**RISK:** LOW for everything the repository can see; the UNVERIFIED component is carried
as a named open question, and is Option B evidence item 4.

### D4 — Identity determinism — PASS / LOW
**EVIDENCE:** Phase 4 identity is determinism-by-construction: allowlist-based free
function `identity_hash()` with contract version, ordered fields, fail-closed validation
(`pit/hashing.py:172-264`), `provider_timestamp` prohibited directly and transitively
(ID-WC-01/02), wall-clock/RNG/PID exclusion (ID-WC-03, MUT-12), true cross-process
verification (T-H05, 5 OS processes), and sidecar ingestion-time invariance (T-H02,
MUT-05). The frozen `Candle.to_hash()` itself remains defective (F-3) — by record, not by
use: it is declared identity-ineligible (spec §2.4) and never enters identity.
**RISK:** LOW — the identity contract most stakeholders care about is sound; the frozen
method's defect is bounded by three machine-enforced prohibition layers.

### D5 — Downstream hash compatibility — UNVERIFIED / LOW (current)
**EVIDENCE:** In-repo downstream consumer inventory (this analysis, §4): zero active
consumers of `Candle.to_hash()`; one dormant consumer
(`DataIngester._compute_raw_hash`); zero consumers of its outputs. No golden vector pins
a Candle digest; SUB-18 pins files, not method outputs. External persistence of Candle
digests: **UNVERIFIED**. Consequently the compatibility consequences of a hypothetical
amendment cannot be established from available evidence.
**RISK:** LOW today (nothing to break); the grade would rise to HIGH the moment evidence
shows persisted historical digests — which is why the inventory is a mandatory
pre-amendment artifact.

### D6 — PIT correctness — PASS / LOW
**EVIDENCE:** `dataset_content_hash()` reads only timestamp/OHLCV/volume attributes and
never any frozen hash (`pit/view.py:60-80`); eligibility hashes exclude audit times by
mandate (`ELIGIBILITY_FIELDS`, `pit/hashing.py:273-316`); tie-breakers reject wall-clock
keys (TIE-04); cutoff boundary semantics are pinned by tests (T-P01/T-P02, MUT-14
mutation); PROH-LEG-01 prohibits wall clock in the view build path. Wall-clock
`provider_timestamp` cannot enter any PIT decision.
**RISK:** LOW.

### D7 — Security impact — PASS / LOW
**EVIDENCE:** The defect leaks only construction timing into a digest; the digest is not
used for authentication, authorization, or integrity enforcement anywhere (no consumer).
No injection surface, no secret handling, no privilege boundary is involved. The
week-end security scan independently found zero eval/exec/pickle/shell/network in `src/`
and zero secrets in history.
**RISK:** LOW — worst-case misuse would be a false "data changed" conclusion from
comparing two raw-layer fingerprints, an availability/audit-noise issue, not a compromise.

### D8 — Current production/live impact — PASS / NONE
**EVIDENCE:** No live execution path exists: the live boundary is deny-by-default with an
empty human-only token registry; no broker code exists; no production dataset store; no
external traffic. The system is a research/construction-stage codebase.
**RISK:** NONE today. This is the strongest practical argument that amendment urgency is
zero.

### D9 — Migration complexity — UNVERIFIED, assessed HIGH / MEDIUM
**EVIDENCE:** No migration is specified anywhere. Complexity drivers measured from the
evidence: family scope (F-14: F-04 + F-05 + `created_at`), old/new hash versioning
decision (§7.1 item 9, no design chosen), old-form golden vectors capturable only while
frozen (item 10), SUB-18 manifest re-record cycle, independent re-audit requirement, and
the UNVERIFIED external-artifact inventory. No compatibility results exist and none are
invented.
**RISK:** MEDIUM — not a present exposure, but an honest ceiling: any future amendment is
a multi-artifact governance program, not a code patch.

### D10 — Governance risk — CONTAINED under Option A / LOW
**EVIDENCE:** Under Option A the freeze regime, manifest discipline, and audit chain
remain exactly as independently verified; H-1 is carried as a registered, priced
limitation with a named decision owner. The governance risk of an UNAUTHORIZED or
premature amendment is HIGH: it would breach FRZ-class rules, invalidate the
READY_WITH_FINDINGS verdict basis, force a full re-verification cycle, and set a
precedent that frozen contracts bend under convenience.
**RISK:** LOW under the recommended option; HIGH under violation — hence the strict
authorization gating in §13.

---

## 9. Risk Matrix

Likelihood (of materialization within the next governance cycle) × Impact (if
materialized). "Mitigation" states what exists TODAY; nothing new is authorized by this
record.

| ID | Risk | Likelihood | Impact | Current mitigation / detection |
|---|---|---|---|---|
| RS-1 | Future Phase 4+ code invokes `Candle.to_hash()` for identity | LOW | MEDIUM (identity instability) | SUB-25 bomb test; MUT-13 mutation gate; ID-WC-01/02 fail-closed allowlists; forensic cadence |
| RS-2 | Dormant ingestion API reactivated; `raw_data_hash`/`source_hash` become silently non-reproducible | LOW | MEDIUM (audit fingerprint noise) | This record's registered precondition (§4.4); reactivation requires a design gate; no current callers |
| RS-3 | Persisted historical Candle digests exist externally and become unverifiable | UNVERIFIED | LOW-MEDIUM | None possible without evidence; Option B item 4 would resolve |
| RS-4 | Premature/unauthorized amendment breaks reproducibility and freeze precedent | LOW (gated) | HIGH | Authorization rule (§13); amendment evidence checklist (§10); independent review requirement |
| RS-5 | "Suite green" misread as "H-1 resolved"; containment vigilance decays | MEDIUM | LOW-MEDIUM | This record states the distinction (F-10, §4.3); H-1 stays OPEN in all registers |
| RS-6 | Sibling defects (F-05 `retrieval_timestamp`, `created_at`) treated as fixed because F-04 is discussed | LOW | LOW | All prohibited in Phase 4 identity (`pit/hashing.py:50-57`); family scope recorded (F-14) |
| RS-7 | Containment artifacts (prohibition comment, SUB-25, MUT gates) removed or weakened by future edits | LOW | MEDIUM | SUB-18 in-suite manifest pin; week-end forensic re-runs; mutation gate re-runs |
| RS-8 | Frozen dead code `verify_no_dataset_mutation` (`validation.py:260-267`, `str(id())` fallback) misleads future hash work | LOW | LOW | Recorded here (F-13); zero callers; amendment program must inventory it |

Aggregate residual risk under Option A: **LOW**, dominated by RS-1/RS-2 (both mitigated)
and RS-5 (attention risk). No CRITICAL or HIGH residual risk remains under containment.

---

## 10. Required Evidence for Amendment

This is the authoritative checklist for any future Option B authorization. An amendment
may not begin until every item is green and recorded. Items mirror §7.1 and add
acceptance criteria.

| # | Evidence artifact | Acceptance criterion | Status today |
|---|---|---|---|
| 1 | Human authorization record | Named principal, date, scope, explicit invocation of the amendment clause | ABSENT |
| 2 | Amendment specification | Scope decision (field default / serialization / family / parallel-hash), normative text, test plan | ABSENT |
| 3 | Compatibility analysis | Every public consumer enumerated and dispositioned; byte-format deltas stated | UNVERIFIED |
| 4 | Historical hash impact inventory | Complete list of persisted old-form digests (in-repo AND external operator attestation); re-derivability requirement decided | UNVERIFIED |
| 5 | Downstream consumer inventory | Re-run at amendment-time HEAD; includes dormant ingestion path disposition | PARTIAL (this record) |
| 6 | Reproducibility impact analysis | Proof that frozen backtest chain immunity survives the change (re-measured §10.3-style probe) | PARTIAL (pre-change baseline exists) |
| 7 | Dataset identity impact analysis | SUB-25-class proof re-run post-change | PARTIAL (pre-change baseline exists) |
| 8 | Migration strategy | Staged rollout with rollback; consumer transition; re-ingestion policy | ABSENT |
| 9 | Hash versioning strategy | Old/new digests never silently comparable (version prefix, tag, or field-list constant — chosen, not merely listed as candidates) | ABSENT |
| 10 | Golden vectors | Old-form captured BEFORE code change; new-form after; cross-checked both directions | ABSENT (old-form capture window is OPEN while frozen) |
| 11 | Regression tests | Unset-path determinism, explicit/None modes, cross-process stability — all assertable post-change | ABSENT (impossible pre-change against frozen contract) |
| 12 | Independent forensic review | Reviewer ≠ implementer; scope covers this checklist | ABSENT |
| 13 | Full regression | Suite green at amendment commit (baseline 692) | NOT APPLICABLE YET |
| 14 | Reproducibility audit | ≥ 3 fresh subprocesses; frozen AND amended methods deterministic | NOT APPLICABLE YET |
| 15 | Final human acceptance | Dated acceptance record referencing all artifacts above | ABSENT |
| 16 | New frozen manifest | SUB-18 successor recorded; FRZ-04 re-pinned; spec §12.1 supersession entries added | ABSENT |

**Sequencing note.** Item 10's old-form vectors and item 4's inventory can and should be
produced while the contract is still frozen (they are only derivable then). If the human
principal anticipates ever choosing Option B, capturing these two artifacts early is the
only pre-work that is both safe and valuable. It is NOT authorized by this record; it is
noted as a candidate for a future authorization.

---

## 11. Governance Consequences

**If Option A is adopted (recommended).** The repository enters a steady state in which
H-1 is a permanent registered limitation of the frozen Phase 3 contract. Consequences:
(i) every future forensic cycle must re-verify the three containment layers (SUB-25,
MUT-13/MUT-05, SUB-18) — they become permanent regression sentinels; (ii) every future
phase plan and design review must treat `Candle.to_hash()` as a non-identity,
non-reproducibility fingerprint, and any new design touching raw-layer fingerprints must
disclose the limitation; (iii) H-1 remains OPEN in the findings register with disposition
"CONTAINED — accepted limitation of frozen contract", reviewed at each week-end
inspection until either formally closed by human acceptance or superseded by an amendment;
(iv) the dormant ingestion API carries a standing reactivation precondition (§4.4);
(v) no test may ever be added that asserts unset-path determinism against the frozen
contract — such a test is only lawful AFTER an authorized amendment.

**If Option B is opened later.** The amendment becomes a first-class governance program
with its own authorization instrument, its own specification, and the §10 checklist as
its exit criteria. Consequences: (i) during the program, all other Phase 3-adjacent work
must pause to avoid moving baselines; (ii) the manifest regime must be re-recorded in the
same cycle as the code change; (iii) the precedent is bounded by the checklist — future
frozen-contract changes cite this program as the required process, preventing ad-hoc
erosion of the freeze; (iv) the independent-review requirement (item 12) preserves the
multi-AI separation the repository has used since Phase 4A.1.

**If neither decision is recorded (default drift).** The worst outcome is silence: H-1
stays nominally open, vigilance decays (RS-5), and the dormant API quietly becomes
load-bearing in some future tool without anyone connecting it to this analysis. This
record exists precisely to prevent that outcome by demanding an explicit human decision
as the next governance action.

**If the freeze is violated (unauthorized amendment).** Immediate consequences: breach of
the FRZ-class contract rules and of the authorization regime documented across the
governance record set; invalidation of the 11/11 blob-integrity and 13/13 manifest
verifications that underwrite the READY_WITH_FINDINGS verdict; mandatory full regression
plus independent re-audit plus manifest re-record before any further work; and a
governance incident record. The authorization state in §13 exists to make this path
unambiguous.

---

## 12. Recommended Decision

**RECOMMENDATION: OPTION A — CONTAINMENT.** Keep the frozen Phase 3 contract unchanged;
keep `Candle.to_hash()` byte-for-byte as it is; keep the unset-`provider_timestamp`
construction path prohibited from every identity use; keep Phase 4 identity independent
of all frozen Phase 3 hash methods; maintain the containment sentinels (SUB-25, T-H02,
MUT-13/MUT-05, SUB-18) as permanent regression gates; and register H-1 as a known
frozen-contract limitation under continuous review. H-1 remains **OPEN /
HUMAN-REVIEWED / CONTAINED** — explicitly NOT CLOSED.

**Explicit reasons (each independently sufficient; together decisive):**

1. **The defect lives inside a frozen historical contract.** Its bytes predate the
current cycle and are pinned by the manifest regime; editing it voluntarily breaks the
very property (11/11 blob integrity, 13/13 pins) that underwrites every verification
verdict issued for this repository.
2. **Changing it has potentially material hash/reproducibility consequences.** Every
future digest produced by the method would change; the external-artifact inventory that
would bound the blast radius is UNVERIFIED; old-form golden vectors exist only while the
contract is still frozen. Acting before this evidence exists is exactly the risk the
freeze exists to prevent.
3. **No Phase 3 amendment authorization currently exists.** Beginning such work without
a human authorization instrument would be a governance violation regardless of technical
merit (F-11, §13).
4. **Every active path is already defect-free.** Phase 4 identity is prohibited and
bomb-tested; the frozen backtest chain is immune by construction; PIT correctness never
touches the field; there is no live or production consumer (§4.2, D8).
5. **Zero call sites is not proof of correctness — and containment is not elimination.**
This record honors that distinction by keeping the defect registered and the finding
OPEN rather than converting containment into a silent closure (§4.3).

**Containment adequacy statement.** On the evidence examined, containment IS adequate
for the system as it exists today: all identity, reproducibility, and PIT paths are
provably independent of the defect, and the single production call site is dormant with
zero callers. The one condition under which this assessment would change is recorded
below; none of its triggers is present now.

**Conditions that would flip the recommendation to Option B (none currently met):**
- a requirement that `Candle.to_hash()` itself become a deterministic, identity-bearing
  function (e.g., dataset-level content addressing built on the frozen method);
- reactivation of the Phase 3 ingestion pipeline for reproducible datasets, making
  `raw_data_hash`/`source_hash` load-bearing (§4.4);
- evidence that persisted historical Candle digests exist externally and require stable
  re-verification (resolving the current UNVERIFIED item);
- a human directive to unify Phase 3 and Phase 4 hashing into a single versioned
  contract.

If any trigger materializes, the minimum required amendment process is the §10
checklist — sixteen evidence artifacts, sequenced so that old-form golden vectors and the
historical inventory are captured while the contract is still frozen.

---

## 13. Authorization State

This section is the authorization ledger of record for H-1 as of 2026-10-07. It restates
and fixes what may and may not proceed. **This document grants no authorization.**

| Authorization item | State | Notes |
|---|---|---|
| Phase 3 contract amendment (`Candle.to_hash()` or family) | **NOT AUTHORIZED** | Requires the full §10 evidence program plus an explicit human instrument |
| Frozen Phase 3 modification (any file/byte) | **NOT AUTHORIZED** | Freeze intact at HEAD; verified this analysis (F-4, F-5) |
| WP-2 | **NOT AUTHORIZED** | No scope defined in any governing document reviewed; any future authorization must be issued separately |
| WP-3 | **NOT AUTHORIZED** | Same — separate instrument required |
| WP-5 | **NOT AUTHORIZED** | Same — separate instrument required |
| Implementation of any kind under H-1 | **NOT GRANTED** | This is a decision-analysis record only |
| Test modifications related to H-1 | **NOT GRANTED** | Including — especially — determinism tests targeting the frozen contract |
| Commits / pushes / merges | **NOT GRANTED** | Read-only session; repository verified untouched (§ STOP verification) |
| H-1 closure | **NOT GRANTED** | Closure authority is reserved to the human principal (§14) |
| Live execution | **NEVER AUTHORIZED** | Standing boundary of the construction blueprint; deny-by-default gate; not subject to this record's discretion |

**NEXT GOVERNANCE ACTION: HUMAN DECISION REQUIRED** — accept Option A (containment,
H-1 remains OPEN/HUMAN-REVIEWED/CONTAINED) or open the Option B authorization process
(§10). No other action may proceed against H-1.

---

## 14. H-1 Closure Requirements

H-1 may be closed ONLY by the governing human principal, by one of exactly two recorded
paths. This document does not close H-1, and nothing in it may be read as closure.

**Path 1 — Closure by accepted containment.** The human principal records a dated
acceptance that containment is the permanent disposition. The closure record must
state: (a) that the defect is understood to REMAIN in the frozen contract (not fixed);
(b) the containment basis (this record's §4.2 evidence); (c) the standing obligations
(permanent sentinels SUB-25/T-H02/MUT-13/MUT-05/SUB-18; the §4.4 reactivation
precondition; the prohibition on unset-path determinism tests against the frozen
contract); and (d) the re-open triggers of §12. Status on closure:
CLOSED-AS-ACCEPTED-LIMITATION (known defect, contained, accepted).

**Path 2 — Closure by completed amendment.** The Option B program completes with all
sixteen §10 items green, the new manifest recorded, independent review passed, full
regression and reproducibility audits green, and final human acceptance issued. Status
on closure: RESOLVED-BY-AMENDMENT.

**Prohibited closures.** Closure by silence, closure by suite-green inference, closure
by call-site count, or closure by any agent acting without the human principal's
explicit instrument are all invalid and must be reversed if discovered.

---

## 15. Deferred Work

All items below are recognized, recorded, and **deliberately not performed**. Each
requires its own authorization instrument; none is authorized by this record.

1. **WP-2 — NOT AUTHORIZED.** No authorized scope exists in the governing documents
   reviewed by this analysis; any definition and authorization must be issued separately
   by the human principal.
2. **WP-3 — NOT AUTHORIZED.** Same condition as WP-2.
3. **WP-5 — NOT AUTHORIZED.** Same condition as WP-2.
4. **Option B pre-work (if ever chosen):** capture of old-form golden vectors and the
   external-artifact digest inventory while the contract is still frozen (§10 sequencing
   note). Safe and valuable — and still requiring separate authorization.
5. **Ingestion-path guard (test-only hardening):** a future authorized test commit could
   add a sentinel proving the dormant `DataIngester` path is not silently reactivated
   with unset-timestamp construction (§4.4). Not performed: it touches the test suite,
   which this read-only gate forbids.
6. **Week-end inspection queued corrections (unrelated to H-1, already deferred by that
   inspection):** M-1 dependency hygiene, M-2 local main ref alignment, M-3 stale §10.2
   manifest marker, M-4 feature-test depth, L-1 `src/audit.log` removal, L-2 file-handle
   hygiene, L-3 frozen-era test file rename. All wait on an authorized change window.
7. **Nothing in this list may be started as a side effect of any other work.** Each
   carries the same authorization gate as the amendment itself.

---

## 16. Final Decision Record

```text
H-1 STATUS:
OPEN

H-1 CONDITION:
KNOWN FROZEN-CONTRACT DEFECT

CURRENT CONTAINMENT:
Candle.to_hash() (src/data_engine/schemas.py:130-133) is wall-clock
contaminated via provider_timestamp default_factory=_now_utc (F-04,
schemas.py:84) when the field is omitted at construction; reproduced
first-hand at HEAD a7fba96 on 2026-10-07 (unset: fec31014… vs
d1556110… for identical OHLCV; explicit: 884e2ce9… == 884e2ce9…).
Containment is machine-enforced: Phase 4 identity prohibits the field
outright (pit/hashing.py:50-57,137-169, ID-WC-01/02), never invokes the
frozen method (pit/view.py:60-80), and is bomb-tested over real Phase 3
candles (SUB-25, test_pit_view.py:1201-1231) with mutation-verified
detection (MUT-13, MUT-05). The frozen backtest hash chain is immune by
construction (backtest.py:608-627; spec §10.3 measured; week-end probe
3/3). The single production call site (ingestion.py:165-168, fed by
unset construction at provider.py:270-281) is DORMANT: zero callers in
src, tests, or CLI. Frozen Phase 3 integrity verified intact at HEAD:
11/11 strategy blobs byte-identical to main@13fdc7e, Candle region
lines 61-134 byte-identical, SUB-18 manifest 13/13 pins match, zero
cycle commits touch frozen paths. Zero active identity, reproducibility,
or PIT consumers of the defect; no live or production system exists.

RECOMMENDED OPTION:
OPTION A — CONTAINMENT

PHASE 3 AMENDMENT:
NOT AUTHORIZED

WP-2:
NOT AUTHORIZED

WP-3:
NOT AUTHORIZED

WP-5:
NOT AUTHORIZED

IMPLEMENTATION AUTHORIZATION:
NOT GRANTED

LIVE EXECUTION:
NEVER AUTHORIZED

NEXT GOVERNANCE ACTION:
HUMAN DECISION REQUIRED
```

---

## Appendix A — Evidence Register

Primary evidence examined by this analysis at HEAD
`a7fba96433b3858f49e0c96a113332f11078bbc8`, branch
`phase-4a/4a1-architecture-correction`, on 2026-10-07. All citations are file:line as
they exist at that commit.

| # | Evidence | Location | Verified by |
|---|---|---|---|
| E1 | `provider_timestamp` default factory | `src/data_engine/schemas.py:84` (with `:61-62`) | Direct read |
| E2 | `Candle.to_hash()` whole-model hash | `src/data_engine/schemas.py:130-133` | Direct read |
| E3 | First-hand F-04 reproduction digests | `scripts/h1_f04_repro.py` output (this session) | Runtime measurement |
| E4 | Week-end subprocess reproduction | `ZAI_WEEK_END_FULL_FORENSIC_INSPECTION.md` §6.3, §20 | Prior measured report |
| E5 | Historical CONTAMINATED classification | `HASH_FORENSIC_AUDIT.md` (lines 15-26, 47, 228-293) | Direct read |
| E6 | F-04 registered, disposition identity-ineligible | `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` §0.2 (line 57), §2.1 (line 230), §2.4 (line 258), §10.3 (lines 1263-1267) | Direct read |
| E7 | Design-lock measurement of divergence | `PHASE_4A1_DESIGN_LOCK_RECORD.md:352` | Direct read |
| E8 | Phase 4 prohibition constant | `src/data_engine/pit/hashing.py:50-57` | Direct read |
| E9 | Fail-closed allowlist enforcement (direct + transitive) | `src/data_engine/pit/hashing.py:137-169, 172-264` | Direct read |
| E10 | `dataset_content_hash()` attribute-only reads + prohibition text | `src/data_engine/pit/view.py:60-80` (text at :65) | Direct read |
| E11 | SUB-25 bomb test over real Phase 3 candles | `tests/test_pit_view.py:1199-1231` | Direct read |
| E12 | MUT-13 / MUT-05 mutation coverage | `scripts/mutation_gate.py:112-140, 285-300` | Direct read |
| E13 | Immune backtest dataset hash | `src/data_engine/strategy/backtest.py:608-627` (used at :194) | Direct read |
| E14 | T-H03 golden pin (StrategySpec) | `tests/test_pit_view.py:216-230` | Direct read |
| E15 | SUB-18 in-suite manifest re-assertion | `tests/test_pit_view.py:1011, 1044` | Direct read |
| E16 | Only src call site of `Candle.to_hash()` | `src/data_engine/ingestion.py:165-168` (outputs at :98, :121) | Grep + read |
| E17 | Unset candle construction in provider | `src/data_engine/provider.py:270-281` (method `fetch_candles` at :216; wall-clock `retrieve_raw` metadata at :101) | Direct read |
| E18 | Dormancy of ingestion path | `ingest_from_file` `ingestion.py:195-219`; CLI advisory `cli.py:47-49`; zero test invocations (grep) | Grep + read |
| E19 | Suite's only touch of the method (smoke) | `tests/test_pit.py:914-922` | Direct read |
| E20 | Frozen blob integrity | `git log 13fdc7e..a7fba96 -- src/data_engine/strategy/` empty; Candle region 61-134 diff-empty vs `13fdc7e` | Git commands |
| E21 | SUB-18 manifest 13/13 pins | `PHASE_4A1_IMPLEMENTATION_RECORD.md` §3 (lines 54-66) vs `sha256sum` at HEAD | Runtime re-verification |
| E22 | Dead-code adjacent pattern | `src/data_engine/strategy/validation.py:260-267` (zero callers) | Grep + read |
| E23 | Ground truth (HEAD/branch/tree) | `git rev-parse HEAD`; `git branch --show-current`; `git status --porcelain=v1` | Git commands |
| E24 | Test suite state | Week-end inspection §7 (692/692/0/0/0/0) — reported; not re-run in this read-only session | Prior measured report |

**Read-only attestation.** During this analysis: no repository file was created,
modified, staged, committed, pushed, or merged; no test was modified or executed against
the suite; the only artifacts produced live outside the repository
(`/home/z/my-project/download/H1_FORMAL_DECISION_ANALYSIS.md` and
`/home/z/my-project/scripts/h1_f04_repro.py`); runtime probes imported the package only
and wrote nothing (imports create gitignored `__pycache__` only). Final repository state
verification is recorded in the session log accompanying this record.



