// Verify v4 DB state: invitation codes, users, paper accounts
import { PrismaClient } from '@prisma/client'
const db = new PrismaClient()

async function main() {
  const codes = await db.invitationCode.findMany()
  console.log('INVITATION CODES:')
  codes.forEach((c) => console.log(`  ${c.code} | uses=${c.uses}/${c.maxUses || '∞'} | active=${c.active} | lastUsed=${c.lastUsedAt?.toISOString() ?? 'never'}`))
  const users = await db.user.findMany({ select: { email: true, name: true, role: true, totpEnabled: true } })
  console.log('USERS:')
  users.forEach((u) => console.log(`  ${u.email} (${u.name}) | role=${u.role} | 2fa=${u.totpEnabled}`))
  const accounts = await db.paperAccount.findMany({ include: { user: { select: { email: true } } } })
  console.log('PAPER ACCOUNTS:')
  accounts.forEach((a) => console.log(`  ${a.user.email} → ${a.name} | balance=${a.balance} | autopilot=${a.autopilot}`))
  const engine = await db.engineState.findUnique({ where: { id: 'singleton' } })
  console.log('ENGINE:', engine ? `running=${engine.running} autopilot=${engine.autopilot} kill=${engine.killSwitch}` : 'missing')
}

main().then(() => db.$disconnect())
