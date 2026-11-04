package com.aitradinglab.engine;

import com.aitradinglab.engine.EngineCore;
import com.aitradinglab.engine.StrategyPack;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import org.json.JSONException;
import org.json.JSONObject;

/* loaded from: classes.dex */
public class AiTrainer {

    public static class Res {
        public String key;
        public int n = 0;
        public int nOos = 0;
        public double wr = 0.0d;
        public double pf = 0.0d;
        public double expR = 0.0d;
        public double oosWr = 0.0d;
        public double oosPf = 0.0d;
        public double weight = 1.0d;
        public int enabled = 1;
        public String from = "";
    }

    public interface SigFn {
        List<StrategyPack.Signal> at(List<EngineCore.Candle> list, int i);
    }

    public static class T {
        public double r;
        public long ts;
    }

    public static int enabledFrom(int i, double d) {
        return (i != 0 && d < 0.9d) ? 0 : 1;
    }

    public static double weightFrom(double d) {
        if (d >= 1.5d) {
            return 1.3d;
        }
        if (d >= 1.3d) {
            return 1.15d;
        }
        if (d >= 1.1d) {
            return 1.0d;
        }
        return d >= 0.9d ? 0.8d : 0.6d;
    }

    public static List<T> simulate(List<EngineCore.Candle> list, SigFn sigFn, double d, double d2) {
        List<EngineCore.Candle> list2 = null;
        ArrayList arrayList = null;
        double d3 = 0.0d;
        int i = 0;
        boolean z = false;
        boolean z2 = false;
        double d4 = 0.0d;
        double d5 = 0.0d;
        double d6 = 0.0d;
        List<EngineCore.Candle> list3 = list;
        ArrayList arrayList2 = new ArrayList();
        if (list3 == null || list.size() < 60) {
            return arrayList2;
        }
        double d7 = d2 / 10000.0d;
        double d8 = 0.0d;
        int i2 = 0;
        int i3 = -1;
        boolean z3 = false;
        boolean z4 = false;
        double d9 = 0.0d;
        double d10 = 0.0d;
        double d11 = 0.0d;
        while (true) {
            boolean z5 = true;
            if (i2 >= list.size() - 1) {
                return arrayList2;
            }
            int i4 = i2;
            if (i3 >= 0) {
                EngineCore.Candle candle = list3.get(i4);
                arrayList = arrayList2;
                if (!z3) {
                    if (z4 && candle.h >= d9 + d10) {
                        d8 = Math.max(d8, d9);
                        z3 = true;
                    }
                    if (!z4 && candle.l <= d9 - d10) {
                        d8 = Math.min(d8, d9);
                        z3 = true;
                    }
                }
                boolean z6 = !z4 ? candle.h < d8 : candle.l > d8;
                double d12 = d8;
                if (!z4 ? candle.l > d11 : candle.h < d11) {
                    z5 = false;
                }
                if (z6 || z5 || i4 - i3 >= 96) {
                    if (z6) {
                        d6 = d12;
                    } else {
                        d6 = z5 ? d11 : candle.c;
                    }
                    double d13 = (z4 ? d6 - d9 : d9 - d6) - ((d9 + d6) * (d + d7));
                    T t = new T();
                    list2 = list;
                    boolean z7 = z3;
                    t.ts = list2.get(i3).ts;
                    t.r = d10 > 0.0d ? d13 / d10 : 0.0d;
                    if (t.r > 2.05d) {
                        t.r = 2.05d;
                    }
                    if (t.r < -1.3d) {
                        t.r = -1.3d;
                    }
                    arrayList.add(t);
                    z3 = z7;
                    d8 = d12;
                    i3 = -1;
                } else {
                    list2 = list;
                    d8 = d12;
                }
            } else {
                list2 = list3;
                arrayList = arrayList2;
                List<StrategyPack.Signal> at = sigFn.at(list2, i4);
                if (at == null || at.isEmpty()) {
                    d3 = d8;
                    i = i3;
                    z = z3;
                    z2 = z4;
                    d4 = d9;
                    d5 = d10;
                } else {
                    StrategyPack.Signal signal = at.get(0);
                    int i5 = i4 + 1;
                    d3 = d8;
                    i = i3;
                    z = z3;
                    double d14 = list2.get(i5).o * ("BUY".equals(signal.side) ? d7 + 1.0d : 1.0d - d7);
                    z2 = z4;
                    d4 = d9;
                    d5 = d10;
                    double abs = Math.abs(signal.refPrice - signal.slPrice);
                    if (abs > 0.0d && d14 > 0.0d) {
                        double d15 = signal.slPrice;
                        boolean equals = "BUY".equals(signal.side);
                        double d16 = 2.0d * abs;
                        d11 = equals ? d16 + d14 : d14 - d16;
                        EngineCore.Candle candle2 = list2.get(i5);
                        boolean z8 = !equals ? candle2.h < d15 : candle2.l > d15;
                        if (!equals ? candle2.l > d11 : candle2.h < d11) {
                            z5 = false;
                        }
                        if (z8 || z5) {
                            double d17 = z8 ? d15 : d11;
                            double d18 = (equals ? d17 - d14 : d14 - d17) - ((d14 + d17) * (d + d7));
                            T t2 = new T();
                            t2.ts = list2.get(i5).ts;
                            t2.r = abs > 0.0d ? d18 / abs : 0.0d;
                            if (t2.r > 2.05d) {
                                t2.r = 2.05d;
                            }
                            if (t2.r < -1.3d) {
                                t2.r = -1.3d;
                            }
                            arrayList.add(t2);
                            z4 = equals;
                            i3 = -1;
                        } else {
                            i3 = i5;
                            z4 = equals;
                        }
                        z3 = false;
                        d10 = abs;
                        d9 = d14;
                        d8 = d15;
                    }
                }
                z4 = z2;
                i3 = i;
                d8 = d3;
                z3 = z;
                d9 = d4;
                d10 = d5;
            }
            arrayList2 = arrayList;
            i2 = i4 + 1;
            list3 = list2;
        }
    }

    public static double[] stats(List<T> list) {
        double d = 0.0d;
        double d2 = 0.0d;
        double d3 = 0.0d;
        double d4 = 0.0d;
        for (T t : list) {
            d += t.r;
            if (t.r > 0.0d) {
                d2 += 1.0d;
                d3 += t.r;
            } else if (t.r < 0.0d) {
                d4 += -t.r;
            }
        }
        int size = list.size();
        double d5 = size;
        return new double[]{d5, size > 0 ? d2 / d5 : 0.0d, d4 > 0.0d ? d3 / d4 : d3 > 0.0d ? 99 : 0, size > 0 ? d / d5 : 0.0d};
    }

    public static double[] oosStats(List<T> list, long j) {
        ArrayList arrayList = new ArrayList();
        for (T t : list) {
            if (t.ts >= j) {
                arrayList.add(t);
            }
        }
        return stats(arrayList);
    }

    public static JSONObject resJson(Res res) {
        try {
            return new JSONObject().put("n", res.n).put("wr", round(res.wr * 100.0d, 1)).put("pf", round(res.pf, 2)).put("oos_n", res.nOos).put("oos_wr", round(res.oosWr * 100.0d, 1)).put("oos_pf", round(res.oosPf, 2)).put("exp_r", round(res.expR, 3)).put("w", res.weight).put("on", res.enabled);
        } catch (JSONException unused) {
            return new JSONObject();
        }
    }

    private static double round(double d, int i) {
        return Math.round(d * Math.pow(10.0d, i)) / Math.pow(10.0d, i);
    }

    public static List<StrategyPack.Signal> shaakuniSignals(List<EngineCore.Candle> list, int i, String str) {
        ArrayList arrayList = new ArrayList();
        EngineCore.Candle candle = list.get(i);
        double atr = EngineCore.atr(list, 14);
        if (Double.isNaN(atr) || atr <= 0.0d) {
            return arrayList;
        }
        double d = candle.c;
        int i2 = i + 1;
        double[] prevDayHighLow = EngineCore.prevDayHighLow(list.subList(0, i2));
        EngineCore.StructEvent structureWalk = EngineCore.structureWalk(list.subList(0, i2), 10);
        StrategyPack.Signal signal = null;
        if ("SHK1_SSM_BULL".equals(str)) {
            if (prevDayHighLow != null && structureWalk != null && "BULL".equals(structureWalk.dir) && "MSS".equals(structureWalk.kind) && "SWEEP".equals(EngineCore.sweepStatus(list.subList(0, i2), prevDayHighLow[1], false))) {
                signal = mk("SHK1_SSM_BULL", "BUY", candle, atr);
            }
        } else if ("SHK2_SSM_BEAR".equals(str)) {
            if (prevDayHighLow != null && structureWalk != null && "BEAR".equals(structureWalk.dir) && "MSS".equals(structureWalk.kind) && "SWEEP".equals(EngineCore.sweepStatus(list.subList(0, i2), prevDayHighLow[0], true))) {
                signal = mk("SHK2_SSM_BEAR", "SELL", candle, atr);
            }
        } else if ("SHK3_KZ_SWEEP".equals(str)) {
            if ("yes".equals(EngineCore.sessionNow(candle.ts)[1]) && prevDayHighLow != null) {
                boolean equals = "SWEEP".equals(EngineCore.sweepStatus(list.subList(0, i2), prevDayHighLow[0], true));
                if ("SWEEP".equals(EngineCore.sweepStatus(list.subList(0, i2), prevDayHighLow[1], false))) {
                    signal = mk("SHK3_KZ_SWEEP", "BUY", candle, atr);
                } else if (equals) {
                    signal = mk("SHK3_KZ_SWEEP", "SELL", candle, atr);
                }
            }
        } else if ("SHK4_OB_RETEST".equals(str)) {
            if (structureWalk != null) {
                Iterator<EngineCore.ObZone> it = EngineCore.orderBlocks(list.subList(0, i2), 10).iterator();
                while (true) {
                    if (!it.hasNext()) {
                        break;
                    }
                    EngineCore.ObZone next = it.next();
                    if (!next.mitigated && d >= next.bottom && d <= next.top) {
                        signal = mk("SHK4_OB_RETEST", next.bullish ? "BUY" : "SELL", candle, atr);
                    }
                }
            }
        } else if ("SHK5_PD_EMA200".equals(str) && prevDayHighLow != null) {
            double d2 = (prevDayHighLow[0] + prevDayHighLow[1]) / 2.0d;
            double emaClose = emaClose(list, i, 200);
            if (!Double.isNaN(emaClose)) {
                if (d < d2 && d > emaClose) {
                    signal = mk("SHK5_PD_EMA200", "BUY", candle, atr);
                } else if (d > d2 && d < emaClose) {
                    signal = mk("SHK5_PD_EMA200", "SELL", candle, atr);
                }
            }
        }
        StrategyPack.Signal signal2 = signal;
        if (signal2 != null) {
            arrayList.add(signal2);
        }
        return arrayList;
    }

    private static StrategyPack.Signal mk(String str, String str2, EngineCore.Candle candle, double d) {
        StrategyPack.Signal signal = new StrategyPack.Signal();
        signal.strategy = str;
        signal.side = str2;
        signal.sigTs = candle.ts;
        signal.sigIdx = -1;
        signal.refPrice = candle.c;
        signal.windowBars = 8;
        if ("BUY".equals(str2)) {
            signal.slPrice = candle.l - (1.5d * d);
            signal.boundary = candle.l - (d * 2.5d);
        } else {
            signal.slPrice = candle.h + (1.5d * d);
            signal.boundary = candle.h + (d * 2.5d);
        }
        signal.note = "Shaakuni playbook " + str;
        return signal;
    }

    private static double emaClose(List<EngineCore.Candle> list, int i, int i2) {
        if (i < i2 - 1) {
            return Double.NaN;
        }
        double d = 2.0d / (i2 + 1);
        int i3 = 0;
        double d2 = 0.0d;
        boolean z = false;
        while (i3 <= i) {
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

    public static double[][] prevDayMap(List<EngineCore.Candle> list) {
        TreeMap treeMap = new TreeMap();
        double[][] dArr = new double[list.size()][];
        long j = -1;
        double d = 0.0d;
        double d2 = 0.0d;
        for (int i = 0; i < list.size(); i++) {
            EngineCore.Candle candle = list.get(i);
            long j2 = candle.ts / 86400000;
            if (j2 != j) {
                if (j > 0) {
                    treeMap.put(Long.valueOf(j), new double[]{d, d2});
                }
                double d3 = candle.h;
                d2 = candle.l;
                d = d3;
                j = j2;
            } else {
                if (candle.h > d) {
                    d = candle.h;
                }
                if (candle.l < d2) {
                    d2 = candle.l;
                }
            }
            Map.Entry lastEntry = treeMap.lastEntry();
            dArr[i] = lastEntry == null ? null : (double[]) lastEntry.getValue();
        }
        return dArr;
    }
}
