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

    Phase 4A.1 filesystem security (spec SECTION 11, FS-01..FS-24):
    - approved-root containment on RESOLVED paths, by component
      (FS-01/02/03/05); no approved root -> fail closed, no I/O (FS-06)
    - endpoint escapes rejected (FS-07/08) BEFORE os.path.exists()
      and before any read (FS-09/10)
    - symlinks resolved and re-verified against containment
      (FS-11/12/13)
    - instrument identifiers validated against an allowlist BEFORE
      path construction (FS-14); separators/traversal/drive/UNC
      rejected (FS-15); filenames built only from validated
      identifiers (FS-16)
    - every allow and deny is recorded to the structured security
      audit trail when configured (FS-21/22)
    - rejections raise FilesystemSecurityError naming the rule (FS-20)
    """

    def __init__(self, config: ProviderConfig, registry: Optional[InstrumentRegistry] = None):
        super().__init__(config, registry)
        import os
        self._data_dir = config.endpoint or "./data"
        self._approved_root = config.approved_data_root
        self._audit_trail = None
        if config.audit_trail_path:
            from data_engine.security import SecurityAuditTrail
            self._audit_trail = SecurityAuditTrail(config.audit_trail_path)

    def _audit(self, path: str, decision: str, rule: str) -> None:
        """Record an allow/deny decision to the audit trail (FS-21)."""
        if self._audit_trail is not None:
            try:
                self._audit_trail.record(
                    actor=f"provider:{self.config.provider_name}",
                    path=str(path),
                    decision=decision,
                    rule=rule,
                )
            except (IOError, OSError):
                # Audit-trail write failure must not silently open a hole:
                # the containment decision itself already stands (fail
                # closed at the control, best-effort at the recorder).
                pass

    def _resolve_contained_dir(self):
        """Resolve the data directory and verify containment (FS-01..08)."""
        from pathlib import Path
        from data_engine.security import FilesystemSecurityError, ensure_containment
        if self._approved_root is None:
            # FS-06: fail closed — no I/O without an approved root.
            raise FilesystemSecurityError(
                "FS-06",
                "FileDataProvider has no approved_data_root configured — "
                "failing closed; no filesystem I/O is permitted.",
            )
        return ensure_containment(self._data_dir, self._approved_root, rule="FS-07")

    def _validate_instrument(self, instrument: str) -> str:
        """Validate the instrument before path construction (FS-14..16)."""
        from data_engine.security import validate_instrument_identifier
        registry_count = 0
        try:
            registry_count = len(getattr(self.registry, "_instruments", {}) or {})
        except Exception:
            registry_count = 0
        return validate_instrument_identifier(
            instrument,
            allowlist=self.config.instrument_allowlist,
            registry=self.registry,
            registry_count=registry_count,
        )

    def fetch_candles(self, instrument: str, timeframe: Timeframe, start: datetime, end: datetime) -> list:
        """Read candles from a contained, validated file path.

        Returns empty list if the (validated) file does not exist.
        Raises FilesystemSecurityError on any containment, traversal,
        or allowlist violation (FS-20) — BEFORE any existence check or
        read (FS-09/10).
        """
        from pathlib import Path
        from data_engine.security import FilesystemSecurityError, ensure_containment

        # FS-09: ALL validation happens before os.path.exists() / read.
        try:
            data_dir = self._resolve_contained_dir()
        except FilesystemSecurityError as exc:
            self._audit(str(self._data_dir), "DENY", exc.rule)
            raise
        try:
            # FS-14/15/16: instrument validated BEFORE path construction.
            validated_instrument = self._validate_instrument(instrument)
        except FilesystemSecurityError as exc:
            self._audit(f"instrument:{instrument}", "DENY", exc.rule)
            raise

        # FS-16: filename constructed ONLY from the validated identifier.
        filepath = Path(data_dir) / f"{validated_instrument}_{timeframe.value}.csv"

        try:
            # FS-12/13: resolve (following symlinks) and re-verify
            # containment of the final path.
            ensure_containment(filepath, self._approved_root, rule="FS-13")
        except FilesystemSecurityError as exc:
            self._audit(str(filepath), "DENY", exc.rule)
            raise

        import os
        if not os.path.exists(filepath):
            self._audit(str(filepath), "ALLOW", "FS-16")
            return []

        self._audit(str(filepath), "ALLOW", "FS-05")
        import pandas as pd
        df = pd.read_csv(filepath)
        candles = []
        # The provider contract declares its timezone (config.timezone,
        # default UTC); naive CSV timestamps are interpreted in that
        # contract so the range comparison is always well-defined.
        def _aware(ts: datetime) -> datetime:
            if ts is not None and ts.tzinfo is None:
                return ts.replace(tzinfo=UTC)
            return ts
        start_cmp, end_cmp = _aware(start), _aware(end)
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
                if start_cmp <= _aware(candle.timestamp) <= end_cmp:
                    candles.append(candle)
            except (ValueError, KeyError):
                continue
        return candles

    def fetch_instrument_info(self, symbol: str) -> Optional[Instrument]:
        return None  # File provider doesn't provide instrument metadata

    def check_connectivity(self) -> bool:
        """Check reachability of the CONTAINED data directory.

        The historical T5 defect (check_connectivity('C:/Windows') ->
        True — arbitrary directory enumeration) is closed: connectivity
        is only reported for a directory that resolves inside the
        approved root (FS-05); otherwise False.
        """
        from data_engine.security import FilesystemSecurityError
        try:
            data_dir = self._resolve_contained_dir()
        except FilesystemSecurityError:
            return False
        import os
        return os.path.isdir(data_dir)


# Register built-in provider
ProviderFactory.register("file", FileDataProvider)
