import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { requireAdmin } from '@/lib/auth/session'

// GET — list all invitation codes with usage stats
export async function GET() {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Admin access required' }, { status: 403 })
  const codes = await db.invitationCode.findMany({ orderBy: { createdAt: 'desc' } })
  return NextResponse.json({ codes })
}

// POST — create a new code, toggle a code, or delete a code
export async function POST(req: Request) {
  const admin = await requireAdmin()
  if (!admin) return NextResponse.json({ error: 'Admin access required' }, { status: 403 })
  try {
    const { action, id, code, label, maxUses } = await req.json()

    switch (action) {
      case 'create': {
        const clean = String(code ?? '').trim().toUpperCase()
        if (!/^[A-Z0-9]{6,12}$/.test(clean)) {
          return NextResponse.json(
            { error: 'Code must be 6-12 letters/numbers (A-Z, 0-9)' },
            { status: 400 },
          )
        }
        const dup = await db.invitationCode.findUnique({ where: { code: clean } })
        if (dup) return NextResponse.json({ error: 'This code already exists' }, { status: 409 })
        const created = await db.invitationCode.create({
          data: {
            code: clean,
            label: String(label ?? '').trim().slice(0, 60),
            maxUses: Math.max(0, Math.min(9999, Number(maxUses) || 0)),
            createdBy: admin.name || admin.email,
          },
        })
        return NextResponse.json({ ok: true, code: created })
      }
      case 'toggle': {
        const target = await db.invitationCode.findUnique({ where: { id } })
        if (!target) return NextResponse.json({ error: 'Code not found' }, { status: 404 })
        const updated = await db.invitationCode.update({
          where: { id },
          data: { active: !target.active },
        })
        return NextResponse.json({ ok: true, active: updated.active })
      }
      case 'delete': {
        await db.invitationCode.delete({ where: { id } })
        return NextResponse.json({ ok: true })
      }
      default:
        return NextResponse.json({ error: 'Unknown action' }, { status: 400 })
    }
  } catch (e) {
    console.error('invites error', e)
    return NextResponse.json({ error: 'Operation failed' }, { status: 500 })
  }
}
