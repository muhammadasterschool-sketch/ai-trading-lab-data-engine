// ============================================================
//  AI Trading Lab v4 - Admin password reset tool (zero deps)
//  Works on Windows / Linux / macOS with Bun (bun:sqlite).
//
//  Use when you forgot the admin password or after a fresh
//  install: sets a known password and clears 2FA so the next
//  login shows a fresh QR enrollment.
//
//  Run:  bun scripts/reset-admin.mjs [newPassword]
// ============================================================
import { Database } from 'bun:sqlite'
import { scryptSync, randomBytes } from 'crypto'
import { existsSync } from 'fs'
import { join, dirname } from 'path'

const ADMIN_EMAIL = 'muhammadasterschool@gmail.com'
const DEFAULT_PASSWORD = 'AurumLab2026'

// ---- locate the database (script lives in <root>/scripts) ----
const candidates = [
  process.argv[2],
  join(import.meta.dir, '..', 'db', 'custom.db'),
  join(process.cwd(), 'db', 'custom.db'),
].filter(Boolean)

const dbPath = candidates.find((p) => existsSync(p))
if (!dbPath) {
  console.error('[reset-admin] ERROR: db/custom.db not found (looked in: ' + candidates.join(', ') + ')')
  process.exit(1)
}

// ---- hash in the exact app format: scrypt:<salt-hex>:<hash-hex> ----
function hashPassword(password) {
  const salt = randomBytes(16).toString('hex')
  const hash = scryptSync(password, salt, 64).toString('hex')
  return `scrypt:${salt}:${hash}`
}

const newPassword = String(process.argv[2] || DEFAULT_PASSWORD)
if (newPassword.length < 8) {
  console.error('[reset-admin] ERROR: password must be at least 8 characters')
  process.exit(1)
}

const db = new Database(dbPath)
const row = db
  .query('SELECT id, email, name, role, totpEnabled FROM "User" WHERE email = ?')
  .get(ADMIN_EMAIL)

if (!row) {
  console.error(`[reset-admin] ERROR: no user found with email ${ADMIN_EMAIL}`)
  db.close()
  process.exit(1)
}

db.query('UPDATE "User" SET passwordHash = ?, totpEnabled = 0, totpSecret = NULL, isActive = 1 WHERE email = ?')
  .run(hashPassword(newPassword), ADMIN_EMAIL)
db.close()

console.log('')
console.log('==============================================')
console.log('  ADMIN PASSWORD RESET - OK')
console.log('==============================================')
console.log(`  Name     : ${row.name || 'Muhammad'}`)
console.log(`  Email    : ${ADMIN_EMAIL}`)
console.log(`  Password : ${newPassword}`)
console.log('  2FA      : cleared - next login shows a fresh QR to scan')
console.log('==============================================')
console.log('  Login: Sign-in tab -> Name + Email + Password')
console.log('  Then scan the QR with Google Authenticator,')
console.log('  enter the 6-digit code - done.')
console.log('==============================================')
console.log('')
