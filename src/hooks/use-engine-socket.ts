'use client'

import { useEffect, useRef, useState, useCallback } from 'react'
import { io, type Socket } from 'socket.io-client'

export interface LivePrice {
  last: number
  bid: number
  ask: number
  ts: number
  spread?: number
}

export interface EngineAccount {
  equity: number
  balance: number
  dayPnlPct: number
  drawdownPct: number
  dailyLossLimitPct: number
  maxDrawdownPct: number
  status: string
  autopilot: boolean
  crashPause: boolean
  openPositions: Array<{
    id: string
    side: string
    qty: number
    entryPrice: number
    currentPrice: number
    unrealized: number
    mode: string
    openedAt: number
    closeIn: number | null
  }>
  burst: { active: boolean; direction: string | null; seq: number; pending: string | null }
  ts: number
}

export interface ConsensusLive {
  symbol: string
  bullishScore: number
  bearishScore: number
  direction: string
  thresholdMet: boolean
  votes: Array<{ key: string; name: string; dir: number; conf: number; reason: string }>
  burst?: { active: boolean; direction: string | null; seq: number; status: string }
  barTs: number
}

export interface CrashLive {
  probability: number
  meltUp: number
  severity: string
  direction: string
  indicators: Record<string, number>
  narrative: string
}

export interface EngineStats {
  ticks: number
  bars: number
  ordersFilled: number
  ordersRejected: number
  bursts: number
  burstTrades: number
  positions: number
  uptimeSec: number
}

export function useEngineSocket() {
  const socketRef = useRef<Socket | null>(null)
  const [connected, setConnected] = useState(false)
  const [gold, setGold] = useState<LivePrice | null>(null)
  const [btc, setBtc] = useState<LivePrice | null>(null)
  const [account, setAccount] = useState<EngineAccount | null>(null)
  const [consensus, setConsensus] = useState<ConsensusLive | null>(null)
  const [crash, setCrash] = useState<CrashLive | null>(null)
  const [stats, setStats] = useState<EngineStats | null>(null)
  const [feed, setFeed] = useState<Array<{ ts: number; text: string; kind: string }>>([])

  const pushFeed = useCallback((text: string, kind: string) => {
    setFeed((f) => [{ ts: Date.now(), text, kind }, ...f].slice(0, 80))
  }, [])

  useEffect(() => {
    // Dual-mode connection (v4):
    // 1. Page served directly from the Next.js server (self-hosted local mode,
    //    no reverse proxy) → engine lives at <same-host>:3003
    // 2. Page served through a reverse proxy / gateway (sandbox preview, Caddy
    //    on :81, or cloud deployment) → same-origin with ?XTransformPort=3003
    let url = '/?XTransformPort=3003'
    if (typeof window !== 'undefined') {
      const { protocol, hostname, port } = window.location
      if (port === '3000') {
        url = `${protocol}//${hostname}:3003`
      }
    }
    const socket = io(url, {
      transports: ['websocket', 'polling'],
      forceNew: true,
      reconnection: true,
      reconnectionAttempts: 20,
      reconnectionDelay: 2000,
    })
    socketRef.current = socket

    socket.on('connect', () => setConnected(true))
    socket.on('disconnect', () => setConnected(false))
    socket.on('hello', (data: { gold: LivePrice | null; btc: LivePrice | null; account: EngineAccount | null; consensus: ConsensusLive | null; stats: EngineStats }) => {
      if (data.gold) setGold(data.gold)
      if (data.btc) setBtc(data.btc)
      if (data.account) setAccount(data.account)
      if (data.consensus) setConsensus(data.consensus)
      if (data.stats) setStats(data.stats)
    })
    socket.on('price', (data: { gold: LivePrice | null; btc: LivePrice | null }) => {
      if (data.gold) setGold(data.gold)
      if (data.btc) setBtc(data.btc)
    })
    socket.on('account', (data: EngineAccount) => setAccount(data))
    socket.on('consensus', (data: ConsensusLive) => {
      setConsensus(data)
      if (data.burst?.active) {
        pushFeed(`Burst mode ACTIVE (${data.burst.direction}) — seq #${data.burst.seq}`, 'burst')
      }
    })
    socket.on('crash', (data: CrashLive) => setCrash(data))
    socket.on('crash-alert', (data: { alert: { probability: number; direction: string; severity: string }; narrative: string }) => {
      pushFeed(`⚠ CRASH ALERT ${data.alert.severity}: ${data.alert.probability}% probability ${data.alert.direction} — ${data.narrative}`, 'crash')
    })
    socket.on('forecast', (data: { direction: string; confidence: number }) => {
      pushFeed(`Forecast(5m): ${data.direction} @ ${data.confidence}% confidence`, 'forecast')
    })
    socket.on('trade', (data: { side: string; qty: number; entryPrice: number; mode: string; reason: string; ts: number }) => {
      pushFeed(`${data.mode === 'BURST' ? '⚡' : '📈'} ${data.side} ${data.qty} @ ${data.entryPrice.toFixed(2)} — ${data.reason}`, 'trade')
    })
    socket.on('trade-close', (data: { side: string; pnl: number; exitReason: string; mode: string; ts: number }) => {
      pushFeed(`${data.pnl >= 0 ? '✅' : '❌'} Closed ${data.side} (${data.exitReason}) PnL $${data.pnl.toFixed(2)}`, 'close')
    })
    socket.on('order-rejected', (data: { reason: string; mode: string }) => {
      pushFeed(`🚫 Order rejected (${data.mode}): ${data.reason}`, 'reject')
    })
    socket.on('burst-tick', (data: { seq: number; direction: string | null }) => {
      pushFeed(`⚡ Burst trade #${data.seq} ${data.direction}`, 'burst')
    })
    socket.on('positions-closed', (data: { reason: string }) => {
      pushFeed(`All positions closed (${data.reason})`, 'close')
    })
    socket.on('stats', (data: EngineStats) => setStats(data))

    return () => {
      socket.disconnect()
    }
  }, [pushFeed])

  return { connected, gold, btc, account, consensus, crash, stats, feed }
}

// ---------- formatting helpers ----------
export function fmtUsd(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !isFinite(v)) return '—'
  return v.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export function fmtPct(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || !isFinite(v)) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(digits)}%`
}

export function fmtPnl(v: number | null | undefined): string {
  if (v === null || v === undefined || !isFinite(v)) return '—'
  return `${v >= 0 ? '+' : '−'}$${Math.abs(v).toFixed(2)}`
}

export function pnlColor(v: number | null | undefined): string {
  if (v === null || v === undefined || !isFinite(v) || v === 0) return 'text-zinc-400'
  return v > 0 ? 'text-emerald-400' : 'text-red-400'
}

export function timeAgo(ts: number | string | Date): string {
  const t = typeof ts === 'number' ? ts : new Date(ts).getTime()
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}
