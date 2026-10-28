import { NextResponse } from 'next/server'
import { getAuthUser } from '@/lib/auth/session'
import { ingestMonthly, ingestDaily } from '@/lib/data/ingest'

// Fetch more real 1-minute data from the Binance Vision public repository.
// body: { symbol: 'PAXGUSDT' | 'BTCUSDT', months?: number, days?: number }
export async function POST(req: Request) {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  try {
    const { symbol, months, days } = await req.json()
    if (!['PAXGUSDT', 'BTCUSDT'].includes(symbol)) {
      return NextResponse.json({ error: 'Invalid symbol' }, { status: 400 })
    }
    const results: Array<{ period: string; status: string; bars?: number; error?: string }> = []

    if (months && months > 0) {
      const now = new Date()
      const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1))
      for (let i = 0; i < Math.min(months, 6); i++) {
        const year = d.getUTCFullYear()
        const month = d.getUTCMonth() + 1
        const res = await ingestMonthly(symbol, year, month)
        results.push(res)
        d.setUTCMonth(d.getUTCMonth() - 1)
      }
    }
    if (days && days > 0) {
      const now = new Date()
      const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()))
      d.setUTCDate(d.getUTCDate() - 1)
      for (let i = 0; i < Math.min(days, 14); i++) {
        const date = d.toISOString().slice(0, 10)
        const res = await ingestDaily(symbol, date)
        results.push(res)
        d.setUTCDate(d.getUTCDate() - 1)
      }
    }
    if (results.length === 0) {
      return NextResponse.json({ error: 'Specify months and/or days' }, { status: 400 })
    }
    const fetched = results.filter((r) => r.status === 'READY').reduce((s, r) => s + (r.bars ?? 0), 0)
    return NextResponse.json({ ok: true, fetched, results })
  } catch (e) {
    console.error('data fetch error', e)
    return NextResponse.json({ error: 'Fetch failed' }, { status: 500 })
  }
}
