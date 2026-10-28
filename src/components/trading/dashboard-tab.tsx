'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Progress } from '@/components/ui/progress'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { fmtUsd, fmtPct, fmtPnl, pnlColor, timeAgo, type EngineSocketData } from './types'
import {
  TrendingUp, TrendingDown, Zap, ShieldAlert, Gauge, Activity, Play, Square, AlertTriangle, Radio,
} from 'lucide-react'

interface Props {
  socket: EngineSocketData
  user: { id: string; email: string; name: string | null; role: string }
}

export default function DashboardTab({ socket }: Props) {
  const [engine, setEngine] = useState<{ autopilot: boolean; killSwitch: boolean; running: boolean } | null>(null)
  const [busy, setBusy] = useState(false)

  const loadEngine = async () => {
    const res = await fetch('/api/engine')
    if (res.ok) {
      const data = await res.json()
      setEngine(data.state)
    }
  }
  useEffect(() => {
    loadEngine()
  }, [socket.account?.autopilot])

  const control = async (action: string) => {
    setBusy(true)
    try {
      await fetch('/api/engine', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      })
      await loadEngine()
    } finally {
      setBusy(false)
    }
  }

  const acc = socket.account
  const cons = socket.consensus
  const crash = socket.crash
  const autopilot = engine?.autopilot ?? acc?.autopilot ?? false
  const bullPct = cons?.bullishScore ?? 50

  return (
    <div className="space-y-4 sm:space-y-5">
      {/* Crash banner */}
      {crash && (crash.probability >= 70 || crash.meltUp >= 70) && (
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 p-4 flex items-start gap-3">
          <AlertTriangle className="text-red-400 shrink-0 mt-0.5" size={20} />
          <div className="min-w-0">
            <div className="font-semibold text-red-300">
              Crash protection active — {crash.probability >= crash.meltUp ? `${crash.probability}% crash-down` : `${crash.meltUp}% melt-up`} probability ({crash.severity})
            </div>
            <div className="text-xs text-red-200/70 mt-1">{crash.narrative}</div>
            <div className="text-xs text-red-200/70 mt-1">New orders paused until probability drops below 60%.</div>
          </div>
        </div>
      )}

      {/* Row 1: consensus + burst */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Consensus gauge */}
        <Card className="lg:col-span-2 bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-zinc-300">
              <Gauge size={15} className="text-amber-500" /> Strategy Consensus — GOLD 1m
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="flex justify-between text-xs mb-1.5">
                <span className="text-emerald-400 font-medium flex items-center gap-1">
                  <TrendingUp size={13} /> Bullish {cons ? cons.bullishScore.toFixed(1) : '—'}%
                </span>
                <span className="text-zinc-500">60% threshold to confirm</span>
                <span className="text-red-400 font-medium flex items-center gap-1">
                  Bearish {cons ? cons.bearishScore.toFixed(1) : '—'}% <TrendingDown size={13} />
                </span>
              </div>
              <div className="h-3 rounded-full bg-zinc-800 overflow-hidden flex">
                <div className="bg-gradient-to-r from-emerald-600 to-emerald-400 transition-all duration-700" style={{ width: `${bullPct}%` }} />
                <div className="bg-gradient-to-r from-red-400 to-red-600 transition-all duration-700 flex-1" />
              </div>
              <div className="relative h-4">
                <div className="absolute left-[60%] -translate-x-1/2 text-[10px] text-zinc-500 flex flex-col items-center">
                  <span>▼</span>
                </div>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {cons?.direction === 'BULLISH' && <Badge className="bg-emerald-500/15 text-emerald-400 border-emerald-500/30">BULLISH consensus {cons.bullishScore.toFixed(0)}%</Badge>}
              {cons?.direction === 'BEARISH' && <Badge className="bg-red-500/15 text-red-400 border-red-500/30">BEARISH consensus {cons.bearishScore.toFixed(0)}%</Badge>}
              {(!cons || cons.direction === 'NEUTRAL') && <Badge variant="outline" className="text-zinc-400 border-zinc-700">No consensus yet</Badge>}
              {cons?.burst?.status && <span className="text-xs text-zinc-500">{cons.burst.status}</span>}
            </div>
            {/* strategy votes */}
            <div className="space-y-1.5 max-h-44 overflow-y-auto pr-1">
              {(cons?.votes ?? []).map((v) => (
                <div key={v.key} className="flex items-center gap-2 text-xs bg-zinc-950/60 rounded-lg px-3 py-2 border border-zinc-800/60">
                  <span className={v.dir === 1 ? 'text-emerald-400' : 'text-red-400'}>{v.dir === 1 ? '▲ LONG' : '▼ SHORT'}</span>
                  <span className="text-zinc-300 font-medium truncate">{v.name}</span>
                  <span className="ml-auto text-amber-400 font-mono">{v.conf.toFixed(0)}%</span>
                </div>
              ))}
              {(!cons || cons.votes.length === 0) && (
                <div className="text-xs text-zinc-600 text-center py-3">Waiting for strategy votes on next candle close…</div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Burst mode + engine control */}
        <Card className={`bg-zinc-900/50 ${acc?.burst.active ? 'border-amber-500/50' : 'border-zinc-800'}`}>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-zinc-300">
              <Zap size={15} className={acc?.burst.active ? 'text-amber-400 animate-pulse' : 'text-zinc-500'} />
              Burst Mode — 1 trade / sec
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2">
              {acc?.burst.active ? (
                <Badge className="bg-amber-500/15 text-amber-400 border-amber-500/40 animate-pulse">ACTIVE — {acc.burst.direction}</Badge>
              ) : (
                <Badge variant="outline" className="text-zinc-500 border-zinc-700">STANDBY</Badge>
              )}
              {acc?.burst.seq ? <span className="text-xs text-zinc-500 font-mono">#{acc.burst.seq}</span> : null}
            </div>
            <p className="text-[11px] text-zinc-500 leading-relaxed">
              When ≥2 strategies reach 60% weighted consensus and a confirmation candle closes in that
              direction, the engine starts placing one paper trade per second with hard risk caps.
            </p>
            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={busy || autopilot}
                onClick={() => control('autopilot-on')}
                className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white"
              >
                <Play size={14} className="mr-1" /> Start Autopilot
              </Button>
              <Button
                size="sm"
                disabled={busy || !autopilot}
                onClick={() => control('autopilot-off')}
                variant="destructive"
                className="flex-1"
              >
                <Square size={14} className="mr-1" /> Stop
              </Button>
            </div>
            {engine?.killSwitch && (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => control('release-kill')} className="w-full border-red-500/40 text-red-300">
                Kill switch engaged — click to release
              </Button>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Row 2: account + prices + stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-[11px] text-zinc-500">Equity (paper)</div>
            <div className="text-xl font-mono font-semibold text-amber-400">{fmtUsd(acc?.equity, 2)}</div>
            <div className={`text-xs ${pnlColor(acc?.dayPnlPct)}`}>Today {fmtPct(acc?.dayPnlPct)}</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-[11px] text-zinc-500">Drawdown vs HWM</div>
            <div className="text-xl font-mono font-semibold">{fmtPct(acc?.drawdownPct).replace('+', '')}</div>
            <Progress value={Math.min(100, ((acc?.drawdownPct ?? 0) / (acc?.maxDrawdownPct ?? 10)) * 100)} className="h-1.5 mt-2 bg-zinc-800" />
            <div className="text-[10px] text-zinc-600 mt-1">limit {acc?.maxDrawdownPct ?? 10}% · daily {acc?.dailyLossLimitPct ?? 5}%</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-[11px] text-zinc-500">Open Positions</div>
            <div className="text-xl font-mono font-semibold">{acc?.openPositions.length ?? 0}</div>
            <div className="text-[10px] text-zinc-600">
              {acc?.openPositions.filter((p) => p.mode === 'BURST').length ?? 0} burst · {socket.stats?.burstTrades ?? 0} burst fills total
            </div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-4">
            <div className="text-[11px] text-zinc-500">Engine Uptime</div>
            <div className="text-xl font-mono font-semibold">
              {socket.stats ? `${Math.floor((socket.stats.uptimeSec ?? 0) / 60)}m ${String((socket.stats.uptimeSec ?? 0) % 60).padStart(2, '0')}s` : '—'}
            </div>
            <div className="text-[10px] text-zinc-600">{socket.stats?.ticks.toLocaleString() ?? 0} ticks · {socket.stats?.bars ?? 0} bars</div>
          </CardContent>
        </Card>
      </div>

      {/* Row 3: open positions + live feed */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-zinc-300">
              <Activity size={15} className="text-amber-500" /> Open Positions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-72 overflow-y-auto space-y-2">
              {(acc?.openPositions ?? []).map((p) => (
                <div key={p.id} className="flex items-center gap-2 text-xs bg-zinc-950/60 rounded-lg px-3 py-2.5 border border-zinc-800/60">
                  <Badge variant="outline" className={p.side === 'LONG' ? 'text-emerald-400 border-emerald-500/40' : 'text-red-400 border-red-500/40'}>{p.side}</Badge>
                  <span className="font-mono text-zinc-400">{p.qty.toFixed(3)} @ {p.entryPrice.toFixed(2)}</span>
                  {p.mode === 'BURST' && <Zap size={11} className="text-amber-400" />}
                  <span className={`ml-auto font-mono ${pnlColor(p.unrealized)}`}>{fmtPnl(p.unrealized)}</span>
                  {p.closeIn !== null && p.closeIn !== undefined && <span className="text-[10px] text-zinc-600">{p.closeIn}s</span>}
                </div>
              ))}
              {(!acc || acc.openPositions.length === 0) && (
                <div className="text-xs text-zinc-600 text-center py-8">No open positions — autopilot {autopilot ? 'running' : 'paused'}</div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-zinc-300">
              <Radio size={15} className={socket.connected ? 'text-emerald-400 animate-pulse' : 'text-zinc-500'} /> Live Feed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-72 overflow-y-auto space-y-1.5">
              {socket.feed.map((f, i) => (
                <div key={`${f.ts}-${i}`} className={`text-[11px] font-mono px-2.5 py-1.5 rounded border ${
                  f.kind === 'crash' ? 'bg-red-500/10 border-red-500/30 text-red-300'
                  : f.kind === 'burst' ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
                  : f.kind === 'close' ? 'bg-zinc-900 border-zinc-800 text-zinc-400'
                  : f.kind === 'reject' ? 'bg-zinc-900 border-zinc-800 text-zinc-500'
                  : 'bg-zinc-900 border-zinc-800 text-zinc-300'
                }`}>
                  <span className="text-zinc-600 mr-2">{new Date(f.ts).toISOString().slice(11, 19)}</span>
                  {f.text}
                </div>
              ))}
              {socket.feed.length === 0 && (
                <div className="text-xs text-zinc-600 text-center py-8">
                  {socket.connected ? 'Connected — waiting for market events…' : 'Connecting to engine…'}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Crash indicator */}
      {crash && (
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm flex items-center gap-2 text-zinc-300">
              <ShieldAlert size={15} className={crash.severity === 'LOW' ? 'text-zinc-500' : crash.severity === 'MEDIUM' ? 'text-amber-500' : 'text-red-400'} />
              Crash Radar
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div>
                <div className="text-zinc-500 text-[10px]">Crash-down probability</div>
                <div className="font-mono text-lg text-red-400">{crash.probability}%</div>
              </div>
              <div>
                <div className="text-zinc-500 text-[10px]">Melt-up probability</div>
                <div className="font-mono text-lg text-emerald-400">{crash.meltUp}%</div>
              </div>
              <div>
                <div className="text-zinc-500 text-[10px]">Volatility z-score</div>
                <div className="font-mono text-lg">{crash.indicators.volZ?.toFixed(1) ?? '—'}</div>
              </div>
              <div>
                <div className="text-zinc-500 text-[10px]">ATR regime ratio</div>
                <div className="font-mono text-lg">{crash.indicators.atrRatio?.toFixed(2) ?? '—'}</div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
