import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'

// TCA digest (report §8.3): arrival-price shortfall per strategy / mode / side.
export async function GET() {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  const account = await db.paperAccount.findFirst({ where: { userId: user.id } })
  if (!account) return NextResponse.json({ digest: null })

  const fills = await db.paperOrder.findMany({
    where: { accountId: account.id, status: 'FILLED' },
    orderBy: { createdAt: 'desc' },
    take: 2000,
  })
  if (fills.length === 0) return NextResponse.json({ digest: { totalFills: 0 } })

  const groups: Record<string, { fills: number; bps: number; costs: number }> = {}
  for (const f of fills) {
    if (f.fillPrice === null || f.decisionPrice === null) continue
    const dir = f.side === 'BUY' ? 1 : -1
    const notional = f.decisionPrice * f.qty
    if (notional <= 0) continue
    const shortfallBps = ((f.fillPrice - f.decisionPrice) * dir * f.qty) / notional * 10_000
    const cost = (f.spreadCost ?? 0) + (f.fee ?? 0) + (f.slippage ?? 0) + (f.impactEstimate ?? 0)
    for (const key of [`strategy:${f.strategyKey ?? 'manual'}`, `mode:${f.mode}`, `side:${f.side}`]) {
      groups[key] ??= { fills: 0, bps: 0, costs: 0 }
      groups[key].fills++
      groups[key].bps += shortfallBps
      groups[key].costs += cost
    }
  }
  const digest = {
    totalFills: fills.length,
    groups: Object.fromEntries(
      Object.entries(groups).map(([k, v]) => [k, { fills: v.fills, avgShortfallBps: round2(v.bps / v.fills), totalCosts: round2(v.costs) }])
    ),
    overall: {
      avgShortfallBps: round2(fills.reduce((s, f) => s + (f.fillPrice && f.decisionPrice ? ((f.fillPrice - f.decisionPrice) * (f.side === 'BUY' ? 1 : -1) * f.qty) / (f.decisionPrice * f.qty) * 10_000 : 0), 0) / fills.length),
      totalCosts: round2(fills.reduce((s, f) => s + (f.spreadCost ?? 0) + (f.fee ?? 0) + (f.slippage ?? 0) + (f.impactEstimate ?? 0), 0)),
    },
  }
  return NextResponse.json({ digest })
}

function round2(v: number) {
  return Math.round(v * 100) / 100
}
