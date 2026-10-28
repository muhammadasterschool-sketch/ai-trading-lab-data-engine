import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'
import { STRATEGY_META } from '@/lib/engine/strategies'

export async function GET() {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  const strategies = await db.strategy.findMany({ orderBy: { createdAt: 'asc' } })
  return NextResponse.json({ strategies, meta: STRATEGY_META })
}

export async function POST(req: Request) {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  try {
    const { key, action, params } = await req.json()
    const strategy = await db.strategy.findUnique({ where: { key } })
    if (!strategy) return NextResponse.json({ error: 'Strategy not found' }, { status: 404 })

    if (action === 'toggle-status') {
      const next = strategy.status === 'ACTIVE' ? 'PAUSED' : 'ACTIVE'
      // PROPOSED strategies need approval to become ACTIVE (governance)
      if (strategy.status === 'PROPOSED') {
        return NextResponse.json({ error: 'Proposed strategies need approval first (see Approvals tab)' }, { status: 400 })
      }
      await db.strategy.update({ where: { id: strategy.id }, data: { status: next } })
      return NextResponse.json({ ok: true, status: next })
    }
    if (action === 'update-params') {
      if (params && typeof params === 'object') {
        await db.strategy.update({ where: { id: strategy.id }, data: { params: JSON.stringify(params) } })
      }
      return NextResponse.json({ ok: true })
    }
    return NextResponse.json({ error: 'Unknown action' }, { status: 400 })
  } catch (e) {
    console.error('strategies error', e)
    return NextResponse.json({ error: 'Action failed' }, { status: 500 })
  }
}
