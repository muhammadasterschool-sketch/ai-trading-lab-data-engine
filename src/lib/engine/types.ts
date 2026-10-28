// ============ Shared engine types ============

export interface OHLCV {
  ts: number // epoch ms
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export type Direction = 1 | -1 | 0 // LONG | SHORT | NEUTRAL

export interface StrategySignal {
  dir: Direction
  /** confidence 0-100 */
  conf: number
  /** true = fresh entry event (cross/breakout/extreme). false = held stance (consensus vote only). */
  fresh: boolean
  reason: string
}

export interface StrategyVote {
  key: string
  name: string
  dir: Direction
  conf: number
  reason: string
}

export interface ConsensusState {
  symbol: string
  bullishScore: number // 0-100 — share of weighted confidence that is bullish
  bearishScore: number
  direction: 'BULLISH' | 'BEARISH' | 'NEUTRAL'
  thresholdMet: boolean
  votes: StrategyVote[]
  ts: number
}

export interface CostModel {
  /** relative spread (ask-bid)/mid as fraction, e.g. 0.0004 = 4bps */
  spreadFraction: number
  /** commission per side as fraction of notional, e.g. 0.0002 */
  feeFraction: number
  /** base slippage fraction (latency/queue), e.g. 0.0001 */
  baseSlippage: number
  /** square-root impact coefficient Y (bps) at 100% of ADV; bps = Y * sqrt(q/ADV) */
  impactCoeffBps: number
  /** typical daily volume in units of the asset (for impact scaling) */
  advUnits: number
}

export const DEFAULT_COSTS: CostModel = {
  // Realistic gold CFD (Exness-style standard account) round-trip ≈ 2bps:
  // spread ~1bp (≈$0.30-0.40/oz on ~$4000 gold), commission ~0.4bp/side-equivalent,
  // latency slippage ~0.2bp per side. Plus square-root impact on size.
  spreadFraction: 0.0001, // ~1 bp spread
  feeFraction: 0.00002, // ~0.2 bp per side
  baseSlippage: 0.00002, // ~0.2 bp per side
  impactCoeffBps: 10, // sqrt impact coefficient
  advUnits: 8000, // PAXG ~8k units/day
}

export interface BacktestMetrics {
  trades: number
  winRate: number
  netReturn: number // fraction of starting equity
  sharpe: number
  sortino: number
  maxDrawdown: number
  profitFactor: number
  avgWin: number
  avgLoss: number
  totalCosts: number
  expectancy: number
}

export interface BarLike {
  ts: Date
  open: number
  high: number
  low: number
  close: number
  volume: number
}
