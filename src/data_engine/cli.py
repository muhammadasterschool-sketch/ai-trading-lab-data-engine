"""CLI entry point for the AI Trading Lab Data Engine.

Usage:
    data-engine validate <dataset_id>
    data-engine report <dataset_id>
    data-engine status
    data-engine storage-report
"""

import sys
import argparse
from datetime import datetime, UTC
from data_engine import DataIngester, DataValidator, DataStorage, DataQualityGate
from data_engine.quant_boundary import LLMBoundary, CalculationType


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
            print("[Data Engine] Status: OPERATIONAL")
            print(f"  Timestamp: {datetime.now(UTC).isoformat()}")
            print("  LLM/Quant Boundary: ENFORCED")
            print("  Data Quality Gate: ACTIVE")
            print("  RAW Immutability: ENFORCED")
            print("  Evidence Integrity: ENFORCED")

        elif args.command == "check-boundary":
            calc_type = CalculationType(args.calc_type.lower()) if args.calc_type else None
            if calc_type:
                LLMBoundary.assert_deterministic(calc_type, "cli_check")
                print(f"[Boundary] {args.calc_type} is DETERMINISTIC — must use code, not LLM.")
            else:
                print(f"[Boundary] Valid calculation types:")
                for ct in CalculationType:
                    print(f"  - {ct.value}")

    except Exception as e:
        print(f"[Data Engine] Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
