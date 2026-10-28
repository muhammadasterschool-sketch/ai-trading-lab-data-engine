import type { OHLCV, StrategyVote, ConsensusState } from './types'
import { STRATEGIES } from './strategies'

// ============ Consensus engine (the 60% rule) ============
//
// Each active strategy votes {direction, confidence}. Vote weight = confidence.
// bullishScore = Σ conf(bullish) / Σ conf(all non-neutral) × 100.
// If bullishScore ≥ threshold (default 60%) → market direction confirmed BULLISH.
// Then we wait for the CONFIRMATION CANDLE: the next closed 1m candle that
// closes in the same direction with a real body. Only then does burst mode arm.

export interface ConsensusEngineState {
  pendingDirection: 'BULLISH' | 'BEARISH' | null
  pendingSince: number | null
  confirmedDirection: 'BULLISH' | 'BEARISH' | null
  confirmationCandleAt: number | null
  burstActive: boolean
  burstStartedAt: number | null
  burstSeq: number
  lastBurstDir: 'BULLISH' | 'BEARISH' | null
}

export function newConsensusState(): ConsensusEngineState {
  return {
    pendingDirection: null,
    pendingSince: null,
    confirmedDirection: null,
    confirmationCandleAt: null,
    burstActive: false,
    burstStartedAt: null,
    burstSeq: 0,
    lastBurstDir: null,
  }
}

export function computeConsensus(
  symbol: string,
  votes: StrategyVote[],
  threshold: number,
  ts: number
): ConsensusState {
  let bull = 0
  let bear = 0
  for (const v of votes) {
    if (v.dir === 1) bull += v.conf
    else if (v.dir === -1) bear += v.conf
  }
  const total = bull + bear
  const bullishScore = total > 0 ? (bull / total) * 100 : 50
  const bearishScore = total > 0 ? (bear / total) * 100 : 50

  let direction: ConsensusState['direction'] = 'NEUTRAL'
  let thresholdMet = false
  const voters = votes.filter((v) => v.dir !== 0).length
  if (total >= 30 && voters >= 2) {
    // need at least 2 strategies voting (real confirmation, not a lone signal)
    if (bullishScore >= threshold) {
      direction = 'BULLISH'
      thresholdMet = true
    } else if (bearishScore >= threshold) {
      direction = 'BEARISH'
      thresholdMet = true
    }
  }
  return {
    symbol,
    bullishScore: Math.round(bullishScore * 10) / 10,
    bearishScore: Math.round(bearishScore * 10) / 10,
    direction: thresholdMet ? direction : 'NEUTRAL',
    thresholdMet,
    votes,
    ts,
  }
}

/**
 * Feed the latest CLOSED bar into the burst state machine.
 * Returns events to act on.
 */
export interface BurstDecision {
  armed: boolean
  startBurst: boolean
  stopBurst: boolean
  burstDirection: 'BULLISH' | 'BEARISH' | null
  reason: string
}

export function updateBurstStateMachine(
  state: ConsensusEngineState,
  consensus: ConsensusState,
  closedBar: OHLCV,
  atrValue: number,
  opts: { maxBurstSeconds?: number; dropThreshold?: number } = {}
): BurstDecision {
  const maxBurstSeconds = opts.maxBurstSeconds ?? 120
  const dropThreshold = opts.dropThreshold ?? 55
  const barBody = Math.abs(closedBar.close - closedBar.open)
  const minBody = atrValue * 0.15 // candle must have a real body
  const bullishCandle = closedBar.close > closedBar.open && barBody >= minBody
  const bearishCandle = closedBar.close < closedBar.open && barBody >= minBody
  const now = closedBar.ts

  const decision: BurstDecision = {
    armed: false,
    startBurst: false,
    stopBurst: false,
    burstDirection: null,
    reason: '',
  }

  // --- active burst management ---
  if (state.burstActive && state.burstStartedAt) {
    const heldFor = now - state.burstStartedAt
    const dir = state.lastBurstDir
    const stillConvicted =
      dir === 'BULLISH'
        ? consensus.bullishScore >= dropThreshold
        : consensus.bearishScore >= dropThreshold
    if (!stillConvicted) {
      state.burstActive = false
      state.confirmedDirection = null
      state.pendingDirection = null
      decision.stopBurst = true
      decision.reason = `Consensus below ${dropThreshold}% — burst ended`
      return decision
    }
    if (heldFor >= maxBurstSeconds * 1000) {
      state.burstActive = false
      state.confirmedDirection = null
      decision.stopBurst = true
      decision.reason = `Burst max duration (${maxBurstSeconds}s) reached`
      return decision
    }
    decision.armed = true
    decision.burstDirection = dir
    decision.reason = 'Burst active'
    return decision
  }

  // --- confirmation candle logic ---
  if (state.pendingDirection) {
    const dir = state.pendingDirection
    const confirmed =
      (dir === 'BULLISH' && bullishCandle) || (dir === 'BEARISH' && bearishCandle)
    if (confirmed) {
      state.confirmedDirection = dir
      state.confirmationCandleAt = now
      state.burstActive = true
      state.burstStartedAt = now
      state.burstSeq = 0
      state.lastBurstDir = dir
      decision.startBurst = true
      decision.armed = true
      decision.burstDirection = dir
      decision.reason = `Confirmation candle closed ${dir.toLowerCase()} — burst mode armed (1 trade/sec)`
      return decision
    }
    // opposite candle invalidates the pending confirmation
    const invalidated =
      (dir === 'BULLISH' && bearishCandle) || (dir === 'BEARISH' && bullishCandle)
    if (invalidated) {
      state.pendingDirection = null
      state.pendingSince = null
      decision.reason = 'Opposite candle — pending confirmation invalidated'
      return decision
    }
    decision.reason = `Awaiting ${dir.toLowerCase()} confirmation candle…`
    return decision
  }

  // --- fresh threshold crossing ---
  if (consensus.thresholdMet) {
    state.pendingDirection = consensus.direction === 'NEUTRAL' ? null : consensus.direction
    state.pendingSince = now
    decision.reason = `${consensus.direction} consensus ≥ threshold — awaiting confirmation candle`
  } else {
    decision.reason = 'No consensus threshold met'
  }
  return decision
}

/** Evaluate all active strategies on the latest closed bar */
export function collectVotes(
  bars: OHLCV[],
  activeKeys: string[],
  activeParams: Record<string, Record<string, number>> = {}
): StrategyVote[] {
  if (bars.length < 220) return []
  const i = bars.length - 1
  const votes: StrategyVote[] = []
  for (const s of STRATEGIES) {
    if (!activeKeys.includes(s.key)) continue
    const params = activeParams[s.key] ?? s.defaults
    try {
      const ctx = s.prepare(bars, params)
      const sig = s.signalAt(ctx, i, params)
      if (sig.dir !== 0 && sig.conf > 0) {
        votes.push({ key: s.key, name: s.name, dir: sig.dir, conf: sig.conf, reason: sig.reason })
      }
    } catch {
      // strategy error → skip vote
    }
  }
  return votes
}
