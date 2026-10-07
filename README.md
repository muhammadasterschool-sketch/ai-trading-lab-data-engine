# AI Trading Lab — Data Engine

Production-grade deterministic market-data engine for the AI Trading Lab.

## Architecture

```
Market Data Sources
        ↓
Raw Data Ingestion
        ↓
Data Validation
        ↓
Normalization
        ↓
Canonical Market Dataset
        ↓
Historical Storage
        ↓
Research / Quant / Backtest APIs
```

## Core Principles

1. **Provider Independence** — Multiple providers supported via abstraction layer
2. **Timeframe Integrity** — Timeframes are never silently converted
3. **Data Validation** — Every dataset is validated before entering the canonical store
4. **Provenance** — Every dataset answers "Exactly which data produced this backtest?"
5. **Raw/Processed/Research Separation** — Three-tier storage with immutability guarantees
6. **Evidence Integrity** — REAL, SYNTHETIC, SIMULATED, UNKNOWN labels enforced
7. **Deterministic/LLM Boundary** — LLM orchestrates; code computes
8. **DATA_QUALITY_BLOCKED** — Downstream analysis stops when quality is insufficient
9. **Security** — Input validation, secret isolation, no code execution from datasets

## Quick Start

```python
from data_engine.schemas import Candle, Timeframe, Instrument, AssetClass
from data_engine.validation import DataValidator
from data_engine.ingestion import DataIngester
from data_engine.storage import DataStorage
from data_engine.data_blocked import DataQualityGate

# Create a candle
candle = Candle(
    timestamp=datetime.utcnow(),
    open=100.0, high=105.0, low=98.0, close=102.0,
    volume=1000.0, timeframe=Timeframe.D1,
)

# Validate
validator = DataValidator()
results = validator.validate_dataset(dataset)
```

## Module Structure

| Module | Purpose |
|--------|---------|
| `schemas.py` | Canonical Pydantic models |
| `timeframes.py` | Timeframe handling, effective lookback calculation |
| `instruments.py` | Canonical instrument model, asset-class semantics |
| `provider.py` | Provider abstraction (MarketDataProvider, ProviderFactory) |
| `ingestion.py` | Raw data ingestion, validation, canonical dataset creation |
| `validation.py` | Deterministic data validation engine |
| `storage.py` | RAW/PROCESSED/RESEARCH three-tier storage |
| `provenance.py` | Dataset versioning and provenance tracking |
| `quarantine.py` | Quarantine system for invalid data |
| `quality_report.py` | Automated data quality reporting |
| `evidence.py` | Evidence integrity (REAL/SYNTHETIC/SIMULATED/UNKNOWN) |
| `data_blocked.py` | DATA_QUALITY_BLOCKED exception and gate |
| `security.py` | Security controls, secret isolation, audit logging |
| `quant_boundary.py` | Deterministic/LLM boundary enforcement |
| `cli.py` | CLI entry point |
| `quant/` | **Phase 2** Deterministic Quant Engine |
| `quant/__init__.py` | Package exports, version |
| `quant/schemas.py` | Typed result structures |
| `quant/validation.py` | Input validation at quant boundary |
| `quant/core.py` | Main QuantEngine entry point |
| `quant/returns.py` | Simple, log, cumulative returns |
| `quant/moving_averages.py` | SMA, EMA |
| `quant/momentum.py` | RSI |
| `quant/volatility.py` | ATR, rolling std, realized volatility |
| `quant/trend.py` | EMA/SMA 20/50/200, trend states |
| `quant/statistics.py` | Mean, median, variance, std, correlation, z-score |
| `quant/drawdown.py` | Drawdown, max drawdown, duration |
|| `quant/registry.py` | Indicator registry |
| `strategy/` | **Phase 3** Strategy & Backtest Engine |
| `strategy/__init__.py` | Package exports, version |
| `strategy/schemas.py` | Immutable strategy specs, orders, positions |
| `strategy/execution.py` | Deterministic execution model, costs, slippage |
| `strategy/backtest.py` | BacktestEngine, chronological processing |
| `strategy/metrics.py` | All deterministic backtest metrics |
| `strategy/validation.py` | Strategy validation, leakage detection |
| `strategy/provenance.py` | Backtest provenance tracking |
| `strategy/trades.py` | Immutable trade ledger |
| `strategy/positions.py` | Equity tracker, position tracker |

## Gold-Trading-Lab Integration

The Data Engine is compatible with `gold-trading-lab`. Key integration points:

- XAU/USD instrument via `create_xau_usd_instrument()`
- Timeframe separation enforced (Daily vs H4 are distinct datasets)
- Evidence provenance flows through to all downstream research
- Existing gold-trading-lab research findings are NOT modified by the Data Engine

## No Live Trading

This Data Engine does NOT implement or enable:
- Live broker orders
- Autonomous capital deployment
- Real-money execution
- Automatic position opening

## Security

- API keys from environment variables only
- Secrets redacted in logs and data structures
- No arbitrary code execution from datasets
- Immutable provenance records
- Audit logging for all security-relevant actions

## License

MIT

## Phase Map (4A.1 remediation complete → lifecycle/autonomy layer complete)

```
src/data_engine/
    pit/                    4A.1   temporal/PIT foundation (identity contracts,
                                  canonical serialization, PitView, experiments)
    actions/                4A.2   corporate actions, adjustment chains,
                                  survivorship-bias-free universes, calendars
    derivatives/            4A.3   futures contracts, rollover policies,
                                  continuous series (leakage-guarded)
    research/               4A.4   research governance (no self-approval)
    experiment_registry/    5      experiment registry + reproducibility logs
    quant/                  2/6    deterministic quant engine + PIT feature
                                  pipeline (quant/features.py)
    research_validation/    7      bias/leakage detection, statistics (scipy-free),
                                  walk-forward, robustness
    risk/                   8      hard-limit risk engine (kill switch),
                                  exposure, inverse-vol portfolio construction
    hermes/                 9      agent contracts (unavailable permissions),
                                  free-first model routing, orchestration audit
    infra/                  10     reproducibility verification, observability,
                                  monitoring, checkpoint recovery
    paper/                  11     paper trading (realism simulator, gateway,
                                  reconciliation) + 30-day evaluation +
                                  graduation/retirement + LiveAuthorizationGate
    discovery/              12     strategy discovery (bounded deterministic
                                  grids, validated-only registry) + the
                                  fail-closed execution-eligibility chain
    knowledge/              18     knowledge/memory records — fact/
                                  observation/hypothesis/model-output/
                                  human-decision; unvalidated model output
                                  is never authoritative evidence
    benchmarks/             30     performance suite over real components;
                                  deterministic operation counts; NO-TRADE
                                  capability proven
```

**Live execution boundary:** NEVER authorized by this codebase. The
`LiveAuthorizationGate` denies by default; a grant requires a
human-issued token from a registry that starts empty and refuses
machine principals (blueprint 5.59).

**Closure records:** `PHASE_4A1_IMPLEMENTATION_RECORD.md` (4A.1),
`PHASES_4A2_TO_GRADUATION_IMPLEMENTATION_RECORD.md` (4A.2→graduation),
`PHASES_DISCOVERY_TO_AUTONOMY_IMPLEMENTATION_RECORD.md` (discovery/knowledge/benchmarks/lifecycle).
