import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { verifyPassword, generateTotpSecret, totpUri } from '@/lib/auth/crypto'
import { createSession, getSession } from '@/lib/auth/session'
import QRCode from 'qrcode'

export async function POST(req: Request) {
  try {
    const { email, password, name } = await req.json()
    if (!email || !password || !name) {
      return NextResponse.json({ error: 'Name, email and password are all required' }, { status: 400 })
    }
    const user = await db.user.findUnique({ where: { email: String(email).toLowerCase().trim() } })
    if (!user || !verifyPassword(String(password), user.passwordHash)) {
      return NextResponse.json({ error: 'Invalid email or password' }, { status: 401 })
    }
    // Name must match the account (the name chosen at registration) — case-insensitive
    const givenName = String(name).trim().toLowerCase()
    const storedName = String(user.name ?? '').trim().toLowerCase()
    if (!storedName || givenName !== storedName) {
      return NextResponse.json({ error: 'Name does not match this account — enter the exact name used at registration' }, { status: 401 })
    }
    if (!user.isActive) {
      return NextResponse.json({ error: 'Account deactivated — contact your administrator' }, { status: 403 })
    }

    // Stage 1 passed. 2FA is MANDATORY for every account.
    if (!user.totpEnabled || !user.totpSecret) {
      // First login → enrollment flow: generate secret, return QR
      const secret = user.totpSecret ?? generateTotpSecret()
      await db.user.update({ where: { id: user.id }, data: { totpSecret: secret, totpEnabled: false } })
      const uri = totpUri(user.email, secret)
      const qr = await QRCode.toDataURL(uri, { width: 220, margin: 1 })
      await createSession(user.id, 'PASSWORD_OK')
      return NextResponse.json({
        stage: 'ENROLL_2FA',
        qr,
        secret,
        message: 'Two-factor authentication is required. Scan the QR with Google Authenticator / Authy, then enter the 6-digit code.',
      })
    }

    // Already enrolled → ask for code
    await createSession(user.id, 'PASSWORD_OK')
    return NextResponse.json({ stage: 'VERIFY_2FA', message: 'Enter your 6-digit authenticator code' })
  } catch (e) {
    console.error('login error', e)
    return NextResponse.json({ error: 'Login failed' }, { status: 500 })
  }
}

export async function GET() {
  const s = await getSession()
  if (!s) return NextResponse.json({ authenticated: false })
  return NextResponse.json({
    authenticated: s.stage === 'FULL',
    stage: s.stage,
    user: s.user,
  })
}
