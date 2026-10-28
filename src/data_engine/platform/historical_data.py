"""v1.5.0 HistoricalDataService — REAL, checksum-verified backtest data.

Owner mandate (2026-10-28): "backtest data try karo ke real and
verified data kisi repo se fetch karlo agar na mile to phir websites
par jao".

Source ladder (in order):

1. **Bundled repo datasets** — ``datasets/`` inside the repository
   (Binance Vision monthly 1m klines zips + manifest with sha256 that
   was verified against the source's official ``.CHECKSUM`` at
   acquisition). Works fully offline; every load re-verifies the
   sha256 against the manifest before parsing.
2. **Binance Vision (website)** — downloads additional monthly kline
   zips from ``data.binance.vision`` and verifies them against the
   official ``.CHECKSUM`` file; results are cached on disk so a
   dataset is downloaded + verified at most once per cache lifetime.

GOVERNANCE (honest boundary):

- This module feeds RESEARCH BACKTESTS and the lab BarStore only. It
  is NOT an operational feed: the ``feed_source_candidates`` /
  SRC-APPROVAL chain and the ``DATA_READINESS`` gate are untouched
  (SYNTHETIC_ONLY/REAL_BLOCKED for operational feeds). Nothing here
  can serve a live trading session.
- Bars loaded here are labelled with full provenance (source URL,
  checksum, coverage) and are validated by the lab's own
  ``validate_bar`` (fail-closed) before they can enter the BarStore.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_BINANCE_BASE = (
    "https://data.binance.vision/data/spot/monthly/klines"
)
_SYMBOL_RE = re.compile(r"^[A-Z0-9]{4,20}$")
_TIMEFRAMES = ("1m", "5m", "15m", "1h", "1d")


class HistoricalDataError(RuntimeError):
    """Raised on contract violations (fail closed)."""


# ---------------------------------------------------------------------------
# datasets/ root discovery
# ---------------------------------------------------------------------------

def find_datasets_root() -> Optional[Path]:
    """Locate the bundled ``datasets/`` directory (env > CWD > repo)."""
    env = os.environ.get("AITL_DATASETS_DIR")
    if env:
        candidate = Path(env)
        if candidate.is_dir():
            return candidate
    for base in (Path.cwd(), Path(__file__).resolve().parents):
        # parents walks upward from platform/ -> data_engine -> src -> repo
        for depth in range(0, 6):
            candidate = base if depth == 0 else base
        break
    here = Path(__file__).resolve()
    # src/data_engine/platform/historical_data.py -> repo root is 3 up
    for parent in here.parents:
        candidate = parent / "datasets"
        if (candidate / "manifest.json").is_file():
            return candidate
    cwd_candidate = Path.cwd() / "datasets"
    if (cwd_candidate / "manifest.json").is_file():
        return cwd_candidate
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def list_bundled_datasets() -> List[Dict[str, Any]]:
    """Manifest entries for the bundled (offline, verified) datasets."""
    root = find_datasets_root()
    if root is None:
        return []
    try:
        manifest = json.loads(
            (root / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return []
    datasets = manifest.get("datasets")
    if not isinstance(datasets, list):
        return []
    return [dict(d) for d in datasets if isinstance(d, dict)]


def _parse_binance_csv(raw: bytes, symbol: str) -> List[Dict[str, Any]]:
    """Parse Binance monthly klines CSV bytes into lab bar dicts.

    Columns: open_time(us), open, high, low, close, volume, close_time,
    quote_volume, count, taker_buy_base, taker_buy_quote, ignore.
    """
    text = raw.decode("utf-8")
    rows = csv.reader(io.StringIO(text))
    bars: List[Dict[str, Any]] = []
    for row in rows:
        if len(row) < 6:
            continue
        try:
            open_ts_us = int(row[0])
            open_ = float(row[1])
            high = float(row[2])
            low = float(row[3])
            close = float(row[4])
            volume = float(row[5])
        except (ValueError, IndexError):
            raise HistoricalDataError(
                f"malformed kline row for {symbol} (refused, fail closed)"
            )
        ts = datetime.fromtimestamp(
            open_ts_us / 1_000_000.0, tz=timezone.utc
        ).isoformat()
        bars.append(
            {
                "ts": ts,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            }
        )
    return bars


# ---------------------------------------------------------------------------
# Binance Vision source (network, injectable transport for tests)
# ---------------------------------------------------------------------------

def _default_transport(url: str, timeout: float = 60.0) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "ai-trading-lab-data-engine/1.5.0"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


class BinanceVisionSource:
    """Downloads + checksum-verifies monthly klines from Binance Vision."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        transport: Optional[Callable[[str], bytes]] = None,
    ) -> None:
        self._cache = Path(cache_dir) if cache_dir else None
        self._transport = transport or _default_transport

    def fetch_month(
        self,
        symbol: str,
        timeframe: str,
        year: int,
        month: int,
    ) -> Dict[str, Any]:
        if not _SYMBOL_RE.match(symbol or ""):
            raise HistoricalDataError(f"invalid symbol {symbol!r}")
        if timeframe not in _TIMEFRAMES:
            raise HistoricalDataError(
                f"unsupported timeframe {timeframe!r} "
                f"(allowed: {list(_TIMEFRAMES)})"
            )
        if not 2017 <= year <= 2100 or not 1 <= month <= 12:
            raise HistoricalDataError("year/month out of range")
        name = f"{symbol}-{timeframe}-{year}-{month:02d}.zip"
        url = f"{_BINANCE_BASE}/{symbol}/{timeframe}/{name}"
        checksum_url = f"{url}.CHECKSUM"
        cache_path = (
            self._cache / name if self._cache is not None else None
        )
        if cache_path is not None and cache_path.is_file():
            payload = cache_path.read_bytes()
            cached = True
        else:
            try:
                payload = self._transport(url)
            except Exception as exc:  # network/HTTP — surfaced honestly
                raise HistoricalDataError(
                    f"download failed for {url}: {type(exc).__name__}"
                ) from exc
            cached = False
        # ALWAYS verify against the official checksum (even cached data)
        try:
            checksum_raw = self._transport(checksum_url).decode("utf-8")
        except Exception as exc:
            raise HistoricalDataError(
                f"checksum download failed for {checksum_url}: "
                f"{type(exc).__name__} (unverified data is refused)"
            ) from exc
        expected = checksum_raw.split()[0].strip().lower()
        actual = hashlib.sha256(payload).hexdigest()
        if expected != actual:
            raise HistoricalDataError(
                f"sha256 MISMATCH for {name}: expected {expected}, got "
                f"{actual} (refused, fail closed)"
            )
        if cache_path is not None and not cached:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(payload)
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            inner = [n for n in zf.namelist() if n.endswith(".csv")]
            if not inner:
                raise HistoricalDataError(
                    f"downloaded archive has no CSV member for {symbol}"
                )
            raw_csv = zf.read(inner[0])
        bars = _parse_binance_csv(raw_csv, symbol)
        if not bars:
            raise HistoricalDataError(f"no bars parsed from {name}")
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": bars,
            "count": len(bars),
            "provenance": {
                "source": "binance-vision",
                "source_url": url,
                "checksum_url": checksum_url,
                "sha256": actual,
                "checksum_verified": True,
                "cached": cached,
                "format": "binance-monthly-klines-csv-zip",
                "governance": "RESEARCH_BACKTEST_ONLY",
            },
        }


# ---------------------------------------------------------------------------
# Bundled source (offline, manifest-verified)
# ---------------------------------------------------------------------------

def load_bundled_dataset(dataset_id: str) -> Dict[str, Any]:
    """Load one bundled dataset, re-verifying its sha256 (fail closed)."""
    root = find_datasets_root()
    if root is None:
        raise HistoricalDataError(
            "no bundled datasets/ directory found (repo or "
            "AITL_DATASETS_DIR)"
        )
    for entry in list_bundled_datasets():
        if entry.get("id") != dataset_id:
            continue
        path = root / str(entry.get("path", ""))
        if not path.is_file():
            raise HistoricalDataError(
                f"bundled dataset file missing: {entry.get('path')}"
            )
        actual = _sha256_file(path)
        expected = str(entry.get("sha256", "")).lower()
        if not expected or actual != expected:
            raise HistoricalDataError(
                f"sha256 MISMATCH for bundled {dataset_id}: manifest "
                f"{expected[:16]}... vs file {actual[:16]}... "
                "(refused, fail closed)"
            )
        with zipfile.ZipFile(path) as zf:
            inner = [n for n in zf.namelist() if n.endswith(".csv")]
            if not inner:
                raise HistoricalDataError(
                    f"bundled {dataset_id} has no CSV member"
                )
            raw = zf.read(inner[0])
        bars = _parse_binance_csv(raw, str(entry.get("symbol", "")))
        if not bars:
            raise HistoricalDataError(f"no bars parsed from {dataset_id}")
        return {
            "symbol": entry.get("symbol"),
            "timeframe": entry.get("timeframe"),
            "bars": bars,
            "count": len(bars),
            "provenance": {
                "source": "bundled-repo",
                "dataset_id": dataset_id,
                "source_url": entry.get("source_url"),
                "checksum_url": entry.get("checksum_url"),
                "sha256": actual,
                "checksum_verified": True,
                "coverage": entry.get("coverage"),
                "license_note": entry.get("license_note"),
                "governance": "RESEARCH_BACKTEST_ONLY",
            },
        }
    raise HistoricalDataError(f"unknown bundled dataset {dataset_id!r}")


# ---------------------------------------------------------------------------
# Service facade
# ---------------------------------------------------------------------------

class HistoricalDataService:
    """Bundled-first real-data service with a website fallback."""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        transport: Optional[Callable[[str], bytes]] = None,
    ) -> None:
        self._binance = BinanceVisionSource(
            cache_dir=cache_dir, transport=transport
        )

    def bundled_for(self, symbol: str, timeframe: str = "1m") -> List[dict]:
        """Manifest entries matching a symbol/timeframe."""
        return [
            d
            for d in list_bundled_datasets()
            if d.get("symbol") == symbol and d.get("timeframe") == timeframe
        ]

    def fetch(
        self,
        symbol: str,
        timeframe: str = "1m",
        *,
        months: int = 1,
        source: str = "auto",
        end_year: Optional[int] = None,
        end_month: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Fetch real bars: bundled repo data first, then the website.

        ``months`` <= 3 (bounded); ``source`` = auto | bundled |
        binance-vision. When fetching from the website the most recent
        COMPLETE month is the default anchor (current month is never
        served half-finished).
        """
        if isinstance(months, bool) or not isinstance(months, int):
            raise HistoricalDataError("months must be an integer")
        if not 1 <= months <= 3:
            raise HistoricalDataError("months must be within [1, 3]")
        if source not in ("auto", "bundled", "binance-vision"):
            raise HistoricalDataError(f"unknown source {source!r}")
        if source in ("auto", "bundled"):
            matches = self.bundled_for(symbol, timeframe)
            if matches:
                latest = sorted(
                    matches, key=lambda d: str(d.get("id", ""))
                )[-1]
                result = load_bundled_dataset(str(latest["id"]))
                result["source_used"] = "bundled-repo"
                return result
            if source == "bundled":
                raise HistoricalDataError(
                    f"no bundled dataset for {symbol} {timeframe} "
                    "(fallback disabled for this call)"
                )
        # website fallback (or explicit binance-vision)
        if end_year is None or end_month is None:
            now = datetime.now(timezone.utc)
            # anchor at the last COMPLETE month
            if now.month == 1:
                end_year, end_month = now.year - 1, 12
            else:
                end_year, end_month = now.year, now.month - 1
        collected: List[Dict[str, Any]] = []
        year, month = end_year, end_month
        for _ in range(months):
            result = self._binance.fetch_month(symbol, timeframe, year, month)
            collected.insert(0, result)
            month -= 1
            if month == 0:
                month = 12
                year -= 1
        bars: List[Dict[str, Any]] = []
        provenance: List[dict] = []
        for result in collected:
            bars.extend(result["bars"])
            provenance.append(result["provenance"])
        # dedupe by ts (keep newest) + chronological sort
        by_ts: Dict[str, Dict[str, Any]] = {}
        for bar in bars:
            by_ts[bar["ts"]] = bar
        bars = [by_ts[k] for k in sorted(by_ts.keys())]
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": bars,
            "count": len(bars),
            "source_used": "binance-vision",
            "provenance": provenance,
        }

    @staticmethod
    def import_into_barstore(
        bar_store: Any,
        symbol: str,
        bars: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Chunked, validated import into the lab BarStore (bounded)."""
        from data_engine.runtime.lab import MAX_BARS_PER_REQUEST

        if not bars:
            raise HistoricalDataError("no bars to import")
        added = 0
        total = 0
        for start in range(0, len(bars), MAX_BARS_PER_REQUEST):
            chunk = bars[start: start + MAX_BARS_PER_REQUEST]
            result = bar_store.append(symbol, chunk)
            added += int(result.get("added", 0))
            total = int(result.get("total", total))
        return {
            "symbol": symbol,
            "imported": added,
            "total_in_store": total,
        }


__all__ = [
    "HistoricalDataError",
    "HistoricalDataService",
    "BinanceVisionSource",
    "find_datasets_root",
    "list_bundled_datasets",
    "load_bundled_dataset",
]
