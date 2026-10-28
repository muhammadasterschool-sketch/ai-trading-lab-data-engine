'use client'

import { useEffect, useState } from 'react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { useToast } from '@/hooks/use-toast'
import { timeAgo } from './types'
import { Users, ShieldCheck, KeyRound, UserX, UserCheck, RotateCcw, Ticket, Plus, Trash2, Power, Bell, CheckCheck } from 'lucide-react'
import { Input } from '@/components/ui/input'

interface UserRow {
  id: string
  email: string
  name: string | null
  role: string
  totpEnabled: boolean
  isActive: boolean
  lastLoginAt: string | null
  createdAt: string
}

interface InviteRow {
  id: string
  code: string
  label: string
  maxUses: number
  uses: number
  active: boolean
  createdBy: string
  createdAt: string
  lastUsedAt: string | null
}

interface NotifRow {
  id: string
  kind: string
  title: string
  body: string
  meta: string
  read: boolean
  createdAt: string
}

export default function AdminTab({ currentUser }: { currentUser: { id: string; email: string } }) {
  const [users, setUsers] = useState<UserRow[]>([])
  const [stats, setStats] = useState<{ total: number; active: number; sessions: number } | null>(null)
  const [invites, setInvites] = useState<InviteRow[]>([])
  const [newCode, setNewCode] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newMax, setNewMax] = useState('0')
  const [inviteBusy, setInviteBusy] = useState(false)
  const [notifs, setNotifs] = useState<NotifRow[]>([])
  const [unread, setUnread] = useState(0)
  const { toast } = useToast()

  const load = async () => {
    const res = await fetch('/api/admin/users')
    if (res.ok) {
      const d = await res.json()
      setUsers(d.users)
      setStats(d.stats)
    }
    const r2 = await fetch('/api/admin/invites')
    if (r2.ok) {
      const d2 = await r2.json()
      setInvites(d2.codes)
    }
    // v5.6 — registration notification feed (owner sees every signup first)
    const r3 = await fetch('/api/admin/notifications')
    if (r3.ok) {
      const d3 = await r3.json()
      setNotifs(d3.items ?? [])
      setUnread(d3.unreadCount ?? 0)
    }
  }
  useEffect(() => {
    const t = setTimeout(load, 0)
    const poll = setInterval(load, 20000) // live feed — new signups appear without reload
    return () => {
      clearTimeout(t)
      clearInterval(poll)
    }
  }, [])

  const markAllRead = async () => {
    await fetch('/api/admin/notifications', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'read-all' }),
    })
    load()
  }

  const inviteAct = async (action: string, extra: Record<string, unknown> = {}) => {
    const res = await fetch('/api/admin/invites', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, ...extra }),
    })
    const d = await res.json()
    if (!res.ok) {
      toast({ title: 'Failed', description: d.error, variant: 'destructive' })
      return
    }
    if (action === 'create') {
      toast({ title: 'Invitation code created', description: d.code.code, duration: 12000 })
      setNewCode('')
      setNewLabel('')
      setNewMax('0')
    } else {
      toast({ title: 'Done' })
    }
    load()
  }

  const act = async (action: string, userId: string, extra: Record<string, unknown> = {}) => {
    const res = await fetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action, userId, ...extra }),
    })
    const d = await res.json()
    if (!res.ok) {
      toast({ title: 'Action failed', description: d.error, variant: 'destructive' })
      return
    }
    if (d.tempPassword) {
      toast({
        title: 'Password reset',
        description: `Temporary password: ${d.tempPassword} — share securely. 2FA enrollment will happen on next login.`,
        duration: 15000,
      })
    } else {
      toast({ title: 'Done' })
    }
    load()
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold flex items-center gap-2">
          <Users size={18} className="text-amber-500" /> Admin — Users &amp; System
        </h2>
        <p className="text-xs text-zinc-500 mt-0.5">
          Every login requires two-factor verification. Deactivated users are logged out immediately.
        </p>
      </div>

      <Card className="bg-zinc-900/50 border-zinc-800 border-l-2 border-l-amber-500/70">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
            <Bell size={14} className="text-amber-500" /> Registration alerts
            {unread > 0 && (
              <Badge className="bg-amber-500 text-zinc-950 hover:bg-amber-400 ml-1">{unread} new</Badge>
            )}
            {notifs.length > 0 && unread > 0 && (
              <Button size="sm" variant="ghost" className="h-6 text-[10px] text-zinc-400 ml-auto" onClick={markAllRead}>
                <CheckCheck size={12} className="mr-1" /> Mark all read
              </Button>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {notifs.length === 0 ? (
            <p className="text-[11px] text-zinc-500">No registrations yet — the moment anyone signs up with any invitation code, the alert appears here first (and on the owner&apos;s phone as a status-bar notification).</p>
          ) : (
            <div className="space-y-1.5 max-h-64 overflow-y-auto">
              {notifs.map((n) => (
                <div key={n.id} className={`rounded-md border px-3 py-2 ${n.read ? 'border-zinc-800/60 bg-zinc-950/40' : 'border-amber-500/30 bg-amber-500/5'}`}>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-semibold ${n.read ? 'text-zinc-400' : 'text-amber-300'}`}>{n.title}</span>
                    {!n.read && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 shrink-0" />}
                    <span className="text-[10px] text-zinc-600 ml-auto shrink-0">{timeAgo(n.createdAt)}</span>
                  </div>
                  <div className="text-[11px] text-zinc-400 mt-0.5">{n.body}</div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <div className="grid grid-cols-3 gap-3">
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="text-[10px] text-zinc-500">Users</div>
            <div className="text-lg font-mono font-semibold">{stats?.total ?? '—'}</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="text-[10px] text-zinc-500">Active</div>
            <div className="text-lg font-mono font-semibold text-emerald-400">{stats?.active ?? '—'}</div>
          </CardContent>
        </Card>
        <Card className="bg-zinc-900/50 border-zinc-800">
          <CardContent className="p-3">
            <div className="text-[10px] text-zinc-500">Live sessions</div>
            <div className="text-lg font-mono font-semibold">{stats?.sessions ?? '—'}</div>
          </CardContent>
        </Card>
      </div>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-300">User management</CardTitle>
        </CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-xs min-w-[760px]">
            <thead>
              <tr className="text-zinc-500 border-b border-zinc-800">
                <th className="text-left py-2 pr-2">User</th>
                <th className="text-left py-2 pr-2">Role</th>
                <th className="text-left py-2 pr-2">2FA</th>
                <th className="text-left py-2 pr-2">Status</th>
                <th className="text-left py-2 pr-2">Last login</th>
                <th className="text-left py-2 pr-2">Joined</th>
                <th className="text-right py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-b border-zinc-800/50">
                  <td className="py-2.5 pr-2">
                    <div className="text-zinc-200">{u.name ?? '—'}</div>
                    <div className="text-zinc-500 text-[10px]">{u.email}</div>
                  </td>
                  <td className="py-2.5 pr-2">
                    <Badge variant="outline" className={u.role === 'ADMIN' ? 'border-amber-500/40 text-amber-400' : 'border-zinc-700 text-zinc-400'}>
                      {u.role}
                    </Badge>
                  </td>
                  <td className="py-2.5 pr-2">
                    {u.totpEnabled ? (
                      <span className="text-emerald-400 flex items-center gap-1"><ShieldCheck size={12} /> enabled</span>
                    ) : (
                      <span className="text-amber-400">pending enrollment</span>
                    )}
                  </td>
                  <td className="py-2.5 pr-2">
                    {u.isActive ? (
                      <span className="text-emerald-400">active</span>
                    ) : (
                      <span className="text-red-400">deactivated</span>
                    )}
                  </td>
                  <td className="py-2.5 pr-2 text-zinc-500">{u.lastLoginAt ? timeAgo(u.lastLoginAt) : 'never'}</td>
                  <td className="py-2.5 pr-2 text-zinc-500">{new Date(u.createdAt).toISOString().slice(0, 10)}</td>
                  <td className="py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      {u.id !== currentUser.id && (
                        <>
                          <Button
                            size="sm" variant="outline" className="h-7 text-[10px] border-zinc-700"
                            onClick={() => act('toggle-active', u.id)}
                          >
                            {u.isActive ? <><UserX size={11} className="mr-1" /> Deactivate</> : <><UserCheck size={11} className="mr-1" /> Activate</>}
                          </Button>
                          <Button
                            size="sm" variant="outline" className="h-7 text-[10px] border-zinc-700"
                            onClick={() => act('set-role', u.id, { role: u.role === 'ADMIN' ? 'TRADER' : 'ADMIN' })}
                          >
                            Make {u.role === 'ADMIN' ? 'trader' : 'admin'}
                          </Button>
                        </>
                      )}
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button size="sm" variant="outline" className="h-7 text-[10px] border-zinc-700">
                            <KeyRound size={11} className="mr-1" /> Reset password
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent className="bg-zinc-900 border-zinc-700">
                          <AlertDialogHeader>
                            <AlertDialogTitle>Reset password for {u.email}?</AlertDialogTitle>
                            <AlertDialogDescription>
                              A new temporary password will be generated and shown once. The user&apos;s 2FA
                              enrollment will also be reset (they will scan a new QR on next login), and all their
                              sessions will be terminated.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction onClick={() => act('reset-password', u.id)}>Reset</AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardHeader className="pb-2">
          <CardTitle className="text-sm text-zinc-300 flex items-center gap-2">
            <Ticket size={14} className="text-amber-500" /> Invitation codes (invite-only access)
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-2 items-end">
            <div className="sm:col-span-4 space-y-1">
              <label className="text-[10px] text-zinc-500">Code (A-Z, 0-9)</label>
              <Input value={newCode} onChange={(e) => setNewCode(e.target.value.toUpperCase())} placeholder="AB12CD34" className="h-8 bg-zinc-950 border-zinc-700 font-mono text-xs" />
            </div>
            <div className="sm:col-span-4 space-y-1">
              <label className="text-[10px] text-zinc-500">Label (who is it for)</label>
              <Input value={newLabel} onChange={(e) => setNewLabel(e.target.value)} placeholder="e.g. Ali — trading group" className="h-8 bg-zinc-950 border-zinc-700 text-xs" />
            </div>
            <div className="sm:col-span-2 space-y-1">
              <label className="text-[10px] text-zinc-500">Max uses (0=∞)</label>
              <Input type="number" min={0} value={newMax} onChange={(e) => setNewMax(e.target.value)} className="h-8 bg-zinc-950 border-zinc-700 text-xs" />
            </div>
            <Button
              size="sm" disabled={inviteBusy || newCode.length < 6}
              onClick={() => inviteAct('create', { code: newCode, label: newLabel, maxUses: Number(newMax) })}
              className="h-8 bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold text-xs sm:col-span-2"
            >
              <Plus size={13} className="mr-1" /> Create
            </Button>
          </div>

          <div className="overflow-x-auto -mx-2 px-2">
            <table className="w-full text-xs min-w-[640px]">
              <thead>
                <tr className="text-zinc-500 border-b border-zinc-800">
                  <th className="text-left py-2 pr-2">Code</th>
                  <th className="text-left py-2 pr-2">Label</th>
                  <th className="text-left py-2 pr-2">Uses</th>
                  <th className="text-left py-2 pr-2">Status</th>
                  <th className="text-left py-2 pr-2">Last used</th>
                  <th className="text-right py-2">Actions</th>
                </tr>
              </thead>
              <tbody>
                {invites.map((c) => (
                  <tr key={c.id} className="border-b border-zinc-800/50">
                    <td className="py-2 pr-2 font-mono text-amber-400 tracking-wider">{c.code}</td>
                    <td className="py-2 pr-2 text-zinc-300">{c.label || '—'}</td>
                    <td className="py-2 pr-2 text-zinc-400">{c.uses}{c.maxUses > 0 ? ` / ${c.maxUses}` : ' / ∞'}</td>
                    <td className="py-2 pr-2">
                      {c.active
                        ? <span className="text-emerald-400">active</span>
                        : <span className="text-red-400">disabled</span>}
                    </td>
                    <td className="py-2 pr-2 text-zinc-500">{c.lastUsedAt ? timeAgo(c.lastUsedAt) : 'never'}</td>
                    <td className="py-2 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <Button size="sm" variant="outline" className="h-7 text-[10px] border-zinc-700" onClick={() => inviteAct('toggle', { id: c.id })}>
                          <Power size={11} className="mr-1" /> {c.active ? 'Disable' : 'Enable'}
                        </Button>
                        <Button size="sm" variant="outline" className="h-7 text-[10px] border-zinc-700 text-red-400 hover:text-red-300" onClick={() => inviteAct('delete', { id: c.id })}>
                          <Trash2 size={11} className="mr-1" /> Delete
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-zinc-500 leading-relaxed">
            Nobody can create an account on this engine without an active invitation code. Share a code privately;
            the recipient opens the app, taps <b>Register</b>, and signs up with their name, Gmail and the code.
            Every account still requires mandatory 2FA enrollment on first login. Use max-uses to make
            single-person codes (max uses = 1) that burn after one registration.
          </p>
        </CardContent>
      </Card>

      <Card className="bg-zinc-900/50 border-zinc-800">
        <CardContent className="p-4 flex items-start gap-3">
          <RotateCcw size={15} className="text-amber-500 shrink-0 mt-0.5" />
          <p className="text-[11px] text-zinc-500 leading-relaxed">
            The separate admin APK has been retired — all administration (user management, approvals, kill switch,
            account reset) now lives inside this monitor app behind mandatory 2FA. Admins see every user; regular
            users see only their own trading workspace.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
