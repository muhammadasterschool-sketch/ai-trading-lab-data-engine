# 04 — Tests Added & Exact Test Results

## 1. Commands executed (this branch, this machine)

| Command | Result |
|---|---|
| `uv run python -m pytest tests/test_mt5_market_data_feed.py -q` | **51 passed** |
| `uv run python -m pytest tests/test_mt5_paper_only_negative.py -q` | **15 passed** |
| `uv run python -m pytest tests/test_mt5_symbol_mapping.py -q` | **19 passed** |
| `uv run python -m pytest tests/test_mt5_terminal_integration.py -q` | **5 skipped** (`BLOCKED_ON_OPERATOR_ENV` — honest NOT RUN, see 05) |
| `uv run pytest -q` (FULL suite) | **2994 passed, 8 skipped, 0 failed, 177.91 s, exit 0** |
| `uv run data-engine status --gates` | identical to baseline: `PAPER_READINESS: BLOCKED`, `LIVE_AUTHORIZATION: NOT_AUTHORIZED`, `DATA_READINESS: SYNTHETIC_ONLY/REAL_BLOCKED`, `MODEL_READINESS: 0_APPROVED` |
| `uv run data-engine mt5-probe --self-test` (no MetaTrader5 pkg) | exit **7**, "probe NOT RUN" (honest) |
| `uv run data-engine mt5-probe --self-test` (no MT5_* env) | exit **2**, `MT5_E_CREDENTIALS` naming only the missing variable names |

## 2. Delta vs baseline (commit `4cc6782`)

- Baseline (Task-3 audit run at `4cc6782`): **2909 passed, 3 skipped, 0 failed, 179.94 s, exit 0**
- After this change: **2994 passed (+85), 8 skipped (+5), 0 failed**
- The +85 = exactly the new unit (51) + negative (15) + mapping (19) tests.
- The +5 skips = exactly the new genuine-terminal integration checks,
  auto-skipped because this host is not Windows and has no
  MetaTrader5 package — the honest NOT RUN, never a mock pass.
- Zero pre-existing tests broken; zero governance assertions changed.

## 3. What the new tests prove (highlights)

Paper-only boundary:
- refusal trio raises `MT5OrderRefusedError` even when disconnected;
- a call-recording spy across the FULL workflow (connect → catalogue →
  spec → bars → ticks → range → health → reconnect → disconnect) shows
  `order_attempts == []` and every called module function inside the
  closed read allowlist;
- AST scan: zero calls to any of the 8 order/trade functions across
  the three genuine modules; zero hardcoded broker suffixes;
- a would-be REAL-mode venue descriptor is refused at registration.

DEMO verification (fail-closed matrix):
- DEMO verified positively via the installed module's own constant;
  REAL / CONTEST / unknown / None refused; terminal-not-connected
  refused; initialize failure structured; server mismatch refused.

Data honesty:
- forming bar excluded by default (and included only when explicitly
  asked); stale data raises with age/threshold or flags in provenance
  (never silent); corrupt OHLC refused; empty answers are structured
  errors; range queries return only fully-closed bars and `[]` when
  nothing qualifies; numpy + namedtuple payload shapes normalised.

Credentials:
- `SecretStr` never rendered in repr/str/JSON; errors name only
  missing VARIABLE names; health/provenance payloads credential-free.

Mapping exactness:
- unobserved symbols refused (including identity mappings);
  duplicate/ambiguous proposals refused; digest-sensitive
  re-verification refuses broker-side spec drift or symbol removal;
  JSON round-trip preserves digests and still re-checks live.
