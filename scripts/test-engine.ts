// Quick engine sanity test
import { PrismaClient } from '@prisma/client'
import { STRATEGIES } from '../src/lib/engine/strategies'
import { runBacktest, walkForward } from '../src/lib/engine/backtest'
import { runAutoScan } from '../src/lib/engine/autoscan'
import { computeConsensus } from '../src/lib/engine/consensus'
import { assessCrash, forecastNextMove } from '../src/lib/engine/crash'
import { expectedMaxNoiseZ, DSR_REFERENCE } from '../src/lib/engine/dsr'
import { verifyTotp, generateTotpSecret } from '../src/lib/auth/crypto'

const db = new PrismaClient()

async function main() {
  const t0 = Date.now()
  const bundles = await db.dataBundle.findMany({ where: { symbol: 'PAXGUSDT', status: 'READY' }, select: { id: true } })
  const rows = await db.bar.findMany({
    where: { bundleId: { in: bundles.map((b) => b.id) } },
    orderBy: { ts: 'asc' },
  })
  console.log(`loaded ${rows.length} gold bars in ${Date.now() - t0}ms (${new Date(rows[0].ts).toISOString().slice(0, 10)} → ${new Date(rows[rows.length - 1].ts).toISOString().slice(0, 10)})`)

  const bars = rows.map((r) => ({ ts: r.ts.getTime(), open: r.open, high: r.high, low: r.low, close: r.close, volume: r.volume }))
  const last30d = bars.slice(-43200) // ~30 days

  // 1. individual strategy backtests
  console.log('\n--- Backtest (30d, costs ON) ---')
  for (const s of STRATEGIES) {
    const t = Date.now()
    const res = runBacktest(last30d, s, s.defaults)
    console.log(
      `${s.key.padEnd(18)} trades=${String(res.metrics.trades).padStart(4)} win%=${(res.metrics.winRate * 100).toFixed(0).padStart(3)} net=${(res.metrics.netReturn * 100).toFixed(2)}% sharpe=${res.metrics.sharpe} dd=${(res.metrics.maxDrawdown * 100).toFixed(1)}% pf=${res.metrics.profitFactor} (${Date.now() - t}ms) exits=${JSON.stringify(res.exitReasons)}`
    )
  }

  // 2. no-cost comparison (show cost impact)
  const s0 = STRATEGIES[0]
  const noCost = runBacktest(last30d, s0, s0.defaults, { applyCosts: false })
  const withCost = runBacktest(last30d, s0, s0.defaults, { applyCosts: true })
  console.log(`\nCost impact (ema-crossover): no-cost net=${(noCost.metrics.netReturn * 100).toFixed(2)}% vs with-cost net=${(withCost.metrics.netReturn * 100).toFixed(2)}% | total costs=$${withCost.metrics.totalCosts}`)

  // 3. walk-forward
  console.log('\n--- Walk-forward (5 folds, ema-crossover) ---')
  const wf = walkForward(last30d, s0, s0.defaults)
  for (const f of wf.foldStats) console.log(`  fold ${f.fold}: ${f.from}→${f.to} trades=${f.trades} net=${(f.netReturn * 100).toFixed(2)}% sharpe=${f.sharpe}`)
  console.log(`  aggregate: trades=${wf.aggregate.trades} net=${(wf.aggregate.netReturn * 100).toFixed(2)}% sharpe=${wf.aggregate.sharpe}`)

  // 4. auto-scan (all 5 strategies)
  console.log('\n--- Auto-scan ---')
  const t1 = Date.now()
  const scan = runAutoScan(bars.slice(-86400), STRATEGIES.map((s) => s.key), { topK: 5 })
  console.log(`trials=${scan.trials} in ${scan.durationMs}ms | noiseBar=${scan.noiseBarZ}σ (σ_trials=${scan.sigmaTrials}) | winner clears noise: ${scan.clearsNoise}`)
  for (const r of scan.results) {
    console.log(`  #${r.rank} ${r.strategyKey} ${JSON.stringify(r.params)} sharpe=${r.sharpe} oos=${r.oosSharpe ?? '-'} trades=${r.trades}`)
  }

  // 5. DSR reference check
  console.log('\n--- DSR noise bar check ---')
  for (const ref of DSR_REFERENCE) {
    const calc = expectedMaxNoiseZ(ref.n)
    console.log(`  N=${ref.n}: published=${ref.sigma}σ computed=${calc.toFixed(2)}σ ${Math.abs(calc - ref.sigma) < 0.06 ? '✓' : '✗'}`)
  }

  // 6. consensus + crash + forecast
  console.log('\n--- Live signals (last bar) ---')
  const votes = STRATEGIES.map((s) => {
    const ctx = s.prepare(bars, s.defaults)
    return { s, sig: s.signalAt(ctx, bars.length - 1, s.defaults) }
  })
  for (const v of votes) console.log(`  ${v.s.key.padEnd(18)} dir=${v.sig.dir === 1 ? 'LONG ' : v.sig.dir === -1 ? 'SHORT' : 'FLAT '} conf=${v.sig.conf} — ${v.sig.reason}`)
  const stratVotes = votes.filter((v) => v.sig.dir !== 0).map((v) => ({ key: v.s.key, name: v.s.name, dir: v.sig.dir as 1 | -1, conf: v.sig.conf, reason: v.sig.reason }))
  const cons = computeConsensus('PAXGUSDT', stratVotes, 60, Date.now())
  console.log(`  CONSENSUS: bull=${cons.bullishScore}% bear=${cons.bearishScore}% → ${cons.direction} (thresholdMet=${cons.thresholdMet})`)
  const crash = assessCrash(bars)
  console.log(`  CRASH: prob=${crash.probability}% melt-up=${crash.meltUpProbability}% severity=${crash.severity} — ${crash.narrative}`)
  const fc = forecastNextMove(bars)
  console.log(`  FORECAST(5m): ${fc.direction} conf=${fc.confidence}% from ${fc.refPrice}`)

  // 7. TOTP check
  console.log('\n--- TOTP ---')
  const secret = generateTotpSecret()
  console.log(`  secret=${secret} verify(wrong)=${verifyTotp(secret, '000000')} (expected false unless lucky)`)

  console.log(`\nAll checks done in ${Date.now() - t0}ms`)
}

main().catch(console.error).finally(() => db.$disconnect())
