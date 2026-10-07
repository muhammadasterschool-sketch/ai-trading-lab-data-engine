# PHASES 4A.2 THROUGH GRADUATION — IMPLEMENTATION RECORD

**Record ID:** PHASES_4A2_TO_GRADUATION_IMPLEMENTATION_RECORD
**Implementing agent:** ZAI (controlled implementation agent)
**Date:** 2026-10-07 (PKT)
**Branch:** `phase-4a/4a1-architecture-correction` (local commits; operator pushes)
**Predecessor record:** `PHASE_4A1_IMPLEMENTATION_RECORD.md` (4A.1 closure @ `e7505d3`)
**Governing roadmap:** `MASTER_FULL_SYSTEM_CONSTRUCTION_BLUEPRINT.md` §2 (Complete Roadmap) and §5.11–5.60

---

## 1. AUTHORIZATION

Operator session directives (2026-10-07, quoted):

> "Ok continue and make all the phases left after that we will push all the commits at once in the repo"

This authorizes implementation of every MISSING phase listed in the
blueprint roadmap — 4A.2, 4A.3, 4A.4, 5, 6 (completion), 7, 8, 9, 10,
11, 30-Day Evaluation, Strategy Graduation/Retirement — following the
same evidence-per-commit discipline as the 4A.1 remediation cycle.

**Explicit exclusion honored:** the roadmap marks *Live Execution
Boundary* as `NEVER AUTHORIZED / OUT_OF_SCOPE`. This cycle did NOT
implement live trading. What it implemented is the **boundary gate**
(blueprint 5.59): `LiveAuthorizationGate` DENIES by default; a grant
requires a human-issued token from a registry that starts EMPTY and
refuses machine principals at issue time. The blueprint itself never
issues the token, so the boundary cannot be crossed from inside the
system.

---

## 2. PHASE-BY-PHASE DELIVERY

| # | Phase | Commit | Package / modules | Tests |
|---|-------|--------|-------------------|-------|
| 1 | 4A.2 Corporate Actions / Universe / Calendar (5.11–5.13) | `0ce78f6` | `actions/{models,chain,universe,calendar}.py` | 29 |
| 2 | 4A.3 Futures / Rollover / Continuous (5.14) | `83f260e` | `derivatives/{models,rollover,continuous}.py` | 14 |
| 3 | 4A.4 Research Governance (5.15) | `1725390` | `research/governance.py` | 7 |
| 4 | 5 Experiment Registry (5.16) | `ce05d7e` | `experiment_registry/registry.py` | 7 |
| 5 | 6 Feature Engineering (5.21) | `9df890d` | `quant/features.py` | 6 |
| 6 | 7 Validation Suite (5.24–5.27) | `822cbeb` | `research_validation/{bias,statistical,walk_forward,robustness}.py` | 17 |
| 7 | 8 Risk / Exposure / Portfolio (5.28–5.31) | `006d826` | `risk/{engine,portfolio}.py` | 11 |
| 8 | 9 Hermes Orchestration (5.35–5.41) | `a45dc0e` | `hermes/{providers,contracts,orchestrator}.py` | 9 |
| 9 | 10 Production Infra (5.47–5.50) | `cc9ea6b` | `infra/observability.py` | 8 |
| 10 | 11 Paper Trading (5.51, 5.55) | `4d49149` | `paper/{models,simulator,gateway}.py` | 10 |
| 11 | 11+ Evaluation / Graduation / Retirement / Live Boundary (5.56–5.59) | `5eaf51e` | `paper/evaluation.py` | 11 |
| 12 | Facade + this record | (this commit) | `__init__.py`, this file | — |

Every commit landed with a green suite. Frozen Phase 3 `strategy/*`
blobs untouched throughout (verified in §4).

---

## 3. INVARIANT HIGHLIGHTS (per blueprint domain)

**4A.2 (5.11–5.13).** Corporate actions: discriminated union with PIT
chronology guard (announcement <= effective) and `ca42.` identities.
AdjustmentChain: original series never mutated (history preserved,
hash-pinned); `FutureActionError` on applying an action not yet
announced (look-ahead is a blocker-grade defect). PointInTimeUniverse:
survivorship-bias-free `constituents(as_of)`; retro-effective events
invisible until announcement; deterministic `uni42.` snapshots.
TradingCalendar: the authorized 4A.2 expansion of the 4A.1
`CalendarRef` identity reference (INV-06 scope guard respected — 4A.1
shipped reference-only); IANA validation, UTC session bounds,
fail-closed on non-trading days; calendar-owned `periods_per_year`
(the frozen Phase 3 `metrics.periods_per_year` dict is untouched and
remains valid for its 365-day forex case).

**4A.3 (5.14).** Contracts and continuous series are distinct entities
(distinct identity families). `RollDecision` enforces
`decision_time <= effective_time` structurally (leakage
unrepresentable). Volume/open-interest crosses decide on bars present
in BOTH series (observable when made). Continuous stitching: the roll
bar pair must exist ON the roll date — closes from later dates are
future data and raise `RollLeakageError`.

**4A.4 (5.15).** Approval is EXTERNAL metadata. NO-SELF-APPROVAL is
structural: submitter != approver AND approver must be HUMAN
(machine approvers rejected at construction). Registry: append-only,
duplicate-rejecting, ghost-approval-rejecting, hash-verified reads;
unapproved research is visible but never in `approved_only()`.

**Phase 5 (5.16).** Registry keyed by the 4A.1 deterministic
experiment identity; duplicate identity = the same experiment, cannot
register twice. ReproducibilityLog: environment pins, input/output
hashes, MATCH/MISMATCH/UNVERIFIED verdicts; empty log = UNVERIFIED
(never silently assumed reproducible).

**Phase 6 (5.21).** FeaturePipeline slices candles to
`timestamp <= as_of` BEFORE computing (features structurally
incapable of referencing future data); `feat6.` identity covers specs
+ cutoff + input hash; warm-up values stay None.

**Phase 7 (5.24–5.27).** Deterministic statistics without scipy:
Student-t CDF via regularized incomplete beta (Lentz), t-quantile by
bisection; degenerate samples raise (no fake p-values). Bonferroni +
Benjamini-Hochberg step-up. Walk-forward windows disjoint/ordered/
embargoed BY CONSTRUCTION; defense-in-depth re-validation (future-test
intrusion rejected; rolling past overlap legitimate). Robustness:
bounded sweeps, per-axis plateau detection, regime sign-consistency.

**Phase 8 (5.28–5.31).** Hard limits with ZERO override path: every
breach raises AND records to a hash-chained log; kill switch trips on
breach (production posture) and refuses all evaluation until
externally reset. Portfolio: inverse-volatility allocation with the
limit gauntlet as a PRECONDITION (constraint satisfaction before
return).

**Phase 9 (5.35–5.41).** Agent contracts with STRUCTURALLY UNAVAILABLE
permissions (live trading, blocker closure, frozen-contract
modification, self-approval — the constructor rejects them).
Free-first ModelRouter with deterministic test provider (cross-process
stable). Hermes coordinates but never executes; dispatch rejections
are AUDITED, not raised; hash-chained audit log. Zero network
capability in package.

**Phase 10 (5.47–5.50).** ReproducibilityVerifier (N-run output
hashing; hidden randomness raises). Phantom metric series forbidden.
Hash-chained logs and audit trails. Checkpoint restore verifies the
content hash BEFORE applying (tamper fails closed).

**Phase 11 (5.51, 5.55).** NO real money, NO broker credentials —
structurally: orders carry no account/auth fields and `extra=forbid`
enforces the surface. Market realism: spread, commission,
deterministic impact slippage, latency (market orders fill at the NEXT
bar's open — no look-ahead fills), participation cap rejects oversized
orders. Three-way reconciliation by exact replay; discrepancies raise.

**Evaluation/Graduation/Boundary (5.56–5.59).** The 30-day rule is
structural (window < 30 days => INCOMPLETE; measured from provided
timestamps, never wall clock). Graduation requires BOTH a complete
evaluation AND a verified human token. The live boundary DENIES by
default; grants require human token + evaluation + graduation +
production attestation; the token registry starts empty and refuses
machine principals — the blueprint never issues it.

---

## 4. FORENSIC VERIFICATION AT CYCLE EXIT

| Check | Method | Result |
|-------|--------|--------|
| Full regression | `uv run pytest -q` | **692 passed** (563 at 4A.1 exit + 129 new) |
| Determinism | 3 consecutive full-suite runs | identical (692/692/692) |
| Frozen Phase 3 blobs | `git rev-parse` vs `13fdc7e` | **11/11 strategy blobs byte-identical** |
| SUB-18 manifest | `sha256sum -c` over the 13-file manifest | 13/13 OK |
| Secret scan | credential-pattern scan over all tracked files | 0 hits |
| Untracked artifacts | `git ls-files --others --exclude-standard` | empty |
| Working tree | `git status --porcelain` | clean |

---

## 5. HONEST LIMITATIONS

1. **Same-agent implementation + verification.** As in the 4A.1
   cycle, the verification layer (tests, gates, this record) was
   produced by the same agent that implemented. The named-test
   matrices, determinism runs, and hash checks are the independent
   evidence substitutes available in this environment; an external
   review remains the operator's prerogative after push.
2. **Phases 9 and 10 are deterministic cores, not deployments.**
   Hermes ships agent contracts, routing, orchestration, and audit —
   with a deterministic test provider and NO network adapter (the
   production LLM adapter is an operator-environment concern).
   Production data infrastructure (Phase 10) ships reproducibility,
   observability, monitoring, and recovery primitives — not live data
   feeds. The roadmap's "Production Data Infra" as deployed infra
   requires operator-owned environment work outside this codebase.
3. **Paper trading is a simulator, not a market.** Realism is
   parameterized and deterministic; real market microstructure is
   approximated (half-spread + impact), not replicated.
4. **Broker abstraction / MT5 (5.52/5.53) intentionally deferred.**
   These domains sit on the far side of the live boundary and are
   pointless (and unsafe) to build before the boundary itself; the
   boundary gate is delivered, the adapters are not.

---

## 6. REGRESSION BASELINE — DECLARED

| Epoch | Suite | Measurement |
|-------|------:|-------------|
| Phase 3 freeze (`main@13fdc7e`) | 367 | historical declaration (§4 of the 4A.1 record) |
| 4A.1 exit (`e7505d3`) | 563 | measured, ×3 determinism |
| **This cycle exit** | **692** | measured, ×3 determinism |

The 129-test delta is this cycle's authorized addition (129 new named
tests across 11 phase test files). No existing test was modified or
removed in this cycle.
