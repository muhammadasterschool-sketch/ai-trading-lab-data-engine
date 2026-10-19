"""F-06 — venue-level submission-rate backstop on the runtime paper
venue (Milestone A B2 completion; master prompt v4.0 Stage 1 Group 2).

The durable submission ledger + spacing governor (B1/B2 core, commit
734a4e6) cap submissions at the RUNTIME boundary. Finding F-06
(artifacts/stage-a/02-FINDINGS-REGISTER.md) noted that the
authoritative paper VENUE itself was uncapped:
``RUNTIME_PAPER_VENUE_CAPABILITIES`` declared the default
``RateLimitPolicy()`` (0 = unlimited) and
``RuntimePaperExecutionAdapter`` enforced no order budget — a caller
that bypassed (or a bug that skipped) the runtime gates could submit
to the venue without any venue-side limit.

This group closes F-06 exactly as the patch plan (Group P2)
specifies: the owner-ratified paper defaults (Part 3 — max 5 orders
per 60 seconds) are declared in
``RUNTIME_PAPER_VENUE_CAPABILITIES.rate_limit`` AND enforced
venue-side, independent of every runtime gate (defense in depth).

PROVEN HERE
-----------
1. The capability descriptor declares the owner-ratified budget
   (5 orders / 60s, with a real cool-down hint).
2. The venue adapter ALONE — no risk gate, no kill switch, no ledger,
   no governor — refuses the 6th submission inside the window.
3. Idempotent duplicates (same ``client_order_id``) never consume
   budget — retries of an already-held order are free, mirroring the
   venue-side idempotency contract.
4. The budget is restored only when the window genuinely slides
   (injectable-clock determinism).
5. A venue refusal leaves NO venue order (never half-accepts).
6. Through a full ``BrokerSession`` with permissive central gates
   (the "runtime gate bypassed" scenario), the 6th submission is
   still refused BY THE VENUE — venue independence at the
   broker-neutral boundary.

All venues in these tests are paper/mock. No real broker, no
network, no real credentials. LIVE TRADING REMAINS NOT AUTHORIZED;
PAPER_READY stays FALSE.
"""

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.brokers.errors import (
    BrokerErrorCategory,
    RateLimitError,
)
from data_engine.brokers.models import (
    OrderKind,
    OrderRequest,
    Side,
)
from data_engine.brokers.redaction import BrokerCredential
from data_engine.brokers.session import (
    BrokerSession,
    KillSwitchState,
    RiskDecision,
    RetryPolicy,
)
from data_engine.runtime import RuntimePaperExecutionAdapter
from data_engine.runtime.broker_execution import (
    RUNTIME_PAPER_VENUE_CAPABILITIES,
    RUNTIME_PAPER_VENUE_ID,
)

from test_runtime_authoritative_venue import (
    ACCOUNT,
    CLOCK_BASE,
    SECRET,
    SYMBOL,
    _mk_runtime,
    _specs,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
class _Stepper:
    """Controllable deterministic clock (advances ``step`` per call,
    jumpable for window-slide tests)."""

    def __init__(self, step: timedelta = timedelta(seconds=1)):
        self.t = CLOCK_BASE
        self.step = step

    def __call__(self):
        self.t = self.t + self.step
        return self.t

    def jump(self, delta: timedelta) -> None:
        self.t = self.t + delta


def _request(cid: str, qty: Decimal = Decimal("1")) -> OrderRequest:
    return OrderRequest(
        client_order_id=cid,
        account_id=ACCOUNT,
        symbol=SYMBOL,
        side=Side.BUY,
        order_kind=OrderKind.MARKET,
        quantity=qty,
    )


def _adapter(tmp_path: Path, clock) -> RuntimePaperExecutionAdapter:
    rt = _mk_runtime(f"rate-backstop-{tmp_path.name}", tmp_path / "state")
    adapter = RuntimePaperExecutionAdapter(
        rt,
        instruments=_specs(),
        account_id=ACCOUNT,
        clock=clock,
    )
    adapter.connect(BrokerCredential(ACCOUNT, SECRET))
    return adapter


# ---------------------------------------------------------------------------
# 1. Capability declaration (F-06: the venue is no longer "uncapped")
# ---------------------------------------------------------------------------
class TestCapabilityDeclaration:

    def test_owner_ratified_budget_declared(self):
        policy = RUNTIME_PAPER_VENUE_CAPABILITIES.rate_limit
        # Owner-ratified paper defaults (Part 3): max 5 per 60s.
        assert policy.max_orders_per_window == 5
        assert policy.window_seconds == 60.0
        # A real cool-down hint, never zero/None (the refusal carries it).
        assert policy.retry_after_seconds is not None
        assert policy.retry_after_seconds >= 60.0

    def test_capability_belongs_to_runtime_paper_venue(self):
        assert (
            RUNTIME_PAPER_VENUE_CAPABILITIES.broker_id
            == RUNTIME_PAPER_VENUE_ID
        )


# ---------------------------------------------------------------------------
# 2-5. Venue-adapter budget — completely independent of runtime gates
# ---------------------------------------------------------------------------
class TestVenueAdapterBudget:

    def test_fifth_accepted_sixth_refused(self, tmp_path):
        adapter = _adapter(tmp_path, _Stepper())
        for i in range(1, 6):
            ack = adapter.submit_order(_request(f"cid-{i}"))
            assert ack.client_order_id == f"cid-{i}"
        with pytest.raises(RateLimitError) as exc:
            adapter.submit_order(_request("cid-6"))
        assert exc.value.category is BrokerErrorCategory.RATE_LIMIT
        assert exc.value.retry_after_seconds is not None
        assert exc.value.retry_after_seconds >= 60.0

    def test_idempotent_duplicate_does_not_consume_budget(self, tmp_path):
        adapter = _adapter(tmp_path, _Stepper())
        first = adapter.submit_order(_request("dup-1"))
        again = adapter.submit_order(_request("dup-1"))
        # Same client_order_id resolves to the SAME venue truth, and
        # the duplicate consumed NO budget: 4 more distinct ids fit.
        assert again.client_order_id == first.client_order_id
        assert again.venue_order_id == first.venue_order_id
        for i in range(2, 6):
            adapter.submit_order(_request(f"dup-{i}"))
        with pytest.raises(RateLimitError):
            adapter.submit_order(_request("dup-7"))

    def test_budget_restores_only_after_window_slides(self, tmp_path):
        stepper = _Stepper()
        adapter = _adapter(tmp_path, stepper)
        for i in range(1, 6):
            adapter.submit_order(_request(f"win-{i}"))
        # Still WELL inside the 60s window (a small jump keeps every
        # submission timestamp within it): the budget is NOT restored.
        stepper.jump(timedelta(seconds=5))
        with pytest.raises(RateLimitError):
            adapter.submit_order(_request("win-6"))
        # The window genuinely slid past 60s since the OLDEST
        # submission (a generous 300s jump — deterministic under any
        # clock-call count): the budget recovers.
        stepper.jump(timedelta(seconds=300))
        ack = adapter.submit_order(_request("win-6"))
        assert ack.client_order_id == "win-6"

    def test_refusal_leaves_no_venue_order(self, tmp_path):
        adapter = _adapter(tmp_path, _Stepper())
        for i in range(1, 6):
            adapter.submit_order(_request(f"held-{i}"))
        with pytest.raises(RateLimitError):
            adapter.submit_order(_request("held-6"))
        # The refused request never became a venue order: the venue
        # holds exactly the 5 admitted ids (fail-closed, no ghosts).
        for i in range(1, 6):
            status = adapter.order_status(f"held-{i}")
            assert status.client_order_id == f"held-{i}"
        with pytest.raises(Exception):
            adapter.order_status("held-6")


# ---------------------------------------------------------------------------
# 6. Session-boundary independence (permissive central gates — the
#    venue budget is the last line of defense)
# ---------------------------------------------------------------------------
def _approve(request: OrderRequest) -> RiskDecision:
    return RiskDecision(approved=True)


def _switch_off() -> KillSwitchState:
    return KillSwitchState(active=False)


class TestSessionBoundaryIndependence:

    def test_sixth_submission_refused_by_venue_through_session(
        self, tmp_path,
    ):
        rt = _mk_runtime(f"sess-backstop-{tmp_path.name}",
                         tmp_path / "state")
        adapter = RuntimePaperExecutionAdapter(
            rt,
            instruments=_specs(),
            account_id=ACCOUNT,
            clock=_Stepper(),
        )
        session = BrokerSession(
            adapter,
            account_id=ACCOUNT,
            journal_path=tmp_path / "session-journal.json",
            risk_decision_fn=_approve,
            kill_switch_fn=_switch_off,
            retry_policy=RetryPolicy(max_attempts=1),
            sleeper=lambda s: None,
            clock=_Stepper(),
        )
        session.connect(BrokerCredential(ACCOUNT, SECRET))
        for i in range(1, 6):
            ack = session.submit_order(_request(f"sess-{i}"))
            assert ack.client_order_id == f"sess-{i}"
        # Central gates are permissive; ONLY the venue budget refuses.
        with pytest.raises(RateLimitError) as exc:
            session.submit_order(_request("sess-6"))
        assert exc.value.category is BrokerErrorCategory.RATE_LIMIT
        # The venue holds exactly the 5 accepted orders.
        assert len(adapter._orders) == 5
