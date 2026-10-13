"""Deterministic mock adapters (multi-broker mandate, Phase M1 +
Batch 7 + Batch 15).

Seven in-memory venues sharing the engine in ``_mock_core``:

- :class:`PaperBrokerAdapter`     — paper/simulation (reference surface)
- :class:`MT5StyleMockAdapter`    — generic MT5-compatible class
- :class:`ExnessMT5MockAdapter`   — Exness, MT5 terminal class (Batch 15)
- :class:`XMMT5MockAdapter`       — XM, MT5 terminal class (Batch 15)
- :class:`BinanceSpotMockAdapter` — Binance spot REST/filter semantics
- :class:`BybitV5MockAdapter`     — Bybit v5 spot/linear semantics
- :class:`BitgetSpotMockAdapter`  — Bitget spot v2 clientOrderId semantics

NO network. NO real credentials. NO real orders. Live trading is NOT
AUTHORIZED in this repository — the real Binance/Bybit/Bitget/MT5/
Exness/XM adapters are future, separately-reviewed phases behind the
same interface.
"""

from data_engine.brokers.adapters.binance_mock import BinanceSpotMockAdapter
from data_engine.brokers.adapters.bitget_mock import BitgetSpotMockAdapter
from data_engine.brokers.adapters.bybit_mock import BybitV5MockAdapter
from data_engine.brokers.adapters.exness_mock import ExnessMT5MockAdapter
from data_engine.brokers.adapters.mt5_mock import MT5StyleMockAdapter
from data_engine.brokers.adapters.paper import PaperBrokerAdapter
from data_engine.brokers.adapters.xm_mock import XMMT5MockAdapter

__all__ = [
    "PaperBrokerAdapter",
    "MT5StyleMockAdapter",
    "ExnessMT5MockAdapter",
    "XMMT5MockAdapter",
    "BinanceSpotMockAdapter",
    "BybitV5MockAdapter",
    "BitgetSpotMockAdapter",
]
