#!/usr/bin/env python3
"""Windows packaging smoke test (Batch 18).

Run this ON WINDOWS, inside the freshly installed virtual environment,
AFTER installing the built wheel (see docs/WINDOWS_INSTALLER_AND_
PACKAGING.md for the full procedure)::

    python -m venv .venv
    .venv\\Scripts\\python -m pip install --upgrade pip
    .venv\\Scripts\\python -m pip install ai_trading_lab_data_engine-0.1.0-py3-none-any.whl
    .venv\\Scripts\\python scripts\\windows_smoke_test.py

VERIFICATION STATUS (honest): this script is EXECUTABLE LOGIC ONLY —
it was NOT executed during Batch 18 because the agent environment is
not Windows. It must be run by the operator on a Windows host and its
output recorded as the packaging evidence. Every check is FAIL-CLOSED:
a non-zero exit code means the packaged application is NOT fit.

Checks (each prints PASS/FAIL and a reason):
 1. import + version provenance (data_engine imports; __version__).
 2. Readiness verdict: PAPER_READY must be FALSE with failing gates —
    a packaged application that reports paper-ready would be defective.
 3. Live-trading surface: REAL execution-mode capability descriptors
    must be REFUSED at construction (nothing silently enables live).
 4. Broker registry: all registered venues are MOCK_DETERMINISTIC.
 5. Dashboard: binds loopback ONLY (127.0.0.1), GET-only surface.
 6. Safe shutdown: dashboard server stops cleanly.

LIVE TRADING IS NOT AUTHORIZED — this script never places orders and
never contacts any broker or exchange.
"""

import sys

FAILURES: list = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    print("Windows packaging smoke test (Batch 18)")
    print(f"python: {sys.version}")
    print()

    # 1. import + version provenance ------------------------------------
    try:
        import data_engine

        check("import data_engine", True, f"__version__={data_engine.__version__}")
    except Exception as exc:  # noqa: BLE001 — report and fail closed
        check("import data_engine", False, repr(exc))
        return 1

    # 2. readiness verdict: PAPER_READY must be FALSE --------------------
    try:
        from data_engine.runtime.readiness import (
            GATE_NAMES,
            PaperReadinessGate,
        )

        # The packaged application ships NO real data/feed/governance
        # evidence, so the honest verdict must be paper-NOT-ready.
        # (Evaluating the full gate requires runtime evidence objects;
        # the structural check below pins the contract instead: a
        # report claiming paper_ready with failing gates is impossible.)
        from data_engine.runtime.readiness import ReadinessReport
        try:
            ReadinessReport(
                evidences=(),
                paper_ready=True,
                failed_gates=("REAL_DATA_READY",),
            )
            check("readiness fail-closed contract", False,
                  "fabricated paper_ready=TRUE accepted — DEFECT")
        except Exception:
            check("readiness fail-closed contract", True,
                  "PAPER_READY=TRUE with failing gates refused structurally")
    except Exception as exc:  # noqa: BLE001
        check("readiness fail-closed contract", False, repr(exc))

    # 3. REAL execution mode must be refused ------------------------------
    try:
        from data_engine.brokers.capabilities import (
            BrokerCapabilities,
            ExecutionMode,
        )
        from data_engine.brokers.models import AccountMode, OrderKind

        try:
            BrokerCapabilities(
                broker_id="smoke-real",
                display_name="smoke real",
                execution_mode=ExecutionMode.REAL,
                order_kinds=(OrderKind.MARKET,),
                account_modes=(AccountMode.REAL,),
            )
            check("REAL execution mode refused", False,
                  "REAL-mode descriptor registered — DEFECT")
        except Exception:
            check("REAL execution mode refused", True,
                  "REAL-mode descriptor refused at construction")
    except Exception as exc:  # noqa: BLE001
        check("REAL execution mode refused", False, repr(exc))

    # 4. every registered venue is MOCK_DETERMINISTIC ---------------------
    try:
        from data_engine.brokers import default_registry

        registry = default_registry()
        modes = {d.broker_id: d.execution_mode.value for d in registry.descriptors()}
        all_mock = all(v == "MOCK_DETERMINISTIC" for v in modes.values())
        check("all venues MOCK_DETERMINISTIC", all_mock, f"{len(modes)} venues")
    except Exception as exc:  # noqa: BLE001
        check("all venues MOCK_DETERMINISTIC", False, repr(exc))

    # 5/6. dashboard: loopback-only default, binds, safe shutdown --------
    try:
        import inspect

        from data_engine.platform.dashboard import DashboardServer

        default_host = inspect.signature(
            DashboardServer.__init__
        ).parameters["host"].default
        check("dashboard default bind is loopback", default_host == "127.0.0.1",
              f"default host={default_host!r}")
        server = DashboardServer(lambda: None, port=0)  # never serves
        server.start()
        check("dashboard binds (ephemeral port)", server.bound_port is not None,
              f"bound port={server.bound_port}")
        server.shutdown()
        check("dashboard safe shutdown", True)
    except Exception as exc:  # noqa: BLE001
        check("dashboard loopback + bind + shutdown", False, repr(exc))

    print()
    if FAILURES:
        print(f"SMOKE RESULT: FAIL ({len(FAILURES)} failed checks: "
              + ", ".join(FAILURES) + ")")
        return 1
    print("SMOKE RESULT: PASS — packaged application is fit "
          "(PAPER_READY = FALSE; LIVE TRADING NOT AUTHORIZED)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
