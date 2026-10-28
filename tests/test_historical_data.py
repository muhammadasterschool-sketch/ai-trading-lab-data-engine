"""v1.5.0 historical data tests — bundled verified datasets + the
Binance Vision source (checksum-verified, injectable transport) +
BarStore import.

Deterministic, offline: network transport is ALWAYS faked. The
bundled-dataset tests read the real ``datasets/`` shipped in the repo
(they are part of the source tree, not the network).
"""

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

import pytest

from data_engine.platform.historical_data import (
    BinanceVisionSource,
    HistoricalDataError,
    HistoricalDataService,
    find_datasets_root,
    list_bundled_datasets,
    load_bundled_dataset,
)
from data_engine.runtime.lab import BarStore

NOW = datetime(2026, 10, 28, tzinfo=timezone.utc)


def _fake_binance_zip(symbol: str, rows: int = 50) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        lines = []
        for i in range(rows):
            ts_us = (1_788_220_400 + i * 60) * 1_000_000
            price = 100.0 + i * 0.1
            lines.append(
                f"{ts_us},{price},{price + 0.5},{price - 0.5},{price},"
                f"10.5,{ts_us + 59_999_999},1050.0,3,5.0,50.0,0"
            )
        zf.writestr(f"{symbol}-1m.csv", "\n".join(lines))
    return buffer.getvalue()


class _FakeTransport:
    """Serves a fake monthly zip + its matching .CHECKSUM."""

    def __init__(self, payload: bytes, fail_urls=()):
        self.payload = payload
        self.fail_urls = set(fail_urls)
        self.calls = []

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if url in self.fail_urls:
            raise OSError("boom")
        if url.endswith(".CHECKSUM"):
            digest = hashlib.sha256(self.payload).hexdigest()
            return f"{digest}  {url.rsplit('/', 1)[-1]}\n".encode()
        return self.payload


class TestBundledDatasets:
    def test_repo_ships_two_verified_datasets(self):
        rows = list_bundled_datasets()
        ids = {d["id"] for d in rows}
        assert "binance-spot-BTCUSDT-1m-2026-09" in ids
        assert "binance-spot-ETHUSDT-1m-2026-09" in ids
        for row in rows:
            assert row["governance"] == "RESEARCH_BACKTEST_ONLY"
            assert row["sha256"] and len(row["sha256"]) == 64

    def test_bundled_load_verifies_sha_and_parses(self):
        result = load_bundled_dataset("binance-spot-BTCUSDT-1m-2026-09")
        assert result["count"] == 43200
        assert result["provenance"]["checksum_verified"] is True
        first = result["bars"][0]
        assert set(first) == {"ts", "open", "high", "low", "close", "volume"}
        assert first["ts"].startswith("2026-09-01T00:00")

    def test_bundled_unknown_dataset_refused(self):
        with pytest.raises(HistoricalDataError):
            load_bundled_dataset("nope")

    def test_bundled_tamper_detected(self, tmp_path, monkeypatch):
        root = find_datasets_root()
        assert root is not None
        # copy datasets to a tampered twin
        twin = tmp_path / "datasets"
        twin.mkdir()
        for f in root.rglob("*"):
            if f.is_file():
                target = twin / f.relative_to(root)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(f.read_bytes())
        victim = twin / "binance-spot/1m/BTCUSDT-1m-2026-09.zip"
        victim.write_bytes(b"tampered")
        monkeypatch.setenv("AITL_DATASETS_DIR", str(twin))
        with pytest.raises(HistoricalDataError, match="MISMATCH"):
            load_bundled_dataset("binance-spot-BTCUSDT-1m-2026-09")


class TestBinanceVisionSource:
    def test_fetch_month_verifies_checksum(self, tmp_path):
        payload = _fake_binance_zip("BTCUSDT")
        transport = _FakeTransport(payload)
        source = BinanceVisionSource(cache_dir=tmp_path, transport=transport)
        result = source.fetch_month("BTCUSDT", "1m", 2026, 8)
        assert result["count"] == 50
        assert result["provenance"]["checksum_verified"] is True
        # zip + checksum both fetched
        assert len(transport.calls) == 2

    def test_cached_payload_still_verified(self, tmp_path):
        payload = _fake_binance_zip("BTCUSDT")
        transport = _FakeTransport(payload)
        source = BinanceVisionSource(cache_dir=tmp_path, transport=transport)
        source.fetch_month("BTCUSDT", "1m", 2026, 8)
        # second fetch: cache hit, but the CHECKSUM is still verified
        result = source.fetch_month("BTCUSDT", "1m", 2026, 8)
        assert result["provenance"]["cached"] is True
        assert result["provenance"]["checksum_verified"] is True

    def test_checksum_mismatch_refused(self, tmp_path):
        payload = _fake_binance_zip("BTCUSDT")
        bad = _FakeTransport(payload)

        def wrong_checksum(url):
            if url.endswith(".CHECKSUM"):
                return b"0" * 64 + b"  fake\n"
            return bad.payload

        source = BinanceVisionSource(
            cache_dir=tmp_path, transport=wrong_checksum
        )
        with pytest.raises(HistoricalDataError, match="MISMATCH"):
            source.fetch_month("BTCUSDT", "1m", 2026, 8)

    def test_unreachable_checksum_refused(self, tmp_path):
        payload = _fake_binance_zip("BTCUSDT")
        transport = _FakeTransport(payload)
        transport.fail_urls.add("x.CHECKSUM")
        source = BinanceVisionSource(cache_dir=tmp_path, transport=transport)
        # make every checksum url fail
        original = transport.__call__

        def selective(url):
            if url.endswith(".CHECKSUM"):
                raise OSError("down")
            return original(url)

        source = BinanceVisionSource(cache_dir=tmp_path, transport=selective)
        with pytest.raises(HistoricalDataError, match="checksum download"):
            source.fetch_month("BTCUSDT", "1m", 2026, 8)

    def test_bad_symbol_and_timeframe_refused(self, tmp_path):
        source = BinanceVisionSource(
            cache_dir=tmp_path, transport=_FakeTransport(b"x")
        )
        with pytest.raises(HistoricalDataError):
            source.fetch_month("btc!!", "1m", 2026, 8)
        with pytest.raises(HistoricalDataError):
            source.fetch_month("BTCUSDT", "7m", 2026, 8)


class TestServiceFacade:
    def test_bundled_first_then_website_fallback(self, tmp_path):
        service = HistoricalDataService(
            cache_dir=tmp_path,
            transport=_FakeTransport(_fake_binance_zip("ETHUSDT")),
        )
        # ETHUSDT is bundled -> served from the repo, no network
        result = service.fetch("ETHUSDT", "1m")
        assert result["source_used"] == "bundled-repo"
        assert result["count"] == 43200

    def test_bundled_only_refusal(self, tmp_path):
        service = HistoricalDataService(cache_dir=tmp_path)
        with pytest.raises(HistoricalDataError):
            service.fetch("XAUUSD", "1m", source="bundled")

    def test_months_bounded(self, tmp_path):
        service = HistoricalDataService(cache_dir=tmp_path)
        with pytest.raises(HistoricalDataError):
            service.fetch("BTCUSDT", "1m", months=0)
        with pytest.raises(HistoricalDataError):
            service.fetch("BTCUSDT", "1m", months=4)

    def test_import_into_barstore_validates(self, tmp_path):
        service = HistoricalDataService(cache_dir=tmp_path)
        fetched = service.fetch("BTCUSDT", "1m")
        store = BarStore(tmp_path / "bars")
        result = HistoricalDataService.import_into_barstore(
            store, "BTCUSDT", fetched["bars"][:1000]
        )
        assert result["imported"] == 1000
        assert result["total_in_store"] == 1000
        # garbage bars are refused by the lab's own validator
        with pytest.raises(Exception):
            HistoricalDataService.import_into_barstore(
                store, "BTCUSDT", [{"ts": "bad", "close": -5}]
            )
