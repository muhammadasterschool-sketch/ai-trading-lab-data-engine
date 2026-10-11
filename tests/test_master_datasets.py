"""Master market-data import tests (2026-10-11 mandate).

Deterministic fixture files (tiny, hand-built) exercise every audit
check and classification rule for the four Master dataset schemas:
coins ms-epoch klines, forex rate series, stocks/metals periodic
OHLCV. The REAL four-file audit runs as a repo-level evidence script
(scripts/master_data_ingest.py) plus a committed-manifest integration
test — the 51 MB bundle is an operator input, not a unit fixture.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from data_engine.platform import (
    AuditLog,
    Capability,
    EligibilityStatus,
    InstrumentRegistry,
    MasterDataKind,
    MasterProvenanceRecord,
    audit_coins_master,
    audit_forex_master,
    audit_ohlcv_master,
    ingest_master_dataset,
)
from data_engine.prediction.datasets import DatasetState

ACQ = datetime(2026, 10, 11, 12, 0, 0, tzinfo=timezone.utc)

COINS_HEADER = "Symbol,Open_time,Open,High,Low,Close,Volume,Close_time\n"
FOREX_HEADER = "Currency_Pair,Date,Exchange_Rate\n"
OHLCV_HEADER = "Asset,Date,Open,High,Low,Close,Volume\n"


def _d(ts: str) -> int:
    """ISO date -> ms epoch (UTC) for fixture construction."""
    import pandas as pd

    return int(pd.Timestamp(ts, tz="UTC").value // 1_000_000)


def _coins_row(sym, day, o, h, low, c, vol=100.0, span_ms=86_400_000):
    return (f"{sym},{_d(day)},{o},{h},{low},{c},{vol},"
            f"{_d(day) + span_ms - 1}\n")


def _ohlcv_row(asset, day, o, h, low, c, vol=1000):
    return f"{asset},{day},{o},{h},{low},{c},{vol}\n"


def _fx_row(pair, day, rate):
    return f"{pair},{day},{rate}\n"


def _write(tmp_path: Path, name: str, header: str, rows: list[str]) -> Path:
    p = tmp_path / name
    p.write_text(header + "".join(rows), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Coins: ms timestamps, chronology, OHLC, duplicates, anachronisms,
# listing dates, partial spans, incomplete latest candle
# ---------------------------------------------------------------------------

class TestCoinsAudit:
    def test_clean_fixture_is_real_unverified(self, tmp_path: Path):
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2024-01-16", 42000.0, 43200.0, 41900.0, 43137.95),
            _coins_row("BTCUSDT", "2024-01-17", 43137.95, 44000.0, 43000.0, 43500.0),
            _coins_row("ETHBTC", "2024-01-16", 0.0588, 0.0601, 0.0585, 0.0599),
        ])
        a = audit_coins_master(p, acquisition_ts=ACQ)
        assert a.recommended_state is DatasetState.REAL_UNVERIFIED
        assert a.symbol_count == 2
        assert a.expected_columns_match
        assert a.duplicate_symbol_time_rows == 0
        assert a.ohlc_violation_rows == 0
        assert a.non_positive_price_rows == 0
        assert a.quote_anachronism_rows == 0
        assert a.pre_listing_rows == 0
        assert a.invalid_timestamp_rows == 0
        # both final candles close 2024-01-17 — long before ACQ
        assert a.latest_candle_incomplete_symbols == 0

    def test_ms_epoch_timestamps_parsed_to_utc_dates(self, tmp_path: Path):
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2024-01-16", 1.0, 2.0, 0.5, 1.5),
        ])
        a = audit_coins_master(p)
        sym = a.instruments[0]
        assert sym.first_row_date == "2024-01-16"
        assert sym.last_close_time_date == "2024-01-16"
        assert sym.coverage_years == 0.0  # single row

    def test_invalid_timestamp_counted(self, tmp_path: Path):
        p = tmp_path / "coins.csv"
        p.write_text(
            COINS_HEADER
            + _coins_row("BTCUSDT", "2024-01-16", 1.0, 2.0, 0.5, 1.5)
            + "BTCUSDT,not-a-number,1.0,2.0,0.5,1.5,100.0,1705449599999\n",
            encoding="utf-8",
        )
        a = audit_coins_master(p)
        assert a.invalid_timestamp_rows >= 1

    def test_duplicate_symbol_time_detected(self, tmp_path: Path):
        row = _coins_row("BTCUSDT", "2024-01-16", 1.0, 2.0, 0.5, 1.5)
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [row, row])
        a = audit_coins_master(p)
        assert a.duplicate_symbol_time_rows == 1
        assert a.recommended_state is DatasetState.INVALID

    def test_non_chronological_detected_on_file_order(self, tmp_path: Path):
        # rows written OUT OF ORDER: later candle first
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2024-01-17", 1.0, 2.0, 0.5, 1.5),
            _coins_row("BTCUSDT", "2024-01-16", 1.0, 2.0, 0.5, 1.5),
        ])
        a = audit_coins_master(p)
        assert a.non_chronological_rows == 1
        assert a.recommended_state is DatasetState.INVALID

    def test_ohlc_violation_detected(self, tmp_path: Path):
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2024-01-16", 10.0, 9.5, 8.0, 9.0),
        ])
        a = audit_coins_master(p)
        assert a.ohlc_violation_rows == 1
        assert a.recommended_state is DatasetState.INVALID

    def test_non_positive_price_detected(self, tmp_path: Path):
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2024-01-16", -1.0, 2.0, 0.5, 1.5),
        ])
        a = audit_coins_master(p)
        assert a.non_positive_price_rows == 1
        assert a.recommended_state is DatasetState.INVALID

    def test_usdt_quote_anachronism_marks_synthetic(self, tmp_path: Path):
        # USDT existed from 2014-10-06 — a USDT-quoted candle in 2013
        # is impossible
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2013-01-01", 100.0, 110.0, 90.0, 105.0),
            _coins_row("BTCUSDT", "2013-01-02", 105.0, 115.0, 95.0, 110.0),
        ])
        a = audit_coins_master(p)
        assert a.quote_anachronism_rows == 2
        assert a.recommended_state is DatasetState.SYNTHETIC
        assert any("HARD" in e for e in a.fabrication_evidence)

    def test_pre_listing_base_asset_marks_synthetic(self, tmp_path: Path):
        # SOL mainnet 2020-03-16 — a SOLBTC candle in 2019 is impossible
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("SOLBTC", "2019-01-01", 0.001, 0.0011, 0.0009, 0.001),
            _coins_row("SOLBTC", "2019-01-02", 0.001, 0.0011, 0.0009, 0.001),
        ])
        a = audit_coins_master(p)
        assert a.pre_listing_rows == 2
        assert a.recommended_state is DatasetState.SYNTHETIC

    def test_post_listing_not_flagged(self, tmp_path: Path):
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2024-01-16", 1.0, 2.0, 0.5, 1.5),
            _coins_row("BTCUSDT", "2024-01-17", 1.5, 2.0, 0.5, 1.6),
        ])
        a = audit_coins_master(p)
        assert a.pre_listing_rows == 0
        assert a.quote_anachronism_rows == 0

    def test_partial_span_candle_counted_not_invalidating(self, tmp_path: Path):
        # a 3h-span candle (delisted pair's last partial candle) is
        # evidence, not an integrity failure
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("XLMUSDC", "2024-01-16", 1.0, 2.0, 0.5, 1.5),
            _coins_row("XLMUSDC", "2024-01-17", 1.5, 2.0, 0.5, 1.6,
                       span_ms=10_800_000),
        ])
        a = audit_coins_master(p)
        assert a.partial_span_rows == 1
        assert a.recommended_state is DatasetState.REAL_UNVERIFIED

    def test_internal_day_gap_counted(self, tmp_path: Path):
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2024-01-16", 1.0, 2.0, 0.5, 1.5),
            _coins_row("BTCUSDT", "2024-01-20", 1.5, 2.0, 0.5, 1.6),
        ])
        a = audit_coins_master(p)
        assert a.internal_day_gaps == 1

    def test_incomplete_latest_candle_vs_acquisition(self, tmp_path: Path):
        # final candle closes AFTER the bundle acquisition timestamp
        late_acq = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2026-10-10", 1.0, 2.0, 0.5, 1.5),
            _coins_row("BTCUSDT", "2026-10-11", 1.5, 2.0, 0.5, 1.6),
        ])
        a = audit_coins_master(p, acquisition_ts=late_acq)
        assert a.latest_candle_incomplete_symbols == 1
        assert a.instruments[0].latest_candle_incomplete
        # incomplete candle is a coverage WARNING — not INVALID
        assert a.recommended_state is DatasetState.REAL_UNVERIFIED

    def test_complete_latest_candle_when_acquisition_after_close(
        self, tmp_path: Path
    ):
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2024-01-16", 1.0, 2.0, 0.5, 1.5),
        ])
        a = audit_coins_master(p, acquisition_ts=ACQ)
        assert a.latest_candle_incomplete_symbols == 0

    def test_symbol_decomposition(self, tmp_path: Path):
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCFDUSD", "2024-01-16", 1.0, 2.0, 0.5, 1.5),
            _coins_row("ETHBTC", "2024-01-16", 0.05, 0.06, 0.04, 0.05),
            _coins_row("USDTARS", "2024-01-16", 1000.0, 1100.0, 900.0, 1050.0),
        ])
        a = audit_coins_master(p)
        by_symbol = {s.symbol: s for s in a.instruments}
        assert by_symbol["BTCFDUSD"].base == "BTC"
        assert by_symbol["BTCFDUSD"].quote == "FDUSD"
        assert by_symbol["ETHBTC"].base == "ETH"
        assert by_symbol["USDTARS"].base == "USDT"
        assert by_symbol["USDTARS"].quote == "ARS"
        assert a.unparsed_quote_symbols == 0

    def test_fdusd_anachronism_detected(self, tmp_path: Path):
        # FDUSD launched 2023-06-26 — candles before that are impossible
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCFDUSD", "2023-01-02", 1.0, 2.0, 0.5, 1.5),
            _coins_row("BTCFDUSD", "2023-01-03", 1.0, 2.0, 0.5, 1.5),
        ])
        a = audit_coins_master(p)
        assert a.quote_anachronism_rows == 2

    def test_audit_deterministic_and_pure(self, tmp_path: Path):
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("BTCUSDT", "2024-01-16", 1.0, 2.0, 0.5, 1.5),
            _coins_row("BTCUSDT", "2024-01-17", 1.5, 2.0, 0.5, 1.6),
        ])
        a1 = audit_coins_master(p, acquisition_ts=ACQ)
        a2 = audit_coins_master(p, acquisition_ts=ACQ)
        assert a1.model_dump_json() == a2.model_dump_json()
        assert a1.sha256 == a2.sha256


# ---------------------------------------------------------------------------
# Forex: rate-series semantics (never OHLC)
# ---------------------------------------------------------------------------

class TestForexAudit:
    def test_clean_rate_series_is_real_unverified(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
            _fx_row("USD_EUR", "2024-01-03", 0.915),
            _fx_row("USD_JPY", "2024-01-02", 141.0),
        ])
        a = audit_forex_master(p)
        assert a.recommended_state is DatasetState.REAL_UNVERIFIED
        assert a.pair_count == 2
        assert a.duplicate_pair_date_rows == 0
        assert a.non_positive_rate_rows == 0

    def test_rate_series_is_not_ohlc_schema(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
        ])
        a = audit_forex_master(p)
        assert "OHLC" in a.schema_compatibility[0]
        assert "FORBIDDEN" in a.schema_compatibility[1]
        assert "Open" not in a.columns
        # the audit model itself has no OHLC fields to fill
        assert not hasattr(a.pairs[0], "open")

    def test_quote_direction_recorded_usd_based(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
        ])
        a = audit_forex_master(p)
        assert a.quote_direction.startswith("USD_BASED")
        assert a.pairs[0].base == "USD"
        assert a.pairs[0].quote == "EUR"

    def test_duplicate_pair_date_detected(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
            _fx_row("USD_EUR", "2024-01-02", 0.92),
        ])
        a = audit_forex_master(p)
        assert a.duplicate_pair_date_rows == 1
        assert a.recommended_state is DatasetState.INVALID

    def test_non_positive_rate_detected(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", -0.91),
        ])
        a = audit_forex_master(p)
        assert a.non_positive_rate_rows == 1
        assert a.recommended_state is DatasetState.INVALID

    def test_non_chronological_detected_on_file_order(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-03", 0.91),
            _fx_row("USD_EUR", "2024-01-02", 0.90),
        ])
        a = audit_forex_master(p)
        assert a.non_chronological_rows == 1

    def test_weekend_rows_counted(self, tmp_path: Path):
        # 2024-01-06 is a Saturday
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-05", 0.91),
            _fx_row("USD_EUR", "2024-01-06", 0.915),
        ])
        a = audit_forex_master(p)
        assert a.pairs[0].weekend_rows == 1

    def test_friday_to_monday_is_not_a_missing_business_day(
        self, tmp_path: Path
    ):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-05", 0.91),  # Friday
            _fx_row("USD_EUR", "2024-01-08", 0.915),  # Monday
        ])
        a = audit_forex_master(p)
        assert a.pairs[0].non_weekend_gap_rows == 0

    def test_midweek_hole_is_a_missing_business_day(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),  # Tuesday
            _fx_row("USD_EUR", "2024-01-05", 0.915),  # Friday (Wed+Thu missing)
        ])
        a = audit_forex_master(p)
        assert a.pairs[0].non_weekend_gap_rows == 1

    def test_malformed_pair_recorded_unknown(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("EURUSD", "2024-01-02", 1.10),  # no underscore, 6 chars
        ])
        a = audit_forex_master(p)
        assert a.unparsed_pair_symbols == 1
        assert a.pairs[0].quote == "UNKNOWN"

    def test_reference_anchor_check(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2004-12-31", 0.73416),
        ])
        a = audit_forex_master(p)
        anchor = next(
            x for x in a.anchor_results if x.instrument == "USD_EUR"
        )
        assert anchor.found
        assert anchor.within_tolerance

    def test_audit_deterministic(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
            _fx_row("USD_EUR", "2024-01-03", 0.92),
        ])
        assert (audit_forex_master(p).model_dump_json()
                == audit_forex_master(p).model_dump_json())


# ---------------------------------------------------------------------------
# Stocks / Metals: periodic OHLCV
# ---------------------------------------------------------------------------

class TestOhlcvAudit:
    def test_clean_monthly_fixture_is_real_unverified(self, tmp_path: Path):
        rows = [_ohlcv_row("Gold", f"2024-{m:02d}-01", 2000.0, 2100.0,
                           1950.0, 2050.0) for m in range(1, 13)]
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.METALS)
        assert a.recommended_state is DatasetState.REAL_UNVERIFIED
        assert a.assets[0].dominant_frequency == "MONTHLY"
        assert a.d1_suitable_assets == 0
        assert a.assets[0].d1_suitable is False

    def test_ohlc_violation_detected_with_row_detail(self, tmp_path: Path):
        rows = [
            _ohlcv_row("Gold", "2024-01-01", 2000.0, 2100.0, 1950.0, 2050.0),
            # close above high — impossible
            _ohlcv_row("Gold", "2024-02-01", 2050.0, 2060.0, 2040.0, 2099.0),
        ]
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.METALS)
        assert a.ohlc_violation_rows == 1
        v = a.ohlc_violation_detail[0]
        assert v.asset == "Gold"
        assert v.date == "2024-02-01"
        assert "high < max(open,close)" in v.reason
        assert a.recommended_state is DatasetState.INVALID

    def test_low_above_open_violation(self, tmp_path: Path):
        rows = [
            _ohlcv_row("Copper", "2024-01-01", 3.80, 4.00, 3.95, 3.90),
        ]
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.METALS)
        assert a.ohlc_violation_rows == 1
        assert "low > min(open,close)" in a.ohlc_violation_detail[0].reason

    def test_duplicate_asset_date_detected(self, tmp_path: Path):
        row = _ohlcv_row("Gold", "2024-01-01", 2000.0, 2100.0, 1950.0, 2050.0)
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, [row, row])
        a = audit_ohlcv_master(p, MasterDataKind.METALS)
        assert a.duplicate_asset_date_rows == 1
        assert a.recommended_state is DatasetState.INVALID

    def test_non_chronological_detected_on_file_order(self, tmp_path: Path):
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, [
            _ohlcv_row("Gold", "2024-02-01", 2000.0, 2100.0, 1950.0, 2050.0),
            _ohlcv_row("Gold", "2024-01-01", 1990.0, 2100.0, 1950.0, 2040.0),
        ])
        a = audit_ohlcv_master(p, MasterDataKind.METALS)
        assert a.non_chronological_rows == 1

    def test_quarterly_frequency_detected(self, tmp_path: Path):
        rows = [
            _ohlcv_row("SP500", f"{y}-{m:02d}-01", 4000.0, 4100.0, 3900.0, 4050.0)
            for y in (2022, 2023, 2024) for m in (3, 6, 9, 12)
        ]
        p = _write(tmp_path, "stocks.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.STOCKS)
        assert a.assets[0].dominant_frequency == "QUARTERLY"

    def test_daily_frequency_is_d1_suitable(self, tmp_path: Path):
        import pandas as pd

        days = pd.date_range("2024-01-01", periods=30, freq="D")
        rows = [_ohlcv_row("Gold", d.date().isoformat(), 2000.0, 2100.0,
                           1950.0, 2050.0) for d in days]
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.METALS)
        assert a.assets[0].dominant_frequency == "DAILY"
        assert a.assets[0].d1_suitable is True
        assert a.d1_suitable_assets == 1

    def test_missing_periods_counted(self, tmp_path: Path):
        months = [f"2024-{m:02d}-01" for m in (1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12)]
        rows = [
            _ohlcv_row("Gold", d, 2000.0, 2100.0, 1950.0, 2050.0)
            for d in months
        ]
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.METALS)
        # April is missing from an otherwise monthly grid
        assert a.assets[0].dominant_frequency == "MONTHLY"
        assert a.assets[0].missing_period_count == 1

    def test_repeated_consecutive_closes_counted(self, tmp_path: Path):
        rows = [
            _ohlcv_row("Gold", "2024-01-01", 2000.0, 2100.0, 1950.0, 2050.0),
            _ohlcv_row("Gold", "2024-02-01", 2040.0, 2090.0, 1990.0, 2050.0),
        ]
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.METALS)
        assert a.assets[0].repeated_consecutive_closes == 1

    def test_partial_period_tail_flagged(self, tmp_path: Path):
        rows = [
            _ohlcv_row("Gold", f"2024-{m:02d}-01", 2000.0, 2100.0, 1950.0,
                       2050.0 + m)
            for m in range(1, 13)
        ]
        # mid-month tail row whose close repeats the prior month close
        rows.append(_ohlcv_row("Gold", "2025-01-09", 2060.0, 2070.0, 2050.0,
                               2061.0))
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.METALS)
        assert a.assets[0].partial_period_tail is True

    def test_equity_inception_pre_listing_fabrication(self, tmp_path: Path):
        # Tesla IPO 2010-06-29 — a period bar ending before that is
        # impossible. First bar 2010-01-01, next 2010-04-01 (ends
        # before IPO) => fabrication evidence.
        rows = [
            _ohlcv_row("Tesla", "2010-01-01", 1.0, 2.0, 0.5, 1.5),
            _ohlcv_row("Tesla", "2010-04-01", 1.5, 2.0, 0.5, 1.6),
        ]
        p = _write(tmp_path, "stocks.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.STOCKS)
        assert "FABRICATION_EVIDENCE" in a.assets[0].inception_note

    def test_equity_inception_ok_with_caveat(self, tmp_path: Path):
        # Microsoft IPO 1986-03-13; period-start 1986-03-01 bar covers
        # through 1986-06-01 => OK_WITH_CAVEAT (period convention)
        rows = [
            _ohlcv_row("Microsoft", "1986-03-01", 26.0, 28.0, 25.0, 27.0),
            _ohlcv_row("Microsoft", "1986-06-01", 27.0, 29.0, 26.0, 28.0),
        ]
        p = _write(tmp_path, "stocks.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.STOCKS)
        assert a.assets[0].inception_note.startswith("OK_WITH_CAVEAT")

    def test_index_inception_not_flagged(self, tmp_path: Path):
        rows = [
            _ohlcv_row("SP500", "2020-01-01", 3200.0, 3300.0, 3100.0, 3250.0),
            _ohlcv_row("SP500", "2020-04-01", 3250.0, 3350.0, 3150.0, 3300.0),
        ]
        p = _write(tmp_path, "stocks.csv", OHLCV_HEADER, rows)
        a = audit_ohlcv_master(p, MasterDataKind.STOCKS)
        assert a.assets[0].inception_note.startswith("OK:")

    def test_kind_refused_for_wrong_schema(self, tmp_path: Path):
        p = _write(tmp_path, "x.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
        ])
        with pytest.raises(ValueError):
            audit_ohlcv_master(p, MasterDataKind.COINS)

    def test_audit_deterministic(self, tmp_path: Path):
        rows = [_ohlcv_row("Gold", f"2024-{m:02d}-01", 2000.0, 2100.0,
                           1950.0, 2050.0) for m in range(1, 13)]
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, rows)
        assert (
            audit_ohlcv_master(p, MasterDataKind.METALS).model_dump_json()
            == audit_ohlcv_master(p, MasterDataKind.METALS).model_dump_json()
        )


# ---------------------------------------------------------------------------
# Provenance, ingestion, registry integration, manifests
# ---------------------------------------------------------------------------

class TestProvenanceAndIngestion:
    def test_provenance_records_unknown_honestly(self):
        prov = MasterProvenanceRecord(bundle_name="test-bundle")
        assert prov.provider == "UNKNOWN"
        assert prov.provider_download_url == "UNKNOWN"
        assert prov.licence == "UNKNOWN"
        assert prov.licence_verified is False
        assert "NOT" in prov.approval_records  # not a source approval
        assert prov.integrity_status == (
            "USER_SUPPLIED_NOT_INDEPENDENTLY_SOURCE_VERIFIED"
        )

    def test_ingest_registers_instruments_with_states(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
            _fx_row("USD_EUR", "2024-01-03", 0.92),
        ])
        registry = InstrumentRegistry(audit_log=AuditLog())
        log = AuditLog()
        record = ingest_master_dataset(
            p, MasterDataKind.FOREX_RATES, registry, audit_log=log
        )
        assert record.data_state is DatasetState.REAL_UNVERIFIED
        assert record.instrument_count == 1
        assert len(record.registered_instrument_ids) == 1
        rec = registry.get(record.registered_instrument_ids[0])
        assert rec.instrument.symbol == "USD_EUR"
        assert rec.instrument.base_asset == "USD"
        assert rec.instrument.quote_asset == "EUR"
        assert rec.data_state is DatasetState.REAL_UNVERIFIED
        # provider mapping preserves the ORIGINAL identifier
        assert rec.provider_symbols[0].provider == "csv:master:forex_rates"
        assert rec.provider_symbols[0].provider_symbol == "USD_EUR"
        # REAL_UNVERIFIED keeps backtesting/research ELIGIBLE per
        # registry policy; paper trading stays BLOCKED (REAL_VERIFIED
        # is required there)
        assert rec.eligibility(Capability.BACKTESTING) is (
            EligibilityStatus.ELIGIBLE
        )
        assert rec.eligibility(Capability.PAPER_TRADING) is (
            EligibilityStatus.BLOCKED
        )

    def test_ingest_invalid_dataset_blocks_instruments(self, tmp_path: Path):
        p = _write(tmp_path, "metals.csv", OHLCV_HEADER, [
            _ohlcv_row("Gold", "2024-01-01", 2000.0, 2100.0, 1950.0, 2050.0),
            _ohlcv_row("Gold", "2024-02-01", 2050.0, 2060.0, 2040.0, 2099.0),
        ])
        registry = InstrumentRegistry(audit_log=AuditLog())
        record = ingest_master_dataset(
            p, MasterDataKind.METALS, registry
        )
        assert record.data_state is DatasetState.INVALID
        rec = registry.get(record.registered_instrument_ids[0])
        assert rec.data_state is DatasetState.INVALID

    def test_ingest_coins_instrument_construction(self, tmp_path: Path):
        p = _write(tmp_path, "coins.csv", COINS_HEADER, [
            _coins_row("ETHBTC", "2024-01-16", 0.0588, 0.0601, 0.0585, 0.0599),
            _coins_row("ETHBTC", "2024-01-17", 0.0599, 0.061, 0.058, 0.060),
        ])
        registry = InstrumentRegistry(audit_log=AuditLog())
        record = ingest_master_dataset(
            p, MasterDataKind.COINS, registry,
            acquisition_ts=ACQ,
        )
        rec = registry.get(record.registered_instrument_ids[0])
        assert rec.instrument.asset_class.value == "cryptocurrency"
        assert rec.instrument.base_asset == "ETH"
        assert rec.instrument.quote_asset == "BTC"
        assert rec.instrument.venue is None  # UNKNOWN — never invented

    def test_ingest_emits_audit_events(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
        ])
        log = AuditLog()
        ingest_master_dataset(
            p, MasterDataKind.FOREX_RATES,
            InstrumentRegistry(audit_log=AuditLog()), audit_log=log,
        )
        events = [e.event for e in log.events()]
        assert "master_dataset_ingested" in events
        assert "master_dataset_evidence" in events

    def test_manifest_deterministic_and_reproducible(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
            _fx_row("USD_EUR", "2024-01-03", 0.92),
        ])
        registry = InstrumentRegistry(audit_log=AuditLog())
        r1 = ingest_master_dataset(p, MasterDataKind.FOREX_RATES, registry)
        r2 = ingest_master_dataset(
            p, MasterDataKind.FOREX_RATES, InstrumentRegistry()
        )
        assert r1.manifest_hash == r2.manifest_hash
        assert r1.to_manifest_json() == r2.to_manifest_json()
        # manifest embeds the provenance record
        assert '"provider": "UNKNOWN"' in r1.to_manifest_json()

    def test_real_verified_unreachable_by_construction(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
        ])
        record = ingest_master_dataset(
            p, MasterDataKind.FOREX_RATES, InstrumentRegistry()
        )
        assert record.data_state is not DatasetState.REAL_VERIFIED
        assert "REAL_VERIFIED is unreachable" in record.verification_notes[1]

    def test_dataset_id_is_checksum_derived(self, tmp_path: Path):
        p = _write(tmp_path, "forex.csv", FOREX_HEADER, [
            _fx_row("USD_EUR", "2024-01-02", 0.91),
        ])
        record = ingest_master_dataset(
            p, MasterDataKind.FOREX_RATES, InstrumentRegistry()
        )
        assert record.dataset_id.startswith("DSV-")
        assert len(record.dataset_id) == 20


# ---------------------------------------------------------------------------
# Integration: committed bundle files + committed manifests
# (exercises the REAL operator inputs in CI — files are committed)
# ---------------------------------------------------------------------------

REPO = Path(__file__).resolve().parents[1]
RAW_MASTER = REPO / "data" / "raw" / "master"
MANIFESTS_MASTER = REPO / "data" / "manifests" / "master"

pytestmark_integration = pytest.mark.skipif(
    not (RAW_MASTER / "Coins_Master.csv").exists(),
    reason="master bundle files not present",
)


@pytestmark_integration
class TestCommittedBundleIntegration:
    def test_committed_files_match_declared_checksums(self):
        import hashlib

        declared = {
            "Coins_Master.csv": "7a6b9eae03d7961b5869fddb8f95f660"
                                "cec5a6b91f260eb0aa1f2f96aa8a4fc8",
            "Forex_Master.csv": "f0618be1b1c48c3f7eed22c5582eb868"
                                "2a56134f682546f37419ed3c9140b4fd",
            "Stocks_Master.csv": "294df03dda5b21f05677b0bbf4f5efc7"
                                 "f3ba6d00c37e1c597c22c20a9a41aaae",
            "Metals_Master.csv": "6e921a9a2ecf911ec6a6da657387530b"
                                 "e21f0847049d409af6c27ff76d0d879b",
        }
        for name, expected in declared.items():
            h = hashlib.sha256((RAW_MASTER / name).read_bytes()).hexdigest()
            assert h == expected, f"{name} checksum drifted"

    def test_committed_manifests_match_recomputed_audit(self):
        for kind, audit_fn in (
            ("coins", None),
            ("forex_rates", None),
            ("stocks", None),
            ("metals", None),
        ):
            manifest_path = MANIFESTS_MASTER / f"{kind}_master_manifest.json"
            if not manifest_path.exists():
                pytest.skip("manifests not generated yet")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            # recompute audit and compare the content hash + key totals
            if kind == "coins":
                audit = audit_coins_master(
                    RAW_MASTER / "Coins_Master.csv",
                    acquisition_ts=datetime.fromisoformat(
                        "2026-10-11T12:53:19.264928+00:00"
                    ),
                )
            elif kind == "forex_rates":
                audit = audit_forex_master(RAW_MASTER / "Forex_Master.csv")
            elif kind == "stocks":
                audit = audit_ohlcv_master(
                    RAW_MASTER / "Stocks_Master.csv", MasterDataKind.STOCKS
                )
            else:
                audit = audit_ohlcv_master(
                    RAW_MASTER / "Metals_Master.csv", MasterDataKind.METALS
                )
            assert manifest["content_sha256"] == audit.sha256
            assert manifest["row_count"] == audit.row_count
            assert manifest["data_state"] == audit.recommended_state.value
            assert manifest["coverage_start"] == audit.coverage_start
            assert manifest["coverage_end"] == audit.coverage_end

    def test_committed_summary_totals_honest(self):
        summary_path = MANIFESTS_MASTER / "master_import_summary.json"
        if not summary_path.exists():
            pytest.skip("summary not generated yet")
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        assert summary["totals"]["real_verified"] == 0
        assert summary["totals"]["invalid"] == 1
        assert summary["totals"]["real_unverified"] == 3
        assert summary["totals"]["rows"] == (
            499310 + 39025 + 2241 + 1378
        )
