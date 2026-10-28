// Re-export socket types & helpers for tab components
export {
  useEngineSocket,
  fmtUsd,
  fmtPct,
  fmtPnl,
  pnlColor,
  timeAgo,
  type LivePrice,
  type EngineAccount,
  type ConsensusLive,
  type CrashLive,
  type EngineStats,
} from '@/hooks/use-engine-socket'

export type EngineSocketData = {
  connected: boolean
  gold: import('@/hooks/use-engine-socket').LivePrice | null
  btc: import('@/hooks/use-engine-socket').LivePrice | null
  account: import('@/hooks/use-engine-socket').EngineAccount | null
  consensus: import('@/hooks/use-engine-socket').ConsensusLive | null
  crash: import('@/hooks/use-engine-socket').CrashLive | null
  stats: import('@/hooks/use-engine-socket').EngineStats | null
  feed: Array<{ ts: number; text: string; kind: string }>
}
