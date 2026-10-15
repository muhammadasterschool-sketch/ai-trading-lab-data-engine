"""Master market-data bundle audit + ingestion (2026-10-11 mandate).

Audits the four operator-supplied "Master" CSV datasets BEFORE any of
their content can reach the platform registries, and classifies each
file's epistemic state from EVIDENCE, never from the file's own claims
or the operator's approval to USE the data (approval-to-use is not
source verification — see PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md
§5: source approval is a separate, recorded HUMAN decision on the
SOURCE, which these operator-supplied files do not carry).

The four files and their true shapes (measured, not assumed):

- ``Coins_Master.csv``  — Binance-style concatenated symbols with
  millisecond epoch ``Open_time``/``Close_time`` UTC daily klines;
  ~500 symbols over a ~1000-day window ending 2026-10-11.
- ``Forex_Master.csv``  — ONE exchange rate per currency pair per
  business day (``USD_EUR`` style, USD base). This is a RATE SERIES,
  not OHLC candles. It is audited as such and is NEVER converted into
  fabricated OHLC bars.
- ``Stocks_Master.csv`` — 9 assets sampled at MONTHLY or QUARTERLY
  period-start dates with sparse partial-period tail rows.
- ``Metals_Master.csv`` — 5 metals sampled at MONTHLY period-start
  dates with 19 impossible-OHLC rows and 46..63 missing months per
  asset. Violations are REPORTED VERBATIM with row indices — never
  repaired, guessed, or silently rewritten (the original provider's
  data is required for any correction and is not available).

Fail-closed contracts (mirroring platform/datasets.py):

- ``REAL_VERIFIED`` is unreachable from CSV ingestion by construction
  (nine-stage verification chain + human source approval, §2/§5 of
  the provenance policy).
- HARD fabrication evidence (pre-quote-existence OHLC, pre-listing
  OHLC) ⇒ ``SYNTHETIC``.
- Integrity failures (duplicates, non-chronology, impossible OHLC,
  non-positive prices) ⇒ ``INVALID``.
- Clean-but-unverified ⇒ ``REAL_UNVERIFIED`` with every unverifiable
  provenance field recorded as ``UNKNOWN``/``UNVERIFIED`` — never
  invented.
- Original files are immutable inputs: this module only READS them.

Determinism (INV-01): every identity is a pure function of file
content and caller-supplied constants — no wall-clock anywhere. The
bundle's own declared ``created_utc`` acquisition timestamp (a fixed
constant from MASTER_DATA_MANIFEST.json) is the ONLY time reference
used, and only for latest-candle completeness evidence.
"""

import hashlib
import json
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from data_engine.platform.events import AuditLog
from data_engine.platform.registry import (
    InstrumentRegistry,
    ProviderSymbolMapping,
)
from data_engine.prediction.datasets import DatasetState
from data_engine.schemas import AssetClass, ContractType, Instrument

# ---------------------------------------------------------------------------
# Well-established existence facts (audit evidence only — never secrets).
# Values are conservative (earliest plausible tradable date) so a flag is
# never a false positive; absence of a flag is never proof of reality.
# ---------------------------------------------------------------------------

#: Quote assets a concatenated Binance-style symbol can end with. The
#: suffix parse table is evidence, not a claim that the file came from
#: Binance (the file declares no venue — venue stays UNKNOWN).
COIN_QUOTE_SUFFIXES: tuple[str, ...] = (
    "FDUSD",  # 5 chars — must precede shorter overlapping suffixes
    "USDT",
    "USDC",
    "BUSD",
    "TUSD",
    "TRY",
    "EUR",
    "BTC",
    "ETH",
    "BNB",
    "XRP",
    "ARS",
    "BRL",
    "ZAR",
    "DAI",
)

#: Earliest existence of quote assets (well-established launch dates).
MASTER_QUOTE_ASSET_EXISTENCE: dict[str, date] = {
    "BTC": date(2010, 7, 18),   # earliest exchange-traded BTC (Mt.Gox)
    "ETH": date(2015, 7, 30),   # mainnet launch
    "USDT": date(2014, 10, 6),  # Tether launch
    "USDC": date(2018, 9, 26),  # CENTRE launch
    "FDUSD": date(2023, 6, 26),  # First Digital USD launch
}

#: Well-established earliest tradable dates for base assets that appear
#: in the file (conservative). Unlisted bases stay UNVERIFIED — never
#: guessed either way.
MASTER_BASE_ASSET_EXISTENCE: dict[str, date] = {
    "BTC": date(2010, 7, 18),
    "ETH": date(2015, 7, 30),
    "LTC": date(2011, 10, 13),
    "DOGE": date(2013, 12, 6),
    "SOL": date(2020, 3, 16),
    "XRP": date(2012, 8, 1),
    "ADA": date(2017, 9, 29),
    "BNB": date(2017, 7, 14),
    "TRX": date(2018, 6, 25),
}

#: End-2004 reference rates for the seven USD-base pairs (well-
#: established closes; a match is calibration evidence, NOT proof of
#: reality). Tolerance 5%.
FOREX_REFERENCE_ANCHORS: tuple[tuple[str, str, float, float], ...] = (
    ("USD_EUR", "2004-12-31", 0.7341, 0.05),
    ("USD_GBP", "2004-12-31", 0.5175, 0.05),
    ("USD_JPY", "2004-12-31", 103.79, 0.05),
    ("USD_CHF", "2004-12-31", 1.1405, 0.05),
    ("USD_AUD", "2004-12-31", 1.3054, 0.05),
    ("USD_CAD", "2004-12-31", 1.2046, 0.05),
    ("USD_NZD", "2004-12-31", 1.4112, 0.05),
)

#: Calibration anchors for well-established historical closes inside
#: each file's coverage. A match is CALIBRATION evidence only.
MASTER_CALIBRATION_ANCHORS: dict[str, tuple[tuple[str, str, float, float], ...]] = {
    "coins": (
        ("BTCUSDT", "2024-12-31", 93429.0, 0.03),
        ("ETHBTC", "2024-01-16", 0.0594, 0.10),
    ),
    "stocks": (
        ("SP500", "2024-12-01", 5881.63, 0.05),
        ("Apple", "2024-12-01", 250.42, 0.05),
        ("Nvidia", "2024-12-01", 134.70, 0.08),
    ),
    "metals": (
        ("Gold", "2011-09-01", 1650.75, 0.10),
        ("Silver", "2011-09-01", 30.19, 0.12),
    ),
}

#: Well-established inception/IPO dates for the stocks assets (audit
#: notes: a first row dated AFTER inception is normal; a whole period
#: bar that ENDS before inception would be fabrication evidence).
MASTER_EQUITY_INCEPTION: dict[str, date] = {
    "Apple": date(1980, 12, 12),
    "Microsoft": date(1986, 3, 13),
    "Amazon": date(1997, 5, 15),
    "Google": date(2004, 8, 19),
    "Tesla": date(2010, 6, 29),
    "Nvidia": date(1999, 1, 22),
    "Nasdaq": date(1971, 2, 8),   # composite index launch
    "SP500": date(1957, 3, 4),    # modern index launch
    "DowJones": date(1928, 10, 1),  # modern 30-stock index
}

#: The four master dataset schemas (measured from the supplied files).
MASTER_KIND_COLUMNS: dict[str, tuple[str, ...]] = {
    "coins": ("Symbol", "Open_time", "Open", "High", "Low", "Close",
              "Volume", "Close_time"),
    "forex_rates": ("Currency_Pair", "Date", "Exchange_Rate"),
    "stocks": ("Asset", "Date", "Open", "High", "Low", "Close", "Volume"),
    "metals": ("Asset", "Date", "Open", "High", "Low", "Close", "Volume"),
}

#: One day in milliseconds (daily kline span).
DAY_MS = 86_400_000


class MasterDataKind(str, Enum):
    """The four master dataset kinds (schema-true, not forced to OHLC)."""

    COINS = "coins"
    FOREX_RATES = "forex_rates"
    STOCKS = "stocks"
    METALS = "metals"


# ---------------------------------------------------------------------------
# Shared helpers (deterministic)
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _parse_coin_symbol(symbol: str) -> tuple[str, str]:
    """Split a concatenated symbol into (base, quote) by known suffix.

    Returns quote ``UNKNOWN`` when no known suffix matches — recorded
    as evidence, never guessed beyond the table.
    """
    for quote in COIN_QUOTE_SUFFIXES:
        if symbol.endswith(quote) and len(symbol) > len(quote):
            return symbol[: -len(quote)], quote
    return symbol, "UNKNOWN"


def _frequency_label(median_gap_days: float) -> str:
    """Label an observed median gap (deterministic bucketing)."""
    if median_gap_days <= 3:
        return "DAILY"
    if median_gap_days <= 10:
        return "WEEKLY"
    if median_gap_days <= 45:
        return "MONTHLY"
    if median_gap_days <= 100:
        return "QUARTERLY"
    return "SPARSE"


class AnchorResult(BaseModel):
    """One calibration-anchor comparison (evidence, not proof)."""

    model_config = ConfigDict(frozen=True)

    instrument: str
    date: str
    expected_approx: float
    tolerance: float
    actual: Optional[float] = None
    within_tolerance: Optional[bool] = None
    found: bool = False


# ---------------------------------------------------------------------------
# Coins audit models
# ---------------------------------------------------------------------------

class CoinsSymbolAudit(BaseModel):
    """Per-symbol audit slice for the coins klines file (evidence only)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    base: str
    quote: str
    rows: int
    valid_ohlc_rows: int
    duplicate_rows: int
    non_chronological_rows: int
    ohlc_violation_rows: int
    non_positive_price_rows: int
    nan_ohlc_rows: int
    partial_span_rows: int
    internal_day_gaps: int
    quote_anachronism_rows: int
    pre_listing_rows: int
    first_row_date: Optional[str] = None
    first_valid_ohlc_date: Optional[str] = None
    last_row_date: Optional[str] = None
    last_close_time_date: Optional[str] = None
    first_open: Optional[float] = None
    last_close: Optional[float] = None
    min_low: Optional[float] = None
    max_high: Optional[float] = None
    coverage_years: float = 0.0
    latest_candle_incomplete: bool = False

    @property
    def quote_verified(self) -> bool:
        return self.quote in MASTER_QUOTE_ASSET_EXISTENCE or self.quote in (
            "BTC", "ETH"
        )


class CoinsMasterAudit(BaseModel):
    """Complete audit of the coins klines CSV — reproducible evidence."""

    model_config = ConfigDict(frozen=True)

    file_name: str
    sha256: str
    kind: MasterDataKind
    row_count: int
    columns: tuple[str, ...]
    expected_columns_match: bool
    symbol_count: int
    instruments: tuple[CoinsSymbolAudit, ...]
    duplicate_symbol_time_rows: int
    non_chronological_rows: int
    ohlc_violation_rows: int
    non_positive_price_rows: int
    nan_ohlc_rows: int
    partial_span_rows: int
    internal_day_gaps: int
    quote_anachronism_rows: int
    pre_listing_rows: int
    unparsed_quote_symbols: int
    invalid_timestamp_rows: int
    negative_volume_rows: int
    latest_candle_incomplete_symbols: int
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None
    anchor_results: tuple[AnchorResult, ...] = ()
    anchors_within_tolerance: int = 0
    anchors_checked: int = 0

    @property
    def fabrication_evidence(self) -> tuple[str, ...]:
        evidence: list[str] = []
        if self.quote_anachronism_rows > 0:
            evidence.append(
                f"HARD: {self.quote_anachronism_rows} rows quote a quote-asset "
                f"that did not exist on the row date (well-established launch "
                f"dates: "
                f"{ {q: d.isoformat() for q, d in sorted(MASTER_QUOTE_ASSET_EXISTENCE.items())} })"
            )
        if self.pre_listing_rows > 0:
            evidence.append(
                f"HARD: {self.pre_listing_rows} rows print OHLC before the "
                f"well-established earliest tradable date of their base asset"
            )
        return tuple(evidence)

    @property
    def integrity_findings(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.duplicate_symbol_time_rows:
            out.append(f"duplicate (Symbol,Open_time) rows: "
                       f"{self.duplicate_symbol_time_rows}")
        if self.non_chronological_rows:
            out.append(f"non-chronological rows: {self.non_chronological_rows}")
        if self.ohlc_violation_rows:
            out.append(f"OHLC relationship violations: {self.ohlc_violation_rows}")
        if self.non_positive_price_rows:
            out.append(f"non-positive prices: {self.non_positive_price_rows}")
        if self.nan_ohlc_rows:
            out.append(f"NaN OHLC cells: {self.nan_ohlc_rows}")
        return tuple(out)

    @property
    def recommended_state(self) -> DatasetState:
        if self.fabrication_evidence:
            return DatasetState.SYNTHETIC
        if self.integrity_findings:
            return DatasetState.INVALID
        return DatasetState.REAL_UNVERIFIED

    def summary_notes(self) -> tuple[str, ...]:
        notes: list[str] = [
            f"file={self.file_name} sha256={self.sha256[:16]}… rows={self.row_count} "
            f"symbols={self.symbol_count} coverage={self.coverage_start}.."
            f"{self.coverage_end}",
            f"epistemic classification: {self.recommended_state.value} "
            f"(REAL_VERIFIED is unreachable from CSV ingestion by construction)",
            f"timestamps: millisecond epoch UTC (Open_time/Close_time); "
            f"daily kline span expectation {DAY_MS} ms; "
            f"partial-span rows={self.partial_span_rows}; "
            f"invalid timestamp rows={self.invalid_timestamp_rows}",
        ]
        notes.extend(self.fabrication_evidence)
        if self.integrity_findings:
            notes.extend(f"INTEGRITY: {f}" for f in self.integrity_findings)
        else:
            notes.append(
                "integrity: duplicates=0, chronology OK, OHLC relations OK, "
                "prices positive and finite"
            )
        notes.append(
            f"coverage shape: ~1000-day rolling window ending {self.coverage_end} "
            f"for most symbols; {len([s for s in self.instruments if s.rows < 1000])} "
            f"symbols carry shorter histories (listing mid-window or missing "
            f"candles — never fabricated by this engine); "
            f"{self.internal_day_gaps} internal day gaps across all symbols"
        )
        if self.latest_candle_incomplete_symbols:
            notes.append(
                f"LATEST CANDLE: {self.latest_candle_incomplete_symbols} symbols' "
                f"final candle ({self.coverage_end}) closes AFTER the bundle's "
                f"declared acquisition timestamp — it was still forming when "
                f"acquired and MUST be excluded from completed-candle research "
                f"until re-acquired"
            )
        if self.unparsed_quote_symbols:
            notes.append(
                f"UNPARSED: {self.unparsed_quote_symbols} symbols matched no "
                f"known quote suffix (quote recorded UNKNOWN — never guessed)"
            )
        if self.anchors_checked:
            notes.append(
                f"calibration anchors: {self.anchors_within_tolerance}/"
                f"{self.anchors_checked} within tolerance (calibration to real "
                f"history, NOT proof of reality)"
            )
        return tuple(notes)


# ---------------------------------------------------------------------------
# Coins audit
# ---------------------------------------------------------------------------

def audit_coins_master(
    path: Path,
    acquisition_ts: Optional[datetime] = None,
) -> CoinsMasterAudit:
    """Full deterministic audit of the coins klines CSV (read-only).

    ``acquisition_ts`` is the bundle's DECLARED creation timestamp (a
    fixed constant supplied by the caller — never wall-clock). It is
    used only to judge whether each symbol's final candle could have
    been complete at acquisition time.
    """
    df = pd.read_csv(path)
    df.columns = [str(c) for c in df.columns]
    expected = MASTER_KIND_COLUMNS[MasterDataKind.COINS.value]
    columns_match = tuple(df.columns) == expected

    for col in ("Open_time", "Close_time"):
        df[f"_{col}"] = pd.to_numeric(df[col], errors="coerce")
    invalid_ts = int(df["_Open_time"].isna().sum() + df["_Close_time"].isna().sum())

    df["_ts"] = pd.to_datetime(df["_Open_time"], unit="ms", utc=True,
                               errors="coerce")
    df["_ct"] = pd.to_datetime(df["_Close_time"], unit="ms", utc=True,
                               errors="coerce")
    df["_sym"] = df["Symbol"].astype(str)
    for c in ("Open", "High", "Low", "Close"):
        df[f"_{c}"] = pd.to_numeric(df[c], errors="coerce")
    df["_vol"] = pd.to_numeric(df["Volume"], errors="coerce")
    df["_span"] = (df["_Close_time"] - df["_Open_time"] + 1)

    dup_total = int(df.duplicated(["_sym", "_Open_time"]).sum())

    inst_audits: list[CoinsSymbolAudit] = []
    total_non_chrono = 0
    total_ohlc_viol = 0
    total_nonpos = 0
    total_nan = 0
    total_partial_span = 0
    total_day_gaps = 0
    total_quote_anach = 0
    total_pre_listing = 0
    unparsed_quote = 0
    negative_volume = 0
    incomplete_latest = 0
    coverage_dates: list[pd.Timestamp] = []

    for symbol, g in df.groupby("_sym", sort=True):
        # non-chronology is measured on the FILE's original row order
        # (computing it after sorting would be vacuous — always zero)
        non_chrono = int((g["_Open_time"].diff() < 0).sum())
        g = g.sort_values("_Open_time")
        base, quote = _parse_coin_symbol(symbol)
        if quote == "UNKNOWN":
            unparsed_quote += 1

        dates = g["_ts"]
        coverage_dates.extend(dates.dropna().tolist())

        total_non_chrono += non_chrono
        dup_rows = int(g.duplicated(["_Open_time"]).sum())

        has_ohlc = g[["_Open", "_High", "_Low", "_Close"]].notna().all(axis=1)
        nan_rows = int((~has_ohlc).sum())
        total_nan += nan_rows
        valid = g[has_ohlc]
        ohlc_viol = int(
            (
                (valid["_High"] < valid[["_Open", "_Close"]].max(axis=1))
                | (valid["_Low"] > valid[["_Open", "_Close"]].min(axis=1))
                | (valid["_High"] < valid["_Low"])
            ).sum()
        )
        total_ohlc_viol += ohlc_viol
        nonpos = int((valid[["_Open", "_High", "_Low", "_Close"]] <= 0)
                     .any(axis=1).sum())
        total_nonpos += nonpos
        negative_volume += int((g["_vol"] < 0).sum())

        partial_span = int((g["_span"] != DAY_MS).sum())
        total_partial_span += partial_span

        t = g["_Open_time"].dropna().sort_values()
        day_gaps = int((t.diff().dropna() / DAY_MS != 1.0).sum())
        total_day_gaps += day_gaps

        # quote-asset anachronism (fabrication evidence)
        anach = 0
        quote_exists = MASTER_QUOTE_ASSET_EXISTENCE.get(quote)
        if quote_exists is not None:
            anach = int((g["_ts"].dt.date < quote_exists).sum())
        total_quote_anach += anach

        # pre-listing rows for bases with well-established dates
        pre = 0
        earliest = None
        base_exists = MASTER_BASE_ASSET_EXISTENCE.get(base)
        bounds = [d for d in (base_exists, quote_exists) if d is not None]
        if bounds:
            earliest = max(bounds)
            pre = int((g["_ts"].dt.date < earliest).sum())
        total_pre_listing += pre

        last_ct = g["_ct"].dropna()
        incomplete = bool(
            acquisition_ts is not None
            and len(last_ct)
            and last_ct.iloc[-1].to_pydatetime() > acquisition_ts
        )
        if incomplete:
            incomplete_latest += 1

        first_valid = valid["_ts"] if len(valid) else pd.Series(dtype="datetime64[ns, UTC]")
        span_years = 0.0
        if len(valid) >= 2:
            span = valid["_ts"].iloc[-1] - valid["_ts"].iloc[0]
            span_years = round(span.total_seconds() / (365.25 * 86400), 3)

        inst_audits.append(
            CoinsSymbolAudit(
                symbol=symbol,
                base=base,
                quote=quote,
                rows=len(g),
                valid_ohlc_rows=len(valid),
                duplicate_rows=dup_rows,
                non_chronological_rows=non_chrono,
                ohlc_violation_rows=ohlc_viol,
                non_positive_price_rows=nonpos,
                nan_ohlc_rows=nan_rows,
                partial_span_rows=partial_span,
                internal_day_gaps=day_gaps,
                quote_anachronism_rows=anach,
                pre_listing_rows=pre,
                first_row_date=(
                    dates.dropna().iloc[0].date().isoformat()
                    if dates.notna().any() else None
                ),
                first_valid_ohlc_date=(
                    first_valid.iloc[0].date().isoformat()
                    if len(first_valid) else None
                ),
                last_row_date=(
                    dates.dropna().iloc[-1].date().isoformat()
                    if dates.notna().any() else None
                ),
                last_close_time_date=(
                    last_ct.iloc[-1].date().isoformat() if len(last_ct) else None
                ),
                first_open=float(valid["_Open"].iloc[0]) if len(valid) else None,
                last_close=float(valid["_Close"].iloc[-1]) if len(valid) else None,
                min_low=float(valid["_Low"].min()) if len(valid) else None,
                max_high=float(valid["_High"].max()) if len(valid) else None,
                coverage_years=span_years,
                latest_candle_incomplete=incomplete,
            )
        )

    # calibration anchors
    anchor_results: list[AnchorResult] = []
    for sym, dstr, expected, tol in MASTER_CALIBRATION_ANCHORS["coins"]:
        row = df[(df["_sym"] == sym) & (df["_ts"] == pd.Timestamp(dstr, tz="UTC"))]
        if len(row) and pd.notna(row["_Close"].iloc[0]):
            actual = float(row["_Close"].iloc[0])
            within = abs(actual - expected) / expected <= tol
            anchor_results.append(AnchorResult(
                instrument=sym, date=dstr, expected_approx=expected,
                tolerance=tol, actual=actual, within_tolerance=within, found=True,
            ))
        else:
            anchor_results.append(AnchorResult(
                instrument=sym, date=dstr, expected_approx=expected,
                tolerance=tol, found=False,
            ))

    cov = (
        min(coverage_dates).date().isoformat(),
        max(coverage_dates).date().isoformat(),
    ) if coverage_dates else (None, None)

    return CoinsMasterAudit(
        file_name=path.name,
        sha256=_sha256_file(path),
        kind=MasterDataKind.COINS,
        row_count=len(df),
        columns=tuple(str(c) for c in df.columns),
        expected_columns_match=columns_match,
        symbol_count=len(inst_audits),
        instruments=tuple(inst_audits),
        duplicate_symbol_time_rows=dup_total,
        non_chronological_rows=total_non_chrono,
        ohlc_violation_rows=total_ohlc_viol,
        non_positive_price_rows=total_nonpos,
        nan_ohlc_rows=total_nan,
        partial_span_rows=total_partial_span,
        internal_day_gaps=total_day_gaps,
        quote_anachronism_rows=total_quote_anach,
        pre_listing_rows=total_pre_listing,
        unparsed_quote_symbols=unparsed_quote,
        invalid_timestamp_rows=invalid_ts,
        negative_volume_rows=negative_volume,
        latest_candle_incomplete_symbols=incomplete_latest,
        coverage_start=cov[0],
        coverage_end=cov[1],
        anchor_results=tuple(anchor_results),
        anchors_within_tolerance=sum(1 for a in anchor_results if a.within_tolerance),
        anchors_checked=len(anchor_results),
    )


# ---------------------------------------------------------------------------
# Forex (rate series) audit models
# ---------------------------------------------------------------------------

class ForexPairAudit(BaseModel):
    """Per-pair audit slice for the USD-base rate series."""

    model_config = ConfigDict(frozen=True)

    pair: str
    base: str
    quote: str
    rows: int
    duplicate_rows: int
    non_chronological_rows: int
    non_positive_rate_rows: int
    nan_rate_rows: int
    weekend_rows: int
    non_weekend_gap_rows: int
    median_gap_days: float
    first_row_date: Optional[str] = None
    last_row_date: Optional[str] = None
    first_rate: Optional[float] = None
    last_rate: Optional[float] = None
    min_rate: Optional[float] = None
    max_rate: Optional[float] = None
    coverage_years: float = 0.0


class ForexMasterAudit(BaseModel):
    """Complete audit of the forex rate-series CSV (NOT OHLC — ever)."""

    model_config = ConfigDict(frozen=True)

    file_name: str
    sha256: str
    kind: MasterDataKind
    row_count: int
    columns: tuple[str, ...]
    expected_columns_match: bool
    pairs: tuple[ForexPairAudit, ...]
    pair_count: int
    duplicate_pair_date_rows: int
    non_chronological_rows: int
    non_positive_rate_rows: int
    nan_rate_rows: int
    unparsed_pair_symbols: int
    invalid_date_rows: int
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None
    anchor_results: tuple[AnchorResult, ...] = ()
    anchors_within_tolerance: int = 0
    anchors_checked: int = 0

    @property
    def quote_direction(self) -> str:
        return "USD_BASED (rate = quote currency per 1 USD)"

    @property
    def schema_compatibility(self) -> tuple[str, ...]:
        return (
            "RATE_SERIES: one exchange rate per pair per business day — "
            "this file carries NO open/high/low and is therefore NOT "
            "compatible with the engine's Candle (OHLC) schema",
            "fabricating OHLC from a single daily rate is FORBIDDEN "
            "(this module never performs such a conversion)",
            "engine FX Instrument mapping is compatible via explicit "
            "base/quote decomposition (base=USD, quote=<CCY>); any "
            "EURUSD-style convention requires an explicit inversion "
            "step documented at use-site",
        )

    @property
    def integrity_findings(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.duplicate_pair_date_rows:
            out.append(f"duplicate (pair,date) rows: "
                       f"{self.duplicate_pair_date_rows}")
        if self.non_chronological_rows:
            out.append(f"non-chronological rows: {self.non_chronological_rows}")
        if self.non_positive_rate_rows:
            out.append(f"non-positive rates: {self.non_positive_rate_rows}")
        if self.nan_rate_rows:
            out.append(f"NaN rates: {self.nan_rate_rows}")
        return tuple(out)

    @property
    def recommended_state(self) -> DatasetState:
        if self.integrity_findings:
            return DatasetState.INVALID
        return DatasetState.REAL_UNVERIFIED

    def summary_notes(self) -> tuple[str, ...]:
        notes: list[str] = [
            f"file={self.file_name} sha256={self.sha256[:16]}… rows={self.row_count} "
            f"pairs={self.pair_count} coverage={self.coverage_start}.."
            f"{self.coverage_end}",
            f"epistemic classification: {self.recommended_state.value} "
            f"(REAL_VERIFIED is unreachable from CSV ingestion by construction)",
            f"semantics: {self.quote_direction}; frequency: business-day "
            f"daily (weekend gaps expected); timezone: UNKNOWN — the file "
            f"carries calendar dates with no time-of-day or fix-time "
            f"metadata (recorded UNVERIFIED, never invented)",
            f"source/provider: UNKNOWN (no provider metadata in file or "
            f"bundle — rate-fix convention unverifiable)",
        ]
        notes.extend(self.schema_compatibility)
        if self.integrity_findings:
            notes.extend(f"INTEGRITY: {f}" for f in self.integrity_findings)
        else:
            notes.append("integrity: duplicates=0, chronology OK, rates "
                         "positive and finite")
        if self.anchors_checked:
            notes.append(
                f"calibration anchors: {self.anchors_within_tolerance}/"
                f"{self.anchors_checked} within 5% of well-established "
                f"end-2004 reference rates (calibration, NOT proof of reality)"
            )
        return tuple(notes)


def audit_forex_master(path: Path) -> ForexMasterAudit:
    """Full deterministic audit of the forex rate-series CSV (read-only)."""
    df = pd.read_csv(path)
    df.columns = [str(c) for c in df.columns]
    expected = MASTER_KIND_COLUMNS[MasterDataKind.FOREX_RATES.value]
    columns_match = tuple(df.columns) == expected

    df["_d"] = pd.to_datetime(df["Date"], errors="coerce")
    df["_pair"] = df["Currency_Pair"].astype(str)
    df["_rate"] = pd.to_numeric(df["Exchange_Rate"], errors="coerce")
    invalid_dates = int(df["_d"].isna().sum())

    dup_total = int(df.duplicated(["_pair", "_d"]).sum())

    pair_audits: list[ForexPairAudit] = []
    total_non_chrono = 0
    total_nonpos = 0
    total_nan = 0
    unparsed = 0
    coverage_dates: list[pd.Timestamp] = []

    for pair, g in df.groupby("_pair", sort=True):
        # non-chronology on the FILE's original row order (pre-sort)
        non_chrono = int((g["_d"].diff().dt.total_seconds() < 0).sum())
        g = g.sort_values("_d")
        parts = pair.split("_")
        if len(parts) == 2 and all(p.isalpha() and len(p) == 3 for p in parts):
            base, quote = parts[0], parts[1]
        else:
            base, quote = pair, "UNKNOWN"
            unparsed += 1

        dates = g["_d"]
        coverage_dates.extend(dates.dropna().tolist())
        total_non_chrono += non_chrono
        dup_rows = int(g.duplicated(["_d"]).sum())

        rates = g["_rate"]
        nonpos = int((rates <= 0).sum())
        total_nonpos += nonpos
        nan_rows = int(rates.isna().sum())
        total_nan += nan_rows

        weekend = int(dates.dt.dayofweek.isin([5, 6]).sum())
        gaps = dates.diff().dt.days.dropna()
        # non-weekend gaps = consecutive observations with at least one
        # MISSING business day strictly between them (Friday->Monday
        # spans a weekend and is NOT a missing business day)
        non_weekend_gaps = 0
        if len(gaps):
            d_prev = (
                dates.shift(1).reindex(gaps.index).values
                .astype("datetime64[D]") + np.timedelta64(1, "D")
            )
            d_curr = dates.reindex(gaps.index).values.astype("datetime64[D]")
            busdays = np.busday_count(d_prev, d_curr)
            non_weekend_gaps = int((busdays > 0).sum())
        median_gap = float(gaps.median()) if len(gaps) else 0.0

        span_years = 0.0
        if dates.notna().sum() >= 2:
            span = dates.dropna().iloc[-1] - dates.dropna().iloc[0]
            span_years = round(span.total_seconds() / (365.25 * 86400), 3)

        pair_audits.append(
            ForexPairAudit(
                pair=pair,
                base=base,
                quote=quote,
                rows=len(g),
                duplicate_rows=dup_rows,
                non_chronological_rows=non_chrono,
                non_positive_rate_rows=nonpos,
                nan_rate_rows=nan_rows,
                weekend_rows=weekend,
                non_weekend_gap_rows=non_weekend_gaps,
                median_gap_days=round(median_gap, 2),
                first_row_date=(
                    dates.dropna().iloc[0].date().isoformat()
                    if dates.notna().any() else None
                ),
                last_row_date=(
                    dates.dropna().iloc[-1].date().isoformat()
                    if dates.notna().any() else None
                ),
                first_rate=float(rates.dropna().iloc[0])
                if rates.notna().any() else None,
                last_rate=float(rates.dropna().iloc[-1])
                if rates.notna().any() else None,
                min_rate=float(rates.min()) if rates.notna().any() else None,
                max_rate=float(rates.max()) if rates.notna().any() else None,
                coverage_years=span_years,
            )
        )

    anchor_results: list[AnchorResult] = []
    for pair, dstr, expected_rate, tol in FOREX_REFERENCE_ANCHORS:
        row = df[(df["_pair"] == pair) & (df["_d"] == pd.Timestamp(dstr))]
        if len(row) and pd.notna(row["_rate"].iloc[0]):
            actual = float(row["_rate"].iloc[0])
            within = abs(actual - expected_rate) / expected_rate <= tol
            anchor_results.append(AnchorResult(
                instrument=pair, date=dstr, expected_approx=expected_rate,
                tolerance=tol, actual=actual, within_tolerance=within, found=True,
            ))
        else:
            anchor_results.append(AnchorResult(
                instrument=pair, date=dstr, expected_approx=expected_rate,
                tolerance=tol, found=False,
            ))

    cov = (
        min(coverage_dates).date().isoformat(),
        max(coverage_dates).date().isoformat(),
    ) if coverage_dates else (None, None)

    return ForexMasterAudit(
        file_name=path.name,
        sha256=_sha256_file(path),
        kind=MasterDataKind.FOREX_RATES,
        row_count=len(df),
        columns=tuple(str(c) for c in df.columns),
        expected_columns_match=columns_match,
        pairs=tuple(pair_audits),
        pair_count=len(pair_audits),
        duplicate_pair_date_rows=dup_total,
        non_chronological_rows=total_non_chrono,
        non_positive_rate_rows=total_nonpos,
        nan_rate_rows=total_nan,
        unparsed_pair_symbols=unparsed,
        invalid_date_rows=invalid_dates,
        coverage_start=cov[0],
        coverage_end=cov[1],
        anchor_results=tuple(anchor_results),
        anchors_within_tolerance=sum(1 for a in anchor_results if a.within_tolerance),
        anchors_checked=len(anchor_results),
    )


# ---------------------------------------------------------------------------
# Stocks / Metals (periodic OHLCV) audit models
# ---------------------------------------------------------------------------

class OhlcvViolationRow(BaseModel):
    """One impossible-OHLC row, reported verbatim (never repaired)."""

    model_config = ConfigDict(frozen=True)

    asset: str
    date: str
    row_index: int
    open: float
    high: float
    low: float
    close: float
    reason: str


class OhlcvAssetAudit(BaseModel):
    """Per-asset audit slice for a periodic OHLCV file."""

    model_config = ConfigDict(frozen=True)

    asset: str
    rows: int
    duplicate_rows: int
    non_chronological_rows: int
    ohlc_violation_rows: int
    non_positive_price_rows: int
    nan_price_rows: int
    negative_volume_rows: int
    repeated_consecutive_closes: int
    partial_period_tail: bool
    dominant_frequency: str
    median_gap_days: float
    missing_period_count: int
    first_row_date: Optional[str] = None
    last_row_date: Optional[str] = None
    first_open: Optional[float] = None
    last_close: Optional[float] = None
    min_low: Optional[float] = None
    max_high: Optional[float] = None
    coverage_years: float = 0.0
    inception_note: str = "INCEPTION_UNVERIFIED"

    @property
    def d1_suitable(self) -> bool:
        """Engine strategies consume D1 candles; coarser bars do not fit."""
        return self.dominant_frequency == "DAILY"


class OhlcvMasterAudit(BaseModel):
    """Complete audit of a periodic OHLCV CSV (stocks or metals)."""

    model_config = ConfigDict(frozen=True)

    file_name: str
    sha256: str
    kind: MasterDataKind
    row_count: int
    columns: tuple[str, ...]
    expected_columns_match: bool
    assets: tuple[OhlcvAssetAudit, ...]
    asset_count: int
    duplicate_asset_date_rows: int
    non_chronological_rows: int
    ohlc_violation_rows: int
    ohlc_violation_detail: tuple[OhlcvViolationRow, ...]
    non_positive_price_rows: int
    nan_price_rows: int
    negative_volume_rows: int
    invalid_date_rows: int
    d1_suitable_assets: int
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None
    anchor_results: tuple[AnchorResult, ...] = ()
    anchors_within_tolerance: int = 0
    anchors_checked: int = 0

    @property
    def integrity_findings(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.duplicate_asset_date_rows:
            out.append(f"duplicate (Asset,Date) rows: "
                       f"{self.duplicate_asset_date_rows}")
        if self.non_chronological_rows:
            out.append(f"non-chronological rows: {self.non_chronological_rows}")
        if self.ohlc_violation_rows:
            out.append(f"impossible OHLC rows: {self.ohlc_violation_rows} "
                       f"(reported verbatim with row indices; correction "
                       f"requires the original provider's data — never "
                       f"guessed or rewritten by this engine)")
        if self.non_positive_price_rows:
            out.append(f"non-positive prices: {self.non_positive_price_rows}")
        if self.nan_price_rows:
            out.append(f"NaN prices: {self.nan_price_rows}")
        return tuple(out)

    @property
    def recommended_state(self) -> DatasetState:
        if self.integrity_findings:
            return DatasetState.INVALID
        return DatasetState.REAL_UNVERIFIED

    def summary_notes(self) -> tuple[str, ...]:
        notes: list[str] = [
            f"file={self.file_name} sha256={self.sha256[:16]}… rows={self.row_count} "
            f"assets={self.asset_count} coverage={self.coverage_start}.."
            f"{self.coverage_end}",
            f"epistemic classification: {self.recommended_state.value} "
            f"(REAL_VERIFIED is unreachable from CSV ingestion by construction)",
            f"frequency: PERIODIC (period-start dated bars, NOT daily) — "
            f"{self.d1_suitable_assets}/{self.asset_count} assets are "
            f"D1-suitable; the rest are MONTHLY/QUARTERLY and are NOT "
            f"suitable for the engine's daily-candle strategies without "
            f"explicit resampling governance",
            f"timezone: UNKNOWN (calendar dates, no time-of-day metadata — "
            f"UNVERIFIED, never invented); source/provider: UNKNOWN",
        ]
        if self.integrity_findings:
            notes.extend(f"INTEGRITY: {f}" for f in self.integrity_findings)
        else:
            notes.append("integrity: duplicates=0, chronology OK, OHLC "
                         "relations OK, prices positive")
        for a in self.assets:
            if a.missing_period_count:
                notes.append(
                    f"coverage: {a.asset} has ~{a.missing_period_count} missing "
                    f"periods under its observed {a.dominant_frequency} grid "
                    f"(gaps recorded, never fabricated)"
                )
            if a.partial_period_tail:
                notes.append(
                    f"coverage: {a.asset} final row ({a.last_row_date}) is a "
                    f"partial-period tail row off the "
                    f"{a.dominant_frequency} grid (close repeats the prior "
                    f"period close — carry-forward evidence; exclude from "
                    f"completed-period research)"
                )
        if self.anchors_checked:
            notes.append(
                f"calibration anchors: {self.anchors_within_tolerance}/"
                f"{self.anchors_checked} within tolerance (calibration to "
                f"real history, NOT proof of reality)"
            )
        return tuple(notes)


def audit_ohlcv_master(path: Path, kind: MasterDataKind) -> OhlcvMasterAudit:
    """Full deterministic audit of a periodic OHLCV CSV (read-only)."""
    if kind not in (MasterDataKind.STOCKS, MasterDataKind.METALS):
        raise ValueError(f"audit_ohlcv_master refuses kind {kind!r}")
    df = pd.read_csv(path)
    df.columns = [str(c) for c in df.columns]
    expected = MASTER_KIND_COLUMNS[kind.value]
    columns_match = tuple(df.columns) == expected

    df["_d"] = pd.to_datetime(df["Date"], errors="coerce")
    df["_asset"] = df["Asset"].astype(str)
    for c in ("Open", "High", "Low", "Close"):
        df[f"_{c}"] = pd.to_numeric(df[c], errors="coerce")
    df["_vol"] = pd.to_numeric(df["Volume"], errors="coerce")
    invalid_dates = int(df["_d"].isna().sum())

    dup_total = int(df.duplicated(["_asset", "_d"]).sum())

    asset_audits: list[OhlcvAssetAudit] = []
    violations: list[OhlcvViolationRow] = []
    total_non_chrono = 0
    total_nonpos = 0
    total_nan = 0
    total_negvol = 0
    d1_suitable = 0
    coverage_dates: list[pd.Timestamp] = []

    for asset, g in df.groupby("_asset", sort=True):
        # non-chronology on the FILE's original row order (pre-sort)
        non_chrono = int((g["_d"].diff().dt.total_seconds() < 0).sum())
        g = g.sort_values("_d")
        dates = g["_d"]
        coverage_dates.extend(dates.dropna().tolist())

        total_non_chrono += non_chrono
        dup_rows = int(g.duplicated(["_d"]).sum())

        has_ohlc = g[["_Open", "_High", "_Low", "_Close"]].notna().all(axis=1)
        nan_rows = int((~has_ohlc).sum())
        total_nan += nan_rows
        valid = g[has_ohlc]
        viol_mask = (
            (valid["_High"] < valid[["_Open", "_Close"]].max(axis=1))
            | (valid["_Low"] > valid[["_Open", "_Close"]].min(axis=1))
            | (valid["_High"] < valid["_Low"])
        )
        ohlc_viol = int(viol_mask.sum())
        for idx, (_, r) in enumerate(valid[viol_mask].iterrows()):
            reasons = []
            if r["_High"] < max(r["_Open"], r["_Close"]):
                reasons.append("high < max(open,close)")
            if r["_Low"] > min(r["_Open"], r["_Close"]):
                reasons.append("low > min(open,close)")
            if r["_High"] < r["_Low"]:
                reasons.append("high < low")
            violations.append(OhlcvViolationRow(
                asset=asset,
                date=r["_d"].date().isoformat(),
                row_index=int(r.name),
                open=float(r["_Open"]),
                high=float(r["_High"]),
                low=float(r["_Low"]),
                close=float(r["_Close"]),
                reason="; ".join(reasons),
            ))
        nonpos = int((valid[["_Open", "_High", "_Low", "_Close"]] <= 0)
                     .any(axis=1).sum())
        total_nonpos += nonpos
        total_negvol += int((g["_vol"] < 0).sum())

        closes = valid["_Close"].reset_index(drop=True)
        repeats = int((closes.diff() == 0).sum()) if len(closes) > 1 else 0

        gaps = dates.diff().dt.days.dropna()
        median_gap = float(gaps.median()) if len(gaps) else 0.0
        freq = _frequency_label(median_gap)

        # missing periods under the OBSERVED dominant grid
        missing = 0
        if len(dates) >= 2 and median_gap > 0:
            full_span_days = (dates.dropna().iloc[-1] - dates.dropna().iloc[0]).days
            expected_steps = int(round(full_span_days / median_gap))
            missing = max(0, expected_steps - (len(dates) - 1))
        if freq == "DAILY":
            d1_suitable += 1

        # partial-period tail: last row off the period-start grid or
        # last close repeats the prior close with a short final gap
        partial_tail = False
        if len(valid) >= 2 and freq in ("MONTHLY", "QUARTERLY"):
            last_gap = gaps.iloc[-1] if len(gaps) else 0.0
            same_close = float(valid["_Close"].iloc[-1]) == float(
                valid["_Close"].iloc[-2])
            off_grid = valid["_d"].iloc[-1].day != valid["_d"].iloc[-2].day
            partial_tail = bool(off_grid or (same_close and last_gap < median_gap))

        # inception evidence (stocks only; well-established dates)
        inception_note = "INCEPTION_UNVERIFIED"
        if kind is MasterDataKind.STOCKS:
            known = MASTER_EQUITY_INCEPTION.get(asset)
            if known is not None and len(valid):
                first_bar = valid["_d"].iloc[0]
                # period-start convention: the first bar covers up to
                # roughly its next observed date; a whole bar ending
                # before inception would be fabrication evidence.
                next_ts = valid["_d"].iloc[1] if len(valid) > 1 else (
                    first_bar + pd.Timedelta(days=int(median_gap) or 31)
                )
                if next_ts.date() < known:
                    inception_note = (
                        f"FABRICATION_EVIDENCE: first bar ({first_bar.date()}) "
                        f"ends before established inception {known.isoformat()}"
                    )
                elif first_bar.date() < known:
                    inception_note = (
                        f"OK_WITH_CAVEAT: first period-start "
                        f"{first_bar.date()} precedes inception "
                        f"{known.isoformat()} but the bar covers through "
                        f"{next_ts.date()} (period-start convention)"
                    )
                else:
                    inception_note = (
                        f"OK: first bar {first_bar.date()} on/after "
                        f"established inception {known.isoformat()}"
                    )

        span_years = 0.0
        if len(valid) >= 2:
            span = valid["_d"].iloc[-1] - valid["_d"].iloc[0]
            span_years = round(span.total_seconds() / (365.25 * 86400), 3)

        asset_audits.append(
            OhlcvAssetAudit(
                asset=asset,
                rows=len(g),
                duplicate_rows=dup_rows,
                non_chronological_rows=non_chrono,
                ohlc_violation_rows=ohlc_viol,
                non_positive_price_rows=nonpos,
                nan_price_rows=nan_rows,
                negative_volume_rows=int((g["_vol"] < 0).sum()),
                repeated_consecutive_closes=repeats,
                partial_period_tail=partial_tail,
                dominant_frequency=freq,
                median_gap_days=round(median_gap, 2),
                missing_period_count=missing,
                first_row_date=(
                    dates.dropna().iloc[0].date().isoformat()
                    if dates.notna().any() else None
                ),
                last_row_date=(
                    dates.dropna().iloc[-1].date().isoformat()
                    if dates.notna().any() else None
                ),
                first_open=float(valid["_Open"].iloc[0]) if len(valid) else None,
                last_close=float(valid["_Close"].iloc[-1]) if len(valid) else None,
                min_low=float(valid["_Low"].min()) if len(valid) else None,
                max_high=float(valid["_High"].max()) if len(valid) else None,
                coverage_years=span_years,
                inception_note=inception_note,
            )
        )

    anchor_key = kind.value
    anchor_results: list[AnchorResult] = []
    for asset, dstr, expected, tol in MASTER_CALIBRATION_ANCHORS.get(anchor_key, ()):
        row = df[(df["_asset"] == asset) & (df["_d"] == pd.Timestamp(dstr))]
        if len(row) and pd.notna(row["_Close"].iloc[0]):
            actual = float(row["_Close"].iloc[0])
            within = abs(actual - expected) / expected <= tol
            anchor_results.append(AnchorResult(
                instrument=asset, date=dstr, expected_approx=expected,
                tolerance=tol, actual=actual, within_tolerance=within, found=True,
            ))
        else:
            anchor_results.append(AnchorResult(
                instrument=asset, date=dstr, expected_approx=expected,
                tolerance=tol, found=False,
            ))

    cov = (
        min(coverage_dates).date().isoformat(),
        max(coverage_dates).date().isoformat(),
    ) if coverage_dates else (None, None)

    return OhlcvMasterAudit(
        file_name=path.name,
        sha256=_sha256_file(path),
        kind=kind,
        row_count=len(df),
        columns=tuple(str(c) for c in df.columns),
        expected_columns_match=columns_match,
        assets=tuple(asset_audits),
        asset_count=len(asset_audits),
        duplicate_asset_date_rows=dup_total,
        non_chronological_rows=total_non_chrono,
        ohlc_violation_rows=len(violations),
        ohlc_violation_detail=tuple(violations),
        non_positive_price_rows=total_nonpos,
        nan_price_rows=total_nan,
        negative_volume_rows=total_negvol,
        invalid_date_rows=invalid_dates,
        d1_suitable_assets=d1_suitable,
        coverage_start=cov[0],
        coverage_end=cov[1],
        anchor_results=tuple(anchor_results),
        anchors_within_tolerance=sum(1 for a in anchor_results if a.within_tolerance),
        anchors_checked=len(anchor_results),
    )


# ---------------------------------------------------------------------------
# Provenance + dataset record + ingestion
# ---------------------------------------------------------------------------

class MasterProvenanceRecord(BaseModel):
    """Honest provenance for the operator-supplied master bundle.

    Every unverifiable field is the literal string ``UNKNOWN`` — never
    invented. Operator supply/approval-to-use is explicitly NOT source
    approval (provenance policy §5).
    """

    model_config = ConfigDict(frozen=True)

    bundle_name: str
    acquisition_timestamp: str = "UNKNOWN"
    provider: str = "UNKNOWN"
    provider_download_url: str = "UNKNOWN"
    provider_download_timestamp: str = "UNKNOWN"
    licence: str = "UNKNOWN"
    licence_verified: bool = False
    timezone: str = "UNKNOWN"
    interval: str = "UNKNOWN"
    symbol_mapping: str = (
        "concatenated Binance-style suffix parse (documented table: "
        "COIN_QUOTE_SUFFIXES); USD_XXX pairs decomposed base=USD; "
        "original identifiers preserved as provider symbol mappings"
    )
    approval_records: str = (
        "NONE — user-supplied files carry approval-to-use, which is NOT "
        "a source approval (SRC-APPROVAL record required per provenance "
        "policy §5 before any promotion above REAL_UNVERIFIED)"
    )
    integrity_status: str = "USER_SUPPLIED_NOT_INDEPENDENTLY_SOURCE_VERIFIED"
    bundle_manifest_sha256: str = "UNKNOWN"
    bundle_checksums_verified: bool = False


class MasterDatasetRecord(BaseModel):
    """Immutable import record + manifest identity for one master file."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    file_name: str
    sha256: str
    kind: MasterDataKind
    row_count: int
    instrument_count: int
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None
    data_state: DatasetState
    provenance: MasterProvenanceRecord
    verification_notes: tuple[str, ...] = ()
    registered_instrument_ids: tuple[str, ...] = ()
    audit: Any = Field(exclude=True)

    @property
    def manifest_hash(self) -> str:
        return _canonical_hash(
            {
                "kind": "master_dataset_manifest",
                "file_name": self.file_name,
                "sha256": self.sha256,
                "kind_value": self.kind.value,
                "row_count": self.row_count,
                "instrument_count": self.instrument_count,
                "coverage_start": self.coverage_start,
                "coverage_end": self.coverage_end,
                "data_state": self.data_state.value,
                "audit_digest": self.audit_sha256,
            }
        )

    @property
    def audit_sha256(self) -> str:
        payload = json.loads(self.audit.model_dump_json(
            exclude={"instruments", "pairs", "assets", "anchor_results",
                     "ohlc_violation_detail"}
        ))
        return _canonical_hash(payload)

    def to_manifest_json(self) -> str:
        """Canonical, reproducible manifest (sorted keys, no wall-clock)."""
        return json.dumps(
            {
                "dataset_id": self.dataset_id,
                "manifest_hash": self.manifest_hash,
                "file_name": self.file_name,
                "content_sha256": self.sha256,
                "kind": self.kind.value,
                "row_count": self.row_count,
                "instrument_count": self.instrument_count,
                "coverage_start": self.coverage_start,
                "coverage_end": self.coverage_end,
                "data_state": self.data_state.value,
                "provenance": json.loads(self.provenance.model_dump_json()),
                "verification_notes": list(self.verification_notes),
                "registered_instrument_ids": list(self.registered_instrument_ids),
                "audit": json.loads(self.audit.model_dump_json()),
            },
            sort_keys=True,
            indent=2,
        )


def _instrument_for_master(
    kind: MasterDataKind, identifier: str, base: str, quote: str,
) -> Instrument:
    """Canonical Instrument from master identifiers (venue UNKNOWN)."""
    if kind is MasterDataKind.COINS:
        return Instrument(
            symbol=identifier,
            asset_class=AssetClass.CRYPTO,
            base_asset=base,
            quote_asset=quote,
            venue=None,
            contract_type=ContractType.SPOT,
            currency=quote,
        )
    if kind is MasterDataKind.FOREX_RATES:
        return Instrument(
            symbol=identifier,
            asset_class=AssetClass.FX,
            base_asset=base,
            quote_asset=quote,
            venue=None,
            contract_type=ContractType.SPOT,
            currency=quote,
        )
    if kind is MasterDataKind.METALS:
        return Instrument(
            symbol=identifier,
            asset_class=AssetClass.METAL,
            base_asset=identifier,
            quote_asset="USD",
            venue=None,
            contract_type=ContractType.SPOT,
            currency="USD",
        )
    # stocks: index vs equity by the file's own asset inventory
    is_index = identifier in ("SP500", "Nasdaq", "DowJones")
    return Instrument(
        symbol=identifier,
        asset_class=AssetClass.INDEX if is_index else AssetClass.EQUITY,
        base_asset=identifier,
        quote_asset="USD",
        venue=None,
        contract_type=(
            ContractType.UNKNOWN if is_index else ContractType.SPOT
        ),
        currency="USD",
    )


def ingest_master_dataset(
    path: Path,
    kind: MasterDataKind,
    registry: InstrumentRegistry,
    audit_log: Optional[AuditLog] = None,
    provenance: Optional[MasterProvenanceRecord] = None,
    acquisition_ts: Optional[datetime] = None,
) -> MasterDatasetRecord:
    """Audit → classify → register instruments (fail-closed, evidence-first).

    Mirrors ``ingest_csv_dataset``: the dataset is recorded with its
    evidence-derived state; instruments are registered with ORIGINAL
    identifiers preserved as provider symbol mappings; the data state
    is set exactly as the audit classified it. ``REAL_VERIFIED`` can
    never be produced here by construction.
    """
    if kind is MasterDataKind.COINS:
        audit = audit_coins_master(path, acquisition_ts=acquisition_ts)
        members = audit.instruments
    elif kind is MasterDataKind.FOREX_RATES:
        audit = audit_forex_master(path)
        members = audit.pairs  # type: ignore[assignment]
    elif kind in (MasterDataKind.STOCKS, MasterDataKind.METALS):
        audit = audit_ohlcv_master(path, kind)
        members = audit.assets  # type: ignore[assignment]
    else:  # pragma: no cover — closed enum
        raise ValueError(f"unsupported master kind {kind!r}")

    state = audit.recommended_state

    # logical timestamp derived from file coverage end (never wall-clock)
    logical_day = audit.coverage_end or "1970-01-01"
    logical_ts = datetime(
        *(int(p) for p in logical_day.split("-")), tzinfo=timezone.utc
    )

    prov = provenance or MasterProvenanceRecord(
        bundle_name="UNKNOWN", acquisition_timestamp=logical_day
    )

    registered: list[str] = []
    for m in members:
        identifier = m.symbol if hasattr(m, "symbol") else (
            m.pair if hasattr(m, "pair") else m.asset
        )
        base = getattr(m, "base", identifier)
        quote = getattr(m, "quote", "USD")
        instrument = _instrument_for_master(kind, identifier, base, quote)
        result = registry.register(
            instrument,
            f"csv:master:{kind.value}:{path.name}",
            logical_ts,
            provider_symbols=(
                ProviderSymbolMapping(
                    provider=f"csv:master:{kind.value}",
                    provider_symbol=identifier,
                ),
            ),
        )
        coverage_years = float(getattr(m, "coverage_years", 0.0) or 0.0)
        registry.set_data_state(
            result.record.internal_id,
            state,
            logical_ts,
            coverage_years=coverage_years,
            # REAL_VERIFIED is unreachable: the audit only ever
            # classifies SYNTHETIC / INVALID / REAL_UNVERIFIED.
        )
        registered.append(result.record.internal_id)

    if audit_log is not None:
        audit_log.record(
            logical_ts,
            "registry",
            "master_dataset_ingested",
            f"{path.name}: state={state.value} rows={audit.row_count} "
            f"instruments={len(registered)}",
            path.name,
        )
        for note in audit.summary_notes():
            audit_log.record(
                logical_ts, "registry", "master_dataset_evidence", note, path.name
            )

    record = MasterDatasetRecord(
        dataset_id="DSV-" + _canonical_hash(
            {"file_name": path.name, "sha256": audit.sha256,
             "kind": kind.value, "master": True}
        )[:16],
        file_name=path.name,
        sha256=audit.sha256,
        kind=kind,
        row_count=audit.row_count,
        instrument_count=len(registered),
        coverage_start=audit.coverage_start,
        coverage_end=audit.coverage_end,
        data_state=state,
        provenance=prov,
        verification_notes=audit.summary_notes(),
        registered_instrument_ids=tuple(registered),
        audit=audit,
    )
    return record


__all__ = [
    "COIN_QUOTE_SUFFIXES",
    "MASTER_QUOTE_ASSET_EXISTENCE",
    "MASTER_BASE_ASSET_EXISTENCE",
    "MASTER_EQUITY_INCEPTION",
    "MASTER_KIND_COLUMNS",
    "FOREX_REFERENCE_ANCHORS",
    "MASTER_CALIBRATION_ANCHORS",
    "DAY_MS",
    "MasterDataKind",
    "AnchorResult",
    "CoinsSymbolAudit",
    "CoinsMasterAudit",
    "ForexPairAudit",
    "ForexMasterAudit",
    "OhlcvViolationRow",
    "OhlcvAssetAudit",
    "OhlcvMasterAudit",
    "MasterProvenanceRecord",
    "MasterDatasetRecord",
    "audit_coins_master",
    "audit_forex_master",
    "audit_ohlcv_master",
    "ingest_master_dataset",
]
