# REGRESSION BASELINE FORENSIC
**Date:** 2026-09-30
**Mode:** READ-ONLY

---

## 1. Exact Test Files Discovered

| # | File | Size | Discovered by pytest? |
|---|------|------|----------------------|
| 1 | tests/test_data_engine.py | 34,827 bytes | YES |
| 2 | tests/test_pit.py | 38,176 bytes | YES (UNTRACKED) |
| 3 | tests/test_quant.py | Unknown | YES |
| 4 | tests/test_redteam.py | Unknown | YES |
| 5 | tests/test_strategy.py | Unknown | YES |
| 6 | tests/test_strategy_independent.py | 62,522 bytes | YES |
| 7 | tests/test_strategy_corrupted_pre_rebuild.py | Unknown | NO (not discovered) |

---

## 2. Exact Test Count Per File

| File | Test Count | Class Count |
|------|-----------|-------------|
| test_data_engine.py | 62 | 22 classes |
| test_pit.py | 97 | 15 classes |
| test_quant.py | 134 | 21 classes |
| test_redteam.py | 50 | 10 classes |
| test_strategy.py | 82 | Unknown |
| test_strategy_independent.py | 39 | 10 classes |
| **TOTAL** | **464** | **88 classes** |

---

## 3. Exact Tests Discovered (test_data_engine.py)

### TestValidOHLCVDataset (2)
- test_valid_candle_creation
- test_valid_dataset_creation

### TestMissingCandle (1)
- test_missing_candle_detection

### TestDuplicateCandle (1)
- test_duplicate_candle_detection

### TestInvalidOHLC (3)
- test_high_less_than_low
- test_high_less_than_open
- test_low_greater_than_high

### TestOutOfOrderTimestamps (1)
- test_out_of_order_detection

### TestTimezoneInconsistency (2)
- test_timezone_in_datasets
- test_timeframe_preservation

### TestCorruptedRecord (2)
- test_nan_price_detection
- test_inf_price_detection

### TestAbnormalGap (1)
- test_large_gap_detection

### TestSyntheticDataLabeling (3)
- test_synthetic_provenance
- test_synthetic_cannot_be_strong_evidence
- test_synthetic_must_not_be_real

### TestRealDataProvenance (1)
- test_real_provenance_is_strong_evidence

### TestUnknownProvenanceBlocking (2)
- test_unknown_provenance_blocks_downstream
- test_unknown_cannot_be_strong_evidence

### TestDatasetVersioning (2)
- test_version_tracker
- test_new_version_does_not_overwrite

### TestRawDataImmutability (2)
- test_raw_cannot_be_overwritten
- test_raw_immutability_verified

### TestDataQualityBlocked (4)
- test_blocked_on_empty_dataset
- test_blocked_on_quarantined
- test_blocked_report
- test_no_llm_repair_allowed

### TestTimeframePreservation (4)
- test_daily_not_weekly
- test_h4_not_daily
- test_effective_lookback_difference
- test_timeframe_conversion_assertion

### TestUnavailableFields (2)
- test_none_volume_is_acceptable
- test_none_bid_ask_is_acceptable

### TestNaNInfinityDetection (2)
- test_positive_price_constraint
- test_zero_price_rejected

### TestProvenancePropagation (2)
- test_provenance_flows_to_datasets
- test_provenance_cannot_be_upgraded

### TestDownstreamRejection (2)
- test_quarantined_blocked_downstream
- test_storage_rejects_quarantined

### TestLLMBoundary (3)
- test_ema_is_deterministic
- test_llm_allowed_operations
- test_deterministic_calculations_not_overridden

### TestSecurity (3)
- test_sanitize_dataset_removes_code
- test_secret_protection
- test_immutable_provenance

### TestTimeframes (3)
- test_bars_per_year
- test_xau_usd_instrument
- test_instrument_registry

### TestQualityReport (2)
- test_report_generation
- test_report_is_usable_for_valid

### TestStorageSeparation (1)
- test_three_tiers_separated

### TestStorageRegression (4)
- test_retrieved_objects_are_separate_from_stored
- test_frozen_candle_mutation_rejected
- test_storage_isolation_deep_copy_behavior
- test_get_processed_returns_deep_copy

**Subtotal: 62 tests**

---

## 4. test_strategy_corrupted_pre_rebuild.py

**Status:** EXISTS but NOT ACTIVE

This file exists in tests/ but is NOT discovered by pytest as a test file. It is preserved as a historical artifact of the corrupted pre-rebuild state. It is NOT part of the 464-test baseline.

**Classification:** HISTORICAL_ARTIFACT

---

## 5. test_pit.py — Is It Part of the Baseline?

**YES.** test_pit.py is DISCOVERED and EXECUTED by pytest. It contributes 97 tests to the 464 total.

**Status:** UNTRACKED ARTIFACT — part of the baseline but without authorization.

**Classification:** CONTRIBUTES_TO_BASELINE but UNAUTHORIZED

---

## 6. Historical Artifacts

| Artifact | Classification | Reason |
|----------|---------------|--------|
| tests/test_strategy_corrupted_pre_rebuild.py | HISTORICAL | Preserved corrupted pre-rebuild file, not active in test suite |
| docs/strategy_engine_design.md (original line 2238) | HISTORICAL | Original "COMPLETE" status replaced by "NO-GO" in working tree |
| All committed files (13fdc7e, 8f1570f) | AUTHORIZED | Commit-backed |

---

## 7. Skipped Tests

**NONE.** No tests use `@pytest.mark.skip` or `@pytest.mark.skipif`. All 464 tests are active and passing.

---

## 8. Weakened Tests

**NONE DETECTED.** No evidence of test weakening. All tests appear to test their stated behavior.

**Caveat:** Without comparing to a known-good baseline of test code, "weakened" cannot be definitively ruled out. However, no evidence of weakening is present in the current codebase.

---

## 9. Deleted Tests

**NONE DETECTED.** All test functions in the current codebase are present and passing. No evidence of deleted tests.

**Caveat:** Without git history beyond 2 commits, "deleted" cannot be definitively determined. The only git history is:
- 13fdc7e: "finalize Phase 3 strategy backtest foundation"
- 8f1570f: "stabilize phase 3 strategy backtest engine"

No earlier history is available to compare against.

---

## 10. Is 464 the Correct Frozen Baseline?

**NO.** Here's why:

1. **test_pit.py is UNTRACKED** — it contributes 97 tests to the 464 total but has no git history, no authorization, and no design-gate approval. If test_pit.py is excluded, the baseline is 367 tests (464 - 97).

2. **test_pit.py is NEW** — it was created as part of the Phase 4A.1 implementation but is not committed. The 464 number includes tests that were never authorized.

3. **The "frozen baseline" claim is ambiguous:**
   - If "frozen" means "committed and unchanged": the baseline is 367 (excluding test_pit.py)
   - If "frozen" means "currently passing": the baseline is 464 (including test_pit.py)
   - The architecture gate document claims 464 is the frozen baseline, but this includes unauthorized tests

4. **The 464 number conflates authorized and unauthorized tests:**
   - 367 tests are committed (authorized via commit)
   - 97 tests are untracked (unauthorized)
   - 464 = 367 + 97

**Correct baseline classification:**

| Baseline | Count | Composition |
|----------|-------|-------------|
| Authorized (committed) | 367 | All tests except test_pit.py |
| Unauthorized (untracked) | 97 | test_pit.py only |
| Total passing | 464 | 367 + 97 |

**The "464-test frozen baseline" claim is INCORRECT if "frozen" implies authorization.** The correct authorized baseline is 367 tests.

---

## BLOCKER DECLARATION

**BASELINE_CONTAMINATION: YES**

The 464-test baseline includes 97 unauthorized tests (test_pit.py). Any claim that "464 tests pass" as evidence of Phase 3 completion is misleading because it includes tests that were never authorized.

**Correct statement:** 367 authorized tests pass. 97 unauthorized tests (test_pit.py) also pass but do not count toward the authorized baseline.

IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED
