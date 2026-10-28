import type { OHLCV, CostModel } from './types'
import { DEFAULT_COSTS } from './types'
import { STRATEGIES, paramCombinations } from './strategies'
import { runBacktest, type BacktestOptions } from './backtest'
import { expectedMaxNoiseZ, sharpeStd, deflateSharpe } from './dsr'

// ============ Auto-Scan (v1.2) ============
// Grid sweep across strategy parameter combinations, run over the selected
// history, ranked with the DSR noise bar displayed next to the leaderboard.
// IS/OOS split: top combos are re-tested out-of-sample (walk-forward lite).

export interface ScanComboResult {
  strategyKey: string
  params: Record<string, number>
  trades: number
  winRate: number
  sharpe: number
  sortino: number
  maxDrawdown: number
  netReturn: number
  profitFactor: number
  oosSharpe?: number
  oosReturn?: number
  rank?: number
}

export interface ScanOutput {
  trials: number
  noiseBarZ: number // expected best Sharpe from pure noise, in cross-trial σ
  noiseBarSharpe: number // in Sharpe units
  sigmaTrials: number
  deflatedSharpe: number
  clearsNoise: boolean
  results: ScanComboResult[] // sorted, top N
  isBars: number
  oosBars: number
  durationMs: number
}

export function runAutoScan(
  bars: OHLCV[],
  strategyKeys: string[],
  options: { topK?: number; costs?: CostModel; riskPerTrade?: number } = {}
): ScanOutput {
  const topK = options.topK ?? 15
  const t0 = Date.now()
  const allSharpes: number[] = []
  let trials = 0

  // IS = first 70%, OOS = last 30%
  const split = Math.floor(bars.length * 0.7)
  const isBars = bars.slice(0, split)
  const oosBars = bars.slice(Math.max(0, split - 240)) // warmup context

  const btOptions: BacktestOptions = {
    costs: options.costs ?? DEFAULT_COSTS,
    riskPerTrade: options.riskPerTrade ?? 0.01,
    applyCosts: true,
  }

  const pool: ScanComboResult[] = []
  const stopSweep = [2, 3, 4] // risk-geometry sweep: stop distance in ATRs

  for (const s of STRATEGIES) {
    if (!strategyKeys.includes(s.key)) continue
    const combos = paramCombinations(s.grid)
    for (const params of combos) {
      for (const stopAtrMult of stopSweep) {
      trials++
      try {
        const res = runBacktest(isBars, s, params, { ...btOptions, stopAtrMult })
        if (isFinite(res.metrics.sharpe)) allSharpes.push(res.metrics.sharpe)
        pool.push({
          strategyKey: s.key,
          params: { ...params, stopAtrMult },
          trades: res.metrics.trades,
          winRate: res.metrics.winRate,
          sharpe: res.metrics.sharpe,
          sortino: res.metrics.sortino,
          maxDrawdown: res.metrics.maxDrawdown,
          netReturn: res.metrics.netReturn,
          profitFactor: res.metrics.profitFactor,
        })
      } catch {
        // skip broken combo
      }
      }
    }
  }

  // rank IS results by Sharpe, keep combos that actually traded
  const active = pool.filter((r) => r.trades >= 5)
  active.sort((a, b) => b.sharpe - a.sharpe)
  const top = active.slice(0, topK)

  // walk-forward-lite: re-test top combos on the OOS segment
  for (const combo of top) {
    const s = STRATEGIES.find((x) => x.key === combo.strategyKey)
    if (!s) continue
    try {
      const { stopAtrMult, ...params } = combo.params
      const oos = runBacktest(oosBars, s, params, { ...btOptions, stopAtrMult })
      combo.oosSharpe = oos.metrics.sharpe
      combo.oosReturn = oos.metrics.netReturn
    } catch {
      combo.oosSharpe = 0
      combo.oosReturn = 0
    }
  }
  top.forEach((r, idx) => (r.rank = idx + 1))

  const sigma = sharpeStd(pool.map((r) => r.sharpe))
  const winner = top[0]
  const deflation = winner
    ? deflateSharpe(winner.sharpe, trials, sigma, isBars.length)
    : { noiseBarZ: 0, noiseBarSharpe: 0, deflatedSharpe: 0, clearsNoise: false }

  return {
    trials,
    noiseBarZ: Math.round(expectedMaxNoiseZ(Math.max(2, trials)) * 100) / 100,
    noiseBarSharpe: Math.round(deflation.noiseBarSharpe * 100) / 100,
    sigmaTrials: Math.round(sigma * 1000) / 1000,
    deflatedSharpe: deflation.deflatedSharpe,
    clearsNoise: deflation.clearsNoise,
    results: top,
    isBars: isBars.length,
    oosBars: oosBars.length,
    durationMs: Date.now() - t0,
  }
}
