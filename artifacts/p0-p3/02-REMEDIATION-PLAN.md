# P0-P3 PRIORITIZED REMEDIATION PLAN

Status after this task: every CONFIRMED SOFTWARE defect is FIXED AND
VERIFIED (FIX-9 … FIX-14, each with regression tests). What remains
splits into (a) owner-side provisioning (external to code) and (b)
non-blocking hardening backlog. **No software blocker remains open.**

## 1. Blockers that remain (owner-side provisioning only)

These are readiness gates that no code change can satisfy — they are
the reason the final decision stays `BLOCKED — DO NOT START PAPER
TRADING`:

1. **GOVERNANCE_READY (GOV-03/04/05).** Record the human decisions
   (credential-rotation confirmation, keyed-MAC provisioning record,
   data-source approval) AND sign them with the new operator approval
   key (FIX-9) so the evidence is machine-verifiable. Owner action
   checklist §1.
2. **OPERATIONAL_FEED_READY.** Provision a genuine, human-approved
   market feed for exactly the instruments in the support matrix
   (currently the Binance public spot pilot: BTCUSDT spot), with
   source approval in the prediction source registry, freshness and
   warm-up validated through `feed_gate`/`feed_composition`. Owner
   action checklist §2.
3. **REAL_DATA_READY.** Out of scope for this task (historical
   datasets excluded); remains FALSE and tracked separately by
   `docs/READINESS_EVIDENCE_INVENTORY.md` + GOV-HDD-001.
4. **The separately authorized 30-day soak.** Preflight machinery is
   now executable (`data-engine soak-preflight`); the soak itself
   still requires the owner's explicit start authorization
   (PAPER-SOAK-PROCEDURE.md §1.1).

## 2. Non-blocking hardening backlog (recommended, not required)

| # | Item | Rationale | Suggested order |
|---|---|---|---|
| H-1 | Operator signing tooling: a small documented script (outside the engine) that records + signs `OperatorApprovalRecord`s from interactive prompts | Makes FIX-9 approvals ergonomic for the owner | before first authorized soak |
| H-2 | Windows host validation run (real Windows machine or CI windows runner) of: install.ps1 → run-tests.ps1 → run-paper.ps1 refusal paths | Converts "NOT VERIFIED" Windows markers into tested claims (or removes Windows from the supported matrix) | optional, before any Windows deployment |
| H-3 | Ensemble persistence/loader story for real deployments (today the operator supplies an importable factory; a pinned-artifact loader would strengthen BLOCKER-21 provenance) | Production ergonomics | after first soak decision |
| H-4 | Extend trusted-evidence requirement to ALL operator-recorded evidence (currently the 26 non-human recorded gates remain operator-attested text; component gates are first-hand verified and override) | Defense in depth beyond the prompt's human-gate requirement | post-soak hardening |
| H-5 | Provider-mode launch smoke against the real Binance public endpoint (read-only market data, paper execution) under an owner-approved source record | Converts the adapter pilot into operational-feed evidence | with owner action §2 |

## 3. What was completed this task (for the record)

P0 (safety & truthfulness): FIX-9 evidence trust boundary, FIX-10
real session wiring, FIX-11 report reconciliation. P1 (operational
dependencies): FIX-12 Windows import discipline, FIX-13 deployment
script hardening; feed/instrument/governance honesty verified, gates
correctly FALSE. P2/P3: FIX-14 soak preflight + dry run; CI verified;
documentation reconciled to executable output. Historical/backtest
work excluded throughout.
