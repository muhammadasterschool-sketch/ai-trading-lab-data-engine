"""FIX-10 (B-P0-01) — the CLI/session wiring: deterministic
integration tests proving the supervisor drives a REAL paper session
loop.

The audit confirmed ``cli serve`` constructed ``PaperRuntimeService``
with NO ``tick_fn`` and no ``compose_operational_session`` wiring —
no operator path could ever run a session (B-P0-01). These tests pin
the CLOSED state:

- ``launch_paper_session`` composes + starts one operational PAPER
  session through the composition root (C1 order, FIX-9 trusted
  approvals enforced);
- the ``SessionTick`` wired into the supervisor loop CONSUMES the
  bar source and advances the governed runtime deterministically;
- a rejecting gate (kill switch) produces NO new orders;
- any accepted simulated order lands ONLY in the paper venue
  journal (never a real adapter — L1-L4 proofs cover the structural
  side; here we verify the wiring keeps routing to the paper venue);
- every launch failure refuses fail-closed with exit code 4 and an
  actionable message;
- the CLI ``serve --session-launch`` path surfaces the same exit
  codes (4 refused, 0 bounded clean run with ticks advanced).

All fixtures are deterministic replays/paper mocks. No network, no
real broker, no live trading.
"""

import json
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.runtime import GATE_NAMES
from data_engine.runtime.composition import (
    COMPONENT_EVIDENCE_GATES,
    HUMAN_EVIDENCE_GATES,
)
from data_engine.runtime.operator_approval import (
    OPERATOR_APPROVAL_ENV_KEY,
    OperatorApprovalKey,
    OperatorApprovalRecord,
    build_trusted_evidence,
    sign_approval,
)
from data_engine.runtime.session_launch import (
    SESSION_LAUNCH_EXIT_CODE,
    LaunchBarSource,
    LaunchRecordedEvidence,
    ReplayBarSource,
    SessionLaunchError,
    SessionLaunchPlan,
    SessionTick,
    launch_paper_session,
    load_launch_plan,
)

T0 = datetime(2026, 3, 1, 9, 0, tzinfo=UTC)
SYMBOL = "TEST/USD"
ACCOUNT = "launch-paper-acct"

#: Deterministic-replay staleness budget: the replay fixture's bar
#: timestamps are a fixed historical window, so the session opts into
#: a generous watchdog limit (the watchdog itself has dedicated
#: tests; here it must not starve the wiring proof of decisions).
REPLAY_STALENESS_SECONDS = 60 * 60 * 24 * 365

NOW = datetime.now(UTC)
_APPROVAL_KEY = OperatorApprovalKey(secrets.token_bytes(32))


def _ensemble_bundle():
    """The fitted world + the operator's model pins (F-14: every
    ensemble member's model hash, pinned in the session config)."""
    from test_runtime_e2e import _fit_world

    ens, cal = _fit_world()
    pins = [m.artifact().model_hash for m in ens.members]
    return ens, cal, pins


def _ensemble_factory():
    """Operator-style ensemble factory (referenced by the CLI-level
    plan as 'test_session_launch:_ensemble_factory' — the
    operator's own fitted-model loader stand-in). Returns
    (ensemble, calibrator)."""
    ens, cal, _pins = _ensemble_bundle()
    return ens, cal


def _bars(n=160, start=100.0, phase=6, drift=2.0, interval=300):
    bars = []
    price = start
    for i in range(n):
        d = drift if (i // phase) % 2 == 0 else -drift * 0.92
        o = price
        c = price + d
        bars.append({
            "timestamp": (T0 + timedelta(seconds=interval * i)).isoformat(),
            "open": str(o), "high": str(max(o, c) + 0.25),
            "low": str(min(o, c) - 0.25), "close": str(c),
            "volume": "5000",
        })
        price = c
    return bars


def _write_bars(tmp_path, bars, name="bars.jsonl"):
    path = tmp_path / name
    path.write_text(
        "\n".join(json.dumps(b) for b in bars) + "\n", encoding="utf-8",
    )
    return str(path)


def _write_approvals(tmp_path, *, gates=HUMAN_EVIDENCE_GATES,
                     key=_APPROVAL_KEY, name="approvals.json"):
    entries = []
    for gate in sorted(gates):
        record = OperatorApprovalRecord(
            record_id=f"approval-{gate.lower()}",
            approval_kind="RECORDED_EVIDENCE",
            principal="operator-test",
            decision="APPROVE",
            gate=gate,
            scope="*",
            issued_at=NOW - timedelta(hours=1),
            expires_at=NOW + timedelta(days=30),
            artifact_digest="",
            reason=f"recorded operator decision for {gate}",
        )
        entries.append({
            "record": json.loads(record.model_dump_json()),
            "signature": sign_approval(record, key),
        })
    path = tmp_path / name
    path.write_text(
        json.dumps({"approvals": entries}), encoding="utf-8",
    )
    return str(path)


def _recorded_evidence_entries():
    """Operator-attested recorded evidence for every NON-human,
    non-component gate (the remaining recorded-evidence class)."""
    remaining = [
        g for g in GATE_NAMES
        if g not in HUMAN_EVIDENCE_GATES and g not in COMPONENT_EVIDENCE_GATES
    ]
    return [
        {
            "gate": g,
            "component": f"operator-recorded:{g.lower()}",
            "check": "operator_evidence_bundle",
            "evidence": "operator-recorded evidence on file",
            "passed": True,
        }
        for g in remaining
    ]


def _plan_dict(bars_file, approvals_file, *, session_id="launch-test",
               state_dir="state", venue_account=ACCOUNT, pins=None,
               base_dir=None):
    if pins is None:
        _, _, pins = _ensemble_bundle()
    if base_dir is not None:
        state_dir = str(Path(base_dir) / state_dir)
    return {
        "session": {
            "symbol": SYMBOL,
            "timeframe": "5m",
            "session_id": session_id,
            "initial_equity": "100000",
            "expected_interval_seconds": 300.0,
            "lookback": 8,
            "horizon": 2,
            "feature_version": "fv-1",
            "dataset_version": "dv-synth",
            "ttl_bars": 3,
            "max_crash_probability": 0.0,   # notrade fixture discipline
            "crash_exit_probability": 0.0,
            "max_feed_staleness_seconds": REPLAY_STALENESS_SECONDS,
            "pinned_model_hashes": pins,
        },
        "state_dir": state_dir,
        "ledger_path": str(
            Path(state_dir).parent / "ledger.json"
        ) if base_dir is None else str(Path(base_dir) / "ledger.json"),
        "venue_journal_path": (
            str(Path(base_dir) / "venue.json")
            if base_dir is not None else "venue.json"
        ),
        "venue_account_id": venue_account,
        "instruments": [
            {
                "broker_id": "runtime-paper-venue",
                "symbol": SYMBOL,
                "broker_symbol": SYMBOL,
                "base_asset": "TEST",
                "quote_asset": "USD",
                "tick_size": "0.01",
                "lot_step": "0.0001",
                "min_quantity": "0.0001",
                "max_quantity": "100000",
                "min_notional": "0",
            }
        ],
        "venue_currency": "USD",
        "venue_initial_balance": "100000",
        "approvals_file": approvals_file,
        "recorded_evidence": _recorded_evidence_entries(),
        "bar_source": {"mode": "replay", "bars_file": bars_file},
        "ensemble_factory": "test_session_launch:_ensemble_factory",
    }


def _write_plan(tmp_path, plan, name="launch.json"):
    path = tmp_path / name
    path.write_text(json.dumps(plan), encoding="utf-8")
    return str(path)


@pytest.fixture
def mac_env(monkeypatch):
    monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))


@pytest.fixture
def approval_env(monkeypatch):
    monkeypatch.setenv(
        OPERATOR_APPROVAL_ENV_KEY, secrets.token_bytes(32).hex(),
    )


# ---------------------------------------------------------------------------
# 1. the launch itself
# ---------------------------------------------------------------------------

class TestLaunchPaperSession:

    def test_launch_composes_and_starts_the_session(self, tmp_path,
                                                     monkeypatch):
        """The headline B-P0-01 fix: a REAL operational paper session
        is composed + started from a launch plan (not just a
        supervisor shell)."""
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        bars_file = _write_bars(tmp_path, _bars(160))
        approvals_file = _write_approvals(tmp_path)
        plan = load_launch_plan(_write_plan(
            tmp_path, _plan_dict(bars_file, approvals_file,
                                 base_dir=tmp_path),
        ))
        launched = launch_paper_session(
            plan,
            ensemble=_ensemble_factory()[0],
            calibrator=_ensemble_factory()[1],
            approval_key=_APPROVAL_KEY,
        )
        assert launched.composed.start_report is not None
        assert launched.composed.start_report.post_start_verified
        # A launched operational session is live (RUNNING, trading
        # states only — never a half-ready INIT shell).
        assert launched.composed.runtime.state.value in (
            "RUNNING", "READY", "ACTIVE", "PAUSED",
        )

    def test_tick_consumes_bars_and_advances_the_loop(self, tmp_path,
                                                      monkeypatch):
        """The supervisor tick drives the governed runtime: bars are
        consumed, metrics advance, refusals are counted honestly."""
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        n = 150
        bars_file = _write_bars(tmp_path, _bars(n))
        approvals_file = _write_approvals(tmp_path)
        plan = load_launch_plan(_write_plan(
            tmp_path, _plan_dict(bars_file, approvals_file,
                                 base_dir=tmp_path),
        ))
        launched = launch_paper_session(
            plan,
            ensemble=_ensemble_factory()[0],
            calibrator=_ensemble_factory()[1],
            approval_key=_APPROVAL_KEY,
        )
        tick = launched.tick
        for _ in range(n + 5):   # drive past exhaustion too
            tick()
        assert tick.ticks == n + 5
        assert tick.bars_fed == n
        metrics = launched.composed.runtime.metrics
        assert metrics.counters.get("bars_processed", 0) == n

    def test_loop_is_deterministic_across_launches(self, tmp_path,
                                                    monkeypatch):
        """Two launches over the SAME plan + bars produce the SAME
        decision/order outcome counts (deterministic replay — no
        ambient clock or randomness leaks into the loop)."""
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        results = []
        for run in (1, 2):
            run_dir = tmp_path / f"run{run}"
            run_dir.mkdir()
            bars_file = _write_bars(tmp_path, _bars(150))
            approvals_file = _write_approvals(tmp_path)
            plan = load_launch_plan(_write_plan(
                run_dir,
                _plan_dict(bars_file, approvals_file, session_id="det",
                           base_dir=run_dir),
            ))
            # per-run state paths inside run_dir
            launched = launch_paper_session(
                plan,
                ensemble=_ensemble_factory()[0],
                calibrator=_ensemble_factory()[1],
                approval_key=_APPROVAL_KEY,
            )
            for _ in range(150):
                launched.tick()
            runtime = launched.composed.runtime
            results.append((
                metrics_snapshot(runtime),
                len(list(runtime.oms.orders())),
            ))
        assert results[0] == results[1]

    def test_orders_route_only_to_the_paper_venue(self, tmp_path,
                                                  monkeypatch):
        """Any simulated order the session produces lands in the
        PAPER venue journal (mock deterministic execution; a REAL
        adapter is structurally refused — L1-L4)."""
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        # A live-trading-flavored world: enough trend to fire organic
        # decisions (crash thresholds kept at the notrade fixture
        # discipline but decision engine left free to trade).
        bars_file = _write_bars(tmp_path, _bars(200))
        approvals_file = _write_approvals(tmp_path)
        plan = load_launch_plan(_write_plan(
            tmp_path, _plan_dict(bars_file, approvals_file,
                                 session_id="venue-route",
                                 base_dir=tmp_path),
        ))
        launched = launch_paper_session(
            plan,
            ensemble=_ensemble_factory()[0],
            calibrator=_ensemble_factory()[1],
            approval_key=_APPROVAL_KEY,
        )
        for _ in range(200):
            launched.tick()
        runtime = launched.composed.runtime
        venue = launched.composed.start_report.venue
        oms_orders = list(runtime.oms.orders())
        journal = venue.session.journal_records()
        # every order that reached SUBMITTED+ must have a venue
        # journal record with the same order identity (paper venue is
        # the ONLY executable route; nothing bypasses it).
        submitted = [
            o for o in oms_orders
            if o.status.value in (
                "SUBMITTED", "ACKNOWLEDGED", "PARTIALLY_FILLED",
                "FILLED", "CANCELLED", "REJECTED", "TIMED_OUT",
            )
        ]
        journal_ids = {
            r.get("payload", {}).get("order_id")
            for r in journal
        }
        for order in submitted:
            assert order.order_id in journal_ids

    def test_kill_switch_produces_no_new_orders(self, tmp_path,
                                                monkeypatch):
        """A rejecting gate (the kill switch) stops new submissions:
        the loop keeps consuming bars but creates no new orders."""
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        bars_file = _write_bars(tmp_path, _bars(150))
        approvals_file = _write_approvals(tmp_path)
        plan = load_launch_plan(_write_plan(
            tmp_path, _plan_dict(bars_file, approvals_file,
                                 session_id="killswitch",
                                 base_dir=tmp_path),
        ))
        launched = launch_paper_session(
            plan,
            ensemble=_ensemble_factory()[0],
            calibrator=_ensemble_factory()[1],
            approval_key=_APPROVAL_KEY,
        )
        runtime = launched.composed.runtime
        # warm up, then trip the unprivileged kill switch
        for _ in range(100):
            launched.tick()
        before = len(list(runtime.oms.orders()))
        from data_engine.runtime.kill_switch import KillSwitchScope

        runtime.kill_switch.trip(
            KillSwitchScope.PORTFOLIO,
            "operator halt (wiring test)",
            source="test.killswitch",
        )
        for _ in range(50):
            launched.tick()
        after = len(list(runtime.oms.orders()))
        assert after == before
        assert launched.tick.bars_fed == 150

    def test_replay_source_exhaustion_is_visible_not_fatal(self, tmp_path):
        source = ReplayBarSource(_write_bars(tmp_path, _bars(3)))
        assert source.next_bar() is not None
        assert source.next_bar() is not None
        assert source.next_bar() is not None
        assert source.next_bar() is None

    def test_replay_source_refuses_empty_file(self, tmp_path):
        empty = tmp_path / "empty.jsonl"
        empty.write_text("", encoding="utf-8")
        with pytest.raises(SessionLaunchError, match="no bars"):
            ReplayBarSource(empty)

    def test_replay_source_refuses_naive_timestamps(self, tmp_path):
        bad = tmp_path / "naive.jsonl"
        bad.write_text(
            json.dumps({
                "timestamp": "2026-03-01T09:00:00",  # naive — ambiguous
                "open": "1", "high": "1", "low": "1", "close": "1",
                "volume": "1",
            }),
            encoding="utf-8",
        )
        with pytest.raises(SessionLaunchError, match="tz-aware"):
            ReplayBarSource(bad)


def metrics_snapshot(runtime):
    """Deterministic, ambient-free metrics snapshot (counters only)."""
    m = runtime.metrics
    return {
        k: v for k, v in sorted(m.counters.items())
    }


# ---------------------------------------------------------------------------
# 2. fail-closed launch refusals (exit code 4 surface)
# ---------------------------------------------------------------------------

class TestLaunchRefusals:

    def _attempt(self, tmp_path, plan_dict):
        try:
            plan = load_launch_plan(_write_plan(tmp_path, plan_dict))
        except SessionLaunchError as exc:
            return exc
        try:
            return launch_paper_session(
                plan, ensemble=None, approval_key=_APPROVAL_KEY,
            )
        except SessionLaunchError as exc:
            return exc

    def test_missing_plan_file_refused(self, tmp_path):
        with pytest.raises(SessionLaunchError, match="not found"):
            load_launch_plan(tmp_path / "does-not-exist.json")

    def test_malformed_plan_json_refused(self, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(SessionLaunchError, match="invalid JSON"):
            load_launch_plan(bad)

    def test_unknown_bar_source_mode_refused(self, tmp_path):
        with pytest.raises(Exception, match="unknown"):
            LaunchBarSource(mode="telepathy")

    def test_unknown_provider_refused_with_honest_inventory(self, tmp_path):
        """B-P1-07 honesty: the launcher refuses to claim market
        support that has no proven adapter."""
        with pytest.raises(Exception, match="not a proven adapter"):
            LaunchBarSource(
                mode="provider", provider="forex_magic",
                symbol="EURUSD", interval_seconds=60,
            )

    def test_missing_approvals_file_refused(self, tmp_path,
                                               monkeypatch):
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY",
                           secrets.token_hex(32))
        bars_file = _write_bars(tmp_path, _bars(30))
        plan = _plan_dict(bars_file, str(tmp_path / "no-approvals.json"),
                           base_dir=tmp_path)
        exc = self._attempt(tmp_path, plan)
        assert isinstance(exc, SessionLaunchError)
        assert "approvals file not found" in str(exc)

    def test_incomplete_evidence_chain_refuses_start(self, tmp_path,
                                                        monkeypatch):
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY",
                           secrets.token_hex(32))
        """No recorded evidence for the recorded-evidence class gates
        => the readiness chain is incomplete => start REFUSED."""
        bars_file = _write_bars(tmp_path, _bars(30))
        approvals_file = _write_approvals(tmp_path)
        plan = _plan_dict(bars_file, approvals_file, base_dir=tmp_path)
        plan["recorded_evidence"] = []     # drop the recorded bundle
        exc = self._attempt(tmp_path, plan)
        assert isinstance(exc, SessionLaunchError)
        assert "REFUSED" in str(exc)

    def test_forged_signature_refused(self, tmp_path, monkeypatch):
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY",
                           secrets.token_hex(32))
        """An approvals file whose signatures were NOT made with the
        launch-time key is refused (FIX-9 boundary inside the
        launcher)."""
        bars_file = _write_bars(tmp_path, _bars(30))
        other_key = OperatorApprovalKey(secrets.token_bytes(32))
        approvals_file = _write_approvals(tmp_path, key=other_key)
        plan = _plan_dict(bars_file, approvals_file, base_dir=tmp_path)
        exc = self._attempt(tmp_path, plan)
        assert isinstance(exc, SessionLaunchError)
        assert "REFUSED" in str(exc)

    def test_human_gate_recorded_evidence_refused(self, tmp_path):
        """Free-text recorded evidence for a HUMAN gate is refused at
        plan validation (must go through the signed approvals file)."""
        with pytest.raises(Exception, match="human-dependency gate"):
            LaunchRecordedEvidence(
                gate="GOVERNANCE_READY",
                component="x", check="y",
                evidence="operator says yes", passed=True,
            )

    def test_unresolvable_ensemble_factory_refused(
            self, tmp_path, monkeypatch,
    ):
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY",
                           secrets.token_hex(32))
        bars_file = _write_bars(tmp_path, _bars(30))
        approvals_file = _write_approvals(tmp_path)
        plan = _plan_dict(bars_file, approvals_file, base_dir=tmp_path)
        plan["ensemble_factory"] = "no.such.module:factory"
        exc = self._attempt(tmp_path, plan)
        assert isinstance(exc, SessionLaunchError)
        assert "ensemble" in str(exc).lower()

    def test_approval_key_required_when_approvals_present(self, tmp_path,
                                                          monkeypatch):
        """Approvals present but no key anywhere (env unset, none
        injected) => launch refused (fail closed)."""
        monkeypatch.delenv(OPERATOR_APPROVAL_ENV_KEY, raising=False)
        bars_file = _write_bars(tmp_path, _bars(30))
        approvals_file = _write_approvals(tmp_path)
        plan = load_launch_plan(_write_plan(
            tmp_path, _plan_dict(bars_file, approvals_file,
                                 base_dir=tmp_path),
        ))
        with pytest.raises(SessionLaunchError, match="approval key"):
            launch_paper_session(plan, ensemble=_ensemble_factory()[0])


# ---------------------------------------------------------------------------
# 3. the CLI wiring (exit codes + honest supervisor-only default)
# ---------------------------------------------------------------------------

class TestCliServeSessionLaunch:

    def test_cli_exit_code_4_on_refused_launch(self, tmp_path, capsys,
                                               monkeypatch):
        """A refused launch surfaces exit code 4 with the actionable
        reason (never a silent supervisor start)."""
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        from data_engine.cli import main

        bars_file = _write_bars(tmp_path, _bars(30))
        plan = _plan_dict(bars_file, str(tmp_path / "missing.json"),
                           base_dir=tmp_path)
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SystemExit) as excinfo:
            main([
                "serve", "--session-launch", plan_path,
                "--no-dashboard",
            ])
        assert excinfo.value.code == SESSION_LAUNCH_EXIT_CODE == 4
        err = capsys.readouterr().err
        assert "SESSION LAUNCH REFUSED" in err

    def test_cli_bounded_run_advances_the_session(self, tmp_path, capsys,
                                                  monkeypatch):
        """The full CLI path: serve --session-launch composes the
        session, the supervisor loop drives its tick, and a bounded
        run exits 0 AFTER bars were consumed (loop advancement
        through the real entry point)."""
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        # The CLI path loads the approval key from the environment —
        # so the approvals file must be signed with THAT key.
        env_key_hex = secrets.token_bytes(32).hex()
        monkeypatch.setenv(OPERATOR_APPROVAL_ENV_KEY, env_key_hex)
        env_key = OperatorApprovalKey(bytes.fromhex(env_key_hex))
        from data_engine.cli import main

        bars_file = _write_bars(tmp_path, _bars(400))
        approvals_file = _write_approvals(tmp_path, key=env_key)
        plan_path = _write_plan(
            tmp_path,
            _plan_dict(bars_file, approvals_file, session_id="cli-run",
                       base_dir=tmp_path),
        )
        with pytest.raises(SystemExit) as excinfo:
            main([
                "serve", "--session-launch", plan_path,
                "--no-dashboard",
                "--tick-seconds", "0.01",
                "--heartbeat-seconds", "3600",
                "--max-seconds", "0.5",
            ])
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert "operational PAPER session composed and started" in out
        assert "graceful shutdown" in out

    def test_cli_without_session_launch_stays_honest_supervisor(
        self, tmp_path, capsys, monkeypatch,
    ):
        """Without --session-launch the supervisor REFUSES to start
        (readiness gate has no evidence in-process => exit 2) — it
        never fabricates a ready-looking session shell."""
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        from data_engine.cli import main

        with pytest.raises(SystemExit) as excinfo:
            main(["serve", "--no-dashboard"])
        assert excinfo.value.code == 2
        err = capsys.readouterr().err
        assert "PAPER_READY = FALSE" in err


# ---------------------------------------------------------------------------
# 4. plan model honesty
# ---------------------------------------------------------------------------

class TestPlanModel:

    def test_plan_rejects_unknown_top_level_keys(self):
        with pytest.raises(Exception):
            SessionLaunchPlan(
                session={"symbol": "X"},
                state_dir="s", ledger_path="l",
                venue_journal_path="v", venue_account_id="a",
                instruments=[],
                bar_source={"mode": "replay", "bars_file": "b.jsonl"},
                ensemble_factory="m:f",
                smuggled="no",
            )

    def test_plan_requires_ensemble_factory_ref_format(self):
        with pytest.raises(Exception, match="module:function"):
            SessionLaunchPlan(
                session={"symbol": "X"},
                state_dir="s", ledger_path="l",
                venue_journal_path="v", venue_account_id="a",
                instruments=[],
                bar_source={"mode": "replay", "bars_file": "b.jsonl"},
                ensemble_factory="not-a-ref",
            )

    def test_plan_session_validated_against_runtime_config(self):
        with pytest.raises(Exception):
            SessionLaunchPlan(
                session={"bogus_field": 1},
                state_dir="s", ledger_path="l",
                venue_journal_path="v", venue_account_id="a",
                instruments=[],
                bar_source={"mode": "replay", "bars_file": "b.jsonl"},
                ensemble_factory="m:f",
            )
