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
