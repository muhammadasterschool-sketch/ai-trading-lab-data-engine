# AI Trading Lab — Data Engine
## Repository Progress Brief

> One-page orientation: what exists in this repository today, how it got here,
> and what remains. Generated 2026-10-08 after the final governance-docs push.

| | |
|---|---|
| **Remote** | https://github.com/muhammadasterschool-sketch/ai-trading-lab-data-engine |
| **HEAD** | `018d084` — `main` and `phase-4a/4a1-architecture-correction` (in sync) |
| **Test suite** | **789 passed** (deterministic; verified 3x) |
| **Overall status** | READY_WITH_FINDINGS — construction complete, evaluation phase gated |

---

## 1. What this repository is

A **point-in-time (PIT) multi-asset market data engine** and strategy research
platform for systematic trading research, built governance-first: frozen Phase 3
strategy contracts, fail-closed filesystem security, hash-chained audit trails,
human-only authorization gates, and a live-trading boundary that is **never
authorized by design**. The Python package `data_engine` (src-layout, uv-managed)
covers the full research lifecycle: data ingestion → PIT views → feature
computation → backtesting → research validation → risk control → paper trading
→ governed evaluation and graduation.

## 2. Construction timeline (in order)

| Stage | Scope | Commits | Suite |
|---|---|---|---|
| Phases 0–3 (baseline, inherited) | Core engine, ingestion, PIT serialization/hashing, **frozen strategy engine** (11 blobs byte-pinned) | pre-`df44d27` | 465 |
| Phase 4A.1 remediation | 8/8 architecture blockers closed | `665a9d5..e7505d3` (9) | 563 |
| Phases 4A.2 → graduation | Corporate actions, derivatives, research gov, registry, features, validation, risk, hermes, infra, paper trading, graduation layer | `0ce78f6..a7fba96` (12) | 692 |
| Master-mandate cycle | Strategy discovery, knowledge/memory, benchmarks, end-to-end lifecycle test | `0cafbb4..281dfdc` (5) | 789 |
| Governance docs (CR-10) | 10 audit/governance reports committed into repo | `018d084` (1) | 789 |
| This brief | Consolidated progress summary | this commit | 789 |

## 3. What was built, phase by phase

**Phase 4A.1 — architecture correction (8/8 blockers CLOSED).** Canonical
type-tagged serialization (`pit/serialization.py`), identity/eligibility hashing
with prohibited-field enforcement (`pit/hashing.py`), temporal-semantics and
policy validators, six new PIT modules (sidecar, revision chain, tiebreaker,
instrument primitives, PIT view/builder, experiment identity), filesystem
containment security layer with hash-chained audit trail, re-established
implementation record, and 95 mandated acceptance identifiers as named tests
plus a 15/15 mutation detection gate.

**Phases 4A.2–4A.4.** Corporate-action engine (splits/dividends, announcement ≤
effective semantics, as-of universes), derivatives package (futures contracts,
rollover detection, continuous series with roll-leakage protection), research
governance with structural no-self-approval.

**Phases 5–11.** Experiment registry (duplicate-identity rejection,
reproducibility verdicts), PIT feature pipeline (slice-then-compute), research
validation (bias/leakage/overfitting detectors, walk-forward, robustness),
risk engine (hard limits, kill switch, hash-chained violations, exposure),
hermes agent-permission layer (structurally-unavailable permissions, audited
rejections), infra (reproducibility RNG detector, phantom-proof metrics,
tamper-fail-closed checkpoints), paper trading (realism simulator with
latency/spread/impact, gateway, side-aware positions, three-way
reconciliation).

**Graduation layer.** 30-day evaluation rule (structural, from provided
timestamps), human-only token registry (starts empty), graduation/retirement
flows, and `LiveAuthorizationGate` — deny-by-default, 4-condition conjunctive,
machine principals refused. **Live execution is modeled but never grantable
without an explicit human token the blueprint never issues.**

**Master-mandate cycle.** Strategy discovery (`discovery/` — candidates,
identity allowlists, fail-closed grids, validated-only registry,
execution-eligibility chain defaulting to NO TRADE), knowledge/memory layer
(`knowledge/` — 5 record classes, authoritative-source filtering, content
addressing, bounded memory), performance benchmarks (`benchmarks/` — 10 real
component surfaces, timing-excluded hashes), and a full 15-stage end-to-end
lifecycle test ending in a governed REJECTION with NO TRADE at 10 boundaries.

## 4. Current verified state (all gates green at `018d084`)

- **789/789 tests pass** — deterministic across repeated runs, cache disabled.
- **Frozen Phase 3 intact**: 11/11 strategy blobs byte-identical to `13fdc7e`;
  SUB-18 manifest 13/13 sha256 pins match.
- **Secret scan**: 0 hits across 200 tracked files; 0 secrets in full history.
- **Mutation gate**: 15/15 reintroduced defects detected.
- **Cross-process identity**: `disc20.` / `know42.` / `bmk30.` hashes stable
  across fresh OS processes.
- **Security**: no network/MT5/broker code in `src`; filesystem containment
  fail-closed; zero untracked artifacts; working tree clean.

## 5. Open items (honest register — see `ZAI_DEFECT_REGISTER.md`)

| ID | Severity | State | Summary |
|---|---|---|---|
| H-1 / F-04 | HIGH | **OPEN / CONTAINED** | `Candle.to_hash()` non-deterministic when `provider_timestamp` unset; dormant path (zero active callers); Phase 4 identity prohibited from using it at 3 layers. Human ratification of containment pending. |
| F-11 | MEDIUM | registered | `QuantEngine` does not merge `IndicatorSpec.parameters` defaults — bare `sma` yields all-None; pre-parameterized names (`sma20`, `rsi14`) work. |
| — | 4 MEDIUM + 8 LOW | registered | Counting nuances, CRLF decision recorded-not-acted, stale blueprint status lines. |

**Gated (not defects):** 30-day paper-trading evaluation not yet started (no
candidates exist yet); external review windows (GPT re-audit, Claude fix
window) not dispatched; final human acceptance pending.

## 6. Repository layout

```
src/data_engine/
  pit/            serialization, hashing, views, sidecars, revisions (4A.1)
  strategy/       FROZEN Phase 3 engine (backtest, equity, execution, ledger…)
  actions/        corporate actions (4A.2)      derivatives/ (4A.3)
  research/       human-only approvals (4A.4)   experiment_registry/ (5)
  quant/          PIT features (6)              research_validation/ (7)
  risk/           limits, kill switch (8)       hermes/ agent perms (9)
  infra/          reproducibility, metrics (10) paper/ simulator, eval (11)
  discovery/      strategy candidates (mandate) knowledge/ records (mandate)
  benchmarks/     performance surfaces (mandate)
tests/            789 tests incl. test_pit_view.py (95 IDs) + lifecycle
docs/             engine design docs
*.md (root)       60+ governance/audit/implementation records
```

## 7. What comes next

1. **Start the 30-day paper-trading evaluation** once a strategy candidate is
   validated and registered (rule is structural and already implemented).
2. **Dispatch external review windows** — GPT re-audit and Claude fix window
   (F-11 and the 4 MEDIUM findings are queued for the fix window).
3. **Ratify H-1 containment** — human decision on `PHASE_GOVERNANCE_
   RECONCILIATION.md` recommendation (Option A: containment, no Phase 3
   amendment).
4. **Final human acceptance** → graduation decision. Live execution remains
   never-authorized without an explicit human-issued token.

## 8. Key documents in this repository

`MASTER_FULL_SYSTEM_CONSTRUCTION_BLUEPRINT.md` (authority) ·
`PHASE_4A1_IMPLEMENTATION_RECORD.md` ·
`PHASES_4A2_TO_GRADUATION_IMPLEMENTATION_RECORD.md` ·
`PHASES_DISCOVERY_TO_AUTONOMY_IMPLEMENTATION_RECORD.md` ·
`ZAI_CURRENT_REPOSITORY_STATE.md` · `PHASE_GOVERNANCE_RECONCILIATION.md` ·
`H1_FORMAL_DECISION_ANALYSIS.md` · `ZAI_DEFECT_REGISTER.md` ·
`ZAI_WEEK_END_FULL_FORENSIC_INSPECTION.md` ·
`FINAL_FULL_REPOSITORY_FORENSIC_AUDIT.md` ·
`AI_TRADING_LAB_FINAL_ACCEPTANCE_AUDIT.md`
