#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI Trading Lab — MT5 Bridge v1.0  (v2.1 "HALAL MT5" ke liye)
=============================================================
Ye script aapke PC par chalta hai jahan MetaTrader5 terminal installed hai.
Ye MT5 terminal se REAL candles utha kar AI Trading Lab app ko deta hai.

KAISE USE KAREIN (Windows PC):
  1) MetaTrader5 terminal install karein aur login karein (demo bhi chalega)
  2) pip install MetaTrader5
  3) python mt5-bridge.py
  4) App me: Settings > MT5 DATA FEED > apne PC ka URL dalein
     e.g.  http://192.168.1.5:8899   (PC ka local IP, same WiFi network)
  5) SET dabayen — ab app ki candles seedha aapke MT5 broker se aayengi

NOTE: Script khali chhodo to app ka built-in halal commodities feed
(Gold/Silver/Oil/Gas/Agri — public futures data) khud chalta rehta hai.
Bridge optional hai — real MT5 broker prices ke liye.
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

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/health":
            info = mt5.terminal_info()
            self._json(200, {"ok": True, "bridge": "mt5-bridge v1.0",
                             "terminal": bool(info), "connected": bool(info and info.connected)})
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
        self._json(404, {"error": "unknown path — /health ya /candles?symbol=XAUUSD&tf=5m&limit=200"})


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
