'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { useToast } from '@/hooks/use-toast'
import { LineChart, Youtube, Pause, Play } from 'lucide-react'

interface Strategy {
  id: string
  key: string
  name: string
  family: string
  description: string
  youtuberRef: string
  params: string
  status: string
  weight: number
}

const FAMILY_COLORS: Record<string, string> = {
  trend: 'bg-amber-500/15 text-amber-400 border-amber-500/30',
  'mean-reversion': 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  breakout: 'bg-orange-500/15 text-orange-400 border-orange-500/30',
  momentum: 'bg-fuchsia-500/15 text-fuchsia-400 border-fuchsia-500/30',
  institutional: 'bg-cyan-500/15 text-cyan-400 border-cyan-500/30',
}

export default function StrategiesTab() {
  const [strategies, setStrategies] = useState<Strategy[]>([])
  const [loading, setLoading] = useState(true)
  const { toast } = useToast()

  const load = async () => {
    const res = await fetch('/api/strategies')
    if (res.ok) {
      const data = await res.json()
      setStrategies(data.strategies)
    }
    setLoading(false)
  }
  useEffect(() => {
    const t = setTimeout(load, 0)
    return () => clearTimeout(t)
     
  }, [])

  const toggle = async (key: string) => {
    const res = await fetch('/api/strategies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, action: 'toggle-status' }),
    })
    const data = await res.json()
    if (!res.ok) {
      toast({ title: 'Cannot change status', description: data.error, variant: 'destructive' })
      return
    }
    toast({ title: data.status === 'ACTIVE' ? 'Strategy activated' : 'Strategy paused' })
    load()
  }

  if (loading) return <div className="text-center text-zinc-500 py-16">Loading strategies…</div>

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <LineChart size={18} className="text-amber-500" /> Top-5 YouTuber Strategies
          </h2>
          <p className="text-xs text-zinc-500 mt-0.5">
            The five most-taught 1-minute gold scalping setups — voting on every closed candle
          </p>
        </div>
        <Badge variant="outline" className="border-amber-500/40 text-amber-400">
          <Youtube size={12} className="mr-1" /> M1 · Gold (PAXG)
        </Badge>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
        {strategies.map((s) => {
          const params = JSON.parse(s.params || '{}')
          const active = s.status === 'ACTIVE'
          return (
            <Card key={s.key} className={`bg-zinc-900/50 ${active ? 'border-zinc-700' : 'border-zinc-800 opacity-75'}`}>
              <CardHeader className="pb-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <CardTitle className="text-base">{s.name}</CardTitle>
                    <div className="text-[11px] text-zinc-500 mt-0.5">{s.youtuberRef}</div>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Badge variant="outline" className={FAMILY_COLORS[s.family] ?? 'text-zinc-400 border-zinc-700'}>{s.family}</Badge>
                    <Switch checked={active} onCheckedChange={() => toggle(s.key)} aria-label={`Toggle ${s.name}`} />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-xs text-zinc-400 leading-relaxed">{s.description}</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(params).map(([k, v]) => (
                    <span key={k} className="text-[10px] font-mono bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-zinc-400">
                      {k}=<span className="text-amber-400">{String(v)}</span>
                    </span>
                  ))}
                </div>
                <div className="flex items-center gap-2 text-[10px] text-zinc-600">
                  {active ? (
                    <span className="flex items-center gap-1 text-emerald-400"><Play size={10} /> voting in consensus</span>
                  ) : (
                    <span className="flex items-center gap-1"><Pause size={10} /> paused — not voting</span>
                  )}
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-4 text-xs text-zinc-500 leading-relaxed">
          <p className="font-medium text-zinc-300 mb-1.5">How consensus works</p>
          Each active strategy votes LONG/SHORT with a confidence weight on every closed 1-minute candle.
          When at least two strategies agree and the weighted consensus crosses <span className="text-amber-400">60%</span>,
          the engine waits for a <span className="text-amber-400">confirmation candle</span> closing in that direction —
          then burst mode begins placing <span className="text-amber-400">one paper trade per second</span> under hard
          risk caps (each burst trade risks 0.1% of equity, closes after 60s, and the whole mode halts instantly on
          any risk limit).
        </CardContent>
      </Card>
    </div>
  )
}
