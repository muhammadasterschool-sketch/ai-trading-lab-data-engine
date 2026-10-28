// ============ Seed: admin user + 5 YouTuber strategies + engine state + real data ============
// Run: bun run scripts/seed.ts
import { PrismaClient } from '@prisma/client'
import { hashPassword, generatePassword } from '../src/lib/auth/crypto'
import { STRATEGY_META } from '../src/lib/engine/strategies'
import { recentMonths, recentDays } from '../src/lib/data/binanceVision'
import { ingestMonthly, ingestDaily } from '../src/lib/data/ingest'

const db = new PrismaClient()

const ADMIN_EMAIL = 'muhammadasterschool@gmail.com'
const ADMIN_NAME = 'Muhammad'

async function seedUsers() {
  const existing = await db.user.findUnique({ where: { email: ADMIN_EMAIL } })
  let password: string
  if (existing) {
    password = '(unchanged — user already exists)'
    console.log(`[seed] admin already exists: ${ADMIN_EMAIL}`)
    await db.user.update({ where: { id: existing.id }, data: { name: ADMIN_NAME, role: 'ADMIN', isActive: true } })
  } else {
    password = generatePassword()
    await db.user.create({
      data: {
        email: ADMIN_EMAIL,
        name: ADMIN_NAME,
        passwordHash: hashPassword(password),
        role: 'ADMIN',
      },
    })
    console.log(`[seed] admin created: ${ADMIN_EMAIL}`)
  }
  // demo trader user for user-management demo
  const traderEmail = 'trader@aitradinglab.local'
  const trader = await db.user.findUnique({ where: { email: traderEmail } })
  if (!trader) {
    const tp = generatePassword()
    await db.user.create({
      data: { email: traderEmail, name: 'Demo Trader', passwordHash: hashPassword(tp), role: 'TRADER' },
    })
    console.log(`[seed] demo trader created: ${traderEmail} / ${tp}`)
  }
  return password
}

async function seedStrategies() {
  for (const s of STRATEGY_META) {
    const existing = await db.strategy.findUnique({ where: { key: s.key } })
    const data = {
      name: s.name,
      family: s.family,
      description: s.description,
      youtuberRef: s.youtuberRef,
      params: JSON.stringify(s.defaults),
      paramGrid: JSON.stringify(s.grid),
      status: 'ACTIVE',
    }
    if (existing) {
      await db.strategy.update({ where: { key: s.key }, data })
    } else {
      await db.strategy.create({ data: { key: s.key, ...data } })
    }
  }
  console.log(`[seed] ${STRATEGY_META.length} YouTuber strategies active`)
}

async function seedEngineState() {
  await db.engineState.upsert({
    where: { id: 'singleton' },
    create: { id: 'singleton', running: true, autopilot: false },
    update: {},
  })
  console.log('[seed] engine state: running=true, autopilot=false (safe default)')
}

async function seedPaperAccount() {
  const admin = await db.user.findUnique({ where: { email: ADMIN_EMAIL } })
  if (!admin) return
  const existing = await db.paperAccount.findFirst({ where: { userId: admin.id } })
  if (!existing) {
    await db.paperAccount.create({ data: { userId: admin.id, name: 'Primary Paper Account', symbol: 'PAXGUSDT' } })
    console.log('[seed] paper account created ($100,000)')
  } else {
    console.log('[seed] paper account exists')
  }
}

async function seedData() {
  // Gold (PAXGUSDT): last 4 months + October dailies
  const months = recentMonths(4)
  console.log(`[seed] fetching GOLD (PAXGUSDT) monthly bundles: ${months.map((m) => `${m.year}-${m.month}`).join(', ')}`)
  for (const m of months) {
    const res = await ingestMonthly('PAXGUSDT', m.year, m.month)
    console.log(`  ${res.period}: ${res.status} ${res.bars ? `(${res.bars} bars)` : res.error ?? ''}`)
  }
  const days = recentDays(3)
  console.log(`[seed] fetching GOLD daily bundles (latest ${days[0]} … ${days[days.length - 1]})`)
  for (const d of days) {
    const res = await ingestDaily('PAXGUSDT', d)
    console.log(`  ${d}: ${res.status} ${res.bars ? `(${res.bars} bars)` : res.error ?? ''}`)
  }
  // Bitcoin (BTCUSDT): last 2 months
  const btcMonths = recentMonths(2)
  console.log(`[seed] fetching BTC monthly bundles…`)
  for (const m of btcMonths) {
    const res = await ingestMonthly('BTCUSDT', m.year, m.month)
    console.log(`  ${res.period}: ${res.status} ${res.bars ? `(${res.bars} bars)` : res.error ?? ''}`)
  }
}

async function main() {
  console.log('=== AI Trading Lab — seed started ===')
  const adminPassword = await seedUsers()
  await seedStrategies()
  await seedEngineState()
  await seedPaperAccount()
  await seedData()
  const barCount = await db.bar.count()
  const bundles = await db.dataBundle.count()
  console.log('=== Seed complete ===')
  console.log(`Bundles: ${bundles} | Total bars: ${barCount}`)
  if (adminPassword !== '(unchanged — user already exists)') {
    console.log('\n╔══════════════════════════════════════════════════════════╗')
    console.log(`║ ADMIN LOGIN: ${ADMIN_EMAIL}`)
    console.log(`║ ADMIN PASSWORD: ${adminPassword}`)
    console.log('║ (2FA will be set up on first login — scan the QR code)')
    console.log('╚══════════════════════════════════════════════════════════╝')
  }
}

main()
  .catch((e) => {
    console.error('Seed failed:', e)
    process.exit(1)
  })
  .finally(() => db.$disconnect())
