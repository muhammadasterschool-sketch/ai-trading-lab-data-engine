"""Stage G / G1 — confirmed-trade spacing (Part 9B mandate).

The owner-ratified rule: minimum 1 second between a CONFIRMED TRADE
and the NEXT SUBMISSION, in ADDITION to submission-to-submission
spacing. This file pins the G1 wiring on the durable submission
ledger:

- differential proof: a fill confirmation at T+2.0 with the next
  reserve at T+2.5 is REFUSED (0.5s < 1.0s from the CONFIRMED
  TRADE) even though submission-to-submission spacing alone
  (2.5s >= 1.0s) would have allowed it — the confirmed trade
  RE-ARMS the spacing clock;
- the confirmation is DURABLE (restart-conservative);
- fail-closed refusals: unknown reservation, abandoned reservation;
- the refusal message names the confirmed-trade source.

Reuse the deterministic builders from the existing ledger suite.
"""

import json
from datetime import timedelta
from pathlib import Path

import pytest

from data_engine.runtime.submission_ledger import (
    CapacityRefused,
    ReservationState,
    SubmissionLedger,
    SubmissionLedgerError,
    SubmissionPolicy,
)
from test_submission_ledger import T0, _clock, _ledger, _policy

SYMBOL = "TEST/USD"


class TestConfirmedTradeSpacing:
    def test_fill_confirmation_re_arms_spacing_clock(self, tmp_path):
        """THE G1 differential: submission-to-submission spacing would
        allow the next reserve (2.5s apart), but the CONFIRMED TRADE
        at T+2.0 re-arms the clock — 0.5s later is REFUSED."""
        path = tmp_path / "led.json"
        clock = _clock(start=T0, step_seconds=0.5)
        led = _ledger(path, clock=clock)
        # reserve at T0+0.5 (call 1), mark submitted
        r1 = led.reserve("ord-1")                       # t = T0+0.5
        led.mark_submitted(r1.reservation_id)           # t = T0+1.0
        # fill confirmed at T0+2.0 (clock call 3)
        led.record_fill_confirmation(r1.reservation_id)  # t = T0+2.0
        # next reserve attempt at T0+2.5: only 0.5s after the
        # confirmed trade -> REFUSED (G1)
        with pytest.raises(CapacityRefused) as excinfo:
            led.reserve("ord-2")                        # t = T0+2.5
        assert "confirmed trade" in str(excinfo.value)
        assert "0.500" in str(excinfo.value)

    def test_submission_spacing_still_enforced_without_fills(self, tmp_path):
        """Positive control: the B2 submission-to-submission spacing
        still applies when no fill has occurred (unchanged B2
        behavior — G1 is additive, never a weakening)."""
        path = tmp_path / "led.json"
        clock = _clock(start=T0, step_seconds=0.4)
        led = _ledger(path, clock=clock)
        led.reserve("ord-1")                            # t = T0+0.4
        with pytest.raises(CapacityRefused) as excinfo:
            led.reserve("ord-2")                        # t = T0+0.8
        assert "durable submission" in str(excinfo.value)

    def test_reserve_allowed_after_min_spacing_from_fill(self, tmp_path):
        """Exactly min-spacing after the confirmed trade is allowed."""
        path = tmp_path / "led.json"
        clock = _clock(start=T0, step_seconds=1.0)
        led = _ledger(path, clock=clock)
        r1 = led.reserve("ord-1")                       # t = T0+1.0
        led.mark_submitted(r1.reservation_id)           # t = T0+2.0
        led.record_fill_confirmation(r1.reservation_id)  # t = T0+3.0
        r2 = led.reserve("ord-2")                       # t = T0+4.0
        assert r2.state is ReservationState.RESERVED

    def test_fill_confirmation_is_durable_across_restart(self, tmp_path):
        """The confirmation (and its spacing effect) survives a
        restart — conservative restart semantics preserved."""
        path = tmp_path / "led.json"
        clock = _clock(start=T0, step_seconds=1.0)
        led = _ledger(path, clock=clock)
        r1 = led.reserve("ord-1")                       # t = T0+1.0
        led.record_fill_confirmation(r1.reservation_id)  # t = T0+2.0
        # NEW ledger instance over the same durable file; its clock
        # FIRST call lands 0.5s past the confirmed trade (T0+2.5)
        led2 = SubmissionLedger(
            path, policy=_policy(),
            wall_clock=_clock(start=T0 + timedelta(seconds=1.5)),
        )
        with pytest.raises(CapacityRefused) as excinfo:
            led2.reserve("ord-2")
        assert "confirmed trade" in str(excinfo.value)
        # and the durable record carries the confirmation
        doc = json.loads(path.read_text())
        rec = doc["records"][0]
        assert rec["fill_confirmed_at"] is not None
        assert any(
            "confirmed trade" in t.get("note", "")
            for t in rec.get("transitions", [])
        )

    def test_unknown_reservation_fill_refused(self, tmp_path):
        led = _ledger(tmp_path / "led.json")
        with pytest.raises(SubmissionLedgerError) as excinfo:
            led.record_fill_confirmation("res-does-not-exist")
        assert "not found" in str(excinfo.value)
        # and nothing was fabricated into the durable file
        doc = json.loads((tmp_path / "led.json").read_text())
        assert doc["records"] == []

    def test_abandoned_reservation_fill_refused(self, tmp_path):
        path = tmp_path / "led.json"
        clock = _clock(start=T0, step_seconds=1.0)
        led = _ledger(path, clock=clock)
        r1 = led.reserve("ord-1")
        led.abandon(r1.reservation_id, reason="pre-venue refusal")
        with pytest.raises(SubmissionLedgerError) as excinfo:
            led.record_fill_confirmation(r1.reservation_id)
        assert "ABANDONED" in str(excinfo.value)

    def test_fill_on_finalized_reservation_is_legal(self, tmp_path):
        """Fills may arrive after the attempt finalized with an ack —
        the confirmation must still be recordable (and re-arm)."""
        path = tmp_path / "led.json"
        clock = _clock(start=T0, step_seconds=1.0)
        led = _ledger(path, clock=clock)
        r1 = led.reserve("ord-1")                        # t = T0+1.0
        led.mark_submitted(r1.reservation_id)            # t = T0+2.0
        led.finalize(r1.reservation_id, "ACKNOWLEDGED")  # t = T0+3.0
        led.record_fill_confirmation(r1.reservation_id)  # t = T0+4.0
        # the fill re-arms spacing EVEN on a finalized reservation:
        # a fresh ledger whose first now() lands T0+4.5 (0.5s after
        # the confirmed trade) is REFUSED
        led_tight = SubmissionLedger(
            path, policy=_policy(),
            wall_clock=_clock(start=T0 + timedelta(seconds=3.5)),
        )
        with pytest.raises(CapacityRefused) as excinfo:
            led_tight.reserve("ord-3")
        assert "confirmed trade" in str(excinfo.value)

    def test_quantity_is_recorded_in_transition_note(self, tmp_path):
        path = tmp_path / "led.json"
        clock = _clock(start=T0, step_seconds=1.0)
        led = _ledger(path, clock=clock)
        r1 = led.reserve("ord-1")
        led.record_fill_confirmation(r1.reservation_id, quantity="0.5")
        doc = json.loads(path.read_text())
        note = doc["records"][0]["transitions"][-1]["note"]
        assert "quantity=0.5" in note

    def test_policy_min_spacing_default_is_owner_ratified_1s(self):
        """Part 3 ratification: min 1 second (paper mode)."""
        policy = SubmissionPolicy()
        assert policy.min_spacing_seconds == 1.0
