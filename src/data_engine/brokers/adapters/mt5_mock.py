"""MT5-compatible broker mock (Exness/XM-class retail semantics).

Deterministic in-memory simulation of COMMON MT5 terminal semantics —
NOT a MetaTrader5 connection (the real, Windows-terminal-bound read
surface lives in ``data_engine/platform/mt5.py`` and its order path is
structurally refused). This mock encodes what the broker-neutral layer
must handle for the MT5 broker CLASS:

- **Hedging position tickets** — each accepted MARKET order opens one
  ticket; ``positions()`` returns per-ticket records.
- **Attached SL/TP** — orders carry stop-loss/take-profit fields.
- **Volume-step lots** — ``volume_min``/``volume_step``/``volume_max``
  per symbol; misalignment is a definitive rejection (retcode-style).
- **Comment-field idempotency** — MT5 has no native client-order-id;
  the discipline rides the free-text comment (the mock enforces the
  guarantee; the descriptor documents the mechanism).
- **Account-currency accounting** — the opening deal charges
  commission; realized P&L settles at position CLOSE (margin-style),
  not on every base/quote exchange.
- **REAL account modes are refused by construction** — live trading is
  NOT AUTHORIZED in this repository.

Exness/XM account support ("only where account support is verified")
is an OPERATOR verification step outside this mock: symbol suffixes
(e.g. ``EURUSDm``), server names and account modes must be confirmed
per account before any real adapter is enabled. Unverified brokers
are not connectable by design.
"""

from datetime import datetime
from decimal import Decimal
from typing import Callable, Dict, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.brokers.adapters._mock_core import DeterministicMockVenue, MockVenueError
from data_engine.brokers.capabilities import MT5_MOCK_CAPABILITIES
from data_engine.brokers.models import (
    InstrumentSpec,
    OrderRequest,
    PositionRecord,
    Side,
    VenueFill,
)


def _mt5_instruments() -> tuple:
    return (
        InstrumentSpec(
            broker_id="mt5-mock",
            symbol="EURUSD",
            broker_symbol="EURUSD",
            base_asset="EUR",
            quote_asset="USD",
            tick_size=Decimal("0.00001"),
            lot_step=Decimal("0.01"),
            min_quantity=Decimal("0.01"),
            max_quantity=Decimal("100"),
            min_notional=Decimal("0"),
            reference_price=Decimal("1.10000"),
        ),
        InstrumentSpec(
            broker_id="mt5-mock",
            symbol="XAUUSD",
            broker_symbol="XAUUSD",
            base_asset="XAU",
            quote_asset="USD",
            tick_size=Decimal("0.01"),
            lot_step=Decimal("0.01"),
            min_quantity=Decimal("0.01"),
            max_quantity=Decimal("50"),
            min_notional=Decimal("0"),
            reference_price=Decimal("2350.00"),
        ),
        InstrumentSpec(
            broker_id="mt5-mock",
            symbol="BTCUSD",
            broker_symbol="BTCUSD",  # Exness/XM-style crypto CFD naming
            base_asset="BTC",
            quote_asset="USD",
            tick_size=Decimal("0.01"),
            lot_step=Decimal("0.01"),
            min_quantity=Decimal("0.01"),
            max_quantity=Decimal("10"),
            min_notional=Decimal("0"),
            reference_price=Decimal("50000.00"),
        ),
    )


class _MT5Position(BaseModel):
    """One open hedging ticket at the MT5-style mock."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ticket: str
    symbol: str
    side: Side
    quantity: Decimal
    entry_price: Decimal
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    opened_at: datetime


class MT5StyleMockAdapter(DeterministicMockVenue):
    """Exness/XM-class MT5 semantics (deterministic, DEMO only)."""

    def __init__(
        self,
        clock: Callable[[], datetime],
        initial_balance: Optional[Decimal] = None,
        account_mode: Optional[object] = None,
    ) -> None:
        from data_engine.brokers.models import AccountMode
        if account_mode is None:
            account_mode = AccountMode.DEMO
        if not isinstance(account_mode, AccountMode):
            raise MockVenueError("account_mode must be an AccountMode value")
        super().__init__(
            capabilities=MT5_MOCK_CAPABILITIES,
            instruments=_mt5_instruments(),
            initial_balances={"USD": initial_balance or Decimal("10000")},
            currency="USD",
            clock=clock,
            account_mode=account_mode,
            fee_rate=Decimal("0.0002"),  # commission-style rate on notional
        )
        self._open_positions: Dict[str, _MT5Position] = {}
        self._realized_total = Decimal("0")

    # -- venue-native code mapping (representative TRADE_RETCODEs) ------
    def _precision_rejection_code(self) -> str:
        return "10014"  # TRADE_RETCODE_INVALID_VOLUME (volume/price shape)

    def _insufficient_funds_code(self) -> str:
        return "10019"  # TRADE_RETCODE_NO_MONEY

    def _unknown_order_code(self) -> str:
        return "10036"  # TRADE_RETCODE_POSITION_CLOSED / order unknown

    def _unknown_symbol_code(self) -> str:
        return "SYMBOL_UNKNOWN"  # descriptive: symbol lookup precedes retcodes

    def _request_limit_code(self) -> str:
        return "10027"  # TRADE_RETCODE_TOO_MANY_REQUESTS

    def _order_limit_code(self) -> str:
        return "10027"

    # -- MT5-specific accounting -----------------------------------------

    def _check_sufficient_funds(
        self, request: OrderRequest, spec: InstrumentSpec
    ) -> Optional[Tuple[str, str]]:
        """Margin-style placement: no base/quote asset requirement at
        order time (the mock does not model margin; the account-currency
        balance moves by COMMISSION at open and by P&L at close)."""
        return None

    def _apply_fill_accounting(
        self,
        request: OrderRequest,
        spec: InstrumentSpec,
        fill: VenueFill,
    ) -> None:
        """Margin-style: the opening deal charges COMMISSION only; the
        account-currency balance does not exchange base/quote."""
        self._balances[self._currency] = (
            self._balances.get(self._currency, Decimal("0")) - fill.fee
        )
        if self._balances[self._currency] < 0:
            from data_engine.brokers.adapters._mock_core import MockVenueError
            raise MockVenueError(
                "MT5 mock accounting went negative — commission pre-check "
                "is missing (defect)"
            )
        # One hedging ticket per accepted order (opening fill).
        self._open_positions[fill.venue_order_id] = _MT5Position(
            ticket=fill.venue_order_id,
            symbol=fill.symbol,
            side=fill.side,
            quantity=fill.quantity,
            entry_price=fill.price,
            stop_loss=request.stop_loss,
            take_profit=request.take_profit,
            opened_at=fill.filled_at,
        )

    def positions(self) -> Tuple[PositionRecord, ...]:
        """Per-ticket position records (HEDGING semantics)."""
        from data_engine.brokers.models import ConnectionState
        self._api_guard()
        return tuple(
            PositionRecord(
                account_id=self._bound_account,
                broker_id=self._broker_id,
                symbol=pos.symbol,
                quantity=(pos.quantity if pos.side is Side.BUY else -pos.quantity),
                average_entry_price=pos.entry_price,
                realized_pnl=Decimal("0"),  # open tickets carry no realized P&L
                ticket=pos.ticket,
            )
            for pos in sorted(self._open_positions.values(), key=lambda p: p.ticket)
        )

    def account_realized_pnl(self) -> Decimal:
        """Total realized P&L settled through ``close_position``."""
        return self._realized_total

    def close_position(self, ticket: str, price: Decimal) -> Decimal:
        """TEST HOOK: settle one open ticket at ``price``.

        Realized P&L lands in the account-currency balance; the ticket
        is removed. (A real MT5 close is itself a deal — modelling it
        as an explicit hook keeps the mock's order book clean.)
        """
        from data_engine.brokers.adapters._mock_core import MockVenueError
        self._api_guard()
        pos = self._open_positions.get(ticket)
        if pos is None:
            raise MockVenueError(f"no open ticket {ticket!r}")
        if pos.side is Side.BUY:
            pnl = (price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - price) * pos.quantity
        self._realized_total += pnl
        self._balances[self._currency] = (
            self._balances.get(self._currency, Decimal("0")) + pnl
        )
        del self._open_positions[ticket]
        return pnl


__all__ = ["MT5StyleMockAdapter"]
