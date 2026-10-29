#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Trading Lab — MT5 Bridge v2.0  (v3.0 "QUANT PRO" ke liye)
=============================================================
Ye script aapke PC par chalta hai jahan MetaTrader5 terminal installed hai.
Ye MT5 terminal se REAL candles utha kar AI Trading Lab app ko deta hai.

NAEE v3.0: LIVE MIRROR endpoints — /order, /positions, /close
  App me Settings > BRIDGE LIVE MIRROR ON karne par paper trades ke saath
  ye bridge REAL MT5 orders bhi bhejega (owner ki zimmedari — demo account
  par pehle test karein!).

KAISE USE KAREIN (Windows PC):
  1) MetaTrader5 terminal install karein aur login karein (DEMO pehle!)
  2) pip install MetaTrader5
  3) python mt5-bridge.py
  4) App me: Settings > MT5 DATA FEED > apne PC ka URL dalein
     e.g.  http://192.168.1.5:8899   (PC ka local IP, same WiFi network)
  5) SET dabayen — ab app ki candles seedha aapke MT5 broker se aayengi
  6) (Optional) BRIDGE LIVE toggle — real orders ke liye (demo pehle)

NOTE: Script khali chhodo to app ka built-in halal commodities feed
(Gold/Silver/Oil/Gas/Agri — public futures data) khud chalta rehta hai.
Bridge optional hai — real MT5 broker prices + live order routing ke liye.
"""

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

HOST = "0.0.0.0"
PORT = 8899

try:
    import MetaTrader5 as mt5
except ImportError:
    print("MetaTrader5 package nahi mila. Pehle ye chalayen:  pip install MetaTrader5")
    raise SystemExit(1)

TF_MAP = {
    "1m": mt5.TIMEFRAME_M1,  "5m": mt5.TIMEFRAME_M5,   "15m": mt5.TIMEFRAME_M15,
    "30m": mt5.TIMEFRAME_M30, "1h": mt5.TIMEFRAME_H1,  "4h": mt5.TIMEFRAME_H4,
}


def fetch_candles(symbol, tf="5m", limit=200):
    bars = mt5.copy_rates_from_pos(symbol, TF_MAP.get(tf, mt5.TIMEFRAME_M5), 0, int(limit))
    if bars is None:
        return None
    # Binance-shape JSON: [[ts_ms, open, high, low, close, volume], ...]
    return [[int(b["time"]) * 1000, float(b["open"]), float(b["high"]),
             float(b["low"]), float(b["close"]), float(b["tick_volume"])] for b in bars]


SYMBOL_MAP = {  # app symbol -> MT5 broker symbol (broker-specific overrides app se bhi aa sakte hain)
    "XAUUSD": "XAUUSD", "XAGUSD": "XAGUSD", "USOIL": "USOIL", "UKOIL": "UKOIL", "NGAS": "NGAS",
}


def place_order(body):
    """v3.0 LIVE MIRROR — market order bhejo. body: {symbol, side, volume, trade_id}.
    WARNING: ye REAL money order hai (ya demo, jo account logged in hai)."""
    sym = body.get("symbol", "XAUUSD").strip()
    sym = SYMBOL_MAP.get(sym, sym)
    side = body.get("side", "BUY").upper()
    vol = float(body.get("volume", 0.01))
    if not mt5.symbol_select(sym, True):
        return {"ok": False, "error": "symbol " + sym + " Market Watch me nahi (add karein)"}
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        return {"ok": False, "error": "symbol " + sym + " ka quote nahi mila"}
    price = tick.ask if side == "BUY" else tick.bid
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": max(0.01, vol),
        "type": mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "deviation": 20,
        "magic": 20261029,
        "comment": "ATL v3.0 mirror t" + str(body.get("trade_id", 0)),
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res is None:
        return {"ok": False, "error": "order_send returned None: " + str(mt5.last_error())}
    if res.retcode != mt5.TRADE_RETCODE_DONE:
        return {"ok": False, "error": "retcode " + str(res.retcode) + " " + str(res.comment)}
    return {"ok": True, "order": res.order, "price": res.price, "volume": res.volume,
            "symbol": sym, "side": side, "deal": res.deal}


def close_position(body):
    """v3.0 — symbol ke sab positions ya specific ticket close karo.
    body: {symbol, trade_id (optional — comment se match)}"""
    sym = body.get("symbol", "").strip()
    sym = SYMBOL_MAP.get(sym, sym)
    tid = int(body.get("trade_id", 0))
    closed = 0
    positions = mt5.positions_get(symbol=sym) if sym else mt5.positions_get()
    if positions is None:
        return {"ok": False, "error": "positions_get fail: " + str(mt5.last_error())}
    for p in positions:
        if tid and ("t" + str(tid)) not in (p.comment or ""):
            continue  # sirf isi app-trade ka mirror position
        tick = mt5.symbol_info_tick(p.symbol)
        if tick is None:
            continue
        is_buy = p.type == mt5.POSITION_TYPE_BUY
        req = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": p.ticket,
            "symbol": p.symbol,
            "volume": p.volume,
            "type": mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY,
            "price": tick.bid if is_buy else tick.ask,
            "deviation": 20,
            "magic": 20261029,
            "comment": "ATL v3.0 close t" + str(tid),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        res = mt5.order_send(req)
        if res is not None and res.retcode == mt5.TRADE_RETCODE_DONE:
            closed += 1
    return {"ok": True, "closed": closed}


def list_positions():
    """v3.0 — khuli MT5 positions ki list (monitoring)."""
    out = []
    positions = mt5.positions_get()
    if positions is None:
        return out
    for p in positions:
        out.append({"ticket": p.ticket, "symbol": p.symbol,
                    "type": "BUY" if p.type == mt5.POSITION_TYPE_BUY else "SELL",
                    "volume": p.volume, "price_open": p.price_open,
                    "price_current": p.price_current, "profit": p.profit,
                    "comment": p.comment})
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[bridge]", self.address_string(), fmt % args)

    def _json(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        """v3.0 LIVE MIRROR — /order, /close (real money routes; app sirf bridge_live
        ON + owner approval ke saath bhejta hai)."""
        u = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode() or "{}")
        except Exception:
            self._json(400, {"ok": False, "error": "invalid JSON"})
            return
        if u.path == "/order":
            print("[bridge] ORDER:", body.get("symbol"), body.get("side"), body.get("volume"))
            self._json(200, place_order(body))
            return
        if u.path == "/close":
            print("[bridge] CLOSE:", body.get("symbol"), "t" + str(body.get("trade_id", 0)))
            self._json(200, close_position(body))
            return
        self._json(404, {"ok": False, "error": "unknown POST path — /order ya /close"})

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/health":
            info = mt5.terminal_info()
            acc = mt5.account_info()
            self._json(200, {"ok": True, "bridge": "mt5-bridge v2.0 (QUANT PRO)",
                             "terminal": bool(info), "connected": bool(info and info.connected),
                             "account": acc.login if acc else 0,
                             "server": acc.server if acc else "",
                             "currency": acc.currency if acc else "",
                             "positions": len(mt5.positions_get() or [])})
            return
        if u.path == "/positions":
            self._json(200, {"ok": True, "positions": list_positions()})
            return
        if u.path == "/candles":
            sym = (q.get("symbol", [""])[0] or "").strip()
            if not sym:
                self._json(400, {"error": "symbol required (e.g. XAUUSD)"})
                return
            data = fetch_candles(sym, q.get("tf", ["5m"])[0], q.get("limit", ["200"])[0])
            if data is None:
                self._json(404, {"error": "symbol " + sym + " MT5 terminal me nahi mila "
                                          "(Market Watch me add karein)"})
                return
            self._json(200, data)
            return
        self._json(404, {"error": "unknown path — /health, /candles, /positions ya POST /order, /close"})


if __name__ == "__main__":
    if not mt5.initialize():
        print("MT5 initialize FAIL — MetaTrader5 terminal install/open karein:", mt5.last_error())
        raise SystemExit(1)
    acc = mt5.account_info()
    print("=" * 60)
    print(" AI Trading Lab — MT5 Bridge chal raha hai: http://0.0.0.0:%d" % PORT)
    if acc:
        print(" MT5 account: %s | server: %s | balance: %.2f %s" %
              (acc.login, acc.server, acc.balance, acc.currency))
    print(" App me Settings > MT5 DATA FEED me PC ka IP dalein (same WiFi).")
    print(" Ctrl+C se band karein.")
    print("=" * 60)
    try:
        HTTPServer((HOST, PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nBridge band. Allah Hafiz!")
    finally:
        mt5.shutdown()
