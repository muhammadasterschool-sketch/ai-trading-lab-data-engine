"""CLI entry point for the AI Trading Lab Data Engine.

Usage:
    data-engine validate <dataset_id>
    data-engine report <dataset_id>
    data-engine status
    data-engine storage-report
    data-engine check-boundary <calc_type>

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

    # Validate command
    subparsers.add_parser("validate", help="Validate a dataset")

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

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    try:
        if args.command == "validate":
            print("[Data Engine] Validation mode activated.")
            print("Use DataIngester to validate datasets programmatically.")

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
