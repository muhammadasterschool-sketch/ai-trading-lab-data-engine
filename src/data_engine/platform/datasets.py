"""Historical CSV dataset audit + ingestion (platform mandate Phase C).

Audits the four supplied market-data CSV files (crypto / forex / metals /
stocks+indices daily, 2006-2026) BEFORE any of their content can reach
the platform registries, and classifies each file's epistemic state from
EVIDENCE, never from the file's own claims.

Fail-closed contracts:
- The presence of a dataset proves nothing about its reality. A file is
  promoted to ``REAL_VERIFIED`` by NOTHING in this module — that state
  requires the repository's nine-stage verification chain plus explicit
  human approval (see runtime/data_gate.py), which CSV files cannot
  satisfy by construction.
- HARD fabrication evidence (any one is sufficient to classify a file
  SYNTHETIC):
    (a) OHLC prices printed before an instrument's well-established
        listing/existence date (e.g. equity candles before its IPO);
    (b) venue/exchange attribution to an entity that did not exist on
        the row's date (e.g. "Binance" on 2006-2010 rows);
    (c) OHLC printed on rows the file itself marks as market-closed
        holidays;
    (d) a perfectly uniform, identical-row-count weekday grid across
        every instrument in the file — including instruments that
        provably started trading mid-range — a generation signature no
        real multi-instrument history exhibits.
- Integrity problems (duplicates, non-chronology, OHLC violations,
  non-positive prices, missing OHLC on active rows) are counted
  independently of the epistemic classification and reported verbatim.
- Original files are immutable inputs: the module only READS them and
  records their SHA-256; instruments are registered with their ORIGINAL
  identifiers preserved as provider symbol mappings.

The audit is deterministic (INV-01): every identity is a pure function
of file content and declared constants — no wall-clock anywhere.
"""

import hashlib
import json
from datetime import date, datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

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
# Sources: exchange IPO records / genesis blocks / launch announcements;
# values chosen conservatively (earliest plausible tradable date).
# ---------------------------------------------------------------------------

KNOWN_LISTING_DATES: dict[str, date] = {
    # equities (IPO day)
    "TSLA": date(2010, 6, 29),
    # crypto: earliest exchange-traded / mainnet-live dates
    "BTC/USDT": date(2010, 7, 18),  # Mt.Gox launch (genesis 2009-01-03)
    "ETH/USDT": date(2015, 7, 30),  # mainnet launch
    "LTC/USDT": date(2011, 10, 13),  # launch
    "SOL/USDT": date(2020, 3, 16),  # mainnet beta
}

#: Earliest existence date of entities referenced in Exchange columns.
KNOWN_VENUE_EXISTENCE: dict[str, date] = {
    "binance": date(2017, 7, 14),
    "usdt": date(2014, 10, 6),
    "coinbase": date(2012, 10, 1),
    "bitstamp": date(2011, 8, 18),
    "kraken": date(2011, 7, 1),
}

#: 2006 start anchors: (instrument, date, real close, tolerance fraction).
#: Well-established historical closes; used to test whether a series is
#: anchored to real history (calibration) — matching them does NOT make
#: a file real, it makes it CALIBRATED.
HISTORY_ANCHORS: tuple[tuple[str, str, float, float], ...] = (
    ("EURUSD", "2006-01-02", 1.1841, 0.02),
    ("GBPUSD", "2006-01-02", 1.7400, 0.02),
    ("USDJPY", "2006-01-02", 119.00, 0.02),
    ("USDCHF", "2006-01-02", 1.3100, 0.05),
    ("AUDUSD", "2006-01-02", 0.7520, 0.02),
    ("USDCAD", "2006-01-02", 1.1640, 0.02),
    ("XAUUSD", "2006-01-02", 525.00, 0.02),
    ("XAGUSD", "2006-01-02", 9.00, 0.03),
    ("XPTUSD", "2006-01-02", 1000.00, 0.05),
    ("XPDUSD", "2006-01-02", 260.00, 0.05),
    ("US500", "2006-01-02", 1242.00, 0.02),
    ("US30", "2006-01-02", 10847.00, 0.04),
    ("US100", "2006-01-03", 1690.00, 0.04),
    ("AAPL", "2006-01-03", 2.60, 0.06),  # split-adjusted (7:1 2014, 4:1 2020)
    ("MSFT", "2006-01-03", 26.80, 0.04),
)

#: Plausibility bands for the final close of each series, derived from
#: the last WELL-ESTABLISHED levels (2024) and any remotely comparable
#: historical structural break. Falling outside the band is recorded as
#: an implausibility ANOMALY (evidence, not proof).
ENDPOINT_PLAUSIBILITY_BANDS: tuple[tuple[str, float, float], ...] = (
    ("USDCHF", 0.55, 2.00),
    ("USDJPY", 60.0, 250.0),
    ("XAGUSD", 5.0, 200.0),
    ("XAUUSD", 300.0, 5000.0),
    ("US500", 2000.0, 20000.0),
    ("US100", 3000.0, 40000.0),
    ("US30", 15000.0, 100000.0),
    ("EURUSD", 0.80, 1.80),
    ("GBPUSD", 1.00, 2.30),
)


class CsvKind(str, Enum):
    """The four supplied dataset schemas."""

    CRYPTO = "crypto"
    FOREX = "forex"
    METALS = "metals"
    STOCKS_INDICES = "stocks_indices"


_KIND_COLUMNS: dict[CsvKind, tuple[str, ...]] = {
    CsvKind.CRYPTO: (
        "Date", "Symbol", "Exchange", "Open", "High", "Low", "Close",
        "Volume_Base", "Volume_Quote_USD", "Trading_Session",
        "Funding_Rate_8h_%", "Status",
    ),
    CsvKind.FOREX: (
        "Date", "Symbol", "Open", "High", "Low", "Close", "Volume_Ticks",
        "Spread_Pips", "Pip_Value_USD_StdLot", "Max_Leverage",
        "Swap_Long_Points", "Swap_Short_Points", "Session_Calendar",
    ),
    CsvKind.METALS: (
        "Date", "Symbol_Standard", "Broker_Symbol_Name", "Open", "High",
        "Low", "Close", "Volume", "Contract_Size", "Tick_Size",
        "Tick_Value_USD", "Price_Precision", "Initial_Margin_USD",
        "Maintenance_Margin_USD",
    ),
    CsvKind.STOCKS_INDICES: (
        "Date", "Symbol", "Asset_Class", "Open", "High", "Low", "Close",
        "Volume", "Trading_Session", "Market_Status", "Corporate_Action",
        "Contract_Size", "Financing_Rate_Long_%",
    ),
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class InstrumentAudit(BaseModel):
    """Per-instrument audit slice (all fields evidence, no opinions)."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    original_identifier: str
    rows: int
    valid_ohlc_rows: int
    explicit_pre_launch_rows: int
    first_row_date: Optional[str] = None
    first_valid_ohlc_date: Optional[str] = None
    last_row_date: Optional[str] = None
    first_open: Optional[float] = None
    last_close: Optional[float] = None
    min_low: Optional[float] = None
    max_high: Optional[float] = None
    pre_listing_ohlc_rows: int = 0
    duplicate_rows: int = 0
    non_chronological_rows: int = 0
    ohlc_violation_rows: int = 0
    non_positive_price_rows: int = 0
    missing_ohlc_on_active_rows: int = 0
    weekday_histogram: tuple[tuple[int, int], ...] = ()
    unique_row_counts_note: str = ""

    @property
    def has_pre_listing_ohlc(self) -> bool:
        return self.pre_listing_ohlc_rows > 0


class AnchorResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    instrument: str
    date: str
    expected_approx: float
    tolerance: float
    actual: Optional[float] = None
    within_tolerance: Optional[bool] = None
    found: bool = False


class CsvDatasetAudit(BaseModel):
    """Complete audit of one CSV file — reproducible evidence record."""

    model_config = ConfigDict(frozen=True)

    file_name: str
    sha256: str
    kind: CsvKind
    row_count: int
    columns: tuple[str, ...]
    expected_columns_match: bool
    instruments: tuple[InstrumentAudit, ...]
    duplicate_symbol_date_rows: int
    non_chronological_rows: int
    ohlc_violation_rows: int
    non_positive_price_rows: int
    holiday_rows_with_ohlc: int
    venue_anachronism_rows: int
    uniform_generation_grid: bool
    anchor_results: tuple[AnchorResult, ...] = ()
    anchors_within_tolerance: int = 0
    anchors_checked: int = 0
    endpoint_anomalies: tuple[str, ...] = ()
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None

    # -- evidence-derived classification ---------------------------------
    @property
    def fabrication_evidence(self) -> tuple[str, ...]:
        evidence: list[str] = []
        for inst in self.instruments:
            if inst.pre_listing_ohlc_rows > 0:
                known = KNOWN_LISTING_DATES.get(inst.symbol)
                evidence.append(
                    f"HARD: {inst.symbol} prints OHLC on {inst.pre_listing_ohlc_rows} "
                    f"rows before its established listing date "
                    f"{known.isoformat() if known else 'N/A'} (first OHLC "
                    f"{inst.first_valid_ohlc_date})"
                )
        if self.venue_anachronism_rows > 0:
            evidence.append(
                f"HARD: {self.venue_anachronism_rows} rows attribute trading to a "
                f"venue/quote-asset that did not exist on the row date "
                f"(earliest venue existence {min(v.isoformat() for v in KNOWN_VENUE_EXISTENCE.values())})"
            )
        if self.holiday_rows_with_ohlc > 0:
            evidence.append(
                f"HARD: {self.holiday_rows_with_ohlc} rows carry OHLC on dates the "
                f"file itself marks Closed_Holiday — real closed markets print no candle"
            )
        if self.uniform_generation_grid:
            evidence.append(
                "HARD: every instrument spans the identical weekday grid with "
                "identical row counts — including instruments that provably began "
                "trading mid-range — a construction signature, not a real "
                "multi-instrument history"
            )
        return tuple(evidence)

    @property
    def integrity_findings(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.duplicate_symbol_date_rows:
            out.append(f"duplicate (symbol,date) rows: {self.duplicate_symbol_date_rows}")
        if self.non_chronological_rows:
            out.append(f"non-chronological rows: {self.non_chronological_rows}")
        if self.ohlc_violation_rows:
            out.append(f"OHLC relationship violations: {self.ohlc_violation_rows}")
        if self.non_positive_price_rows:
            out.append(f"non-positive prices: {self.non_positive_price_rows}")
        return tuple(out)

    @property
    def recommended_state(self) -> DatasetState:
        """Evidence-derived epistemic state (never REAL_VERIFIED here)."""
        if self.fabrication_evidence:
            return DatasetState.SYNTHETIC
        if self.integrity_findings:
            return DatasetState.INVALID
        return DatasetState.REAL_UNVERIFIED

    def summary_notes(self) -> tuple[str, ...]:
        notes: list[str] = [
            f"file={self.file_name} sha256={self.sha256[:16]}… rows={self.row_count} "
            f"instruments={len(self.instruments)} coverage={self.coverage_start}..{self.coverage_end}",
            f"epistemic classification: {self.recommended_state.value} "
            f"(REAL_VERIFIED is unreachable from CSV ingestion by construction — "
            f"requires the nine-stage verification chain plus human approval)",
        ]
        notes.extend(self.fabrication_evidence)
        notes.extend(self.endpoint_anomalies)
        if self.integrity_findings:
            notes.extend(f"INTEGRITY: {f}" for f in self.integrity_findings)
        else:
            notes.append("integrity: duplicates=0, chronology OK, OHLC relations OK, prices positive")
        if self.anchors_checked:
            notes.append(
                f"2006 calibration anchors: {self.anchors_within_tolerance}/{self.anchors_checked} "
                f"within tolerance (calibration to real history, NOT proof of reality)"
            )
        for inst in self.instruments:
            if inst.explicit_pre_launch_rows:
                known = KNOWN_LISTING_DATES.get(inst.symbol)
                if known is None or (
                    inst.first_valid_ohlc_date and inst.first_valid_ohlc_date > known.isoformat()
                ):
                    notes.append(
                        f"coverage: {inst.symbol} active series starts "
                        f"{inst.first_valid_ohlc_date} (later than established listing "
                        f"{known.isoformat() if known else '?'} — early history missing, "
                        f"never fabricated by this engine)"
                    )
        return tuple(notes)


class PlatformDatasetRecord(BaseModel):
    """Immutable import record + manifest identity for one CSV dataset."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    file_name: str
    sha256: str
    kind: CsvKind
    row_count: int
    instrument_count: int
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None
    data_state: DatasetState
    verification_notes: tuple[str, ...] = ()
    registered_instrument_ids: tuple[str, ...] = ()
    audit: CsvDatasetAudit

    @property
    def manifest_hash(self) -> str:
        return _canonical_hash(
            {
                "kind": "platform_dataset_manifest",
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
        return _canonical_hash(
            json.loads(self.audit.model_dump_json(exclude={"instruments", "anchor_results"}))
        )

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
                "verification_notes": list(self.verification_notes),
                "registered_instrument_ids": list(self.registered_instrument_ids),
                "audit": json.loads(self.audit.model_dump_json()),
            },
            sort_keys=True,
            indent=2,
        )


def _asset_class_for(kind: CsvKind, symbol: str, asset_class_column: Optional[str]) -> AssetClass:
    if kind is CsvKind.CRYPTO:
        return AssetClass.CRYPTO
    if kind is CsvKind.FOREX:
        return AssetClass.FX
    if kind is CsvKind.METALS:
        return AssetClass.METAL
    # stocks_indices: honour the file's own Asset_Class declaration
    if asset_class_column and "index" in asset_class_column.lower():
        return AssetClass.INDEX
    return AssetClass.EQUITY


def _split_forex_symbol(symbol: str) -> tuple[str, str]:
    if len(symbol) == 6 and symbol.isalpha():
        return symbol[:3], symbol[3:]
    return symbol, "USD"


def _instrument_for(kind: CsvKind, symbol: str, asset_class_column: Optional[str], venue: Optional[str]) -> Instrument:
    ac = _asset_class_for(kind, symbol, asset_class_column)
    if kind is CsvKind.FOREX:
        base, quote = _split_forex_symbol(symbol)
    elif kind is CsvKind.METALS:
        base, quote = (symbol[:3], symbol[3:]) if len(symbol) == 6 else (symbol, "USD")
    elif kind is CsvKind.CRYPTO and "/" in symbol:
        base, quote = symbol.split("/", 1)
    else:
        base, quote = symbol, "USD"
    contract = ContractType.CFD if kind is CsvKind.STOCKS_INDICES else ContractType.SPOT
    return Instrument(
        symbol=symbol,
        asset_class=ac,
        base_asset=base,
        quote_asset=quote,
        venue=venue,
        contract_type=contract,
        currency="USD",
    )


# ---------------------------------------------------------------------------
# The audit itself
# ---------------------------------------------------------------------------

def audit_csv_file(path: Path, kind: CsvKind) -> CsvDatasetAudit:
    """Full deterministic audit of one CSV file (read-only; no registry)."""
    df = pd.read_csv(path)
    df.columns = [str(c) for c in df.columns]
    expected = _KIND_COLUMNS[kind]
    columns_match = tuple(df.columns) == expected

    sym_col = "Symbol_Standard" if "Symbol_Standard" in df.columns else "Symbol"
    date_col = "Date"
    df["_date"] = pd.to_datetime(df[date_col], errors="coerce")
    df["_sym"] = df[sym_col].astype(str)
    ohlc = ["Open", "High", "Low", "Close"]
    for c in ohlc:
        df[f"_{c}"] = pd.to_numeric(df[c], errors="coerce")

    duplicate_symbol_date = int(df.duplicated([sym_col, date_col]).sum())

    inst_audits: list[InstrumentAudit] = []
    total_non_chrono = 0
    total_ohlc_viol = 0
    total_nonpos = 0
    total_missing_active = 0
    holiday_ohlc_rows = 0
    venue_anachronism_rows = 0
    coverage_dates: list[pd.Timestamp] = []
    row_counts: dict[str, int] = {}

    exchange_col = "Exchange" if "Exchange" in df.columns else None
    status_col = "Status" if "Status" in df.columns else None
    market_status_col = "Market_Status" if "Market_Status" in df.columns else None
    volume_col = next(
        (c for c in ("Volume_Base", "Volume", "Volume_Ticks") if c in df.columns), None
    )

    for symbol, g in df.groupby("_sym", sort=True):
        g = g.sort_values("_date")
        row_counts[symbol] = len(g)
        dates = g["_date"]
        coverage_dates.extend(dates.dropna().tolist())

        non_chrono = int((dates.diff().dt.total_seconds() < 0).sum())
        total_non_chrono += non_chrono

        has_ohlc = g[["_Open", "_High", "_Low", "_Close"]].notna().all(axis=1)
        valid = g[has_ohlc]
        ohlc_viol = int(
            (
                (valid["_High"] < valid[["_Open", "_Close"]].max(axis=1))
                | (valid["_Low"] > valid[["_Open", "_Close"]].min(axis=1))
            ).sum()
        )
        total_ohlc_viol += ohlc_viol
        nonpos = int((valid[["_Open", "_High", "_Low", "_Close"]] <= 0).any(axis=1).sum())
        total_nonpos += nonpos

        pre_listing = 0
        listing = KNOWN_LISTING_DATES.get(symbol)
        if listing is not None and len(valid):
            pre_listing = int((valid["_date"].dt.date < listing).sum())

        explicit_pre = 0
        if status_col:
            explicit_pre = int((g[status_col] == "Pre_Launch_Unlisted").sum())

        missing_active = 0
        if status_col:
            active = g[g[status_col] == "Active_Trading"]
            missing_active = int((~active[["_Open", "_Close"]].notna().all(axis=1)).sum())
        elif market_status_col:
            open_rows = g[g[market_status_col] == "Open_Regular"]
            missing_active = int((~open_rows[["_Open", "_Close"]].notna().all(axis=1)).sum())
        total_missing_active += missing_active

        # holiday rows carrying OHLC (fabrication evidence (c))
        if market_status_col is not None:
            closed = g[g[market_status_col] == "Closed_Holiday"]
            holiday_ohlc_rows += int(
                closed[["_Open", "_High", "_Low", "_Close"]].notna().all(axis=1).sum()
            )

        # venue anachronisms (fabrication evidence (b))
        if exchange_col is not None:
            ex = g[exchange_col].astype(str)
            for entity, exists_from in KNOWN_VENUE_EXISTENCE.items():
                mask = (
                    ex.str.lower().str.contains(entity, regex=False)
                    & (dates.dt.date < exists_from)
                )
                venue_anachronism_rows += int(mask.sum())
            # quote-asset anachronism: /USDT quoted before USDT existed
            if "/" in symbol and symbol.upper().endswith("/USDT"):
                usdt_from = KNOWN_VENUE_EXISTENCE["usdt"]
                venue_anachronism_rows += int(
                    (has_ohlc & (dates.dt.date < usdt_from)).sum()
                )

        weekday_hist = tuple(
            (int(k), int(v))
            for k, v in sorted(dates.dt.dayofweek.value_counts().items())
        )

        inst_audits.append(
            InstrumentAudit(
                symbol=symbol,
                original_identifier=str(symbol),
                rows=len(g),
                valid_ohlc_rows=len(valid),
                explicit_pre_launch_rows=explicit_pre,
                first_row_date=(
                    dates.dropna().iloc[0].date().isoformat() if dates.notna().any() else None
                ),
                first_valid_ohlc_date=(
                    valid["_date"].iloc[0].date().isoformat() if len(valid) else None
                ),
                last_row_date=(
                    dates.dropna().iloc[-1].date().isoformat() if dates.notna().any() else None
                ),
                first_open=float(valid["_Open"].iloc[0]) if len(valid) else None,
                last_close=float(valid["_Close"].iloc[-1]) if len(valid) else None,
                min_low=float(valid["_Low"].min()) if len(valid) else None,
                max_high=float(valid["_High"].max()) if len(valid) else None,
                pre_listing_ohlc_rows=pre_listing,
                duplicate_rows=duplicate_symbol_date,  # file-level count reflected per slice
                non_chronological_rows=non_chrono,
                ohlc_violation_rows=ohlc_viol,
                non_positive_price_rows=nonpos,
                missing_ohlc_on_active_rows=missing_active,
                weekday_histogram=weekday_hist,
            )
        )

    # uniform generation grid signature (fabrication evidence (d)):
    # identical row counts across ALL instruments + zero non-weekend gaps
    # on the shared calendar grid.
    uniform_grid = False
    if len(row_counts) >= 2:
        uniform_rows = len(set(row_counts.values())) == 1
        unique_dates = pd.Series(sorted(df["_date"].dropna().unique()))
        gaps = unique_dates.diff().dt.days.dropna()
        gap_values = set(gaps.unique())
        weekday_only = gap_values <= {1.0, 3.0} or gap_values <= {1.0, 2.0, 3.0, 4.0}
        uniform_grid = bool(uniform_rows and weekday_only and (gaps == 3).sum() > 0)

    # anchors
    anchor_results: list[AnchorResult] = []
    for sym, dstr, expected, tol in HISTORY_ANCHORS:
        applicable = any(i.symbol == sym for i in inst_audits)
        if not applicable:
            continue
        row = df[(df["_sym"] == sym) & (df["_date"] == pd.Timestamp(dstr))]
        if len(row) and pd.notna(row["_Close"].iloc[0]):
            actual = float(row["_Close"].iloc[0])
            within = abs(actual - expected) / expected <= tol
            anchor_results.append(
                AnchorResult(
                    instrument=sym, date=dstr, expected_approx=expected,
                    tolerance=tol, actual=actual, within_tolerance=within, found=True,
                )
            )
        else:
            anchor_results.append(
                AnchorResult(
                    instrument=sym, date=dstr, expected_approx=expected,
                    tolerance=tol, found=False,
                )
            )

    # endpoint plausibility anomalies (recorded as notes, not proof)
    endpoint_anomalies: list[str] = []
    for inst in inst_audits:
        for sym, lo, hi in ENDPOINT_PLAUSIBILITY_BANDS:
            if inst.symbol == sym and inst.last_close is not None:
                if not (lo <= inst.last_close <= hi):
                    endpoint_anomalies.append(
                        f"ANOMALY: {sym} final close {inst.last_close} outside any "
                        f"plausibility band [{lo}, {hi}] derived from established "
                        f"historical levels — consistent with unbounded synthetic drift"
                    )

    cov = (
        min(coverage_dates).date().isoformat(),
        max(coverage_dates).date().isoformat(),
    ) if coverage_dates else (None, None)

    return CsvDatasetAudit(
        file_name=path.name,
        sha256=_sha256_file(path),
        kind=kind,
        row_count=len(df),
        columns=tuple(str(c) for c in df.columns),
        expected_columns_match=columns_match,
        instruments=tuple(inst_audits),
        duplicate_symbol_date_rows=duplicate_symbol_date,
        non_chronological_rows=total_non_chrono,
        ohlc_violation_rows=total_ohlc_viol,
        non_positive_price_rows=total_nonpos,
        holiday_rows_with_ohlc=holiday_ohlc_rows,
        venue_anachronism_rows=venue_anachronism_rows,
        uniform_generation_grid=uniform_grid,
        anchor_results=tuple(anchor_results),
        anchors_within_tolerance=sum(
            1 for a in anchor_results if a.within_tolerance
        ),
        anchors_checked=len(anchor_results),
        endpoint_anomalies=tuple(endpoint_anomalies),
        coverage_start=cov[0],
        coverage_end=cov[1],
    )


def ingest_csv_dataset(
    path: Path,
    kind: CsvKind,
    registry: InstrumentRegistry,
    audit_log: Optional[AuditLog] = None,
) -> PlatformDatasetRecord:
    """Audit → classify → register instruments (fail-closed, evidence-first).

    The dataset is recorded with its evidence-derived state. Instruments
    are registered with their ORIGINAL identifiers preserved; the data
    state is set exactly as the audit classified it — synthetic datasets
    leave instruments BLOCKED for backtesting/research eligibility per
    registry policy.
    """
    audit = audit_csv_file(path, kind)
    state = audit.recommended_state

    # discovery/verification timestamps must be caller-supplied for
    # determinism — derive a LOGICAL timestamp from the file coverage end
    # (never wall-clock; the file itself is the declared time authority).
    logical_day = audit.coverage_end or "1970-01-01"
    logical_ts = datetime(
        *(int(p) for p in logical_day.split("-")), tzinfo=timezone.utc
    )

    registered: list[str] = []
    df = pd.read_csv(path)
    sym_col = "Symbol_Standard" if "Symbol_Standard" in df.columns else "Symbol"
    exchange_col = "Exchange" if "Exchange" in df.columns else None
    asset_class_col = "Asset_Class" if "Asset_Class" in df.columns else None

    for symbol in sorted(df[sym_col].astype(str).unique()):
        asset_class_value = None
        if asset_class_col:
            rows = df[df[sym_col].astype(str) == symbol]
            asset_class_value = str(rows[asset_class_col].iloc[0])
        venue = None
        if exchange_col:
            rows = df[df[sym_col].astype(str) == symbol]
            venue = str(rows[exchange_col].iloc[0])
        instrument = _instrument_for(kind, symbol, asset_class_value, venue)
        result = registry.register(
            instrument,
            f"csv:{kind.value}:{path.name}",
            logical_ts,
            provider_symbols=(
                ProviderSymbolMapping(
                    provider=f"csv:{kind.value}", provider_symbol=symbol
                ),
            ),
        )
        inst_audit = next(
            (i for i in audit.instruments if i.symbol == symbol), None
        )
        coverage_years = 0.0
        if inst_audit and inst_audit.first_valid_ohlc_date and inst_audit.last_row_date:
            span = (
                date.fromisoformat(inst_audit.last_row_date)
                - date.fromisoformat(inst_audit.first_valid_ohlc_date)
            )
            coverage_years = round(span.days / 365.25, 3)
        registry.set_data_state(
            result.record.internal_id,
            state,
            logical_ts,
            coverage_years=coverage_years,
            # REAL_VERIFIED can never be requested here by construction:
            # the audit classifies SYNTHETIC/INVALID/REAL_UNVERIFIED only.
        )
        registered.append(result.record.internal_id)

    if audit_log is not None:
        audit_log.record(
            logical_ts,
            "registry",
            "dataset_ingested",
            f"{path.name}: state={state.value} rows={audit.row_count} "
            f"instruments={len(registered)}",
            path.name,
        )
        for note in audit.fabrication_evidence:
            audit_log.record(
                logical_ts, "registry", "dataset_evidence", note, path.name
            )

    record = PlatformDatasetRecord(
        dataset_id="DSV-" + _canonical_hash(
            {"file_name": path.name, "sha256": audit.sha256, "kind": kind.value}
        )[:16],
        file_name=path.name,
        sha256=audit.sha256,
        kind=kind,
        row_count=audit.row_count,
        instrument_count=len(registered),
        coverage_start=audit.coverage_start,
        coverage_end=audit.coverage_end,
        data_state=state,
        verification_notes=audit.summary_notes(),
        registered_instrument_ids=tuple(registered),
        audit=audit,
    )
    return record
