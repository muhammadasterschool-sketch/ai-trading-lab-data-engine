package com.aitradinglab.engine;

import com.aitradinglab.engine.EngineCore;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

/* loaded from: classes.dex */
public class StrategyPack {
    public static final int DEFAULT_WINDOW = 5;
    public static final String[][] STRATEGIES = {new String[]{"S1_EMA_PULLBACK", "EMA 21/50 + RSI pullback", "Solid base"}, new String[]{"S2_BB_SQUEEZE", "Bollinger squeeze breakout + volume", "Decent"}, new String[]{"S3_SUPERTREND_ADX", "Supertrend flip + ADX", "Decent"}, new String[]{"S4_VWAP_BOUNCE", "VWAP bounce (session)", "Promising"}, new String[]{"S5_PDH_PDL", "Previous day high/low breakout", "Promising"}, new String[]{"S6_FUNDING_OI", "Funding + OI contrarian fade", "Promising"}, new String[]{"S7_CANDLE_PAT", "Engulfing/Hammer + trend + volume", "Part-3"}, new String[]{"S8_DOW_PULLBACK", "Dow HH/HL structure pullback", "Part-4"}, new String[]{"S9_GANN_50", "50% retracement bounce (Gann)", "Part-4"}, new String[]{"P1_14D_RIDER", "14D Breakout Rider (5M Playbook)", "CHAMPION"}, new String[]{"P2_10D_TREND", "10D Trend+Volume Break (Playbook)", "4/4 positive"}, new String[]{"P3_14D_CLASSIC", "14D Breakout Classic (Playbook)", "3/4 positive"}, new String[]{"P4_SQUEEZE", "Squeeze Explosion (Playbook)", "Rare + powerful"}};
    public static final String[] KEYS = {"S1_EMA_PULLBACK", "S2_BB_SQUEEZE", "S3_SUPERTREND_ADX", "S4_VWAP_BOUNCE", "S5_PDH_PDL", "S6_FUNDING_OI", "S7_CANDLE_PAT", "S8_DOW_PULLBACK", "S9_GANN_50", "P1_14D_RIDER", "P2_10D_TREND", "P3_14D_CLASSIC", "P4_SQUEEZE"};

    public static class Signal {
        public double boundary;
        public String note;
        public double refPrice;
        public String side;
        public int sigIdx;
        public long sigTs;
        public double slPrice;
        public String strategy;
        public int windowBars;
    }

    private static double emaAt(List<EngineCore.Candle> list, int i, int i2) {
        if (list.size() < i || i2 < i - 1) {
            return Double.NaN;
        }
        double d = 2.0d / (i + 1);
        int i3 = 0;
        double d2 = 0.0d;
        boolean z = false;
        while (i3 <= i2) {
            double d3 = list.get(i3).c;
            if (z) {
                d3 = ((d3 - d2) * d) + d2;
            }
            d2 = d3;
            i3++;
            z = true;
        }
        return d2;
    }

    private static double rsiAt(List<EngineCore.Candle> list, int i, int i2) {
        if (i2 < i) {
            return Double.NaN;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int i3 = (i2 - i) + 1; i3 <= i2; i3++) {
            double d3 = list.get(i3).c - list.get(i3 - 1).c;
            if (d3 > 0.0d) {
                d += d3;
            } else {
                d2 -= d3;
            }
        }
        double d4 = d2 + d;
        if (d4 == 0.0d) {
            return 50.0d;
        }
        return (d * 100.0d) / d4;
    }

    private static double[] bollingerAt(List<EngineCore.Candle> list, int i, int i2) {
        if (i2 < i - 1) {
            return null;
        }
        double d = 0.0d;
        double d2 = 0.0d;
        for (int i3 = (i2 - i) + 1; i3 <= i2; i3++) {
            double d3 = list.get(i3).c;
            d += d3;
            d2 += d3 * d3;
        }
        double d4 = i;
        double d5 = d / d4;
        double sqrt = Math.sqrt(Math.max(0.0d, (d2 / d4) - (d5 * d5))) * 2.0d;
        return new double[]{d5 - sqrt, d5, sqrt + d5};
    }

    private static double vwapSession(List<EngineCore.Candle> list, int i, int i2) {
        double d = 0.0d;
        double d2 = 0.0d;
        for (int max = Math.max(0, (i - i2) + 1); max <= i; max++) {
            EngineCore.Candle candle = list.get(max);
            d2 += (((candle.h + candle.l) + candle.c) / 3.0d) * candle.v;
            d += candle.v;
        }
        return d > 0.0d ? d2 / d : list.get(i).c;
    }

    private static double volSma(List<EngineCore.Candle> list, int i, int i2) {
        double d = 0.0d;
        if (i < i2) {
            return 0.0d;
        }
        int i3 = i - i2;
        while (true) {
            i3++;
            if (i3 > i) {
                return d / i2;
            }
            d += list.get(i3).v;
        }
    }

    private static int stDirAt(List<EngineCore.Candle> list, int i) {
        double[] supertrend = null;
        if (i >= 12 && (supertrend = EngineCore.supertrend(list.subList(0, i + 1))) != null) {
            return (int) supertrend[1];
        }
        return 0;
    }

    private static double stLineAt(List<EngineCore.Candle> list, int i) {
        double[] supertrend = EngineCore.supertrend(list.subList(0, i + 1));
        if (supertrend == null) {
            return Double.NaN;
        }
        return supertrend[0];
    }

    public static double[] adxAt(List<EngineCore.Candle> list, int i, int i2) {
        int i3 = 0;
        List<EngineCore.Candle> list2 = list;
        int i4 = i;
        int i5 = i2;
        int i6 = i4 * 2;
        if (i5 < i6 + 2) {
            return null;
        }
        int i7 = 1;
        int i8 = (i5 - i6) + 1;
        double d = 0.0d;
        double d2 = 0.0d;
        double d3 = 0.0d;
        while (true) {
            i3 = i5 - i4;
            if (i8 > i3) {
                break;
            }
            EngineCore.Candle candle = list2.get(i8);
            EngineCore.Candle candle2 = list2.get(i8 - 1);
            double d4 = candle.h - candle2.h;
            int i9 = i8;
            double d5 = candle2.l - candle.l;
            d += (d4 <= d5 || d4 <= 0.0d) ? 0.0d : d4;
            if (d5 <= d4 || d5 <= 0.0d) {
                d5 = 0.0d;
            }
            d2 += d5;
            d3 += Math.max(candle.h - candle.l, Math.max(Math.abs(candle.h - candle2.c), Math.abs(candle.l - candle2.c)));
            i8 = i9 + 1;
            list2 = list;
            i4 = i;
            i5 = i2;
            i7 = 1;
        }
        int i10 = i3 + i7;
        int i11 = i2;
        double d6 = 0.0d;
        double d7 = 0.0d;
        double d8 = 0.0d;
        int i12 = 0;
        while (i10 <= i11) {
            EngineCore.Candle candle3 = list.get(i10);
            double d9 = d8;
            EngineCore.Candle candle4 = list.get(i10 - 1);
            double d10 = d7;
            double d11 = d6;
            double d12 = candle3.h - candle4.h;
            double d13 = candle4.l - candle3.l;
            double d14 = i;
            d = (d - (d / d14)) + ((d12 <= d13 || d12 <= 0.0d) ? 0.0d : d12);
            double d15 = d2 - (d2 / d14);
            if (d13 <= d12 || d13 <= 0.0d) {
                d13 = 0.0d;
            }
            double d16 = d15 + d13;
            d3 = (d3 - (d3 / d14)) + Math.max(candle3.h - candle3.l, Math.max(Math.abs(candle3.h - candle4.c), Math.abs(candle3.l - candle4.c)));
            if (d3 <= 0.0d) {
                d8 = d9;
                d6 = d11;
            } else {
                double d17 = (d * 100.0d) / d3;
                double d18 = (d16 * 100.0d) / d3;
                double d19 = d17 + d18;
                double abs = d19 == 0.0d ? 0.0d : (Math.abs(d17 - d18) * 100.0d) / d19;
                i12++;
                d10 = d17;
                d8 = d18;
                d6 = d11 + abs;
            }
            i10++;
            i11 = i2;
            d7 = d10;
            d2 = d16;
        }
        return new double[]{i12 > 0 ? d6 / i12 : 0.0d, d7, d8};
    }

    public static Signal emaPullback(List<EngineCore.Candle> list, int i) {
        if (i < 210) {
            return null;
        }
        EngineCore.Candle candle = list.get(i);
        int i2 = i - 1;
        EngineCore.Candle candle2 = list.get(i2);
        double emaAt = emaAt(list, 21, i);
        double emaAt2 = emaAt(list, 50, i);
        double emaAt3 = emaAt(list, 200, i);
        double rsiAt = rsiAt(list, 14, i);
        double rsiAt2 = rsiAt(list, 14, i2);
        if (Double.isNaN(emaAt) || Double.isNaN(emaAt2) || Double.isNaN(emaAt3) || Double.isNaN(rsiAt) || Double.isNaN(rsiAt2)) {
            return null;
        }
        double atr = EngineCore.atr(list, 14);
        if (Double.isNaN(atr) || atr <= 0.0d) {
            return null;
        }
        boolean z = candle.c > candle.o;
        boolean z2 = candle.c < candle.o;
        Signal signal = new Signal();
        if (candle.c > emaAt3 && emaAt > emaAt2 && rsiAt2 < 42.0d && rsiAt >= 42.0d && rsiAt < 62.0d && z) {
            signal.strategy = "S1_EMA_PULLBACK";
            signal.side = "BUY";
            signal.slPrice = Math.min(candle.l, candle2.l) - (atr * 1.5d);
            signal.boundary = emaAt2;
            signal.windowBars = 5;
            signal.note = "RSI pullback recovery " + String.format(Locale.US, "%.1f→%.1f", Double.valueOf(rsiAt2), Double.valueOf(rsiAt)) + " (uptrend EMA21>50, close>EMA200)";
        } else {
            if (candle.c >= emaAt3 || emaAt >= emaAt2 || rsiAt2 <= 58.0d || rsiAt > 58.0d || rsiAt <= 38.0d || !z2) {
                return null;
            }
            signal.strategy = "S1_EMA_PULLBACK";
            signal.side = "SELL";
            signal.slPrice = Math.max(candle.h, candle2.h) + (atr * 1.5d);
            signal.boundary = emaAt2;
            signal.windowBars = 5;
            signal.note = "RSI pullback rejection " + String.format(Locale.US, "%.1f→%.1f", Double.valueOf(rsiAt2), Double.valueOf(rsiAt)) + " (downtrend EMA21<50, close<EMA200)";
        }
        signal.sigTs = candle.ts;
        signal.sigIdx = i;
        signal.refPrice = candle.c;
        return signal;
    }

    public static Signal bbSqueeze(List<EngineCore.Candle> list, int i) {
        double d = 0.0d;
        if (i < 120) {
            return null;
        }
        EngineCore.Candle candle = list.get(i);
        double[] bollingerAt = bollingerAt(list, 20, i);
        int i2 = i - 1;
        double[] bollingerAt2 = bollingerAt(list, 20, i2);
        if (bollingerAt == null || bollingerAt2 == null || bollingerAt2[1] <= 0.0d) {
            return null;
        }
        double d2 = bollingerAt[1];
        double d3 = bollingerAt[2];
        double d4 = bollingerAt[0];
        double[] dArr = new double[100];
        int i3 = 0;
        for (int i4 = 100; i3 < i4; i4 = 100) {
            double[] bollingerAt3 = bollingerAt(list, 20, (i - 99) + i3);
            if (bollingerAt3 != null) {
                double d5 = bollingerAt3[1];
                if (d5 > 0.0d) {
                    d = (bollingerAt3[2] - bollingerAt3[0]) / d5;
                    dArr[i3] = d;
                    i3++;
                }
            }
            d = 1.0d;
            dArr[i3] = d;
            i3++;
        }
        Arrays.sort(dArr);
        if ((bollingerAt2[2] - bollingerAt2[0]) / bollingerAt2[1] > dArr[19]) {
            return null;
        }
        double volSma = volSma(list, i2, 20);
        if (volSma <= 0.0d) {
            return null;
        }
        Signal signal = new Signal();
        if (candle.c > d3 && candle.v > volSma * 1.2d) {
            signal.strategy = "S2_BB_SQUEEZE";
            signal.side = "BUY";
            signal.slPrice = d2;
            signal.boundary = d2;
            signal.windowBars = 5;
            signal.note = "BB squeeze breakout UP, vol " + String.format(Locale.US, "%.1fx", Double.valueOf(candle.v / volSma));
        } else {
            if (candle.c >= d4 || candle.v <= 1.2d * volSma) {
                return null;
            }
            signal.strategy = "S2_BB_SQUEEZE";
            signal.side = "SELL";
            signal.slPrice = d2;
            signal.boundary = d2;
            signal.windowBars = 5;
            signal.note = "BB squeeze breakout DOWN, vol " + String.format(Locale.US, "%.1fx", Double.valueOf(candle.v / volSma));
        }
        signal.sigTs = candle.ts;
        signal.sigIdx = i;
        signal.refPrice = candle.c;
        return signal;
    }

    public static Signal supertrendAdx(List<EngineCore.Candle> list, int i) {
        double[] adxAt = null;
        if (i < 60) {
            return null;
        }
        int stDirAt = stDirAt(list, i);
        int stDirAt2 = stDirAt(list, i - 1);
        if (stDirAt != 0 && stDirAt2 != 0 && stDirAt != stDirAt2 && (adxAt = adxAt(list, 14, i)) != null && adxAt[0] >= 25.0d) {
            double stLineAt = stLineAt(list, i);
            if (!Double.isNaN(stLineAt) && stLineAt > 0.0d) {
                EngineCore.Candle candle = list.get(i);
                Signal signal = new Signal();
                signal.sigTs = candle.ts;
                signal.sigIdx = i;
                signal.refPrice = candle.c;
                signal.slPrice = stLineAt;
                signal.boundary = stLineAt;
                signal.windowBars = 10;
                if (stDirAt > 0 && adxAt[1] > adxAt[2]) {
                    signal.strategy = "S3_SUPERTREND_ADX";
                    signal.side = "BUY";
                    signal.note = "Supertrend flip UP + ADX " + String.format(Locale.US, "%.0f", Double.valueOf(adxAt[0])) + " (+DI>-DI)";
                } else if (stDirAt < 0 && adxAt[2] > adxAt[1]) {
                    signal.strategy = "S3_SUPERTREND_ADX";
                    signal.side = "SELL";
                    signal.note = "Supertrend flip DOWN + ADX " + String.format(Locale.US, "%.0f", Double.valueOf(adxAt[0])) + " (-DI>+DI)";
                }
                return signal;
            }
        }
        return null;
    }

    public static Signal vwapBounce(List<EngineCore.Candle> list, int i) {
        if (i < 30) {
            return null;
        }
        EngineCore.Candle candle = list.get(i);
        double vwapSession = vwapSession(list, i, 96);
        if (vwapSession <= 0.0d) {
            return null;
        }
        double atr = EngineCore.atr(list, 14);
        if (Double.isNaN(atr) || atr <= 0.0d) {
            return null;
        }
        double vwapSession2 = vwapSession(list, i - 1, 96);
        boolean z = candle.c > candle.o;
        boolean z2 = candle.c < candle.o;
        Signal signal = new Signal();
        if (candle.l <= 1.0005d * vwapSession && candle.c > vwapSession && z && candle.c > vwapSession2) {
            signal.strategy = "S4_VWAP_BOUNCE";
            signal.side = "BUY";
            signal.slPrice = Math.min(candle.l, vwapSession) - (atr * 0.5d);
            signal.boundary = 0.997d * vwapSession;
            signal.windowBars = 5;
            signal.note = "VWAP bounce (touch + reclaim) — session VWAP " + fpx(vwapSession);
        } else {
            if (candle.h < 0.9995d * vwapSession || candle.c >= vwapSession || !z2 || candle.c >= vwapSession2) {
                return null;
            }
            signal.strategy = "S4_VWAP_BOUNCE";
            signal.side = "SELL";
            signal.slPrice = Math.max(candle.h, vwapSession) + (atr * 0.5d);
            signal.boundary = 1.003d * vwapSession;
            signal.windowBars = 5;
            signal.note = "VWAP reject (touch + close below) — session VWAP " + fpx(vwapSession);
        }
        signal.sigTs = candle.ts;
        signal.sigIdx = i;
        signal.refPrice = candle.c;
        return signal;
    }

    public static Signal pdhPdl(List<EngineCore.Candle> list, int i, double[] dArr) {
        if (dArr == null || dArr[0] <= 0.0d || dArr[1] <= 0.0d) {
            return null;
        }
        if (i < 25) {
            return null;
        }
        EngineCore.Candle candle = list.get(i);
        double volSma = volSma(list, i - 1, 20);
        double atr = EngineCore.atr(list, 14);
        if (Double.isNaN(atr) || atr <= 0.0d) {
            return null;
        }
        Signal signal = new Signal();
        signal.sigTs = candle.ts;
        signal.sigIdx = i;
        signal.refPrice = candle.c;
        if (candle.c > dArr[0] && candle.c <= dArr[0] * 1.02d && (volSma <= 0.0d || candle.v > volSma * 0.8d)) {
            signal.strategy = "S5_PDH_PDL";
            signal.side = "BUY";
            signal.slPrice = Math.max(dArr[0] - (atr * 1.5d), dArr[1]);
            signal.boundary = dArr[0];
            signal.windowBars = 8;
            signal.note = "Previous DAY HIGH breakout close " + fpx(candle.c) + " > " + fpx(dArr[0]);
        } else {
            if (candle.c >= dArr[1] || candle.c < dArr[1] * 0.98d) {
                return null;
            }
            if (volSma > 0.0d && candle.v <= volSma * 0.8d) {
                return null;
            }
            signal.strategy = "S5_PDH_PDL";
            signal.side = "SELL";
            signal.slPrice = Math.min(dArr[1] + (atr * 1.5d), dArr[0]);
            signal.boundary = dArr[1];
            signal.windowBars = 8;
            signal.note = "Previous DAY LOW breakdown close " + fpx(candle.c) + " < " + fpx(dArr[1]);
        }
        return signal;
    }

    public static Signal fundingOi(List<EngineCore.Candle> list, int i, double[] dArr) {
        if (dArr == null || dArr.length < 2) {
            return null;
        }
        if (i < 30) {
            return null;
        }
        EngineCore.Candle candle = list.get(i);
        double d = dArr[0];
        double d2 = dArr[1];
        double atr = EngineCore.atr(list, 14);
        if (Double.isNaN(atr) || atr <= 0.0d) {
            return null;
        }
        Signal signal = new Signal();
        signal.sigTs = candle.ts;
        signal.sigIdx = i;
        signal.refPrice = candle.c;
        signal.windowBars = 12;
        if (d >= 7.5E-4d && d2 > 5.0d) {
            signal.strategy = "S6_FUNDING_OI";
            signal.side = "SELL";
            signal.slPrice = candle.c + (2.0d * atr);
            signal.boundary = candle.c + (atr * 3.0d);
            signal.note = "Crowded LONG fade — funding " + String.format(Locale.US, "%.4f%%", Double.valueOf(d * 100.0d)) + "/8h, OI 24h " + String.format(Locale.US, "%+.1f%%", Double.valueOf(d2));
        } else {
            if (d > -7.5E-4d || d2 <= 5.0d) {
                return null;
            }
            signal.strategy = "S6_FUNDING_OI";
            signal.side = "BUY";
            signal.slPrice = candle.c - (2.0d * atr);
            signal.boundary = candle.c - (atr * 3.0d);
            signal.note = "Crowded SHORT fade — funding " + String.format(Locale.US, "%.4f%%", Double.valueOf(d * 100.0d)) + "/8h, OI 24h " + String.format(Locale.US, "%+.1f%%", Double.valueOf(d2));
        }
        return signal;
    }

    /* JADX WARN: Removed duplicated region for block: B:51:0x00fa  */
    /* JADX WARN: Removed duplicated region for block: B:60:0x0141  */
    /* JADX WARN: Removed duplicated region for block: B:72:0x0178  */
    /* JADX WARN: Removed duplicated region for block: B:83:0x01a7 A[ADDED_TO_REGION, ORIG_RETURN, RETURN] */
    /*
        Code decompiled incorrectly, please refer to instructions dump.
    */
    public static Signal candlePattern(List<EngineCore.Candle> object, int n) {
        block4: {
            block5: {
                block6: {
                    block9: {
                        Signal signal = null;
                        block8: {
                            boolean bl = false;
                            double d = 0.0d;
                            double d2 = 0.0d;
                            double d3 = 0.0d;
                            EngineCore.Candle candle = null;
                            int n2 = 0;
                            EngineCore.Candle candle2 = null;
                            block7: {
                                if (n < 60) {
                                    return null;
                                }
                                candle2 = object.get(n);
                                n2 = n - 1;
                                candle = object.get(n2);
                                d3 = StrategyPack.emaAt(object, 50, n);
                                d2 = StrategyPack.emaAt(object, 200, n);
                                if (Double.isNaN(d3) || Double.isNaN(d2)) break block4;
                                d = EngineCore.atr(object, 14);
                                if (Double.isNaN(d) || d <= 0.0) break block5;
                                double d4 = StrategyPack.volSma(object, n2, 20);
                                if (d4 <= 0.0 || candle2.v <= d4 * 1.1) break block6;
                                boolean bl2 = candle2.c > candle2.o;
                                n2 = candle2.c < candle2.o ? 1 : 0;
                                bl = candle.c > candle.o;
                                boolean bl3 = bl2 && !bl && candle2.c > candle.o && candle2.o <= candle.c;
                                bl = n2 != 0 && bl && candle2.c < candle.o && candle2.o >= candle.c;
                                double d5 = Math.abs(candle2.c - candle2.o);
                                d4 = candle2.h - candle2.l;
                                bl2 = bl2 && d4 > 0.0 && candle2.o - candle2.l >= d5 * 2.0 && candle2.h - Math.max(candle2.o, candle2.c) <= d5 * 0.35;
                                n2 = n2 != 0 && d4 > 0.0 && candle2.h - candle2.o >= 2.0 * d5 && Math.max(candle2.o, candle2.c) - candle2.l <= d5 * 0.35 ? 1 : 0;
                                signal = new Signal();
                                signal.sigTs = candle2.ts;
                                signal.sigIdx = n;
                                signal.refPrice = candle2.c;
                                signal.windowBars = 5;
                                if (!(candle2.c > d2) || !(d3 > d2) || !bl3 && !bl2) break block7;
                                signal.strategy = "S7_CANDLE_PAT";
                                signal.side = "BUY";
                                signal.slPrice = Math.min(candle2.l, candle.l) - d * 0.5;
                                signal.boundary = Math.min(candle2.l, candle.l);
                                signal.note = bl3 ? "Bullish engulfing (uptrend, vol confirm)" : "Hammer (uptrend, vol confirm)";
                                break block8;
                            }
                            if (!(candle2.c < d2) || !(d3 < d2) || !bl && n2 == 0) break block9;
                            signal.strategy = "S7_CANDLE_PAT";
                            signal.side = "SELL";
                            signal.slPrice = Math.max(candle2.h, candle.h) + d * 0.5;
                            signal.boundary = Math.max(candle2.h, candle.h);
                            signal.note = bl ? "Bearish engulfing (downtrend, vol confirm)" : "Shooting star (downtrend, vol confirm)";
                        }
                        return signal;
                    }
                    return null;
                }
                return null;
            }
            return null;
        }
        return null;
    }

    public static Signal dowPullback(List<EngineCore.Candle> list, int i) {
        if (i < 90) {
            return null;
        }
        EngineCore.Candle candle = list.get(i);
        double emaAt = emaAt(list, 21, i);
        double emaAt2 = emaAt(list, 50, i);
        double emaAt3 = emaAt(list, 200, i);
        if (Double.isNaN(emaAt) || Double.isNaN(emaAt2) || Double.isNaN(emaAt3)) {
            return null;
        }
        double atr = EngineCore.atr(list, 14);
        if (Double.isNaN(atr) || atr <= 0.0d) {
            return null;
        }
        int i2 = i - 3;
        double pivotHigh = pivotHigh(list, i2, 3);
        int i3 = i - 13;
        double pivotHigh2 = pivotHigh(list, i3, 3);
        double pivotLow = pivotLow(list, i2, 3);
        double pivotLow2 = pivotLow(list, i3, 3);
        if (Double.isNaN(pivotHigh) || Double.isNaN(pivotHigh2) || Double.isNaN(pivotLow) || Double.isNaN(pivotLow2)) {
            return null;
        }
        boolean z = candle.c > candle.o;
        boolean z2 = candle.c < candle.o;
        Signal signal = new Signal();
        signal.sigTs = candle.ts;
        signal.sigIdx = i;
        signal.refPrice = candle.c;
        signal.windowBars = 5;
        if (pivotHigh > pivotHigh2 && pivotLow > pivotLow2 && candle.c > emaAt3 && candle.l <= emaAt && candle.c > emaAt && z) {
            signal.strategy = "S8_DOW_PULLBACK";
            signal.side = "BUY";
            signal.slPrice = pivotLow - (atr * 0.5d);
            signal.boundary = emaAt2;
            signal.note = "Dow HH+HL uptrend — EMA21 pullback reclaim";
        } else {
            if (pivotHigh >= pivotHigh2 || pivotLow >= pivotLow2 || candle.c >= emaAt3 || candle.h < emaAt || candle.c >= emaAt || !z2) {
                return null;
            }
            signal.strategy = "S8_DOW_PULLBACK";
            signal.side = "SELL";
            signal.slPrice = pivotHigh + (atr * 0.5d);
            signal.boundary = emaAt2;
            signal.note = "Dow LH+LL downtrend — EMA21 pullback rejection";
        }
        return signal;
    }

    private static double pivotHigh(List<EngineCore.Candle> list, int i, int i2) {
        int i3 = 0;
        int i4 = i - i2;
        if (i4 < 0 || (i3 = i2 + i) >= list.size()) {
            return Double.NaN;
        }
        double d = list.get(i).h;
        while (i4 <= i3) {
            if (list.get(i4).h > d) {
                return Double.NaN;
            }
            i4++;
        }
        return d;
    }

    private static double pivotLow(List<EngineCore.Candle> list, int i, int i2) {
        int i3 = 0;
        int i4 = i - i2;
        if (i4 < 0 || (i3 = i2 + i) >= list.size()) {
            return Double.NaN;
        }
        double d = list.get(i).l;
        while (i4 <= i3) {
            if (list.get(i4).l < d) {
                return Double.NaN;
            }
            i4++;
        }
        return d;
    }

    public static Signal gann50(List<EngineCore.Candle> list, int i) {
        if (i < 210) {
            return null;
        }
        EngineCore.Candle candle = list.get(i);
        double emaAt = emaAt(list, 200, i);
        if (Double.isNaN(emaAt)) {
            return null;
        }
        int i2 = i - 5;
        double pivotHigh = pivotHigh(list, i2, 5);
        double pivotLow = pivotLow(list, i2, 5);
        if (Double.isNaN(pivotHigh) || Double.isNaN(pivotLow) || pivotHigh <= pivotLow) {
            return null;
        }
        double d = ((pivotHigh - pivotLow) * 0.5d) + pivotLow;
        double atr = EngineCore.atr(list, 14);
        if (Double.isNaN(atr) || atr <= 0.0d) {
            return null;
        }
        boolean z = candle.c > candle.o;
        boolean z2 = candle.c < candle.o;
        Signal signal = new Signal();
        signal.sigTs = candle.ts;
        signal.sigIdx = i;
        signal.refPrice = candle.c;
        signal.windowBars = 5;
        if (candle.c > emaAt && candle.l <= d && candle.c > d && z) {
            signal.strategy = "S9_GANN_50";
            signal.side = "BUY";
            signal.slPrice = pivotLow - (atr * 0.5d);
            signal.boundary = 0.99d * d;
            signal.note = "Gann 50% bounce " + fpx(d) + " (uptrend swing " + fpx(pivotLow) + "→" + fpx(pivotHigh) + ")";
        } else {
            if (candle.c >= emaAt || candle.h < d || candle.c >= d || !z2) {
                return null;
            }
            signal.strategy = "S9_GANN_50";
            signal.side = "SELL";
            signal.slPrice = pivotHigh + (atr * 0.5d);
            signal.boundary = 1.01d * d;
            signal.note = "Gann 50% rejection " + fpx(d) + " (downtrend swing " + fpx(pivotHigh) + "→" + fpx(pivotLow) + ")";
        }
        return signal;
    }

    public static List<Signal> evaluateAll(List<EngineCore.Candle> list, int i, double[] dArr, double[] dArr2, double d) {
        Signal dowPullback = null;
        Signal supertrendAdx = null;
        Signal emaPullback = null;
        ArrayList arrayList = new ArrayList();
        boolean z = d >= 0.0d && d < 15.0d;
        if (!z && (emaPullback = emaPullback(list, i)) != null) {
            arrayList.add(emaPullback);
        }
        Signal bbSqueeze = bbSqueeze(list, i);
        if (bbSqueeze != null) {
            arrayList.add(bbSqueeze);
        }
        if (!z && (supertrendAdx = supertrendAdx(list, i)) != null) {
            arrayList.add(supertrendAdx);
        }
        Signal vwapBounce = vwapBounce(list, i);
        if (vwapBounce != null) {
            arrayList.add(vwapBounce);
        }
        Signal pdhPdl = pdhPdl(list, i, dArr);
        if (pdhPdl != null) {
            arrayList.add(pdhPdl);
        }
        Signal fundingOi = fundingOi(list, i, dArr2);
        if (fundingOi != null) {
            arrayList.add(fundingOi);
        }
        Signal candlePattern = candlePattern(list, i);
        if (candlePattern != null) {
            arrayList.add(candlePattern);
        }
        if (!z && (dowPullback = dowPullback(list, i)) != null) {
            arrayList.add(dowPullback);
        }
        Signal gann50 = gann50(list, i);
        if (gann50 != null) {
            arrayList.add(gann50);
        }
        return arrayList;
    }

    private static String fpx(double d) {
        return String.format(Locale.US, d >= 100.0d ? "%.3f" : "%.6f", Double.valueOf(d));
    }

    public static double atrAt(List<EngineCore.Candle> list, int i, int i2) {
        if (i2 < i || i <= 0) {
            return Double.NaN;
        }
        double d = 0.0d;
        for (int i3 = (i2 - i) + 1; i3 <= i2; i3++) {
            d += tr(list, i3);
        }
        return d / i;
    }

    private static double tr(List<EngineCore.Candle> list, int i) {
        if (i <= 0) {
            return list.get(i).h - list.get(i).l;
        }
        double d = list.get(i - 1).c;
        return Math.max(list.get(i).h - list.get(i).l, Math.max(Math.abs(list.get(i).h - d), Math.abs(list.get(i).l - d)));
    }

    public static double[] hhll(List<EngineCore.Candle> list, int i, int i2) {
        double d = Double.NEGATIVE_INFINITY;
        double d2 = Double.POSITIVE_INFINITY;
        for (int max = Math.max(0, i); max <= i2 && max < list.size(); max++) {
            if (list.get(max).h > d) {
                d = list.get(max).h;
            }
            if (list.get(max).l < d2) {
                d2 = list.get(max).l;
            }
        }
        return new double[]{d, d2};
    }

    static List<Double> hourlyCloses(List<EngineCore.Candle> list, int i, int i2) {
        ArrayList arrayList = new ArrayList();
        long j = list.get(i).ts / 3600000;
        while (i >= 0 && arrayList.size() < i2) {
            EngineCore.Candle candle = list.get(i);
            if (candle.ts / 3600000 < j && candle.ts % 3600000 == 3300000) {
                arrayList.add(Double.valueOf(candle.c));
            }
            i--;
        }
        return arrayList;
    }

    static double emaDoubles(List<Double> list, int i) {
        if (list.size() < i) {
            return Double.NaN;
        }
        double d = 0.0d;
        for (int i2 = 0; i2 < i; i2++) {
            d += list.get(i2).doubleValue();
        }
        double d2 = d / i;
        double d3 = 2.0d / (i + 1);
        while (i < list.size()) {
            d2 = (d2 * (1.0d - d3)) + (list.get(i).doubleValue() * d3);
            i++;
        }
        return d2;
    }

    static double bbWidth(List<EngineCore.Candle> list, int i) {
        double[] bollingerAt = bollingerAt(list, 20, i);
        if (bollingerAt == null) {
            return Double.NaN;
        }
        return bollingerAt[2] - bollingerAt[0];
    }

    private static Signal pb(String str, String str2, EngineCore.Candle candle, int i, double d, String str3) {
        Signal signal = new Signal();
        signal.strategy = str;
        signal.side = str2;
        signal.sigTs = candle.ts;
        signal.sigIdx = i;
        signal.refPrice = candle.c;
        signal.slPrice = d;
        signal.boundary = 0.0d;
        signal.windowBars = 0;
        signal.note = str3;
        return signal;
    }

    public static List<Signal> evaluatePlaybook(List<EngineCore.Candle> list, int i) {
        double d = 0.0d;
        int i2 = 0;
        String str = null;
        String str2 = null;
        ArrayList arrayList = new ArrayList();
        if (list != null && i >= 300 && i < list.size()) {
            EngineCore.Candle candle = list.get(i);
            double atrAt = atrAt(list, 14, i);
            if (atrAt <= 0.0d) {
                return arrayList;
            }
            boolean z = i >= 4032;
            boolean z2 = i >= 2880;
            int i3 = i - 1;
            double[] hhll = hhll(list, i - 4032, i3);
            double volSma = volSma(list, i, 288);
            boolean z3 = volSma > 0.0d && candle.v > volSma * 1.3d;
            double d2 = candle.c;
            if (z) {
                if (d2 <= hhll[0] || !z3) {
                    str2 = " + vol 1.3x — trail 8xATR";
                    d = d2;
                    i2 = i3;
                } else {
                    str2 = " + vol 1.3x — trail 8xATR";
                    d = d2;
                    i2 = i3;
                    arrayList.add(pb("P1_14D_RIDER", "BUY", candle, i, d2 - (atrAt * 5.0d), "14D high break " + fpx(hhll[0]) + " + vol 1.3x — trail 8xATR"));
                }
                if (d < hhll[1] && z3) {
                    arrayList.add(pb("P1_14D_RIDER", "SELL", candle, i, d + (5.0d * atrAt), "14D low break " + fpx(hhll[1]) + str2));
                }
            } else {
                d = d2;
                i2 = i3;
            }
            if (z) {
                if (d > hhll[0]) {
                    arrayList.add(pb("P3_14D_CLASSIC", "BUY", candle, i, d - (atrAt * 3.5d), "14D high break (classic, no vol filter) — trail 8xATR"));
                }
                if (d < hhll[1]) {
                    arrayList.add(pb("P3_14D_CLASSIC", "SELL", candle, i, d + (atrAt * 3.5d), "14D low break (classic, no vol filter) — trail 8xATR"));
                }
            }
            if (z2) {
                double[] hhll2 = hhll(list, i - 2880, i2);
                List<Double> hourlyCloses = hourlyCloses(list, i, 220);
                double emaDoubles = emaDoubles(hourlyCloses, 50);
                double emaDoubles2 = emaDoubles(hourlyCloses, 200);
                if (!Double.isNaN(emaDoubles) && !Double.isNaN(emaDoubles2)) {
                    if (d <= hhll2[0] || emaDoubles <= emaDoubles2 || !z3) {
                        str = ") — trail 8xATR";
                    } else {
                        str = ") — trail 8xATR";
                        arrayList.add(pb("P2_10D_TREND", "BUY", candle, i, d - (atrAt * 4.0d), "10D high break + 1h trend UP (EMA50 " + fpx(emaDoubles) + " > EMA200 " + fpx(emaDoubles2) + ") — trail 8xATR"));
                    }
                    if (d < hhll2[1] && emaDoubles < emaDoubles2 && z3) {
                        arrayList.add(pb("P2_10D_TREND", "SELL", candle, i, d + (4.0d * atrAt), "10D low break + 1h trend DOWN (EMA50 " + fpx(emaDoubles) + " < EMA200 " + fpx(emaDoubles2) + str));
                    }
                }
            }
            if (z) {
                boolean z4 = false;
                for (int max = Math.max(0, i - 11); max <= i && !z4; max++) {
                    double bbWidth = bbWidth(list, max);
                    if (!Double.isNaN(bbWidth)) {
                        int i4 = 0;
                        int i5 = 0;
                        for (int i6 = max - 4032; i6 <= max; i6 += 4) {
                            if (i6 >= 20) {
                                double bbWidth2 = bbWidth(list, i6);
                                if (!Double.isNaN(bbWidth2)) {
                                    i4++;
                                    if (bbWidth2 < bbWidth) {
                                        i5++;
                                    }
                                }
                            }
                        }
                        if (i4 >= 500 && (i5 * 100.0d) / i4 < 30.0d) {
                            z4 = true;
                        }
                    }
                }
                if (z4) {
                    if (d > hhll[0]) {
                        arrayList.add(pb("P4_SQUEEZE", "BUY", candle, i, d - (atrAt * 3.5d), "Squeeze explosion (BB width pct < 30%) + 14D high break — trail 7xATR"));
                    }
                    if (d < hhll[1]) {
                        arrayList.add(pb("P4_SQUEEZE", "SELL", candle, i, d + (atrAt * 3.5d), "Squeeze explosion (BB width pct < 30%) + 14D low break — trail 7xATR"));
                    }
                }
            }
        }
        return arrayList;
    }
}
