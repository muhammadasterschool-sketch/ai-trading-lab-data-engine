# v1.9 — OWNER GATE (versionCode 26)

**Release date:** Oct 29, 2026 · **Owner request:** "code pehle se likha hua nahi ana chahiye… register karne ke baad mere pass notification ana chahiye, iske baad hi login kar sakta hai. Aik admin sirf, baaki sare users."

## Kya badla (What changed)

### 1. Pre-written invite code REMOVED everywhere
- Register form ka code field ab **khali** hota hai — pehle `M•••••••(REDACTED)` hardcoded pre-filled tha, is liye jo bhi page khole register kar sakta tha.
- Forgot-password (reset) form se bhi pre-filled code hata diya.
- **Public downloads page se bhi code leak hata diya** — wahan code openly published tha (`⚠ Invitation code: M•••••••(REDACTED)`), sab se bara leak yehi tha.
- Ab code sirf owner Control tab se generate hota hai aur owner khud user ko bhejta hai (WhatsApp etc).

### 2. Registration → OWNER NOTIFICATION (3 channels)
- **Status-bar notification** (high importance) — "🔔 New registration — APPROVE karein: <name>"
- **In-app alert feed** (Settings > Control > Registration Alerts) — unread badge ke saath
- **Home par red banner** (admin only) — "⏳ N registrations PENDING approval — <names>" + direct link to Control
- PENDING user login try kare to owner ko **dobara reminder notification** jata hai.

### 3. APPROVAL GATE — approval ke baad hi login
- Naya registration `approved=0` (PENDING) banta hai — **login 403 refused** clear message ke saath: "Account PENDING approval — owner ne abhi approve nahi kiya."
- Owner Control > Users me **✓ APPROVE** button dabata hai → user approved → ab sign in possible.
- Users list me PENDING pill + "LOGIN BLOCKED" status + APPROVE button.
- Control stats me "Pending Approval" card.
- Db v4→v5 migration: `users.approved INTEGER DEFAULT 1` — **purane sab accounts (owner included) update ke baad seedha login kar sakte hain**, koi lockout nahi.

### 4. SINGLE ADMIN — sirf 1 ADMIN, baaki sab TRADER
- Pehla account = ADMIN (owner, auto-approved). **Baaki SAB registrations TRADER + PENDING.**
- Second admin ban hi nahi sakta (koi promote endpoint nahi; register always TRADER after first).
- Last-admin delete protection pehle se thi — barkarar.

## 3C rules: UNCHANGED
Buy: C1 green + C2 green + C3 red, body≥70%, C3 close protected; SL opposite extreme; BE @+1R; TP @+3R; 5-candle window. v1.8 PRO FILTER PACK + v1.7 PRO GUARD + fees 0.05%/side sab barkarar.

## Technical notes
- `users` table: +`approved` column (v5 migration, idempotent ALTER, DEFAULT 1)
- `/api/auth/register` → non-first registrations insert `approved=0`; response `{pending:1}`
- `/api/auth/login` → `approved=0` → 403 + PENDING_LOGIN notification + reminder to owner
- `/api/admin/users` → `approved` per user + `pendingUsers` count
- `/api/admin/users` POST → new action `approve`
- Notifier.registration(..., boolean owner) — owner vs pending-registration message
- versionCode 26, versionName "1.9", health `1.9.0`
