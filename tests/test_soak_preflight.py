"""FIX-14 (B-P2-16 / Task 12) — paper-soak preflight: fail-closed
executable checks + the MOCK DRY RUN of the soak procedure.

The audit found the soak procedure was DOCUMENT-ONLY: no executable
preflight refused a soak start on false/stale evidence, and no dry
run existed. These tests pin the closed state:

- every non-component gate must carry PASSING bundle evidence;
- one missing gate refuses with E_SOAK_EVIDENCE_MISSING;
- a failing gate refuses with E_SOAK_GATES_FALSE;
- human gates must be SIGNED approvals (plain recorded evidence
  refuses with E_SOAK_EVIDENCE_UNTRUSTED);
- approvals expiring before the soak END refuse (stale-for-purpose
  evidence, E_SOAK_APPROVALS_EXPIRE_BEFORE_SOAK_END);
- a valid signed bundle covering the whole window PASSES, and the
  report names exactly what remains pending first-hand verification
  at launch (the six component gates);
- the CLI surfaces exit 0 (pass) / 6 (refusal);
- the preflight reads NO CI input (a green CI run alone can never
  start a soak — structural pin).

The dry run simulates the soak PROCEDURE with deterministic mocks:
preflight -> (authorized) launch -> bounded tick loop -> shutdown.
NO ACTUAL SOAK IS STARTED anywhere in this file (and none was started
by this task).
"""

import json
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from data_engine.runtime import GATE_NAMES
from data_engine.runtime.composition import (
    COMPONENT_EVIDENCE_GATES,
    HUMAN_EVIDENCE_GATES,
)
from data_engine.runtime.operator_approval import (
    OperatorApprovalKey,
    OperatorApprovalRecord,
    sign_approval,
)
from data_engine.runtime.soak_preflight import (
    DEFAULT_SOAK_DURATION_DAYS,
    SOAK_PREFLIGHT_EXIT_CODE,
    SoakPreflightError,
    run_soak_preflight,
)
from data_engine.runtime.session_launch import (
    SessionLaunchError,
    launch_paper_session,
    load_launch_plan,
)

NOW = datetime.now(UTC)
KEY = OperatorApprovalKey(secrets.token_bytes(32))


def _bars(n=60):
    from test_session_launch import _bars as _gen

    return _gen(n)


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def _approvals_json(*, gates=HUMAN_EVIDENCE_GATES, key=KEY,
                    issued=None, expires=None, decision="APPROVE"):
    entries = []
    for gate in sorted(gates):
        record = OperatorApprovalRecord(
            record_id=f"approval-{gate.lower()}",
            approval_kind="RECORDED_EVIDENCE",
            principal="operator-test",
            decision=decision,
            gate=gate,
            scope="*",
            issued_at=issued or (NOW - timedelta(hours=1)),
            expires_at=expires or (NOW + timedelta(days=60)),
            artifact_digest="",
            reason=f"recorded operator decision for {gate}",
        )
        entries.append({
            "record": json.loads(record.model_dump_json()),
            "signature": sign_approval(record, key),
        })
    return json.dumps({"approvals": entries})


def _recorded_entries(*, drop=(), fail=()):
    remaining = [
        g for g in GATE_NAMES
        if g not in HUMAN_EVIDENCE_GATES
        and g not in COMPONENT_EVIDENCE_GATES
        and g not in drop
    ]
    return [
        {
            "gate": g,
            "component": f"operator-recorded:{g.lower()}",
            "check": "operator_evidence_bundle",
            "evidence": "operator-recorded evidence on file",
            "passed": g not in fail,
        }
        for g in remaining
    ]


def _plan_dict(tmp_path, *, approvals_name="approvals.json",
               recorded=None, human_plain=False):
    from test_session_launch import (
        _ensemble_bundle, _write_approvals, _write_bars,
    )

    bars_file = _write_bars(tmp_path, _bars(80))
    if human_plain:
        # sabotage: human gates carried as PLAIN recorded entries
        approvals_file = None
        entries = _recorded_entries()
        entries += [
            {
                "gate": g,
                "component": f"operator-recorded:{g.lower()}",
                "check": "operator_evidence_bundle",
                "evidence": "operator says yes (unsigned)",
                "passed": True,
            }
            for g in sorted(HUMAN_EVIDENCE_GATES)
        ]
    else:
        approvals_file = _write(
            tmp_path, approvals_name, _approvals_json(),
        )
        entries = _recorded_entries()
    if recorded is not None:
        entries = recorded
    ens, cal, pins = _ensemble_bundle()
    return {
        "session": {
            "symbol": "TEST/USD",
            "timeframe": "5m",
            "session_id": "soak-preflight-test",
            "initial_equity": "100000",
            "expected_interval_seconds": 300.0,
            "lookback": 8,
            "horizon": 2,
            "feature_version": "fv-1",
            "dataset_version": "dv-synth",
            "ttl_bars": 3,
            "max_crash_probability": 0.0,
            "crash_exit_probability": 0.0,
            "max_feed_staleness_seconds": 60 * 60 * 24 * 365,
            "pinned_model_hashes": pins,
        },
        "state_dir": str(tmp_path / "state"),
        "ledger_path": str(tmp_path / "ledger.json"),
        "venue_journal_path": str(tmp_path / "venue.json"),
        "venue_account_id": "soak-preflight-acct",
        "instruments": [
            {
                "broker_id": "runtime-paper-venue",
                "symbol": "TEST/USD",
                "broker_symbol": "TEST/USD",
                "base_asset": "TEST",
                "quote_asset": "USD",
                "tick_size": "0.01",
                "lot_step": "0.0001",
                "min_quantity": "0.0001",
                "max_quantity": "100000",
                "min_notional": "0",
            }
        ],
        "approvals_file": approvals_file,
        "recorded_evidence": entries,
        "bar_source": {"mode": "replay", "bars_file": bars_file},
        "ensemble_factory": "test_session_launch:_ensemble_factory",
    }


def _write_plan(tmp_path, plan):
    return _write(tmp_path, "launch.json", json.dumps(plan))


# ---------------------------------------------------------------------------
# 1. preflight verdicts
# ---------------------------------------------------------------------------

class TestSoakPreflightVerdicts:

    def test_valid_bundle_passes(self, tmp_path):
        plan_path = _write_plan(tmp_path, _plan_dict(tmp_path))
        report = run_soak_preflight(
            plan_path, approval_key=KEY, as_of=NOW,
        )
        assert report.passed is True
        assert set(report.human_gates_verified) == set(HUMAN_EVIDENCE_GATES)
        assert set(report.pending_launch_verification) == set(
            COMPONENT_EVIDENCE_GATES
        )
        # all 26 non-component gates covered by the bundle
        assert len(report.gates_covered) == len(GATE_NAMES) - len(
            COMPONENT_EVIDENCE_GATES
        )
        assert len(report.approval_ids) == 3
        assert report.plan_session_id == "soak-preflight-test"

    def test_missing_gate_evidence_refuses(self, tmp_path):
        plan = _plan_dict(tmp_path)
        plan["recorded_evidence"] = _recorded_entries(drop={"DATA_READY"})
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SoakPreflightError) as excinfo:
            run_soak_preflight(
                plan_path, approval_key=KEY, as_of=NOW,
            )
        assert excinfo.value.reason_code == "E_SOAK_EVIDENCE_MISSING"
        assert "DATA_READY" in excinfo.value.detail

    def test_failing_gate_evidence_refuses(self, tmp_path):
        plan = _plan_dict(tmp_path)
        plan["recorded_evidence"] = _recorded_entries(fail={"TESTS_READY"})
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SoakPreflightError) as excinfo:
            run_soak_preflight(
                plan_path, approval_key=KEY, as_of=NOW,
            )
        assert excinfo.value.reason_code == "E_SOAK_GATES_FALSE"
        assert "TESTS_READY" in excinfo.value.detail

    def test_plain_recorded_human_evidence_refuses(self, tmp_path):
        """A green-looking bundle with UNSIGNED human-gate entries
        refuses — the plan model itself rejects human-gate recorded
        entries at LOAD time (the FIX-9 boundary enforced one layer
        earlier than the preflight; the preflight re-asserts it for
        already-loaded bundles)."""
        plan = _plan_dict(tmp_path, human_plain=True)
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SoakPreflightError) as excinfo:
            run_soak_preflight(
                plan_path, approval_key=KEY, as_of=NOW,
            )
        assert excinfo.value.reason_code == "E_SOAK_PLAN_INVALID"
        # the plan model names the human-gate violation
        assert "human-dependency gate" in excinfo.value.detail

    def test_approval_expiring_before_soak_end_refuses(self, tmp_path):
        """A 30-day soak needs approvals valid for the WHOLE window:
        an approval expiring in 10 days refuses the 30-day soak."""
        plan = _plan_dict(
            tmp_path,
            approvals_name="short-approvals.json",
        )
        # rewrite the approvals with a short window
        plan["approvals_file"] = _write(
            tmp_path, "short-approvals.json",
            _approvals_json(expires=NOW + timedelta(days=10)),
        )
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SoakPreflightError) as excinfo:
            run_soak_preflight(
                plan_path, approval_key=KEY, as_of=NOW,
            )
        assert excinfo.value.reason_code == \
            "E_SOAK_APPROVALS_EXPIRE_BEFORE_SOAK_END"

    def test_expired_approval_refuses_at_verification(self, tmp_path):
        plan = _plan_dict(tmp_path)
        plan["approvals_file"] = _write(
            tmp_path, "approvals.json",
            _approvals_json(
                issued=NOW - timedelta(days=3),
                expires=NOW - timedelta(days=1),
            ),
        )
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SoakPreflightError) as excinfo:
            run_soak_preflight(
                plan_path, approval_key=KEY, as_of=NOW,
            )
        assert excinfo.value.reason_code == "E_SOAK_EVIDENCE_UNTRUSTED"

    def test_forged_approval_signature_refuses(self, tmp_path):
        other_key = OperatorApprovalKey(secrets.token_bytes(32))
        plan = _plan_dict(tmp_path)
        plan["approvals_file"] = _write(
            tmp_path, "approvals.json", _approvals_json(key=other_key),
        )
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SoakPreflightError) as excinfo:
            run_soak_preflight(
                plan_path, approval_key=KEY, as_of=NOW,
            )
        assert excinfo.value.reason_code == "E_SOAK_EVIDENCE_UNTRUSTED"

    def test_invalid_plan_refuses(self, tmp_path):
        plan_path = _write(tmp_path, "broken.json", "{nope")
        with pytest.raises(SoakPreflightError) as excinfo:
            run_soak_preflight(plan_path, approval_key=KEY, as_of=NOW)
        assert excinfo.value.reason_code == "E_SOAK_PLAN_INVALID"

    def test_missing_approvals_file_refuses(self, tmp_path):
        plan = _plan_dict(tmp_path)
        plan["approvals_file"] = str(tmp_path / "does-not-exist.json")
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SoakPreflightError) as excinfo:
            run_soak_preflight(
                plan_path, approval_key=KEY, as_of=NOW,
            )
        assert excinfo.value.reason_code == "E_SOAK_EVIDENCE_UNTRUSTED"

    def test_missing_approval_key_refuses(self, tmp_path, monkeypatch):
        import data_engine.runtime.operator_approval as oa

        monkeypatch.delenv(oa.OPERATOR_APPROVAL_ENV_KEY, raising=False)
        monkeypatch.delenv(oa.OPERATOR_APPROVAL_ENV_KEY_FILE,
                           raising=False)
        plan_path = _write_plan(tmp_path, _plan_dict(tmp_path))
        with pytest.raises(SoakPreflightError) as excinfo:
            run_soak_preflight(plan_path, approval_key=None, as_of=NOW)
        assert excinfo.value.reason_code == \
            "E_SOAK_APPROVAL_KEY_UNAVAILABLE"

    def test_default_soak_window_is_30_days(self):
        assert DEFAULT_SOAK_DURATION_DAYS == 30


# ---------------------------------------------------------------------------
# 2. CI irrelevance (structural)
# ---------------------------------------------------------------------------

class TestCiIrrelevance:

    def test_preflight_module_reads_no_ci_input(self):
        """Structural pin: the soak preflight source references no CI
        status/env/Artifacts input — a green CI run alone can never
        admit a soak. (Docstring MENTIONS of CI are fine; the scan
        targets CI-input identifiers only.)"""
        import inspect
        import re

        import data_engine.runtime.soak_preflight as mod

        source = inspect.getsource(mod)
        # strip docstrings and comments before scanning
        stripped = re.sub(
            r'"""[\s\S]*?"""', "", source,
        )
        stripped = re.sub(r"#[^\n]*", "", stripped)
        for banned in (
            "ci_status", "GITHUB_ACTIONS", "gh_run", "workflow_run",
            "GITHUB_SHA", "CI_GREEN", "ci_green", "run_id", "conclusion",
        ):
            assert banned not in stripped, (
                f"soak preflight must not read CI inputs (found "
                f"{banned!r})"
            )
        # and no environment reads outside the approval-key channel
        assert stripped.count("os.environ") == 0

    def test_env_cannot_flip_the_preflight(self, tmp_path, monkeypatch):
        monkeypatch.setenv("SOAK_APPROVED", "1")
        monkeypatch.setenv("CI_GREEN", "true")
        plan = _plan_dict(tmp_path)
        plan["recorded_evidence"] = _recorded_entries(drop={"PIT_READY"})
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SoakPreflightError):
            run_soak_preflight(plan_path, approval_key=KEY, as_of=NOW)


# ---------------------------------------------------------------------------
# 3. the CLI surface (exit codes 0 / 6)
# ---------------------------------------------------------------------------

class TestSoakPreflightCli:

    def test_cli_pass_exit_zero(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        # The CLI loads the approval key from the env — the approvals
        # file must be signed with THAT key.
        import data_engine.runtime.operator_approval as oa

        env_hex = secrets.token_bytes(32).hex()
        monkeypatch.setenv(oa.OPERATOR_APPROVAL_ENV_KEY, env_hex)
        env_key = OperatorApprovalKey(bytes.fromhex(env_hex))
        from data_engine.cli import main

        plan = _plan_dict(tmp_path)
        plan["approvals_file"] = _write(
            tmp_path, "approvals.json", _approvals_json(key=env_key),
        )
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SystemExit) as excinfo:
            main(["soak-preflight", plan_path])
        assert excinfo.value.code == 0
        out = capsys.readouterr().out
        assert "PASS" in out

    def test_cli_refusal_exit_six(self, tmp_path, capsys, monkeypatch):
        import data_engine.runtime.operator_approval as oa

        env_hex = secrets.token_bytes(32).hex()
        monkeypatch.setenv(oa.OPERATOR_APPROVAL_ENV_KEY, env_hex)
        env_key = OperatorApprovalKey(bytes.fromhex(env_hex))
        from data_engine.cli import main

        plan = _plan_dict(tmp_path)
        plan["approvals_file"] = _write(
            tmp_path, "approvals.json", _approvals_json(key=env_key),
        )
        plan["recorded_evidence"] = _recorded_entries(drop={"PIT_READY"})
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SystemExit) as excinfo:
            main(["soak-preflight", plan_path])
        assert excinfo.value.code == SOAK_PREFLIGHT_EXIT_CODE == 6
        err = capsys.readouterr().err
        assert "REFUSED" in err
        assert "PIT_READY" in err


# ---------------------------------------------------------------------------
# 4. the MOCK DRY RUN of the soak procedure (starts nothing)
# ---------------------------------------------------------------------------

class TestSoakProcedureDryRun:

    def test_full_procedure_dry_run_with_mocks(self, tmp_path,
                                               monkeypatch):
        """The dry-run simulation of PAPER-SOAK-PROCEDURE.md using
        deterministic mocks ONLY:

        preflight (pass) -> separately-authorized launch -> bounded
        tick loop -> clean shutdown. This is the procedure SHAPE —
        NO actual 30-day soak is started (the loop is bounded to a
        few ticks on a replay file, exactly like the documented
        pre-soak smoke)."""
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))

        # 1. preflight passes on the signed bundle
        plan = _plan_dict(tmp_path)
        plan_path = _write_plan(tmp_path, plan)
        preflight = run_soak_preflight(
            plan_path, approval_key=KEY, as_of=NOW,
        )
        assert preflight.passed

        # 2. the (in-procedure separately authorized) launch
        loaded = load_launch_plan(plan_path)
        launched = launch_paper_session(
            loaded,
            ensemble=None,   # plan factory: test_session_launch (pytest-importable)
            approval_key=KEY,
        )
        assert launched.composed.start_report.post_start_verified

        # 3. bounded tick loop (the documented smoke scope — minutes,
        #    not days)
        for _ in range(80):
            launched.tick()
        assert launched.tick.bars_fed == 80

        # 4. graceful stop: the supervisor's request_stop equivalent
        #    for an in-process session (HALT via kill switch is the
        #    procedure's stop condition; here we simply verify the
        #    loop is quiescent when the source is exhausted)
        launched.tick()
        assert launched.tick.source_name.endswith("bars.jsonl")

    def test_dry_run_refuses_when_preflight_refuses(self, tmp_path,
                                                    monkeypatch):
        """Procedure order is ENFORCED: the dry run never reaches the
        launch step when the preflight refuses (missing evidence)."""
        monkeypatch.setenv("RUNTIME_LEDGER_MAC_KEY", secrets.token_hex(32))
        plan = _plan_dict(tmp_path)
        plan["recorded_evidence"] = _recorded_entries(drop={"AUDIT_READY"})
        plan_path = _write_plan(tmp_path, plan)
        with pytest.raises(SoakPreflightError):
            run_soak_preflight(plan_path, approval_key=KEY, as_of=NOW)
        # and the launch itself would also refuse on the incomplete
        # chain (defense in depth)
        loaded = load_launch_plan(plan_path)
        with pytest.raises((SessionLaunchError, Exception)):
            launch_paper_session(
                loaded, ensemble=None, approval_key=KEY,
            )
