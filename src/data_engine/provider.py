"""Provider abstraction layer for the AI Trading Lab Data Engine.

Provides a provider-independent interface so the research engine can
support multiple data providers without coupling to any single vendor.

Providers are not required to implement all methods — unavailable
fields must be represented as None, never fabricated.
"""

from abc import ABC, abstractmethod
from datetime import datetime, UTC
from typing import Optional, List, Dict
from pydantic import BaseModel
from data_engine.schemas import (
    Candle, Instrument, Timeframe, ProviderConfig,
    EvidenceProvenance, ValidationStatus
)
from data_engine.instruments import InstrumentRegistry


class MarketDataProvider(ABC):
    """Abstract base class for all market data providers.

    Subclasses must implement data retrieval. They must NEVER fabricate
    unavailable fields — return None instead.
    """

    def __init__(self, config: ProviderConfig, registry: Optional[InstrumentRegistry] = None):
        self.config = config
        self.registry = registry or InstrumentRegistry()
        self._api_key: Optional[str] = None

    @abstractmethod
    def fetch_candles(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> List[Candle]:
        """Fetch OHLCV candles for the given instrument and timeframe.

        Returns an empty list if no data is available.
        Never returns fabricated candles.
        """
        pass

    @abstractmethod
    def fetch_instrument_info(self, symbol: str) -> Optional[Instrument]:
        """Retrieve instrument metadata from the provider."""
        pass

    @abstractmethod
    def check_connectivity(self) -> bool:
        """Check if the provider endpoint is reachable."""
        pass

    def _load_api_key(self):
        """Load API key from environment variable if configured."""
        if self.config.api_key_env_var:
            import os
            self._api_key = os.environ.get(self.config.api_key_env_var)
            if self._api_key is None:
                raise EnvironmentError(
                    f"API key environment variable '{self.config.api_key_env_var}' "
                    f"is not set"
                )
        return self._api_key

    def _validate_candle(self, candle: Candle) -> bool:
        """Basic candle validation before returning to caller."""
        if candle.high < candle.low:
            return False
        if candle.open <= 0 or candle.close <= 0:
            return False
        if candle.volume is not None and candle.volume < 0:
            return False
        return True

    def retrieve_raw(
        self,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> Dict:
        """Retrieve raw provider response with full metadata.

        Returns a dict with 'raw_data', 'provider_metadata', and 'retrieval_timestamp'.
        This is the RAW layer — immutable after ingestion.
        """
        candles = self.fetch_candles(instrument, timeframe, start, end)
        return {
            "raw_data": candles,
            "provider": self.config.provider_name,
            "provider_type": self.config.provider_type,
            "instrument": instrument,
            "timeframe": timeframe.value,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "retrieval_timestamp": datetime.now(UTC).isoformat(),
            "timezone": self.config.timezone,
            "candle_count": len(candles),
            "api_key_loaded": self._api_key is not None,
        }


class ProviderFactory:
    """Factory for creating provider instances.

    Supports future provider types without coupling the research engine
    to any specific implementation.
    """

    _providers: Dict[str, type] = {}

    @classmethod
    def register(cls, name: str, provider_class: type):
        """Register a new provider type."""
        if not issubclass(provider_class, MarketDataProvider):
            raise TypeError(f"Provider must subclass MarketDataProvider, got {provider_class}")
        cls._providers[name] = provider_class

    @classmethod
    def create(cls, config: ProviderConfig, registry: Optional[InstrumentRegistry] = None) -> MarketDataProvider:
        """Create a provider instance by name."""
        provider_class = cls._providers.get(config.provider_name)
        if provider_class is None:
            raise ValueError(
                f"Unknown provider: '{config.provider_name}'. "
                f"Registered providers: {list(cls._providers.keys())}"
            )
        return provider_class(config, registry)

    @classmethod
    def registered_providers(cls) -> list:
        return list(cls._providers.keys())


# Built-in provider: File-based provider for archived data
class FileDataProvider(MarketDataProvider):
    """Provider that reads OHLCV data from CSV/JSON files.

    Used for backtesting with existing archival data (e.g., evtradelabs.com exports).
    """

    def __init__(self, config: ProviderConfig, registry: Optional[InstrumentRegistry] = None):
        super().__init__(config, registry)
        import os
        self._data_dir = config.endpoint or "./data"

    def fetch_candles(self, instrument: str, timeframe: Timeframe, start: datetime, end: datetime) -> list:
        """Read candles from a file. Returns empty list if file not found."""
        import os
        filepath = os.path.join(self._data_dir, f"{instrument}_{timeframe.value}.csv")
        if not os.path.exists(filepath):
            return []
        import pandas as pd
        df = pd.read_csv(filepath)
        candles = []
        for _, row in df.iterrows():
            try:
                candle = Candle(
                    timestamp=pd.to_datetime(row["timestamp"]),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume", 0)) if "volume" in row else None,
                    timeframe=timeframe,
                    bid=float(row["bid"]) if "bid" in row else None,
                    ask=float(row["ask"]) if "ask" in row else None,
                    spread=float(row["spread"]) if "spread" in row else None,
                )
                if start <= candle.timestamp <= end:
                    candles.append(candle)
            except (ValueError, KeyError):
                continue
        return candles

    def fetch_instrument_info(self, symbol: str) -> Optional[Instrument]:
        return None  # File provider doesn't provide instrument metadata

    def check_connectivity(self) -> bool:
        import os
        return os.path.isdir(self._data_dir)


# Register built-in provider
ProviderFactory.register("file", FileDataProvider)
