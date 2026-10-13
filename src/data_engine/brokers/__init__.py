"""Broker-neutral execution layer (multi-broker architecture mandate).

Phase M1 + Batch 7 + Batch 15 — the normalized interface, capability
registry, credential redaction, guarded session and SEVEN
DETERMINISTIC MOCK adapters:

- paper/simulation (reference surface)
- MT5-compatible class (generic terminal semantics)
- Exness (MT5 terminal class — Batch 15)
- XM (MT5 terminal class — Batch 15)
- Binance spot (REST/filter semantics)
- Bybit v5 (spot/linear order semantics)
- Bitget spot v2 (clientOrderId semantics)

PAPER/TEST ONLY: no network, no real credentials, no real orders.
Live trading is NOT AUTHORIZED in this repository; real adapters are
future, separately-reviewed phases behind the same interface.

Architecture (see docs/MULTI_BROKER_EXECUTION_ARCHITECTURE.md):

    strategy / runtime → central RiskGate + KillSwitch → BrokerSession
                                                             ↓
                                                   BrokerAdapter (interface)
                                                             ↓
                                                   mock adapters (M1)
"""

from data_engine.brokers.adapters import (
    BinanceSpotMockAdapter,
    BitgetSpotMockAdapter,
    BybitV5MockAdapter,
    ExnessMT5MockAdapter,
    MT5StyleMockAdapter,
    PaperBrokerAdapter,
    XMMT5MockAdapter,
)
from data_engine.brokers.capabilities import (
    BINANCE_MOCK_CAPABILITIES,
    BITGET_MOCK_CAPABILITIES,
    BYBIT_MOCK_CAPABILITIES,
    BrokerCapabilities,
    CapabilityRegistry,
    CapabilityRegistryError,
    ExecutionMode,
    EXNESS_MOCK_CAPABILITIES,
    IdempotencyKeyMechanism,
    MT5_MOCK_CAPABILITIES,
    PAPER_MOCK_CAPABILITIES,
    RateLimitPolicy,
    ReconciliationStyle,
    SlTpSemantics,
    XM_MOCK_CAPABILITIES,
    default_registry,
)
from data_engine.brokers.errors import (
    REDACTED_PLACEHOLDER,
    BrokerErrorCategory,
    BrokerExecutionError,
    OrderRefusedError,
    RateLimitError,
    RETRYABLE_CATEGORIES,
    UnknownOrderStateError,
    UnsupportedOrderError,
    capability_mismatch_reason,
    redact_mapping,
    scrub_text,
)
from data_engine.brokers.interface import BROKER_ADAPTER_SURFACE, BrokerAdapter
from data_engine.brokers.models import (
    BROKER_NEUTRAL_CONTRACT_VERSION,
    AccountInfo,
    AccountMode,
    BalanceRecord,
    ConnectionState,
    ExpectedOrderState,
    InstrumentSpec,
    OrderAck,
    OrderKind,
    OrderRequest,
    PositionMode,
    PositionRecord,
    ReconciliationMismatch,
    ReconciliationMismatchKind,
    Side,
    TimeInForce,
    VenueFill,
    VenueOrderStatus,
    VenueReconciliationReport,
)
from data_engine.brokers.redaction import (
    BrokerCredential,
    CredentialError,
    assert_no_secret_material,
    find_secret_leak,
    redact_mapping as _redact_mapping_alias,
    scrub_secrets,
)
from data_engine.brokers.session import (
    BROKER_SESSION_JOURNAL_SCHEMA,
    BrokerSession,
    JournalRecord,
    KillSwitchState,
    RetryPolicy,
    RiskDecision,
    SessionJournalError,
)
from data_engine.brokers.instruments import (
    CatalogEntry,
    InstrumentCatalog,
    RegistrySyncReport,
    discover_instruments,
    sync_catalog_to_platform_registry,
)

__all__ = [
    # contract + models
    "BROKER_NEUTRAL_CONTRACT_VERSION",
    "Side",
    "OrderKind",
    "TimeInForce",
    "VenueOrderStatus",
    "ConnectionState",
    "AccountMode",
    "PositionMode",
    "InstrumentSpec",
    "OrderRequest",
    "OrderAck",
    "VenueFill",
    "PositionRecord",
    "BalanceRecord",
    "AccountInfo",
    "ExpectedOrderState",
    "ReconciliationMismatch",
    "ReconciliationMismatchKind",
    "VenueReconciliationReport",
    # errors
    "BrokerErrorCategory",
    "RETRYABLE_CATEGORIES",
    "BrokerExecutionError",
    "RateLimitError",
    "UnknownOrderStateError",
    "OrderRefusedError",
    "UnsupportedOrderError",
    "capability_mismatch_reason",
    "scrub_text",
    "redact_mapping",
    "REDACTED_PLACEHOLDER",
    # capabilities
    "SlTpSemantics",
    "IdempotencyKeyMechanism",
    "ReconciliationStyle",
    "ExecutionMode",
    "RateLimitPolicy",
    "BrokerCapabilities",
    "CapabilityRegistry",
    "CapabilityRegistryError",
    "PAPER_MOCK_CAPABILITIES",
    "MT5_MOCK_CAPABILITIES",
    "EXNESS_MOCK_CAPABILITIES",
    "XM_MOCK_CAPABILITIES",
    "BINANCE_MOCK_CAPABILITIES",
    "BYBIT_MOCK_CAPABILITIES",
    "BITGET_MOCK_CAPABILITIES",
    "default_registry",
    # redaction
    "BrokerCredential",
    "CredentialError",
    "scrub_secrets",
    "find_secret_leak",
    "assert_no_secret_material",
    # interface
    "BrokerAdapter",
    "BROKER_ADAPTER_SURFACE",
    # session
    "BrokerSession",
    "RiskDecision",
    "KillSwitchState",
    "RetryPolicy",
    "JournalRecord",
    "SessionJournalError",
    "BROKER_SESSION_JOURNAL_SCHEMA",
    # adapters (deterministic mocks — Phase M1 + Batch 7 Bitget + Batch 15 Exness/XM)
    "PaperBrokerAdapter",
    "MT5StyleMockAdapter",
    "ExnessMT5MockAdapter",
    "XMMT5MockAdapter",
    "BinanceSpotMockAdapter",
    "BybitV5MockAdapter",
    "BitgetSpotMockAdapter",
    # instrument discovery / catalog / registry sync (Batch 7)
    "CatalogEntry",
    "InstrumentCatalog",
    "RegistrySyncReport",
    "discover_instruments",
    "sync_catalog_to_platform_registry",
]
