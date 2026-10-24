# 03 — Exact Local Setup Commands for the Windows Host

One-time setup on the Windows machine that runs the MT5 terminal
(the paper-session host). Credentials NEVER enter the repository.

## 1. Prerequisites

1. Windows 10/11 x64.
2. MetaTrader 5 terminal installed and logged in ONCE manually with
   the Exness **DEMO** account (let the terminal cache the account;
   the terminal must be running for the Python package to attach).
3. Python 3.11–3.14 x64 + `uv` (or plain pip).

## 2. Install the project + the Windows-only package

```bat
:: from the repository root
uv sync --extra dev
uv pip install MetaTrader5
:: sanity: this MUST print a version, not an error
uv run python -c "import MetaTrader5; print(MetaTrader5.version())"
```

`MetaTrader5` is intentionally NOT in `pyproject.toml` (Windows-only);
installing it is an operator step on the Windows host only.

## 3. Environment variables (operator shell — NOT files in the repo)

```bat
setx MT5_LOGIN      88012345                                   &:: your DEMO login number
setx MT5_PASSWORD   "your-demo-password-here"                  &:: DEMO password
setx MT5_SERVER     "Exness-MT5Trial8"                         &:: EXACT server from the terminal's login dialog
setx MT5_TERMINAL_PATH "C:\Program Files\MetaTrader 5\terminal64.exe"  &:: optional
setx MT5_EXPECTED_SERVER "Exness-MT5Trial"                     &:: optional substring cross-check
```

Open a NEW shell afterwards (setx applies to new processes). To
verify without printing the secret:

```bat
uv run python -c "import os; print(sorted(k for k in os.environ if k.startswith('MT5')))"
```

## 4. First evidence run (read-only)

```bat
:: full self-test: connect → positive DEMO verification → catalogue
:: → M1 bar sample → tick sample → clean disconnect (JSON to stdout)
uv run data-engine mt5-probe --self-test --symbol EURUSD

:: archive the evidence (recommended):
uv run data-engine mt5-probe --self-test --symbol EURUSD > artifacts\mt5-integration\self-test-%DATE%.json
```

Exit codes: `0` verified · `2` configuration/credential error ·
`6` fail-closed refusal (read the JSON `error` field) · `7`
environment blocked (package/terminal unavailable → NOT RUN).

## 5. Symbol catalogue → symbol map (exact mapping workflow)

```bat
:: 1) dump what the terminal ACTUALLY offers
uv run data-engine mt5-probe --dump-catalogue artifacts\mt5-integration\catalogue.json

:: 2) author a PROPOSAL file mapping canonical → broker symbol using
::    ONLY names present in catalogue.json, e.g. map.json:
::    {"entries": [
::        {"canonical": "EURUSD", "broker_symbol": "EURUSDm"},
::        {"canonical": "XAUUSD", "broker_symbol": "XAUUSD"}
::    ]}

:: 3) validate the proposal against the live terminal — produces the
::    digest-stamped validated map
uv run data-engine mt5-probe --validate-map artifacts\mt5-integration\map.json

:: 4) bar-sample evidence for each mapped symbol
uv run data-engine mt5-probe --symbol EURUSD --timeframe M1 --bars 50 --out artifacts\mt5-integration\bars-eurusd-m1.json
uv run data-engine mt5-probe --symbol XAUUSD --timeframe M15 --bars 50 --out artifacts\mt5-integration\bars-xauusd-m15.json
```

If the broker changes a specification later, the feed REFUSES until
`--validate-map` is re-run — that refusal is the safety feature
working, not a bug.

## 6. Run the integration checks (genuine terminal)

```bat
uv run pytest tests\test_mt5_terminal_integration.py -v
:: archive output as the NOT-RUN→RUNNED evidence flip
```

## 7. Weekend note

Forex/metals/indices are closed at weekends: `latest_bars` /
`latest_ticks` will raise `MT5_E_STALE_DATA` (default) — pass
`--stale-flag` for evidence runs, or accept the refusal as the honest
"market closed" signal it is.
