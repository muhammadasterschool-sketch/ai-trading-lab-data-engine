// Backfill October 2026 daily bars (monthly zip not published yet for current month)
import { PrismaClient } from '@prisma/client'
import { ingestDaily } from '../src/lib/data/ingest'

const db = new PrismaClient()

async function main() {
  const symbols = ['PAXGUSDT', 'BTCUSDT']
  for (const symbol of symbols) {
    for (let d = 1; d <= 27; d++) {
      const date = `2026-10-${String(d).padStart(2, '0')}`
      const res = await ingestDaily(symbol, date)
      console.log(`${symbol} ${date}: ${res.status} ${res.bars ? `(${res.bars} bars)` : res.error ?? ''}`)
    }
  }
  const total = await db.bar.count()
  console.log(`Total bars now: ${total}`)
}

main()
  .catch((e) => {
    console.error(e)
    process.exit(1)
  })
  .finally(() => db.$disconnect())
