# PHASE 0 EVIDENCE RE-AUDIT
**Date:** 2026-09-30
**Mode:** READ-ONLY
**Branch:** phase-4a/4a1-temporal-foundation

---

## Re-Audit of Previously Reported Phase 0 PASS

Each criterion is challenged independently. PASS requires concrete evidence, not design intent, branch location, or test existence.

---

## F-01: One Authoritative Identity Mechanism

**Claim:** Phase 0 has one authoritative identity mechanism.

**Evidence Reviewed:**
- `Candle.to_hash()` — uses `model_dump_json()` → SHA-256 (serializes ALL fields including `provider_timestamp`)
- `ProvenanceRecord.to_hash()` — uses `model_dump_json()` → SHA-256 (serializes ALL fields including `retrieval_timestamp`)
- `DatasetVersion` has `created_at` with `default_factory=_now_utc`
- No explicit allowlist exists for any entity

**Findings:**
- `model_dump_json()` serializes everything — it is NOT an allowlist, it is "serialize everything"
- `provider_timestamp` is a wall-clock audit field that enters identity via `Candle.to_hash()`
- `retrieval_timestamp` is a wall-clock audit field that enters identity via `ProvenanceRecord.to_hash()`
- No single authoritative mechanism exists — multiple mechanisms use different serialization strategies

**STATUS: FAIL**
- No authoritative identity mechanism exists
- Multiple hashing methods use different approaches
- Wall-clock fields contaminate identity hashes

---

## F-02: Positive Identity Allowlist

**Claim:** Phase 0 has a positive identity allowlist.

**Evidence Reviewed:**
- `Candle.to_hash()`: `self.model_dump_json()` — NO allowlist
- `ProvenanceRecord.to_hash()`: `self.model_dump_json()` — NO allowlist
- `DatasetVersion`: no `to_hash()` method
- `Dataset`: no `to_hash()` method

**Findings:**
- No entity in Phase 0 defines an explicit identity-field allowlist
- `model_dump_json()` is the opposite of an allowlist — it serializes all fields
- The Phase 4A.1 architecture gate explicitly documents this as FAIL

**STATUS: FAIL**
- No positive allowlist exists anywhere in Phase 0

---

## F-06: Canonical Serialization

**Claim:** Phase 0 has canonical serialization.

**Evidence Reviewed:**
- `Candle.to_hash()`: `model_dump_json()` — Pydantic's JSON serialization, not a project-defined canonical form
- No `canonical_serialize()` exists in Phase 0 (it exists in `pit/serialization.py` which is Phase 4A.1 untracked code)
- Pydantic's `model_dump_json()` does NOT guarantee:
  - Deterministic dict key ordering across Python versions
  - Float normalization (-0.0 → 0.0)
  - NaN/Infinity rejection
  - Naive datetime rejection

**Findings:**
- Phase 0 has NO canonical serialization mechanism
- The `canonical_serialize()` in `pit/serialization.py` is Phase 4A.1 untracked code, not Phase 0
- Pydantic serialization is not canonical by the project's own definition

**STATUS: FAIL**
- No canonical serialization in Phase 0
- Pydantic JSON serialization is not canonical

---

## F-11: Schema Version

**Claim:** Phase 0 schemas have a schema version.

**Evidence Reviewed:**
- `Candle` model: no schema_version field
- `Instrument` model: no schema_version field
- `ProvenanceRecord` model: no schema_version field
- `Dataset` model: no schema_version field
- `DatasetVersion` model: has `version` field (e.g., "v1.0.0") but this is a dataset version, not a schema version
- `__version__` in `src/data_engine/__init__.py` — this is package version, not schema version

**Findings:**
- No schema_version field exists on any Phase 0 model
- Package version ≠ schema version
- Dataset version ≠ schema version

**STATUS: FAIL**
- No schema version mechanism exists in Phase 0

---

## F-13: Hash Algorithm Version

**Claim:** Phase 0 has a hash algorithm version.

**Evidence Reviewed:**
- `Candle.to_hash()`: `hashlib.sha256(data.encode()).hexdigest()` — no version identifier
- `ProvenanceRecord.to_hash()`: `hashlib.sha256(data.encode()).hexdigest()` — no version identifier
- No `hash_algorithm` field anywhere
- No versioned hash prefix (e.g., "sha256:...")

**Findings:**
- SHA-256 is used but no algorithm version is declared
- If SHA-256 is replaced with SHA-3 in the future, existing hashes cannot be distinguished from new hashes
- No versioned hash format exists

**STATUS: FAIL**
- No hash algorithm version exists in Phase 0

---

## F-18: Different Inputs → Different Identity

**Claim:** Phase 0 guarantees different inputs produce different identities.

**Evidence Reviewed:**
- `Candle.to_hash()`: deterministic for same input (SHA-256 property)
- `ProvenanceRecord.to_hash()`: deterministic for same input
- Collision resistance is a property of SHA-256, not of the implementation

**Findings:**
- SHA-256 collision resistance is assumed, not proven for this application
- The implementation does NOT add any uniqueness guarantees beyond SHA-256
- "Different inputs → different identity" is a probabilistic guarantee of SHA-256, not a deterministic guarantee of the implementation

**STATUS: UNVERIFIED**
- SHA-256 collision resistance is assumed
- No additional uniqueness mechanism exists
- Not independently verifiable without cryptanalytic evidence

---

## H-07: Filesystem Control

**Claim:** Phase 0 has filesystem control.

**Evidence Reviewed:**
- `DataStorage` class: in-memory storage with `_raw_store`, `_processed_store`, `_research_store`
- `FileDataProvider`: reads from CSV files using `os.path.join(self._data_dir, filename)`
- `DataIngester.ingest_from_file()`: convenience function using FileDataProvider
- No filesystem sandbox, no path restriction, no chroot, no container

**Findings:**
- `DataStorage` is in-memory only — no filesystem control relevant
- `FileDataProvider` reads from arbitrary filesystem paths
- No control exists over which files can be read

**STATUS: UNVERIFIED**
- In-memory storage has no filesystem attack surface
- FileDataProvider has uncontrolled filesystem access
- No filesystem control mechanism exists

---

## H-08: Path Traversal Prevention

**Claim:** Phase 0 prevents path traversal.

**Evidence Reviewed:**
- `FileDataProvider.fetch_candles()`: `filepath = os.path.join(self._data_dir, f"{instrument}_{timeframe.value}.csv")`
- `os.path.join()` does NOT prevent traversal — if `self._data_dir` is `../../etc`, the path becomes `../../etc/XAU/USD_1h.csv`
- No validation of `self._data_dir` against traversal patterns
- No `os.path.realpath()` or `os.path.abspath()` check
- No check that resolved path is within expected base directory

**Findings:**
- `os.path.join()` alone is NOT path-traversal prevention
- No containment logic exists in FileDataProvider
- If `config.endpoint` is set to an absolute path or path with `../`, traversal is possible

**STATUS: FAIL**
- No path traversal prevention exists in FileDataProvider
- `os.path.join()` is not a security control

---

## H-14: Fail-Closed Security

**Claim:** Phase 0 has fail-closed security.

**Evidence Reviewed:**
- `DataQualityBlockedError`: raised when DATA_QUALITY_BLOCKED is triggered
- `DataQualityGate`: blocks datasets that fail quality checks
- `QuarantineManager`: isolates invalid data
- `EvidenceProvenance`: UNKNOWN/SYNTHETIC data blocked from strong evidence claims

**Findings:**
- These are data-quality gates, not security fail-closed mechanisms
- "Fail-closed" means: if security mechanism fails, access is denied by default
- No security mechanism in Phase 0 has a "fail" mode that defaults to denied
- `DataQualityBlockedError` is a data quality exception, not a security boundary
- No authentication, authorization, or access control exists

**STATUS: FAIL**
- Data quality gates are not security fail-closed mechanisms
- No security boundary exists that fails closed

---

## H-16: Security Auditability

**Claim:** Phase 0 has security auditability.

**Evidence Reviewed:**
- `DataStorage._storage_log`: records store operations with timestamps
- `DataIngester._ingestion_log`: records ingestion operations
- `QuarantineManager._quarantine_log`: records quarantine events
- `ProvenanceTracker`: tracks dataset versions

**Findings:**
- These are operational logs, not security audit logs
- No security-relevant events are logged (no authentication attempts, no access control decisions, no authorization failures)
- `DataQualityBlockedError` is not a security event
- No audit trail for security-relevant operations exists

**STATUS: FAIL**
- Operational logs exist but no security audit trail
- No security events are logged

---

## J-05: Determinism Evidence

**Claim:** Phase 0 is deterministic.

**Evidence Reviewed:**
- 464 tests pass, many testing deterministic behavior
- `test_deterministic_calculations_not_overridden` in test_data_engine.py
- `test_result_hash_deterministic` in test_strategy_independent.py
- `test_deterministic_multiple_runs` in test_pit.py (untracked)
- `Candle.to_hash()` returns same value for same input
- `ProvenanceRecord.to_hash()` returns same value for same input

**Findings:**
- Determinism is tested and verified for many operations
- `datetime.now(UTC)` is used in some places (e.g., `DatasetVersion.created_at`, `ProvenanceRecord.retrieval_timestamp`) — these introduce non-determinism into object construction but NOT into hash computation (hashes are computed from field values, not from construction time)
- The `test_no_datetime_utcnow_in_source` test verifies no `utcnow()` calls remain (per test_pit.py backward compat test)

**STATUS: PASS**
- Determinism is verified by existing tests
- Hash computations are deterministic
- Object construction uses `datetime.now(UTC)` but this does not affect hash determinism

---

## L-06: Seed Evidence

**Claim:** Phase 0 has seed evidence.

**Evidence Reviewed:**
- `BacktestConfig` has `seed` parameter
- `test_strategy_independent.py` uses `seed=42` in tests
- QuantEngine uses seed for deterministic calculations

**Findings:**
- Seed is used in backtest configuration
- Determinism relies on seed for randomized operations
- No seed is used in Phase 0 data operations (Candle creation, Dataset construction) — these are fully deterministic without seed

**STATUS: PASS**
- Seed is used where randomization exists (backtest)
- Phase 0 data operations are deterministic without seed

---

## N-01: Authorization Evidence

**Claim:** Phase 0 implementation is authorized.

**Evidence Reviewed:**
- 2 commits on branch: 13fdc7e, 8f1570f
- No PR, no design review, no human approval record
- No authorization document citing Phase 0 implementation

**Findings:**
- Commits exist but no explicit authorization evidence
- "Branch location" is not authorization
- "Tests pass" is not authorization
- No human approval record exists for Phase 0

**STATUS: UNVERIFIED**
- No authorization evidence exists for Phase 0
- Commits are necessary but not sufficient for authorization

---

## N-02: Test Authorization Evidence

**Claim:** Phase 0 tests are authorized.

**Evidence Reviewed:**
- 62 tests in test_data_engine.py — committed in 13fdc7e
- 50 tests in test_redteam.py — committed
- 134 tests in test_quant.py — committed
- 82 tests in test_strategy.py — committed
- 39 tests in test_strategy_independent.py — committed
- 97 tests in test_pit.py — UNTRACKED, not committed

**Findings:**
- Committed tests have implicit authorization via commit
- test_pit.py is UNTRACKED — no authorization evidence
- No test authorization document exists

**STATUS: UNVERIFIED**
- Committed tests: implicit authorization via commit (not ideal but exists)
- test_pit.py: NO authorization evidence (untracked)

---

## N-03: Documentation Authorization Evidence

**Claim:** Phase 0 documentation is authorized.

**Evidence Reviewed:**
- `docs/strategy_engine_design.md` — committed, modified in working tree (UNAUTHORIZED change)
- `docs/strategy_engine.md` — committed
- `docs/quant_engine.md` — committed (Phase 2)
- 10 untracked .md files — NO authorization evidence

**Findings:**
- Committed docs have implicit authorization
- Modified design doc has UNAUTHORIZED working-tree change
- 10 untracked documentation files have NO authorization evidence

**STATUS: FAIL**
- docs/strategy_engine_design.md has unauthorized modification
- 10 untracked documentation files are unauthorized

---

## N-10: Working-Tree Accounting

**Claim:** Working tree is properly accounted for.

**Evidence Reviewed:**
- `git status --short` shows 2 modified files + 17 untracked items
- `git diff --stat` shows 2 files changed
- `git diff` shows exact changes
- `git ls-files --others --exclude-standard` shows all untracked files

**Findings:**
- Working tree has 2 modified files (unauthorized)
- Working tree has 17 untracked items (10 docs + 6 source + 1 test)
- No accounting document explains these artifacts
- No authorization exists for any working-tree change

**STATUS: FAIL**
- 2 unauthorized modifications
- 17 unauthorized untracked artifacts
- No working-tree accounting document exists

---

## SUMMARY: PHASE 0 EVIDENCE RE-AUDIT

| Criterion | Status | Reason |
|-----------|--------|--------|
| F-01: One authoritative identity mechanism | FAIL | Multiple mechanisms, no allowlist, wall-clock contamination |
| F-02: Positive identity allowlist | FAIL | No allowlist exists — model_dump_json() serializes everything |
| F-06: Canonical serialization | FAIL | No canonical serialization in Phase 0; Pydantic JSON is not canonical |
| F-11: Schema version | FAIL | No schema_version field on any model |
| F-13: Hash algorithm version | FAIL | No algorithm version declared; no versioned hash format |
| F-18: Different inputs → different identity | UNVERIFIED | SHA-256 collision resistance assumed, not proven |
| H-07: Filesystem control | UNVERIFIED | In-memory storage has no attack surface; FileDataProvider has uncontrolled access |
| H-08: Path traversal prevention | FAIL | os.path.join() is not prevention; no containment logic exists |
| H-14: Fail-closed security | FAIL | Data quality gates are not security fail-closed mechanisms |
| H-16: Security auditability | FAIL | Operational logs exist; no security audit trail |
| J-05: Determinism evidence | PASS | Tests verify determinism; hashes are deterministic |
| L-06: Seed evidence | PASS | Seed used where needed; Phase 0 data ops are deterministic |
| N-01: Authorization evidence | UNVERIFIED | No explicit authorization; commits exist but no approval record |
| N-02: Test authorization evidence | UNVERIFIED | Committed tests have implicit authorization; test_pit.py has none |
| N-03: Documentation authorization evidence | FAIL | Unauthorized design doc modification; 10 unauthorized untracked docs |
| N-10: Working-tree accounting | FAIL | 2 unauthorized modifications; 17 unauthorized untracked artifacts |

**OVERALL: FAIL**
Phase 0 has multiple evidence gaps. The previously reported PASS is not supported by concrete evidence for F-01, F-02, F-06, F-11, F-13, H-08, H-14, H-16, N-03, and N-10.

IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
