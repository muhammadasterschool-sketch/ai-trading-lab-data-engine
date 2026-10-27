"""Durable trade ledger (v1.0.0 — owner mandate: "kis pe trade li,
kitna profit hua").

The owner asked for a per-trade ledger of their engine: WHICH
instrument was traded, WHEN, on which side, at what price, and what
profit/loss it produced — plus aggregate stats (trades per symbol for
the dashboard mini chart, total PnL, wins/losses).

Design (fail-closed, honest, bounded):

- **Append-only JSONL**: one trade = one JSON line in
  ``trade_ledger.jsonl`` inside the monitor state directory. Atomic
  enough for a single-writer lab process; tolerant readers SKIP a
  corrupted line (counted in ``skipped_lines``) instead of refusing
  to serve the whole history.
- **Monitor-only honesty**: in monitor-only serve mode NOTHING
  records into the ledger (no trading session exists, none is
  composed here) — the stats endpoint then reports
  ``total_trades: 0`` and the dashboard chart honestly shows
  "no trades yet". When a composed paper session wires this ledger
  as its fill sink, records appear here and flow straight to the
  phone. No fabricated history, ever.
- **Bounded reads**: ``entries()`` returns the most recent ``limit``
  records (default 200) — the phone never pulls an unbounded list.
- **Validation**: symbol/side/quantity/price are strictly validated
  (side in {BUY, SELL}, quantity > 0, price >= 0); pnl is a float or
  None (open positions carry no realized PnL yet).
- **Thread-safe**: a single lock guards the in-memory index and the
  append; the serving API and a future session loop can share one
  instance.

All data served is SYNTHETIC/paper-only in this repository. LIVE
TRADING REMAINS NOT AUTHORIZED. PAPER_READY stays FALSE.
"""

from __future__ import annotations

import json
import math
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from data_engine.runtime.contracts import RuntimeContractError

_SIDES = frozenset({"BUY", "SELL"})
_MAX_SYMBOL = 64
_MAX_NOTE = 256
_MAX_STRATEGY = 128


class TradeLedgerError(RuntimeContractError):
    """Raised on trade-ledger contract violations."""


def _num(value: Any, field: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TradeLedgerError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise TradeLedgerError(f"{field} must be finite")
    if positive and number <= 0:
        raise TradeLedgerError(f"{field} must be > 0")
    return number


def _text(value: Any, field: str, *, cap: int, required: bool = False) -> str:
    text = "" if value is None else str(value).strip()
    if len(text) > cap:
        text = text[:cap]
    if required and not text:
        raise TradeLedgerError(f"{field} must be non-empty")
    return text


class TradeLedger:
    """Append-only per-trade ledger with aggregate stats."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._records: list[dict] = []
        self.skipped_lines = 0
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError:
            return
        for line in raw.splitlines():
            text = line.strip()
            if not text:
                continue
            try:
                record = json.loads(text)
            except ValueError:
                self.skipped_lines += 1
                continue
            if isinstance(record, dict):
                self._records.append(record)
            else:
                self.skipped_lines += 1

    # -- write path (session-side fill sink) ---------------------------------

    def record(
        self,
        *,
        symbol: Any,
        side: Any,
        quantity: Any,
        price: Any,
        pnl: Any = None,
        strategy: Any = "",
        note: Any = "",
        opened_at: Any = None,
    ) -> dict:
        """Record ONE closed trade (or an open fill with ``pnl=None``).

        Returns the stored record. Raises :class:`TradeLedgerError`
        on any contract violation — a bad fill must never be silently
        rewritten into a good-looking one.
        """
        symbol_text = _text(symbol, "symbol", cap=_MAX_SYMBOL, required=True)
        symbol_text = symbol_text.upper()
        side_text = _text(side, "side", cap=8, required=True).upper()
        if side_text not in _SIDES:
            raise TradeLedgerError("side must be BUY or SELL")
        quantity_value = _num(quantity, "quantity", positive=True)
        price_value = _num(price, "price")
        pnl_value = None if pnl is None else _num(pnl, "pnl")
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "symbol": symbol_text,
            "side": side_text,
            "quantity": quantity_value,
            "price": price_value,
            "pnl": pnl_value,
            "strategy": _text(strategy, "strategy", cap=_MAX_STRATEGY),
            "note": _text(note, "note", cap=_MAX_NOTE),
        }
        if opened_at is not None:
            record["opened_at"] = _text(opened_at, "opened_at", cap=64)
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._records.append(record)
            try:
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            except OSError as exc:
                self._records.pop()  # in-memory must match the durable file
                raise TradeLedgerError(
                    f"trade ledger append failed: {type(exc).__name__}"
                ) from exc
            return dict(record)

    # -- read surface (monitoring API / admin panel) --------------------------

    def entries(self, limit: int = 200) -> list[dict]:
        """Most-recent-first snapshot, bounded by ``limit`` (>= 1)."""
        limit = max(1, int(limit))
        with self._lock:
            records = [dict(r) for r in self._records]
        records.reverse()
        return records[:limit]

    def stats(self) -> dict:
        """Aggregate stats for the dashboard mini chart + admin panel.

        ``per_symbol`` maps symbol -> trade count (the "sab se jyada
        trades" chart data); ``total_pnl`` sums every realized PnL.
        """
        with self._lock:
            records = list(self._records)
        per_symbol: dict[str, int] = {}
        total_pnl = 0.0
        wins = 0
        losses = 0
        for record in records:
            symbol = str(record.get("symbol", "?"))
            per_symbol[symbol] = per_symbol.get(symbol, 0) + 1
            pnl = record.get("pnl")
            if isinstance(pnl, (int, float)) and not isinstance(pnl, bool):
                total_pnl += float(pnl)
                if pnl >= 0:
                    wins += 1
                else:
                    losses += 1
        total_pnl = round(total_pnl, 10)
        return {
            "total_trades": len(records),
            "wins": wins,
            "losses": losses,
            "total_pnl": total_pnl,
            "per_symbol": dict(
                sorted(per_symbol.items(), key=lambda kv: kv[1], reverse=True)
            ),
            "skipped_lines": self.skipped_lines,
            "last_trade_at": records[-1].get("ts") if records else None,
        }


__all__ = ["TradeLedger", "TradeLedgerError"]
