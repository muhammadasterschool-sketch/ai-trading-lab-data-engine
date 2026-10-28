import { NextResponse } from 'next/server'
import { db } from '@/lib/db'
import { hashPassword } from '@/lib/auth/crypto'

// Simple in-memory rate limit (per IP): max 5 registration attempts / 15 min
const attempts = new Map<string, { count: number; first: number }>()
const WINDOW_MS = 15 * 60 * 1000
const MAX_ATTEMPTS = 5

function rateLimited(ip: string): boolean {
  const now = Date.now()
  const rec = attempts.get(ip)
  if (!rec || now - rec.first > WINDOW_MS) {
    attempts.set(ip, { count: 1, first: now })
    return false
  }
  rec.count++
  return rec.count > MAX_ATTEMPTS
}

export async function POST(req: Request) {
  try {
    const ip = req.headers.get('x-forwarded-for')?.split(',')[0]?.trim() || 'local'
    if (rateLimited(ip)) {
      return NextResponse.json(
        { error: 'Too many attempts. Try again later.' },
        { status: 429 },
      )
    }

    const { name, email, password, invitationCode } = await req.json()

    // ---- validate invitation code FIRST — no code, no access ----
    const rawCode = String(invitationCode ?? '').trim().toUpperCase()
    if (!rawCode) {
      return NextResponse.json(
        { error: 'Invitation code required. This engine is invite-only.' },
        { status: 403 },
      )
    }
    const invite = await db.invitationCode.findUnique({ where: { code: rawCode } })
    if (!invite || !invite.active) {
      return NextResponse.json(
        { error: 'Invalid or deactivated invitation code' },
        { status: 403 },
      )
    }
    if (invite.maxUses > 0 && invite.uses >= invite.maxUses) {
      return NextResponse.json(
        { error: 'This invitation code has reached its usage limit' },
        { status: 403 },
      )
    }

    // ---- validate fields ----
    const cleanName = String(name ?? '').trim()
    const cleanEmail = String(email ?? '').toLowerCase().trim()
    const pass = String(password ?? '')

    if (cleanName.length < 2 || cleanName.length > 60) {
      return NextResponse.json({ error: 'Enter your full name (2-60 characters)' }, { status: 400 })
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(cleanEmail)) {
      return NextResponse.json({ error: 'Enter a valid email address' }, { status: 400 })
    }
    if (pass.length < 8) {
      return NextResponse.json({ error: 'Password must be at least 8 characters' }, { status: 400 })
    }

    // ---- password strength ----
    if (!/[A-Za-z]/.test(pass) || !/[0-9]/.test(pass)) {
      return NextResponse.json(
        { error: 'Password must contain letters and numbers' },
        { status: 400 },
      )
    }

    const existing = await db.user.findUnique({ where: { email: cleanEmail } })
    if (existing) {
      return NextResponse.json(
        { error: 'An account with this email already exists. Sign in instead.' },
        { status: 409 },
      )
    }

    // Guard against password === email/name triviality
    if (pass.toLowerCase().includes(cleanEmail.split('@')[0])) {
      return NextResponse.json(
        { error: 'Password must not contain your email name' },
        { status: 400 },
      )
    }

    // ---- create user (TRADER role, 2FA enrollment happens on first login) ----
    const user = await db.user.create({
      data: {
        email: cleanEmail,
        name: cleanName,
        passwordHash: hashPassword(pass),
        role: 'TRADER',
      },
    })

    // Paper account for the new user (isolated from admin's account)
    await db.paperAccount.create({
      data: { userId: user.id, name: `${cleanName}'s Paper Account` },
    })

    // ---- consume invitation ----
    await db.invitationCode.update({
      where: { code: rawCode },
      data: { uses: { increment: 1 }, lastUsedAt: new Date() },
    })

    // ---- v5.6: instant ADMIN notification — owner sees EVERY signup first ----
    try {
      await db.adminNotification.create({
        data: {
          kind: 'REGISTER',
          title: `New registration — ${cleanName}`,
          body: `${cleanName} (${cleanEmail}) joined via invitation code ${rawCode}`,
          meta: JSON.stringify({
            email: cleanEmail,
            name: cleanName,
            inviteCode: rawCode,
            role: 'TRADER',
            ip,
          }),
        },
      })
    } catch (notifyErr) {
      console.error('admin notification failed', notifyErr) // never block the signup
    }

    return NextResponse.json({
      ok: true,
      message:
        'Account created. Sign in with your email and password — you will then enroll two-factor authentication (mandatory).',
    })
  } catch (e) {
    console.error('register error', e)
    return NextResponse.json({ error: 'Registration failed' }, { status: 500 })
  }
}

// Health check for the app shell (connection test)
export async function GET() {
  return NextResponse.json({
    ok: true,
    engine: 'ai-trading-lab-data-engine',
    version: '4.0.0',
    inviteOnly: true,
  })
}
