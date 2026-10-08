# REAL DATA READINESS CONTRACT

**Document ID:** GOV-RDR-001 · **Version:** 1.0.0 · **Date:** 2026-10-09
**Status:** BLOCKED_ON_REAL_DATA (mandate §9 — never invented)
**Implements:** `src/data_engine/runtime/data_gate.py`

---

## 1. Pipeline Contract (mandate §9)

    DATA SOURCE (human approval)
      → INGESTION → VALIDATION → NORMALIZATION
      → TIMESTAMP VALIDATION → SYMBOL VALIDATION
      → CORPORATE ACTION POLICY → MISSING DATA POLICY
      → DUPLICATE POLICY → PIT VALIDATION → PROVENANCE
      → DATASET MANIFEST → REPLAYABILITY

## 2. Required Dataset Record (per dataset)

`dataset_id, source, acquisition_timestamp, market, symbols,
timeframe, coverage_start, coverage_end, timezone, adjustment_state,
missing_data_statistics, duplicate_statistics, quality_status,
pit_status, provenance, content_hash, epistemic_state`

Implemented as `DatasetReadinessRecord` (construction-validated:
coverage ordered, REAL_VERIFIED requires quality PASSED + PIT
VERIFIED). Registration is available via `RealDataReadiness.register`.

## 3. Hard Quality Gates (mandate §10 — implemented `validate_bars`)

missing timestamps · duplicate timestamps · non-monotonic timestamps ·
impossible OHLC relationships · invalid prices · negative volume ·
NaN · infinity · stale records · gaps · timezone inconsistency —
every rejection carries bar index + check + explainable reason.

## 4. Current State (honest)

- Verified real datasets in this repository: **0** (VERIFIED_YEARS = 0).
- Synthetic fixtures exist for tests only and can NEVER be promoted
  (Phase 4A.1 dataset governance: SYNTHETIC → REAL_VERIFIED without
  human-approved evidence is structurally rejected).
- `RealDataReadiness.report()` today: `datasets_registered = 0`,
  `gate = BLOCKED_ON_REAL_DATA`.
- Consequence: **DATA_READY = FALSE ⇒ PAPER_READY = FALSE** until an
  operator-approved real dataset passes the full pipeline above.

## 5. Operator Actions to Unblock

1. Select and approve a data source (human decision —
   PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md governs approval).
2. Acquire data; record the full §2 dataset record.
3. Run validation + quality gates + PIT verification + provenance.
4. Register the dataset; re-run the readiness gate.

This contract deliberately does NOT invent, synthesize, or promote
any data (mandate §9).
