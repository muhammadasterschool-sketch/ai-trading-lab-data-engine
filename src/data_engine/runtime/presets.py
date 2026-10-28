"""v1.5.0 TOP-5 YouTuber strategy presets (M1 paper-ready).

Lives in ``runtime/`` (NOT the frozen ``strategy/`` domain) because
 these are OWNER-LAB preset definitions for the LabBacktester kinds —
 the runtime boundary (BUG-008) forbids runtime modules from
 importing the frozen strategy domain, and these presets never touch
 frozen models.

Owner mandate (2026-10-28): "top 5 strategy jo YouTubers use karte hai
woh from start daal do taake paper trading in strategies se start ho
aur ye 1 min ke timeframe mai trade le" — the five most-popularized
retail trading strategies on YouTube, encoded as DETERMINISTIC
long/flat lab kinds with confirmation-candle semantics (signal on the
CLOSED bar only), preloaded for every new symbol bootstrap.

HONEST notes:
- These are the classic retail formulations, popularized by trading
  YouTubers; popularity is NOT evidence of edge. Every preset goes
  through the SAME G6 gate (backtest -> 30-day paper window -> explicit
  owner YES) as any other strategy.
- All five default to the M1 (1-minute) timeframe and demand a
  CONFIRMATION CANDLE: the entry evaluates only on bar close, never
  intrabar.
- No preset can authorize live trading (LIVE_AUTHORIZATION stays
  NOT_AUTHORIZED); nothing here sends orders anywhere.
"""

from __future__ import annotations

from typing import Any, Dict, List

#: The five presets, in bootstrap order. ``params`` match the
#: LabBacktester kind signatures exactly (validated fail-closed).
TOP5_YOUTUBER_PRESETS: List[Dict[str, Any]] = [
    {
        "preset_id": "yt-ema-scalp",
        "kind": "ema_scalp",
        "label": "YT1 EMA 9/21 Scalp + 200 filter",
        "params": {"fast": 9, "slow": 21, "trend": 200},
        "timeframe": "M1",
        "origin": (
            "EMA-ribbon scalping as popularized by trading YouTubers: "
            "fast/slow EMA cross traded only in the direction of the "
            "200 EMA regime filter"
        ),
        "confirmation_candle": True,
    },
    {
        "preset_id": "yt-rsi-bb",
        "kind": "rsi_bb",
        "label": "YT2 RSI + Bollinger mean-reversion",
        "params": {
            "rsi_period": 14,
            "oversold": 25,
            "overbought": 70,
            "bb_period": 20,
            "bb_std": 2.0,
        },
        "timeframe": "M1",
        "origin": (
            "Bollinger-band mean-reversion with an RSI trigger, the "
            "'overbought/oversold' staple of retail YouTube channels"
        ),
        "confirmation_candle": True,
    },
    {
        "preset_id": "yt-vwap-reversion",
        "kind": "vwap_reversion",
        "label": "YT3 VWAP reversion scalp",
        "params": {
            "vwap_window": 30,
            "deviation_bps": 150,
            "rsi_period": 7,
            "rsi_low": 30,
        },
        "timeframe": "M1",
        "origin": (
            "'Fade the VWAP' intraday reversion: stretched distance "
            "from volume-weighted average price plus an RSI extreme"
        ),
        "confirmation_candle": True,
    },
    {
        "preset_id": "yt-supertrend",
        "kind": "supertrend_follow",
        "label": "YT4 Supertrend follow + ADX filter",
        "params": {
            "st_period": 10,
            "st_mult": 3.0,
            "adx_period": 14,
            "adx_min": 20,
        },
        "timeframe": "M1",
        "origin": (
            "Supertrend (ATR bands) with an ADX trend-strength filter — "
            "the single most-requested indicator on trading YouTube"
        ),
        "confirmation_candle": True,
    },
    {
        "preset_id": "yt-orb",
        "kind": "orb_breakout",
        "label": "YT5 Opening Range Breakout",
        "params": {"range_bars": 15, "vol_factor": 1.2, "vol_period": 20},
        "timeframe": "M1",
        "origin": (
            "Opening Range Breakout: trade the break of the session's "
            "first-15-minute range with a volume confirmation — the "
            "classic 'first 15 minutes' YouTube day-trade setup"
        ),
        "confirmation_candle": True,
    },
]

#: Kinds contributed by this preset pack (consumed by runtime/lab.py).
PRESET_KINDS: tuple = tuple(sorted({p["kind"] for p in TOP5_YOUTUBER_PRESETS}))


def presets_for_api() -> List[Dict[str, Any]]:
    """API-safe copy of the preset list (no shared mutable state)."""
    return [
        {
            "preset_id": p["preset_id"],
            "kind": p["kind"],
            "label": p["label"],
            "params": dict(p["params"]),
            "timeframe": p["timeframe"],
            "origin": p["origin"],
            "confirmation_candle": p["confirmation_candle"],
        }
        for p in TOP5_YOUTUBER_PRESETS
    ]


__all__ = ["TOP5_YOUTUBER_PRESETS", "PRESET_KINDS", "presets_for_api"]
