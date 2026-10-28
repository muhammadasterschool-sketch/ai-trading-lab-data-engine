import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'
import { DSR_REFERENCE } from '@/lib/engine/dsr'

// Dashboard aggregate: account, recent trades, consensus log, engine state
export async function GET() {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })

  const [account, engineState] = await Promise.all([
    db.paperAccount.findFirst({ where: { userId: user.id } }),
    db.engineState.findUnique({ where: { id: 'singleton' } }),
  ])

  const [trades, consensus, riskEvents] = account
    ? await Promise.all([
        db.paperTrade.findMany({ where: { accountId: account.id }, orderBy: { entryAt: 'desc' }, take: 25 }),
        db.consensusLog.findMany({ where: { symbol: 'PAXGUSDT' }, orderBy: { ts: 'desc' }, take: 20 }),
        db.riskEvent.findMany({ where: { accountId: account.id }, orderBy: { ts: 'desc' }, take: 10 }),
      ])
    : [[], [], []]

  const closed = trades.filter((t) => t.status === 'CLOSED' && t.pnl !== null)
  const wins = closed.filter((t) => (t.pnl ?? 0) > 0).length

  return NextResponse.json({
    account,
    engineState,
    trades,
    consensus,
    riskEvents,
    stats: {
      closedTrades: closed.length,
      winRate: closed.length ? wins / closed.length : null,
      realizedPnl: closed.reduce((s, t) => s + (t.pnl ?? 0), 0),
    },
    dsrReference: DSR_REFERENCE,
  })
}
