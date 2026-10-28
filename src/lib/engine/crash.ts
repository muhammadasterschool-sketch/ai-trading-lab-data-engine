import type { OHLCV } from './types'
import { atr, realizedVol, zscore, bollinger, vwapDaily, ema, macd, rsi } from './indicators'

// ============ Crash prediction + next-move prediction ============
//
// Crash model: monitors volatility explosion, downside velocity, volume surge,
// consecutive adverse candles and Bollinger squeeze-release. Outputs a
// probability 0-100 that a violent move (crash down / melt-up) is imminent.
//
// Next-move model: lightweight ensemble (momentum + reversion + trend structure)
// forecasting direction over the next N minutes, logged as Prediction records
// and scored for rolling accuracy.

export interface CrashIndicators {
  volZ: number // z-score of realized volatility
  atrRatio: number // ATR(14) / SMA(ATR(14), 100)
  velocity: number // 10-bar move in ATR units (signed)
  volumeZ: number // volume z-score
  downStreak: number // consecutive bearish candles
  upStreak: number
  bbSqueezeRelease: number // width now / width 20 bars ago
  vwapDev: number // distance from VWAP in ATRs
}

export interface CrashAssessment {
  probability: number // 0-100 probability of an imminent violent move DOWN
  meltUpProbability: number // 0-100 violent move UP
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  direction: 'DOWN' | 'UP'
  indicators: CrashIndicators
  narrative: string
}

export function assessCrash(bars: OHLCV[]): CrashAssessment | null {
  const n = bars.length
  if (n < 220) return null
  const i = n - 1
  const closes = bars.map((b) => b.close)
  const a = atr(bars, 14)
  const rv = realizedVol(closes, 20)
  const rvZ = zscore(rv.map((v) => (isNaN(v) ? 0 : v)), 100)
  const volZ = isNaN(rvZ[i]) ? 0 : rvZ[i]
  const atrSeries = a
  const atrAvg = atrSeries.slice(Math.max(0, i - 99), i).filter((v) => !isNaN(v))
  const atrAvgVal = atrAvg.length ? atrAvg.reduce((s, v) => s + v, 0) / atrAvg.length : a[i]
  const atrRatio = atrAvgVal > 0 ? a[i] / atrAvgVal : 1
  const move10 = bars[i].close - bars[Math.max(0, i - 10)].close
  const velocity = a[i] > 0 ? move10 / a[i] : 0
  const volZscore = zscore(bars.map((b) => b.volume), 50)
  const volumeZ = isNaN(volZscore[i]) ? 0 : volZscore[i]
  let downStreak = 0
  let upStreak = 0
  for (let j = i; j > Math.max(0, i - 30); j--) {
    if (bars[j].close < bars[j].open) downStreak++
    else break
  }
  for (let j = i; j > Math.max(0, i - 30); j--) {
    if (bars[j].close > bars[j].open) upStreak++
    else break
  }
  const bb = bollinger(closes, 20, 2)
  const widthNow = bb.width[i]
  // floor the reference width at 1bp of price: flat/illiquid stretches print
  // near-zero Bollinger width, making the squeeze-release ratio explode
  const widthPast = Math.max(bb.width[Math.max(0, i - 20)], closes[i] * 0.0001)
  const bbSqueezeRelease = widthPast > 0 ? widthNow / widthPast : 1
  const vw = vwapDaily(bars)
  const vwapDev = a[i] > 0 ? (closes[i] - vw[i]) / a[i] : 0

  // ---- scoring: directional evidence + volatility context ----
  // Directional components (what direction a violent move would take)
  const dirDown = Math.max(0, -velocity - 1.5) * 10 + Math.max(0, downStreak - 4) * 4
  const dirUp = Math.max(0, velocity - 1.5) * 10 + Math.max(0, upStreak - 4) * 4
  // Shared volatility context (regime stress, direction-agnostic)
  const volContext =
    Math.max(0, volZ - 1.5) * 6 +
    Math.max(0, atrRatio - 1.6) * 20 +
    Math.max(0, volumeZ) * 3 +
    Math.max(0, bbSqueezeRelease - 2.0) * 8
  const downScore = dirDown + volContext * 0.6
  const upScore = dirUp + volContext * 0.6
  const crashProb = Math.max(0, Math.min(100, 100 / (1 + Math.exp(-(downScore - 40) / 10))))
  const meltProb = Math.max(0, Math.min(100, 100 / (1 + Math.exp(-(upScore - 40) / 10))))

  const isDown = crashProb >= meltProb
  const prob = Math.max(crashProb, meltProb)
  const severity = prob >= 85 ? 'CRITICAL' : prob >= 70 ? 'HIGH' : prob >= 50 ? 'MEDIUM' : 'LOW'

  const narrative = isDown
    ? `Volatility z=${volZ.toFixed(1)}, ATR ratio ${atrRatio.toFixed(2)}, ${downStreak} consecutive red candles, velocity ${velocity.toFixed(1)} ATR/10bars${volumeZ > 2 ? `, volume spike z=${volumeZ.toFixed(1)}` : ''}`
    : `Volatility z=${volZ.toFixed(1)}, ATR ratio ${atrRatio.toFixed(2)}, ${upStreak} consecutive green candles, velocity ${velocity.toFixed(1)} ATR/10bars${volumeZ > 2 ? `, volume spike z=${volumeZ.toFixed(1)}` : ''}`

  return {
    probability: Math.round(crashProb * 10) / 10,
    meltUpProbability: Math.round(meltProb * 10) / 10,
    severity,
    direction: isDown ? 'DOWN' : 'UP',
    indicators: {
      volZ: r1(volZ),
      atrRatio: r1(atrRatio),
      velocity: r1(velocity),
      volumeZ: r1(volumeZ),
      downStreak,
      upStreak,
      bbSqueezeRelease: r1(bbSqueezeRelease),
      vwapDev: r1(vwapDev),
    },
    narrative,
  }
}

export interface MoveForecast {
  direction: 'UP' | 'DOWN'
  confidence: number // 0-100
  refPrice: number
  expectedMoveAtr: number
  components: { momentum: number; reversion: number; trend: number }
}

/** Ensemble forecast of the next move over `horizonBars` (default 5 min on M1). */
export function forecastNextMove(bars: OHLCV[], horizonBars = 5): MoveForecast | null {
  const n = bars.length
  if (n < 220) return null
  const i = n - 1
  const closes = bars.map((b) => b.close)
  const a = atr(bars, 14)
  if (isNaN(a[i])) return null

  // momentum component: EMA9 slope + MACD histogram
  const e9 = ema(closes, 9)
  const e21 = ema(closes, 21)
  const m = macd(closes)
  const emaSlope = a[i] > 0 ? (e9[i] - e9[i - 3]) / a[i] : 0
  const macdHist = m.hist[i] - m.hist[i - 2]
  const momentum = Math.tanh(emaSlope * 1.2) * 0.6 + Math.tanh(macdHist / (a[i] * 0.15)) * 0.4

  // reversion component: RSI distance from 50, VWAP stretch
  const r = rsi(closes, 14)
  const vw = vwapDaily(bars)
  const rsiStretch = ((r[i] ?? 50) - 50) / 50 // -1..1
  const vwapStretch = a[i] > 0 ? (closes[i] - vw[i]) / (a[i] * 2) : 0
  const reversion = -Math.tanh(rsiStretch * 1.3) * 0.55 - Math.tanh(vwapStretch) * 0.45

  // trend structure: EMA9 vs EMA21 + higher highs
  const structure = closes[i] > e21[i] ? 1 : -1
  const hh = bars[i].high > bars[i - 1].high ? 1 : -1
  const trend = structure * 0.7 + hh * 0.3

  const raw = momentum * 0.4 + trend * 0.35 + reversion * 0.25
  const direction: 'UP' | 'DOWN' = raw >= 0 ? 'UP' : 'DOWN'
  const confidence = Math.min(95, Math.round(50 + Math.abs(raw) * 60))
  return {
    direction,
    confidence,
    refPrice: closes[i],
    expectedMoveAtr: r2(Math.abs(raw) * 0.9 * a[i] * Math.sqrt(horizonBars / 5) * 10) / 10,
    components: { momentum: r2(momentum * 100) / 100, reversion: r2(reversion * 100) / 100, trend: r2(trend * 100) / 100 },
  }
}

function r1(v: number) {
  return Math.round(v * 10) / 10
}
function r2(v: number) {
  return Math.round(v * 100) / 100
}
