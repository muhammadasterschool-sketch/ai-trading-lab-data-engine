# DECISION LEDGER SPEC

**Document ID:** TRA-DLS-001 · **Version:** 1.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `runtime/ledgers.py` (decision ledger) + `runtime/decision.py`
**Mandate:** §22/§35

---

## 1. Decision Records

Every DecisionEngine output is ledgered immediately:

- actionable decisions: `DECISION_BUY / DECISION_SELL /
  DECISION_REDUCE / DECISION_HOLD / DECISION_CLOSE` — with decision
  id, symbol, reason, prediction ids, regime, crash risk, parent =
  prediction artifact id;
- refusals: `DECISION_NO_TRADE` (§35) — with the full refusal context
  (reason, blocked condition, uncertainty, crash risk, regime, model
  versions, portfolio state).

## 2. Decision Contract (§22)

Closed vocabulary BUY/SELL/REDUCE/HOLD/CLOSE/NO_TRADE. Every decision
cites its evidence (prediction ids + model versions are mandatory
fields), records the portfolio state it saw, and — for entry
decisions — the alternatives it rejected with reasons
(`RejectedAlternative`). The decision reason must be a substantive
explanation (≥ 8 chars, enforced by contract validation).

## 3. Authority Boundary

The DecisionEngine has NO order authority. The decision ledger
records INTENT; the trade-plan ledger records the sized plan; the
risk assessment (trade-plan ledger) records the gate verdict; the
order ledger records execution. The full §69 question chain
("what decision was made; why was it made; what risk checks
passed/failed") is reconstructible from these four ledgers joined on
correlation id.

## 4. NO_TRADE Statistics

Because every refusal is ledgered with its blocked condition, the
system can aggregate WHY it did not trade over any window (data
stale / uncertainty / crash / confidence / no-entry band / kill
switch) — the anti-silence guarantee of §35.
