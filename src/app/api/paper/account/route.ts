import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'

export async function GET() {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  let account = await db.paperAccount.findFirst({ where: { userId: user.id } })
  if (!account) {
    account = await db.paperAccount.create({ data: { userId: user.id, symbol: 'PAXGUSDT' } })
  }
  const positions = await db.paperPosition.findMany({ where: { accountId: account.id, status: 'OPEN' } })
  return NextResponse.json({ account, openPositions: positions.length })
}

export async function POST(req: Request) {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  try {
    const { dailyLossLimitPct, maxDrawdownPct, perTradeRiskPct, burstRiskPct, maxBurstTrades, consensusThreshold, burstEnabled } = await req.json()
    const account = await db.paperAccount.findFirst({ where: { userId: user.id } })
    if (!account) return NextResponse.json({ error: 'No account' }, { status: 404 })
    await db.paperAccount.update({
      where: { id: account.id },
      data: {
        dailyLossLimitPct: clamp(dailyLossLimitPct, 1, 25, account.dailyLossLimitPct),
        maxDrawdownPct: clamp(maxDrawdownPct, 2, 50, account.maxDrawdownPct),
        perTradeRiskPct: clamp(perTradeRiskPct, 0.1, 5, account.perTradeRiskPct),
        burstRiskPct: clamp(burstRiskPct, 0.01, 2, account.burstRiskPct),
        maxBurstTrades: Math.round(clamp(maxBurstTrades, 10, 300, account.maxBurstTrades)),
        consensusThreshold: clamp(consensusThreshold, 50, 90, account.consensusThreshold),
        burstEnabled: typeof burstEnabled === 'boolean' ? burstEnabled : account.burstEnabled,
      },
    })
    return NextResponse.json({ ok: true })
  } catch (e) {
    console.error('account update error', e)
    return NextResponse.json({ error: 'Update failed' }, { status: 500 })
  }
}

function clamp(v: unknown, min: number, max: number, fallback: number) {
  const n = Number(v)
  if (!isFinite(n)) return fallback
  return Math.min(max, Math.max(min, n))
}
