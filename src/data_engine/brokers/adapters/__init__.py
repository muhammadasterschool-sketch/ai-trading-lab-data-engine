"""Deterministic mock adapters (multi-broker mandate, Phase M1 +
Batch 7).

Five in-memory venues sharing the engine in ``_mock_core``:

- :class:`PaperBrokerAdapter`     — paper/simulation (reference surface)
- :class:`MT5StyleMockAdapter`    — MT5-compatible class (Exness/XM-class)
- :class:`BinanceSpotMockAdapter` — Binance spot REST/filter semantics
- :class:`BybitV5MockAdapter`     — Bybit v5 spot/linear semantics
- :class:`BitgetSpotMockAdapter`  — Bitget spot v2 clientOrderId semantics

NO network. NO real credentials. NO real orders. Live trading is NOT
AUTHORIZED in this repository — the real Binance/Bybit/Bitget/MT5
adapters are future, separately-reviewed phases behind the same
interface.
"""

from data_engine.brokers.adapters.binance_mock import BinanceSpotMockAdapter
from data_engine.brokers.adapters.bitget_mock import BitgetSpotMockAdapter
from data_engine.brokers.adapters.bybit_mock import BybitV5MockAdapter
from data_engine.brokers.adapters.mt5_mock import MT5StyleMockAdapter
from data_engine.brokers.adapters.paper import PaperBrokerAdapter

__all__ = [
    "PaperBrokerAdapter",
    "MT5StyleMockAdapter",
    "BinanceSpotMockAdapter",
    "BybitV5MockAdapter",
    "BitgetSpotMockAdapter",
]
