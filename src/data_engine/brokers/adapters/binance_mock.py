"""Binance spot mock (REST/filter semantics, deterministic).

Encodes the broker-neutral layer's Binance-specific obligations:

- **MARKET/LIMIT only** — spot has no plain STOP kind and NO attached
  stop-loss/take-profit: stops are SEPARATE order submissions
  (STOP_LOSS_LIMIT / TAKE_PROFIT_LIMIT / OCO). The capability
  descriptor declares ``SEPARATE_ORDERS``; requests carrying attached
  SL/TP fail closed with the venue-native alternative in the message.
- **Filters** — tickSize / stepSize / MIN_NOTIONAL; violations map to
  the venue's definitive ``-1013`` filter failure.
- **newClientOrderId** — first-class idempotency key.
- **Request-weight rate limits** — HTTP 429-style throttling with
  ``retry_after``.
- **Balances-only account** — spot has no position object; positions()
  is empty by design.

Representative native codes preserved verbatim for audit: ``-1013``
filter failure, ``-2010`` insufficient balance, ``-2013`` order does
not exist, ``-1121`` invalid symbol, ``429``/``418`` throttling.
"""

from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from data_engine.brokers.adapters._mock_core import DeterministicMockVenue
from data_engine.brokers.capabilities import BINANCE_MOCK_CAPABILITIES
from data_engine.brokers.models import InstrumentSpec


def _binance_instruments() -> tuple:
    return (
        InstrumentSpec(
            broker_id="binance-mock",
            symbol="BTCUSDT",
            broker_symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            lot_step=Decimal("0.00001"),
            min_quantity=Decimal("0.00001"),
            max_quantity=Decimal("1000"),
            min_notional=Decimal("10"),
            reference_price=Decimal("50000.00"),
        ),
        InstrumentSpec(
            broker_id="binance-mock",
            symbol="ETHUSDT",
            broker_symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            lot_step=Decimal("0.0001"),
            min_quantity=Decimal("0.0001"),
            max_quantity=Decimal("5000"),
            min_notional=Decimal("10"),
            reference_price=Decimal("3000.00"),
        ),
    )


class BinanceSpotMockAdapter(DeterministicMockVenue):
    """Binance spot semantics (deterministic, DEMO/testnet-class only)."""

    def __init__(
        self,
        clock: Callable[[], datetime],
        initial_balances: Optional[dict] = None,
    ) -> None:
        balances = initial_balances or {
            "USDT": Decimal("10000"),
            "BTC": Decimal("0.5"),
            "ETH": Decimal("5"),
        }
        super().__init__(
            capabilities=BINANCE_MOCK_CAPABILITIES,
            instruments=_binance_instruments(),
            initial_balances=balances,
            currency="USDT",
            clock=clock,
            fee_rate=Decimal("0.001"),
        )

    # -- venue-native code mapping ---------------------------------------
    def _precision_rejection_code(self) -> str:
        return "-1013"  # FILTER_FAILURE (tick/step/minNotional/shape)

    def _insufficient_funds_code(self) -> str:
        return "-2010"  # NEW_ORDER_REJECTED: insufficient balance

    def _unknown_order_code(self) -> str:
        return "-2013"  # Order does not exist

    def _unknown_symbol_code(self) -> str:
        return "-1121"  # Invalid symbol

    def _request_limit_code(self) -> str:
        return "429"    # HTTP Too Many Requests

    def _order_limit_code(self) -> str:
        return "429"


__all__ = ["BinanceSpotMockAdapter"]
