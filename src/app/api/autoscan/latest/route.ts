import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'

export async function GET() {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  const scan = await db.scanRun.findFirst({ where: { status: 'DONE' }, orderBy: { startedAt: 'desc' }, include: { results: true } })
  if (!scan) return NextResponse.json({ scan: null })
  return NextResponse.json({
    scan: {
      id: scan.id,
      symbol: scan.symbol,
      days: scan.days,
      trials: scan.trials,
      noiseBar: scan.noiseBar,
      startedAt: scan.startedAt,
      finishedAt: scan.finishedAt,
      results: scan.results.sort((a, b) => (a.rank ?? 99) - (b.rank ?? 99)),
    },
  })
}
