# P0-P3 OWNER ACTION CHECKLIST

Exact safe local steps. **No secret values are requested or accepted
in chat** — keys are generated and stored by you, locally, through
the documented channels.

## 1. Close GOVERNANCE_READY (GOV-03 / GOV-04 / GOV-05)

1. Generate two strong keys (≥ 32 bytes each) in your secret store:
   - ledger MAC key → `RUNTIME_LEDGER_MAC_KEY[_FILE]`
   - operator approval key → `OPERATOR_APPROVAL_MAC_KEY[_FILE]`
   (absolute file path outside the repo, mode 0600).
2. Record the three governance decisions (approving principal,
   scope, time, decision, reason — the typed fields):
   - GOV-03 credential-rotation confirmation;
   - GOV-04 keyed-MAC provisioning record (cite the ledger key
     fingerprint `mackey-…`, never the key);
   - GOV-05 data-source approval for the operational feed source.
3. Sign each decision with the approval key
   (`OperatorApprovalRecord` + HMAC-SHA256 signature; a small local
   script following `runtime/operator_approval.py`'s documented
   fields — or the backlog H-1 signing helper).
4. Put the records + signatures into the launch plan's approvals
   file (`{"approvals": [{"record": {...}, "signature": "<64-hex>"}]}`).

## 2. Close OPERATIONAL_FEED_READY

1. Decide the approved feed source for the paper session (currently
   the only proven adapter: Binance public spot REST, pilot symbol
   `BTCUSDT`). Register the source approval in the prediction source
   registry with PRODUCTION_INGESTION scope (the feed gate reads the
   registry; AI approvals are structurally rejected there).
2. Configure the launch plan's `bar_source`:
   `{"mode": "provider", "provider": "binance_public", "symbol":
   "BTCUSDT", "interval_seconds": 300}`.
3. Optionally run the connectivity smoke
   (`scripts/binance_public_smoke.py`) from the machine that will
   host the session, and record the result.

## 3. Author the session launch plan

`launch-plan.json` (typed — invalid fields are refused with the exact
field name): session config (symbol/timeframe/lookback/pins/staleness
budget), durable-state paths, instrument specs, approvals file,
recorded-evidence entries for the 23 recorded gates, bar source, and
your ensemble factory `module:function` (your fitted, pinned model
code — the engine ships no default model).

## 4. Validate everything WITHOUT starting anything

```
data-engine status --gates          # honest 32-gate disposition
data-engine soak-preflight launch-plan.json --soak-days 30
```

Exit 0 = the evidence chain admits a separately authorized soak
start. Exit 6 = the named gap (stable reason code) tells you exactly
what to fix. Nothing starts from these commands; CI greenness is
irrelevant to them.

## 5. Bounded paper-only smoke (optional, minutes)

```
data-engine serve --session-launch launch-plan.json \
    --no-dashboard --max-seconds 60
```

Bounded run: composes + starts the session, drives its tick for 60s
(fail-closed at every gap; exit 0 clean, 4 refused launch, 2
readiness refusal). On Windows hosts use WSL/Linux for the
ledger-bearing runtime (see the Windows platform report).

## 6. When you separately authorize the soak

Follow `artifacts/stage-d/PAPER-SOAK-PROCEDURE.md` exactly (its §1
preconditions now include the executable preflight). Record the soak
start as a SIGNED `SOAK_START` approval. Daily: archive
`status --gates` snapshots. Abort conditions and recovery are in the
procedure.

## 7. After the project: revoke the GitHub PAT

The push token used for this task's commits should be revoked now
that all work is pushed and verified (your stated plan).
