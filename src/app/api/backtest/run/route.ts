import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'
import { getStrategy } from '@/lib/engine/strategies'
import { runBacktest, walkForward } from '@/lib/engine/backtest'
import { loadSymbolBars } from '@/lib/data/ingest'

export async function POST(req: Request) {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  try {
    const body = await req.json()
    const {
      symbol = 'PAXGUSDT',
      strategyKey,
      params = {},
      days = 30,
      costs = true,
      walkForward: wf = false,
      stopAtrMult = 2,
      targetAtrMult = 3,
    } = body

    const strategy = getStrategy(strategyKey)
    if (!strategy) return NextResponse.json({ error: 'Unknown strategy' }, { status: 400 })

    const needBars = Math.max(days, 7) * 1440 + 300
    const bars = await loadSymbolBars(symbol, needBars, needBars)
    if (bars.length < 2000) return NextResponse.json({ error: 'Not enough data — fetch more in the Data tab' }, { status: 400 })

    const mergedParams = { ...strategy.defaults, ...params }
    const options = { applyCosts: costs, stopAtrMult, targetAtrMult, startEquity: 100_000 }

    const t0 = Date.now()
    const result = runBacktest(bars, strategy, mergedParams, options)
    const foldStats = wf ? walkForward(bars, strategy, mergedParams, { ...options, folds: 5 }) : null
    const durationMs = Date.now() - t0

    const run = await db.backtestRun.create({
      data: {
        symbol,
        strategyKey,
        params: JSON.stringify(mergedParams),
        startDate: new Date(bars[0].ts),
        endDate: new Date(bars[bars.length - 1].ts),
        costsApplied: costs,
        walkForward: wf,
        metrics: JSON.stringify(result.metrics),
        equityCurve: JSON.stringify(result.equityCurve),
        foldStats: JSON.stringify(foldStats?.foldStats ?? []),
        tradeSample: JSON.stringify(result.trades.slice(-50)),
      },
    })

    return NextResponse.json({
      ok: true,
      runId: run.id,
      durationMs,
      barsUsed: bars.length,
      range: { from: new Date(bars[0].ts).toISOString(), to: new Date(bars[bars.length - 1].ts).toISOString() },
      params: mergedParams,
      metrics: result.metrics,
      exitReasons: result.exitReasons ?? {},
      equityCurve: result.equityCurve,
      tradeSample: result.trades.slice(-30),
      foldStats: foldStats
        ? { folds: foldStats.foldStats, aggregate: foldStats.aggregate, equityCurve: foldStats.equityCurve }
        : null,
    })
  } catch (e) {
    console.error('backtest error', e)
    return NextResponse.json({ error: 'Backtest failed' }, { status: 500 })
  }
}
