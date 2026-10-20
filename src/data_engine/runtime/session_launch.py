"""Fail-closed CLI session launcher (P0-P3 master audit FIX-10 /
B-P0-01).

WHY THIS MODULE EXISTS. The audit confirmed the CLI ``serve`` path
constructed :class:`PaperRuntimeService` with NO ``tick_fn`` and no
call to :func:`compose_operational_session` — the launched process
was a supervisor/heartbeat shell in which NO operator path could ever
run a paper session (B-P0-01). The composition root existed and was
tested, but nothing connected it to the operational entry point.

WHAT THIS MODULE ADDS (the explicit production wiring seam):

- :class:`SessionLaunchPlan` — a TYPED, validated launch
  configuration (JSON on disk, operator-owned, fail-closed on any
  malformed/missing field). It carries the session config, the
  durable-state paths, the paper-venue boundary, the instrument
  specs, the SIGNED operator-approval bundle reference, the recorded
  evidence entries for non-human gates, and the bar source.
- :func:`launch_paper_session` — compose + start one operational
  paper session through THE composition root
  (:func:`compose_operational_session`, C1 documented order) with the
  trusted-approval boundary (FIX-9) enforced, then return the live
  session plus a REAL tick function.
- :class:`SessionTick` — the tick closure the supervisor drives every
  ``tick_seconds``: it pulls the next bar from the configured source
  (deterministic replay file or a provider adapter) and feeds it to
  ``TradingRuntime.process_bar`` (the full governed chain §26: data
  validation → pending-order fills → drawdown enforcement → TTL →
  exits → staleness watchdog → PIT sequence → decision → risk gate →
  paper venue).

FAIL-CLOSED POSTURE (exit code 4 from the CLI):

- malformed plan, unreadable bars file, unresolvable ensemble
  factory, missing/invalid signed approvals, missing approval key,
  incomplete readiness chain, launch-time start refusal — each
  refuses with an actionable message naming the exact file/field/
  reason code. There is NO default ensemble, NO default venue, and
  NO default evidence: a session never launches "half-ready".
- The launched session is PAPER-ONLY by construction: it flows
  through the composition root whose venue boundary enforces
  ``MOCK_DETERMINISTIC`` execution mode and refuses REAL adapters
  (L1-L4 proof tests in test_paper_mode_selection_proof.py).

HONEST SCOPE:

- ``replay`` bar source = deterministic bar file (tests, smoke,
  replay verification). ``provider`` bar source polls a REAL
  market-data adapter (currently only the Binance public spot
  klines pilot — see the market support matrix). Execution remains
  paper-only regardless of the data source.
- The ensemble is operator-supplied code: the plan names a
  ``module:factory`` import reference. The engine NEVER ships a
  default fitted model — an operational session requires the
  operator's own fitted/pinned ensemble (BLOCKER 21 hashes are
  enforced by the runtime at start).

This module reads NO environment variable except the approval-key
and ledger-MAC channels documented in FIX-9/F-25 (loaded inside the
composition root / :class:`OperatorApprovalKey.from_environment`).
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from data_engine.brokers.models import InstrumentSpec
from data_engine.brokers.redaction import BrokerCredential
from data_engine.runtime.composition import (
    COMPONENT_EVIDENCE_GATES,
    HUMAN_EVIDENCE_GATES,
    CompositionError,
    CompositionStartRefused,
    OperationalSessionConfig,
    compose_operational_session,
)
from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.operator_approval import (
    OperatorApprovalKey,
    OperatorApprovalRecord,
    build_trusted_evidence,
)
from data_engine.runtime.readiness import GATE_NAMES, GateEvidence
from data_engine.runtime.runtime import RuntimeConfig

__all__ = [
    "SESSION_LAUNCH_EXIT_CODE",
    "SessionLaunchError",
    "LaunchBarSource",
    "LaunchRecordedEvidence",
    "SessionLaunchPlan",
    "ReplayBarSource",
    "ProviderBarSource",
    "SessionTick",
    "LaunchedSession",
    "load_launch_plan",
    "launch_paper_session",
]

#: Dedicated CLI exit code for a refused session launch (distinct
#: from the supervisor's readiness refusal 2 and network refusal 3).
SESSION_LAUNCH_EXIT_CODE = 4

#: The only bar-source modes the launcher understands.
_BAR_SOURCE_MODES = ("replay", "provider")

#: The only provider adapters the launcher will construct by name
#: (the honest adapter inventory — see the market support matrix;
#: B-P1-07: never infer support from a schema enum).
_KNOWN_PROVIDERS = ("binance_public",)


class SessionLaunchError(RuntimeContractError):
    """Refused session launch (fail closed, actionable message)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.exit_code = SESSION_LAUNCH_EXIT_CODE


class LaunchBarSource(BaseModel):
    """The session's bar source: deterministic replay file or a
    provider adapter poll. extra='forbid' — unknown keys refuse."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: str
    bars_file: Optional[str] = None
    provider: Optional[str] = None
    symbol: Optional[str] = None
    interval_seconds: Optional[int] = None
    #: provider mode: how many closed bars to fetch per poll window.
    poll_bars: int = 2

    @field_validator("mode")
    @classmethod
    def _mode(cls, v: str) -> str:
        if v not in _BAR_SOURCE_MODES:
            raise SessionLaunchError(
                f"bar source mode {v!r} unknown (allowed: "
                f"{_BAR_SOURCE_MODES}) — refusing to guess a feed"
            )
        return v

    @model_validator(mode="after")
    def _validate_bar_source(self) -> "LaunchBarSource":
        if self.mode == "replay" and not self.bars_file:
            raise SessionLaunchError(
                "replay bar source requires 'bars_file' (JSONL, one bar "
                "dict per line: timestamp/open/high/low/close/volume)"
            )
        if self.mode == "provider":
            if not self.provider:
                raise SessionLaunchError(
                    "provider bar source requires 'provider' (known: "
                    f"{_KNOWN_PROVIDERS})"
                )
            if self.provider not in _KNOWN_PROVIDERS:
                raise SessionLaunchError(
                    f"provider {self.provider!r} is not a proven adapter "
                    f"(known: {_KNOWN_PROVIDERS}) — the launcher refuses "
                    "to claim market support that has no adapter evidence"
                )
            if not self.symbol or not self.interval_seconds:
                raise SessionLaunchError(
                    "provider bar source requires 'symbol' and "
                    "'interval_seconds'"
                )
            if self.poll_bars < 1:
                raise SessionLaunchError("poll_bars must be >= 1")
        return self


class LaunchRecordedEvidence(BaseModel):
    """One operator-attested recorded-evidence entry for a NON-human
    gate (the human gates require SIGNED approvals — FIX-9)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    gate: str
    component: str
    check: str
    evidence: str
    passed: bool

    @field_validator("gate")
    @classmethod
    def _gate(cls, v: str) -> str:
        if v not in GATE_NAMES:
            raise SessionLaunchError(
                f"recorded-evidence entry targets unknown gate {v!r}"
            )
        if v in HUMAN_EVIDENCE_GATES:
            raise SessionLaunchError(
                f"gate {v!r} is a human-dependency gate: recorded "
                "free-text entries cannot satisfy it — provide a "
                "SIGNED approval record in the approvals file "
                "(FIX-9)"
            )
        return v

    def to_gate_evidence(self) -> GateEvidence:
        return GateEvidence(
            gate=self.gate,
            component=self.component,
            check=self.check,
            evidence=self.evidence,
            passed=self.passed,
        )


class SessionLaunchPlan(BaseModel):
    """The typed, validated session launch plan (JSON on disk)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session: dict
    state_dir: str
    ledger_path: str
    venue_journal_path: str
    venue_account_id: str
    instruments: list
    venue_currency: str = "USD"
    venue_initial_balance: str = "100000"
    #: SIGNED approval bundle (JSON: {"approvals": [{"record": {...},
    #: "signature": "<64-hex>"}]}) satisfying the human gates.
    approvals_file: Optional[str] = None
    #: Operator-attested recorded evidence for non-human gates.
    recorded_evidence: list[LaunchRecordedEvidence] = []
    bar_source: LaunchBarSource
    #: Operator-supplied ensemble factory "module:function" (their
    #: fitted, pinned model code — the engine never ships a default).
    ensemble_factory: str
    #: Optional distinct venue clock ISO anchor is NOT configured
    #: here — the venue clock is the engine's UTC wall clock.

    @field_validator("session")
    @classmethod
    def _session(cls, v: dict) -> dict:
        if not isinstance(v, dict) or not v:
            raise SessionLaunchError(
                "plan.session must be a non-empty RuntimeConfig dict"
            )
        return v

    @field_validator("ensemble_factory")
    @classmethod
    def _factory(cls, v: str) -> str:
        if ":" not in v:
            raise SessionLaunchError(
                f"ensemble_factory {v!r} must be 'module:function' — "
                "the operator's own fitted-ensemble loader"
            )
        return v

    @model_validator(mode="after")
    def _validated_session(self) -> "SessionLaunchPlan":
        # Eager fail-closed validation: a plan that reaches disk with
        # an invalid RuntimeConfig payload is refused at LOAD time,
        # not at launch time (the operator learns the exact field at
        # plan-authoring time).
        self.runtime_config()
        return self

    def runtime_config(self) -> RuntimeConfig:
        try:
            return RuntimeConfig(**self.session)
        except Exception as exc:
            raise SessionLaunchError(
                f"plan.session failed RuntimeConfig validation: {exc}"
            ) from exc

    def instrument_specs(self) -> dict:
        try:
            return {
                spec["symbol"]: InstrumentSpec(**spec)
                for spec in self.instruments
            }
        except SessionLaunchError:
            raise
        except Exception as exc:
            raise SessionLaunchError(
                f"plan.instruments failed InstrumentSpec validation: "
                f"{exc}"
            ) from exc


def load_launch_plan(path) -> SessionLaunchPlan:
    """Load + validate a launch plan from a JSON file (fail closed
    with the exact field/reason on any malformed content)."""
    plan_path = Path(path)
    if not plan_path.is_file():
        raise SessionLaunchError(f"launch plan not found: {plan_path}")
    try:
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionLaunchError(
            f"launch plan unreadable/invalid JSON ({plan_path}): {exc}"
        ) from exc
    try:
        return SessionLaunchPlan(**raw)
    except SessionLaunchError:
        raise
    except Exception as exc:
        raise SessionLaunchError(
            f"launch plan failed validation ({plan_path}): {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# bar sources
# ---------------------------------------------------------------------------

class ReplayBarSource:
    """Deterministic bar source: a JSONL file, one bar dict per line
    (timestamp as ISO-8601 with timezone, open/high/low/close/volume).
    ``next_bar()`` returns dicts in file order, then ``None``
    (exhausted — the supervisor keeps running but the tick counts no
    new bars; a bounded launch ends via --max-seconds or SIGTERM)."""

    def __init__(self, bars_file) -> None:
        path = Path(bars_file)
        if not path.is_file():
            raise SessionLaunchError(f"replay bars file not found: {path}")
        bars = []
        try:
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                line = line.strip()
                if not line:
                    continue
                bar = json.loads(line)
                bar = _normalize_bar(bar, f"{path}:{lineno}")
                bars.append(bar)
        except SessionLaunchError:
            raise
        except Exception as exc:
            raise SessionLaunchError(
                f"replay bars file invalid ({path}): {exc}"
            ) from exc
        if not bars:
            raise SessionLaunchError(
                f"replay bars file has no bars ({path}) — a session "
                "cannot warm up from an empty feed"
            )
        self._bars = bars
        self._cursor = 0
        self.name = str(path)

    def next_bar(self) -> Optional[dict]:
        if self._cursor >= len(self._bars):
            return None
        bar = self._bars[self._cursor]
        self._cursor += 1
        return bar


class ProviderBarSource:
    """Polling bar source over a REAL market-data adapter (paper-only
    execution regardless of data source). The adapter is INJECTED —
    the launcher constructs only known adapters (Binance public spot
    pilot); tests inject deterministic mocks (no network).

    Each ``next_bar()`` polls the adapter's recent CLOSED bars and
    yields any bar whose timestamp has not been fed yet (dedup by
    timestamp, oldest first). Fetch errors FAIL CLOSED: the source
    raises, the tick records a refusal, and no bar is fabricated."""

    def __init__(
        self,
        provider,
        *,
        symbol: str,
        interval_seconds: int,
        poll_bars: int = 2,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        from data_engine.timeframes import Timeframe

        if provider is None:
            raise SessionLaunchError(
                "provider bar source requires a provider adapter "
                "instance (known constructors: binance_public)"
            )
        self._provider = provider
        self._symbol = symbol
        self._interval = interval_seconds
        self._poll_bars = max(1, poll_bars)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._seen: set = set()
        self._pending: list = []
        self.name = getattr(provider, "name", type(provider).__name__)

    def _timeframe(self):
        from data_engine.timeframes import Timeframe

        seconds_to_tf = {
            60: Timeframe.M1, 300: Timeframe.M5, 900: Timeframe.M15,
            3600: Timeframe.H1, 14400: Timeframe.H4, 86400: Timeframe.D1,
        }
        tf = seconds_to_tf.get(self._interval)
        if tf is None:
            raise SessionLaunchError(
                f"interval_seconds={self._interval} has no Timeframe "
                "mapping (known: 60/300/900/3600/14400/86400)"
            )
        return tf

    def next_bar(self) -> Optional[dict]:
        if not self._pending:
            now = self._clock()
            from datetime import timedelta

            window_start = now - timedelta(
                seconds=self._interval * (self._poll_bars + 2)
            )
            try:
                candles = self._provider.fetch_candles(
                    self._symbol,
                    self._timeframe(),
                    window_start,
                    now,
                )
            except Exception as exc:  # adapter contract: fail closed
                raise SessionLaunchError(
                    f"provider bar fetch failed ({self.name}, "
                    f"{self._symbol}): {type(exc).__name__}: {exc} — "
                    "no bar is fabricated on a feed error"
                ) from exc
            for candle in candles or []:
                bar = _normalize_bar(
                    {
                        "timestamp": candle.timestamp,
                        "open": candle.open,
                        "high": candle.high,
                        "low": candle.low,
                        "close": candle.close,
                        "volume": candle.volume,
                    },
                    f"{self.name}:{self._symbol}",
                )
                if bar["timestamp"] not in self._seen:
                    self._pending.append(bar)
            self._pending.sort(key=lambda b: b["timestamp"])
        if not self._pending:
            return None
        bar = self._pending.pop(0)
        self._seen.add(bar["timestamp"])
        return bar


def _normalize_bar(bar: Mapping, where: str) -> dict:
    """Validate/normalize one bar dict (fail closed at the source:
    the runtime's own §10 validation is the second gate)."""
    from datetime import datetime as _dt
    from decimal import Decimal as _Decimal

    try:
        ts = bar["timestamp"]
        if isinstance(ts, str):
            ts = _dt.fromisoformat(ts)
        if ts.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        out = {
            "timestamp": ts.astimezone(UTC),
            "open": _Decimal(str(bar["open"])),
            "high": _Decimal(str(bar["high"])),
            "low": _Decimal(str(bar["low"])),
            "close": _Decimal(str(bar["close"])),
            "volume": _Decimal(str(bar.get("volume", 0))),
        }
    except SessionLaunchError:
        raise
    except Exception as exc:
        raise SessionLaunchError(
            f"invalid bar at {where}: {exc} — bars require "
            "tz-aware timestamp + open/high/low/close/volume"
        ) from exc
    return out


# ---------------------------------------------------------------------------
# the tick
# ---------------------------------------------------------------------------

class SessionTick:
    """The REAL session tick driven by the supervisor loop: pull the
    next bar from the source and feed it through the governed
    ``process_bar`` chain. Counts ticks, bar refusals and feed errors
    (honest observability: a stalled/exhausted source is VISIBLE as
    ticks_without_new_bar, never silently healthy)."""

    def __init__(self, runtime, bar_source) -> None:
        self._runtime = runtime
        self._source = bar_source
        self.ticks = 0
        self.bars_fed = 0
        self.bar_refusals = 0
        self.feed_errors = 0
        self.last_error: Optional[str] = None

    @property
    def source_name(self) -> str:
        return getattr(self._source, "name", type(self._source).__name__)

    def __call__(self) -> None:
        self.ticks += 1
        try:
            bar = self._source.next_bar()
        except SessionLaunchError as exc:
            # Provider failure: counted, surfaced, NEVER fabricated.
            self.feed_errors += 1
            self.last_error = str(exc)
            return
        if bar is None:
            return
        outcome = self._runtime.process_bar(bar)
        self.bars_fed += 1
        if getattr(outcome, "refused", False):
            self.bar_refusals += 1


# ---------------------------------------------------------------------------
# the launcher
# ---------------------------------------------------------------------------

@dataclass
class LaunchedSession:
    """The launched operational paper session + its wiring surface."""

    composed: Any
    tick: SessionTick
    plan: SessionLaunchPlan
    launched_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _import_ensemble_factory(ref: str):
    """Import the operator's ensemble factory ``module:function``.
    Fail closed with an actionable message on any import problem."""
    module_name, _, attr = ref.partition(":")
    if not module_name or not attr:
        raise SessionLaunchError(
            f"ensemble_factory {ref!r} must be 'module:function'"
        )
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise SessionLaunchError(
            f"ensemble factory module {module_name!r} could not be "
            f"imported: {exc} — the operator's fitted-ensemble code "
            "must be importable from the launch environment"
        ) from exc
    factory = getattr(module, attr, None)
    if not callable(factory):
        raise SessionLaunchError(
            f"ensemble factory {ref!r} did not resolve to a callable"
        )
    return factory


def _load_approvals(
    path, key: OperatorApprovalKey, *, as_of: datetime,
) -> tuple:
    """Load the SIGNED approval bundle (JSON: approvals list with
    record + signature) and build verified TrustedGateEvidence."""
    approvals_path = Path(path)
    if not approvals_path.is_file():
        raise SessionLaunchError(
            f"approvals file not found: {approvals_path}"
        )
    try:
        raw = json.loads(approvals_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SessionLaunchError(
            f"approvals file unreadable/invalid JSON "
            f"({approvals_path}): {exc}"
        ) from exc
    entries = raw.get("approvals") if isinstance(raw, dict) else None
    if not isinstance(entries, list) or not entries:
        raise SessionLaunchError(
            f"approvals file ({approvals_path}) must contain a "
            "non-empty 'approvals' list of "
            "{'record': {...}, 'signature': '<64-hex>'} entries"
        )
    out = []
    for i, entry in enumerate(entries):
        try:
            record = OperatorApprovalRecord(**entry["record"])
            signature = entry["signature"]
        except SessionLaunchError:
            raise
        except Exception as exc:
            raise SessionLaunchError(
                f"approvals entry #{i + 1} malformed "
                f"({approvals_path}): {exc}"
            ) from exc
        try:
            out.append(build_trusted_evidence(
                record, signature, key, as_of=as_of,
            ))
        except Exception as exc:
            raise SessionLaunchError(
                f"approval #{i + 1} ({record.record_id}) REFUSED: "
                f"{exc} — sign the record with the operator approval "
                "key (see docs/PAPER_OPERATOR_RUNBOOK.md)"
            ) from exc
    return tuple(out)


def launch_paper_session(
    plan: SessionLaunchPlan,
    *,
    ensemble=None,
    calibrator=None,
    approval_key: Optional[OperatorApprovalKey] = None,
    provider=None,
    wall_clock=None,
    approval_as_of: Optional[datetime] = None,
    started: bool = True,
) -> LaunchedSession:
    """Compose + start one operational paper session from a validated
    launch plan, and return the live session with its REAL tick.

    Injection seams (tests / operator launchers): ``ensemble`` +
    ``calibrator`` (skip the importable factory), ``approval_key``
    (skip the environment channel), ``provider`` (a constructed
    adapter — or a deterministic mock). Every seam defaults to the
    operator-owned source; none defaults to a fabricated value.

    Fail-closed ordering: plan → ensemble → approvals → recorded
    evidence → composition root (C1 order) → explicit start."""
    if not isinstance(plan, SessionLaunchPlan):
        raise SessionLaunchError(
            "launch_paper_session requires a validated "
            "SessionLaunchPlan (load it via load_launch_plan)"
        )
    as_of = approval_as_of or datetime.now(UTC)

    # -- ensemble (operator-supplied, never defaulted) ---------------------
    if ensemble is None:
        factory = _import_ensemble_factory(plan.ensemble_factory)
        try:
            built = factory()
        except Exception as exc:
            raise SessionLaunchError(
                f"ensemble factory {plan.ensemble_factory!r} failed: "
                f"{exc}"
            ) from exc
        if isinstance(built, tuple) and len(built) == 2:
            ensemble, calibrator = built
        else:
            ensemble = built

    # -- evidence bundle ----------------------------------------------------
    evidence: list = []
    if plan.approvals_file:
        if approval_key is None:
            try:
                approval_key = OperatorApprovalKey.from_environment()
            except Exception as exc:
                raise SessionLaunchError(
                    f"launch refused — operator approval key "
                    f"unavailable: {exc}"
                ) from exc
        evidence.extend(_load_approvals(
            plan.approvals_file, approval_key, as_of=as_of,
        ))
    for entry in plan.recorded_evidence:
        evidence.append(entry.to_gate_evidence())

    # -- bar source ----------------------------------------------------------
    if plan.bar_source.mode == "replay":
        bar_source = ReplayBarSource(plan.bar_source.bars_file)
    else:
        if provider is None:
            provider = _construct_known_provider(plan.bar_source.provider)
        bar_source = ProviderBarSource(
            provider,
            symbol=plan.bar_source.symbol,
            interval_seconds=plan.bar_source.interval_seconds,
            poll_bars=plan.bar_source.poll_bars,
        )

    # -- the composition root (C1 documented order, FIX-9 boundary) --------
    try:
        config = OperationalSessionConfig(session=plan.runtime_config())
    except Exception as exc:
        raise SessionLaunchError(
            f"operational session config refused: {exc}"
        ) from exc
    try:
        composed = compose_operational_session(
            config=config,
            ensemble=ensemble,
            calibrator=calibrator,
            state_dir=Path(plan.state_dir),
            ledger_path=Path(plan.ledger_path),
            venue_journal_path=Path(plan.venue_journal_path),
            venue_account_id=plan.venue_account_id,
            venue_credential=BrokerCredential(
                plan.venue_account_id,
                "launch-plan-paper-boundary",
            ),
            instruments=plan.instrument_specs(),
            venue_clock=lambda: datetime.now(UTC),
            operator_evidence=tuple(evidence),
            operator_approval_key=approval_key,
            approval_as_of=as_of,
            wall_clock=wall_clock,
        )
    except CompositionError as exc:
        raise SessionLaunchError(
            f"session launch REFUSED by the composition root: {exc}"
        ) from exc

    # -- the explicit lifecycle start ---------------------------------------
    if started:
        try:
            composed.start()
        except CompositionStartRefused as exc:
            raise SessionLaunchError(
                "session launch REFUSED — readiness chain incomplete: "
                f"{exc}"
            ) from exc
        except CompositionError as exc:
            raise SessionLaunchError(
                f"session start failed (fail closed): {exc}"
            ) from exc

    tick = SessionTick(composed.runtime, bar_source)
    return LaunchedSession(composed=composed, tick=tick, plan=plan)


def _construct_known_provider(name: str):
    """Construct a KNOWN adapter by name (the honest inventory: only
    the Binance public spot pilot has a proven constructor; anything
    else refuses — B-P1-07: no support claimed without an adapter).

    Boundary note (BUG-008): the frozen ``data_engine.schemas`` is
    imported via the sanctioned ``data_engine.provider`` bridge —
    runtime modules never import the frozen domain directly."""
    if name == "binance_public":
        from data_engine.provider import ProviderConfig
        from data_engine.providers.binance_public import (
            BINANCE_PUBLIC_PROVIDER_NAME,
            DEFAULT_ENDPOINT,
            BinancePublicKlinesProvider,
        )

        return BinancePublicKlinesProvider(
            ProviderConfig(
                provider_name=BINANCE_PUBLIC_PROVIDER_NAME,
                provider_type="api",
                endpoint=DEFAULT_ENDPOINT,
            )
        )
    raise SessionLaunchError(
        f"no proven constructor for provider {name!r} "
        f"(known: {_KNOWN_PROVIDERS})"
    )
