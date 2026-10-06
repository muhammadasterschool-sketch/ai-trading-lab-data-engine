# Phase 4A — Multi-Asset Point-in-Time Research Design Review

**Review Date:** 2026-09-28
**Review Mode:** DESIGN REVIEW ONLY — NO IMPLEMENTATION AUTHORIZED
**Repository:** `C:\Users\muham\ai-trading-lab-data-engine`
**Latest Commit:** `13fdc7e` ("finalize Phase 3 strategy backtest foundation")
**Branch:** `phase-4a/4a1-temporal-foundation`
**Phase 3 Baseline:** 367 passing tests, clean working tree at Phase 3 closeout
**Existing Phase 4A.1 Work:** Untracked `src/data_engine/pit/` (6 files) + `tests/test_pit.py` (949 lines)

**Status:** DESIGN REVIEW COMPLETE — NO IMPLEMENTATION AUTHORIZED

---

## 1. VERIFIED CURRENT ARCHITECTURE

### 1.1 Verified Repository Facts

The following are verified by direct source inspection at commit `13fdc7e`:

**Source modules (committed):**
- `src/data_engine/schemas.py` — Core Pydantic models: `Candle`, `Instrument`, `ProviderConfig`, `ProvenanceRecord`, `DatasetVersion`, `Dataset`, `ValidationResult`
- `src/data_engine/strategy/` — Phase 3 backtest engine: `backtest.py`, `schemas.py`, `execution.py`, `position.py`, `ledger.py`, `equity.py`, `conditions.py`, `metrics.py`, `provenance.py`, `validation.py`
- `src/data_engine/quant/` — Phase 2 Quant Engine: 12 modules (core, schemas, validation, registry, returns, moving_averages, momentum, volatility, trend, statistics, drawdown)
- `src/data_engine/storage.py` — Three-tier storage (RAW/PROCESSED/RESEARCH) with deep-copy
- `src/data_engine/data_blocked.py` — `DataQualityGate`, `DataQualityBlockedError`
- `src/data_engine/provenance.py` — `ProvenanceTracker`, `DatasetVersion` tracking
- `src/data_engine/instruments.py` — `InstrumentRegistry`, `ASSET_SEMANTICS` dict, symbol pattern validation
- `src/data_engine/ingestion.py` — `DataIngester`, `IngestionResult`
- `src/data_engine/evidence.py` — `EvidenceProvenance` enum (REAL, SYNTHETIC, SIMULATED, UNKNOWN), `EvidenceLabel`
- `src/data_engine/quant_boundary.py` — `LLMBoundary`, `CalculationType` enum
- `src/data_engine/provider.py` — `MarketDataProvider`, `ProviderFactory`

**Verified model properties:**
- All Pydantic models use `model_config = ConfigDict(frozen=True)` (verified)
- All datetime calls use `datetime.now(UTC)` (verified)
- Zero `os.popen()`, `datetime.utcnow()`, `eval()`, `exec()` in source (verified)
- Canonical serialization: pipe-separated fields, `.10f` floats, `<NULL>` for None
- `BacktestConfig` uses serialized string fields for cost/slippage (verified)
- `StrategySpec.to_hash()` uses canonical serialization per Section I of design doc
- `BacktestProvenance.compute_result_hash()` excludes runtime timestamps (verified)

**Asset class support (already in schemas.py):**
- `AssetClass` enum: CRYPTO, FX, EQUITY, INDEX, COMMODITY, METAL
- `ContractType` enum: SPOT, FUTURES, CFD, OPTION, UNKNOWN
- `Instrument` model: symbol, asset_class, base_asset, quote_asset, exchange, venue, contract_type, currency, provider_symbol

**Existing Phase 4A.1 PIT module (UNTracked — not committed):**
- `src/data_engine/pit/__init__.py` (`__version__ = "4.1.0"`)
- `src/data_engine/pit/temporal.py` — `TemporalDataType`, `TemporalSemantics` (event_time, observation_time, publication_time, effective_time, revision_time, ingestion_time)
- `src/data_engine/pit/availability.py` — `AvailabilityPolicy`, `PublicationControlledAvailability`, `RevisionAwareAvailability`
- `src/data_engine/pit/contract.py` — `TemporalContract`, `MissingFieldPolicy`
- `src/data_engine/pit/hashing.py` — `deterministic_hash()`, `deterministic_hash_bytes()`, `verify_hash_determinism()`
- `src/data_engine/pit/serialization.py` — `canonical_serialize()`, `SerializationError`
- `tests/test_pit.py` — 949 lines of tests for temporal foundation

### 1.2 Current Phase 3 Contract Summary

**BacktestConfig fields:** `initial_capital`, `cost_parameters_serialized`, `slippage_parameters_serialized`, `allow_short`, `execution_semantics`, `max_position_size`, `seed`, `execution_delay`, `max_exposure_pct`

**StrategySpec canonical hash field order:** `strategy_id|strategy_version|strategy_name|instrument|timeframe|entry_conditions_serialized|exit_conditions_serialized|position_sizing_serialized|stop_loss_pct|take_profit_pct|max_position_size|max_exposure_pct|required_indicators|allow_short|cost_parameters_serialized|slippage_parameters_serialized|execution_semantics|description|author|assumptions_serialized`

**Result hash formula:** `sha256(strategy_hash|dataset_hash|canonical_trades|canonical_equity|canonical_metrics|config_hash)` — runtime timestamps excluded

**Dataset hash:** Content-based using `model_dump_json()`, includes `evidence_provenance`

### 1.3 Design Document Integrity Observation

**Finding:** The final line of `docs/strategy_engine_design.md` reads `IMPLEMENTATION STATUS: COMPLETE — DESIGN LOCK PENDING FINAL REVIEW\r` (with trailing CR and checkmark character). The skill documentation requires the final line to be EXACTLY `IMPLEMENTATION STATUS: NO-GO — DESIGN LOCK PENDING FINAL REVIEW`. This discrepancy was introduced in commit `13fdc7e` which modified the design doc. This is a design document integrity concern, not a source code issue.

### 1.4 Existing Phase 4A.1 Design Decisions (Verified from Pit Module)

The untracked PIT module has already made these design decisions:
- **Temporal model:** 6 temporal fields (event_time, observation_time, publication_time, effective_time, revision_time, ingestion_time)
- **ingestion_time is metadata-only** — excluded from eligibility, hashes, and research identity
- **All timestamps UTC-normalized** — naive datetimes rejected
- **TemporalDataType:** OHLCV, ECONOMIC, NEWS, DERIVED
- **Availability policies:** PublicationControlledAvailability, RevisionAwareAvailability (declarative, immutable)
- **TemporalContract:** Required/eligible/non_eligible field lists, missing field policy, timezone requirement
- **Canonical serialization:** JSON-based with `sort_keys=True`, deterministic
- **Deterministic hashing:** SHA-256 of canonical bytes

---

## 2. PROPOSED MULTI-ASSET ARCHITECTURE

### 2.1 Architectural Principle: Asset-Class-Agnostic Core with Asset-Specific Extensions

The core design principle is that **no asset class should be able to assume it is the primary or default model**. The existing architecture already has a foundation (Instrument, AssetClass, ContractType), but it needs significant extension to support multi-asset PIT research.

**Proposed layering:**

```
Multi-Asset Research Platform
├── Shared Core (asset-class-agnostic)
│   ├── Instrument Identity & Lifecycle
│   ├── Temporal / PIT Semantics
│   ├── Calendar & Session Abstraction
│   ├── Venue / Exchange Registry
│   ├── Experiment Identity & Provenance
│   └── Canonical Serialization & Hashing
│
├── Asset-Class-Specific Extensions
│   ├── Equities Module
│   ├── Forex Module
│   ├── Futures Module
│   └── Extensibility Framework
│
└── Research Orchestration Layer
    ├── PIT View Construction
    ├── Point-in-Time Dataset Builder
    └── Experiment Identity Assembly
```

### 2.2 Rationale for Layering

The existing `Instrument` model in `schemas.py` already has the seeds of this architecture (asset_class, base_asset, quote_asset, contract_type, exchange, venue, currency). However, it conflates several concerns that must be separated:

1. **Identity** (what is this instrument, stable across time) vs **Specification** (how does it trade at a given time) vs **Data Model** (what data format does it use)
2. **Calendar** (when does it trade) vs **Contract** (what are its terms) vs **Venue** (where does it trade)
3. **Event time** (when did the market event occur) vs **Publication time** (when was it reported) vs **Effective time** (when did it become actionable)

### 2.3 Key Design Decisions

| # | Decision | Rationale | Impact |
|---|----------|-----------|--------|
| D1 | Shared core is asset-class-agnostic; no default asset class | Prevents stock-shaped assumptions from leaking into other asset classes | All new models must not assume equities as default |
| D2 | Instrument identity is separate from instrument specification | Identity persists across corporate actions and contract rollovers | Enables PIT universe tracking |
| D3 | Calendar/session is a configurable interface, not a hardcoded list | Different asset classes have different trading calendars | Enables 24/7, exchange-specific, and instrument-specific calendars |
| D4 | PIT metadata lives in sidecar records, not in existing Phase 3 models | Preserves legacy hash stability | Existing datasets remain valid |
| D5 | Experiment identity includes PIT snapshot hash, not just dataset hash | Same dataset at different PIT cutoffs produces different experiments | Prevents silent experiment equivalence |
| D6 | Futures continuous series and individual contracts are distinct instruments | They have different prices and trading behavior | Prevents roll leakage |
| D7 | Corporate actions create new instrument identity events, not data corrections | Preserves point-in-time integrity | Prevents survivorship bias |
| D8 | FX bid/ask spread and financing are explicit model parameters, not implicit | Different providers have different spread models | Prevents hidden assumptions |

---

## 3. SHARED VERSUS ASSET-SPECIFIC BOUNDARIES

### 3.1 Shared Core (Universal Fields)

The following fields belong in the shared core and are universal across all asset classes:

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| `instrument_identity` | InstrumentIdentity | Stable, immutable identifier for the instrument across its lifecycle | Yes |
| `asset_class` | AssetClass | Asset class category | Yes |
| `contract_type` | ContractType | SPOT, FUTURES, CFD, OPTION | Yes |
| `venue` | Venue | Exchange or market identifier | Yes |
| `base_currency` | str | Base currency of the instrument | Yes |
| `quote_currency` | str | Quote currency (where applicable) | Yes |
| `trading_currency` | str | Currency in which the instrument trades and settles | Yes |
| `price_precision` | int | Decimal places for price representation | Yes |
| `quantity_precision` | int | Decimal places for quantity representation | Yes |
| `timezone` | str | Primary timezone for trading sessions | Yes |
| `calendar_ref` | CalendarRef | Reference to the trading calendar | Yes |
| `effective_from` | datetime | When this specification becomes effective | Yes |
| `effective_to` | datetime | When this specification expires (None = permanent) | Yes |
| `data_source` | DataSource | Provenance identity for the data provider | Yes |

### 3.2 Asset-Specific Extensions

The following fields belong in asset-specific schemas:

**Equities-specific:**
- `isin` (International Securities Identification Number)
- `cusip` (Committee on Uniform Securities Identification Procedures)
- `listing_exchange` (primary exchange, may differ from venue)
- `share_class` (e.g., Class A, Class B)
- `corporate_action_history` (splits, dividends, symbol changes, delistings)
- `adjusted_price_method` (how adjusted prices are computed)
- `dividend_currency` (may differ from trading currency)
- `delisting_date` (if applicable)
- `point_in_time_universe_membership` (whether it was in the investable universe at any given date)

**Forex-specific:**
- `pair_convention` (direct/indirect/quoted)
- `base_currency_semantics` (what the base currency represents)
- `typical_spread_range` (min/max historical spread)
- `financing_rate_source` (how swap/financing rates are determined)
- `provider_symbol_mapping` (how the pair is named by each provider)
- `session_overlap_windows` (when major sessions overlap)
- `rollover_time` (daily rollover timestamp)
- `market_closure_weekend` (Friday close to Sunday open)

**Futures-specific:**
- `contract_month` (e.g., H25, M25, Z25)
- `expiry_date` (last trading day)
- `first_notice_date` (first notice day)
- `contract_multiplier` (dollar value per tick)
- `tick_size` (minimum price increment)
- `tick_value` (dollar value of one tick)
- `settlement_method` (cash vs physical)
- `settlement_price_source` (how settlement price is determined)
- `trading_session_metadata` (regular hours, extended hours, electronic session)
- `continuous_series_adjustment_method` (back-adjusted vs forward-adjusted vs ratio-adjusted)
- `rollover_policy` (explicit rules for when and how to roll)
- `primary_contract` (the most liquid contract in a series)

### 3.3 What NOT to Force into the Shared Core

The following must NOT be forced into the shared core:

- **Candle-only data model**: Not all asset classes produce OHLCV bars. Forex tick data, economic calendar events, and futures settlement reports have different structures.
- **Volume semantics**: Volume means different things across asset classes (share volume, tick volume, contract volume, none at all).
- **Bid/ask assumptions**: Not all instruments have bid/ask from all providers.
- **Trading session assumptions**: 24/7 crypto markets vs exchange-hours equity markets vs 24/5 forex markets require fundamentally different calendar models.
- **Corporate action handling**: Relevant for equities, not for forex or most crypto.
- **Contract rollover**: Relevant for futures, not for spot instruments.

---

## 4. REVISED PHASE 4A MODULE MAP

### 4.1 Proposed Module Structure

```
src/data_engine/
├── # Existing (unchanged, Phase 3)
│   ├── schemas.py                    # Core models (Candle, Instrument, Dataset, etc.)
│   ├── strategy/                     # Phase 3 backtest engine (frozen)
│   ├── quant/                        # Phase 2 quant engine (frozen)
│   ├── storage.py                    # Three-tier storage (frozen)
│   ├── data_blocked.py               # DataQualityGate (frozen)
│   ├── provenance.py                 # ProvenanceTracker (frozen)
│   ├── ingestion.py                  # DataIngester (frozen)
│   ├── evidence.py                   # EvidenceProvenance (frozen)
│   ├── instruments.py                # InstrumentRegistry (frozen)
│   ├── provider.py                   # MarketDataProvider (frozen)
│   ├── quant_boundary.py             # LLMBoundary (frozen)
│   ├── validation.py                 # DataValidator (frozen)
│   └── __init__.py                   # v0.1.0 (frozen)
│
├── # Phase 4A.1 — PIT Temporal Foundation (existing, untracked)
│   └── pit/
│       ├── __init__.py               # v4.1.0
│       ├── temporal.py               # TemporalDataType, TemporalSemantics
│       ├── availability.py           # AvailabilityPolicy, PublicationControlledAvailability
│       ├── contract.py               # TemporalContract, MissingFieldPolicy
│       ├── hashing.py                # deterministic_hash, deterministic_hash_bytes
│       └── serialization.py          # canonical_serialize, SerializationError
│
├── # Phase 4A — NEW MODULES (proposed, NOT IMPLEMENTED)
│   ├── multi_asset/
│   │   ├── __init__.py              # v4.0.0
│   │   ├── identity.py              # InstrumentIdentity, IdentityLifecycleEvent
│   │   ├── specification.py         # InstrumentSpecification, EffectiveDatedSpec
│   │   ├── venue.py                 # VenueRegistry, ExchangeSession
│   │   ├── calendar.py              # CalendarInterface, HolidayCalendar, SessionSchedule
│   │   ├── currency.py              # CurrencyRef, CurrencyPrecision
│   │   └── precision.py             # TickSize, TickValue, ContractMultiplier
│   │
│   ├── equities/
│   │   ├── __init__.py
│   │   ├── corporate_actions.py     # Split, Dividend, SymbolChange, Delisting
│   │   ├── universe.py             # PointInTimeUniverse, DelistedSecurity
│   │   ├── adjusted_prices.py      # AdjustmentMethod, AdjustmentChain
│   │   └── exchange.py             # EquityExchange, SessionCalendar
│   │
│   ├── forex/
│   │   ├── __init__.py
│   │   ├── conventions.py          # PairConvention, BaseQuoteSemantics
│   │   ├── spread.py               # SpreadModel, BidAskData
│   │   ├── financing.py            # FinancingRate, SwapAssumption
│   │   ├── provider_mapping.py     # ProviderSymbolMap, SymbolNormalization
│   │   └── session.py              # FxSession, RolloverPolicy
│   │
│   ├── futures/
│   │   ├── __init__.py
│   │   ├── contract.py             # FuturesContract, DatedContractSpec
│   │   ├── continuous.py           # ContinuousSeries, AdjustmentMethod, RolloverPolicy
│   │   ├── expiry.py               # ExpiryMetadata, LastTradingDay, Settlement
│   │   └── rollover.py             # RollEvent, RollBoundary, RollLeakageDetector
│   │
│   ├── temporal/                   # Extends Phase 4A.1
│   │   ├── __init__.py
│   │   ├── pit_view.py            # PitView, PitCutoff, TemporalQuery
│   │   ├── revision.py            # RevisionHistory, VersionedSnapshot
│   │   ├── event_time.py          # EventTime, PublicationTime, EffectiveTime
│   │   ├── timezone.py            # TimezoneNormalization, MissingTimestampPolicy
│   │   └── determinism.py         # DeterministicTieBreakers, OrderingPolicy
│   │
│   ├── calendar/                   # Extends the shared calendar concept
│   │   ├── __init__.py
│   │   ├── interface.py           # CalendarInterface, SessionDefinition
│   │   ├── registry.py            # CalendarRegistry, VenueCalendarMap
│   │   ├── holiday.py             # HolidayCalendar, ExceptionClosure
│   │   ├── versioning.py          # CalendarVersion, CalendarChangeEvent
│   │   └── schedule.py            # TradingSchedule, OvernightSession
│   │
│   ├── experiment/                 # Experiment identity and provenance
│   │   ├── __init__.py
│   │   ├── identity.py            # ExperimentIdentity, ExperimentHash
│   │   ├── provenance.py          # PitProvenance, ViewSnapshot, ApprovalMetadata
│   │   ├── config.py              # PitExperimentConfig, RevisionPolicy
│   │   └── validation.py          # ResearchContract, ApprovalGate
│   │
│   └── boundary/                   # Trust boundaries
│       ├── __init__.py
│       ├── research_contract.py   # ResearchContract, ValidationResult
│       ├── data_view.py           # DataViewConstructor, PitViewBuilder
│       ├── synthetic.py           # SyntheticDataScope, EvidenceLabeling
│       └── approval.py            # ApprovalMetadata, AuditTrail
│
└── # Version declarations
```

### 4.2 Version Strategy

| Component | Version | Notes |
|-----------|---------|-------|
| `data_engine` | `0.1.0` | Unchanged |
| `data_engine.strategy` | `3.0.0` | Unchanged |
| `data_engine.quant` | `2.0.0` | Unchanged |
| `data_engine.pit` | `4.1.0` | Unchanged (existing) |
| `data_engine.multi_asset` | `4.0.0` | New — follows PIT versioning |
| `data_engine.multi_asset.calendar` | `4.0.0` | New |
| `data_engine.multi_asset.equities` | `4.0.0` | New |
| `data_engine.multi_asset.forex` | `4.0.0` | New |
| `data_engine.multi_asset.futures` | `4.0.0` | New |
| `data_engine.multi_asset.experiment` | `4.0.0` | New |
| `data_engine.multi_asset.temporal` | `4.0.0` | New — extends pit/temporal |

---

## 5. DATA AND TEMPORAL SCHEMAS

### 5.1 Proposed Shared Core Schemas

**InstrumentIdentity** (frozen Pydantic):
```
instrument_identity: str          # Stable UUID or canonical identifier
asset_class: AssetClass
contract_type: ContractType
venue: VenueRef
created_at: datetime              # When this identity was first registered
registration_source: str          # Who created this identity
```

**InstrumentSpecification** (frozen Pydantic, effective-dated):
```
identity: InstrumentIdentity
effective_from: datetime          # When this spec becomes active
effective_to: Optional[datetime]  # When this spec expires (None = permanent)
price_precision: int
quantity_precision: int
tick_size: Optional[Decimal]      # Minimum price increment
tick_value: Optional[Decimal]     # Dollar value of one tick (futures)
contract_multiplier: Optional[Decimal]  # Futures contract size
trading_currency: str
calendar_ref: CalendarRef
data_source: DataSource
```

**Venue** (frozen Pydantic):
```
venue_id: str
venue_name: str
venue_type: str                   # EXCHANGE, OTC, ELECTRONIC, etc.
timezone: str
trading_calendar_ref: CalendarRef
country: Optional[str]
regulatory_jurisdiction: Optional[str]
```

**CalendarRef** (frozen Pydantic):
```
calendar_id: str
calendar_version: str
calendar_type: str                # EXCHANGE, FX_SESSION, CRYPTO, CUSTOM
description: str
```

**DataSource** (frozen Pydantic):
```
source_id: str
provider_name: str
provider_type: str                # API, FILE, DATABASE, WEBSOCKET
symbol_mapping: Optional[str]     # Provider-specific symbol
data_format: str                  # OHLCV, TICK, SETTLEMENT, EVENT
provenance_hash: str              # Hash of the source specification
```

**PrecisionSpec** (frozen Pydantic):
```
price_decimal_places: int
quantity_decimal_places: int
tick_size: Optional[Decimal]
tick_value: Optional[Decimal]     # Only applicable to futures
contract_multiplier: Optional[Decimal]  # Only applicable to futures
```

### 5.2 Proposed Temporal/PIT Schemas

**TemporalBoundary** (frozen Pydantic):
```
event_time: datetime              # When the market event occurred
observation_time: datetime        # When the observation was recorded
publication_time: Optional[datetime]  # When data was published/made available
effective_time: Optional[datetime]    # When data becomes effective/applicable
revision_time: Optional[datetime]     # When this specific version was revised
ingestion_time: datetime          # Metadata-only; excluded from eligibility and hashes
pit_cutoff: datetime              # The PIT cutoff for this view
```

**PitView** (frozen Pydantic):
```
view_id: str
view_name: str
pit_cutoff: datetime              # All data published at or before this time
revision_policy: RevisionPolicy
instrument_spec_version: str      # Which instrument spec version applies
calendar_version: str             # Which calendar version applies
dataset_hash: str                 # Hash of the underlying dataset
view_hash: str                    # Hash of this PIT view (distinct from dataset_hash)
created_at: datetime              # When this view was constructed
```

**RevisionHistory** (frozen Pydantic):
```
record_id: str
temporal_boundary: TemporalBoundary
revision_chain: List[RevisionEntry]  # Ordered from oldest to newest
```

**RevisionEntry** (frozen Pydantic):
```
revision_time: datetime
publication_time: Optional[datetime]
effective_time: Optional[datetime]
data_hash: str                    # Hash of the data at this revision
change_description: str
supersedes: Optional[str]         # ID of the revision this replaces
```

**TieBreaker** (frozen Pydantic):
```
tie_breaker_type: str             # "timestamp_then_venue_then_symbol" etc.
priority_order: List[str]         # Ordered list of tie-break fields
deterministic_value: str          # The deterministic value used for ordering
```

### 5.3 Schema Boundary Rules

1. **Phase 3 models are NOT modified.** `Candle`, `Instrument`, `Dataset`, `BacktestConfig`, `StrategySpec` remain exactly as they are.
2. **PIT metadata lives in sidecar records** — new models reference existing Phase 3 models by ID/hash, not by embedding.
3. **Legacy serialization remains unchanged.** `BacktestProvenance.compute_result_hash()` must produce the same output for the same inputs.
4. **New PIT-aware hashes are additive.** `view_hash` is computed from the PIT view configuration, not from the same inputs as `dataset_hash`.
5. **No wall-clock defaults.** All datetime fields must be explicitly provided. The `provider_timestamp: Optional[datetime] = Field(default_factory=_now_utc)` on `Candle` is a pre-existing exception that must remain frozen (not changed), but it is explicitly a provider metadata field, not a PIT temporal field.

---

## 6. PIT AND REVISION SEMANTICS

### 6.1 Separation of Temporal Concepts

The following temporal concepts must be strictly separated:

| Concept | Definition | Participates in PIT eligibility? | Participates in result_hash? |
|---------|------------|----------------------------------|------------------------------|
| **Event time** | When the market event actually occurred | Yes — determines which events existed at PIT cutoff | Yes |
| **Observation time** | When the observation was recorded | Yes — determines when the observation became known | Yes |
| **Publication time** | When data was published/made available | **Yes — critical for PIT** — data published after cutoff is excluded | Yes |
| **Effective time** | When data becomes applicable | Yes — determines when data can be used | Yes |
| **Revision time** | When this specific version was revised | Yes — determines which version existed at PIT cutoff | Yes |
| **Ingestion time** | When data was ingested into the system | **No** — metadata only | **No** |
| **PIT cutoff** | The temporal boundary for the research view | Defines the boundary | **Yes** — must be part of view_hash |
| **Simulation end date** | When the backtest simulation ends | No — a backtest configuration parameter | Yes — part of config_hash |

### 6.2 PIT Cutoff vs Simulation End Date

**These are fundamentally different concepts and must never be conflated:**

- **PIT cutoff** answers: "What information was publicly available as of time T?" This is a research design decision about the knowledge boundary.
- **Simulation end date** answers: "At which bar does the backtest stop?" This is a backtest execution parameter.

**Example:** A strategy backtest runs from 2020-01-01 to 2023-12-31 (simulation end date). The PIT cutoff is 2023-12-31, meaning only data published on or before 2023-12-31 can be used. However, if a corporate action occurred on 2024-01-15 but was retroactively applied to 2023 data, that corporate action must NOT be visible in the PIT view because it was published after the cutoff.

### 6.3 Future Publication Handling

**Rule:** Data published after the PIT cutoff is normally **excluded** from that view. Its existence is not an error — it is simply not yet available.

**Behavior:**
1. When constructing a PIT view at cutoff T, iterate through all data items.
2. For each item, check if `publication_time <= T`.
3. If `publication_time > T`, the item is **excluded** — not flagged as an error.
4. If an item has `publication_time` but it is `None`, apply the `MissingFieldPolicy` from the TemporalContract.
5. Items with `publication_time <= T` but `effective_time > T` are **excluded** (not yet effective).
6. Items with `revision_time > T` but `publication_time <= T` — use the latest revision where `revision_time <= T`.

**Why this matters:** A dataset ingested today may contain data points with future publication times (e.g., economic data released after the market close). These must not silently contaminate a PIT view set at an earlier time.

### 6.4 Revision History Reconstruction

**Rule:** A single latest-value record is NOT sufficient to reconstruct earlier vintages.

**Requirement:** Full revision history must be stored and queryable. Each revision must have:
- The data content at that revision
- The temporal metadata (event_time, publication_time, effective_time, revision_time)
- A deterministic hash of the content and metadata
- A reference to the previous revision (or null for the first)

**Revision chain semantics:**
```
Revision v1 (published T1) → Revision v2 (published T2, revision_time T2') → Revision v3 (published T3)
```
At PIT cutoff T2: only v1 and v2 are visible. At PIT cutoff T3: v1, v2, and v3 are visible.

**Storage model:** Revision history is stored as an append-only log. Each revision entry is immutable. The current value is the latest revision by revision_time. Historical queries reconstruct the state at any point in time by filtering revisions by temporal boundary.

### 6.5 Deterministic Tie-Breakers

**Rule:** Insertion order alone is NOT acceptable as a tie-breaker.

**Required deterministic tie-breaker for equal-time observations:**

When two or more observations have identical `event_time`, `publication_time`, `effective_time`, and `revision_time`, the ordering must be determined by a declared, deterministic tie-breaker function. The tie-breaker must produce the same output across all platforms and Python versions.

**Proposed default tie-breaker priority (configurable per asset class):**
1. `venue` (lexicographic)
2. `instrument_identity` (lexicographic)
3. `data_source.source_id` (lexicographic)
4. `canonical_bytes` (byte comparison of canonical serialization)

**Requirement:** The tie-breaker policy must be declared in the experiment configuration and included in the experiment identity hash. Changing the tie-breaker policy creates a different experiment identity.

### 6.6 Missing Timestamps and Timezone Normalization

**Missing timestamp policy:**
- `event_time`: MUST be present. If missing, the record is rejected (REJECT policy) or marked with a temporal uncertainty flag.
- `observation_time`: SHOULD be present. If missing, falls back to `event_time`.
- `publication_time`: May be unknown for some data types. Governed by `MissingFieldPolicy`.
- `effective_time`: May be null if same as `publication_time` or `event_time`.
- `revision_time`: Null for the first revision of a record.
- `ingestion_time`: Always recorded but metadata-only.

**Timezone normalization:**
- All PIT timestamps must be timezone-aware and normalized to UTC.
- Naive datetimes are rejected at validation time.
- Source timezone information (e.g., "this data is from the Tokyo exchange") must be preserved as metadata on the Venue or DataSource, not embedded in the timestamp.
- DST transitions must not affect PIT eligibility — all comparisons use UTC-normalized times.

### 6.7 Stale vs. Historical Data

**Definition:**
- **Stale data:** Data that has been superseded by a newer revision and should no longer be used for current research. Stale data may still be relevant for PIT reconstruction.
- **Historical data:** Data that was valid at a prior point in time and is relevant for understanding past market conditions. Historical data is not "stale" — it is the correct data for its temporal context.

**Implication for PIT:** A data item with `revision_time = T1` that was later revised at `revision_time = T2` is NOT stale — it is the correct data for any PIT view with `cutoff < T2`. It is only stale for PIT views with `cutoff >= T2`.

---

## 7. EXPERIMENT IDENTITY AND HASH VERSIONING PLAN

### 7.1 Deterministic Experiment Identity

**Proposed experiment identity includes:**

| Component | Source | Hash Input | Required? |
|-----------|--------|------------|-----------|
| Strategy hash | `StrategySpec.to_hash()` | Canonical strategy serialization | Yes |
| Source dataset identity | `Dataset.dataset_id` + `DatasetVersion.version` | String concatenation | Yes |
| Source dataset content hash | `Dataset.raw_data_hash` or provenance `source_hash` | SHA-256 | Yes |
| **PIT snapshot/view hash** | `PitView.view_hash` | SHA-256 of PitView canonical serialization | **Yes** |
| PIT cutoff | `PitView.pit_cutoff` | ISO 8601 UTC | Yes |
| PIT revision policy | `RevisionPolicy` configuration | Canonical serialization | Yes |
| Instrument specification version | `InstrumentSpecification` version identifier | String | Yes |
| Calendar version | `CalendarRef.calendar_version` | String | Yes |
| Feature-definition hash | Hash of all indicator definitions used | SHA-256 | Yes |
| Configuration hash | `BacktestConfig` config_hash | SHA-256 of canonical config | Yes |
| Code/schema version | `engine_version`, `quant_engine_version` | String | Yes |
| Tie-breaker policy | Declared tie-breaker configuration | Canonical serialization | Yes |

**Key insight:** The `view_hash` is distinct from the `dataset_hash`. A `dataset_hash` identifies the raw data content. A `view_hash` identifies the PIT view constructed from that data at a specific cutoff with specific revision, calendar, and instrument specification versions.

### 7.2 Hash Versioning Plan

**Phase 3 hashes (unchanged):**
- `strategy_hash`: Same canonical serialization, same algorithm
- `config_hash`: Same canonical serialization, same field order
- `dataset_hash`: Same canonical serialization, same algorithm
- `result_hash`: Same formula `sha256(strategy_hash|dataset_hash|canonical_trades|canonical_equity|canonical_metrics|config_hash)`

**New Phase 4A hashes:**
- `view_hash`: `sha256(pit_cutoff|revision_policy|instrument_spec_version|calendar_version|dataset_hash|temporal_filter_chain)`
- `experiment_id`: `sha256(strategy_hash|view_hash|config_hash|feature_hash|tie_breaker_policy|code_version)`

**Hash version declaration:**
- All hashes must include a version prefix or algorithm identifier to prevent cross-version confusion.
- The `BacktestProvenance` model should include `view_hash`, `experiment_id`, and `hash_algorithm_version` fields.

### 7.3 Legacy Hash Stability Guarantees

**Rule: `BacktestProvenance.compute_result_hash()` MUST produce identical output for identical inputs before and after Phase 4A changes.**

**How this is guaranteed:**
1. `BacktestProvenance` is NOT modified. Its fields and `compute_result_hash()` method remain exactly as they are.
2. New PIT metadata is added to `BacktestProvenance` as **new optional fields** with default values. Existing `result_hash` computation ignores new fields.
3. The `result_hash` formula continues to use the same inputs: `strategy_hash`, `dataset_hash`, `canonical_trades`, `canonical_equity`, `canonical_metrics`, `config_hash`.
4. New `view_hash` and `experiment_id` are **additional** fields on `BacktestProvenance`, not replacements for existing hash fields.
5. A `hash_version` field distinguishes Phase 3 hashes from Phase 4A hashes.

### 7.4 How view_hash Relates to dataset_hash

```
dataset_hash = SHA-256(canonical dataset bytes)
                ↓ identifies the raw data content
view_hash = SHA-256(pit_cutoff | revision_policy | instrument_spec_version | calendar_version | dataset_hash | temporal_filter)
                ↓ identifies a specific PIT VIEW of that data
experiment_id = SHA-256(strategy_hash | view_hash | config_hash | feature_hash | tie_breaker_policy | code_version)
                ↓ identifies a specific reproducible experiment
```

**Same dataset_hash, different view_hash:** Two PIT views over the same dataset but with different cutoffs produce different view_hashes and different experiment_ids.
**Different dataset_hash, same view_hash:** Not possible — view_hash includes dataset_hash.

---

## 8. PHASE 3 COMPATIBILITY AND MIGRATION PLAN

### 8.1 Sidecar Record Strategy

**Decision: PIT metadata lives in sidecar records, NOT in existing Phase 3 models.**

**Justification:**
1. Adding temporal fields to `Candle`, `Instrument`, or `Dataset` would change their canonical serialization, breaking existing hashes.
2. The Phase 3 `Candle` model has `provider_timestamp: Optional[datetime]` which serves a similar but different purpose (provider metadata, not PIT temporal).
3. Sidecar records allow PIT metadata to evolve independently of the core data models.

**Sidecar record structure:**
```python
class PitSidecar(BaseModel):
    """PIT metadata attached to a Phase 3 dataset by reference."""
    model_config = ConfigDict(frozen=True)
    dataset_id: str                    # References Dataset.dataset_id
    dataset_version: str               # References DatasetVersion.version
    temporal_boundary: TemporalBoundary
    pit_view_id: str                   # References PitView.view_id
    revision_history: List[RevisionEntry]
    instrument_spec_version: str
    calendar_version: str
```

### 8.2 Legacy Dataset Validity

**Rule: Existing Phase 3 datasets remain valid as-is.**

**How:**
1. Existing `Dataset` objects without PIT sidecars are treated as having `publication_time = effective_time = event_time = dataset_provenance.retrieval_timestamp`.
2. This is an implicit assumption that must be declared in the experiment configuration.
3. Legacy datasets can be used in PIT views, but the PIT view must declare that the temporal metadata is inferred from the provenance record.
4. The `PitSidecar` is optional — a dataset without one is valid but has limited PIT functionality.

### 8.3 Legacy Serialization Stability

**Guarantee:** All existing serialization formats remain unchanged.

**Specific guarantees:**
- `StrategySpec.canonical_serialize()` output: unchanged
- `BacktestConfig.get_cost_parameters()` / `get_slippage_parameters()`: unchanged
- `BacktestProvenance.compute_result_hash()` inputs and algorithm: unchanged
- `Candle.to_hash()`: unchanged
- `ProvenanceRecord.to_hash()`: unchanged
- Dataset canonical serialization: unchanged
- `canonical_serialize()` in `pit/serialization.py`: unchanged
- `deterministic_hash()` in `pit/hashing.py`: unchanged

### 8.4 PIT-Aware Experiment Identity Schema/Version

**Decision: A new schema/version IS required for PIT-aware experiment identity.**

**How:**
1. `BacktestProvenance` gains new optional fields: `view_hash: str = ""`, `experiment_id: str = ""`, `pit_cutoff: Optional[datetime] = None`, `hash_algorithm_version: str = "4.0.0"`.
2. The `engine_version` field remains `"3.0.0"` for Phase 3 compatibility.
3. New fields have defaults to maintain backward compatibility with existing code that constructs `BacktestProvenance`.
4. A new `PitExperimentProvenance` model extends `BacktestProvenance` with PIT-specific fields for experiments that require PIT semantics.
5. The `result_hash` computation in `BacktestProvenance` is NOT changed.

### 8.5 Avoiding Silent Changes to compute_result_hash()

**Mechanism:**
1. `BacktestProvenance.compute_result_hash()` method is never modified.
2. Any new hash computation (e.g., `view_hash`, `experiment_id`) uses a NEW method name (e.g., `compute_view_hash()`, `compute_experiment_id()`).
3. Tests that verify `result_hash` stability must continue to pass without modification.
4. The `result_hash` field on `BacktestResult` continues to use the same formula.
5. A new `view_hash` field is added to `BacktestResult` and `BacktestProvenance` but is computed separately.

### 8.6 Migration Path

**Phase 3 → Phase 4A migration steps (design only, not implemented):**

1. **Add `PitSidecar` model** — new module, no changes to existing models
2. **Add `PitView`, `TemporalBoundary`, `RevisionHistory` models** — new module
3. **Extend `BacktestProvenance`** — add optional fields with defaults
4. **Add `compute_view_hash()` method** — new method on `BacktestProvenance`
5. **Add `compute_experiment_id()` method** — new method
6. **Create `PitExperimentConfig`** — configuration for PIT-aware experiments
7. **Create `CalendarInterface`** — abstract calendar/session interface
8. **Create asset-specific modules** — equities, forex, futures
9. **Create `ResearchContract`** — validation and approval boundary

**Migration compatibility rule:** Every existing Phase 3 test must continue to pass without modification. New tests are added for new functionality.

---

## 9. ASSET-SPECIFIC RISK AND LEAKAGE ANALYSIS

### 9.1 Futures: Continuous-Contract Adjustment and Rollover Leakage

**Risk:** Future contract information leaking into historical decisions.

**Specific leakage vectors:**
1. **Roll date leakage:** Knowing that contract X was rolled on date D, and using that knowledge to make a trading decision before date D. The roll decision itself is based on market conditions that were knowable, but the **specific roll timing** may contain information not available before the roll.
2. **Back-adjustment leakage:** Continuous series prices are adjusted retroactively. Using back-adjusted prices in a PIT view at a time before the adjustment was known creates a look-ahead bias.
3. **Settlement price leakage:** Settlement prices may be published after the PIT cutoff. Using settlement prices that were not yet published at the decision time is a PIT violation.
4. **Expiry metadata leakage:** Knowing that a contract expires on date X is generally public information, but the specific contract terms (multiplier, tick size) may change. Using the latest contract specifications for a historical decision is a leakage risk.

**Proposed mitigation:**
- Futures contracts must be tracked as **individual dated instruments** in PIT views.
- Continuous series must be marked with their **adjustment method** and **adjustment date**.
- Back-adjusted prices must have a separate `adjusted_price` field with the adjustment metadata, never replacing the raw contract price in PIT views.
- **Roll policy** must be declared explicitly (e.g., "roll 5 trading days before expiry") and must not depend on future information.
- `RolloverPolicy` must specify the lookback window for determining which contract is primary, using only information available at that time.

**Red-team test case:** Construct a PIT view at time T. Verify that no contract expiring after T+1 is used in the view, and that no back-adjustment made after T is visible.

### 9.2 Equities: Corporate Actions and Survivorship Bias

**Risk:** Corporate action adjustments creating look-ahead bias, and delisted securities being excluded from historical analysis.

**Specific leakage vectors:**
1. **Split/dividend adjustments:** A 2-for-1 split is retroactively applied to historical prices. Using adjusted prices in a PIT view before the split announcement creates look-ahead bias.
2. **Symbol changes:** A company changes its ticker from ABC to XYZ. A PIT view at a time when the symbol was still ABC must not show data under the symbol XYZ.
3. **Delisting survivorship bias:** A company is delisted. A dataset that only includes currently-listed securities excludes the delisted company's pre-delisting data, creating survivorship bias.
4. **Merger/acquisition adjustments:** When Company A acquires Company B, Company B's historical data may be removed or adjusted.

**Proposed mitigation:**
- **Corporate actions create new instrument identity events**, not data corrections. A split on date D creates a new `InstrumentSpecification` effective from D, but the pre-split data remains available under the pre-split specification.
- **Point-in-time universe membership** must be tracked. At any PIT cutoff, the universe includes only securities that were listed and not delisted at that time.
- **Adjusted vs. unadjusted prices** are distinct data products. PIT views must declare which version they use.
- **Delisted securities** must remain in the historical dataset with a `delisting_date` field and `universe_membership` timeline.

**Red-team test case:** Construct a PIT view at time T=2020-01-01. Verify that a split announced on 2020-06-01 does NOT affect prices visible at T. Verify that a security delisted on 2021-03-01 is visible in the PIT view at T=2020-01-01.

### 9.3 FX: Bid/Ask and Financing Assumptions

**Risk:** Hidden spread assumptions and financing rates creating unrealistic backtest results.

**Specific leakage vectors:**
1. **Bid/ask spread assumptions:** Using a fixed spread assumption that does not match the actual spread at the time of the trade.
2. **Provider-specific symbol mapping:** The same currency pair may have different symbols across providers (e.g., EURUSD vs. EUR/USD vs. EURUSD-SPOT). Incorrect mapping leads to data substitution.
3. **Financing/swap rates:** Overnight financing rates change over time. Using current rates for historical positions creates unrealistic P&L.
4. **Session/holiday assumptions:** FX trades 24/5, but holidays in specific countries can affect liquidity and spread. Assuming continuous liquidity on holidays is unrealistic.

**Proposed mitigation:**
- **Bid/ask data** must be stored separately from mid-price. PIT views must declare whether they use mid-price, bid, or ask.
- **Spread assumptions** must be explicit parameters, not hidden defaults. The `SpreadModel` must be declared in the experiment configuration.
- **Financing rates** must be time-series data with their own PIT temporal metadata. They cannot be assumed constant.
- **Provider symbol mapping** must be versioned and included in the data source hash. A change in symbol mapping creates a different data source identity.
- **Rollover time** must be declared and consistent across the dataset.

**Red-team test case:** Construct two PIT views over the same FX dataset — one using mid-price, one using ask price. Verify they produce different results and that the difference is correctly attributed to the spread assumption.

### 9.4 Cross-Asset Calendar Leakage

**Risk:** Assuming one universal trading calendar across asset classes.

**Specific leakage vectors:**
1. **Equity holiday assumed for FX:** US equity markets are closed on Thanksgiving, but FX markets remain open. Treating Thanksgiving as a non-trading day for FX creates a gap in data.
2. **Crypto 24/7 assumed for futures:** Crypto trades 24/7, but futures contracts have specific trading sessions. Treating crypto 24/7 as futures trading hours creates unrealistic fill assumptions.
3. **DST transitions:** Markets transitioning to/from daylight saving time have shifted session boundaries. Not accounting for DST creates timestamp mismatches.
4. **Instrument-specific schedules:** Some futures contracts have different trading hours than the parent exchange. Using exchange hours for all contracts is incorrect.

**Proposed mitigation:**
- **Calendar versioning:** Each calendar has a version number. Changes to the calendar (e.g., new holiday declared, DST rule change) create a new calendar version.
- **Calendar version included in experiment identity.** Changing the calendar version creates a different experiment.
- **Instrument-specific calendars** override exchange-level calendars.
- **Overnight sessions** must be explicitly declared (e.g., CME Globex overnight session).
- **24/7 markets** are represented as a calendar with no session boundaries, not as an absence of calendar data.

---

## 10. TEST MATRIX WITH ACCEPTANCE CRITERIA

### 10.1 Legacy Phase 3 Hash Stability

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-H01 | Result hash unchanged after Phase 4A additions | Same inputs produce identical `result_hash` before and after | Regression |
| T-H02 | Dataset hash unchanged | `Dataset.to_hash()` produces same output after adding PitSidecar | Regression |
| T-H03 | Strategy hash unchanged | `StrategySpec.to_hash()` produces same output after any changes | Regression |
| T-H04 | Config hash unchanged | `BacktestConfig._compute_config_hash()` produces same output | Regression |
| T-H05 | Cross-process determinism | Run same backtest in 6 separate processes, compare all hashes | Determinism |
| T-H06 | Run timestamp exclusion | Changing `run_timestamp` does not change `result_hash` | Determinism |

### 10.2 PIT Cutoff Boundary Behavior

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-P01 | Data published exactly at cutoff | `publication_time == pit_cutoff` → included | Boundary |
| T-P02 | Data published one second after cutoff | `publication_time == pit_cutoff + 1s` → excluded | Boundary |
| T-P03 | Data revised after cutoff | Latest revision with `revision_time <= pit_cutoff` is used | Boundary |
| T-P04 | Data with publication_time after cutoff | Excluded from PIT view, no error raised | Boundary |
| T-P05 | Data with effective_time after cutoff | Excluded even if publication_time <= cutoff | Boundary |
| T-P06 | PIT cutoff equals simulation start | All data published before start is available | Boundary |
| T-P07 | PIT cutoff equals simulation end | Same as simulation end date, no conflict | Boundary |

### 10.3 Revision History Reconstruction

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-R01 | Single revision history | One revision → one visible entry at any cutoff after publication | Reconstruction |
| T-R02 | Multiple revisions | At cutoff T, only revisions with revision_time <= T are visible | Reconstruction |
| T-R03 | Revision chain integrity | Each revision references the previous revision | Reconstruction |
| T-R04 | Latest-value-only rejection | A dataset with only the latest value cannot reconstruct vintages | Reconstruction |
| T-R05 | Revision hash determinism | Same revision data produces same hash across processes | Determinism |
| T-R06 | Superseded revision access | Accessing a superseded revision returns the correct historical data | Reconstruction |

### 10.4 Same Observation with Different Publication/Revision Times

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-S01 | Same data, different publication_time | Two records with identical data but different publication_time → different PIT eligibility | Temporal |
| T-S02 | Same data, different revision_time | Two revisions with identical data → same content hash, different revision_time | Temporal |
| T-S03 | Same publication_time, different event_time | Two observations published simultaneously but from different events → distinct | Temporal |
| T-S04 | Equal temporal fields | Deterministic tie-breaker produces consistent ordering | Determinism |

### 10.5 Missing Temporal Metadata

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-M01 | Missing event_time | Rejected by TemporalContract with REJECT policy | Validation |
| T-M02 | Missing publication_time | Rejected or allowed based on TemporalContract policy | Validation |
| T-M03 | Missing effective_time | Falls back to publication_time or event_time | Validation |
| T-M04 | Missing revision_time | Treated as first revision (null) | Validation |
| T-M05 | Missing all temporal fields | Rejected, no silent default applied | Validation |
| T-M06 | Naive datetime rejection | Any timezone-naive datetime raises ValidationError | Validation |

### 10.6 Timezone Normalization

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-Z01 | EST → UTC conversion | 5:30 EST → 10:30 UTC | Normalization |
| T-Z02 | All PIT timestamps UTC | After normalization, all timestamps have UTC timezone | Normalization |
| T-Z03 | DST transition boundary | Timestamps across DST boundary maintain correct UTC offset | Normalization |
| T-Z04 | Source timezone preserved as metadata | Original timezone stored on Venue/DataSource, not in timestamp | Normalization |

### 10.7 Deterministic Equal-Time Ordering

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-O01 | Same timestamp, different venue | Tie-breaker orders by venue lexicographically | Determinism |
| T-O02 | Same timestamp, same venue, different symbol | Tie-breaker orders by instrument_identity | Determinism |
| T-O03 | Cross-platform determinism | Same ordering on Windows and Linux | Determinism |
| T-O04 | Tie-breaker policy in experiment identity | Changing tie-breaker policy changes experiment_id | Determinism |

### 10.8 Immutable PIT Snapshots

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-I01 | PitView immutability | Attempting to modify PitView raises ValidationError | Immutability |
| T-I02 | PIT snapshot after construction | Constructed snapshot cannot be changed by later data ingestion | Immutability |
| T-I03 | Revision history immutability | Append-only — cannot modify or delete existing revision entries | Immutability |
| T-I04 | Sidecar immutability | PitSidecar is frozen — no mutation after construction | Immutability |

### 10.9 Instrument-Specification Changes Over Time

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-SPEC01 | Tick size change | Instrument spec with old tick_size visible before change, new after | Specification |
| T-SPEC02 | Effective-dated specification | Specification effective_from and effective_to respected | Specification |
| T-SPEC03 | Contract multiplier change (futures) | Old multiplier for pre-change dates, new for post-change dates | Specification |
| T-SPEC04 | Currency change | Trading currency correct for each time period | Specification |

### 10.10 Equity Corporate Actions and PIT Universe Membership

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-EQ01 | Split adjustment | Pre-split prices not adjusted in PIT view before split date | Corporate Action |
| T-EQ02 | Dividend adjustment | Pre-dividend prices not adjusted in PIT view before ex-date | Corporate Action |
| T-EQ03 | Symbol change | Old symbol visible before change date, new symbol after | Corporate Action |
| T-EQ04 | Delisting survivorship | Delisted security visible in PIT view before delisting date | Survivorship Bias |
| T-EQ05 | Point-in-time universe | Universe membership at PIT cutoff T includes only securities listed at T | Survivorship Bias |
| T-EQ06 | Merger/acquisition | Acquired company's data remains in historical PIT views | Corporate Action |

### 10.11 Futures Expiry and Rollover Boundaries

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-FU01 | Contract expiry boundary | Contract not used after last trading day | Expiry |
| T-FU02 | Roll boundary | Roll occurs at declared rollover policy time, not before | Rollover |
| T-FU03 | Continuous series adjustment | Back-adjusted prices not visible in PIT view before adjustment date | Adjustment |
| T-FU04 | Raw contract price vs continuous | Raw prices and adjusted prices are distinct and separately identifiable | Adjustment |
| T-FU05 | Roll leakage | Future roll information not available in PIT view before the roll event | Leakage |
| T-FU06 | Settlement price timing | Settlement price not used in PIT view before publication time | Timing |

### 10.12 FX Pair Conventions and Spread Assumptions

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-FX01 | Pair convention | Base/quote semantics correct for the pair | Convention |
| T-FX02 | Provider symbol mapping | Correct symbol resolved for each provider | Mapping |
| T-FX03 | Mid vs ask price | PIT view using mid-price differs from PIT view using ask price | Spread |
| T-FX04 | Spread assumption explicit | Spread model declared in experiment config, not implicit | Assumption |
| T-FX05 | Financing rate time series | Financing rates change over time, not constant | Financing |
| T-FX06 | Session/holiday handling | FX trading continues during equity holidays | Calendar |

### 10.13 Calendar Version Changes

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-C01 | Calendar version change | New holiday added → new calendar version → different experiment identity | Versioning |
| T-C02 | DST transition | Calendar handles DST shift correctly | DST |
| T-C03 | Exchange-specific calendar | Different exchanges have different session calendars | Exchange |
| T-C04 | Instrument-specific schedule | Instrument overrides exchange calendar | Override |
| T-C05 | 24/7 market calendar | Crypto market has no session boundaries | 24/7 |
| T-C06 | Calendar version in experiment identity | Changing calendar version changes experiment_id | Identity |

### 10.14 Invalid or Future Information Excluded from Historical Views

| Test ID | Description | Acceptance Criteria | Category |
|---------|-------------|---------------------|----------|
| T-X01 | Future publication excluded | Data published after PIT cutoff is excluded | Exclusion |
| T-X02 | Future revision excluded | Revision with revision_time > cutoff is excluded | Exclusion |
| T-X03 | Future effective excluded | Effective time after cutoff → excluded | Exclusion |
| T-X04 | Future contract expiry excluded | Contract expiring after cutoff not used in historical view | Exclusion |
| T-X05 | Future corporate action excluded | Corporate action announced after cutoff not applied | Exclusion |
| T-X06 | Future calendar change excluded | Calendar change effective after cutoff not applied | Exclusion |
| T-X07 | No automatic error on future data | Future data is silently excluded, not flagged as error | Behavior |

---

## 11. RED-TEAM FINDINGS, SEVERITY, AND REMEDIATION

### 11.1 Critical Findings

| ID | Finding | Severity | Evidence | Remediation |
|----|---------|----------|----------|-------------|
| RT-01 | **PIT cutoff conflated with simulation end date** | CRITICAL | The existing backtest engine has no concept of PIT cutoff; `BacktestConfig` has no `pit_cutoff` field. A backtest running from 2020-2023 uses all data from the dataset without considering when data was published. | Add `pit_cutoff` to `BacktestConfig` as a new optional field. Create `PitViewBuilder` that constructs PIT-filtered datasets before backtest execution. |
| RT-02 | **No revision history reconstruction** | CRITICAL | The existing `ProvenanceRecord` and `DatasetVersion` track versions but do not maintain a revision chain per data item. A single `DatasetVersion` represents one snapshot, not a revision history. | Implement `RevisionHistory` as a sidecar record. Each data item gets a revision chain. `PitView` reconstructs the state at any cutoff. |
| RT-03 | **Latest-value-only data cannot reconstruct PIT views** | CRITICAL | The `Dataset` model stores one set of candles per dataset version. There is no mechanism to retrieve "what did this data look like at PIT cutoff T?" | PIT sidecar records must store revision history. The `PitViewBuilder` queries the revision chain, not just the latest data. |
| RT-04 | **Single universal calendar assumption** | CRITICAL | `Timeframe` enum and `Candle` model assume a single trading calendar. `Timeframe.M1=525600` periods_per_year assumes 24/7 trading. This is true for crypto but false for equities and futures. | Create `CalendarInterface`. Each instrument references a calendar. `periods_per_year` must be calendar-aware, not a fixed constant. |
| RT-05 | **Futures continuous series and individual contracts not distinguished** | CRITICAL | `ContractType.FUTURES` exists but there is no model for individual dated contracts vs continuous series. The `Instrument` model has no contract_month or expiry_date field. | Add `FuturesContract` model with expiry, contract_month, and adjustment metadata. Continuous series must be a distinct instrument type with explicit adjustment method. |

### 11.2 High Findings

| ID | Finding | Severity | Evidence | Remediation |
|----|---------|----------|----------|-------------|
| RT-06 | **No point-in-time universe membership** | HIGH | `Instrument` model has no `listing_date` or `delisting_date`. A dataset of equities implicitly includes all securities that ever existed, creating survivorship bias. | Add `PointInTimeUniverse` model. Track universe membership per instrument per date. PIT views filter by universe membership at the cutoff. |
| RT-07 | **Corporate actions create data corrections, not new events** | HIGH | When a split occurs, historical prices are retroactively adjusted in most datasets. There is no mechanism to preserve the original prices at the PIT point in time. | Corporate actions create new `InstrumentSpecification` versions. Historical data remains under the old specification. Adjusted prices are a separate data product. |
| RT-08 | **FX bid/ask spread assumptions implicit** | HIGH | `Candle` has `bid`, `ask`, `spread` fields but no model for how spreads are determined or whether they are realistic for the time period. | Create `SpreadModel` with explicit assumptions. PIT views must declare spread assumptions. `BacktestConfig` must include spread model reference. |
| RT-09 | **ingestion_time included in temporal semantics but potentially misused** | HIGH | `TemporalSemantics.ingestion_time` is documented as metadata-only, but there is no enforcement mechanism preventing it from being used in PIT eligibility calculations. | The `TemporalContract` must explicitly list which fields are eligible and non-eligible. `TemporalSemantics.temporal_hash_input()` already excludes ingestion_time. |
| RT-10 | **No mechanism to validate PIT view construction** | HIGH | The existing `DataQualityGate` validates data quality but has no concept of PIT temporal validity. | Create `PitViewValidator` that checks all data items in a view against the PIT cutoff using `TemporalContract`. |

### 11.3 Medium Findings

| ID | Finding | Severity | Evidence | Remediation |
|----|---------|----------|----------|-------------|
| RT-11 | **Deterministic tie-breakers not declared** | MEDIUM | `canonical_serialize` sorts dict keys and preserves list order, but when two observations have identical temporal fields, the ordering is not deterministic across platforms due to dict insertion order or float representation differences. | Define `TieBreakerPolicy` in experiment configuration. Include in `experiment_id` hash. |
| RT-12 | **Wall-clock default in Candle.provider_timestamp** | MEDIUM | `Candle` has `provider_timestamp: Optional[datetime] = Field(default_factory=_now_utc)`. This is a wall-clock default that introduces non-determinism. | This is a pre-existing Phase 3 model and must NOT be modified. However, any new PIT-aware schema must NOT have wall-clock defaults. |
| RT-13 | **No versioning for calendar data** | MEDIUM | Calendars are not versioned in the current architecture. A holiday change would silently affect all experiments. | Create `CalendarVersion` model. Include calendar version in `PitView` and `experiment_id`. |
| RT-14 | **No explicit approval representation for research contracts** | MEDIUM | The existing `DataQualityGate` blocks invalid data but does not represent human or system approval as auditable external metadata. | Create `ApprovalMetadata` model. Approval is represented as an auditable record, not a bypassable method call. |
| RT-15 | **Synthetic/simulated data can be misrepresented** | MEDIUM | `EvidenceProvenance` has SYNTHETIC and SIMULATED labels, but the `ProvenanceTracker.can_downstream_use()` only blocks SYNTHETIC for downstream use. SIMULATED data can still be used without clear labeling. | `ResearchContract` must explicitly label all data as REAL, SYNTHETIC, SIMULATED, or UNKNOWN. PIT views must carry the evidence label. |

### 11.4 Low Findings

| ID | Finding | Severity | Evidence | Remediation |
|----|---------|----------|----------|-------------|
| RT-16 | **Design doc integrity discrepancy** | LOW | `docs/strategy_engine_design.md` final line says "COMPLETE" instead of "NO-GO" with a CR and checkmark. | Not a source code issue. Document the discrepancy. The design lock SHA may need verification. |
| RT-17 | **Phase 4A.1 PIT module untracked** | LOW | The `src/data_engine/pit/` and `tests/test_pit.py` are untracked. The Phase 4A.1 work is not committed. | Commit the Phase 4A.1 work with appropriate version tagging. Verify all tests pass before proceeding. |
| RT-18 | **No cross-process determinism test for PIT views** | LOW | `verify_cross_process_hash` exists in `pit/hashing.py` but is not tested for PIT view construction. | Add `test_pit_cross_process_determinism` to `test_pit.py`. |
| RT-19 | **Missing timestamp handling varies by component** | LOW | Some components reject missing timestamps, others allow None. The policy is inconsistent. | Standardize on `MissingFieldPolicy` from `TemporalContract` across all components. |

### 11.5 Design Contradictions Identified

| ID | Contradiction | Severity | Resolution |
|----|--------------|----------|------------|
| RC-01 | **"No wall-clock defaults in deterministic schemas" vs `Candle.provider_timestamp` default** | HIGH | The existing `Candle.provider_timestamp` uses `default_factory=_now_utc)` which is a wall-clock default. This was introduced in Phase 3 and must remain frozen. New PIT schemas must not have this pattern. |
| RC-02 | **"Separate PIT cutoff from simulation end date" vs existing backtest has no PIT cutoff** | HIGH | The Phase 3 backtest engine treats all dataset data as available regardless of publication time. The PIT cutoff concept does not exist in Phase 3. |
| RC-03 | **"Full revision history reconstruction" vs "DatasetVersion is immutable single snapshot"** | MEDIUM | `DatasetVersion` in `schemas.py` represents a single immutable snapshot. Revision history requires a chain of versions per data item, not a single version per dataset. |
| RC-04 | **"Universal calendar" vs "exchange-specific sessions"** | MEDIUM | `Timeframe` and `periods_per_year` assume a universal trading calendar. Different exchanges have different holidays and session hours. |
| RC-05 | **"No future information leakage" vs existing backtest processes all data sequentially** | MEDIUM | The backtest loop processes data chronologically, but it has no mechanism to filter data by publication time. Data published after a bar's time is still visible to the backtest. |

### 11.6 Unsafe Assumptions

| ID | Assumption | Where | Risk | Correct Assumption |
|----|------------|-------|------|-------------------|
| UA-01 | "All asset classes share the same trading calendar" | `Timeframe`, `periods_per_year` | Calendar leakage | Each instrument has its own calendar reference |
| UA-02 | "A single latest-value record is sufficient for PIT reconstruction" | `Dataset`, `DatasetVersion` | Revision leakage | Revision chains must be stored and queryable |
| UA-03 | "Volume means the same thing across asset classes" | `Candle.volume` | Semantic mismatch | Volume semantics are asset-class-specific |
| UA-04 | "Bid/ask is always available" | `Candle.bid`, `Candle.ask` | Data substitution | Bid/ask may be unavailable; mid-price is a separate product |
| UA-05 | "Corporate actions can be retroactively applied" | Data ingestion | Look-ahead bias | Corporate actions create new instrument specifications |
| UA-06 | "Continuous futures prices represent actual trade prices" | `ContractType.FUTURES` | Adjustment leakage | Continuous series are synthetic constructs with explicit adjustment methods |
| UA-07 | "All data is published at the time of observation" | `Candle.provider_timestamp` | PIT violation | Publication time can differ significantly from observation time |
| UA-08 | "The same symbol always refers to the same instrument" | `Instrument.symbol` | Identity collision | Symbols change over time; identity must be stable across symbol changes |

---

## 12. EXPLICIT DESIGN DECISIONS AND UNRESOLVED QUESTIONS

### 12.1 Explicit Design Decisions

| # | Decision | Rationale | Status |
|---|----------|-----------|--------|
| DD-01 | PIT metadata lives in sidecar records, not in existing Phase 3 models | Preserves hash stability, allows independent evolution | **DECIDED** |
| DD-02 | A new PIT-aware experiment identity requires a new schema/version | `BacktestProvenance` must not have its `result_hash` changed | **DECIDED** |
| DD-03 | Future publication is normally excluded, not an error | PIT views are time-sliced views, not validation of data freshness | **DECIDED** |
| DD-04 | Calendar version is included in experiment identity | Different calendar versions produce different market sessions | **DECIDED** |
| DD-05 | Revision history is an append-only chain | Immutability and auditability | **DECIDED** |
| DD-06 | Deterministic tie-breakers are declared per experiment | Prevents non-deterministic ordering | **DECIDED** |
| DD-07 | Single latest-value record is NOT sufficient for PIT reconstruction | Revision chains must be stored | **DECIDED** |
| DD-08 | `ingestion_time` is metadata-only, excluded from eligibility and hashes | Prevents ingestion timing from leaking into research | **DECIDED** (in existing Phase 4A.1) |
| DD-09 | All PIT timestamps must be UTC-normalized, naive datetimes rejected | Consistency and determinism | **DECIDED** (in existing Phase 4A.1) |
| DD-10 | Corporate actions create new instrument identity events, not data corrections | Preserves PIT integrity | **DECIDED** |
| DD-11 | Futures continuous series and individual contracts are distinct instruments | Prevents adjustment leakage | **DECIDED** |
| DD-12 | Calendar data is versioned and included in experiment identity | Enables reproducibility | **DECIDED** |
| DD-13 | No wall-clock defaults in new deterministic schemas | Determinism | **DECIDED** |
| DD-14 | `BacktestProvenance.compute_result_hash()` is never modified | Legacy hash stability | **DECIDED** |
| DD-15 | Approval is represented as auditable external metadata | Non-bypassable validation | **DECIDED** |
| DD-16 | Synthetic/simulated data must be explicitly labeled in PIT views | Evidence integrity | **DECIDED** |

### 12.2 Unresolved Questions

| # | Question | Impact | Options |
|---|----------|--------|---------|
| UQ-01 | **Should `periods_per_year` be a per-instrument property or a calendar property?** | Affects all backtest metric calculations. Current implementation uses fixed values per `Timeframe` (M1=525600, etc.) which assumes 24/7 trading. | Option A: Make `periods_per_year` a property of `CalendarRef`. Option B: Keep `Timeframe`-based but add a `trading_days_per_year` override per instrument. Option C: Calculate `periods_per_year` dynamically from the calendar's session schedule. |
| UQ-02 | **How should the `PitSidecar` be versioned independently of the dataset?** | Affects migration strategy. If the sidecar schema changes, existing datasets with old sidecar versions may need conversion. | Option A: Sidecar has its own version field. Option B: Sidecar is immutable once created; new sidecars are created for schema changes. Option C: Sidecar schema changes are backward-compatible by adding optional fields. |
| UQ-03 | **Should `PitView` be constructed before or after the backtest engine runs?** | Affects architecture. If before, the backtest engine receives a filtered dataset. If after, the backtest engine has a PIT filter parameter. | Option A: `PitViewBuilder` constructs a filtered `Dataset` before `BacktestEngine.run()`. Option B: `BacktestEngine` accepts a `PitView` parameter and filters internally. Option C: Separate `PitBacktestEngine` that composes `PitViewBuilder` and `BacktestEngine`. |
| UQ-04 | **How are `ApprovalMetadata` decisions represented?** | Affects trust boundaries. Approval must be auditable but also practical. | Option A: Approval is a signed record with approver, timestamp, and scope. Option B: Approval is a hash of the research contract + config + dataset hash. Option C: Approval is an external audit trail reference with a hash commitment. |
| UQ-05 | **Should the `CalendarInterface` be a Pydantic model or a protocol/ABC?** | Affects extensibility. A Pydantic model allows validation and serialization. An ABC allows arbitrary Python implementations. | Option A: Pydantic model for consistency with the codebase. Option B: Protocol for maximum flexibility. Option C: Both — a Pydantic model for configuration and a protocol for the runtime interface. |
| UQ-06 | **How does the `RolloverPolicy` handle ambiguous roll dates?** | Futures contracts may have multiple valid rollover dates. The policy must be deterministic. | Option A: Fixed number of trading days before expiry (e.g., "5 days"). Option B: Volume-based rollover (roll when volume shifts to next contract). Option C: Configurable policy with explicit date or condition. |
| UQ-07 | **Should `TemporalContract` support asset-class-specific required fields?** | Different asset classes may require different temporal fields. | Option A: `TemporalContract` has a `required_fields` list that varies by `TemporalDataType`. Option B: Subclass `TemporalContract` per asset class. Option C: `TemporalContract` has a `data_type` field that determines default required fields, overridable. |
| UQ-08 | **What is the relationship between `data_engine.pit` (v4.1.0) and the proposed `data_engine.multi_asset.temporal` (v4.0.0)?** | Affects module organization and versioning. | Option A: `multi_asset.temporal` extends `pit/temporal.py` with new classes, keeping both modules. Option B: `pit/` is absorbed into `multi_asset/temporal/` with a refactoring pass. Option C: `pit/` remains standalone for Phase 4A.1; `multi_asset/temporal/` adds PIT-aware research constructs on top. |
| UQ-09 | **How are timezone conversions handled when source timezone is unknown?** | Some data providers do not specify the exchange timezone. | Option A: Reject data with unknown timezone. Option B: Default to UTC and log a warning. Option C: Infer timezone from the exchange/venue metadata. |
| UQ-10 | **Should `event_time` be required for all data types, including derived indicators?** | Derived indicators (e.g., EMA values) don't have a natural "event time" — they have a computation time. | Option A: `event_time` = timestamp of the bar the indicator is computed for. Option B: `event_time` = computation completion time. Option C: `event_time` = `observation_time` for derived data. |
| UQ-11 | **How does the `ResearchContract` handle partial approval?** | A research project may have partial approval (e.g., approved data but not methodology). | Option A: Approval is all-or-nothing. Option B: Approval has scopes (data_approved, methodology_approved, results_approved). Option C: Approval is a DAG of dependent approvals. |
| UQ-12 | **Should `view_hash` include the tie-breaker policy?** | If two PIT views have the same cutoff and data but different tie-breakers, should they have different hashes? | Option A: Yes — tie-breaker affects ordering and therefore results. Option B: No — tie-breaker is a configuration detail, not a data identity detail. Option C: Only if the tie-breaker affects the actual data items included. |
| UQ-13 | **How should `TemporalContract` handle `TemporalDataType.DERIVED`?** | Derived indicators have no `publication_time` in the traditional sense — they are computed. | Option A: `publication_time` = computation completion time. Option B: `publication_time` = the `event_time` of the underlying data. Option C: `publication_time` is null and governed by `MissingFieldPolicy`. |
| UQ-14 | **What is the interaction between `DataQualityGate` and `PitViewValidator`?** | Both validate data before downstream use. There may be overlap or conflict. | Option A: `PitViewValidator` runs after `DataQualityGate`. Option B: `PitViewValidator` is a separate gate in the pipeline. Option C: `DataQualityGate` is extended with PIT validation methods. |
| UQ-15 | **Should `BacktestConfig` be extended with `pit_cutoff` or should `PitView` be constructed separately?** | Affects the backtest configuration interface. | Option A: Add `pit_cutoff` to `BacktestConfig`. Option B: `PitView` is a separate pre-processing step. Option C: `BacktestEngine.run()` accepts an optional `PitView` parameter. |

### 12.3 Design Contradiction Resolution Plan

| RC ID | Contradiction | Resolution |
|-------|--------------|------------|
| RC-01 | Wall-clock default in `Candle.provider_timestamp` | **Accepted as a Phase 3 legacy exception.** The field is `provider_timestamp`, not a PIT temporal field. New PIT schemas must not have this pattern. Document as a known deviation. |
| RC-02 | No PIT cutoff in Phase 3 backtest | **Resolution:** Add `PitView` as a pre-processing step. `BacktestEngine.run()` optionally accepts a `PitView`. The existing backtest continues to work without a PIT view (implicit full-data view). |
| RC-03 | `DatasetVersion` vs revision chain | **Resolution:** `DatasetVersion` remains as-is for dataset-level versioning. A new `RevisionChain` model handles per-data-item revision history, stored in `PitSidecar`. |
| RC-04 | Universal vs exchange-specific calendar | **Resolution:** `Timeframe` remains for data granularity. `CalendarRef` is added for trading schedule. `periods_per_year` in metrics becomes calendar-aware. |
| RC-05 | No future data filtering in backtest | **Resolution:** `PitViewBuilder` filters data before passing to `BacktestEngine`. The backtest engine itself is not modified. |蛋---

## 13. RECOMMENDED SMALL IMPLEMENTATION SUBPHASES

**These are recommended subphases for eventual implementation. No implementation is authorized in this review.**

### Subphase 4A.0: Foundation (Prerequisites)

1. Commit and test existing Phase 4A.1 `pit/` module
2. Verify `BacktestProvenance.compute_result_hash()` stability with existing tests
3. Verify design document integrity (`docs/strategy_engine_design.md` final line)
4. Create `CalendarInterface` abstract protocol
5. Create `InstrumentIdentity` and `EffectiveDatedSpec` models
6. Create `TemporalBoundary` and `PitView` models (extend existing `pit/temporal.py`)
7. Create `RevisionEntry` and `RevisionHistory` models
8. Create `TieBreakerPolicy` model with deterministic serialization

**Exit criteria:** All existing tests pass. New models are frozen Pydantic with canonical serialization. `BacktestProvenance.compute_result_hash()` produces identical output.

### Subphase 4A.1: PIT View Construction

1. Create `PitViewBuilder` that constructs PIT-filtered datasets
2. Create `PitSidecar` model and `PitSidecarStore`
3. Create `PitViewValidator` that validates temporal eligibility
4. Create `PitView` hash computation (`compute_view_hash()`)
5. Create `PitExperimentConfig` with `pit_cutoff`, `revision_policy`, `calendar_version`
6. Create `ExperimentIdentity` model with `compute_experiment_id()`
7. Create `ApprovalMetadata` model

**Exit criteria:** PIT view construction is deterministic. `view_hash` differs from `dataset_hash`. `experiment_id` includes all required components. `result_hash` unchanged.

### Subphase 4A.2: Calendar and Session Infrastructure

1. Create `CalendarRegistry` and `VenueRegistry`
2. Create `HolidayCalendar` and `ExceptionClosure` models
3. Create `TradingSchedule` with overnight session support
4. Create `CalendarVersion` model with versioning
5. Create exchange-specific calendar definitions (minimum: one equity exchange, one FX market, one futures exchange)
6. Create `CalendarInterface` concrete implementations
7. Integrate calendar version into `ExperimentIdentity`

**Exit criteria:** Calendar version changes produce different experiment identities. Different exchanges have different session calendars. DST transitions handled correctly.

### Subphase 4A.3: Equities Module

1. Create `CorporateAction` models (Split, Dividend, SymbolChange, Delisting)
2. Create `PointInTimeUniverse` model
3. Create `AdjustmentChain` for adjusted/unadjusted prices
4. Create `EquityExchange` calendar
5. Create corporate action test cases
6. Create survivorship bias test cases

**Exit criteria:** Corporate actions create new instrument specifications, not data corrections. PIT views at time T show correct universe membership. Adjusted prices are separate from raw prices.

### Subphase 4A.4: Forex Module

1. Create `PairConvention` and `BaseQuoteSemantics` models
2. Create `SpreadModel` with explicit assumptions
3. Create `FinancingRate` time-series model
4. Create `ProviderSymbolMap` and symbol normalization
5. Create `FxSession` and `RolloverPolicy`
6. Create FX-specific test cases

**Exit criteria:** Bid/ask spread is explicit and configurable. Financing rates are time-series. Provider symbol mapping is versioned. PIT views correctly handle FX sessions.

### Subphase 4A.5: Futures Module

1. Create `FuturesContract` with expiry and contract metadata
2. Create `ContinuousSeries` with adjustment method
3. Create `RolloverPolicy` with explicit rules
4. Create `RollEvent` and `RollBoundary` models
5. Create `RollLeakageDetector`
6. Create futures-specific test cases

**Exit criteria:** Individual contracts and continuous series are distinct. Roll leakage is prevented. Continuous series adjustment method is explicit. Back-adjusted prices are not confused with raw contract prices.

### Subphase 4A.6: Integration and Validation

1. Create `ResearchContract` validation framework
2. Create `DataViewConstructor` and `PitViewBuilder` integration
3. Create `SyntheticDataScope` and evidence labeling
4. Create end-to-end test suite spanning all asset classes
5. Create cross-process determinism tests
6. Create legacy hash stability regression suite
7. Create red-team validation suite

**Exit criteria:** All asset classes work correctly. Research contracts are auditable. Synthetic data is properly labeled. All legacy Phase 3 tests pass.

---

## APPENDIX: VERIFICATION SUMMARY

### Verified Facts Summary

| Fact | Source | Status |
|------|--------|--------|
| Phase 3 complete with 367 tests | Test suite | VERIFIED |
| Latest commit `13fdc7e` | Git | VERIFIED |
| Branch `phase-4a/4a1-temporal-foundation` | Git | VERIFIED |
| `pit/` module is untracked | Git status | VERIFIED |
| `pit/` module `__version__ = "4.1.0"` | `src/data_engine/pit/__init__.py` | VERIFIED |
| `test_pit.py` is 949 lines | File size | VERIFIED |
| `AssetClass` has 6 members | `src/data_engine/schemas.py` | VERIFIED |
| `ContractType` has 4 members | `src/data_engine/schemas.py` | VERIFIED |
| `TemporalSemantics` has 6 temporal fields | `src/data_engine/pit/temporal.py` | VERIFIED |
| `ingestion_time` excluded from hashes | `src/data_engine/pit/temporal.py` | VERIFIED |
| All Pydantic models frozen | Source inspection | VERIFIED |
| No `os.popen`, `datetime.utcnow()`, `eval`, `exec` | Source inspection | VERIFIED |
| `BacktestConfig` uses serialized string fields | `src/data_engine/strategy/backtest.py` | VERIFIED |
| `StrategySpec.to_hash()` uses canonical serialization | `src/data_engine/strategy/schemas.py` | VERIFIED |
| `BacktestProvenance.compute_result_hash()` excludes runtime timestamps | `src/data_engine/strategy/provenance.py` | VERIFIED |
| Three-tier storage with deep-copy | `src/data_engine/storage.py` | VERIFIED |
| `DataQualityGate` blocks SYNTHETIC | `src/data_engine/data_blocked.py` | VERIFIED |
| Design doc final line has "COMPLETE" not "NO-GO" | `docs/strategy_engine_design.md` | VERIFIED |
| `Candle` has `provider_timestamp` wall-clock default | `src/data_engine/schemas.py` | VERIFIED |
| `Instruments.py` has `ASSET_SEMANTICS` dict | `src/data_engine/instruments.py` | VERIFIED |
| `EvidenceProvenance` has REAL, SYNTHETIC, SIMULATED, UNKNOWN | `src/data_engine/evidence.py` | VERIFIED |
| `quant_boundary.py` has `LLMBoundary` | `src/data_engine/quant_boundary.py` | VERIFIED |

### Design Review Status

All 13 required sections completed. No implementation authorized. All unresolved questions documented with impact analysis and concrete options. All red-team findings classified by severity with specific remediation paths.

---

`IMPLEMENTATION AUTHORIZATION: NOT_AUTHORIZED`