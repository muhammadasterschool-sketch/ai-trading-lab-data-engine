# KILL SWITCH SPEC

**Document ID:** TRA-KSS-001 · **Version:** 1.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/kill_switch.py`, `risk/engine.py`
**Mandate:** §26 (hierarchical kill switches)

---

## 1. Scopes (7)

ORDER · STRATEGY · SYMBOL · MODEL · PORTFOLIO · ACCOUNT · GLOBAL

Effects: GLOBAL/ACCOUNT → runtime HALTED; PORTFOLIO → no new orders;
SYMBOL → NO_TRADE for the symbol; MODEL → model retired from
prediction; STRATEGY → strategy disabled; ORDER → one order blocked.

## 2. Semantics

- **Tripping is unprivileged** (the fail-safe direction must always be
  reachable). Every trip is ledgered (Incident Ledger, RT-F5).
- **Checking happens before every execution** (`KillSwitchManager.check`
  inside the RiskGate's mandatory `kill_switch` check). Risk-REDUCING
  orders (closing) remain permitted under an active switch — the
  switch blocks NEW exposure, not risk reduction (BUG-003 netting
  discipline; the closing path is the fail-safe direction).
- **Reset is human-principal gated** (ARCH-F1/§61): machine principals
  are structurally refused — the AI can NEVER disable a critical kill
  switch. ACCOUNT/GLOBAL additionally require a recorded
  `authorize_reset` from the SAME human principal BEFORE `reset`.
- Persisted switch state survives restart (RT-F4); restore happens in
  recovery, and a critical active switch forces the HALT verdict.

## 3. SwitchState Record (§26 fields)

scope, target, active, activated_at, reason, source,
reset_requested_at/by, reset_authorized_at/by, reset_at — all
persisted and audited.

## 4. Layering with the Phase 8 RiskEngine

The runtime kill-switch hierarchy wraps the Phase 8 engine's own
switch: the RiskGate consults BOTH (manager hierarchy via
`kill_switch` check; engine via `check_order`'s `_guard`). The
engine's trip/reset are audited in its violation chain (RT-F5) and
verifiable (ARCH-F2 `verify_violation_log`).
