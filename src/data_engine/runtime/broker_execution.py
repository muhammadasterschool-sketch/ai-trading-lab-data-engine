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
    OrderRefusedError,
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
    OrderLifecycle,
    RuntimeContractError,
    RuntimeState,
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


class VenueSubmissionRefused(RuntimeContractError):
    """The venue session DEFINITIVELY refused a runtime order
    (gates/isolation/health/capability/precision). The venue never
    saw the order — the runtime may reject its OMS order. Carries the
    session's ``reason_code`` verbatim for the audit ledger."""

    def __init__(self, reason_code: str, message: str) -> None:
        super().__init__(
            f"venue refused the submission ({reason_code}): {message}"
        )
        self.reason_code = reason_code


class VenueSubmissionUncertain(RuntimeContractError):
    """The venue submission outcome is AMBIGUOUS (timeout retries
    exhausted / UNKNOWN state). The venue MAY hold a live order —
    failure is NEVER inferred from a lost ack; the runtime must mark
    the order UNKNOWN and reconcile before any retry."""


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
        "submitted_at", "execution_anchor", "fill_window_bars",
        "fill_order_id",
    )

    def __init__(self, request: OrderRequest, venue_order_id: str,
                 submitted_at: datetime,
                 execution_anchor: datetime,
                 fill_window_bars: Optional[int] = None,
                 fill_order_id: Optional[str] = None) -> None:
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
        #: AUTHORITATIVE mode: the TTL fill window (bars) taken from
        #: the OMS order — identical to the runtime's internal
        #: ``ttl_bars or config.ttl_bars`` window. None = side-band
        #: GTC behaviour (unchanged Batch-3 semantics).
        self.fill_window_bars = fill_window_bars
        #: AUTHORITATIVE mode: the identity stamped into hosted fills
        #: — the OMS order id (= client_order_id), so ``apply_fill``
        #: and fill-id determinism are EXACTLY the internal path's.
        #: None = side-band venue_order_id (unchanged).
        self.fill_order_id = fill_order_id or venue_order_id

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
        authoritative: bool = False,
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
        #: AUTHORITATIVE mode (Batch 5, Phase M2 completion): the venue
        #: hosts the runtime's AUTHORITATIVE order path — submissions
        #: must map 1:1 to RISK_APPROVED OMS orders, fills carry the
        #: OMS order identity, and the TTL fill window mirrors the
        #: internal path exactly. False = the Batch-3 side-band
        #: behaviour, byte-for-byte unchanged.
        self._authoritative = bool(authoritative)
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
        fill_window_bars = None
        fill_order_id = None
        if self._authoritative:
            # AUTHORITATIVE mode: a submission without a corresponding
            # RISK_APPROVED OMS order is a wiring violation — fail
            # closed, the venue never invents orders.
            try:
                oms_order = self._runtime._oms.order(
                    request.client_order_id
                )
            except Exception as exc:
                raise BrokerExecutionError(
                    f"authoritative submission {request.client_order_id!r} "
                    "has no OMS order — venue submissions exist only for "
                    "risk-approved runtime orders (fail closed)",
                    category=BrokerErrorCategory.INVALID_ORDER,
                    broker_id=self.broker_id,
                ) from exc
            if oms_order.status is not OrderLifecycle.RISK_APPROVED:
                raise BrokerExecutionError(
                    f"OMS order {request.client_order_id!r} is "
                    f"{oms_order.status.value}, not RISK_APPROVED — the "
                    "venue only serves fingerprint-bound approved orders "
                    "(fail closed)",
                    category=BrokerErrorCategory.INVALID_ORDER,
                    broker_id=self.broker_id,
                )
            # The TTL fill window mirrors the internal path EXACTLY:
            # order.ttl_bars or the runtime config default.
            fill_window_bars = (
                oms_order.ttl_bars
                if oms_order.ttl_bars is not None
                else self._runtime._config.ttl_bars
            )
            # Hosted fills carry the OMS order identity so that
            # ``OMS.apply_fill`` binding and fill-id determinism are
            # exactly the internal path's.
            fill_order_id = request.client_order_id
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
            fill_window_bars=fill_window_bars,
            fill_order_id=fill_order_id,
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

    # -- runtime-package seam (authoritative mode) ---------------------------
    def runtime_fills(self, client_order_id: str) -> Tuple:
        """The AUTHORITATIVE ``RuntimeFill`` objects hosted for ONE
        venue order — the full cost decomposition the runtime's OMS /
        position book consumes (the venue-neutral ``VenueFill``
        aggregates the same costs into one ``fee`` field for OTHER
        consumers). Runtime-package seam: only the authoritative venue
        integration may call this."""
        order = self._orders.get(client_order_id)
        if order is None:
            raise BrokerExecutionError(
                f"unknown client_order_id {client_order_id!r}",
                category=BrokerErrorCategory.INVALID_ORDER,
                broker_id=self.broker_id,
            )
        return tuple(order.fills)

    def register_recovered_order(self, oms_order, venue_status) -> None:
        """Restart recovery (runtime-package seam): rebuild ONE venue
        order from the persisted OMS truth.

        The hosted fill model is a PURE function of (order parameters,
        admitted bars, realism) — so the complete fill list is
        REGENERATED over the full admitted history and VERIFIED
        against the persisted OMS fills (fill identities, quantities,
        prices, bar indices). Any divergence is an incompatible state
        and refuses recovery (fail closed). The rebuilt venue order
        then adopts the persisted fills and continues deterministically
        from the persisted fill cursor."""
        self._require_connected()
        if not self._authoritative:
            raise BridgeContractError(
                "register_recovered_order is an authoritative-mode seam"
            )
        cid = oms_order.order_id
        if cid in self._orders:
            raise BridgeContractError(
                f"venue order {cid!r} is already registered"
            )
        if oms_order.submitted_at is None:
            raise BridgeContractError(
                f"restored OMS order {cid!r} has no submitted_at — the "
                "venue book cannot be rebuilt deterministically "
                "(fail closed)"
            )
        ttl_window = (
            oms_order.ttl_bars
            if oms_order.ttl_bars is not None
            else self._runtime._config.ttl_bars
        )
        regenerated = self._execution.execute(
            order_id=cid,
            symbol=oms_order.symbol,
            side=oms_order.side,
            order_type=oms_order.order_type,
            quantity=oms_order.quantity,
            bars=self._runtime._bars,
            submitted_at=oms_order.submitted_at,
            limit_price=oms_order.limit_price,
            max_bars=ttl_window,
            from_bar=None,
            start_index=0,
        )
        persisted = list(oms_order.fills)
        n = len(persisted)
        diverged = len(regenerated) < n or any(
            a.fill_id != b.fill_id
            for a, b in zip(regenerated, persisted)
        )
        if diverged:
            raise BridgeContractError(
                f"venue recovery for {cid!r}: regenerated fills diverge "
                "from the persisted OMS fills — incompatible persisted "
                "state (bars / realism / order parameters changed); "
                "refusing to rebuild (fail closed)"
            )
        live = oms_order.status in (
            OrderLifecycle.SUBMITTED, OrderLifecycle.ACKNOWLEDGED,
            OrderLifecycle.PARTIALLY_FILLED,
        )
        if live and len(regenerated) != n:
            raise BridgeContractError(
                f"venue recovery for {cid!r}: a live order has hosted "
                "fills beyond the persisted OMS record — refusing "
                "(fail closed)"
            )
        # Derive the venue status for live orders from venue truth;
        # terminal orders adopt the journaled venue status (a cancel/
        # expiry is an EVENT, not a function of bars).
        if venue_status in (
            VenueOrderStatus.FILLED, VenueOrderStatus.CANCELLED,
            VenueOrderStatus.REJECTED, VenueOrderStatus.EXPIRED,
        ):
            derived = venue_status
        else:
            filled = sum(
                (f.quantity for f in persisted), Decimal("0")
            )
            if filled >= oms_order.quantity and oms_order.quantity > 0:
                derived = VenueOrderStatus.FILLED
            elif filled > 0:
                derived = VenueOrderStatus.PARTIALLY_FILLED
            else:
                derived = VenueOrderStatus.OPEN
            if derived != venue_status:
                raise BridgeContractError(
                    f"venue recovery for {cid!r}: journal venue status "
                    f"{venue_status.value} diverges from regenerated "
                    f"truth {derived.value} — refusing (fail closed)"
                )
        cursor = self._runtime._order_fill_cursor.get(cid)
        if cursor is None:
            cursor = (
                persisted[-1].bar_index + 1 if persisted else 0
            )
        request = OrderRequest(
            client_order_id=cid,
            account_id=self._account_id,
            symbol=oms_order.symbol,
            side=Side.BUY if oms_order.side == "BUY" else Side.SELL,
            order_kind=(
                OrderKind.MARKET if oms_order.order_type == "MARKET"
                else OrderKind.LIMIT
            ),
            quantity=oms_order.quantity,
            price=oms_order.limit_price,
            stop_price=None,
            time_in_force=TimeInForce.GTC,
            stop_loss=None,
            take_profit=None,
            reduce_only=False,
        )
        order = _VenueOrder(
            request=request,
            venue_order_id=(
                "rtpv-" + hashlib.sha256(
                    cid.encode("utf-8")
                ).hexdigest()[:24]
            ),
            submitted_at=oms_order.submitted_at,
            execution_anchor=oms_order.submitted_at,
            fill_window_bars=ttl_window,
            fill_order_id=cid,
        )
        order.fills = list(persisted)
        order.cursor = cursor
        order.status = derived
        self._orders[cid] = order

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
            order_id=order.fill_order_id,
            symbol=order.request.symbol,
            side=order.request.side.value,
            order_type=order.request.order_kind.value,
            quantity=order.remaining_quantity,
            bars=bars,
            submitted_at=order.execution_anchor,
            limit_price=order.request.price,
            max_bars=order.fill_window_bars,
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
# AUTHORITATIVE integration (Batch 5 — Phase M2 completion)
# ----------------------------------------------------------------------
class RuntimeOrderPathRiskGate:
    """Session risk gate for the AUTHORITATIVE runtime order path.

    This gate NEVER re-decides risk. It VERIFIES that the request maps
    1:1 onto an OMS order in ``RISK_APPROVED`` state whose fingerprint
    fields match the request exactly — the structural, fingerprint-
    bound evidence (RT-F1: ``OMS.risk_approve`` already refused any
    assessment that does not match THIS order) that the runtime's ONE
    authoritative RiskGate assessment (all 22 mandatory checks,
    including RUN-DD-1 account drawdown) approved exactly this order.

    The result: ONE coherent risk decision (RiskGate assessment ->
    fingerprint-bound OMS approval -> venue submission verification)
    bound to a single order identity — the venue ``client_order_id``
    IS the OMS order id. Any mismatch, any foreign identity, any
    non-approved state: REFUSED fail closed.
    """

    BINDING_CHECK = "order_path_binding"

    #: The OMS state whose structural evidence satisfies the binding
    #: verification: RISK_APPROVED — the ONLY point at which the
    #: authoritative order path submits to the venue (the OMS
    #: fingerprint-bound approval, RT-F1, is on record exactly then;
    #: every later state transition is governed by fills/cancels/
    #: reconciliation, never a fresh submission).
    BOUND_STATES = (
        OrderLifecycle.RISK_APPROVED,
    )

    def __init__(self, runtime: TradingRuntime) -> None:
        if not isinstance(runtime, TradingRuntime):
            raise BridgeContractError(
                "RuntimeOrderPathRiskGate requires the TradingRuntime "
                "whose RiskGate governs this session"
            )
        self._runtime = runtime

    def __call__(self, request: OrderRequest) -> RiskDecision:
        runtime = self._runtime
        try:
            order = runtime._oms.order(request.client_order_id)
        except Exception:
            return RiskDecision(
                approved=False,
                reason=(
                    f"request {request.client_order_id!r} maps to no OMS "
                    "order — venue submissions exist only for orders the "
                    "runtime's authoritative path created and "
                    "risk-approved (fail closed)"
                ),
                failed_checks=(self.BINDING_CHECK,),
            )
        if order.status not in self.BOUND_STATES:
            return RiskDecision(
                approved=False,
                reason=(
                    f"OMS order {order.order_id} is {order.status.value} "
                    "— no fingerprint-bound passing assessment or live "
                    "re-adoption evidence is on record for this "
                    "submission (fail closed)"
                ),
                failed_checks=(self.BINDING_CHECK,),
            )
        matches = (
            order.symbol == request.symbol
            and order.side == request.side.value
            and order.order_type == request.order_kind.value
            and order.quantity == request.quantity
            and order.limit_price == request.price
        )
        if not matches:
            return RiskDecision(
                approved=False,
                reason=(
                    f"request diverges from OMS order {order.order_id} "
                    "(symbol/side/kind/quantity/limit) — the venue never "
                    "executes anything but the risk-approved fingerprint"
                ),
                failed_checks=(self.BINDING_CHECK,),
            )
        return RiskDecision(
            approved=True,
            reason=(
                f"OMS order {order.order_id} is RISK_APPROVED with a "
                "fingerprint-bound passing assessment (RT-F1) — the "
                "runtime's single authoritative RiskGate decision"
            ),
        )


class RuntimeAuthoritativeVenue:
    """The broker-neutral execution venue BOUND to the runtime's
    AUTHORITATIVE order path (Batch 5 — Phase M2 completion).

    When this venue is attached, every runtime order — entries AND
    protective exits — flows through the guarded ``BrokerSession``
    pipeline (isolation > health > reconciliation-gate > kill-switch >
    risk-binding verification > journal idempotency > capability +
    precision pre-checks > bounded retry > the hosted fill model).
    There is NO hidden direct-execution fallback: once attached,
    ``TradingRuntime._process_pending_orders`` fills orders ONLY from
    venue polls.

    Safety properties owned by this seam:

    - **Single coherent risk decision**: the session's risk gate is
      the ``RuntimeOrderPathRiskGate`` binding verification (above);
      the kill-switch gate is the runtime's REAL
      ``KillSwitchManager`` with the DOCUMENTED risk-reduction
      carve-out for explicitly reduce-only orders that verifiably
      reduce the live position (mirroring the runtime gate's own
      closing-order carve-out — exits traverse the same boundary).
    - **Exactly-once fills**: polls return only the RuntimeFill delta
      beyond what the OMS already holds; the application path is the
      runtime's own (OMS -> position -> P&L -> ledger), unchanged.
    - **Ambiguity discipline**: a refused submission REJECTS the OMS
      order (the venue never saw it); an ambiguous submission marks
      it UNKNOWN + RECONCILING and stops the runtime
      (EXECUTION_UNCERTAIN) until reconciliation resolves from venue
      truth — never an inferred failure.
    - **Restart idempotency**: recovery rebuilds the venue book from
      persisted OMS + journal truth with deterministic-regeneration
      verification; the same ``client_order_id`` never executes twice.
    """

    def __init__(
        self,
        runtime: TradingRuntime,
        session: BrokerSession,
        adapter: RuntimePaperExecutionAdapter,
        account_id: str,
    ) -> None:
        if not isinstance(runtime, TradingRuntime):
            raise BridgeContractError(
                "RuntimeAuthoritativeVenue requires the TradingRuntime "
                "it governs"
            )
        if not isinstance(session, BrokerSession):
            raise BridgeContractError(
                "RuntimeAuthoritativeVenue requires a BrokerSession"
            )
        if not isinstance(adapter, RuntimePaperExecutionAdapter):
            raise BridgeContractError(
                "RuntimeAuthoritativeVenue requires a "
                "RuntimePaperExecutionAdapter in authoritative mode"
            )
        if not adapter._authoritative:
            raise BridgeContractError(
                "the venue adapter must be constructed with "
                "authoritative=True (the runtime order path seam)"
            )
        self._runtime = runtime
        self._session = session
        self._adapter = adapter
        self._account_id = account_id
        self._ks_gate = RuntimeKillSwitchGate(runtime)
        #: The submission context (request, reduce_only) while THIS
        #: seam is driving a session submission — the kill-switch
        #: carve-out is consultative ONLY for seam-driven submissions.
        #: Foreign/direct session submissions get NO carve-out.
        self._active_submission: Optional[Tuple[OrderRequest, bool]] = None

    # -- identity ----------------------------------------------------------
    @property
    def session(self) -> BrokerSession:
        return self._session

    @property
    def adapter(self) -> RuntimePaperExecutionAdapter:
        return self._adapter

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def broker_id(self) -> str:
        return self._adapter.broker_id

    # -- central gates -------------------------------------------------------
    def _kill_switch_state(self) -> KillSwitchState:
        """Session kill-switch gate: the runtime's REAL manager governs
        every submission, with the NARROW risk-reduction carve-out for
        seam-driven reduce-only orders that verifiably reduce the live
        position (the runtime gate's documented closing-order
        carve-out, mirrored at the venue boundary)."""
        submission = self._active_submission
        if submission is not None:
            request, reduce_only = submission
            if reduce_only and self._submission_is_risk_reducing(request):
                return KillSwitchState(
                    active=False,
                    reason=(
                        "risk-reduction carve-out: reduce-only order that "
                        "verifiably reduces the live position (closing "
                        "order; new exposure stays blocked)"
                    ),
                )
        return self._ks_gate()

    def _submission_is_risk_reducing(self, request: OrderRequest) -> bool:
        try:
            order = self._runtime._oms.order(request.client_order_id)
        except Exception:
            return False
        position = self._runtime._positions.get(order.symbol)
        units = position.quantity if position is not None else Decimal("0")
        if units == 0:
            return False
        reduces = (
            (units > 0 and order.side == "SELL")
            or (units < 0 and order.side == "BUY")
        )
        return reduces and order.quantity <= abs(units)

    # -- the submission path ----------------------------------------------------
    def submission_block_reason(self) -> Optional[str]:
        """Fail-closed pre-check: a degraded (unreconciled) or
        unhealthy venue, or a runtime outside its operational state,
        refuses ALL new submissions (defence in depth beyond the
        bar-level operating-state guard)."""
        if self._session.degraded:
            return "venue_reconciliation_required"
        if self._session.health().value != "CONNECTED":
            return "venue_not_connected"
        state = self._runtime._state
        if state is not RuntimeState.RUNNING:
            return f"runtime_state_{state.value.lower()}"
        return None

    def submit_order(self, order, *, reduce_only: bool,
                     correlation_id: str) -> OrderAck:
        """Submit ONE risk-approved OMS order to the venue session.

        The ``client_order_id`` IS the OMS order id — one identity from
        decision to venue. Raises :class:`VenueSubmissionRefused`
        (definitive — the venue never saw it) or
        :class:`VenueSubmissionUncertain` (ambiguous — reconcile
        before ANY retry)."""
        request = OrderRequest(
            client_order_id=order.order_id,
            account_id=self._account_id,
            symbol=order.symbol,
            side=Side.BUY if order.side == "BUY" else Side.SELL,
            order_kind=(
                OrderKind.MARKET if order.order_type == "MARKET"
                else OrderKind.LIMIT
            ),
            quantity=order.quantity,
            price=order.limit_price,
            stop_price=None,
            time_in_force=TimeInForce.GTC,
            # Protective levels are RUNTIME-governed (the frozen paper
            # model attaches SL/TP to the position after the first
            # fill and submits exit orders through this same boundary)
            # — never venue-attached on the authoritative path.
            stop_loss=None,
            take_profit=None,
            reduce_only=reduce_only,
        )
        self._active_submission = (request, reduce_only)
        try:
            ack = self._session.submit_order(request)
        except OrderRefusedError as exc:
            raise VenueSubmissionRefused(exc.reason_code, str(exc)) \
                from exc
        except BrokerExecutionError as exc:
            raise VenueSubmissionUncertain(str(exc)) from exc
        finally:
            self._active_submission = None
        self._runtime._ledgers.record(
            ledger="order",
            event_type="ORDER_VENUE_SUBMITTED",
            correlation_id=correlation_id,
            actor="runtime.venue",
            payload={
                "order_id": order.order_id,
                "broker_id": self.broker_id,
                "account_id": self._account_id,
                "venue_order_id": ack.venue_order_id,
                "reduce_only": reduce_only,
            },
            parent_id=order.order_id,
        )
        return ack

    def poll_order(self, order, correlation_id: str) -> List:
        """Advance + journal venue truth for ONE live OMS order and
        return the NOT-yet-applied ``RuntimeFill`` delta.

        Exactly-once by construction: the delta is the venue's hosted
        fills beyond the count the OMS already holds. A redundant poll
        returns an empty delta."""
        cid = order.order_id
        # order_fills advances the hosted fill model against newly
        # admitted bars AND journals VENUE_SYNC (status + filled qty).
        self._session.order_fills(cid)
        venue_fills = self._adapter.runtime_fills(cid)
        applied = len(order.fills)
        if applied > len(venue_fills):
            raise BridgeContractError(
                f"venue poll for {cid!r}: the OMS holds {applied} fills "
                f"but the venue hosts {len(venue_fills)} — books diverged "
                "(fail closed; reconciliation required)"
            )
        return list(venue_fills[applied:])

    def cancel_order(self, order_id: str, correlation_id: str,
                     reason: str) -> None:
        """Cancel ONE order at the venue (kill-switch fill-time
        enforcement / TTL expiry sync). Failures are LEDGERED, never
        silenced — any resulting divergence surfaces at the next
        reconciliation and degrades the session."""
        try:
            self._session.cancel_order(order_id)
        except Exception as exc:
            self._runtime._ledgers.record(
                ledger="incident",
                event_type="VENUE_CANCEL_FAILED",
                correlation_id=correlation_id,
                actor="runtime.venue",
                payload={
                    "order_id": order_id,
                    "reason": reason,
                    "error": str(exc),
                    "action": (
                        "OMS cancellation proceeds; venue divergence will "
                        "surface at reconciliation (fail closed)"
                    ),
                },
            )

    # -- reconciliation -------------------------------------------------------
    def reconcile(self):
        """Journal expectations vs venue truth (the session's §32
        discipline; reports, never repairs)."""
        return self._session.reconcile()

    def resolve_ambiguity(self, correlation_id: str = "venue-resolve"):
        """Reconcile-and-resolve for ambiguous (UNKNOWN/RECONCILING)
        submissions. Resolution adopts VENUE truth — never an inferred
        failure: fills apply exactly once, the OMS lifecycle resolves,
        and the runtime resumes only on a CLEAN report.

        Phantom investigation: a venue order the journal never tracked
        (a lost-ack submission) is cross-checked against the OMS order
        parameters and adopted via the LEDGERED accept-venue-truth
        action (``sync_order_state``) — only for OMS orders currently
        in an ambiguous state, never silently."""
        runtime = self._runtime
        report = self._session.reconcile()
        if not report.ok:
            report = self._investigate_phantoms(report, correlation_id)
        if report.ok:
            self._apply_resolutions(report, correlation_id)
        else:
            if runtime._state is RuntimeState.RUNNING:
                runtime._flag_execution_uncertain(
                    "venue reconciliation mismatch after resolve attempt: "
                    + "; ".join(
                        f"{m.kind.value}:{m.client_order_id}"
                        for m in report.mismatches[:3]
                    ),
                    correlation_id,
                )
        return report

    def _investigate_phantoms(self, report, correlation_id):
        """Lost-ack adoption: a venue order the journal never tracked,
        cross-checked against the OMS order parameters, is re-adopted
        through the REAL submission pipeline — the OMS order (in an
        ambiguous state) is first resolved to SUBMITTED from the
        confirmed venue truth, then the IDENTICAL request is
        re-submitted through the guarded session (idempotent venue
        replay, never a re-execution) and venue truth is synced.
        Anything that does not cross-check EXACTLY stays blocked —
        operator attention required."""
        runtime = self._runtime
        phantoms = [
            m for m in report.mismatches
            if m.kind is ReconciliationMismatchKind.PHANTOM_ORDER_AT_VENUE
        ]
        for mismatch in phantoms:
            cid = mismatch.client_order_id
            try:
                oms_order = runtime._oms.order(cid)
            except Exception:
                continue
            if oms_order.status not in (
                OrderLifecycle.UNKNOWN, OrderLifecycle.RECONCILING,
            ):
                continue  # only ambiguous orders may adopt venue truth
            venue_order = self._adapter._orders.get(cid)
            if venue_order is None:
                continue
            vr = venue_order.request
            params_match = (
                vr.symbol == oms_order.symbol
                and vr.side.value == oms_order.side
                and vr.order_kind.value == oms_order.order_type
                and vr.quantity == oms_order.quantity
                and vr.price == oms_order.limit_price
            )
            if not params_match:
                continue  # REAL divergence: operator attention required
            # Venue truth confirms the order is LIVE: resolve the OMS
            # ambiguity to SUBMITTED (the legal reconciliation
            # resolution), then adopt the order into the session
            # journal through the EXPLICIT ledgered recovery action.
            runtime._oms.resolve_reconciling(
                cid, OrderLifecycle.SUBMITTED
            )
            runtime._ledgers.record(
                ledger="incident",
                event_type="VENUE_PHANTOM_ADOPTED",
                correlation_id=correlation_id,
                actor="runtime.venue",
                payload={
                    "order_id": cid,
                    "action": (
                        "lost-ack submission adopted from cross-checked "
                        "venue truth via the ledgered session adoption "
                        "action (never a re-execution)"
                    ),
                },
            )
            try:
                self._session.adopt_venue_order(vr)
            except BrokerExecutionError:
                continue  # adoption refused — stays blocked (fail closed)
        return self._session.reconcile()

    def _apply_resolutions(self, report, correlation_id) -> None:
        runtime = self._runtime
        for resolution in report.resolved:
            cid = resolution.client_order_id
            try:
                oms_order = runtime._oms.order(cid)
            except Exception:
                continue
            if oms_order.status not in (
                OrderLifecycle.UNKNOWN, OrderLifecycle.RECONCILING,
            ):
                continue
            runtime._resolve_venue_order(
                cid, resolution.status, correlation_id
            )
        # Terminal-state UNKNOWN resolutions are also possible through
        # phantom adoption (sync_order_state path): resolve any OMS
        # order still ambiguous whose venue truth is now journaled.
        for record in self._session._tracked_records():
            if record.status is None or record.status is \
                    VenueOrderStatus.UNKNOWN:
                continue
            cid = record.client_order_id
            try:
                oms_order = runtime._oms.order(cid)
            except Exception:
                continue
            if oms_order.status in (
                OrderLifecycle.UNKNOWN, OrderLifecycle.RECONCILING,
            ):
                runtime._resolve_venue_order(
                    cid, record.status, correlation_id
                )
        if runtime._state is RuntimeState.EXECUTION_UNCERTAIN:
            runtime._resume_after_venue_reconciliation(correlation_id)

    # -- restart recovery ------------------------------------------------------
    def recover(self, correlation_id: str = "venue-recovery"):
        """Restart recovery: rebuild the venue book from persisted OMS
        + journal truth and reconcile.

        Fail-closed rules:

        - LIVE OMS orders unknown to the venue journal refuse the
          attachment (no hidden direct-execution fallback, no silent
          migration of in-flight internal orders).
        - Journal orders the OMS does not hold refuse the attachment
          (the journal belongs to a different session's truth).
        - Journaled UNKNOWN outcomes are NEVER fabricated into the
          venue book — a fresh in-memory venue honestly does not hold
          them, reconciliation reports the mismatch, and the runtime
          stays blocked (EXECUTION_UNCERTAIN) until an operator
          resolves it. A lost ack NEVER infers failure.
        - Every rebuilt order's hosted fills are VERIFIED against the
          deterministic regeneration of the persisted state (bars +
          order parameters + realism): divergence refuses recovery.
        """
        runtime = self._runtime
        tracked = self._session._tracked_records()
        journal_cids = {r.client_order_id for r in tracked}
        # 1. no live OMS order may bypass the venue journal
        for live in runtime._oms.live_orders():
            if live.order_id not in journal_cids:
                raise BridgeContractError(
                    f"live OMS order {live.order_id} is unknown to the "
                    "venue journal — attaching a venue to a session with "
                    "in-flight INTERNAL orders would create a hidden "
                    "direct-execution fallback (refused; let the orders "
                    "expire or reconcile first)"
                )
        # 2. the journal must belong to THIS runtime's truth
        for record in tracked:
            try:
                runtime._oms.order(record.client_order_id)
            except Exception as exc:
                raise BridgeContractError(
                    f"the venue journal expects order "
                    f"{record.client_order_id!r} but this runtime's OMS "
                    "never held it — the journal belongs to a different "
                    "session's state (refusing, fail closed)"
                ) from exc
        # 3. rebuild the venue book (UNKNOWN orders are NOT fabricated)
        unknown_cids: List[str] = []
        for record in tracked:
            if record.status is VenueOrderStatus.UNKNOWN:
                unknown_cids.append(record.client_order_id)
                continue
            oms_order = runtime._oms.order(record.client_order_id)
            self._adapter.register_recovered_order(
                oms_order, record.status
            )
        # 4. reconcile journal vs the rebuilt venue truth
        report = self._session.reconcile()
        if not report.ok:
            if runtime._state is RuntimeState.RUNNING:
                runtime._flag_execution_uncertain(
                    "venue recovery: reconciliation mismatch ("
                    + "; ".join(
                        f"{m.kind.value}:{m.client_order_id}"
                        for m in report.mismatches[:3]
                    )
                    + ") — new submissions blocked until reconciled",
                    correlation_id,
                )
        elif unknown_cids:
            # A clean report cannot coexist with unregistered UNKNOWN
            # orders (they mismatch as ORDER_MISSING) — defensive.
            if runtime._state is RuntimeState.RUNNING:
                runtime._flag_execution_uncertain(
                    "venue recovery: unresolved UNKNOWN submission(s) "
                    + ", ".join(unknown_cids)
                    + " — reconcile before any new submission",
                    correlation_id,
                )
        return report


# ----------------------------------------------------------------------
# The authoritative attach factory (the Phase M2 completion seam)
# ----------------------------------------------------------------------
def attach_authoritative_paper_venue(
    runtime: TradingRuntime,
    *,
    account_id: str,
    journal_path: Path,
    clock: Callable[[], datetime],
    instruments: Mapping[str, InstrumentSpec],
    credential: BrokerCredential,
    currency: str = "USD",
    initial_balance: Decimal = Decimal("100000"),
    retry_policy=None,
    sleeper=None,
    adapter_factory=None,
) -> RuntimeAuthoritativeVenue:
    """Attach the broker-neutral execution venue to the runtime's
    AUTHORITATIVE order path (Phase M2 completion).

    From this moment every runtime order (entries AND protective
    exits) is submitted through the guarded ``BrokerSession``
    pipeline and fills EXCLUSIVELY from venue polls — the runtime's
    internal direct-execution path is replaced, not bypassed. The
    fill model is the runtime's own ``PaperExecutionAdapter`` hosted
    venue-side: fills are bit-identical to the internal path.

    Fail-closed contract:

    - ``instruments`` MUST contain a spec for the runtime's own
      symbol — precision is enforced, never guessed.
    - ``credential`` MUST be an account-matching ``BrokerCredential``
      holder (account isolation; the secret never reaches ledgers,
      snapshots, OMS records or the journal).
    - The runtime must be STARTED; a runtime with LIVE pre-venue
      (internal) orders refuses the attachment.
    - A RESTARTED runtime triggers venue-book recovery with
      deterministic-regeneration verification and reconciliation.
    - ``MOCK_DETERMINISTIC`` execution mode is enforced by the
      session; REAL adapters are refused. LIVE TRADING IS NOT
      AUTHORIZED.
    """
    if not isinstance(runtime, TradingRuntime):
        raise BridgeContractError(
            "attach_authoritative_paper_venue requires a TradingRuntime"
        )
    if runtime.venue is not None:
        raise BridgeContractError(
            "an authoritative venue is already attached to this runtime"
        )
    if runtime.state is RuntimeState.INIT:
        raise BridgeContractError(
            "start the runtime BEFORE attaching the venue (recovery "
            "ordering: runtime state first, venue book rebuild second)"
        )
    symbol = runtime.config.symbol
    specs = dict(instruments)
    if symbol not in specs:
        raise BridgeContractError(
            f"no instrument spec for the runtime's configured symbol "
            f"{symbol!r} — capability/precision cannot be enforced on a "
            "guess (fail closed; supply the venue's real spec)"
        )
    if not isinstance(credential, BrokerCredential):
        raise BridgeContractError(
            "a BrokerCredential holder is MANDATORY (account isolation)"
        )
    if not credential.matches_account(account_id):
        raise CredentialError(
            f"credential is for account {credential.account_id!r} but "
            f"this venue serves {account_id!r} (isolation refusal)"
        )
    if adapter_factory is None:
        def adapter_factory(rt, inst, acct, clk):
            return RuntimePaperExecutionAdapter(
                rt, instruments=inst, account_id=acct, clock=clk,
                currency=currency, initial_balance=initial_balance,
                authoritative=True,
            )
    adapter = adapter_factory(runtime, specs, account_id, clock)
    if not isinstance(adapter, RuntimePaperExecutionAdapter):
        raise BridgeContractError(
            "adapter_factory must produce a RuntimePaperExecutionAdapter "
            "(the authoritative venue hosts the runtime's own fill model)"
        )

    def kill_switch_fn() -> KillSwitchState:
        # Resolves `venue` at CALL time (the session is constructed
        # before the venue object exists; submissions are impossible
        # before both exist).
        return venue._kill_switch_state()

    session = BrokerSession(
        adapter,
        account_id=account_id,
        journal_path=Path(journal_path),
        risk_decision_fn=RuntimeOrderPathRiskGate(runtime),
        kill_switch_fn=kill_switch_fn,
        retry_policy=retry_policy,
        sleeper=sleeper,
        clock=clock,
    )
    venue = RuntimeAuthoritativeVenue(
        runtime, session, adapter, account_id
    )
    session.connect(credential)
    runtime._bind_authoritative_venue(venue)
    venue.recover()
    return venue


# ----------------------------------------------------------------------
# The side-band attach factory (Batch 3 — unchanged)
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
    "VenueSubmissionRefused",
    "VenueSubmissionUncertain",
    "RuntimeKillSwitchGate",
    "RuntimeRiskGateBridge",
    "RuntimeOrderPathRiskGate",
    "RuntimeAuthoritativeVenue",
    "RuntimePaperExecutionAdapter",
    "attach_runtime_paper_session",
    "attach_authoritative_paper_venue",
]
