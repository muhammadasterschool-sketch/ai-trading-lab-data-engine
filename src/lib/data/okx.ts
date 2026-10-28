// ============ OKX public market data (live feed, no API key) ============
// Used for real-time paper trading: PAXG-USDT (physical-gold-backed token =
// live gold price) and BTC-USDT. Public endpoints, generous rate limits.

export interface OkxTicker {
  instId: string
  last: number
  askPx: number
  bidPx: number
  open24h: number
  high24h: number
  low24h: number
  vol24h: number
  ts: number
}

export interface OkxCandle {
  ts: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  confirmed: boolean
}

export async function fetchTicker(instId: string): Promise<OkxTicker | null> {
  try {
    const res = await fetch(`https://www.okx.com/api/v5/market/ticker?instId=${instId}`, {
      signal: AbortSignal.timeout(8000),
      headers: { 'User-Agent': 'ai-trading-lab/1.0' },
    })
    if (!res.ok) return null
    const json = (await res.json()) as { code: string; data?: Array<Record<string, string>> }
    if (json.code !== '0' || !json.data?.length) return null
    const d = json.data[0]
    return {
      instId,
      last: Number(d.last),
      askPx: Number(d.askPx),
      bidPx: Number(d.bidPx),
      open24h: Number(d.open24h),
      high24h: Number(d.high24h),
      low24h: Number(d.low24h),
      vol24h: Number(d.vol24h),
      ts: Number(d.ts),
    }
  } catch {
    return null
  }
}

export async function fetchCandles(instId: string, bar = '1m', limit = 5): Promise<OkxCandle[]> {
  try {
    const res = await fetch(
      `https://www.okx.com/api/v5/market/candles?instId=${instId}&bar=${bar}&limit=${limit}`,
      { signal: AbortSignal.timeout(8000), headers: { 'User-Agent': 'ai-trading-lab/1.0' } }
    )
    if (!res.ok) return []
    const json = (await res.json()) as { code: string; data?: string[][] }
    if (json.code !== '0' || !json.data) return []
    // newest first → reverse to oldest first
    return json.data
      .map((d) => ({
        ts: Number(d[0]),
        open: Number(d[1]),
        high: Number(d[2]),
        low: Number(d[3]),
        close: Number(d[4]),
        volume: Number(d[5]),
        confirmed: d[8] === '1',
      }))
      .reverse()
  } catch {
    return []
  }
}
