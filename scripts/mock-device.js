// Mock Device Server v2 — replicates ATL Android engine API contract (v1.3 / remote main)
// Usage: bun /home/z/my-project/scripts/mock-device.js  (port 8123)
const dashboardHtml = require("fs").readFileSync(
  "/home/z/my-project/android-app/app/src/main/assets/dashboard.html", "utf8");
const PORT = 8123;
const now = Date.now();

const routes = {
  "GET /api/health": () => ({ ok: true, engine: "ai-trading-lab-phone", device: "Samsung SM-S928B", android: 34, version: "1.3.0", timeframe: "1m", scanner: "24h" }),
  "POST /api/auth/login": () => ({ token: "mock-token-123", user: { name: "Owner", role: "ADMIN", email: "owner@atl.app" } }),
  "POST /api/auth/register": () => ({ message: "Account created — ab sign in karein" }),
  "POST /api/auth/logout": () => ({ ok: true }),
  "GET /api/dashboard": () => ({
    balance: 100, startBalance: 100, totalPnl: 12.47, pnlPct: 12.47,
    openCount: 1, openPnl: 0.31, closedCount: 27, winRate: 59.3,
    dayPnlPct: 1.8, drawdownPct: -2.1,
    equity: [100, 99.2, 101, 100.5, 103, 102.1, 105, 104.2, 106, 108.3, 107.1, 112.47],
    engine: { engine_on: true, active_symbols: 30,
      consensus: "24h scan #412 — 30 syms on 1m — 11 voters · BUY 8 vs SELL 3 · best 72% — silent 6 min",
      news_pause: false, data_host: "https://data-api.binance.vision", timeframe: "1m", scanner: "24h",
      scan_count: 412, last_scan_at: now - 25000, strategy_count: 35, indicator_count: 82,
      fear_greed: 71, battery_ok: false, watchdog: "9-min Doze-safe alarm + thread watchdog + swipe-kill restart" },
    user: { name: "Owner", role: "ADMIN" }
  }),
  "GET /api/instruments": () => ({ active: 30, watching: 118, pending: 2, total: 150,
    instruments: ["BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","XRPUSDT","DOGEUSDT","ADAUSDT","AVAXUSDT"].map((s, i) =>
      ({ symbol: s, exchange: "BINANCE", assetClass: "SPOT", status: i < 6 ? "ACTIVE" : "WATCHING",
        lastDataAt: now - i * 60000, note: "top volume pair — auto-discovered" })) }),
  "GET /api/indicators": () => ({ ok: true, symbol: "BTCUSDT", timeframe: "1m",
    library: [["Trend","EMA 9/21/50"],["Trend","Supertrend 10x3"],["Momentum","RSI 14"],["Volume","OBV"]],
    values: { price: 67120.55, rsi14: 61.24, ema9: 67098.2, ema21: 66985.4, ema50: 66750.9,
      supertrend: "UP 66750.1", macd: [42.71, 31.09], candlePattern: "Bullish Engulfing" } }),
  "GET /api/news": () => ({ news: [
    { ts: now - 1200000, source: "CoinDesk", headline: "Bitcoin ETF inflows hit weekly record", sentiment: "BULLISH", impact: "MEDIUM" },
    { ts: now - 3600000, source: "Cointelegraph", headline: "Fed holds rates steady", sentiment: "NEUTRAL", impact: "HIGH" }] }),
  "GET /api/trades": () => ({ trades: [
    { id: 904, symbol: "BTCUSDT", side: "BUY", qty: 0.0012, entry: 67120.55, sl: 66800.1, tp: 67650.2, exit: null, pnl: null,
      status: "OPEN", strategy: "CONSENSUS_35", consensus: 0.72, openedAt: now - 15 * 60000, closedAt: 0 },
    { id: 903, symbol: "ETHUSDT", side: "SELL", qty: 0.02, entry: 3210.4, sl: 3230.0, tp: 3170.5, exit: 3170.5, pnl: 0.8,
      status: "CLOSED", strategy: "SCOUT_SIGNAL", consensus: 0.66, openedAt: now - 90 * 60000, closedAt: now - 40 * 60000 },
    { id: 902, symbol: "SOLUSDT", side: "BUY", qty: 0.3, entry: 145.2, sl: 144.0, tp: 147.2, exit: 144.0, pnl: -0.36,
      status: "CLOSED", strategy: "CONSENSUS_35", consensus: 0.61, openedAt: now - 200 * 60000, closedAt: now - 150 * 60000 }] }),
  "GET /api/history": () => ({ ok: true, years: [
    { y: "2026", trades: 25, wins: 15, pnl: 12.03, months: [
      { m: "10", y: "2026", trades: 15, wins: 10, pnl: 8.41, days: [
        { d: "29", trades: 5, wins: 3, pnl: 2.1, vol: 812.4 },
        { d: "28", trades: 6, wins: 4, pnl: 3.9, vol: 940.1 },
        { d: "27", trades: 4, wins: 3, pnl: 2.41, vol: 655.0 }] },
      { m: "9", y: "2026", trades: 10, wins: 5, pnl: 3.62, days: [
        { d: "30", trades: 3, wins: 2, pnl: 1.2, vol: 402.2 }] }] },
    { y: "2025", trades: 2, wins: 1, pnl: 0.44, months: [
      { m: "12", y: "2025", trades: 2, wins: 1, pnl: 0.44, days: [
        { d: "15", trades: 2, wins: 1, pnl: 0.44, vol: 180.6 }] }] }] }),
  "GET /api/strategies": () => ({
    symbol: "BTCUSDT", lastVoteSym: "BTCUSDT", ytChannel: { id: "UCtest123", name: "Test Trader" },
    custom: [
      { id: 2, name: "RSI dip + EMA50 trend", status: "BACKTESTED", source: "ai-text",
        rules: "rsi(14)<30 AND price>ema(50) → BUY ; rsi(14)>70 → SELL",
        stats: { trades: 37, winrate: 56.8, pf: 1.42, netPct: 9.84, maxDD: 7.4, symbol: "BTCUSDT" } },
      { id: 3, name: "YT: Supertrend scalping", status: "CANDIDATE", source: "youtube",
        rules: "supertrend(10,3) flip → follow", video: { id: "dQw4w9WgXcQ", title: "Best Supertrend Scalping Strategy (1000 candles tested)" } },
      { id: 1, name: "EMA cross 9/21", status: "PAPER", source: "ai-text", rules: "ema(9)>ema(21) → BUY ; ema(9)<ema(21) → SELL",
        stats: { trades: 42, winrate: 54.8, pf: 1.21, netPct: 3.9, maxDD: 6.2, symbol: "BTCUSDT" } }],
    builtin: ["EMA 9/21 Cross","RSI + Bollinger","MACD + Stochastic","VWAP Reversion","Breakout 20","Supertrend",
      "Ichimoku Cloud","ADX Trend","CCI + Williams %R","MFI + OBV","PSAR + Aroon","Stochastic RSI","Candle Patterns",
      "Donchian","Hull MA","KAMA","Vortex","Alligator","TSI","CMO","Fisher","DeMarker","Awesome Osc","Volume Flow",
      "CMF","Klinger","PVT + A/D","Fibonacci","Pivot Points","Fair Value Gap","BOS","Liquidity Sweep","Harmonic",
      "Schaff TC","Fear & Greed"].map((n, i) => ({ name: n, group: i < 6 ? "Trend" : (i < 12 ? "Momentum" : "Encyclopedia"),
      vote: [1,0,0,0,0,1,1,1,0,1,1,0,0,0,1,1,1,1,1,0,0,0,1,1,1,1,1,0,0,0,0,0,0,1,0][i] })) }),
  "POST /api/strategies": (b) => {
    const a = b.action || "";
    if (a === "add") return { ok: true, strategy: { id: 9, name: "AI: " + (b.text || "").slice(0, 28), status: "CANDIDATE" } };
    if (a === "yt_add") return { ok: true, message: "Video watch ho gayi — CANDIDATE ban gayi (transcript se spec nikaala)" };
    if (a === "yt_channel") return { ok: true, message: "Subscribed — engine har 15 min nayi videos + live streams check karega" };
    if (a === "backtest") return { ok: true, message: "Backtest: 37 trades · win 56.8% · PF 1.42 · net +9.84% · maxDD 7.4%" };
    if (a === "paper") return { ok: true, message: "PAPER mode on — shadow trades chal rahi hain" };
    if (a === "approve") return { ok: true, message: "LIVE approved — engine ab is strategy se khud trade karega" };
    if (a === "reject") return { ok: true, message: "Rejected" };
    if (a === "delete") return { ok: true, message: "Deleted" };
    if (a === "set_symbol") return { ok: true, message: "Backtest symbol set: " + b.symbol };
    if (a === "yt_stop") return { ok: true, message: "Watcher stopped" };
    return { ok: true };
  },
  "GET /api/logs": () => ({ logs: [
    { ts: now - 60000, level: "INFO", component: "EXECUTOR", event: "PAPER_OPEN", details: "BTCUSDT BUY [CONSENSUS_35] qty=0.0012 entry=67120.55 consensus=72% risk=1.30%" },
    { ts: now - 300000, level: "INFO", component: "LAB", event: "YT_WATCH", details: "video dQw4w9WgXcQ — transcript fetched on phone, spec extracted: supertrend(10,3)" },
    { ts: now - 900000, level: "WARN", component: "SYSTEM", event: "TASK_REMOVED", details: "app task swiped away — AlarmManager restart scheduled" },
    { ts: now - 1800000, level: "INFO", component: "SYSTEM", event: "SERVICE_START", details: "phone server online on port 81" }] }),
  "GET /api/brokers": () => ({ brokers: [] }),
  "GET /api/settings": () => ({ engineOn: true, version: "1.3" }),
  "GET /api/admin/alerts": () => ({ unreadCount: 2, alerts: [
    { id: 1, title: "New registration", body: "owner@atl.app (ADMIN)", read: 0, created_at: now - 7200000 }] }),
  "POST /api/balance": (b) => ({ ok: true, balance: b.amount, message: "Paper balance set: $" + b.amount }),
  "POST /api/settings": (b) => ({ ok: true, engineOn: b.engineOn }),
  "POST /api/trades/close": () => ({ ok: true, message: "closed" }),
  "POST /api/instruments/scan": () => ({ ok: true, message: "Discovery + news scan started" }),
};

if (typeof Bun !== "undefined") {
  Bun.serve({
    port: PORT,
    async fetch(req) {
      const u = new URL(req.url);
      const path = u.pathname;
      if (path === "/" || path === "/index.html") return new Response(dashboardHtml, { headers: { "content-type": "text/html" } });
      if (path.startsWith("/api/history/csv")) return new Response("id,symbol,side,qty,entry,exit,pnl,status\n903,ETHUSDT,SELL,0.02,3210.4,3170.5,0.8,CLOSED\n", { headers: { "content-type": "text/csv" } });
      const handler = routes[req.method + " " + path]
        || (req.method === "GET" && path.startsWith("/api/indicators") ? routes["GET /api/indicators"] : null);
      if (handler) {
        let body = {};
        try { body = req.method === "POST" ? await req.json() : {}; } catch (e) {}
        return Response.json(handler(body));
      }
      return new Response(JSON.stringify({ error: "no route: " + req.method + " " + path }), { status: 404, headers: { "content-type": "application/json" } });
    },
  });
  console.log("MOCK DEVICE v2 (v1.3 contract) on http://localhost:" + PORT);
} else {
  console.log("bun required");
}
