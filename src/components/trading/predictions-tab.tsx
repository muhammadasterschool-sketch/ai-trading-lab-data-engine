'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { fmtUsd, timeAgo, type EngineSocketData } from './types'
import { Brain, TrendingUp, TrendingDown, ShieldAlert, CheckCircle2, XCircle } from 'lucide-react'

interface Prediction {
  id: string
  ts: string
  direction: string
  confidence: number
  refPrice: number
  resolvedAt: string | null
  actualPrice: number | null
  correct: boolean | null
  features: string
}

interface CrashAlertRow {
  id: string
  ts: string
  probability: number
  severity: string
  direction: string
  indicators: string
  actionTaken: string | null
}

export default function PredictionsTab({ socket }: { socket: EngineSocketData }) {
  const [predictions, setPredictions] = useState<Prediction[]>([])
  const [alerts, setAlerts] = useState<CrashAlertRow[]>([])
  const [stats, setStats] = useState<{ total: number; resolved: number; accuracy: number | null; recentAccuracy: number | null } | null>(null)

  const load = async () => {
    const res = await fetch('/api/predictions')
    if (res.ok) {
      const d = await res.json()
      setPredictions(d.predictions)
      setAlerts(d.crashAlerts)
      setStats(d.stats)
    }
  }
  useEffect(() => {
    const t0 = setTimeout(load, 0)
    const t = setInterval(load, 20000)
    return () => {
      clearTimeout(t0)
      clearInterval(t)
    }
  }, [])

  const latest = predictions[0]
  const crash = socket.crash

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Brain size={18} className="text-amber-500" /> Predictions — Crash Radar &amp; Next Move
        </h2>
        <p className="text-xs text-zinc-500 mt-0.5">
          Lightweight ensemble (momentum + reversion + trend structure) forecasting the next 5 minutes, plus
          volatility-regime crash detection. Every forecast is scored and logged.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Current forecast */}
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-zinc-300">Next-move forecast (5-minute horizon)</CardTitle>
          </CardHeader>
          <CardContent>
            {latest ? (
              <div className="space-y-3">
                <div className="flex items-center gap-4">
                  <div className={`w-14 h-14 rounded-xl flex items-center justify-center ${latest.direction === 'UP' ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400'}`}>
                    {latest.direction === 'UP' ? <TrendingUp size={26} /> : <TrendingDown size={26} />}
                  </div>
                  <div>
                    <div className="text-2xl font-mono font-semibold">{latest.direction}</div>
                    <div className="text-xs text-zinc-500">
                      {latest.confidence}% confidence · from ${fmtUsd(latest.refPrice)} · {timeAgo(latest.ts)}
                    </div>
                  </div>
                </div>
                <div>
                  <div className="flex justify-between text-[10px] text-zinc-500 mb-1">
                    <span>Confidence</span>
                    <span>{latest.confidence}%</span>
                  </div>
                  <Progress value={latest.confidence} className="h-2 bg-zinc-800" />
                </div>
                {latest.resolvedAt && (
                  <div className={`text-xs flex items-center gap-1.5 ${latest.correct ? 'text-emerald-400' : 'text-red-400'}`}>
                    {latest.correct ? <CheckCircle2 size={13} /> : <XCircle size={13} />}
                    Resolved: {latest.correct ? 'correct' : 'incorrect'} (actual ${fmtUsd(latest.actualPrice ?? 0)})
                  </div>
                )}
              </div>
            ) : (
              <div className="text-sm text-zinc-600 text-center py-8">Engine warming up — first forecast within 5 minutes</div>
            )}
          </CardContent>
        </Card>

        {/* Crash radar live */}
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
              <ShieldAlert size={15} className={crash && crash.severity !== 'LOW' ? 'text-red-400' : 'text-zinc-500'} /> Crash radar (live)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {crash ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="text-[10px] text-zinc-500 mb-1">Crash-down {crash.probability}%</div>
                    <Progress value={crash.probability} className="h-2 bg-zinc-800 [&>div]:bg-red-500" />
                  </div>
                  <div>
                    <div className="text-[10px] text-zinc-500 mb-1">Melt-up {crash.meltUp}%</div>
                    <Progress value={crash.meltUp} className="h-2 bg-zinc-800 [&>div]:bg-emerald-500" />
                  </div>
                </div>
                <p className="text-[11px] text-zinc-500 leading-relaxed">{crash.narrative}</p>
                <div className="grid grid-cols-3 gap-2 text-[10px] text-zinc-600">
                  <span>vol z: <span className="text-zinc-300 font-mono">{crash.indicators.volZ?.toFixed(1)}</span></span>
                  <span>ATR ratio: <span className="text-zinc-300 font-mono">{crash.indicators.atrRatio?.toFixed(2)}</span></span>
                  <span>velocity: <span className="text-zinc-300 font-mono">{crash.indicators.velocity?.toFixed(1)}</span></span>
                  <span>volume z: <span className="text-zinc-300 font-mono">{crash.indicators.volumeZ?.toFixed(1)}</span></span>
                  <span>BB release: <span className="text-zinc-300 font-mono">{crash.indicators.bbSqueezeRelease?.toFixed(2)}</span></span>
                  <span>VWAP dev: <span className="text-zinc-300 font-mono">{crash.indicators.vwapDev?.toFixed(1)}σ</span></span>
                </div>
              </div>
            ) : (
              <div className="text-sm text-zinc-600 text-center py-8">Waiting for candle closes…</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Accuracy stats */}
      {stats && stats.resolved > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3">
              <div className="text-[10px] text-zinc-500">Forecasts made</div>
              <div className="text-lg font-mono font-semibold">{stats.total}</div>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3">
              <div className="text-[10px] text-zinc-500">Resolved</div>
              <div className="text-lg font-mono font-semibold">{stats.resolved}</div>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3">
              <div className="text-[10px] text-zinc-500">All-time accuracy</div>
              <div className="text-lg font-mono font-semibold text-amber-400">{stats.accuracy !== null ? `${(stats.accuracy * 100).toFixed(1)}%` : '—'}</div>
            </CardContent>
          </Card>
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3">
              <div className="text-[10px] text-zinc-500">Last-20 accuracy</div>
              <div className="text-lg font-mono font-semibold">{stats.recentAccuracy !== null ? `${(stats.recentAccuracy * 100).toFixed(1)}%` : '—'}</div>
            </CardContent>
          </Card>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Prediction log */}
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-zinc-300">Forecast log</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-80 overflow-y-auto space-y-1.5">
              {predictions.map((p) => (
                <div key={p.id} className="flex items-center gap-2 text-xs bg-zinc-950/60 rounded-lg px-3 py-2 border border-zinc-800/60">
                  <span className={p.direction === 'UP' ? 'text-emerald-400' : 'text-red-400'}>{p.direction === 'UP' ? '▲' : '▼'}</span>
                  <span className="font-mono text-zinc-500">{new Date(p.ts).toISOString().slice(11, 16)}</span>
                  <span className="text-zinc-400">{p.confidence}%</span>
                  <span className="text-zinc-600">from ${p.refPrice.toFixed(2)}</span>
                  <span className="ml-auto">
                    {p.resolvedAt ? (
                      p.correct ? <span className="text-emerald-400">✓</span> : <span className="text-red-400">✗</span>
                    ) : (
                      <span className="text-zinc-600">pending</span>
                    )}
                  </span>
                </div>
              ))}
              {predictions.length === 0 && <div className="text-center text-zinc-600 py-6 text-sm">No forecasts yet</div>}
            </div>
          </CardContent>
        </Card>

        {/* Crash alerts */}
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm text-zinc-300">Crash alert history</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="max-h-80 overflow-y-auto space-y-1.5">
              {alerts.map((a) => (
                <div key={a.id} className="text-xs bg-zinc-950/60 rounded-lg px-3 py-2 border border-zinc-800/60">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className={a.severity === 'CRITICAL' || a.severity === 'HIGH' ? 'border-red-500/40 text-red-400' : 'border-amber-500/40 text-amber-400'}>
                      {a.severity}
                    </Badge>
                    <span className="font-mono">{a.probability}%</span>
                    <span className={a.direction === 'DOWN' ? 'text-red-400' : 'text-emerald-400'}>{a.direction}</span>
                    <span className="ml-auto text-zinc-600">{timeAgo(a.ts)}</span>
                  </div>
                  <div className="text-[10px] text-zinc-600 mt-1">{a.actionTaken}</div>
                </div>
              ))}
              {alerts.length === 0 && (
                <div className="text-center text-zinc-600 py-6 text-sm">
                  No crash alerts yet — the radar fires at ≥70% probability and auto-pauses new orders
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
