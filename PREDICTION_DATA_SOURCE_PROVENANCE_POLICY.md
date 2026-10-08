# PREDICTION DATA-SOURCE & PROVENANCE POLICY

```text
Document Type:  Governing policy (data acquisition / provenance)
Phase:          PRED (Prediction & Crash Intelligence) — closure cycle
Authority:      B — CURRENT SUPPORTING (policy companion to the
                authoritative prediction spec)
Status:         CURRENT
Version:        1.0.0
Last Updated:   2026-10-08
Companion Spec: AI_TRADING_LAB_PREDICTION_CRASH_INTELLIGENCE_SPEC.md §7
                (data policy)
Implementation: src/data_engine/prediction/datasets.py,
                src/data_engine/prediction/quality_gates.py,
                src/data_engine/prediction/source_registry.py
```

---

## 1. Policy Statement

No dataset enters evaluation without an immutable manifest, a passed
quality-gate report, a declared epistemic state, and — for empirical
claims — a human-approved source. Synthetic fixtures are legal for
deterministic contract testing and ILLEGAL as empirical evidence.
These rules are enforced as code; this document is their human-readable
record.

## 2. Dataset Epistemic States

| State | Meaning | May back empirical claims? |
|---|---|---|
| `SYNTHETIC` | Deterministic fixture with declared generator + seed | NEVER |
| `REAL_UNVERIFIED` | Real acquisition claim without complete verification evidence | NO |
| `REAL_VERIFIED` | Complete verification chain (checksum + provenance + quality + approved source + coverage) | YES |
| `INSUFFICIENT` | Real but below the 5-year minimum coverage | NO (CRISIS_SAMPLE_INSUFFICIENT stands) |
| `INVALID` | Failed verification — refused, never repaired in place | NO |

State transitions are one-way and evidence-driven:
- `SYNTHETIC` can never be promoted (a checksum match on synthetic
  content proves only fixture integrity).
- `REAL_UNVERIFIED` → `REAL_VERIFIED` requires ALL of: matching
  content checksum, complete provenance, declared license, passed
  quality report, human-approved source.
- Any hard failure on a `REAL_VERIFIED` claim demotes to `INVALID`
  (declared-verified without evidence demotes to `REAL_UNVERIFIED`).
- Real datasets below 5 verified years read `INSUFFICIENT`.

## 3. Manifest Requirements (every dataset, no exceptions)

`dataset_name`, `source_name`, `source_version`,
`acquisition_timestamp` (logical, caller-supplied — never wall-clock),
`coverage_start/end`, `symbol`, `exchange` (where applicable),
`timezone`, `frequency`, `corporate_action_treatment`,
`adjustment_policy`, `missing_data_policy`, `revision_policy`,
`license_basis`, `provenance_metadata`, `content_checksum`,
`row_count`, `data_state`. The manifest hash (`preds.`) IS the
immutable dataset identifier — any field change is a new dataset.

## 4. Quality Gates (QG-01..QG-16, all deterministic)

Timestamp ordering; duplicate timestamps; missing intervals
(frequency-aware tolerance); impossible OHLC relationships;
negative/invalid prices; invalid volumes; timezone consistency;
future timestamps (acquisition bound); discontinuities; symbol
identity mismatch; dataset coverage gaps; corporate-action
consistency (split-like jump detection under adjusted policies);
revision contamination; accidental look-ahead (evaluation cutoff);
dataset checksum mismatch; provenance incompleteness.

Every failure yields an explicit refusal state (`INVALID`, or
`DATA_INSUFFICIENT` for coverage-class findings) with affected-row
indices. Data is never silently repaired in a way that changes its
epistemic status.

## 5. Source Governance

- Every source is DECLARED in the registry with license basis,
  coverage, granularity, expected limitations, revision and
  corporate-action behavior, provenance mechanism, verification
  status, and approved usage scopes.
- **Source approval is a HUMAN DECISION** (mandate §18.1). AI/agent
  approvals are structurally rejected; a source cannot enter the
  registry above UNVETTED without a recorded human approval.
- Usage authorization is fail-closed: approved status AND explicit
  scope membership (`contract-testing` / `empirical-evaluation` /
  `production-ingestion`).
- **No credentials in the repository.** The registry schema
  (`extra="forbid"`) structurally prevents credential fields.
  Credentials, when a source requires them, enter only via
  environment variables (`DATA_SOURCE_CREDENTIAL_<SOURCE>`) read at
  acquisition time by a human-approved acquisition runner, and are
  never committed, logged, or hashed.

## 6. Candidate Source Matrix (RECOMMENDATION — no approval implied)

| Source | Type | License basis | Coverage | Key limitations |
|---|---|---|---|---|
| stooq-daily-ohlcv | archive-download | UNKNOWN — public archive terms to confirm | multi-decade daily OHLCV (major instruments, to verify) | corporate-action treatment per symbol must be verified; revision behavior undocumented |
| fred-macro-series | macro-api | public domain (verify per series) | macro series, daily–monthly | revisions published — vintage snapshots required for PIT truth |
| binance-public-klines | exchange-api | exchange ToS — verify | crypto pairs, 1m..1d, full history | crypto only; delistings exist |
| alpha-vantage-free-tier | vendor-api | vendor free-tier terms | equities daily, limited history | 25 req/day free tier; API key via env var only |
| yfinance-unofficial | unofficial-client | UNKNOWN — must be reviewed | equities daily OHLCV | unofficial, no contract; pin adjustment behavior |

All five candidates are registered UNVETTED with honest limitation
notes. The operator decision template below records what an approval
must state.

## 7. Approval Templates (HUMAN DECISIONS — never fabricated)

### 7.1 Data-source approval record

```text
Decision ID:        SRC-APPROVAL-<source_name>-<date>
Approver:           <named human>
Approver kind:      human
Target status:      APPROVED_FOR_TESTING | APPROVED_FOR_PRODUCTION
Approved scopes:    contract-testing | empirical-evaluation | production-ingestion
License basis:      <confirmed license text/reference>
Coverage verified:  <evidence reference>
Provenance:         <mechanism + acquisition procedure>
Recorded at:        <logical timestamp>
```

### 7.2 Dataset verification acceptance record

```text
Dataset manifest:   <preds. hash>
Computed state:     REAL_VERIFIED
Checksum evidence:  <recomputed == declared>
Quality report:     <predq. hash, passed>
Coverage:           <years> >= 5.0 minimum
Source approval:    <SRC-APPROVAL decision id>
Accepted by:        <named human>
```

## 8. Standing State

REAL_DATA_VALIDATION = BLOCKED. The repository contains zero verified
years of real market data; the acquisition framework, quality gates,
and refusal states are complete and tested (48 tests), idle until a
source is approved. No dataset will be downloaded, converted, or
"promoted" without the records above.
