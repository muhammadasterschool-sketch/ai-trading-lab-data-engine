"""Runtime -> broker-neutral execution bridge (Phase M2 / Batch 3).

The SMALLEST maintainable integration layer connecting the
authoritative paper runtime to the broker-neutral execution
interface (multi-broker architecture mandate Phase M2):

    +--------------------------------------+
    | TradingRuntime (authoritative paper) |
    |  RiskGate (22 checks) - KillSwitch   |
    |  PaperExecutionAdapter - bar history |
    +------------------+-------------------+
     gates bridged DOWN | bar history + fill model hosted
    +------------------v-------------------+
    | BrokerSession (broker-neutral)       |
    |  isolation > health > reconcile-gate  |
    |  > kill-switch > risk > idempotency   |
    |  > capabilities > retry > journal     |
    +------------------+-------------------+
                       v
    +--------------------------------------+
    | RuntimePaperExecutionAdapter         |
    |  (BrokerAdapter hosting the runtime's|
    |   PaperExecutionAdapter fill model)  |
    +--------------------------------------+

What this layer IS:

- A governed venue front-end for the paper runtime. Every
  broker-neutral submission is gated by the runtime's REAL
  ``RiskGate`` (all 22 mandatory checks, including RUN-DD-1 account
  drawdown) and ``KillSwitchManager`` — the SAME instances the
  runtime's own order path uses (never copies, never weakenings).
- Session-level protections the runtime does not provide on this
  boundary: journal idempotency across restarts, capability/
  precision pre-checks, bounded deterministic retry, UNKNOWN
  degradation with reconciliation-only recovery.
- Fills produced by the runtime's own ``PaperExecutionAdapter``
  over the runtime's ADMITTED bar history (deterministic: a pure
  function of order parameters + bars + realism).

What this layer is NOT:

- A change to the runtime's authoritative order path.
  ``_execute_plan`` and the OMS are UNTOUCHED — attaching a session
  changes zero runtime behaviour (the untouched suite proves it).
  Venue orders live in the session journal + the adapter's
  venue-side book, NOT in the runtime OMS/position book.
- A live-trading surface. ``MOCK_DETERMINISTIC`` execution mode is
  enforced by the session constructor; REAL adapters are refused.
  LIVE TRADING REMAINS NOT AUTHORIZED.

Broker-specific logic stays behind ``BrokerAdapter`` implementations
(the runtime never imports an adapter); this module — a runtime-
package member — is the ONLY seam, and it deliberately composes the
runtime's internal authoritative state exactly like the OMS/risk
tests do. Nothing outside ``data_engine.runtime`` may rely on those
internals.
"""

import hashlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from data_engine.brokers.capabilities import (
    AccountMode,
    BrokerCapabilities,
    ExecutionMode,
    IdempotencyKeyMechanism,
    PositionMode,
    ReconciliationStyle,
    SlTpSemantics,
)
from data_engine.brokers.errors import (
    BrokerErrorCategory,
    BrokerExecutionError,
)
from data_engine.brokers.interface import BrokerAdapter
from data_engine.brokers.models import (
    AccountInfo,
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
)
from data_engine.brokers.redaction import BrokerCredential, CredentialError
from data_engine.brokers.session import (
    BrokerSession,
    KillSwitchState,
    RiskDecision,
)
from data_engine.runtime.contracts import (
    DecisionAction,
    EntryConstraints,
    TradePlan,
    UncertaintyReport,
)
from data_engine.runtime.kill_switch import KillSwitchActive
from data_engine.runtime.pnl import PositionState
from data_engine.runtime.runtime import TradingRuntime

#: Stable venue id for the runtime-hosted paper venue.
RUNTIME_PAPER_VENUE_ID = "runtime-paper"

#: The runtime paper venue serves EXACTLY what the frozen paper OMS
#: supports: MARKET + LIMIT, GTC, attached SL/TP, reduce-only closes.
#: Anything else (STOP kinds, IOC/FOK/DAY) is refused BEFORE the
#: venue is reached — fail closed, never silently translated.
RUNTIME_PAPER_VENUE_CAPABILITIES = BrokerCapabilities(
    broker_id=RUNTIME_PAPER_VENUE_ID,
    display_name="Runtime-hosted paper venue (authoritative fill model)",
    execution_mode=ExecutionMode.MOCK_DETERMINISTIC,
    order_kinds=(OrderKind.MARKET, OrderKind.LIMIT),
    time_in_force=(TimeInForce.GTC,),
    sl_tp=SlTpSemantics.ATTACHED,
    position_mode=PositionMode.NETTING,
    idempotency_key=IdempotencyKeyMechanism.INTERNAL_JOURNAL,
    supports_reduce_only=True,
    account_modes=(AccountMode.DEMO,),
    venue_notes=(
        "Phase M2 integration venue: hosts the frozen runtime's "
        "PaperExecutionAdapter fill model over the runtime's admitted "
        "bar history. Play-money only; submissions are governed by the "
        "runtime's REAL RiskGate + KillSwitchManager. The runtime's own "
        "order path is untouched."
    ),
)


class BridgeContractError(RuntimeError):
    """Raised on bridge construction/contract violations."""


# ----------------------------------------------------------------------
# Central-gate bridges (runtime -> session injectables)
# ----------------------------------------------------------------------
class RuntimeKillSwitchGate:
    """Session kill-switch gate backed by the runtime's REAL
    ``KillSwitchManager`` (the same instance the runtime's own order
    path consults — a trip anywhere in the runtime refuses broker
    submissions too)."""

    def __init__(self, runtime: TradingRuntime) -> None:
        if not isinstance(runtime, TradingRuntime):
            raise BridgeContractError(
                "RuntimeKillSwitchGate requires the TradingRuntime whose "
                "KillSwitchManager governs this session"
            )
        self._runtime = runtime

    def __call__(self) -> KillSwitchState:
        manager = self._runtime.kill_switch
        symbol = self._runtime.config.symbol
        try:
            manager.check(symbol=symbol)
        except KillSwitchActive as exc:
            # Report the highest-severity active governing switch for
            # the audit record (scope order: GLOBAL > ACCOUNT >
            # PORTFOLIO > SYMBOL).
            scope, reason = "SYMBOL", str(exc)
            for state in manager.states():
                if not state.active:
                    continue
                if state.scope.value in ("GLOBAL", "ACCOUNT", "PORTFOLIO") \
                        or (state.scope.value == "SYMBOL"
                            and (state.target or "") == symbol.upper()):
                    scope = state.scope.value
                    reason = state.reason or str(exc)
                    break
            return KillSwitchState(active=True, scope=scope, reason=reason)
        return KillSwitchState(active=False)


class RuntimeRiskGateBridge:
    """Session risk gate backed by the runtime's REAL ``RiskGate``.

    Translates ONE broker-neutral ``OrderRequest`` into the runtime's
    canonical ``TradePlan`` + ``RiskContext`` (synthesised from LIVE
    runtime state — equity, positions, drawdown, volatility, daily
    return — at the latest admitted bar) and evaluates the FULL
    mandatory check set (all 22, including ``account_drawdown``). The
    assessment is ledgered into the runtime's ledger family
    (auditable forever).

    Translation contract (documented, fail-closed):

    - Only MARKET/LIMIT requests are translatable — the frozen paper
      OMS supports exactly those (STOP/STOP_LIMIT are refused with a
      named failed check; the capability descriptor refuses them
      pre-venue too — defence in depth).
    - Bridged orders carry NO model signal, so the uncertainty/
      crash fields use the SAME deterministic marker the runtime uses
      for its own protective-exit plans (confidence 1.0, entropy 0.0,
      disagreement 0.0, crash probability 0.0) — the capital-risk
      checks (exposure, leverage, concentration, liquidity, spread,
      volatility, drawdown, account drawdown, loss limit, position
      limit, kill switch, SL/TP geometry, R:R, paper mode) all apply
      at full strength.
    - No admitted bars => no market context => REFUSED (fail closed).
    """

    #: The named failed check recorded when the request's order kind
    #: cannot be translated onto the frozen paper OMS.
    UNSUPPORTED_KIND_CHECK = "paper_oms_order_kind"

    def __init__(self, runtime: TradingRuntime) -> None:
        if not isinstance(runtime, TradingRuntime):
            raise BridgeContractError(
                "RuntimeRiskGateBridge requires the TradingRuntime whose "
                "RiskGate governs this session"
            )
        self._runtime = runtime

    def __call__(self, request: OrderRequest) -> RiskDecision:
        runtime = self._runtime
        correlation_id = f"bridge:{request.client_order_id}"

        if request.order_kind not in (OrderKind.MARKET, OrderKind.LIMIT):
            return RiskDecision(
                approved=False,
                reason=(
                    f"order kind {request.order_kind.value} cannot be "
                    "translated onto the frozen paper OMS (MARKET/LIMIT "
                    "only) — refused fail closed"
                ),
                failed_checks=(self.UNSUPPORTED_KIND_CHECK,),
            )
        if request.symbol != runtime.config.symbol:
            return RiskDecision(
                approved=False,
                reason=(
                    f"symbol {request.symbol!r} is not the runtime's "
                    f"configured instrument {runtime.config.symbol!r} — "
                    "the runtime holds no authoritative market context "
                    "(mark, volume, volatility) for a foreign instrument, "
                    "so the order is unverifiable (fail closed)"
                ),
                failed_checks=("bridge_symbol_context",),
            )
        bars = runtime._bars
        if not bars:
            return RiskDecision(
                approved=False,
                reason=(
                    "no admitted market context in the runtime — an order "
                    "without a mark, volume or volatility is unverifiable "
                    "(fail closed)"
                ),
                failed_checks=("no_market_context",),
            )
        latest = bars[-1]
        reference = Decimal(str(latest["close"]))

        side = (
            DecisionAction.BUY if request.side is Side.BUY
            else DecisionAction.SELL
        )
        notional = request.quantity * (
            request.price if request.price is not None else reference
        )
        # risk_budget: the SL-bounded worst case when protective
        # levels are attached, else the full notional (conservative —
        # an unbounded order is refused by the gate anyway).
        if request.stop_loss is not None:
            risk_budget = request.quantity * abs(reference - request.stop_loss)
        else:
            risk_budget = notional
        plan = TradePlan(
            trade_plan_id=f"bridge-plan-{request.client_order_id}",
            decision_id=f"bridge-decision-{request.client_order_id}",
            symbol=request.symbol,
            side=side,
            quantity=request.quantity,
            notional=notional,
            entry=EntryConstraints(
                order_type=request.order_kind.value,
                limit_price=request.price,
                time_in_force="GTC",
                ttl_bars=None,
            ),
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            risk_budget=risk_budget,
            expected_return=0.0,
            risk_reward_ratio=0.0,
            uncertainty=UncertaintyReport(
                confidence=1.0, entropy=0.0, ensemble_disagreement=0.0
            ),
            crash_risk={"probability": 0.0},
            model_context={"model": "runtime.broker_execution_bridge"},
            correlation_id=correlation_id,
        )
        context = runtime._risk_context_for_bridge(plan, reference, latest)
        assessment = runtime.risk_gate.evaluate(
            plan, context, correlation_id, ledger=runtime.ledgers
        )
        failed = tuple(c.check for c in assessment.failed_checks)
        reason = (
            "all 22 mandatory checks passed (bridged assessment "
            f"{assessment.assessment_id})"
            if assessment.passed
            else "failed checks: " + ", ".join(failed)
        )
        return RiskDecision(
            approved=assessment.passed,
            reason=reason,
            failed_checks=failed,
        )


# ----------------------------------------------------------------------
# Runtime-hosted venue adapter
# ----------------------------------------------------------------------
class _VenueOrder:
    """Mutable venue-side order book entry (adapter-private)."""

    __slots__ = (
        "request", "venue_order_id", "status", "fills", "cursor",
        "submitted_at", "execution_anchor",
    )

    def __init__(self, request: OrderRequest, venue_order_id: str,
                 submitted_at: datetime,
                 execution_anchor: datetime) -> None:
        self.request = request
        self.venue_order_id = venue_order_id
        self.status = VenueOrderStatus.OPEN
        self.fills: List = []
        self.cursor = 0  # next bar index to scan for fills
        self.submitted_at = submitted_at
        #: The market-time anchor for the hosted fill model: the
        #: LAST ADMITTED bar's timestamp at submission. A wall/step
        #: clock time AFTER every bar would drift the latency window
        #: forward on every advance (execute() re-derives submit_idx
        #: from this value) — anchoring at bar time keeps the venue's
        #: fill-lag semantics identical to the runtime's own.
        self.execution_anchor = execution_anchor

    @property
    def filled_quantity(self) -> Decimal:
        return sum((f.quantity for f in self.fills), Decimal("0"))

    @property
    def remaining_quantity(self) -> Decimal:
        return self.request.quantity - self.filled_quantity

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            VenueOrderStatus.FILLED, VenueOrderStatus.CANCELLED,
            VenueOrderStatus.REJECTED, VenueOrderStatus.EXPIRED,
        )


class RuntimePaperExecutionAdapter(BrokerAdapter):
    """BrokerAdapter hosting the runtime's PaperExecutionAdapter.

    Venue-side execution is a PURE function of (request, the
    runtime's admitted bar history, the runtime's realism config) —
    the identical deterministic fill model the runtime's own order
    path uses (half-spread + impact + commission per unit,
    participation-capped partial fills, LIMIT never through the
    limit, BUG-001/BUG-007 disciplines enforced by the hosted
    adapter). Orders submitted while N bars are admitted first
    become executable ``fill_lag_bars`` bars later — the runtime's
    latency semantics, hosted venue-side.

    Execution advances when the venue is POLLED (order_status /
    order_fills / sync_order_state / reconcile) against bars newly
    admitted since the last poll — mirroring how a real venue fills
    resting orders as the market moves while clients poll for truth.
    """

    def __init__(
        self,
        runtime: TradingRuntime,
        *,
        instruments: Mapping[str, InstrumentSpec],
        account_id: str,
        clock: Callable[[], datetime],
        currency: str = "USD",
        initial_balance: Decimal = Decimal("100000"),
    ) -> None:
        if not isinstance(runtime, TradingRuntime):
            raise BridgeContractError(
                "RuntimePaperExecutionAdapter requires the TradingRuntime "
                "whose fill model + bar history it hosts"
            )
        if not callable(clock):
            raise BridgeContractError(
                "an injectable clock callable is MANDATORY (determinism)"
            )
        if not isinstance(account_id, str) or not account_id.strip():
            raise BridgeContractError("account_id must be non-empty")
        self._runtime = runtime
        self._execution = runtime._execution  # THE PaperExecutionAdapter
        self._instruments = {
            sym: spec for sym, spec in dict(instruments).items()
        }
        self._account_id = account_id.strip()
        self._clock = clock
        self._currency = currency
        self._initial_balance = initial_balance
        self._state = ConnectionState.DISCONNECTED
        self._orders: Dict[str, _VenueOrder] = {}

    # -- descriptive ------------------------------------------------------
    @property
    def broker_id(self) -> str:
        return RUNTIME_PAPER_VENUE_ID

    @property
    def capabilities(self) -> BrokerCapabilities:
        return RUNTIME_PAPER_VENUE_CAPABILITIES

    # -- lifecycle ---------------------------------------------------------
    def connect(self, credential) -> None:
        if not isinstance(credential, BrokerCredential):
            raise CredentialError("connect requires a BrokerCredential holder")
        if not credential.matches_account(self._account_id):
            raise BrokerExecutionError(
                f"credential is for account {credential.account_id!r} but "
                f"this venue serves {self._account_id!r} (isolation refusal)",
                category=BrokerErrorCategory.AUTH,
                broker_id=self.broker_id,
            )
        self._state = ConnectionState.CONNECTED

    def disconnect(self) -> None:
        self._state = ConnectionState.DISCONNECTED

    def health(self) -> ConnectionState:
        return self._state

    # -- account + instruments ---------------------------------------------
    def account_info(self) -> AccountInfo:
        self._require_connected()
        return AccountInfo(
            broker_id=self.broker_id,
            account_id=self._account_id,
            account_mode=AccountMode.DEMO,
            currency=self._currency,
            position_mode=PositionMode.NETTING,
            leverage=None,
            display_name="Runtime-hosted paper account (play money)",
        )

    def instrument_spec(self, symbol: str) -> InstrumentSpec:
        spec = self._instruments.get(symbol)
        if spec is None:
            raise BrokerExecutionError(
                f"symbol {symbol!r} is not served by the runtime paper "
                "venue — instrument metadata is integrator-supplied, "
                "never guessed",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self.broker_id,
            )
        return spec

    def list_symbols(self) -> Tuple[str, ...]:
        return tuple(sorted(self._instruments))

    # -- orders --------------------------------------------------------------
    def submit_order(self, request: OrderRequest) -> OrderAck:
        self._require_connected()
        if request.account_id != self._account_id:
            raise BrokerExecutionError(
                f"request names account {request.account_id!r} but this "
                f"venue serves {self._account_id!r}",
                category=BrokerErrorCategory.AUTH,
                broker_id=self.broker_id,
            )
        prior = self._orders.get(request.client_order_id)
        if prior is not None:
            # Idempotent: the SAME client_order_id never executes twice;
            # the CURRENT venue truth is returned.
            self._advance(prior)
            return self._ack_for(prior)
        venue_order_id = (
            "rtpv-"
            + hashlib.sha256(
                request.client_order_id.encode("utf-8")
            ).hexdigest()[:24]
        )
        submitted_at = self._clock()
        bars = self._runtime._bars
        anchor = submitted_at
        if bars:
            ts = bars[-1].get("timestamp")
            if ts is not None and getattr(ts, "tzinfo", None) is not None:
                anchor = ts
        order = _VenueOrder(
            request=request,
            venue_order_id=venue_order_id,
            submitted_at=submitted_at,
            execution_anchor=anchor,
        )
        self._orders[request.client_order_id] = order
        self._advance(order)
        return self._ack_for(order)

    def cancel_order(self, client_order_id: str) -> OrderAck:
        self._require_connected()
        order = self._orders.get(client_order_id)
        if order is None:
            raise BrokerExecutionError(
                f"unknown client_order_id {client_order_id!r} — venue truth "
                "fails closed, never guessed",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self.broker_id,
            )
        if not order.is_terminal:
            order.status = VenueOrderStatus.CANCELLED
        return self._ack_for(order)

    def order_status(self, client_order_id: str) -> OrderAck:
        self._require_connected()
        order = self._orders.get(client_order_id)
        if order is None:
            raise BrokerExecutionError(
                f"unknown client_order_id {client_order_id!r}",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self.broker_id,
            )
        self._advance(order)
        return self._ack_for(order)

    def order_fills(self, client_order_id: str) -> Tuple[VenueFill, ...]:
        self._require_connected()
        order = self._orders.get(client_order_id)
        if order is None:
            raise BrokerExecutionError(
                f"unknown client_order_id {client_order_id!r}",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self.broker_id,
            )
        self._advance(order)
        return tuple(self._venue_fill(f, order) for f in order.fills)

    # -- account state ---------------------------------------------------------
    def positions(self) -> Tuple[PositionRecord, ...]:
        self._require_connected()
        book = self._venue_position_book()
        records = []
        for symbol, state in sorted(book.items()):
            if state.is_flat:
                continue
            records.append(PositionRecord(
                account_id=self._account_id,
                broker_id=self.broker_id,
                symbol=symbol,
                quantity=state.quantity,
                average_entry_price=state.average_cost,
                realized_pnl=state.realized_pnl,
            ))
        return tuple(records)

    def balances(self) -> Tuple[BalanceRecord, ...]:
        self._require_connected()
        book = self._venue_position_book()
        equity = self._initial_balance
        for state in book.values():
            equity += state.realized_pnl
            if not state.is_flat:
                mark = self._latest_close()
                if mark is not None:
                    equity += (
                        state.quantity * (mark - state.average_cost)
                    )
        return (
            BalanceRecord(
                account_id=self._account_id,
                broker_id=self.broker_id,
                asset=self._currency,
                free=equity,
            ),
        )

    # -- reconciliation -----------------------------------------------------------
    def reconcile(self, expected) -> VenueReconciliationReport:
        self._require_connected()
        # Venue truth first: advance every live order against any bars
        # admitted since the last poll (the venue is the execution
        # authority — its truth is what reconciliation compares AGAINST).
        for order in list(self._orders.values()):
            self._advance(order)
        mismatches: List[ReconciliationMismatch] = []
        resolved: List[ExpectedOrderState] = []
        expected_ids = set()
        for exp in expected:
            expected_ids.add(exp.client_order_id)
            order = self._orders.get(exp.client_order_id)
            if order is None:
                mismatches.append(ReconciliationMismatch(
                    kind=ReconciliationMismatchKind.ORDER_MISSING_AT_VENUE,
                    client_order_id=exp.client_order_id,
                    detail=(
                        "journal expects an order the venue never held"
                    ),
                ))
                continue
            if exp.status is VenueOrderStatus.UNKNOWN:
                # Venue truth resolves the ambiguity (definitive only).
                resolved.append(ExpectedOrderState(
                    client_order_id=exp.client_order_id,
                    status=order.status,
                    filled_quantity=order.filled_quantity,
                ))
                continue
            if order.status is not VenueOrderStatus.UNKNOWN \
                    and exp.status != order.status:
                mismatches.append(ReconciliationMismatch(
                    kind=ReconciliationMismatchKind.STATUS_DIVERGENCE,
                    client_order_id=exp.client_order_id,
                    detail=(
                        f"journal believes {exp.status.value} but venue "
                        f"truth is {order.status.value} — accept venue "
                        "truth via sync_order_state, never paper over"
                    ),
                ))
                continue
            if exp.filled_quantity != order.filled_quantity:
                mismatches.append(ReconciliationMismatch(
                    kind=ReconciliationMismatchKind.FILL_QUANTITY_DIVERGENCE,
                    client_order_id=exp.client_order_id,
                    detail=(
                        f"journal believes {exp.filled_quantity} filled "
                        f"but venue truth is {order.filled_quantity}"
                    ),
                ))
        for cid, order in sorted(self._orders.items()):
            if cid not in expected_ids:
                mismatches.append(ReconciliationMismatch(
                    kind=ReconciliationMismatchKind.PHANTOM_ORDER_AT_VENUE,
                    client_order_id=cid,
                    detail=(
                        f"venue holds order the journal does not know "
                        f"(status {order.status.value})"
                    ),
                ))
        return VenueReconciliationReport(
            broker_id=self.broker_id,
            account_id=self._account_id,
            ok=not mismatches,
            checked_orders=len(tuple(expected)),
            mismatches=tuple(mismatches),
            resolved=tuple(resolved),
        )

    # -- internals ---------------------------------------------------------------
    def _require_connected(self) -> None:
        if self._state is not ConnectionState.CONNECTED:
            raise BrokerExecutionError(
                f"runtime paper venue is {self._state.value} — calls fail "
                "closed until connected",
                category=BrokerErrorCategory.CONNECTIVITY,
                broker_id=self.broker_id,
            )

    def _latest_close(self) -> Optional[Decimal]:
        bars = self._runtime._bars
        if not bars:
            return None
        return Decimal(str(bars[-1]["close"]))

    def _advance(self, order: _VenueOrder) -> None:
        """Advance ONE order's execution against bars admitted since
        its cursor (the runtime's own deterministic fill model)."""
        if order.status not in (
            VenueOrderStatus.OPEN, VenueOrderStatus.PARTIALLY_FILLED,
        ):
            return
        bars = self._runtime._bars
        if not bars or order.remaining_quantity <= 0:
            return
        new_fills = self._execution.execute(
            order_id=order.venue_order_id,
            symbol=order.request.symbol,
            side=order.request.side.value,
            order_type=order.request.order_kind.value,
            quantity=order.remaining_quantity,
            bars=bars,
            submitted_at=order.execution_anchor,
            limit_price=order.request.price,
            max_bars=None,  # GTC venue orders: bounded per poll by bars
            from_bar=order.cursor,
            start_index=len(order.fills),
        )
        if new_fills:
            order.fills.extend(new_fills)
            order.cursor = new_fills[-1].bar_index + 1
        filled = order.filled_quantity
        if filled >= order.request.quantity:
            order.status = VenueOrderStatus.FILLED
        elif filled > 0:
            order.status = VenueOrderStatus.PARTIALLY_FILLED

    def _ack_for(self, order: _VenueOrder) -> OrderAck:
        return OrderAck(
            client_order_id=order.request.client_order_id,
            venue_order_id=order.venue_order_id,
            account_id=order.request.account_id,
            broker_id=self.broker_id,
            symbol=order.request.symbol,
            side=order.request.side,
            order_kind=order.request.order_kind,
            quantity=order.request.quantity,
            status=order.status,
            submitted_at=order.submitted_at,
        )

    def _venue_fill(self, fill, order: _VenueOrder) -> VenueFill:
        """RuntimeFill -> VenueFill. The venue-neutral fill model has
        ONE aggregate ``fee`` field; the runtime's full cost
        decomposition (commission + slippage + spread) is aggregated
        into it exactly once (the decomposition stays authoritative
        in the runtime's own ledgers)."""
        return VenueFill(
            fill_id=fill.fill_id,
            venue_order_id=order.venue_order_id,
            client_order_id=order.request.client_order_id,
            account_id=order.request.account_id,
            broker_id=self.broker_id,
            symbol=fill.symbol,
            side=Side.BUY if fill.side == "BUY" else Side.SELL,
            quantity=fill.quantity,
            price=fill.price,
            fee=fill.commission + fill.slippage_cost + fill.spread_cost,
            filled_at=fill.filled_at,
        )

    def _venue_position_book(self) -> Dict[str, PositionState]:
        """Netted venue-side book, replayed from venue fills with the
        runtime's authoritative position model (cost-embedded)."""
        book: Dict[str, PositionState] = {}
        for order in self._orders.values():
            for fill in order.fills:
                state = book.get(
                    fill.symbol, PositionState(symbol=fill.symbol)
                )
                book[fill.symbol] = state.apply_fill(
                    fill_quantity=fill.quantity,
                    fill_price=fill.price,
                    side=fill.side,
                    commission=fill.commission,
                    slippage_cost=fill.slippage_cost,
                    spread_cost=fill.spread_cost,
                    filled_at=fill.filled_at,
                    source_event=fill.fill_id,
                )
        return book


# ----------------------------------------------------------------------
# The attach factory (the integration seam)
# ----------------------------------------------------------------------
def attach_runtime_paper_session(
    runtime: TradingRuntime,
    *,
    account_id: str,
    journal_path: Path,
    clock: Callable[[], datetime],
    instruments: Mapping[str, InstrumentSpec],
    currency: str = "USD",
    initial_balance: Decimal = Decimal("100000"),
    retry_policy=None,
    sleeper=None,
) -> BrokerSession:
    """Attach a broker-neutral ``BrokerSession`` to a STARTED paper
    runtime (Phase M2 integration seam).

    The returned session is governed by the runtime's REAL central
    gates (``RuntimeRiskGateBridge`` / ``RuntimeKillSwitchGate`` —
    the same instances the runtime's own order path uses) and
    executes through the runtime's own deterministic fill model
    (``RuntimePaperExecutionAdapter``). The runtime's authoritative
    order path is untouched: venue orders live in the session journal
    + venue book, never in the runtime OMS.

    Fail-closed notes:

    - ``instruments`` is integrator-supplied metadata — the venue
      never GUESSES a spec (unknown symbols are refused).
    - The session enforces ``MOCK_DETERMINISTIC`` execution mode;
      REAL adapters are refused (LIVE NOT AUTHORIZED).
    - A runtime with no admitted bars refuses every order at the
      risk bridge (no market context — fail closed).
    """
    adapter = RuntimePaperExecutionAdapter(
        runtime,
        instruments=instruments,
        account_id=account_id,
        clock=clock,
        currency=currency,
        initial_balance=initial_balance,
    )
    return BrokerSession(
        adapter,
        account_id=account_id,
        journal_path=Path(journal_path),
        risk_decision_fn=RuntimeRiskGateBridge(runtime),
        kill_switch_fn=RuntimeKillSwitchGate(runtime),
        retry_policy=retry_policy,
        sleeper=sleeper,
        clock=clock,
    )


__all__ = [
    "RUNTIME_PAPER_VENUE_ID",
    "RUNTIME_PAPER_VENUE_CAPABILITIES",
    "BridgeContractError",
    "RuntimeKillSwitchGate",
    "RuntimeRiskGateBridge",
    "RuntimePaperExecutionAdapter",
    "attach_runtime_paper_session",
]
