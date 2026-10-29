#!/usr/bin/env python3
"""
3C STRATEGY BACKTEST — exact mechanical rules from the MASTER TRAINING PROMPT.
Real Binance 5m klines (data-api.binance.vision). No invented data, no look-ahead.

Rules implemented verbatim:
  BUY  setup: C1 green, C2 green (each body >= 70% of H-L range), C3 red,
              C3.close >= lowest Low of C1 & C2 (inclusive -> 'not below')
  SELL setup: mirror (C1,C2 red body>=70%, C3 green, C3.close <= highest High of C1&C2)
  Zone: highest High / lowest Low across all 3 setup candles
  Window: next 5 closed 5m candles after C3 (5th included); breakout must occur there
  Invalidation (BUY): a window candle CLOSES below zoneLow (wick alone does NOT cancel)
  Invalidation (SELL): a window candle CLOSES above zoneHigh
  Same-candle breakout+invalidation = UNKNOWN sequence from OHLC -> skip (conservative)
  Entry: stop-order simulation. BUY trigger = zoneHigh (+buffer), fill = max(trigger, open)
  SL: opposite extreme of setup minus/plus SL buffer (BUY: zoneLow - buf)
  1R = |entry - SL|; TP = 3R; at +1R move SL to breakeven (whole position); no partial TP
  Risk: 1% of equity per trade, qty = riskAmt / riskDist (notional capped 95% equity)
  Conservative same-candle order: original-SL hit first, then TP, then BE move last.
"""
import json, time, urllib.request, sys

HOSTS = ["https://data-api.binance.vision", "https://api.binance.com"]
BODY_PCT = 0.70
WINDOW = 5
ENTRY_BUF = 0.0     # fraction of price (0 = pure breakout level)
SL_BUF = 0.0        # fraction of price (0 = SL exactly at opposite extreme)
RISK = 0.01         # 1% of equity
TP_R = 3.0          # 3R take profit, whole position
FEE_RT = 0.001      # 0.1% round-trip taker+slippage estimate (reported separately)

def fetch_klines(symbol, days, total=None):
    out, end = [], int(time.time() * 1000)
    need = total or days * 288
    while len(out) < need:
        q = f"/api/v3/klines?symbol={symbol}&interval=5m&limit=1000"
        if out:
            q += f"&endTime={out[0][0] - 1}"
        else:
            q += f"&endTime={end}"
        body = None
        for h in HOSTS:
            try:
                with urllib.request.urlopen(h + q, timeout=20) as r:
                    body = r.read().decode()
                break
            except Exception:
                continue
        if body is None:
            raise RuntimeError("fetch fail " + symbol)
        arr = json.loads(body)
        if not arr:
            break
        out = [[int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in arr] + out
        time.sleep(0.12)
    # drop unclosed last candle
    last_open = out[-1][0]
    if int(time.time() * 1000) - last_open < 300_000:
        out = out[:-1]
    return out

def body_pct(c):
    rng = c[2] - c[3]
    if rng <= 0:
        return 0.0
    return abs(c[4] - c[1]) / rng

def backtest(symbol, k):
    n = len(k)
    stats = dict(setups=0, triggered=0, expired=0, invalidated=0, unknown=0,
                 wins=0, losses=0, be=0, r_sum=0.0)
    equity = 100.0
    peak, maxdd = 100.0, 0.0
    gross_win = gross_loss = 0.0
    fees_paid = 0.0
    trades = []
    i = 2
    pending = None  # dict(side, zoneHigh, zoneLow, c3i)
    while i < n:
        c = k[i]
        acted = False
        if pending is not None:
            win_idx = i - pending["c3i"]  # 1..5
            if win_idx > WINDOW:
                stats["expired"] += 1
                pending = None
                # fall through: this candle may start a new setup
            else:
                if pending["side"] == "BUY":
                    trigger = pending["zoneHigh"] * (1 + ENTRY_BUF)
                    close_invalid = c[4] < pending["zoneLow"]
                    broke = c[2] > trigger
                    fill = max(trigger, c[1])
                    sl = pending["zoneLow"] * (1 - SL_BUF)
                else:
                    trigger = pending["zoneLow"] * (1 - ENTRY_BUF)
                    close_invalid = c[4] > pending["zoneHigh"]
                    broke = c[3] < trigger
                    fill = min(trigger, c[1])
                    sl = pending["zoneHigh"] * (1 + SL_BUF)
                if close_invalid and broke:
                    stats["unknown"] += 1   # OHLC alone can't sequence this — skip
                    stats["invalidated"] += 1
                    pending = None
                    acted = True
                elif close_invalid:
                    stats["invalidated"] += 1
                    pending = None
                    acted = True
                elif broke:
                    # open a simulated trade (always allowed — unlimited positions model,
                    # but sim carries ONE position: skip new entries while one is open)
                    if sim_open[0] is None:
                        stats["triggered"] += 1
                        risk_dist = abs(fill - sl)
                        if risk_dist > 0:
                            risk_amt = equity * RISK
                            qty = risk_amt / risk_dist
                            if qty * fill > equity * 0.95:
                                qty = equity * 0.95 / fill
                            sim_open[0] = dict(side=pending["side"], entry=fill, sl=sl,
                                               qty=qty, risk_amt=qty * risk_dist, ei=i)
                        pending = None
                        acted = True
                    else:
                        pending = None  # setup fired while sim busy — setup consumed
                        acted = True
        if pending is None and not acted and i >= 2:
            c1, c2, c3 = k[i - 2], k[i - 1], k[i]
            g1, g2, g3 = c1[4] > c1[1], c2[4] > c2[1], c3[4] > c3[1]
            b1ok, b2ok = body_pct(c1) >= BODY_PCT, body_pct(c2) >= BODY_PCT
            buy = g1 and g2 and (not g3) and b1ok and b2ok and c3[4] >= min(c1[3], c2[3])
            sell = (not g1) and (not g2) and g3 and b1ok and b2ok and c3[4] <= max(c1[2], c2[2])
            if buy or sell:
                stats["setups"] += 1
                pending = dict(side="BUY" if buy else "SELL",
                               zoneHigh=max(c1[2], c2[2], c3[2]),
                               zoneLow=min(c1[3], c2[3], c3[3]),
                               c3i=i)
        i += 1

    # manage open sim position inside the main loop is complex; redo as second pass:
    return stats

# The single-position management needs to live inside the walk; restructure:
def backtest2(symbol, k):
    n = len(k)
    stats = dict(setups=0, triggered=0, expired=0, invalidated=0, unknown=0,
                 wins=0, losses=0, be=0)
    equity = 100.0
    peak, maxdd = 100.0, 0.0
    gross_win = gross_loss = 0.0
    trades = []
    pos = None       # open sim position
    pending = None
    r_sum = 0.0
    for i in range(2, n):
        c = k[i]
        # ---- manage open position first (conservative SL -> TP -> BE) ----
        if pos is not None:
            side = pos["side"]
            # NOTE: sl may be entry after BE move — plain compare works for both states
            if side == "BUY":
                hit_sl = c[3] <= pos["sl"]
                hit_tp = c[2] >= pos["tp"]
                be_hit = pos["sl"] < pos["entry"] and c[2] >= pos["entry"] + pos["rd"]
            else:
                hit_sl = c[2] >= pos["sl"]
                hit_tp = c[3] <= pos["tp"]
                be_hit = pos["sl"] > pos["entry"] and c[3] <= pos["entry"] - pos["rd"]
            exit_px, reason = None, None
            if hit_sl:
                exit_px, reason = pos["sl"], "SL"
            elif hit_tp:
                exit_px, reason = pos["tp"], "TP"
            else:
                if be_hit:
                    pos["sl"] = pos["entry"]      # move whole position to breakeven
                    pos["be_moved"] = True
            if exit_px is not None:
                pnl = (exit_px - pos["entry"]) * pos["qty"] if side == "BUY" else (pos["entry"] - exit_px) * pos["qty"]
                fee = (pos["entry"] + exit_px) * pos["qty"] * FEE_RT / 2 * 2  # in+out
                r_mult = pnl / pos["risk_amt"] if pos["risk_amt"] > 0 else 0
                equity += pnl
                peak = max(peak, equity)
                maxdd = max(maxdd, (peak - equity) / peak if peak > 0 else 0)
                if abs(pnl) < 1e-12:
                    stats["be"] += 1
                elif pnl > 0:
                    stats["wins"] += 1; gross_win += pnl
                else:
                    stats["losses"] += 1; gross_loss += -pnl
                r_sum += r_mult
                trades.append((reason, round(r_mult, 2), round(pnl, 4)))
                pos = None
        # ---- pending setup handling ----
        acted = False
        if pending is not None:
            win_idx = i - pending["c3i"]
            if win_idx > WINDOW:
                stats["expired"] += 1
                pending = None
            else:
                if pending["side"] == "BUY":
                    trigger = pending["zoneHigh"] * (1 + ENTRY_BUF)
                    close_invalid = c[4] < pending["zoneLow"]
                    broke = c[2] > trigger
                    fill = max(trigger, c[1])
                    sl = pending["zoneLow"] * (1 - SL_BUF)
                else:
                    trigger = pending["zoneLow"] * (1 - ENTRY_BUF)
                    close_invalid = c[4] > pending["zoneHigh"]
                    broke = c[3] < trigger
                    fill = min(trigger, c[1])
                    sl = pending["zoneHigh"] * (1 + SL_BUF)
                if broke and close_invalid:
                    stats["unknown"] += 1
                    stats["invalidated"] += 1
                    pending = None
                elif close_invalid:
                    stats["invalidated"] += 1
                    pending = None
                elif broke:
                    if pos is None:
                        rd = abs(fill - sl)
                        if rd > 0:
                            risk_amt0 = equity * RISK
                            qty = risk_amt0 / rd
                            if qty * fill > equity * 0.95:
                                qty = equity * 0.95 / fill
                            pos = dict(side=pending["side"], entry=fill, sl=sl,
                                       tp=fill + TP_R * rd if pending["side"] == "BUY" else fill - TP_R * rd,
                                       qty=qty, rd=rd, risk_amt=qty * rd, be_moved=False)
                            stats["triggered"] += 1
                    pending = None
                # else: still waiting
                acted = pending is None  # consumed or never was
        # ---- new setup detection (only when no pending) ----
        if pending is None:
            c1, c2, c3 = k[i - 2], k[i - 1], k[i]
            g1, g2, g3 = c1[4] > c1[1], c2[4] > c2[1], c3[4] > c3[1]
            b1ok, b2ok = body_pct(c1) >= BODY_PCT, body_pct(c2) >= BODY_PCT
            buy = g1 and g2 and (not g3) and b1ok and b2ok and c3[4] >= min(c1[3], c2[3])
            sell = (not g1) and (not g2) and g3 and b1ok and b2ok and c3[4] <= max(c1[2], c2[2])
            if buy or sell:
                stats["setups"] += 1
                pending = dict(side="BUY" if buy else "SELL",
                               zoneHigh=max(c1[2], c2[2], c3[2]),
                               zoneLow=min(c1[3], c2[3], c3[3]),
                               c3i=i)
    # force-close open position at end
    if pos is not None:
        c = k[-1]
        pnl = (c[4] - pos["entry"]) * pos["qty"] if pos["side"] == "BUY" else (pos["entry"] - c[4]) * pos["qty"]
        equity += pnl
        r_sum += pnl / pos["risk_amt"] if pos["risk_amt"] > 0 else 0
        if pnl > 0: stats["wins"] += 1
        elif pnl < 0: stats["losses"] += 1
        else: stats["be"] += 1
        pos = None
    nT = stats["wins"] + stats["losses"] + stats["be"]
    stats["trades"] = nT
    stats["winrate"] = round(100 * stats["wins"] / nT, 1) if nT else 0.0
    stats["avgR"] = round(r_sum / nT, 3) if nT else 0.0
    stats["net_pct_gross"] = round(equity - 100, 2)
    stats["maxdd_pct"] = round(maxdd * 100, 1)
    stats["pf"] = round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
    return stats

if __name__ == "__main__":
    symbols = sys.argv[1:] or ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "PAXGUSDT"]
    DAYS = 90
    print(f"3C STRATEGY BACKTEST — M5, {DAYS} days, real Binance klines")
    print(f"rules: body>=70% (C1,C2) | 5-candle window | close-invalidation | SL=opposite extreme | BE@+1R | TP=+3R | risk 1% | no daily limits")
    print(f"fees: gross (paper engine parity) — 0.1% round-trip NOT deducted\n")
    grand = dict(trades=0, wins=0, losses=0)
    for s in symbols:
        try:
            k = fetch_klines(s, DAYS)
        except Exception as e:
            print(f"{s}: FETCH FAIL {e}")
            continue
        st = backtest2(s, k)
        grand["trades"] += st["trades"]; grand["wins"] += st["wins"]; grand["losses"] += st["losses"]
        days_covered = round((k[-1][0] - k[0][0]) / 86400000.0, 1)
        print(f"--- {s} ({days_covered}d, {len(k)} closed 5m candles) ---")
        print(f"  setups detected: {st['setups']}  |  triggered: {st['triggered']}  |  expired: {st['expired']}  |  invalidated: {st['invalidated']} (unknown-seq: {st['unknown']})")
        print(f"  trades: {st['trades']}  wins: {st['wins']}  losses: {st['losses']}  breakeven: {st['be']}  winrate: {st['winrate']}%")
        print(f"  avg R/trade: {st['avgR']}  |  PF: {st['pf']}  |  net: {st['net_pct_gross']:+.2f}% (on $100, 1% risk)  |  maxDD: {st['maxdd_pct']}%")
    tot = grand["wins"] + grand["losses"]
    if tot:
        print(f"\nTOTAL: {grand['trades']} trades — winrate {round(100*grand['wins']/tot,1)}% (BE excluded)")
