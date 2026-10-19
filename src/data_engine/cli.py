"""CLI entry point for the AI Trading Lab Data Engine.

Usage:
    data-engine validate <dataset_id>
    data-engine report <dataset_id>
    data-engine status
    data-engine storage-report
    data-engine check-boundary <calc_type>
    data-engine serve [--host H] [--port P] [--no-dashboard]
                      [--max-seconds S]   (long-running paper supervisor)

BUG-006 correction: ``status`` reports seven DISTINCT health
 dimensions with truthful values for the current repository state
 instead of a single untruthful "OPERATIONAL" claim. RT-F7
correction: ``check-boundary`` verifies the deterministic boundary
and EXITS 0 for deterministic-required types (the old implementation
called ``assert_deterministic`` — which raises exactly for those
types — and therefore always exited 1).
"""

import sys
import argparse
from datetime import datetime, UTC
from data_engine import DataIngester, DataValidator, DataStorage, DataQualityGate
from data_engine.quant_boundary import LLMBoundary, CalculationType


#: Truthful status dimensions for the current repository state
#: (BUG-006). Updated only when the underlying reality changes —
#: never a single blanket "OPERATIONAL" claim.
STATUS_DIMENSIONS = {
    "LIBRARY_HEALTH": "OK",
    "RUNTIME_HEALTH": "ABSENT",
    "PAPER_READINESS": "BLOCKED",
    "LIVE_AUTHORIZATION": "NOT_AUTHORIZED",
    "DATA_READINESS": "SYNTHETIC_ONLY/REAL_BLOCKED",
    "MODEL_READINESS": "0_APPROVED",
    "RECONCILIATION_HEALTH": "NOT_WIRED",
}


def main():
    parser = argparse.ArgumentParser(
        description="AI Trading Lab Data Engine CLI"
    )
    subparsers = parser.add_subparsers(dest="command")

    # Validate command (F-21: the usage docstring always promised a
    # dataset_id positional — the parser never registered it)
    validate_parser = subparsers.add_parser(
        "validate", help="Validate a dataset"
    )
    validate_parser.add_argument(
        "dataset_id", help="Dataset ID to validate"
    )

    # Report command
    report_parser = subparsers.add_parser("report", help="Generate quality report")
    report_parser.add_argument("dataset_id", help="Dataset ID")

    # Storage report
    subparsers.add_parser("storage-report", help="Show storage status")

    # Status
    subparsers.add_parser("status", help="Show engine status")

    # Boundary check
    boundary_parser = subparsers.add_parser("check-boundary", help="Verify LLM/quant boundary")
    boundary_parser.add_argument("calc_type", help="Calculation type to verify")

    # Long-running paper-mode supervisor (reconstruction D-4/D-5:
    # explicit entrypoint for the systemd unit — the bare module
    # invocation printed help and exited 0, going inactive at once).
    serve_parser = subparsers.add_parser(
        "serve",
        help=(
            "Run the long-running paper-mode supervisor "
            "(fail-closed startup; loopback-only dashboard)"
        ),
    )
    serve_parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="dashboard bind host (loopback ONLY — non-loopback is refused)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8017,
        help="dashboard port (0 = ephemeral)",
    )
    serve_parser.add_argument(
        "--no-dashboard",
        action="store_true",
        help="do not start the read-only dashboard",
    )
    serve_parser.add_argument(
        "--heartbeat-seconds",
        type=float,
        default=30.0,
        help="supervisor heartbeat interval",
    )
    serve_parser.add_argument(
        "--tick-seconds",
        type=float,
        default=1.0,
        help="supervision loop tick interval",
    )
    serve_parser.add_argument(
        "--max-seconds",
        type=float,
        default=None,
        help=(
            "bounded runtime (tests/smoke); omit to run until SIGTERM/SIGINT"
        ),
    )

    # State-store recovery tool (F-12: torn journal tail — audited,
    # explicit operator confirmation, NEVER automatic truncation)
    recover_parser = subparsers.add_parser(
        "recover-state",
        help=(
            "Inspect (and, with explicit confirmation, repair) a "
            "state store's journal after a torn-tail crash"
        ),
    )
    recover_parser.add_argument(
        "store_dir", help="state store directory to inspect"
    )
    recover_parser.add_argument(
        "--confirm-truncate",
        action="store_true",
        help=(
            "EXPLICIT operator confirmation: truncate the damaged "
            "journal tail to its longest valid chained prefix and "
            "journal the repair (without this flag the tool only "
            "REPORTS and exits non-zero)"
        ),
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    try:
        if args.command == "validate":
            print(
                f"[Data Engine] Validation for dataset "
                f"{args.dataset_id}."
            )
            print("Use DataIngester to validate datasets programmatically.")

        elif args.command == "recover-state":
            # F-12: fail-closed availability recovery — REPORT first;
            # repair ONLY on explicit operator confirmation, and the
            # repair is itself journaled (audited, never silent).
            from pathlib import Path as _P
            from data_engine.runtime.state import (
                StateStoreError as _SSE,
                scan_journal_tail as _scan,
                truncate_journal_tail as _trunc,
            )
            store_dir = _P(args.store_dir)
            journal_path = store_dir / "journal.jsonl"
            try:
                report = _scan(journal_path)
            except _SSE as exc:
                print(f"[Recovery] ERROR: {exc}", file=sys.stderr)
                raise SystemExit(1)
            if report["damaged_lines"] == 0:
                print(
                    f"[Recovery] journal HEALTHY — "
                    f"{report['valid_records']} valid records, "
                    "no damaged tail."
                )
                raise SystemExit(0)
            print(
                f"[Recovery] journal at {journal_path} has a DAMAGED "
                f"tail: {report['valid_records']} valid records, "
                f"{report['damaged_lines']} damaged trailing line(s) "
                f"(last valid index: {report['last_valid_index']})."
            )
            if not args.confirm_truncate:
                print(
                    "[Recovery] REFUSING to repair without explicit "
                    "confirmation — rerun with --confirm-truncate to "
                    "truncate the damaged tail (the repair is "
                    "journaled and audited; state.json is never "
                    "touched)."
                )
                raise SystemExit(3)
            total = _trunc(journal_path, report)
            print(
                f"[Recovery] REPAIRED — journal truncated to its "
                f"valid prefix + 1 recovery record ({total} records "
                "total). The truncation itself is journaled."
            )
            raise SystemExit(0)

        elif args.command == "report":
            print(f"[Data Engine] Quality report for {args.dataset_id}.")
            print("Use dataset.quality_report() programmatically.")

        elif args.command == "storage-report":
            print("[Data Engine] Storage status.")
            print("Use DataStorage.get_storage_report() programmatically.")

        elif args.command == "status":
            # BUG-006: seven distinct, truthful health dimensions — a
            # library-only state must never be reported as a single
            # blanket "OPERATIONAL" claim.
            print("[Data Engine] Status:")
            print(f"  Timestamp: {datetime.now(UTC).isoformat()}")
            for dimension, value in STATUS_DIMENSIONS.items():
                print(f"  {dimension}: {value}")

        elif args.command == "serve":
            from data_engine.runtime.service import PaperRuntimeService

            service = PaperRuntimeService(
                host=args.host,
                port=args.port,
                enable_dashboard=not args.no_dashboard,
                heartbeat_seconds=args.heartbeat_seconds,
                tick_seconds=args.tick_seconds,
                max_seconds=args.max_seconds,
            )
            # SystemExit propagates past the Exception handler below so
            # the documented service exit codes reach the process.
            raise SystemExit(service.run())

        elif args.command == "check-boundary":
            calc_type = CalculationType(args.calc_type.lower()) if args.calc_type else None
            if calc_type:
                # RT-F7 correction: VERIFICATION, not assertion. The old
                # code called assert_deterministic() — which raises
                # exactly for deterministic-required types — so the
                # check always exited 1. Verifying means: the type IS
                # deterministic-required -> confirm and exit 0.
                if LLMBoundary.is_deterministic_required(calc_type):
                    print(
                        f"[Boundary] {args.calc_type} is DETERMINISTIC — "
                        "must use code, not LLM."
                    )
                else:
                    print(
                        f"[Boundary] {args.calc_type} is not in the "
                        "deterministic-required set — no boundary "
                        "enforcement applies."
                    )
            else:
                print(f"[Boundary] Valid calculation types:")
                for ct in CalculationType:
                    print(f"  - {ct.value}")

    except Exception as e:
        print(f"[Data Engine] Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
