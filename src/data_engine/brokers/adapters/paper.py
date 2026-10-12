"""Paper/simulation execution adapter (multi-broker mandate, Phase M1).

The reference broker-neutral adapter: every capability is supported,
nothing throttles, money is play-money. It PROVES the neutral surface
end-to-end — and it is deliberately NOT the operational paper pipeline:
the frozen 22-module runtime simulator (``data_engine/runtime/``)
remains the authoritative paper engine. Wiring that runtime onto this
interface is Phase M2 and will be separately reviewed.
"""

from datetime import datetime
from decimal import Decimal
from typing import Callable, Mapping, Optional

from data_engine.brokers.adapters._mock_core import DeterministicMockVenue
from data_engine.brokers.capabilities import PAPER_MOCK_CAPABILITIES
from data_engine.brokers.models import InstrumentSpec


def _paper_instruments() -> tuple:
    return (
        InstrumentSpec(
            broker_id="paper-mock",
            symbol="BTCUSDT",
            broker_symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            tick_size=Decimal("0.01"),
            lot_step=Decimal("0.0001"),
            min_quantity=Decimal("0.0001"),
            max_quantity=Decimal("100"),
            min_notional=Decimal("0"),
            reference_price=Decimal("50000.00"),
        ),
        InstrumentSpec(
            broker_id="paper-mock",
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
    )


class PaperBrokerAdapter(DeterministicMockVenue):
    """Deterministic paper venue (all capabilities, DEMO only)."""

    def __init__(
        self,
        clock: Callable[[], datetime],
        initial_balances: Optional[Mapping[str, Decimal]] = None,
    ) -> None:
        super().__init__(
            capabilities=PAPER_MOCK_CAPABILITIES,
            instruments=_paper_instruments(),
            initial_balances=initial_balances or {
                "USDT": Decimal("100000"),
                "USD": Decimal("100000"),
                "BTC": Decimal("1"),
                "EUR": Decimal("100000"),
            },
            currency="USD",
            clock=clock,
            fee_rate=Decimal("0"),
        )

    # -- descriptive venue codes (the paper venue has no native API) ----
    def _precision_rejection_code(self) -> str:
        return "PAPER_INVALID_ORDER"

    def _insufficient_funds_code(self) -> str:
        return "PAPER_INSUFFICIENT_FUNDS"

    def _unknown_order_code(self) -> str:
        return "PAPER_UNKNOWN_ORDER"

    def _unknown_symbol_code(self) -> str:
        return "PAPER_UNKNOWN_SYMBOL"

    def _request_limit_code(self) -> str:
        return "PAPER_RATE_LIMITED"

    def _order_limit_code(self) -> str:
        return "PAPER_RATE_LIMITED"


__all__ = ["PaperBrokerAdapter"]
