'use client'

import { useEffect, useState, useCallback } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Slider } from '@/components/ui/slider'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useToast } from '@/hooks/use-toast'
import { fmtPnl, pnlColor, timeAgo, type EngineSocketData } from './types'
import { Wallet, Zap, ShieldAlert, CheckCheck, X, Save, Gauge } from 'lucide-react'

interface PaperAccount {
  id: string
  balance: number
  equity: number
  startBalance: number
  dailyLossLimitPct: number
  maxDrawdownPct: number
  perTradeRiskPct: number
  burstRiskPct: number
  maxBurstTrades: number
  consensusThreshold: number
  burstEnabled: boolean
  status: string
}

interface Trade {
  id: string
  side: string
  qty: number
  entryPrice: number
  exitPrice: number | null
  entryAt: string
  exitAt: string | null
  pnl: number | null
  mode: string
  status: string
  strategyKey: string | null
  tcaBps: number | null
}

interface TcaDigest {
  totalFills: number
  groups: Record<string, { fills: number; avgShortfallBps: number; totalCosts: number }>
  overall: { avgShortfallBps: number; totalCosts: number }
}

interface ApprovalRequest {
  id: string
  type: string
  title: string
  evidence: string
  status: string
  requestedBy: string
  decidedBy: string | null
  createdAt: string
}

export default function PaperTab({ socket, user }: { socket: EngineSocketData; user: { role: string } }) {
  const [account, setAccount] = useState<PaperAccount | null>(null)
  const [trades, setTrades] = useState<Trade[]>([])
  const [tca, setTca] = useState<TcaDigest | null>(null)
  const [approvals, setApprovals] = useState<ApprovalRequest[]>([])
  const [saving, setSaving] = useState(false)
  const { toast } = useToast()

  const [risk, setRisk] = useState({ dailyLoss: 5, maxDd: 10, perTrade: 1, burstRisk: 0.1, maxBurst: 60, threshold: 60 })

  const load = useCallback(async () => {
    const [accRes, tradeRes, tcaRes, apprRes] = await Promise.all([
      fetch('/api/paper/account'),
      fetch('/api/paper/trades?limit=100'),
      fetch('/api/paper/tca'),
      fetch('/api/approvals'),
    ])
    if (accRes.ok) {
      const d = await accRes.json()
      setAccount(d.account)
      setRisk({
        dailyLoss: d.account.dailyLossLimitPct,
        maxDd: d.account.maxDrawdownPct,
        perTrade: d.account.perTradeRiskPct,
        burstRisk: d.account.burstRiskPct,
        maxBurst: d.account.maxBurstTrades,
        threshold: d.account.consensusThreshold,
      })
    }
    if (tradeRes.ok) setTrades((await tradeRes.json()).trades)
    if (tcaRes.ok) setTca((await tcaRes.json()).digest)
    if (apprRes.ok) setApprovals((await apprRes.json()).requests)
  }, [])

  useEffect(() => {
    load()
    const t = setInterval(load, 15000)
    return () => clearInterval(t)
  }, [load])

  const saveRisk = async () => {
    setSaving(true)
    try {
      await fetch('/api/paper/account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dailyLossLimitPct: risk.dailyLoss,
          maxDrawdownPct: risk.maxDd,
          perTradeRiskPct: risk.perTrade,
          burstRiskPct: risk.burstRisk,
          maxBurstTrades: risk.maxBurst,
          consensusThreshold: risk.threshold,
        }),
      })
      toast({ title: 'Risk configuration saved' })
      load()
    } finally {
      setSaving(false)
    }
  }

  const decide = async (id: string, approve: boolean) => {
    const res = await fetch('/api/approvals', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'decide', id, note: approve ? 'APPROVED' : 'REJECT' }),
    })
    if (res.ok) {
      toast({ title: approve ? 'Approved' : 'Rejected' })
      load()
    } else {
      const d = await res.json()
      toast({ title: 'Failed', description: d.error, variant: 'destructive' })
    }
  }

  const control = async (action: string) => {
    await fetch('/api/engine', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action }),
    })
    toast({ title: action === 'close-all' ? 'Closing all positions…' : action })
  }

  const closed = trades.filter((t) => t.status === 'CLOSED')
  const wins = closed.filter((t) => (t.pnl ?? 0) > 0).length
  const acc = socket.account

  return (
    <div className="space-y-4">
      {/* Header stats */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        {[
          { label: 'Equity', value: `$${(acc?.equity ?? account?.equity ?? 0).toLocaleString()}`, color: 'text-amber-400' },
          { label: 'Day P&L', value: `${(acc?.dayPnlPct ?? 0) >= 0 ? '+' : ''}${(acc?.dayPnlPct ?? 0).toFixed(2)}%`, color: pnlColor(acc?.dayPnlPct ?? 0) },
          { label: 'Closed trades', value: String(closed.length) },
          { label: 'Win rate', value: closed.length ? `${((wins / closed.length) * 100).toFixed(1)}%` : '—' },
          { label: 'Status', value: acc?.status ?? account?.status ?? '—', color: (acc?.status ?? '') === 'ACTIVE' ? 'text-emerald-400' : 'text-red-400' },
        ].map((s) => (
          <Card key={s.label} className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="p-3">
              <div className="text-[10px] text-zinc-500">{s.label}</div>
              <div className={`text-lg font-mono font-semibold ${s.color ?? 'text-zinc-200'}`}>{s.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Tabs defaultValue="trades">
        <TabsList className="bg-zinc-900 border border-zinc-800">
          <TabsTrigger value="trades" className="data-[state=active]:bg-amber-500/15 data-[state=active]:text-amber-400">Trades</TabsTrigger>
          <TabsTrigger value="risk" className="data-[state=active]:bg-amber-500/15 data-[state=active]:text-amber-400">Risk Config</TabsTrigger>
          <TabsTrigger value="tca" className="data-[state=active]:bg-amber-500/15 data-[state=active]:text-amber-400">TCA</TabsTrigger>
          <TabsTrigger value="approvals" className="data-[state=active]:bg-amber-500/15 data-[state=active]:text-amber-400">
            Approvals {approvals.filter((a) => a.status === 'PENDING').length > 0 && (
              <span className="ml-1.5 w-2 h-2 rounded-full bg-amber-400 inline-block" />
            )}
          </TabsTrigger>
        </TabsList>

        {/* Trades */}
        <TabsContent value="trades" className="space-y-3">
          <div className="flex gap-2 flex-wrap">
            <Button size="sm" variant="outline" className="border-zinc-700" onClick={() => control('close-all')}>
              <X size={13} className="mr-1" /> Close all positions
            </Button>
            <Badge variant="outline" className="border-zinc-700 text-zinc-400">
              <Zap size={11} className="mr-1 text-amber-400" /> burst trades close after 60s
            </Badge>
          </div>
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardContent className="overflow-x-auto">
              <table className="w-full text-xs min-w-[720px]">
                <thead>
                  <tr className="text-zinc-500 border-b border-zinc-800">
                    <th className="text-left py-2 pr-2">Opened</th>
                    <th className="text-left py-2 pr-2">Side</th>
                    <th className="text-left py-2 pr-2">Mode</th>
                    <th className="text-left py-2 pr-2">Strategy</th>
                    <th className="text-right py-2 pr-2">Qty</th>
                    <th className="text-right py-2 pr-2">Entry</th>
                    <th className="text-right py-2 pr-2">Exit</th>
                    <th className="text-right py-2 pr-2">P&L</th>
                    <th className="text-right py-2 pr-2">TCA</th>
                    <th className="text-right py-2">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t) => (
                    <tr key={t.id} className="border-b border-zinc-800/50">
                      <td className="py-2 pr-2 text-zinc-500">{timeAgo(t.entryAt)}</td>
                      <td className={`py-2 pr-2 font-medium ${t.side === 'LONG' ? 'text-emerald-400' : 'text-red-400'}`}>{t.side}</td>
                      <td className="py-2 pr-2">
                        {t.mode === 'BURST' ? <span className="text-amber-400 flex items-center gap-1"><Zap size={10} />Burst</span> : <span className="text-zinc-400">Normal</span>}
                      </td>
                      <td className="py-2 pr-2 text-zinc-400">{t.strategyKey ?? '—'}</td>
                      <td className="py-2 pr-2 text-right font-mono">{t.qty.toFixed(3)}</td>
                      <td className="py-2 pr-2 text-right font-mono">{t.entryPrice.toFixed(2)}</td>
                      <td className="py-2 pr-2 text-right font-mono">{t.exitPrice?.toFixed(2) ?? '—'}</td>
                      <td className={`py-2 pr-2 text-right font-mono ${pnlColor(t.pnl)}`}>{t.status === 'CLOSED' ? fmtPnl(t.pnl) : '—'}</td>
                      <td className="py-2 pr-2 text-right font-mono text-zinc-500">{t.tcaBps !== null ? `${t.tcaBps.toFixed(1)}bp` : '—'}</td>
                      <td className="py-2 text-right">
                        <span className={t.status === 'OPEN' ? 'text-amber-400' : 'text-zinc-500'}>{t.status}</span>
                      </td>
                    </tr>
                  ))}
                  {trades.length === 0 && (
                    <tr><td colSpan={10} className="text-center py-8 text-zinc-600">No paper trades yet — start autopilot on the Dashboard</td></tr>
                  )}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Risk config */}
        <TabsContent value="risk" className="space-y-4">
          <Card className="bg-zinc-900/50 border-zinc-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm flex items-center gap-2 text-zinc-300">
                <ShieldAlert size={15} className="text-amber-500" /> Prop-firm Risk Rulebook
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              {[
                { label: 'Daily loss limit', value: risk.dailyLoss, min: 1, max: 10, step: 0.5, unit: '%', set: (v: number) => setRisk({ ...risk, dailyLoss: v }), desc: 'Circuit breaker — halts trading for the day' },
                { label: 'Trailing max drawdown', value: risk.maxDd, min: 2, max: 30, step: 1, unit: '%', set: (v: number) => setRisk({ ...risk, maxDd: v }), desc: 'Measured from the account high-water mark' },
                { label: 'Risk per trade (normal)', value: risk.perTrade, min: 0.1, max: 3, step: 0.1, unit: '%', set: (v: number) => setRisk({ ...risk, perTrade: v }), desc: 'Position sized so the stop distance = this % of equity' },
                { label: 'Risk per burst trade', value: risk.burstRisk, min: 0.01, max: 1, step: 0.01, unit: '%', set: (v: number) => setRisk({ ...risk, burstRisk: v }), desc: 'Each 1-trade/sec burst order risks this much' },
                { label: 'Max burst trades', value: risk.maxBurst, min: 10, max: 200, step: 10, unit: '', set: (v: number) => setRisk({ ...risk, maxBurst: v }), desc: 'Hard cap on burst sequence length (1/sec)' },
                { label: 'Consensus threshold', value: risk.threshold, min: 50, max: 90, step: 5, unit: '%', set: (v: number) => setRisk({ ...risk, threshold: v }), desc: 'Weighted agreement required before confirmation candle' },
              ].map((s) => (
                <div key={s.label}>
                  <div className="flex justify-between text-xs mb-1.5">
                    <span className="text-zinc-300">{s.label} <span className="text-zinc-600">— {s.desc}</span></span>
                    <span className="font-mono text-amber-400">{s.value}{s.unit}</span>
                  </div>
                  <Slider value={[s.value]} min={s.min} max={s.max} step={s.step} onValueChange={(v) => s.set(v[0])} />
                </div>
              ))}
              <div className="flex items-center gap-3">
                <Button onClick={saveRisk} disabled={saving} className="bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold">
                  <Save size={14} className="mr-1.5" /> {saving ? 'Saving…' : 'Save configuration'}
                </Button>
                <span className="text-[11px] text-zinc-600">Applies to every order the engine places — including each burst trade.</span>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* TCA */}
        <TabsContent value="tca" className="space-y-3">
          {tca && tca.totalFills > 0 ? (
            <>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <Card className="bg-zinc-900/50 border-zinc-800">
                  <CardContent className="p-3">
                    <div className="text-[10px] text-zinc-500">Total fills analysed</div>
                    <div className="text-lg font-mono font-semibold">{tca.totalFills}</div>
                  </CardContent>
                </Card>
                <Card className="bg-zinc-900/50 border-zinc-800">
                  <CardContent className="p-3">
                    <div className="text-[10px] text-zinc-500">Avg arrival-price shortfall</div>
                    <div className="text-lg font-mono font-semibold text-amber-400">{tca.overall.avgShortfallBps.toFixed(2)} bp</div>
                  </CardContent>
                </Card>
                <Card className="bg-zinc-900/50 border-zinc-800">
                  <CardContent className="p-3">
                    <div className="text-[10px] text-zinc-500">Total friction costs</div>
                    <div className="text-lg font-mono font-semibold">${tca.overall.totalCosts.toFixed(2)}</div>
                  </CardContent>
                </Card>
              </div>
              <Card className="bg-zinc-900/50 border-zinc-800">
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm text-zinc-300">Breakdown (implementation shortfall per group)</CardTitle>
                </CardHeader>
                <CardContent className="overflow-x-auto">
                  <table className="w-full text-xs min-w-[480px]">
                    <thead>
                      <tr className="text-zinc-500 border-b border-zinc-800">
                        <th className="text-left py-2">Group</th>
                        <th className="text-right py-2 pr-2">Fills</th>
                        <th className="text-right py-2 pr-2">Avg shortfall (bp)</th>
                        <th className="text-right py-2">Total costs</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(tca.groups).map(([k, v]) => (
                        <tr key={k} className="border-b border-zinc-800/50">
                          <td className="py-2 text-zinc-300">{k}</td>
                          <td className="py-2 text-right font-mono">{v.fills}</td>
                          <td className="py-2 text-right font-mono text-amber-400">{v.avgShortfallBps.toFixed(2)}</td>
                          <td className="py-2 text-right font-mono">${v.totalCosts.toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </CardContent>
              </Card>
            </>
          ) : (
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-8 text-center text-sm text-zinc-500">
                No fills yet — TCA (transaction cost analysis) will appear after the first paper trades.
              </CardContent>
            </Card>
          )}
        </TabsContent>

        {/* Approvals */}
        <TabsContent value="approvals" className="space-y-3">
          {approvals.length === 0 ? (
            <Card className="bg-zinc-900/50 border-zinc-800">
              <CardContent className="p-8 text-center text-sm text-zinc-500">
                No approval requests. Auto-scan winners can be sent here from the Auto-Scan tab.
              </CardContent>
            </Card>
          ) : (
            approvals.map((a) => {
              const evidence = JSON.parse(a.evidence || '{}')
              return (
                <Card key={a.id} className={`bg-zinc-900/50 ${a.status === 'PENDING' ? 'border-amber-500/30' : 'border-zinc-800'}`}>
                  <CardContent className="p-4">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="min-w-0">
                        <div className="font-medium text-sm">{a.title}</div>
                        <div className="text-[11px] text-zinc-500 mt-0.5">
                          {a.type} · by {a.requestedBy} · {timeAgo(a.createdAt)}
                        </div>
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          {Object.entries(evidence).slice(0, 6).map(([k, v]) => (
                            <span key={k} className="text-[10px] font-mono bg-zinc-950 border border-zinc-800 rounded px-2 py-0.5 text-zinc-400">
                              {k}: <span className="text-amber-400">{typeof v === 'object' ? JSON.stringify(v) : String(v)}</span>
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {a.status === 'PENDING' ? (
                          user.role === 'ADMIN' ? (
                            <>
                              <Button size="sm" className="bg-emerald-600 hover:bg-emerald-500 text-white" onClick={() => decide(a.id, true)}>
                                <CheckCheck size={13} className="mr-1" /> Approve
                              </Button>
                              <Button size="sm" variant="destructive" onClick={() => decide(a.id, false)}>Reject</Button>
                            </>
                          ) : (
                            <Badge variant="outline" className="border-amber-500/40 text-amber-400">Awaiting admin decision</Badge>
                          )
                        ) : (
                          <Badge variant="outline" className={a.status === 'APPROVED' ? 'border-emerald-500/40 text-emerald-400' : 'border-red-500/40 text-red-400'}>
                            {a.status}
                          </Badge>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )
            })
          )}
        </TabsContent>
      </Tabs>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-4 flex items-start gap-3">
          <Gauge size={16} className="text-amber-500 shrink-0 mt-0.5" />
          <p className="text-[11px] text-zinc-500 leading-relaxed">
            Governance: strategies proposed by research (auto-scan) enter the approval inbox before they can trade
            paper. The kill switch and close-all controls live on this page and the Dashboard. Live trading is not
            enabled in this build — this system trades paper only.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
