'use client'

import { useEffect, useState, useCallback } from 'react'
import { useEngineSocket } from '@/hooks/use-engine-socket'
import LoginView from '@/components/trading/login-view'
import DashboardTab from '@/components/trading/dashboard-tab'
import StrategiesTab from '@/components/trading/strategies-tab'
import AutoscanTab from '@/components/trading/autoscan-tab'
import BacktestTab from '@/components/trading/backtest-tab'
import PaperTab from '@/components/trading/paper-tab'
import PredictionsTab from '@/components/trading/predictions-tab'
import DataTab from '@/components/trading/data-tab'
import AdminTab from '@/components/trading/admin-tab'
import { fmtUsd } from '@/hooks/use-engine-socket'
import {
  LayoutDashboard, LineChart, Radar, FlaskConical, Wallet, Brain, Database, Users, LogOut, Zap, Wifi, WifiOff,
} from 'lucide-react'

type Tab = 'dashboard' | 'strategies' | 'autoscan' | 'backtest' | 'paper' | 'predictions' | 'data' | 'admin'

export default function Home() {
  const [authState, setAuthState] = useState<'checking' | 'unauthenticated' | 'authenticated'>('checking')
  const [user, setUser] = useState<{ id: string; email: string; name: string | null; role: string } | null>(null)
  const [tab, setTab] = useState<Tab>('dashboard')
  const socket = useEngineSocket()

  const checkAuth = useCallback(async () => {
    try {
      const res = await fetch('/api/auth/login')
      const data = await res.json()
      if (data.authenticated && data.user) {
        setUser(data.user)
        setAuthState('authenticated')
      } else {
        setAuthState('unauthenticated')
      }
    } catch {
      setAuthState('unauthenticated')
    }
  }, [])

  useEffect(() => {
    const t = setTimeout(checkAuth, 0)
    return () => clearTimeout(t)
  }, [checkAuth])

  // PWA service worker registration (installable app / Add to Home Screen)
  useEffect(() => {
    if ('serviceWorker' in navigator && window.location.protocol === 'https:') {
      navigator.serviceWorker.register('/sw.js').catch(() => {})
    }
  }, [])

  const logout = async () => {
    await fetch('/api/auth/logout', { method: 'POST' })
    setUser(null)
    setAuthState('unauthenticated')
  }

  if (authState === 'checking') {
    return (
      <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
        <div className="animate-pulse text-amber-500 font-mono">AI TRADING LAB — booting…</div>
      </div>
    )
  }

  if (authState === 'unauthenticated' || !user) {
    return <LoginView onSuccess={(u) => { setUser(u); setAuthState('authenticated') }} />
  }

  const tabs: Array<{ key: Tab; label: string; icon: React.ReactNode; adminOnly?: boolean }> = [
    { key: 'dashboard', label: 'Dashboard', icon: <LayoutDashboard size={17} /> },
    { key: 'strategies', label: 'Strategies', icon: <LineChart size={17} /> },
    { key: 'autoscan', label: 'Auto-Scan', icon: <Radar size={17} /> },
    { key: 'backtest', label: 'Backtest', icon: <FlaskConical size={17} /> },
    { key: 'paper', label: 'Paper Trading', icon: <Wallet size={17} /> },
    { key: 'predictions', label: 'Predictions', icon: <Brain size={17} /> },
    { key: 'data', label: 'Data', icon: <Database size={17} /> },
    { key: 'admin', label: 'Admin', icon: <Users size={17} />, adminOnly: true },
  ]

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-zinc-900/60 backdrop-blur sticky top-0 z-40">
        <div className="flex items-center justify-between px-3 sm:px-5 h-14 gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-400 to-yellow-600 flex items-center justify-center shrink-0">
              <Zap size={17} className="text-zinc-950" />
            </div>
            <div className="min-w-0">
              <div className="font-semibold text-sm sm:text-base truncate">AI Trading Lab <span className="text-amber-500">Data Engine</span>
                <span className="ml-1.5 inline-flex items-center rounded bg-amber-500/15 border border-amber-500/30 px-1 py-px text-[9px] font-semibold text-amber-400 align-middle">v4.0</span>
              </div>
              <div className="text-[10px] text-zinc-500 hidden sm:block">Monitor · Paper Trading · Research</div>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-4">
            {socket.gold && (
              <div className="text-right hidden xs:block">
                <div className="text-[10px] text-zinc-500 leading-none">GOLD</div>
                <div className="font-mono text-sm text-amber-400 leading-tight">{fmtUsd(socket.gold.last)}</div>
              </div>
            )}
            {socket.btc && (
              <div className="text-right hidden sm:block">
                <div className="text-[10px] text-zinc-500 leading-none">BTC</div>
                <div className="font-mono text-sm text-zinc-300 leading-tight">{fmtUsd(socket.btc.last, 0)}</div>
              </div>
            )}
            <div className={`flex items-center gap-1 text-[11px] px-2 py-1 rounded-full ${socket.connected ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'}`}>
              {socket.connected ? <Wifi size={12} /> : <WifiOff size={12} />}
              <span className="hidden sm:inline">{socket.connected ? 'LIVE' : 'OFFLINE'}</span>
            </div>
            <div className="hidden md:flex flex-col text-right leading-tight mr-1">
              <span className="text-xs text-zinc-300">{user.name ?? user.email}</span>
              <span className="text-[10px] text-amber-500/80">{user.role}</span>
            </div>
            <button
              onClick={logout}
              className="p-2 rounded-lg hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200"
              title="Log out"
            >
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </header>

      <div className="flex flex-1 min-h-0">
        {/* Sidebar (desktop) */}
        <nav className="hidden md:flex flex-col w-52 border-r border-zinc-800 bg-zinc-900/30 p-2 gap-1 sticky top-14 h-[calc(100vh-3.5rem)]">
          {tabs.filter((t) => !t.adminOnly || user.role === 'ADMIN').map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm text-left transition-colors ${
                tab === t.key ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30' : 'text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-200 border border-transparent'
              }`}
            >
              {t.icon}
              {t.label}
              {t.key === 'paper' && socket.account?.burst.active && (
                <span className="ml-auto w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
              )}
            </button>
          ))}
          <div className="mt-auto p-3 text-[10px] text-zinc-600 leading-relaxed">
            Research → Backtest → Paper → Live parity engine.
            <br />
            Every fill models spread + slippage + impact.
          </div>
        </nav>

        {/* Mobile tabs */}
        <div className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-zinc-900/95 backdrop-blur border-t border-zinc-800 flex overflow-x-auto">
          {tabs.filter((t) => !t.adminOnly || user.role === 'ADMIN').map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex-1 min-w-[64px] flex flex-col items-center gap-0.5 py-2 text-[9px] ${
                tab === t.key ? 'text-amber-400' : 'text-zinc-500'
              }`}
            >
              {t.icon}
              <span className="truncate max-w-full px-0.5">{t.label}</span>
            </button>
          ))}
        </div>

        {/* Content */}
        <main className="flex-1 min-w-0 p-3 sm:p-5 pb-20 md:pb-5 overflow-x-hidden">
          {tab === 'dashboard' && <DashboardTab socket={socket} user={user} />}
          {tab === 'strategies' && <StrategiesTab />}
          {tab === 'autoscan' && <AutoscanTab />}
          {tab === 'backtest' && <BacktestTab />}
          {tab === 'paper' && <PaperTab socket={socket} user={user} />}
          {tab === 'predictions' && <PredictionsTab socket={socket} />}
          {tab === 'data' && <DataTab />}
          {tab === 'admin' && user.role === 'ADMIN' && <AdminTab currentUser={user} />}
        </main>
      </div>

      {/* Footer */}
      <footer className="hidden md:block border-t border-zinc-800 bg-zinc-900/40 px-5 py-2 text-[10px] text-zinc-600">
        AI Trading Lab Data Engine · Paper trading only — no live orders · All results model real costs (spread, slippage, square-root impact)
      </footer>
    </div>
  )
}
