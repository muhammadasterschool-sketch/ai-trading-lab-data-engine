import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'

export async function GET() {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  try {
    const [predictions, crashAlerts] = await Promise.all([
      db.prediction.findMany({ where: { symbol: 'PAXGUSDT' }, orderBy: { ts: 'desc' }, take: 60 }),
      db.crashAlert.findMany({ where: { symbol: 'PAXGUSDT' }, orderBy: { ts: 'desc' }, take: 30 }),
    ])
    const resolved = predictions.filter((p) => p.resolvedAt !== null)
    const accuracy = resolved.length ? resolved.filter((p) => p.correct).length / resolved.length : null
    const recentAccuracy = (() => {
      const last20 = resolved.slice(0, 20)
      return last20.length ? last20.filter((p) => p.correct).length / last20.length : null
    })()
    return NextResponse.json({
      latest: predictions[0] ?? null,
      predictions,
      crashAlerts,
      stats: { total: predictions.length, resolved: resolved.length, accuracy, recentAccuracy },
    })
  } catch (e) {
    console.error('predictions error', e)
    return NextResponse.json({ error: 'Failed' }, { status: 500 })
  }
}
