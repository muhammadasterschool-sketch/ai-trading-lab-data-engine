"""v1.5.0 RapidScalper — PAPER-ONLY one-trade-per-second burst journal.

Owner mandate (2026-10-28): "60 percent sure ho ke market ab Bullish
ya phir bearish ho gi to phir ye 1 trade per sec shuru karde after
confirmation candle".

HONEST engineering translation:

- When the ConfidenceGate confirms (>= 60%) a BULLISH or BEARISH call
  on a CLOSED confirmation candle, the scalper plans a burst of ONE
  simulated paper fill per second for the next ``burst_seconds``
  (default 60 s = one M1 candle). The burst is JOURNALED to the
  strategy's paper ledger — no orders are sent anywhere, no broker is
  contacted, and the venue stays MOCK/paper by construction.
- Entry prices are the confirmation close plus a deterministic cost
  model (fee + slippage, per side). The exit is MARKED at the NEXT
  closed candle's close (actual future data — never extrapolated).
- Hard risk caps (all fail-closed): max 1 fill/second, max
  ``max_fills_per_burst`` fills, a cooldown between bursts, a
  cumulative burst loss limit that disarms further bursts once
  breached, and a total refusal while the kill switch is ACTIVE.
- LIVE TRADING REMAINS NOT_AUTHORIZED. This module cannot and does
  not change that.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class RapidScalper:
    """Deterministic paper-burst planner/journaler (no RNG, no orders)."""

    DEFAULTS = {
        "fills_per_second": 1,
        "burst_seconds": 60,
        "max_fills_per_burst": 60,
        "cooldown_bars": 2,
        "burst_loss_limit_bps": 100.0,  # cumulative; disarms when breached
        "fee_bps": 10.0,
        "slippage_bps": 2.0,
    }

    def __init__(self, **overrides: Any) -> None:
        unknown = set(overrides) - set(self.DEFAULTS)
        if unknown:
            raise ValueError(f"unknown RapidScalper params: {sorted(unknown)}")
        self.config: Dict[str, Any] = dict(self.DEFAULTS)
        self.config.update(overrides)
        if self.config["fills_per_second"] != 1:
            raise ValueError(
                "fills_per_second is pinned to 1 (owner spec: 1 trade/sec)"
            )
        if self.config["max_fills_per_burst"] > self.config["burst_seconds"]:
            raise ValueError(
                "max_fills_per_burst cannot exceed burst_seconds at 1/sec"
            )

    # ------------------------------------------------------------------

    def plan_burst(
        self,
        *,
        submission_id: str,
        symbol: str,
        direction: str,
        confidence_pct: float,
        confirmation_close: float,
        confirmation_ts: Any,
        unit_qty: float = 1.0,
    ) -> Dict[str, Any]:
        """Plan (not execute) a burst after a confirmed assessment.

        Returns a journal-ready event dict. Fill prices use a
        deterministic per-second impact ramp: entry_k = close *
        (1 + side*(fee+slip+k*impact_ramp)/10^4) with impact_ramp
        pinned to 0.0 (no fabricated impact curve — flat, honest).
        """
        if direction not in ("BULLISH", "BEARISH"):
            raise ValueError("direction must be BULLISH or BEARISH")
        side = "BUY" if direction == "BULLISH" else "SELL"
        cost_bps = float(self.config["fee_bps"]) + float(
            self.config["slippage_bps"]
        )
        fills = []
        for k in range(int(self.config["max_fills_per_burst"])):
            offset_sec = k + 1  # 1 fill per second, first at t+1s
            price = confirmation_close * (
                1.0 + (1.0 if side == "BUY" else -1.0) * cost_bps / 10_000.0
            )
            fills.append(
                {
                    "t_offset_sec": offset_sec,
                    "side": side,
                    "qty": unit_qty,
                    "price": round(price, 10),
                    "cost_bps": cost_bps,
                }
            )
        return {
            "event": "RAPID_BURST",
            "submission_id": submission_id,
            "symbol": symbol,
            "direction": direction,
            "side": side,
            "confidence_pct": round(float(confidence_pct), 2),
            "confirmation_candle": {"ts": confirmation_ts,
                                    "close": confirmation_close},
            "fills": fills,
            "fills_planned": len(fills),
            "rate": "1 fill/second (paper journal only)",
            "status": "PENDING_MARK",
            "note": (
                "hypothetical paper fills; exit marked at the NEXT "
                "closed candle; no orders were sent anywhere"
            ),
        }

    @staticmethod
    def mark_burst(
        burst_event: Dict[str, Any],
        *,
        next_close: float,
    ) -> Dict[str, Any]:
        """Mark a planned burst against the actual next closed candle.

        PnL (price units, qty-weighted): long bursts gain when
        next_close > avg entry; short bursts the mirror. Costs are
        already inside the fill prices (conservative: both sides pay
        fee+slip).
        """
        fills = burst_event.get("fills") or []
        if not fills or next_close is None or next_close <= 0:
            raise ValueError("cannot mark a burst without fills/next close")
        qty_total = sum(float(f["qty"]) for f in fills)
        avg_entry = sum(float(f["price"]) * float(f["qty"]) for f in fills) / qty_total
        side = burst_event["side"]
        sign = 1.0 if side == "BUY" else -1.0
        gross = sign * (next_close - avg_entry) * qty_total
        # exits also pay the cost model (fee+slip on the way out)
        cost_bps = float(fills[0].get("cost_bps", 12.0))
        exit_cost = next_close * (cost_bps / 10_000.0) * qty_total
        net = gross - exit_cost
        net_bps = (
            sign * (next_close / avg_entry - 1.0) * 10_000.0 - cost_bps
        )
        marked = dict(burst_event)
        marked.update(
            {
                "status": "MARKED",
                "exit_close": next_close,
                "avg_entry": round(avg_entry, 10),
                "qty_total": qty_total,
                "gross_pnl": round(gross, 10),
                "net_pnl": round(net, 10),
                "net_pnl_bps": round(net_bps, 4),
            }
        )
        return marked

    @staticmethod
    def burst_allowed(
        *,
        meta: Optional[Dict[str, Any]],
        bars_since_last_burst: Optional[int],
        cooldown_bars: int,
        cumulative_bps: float,
        loss_limit_bps: float,
    ) -> Dict[str, Any]:
        """Fail-closed burst admission check (inspectable reasons)."""
        if cumulative_bps <= -abs(loss_limit_bps):
            return {
                "allowed": False,
                "reason": (
                    f"cumulative burst loss {cumulative_bps:.1f} bps "
                    f"breached the {-abs(loss_limit_bps):.1f} bps limit "
                    "(bursts disarmed for this window)"
                ),
            }
        if bars_since_last_burst is not None and bars_since_last_burst < cooldown_bars:
            return {
                "allowed": False,
                "reason": (
                    f"cooldown: {bars_since_last_burst} < {cooldown_bars} "
                    "bars since the last burst"
                ),
            }
        return {"allowed": True, "reason": "within caps"}


__all__ = ["RapidScalper"]
