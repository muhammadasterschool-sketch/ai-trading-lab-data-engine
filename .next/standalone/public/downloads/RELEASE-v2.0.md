# v2.0 — SIDE DRAWER (versionCode 27)

**Release date:** Oct 29, 2026 · **Owner request:** "broker add karne ke functions remove ho gaye hai — aik kam karo ke side drawer ana do jis mai saare options honge"

## Kya hua tha (diagnosis)
Broker functions **remove NAHI hue** — v1.8 UI consolidation (10 tabs → 5) me wo Settings ke andar ek chip (⚙️ Settings → 🔌 Broker) ban gaye the. `renderBroker()` + Add Custom Broker form (name/kind/api key/secret/login/password) + Saved Brokers + REMOVE — sab code me intact tha. Problem discoverability ki thi, functionality ki nahi.

## Hal — v2.0 SIDE DRAWER

### ☰ Hamburger drawer (header left button)
- Slide-in drawer left se, premium dark theme, smooth animation (0.24s)
- **Scrim backdrop** — bahar tap/✕ karo to band
- **User card**: name + email + ADMIN/TRADER role pill

### Drawer me SAARE options (kuch chhupa nahi)
**Trading:**
- 📊 Home (candlestick chart, equity, engine status)
- 💱 Trades (live P/L)
- 🧪 Strategy Lab (3C · AI strategies · trash/UNDO)
- 📡 Insights (indicators · news · instruments · logs)

**System — saare options:**
- ⚙️ Settings — General (risk · engine · guards)
- 🔌 **Broker — Add / Saved** (api keys · remove) ← ab seedhe drawer se khulta hai
- 🛡️ Owner Control (admin: users · invites · alerts) — unread+pending red badge ke saath

**Account:** 🚪 Sign out

### Extra
- Active item highlight (green) — kahan ho pata chalta hai
- Control badge drawer ke andar bhi live update (pollAlerts → updateNavBadges → renderDrawer)
- Bottom nav (5 tabs) barkarar — drawer supplement hai, replacement nahi
- SET_TAB deep-link: Broker/Control click par seedha wahi section khulta hai

## 3C rules: UNCHANGED
Buy: C1 green + C2 green + C3 red, body≥70%, C3 close protected; SL opposite extreme; BE @+1R; TP @+3R; 5-candle window. v1.9 OWNER GATE + v1.8 PRO FILTER PACK + PRO GUARD + fees sab barkarar.

## Technical notes
- CSS: #burger, #scrim, #drawer, .dhead/.duser/.ditems/.ditem/.dsep/.dlabel/.dfoot
- JS: openDrawer/closeDrawer/dGo(tab,setTab)/dItem/renderDrawer; updateNavBadges me drawer live-refresh
- versionCode 27, versionName "2.0", health `2.0.0`
