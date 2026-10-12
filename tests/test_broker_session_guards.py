"""BrokerSession guard tests (multi-broker mandate, Phase M1).

Pins the fail-closed submission pipeline: injectable risk/kill-switch
gates (absent ⇒ refuse everything), account isolation, journal-backed
idempotency (across restarts), bounded deterministic retry, reconnect
behaviour, UNKNOWN-outcome degradation + reconciliation recovery,
divergence handling and journal tamper-evidence. The central-gate
independence proof runs PARAMETRIZED over all four venues: the same
gate refusal blocks every broker.
"""

import json
from datetime import datetime, UTC
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.brokers import (
    BinanceSpotMockAdapter,
    BrokerCredential,
    BrokerErrorCategory,
    BrokerSession,
    BybitV5MockAdapter,
    KillSwitchState,
    MT5StyleMockAdapter,
    OrderKind,
    OrderRefusedError,
    OrderRequest,
    PaperBrokerAdapter,
    RetryPolicy,
    RiskDecision,
    Side,
    TimeInForce,
    UnknownOrderStateError,
    VenueOrderStatus,
)
from data_engine.brokers.errors import BrokerExecutionError
from data_engine.brokers.session import SessionJournalError

ACCOUNT = "acct-1"
SECRET = "mock-secret-material-DO-NOT-PRINT"
FIXED_TS = datetime(2026, 10, 12, 12, 0, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return FIXED_TS


ADAPTER_FACTORIES = {
    "paper-mock": PaperBrokerAdapter,
    "mt5-mock": MT5StyleMockAdapter,
    "binance-mock": BinanceSpotMockAdapter,
    "bybit-mock": BybitV5MockAdapter,
}

BTC_SYMBOL = {
    "paper-mock": "BTCUSDT",
    "mt5-mock": "BTCUSD",
    "binance-mock": "BTCUSDT",
    "bybit-mock": "BTCUSDT",
}


def approve(request: OrderRequest) -> RiskDecision:
    return RiskDecision(approved=True, reason="within limits")


def reject(request: OrderRequest) -> RiskDecision:
    return RiskDecision(
        approved=False, reason="position limit exceeded",
        failed_checks=("position_limit",),
    )


def switch_off() -> KillSwitchState:
    return KillSwitchState(active=False)


def switch_on() -> KillSwitchState:
    return KillSwitchState(
        active=True, reason="daily loss limit breached", scope="ACCOUNT"
    )


def _request(broker_id: str, cid: str, qty: Decimal = Decimal("0.02"), **extra):
    kwargs = dict(
        client_order_id=cid, account_id=ACCOUNT, symbol=BTC_SYMBOL[broker_id],
        side=Side.BUY, order_kind=OrderKind.MARKET, quantity=qty,
    )
    kwargs.update(extra)
    return OrderRequest(**kwargs)


def _session(broker_id: str, tmp_path: Path, *, risk=approve, kill=switch_off,
             sleeper=None, retry=None, account: str = ACCOUNT):
    adapter = ADAPTER_FACTORIES[broker_id](fixed_clock)
    session = BrokerSession(
        adapter,
        account_id=account,
        journal_path=tmp_path / f"journal-{broker_id}.json",
        risk_decision_fn=risk,
        kill_switch_fn=kill,
        sleeper=sleeper if sleeper is not None else (lambda s: None),
        retry_policy=retry,
        clock=fixed_clock,
    )
    session.connect(BrokerCredential(account, SECRET))
    return session


@pytest.fixture(params=list(ADAPTER_FACTORIES))
def session(request, tmp_path) -> BrokerSession:
    return _session(request.param, tmp_path)


class SleepRecorder:
    def __init__(self):
        self.sleeps = []

    def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)


# ---------------------------------------------------------------------------
# Fail-closed gates
# ---------------------------------------------------------------------------

class TestSessionGates:

    def test_missing_risk_gate_refuses_everything(self, tmp_path):
        session = _session("paper-mock", tmp_path, risk=None)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "g-1"))
        assert exc.value.reason_code == "GATE_MISSING_RISK"
        assert session.adapter.submit_attempts == 0  # venue never called

    def test_missing_kill_switch_gate_refuses_everything(self, tmp_path):
        session = _session("paper-mock", tmp_path, kill=None)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "g-2"))
        assert exc.value.reason_code == "GATE_MISSING_KILL_SWITCH"
        assert session.adapter.submit_attempts == 0

    def test_active_kill_switch_refuses_before_venue(self, tmp_path):
        session = _session("paper-mock", tmp_path, kill=switch_on)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "g-3"))
        assert exc.value.reason_code == "KILL_SWITCH_ACTIVE"
        assert "daily loss limit" in str(exc.value)
        assert session.adapter.submit_attempts == 0

    def test_risk_refusal_names_failed_checks(self, tmp_path):
        session = _session("paper-mock", tmp_path, risk=reject)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "g-4"))
        assert exc.value.reason_code == "RISK_REFUSED"
        assert "position_limit" in str(exc.value)
        assert session.adapter.submit_attempts == 0

    def test_kill_switch_is_checked_before_risk(self, tmp_path):
        risk_calls = []

        def counting_risk(request):
            risk_calls.append(request)
            return RiskDecision(approved=False, reason="would refuse")

        session = _session(
            "paper-mock", tmp_path, risk=counting_risk, kill=switch_on
        )
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "g-5"))
        assert exc.value.reason_code == "KILL_SWITCH_ACTIVE"
        assert risk_calls == []  # risk gate never even consulted

    def test_risk_gate_receives_the_exact_request(self, tmp_path):
        seen = []

        def capturing_risk(request):
            seen.append(request)
            return RiskDecision(approved=True)

        session = _session("paper-mock", tmp_path, risk=capturing_risk)
        req = _request("paper-mock", "g-6")
        session.submit_order(req)
        assert seen == [req]

    def test_risk_gate_exception_propagates_fail_closed(self, tmp_path):
        def exploding_risk(request):
            raise RuntimeError("risk engine unavailable")

        session = _session("paper-mock", tmp_path, risk=exploding_risk)
        with pytest.raises(RuntimeError):
            session.submit_order(_request("paper-mock", "g-7"))
        assert session.adapter.submit_attempts == 0

    def test_account_isolation_at_session_level(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "g-8",
                                          account_id="OTHER"))
        assert exc.value.reason_code == "ACCOUNT_ISOLATION"
        assert session.adapter.submit_attempts == 0

    def test_health_gate_blocks_when_disconnected(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        session.disconnect()
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "g-9"))
        assert exc.value.reason_code == "ADAPTER_NOT_CONNECTED"

    def test_refusals_are_journaled_but_do_not_block_resubmission(self, tmp_path):
        kill_state = {"active": True}

        def toggling_switch():
            return KillSwitchState(active=kill_state["active"])

        session = _session("paper-mock", tmp_path, kill=toggling_switch)
        with pytest.raises(OrderRefusedError):
            session.submit_order(_request("paper-mock", "g-10"))
        refusals = [r for r in session.journal_records()
                    if r.entry_type == "ORDER_REFUSED"]
        assert refusals and refusals[0].reason_code == "KILL_SWITCH_ACTIVE"
        # Fix the condition → the SAME request now goes through.
        kill_state["active"] = False
        ack = session.submit_order(_request("paper-mock", "g-10"))
        assert ack.status is VenueOrderStatus.FILLED

    def test_connect_refuses_credential_for_another_account(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        from data_engine.brokers import CredentialError
        with pytest.raises(CredentialError):
            session.connect(BrokerCredential("OTHER", SECRET))

    def test_reconnect_without_connect_refuses(self, tmp_path):
        adapter = ADAPTER_FACTORIES["paper-mock"](fixed_clock)
        session = BrokerSession(
            adapter, account_id=ACCOUNT,
            journal_path=tmp_path / "j.json", clock=fixed_clock,
        )
        with pytest.raises(OrderRefusedError) as exc:
            session.reconnect()
        assert exc.value.reason_code == "NEVER_CONNECTED"


# ---------------------------------------------------------------------------
# Central-gate independence (parametrized over every venue)
# ---------------------------------------------------------------------------

class TestCentralGateIndependence:

    @pytest.mark.parametrize("broker_id", list(ADAPTER_FACTORIES))
    def test_risk_refusal_blocks_every_broker(self, broker_id, tmp_path):
        session = _session(broker_id, tmp_path, risk=reject)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request(broker_id, "ind-1"))
        assert exc.value.reason_code == "RISK_REFUSED"
        assert session.adapter.submit_attempts == 0

    @pytest.mark.parametrize("broker_id", list(ADAPTER_FACTORIES))
    def test_kill_switch_blocks_every_broker(self, broker_id, tmp_path):
        session = _session(broker_id, tmp_path, kill=switch_on)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request(broker_id, "ind-2"))
        assert exc.value.reason_code == "KILL_SWITCH_ACTIVE"
        assert session.adapter.submit_attempts == 0

    @pytest.mark.parametrize("broker_id", list(ADAPTER_FACTORIES))
    def test_approved_order_reaches_every_broker(self, broker_id, tmp_path):
        session = _session(broker_id, tmp_path)
        ack = session.submit_order(_request(broker_id, "ind-3"))
        assert ack.status is VenueOrderStatus.FILLED
        assert session.adapter.executed_orders == 1


# ---------------------------------------------------------------------------
# Capability + precision pre-venue checks
# ---------------------------------------------------------------------------

class TestPreVenueChecks:

    def test_unsupported_order_kind_never_reaches_venue(self, tmp_path):
        session = _session("binance-mock", tmp_path)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request(
                "binance-mock", "cap-1",
                order_kind=OrderKind.STOP, stop_price=Decimal("49000.00"),
            ))
        assert exc.value.reason_code == "UNSUPPORTED_ORDER_KIND"
        assert session.adapter.submit_attempts == 0

    def test_attached_sltp_refused_on_separate_orders_venues(self, tmp_path):
        session = _session("binance-mock", tmp_path)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request(
                "binance-mock", "cap-2", stop_loss=Decimal("47000.00"),
            ))
        assert exc.value.reason_code == "SLTP_SEMANTICS_MISMATCH"
        assert "separate" in str(exc.value)

    def test_attached_sltp_accepted_on_attached_venues(self, tmp_path):
        for broker in ("paper-mock", "mt5-mock", "bybit-mock"):
            session = _session(broker, tmp_path)
            ack = session.submit_order(_request(
                broker, f"cap-3-{broker}",
                stop_loss=Decimal("47000.00"), take_profit=Decimal("55000.00"),
            ))
            assert ack.status is VenueOrderStatus.FILLED

    def test_unsupported_time_in_force_refused(self, tmp_path):
        session = _session("mt5-mock", tmp_path)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request(
                "mt5-mock", "cap-4", time_in_force=TimeInForce.FOK,
            ))
        assert exc.value.reason_code == "UNSUPPORTED_TIME_IN_FORCE"

    def test_reduce_only_refused_where_unsupported(self, tmp_path):
        session = _session("binance-mock", tmp_path)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("binance-mock", "cap-5",
                                          reduce_only=True))
        assert exc.value.reason_code == "REDUCE_ONLY_UNSUPPORTED"

    def test_unknown_symbol_refused_pre_venue(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "cap-6",
                                          symbol="NOTASYMBOL"))
        assert exc.value.reason_code == "UNKNOWN_SYMBOL"

    def test_precision_violation_refused_pre_venue(self, tmp_path):
        session = _session("binance-mock", tmp_path)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("binance-mock", "cap-7",
                                          qty=Decimal("0.020005")))
        assert exc.value.reason_code == "PRECISION_INVALID"
        assert session.adapter.submit_attempts == 0

    def test_min_notional_rejected_by_venue_via_session(self, tmp_path):
        session = _session("binance-mock", tmp_path)
        ack = session.submit_order(_request("binance-mock", "cap-8",
                                            qty=Decimal("0.0001")))
        assert ack.status is VenueOrderStatus.REJECTED
        assert ack.venue_code == "-1013"


# ---------------------------------------------------------------------------
# Idempotency (journal-backed)
# ---------------------------------------------------------------------------

class TestSessionIdempotency:

    def test_duplicate_returns_same_ack_without_venue_call(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        first = session.submit_order(_request("paper-mock", "idem-1"))
        second = session.submit_order(_request("paper-mock", "idem-1"))
        assert second == first
        assert session.adapter.submit_attempts == 1  # dedup at the session
        assert session.adapter.executed_orders == 1
        ack_records = [r for r in session.journal_records()
                       if r.client_order_id == "idem-1" and r.entry_type == "ORDER_ACK"]
        assert len(ack_records) == 1

    def test_same_key_different_request_is_refused(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        session.submit_order(_request("paper-mock", "idem-2"))
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "idem-2",
                                          qty=Decimal("0.03")))
        assert exc.value.reason_code == "IDEMPOTENCY_KEY_REUSE"

    def test_definitive_rejection_is_idempotent_too(self, tmp_path):
        session = _session("binance-mock", tmp_path)
        first = session.submit_order(_request("binance-mock", "idem-3",
                                              qty=Decimal("0.0001")))
        assert first.status is VenueOrderStatus.REJECTED
        second = session.submit_order(_request("binance-mock", "idem-3",
                                               qty=Decimal("0.0001")))
        assert second == first
        assert session.adapter.submit_attempts == 1

    def test_cancel_updates_the_journal(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        session.submit_order(OrderRequest(
            client_order_id="idem-4", account_id=ACCOUNT, symbol="BTCUSDT",
            side=Side.BUY, order_kind=OrderKind.LIMIT,
            quantity=Decimal("0.02"), price=Decimal("48000.00"),
        ))
        cancelled = session.cancel_order("idem-4")
        assert cancelled.status is VenueOrderStatus.CANCELLED
        latest = [r for r in session.journal_records()
                  if r.client_order_id == "idem-4"][-1]
        assert latest.entry_type == "VENUE_SYNC"
        assert latest.status is VenueOrderStatus.CANCELLED


# ---------------------------------------------------------------------------
# Bounded retry (deterministic backoff)
# ---------------------------------------------------------------------------

class TestBoundedRetry:

    def test_rate_limit_retries_with_deterministic_backoff(self, tmp_path):
        recorder = SleepRecorder()
        policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.05,
                             backoff_factor=2.0)
        session = _session("paper-mock", tmp_path, sleeper=recorder,
                           retry=policy)
        session.adapter.inject_rate_limit(1)  # first attempt throttled
        ack = session.submit_order(_request("paper-mock", "rtry-1"))
        assert ack.status is VenueOrderStatus.FILLED
        assert session.adapter.submit_attempts == 2
        assert list(session.sleep_log) == [0.05]
        assert recorder.sleeps == [0.05]

    def test_persistent_rate_limit_fails_closed_after_max_attempts(self, tmp_path):
        recorder = SleepRecorder()
        policy = RetryPolicy(max_attempts=3, base_delay_seconds=0.05,
                             backoff_factor=2.0)
        session = _session("paper-mock", tmp_path, sleeper=recorder,
                           retry=policy)
        session.adapter.inject_rate_limit(10)  # more than max attempts
        with pytest.raises(BrokerExecutionError) as exc:
            session.submit_order(_request("paper-mock", "rtry-2"))
        assert exc.value.category is BrokerErrorCategory.RATE_LIMIT
        assert session.adapter.submit_attempts == 3
        assert list(session.sleep_log) == [0.05, 0.1]  # base, base*factor
        # Nothing journaled as submitted (venue holds no order).
        assert [r for r in session.journal_records()
                if r.client_order_id == "rtry-2" and r.entry_type == "ORDER_ACK"] == []
        assert not session.degraded  # unambiguous failure: no degradation

    def test_unknown_state_is_never_retried(self, tmp_path):
        recorder = SleepRecorder()
        session = _session("paper-mock", tmp_path, sleeper=recorder)
        session.adapter.inject_ack_timeout()
        with pytest.raises(UnknownOrderStateError):
            session.submit_order(_request("paper-mock", "rtry-3"))
        assert session.adapter.submit_attempts == 1
        assert recorder.sleeps == []  # never slept, never retried


# ---------------------------------------------------------------------------
# UNKNOWN outcome → degradation → reconciliation recovery
# ---------------------------------------------------------------------------

class TestUnknownOutcomeRecovery:

    def _inject_unknown(self, session: BrokerSession, cid: str):
        session.adapter.inject_ack_timeout()
        with pytest.raises(UnknownOrderStateError):
            session.submit_order(_request(session.broker_id, cid))

    def test_unknown_degrades_and_blocks_all_submissions(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        self._inject_unknown(session, "unk-1")
        assert session.degraded is True
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "unk-2"))
        assert exc.value.reason_code == "RECONCILIATION_REQUIRED"
        assert session.adapter.submit_attempts == 1  # unk-2 never reached venue

    def test_unknown_is_journaled(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        self._inject_unknown(session, "unk-3")
        record = [r for r in session.journal_records()
                  if r.client_order_id == "unk-3"][-1]
        assert record.status is VenueOrderStatus.UNKNOWN

    def test_reconcile_resolves_unknown_from_venue_truth(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        self._inject_unknown(session, "unk-4")
        # The venue DID accept and fill the order.
        assert session.adapter.order_status("unk-4").status \
            is VenueOrderStatus.FILLED
        report = session.reconcile()
        assert report.ok is True
        assert report.resolved[0].client_order_id == "unk-4"
        assert report.resolved[0].status is VenueOrderStatus.FILLED
        assert session.degraded is False
        # Submissions resume.
        ack = session.submit_order(_request("paper-mock", "unk-5"))
        assert ack.status is VenueOrderStatus.FILLED

    def test_degraded_state_survives_restart(self, tmp_path):
        journal = tmp_path / "restart-unknown.json"
        adapter = PaperBrokerAdapter(fixed_clock)
        session = BrokerSession(
            adapter, account_id=ACCOUNT, journal_path=journal,
            risk_decision_fn=approve, kill_switch_fn=switch_off,
            sleeper=lambda s: None, clock=fixed_clock,
        )
        session.connect(BrokerCredential(ACCOUNT, SECRET))
        adapter.inject_ack_timeout()
        with pytest.raises(UnknownOrderStateError):
            session.submit_order(_request("paper-mock", "rs-1"))

        # New process, same journal: degraded at construction.
        adapter2 = PaperBrokerAdapter(fixed_clock)
        session2 = BrokerSession(
            adapter2, account_id=ACCOUNT, journal_path=journal,
            risk_decision_fn=approve, kill_switch_fn=switch_off,
            sleeper=lambda s: None, clock=fixed_clock,
        )
        session2.connect(BrokerCredential(ACCOUNT, SECRET))
        assert session2.degraded is True
        with pytest.raises(OrderRefusedError) as exc:
            session2.submit_order(_request("paper-mock", "rs-2"))
        assert exc.value.reason_code == "RECONCILIATION_REQUIRED"
        # The fresh venue never received the order → resolution: REJECTED.
        report = session2.reconcile()
        assert report.ok is True
        assert report.resolved[0].status is VenueOrderStatus.REJECTED
        assert session2.degraded is False

    def test_idempotency_survives_restart(self, tmp_path):
        journal = tmp_path / "restart-idem.json"
        adapter = PaperBrokerAdapter(fixed_clock)
        session = BrokerSession(
            adapter, account_id=ACCOUNT, journal_path=journal,
            risk_decision_fn=approve, kill_switch_fn=switch_off,
            sleeper=lambda s: None, clock=fixed_clock,
        )
        session.connect(BrokerCredential(ACCOUNT, SECRET))
        first = session.submit_order(_request("paper-mock", "rs-idem"))

        adapter2 = PaperBrokerAdapter(fixed_clock)
        session2 = BrokerSession(
            adapter2, account_id=ACCOUNT, journal_path=journal,
            risk_decision_fn=approve, kill_switch_fn=switch_off,
            sleeper=lambda s: None, clock=fixed_clock,
        )
        session2.connect(BrokerCredential(ACCOUNT, SECRET))
        replayed = session2.submit_order(_request("paper-mock", "rs-idem"))
        assert replayed == first
        assert adapter2.submit_attempts == 0  # dedup purely from the journal


# ---------------------------------------------------------------------------
# Divergence detection + explicit recovery
# ---------------------------------------------------------------------------

class TestDivergenceHandling:

    def test_fill_divergence_degrades_until_synced(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        session.submit_order(OrderRequest(
            client_order_id="dv-1", account_id=ACCOUNT, symbol="BTCUSDT",
            side=Side.BUY, order_kind=OrderKind.LIMIT,
            quantity=Decimal("0.02"), price=Decimal("48000.00"),
        ))
        # The venue fills the resting order OUT-OF-BAND.
        session.adapter.trigger_fill("dv-1", Decimal("48000.00"))
        report = session.reconcile()
        assert report.ok is False
        kinds = {m.kind.value for m in report.mismatches}
        assert "STATUS_DIVERGENCE" in kinds or "FILL_QUANTITY_DIVERGENCE" in kinds
        assert session.degraded is True  # mismatch stops new orders (§32)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "dv-2"))
        assert exc.value.reason_code == "RECONCILIATION_REQUIRED"
        # Explicit venue-truth sync, then a CLEAN reconciliation resumes.
        session.sync_order_state("dv-1")
        report2 = session.reconcile()
        assert report2.ok is True
        assert session.degraded is False

    def test_phantom_order_degrades(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        # An order submitted DIRECTLY at the venue (bypassing the session)
        # is a phantom from the journal's perspective.
        session.adapter.submit_order(_request("paper-mock", "ghost-1"))
        report = session.reconcile()
        assert report.ok is False
        assert report.mismatches[0].kind.value == "PHANTOM_ORDER_AT_VENUE"
        assert session.degraded is True


# ---------------------------------------------------------------------------
# Journal integrity
# ---------------------------------------------------------------------------

class TestJournalIntegrity:

    def test_journal_is_atomic_json_without_secret_material(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        session.submit_order(_request("paper-mock", "ji-1"))
        text = (tmp_path / "journal-paper-mock.json").read_text(encoding="utf-8")
        document = json.loads(text)  # valid JSON
        assert document["schema"].startswith("broker-session-journal/")
        assert SECRET not in text
        assert "mock-secret" not in text

    def test_tampered_journal_refuses_to_load(self, tmp_path):
        journal = tmp_path / "journal-paper-mock.json"
        session = _session("paper-mock", tmp_path)
        session.submit_order(_request("paper-mock", "tj-1"))
        document = json.loads(journal.read_text(encoding="utf-8"))
        document["records"][0]["reason_code"] = "TAMPERED"
        journal.write_text(json.dumps(document), encoding="utf-8")
        with pytest.raises(SessionJournalError):
            BrokerSession(
                PaperBrokerAdapter(fixed_clock), account_id=ACCOUNT,
                journal_path=journal, clock=fixed_clock,
            )

    def test_foreign_journal_refuses_to_load(self, tmp_path):
        journal = tmp_path / "journal-paper-mock.json"
        session = _session("paper-mock", tmp_path)
        session.submit_order(_request("paper-mock", "fj-1"))
        with pytest.raises(SessionJournalError):
            BrokerSession(
                PaperBrokerAdapter(fixed_clock), account_id="OTHER-ACCOUNT",
                journal_path=journal, clock=fixed_clock,
            )

    def test_corrupt_journal_refuses_to_load(self, tmp_path):
        journal = tmp_path / "corrupt.json"
        journal.write_text("{not json", encoding="utf-8")
        with pytest.raises(SessionJournalError):
            BrokerSession(
                PaperBrokerAdapter(fixed_clock), account_id=ACCOUNT,
                journal_path=journal, clock=fixed_clock,
            )

    def test_error_messages_never_contain_secret(self, tmp_path):
        session = _session("paper-mock", tmp_path, risk=reject)
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "sec-1"))
        assert SECRET not in str(exc.value)
        assert SECRET not in repr(session)


# ---------------------------------------------------------------------------
# Reconnect behaviour
# ---------------------------------------------------------------------------

class TestReconnectBehaviour:

    def test_connectivity_failure_then_reconnect_resumes(self, tmp_path):
        session = _session("paper-mock", tmp_path)
        session.adapter.inject_disconnect()
        with pytest.raises(OrderRefusedError) as exc:
            session.submit_order(_request("paper-mock", "rcn-1"))
        assert exc.value.reason_code == "ADAPTER_NOT_CONNECTED"
        # Sustained outage: reconnect fails while injected.
        with pytest.raises(BrokerExecutionError):
            session.reconnect()
        # Clear the outage, reconnect, resume.
        session.adapter.clear_injections()
        session.reconnect()
        ack = session.submit_order(_request("paper-mock", "rcn-2"))
        assert ack.status is VenueOrderStatus.FILLED
