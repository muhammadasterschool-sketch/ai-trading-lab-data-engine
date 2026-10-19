"""U-22 (Stage D, patch plan P6) — the consolidated paper simulation
assumption register (docs/PAPER_SIMULATION_ASSUMPTIONS.md) pinned to
the CODE it describes.

Pinning strategy (documentation must never drift from behavior):

- **Structural pins** — the document exists, carries the mandated
  sections (fills / rejections / partials / slippage / fees / latency /
  venue outcomes), states PAPER_READY = FALSE, and names its
  authoritative implementation modules.
- **Behavioral agreement** — every documented numeric invariant is
  re-derived from the code: fill lag >= 1 with default 1,
  participation cap in (0, 1], non-negative costs, ALL-OR-NOTHING
  fills (a Fill always carries the full order quantity), oversized
  orders raise (never partially fill), limit fills never cross the
  limit, and the cost-decomposition identity holds in exact Decimal
  arithmetic.
"""

import re
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.paper.models import OrderSide, OrderType, PaperOrder
from data_engine.paper.simulator import (
    ExecutionRealism,
    ExecutionSimulator,
    SimulationError,
)

DOC = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "PAPER_SIMULATION_ASSUMPTIONS.md"
)


# ----------------------------------------------------------------------
# 1. Structural pins — the register exists and carries every mandate
# ----------------------------------------------------------------------
class TestDocumentStructure:
    def test_document_exists(self):
        assert DOC.is_file(), "PAPER_SIMULATION_ASSUMPTIONS.md is missing"

    @pytest.mark.parametrize(
        "section",
        [
            "## 1. Fills",
            "## 2. Rejections",
            "## 3. Partial fills",
            "## 4. Slippage",
            "## 5. Fees",
            "## 6. Latency",
            "## 7. Cost decomposition identity",
            "## 8. Determinism",
            "## 9. Venue-level submission outcomes",
            "## 10. What this document does not claim",
        ],
    )
    def test_mandated_sections_present(self, section):
        text = DOC.read_text(encoding="utf-8")
        assert section in text, f"missing section {section!r}"

    def test_paper_ready_false_stated(self):
        text = DOC.read_text(encoding="utf-8")
        assert "PAPER_READY = FALSE" in text
        assert "LIVE TRADING NOT AUTHORIZED" in text

    def test_authoritative_modules_named(self):
        text = DOC.read_text(encoding="utf-8")
        for module in (
            "paper/simulator.py",
            "paper/gateway.py",
            "brokers/session.py",
            "runtime/broker_execution.py",
        ):
            assert module in text, f"doc must cite its authority {module}"

    def test_no_real_market_claims(self):
        text = DOC.read_text(encoding="utf-8")
        assert "No real-market microstructure" in text
        assert "MOCK_DETERMINISTIC" in text


# ----------------------------------------------------------------------
# 2. Behavioral agreement — the documented invariants ARE the code's
# ----------------------------------------------------------------------
_REALISM = ExecutionRealism(
    half_spread=Decimal("0.05"),
    commission_per_unit=Decimal("0.001"),
    impact_rate=Decimal("0.01"),
    participation_cap=Decimal("0.10"),
)


def _bar(ts_minutes, open_, high, low, close, volume):
    from datetime import datetime, timedelta, UTC

    return {
        "timestamp": datetime(2026, 1, 1, tzinfo=UTC)
        + timedelta(minutes=ts_minutes),
        "open": Decimal(str(open_)),
        "high": Decimal(str(high)),
        "low": Decimal(str(low)),
        "close": Decimal(str(close)),
        "volume": volume,
    }


def _order(submitted_at_minutes, side=OrderSide.BUY, qty=Decimal("10")):
    from datetime import datetime, timedelta, UTC

    submitted = (
        datetime(2026, 1, 1, tzinfo=UTC)
        + timedelta(minutes=submitted_at_minutes)
    )
    return PaperOrder(
        client_order_id="doc-pin-1",
        symbol="TEST/USD",
        side=side,
        order_type=OrderType.MARKET,
        quantity=qty,
        submitted_at=submitted,
    )


class TestDocumentNumericAgreement:
    def test_fill_lag_default_is_one_and_minimum_is_one(self):
        assert _REALISM.fill_lag_bars == 1
        with pytest.raises(ValueError):
            ExecutionRealism(
                half_spread=Decimal("0.05"),
                commission_per_unit=Decimal("0.001"),
                impact_rate=Decimal("0.01"),
                participation_cap=Decimal("0.10"),
                fill_lag_bars=0,
            )

    def test_participation_cap_bounds(self):
        with pytest.raises(ValueError):
            ExecutionRealism(
                half_spread=Decimal("0.05"),
                commission_per_unit=Decimal("0.001"),
                impact_rate=Decimal("0.01"),
                participation_cap=Decimal("0"),
            )
        with pytest.raises(ValueError):
            ExecutionRealism(
                half_spread=Decimal("0.05"),
                commission_per_unit=Decimal("0.001"),
                impact_rate=Decimal("0.01"),
                participation_cap=Decimal("1.5"),
            )

    def test_costs_are_non_negative_by_construction(self):
        with pytest.raises(ValueError):
            ExecutionRealism(
                half_spread=Decimal("-0.05"),
                commission_per_unit=Decimal("0.001"),
                impact_rate=Decimal("0.01"),
                participation_cap=Decimal("0.10"),
            )

    def test_fills_are_all_or_nothing(self):
        """A Fill ALWAYS carries the full order quantity (no partials)."""
        sim = ExecutionSimulator(_REALISM)
        bars = [
            _bar(0, 100, 101, 99, 100, 100_000),
            _bar(5, 100, 101, 99, 100, 100_000),
        ]
        fill = sim.simulate(_order(0), bars)
        assert fill is not None
        assert fill.quantity == Decimal("10")

    def test_oversized_orders_raise_never_partially_fill(self):
        sim = ExecutionSimulator(_REALISM)
        bars = [
            _bar(0, 100, 101, 99, 100, 100_000),
            _bar(5, 100, 101, 99, 100, 100_000),
        ]
        oversized = _order(0, qty=Decimal("20000"))  # > 10% of volume
        with pytest.raises(SimulationError, match="participation"):
            sim.simulate(oversized, bars)

    def test_market_fill_is_next_bar_open_plus_adverse_stack(self):
        sim = ExecutionSimulator(_REALISM)
        bars = [
            _bar(0, 100, 101, 99, 100, 100_000),
            _bar(5, 102, 103, 101, 102, 100_000),
        ]
        fill = sim.simulate(_order(0), bars)
        assert fill is not None
        impact = Decimal("0.01") * (Decimal("10") / Decimal("100000")) * Decimal("102")
        expected = Decimal("102") + Decimal("0.05") + impact
        assert fill.price == expected
        # ... and never the triggering bar's open (100)
        assert fill.price != Decimal("100")

    def test_limit_never_fills_through_the_limit(self):
        sim = ExecutionSimulator(_REALISM)
        bars = [
            _bar(0, 100, 101, 99, 100, 100_000),
            _bar(5, 102, 103, 101, 102, 100_000),
        ]
        from datetime import datetime, timedelta, UTC

        order = PaperOrder(
            client_order_id="doc-pin-limit",
            symbol="TEST/USD",
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=Decimal("10"),
            limit_price=Decimal("100.5"),
            submitted_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        fill = sim.simulate(order, bars)
        # the bar crossed the limit (low 101 > limit? no: low=101 which is
        # ABOVE the 100.5 limit -> NOT crossed -> no fill). Use a low that
        # crosses instead:
        assert fill is None
        crossing = [
            _bar(0, 100, 101, 99, 100, 100_000),
            _bar(5, 102, 103, 100, 102, 100_000),  # low 100 <= limit 100.5
        ]
        fill = sim.simulate(order, crossing)
        assert fill is not None
        assert fill.price <= Decimal("100.5")

    def test_cost_decomposition_identity_holds_exactly(self):
        sim = ExecutionSimulator(_REALISM)
        bars = [
            _bar(0, 100, 101, 99, 100, 100_000),
            _bar(5, 102, 103, 101, 102, 100_000),
        ]
        fill = sim.simulate(_order(0), bars)
        qty = fill.quantity
        assert (
            fill.price * qty
            == Decimal("102") * qty + fill.spread_cost + fill.slippage_cost
        )
        assert fill.commission == Decimal("0.001") * qty

    def test_bar_ordering_is_enforced(self):
        sim = ExecutionSimulator(_REALISM)
        bad = [
            _bar(0, 100, 101, 99, 100, 100_000),
            _bar(0, 100, 101, 99, 100, 100_000),  # duplicate timestamp
        ]
        with pytest.raises(SimulationError, match="strictly"):
            sim.simulate(_order(0), bad)

    def test_venue_outcomes_vocabulary_matches_the_doc(self):
        """ACCEPTED / REFUSED / UNKNOWN is the closed outcome
        vocabulary at the venue seam — pinned by the session journal's
        entry types."""
        from data_engine.brokers import session as session_module

        source = Path(session_module.__file__).read_text(encoding="utf-8")
        for entry in ("ORDER_ACK", "ORDER_REFUSED"):
            assert entry in source, (
                f"journal vocabulary must include {entry} (doc §9)"
            )
        # The doc's timeout/UNKNOWN discipline lives in the venue seam:
        from data_engine.runtime import broker_execution as be

        be_source = Path(be.__file__).read_text(encoding="utf-8")
        assert "VenueSubmissionUncertain" in be_source
        assert "VenueSubmissionRefused" in be_source
