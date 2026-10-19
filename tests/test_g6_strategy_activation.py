"""Stage G / G6 — strategy submission pipeline + activation gate tests.

The owner mandate is fail-closed end-to-end:
- no activation without backtest evidence;
- no activation without a COMPLETED validation window + evidence
  (short cycles allowed for the dev-run automation tests, journaled);
- no activation without an explicit YES (absent/NO/ambiguous ⇒ INACTIVE);
- every transition journaled to the decision ledger.
"""

from datetime import datetime, timedelta, timezone

import pytest

from data_engine.runtime.ledgers import LedgerFamily
from data_engine.runtime.strategy_activation import (
    ActivationDecision,
    BacktestEvidence,
    INACTIVE,
    PipelineState,
    StrategyActivationError,
    StrategyActivationGate,
    ValidationEvidence,
    VALIDATION_CYCLE_DAYS,
)

T0 = datetime(2026, 10, 20, 12, 0, 0, tzinfo=timezone.utc)


def _backtest(bars=1000, trades=12):
    return BacktestEvidence(
        backtest_id="bt-1",
        ran_at=T0,
        bars_tested=bars,
        trades=trades,
        total_return="0.12",
        max_drawdown="0.05",
        engine_version="0.3.0",
    )


def _validation(start, end, paper_trades=30):
    return ValidationEvidence(
        validation_id="val-1",
        window_start=start,
        window_end=end,
        cycles_completed=1,
        paper_trades=paper_trades,
        anomalies=0,
    )


def _submitted(gate, submission_id="strat-1"):
    return gate.submit(
        submitted_by="user-alice",
        label="BTC momentum breakout",
        structured_spec={
            "symbol": "BTCUSDT",
            "entry": "breakout above 20-bar high",
            "exit": "stop 1%, target 2%",
        },
        free_text="Buy BTC when it breaks the 20-bar high with volume; "
                  "exit at 2x ATR target or 1x ATR stop.",
        submission_id=submission_id,
    )


class TestPipelineOrder:
    def test_submit_creates_inactive_record(self):
        gate = StrategyActivationGate(LedgerFamily())
        _submitted(gate)
        status = gate.status("strat-1")
        assert status["state"] == "SUBMITTED"
        assert status["disposition"] == INACTIVE

    def test_activation_before_backtest_refused(self):
        gate = StrategyActivationGate(LedgerFamily())
        _submitted(gate)
        record = gate.activate(
            "strat-1", ActivationDecision.yes(decided_by="user-alice")
        )
        assert record.state is PipelineState.SUBMITTED
        assert record.disposition == INACTIVE

    def test_activation_before_validation_refused(self):
        gate = StrategyActivationGate(LedgerFamily())
        _submitted(gate)
        gate.record_backtest("strat-1", _backtest())
        record = gate.activate(
            "strat-1", ActivationDecision.yes(decided_by="user-alice")
        )
        assert record.state is PipelineState.BACKTESTED
        assert record.disposition == INACTIVE

    def test_strict_pipeline_order_enforced(self):
        gate = StrategyActivationGate(LedgerFamily())
        _submitted(gate)
        with pytest.raises(StrategyActivationError):
            gate.record_backtest("missing", _backtest())
        # cannot schedule validation before backtest
        with pytest.raises(StrategyActivationError):
            gate.schedule_validation("strat-1")

    def test_validation_before_window_elapses_refused(self):
        gate = StrategyActivationGate(LedgerFamily())
        _submitted(gate)
        gate.record_backtest("strat-1", _backtest())
        end = gate.schedule_validation(
            "strat-1", cycle_days=30, now=T0
        )
        assert end == T0 + timedelta(days=30)
        with pytest.raises(StrategyActivationError) as excinfo:
            gate.record_validation(
                "strat-1",
                _validation(T0, end),
                now=T0 + timedelta(days=29),  # window NOT elapsed
            )
        assert "window has NOT elapsed" in str(excinfo.value)


class TestTheGate:
    def _validated_gate(self, cycle_days=1):
        gate = StrategyActivationGate(LedgerFamily())
        _submitted(gate)
        gate.record_backtest("strat-1", _backtest())
        end = gate.schedule_validation(
            "strat-1", cycle_days=cycle_days, now=T0
        )
        gate.record_validation(
            "strat-1", _validation(T0, end), now=end + timedelta(hours=1)
        )
        return gate

    def test_explicit_yes_activates_paper_only(self):
        gate = self._validated_gate()
        record = gate.activate(
            "strat-1",
            ActivationDecision.yes(
                decided_by="user-alice", note="reviewed the evidence"
            ),
        )
        assert record.state is PipelineState.ACTIVATED
        assert record.disposition == "ACTIVATED"
        status = gate.status("strat-1")
        assert status["decision"]["affirmative"] is True

    def test_no_keeps_inactive(self):
        gate = self._validated_gate()
        record = gate.activate(
            "strat-1", ActivationDecision.no(decided_by="user-alice")
        )
        assert record.disposition == INACTIVE

    def test_no_answer_keeps_inactive(self):
        """'No answer or ambiguity = stays INACTIVE' — the mandate's
        exact words: simulate an ambiguous decision object."""
        gate = self._validated_gate()
        ambiguous = ActivationDecision(
            affirmative=False, decided_at=T0, decided_by="unknown",
            note="no explicit answer recorded",
        )
        record = gate.activate("strat-1", ambiguous)
        assert record.disposition == INACTIVE

    def test_affirmative_must_be_strict_true(self):
        gate = self._validated_gate()
        truthy_but_not_true = ActivationDecision(
            affirmative=1, decided_at=T0, decided_by="user"
        )  # type: ignore[arg-type]
        record = gate.activate("strat-1", truthy_but_not_true)
        # int(1) is not True -> the gate treats it as NOT an explicit YES
        assert record.disposition == INACTIVE

    def test_short_cycle_deviation_is_journaled_not_silent(self):
        family = LedgerFamily()
        gate = StrategyActivationGate(family)
        _submitted(gate)
        gate.record_backtest("strat-1", _backtest())
        gate.schedule_validation("strat-1", cycle_days=1, now=T0)
        events = [
            e for e in family.events("decision")
            if e.event_type == "STRATEGY_VALIDATION_SCHEDULED"
        ]
        assert events, "scheduling must be journaled"
        payload = events[0].payload
        assert payload["short_cycle_deviation"] is True
        assert "30" in payload["note"]

    def test_ratified_default_is_30_days(self):
        assert VALIDATION_CYCLE_DAYS == 30


class TestEvidenceContract:
    def test_backtest_evidence_required(self):
        gate = StrategyActivationGate(LedgerFamily())
        _submitted(gate)
        with pytest.raises(StrategyActivationError):
            gate.record_backtest("strat-1", "trust me")  # not evidence

    def test_backtest_evidence_fields_validated(self):
        from decimal import Decimal

        with pytest.raises(Exception):
            BacktestEvidence(
                backtest_id="", ran_at=T0, bars_tested=10, trades=1,
                total_return=Decimal("0.1"),
                max_drawdown=Decimal("0.01"), engine_version="0.3.0",
            )

    def test_submission_requires_structured_spec(self):
        gate = StrategyActivationGate(LedgerFamily())
        with pytest.raises(Exception):
            gate.submit(
                submitted_by="u", label="x", structured_spec={},
                free_text="",
            )

    def test_llm_parse_source_is_parsing_only(self):
        gate = StrategyActivationGate(LedgerFamily())
        submission = gate.submit(
            submitted_by="u", label="x",
            structured_spec={"symbol": "BTCUSDT"},
            free_text="parsed by assistant",
            parse_source="LLM_ASSIST_PARSE_ONLY",
        )
        assert submission.parse_source == "LLM_ASSIST_PARSE_ONLY"
        with pytest.raises(Exception):
            gate.submit(
                submitted_by="u", label="x",
                structured_spec={"s": 1}, free_text="",
                parse_source="LLM_DECIDES",
            )

    def test_ledger_family_required(self):
        with pytest.raises(StrategyActivationError):
            StrategyActivationGate("not-a-family")

    def test_every_transition_is_journaled(self):
        family = LedgerFamily()
        gate = StrategyActivationGate(family)
        _submitted(gate)
        gate.record_backtest("strat-1", _backtest())
        end = gate.schedule_validation("strat-1", cycle_days=1, now=T0)
        gate.record_validation(
            "strat-1", _validation(T0, end), now=end + timedelta(hours=1)
        )
        gate.activate(
            "strat-1", ActivationDecision.yes(decided_by="user-alice")
        )
        event_types = [
            e.event_type for e in family.events("decision")
        ]
        assert "STRATEGY_SUBMITTED" in event_types
        assert "STRATEGY_BACKTESTED" in event_types
        assert "STRATEGY_VALIDATION_SCHEDULED" in event_types
        assert "STRATEGY_VALIDATED" in event_types
        assert "STRATEGY_ACTIVATED" in event_types
        # the activation event carries the paper-only marker
        activated = [
            e for e in family.events("decision")
            if e.event_type == "STRATEGY_ACTIVATED"
        ][0]
        assert activated.payload["live_trading"] == "NOT_AUTHORIZED"
        assert activated.payload["mode"] == "PAPER_EVALUATION_ONLY"
