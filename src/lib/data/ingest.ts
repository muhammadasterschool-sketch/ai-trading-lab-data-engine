import { db } from '@/lib/db'
import { fetchZipCsv, parseKlinesCsv, qualityGate, monthlyUrl, dailyUrl } from './binanceVision'

// ============ Ingest pipeline: repo → quality gate → DB with provenance ============

export interface IngestResult {
  period: string
  status: 'READY' | 'FAILED' | 'SKIPPED'
  bars?: number
  gaps?: number
  duplicates?: number
  outliers?: number
  error?: string
}

export async function ingestMonthly(symbol: string, year: number, month: number): Promise<IngestResult> {
  const period = `${year}-${String(month).padStart(2, '0')}`
  const url = monthlyUrl(symbol, year, month)
  return ingestFromUrl(symbol, period, url)
}

export async function ingestDaily(symbol: string, date: string): Promise<IngestResult> {
  const url = dailyUrl(symbol, date)
  return ingestFromUrl(symbol, date, url)
}

async function ingestFromUrl(symbol: string, period: string, url: string): Promise<IngestResult> {
  // skip if bundle already exists and is READY
  const existing = await db.dataBundle.findFirst({ where: { symbol, period, status: 'READY' } })
  if (existing) return { period, status: 'SKIPPED', bars: existing.barCount }
  // clean up previous failed attempts
  await db.dataBundle.deleteMany({ where: { symbol, period, status: 'FAILED' } })

  const bundle = await db.dataBundle.create({
    data: {
      symbol,
      timeframe: '1m',
      source: 'binance-vision-repo',
      sourceUrl: url,
      period,
      startDate: new Date(0),
      endDate: new Date(0),
      status: 'FETCHING',
    },
  })

  try {
    const { csv, sha256, bytes } = await fetchZipCsv(url)
    const raw = parseKlinesCsv(csv)
    if (raw.length === 0) throw new Error('empty dataset')
    const q = qualityGate(raw)

    const CHUNK = 2000
    for (let i = 0; i < q.bars.length; i += CHUNK) {
      const chunk = q.bars.slice(i, i + CHUNK).map((b) => ({
        bundleId: bundle.id,
        ts: new Date(b.ts),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
        volume: b.volume,
      }))
      await db.bar.createMany({ data: chunk })
    }

    const start = q.bars[0]
    const end = q.bars[q.bars.length - 1]
    await db.dataBundle.update({
      where: { id: bundle.id },
      data: {
        status: 'READY',
        startDate: new Date(start.ts),
        endDate: new Date(end.ts),
        barCount: q.bars.length,
        gaps: q.gaps,
        duplicates: q.duplicates + q.nonMonotone,
        outliers: q.outliers,
        quality: q.outliers > q.bars.length * 0.01 ? 'WARN' : 'PASSED',
        provenance: JSON.stringify({
          repository: 'data.binance.vision',
          url,
          sha256,
          bytes,
          rawRows: raw.length,
          cleanRows: q.bars.length,
          fetchedAt: new Date().toISOString(),
          note: symbol === 'PAXGUSDT' ? 'Paxos Gold — 1:1 physical gold backed, tracks spot XAUUSD' : 'Spot market data',
        }),
      },
    })
    console.log(`[ingest] ${symbol} ${period}: ${q.bars.length} bars, ${q.gaps} gaps, sha256=${sha256.slice(0, 12)}…`)
    return { period, status: 'READY', bars: q.bars.length, gaps: q.gaps, duplicates: q.duplicates, outliers: q.outliers }
  } catch (e) {
    await db.dataBundle.update({
      where: { id: bundle.id },
      data: { status: 'FAILED', error: e instanceof Error ? e.message : String(e) },
    })
    await db.bar.deleteMany({ where: { bundleId: bundle.id } })
    return { period, status: 'FAILED', error: e instanceof Error ? e.message : String(e) }
  }
}

/** Load bars for a symbol as engine OHLCV[] (all READY bundles, time-ordered, deduped). */
export async function loadSymbolBars(symbol: string, maxBars = 500_000, latestN?: number) {
  const bundles = await db.dataBundle.findMany({ where: { symbol, status: 'READY' }, select: { id: true } })
  if (bundles.length === 0) return [] as Array<{ ts: number; open: number; high: number; low: number; close: number; volume: number }>
  // when only the most recent N bars are needed, query desc + reverse (memory-safe)
  const query = {
    where: { bundleId: { in: bundles.map((b) => b.id) } },
    orderBy: { ts: 'desc' as const },
    take: latestN ?? maxBars,
  }
  const rows = await db.bar.findMany(query)
  rows.reverse()
  const seen = new Set<number>()
  const out: Array<{ ts: number; open: number; high: number; low: number; close: number; volume: number }> = []
  for (const r of rows) {
    const t = r.ts.getTime()
    if (seen.has(t)) continue
    seen.add(t)
    out.push({ ts: t, open: r.open, high: r.high, low: r.low, close: r.close, volume: r.volume })
  }
  return out
}
