'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { useToast } from '@/hooks/use-toast'
import { Database, Download, ShieldCheck, ExternalLink } from 'lucide-react'

interface Bundle {
  id: string
  symbol: string
  period: string
  source: string
  sourceUrl: string
  startDate: string
  endDate: string
  barCount: number
  gaps: number
  duplicates: number
  outliers: number
  quality: string
  status: string
  provenance: { repository?: string; sha256?: string; fetchedAt?: string; note?: string }
}

export default function DataTab() {
  const [bundles, setBundles] = useState<Bundle[]>([])
  const [totalBars, setTotalBars] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const { toast } = useToast()

  const load = async () => {
    const res = await fetch('/api/data/bundles')
    if (res.ok) {
      const d = await res.json()
      setBundles(d.bundles)
      setTotalBars(d.totalBars)
    }
  }
  useEffect(() => {
    load()
  }, [])

  const fetchMore = async (symbol: string, months: number, days: number) => {
    setBusy(symbol)
    try {
      const res = await fetch('/api/data/fetch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, months, days }),
      })
      const d = await res.json()
      if (!res.ok) throw new Error(d.error)
      toast({
        title: `${symbol}: ${d.fetched.toLocaleString()} new bars ingested`,
        description: `${d.results.filter((r: { status: string }) => r.status === 'READY').length} bundles READY`,
      })
      load()
    } catch (e) {
      toast({ title: 'Fetch failed', description: e instanceof Error ? e.message : 'error', variant: 'destructive' })
    } finally {
      setBusy(null)
    }
  }

  const gold = bundles.filter((b) => b.symbol === 'PAXGUSDT')
  const btc = bundles.filter((b) => b.symbol === 'BTCUSDT')
  const goldBars = gold.reduce((s, b) => s + b.barCount, 0)
  const btcBars = btc.reduce((s, b) => s + b.barCount, 0)

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Database size={18} className="text-amber-500" /> Market Data — Real &amp; Verified
        </h2>
        <p className="text-xs text-zinc-500 mt-0.5">
          1-minute bars from the Binance Vision public data repository (checksummed dumps). Gold = PAXG
          (Paxos Gold, 1:1 physical-gold backed — tracks spot XAUUSD). Every bundle carries full provenance.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="text-[10px] text-zinc-500">Total 1m bars</div>
            <div className="text-lg font-mono font-semibold text-amber-400">{totalBars.toLocaleString()}</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="text-[10px] text-zinc-500">Gold (PAXG) bars</div>
            <div className="text-lg font-mono font-semibold">{goldBars.toLocaleString()}</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="text-[10px] text-zinc-500">BTC bars</div>
            <div className="text-lg font-mono font-semibold">{btcBars.toLocaleString()}</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="text-[10px] text-zinc-500">Bundles</div>
            <div className="text-lg font-mono font-semibold">{bundles.length}</div>
          </CardContent>
        </Card>
      </div>

      <div className="flex flex-wrap gap-2">
        <Button size="sm" disabled={busy !== null} onClick={() => fetchMore('PAXGUSDT', 0, 3)} className="bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold">
          <Download size={13} className="mr-1.5" /> {busy === 'PAXGUSDT' ? 'Fetching…' : 'Fetch gold — last 3 days'}
        </Button>
        <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => fetchMore('PAXGUSDT', 1, 0)} className="border-zinc-700">
          <Download size={13} className="mr-1.5" /> Fetch gold — 1 more month
        </Button>
        <Button size="sm" variant="outline" disabled={busy !== null} onClick={() => fetchMore('BTCUSDT', 0, 3)} className="border-zinc-700">
          <Download size={13} className="mr-1.5" /> Fetch BTC — last 3 days
        </Button>
      </div>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
            <ShieldCheck size={14} className="text-emerald-400" /> Bundles &amp; provenance
          </CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-xs min-w-[820px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-2 pr-2">Symbol</th>
                <th className="text-left py-2 pr-2">Period</th>
                <th className="text-left py-2 pr-2">Range (UTC)</th>
                <th className="text-right py-2 pr-2">Bars</th>
                <th className="text-right py-2 pr-2">Gaps</th>
                <th className="text-right py-2 pr-2">Outliers</th>
                <th className="text-left py-2 pr-2">Quality</th>
                <th className="text-left py-2 pr-2">SHA-256</th>
                <th className="text-left py-2">Source</th>
              </tr>
            </thead>
            <tbody>
              {bundles.map((b) => (
                <tr key={b.id} className="border-b border-zinc-800/50">
                  <td className="py-2 pr-2">
                    <span className={b.symbol === 'PAXGUSDT' ? 'text-amber-400' : 'text-zinc-300'}>{b.symbol === 'PAXGUSDT' ? 'GOLD' : 'BTC'}</span>
                  </td>
                  <td className="py-2 pr-2 font-mono text-zinc-400">{b.period}</td>
                  <td className="py-2 pr-2 text-zinc-500 font-mono text-[10px]">
                    {b.startDate.slice(0, 10)} → {b.endDate.slice(0, 10)}
                  </td>
                  <td className="py-2 pr-2 text-right font-mono">{b.barCount.toLocaleString()}</td>
                  <td className="py-2 pr-2 text-right font-mono text-zinc-500">{b.gaps}</td>
                  <td className="py-2 pr-2 text-right font-mono text-zinc-500">{b.outliers}</td>
                  <td className="py-2 pr-2">
                    <Badge variant="outline" className={b.quality === 'PASSED' ? 'border-emerald-500/40 text-emerald-400' : 'border-amber-500/40 text-amber-400'}>
                      {b.quality}
                    </Badge>
                  </td>
                  <td className="py-2 pr-2 font-mono text-[10px] text-zinc-600">{b.provenance?.sha256?.slice(0, 10) ?? '—'}…</td>
                  <td className="py-2">
                    <a href={b.sourceUrl} target="_blank" rel="noreferrer" className="text-amber-500/80 hover:text-amber-400 inline-flex items-center gap-1">
                      repo <ExternalLink size={10} />
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-4 text-[11px] text-zinc-500 leading-relaxed space-y-2">
          <p><span className="text-zinc-300 font-medium">Quality gates</span> — every bundle passes duplicate detection, timestamp monotonicity, OHLC sanity and outlier screening before admission. Gaps are counted and displayed, never hidden.</p>
          <p><span className="text-zinc-300 font-medium">Point-in-time honesty</span> — each bundle stores its source URL, SHA-256 checksum, byte size and retrieval time, so any backtest can be reproduced from the exact same bytes.</p>
          <p><span className="text-zinc-300 font-medium">Live feed</span> — the paper-trading engine streams real-time prices from OKX public market data (PAXG-USDT / BTC-USDT tickers) and builds live 1-minute candles, which are appended to the &ldquo;okx-live&rdquo; bundle for future research.</p>
        </CardContent>
      </Card>
    </div>
  )
}
