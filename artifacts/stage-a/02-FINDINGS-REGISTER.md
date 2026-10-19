# 02 — FINDINGS REGISTER (Stage A)

**Repo:** ai-trading-lab-data-engine @ `main` `4e9be355` · **Baseline:** 2,403 passed + 1 skipped (exit 0)
**Severity scale:** HIGH = violates a mandate invariant or breaks a documented contract in the default deployment path · MEDIUM = durability/availability/hygiene defect with realistic trigger · LOW = hardening/consistency gap · INFO = documented assumption worth tracking.

**Severity distribution:** 6 HIGH · 10 MEDIUM · 9 LOW/INFO. Zero findings enable live trading or real-money risk (system is structurally paper-only — verified at 4 layers).

---

## F-01 — Submission-rate accounting is volatile (in-memory only, not persisted)

- **Severity:** HIGH — Milestone A B1 core target; a restart wipes the submission budget in the fail-OPEN direction for throttling, violating the durable-ledger intent of the owner-ratified spacing defaults.
- **File:lines:** `src/data_engine/runtime/runtime.py:397-399` (`self._submission_times: list = []`), `runtime.py:3062-3077` (`_record_submission`/`_submissions_in_window`), `src/data_engine/runtime/state.py:59-78` (`EXECUTION_STATE_FIELDS` — no submission-times field; **personally verified**).
- **Evidence:** The only durable record of submissions (session journal ORDER_ACKs) is not consulted for rate purposes; the snapshot schema deliberately excludes `_submission_times`.
- **Affected path:** `order_rate_limit` check (risk_gate.py:401-444) reads a list that resets on every process start.
- **Consequence:** A crash-restart loop can multiply the effective rate budget (each restart grants a fresh 5/60s + 10-open budget). Paper-mode impact today is contained by mock venue idempotency, but the throttle is not durable evidence.
- **Existing protection:** In-process sequential bar-driven loop makes TOCTOU theoretical; risk gate fails CLOSED when measured state is unknown; mock venue idempotency prevents double execution.
- **Proposed remediation (B1):** Durable submission ledger persisted transactionally with the rate decision; restore on recovery; conservative reconstruction from journalled acks when the ledger is ahead/behind.
- **Regression-test design:** (1) Submit at limit → persist → restart → next submission must be refused until window/spacing satisfied (fails on current code: restart resets budget). (2) Property: measured window ⊇ journalled ack window after recovery.
- **Acceptance criteria:** Post-restart rate accounting is a superset of pre-crash accounting; no test can observe a fresh budget after restart with outstanding history; suite green.
- **Residual risk:** Low after B1 — ledger write itself becomes a new failure point (must fail closed pre-broker-call, which B1 enforces).

## F-02 — No atomic reservation: capacity check and record are separate steps, no cross-process guarantee

- **Severity:** HIGH — Milestone A B1: "atomic reservation capacity check; competing processes can never both consume the last slot."
- **File:lines:** Check at `runtime.py:2146-2152` + `risk_gate.py:401-444`; record only post-ack at `runtime.py:2261/2276`; no reservation object exists anywhere (verified by exploration + grep).
- **Evidence:** Gate evaluates over `_submissions_in_window` BEFORE order creation, but the record happens after venue ack — two runtimes (or a runtime + side-band session) on one deployment each hold a full budget; nothing enforces single-process.
- **Affected path:** All submission routes R1-R4 (master report §2.1).
- **Consequence:** N concurrent processes ⇒ up to N× the ratified limit. Today only tests construct runtimes, but Stage C's composition root will make this live.
- **Existing protection:** Deployment assumption of one process per store dir (systemd template-instance unit); side-band bridge over-counts (fail-safe direction).
- **Proposed remediation (B1):** flock-protected ledger with atomic reserve-then-submit protocol: (a) acquire exclusive lock; (b) capacity+spacing check inside the lock; (c) durable reservation with order identity written inside the same lock; (d) broker call only with valid reservation; (e) release/finalize on definitive outcome; (f) crash recovery conservatively reconstructs outstanding reservations (reservation = consumed until proven otherwise).
- **Regression-test design:** Two processes racing for the last slot (multiprocessing test with real flock on the actual filesystem — exactly one wins); failed reservation leaves no record; no order reaches commit/ack processing without a valid reservation (assert via instrumentation); kill -9 mid-protocol → reconstruction treats reservation as consumed.
- **Acceptance criteria:** Every property above holds on the actual filesystem (not mocks); suite green; no submission path bypasses the reservation boundary (grep-verified + contract test).
- **Residual risk:** Lock holder crash before broker call leaks a consumed slot until window expiry — acceptable (conservative direction), documented.

## F-03 — Zero file locking anywhere; single-writer is an unenforced assumption

- **Severity:** HIGH — mandate: "locking verified on the actual filesystem"; concurrent writers can corrupt every persistent artifact family.
- **File:lines:** No `flock|fcntl|filelock` matches in `src/` (grep-verified). Fixed tmp names: `state.py:241` (`state.json.tmp`), `session.py:807` (`<journal>.tmp`). Unlocked RMW: `security.py:344-360`. Index-from-memory: `state.py:167-169`.
- **Evidence:** `ExecutionStateStore` accepts any path and opens stores another process owns; two `serve`/runtime instances on one dir would interleave writes to the SAME tmp inode before `os.replace` (garbage or lost records); `SecurityAuditTrail.record` reads all entries then appends → chain fork under concurrency.
- **Affected path:** W1/W2/W6/W10 (master report §2.2).
- **Consequence:** Silent last-write-wins record loss; hash-chain forks that fail `verify()` (availability loss + ambiguity about authoritative fork).
- **Existing protection:** systemd one-instance-per-user template (`ai-trading-lab@.service:24-55`); tamper-evident digests mean corruption is DETECTED (load fails closed) — but detection ≠ prevention, and the failure mode bricks the deployment.
- **Proposed remediation (B4):** Store-level exclusive lock file (`.lock` + flock) acquired for the whole write path incl. tmp+replace; unique tmp names (pid+counter); locked append for SecurityAuditTrail; lock acquire at store open (fail closed: "another engine holds this store").
- **Regression-test design:** Two processes opening the same store dir → second refuses (actual filesystem flock); interleaved SecurityAuditTrail.record from two processes → chain stays linear.
- **Acceptance criteria:** No code path can write a store/journal without holding the lock; concurrent-open refused with clear error; suite green.
- **Residual risk:** NFS/POSIX-adjacent filesystems with unreliable flock — document supported filesystems (local ext4/xfs, btrfs).

## F-04 — systemd unit: `ProtectSystem=strict` without `ReadWritePaths=` breaks the documented state contract

- **Severity:** HIGH — the default deployment template cannot persist state as its own docs promise; discovered by template analysis and verified against unit directives (**personally verified**).
- **File:lines:** `deploy/systemd/ai-trading-lab@.service:30` (`ProtectSystem=strict`), `:48` (`WorkingDirectory=/var/lib/ai-trading-lab/%i`) — no `ReadWritePaths`, no `StateDirectory=`; documented contract `docs/PER_USER_VPS_DEPLOYMENT.md:66-70`; validator blind spot `scripts/validate_deployment_templates.py:46-67`.
- **Evidence:** Under `strict`, the whole filesystem is read-only except /dev, /proc, /tmp (private). Every state write (state.json, journal.jsonl, broker journal) would fail with EROFS ⇒ runtime HALT (fail-closed, but the deployment is unusable as templated).
- **Affected path:** W1-W7 under the deployed unit.
- **Consequence:** Fresh VPS deployment following the guide halts on first persist; also silently kills the fail-open `audit_log` write (F-10) making it fail-closed-but-invisible.
- **Existing protection:** Fail-closed persistence discipline converts the failure to a HALT (no silent corruption).
- **Proposed remediation (B4):** Add `ReadWritePaths=/var/lib/ai-trading-lab/%i` (+ `StateDirectory=ai-trading-lab-%i` or explicit dirs), plus `UMask=0027`; extend the template validator to require ReadWritePaths consistency; add the missing hardening set (`SystemCallFilter=@system-service`, `SystemCallArchitectures=native`, `PrivateDevices=yes`, `ProtectHostname/Clock=yes`, `ProtectProc=invisible`, `RestrictNamespaces=yes`, `CapabilityBoundingSet=`, `MemoryDenyWriteExecute=yes`).
- **Regression-test design:** Validator unit test: a unit without ReadWritePaths-under-strict FAILS validation; validator test for each new directive.
- **Acceptance criteria:** Validator green on updated template; `systemd-analyze security` improves; documented quickstart passes an end-to-end persist under the unit (manual VM check documented in Stage E evidence).
- **Residual risk:** Over-restrictive SystemCallFilter can break Python runtime — use `@system-service` allow-list, verify in Stage E VM run.

## F-05 — No production composition root; runtime constructed only in tests

- **Severity:** HIGH — Stage C core target; today nothing assembles a validated operating runtime, and the supervisor certifies nothing (honestly).
- **File:lines:** `TradingRuntime(` constructed only in `tests/` (grep over src/ + tests/); `runtime/service.py:12-18, 54-64, 185-197` (supervisor shell, readiness structurally FALSE, exit 2); `cli.py:31-39` (`status` hardcodes ABSENT/NOT_WIRED).
- **Evidence:** `serve` never builds a runtime; the tick_fn seam is unwired; readiness gate has no evidence supplier in production code.
- **Consequence:** The "integrated system" is a library + tests, not an operable service; readiness verdicts cannot become TRUE through any production path.
- **Existing protection:** Honesty-by-construction (supervisor refuses to claim active; PAPER_READY structurally FALSE).
- **Proposed remediation (Stage C1/C2):** Explicit composition root constructing in documented order (validated config → state store → durable reservation ledger → governor → OMS → risk/readiness gates → feed services → paper session boundary → audit journal → reconciliation driver → lifecycle), wired to readiness evidence suppliers and the supervisor; no hidden globals.
- **Regression-test design:** Integration test: composition root builds a runtime from a config file; readiness gates individually flippable; supervisor exits 2 until all evidence present; no construction-order violation possible (type-state test).
- **Acceptance criteria:** Supervisor never reports active unless constructed+validated+operating (test-pinned); every readiness gate has an evidence supplier or is explicitly NOT_WIRED in status output.
- **Residual risk:** Low — additive construction; frozen strategy blobs untouched.

## F-06 — Authoritative paper venue is uncapped (no rate_limit in capabilities)

- **Severity:** MEDIUM — defense-in-depth gap: throttling depends entirely on the volatile runtime gate (F-01).
- **File:lines:** `runtime/broker_execution.py:125-143` (`RUNTIME_PAPER_VENUE_CAPABILITIES` — no `rate_limit` arg; **personally verified**), default uncapped at `brokers/capabilities.py:89-90`.
- **Evidence:** All mock adapters enforce per-instance in-memory rate windows (`_mock_core.py:290-324`) but the authoritative venue declares none.
- **Consequence:** A bug/bypass in the runtime gate removes the last throttle layer on the venue seam.
- **Existing protection:** Runtime RiskGate (order_rate_limit + max_open_orders) is the enforced layer; venue notes document governance.
- **Proposed remediation (B2):** Declare `rate_limit=RateLimitPolicy(max_orders_per_window=5, window_seconds=60.0)` matching owner-ratified defaults; venue-level enforcement becomes the durable backstop once B1 lands.
- **Regression test:** Venue refuses the 6th submission in a 60s window at the adapter boundary.
- **Acceptance criteria:** Venue-level refusal demonstrable independent of runtime gate.
- **Residual risk:** None material.

## F-07 — Crash window between venue accept and OMS.submit leaves an unpolled order

- **Severity:** MEDIUM — B3 target; a crash between venue submission (runtime.py:2218) and OMS submit/record (2269-2276) leaves the OMS order in RISK_APPROVED, which is ∉ LIVE_STATES.
- **File:lines:** `runtime.py:2218-2276`; `_process_pending_orders` filters to SUBMITTED/ACKNOWLEDGED/PARTIALLY_FILLED (`runtime.py:2353-2356`); venue recovery step 1 only checks live OMS orders vs journal (`broker_execution.py:1501-1509`).
- **Consequence:** Venue holds truth the OMS lacks: fills accumulate unapplied until manual intervention; recovery does not flag the divergence.
- **Existing protection:** Venue-side journal is authoritative and digest-verified; reconciliation machinery exists but is not wired to detect this specific divergence (RISK_APPROVED-but-journalled-at-venue).
- **Proposed remediation (B3):** Recovery/reconciliation rule: any venue-journal ORDER_ACK whose client_order_id maps to an OMS order in a pre-SUBMITTED state is an EXECUTION_UNCERTAIN incident → fail-closed halt + operator report (never auto-adopt optimism); OMS transition to UNKNOWN/RECONCILING then venue-truth resolution via existing `_resolve_venue_order`.
- **Regression test:** Fault-injection double: venue ack recorded, OMS.submit skipped (simulated crash) → recovery must detect, halt, and report; no silent resume.
- **Acceptance criteria:** No test can reach RUNNING with a journalled-but-unprocessed venue order.
- **Residual risk:** Low — incident is availability-shaped (halt + manual reconcile), which is the mandated fail-closed posture.

## F-08 — BrokerSession journal: atomic but not fsynced (power-loss durability gap)

- **Severity:** MEDIUM — mandate requires fsync/atomic-replace verification on the actual filesystem.
- **File:lines:** `brokers/session.py:805-816` (`_write_journal` — tmp+`os.replace`, **no `os.fsync`**, no dir fsync).
- **Consequence:** Process-crash-safe, but power loss can lose the rename → venue truth (acks) lost while the (mock) venue also evaporates; with a REAL future venue this becomes a lost-ack hazard.
- **Existing protection:** Atomicity (no torn file); digest-verified load fails closed on corruption; adapters idempotent.
- **Proposed remediation (B4):** `fh.flush()+os.fsync(fh.fileno())` before replace + directory fsync; same for state store's replace path (F-09).
- **Regression test:** Filesystem-level: journal survives simulated abrupt termination is already process-level; power-loss is design-verified (fsync call presence pinned by test asserting on source/behavior contract — documented limitation).
- **Acceptance criteria:** fsync calls present on both file and directory in both journal writers; suite green.
- **Residual risk:** Minimal.

## F-09 — ExecutionStateStore: no directory fsync after os.replace

- **Severity:** MEDIUM — durability of the NAME `state.json` is not guaranteed on all filesystems after power loss.
- **File:lines:** `runtime/state.py:239-253` (`_atomic_write_json` — file fsync ✓, dir fsync ✗); journal creation same.
- **Proposed remediation (B4):** `os.open(dir, O_DIRECTORY)` + `os.fsync(dirfd)` after replace. **Regression test / acceptance:** presence-pinned + integration with F-03 lock. **Residual:** negligible.

## F-10 — SecurityManager.audit_log is fail-OPEN and writes inside the repo tree

- **Severity:** MEDIUM — contradicts the repo's own fail-closed persistence doctrine; silently invisible under F-04's unit.
- **File:lines:** `security.py:69-75` — path `src/../audit.log` (module-relative); `except (IOError, OSError): pass  # Audit log failure is non-critical`.
- **Consequence:** Audit events can be silently lost; writes pollute the source tree (gitignored, but present on disk).
- **Existing protection:** `.gitignore:15`; the hash-chained SecurityAuditTrail (FS-21/22) is the real audit surface and is fail-closed on verify.
- **Proposed remediation (B4):** Route to operator-configured path (default under state dir, never module-relative); raise/log-loud on write failure (fail closed for the audit channel); keep best-effort only for explicitly-decorated non-security diagnostics if any.
- **Regression test:** Unwritable audit path → startup failure or loud incident (not silence).
- **Acceptance criteria:** No `pass`-swallowed IO on audit paths; no writes inside package dir.
- **Residual risk:** Low.

## F-11 — SecurityAuditTrail.record: unlocked read-modify-write → chain fork

- **Severity:** MEDIUM — availability + authority ambiguity under concurrency.
- **File:lines:** `security.py:344-360` (read all entries → compute prev_hash/seq → append).
- **Proposed remediation (B4):** flock around read+append (shares the F-03 lock discipline); retry on contention. **Regression:** two processes × N records → linear chain, `verify()` true. **Acceptance:** no fork observable. **Residual:** low.

## F-12 — Torn journal tail bricks the state store; no repair runbook/tooling

- **Severity:** MEDIUM — fail-closed but availability-hostile; operator recovery is undocumented.
- **File:lines:** `runtime/state.py:157-161` (JSONDecodeError ⇒ StateStoreError, no truncation), `:190-192` (append+fsync window).
- **Proposed remediation (B4):** Documented `data-engine` recovery subcommand: verify snapshot integrity → offer explicit, audited tail-truncation of the journal with incident record + operator confirmation; NEVER automatic silent truncation. **Regression:** torn-tail fixture → recovery tool detects, reports exactly the damaged record count, refuses without confirmation flag. **Acceptance:** runbook exists; tool tested. **Residual:** low.

## F-13 — Feed-staleness wall-clock watchdog disabled by default

- **Severity:** MEDIUM — the single most important permissive default for a live paper deployment.
- **File:lines:** `runtime.py:151-163` (`max_feed_staleness_seconds = None`), enforcement `runtime.py:3496-3631`; bridge path honest-unmeasurable ⇒ fails closed (`3142-3159`); internal path feeds `last_bar_age_bars=0` (`2124`).
- **Proposed remediation (B4/documentation + Stage C):** Composition root sets an explicit staleness budget for operational sessions (paper default: 900s, matching feed gate); deployment docs mark the knob MANDATORY. Keep None only for deterministic replay with a loud startup line. **Regression:** config with watchdog unset in operational mode → composition root refuses. **Residual:** low.

## F-14 — Hardcoded risk limits and context values in runtime wiring

- **Severity:** MEDIUM — `market_open=True, paper_mode=True, model_valid=True, last_bar_age_bars=0` hardcoded at `runtime.py:2119-2127`; `RuntimeRiskLimits` hardcoded except `max_position_units` (`runtime.py:384-390`); `max_volatility=0.10`/`max_spread_fraction=0.01` at `2137,2140`.
- **Consequence:** Gate context is honest only within the deterministic replay frame; an operational deployment inherits unratified numbers (docstring itself admits `max_open_orders=10` has no prior design value — provisional pending ratification; NOTE: owner has NOW ratified 5/60s + 10 open + 1s spacing for paper mode in Part 3).
- **Proposed remediation (Stage C):** Composition root injects all context values from validated config; ratify the Part 3 defaults explicitly in config with provenance comments. **Regression:** composition root test asserts no hardcoded gate context in operational mode. **Residual:** low.

## F-15 — CI matrix omits declared Python 3.14; no lint/type/SAST/coverage gates

- **Severity:** MEDIUM — the declared runtime (`.python-version` 3.14) is never CI-tested (baseline verified locally this session on 3.14.8, but CI blind).
- **File:lines:** `.github/workflows/ci.yml:26` (matrix 3.11/3.12); no ruff/mypy/bandit/coverage anywhere in ci.yml or pyproject.
- **Proposed remediation (B4):** Add 3.14 (and 3.13) to matrix; add ruff (lint-only, non-blocking → blocking on new code paths) + coverage report artifact + bandit SAST step; keep frozen-blob verification untouched. **Regression:** CI green on all matrix legs. **Residual:** CI runtime cost.

## F-16 — pip-audit job not triggered on push to main

- **Severity:** MEDIUM — direct main pushes skip vulnerability auditing (weekly cron + PR only).
- **File:lines:** `ci.yml:5-9, 108`.
- **Proposed remediation (B4):** Add `push: branches: [main]` to the audit job triggers. **Regression:** workflow trigger inspection (dry-run). **Residual:** low.

## F-17 — `_canonical_instrument` hardcodes CRYPTO/SPOT — multi-asset registration blocked (Stage G3)

- **Severity:** LOW (today, paper-crypto-only) — but it is the single biggest G3 blocker: stocks/metals/forex cannot register via broker discovery.
- **File:lines:** `brokers/instruments.py:262-280`; asset-class vocabulary supports 6 classes (`schemas.py:30-35`); data manifests already multi-asset.
- **Proposed remediation (G3):** Derive AssetClass/ContractType from the capability descriptor + a per-broker instrument-type map with provenance; fail closed on unmappable instruments. **Regression:** registration tests per asset class (stock/crypto/metal/fx); unmapped class refused. **Residual:** medium (needs per-broker mapping data).

## F-18 — CI history secret scan covers only 4 token prefixes

- **Severity:** LOW — no PEM private keys / generic patterns in the history scan (the deploy validator checks PEM but CI history scan does not; gitleaks-style scanning absent).
- **File:lines:** `ci.yml:89-91`; `scripts/validate_deployment_templates.py:76`.
- **Proposed remediation (B4):** Extend scan set with PEM/OPENSSH/EC private key headers + xox/AIza prefixes. **Regression:** fixture secrets detected in a synthetic history in a self-test. **Residual:** low.

## F-19 — Side-band bridge records submission capacity on gate-pass (before venue call) — over-counting

- **Severity:** LOW — fail-SAFE direction (over-counts, never under-counts) but asymmetric with the authoritative path (record-after-ack), which can under-count on crash (see F-01/F-02).
- **File:lines:** `broker_execution.py:333-336` vs `runtime.py:2261/2276`.
- **Proposed remediation (B1/B2):** Both paths converge on the durable reservation ledger (reserve-before-call, finalize-on-outcome) — asymmetry disappears. **Regression:** ledger-level accounting identical for both paths. **Residual:** none after B1.

## F-20 — `crash.py` allows `dataset_version="UNRECORDED"` default

- **Severity:** LOW — fail-open edge in an otherwise fail-closed prediction contract: assessments can legally carry unrecorded provenance.
- **File:lines:** `prediction/crash.py:96`.
- **Proposed remediation (G7):** Refuse construction without an explicit dataset_version in operational paths (keep default only for explicitly-labeled test fixtures). **Regression:** operational constructor raises on missing version. **Residual:** low.

## F-21 — CLI usage docstring/argument mismatch

- **Severity:** LOW — usage says `validate <dataset_id>` but parser registers no positional.
- **File:lines:** `cli.py:4` vs `cli.py:49`.
- **Proposed remediation (B4):** Fix docstring or register the argument (prefer: register argument — matches G6 reporting direction). **Residual:** none.

## F-22 — Test storage dirs at fixed paths (repo-root + /tmp collisions)

- **Severity:** LOW — hygiene: `test_storage*` dirs created at repo root by `tests/test_data_engine.py:419+`; fixed `/tmp/test_storage_*` paths in `tests/test_redteam.py:180+` collide across users/CI.
- **Proposed remediation (B4):** `tmp_path` fixtures; add `test_storage*` to cleanup. **Residual:** none.

## F-23 — Kill-switch reduce-only carve-out at the venue gate (INFO — documented, tracked)

- **Severity:** INFO — a reduce-only order can traverse an ACTIVE kill switch at the session boundary (`broker_execution.py:1188-1206`); narrow, cross-checked, documented; fill-time enforcement remains the backstop (`runtime.py:2358-2397`).
- **Action:** Track only; add a dedicated contract test pinning the carve-out's verifiable-reduce-only precondition if absent. **Residual:** accepted, documented.

## F-24 — TIMEOUT retry safety rests on adapter idempotency contract (INFO)

- **Severity:** INFO — bounded retries on TIMEOUT are safe only because the adapter contract mandates idempotency (`interface.py:60-62`; acknowledged at `errors.py:16-19`); a future non-idempotent venue could double-execute.
- **Action:** When any non-mock adapter is ever proposed (G5), require an idempotency verification suite as part of the adapter acceptance gate — fail closed on unverified idempotency. **Residual:** none while all adapters are deterministic mocks.

## F-25 — MAC custody implemented but NOT OPERATIONAL (no key provisioned) (INFO)

- **Severity:** INFO — keyed-MAC ledger custody is complete but unkeyed in practice (GOV-04); unkeyed chains are re-forgeable end-to-end (threat model `mac_custody.py:5-11`). Known governance decision, honestly recorded in `docs/READINESS_EVIDENCE_INVENTORY.md:178`.
- **Action:** Stage C composition root provisions `RUNTIME_LEDGER_MAC_KEY` via the documented env/key-file path for operational deployments; paper-soak evidence must record key_id. **Residual:** governance-owned.

---

## Register summary

| ID | Sev | One-line | Stage |
|---|---|---|---|
| F-01 | HIGH | Volatile submission-rate accounting (restart wipes budget) | B1 |
| F-02 | HIGH | No atomic reservation / cross-process capacity guarantee | B1 |
| F-03 | HIGH | Zero file locking; fixed tmp names; unlocked RMW | B4 |
| F-04 | HIGH | systemd: ProtectSystem=strict without ReadWritePaths | B4 |
| F-05 | HIGH | No production composition root | C |
| F-06 | MED | Uncapped authoritative venue | B2 |
| F-07 | MED | Venue-accept→OMS-submit crash window unpolled | B3 |
| F-08 | MED | Session journal not fsynced | B4 |
| F-09 | MED | State store: no directory fsync | B4 |
| F-10 | MED | Fail-open security audit_log in repo tree | B4 |
| F-11 | MED | SecurityAuditTrail unlocked RMW | B4 |
| F-12 | MED | Torn journal tail bricks store; no repair tool | B4 |
| F-13 | MED | Feed watchdog off by default | C |
| F-14 | MED | Hardcoded risk limits/gate context | C |
| F-15 | MED | CI omits 3.14; no lint/SAST/coverage | B4 |
| F-16 | MED | Dep audit not on push to main | B4 |
| F-17 | LOW | Instruments hardcode CRYPTO/SPOT (G3 blocker) | G3 |
| F-18 | LOW | Secret scan 4 prefixes only | B4 |
| F-19 | LOW | Bridge/authoritative accounting asymmetry | B1 |
| F-20 | LOW | dataset_version UNRECORDED default | G7 |
| F-21 | LOW | CLI docstring/arg mismatch | B4 |
| F-22 | LOW | Fixed test storage paths | B4 |
| F-23 | INFO | KS reduce-only carve-out (documented) | track |
| F-24 | INFO | TIMEOUT retry idempotency assumption | G5 gate |
| F-25 | INFO | MAC custody not operational | C |

**No finding weakens a risk control to make tests pass; all remediations preserve or strengthen fail-closed posture. PAPER_READY remains FALSE.**

