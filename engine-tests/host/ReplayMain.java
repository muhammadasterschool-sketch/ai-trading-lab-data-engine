package com.aitradinglab.engine;

import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * REPLAY TUNER (host-only) — engine ke EXACT rules par real Binance 5m klines replay.
 *
 * Rules replicated 1:1 from EngineCore (v1.0, PRO-FILTER-FREE build):
 *   - 3C MASTER: C1+C2 body>=70% same dir, C3 opposite protected, 5-candle window,
 *     close-based invalidation, fill = max(trigger, open), SL opposite extreme,
 *     BE @ +1R, TP @ +tpR (default 3R). Fee-edge guard (TP move < RT fees = skip).
 *   - PLAYBOOK P1-P4 (StrategyPack.evaluatePlaybook — REAL code called): SL = mult x ATR
 *     (P1 5x, P2 4x, P3/P4 3.5x), NO TP, trail after 4 bars (P4 7x, others 8x ATR),
 *     notional cap, fee-edge 2xATR.
 *   - PACK S1-S9 (StrategyPack.evaluateAll — REAL code called): entry at signal close,
 *     SL = signal slPrice, TP +2R, BE @ +1R.
 *   - Sizing: risk = equity * riskPct / 100 per trade, qty = risk / slDist,
 *     notional cap = equity * levCap (tunable — paper leverage).
 *   - Fees 0.05%/side + slip 2bps each side (slipEntry/slipExit parity).
 *   - Guards: 15 min symbol cooldown after SL; 3 consecutive SL on symbol = 1h block.
 *
 * Usage: java ReplayMain <days> <riskPct> <levCap> <tpR> <mask> [hourlyReport] [entryBufPct] [slBufPct]
 *   mask bit0=3C(1) bit1=PB(2) bit2=PACK(4); e.g. 7 = all, 3 = 3C+PB
 * Output: daily P&L, final equity, max DD, hourly curve tail (1h target check).
 */
public class ReplayMain {
    static final double TAKER_FEE = 0.0005;
    static final double SLIP_BPS = 2.0;
    static final long TF_MS = 5L * 60 * 1000;

    static class Trade {
        String sym, side, tier;
        double entry, sl, tp, qty, riskAmt, trail;
        int barsHeld;
        boolean beMoved;
        long openTs;
    }

    public static void main(String[] a) throws Exception {
        int days = a.length > 0 ? Integer.parseInt(a[0]) : 3;
        double riskPct = a.length > 1 ? Double.parseDouble(a[1]) : 1.0;
        double levCap = a.length > 2 ? Double.parseDouble(a[2]) : 0.95;
        double tpR = a.length > 3 ? Double.parseDouble(a[3]) : 3.0;
        int mask = a.length > 4 ? Integer.parseInt(a[4]) : 7;
        boolean hourly = a.length > 5 && "1".equals(a[5]);
        final double entryBuf = a.length > 6 ? Double.parseDouble(a[6]) / 100.0 : 0.0;
        final double slBuf = a.length > 7 ? Double.parseDouble(a[7]) / 100.0 : 0.0;
        String symSel = a.length > 8 ? a[8] : "all";   // all | majors | alts
        if (a.length > 9) X4_SIGMA = Double.parseDouble(a[9]);
        if (a.length > 10) X4_TP = Double.parseDouble(a[10]);
        final boolean beOn = a.length > 11 ? "1".equals(a[11]) : true;
        final int cdMin = a.length > 12 ? Integer.parseInt(a[12]) : 15;   // cooldown minutes after SL
        final int offsetDays = a.length > 13 ? Integer.parseInt(a[13]) : 0;   // replay window ko itne din peeche shift karo

        String[] allSyms = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT"};
        java.util.List<String> symList = new java.util.ArrayList<>();
        for (String s : allSyms) {
            boolean major = s.equals("BTCUSDT") || s.equals("ETHUSDT") || s.equals("BNBUSDT");
            if (symSel.equals("all") || (symSel.equals("majors") && major) || (symSel.equals("alts") && !major)) symList.add(s);
        }
        String[] syms = symList.toArray(new String[0]);
        Map<String, List<EngineCore.Candle>> data = new HashMap<>();
        for (String s : syms) {
            List<EngineCore.Candle> k = fetchKlines(s, days);
            data.put(s, k);
            System.err.println("[fetch] " + s + " — " + k.size() + " 5m bars");
        }

        double bal = 100.0, peak = 100.0, maxDD = 0;
        double dayStart = 100.0;
        long startTs = Long.MAX_VALUE, endTs = 0;
        for (List<EngineCore.Candle> k : data.values())
            if (!k.isEmpty()) { startTs = Math.min(startTs, k.get(0).ts); endTs = Math.max(endTs, k.get(k.size() - 1).ts); }
        int bars = (int) ((endTs - startTs) / TF_MS) + 1;
        long replayFrom = endTs - (days + offsetDays) * 86400000L;
        long replayTo = replayFrom + days * 86400000L;

        List<Trade> open = new ArrayList<>();
        Map<String, Long> cooldownUntil = new HashMap<>();
        Map<String, Integer> consecLoss = new HashMap<>();
        Map<String, Long> lastBarEval = new HashMap<>();
        int totalTrades = 0, wins = 0;
        double grossWin = 0, grossLoss = 0, feesPaid = 0;
        StringBuilder hourlySb = new StringBuilder();

        // per-tier stats (konsa strategy tier profit/loss de raha hai)
        java.util.Map<String, int[]> tierN = new java.util.HashMap<>();
        java.util.Map<String, double[]> tierPnl = new java.util.HashMap<>();
        // 3C pending setups (walk3C parity — koi look-ahead NAHI)
        Map<String, Object[]> pending3C = new HashMap<>();   // sym -> {side, boundary, trigger, slP, c3Idx}

        // bar-wise chronological walk
        for (int b = 0; b < bars; b++) {
            long ts = startTs + b * TF_MS;
            if (ts < replayFrom) continue;
            if (ts > replayTo) break;

            // 1) manage open trades on this bar (SL first — conservative), then BE/TP
            List<Trade> stillOpen = new ArrayList<>();
            for (Trade t : open) {
                List<EngineCore.Candle> k = data.get(t.sym);
                int i = (int) ((ts - k.get(0).ts) / TF_MS);
                if (i < 0 || i >= k.size()) { stillOpen.add(t); continue; }
                EngineCore.Candle c = k.get(i);
                boolean buy = "BUY".equals(t.side);
                double exit = Double.NaN; String reason = null;
                boolean hitSl = buy ? c.l <= t.sl : c.h >= t.sl;
                boolean hitTp = t.tp > 0 && (buy ? c.h >= t.tp : c.l <= t.tp);
                if (hitSl) { exit = t.sl; reason = "SL"; }
                else if (hitTp) { exit = t.tp; reason = "TP"; }
                else if (!t.beMoved && beOn && (t.tier.startsWith("3C") || t.tier.startsWith("X"))) {
                    double rDist = Math.abs(t.riskAmt / t.qty);
                    boolean beHit = buy ? c.h >= t.entry + rDist : c.l <= t.entry - rDist;
                    if (beHit) { t.sl = t.entry; t.beMoved = true; }
                }
                if (reason == null && t.tier.startsWith("PB")) {
                    // playbook trail: closed-bar replay (bars 0-3 initial SL, phir trail)
                    t.barsHeld++;
                    if (t.barsHeld > 4) {
                        double atr = StrategyPack.atrAt(k, 14, i);
                        double tm = t.tier.contains("P4") ? 7.0 : 8.0;
                        double cand = buy ? c.c - tm * atr : c.c + tm * atr;
                        t.trail = t.trail == 0 ? cand : (buy ? Math.max(t.trail, cand) : Math.min(t.trail, cand));
                        boolean hitTrail = buy ? c.l <= t.trail : c.h >= t.trail;
                        if (hitTrail) { exit = t.trail; reason = "TRAIL"; }
                    }
                }
                if (reason != null) {
                    double exitFill = slipExit(exit, t.side);
                    double fees = (t.qty * t.entry + t.qty * exitFill) * TAKER_FEE;
                    feesPaid += fees;
                    double pnl = (buy ? exitFill - t.entry : t.entry - exitFill) * t.qty - fees;
                    bal += pnl; totalTrades++;
                    int[] tn = tierN.computeIfAbsent(t.tier, x -> new int[]{0, 0});
                    tn[0]++; if (pnl > 0) tn[1]++;
                    double[] tp2 = tierPnl.computeIfAbsent(t.tier, x -> new double[]{0});
                    tp2[0] += pnl;
                    if (pnl > 0) { wins++; grossWin += pnl; } else grossLoss += -pnl;
                    if ("SL".equals(reason) || (pnl < 0 && "TRAIL".equals(reason))) {
                        cooldownUntil.put(t.sym, ts + cdMin * 60_000L);
                        int cl = consecLoss.getOrDefault(t.sym, 0) + 1;
                        consecLoss.put(t.sym, cl);
                        if (cl >= 3) cooldownUntil.put(t.sym, ts + 60 * 60_000L);
                    } else consecLoss.put(t.sym, 0);
                } else stillOpen.add(t);
            }
            open = stillOpen;

            // 2) new signals on CLOSED bar i-1 (bar ts abhi live hai — engine parity)
            int ci = (int) ((ts - startTs) / TF_MS) - 1;
            if (ci < 0) continue;

            // --- 3C MASTER (walk3C parity: pending state machine, koi look-ahead nahi) ---
            if ((mask & 1) != 0) {
                for (String sym : syms) {
                    List<EngineCore.Candle> k = data.get(sym);
                    int i = (int) ((ts - k.get(0).ts) / TF_MS) - 1;
                    if (i < 2 || i >= k.size()) continue;
                    EngineCore.Candle c = k.get(i);
                    // 1) pending setup ko isi bar par evaluate karo (fill ABHI ho sakta hai)
                    Object[] pend = pending3C.get(sym);
                    if (pend != null) {
                        String pSide = (String) pend[0];
                        double pBoundary = (Double) pend[1], pTrigger = (Double) pend[2], pSl = (Double) pend[3];
                        int c3Idx = (Integer) pend[4];
                        int winIdx = i - c3Idx;
                        if (winIdx > 5) {
                            pending3C.remove(sym);   // SETUP_EXPIRED
                        } else {
                            boolean buy = "BUY".equals(pSide);
                            boolean closeInvalid = buy ? c.c < pBoundary : c.c > pBoundary;
                            boolean broke = buy ? c.h > pTrigger : c.l < pTrigger;
                            if (broke && closeInvalid) {
                                pending3C.remove(sym);   // SETUP_INVALIDATED (ambiguous)
                            } else if (closeInvalid) {
                                pending3C.remove(sym);   // SETUP_INVALIDATED
                            } else if (broke) {
                                double fill = buy ? Math.max(pTrigger, c.o) : Math.min(pTrigger, c.o);
                                pending3C.remove(sym);
                                if (cooldownUntil.getOrDefault(sym, 0L) <= ts)
                                    open3C(fill, pSide, sym, pSl, ts, bal, riskPct, levCap, tpR, open);
                            }
                        }
                        continue;   // isi bar par setup evaluate hua — naya setup agle bar se
                    }
                    // 2) naya setup detect karo (C1=i-2, C2=i-1, C3=i)
                    if (cooldownUntil.getOrDefault(sym, 0L) > ts) continue;
                    EngineCore.Candle c3 = c, c1 = k.get(i - 2), c2 = k.get(i - 1);
                    boolean g1 = c1.c > c1.o, g2 = c2.c > c2.o, g3 = c3.c > c3.o;
                    boolean b1 = bodyPct(c1) >= 0.70, b2 = bodyPct(c2) >= 0.70;
                    if (b1 && b2 && g1 && g2 && !g3 && c3.c >= Math.min(c1.l, c2.l)) {
                        double zH = Math.max(c1.h, Math.max(c2.h, c3.h)), zL = Math.min(c1.l, Math.min(c2.l, c3.l));
                        pending3C.put(sym, new Object[]{"BUY", zL, zH * (1 + entryBuf), zL * (1 - slBuf), i});
                    } else if (b1 && b2 && !g1 && !g2 && g3 && c3.c <= Math.max(c1.h, c2.h)) {
                        double zH = Math.max(c1.h, Math.max(c2.h, c3.h)), zL = Math.min(c1.l, Math.min(c2.l, c3.l));
                        pending3C.put(sym, new Object[]{"SELL", zH, zL * (1 - entryBuf), zH * (1 + slBuf), i});
                    }
                }
            }

            // --- PLAYBOOK + PACK ---
            for (String sym : syms) {
                List<EngineCore.Candle> k = data.get(sym);
                int i = (int) ((ts - k.get(0).ts) / TF_MS) - 1;
                if (i < 500 || i >= k.size()) continue;
                Long done = lastBarEval.get(sym + "|pb");
                if (done != null && done == k.get(i).ts) continue;
                lastBarEval.put(sym + "|pb", k.get(i).ts);

                if ((mask & 2) != 0 && cooldownUntil.getOrDefault(sym, 0L) <= ts) {
                    // PB sirf BTC/ETH/BNB/SOL par
                    if (sym.equals("BTCUSDT") || sym.equals("ETHUSDT") || sym.equals("BNBUSDT") || sym.equals("SOLUSDT")) {
                        List<StrategyPack.Signal> sigs = StrategyPack.evaluatePlaybook(k, i);
                        for (StrategyPack.Signal s : sigs) {
                            boolean dup = false;
                            for (Trade t : open) if (t.sym.equals(sym) && t.tier.equals("PB:" + s.strategy)) dup = true;
                            if (dup) continue;
                            openPb(sym, s, k, i, bal, riskPct, levCap, open);
                        }
                    }
                }
                if ((mask & 4) != 0 && cooldownUntil.getOrDefault(sym, 0L) <= ts) {
                    double[] prevDay = EngineCore.prevDayHighLow(k.subList(0, i + 1));
                    double[] adx = StrategyPack.adxAt(k, 14, i);
                    double chopAdx = adx == null ? -1 : adx[0];
                    double[] deriv = fundingOiCached(sym);
                    List<StrategyPack.Signal> sigs = StrategyPack.evaluateAll(k, i, prevDay, deriv, chopAdx);
                    for (StrategyPack.Signal s : sigs) {
                        if (s.strategy.startsWith("P")) continue;   // PB alag se
                        boolean dup = false;
                        for (Trade t : open) if (t.sym.equals(sym) && t.tier.equals("PDF:" + s.strategy)) dup = true;
                        if (dup) continue;
                        openPdf(sym, s, k, i, bal, riskPct, levCap, open);
                    }
                }
                // ===== EXPERIMENTAL TIER X (edge search — "different things") =====
                if ((mask & 8) != 0) x1Donchian(k, i, sym, bal, riskPct, levCap, open, cooldownUntil, ts);
                if ((mask & 16) != 0) x2RsiFade(k, i, sym, bal, riskPct, levCap, open, cooldownUntil, ts);
                if ((mask & 32) != 0) x3MomentumBurst(k, i, sym, bal, riskPct, levCap, open, cooldownUntil, ts);
                if ((mask & 64) != 0) x4VwapDevFade(k, i, sym, bal, riskPct, levCap, open, cooldownUntil, ts);
                if ((mask & 128) != 0) x5VwapTrend(k, i, sym, bal, riskPct, levCap, open, cooldownUntil, ts);
                if ((mask & 256) != 0) x6ConfluenceFade(k, i, sym, bal, riskPct, levCap, open, cooldownUntil, ts);
                if ((mask & 512) != 0) x7RegimeFade(k, i, sym, bal, riskPct, levCap, open, cooldownUntil, ts);
            }

            // 3) equity track (har 5m par)
            double eq = bal;
            for (Trade t : open) {
                List<EngineCore.Candle> k = data.get(t.sym);
                int i = (int) ((ts - k.get(0).ts) / TF_MS);
                if (i < 0 || i >= k.size()) continue;
                double px = k.get(i).c;
                eq += ("BUY".equals(t.side) ? px - t.entry : t.entry - px) * t.qty;
            }
            peak = Math.max(peak, eq);
            if (peak > 0) maxDD = Math.max(maxDD, (peak - eq) / peak * 100);
            if (hourly && ts % 3600000L < TF_MS)
                hourlySb.append(String.format("%d,%.2f%n", ts / 3600000L, eq));
            long day = ts / 86400000L;
            long prevDayTs = ts - TF_MS;
            if (prevDayTs >= replayFrom && prevDayTs / 86400000L != day) {
                System.out.println(String.format("[day] equity=%.2f (dayPnl %+.2f%%)", bal, (bal - dayStart) / dayStart * 100));
                dayStart = bal;
            }
        }

        double netPct = (bal - 100.0) / 100.0 * 100;
        double pf = grossLoss > 0 ? grossWin / grossLoss : 99;
        System.out.println("=== RESULT risk=" + riskPct + "% lev=" + levCap + " tpR=" + tpR + " mask=" + mask
                + " days=" + days + " ===");
        System.out.println(String.format(
                "final=$%.2f net=%+.1f%% trades=%d win=%.1f%% PF=%.2f maxDD=%.1f%% fees=$%.2f openLeft=%d",
                bal, netPct, totalTrades, totalTrades > 0 ? 100.0 * wins / totalTrades : 0, pf, maxDD, feesPaid, open.size()));
        if (hourly && hourlySb.length() > 0) {
            // hourly % return distribution — $100→$200/1h check
            String[] lines = hourlySb.toString().trim().split("\n");
            double bestH = 0, worstH = 0; int nH = 0; double sumH = 0;
            List<Double> hrs = new ArrayList<>();
            for (int i = 1; i < lines.length; i++) {
                String[] p1 = lines[i - 1].split(","), p2 = lines[i].split(",");
                double e1 = Double.parseDouble(p1[1]), e2 = Double.parseDouble(p2[1]);
                double r = (e2 - e1) / e1 * 100;
                hrs.add(r); sumH += r; nH++;
                bestH = Math.max(bestH, r); worstH = Math.min(worstH, r);
            }
            System.out.println("hourly returns: n=" + nH + " avg=" + String.format("%+.2f%%", sumH / Math.max(1, nH))
                    + " best=" + String.format("%+.2f%%", bestH) + " worst=" + String.format("%+.2f%%", worstH));
            java.util.Collections.sort(hrs);
            if (!hrs.isEmpty())
                System.out.println("hourly p50=" + String.format("%+.2f%%", hrs.get(hrs.size() / 2))
                        + " p90=" + String.format("%+.2f%%", hrs.get((int) (hrs.size() * 0.9))));
        }
        // per-tier breakdown (kaun profit/loss de raha hai)
        System.out.println("--- TIER BREAKDOWN ---");
        for (Map.Entry<String, int[]> e : tierN.entrySet()) {
            double pnl = tierPnl.get(e.getKey())[0];
            int[] n = e.getValue();
            System.out.println(String.format("%-22s n=%-4d win=%-5.1f pnl=%+.2f", e.getKey(), n[0],
                    n[0] > 0 ? 100.0 * n[1] / n[0] : 0, pnl));
        }
    }

    static double bodyPct(EngineCore.Candle c) {
        double rng = c.h - c.l;
        return rng <= 0 ? 0 : Math.abs(c.c - c.o) / rng;
    }

    // ===== X1: Donchian(96=8h) breakout + 1h EMA trend + volume — TP 2.5R, BE @1R =====
    static void x1Donchian(List<EngineCore.Candle> k, int i, String sym, double bal, double riskPct,
                           double levCap, List<Trade> open, Map<String, Long> cd, long ts) {
        if (i < 200 || cd.getOrDefault(sym, 0L) > ts) return;
        EngineCore.Candle bar = k.get(i);
        double hh = -1, ll = Double.MAX_VALUE;
        for (int j = i - 96; j < i; j++) { if (k.get(j).h > hh) hh = k.get(j).h; if (k.get(j).l < ll) ll = k.get(j).l; }
        // 1h trend: EMA12 of hourly closes (last 12h)
        List<Double> hc = new ArrayList<>();
        for (int j = i - 11; j <= i; j++) hc.add(k.get(j).c);   // approx 5m->1h proxy (12 bars)
        // proper hourly: every 12th close
        hc.clear();
        for (int j = i - 143; j <= i; j += 12) if (j >= 0) hc.add(k.get(j).c);
        if (hc.size() < 10) return;
        double eSum = 0; for (double v : hc.subList(Math.max(0, hc.size() - 12), hc.size())) eSum += v;
        double eAvg = eSum / Math.min(12, hc.size());
        double volSma = 0; for (int j = i - 95; j < i; j++) volSma += k.get(j).v; volSma /= 96;
        String side = null;
        if (bar.c > hh && bar.c > eAvg && volSma > 0 && bar.v > 1.2 * volSma) side = "BUY";
        else if (bar.c < ll && bar.c < eAvg && volSma > 0 && bar.v > 1.2 * volSma) side = "SELL";
        if (side == null) return;
        double atr = StrategyPack.atrAt(k, 14, i);
        if (!(atr > 0)) return;
        double slDist = 1.2 * atr;
        boolean buy = "BUY".equals(side);
        openX("X1_DONCH", sym, side, bar.c, slDist, 2.5, bal, riskPct, levCap, open);
    }

    // ===== X2: RSI(14) extreme mean-reversion — TP 1.2R, SL 1R (no BE) =====
    static void x2RsiFade(List<EngineCore.Candle> k, int i, String sym, double bal, double riskPct,
                          double levCap, List<Trade> open, Map<String, Long> cd, long ts) {
        if (i < 50 || cd.getOrDefault(sym, 0L) > ts) return;
        EngineCore.Candle bar = k.get(i);
        double g = 0, l = 0;
        for (int j = i - 13; j <= i; j++) { double ch = k.get(j).c - k.get(j - 1).c; if (ch > 0) g += ch; else l -= ch; }
        if (g + l == 0) return;
        double rsi = 100 * g / (g + l);
        double atr = StrategyPack.atrAt(k, 14, i);
        if (!(atr > 0)) return;
        if (rsi < 22) openX("X2_RSI_FADE", sym, "BUY", bar.c, 1.0 * atr, 1.2, bal, riskPct, levCap, open);
        else if (rsi > 78) openX("X2_RSI_FADE", sym, "SELL", bar.c, 1.0 * atr, 1.2, bal, riskPct, levCap, open);
    }

    // ===== X3: momentum burst — 3 same-dir candles total body > 1.5xATR + vol 1.5x → continuation =====
    static void x3MomentumBurst(List<EngineCore.Candle> k, int i, String sym, double bal, double riskPct,
                                double levCap, List<Trade> open, Map<String, Long> cd, long ts) {
        if (i < 60 || cd.getOrDefault(sym, 0L) > ts) return;
        EngineCore.Candle c1 = k.get(i - 2), c2 = k.get(i - 1), c3 = k.get(i);
        double atr = StrategyPack.atrAt(k, 14, i);
        if (!(atr > 0)) return;
        double body = Math.abs(c3.c - c3.o) + Math.abs(c2.c - c2.o) + Math.abs(c1.c - c1.o);
        boolean up = c1.c > c1.o && c2.c > c2.o && c3.c > c3.o;
        boolean dn = c1.c < c1.o && c2.c < c2.o && c3.c < c3.o;
        double volSma = 0; for (int j = i - 47; j < i; j++) volSma += k.get(j).v; volSma /= 48;
        if (up && body > 1.5 * atr && volSma > 0 && c3.v > 1.5 * volSma)
            openX("X3_MOMO", sym, "BUY", c3.c, 1.5 * atr, 2.0, bal, riskPct, levCap, open);
        else if (dn && body > 1.5 * atr && volSma > 0 && c3.v > 1.5 * volSma)
            openX("X3_MOMO", sym, "SELL", c3.c, 1.5 * atr, 2.0, bal, riskPct, levCap, open);
    }

    // ===== X4: VWAP deviation fade (24h vwap, SIGMA sigma) — TP X4TP, SL 1R =====
    static double X4_SIGMA = 2.2, X4_TP = 1.5;
    static void x4VwapDevFade(List<EngineCore.Candle> k, int i, String sym, double bal, double riskPct,
                              double levCap, List<Trade> open, Map<String, Long> cd, long ts) {
        if (i < 300 || cd.getOrDefault(sym, 0L) > ts) return;
        double pv = 0, vv = 0;
        int from = Math.max(0, i - 287);
        for (int j = from; j <= i; j++) { EngineCore.Candle c = k.get(j); double tp = (c.h + c.l + c.c) / 3; pv += tp * c.v; vv += c.v; }
        if (vv <= 0) return;
        double vwap = pv / vv;
        double var = 0; int n = 0;
        for (int j = from; j <= i; j++) { double d = k.get(j).c - vwap; var += d * d; n++; }
        double sd = Math.sqrt(var / Math.max(1, n));
        if (sd <= 0) return;
        EngineCore.Candle bar = k.get(i);
        double atr = StrategyPack.atrAt(k, 14, i);
        if (!(atr > 0)) return;
        if (bar.c > vwap + X4_SIGMA * sd) openX("X4_VWAP_FADE", sym, "SELL", bar.c, 1.0 * atr, X4_TP, bal, riskPct, levCap, open);
        else if (bar.c < vwap - X4_SIGMA * sd) openX("X4_VWAP_FADE", sym, "BUY", bar.c, 1.0 * atr, X4_TP, bal, riskPct, levCap, open);
    }

    // ===== X5: X4 (sigma 3.5 fade) + 1h TREND ALIGNMENT — dip-buy in uptrend, rip-sell in downtrend =====
    static void x5VwapTrend(List<EngineCore.Candle> k, int i, String sym, double bal, double riskPct,
                            double levCap, List<Trade> open, Map<String, Long> cd, long ts) {
        if (i < 300 || cd.getOrDefault(sym, 0L) > ts) return;
        // 1h trend: EMA20 of hourly closes
        java.util.List<Double> hc = new java.util.ArrayList<>();
        for (int j = i - 239; j <= i; j += 12) if (j >= 0) hc.add(k.get(j).c);
        if (hc.size() < 20) return;
        double mult = 2.0 / 21.0, e = hc.get(0);
        for (int j = 1; j < hc.size(); j++) e = (hc.get(j) - e) * mult + e;
        double pv = 0, vv = 0;
        int from = Math.max(0, i - 287);
        for (int j = from; j <= i; j++) { EngineCore.Candle c = k.get(j); double tp = (c.h + c.l + c.c) / 3; pv += tp * c.v; vv += c.v; }
        if (vv <= 0) return;
        double vwap = pv / vv;
        double var = 0; int n = 0;
        for (int j = from; j <= i; j++) { double d = k.get(j).c - vwap; var += d * d; n++; }
        double sd = Math.sqrt(var / Math.max(1, n));
        if (sd <= 0) return;
        EngineCore.Candle bar = k.get(i);
        double atr = StrategyPack.atrAt(k, 14, i);
        if (!(atr > 0)) return;
        boolean upTrend = bar.c > e, dnTrend = bar.c < e;
        if (upTrend && bar.c < vwap - X5_SIGMA * sd) openX("X5_VWAP_TREND", sym, "BUY", bar.c, 1.0 * atr, X4_TP, bal, riskPct, levCap, open);
        else if (dnTrend && bar.c > vwap + X5_SIGMA * sd) openX("X5_VWAP_TREND", sym, "SELL", bar.c, 1.0 * atr, X4_TP, bal, riskPct, levCap, open);
    }
    static double X5_SIGMA = 3.5;

    // ===== X6: CONFLUENCE fade — VWAP dev >= X4_SIGMA AND RSI extreme (double confirmation) =====
    static void x6ConfluenceFade(List<EngineCore.Candle> k, int i, String sym, double bal, double riskPct,
                                 double levCap, List<Trade> open, Map<String, Long> cd, long ts) {
        if (i < 300 || cd.getOrDefault(sym, 0L) > ts) return;
        double pv = 0, vv = 0;
        int from = Math.max(0, i - 287);
        for (int j = from; j <= i; j++) { EngineCore.Candle c = k.get(j); double tp = (c.h + c.l + c.c) / 3; pv += tp * c.v; vv += c.v; }
        if (vv <= 0) return;
        double vwap = pv / vv;
        double var = 0; int n = 0;
        for (int j = from; j <= i; j++) { double d = k.get(j).c - vwap; var += d * d; n++; }
        double sd = Math.sqrt(var / Math.max(1, n));
        if (sd <= 0) return;
        EngineCore.Candle bar = k.get(i);
        double g = 0, l = 0;
        for (int j = i - 13; j <= i; j++) { double ch = k.get(j).c - k.get(j - 1).c; if (ch > 0) g += ch; else l -= ch; }
        if (g + l == 0) return;
        double rsi = 100 * g / (g + l);
        double atr = StrategyPack.atrAt(k, 14, i);
        if (!(atr > 0)) return;
        if (bar.c < vwap - X4_SIGMA * sd && rsi < 30) openX("X6_CONFL", sym, "BUY", bar.c, 1.0 * atr, X4_TP, bal, riskPct, levCap, open);
        else if (bar.c > vwap + X4_SIGMA * sd && rsi > 70) openX("X6_CONFL", sym, "SELL", bar.c, 1.0 * atr, X4_TP, bal, riskPct, levCap, open);
    }

    // ===== X7: X6 + REGIME GATE — sirf ranging market (ADX56 < 22) mein fade =====
    static double X7_ADX = 22.0;
    static void x7RegimeFade(List<EngineCore.Candle> k, int i, String sym, double bal, double riskPct,
                             double levCap, List<Trade> open, Map<String, Long> cd, long ts) {
        if (i < 300 || cd.getOrDefault(sym, 0L) > ts) return;
        double[] adx = StrategyPack.adxAt(k, 56, i);   // 5m ADX(56) ≈ 1h ADX(14) time-equivalent
        if (adx == null || adx[0] >= X7_ADX) return;   // strong trend = fade NAHI
        double pv = 0, vv = 0;
        int from = Math.max(0, i - 287);
        for (int j = from; j <= i; j++) { EngineCore.Candle c = k.get(j); double tp = (c.h + c.l + c.c) / 3; pv += tp * c.v; vv += c.v; }
        if (vv <= 0) return;
        double vwap = pv / vv;
        double var = 0; int n = 0;
        for (int j = from; j <= i; j++) { double d = k.get(j).c - vwap; var += d * d; n++; }
        double sd = Math.sqrt(var / Math.max(1, n));
        if (sd <= 0) return;
        EngineCore.Candle bar = k.get(i);
        double g = 0, l = 0;
        for (int j = i - 13; j <= i; j++) { double ch = k.get(j).c - k.get(j - 1).c; if (ch > 0) g += ch; else l -= ch; }
        if (g + l == 0) return;
        double rsi = 100 * g / (g + l);
        double atr = StrategyPack.atrAt(k, 14, i);
        if (!(atr > 0)) return;
        if (bar.c < vwap - X4_SIGMA * sd && rsi < 30) openX("X7_REGIME", sym, "BUY", bar.c, 1.0 * atr, X4_TP, bal, riskPct, levCap, open);
        else if (bar.c > vwap + X4_SIGMA * sd && rsi > 70) openX("X7_REGIME", sym, "SELL", bar.c, 1.0 * atr, X4_TP, bal, riskPct, levCap, open);
    }

    static void openX(String tier, String sym, String side, double price, double slDist, double tpR,
                      double bal, double riskPct, double levCap, List<Trade> open) {
        for (Trade t : open) if (t.sym.equals(sym) && t.tier.equals(tier)) return;
        boolean buy = "BUY".equals(side);
        double entry = slipEntry(price, side);
        if (!(slDist > 0)) return;
        double tpDist = tpR * slDist;
        if (tpDist / entry * 10000 < 14) return;
        double risk = bal * riskPct / 100.0;
        double qty = risk / slDist;
        if (qty * entry > bal * levCap) qty = bal * levCap / entry;
        if (qty <= 0) return;
        Trade t = new Trade();
        t.sym = sym; t.side = side; t.tier = tier; t.entry = entry;
        t.sl = buy ? entry - slDist : entry + slDist;
        t.tp = buy ? entry + tpDist : entry - tpDist;
        t.qty = qty; t.riskAmt = slDist * qty; t.openTs = 0;
        open.add(t);
    }

    static double slipEntry(double p, String side) {
        double s = SLIP_BPS / 10000.0;
        return "BUY".equals(side) ? p * (1 + s) : p * (1 - s);
    }

    static double slipExit(double p, String side) {
        double s = SLIP_BPS / 10000.0;
        return "BUY".equals(side) ? p * (1 - s) : p * (1 + s);
    }

    static void open3C(double fill, String side, String sym, double slP, long ts,
                       double bal, double riskPct, double levCap, double tpR, List<Trade> open) {
        for (Trade t : open) if (t.sym.equals(sym) && t.tier.startsWith("3C")) return;
        boolean buy = "BUY".equals(side);
        double entry = slipEntry(fill, side);
        double slDist = Math.abs(entry - slP);
        if (slDist <= 0) return;
        double tpDist = tpR * slDist;
        // fee-edge guard: TP move < round-trip fees (0.05%x2 + slip 2bps x2) = 14bps → skip
        if (tpDist / entry * 10000 < 14) return;
        double risk = bal * riskPct / 100.0;
        double qty = risk / slDist;
        if (qty * entry > bal * levCap) qty = bal * levCap / entry;
        if (qty <= 0) return;
        Trade t = new Trade();
        t.sym = sym; t.side = side; t.tier = "3C"; t.entry = entry;
        t.sl = buy ? entry - slDist : entry + slDist;
        t.tp = buy ? entry + tpDist : entry - tpDist;
        t.qty = qty; t.riskAmt = slDist * qty; t.openTs = ts;
        open.add(t);
    }

    static void openPb(String sym, StrategyPack.Signal s, List<EngineCore.Candle> k, int i,
                       double bal, double riskPct, double levCap, List<Trade> open) {
        double atr = StrategyPack.atrAt(k, 14, i);
        if (!(atr > 0)) return;
        double price = k.get(i).c;
        double slMult = s.strategy.startsWith("P1") ? 5.0 : s.strategy.startsWith("P2") ? 4.0 : 3.5;
        double slDist = slMult * atr;
        if (!(slDist > 0)) return;
        // fee-edge guard: expected 2xATR move < RT fees → skip
        if (2 * atr / price * 10000 < 14) return;
        boolean buy = "BUY".equals(s.side);
        double entry = slipEntry(price, s.side);
        double risk = bal * riskPct / 100.0;
        double qty = risk / slDist;
        if (qty * entry > bal * levCap) qty = bal * levCap / entry;
        if (qty <= 0) return;
        Trade t = new Trade();
        t.sym = sym; t.side = s.side; t.tier = "PB:" + s.strategy; t.entry = entry;
        t.sl = buy ? entry - slDist : entry + slDist;
        t.tp = 0; t.qty = qty; t.riskAmt = slDist * qty; t.openTs = k.get(i).ts; t.trail = 0; t.barsHeld = 0;
        open.add(t);
    }

    static void openPdf(String sym, StrategyPack.Signal s, List<EngineCore.Candle> k, int i,
                        double bal, double riskPct, double levCap, List<Trade> open) {
        double price = k.get(i).c;
        double rd = Math.abs(price - s.slPrice);
        if (rd <= 0) return;
        double tpDist = 2 * rd;
        if (tpDist / price * 10000 < 14) return;
        boolean buy = "BUY".equals(s.side);
        double entry = slipEntry(price, s.side);
        double risk = bal * riskPct / 100.0;
        double qty = risk / rd;
        if (qty * entry > bal * levCap) qty = bal * levCap / entry;
        if (qty <= 0) return;
        Trade t = new Trade();
        t.sym = sym; t.side = s.side; t.tier = "PDF:" + s.strategy; t.entry = entry;
        t.sl = buy ? entry - rd : entry + rd;
        t.tp = buy ? entry + tpDist : entry - tpDist;
        t.qty = qty; t.riskAmt = rd * qty; t.openTs = k.get(i).ts;
        open.add(t);
    }

    static Map<String, double[]> fundingCache = new HashMap<>();

    static double[] fundingOiCached(String sym) {
        if (fundingCache.containsKey(sym)) return fundingCache.get(sym);
        try {
            String fr = httpGet("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=" + sym, 8000);
            if (fr == null) { fundingCache.put(sym, null); return null; }
            double funding = new org.json.JSONObject(fr).optDouble("lastFundingRate", Double.NaN);
            if (Double.isNaN(funding)) { fundingCache.put(sym, null); return null; }
            double[] out = new double[]{funding, 0};
            fundingCache.put(sym, out);
            return out;
        } catch (Throwable t) { fundingCache.put(sym, null); return null; }
    }

    static List<EngineCore.Candle> fetchKlines(String sym, int days) throws Exception {
        List<EngineCore.Candle> out = new ArrayList<>();
        long endTime = System.currentTimeMillis();
        int pages = (days * 288) / 1000 + 6;   // +14d PB warmup ke liye buffer
        for (int pg = 0; pg < pages; pg++) {
            String url = "https://api.binance.com/api/v3/klines?symbol=" + sym + "&interval=5m&limit=1000&endTime=" + endTime;
            String body = httpGet(url, 15000);
            if (body == null) break;
            org.json.JSONArray arr = new org.json.JSONArray(body);
            if (arr.length() == 0) break;
            for (int i = arr.length() - 1; i >= 0; i--) {
                org.json.JSONArray o = arr.getJSONArray(i);
                EngineCore.Candle c = new EngineCore.Candle();
                c.ts = o.getLong(0); c.o = o.getDouble(1); c.h = o.getDouble(2);
                c.l = o.getDouble(3); c.c = o.getDouble(4); c.v = o.getDouble(5);
                out.add(0, c);
            }
            long oldest = arr.getJSONArray(0).getLong(0);
            endTime = oldest - 1;
            if (arr.length() < 1000) break;
            Thread.sleep(120);
        }
        return out;
    }

    static String httpGet(String url, int timeoutMs) {
        try {
            HttpURLConnection conn = (HttpURLConnection) new URL(url).openConnection();
            conn.setConnectTimeout(timeoutMs); conn.setReadTimeout(timeoutMs);
            byte[] b = conn.getInputStream().readAllBytes();
            return new String(b, StandardCharsets.UTF_8);
        } catch (Throwable t) { return null; }
    }
}
