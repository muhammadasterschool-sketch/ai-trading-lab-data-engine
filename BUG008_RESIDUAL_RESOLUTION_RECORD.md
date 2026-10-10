# BUG-008 RESIDUAL RESOLUTION RECORD

**Document ID:** GOV-B08-001 · **Version:** 1.0.0 · **Date:** 2026-10-10
**Status:** CLOSED (residual) — permanent acceptance of the
runtime-boundary adapter, authorized by the operator human principal.
Frozen Phase 3 contracts and artifacts remain byte-identical
(SUB-18 11/11 blobs + 13/13 manifest re-verified before AND after this
cycle).
**Resolves:** the BUG-008 PARTIAL/rule-deferred residual recorded by
`P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md` (15/16 CLOSED · 1
PARTIAL) and carried by `PAPER_TRADING_READINESS_FINAL_REPORT.md`
§13.5 / §15.5 ("manifest-refresh authorization or permanent
acceptance of the runtime-boundary adapter").

---

## 1. The Defect (recap)

BUG-008 (pre-paper forensic cycle): 13 mutable fields (9 frozen
strategy-domain fields + 4 manifest-pinned `schemas.py` fields) remain
mutable inside SUB-18 manifest-pinned files that are IMMUNE BY RULE —
they cannot be made immutable without modifying frozen Phase 3
artifacts and recomputing pinned hashes. The P1 correction window
therefore deferred them under frozen/manifest immunity with a
runtime-boundary adapter as containment.

## 2. Operator Decision (verbatim evidence)

> "BUG-008: I authorize the documented residual-resolution path that
> preserves all frozen Phase 3 contracts and artifacts. Implement only
> the permitted boundary/adapter changes. Do not alter frozen
> artifacts or pinned hashes."

```text
Decision ID:     GOV-B08-001
Decision:        PERMANENT ACCEPTANCE of the runtime-boundary adapter
                 (the documented residual path that preserves frozen
                 contracts). The manifest-refresh alternative is NOT
                 authorized (it would alter frozen artifacts/pinned
                 hashes).
Approver:        The repository operator (human principal)
Approver kind:   human (in-session operator authorization)
Channel:         zai-web (IM session web-a816f89a-8d02-42d6-b1a7-
                 6577eb1dc53e, chat 218858c8-6142-48a8-b177-
                 8668467ef6c4)
Recorded at:     2026-10-10 (PKT)
Executed by:     ZAI (controlled agent) — recording + the authorized
                 boundary/adapter strengthening only.
```

## 3. The Accepted Contract (as now permanently in force)

`src/data_engine/runtime/vocabulary.py` —
`freeze_strategy_boundary(model) -> Mapping[str, Any]`:

1. Any strategy-domain (or schemas.py) object crossing into the
   runtime is DEEP-COPIED; the runtime receives a read-only mapping
   snapshot only.
2. The ORIGINAL object is never retained or mutated by the runtime.
3. The 13 manifest/frozen-immune mutable fields therefore can never be
   mutated through any runtime code path — the residual exposure is
   contained without touching any pinned file.
4. The vocabulary bridge (`strategy_side_to_runtime` and friends)
   remains the ONE authoritative cross-domain translation surface
   (RT-F6) — no ad-hoc conversions in callers.

## 4. Strengthening Delivered With This Record (permitted boundary work)

This cycle strengthened the acceptance with additional regression
coverage beyond the pre-existing tests
(`tests/test_finding_closures.py::TestBUG008Disposition`):

- **13-field enumeration pinned in tests** — the deferred fields are
  now enumerated as a documented constant set in the regression test
  (`tests/test_bug008_boundary_closure.py`), with a test proving the
  boundary snapshot carries them and that mutating the runtime-side
  snapshot never affects a frozen-domain model.
- **Call-site sweep** — a source-scan regression test proving every
  runtime module that imports from the frozen strategy domain goes
  through the boundary/bridge surface (no direct mutable retention).
- **Frozen preservation re-proven** — SUB-18 manifest 13/13 + blobs
  11/11 verified BEFORE and AFTER the change set (independent scripts;
  see the cycle's final report). No pinned hash changed.

## 5. Final Disposition

**BUG-008 = CLOSED (residual accepted permanently under GOV-B08-001).**
The P2 register's CONDITIONAL-PASS condition "BUG-008 residual
authorization path" is satisfied by this record; the residual is no
longer deferred but RESOLVED BY ACCEPTED CONTAINMENT — with the frozen
contract's byte-identity as the standing proof that the acceptance
never altered what it protects.

Reopening (migrating the 13 fields inside the frozen files) would
require a NEW operator decision + authorized manifest-refresh window
(the Option-B path H1_FORMAL_DECISION_ANALYSIS.md describes for H-1);
nothing in this record creates such a window.
