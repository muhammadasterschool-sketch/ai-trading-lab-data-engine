'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { Radar, Play, ShieldAlert, CheckCircle2, XCircle, Send } from 'lucide-react'

interface ScanResult {
  strategyKey: string
  params: Record<string, number>
  trades: number
  winRate: number
  sharpe: number
  sortino: number
  maxDrawdown: number
  netReturn: number
  profitFactor: number
  oosSharpe?: number
  oosReturn?: number
  rank?: number
}

interface ScanData {
  scanId: string
  durationMs: number
  trials: number
  noiseBarZ: number
  noiseBarSharpe: number
  sigmaTrials: number
  deflatedSharpe: number
  clearsNoise: boolean
  isBars: number
  oosBars: number
  results: ScanResult[]
}

export default function AutoscanTab() {
  const [days, setDays] = useState('30')
  const [running, setRunning] = useState(false)
  const [scan, setScan] = useState<ScanData | null>(null)
  const { toast } = useToast()

  useEffect(() => {
    fetch('/api/autoscan/latest')
      .then((r) => r.json())
      .then((d) => {
        if (d.scan) {
          // rehydrate latest scan from DB
          setScan({
            scanId: d.scan.id,
            durationMs: 0,
            trials: d.scan.trials,
            noiseBarZ: d.scan.noiseBar,
            noiseBarSharpe: 0,
            sigmaTrials: 0,
            deflatedSharpe: 0,
            clearsNoise: false,
            isBars: 0,
            oosBars: 0,
            results: d.scan.results.map((r: Record<string, unknown>) => ({
              strategyKey: r.strategyKey as string,
              params: JSON.parse(r.params as string),
              trades: r.trades as number,
              winRate: r.winRate as number,
              sharpe: r.sharpe as number,
              sortino: r.sortino as number,
              maxDrawdown: r.maxDrawdown as number,
              netReturn: r.netReturn as number,
              profitFactor: r.profitFactor as number,
              oosSharpe: r.oosSharpe ?? undefined,
              oosReturn: r.oosReturn ?? undefined,
              rank: r.rank ?? undefined,
            })),
          })
        }
      })
      .catch(() => {})
  }, [])

  const runScan = async () => {
    setRunning(true)
    try {
      const res = await fetch('/api/autoscan/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol: 'PAXGUSDT', days: Number(days), strategies: [] }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      setScan(data)
      toast({
        title: `Scan complete — ${data.trials} trials`,
        description: data.clearsNoise ? 'Winner CLEARS the DSR noise bar' : 'Winner does NOT clear the noise bar (likely overfit)',
      })
    } catch (e) {
      toast({ title: 'Scan failed', description: e instanceof Error ? e.message : 'error', variant: 'destructive' })
    } finally {
      setRunning(false)
    }
  }

  const sendToPaper = async (r: ScanResult) => {
    await fetch('/api/approvals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        action: 'create',
        type: 'SCAN_WINNER',
        refKey: r.strategyKey,
        title: `Auto-scan winner: ${r.strategyKey} (Sharpe ${r.sharpe})`,
        evidence: { params: r.params, sharpe: r.sharpe, oosSharpe: r.oosSharpe, trades: r.trades, winRate: r.winRate, netReturn: r.netReturn },
      }),
    })
    toast({ title: 'Sent to approval inbox', description: 'An admin must approve before it can go live on paper.' })
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <Radar size={18} className="text-amber-500" /> Auto-Scan
          </h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            Parameter grid sweep with real cost models · IS/OOS split · DSR noise bar
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger className="w-32 bg-zinc-900 border-zinc-700">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="14">Last 14 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
              <SelectItem value="60">Last 60 days</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={runScan} disabled={running} className="bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold">
            <Play size={14} className="mr-1.5" /> {running ? 'Scanning…' : 'Run Scan'}
          </Button>
        </div>
      </div>

      {scan && (
        <>
          {/* Stats strip */}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-3">
                <div className="text-[10px] text-zinc-500">Trials run</div>
                <div className="text-lg font-mono font-semibold">{scan.trials}</div>
              </CardContent>
            </Card>
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-3">
                <div className="text-[10px] text-zinc-500">DSR noise bar</div>
                <div className="text-lg font-mono font-semibold text-amber-400">{scan.noiseBarZ}σ</div>
              </CardContent>
            </Card>
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-3">
                <div className="text-[10px] text-zinc-500">σ of trial Sharpes</div>
                <div className="text-lg font-mono font-semibold">{scan.sigmaTrials || '—'}</div>
              </CardContent>
            </Card>
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-3">
                <div className="text-[10px] text-zinc-500">Deflated Sharpe</div>
                <div className="text-lg font-mono font-semibold">{scan.deflatedSharpe || '—'}</div>
              </CardContent>
            </Card>
            <Card className={`bg-zinc-900/50 ${scan.clearsNoise ? 'border-emerald-500/40' : 'border-red-500/40'}`}>
              <CardContent className="p-3">
                <div className="text-[10px] text-zinc-500">Clears noise?</div>
                <div className={`text-sm font-semibold flex items-center gap-1 ${scan.clearsNoise ? 'text-emerald-400' : 'text-red-400'}`}>
                  {scan.clearsNoise ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                  {scan.clearsNoise ? 'YES' : 'NO'}
                </div>
              </CardContent>
            </Card>
          </div>

          {!scan.clearsNoise && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-3.5 flex gap-3">
              <ShieldAlert size={18} className="text-amber-400 shrink-0 mt-0.5" />
              <p className="text-xs text-zinc-400 leading-relaxed">
                <span className="text-amber-400 font-medium">Overfitting warning (Bailey &amp; López de Prado 2014):</span>{' '}
                with {scan.trials} trials, pure noise is expected to produce a best Sharpe of {scan.noiseBarZ}σ above the
                cross-trial average. This scan&apos;s winner does <span className="text-red-400 font-medium">not</span> clear
                that bar — treat the leaderboard as a research shortlist, not proof of edge. The honest signal here is
                the OOS column: configurations that also hold up out-of-sample.
              </p>
            </div>
          )}

          {/* Leaderboard */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-zinc-300">Leaderboard (top {scan.results.length}) — ranked by in-sample Sharpe</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full text-xs min-w-[760px]">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="text-left py-2 pr-2">#</th>
                    <th className="text-left py-2 pr-2">Strategy</th>
                    <th className="text-left py-2 pr-2">Params</th>
                    <th className="text-right py-2 pr-2">Trades</th>
                    <th className="text-right py-2 pr-2">Win%</th>
                    <th className="text-right py-2 pr-2">Net</th>
                    <th className="text-right py-2 pr-2">Sharpe</th>
                    <th className="text-right py-2 pr-2">OOS Sharpe</th>
                    <th className="text-right py-2 pr-2">MaxDD</th>
                    <th className="text-right py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {scan.results.map((r, i) => (
                    <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                      <td className="py-2 pr-2 text-zinc-500">{r.rank ?? i + 1}</td>
                      <td className="py-2 pr-2 text-zinc-300">{r.strategyKey}</td>
                      <td className="py-2 pr-2 font-mono text-[10px] text-zinc-500 max-w-56 truncate">
                        {Object.entries(r.params).map(([k, v]) => `${k}=${v}`).join(' ')}
                      </td>
                      <td className="py-2 pr-2 text-right font-mono">{r.trades}</td>
                      <td className="py-2 pr-2 text-right font-mono">{(r.winRate * 100).toFixed(0)}%</td>
                      <td className={`py-2 pr-2 text-right font-mono ${r.netReturn >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {(r.netReturn * 100).toFixed(1)}%
                      </td>
                      <td className="py-2 pr-2 text-right font-mono text-amber-400">{r.sharpe}</td>
                      <td className={`py-2 pr-2 text-right font-mono ${(r.oosSharpe ?? 0) > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {r.oosSharpe?.toFixed(1) ?? '—'}
                      </td>
                      <td className="py-2 pr-2 text-right font-mono text-zinc-400">{(r.maxDrawdown * 100).toFixed(0)}%</td>
                      <td className="py-2 text-right">
                        <Button size="sm" variant="outline" className="h-7 text-[10px] border-zinc-700" onClick={() => sendToPaper(r)}>
                          <Send size={10} className="mr-1" /> Paper
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      )}

      {!scan && !running && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-8 text-center text-sm text-zinc-500">
            Run your first scan — the engine sweeps every strategy&apos;s parameter grid over real gold
            data with full cost modelling, then shows how much of the leaderboard is expected to be noise.
          </CardContent>
        </Card>
      )}
    </div>
  )
}
