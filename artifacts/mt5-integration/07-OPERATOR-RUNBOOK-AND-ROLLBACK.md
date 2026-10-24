# 07 — Operator Runbook & Rollback Procedure

## 1. Daily operation (Windows paper-session host)

```bat
:: terminal running? probe first — it is the health check
uv run data-engine mt5-probe --self-test --symbol EURUSD

:: latest observed bars (freshness-enforced)
uv run data-engine mt5-probe --symbol EURUSD --timeframe M1 --bars 50

:: weekend / closed-market evidence runs (staleness flagged, not raised)
uv run data-engine mt5-probe --symbol EURUSD --timeframe M1 --bars 50 --stale-flag
```

Programmatic use (paper runtime data layer):

```python
from data_engine.platform.mt5_terminal import MT5TerminalConfig
from data_engine.platform.mt5_market_data import ExnessMT5DemoFeed
from data_engine.platform.mt5_symbol_map import SymbolMapEntry
from data_engine.schemas import ProviderConfig

feed = ExnessMT5DemoFeed(
    ProviderConfig(provider_name="exness-mt5-demo",
                   provider_type="broker-terminal"),
    terminal_config=MT5TerminalConfig.from_env(),
    symbol_map_path="artifacts/mt5-integration/map.json.validated.json",
)
health = feed.connect()            # fails closed unless DEMO verified
batch = feed.latest_bars("EURUSD", "M1", 100)   # bars + provenance
# ... strategy output goes to the INTERNAL paper broker, as before
feed.disconnect()
```

Operational notes:
- `ensure_connected()` after any structured disconnect — it re-runs the
  FULL verification chain (connectivity → positive DEMO → server match
  → symbol-map digests).
- Every batch carries `MT5FeedProvenance`; persist it alongside any
  stored bars (payload SHA-256 is the audit anchor).
- MT5 timestamps are broker-server epochs, carried verbatim in
  provenance (`raw_time_epoch` + derived UTC datetime). Validate
  session/timezone semantics for your account family before treating
  staleness thresholds as market facts.
- MN1 freshness uses a nominal ~30-day bar length (documented
  approximation, freshness only — never used for bar values).

## 2. Failure playbook

| Symptom | Meaning | Action |
|---|---|---|
| exit 7 / `MT5_E_MODULE_UNAVAILABLE` | package/terminal absent | start MT5 terminal, reinstall `MetaTrader5` on Windows, retry |
| exit 2 / `MT5_E_CREDENTIALS` | env vars missing/invalid | re-export MT5_* (values never printed anywhere) |
| exit 6 / `MT5_E_NOT_DEMO_VERIFIED` | account is not DEMO (or unverifiable) | STOP — connect a DEMO account; do not look for workarounds |
| `MT5_E_SERVER_MISMATCH` | unexpected server | verify the account/server in the terminal; fix MT5_EXPECTED_SERVER honestly |
| `MT5_E_SYMBOL_MAP_INVALID` (drift) | broker changed a specification | inspect catalogue dump, re-author + `--validate-map`, review the diff before re-validating |
| `MT5_E_STALE_DATA` | market closed or feed down | weekend → expected; weekday → check terminal connectivity |
| `MT5_E_CONNECT` after retries | terminal/server unreachable | restart terminal, check Exness server status; feed stays disconnected (fail-closed) |

## 3. Rollback procedure

The feature is ADDITIVE. Rollback options, cheapest first:

1. **Stop using it (runtime rollback).** The feed is a provider —
   simply stop constructing it / remove it from any launch plan. No
   persisted state, no daemon, no schema migration exists to unwind.
   The candidate record stays UNVETTED (it approves nothing by
   existing).
2. **Revert the branch (code rollback).**
   ```bash
   git checkout main
   git branch                            # confirm you are off the feature branch
   # if the branch was merged and must be unwound:
   git revert -m 1 <merge-commit-sha>    # creates an inverse commit; history preserved
   ```
   The repo discipline is no-reset/no-rebase/no-force-push — an
   explicit revert commit is THE rollback mechanism. Files removed by
   revert: the three new platform modules + four test files; restored:
   the small additive diffs in `mt5.py`, `platform/__init__.py`,
   `feed_source_candidates.py`, `cli.py`, docs, CHANGELOG.
3. **Verify the rollback.**
   ```bash
   uv run pytest -q                      # expect the pre-branch counts
   uv run data-engine status --gates     # PAPER_READINESS: BLOCKED (unchanged by either state)
   ```

## 4. Invariants to re-verify after ANY change to this area

- `data-engine status --gates` → PAPER_READINESS: BLOCKED;
  LIVE_AUTHORIZATION: NOT_AUTHORIZED.
- `build_feed_source_registry()` → every record UNVETTED.
- `tests/test_mt5_paper_only_negative.py` fully green (allowlist spy +
  AST scan + venue refusal).
- No `MetaTrader5` entry in `pyproject.toml`.
- No credential value in any file, log or artifact.
