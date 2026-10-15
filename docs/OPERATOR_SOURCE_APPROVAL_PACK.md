# OPERATOR SOURCE-APPROVAL PACK

```text
Document Type:  Human-decision evidence pack + decision template
Phase:          Paper-readiness engineering cycle (2026-10-11/12)
Authority:      B — CURRENT SUPPORTING (the DECISION AUTHORITY is the
                operator; this pack prepares, never makes, decisions)
Status:         CURRENT
Version:        1.0.0
Companion code: src/data_engine/platform/feed_source_candidates.py
                (machine-readable UNVETTED candidate records)
Related policy: PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md §5/§7.1
```

---

## 1. Purpose

The repository now contains REAL market-data machinery: a Binance
public spot-klines adapter (crypto pilot, BTCUSDT 15m), the forex
USD-base rate-series reader (structurally NOT a candle feed), and
the operational-feed composition that wires them into the 32-gate
readiness system (see `MASTER_MARKET_DATA_IMPORT_RECORD.md` §10 and
the fresh §0C readiness amendment).

**None of that machinery approves anything.** Source approval is a
HUMAN-ONLY decision (`PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md`
§5; the registry structurally rejects AI approvals). This pack gives
the operator the exact evidence, the exact template, and the exact
record-making commands — the decision itself is yours.

## 2. The four evidence classes (never conflated)

| Class | What it is | Who can produce it | Current status |
|---|---|---|---|
| 1. Endpoint connectivity | The endpoint responded once | Anyone (smoke script) | Observed (operator Pydroid 3 run + optional `scripts/binance_public_smoke.py`) |
| 2. Basic OHLCV validity | Returned rows pass schema checks | Tests (mocked) + smoke | Proven for the adapter (41 unit tests + smoke path) |
| 3. Operational feed readiness | Approved + provisioned + fresh + mapped + warm-up | Gate machinery + HUMAN approval | **Machinery COMPLETE; verdict FALSE (no approval)** |
| 4. Research-dataset verification | Nine-stage REAL_VERIFIED chain | HUMAN + evidence chain | Not started (0 REAL_VERIFIED) |

## 3. Candidate: `binance-public-spot` (crypto pilot)

Read this BEFORE deciding — machine-readable record:
`src/data_engine/platform/feed_source_candidates.py::candidate_record("binance-public-spot")`.

**What is known (first-hand, in-repo):**
- Adapter mechanics: 41 deterministic offline tests pass
  (`tests/test_provider_binance_public.py`); closed-candle
  enforcement, bounded retries/pagination, raw-response SHA-256
  provenance, rate-limit mapping (429/418 → typed error, no retry
  storm), duplicate/gap/ordering checks.
- End-to-end gate integration: 29 tests
  (`tests/test_feed_composition.py`) prove the adapter feeds the
  32nd gate and that an UNVETTED source REFUSES runtime start.
- One manual connectivity observation exists (five BTCUSDT 15m
  klines: four closed, one open, basic OHLCV checks passed).

**What is UNKNOWN / UNVERIFIED (decide on this honestly):**
- Binance Terms of Use and API Terms — permitted use of public
  market data for this project: **NOT reviewed, NOT confirmed**.
- Jurisdictional availability of api.binance.com from your
  deployment environment: **UNVERIFIED**.
- Endpoint stability / reliability over continuous operation:
  **UNMEASURED** (a single successful fetch proves nothing about
  continuity).
- Revision policy for closed klines: **UNVERIFIED**.
- No SLA exists; availability can change without notice.

**Evidence still required for an honest approval decision:**
1. Your review of https://www.binance.com/en/terms and the API Terms
   (or the equivalent current documents) — record the exact
   document identity + date you reviewed.
2. A jurisdiction/availability check from the actual paper-session
   host (e.g. run `scripts/binance_public_smoke.py` there).
3. A reliability observation over a period you consider sufficient
   (e.g. scheduled smoke runs for N days — the repo does not
   currently ship a scheduler; a cron-operated smoke run is an
   operator-environment concern).
4. Your decision on whether rate limits / no-SLA / revision
   behaviour are acceptable for a PAPER-ONLY session.

## 4. Blocked markets (no candidate to approve — do NOT approve these)

| Market | Status | Honest blocker |
|---|---|---|
| Forex 15m OHLC | BLOCKED | No genuine 15-minute OHLC forex source identified/validated. The operator's forex bundle is a DAILY rate series (research-only, `REAL_UNVERIFIED`); rate→OHLC conversion is forbidden fabrication. |
| Stocks 15m | BLOCKED | No intraday equities source validated; master bundle is monthly/quarterly (0/9 D1-suitable). Intraday equity data is typically licence-restricted and paid. |
| Metals 15m | BLOCKED | No intraday metals source validated; master bundle monthly/quarterly with 19 impossible-OHLC rows quarantined (INVALID). Spot vs futures vs ETF identity must be pinned first. |

These stay blocked regardless of connectivity tests: approving a
market without a genuine source would fabricate readiness.

## 5. SRC-APPROVAL decision template (fill EXACTLY, then record)

Per policy §7.1 — copy this block, fill every `<...>` field, and
record it as your decision. Nothing is pre-filled: no approver, no
timestamp, no licence claim, no decision id exists until YOU write
them.

```text
Decision ID:        SRC-APPROVAL-<source_name>-<date>
Approver:           <named human>
Approver kind:      human
Target status:      APPROVED_FOR_TESTING | APPROVED_FOR_PRODUCTION
Approved scopes:    contract-testing | empirical-evaluation | production-ingestion
License basis:      <confirmed license text/reference — exact document
                    identity + review date; UNKNOWN is NOT approvable>
Coverage verified:  <evidence reference — what you personally checked
                    and when>
Provenance:         <mechanism + acquisition procedure you accept>
Recorded at:        <logical timestamp>
Notes:              <any conditions/limits you attach>
```

## 6. How to record the decision (exact commands)

On the paper-session host, from the repository root:

```bash
# 1. Review the candidate record (machine-readable, UNVETTED):
#    src/data_engine/platform/feed_source_candidates.py

# 2. Record your approval through the registry's human-only API.
#    The repository ships a recording helper for operators:
uv run python - <<'PY'
from data_engine.prediction.source_registry import (
    DataSourceRegistry, SourceVerificationStatus,
)
from data_engine.platform.feed_source_candidates import (
    build_feed_source_registry,
)

registry = build_feed_source_registry()
decision = registry.submit_approval(
    "binance-public-spot",
    approver="<YOUR NAME>",            # named human
    approver_kind="human",             # REQUIRED — "ai" is rejected
    target_status=SourceVerificationStatus.APPROVED_FOR_PRODUCTION,
    approved_usage_scopes=("production-ingestion",),
    recorded_at="<YYYY-MM-DDTHH:MM:SS+00:00>",
)
print(decision)
PY
```

Notes on that recording:
- `submit_approval` mutates an IN-MEMORY registry. For the decision
  to persist for the paper-session bootstrap, record it in the
  session's source-registry store as your environment defines (the
  runtime composition accepts any registry object; persistence of
  approvals is an operator-environment concern documented in the
  runbook §6).
- `approver_kind="ai"` is structurally rejected — the decision id,
  approver name and licence basis must be genuinely yours.

## 7. After approval — what changes and what does NOT

| Item | After a recorded production approval |
|---|---|
| `OPERATIONAL_FEED_READY` | Can become TRUE **only when the gate ALSO passes** on live inputs: validated closed bars, correct canonical mapping (instrument registered), sufficient warm-up, freshness within tolerance, no gaps/duplicates. Approval alone is necessary, not sufficient. |
| `PAPER_READY` | Still requires ALL 32 gates — including `REAL_DATA_READY`, MAC-key provisioning, and the remaining governance items. See the readiness report §0C for the live list. |
| Live trading | **STILL NOT AUTHORIZED. NOTHING in this pack touches the live boundary. `LiveAuthorizationGate` continues to deny unconditionally.** |
