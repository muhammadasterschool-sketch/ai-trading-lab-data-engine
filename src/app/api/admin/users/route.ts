import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { requireAdmin } from '@/lib/auth/session'
import { hashPassword, generatePassword } from '@/lib/auth/crypto'

export async function GET() {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Admin access required' }, { status: 403 })
  const users = await db.user.findMany({
    orderBy: { createdAt: 'asc' },
    select: {
      id: true,
      email: true,
      name: true,
      role: true,
      totpEnabled: true,
      isActive: true,
      lastLoginAt: true,
      createdAt: true,
    },
  })
  const sessions = await db.session.count()
  return NextResponse.json({ users, stats: { total: users.length, active: users.filter((u) => u.isActive).length, sessions } })
}

export async function POST(req: Request) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Admin access required' }, { status: 403 })
  try {
    const { action, userId } = await req.json()
    const target = await db.user.findUnique({ where: { id: userId } })
    if (!target) return NextResponse.json({ error: 'User not found' }, { status: 404 })

    switch (action) {
      case 'toggle-active': {
        if (target.id === admin.id) {
          return NextResponse.json({ error: 'You cannot deactivate your own account' }, { status: 400 })
        }
        const updated = await db.user.update({ where: { id: userId }, data: { isActive: !target.isActive } })
        if (!updated.isActive) {
          await db.session.deleteMany({ where: { userId } })
        }
        return NextResponse.json({ ok: true, isActive: updated.isActive })
      }
      case 'reset-password': {
        const password = generatePassword()
        await db.user.update({
          where: { id: userId },
          data: { passwordHash: hashPassword(password), totpEnabled: false, totpSecret: null },
        })
        await db.session.deleteMany({ where: { userId } })
        return NextResponse.json({ ok: true, tempPassword: password })
      }
      case 'set-role': {
        const { role } = (await req.json()) as { role?: string }
        if (!['ADMIN', 'TRADER'].includes(role ?? '')) {
          return NextResponse.json({ error: 'Invalid role' }, { status: 400 })
        }
        if (target.id === admin.id && role !== 'ADMIN') {
          return NextResponse.json({ error: 'You cannot demote yourself' }, { status: 400 })
        }
        await db.user.update({ where: { id: userId }, data: { role: role! } })
        return NextResponse.json({ ok: true })
      }
      case 'force-2fa-reset': {
        await db.user.update({ where: { id: userId }, data: { totpEnabled: false, totpSecret: null } })
        await db.session.deleteMany({ where: { userId } })
        return NextResponse.json({ ok: true })
      }
      default:
        return NextResponse.json({ error: 'Unknown action' }, { status: 400 })
    }
  } catch (e) {
    console.error('admin users error', e)
    return NextResponse.json({ error: 'Action failed' }, { status: 500 })
  }
}
