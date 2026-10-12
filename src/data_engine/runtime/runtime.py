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

from pydantic import BaseModel, ConfigDict, field_validator

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
from data_engine.runtime.risk_gate import RiskContext, RiskGate
from data_engine.runtime.rl import (
    GovernedRLPolicy,
    RLGovernanceError,
    RLObservation,
)
from data_engine.runtime.sequence import (
    SequenceSpec,
    build_sequence_set,
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
    ) -> None:
        if config is None or ensemble is None:
            raise RuntimeContractError(
                "runtime requires config + fitted ensemble"
            )
        self._config = config
        self._ensemble = ensemble
        self._calibrator = calibrator
        self._store = state_store
        self._readiness_gate = readiness_gate
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
        limits = RiskLimits(
            max_position_units=config.max_position_units,
            max_leverage=Decimal("1.0"),
            max_single_asset_weight=Decimal("0.30"),
            max_sector_weight=Decimal("1.0"),
            max_portfolio_heat=Decimal("1.0"),
        )
        self._risk_engine = RiskEngine(limits)
        self._risk_gate = RiskGate(self._risk_engine, self._kill_switch)
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
        self._entry_orders_by_symbol: dict = {}
        self._started_at: Optional[datetime] = None
        # Latency-aware pending-order bookkeeping: fills for orders
        # submitted on bar N happen on bars N+lag.. (never same-bar).
        self._order_fill_cursor: dict = {}   # order_id -> next bar index
        self._pending_protection: dict = {}  # order_id -> (sl, tp, corr)
        self._pending_exits: dict = {}       # symbol -> (order_id, reason, snapshot)
        self._restarted = False              # True after state restoration
        self._restored_runtime_state = None  # persisted operating state
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
        config_digest = prefixed_hash(
            "rtcfg.",
            {
                "kind": "runtime_config_identity",
                "config": self._config.model_dump(mode="json"),
            },
        )
        return {
            "contract_version": RUNTIME_CONTRACT_VERSION,
            "session_id": self._config.session_id,
            "symbol": self._config.symbol,
            "timeframe": self._config.timeframe,
            "config_digest": config_digest,
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
        exit_orders = self._submit_protection_exits(
            bar, idx, correlation_id, crash
        )
        orders_created.extend(exit_orders)

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
            market_open=True,
            paper_mode=True,
            model_valid=True,
            uncertainty=plan.uncertainty,
            crash_probability=float(plan.crash_risk.get("probability", 1.0)),
            max_acceptable_crash_probability=self._config.max_crash_probability,
            max_drawdown_fraction=self._window_drawdown(),
            account_drawdown_fraction=self._account_drawdown(),
            account_drawdown_limit_fraction=(
                self._config.max_account_drawdown_fraction
            ),
            volatility=self._window_volatility(),
            max_volatility=0.10,
            daily_realized_return=self._daily_realized_return(),
            half_spread=self._realism.half_spread,
            max_spread_fraction=Decimal("0.01"),
            duplicate_order_id=duplicate,
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
                self._metrics.increment("orders_venue_submitted")
            except _Refused as exc:
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
                self._metrics.increment("orders_venue_unknown")
                self._flag_execution_uncertain(
                    f"venue submission outcome uncertain for order "
                    f"{order.order_id}: {exc}",
                    correlation_id,
                )
                return [], ()
        self._oms.submit(
            order.order_id,
            submitted_at=bar["timestamp"],
            bar_index=bar_index,
        )
        self._oms.acknowledge(order.order_id)
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
        — the historical partial-fill-event semantics are preserved
        exactly."""
        for fill in new_fills:
            self._oms.apply_fill(order.order_id, fill)
            self._apply_fill_to_position(fill, correlation_id)
            fills_sink.append(fill)
            self._metrics.increment("fills")
            if order.remaining_quantity > 0:
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
    ) -> list:
        """SL/TP/crash exit submission for positions from earlier bars."""
        orders: list = []
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
            created, _ = self._execute_plan(
                exit_plan, bar, bar_index, correlation_id,
                Decimal(str(bar["close"])),
                self._current_equity(Decimal(str(bar["close"]))),
            )
            if created:
                self._pending_exits[symbol] = (
                    created[0].order_id, reason, position,
                )
                orders.extend(created)
        return orders

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
            last_bar_age_bars=0,
            market_open=True,
            paper_mode=True,
            model_valid=True,
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
            max_volatility=0.10,
            daily_realized_return=self._daily_realized_return(),
            half_spread=self._realism.half_spread,
            max_spread_fraction=Decimal("0.01"),
        )

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
