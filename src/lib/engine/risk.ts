// ============ Risk engine — the prop-firm rulebook (report §9.1) ============
// Enforced PRE-TRADE on every order, including burst-mode orders:
//   • Daily loss circuit breaker (default 5% of day-start equity)
//   • Trailing high-water-mark drawdown deactivation (default 10%)
//   • Per-trade notional/loss cap (default 1% risk; burst trades 0.1%)
//   • Cooldown after any breach (default 5 minutes)
//   • Kill switch (manual or crash-triggered) blocks everything

export interface RiskState {
  balance: number
  equity: number
  highWaterMark: number
  dayStartEquity: number
  dayKey: string
  dailyLossLimitPct: number
  maxDrawdownPct: number
  perTradeRiskPct: number
  burstRiskPct: number
  status: 'ACTIVE' | 'HALTED_DAILY' | 'HALTED_DD' | 'KILLED'
  cooldownUntil: number | null // epoch ms
}

export interface RiskCheckInput {
  price: number
  stopDistance: number
  riskPct: number
  mode: 'NORMAL' | 'BURST' | 'MANUAL'
  crashPause?: boolean
  openExposure?: number // gross notional already open
}

export type RiskVerdict =
  | { allowed: true; qty: number; riskAmount: number }
  | { allowed: false; qty: 0; riskAmount: 0; reason: string; type: RiskEventType }

export type RiskEventType =
  | 'DAILY_LOSS_BREACH'
  | 'TRAILING_DD_BREACH'
  | 'PER_TRADE_CAP'
  | 'KILL_SWITCH'
  | 'COOLDOWN'
  | 'CRASH_PAUSE'
  | 'INVALID_ORDER'

export const DAY_MS = 86_400_000

export function utcDayKey(ts = Date.now()): string {
  return new Date(ts).toISOString().slice(0, 10)
}

/** Refresh day-rollover and trailing status. Mutates + returns events. */
export function refreshRiskState(state: RiskState, now = Date.now()): RiskEventType[] {
  const events: RiskEventType[] = []
  const todayKey = utcDayKey(now)
  if (state.dayKey !== todayKey) {
    state.dayKey = todayKey
    state.dayStartEquity = state.equity
    if (state.status === 'HALTED_DAILY') state.status = 'ACTIVE' // new day, new chance
  }
  state.highWaterMark = Math.max(state.highWaterMark, state.equity)

  const dayLossPct = (state.dayStartEquity - state.equity) / Math.max(1e-9, state.dayStartEquity)
  if (dayLossPct >= state.dailyLossLimitPct / 100 && state.status !== 'KILLED') {
    if (state.status !== 'HALTED_DAILY') events.push('DAILY_LOSS_BREACH')
    state.status = 'HALTED_DAILY'
  }
  const ddPct = (state.highWaterMark - state.equity) / Math.max(1e-9, state.highWaterMark)
  if (ddPct >= state.maxDrawdownPct / 100 && state.status !== 'KILLED') {
    if (state.status !== 'HALTED_DD') events.push('TRAILING_DD_BREACH')
    state.status = 'HALTED_DD'
  }
  return events
}

/** Pre-trade check — call before EVERY order (including each burst trade). */
export function preTradeCheck(state: RiskState, input: RiskCheckInput, now = Date.now()): RiskVerdict {
  if (state.status === 'KILLED') {
    return { allowed: false, qty: 0, riskAmount: 0, reason: 'Kill switch engaged — trading blocked', type: 'KILL_SWITCH' }
  }
  if (state.status === 'HALTED_DAILY') {
    return {
      allowed: false,
      qty: 0,
      riskAmount: 0,
      reason: 'Daily loss limit breached — halted for the day',
      type: 'DAILY_LOSS_BREACH',
    }
  }
  if (state.status === 'HALTED_DD') {
    return {
      allowed: false,
      qty: 0,
      riskAmount: 0,
      reason: 'Trailing drawdown limit breached — autopilot deactivated',
      type: 'TRAILING_DD_BREACH',
    }
  }
  if (state.cooldownUntil && now < state.cooldownUntil) {
    return {
      allowed: false,
      qty: 0,
      riskAmount: 0,
      reason: `Risk cooldown active until ${new Date(state.cooldownUntil).toISOString().slice(11, 19)} UTC`,
      type: 'COOLDOWN',
    }
  }
  if (input.crashPause) {
    return { allowed: false, qty: 0, riskAmount: 0, reason: 'Crash-protection pause active', type: 'CRASH_PAUSE' }
  }
  if (!(input.price > 0) || !(input.stopDistance > 0)) {
    return { allowed: false, qty: 0, riskAmount: 0, reason: 'Invalid order parameters', type: 'INVALID_ORDER' }
  }

  const capPct = input.mode === 'BURST' ? state.burstRiskPct : state.perTradeRiskPct
  const riskPct = Math.min(input.riskPct, capPct)
  const riskAmount = state.equity * (riskPct / 100)
  const qty = riskAmount / input.stopDistance
  if (!(qty > 0) || !isFinite(qty)) {
    return { allowed: false, qty: 0, riskAmount: 0, reason: 'Quantity computed as zero/invalid', type: 'INVALID_ORDER' }
  }
  // notional sanity: never more than 3× equity notional in a single order
  const notional = qty * input.price
  if (notional > state.equity * 3) {
    return { allowed: false, qty: 0, riskAmount: 0, reason: 'Order notional exceeds 3× equity cap', type: 'PER_TRADE_CAP' }
  }
  return { allowed: true, qty, riskAmount }
}

/** Register a breach event: sets cooldown. */
export function registerBreach(state: RiskState, type: RiskEventType, cooldownMinutes = 5, now = Date.now()): void {
  state.cooldownUntil = Math.max(state.cooldownUntil ?? 0, now + cooldownMinutes * 60_000)
  if (type === 'KILL_SWITCH') state.status = 'KILLED'
}

// ============ TCA (report §8.3) ============

export interface TcaRecord {
  decisionPrice: number // arrival mid at signal time
  fillPrice: number
  side: 'BUY' | 'SELL'
  qty: number
  spreadCost: number // currency
  fee: number
  slippage: number // currency vs decision mid (excl. spread)
  impactEstimate: number
}

export function analyzeFill(rec: TcaRecord): {
  shortfall: number // implementation shortfall in currency (positive = cost)
  shortfallBps: number // in basis points of notional
  totalCost: number
} {
  const dir = rec.side === 'BUY' ? 1 : -1
  const shortfall = (rec.fillPrice - rec.decisionPrice) * dir * rec.qty
  const notional = rec.decisionPrice * rec.qty
  return {
    shortfall,
    shortfallBps: notional > 0 ? (shortfall / notional) * 10_000 : 0,
    totalCost: rec.spreadCost + rec.fee + rec.slippage + rec.impactEstimate,
  }
}

/** Square-root impact estimate (report §8.2): bps = Y · sqrt(q / ADV) */
export function sqrtImpactBps(qty: number, advUnits: number, coeffBps = 10): number {
  if (advUnits <= 0 || qty <= 0) return 0
  return coeffBps * Math.sqrt(Math.min(1, qty / advUnits))
}
