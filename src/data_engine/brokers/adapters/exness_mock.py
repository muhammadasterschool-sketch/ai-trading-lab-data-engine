"""Exness MT5-terminal mock (deterministic, Batch 15 — item C-1).

Batch 11 §9 recorded Exness as having "NO adapter of any kind". This
module closes that gap at the honest level the architecture supports
today: a DEDICATED MT5-class deterministic mock venue. Exness is an
MT5/MT4 brokerage, so the terminal semantics are inherited VERBATIM
from :class:`~data_engine.brokers.adapters.mt5_mock.MT5StyleMockAdapter`
(hedging position tickets, attached SL/TP, volume-step lots,
comment-field idempotency, margin-style account-currency accounting,
MT5 TRADE_RETCODE mapping); what is NEW is the venue identity:

- own capability descriptor ``exness-mock`` (registered in the default
  :class:`~data_engine.brokers.capabilities.CapabilityRegistry`);
- own instrument set (Standard-account plain symbols: EURUSD, XAUUSD,
  BTCUSD) so platform-registry sync maps ``broker:exness-mock`` venue
  symbols onto the canonical identities without conflating brokers;
- own audit narrative: symbol suffixes and server names are
  ACCOUNT-TYPE facts that the operator verifies per account BEFORE any
  real adapter activation — UNVERIFIED brokers are not connectable by
  design.

NO network. NO real credentials. NO real orders. The descriptor is
``MOCK_DETERMINISTIC`` and the session structurally refuses REAL
execution modes. LIVE TRADING IS NOT AUTHORIZED.
"""

from datetime import datetime
from decimal import Decimal
from typing import Callable, Optional

from data_engine.brokers.adapters.mt5_mock import MT5StyleMockAdapter
from data_engine.brokers.capabilities import EXNESS_MOCK_CAPABILITIES
from data_engine.brokers.models import InstrumentSpec


def _exness_instruments() -> tuple:
    """Standard-account plain symbols (Exness MT5 class, deterministic)."""
    return (
        InstrumentSpec(
            broker_id="exness-mock",
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
            broker_id="exness-mock",
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
            broker_id="exness-mock",
            symbol="BTCUSD",
            broker_symbol="BTCUSD",  # Exness-style crypto CFD naming
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


class ExnessMT5MockAdapter(MT5StyleMockAdapter):
    """Exness MT5-terminal semantics (deterministic, DEMO-class only).

    Inherits the full MT5 class implementation — including the MT5
    TRADE_RETCODE mapping (10014 invalid volume, 10019 no money,
    10027 too many requests, ...) — and binds it to the Exness venue
    identity. NOT an Exness connection; real connectivity is a future,
    separately operator-authorized adapter behind the same interface.
    """

    def __init__(
        self,
        clock: Callable[[], datetime],
        initial_balance: Optional[Decimal] = None,
        account_mode: Optional[object] = None,
    ) -> None:
        super().__init__(
            clock,
            initial_balance,
            account_mode,
            capabilities=EXNESS_MOCK_CAPABILITIES,
            instruments=_exness_instruments(),
        )


__all__ = ["ExnessMT5MockAdapter"]
