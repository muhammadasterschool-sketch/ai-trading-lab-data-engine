import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser } from '@/lib/auth/session'

export async function GET() {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  const account = await db.paperAccount.findFirst({ where: { userId: user.id } })
  if (!account) return NextResponse.json({ events: [] })
  const events = await db.riskEvent.findMany({ where: { accountId: account.id }, orderBy: { ts: 'desc' }, take: 100 })
  return NextResponse.json({ events })
}
