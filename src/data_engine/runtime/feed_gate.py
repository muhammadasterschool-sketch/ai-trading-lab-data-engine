"""Operational market-feed readiness gate (operator mandate 2026-10-10
§2/§5 — the research-history vs operational-feed distinction).

WHY THIS MODULE EXISTS. The pre-existing REAL_DATA_READY gate answers a
DATASET question ("does a REAL_VERIFIED dataset exist?"), and the
documented path to satisfy it (REAL_DATA_READINESS_CONTRACT.md §5 +
PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md §7.2) has de facto been the
long-term research corpus (>= 5 verified years; the deferred 20-year
acquisition). That conflates two genuinely different requirements:

1. RESEARCH HISTORY — long-term verified market history for empirical
   claims, backtest evidence and strategy graduation. DEFERRED by the
   operator (decision GOV-HDD-001, 2026-10-10: "Long-term historical
   market-data acquisition is DEFERRED"). It is NOT a paper-activation
   requirement and is NEVER reported satisfied here.
2. OPERATIONAL FEED — what a paper session ACTUALLY consumes: a
   genuine current market feed for the traded symbol/timeframe from a
   HUMAN-APPROVED source, validated, fresh, correctly mapped, with
   enough bars for the strategy's indicator warm-up window.

This module implements the OPERATIONAL FEED evaluation. The verdict
feeds the ``OPERATIONAL_FEED_READY`` readiness gate (32nd mandatory
gate — see readiness.py). REAL_DATA_READY keeps its dataset semantics
unchanged (synthetic promotion remains structurally refused).

FAIL-CLOSED, ENVIRONMENT-FREE. Every component requires objective
inputs supplied by the composition root; anything missing, unknown,
stale, unmapped or quality-rejected => verdict FALSE with explicit
reasons. The module reads NO environment variable (structural test)
and never fabricates an approval: source approval remains a recorded
HUMAN decision in the prediction source registry
(PREDICTION_DATA_SOURCE_PROVENANCE_POLICY.md §5 — AI approvals are
structurally rejected there), so an unapproved source can only ever
evaluate FALSE here.

The reference time ``as_of`` is CALLER-SUPPLIED (logical session time)
— the gate itself stays deterministic given its inputs (no ambient
wall-clock), preserving the replay/identity discipline.
"""

from datetime import datetime, timedelta, UTC
from typing import Any, Mapping, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.runtime.contracts import RuntimeContractError
from data_engine.runtime.data_gate import validate_bars

#: Operator decision record for the deferral (HISTORICAL_DATA_DEFERRAL_RECORD.md).
RESEARCH_HISTORY_DECISION_ID = "GOV-HDD-001"

#: Honest, constant research-history status reported by every feed
#: verdict: the long-term corpus is DEFERRED — never claimed satisfied,
#: never an activation blocker (it is tracked separately from the
#: operational feed requirement this gate evaluates).
RESEARCH_HISTORY_STATUS = "DEFERRED_BY_OPERATOR"

#: Required source approval for a genuine operational feed: the
#: production-ingestion scope (contract-testing scope cannot authorize
#: a real feed for a paper session).
REQUIRED_SOURCE_STATUS = "APPROVED_FOR_PRODUCTION"
REQUIRED_SOURCE_SCOPE = "production-ingestion"

#: Default freshness tolerance: the newest bar must be at most this old
#: relative to the caller-supplied session reference time, and at most
#: FUTURE_TOLERANCE ahead of it (clock-skew allowance — a feed from the
#: future is a PIT violation, not a bonus).
DEFAULT_MAX_STALENESS_SECONDS = 900
DEFAULT_FUTURE_TOLERANCE_SECONDS = 60


class FeedGateError(RuntimeContractError):
    """Raised on operational-feed contract violations."""


class OperationalFeedReport(BaseModel):
    """Fail-closed verdict for one operational-feed evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    passed: bool
    source_name: str
    source_status: str
    approved_scopes: tuple
    symbol: str
    canonical_instrument_id: Optional[str] = None
    bar_count: int
    warmup_required: int
    quality_rejections: tuple
    latest_bar_timestamp: Optional[datetime] = None
    as_of: Optional[datetime] = None
    research_history_status: str = RESEARCH_HISTORY_STATUS
    reasons: tuple = ()

    @field_validator("source_name", "symbol", "source_status")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise FeedGateError("feed report text fields must be non-empty")
        return v.strip()

    @field_validator("research_history_status")
    @classmethod
    def _validate_deferral(cls, v: str) -> str:
        if v != RESEARCH_HISTORY_STATUS:
            raise FeedGateError(
                "research-history status is the operator decision record "
                f"({RESEARCH_HISTORY_DECISION_ID}) — constant "
                f"{RESEARCH_HISTORY_STATUS!r}; this gate never claims "
                "long-term history is satisfied"
            )
        return v


def _registry_status(registry: Any, source_name: str) -> tuple:
    """Duck-typed lookup into the prediction source registry.

    Returns ``(status_str, scopes_tuple)``. Raises :class:`FeedGateError`
    when the source is not registered (the registry raises its own
    contract error on unknown names — surfaced as a fail-closed
    reason, never swallowed into a pass).
    """
    if registry is None or not hasattr(registry, "get"):
        raise FeedGateError(
            "a governed DataSourceRegistry instance is required to "
            "evaluate an operational feed (source approval is a "
            "recorded human decision — never invented here)"
        )
    try:
        record = registry.get(source_name)
    except Exception as exc:
        raise FeedGateError(
            f"feed source {source_name!r} is not registered in the "
            "governed source registry (fail closed)"
        ) from exc
    status = getattr(record, "verification_status", None)
    status_value = getattr(status, "value", status)
    scopes = getattr(record, "approved_usage_scopes", ()) or ()
    return str(status_value), tuple(str(s) for s in scopes)


def evaluate_operational_feed(
    *,
    source_registry: Any,
    source_name: str,
    session_symbol: str,
    bars: Sequence[Mapping],
    required_warmup_bars: int,
    as_of: datetime,
    canonical_instrument_id: Optional[str] = None,
    registry_confirmed: bool = False,
    expected_interval: Optional[timedelta] = None,
    max_staleness_seconds: int = DEFAULT_MAX_STALENESS_SECONDS,
    future_tolerance_seconds: int = DEFAULT_FUTURE_TOLERANCE_SECONDS,
) -> OperationalFeedReport:
    """Evaluate the MINIMUM operational feed requirements.

    Components (operator mandate §5 checklist, mapped):

    - genuine source ........ registry status APPROVED_FOR_PRODUCTION
                             with production-ingestion scope (human
                             decision on record — never fabricated);
    - validated ............. ``validate_bars`` quality gates PASS;
    - warm-up ............... ``len(bars) >= required_warmup_bars``;
    - fresh ................. newest bar within the staleness window
                             of ``as_of`` and not future-dated beyond
                             the clock-skew tolerance;
    - correctly mapped ...... registry-confirmed canonical instrument
                             id present and non-empty.

    Any failure => ``passed=False`` with explicit reasons. Synthetic
    data never enters this gate legitimately: its sources are UNVETTED
    by construction, and only a human approval can change that.
    """
    if not isinstance(source_name, str) or not source_name.strip():
        raise FeedGateError("source_name must be a non-empty string")
    if not isinstance(session_symbol, str) or not session_symbol.strip():
        raise FeedGateError("session_symbol must be a non-empty string")
    if not isinstance(required_warmup_bars, int) or required_warmup_bars < 1:
        raise FeedGateError("required_warmup_bars must be a positive int")
    if as_of is None or getattr(as_of, "tzinfo", None) is None:
        raise FeedGateError("as_of must be a timezone-aware datetime")
    as_of = as_of.astimezone(UTC)
    if max_staleness_seconds < 1 or future_tolerance_seconds < 0:
        raise FeedGateError("staleness/future tolerances must be sensible")

    reasons: list = []

    # -- genuine source (human-approved, production-ingestion scope) -------
    try:
        source_status, scopes = _registry_status(source_registry, source_name)
    except FeedGateError as exc:
        source_status, scopes = "UNREGISTERED", ()
        reasons.append(str(exc))
    if source_status != "UNREGISTERED":
        if source_status != REQUIRED_SOURCE_STATUS:
            reasons.append(
                f"source {source_name!r} status is {source_status!r} — an "
                f"operational feed requires {REQUIRED_SOURCE_STATUS!r} "
                "(human decision; APPROVED_FOR_TESTING cannot authorize a "
                "genuine paper-session feed)"
            )
        if REQUIRED_SOURCE_SCOPE not in scopes:
            reasons.append(
                f"source {source_name!r} lacks the "
                f"{REQUIRED_SOURCE_SCOPE!r} usage scope (approved scopes: "
                f"{list(scopes) or 'none'})"
            )

    # -- validated (hard quality gates over the feed window) ---------------
    # NOTE: staleness is NOT passed to validate_bars — the warm-up window
    # legitimately contains older bars; feed-level FRESHNESS is a property
    # of the NEWEST bar only (checked separately below).
    bars = list(bars)
    accepted, rejections = validate_bars(
        bars,
        expected_interval=expected_interval,
    )
    for rejection in rejections:
        reasons.append(
            f"quality rejection @bar {rejection.bar_index} "
            f"[{rejection.check}]: {rejection.reason}"
        )

    # -- warm-up sufficiency ---------------------------------------------------
    if len(bars) < required_warmup_bars:
        reasons.append(
            f"feed window has {len(bars)} bars — the strategy's indicator "
            f"warm-up requires {required_warmup_bars} (insufficient warm-up)"
        )

    # -- freshness (caller-supplied logical reference time) ------------------
    latest_ts: Optional[datetime] = None
    if bars:
        candidate = bars[-1].get("timestamp")
        if candidate is not None and getattr(candidate, "tzinfo", None) is not None:
            latest_ts = candidate.astimezone(UTC)
            age = (as_of - latest_ts).total_seconds()
            if age > max_staleness_seconds:
                reasons.append(
                    f"feed is STALE: newest bar is {age:.0f}s old "
                    f"(limit {max_staleness_seconds}s as of the session "
                    "reference time)"
                )
            if age < -future_tolerance_seconds:
                reasons.append(
                    f"feed is FUTURE-DATED: newest bar is {-age:.0f}s "
                    "ahead of the session reference time (beyond the "
                    f"{future_tolerance_seconds}s clock-skew tolerance) — "
                    "point-in-time violation"
                )

    # -- correct instrument mapping --------------------------------------------
    if not registry_confirmed:
        reasons.append(
            "instrument mapping unconfirmed — the session symbol must be "
            "resolved to a canonical instrument id in the governed "
            "registry (fail closed on ambiguity)"
        )
    if not (isinstance(canonical_instrument_id, str)
            and canonical_instrument_id.strip()):
        reasons.append(
            "canonical instrument id missing/empty — the feed cannot be "
            "proven correctly mapped to the traded instrument"
        )

    return OperationalFeedReport(
        passed=not reasons,
        source_name=source_name,
        source_status=source_status,
        approved_scopes=scopes,
        symbol=session_symbol,
        canonical_instrument_id=(
            canonical_instrument_id.strip()
            if isinstance(canonical_instrument_id, str)
            and canonical_instrument_id.strip() else None
        ),
        bar_count=len(bars),
        warmup_required=required_warmup_bars,
        quality_rejections=tuple(rejections),
        latest_bar_timestamp=latest_ts,
        as_of=as_of,
        reasons=tuple(reasons),
    )


__all__ = [
    "RESEARCH_HISTORY_DECISION_ID",
    "RESEARCH_HISTORY_STATUS",
    "REQUIRED_SOURCE_STATUS",
    "REQUIRED_SOURCE_SCOPE",
    "DEFAULT_MAX_STALENESS_SECONDS",
    "DEFAULT_FUTURE_TOLERANCE_SECONDS",
    "FeedGateError",
    "OperationalFeedReport",
    "evaluate_operational_feed",
]
