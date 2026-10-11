# MASTER MARKET-DATA IMPORT RECORD

```text
Document Type:  Import decision + execution record (data governance)
Phase:          MASTER-IMPORT — operator master-bundle integration
Authority:      B — CURRENT SUPPORTING (evidence record for the
                data-governance chain; readiness authority remains
                PAPER_TRADING_READINESS_FINAL_REPORT.md)
Status:         CURRENT
Version:        1.0.0
Date:           2026-10-11
Branch:         feat/master-market-data-import (created from
                phase-4a/4a1-architecture-correction @ d49b822 —
                remote main = phase branch = d49b822 verified before
                any change; tree clean)
Operator Input: Master_Market_Data_for_ZAI.zip (uploaded 2026-10-11;
                bundle manifest MASTER_DATA_MANIFEST.json preserved at
                data/raw/master/_bundle/, sha256
                3ec9c30c2e3de12f110950702e551f5bac17f28a3c0a5926ac6909010af42a1f)
Governance:     PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md (§2
                epistemic states, §5 human-only source approval),
                REAL_DATA_READINESS_CONTRACT.md, platform
                registry/datasets architecture (Phase C precedent)
```

---

## 1. Mandate and Non-Negotiables

The operator supplied four master datasets and required: safe
integration on a feature branch, checksum verification before import,
originals preserved byte-for-byte, independent per-dataset inspection,
honest provenance, no promotion to REAL_VERIFIED from user supply,
regression tests, full suite + CI, an operational-feed verification
kept separate from historical CSVs, and an honest readiness report.

**Approvals respected, never re-asked:** the operator's prior
recorded decisions (H-1 ratification GOV-H1-002-RATIFY, CI/WP-12
WP-12-CI-ENABLE, BUG-008 residual GOV-B08-001, keyed-MAC GOV-KMC-001,
historical-data deferral GOV-HDD-001) remain in force and untouched.
Per the repository's own policy, approval-to-USE data is not and
cannot be a source approval — technical validation still ran in full.

## 2. Bundle Identity and Checksum Verification (before import)

| File | Declared SHA-256 (bundle manifest) | Computed at import | Verdict |
|---|---|---|---|
| Coins_Master.csv | `7a6b9eae03d7961b5869fddb8f95f660cec5a6b91f260eb0aa1f2f96aa8a4fc8` | identical | **MATCH** |
| Forex_Master.csv | `f0618be1b1c48c3f7eed22c5582eb8682a56134f682546f37419ed3c9140b4fd` | identical | **MATCH** |
| Stocks_Master.csv | `294df03dda5b21f05677b0bbf4f5efc7f3ba6d00c37e1c597c22c20a9a41aaae` | identical | **MATCH** |
| Metals_Master.csv | `6e921a9a2ecf911ec6a6da657387530be21f0847049d409af6c27ff76d0d879b` | identical | **MATCH** |

Bundle-declared acquisition timestamp: `2026-10-11T12:53:19.264928+00:00`
(used ONLY as the deterministic time reference for latest-candle
completeness evidence — never wall-clock). The bundle's own manifest
self-declares `USER_SUPPLIED_NOT_INDEPENDENTLY_SOURCE_VERIFIED`, which
this import honors to the letter.

## 3. Storage Decision (Git LFS analysis — explicit, not silent)

- **Git LFS is NOT supported by this repository:** no `git-lfs`
  binary available in the operating environment, no `.gitattributes`
  LFS tracking anywhere in history, and the CI workflow
  (`.github/workflows/ci.yml`, installed verbatim per WP-12) uses
  `actions/checkout@v4` **without any LFS retrieval step** — LFS
  pointer blobs would break CI's dataset tests by construction.
- **GitHub limits:** files above 50 MB warn and above 100 MB are
  rejected. `Coins_Master.csv` is 49,742,161 bytes (49.74 MB decimal)
  — under both thresholds.
- **Approved external artifact storage: none exists.** The repository
  has no approved external artifact store; session upload storage is
  neither durable, immutable, nor approved, and claiming it as the
  canonical home would be dishonest. No file was silently skipped,
  truncated, or replaced.
- **DECISION: all four raw files are committed byte-for-byte under
  `data/raw/master/`** (51.0 MB total), matching the repository's
  existing RAW-tier practice (`data/raw/*.csv`, 13 MB, same
  immutability discipline: ingestion only ever READS them). The
  operator's completion criterion — files actually present in the
  repository with CI observed — cannot be satisfied any other way.
- **Normalized/corrected outputs live separately** under
  `data/processed/master/` (gitignored, generated): transformation is
  timestamp re-formatting and symbol decomposition ONLY — no price
  value is ever altered, invented, or repaired. Metals violation rows
  are EXCLUDED by row index in the normalized view and listed
  verbatim in the manifest's `ohlc_violation_detail`. Lineage +
  checksums recorded in `data/processed/master/lineage.json`;
  everything is regenerable via `scripts/master_data_ingest.py`.

## 4. Per-Dataset Audit Findings (measured, never assumed)

### 4.1 Coins_Master.csv — Binance-style daily klines (ms epoch)

- 499,310 rows · 500 symbols · coverage 2019-02-19 → 2026-10-11 ·
  columns match the declared schema exactly.
- Quote-family inventory (suffix parse, documented table): USDT 234,
  TRY 124, BTC 35, USDC 30, EUR 23, FDUSD 22, ETH 12, ARS/BRL/ZAR/BNB/XRP
  20 — **0 symbols unparsed**.
- Integrity: duplicates=0 · non-chronology=0 · OHLC violations=0 ·
  non-positive=0 · NaN=0 · invalid timestamps=0 · negative volume=0.
- Timestamps: millisecond-epoch UTC (`Open_time`/`Close_time`); daily
  span 86,400,000 ms holds for 499,294 rows — **16 partial-span
  candles** (3h/8h spans, delisted USDC/TRY pairs' final partial
  candles: XLMUSDC, LINKUSDC, LTCUSDC, TRXUSDC, ZECUSDC, NEOUSDC,
  ATOMUSDC, ETCUSDC, ALGOUSDC, DOGEUSDC, ONTUSDC, BCHUSDC, STRAXUSDT,
  XTZTRY, ACMTRY, STRAXTRY) — recorded as evidence, not integrity
  failures.
- Listing/existence evidence: **0 quote-asset anachronisms** (USDT
  rows ≥ 2014-10-06, USDC ≥ 2018-09-26, FDUSD ≥ 2023-06-26, BTC-pair
  rows ≥ 2010-07-18 — all verified clean) and **0 pre-listing rows**
  against well-established base-asset dates (BTC, ETH, LTC, DOGE, SOL,
  XRP, ADA, BNB, TRX).
- Coverage shape: ~1000-day rolling window ending 2026-10-11 for most
  symbols; 16 symbols carry earlier partial histories (earliest
  2019-02-19 XLMUSDC); 18 symbols have <1000 rows (mid-window listing
  or missing candles — never fabricated); 16 internal day gaps (the
  partial-span discontinuities).
- **Latest candle: ALL 500 symbols' final candle (2026-10-11) closes
  at 23:59:59.999 UTC — AFTER the bundle's declared acquisition
  timestamp 12:53:19 UTC — so every final candle was still forming at
  acquisition. They are flagged `latest_candle_incomplete` and MUST be
  excluded from completed-candle research until re-acquired.**
- Calibration: BTCUSDT 2024-12-31 close 93,576.0 vs ~93,429 (0.16%);
  ETHBTC 2024-01-16 close 0.05999 vs ~0.0594 — 2/2 anchors within
  tolerance (calibration to real history, NOT proof of reality).
- **Classification: REAL_UNVERIFIED.**

### 4.2 Forex_Master.csv — USD-base rate series (NOT OHLC)

- 39,025 rows · 7 pairs (USD_EUR/GBP/JPY/CHF/AUD/CAD/NZD) · coverage
  2004-12-31 → 2026-10-09 (5,575 business days per pair).
- Semantics verified: **one exchange rate per pair per business day;
  quote direction USD_BASED (rate = quote currency per 1 USD)**;
  frequency: business-day daily (0 weekend rows; Friday→Monday gaps
  are weekend gaps); 72 missing-business-day gaps per pair over 21
  years recorded (holidays + gaps — evidence, never fabricated).
- Integrity: duplicates=0 · non-chronology=0 · non-positive=0 · NaN=0.
- Calibration: 7/7 end-2004 anchors within 5% of well-established
  reference rates (e.g. USD_EUR 0.73416 vs ~0.7341).
- **Schema compatibility verdict (recorded in the manifest): this is
  a RATE SERIES and is NOT compatible with the engine's Candle (OHLC)
  schema — fabricating OHLC from a single daily rate is FORBIDDEN and
  this pipeline never performs such a conversion.** Engine FX
  Instrument mapping is compatible via explicit base/quote
  decomposition (base=USD); any EURUSD-style convention requires an
  explicit documented inversion at use-site. Timezone: UNKNOWN
  (calendar dates, no fix-time metadata — UNVERIFIED, never invented).
- **Classification: REAL_UNVERIFIED (as a rate series).**

### 4.3 Stocks_Master.csv — periodic (monthly/quarterly) OHLCV

- 2,241 rows · 9 assets · coverage 1984-11-01 → 2026-10-09.
- **Actual per-asset frequency (measured, not assumed): MONTHLY for
  Amazon, DowJones, Google, Nvidia, Tesla; QUARTERLY for Apple,
  Microsoft, Nasdaq, SP500 (period-start dated bars: Dec/Mar/Jun/Sep).
  0/9 assets are D1-suitable — the file is NOT suitable for the
  engine's daily-candle strategies without explicit resampling
  governance.**
- Integrity: duplicates=0 · non-chronology=0 · OHLC violations=0 ·
  non-positive=0 · NaN=0.
- Missing periods: 0 under each asset's observed monthly/quarterly
  grid.
- Stale/repeated closes: 1–3 per asset — all at the **partial-period
  tail row** (final row 2026-10-09 is off the period-start grid, its
  close repeats the prior period's close with shrunken volume —
  carry-forward evidence; flagged `partial_period_tail`, excluded from
  completed-period research).
- Inception: all 9 assets' first bars on/after well-established
  inception dates (Microsoft carries the documented period-start
  caveat: 1986-03-01 bar covers through 1986-06-01 vs IPO 1986-03-13).
  No pre-inception fabrication evidence.
- Calibration: 3/3 anchors within tolerance (SP500 2024-12 ≈ 5,881.63;
  Apple ≈ 250.42; Nvidia ≈ 134.70).
- **Classification: REAL_UNVERIFIED.**

### 4.4 Metals_Master.csv — monthly OHLCV with 19 impossible rows

- 1,378 rows · 5 assets (Gold, Silver, Platinum, Palladium, Copper) ·
  coverage 1997-11-01 → 2026-10-09.
- **Integrity: 19 impossible-OHLC rows CONFIRMED (the previously
  observed violations) — reported VERBATIM with row indices, values,
  and reasons in `metals_master_manifest.json:ohlc_violation_detail`
  (Gold 4, Silver 2, Platinum 5, Palladium 6, Copper 3... counted by
  asset in the manifest; every row is either close>high or low>min
  range). Correction requires the ORIGINAL provider's data, which is
  NOT available (provider UNKNOWN) — this engine never guesses or
  silently rewrites prices. The dataset is therefore classified
  INVALID (failed verification — refused, never repaired in place,
  per provenance policy §2).**
- Frequency: MONTHLY (period-start bars) for all 5 assets — 0/5
  D1-suitable. Missing periods: ~40 (Gold/Silver/Copper), ~46
  (Palladium), ~56 (Platinum) months under each observed grid,
  including recent months (Gold is missing 2024-09 and 2024-12) —
  recorded, never fabricated.
- Partial-period tail rows on all 5 assets (same 2026-10-09
  carry-forward pattern as stocks).
- Calibration: Gold 2011-09 ≈ 1,620.4 vs ~1,650.75 and Silver ≈ 30.04
  vs ~30.19 — 2/2 anchors within tolerance (calibration only).
- **Classification: INVALID.**

## 5. Provenance (honest — UNKNOWN where unverifiable)

Recorded per-dataset in every manifest (`provenance` block):
provider=`UNKNOWN`, download URL=`UNKNOWN`, download timestamp=`UNKNOWN`,
licence=`UNKNOWN` (licence_verified=false), timezone=`UNKNOWN`
(coins: UTC by ms-epoch convention — the one field the format pins),
interval=declared per audit, symbol mapping=documented, approval
records=`NONE — user-supplied files carry approval-to-use, which is
NOT a source approval`, integrity status=`USER_SUPPLIED_NOT_
INDEPENDENTLY_SOURCE_VERIFIED`, bundle manifest sha256 pinned,
checksums verified=true. Promotion to REAL_VERIFIED additionally
requires (and is blocked on): identified provider, confirmed licence,
recorded SRC-APPROVAL human decision, the nine-stage verification
chain, and — for metals — provider-derived corrections.

## 6. Import Pipeline Implementation (supported interfaces)

- **New module `src/data_engine/platform/master_datasets.py`** —
  four schema-true audits (coins klines / forex rate series / stocks
  & metals periodic OHLCV), evidence-derived classification
  (SYNTHETIC / INVALID / REAL_UNVERIFIED — REAL_VERIFIED unreachable
  by construction), frozen Pydantic evidence models, deterministic
  manifests, registry ingestion with original-identifier provider
  mappings. Exported via the platform package.
- **Evidence script `scripts/master_data_ingest.py`** (committed,
  CI-runnable): checksum verify → audit → registry → manifests →
  normalized views + lineage. Bundle constants embedded for
  self-contained reproducibility.
- **Manifests committed** under `data/manifests/master/` (4 dataset
  manifests + import summary; deterministic, sorted keys, no
  wall-clock).
- **Regression tests `tests/test_master_datasets.py`** — 55 tests:
  schemas, ms-timestamp handling, duplicates, non-chronology (pre-sort
  — file order), OHLC constraints with row-level detail, missing
  periods, listing/existence dates, partial-span candles, incomplete
  latest candle vs acquisition timestamp, rate-vs-OHLC separation
  (fabrication forbidden), frequency/d1-suitability, partial-period
  tails, repeated closes, provenance honesty, manifest determinism,
  registry integration, committed-bundle integration (checksums +
  manifests re-verified from the committed files).
- **Existing-pipeline defect found and fixed (non-weakening):**
  `platform/datasets.py` computed per-symbol non-chronology AFTER
  sorting — vacuously zero, it could never fire; its unit test
  asserted `>= 0` (equally vacuous). Fixed to pre-sort measurement;
  the weak test replaced with a real `== 1` + INVALID assertion
  (F-24 replacement pattern, mapping documented in-file). **All four
  committed raw CSVs are chronological in file order — the regenerated
  legacy manifests were verified byte-identical before committing**
  (crypto/forex/metals/stocks_indices + import_summary all IDENTICAL).

## 7. Test and Verification Evidence

- Full suite after integration: **1,685 passed + 1 skipped**
  (baseline 1,630 + 55 new − 0 removed; the 1 pre-existing skip is
  documented). Determinism: repeated full-suite runs agree.
- Committed-bundle integration tests re-verify all four SHA-256
  checksums and re-audit the committed files against the committed
  manifests on every run (CI included).
- Frozen Phase 3 integrity: verified unchanged (13/13 manifest).
- Security: repository secret scan re-run clean (no credentials
  introduced; bundle contains none; manifests contain none).
- CI: the workflow runs the full suite + determinism + frozen
  verification on every push/PR (first platform runs recorded in the
  push cycle; this branch's PR triggers the same workflow).

## 8. Readiness Impact (honest, fail-closed)

This import does NOT and CANNOT flip any readiness gate:

- **REAL_DATA_READY remains FALSE** — VERIFIED_YEARS stays 0: zero
  REAL_VERIFIED datasets exist (3 REAL_UNVERIFIED + 1 INVALID now
  registered; 521 instruments registered with evidence-derived
  states). REAL_UNVERIFIED data may back RESEARCH/BACKTESTING
  eligibility per registry policy but never paper activation.
- **OPERATIONAL_FEED_READY remains FALSE** — historical CSVs are not
  an operational feed: no human-approved source exists, nothing is
  provisioned, and freshness/mapping/warm-up of a CURRENT feed are
  unproven by construction from static files. (Also: forex is a rate
  series, stocks/metals are monthly/quarterly, and the coins file's
  final candles are incomplete at acquisition — none of these can
  serve a daily operational bar feed.)
- **GOVERNANCE_READY unchanged** (H-1 ✓, CI/WP-12 ✓; open: PAT-rotation
  confirmation, keyed-MAC key provisioning, source approval).
- **PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY
  (unchanged).** LIVE NOT AUTHORIZED.

## 9. Honest Limitations

- Provider, licence, download URL and timezone are UNKNOWN for all
  four files; calibration anchors prove consistency with real history
  at a handful of dates, NOT authenticity of 541,954 rows.
- The 19 metals violations are quarantined, not corrected — correction
  requires original provider data that was never supplied.
- The coins file's 2026-10-11 candles (all 500 symbols) are incomplete
  by acquisition evidence; stocks/metals tails are partial periods.
- CI platform execution for THIS branch's PR had not been observed at
  the time this record was written (push depends on operator
  credential); the record will not claim otherwise.
