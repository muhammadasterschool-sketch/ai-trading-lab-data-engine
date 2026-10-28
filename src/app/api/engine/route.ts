import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser, requireAdmin } from '@/lib/auth/session'

// Engine control: autopilot on/off, kill switch, reset account.
// The engine mini-service polls EngineState and reacts within ~2s.
export async function GET() {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  const state = await db.engineState.findUnique({ where: { id: 'singleton' } })
  return NextResponse.json({ state })
}

export async function POST(req: Request) {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  try {
    const { action } = await req.json()
    await db.engineState.upsert({
      where: { id: 'singleton' },
      create: { id: 'singleton', running: true },
      update: {},
    })

    switch (action) {
      case 'autopilot-on': {
        const account = await db.paperAccount.findFirst({ where: { userId: user.id } })
        if (account && account.status === 'KILLED') {
          return NextResponse.json({ error: 'Account is KILLED — reset it first' }, { status: 400 })
        }
        await db.engineState.update({ where: { id: 'singleton' }, data: { autopilot: true, killSwitch: false } })
        return NextResponse.json({ ok: true, autopilot: true })
      }
      case 'autopilot-off': {
        await db.engineState.update({ where: { id: 'singleton' }, data: { autopilot: false } })
        return NextResponse.json({ ok: true, autopilot: false })
      }
      case 'close-all': {
        await db.engineState.update({ where: { id: 'singleton' }, data: { closeAll: true } })
        return NextResponse.json({ ok: true })
      }
      case 'kill-switch': {
        await db.engineState.update({ where: { id: 'singleton' }, data: { autopilot: false, killSwitch: true } })
        return NextResponse.json({ ok: true, killSwitch: true })
      }
      case 'release-kill': {
        await db.engineState.update({ where: { id: 'singleton' }, data: { killSwitch: false } })
        return NextResponse.json({ ok: true, killSwitch: false })
      }
      case 'reset-account': {
        const admin = await requireAdmin()
        if (!admin) return NextResponse.json({ error: 'Admin required for account reset' }, { status: 403 })
        const account = await db.paperAccount.findFirst({ where: { userId: user.id } })
        if (!account) return NextResponse.json({ error: 'No account' }, { status: 404 })
        await db.paperPosition.deleteMany({ where: { accountId: account.id } })
        await db.paperOrder.deleteMany({ where: { accountId: account.id } })
        await db.paperTrade.deleteMany({ where: { accountId: account.id } })
        await db.riskEvent.deleteMany({ where: { accountId: account.id } })
        await db.paperAccount.update({
          where: { id: account.id },
          data: {
            balance: account.startBalance,
            equity: account.startBalance,
            highWaterMark: account.startBalance,
            dayStartEquity: account.startBalance,
            status: 'ACTIVE',
            cooldownUntil: null,
          },
        })
        await db.engineState.update({ where: { id: 'singleton' }, data: { autopilot: false, killSwitch: false } })
        return NextResponse.json({ ok: true })
      }
      default:
        return NextResponse.json({ error: 'Unknown action' }, { status: 400 })
    }
  } catch (e) {
    console.error('engine control error', e)
    return NextResponse.json({ error: 'Action failed' }, { status: 500 })
  }
}
