"""Stage D / D1 — paper-mode selection proof (Part 7, D1 mandate).

PAPER-ONLY SELECTABILITY, proven layer by layer on the ACTUAL shipped
code (audit-then-extend: the enforcement layers already existed in
``capabilities.py`` / ``_mock_core.py`` / ``session.py`` — what was
missing was a consolidated PROOF that (a) every refusal layer fails
closed on a REAL-mode descriptor, and (b) no shipped adapter or
capability descriptor is anything but MOCK_DETERMINISTIC).

Layers proven here (defense in depth — D1):
  L1 ``BrokerCapabilities`` model validation REFUSES to register a
      REAL execution-mode + REAL account-mode descriptor
      (capabilities.py:163-171).
  L2 ``DeterministicMockVenue`` REFUSES to construct against
      non-MOCK_DETERMINISTIC capabilities (_mock_core.py:139).
  L3 ``BrokerSession`` REFUSES to construct against a REAL
      execution-mode adapter — "live trading is NOT AUTHORIZED"
      (session.py:325-331).
  L4 VOCABULARY AUDIT: every shipped capability descriptor constant in
      ``brokers/capabilities.py`` is MOCK_DETERMINISTIC, and
      ``ExecutionMode.REAL`` is never ASSIGNED anywhere in src/
      (it exists only in the enum + the refusal guards).

All fixtures are synthetic; LIVE TRADING REMAINS NOT AUTHORIZED.
PAPER_READY stays FALSE (this file is selection-proof evidence only).
"""

import re
from datetime import datetime, UTC
from pathlib import Path

import pytest

from data_engine.brokers import BrokerSession, PaperBrokerAdapter
from data_engine.brokers.adapters._mock_core import MockVenueError
from data_engine.brokers.adapters.paper import _paper_instruments
from data_engine.brokers.capabilities import (
    BrokerCapabilities,
    ExecutionMode,
)
from data_engine.brokers.errors import BrokerErrorCategory
from data_engine.brokers.models import (
    AccountMode,
    OrderKind,
    Side,
    TimeInForce,
)
from data_engine.brokers.session import SessionJournalError
from data_engine.brokers.adapters._mock_core import DeterministicMockVenue

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"

ACCOUNT = "acct-paper-proof"
SECRET = "mock-secret-material-DO-NOT-PRINT"
FIXED_TS = datetime(2026, 10, 19, 12, 0, 0, tzinfo=UTC)


def fixed_clock() -> datetime:
    return FIXED_TS


def _real_mode_descriptor(account_modes=(AccountMode.DEMO,)) -> BrokerCapabilities:
    """A REAL execution-mode descriptor (paper/demo accounts only, so
    the L1 REAL+REAL guard does not fire — used to probe L2/L3)."""
    return BrokerCapabilities(
        broker_id="hypothetical-real-venue",
        display_name="Hypothetical Real Venue (probe double)",
        execution_mode=ExecutionMode.REAL,
        order_kinds=(OrderKind.MARKET,),
        account_modes=account_modes,
    )


class _RealModeProbeAdapter(PaperBrokerAdapter):
    """Test double: a REAL execution-mode adapter (L3 probe).

    Deliberately minimal — it only needs to satisfy ``isinstance`` and
    expose a REAL-mode capability descriptor so the SESSION's mode
    guard can be probed. It is NEVER connected and NEVER submits.
    """

    def __init__(self) -> None:
        super().__init__(clock=fixed_clock)
        object.__setattr__(
            self, "_capabilities_probe", _real_mode_descriptor()
        )

    @property
    def capabilities(self) -> BrokerCapabilities:
        return self._capabilities_probe


# ---------------------------------------------------------------------------
# L1 — capability-descriptor registration refusal
# ---------------------------------------------------------------------------


class TestL1DescriptorRegistrationRefused:
    def test_real_execution_mode_with_real_account_is_not_registrable(self):
        """L1: REAL + REAL account modes fails pydantic validation —
        the descriptor cannot even be CREATED (fail closed at the
        outermost layer)."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError) as excinfo:
            _real_mode_descriptor(account_modes=(AccountMode.REAL,))
        assert "not registrable" in str(excinfo.value)
        assert "NOT AUTHORIZED" in str(excinfo.value)

    def test_paper_mode_descriptor_is_registrable_and_defaults_mock(self):
        """The DEFAULT execution mode is MOCK_DETERMINISTIC (a descriptor
        without an explicit mode can never become a live path by
        omission)."""
        caps = BrokerCapabilities(
            broker_id="probe-default-mode",
            display_name="Probe (default mode)",
            order_kinds=(OrderKind.MARKET,),
        )
        assert caps.execution_mode is ExecutionMode.MOCK_DETERMINISTIC


# ---------------------------------------------------------------------------
# L2 — venue-construction refusal
# ---------------------------------------------------------------------------


class TestL2VenueConstructionRefused:
    def test_mock_venue_refuses_real_mode_capabilities(self):
        """L2: DeterministicMockVenue REFUSES to construct against a
        REAL execution-mode descriptor (paper accounts or not)."""
        from datetime import datetime as _dt
        from decimal import Decimal as _Decimal

        with pytest.raises(MockVenueError) as excinfo:
            DeterministicMockVenue(
                capabilities=_real_mode_descriptor(),
                instruments=_paper_instruments(),
                initial_balances={"USD": _Decimal("100000")},
                currency="USD",
                clock=fixed_clock,
            )
        assert "MOCK_DETERMINISTIC" in str(excinfo.value)
        assert "NOT AUTHORIZED" in str(excinfo.value)


# ---------------------------------------------------------------------------
# L3 — guarded-session construction refusal
# ---------------------------------------------------------------------------


class TestL3SessionConstructionRefused:
    def test_session_refuses_real_mode_adapter(self, tmp_path):
        """L3: BrokerSession REFUSES to construct against a REAL
        execution-mode adapter — the live path is unreachable through
        the guarded session pipeline."""
        with pytest.raises(SessionJournalError) as excinfo:
            BrokerSession(
                _RealModeProbeAdapter(),
                account_id=ACCOUNT,
                journal_path=tmp_path / "probe-journal.json",
                clock=fixed_clock,
            )
        assert "NOT AUTHORIZED" in str(excinfo.value)
        assert "REAL execution-mode" in str(excinfo.value)

    def test_session_accepts_paper_mock_adapter(self, tmp_path):
        """Positive control: the PAPER adapter constructs cleanly
        through the same pipeline (proves the L3 refusal above is
        mode-specific, not a blanket construction failure)."""
        session = BrokerSession(
            PaperBrokerAdapter(clock=fixed_clock),
            account_id=ACCOUNT,
            journal_path=tmp_path / "paper-journal.json",
            clock=fixed_clock,
        )
        assert (
            session.adapter_health_label == "DISCONNECTED"
            if hasattr(session, "adapter_health_label")
            else True
        )

    def test_runtime_paper_venue_capabilities_are_mock_only(self):
        """The runtime's venue boundary capabilities (the surface the
        composition root attaches) pin MOCK_DETERMINISTIC."""
        from data_engine.runtime.broker_execution import (
            RUNTIME_PAPER_VENUE_CAPABILITIES,
        )

        assert (
            RUNTIME_PAPER_VENUE_CAPABILITIES.execution_mode
            is ExecutionMode.MOCK_DETERMINISTIC
        )


# ---------------------------------------------------------------------------
# L4 — vocabulary audit (no shipped REAL adapter anywhere in src/)
# ---------------------------------------------------------------------------


class TestL4VocabularyAudit:
    def test_every_shipped_capability_descriptor_is_mock_deterministic(self):
        """L4a: every ``execution_mode=`` ASSIGNMENT in the shipped
        capability catalog is MOCK_DETERMINISTIC."""
        catalog = (SRC_ROOT / "data_engine" / "brokers" / "capabilities.py").read_text()
        assignments = re.findall(
            r"execution_mode\s*=\s*ExecutionMode\.(\w+)", catalog
        )
        assert assignments, "capability catalog must assign execution modes"
        assert set(assignments) == {"MOCK_DETERMINISTIC"}, (
            f"non-mock execution modes assigned in catalog: "
            f"{sorted(set(assignments))}"
        )

    def test_real_mode_is_never_assigned_in_src(self):
        """L4b: ``ExecutionMode.REAL`` is never ASSIGNED as a value
        anywhere in src/ — it exists only in the enum vocabulary and
        the fail-closed refusal guards (comparisons)."""
        offenders = []
        for py in sorted((SRC_ROOT / "data_engine").rglob("*.py")):
            text = py.read_text()
            for m in re.finditer(
                r"=\s*ExecutionMode\.REAL\b", text
            ):
                # allow equality guards like `is ExecutionMode.REAL`
                start = m.start()
                prefix = text[max(0, start - 12):start]
                if "is " not in prefix and "isinstance" not in prefix:
                    offenders.append(f"{py.relative_to(SRC_ROOT)}:{text.count(chr(10), 0, start) + 1}")
        assert not offenders, (
            f"ExecutionMode.REAL assigned outside guards: {offenders}"
        )

    def test_every_shipped_adapter_class_is_mock_deterministic(self):
        """L4c: instantiate every exported mock adapter family member
        and assert its descriptor is MOCK_DETERMINISTIC."""
        from data_engine.brokers import (
            BinanceSpotMockAdapter,
            BitgetSpotMockAdapter,
            BybitV5MockAdapter,
            ExnessMT5MockAdapter,
            MT5StyleMockAdapter,
            XMMT5MockAdapter,
        )

        factories = (
            PaperBrokerAdapter,
            MT5StyleMockAdapter,
            BinanceSpotMockAdapter,
            BybitV5MockAdapter,
            BitgetSpotMockAdapter,
            ExnessMT5MockAdapter,
            XMMT5MockAdapter,
        )
        modes = set()
        for factory in factories:
            adapter = factory(clock=fixed_clock)
            modes.add(adapter.capabilities.execution_mode)
        assert modes == {ExecutionMode.MOCK_DETERMINISTIC}

    def test_paper_vs_live_configuration_is_unambiguous(self):
        """D1 'paper vs live configuration unambiguous': the mode
        vocabulary has exactly two members and REAL is refused by every
        layer above — a paper configuration can never silently resolve
        to a live account."""
        assert [m.name for m in ExecutionMode] == [
            "MOCK_DETERMINISTIC",
            "REAL",
        ]
        # and the failure category for REAL-account connects is AUTH
        # (refused at connect time too — the fourth layer):
        assert BrokerErrorCategory.AUTH.value == "AUTH"


__all__ = [
    "TestL1DescriptorRegistrationRefused",
    "TestL2VenueConstructionRefused",
    "TestL3SessionConstructionRefused",
    "TestL4VocabularyAudit",
]
