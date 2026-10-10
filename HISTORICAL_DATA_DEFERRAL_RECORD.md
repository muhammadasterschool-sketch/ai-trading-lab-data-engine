# HISTORICAL DATA DEFERRAL RECORD

**Document ID:** GOV-HDD-001 · **Version:** 1.0.0 · **Date:** 2026-10-10
**Status:** CURRENT — operator decision recorded; long-term
historical-data acquisition is DEFERRED and OUT OF SCOPE for the
2026-10-10 implementation cycle.
**Implements:** operator mandate 2026-10-10 §1.1 + §2; referenced by
`src/data_engine/runtime/feed_gate.py`
(`RESEARCH_HISTORY_DECISION_ID`) and the 32-gate readiness set's
research-history/operational-feed distinction.

---

## 1. Operator Decision (verbatim evidence)

> "Long-term historical market-data acquisition is DEFERRED. Do not
> acquire the 20-year historical dataset during this implementation
> cycle. Do not fabricate, relabel, or promote synthetic data to
> genuine historical data."

> "Treat long-term historical-data acquisition as DEFERRED and OUT OF
> SCOPE for this cycle. […] Keep every existing synthetic dataset
> correctly labelled. Preserve honest provenance and data-quality
> reporting. Separate long-term historical backtesting requirements
> from the minimum current genuine market-feed requirements needed by
> the paper-trading runtime."

```text
Decision ID:     GOV-HDD-001
Decision:        DEFER long-term historical market-data acquisition
                 (the 20-year research corpus); separate it from the
                 minimum operational market-feed requirement.
Approver:        The repository operator (human principal)
Approver kind:   human (in-session operator authorization)
Channel:         zai-web (IM session web-a816f89a-8d02-42d6-b1a7-
                 6577eb1dc53e, chat 218858c8-6142-48a8-b177-
                 8668467ef6c4)
Recorded at:     2026-10-10 (PKT)
Executed by:     ZAI (controlled agent) — recording only.
```

## 2. What This Means (precise semantics)

1. **DEFERRED, not satisfied.** No historical-data requirement is
   claimed met. `VERIFIED_YEARS` remains honestly computed (currently
   0.0); the four supplied CSV datasets remain classified SYNTHETIC
   from hard fabrication evidence; no promotion, relabel, or repair
   occurs.
2. **Separation, not bypass.** The deferral does NOT weaken any data
   safety gate. Per the operator's own instruction, "VERIFIED_YEARS =
   0" is not permission to bypass data gates: the readiness gate set
   was extended (31 → 32) with `OPERATIONAL_FEED_READY` — a NEW,
   fail-closed gate covering the MINIMUM current genuine market-feed
   requirement (human-approved source with production-ingestion scope,
   validated bars, freshness, correct instrument mapping, indicator
   warm-up sufficiency — `src/data_engine/runtime/feed_gate.py`).
3. **Two distinct requirements, tracked separately from now on:**

   | Requirement | Nature | Status | Where tracked |
   |---|---|---|---|
   | Long-term research history (≥ 5 verified years for empirical claims; the 20-year corpus) | Research/backtest evidence | **DEFERRED by this record** — never reported satisfied, never an activation requirement | `RealDataReadiness.report()` (VERIFIED_YEARS), prediction-layer INSUFFICIENT rule, this record |
   | Minimum operational market feed (current, genuine, validated, fresh, mapped, warm-up sufficient) | Paper-session runtime input | **OPEN — no human-approved source / no genuine feed provisioned yet** | `OPERATIONAL_FEED_READY` gate (32nd mandatory gate) |

4. **Existing evidence preserved.** The dataset manifests under
   `data/manifests/`, the SYNTHETIC classification evidence, and the
   eligibility blocks on all 20 registered instruments are unchanged.

## 3. Analysis Recorded This Cycle (operator §2 instruction)

The authoritative specifications were inspected before implementing
the distinction (`docs/PAPER_READINESS_GATE.md`,
`REAL_DATA_READINESS_CONTRACT.md`,
`PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md`, runtime
`data_gate.py`/`readiness.py`). Finding: the REAL_DATA_READY gate
machinery itself requires ≥ 1 REAL_VERIFIED dataset through the
nine-stage chain — with no coverage minimum of its own — but the
documented path to satisfy it (contract §5 + policy §7.2 acceptance
template, "Coverage: >= 5.0 minimum") de facto gated paper activation
on the long-term research corpus. That is the conflation the operator
directed be removed: **the paper runtime needs a current genuine feed
plus indicator warm-up, not a research corpus.** The narrow,
specification-compliant distinction implemented:

- `OPERATIONAL_FEED_READY` (new mandatory gate) — the minimum
  operational feed requirement above;
- research history stays tracked by `RealDataReadiness` /
  VERIFIED_YEARS / this deferral record — explicitly NOT an activation
  requirement while deferred, and never claimed satisfied.

The strategy itself does NOT structurally require the 20-year corpus
to operate a paper session: the runtime consumes live bars plus its
lookback warm-up window. What it cannot do without real data is
produce RESEARCH-GRADE empirical claims (backtest evidence, strategy
validation graduation) — those remain honestly blocked by the deferral.

## 4. What Unblocks What

- **Paper-trading activation** requires, inter alia, the operational
  feed: an operator SRC-APPROVAL record for a genuine current-feed
  source (policy §7.1 format) + the provisioned feed passing
  `evaluate_operational_feed` + a REAL_VERIFIED dataset record for the
  feed window through the nine-stage chain. None of that is
  historical-data acquisition of the deferred kind; none of it exists
  yet — the gate honestly reads FALSE.
- **Research/empirical claims** additionally require the deferred
  long-term corpus (≥ 5 verified years) — unchanged, honest, out of
  scope this cycle.
