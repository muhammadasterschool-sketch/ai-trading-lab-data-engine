'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useToast } from '@/hooks/use-toast'
import { FlaskConical, Play } from 'lucide-react'
import {
  ResponsiveContainer, LineChart as RLineChart, Line, XAxis, YAxis, Tooltip as RTooltip, ReferenceLine,
} from 'recharts'

interface Metrics {
  trades: number
  winRate: number
  netReturn: number
  sharpe: number
  sortino: number
  maxDrawdown: number
  profitFactor: number
  totalCosts: number
  expectancy: number
  avgWin: number
  avgLoss: number
}

interface BacktestData {
  runId: string
  durationMs: number
  barsUsed: number
  range: { from: string; to: string }
  metrics: Metrics
  exitReasons: Record<string, number>
  equityCurve: Array<{ ts: number; equity: number }>
  foldStats: { folds: Array<{ fold: number; from: string; to: string; trades: number; netReturn: number; sharpe: number }>; aggregate: Metrics; equityCurve: Array<{ ts: number; equity: number }> } | null
}

export default function BacktestTab() {
  const [strategies, setStrategies] = useState<Array<{ key: string; name: string; params: string }>>([])
  const [strategyKey, setStrategyKey] = useState('ema-crossover')
  const [days, setDays] = useState('30')
  const [costs, setCosts] = useState(true)
  const [wf, setWf] = useState(false)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<BacktestData | null>(null)
  const { toast } = useToast()

  useEffect(() => {
    fetch('/api/strategies')
      .then((r) => r.json())
      .then((d) => setStrategies(d.strategies ?? []))
      .catch(() => {})
  }, [])

  const run = async () => {
    setRunning(true)
    try {
      const strat = strategies.find((s) => s.key === strategyKey)
      const res = await fetch('/api/backtest/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          symbol: 'PAXGUSDT',
          strategyKey,
          params: strat ? JSON.parse(strat.params) : {},
          days: Number(days),
          costs,
          walkForward: wf,
        }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error)
      setResult(data)
    } catch (e) {
      toast({ title: 'Backtest failed', description: e instanceof Error ? e.message : 'error', variant: 'destructive' })
    } finally {
      setRunning(false)
    }
  }

  const curve = (result?.foldStats && wf ? result.foldStats.equityCurve : result?.equityCurve ?? []).map((p) => ({
    ...p,
    label: new Date(p.ts).toISOString().slice(5, 10),
  }))

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <FlaskConical size={18} className="text-amber-500" /> Backtest — Reality Modelling
        </h2>
        <p className="text-xs text-zinc-500 mt-0.5">
          Signals on closed candles, fills at next open · spread + slippage + square-root impact on every fill
        </p>
      </div>

      {/* Controls */}
      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-4 flex flex-wrap items-end gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs text-zinc-400">Strategy</Label>
            <Select value={strategyKey} onValueChange={setStrategyKey}>
              <SelectTrigger className="w-56 bg-zinc-950 border-zinc-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {strategies.map((s) => (
                  <SelectItem key={s.key} value={s.key}>{s.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs text-zinc-400">Period</Label>
            <Select value={days} onValueChange={setDays}>
              <SelectTrigger className="w-36 bg-zinc-950 border-zinc-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="7">Last 7 days</SelectItem>
                <SelectItem value="14">Last 14 days</SelectItem>
                <SelectItem value="30">Last 30 days</SelectItem>
                <SelectItem value="60">Last 60 days</SelectItem>
                <SelectItem value="120">Last 120 days</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2 pb-2">
            <Switch id="costs" checked={costs} onCheckedChange={setCosts} />
            <Label htmlFor="costs" className="text-xs text-zinc-400">Cost models</Label>
          </div>
          <div className="flex items-center gap-2 pb-2">
            <Switch id="wf" checked={wf} onCheckedChange={setWf} />
            <Label htmlFor="wf" className="text-xs text-zinc-400">Walk-forward (5 folds)</Label>
          </div>
          <Button onClick={run} disabled={running} className="bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold ml-auto">
            <Play size={14} className="mr-1.5" /> {running ? 'Running…' : 'Run Backtest'}
          </Button>
        </CardContent>
      </Card>

      {result && (
        <>
          {/* Metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            {[
              { label: 'Net return', value: `${(result.metrics.netReturn * 100).toFixed(2)}%`, color: result.metrics.netReturn >= 0 ? 'text-emerald-400' : 'text-red-400' },
              { label: 'Trades', value: String(result.metrics.trades) },
              { label: 'Win rate', value: `${(result.metrics.winRate * 100).toFixed(1)}%` },
              { label: 'Sharpe', value: String(result.metrics.sharpe), color: result.metrics.sharpe >= 0 ? 'text-emerald-400' : 'text-red-400' },
              { label: 'Max drawdown', value: `${(result.metrics.maxDrawdown * 100).toFixed(1)}%`, color: 'text-red-400' },
              { label: 'Total costs', value: `$${result.metrics.totalCosts.toFixed(0)}`, color: 'text-amber-400' },
            ].map((m) => (
              <Card key={m.label} className="bg-zinc-900/50 border-zinc-800">
                <CardContent className="p-3">
                  <div className="text-[10px] text-zinc-500">{m.label}</div>
                  <div className={`text-lg font-mono font-semibold ${m.color ?? 'text-zinc-200'}`}>{m.value}</div>
                </CardContent>
              </Card>
            ))}
          </div>

          {/* Equity curve */}
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-zinc-300">
                Equity curve {wf ? '(walk-forward out-of-sample concatenated)' : ''} — {result.barsUsed.toLocaleString()} bars
                {' · '}{result.range.from.slice(0, 10)} → {result.range.to.slice(0, 10)}
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <RLineChart data={curve} margin={{ top: 5, right: 10, bottom: 0, left: 0 }}>
                    <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#71717a' }} minTickGap={40} />
                    <YAxis tick={{ fontSize: 10, fill: '#71717a' }} domain={['auto', 'auto']} width={60} />
                    <RTooltip
                      contentStyle={{ background: '#18181b', border: '1px solid #3f3f46', borderRadius: 8, fontSize: 12 }}
                      labelStyle={{ color: '#a1a1aa' }}
                      formatter={(v: number) => [`$${v.toLocaleString()}`, 'Equity']}
                    />
                    <ReferenceLine y={100000} stroke="#52525b" strokeDasharray="4 4" />
                    <Line type="monotone" dataKey="equity" stroke="#f59e0b" strokeWidth={1.5} dot={false} />
                  </RLineChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Fold stats */}
            {result.foldStats && (
              <Card className="bg-zinc-900/50 border-zinc-800">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-zinc-300">Walk-forward folds (out-of-sample)</CardTitle>
                </CardHeader>
                <CardContent>
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-zinc-500 border-b border-zinc-800">
                        <th className="text-left py-1.5">Fold</th>
                        <th className="text-left py-1.5">Period</th>
                        <th className="text-right py-1.5">Trades</th>
                        <th className="text-right py-1.5">Net</th>
                        <th className="text-right py-1.5">Sharpe</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.foldStats.folds.map((f) => (
                        <tr key={f.fold} className="border-b border-zinc-800/50">
                          <td className="py-1.5">{f.fold}</td>
                          <td className="py-1.5 text-zinc-500">{f.from} → {f.to}</td>
                          <td className="py-1.5 text-right font-mono">{f.trades}</td>
                          <td className={`py-1.5 text-right font-mono ${f.netReturn >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {(f.netReturn * 100).toFixed(2)}%
                          </td>
                          <td className={`py-1.5 text-right font-mono ${f.sharpe >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{f.sharpe}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            )}

            {/* Exit reasons */}
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm text-zinc-300">Exit reasons &amp; extra metrics</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="flex flex-wrap gap-2">
                  {Object.entries(result.exitReasons).map(([k, v]) => (
                    <span key={k} className="text-xs bg-zinc-950 border border-zinc-800 rounded-lg px-3 py-1.5">
                      {k}: <span className="font-mono text-amber-400">{v}</span>
                    </span>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs pt-2">
                  <div className="text-zinc-500">Sortino: <span className="font-mono text-zinc-300">{result.metrics.sortino}</span></div>
                  <div className="text-zinc-500">Profit factor: <span className="font-mono text-zinc-300">{result.metrics.profitFactor}</span></div>
                  <div className="text-zinc-500">Expectancy/trade: <span className="font-mono text-zinc-300">${result.metrics.expectancy}</span></div>
                  <div className="text-zinc-500">Avg win / loss: <span className="font-mono text-zinc-300">${result.metrics.avgWin} / ${result.metrics.avgLoss}</span></div>
                  <div className="text-zinc-500">Runtime: <span className="font-mono text-zinc-300">{result.durationMs}ms</span></div>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
