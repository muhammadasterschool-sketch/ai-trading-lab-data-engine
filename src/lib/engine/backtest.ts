import type { OHLCV, CostModel, BacktestMetrics } from './types'
import { DEFAULT_COSTS } from './types'
import { atr } from './indicators'
import type { StrategyDef } from './strategies'

// ============ Backtest engine (v1.3 reality modelling) ============
// One code path shared by backtest / auto-scan / paper research.
// Rules of honesty:
//  - signals are computed on CLOSED bars; fills happen at the NEXT bar's open
//  - every fill pays: half-spread + commission + latency slippage + sqrt-impact
//  - stops/targets are checked intrabar against high/low
//  - no look-ahead: ATR/indicators use data up to the signal bar only

export interface BacktestTrade {
  side: 'LONG' | 'SHORT'
  entryTs: number
  exitTs: number
  entryPrice: number
  exitPrice: number
  qty: number
  pnl: number
  pnlPct: number
  exitReason: string
  fees: number
}

export interface BacktestOptions {
  costs?: CostModel
  riskPerTrade?: number // fraction of equity risked per trade (default 1%)
  stopAtrMult?: number // stop distance in ATRs (default 2)
  targetAtrMult?: number // target in ATRs (default 3, 1.5R)
  maxHoldBars?: number // time stop (default 120 bars)
  applyCosts?: boolean
  startEquity?: number
}

export interface BacktestResult {
  metrics: BacktestMetrics
  trades: BacktestTrade[]
  equityCurve: Array<{ ts: number; equity: number }>
  exitReasons?: Record<string, number>
  barsUsed: number
  params: Record<string, number>
  strategyKey: string
}

export function runBacktest(
  bars: OHLCV[],
  strategy: StrategyDef,
  params: Record<string, number>,
  options: BacktestOptions = {}
): BacktestResult {
  const costs = options.costs ?? DEFAULT_COSTS
  const applyCosts = options.applyCosts ?? true
  const riskPerTrade = options.riskPerTrade ?? 0.005
  const stopAtrMult = options.stopAtrMult ?? 2
  const targetAtrMult = options.targetAtrMult ?? 3
  const maxHoldBars = options.maxHoldBars ?? 120
  const startEquity = options.startEquity ?? 100_000
  // SIZING SAFETY: min stop = 5bp of price; max notional = 10× equity (leverage cap)
  const minStopFrac = 0.0005
  const maxLeverage = 10

  const a = atr(bars, 14)
  // prepare strategy context ONCE — O(n) indicators, then O(1) per bar (parity
  // with the live engine, which uses the same prepare/signalAt pair)
  const sctx = strategy.prepare(bars, params)
  const trades: BacktestTrade[] = []
  const equityCurve: Array<{ ts: number; equity: number }> = []
  let equity = startEquity
  let peak = equity
  let maxDD = 0

  // position state
  let pos: {
    side: 'LONG' | 'SHORT'
    entryIdx: number
    entryPrice: number
    qty: number
    stop: number
    target: number
    entryFee: number
    exitReasonTag: string
  } | null = null
  let prevEntryDir: 1 | -1 | 0 = 0 // edge-trigger: no re-entry in same direction
  const exitReasons: Record<string, number> = {}

  const fillPrice = (midPrice: number, side: 'BUY' | 'SELL', qty: number) => {
    if (!applyCosts) return { price: midPrice, cost: 0 }
    const halfSpread = midPrice * costs.spreadFraction * 0.5
    const slip = midPrice * costs.baseSlippage
    const impactBps =
      costs.advUnits > 0 ? costs.impactCoeffBps * Math.sqrt(Math.min(1, qty / costs.advUnits)) : 0
    const impact = midPrice * (impactBps / 10_000)
    const fee = midPrice * qty * costs.feeFraction
    const price = side === 'BUY' ? midPrice + halfSpread + slip + impact : midPrice - halfSpread - slip - impact
    return { price, cost: fee }
  }

  const warmup = Math.min(bars.length - 2, 240)
  for (let i = warmup; i < bars.length; i++) {
    // ---- manage open position on this bar ----
    if (pos) {
      const bar = bars[i]
      let exitPrice: number | null = null
      let exitReason = ''
      if (pos.side === 'LONG') {
        if (bar.low <= pos.stop) {
          exitPrice = pos.stop
          exitReason = 'stop'
        } else if (bar.high >= pos.target) {
          exitPrice = pos.target
          exitReason = 'target'
        }
      } else {
        if (bar.high >= pos.stop) {
          exitPrice = pos.stop
          exitReason = 'stop'
        } else if (bar.low <= pos.target) {
          exitPrice = pos.target
          exitReason = 'target'
        }
      }
      if (!exitPrice && i - pos.entryIdx >= maxHoldBars) {
        exitPrice = bar.close
        exitReason = 'time'
      }
      if (!exitPrice) {
        // opposite signal closes the position
        const sig = strategy.signalAt(sctx, i, params)
        if ((pos.side === 'LONG' && sig.dir === -1) || (pos.side === 'SHORT' && sig.dir === 1)) {
          exitPrice = bar.close
          exitReason = 'reverse'
        }
      }
      if (exitPrice !== null) {
        const exitSide = pos.side === 'LONG' ? 'SELL' : 'BUY'
        const fill = fillPrice(exitPrice, exitSide, pos.qty)
        const grossPnl =
          pos.side === 'LONG' ? (fill.price - pos.entryPrice) * pos.qty : (pos.entryPrice - fill.price) * pos.qty
        const pnl = grossPnl - fill.cost - pos.entryFee
        equity += pnl
        exitReasons[exitReason] = (exitReasons[exitReason] ?? 0) + 1
        trades.push({
          side: pos.side,
          entryTs: bars[pos.entryIdx].ts,
          exitTs: bar.ts,
          entryPrice: pos.entryPrice,
          exitPrice: fill.price,
          qty: pos.qty,
          pnl,
          pnlPct: pnl / (equity - pnl),
          exitReason,
          fees: fill.cost + pos.entryFee,
        })
        pos = null
      }
    }

    // ---- look for entry: FRESH EDGE-TRIGGERED signal, fill at next open ----
    // Fresh events only (crosses/breakouts/extremes) with conf ≥ 60, and only
    // when direction differs from the last entry (edge trigger — anti-churn).
    if (!pos && i + 1 < bars.length) {
      const sig = strategy.signalAt(sctx, i, params)
      if (sig.dir !== 0 && sig.fresh && sig.conf >= 60 && sig.dir !== prevEntryDir && !isNaN(a[i]) && a[i] > 0) {
        const nextOpen = bars[i + 1].open
        const stopDist = Math.max(stopAtrMult * a[i], nextOpen * minStopFrac)
        let qty = (equity * riskPerTrade) / stopDist
        // leverage cap
        if (qty * nextOpen > equity * maxLeverage) qty = (equity * maxLeverage) / nextOpen
        if (qty > 0 && isFinite(qty)) {
          const side: 'BUY' | 'SELL' = sig.dir === 1 ? 'BUY' : 'SELL'
          const fill = fillPrice(nextOpen, side, qty)
          pos = {
            side: sig.dir === 1 ? 'LONG' : 'SHORT',
            entryIdx: i + 1,
            entryPrice: fill.price,
            qty,
            stop: sig.dir === 1 ? fill.price - stopDist : fill.price + stopDist,
            target: sig.dir === 1 ? fill.price + targetAtrMult * a[i] : fill.price - targetAtrMult * a[i],
            entryFee: fill.cost,
            exitReasonTag: '',
          }
          prevEntryDir = sig.dir as 1 | -1
          // do NOT skip the fill bar — its full range plays out after the open fill
        }
      }
    }

    peak = Math.max(peak, equity)
    maxDD = Math.max(maxDD, (peak - equity) / peak)
    if (i % 30 === 0 || i === bars.length - 1) {
      equityCurve.push({ ts: bars[i].ts, equity: Math.round(equity * 100) / 100 })
    }
  }

  const metrics = computeMetrics(trades, equity, startEquity, maxDD, bars.length, applyCosts)
  return { metrics, trades, equityCurve, barsUsed: bars.length, params, strategyKey: strategy.key, exitReasons }
}

export function computeMetrics(
  trades: BacktestTrade[],
  finalEquity: number,
  startEquity: number,
  maxDD: number,
  barCount: number,
  applyCosts: boolean
): BacktestMetrics {
  const wins = trades.filter((t) => t.pnl > 0)
  const losses = trades.filter((t) => t.pnl <= 0)
  const grossWin = wins.reduce((s, t) => s + t.pnl, 0)
  const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnl, 0))
  const totalFees = trades.reduce((s, t) => s + t.fees, 0)
  const netReturn = (finalEquity - startEquity) / startEquity

  // per-trade Sharpe, scaled to annual (M1 bars, 365d market)
  const rets = trades.map((t) => t.pnlPct)
  const meanRet = rets.length ? rets.reduce((s, v) => s + v, 0) / rets.length : 0
  const sd = rets.length > 1 ? Math.sqrt(rets.reduce((s, v) => s + (v - meanRet) ** 2, 0) / (rets.length - 1)) : 0
  const tradesPerYear = barCount > 0 ? (trades.length / barCount) * 525_600 : 0
  const sharpe = sd > 0 && tradesPerYear > 0 ? (meanRet / sd) * Math.sqrt(Math.min(tradesPerYear, 50_000)) : 0
  const downside = rets.filter((r) => r < 0)
  const dsd = downside.length ? Math.sqrt(downside.reduce((s, v) => s + v * v, 0) / downside.length) : 0
  const sortino = dsd > 0 && tradesPerYear > 0 ? (meanRet / dsd) * Math.sqrt(Math.min(tradesPerYear, 50_000)) : 0

  return {
    trades: trades.length,
    winRate: trades.length ? wins.length / trades.length : 0,
    netReturn,
    sharpe: r2(sharpe),
    sortino: r2(sortino),
    maxDrawdown: maxDD,
    profitFactor: grossLoss > 0 ? r2(grossWin / grossLoss) : grossWin > 0 ? 99 : 0,
    avgWin: wins.length ? r2(grossWin / wins.length) : 0,
    avgLoss: losses.length ? r2(grossLoss / losses.length) : 0,
    totalCosts: applyCosts ? r2(totalFees) : 0,
    expectancy: trades.length ? r2((grossWin - grossLoss) / trades.length) : 0,
  }
}

// ============ Walk-forward validation (rolling OOS folds) ============

export interface FoldStat {
  fold: number
  from: string
  to: string
  trades: number
  netReturn: number
  sharpe: number
  maxDrawdown: number
}

export function walkForward(
  bars: OHLCV[],
  strategy: StrategyDef,
  params: Record<string, number>,
  options: BacktestOptions & { folds?: number } = {}
): { foldStats: FoldStat[]; aggregate: BacktestMetrics; equityCurve: Array<{ ts: number; equity: number }> } {
  const folds = options.folds ?? 5
  const foldStats: FoldStat[] = []
  const allTrades: BacktestTrade[] = []
  const equityCurve: Array<{ ts: number; equity: number }> = []
  let equity = options.startEquity ?? 100_000
  const foldSize = Math.floor(bars.length / folds)

  for (let f = 0; f < folds; f++) {
    const start = f * foldSize
    const end = f === folds - 1 ? bars.length : (f + 1) * foldSize
    const segment = bars.slice(Math.max(0, start - 240), end) // warmup context
    if (segment.length < 300) continue
    const res = runBacktest(segment, strategy, params, { ...options, startEquity: equity })
    for (const t of res.trades) {
      allTrades.push(t)
      equity += t.pnl
      equityCurve.push({ ts: t.exitTs, equity: Math.round(equity * 100) / 100 })
    }
    foldStats.push({
      fold: f + 1,
      from: new Date(bars[start].ts).toISOString().slice(0, 10),
      to: new Date(bars[end - 1].ts).toISOString().slice(0, 10),
      trades: res.metrics.trades,
      netReturn: r4(res.metrics.netReturn),
      sharpe: res.metrics.sharpe,
      maxDrawdown: r4(res.metrics.maxDrawdown),
    })
  }
  const maxDD = computeMaxDD(equityCurve.map((p) => p.equity))
  const aggregate = computeMetrics(allTrades, equity, options.startEquity ?? 100_000, maxDD, bars.length, options.applyCosts ?? true)
  return { foldStats, aggregate, equityCurve }
}

function computeMaxDD(curve: number[]): number {
  let peak = curve[0] ?? 0
  let dd = 0
  for (const v of curve) {
    peak = Math.max(peak, v)
    dd = Math.max(dd, (peak - v) / (peak || 1))
  }
  return dd
}

function r2(v: number) {
  return Math.round(v * 100) / 100
}
function r4(v: number) {
  return Math.round(v * 10000) / 10000
}
