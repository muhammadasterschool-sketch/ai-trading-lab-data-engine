import { PrismaClient } from '@prisma/client'
const db = new PrismaClient()
async function main() {
  const bundles = await db.dataBundle.findMany({ orderBy: [{ symbol: 'asc' }, { period: 'asc' }] })
  for (const b of bundles) console.log(`${b.symbol} ${b.period}: ${b.status} (${b.barCount} bars)`)
  console.log(`TOTAL BARS: ${await db.bar.count()}`)
}
main().finally(() => db.$disconnect())
