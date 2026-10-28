import type { OHLCV, StrategySignal } from '../types'
import { ema, rsi, bollinger, macd, stochastic, atr, vwapDaily } from '../indicators'

// ============ Strategy architecture ============
// prepare(bars, params) computes indicator arrays ONCE (O(n));
// signalAt(ctx, i) evaluates a single bar in O(1). This keeps backtests
// linear-time and gives live/backtest the exact same code path (parity).

export interface StrategyDef {
  key: string
  name: string
  family: string
  description: string
  youtuberRef: string
  defaults: Record<string, number>
  grid: Record<string, number[]>
  prepare: (bars: OHLCV[], params: Record<string, number>) => unknown
  signalAt: (ctx: unknown, i: number, params: Record<string, number>) => StrategySignal
}

const closesOf = (bars: OHLCV[]) => bars.map((b) => b.close)

// ---- 1. EMA 9/21 Crossover Scalper ----

interface EmaCtx {
  bars: OHLCV[]
  fast: number[]
  slow: number[]
  trend: number[]
  closes: number[]
  warm: number
}

const emaCrossover: StrategyDef = {
  key: 'ema-crossover',
  name: 'EMA 9/21 Crossover Scalper',
  family: 'trend',
  description:
    'Fast EMA crossing slow EMA in the direction of the higher-timeframe EMA trend filter. The single most-taught 1-minute scalping setup on YouTube for gold and indices: enter on the cross, ride the micro-trend, exit on reverse cross.',
  youtuberRef: 'Classic "9/21 EMA scalping" taught by nearly every scalping channel',
  defaults: { fast: 9, slow: 21, trendFilter: 200, slopeBars: 5 },
  grid: {
    fast: [5, 7, 9, 12],
    slow: [15, 21, 30],
    trendFilter: [100, 200],
    slopeBars: [3, 5],
  },
  prepare(bars, p) {
    const closes = closesOf(bars)
    return {
      bars,
      closes,
      fast: ema(closes, p.fast),
      slow: ema(closes, p.slow),
      trend: ema(closes, p.trendFilter),
      warm: Math.max(p.trendFilter, p.slow) + p.slopeBars + 2,
    }
  },
  signalAt(ctxRaw, i, p) {
    const ctx = ctxRaw as EmaCtx
    if (i < ctx.warm || i === 0) return { dir: 0, conf: 0, fresh: false, reason: 'warming up' }
    const { fast, slow, trend, closes } = ctx
    if (isNaN(trend[i]) || isNaN(slow[i - p.slopeBars]) || isNaN(fast[i - 1])) {
      return { dir: 0, conf: 0, fresh: false, reason: 'warming up' }
    }

    const crossUp = fast[i] > slow[i] && fast[i - 1] <= slow[i - 1]
    const crossDown = fast[i] < slow[i] && fast[i - 1] >= slow[i - 1]
    const aboveTrend = closes[i] > trend[i]
    const belowTrend = closes[i] < trend[i]
    const slopeUp = slow[i] > slow[i - p.slopeBars]
    const slopeDown = slow[i] < slow[i - p.slopeBars]

    if (crossUp && aboveTrend && slopeUp) {
      const conf = Math.min(92, 74 + (closes[i] > fast[i] ? 6 : 0))
      return { dir: 1, conf, fresh: true, reason: `EMA${p.fast} crossed above EMA${p.slow}, EMA${p.trendFilter} trend aligned` }
    }
    if (crossDown && belowTrend && slopeDown) {
      const conf = Math.min(92, 74 + (closes[i] < fast[i] ? 6 : 0))
      return { dir: -1, conf, fresh: true, reason: `EMA${p.fast} crossed below EMA${p.slow}, EMA${p.trendFilter} trend aligned` }
    }
    const holding = fast[i] > slow[i] ? 1 : fast[i] < slow[i] ? -1 : 0
    if (holding === 1 && aboveTrend && slopeUp) {
      return { dir: 1, conf: 55, fresh: false, reason: `Holding EMA${p.fast}/${p.slow} bullish alignment` }
    }
    if (holding === -1 && belowTrend && slopeDown) {
      return { dir: -1, conf: 55, fresh: false, reason: `Holding EMA${p.fast}/${p.slow} bearish alignment` }
    }
    return { dir: 0, conf: 0, fresh: false, reason: 'No aligned EMA cross' }
  },
}

// ---- 2. RSI + Bollinger Band Mean Reversion ----

interface RsiBbCtx {
  bars: OHLCV[]
  rsi: number[]
  bbU: number[]
  bbL: number[]
  bbM: number[]
  trend: number[]
  warm: number
}

const rsiBollinger: StrategyDef = {
  key: 'rsi-bollinger',
  name: 'RSI + Bollinger Band Reversion',
  family: 'mean-reversion',
  description:
    'Buys oversold dips at the lower Bollinger Band in an uptrend, sells overbought spikes at the upper band in a downtrend — the "RSI + BB scalping" combo millions of YouTube tutorials teach for 1-minute gold charts.',
  youtuberRef: '"RSI + Bollinger Band scalping" — staple of beginner scalping tutorials',
  defaults: { rsiPeriod: 14, rsiOversold: 30, rsiOverbought: 70, bbPeriod: 20, bbMult: 2, trendFilter: 200 },
  grid: {
    rsiPeriod: [7, 14, 21],
    rsiOversold: [25, 30, 35],
    rsiOverbought: [65, 70, 75],
    bbMult: [1.8, 2, 2.2],
  },
  prepare(bars, p) {
    const closes = closesOf(bars)
    const bb = bollinger(closes, p.bbPeriod, p.bbMult)
    return {
      bars,
      rsi: rsi(closes, p.rsiPeriod),
      bbU: bb.upper,
      bbL: bb.lower,
      bbM: bb.mid,
      trend: ema(closes, p.trendFilter),
      warm: Math.max(p.trendFilter, p.bbPeriod, p.rsiPeriod) + 2,
    }
  },
  signalAt(ctxRaw, i, p) {
    const ctx = ctxRaw as RsiBbCtx
    if (i < ctx.warm) return { dir: 0, conf: 0, fresh: false, reason: 'warming up' }
    const { rsi, bbU, bbL, bbM, trend, bars } = ctx
    if (isNaN(rsi[i]) || isNaN(bbL[i]) || isNaN(trend[i])) return { dir: 0, conf: 0, fresh: false, reason: 'warming up' }

    const bar = bars[i]
    const atLowerBand = bar.low <= bbL[i]
    const atUpperBand = bar.high >= bbU[i]
    const closedBackInside = bar.close > bbL[i] && bar.close < bbU[i]
    const oversold = rsi[i] <= p.rsiOversold
    const overbought = rsi[i] >= p.rsiOverbought

    if (oversold && atLowerBand && bar.close > trend[i] && closedBackInside) {
      const depth = (p.rsiOversold - rsi[i]) / p.rsiOversold
      const conf = Math.min(90, 60 + depth * 40 + (bar.close > bar.open ? 8 : 0))
      return { dir: 1, conf, fresh: true, reason: `RSI ${rsi[i].toFixed(0)} oversold at lower BB, uptrend dip-buy` }
    }
    if (overbought && atUpperBand && bar.close < trend[i] && closedBackInside) {
      const depth = (rsi[i] - p.rsiOverbought) / (100 - p.rsiOverbought)
      const conf = Math.min(90, 60 + depth * 40 + (bar.close < bar.open ? 8 : 0))
      return { dir: -1, conf, fresh: true, reason: `RSI ${rsi[i].toFixed(0)} overbought at upper BB, downtrend fade` }
    }
    if (rsi[i] < p.rsiOversold + 8 && bar.close > trend[i] && bar.close < bbM[i]) {
      return { dir: 1, conf: 52, fresh: false, reason: 'Approaching oversold in uptrend' }
    }
    if (rsi[i] > p.rsiOverbought - 8 && bar.close < trend[i] && bar.close > bbM[i]) {
      return { dir: -1, conf: 52, fresh: false, reason: 'Approaching overbought in downtrend' }
    }
    return { dir: 0, conf: 0, fresh: false, reason: 'No band extreme' }
  },
}

// ---- 3. London Breakout (Asian range) ----

interface LondonCtx {
  bars: OHLCV[]
  atr: number[]
  asianHigh: number[] // per-bar: Asian session high for that bar's day
  asianLow: number[]
  warm: number
}

const londonBreakout: StrategyDef = {
  key: 'london-breakout',
  name: 'London Breakout',
  family: 'breakout',
  description:
    'Marks the Asian session range and trades the breakout at London open — one of the most-shared gold strategies on YouTube ("London breakout strategy XAUUSD 1 minute"). Volatility expansion at session open does the work.',
  youtuberRef: '"London Breakout / Asian range breakout" — hugely popular gold YouTube strategy',
  defaults: { rangeStartHourUTC: 0, rangeEndHourUTC: 7, tradeEndHourUTC: 10, minRangeAtr: 1.5 },
  grid: {
    rangeEndHourUTC: [6, 7, 8],
    tradeEndHourUTC: [9, 10, 11],
    minRangeAtr: [1.0, 1.5, 2.0],
  },
  prepare(bars, p) {
    const n = bars.length
    const asianHigh = new Array(n).fill(NaN)
    const asianLow = new Array(n).fill(NaN)
    let day = -1
    let rh = -Infinity
    let rl = Infinity
    for (let i = 0; i < n; i++) {
      const d = Math.floor(bars[i].ts / 86_400_000)
      if (d !== day) {
        day = d
        rh = -Infinity
        rl = Infinity
      }
      const hour = new Date(bars[i].ts).getUTCHours()
      if (hour >= p.rangeStartHourUTC && hour < p.rangeEndHourUTC) {
        rh = Math.max(rh, bars[i].high)
        rl = Math.min(rl, bars[i].low)
      }
      asianHigh[i] = rh
      asianLow[i] = rl
    }
    return { bars, atr: atr(bars, 14), asianHigh, asianLow, warm: 60 }
  },
  signalAt(ctxRaw, i, p) {
    const ctx = ctxRaw as LondonCtx
    if (i < ctx.warm || i === 0) return { dir: 0, conf: 0, fresh: false, reason: 'warming up' }
    const { bars, atr, asianHigh, asianLow } = ctx
    const bar = bars[i]
    if (isNaN(atr[i])) return { dir: 0, conf: 0, fresh: false, reason: 'warming up' }
    const hour = new Date(bar.ts).getUTCHours()
    if (hour < p.rangeEndHourUTC || hour >= p.tradeEndHourUTC) {
      return { dir: 0, conf: 0, fresh: false, reason: 'Outside London window' }
    }
    const rh = asianHigh[i]
    const rl = asianLow[i]
    if (!isFinite(rh) || !isFinite(rl)) return { dir: 0, conf: 0, fresh: false, reason: 'No Asian range yet' }
    const rangeSize = rh - rl
    if (rangeSize < p.minRangeAtr * atr[i]) return { dir: 0, conf: 0, fresh: false, reason: 'Asian range too tight' }

    const prevClose = bars[i - 1].close
    const breakoutUp = bar.close > rh && prevClose <= rh
    const breakoutDown = bar.close < rl && prevClose >= rl
    const rangeRatio = rangeSize / atr[i]

    if (breakoutUp) {
      const conf = Math.min(93, 63 + Math.min(15, (rangeRatio - p.minRangeAtr) * 8) + (bar.close > bar.open ? 8 : 0))
      return { dir: 1, conf, fresh: true, reason: `London breakout above Asian high (${rh.toFixed(2)})` }
    }
    if (breakoutDown) {
      const conf = Math.min(93, 63 + Math.min(15, (rangeRatio - p.minRangeAtr) * 8) + (bar.close < bar.open ? 8 : 0))
      return { dir: -1, conf, fresh: true, reason: `London breakdown below Asian low (${rl.toFixed(2)})` }
    }
    return { dir: 0, conf: 0, fresh: false, reason: 'Inside Asian range' }
  },
}

// ---- 4. MACD + Stochastic Momentum Scalper ----

interface MacdStochCtx {
  bars: OHLCV[]
  macdL: number[]
  macdS: number[]
  hist: number[]
  k: number[]
  d: number[]
  warm: number
}

const macdStoch: StrategyDef = {
  key: 'macd-stochastic',
  name: 'MACD + Stochastic Scalper',
  family: 'momentum',
  description:
    'MACD signal cross confirmed by a Stochastic turn in the same direction — the classic "two-indicator confluence" momentum scalp taught across YouTube trading channels for 1-minute entries.',
  youtuberRef: '"MACD + Stochastic confluence" — classic two-indicator YouTube scalp',
  defaults: { macdFast: 12, macdSlow: 26, macdSignal: 9, stochK: 14, stochD: 3, stochUpper: 80, stochLower: 20 },
  grid: {
    macdFast: [8, 12],
    macdSlow: [21, 26],
    stochK: [9, 14],
    stochUpper: [75, 80],
    stochLower: [20, 25],
  },
  prepare(bars, p) {
    const closes = closesOf(bars)
    const m = macd(closes, p.macdFast, p.macdSlow, p.macdSignal)
    const st = stochastic(bars, p.stochK, p.stochD, 3)
    return {
      bars,
      macdL: m.macd,
      macdS: m.signal,
      hist: m.hist,
      k: st.k,
      d: st.d,
      warm: p.macdSlow + p.macdSignal + p.stochK + 8,
    }
  },
  signalAt(ctxRaw, i, p) {
    const ctx = ctxRaw as MacdStochCtx
    if (i < ctx.warm || i === 0) return { dir: 0, conf: 0, fresh: false, reason: 'warming up' }
    const { macdL, macdS, hist, k, d } = ctx
    if (isNaN(macdL[i]) || isNaN(k[i]) || isNaN(d[i]) || isNaN(k[i - 1])) {
      return { dir: 0, conf: 0, fresh: false, reason: 'warming up' }
    }

    const macdCrossUp = macdL[i] > macdS[i] && macdL[i - 1] <= macdS[i - 1]
    const macdCrossDown = macdL[i] < macdS[i] && macdL[i - 1] >= macdS[i - 1]
    const stochTurningUp = k[i] > d[i] && k[i - 1] <= d[i - 1]
    const stochTurningDown = k[i] < d[i] && k[i - 1] >= d[i - 1]
    const histRising = hist[i] > hist[i - 1]
    const histFalling = hist[i] < hist[i - 1]

    if (macdCrossUp && stochTurningUp && k[i] < p.stochUpper) {
      const conf = Math.min(91, 61 + (k[i] < 50 ? 12 : 4) + (histRising ? 8 : 0))
      return { dir: 1, conf, fresh: true, reason: 'MACD bull cross + Stochastic turn up' }
    }
    if (macdCrossDown && stochTurningDown && k[i] > p.stochLower) {
      const conf = Math.min(91, 61 + (k[i] > 50 ? 12 : 4) + (histFalling ? 8 : 0))
      return { dir: -1, conf, fresh: true, reason: 'MACD bear cross + Stochastic turn down' }
    }
    if (macdL[i] > macdS[i] && histRising && k[i] > d[i]) {
      return { dir: 1, conf: 54, fresh: false, reason: 'MACD momentum up' }
    }
    if (macdL[i] < macdS[i] && histFalling && k[i] < d[i]) {
      return { dir: -1, conf: 54, fresh: false, reason: 'MACD momentum down' }
    }
    return { dir: 0, conf: 0, fresh: false, reason: 'No momentum confluence' }
  },
}

// ---- 5. VWAP Reversion Scalper ----

interface VwapCtx {
  bars: OHLCV[]
  vwap: number[]
  atr: number[]
  rsi: number[]
  warm: number
}

const vwapReversion: StrategyDef = {
  key: 'vwap-reversion',
  name: 'VWAP Reversion Scalper',
  family: 'institutional',
  description:
    'Trades snap-backs to the session VWAP when price stretches too far from it with RSI confirming exhaustion. VWAP is the institutional benchmark price — YouTubers sell it as "the one line institutions watch" for gold scalping.',
  youtuberRef: '"VWAP bounce / reversion to VWAP" — institutional-price scalping content',
  defaults: { devAtrMult: 1.5, rsiPeriod: 14, rsiBuyBelow: 35, rsiSellAbove: 65 },
  grid: {
    devAtrMult: [1.0, 1.5, 2.0],
    rsiBuyBelow: [30, 35, 40],
    rsiSellAbove: [60, 65, 70],
  },
  prepare(bars, p) {
    return {
      bars,
      vwap: vwapDaily(bars),
      atr: atr(bars, 14),
      rsi: rsi(closesOf(bars), p.rsiPeriod),
      warm: 60,
    }
  },
  signalAt(ctxRaw, i, p) {
    const ctx = ctxRaw as VwapCtx
    if (i < ctx.warm) return { dir: 0, conf: 0, fresh: false, reason: 'warming up' }
    const { vwap, atr, rsi, bars } = ctx
    if (isNaN(vwap[i]) || isNaN(atr[i]) || isNaN(rsi[i])) return { dir: 0, conf: 0, fresh: false, reason: 'warming up' }

    const close = bars[i].close
    const dev = (close - vwap[i]) / atr[i]
    const greenCandle = close > bars[i].open

    if (dev <= -p.devAtrMult && rsi[i] <= p.rsiBuyBelow) {
      const stretch = (p.devAtrMult - dev) / p.devAtrMult
      const conf = Math.min(90, 60 + stretch * 25 + (greenCandle ? 6 : 0))
      return { dir: 1, conf, fresh: true, reason: `Price ${(-dev).toFixed(1)} ATR below VWAP with RSI ${rsi[i].toFixed(0)}` }
    }
    if (dev >= p.devAtrMult && rsi[i] >= p.rsiSellAbove) {
      const stretch = (dev - p.devAtrMult) / p.devAtrMult
      const conf = Math.min(90, 60 + stretch * 25 + (!greenCandle ? 6 : 0))
      return { dir: -1, conf, fresh: true, reason: `Price ${dev.toFixed(1)} ATR above VWAP with RSI ${rsi[i].toFixed(0)}` }
    }
    if (dev <= -p.devAtrMult * 0.7 && rsi[i] < 45) {
      return { dir: 1, conf: 51, fresh: false, reason: 'Stretching below VWAP' }
    }
    if (dev >= p.devAtrMult * 0.7 && rsi[i] > 55) {
      return { dir: -1, conf: 51, fresh: false, reason: 'Stretching above VWAP' }
    }
    return { dir: 0, conf: 0, fresh: false, reason: 'Price near VWAP' }
  },
}

// ============ Registry ============

export const STRATEGIES: StrategyDef[] = [emaCrossover, rsiBollinger, londonBreakout, macdStoch, vwapReversion]

export function getStrategy(key: string): StrategyDef | undefined {
  return STRATEGIES.find((s) => s.key === key)
}

export const STRATEGY_META = STRATEGIES.map((s) => ({
  key: s.key,
  name: s.name,
  family: s.family,
  description: s.description,
  youtuberRef: s.youtuberRef,
  defaults: s.defaults,
  grid: s.grid,
}))

/** Grid cartesian product for auto-scan */
export function paramCombinations(grid: Record<string, number[]>): Record<string, number>[] {
  const keys = Object.keys(grid)
  let combos: Record<string, number>[] = [{}]
  for (const k of keys) {
    const next: Record<string, number>[] = []
    for (const base of combos) {
      for (const v of grid[k]) next.push({ ...base, [k]: v })
    }
    combos = next
  }
  return combos
}
