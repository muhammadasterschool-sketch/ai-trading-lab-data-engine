"""Explicit long-running paper-mode runtime entrypoint (reconstruction D-4/D-5).

Closes the verified G-03 mismatch: the systemd unit previously ran a
bare ``python -m data_engine.cli`` — a finite-command CLI whose
no-argument invocation prints help and EXITS 0, so the unit went
inactive immediately after start (Restart=on-failure then loops).
The CLI now exposes an explicit long-running ``serve`` subcommand
backed by THIS module.

Honest scope (fail-closed by construction):

- ``serve`` is a paper-mode SUPERVISOR: it enforces the paper
  readiness gate, enforces the loopback-only network posture for the
  read-only dashboard, and keeps the process alive with heartbeat
  logging + graceful signal handling. It does NOT drive a trading
  session by itself (session construction requires operator-provisioned
  config + evidence); the ``tick_fn`` seam exists for that future
  wiring and is exercised by tests.
- Startup is FAIL-CLOSED against the paper readiness gate
  (:class:`data_engine.runtime.readiness.PaperReadinessGate`): with no
  operator-submitted evidence the verdict is structurally FALSE
  (absent evidence is FALSE, never neutral), so the service REFUSES to
  start (exit code 2) until the readiness chain is completed.
- The dashboard (if enabled, default) binds LOOPBACK ONLY. Any
  non-loopback host is refused outright (exit code 3): remote exposure
  requires operator TLS/auth infrastructure that is deliberately NOT
  built — an unauthenticated dashboard must never face a public
  interface (D-5).

Exit codes:
  0 — clean shutdown (SIGTERM/SIGINT or bounded runtime reached)
  1 — unexpected error inside the supervision loop
  2 — readiness refusal (PAPER_READY = FALSE — fail-closed startup)
  3 — network-posture refusal (non-loopback dashboard bind requested)
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from datetime import UTC, datetime
from typing import Any, Callable, Optional

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_READY = 2
EXIT_NETWORK_REFUSED = 3


def _default_readiness_ok() -> bool:
    """Evaluate the authoritative paper readiness gate.

    No evidence is submitted at process start, so the verdict is
    structurally FALSE (absent evidence defaults to FALSE — §53). This
    is the fail-closed startup posture: the service must never run on
    an unevidenced readiness claim.
    """
    from data_engine.runtime.readiness import PaperReadinessGate

    return PaperReadinessGate().evaluate().paper_ready


def _default_snapshot_provider() -> Any:
    """Honest read-only dashboard snapshot: the platform's real empty
    state (no fabricated instruments, positions or trades)."""
    from data_engine.platform import AuditLog, InstrumentRegistry
    from data_engine.platform.dashboard import build_snapshot

    return build_snapshot(
        synchronized_at=datetime.now(UTC).isoformat(),
        registry=InstrumentRegistry(audit_log=AuditLog()),
        audit_log=AuditLog(),
    )


class PaperRuntimeService:
    """Long-running paper-mode supervisor (one process, one job)."""

    def __init__(
        self,
        *,
        readiness_fn: Optional[Callable[[], bool]] = None,
        snapshot_provider: Optional[Callable[[], Any]] = None,
        host: str = "127.0.0.1",
        port: int = 8017,
        enable_dashboard: bool = True,
        heartbeat_seconds: float = 30.0,
        tick_seconds: float = 1.0,
        max_seconds: Optional[float] = None,
        tick_fn: Optional[Callable[[], None]] = None,
        clock: Callable[[], float] = time.monotonic,
        sleep_fn: Callable[[float], None] = time.sleep,
        stdout=None,
        stderr=None,
        monitoring_api: Optional[Any] = None,
        heartbeat_sender: Optional[Any] = None,
    ) -> None:
        if tick_seconds <= 0 or heartbeat_seconds <= 0:
            raise ValueError("tick/heartbeat intervals must be positive")
        if max_seconds is not None and max_seconds <= 0:
            raise ValueError("max_seconds must be positive when set")
        self._readiness_fn = readiness_fn or _default_readiness_ok
        self._snapshot_provider = snapshot_provider or _default_snapshot_provider
        self._host = host
        self._port = port
        self._enable_dashboard = enable_dashboard
        self._heartbeat_seconds = heartbeat_seconds
        self._tick_seconds = tick_seconds
        self._max_seconds = max_seconds
        self._tick_fn = tick_fn
        self._clock = clock
        self._sleep = sleep_fn
        self._stdout = stdout if stdout is not None else sys.stdout
        self._stderr = stderr if stderr is not None else sys.stderr
        self._stop_requested = False
        self._dashboard: Optional[Any] = None
        self._dashboard_thread: Optional[threading.Thread] = None
        self._stop_reason = "bounded runtime reached"
        # Stage F wiring: authenticated monitoring API (F1) + one-way
        # outbound registry heartbeat (F6) — BOTH optional, BOTH
        # lifecycle-managed by the supervisor (started after the
        # readiness gate passes, stopped on graceful shutdown).
        self._monitoring_api = monitoring_api
        self._heartbeat_sender = heartbeat_sender

    # -- lifecycle -------------------------------------------------------

    @property
    def stop_reason(self) -> str:
        return self._stop_reason

    def request_stop(self, reason: str = "signal received") -> None:
        """Graceful-stop request (also used by the signal handlers)."""
        self._stop_requested = True
        self._stop_reason = reason

    def _install_signal_handlers(self) -> bool:
        """SIGTERM/SIGINT -> graceful stop. Returns False when signal
        handlers cannot be installed (non-main thread — tests install
        nothing and call :meth:`request_stop` directly)."""

        def _handler(signum, frame):  # pragma: no cover - thin shim
            self.request_stop(f"signal {signum} received")

        try:
            signal.signal(signal.SIGTERM, _handler)
            signal.signal(signal.SIGINT, _handler)
            return True
        except ValueError:
            return False

    def _start_dashboard(self) -> None:
        from data_engine.platform.dashboard import DashboardServer

        server = DashboardServer(
            snapshot_provider=self._snapshot_provider,
            host=self._host,
            port=self._port,
        )
        server.start()  # bind only; serving happens on the thread
        self._dashboard = server
        self._dashboard_thread = threading.Thread(
            target=server.serve_forever,
            name="aitl-dashboard",
            daemon=True,
        )
        self._dashboard_thread.start()
        # Wait until the serving thread actually entered serve_forever,
        # so a later shutdown() reliably stops the loop (avoids the
        # bind-then-immediately-close race in short bounded runs).
        deadline = time.monotonic() + 2.0
        while not server._serving and time.monotonic() < deadline:
            time.sleep(0.005)
        print(
            f"[serve] read-only dashboard bound loopback-only: "
            f"{server.url} (no auth/TLS — remote exposure REFUSED by design)",
            file=self._stdout,
            flush=True,
        )

    def _stop_dashboard(self) -> None:
        if self._dashboard is not None:
            self._dashboard.shutdown()
            if self._dashboard_thread is not None:
                self._dashboard_thread.join(timeout=2.0)
                self._dashboard_thread = None
            self._dashboard = None

    def _stop_auxiliary_services(self) -> None:
        """Stop the Stage F surfaces (monitoring API, heartbeat sender)
        in reverse startup order; failures are logged, never fatal."""
        if self._heartbeat_sender is not None:
            try:
                self._heartbeat_sender.stop()
            except Exception as exc:  # graceful shutdown stays graceful
                print(
                    f"[serve] heartbeat sender stop issue: "
                    f"{type(exc).__name__}",
                    file=self._stderr,
                    flush=True,
                )
        if self._monitoring_api is not None:
            try:
                self._monitoring_api.stop()
            except Exception as exc:
                print(
                    f"[serve] monitoring API stop issue: "
                    f"{type(exc).__name__}",
                    file=self._stderr,
                    flush=True,
                )

    def run(self) -> int:
        """Run the supervisor to completion; returns the exit code."""
        # 1. fail-closed readiness gate -----------------------------------
        if not self._readiness_fn():
            print(
                "[serve] REFUSING TO START: PAPER_READY = FALSE "
                "(fail-closed startup — the paper readiness gate holds "
                "no passing evidence in this process). No trading, no "
                "dashboard, no half-running service. Exit 2.",
                file=self._stderr,
                flush=True,
            )
            return EXIT_NOT_READY

        # 2. fail-closed network posture (D-5) -----------------------------
        if self._enable_dashboard and self._host not in LOOPBACK_HOSTS:
            print(
                f"[serve] REFUSING non-loopback dashboard bind to "
                f"{self._host!r}: the read-only dashboard has NO "
                "authentication and NO TLS; remote exposure requires an "
                "explicit operator infrastructure decision (reverse "
                "proxy + TLS + auth). Exit 3.",
                file=self._stderr,
                flush=True,
            )
            return EXIT_NETWORK_REFUSED

        # 3. startup --------------------------------------------------------
        self._stop_requested = False
        self._stop_reason = "bounded runtime reached"
        self._install_signal_handlers()
        started = self._clock()
        if self._enable_dashboard:
            self._start_dashboard()
        if self._monitoring_api is not None:
            self._monitoring_api.start()
            print(
                f"[serve] authenticated monitoring API bound "
                f"{self._monitoring_api.bind_host}:"
                f"{self._monitoring_api.bind_port} "
                "(token auth + rate limit; read-only + kill switch)",
                file=self._stdout,
                flush=True,
            )
        if self._heartbeat_sender is not None:
            self._heartbeat_sender.start()
            print(
                "[serve] one-way outbound registry heartbeat started "
                "(graceful degradation: engine operation never depends "
                "on registry reachability)",
                file=self._stdout,
                flush=True,
            )
        print(
            "[serve] paper-mode supervisor started (PAPER-ONLY posture; "
            "live execution is structurally refused elsewhere in the "
            "runtime; no trading session is driven by this supervisor).",
            file=self._stdout,
            flush=True,
        )

        # 4. supervision loop ------------------------------------------------
        last_beat = None
        try:
            while not self._stop_requested:
                now = self._clock()
                if (
                    self._max_seconds is not None
                    and now - started >= self._max_seconds
                ):
                    self.request_stop("bounded runtime reached")
                    break
                if self._tick_fn is not None:
                    self._tick_fn()
                if last_beat is None or now - last_beat >= self._heartbeat_seconds:
                    print(
                        "[serve] heartbeat: supervisor alive (utc="
                        f"{datetime.now(UTC).isoformat()}); stop_reason="
                        f"{self._stop_reason!r}",
                        file=self._stdout,
                        flush=True,
                    )
                    last_beat = now
                self._sleep(self._tick_seconds)
        except Exception as exc:  # noqa: BLE001 - supervisor must not die silently
            print(
                f"[serve] UNEXPECTED ERROR in supervision loop: "
                f"{type(exc).__name__}: {exc} — shutting down, exit 1",
                file=self._stderr,
                flush=True,
            )
            self._stop_auxiliary_services()
            self._stop_dashboard()
            return EXIT_ERROR

        # 5. graceful shutdown -------------------------------------------------
        self._stop_auxiliary_services()
        self._stop_dashboard()
        print(
            f"[serve] graceful shutdown ({self._stop_reason}); exit 0",
            file=self._stdout,
            flush=True,
        )
        return EXIT_OK


__all__ = [
    "PaperRuntimeService",
    "LOOPBACK_HOSTS",
    "EXIT_OK",
    "EXIT_ERROR",
    "EXIT_NOT_READY",
    "EXIT_NETWORK_REFUSED",
]
