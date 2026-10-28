'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { InputOTP, InputOTPGroup, InputOTPSlot } from '@/components/ui/input-otp'
import { Zap, ShieldCheck, KeyRound, Ticket, UserPlus } from 'lucide-react'

interface Props {
  onSuccess: (user: { id: string; email: string; name: string | null; role: string }) => void
}

export default function LoginView({ onSuccess }: Props) {
  const [step, setStep] = useState<'credentials' | 'enroll' | 'verify'>('credentials')
  const [mode, setMode] = useState<'signin' | 'register'>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [regDone, setRegDone] = useState(false)
  const [code, setCode] = useState('')
  const [qr, setQr] = useState<string | null>(null)
  const [secret, setSecret] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const submitCredentials = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, name }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Login failed')
      if (data.stage === 'ENROLL_2FA') {
        setQr(data.qr)
        setSecret(data.secret)
        setStep('enroll')
      } else {
        setStep('verify')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setBusy(false)
    }
  }

  const submitRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, email, password, invitationCode: inviteCode }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Registration failed')
      setRegDone(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Registration failed')
    } finally {
      setBusy(false)
    }
  }

  const submitCode = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (code.length !== 6) {
      setError('Enter the 6-digit code')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/auth/verify-2fa', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.error || 'Invalid code')
      onSuccess(data.user)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Invalid code')
      setCode('')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-amber-400 to-yellow-600 flex items-center justify-center">
            <Zap size={24} className="text-zinc-950" />
          </div>
          <div>
            <h1 className="text-xl font-bold">AI Trading Lab</h1>
            <p className="text-xs text-zinc-500">
              Data Engine · Monitor &amp; Paper Trading
              <span className="ml-2 inline-flex items-center rounded bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.5 text-[10px] font-semibold text-amber-400">
                v4.0
              </span>
            </p>
          </div>
        </div>

        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 sm:p-8">
          {step === 'credentials' && !regDone && (
            <>
              <div className="grid grid-cols-2 gap-1 mb-6 rounded-lg bg-zinc-950 border border-zinc-800 p-1">
                <button
                  type="button"
                  onClick={() => { setMode('signin'); setError(null) }}
                  className={`rounded-md py-2 text-sm font-medium transition-colors ${mode === 'signin' ? 'bg-amber-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}
                >
                  Sign in
                </button>
                <button
                  type="button"
                  onClick={() => { setMode('register'); setError(null) }}
                  className={`rounded-md py-2 text-sm font-medium transition-colors flex items-center justify-center gap-1.5 ${mode === 'register' ? 'bg-amber-500 text-zinc-950' : 'text-zinc-400 hover:text-zinc-200'}`}
                >
                  <UserPlus size={14} /> Register
                </button>
              </div>

              {mode === 'signin' && (
                <form onSubmit={submitCredentials} className="space-y-4">
                  <div className="flex items-center gap-2 text-amber-500 text-sm mb-2">
                    <ShieldCheck size={16} />
                    <span>Two-factor authentication is mandatory on this system</span>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="si-name">Name</Label>
                    <Input
                      id="si-name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Your registered name"
                      required
                      autoComplete="name"
                      className="bg-zinc-950 border-zinc-700"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@gmail.com"
                      required
                      autoComplete="email"
                      className="bg-zinc-950 border-zinc-700"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••••••"
                      required
                      autoComplete="current-password"
                      className="bg-zinc-950 border-zinc-700"
                    />
                  </div>
                  {error && <p className="text-sm text-red-400">{error}</p>}
                  <Button type="submit" disabled={busy} className="w-full bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold">
                    {busy ? 'Checking…' : 'Sign in'}
                  </Button>
                </form>
              )}

              {mode === 'register' && (
                <form onSubmit={submitRegister} className="space-y-4">
                  <div className="flex items-center gap-2 text-amber-500 text-sm mb-2">
                    <Ticket size={16} />
                    <span>Invite-only — a valid invitation code is required</span>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="invite">Invitation code</Label>
                    <Input
                      id="invite"
                      value={inviteCode}
                      onChange={(e) => setInviteCode(e.target.value.toUpperCase())}
                      placeholder="M2991474"
                      required
                      autoCapitalize="characters"
                      className="bg-zinc-950 border-zinc-700 font-mono tracking-wider"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="name">Full name</Label>
                    <Input
                      id="name"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Your name"
                      required
                      autoComplete="name"
                      className="bg-zinc-950 border-zinc-700"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reg-email">Gmail</Label>
                    <Input
                      id="reg-email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="yourname@gmail.com"
                      required
                      autoComplete="email"
                      className="bg-zinc-950 border-zinc-700"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reg-password">Password</Label>
                    <Input
                      id="reg-password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="Min 8 characters, letters + numbers"
                      required
                      autoComplete="new-password"
                      className="bg-zinc-950 border-zinc-700"
                    />
                  </div>
                  {error && <p className="text-sm text-red-400">{error}</p>}
                  <Button type="submit" disabled={busy} className="w-full bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold">
                    {busy ? 'Creating account…' : 'Create account'}
                  </Button>
                  <p className="text-[11px] text-zinc-500 leading-relaxed">
                    After registration you will sign in with your name + email + password and enroll 2FA
                    (Google Authenticator). Your paper-trading account is created automatically,
                    isolated from other users.
                  </p>
                </form>
              )}
            </>
          )}

          {step === 'credentials' && regDone && (
            <div className="space-y-5 text-center">
              <div className="w-14 h-14 mx-auto rounded-full bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center">
                <ShieldCheck size={26} className="text-emerald-400" />
              </div>
              <div>
                <h2 className="text-lg font-semibold">Account created</h2>
                <p className="text-sm text-zinc-400 mt-1">
                  Now sign in with your name, email and password. On first login you will scan a QR code
                  to activate two-factor authentication — no code, no access.
                </p>
              </div>
              <Button
                type="button"
                onClick={() => { setRegDone(false); setMode('signin'); setPassword(''); setInviteCode(''); setName('') }}
                className="w-full bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold"
              >
                Continue to sign in
              </Button>
            </div>
          )}

          {step === 'enroll' && (
            <div className="space-y-5">
              <div>
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <KeyRound size={18} className="text-amber-500" /> Set up 2FA
                </h2>
                <p className="text-sm text-zinc-400 mt-1">
                  Every account on this engine requires two-factor verification. Scan this QR with Google
                  Authenticator or Authy, then enter the 6-digit code to activate.
                </p>
              </div>
              {qr && (
                <div className="flex justify-center p-3 bg-white rounded-xl w-fit mx-auto">
                  
                  <img src={qr} alt="2FA QR code" width={200} height={200} />
                </div>
              )}
              {secret && (
                <div className="text-center">
                  <p className="text-xs text-zinc-500 mb-1">Can&apos;t scan? Enter this secret manually:</p>
                  <code className="text-xs font-mono bg-zinc-950 border border-zinc-800 rounded px-3 py-1.5 block break-all">{secret}</code>
                </div>
              )}
              <form onSubmit={submitCode} className="space-y-3">
                <Label>Enter the 6-digit code</Label>
                <div className="flex justify-center">
                  <InputOTP maxLength={6} value={code} onChange={setCode}>
                    <InputOTPGroup>
                      {[0, 1, 2, 3, 4, 5].map((i) => (
                        <InputOTPSlot key={i} index={i} className="border-zinc-700 bg-zinc-950" />
                      ))}
                    </InputOTPGroup>
                  </InputOTP>
                </div>
                {error && <p className="text-sm text-red-400 text-center">{error}</p>}
                <Button type="submit" disabled={busy} className="w-full bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold">
                  {busy ? 'Verifying…' : 'Activate 2FA & sign in'}
                </Button>
              </form>
            </div>
          )}

          {step === 'verify' && (
            <form onSubmit={submitCode} className="space-y-5">
              <div>
                <h2 className="text-lg font-semibold flex items-center gap-2">
                  <ShieldCheck size={18} className="text-emerald-400" /> Two-factor verification
                </h2>
                <p className="text-sm text-zinc-400 mt-1">Enter the current 6-digit code from your authenticator app.</p>
              </div>
              <div className="flex justify-center">
                <InputOTP maxLength={6} value={code} onChange={setCode}>
                  <InputOTPGroup>
                    {[0, 1, 2, 3, 4, 5].map((i) => (
                      <InputOTPSlot key={i} index={i} className="border-zinc-700 bg-zinc-950" />
                    ))}
                  </InputOTPGroup>
                </InputOTP>
              </div>
              {error && <p className="text-sm text-red-400 text-center">{error}</p>}
              <Button type="submit" disabled={busy} className="w-full bg-amber-500 hover:bg-amber-400 text-zinc-950 font-semibold">
                {busy ? 'Verifying…' : 'Verify & sign in'}
              </Button>
            </form>
          )}
        </div>

        <p className="text-center text-[11px] text-zinc-600 mt-6">
          Paper trading system · No live orders are ever sent · All data from verified repositories
        </p>
      </div>
    </div>
  )
}
