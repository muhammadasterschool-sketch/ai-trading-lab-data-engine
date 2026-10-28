// ============ AI Trading Lab — Live Paper Trading Engine ============
// Port 3003 · socket.io realtime push · OKX public feed (real gold via PAXG)
// Pipeline: live prices → 1m bars → 5 YouTuber strategies → consensus (60%)
// → confirmation candle → BURST MODE (1 trade/sec) → risk engine → paper fills
// → TCA ledger → realtime UI events.

import { createServer } from 'http'
import { Server } from 'socket.io'
import { PrismaClient } from '@prisma/client'

import { OHLCV } from '../../src/lib/engine/types'
import { collectVotes, computeConsensus, newConsensusState, updateBurstStateMachine } from '../../src/lib/engine/consensus'
import { assessCrash, forecastNextMove } from '../../src/lib/engine/crash'
import { atr } from '../../src/lib/engine/indicators'
import { preTradeCheck, refreshRiskState, registerBreach, sqrtImpactBps, analyzeFill, type RiskState } from '../../src/lib/engine/risk'
import { fetchTicker, fetchCandles } from '../../src/lib/data/okx'

const db = new PrismaClient({ log: [] })
const GOLD_OKX = 'PAXG-USDT'
const BTC_OKX = 'BTC-USDT'
const GOLD = 'PAXGUSDT'
const BTC = 'BTCUSDT'
const HISTORY_BARS = 3000 // ~2 days of 1m bars for indicators

// ---------- live state ----------
interface LivePrice {
  last: number
  bid: number
  ask: number
  ts: number
}
const prices: Record<string, LivePrice> = {}
let goldBars: OHLCV[] = [] // closed 1m bars (oldest → newest)
const burstSM = newConsensusState()
let lastConsensus: ReturnType<typeof computeConsensus> | null = null
let lastBarTs = 0
let crashPause = false
let lastCrashAlertAt = 0
let lastPredictionAt = 0
let lastPersistAt = 0

// paper execution state
interface OpenPos {
  id: string // PaperPosition id
  tradeId: string // PaperTrade id
  symbol: string
  side: 'LONG' | 'SHORT'
  qty: number
  entryPrice: number
  stop: number
  target: number
  openedAt: number
  strategyKey: string
  mode: 'NORMAL' | 'BURST' | 'MANUAL'
  closeAt: number | null // time-based exit (burst)
  decisionPrice: number
  entryFee: number
  entrySpread: number
  entryImpact: number
}
let openPositions: OpenPos[] = []
let riskState: RiskState | null = null
let accountId: string | null = null

const stats = {
  startedAt: 0,
  ticks: 0,
  bars: 0,
  ordersFilled: 0,
  ordersRejected: 0,
  bursts: 0,
  burstTrades: 0,
}

// ---------- paper cost model (gold CFD realistic: spread-only) ----------
const COSTS = {
  feeFraction: 0.0, // Exness standard: commission-free, spread-only
  baseSlippage: 0.00005, // 0.5bp latency slippage
  impactCoeffBps: 10,
  advUnits: 8000,
}

// ---------- socket.io ----------
const httpServer = createServer()
const io = new Server(httpServer, {
  path: '/',
  cors: { origin: '*', methods: ['GET', 'POST'] },
  pingTimeout: 60000,
  pingInterval: 25000,
})

function emit(event: string, data: unknown) {
  io.emit(event, data)
}

// ---------- bootstrap ----------
async function loadHistory() {
  const bundles = await db.dataBundle.findMany({
    where: { symbol: GOLD, status: 'READY' },
    select: { id: true },
  })
  if (bundles.length === 0) {
    console.log('[engine] no historical bars in DB — starting live-only')
    goldBars = []
    return
  }
  // latest HISTORY_BARS across ALL bundles (incl. okx-live), time-ordered, deduped
  const rows = await db.bar.findMany({
    where: { bundleId: { in: bundles.map((b) => b.id) } },
    orderBy: { ts: 'desc' },
    take: HISTORY_BARS + 100,
  })
  const seen = new Set<number>()
  const slice: typeof rows = []
  for (const r of rows) {
    const t = r.ts.getTime()
    if (seen.has(t)) continue
    seen.add(t)
    slice.push(r)
    if (slice.length >= HISTORY_BARS) break
  }
  slice.reverse()
  goldBars = slice.map((b) => ({
    ts: b.ts.getTime(),
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
    volume: b.volume,
  }))
  lastBarTs = goldBars.length ? goldBars[goldBars.length - 1].ts : 0
  console.log(`[engine] loaded ${goldBars.length} historical gold bars (until ${new Date(lastBarTs).toISOString()})`)
}

async function loadAccount() {
  const account = await db.paperAccount.findFirst({ orderBy: { createdAt: 'asc' } })
  if (!account) {
    // create default account for the admin user
    const admin = await db.user.findFirst({ where: { role: 'ADMIN' } })
    if (!admin) {
      console.log('[engine] no admin user yet — will retry')
      return
    }
    const created = await db.paperAccount.create({
      data: { userId: admin.id, name: 'Primary Paper Account', symbol: GOLD },
    })
    accountId = created.id
    riskState = toRiskState(created)
    return
  }
  accountId = account.id
  riskState = toRiskState(account)
  // restore open positions
  const positions = await db.paperPosition.findMany({ where: { accountId: account.id, status: 'OPEN' } })
  const openTradeIds = new Set<string>()
  const openTrades = await db.paperTrade.findMany({ where: { accountId: account.id, status: 'OPEN' }, orderBy: { entryAt: 'asc' } })
  for (const t of openTrades) openTradeIds.add(t.id)
  openPositions = positions.map((p, idx) => ({
    id: p.id,
    tradeId: openTrades[idx]?.id ?? '',
    symbol: p.symbol,
    side: p.side as 'LONG' | 'SHORT',
    qty: p.qty,
    entryPrice: p.avgPrice,
    stop: p.strategyKey ? p.avgPrice : p.avgPrice, // stops restored approx (entry price as reference)
    target: p.avgPrice,
    openedAt: p.openedAt.getTime(),
    strategyKey: p.strategyKey ?? 'manual',
    mode: (p.mode as 'NORMAL' | 'BURST' | 'MANUAL') ?? 'MANUAL',
    closeAt: null,
    decisionPrice: p.avgPrice,
    entryFee: 0,
    entrySpread: 0,
    entryImpact: 0,
  }))
  console.log(`[engine] account ${account.id} equity=${account.equity} positions=${openPositions.length}`)
}

function toRiskState(a: {
  balance: number
  equity: number
  highWaterMark: number
  dayStartEquity: number
  dayKey: string
  dailyLossLimitPct: number
  maxDrawdownPct: number
  perTradeRiskPct: number
  burstRiskPct: number
  status: string
  cooldownUntil: Date | null
}): RiskState {
  return {
    balance: a.balance,
    equity: a.equity,
    highWaterMark: a.highWaterMark,
    dayStartEquity: a.dayStartEquity,
    dayKey: a.dayKey,
    dailyLossLimitPct: a.dailyLossLimitPct,
    maxDrawdownPct: a.maxDrawdownPct,
    perTradeRiskPct: a.perTradeRiskPct,
    burstRiskPct: a.burstRiskPct,
    status: a.status as RiskState['status'],
    cooldownUntil: a.cooldownUntil ? a.cooldownUntil.getTime() : null,
  }
}

async function getActiveStrategies() {
  const strategies = await db.strategy.findMany({ where: { status: 'ACTIVE' } })
  return strategies
}

// ---------- paper execution ----------
function fillPrice(side: 'BUY' | 'SELL', qty: number, ref?: LivePrice): { price: number; spread: number; fee: number; slip: number; impact: number } {
  const p = ref ?? prices[GOLD]
  const mid = p ? (p.bid + p.ask) / 2 : 0
  const halfSpread = p ? (p.ask - p.bid) / 2 : mid * 0.00025
  const slip = mid * COSTS.baseSlippage
  const impactBps = sqrtImpactBps(qty, COSTS.advUnits, COSTS.impactCoeffBps)
  const impact = mid * (impactBps / 10_000)
  const price = side === 'BUY' ? mid + halfSpread + slip + impact : mid - halfSpread - slip - impact
  return { price, spread: halfSpread * qty, fee: price * qty * COSTS.feeFraction, slip: slip * qty, impact: impact * qty }
}

async function placeOrder(opts: {
  side: 'LONG' | 'SHORT'
  mode: 'NORMAL' | 'BURST'
  strategyKey: string
  reason: string
  confidence: number
  riskPct?: number
  notionalCapPct?: number
  closeAfterSec?: number
  stopAtrMult?: number
}) {
  if (!riskState || !accountId) return null
  const now = Date.now()
  refreshRiskState(riskState, now)

  const p = prices[GOLD]
  if (!p) return null
  const a = atr(goldBars, 14)
  const atrVal = a.length && !isNaN(a[a.length - 1]) ? a[a.length - 1] : p.last * 0.0004
  const stopAtrMult = opts.stopAtrMult ?? 2
  // Same sizing safety as the backtester (parity!): min stop 5bp of price
  const stopDist = Math.max(atrVal * stopAtrMult, p.last * 0.0005)

  const verdict = preTradeCheck(
    riskState,
    {
      price: p.last,
      stopDistance: stopDist,
      riskPct: opts.riskPct ?? (opts.mode === 'BURST' ? riskState.burstRiskPct : riskState.perTradeRiskPct),
      mode: opts.mode,
      crashPause,
      openExposure: openPositions.reduce((s, pos) => s + pos.qty * p.last, 0),
    },
    now
  )

  if (!verdict.allowed) {
    stats.ordersRejected++
    await db.paperOrder.create({
      data: {
        accountId,
        strategyKey: opts.strategyKey,
        symbol: GOLD,
        side: opts.side === 'LONG' ? 'BUY' : 'SELL',
        qty: 0,
        requestedPrice: p.last,
        decisionPrice: (p.bid + p.ask) / 2,
        mode: opts.mode,
        status: 'REJECTED',
        rejectReason: verdict.reason,
        reason: opts.reason,
      },
    })
    if ('type' in verdict && (verdict.type === 'DAILY_LOSS_BREACH' || verdict.type === 'TRAILING_DD_BREACH')) {
      registerBreach(riskState, verdict.type, 5, now)
    }
    await persistAccount()
    emit('order-rejected', { reason: verdict.reason, mode: opts.mode, ts: now })
    return null
  }

  // notional cap
  let qty = verdict.qty
  const capNotional = riskState.equity * ((opts.notionalCapPct ?? (opts.mode === 'BURST' ? 5 : 20)) / 100)
  if (qty * p.last > capNotional) qty = capNotional / p.last

  const side: 'BUY' | 'SELL' = opts.side === 'LONG' ? 'BUY' : 'SELL'
  const fill = fillPrice(side, qty)
  const decisionMid = (p.bid + p.ask) / 2

  const pos = await db.paperPosition.create({
    data: {
      accountId,
      symbol: GOLD,
      side: opts.side,
      qty,
      avgPrice: fill.price,
      strategyKey: opts.strategyKey,
      mode: opts.mode,
    },
  })
  const trade = await db.paperTrade.create({
    data: {
      accountId,
      strategyKey: opts.strategyKey,
      symbol: GOLD,
      side: opts.side,
      qty,
      entryPrice: fill.price,
      mode: opts.mode,
      confidence: opts.confidence,
    },
  })
  await db.paperOrder.create({
    data: {
      accountId,
      strategyKey: opts.strategyKey,
      symbol: GOLD,
      side,
      qty,
      requestedPrice: p.last,
      decisionPrice: decisionMid,
      fillPrice: fill.price,
      spreadCost: fill.spread,
      fee: fill.fee,
      slippage: fill.slip,
      impactEstimate: fill.impact,
      mode: opts.mode,
      status: 'FILLED',
      reason: opts.reason,
      burstSeq: opts.mode === 'BURST' ? burstSM.burstSeq : null,
    },
  })

  const openPos: OpenPos = {
    id: pos.id,
    tradeId: trade.id,
    symbol: GOLD,
    side: opts.side,
    qty,
    entryPrice: fill.price,
    stop: opts.side === 'LONG' ? fill.price - stopDist : fill.price + stopDist,
    target: opts.side === 'LONG' ? fill.price + stopDist * 1.5 : fill.price - stopDist * 1.5,
    openedAt: now,
    strategyKey: opts.strategyKey,
    mode: opts.mode,
    closeAt: opts.closeAfterSec ? now + opts.closeAfterSec * 1000 : null,
    decisionPrice: decisionMid,
    entryFee: fill.fee,
    entrySpread: fill.spread,
    entryImpact: fill.impact,
  }
  openPositions.push(openPos)
  stats.ordersFilled++
  if (opts.mode === 'BURST') stats.burstTrades++

  emit('trade', {
    id: trade.id,
    side: opts.side,
    qty: r4(qty),
    entryPrice: r2(fill.price),
    mode: opts.mode,
    strategy: opts.strategyKey,
    reason: opts.reason,
    confidence: opts.confidence,
    ts: now,
  })
  return openPos
}

async function closePosition(pos: OpenPos, exitReason: string) {
  if (!riskState || !accountId) return
  const p = prices[GOLD]
  if (!p) return
  const now = Date.now()
  const side: 'BUY' | 'SELL' = pos.side === 'LONG' ? 'SELL' : 'BUY'
  const fill = fillPrice(side, pos.qty)
  const grossPnl = pos.side === 'LONG' ? (fill.price - pos.entryPrice) * pos.qty : (pos.entryPrice - fill.price) * pos.qty
  const totalCost = fill.fee + fill.spread + fill.impact
  const pnl = grossPnl + pos.entryFee + pos.entrySpread + pos.entryImpact - totalCost

  // TCA
  const tca = analyzeFill({
    decisionPrice: pos.decisionPrice,
    fillPrice: fill.price,
    side,
    qty: pos.qty,
    spreadCost: fill.spread,
    fee: fill.fee,
    slippage: fill.slip,
    impactEstimate: fill.impact,
  })

  const notional = pos.entryPrice * pos.qty
  await db.paperTrade.update({
    where: { id: pos.tradeId },
    data: { status: 'CLOSED', exitPrice: fill.price, exitAt: new Date(now), pnl, fees: totalCost + pos.entryFee + pos.entrySpread + pos.entryImpact, tcaBps: r4(tca.shortfallBps) },
  }).catch(() => {})
  await db.paperPosition.update({ where: { id: pos.id }, data: { status: 'CLOSED', closedAt: new Date(now), realizedPnl: pnl } })
  await db.paperOrder.create({
    data: {
      accountId,
      strategyKey: pos.strategyKey,
      symbol: GOLD,
      side,
      qty: pos.qty,
      requestedPrice: p.last,
      decisionPrice: pos.decisionPrice,
      fillPrice: fill.price,
      spreadCost: fill.spread,
      fee: fill.fee,
      slippage: fill.slip,
      impactEstimate: fill.impact,
      mode: pos.mode,
      status: 'FILLED',
      reason: `EXIT (${exitReason})`,
    },
  })

  riskState.balance += pnl
  riskState.equity += pnl
  openPositions = openPositions.filter((x) => x.id !== pos.id)

  emit('trade-close', {
    id: pos.id,
    side: pos.side,
    pnl: r2(pnl),
    pnlPct: r4((pnl / Math.max(1, notional)) * 100),
    exitPrice: r2(fill.price),
    exitReason,
    mode: pos.mode,
    tcaBps: r2(tca.shortfallBps),
    ts: now,
  })
  await persistAccount()
}

// ---------- bar close pipeline ----------
async function onBarClose(bar: OHLCV, quiet = false) {
  goldBars.push(bar)
  if (goldBars.length > HISTORY_BARS + 500) goldBars = goldBars.slice(-HISTORY_BARS)
  lastBarTs = bar.ts
  stats.bars++

  // persist live bar into LIVE bundle
  await persistLiveBar(bar).catch(() => {})

  // quiet mode: during boot catch-up we only ingest bars — the strategy
  // pipeline (consensus/crash/forecast) runs on fresh live bars only
  if (quiet || Date.now() - bar.ts > 3 * 60_000) return

  const strategies = await getActiveStrategies()
  const activeKeys = strategies.map((s) => s.key)
  const activeParams: Record<string, Record<string, number>> = {}
  for (const s of strategies) {
    try {
      activeParams[s.key] = JSON.parse(s.params)
    } catch {
      activeParams[s.key] = {}
    }
  }
  const votes = collectVotes(goldBars, activeKeys, activeParams)
  const account = await db.paperAccount.findUnique({ where: { id: accountId ?? '' } })
  const threshold = account?.consensusThreshold ?? 60
  const consensus = computeConsensus(GOLD, votes, threshold, bar.ts)
  lastConsensus = consensus

  const a = atr(goldBars, 14)
  const atrVal = a.length && !isNaN(a[a.length - 1]) ? a[a.length - 1] : 1

  const decision = updateBurstStateMachine(burstSM, consensus, bar, atrVal)
  if (decision.startBurst) {
    stats.bursts++
    await db.consensusLog.create({
      data: {
        ts: new Date(bar.ts),
        symbol: GOLD,
        bullishScore: consensus.bullishScore,
        bearishScore: consensus.bearishScore,
        direction: consensus.direction,
        thresholdMet: true,
        pendingSince: burstSM.pendingSince ? new Date(burstSM.pendingSince) : null,
        confirmationCandleAt: new Date(bar.ts),
        burstActive: true,
        votes: JSON.stringify(votes),
      },
    })
  }

  emit('consensus', {
    ...consensus,
    burst: {
      active: burstSM.burstActive,
      direction: burstSM.lastBurstDir,
      seq: burstSM.burstSeq,
      status: decision.reason,
    },
    barTs: bar.ts,
  })

  // ---- crash assessment ----
  const crash = assessCrash(goldBars)
  if (crash) {
    const high = Math.max(crash.probability, crash.meltUpProbability) >= 70
    const downCrash = crash.probability >= 70
    const upMelt = crash.meltUpProbability >= 70
    if (high && Date.now() - lastCrashAlertAt > 10 * 60_000) {
      lastCrashAlertAt = Date.now()
      const alert = await db.crashAlert.create({
        data: {
          ts: new Date(),
          symbol: GOLD,
          probability: downCrash ? crash.probability : crash.meltUpProbability,
          severity: crash.severity,
          direction: downCrash ? 'DOWN' : 'UP',
          indicators: JSON.stringify(crash.indicators),
          actionTaken: crashPause ? 'Already in crash-pause' : 'New orders paused (crash protection)',
        },
      })
      crashPause = true
      emit('crash-alert', { alert, narrative: crash.narrative })
    }
    if (crashPause && crash.probability < 60 && crash.meltUpProbability < 60) crashPause = false
    emit('crash', {
      probability: crash.probability,
      meltUp: crash.meltUpProbability,
      severity: crash.severity,
      direction: crash.direction,
      indicators: crash.indicators,
      narrative: crash.narrative,
    })
  }

  // ---- next-move forecast (every 5 min) ----
  if (Date.now() - lastPredictionAt > 5 * 60_000) {
    lastPredictionAt = Date.now()
    const fc = forecastNextMove(goldBars, 5)
    if (fc) {
      await db.prediction.create({
        data: {
          ts: new Date(),
          symbol: GOLD,
          direction: fc.direction,
          confidence: fc.confidence,
          horizonMin: 5,
          refPrice: fc.refPrice,
          features: JSON.stringify(fc.components),
        },
      })
      emit('forecast', fc)
    }
  }
  await resolveDuePredictions()
}

async function persistLiveBar(bar: OHLCV) {
  if (!accountId) return
  let bundle = await db.dataBundle.findFirst({ where: { symbol: GOLD, source: 'okx-live' } })
  if (!bundle) {
    bundle = await db.dataBundle.create({
      data: {
        symbol: GOLD,
        timeframe: '1m',
        source: 'okx-live',
        sourceUrl: 'https://www.okx.com/api/v5/market/candles?instId=PAXG-USDT',
        period: 'live',
        startDate: new Date(bar.ts),
        endDate: new Date(bar.ts),
        barCount: 0,
        provenance: JSON.stringify({ live: true, startedAt: new Date().toISOString() }),
        status: 'READY',
      },
    })
  }
  await db.bar.create({
    data: {
      bundleId: bundle.id,
      ts: new Date(bar.ts),
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close,
      volume: bar.volume,
    },
  }).catch(() => {}) // ignore duplicate
  await db.dataBundle.update({
    where: { id: bundle.id },
    data: { endDate: new Date(bar.ts), barCount: { increment: 1 } },
  })
}

async function resolveDuePredictions() {
  const due = await db.prediction.findMany({
    where: { resolvedAt: null, ts: { lt: new Date(Date.now() - 5 * 60_000) } },
    take: 20,
  })
  const p = prices[GOLD]
  if (!p) return
  for (const pred of due) {
    const actual = p.last
    const moved = actual - pred.refPrice
    const correct = pred.direction === 'UP' ? moved > 0 : moved < 0
    await db.prediction.update({
      where: { id: pred.id },
      data: { resolvedAt: new Date(), actualPrice: actual, correct },
    }).catch(() => {})
  }
}

// ---------- burst executor (1 trade per second) ----------
let burstTimer: ReturnType<typeof setInterval> | null = null

function startBurstExecutor() {
  if (burstTimer) return
  burstTimer = setInterval(async () => {
    if (!burstSM.burstActive || !engineState.autopilot || !engineState.running) return
    if (engineState.killSwitch) return
    if (!accountCfg.burstEnabled) {
      burstSM.burstActive = false
      stopBurstExecutor()
      return
    }
    if (burstSM.burstSeq >= accountCfg.maxBurstTrades) {
      // hard cap reached — end the burst cleanly
      burstSM.burstActive = false
      burstSM.confirmedDirection = null
      stopBurstExecutor()
      emit('consensus', { ...(lastConsensus ?? { symbol: GOLD, bullishScore: 50, bearishScore: 50, direction: 'NEUTRAL', thresholdMet: false, votes: [], ts: Date.now() }), burst: { active: false, direction: null, seq: burstSM.burstSeq, status: `Burst cap reached (${accountCfg.maxBurstTrades} trades)` }, barTs: lastBarTs })
      return
    }
    const dir: 'LONG' | 'SHORT' = burstSM.lastBurstDir === 'BULLISH' ? 'LONG' : 'SHORT'
    burstSM.burstSeq++
    await placeOrder({
      side: dir,
      mode: 'BURST',
      strategyKey: 'consensus-burst',
      reason: `Burst trade #${burstSM.burstSeq} — ${burstSM.lastBurstDir} consensus`,
      confidence: Math.max(lastConsensus?.bullishScore ?? 60, lastConsensus?.bearishScore ?? 60),
      closeAfterSec: 60,
      stopAtrMult: 2,
    })
    emit('burst-tick', { seq: burstSM.burstSeq, direction: burstSM.lastBurstDir, ts: Date.now() })
  }, 1000)
}

function stopBurstExecutor() {
  if (burstTimer) {
    clearInterval(burstTimer)
    burstTimer = null
  }
}

// ---------- position manager (every tick) ----------
async function managePositions() {
  const p = prices[GOLD]
  if (!p || !riskState) return
  const now = Date.now()
  for (const pos of [...openPositions]) {
    let exit: string | null = null
    if (pos.side === 'LONG') {
      if (p.bid <= pos.stop) exit = 'stop'
      else if (p.bid >= pos.target) exit = 'target'
    } else {
      if (p.ask >= pos.stop) exit = 'stop'
      else if (p.ask <= pos.target) exit = 'target'
    }
    if (!exit && pos.closeAt && now >= pos.closeAt) exit = 'time'
    if (!exit && now - pos.openedAt > 4 * 3600_000) exit = 'max-hold'
    if (exit) await closePosition(pos, exit)
  }
  // mark-to-market equity
  let unrealized = 0
  for (const pos of openPositions) {
    unrealized += pos.side === 'LONG' ? (p.last - pos.entryPrice) * pos.qty : (pos.entryPrice - p.last) * pos.qty
  }
  riskState.equity = riskState.balance + unrealized
  refreshRiskState(riskState, now)
}

// ---------- persistence ----------
async function persistAccount() {
  if (!accountId || !riskState) return
  await db.paperAccount
    .update({
      where: { id: accountId },
      data: {
        balance: riskState.balance,
        equity: riskState.equity,
        highWaterMark: riskState.highWaterMark,
        dayStartEquity: riskState.dayStartEquity,
        dayKey: riskState.dayKey,
        status: riskState.status,
        cooldownUntil: riskState.cooldownUntil ? new Date(riskState.cooldownUntil) : null,
      },
    })
    .catch(() => {})
}

// ---------- control state from DB ----------
const engineState = { running: false, autopilot: false, killSwitch: false }
const accountCfg = { maxBurstTrades: 60, burstEnabled: true }

async function pollControl() {
  const st = await db.engineState.findUnique({ where: { id: 'singleton' } })
  if (!st) return
  const wasAutopilot = engineState.autopilot
  engineState.running = st.running
  engineState.autopilot = st.autopilot
  engineState.killSwitch = st.killSwitch
  // refresh account-level config
  const acc = accountId ? await db.paperAccount.findUnique({ where: { id: accountId } }) : null
  if (acc) {
    accountCfg.maxBurstTrades = acc.maxBurstTrades
    accountCfg.burstEnabled = acc.burstEnabled
  }
  if (st.closeAll && openPositions.length > 0) {
    for (const pos of [...openPositions]) {
      await closePosition(pos, 'manual-close-all')
    }
    await db.engineState.update({ where: { id: 'singleton' }, data: { closeAll: false } })
    emit('positions-closed', { reason: 'manual-close-all', ts: Date.now() })
  }
  if (engineState.killSwitch && burstSM.burstActive) {
    burstSM.burstActive = false
    stopBurstExecutor()
  }
  if (!engineState.autopilot && wasAutopilot) {
    stopBurstExecutor()
    if (burstSM.burstActive) {
      burstSM.burstActive = false
      emit('consensus', { ...(lastConsensus ?? { symbol: GOLD, bullishScore: 50, bearishScore: 50, direction: 'NEUTRAL', thresholdMet: false, votes: [], ts: Date.now() }), burst: { active: false, direction: null, seq: burstSM.burstSeq, status: 'Autopilot off — burst stopped' }, barTs: lastBarTs })
    }
  }
}

// ---------- main loops ----------
async function tickPrices() {
  stats.ticks++
  const [gold, btc] = await Promise.all([fetchTicker(GOLD_OKX), fetchTicker(BTC_OKX)])
  if (gold && gold.last > 0) prices[GOLD] = { last: gold.last, bid: gold.bidPx, ask: gold.askPx, ts: gold.ts }
  if (btc && btc.last > 0) prices[BTC] = { last: btc.last, bid: btc.bidPx, ask: btc.askPx, ts: btc.ts }
  emit('price', {
    gold: prices[GOLD] ? { ...prices[GOLD], spread: r2(prices[GOLD].ask - prices[GOLD].bid) } : null,
    btc: prices[BTC] ? { ...prices[BTC] } : null,
    ts: Date.now(),
  })
  await managePositions()
  if (Date.now() - lastPersistAt > 10_000) {
    lastPersistAt = Date.now()
    await persistAccount()
    await db.engineState
      .update({
        where: { id: 'singleton' },
        data: {
          lastTickAt: new Date(),
          lastPriceGold: prices[GOLD]?.last ?? null,
          lastPriceBtc: prices[BTC]?.last ?? null,
          lastBarTs: lastBarTs ? new Date(lastBarTs) : null,
          burstState: JSON.stringify({ active: burstSM.burstActive, dir: burstSM.lastBurstDir, seq: burstSM.burstSeq, crashPause }),
        },
      })
      .catch(() => {})
    emit('account', accountSnapshot())
    emit('stats', { ...stats, positions: openPositions.length, uptimeSec: stats.startedAt ? Math.floor((Date.now() - stats.startedAt) / 1000) : 0 })
  }
}

let candlePollBusy = false
async function pollCandles() {
  if (candlePollBusy) return
  candlePollBusy = true
  try {
    // if we are >5 min behind, backfill a bigger window (gap recovery)
    const behind = Date.now() - lastBarTs
    const limit = behind > 5 * 60_000 ? 300 : 5
    const candles = await fetchCandles(GOLD_OKX, '1m', limit)
    const catchingUp = Date.now() - lastBarTs > 3 * 60_000
    for (const c of candles) {
      if (!c.confirmed) continue
      if (c.ts <= lastBarTs) continue
      await onBarClose({ ts: c.ts, open: c.open, high: c.high, low: c.low, close: c.close, volume: c.volume }, catchingUp)
    }
    // burst executor lifecycle follows burstSM state
    if (burstSM.burstActive && engineState.autopilot && engineState.running && !engineState.killSwitch) {
      startBurstExecutor()
    } else {
      stopBurstExecutor()
    }
  } finally {
    candlePollBusy = false
  }
}

function accountSnapshot() {
  if (!riskState) return null
  const now = Date.now()
  const dayPnlPct = ((riskState.equity - riskState.dayStartEquity) / Math.max(1e-9, riskState.dayStartEquity)) * 100
  const ddPct = ((riskState.highWaterMark - riskState.equity) / Math.max(1e-9, riskState.highWaterMark)) * 100
  return {
    equity: r2(riskState.equity),
    balance: r2(riskState.balance),
    dayPnlPct: r2(dayPnlPct),
    drawdownPct: r2(ddPct),
    dailyLossLimitPct: riskState.dailyLossLimitPct,
    maxDrawdownPct: riskState.maxDrawdownPct,
    status: riskState.status,
    autopilot: engineState.autopilot,
    crashPause,
    openPositions: openPositions.map((p) => ({
      id: p.id,
      side: p.side,
      qty: r4(p.qty),
      entryPrice: r2(p.entryPrice),
      currentPrice: prices[GOLD]?.last ?? p.entryPrice,
      unrealized: r2((p.side === 'LONG' ? (prices[GOLD]!.last - p.entryPrice) * p.qty : (p.entryPrice - prices[GOLD]!.last) * p.qty)),
      mode: p.mode,
      openedAt: p.openedAt,
      closeIn: p.closeAt ? Math.max(0, Math.round((p.closeAt - now) / 1000)) : null,
    })),
    burst: {
      active: burstSM.burstActive,
      direction: burstSM.lastBurstDir,
      seq: burstSM.burstSeq,
      pending: burstSM.pendingDirection,
    },
    ts: now,
  }
}

// ---------- socket.io client handling ----------
io.on('connection', (socket) => {
  socket.emit('hello', {
    engine: 'ai-trading-lab-engine',
    running: engineState.running,
    autopilot: engineState.autopilot,
    gold: prices[GOLD] ?? null,
    btc: prices[BTC] ?? null,
    account: accountSnapshot(),
    consensus: lastConsensus
      ? { ...lastConsensus, burst: { active: burstSM.burstActive, direction: burstSM.lastBurstDir, seq: burstSM.burstSeq, status: '' }, barTs: lastBarTs }
      : null,
    stats: { ...stats, uptimeSec: stats.startedAt ? Math.floor((Date.now() - stats.startedAt) / 1000) : 0 },
  })
})

// ---------- boot ----------
async function boot() {
  console.log('[engine] booting…')
  await loadHistory()
  await loadAccount()
  // ensure EngineState row
  await db.engineState.upsert({
    where: { id: 'singleton' },
    create: { id: 'singleton', running: true, autopilot: false },
    update: {},
  })
  engineState.running = true
  stats.startedAt = Date.now()

  setInterval(() => tickPrices().catch((e) => console.error('[engine] tick error', e)), 1000)
  setInterval(() => pollCandles().catch((e) => console.error('[engine] candle error', e)), 3000)
  setInterval(() => pollControl().catch((e) => console.error('[engine] control error', e)), 2000)
  setInterval(() => {
    emit('account', accountSnapshot())
  }, 5000)

  console.log('[engine] live — feed every 1s, bars every 3s, control every 2s')
}

httpServer.listen(3003, () => {
  console.log('[engine] socket.io listening on :3003')
  boot().catch((e) => console.error('[engine] boot failed', e))
})

process.on('SIGTERM', () => {
  httpServer.close(() => process.exit(0))
})
process.on('SIGINT', () => {
  httpServer.close(() => process.exit(0))
})

function r2(v: number) {
  return Math.round(v * 100) / 100
}
function r4(v: number) {
  return Math.round(v * 10000) / 10000
}
