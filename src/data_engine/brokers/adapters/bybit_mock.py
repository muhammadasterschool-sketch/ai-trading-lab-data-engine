"""Bybit v5 mock (spot/linear order semantics, deterministic).

Encodes the broker-neutral layer's Bybit-specific obligations:

- **MARKET/LIMIT only** — conditional/trigger orders are a separate v5
  concept, not part of this phase's normalized kinds.
- **Attached SL/TP** — v5 orders carry stopLoss/takeProfit fields.
- **orderLinkId** — first-class idempotency key.
- **lotSizeFilter + minOrderAmt** — minOrderQty / qtyStep / minimum
  order amount; violations map to the venue's definitive codes.
- **One-way (netting) position mode** — hedge mode is a per-account
  switch on the real venue; the mock pins one-way semantics.
- **reduce-only** — supported and enforced against the net position.

Representative native retCodes preserved verbatim for audit: ``10004``
rate-limited, ``10001`` invalid parameters, ``10010`` order does not
exist, ``10014`` insufficient available balance, ``110007`` invalid
quantity/amount shape.
"""

from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from data_engine.brokers.adapters._mock_core import DeterministicMockVenue
from data_engine.brokers.capabilities import BYBIT_MOCK_CAPABILITIES
from data_engine.brokers.models import InstrumentSpec


def _bybit_instruments() -> tuple:
    return (
        InstrumentSpec(
            broker_id="bybit-mock",
            symbol="BTCUSDT",
            broker_symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.1"),
            lot_step=Decimal("0.001"),
            min_quantity=Decimal("0.001"),
            max_quantity=Decimal("1000"),
            min_notional=Decimal("5"),
            reference_price=Decimal("50000.0"),
        ),
        InstrumentSpec(
            broker_id="bybit-mock",
            symbol="ETHUSDT",
            broker_symbol="ETHUSDT",
            base_asset="ETH",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            lot_step=Decimal("0.01"),
            min_quantity=Decimal("0.01"),
            max_quantity=Decimal("5000"),
            min_notional=Decimal("1"),
            reference_price=Decimal("3000.00"),
        ),
    )


class BybitV5MockAdapter(DeterministicMockVenue):
    """Bybit v5 spot/linear semantics (deterministic, DEMO only)."""

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
            capabilities=BYBIT_MOCK_CAPABILITIES,
            instruments=_bybit_instruments(),
            initial_balances=balances,
            currency="USDT",
            clock=clock,
            fee_rate=Decimal("0.001"),
        )

    # -- venue-native code mapping ---------------------------------------
    def _precision_rejection_code(self) -> str:
        return "110007"  # qty/amount invalid (representative v5 code)

    def _insufficient_funds_code(self) -> str:
        return "10014"   # insufficient available balance

    def _unknown_order_code(self) -> str:
        return "10010"   # order does not exist

    def _unknown_symbol_code(self) -> str:
        return "10001"   # invalid parameters (symbol unknown)

    def _request_limit_code(self) -> str:
        return "10004"   # rate-limited

    def _order_limit_code(self) -> str:
        return "10004"


__all__ = ["BybitV5MockAdapter"]
