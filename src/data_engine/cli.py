"""CLI entry point for the AI Trading Lab Data Engine.

Usage:
    data-engine validate <dataset_id>
    data-engine report <dataset_id>
    data-engine status
    data-engine storage-report
    data-engine check-boundary <calc_type>
    data-engine serve [--host H] [--port P] [--no-dashboard]
                      [--max-seconds S]   (long-running paper supervisor)
                      [--session-launch PLAN_JSON]
                                          (compose + start one operational
                                           PAPER session, FIX-10)
    data-engine soak-preflight PLAN_JSON [--soak-days N]
                                          (fail-closed soak preflight,
                                           FIX-14 — starts nothing)

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
import os
from datetime import datetime, UTC
from data_engine import DataIngester, DataValidator, DataStorage, DataQualityGate
from data_engine.quant_boundary import LLMBoundary, CalculationType


def _read_token_file(path: str, purpose: str) -> str:
    """Read a bearer token from a dedicated file (Stage F hygiene:
    tokens travel via files with 600 permissions, NEVER via CLI
    arguments, environment dumps, or logs)."""
    from pathlib import Path

    token_file = Path(path)
    if not token_file.is_file():
        raise ValueError(f"{purpose} token file not found: {path}")
    token = token_file.read_text(encoding="utf-8").strip()
    if len(token) < 16:
        raise ValueError(
            f"{purpose} token too weak (>= 16 chars required): {path}"
        )
    mode = token_file.stat().st_mode & 0o777
    if mode & 0o077:
        print(
            f"[serve] WARNING: {purpose} token file {path} is "
            f"group/world readable (mode {oct(mode)}); run: "
            f"chmod 600 {path}",
            file=sys.stderr,
        )
    return token


def _build_monitoring_api(
    *,
    bind: str,
    port: int,
    token_file: str,
    pairing_service=None,
):
    """Construct the authenticated monitoring API (Stage F/F1) with
    HONEST providers: the health endpoint reflects the supervisor's
    own process state; every not-yet-composed dimension reports
    ABSENT. The kill-switch activator stays UNWIRED in the bare CLI
    path (fail closed: POST returns 503 until an operational session
    composition injects the real activator).

    v4.0: an OPTIONAL ``pairing_service`` (runtime.pairing.PairingService)
    wires the ``POST /api/pair`` onboarding endpoint; absent = pairing
    disabled (503 fail-closed)."""
    import time as _time

    from data_engine import __version__
    from data_engine.runtime.monitoring import MonitoringAPI

    token = _read_token_file(token_file, "monitoring API")
    started = _time.monotonic()

    def health() -> dict:
        return {
            "engine_mode": "PAPER_SUPERVISOR",
            "engine_state": "RUNNING",
            "engine_version": __version__,
            "uptime_seconds": round(_time.monotonic() - started, 1),
            "kill_switch": "NOT_WIRED_IN_BARE_CLI_PATH",
            "detail": (
                "supervisor-level health; a composed operational session "
                "injects richer providers (positions/orders/pnl/risk)"
            ),
        }

    return MonitoringAPI(
        auth_token=token,
        host=bind,
        port=port,
        health_provider=health,
        pairing_service=pairing_service,
    )


def _build_heartbeat_sender(
    *,
    registry_url: str,
    token_file,
    user_label: str,
    interval: float,
):
    """Construct the one-way outbound registry heartbeat sender
    (Stage F/F6). Payload = identity + health ONLY (data minimization
    TEST-ENFORCED in tests/test_monitoring_api.py)."""
    import platform as _platform
    import time as _time

    from data_engine import __version__
    from data_engine.runtime.heartbeat import (
        HeartbeatSender,
        build_heartbeat_payload,
    )

    if not token_file:
        raise ValueError(
            "--registry-token-file is required when --registry-url is set"
        )
    ingest_token = _read_token_file(token_file, "registry ingest")
    started = _time.monotonic()
    server_id = f"{_platform.node() or 'user-server'}:data-engine:{__version__}"

    def payload() -> dict:
        return build_heartbeat_payload(
            user_label=user_label,
            server_id=server_id,
            engine_mode="PAPER_SUPERVISOR",
            engine_version=__version__,
            uptime_seconds=round(_time.monotonic() - started, 1),
            feed_health="NOT_WIRED",
            risk_state="NOT_WIRED",
            kill_switch="NOT_WIRED_IN_BARE_CLI_PATH",
        )

    return HeartbeatSender(
        registry_url=registry_url,
        ingest_token=ingest_token,
        payload_builder=payload,
        interval_seconds=interval,
    )


#: Truthful status dimensions for the current repository state
#: (BUG-006). Updated only when the underlying reality changes —
#: never a single blanket "OPERATIONAL" claim. Stage C (F-05)
#: adds the composition-root availability dimension: the explicit
#: production assembly EXISTS (runtime/composition.py) even while
#: no session is composed in THIS process (RUNTIME_HEALTH stays
#: honestly ABSENT for the bare CLI invocation).
STATUS_DIMENSIONS = {
    "LIBRARY_HEALTH": "OK",
    "RUNTIME_HEALTH": "ABSENT",
    "COMPOSITION_ROOT": "AVAILABLE",
    "PAPER_READINESS": "BLOCKED",
    "LIVE_AUTHORIZATION": "NOT_AUTHORIZED",
    "DATA_READINESS": "SYNTHETIC_ONLY/REAL_BLOCKED",
    "MODEL_READINESS": "0_APPROVED",
    "RECONCILIATION_HEALTH": "NOT_WIRED",
}


def main(argv=None):
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
    status_parser = subparsers.add_parser("status", help="Show engine status")
    status_parser.add_argument(
        "--gates",
        action="store_true",
        help=(
            "list every paper-readiness gate with its honest evidence-"
            "supplier disposition (F-05: supplied by the composition "
            "root / operator-recorded evidence required / human action "
            "required)"
        ),
    )

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
    # -- Stage F: authenticated monitoring API (F1) + registry heartbeat (F6)
    serve_parser.add_argument(
        "--monitor-port",
        type=int,
        default=8018,
        help="authenticated monitoring API port (read-only + kill switch)",
    )
    serve_parser.add_argument(
        "--monitor-bind",
        default="127.0.0.1",
        help=(
            "monitoring API bind address (loopback default; the per-user "
            "deployment binds loopback and terminates TLS at the reverse "
            "proxy — see deploy/server-install.sh)"
        ),
    )
    serve_parser.add_argument(
        "--monitor-token-file",
        default=None,
        help=(
            "path to the monitoring API bearer token file (600 perms). "
            "REQUIRED to enable the monitoring API; tokens are NEVER "
            "passed as CLI arguments (shell-history hygiene)."
        ),
    )
    serve_parser.add_argument(
        "--session-launch",
        default=None,
        metavar="PLAN_JSON",
        help=(
            "EXPLICIT session launch plan (FIX-10/B-P0-01): compose "
            "and start one operational PAPER session through the "
            "composition root and wire its REAL tick into this "
            "supervisor loop. The plan carries the session config, "
            "durable-state paths, instrument specs, SIGNED operator "
            "approvals (FIX-9) and the bar source (deterministic "
            "replay file or a proven provider adapter). Refused "
            "fail-closed with exit code 4 on any gap."
        ),
    )
    serve_parser.add_argument(
        "--registry-url",
        default=None,
        help=(
            "owner admin-registry heartbeat URL (https://...). Optional; "
            "enables the one-way outbound health heartbeat (graceful "
            "degradation if the registry is unreachable)."
        ),
    )
    serve_parser.add_argument(
        "--registry-token-file",
        default=None,
        help="path to the registry ingest token file (required with --registry-url)",
    )
    serve_parser.add_argument(
        "--user-label",
        default="unlabeled-user-server",
        help="heartbeat identity label for this user server",
    )
    serve_parser.add_argument(
        "--heartbeat-interval",
        type=float,
        default=45.0,
        help="heartbeat interval seconds (30-60 recommended)",
    )
    # -- v4.0 (B1/B3/P5): invitation-code pairing + mDNS announcement
    serve_parser.add_argument(
        "--pairing-config",
        default=None,
        help=(
            "path to the invitation-pairing config JSON (salted hash, "
            "version 1). Required to enable POST /api/pair; absent = "
            "pairing DISABLED (fail-closed). Malformed/missing file at "
            "the given path REFUSES startup."
        ),
    )
    serve_parser.add_argument(
        "--mdns-announce",
        action="store_true",
        help=(
            "announce the monitoring API on the LAN as "
            "_aitl-monitor._tcp.local. (mDNS; graceful fallback to the "
            "manual PC-address entry if zeroconf is unavailable)"
        ),
    )
    serve_parser.add_argument(
        "--mdns-instance",
        default=None,
        help="mDNS instance name (default: aitl-monitor)",
    )

    # Pairing status probe (v4.0 B4): prints whether invitation
    # pairing is enabled and the configured attempt cap — NEVER the
    # code itself.
    pair_status_parser = subparsers.add_parser(
        "pair-status",
        help=(
            "Show invitation-pairing configuration status (enabled/"
            "disabled, attempt cap) — never the invitation code"
        ),
    )
    pair_status_parser.add_argument(
        "--config",
        required=True,
        help="path to the pairing config JSON to inspect",
    )

    # Soak preflight (FIX-14 / B-P2-16 + Task 12): the EXECUTABLE
    # fail-closed check that must run BEFORE any separately
    # authorized 30-day soak start. Reads no CI status — a green CI
    # run alone can never start a soak.
    soak_parser = subparsers.add_parser(
        "soak-preflight",
        help=(
            "Run the fail-closed paper-soak preflight over a session "
            "launch plan (refuses with exit 6 unless every "
            "non-component gate carries passing evidence, the human "
            "gates carry SIGNED approvals, and every approval covers "
            "the full soak window)"
        ),
    )
    soak_parser.add_argument(
        "plan", help="path to the session launch plan JSON",
    )
    soak_parser.add_argument(
        "--soak-days",
        type=int,
        default=30,
        help="planned soak duration in days (default 30)",
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

    args = parser.parse_args(argv)

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

        elif args.command == "soak-preflight":
            # FIX-14 (B-P2-16 / Task 12): the preflight that must run
            # before ANY separately authorized soak start. PASS =>
            # exit 0 with the verdict record; refusal => exit 6 with
            # the stable reason code and the exact remediation.
            from data_engine.runtime.soak_preflight import (
                SOAK_PREFLIGHT_EXIT_CODE,
                SoakPreflightError,
                run_soak_preflight,
            )

            try:
                preflight = run_soak_preflight(
                    args.plan, soak_duration_days=args.soak_days,
                )
            except SoakPreflightError as exc:
                print(
                    f"[soak-preflight] REFUSED: {exc}",
                    file=sys.stderr,
                )
                raise SystemExit(SOAK_PREFLIGHT_EXIT_CODE)
            print("[soak-preflight] PASS — the evidence chain admits a")
            print("separately AUTHORIZED soak start (this preflight")
            print("starts nothing; CI status is irrelevant here):")
            print(f"  plan session: {preflight.plan_session_id}")
            print(f"  as_of: {preflight.as_of.isoformat()}")
            print(f"  soak end: {preflight.soak_end.isoformat()}")
            print(
                f"  bundle-covered gates: {len(preflight.gates_covered)}"
            )
            print(
                "  human gates verified (signed): "
                ", ".join(preflight.human_gates_verified)
            )
            print(
                "  pending first-hand verification at launch: "
                ", ".join(preflight.pending_launch_verification)
            )
            print(
                "  approval records: "
                ", ".join(preflight.approval_ids)
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
            if getattr(args, "gates", False):
                # Stage C (F-05 acceptance): every readiness gate has
                # an evidence supplier or is explicitly NOT supplyable
                # by code — the honest per-gate disposition.
                from data_engine.runtime.composition import (
                    GATE_SUPPLIER_DISPOSITION,
                )
                print("  Readiness-gate supplier disposition:")
                for gate in sorted(GATE_SUPPLIER_DISPOSITION):
                    print(
                        f"    {gate}: {GATE_SUPPLIER_DISPOSITION[gate]}"
                    )

        elif args.command == "pair-status":
            # v4.0 (B4): fail-closed, one-shot, NO code material.
            # A missing file is honestly reported as "disabled";
            # a malformed file is a LOUD error (operator misconfig).
            from pathlib import Path as _P
            from data_engine.runtime.pairing import (
                PairingConfigError as _PCE,
                format_pairing_status as _fmt,
                load_pairing_config as _load,
            )

            if not _P(args.config).is_file():
                print(
                    "[pair-status] invitation pairing: DISABLED "
                    f"(no config file at {args.config})"
                )
                print(
                    "[pair-status] note: the code itself is never "
                    "displayed; the serving process console shows live "
                    "attempt outcomes."
                )
                raise SystemExit(0)
            try:
                pairing_cfg = _load(args.config)
            except _PCE as exc:
                print(f"[pair-status] CONFIG ERROR: {exc}", file=sys.stderr)
                raise SystemExit(1)
            print(_fmt(pairing_cfg))
            raise SystemExit(0)

        elif args.command == "serve":
            from data_engine.runtime.service import PaperRuntimeService

            monitoring_api = None
            heartbeat_sender = None
            pairing_service = None
            mdns_announcement = None
            launched = None
            try:
                pairing_service = None
                if args.pairing_config:
                    from data_engine.runtime.pairing import (
                        PairingConfigError,
                        PairingService,
                        load_pairing_config,
                    )

                    # Fail-closed startup posture (mirrors the monitor
                    # token file): a malformed/missing config at the
                    # EXPLICITLY given path refuses to serve.
                    try:
                        pairing_service = PairingService(
                            load_pairing_config(args.pairing_config)
                        )
                    except PairingConfigError as pairing_error:
                        print(
                            f"[serve] REFUSING TO START: pairing config "
                            f"failed closed: {pairing_error}",
                            file=sys.stderr,
                        )
                        raise SystemExit(1)
                    print(
                        "[serve] invitation pairing ENABLED from "
                        f"{args.pairing_config} (POST /api/pair; the "
                        "code is never logged)"
                    )
                if args.monitor_token_file:
                    monitoring_api = _build_monitoring_api(
                        bind=args.monitor_bind,
                        port=args.monitor_port,
                        token_file=args.monitor_token_file,
                        pairing_service=pairing_service,
                    )
                if args.mdns_announce:
                    if monitoring_api is None:
                        print(
                            "[serve] --mdns-announce requires the "
                            "monitoring API (pass --monitor-token-file); "
                            "skipping announcement (honest no-op)",
                            file=sys.stderr,
                        )
                    else:
                        from data_engine.runtime.announce import (
                            DEFAULT_INSTANCE,
                            try_announce_mdns,
                        )

                        mdns_announcement = try_announce_mdns(
                            instance=args.mdns_instance or DEFAULT_INSTANCE,
                            host=args.monitor_bind,
                            port=args.monitor_port,
                        )
                        print(f"[serve] {mdns_announcement.status}")
                if args.registry_url:
                    heartbeat_sender = _build_heartbeat_sender(
                        registry_url=args.registry_url,
                        token_file=args.registry_token_file,
                        user_label=args.user_label,
                        interval=args.heartbeat_interval,
                    )
            except (OSError, ValueError) as setup_error:
                print(
                    f"[serve] REFUSING TO START: Stage F surface setup "
                    f"failed closed: {setup_error}",
                    file=sys.stderr,
                )
                raise SystemExit(1)

            # FIX-10 (B-P0-01): the EXPLICIT session-launch wiring —
            # without this flag the supervisor runs as an honest
            # supervisor-only shell (no session is composed, no
            # tick_fn is fabricated); with it, a REAL operational
            # paper session is composed through the composition root
            # and its tick drives the supervised loop.
            tick_fn = None
            readiness_fn = None
            if args.session_launch:
                from data_engine.runtime.session_launch import (
                    SESSION_LAUNCH_EXIT_CODE,
                    SessionLaunchError,
                    launch_paper_session,
                    load_launch_plan,
                )

                try:
                    plan = load_launch_plan(args.session_launch)
                    launched = launch_paper_session(plan)
                except SessionLaunchError as launch_error:
                    print(
                        f"[serve] SESSION LAUNCH REFUSED (exit "
                        f"{SESSION_LAUNCH_EXIT_CODE}): {launch_error}",
                        file=sys.stderr,
                    )
                    raise SystemExit(SESSION_LAUNCH_EXIT_CODE)
                tick_fn = launched.tick
                readiness_fn = (
                    lambda: launched.composed.readiness_gate
                    .evaluate().paper_ready
                )
                print(
                    "[serve] operational PAPER session composed and "
                    "started via the composition root; the supervisor "
                    f"loop now drives its tick (source: "
                    f"{launched.tick.source_name})",
                    file=sys.stdout,
                    flush=True,
                )

            service = PaperRuntimeService(
                host=args.host,
                port=args.port,
                enable_dashboard=not args.no_dashboard,
                heartbeat_seconds=args.heartbeat_seconds,
                tick_seconds=args.tick_seconds,
                max_seconds=args.max_seconds,
                tick_fn=tick_fn,
                readiness_fn=readiness_fn,
                monitoring_api=monitoring_api,
                heartbeat_sender=heartbeat_sender,
            )
            try:
                # SystemExit propagates past the Exception handler below so
                # the documented service exit codes reach the process.
                raise SystemExit(service.run())
            finally:
                # v4.0: best-effort mDNS teardown (never masks the exit code)
                if mdns_announcement is not None:
                    mdns_announcement.stop()

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
