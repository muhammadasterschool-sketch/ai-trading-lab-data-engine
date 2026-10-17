"""Reconstruction D-4/D-5 — lifecycle tests for the explicit paper-mode
runtime entrypoint (``data_engine.cli serve`` /
``runtime.service.PaperRuntimeService``).

Pins (G-03 closure):

- fail-closed startup: with the real (evidence-less) readiness gate the
  service REFUSES to start (exit 2) — including via the real CLI in a
  subprocess;
- bounded run: startup -> heartbeat loop -> graceful shutdown -> exit 0;
- graceful interruption: a stop request (the same path SIGTERM/SIGINT
  take) exits 0 with the reason recorded;
- exception path: an unexpected error in the supervision loop exits 1;
- network posture (D-5): the dashboard binds loopback only, and a
  non-loopback bind request is REFUSED (exit 3) — no unauthenticated
  dashboard ever faces a non-loopback interface;
- invalid configuration is rejected up front.

All output is captured via injectable streams; no secrets are involved
anywhere (the service handles no credentials at all).
"""

import io
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from data_engine.runtime.service import (
    EXIT_ERROR,
    EXIT_NETWORK_REFUSED,
    EXIT_NOT_READY,
    EXIT_OK,
    PaperRuntimeService,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _svc(**over) -> PaperRuntimeService:
    defaults = dict(
        readiness_fn=lambda: True,
        enable_dashboard=False,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    defaults.update(over)
    return PaperRuntimeService(**defaults)


class TestFailClosedStartup:
    def test_real_evidence_less_readiness_refuses_start(self):
        """The DEFAULT readiness source is the authoritative gate with
        no submitted evidence -> structurally FALSE -> refusal."""
        svc = _svc(readiness_fn=None)
        assert svc.run() == EXIT_NOT_READY

    def test_explicit_false_readiness_refuses_start(self):
        out, err = io.StringIO(), io.StringIO()
        svc = _svc(readiness_fn=lambda: False, stderr=err)
        assert svc.run() == EXIT_NOT_READY
        assert "REFUSING TO START" in err.getvalue()
        assert "PAPER_READY = FALSE" in err.getvalue()

    def test_refusal_starts_no_dashboard(self):
        """A refused start must not leave a bound socket behind."""
        svc = _svc(readiness_fn=lambda: False, enable_dashboard=True, port=0)
        assert svc.run() == EXIT_NOT_READY
        assert svc._dashboard is None


class TestNetworkPosture:
    def test_non_loopback_bind_is_refused(self):
        err = io.StringIO()
        svc = _svc(host="0.0.0.0", enable_dashboard=True, stderr=err)
        assert svc.run() == EXIT_NETWORK_REFUSED
        assert "non-loopback" in err.getvalue()

    def test_non_loopback_refused_even_for_localhost_alias_gap(self):
        svc = _svc(host="192.168.1.10", enable_dashboard=True)
        assert svc.run() == EXIT_NETWORK_REFUSED

    def test_default_host_is_loopback(self):
        assert _svc()._host == "127.0.0.1"

    def test_dashboard_binds_loopback_and_shuts_down_cleanly(self):
        out = io.StringIO()
        seen = {}

        def probe():
            dash = svc._dashboard
            assert dash is not None
            seen["url"] = dash.url
            assert dash.bound_port, "dashboard port must be bound"

        svc = _svc(
            enable_dashboard=True,
            port=0,
            max_seconds=0.15,
            tick_seconds=0.01,
            tick_fn=probe,
            stdout=out,
        )
        assert svc.run() == EXIT_OK
        assert seen["url"].startswith("http://127.0.0.1:")
        assert svc._dashboard is None, "dashboard must be shut down"
        assert "loopback-only" in out.getvalue()


class TestLifecycle:
    def test_bounded_run_exits_zero(self):
        out = io.StringIO()
        svc = _svc(max_seconds=0.06, tick_seconds=0.01, stdout=out)
        assert svc.run() == EXIT_OK
        assert svc.stop_reason == "bounded runtime reached"
        assert "graceful shutdown" in out.getvalue()

    def test_stop_request_mirrors_signal_path_exits_zero(self):
        result = {}

        def runner():
            result["code"] = svc.run()

        svc = _svc(max_seconds=None, sleep_fn=lambda s: time.sleep(0.005))
        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        time.sleep(0.05)
        # This is the exact code path the SIGTERM/SIGINT handlers take.
        svc.request_stop("signal 15 received")
        thread.join(timeout=2.0)
        assert not thread.is_alive()
        assert result["code"] == EXIT_OK
        assert svc.stop_reason == "signal 15 received"

    def test_tick_exception_exits_one(self):
        err = io.StringIO()

        def boom():
            raise RuntimeError("synthetic supervision failure")

        svc = _svc(tick_fn=boom, stderr=err)
        assert svc.run() == EXIT_ERROR
        assert "UNEXPECTED ERROR" in err.getvalue()
        assert "RuntimeError" in err.getvalue()

    def test_invalid_configuration_rejected_up_front(self):
        with pytest.raises(ValueError):
            _svc(tick_seconds=0)
        with pytest.raises(ValueError):
            _svc(heartbeat_seconds=0)
        with pytest.raises(ValueError):
            _svc(max_seconds=0)


class TestCliIntegration:
    def test_real_cli_serve_refuses_while_not_ready(self):
        """End-to-end: `python -m data_engine.cli serve` must exit 2 with
        the fail-closed refusal (current real-world posture, honestly
        pinned: PAPER_READY = FALSE until the evidence chain passes)."""
        proc = subprocess.run(
            [sys.executable, "-m", "data_engine.cli", "serve",
             "--no-dashboard"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=REPO_ROOT,
        )
        assert proc.returncode == EXIT_NOT_READY, (
            proc.stdout + proc.stderr
        )
        assert "REFUSING TO START" in proc.stderr

    def test_cli_serve_registers_in_help(self):
        proc = subprocess.run(
            [sys.executable, "-m", "data_engine.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=60,
            cwd=REPO_ROOT,
        )
        assert proc.returncode == 0
        assert "serve" in proc.stdout
