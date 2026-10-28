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
from datetime import datetime, UTC
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
    state_dir: str = "./monitor-state",
    bootstrap_presets: bool = False,
):
    """Construct the authenticated monitoring API (Stage F/F1) with
    HONEST providers: the health endpoint reflects the supervisor's
    own process state; every not-yet-composed dimension reports
    ABSENT.

    v4.0: an OPTIONAL ``pairing_service`` (runtime.pairing.PairingService)
    wires the ``POST /api/pair`` onboarding endpoint; absent = pairing
    disabled (503 fail-closed).

    v1.0.0 (owner mandate): the serve path wires the REAL durable
    controls — a :class:`~data_engine.runtime.control_state.DurableKillSwitch`
    (the phone's STOP button finally ACTS and PERSISTS), a
    :class:`~data_engine.runtime.registry.ClientRegistry` (who is
    connected / who ever registered) and a
    :class:`~data_engine.runtime.trade_ledger.TradeLedger` (which
    trades, what profit). All three live under ``state_dir``."""
    import time as _time
    from pathlib import Path as _Path

    from data_engine import __version__
    from data_engine.runtime.control_state import DurableKillSwitch
    from data_engine.runtime.lab import AssistantEngine as _AE
    from data_engine.runtime.lab import BarStore as _BarStore
    from data_engine.runtime.lab import LabManager as _Lab
    from data_engine.runtime.monitoring import MonitoringAPI
    from data_engine.runtime.registry import ClientRegistry
    from data_engine.runtime.trade_ledger import TradeLedger

    token = _read_token_file(token_file, "monitoring API")
    started = _time.monotonic()

    state_root = _Path(state_dir)
    kill_switch = DurableKillSwitch(state_root / "kill_switch_state.json")
    client_registry = ClientRegistry(state_root)
    trade_ledger = TradeLedger(state_root / "trade_ledger.jsonl")

    def health() -> dict:
        return {
            "engine_mode": "PAPER_SUPERVISOR",
            "engine_state": "RUNNING",
            "engine_version": __version__,
            "uptime_seconds": round(_time.monotonic() - started, 1),
            # v1.0.0: the REAL standing stop flag (durable), replacing
            # the honest-but-useless NOT_WIRED marker.
            "kill_switch": kill_switch.state()["state"],
            "detail": (
                "supervisor-level health; a composed operational session "
                "injects richer providers (positions/orders/pnl/risk)"
            ),
        }

    # -- v1.1.0 OWNER AI LAB wiring -------------------------------------
    # The lab is ALWAYS wired in the serve path (fail-closed internals;
    # every store lives under --monitor-state-dir). The kill switch
    # also pauses forward paper evaluation: a standing STOP is a stop
    # for the whole lab.
    _bar_store = _BarStore(state_root / "bars")
    _lab = _Lab(
        state_root,
        _bar_store,
        is_halted=lambda: kill_switch.state()["state"] == "ACTIVE",
    )
    _lab.assistant = _AE(
        trade_ledger=trade_ledger,
        client_registry=client_registry,
        health_provider=health,
    )

    # -- v1.5.0 ACCOUNTS (mandatory TOTP 2FA login) + HIST DATA --------
    from data_engine.platform.historical_data import (
        HistoricalDataService as _Hist,
    )
    from data_engine.runtime.accounts import AccountService as _Accounts

    _accounts = _Accounts(state_root)
    _hist = _Hist(cache_dir=state_root / "hist-cache")

    return MonitoringAPI(
        auth_token=token,
        host=bind,
        port=port,
        health_provider=health,
        pairing_service=pairing_service,
        killswitch_state_provider=kill_switch.state,
        killswitch_activator=kill_switch.activate,
        client_registry=client_registry,
        trade_ledger=trade_ledger,
        lab=_lab,
        accounts=_accounts,
        bootstrap_presets=bootstrap_presets,
        hist_service=_hist,
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
        "--bootstrap-presets",
        action="store_true",
        help=(
            "v1.5.0: auto-create the TOP-5 YouTuber strategy presets "
            "(and open their 30-day paper windows) the first time bars "
            "land for a symbol that has no strategies yet. Activation "
            "still requires the owner's explicit YES (G6 unchanged)."
        ),
    )
    serve_parser.add_argument(
        "--monitor-state-dir",
        default="./monitor-state",
        help=(
            "v1.0.0: directory for the durable owner controls — kill "
            "switch state, client registry (registrations.json) and "
            "the trade ledger (trade_ledger.jsonl). Created on demand."
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

    # v1.0.0 (owner mandate): the HUMAN-principal resume path. STOP is
    # reachable from the paired phone (kill-switch POST); RESUME is
    # deliberately PC-gated — run this ON the machine.
    control_reset_parser = subparsers.add_parser(
        "control-reset",
        help=(
            "Reset the durable STOP flag on THIS PC (owner resume "
            "path; the monitoring API can never reset it)"
        ),
    )
    control_reset_parser.add_argument(
        "--monitor-state-dir",
        default="./monitor-state",
        help=(
            "directory holding kill_switch_state.json (same value as "
            "the serve --monitor-state-dir)"
        ),
    )
    control_reset_parser.add_argument(
        "--actor",
        default="owner-on-pc",
        help="audit identity recorded for this reset",
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

    # MT5 operator probe (genuine Exness MT5 DEMO feed): the ONLY
    # supported way to produce terminal evidence on the Windows host.
    # Reads credentials from the environment ONLY; never prints them.
    # Exit codes: 0 = verified; 2 = configuration/credential error;
    # 6 = fail-closed verification refusal; 7 = environment blocked
    # (MetaTrader5 package / Windows terminal unavailable → honest
    # NOT RUN, never a mock substitution).
    mt5_parser = subparsers.add_parser(
        "mt5-probe",
        help=(
            "Connect to the local MetaTrader 5 terminal (Windows), "
            "positively verify the DEMO environment and produce "
            "operator evidence (catalogue dump, symbol-map "
            "validation, bar/tick samples) — read-only, paper-only"
        ),
    )
    mt5_parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Full evidence run: connect → DEMO verification → "
            "health → catalogue count → M1 bar sample → tick sample "
            "→ clean disconnect (JSON report to stdout)"
        ),
    )
    mt5_parser.add_argument(
        "--dump-catalogue",
        metavar="PATH",
        help=(
            "write the OBSERVED symbol catalogue (JSON) to PATH — "
            "the input the operator uses to author a symbol-map "
            "proposal"
        ),
    )
    mt5_parser.add_argument(
        "--validate-map",
        metavar="PATH",
        help=(
            "validate the symbol-map PROPOSAL at PATH against the "
            "live terminal and write the digest-stamped validated "
            "map to PATH.validated.json"
        ),
    )
    mt5_parser.add_argument(
        "--symbol",
        metavar="CANONICAL",
        help=(
            "with --bars: fetch a bar sample for this canonical "
            "symbol (must be in the validated map)"
        ),
    )
    mt5_parser.add_argument(
        "--timeframe",
        default="M1",
        help="bar sample timeframe (default M1)",
    )
    mt5_parser.add_argument(
        "--bars",
        type=int,
        help="fetch a latest-bars sample of N bars for --symbol",
    )
    mt5_parser.add_argument(
        "--out",
        metavar="PATH",
        help="write the bar-sample JSON artifact (bars + provenance) to PATH",
    )
    mt5_parser.add_argument(
        "--stale-flag",
        action="store_true",
        help=(
            "report staleness as a flagged field instead of a "
            "refusal (for weekend/closed-market evidence runs)"
        ),
    )

    # -- v1.5.0: accounts (admin bootstrap) + historical data CLI -------
    add_admin_parser = subparsers.add_parser(
        "add-admin",
        help=(
            "v1.5.0: create the first ADMIN account (email + name; the "
            "password is read from a hidden prompt or stdin — NEVER a "
            "CLI argument). The account enrolls TOTP 2FA on first login."
        ),
    )
    add_admin_parser.add_argument("--email", required=True)
    add_admin_parser.add_argument("--name", required=True)
    add_admin_parser.add_argument(
        "--monitor-state-dir", default="./monitor-state"
    )
    add_admin_parser.add_argument(
        "--password-stdin",
        action="store_true",
        help="read the password from stdin instead of a hidden prompt",
    )
    accounts_list_parser = subparsers.add_parser(
        "accounts-list",
        help="v1.5.0: list accounts (emails/roles/2FA state/last login)",
    )
    accounts_list_parser.add_argument(
        "--monitor-state-dir", default="./monitor-state"
    )
    hist_datasets_parser = subparsers.add_parser(
        "hist-datasets",
        help=(
            "v1.5.0: list the bundled VERIFIED REAL historical datasets "
            "(sha256-checked against the source checksum)"
        ),
    )
    hist_import_parser = subparsers.add_parser(
        "hist-import",
        help=(
            "v1.5.0: import VERIFIED REAL history into the lab BarStore "
            "(bundled repo data first; Binance Vision website fallback)"
        ),
    )
    hist_import_parser.add_argument("--symbol", required=True)
    hist_import_parser.add_argument("--timeframe", default="1m")
    hist_import_parser.add_argument(
        "--source",
        default="auto",
        choices=["auto", "bundled", "binance-vision"],
    )
    hist_import_parser.add_argument("--months", type=int, default=1)
    hist_import_parser.add_argument(
        "--monitor-state-dir", default="./monitor-state"
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

        elif args.command == "control-reset":
            # v1.0.0: the owner's resume path (STOP came from the
            # phone; resume happens HERE, on the PC, human-gated).
            from pathlib import Path as _ResetPath

            from data_engine.runtime.control_state import DurableKillSwitch

            state_file = (
                _ResetPath(args.monitor_state_dir) / "kill_switch_state.json"
            )
            store = DurableKillSwitch(state_file)
            state = store.reset(actor=args.actor)
            print(
                "[control-reset] durable STOP flag cleared by "
                f"{args.actor}:"
            )
            print(f"  state: {state['state']}")
            print(f"  file:  {state_file}")
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
                        state_dir=args.monitor_state_dir,
                        bootstrap_presets=bool(args.bootstrap_presets),
                    )
                    print(
                        "[serve] durable owner controls wired from "
                        f"{args.monitor_state_dir} (kill-switch state + "
                        "client registry + trade ledger; STOP from the "
                        "phone now persists; resume = control-reset on "
                        "the PC)"
                    )
                    print(
                        "[serve] accounts + mandatory TOTP 2FA login "
                        "wired (POST /api/auth/login); create the first "
                        "admin with: data-engine add-admin --email ... "
                        "--monitor-state-dir " + args.monitor_state_dir
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

        elif args.command == "add-admin":
            from data_engine.runtime.accounts import (
                AccountError as _AccountError,
                AccountService as _Accounts,
            )

            if args.password_stdin:
                password = sys.stdin.readline().rstrip("\r\n")
            else:
                import getpass

                password = getpass.getpass(
                    f"Admin password for {args.email} (min 10 chars): "
                )
                confirm = getpass.getpass("Confirm password: ")
                if password != confirm:
                    print("[add-admin] passwords do not match", file=sys.stderr)
                    raise SystemExit(2)
            try:
                service = _Accounts(args.monitor_state_dir)
                record = service.store.create_account(
                    args.email, args.name, password, "admin"
                )
            except _AccountError as exc:
                print(f"[add-admin] REFUSED: {exc}", file=sys.stderr)
                raise SystemExit(2)
            print("[add-admin] ADMIN account created:")
            print(f"  email : {record['email']}")
            print(f"  name  : {record['name']}")
            print(f"  role  : {record['role']}")
            print(
                "  2FA   : enroll on first login in the monitor app "
                "(email + password -> the app shows the authenticator "
                "secret -> login again with the 6-digit code)"
            )
            raise SystemExit(0)
        elif args.command == "accounts-list":
            from data_engine.runtime.accounts import (
                AccountService as _Accounts,
            )

            service = _Accounts(args.monitor_state_dir)
            rows = service.store.list_accounts()
            if not rows:
                print(
                    "[accounts-list] no accounts yet — create the first "
                    "admin with: data-engine add-admin --email ... --name ..."
                )
                raise SystemExit(0)
            for row in rows:
                print(
                    f"{row['email']:<36} {row['role']:<7} "
                    f"2FA={'yes' if row['totp_enrolled'] else 'PENDING'} "
                    f"last_login={row['last_login_at'] or 'never'}"
                )
            raise SystemExit(0)
        elif args.command == "hist-datasets":
            from data_engine.platform.historical_data import (
                list_bundled_datasets as _list_ds,
            )

            rows = _list_ds()
            if not rows:
                print("[hist-datasets] no bundled datasets found")
                raise SystemExit(0)
            for row in rows:
                prov = row.get("coverage") or {}
                print(
                    f"{row['id']}: {row['rows']} bars "
                    f"({prov.get('start', '?')} -> {prov.get('end', '?')}) "
                    f"sha256={str(row.get('sha256', ''))[:16]}... "
                    f"[{row.get('governance', '')}]"
                )
            print(
                "[hist-datasets] all rows verified against the source's "
                "official checksum; RESEARCH_BACKTEST_ONLY"
            )
            raise SystemExit(0)
        elif args.command == "hist-import":
            from pathlib import Path as _LocalPath

            from data_engine.platform.historical_data import (
                HistoricalDataService as _Hist,
            )
            from data_engine.runtime.lab import BarStore as _BarStore

            try:
                service = _Hist(
                    cache_dir=_LocalPath(args.monitor_state_dir)
                    / "hist-cache"
                )
                fetched = service.fetch(
                    args.symbol,
                    args.timeframe,
                    months=args.months,
                    source=args.source,
                )
                bar_store = _BarStore(
                    _LocalPath(args.monitor_state_dir) / "bars"
                )
                result = service.import_into_barstore(
                    bar_store, args.symbol, fetched["bars"]
                )
            except Exception as exc:  # noqa: BLE001 — CLI boundary
                print(f"[hist-import] REFUSED: {exc}", file=sys.stderr)
                raise SystemExit(2)
            print(
                f"[hist-import] {args.symbol} {args.timeframe}: imported "
                f"{result['imported']} verified-real bars "
                f"(source: {fetched['source_used']}; store now holds "
                f"{result['total_in_store']})"
            )
            raise SystemExit(0)
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
                print("[Boundary] Valid calculation types:")
                for ct in CalculationType:
                    print(f"  - {ct.value}")

        elif args.command == "mt5-probe":
            # Genuine Exness MT5 DEMO operator probe — read-only,
            # paper-only. Credentials come from the environment ONLY
            # and are never printed. Exit codes (documented in the
            # parser): 0 verified / 2 config / 6 fail-closed refusal /
            # 7 environment blocked (honest NOT RUN).
            import json as _json

            from data_engine.platform.mt5_market_data import (
                ExnessMT5DemoFeed as _Feed,
                MT5ConfigError as _CfgErr,
            )
            from data_engine.platform.mt5_symbol_map import (
                MT5SymbolMap as _Map,
                MT5SymbolMapError as _MapErr,
                SymbolMapEntry as _Entry,
            )
            from data_engine.platform.mt5_terminal import (
                MT5CredentialsError as _CredErr,
                MT5TerminalConfig as _TermCfg,
                MT5TerminalError as _TermErr,
            )
            from data_engine.schemas import ProviderConfig as _ProvCfg

            def _fail(code: int, message: str) -> None:
                print(f"[mt5-probe] {message}", file=sys.stderr)
                raise SystemExit(code)

            try:
                terminal_config = _TermCfg.from_env()
            except _CredErr as exc:
                _fail(2, str(exc))

            # An explicit --symbol authorises an IDENTITY mapping
            # proposal (canonical == broker symbol) which is still
            # positively validated against the live terminal at
            # connect — nothing is assumed.
            proposals = None
            if args.symbol:
                proposals = (
                    _Entry(
                        canonical=args.symbol,
                        broker_symbol=args.symbol,
                    ),
                )

            provider_config = _ProvCfg(
                provider_name="exness-mt5-demo",
                provider_type="broker-terminal",
                supports_bid_ask=True,
            )
            feed = _Feed(
                provider_config,
                terminal_config=terminal_config,
                symbol_map_proposals=proposals,
            )

            # Environment gate FIRST: no MetaTrader5 module → honest
            # NOT RUN (exit 7), never a mock substitution.
            from data_engine.platform.mt5_terminal import (
                load_mt5_module as _load_module,
            )
            if _load_module() is None:
                _fail(
                    7,
                    "MetaTrader5 package not importable on this "
                    "platform (Windows-only) — probe NOT RUN; install "
                    "the package on the Windows terminal host and "
                    "export MT5_* environment variables (see "
                    "artifacts/mt5-integration/03-WINDOWS-HOST-SETUP.md)",
                )

            if args.dump_catalogue:
                try:
                    feed.connect()
                    rows = feed.symbol_catalogue()
                except (_TermErr, _CfgErr) as exc:
                    _fail(6, f"catalogue dump refused: {exc}")
                with open(args.dump_catalogue, "w", encoding="utf-8") as fh:
                    _json.dump(
                        {
                            "captured_at_utc": datetime.now(UTC).isoformat(),
                            "venue_server": feed.health_check().venue_server,
                            "symbol_count": len(rows),
                            "symbols": [dict(r) for r in rows],
                        },
                        fh,
                        indent=2,
                        default=str,
                    )
                print(
                    f"[mt5-probe] catalogue dumped: {len(rows)} symbols "
                    f"-> {args.dump_catalogue}"
                )
                feed.disconnect()

            if args.validate_map:
                try:
                    proposals = _Map.proposals_from_json(
                        open(args.validate_map, "r", encoding="utf-8").read()
                    )
                    feed.connect()
                    validated = _Map.validate(
                        proposals, feed._terminal, datetime.now(UTC)
                    )
                except (
                    _MapErr,
                    _TermErr,
                    _CfgErr,
                    FileNotFoundError,
                ) as exc:
                    _fail(6, f"map validation refused: {exc}")
                out_path = f"{args.validate_map}.validated.json"
                with open(out_path, "w", encoding="utf-8") as fh:
                    fh.write(validated.to_json())
                print(
                    f"[mt5-probe] symbol map VALIDATED against observed "
                    f"terminal metadata: {len(validated)} entries -> "
                    f"{out_path}"
                )
                feed.disconnect()

            if args.bars:
                if not args.symbol:
                    _fail(2, "--bars requires --symbol CANONICAL")
                try:
                    feed.connect()
                    batch = feed.latest_bars(
                        args.symbol,
                        args.timeframe,
                        int(args.bars),
                        stale_policy="flag" if args.stale_flag else "raise",
                    )
                except (_TermErr, _CfgErr, _MapErr) as exc:
                    _fail(6, f"bar sample refused: {exc}")
                except Exception as exc:  # noqa: BLE001 — verification refusals
                    _fail(6, f"bar sample refused: {exc}")
                payload = _json.loads(batch.model_dump_json())
                if args.out:
                    with open(args.out, "w", encoding="utf-8") as fh:
                        _json.dump(payload, fh, indent=2)
                    print(
                        f"[mt5-probe] {len(batch.bars)} {args.timeframe} "
                        f"bars for {args.symbol} (DEMO verified) -> "
                        f"{args.out}"
                    )
                else:
                    prov = payload["provenance"]
                    print(
                        f"[mt5-probe] {len(batch.bars)} {args.timeframe} "
                        f"bars for {args.symbol} — env={prov['environment']} "
                        f"server={prov['venue_server']} "
                        f"build={prov['terminal_build']} "
                        f"staleness={prov['staleness_seconds'] and round(prov['staleness_seconds'])}s "
                        f"sha256={prov['payload_sha256'][:12]}…"
                    )
                feed.disconnect()

            if args.self_test:
                report: dict = {"command": "mt5-probe --self-test"}
                try:
                    from data_engine.platform.mt5_market_data import (
                        MT5ConfigError as _SampCfg,
                    )

                    started = datetime.now(UTC)
                    health = feed.connect()
                    catalogue = feed.symbol_catalogue()
                    if args.symbol:
                        sample_symbol = args.symbol
                    elif feed.symbol_map and len(feed.symbol_map):
                        sample_symbol = feed.symbol_map.entries()[0].canonical
                    else:
                        raise _SampCfg(
                            "self-test sampling needs --symbol CANONICAL "
                            "or a validated symbol map"
                        )
                    bars = feed.latest_bars(
                        sample_symbol,
                        "M1",
                        5,
                        stale_policy="flag",
                    )
                    ticks = feed.latest_ticks(
                        sample_symbol, 5, stale_policy="flag"
                    )
                    report.update(
                        {
                            "status": "PASS",
                            "environment": "DEMO (positively verified)",
                            "health": _json.loads(health.model_dump_json()),
                            "symbol_count": len(catalogue),
                            "sample_symbol": bars.provenance.canonical,
                            "sample_bars": len(bars.bars),
                            "sample_ticks": len(ticks.ticks),
                            "bar_payload_sha256": bars.provenance.payload_sha256,
                            "started_at_utc": started.isoformat(),
                            "finished_at_utc": datetime.now(UTC).isoformat(),
                            "note": (
                                "read-only evidence — no order path was "
                                "available to this process"
                            ),
                        }
                    )
                    print(_json.dumps(report, indent=2))
                    feed.disconnect()
                except Exception as exc:  # noqa: BLE001 — fail-closed report
                    report.update(
                        {
                            "status": "FAIL (fail-closed)",
                            "error": str(exc),
                            "finished_at_utc": datetime.now(UTC).isoformat(),
                        }
                    )
                    print(_json.dumps(report, indent=2))
                    try:
                        feed.disconnect()
                    except Exception:  # noqa: BLE001
                        pass
                    raise SystemExit(6)

            if not (
                args.self_test
                or args.dump_catalogue
                or args.validate_map
                or args.bars
            ):
                _fail(2, "nothing to do — pass --self-test, --dump-catalogue, "
                         "--validate-map and/or --symbol/--bars")

    except Exception as e:
        print(f"[Data Engine] Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
