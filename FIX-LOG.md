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
