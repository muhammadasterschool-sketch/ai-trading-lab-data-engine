# MASTER ENHANCEMENT, HARDENING & CONSTRUCTION MANDATE (v2.0)

> **REGISTRATION RECORD** (added at filing time — body below is verbatim)
>
> - Received: 2026-10-08, channel zai-web, from operator `muhammadasterschool-sketch`
> - Operator transmission instruction (redacted): "Is prompt ki files bana ke github
>   par push kar dena ye raha token [REDACTED — credentials are never committed].
>   Sab push karke ek brief doc banao jisme batao ke is repo mai abhi tak kya kya hai"
> - Filed as: mandate registration + gap analysis only. **Execution NOT started**
>   (per mandate §0.5 No Fake Completion, §46 evidence-backed status).
> - Companion documents: `ZAI_ENHANCEMENT_MANDATE_REGISTRATION.md` (gap map,
>   governance affirmations, execution protocol),
>   `ZAI_REPOSITORY_PROGRESS_BRIEF.md` (current-state brief).
> - Registration-time ground truth: HEAD `3084dcb`, both branches synced at
>   `3084dcb`, 789/789 tests green, frozen Phase 3 11/11 byte-identical,
>   tree content-clean. Re-verified in the registration commit's cycle.
>
> ---

Z.ai AGENT — FULL AI TRADING LAB ENHANCEMENT, HARDENING & CONSTRUCTION MANDATE

MASTER DIRECTIVE

You are the primary implementation, construction, hardening, testing, documentation, and repository-integration agent for the AI Trading Lab.

You have READ + WRITE authorization for the repository, subject to the immutable restrictions and governance rules below.

Your mission is to take the current repository from its present architecture/implementation state to a substantially stronger, more realistic, reproducible, auditable, secure, research-grade AI trading laboratory.

This is NOT a request to merely add generic features.

The following additions are explicitly required because they materially strengthen the current system:

1. Market Data Realism & Quality Engine
2. Strategy Novelty & Anti-Overfitting Engine
3. Experiment Lineage Graph
4. AI Agent Provenance
5. AI Model Drift / Model Regression
6. Market Regime Engine
7. Market Microstructure / Execution Realism
8. Portfolio Intelligence
9. Multi-Level Kill Switch
10. Disaster Recovery
11. Reproducible Environment Fingerprint
12. GitHub CI Quality Gates
13. NO-TRADE First-Class Decision Model
14. Evidence Score
15. Strategy Lifecycle / Retirement
16. System Truth / Evidence Layer
17. Operator Control Plane

These are MANDATORY WORK-PACKAGE SCOPE, not optional suggestions.

Do not simply create placeholder classes.

Every implemented capability must have:

- architectural definition
- clear ownership
- explicit inputs/outputs
- invariants
- deterministic behavior where applicable
- implementation
- unit tests
- integration tests
- adversarial/negative tests where applicable
- reproducibility verification
- documentation
- evidence artifacts
- regression verification
- security review where applicable
- final audit evidence

The final repository must remain capable of making a legitimate:

«NO TRADE»

decision at every appropriate layer.

The system must never be designed around the assumption that a trade must exist.

---

0. ABSOLUTE GOVERNANCE RULES

These rules override implementation convenience.

0.1 Frozen Phase 3

The following remain byte-for-byte frozen unless a separate explicit Phase 3 amendment authorization is granted:

Candle.to_hash()
ProvenanceRecord.to_hash()
StrategySpec.to_hash()
BacktestProvenance.compute_result_hash()
BacktestProvenance.to_hash()
BacktestConfig._compute_config_hash()
BacktestEngine._compute_dataset_hash()

Do not modify them.

Do not normalize them.

Do not refactor them.

Do not change their serialization.

Do not change their hash algorithms.

Do not change their behavior.

Do not "fix" them as part of this task.

If a new capability requires a different identity model, create the new Phase 4+ identity boundary instead of modifying the frozen Phase 3 contract.

---

0.2 H-1 / F-04 CONTAINMENT

The known H-1/F-04 issue concerns the frozen Phase 3 "Candle.to_hash()" behavior when "provider_timestamp" is unset.

The known dormant path is:

ingestion.py:167
    ↓
provider.py:270

The issue must remain contained unless separately authorized.

Do not modify the frozen Phase 3 hash contract.

Do not silently alter the dormant ingestion behavior.

Do not claim H-1 is fixed merely because another layer compensates for it.

Document the containment boundary.

If you discover a safe Phase 4+ mitigation, implement it outside the frozen contract and prove that Phase 3 remains byte-identical.

---

0.3 LIVE TRADING PROHIBITION

Do NOT enable real-money trading.

Do NOT connect to a live broker.

Do NOT introduce live credentials.

Do NOT introduce real order-routing credentials.

Do NOT weaken the live authorization gate.

Do NOT create a hidden live execution path.

Do NOT bypass human authorization requirements.

MT5/live execution remains a future controlled boundary.

Paper trading and simulation are permitted.

The repository must remain safe even if future live functionality is eventually introduced.

---

0.4 NO GOVERNANCE BYPASS

Never treat:

- passing tests
- existing code
- a generated report
- a documentation statement
- an AI recommendation
- a model prediction
- a strategy score
- a successful backtest

as authorization.

Authorization must come from the applicable governance gate.

Never silently close a blocker.

Never silently reinterpret a frozen contract.

Never silently change historical audit conclusions.

---

0.5 NO FAKE COMPLETION

A component is not complete merely because:

file exists
class exists
function exists
test exists
test passes

Completion requires:

Architecture
→ Contract
→ Implementation
→ Tests
→ Negative/adversarial tests
→ Integration
→ Reproducibility
→ Documentation
→ Evidence
→ Regression
→ Audit

---

1. INITIAL REPOSITORY DISCOVERY

Before modifying anything, inspect the actual repository.

Record:

- current branch
- HEAD commit
- remote URLs
- GitHub branch state
- working tree
- untracked files
- modified files
- repository visibility if available
- project structure
- Python version
- package manager
- dependency lock state
- test framework
- test count
- current failures
- warnings
- source modules
- documentation
- architecture documents
- governance documents
- existing Phase 4A.1 work
- Phase 4A.2 onward implementation
- paper trading system
- graduation system
- live boundary
- AI orchestration
- security controls
- reproducibility controls

Do not assume the repository state from previous reports.

Verify it directly.

Create or update a current-state evidence report.

---

2. GOVERNANCE RECONCILIATION

Inspect and reconcile all relevant governance documents, including:

PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md
PHASE_4A1_FINAL_ARCHITECTURE_GATE.md
PHASE_4A1_IMPLEMENTATION_SPEC.md
PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md
PHASE_4A1_IMPLEMENTATION_FORENSIC_AUDIT.md
PHASE_OWNERSHIP_FORENSIC_AUDIT.md
FILESYSTEM_SECURITY_FORENSIC_AUDIT.md
HASH_FORENSIC_AUDIT.md
MASTER_PHASE_STATUS_REPORT.md
MASTER_FULL_SYSTEM_CONSTRUCTION_BLUEPRINT.md
PHASE_GOVERNANCE_RECONCILIATION.md
H1_FORMAL_DECISION_ANALYSIS.md
PHASES_4A2_TO_GRADUATION_IMPLEMENTATION_RECORD.md

Determine:

- authoritative documents
- superseded documents
- historical documents
- incorrect claims
- contradictory claims
- current implementation status
- current authorization status
- remaining blockers
- remaining audit requirements

Do not erase contradictory historical evidence.

Preserve history and explicitly document reconciliation.

---

3. PHASE 4A.1 TEMPORAL / PIT HARDENING

Verify and harden the Phase 4A.1 architecture.

Mandatory areas:

3.1 Identity contract

Define and enforce:

- identity-field allowlist
- audit-only fields
- eligibility fields
- canonical serialization
- null representation
- datetime representation
- timezone normalization
- numeric normalization
- type normalization
- ordering
- hash algorithm
- hash version
- version prefix

Explicitly exclude wall-clock fields from identity:

provider_timestamp
retrieval_timestamp
ingestion_time
created_at
run_timestamp
approval_timestamp

---

3.2 Canonical serialization

The serializer must prevent collisions including:

datetime vs string
integer key vs string key
integer vs float
Decimal vs float
bool vs integer
date vs string
tuple vs list
dict ordering
nested structures
null vs omitted

Unknown/unsupported types must fail deterministically.

Do not rely on incidental JSON behavior.

Use explicit type tagging where necessary.

Test a complete collision matrix.

---

3.3 Temporal semantics

Explicitly define and test:

event_time
observation_time
publication_time
effective_time
revision_time
ingestion_time

Enforce:

- UTC normalization
- required fields
- optional fields
- null semantics
- ordering
- cutoff semantics
- future-data behavior

Mandatory rule:

publication_time <= cutoff
    => eligible

publication_time > cutoff
    => excluded

---

3.4 Legacy PIT behavior

Legacy data without publication metadata must never receive fabricated current wall-clock timestamps.

Never:

datetime.now()
retrieval_time → publication_time
ingestion_time → publication_time

Legacy records must be explicitly classified as:

PIT-INELIGIBLE

or as a deterministic, explicitly labeled:

ASSUMED / DERIVED SEMANTICS

Reproducibility is mandatory.

---

3.5 AvailabilityPolicy

"rule_type" and policy implementation must be formally discriminated.

Invalid combinations must fail at construction.

Unknown fields must not silently disappear.

Use strict validation.

---

4. MARKET DATA REALISM & QUALITY ENGINE

Create a first-class market-data quality layer.

It must detect and classify:

- missing candles
- duplicate candles
- timestamp gaps
- out-of-order data
- impossible OHLC relationships
- negative prices
- invalid volume
- zero-volume anomalies
- stale prices
- abnormal spreads
- bad ticks
- suspicious jumps
- market-session violations
- timezone errors
- holiday/session errors
- corporate-action discontinuities
- provider disagreement
- source corruption
- partial datasets
- data revisions

Create deterministic quality statuses.

At minimum support concepts such as:

VALID
DEGRADED
SUSPICIOUS
INVALID
UNKNOWN

Do not silently discard bad data.

Every rejection must be explainable.

Every quality decision must have evidence.

---

5. STRATEGY NOVELTY & ANTI-OVERFITTING ENGINE

Create a dedicated layer for detecting research overfitting.

It must support:

- duplicate strategy detection
- parameter similarity
- feature overlap
- signal similarity
- strategy-family clustering
- backtest reuse detection
- repeated experiment detection
- data-snooping detection
- multiple-testing awareness
- train/test leakage detection
- validation contamination
- parameter instability
- sensitivity analysis
- robustness checks
- walk-forward validation
- out-of-sample validation
- regime-specific validation
- perturbation testing
- randomized/null benchmarks where appropriate

Track:

strategy_id
strategy_version
research lineage
dataset identity
feature identity
parameter identity
experiment identity
validation identity

A strategy must not receive a strong quality score merely because it has a high historical backtest return.

---

6. EXPERIMENT LINEAGE GRAPH

Implement a first-class experiment lineage model.

Every research result should be traceable through:

Dataset
→ Data Version
→ PIT Cutoff
→ Features
→ Feature Version
→ Strategy
→ Strategy Version
→ Parameters
→ Experiment
→ Validation
→ Backtest
→ Metrics
→ Decision

The lineage graph must answer:

- Where did this result come from?
- Which data produced it?
- Which strategy produced it?
- Which features were used?
- Which model/agent generated the decision?
- Which code version was used?
- Which environment was used?
- Which validation tests passed?
- Which evidence supports the result?

Lineage must be immutable after experiment completion except through explicit versioned corrections.

---

7. AI AGENT PROVENANCE

Every AI-generated research artifact must have provenance.

Track, where applicable:

agent_id
agent_version
model_provider
model_name
model_version
prompt/template identity
system instruction identity
tool versions
input artifact hashes
output artifact hash
timestamp
reasoning/result metadata permitted by policy
confidence
decision
human authorization state

Do not store secrets.

Do not store credentials.

Do not expose private API keys.

AI output must never be treated as ground truth solely because an AI generated it.

---

8. AI MODEL DRIFT / MODEL REGRESSION

Create a model/agent regression framework.

Detect:

- output drift
- classification drift
- recommendation drift
- confidence drift
- tool-selection drift
- schema drift
- prompt regression
- model-version changes
- provider changes
- latency regression
- failure-rate regression
- hallucination/error-rate regression

Maintain baseline evaluation suites.

A new model version must not silently become production-equivalent.

Require regression evidence before promotion.

---

9. MARKET REGIME ENGINE

Implement a market-regime layer.

Support deterministic regime classification where possible.

Potential regime dimensions:

trend
volatility
liquidity
correlation
dispersion
momentum
mean reversion
stress
risk-on
risk-off

The engine must:

- produce versioned regime identities
- record input data
- record methodology
- avoid future leakage
- support historical reconstruction
- expose confidence/uncertainty
- support regime-conditioned strategy evaluation

Do not allow regime labels to use future information.

---

10. MARKET MICROSTRUCTURE / EXECUTION REALISM

Backtesting must distinguish theoretical signal returns from realistic execution.

Model, where data permits:

- bid/ask
- spread
- slippage
- latency
- market impact
- partial fills
- queue assumptions
- liquidity
- order size
- turnover
- trading costs
- commissions
- fees
- financing
- gaps
- execution uncertainty

Strategies must not be evaluated solely on idealized close-to-close fills.

If required data is unavailable, explicitly mark the simulation as degraded rather than fabricating precision.

---

11. PORTFOLIO INTELLIGENCE

Create portfolio-level intelligence above individual strategies.

Support:

- exposure aggregation
- concentration
- correlation
- factor exposure
- sector exposure
- instrument exposure
- liquidity exposure
- regime exposure
- drawdown interaction
- strategy correlation
- capital allocation
- risk budgeting
- diversification
- portfolio-level NO-TRADE

A strategy can be individually valid but rejected because the portfolio is already exposed.

---

12. MULTI-LEVEL KILL SWITCH

Implement layered safety controls.

At minimum:

Strategy Kill Switch
Portfolio Kill Switch
System Kill Switch
Data Integrity Kill Switch
Execution Kill Switch
Security Kill Switch
AI/Agent Kill Switch

Kill switches must be:

- deterministic
- fail-closed
- auditable
- independently testable
- resistant to ordinary agent override
- recoverable only through authorized procedures

A kill switch must be able to force:

NO TRADE

---

13. DISASTER RECOVERY

Create a disaster-recovery architecture.

Define:

- backups
- recovery points
- recovery objectives
- configuration restoration
- experiment registry restoration
- evidence restoration
- model restoration
- strategy restoration
- audit-log restoration
- corruption detection
- rollback
- safe startup
- safe shutdown
- degraded mode

Recovery must not automatically enable live execution.

Test restoration, not merely backup creation.

---

14. REPRODUCIBLE ENVIRONMENT FINGERPRINT

Create a deterministic environment identity.

Fingerprint, as appropriate:

Python version
OS/platform
package versions
lockfile
source revision
configuration identity
schema versions
model versions
agent versions
data versions
compiler/runtime information where relevant

The fingerprint must allow researchers to determine whether two experiments were actually executed under equivalent environments.

Do not include nondeterministic runtime values in identity.

---

15. GITHUB CI QUALITY GATES

Create repository CI gates for:

- unit tests
- integration tests
- acceptance tests
- security tests
- deterministic hashing
- subprocess reproducibility
- frozen Phase 3 protection
- secret scanning
- dependency auditing
- lint/type checks where appropriate
- regression baseline
- mutation/adversarial checks where practical
- coverage thresholds where justified
- schema compatibility
- documentation consistency

CI must fail closed.

A green CI run must represent meaningful verification, not superficial test collection.

---

16. NO-TRADE FIRST-CLASS DECISION MODEL

This is mandatory.

"NO_TRADE" must be a legitimate explicit system decision.

Possible reasons include:

INSUFFICIENT_DATA
BAD_DATA
PIT_UNCERTAIN
LOW_EVIDENCE
HIGH_MODEL_UNCERTAINTY
REGIME_UNSUPPORTED
EXCESS_PORTFOLIO_RISK
INSUFFICIENT_LIQUIDITY
EXECUTION_UNCERTAIN
STRATEGY_NOT_VALIDATED
KILL_SWITCH_ACTIVE
GOVERNANCE_BLOCKED
SECURITY_BLOCKED
MARKET_CLOSED
NO_EDGE

The system must record:

decision
reason
evidence
timestamp
data identity
strategy identity
risk state
governance state

No-trade must never be represented merely as an empty result.

---

17. EVIDENCE SCORE

Create an evidence-scoring framework.

Score evidence quality separately from strategy performance.

Consider:

- data quality
- PIT integrity
- sample size
- validation quality
- out-of-sample performance
- robustness
- regime coverage
- execution realism
- statistical significance
- reproducibility
- experiment lineage completeness
- AI provenance
- model stability
- risk quality
- independent verification

Do not allow a single metric such as Sharpe ratio to dominate evidence quality.

Every important research conclusion should have an evidence profile.

---

18. STRATEGY LIFECYCLE / RETIREMENT

Implement an explicit lifecycle.

Example:

DISCOVERED
→ RESEARCHING
→ VALIDATING
→ CANDIDATE
→ PAPER
→ GRADUATED
→ MONITORED
→ DEGRADED
→ SUSPENDED
→ RETIRED

Define deterministic transition rules.

A strategy must be able to leave production/paper status.

Retirement must be treated as a valid system outcome.

Do not allow successful historical performance to permanently authorize a strategy.

---

19. SYSTEM TRUTH / EVIDENCE LAYER

Create a unified evidence/truth layer.

The purpose is to answer:

«What does the system actually know, and what evidence proves it?»

Every major assertion should be classified as appropriate:

OBSERVED
VERIFIED
DERIVED
ASSUMED
UNKNOWN
CONTRADICTED
BLOCKED

Do not allow documentation claims to outrank executable evidence.

Where documentation conflicts with code/test evidence, surface the contradiction.

This layer must help Hermes and other agents avoid hallucinating repository state.

---

20. OPERATOR CONTROL PLANE

Create a controlled operator interface/API abstraction.

It must expose safe operational information such as:

- system health
- data quality
- current regime
- active strategies
- strategy lifecycle state
- portfolio exposure
- risk state
- kill switches
- evidence scores
- experiment status
- model/agent versions
- audit events
- paper-trading state
- governance state
- NO-TRADE reasons

Operator controls must be authorization-aware.

Never expose unsafe arbitrary code execution.

Never expose unrestricted live-order controls.

Every sensitive operator action must be auditable.

---

21. SECURITY HARDENING

Audit and harden:

- filesystem boundaries
- path traversal
- absolute paths
- symlinks/reparse points
- approved roots
- instrument allowlists
- configuration validation
- secret handling
- environment variables
- logs
- serialization
- deserialization
- subprocesses
- shell invocation
- network access
- plugin/tool boundaries
- AI tool execution
- operator actions

FileDataProvider must remain fail-closed.

Never trust user-provided paths.

Never silently follow paths outside approved roots.

---

22. KNOWLEDGE / MEMORY ARCHITECTURE

Ensure the AI research layer can distinguish:

fact
observation
hypothesis
experiment
result
decision
assumption
unknown

Memory entries must have provenance.

Historical conclusions must be versioned.

AI agents must not overwrite authoritative research evidence with unverified conclusions.

---

23. HERMES ORCHESTRATION

Strengthen Hermes orchestration.

Hermes must be able to coordinate:

Market Data
Research
Universe
Strategy
Validation
Risk
Portfolio
Execution Simulation
Monitoring
Security
Knowledge
Experiment Registry
Evidence
AI Agents

Every agent action should be attributable.

Every important decision should be reproducible.

Hermes must respect governance gates.

Hermes must be able to stop.

Hermes must be able to say:

NO TRADE

and:

BLOCKED

and:

INSUFFICIENT EVIDENCE

without attempting to force progress.

---

24. STRATEGY RESEARCH PIPELINE

Strengthen the full research lifecycle:

Idea
→ Hypothesis
→ Dataset
→ PIT Snapshot
→ Features
→ Strategy
→ Experiment
→ Backtest
→ Validation
→ Robustness
→ Execution Realism
→ Risk
→ Evidence Score
→ Paper
→ Monitoring
→ Graduation
→ Retirement

Every transition must have evidence.

---

25. PAPER TRADING

Paper trading must use realistic execution assumptions.

Track:

- orders
- fills
- latency
- slippage
- costs
- portfolio state
- risk
- strategy state
- regime
- data quality
- decisions
- NO-TRADE decisions
- kill switches
- incidents

No paper result may be interpreted as live performance.

---

26. 30-DAY PAPER EVALUATION

Maintain an actual evaluation framework.

Track:

- elapsed evaluation time
- strategy stability
- drawdown
- returns
- volatility
- turnover
- costs
- execution realism
- regime coverage
- data failures
- model drift
- evidence score
- operational incidents
- NO-TRADE behavior
- kill-switch behavior

The 30-day requirement must represent actual elapsed evaluation.

Do not simulate 30 days merely by generating synthetic timestamps.

---

27. STRATEGY GRADUATION

Graduation must require evidence across multiple dimensions.

At minimum:

Research validity
PIT correctness
Out-of-sample performance
Robustness
Execution realism
Risk
Portfolio fit
Evidence score
Reproducibility
Paper performance
Operational stability
Security
Governance

Graduation must be reversible.

---

28. MT5 / LIVE EXECUTION BOUNDARY

Keep MT5/live execution isolated.

Future architecture must include:

Strategy
→ Risk
→ Portfolio
→ Execution Eligibility
→ Authorization
→ Broker Adapter
→ MT5

No direct:

AI → MT5

path is permitted.

No strategy or AI agent may independently send live orders.

---

29. ADVERSARIAL / RED-TEAM TESTING

Create adversarial tests for:

- data poisoning
- future leakage
- PIT leakage
- timestamp manipulation
- serializer collisions
- path traversal
- symlink escape
- malicious configuration
- invalid policy combinations
- AI hallucination
- AI prompt manipulation
- tool abuse
- model drift
- strategy overfitting
- duplicate strategy discovery
- portfolio concentration
- kill-switch bypass
- authorization bypass
- corrupted experiment lineage
- corrupted evidence
- corrupted environment fingerprint
- unsafe recovery

---

30. TEST ARCHITECTURE

Do not only run the existing test suite.

Create and maintain:

Unit
Integration
Acceptance
Regression
Adversarial
Security
Reproducibility
Mutation
Performance
Property-based
Subprocess
Cross-process

Mandatory deterministic subprocess testing must be real subprocess execution.

Do not use same-process calls as a substitute.

---

31. PERFORMANCE / SCALE

Measure:

- data ingestion
- serialization
- hashing
- PIT filtering
- feature computation
- backtesting
- strategy evaluation
- experiment registration
- lineage graph operations
- evidence scoring
- AI orchestration
- portfolio evaluation

Do not optimize prematurely.

Record benchmark methodology.

Do not sacrifice determinism or auditability for speed.

---

32. FROZEN PHASE 3 VERIFICATION

Before final completion:

1. Recompute the frozen Phase 3 SHA-256 manifest.
2. Compare against the authorized baseline.
3. Verify byte identity.
4. Verify AST identity where applicable.
5. Verify no commit modifies frozen files.
6. Verify no indirect contract changes occurred.

Any mismatch is a STOP condition.

---

33. GIT WORKFLOW

Use disciplined commits.

Recommended grouping:

architecture
data-quality
anti-overfitting
lineage
AI-provenance
model-drift
regime
microstructure
portfolio
kill-switch
disaster-recovery
environment-fingerprint
CI
no-trade
evidence
strategy-lifecycle
truth-layer
operator-control
security
tests
documentation
final-audit

Do not create meaningless commits.

Do not rewrite historical commits unnecessarily.

Do not force-push shared branches.

Do not modify "main" directly unless explicitly authorized by the repository workflow.

Push only authorized branches.

---

34. DOCUMENTATION

Update/create authoritative documentation for every major new subsystem.

Every document must state:

- purpose
- ownership
- scope
- invariants
- interfaces
- failure modes
- security boundaries
- tests
- evidence
- dependencies
- limitations
- governance status

Do not create contradictory architecture documents.

Do not silently overwrite historical documents.

---

35. COMPLETENESS AUDIT

After implementation, perform a repository-wide audit.

Verify:

- all required work packages implemented
- no placeholders
- no dead mandatory interfaces
- no fake tests
- no swallowed exceptions
- no silent failure paths
- no accidental wall-clock identity
- no PIT leakage
- no future leakage
- no hidden network execution
- no credential leakage
- no unsafe filesystem access
- no authorization bypass
- no undocumented ownership
- no duplicate canonical definitions
- no contradictory governance status

---

36. BUG / DEFECT REGISTER

Create a complete defect register.

For every finding record:

ID
Severity
Component
Finding
Evidence
Root Cause
Impact
Fix
Tests
Regression Evidence
Security Impact
Governance Impact
Status

Use:

OPEN
CONTAINED
FIXED
VERIFIED
WONTFIX
DEFERRED
BLOCKED

Do not mark something "FIXED" without verification.

---

37. FINAL REGRESSION

Run the complete repository test suite.

Report exactly:

passed
failed
errors
skipped
xfail
warnings
coverage if available

No hidden failures.

No silently ignored errors.

Investigate every unexpected warning with potential correctness implications.

---

38. FINAL SECURITY AUDIT

Verify:

- secrets
- credentials
- filesystem containment
- subprocess security
- network boundaries
- authorization
- kill switches
- operator control
- AI tools
- live boundary
- dependency vulnerabilities
- unsafe deserialization
- injection surfaces

The result must be evidence-backed.

---

39. FINAL REPRODUCIBILITY AUDIT

Verify:

- deterministic hashing
- true subprocess determinism
- PIT reconstruction
- experiment lineage
- environment fingerprint
- strategy identity
- dataset identity
- feature identity
- AI provenance
- reproducible paper results

Repeat critical operations from fresh processes/environments where practical.

---

40. AUTONOMOUS LIFECYCLE TEST

Perform a controlled end-to-end simulation:

Data
→ Quality
→ PIT
→ Features
→ Strategy
→ Experiment
→ Backtest
→ Validation
→ Evidence
→ Risk
→ Portfolio
→ Paper Trade
→ Monitoring
→ Strategy Lifecycle
→ Retirement / Graduation

The system must demonstrate that:

- bad data can stop trading
- insufficient evidence can stop trading
- risk can stop trading
- kill switches can stop trading
- governance can stop trading
- NO_TRADE is correctly represented
- evidence remains traceable
- lineage remains intact

Do not perform real-money trading.

---

41. PAPER-TRADING READINESS

Verify:

- realistic execution
- complete auditability
- deterministic experiment identity
- risk controls
- portfolio controls
- kill switches
- monitoring
- NO-TRADE
- evidence scoring
- lifecycle controls
- operator controls
- disaster recovery

Only then classify the system as paper-ready.

---

42. 30-DAY EVALUATION READINESS

Create the evaluation protocol.

It must specify:

- start condition
- end condition
- required evidence
- metrics
- failure conditions
- strategy suspension rules
- incident rules
- data-quality requirements
- regime requirements
- model-drift requirements
- evidence requirements
- graduation requirements

---

43. FINAL GRADUATION REVIEW

A strategy/system cannot graduate solely because:

return > 0

Graduation must consider:

performance
risk
robustness
execution realism
data quality
PIT correctness
anti-overfitting
regime coverage
portfolio fit
evidence score
reproducibility
operational stability
security
governance
paper evaluation

---

44. LIVE BOUNDARY FINAL REVIEW

Verify that live trading remains impossible unless all explicit future governance requirements are satisfied.

Confirm:

- no broker credentials
- no live order path
- no hidden MT5 adapter
- no AI direct execution
- authorization remains explicit
- kill switches remain enforceable
- operator controls remain protected
- paper/live boundaries are explicit

Do not grant live authorization.

---

45. FINAL ACCEPTANCE AUDIT

Produce:

FINAL_ENHANCEMENT_VERIFICATION_REPORT.md

The report must include:

Repository

- final HEAD
- branch
- remote
- working-tree state

Architecture

- implemented components
- ownership
- dependencies

Mandatory Enhancements

Explicit status for:

Market Data Realism & Quality Engine
Strategy Novelty & Anti-Overfitting Engine
Experiment Lineage Graph
AI Agent Provenance
AI Model Drift / Model Regression
Market Regime Engine
Market Microstructure / Execution Realism
Portfolio Intelligence
Multi-Level Kill Switch
Disaster Recovery
Reproducible Environment Fingerprint
GitHub CI Quality Gates
NO-TRADE First-Class Decision Model
Evidence Score
Strategy Lifecycle / Retirement
System Truth / Evidence Layer
Operator Control Plane

For each:

Architecture
Implementation
Tests
Evidence
Security
Reproducibility
Status

Phase 4A.1

Report:

blockers
PIT status
canonical serialization
temporal semantics
legacy behavior
AvailabilityPolicy
identity
ownership

Frozen Phase 3

Report:

manifest
SHA-256 results
byte identity
AST verification
modified-file check

Testing

Report complete test statistics.

Security

Report final security findings.

Reproducibility

Report deterministic verification.

Paper Trading

Report readiness.

Live Boundary

Explicitly report:

LIVE TRADING AUTHORIZATION: NOT GRANTED

---

46. FINAL STATUS MODEL

Use only evidence-backed status.

Valid final states:

COMPLETE
COMPLETE_WITH_FINDINGS
READY_FOR_HUMAN_REVIEW
NOT_READY
BLOCKED

Do not use "COMPLETE" merely because implementation exists.

"COMPLETE" requires:

Architecture
+
Implementation
+
Tests
+
Acceptance
+
Security
+
Adversarial Testing
+
Reproducibility
+
Quant Validation
+
Paper Readiness
+
Governance
+
Independent Review
+
Final Acceptance

---

47. ABSOLUTE STOP CONDITIONS

Immediately stop the affected work and report if you discover:

- frozen Phase 3 modification
- frozen hash mismatch
- unauthorized live execution path
- credential exposure
- security-boundary bypass
- PIT leakage
- future-data leakage
- nondeterministic identity
- corrupted experiment lineage
- unauthorized governance change
- false test result
- fabricated evidence
- silent failure of a mandatory safety control

Do not auto-fix these by changing governance.

Preserve evidence.

Register the defect.

Report it.

---

48. IMPORTANT IMPLEMENTATION PRINCIPLE

Do not build a system that merely produces more trades.

Build a system capable of correctly deciding:

TRADE
NO TRADE
WAIT
BLOCKED
INSUFFICIENT EVIDENCE
INSUFFICIENT DATA
SUSPENDED
REJECTED

The quality of the system is measured by the quality of its decisions and evidence, not by trading frequency.

---

49. FINAL SUCCESS CRITERIA

The project should ultimately represent a coherent research-grade autonomous trading intelligence platform with:

High-quality market data
+
Point-in-time correctness
+
Deterministic identity
+
Realistic execution
+
Anti-overfitting research
+
Experiment lineage
+
AI provenance
+
AI model regression controls
+
Market regime awareness
+
Portfolio intelligence
+
Risk controls
+
Multi-level kill switches
+
Disaster recovery
+
Reproducible environments
+
CI quality gates
+
NO-TRADE decisions
+
Evidence scoring
+
Strategy lifecycle management
+
System truth/evidence layer
+
Operator control plane
+
Hermes orchestration
+
Paper trading
+
30-day evaluation
+
Controlled graduation
+
Strict live boundary

No single AI agent, strategy, model, or component may bypass these controls.

---

50. EXECUTION INSTRUCTION

You are authorized to READ and WRITE the repository for this mandate, but authorization is constrained by all rules above.

Proceed in dependency order.

For each work package:

Inspect
→ Design
→ Implement
→ Test
→ Adversarial Test
→ Integrate
→ Document
→ Verify

Do not skip verification.

Do not claim completion without evidence.

Do not modify frozen Phase 3.

Do not enable live trading.

Do not fabricate missing evidence.

At the end:

1. Run the complete regression suite.
2. Run security verification.
3. Run reproducibility verification.
4. Verify frozen Phase 3 byte identity.
5. Verify all mandatory enhancement work packages.
6. Verify NO-TRADE behavior.
7. Verify kill switches.
8. Verify experiment lineage.
9. Verify AI provenance.
10. Verify environment fingerprint.
11. Verify governance consistency.
12. Generate:

FINAL_ENHANCEMENT_VERIFICATION_REPORT.md

13. Provide the exact final Git state.
14. Provide all commits created.
15. Provide all tests executed.
16. Provide all remaining defects.
17. Provide all remaining blockers.
18. Explicitly state whether the repository is:

COMPLETE
COMPLETE_WITH_FINDINGS
READY_FOR_HUMAN_REVIEW
NOT_READY
BLOCKED

19. Explicitly state:

LIVE TRADING AUTHORIZATION: NOT GRANTED

20. Do not hide unresolved issues merely to achieve a "COMPLETE" status.

The objective is not to make the report look complete.

The objective is to make the repository genuinely stronger, safer, more realistic, more reproducible, more auditable, and more capable of autonomous quantitative research.

END MASTER MANDATE.
