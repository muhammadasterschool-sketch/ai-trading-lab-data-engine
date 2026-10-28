// Seed invitation codes for AI Trading Lab Data Engine v4
// Usage: bun scripts/seed-invites.ts
import { PrismaClient } from '@prisma/client'

const db = new PrismaClient()

async function main() {
  // Primary master code (user-provided) — unlimited uses
  await db.invitationCode.upsert({
    where: { code: 'M2991474' },
    update: { active: true, label: 'Master invite — Muhammad' },
    create: {
      code: 'M2991474',
      label: 'Master invite — Muhammad',
      maxUses: 0, // 0 = unlimited
      active: true,
      createdBy: 'muhammad',
    },
  })
  const all = await db.invitationCode.findMany()
  console.log('Invitation codes:', all.map((c) => `${c.code} (${c.active ? 'active' : 'off'}, ${c.uses}/${c.maxUses || '∞'} uses)`))
}

main().then(() => db.$disconnect()).catch((e) => {
  console.error(e)
  db.$disconnect()
  process.exit(1)
})
