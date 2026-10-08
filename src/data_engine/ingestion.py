"""Raw data ingestion layer for the AI Trading Lab Data Engine.

Implements strict RAW → PROCESSED → RESEARCH separation.
Raw data is immutable after ingestion. Never overwritten.
"""

from datetime import datetime, UTC
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from data_engine.schemas import Candle, Dataset, Instrument, Timeframe, ValidationStatus
from data_engine.provider import MarketDataProvider, ProviderFactory
from data_engine.validation import DataValidator
from data_engine.provenance import ProvenanceRecord, DatasetVersion
from data_engine.quarantine import QuarantineManager
from data_engine.data_blocked import DATA_QUALITY_BLOCKED, DataQualityBlockedError
from data_engine.evidence import EvidenceProvenance  # ARCH-F3: used at line 191, previously never imported


class IngestionResult(BaseModel):
    """Result of a data ingestion operation."""
    dataset: Optional[Dataset] = None
    quarantine_report: Optional[List[Dict]] = None
    blocked: bool = False
    block_reason: Optional[str] = None
    validation_summary: Optional[dict] = None


class DataIngester:
    """Ingestion orchestrator.

    Manages the flow: Provider → Raw → Validation → Canonical Dataset.
    Raw data is never overwritten by processed data.
    """

    def __init__(self):
        self.validator = DataValidator()
        self.quarantine = QuarantineManager()
        self._raw_store: Dict[str, List] = {}  # Immutable raw storage
        self._ingestion_log: List[Dict] = []

    def ingest(
        self,
        provider: MarketDataProvider,
        instrument: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
        evidence_provenance: str = "UNKNOWN",
        dataset_id: Optional[str] = None,
        dataset_version: Optional[str] = None,
    ) -> IngestionResult:
        """Ingest data from a provider through to canonical dataset.

        Flow:
        1. Retrieve raw data from provider
        2. Store raw data immutably
        3. Validate all candles
        4. If validation fails critically → DATA_QUALITY_BLOCKED
        5. Build canonical dataset with provenance
        """
        # Step 1: Retrieve raw data
        raw = provider.retrieve_raw(instrument, timeframe, start, end)
        candles = raw.get("raw_data", [])

        # Store raw data immutably
        raw_key = self._raw_key(provider.config.provider_name, instrument, timeframe, start, end)
        self._raw_store[raw_key] = candles  # Never overwritten

        # Step 2: Validate
        if not candles:
            return IngestionResult(
                blocked=True,
                block_reason=DATA_QUALITY_BLOCKED,
                validation_summary={
                    "status": "INVALID",
                    "reason": "No candles returned from provider",
                    "dataset_id": dataset_id or "unknown",
                }
            )

        # Build instrument
        instrument_obj = provider.fetch_instrument_info(instrument)
        if instrument_obj is None:
            instrument_obj = self._fallback_instrument(instrument)

        # Build provenance
        provenance = self._build_provenance(
            provider=provider.config,
            instrument=instrument_obj,
            timeframe=timeframe,
            start=start,
            end=end,
            evidence_provenance=evidence_provenance,
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            source_hash=self._compute_raw_hash(candles),
        )

        # Build dataset
        from data_engine.schemas import Dataset, DatasetVersion
        dataset_version_obj = DatasetVersion(
            dataset_id=provenance.dataset_id,
            version=provenance.dataset_version,
            source=provider.config.provider_name,
            instrument=instrument_obj,
            timeframe=timeframe,
            time_period_start=start,
            time_period_end=end,
            ingestion_version="1.0",
            transformation_version="1.0",
            validation_version="1.0",
        )

        dataset = Dataset(
            dataset_id=provenance.dataset_id,
            version=dataset_version_obj,
            candles=candles,
            provenance=provenance,
            raw_data_hash=self._compute_raw_hash(candles),
            total_rows=len(candles),
        )

        # Step 3: Validate dataset
        results = self.validator.validate_dataset(dataset)
        summary = self.validator.get_validation_summary(dataset)

        # Step 4: Check for critical failures
        if summary["overall_status"] == ValidationStatus.INVALID:
            invalid_candles = [r for r in results if r.status == ValidationStatus.INVALID]
            self.quarantine.quarantine(dataset.dataset_id, invalid_candles)
            return IngestionResult(
                blocked=True,
                block_reason=DATA_QUALITY_BLOCKED,
                quarantine_report=invalid_candles,
                validation_summary=summary,
            )

        # Step 5: Success
        self._ingestion_log.append({
            "timestamp": datetime.now(UTC).isoformat(),
            "dataset_id": dataset.dataset_id,
            "provider": provider.config.provider_name,
            "instrument": instrument,
            "timeframe": timeframe.value,
            "candle_count": len(candles),
            "validation_status": summary["overall_status"].value,
            "raw_key": raw_key,
        })

        return IngestionResult(
            dataset=dataset,
            validation_summary=summary,
            blocked=False,
        )

    def _fallback_instrument(self, instrument: str):
        """Fallback instrument when the provider supplies no metadata.

        RT-F8 correction companion: the previous fallback passed
        ``asset_class=None`` — a value the Instrument contract can
        never validate — so the file-provider ingestion path died with
        a ValidationError even after the FS-06 root fix. This fallback
        classifies the symbol with the repository's own classifier
        (``instruments.InstrumentRegistry.classify_asset_class``) and
        FAILS CLOSED for symbols it cannot honestly classify — no
        fabricated asset classes.
        """
        from data_engine.instruments import InstrumentRegistry
        from data_engine.schemas import Instrument

        asset_class = InstrumentRegistry().classify_asset_class(instrument)
        if asset_class is None:
            raise ValueError(
                f"provider supplied no instrument metadata for "
                f"{instrument!r} and the symbol cannot be classified — "
                "refusing to fabricate an asset class (fail closed)"
            )
        if "/" in instrument:
            base, quote = instrument.split("/", 1)
        else:
            base, quote = instrument, "USD"
        return Instrument(
            symbol=instrument,
            asset_class=asset_class,
            base_asset=base,
            quote_asset=quote,
        )

    def get_raw_data(self, key: str) -> Optional[List]:
        """Retrieve immutable raw data by key."""
        return self._raw_store.get(key)

    def _raw_key(self, provider_name, instrument, timeframe, start, end) -> str:
        return f"{provider_name}::{instrument}::{timeframe.value}::{start.isoformat()}::{end.isoformat()}"

    def _compute_raw_hash(self, candles: List[Candle]) -> str:
        """Deterministic raw-data hash (ARCH-F6 correction).

        The OLD implementation chained ``Candle.to_hash()`` — which is
        wall-clock contaminated through the ``provider_timestamp``
        default factory (H-1 / F-04 family): two structurally identical
        candle lists hashed differently depending on construction
        time. This implementation hashes the CANONICAL market-data
        fields of each candle via the PIT deterministic hash and
        deliberately EXCLUDES ``provider_timestamp``: identical market
        data now hashes identically, keeping the H-1 containment
        posture (the dormant path never invokes the contaminated
        ``to_hash``) without amending the frozen Candle model.
        """
        import hashlib
        from data_engine.pit.hashing import deterministic_hash
        digests = [
            deterministic_hash(
                {
                    "timestamp": c.timestamp.isoformat(),
                    "open": c.open,
                    "high": c.high,
                    "low": c.low,
                    "close": c.close,
                    "volume": c.volume,
                    "timeframe": c.timeframe.value,
                    "bid": c.bid,
                    "ask": c.ask,
                    "spread": c.spread,
                    "currency": c.currency,
                }
            )
            for c in candles
        ]
        return hashlib.sha256(
            ("[" + ",".join(digests) + "]").encode()
        ).hexdigest()

    def _build_provenance(self, provider, instrument, timeframe, start, end,
                          evidence_provenance, dataset_id, dataset_version, source_hash):
        from data_engine.schemas import ProvenanceRecord, Instrument
        import uuid
        if not dataset_id:
            dataset_id = f"ds_{uuid.uuid4().hex[:12]}"
        if not dataset_version:
            dataset_version = f"v1.0.0_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"

        return ProvenanceRecord(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            provider=provider.provider_name,
            source=provider.provider_type,
            instrument=instrument,
            timeframe=timeframe,
            start_timestamp=start,
            end_timestamp=end,
            retrieval_timestamp=datetime.now(UTC),
            timezone=provider.timezone,
            source_hash=source_hash,
            evidence_provenance=EvidenceProvenance(evidence_provenance),
        )


def ingest_from_file(
    file_path: str,
    instrument: str,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    evidence_provenance: str = "REAL",
    dataset_id: Optional[str] = None,
) -> IngestionResult:
    """Convenience function to ingest from a file-based provider.

    Used for backtesting with archived data from evtradelabs.com etc.

    RT-F8 correction: the data directory is derived from the caller's
    ``file_path`` and supplied EXPLICITLY as the provider's approved
    data root (FS-04) — the previous implementation hard-coded
    ``endpoint="./data"`` with NO approved root, so the FS-06
    fail-closed containment layer rejected every read before it
    happened (dead path). The security invariant is unchanged: file
    I/O still fails closed without an approved root; the approval is
    now supplied by the calling operator instead of being absent.

    Filename convention: the file provider constructs its filename
    from the validated instrument and timeframe — ``file_path`` must
    therefore be named ``{instrument}_{timeframe.value}.csv`` inside
    its directory (a mismatch fails closed with an explicit contract
    error instead of a silently empty dataset).
    """
    from pathlib import Path
    from data_engine.schemas import ProviderConfig
    from data_engine.provider import ProviderFactory

    resolved = Path(file_path).expanduser().resolve()
    expected_name = f"{instrument}_{timeframe.value}.csv"
    if resolved.name != expected_name:
        raise ValueError(
            f"ingest_from_file contract (RT-F8): file must be named "
            f"{expected_name!r} for instrument {instrument!r} / "
            f"timeframe {timeframe.value!r}, got {resolved.name!r}"
        )
    data_dir = resolved.parent
    config = ProviderConfig(
        provider_name="file",
        provider_type="file",
        endpoint=str(data_dir),
        approved_data_root=str(data_dir),  # FS-04: explicit caller approval
        instrument_allowlist=[instrument],  # FS-14: caller names the instrument
        timezone="UTC",
    )
    provider = ProviderFactory.create(config)
    ingester = DataIngester()
    return ingester.ingest(
        provider=provider,
        instrument=instrument,
        timeframe=timeframe,
        start=start,
        end=end,
        evidence_provenance=evidence_provenance,
        dataset_id=dataset_id,
    )
