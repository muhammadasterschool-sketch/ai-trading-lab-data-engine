import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'

export async function GET() {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  const bundles = await db.dataBundle.findMany({ orderBy: [{ symbol: 'asc' }, { period: 'asc' }] })
  const totalBars = await db.bar.count()
  return NextResponse.json({
    bundles: bundles.map((b) => ({
      id: b.id,
      symbol: b.symbol,
      period: b.period,
      source: b.source,
      sourceUrl: b.sourceUrl,
      startDate: b.startDate,
      endDate: b.endDate,
      barCount: b.barCount,
      gaps: b.gaps,
      duplicates: b.duplicates,
      outliers: b.outliers,
      quality: b.quality,
      status: b.status,
      provenance: JSON.parse(b.provenance || '{}'),
      fetchedAt: b.fetchedAt,
    })),
    totalBars,
  })
}
