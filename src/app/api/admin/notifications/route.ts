import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { requireAdmin } from '@/lib/auth/session'

// v5.6 — Admin notification feed: the owner sees EVERY registration
// (any invitation code) here first, with an unread badge.

export async function GET() {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Admin access required' }, { status: 403 })

  const [items, unreadCount] = await Promise.all([
    db.adminNotification.findMany({
      orderBy: { createdAt: 'desc' },
      take: 100,
    }),
    db.adminNotification.count({ where: { read: false } }),
  ])

  return NextResponse.json({ items, unreadCount })
}

export async function POST(req: Request) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Admin access required' }, { status: 403 })

  try {
    const body = await req.json().catch(() => ({}) as { action?: string; id?: string })
    const { action, id } = body
    if (action === 'read-all') {
      await db.adminNotification.updateMany({ where: { read: false }, data: { read: true } })
    } else if (action === 'read' && id) {
      await db.adminNotification.update({ where: { id }, data: { read: true } })
    } else {
      return NextResponse.json({ error: 'Unknown action' }, { status: 400 })
    }
    return NextResponse.json({ ok: true })
  } catch (e) {
    console.error('notifications POST error', e)
    return NextResponse.json({ error: 'Failed to update notifications' }, { status: 500 })
  }
}
