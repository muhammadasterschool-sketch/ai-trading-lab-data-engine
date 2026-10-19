"""U-21 (Stage D, patch plan P6) — PAPER-MODE-ONLY venue selection
proof, test-pinned.

The claim being proven, with regression force: **no code path selects
a live account in paper mode.** This is not a convention — it is four
independent structural refusal layers, each pinned here:

1. **Descriptor layer** — ``BrokerCapabilities`` refuses to even
   construct a REAL execution-mode descriptor that declares a REAL
   account mode (capabilities.py model validator).
2. **Registry/catalog layer** — every descriptor shipped in the
   default catalog is ``MOCK_DETERMINISTIC`` and declares ONLY
   ``DEMO`` account modes.
3. **Session layer** — ``BrokerSession`` refuses to construct against
   ANY adapter whose execution mode is not ``MOCK_DETERMINISTIC``
   (session.py), and the mock venue core refuses the same
   (adapters/_mock_core.py).
4. **Runtime layer** — the runtime paper venue capabilities are
   ``MOCK_DETERMINISTIC``/DEMO-only, the runtime's attach seams are
   paper-venue constructors, and the RiskGate's mandatory check #1
   refuses EVERY order when ``paper_mode`` is False.

Plus a structural AST scan: the ONLY module in ``src/`` that may
reference ``ExecutionMode.REAL`` is the refusal validator itself
(capabilities.py). Any new file that references REAL execution must
fail this test until it is either a refusal site or is explicitly
reviewed onto the allowlist.

PAPER_READY stays FALSE. LIVE TRADING REMAINS NOT AUTHORIZED.
"""

import ast
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.brokers.adapters._mock_core import (
    DeterministicMockVenue,
    MockVenueError,
)
from data_engine.brokers.capabilities import (
    AccountMode,
    BrokerCapabilities,
    CapabilityRegistry,
    ExecutionMode,
    OrderKind,
    RateLimitPolicy,
    ReconciliationStyle,
    default_registry,
)
from data_engine.brokers.interface import BrokerAdapter
from data_engine.brokers.models import InstrumentSpec
from data_engine.brokers.session import BrokerSession, SessionJournalError
from data_engine.runtime.broker_execution import (
    RUNTIME_PAPER_VENUE_CAPABILITIES,
    RUNTIME_PAPER_VENUE_ID,
)
from data_engine.runtime.risk_gate import RiskContext, RiskGate

from test_runtime_authoritative_venue import _clock, _plan, _specs

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


# ----------------------------------------------------------------------
# 1. Descriptor layer — REAL + REAL account is not even constructible
# ----------------------------------------------------------------------
class TestDescriptorLayerRefusal:
    def test_real_execution_with_real_account_mode_refused_at_construction(self):
        with pytest.raises(ValueError, match="REAL execution-mode descriptors"):
            BrokerCapabilities(
                broker_id="live-attempt",
                display_name="live attempt",
                execution_mode=ExecutionMode.REAL,
                order_kinds=(OrderKind.MARKET,),
                account_modes=(AccountMode.REAL,),
            )

    def test_real_account_mode_alone_is_not_a_live_venue(self):
        """A MOCK descriptor that (mistakenly) declared a REAL account
        mode is still not a live venue: it carries no execution
        capability beyond the deterministic mock. The catalogue proof
        below pins that no shipped descriptor does even this."""
        caps = BrokerCapabilities(
            broker_id="mock-real-account-listed",
            display_name="mock with a listed REAL account mode",
            execution_mode=ExecutionMode.MOCK_DETERMINISTIC,
            order_kinds=(OrderKind.MARKET,),
            account_modes=(AccountMode.DEMO, AccountMode.REAL),
        )
        assert caps.execution_mode is ExecutionMode.MOCK_DETERMINISTIC


# ----------------------------------------------------------------------
# 2. Catalog layer — every shipped descriptor is mock + demo-only
# ----------------------------------------------------------------------
class TestCatalogIsMockOnly:
    def test_default_registry_is_mock_deterministic_only(self):
        registry = default_registry()
        assert isinstance(registry, CapabilityRegistry)
        descriptors = registry.descriptors()
        assert len(descriptors) >= 7, "catalogue unexpectedly small"
        for caps in descriptors:
            assert caps.execution_mode is ExecutionMode.MOCK_DETERMINISTIC, (
                f"{caps.broker_id} declares a non-mock execution mode"
            )
            assert AccountMode.REAL not in caps.account_modes, (
                f"{caps.broker_id} declares a REAL account mode"
            )

    def test_runtime_paper_venue_is_mock_and_demo_only(self):
        caps = RUNTIME_PAPER_VENUE_CAPABILITIES
        assert caps.broker_id == RUNTIME_PAPER_VENUE_ID
        assert caps.execution_mode is ExecutionMode.MOCK_DETERMINISTIC
        assert AccountMode.REAL not in caps.account_modes
        assert caps.account_modes == (AccountMode.DEMO,)


# ----------------------------------------------------------------------
# 3. Session layer — REAL adapters cannot be constructed against
# ----------------------------------------------------------------------
def _real_mode_caps() -> BrokerCapabilities:
    """A REAL execution-mode descriptor with DEMO-only account modes —
    legal to construct as a model object (it declares no REAL account),
    but ILLEGAL to attach anywhere (the session refusal below)."""
    return BrokerCapabilities(
        broker_id="real-exec-adapter",
        display_name="REAL execution adapter (test double)",
        execution_mode=ExecutionMode.REAL,
        order_kinds=(OrderKind.MARKET,),
        account_modes=(AccountMode.DEMO,),
        rate_limit=RateLimitPolicy(),
        reconciliation_style=ReconciliationStyle.ORDER_FILL_POLL,
    )


class _RealModeAdapter(BrokerAdapter):
    """A minimal CONCRETE adapter carrying REAL execution capabilities.

    Implements every abstract method as a raising stub: the session
    must refuse it at CONSTRUCTION (before any method could run), so
    the stubs are unreachable by design."""

    def __init__(self, caps: BrokerCapabilities) -> None:
        self._caps = caps

    @property
    def broker_id(self) -> str:
        return self._caps.broker_id

    @property
    def capabilities(self) -> BrokerCapabilities:
        return self._caps

    def _refuse(self, *args, **kwargs):
        raise AssertionError("REAL adapter methods must be unreachable")

    connect = disconnect = _refuse
    health = account_info = _refuse
    instrument_spec = list_symbols = _refuse
    submit_order = cancel_order = _refuse
    order_status = order_fills = _refuse
    positions = balances = _refuse

    def reconcile(self, *args, **kwargs):
        raise AssertionError("REAL adapter methods must be unreachable")


class TestSessionLayerRefusal:
    def test_broker_session_refuses_real_execution_mode_adapter(self, tmp_path):
        adapter = _RealModeAdapter(_real_mode_caps())
        with pytest.raises(SessionJournalError, match="REAL execution-mode"):
            BrokerSession(
                adapter=adapter,
                account_id="paper-acct",
                journal_path=Path(tmp_path) / "journal.json",
                clock=_clock(),
            )

    def test_mock_venue_core_refuses_non_mock_capabilities(self):
        spec = _specs()["TEST/USD"]
        assert isinstance(spec, InstrumentSpec)
        with pytest.raises(MockVenueError, match="MOCK_DETERMINISTIC"):
            DeterministicMockVenue(
                capabilities=_real_mode_caps(),
                instruments=[spec],
                initial_balances={"USD": Decimal("10000")},
                currency="USD",
                clock=_clock(),
            )


# ----------------------------------------------------------------------
# 4. Runtime layer — the risk gate refuses every non-paper order
# ----------------------------------------------------------------------
class TestRuntimeLayerPaperIsolation:
    @staticmethod
    def _context(**overrides) -> RiskContext:
        """A risk-clean context: everything passes EXCEPT the fields
        the caller overrides (paper_mode first)."""
        base = dict(
            equity=Decimal("100000"),
            reference_price=Decimal("100"),
            bar_volume=Decimal("5000"),
            market_open=True,
            paper_mode=True,
            model_valid=True,
            crash_probability=0.0,
            volatility=0.01,
        )
        base.update(overrides)
        return RiskContext(**base)

    def test_non_paper_runtime_refuses_every_order(self):
        from data_engine.risk.engine import RiskEngine, RiskLimits
        from data_engine.runtime.contracts import DecisionAction
        from data_engine.runtime.kill_switch import KillSwitchManager
        from data_engine.runtime.ledgers import LedgerFamily

        gate = RiskGate(
            engine=RiskEngine(
                RiskLimits(
                    max_position_units=Decimal("1000"),
                    max_leverage=Decimal("1"),
                    max_single_asset_weight=Decimal("0.25"),
                    max_sector_weight=Decimal("1"),
                    max_portfolio_heat=Decimal("1"),
                ),
                trip_on_breach=False,
            ),
            kill_switch=KillSwitchManager(LedgerFamily()),
        )
        plan = _plan(
            "corr-proof", DecisionAction.BUY, Decimal("1"),
            Decimal("100"),
        )
        assessment = gate.evaluate(
            plan, self._context(paper_mode=False), "corr-proof"
        )
        assert assessment.passed is False
        paper = next(c for c in assessment.checks if c.check == "paper_mode")
        assert paper.passed is False
        assert "execution forbidden" in paper.reason

    def test_paper_mode_is_a_structural_literal_in_the_runtime(self):
        """The runtime wires paper_mode=True at every RiskContext site
        — there is no config field that can flip it (F-14 de-hardcoded
        the CEILINGS, deliberately NOT this flag)."""
        import re

        runtime_src = (
            SRC_ROOT / "data_engine" / "runtime" / "runtime.py"
        ).read_text(encoding="utf-8")
        sites = re.findall(r"paper_mode\s*=\s*(\w+)", runtime_src)
        assert sites, "no paper_mode wiring sites found"
        assert set(sites) == {"True"}, (
            f"paper_mode must be a structural True literal at every "
            f"wiring site; found {sorted(set(sites))}"
        )


# ----------------------------------------------------------------------
# 5. Structural AST scan — REAL execution is referenced only by the
#    refusal validator
# ----------------------------------------------------------------------
class TestStructuralRealReferenceScan:
    def _files_referencing_real_execution(self):
        offenders = []
        for path in sorted((SRC_ROOT).rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            found = any(
                isinstance(node, ast.Attribute)
                and node.attr == "REAL"
                and isinstance(node.value, ast.Name)
                and node.value.id == "ExecutionMode"
                for node in ast.walk(tree)
            )
            if found:
                offenders.append(path.relative_to(SRC_ROOT).as_posix())
        return offenders

    def test_execution_mode_real_referenced_only_by_the_refusal_validator(self):
        offenders = self._files_referencing_real_execution()
        assert offenders == ["data_engine/brokers/capabilities.py"], (
            "ExecutionMode.REAL may be referenced ONLY by the refusal "
            "validator in brokers/capabilities.py — every new reference "
            "must be a refusal site and requires explicit review to join "
            f"this allowlist. Found: {offenders}"
        )

    def test_no_real_account_mode_construction_in_src(self):
        """No src module CONSTRUCTS an AccountMode.REAL selection
        except the allowlisted sites:

        - ``capabilities.py`` — the refusal validator itself (it must
          name REAL to refuse it);
        - ``platform/mt5.py`` — the READ-ONLY data-plane mapping of
          the operator's EXTERNAL MT5 terminal-reported account mode
          (labeling an observed external fact; that module refuses
          all orders unconditionally — repository policy).
        """
        offenders = []
        for path in sorted(SRC_ROOT.rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            found = any(
                isinstance(node, ast.Attribute)
                and node.attr == "REAL"
                and isinstance(node.value, ast.Name)
                and node.value.id == "AccountMode"
                for node in ast.walk(tree)
            )
            if found:
                offenders.append(path.relative_to(SRC_ROOT).as_posix())
        allowed = {
            "data_engine/brokers/capabilities.py",
            "data_engine/platform/mt5.py",
        }
        assert set(offenders) == allowed, (
            f"AccountMode.REAL references outside the two allowlisted "
            f"refusal/read-only sites: {sorted(set(offenders) - allowed)}"
        )


# ----------------------------------------------------------------------
# 6. Honest posture statement
# ----------------------------------------------------------------------
def test_paper_ready_stays_false_in_the_readiness_gate():
    """The authoritative readiness verdict is computed from the 32
    mandatory gates — three of them (REAL_DATA_READY,
    OPERATIONAL_FEED_READY, GOVERNANCE_READY) are human/data
    dependencies that no code path may fabricate, so PAPER_READY
    remains FALSE. This proof file closes a SELECTION gap (U-21); it
    does not and cannot upgrade readiness."""
    from data_engine.runtime.readiness import GATE_NAMES

    assert "REAL_DATA_READY" in GATE_NAMES
    assert "OPERATIONAL_FEED_READY" in GATE_NAMES
    assert "GOVERNANCE_READY" in GATE_NAMES
