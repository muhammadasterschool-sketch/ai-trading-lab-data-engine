import type { OHLCV } from './types'

// ============ Indicator library (20 indicators, array-based for speed) ============
// All functions return arrays aligned with input bars; leading values may be NaN.

export function sma(values: number[], period: number): number[] {
  const out = new Array(values.length).fill(NaN)
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    if (i >= period - 1) out[i] = sum / period
  }
  return out
}

export function ema(values: number[], period: number): number[] {
  const out = new Array(values.length).fill(NaN)
  if (values.length === 0) return out
  const k = 2 / (period + 1)
  let prev = NaN
  for (let i = 0; i < values.length; i++) {
    const v = values[i]
    if (i === period - 1) {
      let sum = 0
      for (let j = 0; j < period; j++) sum += values[j]
      prev = sum / period
      out[i] = prev
    } else if (i >= period) {
      prev = v * k + prev * (1 - k)
      out[i] = prev
    }
  }
  return out
}

export function wma(values: number[], period: number): number[] {
  const out = new Array(values.length).fill(NaN)
  const denom = (period * (period + 1)) / 2
  for (let i = period - 1; i < values.length; i++) {
    let s = 0
    for (let j = 0; j < period; j++) s += values[i - period + 1 + j] * (j + 1)
    out[i] = s / denom
  }
  return out
}

export function stdev(values: number[], period: number): number[] {
  const out = new Array(values.length).fill(NaN)
  for (let i = period - 1; i < values.length; i++) {
    let mean = 0
    for (let j = i - period + 1; j <= i; j++) mean += values[j]
    mean /= period
    let v = 0
    for (let j = i - period + 1; j <= i; j++) v += (values[j] - mean) ** 2
    out[i] = Math.sqrt(v / period)
  }
  return out
}

export function rsi(closes: number[], period = 14): number[] {
  const out = new Array(closes.length).fill(NaN)
  if (closes.length <= period) return out
  let avgGain = 0
  let avgLoss = 0
  for (let i = 1; i <= period; i++) {
    const d = closes[i] - closes[i - 1]
    if (d >= 0) avgGain += d
    else avgLoss -= d
  }
  avgGain /= period
  avgLoss /= period
  out[period] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  for (let i = period + 1; i < closes.length; i++) {
    const d = closes[i] - closes[i - 1]
    const g = d > 0 ? d : 0
    const l = d < 0 ? -d : 0
    avgGain = (avgGain * (period - 1) + g) / period
    avgLoss = (avgLoss * (period - 1) + l) / period
    out[i] = avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)
  }
  return out
}

export interface MacdResult {
  macd: number[]
  signal: number[]
  hist: number[]
}

export function macd(closes: number[], fast = 12, slow = 26, signalPeriod = 9): MacdResult {
  const emaFast = ema(closes, fast)
  const emaSlow = ema(closes, slow)
  const macdLine = closes.map((_, i) => emaFast[i] - emaSlow[i])
  const signal = ema(macdLine.map((v) => (isNaN(v) ? 0 : v)), signalPeriod)
  const hist = macdLine.map((v, i) => v - signal[i])
  return { macd: macdLine, signal, hist }
}

export interface BollingerResult {
  mid: number[]
  upper: number[]
  lower: number[]
  width: number[] // (upper-lower)/mid
}

export function bollinger(closes: number[], period = 20, mult = 2): BollingerResult {
  const mid = sma(closes, period)
  const sd = stdev(closes, period)
  const upper = mid.map((m, i) => m + mult * sd[i])
  const lower = mid.map((m, i) => m - mult * sd[i])
  const width = mid.map((m, i) => (m ? (upper[i] - lower[i]) / m : NaN))
  return { mid, upper, lower, width }
}

export function trueRange(bars: OHLCV[]): number[] {
  const out = new Array(bars.length).fill(NaN)
  for (let i = 1; i < bars.length; i++) {
    // 0.5bp floor: illiquid feeds print zero-range candles (high=low), which
    // would collapse ATR to ~0 and blow up every ATR-normalised metric
    const tr = Math.max(
      bars[i].high - bars[i].low,
      Math.abs(bars[i].high - bars[i - 1].close),
      Math.abs(bars[i].low - bars[i - 1].close),
      bars[i].close * 0.00005
    )
    out[i] = tr
  }
  return out
}

export function atr(bars: OHLCV[], period = 14): number[] {
  const tr = trueRange(bars)
  const out = new Array(bars.length).fill(NaN)
  if (bars.length <= period) return out
  let sum = 0
  for (let i = 1; i <= period; i++) sum += tr[i]
  out[period] = sum / period
  for (let i = period + 1; i < bars.length; i++) {
    out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
  }
  return out
}

export interface StochResult {
  k: number[]
  d: number[]
}

export function stochastic(bars: OHLCV[], kPeriod = 14, dPeriod = 3, smooth = 3): StochResult {
  const raw = new Array(bars.length).fill(NaN)
  for (let i = kPeriod - 1; i < bars.length; i++) {
    let hh = -Infinity
    let ll = Infinity
    for (let j = i - kPeriod + 1; j <= i; j++) {
      hh = Math.max(hh, bars[j].high)
      ll = Math.min(ll, bars[j].low)
    }
    raw[i] = hh === ll ? 50 : ((bars[i].close - ll) / (hh - ll)) * 100
  }
  const k = sma(raw.map((v) => (isNaN(v) ? 0 : v)), smooth).map((v, i) => (isNaN(raw[i]) ? NaN : v))
  const d = sma(k.map((v) => (isNaN(v) ? 0 : v)), dPeriod).map((v, i) => (isNaN(k[i]) ? NaN : v))
  return { k, d }
}

export function adx(bars: OHLCV[], period = 14): { adx: number[]; plusDi: number[]; minusDi: number[] } {
  const n = bars.length
  const plusDm = new Array(n).fill(0)
  const minusDm = new Array(n).fill(0)
  const tr = trueRange(bars)
  for (let i = 1; i < n; i++) {
    const up = bars[i].high - bars[i - 1].high
    const down = bars[i - 1].low - bars[i].low
    plusDm[i] = up > down && up > 0 ? up : 0
    minusDm[i] = down > up && down > 0 ? down : 0
  }
  const smooth = (arr: number[]) => {
    const out = new Array(n).fill(NaN)
    let s = 0
    for (let i = 1; i <= period; i++) s += arr[i] || 0
    out[period] = s
    for (let i = period + 1; i < n; i++) out[i] = out[i - 1] - out[i - 1] / period + (arr[i] || 0)
    return out
  }
  const sTr = smooth(tr)
  const sPlus = smooth(plusDm)
  const sMinus = smooth(minusDm)
  const plusDi = new Array(n).fill(NaN)
  const minusDi = new Array(n).fill(NaN)
  const dx = new Array(n).fill(NaN)
  for (let i = period; i < n; i++) {
    if (!sTr[i]) continue
    plusDi[i] = (100 * sPlus[i]) / sTr[i]
    minusDi[i] = (100 * sMinus[i]) / sTr[i]
    const sum = plusDi[i] + minusDi[i]
    dx[i] = sum === 0 ? 0 : (100 * Math.abs(plusDi[i] - minusDi[i])) / sum
  }
  const adxArr = new Array(n).fill(NaN)
  const firstAdx = period * 2 - 1
  if (n > firstAdx) {
    let s = 0
    let count = 0
    for (let i = period; i <= firstAdx; i++) {
      if (!isNaN(dx[i])) {
        s += dx[i]
        count++
      }
    }
    adxArr[firstAdx] = s / Math.max(1, count)
    for (let i = firstAdx + 1; i < n; i++) {
      adxArr[i] = (adxArr[i - 1] * (period - 1) + (dx[i] || 0)) / period
    }
  }
  return { adx: adxArr, plusDi, minusDi }
}

/** Session-anchored VWAP — resets every UTC day (institutional standard). */
export function vwapDaily(bars: OHLCV[]): number[] {
  const out = new Array(bars.length).fill(NaN)
  let cumPV = 0
  let cumV = 0
  let currentDay = -1
  for (let i = 0; i < bars.length; i++) {
    const day = Math.floor(bars[i].ts / 86_400_000)
    if (day !== currentDay) {
      currentDay = day
      cumPV = 0
      cumV = 0
    }
    const typical = (bars[i].high + bars[i].low + bars[i].close) / 3
    const v = bars[i].volume || 1e-9
    cumPV += typical * v
    cumV += v
    out[i] = cumPV / cumV
  }
  return out
}

export function rollingVwap(bars: OHLCV[], period = 60): number[] {
  const out = new Array(bars.length).fill(NaN)
  let cumPV = 0
  let cumV = 0
  for (let i = 0; i < bars.length; i++) {
    const typical = (bars[i].high + bars[i].low + bars[i].close) / 3
    const v = bars[i].volume || 1e-9
    cumPV += typical * v
    cumV += v
    if (i >= period) {
      const old = bars[i - period]
      const oldTypical = (old.high + old.low + old.close) / 3
      const oldV = old.volume || 1e-9
      cumPV -= oldTypical * oldV
      cumV -= oldV
    }
    out[i] = cumV > 0 ? cumPV / cumV : NaN
  }
  return out
}

export function cci(bars: OHLCV[], period = 20): number[] {
  const tp = bars.map((b) => (b.high + b.low + b.close) / 3)
  const ma = sma(tp, period)
  const out = new Array(bars.length).fill(NaN)
  for (let i = period - 1; i < bars.length; i++) {
    let dev = 0
    for (let j = i - period + 1; j <= i; j++) dev += Math.abs(tp[j] - ma[i])
    dev /= period
    out[i] = dev === 0 ? 0 : (tp[i] - ma[i]) / (0.015 * dev)
  }
  return out
}

export function williamsR(bars: OHLCV[], period = 14): number[] {
  const out = new Array(bars.length).fill(NaN)
  for (let i = period - 1; i < bars.length; i++) {
    let hh = -Infinity
    let ll = Infinity
    for (let j = i - period + 1; j <= i; j++) {
      hh = Math.max(hh, bars[j].high)
      ll = Math.min(ll, bars[j].low)
    }
    out[i] = hh === ll ? -50 : ((hh - bars[i].close) / (hh - ll)) * -100
  }
  return out
}

export function mfi(bars: OHLCV[], period = 14): number[] {
  const n = bars.length
  const out = new Array(n).fill(NaN)
  const tp = bars.map((b) => (b.high + b.low + b.close) / 3)
  for (let i = period; i < n; i++) {
    let pos = 0
    let neg = 0
    for (let j = i - period + 1; j <= i; j++) {
      const flow = tp[j] * (bars[j].volume || 0)
      if (tp[j] > tp[j - 1]) pos += flow
      else if (tp[j] < tp[j - 1]) neg += flow
    }
    out[i] = neg === 0 ? 100 : 100 - 100 / (1 + pos / neg)
  }
  return out
}

export function obv(bars: OHLCV[]): number[] {
  const out = new Array(bars.length).fill(0)
  for (let i = 1; i < bars.length; i++) {
    const v = bars[i].volume || 0
    out[i] = out[i - 1] + (bars[i].close > bars[i - 1].close ? v : bars[i].close < bars[i - 1].close ? -v : 0)
  }
  return out
}

export function roc(closes: number[], period = 9): number[] {
  return closes.map((c, i) => (i >= period && closes[i - period] !== 0 ? ((c - closes[i - period]) / closes[i - period]) * 100 : NaN))
}

export function momentum(closes: number[], period = 10): number[] {
  return closes.map((c, i) => (i >= period ? c - closes[i - period] : NaN))
}

export function donchian(bars: OHLCV[], period = 20): { upper: number[]; lower: number[]; mid: number[] } {
  const upper = new Array(bars.length).fill(NaN)
  const lower = new Array(bars.length).fill(NaN)
  const mid = new Array(bars.length).fill(NaN)
  for (let i = period - 1; i < bars.length; i++) {
    let hh = -Infinity
    let ll = Infinity
    for (let j = i - period + 1; j <= i; j++) {
      hh = Math.max(hh, bars[j].high)
      ll = Math.min(ll, bars[j].low)
    }
    upper[i] = hh
    lower[i] = ll
    mid[i] = (hh + ll) / 2
  }
  return { upper, lower, mid }
}

export function keltner(bars: OHLCV[], period = 20, mult = 2): { mid: number[]; upper: number[]; lower: number[] } {
  const closes = bars.map((b) => b.close)
  const mid = ema(closes, period)
  const a = atr(bars, period)
  return {
    mid,
    upper: mid.map((m, i) => m + mult * a[i]),
    lower: mid.map((m, i) => m - mult * a[i]),
  }
}

/** Simple supertrend (trend-following stop-and-reverse) */
export function supertrend(bars: OHLCV[], period = 10, mult = 3): { line: number[]; dir: number[] } {
  const n = bars.length
  const a = atr(bars, period)
  const line = new Array(n).fill(NaN)
  const dir = new Array(n).fill(0)
  let upperPrev = NaN
  let lowerPrev = NaN
  for (let i = 0; i < n; i++) {
    if (isNaN(a[i])) continue
    const mid = (bars[i].high + bars[i].low) / 2
    let upper = mid + mult * a[i]
    let lower = mid - mult * a[i]
    if (!isNaN(upperPrev)) {
      upper = bars[i - 1] && bars[i - 1].close > upperPrev ? upper : Math.min(upper, upperPrev)
      lower = bars[i - 1] && bars[i - 1].close < lowerPrev ? lower : Math.max(lower, lowerPrev)
    }
    const prevDir = i > 0 ? dir[i - 1] : 1
    dir[i] = bars[i].close > upper ? 1 : bars[i].close < lower ? -1 : prevDir
    line[i] = dir[i] === 1 ? lower : upper
    upperPrev = upper
    lowerPrev = lower
  }
  return { line, dir }
}

export function zscore(values: number[], period: number): number[] {
  const m = sma(values, period)
  const sd = stdev(values, period)
  return values.map((v, i) => (sd[i] ? (v - m[i]) / sd[i] : NaN))
}

/** Realized volatility (stdev of log returns) */
export function realizedVol(closes: number[], period = 20): number[] {
  const rets = closes.map((c, i) => (i > 0 && closes[i - 1] > 0 ? Math.log(c / closes[i - 1]) : NaN))
  return stdev(rets.map((r) => (isNaN(r) ? 0 : r)), period)
}
