"""The broker-neutral adapter interface (multi-broker mandate, Phase M1).

One abstract surface every execution venue must implement:

- connect / disconnect / health status
- account information (mode, currency, position mode, leverage)
- instrument metadata (normalized precision / lot / notional rules)
- order submission (idempotent), cancellation, status lookup, fills
- positions, balances
- venue reconciliation against the session journal's expectations
- normalized errors ONLY (venue-native codes preserved as audit data)

Position of this interface in the architecture:

    strategy / runtime  →  central RiskGate + KillSwitch  →  BrokerSession
                                                              ↓
                                                    BrokerAdapter (THIS)
                                                              ↓
                                        paper-mock | mt5-mock | binance-mock
                                        | bybit-mock | (future) real adapters

The strategy layer and the central risk controls NEVER import an
adapter; they submit through the session, which enforces the gates
BEFORE the adapter is reached (mandate requirement: "strategy and
central risk controls independent of broker-specific code").

Every method is synchronous and deterministic in Phase M1 (mocks);
the signature set is deliberately narrow so a future async or
threaded real adapter can bridge it without renegotiating the
contract.
"""

from abc import ABC, abstractmethod
from typing import Mapping, Optional, Sequence, Tuple

from data_engine.brokers.capabilities import BrokerCapabilities
from data_engine.brokers.models import (
    AccountInfo,
    BalanceRecord,
    ConnectionState,
    ExpectedOrderState,
    InstrumentSpec,
    OrderAck,
    OrderRequest,
    PositionRecord,
    VenueFill,
    VenueReconciliationReport,
)


class BrokerAdapter(ABC):
    """Abstract broker-neutral execution venue.

    Contract notes shared by ALL adapters:

    - **Account isolation**: ``connect`` binds the adapter to exactly
      ONE account (the credential's account). Every subsequent call
      refuses any other account id — defense in depth against
      cross-account leakage.
    - **Idempotency**: submitting the same ``client_order_id`` twice
      returns the SAME acknowledgement and never executes twice.
    - **Definitive rejections** are normal ``REJECTED`` acks (with
      ``venue_code``/``reject_reason``); transport failures raise
      typed errors from :mod:`data_engine.brokers.errors`.
    - **UNKNOWN outcomes** raise :class:`UnknownOrderStateError` —
      the caller must journal UNKNOWN and reconcile before retrying.
    - **No credential material** may ever appear in return values,
      error messages or logs.
    """

    @property
    @abstractmethod
    def broker_id(self) -> str:
        """Stable unique venue identifier (matches the registry)."""

    @property
    @abstractmethod
    def capabilities(self) -> BrokerCapabilities:
        """This adapter's capability descriptor (single source of truth)."""

    # -- lifecycle -------------------------------------------------------

    @abstractmethod
    def connect(self, credential) -> None:
        """Bind to ONE account and connect.

        Raises ``AUTH``-category errors on rejection (including the
        repository-wide refusal of REAL account modes in this phase).
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect (idempotent). Subsequent calls fail closed."""

    @abstractmethod
    def health(self) -> ConnectionState:
        """Current connection state (never raises)."""

    # -- account + instruments -------------------------------------------

    @abstractmethod
    def account_info(self) -> AccountInfo:
        """Normalized info for the CONNECTED account."""

    @abstractmethod
    def instrument_spec(self, symbol: str) -> InstrumentSpec:
        """Normalized instrument metadata; unknown symbols fail closed
        (INVALID_ORDER-category error — never a guessed spec)."""

    @abstractmethod
    def list_symbols(self) -> Tuple[str, ...]:
        """Canonical symbols this venue currently serves."""

    # -- orders ----------------------------------------------------------

    @abstractmethod
    def submit_order(self, request: OrderRequest) -> OrderAck:
        """Submit one order (idempotent per ``client_order_id``)."""

    @abstractmethod
    def cancel_order(self, client_order_id: str) -> OrderAck:
        """Cancel one order (idempotent; terminal orders are returned
        unchanged — never an error for an already-terminal order)."""

    @abstractmethod
    def order_status(self, client_order_id: str) -> OrderAck:
        """Venue truth for one order (UNKNOWN id fails closed)."""

    @abstractmethod
    def order_fills(self, client_order_id: str) -> Tuple[VenueFill, ...]:
        """All fills of one order, in execution order."""

    # -- account state ----------------------------------------------------

    @abstractmethod
    def positions(self) -> Tuple[PositionRecord, ...]:
        """Netted position snapshot (BALANCES_ONLY venues: empty)."""

    @abstractmethod
    def balances(self) -> Tuple[BalanceRecord, ...]:
        """Asset balances of the connected account."""

    # -- reconciliation ----------------------------------------------------

    @abstractmethod
    def reconcile(
        self,
        expected: Sequence[ExpectedOrderState],
    ) -> VenueReconciliationReport:
        """Compare journal expectations against venue truth.

        UNKNOWN journal records resolvable to a definitive venue
        status are REPORTED as resolutions (venue is the execution
        authority); phantom / missing / conflicting records are
        mismatches. The adapter reports — it never repairs.
        """


#: The abstract surface is deliberately EXACTLY these methods; the
#: contract tests enumerate them to fail closed on accidental growth
#: (an unreviewed method added to the interface is a design change).
BROKER_ADAPTER_SURFACE: Tuple[str, ...] = (
    "broker_id",
    "capabilities",
    "connect",
    "disconnect",
    "health",
    "account_info",
    "instrument_spec",
    "list_symbols",
    "submit_order",
    "cancel_order",
    "order_status",
    "order_fills",
    "positions",
    "balances",
    "reconcile",
)


__all__ = [
    "BrokerAdapter",
    "BROKER_ADAPTER_SURFACE",
]
