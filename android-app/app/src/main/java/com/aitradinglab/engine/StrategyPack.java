package com.aitradinglab.engine;

import java.util.ArrayList;
import java.util.List;

/**
 * v4.4.0 STRATEGY PACK — PDF "Complete Trading Encyclopedia / Binance Edition" ki
 * mechanical strategies (owner: "purani PDF ki strategies DELETE NAHI karni thi").
 * v4.1.0(35) rebuild me ye pack ghalti se gayab ho gaya tha — AB RESTORED.
 *
 *   S1 EMA_PULLBACK   — EMA 21/50 + RSI pullback (PDF rating: Solid base)
 *   S2 BB_SQUEEZE     — Bollinger squeeze breakout + volume (Decent)
 *   S3 SUPERTREND_ADX — Supertrend flip + ADX strength (Decent)
 *   S4 VWAP_BOUNCE    — VWAP bounce/reject (Promising — crypto volume REAL)
 *   S5 PDH_PDL        — Previous day high/low breakout (Promising, objective)
 *   S6 FUNDING_OI     — Funding rate + OI contrarian fade (Promising, fapi.binance.com)
 *   S7 CANDLE_PAT     — PDF Part-3: engulfing/hammer with EMA trend + volume
 *   S8 DOW_PULLBACK   — PDF Part-4: Dow theory HH/HL structure pullback (EMA21 tag)
 *   S9 GANN_50        — PDF Part-4: 50% retracement bounce of last swing
 *
 * (ICT_FVG / ORDER_BLOCK / LIQ_SWEEP / WYCKOFF / MKT_PROFILE Shaakuni Suite + Lab
 *  DSL me pehle se hain — duplicate nahi kiye.)
 *
 * Timeframe: CLOSED 15m candles (PDF section 11: "1m/5m scalping is dominated by
 * fees") — engine 15m feed alag se fetch karta hai. Har strategy deterministic +
 * restart-safe: signal candle open time = idempotency anchor.
 * S7/S8/S9 naye (PDF Part-3/4 rules se) — baaki 6 v4.0 pack ke exact rules.
 */
public class StrategyPack {

    /** Ek mechanical strategy signal — paper trade isi par start hota hai. */
    public static class Signal {
        public String strategy;   // "S1_EMA_PULLBACK" ...
        public String side;       // BUY | SELL
        public long sigTs;        // signal candle open time (ms)
        public int sigIdx;        // index in closed candle list
        public double refPrice;   // signal close
        public double slPrice;    // stop loss
        public double boundary;   // invalidation: close beyond = dead
        public int windowBars;    // entry/validity window (15m bars)
        public String note;       // human-readable trigger note
    }

    /** Strategy metadata (UI/settings ke liye) — key, label, rating. */
    public static final String[][] STRATEGIES = {
            {"S1_EMA_PULLBACK",   "EMA 21/50 + RSI pullback",            "Solid base"},
            {"S2_BB_SQUEEZE",     "Bollinger squeeze breakout + volume",  "Decent"},
            {"S3_SUPERTREND_ADX", "Supertrend flip + ADX",                "Decent"},
            {"S4_VWAP_BOUNCE",    "VWAP bounce (session)",                "Promising"},
            {"S5_PDH_PDL",        "Previous day high/low breakout",       "Promising"},
            {"S6_FUNDING_OI",     "Funding + OI contrarian fade",         "Promising"},
            {"S7_CANDLE_PAT",     "Engulfing/Hammer + trend + volume",    "Part-3"},
            {"S8_DOW_PULLBACK",   "Dow HH/HL structure pullback",         "Part-4"},
            {"S9_GANN_50",        "50% retracement bounce (Gann)",        "Part-4"},
            {"P1_14D_RIDER",      "14D Breakout Rider (5M Playbook)",     "CHAMPION"},
            {"P2_10D_TREND",      "10D Trend+Volume Break (Playbook)",    "4/4 positive"},
            {"P3_14D_CLASSIC",    "14D Breakout Classic (Playbook)",      "3/4 positive"},
            {"P4_SQUEEZE",        "Squeeze Explosion (Playbook)",         "Rare + powerful"}
    };

    public static final String[] KEYS = {
            "S1_EMA_PULLBACK", "S2_BB_SQUEEZE", "S3_SUPERTREND_ADX", "S4_VWAP_BOUNCE",
            "S5_PDH_PDL", "S6_FUNDING_OI", "S7_CANDLE_PAT", "S8_DOW_PULLBACK", "S9_GANN_50",
            "P1_14D_RIDER", "P2_10D_TREND", "P3_14D_CLASSIC", "P4_SQUEEZE"
    };

    /** Default entry/validity window (15m bars). */
    public static final int DEFAULT_WINDOW = 5;

    // ================== helpers (pure, testable) ==================
    private static double emaAt(List<EngineCore.Candle> k, int n, int at) {
        if (k.size() < n || at < n - 1) return Double.NaN;
        double mult = 2.0 / (n + 1), e = 0; boolean init = false;
        for (int i = 0; i <= at; i++) {
            double c = k.get(i).c;
            e = init ? (c - e) * mult + e : c; init = true;
        }
        return e;
    }
    private static double rsiAt(List<EngineCore.Candle> k, int n, int at) {
        if (at < n) return Double.NaN;
        double g = 0, l = 0;
        for (int i = at - n + 1; i <= at; i++) {
            double ch = k.get(i).c - k.get(i - 1).c;
            if (ch > 0) g += ch; else l -= ch;
        }
        if (g + l == 0) return 50;
        return 100 * g / (g + l);
    }
    private static double[] bollingerAt(List<EngineCore.Candle> k, int n, int at) {
        if (at < n - 1) return null;
        double sum = 0, sum2 = 0;
        for (int i = at - n + 1; i <= at; i++) { double c = k.get(i).c; sum += c; sum2 += c * c; }
        double mean = sum / n, sd = Math.sqrt(Math.max(0, sum2 / n - mean * mean));
        return new double[]{mean - 2 * sd, mean, mean + 2 * sd};
    }
    private static double vwapSession(List<EngineCore.Candle> k, int at, int bars) {
        double pv = 0, vv = 0;
        int from = Math.max(0, at - bars + 1);
        for (int i = from; i <= at; i++) {
            EngineCore.Candle c = k.get(i);
            double tp = (c.h + c.l + c.c) / 3;
            pv += tp * c.v; vv += c.v;
        }
        return vv > 0 ? pv / vv : k.get(at).c;
    }
    private static double volSma(List<EngineCore.Candle> k, int at, int n) {
        if (at < n) return 0;
        double s = 0;
        for (int i = at - n + 1; i <= at; i++) s += k.get(i).v;
        return s / n;
    }
    private static int stDirAt(List<EngineCore.Candle> k, int at) {
        if (at < 12) return 0;
        List<EngineCore.Candle> sub = k.subList(0, at + 1);
        double[] st = EngineCore.supertrend(sub);
        return st == null ? 0 : (int) st[1];
    }
    private static double stLineAt(List<EngineCore.Candle> k, int at) {
        List<EngineCore.Candle> sub = k.subList(0, at + 1);
        double[] st = EngineCore.supertrend(sub);
        return st == null ? Double.NaN : st[0];
    }

    /** ADX +DI/-DI at index (Wilder) — [adx, +di, -di], ya null. */
    public static double[] adxAt(List<EngineCore.Candle> k, int n, int at) {
        if (at < 2 * n + 2) return null;
        double plusS = 0, minusS = 0, trS = 0;
        for (int i = at - 2 * n + 1; i <= at - n; i++) {
            EngineCore.Candle c = k.get(i), p = k.get(i - 1);
            double up = c.h - p.h, dn = p.l - c.l;
            plusS += (up > dn && up > 0) ? up : 0;
            minusS += (dn > up && dn > 0) ? dn : 0;
            trS += Math.max(c.h - c.l, Math.max(Math.abs(c.h - p.c), Math.abs(c.l - p.c)));
        }
        double dxSum = 0; int dxN = 0; double pdi = 0, mdi = 0;
        for (int i = at - n + 1; i <= at; i++) {
            EngineCore.Candle c = k.get(i), p = k.get(i - 1);
            double up = c.h - p.h, dn = p.l - c.l;
            plusS = plusS - plusS / n + ((up > dn && up > 0) ? up : 0);
            minusS = minusS - minusS / n + ((dn > up && dn > 0) ? dn : 0);
            trS = trS - trS / n + Math.max(c.h - c.l, Math.max(Math.abs(c.h - p.c), Math.abs(c.l - p.c)));
            if (trS <= 0) continue;
            pdi = 100 * plusS / trS; mdi = 100 * minusS / trS;
            double dx = (pdi + mdi == 0) ? 0 : 100 * Math.abs(pdi - mdi) / (pdi + mdi);
            dxSum += dx; dxN++;
        }
        return new double[]{dxN > 0 ? dxSum / dxN : 0, pdi, mdi};
    }

    // ================== S1 — EMA 21/50 + RSI PULLBACK ==================
    public static Signal emaPullback(List<EngineCore.Candle> k, int i) {
        if (i < 210) return null;
        EngineCore.Candle c = k.get(i), p = k.get(i - 1);
        double e21 = emaAt(k, 21, i), e50 = emaAt(k, 50, i), e200 = emaAt(k, 200, i);
        double r = rsiAt(k, 14, i), rPrev = rsiAt(k, 14, i - 1);
        if (Double.isNaN(e21) || Double.isNaN(e50) || Double.isNaN(e200) || Double.isNaN(r) || Double.isNaN(rPrev)) return null;
        double a = EngineCore.atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return null;
        boolean bull = c.c > c.o, bear = c.c < c.o;
        Signal s = new Signal();
        if (c.c > e200 && e21 > e50 && rPrev < 42 && r >= 42 && r < 62 && bull) {
            s.strategy = "S1_EMA_PULLBACK"; s.side = "BUY";
            s.slPrice = Math.min(c.l, p.l) - 1.5 * a;
            s.boundary = e50; s.windowBars = DEFAULT_WINDOW;
            s.note = "RSI pullback recovery " + String.format(java.util.Locale.US, "%.1f→%.1f", rPrev, r) + " (uptrend EMA21>50, close>EMA200)";
        } else if (c.c < e200 && e21 < e50 && rPrev > 58 && r <= 58 && r > 38 && bear) {
            s.strategy = "S1_EMA_PULLBACK"; s.side = "SELL";
            s.slPrice = Math.max(c.h, p.h) + 1.5 * a;
            s.boundary = e50; s.windowBars = DEFAULT_WINDOW;
            s.note = "RSI pullback rejection " + String.format(java.util.Locale.US, "%.1f→%.1f", rPrev, r) + " (downtrend EMA21<50, close<EMA200)";
        } else return null;
        s.sigTs = c.ts; s.sigIdx = i; s.refPrice = c.c;
        return s;
    }

    // ================== S2 — BOLLINGER SQUEEZE BREAKOUT + VOLUME ==================
    public static Signal bbSqueeze(List<EngineCore.Candle> k, int i) {
        if (i < 120) return null;
        EngineCore.Candle c = k.get(i);
        double[] bb = bollingerAt(k, 20, i);
        double[] bbPrev = bollingerAt(k, 20, i - 1);
        if (bb == null || bbPrev == null || bbPrev[1] <= 0) return null;
        double mid = bb[1], up = bb[2], lo = bb[0];
        // squeeze check: PREV bar bandwidth last-100 ke lowest quintile me
        double[] bws = new double[100];
        for (int j = 0; j < 100; j++) {
            double[] b = bollingerAt(k, 20, i - 99 + j);
            bws[j] = (b == null || b[1] <= 0) ? 1 : (b[2] - b[0]) / b[1];
        }
        java.util.Arrays.sort(bws);
        double q20 = bws[19];
        if ((bbPrev[2] - bbPrev[0]) / bbPrev[1] > q20) return null;
        double vs = volSma(k, i - 1, 20);
        if (vs <= 0) return null;
        Signal s = new Signal();
        if (c.c > up && c.v > 1.2 * vs) {
            s.strategy = "S2_BB_SQUEEZE"; s.side = "BUY";
            s.slPrice = mid; s.boundary = mid; s.windowBars = DEFAULT_WINDOW;
            s.note = "BB squeeze breakout UP, vol " + String.format(java.util.Locale.US, "%.1fx", c.v / vs);
        } else if (c.c < lo && c.v > 1.2 * vs) {
            s.strategy = "S2_BB_SQUEEZE"; s.side = "SELL";
            s.slPrice = mid; s.boundary = mid; s.windowBars = DEFAULT_WINDOW;
            s.note = "BB squeeze breakout DOWN, vol " + String.format(java.util.Locale.US, "%.1fx", c.v / vs);
        } else return null;
        s.sigTs = c.ts; s.sigIdx = i; s.refPrice = c.c;
        return s;
    }

    // ================== S3 — SUPERTREND FLIP + ADX ==================
    public static Signal supertrendAdx(List<EngineCore.Candle> k, int i) {
        if (i < 60) return null;
        int dirNow = stDirAt(k, i), dirPrev = stDirAt(k, i - 1);
        if (dirNow == 0 || dirPrev == 0 || dirNow == dirPrev) return null;
        double[] adx = adxAt(k, 14, i);
        if (adx == null || adx[0] < 25) return null;
        double st = stLineAt(k, i);
        if (Double.isNaN(st) || st <= 0) return null;
        EngineCore.Candle c = k.get(i);
        Signal s = new Signal();
        s.sigTs = c.ts; s.sigIdx = i; s.refPrice = c.c;
        s.slPrice = st; s.boundary = st; s.windowBars = 10;
        if (dirNow > 0 && adx[1] > adx[2]) {
            s.strategy = "S3_SUPERTREND_ADX"; s.side = "BUY";
            s.note = "Supertrend flip UP + ADX " + String.format(java.util.Locale.US, "%.0f", adx[0]) + " (+DI>-DI)";
        } else if (dirNow < 0 && adx[2] > adx[1]) {
            s.strategy = "S3_SUPERTREND_ADX"; s.side = "SELL";
            s.note = "Supertrend flip DOWN + ADX " + String.format(java.util.Locale.US, "%.0f", adx[0]) + " (-DI>+DI)";
        } else return null;
        return s;
    }

    // ================== S4 — VWAP BOUNCE (session = 96 bars = 24h @15m) ==================
    public static Signal vwapBounce(List<EngineCore.Candle> k, int i) {
        if (i < 30) return null;
        EngineCore.Candle c = k.get(i);
        double vw = vwapSession(k, i, 96);
        if (vw <= 0) return null;
        double a = EngineCore.atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return null;
        double prevVw = vwapSession(k, i - 1, 96);
        boolean bull = c.c > c.o, bear = c.c < c.o;
        double tol = 0.0005;   // touch tolerance 5 bps
        Signal s = new Signal();
        if (c.l <= vw * (1 + tol) && c.c > vw && bull && c.c > prevVw) {
            s.strategy = "S4_VWAP_BOUNCE"; s.side = "BUY";
            s.slPrice = Math.min(c.l, vw) - 0.5 * a;
            s.boundary = vw * 0.997; s.windowBars = DEFAULT_WINDOW;
            s.note = "VWAP bounce (touch + reclaim) — session VWAP " + fpx(vw);
        } else if (c.h >= vw * (1 - tol) && c.c < vw && bear && c.c < prevVw) {
            s.strategy = "S4_VWAP_BOUNCE"; s.side = "SELL";
            s.slPrice = Math.max(c.h, vw) + 0.5 * a;
            s.boundary = vw * 1.003; s.windowBars = DEFAULT_WINDOW;
            s.note = "VWAP reject (touch + close below) — session VWAP " + fpx(vw);
        } else return null;
        s.sigTs = c.ts; s.sigIdx = i; s.refPrice = c.c;
        return s;
    }

    // ================== S5 — PREVIOUS DAY HIGH/LOW BREAKOUT ==================
    /** prevDay = [pdh, pdl] (closed prev UTC day). Close-based breakout + range band
     *  (2%) + volume confirm; boundary = level (failed breakout close-back = dead). */
    public static Signal pdhPdl(List<EngineCore.Candle> k, int i, double[] prevDay) {
        if (prevDay == null || prevDay[0] <= 0 || prevDay[1] <= 0) return null;
        if (i < 25) return null;
        EngineCore.Candle c = k.get(i);
        double vs = volSma(k, i - 1, 20);
        double a = EngineCore.atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return null;
        Signal s = new Signal();
        s.sigTs = c.ts; s.sigIdx = i; s.refPrice = c.c;
        if (c.c > prevDay[0] && c.c <= prevDay[0] * 1.02 && (vs <= 0 || c.v > 0.8 * vs)) {
            s.strategy = "S5_PDH_PDL"; s.side = "BUY";
            s.slPrice = Math.max(prevDay[0] - 1.5 * a, prevDay[1]);
            s.boundary = prevDay[0]; s.windowBars = 8;
            s.note = "Previous DAY HIGH breakout close " + fpx(c.c) + " > " + fpx(prevDay[0]);
        } else if (c.c < prevDay[1] && c.c >= prevDay[1] * 0.98 && (vs <= 0 || c.v > 0.8 * vs)) {
            s.strategy = "S5_PDH_PDL"; s.side = "SELL";
            s.slPrice = Math.min(prevDay[1] + 1.5 * a, prevDay[0]);
            s.boundary = prevDay[1]; s.windowBars = 8;
            s.note = "Previous DAY LOW breakdown close " + fpx(c.c) + " < " + fpx(prevDay[1]);
        } else return null;
        return s;
    }

    // ================== S6 — FUNDING + OI CONTRARIAN FADE ==================
    /** deriv = [fundingRate (0.01 = 1%), oiChangePct24h]. Extreme funding + fresh OI =
     *  crowded side fade. SL = 2×ATR, boundary = 3×ATR, window 12. */
    public static Signal fundingOi(List<EngineCore.Candle> k, int i, double[] deriv) {
        if (deriv == null || deriv.length < 2) return null;
        if (i < 30) return null;
        EngineCore.Candle c = k.get(i);
        double funding = deriv[0], oiChg = deriv[1];
        double a = EngineCore.atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return null;
        Signal s = new Signal();
        s.sigTs = c.ts; s.sigIdx = i; s.refPrice = c.c;
        s.windowBars = 12;
        if (funding >= 0.00075 && oiChg > 5.0) {
            s.strategy = "S6_FUNDING_OI"; s.side = "SELL";
            s.slPrice = c.c + 2 * a; s.boundary = c.c + 3 * a;
            s.note = "Crowded LONG fade — funding " + String.format(java.util.Locale.US, "%.4f%%", funding * 100)
                    + "/8h, OI 24h " + String.format(java.util.Locale.US, "%+.1f%%", oiChg);
        } else if (funding <= -0.00075 && oiChg > 5.0) {
            s.strategy = "S6_FUNDING_OI"; s.side = "BUY";
            s.slPrice = c.c - 2 * a; s.boundary = c.c - 3 * a;
            s.note = "Crowded SHORT fade — funding " + String.format(java.util.Locale.US, "%.4f%%", funding * 100)
                    + "/8h, OI 24h " + String.format(java.util.Locale.US, "%+.1f%%", oiChg);
        } else return null;
        return s;
    }

    // ================== S7 — CANDLE PATTERN + TREND + VOLUME (PDF Part-3) ==================
    /** Engulfing ya hammer, EMA50 trend direction me, volume > 1.1×SMA20. */
    public static Signal candlePattern(List<EngineCore.Candle> k, int i) {
        if (i < 60) return null;
        EngineCore.Candle c = k.get(i), p = k.get(i - 1);
        double e50 = emaAt(k, 50, i), e200 = emaAt(k, 200, i);
        if (Double.isNaN(e50) || Double.isNaN(e200)) return null;
        double a = EngineCore.atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return null;
        double vs = volSma(k, i - 1, 20);
        if (vs <= 0 || c.v <= 1.1 * vs) return null;
        boolean bull = c.c > c.o, bear = c.c < c.o;
        boolean pBull = p.c > p.o;
        boolean engulfBull = bull && !pBull && c.c > p.o && c.o <= p.c;
        boolean engulfBear = bear && pBull && c.c < p.o && c.o >= p.c;
        double body = Math.abs(c.c - c.o), range = c.h - c.l;
        boolean hammerBull = bull && range > 0 && (c.o - c.l) >= 2 * body && (c.h - Math.max(c.o, c.c)) <= 0.35 * body;
        boolean starBear = bear && range > 0 && (c.h - c.o) >= 2 * body && (Math.max(c.o, c.c) - c.l) <= 0.35 * body;
        Signal s = new Signal();
        s.sigTs = c.ts; s.sigIdx = i; s.refPrice = c.c; s.windowBars = DEFAULT_WINDOW;
        if (c.c > e200 && e50 > e200 && (engulfBull || hammerBull)) {
            s.strategy = "S7_CANDLE_PAT"; s.side = "BUY";
            s.slPrice = Math.min(c.l, p.l) - 0.5 * a;
            s.boundary = Math.min(c.l, p.l);
            s.note = engulfBull ? "Bullish engulfing (uptrend, vol confirm)" : "Hammer (uptrend, vol confirm)";
        } else if (c.c < e200 && e50 < e200 && (engulfBear || starBear)) {
            s.strategy = "S7_CANDLE_PAT"; s.side = "SELL";
            s.slPrice = Math.max(c.h, p.h) + 0.5 * a;
            s.boundary = Math.max(c.h, p.h);
            s.note = engulfBear ? "Bearish engulfing (downtrend, vol confirm)" : "Shooting star (downtrend, vol confirm)";
        } else return null;
        return s;
    }

    // ================== S8 — DOW HH/HL STRUCTURE PULLBACK (PDF Part-4) ==================
    /** Uptrend: last 2 pivot highs HH + pivot lows HL; pullback EMA21 tag + bull close.
     *  SL = aakhri HL ke neeche; boundary = EMA50. Mirror SELL. */
    public static Signal dowPullback(List<EngineCore.Candle> k, int i) {
        if (i < 90) return null;
        EngineCore.Candle c = k.get(i);
        double e21 = emaAt(k, 21, i), e50 = emaAt(k, 50, i), e200 = emaAt(k, 200, i);
        if (Double.isNaN(e21) || Double.isNaN(e50) || Double.isNaN(e200)) return null;
        double a = EngineCore.atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return null;
        // pivots: ±3 window extremes (closed bars hi)
        double ph1 = pivotHigh(k, i - 3, 3), ph2 = pivotHigh(k, i - 13, 3);
        double pl1 = pivotLow(k, i - 3, 3), pl2 = pivotLow(k, i - 13, 3);
        if (Double.isNaN(ph1) || Double.isNaN(ph2) || Double.isNaN(pl1) || Double.isNaN(pl2)) return null;
        boolean bull = c.c > c.o, bear = c.c < c.o;
        Signal s = new Signal();
        s.sigTs = c.ts; s.sigIdx = i; s.refPrice = c.c; s.windowBars = DEFAULT_WINDOW;
        if (ph1 > ph2 && pl1 > pl2 && c.c > e200 && c.l <= e21 && c.c > e21 && bull) {
            s.strategy = "S8_DOW_PULLBACK"; s.side = "BUY";
            s.slPrice = pl1 - 0.5 * a;
            s.boundary = e50;
            s.note = "Dow HH+HL uptrend — EMA21 pullback reclaim";
        } else if (ph1 < ph2 && pl1 < pl2 && c.c < e200 && c.h >= e21 && c.c < e21 && bear) {
            s.strategy = "S8_DOW_PULLBACK"; s.side = "SELL";
            s.slPrice = ph1 + 0.5 * a;
            s.boundary = e50;
            s.note = "Dow LH+LL downtrend — EMA21 pullback rejection";
        } else return null;
        return s;
    }
    private static double pivotHigh(List<EngineCore.Candle> k, int at, int w) {
        if (at - w < 0 || at + w >= k.size()) return Double.NaN;
        double v = k.get(at).h;
        for (int j = at - w; j <= at + w; j++) if (k.get(j).h > v) return Double.NaN;
        return v;
    }
    private static double pivotLow(List<EngineCore.Candle> k, int at, int w) {
        if (at - w < 0 || at + w >= k.size()) return Double.NaN;
        double v = k.get(at).l;
        for (int j = at - w; j <= at + w; j++) if (k.get(j).l < v) return Double.NaN;
        return v;
    }

    // ================== S9 — GANN 50% RETRACEMENT BOUNCE (PDF Part-4) ==================
    /** Last swing (pivot ±5) ka 50% level; trend side se wick-pierce + close-back. */
    public static Signal gann50(List<EngineCore.Candle> k, int i) {
        if (i < 210) return null;
        EngineCore.Candle c = k.get(i);
        double e200 = emaAt(k, 200, i);
        if (Double.isNaN(e200)) return null;
        double ph = pivotHigh(k, i - 5, 5), pl = pivotLow(k, i - 5, 5);
        if (Double.isNaN(ph) || Double.isNaN(pl) || ph <= pl) return null;
        double retr = pl + 0.5 * (ph - pl);
        double a = EngineCore.atr(k, 14);
        if (Double.isNaN(a) || a <= 0) return null;
        boolean bull = c.c > c.o, bear = c.c < c.o;
        Signal s = new Signal();
        s.sigTs = c.ts; s.sigIdx = i; s.refPrice = c.c; s.windowBars = DEFAULT_WINDOW;
        if (c.c > e200 && c.l <= retr && c.c > retr && bull) {
            s.strategy = "S9_GANN_50"; s.side = "BUY";
            s.slPrice = pl - 0.5 * a;
            s.boundary = retr * 0.99;
            s.note = "Gann 50% bounce " + fpx(retr) + " (uptrend swing " + fpx(pl) + "→" + fpx(ph) + ")";
        } else if (c.c < e200 && c.h >= retr && c.c < retr && bear) {
            s.strategy = "S9_GANN_50"; s.side = "SELL";
            s.slPrice = ph + 0.5 * a;
            s.boundary = retr * 1.01;
            s.note = "Gann 50% rejection " + fpx(retr) + " (downtrend swing " + fpx(ph) + "→" + fpx(pl) + ")";
        } else return null;
        return s;
    }

    // ================== EVALUATE ALL ==================
    /** Sab 9 strategies ek closed 15m bar par — jitni fire karein sab signals.
     *  deriv = [funding, oiChg24h] ya null (S6 skip). chopAdx < 15 → trend strategies
     *  (S1/S3/S8) skip (chop filter — professional loss-guard). */
    public static List<Signal> evaluateAll(List<EngineCore.Candle> k, int i, double[] prevDay,
                                           double[] deriv, double chopAdx) {
        List<Signal> out = new ArrayList<>();
        boolean chop = !(chopAdx < 0) && chopAdx < 15.0;
        Signal s;
        if (!chop && (s = emaPullback(k, i)) != null) out.add(s);
        if ((s = bbSqueeze(k, i)) != null) out.add(s);
        if (!chop && (s = supertrendAdx(k, i)) != null) out.add(s);
        if ((s = vwapBounce(k, i)) != null) out.add(s);
        if ((s = pdhPdl(k, i, prevDay)) != null) out.add(s);
        if ((s = fundingOi(k, i, deriv)) != null) out.add(s);
        if ((s = candlePattern(k, i)) != null) out.add(s);
        if (!chop && (s = dowPullback(k, i)) != null) out.add(s);
        if ((s = gann50(k, i)) != null) out.add(s);
        return out;
    }

    private static String fpx(double v) {
        return String.format(java.util.Locale.US, v >= 100 ? "%.3f" : "%.6f", v);
    }

    // ================== v1.0 — 5M PLAYBOOK (Z.ai Research "5-Minute Crypto Strategy Guide") ==================
    // 5 saal x 4 coins (BTC/ETH/BNB/SOL) x 49 configs ka no-lookahead backtest — sirf
    // profitable families andar: multi-day breakout riding. Rules guide section 4-7 se
    // EXACT: entry closed 5m bar par, initial SL = atrX x ATR(14), NO TP — exit trail
    // (trailMult x ATR, 4 closed bars ke baad, sirf behtar direction me shift) se.
    // ATR(14) — Wilder TR average (signal use ke liye standard 14-bar TR mean).

    /** Wilder ATR(n) at bar index at (0-based). NaN agar data kam. */
    public static double atrAt(List<EngineCore.Candle> k, int n, int at) {
        if (at < n || n <= 0) return Double.NaN;
        double sum = 0;
        for (int j = at - n + 1; j <= at; j++) sum += tr(k, j);
        return sum / n;
    }

    private static double tr(List<EngineCore.Candle> k, int j) {
        if (j <= 0) return k.get(j).h - k.get(j).l;
        double pc = k.get(j - 1).c;
        return Math.max(k.get(j).h - k.get(j).l,
                Math.max(Math.abs(k.get(j).h - pc), Math.abs(k.get(j).l - pc)));
    }

    /** [highestHigh, lowestLow] of bars [from, to] inclusive. */
    public static double[] hhll(List<EngineCore.Candle> k, int from, int to) {
        double hh = Double.NEGATIVE_INFINITY, ll = Double.POSITIVE_INFINITY;
        for (int j = Math.max(0, from); j <= to && j < k.size(); j++) {
            if (k.get(j).h > hh) hh = k.get(j).h;
            if (k.get(j).l < ll) ll = k.get(j).l;
        }
        return new double[]{hh, ll};
    }

    /** Completed 1h bars ka close series (5m bars se group) — NO lookahead: jis hour me
     *  signal bar hai wo EXCLUDE (:55 bar ka close = mukammal hour close). */
    static List<Double> hourlyCloses(List<EngineCore.Candle> k, int i, int needHours) {
        List<Double> out = new ArrayList<>();
        long curHour = k.get(i).ts / 3600000L;
        for (int j = i; j >= 0 && out.size() < needHours; j--) {
            EngineCore.Candle b = k.get(j);
            if (b.ts / 3600000L >= curHour) continue;                 // current hour incomplete/exclude
            if (b.ts % 3600000L == 3300000L) out.add(b.c);            // :55 bar = completed hour close
        }
        return out;
    }

    /** EMA over double closes (SMA seed) — kam data par NaN. */
    static double emaDoubles(List<Double> v, int n) {
        if (v.size() < n) return Double.NaN;
        double sum = 0;
        for (int i = 0; i < n; i++) sum += v.get(i);
        double e = sum / n;
        double a = 2.0 / (n + 1);
        for (int i = n; i < v.size(); i++) e = v.get(i) * a + e * (1 - a);
        return e;
    }

    /** BB(20,2) width at bar (upper-lower). */
    static double bbWidth(List<EngineCore.Candle> k, int at) {
        double[] bb = bollingerAt(k, 20, at);
        return bb == null ? Double.NaN : (bb[2] - bb[0]);   // upper - lower (full BB width)
    }

    /** Playbook signal factory. */
    private static Signal pb(String key, String side, EngineCore.Candle bar, int i, double sl, String note) {
        Signal s = new Signal();
        s.strategy = key; s.side = side; s.sigTs = bar.ts; s.sigIdx = i; s.refPrice = bar.c;
        s.slPrice = sl; s.boundary = 0; s.windowBars = 0; s.note = note;
        return s;
    }

    /**
     * 5M PLAYBOOK detectors — CLOSED 5m candles, bar i (last closed). Guide rules EXACT:
     *  P1 14D Breakout Rider  : close > 14d HH (4032 bars, signal bar exclude) + vol > 1.3x(288 SMA) | SL 5xATR, trail 8x
     *  P2 10D Trend+Volume    : close > 10d HH (2880) + 1h EMA50>EMA200 + vol 1.3x | SL 4xATR, trail 8x
     *  P3 14D Breakout Classic: close > 14d HH (no vol filter) | SL 3.5xATR, trail 8x
     *  P4 Squeeze Explosion   : BB width percentile < 30% (last 12 bars me) + 14d break | SL 3.5xATR, trail 7x
     * Depth guard: P1/P3/P4 ko poore 4032-bar window ki zaroorat, P2 ko 2880+2400 (1h EMA200) —
     * kam data par koi signal nahi (conservative, no partial-window signals).
     */
    public static List<Signal> evaluatePlaybook(List<EngineCore.Candle> k, int i) {
        List<Signal> out = new ArrayList<>();
        if (k == null || i < 300 || i >= k.size()) return out;
        EngineCore.Candle bar = k.get(i);
        double atr = atrAt(k, 14, i);
        if (!(atr > 0)) return out;
        boolean deep14 = i >= 4032;          // poora 14-din window
        boolean deep10 = i >= 2880;          // poora 10-din window (P2: + 2400 1h EMA seed ke liye 12x200)
        double[] rng14 = hhll(k, i - 4032, i - 1);
        double volSma288 = volSma(k, i, 288);
        boolean volOk = volSma288 > 0 && bar.v > 1.3 * volSma288;
        double close = bar.c;

        // --- P1 14D Breakout Rider (CHAMPION) ---
        if (deep14) {
            if (close > rng14[0] && volOk)
                out.add(pb("P1_14D_RIDER", "BUY", bar, i, close - 5.0 * atr,
                        "14D high break " + fpx(rng14[0]) + " + vol 1.3x — trail 8xATR"));
            if (close < rng14[1] && volOk)
                out.add(pb("P1_14D_RIDER", "SELL", bar, i, close + 5.0 * atr,
                        "14D low break " + fpx(rng14[1]) + " + vol 1.3x — trail 8xATR"));
        }
        // --- P3 14D Breakout Classic (no volume filter) ---
        if (deep14) {
            if (close > rng14[0])
                out.add(pb("P3_14D_CLASSIC", "BUY", bar, i, close - 3.5 * atr,
                        "14D high break (classic, no vol filter) — trail 8xATR"));
            if (close < rng14[1])
                out.add(pb("P3_14D_CLASSIC", "SELL", bar, i, close + 3.5 * atr,
                        "14D low break (classic, no vol filter) — trail 8xATR"));
        }
        // --- P2 10D Trend+Volume Break (1h EMA trend filter) ---
        if (deep10) {
            double[] rng10 = hhll(k, i - 2880, i - 1);
            List<Double> hc = hourlyCloses(k, i, 220);
            double e50 = emaDoubles(hc, 50), e200 = emaDoubles(hc, 200);
            if (!Double.isNaN(e50) && !Double.isNaN(e200)) {
                if (close > rng10[0] && e50 > e200 && volOk)
                    out.add(pb("P2_10D_TREND", "BUY", bar, i, close - 4.0 * atr,
                            "10D high break + 1h trend UP (EMA50 " + fpx(e50) + " > EMA200 " + fpx(e200) + ") — trail 8xATR"));
                if (close < rng10[1] && e50 < e200 && volOk)
                    out.add(pb("P2_10D_TREND", "SELL", bar, i, close + 4.0 * atr,
                            "10D low break + 1h trend DOWN (EMA50 " + fpx(e50) + " < EMA200 " + fpx(e200) + ") — trail 8xATR"));
            }
        }
        // --- P4 Squeeze Explosion (BB width percentile < 30% phir 14d break) ---
        if (deep14) {
            boolean squeeze = false;
            for (int j = Math.max(0, i - 11); j <= i && !squeeze; j += 1) {
                double w = bbWidth(k, j);
                if (Double.isNaN(w)) continue;
                int samples = 0, below = 0;
                for (int q = j - 4032; q <= j; q += 4) {     // stride-4 percentile sample
                    if (q < 20) continue;
                    double wq = bbWidth(k, q);
                    if (Double.isNaN(wq)) continue;
                    samples++;
                    if (wq < w) below++;
                }
                if (samples >= 500 && below * 100.0 / samples < 30.0) squeeze = true;
            }
            if (squeeze) {
                if (close > rng14[0])
                    out.add(pb("P4_SQUEEZE", "BUY", bar, i, close - 3.5 * atr,
                            "Squeeze explosion (BB width pct < 30%) + 14D high break — trail 7xATR"));
                if (close < rng14[1])
                    out.add(pb("P4_SQUEEZE", "SELL", bar, i, close + 3.5 * atr,
                            "Squeeze explosion (BB width pct < 30%) + 14D low break — trail 7xATR"));
            }
        }
        return out;
    }
}
