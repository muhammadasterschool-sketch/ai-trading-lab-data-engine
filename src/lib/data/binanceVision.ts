import crypto from 'crypto'
import { unzipSync, strFromU8 } from 'fflate'

// ============ Binance Vision public data repository fetcher ============
// data.binance.vision is Binance's official historical data repository
// (S3-hosted, checksummed zip/CSV dumps). This gives us REAL, verified
// 1-minute market data with full provenance — no API key, no rate limits.
//
// PAXGUSDT = Paxos Gold — each token is backed 1:1 by a physical London
// Good Delivery gold bar, so its price tracks spot gold (XAUUSD) tightly.

export const SYMBOLS = {
  PAXGUSDT: { okx: 'PAXG-USDT', label: 'GOLD (PAXG)', advUnits: 8000 },
  BTCUSDT: { okx: 'BTC-USDT', label: 'BITCOIN', advUnits: 1200 },
} as const

export type VisionSymbol = keyof typeof SYMBOLS

export function monthlyUrl(symbol: string, year: number, month: number): string {
  const mm = String(month).padStart(2, '0')
  return `https://data.binance.vision/data/spot/monthly/klines/${symbol}/1m/${symbol}-1m-${year}-${mm}.zip`
}

export function dailyUrl(symbol: string, date: string): string {
  // date = YYYY-MM-DD
  return `https://data.binance.vision/data/spot/daily/klines/${symbol}/1m/${symbol}-1m-${date}.zip`
}

export interface ParsedBar {
  ts: number // epoch ms
  open: number
  high: number
  low: number
  close: number
  volume: number
}

/** Normalize timestamp: recent dumps use microseconds, older use milliseconds. */
function normalizeTs(raw: string | number): number {
  const n = typeof raw === 'string' ? Number(raw) : raw
  if (!isFinite(n) || n <= 0) return 0
  if (n > 1e14) return Math.round(n / 1000) // microseconds → ms
  if (n > 1e11) return Math.round(n) // already ms
  return Math.round(n * 1000) // seconds → ms
}

export function parseKlinesCsv(csv: string): ParsedBar[] {
  const lines = csv.split('\n').map((l) => l.trim()).filter((l) => l.length > 0 && !l.startsWith('open_time'))
  const bars: ParsedBar[] = []
  for (const line of lines) {
    const cols = line.split(',')
    if (cols.length < 6) continue
    const ts = normalizeTs(cols[0])
    const open = Number(cols[1])
    const high = Number(cols[2])
    const low = Number(cols[3])
    const close = Number(cols[4])
    const volume = Number(cols[5])
    if (!ts || !isFinite(open) || !isFinite(high) || !isFinite(low) || !isFinite(close)) continue
    if (open <= 0 || high <= 0 || low <= 0 || close <= 0) continue
    bars.push({ ts, open, high, low, close, volume: isFinite(volume) ? volume : 0 })
  }
  return bars
}

export interface QualityReport {
  bars: ParsedBar[]
  duplicates: number
  gaps: number
  outliers: number
  nonMonotone: number
  passed: boolean
}

/** Quality gates: monotone timestamps, duplicate & outlier screening, gap census. */
export function qualityGate(bars: ParsedBar[]): QualityReport {
  const seen = new Set<number>()
  const clean: ParsedBar[] = []
  let duplicates = 0
  let outliers = 0
  let nonMonotone = 0
  let prevTs = 0

  for (const b of bars) {
    if (b.ts <= prevTs) {
      nonMonotone++
      continue
    }
    if (seen.has(b.ts)) {
      duplicates++
      continue
    }
    // OHLC sanity: high >= max(o,c), low <= min(o,c), prices within 50% of neighbours
    const maxOC = Math.max(b.open, b.close)
    const minOC = Math.min(b.open, b.close)
    const badOhlc = b.high < maxOC * 0.999 || b.low > minOC * 1.001
    if (badOhlc) {
      outliers++
      continue
    }
    if (clean.length > 0) {
      const ref = clean[clean.length - 1].close
      if (Math.abs(b.close - ref) / ref > 0.5) {
        outliers++
        continue
      }
    }
    seen.add(b.ts)
    clean.push(b)
    prevTs = b.ts
  }

  // gap census (expect 60_000 ms spacing)
  let gaps = 0
  for (let i = 1; i < clean.length; i++) {
    const diff = clean[i].ts - clean[i - 1].ts
    if (diff > 60_000) gaps += Math.floor(diff / 60_000) - 1
  }

  return {
    bars: clean,
    duplicates,
    gaps,
    outliers,
    nonMonotone,
    passed: true,
  }
}

export async function fetchZipCsv(url: string): Promise<{ csv: string; sha256: string; bytes: number }> {
  const res = await fetch(url, { signal: AbortSignal.timeout(60_000) })
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`)
  const buf = Buffer.from(await res.arrayBuffer())
  const sha256 = crypto.createHash('sha256').update(buf).digest('hex')
  // standard PKZIP → pure-JS unzip (works in Node and Bun)
  const csv = unzipToCsv(buf)
  return { csv, sha256, bytes: buf.length }
}

function unzipToCsv(buf: Buffer): string {
  const files = unzipSync(new Uint8Array(buf))
  const entry = Object.keys(files).find((f) => f.toLowerCase().endsWith('.csv'))
  if (!entry) throw new Error('no csv in archive')
  return strFromU8(files[entry])
}

/** List last N months (YYYY-MM) before a given date (inclusive). */
export function recentMonths(count: number, ref = new Date()): Array<{ year: number; month: number }> {
  const out: Array<{ year: number; month: number }> = []
  const d = new Date(Date.UTC(ref.getUTCFullYear(), ref.getUTCMonth(), 1))
  for (let i = 0; i < count; i++) {
    out.push({ year: d.getUTCFullYear(), month: d.getUTCMonth() + 1 })
    d.setUTCMonth(d.getUTCMonth() - 1)
  }
  return out.reverse()
}

/** List daily date strings from a start date up to yesterday. */
export function recentDays(count: number, ref = new Date()): string[] {
  const out: string[] = []
  const d = new Date(Date.UTC(ref.getUTCFullYear(), ref.getUTCMonth(), ref.getUTCDate()))
  d.setUTCDate(d.getUTCDate() - 1) // yesterday latest (today may be incomplete)
  for (let i = 0; i < count; i++) {
    out.push(d.toISOString().slice(0, 10))
    d.setUTCDate(d.getUTCDate() - 1)
  }
  return out.reverse()
}
