# H-1 RATIFICATION DECISION RECORD

**Document ID:** GOV-H1-002 · **Version:** 1.0.0 · **Date:** 2026-10-09
**Status:** HUMAN_DECISION_REQUIRED — no approval fabricated (mandate §8/§57)
**Supersedes/extends:** H1_FORMAL_DECISION_ANALYSIS.md (analysis, v1.0.0)

---

## 1. Decision Requested

Ratify (or reject) the H-1 / F-04 CONTAINMENT of the wall-clock
contamination in the frozen Phase 3 `Candle.to_hash()` identity path.

## 2. Background (verified facts)

- The frozen Phase 3 contract (SUB-18 manifest, 13 pinned files)
  computes `Candle.to_hash()` over fields including
  `provider_timestamp`, whose value is captured with wall-clock time —
  the F-04 defect. Frozen-file modification is IMMUNE BY RULE
  (manifest hashes + frozen blob identity; verified 11/11 + 13/13 at
  every gate since).
- Containment controls in force (Phase 4A.1 + P1/P2 verified):
  - Phase 4 identity paths never call `Candle.to_hash()`
    (ARCH-F6 correction: `_compute_raw_hash` excludes
    `provider_timestamp`; deterministic).
  - Runtime identity (`rt*.` family) NEVER depends on any frozen
    hash method (documented + enforced in `runtime/identity.py`).
  - The pre-existing status-metadata line in
    `docs/strategy_engine_design.md` (COMPLETE→NO-GO, Blocker-2
    governance record) was disclosed in the P2 report §4 and is NOT a
    P1 change.

## 3. Options

| Option | Consequence | Authority required |
|---|---|---|
| A. RATIFY containment | H-1 closes; frozen wall-clock defect accepted as contained forever | Human principal |
| B. REJECT + manifest-refresh window | Frozen files change; manifest + hashes recomputed; full regression re-run | Human principal + new authorized window |
| C. Keep OPEN/CONTAINED (status quo) | H-1 remains a recorded, contained, unfrozen risk | None (current state) |

## 4. What This Record Does NOT Do

It does not close H-1, does not fabricate approval, and does not
modify any frozen artifact. Per the mandate §8: only the repository's
formal ratification mechanism (a human principal's recorded decision)
may change H-1's state.

## 5. Signature Block (to be completed by a human principal)

```
Principal: ____________________  (required, human)
Principal kind: human
Decision: [ ] A — RATIFY   [ ] B — REJECT + refresh   [ ] C — keep OPEN
Reason:   ____________________
Date:     ____________________
```

Until this block is completed by an identified human principal,
**H-1 = OPEN / CONTAINED / HUMAN_DECISION_REQUIRED**.
