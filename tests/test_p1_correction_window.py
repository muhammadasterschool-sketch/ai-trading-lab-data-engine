"""P1 correction-window regression suite (authorized fix window).

Every test in this file proves ONE authorized P1 correction with
objective BEFORE/AFTER evidence semantics: the test asserts the
CORRECT behavior that the pre-paper forensic
(PRE_PAPER_BUG_FORENSIC_AND_CLOSURE_REPORT.md §5) specified, and each
pinned defective assertion it replaces is noted in the test
docstring. Targeted at: BUG-001..009, ARCH-F1/F3/F4/F6,
RT-F7/F8/F13 — and nothing else.

Deliberately NOT covered here (outside the P1 window): RT-F1..F6,
RT-F9..F12, RT-F14/F15, MC-1..12, ARCH-F2/F5/F7..F12 — their
dispositions are unchanged by this correction window.
"""

import math
import random
import subprocess
import sys
from datetime import datetime, UTC
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from data_engine.paper import (
    AnalyticsEngine,
    AuditLogger,
    ExecutionRealism,
    ExecutionSimulator,
    Fill,
    GatewayRecord,
    OrderSide,
    OrderStatus,
    OrderType,
    PaperOrder,
    PaperPosition,
    PaperOrderGateway,
    ReconciliationEngine,
    ReconciliationError,
    SimulationError,
)
from data_engine.risk import (
    Allocation,
    ExposureReport,
    KillSwitchActiveError,
    RiskEngine,
    RiskLimits,
    RiskViolationError,
)

D = Decimal
REPO_ROOT = Path(__file__).resolve().parents[1]


def utc(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=UTC)


def make_bars():
    return [
        {"timestamp": utc(2020, 1, 6, 10), "open": D("100"), "high": D("101"),
         "low": D("99"), "close": D("100"), "volume": D("10000")},
        {"timestamp": utc(2020, 1, 6, 11), "open": D("102"), "high": D("103"),
         "low": D("101"), "close": D("102"), "volume": D("10000")},
        {"timestamp": utc(2020, 1, 6, 12), "open": D("104"), "high": D("105"),
         "low": D("103"), "close": D("104"), "volume": D("10000")},
    ]


REALISM = ExecutionRealism(
    half_spread=D("0.05"),
    commission_per_unit=D("0.01"),
    impact_rate=D("0.001"),
    participation_cap=D("0.1"),
    fill_lag_bars=1,
)

LIMITS = RiskLimits(
    max_position_units=D("100"),
    max_leverage=D("2"),
    max_single_asset_weight=D("0.3"),
    max_sector_weight=D("0.6"),
    max_portfolio_heat=D("1.5"),
)


def make_order(coid="o-1", side=OrderSide.BUY, qty="100", submitted=None,
               order_type=OrderType.MARKET, limit=None):
    return PaperOrder(
        client_order_id=coid, symbol="AAA", side=side,
        order_type=order_type, quantity=D(qty),
        limit_price=D(limit) if limit else None,
        submitted_at=submitted or utc(2020, 1, 6, 10),
    )


# ======================================================================
# BUG-001 — limit-order price protection
# ======================================================================

class TestBug001LimitPriceProtection:

    def test_buy_limit_passive_fill_at_limit_zero_costs(self):
        """REPRO-A AFTER: BUY limit 101.5 (bar-1 open 102, all-in ask
        102.05102) fills AT 101.5 — never above the limit — with the
        improvement in the price, not as negative costs."""
        simulator = ExecutionSimulator(REALISM)
        fill = simulator.simulate(
            make_order(order_type=OrderType.LIMIT, limit="101.5"), make_bars()
        )
        assert fill is not None
        assert fill.price <= D("101.5")
        assert fill.price == D("101.5")
        assert fill.spread_cost == D("0")
        assert fill.slippage_cost == D("0")
        assert fill.commission == D("0.01") * D("100")

    def test_buy_limit_marketable_fill_improves_price(self):
        """A BUY limit above the all-in ask fills at the market all-in
        price (price improvement) with the full adverse stack charged —
        still never above the limit."""
        simulator = ExecutionSimulator(REALISM)
        fill = simulator.simulate(
            make_order(order_type=OrderType.LIMIT, limit="103"), make_bars()
        )
        assert fill is not None
        impact = D("0.001") * (D(100) / D(10000)) * D("102")
        assert fill.price == D("102") + D("0.05") + impact  # all-in ask
        assert fill.price < D("103")  # improvement vs the limit
        assert fill.spread_cost == D("0.05") * D("100")
        assert fill.slippage_cost == impact * D("100")

    def test_sell_limit_never_fills_below_limit(self):
        """REPRO-A2 AFTER: SELL limit fills at >= the limit."""
        simulator = ExecutionSimulator(REALISM)
        fill = simulator.simulate(
            make_order(side=OrderSide.SELL, order_type=OrderType.LIMIT,
                       limit="102.5"),
            make_bars(),
        )
        assert fill is not None
        assert fill.price >= D("102.5")
        assert fill.price == D("102.5")  # passive at the limit
        assert fill.spread_cost == D("0")
        assert fill.slippage_cost == D("0")

    def test_sell_limit_marketable_fill(self):
        simulator = ExecutionSimulator(REALISM)
        fill = simulator.simulate(
            make_order(side=OrderSide.SELL, order_type=OrderType.LIMIT,
                       limit="101.5"),
            make_bars(),
        )
        assert fill is not None
        impact = D("0.001") * (D(100) / D(10000)) * D("102")
        all_in_bid = D("102") - D("0.05") - impact
        assert fill.price == max(D("101.5"), all_in_bid)
        assert fill.price >= D("101.5")
        assert fill.price == all_in_bid  # marketable: all-in bid > limit

    def test_limit_cost_accounting_identity(self):
        """§5.1 accounting identity: for BUY,
        price*qty == base*qty + (spread_cost + slippage_cost) with
        base = min(limit, open); mirrored for SELL."""
        simulator = ExecutionSimulator(REALISM)
        bars = make_bars()
        for limit in ("101.5", "102.1", "103"):
            fill = simulator.simulate(
                make_order(order_type=OrderType.LIMIT, limit=limit), bars
            )
            assert fill is not None
            base = min(D(limit), D("102"))
            assert fill.price * fill.quantity == (
                base * fill.quantity + fill.spread_cost + fill.slippage_cost
            )
        for limit in ("102.5", "101.9"):
            fill = simulator.simulate(
                make_order(side=OrderSide.SELL, order_type=OrderType.LIMIT,
                           limit=limit),
                bars,
            )
            assert fill is not None
            base = max(D(limit), D("102"))
            assert fill.price * fill.quantity == (
                base * fill.quantity - fill.spread_cost - fill.slippage_cost
            )

    def test_limit_invariant_property_randomized(self):
        """§5.1 property test: randomized realism + random bars — BUY
        limit fills NEVER above the limit; SELL NEVER below it."""
        rng = random.Random(20261008)
        for _ in range(300):
            half_spread = D(str(round(rng.uniform(0, 0.5), 4)))
            impact_rate = D(str(round(rng.uniform(0, 0.01), 6)))
            realism = ExecutionRealism(
                half_spread=half_spread,
                commission_per_unit=D("0.01"),
                impact_rate=impact_rate,
                participation_cap=D("0.5"),
                fill_lag_bars=1,
            )
            base_price = rng.uniform(50, 200)
            o = round(base_price + rng.uniform(-1, 1), 3)
            c = round(base_price + rng.uniform(-1, 1), 3)
            hi = round(max(o, c) + rng.uniform(0, 1), 3)
            lo = round(min(o, c) - rng.uniform(0, 1), 3)
            volume = round(rng.uniform(5000, 50000), 1)
            bars = [
                {"timestamp": utc(2020, 1, 6, 10),
                 "open": D(str(base_price)), "high": D(str(hi)),
                 "low": D(str(lo)), "close": D(str(c)),
                 "volume": D(str(volume))},
                {"timestamp": utc(2020, 1, 6, 11),
                 "open": D(str(o)), "high": D(str(hi)),
                 "low": D(str(lo)), "close": D(str(c)),
                 "volume": D(str(volume))},
            ]
            qty = D(str(round(rng.uniform(1, 100), 2)))
            if qty * 1 > D("0.5") * D(str(volume)):
                continue  # participation cap — realism rejection, not fill
            buy_limit = D(str(round(rng.uniform(lo, hi), 3)))
            fill = ExecutionSimulator(realism).simulate(
                PaperOrder(
                    client_order_id="p1", symbol="AAA", side=OrderSide.BUY,
                    order_type=OrderType.LIMIT, quantity=qty,
                    limit_price=buy_limit,
                    submitted_at=utc(2020, 1, 6, 10),
                ),
                bars,
            )
            if fill is not None:
                assert fill.price <= buy_limit, (
                    f"BUG-001 invariant violated: BUY fill {fill.price} > "
                    f"limit {buy_limit}"
                )
            sell_limit = D(str(round(rng.uniform(lo, hi), 3)))
            fill = ExecutionSimulator(realism).simulate(
                PaperOrder(
                    client_order_id="p2", symbol="AAA", side=OrderSide.SELL,
                    order_type=OrderType.LIMIT, quantity=qty,
                    limit_price=sell_limit,
                    submitted_at=utc(2020, 1, 6, 10),
                ),
                bars,
            )
            if fill is not None:
                assert fill.price >= sell_limit, (
                    f"BUG-001 invariant violated: SELL fill {fill.price} < "
                    f"limit {sell_limit}"
                )

    def test_market_orders_unchanged(self):
        """The MARKET branch retains the exact pre-correction price
        semantics (regression guard for the refactor)."""
        simulator = ExecutionSimulator(REALISM)
        fill = simulator.simulate(make_order(), make_bars())
        impact = D("0.001") * (D(100) / D(10000)) * D("102")
        assert fill.price == D("102") + D("0.05") + impact
        assert fill.spread_cost == D("0.05") * D("100")
        assert fill.slippage_cost == impact * D("100")


# ======================================================================
# BUG-002 — position-flip basis
# ======================================================================

def _fill(fid, side, qty, price, at):
    return Fill(
        fill_id=fid, client_order_id=f"c-{fid}", symbol="AAA", side=side,
        quantity=D(qty), price=D(price), commission=D("0"),
        slippage_cost=D("0"), spread_cost=D("0"), filled_at=at,
    )


class TestBug002FlipBasis:

    def test_long_flip_to_short_opens_at_flip_price(self):
        """REPRO-B AFTER: +100@100 -> sell 140@110 -> short -40 with
        basis 110 (the flip fill's all-in price), NOT 100."""
        position = PaperPosition(symbol="AAA").apply_fill(
            _fill("f1", OrderSide.BUY, "100", "100", utc(2020, 1, 1))
        )
        flipped = position.apply_fill(
            _fill("f2", OrderSide.SELL, "140", "110", utc(2020, 1, 2))
        )
        assert flipped.quantity == D("-40")
        assert flipped.average_cost == D("110")
        assert flipped.realized_pnl == (D("110") - D("100")) * D("100")

    def test_short_flip_to_long_opens_at_flip_price(self):
        position = PaperPosition(symbol="AAA").apply_fill(
            _fill("f1", OrderSide.SELL, "100", "110", utc(2020, 1, 1))
        )
        flipped = position.apply_fill(
            _fill("f2", OrderSide.BUY, "150", "100", utc(2020, 1, 2))
        )
        assert flipped.quantity == D("50")
        assert flipped.average_cost == D("100")

    def test_flip_realized_pnl_economics(self):
        """REPRO-B2 AFTER: +100@100 -> sell 140@110 -> close the -40
        short at 120 realizes (110-100)*100 + (110-120)*40 = +600 —
        the pre-fix defect doubled the loss to +200 via the stale
        basis."""
        position = PaperPosition(symbol="AAA").apply_fill(
            _fill("f1", OrderSide.BUY, "100", "100", utc(2020, 1, 1))
        )
        position = position.apply_fill(
            _fill("f2", OrderSide.SELL, "140", "110", utc(2020, 1, 2))
        )
        position = position.apply_fill(
            _fill("f3", OrderSide.BUY, "40", "120", utc(2020, 1, 3))
        )
        assert position.quantity == D("0")
        assert position.realized_pnl == D("600")

    def test_partial_reduction_preserves_basis(self):
        position = PaperPosition(symbol="AAA").apply_fill(
            _fill("f1", OrderSide.BUY, "100", "100", utc(2020, 1, 1))
        )
        reduced = position.apply_fill(
            _fill("f2", OrderSide.SELL, "40", "105", utc(2020, 1, 2))
        )
        assert reduced.quantity == D("60")
        assert reduced.average_cost == D("100")  # basis preserved
        assert reduced.realized_pnl == D("5") * D("40")

    def test_full_close_resets_basis(self):
        position = PaperPosition(symbol="AAA").apply_fill(
            _fill("f1", OrderSide.BUY, "100", "100", utc(2020, 1, 1))
        )
        closed = position.apply_fill(
            _fill("f2", OrderSide.SELL, "100", "110", utc(2020, 1, 2))
        )
        assert closed.quantity == D("0")
        assert closed.average_cost == D("0")


# ======================================================================
# BUG-003 — signed risk netting
# ======================================================================

class TestBug003SignedNetting:

    def test_full_close_passes(self):
        """§5 case 1: current +100 (max 100), sell 100 -> projected 0.
        The pre-fix additive engine projected 200, raised, and tripped
        the kill switch on a risk-REDUCING order."""
        engine = RiskEngine(LIMITS, trip_on_breach=True)
        engine.check_order("X", D("-100"), current_units=D("100"))
        assert not engine.kill_switch_active

    def test_reduction_passes(self):
        """§5 case 2: +100 -> sell 40 -> +60."""
        engine = RiskEngine(LIMITS, trip_on_breach=True)
        engine.check_order("X", D("-40"), current_units=D("100"))
        assert not engine.kill_switch_active

    def test_flip_passes_within_residual(self):
        """§5 case 3 (order-size-rule-conformant numbers): current +40,
        sell 60 -> residual -20 — a legitimate flip passes. (The §5
        literal "+100/-140" example additionally requires max >= 140
        under the order-itself-oversized rule; with max=100 such an
        order is rightly rejected by order size.)"""
        engine = RiskEngine(LIMITS, trip_on_breach=True)
        engine.check_order("X", D("-60"), current_units=D("40"))
        assert not engine.kill_switch_active

    def test_increase_rejected(self):
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        with pytest.raises(RiskViolationError, match="exceeds max"):
            engine.check_order("X", D("50"), current_units=D("60"))

    def test_flip_rejected_on_oversized_residual(self):
        """Oversized flips/orders are rejected: a −250 order on +100
        breaches the projected rule (|−150| > 100), and an
        already-over-limit position reduced but still over the cap
        breaches it too. The order-size rule fires when only the
        order's own magnitude is oversized."""
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        with pytest.raises(RiskViolationError, match="exceeds max"):
            engine.check_order("X", D("-250"), current_units=D("100"))
        with pytest.raises(RiskViolationError, match="exceeds max"):
            engine.check_order("X", D("-25"), current_units=D("150"))
        with pytest.raises(RiskViolationError, match="order itself"):
            engine.check_order("X", D("150"), current_units=D("-100"))

    def test_order_itself_oversized_rejected(self):
        """An order whose own magnitude exceeds the cap is rejected even
        when the resulting residual is within limits."""
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        with pytest.raises(RiskViolationError, match="order itself"):
            engine.check_order("X", D("150"), current_units=D("-100"))

    def test_reductions_and_closes_never_trip_kill_switch(self):
        engine = RiskEngine(LIMITS, trip_on_breach=True)
        engine.check_order("X", D("-100"), current_units=D("100"))
        engine.check_order("X", D("-60"), current_units=D("100"))
        engine.check_order("X", D("-60"), current_units=D("40"))
        engine.check_order("X", D("100"), current_units=D("-100"))  # short close
        assert not engine.kill_switch_active
        assert len(engine.violation_log) == 0

    def test_breach_still_trips_and_records(self):
        """The hard-limit posture is unchanged for true breaches."""
        engine = RiskEngine(LIMITS, trip_on_breach=True)
        with pytest.raises(RiskViolationError):
            engine.check_order("X", D("150"))
        assert engine.kill_switch_active
        assert engine.violation_log[0].rule == "max_position_units"
        with pytest.raises(KillSwitchActiveError):
            engine.check_order("X", D("1"))

    def test_signed_netting_documented_semantics(self):
        """Positive units BUY onto positive position == same-sign
        accumulation (compatible with the legacy additive results)."""
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        engine.check_order("X", D("40"), current_units=D("60"))
        with pytest.raises(RiskViolationError):
            engine.check_order("X", D("41"), current_units=D("60"))


# ======================================================================
# ARCH-F1 — kill-switch reset authentication
# ======================================================================

class TestArchF1KillSwitchResetAuthentication:

    def test_bare_reset_refused(self):
        """The pre-fix bare ``reset_kill_switch()`` call now fails
        closed — an unidentified caller can never clear a tripped
        switch."""
        engine = RiskEngine(LIMITS, trip_on_breach=True)
        engine.trip_kill_switch()
        with pytest.raises(RiskViolationError, match="identified principal"):
            engine.reset_kill_switch()
        assert engine.kill_switch_active

    def test_machine_principal_refused(self):
        engine = RiskEngine(LIMITS, trip_on_breach=True)
        engine.trip_kill_switch()
        with pytest.raises(RiskViolationError, match="HUMAN principal"):
            engine.reset_kill_switch(principal="agent-1",
                                     principal_kind="machine")
        assert engine.kill_switch_active

    def test_ai_principal_refused(self):
        engine = RiskEngine(LIMITS, trip_on_breach=True)
        engine.trip_kill_switch()
        with pytest.raises(RiskViolationError, match="HUMAN principal"):
            engine.reset_kill_switch(principal="model-x",
                                     principal_kind="ai")
        assert engine.kill_switch_active

    def test_human_principal_resets(self):
        engine = RiskEngine(LIMITS, trip_on_breach=True)
        engine.trip_kill_switch()
        engine.reset_kill_switch(principal="risk-operator",
                                 principal_kind="human")
        assert not engine.kill_switch_active

    def test_empty_principal_refused(self):
        engine = RiskEngine(LIMITS)
        engine.trip_kill_switch()
        with pytest.raises(RiskViolationError):
            engine.reset_kill_switch(principal="   ",
                                     principal_kind="human")
        assert engine.kill_switch_active

    def test_trip_remains_unprivileged(self):
        """Tripping (the fail-safe direction) stays reachable by any
        caller — only clearing is privileged."""
        engine = RiskEngine(LIMITS, trip_on_breach=False)
        engine.trip_kill_switch()
        assert engine.kill_switch_active

    def test_trip_on_breach_optout_is_explicit(self):
        """The constructor opt-out is no longer silent: it warns and is
        introspectable (ARCH-F1 second dimension)."""
        import warnings as _warnings
        with pytest.warns(UserWarning, match="trip_on_breach=False"):
            engine = RiskEngine(LIMITS, trip_on_breach=False)
        assert engine.trip_on_breach is False
        with _warnings.catch_warnings():
            _warnings.simplefilter("error")  # any warning -> error
            engine = RiskEngine(LIMITS, trip_on_breach=True)
        assert engine.trip_on_breach is True

    def test_default_posture_auto_trips(self):
        engine = RiskEngine(LIMITS)  # default: trip_on_breach=True, no warning
        assert engine.trip_on_breach is True
        with pytest.raises(RiskViolationError):
            engine.check_order("X", D("500"))
        assert engine.kill_switch_active


# ======================================================================
# BUG-004 — status-aware reconciliation
# ======================================================================

class TestBug004StatusAwareReconciliation:

    def _filled_record(self, order, fill):
        return GatewayRecord(order=order, status=OrderStatus.FILLED, fill=fill)

    def test_missing_fill_of_filled_order_raises(self):
        """REPRO-D AFTER: FILLED order + missing fill record no longer
        reconciles clean."""
        order = make_order()
        record = GatewayRecord(order=order, status=OrderStatus.FILLED)
        engine = ReconciliationEngine()
        with pytest.raises(ReconciliationError,
                           match="filled orders without fills"):
            engine.reconcile([record], [], {})

    def test_fill_on_cancelled_order_raises(self):
        order = make_order(order_type=OrderType.LIMIT, limit="101.5")
        fill = ExecutionSimulator(REALISM).simulate(order, make_bars())
        cancelled = GatewayRecord(order=order, status=OrderStatus.CANCELLED)
        with pytest.raises(ReconciliationError,
                           match="fills attached to non-filled"):
            ReconciliationEngine().reconcile([cancelled], [fill], {})

    def test_fill_on_submitted_order_raises(self):
        order = make_order(order_type=OrderType.LIMIT, limit="90")
        synth = Fill(
            fill_id="g", client_order_id=order.client_order_id,
            symbol="AAA", side=OrderSide.BUY, quantity=D("10"),
            price=D("100"), commission=D("0"), slippage_cost=D("0"),
            spread_cost=D("0"), filled_at=utc(2020, 1, 6, 11),
        )
        submitted = GatewayRecord(order=order, status=OrderStatus.SUBMITTED)
        with pytest.raises(ReconciliationError,
                           match="fills attached to non-filled"):
            ReconciliationEngine().reconcile([submitted], [synth], {})

    def test_status_aware_clean_pass(self):
        order = make_order()
        fill = ExecutionSimulator(REALISM).simulate(order, make_bars())
        record = GatewayRecord(order=order, status=OrderStatus.FILLED,
                               fill=fill)
        positions = {"AAA": PaperPosition(symbol="AAA").apply_fill(fill)}
        result = ReconciliationEngine().reconcile([record], [fill], positions)
        assert result["status"] == "reconciled"

    def test_legacy_order_sequence_still_reconciles(self):
        """Plain PaperOrder input keeps working (status-blind check 2
        is honestly skipped, not falsely claimed)."""
        order = make_order()
        fill = ExecutionSimulator(REALISM).simulate(order, make_bars())
        positions = {"AAA": PaperPosition(symbol="AAA").apply_fill(fill)}
        result = ReconciliationEngine().reconcile([order], [fill], positions)
        assert result["status"] == "reconciled"

    def test_orphan_fill_still_raises(self):
        order = make_order()
        ghost = _fill("g", OrderSide.BUY, "1", "1", utc(2020, 1, 1))
        with pytest.raises(ReconciliationError, match="fills without orders"):
            ReconciliationEngine().reconcile([order], [ghost], {})


# ======================================================================
# BUG-005 — audit-trail deep immutability
# ======================================================================

class TestBug005AuditImmutability:

    def test_caller_payload_mutation_does_not_propagate(self):
        """REPRO-E AFTER: mutating the caller's payload dict after
        log() leaves the historical entry unchanged and verify()
        valid."""
        audit = AuditLogger()
        payload = {"client_order_id": "o-1", "nested": {"price": "102"}}
        audit.log("order_submitted", payload)
        payload["client_order_id"] = "TAMPERED"
        payload["nested"]["price"] = "0"
        entry = audit.entries[0]
        assert entry["payload"]["client_order_id"] == "o-1"
        assert entry["payload"]["nested"]["price"] == "102"
        assert audit.verify()

    def test_entries_are_copies_not_references(self):
        """REPRO-E (second half) AFTER: mutating the returned entries
        cannot corrupt the internal chain."""
        audit = AuditLogger()
        audit.log("order_submitted", {"client_order_id": "o-1"})
        snapshot = audit.entries
        snapshot[0]["event"] = "TAMPERED"
        snapshot[0]["payload"]["client_order_id"] = "TAMPERED"
        assert audit.entries[0]["event"] == "order_submitted"
        assert audit.entries[0]["payload"]["client_order_id"] == "o-1"
        assert audit.verify()

    def test_entry_schema_observability_fields(self):
        """§5.5: entries carry timestamp, component, event_id."""
        audit = AuditLogger()
        audit.log("order_filled", {"price": "102"}, component="paper.sim")
        entry = audit.entries[0]
        assert entry["event_id"] == "evt-000000-order_filled"
        assert entry["component"] == "paper.sim"
        assert entry["timestamp"]  # wall-clock by design (FS-21 convention)
        assert audit.verify()

    def test_internal_tamper_detected(self):
        """In-place tampering of the internal store still breaks
        verification (tamper-EVIDENT chain, unchanged semantics)."""
        audit = AuditLogger()
        audit.log("order_submitted", {"client_order_id": "o-1"})
        audit.log("order_filled", {"client_order_id": "o-1"})
        audit._entries[0]["event"] = "TAMPERED"
        assert not audit.verify()

    def test_unreforced_chain_threat_model_documented(self):
        """REPRO-E2 ACCEPTED THREAT MODEL (registered human decision,
        pre-paper forensic §5.5): an attacker with full write access
        can rewrite history AND recompute a consistent chain — the
        unkeyed chain is tamper-evident, not tamper-PROOF. This test
        pins the current honest boundary until the keyed-MAC custody
        decision is made."""
        audit = AuditLogger()
        audit.log("order_submitted", {"client_order_id": "o-1"})
        from data_engine.pit.hashing import deterministic_hash
        from data_engine.paper.models import PHASE_11_CONTRACT_VERSION
        # Rewrite FILLED -> CANCELLED and re-forge the chain:
        entry = audit._entries[0]
        entry["event"] = "order_cancelled"
        entry["chain_hash"] = deterministic_hash(
            {
                "contract_version": PHASE_11_CONTRACT_VERSION,
                "event": entry["event"],
                "payload": entry["payload"],
                "component": entry["component"],
                "event_id": entry["event_id"],
                "timestamp": entry["timestamp"],
                "prev_chain_hash": entry["prev_chain_hash"],
                "index": entry["index"],
            }
        )
        assert audit.verify() is True  # accepted threat model, documented


# ======================================================================
# BUG-006 — truthful CLI status
# ======================================================================

class TestBug006CliStatusTruthfulness:

    def _run_cli(self, argv, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["data-engine"] + argv)
        from data_engine.cli import main
        main()
        return capsys.readouterr().out

    def test_status_reports_seven_truthful_dimensions(self):
        """§5.6: seven distinct dimensions with truthful values; the
        single blanket 'OPERATIONAL' claim is gone."""
        import pytest as _pytest
        captured = {}
        # run through monkeypatch-free invocation for simplicity:
        from data_engine.cli import STATUS_DIMENSIONS, main
        assert set(STATUS_DIMENSIONS) == {
            "LIBRARY_HEALTH", "RUNTIME_HEALTH", "PAPER_READINESS",
            "LIVE_AUTHORIZATION", "DATA_READINESS", "MODEL_READINESS",
            "RECONCILIATION_HEALTH",
        }
        assert STATUS_DIMENSIONS["LIBRARY_HEALTH"] == "OK"
        assert STATUS_DIMENSIONS["RUNTIME_HEALTH"] == "ABSENT"
        assert STATUS_DIMENSIONS["PAPER_READINESS"] == "BLOCKED"
        assert STATUS_DIMENSIONS["LIVE_AUTHORIZATION"] == "NOT_AUTHORIZED"
        assert STATUS_DIMENSIONS["DATA_READINESS"] == "SYNTHETIC_ONLY/REAL_BLOCKED"
        assert STATUS_DIMENSIONS["MODEL_READINESS"] == "0_APPROVED"
        assert STATUS_DIMENSIONS["RECONCILIATION_HEALTH"] == "NOT_WIRED"

    def test_status_output_prints_all_dimensions(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv", ["data-engine", "status"])
        from data_engine.cli import main
        main()
        out = capsys.readouterr().out
        for key in ("LIBRARY_HEALTH", "RUNTIME_HEALTH", "PAPER_READINESS",
                    "LIVE_AUTHORIZATION", "DATA_READINESS",
                    "MODEL_READINESS", "RECONCILIATION_HEALTH"):
            assert key in out
        assert "OPERATIONAL" not in out


# ======================================================================
# BUG-007 — bar-series ordering validation
# ======================================================================

class TestBug007BarOrdering:

    def test_unsorted_bars_raise(self):
        simulator = ExecutionSimulator(REALISM)
        bars = make_bars()
        unsorted_bars = [bars[1], bars[0], bars[2]]
        with pytest.raises(SimulationError, match="strictly increasing"):
            simulator.simulate(make_order(), unsorted_bars)

    def test_duplicate_timestamps_raise(self):
        simulator = ExecutionSimulator(REALISM)
        bars = make_bars()
        dup = [bars[0], dict(bars[0]), bars[1]]
        with pytest.raises(SimulationError, match="strictly increasing"):
            simulator.simulate(make_order(), dup)

    def test_valid_series_unchanged(self):
        simulator = ExecutionSimulator(REALISM)
        fill = simulator.simulate(make_order(), make_bars())
        assert fill is not None and fill.filled_at == utc(2020, 1, 6, 11)


# ======================================================================
# BUG-008 — deep immutability of frozen record models
# ======================================================================

class TestBug008DeepImmutability:

    def _assert_frozen_dict(self, container):
        with pytest.raises(TypeError):
            container["__probe__"] = 1
        with pytest.raises(TypeError):
            container.pop(next(iter(container), "k"), None)
        with pytest.raises(TypeError):
            container.update({"x": 1})
        with pytest.raises(TypeError):
            container.clear()

    def _assert_frozen_list(self, container):
        with pytest.raises(TypeError):
            container.append(1)
        with pytest.raises(TypeError):
            container[0] = 1
        with pytest.raises(TypeError):
            container.pop()
        with pytest.raises(TypeError):
            container.clear()

    def test_log_entry_fields_frozen(self):
        from data_engine.infra.observability import LogEntry
        caller = {"a": {"b": 1}}
        entry = LogEntry(level="info", message="m", fields=caller,
                         entry_hash="h" * 64)
        caller["a"]["b"] = 99
        assert entry.fields == {"a": {"b": 1}}
        self._assert_frozen_dict(entry.fields)
        with pytest.raises(TypeError):
            entry.fields["a"]["b"] = 99  # nested container frozen too

    def test_checkpoint_state_frozen(self):
        from data_engine.infra.observability import Checkpoint
        caller = {"pos": [1, 2]}
        cp = Checkpoint(checkpoint_id="c1", state=caller,
                        state_hash="h" * 64)
        caller["pos"].append(3)
        assert cp.state == {"pos": [1, 2]}
        self._assert_frozen_dict(cp.state)
        self._assert_frozen_list(cp.state["pos"])

    def test_exposure_report_maps_frozen(self):
        by_asset = {"AAA": "0.1"}
        report = ExposureReport(
            by_asset=by_asset, by_sector={"tech": "0.1"},
            single_asset_breaches=(), sector_breaches=(),
            total_exposure="0.1",
        )
        by_asset["AAA"] = "9.9"
        assert report.by_asset["AAA"] == "0.1"
        self._assert_frozen_dict(report.by_asset)
        self._assert_frozen_dict(report.by_sector)

    def test_allocation_weights_frozen(self):
        caller = {"AAA": "0.5"}
        alloc = Allocation(weights=caller, gross_exposure="0.5")
        caller["AAA"] = "9.9"
        assert alloc.weights["AAA"] == "0.5"
        self._assert_frozen_dict(alloc.weights)

    def test_knowledge_and_memory_content_frozen(self):
        from data_engine.knowledge.models import (
            KnowledgeRecord, MemoryRecord, RecordType,
        )
        from data_engine.research.governance import Principal, PrincipalKind
        principal = Principal(
            principal_id="human-1", kind=PrincipalKind.HUMAN
        )
        caller = {"k": {"v": [1]}}
        record = KnowledgeRecord(
            record_id="rec-000000000001", record_type=RecordType.OBSERVATION,
            principal=principal, content=caller,
        )
        caller["k"]["v"].append(2)
        assert record.content == {"k": {"v": [1]}}
        self._assert_frozen_dict(record.content)
        self._assert_frozen_list(record.content["k"]["v"])
        memory = MemoryRecord(
            session_id="s1", sequence=0, principal=principal,
            content={"m": [1]},
        )
        self._assert_frozen_dict(memory.content)
        self._assert_frozen_list(memory.content["m"])

    def test_revision_entry_payload_frozen(self):
        from data_engine.pit.revision import RevisionEntry
        caller = {"px": {"bid": 1.5}}
        entry = RevisionEntry(
            revision_time=utc(2020, 1, 1), publication_time=utc(2020, 1, 1),
            payload=caller,
        )
        caller["px"]["bid"] = 0.1
        assert entry.payload == {"px": {"bid": 1.5}}
        self._assert_frozen_dict(entry.payload)
        assert RevisionEntry(
            revision_time=utc(2020, 1, 1), publication_time=utc(2020, 1, 1),
        ).payload == {}  # default {} is frozen too

    def test_temporal_contract_field_lists_frozen(self):
        from data_engine.pit.contract import TemporalContract
        from data_engine.pit.temporal import TemporalDataType
        contract = TemporalContract(
            data_type=TemporalDataType.OHLCV,
            required_fields=["event_time"],
        )
        self._assert_frozen_list(contract.required_fields)
        self._assert_frozen_list(contract.eligible_fields)
        self._assert_frozen_list(contract.non_eligible_fields)

    def test_quant_record_series_frozen(self):
        from data_engine.quant.schemas import (
            IndicatorResult, IndicatorSeries,
        )
        result = IndicatorResult(
            indicator_name="sma", period=20, values=[1.0, None],
            dataset_id="ds", timeframe="15m", instrument="XAUUSD",
        )
        assert result.values == [1.0, None]  # equality with plain list kept
        self._assert_frozen_list(result.values)
        series = IndicatorSeries(
            name="sma", timestamps=[utc(2020, 1, 1), utc(2020, 1, 2)],
            values=[1.0, 2.0], timeframe="15m",
        )
        self._assert_frozen_list(series.timestamps)
        self._assert_frozen_list(series.values)
        assert series.last_valid() == (2.0, utc(2020, 1, 2))  # reads work

    def test_drawdown_series_frozen(self):
        from data_engine.quant.drawdown import DrawdownResult
        result = DrawdownResult(
            drawdowns=[0.1, 0.2], running_peaks=[1.0, 1.0],
            max_drawdown=0.2, max_drawdown_index=1,
            max_drawdown_duration=1, recovery_duration=1, total_periods=2,
        )
        self._assert_frozen_list(result.drawdowns)
        self._assert_frozen_list(result.running_peaks)

    def test_benchmark_and_validation_records_frozen(self):
        from data_engine.benchmarks.runner import BenchmarkCase
        from data_engine.quarantine import QuarantinedRecord
        from data_engine.research_validation.robustness import (
            RobustnessReport,
        )
        from data_engine.research_validation.walk_forward import (
            WalkForwardReport,
        )
        from data_engine.experiment_registry.registry import (
            ReproducibilityRun,
        )
        case = BenchmarkCase(name="n", description="d",
                             workload={"ops": 10}, operations=10)
        self._assert_frozen_dict(case.workload)
        quarantined = QuarantinedRecord(
            dataset_id="ds", record_index=0, candle_hash=None,
            validation_results=[], reason="r",
        )
        self._assert_frozen_list(quarantined.validation_results)
        robust = RobustnessReport(
            evaluations=(), plateau={"axes": {"fast": {"fragile": False}}},
            stable=True,
        )
        self._assert_frozen_dict(robust.plateau)
        assert robust.plateau["axes"]["fast"]["fragile"] is False  # reads
        wf = WalkForwardReport(
            window_count=1, per_window_results=(), oos_aggregate={"sharpe": 1.0},
        )
        self._assert_frozen_dict(wf.oos_aggregate)
        run = ReproducibilityRun(
            run_label="l", environment_pin={"engine": "v2"},
            input_hash="i" * 64, observed_output_hash="o" * 64,
            expected_output_hash="e" * 64, run_at=utc(2020, 1, 1),
        )
        self._assert_frozen_dict(run.environment_pin)

    def test_frozen_containers_serialize_identically(self):
        """Hash stability across the migration: frozen containers
        serialize exactly like plain containers (PIT canonical + JSON),
        so record identities are unchanged."""
        from data_engine.pit.serialization import canonical_serialize
        from data_engine.pit.immutable import freeze
        plain = {"b": 1, "a": {"x": [1, 2]}, "c": [3, 4]}
        frozen = freeze(plain)
        assert canonical_serialize(plain) == canonical_serialize(frozen)
        import json
        assert json.dumps(plain, sort_keys=True) == json.dumps(
            dict(frozen), sort_keys=True
        )

    def test_knowledge_hash_unchanged_by_freeze(self):
        from data_engine.knowledge.models import (
            KnowledgeRecord, RecordType,
        )
        from data_engine.research.governance import Principal, PrincipalKind
        principal = Principal(principal_id="human-1", kind=PrincipalKind.HUMAN)
        common = dict(
            record_id="rec-000000000001", record_type=RecordType.OBSERVATION,
            principal=principal, content={"k": 1},
        )
        a = KnowledgeRecord(**common)
        b = KnowledgeRecord(**{**common, "content": {"k": 1}})
        assert a.record_hash == b.record_hash
        assert a.record_hash.startswith("know42.")


# ======================================================================
# BUG-009 — finite-input analytics guard
# ======================================================================

class TestBug009FiniteGuards:

    def test_total_pnl_nan_raises(self):
        with pytest.raises(ValueError, match="not finite"):
            AnalyticsEngine.total_pnl([100.0, float("nan"), 90.0])

    def test_total_pnl_inf_raises(self):
        with pytest.raises(ValueError, match="not finite"):
            AnalyticsEngine.total_pnl([100.0, float("inf")])

    def test_max_drawdown_nan_raises(self):
        with pytest.raises(ValueError, match="not finite"):
            AnalyticsEngine.max_drawdown([100.0, float("nan"), 90.0])

    def test_max_drawdown_inf_raises(self):
        with pytest.raises(ValueError, match="not finite"):
            AnalyticsEngine.max_drawdown([100.0, -float("inf")])

    def test_sharpe_nan_raises(self):
        with pytest.raises(ValueError, match="not finite"):
            AnalyticsEngine.sharpe([0.01, float("nan")])

    def test_finite_behavior_unchanged(self):
        assert AnalyticsEngine.total_pnl([100.0, 110.0]) == 10.0
        assert AnalyticsEngine.max_drawdown([100.0, 80.0, 90.0]) == 0.2
        assert AnalyticsEngine.sharpe([0.01, 0.02]) > 0


# ======================================================================
# RT-F7 — CLI check-boundary exit semantics
# ======================================================================

class TestRtF7CheckBoundary:

    def test_deterministic_type_exits_zero(self, monkeypatch, capsys):
        """REPRO-G AFTER: 'check-boundary ema' succeeds (exit 0) — the
        pre-fix inversion called assert_deterministic and always
        exited 1."""
        monkeypatch.setattr(sys, "argv",
                             ["data-engine", "check-boundary", "ema"])
        from data_engine.cli import main
        main()  # must NOT raise SystemExit
        out = capsys.readouterr().out
        assert "DETERMINISTIC" in out

    def test_invalid_type_reports_error(self, monkeypatch, capsys):
        monkeypatch.setattr(sys, "argv",
                             ["data-engine", "check-boundary", "bogus"])
        from data_engine.cli import main
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
        assert "Error" in capsys.readouterr().err

    def test_no_argument_reports_usage(self, monkeypatch, capsys):
        """calc_type is a required positional argument — argparse
        reports usage and exits (the type-listing branch requires an
        optional argument that the CLI does not offer today)."""
        monkeypatch.setattr(sys, "argv", ["data-engine", "check-boundary"])
        from data_engine.cli import main
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 2  # argparse usage error


# ======================================================================
# ARCH-F4 — quant_boundary latent NameError
# ======================================================================

class TestArchF4QuantBoundaryTimestamps:

    def test_deterministic_result_default_timestamp(self):
        """REPRO-F AFTER: constructing DeterministicResult with the
        default factory no longer raises NameError."""
        from data_engine.quant_boundary import DeterministicResult
        result = DeterministicResult(
            calculation_type="ema", result=1.0, parameters={"period": 20},
            input_dataset_id="ds",
        )
        assert result.calculation_timestamp  # populated, not crashed

    def test_mark_complete_records_timestamp(self):
        from data_engine.quant_boundary import QuantBoundary
        boundary = QuantBoundary()
        boundary.mark_complete(1, {"value": 1.0})
        completed = boundary.get_completed()
        assert completed[0]["completed_at"]


# ======================================================================
# ARCH-F3 — ingestion EvidenceProvenance import
# ======================================================================

class TestArchF3IngestionProvenance:

    def test_build_provenance_resolves_evidence(self):
        """The happy-path provenance builder no longer dies with
        NameError: EvidenceProvenance is imported and applied."""
        from data_engine.ingestion import DataIngester
        from data_engine.schemas import (
            AssetClass, Instrument, ProviderConfig, Timeframe,
        )
        from data_engine.evidence import EvidenceProvenance
        ingester = DataIngester()
        config = ProviderConfig(
            provider_name="stub", provider_type="api", timezone="UTC",
        )
        instrument = Instrument(
            symbol="XAUUSD", base_asset="XAU", quote_asset="USD",
            asset_class=AssetClass.METAL,
        )
        provenance = ingester._build_provenance(
            provider=config, instrument=instrument,
            timeframe=Timeframe.M15,
            start=utc(2020, 1, 1), end=utc(2020, 1, 2),
            evidence_provenance="REAL", dataset_id="ds_1",
            dataset_version="v1", source_hash="0" * 64,
        )
        assert provenance.evidence_provenance is EvidenceProvenance.REAL


# ======================================================================
# ARCH-F6 — deterministic raw hash
# ======================================================================

class TestArchF6DeterministicRawHash:

    def _candle(self, offset=0.0):
        from data_engine.schemas import Candle, Timeframe
        ts = utc(2020, 1, 6, 10)
        return Candle(
            timestamp=ts, open=100.0 + offset, high=101.0 + offset,
            low=99.0 + offset, close=100.0 + offset, volume=1000.0,
            timeframe=Timeframe.M15,
            # provider_timestamp deliberately left to its wall-clock
            # default factory — the H-1 contamination vector.
        )

    def test_identical_market_data_hashes_identically(self):
        """Two SEPARATELY constructed candle lists with identical
        market fields (but different wall-clock provider_timestamp
        defaults) hash identically — the pre-fix implementation did
        not."""
        from data_engine.ingestion import DataIngester
        ingester = DataIngester()
        hash_a = ingester._compute_raw_hash([self._candle(), self._candle(1)])
        hash_b = ingester._compute_raw_hash([self._candle(), self._candle(1)])
        assert hash_a == hash_b

    def test_raw_hash_ignores_provider_timestamp(self):
        from data_engine.ingestion import DataIngester
        from data_engine.schemas import Candle, Timeframe
        ingester = DataIngester()
        common = dict(
            open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0,
            timeframe=Timeframe.M15,
        )
        a = Candle(timestamp=utc(2020, 1, 6, 10),
                   provider_timestamp=utc(2020, 1, 6, 10), **common)
        b = Candle(timestamp=utc(2020, 1, 6, 10),
                   provider_timestamp=utc(2021, 6, 1, 12), **common)
        assert ingester._compute_raw_hash([a]) == ingester._compute_raw_hash([b])

    def test_different_market_data_hashes_differently(self):
        from data_engine.ingestion import DataIngester
        ingester = DataIngester()
        assert (ingester._compute_raw_hash([self._candle()])
                != ingester._compute_raw_hash([self._candle(1)]))


# ======================================================================
# RT-F8 — ingest_from_file dead path
# ======================================================================

class TestRtF8IngestFromFile:

    CSV_ROWS = (
        "timestamp,open,high,low,close,volume\n"
        "2020-01-06T10:00:00+00:00,100.0,101.0,99.0,100.0,10000\n"
        "2020-01-06T11:00:00+00:00,102.0,103.0,101.0,102.0,10000\n"
    )

    def _write_csv(self, tmp_path, name="XAUUSD_15m.csv"):
        path = tmp_path / name
        path.write_text(self.CSV_ROWS, encoding="utf-8")
        return path

    def test_ingests_through_fs06_containment(self, tmp_path):
        """AFTER: the path carries an explicit approved data root and
        reads the file through the FS-01..24 containment layer instead
        of failing closed on a missing root (dead path)."""
        from data_engine.ingestion import ingest_from_file
        from data_engine.schemas import Timeframe
        path = self._write_csv(tmp_path)
        result = ingest_from_file(
            file_path=str(path), instrument="XAUUSD",
            timeframe=Timeframe.M15,
            start=utc(2020, 1, 6), end=utc(2020, 1, 7),
        )
        assert result.blocked is False
        assert result.dataset is not None
        assert result.dataset.total_rows == 2

    def test_wrong_filename_fails_closed(self, tmp_path):
        from data_engine.ingestion import ingest_from_file
        from data_engine.schemas import Timeframe
        path = self._write_csv(tmp_path, name="other.csv")
        with pytest.raises(ValueError, match="ingest_from_file contract"):
            ingest_from_file(
                file_path=str(path), instrument="XAUUSD",
                timeframe=Timeframe.M15,
                start=utc(2020, 1, 6), end=utc(2020, 1, 7),
            )

    def test_missing_file_blocks_honestly(self, tmp_path):
        """A non-existent (but correctly named) file returns zero
        candles and DATA_QUALITY_BLOCKED — fail closed, no fabrication."""
        from data_engine.ingestion import ingest_from_file
        from data_engine.schemas import Timeframe
        result = ingest_from_file(
            file_path=str(tmp_path / "XAUUSD_15m.csv"),
            instrument="XAUUSD", timeframe=Timeframe.M15,
            start=utc(2020, 1, 6), end=utc(2020, 1, 7),
        )
        assert result.blocked is True
        assert result.dataset is None

    def test_security_layers_still_enforced(self, tmp_path):
        """The FS-06/FS-14 security invariants are untouched: a provider
        without an approved root still fails closed (at construction
        for an absolute endpoint — FS-18 — or at read otherwise)."""
        from data_engine.schemas import ProviderConfig
        from data_engine.provider import ProviderFactory
        from data_engine.security import FilesystemSecurityError
        with pytest.raises((ValueError, FilesystemSecurityError)):
            config = ProviderConfig(
                provider_name="file", provider_type="file",
                endpoint=str(tmp_path), timezone="UTC",
            )  # no approved_data_root, no allowlist
            ProviderFactory.create(config).fetch_candles(
                "XAUUSD",
                __import__(
                    "data_engine.schemas", fromlist=["Timeframe"]
                ).Timeframe.M15,
                utc(2020, 1, 6), utc(2020, 1, 7),
            )


# ======================================================================
# RT-F13 — packaging / artifact hygiene
# ======================================================================

class TestRtF13Hygiene:

    def test_pytest_not_a_runtime_dependency(self):
        import tomllib
        data = tomllib.loads(
            (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        deps = data["project"]["dependencies"]
        assert not any(d.startswith("pytest") for d in deps), (
            "RT-F13: pytest must not be a runtime dependency"
        )
        dev = data["project"]["optional-dependencies"]["dev"]
        assert any(d.startswith("pytest") for d in dev)

    def test_src_audit_log_untracked(self):
        out = subprocess.run(
            ["git", "ls-files", "src/audit.log"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        ).stdout.strip()
        assert out == "", "RT-F13: src/audit.log must not be tracked"

    def test_gitignore_covers_audit_log(self):
        out = subprocess.run(
            ["git", "check-ignore", "src/audit.log"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        assert out.returncode == 0, (
            "RT-F13: .gitignore must cover the runtime audit artifact"
        )

    def test_no_pytest_imports_in_src(self):
        """The packaging change is safe: nothing in src/ imports pytest."""
        hits = []
        for path in (REPO_ROOT / "src").rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith(("import pytest", "from pytest")):
                    hits.append(f"{path}:{stripped}")
        assert hits == []


# ======================================================================
# Frozen-contract protection (P1 rule 1)
# ======================================================================

class TestFrozenContractsUntouched:

    def test_frozen_phase3_blobs_byte_identical(self):
        """P1 rule 1: the 11 frozen Phase-3 blobs are byte-identical to
        main@13fdc7e (mirrors final_gate_verify.py check 1)."""
        FROZEN = [
            "src/data_engine/strategy/__init__.py",
            "src/data_engine/strategy/backtest.py",
            "src/data_engine/strategy/conditions.py",
            "src/data_engine/strategy/equity.py",
            "src/data_engine/strategy/execution.py",
            "src/data_engine/strategy/ledger.py",
            "src/data_engine/strategy/metrics.py",
            "src/data_engine/strategy/position.py",
            "src/data_engine/strategy/provenance.py",
            "src/data_engine/strategy/schemas.py",
            "src/data_engine/strategy/validation.py",
        ]

        def sh(*args):
            return subprocess.run(
                args, cwd=REPO_ROOT, capture_output=True, text=True,
                check=True,
            ).stdout.strip()

        same = sum(
            1 for f in FROZEN
            if sh("git", "rev-parse", f"13fdc7e:{f}")
            == sh("git", "rev-parse", f"HEAD:{f}")
        )
        assert same == 11

    def test_schemas_py_manifest_pinned_untouched(self):
        """P1 rule 1: schemas.py is SUB-18 manifest-pinned — this window
        deliberately did not modify it (BUG-008 schemas.py fields are
        deferred with the rule citation)."""
        import hashlib
        record = (REPO_ROOT / "PHASE_4A1_IMPLEMENTATION_RECORD.md").read_text(
            encoding="utf-8"
        )
        import re as _re
        block = _re.search(
            r"```(?:\w+)?\n([0-9a-f]{64}  [^\n]+\n)+```", record
        )
        recorded = {}
        for line in block.group(0).strip("`").strip().splitlines():
            m = _re.match(r"^([0-9a-f]{64})  (\S+)$", line.strip())
            if m:
                recorded[m.group(2)] = m.group(1)
        mismatches = []
        for f, h in recorded.items():
            actual = hashlib.sha256(
                (REPO_ROOT / f).read_bytes()
            ).hexdigest()
            if actual != h:
                mismatches.append(f)
        assert mismatches == [], f"SUB-18 manifest violated: {mismatches}"
