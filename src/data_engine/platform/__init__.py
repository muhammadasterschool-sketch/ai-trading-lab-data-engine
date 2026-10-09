"""Platform-expansion module package (mandate 2026-10-10).

Phases D–H of the platform-expansion mandate: strategy management lab,
instrument registry + workbook export, news intelligence, MT5 and
TradingView adapters. Every module is fail-closed, deterministic in
identity payloads (INV-01 discipline: identities are pure functions of
declared fields — never of wall-clock time), and advisory-only with
respect to the governed trading runtime: nothing in this package can
submit, alter or bypass orders, risk gates, kill switches or readiness.

PLATFORM_CONTRACT_VERSION follows the repository contract-versioning
discipline (see runtime/contracts.py RUNTIME_CONTRACT_VERSION).
"""

PLATFORM_CONTRACT_VERSION = "1.0.0"

from data_engine.platform.events import AuditLog, PlatformAuditEvent
from data_engine.platform.registry import (
    Capability,
    EligibilityStatus,
    InstrumentRecord,
    InstrumentRegistry,
    OperatorApprovalRecord,
    ProviderSymbolMapping,
    canonical_instrument_id,
)
from data_engine.platform.workbook import (
    MarketWatchEntry,
    OpenPositionRecord,
    StrategyPerformanceRecord,
    TradeRecord,
    WorkbookExporter,
)
from data_engine.platform.strategy_lab import (
    EvidenceRecord,
    LifecycleState,
    LifecycleError,
    OperatorApproval,
    StrategyLab,
    StrategyRecord,
    StrategyType,
    StrategyVersion,
)
from data_engine.platform.news import (
    EconomicEvent,
    NewsCategory,
    NewsIntelligenceService,
    NewsItem,
    Sentiment,
    VerificationStatus,
)
from data_engine.platform.mt5 import (
    AccountMode,
    MT5AccountInfo,
    MT5Adapter,
    MT5Candle,
    MT5ConnectionState,
    MT5OrderRefusedError,
    MT5SymbolSpec,
    MT5UnavailableError,
)
from data_engine.platform.tradingview import (
    TVEventCategory,
    TVSignalPayload,
    TVSignalRefusal,
    TVSignalValidator,
    ValidatedTVSignal,
    expected_digest,
)
from data_engine.platform.datasets import (
    CsvDatasetAudit,
    CsvKind,
    InstrumentAudit,
    PlatformDatasetRecord,
    audit_csv_file,
    ingest_csv_dataset,
)

__all__ = [
    "PLATFORM_CONTRACT_VERSION",
    "AuditLog",
    "PlatformAuditEvent",
    "Capability",
    "EligibilityStatus",
    "InstrumentRecord",
    "InstrumentRegistry",
    "ProviderSymbolMapping",
    "canonical_instrument_id",
    "OperatorApprovalRecord",
    "MarketWatchEntry",
    "TradeRecord",
    "StrategyPerformanceRecord",
    "OpenPositionRecord",
    "WorkbookExporter",
    "LifecycleState",
    "LifecycleError",
    "EvidenceRecord",
    "OperatorApproval",
    "StrategyLab",
    "StrategyRecord",
    "StrategyType",
    "StrategyVersion",
    "EconomicEvent",
    "NewsCategory",
    "NewsIntelligenceService",
    "NewsItem",
    "Sentiment",
    "VerificationStatus",
    "AccountMode",
    "MT5AccountInfo",
    "MT5Adapter",
    "MT5Candle",
    "MT5ConnectionState",
    "MT5OrderRefusedError",
    "MT5SymbolSpec",
    "MT5UnavailableError",
    "TVEventCategory",
    "TVSignalPayload",
    "TVSignalRefusal",
    "TVSignalValidator",
    "ValidatedTVSignal",
    "expected_digest",
    "CsvDatasetAudit",
    "CsvKind",
    "InstrumentAudit",
    "PlatformDatasetRecord",
    "audit_csv_file",
    "ingest_csv_dataset",
]
