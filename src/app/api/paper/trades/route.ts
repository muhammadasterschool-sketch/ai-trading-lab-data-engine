import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'

export async function GET(req: Request) {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  const url = new URL(req.url)
  const mode = url.searchParams.get('mode') // NORMAL | BURST | ALL
  const limit = Math.min(Number(url.searchParams.get('limit') ?? 100), 500)
  const account = await db.paperAccount.findFirst({ where: { userId: user.id } })
  if (!account) return NextResponse.json({ trades: [] })
  const trades = await db.paperTrade.findMany({
    where: {
      accountId: account.id,
      ...(mode && mode !== 'ALL' ? { mode } : {}),
    },
    orderBy: { entryAt: 'desc' },
    take: limit,
  })
  const closed = trades.filter((t) => t.status === 'CLOSED')
  const wins = closed.filter((t) => (t.pnl ?? 0) > 0).length
  const stats = {
    total: trades.length,
    closed: closed.length,
    open: trades.length - closed.length,
    winRate: closed.length ? wins / closed.length : 0,
    totalPnl: closed.reduce((s, t) => s + (t.pnl ?? 0), 0),
    burstCount: trades.filter((t) => t.mode === 'BURST').length,
    normalCount: trades.filter((t) => t.mode === 'NORMAL').length,
    avgTcaBps: (() => {
      const withTca = closed.filter((t) => t.tcaBps !== null)
      return withTca.length ? withTca.reduce((s, t) => s + (t.tcaBps ?? 0), 0) / withTca.length : null
    })(),
  }
  return NextResponse.json({ trades, stats })
}
