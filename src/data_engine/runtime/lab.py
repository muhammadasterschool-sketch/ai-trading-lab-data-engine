"""v1.1.0 OWNER AI LAB — the owner-facing research surfaces.

Owner mandate (2026-10-27): "mujhe aik ai ho jiss se hum total profit
and loss puch sake ... agar mai koi strategy do toh woh backtest kare
phir paper trading kare phir results ke sath confirmation le ke ye
strategy ko live karde ... next market ki move predict karne ki
capabilities".

What this module ACTUALLY provides (honest engineering, no theatre):

- :class:`BarStore` — owner-uploaded OHLCV history per symbol
  (bounded, validated, atomic). The lab NEVER invents market data.
- :class:`AssistantEngine` — a DETERMINISTIC, offline, rule-based
  analytics assistant over the owner ledgers (trade ledger, client
  registry, kill-switch state). No external LLM is called; nothing is
  fabricated; every number comes from a ledger.
- :class:`LabBacktester` — a deterministic long/flat signal runner
  (EMA trend / EMA cross / RSI reversal / breakout) over the owner's
  bars, producing objective BacktestEvidence for the G6 gate.
- :class:`LabManager` — the durable driver of the EXISTING fail-closed
  StrategyActivationGate pipeline (submit -> backtest -> paper
  validation window -> explicit YES). Activation remains
  PAPER-EVALUATION-ONLY: LIVE_ACTIVE is unreachable by construction
  and the governance file is untouched (PAPER_READY=FALSE,
  LIVE_AUTHORIZATION=NOT_AUTHORIZED).
- :class:`PredictBaseline` — a statistical next-move baseline
  (momentum vs volatility, logistic squash) with explicit
  research-only disclaimers.
- :class:`BrokerCatalog` — the honest broker surface: simulation/mock
  adapters shipped in-repo + the operator MT5 demo step + the adapter
  interface contract used to add new brokers.
- v1.5.0 additions: five TOP-5 YouTuber strategy kinds (EMA scalp /
  RSI+Bollinger / VWAP reversion / Supertrend follow / opening-range
  breakout — all confirmation-candle, M1-first), an optional cost
  model in the lab backtester (fees+slippage, net-of-cost metrics),
  AUTO-SCAN (deterministic parameter scan with a 70/30 IS/OOS split
  that creates ordinary G6 submissions for the owner to confirm),
  preset bootstrap (the five presets auto-created per symbol so paper
  trading starts with them), and the PAPER-ONLY RapidScalper burst
  journal (one hypothetical fill per second for one minute after a
  >=60% ConfidenceGate confirmation candle — journaled, never sent).
  Governance is untouched: PAPER_READY=FALSE,
  LIVE_AUTHORIZATION=NOT_AUTHORIZED.

Fail-closed everywhere: bad bars are refused, unknown strategies are
refused, the 30-day validation window is enforced by the gate (a
shorter owner-chosen cycle is journaled as a deviation, never silent),
and the kill switch PAUSES forward paper evaluation (a standing STOP
is a stop for the whole lab).
"""

from __future__ import annotations

import json
import math
import os
import re
import threading
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

from data_engine import __version__
from data_engine.runtime.strategy_activation import (
    ActivationDecision,
    BacktestEvidence,
    StrategyActivationError,
    StrategyActivationGate,
    ValidationEvidence,
    VALIDATION_CYCLE_DAYS,
)

#: Hard bounds (fail-closed sizing; every store is bounded).
MAX_BARS_PER_REQUEST = 10_000
MAX_BARS_PER_SYMBOL = 200_000
MIN_BARS_FOR_BACKTEST = 30
MAX_STRATEGIES = 100
MAX_PAPER_EVENTS = 50_000
MAX_QUESTION_CHARS = 2_000
MAX_QUESTION_CHARS_DISPLAY = 200

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9._/-]{1,24}$")
_SLUG_RE = re.compile(r"[^A-Za-z0-9._-]")


class LabError(RuntimeError):
    """Raised on lab-contract violations (fail closed)."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _atomic_write_json(path: Path, payload: Any) -> None:
    """Atomic JSON write (tmp file + os.replace) — a crash mid-write
    can never leave a truncated store behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=1, sort_keys=False), encoding="utf-8"
    )
    os.replace(tmp, path)


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _parse_ts(value: Any) -> datetime:
    """Accept epoch seconds (int/float) or ISO-8601 strings; always
    returns an aware UTC datetime or raises LabError."""
    if isinstance(value, bool):
        raise LabError("bar timestamp must be epoch seconds or ISO-8601")
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise LabError(
                f"bar timestamp not epoch/ISO-8601: {text[:40]!r}"
            ) from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    raise LabError("bar timestamp must be epoch seconds or ISO-8601")


def _as_finite_float(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LabError(f"bar {field} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise LabError(f"bar {field} must be finite")
    return result


def validate_bar(raw: Any) -> Dict[str, Any]:
    """Validate + normalize ONE owner-supplied OHLCV bar (fail closed)."""
    if not isinstance(raw, Mapping):
        raise LabError("each bar must be a JSON object")
    ts = _parse_ts(
        raw.get("ts", raw.get("timestamp", raw.get("time")))
    )
    open_ = _as_finite_float(raw.get("open"), "open")
    high = _as_finite_float(raw.get("high"), "high")
    low = _as_finite_float(raw.get("low"), "low")
    close = _as_finite_float(raw.get("close"), "close")
    if min(open_, high, low, close) <= 0:
        raise LabError("bar prices must be positive")
    if high < max(open_, close) or low > min(open_, close):
        raise LabError(
            "bar high/low inconsistent with open/close (high < body or "
            "low > body is refused)"
        )
    volume: Optional[float] = None
    if raw.get("volume") is not None:
        volume = _as_finite_float(raw.get("volume"), "volume")
        if volume < 0:
            raise LabError("bar volume must be non-negative")
    return {
        "ts": ts.isoformat(),
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }


# ---------------------------------------------------------------------------
# BarStore — owner-uploaded OHLCV history (bounded, atomic, per symbol)
# ---------------------------------------------------------------------------


class BarStore:
    """Per-symbol bar history under ``<state_dir>/bars/``.

    The lab NEVER invents market data: bars enter ONLY through the
    owner's explicit upload (PC-side ``push-bars.ps1`` or the API).
    Files are atomic JSON; every append re-validates and re-trims to
    the per-symbol bound; duplicate timestamps keep the newest bar.
    """

    def __init__(self, state_dir: Path | str) -> None:
        self._dir = Path(state_dir) / "bars"
        self._lock = threading.Lock()

    def _path(self, symbol: str) -> Path:
        if (
            not isinstance(symbol, str)
            or not _SYMBOL_RE.match(symbol)
            or ".." in symbol
            or symbol.startswith("/")
        ):
            raise LabError(
                "symbol must match [A-Za-z0-9._/-]{1,24} without path "
                "traversal (e.g. XAU/USD, BTCUSD)"
            )
        slug = _SLUG_RE.sub("_", symbol)
        return self._dir / f"bars-{slug}.json"

    def append(self, symbol: str, bars: List[Any]) -> Dict[str, Any]:
        """Validate + merge bars (dedupe by timestamp, keep newest);
        returns {added, total, first_ts, last_ts}."""
        if not isinstance(bars, list) or not bars:
            raise LabError("bars must be a non-empty JSON array")
        if len(bars) > MAX_BARS_PER_REQUEST:
            raise LabError(
                f"max {MAX_BARS_PER_REQUEST} bars per request "
                "(split the upload)"
            )
        normalized = [validate_bar(raw) for raw in bars]
        normalized.sort(key=lambda b: b["ts"])
        with self._lock:
            existing: Dict[str, Dict[str, Any]] = {}
            payload = _read_json(self._path(symbol), None)
            if isinstance(payload, dict) and isinstance(
                payload.get("bars"), list
            ):
                for bar in payload["bars"]:
                    existing[str(bar.get("ts"))] = bar
            known_before = set(existing)
            added = sum(
                1 for bar in normalized if bar["ts"] not in known_before
            )
            for bar in normalized:
                existing[bar["ts"]] = bar
            merged = sorted(existing.values(), key=lambda b: b["ts"])
            if len(merged) > MAX_BARS_PER_SYMBOL:
                merged = merged[-MAX_BARS_PER_SYMBOL:]
            _atomic_write_json(
                self._path(symbol),
                {"symbol": symbol, "count": len(merged), "bars": merged},
            )
            return {
                "symbol": symbol,
                "added": added,
                "total": len(merged),
                "first_ts": merged[0]["ts"] if merged else None,
                "last_ts": merged[-1]["ts"] if merged else None,
            }

    def bars(self, symbol: str, limit: Optional[int] = None) -> List[Dict]:
        """Newest-last bar list (optionally only the last ``limit``)."""
        with self._lock:
            payload = _read_json(self._path(symbol), None)
        if not isinstance(payload, dict) or not isinstance(
            payload.get("bars"), list
        ):
            return []
        bars = list(payload["bars"])
        if limit is not None and limit >= 0:
            bars = bars[-limit:]
        return bars

    def count(self, symbol: str) -> int:
        return len(self.bars(symbol))

    def summary(self, symbol: str) -> Dict[str, Any]:
        bars = self.bars(symbol)
        return {
            "symbol": symbol,
            "count": len(bars),
            "first_ts": bars[0]["ts"] if bars else None,
            "last_ts": bars[-1]["ts"] if bars else None,
            "latest_close": bars[-1]["close"] if bars else None,
        }

    def symbols(self) -> List[str]:
        """Symbols that currently have stored bars (sorted)."""
        if not self._dir.exists():
            return []
        found = []
        for path in sorted(self._dir.glob("bars-*.json")):
            payload = _read_json(path, None)
            if isinstance(payload, dict) and payload.get("symbol"):
                found.append(str(payload["symbol"]))
        return sorted(set(found))


# ---------------------------------------------------------------------------
# AssistantEngine — deterministic offline analytics Q&A over the ledgers
# ---------------------------------------------------------------------------


class AssistantEngine:
    """Rule-based analytics assistant ("AI" the honest way).

    Every answer is COMPUTED from the owner ledgers (trade ledger,
    client registry, kill-switch state). No external model is called,
    nothing is invented, and when a ledger is empty the answer says
    so plainly. Deterministic: the same question + ledgers always
    produce the same answer.
    """

    def __init__(
        self,
        *,
        trade_ledger: Any,
        client_registry: Any,
        health_provider: Callable[[], dict],
    ) -> None:
        self._ledger = trade_ledger
        self._registry = client_registry
        self._health = health_provider

    # -- public ------------------------------------------------------------

    def ask(self, question: str) -> Dict[str, Any]:
        text = (question or "").strip()[:MAX_QUESTION_CHARS]
        if not text:
            raise LabError("a question is required")
        lowered = text.lower()
        stats = self._ledger.stats() if self._ledger is not None else {}

        # help / capabilities first (explicit ask)
        if any(k in lowered for k in ("help", "what can you", "kya kar")):
            return self._reply(text, self._capabilities())

        # who is logged in / online
        if any(
            k in lowered
            for k in ("who is logged", "logged in", "online", "kon", "kaun")
        ) and "registr" not in lowered:
            return self._reply(text, self._who_is_online())

        # registration ledger
        if any(k in lowered for k in ("registr", "registered", "sab ne")):
            return self._reply(text, self._registrations_answer())

        # stop / kill switch state
        if any(
            k in lowered for k in ("stop", "kill", "halt", "band", "roka")
        ):
            return self._reply(text, self._stop_state())

        # best / worst symbol by PnL
        wants_best = any(
            k in lowered for k in ("best", "sab se acha", "top")
        )
        wants_worst = any(
            k in lowered for k in ("worst", "sab se kharab", "loss making")
        )
        if wants_best or wants_worst:
            return self._reply(
                text, self._symbol_extreme(best=wants_best)
            )

        # a specific symbol mentioned?
        per_symbol = self._per_symbol_pnl()
        for symbol in sorted(per_symbol, key=len, reverse=True):
            if symbol.lower() in lowered:
                return self._reply(text, self._symbol_answer(symbol))

        # win rate / wins / losses
        if any(
            k in lowered
            for k in ("win", "jeet", "loss rate", "haar", "losses")
        ):
            return self._reply(text, self._win_rate(stats))

        # total profit / loss / pnl
        if any(
            k in lowered
            for k in (
                "total",
                "profit",
                "pnl",
                "p&l",
                "kitna",
                "how much",
                "loss",
                "net",
            )
        ):
            return self._reply(text, self._total_pnl(stats))

        # trade count
        if any(k in lowered for k in ("trade", "trades", "kitni")):
            return self._reply(text, self._trade_count(stats))

        return self._reply(text, self._fallback())

    # -- intent answers ------------------------------------------------------

    def _reply(self, question: str, answer: Dict[str, Any]) -> dict:
        return {
            "question": question[:MAX_QUESTION_CHARS_DISPLAY],
            "answer": answer["answer"],
            "metrics": answer.get("metrics", {}),
            "engine": "rule-based-analytics-offline",
            "generated_at": _utc_now().isoformat(),
        }

    @staticmethod
    def _capabilities() -> dict:
        return {
            "answer": (
                "I am the lab's offline analytics assistant. I can answer "
                "from your LEDGERS only: total profit/loss, per-symbol "
                "PnL, best/worst symbol, win rate, trade counts, who is "
                "logged in, the registration ledger, and the STOP flag "
                "state. I never invent numbers and I never give advice."
            ),
            "metrics": {"capabilities": [
                "total pnl", "per-symbol pnl", "best/worst symbol",
                "win rate", "trade count", "who is online",
                "registrations", "kill-switch state",
            ]},
        }

    def _total_pnl(self, stats: dict) -> dict:
        pnl = float(stats.get("total_pnl", 0.0))
        trades = int(stats.get("total_trades", 0))
        if trades == 0:
            answer = (
                "The trade ledger has NO trades yet (total PnL 0.0). In "
                "monitor-only mode the ledger fills only when a composed "
                "paper session records fills — nothing is fabricated."
            )
        else:
            sign = "profit" if pnl >= 0 else "loss"
            answer = (
                f"Total realized PnL across {trades} trades: {pnl:.10g} "
                f"(net {sign}). Wins {stats.get('wins', 0)} / losses "
                f"{stats.get('losses', 0)}."
            )
        return {"answer": answer, "metrics": stats}

    def _trade_count(self, stats: dict) -> dict:
        trades = int(stats.get("total_trades", 0))
        top = stats.get("per_symbol", {})
        top_str = ", ".join(
            f"{s}: {c}" for s, c in list(top.items())[:6]
        ) or "none"
        return {
            "answer": (
                f"{trades} trades in the ledger. Trades by symbol "
                f"(top): {top_str}."
            ),
            "metrics": {"total_trades": trades, "per_symbol": top},
        }

    def _win_rate(self, stats: dict) -> dict:
        wins = int(stats.get("wins", 0))
        losses = int(stats.get("losses", 0))
        total = wins + losses
        rate = (wins / total * 100.0) if total else 0.0
        return {
            "answer": (
                f"Win rate {rate:.1f}% ({wins} wins / {losses} losses "
                f"over {total} decided trades)."
            ),
            "metrics": {
                "wins": wins, "losses": losses, "win_rate_pct": round(rate, 2),
            },
        }

    def _per_symbol_pnl(self) -> Dict[str, float]:
        """Per-symbol realized PnL computed from the ledger entries."""
        per_symbol: Dict[str, float] = {}
        if self._ledger is None:
            return per_symbol
        try:
            entries = self._ledger.entries(limit=5000)
        except Exception:
            return per_symbol
        for record in entries:
            symbol = str(record.get("symbol", "?"))
            pnl = record.get("pnl")
            if isinstance(pnl, (int, float)) and not isinstance(pnl, bool):
                per_symbol[symbol] = per_symbol.get(symbol, 0.0) + float(pnl)
        return per_symbol

    def _symbol_answer(self, symbol: str) -> dict:
        pnl_map = self._per_symbol_pnl()
        if symbol not in pnl_map:
            return {
                "answer": (
                    f"No realized PnL recorded for {symbol} in the trade "
                    "ledger yet."
                ),
                "metrics": {"symbol": symbol, "pnl": 0.0},
            }
        pnl = pnl_map[symbol]
        verdict = "profit" if pnl >= 0 else "loss"
        return {
            "answer": (
                f"{symbol}: realized {verdict} of {pnl:.10g} in the "
                "trade ledger."
            ),
            "metrics": {"symbol": symbol, "pnl": round(pnl, 10)},
        }

    def _symbol_extreme(self, *, best: bool) -> dict:
        pnl_map = self._per_symbol_pnl()
        if not pnl_map:
            return {
                "answer": (
                    "The trade ledger has no per-symbol PnL yet, so "
                    "best/worst is undefined — nothing is fabricated."
                ),
                "metrics": {},
            }
        symbol = (
            max(pnl_map, key=pnl_map.get)
            if best
            else min(pnl_map, key=pnl_map.get)
        )
        label = "best" if best else "worst"
        return {
            "answer": (
                f"{label.capitalize()} symbol by realized PnL: {symbol} "
                f"({pnl_map[symbol]:.10g})."
            ),
            "metrics": {"symbol": symbol, "pnl": round(pnl_map[symbol], 10)},
        }

    def _who_is_online(self) -> dict:
        rows = (
            self._registry.users() if self._registry is not None else []
        )
        online = [r for r in rows if r.get("online")]
        names = [
            f"{r.get('name') or 'unnamed'} <{r.get('email') or 'no-email'}>"
            for r in online
        ]
        listing = "; ".join(names) if names else "nobody right now"
        return {
            "answer": (
                f"{len(online)} client(s) online in the 90s window: "
                f"{listing}."
            ),
            "metrics": {
                "online": len(online), "known_clients": len(rows),
            },
        }

    def _registrations_answer(self) -> dict:
        rows = (
            self._registry.registrations()
            if self._registry is not None
            else []
        )
        latest = [
            f"{r.get('name') or 'unnamed'} "
            f"<{r.get('email') or 'no-email'}> ({r.get('kind') or '?'})"
            for r in rows[:5]
        ]
        listing = "; ".join(latest) if latest else "no registrations yet"
        return {
            "answer": (
                f"{len(rows)} client(s) in the durable registration "
                f"ledger. Most recent: {listing}."
            ),
            "metrics": {"registered": len(rows)},
        }

    def _stop_state(self) -> dict:
        try:
            health = self._health() or {}
        except Exception:
            health = {}
        state = str(health.get("kill_switch", "UNKNOWN"))
        verdict = (
            "trading is HALTED by the durable STOP flag"
            if state == "ACTIVE"
            else "no standing STOP flag (state " + state + ")"
        )
        return {
            "answer": f"Kill-switch state: {state} — {verdict}.",
            "metrics": {"kill_switch": state},
        }

    @staticmethod
    def _fallback() -> dict:
        return {
            "answer": (
                "I only answer from your ledgers (I never invent data). "
                "Try: 'total profit', 'win rate', 'how many trades', "
                "'best symbol', 'XAUUSD pe kitna profit', 'who is logged "
                "in', 'registrations', 'is trading stopped?', 'help'."
            ),
            "metrics": {},
        }


# ---------------------------------------------------------------------------
# LabBacktester — deterministic long/flat signal runner
# ---------------------------------------------------------------------------

_KINDS = (
    "ema_trend",
    "ema_cross",
    "rsi_reversal",
    "breakout",
    # v1.5.0 TOP-5 YouTuber preset kinds (runtime/presets.py)
    "ema_scalp",
    "rsi_bb",
    "vwap_reversion",
    "supertrend_follow",
    "orb_breakout",
)

_PARAM_BOUNDS: Dict[str, Dict[str, tuple]] = {
    "ema_trend": {"period": (2, 400)},
    "ema_cross": {"fast": (2, 200), "slow": (3, 400)},
    "rsi_reversal": {
        "period": (2, 100),
        "oversold": (1, 49),
        "overbought": (51, 99),
    },
    "breakout": {"lookback": (5, 400)},
    # v1.5.0 (integer params; float params live in _FLOAT_PARAM_BOUNDS)
    "ema_scalp": {"fast": (2, 100), "slow": (3, 200), "trend": (10, 400)},
    "rsi_bb": {"rsi_period": (2, 100), "bb_period": (5, 200)},
    "vwap_reversion": {"vwap_window": (5, 200), "rsi_period": (2, 50)},
    "supertrend_follow": {"st_period": (2, 100), "adx_period": (5, 100)},
    "orb_breakout": {"range_bars": (3, 120), "vol_period": (5, 200)},
}

#: v1.5.0 float-valued params (accepted as int OR float; every other
#: param stays integer-only — the v1.1.0 contract is preserved).
_FLOAT_PARAM_BOUNDS: Dict[str, Dict[str, tuple]] = {
    "rsi_bb": {
        "oversold": (1.0, 49.0),
        "overbought": (51.0, 99.0),
        "bb_std": (0.5, 5.0),
    },
    "vwap_reversion": {
        "deviation_bps": (10.0, 2000.0),
        "rsi_low": (1.0, 49.0),
    },
    "supertrend_follow": {
        "st_mult": (0.5, 10.0),
        "adx_min": (5.0, 60.0),
    },
    "orb_breakout": {
        "vol_factor": (1.0, 10.0),
    },
}

#: v1.5.0 conservative research cost assumptions (per SIDE, basis
#: points). These are documented defaults — NOT venue quotes; owners
#: can pass explicit costs to ``LabBacktester.run``.
def default_cost_bps(symbol: str) -> Dict[str, float]:
    """Conservative per-side cost defaults by asset family (bps)."""
    s = (symbol or "").upper()
    if any(key in s for key in ("USDT", "BUSD", "USDC", "BTC", "ETH")):
        return {"fee_bps": 10.0, "slippage_bps": 2.0}  # crypto taker-ish
    return {"fee_bps": 1.0, "slippage_bps": 7.0}  # FX/metals spread-ish


def _ema_series(closes: List[float], period: int) -> List[Optional[float]]:
    """EMA via the engine's own quant module (single source of truth);
    falls back to the textbook kernel only if the quant import is
    unavailable (never silently changes numbers — the fallback is the
    same formula)."""
    try:
        from data_engine.quant.moving_averages import ema as quant_ema

        return list(quant_ema(closes, period))
    except Exception:  # pragma: no cover - quant is always importable here
        out: List[Optional[float]] = [None] * len(closes)
        if len(closes) < period:
            return out
        alpha = 2.0 / (period + 1.0)
        seed = sum(closes[:period]) / period
        out[period - 1] = seed
        prev = seed
        for i in range(period, len(closes)):
            prev = alpha * closes[i] + (1 - alpha) * prev
            out[i] = prev
        return out


def _rsi_series(closes: List[float], period: int) -> List[Optional[float]]:
    try:
        from data_engine.quant.momentum import rsi as quant_rsi

        return list(quant_rsi(closes, period))
    except Exception:  # pragma: no cover
        out: List[Optional[float]] = [None] * len(closes)
        if len(closes) <= period:
            return out
        gains = losses = 0.0
        for i in range(1, period + 1):
            delta = closes[i] - closes[i - 1]
            gains += max(delta, 0.0)
            losses += max(-delta, 0.0)
        avg_gain = gains / period
        avg_loss = losses / period
        out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (
            1.0 + avg_gain / avg_loss
        )
        for i in range(period + 1, len(closes)):
            delta = closes[i] - closes[i - 1]
            avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
            avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
            out[i] = (
                100.0
                if avg_loss == 0
                else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
            )
        return out


class LabBacktester:
    """Deterministic long/flat runner over OWNER-SUPPLIED bars.

    Execution semantics: the signal computed at bar ``i``'s close is
    filled at THAT bar's close (``signal_at_t_close_execute_at_t_close``
    — the repo's canonical default). Long/flat only; no shorts; the
    equity curve compounds round trips at close prices. This runner is
    deliberately simpler than the full :mod:`data_engine.strategy`
    BacktestEngine (which models commissions/slippage) and says so in
    its notes — the full engine remains available for deeper runs.
    """

    KINDS = _KINDS

    def positions(self, kind: str, params: Dict[str, Any], bars: List[dict]) -> List[int]:
        """Desired position (0/1) after each bar's close."""
        closes = [float(b["close"]) for b in bars]
        if kind == "ema_trend":
            period = int(params.get("period", 50))
            ema = _ema_series(closes, period)
            return [
                1 if (ema[i] is not None and closes[i] > ema[i]) else 0
                for i in range(len(closes))
            ]
        if kind == "ema_cross":
            fast = int(params.get("fast", 12))
            slow = int(params.get("slow", 26))
            if fast >= slow:
                raise LabError("ema_cross requires fast < slow")
            f = _ema_series(closes, fast)
            s = _ema_series(closes, slow)
            return [
                1 if (f[i] is not None and s[i] is not None and f[i] > s[i]) else 0
                for i in range(len(closes))
            ]
        if kind == "rsi_reversal":
            period = int(params.get("period", 14))
            oversold = float(params.get("oversold", 30))
            overbought = float(params.get("overbought", 70))
            rsi = _rsi_series(closes, period)
            positions: List[int] = [0] * len(closes)
            held = 0
            for i in range(len(closes)):
                value = rsi[i]
                if value is not None:
                    if held == 0 and value < oversold:
                        held = 1
                    elif held == 1 and value > overbought:
                        held = 0
                positions[i] = held
            return positions
        if kind == "breakout":
            lookback = int(params.get("lookback", 20))
            positions = [0] * len(closes)
            held = 0
            for i in range(len(closes)):
                if i >= lookback:
                    window_high = max(
                        float(bars[j]["high"])
                        for j in range(i - lookback, i)
                    )
                    window_low = min(
                        float(bars[j]["low"])
                        for j in range(i - lookback, i)
                    )
                    if held == 0 and closes[i] > window_high:
                        held = 1
                    elif held == 1 and closes[i] < window_low:
                        held = 0
                positions[i] = held
            return positions
        if kind == "ema_scalp":
            # v1.5.0 YT1: EMA fast/slow cross traded only above the
            # trend EMA (confirmation candle = closed bar)
            fast = int(params.get("fast", 9))
            slow = int(params.get("slow", 21))
            trend = int(params.get("trend", 200))
            if fast >= slow:
                raise LabError("ema_scalp requires fast < slow")
            f = _ema_series(closes, fast)
            s = _ema_series(closes, slow)
            t = _ema_series(closes, trend)
            return [
                1
                if (
                    f[i] is not None
                    and s[i] is not None
                    and t[i] is not None
                    and f[i] > s[i]
                    and closes[i] > t[i]
                )
                else 0
                for i in range(len(closes))
            ]
        if kind == "rsi_bb":
            # v1.5.0 YT2: enter when RSI oversold AND close at/below
            # the lower Bollinger band; exit at the middle band (or RSI
            # overbought). Confirmation-candle state machine.
            from data_engine.quant.bands import bollinger as _bb

            rsi_period = int(params.get("rsi_period", 14))
            oversold = float(params.get("oversold", 25.0))
            overbought = float(params.get("overbought", 70.0))
            bb_period = int(params.get("bb_period", 20))
            bb_std = float(params.get("bb_std", 2.0))
            rsi = _rsi_series(closes, rsi_period)
            bands = _bb(closes, bb_period, bb_std)
            lower = bands["lower"]
            middle = bands["middle"]
            positions = [0] * len(closes)
            held = 0
            for i in range(len(closes)):
                r = rsi[i]
                if held == 0:
                    if (
                        r is not None
                        and r < oversold
                        and lower[i] is not None
                        and closes[i] <= lower[i]
                    ):
                        held = 1
                else:
                    if (
                        middle[i] is not None
                        and closes[i] >= middle[i]
                    ) or (r is not None and r > overbought):
                        held = 0
                positions[i] = held
            return positions
        if kind == "vwap_reversion":
            # v1.5.0 YT3: fade a stretched distance below rolling
            # VWAP with an RSI extreme; exit back at VWAP.
            from data_engine.quant.bands import rolling_vwap as _rvwap

            vwap_window = int(params.get("vwap_window", 30))
            deviation_bps = float(params.get("deviation_bps", 150.0))
            rsi_period = int(params.get("rsi_period", 7))
            rsi_low = float(params.get("rsi_low", 30.0))
            highs = [float(b["high"]) for b in bars]
            lows = [float(b["low"]) for b in bars]
            vols = [b.get("volume") for b in bars]
            if any(v is None for v in vols):
                raise LabError(
                    "vwap_reversion requires volume data (bars without "
                    "volume are refused — fail closed)"
                )
            vols = [float(v) for v in vols]
            vwap = _rvwap(highs, lows, closes, vols, vwap_window)
            rsi = _rsi_series(closes, rsi_period)
            threshold = 1.0 - deviation_bps / 10_000.0
            positions = [0] * len(closes)
            held = 0
            for i in range(len(closes)):
                v = vwap[i]
                r = rsi[i]
                if held == 0:
                    if (
                        v is not None
                        and closes[i] <= v * threshold
                        and r is not None
                        and r < rsi_low
                    ):
                        held = 1
                elif v is not None and closes[i] >= v:
                    held = 0
                positions[i] = held
            return positions
        if kind == "supertrend_follow":
            # v1.5.0 YT4: Supertrend direction flip gated by ADX
            # trend strength.
            from data_engine.quant.trend_indicators import adx as _adx
            from data_engine.quant.trend_indicators import (
                supertrend as _st,
            )

            st_period = int(params.get("st_period", 10))
            st_mult = float(params.get("st_mult", 3.0))
            adx_period = int(params.get("adx_period", 14))
            adx_min = float(params.get("adx_min", 20.0))
            highs = [float(b["high"]) for b in bars]
            lows = [float(b["low"]) for b in bars]
            st = _st(highs, lows, closes, st_period, st_mult)
            adx_series = _adx(highs, lows, closes, adx_period)["adx"]
            return [
                1
                if (
                    st["direction"][i] == 1
                    and adx_series[i] is not None
                    and adx_series[i] >= adx_min
                )
                else 0
                for i in range(len(closes))
            ]
        if kind == "orb_breakout":
            # v1.5.0 YT5: opening-range breakout per UTC day with a
            # volume confirmation. NOTE: the day's opening range is
            # measured from the first in-window bars of that UTC day
            # (the lab evaluates the trailing window only).
            range_bars = int(params.get("range_bars", 15))
            vol_factor = float(params.get("vol_factor", 1.2))
            vol_period = int(params.get("vol_period", 20))
            vols = [b.get("volume") for b in bars]
            if any(v is None for v in vols):
                raise LabError(
                    "orb_breakout requires volume data (bars without "
                    "volume are refused — fail closed)"
                )
            vols = [float(v) for v in vols]
            days: List[str] = []
            for b in bars:
                try:
                    days.append(_parse_ts(b["ts"]).strftime("%Y-%m-%d"))
                except LabError:
                    days.append("")
            positions = [0] * len(closes)
            held = 0
            current_day: Optional[str] = None
            day_start = 0
            range_high: Optional[float] = None
            range_low: Optional[float] = None
            vol_sma: Optional[float] = None
            for i in range(len(closes)):
                if days[i] != current_day:
                    current_day = days[i]
                    day_start = i
                    held = 0
                    window = [
                        j
                        for j in range(i, min(i + range_bars, len(closes)))
                        if days[j] == current_day
                    ]
                    if len(window) >= 1:
                        range_high = max(
                            float(bars[j]["high"]) for j in window
                        )
                        range_low = min(
                            float(bars[j]["low"]) for j in window
                        )
                    vol_sma = None
                if i >= vol_period - 1:
                    vol_sma = sum(vols[i - vol_period + 1: i + 1]) / vol_period
                # PIT discipline: entries only AFTER the opening range
                # has fully formed (no look-ahead into the range bars)
                range_complete = (i - day_start) >= (range_bars - 1)
                if (
                    held == 0
                    and range_complete
                    and range_high is not None
                    and vol_sma
                    and vol_sma > 0
                    and closes[i] > range_high
                    and vols[i] >= vol_factor * vol_sma
                ):
                    held = 1
                elif held == 1 and range_low is not None and closes[i] < range_low:
                    held = 0
                positions[i] = held
            return positions
        raise LabError(
            f"unknown strategy kind {kind!r} (kinds: {sorted(_KINDS)})"
        )

    def validate_params(self, kind: str, params: Mapping[str, Any]) -> Dict[str, Any]:
        """Whitelist + bound-check params (fail closed).

        v1.5.0: params listed in ``_FLOAT_PARAM_BOUNDS`` accept ints OR
        finite floats; all other params remain integer-only (the
        v1.1.0 contract is unchanged for the four original kinds).
        """
        if kind not in _KINDS:
            raise LabError(
                f"unknown strategy kind {kind!r} (kinds: {sorted(_KINDS)})"
            )
        if not isinstance(params, Mapping):
            raise LabError("params must be a JSON object")
        clean: Dict[str, Any] = {}
        int_bounds = _PARAM_BOUNDS[kind]
        float_bounds = _FLOAT_PARAM_BOUNDS.get(kind, {})
        for name, (low, high) in int_bounds.items():
            raw = params.get(name)
            if raw is None:
                continue
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise LabError(f"param {name} must be a number")
            value = int(raw)
            if value != raw:
                raise LabError(f"param {name} must be an integer")
            if not low <= value <= high:
                raise LabError(
                    f"param {name}={value} outside [{low}, {high}]"
                )
            clean[name] = value
        for name, (low, high) in float_bounds.items():
            raw = params.get(name)
            if raw is None:
                continue
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise LabError(f"param {name} must be a number")
            value = float(raw)
            if not math.isfinite(value):
                raise LabError(f"param {name} must be finite")
            if not low <= value <= high:
                raise LabError(
                    f"param {name}={value} outside [{low}, {high}]"
                )
            clean[name] = value
        unknown = set(params) - (set(int_bounds) | set(float_bounds))
        if unknown:
            raise LabError(
                f"unknown params for {kind}: {sorted(unknown)} "
                f"(allowed: {sorted(set(int_bounds) | set(float_bounds))})"
            )
        if kind == "ema_cross":
            fast = clean.get("fast", 12)
            slow = clean.get("slow", 26)
            if fast >= slow:
                raise LabError("ema_cross requires fast < slow")
        if kind == "ema_scalp":
            fast = clean.get("fast", 9)
            slow = clean.get("slow", 21)
            if fast >= slow:
                raise LabError("ema_scalp requires fast < slow")
        return clean

    def run(
        self,
        kind: str,
        params: Dict[str, Any],
        bars: List[dict],
        *,
        costs: Optional[Mapping[str, float]] = None,
    ) -> Dict[str, Any]:
        """Run + aggregate; returns objective metrics (no claims).

        v1.5.0: pass ``costs={"fee_bps": .., "slippage_bps": ..}``
        (per SIDE) to get net-of-cost metrics. With costs, the headline
        ``total_return_pct`` is the NET figure and the gross figure is
        reported alongside (never silently swapped). Without costs the
        v1.1.0 behaviour (costs not modeled) is preserved exactly.
        """
        if len(bars) < MIN_BARS_FOR_BACKTEST:
            raise LabError(
                f"backtest needs at least {MIN_BARS_FOR_BACKTEST} bars "
                f"for the symbol (have {len(bars)}); upload history "
                "first via POST /api/lab/bars"
            )
        if costs is not None:
            per_side_bps = float(costs.get("fee_bps", 0.0)) + float(
                costs.get("slippage_bps", 0.0)
            )
            if not math.isfinite(per_side_bps) or per_side_bps < 0:
                raise LabError("costs must be finite non-negative bps")
        else:
            per_side_bps = 0.0
        positions = self.positions(kind, params, bars)
        closes = [float(b["close"]) for b in bars]
        equity = 1.0
        gross_equity = 1.0
        curve = [1.0]
        entry: Optional[float] = None
        trades = 0
        wins = 0
        gross_wins = 0
        for i in range(len(bars)):
            if positions[i] == 1 and entry is None:
                entry = closes[i]
            elif positions[i] == 0 and entry is not None:
                round_trip = closes[i] / entry - 1.0
                net_round_trip = round_trip - 2.0 * per_side_bps / 10_000.0
                equity *= 1.0 + net_round_trip
                gross_equity *= 1.0 + round_trip
                curve.append(equity)
                trades += 1
                if round_trip > 0:
                    gross_wins += 1
                if net_round_trip > 0:
                    wins += 1
                entry = None
        if entry is not None:
            # honest mark-to-market close at the last bar
            round_trip = closes[-1] / entry - 1.0
            net_round_trip = round_trip - 2.0 * per_side_bps / 10_000.0
            equity *= 1.0 + net_round_trip
            gross_equity *= 1.0 + round_trip
            curve.append(equity)
            trades += 1
            if round_trip > 0:
                gross_wins += 1
            if net_round_trip > 0:
                wins += 1
            entry = None
        peak = 1.0
        max_dd = 0.0
        for point in curve:
            peak = max(peak, point)
            if peak > 0:
                max_dd = max(max_dd, (peak - point) / peak)
        total_return = equity - 1.0
        result: Dict[str, Any] = {
            "bars_tested": len(bars),
            "trades": trades,
            "total_return_pct": round(total_return * 100.0, 6),
            "max_drawdown_pct": round(max_dd * 100.0, 6),
            "win_rate_pct": round((wins / trades * 100.0) if trades else 0.0, 4),
        }
        if costs is not None:
            result.update(
                {
                    "gross_total_return_pct": round(
                        (gross_equity - 1.0) * 100.0, 6
                    ),
                    "net_total_return_pct": round(total_return * 100.0, 6),
                    "gross_win_rate_pct": round(
                        (gross_wins / trades * 100.0) if trades else 0.0, 4
                    ),
                    "fee_bps_per_side": float(costs.get("fee_bps", 0.0)),
                    "slippage_bps_per_side": float(
                        costs.get("slippage_bps", 0.0)
                    ),
                    "cost_drag_pct": round(
                        (gross_equity - equity) * 100.0, 6
                    ),
                    "runner": "lab_backtester_v1.5 (long/flat, close "
                              "fills, fees+slippage modeled)",
                }
            )
        else:
            result[
                "runner"
            ] = "lab_backtester_v1 (long/flat, close fills, " "costs NOT modeled — full strategy/backtest.py " "engine models commissions+slippage)"
        return result


# ---------------------------------------------------------------------------
# LabManager — durable driver of the G6 activation gate
# ---------------------------------------------------------------------------


class LabManager:
    """Durable, fail-closed driver around the EXISTING
    StrategyActivationGate (G6): create -> backtest -> paper window ->
    explicit confirm. All state mirrors to ``strategies.json``
    (atomic) and is REPLAYED through the gate on boot so the pipeline
    survives restarts. Activation is PAPER-EVALUATION-ONLY — this
    module cannot authorize live trading and never tries."""

    def __init__(
        self,
        state_dir: Path | str,
        bar_store: BarStore,
        *,
        gate: Optional[StrategyActivationGate] = None,
        is_halted: Optional[Callable[[], bool]] = None,
    ) -> None:
        self._dir = Path(state_dir)
        self._store_path = self._dir / "strategies.json"
        self._bars = bar_store
        self._gate = gate or StrategyActivationGate(LedgerFamilyLazy().family)
        self._is_halted = is_halted or (lambda: False)
        self._runner = LabBacktester()
        self._lock = threading.Lock()
        self._paper_meta: Dict[str, dict] = {}
        # v1.5.0: confidence gate (>=60% bullish/bearish confirmation)
        # and the PAPER-ONLY rapid scalper burst journal. Imported
        # lazily to keep the module import graph acyclic.
        from data_engine.runtime.confidence import ConfidenceGate
        from data_engine.runtime.rapid_scalper import RapidScalper

        self._confidence = ConfidenceGate(
            position_fn=self._runner.positions
        )
        self._rapid = RapidScalper()
        # v1.1.0: the AssistantEngine is attached AFTER construction by
        # the serve wiring (it needs the trade ledger + registry +
        # health provider that the monitoring API also uses). None =
        # the assistant route answers 503 fail-closed.
        self.assistant: Optional[Any] = None
        self._load_or_restore()

    @staticmethod
    def _guarded(fn, *args, **kwargs):
        """Run a gate call, translating StrategyActivationError into
        LabError so HTTP surfaces answer 400 with the gate's honest
        refusal message (never a 500)."""
        try:
            return fn(*args, **kwargs)
        except StrategyActivationError as exc:
            raise LabError(f"strategy gate refused: {exc}") from exc

    # -- persistence ---------------------------------------------------------

    def _durable(self) -> dict:
        with self._lock:
            payload = _read_json(self._store_path, None)
        if (
            isinstance(payload, dict)
            and isinstance(payload.get("strategies"), dict)
        ):
            return payload
        return {"version": 1, "strategies": {}}

    def _persist(self, snapshot: dict, spec: dict, meta: dict) -> None:
        durable = self._durable()
        strategies = durable["strategies"]
        strategies[spec["submission_id"]] = {
            "status": snapshot,
            "spec": spec,
            "paper": meta,
        }
        if len(strategies) > MAX_STRATEGIES:
            ordered = sorted(
                strategies.items(),
                key=lambda kv: kv[1]["spec"].get("created_at", ""),
            )
            for stale, _ in ordered[: len(strategies) - MAX_STRATEGIES]:
                del strategies[stale]
        with self._lock:
            _atomic_write_json(self._store_path, durable)

    def _paper_path(self, submission_id: str) -> Path:
        safe = _SLUG_RE.sub("_", submission_id)
        return self._dir / f"paper-{safe}.jsonl"

    def _append_paper_event(self, submission_id: str, event: dict) -> None:
        path = self._paper_path(submission_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        if path.exists():
            with path.open("r", encoding="utf-8") as fh:
                count = sum(1 for _ in fh)
        if count >= MAX_PAPER_EVENTS:
            raise LabError(
                "paper journal is full (delete the strategy or finish "
                "the validation cycle)"
            )
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")

    def _read_paper_events(self, submission_id: str) -> List[dict]:
        path = self._paper_path(submission_id)
        if not path.exists():
            return []
        events = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except ValueError:
                continue  # corrupt line tolerance (ledger posture)
            if isinstance(parsed, dict):
                events.append(parsed)
        return events

    def _load_or_restore(self) -> None:
        """Replay durable records through the gate so the pipeline is
        identical after a restart (the gate is the single truth in
        memory; the JSON mirror is the durable copy)."""
        durable = self._durable()
        for submission_id, entry in durable["strategies"].items():
            spec = entry.get("spec") or {}
            status = entry.get("status") or {}
            meta = entry.get("paper") or {}
            try:
                self._gate.submit(
                    submitted_by=str(
                        spec.get("submitted_by", "owner-lab")
                    ),
                    label=str(spec.get("label", submission_id)),
                    structured_spec=dict(spec.get("structured_spec") or {}),
                    free_text=str(spec.get("free_text", "")),
                    submitted_at=_parse_ts(spec["created_at"]) if spec.get("created_at") else None,
                    submission_id=submission_id,
                )
            except StrategyActivationError:
                continue
            bt = status.get("backtest")
            if bt:
                try:
                    self._gate.record_backtest(
                        submission_id,
                        BacktestEvidence(
                            backtest_id=str(bt["backtest_id"]),
                            ran_at=_parse_ts(bt["ran_at"]),
                            bars_tested=int(bt["bars_tested"]),
                            trades=int(bt["trades"]),
                            total_return=Decimal(str(bt["total_return"])),
                            max_drawdown=Decimal(str(bt["max_drawdown"])),
                            engine_version=str(bt.get("engine_version", __version__)),
                        ),
                    )
                except (StrategyActivationError, KeyError, ValueError, ArithmeticError):
                    continue
            window_end = status.get("validation_window_end")
            if window_end and status.get("backtest"):
                window_start = (meta or {}).get("window_start")
                try:
                    end_dt = _parse_ts(window_end)
                    start_dt = (
                        _parse_ts(window_start) if window_start else end_dt
                    )
                    days = max(1, (end_dt - start_dt).days)
                    self._gate.schedule_validation(
                        submission_id, cycle_days=days, now=start_dt
                    )
                except (StrategyActivationError, ValueError):
                    continue
            validation = status.get("validation")
            if validation and window_end:
                try:
                    self._gate.record_validation(
                        submission_id,
                        ValidationEvidence(
                            validation_id=str(validation["validation_id"]),
                            window_start=_parse_ts(validation["window_start"]),
                            window_end=_parse_ts(validation["window_end"]),
                            cycles_completed=int(validation["cycles_completed"]),
                            paper_trades=int(validation["paper_trades"]),
                            anomalies=int(validation["anomalies"]),
                        ),
                        now=_parse_ts(window_end),
                    )
                except (StrategyActivationError, KeyError, ValueError):
                    continue
            decision = status.get("decision")
            if decision and status.get("state") == "ACTIVATED":
                try:
                    self._gate.activate(
                        submission_id,
                        ActivationDecision.yes(
                            decided_by=str(decision.get("decided_by", "owner")),
                            note=str(decision.get("note", "restored")),
                        ),
                    )
                except StrategyActivationError:
                    continue
            self._paper_meta[submission_id] = dict(meta)

    # -- owner operations ------------------------------------------------------

    def create(
        self,
        *,
        label: str,
        symbol: str,
        kind: str,
        params: Optional[Mapping[str, Any]],
        submitted_by: str = "owner-lab",
    ) -> dict:
        label = (label or "").strip()
        if not label:
            raise LabError("a strategy label is required")
        if len(label) > 80:
            raise LabError("label too long (max 80 chars)")
        clean_params = self._runner.validate_params(kind, dict(params or {}))
        # symbol must be a legal BarStore symbol (the strategy backtests
        # and paper-evaluates THAT symbol's bars)
        self._bars._path(symbol)  # raises LabError on bad symbols
        durable = self._durable()
        if len(durable["strategies"]) >= MAX_STRATEGIES:
            raise LabError(
                f"strategy table full (max {MAX_STRATEGIES}); remove old "
                "strategies first"
            )
        submission_id = f"lab-{_utc_now().strftime('%Y%m%d%H%M%S')}-{len(durable['strategies']) + 1:03d}"
        structured_spec = {
            "symbol": symbol,
            "kind": kind,
            "params": clean_params,
            "runner": "lab_backtester_v1",
        }
        self._guarded(
            self._gate.submit,
            submitted_by=submitted_by or "owner-lab",
            label=f"{label} [{symbol}]",
            structured_spec=structured_spec,
            free_text=f"{kind} strategy on {symbol} (owner lab form)",
            submission_id=submission_id,
        )
        now_iso = _utc_now().isoformat()
        spec = {
            "submission_id": submission_id,
            "created_at": now_iso,
            "submitted_by": submitted_by or "owner-lab",
            "label": f"{label} [{symbol}]",
            "structured_spec": structured_spec,
            "free_text": f"{kind} strategy on {symbol} (owner lab form)",
        }
        snapshot = self._guarded(self._gate.status, submission_id)
        self._persist(snapshot, spec, {})
        return snapshot

    def run_backtest(self, submission_id: str, *, now: Optional[datetime] = None) -> dict:
        symbol, kind, params = self._spec_of(submission_id)
        bars = self._bars.bars(symbol)
        # v1.5.0: manager-level backtests are NET OF COSTS by default
        # (conservative per-family assumptions; honest headline).
        metrics = self._runner.run(
            kind, params, bars, costs=default_cost_bps(symbol)
        )
        moment = now or _utc_now()
        self._guarded(
            self._gate.record_backtest,
            submission_id,
            BacktestEvidence(
                backtest_id=f"bt-{submission_id}-{moment.strftime('%Y%m%dT%H%M%S')}",
                ran_at=moment,
                bars_tested=metrics["bars_tested"],
                trades=metrics["trades"],
                total_return=Decimal(str(metrics["total_return_pct"])),
                max_drawdown=Decimal(str(metrics["max_drawdown_pct"])),
                engine_version=__version__,
            ),
        )
        durable = self._durable()
        entry = durable["strategies"].get(submission_id) or {}
        self._persist(
            self._guarded(self._gate.status, submission_id),
            entry.get("spec") or {},
            self._paper_meta.get(submission_id, {}),
        )
        status = self._guarded(self._gate.status, submission_id)
        status["backtest_metrics"] = metrics
        return status

    def paper_start(
        self, submission_id: str, *, cycle_days: int = VALIDATION_CYCLE_DAYS
    ) -> dict:
        if isinstance(cycle_days, bool) or not isinstance(cycle_days, int):
            raise LabError("cycle_days must be an integer")
        if cycle_days < 1:
            raise LabError("cycle_days must be >= 1 (fail closed)")
        window_end = self._guarded(
            self._gate.schedule_validation,
            submission_id, cycle_days=cycle_days
        )
        start = _utc_now()
        self._paper_meta[submission_id] = {
            "window_start": start.isoformat(),
            "window_end": window_end.isoformat(),
            "cycle_days": cycle_days,
        }
        # fresh journal for the fresh window (honest: previous window's
        # events are NOT mixed into the new cycle)
        path = self._paper_path(submission_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        header = {
            "event": "WINDOW_START",
            "submission_id": submission_id,
            "window_start": start.isoformat(),
            "window_end": window_end.isoformat(),
            "cycle_days": cycle_days,
        }
        path.write_text(json.dumps(header, sort_keys=True) + "\n", encoding="utf-8")
        durable = self._durable()
        entry = durable["strategies"].get(submission_id) or {}
        self._persist(
            self._guarded(self._gate.status, submission_id),
            entry.get("spec") or {},
            self._paper_meta[submission_id],
        )
        return self._gate.status(submission_id)

    def observe_symbol_update(self, symbol: str) -> Dict[str, Any]:
        """Forward paper evaluation: called after new bars land for a
        symbol. For every strategy in VALIDATION_SCHEDULED on that
        symbol, recompute the long/flat state over the latest window
        and journal POSITION FLIPS as hypothetical paper events.
        Paused entirely while the kill switch is ACTIVE (a standing
        STOP is a stop for the whole lab).

        v1.5.0 additions (all journal-only, never orders):
        - marks any pending RapidScalper burst against the actual next
          closed candle (PENDING_MARK -> MARKED with net PnL);
        - after a CONFIRMED >=60% ConfidenceGate assessment on the
          closed confirmation candle, arms a new one-fill-per-second
          paper burst (subject to cooldown + cumulative loss cap +
          kill switch)."""
        evaluated: List[str] = []
        bursts_planned: List[str] = []
        bursts_marked: List[str] = []
        if self._is_halted():
            return {
                "evaluated": [],
                "halted": True,
                "bursts_planned": [],
                "bursts_marked": [],
            }
        durable = self._durable()
        for submission_id, entry in durable["strategies"].items():
            status = entry.get("status") or {}
            spec = entry.get("spec") or {}
            structured = spec.get("structured_spec") or {}
            if (
                status.get("state") != "VALIDATION_SCHEDULED"
                or structured.get("symbol") != symbol
            ):
                continue
            kind = str(structured.get("kind"))
            params = dict(structured.get("params") or {})
            bars = self._bars.bars(symbol, limit=400)
            if len(bars) < MIN_BARS_FOR_BACKTEST:
                continue
            try:
                positions = self._runner.positions(kind, params, bars)
            except LabError:
                continue
            meta = self._paper_meta.setdefault(submission_id, {})

            # -- 1) mark a pending burst against THIS closed candle ----
            pending = meta.get("pending_burst")
            if (
                isinstance(pending, dict)
                and (pending.get("confirmation_candle") or {}).get("ts")
                != bars[-1]["ts"]
            ):
                try:
                    marked = self._rapid.mark_burst(
                        pending, next_close=float(bars[-1]["close"])
                    )
                    self._append_paper_event(submission_id, marked)
                    bursts_marked.append(submission_id)
                    cumulative = float(
                        meta.get("burst_cumulative_bps", 0.0)
                    ) + float(marked["net_pnl_bps"])
                    meta["burst_cumulative_bps"] = cumulative
                    if (
                        cumulative
                        <= -abs(
                            float(self._rapid.config["burst_loss_limit_bps"])
                        )
                    ):
                        meta["bursts_disarmed"] = True
                except (LabError, ValueError):
                    pass  # journal full / degenerate mark — skip honestly
                finally:
                    meta.pop("pending_burst", None)

            # -- 2) position-flip journaling (unchanged semantics) -----
            previous = meta.get("last_position")
            current = positions[-1] if positions else 0
            if previous is None:
                previous = 0
            if current != previous:
                self._append_paper_event(
                    submission_id,
                    {
                        "event": "ENTER_LONG" if current == 1 else "EXIT_LONG",
                        "ts": bars[-1]["ts"],
                        "price": bars[-1]["close"],
                        "symbol": symbol,
                    },
                )
                meta["last_position"] = current

            # -- 3) confidence gate + one-fill-per-second paper burst --
            try:
                if (
                    len(bars) >= self._confidence.MIN_BARS
                    and not meta.get("bursts_disarmed")
                ):
                    assessment = self._confidence.assess(
                        kind, params, bars, positions=positions
                    )
                    if assessment["confirmed"]:
                        bars_since = None
                        if meta.get("last_burst_bars"):
                            bars_since = len(bars) - int(
                                meta["last_burst_bars"]
                            )
                        admission = self._rapid.burst_allowed(
                            meta=meta,
                            bars_since_last_burst=bars_since,
                            cooldown_bars=int(
                                self._rapid.config["cooldown_bars"]
                            ),
                            cumulative_bps=float(
                                meta.get("burst_cumulative_bps", 0.0)
                            ),
                            loss_limit_bps=float(
                                self._rapid.config["burst_loss_limit_bps"]
                            ),
                        )
                        if admission["allowed"]:
                            burst = self._rapid.plan_burst(
                                submission_id=submission_id,
                                symbol=symbol,
                                direction=assessment["direction"],
                                confidence_pct=assessment["confidence_pct"],
                                confirmation_close=float(bars[-1]["close"]),
                                confirmation_ts=bars[-1]["ts"],
                            )
                            self._append_paper_event(submission_id, burst)
                            meta["pending_burst"] = burst
                            meta["last_burst_bars"] = len(bars)
                            bursts_planned.append(submission_id)
            except LabError:
                pass  # assessment refused (e.g. bars) — skip honestly
            evaluated.append(submission_id)
        return {
            "evaluated": evaluated,
            "halted": False,
            "bursts_planned": bursts_planned,
            "bursts_marked": bursts_marked,
        }

    def paper_finish(self, submission_id: str, *, now: Optional[datetime] = None) -> dict:
        meta = self._paper_meta.get(submission_id) or {}
        window_start = meta.get("window_start")
        if not window_start:
            raise LabError(
                "no paper window was started for this strategy "
                "(call paper/start first — fail closed)"
            )
        events = self._read_paper_events(submission_id)
        enters = [e for e in events if e.get("event") == "ENTER_LONG"]
        moment = now or _utc_now()
        start_dt = _parse_ts(window_start)
        evidence = ValidationEvidence(
            validation_id=f"val-{submission_id}",
            window_start=start_dt,
            window_end=moment,
            cycles_completed=1,
            paper_trades=len(enters),
            anomalies=0,
        )
        # the GATE enforces the window (refuses evidence before it
        # elapses — fail closed, journaled)
        self._guarded(
            self._gate.record_validation, submission_id, evidence, now=moment
        )
        durable = self._durable()
        entry = durable["strategies"].get(submission_id) or {}
        self._persist(
            self._guarded(self._gate.status, submission_id),
            entry.get("spec") or {},
            meta,
        )
        status = self._guarded(self._gate.status, submission_id)
        status["paper_summary"] = {
            "paper_trades": len(enters),
            "events": len(events),
            "note": "hypothetical fills at bar close from YOUR uploaded "
                    "bars; no orders were sent anywhere",
        }
        return status

    def confirm(
        self,
        submission_id: str,
        *,
        confirm: str,
        decided_by: str = "owner",
        note: str = "",
    ) -> dict:
        answer = str(confirm or "").strip().upper()
        if answer == "YES":
            decision = ActivationDecision.yes(
                decided_by=decided_by or "owner", note=note or ""
            )
        elif answer in ("", "NO", "N"):
            decision = ActivationDecision.no(
                decided_by=decided_by or "owner",
                note=note or "no explicit YES — stays INACTIVE",
            )
        else:
            raise LabError(
                'confirm must be exactly "YES" to activate; anything '
                "else is treated as NO (fail closed)"
            )
        self._guarded(self._gate.activate, submission_id, decision)
        durable = self._durable()
        entry = durable["strategies"].get(submission_id) or {}
        self._persist(
            self._guarded(self._gate.status, submission_id),
            entry.get("spec") or {},
            self._paper_meta.get(submission_id, {}),
        )
        status = self._guarded(self._gate.status, submission_id)
        status["governance"] = (
            "PAPER_EVALUATION_ONLY — activation never authorizes live "
            "trading (LIVE_AUTHORIZATION=NOT_AUTHORIZED)"
        )
        return status

    def list(self) -> List[dict]:
        durable = self._durable()
        rows = []
        for submission_id, entry in durable["strategies"].items():
            status = dict(entry.get("status") or {})
            status["symbol"] = (entry.get("spec", {}).get("structured_spec") or {}).get("symbol")
            status["kind"] = (entry.get("spec", {}).get("structured_spec") or {}).get("kind")
            status["paper"] = {
                k: v
                for k, v in (entry.get("paper") or {}).items()
                if k != "last_position"
            }
            rows.append(status)
        rows.sort(key=lambda r: r.get("submission_id", ""), reverse=True)
        return rows

    def _spec_of(self, submission_id: str) -> tuple:
        durable = self._durable()
        entry = durable["strategies"].get(submission_id)
        if not entry:
            raise LabError(f"unknown strategy {submission_id!r}")
        structured = entry["spec"]["structured_spec"]
        return (
            str(structured["symbol"]),
            str(structured["kind"]),
            dict(structured.get("params") or {}),
        )

    # ------------------------------------------------------------------
    # v1.5.0: AUTO-SCAN + preset bootstrap
    # ------------------------------------------------------------------

    _AUTO_SCAN_GRID: Dict[str, List[Dict[str, Any]]] = {
        "ema_trend": [{"period": p} for p in (10, 20, 50, 100, 200)],
        "ema_cross": [
            {"fast": f, "slow": s}
            for (f, s) in ((9, 21), (12, 26), (20, 50), (50, 200))
        ],
        "rsi_reversal": [
            {"period": p, "oversold": o, "overbought": ob}
            for (p, o, ob) in ((14, 30, 70), (7, 25, 75), (2, 10, 90))
        ],
        "breakout": [{"lookback": l} for l in (10, 20, 50, 100)],
        "ema_scalp": [
            {"fast": 9, "slow": 21, "trend": 200},
            {"fast": 12, "slow": 26, "trend": 200},
            {"fast": 8, "slow": 20, "trend": 100},
        ],
        "rsi_bb": [
            {"rsi_period": 14, "oversold": 25, "overbought": 70,
             "bb_period": 20, "bb_std": 2.0},
            {"rsi_period": 7, "oversold": 20, "overbought": 75,
             "bb_period": 20, "bb_std": 2.5},
        ],
        "vwap_reversion": [
            {"vwap_window": 30, "deviation_bps": 150, "rsi_period": 7,
             "rsi_low": 30},
            {"vwap_window": 60, "deviation_bps": 100, "rsi_period": 14,
             "rsi_low": 35},
        ],
        "supertrend_follow": [
            {"st_period": 10, "st_mult": 3.0, "adx_period": 14,
             "adx_min": 20},
            {"st_period": 7, "st_mult": 2.0, "adx_period": 14,
             "adx_min": 15},
        ],
        "orb_breakout": [
            {"range_bars": 15, "vol_factor": 1.2, "vol_period": 20},
            {"range_bars": 30, "vol_factor": 1.5, "vol_period": 30},
        ],
    }

    def auto_scan(
        self,
        symbol: str,
        *,
        top_n: int = 3,
        submitted_by: str = "auto-scan",
    ) -> dict:
        """v1.5.0 AUTO-SCAN: deterministic parameter scan over all
        nine lab kinds with a 70/30 in-sample/out-of-sample split,
        NET OF conservative costs. Survivors (>=3 IS trades, positive
        OOS net return) are ranked and the top ``top_n`` become
        ORDINARY G6 submissions the owner still has to confirm —
        auto-scan never activates anything by itself."""
        if isinstance(top_n, bool) or not isinstance(top_n, int):
            raise LabError("top_n must be an integer")
        if not 1 <= top_n <= 10:
            raise LabError("top_n must be within [1, 10] (fail closed)")
        bars = self._bars.bars(symbol)
        if len(bars) < 120:
            raise LabError(
                f"auto-scan needs at least 120 bars for {symbol!r} "
                f"(have {len(bars)}); upload or import history first"
            )
        split = max(MIN_BARS_FOR_BACKTEST, int(len(bars) * 0.7))
        is_bars = bars[:split]
        oos_bars = bars[split:]
        costs = default_cost_bps(symbol)
        candidates: List[dict] = []
        tested = 0
        for kind, grid in self._AUTO_SCAN_GRID.items():
            for params in grid:
                tested += 1
                try:
                    is_metrics = self._runner.run(
                        kind, params, is_bars, costs=costs
                    )
                except LabError:
                    continue
                if is_metrics["trades"] < 3:
                    continue
                try:
                    oos_metrics = self._runner.run(
                        kind, params, oos_bars, costs=costs
                    )
                except LabError:
                    continue
                if oos_metrics["trades"] < 1:
                    continue
                score = (
                    oos_metrics["total_return_pct"]
                    - 0.5 * oos_metrics["max_drawdown_pct"]
                )
                candidates.append(
                    {
                        "kind": kind,
                        "params": params,
                        "is": {
                            "trades": is_metrics["trades"],
                            "net_return_pct": is_metrics[
                                "total_return_pct"
                            ],
                        },
                        "oos": {
                            "trades": oos_metrics["trades"],
                            "net_return_pct": oos_metrics[
                                "total_return_pct"
                            ],
                            "max_drawdown_pct": oos_metrics[
                                "max_drawdown_pct"
                            ],
                        },
                        "score": round(score, 6),
                    }
                )
        survivors = [
            c
            for c in candidates
            if c["oos"]["net_return_pct"] > 0
        ]
        survivors.sort(
            key=lambda c: (-c["score"], c["kind"], json.dumps(c["params"], sort_keys=True))
        )
        created: List[dict] = []
        for candidate in survivors[:top_n]:
            try:
                snapshot = self.create(
                    label=f"AUTO-SCAN {candidate['kind']}",
                    symbol=symbol,
                    kind=candidate["kind"],
                    params=candidate["params"],
                    submitted_by=submitted_by,
                )
                created.append(
                    {
                        "submission_id": snapshot.get("submission_id"),
                        "kind": candidate["kind"],
                        "params": candidate["params"],
                    }
                )
            except LabError:
                continue  # table full etc. — honest skip
        return {
            "symbol": symbol,
            "combinations_tested": tested,
            "candidates_found": len(candidates),
            "survivors": len(survivors),
            "created": created,
            "ranked": survivors[:10],
            "method": (
                "70/30 IS/OOS split, net of conservative costs; top "
                "survivors become ORDINARY submissions — owner YES "
                "still required (G6 unchanged)"
            ),
        }

    def bootstrap_default_strategies(
        self, symbol: str, *, submitted_by: str = "preset-bootstrap"
    ) -> dict:
        """v1.5.0: create the five TOP-5 YouTuber presets for a symbol
        (idempotent — existing labels are skipped), backtest them when
        enough bars exist, and open their 30-day paper windows so paper
        trading STARTS with them. Activation still needs the owner's
        explicit YES (G6 unchanged)."""
        from data_engine.runtime.presets import TOP5_YOUTUBER_PRESETS

        durable = self._durable()
        existing_labels = {
            (entry.get("spec") or {}).get("label", "")
            for entry in durable["strategies"].values()
        }
        created: List[str] = []
        for preset in TOP5_YOUTUBER_PRESETS:
            label = f"{preset['label']} [{symbol}]"
            if label in existing_labels:
                continue
            try:
                snapshot = self.create(
                    label=preset["label"],
                    symbol=symbol,
                    kind=preset["kind"],
                    params=preset["params"],
                    submitted_by=submitted_by,
                )
            except LabError:
                continue
            sid = snapshot.get("submission_id")
            if sid:
                created.append(sid)
        paper_started: List[str] = []
        bars_count = len(self._bars.bars(symbol))
        for sid in created:
            try:
                if bars_count >= MIN_BARS_FOR_BACKTEST:
                    self.run_backtest(sid)
                self.paper_start(sid)
                paper_started.append(sid)
            except LabError:
                continue
        return {
            "symbol": symbol,
            "presets_available": len(TOP5_YOUTUBER_PRESETS),
            "created": created,
            "paper_started": paper_started,
            "note": (
                "presets enter the SAME G6 pipeline; owner YES still "
                "required for activation"
            ),
        }


class LedgerFamilyLazy:
    """Deferred LedgerFamily construction (import cost only when the
    lab is actually wired; legacy unkeyed mode — the owner lab
    journals pipeline transitions to the in-memory decision ledger)."""

    def __init__(self) -> None:
        self._family: Any = None

    @property
    def family(self) -> Any:
        if self._family is None:
            from data_engine.runtime.ledgers import LedgerFamily

            self._family = LedgerFamily()
        return self._family


# ---------------------------------------------------------------------------
# PredictBaseline — statistical next-move research baseline
# ---------------------------------------------------------------------------


class PredictBaseline:
    """Momentum-vs-volatility next-move baseline.

    HONEST labeling: a statistical RESEARCH baseline (momentum scaled
    by realized volatility through a logistic squash), NOT a learned
    model, NOT investment advice, and it authorizes nothing. The
    engine's full prediction stack (data_engine.prediction.*) remains
    the governed research path."""

    LOOKBACK = 20
    MIN_BARS = 25

    def predict(self, bars: List[dict]) -> dict:
        if len(bars) < self.MIN_BARS:
            raise LabError(
                f"prediction needs at least {self.MIN_BARS} bars "
                f"(have {len(bars)}); upload history via POST /api/lab/bars"
            )
        closes = [float(b["close"]) for b in bars]
        lookback = self.LOOKBACK
        momentum = closes[-1] / closes[-1 - lookback] - 1.0
        returns = [
            math.log(closes[i] / closes[i - 1])
            for i in range(len(closes) - lookback, len(closes))
        ]
        mean = sum(returns) / len(returns)
        variance = sum((r - mean) ** 2 for r in returns) / max(1, len(returns) - 1)
        volatility = math.sqrt(variance)
        score = momentum / volatility if volatility > 0 else 0.0
        p_up = 1.0 / (1.0 + math.exp(-score))
        p_up = min(0.95, max(0.05, p_up))
        if p_up > 0.55:
            direction = "UP"
        elif p_up < 0.45:
            direction = "DOWN"
        else:
            direction = "FLAT"
        confidence = "low" if len(bars) < 100 else "medium"
        return {
            "direction": direction,
            "probability_up": round(p_up, 4),
            "momentum_pct": round(momentum * 100.0, 4),
            "volatility_pct": round(volatility * 100.0, 4),
            "expected_move_pct": round(momentum * 100.0, 4),
            "confidence": confidence,
            "bars_used": len(bars),
            "lookback": lookback,
            "disclaimer": (
                "research baseline only — statistical, not a learned "
                "model; NOT investment advice; predicts nothing about "
                "live trading (which stays NOT_AUTHORIZED)"
            ),
        }


# ---------------------------------------------------------------------------
# BrokerCatalog — the honest broker surface
# ---------------------------------------------------------------------------

_BROKER_ROWS = [
    {"id": "mt5_mock", "label": "MetaTrader 5 (mock adapter)",
     "mode": "SIMULATION", "note": "in-repo simulation adapter; the REAL MT5 demo probe is the operator step in deploy/ (Python 3.11-3.14 venv)"},
    {"id": "exness_mock", "label": "Exness (mock adapter)",
     "mode": "SIMULATION", "note": "in-repo simulation adapter used by the Exness demo market-data branch"},
    {"id": "binance_mock", "label": "Binance (mock adapter)",
     "mode": "SIMULATION", "note": "in-repo simulation adapter"},
    {"id": "bybit_mock", "label": "Bybit (mock adapter)",
     "mode": "SIMULATION", "note": "in-repo simulation adapter"},
    {"id": "bitget_mock", "label": "Bitget (mock adapter)",
     "mode": "SIMULATION", "note": "in-repo simulation adapter"},
    {"id": "xm_mock", "label": "XM (mock adapter)",
     "mode": "SIMULATION", "note": "in-repo simulation adapter"},
    {"id": "paper", "label": "Paper broker",
     "mode": "PAPER", "note": "internal paper execution gateway"},
]


class BrokerCatalog:
    """Static, honest broker surface: what ships, what mode it runs
    in, and the EXACT contract used to add a new broker (no live
    credentials are accepted through the monitoring API — live
    trading is not authorized; adapters are code, reviewed in git)."""

    def catalog(self) -> dict:
        return {
            "brokers": _BROKER_ROWS,
            "count": len(_BROKER_ROWS),
            "add_new_broker": {
                "contract": (
                    "implement the BrokerAdapter interface "
                    "(src/data_engine/brokers/interface.py) + register "
                    "capabilities (brokers/capabilities.py); ship it as "
                    "a reviewed git commit — credentials NEVER travel "
                    "through the monitoring API and live execution "
                    "stays NOT_AUTHORIZED"
                ),
                "interface": "src/data_engine/brokers/interface.py",
                "live_trading": "NOT_AUTHORIZED",
            },
        }


__all__ = [
    "AssistantEngine",
    "BarStore",
    "BrokerCatalog",
    "LabBacktester",
    "LabError",
    "LabManager",
    "PredictBaseline",
    "MAX_BARS_PER_REQUEST",
    "MAX_BARS_PER_SYMBOL",
    "MIN_BARS_FOR_BACKTEST",
    "validate_bar",
    "default_cost_bps",
]
