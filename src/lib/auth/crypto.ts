import crypto from 'crypto'

// ============ Password hashing (scrypt — no external deps) ============

export function hashPassword(password: string): string {
  const salt = crypto.randomBytes(16).toString('hex')
  const hash = crypto.scryptSync(password, salt, 64).toString('hex')
  return `scrypt:${salt}:${hash}`
}

export function verifyPassword(password: string, stored: string): boolean {
  try {
    const [scheme, salt, hash] = stored.split(':')
    if (scheme !== 'scrypt' || !salt || !hash) return false
    const candidate = crypto.scryptSync(password, salt, 64)
    const expected = Buffer.from(hash, 'hex')
    if (candidate.length !== expected.length) return false
    return crypto.timingSafeEqual(candidate, expected)
  } catch {
    return false
  }
}

// ============ Random tokens ============

export function randomToken(bytes = 32): string {
  return crypto.randomBytes(bytes).toString('hex')
}

export function generatePassword(): string {
  const upper = 'ABCDEFGHJKLMNPQRSTUVWXYZ'
  const lower = 'abcdefghijkmnopqrstuvwxyz'
  const digits = '23456789'
  const special = '!@#$%&*'
  const all = upper + lower + digits + special
  const pick = (set: string) => set[crypto.randomInt(set.length)]
  // guarantee one of each class + 12 random
  const base = [pick(upper), pick(lower), pick(digits), pick(special)]
  for (let i = 0; i < 12; i++) base.push(pick(all))
  // shuffle
  for (let i = base.length - 1; i > 0; i--) {
    const j = crypto.randomInt(i + 1)
    ;[base[i], base[j]] = [base[j], base[i]]
  }
  return base.join('')
}

// ============ Base32 (RFC 4648, for TOTP secrets) ============

const B32_ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'

export function base32Encode(buf: Buffer): string {
  let bits = 0
  let value = 0
  let output = ''
  for (const byte of buf) {
    value = (value << 8) | byte
    bits += 8
    while (bits >= 5) {
      output += B32_ALPHABET[(value >>> (bits - 5)) & 31]
      bits -= 5
    }
  }
  if (bits > 0) output += B32_ALPHABET[(value << (5 - bits)) & 31]
  return output
}

export function base32Decode(str: string): Buffer {
  const clean = str.toUpperCase().replace(/=+$/, '').replace(/\s/g, '')
  let bits = 0
  let value = 0
  const bytes: number[] = []
  for (const ch of clean) {
    const idx = B32_ALPHABET.indexOf(ch)
    if (idx === -1) continue
    value = (value << 5) | idx
    bits += 5
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 0xff)
      bits -= 8
    }
  }
  return Buffer.from(bytes)
}

// ============ TOTP (RFC 6238) — Google Authenticator compatible ============

export function generateTotpSecret(): string {
  // 20 bytes = 160 bits, standard for authenticator apps
  return base32Encode(crypto.randomBytes(20))
}

function hotp(secret: Buffer, counter: number): string {
  const buf = Buffer.alloc(8)
  buf.writeUInt32BE(Math.floor(counter / 2 ** 32), 0)
  buf.writeUInt32BE(counter % 2 ** 32, 4)
  const hmac = crypto.createHmac('sha1', secret).update(buf).digest()
  const offset = hmac[hmac.length - 1] & 0x0f
  const code =
    ((hmac[offset] & 0x7f) << 24) |
    ((hmac[offset + 1] & 0xff) << 16) |
    ((hmac[offset + 2] & 0xff) << 8) |
    (hmac[offset + 3] & 0xff)
  return (code % 1_000_000).toString().padStart(6, '0')
}

/** Verify a 6-digit TOTP code with ±1 step (30s) tolerance. */
export function verifyTotp(secretBase32: string, code: string, window = 1): boolean {
  const clean = (code || '').replace(/\D/g, '')
  if (clean.length !== 6) return false
  const secret = base32Decode(secretBase32)
  if (secret.length === 0) return false
  const step = Math.floor(Date.now() / 1000 / 30)
  for (let i = -window; i <= window; i++) {
    const expected = hotp(secret, step + i)
    if (crypto.timingSafeEqual(Buffer.from(expected), Buffer.from(clean))) return true
  }
  return false
}

/** otpauth:// URI for QR enrollment */
export function totpUri(email: string, secret: string, issuer = 'AI Trading Lab'): string {
  return `otpauth://totp/${encodeURIComponent(issuer)}:${encodeURIComponent(email)}?secret=${secret}&issuer=${encodeURIComponent(issuer)}&algorithm=SHA1&digits=6&period=30`
}
