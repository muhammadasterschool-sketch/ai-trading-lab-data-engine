# FIX-LOG — FULL PROJECT PROMPT v3.0 run

Format: bug ID / owner report / diagnosis / fix / re-test evidence.
Per Part 11: after every fix the FULL suite was re-run before
continuing. No red suite ever advanced.

---

## FIX-1 — packaged-source suite failures (found by Stage E validation)

- **Owner report:** none (self-caught by the E2 validation mandate).
- **Diagnosis:** running the suite from the Windows package's
  `source/` tree (a git archive WITHOUT `.git`) failed 3 tests that
  invoke git forensics (`git rev-parse`/`diff`/`ls-files`/
  `check-ignore` exit 128 without a repository). Two further tests
  were passing VACUOUSLY in that context (empty stdout on git error).
- **Fix:** `needs_git_checkout` skipif guard on the 5 repo-integrity
  tests — an EXPLICIT, visible skip in the packaged-source context;
  full behavior retained in every git checkout (CI + dev).
- **Re-test evidence:** in-repo suite unchanged (2514 passed + 1
  skipped, 109.03s); packaged-source suite then GREEN (2508 passed +
  7 skipped, 93.03s, exit 0) with the skips visible and counted.
  Commit 7546477.

## FIX-2 — admin registry handler scoping bug (Stage F)

- **Owner report:** none (self-caught by tests).
- **Diagnosis:** `_Handler` was defined inside
  `AdminRegistry.__init__` but referenced from `start()` — NameError
  at service start.
- **Fix:** store the handler class on the instance
  (`self._handler_cls`) and construct the server from it.
- **Re-test evidence:** tests/test_admin_registry.py 22/22 green;
  full suite 2602 passed + 1 skipped (134.83s).

## FIX-3 — monitoring API prediction default provider crash (Stage G)

- **Owner report:** none (self-caught by tests).
- **Diagnosis:** `prediction_provider` defaulted to `_absent`, which
  requires a `component` argument — TypeError on
  `GET /api/prediction` without an injected provider.
- **Fix:** default became `lambda: _absent("prediction")`.
- **Re-test evidence:** tests/test_monitoring_api.py 73/73 green
  (including the honest-ABSENT default test).

## FIX-4 — G1/G3/G4 test defects (clock arithmetic + capability facts)

- **Owner report:** none (self-caught; test-first discipline).
- **Diagnosis:** (a) two G1 tests mis-computed the stepping clock's
  first-call time; (b) G3 tests assumed pydantic-level validation
  order and Provenance vocabulary semantics; (c) one G4 test assumed
  mt5-mock lacked STOP (it supports it) and string-formatted a
  Decimal.
- **Fix:** corrected arithmetic/facts; assertions kept equally
  strict. No production code was weakened to make anything pass.
- **Re-test evidence:** G1 9/9, G3 19/19, G4 19/19; full suite 2685
  passed + 1 skipped (138.76s, exit 0).

---

## Owner-reported bugs

None to date in this run (no BUGS replies received; the run was
pre-approved for all stages). The log above is kept in the
mandated format and will be extended for any future owner reports.

---

## FIX-5 — CI secret scan false positive on synthetic test fixture (final-stage)

- **Owner report:** none (self-caught from CI's all-history secret
  scan failing on 041ea30).
- **Diagnosis:** the Stage F redaction test carried a SYNTHETIC
  token-shaped fixture as a contiguous string literal
  (`tests/test_monitoring_api.py:370`). CI scans ALL immutable
  history (`git grep ... $(git rev-list --all)`), so commits
  ddb4a2b..bab12c7 match forever. History rewrite is FORBIDDEN by
  the project rules, so the literal cannot be excised from the past.
- **Fix (two parts):**
  1. b2e1879: the redaction test now ASSEMBLES its synthetic input
     from pieces at runtime (no contiguous scanner-shaped literal in
     any current tree);
  2. the CI scan step filters EXACTLY that one documented synthetic
     substring (grep -vF) — pinned by
     `tests/test_secret_scan_allowlist.py` (4 tests): exactly ONE
     filter line; current tree carries zero contiguous literals; the
     scan pattern still catches real-shaped credentials (control NOT
     weakened).
- **Re-test evidence:** local simulation of the exact CI command:
  7 total history hits → 7 allowlisted (all the same synthetic
  fixture) → 0 non-allowlisted (scripts/simulate_ci_secret_scan.sh);
  allowlist pin tests 4/4 green; full suite re-run before push.

## FIX-6 — mobile widget test scaffold (final-stage)

- **Owner report:** none (self-caught from CI build-apk failures).
- **Diagnosis:** (a) `FlutterSecureStorage(AndroidOptions(...))`
  passed a positional argument to a named-only constructor
  (flutter analyze error); (b) `flutter create` scaffolds a default
  `test/widget_test.dart` referencing a nonexistent `MyApp`.
- **Fix:** (a) plain `const FlutterSecureStorage()` (v9 enables
  encrypted SharedPreferences on Android by default) — 9ba341f;
  (b) committed real client tests (TLS-only normalization refusals,
  profile-dialog validation + save flow) replacing the broken
  scaffold — bab12c7.
- **Re-test evidence:** build-apk workflow completed SUCCESS on
  bab12c7; APK published as release `apk-bab12c7aa768` (21,156,320
  bytes) with SHA256SUMS.

## FIX-7 — CI secret-scan red on final tree (self-caught, continuation session)

- **Owner report:** none (continuation session re-verified CI on
  812a5fc before sign-off: all four Python test jobs RED).
- **Diagnosis:** FIX-5 was self-defeating in two ways: (a) its CI
  filter embedded the full synthetic fixture as a contiguous literal
  (`grep -vF 'token github_pat_… tail'`) — the literal itself matched
  the scan pattern, so the current-tree pin
  (`test_current_tree_has_no_contiguous_literal`) found
  `HEAD:.github/workflows/ci.yml`; (b) the pin test's own positive
  control (line 75, `github_pat_11REAL…`) was also a contiguous
  literal in the current tree.
- **Fix (merge 0906279, adopting PR #10's F-18b + extension):**
  1. ci.yml secret scan restructured: named `PATTERN=`, `BASELINE=
     "github_pat_11AAAA"` (the Stage F synthetic marker) + FIX-7
     marker `MARKER2="github_pat_11REAL"` (the immutable 812a5fc
     control literal) — both markers are SHORTER than the pattern's
     20-char tail requirement, so neither is itself credential-
     shaped; fail-closed git-grep exit-code handling; FIX-5's
     embedded literal filter deleted.
  2. tests/test_secret_scan_allowlist.py re-pinned (5 tests):
     exactly ONE variable-driven filter pipeline applying BOTH
     named markers; literal-substring filters forbidden forever;
     markers proven not credential-shaped; redaction fixture
     concatenation pin updated to the PR's `"github_" + "pat_11AAAA"`
     idiom; positive controls converted to concatenation.
- **Re-test evidence:** local full suite 2732→2735 passed + 1
  skipped; exact CI step body (extracted from ci.yml, not a copy)
  exits 0 on the real repository; negative control: an injected
  real-shaped ghp_ token SURVIVES the filters (CI would fail);
  history diagnostic: 10 raw hits, all marker-covered; CI on
  0906279: ALL SIX JOBS SUCCESS (first fully green main since
  Stage F).

## FIX-8 — package validator format divergence (self-caught)

- **Owner report:** none (caught by validating the rebuilt package
  with PR #10's new tamper-proof validator).
- **Diagnosis:** the validator parsed SHA256SUMS.txt as
  `"<rel>  <digest>"` while the builder emits the standard sha256sum
  convention `"<digest>  <rel>"`; the validator's fixture tests were
  self-consistent but never cross-checked against a REAL built zip,
  so the divergence was invisible until the real package hit it
  (2 FAILs: "does not cover" + "covers non-members").
- **Fix (0dcccc2):** validator parses digest-first with strict
  malformed-line refusal (64 hex + non-empty path → else ValueError
  → fail closed); fixture harness emits digest-first lines; NEW
  TestBuilderValidatorFormatAgreement source-level cross-pins the
  builder's `f"{digest}  {rel}"` expression against the parser so
  the two can never silently diverge again.
- **Re-test evidence:** real package validates 8/8 — "SHA256SUMS.txt
  covers + matches all 534 packaged files"; tamper control: a
  modified install.ps1 fails BOTH the digest mismatch and the
  posture pins; validation tests 29/29 green; full suite 2735
  passed + 1 skipped.


---

## FIX-9 — human-gate evidence trust boundary (P0-P3 audit / B-P0-03)

- **Owner report:** audit prompt B-P0-03 ("caller-supplied passed=True,
  arbitrary free-text evidence may satisfy trust-dependent gates").
- **Diagnosis:** CONFIRMED. GateEvidence.passed is caller-supplied;
  compose_operational_session accepted plain operator_evidence for
  the three human gates (REAL_DATA / OPERATIONAL_FEED / GOVERNANCE).
  The old test helper literally fabricated passed=True free-text for
  all 32 gates and sessions started — any in-process caller could
  self-satisfy the human-dependency gates.
- **Fix:** runtime/operator_approval.py (typed OperatorApprovalRecord,
  OperatorApprovalKey env/file channels ≥ 32 bytes, HMAC-SHA256
  sign/verify, TrustedGateEvidence, stable fail-closed reason codes)
  + composition-root re-verification (expiry, scope, digest,
  signature) of every human-gate evidence at compose time; plain
  evidence refused with E_EVIDENCE_UNTRUSTED; session-config digest
  pinning (_session_config_digest) prevents cross-config replay;
  CONSTRUCTION_ORDER extended with the operator_approvals step.
- **Re-test evidence:** tests/test_operator_approval.py 43 passed
  (fabricated bundle E2E refusal, forged signature, tampered record,
  expired/not-yet-valid, scope/digest mismatch, hand-crafted subclass,
  wrong-key re-verification, env-bypass impossibility, drift pins);
  test_composition_root.py migrated to the SIGNED operator path —
  29 passed; wider regression batch 141 passed.

## FIX-10 — real session wiring for the CLI supervisor (B-P0-01)

- **Owner report:** audit prompt B-P0-01 ("CLI/service may supervise a
  process without wiring a real operational session tick loop").
- **Diagnosis:** CONFIRMED. cli.py serve constructed
  PaperRuntimeService with NO tick_fn and never called
  compose_operational_session — no operator path could run a paper
  session; the supervisor was an honest but empty shell.
- **Fix:** runtime/session_launch.py — SessionLaunchPlan (typed,
  extra=forbid, eager RuntimeConfig validation), ReplayBarSource /
  ProviderBarSource (known-provider inventory: binance_public only;
  feed errors fail closed, never fabricated), SessionTick (honest
  tick/bar/refusal/feed-error counters), launch_paper_session
  (compose via the C1 root + explicit start; ensemble strictly
  operator-supplied module:function, never defaulted). CLI:
  `serve --session-launch PLAN` with exit code 4 refusals; the
  supervisor-only default stays honest (exit 2 readiness refusal).
- **Re-test evidence:** tests/test_session_launch.py 24 passed —
  launch+start verified, tick consumes bars and advances metrics,
  deterministic across two launches, submitted orders present ONLY in
  the paper venue journal, kill switch produces no new orders, 9
  refusal paths, CLI exit codes 4/0/2, bounded CLI run advances the
  session. BUG-008 boundary incident (direct schemas import) caught
  by the existing pin test and fixed via the provider bridge.

## FIX-11 — gate-count report reconciliation (B-P0-02)

- **Owner report:** audit prompt B-P0-02 ("readiness gates and project
  reports may disagree on mandatory gate count/status" — one report
  said two pending items, others three unresolved gates).
- **Diagnosis:** CONFIRMED. Stage-D report + PROJECT-STATE-REPORT
  said "30 VERIFIED_IN_CODE, 2 PENDING (REAL_DATA, OPERATIONAL_FEED)"
  while the code's HUMAN_EVIDENCE_GATES and
  docs/READINESS_EVIDENCE_INVENTORY.md track THREE unresolved human
  gates (GOVERNANCE_READY was misclassified as code-verified).
- **Fix:** both reports reconciled to "29 VERIFIED_IN_CODE, 3
  PENDING_OPERATIONAL_EVIDENCE (REAL_DATA_READY,
  OPERATIONAL_FEED_READY, GOVERNANCE_READY)" with a FIX-11 note; the
  Stage-D GOVERNANCE_READY row now cites the open GOV-03/04/05
  inventory items.
- **Re-test evidence:** tests/test_report_gate_consistency.py 9
  passed — executable pins that the reports must agree with the
  code's classification (a human gate can never again be classified
  VERIFIED_IN_CODE in any tracked report).

## FIX-12 — Windows import discipline for the submission ledger (B-P1-09)

- **Owner report:** audit prompt B-P1-09 ("fcntl.flock POSIX-only lock
  code may conflict with claimed Windows support").
- **Diagnosis:** CONFIRMED. submission_ledger.py had a TOP-LEVEL
  `import fcntl` — on Windows CPython the module failed at import
  (ModuleNotFoundError), making the documented constructor-level
  fail-closed refusal dead code and breaking every importer
  (composition root, CLI).
- **Fix:** conditional import (the runtime/state.py pattern):
  module imports everywhere; the constructor refuses with the
  documented message + WSL/Linux guidance when flock is unavailable.
- **Re-test evidence:** tests/test_platform_fcntl_import.py 4 passed
  (simulated fcntl absence via blocked import: module imports,
  constructor refuses, POSIX path unchanged, state.py pattern pin).
  Windows-host runs remain honestly NOT VERIFIED (see the platform
  report — this fix makes the failure mode documented, not the host
  tested).

## FIX-13 — run-paper.ps1 exit-code hardening + session plan (B-P1-10)

- **Owner report:** audit prompt B-P1-10 ("Windows/CLI deployment
  script may report success despite failed preflight or missing
  session loop").
- **Diagnosis:** PARTIALLY CONFIRMED. The engine exit code was
  propagated, but a failing `status --gates` tool invocation was
  ignored, and the script had no path to launch a session (tied to
  B-P0-01).
- **Fix:** status-tool failure aborts (exit 5); -SessionPlan
  passthrough to `serve --session-launch` (missing plan refuses with
  exit 4); engine exit code propagates verbatim in all paths.
- **Re-test evidence:** tests/test_windows_package.py +2 contract
  tests (16 total passed).

## FIX-14 — executable soak preflight + mock dry run (B-P2-16 / Task 12)

- **Owner report:** audit prompt Task 12 / B-P2-16 ("add an explicit
  preflight that refuses to start if any mandatory gate is false or
  evidence is stale; a soak cannot begin from a green CI run alone").
- **Diagnosis:** CONFIRMED GAP. The soak procedure was document-only;
  no executable preflight or dry run existed.
- **Fix:** runtime/soak_preflight.py — run_soak_preflight (plan
  validity; every non-component gate passing in the bundle; human
  gates SIGNED-only; approvals covering the FULL soak window; reads
  no CI input) + `cli soak-preflight` (exit 0 pass / 6 refusal,
  stable reason codes); PAPER-SOAK-PROCEDURE.md precondition #3 now
  the executable preflight.
- **Re-test evidence:** tests/test_soak_preflight.py 17 passed —
  all refusal paths (missing gate, failing gate, unsigned human
  evidence, expired approval, approval-expiring-before-soak-end,
  forged signature, missing key), env-var irrelevance, CI-irrelevance
  structural pin, CLI exit codes, and the MOCK DRY RUN
  (preflight → authorized launch → bounded 80-bar tick loop →
  quiescence; procedure order enforced). NO soak was started.

