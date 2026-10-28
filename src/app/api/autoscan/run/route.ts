import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'
import { runAutoScan } from '@/lib/engine/autoscan'
import { STRATEGIES } from '@/lib/engine/strategies'
import { loadSymbolBars } from '@/lib/data/ingest'

export async function POST(req: Request) {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  try {
    const body = await req.json()
    const { symbol = 'PAXGUSDT', days = 30, strategies } = body
    const keys = Array.isArray(strategies) && strategies.length > 0 ? strategies : STRATEGIES.map((s) => s.key)

    const needBars = Math.max(days, 7) * 1440 + 300
    const bars = await loadSymbolBars(symbol, needBars, needBars)
    if (bars.length < 5000) return NextResponse.json({ error: 'Not enough data — fetch more in the Data tab' }, { status: 400 })

    const scan = await db.scanRun.create({
      data: { symbol, days, strategies: JSON.stringify(keys), status: 'RUNNING' },
    })

    const t0 = Date.now()
    const output = runAutoScan(bars, keys, { topK: 15 })
    await db.scanRun.update({
      where: { id: scan.id },
      data: {
        status: 'DONE',
        trials: output.trials,
        noiseBar: output.noiseBarZ,
        finishedAt: new Date(),
      },
    })
    for (const r of output.results) {
      await db.scanResult.create({
        data: {
          scanId: scan.id,
          strategyKey: r.strategyKey,
          params: JSON.stringify(r.params),
          trades: r.trades,
          winRate: r.winRate,
          sharpe: r.sharpe,
          sortino: r.sortino,
          maxDrawdown: r.maxDrawdown,
          netReturn: r.netReturn,
          profitFactor: r.profitFactor,
          oosSharpe: r.oosSharpe ?? null,
          oosReturn: r.oosReturn ?? null,
          rank: r.rank ?? null,
        },
      })
    }

    return NextResponse.json({
      ok: true,
      scanId: scan.id,
      durationMs: Date.now() - t0,
      trials: output.trials,
      noiseBarZ: output.noiseBarZ,
      noiseBarSharpe: output.noiseBarSharpe,
      sigmaTrials: output.sigmaTrials,
      deflatedSharpe: output.deflatedSharpe,
      clearsNoise: output.clearsNoise,
      isBars: output.isBars,
      oosBars: output.oosBars,
      results: output.results,
    })
  } catch (e) {
    console.error('autoscan error', e)
    return NextResponse.json({ error: 'Scan failed' }, { status: 500 })
  }
}
