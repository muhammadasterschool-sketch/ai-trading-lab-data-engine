"""Deterministic in-memory mock venue engine (multi-broker mandate,
Phase M1 — INTERNAL shared machinery for the four mock adapters).

Guarantees (test-facing contract):

- **No network, no threads, no RNG, no wall clock.** An injectable
  ``clock`` callable is MANDATORY; every timestamp and rate-limit
  window decision derives from it, so identical call sequences produce
  byte-identical outcomes (venue ids are sequence counters).
- **Idempotency at the venue boundary**: a duplicate
  ``client_order_id`` returns the stored acknowledgement and never
  executes twice (mirrors real venues with client-order-id support).
- **Account isolation**: ``connect`` binds exactly one account; any
  request naming another account fails closed (AUTH-category error).
- **Fail-closed validation**: unsupported order kinds / TIFs / attached
  SL-TP shapes / unaligned precision are refused — capability and
  instrument facts are enforced HERE as defense in depth behind the
  session's pre-venue checks.
- **Definitive rejections are REJECTED acks** (venue-native code in
  ``venue_code``); transport failures raise typed errors.
- **Failure injection is explicit and deterministic**:
  ``inject_disconnect`` / ``inject_rate_limit`` / ``inject_ack_timeout``
  / ``inject_rejection`` / ``inject_extra_fill`` — the failure-injection
  test surface (mandate deliverable). Injections apply BEFORE order
  acceptance (unambiguous) except ``inject_ack_timeout``, which models
  the realistic accepted-but-unacknowledged case.
- **Reconciliation reports, never repairs**: phantom/missing/conflicting
  records surface as mismatches; UNKNOWN journal records that the venue
  can resolve are reported as resolutions (venue is the execution
  authority).

Spot-like balance accounting (base/quote exchange on fills) is the
default; MT5-style adapters override ``_apply_fill_accounting`` and
``positions`` for ticket/hedging semantics.
"""

from collections import deque
from datetime import datetime
from decimal import Decimal
from typing import Callable, Deque, Dict, List, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.brokers.capabilities import (
    BrokerCapabilities,
    ExecutionMode,
    SlTpSemantics,
)
from data_engine.brokers.errors import (
    BrokerErrorCategory,
    BrokerExecutionError,
    RateLimitError,
    UnknownOrderStateError,
)
from data_engine.brokers.interface import BrokerAdapter
from data_engine.brokers.models import (
    AccountInfo,
    AccountMode,
    BalanceRecord,
    ConnectionState,
    ExpectedOrderState,
    InstrumentSpec,
    OrderAck,
    OrderKind,
    OrderRequest,
    PositionRecord,
    ReconciliationMismatch,
    ReconciliationMismatchKind,
    Side,
    TimeInForce,
    VenueFill,
    VenueOrderStatus,
    VenueReconciliationReport,
    DEFINITIVE_STATUSES,
)
from data_engine.brokers.redaction import BrokerCredential


class MockVenueError(RuntimeError):
    """Raised on mock-venue construction/usage contract violations."""


class _VenueOrder(BaseModel):
    """Internal authoritative record of one order at the mock venue."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request: OrderRequest
    venue_order_id: str
    status: VenueOrderStatus
    submitted_at: datetime
    fills: Tuple[VenueFill, ...] = ()
    reject_reason: Optional[str] = None
    venue_code: Optional[str] = None

    @property
    def filled_quantity(self) -> Decimal:
        return sum((f.quantity for f in self.fills), Decimal("0"))

    def to_ack(self, broker_id: str) -> OrderAck:
        return OrderAck(
            client_order_id=self.request.client_order_id,
            venue_order_id=self.venue_order_id,
            account_id=self.request.account_id,
            broker_id=broker_id,
            symbol=self.request.symbol,
            side=self.request.side,
            order_kind=self.request.order_kind,
            quantity=self.request.quantity,
            status=self.status,
            submitted_at=self.submitted_at,
            reject_reason=self.reject_reason,
            venue_code=self.venue_code,
        )


class DeterministicMockVenue(BrokerAdapter):
    """Shared deterministic venue engine (see module docstring).

    Subclasses (paper / mt5-style / binance-style / bybit-style) supply
    ``capabilities``, ``instruments``, ``initial_balances``, ``currency``
    and venue-specific error-code mapping hooks; they may override the
    accounting hooks for their native semantics.
    """

    def __init__(
        self,
        *,
        capabilities: BrokerCapabilities,
        instruments: Sequence[InstrumentSpec],
        initial_balances: Mapping[str, Decimal],
        currency: str,
        clock: Callable[[], datetime],
        account_mode: AccountMode = AccountMode.DEMO,
        fee_rate: Decimal = Decimal("0"),
    ) -> None:
        if capabilities is None or not isinstance(capabilities, BrokerCapabilities):
            raise MockVenueError("mock venue requires its BrokerCapabilities descriptor")
        if capabilities.execution_mode is not ExecutionMode.MOCK_DETERMINISTIC:
            raise MockVenueError(
                "only MOCK_DETERMINISTIC adapters are constructible in this "
                "phase — live trading is NOT AUTHORIZED in this repository"
            )
        if account_mode not in capabilities.account_modes:
            raise MockVenueError(
                f"account mode {account_mode.value} is not declared by "
                f"{capabilities.broker_id} (declared: "
                f"{[m.value for m in capabilities.account_modes]}) — REAL "
                "account modes are refused by construction this phase"
            )
        if not callable(clock):
            raise MockVenueError(
                "an injectable clock callable is MANDATORY (determinism: no "
                "wall clock, no RNG)"
            )
        if not instruments:
            raise MockVenueError("a venue needs at least one instrument spec")
        self._capabilities = capabilities
        self._broker_id = capabilities.broker_id
        self._instruments: Dict[str, InstrumentSpec] = {}
        for spec in instruments:
            if spec.broker_id != capabilities.broker_id:
                raise MockVenueError(
                    f"instrument {spec.symbol} declares broker {spec.broker_id}, "
                    f"not {capabilities.broker_id}"
                )
            self._instruments[spec.symbol] = spec
        self._initial_balances = {
            asset: Decimal(amount)
            for asset, amount in initial_balances.items()
        }
        self._currency = currency
        self._account_mode = account_mode
        self._fee_rate = Decimal(fee_rate)
        self._clock = clock

        self._state = ConnectionState.DISCONNECTED
        self._credential: Optional[BrokerCredential] = None
        self._bound_account: Optional[str] = None
        self._orders: Dict[str, _VenueOrder] = {}
        self._seq = 0
        self._balances: Dict[str, Decimal] = dict(self._initial_balances)
        self._api_window: Deque[datetime] = deque()
        self._order_window: Deque[datetime] = deque()
        self._submit_attempts = 0
        self._executed_orders = 0

        # -- failure injection state (explicit, deterministic) ----------
        self._injected_disconnect = False
        self._injected_rate_limit_next = 0
        self._injected_ack_timeout = False
        self._injected_rejection: Optional[Tuple[str, str]] = None
        self._market_fill_fraction: Optional[Decimal] = None

    # ------------------------------------------------------------------
    # Adapter identity
    # ------------------------------------------------------------------
    @property
    def broker_id(self) -> str:
        return self._broker_id

    @property
    def capabilities(self) -> BrokerCapabilities:
        return self._capabilities

    @property
    def account_mode(self) -> AccountMode:
        return self._account_mode

    # -- observability counters (test assertions) ------------------------
    @property
    def submit_attempts(self) -> int:
        """Every submit_order CALL (including duplicates/injections)."""
        return self._submit_attempts

    @property
    def executed_orders(self) -> int:
        """Orders the venue actually ACCEPTED as new (excludes duplicates)."""
        return self._executed_orders

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def connect(self, credential) -> None:
        if not isinstance(credential, BrokerCredential):
            raise BrokerExecutionError(
                "connect requires a BrokerCredential holder (opaque, "
                "redacted by construction)",
                category=BrokerErrorCategory.AUTH,
                broker_id=self._broker_id,
            )
        if self._injected_disconnect:
            # A sustained injected outage: connect itself fails until the
            # injection is cleared or reconnect is attempted post-clear.
            raise BrokerExecutionError(
                "connect refused: sustained injected outage is active",
                category=BrokerErrorCategory.CONNECTIVITY,
                broker_id=self._broker_id,
            )
        if self._bound_account is not None and not credential.matches_account(
            self._bound_account
        ):
            raise BrokerExecutionError(
                "adapter is already bound to another account — one adapter "
                "instance serves exactly one account (isolation)",
                category=BrokerErrorCategory.AUTH,
                broker_id=self._broker_id,
                venue_code="ACCOUNT_ISOLATION_MISMATCH",
            )
        self._credential = credential
        self._bound_account = credential.account_id
        self._state = ConnectionState.CONNECTED

    def disconnect(self) -> None:
        self._state = ConnectionState.DISCONNECTED

    def health(self) -> ConnectionState:
        if self._injected_disconnect:
            return ConnectionState.DISCONNECTED
        return self._state

    def _api_guard(self) -> None:
        """Fail-closed prelude for every venue API call."""
        if self.health() is not ConnectionState.CONNECTED:
            raise BrokerExecutionError(
                f"venue {self._broker_id} is {self.health().value} — "
                "failing closed (reconnect required)",
                category=BrokerErrorCategory.CONNECTIVITY,
                broker_id=self._broker_id,
            )
        if self._bound_account is None:
            raise BrokerExecutionError(
                "adapter is not connected to any account",
                category=BrokerErrorCategory.CONNECTIVITY,
                broker_id=self._broker_id,
            )
        self._enforce_request_budget()

    def _require_account(self, account_id: str) -> None:
        if self._bound_account is None or account_id != self._bound_account:
            raise BrokerExecutionError(
                f"request names account {account_id!r} but this adapter is "
                f"bound to {self._bound_account!r} — account isolation "
                "refusal (defense in depth)",
                category=BrokerErrorCategory.AUTH,
                broker_id=self._broker_id,
                venue_code="ACCOUNT_ISOLATION_MISMATCH",
            )

    def _enforce_request_budget(self) -> None:
        cap = self._capabilities.rate_limit.max_requests_per_window
        if cap <= 0:
            return
        now = self._clock()
        window = self._capabilities.rate_limit.window_seconds
        while self._api_window and (now - self._api_window[0]).total_seconds() > window:
            self._api_window.popleft()
        if len(self._api_window) >= cap:
            raise RateLimitError(
                f"request budget exhausted ({cap} calls / {window}s) at "
                f"venue {self._broker_id}",
                broker_id=self._broker_id,
                venue_code=self._request_limit_code(),
                retry_after_seconds=self._capabilities.rate_limit.retry_after_seconds,
            )
        self._api_window.append(now)

    def _enforce_order_budget(self) -> None:
        cap = self._capabilities.rate_limit.max_orders_per_window
        if cap <= 0:
            return
        now = self._clock()
        window = self._capabilities.rate_limit.window_seconds
        while self._order_window and (now - self._order_window[0]).total_seconds() > window:
            self._order_window.popleft()
        if len(self._order_window) >= cap:
            raise RateLimitError(
                f"order placement budget exhausted ({cap} orders / {window}s) "
                f"at venue {self._broker_id}",
                broker_id=self._broker_id,
                venue_code=self._order_limit_code(),
                retry_after_seconds=self._capabilities.rate_limit.retry_after_seconds,
            )
        self._order_window.append(now)

    # -- venue-native code hooks (subclasses map their real codes) -------
    def _request_limit_code(self) -> str:
        return "RATE_LIMITED"

    def _order_limit_code(self) -> str:
        return "RATE_LIMITED"

    def _precision_rejection_code(self) -> str:
        return "INVALID_ORDER"

    def _insufficient_funds_code(self) -> str:
        return "INSUFFICIENT_FUNDS"

    def _unknown_order_code(self) -> str:
        return "UNKNOWN_ORDER"

    # ------------------------------------------------------------------
    # Account + instruments
    # ------------------------------------------------------------------
    def account_info(self) -> AccountInfo:
        self._api_guard()
        return AccountInfo(
            broker_id=self._broker_id,
            account_id=self._bound_account,
            account_mode=self._account_mode,
            currency=self._currency,
            position_mode=self._capabilities.position_mode,
            leverage=None,
            display_name=self._capabilities.display_name,
        )

    def instrument_spec(self, symbol: str) -> InstrumentSpec:
        self._api_guard()
        spec = self._instruments.get(symbol)
        if spec is None:
            raise BrokerExecutionError(
                f"symbol {symbol!r} is not served by {self._broker_id} "
                "(served: " + ", ".join(sorted(self._instruments)) + ") — "
                "never assume a symbol exists at a venue",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self._broker_id,
                venue_code=self._unknown_symbol_code(),
            )
        return spec

    def _unknown_symbol_code(self) -> str:
        return "UNKNOWN_SYMBOL"

    def list_symbols(self) -> Tuple[str, ...]:
        self._api_guard()
        return tuple(sorted(self._instruments))

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def submit_order(self, request: OrderRequest) -> OrderAck:
        self._api_guard()
        self._require_account(request.account_id)
        self._submit_attempts += 1

        # Idempotent duplicate: return the stored outcome, never re-execute.
        existing = self._orders.get(request.client_order_id)
        if existing is not None:
            return existing.to_ack(self._broker_id)

        # Injected sustained rate-limit (applied BEFORE acceptance — the
        # venue provably holds NO order for this id afterwards).
        if self._injected_rate_limit_next > 0:
            self._injected_rate_limit_next -= 1
            raise RateLimitError(
                f"injected rate limit at {self._broker_id} for "
                f"{request.client_order_id} (attempts left: "
                f"{self._injected_rate_limit_next})",
                broker_id=self._broker_id,
                venue_code=self._order_limit_code(),
                retry_after_seconds=self._capabilities.rate_limit.retry_after_seconds,
            )
        self._enforce_order_budget()

        spec = self._instruments.get(request.symbol)
        if spec is None:
            raise BrokerExecutionError(
                f"symbol {request.symbol!r} is not served by {self._broker_id}",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self._broker_id,
                venue_code=self._unknown_symbol_code(),
            )

        # Defense-in-depth capability + precision enforcement (the session
        # already refused these shapes BEFORE calling the venue).
        rejection = self._venue_validate(request, spec)
        if rejection is None:
            rejection = self._check_sufficient_funds(request, spec)
        if rejection is not None:
            code, reason = rejection
            return self._record_order(request, VenueOrderStatus.REJECTED,
                                      reject_reason=reason, venue_code=code)

        # Injected definitive rejection.
        if self._injected_rejection is not None:
            code, reason = self._injected_rejection
            self._injected_rejection = None
            return self._record_order(request, VenueOrderStatus.REJECTED,
                                      reject_reason=reason, venue_code=code)

        ack = self._accept_order(request, spec)

        # Injected ambiguous outcome: the venue HAS accepted (state above),
        # but the caller cannot know — model of an ack timeout after accept.
        if self._injected_ack_timeout:
            self._injected_ack_timeout = False
            raise UnknownOrderStateError(
                f"injected ack timeout at {self._broker_id}: order "
                f"{request.client_order_id} MAY be live at the venue — "
                "journal UNKNOWN and reconcile before ANY retry",
                broker_id=self._broker_id,
                client_order_id=request.client_order_id,
            )
        return ack

    def _venue_validate(
        self, request: OrderRequest, spec: InstrumentSpec
    ) -> Optional[Tuple[str, str]]:
        """Venue-side fail-closed validation → definitive REJECTED ack.

        Returns (venue_code, reason) for a rejection, None when valid.
        """
        caps = self._capabilities
        if not caps.supports_order_kind(request.order_kind):
            return (
                self._precision_rejection_code(),
                f"order kind {request.order_kind.value} is not supported by "
                f"{self._broker_id} (supported: "
                f"{[k.value for k in caps.order_kinds]})",
            )
        if not caps.supports_time_in_force(request.time_in_force):
            return (
                self._precision_rejection_code(),
                f"time-in-force {request.time_in_force.value} is not "
                f"supported by {self._broker_id}",
            )
        if (request.stop_loss is not None or request.take_profit is not None) and \
                caps.sl_tp is not SlTpSemantics.ATTACHED:
            return (
                self._precision_rejection_code(),
                f"{self._broker_id} does not support ATTACHED stop-loss/"
                f"take-profit (semantics: {caps.sl_tp.value})",
            )
        if request.reduce_only and not caps.supports_reduce_only:
            return (
                self._precision_rejection_code(),
                f"{self._broker_id} does not support reduce-only orders",
            )
        problems = spec.order_problems(
            request.quantity,
            request.price
            if request.price is not None
            else (spec.reference_price if spec.reference_price > Decimal("0") else None),
        )
        if problems:
            return (
                self._precision_rejection_code(),
                "; ".join(problems),
            )
        if request.reduce_only:
            net = self._net_position_quantity(request.symbol)
            signed = request.quantity if request.side is Side.BUY else -request.quantity
            would_reduce = (net > 0 and signed < 0) or (net < 0 and signed > 0)
            if not would_reduce or abs(signed) > abs(net):
                return (
                    self._precision_rejection_code(),
                    f"reduce-only order would not reduce the current net "
                    f"position ({net}) — refused",
                )
        return None

    def _accept_order(self, request: OrderRequest, spec: InstrumentSpec) -> OrderAck:
        """Accept as a NEW order and apply venue semantics (fills etc.)."""
        if request.order_kind is OrderKind.MARKET:
            fraction = self._market_fill_fraction
            self._market_fill_fraction = None  # one-shot
            fill_qty = request.quantity
            if fraction is not None and Decimal("0") < fraction < Decimal("1"):
                quantized = spec.quantize_quantity(request.quantity * fraction)
                if Decimal("0") < quantized < request.quantity:
                    fill_qty = quantized
            self._seq += 1
            venue_order_id = f"{self._broker_id}.{self._seq:06d}"
            order = _VenueOrder(
                request=request,
                venue_order_id=venue_order_id,
                status=VenueOrderStatus.PENDING_NEW,
                submitted_at=self._clock(),
            )
            self._orders[request.client_order_id] = order
            if fill_qty > Decimal("0"):
                self._execute_fill(order, spec, fill_qty)
                order = self._orders[request.client_order_id]  # post-fill record
            self._executed_orders += 1
            return order.to_ack(self._broker_id)
        # Resting order kinds (LIMIT / STOP / STOP_LIMIT) sit OPEN until an
        # explicit test hook fills them.
        self._seq += 1
        venue_order_id = f"{self._broker_id}.{self._seq:06d}"
        order = _VenueOrder(
            request=request,
            venue_order_id=venue_order_id,
            status=VenueOrderStatus.OPEN,
            submitted_at=self._clock(),
        )
        self._orders[request.client_order_id] = order
        self._executed_orders += 1
        return order.to_ack(self._broker_id)

    def _execute_fill(
        self,
        order: _VenueOrder,
        spec: InstrumentSpec,
        quantity: Decimal,
        price: Optional[Decimal] = None,
    ) -> VenueFill:
        """Execute one (possibly partial) fill against an accepted order."""
        fill_price = price if price is not None else spec.reference_price
        if fill_price is None or fill_price <= Decimal("0"):
            raise MockVenueError(
                f"instrument {spec.symbol} has no reference price for mock "
                "fills — configure reference_price or pass an explicit price"
            )
        notional = quantity * fill_price
        fee = (self._fee_rate * notional).quantize(Decimal("0.00000001"))
        self._seq += 1
        fill = VenueFill(
            fill_id=f"{self._broker_id}.F{self._seq:06d}",
            venue_order_id=order.venue_order_id,
            client_order_id=order.request.client_order_id,
            account_id=order.request.account_id,
            broker_id=self._broker_id,
            symbol=order.request.symbol,
            side=order.request.side,
            quantity=quantity,
            price=fill_price,
            fee=fee,
            filled_at=self._clock(),
        )
        fills = order.fills + (fill,)
        new_status = (
            VenueOrderStatus.FILLED
            if sum((f.quantity for f in fills), Decimal("0")) >= order.request.quantity
            else VenueOrderStatus.PARTIALLY_FILLED
        )
        self._orders[order.request.client_order_id] = order.model_copy(
            update={"fills": fills, "status": new_status}
        )
        self._apply_fill_accounting(order.request, spec, fill)
        return fill

    def _apply_fill_accounting(
        self,
        request: OrderRequest,
        spec: InstrumentSpec,
        fill: VenueFill,
    ) -> None:
        """Default SPOT-LIKE accounting: base/quote exchange on fills.

        MT5-style adapters override this for ticket/margin semantics.
        """
        base = spec.base_asset or ""
        quote = spec.quote_asset or ""
        if not base or not quote:
            raise MockVenueError(
                f"instrument {spec.symbol} lacks base/quote assets for "
                "spot-like accounting"
            )
        notional = fill.quantity * fill.price
        if fill.side is Side.BUY:
            self._balances[base] = self._balances.get(base, Decimal("0")) + fill.quantity
            self._balances[quote] = (
                self._balances.get(quote, Decimal("0")) - notional - fill.fee
            )
        else:
            self._balances[base] = self._balances.get(base, Decimal("0")) - fill.quantity
            self._balances[quote] = (
                self._balances.get(quote, Decimal("0")) + notional - fill.fee
            )
        if self._balances[base] < 0 or self._balances[quote] < 0:
            # Defensive: the mock never lets accounting drive a negative
            # balance — the pre-check should have rejected the order.
            raise MockVenueError(
                "mock venue accounting went negative — insufficient-funds "
                "pre-check is missing (defect)"
            )

    def _check_sufficient_funds(
        self, request: OrderRequest, spec: InstrumentSpec
    ) -> Optional[Tuple[str, str]]:
        """Spot-like funds pre-check → definitive rejection mapping."""
        if request.order_kind is not OrderKind.MARKET:
            return None  # resting orders are not charged at placement
        quote = spec.quote_asset or ""
        if not quote:
            return None
        price = request.price if request.price is not None else spec.reference_price
        if price is None or price <= 0:
            return None
        need = request.quantity * price
        fee = (self._fee_rate * need).quantize(Decimal("0.00000001"))
        if request.side is Side.BUY:
            available = self._balances.get(quote, Decimal("0"))
            if available < need + fee:
                return (
                    self._insufficient_funds_code(),
                    f"insufficient {quote} balance: need {need + fee}, "
                    f"available {available}",
                )
        else:
            base = spec.base_asset or ""
            available = self._balances.get(base, Decimal("0"))
            if available < request.quantity:
                return (
                    self._insufficient_funds_code(),
                    f"insufficient {base} balance: need {request.quantity}, "
                    f"available {available}",
                )
        return None

    def _record_order(
        self,
        request: OrderRequest,
        status: VenueOrderStatus,
        reject_reason: Optional[str] = None,
        venue_code: Optional[str] = None,
    ) -> OrderAck:
        self._seq += 1
        order = _VenueOrder(
            request=request,
            venue_order_id=f"{self._broker_id}.{self._seq:06d}",
            status=status,
            submitted_at=self._clock(),
            reject_reason=reject_reason,
            venue_code=venue_code,
        )
        self._orders[request.client_order_id] = order
        return order.to_ack(self._broker_id)

    def cancel_order(self, client_order_id: str) -> OrderAck:
        self._api_guard()
        if self._bound_account is None:
            raise BrokerExecutionError(
                "adapter is not connected",
                category=BrokerErrorCategory.CONNECTIVITY,
                broker_id=self._broker_id,
            )
        order = self._orders.get(client_order_id)
        if order is None:
            raise BrokerExecutionError(
                f"venue {self._broker_id} reports no order "
                f"{client_order_id!r} — nothing to cancel",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self._broker_id,
                venue_code=self._unknown_order_code(),
            )
        if order.status in (
            VenueOrderStatus.FILLED, VenueOrderStatus.CANCELLED,
            VenueOrderStatus.REJECTED, VenueOrderStatus.EXPIRED,
        ):
            return order.to_ack(self._broker_id)  # idempotent terminal return
        updated = order.model_copy(update={"status": VenueOrderStatus.CANCELLED})
        self._orders[client_order_id] = updated
        return updated.to_ack(self._broker_id)

    def order_status(self, client_order_id: str) -> OrderAck:
        self._api_guard()
        order = self._orders.get(client_order_id)
        if order is None:
            raise BrokerExecutionError(
                f"venue {self._broker_id} reports no order "
                f"{client_order_id!r}",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self._broker_id,
                venue_code=self._unknown_order_code(),
            )
        return order.to_ack(self._broker_id)

    def order_fills(self, client_order_id: str) -> Tuple[VenueFill, ...]:
        self._api_guard()
        order = self._orders.get(client_order_id)
        if order is None:
            raise BrokerExecutionError(
                f"venue {self._broker_id} reports no order "
                f"{client_order_id!r}",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self._broker_id,
                venue_code=self._unknown_order_code(),
            )
        return order.fills

    # ------------------------------------------------------------------
    # Account state
    # ------------------------------------------------------------------
    def balances(self) -> Tuple[BalanceRecord, ...]:
        self._api_guard()
        return tuple(
            BalanceRecord(
                account_id=self._bound_account,
                broker_id=self._broker_id,
                asset=asset,
                free=amount,
                locked=Decimal("0"),
            )
            for asset, amount in sorted(self._balances.items())
            if amount != Decimal("0")
        )

    def positions(self) -> Tuple[PositionRecord, ...]:
        """Netted positions computed from fills (NETTING venues).

        BALANCES_ONLY venues override to return () (spot: no position
        object); HEDGING venues override with per-ticket records.
        """
        self._api_guard()
        if self._capabilities.position_mode.value == "BALANCES_ONLY":
            return ()
        by_symbol: Dict[str, List[VenueFill]] = {}
        for order in self._orders.values():
            for fill in order.fills:
                by_symbol.setdefault(fill.symbol, []).append(fill)
        records: List[PositionRecord] = []
        for symbol, fills in sorted(by_symbol.items()):
            # Average-cost netting with the repository's BUG-002 flip
            # discipline: on a position flip the residual opposite side
            # OPENS at the flip fill's price (the closed side's basis
            # never carries into the new side).
            qty = Decimal("0")
            cost = Decimal("0")   # unsigned basis of the current qty
            realized = Decimal("0")
            for fill in fills:
                signed = fill.quantity if fill.side is Side.BUY else -fill.quantity
                if qty == 0:
                    qty = signed
                    cost = fill.price * fill.quantity
                elif (qty > 0) == (signed > 0):
                    qty += signed
                    cost += fill.price * fill.quantity
                else:
                    closing = min(abs(signed), abs(qty))
                    avg = cost / abs(qty)
                    pnl_per = (fill.price - avg) if qty > 0 else (avg - fill.price)
                    realized += pnl_per * closing
                    new_qty = qty + signed
                    if new_qty == 0:
                        cost = Decimal("0")
                    elif (new_qty > 0) != (qty > 0):
                        cost = fill.price * abs(new_qty)
                    else:
                        cost = avg * abs(new_qty)
                    qty = new_qty
            records.append(
                PositionRecord(
                    account_id=self._bound_account,
                    broker_id=self._broker_id,
                    symbol=symbol,
                    quantity=qty,
                    average_entry_price=(cost / abs(qty)) if qty != 0 else Decimal("0"),
                    realized_pnl=realized,
                )
            )
        return tuple(records)

    def _net_position_quantity(self, symbol: str) -> Decimal:
        net = Decimal("0")
        for order in self._orders.values():
            for fill in order.fills:
                if fill.symbol == symbol:
                    net += fill.quantity if fill.side is Side.BUY else -fill.quantity
        return net

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------
    def reconcile(
        self,
        expected: Sequence[ExpectedOrderState],
    ) -> VenueReconciliationReport:
        self._api_guard()
        expected_map = {e.client_order_id: e for e in expected}
        mismatches: List[ReconciliationMismatch] = []
        resolved: List[ExpectedOrderState] = []
        for cid, exp in expected_map.items():
            venue = self._orders.get(cid)
            if venue is None:
                if exp.status is VenueOrderStatus.UNKNOWN:
                    # The venue is the execution authority: no such order
                    # here means it was never accepted — a RESOLUTION.
                    resolved.append(ExpectedOrderState(
                        client_order_id=cid,
                        status=VenueOrderStatus.REJECTED,
                        filled_quantity=Decimal("0"),
                    ))
                else:
                    mismatches.append(ReconciliationMismatch(
                        kind=ReconciliationMismatchKind.ORDER_MISSING_AT_VENUE,
                        client_order_id=cid,
                        journal_status=exp.status,
                        venue_status=None,
                        journal_filled_quantity=exp.filled_quantity,
                        venue_filled_quantity=None,
                        detail="journal knows this order; the venue does not",
                    ))
                continue
            venue_filled = venue.filled_quantity
            if exp.status is VenueOrderStatus.UNKNOWN:
                if venue.status in DEFINITIVE_STATUSES:
                    resolved.append(ExpectedOrderState(
                        client_order_id=cid,
                        status=venue.status,
                        filled_quantity=venue_filled,
                    ))
                else:
                    mismatches.append(ReconciliationMismatch(
                        kind=ReconciliationMismatchKind.STATUS_DIVERGENCE,
                        client_order_id=cid,
                        journal_status=exp.status,
                        venue_status=venue.status,
                        journal_filled_quantity=exp.filled_quantity,
                        venue_filled_quantity=venue_filled,
                        detail="UNKNOWN at journal; venue status still not "
                               "definitive — manual investigation required",
                    ))
                continue
            if exp.status is not venue.status:
                mismatches.append(ReconciliationMismatch(
                    kind=ReconciliationMismatchKind.STATUS_DIVERGENCE,
                    client_order_id=cid,
                    journal_status=exp.status,
                    venue_status=venue.status,
                    journal_filled_quantity=exp.filled_quantity,
                    venue_filled_quantity=venue_filled,
                ))
            if exp.filled_quantity != venue_filled:
                mismatches.append(ReconciliationMismatch(
                    kind=ReconciliationMismatchKind.FILL_QUANTITY_DIVERGENCE,
                    client_order_id=cid,
                    journal_status=exp.status,
                    venue_status=venue.status,
                    journal_filled_quantity=exp.filled_quantity,
                    venue_filled_quantity=venue_filled,
                ))
        for cid, venue in self._orders.items():
            if cid not in expected_map:
                mismatches.append(ReconciliationMismatch(
                    kind=ReconciliationMismatchKind.PHANTOM_ORDER_AT_VENUE,
                    client_order_id=cid,
                    journal_status=None,
                    venue_status=venue.status,
                    journal_filled_quantity=None,
                    venue_filled_quantity=venue.filled_quantity,
                    detail="venue holds an order the journal never submitted "
                           "(or diverged beyond tracking) — investigate",
                ))
        return VenueReconciliationReport(
            broker_id=self._broker_id,
            account_id=self._bound_account,
            ok=not mismatches,
            checked_orders=len(expected_map),
            mismatches=tuple(mismatches),
            resolved=tuple(resolved),
        )

    # ------------------------------------------------------------------
    # Failure injection + fill hooks (DETERMINISTIC test surface)
    # ------------------------------------------------------------------
    def inject_disconnect(self) -> None:
        """Sustained outage: every API call fails CONNECTIVITY (and
        connect itself fails) until ``clear_injections`` + reconnect."""
        self._injected_disconnect = True

    def inject_rate_limit(self, attempts: int = 1) -> None:
        """Next ``attempts`` NEW submissions raise RATE_LIMIT BEFORE the
        venue accepts anything (provably unambiguous)."""
        if attempts < 1:
            raise MockVenueError("injection count must be >= 1")
        self._injected_rate_limit_next = attempts

    def inject_ack_timeout(self) -> None:
        """Next NEW submission is ACCEPTED at the venue but raises
        UNKNOWN_STATE to the caller — the realistic ambiguous case."""
        self._injected_ack_timeout = True

    def inject_rejection(self, venue_code: str, reason: str) -> None:
        """Next NEW submission receives a definitive REJECTED ack."""
        self._injected_rejection = (venue_code, reason)

    def inject_extra_fill(
        self,
        client_order_id: str,
        quantity: Decimal,
        price: Decimal,
    ) -> None:
        """Add a venue fill the session has NOT seen — reconciliation
        must flag the divergence (and the venue stays authoritative)."""
        order = self._orders.get(client_order_id)
        if order is None:
            raise MockVenueError(f"no venue order {client_order_id!r} to diverge")
        remaining = order.request.quantity - order.filled_quantity
        if remaining <= 0:
            raise MockVenueError(
                f"order {client_order_id!r} is fully filled — an extra fill "
                "would overfill; use a resting order or trigger_fill instead"
            )
        spec = self._instruments[order.request.symbol]
        self._execute_fill(order, spec, quantity, price)

    def configure_market_fill_fraction(self, fraction: Decimal) -> None:
        """Next MARKET order fills only ``fraction`` of its quantity
        (partial-fill accounting); the remainder rests OPEN."""
        if not Decimal("0") < fraction < Decimal("1"):
            raise MockVenueError("fraction must be in (0, 1)")
        self._market_fill_fraction = fraction

    def fill_remaining(
        self, client_order_id: str, price: Optional[Decimal] = None
    ) -> VenueFill:
        """Fill the remaining quantity of a resting/partial order."""
        order = self._orders.get(client_order_id)
        if order is None:
            raise MockVenueError(f"no venue order {client_order_id!r}")
        spec = self._instruments[order.request.symbol]
        remaining = order.request.quantity - order.filled_quantity
        if remaining <= 0:
            raise MockVenueError("order is already fully filled")
        return self._execute_fill(order, spec, remaining, price)

    def trigger_fill(
        self, client_order_id: str, price: Decimal, quantity: Optional[Decimal] = None
    ) -> VenueFill:
        """Fill a resting (LIMIT/STOP) order at an explicit price."""
        order = self._orders.get(client_order_id)
        if order is None:
            raise MockVenueError(f"no venue order {client_order_id!r}")
        spec = self._instruments[order.request.symbol]
        qty = quantity if quantity is not None else (
            order.request.quantity - order.filled_quantity
        )
        if qty <= 0:
            raise MockVenueError("no remaining quantity to fill")
        return self._execute_fill(order, spec, qty, price)

    def clear_injections(self) -> None:
        self._injected_disconnect = False
        self._injected_rate_limit_next = 0
        self._injected_ack_timeout = False
        self._injected_rejection = None
        self._market_fill_fraction = None


__all__ = ["DeterministicMockVenue", "MockVenueError", "_VenueOrder"]
