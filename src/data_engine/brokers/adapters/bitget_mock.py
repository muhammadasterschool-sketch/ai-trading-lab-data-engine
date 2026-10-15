"""Bitget spot v2 mock (clientOrderId/filter semantics, deterministic).

Batch 7 — the FIFTH deterministic mock venue, closing the Phase-1
discovery audit's broker-matrix gap ("Bitget: NOTHING — no adapter,
no mock, no market-data provider"). Encodes the broker-neutral
layer's Bitget-specific obligations:

- **MARKET/LIMIT only** — spot has no plain STOP kind and NO attached
  stop-loss/take-profit: stops are SEPARATE trigger (plan) order
  submissions. The capability descriptor declares
  ``SEPARATE_ORDERS``; requests carrying attached SL/TP fail closed
  with the venue-native alternative in the message.
- **clientOrderId** — first-class idempotency key.
- **Filters** — price/quantity precision + ``minTradeUSDT`` minimum
  notional; violations map to the venue's filter-failure code.
- **Balances-only account** — spot has no position object;
  ``positions()`` is empty by design.
- **Request + order rate limits** with ``retry_after``.

Representative v2 native codes preserved for audit (re-verified
against the live Bitget docs when the real adapter phase — a
separately operator-authorized review — begins): ``40001`` param
error (unknown symbol), ``43007`` filter/amount violation,
``43025`` order does not exist, ``42911`` frequency limit.

NO network. NO real credentials. NO real orders. The descriptor is
``MOCK_DETERMINISTIC`` and the capability registry structurally
refuses REAL execution modes at registration. LIVE TRADING IS NOT
AUTHORIZED.
"""

from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from data_engine.brokers.adapters._mock_core import DeterministicMockVenue
from data_engine.brokers.capabilities import BITGET_MOCK_CAPABILITIES
from data_engine.brokers.models import InstrumentSpec


def _bitget_instruments() -> tuple:
    return (
        InstrumentSpec(
            broker_id="bitget-mock",
            symbol="BTCUSDT",
            broker_symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            lot_step=Decimal("0.00001"),
            min_quantity=Decimal("0.00001"),
            max_quantity=Decimal("1000"),
            min_notional=Decimal("5"),
            reference_price=Decimal("50000.00"),
        ),
        InstrumentSpec(
            broker_id="bitget-mock",
            symbol="ETHUSDT",
            broker_symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            lot_step=Decimal("0.0001"),
            min_quantity=Decimal("0.0001"),
            max_quantity=Decimal("5000"),
            min_notional=Decimal("5"),
            reference_price=Decimal("3000.00"),
        ),
    )


class BitgetSpotMockAdapter(DeterministicMockVenue):
    """Bitget spot v2 semantics (deterministic, DEMO-class only)."""

    def __init__(
        self,
        clock: Callable[[], datetime],
        initial_balances: Optional[dict] = None,
    ) -> None:
        balances = initial_balances or {
            "USDT": Decimal("10000"),
            "BTC": Decimal("0.2"),
            "ETH": Decimal("2"),
        }
        super().__init__(
            capabilities=BITGET_MOCK_CAPABILITIES,
            instruments=_bitget_instruments(),
            initial_balances=balances,
            currency="USDT",
            clock=clock,
            fee_rate=Decimal("0.001"),
        )

    # -- venue-native code mapping ---------------------------------------
    def _precision_rejection_code(self) -> str:
        return "43007"  # filter/amount violation (representative v2 code)

    def _insufficient_funds_code(self) -> str:
        return "40009"  # insufficient balance (representative v2 code)

    def _unknown_order_code(self) -> str:
        return "43025"  # order does not exist (representative v2 code)

    def _unknown_symbol_code(self) -> str:
        return "40001"  # PARAM_ERROR — invalid symbol

    def _request_limit_code(self) -> str:
        return "42911"  # frequency limit (representative v2 code)

    def _order_limit_code(self) -> str:
        return "42911"


__all__ = ["BitgetSpotMockAdapter"]
