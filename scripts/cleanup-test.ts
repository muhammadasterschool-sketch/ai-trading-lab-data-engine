// Clean up v4 test users + reset master invite code
import { PrismaClient } from '@prisma/client'
const db = new PrismaClient()

async function main() {
  // remove test users (cascades: sessions, paper accounts)
  await db.user.deleteMany({ where: { email: { in: ['alitrader@gmail.com', 'bilal.invited@gmail.com'] } } })
  // remove test invitation code
  await db.invitationCode.deleteMany({ where: { code: 'TESTCODE1' } })
  // reset master code usage
  await db.invitationCode.update({ where: { code: 'M2991474' }, data: { uses: 0, lastUsedAt: null } })
  const users = await db.user.findMany({ select: { email: true } })
  console.log('Remaining users:', users.map((u) => u.email))
  const codes = await db.invitationCode.findMany()
  console.log('Codes:', codes.map((c) => `${c.code} uses=${c.uses}`))
}

main().then(() => db.$disconnect())
