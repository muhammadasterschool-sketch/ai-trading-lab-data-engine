"""Authoritative TradingRuntime — the ONE orchestration path
(pre-paper mandate §24; RT-F1/RT-F2/RT-F3/RT-F4 closures).

    DataFeed → DataValidator → PITGate → FeatureEngine →
    SequenceBuilder → PredictionEngine(Ensemble) → Calibration →
    Uncertainty → Regime → CrashRisk → PortfolioState →
    DecisionEngine → PositionSizer → TradePlan → RiskEngine →
    KillSwitch → OMS → PaperExecutionGateway → Fill →
    PositionState → Reconciliation → Ledgers → Memory → Monitoring

Guarantees:

- **No alternate production path**: every order flows through
  ``_execute_plan`` (create → validate → risk-approve → submit →
  execute → fills); the OMS refuses risk approval without a PASSING
  gate assessment (RT-F1 structural), reconciliation runs after
  fills (RT-F2), every transition is ledgered (RT-F3), and state
  snapshots persist when a store is configured (RT-F4).
- **Fail-closed operating states**: INIT/RUNNING/DEGRADED/
  RECONCILIATION_REQUIRED/RECOVERY_REQUIRED/EXECUTION_UNCERTAIN/
  HALTED — trading only happens in RUNNING.
- **PIT**: each bar's prediction uses a sequence built with cutoff =
  that bar's close timestamp; nothing after the anchor enters
  features (sequence engine enforces).
- **Crash independence (§20)**: crash probability is computed from
  volatility/drawdown/disagreement stress — NEVER from the
  directional signal — and can force NO_TRADE/exit regardless of
  strategy opinion.
- Determinism: bar processing is a pure function of
  (config, models, bar history) — replayable (mandate §49).
"""

import math
import time
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, field_validator

from data_engine.paper.simulator import ExecutionRealism
from data_engine.prediction.regimes import RegimeEngine, RegimeFeatures
from data_engine.risk.engine import RiskEngine, RiskLimits
from data_engine.runtime.contracts import (
    Decision,
    DecisionAction,
    ExitReason,
    MemoryCategory,
    OrderLifecycle,
    PredictionArtifact,
    RuntimeState,
    RuntimeContractError,
    TradePlan,
    UncertaintyReport,
    NON_TRADING_STATES,
)
from data_engine.runtime.data_gate import validate_bars
from data_engine.runtime.decision import (
    DecisionEngine,
    MarketDataStatus,
    DecisionThresholds,
)
from data_engine.runtime.execution import PaperExecutionAdapter, RuntimeFill
from data_engine.runtime.exits import ExitManager
from data_engine.runtime.identity import (
    RUNTIME_CONTRACT_VERSION,
    prefixed_hash,
)
from data_engine.runtime.kill_switch import (
    KillSwitchActive,
    KillSwitchManager,
    KillSwitchScope,
)
from data_engine.runtime.ledgers import LedgerError, LedgerFamily
from data_engine.runtime.memory import MemoryError, TradingMemory
from data_engine.runtime.metrics import RuntimeMetrics
from data_engine.runtime.oms import OMS, OMSOrder
from data_engine.runtime.pnl import PnLEngine, PositionState
from data_engine.runtime.readiness import (
    GateEvidence,
    PaperReadinessGate,
    ReadinessReport,
)
from data_engine.runtime.reconciliation import RuntimeReconciliation
from data_engine.runtime.risk_gate import (
    GateCeilings,
    GateContextDefaults,
    RiskContext,
    RiskGate,
    RuntimeRiskLimits,
)
from data_engine.runtime.rl import (
    GovernedRLPolicy,
    RLGovernanceError,
    RLObservation,
)
from data_engine.runtime.sequence import (
    SequenceSpec,
    build_sequence_set,
)
from data_engine.runtime.submission_ledger import (
    CapacityRefused as _LedgerCapacityRefused,
    SubmissionLedger,
)
from data_engine.runtime.state import (
    EXECUTION_STATE_FIELDS,
    EXECUTION_STATE_SCHEMA_VERSION,
    ExecutionStateStore,
    StateStoreError,
    validate_execution_state,
)
from data_engine.runtime.trade_plan import SizingConfig, TradePlanBuilder


class RuntimeConfig(BaseModel):
    """Governed runtime configuration (fail-closed defaults)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    timeframe: str
    session_id: str
    initial_equity: Decimal
    expected_interval_seconds: float = 300.0
    lookback: int = 8
    horizon: int = 2
    stride: int = 1
    feature_version: str = "fv-seq-1"
    dataset_version: str = "dv-synthetic"
    ttl_bars: int = 3
    max_crash_probability: float = 0.20
    crash_exit_probability: float = 0.40
    max_position_units: Decimal = Decimal("100")
    risk_fraction: Decimal = Decimal("0.01")
    #: RUN-DD-1: ACCOUNT-equity drawdown limit — the maximum
    #: tolerated decline of mark-to-market account equity from the
    #: session high-water mark (default 20%). A STRICT breach
    #: trips the ACCOUNT kill switch (terminal HALT, auditable
    #: source ``runtime.risk.drawdown``, persists immediately per
    #: BLOCKER 12) and the mandatory ``account_drawdown`` risk-gate
    #: check refuses new entry orders; closing/reducing orders stay
    #: permitted (the limit blocks new exposure, not risk
    #: reduction). Equality is IN limit: only a strict breach
    #: trips (consistent with the drawdown/loss_limit checks).
    max_account_drawdown_fraction: float = 0.20
    #: BLOCKER 1: explicit non-operational marking. When True the
    #: runtime is a UNIT-TEST FIXTURE — persistence and the paper
    #: readiness gate are skipped and every start is ledgered as
    #: EPHEMERAL_TEST_FIXTURE. A normal (operational) paper session
    #: NEVER sets this: fail-closed defaults keep it False.
    ephemeral_test_fixture: bool = False
    #: BLOCKER 21: operator-pinned model artifact hashes. When
    #: non-empty, EVERY ensemble member's model_hash must be listed —
    #: a swapped/tampered model is refused at startup (never silently
    #: loaded).
    pinned_model_hashes: tuple = ()
    #: RUN-ST-1: in-session wall-clock feed watchdog limit. When
    #: None (the DEFAULT) the watchdog is DISABLED — the runtime's
    #: documented default posture is deterministic bar replay, where
    #: historical bar timestamps are legitimately far behind the
    #: wall clock. An operational live-clock paper session opts IN
    #: with an explicit positive limit (seconds): a bar whose
    #: wall-clock age STRICTLY exceeds the limit is still admitted
    #: (fills/TTL/drawdown/protection/persistence continue) but the
    #: prediction/decision/entry chain is SKIPPED — new exposure is
    #: refused, fail closed, until the feed catches up.
    #: ``StrictInt`` (a bool limit is a configuration bug, never a
    #: legitimate 1-second watchdog).
    max_feed_staleness_seconds: Optional[StrictInt] = None
    #: Snapshot config compatibility (§0H limitation): config-schema
    #: evolution changes the identity digest of an UNCHANGED session
    #: (the digest covers the full config dump). A snapshot whose
    #: digest decomposes EXACTLY into the documented evolution
    #: (see ``SNAPSHOT_CONFIG_EVOLUTION``) refuses restart by
    #: DEFAULT with a precise message; setting this flag True is the
    #: explicit operator opt-in that resumes the session and ledgers
    #: ``SNAPSHOT_CONFIG_EVOLVED`` loudly. Any SHARED-field value
    #: change still refuses regardless of this flag.
    #: ``StrictBool`` (a coerced "yes"/1.5 is never an opt-in).
    allow_snapshot_config_evolution: StrictBool = False

    @field_validator("symbol", "timeframe", "session_id",
                     "feature_version", "dataset_version")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise RuntimeContractError("config text fields must be non-empty")
        return v.strip()

    @field_validator("initial_equity")
    @classmethod
    def _validate_equity(cls, v: Decimal) -> Decimal:
        if v is None or not v.is_finite() or v <= 0:
            raise RuntimeContractError("initial equity must be positive")
        return v

    @field_validator("max_account_drawdown_fraction")
    @classmethod
    def _validate_drawdown_limit(cls, v: float) -> float:
        if (
            not isinstance(v, (int, float))
            or isinstance(v, bool)
            or not math.isfinite(v)
            or not (0 < v <= 1)
        ):
            raise RuntimeContractError(
                "max_account_drawdown_fraction must be a finite "
                "fraction in (0, 1] (fail closed)"
            )
        return float(v)

    @field_validator("lookback", "horizon", "stride", "ttl_bars")
    @classmethod
    def _validate_windows(cls, v: int) -> int:
        if not isinstance(v, int) or v < 1:
            raise RuntimeContractError("window ints must be >= 1")
        return v

    @field_validator("pinned_model_hashes")
    @classmethod
    def _validate_pins(cls, v) -> tuple:
        v = tuple(v or ())
        for item in v:
            if not isinstance(item, str) or not item.strip():
                raise RuntimeContractError(
                    "pinned_model_hashes entries must be non-empty "
                    "model hash strings"
                )
        return v

    @field_validator("max_feed_staleness_seconds")
    @classmethod
    def _validate_feed_staleness(cls, v):
        if v is None:
            return None
        if v < 1:
            raise RuntimeContractError(
                "max_feed_staleness_seconds must be None (watchdog "
                "disabled — deterministic replay) or an int >= 1 "
                "second (fail closed)"
            )
        return int(v)


#: Regime vocabulary mapping (prediction RegimeEngine → mandate §19
#: governed states). Documented, deterministic, total.
_REGIME_MAP = {
    "CRISIS": "CRASH",
    "STRESSED": "STRESSED",
    "HIGH_VOLATILITY": "HIGH_VOLATILITY",
    "LOW_VOLATILITY": "LOW_VOLATILITY",
    "TRANSITION": "RECOVERY",
    "TRENDING": "TRENDING",
    "RANGE": "RANGING",
    "RISK_ON": "TRENDING",
    "RISK_OFF": "STRESSED",
    "NORMAL": "RANGING",
    "UNKNOWN": "UNKNOWN",
}


#: Snapshot config-schema evolution registry (Batch 6, snapshot
#: compatibility). ORDERED — each entry is one RuntimeConfig field
#: added AFTER the config-digest formula went live, with the
#: documentation section that introduced it. The runtime's identity
#: digest covers the FULL config dump, so a schema addition changes
#: the digest of an otherwise-unchanged session; this registry lets
#: recovery distinguish "known additive evolution" (exact legacy
#: digest recomputation / persisted config view — resumable under
#: the explicit operator opt-in, ledgered loudly) from a true
#: identity change (any SHARED-field value difference — always
#: refused). FUTURE config additions MUST be appended here with
#: their section marker, or restarts of pre-addition snapshots will
#: correctly-but-opaquely refuse.
SNAPSHOT_CONFIG_EVOLUTION = (
    ("0H", "max_account_drawdown_fraction"),
    ("0L", "max_feed_staleness_seconds"),
    ("0L", "allow_snapshot_config_evolution"),
)

#: Field names of :data:`SNAPSHOT_CONFIG_EVOLUTION` (order-aware).
_EVOLUTION_FIELDS = tuple(f for _, f in SNAPSHOT_CONFIG_EVOLUTION)


def _config_digest(config_view: Mapping) -> str:
    """The identity digest of a config view (BLOCKER 21).

    Pure function of the declared config fields — the SAME formula
    since the digest went live (never changed, so digests computed
    by any historical code version remain reproducible).
    """
    return prefixed_hash(
        "rtcfg.",
        {
            "kind": "runtime_config_identity",
            "config": dict(config_view),
        },
    )


class BarOutcome(BaseModel):
    """One processed bar's complete outcome (observability)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bar_index: int
    correlation_id: str
    timestamp: datetime
    accepted: bool
    quality_rejections: tuple = ()
    decision_action: str
    decision_reason: str
    prediction_probability: Optional[float] = None
    regime: str
    crash_probability: float
    orders_created: tuple = ()
    fills: tuple = ()
    exits: tuple = ()
    realized_pnl: str = "0"
    unrealized_pnl: str = "0"
    runtime_state: str
    risk_failed_checks: tuple = ()


class TradingRuntime:
    """The authoritative paper trading runtime (mandate §24)."""

    def __init__(
        self,
        config: RuntimeConfig,
        ensemble,
        calibrator=None,
        state_store: Optional[ExecutionStateStore] = None,
        realism: Optional[ExecutionRealism] = None,
        readiness_gate: Optional[PaperReadinessGate] = None,
        rl_policy: Optional[GovernedRLPolicy] = None,
        mac_custody=None,
        wall_clock=None,
        risk_limits: Optional[RuntimeRiskLimits] = None,
        submission_ledger: Optional["SubmissionLedger"] = None,
        portfolio_limits: Optional[RiskLimits] = None,
        gate_ceilings: Optional[GateCeilings] = None,
        gate_context: Optional[GateContextDefaults] = None,
    ) -> None:
        if config is None or ensemble is None:
            raise RuntimeContractError(
                "runtime requires config + fitted ensemble"
            )
        # Milestone A B1: durable submission ledger (opt-in here; the
        # Stage C composition root makes it MANDATORY for operational
        # deployments). When attached, it is THE authoritative rate
        # accounting (the volatile in-memory list is bypassed).
        if submission_ledger is not None and not isinstance(
            submission_ledger, SubmissionLedger
        ):
            raise RuntimeContractError(
                "submission_ledger must be a SubmissionLedger "
                "(durable, flock-protected rate accounting)"
            )
        self._submission_ledger = submission_ledger
        self._config = config
        self._ensemble = ensemble
        self._calibrator = calibrator
        self._store = state_store
        self._readiness_gate = readiness_gate
        # Stage C (F-14): config-injected portfolio limits / gate
        # ceilings / gate context. None keeps the legacy provisional
        # wiring below (backward compatible for the deterministic
        # replay fixtures); the OPERATIONAL composition root always
        # injects explicit values from validated config (test-pinned:
        # composed runtime carries the CONFIG objects by identity).
        if portfolio_limits is not None and not isinstance(
            portfolio_limits, RiskLimits
        ):
            raise RuntimeContractError(
                "portfolio_limits must be a risk.engine.RiskLimits "
                "(config-injected portfolio risk limits — F-14)"
            )
        if gate_ceilings is not None and not isinstance(
            gate_ceilings, GateCeilings
        ):
            raise RuntimeContractError(
                "gate_ceilings must be a GateCeilings (config-injected "
                "volatility/spread ceilings — F-14)"
            )
        if gate_context is not None and not isinstance(
            gate_context, GateContextDefaults
        ):
            raise RuntimeContractError(
                "gate_context must be a GateContextDefaults "
                "(config-injected market/model context — F-14)"
            )
        self._portfolio_limits_injected = portfolio_limits
        self._gate_ceilings = gate_ceilings or GateCeilings()
        self._gate_context = gate_context or GateContextDefaults()
        # Governed RL advisor (mandate §28/§44): DISABLED by default —
        # None means the RL layer is not part of this session. When
        # enabled it is ADVISORY-ONLY: proposals are recorded to the
        # decision ledger + memory; they have NO execution authority
        # (the Decision/Risk/KillSwitch/OMS chain disposes of every
        # bar independently of the proposal).
        if rl_policy is not None and not isinstance(rl_policy, GovernedRLPolicy):
            raise RuntimeContractError(
                "rl_policy must be a GovernedRLPolicy (advisor-only contract)"
            )
        self._rl_policy = rl_policy
        # Runtime observability (mandate §26): deterministic counters
        # + UNHASHED wall-clock latency gauges (INV-01: gauges are
        # observability, never identity; metrics are never persisted).
        self._metrics = RuntimeMetrics()
        self._realism = realism or ExecutionRealism(
            half_spread=Decimal("0.02"),
            commission_per_unit=Decimal("0.001"),
            impact_rate=Decimal("0.0001"),
            participation_cap=Decimal("0.35"),
            fill_lag_bars=1,
        )

        # --- authoritative component wiring (§24) -----------------------
        # Keyed-MAC ledger custody (operator mandate 2026-10-10 §1.5):
        # None = legacy unkeyed chains (backward compatible); a wired
        # MacCustody signs every ledger event HMAC-SHA256 and STRICT
        # verification then refuses any unkeyed/downgraded event. The
        # custody reads the environment ONLY via its explicit
        # from_environment() provisioning channel — never implicitly.
        from data_engine.runtime.mac_custody import MacCustody
        if mac_custody is not None and not isinstance(mac_custody, MacCustody):
            raise RuntimeContractError(
                "mac_custody must be a MacCustody instance (keyed-MAC "
                "custody contract — operator mandate 2026-10-10 §1.5)"
            )
        self._mac_custody = mac_custody
        self._ledgers = LedgerFamily(mac_custody=mac_custody)
        self._oms = OMS(self._ledgers)
        self._kill_switch = KillSwitchManager(self._ledgers)
        # Stage C (F-14): injected portfolio limits win wholesale; the
        # fallback keeps the reconstruction D-6 provisional defaults
        # (owner-ratified for paper mode; provenance in GateCeilings/
        # composition.py). max_position_units stays config-sourced in
        # the fallback path exactly as before.
        limits = portfolio_limits if portfolio_limits is not None else RiskLimits(
            max_position_units=config.max_position_units,
            max_leverage=Decimal("1.0"),
            max_single_asset_weight=Decimal("0.30"),
            max_sector_weight=Decimal("1.0"),
            max_portfolio_heat=Decimal("1.0"),
        )
        self._risk_engine = RiskEngine(limits)
        self._risk_gate = RiskGate(self._risk_engine, self._kill_switch)
        # Reconstruction D-6: mandatory runtime order limits (order
        # submission rate + maximum open/unresolved orders). Provisional
        # paper-mode defaults; see RuntimeRiskLimits for honest provenance.
        self._risk_limits = risk_limits or RuntimeRiskLimits()
        # Submission-rate accounting on GOVERNED time (bar timestamps —
        # deterministic, replay-stable; wall clock only as fallback).
        self._submission_times: list = []
        self._execution = PaperExecutionAdapter(self._realism)
        self._exit_manager = ExitManager(self._ledgers)
        self._reconciliation = RuntimeReconciliation(self._ledgers)
        self._memory = TradingMemory()
        self._pnl_engine = PnLEngine()
        self._decision_engine = DecisionEngine(
            DecisionThresholds(max_crash_probability=config.max_crash_probability)
        )
        self._plan_builder = TradePlanBuilder(
            SizingConfig(
                risk_fraction=config.risk_fraction,
                max_position_units=config.max_position_units,
                default_ttl_bars=config.ttl_bars,
            )
        )
        self._regime_engine = RegimeEngine()

        # --- operating state ----------------------------------------------
        self._state = RuntimeState.INIT
        self._bars: list = []
        self._bar_index = -1
        self._positions: dict = {}
        self._consecutive_bad_bars = 0
        self._session_start_equity = config.initial_equity
        self._equity_realized = Decimal("0")
        self._started_at: Optional[datetime] = None
        # RUN-ST-1: injectable wall-clock seam for the in-session feed
        # watchdog. The DEFAULT is the real wall clock; tests (and only
        # tests) inject a deterministic clock. Wall-clock values are
        # OBSERVABILITY/gating inputs ONLY (INV-01 discipline): they
        # never enter identity hashes, ledger payloads or persisted
        # state — the watchdog's LEDGER payload carries only the
        # deterministic bar timestamp + configured limit.
        if wall_clock is not None and not callable(wall_clock):
            raise RuntimeContractError(
                "wall_clock must be a callable returning a timezone-aware "
                "datetime (watchdog seam, RUN-ST-1)"
            )
        self._wall_clock = wall_clock or (lambda: datetime.now(UTC))
        # Latency-aware pending-order bookkeeping: fills for orders
        # submitted on bar N happen on bars N+lag.. (never same-bar).
        self._order_fill_cursor: dict = {}   # order_id -> next bar index
        self._pending_protection: dict = {}  # order_id -> (sl, tp, corr)
        self._pending_exits: dict = {}       # symbol -> (order_id, reason, snapshot)
        self._restarted = False              # True after state restoration
        self._restored_runtime_state = None  # persisted operating state
        # Batch 6 (snapshot compat): pending evolution incident — set
        # during identity verification when the operator opted into an
        # evolved-config snapshot; recorded after ledger restoration.
        self._snapshot_config_evolved = None
        # PAPER-RUN-PNL-1: in-memory day-anchor memo (UTC date ->
        # day-start account equity). This is a PURE DETERMINISM CACHE —
        # the anchor is a pure function of persisted state (bars +
        # OMS fills) and is recomputed identically after restart; it
        # is therefore deliberately NOT part of the persisted
        # execution-state schema.
        self._day_anchor_cache = None
        # RUN-DD-1: in-memory high-water-mark memo —
        # (admitted-bar count, OMS-fill count) -> peak equity. PURE
        # DETERMINISM CACHE: the peak is a pure function of persisted
        # state (bars + OMS fills) and is replayed identically after a
        # restart; it is therefore deliberately NOT part of the
        # persisted execution-state schema (same discipline as the
        # day-anchor memo above).
        self._dd_peak_cache = None
        # Batch 5 (Phase M2 completion): the broker-neutral execution
        # venue bound to the AUTHORITATIVE order path. None = the
        # runtime's internal paper execution path (the default; zero
        # behavioural change). Bound ONLY via
        # ``attach_authoritative_paper_venue`` (the runtime-package
        # seam) — never directly.
        self._venue = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    @property
    def state(self) -> RuntimeState:
        return self._state

    @property
    def ledgers(self) -> LedgerFamily:
        return self._ledgers

    @property
    def oms(self) -> OMS:
        return self._oms

    @property
    def kill_switch(self) -> KillSwitchManager:
        return self._kill_switch

    @property
    def risk_gate(self) -> RiskGate:
        """The authoritative 22-check risk gate (Phase M2 integration
        seam — the broker-neutral session's injectable central risk
        gate binds to THIS instance, never a copy)."""
        return self._risk_gate

    @property
    def portfolio_limits(self) -> Optional[RiskLimits]:
        """Config-injected portfolio limits, or None when the legacy
        provisional wiring is in force (Stage C, F-14)."""
        return self._portfolio_limits_injected

    @property
    def gate_ceilings(self) -> GateCeilings:
        """The risk-gate ceilings in force (Stage C, F-14: injected by
        the operational composition root; defaults preserve the
        reconstruction D-6 provisional values)."""
        return self._gate_ceilings

    @property
    def gate_context(self) -> GateContextDefaults:
        """The gate context values in force (Stage C, F-14)."""
        return self._gate_context

    @property
    def memory(self) -> TradingMemory:
        return self._memory

    @property
    def metrics(self) -> RuntimeMetrics:
        """Runtime observability counters + latency gauges (§26)."""
        return self._metrics

    @property
    def rl_policy(self) -> Optional[GovernedRLPolicy]:
        """The governed RL advisor, or None when RL is DISABLED."""
        return self._rl_policy

    @property
    def positions(self) -> Mapping[str, PositionState]:
        return dict(self._positions)

    @property
    def config(self) -> RuntimeConfig:
        return self._config

    @property
    def venue(self):
        """The broker-neutral execution venue bound to the
        authoritative order path (None = the runtime's internal paper
        execution path — the default)."""
        return self._venue

    def _bind_authoritative_venue(self, venue) -> None:
        """Runtime-package seam: bind the authoritative venue (called
        ONLY by ``attach_authoritative_paper_venue`` after its
        fail-closed construction checks)."""
        if self._venue is not None:
            raise RuntimeContractError(
                "an authoritative venue is already bound to this runtime"
            )
        if venue is None:
            raise RuntimeContractError(
                "the authoritative venue seam cannot be None"
            )
        self._venue = venue

    def start(self) -> None:
        """INIT → RUNNING through the AUTHORITATIVE fail-closed chain.

        Operational mode (``ephemeral_test_fixture=False``, the
        default) requires EVERY gate before RUNNING is reachable:

        1. component self-check (ensemble non-empty, feature/dataset
           versions, pinned model hashes — BLOCKER 21);
        2. persistence check (state store present + self-check —
           BLOCKER 1: NO_STATE_STORE ⇒ BLOCKED, never RUNNING);
        3. paper readiness gate (ALL mandatory gates PASS — BLOCKER 2:
           one FALSE/absent gate ⇒ REFUSED);
        4. recovery check (existing state: LOAD → VERIFY → RESTORE →
           RECONCILE — BLOCKER 4: never INIT → RUNNING across a
           restart);
        5. kill-switch check (critical switch active ⇒ HALTED).

        Ephemeral test-fixture mode is the ONLY skip path, is
        explicitly marked in the config, and is ledgered loudly as
        EPHEMERAL_TEST_FIXTURE — a non-operational unit-test fixture,
        never a paper session.
        """
        if self._state is not RuntimeState.INIT:
            raise RuntimeContractError(
                f"runtime cannot start from {self._state.value}"
            )
        # -- 1. component self-checks ----------------------------------
        if not self._ensemble.members:
            raise RuntimeContractError("ensemble empty — refusing to start")
        for member in self._ensemble.members:
            art = member.artifact()
            if art.feature_version != self._config.feature_version:
                raise RuntimeContractError(
                    f"member {art.model_id} feature_version mismatch"
                )
            if art.dataset_version != self._config.dataset_version:
                raise RuntimeContractError(
                    f"member {art.model_id} dataset_version mismatch "
                    f"({art.dataset_version} != "
                    f"{self._config.dataset_version})"
                )
            if self._config.pinned_model_hashes and (
                art.model_hash not in self._config.pinned_model_hashes
            ):
                raise RuntimeContractError(
                    f"member {art.model_id} model_hash {art.model_hash} "
                    "is NOT pinned in RuntimeConfig.pinned_model_hashes — "
                    "refusing to run an unpinned/foreign model "
                    "(BLOCKER 21: never silently load another model)"
                )

        if self._config.ephemeral_test_fixture:
            # Explicitly-marked NON-OPERATIONAL unit-test fixture.
            self._state = RuntimeState.RUNNING
            self._started_at = datetime.now(UTC)
            self._ledgers.record(
                ledger="incident",
                event_type="EPHEMERAL_TEST_FIXTURE_STARTED",
                correlation_id=f"session:{self._config.session_id}",
                actor="runtime",
                payload={
                    "session_id": self._config.session_id,
                    "mode": "ephemeral_test_fixture",
                    "operational": False,
                    "note": "non-operational unit-test fixture — no "
                            "persistence, no readiness verdict; NOT a "
                            "paper trading session",
                },
            )
            return

        # -- 2. persistence is MANDATORY (BLOCKER 1) --------------------
        if self._store is None:
            raise RuntimeContractError(
                "START REFUSED — NO_STATE_STORE: an operational paper "
                "session requires an authoritative persistent "
                "ExecutionStateStore (fail closed: no persistence, no "
                "RUNNING)"
            )
        problems = self._store.self_check()
        if problems:
            self._state = RuntimeState.RECOVERY_REQUIRED
            raise RuntimeContractError(
                "START REFUSED — state store self-check FAILED: "
                + "; ".join(problems)
                + " (RECOVERY_REQUIRED)"
            )

        # -- 3. the paper readiness gate is AUTHORITATIVE (BLOCKER 2) --
        if self._readiness_gate is None:
            raise RuntimeContractError(
                "START REFUSED — no PaperReadinessGate wired: an "
                "operational paper session requires the authoritative "
                "gate with objective evidence for EVERY mandatory gate"
            )
        report = self._readiness_gate.evaluate()
        if not report.paper_ready:
            raise RuntimeContractError(
                "START REFUSED — paper readiness gate verdict is FALSE; "
                f"failed gates: {list(report.failed_gates)} "
                "(fail closed — no shortcut, no override)"
            )

        # -- 4. recovery: LOAD → VERIFY → RESTORE → RECONCILE ----------
        self._recover_existing_state()

        # Milestone A B1: conservative durable-ledger recovery —
        # outstanding reservations are reconstructed from the ledger
        # (journaled → SUBMITTED; unknown → PRESERVED/consumed).
        # Never silently releases risk capacity; every decision is
        # durable + auditable. (Venue-journal reconciliation of
        # reservations happens at venue attach — P3.)
        if self._submission_ledger is not None:
            ledger_report = self._submission_ledger.recover()
            self._ledgers.record(
                ledger="incident",
                event_type="SUBMISSION_LEDGER_RECOVERED",
                correlation_id=f"session:{self._config.session_id}",
                actor="runtime",
                payload={
                    "reconciled_submitted":
                        ledger_report.reconciled_submitted,
                    "preserved_reserved":
                        ledger_report.preserved_reserved,
                    "total_records": ledger_report.total_records,
                    "action": (
                        "durable submission ledger recovered "
                        "conservatively — outstanding reservations "
                        "stay consumed until venue truth resolves "
                        "them (fail closed)"
                    ),
                },
            )

        # A restart from a DEGRADED snapshot stays DEGRADED — data-
        # quality degradation is never cured by a restart (fail
        # closed; the bad-bar history is restored with it).
        if self._restored_runtime_state == "DEGRADED":
            self._state = RuntimeState.DEGRADED
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_RESUMED_DEGRADED",
                correlation_id=f"session:{self._config.session_id}",
                actor="runtime",
                payload={
                    "consecutive_bad_bars": self._consecutive_bad_bars,
                    "reason": "persisted runtime state was DEGRADED; "
                              "restart does not cure data-quality "
                              "degradation",
                },
            )
            return

        # -- 5. kill-switch check ----------------------------------------
        if self._kill_switch.any_critical_active():
            self._state = RuntimeState.HALTED
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_START_REFUSED_CRITICAL_SWITCH",
                correlation_id=f"session:{self._config.session_id}",
                actor="runtime",
                payload={"reason": "ACCOUNT/GLOBAL kill switch active "
                                  "— restart never clears a kill switch"},
            )
            raise RuntimeContractError(
                "START REFUSED — critical kill switch (ACCOUNT/GLOBAL) "
                "is active; a restart NEVER clears a kill switch "
                "(BLOCKER 12)"
            )

        # -- 5b. persisted HALTED is TERMINAL (RUN-HALT-1) ---------------
        # HALT is the terminal safe stop (operator action or
        # persistence failure). A restart must NEVER silently resume
        # a halted session into RUNNING: the terminal state is
        # restored, bars are refused, and trading requires a NEW
        # session. (Placed AFTER the critical-switch check so a
        # critical switch still raises the LOUD refusal.)
        if self._restored_runtime_state == "HALTED":
            self._state = RuntimeState.HALTED
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_RESUMED_HALTED",
                correlation_id=f"session:{self._config.session_id}",
                actor="runtime",
                payload={
                    "reason": "persisted runtime state was HALTED — "
                              "restart never resumes a terminal safe stop",
                    "action": "restored as HALTED (bars refused); begin "
                              "a new session to trade again",
                },
            )
            return

        self._state = RuntimeState.RUNNING
        self._started_at = datetime.now(UTC)
        self._ledgers.record(
            ledger="incident",
            event_type="RUNTIME_STARTED",
            correlation_id=f"session:{self._config.session_id}",
            actor="runtime",
            payload={"session_id": self._config.session_id,
                     "equity": str(self._config.initial_equity),
                     "symbol": self._config.symbol,
                     "mode": "operational",
                     "restarted_from_state": self._restarted},
        )

    def halt(self, reason: str) -> None:
        """Terminal safe stop (operator / critical switch).

        HALT is an authoritative state change — it is persisted
        IMMEDIATELY (BLOCKER 12: a crash right after a halt/kill-switch
        trip must never lose the state on disk).
        """
        previous = self._state
        self._state = RuntimeState.HALTED
        self._metrics.increment("halts")
        self._ledgers.record(
            ledger="incident",
            event_type="RUNTIME_HALTED",
            correlation_id=f"session:{self._config.session_id}",
            actor="runtime",
            payload={"reason": reason, "from": previous.value},
        )
        self._persist_safe(f"session:{self._config.session_id}")

    def trip_kill_switch(
        self,
        scope: KillSwitchScope,
        reason: str,
        target: Optional[str] = None,
    ) -> None:
        """Trip a hierarchical switch; critical scopes halt the runtime.

        The trip is persisted IMMEDIATELY — a restart must NEVER clear
        a kill switch (BLOCKER 12).
        """
        self._kill_switch.trip(
            scope=scope, reason=reason, source="runtime.operator", target=target
        )
        self._metrics.increment("kill_switch_trips")
        self._persist_safe(f"kill-switch:{scope.value}:{target or '*'}")
        if scope in (KillSwitchScope.GLOBAL, KillSwitchScope.ACCOUNT):
            self.halt(f"kill switch {scope.value} tripped: {reason}")
        elif scope is KillSwitchScope.PORTFOLIO:
            self._state = RuntimeState.RECONCILIATION_REQUIRED
            self._persist_safe(f"kill-switch:{scope.value}:{target or '*'}")

    # ------------------------------------------------------------------
    # RUN-CA-1: operator cancel / manual close (audited, fail-closed)
    # ------------------------------------------------------------------
    #: States in which operator cancellation is permitted: cancelling
    #: a pending order REMOVES exposure risk, so it stays available
    #: under HALT (the terminal safe stop) and DEGRADED. The §28
    #: ambiguous/unknown states (EXECUTION_UNCERTAIN, RECOVERY_
    #: REQUIRED, RECONCILIATION_REQUIRED) refuse — reconcile FIRST;
    #: INIT refuses (runtime not started).
    _OPERATOR_CANCEL_STATES = (
        RuntimeState.RUNNING,
        RuntimeState.DEGRADED,
        RuntimeState.HALTED,
    )

    def operator_cancel_order(
        self, order_id: str, *, reason: str,
        correlation_id: Optional[str] = None,
    ) -> dict:
        """Cancel ONE live order as an explicit operator action.

        Fail-closed contract (RUN-CA-1):

        - the order must EXIST (unknown id ⇒ loud refusal, never a
          silent no-op);
        - the order must be LIVE (SUBMITTED/ACKNOWLEDGED/
          PARTIALLY_FILLED — a terminal order has nothing to cancel);
        - the runtime must be in an operator-cancel-permitted state
          (§28 ambiguity states refuse: reconcile first);
        - the cancellation goes through the REAL OMS transition pair
          (request_cancel → finalize_cancel; a partially-filled
          order keeps its filled part, only the remainder cancels)
          and, with a venue attached, through the venue boundary
          (journal-synced venue truth) — exactly the kill-switch
          fill-time cancellation discipline;
        - the incident is ledgered (``ORDER_CANCELLED_OPERATOR``),
          counted (``orders_operator_cancelled``) and persisted
          immediately (BLOCKER 12).

        Returns a summary mapping (order id, status, filled and
        cancelled quantities).
        """
        if not isinstance(order_id, str) or not order_id.strip():
            raise RuntimeContractError(
                "operator cancel requires a non-empty order id"
            )
        if not isinstance(reason, str) or not reason.strip():
            raise RuntimeContractError(
                "operator cancel requires a non-empty reason "
                "(audited operator action)"
            )
        corr = correlation_id or f"operator-cancel:{order_id}"
        if self._state not in self._OPERATOR_CANCEL_STATES:
            raise RuntimeContractError(
                f"operator cancel refused in state {self._state.value} "
                "— reconcile/recover the runtime first (§28: an "
                "ambiguous execution state is resolved from venue "
                "truth, never by cancelling into the ambiguity; fail "
                "closed)"
            )
        try:
            order = self._oms.order(order_id)
        except Exception as exc:
            raise RuntimeContractError(
                f"operator cancel refused: unknown order {order_id!r} "
                f"(the OMS never held it)"
            ) from exc
        if order.status not in (
            OrderLifecycle.SUBMITTED, OrderLifecycle.ACKNOWLEDGED,
            OrderLifecycle.PARTIALLY_FILLED,
        ):
            raise RuntimeContractError(
                f"operator cancel refused: order {order_id} is "
                f"terminal ({order.status.value}) — nothing to cancel"
            )
        if self._venue is not None:
            self._venue.cancel_order(order_id, corr, f"operator: {reason}")
        self._oms.request_cancel(order_id)
        cancelled = self._oms.finalize_cancel(order_id)
        self._pending_protection.pop(order_id, None)
        for symbol, (oid, _, _) in list(self._pending_exits.items()):
            if oid == order_id:
                # the cancelled order WAS the in-flight exit — the
                # protection loop may re-evaluate on the next bar.
                self._pending_exits.pop(symbol, None)
        self._metrics.increment("orders_operator_cancelled")
        self._ledgers.record(
            ledger="incident",
            event_type="ORDER_CANCELLED_OPERATOR",
            correlation_id=corr,
            actor="runtime.operator",
            payload={
                "order_id": order_id,
                "symbol": order.symbol,
                "reason": reason.strip(),
                "filled_quantity": str(cancelled.filled_quantity),
                "cancelled_quantity": str(cancelled.remaining_quantity),
                "action": (
                    "operator cancellation through the real OMS "
                    "transition pair (+ venue boundary when attached); "
                    "the filled part of a partially-filled order stays"
                ),
            },
        )
        self._persist_safe(corr)
        return {
            "order_id": order_id,
            "status": cancelled.status.value,
            "filled_quantity": str(cancelled.filled_quantity),
            "cancelled_quantity": str(cancelled.remaining_quantity),
        }

    def operator_close_position(
        self, symbol: Optional[str] = None, *, reason: str,
        correlation_id: Optional[str] = None,
    ) -> dict:
        """Close (liquidate) the live position as an explicit
        operator action (RUN-CA-1).

        Fail-closed contract:

        - the position must exist and be NON-FLAT (a flat/missing
          position is a loud refusal, never a silent no-op);
        - RUNNING: a MANUAL_CLOSE order is built and submitted through
          the AUTHORITATIVE gate→OMS path (the risk gate's closing
          carve-outs apply — kill switch / account drawdown do not
          block risk REDUCTION); it settles on LATER bars through the
          normal latency/fill model (identical paper semantics to a
          protective exit);
        - HALTED: bars are refused, so a submitted order could never
          fill — instead the close settles IMMEDIATELY at the latest
          admitted bar (open ± half spread, commission per unit),
          through the ONE authoritative fill-application path, with
          every live order for the symbol cancelled first (frozen
          protection included). This is the operator escape hatch
          for the post-HALT frozen-exits condition;
        - every other non-trading state (INIT/DEGRADED/
          RECONCILIATION_REQUIRED/RECOVERY_REQUIRED/EXECUTION_
          UNCERTAIN) refuses — reconcile/recover first (fail closed);
        - both modes ledger their incidents and persist immediately
          (BLOCKER 12); neither can ADD exposure (closing-only).

        Returns a summary mapping (mode, order id, quantities).
        """
        sym = symbol if symbol is not None else self._config.symbol
        if not isinstance(sym, str) or not sym.strip():
            raise RuntimeContractError(
                "manual close requires a non-empty symbol"
            )
        if not isinstance(reason, str) or not reason.strip():
            raise RuntimeContractError(
                "manual close requires a non-empty reason "
                "(audited operator action)"
            )
        corr = correlation_id or f"operator-close:{sym}"
        position = self._positions.get(sym)
        if position is None or position.is_flat:
            raise RuntimeContractError(
                f"manual close refused: no live position for {sym!r} "
                "(flat or never opened — nothing to close)"
            )
        if not self._bars:
            raise RuntimeContractError(
                "manual close refused: no admitted bars — no reference "
                "mark exists (fail closed)"
            )
        latest_bar = self._bars[-1]
        reference = Decimal(str(latest_bar["close"]))
        if self._state is RuntimeState.RUNNING:
            return self._operator_close_submitted(
                sym, position, latest_bar, reference, reason, corr,
            )
        if self._state is RuntimeState.HALTED:
            return self._operator_close_settled(
                sym, position, latest_bar, reference, reason, corr,
            )
        raise RuntimeContractError(
            f"manual close refused in state {self._state.value} — "
            "reconcile/recover the runtime first (fail closed; only "
            "RUNNING (normal submission) and HALTED (immediate "
            "operator settlement) permit manual close)"
        )

    def _operator_close_submitted(
        self, symbol, position, latest_bar, reference, reason, corr,
    ) -> dict:
        """RUNNING manual close: authoritative submission, normal
        bar-path settlement (latency model, exactly the protective-
        exit semantics — just operator-initiated)."""
        plan = self._build_close_plan(
            position, ExitReason.MANUAL_CLOSE, latest_bar, corr,
            detail=f"operator manual close: {reason.strip()}",
        )
        if plan is None:
            raise RuntimeContractError(
                "manual close refused: the plan builder declined the "
                "closing plan (position geometry unverifiable — fail "
                "closed)"
            )
        created, failed = self._execute_plan(
            plan, latest_bar, self._bar_index, corr,
            reference, self._current_equity(reference),
        )
        if not created:
            raise RuntimeContractError(
                "manual close refused by the risk gate: "
                + ", ".join(sorted(set(failed)))
                + " (fail closed — no override path exists)"
            )
        order = created[0]
        self._metrics.increment("orders_operator_close_submitted")
        self._ledgers.record(
            ledger="incident",
            event_type="ORDER_MANUAL_CLOSE_SUBMITTED",
            correlation_id=corr,
            actor="runtime.operator",
            payload={
                "order_id": order.order_id,
                "symbol": symbol,
                "quantity": str(order.quantity),
                "reason": reason.strip(),
                "action": (
                    "operator manual close submitted through the "
                    "authoritative gate→OMS path; settles on later "
                    "bars through the normal latency/fill model"
                ),
            },
        )
        self._persist_safe(corr)
        return {
            "mode": "submitted",
            "order_id": order.order_id,
            "quantity": str(order.quantity),
            "status": order.status.value,
        }

    def _operator_close_settled(
        self, symbol, position, latest_bar, reference, reason, corr,
    ) -> dict:
        """HALTED manual close: IMMEDIATE settlement at the latest
        admitted bar (the operator escape hatch — bars are refused
        under HALT, so a submitted order could never fill).

        The settlement is loud and exactly-once: every LIVE order for
        the symbol is cancelled first (frozen protection included),
        the closing order is created through the real OMS chain
        (create → validate → risk_approve → submit → acknowledge —
        the gate runs with the closing carve-outs), and ONE full
        MARKET fill at ``open ± half_spread`` (adverse side) applies
        through ``_apply_execution_fills`` — the same authoritative
        OMS → position → P&L path every fill uses. With a venue
        attached the order is deliberately NOT submitted to the venue
        (the venue refuses non-RUNNING runtimes by design); the
        incident records that venue truth was not consulted and the
        venue book is not updated — an explicitly operator-owned
        out-of-band settlement, never a hidden direct-execution
        fallback in the NORMAL path.
        """
        # 1. cancel every live order for the symbol (frozen
        #    protection, stale entries — all purposeless post-close).
        for live in list(self._oms.live_orders()):
            if live.symbol != symbol:
                continue
            if self._venue is not None:
                self._venue.cancel_order(
                    live.order_id, corr,
                    f"operator manual close of {symbol}",
                )
            self._oms.request_cancel(live.order_id)
            self._oms.finalize_cancel(live.order_id)
            self._pending_protection.pop(live.order_id, None)
        self._pending_exits.pop(symbol, None)

        # 2. build + risk-gate the closing plan (closing carve-outs
        #    apply; a failure is a loud refusal, never a bypass).
        plan = self._build_close_plan(
            position, ExitReason.MANUAL_CLOSE, latest_bar, corr,
            detail=f"operator manual close (HALT settlement): "
                   f"{reason.strip()}",
        )
        if plan is None:
            raise RuntimeContractError(
                "manual close refused: the plan builder declined the "
                "closing plan (position geometry unverifiable — fail "
                "closed)"
            )
        context = RiskContext(
            equity=self._current_equity(reference),
            current_units=position.quantity,
            reference_price=reference,
            bar_volume=Decimal(str(latest_bar.get("volume") or 0)),
            last_bar_age_bars=0,
            # Stage C (F-14): market/model context injected from the
            # validated gate context (structural paper_mode stays a
            # literal — see GateContextDefaults provenance).
            market_open=self._gate_context.market_open,
            paper_mode=True,
            model_valid=self._gate_context.model_valid,
            uncertainty=plan.uncertainty,
            crash_probability=0.0,
            max_drawdown_fraction=self._window_drawdown(),
            account_drawdown_fraction=self._account_drawdown(),
            account_drawdown_limit_fraction=(
                self._config.max_account_drawdown_fraction
            ),
            volatility=self._window_volatility(),
            max_volatility=self._gate_ceilings.max_volatility,
            daily_realized_return=self._daily_realized_return(),
            half_spread=self._realism.half_spread,
        )
        assessment = self._risk_gate.evaluate(
            plan, context, corr, ledger=self._ledgers,
            assessed_at=latest_bar.get("timestamp"),
        )
        if not assessment.passed:
            raise RuntimeContractError(
                "manual close refused by the risk gate: "
                + ", ".join(
                    sorted({c.check for c in assessment.failed_checks})
                )
                + " (fail closed — no override path exists)"
            )

        # 3. create the order through the real OMS chain.
        order, created = self._oms.create_order(
            plan=plan,
            session_id=self._config.session_id,
            created_at=latest_bar.get("timestamp") or datetime.now(UTC),
            ttl_bars=plan.entry.ttl_bars,
        )
        if not created:
            raise RuntimeContractError(
                "manual close refused: duplicate order intent "
                "(a live manual-close order already exists — fail "
                "closed)"
            )
        self._metrics.increment("orders_created")
        self._oms.validate_order(order.order_id)
        self._oms.risk_approve(order.order_id, assessment)
        self._oms.submit(
            order.order_id,
            submitted_at=latest_bar.get("timestamp"),
            bar_index=self._bar_index,
        )
        self._oms.acknowledge(order.order_id)
        # D-6: truthful submission accounting (closing orders are exempt
        # from the limit BLOCKS but still occupy submission capacity).
        self._record_submission(latest_bar.get("timestamp"))

        # 4. ONE immediate full MARKET fill at the latest admitted
        #    bar's open, adverse half spread applied (deterministic:
        #    bar-derived, never wall-clock — restart-stable).
        bar_ts = latest_bar.get("timestamp")
        if bar_ts is None or getattr(bar_ts, "tzinfo", None) is None:
            raise RuntimeContractError(
                "manual close refused: the latest admitted bar lacks "
                "a timezone-aware timestamp — no provable settlement "
                "mark (fail closed)"
            )
        open_ = Decimal(str(latest_bar["open"]))
        if order.side == "SELL":
            price = open_ - self._realism.half_spread
        else:
            price = open_ + self._realism.half_spread
        qty = order.quantity
        commission = self._realism.commission_per_unit * qty
        fill = RuntimeFill(
            fill_id="pending",
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            quantity=qty,
            price=price,
            commission=commission,
            slippage_cost=Decimal("0"),
            spread_cost=self._realism.half_spread,
            filled_at=bar_ts,
            fill_index=0,
            bar_index=self._bar_index,
        )
        fill = fill.model_copy(update={"fill_id": fill.fill_hash})
        self._apply_execution_fills(order, [fill], corr, [])
        self._reconcile_after_fills(corr)

        self._metrics.increment("orders_operator_closed")
        self._ledgers.record(
            ledger="incident",
            event_type="OPERATOR_MANUAL_CLOSE",
            correlation_id=corr,
            actor="runtime.operator",
            payload={
                "order_id": order.order_id,
                "symbol": symbol,
                "quantity": str(qty),
                "price": str(price),
                "reason": reason.strip(),
                "venue": (
                    "not-consulted (venue refuses non-RUNNING runtimes "
                    "by design; operator-owned out-of-band settlement "
                    "— venue book NOT updated)"
                    if self._venue is not None else "none-attached"
                ),
                "action": (
                    "immediate settlement at the latest admitted bar "
                    "(terminal HALT — bars are refused, so normal "
                    "latency settlement is impossible); one full "
                    "MARKET fill through the authoritative "
                    "OMS→position→P&L path"
                ),
            },
        )
        self._persist_safe(corr)
        return {
            "mode": "settled",
            "order_id": order.order_id,
            "quantity": str(qty),
            "price": str(price),
            "status": self._oms.order(order.order_id).status.value,
        }

    def _build_close_plan(
        self, position, reason: ExitReason, bar: Mapping,
        correlation_id: str, detail: str,
    ):
        """Build the MANUAL_CLOSE plan (the _build_exit_plan geometry
        with an operator-authored reason detail)."""
        decision = Decision(
            decision_id=prefixed_hash(
                "rtdec.",
                {"kind": "manual_close", "reason": reason.value,
                 "position": position.position_id,
                 "detail": detail},
            ),
            action=DecisionAction.CLOSE,
            symbol=position.symbol,
            timestamp=bar["timestamp"],
            prediction_ids=("operator-manual-close",),
            model_versions=("runtime.operator",),
            uncertainty=UncertaintyReport(
                confidence=1.0, entropy=0.0, ensemble_disagreement=0.0
            ),
            regime="EXIT",
            crash_risk={"probability": 0.0},
            portfolio_state={"position_quantity": str(position.quantity)},
            reason=detail,
            rejected_alternatives=(),
            correlation_id=correlation_id,
        )
        reference = Decimal(str(bar["close"]))
        artifact = PredictionArtifact(
            prediction_id=f"manual-close-{reason.value.lower()}",
            symbol=position.symbol,
            horizon=1,
            timestamp=bar["timestamp"],
            prediction="EXIT",
            probability=1.0,
            expected_return=0.0,
            volatility=0.01,
            uncertainty=UncertaintyReport(
                confidence=1.0, entropy=0.0, ensemble_disagreement=0.0
            ),
            model_versions=("runtime.operator",),
            feature_version=self._config.feature_version,
            dataset_version=self._config.dataset_version,
            regime="EXIT",
            crash_risk={"probability": 0.0},
            provenance={"origin": "operator_manual_close"},
            correlation_id=correlation_id,
        )
        return self._plan_builder.build(
            decision=decision,
            artifact=artifact,
            reference_price=reference,
            equity=self._current_equity(reference),
            position_quantity=position.quantity,
        )

    # ------------------------------------------------------------------
    # Recovery (BLOCKER 4/5/6/9/12/13/20 — integrated, not standalone)
    # ------------------------------------------------------------------
    def _identity_block(self) -> dict:
        """Deterministic session/config/model identity (BLOCKER 21).

        Persisted with every snapshot; a restart with a DIFFERENT
        config or model set is refused — the runtime never silently
        continues under another identity.
        """
        members = []
        for member, weight in zip(self._ensemble.members, self._ensemble.weights):
            art = member.artifact()
            members.append({
                "model_id": art.model_id,
                "model_version": art.model_version,
                "model_family": art.model_family,
                "model_hash": art.model_hash,
                "feature_version": art.feature_version,
                "dataset_version": art.dataset_version,
                "seed": art.seed,
                "weight": round(float(weight), 12),
            })
        config_digest = _config_digest(
            self._config.model_dump(mode="json")
        )
        return {
            "contract_version": RUNTIME_CONTRACT_VERSION,
            "session_id": self._config.session_id,
            "symbol": self._config.symbol,
            "timeframe": self._config.timeframe,
            "config_digest": config_digest,
            # Batch 6 (snapshot compat): the EXACT config view the
            # digest was computed over — persisted so that FUTURE
            # schema evolution can decompose a digest mismatch
            # field-by-field (shared-field change vs additive
            # evolution) instead of the legacy suffix-recomputation.
            # Opaque to the execution-state schema (identity is a
            # validated mapping; version 1.1.0 unchanged).
            "config": self._config.model_dump(mode="json"),
            "ensemble_members": members,
            "calibrator": (
                {
                    "dataset_version": self._calibrator.dataset_version,
                    "fitted": self._calibrator.fitted,
                    "ece": round(self._calibrator.ece, 12)
                    if self._calibrator.ece is not None else None,
                }
                if self._calibrator is not None else None
            ),
        }

    def _config_evolution_match(
        self, persisted_identity: Mapping
    ) -> Optional[tuple]:
        """Decompose a config-digest mismatch into KNOWN additive
        schema evolution (Batch 6, snapshot compat).

        Returns the tuple of evolution field names the snapshot is
        BEHIND (a non-empty suffix of ``SNAPSHOT_CONFIG_EVOLUTION``)
        when the persisted identity is EXACTLY the current config
        minus those additions; ``None`` for any true identity change
        (shared-field value difference, removed field, foreign or
        tampered identity — fail closed, never guessed).

        Two decomposition paths, most-exact first:

        1. The snapshot persists its config view (Batch 6+): compare
           field-by-field — every shared field must be EQUAL, nothing
           may be removed, and the missing fields must be exactly
           known evolution additions. The persisted digest itself is
           re-verified against the persisted view (tamper evidence).
        2. Legacy snapshots (no config view): recompute the digest of
           the current config minus each trailing k evolution fields;
           an exact match proves the snapshot's config equals the
           current config minus those k additions.
        """
        persisted_digest = persisted_identity.get("config_digest")
        if not isinstance(persisted_digest, str) or not persisted_digest:
            return None
        current = self._config.model_dump(mode="json")
        persisted_cfg = persisted_identity.get("config")

        if isinstance(persisted_cfg, dict) and persisted_cfg:
            # Path 1 — exact field-wise decomposition.
            if _config_digest(persisted_cfg) != persisted_digest:
                return None  # digest/view inconsistency — tampered
            shared_diff = sorted(
                k for k, v in persisted_cfg.items()
                if k in current and current[k] != v
            )
            removed = sorted(
                k for k in persisted_cfg if k not in current
            )
            if shared_diff or removed:
                return None  # a real identity change, not evolution
            added = tuple(
                f for f in _EVOLUTION_FIELDS
                if f not in persisted_cfg and f in current
            )
            missing_unknown = sorted(
                k for k, v in current.items()
                if k not in persisted_cfg and k not in _EVOLUTION_FIELDS
            )
            if missing_unknown:
                return None  # undeclared schema drift — refuse
            return added if added else None

        # Path 2 — legacy suffix-strip recomputation (pre-Batch-6
        # snapshots: identity holds only the digest).
        for k in range(len(_EVOLUTION_FIELDS), 0, -1):
            legacy_view = {
                f: v for f, v in current.items()
                if f not in set(_EVOLUTION_FIELDS[len(_EVOLUTION_FIELDS) - k:])
            }
            if _config_digest(legacy_view) == persisted_digest:
                return _EVOLUTION_FIELDS[len(_EVOLUTION_FIELDS) - k:]
        return None

    def _recover_existing_state(self) -> None:
        """BLOCKER 4: the ACTUAL runtime recovery path.

        START → LOAD SNAPSHOT → VERIFY SNAPSHOT (+ identity binding)
        → VERIFY hash/ledger integrity → RESTORE OMS → RESTORE
        ORDERS → RESTORE FILLS → RESTORE POSITIONS → RESTORE KILL
        SWITCH → RESTORE LEDGER STATE → RESTORE PENDING EXECUTION
        STATE → RESTORE SL/TP STATE → RECONCILE → only then may the
        caller proceed to RUNNING. Unprovable state ⇒ RECOVERY_REQUIRED
        / RECONCILIATION_REQUIRED / HALTED — never automatic resume.
        """
        if not self._store.has_snapshot:
            # Cold start: nothing to recover — a FRESH session is
            # legal; the first bar will persist the first snapshot.
            # NOTE: no filesystem path in the payload (BLOCKER 14:
            # environment-dependent values never enter the audit
            # chain — deterministic replay must reproduce it).
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_COLD_START",
                correlation_id=f"session:{self._config.session_id}",
                actor="runtime",
                payload={"session_id": self._config.session_id},
            )
            return

        # -- LOAD ---------------------------------------------------------
        try:
            state = self._store.restore()
        except StateStoreError as exc:
            self._state = RuntimeState.RECOVERY_REQUIRED
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_RECOVERY_REQUIRED",
                correlation_id=f"session:{self._config.session_id}",
                actor="runtime",
                payload={"reason": f"persistent state unreadable: {exc}"},
            )
            raise RuntimeContractError(
                f"START REFUSED — RECOVERY_REQUIRED: persistent state "
                f"cannot be loaded/verified: {exc}"
            ) from exc

        # -- VERIFY identity binding (never another session/model) --------
        persisted_identity = state.get("identity", {})
        current_identity = self._identity_block()
        if persisted_identity.get("config_digest") != \
                current_identity["config_digest"]:
            # Batch 6 (snapshot compat): distinguish KNOWN additive
            # config-schema evolution from a true identity change
            # before refusing. A mismatch that decomposes EXACTLY
            # into the documented evolution (SNAPSHOT_CONFIG_
            # EVOLUTION) is resumable ONLY under the explicit
            # operator opt-in — and is ledgered loudly on resume;
            # everything else (any shared-field value difference)
            # remains the hard BLOCKER 21 refusal.
            evolved = self._config_evolution_match(persisted_identity)
            if evolved is not None:
                if not self._config.allow_snapshot_config_evolution:
                    self._state = RuntimeState.RECOVERY_REQUIRED
                    raise RuntimeContractError(
                        "START REFUSED — config schema evolved since "
                        "this snapshot was persisted (added fields: "
                        + ", ".join(evolved)
                        + "); the snapshot is otherwise THIS session's "
                        "identity. Resume requires the explicit "
                        "operator opt-in "
                        "(RuntimeConfig.allow_snapshot_config_evolution="
                        "True); the runtime never silently continues "
                        "under evolved risk semantics (fail closed)"
                    )
                # Deferred: the incident is recorded AFTER the ledger
                # chains are restored (recording now would write into
                # the fresh in-memory ledger that restore_state is
                # about to replace — the event would be lost).
                self._snapshot_config_evolved = evolved
            else:
                self._state = RuntimeState.RECOVERY_REQUIRED
                raise RuntimeContractError(
                    "START REFUSED — persisted state belongs to a DIFFERENT "
                    "config/session/model identity (config_digest mismatch); "
                    "the runtime never silently continues under another "
                    "identity (BLOCKER 21)"
                )
        if persisted_identity.get("session_id") != self._config.session_id:
            self._state = RuntimeState.RECOVERY_REQUIRED
            raise RuntimeContractError(
                "START REFUSED — persisted state session "
                f"{persisted_identity.get('session_id')!r} != configured "
                f"{self._config.session_id!r}"
            )
        # Model identity binding: the persisted ensemble member hashes
        # (and their order/weights) must equal the CURRENT ensemble —
        # a swapped/tampered model is refused, never silently loaded
        # (BLOCKER 21).
        persisted_members = [
            m.get("model_hash") for m in
            persisted_identity.get("ensemble_members", [])
        ]
        current_members = [
            m["model_hash"] for m in current_identity["ensemble_members"]
        ]
        if persisted_members != current_members:
            self._state = RuntimeState.RECOVERY_REQUIRED
            raise RuntimeContractError(
                "START REFUSED — persisted state was produced by a "
                "DIFFERENT model ensemble (member hashes differ); never "
                "silently load another model (BLOCKER 21): persisted "
                f"{persisted_members} vs current {current_members}"
            )

        # -- RESTORE ledger chains FIRST (they must verify) ----------------
        try:
            self._ledgers.restore_state(state.get("ledgers", {}))
        except LedgerError as exc:
            self._state = RuntimeState.RECOVERY_REQUIRED
            raise RuntimeContractError(
                f"START REFUSED — RECOVERY_REQUIRED: {exc}"
            ) from exc
        if self._ledgers.head_hashes() != state.get("ledger_heads"):
            self._state = RuntimeState.RECOVERY_REQUIRED
            raise RuntimeContractError(
                "START REFUSED — RECOVERY_REQUIRED: restored ledger heads "
                "differ from the persisted heads (chain reconstruction "
                "failed)"
            )

        # -- SNAPSHOT CONFIG EVOLUTION (Batch 6): the operator opted in
        # to resuming an evolved-config snapshot — ledger it LOUDLY now
        # that the authoritative ledger chains are restored (the
        # incident joins the session's permanent audit trail).
        if self._snapshot_config_evolved:
            evolved = self._snapshot_config_evolved
            self._snapshot_config_evolved = None
            self._ledgers.record(
                ledger="incident",
                event_type="SNAPSHOT_CONFIG_EVOLVED",
                correlation_id=(
                    f"session:{self._config.session_id}"
                ),
                actor="runtime.recovery",
                payload={
                    "added_fields": {
                        f: self._config.model_dump(mode="json")[f]
                        for f in evolved
                    },
                    "action": (
                        "operator-authorized resume under an evolved "
                        "config schema; the new fields' limits apply "
                        "prospectively from this restart (ledgered, "
                        "never silent)"
                    ),
                },
            )

        # -- RESTORE memory -------------------------------------------------
        try:
            self._memory.restore_state(state.get("memory", []))
        except MemoryError as exc:
            self._state = RuntimeState.RECOVERY_REQUIRED
            raise RuntimeContractError(
                f"START REFUSED — RECOVERY_REQUIRED: {exc}"
            ) from exc
        if self._memory.chain_hash != state.get("memory_chain_hash"):
            self._state = RuntimeState.RECOVERY_REQUIRED
            raise RuntimeContractError(
                "START REFUSED — RECOVERY_REQUIRED: restored memory chain "
                "hash differs from the persisted chain head"
            )

        # -- RESTORE OMS orders + fills + kill switch ------------------------
        restored_orders = self._oms.restore_state(state.get("orders", []))
        restored_switches = self._kill_switch.restore_state(
            state.get("kill_switch", [])
        )

        # -- RESTORE positions (incl. SL/TP levels, BLOCKER 9) ----------------
        positions: dict = {}
        for record in state.get("positions", []):
            pos = PositionState.model_validate(record)
            positions[pos.symbol] = pos
        self._positions = positions

        # -- RESTORE bar history + bookkeeping --------------------------------
        bars = []
        for raw in state.get("bars", []):
            bar = dict(raw)
            ts = bar.get("timestamp")
            if isinstance(ts, str):
                bar["timestamp"] = datetime.fromisoformat(ts)
            bars.append(bar)
        self._bars = bars
        self._bar_index = state.get("bar_index", -1)
        self._consecutive_bad_bars = state.get("consecutive_bad_bars", 0)
        self._equity_realized = Decimal(str(state.get("equity_realized", "0")))
        self._order_fill_cursor = dict(state.get("order_fill_cursor", {}))
        self._restored_runtime_state = state.get("runtime_state")

        # pending protection: order_id -> (sl, tp, corr)
        pending_protection: dict = {}
        for oid, triple in (state.get("pending_protection", {})).items():
            sl, tp, corr = triple
            pending_protection[oid] = (
                Decimal(str(sl)) if sl is not None else None,
                Decimal(str(tp)) if tp is not None else None,
                corr,
            )
        self._pending_protection = pending_protection

        # pending exits: symbol -> (order_id, reason, snapshot)
        pending_exits: dict = {}
        for symbol, entry in (state.get("pending_exits", {})).items():
            order_id, reason, snapshot = entry
            pending_exits[symbol] = (
                order_id,
                ExitReason(reason) if isinstance(reason, str) else reason,
                PositionState.model_validate(snapshot),
            )
        self._pending_exits = pending_exits

        # -- RECONCILE before any resume -------------------------------------
        report = self._reconciliation.reconcile(self._oms, self._positions)
        if not report.ok:
            self._state = RuntimeState.RECONCILIATION_REQUIRED
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_RECONCILIATION_REQUIRED",
                correlation_id=f"session:{self._config.session_id}",
                actor="runtime",
                payload={
                    "mismatches": list(report.mismatches),
                    "action": "start refused — no automatic resume on "
                              "unprovable state (BLOCKER 10)",
                },
            )
            raise RuntimeContractError(
                "START REFUSED — RECONCILIATION_REQUIRED after restart: "
                + "; ".join(report.mismatches[:3])
                + " (BLOCKER 10: reconciliation gates resumption)"
            )

        self._restarted = True
        self._metrics.increment("recovery_events")
        self._ledgers.record(
            ledger="incident",
            event_type="RUNTIME_STATE_RESTORED",
            correlation_id=f"session:{self._config.session_id}",
            actor="runtime",
            payload={
                "restored_orders": restored_orders,
                "restored_switches": restored_switches,
                "restored_positions": len(positions),
                "restored_bars": len(bars),
                "bar_index": self._bar_index,
                "ledger_events": len(self._ledgers),
                "memory_records": len(self._memory),
                "ledger_heads": self._ledgers.head_hashes(),
                "memory_chain_hash": self._memory.chain_hash,
                "verdict": "RESTORED + RECONCILED — resume permitted",
            },
        )

    @property
    def restarted(self) -> bool:
        """True when this runtime instance restored persisted state."""
        return self._restarted

    @property
    def operational(self) -> bool:
        """True for operational paper sessions; False for explicitly
        marked ephemeral test fixtures."""
        return not self._config.ephemeral_test_fixture

    # ------------------------------------------------------------------
    # Bar processing (the authoritative path)
    # ------------------------------------------------------------------
    def process_bar(self, bar: Mapping) -> BarOutcome:
        """Process ONE bar through the full governed chain (§26 timing)."""
        t0 = time.perf_counter()
        try:
            return self._process_bar_body(bar)
        finally:
            # Wall-clock latency is OBSERVABILITY ONLY (INV-01: never
            # identity, never persisted, never a decision input).
            self._metrics.set_gauge(
                "cycle_latency_seconds", time.perf_counter() - t0
            )

    def _process_bar_body(self, bar: Mapping) -> BarOutcome:
        self._bar_index += 1
        self._metrics.increment("bars_processed")
        idx = self._bar_index
        correlation_id = f"corr-{self._config.session_id}-{idx:06d}"
        ts = bar.get("timestamp")
        ts = ts.astimezone(UTC) if getattr(ts, "tzinfo", None) else None

        # -- 0. operating-state guard -------------------------------------
        if self._state in NON_TRADING_STATES:
            self._metrics.increment("bars_refused")
            return self._refuse_bar(idx, correlation_id, ts,
                                    f"runtime is {self._state.value}")

        # -- 1. data validation (§10 hard gates, WITH gap context) -----
        # A stale/gapped bar is only detectable relative to the last
        # admitted bar — validate the pair, then keep only rejections
        # that concern the NEW bar (index -1).
        context_bars = (self._bars[-1:] + [dict(bar)]) if self._bars else [dict(bar)]
        accepted, rejections = validate_bars(
            context_bars,
            expected_interval=timedelta(
                seconds=self._config.expected_interval_seconds
            ),
        )
        new_bar_rejections = tuple(
            r for r in rejections if r.bar_index == len(context_bars) - 1
        )
        if new_bar_rejections:
            self._metrics.increment("bad_bars")
            return self._bad_bar(idx, correlation_id, ts,
                                 new_bar_rejections, bar)

        # -- 2. bar admitted: pending orders fill FIRST (latency §38) ------
        # Orders submitted on earlier bars execute against THIS bar's
        # liquidity — fills precede any new decision (no same-bar fill
        # of the decision that is about to be made on this bar).
        self._bars.append(dict(bar))
        bar_fills = self._process_pending_orders(bar, idx, correlation_id)
        orders_created: list = []
        risk_failed: tuple = ()

        # -- 2b. ACCOUNT-equity drawdown enforcement (RUN-DD-1) ------------
        # Evaluated AFTER this bar's fills and BEFORE any new decision:
        # both fill-driven and price-driven breaches are caught at the
        # first bar where they exist. A strict breach trips the ACCOUNT
        # kill switch and HALTS the session terminally; closing orders
        # submitted later in THIS bar remain permitted (risk-reduction
        # carve-out) and every FOLLOWING bar is refused (HALTED).
        self._enforce_account_drawdown(idx, correlation_id)

        # -- 3. TTL expiry for live orders (§39) ----------------------------
        for order in list(self._oms.live_orders()):
            expired = self._oms.expire_if_elapsed(order.order_id, idx)
            if expired is not None and self._venue is not None:
                # Batch 5: keep venue truth consistent with the OMS
                # expiry (journal-synced cancellation; failures are
                # ledgered and surface at the next reconciliation).
                self._venue.cancel_order(
                    order.order_id, correlation_id, "ttl expiry"
                )

        # -- 4. record exits for completed exit orders (§31) -----------------
        exits = self._record_completed_exits(bar, correlation_id)

        # -- 4b. in-session wall-clock feed watchdog (RUN-ST-1) --------------
        # Everything above (fills, drawdown enforcement, TTL expiry,
        # completed exits) ran UNCONDITIONALLY: the watchdog blocks
        # NEW EXPOSURE, never in-flight settlement, protective
        # action or accounting. A stale bar is admitted and persisted
        # like any accepted bar; only the prediction/decision/entry
        # chain is skipped until the feed catches up (fail closed).
        if self._feed_is_stale(bar):
            return self._stale_bar(
                idx, correlation_id, ts, bar, bar_fills, exits
            )

        # -- 5. PIT sequence construction ----------------------------------
        cutoff = ts
        spec = SequenceSpec(
            symbol=self._config.symbol,
            timeframe=self._config.timeframe,
            lookback=self._config.lookback,
            horizon=self._config.horizon,
            stride=self._config.stride,
            feature_version=self._config.feature_version,
            dataset_version=self._config.dataset_version,
        )
        try:
            sset = build_sequence_set(
                self._bars,
                spec,
                cutoff=cutoff,
                dataset_content_hash=f"bars-{len(self._bars)}",
                expected_interval_seconds=self._config.expected_interval_seconds,
            )
            latest = sset.sequences[-1]
        except Exception as exc:  # insufficient bars yet → HOLD posture
            if bar_fills:
                self._reconcile_after_fills(correlation_id)
            # A warm-up bar still mutates authoritative state (bars,
            # bar cursor) — it is persisted like any accepted bar
            # (BLOCKER 5: no unpersisted state transitions).
            self._persist_safe(correlation_id)
            self._metrics.increment("warmup_bars")
            return self._warmup_bar(idx, correlation_id, ts, str(exc))

        # -- 3. prediction: ensemble → calibration --------------------------
        ensemble_pred = self._ensemble.predict(list(latest.features))
        probability = ensemble_pred.probability
        calibrated = (
            self._calibrator.calibrate(probability)
            if self._calibrator is not None and self._calibrator.fitted
            else probability
        )
        calibrated = min(max(calibrated, 1e-9), 1 - 1e-9)
        confidence = max(calibrated, 1.0 - calibrated)
        entropy = -(
            calibrated * math.log(max(calibrated, 1e-12))
            + (1 - calibrated) * math.log(max(1 - calibrated, 1e-12))
        )
        disagreement = ensemble_pred.disagreement
        uncertainty = UncertaintyReport(
            confidence=round(confidence, 12),
            entropy=round(entropy, 12),
            ensemble_disagreement=round(disagreement, 12),
            epistemic_uncertainty=round(disagreement / 2, 12),
            aleatoric_uncertainty=round(entropy / 2, 12),
        )

        # -- 4. regime (independent classification) -------------------------
        regime_state = self._classify_regime()
        # -- 5. crash intelligence (INDEPENDENT of the signal, §20) ---------
        crash = self._assess_crash(disagreement)

        # -- 6. prediction artifact + ledger ---------------------------------
        prediction_id = prefixed_hash(
            "rtpre.",
            {"kind": "prediction", "bar": idx, "corr": correlation_id,
             "p": round(calibrated, 12)},
        )
        expected_return = round(calibrated - 0.5, 12)
        artifact = PredictionArtifact(
            prediction_id=prediction_id,
            symbol=self._config.symbol,
            horizon=self._config.horizon,
            timestamp=ts,
            prediction="UP" if calibrated >= 0.5 else "DOWN",
            probability=round(calibrated, 12),
            expected_return=expected_return,
            volatility=round(self._window_volatility(), 12),
            uncertainty=uncertainty,
            model_versions=tuple(ensemble_pred.composition.member_versions),
            ensemble_composition={
                v: w for v, w in zip(
                    ensemble_pred.composition.member_versions,
                    ensemble_pred.composition.weights,
                )
            },
            feature_version=self._config.feature_version,
            dataset_version=self._config.dataset_version,
            regime=regime_state,
            crash_risk=crash,
            provenance={
                "session": self._config.session_id,
                "sequence_set": sset.sequence_set_id,
                "calibrated": "yes" if (
                    self._calibrator is not None and self._calibrator.fitted
                ) else "no",
            },
            correlation_id=correlation_id,
        )
        self._ledgers.record(
            ledger="prediction",
            event_type="PREDICTION_ARTIFACT",
            correlation_id=correlation_id,
            actor="runtime.prediction",
            payload={
                "prediction_id": prediction_id,
                "symbol": artifact.symbol,
                "probability": artifact.probability,
                "prediction": artifact.prediction,
                "uncertainty": {
                    "confidence": uncertainty.confidence,
                    "entropy": uncertainty.entropy,
                    "ensemble_disagreement": uncertainty.ensemble_disagreement,
                },
                "regime": regime_state,
                "crash_risk": crash,
                "model_versions": list(artifact.model_versions),
            },
        )

        # -- 7. decision ------------------------------------------------------
        position = self._positions.get(
            self._config.symbol, PositionState(symbol=self._config.symbol)
        )
        data_status = MarketDataStatus(available=True, last_bar_age_bars=0)
        decision = self._decision_engine.decide(
            artifact=artifact,
            data_status=data_status,
            position_quantity=position.quantity,
            correlation_id=correlation_id,
        )
        if decision.action is DecisionAction.NO_TRADE:
            self._ledgers.record_no_trade(decision)
            self._metrics.count_no_trade_reason(decision.reason)
        elif decision.action is DecisionAction.HOLD:
            self._metrics.increment("decisions_hold")
        else:
            self._metrics.increment("decisions_trade")
            self._ledgers.record(
                ledger="decision",
                event_type=f"DECISION_{decision.action.value}",
                correlation_id=correlation_id,
                actor="runtime.decision_engine",
                payload={
                    "decision_id": decision.decision_id,
                    "action": decision.action.value,
                    "symbol": decision.symbol,
                    "reason": decision.reason,
                    "prediction_ids": list(decision.prediction_ids),
                    "regime": decision.regime,
                    "crash_risk": dict(decision.crash_risk),
                },
                parent_id=artifact.prediction_id,
            )
        self._memory.record(
            MemoryCategory.DECISION,
            {"action": decision.action.value, "reason": decision.reason,
             "correlation_id": correlation_id},
            correlation_id=correlation_id,
            at=ts,
        )

        # -- 8. plan + risk gate + submission ---------------------------------
        reference_price = Decimal(str(bar["close"]))
        equity = self._current_equity(reference_price)

        # -- 7b. governed RL advisor (mandate §28/§44; DISABLED by default) --
        # ADVISORY-ONLY: the proposal is ledgered + remembered for
        # audit and CANNOT create, alter or submit an order. The
        # authoritative Decision/Risk/KillSwitch/OMS chain above and
        # below is completely independent of this record.
        if self._rl_policy is not None:
            self._record_rl_proposal(
                artifact=artifact,
                uncertainty=uncertainty,
                regime_state=regime_state,
                crash=crash,
                position=position,
                reference_price=reference_price,
                equity=equity,
                ts=ts,
                correlation_id=correlation_id,
                parent_id=decision.decision_id,
            )

        if decision.action not in (DecisionAction.HOLD, DecisionAction.NO_TRADE):
            plan = self._plan_builder.build(
                decision=decision,
                artifact=artifact,
                reference_price=reference_price,
                equity=equity,
                position_quantity=position.quantity,
            )
            if plan is not None:
                self._ledgers.record(
                    ledger="trade_plan",
                    event_type="TRADE_PLAN_BUILT",
                    correlation_id=correlation_id,
                    actor="runtime.plan_builder",
                    payload={
                        "trade_plan_id": plan.trade_plan_id,
                        "decision_id": plan.decision_id,
                        "symbol": plan.symbol,
                        "side": plan.side.value,
                        "quantity": str(plan.quantity),
                        "notional": str(plan.notional),
                        "stop_loss": str(plan.stop_loss)
                        if plan.stop_loss is not None else None,
                        "take_profit": str(plan.take_profit)
                        if plan.take_profit is not None else None,
                        "risk_budget": str(plan.risk_budget),
                    },
                    parent_id=decision.decision_id,
                )
                created, failed = self._execute_plan(
                    plan, bar, idx, correlation_id, reference_price, equity
                )
                orders_created.extend(created)
                risk_failed = failed

        # -- 9. protective exits for positions from EARLIER bars (§31) -------
        # Positions entered on THIS bar evaluate protection from the
        # next bar onward (never intra-entry-bar lookahead).
        # RUN-OBS-1: exit-path risk failures surface in the outcome.
        exit_orders, exit_failed = self._submit_protection_exits(
            bar, idx, correlation_id, crash
        )
        orders_created.extend(exit_orders)
        risk_failed = risk_failed + exit_failed

        # -- 10. reconciliation after any fills (RT-F2) ------------------------
        if bar_fills:
            self._reconcile_after_fills(correlation_id)

        # -- 11. P&L + memory + persistence --------------------------------------
        position = self._positions.get(
            self._config.symbol, PositionState(symbol=self._config.symbol)
        )
        unrealized = self._pnl_engine.unrealized(position, reference_price)
        pnl_record = self._pnl_engine.record(
            state=position,
            mark_price=reference_price,
            fees_paid=Decimal("0"),
            entry_fill_ids=[f.fill_id for o in self._oms.orders() for f in o.fills],
            exit_fill_ids=[],
            order_ids=[o.order_id for o in self._oms.orders()],
            correlation_id=correlation_id,
        )
        self._ledgers.record(
            ledger="pnl",
            event_type="PNL_SNAPSHOT",
            correlation_id=correlation_id,
            actor="runtime.pnl",
            payload={
                "pnl_id": pnl_record.pnl_id,
                "symbol": pnl_record.symbol,
                "realized": str(pnl_record.realized_pnl),
                "unrealized": str(pnl_record.unrealized_pnl),
                "mark_price": str(reference_price),
            },
        )
        self._memory.record(
            MemoryCategory.MARKET,
            {"bar_index": idx, "close": str(reference_price),
             "correlation_id": correlation_id},
            correlation_id=correlation_id,
            at=ts,
        )
        self._memory.record(
            MemoryCategory.REGIME,
            {"regime": regime_state, "crash_probability": crash["probability"],
             "correlation_id": correlation_id},
            correlation_id=correlation_id,
            at=ts,
        )
        # -- 11. persistence (BLOCKER 1: write failure ⇒ safe HALT) -------
        self._persist_safe(correlation_id)

        return BarOutcome(
            bar_index=idx,
            correlation_id=correlation_id,
            timestamp=ts or datetime.now(UTC),
            accepted=True,
            decision_action=decision.action.value,
            decision_reason=decision.reason,
            prediction_probability=artifact.probability,
            regime=regime_state,
            crash_probability=crash["probability"],
            orders_created=tuple(o.order_id for o in orders_created),
            fills=tuple(f.fill_id for f in bar_fills),
            exits=tuple(e.exit_id for e in exits),
            realized_pnl=str(position.realized_pnl),
            unrealized_pnl=str(unrealized),
            runtime_state=self._state.value,
            risk_failed_checks=risk_failed,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _record_rl_proposal(
        self,
        artifact: PredictionArtifact,
        uncertainty: UncertaintyReport,
        regime_state: str,
        crash: dict,
        position: PositionState,
        reference_price: Decimal,
        equity: Decimal,
        ts: Optional[datetime],
        correlation_id: str,
        parent_id: str,
    ) -> None:
        """Build + ledger + remember ONE governed RL proposal (§28/§44).

        ADVISORY-ONLY record path: nothing here touches the OMS, the
        gateway, the risk gate or the kill switch. A proposal failure
        is an incident (never a trading action). The observation is
        constructed STRICTLY from this bar's already-computed state
        (PIT-safe: no next-bar information can exist yet).
        """
        try:
            observation = RLObservation(
                symbol=artifact.symbol,
                probability=artifact.probability,
                confidence=uncertainty.confidence,
                disagreement=uncertainty.ensemble_disagreement,
                regime=regime_state,
                crash_probability=float(crash.get("probability", 1.0)),
                position_quantity=position.quantity,
                reference_price=reference_price,
                equity=equity,
                unrealized_pnl=self._pnl_engine.unrealized(
                    position, reference_price
                ),
            )
            proposal = self._rl_policy.propose(observation)
        except RLGovernanceError as exc:
            self._ledgers.record(
                ledger="incident",
                event_type="RL_ADVISOR_REFUSED",
                correlation_id=correlation_id,
                actor="runtime.rl_advisor",
                payload={
                    "reason": "observation contract violation",
                    "error": str(exc),
                    "action": "advisor output discarded (fail safe)",
                },
            )
            return
        self._ledgers.record(
            ledger="decision",
            event_type="RL_ACTION_PROPOSED",
            correlation_id=correlation_id,
            actor="runtime.rl_advisor",
            payload={
                "proposal_id": proposal.proposal_id,
                "policy_version": proposal.policy_version,
                "policy_hash": proposal.policy_hash,
                "action": proposal.action.value,
                "target_units": str(proposal.target_units),
                "magnitude_units": str(proposal.magnitude_units),
                "advisory_only": True,
                "bounds_ok": proposal.bounds_ok,
                "ood_flag": proposal.ood_flag,
                "veto_reasons": list(proposal.veto_reasons),
            },
            parent_id=parent_id,
        )
        self._memory.record(
            MemoryCategory.MODEL,
            {"kind": "rl_action_proposal",
             "proposal_id": proposal.proposal_id,
             "action": proposal.action.value,
             "target_units": str(proposal.target_units),
             "advisory_only": True,
             "correlation_id": correlation_id},
            correlation_id=correlation_id,
            at=ts,
        )
        self._metrics.increment("rl_proposals")
        if not proposal.bounds_ok:
            self._metrics.increment("rl_proposals_vetoed")
        if proposal.ood_flag:
            self._metrics.increment("rl_proposals_ood")

    def _execute_plan(
        self,
        plan: TradePlan,
        bar: Mapping,
        bar_index: int,
        correlation_id: str,
        reference_price: Decimal,
        equity: Decimal,
    ):
        """The ONE order path: gate → OMS (create/validate/approve/
        submit/ack). Fills are DEFERRED to the pending-order processor
        (latency: an order submitted on bar N fills on bars N+lag.. —
        never same-bar, §38). Returns (orders, failed_checks)."""
        position = self._positions.get(
            plan.symbol, PositionState(symbol=plan.symbol)
        )
        duplicate = self._duplicate_intent(plan)
        context = RiskContext(
            equity=equity,
            current_units=position.quantity,
            reference_price=reference_price,
            bar_volume=Decimal(str(bar.get("volume") or 0)),
            last_bar_age_bars=0,
            # Stage C (F-14): config-injected context + ceilings
            # (structural paper_mode stays a literal — provenance in
            # GateContextDefaults/GateCeilings).
            market_open=self._gate_context.market_open,
            paper_mode=True,
            model_valid=self._gate_context.model_valid,
            uncertainty=plan.uncertainty,
            crash_probability=float(plan.crash_risk.get("probability", 1.0)),
            max_acceptable_crash_probability=self._config.max_crash_probability,
            max_drawdown_fraction=self._window_drawdown(),
            account_drawdown_fraction=self._account_drawdown(),
            account_drawdown_limit_fraction=(
                self._config.max_account_drawdown_fraction
            ),
            volatility=self._window_volatility(),
            max_volatility=self._gate_ceilings.max_volatility,
            daily_realized_return=self._daily_realized_return(),
            half_spread=self._realism.half_spread,
            max_spread_fraction=self._gate_ceilings.max_spread_fraction,
            duplicate_order_id=duplicate,
            # D-6 measured order-limit state (fail-closed when unknown;
            # measured fresh for EVERY order — no stale snapshots).
            open_order_count=self._open_order_count(),
            max_open_orders=self._risk_limits.max_open_orders,
            orders_submitted_in_window=self._submissions_in_window(
                bar.get("timestamp")
            ),
            max_orders_per_window=self._risk_limits.max_orders_per_window,
            order_rate_window_seconds=self._risk_limits.window_seconds,
        )
        assessment = self._risk_gate.evaluate(
            plan, context, correlation_id, ledger=self._ledgers,
            assessed_at=bar.get("timestamp"),
        )
        if not assessment.passed:
            self._metrics.increment(
                "orders_risk_rejected", len(assessment.failed_checks)
            )
            return [], tuple(c.check for c in assessment.failed_checks)

        order, created = self._oms.create_order(
            plan=plan,
            session_id=self._config.session_id,
            created_at=bar.get("timestamp") or datetime.now(UTC),
            ttl_bars=plan.entry.ttl_bars,
        )
        if not created:
            # Idempotent duplicate — no new order, no execution.
            return [], ()
        self._metrics.increment("orders_created")
        self._oms.validate_order(order.order_id)
        self._oms.risk_approve(order.order_id, assessment)
        # -- Batch 5 (Phase M2 completion): the AUTHORITATIVE venue
        # boundary. With a venue attached, the risk-approved order is
        # submitted through the guarded BrokerSession pipeline (ONE
        # submission path — no hidden direct-execution fallback) and
        # fills EXCLUSIVELY from venue polls in
        # ``_process_pending_orders``. Sequenced BETWEEN risk approval
        # and OMS submission so a definitive venue refusal REJECTS the
        # order (RISK_APPROVED -> REJECTED, ledgered) and an ambiguous
        # outcome marks it UNKNOWN + RECONCILING (§28 — never an
        # inferred failure).
        # Milestone A B3: ONE reservation identity per attempt, live
        # across BOTH the venue path and the internal path — the
        # venue-success fall-through keeps the reservation made BEFORE
        # the broker call (never re-reserved) and the shared tail
        # below finalizes it ACKNOWLEDGED, completing the durable
        # outcome on the authoritative path too.
        reservation_id = None
        if self._venue is not None:
            from data_engine.runtime.broker_execution import (
                VenueSubmissionRefused as _Refused,
                VenueSubmissionUncertain as _Uncertain,
            )
            block_reason = self._venue.submission_block_reason()
            if block_reason is not None:
                self._oms.reject_order(
                    order.order_id,
                    f"venue submission blocked: {block_reason}",
                )
                self._metrics.increment("orders_venue_refused")
                self._ledgers.record(
                    ledger="incident",
                    event_type="VENUE_SUBMISSION_BLOCKED",
                    correlation_id=correlation_id,
                    actor="runtime.execution",
                    payload={
                        "order_id": order.order_id,
                        "reason": block_reason,
                        "action": (
                            "order rejected — the venue refuses new "
                            "submissions while degraded/unhealthy "
                            "(fail closed)"
                        ),
                    },
                )
                return [], (block_reason,)
            # Milestone A B1: durable reservation BEFORE any broker
            # call — capacity/spacing refusal happens strictly
            # earlier than the venue boundary, atomically under the
            # ledger's exclusive flock. A failed reservation leaves
            # no record; a successful one carries the durable order
            # identity.
            if self._submission_ledger is not None:
                try:
                    reservation = self._submission_ledger.reserve(
                        client_order_id=order.order_id,
                        governed_ts=bar["timestamp"],
                    )
                    reservation_id = reservation.reservation_id
                except _LedgerCapacityRefused as exc:
                    self._oms.reject_order(
                        order.order_id,
                        f"submission ledger refused ({exc.reason_code}):"
                        f" {exc}",
                    )
                    self._metrics.increment("orders_capacity_refused")
                    self._ledgers.record(
                        ledger="incident",
                        event_type="SUBMISSION_CAPACITY_REFUSED",
                        correlation_id=correlation_id,
                        actor="runtime.execution",
                        payload={
                            "order_id": order.order_id,
                            "reason_code": exc.reason_code,
                            "action": (
                                "order rejected BEFORE any broker call "
                                "— the durable rate ledger refused the "
                                "reservation (owner-ratified paper "
                                "limits; fail closed)"
                            ),
                        },
                    )
                    return [], ()
            signed_units = plan.quantity if plan.side.value == "BUY" \
                else -plan.quantity
            reduce_only = position.quantity != 0 and (
                (position.quantity > 0) != (signed_units > 0)
            ) and abs(signed_units) <= abs(position.quantity)
            try:
                self._venue.submit_order(
                    order, reduce_only=reduce_only,
                    correlation_id=correlation_id,
                )
                if reservation_id is not None:
                    self._submission_ledger.mark_submitted(
                        reservation_id
                    )
                self._metrics.increment("orders_venue_submitted")
            except _Refused as exc:
                if reservation_id is not None:
                    self._submission_ledger.finalize(
                        reservation_id, "VENUE_REFUSED"
                    )
                self._oms.reject_order(
                    order.order_id,
                    f"venue refused ({exc.reason_code}): {exc}",
                )
                self._metrics.increment("orders_venue_refused")
                self._ledgers.record(
                    ledger="incident",
                    event_type="VENUE_SUBMISSION_REFUSED",
                    correlation_id=correlation_id,
                    actor="runtime.execution",
                    payload={
                        "order_id": order.order_id,
                        "reason_code": exc.reason_code,
                        "action": (
                            "order rejected — the venue never saw it "
                            "(definitive pre-venue refusal, fail closed)"
                        ),
                    },
                )
                return [], ()
            except _Uncertain as exc:
                # Ambiguous submission: the venue MAY hold a live
                # order. NEVER infer failure from a lost ack —
                # UNKNOWN + RECONCILING + EXECUTION_UNCERTAIN until
                # reconciliation resolves from venue truth (§28).
                if reservation_id is not None:
                    self._submission_ledger.finalize(
                        reservation_id, "VENUE_UNCERTAIN"
                    )
                self._oms.submit(
                    order.order_id,
                    submitted_at=bar["timestamp"],
                    bar_index=bar_index,
                )
                self._oms.mark_unknown(
                    order.order_id,
                    f"venue submission outcome uncertain: {exc}",
                )
                self._oms.start_reconciling(order.order_id)
                # D-6: the venue MAY hold this order — it WAS submitted,
                # so it truthfully occupies submission-rate capacity.
                self._record_submission(bar["timestamp"])
                self._metrics.increment("orders_venue_unknown")
                self._flag_execution_uncertain(
                    f"venue submission outcome uncertain for order "
                    f"{order.order_id}: {exc}",
                    correlation_id,
                )
                return [], ()
        # Milestone A B1 — internal path (no venue attached): the
        # durable reservation still gates commit/ack processing —
        # no order reaches acknowledge without a valid reservation.
        # (Venue-success path falls through with its reservation
        # already made BEFORE the broker call — never re-reserved;
        # Milestone A B3: that SAME reservation is finalized
        # ACKNOWLEDGED below once the OMS acknowledges, completing
        # the durable outcome on the authoritative path too.)
        if self._venue is None and self._submission_ledger is not None:
            try:
                reservation = self._submission_ledger.reserve(
                    client_order_id=order.order_id,
                    governed_ts=bar["timestamp"],
                )
                reservation_id = reservation.reservation_id
            except _LedgerCapacityRefused as exc:
                self._oms.reject_order(
                    order.order_id,
                    f"submission ledger refused ({exc.reason_code}):"
                    f" {exc}",
                )
                self._metrics.increment("orders_capacity_refused")
                self._ledgers.record(
                    ledger="incident",
                    event_type="SUBMISSION_CAPACITY_REFUSED",
                    correlation_id=correlation_id,
                    actor="runtime.execution",
                    payload={
                        "order_id": order.order_id,
                        "reason_code": exc.reason_code,
                        "action": (
                            "order rejected before commit/ack — the "
                            "durable rate ledger refused the "
                            "reservation (owner-ratified paper "
                            "limits; fail closed)"
                        ),
                    },
                )
                return [], ()
        self._oms.submit(
            order.order_id,
            submitted_at=bar["timestamp"],
            bar_index=bar_index,
        )
        self._oms.acknowledge(order.order_id)
        if reservation_id is not None:
            if self._venue is None:
                self._submission_ledger.mark_submitted(reservation_id)
            self._submission_ledger.finalize(
                reservation_id, "ACKNOWLEDGED"
            )
        # D-6: gate-passed submission — occupy the rate window.
        self._record_submission(bar["timestamp"])
        if plan.stop_loss is not None or plan.take_profit is not None:
            self._pending_protection[order.order_id] = (
                plan.stop_loss,
                plan.take_profit,
                correlation_id,
            )
        return [order], ()

    def _apply_fill_to_position(self, fill: RuntimeFill, correlation_id: str) -> None:
        position = self._positions.get(
            fill.symbol, PositionState(symbol=fill.symbol)
        )
        updated = position.apply_fill(
            fill_quantity=fill.quantity,
            fill_price=fill.price,
            side=fill.side,
            commission=fill.commission,
            slippage_cost=fill.slippage_cost,
            spread_cost=fill.spread_cost,
            filled_at=fill.filled_at,
            source_event=fill.fill_id,
        )
        self._positions[fill.symbol] = updated
        # PAPER-RUN-PNL-1: cumulative transaction-cost accumulator —
        # OBSERVABILITY ONLY. These costs are ALREADY embedded exactly
        # once in the position's average-cost basis / realized P&L by
        # the authoritative PaperPosition core (paper/models.py
        # price-inclusive basis). It must NEVER be subtracted from
        # account equity again (RUN-EQ-1 double count) and is NOT a
        # P&L measure (RUN-RL-1).
        self._equity_realized = (
            self._equity_realized + fill.commission + fill.slippage_cost
            + fill.spread_cost
        )
        self._ledgers.record(
            ledger="position",
            event_type="POSITION_APPLY_FILL",
            correlation_id=correlation_id,
            actor="runtime.position_book",
            payload={
                "symbol": fill.symbol,
                "fill_id": fill.fill_id,
                "quantity": str(fill.quantity),
                "price": str(fill.price),
                "new_quantity": str(updated.quantity),
                "average_cost": str(updated.average_cost),
                "realized_pnl": str(updated.realized_pnl),
            },
            parent_id=fill.fill_id,
        )

    def _process_pending_orders(
        self, bar: Mapping, bar_index: int, correlation_id: str
    ) -> list:
        """Fill live orders against the newly arrived bar (latency).

        Cursor-based: each order fills only on bars it has not yet
        consumed (fill_index continues the order's numbering — no
        duplicate fill identities, no duplicate fills). Protective
        levels attach after the FIRST fill of an entry order.

        Kill-switch enforcement at FILL time (RUN-KS-1/RUN-KS-2,
        2026-10-12 audit): an in-flight order that would ADD
        exposure is CANCELLED — never filled — while ANY governing
        switch is active (SYMBOL/ORDER scope enforced here;
        GLOBAL/ACCOUNT/PORTFOLIO additionally refuse the whole bar
        through the operating-state guard). Risk-reducing EXIT
        orders are exempt, mirroring the risk gate's documented
        closing-order carve-out (the switch blocks NEW exposure,
        not risk reduction).
        """
        fills: list = []
        from data_engine.runtime.contracts import OrderLifecycle as _LC
        pending_exit_ids = {
            oid for oid, _, _ in self._pending_exits.values()
        }
        for order in list(self._oms.orders()):
            if order.status not in (
                _LC.SUBMITTED, _LC.ACKNOWLEDGED, _LC.PARTIALLY_FILLED
            ):
                continue
            if order.order_id not in pending_exit_ids:
                try:
                    self._kill_switch.check(
                        symbol=order.symbol, order_id=order.order_id,
                    )
                except KillSwitchActive as exc:
                    # Fail closed: cancel the in-flight order (the
                    # already-filled part of a partial order stays;
                    # the remainder is cancelled) and ledger the
                    # incident with the governing-switch description.
                    # With a venue attached the cancellation goes
                    # THROUGH the venue boundary (journal-synced venue
                    # truth; failures ledgered, never silenced).
                    if self._venue is not None:
                        self._venue.cancel_order(
                            order.order_id, correlation_id, str(exc)
                        )
                    self._oms.request_cancel(order.order_id)
                    self._oms.finalize_cancel(order.order_id)
                    self._pending_protection.pop(order.order_id, None)
                    self._metrics.increment("orders_killswitch_cancelled")
                    self._ledgers.record(
                        ledger="incident",
                        event_type="ORDER_CANCELLED_KILL_SWITCH",
                        correlation_id=correlation_id,
                        actor="runtime.execution",
                        payload={
                            "order_id": order.order_id,
                            "symbol": order.symbol,
                            "reason": str(exc),
                            "filled_quantity": str(order.filled_quantity),
                            "cancelled_quantity": str(
                                order.remaining_quantity
                            ),
                            "action": "in-flight order cancelled — "
                                      "governing kill switch active "
                                      "before fill (fail closed)",
                        },
                    )
                    continue
            if order.submitted_at_bar is None or order.submitted_at is None:
                continue
            latency_start = order.submitted_at_bar + self._realism.fill_lag_bars
            cursor = self._order_fill_cursor.get(
                order.order_id, latency_start
            )
            if cursor > bar_index:
                continue  # latency window not reached yet
            ttl_window = order.ttl_bars or self._config.ttl_bars
            try:
                if self._venue is not None:
                    # Batch 5 (Phase M2 completion): fills come
                    # EXCLUSIVELY from venue polls (journal-synced
                    # venue truth; exactly-once delta).
                    new_fills = self._venue.poll_order(
                        order, correlation_id
                    )
                else:
                    new_fills = self._execution.execute(
                        order_id=order.order_id,
                        symbol=order.symbol,
                        side=order.side,
                        order_type=order.order_type,
                        quantity=order.remaining_quantity,
                        bars=self._bars,
                        submitted_at=order.submitted_at,
                        limit_price=order.limit_price,
                        max_bars=ttl_window,
                        from_bar=cursor,
                        start_index=len(order.fills),
                    )
            except Exception as exc:
                # Execution failure: mark the order UNKNOWN and
                # reconcile-before-retry (mandate §28) — never
                # optimistic continuation.
                self._oms.mark_unknown(
                    order.order_id, f"execution adapter failure: {exc}"
                )
                self._oms.start_reconciling(order.order_id)
                self._state = RuntimeState.EXECUTION_UNCERTAIN
                self._ledgers.record(
                    ledger="incident",
                    event_type="EXECUTION_FAILURE",
                    correlation_id=correlation_id,
                    actor="runtime.execution",
                    payload={
                        "order_id": order.order_id,
                        "error": str(exc),
                        "action": "ORDER_UNKNOWN + RECONCILING (§28)",
                    },
                )
                continue
            self._apply_execution_fills(
                order, new_fills, correlation_id, fills
            )
        return fills

    def _apply_execution_fills(
        self, order, new_fills: list, correlation_id: str,
        fills_sink: list,
    ) -> None:
        """Apply execution fills through the ONE authoritative path
        (OMS -> position -> metrics -> memory -> protection attach).

        Shared VERBATIM by the internal execution adapter path and the
        Batch-5 authoritative venue path (venue polls) — identical
        semantics, identical ledger/metrics events, so venue-mode runs
        are bit-identical to internal-mode runs. ``order`` is the
        caller's (possibly stale-within-the-batch) OMS order snapshot
        — RUN-PM-1: the partial-fill metric re-queries the LIVE OMS
        order after each fill, so the COMPLETING fill (live remaining
        hits zero) is never counted as a partial-fill event."""
        for fill in new_fills:
            self._oms.apply_fill(order.order_id, fill)
            self._apply_fill_to_position(fill, correlation_id)
            fills_sink.append(fill)
            self._metrics.increment("fills")
            try:
                live = self._oms.order(order.order_id)
                still_partial = live.remaining_quantity > 0
            except Exception:
                # The order vanished from the OMS mid-batch — the
                # metric cannot be proven, so it is not counted
                # (observability only; the authoritative OMS/position
                # updates above already happened or raised).
                still_partial = False
            if still_partial:
                self._metrics.increment("partial_fill_events")
            self._memory.record(
                MemoryCategory.EXECUTION,
                {"order_id": order.order_id, "fill_id": fill.fill_id,
                 "quantity": str(fill.quantity), "price": str(fill.price),
                 "correlation_id": correlation_id},
                correlation_id=correlation_id,
                at=fill.filled_at,
            )
        if new_fills:
            self._order_fill_cursor[order.order_id] = (
                new_fills[-1].bar_index + 1
            )
            # Attach protective levels after the first entry fill.
            protection = self._pending_protection.get(order.order_id)
            if protection is not None:
                sl, tp, prot_corr = protection
                fresh = self._positions.get(
                    order.symbol, PositionState(symbol=order.symbol)
                )
                if not fresh.is_flat:
                    if sl is not None:
                        fresh, _ = self._exit_manager.set_stop_loss(
                            fresh, sl, prot_corr, fill.filled_at
                        )
                    if tp is not None:
                        fresh, _ = self._exit_manager.set_take_profit(
                            fresh, tp, prot_corr, fill.filled_at
                        )
                    self._positions[order.symbol] = fresh
                    self._pending_protection.pop(order.order_id, None)

    # ------------------------------------------------------------------
    # Batch 5 (Phase M2 completion): authoritative-venue helpers
    # ------------------------------------------------------------------
    def _flag_execution_uncertain(self, reason: str,
                                  correlation_id: str) -> None:
        """Fail-closed transition into EXECUTION_UNCERTAIN with an
        auditable incident record (used by the authoritative venue
        seam for ambiguous submissions/recoveries)."""
        self._state = RuntimeState.EXECUTION_UNCERTAIN
        self._ledgers.record(
            ledger="incident",
            event_type="RUNTIME_EXECUTION_UNCERTAIN",
            correlation_id=correlation_id,
            actor="runtime.venue",
            payload={
                "reason": reason,
                "action": (
                    "bar processing + new submissions blocked until "
                    "venue reconciliation resolves the ambiguity "
                    "(fail closed; never an inferred failure)"
                ),
            },
        )

    def _resolve_venue_order(self, order_id: str, venue_status,
                             correlation_id: str) -> None:
        """Adopt the venue-truth resolution for ONE ambiguous
        (UNKNOWN/RECONCILING) OMS order: apply any not-yet-applied
        hosted fills EXACTLY ONCE (the shared authoritative path),
        then resolve the lifecycle per the venue's status.

        ``venue_status`` is the venue-neutral status enum VALUE (a
        string) — the runtime never imports the brokers package (the
        broker_execution seam is the only boundary)."""
        from data_engine.runtime.contracts import OrderLifecycle as _LC
        status_value = (
            venue_status.value if hasattr(venue_status, "value")
            else str(venue_status)
        )
        order = self._oms.order(order_id)
        venue_fills = self._venue.adapter.runtime_fills(order_id)
        applied = len(order.fills)
        if applied > len(venue_fills):
            raise RuntimeContractError(
                f"venue resolution for {order_id!r}: the OMS holds "
                f"{applied} fills but the venue hosts "
                f"{len(venue_fills)} — books diverged (fail closed)"
            )
        delta = list(venue_fills[applied:])
        if delta:
            self._apply_execution_fills(order, delta, correlation_id, [])
        order = self._oms.order(order_id)
        if order.status in (_LC.UNKNOWN, _LC.RECONCILING):
            resolved = {
                "OPEN": _LC.SUBMITTED,
                "PARTIALLY_FILLED": _LC.PARTIALLY_FILLED,
                "FILLED": _LC.FILLED,
                "CANCELLED": _LC.CANCELLED,
                "REJECTED": _LC.FAILED,
                "EXPIRED": _LC.FAILED,
            }.get(status_value)
            if resolved is None:
                raise RuntimeContractError(
                    f"venue resolution for {order_id!r}: unresolvable "
                    f"venue status {status_value!r} (fail closed)"
                )
            self._oms.resolve_reconciling(order_id, resolved)
        self._ledgers.record(
            ledger="incident",
            event_type="VENUE_ORDER_RESOLVED",
            correlation_id=correlation_id,
            actor="runtime.venue",
            payload={
                "order_id": order_id,
                "venue_status": status_value,
                "fills_adopted": len(delta),
                "action": "venue truth adopted after reconciliation "
                          "(exactly-once fill application)",
            },
        )

    def _resume_after_venue_reconciliation(self,
                                            correlation_id: str) -> None:
        """Resume RUNNING after a CLEAN venue reconciliation resolved
        every ambiguous order (recovery reconciles FIRST, then
        resumes — the restart discipline, in-session)."""
        if self._state is not RuntimeState.EXECUTION_UNCERTAIN:
            return
        self._state = RuntimeState.RUNNING
        self._ledgers.record(
            ledger="incident",
            event_type="RUNTIME_RESUMED_AFTER_VENUE_RECONCILIATION",
            correlation_id=correlation_id,
            actor="runtime.venue",
            payload={
                "action": "clean reconciliation resolved all ambiguous "
                          "orders; resuming (reconcile-then-resume)",
            },
        )

    def _record_completed_exits(self, bar: Mapping, correlation_id: str) -> list:
        """Record ExitRecords for exit orders that have now filled (§31)."""
        exits: list = []
        for symbol, pending in list(self._pending_exits.items()):
            order_id, reason, snapshot = pending
            try:
                order = self._oms.order(order_id)
            except Exception:
                self._pending_exits.pop(symbol, None)
                continue
            if order.status is OrderLifecycle.FILLED:
                current = self._positions.get(
                    symbol, PositionState(symbol=symbol)
                )
                # Hybrid state: quantity/avg from the trigger snapshot,
                # realized P&L AFTER the exit fills (mandate §31 linkage).
                hybrid = PositionState(
                    symbol=symbol,
                    quantity=snapshot.quantity,
                    average_cost=snapshot.average_cost,
                    realized_pnl=current.realized_pnl,
                )
                record = self._exit_manager.record_exit(
                    reason=reason,
                    state=hybrid,
                    timestamp=bar.get("timestamp") or datetime.now(UTC),
                    order_ids=(order_id,),
                    fill_ids=tuple(f.fill_id for f in order.fills),
                    correlation_id=correlation_id,
                )
                exits.append(record)
                self._pending_exits.pop(symbol, None)
            elif order.status in (
                OrderLifecycle.CANCELLED, OrderLifecycle.EXPIRED,
                OrderLifecycle.REJECTED, OrderLifecycle.FAILED,
            ):
                # Exit order did not complete: position remains at risk;
                # protection re-evaluates on the next bar (new exit order).
                self._pending_exits.pop(symbol, None)
                self._ledgers.record(
                    ledger="incident",
                    event_type="EXIT_ORDER_INCOMPLETE",
                    correlation_id=correlation_id,
                    actor="runtime.exit_manager",
                    payload={
                        "order_id": order_id,
                        "symbol": symbol,
                        "status": order.status.value,
                        "reason": "exit order ended without filling; "
                                  "protection will re-trigger",
                    },
                )
        return exits

    def _submit_protection_exits(
        self, bar: Mapping, bar_index: int,
        correlation_id: str, crash: Mapping
    ) -> tuple:
        """SL/TP/crash exit submission for positions from earlier bars.

        Returns ``(orders, failed_checks)`` — RUN-OBS-1: exit-path
        risk rejections are NOT discarded; the failed-check names
        surface in ``BarOutcome.risk_failed_checks`` (they are
        already ledgered as ``RISK_ASSESSMENT_FAIL`` by the gate).
        """
        orders: list = []
        failed: list = []
        bar_ts = bar.get("timestamp") or datetime.now(UTC)
        bar_ts_utc = bar_ts.astimezone(UTC) if getattr(bar_ts, "tzinfo", None) else None
        for symbol, position in list(self._positions.items()):
            if position.is_flat:
                continue
            if (
                bar_ts_utc is not None
                and position.last_update is not None
                and position.last_update == bar_ts_utc
            ):
                continue  # entered this bar — protection from next bar
            if symbol in self._pending_exits:
                continue  # exit already in flight
            hit = self._exit_manager.evaluate_bar(position, bar)
            reason = None
            if hit is not None:
                reason = hit[0]
            elif (
                crash.get("probability", 0.0)
                >= self._config.crash_exit_probability
            ):
                reason = ExitReason.CRASH_EXIT
            if reason is None:
                continue
            exit_plan = self._build_exit_plan(
                position, reason, bar, correlation_id
            )
            if exit_plan is None:
                continue
            created, exit_failed = self._execute_plan(
                exit_plan, bar, bar_index, correlation_id,
                Decimal(str(bar["close"])),
                self._current_equity(Decimal(str(bar["close"]))),
            )
            failed.extend(exit_failed)
            if created:
                self._pending_exits[symbol] = (
                    created[0].order_id, reason, position,
                )
                orders.extend(created)
        return orders, tuple(failed)

    def _reconcile_after_fills(self, correlation_id: str) -> None:
        """Post-fill three-way reconciliation (RT-F2; §32)."""
        report = self._reconciliation.reconcile(self._oms, self._positions)
        if not report.ok:
            self._state = RuntimeState.RECONCILIATION_REQUIRED
            self._metrics.increment("reconciliation_mismatches")
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_RECONCILIATION_REQUIRED",
                correlation_id=correlation_id,
                actor="runtime",
                payload={"mismatches": list(report.mismatches)},
            )

    def _build_exit_plan(self, position: PositionState, reason: ExitReason,
                         bar: Mapping, correlation_id: str):
        """Build the closing plan for a protective exit (§31)."""
        from data_engine.runtime.contracts import (
            RejectedAlternative,
        )
        decision = Decision(
            decision_id=prefixed_hash(
                "rtdec.",
                {"kind": "exit_decision", "reason": reason.value,
                 "position": position.position_id},
            ),
            action=DecisionAction.CLOSE,
            symbol=position.symbol,
            timestamp=bar["timestamp"],
            prediction_ids=("exit-protection",),
            model_versions=("runtime.exit_manager",),
            uncertainty=UncertaintyReport(
                confidence=1.0, entropy=0.0, ensemble_disagreement=0.0
            ),
            regime="EXIT",
            crash_risk={"probability": 0.0},
            portfolio_state={"position_quantity": str(position.quantity)},
            reason=f"protective exit: {reason.value} (position protection)",
            rejected_alternatives=(
                RejectedAlternative(
                    action=DecisionAction.HOLD,
                    reason="holding through a triggered protective level is "
                           "never an alternative",
                ),
            ),
            correlation_id=correlation_id,
        )
        reference = Decimal(str(bar["close"]))
        artifact = PredictionArtifact(
            prediction_id=f"exit-{reason.value.lower()}",
            symbol=position.symbol,
            horizon=1,
            timestamp=bar["timestamp"],
            prediction="EXIT",
            probability=1.0,
            expected_return=0.0,
            volatility=0.01,
            uncertainty=UncertaintyReport(
                confidence=1.0, entropy=0.0, ensemble_disagreement=0.0
            ),
            model_versions=("runtime.exit_manager",),
            feature_version=self._config.feature_version,
            dataset_version=self._config.dataset_version,
            regime="EXIT",
            crash_risk={"probability": 0.0},
            provenance={"origin": "protective_exit"},
            correlation_id=correlation_id,
        )
        return self._plan_builder.build(
            decision=decision,
            artifact=artifact,
            reference_price=reference,
            equity=self._current_equity(reference),
            position_quantity=position.quantity,
        )

    def _duplicate_intent(self, plan: TradePlan) -> Optional[str]:
        """Detect a same-plan live order (duplicate order protection)."""
        from data_engine.runtime.oms import idempotent_order_id
        oid = idempotent_order_id(
            session_id=self._config.session_id,
            trade_plan_id=plan.trade_plan_id,
            decision_id=plan.decision_id,
            correlation_id=plan.correlation_id,
            symbol=plan.symbol,
            side=plan.side.value,
            order_type=plan.entry.order_type,
            quantity=plan.quantity,
            limit_price=plan.entry.limit_price,
        )
        existing = self._oms.order(oid) if self._oms_exists(oid) else None
        if existing is not None and not existing.is_terminal:
            return oid
        return None

    def _oms_exists(self, order_id: str) -> bool:
        try:
            self._oms.order(order_id)
            return True
        except Exception:
            return False

    def _classify_regime(self) -> str:
        closes = [float(b["close"]) for b in self._bars]
        if len(closes) < 21:
            return "UNKNOWN"
        returns = [
            closes[i] / closes[i - 1] - 1.0 for i in range(1, len(closes))
        ]
        recent = returns[-20:]
        vol_20 = _std(recent)
        long_vol = _std(returns[-40:]) if len(returns) >= 40 else vol_20
        vol_ratio = vol_20 / long_vol if long_vol > 0 else 1.0
        window = closes[-40:]
        peak = max(window)
        dd_depth = (peak - closes[-1]) / peak if peak > 0 else 0.0
        mom_20 = closes[-1] / closes[-21] - 1.0
        features = RegimeFeatures(
            vol_20=vol_20, vol_ratio=vol_ratio, dd_depth=dd_depth,
            mom_20=mom_20,
        )
        raw = self._regime_engine.classify(features)
        return _REGIME_MAP.get(raw.upper(), "UNKNOWN")

    def _assess_crash(self, disagreement: float) -> dict:
        """Independent crash intelligence (mandate §20).

        Deterministic stress model over: drawdown stress, volatility
        stress, and model disagreement — deliberately INDEPENDENT of
        the directional prediction signal. Output feeds NO_TRADE /
        CRASH_EXIT decisions and can never be overridden by strategy
        signals.
        """
        closes = [float(b["close"]) for b in self._bars]
        dd = self._window_drawdown()
        vol = self._window_volatility()
        p = 0.02
        if dd is not None:
            if dd >= 0.20:
                p += 0.40
            elif dd >= 0.10:
                p += 0.20
        if vol is not None:
            if vol >= 0.05:
                p += 0.15
            elif vol >= 0.03:
                p += 0.08
        p += 0.25 * min(disagreement, 0.4)
        p = round(min(p, 0.99), 12)
        severity = "HIGH" if p >= 0.5 else ("MEDIUM" if p >= 0.3 else "LOW")
        return {
            "probability": p,
            "severity": severity,
            "horizon": self._config.horizon,
            "volatility_stress": round(vol, 12) if vol is not None else None,
            "drawdown_stress": round(dd, 12) if dd is not None else None,
            "model_disagreement": round(disagreement, 12),
            "liquidity_stress": None,
            "correlation_stress": None,
            "regime": self._classify_regime(),
        }

    def _window_volatility(self) -> float:
        closes = [float(b["close"]) for b in self._bars]
        if len(closes) < 21:
            return 0.0  # insufficient data → vol band check fails closed upstream? (0 is in-band; staleness handles freshness)
        returns = [
            closes[i] / closes[i - 1] - 1.0
            for i in range(len(closes) - 20, len(closes))
        ]
        return round(_std(returns), 12)

    def _window_drawdown(self) -> float:
        closes = [float(b["close"]) for b in self._bars]
        if not closes:
            return 0.0
        peak = closes[0]
        worst = 0.0
        for c in closes:
            peak = max(peak, c)
            if peak > 0:
                worst = max(worst, (peak - c) / peak)
        return round(worst, 12)

    def _daily_realized_return(self) -> float:
        """TRUE daily account P&L return (PAPER-RUN-PNL-1).

        Mark-to-market (realized + unrealized) account-equity return
        between the current UTC day's first admitted bar and the
        latest admitted bar's close. Transaction costs enter exactly
        once via the cost-embedded basis. The day-start anchor is
        deterministically reconstructed by replaying every OMS fill
        admitted before the day's first bar (see
        :meth:`_day_start_equity`) — no persisted day state, so the
        value is identical before and after a restart.

        Fail-closed (RUN-RL-1): an anchor that cannot be established
        or is non-positive yields -1.0 so the mandatory ``loss_limit``
        risk-gate check FAILS (new orders refused, never permitted on
        an unprovable loss state). Before the first admitted bar no
        day has started and nothing can have been lost: 0.0.
        """
        if not self._bars:
            return 0.0
        try:
            anchor = self._day_start_equity()
            if anchor <= 0:
                return -1.0
            mark = Decimal(str(self._bars[-1]["close"]))
            current = self._current_equity(mark)
            return float((current - anchor) / anchor)
        except Exception:
            return -1.0

    def _day_start_equity(self) -> Decimal:
        """Account equity at the start of the CURRENT UTC day
        (PAPER-RUN-PNL-1 acceptance interface).

        Deterministic reconstruction: every OMS fill whose
        ``bar_index`` precedes the first admitted bar of the current
        UTC day is replayed onto a fresh :class:`PositionState`
        (costs embedded once — identical accounting to the live
        position book), then marked at the previous day's last close.
        Before the session's first bar the anchor is the initial
        equity. Bars timestamps are strictly increasing (BUG-007
        discipline) so the day's first bar is found by scanning
        backwards from the latest bar.
        """
        if not self._bars:
            return self._config.initial_equity
        last_ts = self._bars[-1].get("timestamp")
        if last_ts is None or not getattr(last_ts, "tzinfo", None):
            raise RuntimeContractError(
                "cannot establish the daily anchor: latest bar timestamp "
                "is not timezone-aware (fail closed)"
            )
        day = last_ts.astimezone(UTC).date()
        cached = self._day_anchor_cache
        if cached is not None and cached[0] == day:
            return cached[1]
        day_start_index = len(self._bars) - 1
        for i in range(len(self._bars) - 1, -1, -1):
            ts_i = self._bars[i].get("timestamp")
            if ts_i is None or not getattr(ts_i, "tzinfo", None) \
                    or ts_i.astimezone(UTC).date() != day:
                break
            day_start_index = i
        # Replay all fills admitted BEFORE the day's first bar onto a
        # fresh position book (deterministic; reconciliation replays
        # fills the same way).
        replayed: dict = {}
        for order in self._oms.orders():
            for fill in order.fills:
                if fill.bar_index is None or fill.bar_index < day_start_index:
                    state = replayed.get(
                        fill.symbol, PositionState(symbol=fill.symbol)
                    )
                    replayed[fill.symbol] = state.apply_fill(
                        fill_quantity=fill.quantity,
                        fill_price=fill.price,
                        side=fill.side,
                        commission=fill.commission,
                        slippage_cost=fill.slippage_cost,
                        spread_cost=fill.spread_cost,
                        filled_at=fill.filled_at,
                        source_event=fill.fill_id,
                    )
        anchor = self._config.initial_equity
        for state in replayed.values():
            anchor += state.realized_pnl
        if day_start_index > 0:
            prev_close = Decimal(
                str(self._bars[day_start_index - 1]["close"])
            )
            pos = replayed.get(self._config.symbol)
            if pos is not None and not pos.is_flat:
                anchor += self._pnl_engine.unrealized(pos, prev_close)
        self._day_anchor_cache = (day, anchor)
        return anchor

    def _current_equity(self, mark_price: Decimal) -> Decimal:
        """TRUE account equity (PAPER-RUN-PNL-1).

        initial_equity + realized P&L + unrealized at ``mark_price``.
        Transaction costs enter EXACTLY ONCE — embedded in the
        average-cost basis and realized P&L by the authoritative
        ``PaperPosition`` core (price-inclusive basis). The persisted
        ``_equity_realized`` accumulator is cost observability and
        must never be subtracted here (RUN-EQ-1 double count).
        """
        position = self._positions.get(
            self._config.symbol, PositionState(symbol=self._config.symbol)
        )
        unrealized = self._pnl_engine.unrealized(position, mark_price)
        return (
            self._config.initial_equity
            + position.realized_pnl
            + unrealized
        )

    # ------------------------------------------------------------------
    # D-6 runtime order-limit state (order rate + open orders)
    # ------------------------------------------------------------------
    def _open_order_count(self) -> int:
        """Open (unresolved) OMS orders = LIVE_STATES + AMBIGUOUS_STATES.

        Ambiguous outcomes (UNKNOWN/RECONCILING) COUNT as open: a
        possibly-live venue order must keep occupying capacity until
        reconciliation resolves it from venue truth (conservative
        direction). Reconstructed from OMS state after restarts — the
        open-order control survives state restore.
        """
        from data_engine.runtime.oms import AMBIGUOUS_STATES, LIVE_STATES

        return sum(
            1
            for o in self._oms.orders()
            if o.status in LIVE_STATES or o.status in AMBIGUOUS_STATES
        )

    def _prune_submissions(self, now_ts: datetime) -> None:
        """Drop submissions older than the governed-time window.
        On any timestamp-comparison failure the entry is KEPT (an
        over-count blocks more — the fail-safe direction)."""
        window = self._risk_limits.window_seconds
        kept = []
        for t in self._submission_times:
            try:
                age = (now_ts - t).total_seconds()
            except TypeError:
                kept.append(t)
                continue
            if 0 <= age <= window:
                kept.append(t)
        self._submission_times = kept

    def _record_submission(self, ts: Optional[datetime]) -> None:
        """Record a gate-passed OMS submission (governed time: the bar
        timestamp drives determinism/replay; wall clock only as a
        fallback when a bar carries no timestamp).

        Milestone A B1: when a durable SubmissionLedger is attached,
        it is THE authoritative rate accounting — the volatile
        in-memory list is bypassed (F-01: restart no longer wipes
        the budget)."""
        if self._submission_ledger is not None:
            return  # the durable ledger already holds the record
        self._submission_times.append(
            ts if ts is not None else datetime.now(UTC)
        )

    def _submissions_in_window(self, now_ts: Optional[datetime]) -> int:
        if self._submission_ledger is not None:
            # Durable accounting (B1): the ledger counts consumed
            # slots on the wall-clock window — cross-process and
            # restart-stable. Governed time remains the fallback for
            # the legacy no-ledger path below.
            return self._submission_ledger.count_in_window()
        if now_ts is None:
            now_ts = datetime.now(UTC)
        self._prune_submissions(now_ts)
        return len(self._submission_times)

    # ------------------------------------------------------------------
    # ACCOUNT-equity drawdown limit (RUN-DD-1)
    # ------------------------------------------------------------------
    def _risk_context_for_bridge(self, plan: TradePlan,
                                 reference_price: Decimal,
                                 latest_bar: Mapping) -> "RiskContext":
        """Build the live-state RiskContext for a broker-bridge order
        (Phase M2 seam — ``runtime/broker_execution.py``).

        The context is synthesised from the runtime's AUTHORITATIVE
        state at the latest admitted bar: TRUE account equity
        (PAPER-RUN-PNL-1), the live position for the plan's symbol,
        the symbol-window drawdown AND the RUN-DD-1 account drawdown,
        window volatility, and the true daily return. Paper mode is
        structurally true (the runtime is paper-only); model validity
        was self-checked at start(). The plan's own uncertainty/
        crash fields carry the deterministic external-order marker.
        """
        position = self._positions.get(
            plan.symbol, PositionState(symbol=plan.symbol)
        )
        return RiskContext(
            equity=self._current_equity(reference_price),
            current_units=position.quantity,
            reference_price=reference_price,
            bar_volume=Decimal(str(latest_bar.get("volume") or 0)),
            # RUN-ST-1: the HONEST in-session bar age for EXTERNAL
            # orders. With the wall-clock watchdog enabled, the age is
            # the wall-clock distance to the latest admitted bar,
            # expressed in the governed bar-count unit (ceil of
            # age/expected-interval) — a stalled feed then fails the
            # mandatory ``data_staleness`` check fail-closed instead
            # of the pre-fix hardcoded always-fresh 0. With the
            # watchdog disabled (the deterministic-replay default) the
            # age is 0 — honest within the replay frame, where bar
            # timestamps legitimately trail the wall clock.
            last_bar_age_bars=self._bridge_bar_age(latest_bar),
            # Stage C (F-14): config-injected context + ceilings
            # (structural paper_mode stays a literal — provenance in
            # GateContextDefaults/GateCeilings).
            market_open=self._gate_context.market_open,
            paper_mode=True,
            model_valid=self._gate_context.model_valid,
            uncertainty=plan.uncertainty,
            crash_probability=0.0,
            max_acceptable_crash_probability=(
                self._config.max_crash_probability
            ),
            max_drawdown_fraction=self._window_drawdown(),
            account_drawdown_fraction=self._account_drawdown(),
            account_drawdown_limit_fraction=(
                self._config.max_account_drawdown_fraction
            ),
            volatility=self._window_volatility(),
            max_volatility=self._gate_ceilings.max_volatility,
            daily_realized_return=self._daily_realized_return(),
            half_spread=self._realism.half_spread,
            max_spread_fraction=self._gate_ceilings.max_spread_fraction,
            # D-6 measured order-limit state (fail-closed when unknown;
            # measured fresh for EVERY order — no stale snapshots).
            open_order_count=self._open_order_count(),
            max_open_orders=self._risk_limits.max_open_orders,
            orders_submitted_in_window=self._submissions_in_window(
                latest_bar.get("timestamp")
            ),
            max_orders_per_window=self._risk_limits.max_orders_per_window,
            order_rate_window_seconds=self._risk_limits.window_seconds,
        )

    def _bridge_bar_age(self, latest_bar: Mapping) -> int:
        """Wall-clock-derived bar age (in bars) for bridge risk
        contexts (RUN-ST-1). See ``_risk_context_for_bridge``."""
        if self._config.max_feed_staleness_seconds is None:
            return 0
        ts = latest_bar.get("timestamp")
        if ts is None or getattr(ts, "tzinfo", None) is None:
            # Freshness cannot be proven for an unmeasurable bar —
            # express maximal staleness so the mandatory check fails
            # closed (never neutral).
            return 10 ** 6
        age_seconds = (
            self._wall_clock() - ts.astimezone(UTC)
        ).total_seconds()
        if age_seconds <= 0:
            return 0
        interval = max(1.0, float(self._config.expected_interval_seconds))
        return max(0, int(math.ceil(age_seconds / interval)))

    def _account_drawdown(self) -> Optional[float]:
        """ACCOUNT-equity drawdown fraction (RUN-DD-1).

        Calculation (mark-to-market, PAPER-RUN-PNL-1 accounting):
        ``drawdown = (peak - current) / peak`` where ``current`` is
        the TRUE account equity at the LATEST ADMITTED bar's close
        (initial + realized + unrealized; costs exactly once) and
        ``peak`` is the session high-water mark of that same equity
        over every admitted bar close — deterministically replayed
        from the persisted bar history + OMS fills (the identical
        reconstruction discipline as the daily anchor: no new
        persisted field, so the value is restart-stable by
        construction). The mark is always the latest admitted bar —
        the freshest equity state the runtime possesses (feed
        staleness itself is RUN-ST-1, a separate blocker).

        Fail-closed semantics:

        - fresh session (no bars): ``0.0`` — peak == current ==
          initial, nothing is at risk yet;
        - unanchorable equity path (a fill whose ``bar_index`` is
          missing or outside the admitted bar history): ``None`` —
          the mandatory ``account_drawdown`` risk-gate check then
          REFUSES new orders ("unknown — fail closed");
        - non-positive current equity: ``1.0`` — a wiped-out
          account is past any limit (maximal measured drawdown).
        """
        if not self._bars:
            return 0.0
        try:
            peak = self._peak_account_equity()
            if peak is None or peak <= 0:
                return None
            mark = Decimal(str(self._bars[-1]["close"]))
            current = self._current_equity(mark)
            if current <= 0:
                return 1.0
            if current >= peak:
                return 0.0
            return float((peak - current) / peak)
        except Exception:
            # Unmeasurable is NOT tradable: None fails closed at the
            # risk gate (never a neutral 0.0).
            return None

    def _peak_account_equity(self) -> Optional[Decimal]:
        """Session high-water mark of mark-to-market account equity.

        Deterministic replay: every OMS fill is re-applied to a
        fresh :class:`PositionState` book in ``(bar_index,
        fill_index)`` order — exactly the authoritative
        cost-embedded accounting — and equity is marked at every
        admitted bar's close (realized across symbols + unrealized
        for the configured symbol, mirroring the day-anchor
        reconstruction). Pure function of persisted state (bars +
        OMS fills): identical before and after a restart, in-session
        and post-restore.

        A fill whose ``bar_index`` is missing or outside the
        admitted bar history makes the path unanchorable → ``None``
        (fail closed). The governed execution adapter can never
        produce such a fill — only corrupted or foreign restored
        state can (defence in depth).
        """
        if not self._bars:
            return self._config.initial_equity
        n_bars = len(self._bars)
        fills: list = []
        for order in self._oms.orders():
            for fill in order.fills:
                idx = fill.bar_index
                if idx is None or idx < 0 or idx >= n_bars:
                    return None
                fills.append(fill)
        fills.sort(key=lambda f: (f.bar_index, f.fill_index))
        key = (n_bars, len(fills))
        cached = self._dd_peak_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        replayed: dict = {}
        peak = self._config.initial_equity
        fill_i = 0
        n_fills = len(fills)
        for bar_i in range(n_bars):
            while fill_i < n_fills and fills[fill_i].bar_index <= bar_i:
                f = fills[fill_i]
                state = replayed.get(
                    f.symbol, PositionState(symbol=f.symbol)
                )
                replayed[f.symbol] = state.apply_fill(
                    fill_quantity=f.quantity,
                    fill_price=f.price,
                    side=f.side,
                    commission=f.commission,
                    slippage_cost=f.slippage_cost,
                    spread_cost=f.spread_cost,
                    filled_at=f.filled_at,
                    source_event=f.fill_id,
                )
                fill_i += 1
            mark = Decimal(str(self._bars[bar_i]["close"]))
            equity = self._config.initial_equity + sum(
                s.realized_pnl for s in replayed.values()
            )
            pos = replayed.get(self._config.symbol)
            if pos is not None and not pos.is_flat:
                equity += self._pnl_engine.unrealized(pos, mark)
            if equity > peak:
                peak = equity
        self._dd_peak_cache = (key, peak)
        return peak

    def _enforce_account_drawdown(
        self, bar_index: int, correlation_id: str
    ) -> None:
        """RUN-DD-1 enforcement point (called on EVERY admitted bar,
        after that bar's fills and before any new decision).

        - Unknown measure (``None``): ledgered as
          ``ACCOUNT_DRAWDOWN_UNKNOWN`` — new orders fail closed at
          the gate; NO trip on an unknown measure (the switch needs
          human reset, so it is reserved for MEASURED breaches).
        - Strict breach (``drawdown > limit``): ledgered as
          ``ACCOUNT_DRAWDOWN_LIMIT_BREACH`` with the full
          calculation inputs, then the ACCOUNT kill switch is
          tripped (auditable source ``runtime.risk.drawdown``) and
          the session HALTS terminally. The trip persists
          IMMEDIATELY (BLOCKER 12: a crash right after the trip must
          never lose the state on disk); a restart NEVER clears it
          (critical-switch loud refusal at start).

        In-flight entry orders are frozen by the terminal HALT (no
        bar is processed, so no remainder can ever fill past the
        limit); closing orders later in the SAME bar remain
        permitted via the risk-reduction carve-out.
        """
        if self._state is not RuntimeState.RUNNING:
            return  # already in a non-trading state — nothing to enforce
        drawdown = self._account_drawdown()
        limit = self._config.max_account_drawdown_fraction
        if drawdown is None:
            self._ledgers.record(
                ledger="incident",
                event_type="ACCOUNT_DRAWDOWN_UNKNOWN",
                correlation_id=correlation_id,
                actor="runtime.risk.drawdown",
                payload={
                    "bar_index": bar_index,
                    "reason": "account equity path not reconstructible "
                              "(unanchorable fill) — the risk gate "
                              "refuses new orders fail-closed",
                    "action": "no trip on an unknown measure; "
                              "investigate the fill ledger",
                },
            )
            return
        if drawdown <= limit:
            return
        peak = self._peak_account_equity()
        mark = Decimal(str(self._bars[-1]["close"])) if self._bars \
            else self._config.initial_equity
        current = self._current_equity(mark)
        self._metrics.increment("drawdown_limit_breaches")
        self._ledgers.record(
            ledger="incident",
            event_type="ACCOUNT_DRAWDOWN_LIMIT_BREACH",
            correlation_id=correlation_id,
            actor="runtime.risk.drawdown",
            payload={
                "drawdown_fraction": round(drawdown, 12),
                "limit_fraction": limit,
                "peak_equity": str(peak) if peak is not None else None,
                "current_equity": str(current),
                "mark_price": str(mark),
                "bar_index": bar_index,
                "action": "ACCOUNT kill switch tripped + terminal HALT "
                          "(RUN-DD-1: the account's own drawdown is the "
                          "protected quantity)",
            },
        )
        self._kill_switch.trip(
            scope=KillSwitchScope.ACCOUNT,
            reason=(
                f"account drawdown {drawdown:.6f} exceeds limit "
                f"{limit:.6f} (RUN-DD-1 account-equity drawdown limit)"
            ),
            source="runtime.risk.drawdown",
        )
        self._metrics.increment("kill_switch_trips")
        self._persist_safe(f"kill-switch:ACCOUNT:*")
        self.halt(
            "ACCOUNT kill switch tripped by the drawdown limit: "
            f"{drawdown:.6f} > {limit:.6f}"
        )

    def _persist_safe(self, correlation_id: str) -> None:
        """Persist state; on write failure HALT safely (BLOCKER 1).

        Persistence is authoritative: continuing on unverifiable
        state is NEVER best-effort. The bar's outcome is still
        reported honestly, the runtime HALTS, and the NEXT bar is
        refused.
        """
        if self._store is None:
            return
        try:
            self._persist(correlation_id)
        except StateStoreError as exc:
            self._state = RuntimeState.HALTED
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_HALTED",
                correlation_id=correlation_id,
                actor="runtime",
                payload={
                    "reason": f"persistence write failure: {exc}",
                    "from": "RUNNING",
                    "action": "safe halt — execution state could not "
                              "be made durable (BLOCKER 1)",
                },
            )

    def _persist(self, correlation_id: str) -> None:
        """Persist the COMPLETE execution state (BLOCKER 5).

        Every execution-critical in-memory field listed in
        EXECUTION_STATE_FIELDS is persisted atomically: bar history,
        bar cursor, positions incl. SL/TP, OMS orders incl. fills,
        kill-switch states, FULL ledger chains (not just heads),
        structured memory, fill cursors, pending protection/exits,
        the bad-bar counter, realized equity, and the session/config/
        model identity block.
        """
        state = {
            "schema": EXECUTION_STATE_SCHEMA_VERSION,
            "identity": self._identity_block(),
            "orders": self._oms.export_state(),
            "kill_switch": self._kill_switch.export_state(),
            "positions": [
                p.model_dump(mode="json")
                for p in self._positions.values()
            ],
            "ledgers": self._ledgers.export_state(),
            "ledger_heads": self._ledgers.head_hashes(),
            "memory": self._memory.export_state(),
            "memory_chain_hash": self._memory.chain_hash,
            "bars": [dict(b) for b in self._bars],
            "bar_index": self._bar_index,
            "order_fill_cursor": dict(self._order_fill_cursor),
            "pending_protection": {
                oid: [str(sl) if sl is not None else None,
                      str(tp) if tp is not None else None,
                      corr]
                for oid, (sl, tp, corr) in self._pending_protection.items()
            },
            "pending_exits": {
                symbol: [order_id, reason.value if hasattr(reason, "value") else str(reason),
                         snapshot.model_dump(mode="json")]
                for symbol, (order_id, reason, snapshot)
                in self._pending_exits.items()
            },
            "consecutive_bad_bars": self._consecutive_bad_bars,
            "equity_realized": str(self._equity_realized),
            "session_id": self._config.session_id,
            "runtime_state": self._state.value,
        }
        problems = validate_execution_state(state)
        if problems:
            raise StateStoreError(
                "refusing to persist an incomplete execution state: "
                + "; ".join(problems)
            )
        self._store.snapshot(state, kind="bar_checkpoint")

    # -- negative-path bar helpers -----------------------------------------
    def _refuse_bar(self, idx, correlation_id, ts, reason) -> BarOutcome:
        return BarOutcome(
            bar_index=idx,
            correlation_id=correlation_id,
            timestamp=ts or datetime.now(UTC),
            accepted=False,
            decision_action="NO_TRADE",
            decision_reason=reason,
            regime="UNKNOWN",
            crash_probability=1.0,
            runtime_state=self._state.value,
        )

    def _bad_bar(self, idx, correlation_id, ts, rejections, bar) -> BarOutcome:
        self._consecutive_bad_bars += 1
        reasons = "; ".join(r.reason for r in rejections)
        self._ledgers.record(
            ledger="incident",
            event_type="DATA_QUALITY_REJECTION",
            correlation_id=correlation_id,
            actor="runtime.data_gate",
            payload={"bar_index": idx, "reasons": reasons},
        )
        if self._consecutive_bad_bars >= 3:
            self._state = RuntimeState.DEGRADED
            self._ledgers.record(
                ledger="incident",
                event_type="RUNTIME_DEGRADED",
                correlation_id=correlation_id,
                actor="runtime",
                payload={
                    "consecutive_bad_bars": self._consecutive_bad_bars,
                    "reason": "persistent data-quality failures",
                },
            )
        # A rejected bar still mutates authoritative state (bad-bar
        # counter, bar cursor) — persisted like any state transition
        # (BLOCKER 5: no unpersisted state transitions).
        self._persist_safe(correlation_id)
        return self._refuse_bar(
            idx, correlation_id, ts,
            f"data quality rejection: {reasons} — NO_TRADE (fail closed)",
        )

    def _warmup_bar(self, idx, correlation_id, ts, detail) -> BarOutcome:
        return BarOutcome(
            bar_index=idx,
            correlation_id=correlation_id,
            timestamp=ts or datetime.now(UTC),
            accepted=True,
            decision_action="NO_TRADE",
            decision_reason=f"warm-up: sequence engine not yet ready ({detail})",
            regime="UNKNOWN",
            crash_probability=0.0,
            runtime_state=self._state.value,
        )

    # ------------------------------------------------------------------
    # RUN-ST-1: in-session wall-clock feed watchdog
    # ------------------------------------------------------------------
    def _feed_is_stale(self, bar: Mapping) -> bool:
        """True when the watchdog is ENABLED and this bar's
        timezone-aware timestamp is STRICTLY older than
        ``max_feed_staleness_seconds`` on the runtime's wall clock.

        Disabled (``max_feed_staleness_seconds is None``, the
        default) ⇒ never stale — the documented deterministic-replay
        posture (historical bar timestamps legitimately trail the
        wall clock). A bar WITHOUT a usable timezone-aware timestamp
        is treated as STALE when the watchdog is on: freshness
        cannot be proven, and the watchdog is an explicit
        wall-clock assurance the operator asked for (fail closed).
        Future-dated bars (negative age) are NOT stale — clock-skew
        tolerance is the pre-start feed gate's domain, unchanged.
        """
        limit = self._config.max_feed_staleness_seconds
        if limit is None:
            return False
        ts = bar.get("timestamp")
        if ts is None or getattr(ts, "tzinfo", None) is None:
            return True
        age = (self._wall_clock() - ts.astimezone(UTC)).total_seconds()
        return age > limit

    def _stale_bar(
        self, idx, correlation_id, ts, bar, bar_fills, exits
    ) -> BarOutcome:
        """Complete a STALE admitted bar (RUN-ST-1 fail-closed path).

        Skipped: PIT sequence, prediction, calibration, regime crash
        intelligence, decision, plan building, the RL advisor — no
        new exposure is evaluated on data the operator's wall clock
        says is old. Continued: protective exits (SL/TP levels still
        evaluated on the stale bar's prices — risk reduction beats
        freezing protection on the best-available data), post-fill
        reconciliation, the P&L snapshot, memory and persistence —
        the bar is ADMITTED, so authoritative state stays continuous
        (BLOCKER 5: no unpersisted state transitions).

        The ledger payload is DETERMINISTIC (bar timestamp + limit +
        action — never the measured wall-clock age, which would
        break replay reproducibility; INV-01 discipline).
        """
        limit = self._config.max_feed_staleness_seconds
        self._metrics.increment("feed_stale_bars")
        self._ledgers.record(
            ledger="incident",
            event_type="FEED_STALE_BLOCK",
            correlation_id=correlation_id,
            actor="runtime.feed_watchdog",
            payload={
                "bar_index": idx,
                "bar_timestamp": (
                    ts.astimezone(UTC).isoformat() if ts is not None
                    else None
                ),
                "limit_seconds": limit,
                "action": (
                    "new exposure refused — bar wall-clock age beyond "
                    "the configured in-session staleness limit; "
                    "in-flight settlement, protective exits and "
                    "persistence continue (fail closed)"
                ),
            },
        )
        # Protection exits still run: no crash intelligence was
        # computed for this bar, so only price-level (SL/TP) hits
        # can fire — deliberately conservative.
        exit_orders, exit_failed = self._submit_protection_exits(
            bar, idx, correlation_id, {"probability": 0.0}
        )
        orders_created = list(exit_orders)
        if bar_fills:
            self._reconcile_after_fills(correlation_id)
        # P&L observability tail (identical to the normal path).
        position = self._positions.get(
            self._config.symbol, PositionState(symbol=self._config.symbol)
        )
        reference_price = Decimal(str(bar["close"]))
        unrealized = self._pnl_engine.unrealized(
            position, reference_price
        )
        pnl_record = self._pnl_engine.record(
            state=position,
            mark_price=reference_price,
            fees_paid=Decimal("0"),
            entry_fill_ids=[
                f.fill_id for o in self._oms.orders() for f in o.fills
            ],
            exit_fill_ids=[],
            order_ids=[o.order_id for o in self._oms.orders()],
            correlation_id=correlation_id,
        )
        self._ledgers.record(
            ledger="pnl",
            event_type="PNL_SNAPSHOT",
            correlation_id=correlation_id,
            actor="runtime.pnl",
            payload={
                "pnl_id": pnl_record.pnl_id,
                "symbol": pnl_record.symbol,
                "realized": str(pnl_record.realized_pnl),
                "unrealized": str(pnl_record.unrealized_pnl),
                "mark_price": str(reference_price),
            },
        )
        self._memory.record(
            MemoryCategory.MARKET,
            {"bar_index": idx, "close": str(reference_price),
             "correlation_id": correlation_id},
            correlation_id=correlation_id,
            at=ts,
        )
        self._persist_safe(correlation_id)
        return BarOutcome(
            bar_index=idx,
            correlation_id=correlation_id,
            timestamp=ts or datetime.now(UTC),
            accepted=True,
            decision_action="NO_TRADE",
            decision_reason=(
                f"feed stale: bar wall-clock age exceeds the "
                f"{limit}s in-session limit — new exposure refused, "
                f"decision chain skipped (RUN-ST-1 fail closed)"
            ),
            prediction_probability=None,
            regime=self._classify_regime(),
            crash_probability=0.0,
            orders_created=tuple(o.order_id for o in orders_created),
            fills=tuple(f.fill_id for f in bar_fills),
            exits=tuple(e.exit_id for e in exits),
            realized_pnl=str(position.realized_pnl),
            unrealized_pnl=str(unrealized),
            runtime_state=self._state.value,
            risk_failed_checks=exit_failed,
        )


def _std(values) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(max(var, 0.0))


__all__ = [
    "RuntimeConfig",
    "BarOutcome",
    "TradingRuntime",
]
