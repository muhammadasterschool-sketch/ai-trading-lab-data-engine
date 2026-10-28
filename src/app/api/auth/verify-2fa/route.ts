import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { verifyTotp } from '@/lib/auth/crypto'
import { getSession, upgradeSession } from '@/lib/auth/session'

export async function POST(req: Request) {
  try {
    const { code } = await req.json()
    const s = await getSession()
    if (!s || s.stage !== 'PASSWORD_OK') {
      return NextResponse.json({ error: 'Login session missing — start again' }, { status: 401 })
    }
    const user = await db.user.findUnique({ where: { id: s.user.id } })
    if (!user || !user.totpSecret) {
      return NextResponse.json({ error: 'No 2FA secret found — restart login' }, { status: 400 })
    }
    if (!verifyTotp(user.totpSecret, String(code ?? ''))) {
      return NextResponse.json({ error: 'Invalid or expired code — try the current one' }, { status: 401 })
    }
    // success — activate 2FA if enrolling, upgrade session to FULL
    if (!user.totpEnabled) {
      await db.user.update({ where: { id: user.id }, data: { totpEnabled: true, lastLoginAt: new Date() } })
    } else {
      await db.user.update({ where: { id: user.id }, data: { lastLoginAt: new Date() } })
    }
    await upgradeSession()
    return NextResponse.json({ ok: true, user: { id: user.id, email: user.email, name: user.name, role: user.role } })
  } catch (e) {
    console.error('verify-2fa error', e)
    return NextResponse.json({ error: 'Verification failed' }, { status: 500 })
  }
}
