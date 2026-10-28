import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { getAuthUser, requireAdmin } from '@/lib/auth/session'

export async function GET() {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  const requests = await db.approvalRequest.findMany({ orderBy: [{ status: 'asc' }, { createdAt: 'desc' }], take: 100 })
  return NextResponse.json({ requests })
}

export async function POST(req: Request) {
  const user = await getAuthUser()
  if (!user) return NextResponse.json({ error: 'Authentication required' }, { status: 401 })
  try {
    const { action, id, title, type, evidence, refKey, note } = await req.json()

    if (action === 'create') {
      await db.approvalRequest.create({
        data: {
          type: type ?? 'SCAN_WINNER',
          refKey: refKey ?? null,
          title: title ?? 'Untitled request',
          evidence: JSON.stringify(evidence ?? {}),
          requestedBy: user.email,
        },
      })
      return NextResponse.json({ ok: true })
    }
    if (action === 'decide') {
      const admin = await requireAdmin()
      if (!admin) return NextResponse.json({ error: 'Only admins can approve/reject' }, { status: 403 })
      const request = await db.approvalRequest.findUnique({ where: { id } })
      if (!request) return NextResponse.json({ error: 'Request not found' }, { status: 404 })
      if (request.status !== 'PENDING') return NextResponse.json({ error: 'Already decided' }, { status: 400 })
      const approve = note !== 'REJECT'
      await db.approvalRequest.update({
        where: { id },
        data: { status: approve ? 'APPROVED' : 'REJECTED', decidedBy: admin.email, decidedAt: new Date(), note: note ?? null },
      })
      if (approve && request.type === 'STRATEGY' && request.refKey) {
        await db.strategy.update({ where: { key: request.refKey }, data: { status: 'ACTIVE' } }).catch(() => {})
      }
      return NextResponse.json({ ok: true, status: approve ? 'APPROVED' : 'REJECTED' })
    }
    return NextResponse.json({ error: 'Unknown action' }, { status: 400 })
  } catch (e) {
    console.error('approvals error', e)
    return NextResponse.json({ error: 'Action failed' }, { status: 500 })
  }
}
