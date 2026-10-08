# TRADING EVENT CONTRACT

**Document ID:** TRA-TEC-001 · **Version:** 1.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `src/data_engine/runtime/contracts.py` + `runtime/identity.py`
**Mandate:** §21/§22/§23/§31/§34 (typed event contracts)

---

## 1. Identity Rules

- Every identity = `<domain-prefix>` + SHA-256 over a canonical payload
  that ALWAYS includes `RUNTIME_CONTRACT_VERSION` (`1.0.0`).
- Identity is a pure function of declared values: no wall-clock, no
  RNG, no PID, no path (ID-WC-03 discipline).
- Runtime identity NEVER depends on the frozen Phase 3 `Candle` hash
  (H-1 independence).
- Floats are rounded to 12 decimals before hashing.
- Prefix map: `rtpre.` prediction artifacts · `rtdec.` decisions ·
  `rtpln.` trade plans · `rtord.` orders (idempotency keys) ·
  `rtfll.` fills · `rtpos.` positions/P&L · `rtxit.` exits ·
  `rtled.` ledger events · `rtmem.` memory · `rtks.` kill switch ·
  `rtrg.` risk assessments · `rtrec.` reconciliation ·
  `rtsta.` checkpoints/journal · `rtdat.` dataset readiness ·
  `rtseq.` sequences · `rtmod.`/`rtens.`/`rtcal.` model artifacts.

## 2. PredictionArtifact (§21) — immutable after creation

`prediction_id, symbol, horizon, timestamp, prediction (UP/DOWN/FLAT),
probability, expected_return, volatility, uncertainty
(UncertaintyReport), model_versions, ensemble_composition,
feature_version, dataset_version, regime, crash_risk (mandatory
'probability' key), provenance, correlation_id`. Constructed by the
runtime per bar; hash `rtpre.`; recorded in the Prediction Ledger.

## 3. UncertaintyReport (§18)

`confidence, entropy, ensemble_disagreement, epistemic_uncertainty,
aleatoric_uncertainty`. `is_high` returns True when ANY dimension is
missing (missing evidence is uncertainty, never neutrality) or when
confidence < 0.5 / entropy > 0.9.

## 4. Decision (§22) — closed output vocabulary

`BUY / SELL / REDUCE / HOLD / CLOSE / NO_TRADE` — NO_TRADE mandatory
and first-class. Fields: `decision_id, action, symbol, timestamp,
prediction_ids, model_versions, uncertainty, regime, crash_risk,
portfolio_state, reason (substantive, ≥8 chars), rejected_alternatives
(action + reason each), correlation_id`. The DecisionEngine has NO
order authority.

## 5. TradePlan (§23)

`trade_plan_id, decision_id, symbol, side (BUY/SELL only — exits are
netted), quantity, notional, entry constraints (MARKET/LIMIT,
GTC/DAY/TTL + ttl_bars), stop_loss, take_profit, risk_budget (≥0;
zero only for pure risk-reducing plans), expected_return,
risk_reward_ratio, uncertainty, crash_risk, model_context,
correlation_id`. LIMIT plans validate SL/TP geometry at construction.
A TradePlan MUST pass the RiskGate before execution (§25).

## 6. ExitRecord (§31)

`exit_id, reason (SL_HIT/TP_HIT/RISK_EXIT/CRASH_EXIT/STRATEGY_EXIT/
MANUAL_CLOSE/SYSTEM_CLOSE/KILL_SWITCH_CLOSE), symbol, timestamp,
position_quantity (at trigger), average_cost, order_ids, fill_ids,
realized_pnl (post-exit), correlation_id`.

## 7. Runtime Events Envelope

All ledger events (`runtime/ledgers.py`) carry: `event_id, ledger,
event_type, timestamp (audit wall-clock), sequence (per ledger),
correlation_id, parent_id, actor, payload, payload_hash, prev_hash,
event_hash`. Correlation IDs thread the whole chain — §50's
"no orphan events" guarantee is tested in the positive E2E.

## 8. Order Identity (§28)

`idempotent_order_id(session_id, trade_plan_id, decision_id,
correlation_id, symbol, side, order_type, quantity, limit_price)` —
deterministic hash (`rtord.`): the same intent always yields the same
id; retries are structurally detected and idempotent; ambiguous
orders (UNKNOWN/RECONCILING) refuse resubmission until reconciled.
