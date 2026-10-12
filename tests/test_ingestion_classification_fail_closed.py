"""Regression tests — ingestion classification + exit-code fail-closed defects.

Defect register (all CONFIRMED executable on 2026-10-12 by the probe
pattern in the audit record; every test below was RED against the
pre-fix implementation for exactly the documented reason):

- ING-NAT-1   unparseable/missing timestamps silently tolerated by the
              platform CSV audit: dataset classified REAL_UNVERIFIED,
              NaT-dated rows counted inside ``valid_ohlc_rows``.
              (``src/data_engine/platform/datasets.py::audit_csv_file``)
- ING-VOL-1   negative volume silently tolerated by the platform CSV
              audit: no counter, no finding, REAL_UNVERIFIED possible.
              (The newer master path already counts
              ``negative_volume_rows`` — this closes the inconsistency.)
- ING-COL-1   schema mismatch not consulted by classification
              (``expected_columns_match=False`` still classifies);
              missing critical columns crashed with a raw KeyError
              instead of a contract error.
- VAL-ORDER-1 out-of-order timestamps rated WARNING by the core
              ``DataValidator`` so ``DataIngester.ingest`` did not block
              the dataset (the platform CSV path already treats
              non-chronology as INVALID — closed in the strict
              direction, F-24 strengthening pattern).
- ING-STALE-1 ``scripts/platform_csv_ingest.py`` and
              ``scripts/master_data_ingest.py`` silently ingested a
              stale ``data/raw/`` destination copy when a newly
              supplied source file differed in content.
- ING-NVIEW-1 ``scripts/master_data_ingest.py`` swallowed normalized-view
              generation failures (bare ``except Exception`` + print)
              and still returned exit code 0.
"""

import hashlib
import importlib.util
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from data_engine.platform import CsvKind, audit_csv_file
from data_engine.prediction.datasets import DatasetState

REPO_ROOT = Path(__file__).resolve().parents[1]

FOREX_HEADER = (
    "Date,Symbol,Open,High,Low,Close,Volume_Ticks,Spread_Pips,"
    "Pip_Value_USD_StdLot,Max_Leverage,Swap_Long_Points,Swap_Short_Points,"
    "Session_Calendar\n"
)


def _fx_row(d: str, o=1.18, h=1.19, low=1.17, c=1.184, vol=1000) -> str:
    return f"{d},EURUSD,{o},{h},{low},{c},{vol},1.0,10.0,1:30,-2.1,0.5,24/5\n"


def _build(tmp: Path, name: str, rows, header: str = FOREX_HEADER) -> Path:
    p = tmp / name
    p.write_text(header + "".join(rows), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# ING-NAT-1 — unparseable timestamps must fail closed
# ---------------------------------------------------------------------------


class TestInvalidTimestampsFailClosed:
    def test_unparseable_date_counted_and_invalid(self, tmp_path: Path):
        rows = [
            _fx_row("2006-01-02"),
            _fx_row("not-a-date"),  # unparseable -> NaT
            _fx_row("2006-01-04"),
        ]
        audit = audit_csv_file(_build(tmp_path, "nat.csv", rows), CsvKind.FOREX)
        assert audit.invalid_timestamp_rows == 1
        assert audit.integrity_findings
        assert audit.recommended_state is DatasetState.INVALID

    def test_nat_row_not_counted_as_valid_ohlc(self, tmp_path: Path):
        rows = [
            _fx_row("2006-01-02"),
            _fx_row("not-a-date"),
            _fx_row("2006-01-04"),
        ]
        audit = audit_csv_file(_build(tmp_path, "nat.csv", rows), CsvKind.FOREX)
        # a row without a placeable timestamp is not a usable candle
        assert audit.instruments[0].valid_ohlc_rows == 2
        assert audit.instruments[0].rows == 3

    def test_all_nat_dates_fail_closed_without_crash(self, tmp_path: Path):
        rows = [_fx_row("garbage"), _fx_row("also-garbage")]
        audit = audit_csv_file(_build(tmp_path, "allnat.csv", rows), CsvKind.FOREX)
        assert audit.invalid_timestamp_rows == 2
        assert audit.recommended_state is DatasetState.INVALID

    def test_valid_dates_still_clean(self, tmp_path: Path):
        rows = [
            _fx_row("2006-01-02"),
            _fx_row("2006-01-03"),
            _fx_row("2006-01-04"),
        ]
        audit = audit_csv_file(_build(tmp_path, "ok.csv", rows), CsvKind.FOREX)
        assert audit.invalid_timestamp_rows == 0
        assert audit.recommended_state is not DatasetState.INVALID


# ---------------------------------------------------------------------------
# ING-VOL-1 — negative volume must fail closed
# ---------------------------------------------------------------------------


class TestNegativeVolumeFailsClosed:
    def test_negative_volume_counted_and_invalid(self, tmp_path: Path):
        rows = [
            _fx_row("2006-01-02", vol=-500),
            _fx_row("2006-01-03", vol=-500),
            _fx_row("2006-01-04", vol=-500),
        ]
        audit = audit_csv_file(_build(tmp_path, "negvol.csv", rows), CsvKind.FOREX)
        assert audit.negative_volume_rows == 3
        assert audit.integrity_findings
        assert audit.recommended_state is DatasetState.INVALID

    def test_zero_and_positive_volume_not_flagged(self, tmp_path: Path):
        rows = [
            _fx_row("2006-01-02", vol=0),
            _fx_row("2006-01-03", vol=100),
        ]
        audit = audit_csv_file(_build(tmp_path, "okvol.csv", rows), CsvKind.FOREX)
        assert audit.negative_volume_rows == 0
        assert audit.recommended_state is not DatasetState.INVALID

    def test_missing_volume_column_tolerated(self, tmp_path: Path):
        # Volume columns are part of each pinned schema, so REMOVING one
        # is (correctly) a schema mismatch under ING-COL-1. What must be
        # tolerated is the volume CHECK itself: no crash, the negative
        # volume counter stays 0, and the schema mismatch is the ONLY
        # finding (the audit must not fabricate volume findings for a
        # column it cannot see).
        header = FOREX_HEADER.replace("Volume_Ticks,", "")
        rows = [
            _fx_row("2006-01-02").replace(",1000,", ",", 1),
            _fx_row("2006-01-03").replace(",1000,", ",", 1),
        ]
        audit = audit_csv_file(_build(tmp_path, "novol.csv", rows, header), CsvKind.FOREX)
        assert audit.negative_volume_rows == 0
        assert audit.recommended_state is DatasetState.INVALID
        assert len(audit.integrity_findings) == 1
        assert "schema mismatch" in audit.integrity_findings[0]


# ---------------------------------------------------------------------------
# ING-COL-1 — schema mismatch must fail closed; missing critical columns
# must be a contract error, not a raw KeyError
# ---------------------------------------------------------------------------


class TestSchemaMismatchFailsClosed:
    def test_extra_column_invalidates(self, tmp_path: Path):
        header = FOREX_HEADER.replace(
            "Session_Calendar\n", "Session_Calendar,Unexpected_Extra\n")
        rows = [r.rstrip("\n") + ",surprise\n" for r in (
            _fx_row("2006-01-02"),
            _fx_row("2006-01-03"),
        )]
        audit = audit_csv_file(_build(tmp_path, "cols.csv", rows, header), CsvKind.FOREX)
        assert audit.expected_columns_match is False
        assert audit.integrity_findings
        assert audit.recommended_state is DatasetState.INVALID

    def test_missing_open_column_is_contract_error(self, tmp_path: Path):
        header = FOREX_HEADER.replace("Open,", "", 1)
        rows = [_fx_row("2006-01-02").split(",", 1)[1] + "\n"]
        with pytest.raises(ValueError, match="critical column"):
            audit_csv_file(_build(tmp_path, "noopen.csv", rows, header), CsvKind.FOREX)

    def test_missing_symbol_column_is_contract_error(self, tmp_path: Path):
        header = FOREX_HEADER.replace("Symbol,", "", 1)
        rows = ["2006-01-02,1.18,1.19,1.17,1.184,1000,1.0,10.0,1:30,-2.1,0.5,24/5\n"]
        with pytest.raises(ValueError, match="critical column"):
            audit_csv_file(_build(tmp_path, "nosym.csv", rows, header), CsvKind.FOREX)

    def test_expected_schema_still_clean(self, tmp_path: Path):
        rows = [_fx_row("2006-01-02"), _fx_row("2006-01-03")]
        audit = audit_csv_file(_build(tmp_path, "ok.csv", rows), CsvKind.FOREX)
        assert audit.expected_columns_match is True
        assert audit.recommended_state is not DatasetState.INVALID


# ---------------------------------------------------------------------------
# VAL-ORDER-1 — out-of-order timestamps must be INVALID in the core
# validator (not WARNING), so ingestion blocks them
# ---------------------------------------------------------------------------


def _make_candle(ts, o=100.0, h=101.0, low=99.0, c=100.5):
    from data_engine.schemas import Candle, Timeframe
    return Candle(timestamp=ts, open=o, high=h, low=low, close=c,
                  volume=10.0, timeframe=Timeframe.D1)


def _make_dataset(candles):
    from data_engine.schemas import (
        AssetClass, Dataset, DatasetVersion, EvidenceProvenance,
        Instrument, ProvenanceRecord, Timeframe,
    )
    now = datetime.now(UTC)
    inst = Instrument(symbol="EURUSD", asset_class=AssetClass.FX,
                      base_asset="EUR", quote_asset="USD", exchange="OTC")
    start = candles[0].timestamp if candles else now
    end = candles[-1].timestamp if candles else now
    prov = ProvenanceRecord(
        dataset_id="val_order_probe", dataset_version="v1.0.0",
        provider="probe", source="probe", instrument=inst,
        timeframe=Timeframe.D1, start_timestamp=start, end_timestamp=end,
        retrieval_timestamp=now, timezone="UTC",
        evidence_provenance=EvidenceProvenance.REAL,
    )
    return Dataset(
        dataset_id="val_order_probe",
        version=DatasetVersion(
            dataset_id="val_order_probe", version="v1.0.0", source="probe",
            instrument=inst, timeframe=Timeframe.D1,
            time_period_start=start, time_period_end=end,
            ingestion_version="1.0", transformation_version="1.0",
            validation_version="1.0",
        ),
        candles=candles, provenance=prov, raw_data_hash="probe",
        total_rows=len(candles),
    )


class TestCoreValidatorOutOfOrderInvalid:
    def test_out_of_order_dataset_is_invalid(self):
        from data_engine.validation import DataValidator
        candles = [
            _make_candle(datetime(2006, 1, 3, tzinfo=UTC)),
            _make_candle(datetime(2006, 1, 2, tzinfo=UTC)),  # out of order
            _make_candle(datetime(2006, 1, 4, tzinfo=UTC)),
        ]
        summary = DataValidator().get_validation_summary(_make_dataset(candles))
        assert summary["overall_status"].value == "INVALID"

    def test_chronological_dataset_stays_valid(self):
        from data_engine.validation import DataValidator
        candles = [
            _make_candle(datetime(2006, 1, 2, tzinfo=UTC)),
            _make_candle(datetime(2006, 1, 3, tzinfo=UTC)),
            _make_candle(datetime(2006, 1, 4, tzinfo=UTC)),
        ]
        summary = DataValidator().get_validation_summary(_make_dataset(candles))
        assert summary["overall_status"].value == "VALID"


# ---------------------------------------------------------------------------
# Script-level fail-closed behaviour (ING-STALE-1 / ING-NVIEW-1)
# ---------------------------------------------------------------------------


def _load_script(name: str):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_script_{name}", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[f"_script_{name}"] = mod
    spec.loader.exec_module(mod)
    return mod


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestPlatformScriptStaleSourceRefusal:
    def test_divergent_source_refused_loudly(self, tmp_path, monkeypatch, capsys):
        script = _load_script("platform_csv_ingest")
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "fx.csv").write_text(
            FOREX_HEADER + _fx_row("2006-01-02", c=1.18), encoding="utf-8")
        source = tmp_path / "source"
        source.mkdir()
        (source / "fx.csv").write_text(
            FOREX_HEADER + _fx_row("2006-01-02", c=1.20), encoding="utf-8")
        monkeypatch.setattr(script, "RAW", raw)
        monkeypatch.setattr(script, "MANIFESTS", tmp_path / "manifests")
        monkeypatch.setattr(script, "EXPORTS", tmp_path / "exports")
        monkeypatch.setattr(script, "FILES", (("fx.csv", CsvKind.FOREX),))
        rc = script.main([str(source)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "FATAL" in out
        assert "stale" in out.lower()

    def test_matching_source_proceeds_to_success(self, tmp_path, monkeypatch):
        script = _load_script("platform_csv_ingest")
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "fx.csv").write_text(
            FOREX_HEADER + _fx_row("2006-01-02", c=1.184), encoding="utf-8")
        source = tmp_path / "source"
        source.mkdir()
        # byte-identical content: no divergence, ingest proceeds
        (source / "fx.csv").write_text(
            FOREX_HEADER + _fx_row("2006-01-02", c=1.184), encoding="utf-8")
        monkeypatch.setattr(script, "RAW", raw)
        monkeypatch.setattr(script, "MANIFESTS", tmp_path / "manifests")
        monkeypatch.setattr(script, "EXPORTS", tmp_path / "exports")
        monkeypatch.setattr(script, "FILES", (("fx.csv", CsvKind.FOREX),))
        rc = script.main([str(source)])
        assert rc == 0

    def test_fresh_source_copied_and_ingested(self, tmp_path, monkeypatch):
        script = _load_script("platform_csv_ingest")
        raw = tmp_path / "raw"
        raw.mkdir()  # empty: no stale copy can shadow the source
        source = tmp_path / "source"
        source.mkdir()
        rows = [_fx_row("2006-01-02"), _fx_row("2006-01-03")]
        (source / "fx.csv").write_text(FOREX_HEADER + "".join(rows), encoding="utf-8")
        monkeypatch.setattr(script, "RAW", raw)
        monkeypatch.setattr(script, "MANIFESTS", tmp_path / "manifests")
        monkeypatch.setattr(script, "EXPORTS", tmp_path / "exports")
        monkeypatch.setattr(script, "FILES", (("fx.csv", CsvKind.FOREX),))
        rc = script.main([str(source)])
        assert rc == 0
        assert (raw / "fx.csv").exists()
        assert _sha256(raw / "fx.csv") == _sha256(source / "fx.csv")

    def test_missing_file_exits_nonzero_when_nothing_ingested(
            self, tmp_path, monkeypatch):
        script = _load_script("platform_csv_ingest")
        monkeypatch.setattr(script, "RAW", tmp_path / "raw")
        monkeypatch.setattr(script, "MANIFESTS", tmp_path / "manifests")
        monkeypatch.setattr(script, "EXPORTS", tmp_path / "exports")
        monkeypatch.setattr(script, "FILES", (("absent.csv", CsvKind.FOREX),))
        rc = script.main([str(tmp_path / "empty_source")])
        assert rc == 1


class TestMasterScriptFailClosed:
    def _patch_dirs(self, script, tmp_path, monkeypatch):
        raw = tmp_path / "raw"
        raw.mkdir()
        (raw / "m.csv").write_text("Date,Close\n2006-01-02,1.0\n", encoding="utf-8")
        monkeypatch.setattr(script, "RAW", raw)
        monkeypatch.setattr(script, "MANIFESTS", tmp_path / "manifests")
        monkeypatch.setattr(script, "PROCESSED", tmp_path / "processed")
        from data_engine.platform import MasterDataKind
        monkeypatch.setattr(script, "FILES", (("m.csv", MasterDataKind.STOCKS),))
        monkeypatch.setattr(
            script, "BUNDLE_DECLARED_SHA256", {"m.csv": _sha256(raw / "m.csv")})
        return raw

    def test_divergent_source_refused_loudly(self, tmp_path, monkeypatch, capsys):
        script = _load_script("master_data_ingest")
        raw = self._patch_dirs(script, tmp_path, monkeypatch)
        source = tmp_path / "source"
        source.mkdir()
        (source / "m.csv").write_text("Date,Close\n2006-01-03,2.0\n", encoding="utf-8")
        rc = script.main([str(source)])
        assert rc == 2
        out = capsys.readouterr().out
        assert "FATAL" in out

    def test_normalized_view_failure_returns_nonzero(
            self, tmp_path, monkeypatch):
        script = _load_script("master_data_ingest")
        raw = self._patch_dirs(script, tmp_path, monkeypatch)

        def _stub_ingest(*args, **kwargs):
            audit = SimpleNamespace(
                row_count=1,
                expected_columns_match=True,
                duplicate_asset_date_rows=0,
                non_chronological_rows=0,
                ohlc_violation_rows=0,
                non_positive_price_rows=0,
                nan_price_rows=0,
                d1_suitable_assets=1,
                asset_count=1,
            )
            return SimpleNamespace(
                dataset_id="DSV-stub", manifest_hash="h", file_name="m.csv",
                sha256=_sha256(raw / "m.csv"),
                kind=SimpleNamespace(value="stocks_master"),
                row_count=1, instrument_count=1,
                coverage_start="2006-01-02", coverage_end="2006-01-02",
                data_state=SimpleNamespace(value="REAL_UNVERIFIED"),
                to_manifest_json=lambda: "{}", audit=audit,
            )

        def _boom(records):
            raise RuntimeError("injected normalized-view failure")

        monkeypatch.setattr(script, "ingest_master_dataset", _stub_ingest)
        monkeypatch.setattr(script, "_write_normalized_views", _boom)
        rc = script.main([str(raw)])
        assert rc == 3

    def test_normalized_view_failure_propagates(self, tmp_path, monkeypatch):
        script = _load_script("master_data_ingest")
        self._patch_dirs(script, tmp_path, monkeypatch)
        import data_engine.platform.master_datasets as md

        def _boom(*args, **kwargs):
            raise ValueError("injected audit failure")

        monkeypatch.setattr(md, "audit_ohlcv_master", _boom)
        with pytest.raises(ValueError, match="injected audit failure"):
            script._write_normalized_views(
                [{"file_name": "m.csv", "content_sha256": "x"}])
