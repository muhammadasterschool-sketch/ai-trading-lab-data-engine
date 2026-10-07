"""Phase 11 acceptance tests — paper trading pipeline.

Blueprint 5.51/5.55 invariants:

- PT-01  market realism: spread/commission/slippage all recorded in
          the fill; adverse direction applied
- PT-02  latency: market order fills at the NEXT bar's open (never
          the triggering bar — no look-ahead fills)
- PT-03  participation cap: oversized orders rejected (realism gate)
- PT-04  limit orders fill only on crossing bars, at the limit
- PT-05  duplicate order protection; cancel semantics
- PT-06  position accounting: average cost, realized P&L on reduce
- PT-07  reconciliation: replay reproduces positions exactly;
          discrepancies raise (fail closed)
- PT-08  audit trail hash-chained and tamper-evident
- PT-09  no credential surface: orders carry no account/auth fields
          (extra=forbid enforces the contract)
"""

from datetime import datetime, UTC
from decimal import Decimal

import pytest

from data_engine.paper import (
    Fill,
    OrderSide,
    OrderType,
    OrderStatus,
    PaperOrder,
    PaperPosition,
    ExecutionRealism,
    ExecutionSimulator,
    SimulationError,
    PaperOrderGateway,
    GatewayError,
    ReconciliationEngine,
    ReconciliationError,
    AuditLogger,
    AnalyticsEngine,
)

D = Decimal


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


def make_order(coid="o-1", side=OrderSide.BUY, qty="100", submitted=None,
               order_type=OrderType.MARKET, limit=None):
    return PaperOrder(
        client_order_id=coid, symbol="AAA", side=side,
        order_type=order_type, quantity=D(qty),
        limit_price=D(limit) if limit else None,
        submitted_at=submitted or utc(2020, 1, 6, 10),
    )


class TestSimulator:

    def test_pt_01_realism_costs_recorded(self):
        simulator = ExecutionSimulator(REALISM)
        fill = simulator.simulate(make_order(), make_bars())
        assert fill is not None
        # Fill price = next-bar open 102 + half_spread 0.05 + impact
        impact = D("0.001") * (D(100) / D(10000)) * D("102")
        assert fill.price == D("102") + D("0.05") + impact
        assert fill.commission == D("0.01") * D(100)
        assert fill.spread_cost == D("0.05") * D(100)
        assert fill.slippage_cost == impact * D(100)
        assert fill.fill_hash.startswith("fill11.")

    def test_pt_02_latency_no_lookahead(self):
        """PT-02: submitted during bar 0 -> fills at bar 1 open, not bar 0."""
        simulator = ExecutionSimulator(REALISM)
        fill = simulator.simulate(make_order(), make_bars())
        assert fill.filled_at == utc(2020, 1, 6, 11)
        # A sell fills BELOW the bar-1 open (adverse)
        sell = simulator.simulate(
            make_order(side=OrderSide.SELL), make_bars()
        )
        assert sell.price < D("102")
        # Order submitted during the LAST bar cannot fill (latency)
        late = simulator.simulate(
            make_order(submitted=utc(2020, 1, 6, 12)), make_bars()
        )
        assert late is None

    def test_pt_03_participation_cap(self):
        simulator = ExecutionSimulator(REALISM)
        with pytest.raises(SimulationError, match="participation"):
            simulator.simulate(make_order(qty="5000"), make_bars())

    def test_pt_04_limit_orders(self):
        simulator = ExecutionSimulator(REALISM)
        # Buy limit 101.5: bar 1 low is 101 -> crosses -> fills at 101.5
        fill = simulator.simulate(
            make_order(order_type=OrderType.LIMIT, limit="101.5"),
            make_bars(),
        )
        assert fill is not None
        assert fill.price > D("101.5")  # adverse adjustments on top
        # Buy limit 90 never crosses -> no fill
        no_fill = simulator.simulate(
            make_order(order_type=OrderType.LIMIT, limit="90"),
            make_bars(),
        )
        assert no_fill is None

    def test_pt_09_no_credential_surface(self):
        with pytest.raises(ValueError):
            PaperOrder.model_validate(
                {
                    "client_order_id": "x", "symbol": "AAA",
                    "side": "buy", "order_type": "market",
                    "quantity": D("1"),
                    "submitted_at": utc(2020, 1, 1),
                    "broker_account": "leak",  # forbidden field
                }
            )
        with pytest.raises(ValueError, match="limit orders require"):
            make_order(order_type=OrderType.LIMIT)
        with pytest.raises(ValueError, match="must not carry"):
            make_order(limit="100")


class TestGateway:

    def test_pt_05_lifecycle_and_duplicates(self):
        gateway = PaperOrderGateway(ExecutionSimulator(REALISM))
        record = gateway.submit(make_order(), make_bars())
        assert record.status is OrderStatus.FILLED
        with pytest.raises(GatewayError, match="duplicate"):
            gateway.submit(make_order(), make_bars())
        # Unfillable limit order stays SUBMITTED and can be cancelled
        pending = gateway.submit(
            make_order(coid="o-2", order_type=OrderType.LIMIT, limit="50"),
            make_bars(),
        )
        assert pending.status is OrderStatus.SUBMITTED
        cancelled = gateway.cancel("o-2")
        assert cancelled.status is OrderStatus.CANCELLED
        with pytest.raises(GatewayError, match="only submitted"):
            gateway.cancel("o-2")
        # Oversized order: realism gate rejects
        with pytest.raises(GatewayError, match="realism gate"):
            gateway.submit(make_order(coid="o-3", qty="5000"), make_bars())
        rejected = gateway.record("o-3")
        assert rejected.status is OrderStatus.REJECTED


class TestPositionsAndReconciliation:

    def test_pt_06_position_accounting(self):
        buy = Fill(
            fill_id="f1", client_order_id="o-1", symbol="AAA",
            side=OrderSide.BUY, quantity=D("10"), price=D("100"),
            commission=D("1"), slippage_cost=D("0"), spread_cost=D("0"),
            filled_at=utc(2020, 1, 1),
        )
        sell = Fill(
            fill_id="f2", client_order_id="o-2", symbol="AAA",
            side=OrderSide.SELL, quantity=D("10"), price=D("110"),
            commission=D("1"), slippage_cost=D("0"), spread_cost=D("0"),
            filled_at=utc(2020, 1, 2),
        )
        empty = PaperPosition(symbol="AAA")
        held = empty.apply_fill(buy)
        # cost-inclusive average: (100*10 + 1) / 10 = 100.1
        assert held.quantity == D("10")
        assert held.average_cost == D("100.1")
        closed = held.apply_fill(sell)
        assert closed.quantity == D("0")
        # realized: (110 - 1) per unit sell proceeds net... sell price
        # net of costs = (110*10 - 1)/10 = 109.9; pnl = (109.9-100.1)*10
        assert closed.realized_pnl == (D("109.9") - D("100.1")) * D("10")

    def test_pt_07_reconciliation(self):
        simulator = ExecutionSimulator(REALISM)
        bars = make_bars()
        order = make_order()
        fill = simulator.simulate(order, bars)
        positions = {
            "AAA": PaperPosition(symbol="AAA").apply_fill(fill),
        }
        engine = ReconciliationEngine()
        result = engine.reconcile([order], [fill], positions)
        assert result["status"] == "reconciled"
        # Tampered position state -> discrepancy raises
        tampered = {
            "AAA": PaperPosition(
                symbol="AAA", quantity=D("999"),
                average_cost=D("1"), realized_pnl=D("0"),
            ),
        }
        with pytest.raises(ReconciliationError, match="reconciliation failed"):
            engine.reconcile([order], [fill], tampered)
        # Orphan fill raises
        ghost = Fill(
            fill_id="g", client_order_id="ghost", symbol="AAA",
            side=OrderSide.BUY, quantity=D("1"), price=D("1"),
            commission=D("0"), slippage_cost=D("0"), spread_cost=D("0"),
            filled_at=utc(2020, 1, 1),
        )
        with pytest.raises(ReconciliationError, match="fills without orders"):
            engine.reconcile([order], [ghost], positions)


class TestAuditAndAnalytics:

    def test_pt_08_audit_trail(self):
        audit = AuditLogger()
        audit.log("order_submitted", {"client_order_id": "o-1"})
        audit.log("order_filled", {"client_order_id": "o-1", "price": "102"})
        assert len(audit) == 2
        assert audit.verify()
        audit._entries[0]["event"] = "TAMPERED"
        assert not audit.verify()

    def test_pt_08b_analytics(self):
        engine = AnalyticsEngine()
        equity = [100000.0, 101000.0, 100500.0, 102000.0]
        returns = [0.01, -0.00495, 0.014925]
        summary = engine.summarize(equity, returns)
        assert summary["total_pnl"] == pytest.approx(2000.0)
        assert summary["max_drawdown"] == pytest.approx(
            (101000.0 - 100500.0) / 101000.0
        )
        assert summary["sharpe"] == pytest.approx(
            (sum(returns) / 3)
            / (__import__("math").sqrt(
                sum((r - sum(returns) / 3) ** 2 for r in returns) / 2
            ))
            * 252 ** 0.5
        )
        with pytest.raises(ValueError):
            engine.total_pnl([1.0])
