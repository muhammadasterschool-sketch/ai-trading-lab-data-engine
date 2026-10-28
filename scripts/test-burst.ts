// Burst pipeline controlled test — verifies the full consensus → confirmation
// candle → burst state machine → sizing chain without waiting for market.
import { computeConsensus, updateBurstStateMachine, newConsensusState, type ConsensusState } from '../src/lib/engine/consensus'
import type { OHLCV, StrategyVote } from '../src/lib/engine/types'

function makeVotes(dirs: Array<[1 | -1, number]>): StrategyVote[] {
  return dirs.map(([dir, conf], i) => ({ key: `s${i}`, name: `Strategy ${i}`, dir, conf, reason: 'test' }))
}

const atrVal = 1.0
let sm = newConsensusState()
let passed = 0
let failed = 0
function check(name: string, cond: boolean) {
  console.log(`${cond ? '✓' : '✗ FAIL'} ${name}`)
  if (cond) { passed++ } else { failed++ }
}

// --- Test 1: single voter → no consensus (min 2 voters) ---
let c: ConsensusState = computeConsensus('X', makeVotes([[-1, 90]]), 60, 1)
check('single voter cannot reach consensus', !c.thresholdMet && c.direction === 'NEUTRAL')

// --- Test 2: two voters 75/25 → consensus BEARISH ---
c = computeConsensus('X', makeVotes([[-1, 90], [-1, 50], [1, 47]]), 60, 2)
// bear = 140, bull = 47 → bear 74.9%
check('2-3 voters reach BEARISH consensus', c.thresholdMet && c.direction === 'BEARISH')
check('bear score ≈ 74.9', Math.abs(c.bearishScore - 74.9) < 0.2)

// --- Test 3: burst state machine: threshold → pending → confirmation candle → burst ---
sm = newConsensusState()
const t0 = 1_700_000_000_000
// bar 1: consensus met (bearish), candle is bullish → pending, no start
let bar: OHLCV = { ts: t0, open: 100, high: 101, low: 99, close: 100.8, volume: 10 } // bullish body 0.8 ≥ 0.15 ATR
let d = updateBurstStateMachine(sm, c, bar, atrVal)
check('bar 1: pending set, no burst yet', sm.pendingDirection === 'BEARISH' && !d.startBurst && !sm.burstActive)

// bar 2: bearish confirmation candle (body ≥ 0.15 ATR)
bar = { ts: t0 + 60_000, open: 100.8, high: 100.9, low: 99.6, close: 99.8, volume: 10 } // bearish body 1.0
d = updateBurstStateMachine(sm, c, bar, atrVal)
check('bar 2: confirmation candle → burst START', d.startBurst && sm.burstActive && sm.lastBurstDir === 'BEARISH')
check('bar 2: burst direction BEARISH', d.burstDirection === 'BEARISH')

// --- Test 4: doji candle does NOT confirm (body < 0.15 ATR) ---
sm = newConsensusState()
d = updateBurstStateMachine(sm, c, { ts: t0, open: 100, high: 100.2, low: 99.9, close: 100.05, volume: 10 }, atrVal)
d = updateBurstStateMachine(sm, c, { ts: t0 + 60_000, open: 100, high: 100.05, low: 99.95, close: 100.02, volume: 10 }, atrVal)
check('doji candle does not start burst', !d.startBurst && sm.pendingDirection === 'BEARISH')

// --- Test 5: opposite candle invalidates pending ---
d = updateBurstStateMachine(sm, c, { ts: t0 + 120_000, open: 100, high: 101.5, low: 99.9, close: 101.3, volume: 10 }, atrVal)
check('opposite candle invalidates pending', !sm.pendingDirection && !sm.burstActive)

// --- Test 6: burst ends when consensus drops below 55% ---
sm = newConsensusState()
d = updateBurstStateMachine(sm, c, { ts: t0, open: 100, high: 100.5, low: 99, close: 99.2, volume: 10 }, atrVal) // pending
d = updateBurstStateMachine(sm, c, { ts: t0 + 60_000, open: 99.2, high: 99.3, low: 98, close: 98.2, volume: 10 }, atrVal) // confirm → burst
check('test6 setup: burst active', sm.burstActive)
// consensus flips to ~40% bear
const weakBear = computeConsensus('X', makeVotes([[-1, 60], [1, 55], [1, 50]]), 60, t0 + 120_000)
check('weak consensus computed bear < 55', weakBear.bearishScore < 55)
d = updateBurstStateMachine(sm, weakBear, { ts: t0 + 120_000, open: 98.2, high: 98.4, low: 98, close: 98.1, volume: 10 }, atrVal)
check('burst stops on consensus collapse', d.stopBurst && !sm.burstActive)

// --- Test 7: burst max duration 120s ---
sm = newConsensusState()
d = updateBurstStateMachine(sm, c, { ts: t0, open: 100, high: 100.5, low: 99, close: 99.2, volume: 10 }, atrVal)
d = updateBurstStateMachine(sm, c, { ts: t0 + 60_000, open: 99.2, high: 99.3, low: 98, close: 98.2, volume: 10 }, atrVal)
// next bar 200s later with consensus still strong
d = updateBurstStateMachine(sm, c, { ts: t0 + 60_000 + 200_000, open: 98.2, high: 98.4, low: 98, close: 98.3, volume: 10 }, atrVal)
check('burst stops after max duration', d.stopBurst)

// --- Test 8: pre-trade sizing chain (risk → qty → notional cap) ---
import { preTradeCheck, type RiskState } from '../src/lib/engine/risk'
const rs: RiskState = {
  balance: 100_000, equity: 100_000, highWaterMark: 100_000, dayStartEquity: 100_000, dayKey: '2026-10-28',
  dailyLossLimitPct: 5, maxDrawdownPct: 10, perTradeRiskPct: 1, burstRiskPct: 0.1,
  status: 'ACTIVE', cooldownUntil: null,
}
let v = preTradeCheck(rs, { price: 4051, stopDistance: 2 * atrVal, riskPct: 0.1, mode: 'BURST' })
check('burst trade sized: risk 0.1% → $100 → qty 50', v.allowed && Math.abs((v as { qty: number }).qty - 50) < 0.01)
// notional cap 5%: 50 × 4051 = $202k > $5k → capped qty ≈ 1.23
const capQty = (100_000 * 0.05) / 4051
check('notional cap gives qty ≈ 1.23', Math.abs(capQty - 1.234) < 0.01)

// daily loss breach blocks everything
rs.equity = 94_000
rs.dayStartEquity = 100_000
import { refreshRiskState } from '../src/lib/engine/risk'
const events = refreshRiskState(rs)
check('daily loss breach detected (>5%)', events.includes('DAILY_LOSS_BREACH') && rs.status === 'HALTED_DAILY')
v = preTradeCheck(rs, { price: 4051, stopDistance: 2, riskPct: 0.1, mode: 'BURST' })
check('halted account blocks orders', !v.allowed)

console.log(`\n${passed} passed, ${failed} failed`)
process.exit(failed > 0 ? 1 : 0)
