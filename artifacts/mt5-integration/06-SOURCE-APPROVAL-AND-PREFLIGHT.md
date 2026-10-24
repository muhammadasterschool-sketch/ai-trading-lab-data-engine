# 06 — Source-Approval & Launch-Preflight Instructions

The feed is implemented but **approves nothing**. This document maps
the operator's path from "code exists" to "source may be used in a
paper session" — without touching any governance rule.

## 1. Where the new source stands

- `build_feed_source_registry()` now carries FIVE candidates, all
  UNVETTED: `binance-public-spot`, `exness-mt5-demo`,
  `forex-15m-ohlc`, `stocks-15m`, `metals-15m`.
- `BLOCKED_MARKETS` is unchanged: forex/metals/stocks 15-minute paper
  execution stays blocked until a human SRC-APPROVAL exists AND real
  coverage is verified.
- No `submit_approval` call exists anywhere in the implementation or
  tests for the new source (a test asserts the whole registry stays
  UNVETTED).

## 2. Approval prerequisites (all mandatory, in order)

1. **Terminal evidence** — run the Windows workflow
   (03-WINDOWS-HOST-SETUP.md) and archive the artifacts listed in
   05-TERMINAL-EVIDENCE-OR-BLOCKED.md. Flipping 05's table to RUN is
   the precondition for any approval discussion.
2. **Validated symbol map** — every symbol intended for use must be in
   the digest-stamped validated map (probe `--validate-map`).
3. **Freshness observations** — staleness ages during open market AND
   documented weekend behaviour.
4. **Terms review** — the Exness client agreement / market-data terms
   for DEMO data use, recorded in the SRC-APPROVAL `License basis`
   field (exact document identity + review date; "UNKNOWN" is NOT
   approvable).
5. **Human SRC-APPROVAL decision** — fill the §5 template of
   `docs/OPERATOR_SOURCE_APPROVAL_PACK.md` and record it via the §6
   human-only `submit_approval` (approver_kind="human"; "ai" is
   structurally rejected).

## 3. What approval does and does NOT change

Exactly as §7 of the approval pack states for the crypto pilot:

- `OPERATIONAL_FEED_READY` can only become TRUE when the gate ALSO
  passes on live inputs (validated closed bars, correct canonical
  mapping, warm-up, freshness within tolerance, no gaps/duplicates).
- `REAL_DATA_READY` requires the instrument registered with
  observation-derived verified coverage — the feed's provenance
  artifacts are the raw material, not the verdict.
- `PAPER_READY` still requires ALL 32 gates; `LIVE_AUTHORIZATION`
  remains NOT_AUTHORIZED unconditionally.

## 4. Launch preflight (unchanged rules, now with a real-feed path)

When a paper session is eventually launched with MT5-sourced data:

1. Author `launch-plan.json` exactly as the soak-preflight requires
   (23 operator-recorded gate evidences + fitted model module:function
   + signed human approvals covering the full window).
2. `uv run data-engine soak-preflight launch-plan.json` — must exit 0.
3. Only then `--session-launch` composes the session; the composition
   root re-verifies approvals (HMAC) at start and fails closed listing
   every failed gate.
4. The 30-day soak remains mandatory and requires separate, explicit
   owner authorization AFTER all mandatory gates genuinely pass.

The MT5 feed integrates at the DATA layer only: strategy output keeps
flowing to the governed internal paper broker/simulator; no routing,
venue or execution change exists to configure.
