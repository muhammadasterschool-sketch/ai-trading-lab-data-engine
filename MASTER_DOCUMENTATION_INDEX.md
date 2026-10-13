# MASTER DOCUMENTATION INDEX

> **Single source of truth for repository documentation.**
> Every documentation artifact in this repository is classified here by
> phase ownership, authority, status, and supersession relationship.

```text
Document Type:  Master documentation index (SSOT)
Phase:          Cross-phase (all phases)
Authority:      A — AUTHORITATIVE (this index is the documentation map of record)
Status:         CURRENT
Version:        2.24.0
Last Updated:   2026-10-13 (Batch 19 — per-user VPS and
                 operational deployment, design + validated
                 templates: docs/PER_USER_VPS_DEPLOYMENT.md +
                 deploy/systemd/ai-trading-lab@.service +
                 deploy/config/secrets.env.example +
                 scripts/validate_deployment_templates.py +
                 docs/reports/BATCH_19_VPS_DEPLOYMENT.md on dedicated
                 branch feat/batch-19-vps-deployment from af3e303;
                 NO deployment performed (no VPS provisioned, no
                 billable infrastructure, no public exposure, no
                 production credentials — externally-verified outcomes
                 = NONE, honestly separated from simulated design and
                 locally-tested validation); per-user VPS model (one
                 unprivileged instance per user — logical tenancy +
                 physical isolation); 20 validator-pinned hardening
                 keys (aitl-%i no-shell account, NoNewPrivileges,
                 ProtectSystem=strict, IPAddressDeny=any +
                 IPAddressAllow=localhost, MemoryMax/CPUQuota/TasksMax,
                 Restart=on-failure, SIGTERM safe stop); secrets via
                 root-owned 0600 EnvironmentFile names-only (never
                 values/command-history/logs); honest 32-gate
                 readiness + Type=exec + fail-closed startup; backup/
                 restore via tested runtime recovery protocol; NTP
                 prerequisite + RUN-ST-1 feed watchdog; loopback-only
                 default network posture (public exposure = explicit
                 operator TLS/proxy decision); git-versioned templates
                 + SHA-pinned rollback; validator VERIFIED in agent
                 environment 6/6 PASS (20/20 unit keys, no
                 credential-shaped values, secret-named entries empty,
                 6/6 spec sections, simulated/local/external
                 separation); NO gate verdict changed — 29 PASS / 3
                 FAIL, PAPER_READY = FALSE, LIVE NOT AUTHORIZED;
                 Prior 2.23.0 — Batch 18 — Windows installer and
                 application packaging, scaffold with honest
                 verification markers: docs/WINDOWS_INSTALLER_AND_
                 PACKAGING.md + scripts/windows_smoke_test.py +
                 docs/reports/BATCH_18_WINDOWS_PACKAGING.md on
                 dedicated branch feat/batch-18-windows-packaging from
                 40bde4b; scope determined honestly — platform-
                 independent Python engine (wheel py3-none-any), MT5
                 data-plane the only Windows element, signed installer
                 exe = operator product decision (signing keys via
                 secure external processes); reproducible build
                 VERIFIED (uv build: wheel 689,373B SHA256
                 93cd883a…95ea7c0 + sdist 569,496B SHA256
                 284e2a9b…f95eebe; dist/ gitignored — binaries never
                 committed); packaging spec delivered (per-user venv
                 procedure, FS-01..06-contained data dirs, secrets
                 never packaged env-var-only + redaction, fail-closed
                 startup errors + dashboard safe shutdown,
                 upgrade/rollback/backup/uninstall, per-item honest
                 verification-status table); smoke test 7 fail-closed
                 checks (import/version, PAPER_READY fabrication
                 structurally refused, REAL execution mode refused,
                 7 venues MOCK_DETERMINISTIC, dashboard loopback
                 default + ephemeral bind + safe shutdown) — logic
                 VERIFIED in agent env 7/7 PASS, Windows-host execution
                 NOT VERIFIED (operator runs and records — no
                 Windows-host claim anywhere); honest LOW finding:
                 pyproject/lock 0.1.0 vs data_engine.__version__ 0.3.0
                 build-provenance mismatch (lock-frozen + test-pinned,
                 deferred to operator review); NO gate verdict changed
                 — 29 PASS / 3 FAIL, PAPER_READY = FALSE, LIVE NOT
                 AUTHORIZED;
                 Prior 2.22.0 — Batch 17 — security, multi-tenancy and
                 private access, audit + two verified-gap
                 closures: docs/reports/BATCH_17_SECURITY_TENANCY_
                 PRIVATE_ACCESS_AUDIT.md + NEW docs/LICENSING_PRIVATE_
                 DISTRIBUTION_BOUNDARY.md + opt-in dependency
                 vulnerability scanning appended to .github/workflows/
                 ci.yml on dedicated branch
                 audit/batch-17-security-tenancy-private-access from
                 51c08ed; 12 mandate areas audited first-hand — auth
                 (tenant binding at auth time, client tenant IDs
                 never trusted), ownership boundaries, cross-user
                 mutual invisibility, secret vault (SHA-256
                 fingerprints, REDACTED placeholder never storable,
                 redacted repr, duplicate refusal, reveal needs
                 ALLOWING decision, cross-tenant reveal refused;
                 rotation = documented operator procedure, no
                 dedicated API — classified honestly), short-lived
                 sessions + loopback read-only dashboard + mobile
                 no-write/no-order-path, append-only audited decisions
                 + values-never-in-audit, frozen extra=forbid configs
                 + fail-closed defaults + secret-free CI (contents:
                 read, no pull_request_target), admin restrictions
                 (control-plane boundary, ARCH-F1 unprivileged reset
                 refused), 46 negative tests green; GAP CLOSED:
                 audit-dependencies CI job (workflow_dispatch ONLY —
                 existing push/PR CI bit-for-bit unchanged; pip-audit
                 --strict fail-closed over the full locked export;
                 honestly NOT VERIFIED locally — no network/scanner
                 offline, operator must trigger after the pending
                 push); C-5 CLOSED: licensing/private-distribution
                 boundary (license-state gating implemented +
                 test-pinned with explicit DENY-never-silent failure
                 semantics; commercial entitlement deliberately NOT
                 built — operator product decision; NO DRM, NO
                 user-data collection, NO legal-compliance claim;
                 signing keys/credentials/IdP = secure external
                 processes only); NO gate verdict changed — 29 PASS /
                 3 FAIL, PAPER_READY = FALSE, LIVE NOT AUTHORIZED;
                 Prior 2.21.0 — Batch 16 — paper-execution & risk
                 assurance audit, READ-ONLY:
                 docs/reports/BATCH_16_PAPER_EXECUTION_RISK_
                 ASSURANCE_AUDIT.md created on dedicated branch
                 audit/batch-16-paper-execution-risk-assurance from
                 c9c722d; authoritative paper-runtime order path
                 audited against the mandate's 10 requirement areas —
                 ALL PASS first-hand: risk-budget position sizing
                 (quantity = risk_budget/stop_distance, zero-qty
                 refusal, max units cap), true account equity
                 (RUN-EQ-1 double-count guard at runtime.py:2276/:2985),
                 RUN-RL-1 true daily-loss limit with fail-closed anchor
                 establishment, RUN-DD-1 account-equity drawdown,
                 identity-bound risk decision + limit gauntlet, kill
                 switch FILL-time enforcement + terminal HALT + restart
                 survival, deterministic SL/TP over bars (exits.py),
                 partial-fill accounting + exactly-once shared fill
                 path + PARTIALLY_FILLED→EXPIRED, terminal states with
                 loud refusals + idempotency, recovery verdicts + 9
                 hash-chained ledgers + deterministic replay, cost
                 model (half-spread adverse fills + per-unit commission
                 + slippage/spread cost fields + max_spread_fraction
                 guard; financing NOT modeled and NOT required by the
                 frozen spec — documented boundary), one-account session
                 binding + deny-default tenancy, signal→execution
                 ledgered traceability incl. NO_TRADE; ZERO verified
                 gaps → no invented tests (existing negative suites
                 enumerated); suite 2,333+1 (79.14s at base), frozen
                 11/11, manifest 13/13, secret scan 0 across 86
                 commits; NO gate verdict changed — 29 PASS / 3 FAIL,
                 PAPER_READY = FALSE, LIVE NOT AUTHORIZED;
                 Prior 2.20.0 — Batch 15 — broker adapter &
                 execution contract audit + venue/catalog
                 completion, audit + verified-gap
                 implementation: docs/reports/BATCH_15_BROKER_
                 ADAPTER_EXECUTION_CONTRACT_AUDIT.md + two NEW
                 generated artifacts docs/reports/BROKER_CAPABILITY_
                 MATRIX.md + docs/reports/INSTRUMENT_CATALOG_REPORT.md
                 on dedicated branch
                 feat/batch-15-venue-catalog-completion from 1f2c689;
                 per-venue status matrix delivered (7 venues ALL
                 MOCK-ONLY with first-hand anchors — auth/secret
                 boundary, discovery/normalization, capability
                 validation at session boundary, order lifecycle,
                 rate limits/retries/reconnects/reconciliation,
                 native error codes); Batch 11 §9 confirmed items
                 CLOSED: C-1 Exness/XM dedicated MT5-class mock
                 adapters (subclass seams preserve mt5-mock behavior
                 exactly; descriptors exness-mock/xm-mock registered —
                 registry now 7 venues; Standard-account instruments
                 EURUSD/XAUUSD/BTCUSD; per-account operator
                 verification boundary documented), C-2 deterministic
                 instrument-catalog report artifact (5 canonical
                 identities, merged venue mappings ALL UNVERIFIED,
                 fail-closed behaviors referenced, known limitations
                 honest), C-3 broker capability matrix artifact;
                 generator scripts/generate_broker_catalog_artifacts.py
                 (fixed timestamp — byte-identical regeneration);
                 tests: RED-first 33 Exness/XM venue tests (import-RED
                 verified), 13 artifact byte-pin tests, shared contract
                 suite strengthened 5→7 venues, registry pin 5→7;
                 full suite 2,233+1 → 2,333+1 (+100, ZERO regressions,
                 79.44s); frozen 11/11, manifest 13/13, secret scan 0
                 across 85 commits; NO gate verdict changed — 29 PASS /
                 3 FAIL, PAPER_READY = FALSE, LIVE NOT AUTHORIZED;
                 Prior 2.19.0 — Batch 14 — market-data readiness
                 audit + initial state baseline, READ-ONLY:
                 docs/reports/BATCH_14_MARKET_DATA_READINESS_
                 AUDIT.md created on dedicated branch
                 audit/batch-14-market-data-readiness-audit from
                 e781a9b; real starting state established
                 first-hand — Batch 11 verified exact (branch
                 e781a9b clean, ancestry d49b822 → 30ff1ce →
                 7f76c0e → e0e0cee → e781a9b, deliverables via
                 ls-tree), Batch 12/13 reports ABSENT (never
                 executed — superseded per the dynamic
                 remaining-batch rule: confirmed scope absorbed
                 into Batch 15); suite 2,233 + 1 skipped
                 (78.61s) — exact baseline match, zero
                 regressions; frozen 11/11, manifest 13/13,
                 secret scan 0 across 84 commits + tree;
                 dependency map delivered (completed reuse
                 list, 7 code-addressable items C-1..C-7,
                 external blockers B11-R-01..05/13, operator
                 decisions B11-R-11/12); market-data audit
                 8/8 requirement areas PASS at honest
                 classification (provider contracts, UTC
                 timestamp semantics, duplicate/ordering/gap/
                 stale fail-closed, provenance, 248 focused
                 deterministic tests incl. provider-failure
                 mapping, quality/coverage measurement, explicit
                 real-provider boundary — binance-public-spot
                 public-only credentials-refused, feed sources
                 UNVETTED human-approval-only) — ZERO new
                 code-addressable market-data gaps; NO gate
                 verdict changed — 29 PASS / 3 FAIL, PAPER_READY
                 = FALSE, LIVE NOT AUTHORIZED;
                 Prior 2.18.0 — Batch 11 — complete remaining-work
                 audit, READ-ONLY:
                 docs/reports/BATCH_11_COMPLETE_REMAINING_WORK_
                 AUDIT.md created on dedicated branch
                 audit/batch-11-remaining-work-audit from e0e0cee;
                 repository truth verified first-hand (ancestry main
                 d49b822 → 30ff1ce → 7f76c0e → e0e0cee exact, clean
                 tree, Batch 9/10 deliverables present via ls-tree;
                 remote unchanged unauthenticated — main d49b822,
                 batch branches absent, pushes still blocked on
                 credential rotation, exposures #19–#22 unrevoked);
                 suite 2,233 + 1 skipped ×2 deterministic
                 (79.57/81.65s); frozen 11/11, manifest 13/13,
                 secret scan 0 across all 83 commits + working
                 tree; 13-area runtime audit ALL PASS at honest
                 classification — ZERO new code-addressable safety
                 defects; platform requirements reviewed: Windows
                 installer NOT IMPLEMENTED/NOT SPECIFIED, licensing
                 PARTIAL (security-level gating only), per-user VPS
                 deployment EXTERNAL, read-only dashboard core
                 IMPLEMENTED (loopback, 13 tests) with mobile
                 accessibility EXTERNAL; duplicate work NONE (plane
                 separations intentional); 13-item remaining-issues
                 register (B11-R-01..13) with severity/files/
                 acceptance criteria/required tests; recommendation:
                 re-scope Batch 12 (zero confirmed code-addressable
                 safety gaps) toward Batch 13 venue/catalog work
                 (Exness + XM adapters absent; instrument-catalog
                 report + capability matrix artifacts missing); NO
                 gate verdict changed — 29 PASS / 3 FAIL unchanged,
                 PAPER_READY = FALSE, LIVE NOT AUTHORIZED;
                 Prior 2.17.0 — Batch 10 — post-rotation remote
                 reconciliation & release governance:
                 docs/reports/BATCH_10_POST_ROTATION_REMOTE_
                 RECONCILIATION.md created on dedicated branch
                 audit/batch-10-post-rotation-reconciliation from
                 7f76c0e; credential posture verified FIRST-HAND —
                 no replacement credential exists in the agent
                 environment (no helper, no stored file, no CLI, no
                 env token, clean remote URL), so the Batch 9 push
                 remains BLOCKED and NO authenticated operation was
                 attempted (fail-closed); remote reconciled
                 unauthenticated: main d49b822 unchanged, Batch 9
                 branch NOT present remotely, PR heads 7f384e6/
                 d945833 open and unmerged; CI verified GREEN through
                 the public read-only REST API for ALL current heads
                 — main d49b822 (runs 38039475901/38039475525, 4/4
                 legs), PR #1 head 7f384e6 (run 38293840380, 2/2
                 legs), PR #2 head d945833 (run 38242367378, 2/2
                 legs); all 6 repository workflow runs success;
                 both PRs mergeable=true mergeable_state=clean, PR #2
                 strictly contains PR #1; evidence inventory
                 GOV-REI-001 v1.0.0 → v1.1.0 — GOV-06 UNVERIFIED →
                 PASS on verified API evidence, GOV-03 FAIL kept with
                 the first-hand credential-absence finding, no
                 fabrication; suite 2,233 + 1 skipped ×3
                 deterministic (79.64/80.07/80.00s), 244 focused,
                 frozen 11/11, manifest 13/13, secret scan 0 across
                 all 82 commits; NO gate verdict changed — 29 PASS /
                 3 FAIL unchanged, PAPER_READY = FALSE, LIVE NOT
                 AUTHORIZED; recommended merge decisions recorded
                 (advisory only — nothing merged);
                 Prior 2.16.0 — Batch 9 — release readiness, evidence
                 tracking & safe integration audit:
                 docs/READINESS_EVIDENCE_INVENTORY.md (GOV-REI-001
                 v1.0.0) created on dedicated branch
                 audit/batch-9-release-readiness-evidence from 30ff1ce
                 — documentation-only per-evidence-item inventory for
                 the THREE unresolved gates (REAL_DATA_READY
                 RDR-01..06, OPERATIONAL_FEED_READY OFR-01..06,
                 GOVERNANCE_READY GOV-01..06): closed status
                 vocabulary PASS/FAIL/UNVERIFIED, evidence classes
                 that separate verified evidence from operator
                 assertions, evidence references, owners,
                 timestamps, expiry rules, explicit unresolved
                 reasons and next operator actions; 8 binding
                 integrity rules (missing evidence never converts to
                 PASS; registration is not eligibility;
                 REAL_UNVERIFIED is not REAL_VERIFIED; mock is not
                 real broker; no secrets; frozen contracts
                 preserved); pinned by 18 RED-first structural tests
                 (tests/test_readiness_evidence_inventory.py —
                 adversarially verified: a FAIL-to-PASS item flip and
                 a PAPER_READY fabrication are both caught);
                 repository truth verified UNAUTHENTICATED (no
                 credential exists or was used; main d49b822
                 unchanged; PRs #1/#2 open unmerged; CI on current
                 heads UNVERIFIED — REST API 403 rate-limited);
                 suite 2,233 + 1 skipped ×3 deterministic
                 (80.41/80.48/80.00s), 244 focused, frozen 11/11,
                 manifest 13/13, secret scan 0 across all 81
                 commits (count-only output); NO gate changed —
                 29 PASS / 3 FAIL unchanged, PAPER_READY = FALSE;
                 remote push BLOCKED on PAT rotation confirmation
                 (exposure 19); Batch 9 report at
                 docs/reports/BATCH_9_RELEASE_READINESS_EVIDENCE_
                 AUDIT.md)
                 Prior 2.15.0 — Batch 8 — independent runtime audit:
                 docs/reports/BATCH_8_INDEPENDENT_RUNTIME_AUDIT.md
                 created on dedicated branch
                 audit/batch-8-independent-runtime-audit from 4237151;
                 every Batch 5–7 claim re-established FIRST-HAND:
                 commits 39e7939/4237151 resolved + diffed; remote
                 heads verified == local tips via authenticated
                 ls-remote (Batches 2–7 all pushed; PRs #1/#2 open,
                 CI on current heads NOT VERIFIED — session PAT is
                 git-scope-only, API 401); baseline reproduced
                 exactly (2,215 + 1 skipped ×3 deterministic,
                 80.52/81.08/81.22s); authoritative execution path,
                 Batch 6 controls (ST-1/CA-1/PM-1/OBS-1/DA-1/DD-1 +
                 snapshot compat) and Batch 7 discovery/catalog all
                 VERIFIED in code + 141 focused tests; frozen 11/11 +
                 manifest 13/13; CI-equivalent secret scan 0 hits
                 across ALL history (6 stricter-heuristic hits are
                 the intentional mock redaction fixture); ZERO
                 reproducible defects → zero fixes (two suspicions
                 refuted by evidence: workflow YAML valid at byte
                 level — display artifact; heuristic-scan hits are
                 test constants); PAPER_READY = FALSE unchanged —
                 BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY; PAT exposure
                 #19 flagged for rotation)
                 Prior 2.14.0 — Batch 7 (instrument-discovery
                 mandate cycle): Bitget mock venue + broker
                 instrument discovery/catalog/platform-registry sync on
                 continuous branch
                 feat/runtime-risk-broker-neutral-tenancy (from
                 39e7939, tree clean, baseline re-verified
                 first-hand: 2,167 + 1 skipped): BitgetSpotMockAdapter
                 + BITGET_MOCK_CAPABILITIES (the FIFTH deterministic
                 mock venue — the Phase-1 discovery audit's broker
                 matrix had recorded Bitget as entirely unimplemented;
                 MARKET/LIMIT only; SL/TP as separate trigger/plan
                 orders; clientOrderId native idempotency;
                 balances-only spot account; trade filters with
                 minTradeUSDT-class minimum notional; representative
                 v2 native codes preserved for audit, re-verified
                 when a real-adapter phase is authorized;
                 MOCK_DETERMINISTIC enforced, REAL modes structurally
                 refused; joins the SHARED parametrized contract
                 suite); brokers/instruments.py — discover_instruments
                 → immutable InstrumentCatalog (fail-closed:
                 disconnected adapter refuses, foreign specs refuse,
                 duplicate venue symbols refuse, capability DRIFT
                 against the registry refuses, entries snapshot the
                 venue descriptor at discovery time) +
                 sync_catalog_to_platform_registry → canonical
                 identities with broker:<id> provider-symbol mappings
                 in the CENTRAL platform InstrumentRegistry
                 (registration ≠ eligibility — synced instruments
                 land DISCOVERED, the sync never touches data state/
                 verification/eligibility; the same canonical
                 instrument from a second venue merges provider
                 mappings into ONE record; broker mappings start
                 UNVERIFIED); +48 tests (21 new + 27 shared-contract
                 newly parametrized over bitget-mock; one inventory
                 pin updated four→five mocks — documented
                 strengthening, zero assertions weakened); suite
                 2,215 + 1 skipped ×3 deterministic (80.3/81.0/
                 80.4s); frozen 11/11; manifest 13/13;
                 real-credential scan 0 on changed files; architecture
                 doc §6c v1.3.0; readiness report §0M v2.14.0;
                 verdict UNCHANGED PAPER_READY = FALSE, LIVE NOT
                 AUTHORIZED; no real Bitget adapter, no market-data
                 provider, no trading permission claimed.
                 Batch 6 — safety residuals (see readiness §0L):
                 RUN-ST-1 in-session wall-clock feed watchdog
                 (RuntimeConfig.max_feed_staleness_seconds,
                 Optional[StrictInt], default None = disabled for
                 deterministic-replay compatibility — an operational
                 live-clock session OPTS IN; a stale bar is still
                 ADMITTED (fills/TTL/drawdown/protection/persistence
                 continue) but the prediction/decision/entry chain
                 is SKIPPED fail-closed with a deterministic
                 FEED_STALE_BLOCK incident + feed_stale_bars
                 counter; injectable wall_clock seam; the bridge's
                 external-order risk context derives the honest
                 wall-clock bar age so data_staleness fails closed
                 on a stalled feed), RUN-CA-1 operator APIs
                 (operator_cancel_order — live orders only, real
                 OMS transition pair + venue boundary, ledgered +
                 counted + persisted immediately, refused in the §28
                 ambiguity states; operator_close_position — RUNNING
                 submits a MANUAL_CLOSE order through the AUTHORITATIVE
                 gate→OMS path settling on later bars, HALTED settles
                 IMMEDIATELY at the latest admitted bar through the
                 one authoritative fill path with every live order
                 for the symbol cancelled first — the post-HALT
                 frozen-protection escape hatch; risk failures are
                 LOUD refusals naming the failed checks), RUN-PM-1
                 (partial_fill_events re-queries the live OMS order —
                 the completing fill is no longer counted), RUN-DA-1
                 (dead _entry_orders_by_symbol removed), RUN-OBS-1
                 (exit-path risk rejections surfaced in
                 BarOutcome.risk_failed_checks); SNAPSHOT CONFIG
                 COMPATIBILITY (§0H limitation closed): the ordered
                 SNAPSHOT_CONFIG_EVOLUTION registry +
                 allow_snapshot_config_evolution opt-in — a digest
                 mismatch that decomposes EXACTLY into documented
                 additive schema evolution refuses by DEFAULT with
                 a precise actionable message and resumes under the
                 explicit operator opt-in with a ledgered
                 SNAPSHOT_CONFIG_EVOLVED incident; shared-field
                 changes always refuse; new snapshots persist
                 identity["config"] for exact future decomposition;
                 EXECUTION_STATE_SCHEMA 1.1.0 unchanged); +34
                 RED-first acceptance tests; suite 2,167 + 1 skipped
                 ×3 deterministic (77.8/77.7/77.7s); frozen 11/11;
                 manifest 13/13; real-credential scan 0 on changed
                 files; readiness report §0L v2.13.0 + operator
                 runbook operator-API documentation; verdict
                 UNCHANGED PAPER_READY = FALSE, LIVE NOT AUTHORIZED.
                 Batch 2 — RUN-DD-1 account-equity drawdown limit
                 CLOSED on continuous branch
                 feat/runtime-risk-broker-neutral-tenancy (from
                 82f46d9): baseline re-verified first-hand (2,025
                 + 1 skipped, 55.57s); new mandatory risk-gate
                 check `account_drawdown` (21→22 checks; unknown
                 fails closed; strict breach refuses entries;
                 closing-order carve-out preserved);
                 RuntimeConfig.max_account_drawdown_fraction
                 (default 0.20, validated (0,1]); mark-to-market
                 peak replayed deterministically from persisted
                 bars+fills (no new persisted field — restart-
                 stable); per-bar enforcement trips the ACCOUNT
                 kill switch (ledgered breach incident, auditable
                 source runtime.risk.drawdown, terminal HALT,
                 persists immediately, restart refuses to clear);
                 in-flight remainders frozen; +14 RED-first
                 acceptance tests; suite 2,039 + 1 skipped ×3
                 deterministic; frozen 11/11; secret scan 0; two
                 fixture sites declare the new mandatory input
                 (zero assertions weakened); readiness report
                 §0H v2.9.0; verdict UNCHANGED PAPER_READY =
                 FALSE, LIVE NOT AUTHORIZED. Batch 3 same cycle:
                 broker-neutral runtime integration Phase M2
                 DELIVERED as the side-band bridge
                 src/data_engine/runtime/broker_execution.py —
                 BrokerSession governed by the runtime's REAL
                 RiskGate (22 checks incl. account drawdown) +
                 KillSwitchManager, executing through the runtime's
                 own PaperExecutionAdapter fill model over admitted
                 bars; runtime order path UNTOUCHED (side-band);
                 +22 tests (lifecycle/partial fills/resting LIMIT/
                 cancel/central-gate governance/idempotency incl.
                 restart/timeout retry/UNKNOWN reconcile/unsupported
                 kinds/isolation/§32 divergence/phantom/side-band
                 preservation); suite 2,061 + 1 skipped; architecture
                 doc v1.1.0 §6a with explicit remaining adapter work
                 (M3-M6 NOT STARTED, no real broker claimed);
                 readiness report §0I v2.10.0; verdict UNCHANGED.
                 Batch 4 same cycle: multi-user security FOUNDATION
                 delivered as src/data_engine/tenancy/ (tenant
                 identity + approval/license lifecycle, short-lived
                 principals, server-side authoritative resource
                 ownership registry, deny-by-default authorization
                 with tenant-from-authenticated-context-only rule
                 (mismatching client claims denied + audited as
                 incidents), control-plane boundary (admin roles
                 structurally denied tenant trading data), mobile
                 READ_ONLY role with no order-placement path,
                 per-tenant secret vault contract (gated reveals,
                 redacted reprs, values never in audit), per-user
                 provisioning CONTRACT with dry-run-only provisioner
                 (execute refused by design); +46 security tests;
                 suite 2,107 + 1 skipped; design authority
                 docs/MULTI_USER_TENANCY_SECURITY_FOUNDATION.md
                 v1.0.0 with threat model + explicit non-claims (no
                 production multi-tenancy, no public API, no real
                 infra, no mobile app); readiness report §0J
                 v2.11.0; verdict UNCHANGED. Batch 5 same
                 mandate: Phase M2 COMPLETED as the AUTHORITATIVE
                 broker-neutral runtime integration —
                 attach_authoritative_paper_venue binds a guarded
                 BrokerSession ONTO the runtime's single order path
                 (entries AND protective exits; no hidden
                 direct-execution fallback; live pre-venue internal
                 orders refuse the attachment); the session's risk
                 gate is the identity-binding verification of the
                 OMS's RT-F1 fingerprint-bound approval (venue
                 client_order_id == OMS order id); fills come
                 exclusively from venue polls hosting the runtime's
                 own PaperExecutionAdapter (venue-mode runs
                 BIT-IDENTICAL to internal-mode runs); kill-switch
                 fill-time enforcement and the exit risk-reduction
                 carve-out traverse the same boundary; exactly-once
                 fill accounting; UNKNOWN ambiguity blocks everything
                 until ledgered reconciliation adopts venue truth
                 (never an inferred failure; restart-in-ambiguity
                 stays fail-closed); venue book rebuilt on restart
                 with deterministic-regeneration verification (split
                 run == whole run); precision enforcement
                 distinguishes price vs quantity (refusals ledgered
                 with the dimension named); new
                 BrokerSession.adopt_venue_order is the explicit
                 ledgered lost-ack recovery action; +26 RED-first
                 tests; suite 2,133 + 1 skipped ×3 deterministic;
                 frozen 11/11; secret scan 0; architecture doc §6b
                 v1.2.0; readiness report §0K v2.12.0; verdict
                 UNCHANGED. Also this cycle:
                 full-platform discovery mandate cycle:
                 Phase 1 audit delivered on branch
                 fix/ingestion-classification-fail-closed (from d945833):
                 baseline re-verified first-hand (2,005 + 1 skipped,
                 56.51s); six confirmed ingestion/validation
                 classification defects CLOSED with 20 RED-first
                 regression tests — ING-NAT-1 (unparseable timestamps
                 silently REAL_UNVERIFIED, NaT rows counted valid),
                 ING-VOL-1 (negative volume invisible), ING-COL-1
                 (schema mismatch not consulted; KeyError → contract
                 error), VAL-ORDER-1 (out-of-order WARNING→INVALID,
                 one incidental fixture corrected + documented),
                 ING-STALE-1 (both evidence scripts silently ingested
                 stale data/raw copies over new sources — now loud
                 refusals exit 1/2), ING-NVIEW-1 (swallowed normalized-
                 view failures still returned exit 0 — now FATAL exit
                 3); audit columns field records original file columns;
                 suite 2,025 + 1 skipped ×3 deterministic; frozen 11/11;
                 secret scan 0; committed dataset classifications
                 verified UNCHANGED under the hardened audit (read-only,
                 no manifests regenerated); new A-class audit record
                 PHASE_1_DISCOVERY_AUDIT_REPORT.md v1.0.0 (access/
                 branch/PR/CI verification, stack map, safety-chain
                 status, product-gap matrix, broker support matrix —
                 Bitget unimplemented, no production adapter claimed,
                 Phases 2–7 roadmap with acceptance criteria) +
                 readiness report §0G v2.8.0; verdict UNCHANGED
                 PAPER_READY = FALSE, LIVE NOT AUTHORIZED; push blocked
                 on operator credential — exact commands in audit §9;
                 multi-broker architecture mandate cycle:
                 broker-neutral execution layer Phase M1 DELIVERED on
                 branch feat/broker-neutral-execution-architecture (from
                 1c286d2) — new `src/data_engine/brokers/` package:
                 normalized models (STOP/STOP_LIMIT, TIF, UNKNOWN status,
                 instrument precision/lot/notional specs), typed error
                 taxonomy preserving venue-native codes, coherence-
                 validated capability registry (REAL execution modes
                 REFUSED at registration), credential redaction boundary,
                 BrokerAdapter interface + guarded BrokerSession
                 (injectable risk/kill-switch gates — absent gate refuses
                 everything; journal-backed idempotency across restarts;
                 bounded deterministic retry; UNKNOWN degradation with
                 reconciliation-only recovery); four DETERMINISTIC MOCK
                 adapters (paper / MT5-style Exness-XM-class / Binance-
                 spot-style / Bybit-v5-style — zero network, zero real
                 credentials, zero real orders); +236 tests incl. the
                 central-gate independence proof parametrized over all
                 four brokers; baseline re-verified FIRST at 1c286d2
                 (1,769 + 1 skipped, 55.30s) then 2,005 + 1 skipped
                 (54.76s) — zero regressions, zero existing tests
                 modified, frozen 11/11 untouched, secret scan 0; design
                 authority docs/MULTI_BROKER_EXECUTION_ARCHITECTURE.md
                 v1.0.0 with capability matrix + risk-ordered phases
                 M2–M6 all NOT STARTED; verdict UNCHANGED PAPER_READY =
                 FALSE, LIVE NOT AUTHORIZED; kill-switch enforcement
                 audit cycle:
                 baseline re-verified first-hand at efd92c1 (suite
                 1,762 + 1 skipped ×2, frozen 11/11, no tests
                 weakened — 1 modified test is the documented F-24
                 strengthening) + full order-path trace with exact
                 file/function references + three audit-confirmed
                 enforcement bypasses CLOSED on branch
                 fix/paper-runtime-killswitch-fill-enforcement:
                 RUN-KS-1/RUN-KS-2 (in-flight orders filled after a
                 SYMBOL/ORDER-scope kill-switch trip — fill-time
                 enforcement now cancels them, ledgered
                 ORDER_CANCELLED_KILL_SWITCH) + RUN-HALT-1 (persisted
                 HALTED resumed RUNNING on restart — now restores as
                 terminal HALTED); +7 acceptance tests (4 RED pre-fix
                 + 3 behaviour pins), suite 1,769 + 1 skipped ×2,
                 zero regressions, frozen untouched, secret scan 0;
                 exit-order carve-out preserved; readiness report §0E
                 v2.6.0; verdict UNCHANGED PAPER_READY = FALSE;
                 2026-10-12 next-execution mandate cycle: Phase A–C
                 re-verification (PR #1/CI/data/baseline 1,755 + 1
                 skipped ×2, frozen 11/11, secret scan 0) + Phase C
                 source-inspected blocker register (RUN-EQ-1/RL-1/DD-1/
                 ST-1/CA-1/PM-1/DA-1) + Phase D controlled fix
                 PAPER-RUN-PNL-1 CLOSED on branch
                 fix/paper-runtime-pnl-correctness (equity costs counted
                 exactly once + TRUE daily loss limit with deterministic
                 UTC-day anchor; +7 acceptance tests, suite 1,762 + 1
                 skipped ×2, zero regressions, frozen untouched);
                 readiness report §0D v2.5.0; verdict UNCHANGED
                 PAPER_READY = FALSE; 2026-10-12 paper-readiness
                 engineering cycle: readiness report §0C v2.4.0 — real
                 provider package (Binance public klines adapter + forex
                 rate-series separation + transport layer), feed
                 composition into the 32nd gate, UNVETTED source
                 candidates + blocked markets, +70 regression tests
                 (suite 1,755 + 1 skipped), operator source-approval pack
                 + runbook registered; verdict UNCHANGED PAPER_READY =
                 FALSE)
Supersedes:     none (first canonical index)
Superseded By:  —
Source Evidence: doc_discovery.py inventory (80 pre-existing docs), reference
                 graph (199 referrer files scanned), git log, PHASE_GOVERNANCE_
                 RECONCILIATION.md authority matrix
```

**Authority classification vocabulary** (normalization mandate §7):
- **A** — AUTHORITATIVE (current governing specification)
- **B** — CURRENT SUPPORTING (current, subordinate)
- **C** — AUDIT EVIDENCE (produced by audit/verification activity)
- **D** — HISTORICAL (retained to preserve project history)
- **E** — SUPERSEDED (no longer authoritative, retained for traceability)
- **F** — INCORRECT/CONTRADICTORY HISTORICAL CLAIM (preserved, corrected by
  supersession notices / the contradiction register)

**Naming decision (recorded per mandate §6):** No existing document was
renamed. Rationale: (1) `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md`,
`PHASE_4A1_IMPLEMENTATION_RECORD.md`, `docs/strategy_engine_design.md`, and
`tests/AUDIT_REPORT.md` are referenced by **source code and tests**
(`src/data_engine/pit/hashing.py`, `tests/test_pit.py`, `tests/test_pit_view.py`,
`tests/test_strategy.py`) — renaming them would require modifying runtime
code/tests, which the mandate forbids (§1.1, §15, §25 STOP condition);
(2) every historical document carries 2–27 inbound prose references forming
the forensic evidence chain — renaming would sever traceability cited in
commit messages and audit trails (§6); (3) §6 explicitly authorizes
preserving originals and creating clearly identified canonical/current
documents instead — **this index is that canonical document.** New documents
created from 2026-10-08 onward follow the mandate §4/§5 naming standards.

---

## Phase 0 — Foundation / Evidence

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASE_0_EVIDENCE_REAUDIT.md` | C | Historical | Phase 0 evidence re-audit (pre-4A.1 baseline verification) | superseded by later cycle audits for status; retained as evidence |

## Phase 1 — Contract / Security Remediation

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASE_1_CONTRACT_FORENSIC_AUDIT.md` | C | Historical | Phase 1 contract-level forensic audit | evidence of record |
| `AUDIT_PHASE1_REDTEAM.md` | D | Historical | Phase 1 source-level red-team audit | evidence of record |
| `PHASE1_SECURITY_REMEDIATION_REPORT.md` | D | Historical | Phase 1 security remediation record | evidence of record |

## Phase 2 — Baseline Architecture / Design Decisions

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASE2_BASELINE_ARCHITECTURE_AUDIT.md` | C | Historical | Baseline architecture & security audit | evidence of record |
| `PHASE2_HUMAN_DESIGN_DECISION_MATRIX.md` | D | Historical | Human design decision matrix (Phase 2 gate) | evidence of record |
| `PHASE2_HUMAN_DESIGN_DECISION_MATRIX_REDTEAM.md` | D | Historical | Red-team review of the Phase 2 decision matrix | evidence of record |
| `PHASE_2_IMPLEMENTATION_AUTHORIZATION_FORENSIC.md` | C | Historical | Phase 2 implementation-authorization chain forensics (A1–A7 chain origin) | still cited by reconciliation §8 |
| `docs/quant_engine.md` | B | Current supporting | Phase 2 deterministic quant engine design documentation | — |

## Phase 3 — Strategy Engine (FROZEN)

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `docs/strategy_engine.md` | B | Current supporting | Strategy & backtest engine overview (frozen Phase 3 behavior) | — |
| `docs/strategy_engine_design.md` | B | Current supporting — **FROZEN DESIGN DOCUMENT, bytes must not be reformatted** | Final Phase 3 design document (referenced by tests) | — |
| `tests/AUDIT_REPORT.md` | C | Historical | Phase 3 strategy engine comprehensive audit (audit evidence located under `tests/`, deliberately preserved in place) | evidence of record |
| `PHASE3_BLOCKER2_D4_ANALYSIS_AUDIT.md` | D | Historical | Blocker #2 D4 analysis audit | evidence of record |
| `PHASE3_BLOCKER2_D4_CORRECTED_ARTIFACT_AUDIT.md` | D | Historical | Corrected artifact audit for D4 | evidence of record |
| `PHASE3_BLOCKER2_D4_HUMAN_APPROVAL_RECORD.md` | D | Historical | Human approval record (D4) | evidence of record |
| `PHASE3_BLOCKER2_D4_HUMAN_DESIGN_APPROVAL.md` | D | Historical | Human design approval (D4) | evidence of record |
| `PHASE3_BLOCKER2_D4_HUMAN_DESIGN_DECISION_MATRIX.md` | D | Historical | Human design decision matrix (D4) | evidence of record |
| `PHASE3_BLOCKER2_D4_METHODOLOGY_FINAL.md` | D | Historical | Final D4 methodology | evidence of record |
| `PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS.md` | D | Historical | D4 numerical analysis (original) | superseded by _CORRECTED variant; preserved |
| `PHASE3_BLOCKER2_D4_NUMERICAL_ANALYSIS_CORRECTED.md` | D | Historical | D4 numerical analysis (corrected) | evidence of record |
| `PHASE3_BLOCKER2_DESIGN_AMENDMENT_DRAFT.md` | D | Historical | Blocker #2 design amendment draft | superseded by DESIGN_APPROVAL; preserved |
| `PHASE3_BLOCKER2_DESIGN_APPROVAL.md` | D | Historical | Blocker #2 design approval | evidence of record |
| `PHASE3_BLOCKER2_DESIGN_REVIEW.md` | D | Historical | Blocker #2 design review | evidence of record |
| `PHASE3_BLOCKER2_FINAL_DECISION_MATRIX.md` | D | Historical | Blocker #2 final decision matrix | evidence of record |

## Phase 4A — Multi-Asset PIT Design (pre-correction)

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `DESIGN_REVIEW_PHASE_4A_MULTI_ASSET_PIT.md` | E | Superseded | Original 4A multi-asset PIT design review | superseded by 4A.1 architecture correction |
| `DESIGN_GATE_REPORT.md` | E | Superseded | 4A decision-gate report | superseded by 4A.1 cycle |
| `PHASE_4A_FINAL_ARCHITECTURE_SPEC.md` | E | Superseded | 4A final architecture spec (pre-correction) | superseded by 4A.1 spec family |

## Phase 4A.1 — Architecture Correction (remediation cycle)

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md` | E | Superseded (executed); governance practice retained | The 4A.1 remediation spec of record (GOV rules, dispositions). **Name pinned by src/tests references — never rename** | execution mandate discharged; closure evidence = IMPLEMENTATION_RECORD + ZAI_PHASE_4A1_FINAL_STATUS |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_SPEC.md` | E | Superseded | Earlier correction spec | superseded by AUTHORITATIVE_REMEDIATION_SPEC |
| `PHASE_4A1_IMPLEMENTATION_SPEC.md` | E | Superseded (historical) | Implementation specification (spec era) | superseded by closure evidence |
| `PHASE_4A1_BLOCKER_RESOLUTION_SPEC.md` | E | Superseded (historical) | Blocker resolution specification | superseded by AUTHORITATIVE_REMEDIATION_SPEC + closure |
| `PHASE_4A1_IMPLEMENTATION_RECORD.md` | B | Current supporting — **authoritative 4A.1 closure record; manifest pinned by SUB-18 + final_gate_verify.py; name pinned by tests** | 4A.1 implementation record incl. 13-file sha256 manifest | — |
| `PHASE_4A1_FINAL_ARCHITECTURE_GATE.md` | D | Historical | Final architecture gate decision record | closure evidence governs |
| `PHASE_4A1_IMPLEMENTATION_FORENSIC_AUDIT.md` | C | Historical | Implementation forensic audit (spec era) | evidence of record |
| `PHASE_4A1_FORENSIC_RECONCILIATION.md` | D | Historical | Spec-era forensic reconciliation | evidence of record |
| `PHASE_4A1_SPEC_RECONCILIATION.md` | D | Historical | Specification reconciliation | evidence of record |
| `PHASE_4A1_INDEPENDENT_REAUDIT_REPORT.md` | C | Historical | Pre-implementation independent re-audit (RE-AUDIT_FAIL era) | superseded by closure; preserved |
| `PHASE_4A1_POST_REAUDIT_CORRECTION_REPORT.md` | D | Historical | Post-re-audit documentation correction pass | evidence of record |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_CHECKLIST.md` | D | Historical | Correction checklist & diff plan | evidence of record |
| `PHASE_4A1_ARCHITECTURE_CORRECTION_REPORT.md` | D | Historical | Correction report | evidence of record |
| `PHASE_4A1_MANDATORY_BLOCKER_CLOSURE_EXECUTION_PLAN.md` | D | Historical | PLAN_ONLY closure execution plan (executed under authorization A4) | superseded by execution record |
| `PHASE_4A1_PRE_IMPLEMENTATION_PLAN_INTEGRITY_GATE_REPORT.md` | D | Historical | Pre-implementation plan integrity gate | evidence of record |
| `PHASE_4A1_DESIGN_LOCK_RECORD.md` | D | Historical — FAILED attempt, never rewritten | Design Lock attempt #1 | gate SUPERSEDED by operator authorization (CR-04) |
| `PHASE_4A1_DESIGN_LOCK_REATTEMPT_RECORD.md` | D | Historical — FAILED attempt | Design Lock re-attempt #2 | as above |
| `PHASE_4A1_DESIGN_LOCK_FINAL_REATTEMPT_REPORT.md` | D | Historical — FAILED attempt | Design Lock final re-attempt #3 | as above |
| `PHASE_4A1_DL_D1_AUTHORIZATION_IMPACT_ASSESSMENT.md` | D | Historical | DL-D1 authorization & impact assessment | evidence of record |
| `PHASE_4A1_DL_D1_HUMAN_AUTHORIZATION_GATE_REPORT.md` | D | Historical | DL-D1 human-authorization decision gate report | evidence of record |
| `PHASE_4A1_DL_D1_OPTION_A_DECISION_RECORD.md` | D | Historical — decision still standing | Human decision: CRLF Option A | condition root-caused (CR-07) |
| `PHASE_4A1_DL_D5_RED_TEAM_REPORT.md` | D | Historical | DL-D5 red-team report | evidence of record |
| `PHASE_4A1_DL_D5_TARGETED_CORRECTION_REPORT.md` | D | Historical | DL-D5 targeted correction | evidence of record |
| `PHASE_4A1_MULTI_AI_ARCHITECTURE_BLUEPRINT.md` | D | Historical | 4A.1-era multi-AI architecture planning | superseded by construction-era blueprint |
| `PHASE_4A1_MULTI_AI_CONSTRUCTION_BASELINE.md` | D | Historical | 4A.1-era construction baseline / document map | superseded by MASTER_DOCUMENTATION_INDEX (this index) |
| `PHASE_4A1_OPTION_A_CLOSURE_STATE_RECONCILIATION.md` | D | Historical | Option A closure-state reconciliation | superseded by cycle reconciliation |
| `PHASE_4A1_BLOCKER_1_ACCEPTANCE_TEST_REPORT.md` | C | Historical | Blocker 1 acceptance test report | evidence of record |
| `PHASE_4A1_BLOCKER_1_MANIFEST_INTEGRITY_REVIEW.md` | C | Historical | Blocker 1 manifest integrity review | evidence of record |
| `PHASE_4A1_BLOCKER_1_OWNERSHIP_IMPLEMENTATION_REPORT.md` | C | Historical | Blocker 1 ownership implementation report | evidence of record |
| `ZAI_PHASE_4A1_FINAL_STATUS.md` | B | Current supporting | 4A.1 closure status report (8/8 blockers CLOSED, 563 tests, 9 commits) — re-verified post-hoc | — |
| `ZAI_PHASE_4A1_STATE_REAUDIT.md` | C | Audit evidence | Independent re-verification of the 4A.1 final status claims | — |

## Phases 4A.2, 4A.3, 4A.4, 5, 6, 7, 8, 9, 10, 11, 11P, 12

**No phase-owned standalone documents exist for these phases.** Their
authoritative documentation lives in the cross-phase implementation records
(next section). This is intentional: each phase was constructed and closed
within a single cycle whose provenance is recorded cycle-wide, not per-phase.
Any future phase-owned document SHALL follow the naming standard
(`PHASE_04A2_<SUBJECT>.md`, …, `PHASE_12_<SUBJECT>.md`).

## Phase PRED — Prediction & Crash Intelligence

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `AI_TRADING_LAB_PREDICTION_CRASH_INTELLIGENCE_SPEC.md` | A | Current — authoritative architecture spec for the prediction layer (v1.1.0: closure extension §17) | Prediction & crash intelligence contracts, invariants, data policy, governance | — |
| `PREDICTION_INTELLIGENCE_IMPLEMENTATION_REPORT.md` | B | Current supporting — construction record (v1.0.0) + closure addendum (v1.1.0, §7) | Implementation record (31 modules, 270 prediction tests, honest coverage assessment) | — |
| `PREDICTION_VALIDATION_EVALUATION_REPORT.md` | B | Current supporting — closure-cycle validation record | §26 claim-category separation, PRED-F1/F2/F3 closure evidence, blocker closure table | — |
| `PREDICTION_REDTEAM_ADVERSARIAL_REPORT.md` | B | Current supporting — executed adversarial matrix evidence | 45 attacks, six categories, matrix hash `preda.8366…`, all defended | — |
| `PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md` | B | Current supporting — governing data policy companion | Dataset epistemic states, quality gates, source governance, approval templates | — |
| `WP_12_CI_IMPLEMENTATION_SPEC.md` | B | Current supporting — PENDING HUMAN AUTHORIZATION | Implementation-ready GitHub Actions workflow spec; WP-12 = HUMAN_DECISION_REQUIRED | — |

## Phase RT — Final Integrated Runtime (runtime-integration era)

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` | B | Current — audit baseline of record for the FINAL INTEGRATED RUNTIME mandate (§2 FIRST TASK; v1.0.0) | Runtime-integration audit: component inventory, dependency/runtime/execution graphs, ownership tables, missing connections MC-1..12, RT-F1..15 findings, PHASE A–AF implementation order | — |
| `PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md` | A | Current — **authoritative consolidated bug register** for the pre-paper phase (bug-forensic mandate §26; v1.0.0) | Pre-paper forensic: RT-F1..15 + MC-1..12 + ARCH-F1..4 re-verification record; NEW register BUG-001..009 (3 CRITICAL: limit-order price violation, position-flip basis, additive risk netting); 11/11 executable reproductions; prepared fixes (§5) BLOCKED_BY_AUTHORIZATION; PAPER_READY = NO (PAPER-BLK-1..10) | — |

The remaining §61 spec documents (`TRADING_RUNTIME_ARCHITECTURE.md`, `TRADING_EVENT_CONTRACT.md`, `ORDER_LIFECYCLE_SPEC.md`, `PAPER_TRADING_SPEC.md`, …) are deliberately NOT created until their implementing phase lands (audit-first discipline; §61 "only where needed").

## Cross-Phase Implementation Records

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASES_4A2_TO_GRADUATION_IMPLEMENTATION_RECORD.md` | B | Current supporting — authoritative for the 4A.2→graduation cycle | Provenance + authorization #2 record (12 commits, 692 tests) | — |
| `PHASES_DISCOVERY_TO_AUTONOMY_IMPLEMENTATION_RECORD.md` | B | Current supporting — authoritative for the discovery/knowledge/benchmarks/lifecycle cycle | Provenance record (5 commits, 789 tests) | — |
| `ZAI_FULL_ROADMAP_COMPLETION_STATUS.md` | B | Current supporting | Roadmap completion status (4A.2→graduation delivery summary) | — |

## Cross-Phase Governance

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `PHASE_GOVERNANCE_RECONCILIATION.md` | A | Current — authoritative construction-era reconciliation (12 contradictions classified, authorization chain A1–A7, SSOT hierarchy) | Governance reconciliation of the construction era | — |
| `H1_FORMAL_DECISION_ANALYSIS.md` | B | Current — decision-gate artifact; H-1 = OPEN / HUMAN-REVIEWED / CONTAINED; **awaiting human ratification** | H-1/F-04 formal decision analysis | — |
| `ZAI_ENHANCEMENT_MANDATE_REGISTRATION.md` | B | Current | Enhancement Mandate v2.0 registration + 17-package gap analysis | — |
| `GOVERNANCE_DOCUMENT_CONTRADICTION_REGISTER.md` | A | Current — the live contradiction register (carries CR-01..CR-12 forward + documentation-era entries) | Contradiction register of record | supersedes the reconciliation's inline CR table for tracking purposes (original preserved) |

## Cross-Phase Audits

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `AUDIT_SELF_INTEGRITY_REPORT.md` | D | Historical | Pre-4A.1 self-integrity audit | evidence of record |
| `AUDIT_STATE_SNAPSHOT.md` | D | Historical | Pre-4A.1 state snapshot | evidence of record |
| `REGRESSION_BASELINE_FORENSIC.md` | C | Historical | Baseline regression forensics | evidence of record |
| `ZAI_WEEK_END_FULL_FORENSIC_INSPECTION.md` | C | Audit evidence (25 sections; scope nuance CR-06 recorded) | Week-end full forensic inspection | — |
| `ZAI_CURRENT_REPOSITORY_STATE.md` | C | Audit evidence (point-in-time STEP 0 snapshot) | Mandate v1.0 STEP 0 discovery report | superseded for "current state" by the progress brief; preserved as evidence |
| `FINAL_FULL_REPOSITORY_FORENSIC_AUDIT.md` | C | Audit evidence | Mandate Phase 31 forensic audit | — |
| `ZAI_DEFECT_REGISTER.md` | B | Current supporting — live register (1 HIGH contained, 5 MEDIUM, 8 LOW) | Defect register of record | — |
| `AUDIT_DOCUMENTATION_LINKS.md` | C | Current audit evidence | Documentation link audit (this cycle) | — |
| `AUDIT_DOCUMENTATION_NORMALIZATION.md` | C | Current audit evidence | Documentation normalization final report (this cycle) | — |
| `docs/reports/BATCH_8_INDEPENDENT_RUNTIME_AUDIT.md` | A | AUTHORITATIVE Batch 8 independent audit (v1.0.0, 2026-10-13): first-hand re-verification of Batches 5–7 — repository/remote evidence chain (commits resolved + remote heads == local tips, authenticated ls-remote), authoritative broker-neutral execution path (single submission path, identity-bound risk decision, deterministic fills, exactly-once accounting, UNKNOWN-reconciles-from-venue-truth, restart idempotency, precision fail-closed, mock-only enforcement), Batch 6 controls all VERIFIED (watchdog fail-closed incl. bridge honesty; audited operator cancel/close; partial-fill metric; exit-risk observability; dead-state removal; account-drawdown boundaries/trip/restart; snapshot config evolution fail-closed-by-default with no risk-policy override), Batch 7 discovery/catalog (registration ≠ eligibility, fail-closed discovery, Bitget = mock spot-v2 semantics ONLY), tenancy contract verification with infrastructure limitations stated, 2,215+1 ×3 deterministic, frozen 11/11, manifest 13/13, secret scan 0 across all history, zero reproducible defects (two suspicions refuted by byte-level evidence), 32-gate table with 3 honest FAILs (REAL_DATA/OPERATIONAL_FEED/GOVERNANCE — human/data dependencies), real-vs-mock broker matrix, ranked operator actions incl. PAT rotation (exposure #19); PAPER_READY = FALSE unchanged | Independent runtime audit + safety-gate verification + paper-readiness evidence (Batch 8) | — |
| `docs/reports/BATCH_9_RELEASE_READINESS_EVIDENCE_AUDIT.md` | A | AUTHORITATIVE Batch 9 release-readiness audit (v1.0.0, 2026-10-13): repository truth established credential-free (unauthenticated ls-remote — no stored credential exists, none used; main d49b822 unchanged; PRs #1/#2 open unmerged; CI on current heads UNVERIFIED — REST 403 rate-limited twice); documentation-only evidence inventory delivered (GOV-REI-001) for the three unresolved gates with per-item status, evidence class, reference, owner, timestamp, expiry rule, unresolved reason and next operator action; 8 binding integrity rules; 18 RED-first pinning tests adversarially verified (a FAIL-to-PASS item flip caught; a PAPER_READY fabrication caught after guard strengthening — honest finding recorded); suite 2,233 + 1 skipped ×3 deterministic, 244 focused, frozen 11/11, manifest 13/13, secret scan 0 across all 81 commits (count-only output); NO gate changed (29 PASS / 3 FAIL); PAPER_READY = FALSE; multi-broker scope re-verified mock-only; remote push BLOCKED on PAT rotation confirmation — exact operator push/verify commands recorded in §9 | Release readiness + evidence tracking + safe integration audit (Batch 9) | — |
| `docs/reports/BATCH_10_POST_ROTATION_REMOTE_RECONCILIATION.md` | A | AUTHORITATIVE Batch 10 post-rotation reconciliation audit (v1.0.0, 2026-10-13): starting state verified exactly (branch audit/batch-9-release-readiness-evidence @ 7f76c0e, clean tree, parent 30ff1ce); credential posture audited FIRST-HAND — replacement credential ABSENT from the agent environment (no credential helper, no stored credential file, no gh CLI, no token env vars, clean remote URL), revocation unverifiable without forbidden means, so per the mandate all authenticated operations were stopped and the blocker reported (Batch 9 AND Batch 10 pushes remain local-only; exact operator push/verify commands recorded §10); remote reconciled UNAUTHENTICATED: main d49b822 unchanged, Batch 9 branch absent remotely, PR heads unchanged; CI verified GREEN through the public read-only REST API (three quota-contention capture rounds, zero credentials used) for main d49b822 (runs 38039475901 + 38039475525, 4/4 legs success) and BOTH current PR heads — PR #1 7f384e6 (run 38293840380) and PR #2 d945833 (run 38242367378) — upgrading the historical record which previously covered only 4e6dfc5; all 6 repository workflow runs completed success; PR review: both open, unmerged, mergeable=true, mergeable_state=clean; PR #2 strictly contains PR #1 (merge-base 7f384e6); GitHub test-merge refs current against main; branch-protection rules UNVERIFIED (401 unauthenticated); evidence inventory GOV-REI-001 → v1.1.0: GOV-06 UNVERIFIED → PASS on verified API evidence (a visibility item, NOT a gate precondition), GOV-03 FAIL retained with the credential-absence finding, zero fabrication — GOVERNANCE_READY remains FAIL; suite 2,233 + 1 skipped ×3 deterministic, 244 focused, frozen 11/11, manifest 13/13, secret scan 0 across all 82 commits; multi-broker scope untouched mock-only; recommended merge decisions (PR #2 supersedes PR #1) recorded advisory-only — nothing merged, no main change; PAPER_READY = FALSE; LIVE NOT AUTHORIZED | Post-rotation remote reconciliation + release governance (Batch 10) | — |
| `docs/reports/BATCH_11_COMPLETE_REMAINING_WORK_AUDIT.md` | A | AUTHORITATIVE Batch 11 complete remaining-work audit (v1.0.0, 2026-10-13): READ-ONLY mandate executed with zero source/test modifications — repository truth verified first-hand (branch audit/batch-10-post-rotation-reconciliation @ e0e0cee clean; Batch 9 @ 7f76c0e exact; ancestry main d49b822 → 30ff1ce → 7f76c0e → e0e0cee; deliverables confirmed via ls-tree; remote reconciled unauthenticated — main unchanged, batch branches absent, pushes blocked on credential rotation); suite 2,233 + 1 skipped ×2 deterministic (79.57/81.65s) — zero regressions; frozen 11/11, manifest 13/13, secret scan 0 across all 83 commits + working tree; 13-area runtime audit all PASS at honest classification — runtime execution, risk controls, kill switch, order lifecycle, recovery, reconciliation, ingestion, feeds (governed-synthetic), brokers (MOCK-ONLY, structurally enforced at session.py:309 + _mock_core.py:139), instrument registry, tenancy isolation, secrets, readiness gates (FORCE_PAPER_READY structurally impossible) — ZERO new code-addressable safety defects; platform requirements: Windows installer NOT IMPLEMENTED/NOT SPECIFIED (zero artifacts), private licensing PARTIAL (LicenseState security gating implemented; commercial entitlement absent), per-user VPS deployment EXTERNAL (operator infra), read-only mobile dashboard core IMPLEMENTED (loopback stdlib server, 2 GET routes, honesty contracts, 13 tests) with public/mobile accessibility EXTERNAL; duplicate work NONE (mt5/binance data-vs-execution plane separations intentional); missing tests NONE (injected-clock watchdog/feed-freshness tests already exist — RUN-ST-1); 13-item remaining-issues register B11-R-01..13 (severity, class, affected files, acceptance criteria, required tests); dependency-ordered roadmap + recommended next batch: re-scope Batch 12 (no confirmed code-addressable safety gaps — fabricating work forbidden) toward Batch 13 confirmed items (Exness/XM venue disposition, instrument-catalog report artifact, broker capability matrix artifact); NO gate verdict changed — 29 PASS / 3 FAIL; PAPER_READY = FALSE; LIVE NOT AUTHORIZED | Complete remaining-work audit + Batch 12+ roadmap (Batch 11) | — |
| `docs/reports/BATCH_14_MARKET_DATA_READINESS_AUDIT.md` | A | AUTHORITATIVE Batch 14 market-data readiness audit + initial state baseline (v1.0.0, 2026-10-13): READ-ONLY — real starting state established first-hand (Batch 11 @ e781a9b exact, clean tree, ancestry ×4 verified, deliverables via ls-tree; Batch 12/13 reports ABSENT — never executed, confirmed scope absorbed into Batch 15 per dynamic remaining-batch rule; suite 2,233 + 1 skipped 78.61s exact-baseline zero regressions; frozen 11/11, manifest 13/13, secret scan 0 across 84 commits + tree); dependency map (completed reuse list; code-addressable queue C-1 Exness/XM venue disposition, C-2 instrument-catalog report artifact, C-3 capability matrix artifact, C-4 Windows packaging scaffold, C-5 licensing boundary, C-6 VPS deployment design, C-7 mobile dashboard view audit; external blockers + operator decisions enumerated; regressions NONE); market-data audit 8/8 mandate requirement areas PASS at honest classification — provider contracts (frozen extra=forbid, env-only secret boundary, unknown-provider error), instrument mapping (canonical↔provider symbols), UTC timestamp semantics (naive refused), provenance (hash-chained, source_hash, 13/13 pinned manifests), duplicate/ordering/gap/stale fail-closed (validation.py rules, ingestion ING-*, feed gate, risk_gate freshness fail-closed), 248 focused deterministic tests incl. provider-failure mapping (HTTP 429 no-retry-storm, bounded retries, malformed/duplicate/out-of-order/gap-reported-not-fabricated), quality/coverage measurement (health_score, expected-vs-total coverage), explicit real-provider boundary (binance-public-spot ONLY real network adapter — public/unauthenticated/credentials-refused/allowlist; mt5 read-only operator-env; feed candidates UNVETTED human-approval-only) — ZERO new code-addressable market-data gaps (no invented work); real-data qualification reported separately: REAL_DATA_READY/OPERATIONAL_FEED_READY FAIL external, zero claims; NO gate verdict changed — 29 PASS / 3 FAIL; PAPER_READY = FALSE; LIVE NOT AUTHORIZED | Market-data readiness verification + initial state baseline + dependency map (Batch 14; first batch of the Batch 14–23 completion mandate) | — |
| `docs/reports/BATCH_15_BROKER_ADAPTER_EXECUTION_CONTRACT_AUDIT.md` | A | AUTHORITATIVE Batch 15 broker adapter & execution contract audit + venue/catalog completion (v1.0.0, 2026-10-13): audit + verified-gap implementation closing Batch 11 §9 items C-1/C-2/C-3 — per-venue status matrix (7 mock venues: paper/mt5/exness/xm/binance/bybit/bitget ALL MOCK-ONLY with first-hand anchors: BrokerCredential one-account binding + redaction enforcement, fail-closed discovery, session-boundary capability validation, idempotent order lifecycle with venue-native rejection codes, deterministic rate limits + typed error mapping + same-credential reconnect + per-venue reconciliation styles + fail-closed journal recovery; data-plane venues platform/mt5.py read-only + providers/binance_public.py public documented as non-execution); C-1 CLOSED: ExnessMT5MockAdapter + XMMT5MockAdapter inherit MT5 class verbatim via smallest-safe-change subclass seams (defaults preserve mt5-mock behavior exactly), own descriptors exness-mock/xm-mock (registry 5→7 venues), Standard-account instruments EURUSD/XAUUSD/BTCUSD, per-account operator verification boundary documented, NO real connectivity claimed; C-2 CLOSED: deterministic instrument-catalog report (brokers/catalog_report.py + generated artifact — 5 canonical identities BTC/USDT×4 BTC/USD×3 ETH/USDT×3 EUR/USD×4 XAU/USD×3 merged venue mappings ALL UNVERIFIED, eligibility never granted, fail-closed behaviors referenced, known limitations honest incl. canonical asset-class simplification); C-3 CLOSED: broker capability matrix artifact (all descriptor dimensions + unsupported-order-kinds-per-venue + honesty banners); generator script with fixed timestamp (byte-identical regeneration); tests: 33 RED-first venue tests (import-RED verified) + 13 artifact byte-pin tests + contract suite strengthened 5→7 venues + registry pin 5→7 — full suite 2,233+1 → 2,333+1 (+100 tests, ZERO regressions, 79.44s), frozen 11/11, manifest 13/13, secret scan 0 across 85 commits, diff 14 files +1,754/−34 exactly scoped; NO gate verdict changed — 29 PASS / 3 FAIL; PAPER_READY = FALSE; LIVE NOT AUTHORIZED | Broker adapter audit + Exness/XM venue disposition + catalog & capability-matrix artifacts (Batch 15) | — |
| `docs/reports/BROKER_CAPABILITY_MATRIX.md` | A | GENERATED, DETERMINISTIC artifact (Batch 15, item C-3) — rendered by data_engine.brokers.catalog_report.build_capability_matrix over the governed CapabilityRegistry; byte-pinned to regeneration by tests/test_broker_catalog_artifacts.py; 7 mock venues, all MOCK_DETERMINISTIC (REAL refused at registration + session), per-venue order kinds/TIF/SLTP/position-mode/idempotency/reduce-only/account-modes/rate-limit/reconciliation + venue notes + unsupported-order-kinds-per-venue (session refuses BEFORE the venue); LIVE TRADING NOT AUTHORIZED banner | Broker capability matrix (generated reference artifact) | regenerated by scripts/generate_broker_catalog_artifacts.py |
| `docs/reports/INSTRUMENT_CATALOG_REPORT.md` | A | GENERATED, DETERMINISTIC artifact (Batch 15, item C-2) — rendered by data_engine.brokers.catalog_report.build_catalog_report from the 7 discovered venue catalogs + synced platform InstrumentRegistry; byte-pinned to regeneration; 7 venue sections (served instruments, venue symbol mappings, filters) + 5 canonical identities with merged multi-venue mappings (ALL UNVERIFIED — registration ≠ eligibility, LIVE Not Authorized everywhere) + fail-closed discovery behaviors referenced to tests + known limitations (canonical asset-class simplification documented); discovery timestamp = fixed audit-provenance constant (INV-01) | Instrument catalog report (generated reference artifact) | regenerated by scripts/generate_broker_catalog_artifacts.py |
| `docs/reports/BATCH_16_PAPER_EXECUTION_RISK_ASSURANCE_AUDIT.md` | A | AUTHORITATIVE Batch 16 paper-execution & risk assurance audit (v1.0.0, 2026-10-13): READ-ONLY — authoritative paper-runtime order path audited against the mandate's 10 requirement areas, ALL PASS first-hand — risk-budget position sizing (trade_plan.py quantity = risk_budget/stop_distance, zero-qty PlanError, max_position_units cap, notional per plan), true account equity RUN-EQ-1 (double-count guard runtime.py:2276/:2985 — commission/slippage/spread subtracted exactly once), RUN-RL-1 true daily-loss limit (fail-closed anchor establishment runtime.py:2893), RUN-DD-1 account-equity drawdown (high-water mark, restart survival, 14 tests), identity-bound single risk decision + RiskEngine limit gauntlet (breach raises + records, hash-chained log), kill switch FILL-time enforcement RUN-KS-1/2 + terminal HALT + restart survival + ARCH-F1 unprivileged reset refused, deterministic SL/TP over bars (exits.py §31, SLTP_READY gate, exit-risk observability), partial-fill accounting (OMS TRANSITIONS PARTIALLY_FILLED→EXPIRED, RT-F1 fingerprint binding, exactly-once shared _apply_execution_fills, RUN-PM-1 metric), terminal states with loud cancel/close refusals RUN-CA-1 + definitive venue-coded rejections + client_order_id idempotency, recovery verdicts RESUME/HALT/RECONCILIATION_REQUIRED + LOAD→VERIFY→RESTORE→RECONCILE→RESUME + 9 hash-chained ledgers + REPLAY_READY + deterministic suite ×2, cost model (half_spread=0.02 adverse-side deterministic MARKET fills runtime.py:1105-1109, commission_per_unit=0.001, slippage_cost/spread_cost fill fields, max_spread_fraction=0.01 guard — financing NOT modeled and NOT required by the frozen spec, documented boundary), one-account BrokerSession binding + deny-default tenancy (46 tests), signal→execution ledgered traceability incl. NO_TRADE decision records; ZERO verified gaps → zero invented tests (no-invented-work rule; existing negative suites enumerated: killswitch fill enforcement, runtime_rl, account drawdown, pnl correctness incl. double-count negative, recovery integration, safety + residuals incl. injected-clock watchdog, OMS, tenancy, authoritative venue); suite 2,333+1 at base (79.14s); frozen 11/11, manifest 13/13, secret scan 0 across 86 commits; NO gate verdict changed — 29 PASS / 3 FAIL; PAPER_READY = FALSE; LIVE NOT AUTHORIZED | Paper-execution & risk assurance audit (Batch 16) | — |
| `docs/reports/BATCH_17_SECURITY_TENANCY_PRIVATE_ACCESS_AUDIT.md` | A | AUTHORITATIVE Batch 17 security, multi-tenancy and private access audit (v1.0.0, 2026-10-13): audit + two verified-gap closures — 12 mandate areas audited first-hand ALL PASS at honest classification (auth: tenant binding at authentication time inside server-side AuthenticatedPrincipal, client tenant IDs never trusted, mismatch = DENY + TENANT_ID_MANIPULATION incident; ownership: control-plane boundary, tenant reads own license only; cross-user mutual invisibility both directions + positive control; secrets: SecretVault SHA-256 fingerprints/REDACTED-never-storable/redacted repr/duplicate refusal/reveal-needs-allowing-decision/cross-tenant-reveal-refused, env-var-only provider boundary, 0 credential-shaped strings across all history — rotation honestly classified as documented operator procedure without dedicated API, LOW advisory; sessions: short-lived, expired denied everywhere, loopback read-only dashboard 2 GET routes 405/404, mobile no-write/no-secret-store/no-order-path; audit integrity: append-only decisions with security_incident flags, values never in audit, 9 hash-chained ledgers; config: frozen extra=forbid FS-17, fail-closed defaults, secret-free CI contents:read no pull_request_target; admin restrictions: control-plane boundary + ARCH-F1 + authorize_live structural refusal; 46 negative tests green); GAP CLOSED: audit-dependencies CI job appended to .github/workflows/ci.yml (workflow_dispatch ONLY — existing push/PR CI bit-for-bit unchanged, zero test references to ci.yml verified; pip-audit --strict --disable-pip over the full uv export, fail-closed on ANY known vulnerability; honestly NOT VERIFIED locally — offline environment, operator triggers post-push); C-5 CLOSED: docs/LICENSING_PRIVATE_DISTRIBUTION_BOUNDARY.md (security-level license gating implemented + test-pinned, explicit DENY-never-silent semantics, commercial entitlement deliberately unbuilt, NO DRM, NO data collection, NO legal claim, keys/credentials/IdP external-only); NO gate verdict changed — 29 PASS / 3 FAIL; PAPER_READY = FALSE; LIVE NOT AUTHORIZED | Security, multi-tenancy and private access audit + gap closures (Batch 17) | — |
| `docs/LICENSING_PRIVATE_DISTRIBUTION_BOUNDARY.md` | B | CURRENT SUPPORTING licensing & private-distribution boundary definition (v1.0.0, Batch 17 item C-5): IMPLEMENTED surface = license-STATE access gating (ACTIVE/SUSPENDED/REVOKED/EXPIRED; inactive denies everything, revocation immediate, DENY with recorded closed-vocabulary reason — never silent, never degrades); explicitly NOT implemented = commercial entitlement issuance/billing/license-key generation (operator product decision), DRM (none created), user-data collection (no path exists), legal-compliance claims (require external review); required external inputs table (entitlement design, signing keys, production credentials, IdP config, legal review — secure processes only, never in-repo); verification commands (46 tenancy tests + 0-secret forensic gate) | Private-distribution licensing boundary (Batch 17) | — |
| `docs/WINDOWS_INSTALLER_AND_PACKAGING.md` | A | AUTHORITATIVE Windows installer & application packaging spec (v1.0.0, Batch 18 item C-4): scope finding (platform-independent Python engine, wheel py3-none-any, MT5 data-plane the only Windows element, signed installer exe = operator product decision); reproducible build VERIFIED (uv build — wheel 689,373B SHA256 93cd883a…95ea7c0, sdist 569,496B SHA256 284e2a9b…f95eebe; dist/ gitignored, binaries never committed); Windows install procedure (fresh per-user venv %LOCALAPPDATA%, wheel install, optional MT5 extra, smoke validation); data dirs FS-01..06 fail-closed containment; secrets never packaged (env-var-only + redaction); startup errors/safe shutdown/diagnostics; upgrade (fresh-venv) / rollback (SHA-recorded) / backup / uninstall (plain directory delete); version+build provenance incl. honest LOW finding pyproject 0.1.0 vs __version__ 0.3.0 mismatch (lock-frozen, deferred to operator review); per-item verification-status table — clean-install-on-Windows NOT VERIFIED (external Windows host, operator records) | Windows packaging spec (Batch 18) | — |
| `scripts/windows_smoke_test.py` | A | Windows packaging smoke test (Batch 18): 7 fail-closed checks runnable on any installed environment — import+version provenance, readiness fail-closed contract (PAPER_READY=TRUE with failing gates structurally refused), REAL execution-mode descriptor refused, all venues MOCK_DETERMINISTIC, dashboard default loopback bind, ephemeral bind, safe shutdown; script logic VERIFIED in the agent environment (7/7 PASS); Windows-host execution NOT VERIFIED (operator runs post-install and records output); never places orders, never contacts brokers | Windows installation validation (Batch 18) | — |
| `docs/PER_USER_VPS_DEPLOYMENT.md` | A | AUTHORITATIVE per-user VPS & operational deployment design (v1.0.0, Batch 19 item C-6): per-user VPS model (one unprivileged engine instance per user — logical tenancy + physical host isolation per PLATFORM_EXPANSION_SPEC §5); least-privilege OS account + systemd sandboxing; secret injection via root-owned 0600 EnvironmentFile (names only — never values, never command history; journald sees names only); health/readiness/safe-shutdown semantics (honest 32-gate verdict + Type=exec + fail-closed startup + dashboard shutdown); persistent storage + backup/restore via runtime LOAD→VERIFY→RESTORE→RECONCILE→RESUME-or-HALT; restart recovery + NTP prerequisite + RUN-ST-1 feed watchdog; resource limits + redacted journald + incident vocabulary; loopback-only network posture (public exposure = explicit operator TLS/proxy decision); git-versioned templates + SHA-pinned rollback; honest verification-status table — SIMULATED / LOCALLY TESTED / EXTERNALLY VERIFIED (NONE); NO deployment performed | Per-user VPS deployment design (Batch 19) | — |
| `deploy/systemd/ai-trading-lab@.service` | A | Per-user templated systemd unit (Batch 19): 20 validator-pinned hardening keys — aitl-%i dedicated account, NoNewPrivileges/ProtectSystem=strict/ProtectHome/PrivateTmp/RestrictSUIDSGID/LockPersonality/RestrictRealtime, IPAddressDeny=any + IPAddressAllow=localhost, EnvironmentFile secret injection (names only), Type=exec, Restart=on-failure + RestartSec, SIGTERM safe stop, MemoryMax=512M/CPUQuota=50%/TasksMax=64, journald output; committed WITHOUT any secret value (0-secret gate + validator enforce) | Per-user deployment unit template (Batch 19) | — |
| `deploy/config/secrets.env.example` | A | Per-user secrets environment TEMPLATE (Batch 19): placeholder NAMES ONLY — every secret-named entry empty (ATL_PROVIDER_API_KEY=, ATL_KEYED_MAC_KEY=); non-secret config values allowed (ATL_DASHBOARD_HOST=127.0.0.1 loopback-only default, ATL_DASHBOARD_PORT); deploy instructions (copy to /var/lib/ai-trading-lab/<user>/secrets.env, root:aitl-user 0600, set values out-of-band); committed with NO secret values | Deployment secrets template (Batch 19) | — |
| `scripts/validate_deployment_templates.py` | A | Deployment-template validator (Batch 19): fail-closed validation runnable anywhere — 20/20 mandated unit hardening keys, no credential-shaped values in ANY committed template, secret-named entries empty, 6/6 mandated spec sections, simulated/locally-tested/externally-verified separation; VERIFIED in the agent environment 6/6 PASS; proves templates well-formed — NOT a deployment and proves nothing about any running host | Deployment template validation (Batch 19) | — |

## Cross-Phase Security

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `SECURITY_CREDENTIAL_FORENSIC_REPORT.md` | C | Current audit evidence — P0 deliverable of the staged readiness program (v1.0.0) | Credential exposure forensic (4th chat exposure, value withheld, verified STILL ACTIVE via API); full tree/config/history sweeps (0 credentials); push hygiene record; staged readiness program P0–P8 registration (P0 COMPLETE, P1 correction window AWAITING HUMAN AUTHORIZATION); NO TRADING IMPLEMENTATION PERFORMED | — |
| `P1_CORRECTION_WINDOW_REPORT.md` | C | Current audit evidence — P1 execution record (v1.0.0): 16/16 authorized findings corrected with objective evidence (1141/1141 tests x3, 0/17 AFTER-probes defective, 31/31 BUG-008 mutations blocked, frozen gates 11/11 + 13/13); closure verdicts deferred to the P2 re-audit; local commits 1277331 + docs (NOT pushed per rule 11) | Correction-window execution record for BUG-001..009 + ARCH-F1/F3/F4/F6 + RT-F7/F8/F13 | — |
| `P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md` | C | Current audit evidence — P2 independent re-audit record (v1.0.0, READ-ONLY): every P1 correction re-verified first-hand (diffs + probes + 1141/1141 x2 + 8 category subsets); **verdicts 15 CLOSED · 1 PARTIAL (BUG-008 residual rule-deferred) · 0 OPEN · 0 REGRESSED; P2 VERDICT: CONDITIONAL PASS**; frozen integrity re-verified blob-level; security scans 0; exposed PAT re-verified STILL ACTIVE (exposure #5 — rotation OPEN); OBS-1 mode-sweep recorded; open-blocker register (CRED-ROTATION / BUG-008-RESIDUAL / KEYED-MAC / PAPER-BLK-1..6 / P3 Stage-0 / OBS-1); P3 NOT AUTHORIZED | Independent re-audit of the P1 correction window (staged readiness program stage 2) | — |
| `PAPER_TRADING_READINESS_FINAL_REPORT.md` | C | Current cycle evidence — paper-readiness RE-AUDIT final report (**v2.9.0 §0H**: runtime-risk-safety Batch 2 — RUN-DD-1 account-equity drawdown limit CLOSED: mark-to-market (peak-current)/peak with deterministic peak replay from persisted bars+fills, new mandatory `account_drawdown` check (unknown fails closed, strict breach refuses entries, closing carve-out), per-bar enforcement trips ACCOUNT kill switch + terminal HALT with immediate persistence and restart refusal, in-flight freeze verified, +14 RED-first tests, suite 2,039 + 1 skipped ×3, frozen 11/11; config-digest evolution documented (old snapshots fail-closed); **v2.6.0 §0E**: kill-switch enforcement audit — full order-path trace (every order via `_execute_plan` → 21-check RiskGate → fingerprint-bound OMS approval → latency-aware fills), three audit-confirmed bypasses CLOSED on fix/paper-runtime-killswitch-fill-enforcement: RUN-KS-1/RUN-KS-2 (in-flight orders filled after SYMBOL/ORDER-scope trips — fill-time enforcement + ORDER_CANCELLED_KILL_SWITCH incident, exit-order carve-out preserved) + RUN-HALT-1 (persisted HALTED restored as terminal HALTED, never RUNNING); +7 acceptance tests (4 RED pre-fix + 3 pins), suite 1,769 + 1 skipped ×2, zero regressions, frozen untouched; RUN-DD-1 now top-ranked OPEN blocker; **v2.5.0 §0D**: next-execution mandate — Phase A–C re-verified, RUN-EQ-1/RUN-RL-1 (equity cost double-count + vacuous daily loss limit) CLOSED via PAPER-RUN-PNL-1 on fix/paper-runtime-pnl-correctness with 7 acceptance tests first (suite 1,762 + 1 skipped ×2, zero regressions), RUN-DD-1/ST-1/CA-1/PM-1/DA-1 registered OPEN; **v2.4.0 §0C**: real provider architecture + feed composition + 32-gate table; **v2.3.0**: §0B master-import amendment — operator bundle registered 3 × REAL_UNVERIFIED + 1 × INVALID, verdict UNCHANGED; v2.2.0 §0A: operator decisions recorded, keyed-MAC custody, 32nd gate OPERATIONAL_FEED_READY; v2.0.0: all 28 re-audit blockers verified + closed where authorized — persistence MANDATORY, readiness-gated startup, runtime-integrated recovery at 10 restart points, EXECUTION_STATE_SCHEMA v1.1.0, full ledger/memory chain recovery, kill-switch persistence, PARTIAL→EXPIRED defect fixed, wall-clock-free identity (cross-process ×2); frozen 13/13 before AND after; **PAPER_READY = FALSE — BLOCKED_ON_HUMAN_OR_DATA_DEPENDENCY**. Supersedes v1.0.0 (archived at `docs/PAPER_TRADING_READINESS_FINAL_REPORT_v1.md`) | Paper-readiness re-audit cycle (operator-authorized) + next-execution mandate 2026-10-12 + kill-switch enforcement audit 2026-10-12 | — |
| `CURRENT_REPOSITORY_PAPER_READINESS_BRIEF.md` | B | Current supporting — pre-implementation paper-readiness snapshot at f61e1ee (gap register this cycle closed) | Orientation snapshot (superseded in part by the final report above) | — |
| `H1_RATIFICATION_DECISION_RECORD.md` | A | AUTHORITATIVE governance decision record (v2.0.0): **H-1 RATIFIED 2026-10-10 — Option A containment (GOV-H1-002-RATIFY)**; operator in-session authorization quoted verbatim; ratified v1.0.0 text + sha256 pinned; no signature fabricated; frozen artifacts untouched | H-1/F-04 containment governance | — |
| `REAL_DATA_READINESS_CONTRACT.md` | A | AUTHORITATIVE data contract (v1.0.0): full §9 pipeline + dataset record schema + §10 quality gates — **BLOCKED_ON_REAL_DATA** (0 verified datasets; never invented) | Real-data readiness gate | — |
| `CI_WP12_GATE_DECISION_RECORD.md` | A | AUTHORITATIVE governance decision record (v2.0.0): **WP-12 AUTHORIZED 2026-10-10 (WP-12-CI-ENABLE) + IMPLEMENTED** — `.github/workflows/ci.yml` installed verbatim; every workflow gate mirrored locally green; honestly NO GitHub Actions run claimed (first push triggers the first run) | CI gate governance | — |
| `BUG008_RESIDUAL_RESOLUTION_RECORD.md` | A | AUTHORITATIVE governance decision record (v1.0.0, GOV-B08-001): **BUG-008 residual CLOSED — permanent acceptance of the runtime-boundary adapter** (the path preserving frozen contracts); 13 deferred fields pinned by dynamic discovery in `tests/test_bug008_boundary_closure.py`; frozen byte-identity re-proven | BUG-008 residual governance | — |
| `KEYED_MAC_CUSTODY_DECISION_RECORD.md` | A | AUTHORITATIVE governance decision record (v1.0.0, GOV-KMC-001): **keyed-MAC custody DECIDED + mechanism IMPLEMENTED / NOT OPERATIONAL** — `runtime/mac_custody.py` + keyed ledger chains (rtledm. HMAC, rotation grace, strict mode discipline, full-history-rewrite defense); operationalization awaits genuine key provisioning via the secure channel (env-var/external-key-file); provisioning log (fingerprint-only) inside | Ledger integrity governance | — |
| `HISTORICAL_DATA_DEFERRAL_RECORD.md` | A | AUTHORITATIVE governance decision record (v1.0.0, GOV-HDD-001): **long-term historical-data acquisition DEFERRED** by operator (2026-10-10); research-history vs operational-feed separation semantics; referenced by `runtime/feed_gate.py` and the 32-gate readiness set | Data-acquisition governance | — |
| `MASTER_MARKET_DATA_IMPORT_RECORD.md` | A | AUTHORITATIVE import record (v1.1.0, 2026-10-11): **operator master-bundle integrated on feat/master-market-data-import — DELIVERED: branch pushed b9c4361, PR #1 open vs main, platform CI run 38147316090 SUCCESS (3.11 + 3.12; full suite, determinism ×3, frozen-blob, secret scan 0, prediction acceptance); merge left to operator** — 4/4 SHA-256 verified before import and re-verified by platform CI against the pushed tree; originals preserved byte-for-byte under data/raw/master/; LFS explicitly unsupported (analysis recorded); Coins REAL_UNVERIFIED (500 symbols, all final candles incomplete at acquisition), Forex REAL_UNVERIFIED (USD-base RATE SERIES — OHLC fabrication forbidden), Stocks REAL_UNVERIFIED (monthly/quarterly, 0/9 D1-suitable), Metals **INVALID** (19 impossible-OHLC rows quarantined verbatim); provenance honestly UNKNOWN; 521 instruments registered; legacy vacuous non-chronology check fixed with byte-identical legacy manifests verified; +55 regression tests (suite 1,685 + 1 skipped); PAT rotation advisory open; **no readiness gate changed — PAPER_READY = FALSE unchanged** | Master-bundle import governance | — |
| `docs/OPERATOR_SOURCE_APPROVAL_PACK.md` | B | CURRENT SUPPORTING operator evidence pack (v1.0.0, 2026-10-12): the four evidence classes (connectivity / OHLCV validity / operational feed readiness / research verification — never conflated); `binance-public-spot` candidate facts with UNKNOWN licence/terms explicitly listed; blocked-market register (forex/stocks/metals — MISSING DEPENDENCY, not approvable); the exact SRC-APPROVAL decision template (policy §7.1) + recording commands through the registry's human-only API; post-approval semantics (approval necessary, NOT sufficient — gate still evaluates live inputs; live boundary untouched) | Human source-approval governance | — |
| `docs/PAPER_OPERATOR_RUNBOOK.md` | B | CURRENT SUPPORTING operator procedures (v1.0.0, 2026-10-12): install (uv, Python 3.11/3.12); placeholder-only env template; offline suite; optional labelled live smoke; MAC-key provisioning outside git (entropy floor, fingerprint-only logging); source-approval recording; paper-session bootstrap through `build_paper_feed_evidence` (refuses while any gate fails); live-isolation verification commands; health/feed/positions/audit inspection; restart/feed-outage recovery semantics; market disabling via allowlist + approval; honest Pydroid 3 limitation (diagnostics only, NOT a supported execution environment) | Operator procedures | — |
| `docs/MULTI_BROKER_EXECUTION_ARCHITECTURE.md` | A | AUTHORITATIVE multi-broker execution design (v1.0.0, 2026-10-12): current-architecture audit (execution/order/risk/persistence/reconciliation with exact file references); the broker-neutral interface contract v1.0.0 (`src/data_engine/brokers/`); the executable capability matrix for paper/MT5-style (Exness/XM-class)/Binance-spot/Bybit-v5; risk-ordered implementation phases M1–M6 (M1 DELIVERED, M2 runtime integration onward NOT STARTED); honest limitations (mocks model semantics, not networks; operational paper pipeline not yet rewired) | Multi-broker execution layer | — |
| `docs/TRADING_RUNTIME_ARCHITECTURE.md` | A | AUTHORITATIVE runtime spec (v2.0.0): the one orchestration path, fail-closed startup chain (BLOCKER 1/2/4), complete execution-state persistence (BLOCKER 5), component map, operating states, determinism (wall-clock-free identity, BLOCKER 14) | Runtime implementation | — |
| `docs/TRADING_EVENT_CONTRACT.md` | A | AUTHORITATIVE contract spec (v1.0.0): identity rules/prefix map, PredictionArtifact/Decision/TradePlan/ExitRecord schemas, correlation threading | Runtime contracts | — |
| `docs/ORDER_LIFECYCLE_SPEC.md` | A | AUTHORITATIVE OMS spec (v1.0.0): 14-state machine, idempotency, partial fills, TTL, execution realism | OMS implementation | — |
| `docs/PAPER_TRADING_SPEC.md` | A | AUTHORITATIVE paper spec (v1.0.0): structural isolation, persistence, P&L, replay, E2E scope protection | Paper runtime | — |
| `docs/RECONCILIATION_SPEC.md` | A | AUTHORITATIVE reconciliation spec (v1.0.0): multi-fill three-way reconcile, mismatch = STOP_NEW_ORDERS | Runtime reconciliation | — |
| `docs/KILL_SWITCH_SPEC.md` | A | AUTHORITATIVE kill-switch spec (v1.0.0): 7 scopes, human-gated reset, critical-scope authorization | Runtime safety | — |
| `docs/TRADING_LEDGER_SPEC.md` | A | AUTHORITATIVE ledger spec (v2.0.0): 9 hash-chained ledgers, event schema, NO_TRADE ledgering, full-chain persistence + recovery (re-audit BLOCKER 6) | Runtime ledgers | — |
| `docs/PREDICTION_LEDGER_SPEC.md` | A | AUTHORITATIVE prediction-ledger spec (v1.0.0): operational prediction records + research-layer relationship | Runtime prediction ledger | — |
| `docs/DECISION_LEDGER_SPEC.md` | A | AUTHORITATIVE decision-ledger spec (v1.0.0): decision records incl. NO_TRADE with blocked conditions | Runtime decision ledger | — |
| `docs/DISASTER_RECOVERY_SPEC.md` | A | AUTHORITATIVE recovery spec (v2.0.0): runtime-integrated recovery (BLOCKER 4), restore→verify→reconcile→resume-or-halt, corruption detection, runbook | Runtime recovery | — |
| `docs/PAPER_READINESS_GATE.md` | A | AUTHORITATIVE readiness spec (v2.0.0): 30 fail-closed gates (re-audit extension: REAL_DATA/TRADE_PLAN/PARTIAL_FILL/SLTP/AUDIT/REPLAY/BASELINE), runtime enforcement at startup, ephemeral-fixture governance, current FALSE verdict | Readiness gate | — |
| `docs/READINESS_EVIDENCE_INVENTORY.md` | B | CURRENT SUPPORTING evidence inventory (GOV-REI-001 v1.1.0, 2026-10-13): per-evidence-item tracking for the three unresolved gates (REAL_DATA_READY 6 items, OPERATIONAL_FEED_READY 6 items, GOVERNANCE_READY 6 items) — closed status vocabulary (PASS/FAIL/UNVERIFIED), evidence classes separating verified evidence from operator assertions, references, owners, timestamps, expiry rules, explicit unresolved reasons, next operator actions; 8 binding integrity rules (missing evidence never converts to PASS; registration is not eligibility; REAL_UNVERIFIED is not REAL_VERIFIED; mock is not real broker; no secrets; frozen contracts preserved); pinned by 18 structural tests; v1.1.0 (Batch 10): GOV-06 UNVERIFIED → PASS on verified unauthenticated-API CI evidence (runs 38293840380/38242367378 — a visibility item, not a gate precondition), GOV-03 FAIL retained with the first-hand credential-absence finding; the verdict authority remains readiness.py + the final report §15/§16 — this inventory records evidence, it never computes verdicts | Release-readiness evidence tracking (Batches 9–10) | — |
| `FILESYSTEM_SECURITY_FORENSIC_AUDIT.md` | E | Historical audit evidence (pre-B8 remediation findings) | Filesystem security forensic audit | remediation recorded in 4A.1 closure; preserved as evidence |
| `HASH_FORENSIC_AUDIT.md` | E | Historical audit evidence — pre-remediation verdicts (incl. Candle.to_hash CONTAMINATED); current interpretation: H-1 OPEN/CONTAINED | Hash forensic audit | interpretation superseded by `H1_FORMAL_DECISION_ANALYSIS.md`; evidence preserved |
| `PHASE_OWNERSHIP_FORENSIC_AUDIT.md` | E | Historical audit evidence | Phase ownership forensics | superseded by construction records; preserved |

## Reproducibility

No dedicated standalone document. Reproducibility controls are documented
in: `PHASE_4A1_IMPLEMENTATION_RECORD.md` (determinism gates),
`PHASES_DISCOVERY_TO_AUTONOMY_IMPLEMENTATION_RECORD.md` (cross-process
identity probes), and `ZAI_WEEK_END_FULL_FORENSIC_INSPECTION.md` (§ frozen
behavior / determinism). Future dedicated documents SHALL use
`REPRODUCIBILITY_<SUBJECT>.md`. Batch 15 adds byte-reproducible GENERATED
reference artifacts (`docs/reports/BROKER_CAPABILITY_MATRIX.md`,
`docs/reports/INSTRUMENT_CATALOG_REPORT.md`) — deterministic renderers in
`src/data_engine/brokers/catalog_report.py`, regenerated by
`scripts/generate_broker_catalog_artifacts.py` (fixed discovery timestamp;
tests byte-compare every regeneration against the committed files).

## Acceptance

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `AI_TRADING_LAB_FINAL_ACCEPTANCE_AUDIT.md` | C | Current audit evidence — verdict READY_WITH_FINDINGS (NOT COMPLETE) | Mandate Phase 45 final acceptance audit | — |

## Master / System Documents

| Path | Auth | Status | Purpose | Supersession |
|---|---|---|---|---|
| `MASTER_FULL_SYSTEM_CONSTRUCTION_BLUEPRINT.md` | A | Current (architecture normative) / **STALE (§2 status table + L1751 status lines — see contradiction register)** | Construction-era full-system blueprint (60 domains) | status superseded by implementation records; architecture retained |
| `MASTER_ENHANCEMENT_HARDENING_MANDATE.md` | A | Current — enhancement-era authority (50 sections, 17 work packages; execution NOT started) | Enhancement/hardening mandate v2.0 (verbatim, operator-issued) | — |
| `MASTER_PHASE_STATUS_REPORT.md` | F | **INCORRECT/CONTRADICTORY HISTORICAL CLAIMS** — 2026-09-30 snapshot ("NO PHASE MAY ADVANCE", NOT_AUTHORIZED statuses) now stale; preserved per mandate §7-F | Audit-era phase/blocker status snapshot | superseded by `PHASE_GOVERNANCE_RECONCILIATION.md` + implementation records |
| `MASTER_DOCUMENTATION_INDEX.md` | A | Current — **THIS DOCUMENT** | Documentation SSOT index | — |
| `README.md` | B | Current supporting | Package orientation, module map, phase map | — |
| `ZAI_REPOSITORY_PROGRESS_BRIEF.md` | B | Current supporting — the repository progress brief ("what has been done so far") | One-page orientation: timeline, current state, open items | — |
| `ZAI_REPOSITORY_WORK_DONE_SUMMARY.md` | B | Current supporting — the operator-requested condensed work-done summary ("repo me abhi tak kiya kiya hai"; v4.1.0 — includes era 10 operator-approval cycle + the push record) | 5-minute read: TL;DR, hard verified state, era-by-era history (eras 0–10), module inventory, verification record, operator decision list | — |
| `docs/PLATFORM_EXPANSION_SPEC.md` | A | Current — AUTHORITATIVE spec for the platform package (PLT-001 v1.0.0) | 8-module `data_engine.platform` package: instrument registry, workbook Sheets A–G, strategy lab, news intelligence core, MT5 + TradingView adapters, CSV dataset audit/ingestion, read-only dashboard/API; Phase C dataset evidence (116,940 rows / 20 instruments → SYNTHETIC classification with hard fabrication evidence); security posture; honest limitations | — |
| `ZAI_PLATFORM_MANDATE_GAP_MATRIX.md` | B | Current supporting — mandate-to-repo status matrix (v1.1.0) | Section-by-section IMPLEMENTED/PARTIAL/MISSING/BLOCKED mapping with first-hand evidence, dependency/risk table, W1–W8 phased plan WITH delivery statuses (W1–W3, W5–W7 + Phase C DELIVERED; W4 sandbox + W8 DB explicitly NOT STARTED), operator decision list | — |
| `docs/RL_RUNTIME_GOVERNANCE_SPEC.md` | A | Current — AUTHORITATIVE spec for the governed RL advisor runtime + runtime metrics (TRA-RLG-001 v1.0.0) | Advisor-only RL contract: observation/action schemas, hard bounds, OOD fences, deterministic identity, non-authority guarantees, metrics INV-01 boundary, test evidence, honest limitations | — |
| `ZAI_AUTONOMOUS_TRADING_SYSTEM_STATUS.md` | B | Current — §76-required living status document for the Autonomous Intelligence + Full System Expansion mandate (v1.0.0 baseline: §78 audit) | Autonomy levels L0–L8, capability matrix, duplicate-system audit, dependency graph, blocker table BLK-1..15, test/data/model inventories, authorization state | — |
| `TRADING_RUNTIME_ARCHITECTURE_AUDIT.md` | B | Current — runtime-integration audit authority for the FINAL INTEGRATED RUNTIME mandate (see Phase RT section above) | §2 repository audit: the map from component library to governed trading runtime | — |
| `PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md` | A | Current — authoritative bug register for the pre-paper phase (see Phase RT section above) | Consolidated pre-paper forensic: prior-register verification + BUG-001..009 + paper-readiness blockers PAPER-BLK-1..10 | — |
| `PHASE_1_DISCOVERY_AUDIT_REPORT.md` | A | Current — authoritative Phase 1 discovery-audit record for the full-platform mandate (v1.0.0) | Repository access/branch/PR/CI verification (unauthenticated ls-remote ground truth + CI evidence of record), verified stack + layered architecture map, trading-safety-chain status, six confirmed ING/VAL defects with executable evidence + closure, product-gap matrix (multi-user/VPS/mobile/distribution honestly NOT STARTED), broker support matrix (Bitget unimplemented; no production adapter claimed), Phases 2–7 roadmap with acceptance criteria, first-batch record, remaining blockers + operator push commands | — |

---

## Ownership rules (mandate §9)

1. Every phase-owned document above has exactly one primary phase owner.
2. Cross-phase documents carry cross-phase classifications only
   (GOVERNANCE_ / AUDIT_ / SECURITY_ / REPRODUCIBILITY_ / ACCEPTANCE_ /
   MASTER_ or pre-existing names preserved under the §6 traceability rule).
3. No document simultaneously claims two phase owners. The pre-normalization
   legacy names (`PHASE_4A1_…`, `PHASE3_…`, `PHASE2_…`, `ZAI_…`) are retained
   as-is per the recorded rename decision; their phase ownership is fixed by
   THIS index, not by their filename prefix.

## How to use this index

- **"What is the current truth about X?"** → start at
  `ZAI_REPOSITORY_PROGRESS_BRIEF.md` (orientation) → this index (authority
  map) → the A/B-classified documents it points to.
- **"Is a historical claim still valid?"** → check
  `GOVERNANCE_DOCUMENT_CONTRADICTION_REGISTER.md`.
- **"Which document governs frozen Phase 3?"** → `docs/strategy_engine_design.md`
  (design, bytes frozen) + `PHASE_4A1_IMPLEMENTATION_RECORD.md` (freeze
  verification manifest).
