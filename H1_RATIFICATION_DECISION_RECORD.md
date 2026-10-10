# H-1 RATIFICATION DECISION RECORD

**Document ID:** GOV-H1-002 · **Version:** 2.0.0 · **Date:** 2026-10-10
**Status:** RATIFIED — Option A (containment) approved by the operator
human principal, recorded in-session per the repository's formal
ratification mechanism. NO handwritten or cryptographic signature was
fabricated; the approval evidence is the operator's own authorization
text quoted verbatim in §6 below.
**Supersedes/extends:** H1_FORMAL_DECISION_ANALYSIS.md (analysis, v1.0.0);
this record v1.0.0 (sha256
`588b1ede477a65d02ceac6ee4d87a5b1f9555cc86336b22581a0a16293b0f734` at
commit `f1bfe02fab36724a439702e82dc83f9a851444fb` — the exact text the
approval below ratifies)

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
| C. Keep OPEN/CONTAINED (status quo) | H-1 remains a recorded, contained, unfrozen risk | None (former state) |

## 4. What This Record Does NOT Do

It does not fabricate a handwritten signature, invent a cryptographic
identity, or modify any frozen artifact. The operator authorization
below is the human principal's recorded decision, expressed in the
operator's own instruction text and recorded here verbatim with full
provenance (channel, session, timestamp) — the exact mechanism this
record's v1.0.0 §4 reserved to "the repository's formal ratification
mechanism (a human principal's recorded decision)".

## 5. Ratified Decision Text (exact, from v1.0.0 §3)

> **A. RATIFY containment** — H-1 closes; frozen wall-clock defect
> accepted as contained forever. Authority: Human principal.

## 6. Operator Authorization Record (the human principal's decision)

```text
Decision ID:     GOV-H1-002-RATIFY
Decision:        A — RATIFY the H-1 / F-04 containment
Approver:        The repository operator (human principal, identified
                 by session ownership of the repository and its
                 governance program)
Approver kind:   human (in-session operator authorization — the
                 mechanism this record reserved in v1.0.0 §4; no
                 signature fabricated)
Evidence:        Operator mandate, quoted verbatim:
                 "H-1 ratification: I authorize the previously
                 documented H-1 decision, subject to the exact decision
                 text in the authoritative repository specification.
                 Retrieve that text and record my approval against the
                 precise version and hash. If the decision requires
                 clarification beyond the documented scope, report the
                 ambiguity rather than inventing terms."
                 The "previously documented H-1 decision" is the
                 documented RECOMMENDATION of H1_FORMAL_DECISION_ANALYSIS.md
                 ("Recommendation: OPTION A — CONTAINMENT") and the
                 ratification option offered by this record §3/§5 —
                 RATIFY (Option A). No clarification beyond the
                 documented scope was required; no terms were invented.
Ratified text:   §5 above (Option A row, verbatim from v1.0.0)
Ratified record: H1_RATIFICATION_DECISION_RECORD.md v1.0.0
                 sha256 588b1ede477a65d02ceac6ee4d87a5b1f9555cc86336b
                 22581a0a16293b0f734 @ commit f1bfe02fab36724a439702e8
                 2dc83f9a851444fb
Channel:         zai-web (IM session web-a816f89a-8d02-42d6-b1a7-
                 6577eb1dc53e, chat 218858c8-6142-48a8-b177-
                 8668467ef6c4)
Recorded at:     2026-10-10 (PKT) — mandate received and executed in the
                 same session
Executed by:     ZAI (controlled agent) — RECORDING ONLY: the decision
                 and its authority are the operator's; the agent
                 contributed no approval of its own.
```

## 7. Effect

- **H-1 = CLOSED (RATIFIED — containment accepted permanently).** The
  frozen Phase 3 `Candle.to_hash()` wall-clock limitation is accepted
  as contained forever, exactly as Option A defines.
- The containment controls stay under regression enforcement (Phase 4
  identity never calls `Candle.to_hash()`; SUB-25 / T-H02 /
  mutation-verified detection gates remain mandatory).
- Frozen artifacts remain untouched: SUB-18 11/11 blobs + 13/13
  manifest re-verified BEFORE and AFTER this cycle (see the cycle's
  final report).
- GOVERNANCE_READY's H-1 component is now SATISFIED by recorded human
  decision. GOVERNANCE_READY as a whole remains FALSE until its other
  documented components close (real-data source approval, credential
  rotation confirmation, keyed-MAC custody operational status).

## 8. Reversal

Per the analysis §R5 ("decision reversibility"), choosing A does not
foreclose a future Option B amendment window: a NEW human decision
record with its own authorized window would be required to reopen the
frozen contract. Nothing in this record creates such a window.
