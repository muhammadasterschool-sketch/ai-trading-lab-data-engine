# PREDICTION LEDGER SPEC

**Document ID:** TRA-PLS-001 · **Version:** 1.0.0 · **Status:** AUTHORITATIVE (implemented)
**Applies to:** `runtime/ledgers.py` (prediction ledger) + `prediction/ledger.py`
**Mandate:** §34 (prediction ledger as part of the family)

---

## 1. Runtime Prediction Ledger

Every prediction artifact produced by the runtime is appended to the
runtime **prediction** ledger (`rtled.` chain) with: prediction id,
symbol, probability, direction, full uncertainty bundle, regime, crash
risk, model versions, correlation id (parent = bar correlation).
Sequence is monotonic; payload hash + prev-hash chaining make the
prediction history tamper-evident.

## 2. Record Content

`PREDICTION_ARTIFACT` events carry the complete §21 context:
probability AND its provenance (which models, which feature version,
which dataset version, calibrated or not), the uncertainty that
accompanied it, the regime and crash state at decision time. The
ledger answers §69 questions 3–6 ("what did the models predict; how
certain were they; what regime existed; what crash risk existed")
permanently.

## 3. Relationship to the Research Layer

The Phase 4A.1 `PredictionOutcomeLedger` (research validation,
`predg.` identity family) records OUTCOME evaluations (Brier/log-loss
against realized labels) and remains authoritative for model
research evidence. The runtime prediction ledger records OPERATIONAL
predictions that trading decisions were made on. Both use
deterministic identity; neither may be rewritten.

## 4. Replay

Prediction ledger entries are deterministic functions of (models,
bars, config): replaying the same run reproduces the identical
prediction sequence (tested via deterministic replay + ledger chain
verification).
