import { cookies } from 'next/headers'
import { db } from '@/lib/db'
import { randomToken } from './crypto'

const SESSION_COOKIE = 'atl_session'
const SESSION_HOURS = 24

export type SessionUser = {
  id: string
  email: string
  name: string | null
  role: string
  totpEnabled: boolean
}

/** Create a session. stage: PASSWORD_OK (2FA pending) or FULL */
export async function createSession(userId: string, stage: 'PASSWORD_OK' | 'FULL') {
  const token = randomToken()
  const expiresAt = new Date(Date.now() + SESSION_HOURS * 3600_000)
  await db.session.create({ data: { userId, token, stage, expiresAt } })
  const jar = await cookies()
  jar.set(SESSION_COOKIE, token, {
    httpOnly: true,
    sameSite: 'lax',
    path: '/',
    expires: expiresAt,
  })
  return token
}

/** Read + validate the session from cookies. Returns user + stage, or null. */
export async function getSession(): Promise<{ user: SessionUser; stage: string } | null> {
  try {
    const jar = await cookies()
    const token = jar.get(SESSION_COOKIE)?.value
    if (!token) return null
    const session = await db.session.findUnique({
      where: { token },
      include: { user: true },
    })
    if (!session) return null
    if (session.expiresAt < new Date()) {
      await db.session.delete({ where: { id: session.id } }).catch(() => {})
      return null
    }
    if (!session.user.isActive) return null
    return {
      user: {
        id: session.user.id,
        email: session.user.email,
        name: session.user.name,
        role: session.user.role,
        totpEnabled: session.user.totpEnabled,
      },
      stage: session.stage,
    }
  } catch {
    return null
  }
}

/** Full authenticated user (2FA passed). Null otherwise. */
export async function getAuthUser(): Promise<SessionUser | null> {
  const s = await getSession()
  if (!s || s.stage !== 'FULL') return null
  return s.user
}

export async function upgradeSession() {
  const jar = await cookies()
  const token = jar.get(SESSION_COOKIE)?.value
  if (!token) return
  await db.session.update({ where: { token }, data: { stage: 'FULL' } })
}

export async function destroySession() {
  const jar = await cookies()
  const token = jar.get(SESSION_COOKIE)?.value
  if (token) {
    await db.session.deleteMany({ where: { token } }).catch(() => {})
  }
  jar.delete(SESSION_COOKIE)
}

/** Guard for API routes: returns user or throws a 401-shaped null */
export async function requireAdmin(): Promise<SessionUser | null> {
  const user = await getAuthUser()
  if (!user || user.role !== 'ADMIN') return null
  return user
}
