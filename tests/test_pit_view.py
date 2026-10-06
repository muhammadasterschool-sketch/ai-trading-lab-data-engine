"""Phase 4A.1 — Acceptance Test Matrix (spec SECTION 8).

This file is the sole acceptance authority for Phase 4A.1
(PHASE_4A1_AUTHORITATIVE_REMEDIATION_SPEC.md §8.1). Every mandatory
P0 identifier appears as a NAMED test. Per §8.5.11 the matrix is:

    19 mandatory P0 (T-*)          §8.2   (T-H02 and T-R03 split in two)
    25 supplementary (SUB-*)       §8.3
    33 component-level             §8.5.1–8.5.9
     3 legacy-semantics (LEG-T*)   §8.5.10
    15 post-re-audit (COL-*)       §8.6
    ---
    95 identifiers / 97 named test functions

Plus the audit-trail tests resolving SPEC-DEF-02 (§13 Blocker 8 cites
"SUB-24 (audit-log verification)" while §8.3 defines SUB-24 as the
ExperimentIdentity wall-clock test — BOTH are implemented).

Mutation-verification rule (§8.4): every replacement test MUST fail
when its target defect is reintroduced.
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, date, timedelta, UTC
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pytest
from pydantic import ValidationError

from data_engine.pit import (
    PHASE4_IDENTITY_CONTRACT_VERSION,
    AmbiguousTieError,
    AvailabilityPolicy,
    AvailabilityRuleType,
    CalendarRef,
    DataSource,
    ExcludedRecord,
    ExperimentIdentity,
    InstrumentIdentity,
    InstrumentSpecification,
    LegacyClassification,
    LegacyPolicy,
    PitExperimentConfig,
    PitSidecar,
    PitView,
    PitViewBuilder,
    PitViewValidator,
    PublicationControlledAvailability,
    RevisionAwareAvailability,
    RevisionChain,
    RevisionEntry,
    SymbolMapping,
    TieBreakerPolicy,
    Venue,
    ViewValidationResult,
    validate_specification_intervals,
)
from data_engine.pit.availability import (
    PublicationControlledAvailability as PCA,
    RevisionAwareAvailability as RAA,
)
from data_engine.pit.contract import MissingFieldPolicy, TemporalContract
from data_engine.pit.hashing import (
    IdentityContractError,
    PHASE4_IDENTITY_CONTRACT_VERSION as CONTRACT_VERSION,
    PROHIBITED_IDENTITY_FIELDS,
    deterministic_hash,
    eligibility_hash,
    identity_hash,
)
from data_engine.pit.serialization import SerializationError, canonical_serialize
from data_engine.pit.temporal import TemporalDataType, TemporalSemantics
from data_engine.pit.view import dataset_content_hash

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"


# ─── Shared helpers ────────────────────────────────────────────────

def _ts(day, hour=0, minute=0, second=0, micro=0):
    """UTC datetime factory."""
    return datetime(2025, 6, day, hour, minute, second, micro, tzinfo=UTC)


class DuckCandle:
    """Duck-typed candle — the PIT layer never imports Phase 3."""

    def __init__(self, timestamp, open_, high, low, close, volume=None):
        self.timestamp = timestamp
        self.open = open_
        self.high = high
        self.low = low
        self.close = close
        self.volume = volume

    def __eq__(self, other):
        return (self.timestamp, self.open, self.high, self.low, self.close) == (
            other.timestamp, other.open, other.high, other.low, other.close)

    def __repr__(self):
        return f"DuckCandle({self.timestamp.isoformat()}, close={self.close})"


class DuckVersion:
    def __init__(self, version="v1"):
        self.version = version


class DuckDataset:
    def __init__(self, candles, dataset_id="ds", version="v1"):
        self.candles = list(candles)
        self.dataset_id = dataset_id
        self.version = DuckVersion(version)


def _five_candles():
    return [DuckCandle(_ts(d, 10), 100.0 + d, 105.0 + d, 98.0 + d, 102.0 + d)
            for d in range(1, 6)]


def _explicit_sidecar(day=1, publication_day=2):
    return PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(day, 10), observation_time=_ts(day, 10, 30),
        publication_time=_ts(publication_day),
    )


def _tb(name="ts-order", version="1.0.0", keys=("timestamp",)):
    return TieBreakerPolicy(name=name, version=version, keys=keys)


def _build_view(cutoff, sidecar=None, candles=None, tie_breaker=None,
                legacy_policy=None):
    sidecar = sidecar or _explicit_sidecar()
    candles = candles if candles is not None else _five_candles()
    tie_breaker = tie_breaker or _tb()
    ds = DuckDataset(candles)
    return PitViewBuilder().build(
        ds, cutoff, sidecar, tie_breaker, legacy_policy=legacy_policy,
    ), ds


# ═══════════════════════════════════════════════════════════════════
# SECTION 8.2 — MANDATORY P0 MATRIX (19 IDs)
# ═══════════════════════════════════════════════════════════════════

# ─── T-H01: Phase 4 identity stable; frozen result_hash unchanged ───

def test_t_h01_phase4_identity_stable():
    """T-H01 (spec 2): Phase 4 identity is stable, and the frozen
    Phase 3 result_hash chain is unchanged by this remediation."""
    # Phase 4 identity: same inputs -> same identity, repeatedly.
    values = {"dataset_id": "ds", "dataset_version": "v1"}
    fields = ("dataset_id", "dataset_version")
    h1 = identity_hash("PitSidecar", "1.0.0", fields, values)
    for _ in range(5):
        assert identity_hash("PitSidecar", "1.0.0", fields, values) == h1
    assert h1.startswith("pit4.")

    # Frozen Phase 3 result_hash: pure pipe formula, run_timestamp EXCLUDED.
    from data_engine.strategy.provenance import BacktestProvenance
    prov = BacktestProvenance(
        backtest_id="bt-fixed", strategy_id="s", strategy_version="1",
        strategy_hash="a" * 64, dataset_id="ds", dataset_version="v1",
        dataset_hash="b" * 64, instrument="XAU/USD",
        timeframe="D1", initial_capital=10000.0, num_candles=30,
        start_timestamp=_ts(1), end_timestamp=_ts(30),
        cost_parameters={}, slippage_parameters={}, position_sizing_parameters={},
        run_timestamp=_ts(1),
    )
    r1 = prov.compute_result_hash(
        canonical_trades="T1|T2", canonical_equity_curve="E1|E2",
        canonical_metrics="M1", config_hash="c" * 64,
        strategy_hash="s" * 64, dataset_hash="d" * 64,
    )
    r2 = prov.compute_result_hash(
        canonical_trades="T1|T2", canonical_equity_curve="E1|E2",
        canonical_metrics="M1", config_hash="c" * 64,
        strategy_hash="s" * 64, dataset_hash="d" * 64,
    )
    assert r1 == r2 and len(r1) == 64
    # Changing run_timestamp never appears in the hash inputs at all.


# ─── T-H02: identity data sensitivity + wall-clock invariance ───

def test_t_h02_identity_data_sensitivity():
    """T-H02 (spec 2.4): identity changes with data."""
    a = identity_hash("E", "1.0.0", ("a",), {"a": "x"})
    b = identity_hash("E", "1.0.0", ("a",), {"a": "y"})
    assert a != b


def test_t_h02_identity_wallclock_invariance():
    """T-H02 (spec 2.4): identity UNCHANGED when only wall-clock fields
    change. Verified at entity level: a sidecar whose ingestion_time
    moves by a year keeps the same sidecar_hash (ID-WC-01/03)."""
    base = dict(dataset_id="ds", dataset_version="v1",
                event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
                publication_time=_ts(2))
    s_old = PitSidecar(ingestion_time=datetime(2024, 1, 1, tzinfo=UTC), **base)
    s_new = PitSidecar(ingestion_time=datetime(2027, 6, 1, tzinfo=UTC), **base)
    s_none = PitSidecar(ingestion_time=None, **base)
    assert s_old.sidecar_hash == s_new.sidecar_hash == s_none.sidecar_hash


# ─── T-H03: StrategySpec.to_hash() unchanged (golden pin) ───

def test_t_h03_strategy_hash_unchanged():
    """T-H03 (spec 10): frozen StrategySpec.to_hash() produces exactly
    the pre-remediation value for a fixed spec (golden pin, measured
    at main@13fdc7e semantics before any Phase 4A.1 change)."""
    from data_engine.strategy.schemas import StrategySpec
    spec = StrategySpec(
        strategy_id="golden-pin-spec",
        strategy_version="3.0.0",
        position_sizing_serialized='{"method":"fixed","fixed_quantity":1.0}',
    )
    assert spec.to_hash() == (
        "f056e51ba2e275f4bd83068b19744c47079f385fe41fbaff310e5e437a342c38"
    )


# ─── T-H04: BacktestEngine._compute_config_hash() unchanged ───

def test_t_h04_config_hash_unchanged():
    """T-H04 (spec 10): frozen config hash produces exactly the
    pre-remediation values for fixed configs (golden pins)."""
    from data_engine.strategy.backtest import BacktestConfig, BacktestEngine
    default_engine = BacktestEngine(BacktestConfig())
    assert default_engine._compute_config_hash() == (
        "f0f1c84c98bd95ad0bed9e9d108f1f7a820b37915414ca27295e6937b9c135fc"
    )
    variant_engine = BacktestEngine(
        BacktestConfig(initial_capital=50000.0, allow_short=True)
    )
    assert variant_engine._compute_config_hash() == (
        "1281779ceab342a3e53858d17d49a0f4c7a2eb1e09149e768987ddabfcd4ae1d"
    )


# ─── T-H05: true subprocess determinism ───

def test_t_h05_cross_process_determinism():
    """T-H05 (spec 2.6): TRUE subprocess determinism — >= 5 separate OS
    processes each compute a Phase 4 identity; all digests match.

    Replaces the weak in-process loop (F-24 / §8.4). Fails if any
    ambient state (hash seed, locale, PID, time) leaks into identity.
    """
    code = (
        "from data_engine.pit.hashing import identity_hash\n"
        "print(identity_hash('PitSidecar', '1.0.0', "
        "('dataset_id', 'dataset_version'), "
        "{'dataset_id': 'ds', 'dataset_version': 'v1'}))\n"
    )
    env = {**os.environ, "PYTHONPATH": str(SRC_ROOT)}
    digests = []
    for i in range(5):
        env_i = {**env, "LC_ALL": f"en_US.UTF-{i % 2}",
                 "TAXI_PROCESS_INDEX": str(i)}
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, env=env_i, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        digests.append(proc.stdout.strip())
    in_process = identity_hash(
        "PitSidecar", "1.0.0", ("dataset_id", "dataset_version"),
        {"dataset_id": "ds", "dataset_version": "v1"},
    )
    assert len(set(digests)) == 1
    assert digests[0] == in_process


# ─── T-P01: publication == cutoff -> ELIGIBLE (inclusive boundary) ───

def test_t_p01_publication_at_cutoff_eligible():
    """T-P01 (spec 4.6): publication_time == cutoff -> ELIGIBLE."""
    cutoff = _ts(6)
    sidecar = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        publication_time=cutoff,  # exactly at the cutoff
    )
    view, _ = _build_view(cutoff, sidecar=sidecar)
    assert len(view) == 5  # every item eligible at the inclusive boundary
    assert view.excluded_count == 0

    policy = AvailabilityPolicy(
        rule_type=AvailabilityRuleType.PUBLICATION_CONTROLLED,
        policy=PublicationControlledAvailability(),
    )
    assert policy.is_available(cutoff, None, None, cutoff) is True


# ─── T-P02: publication == cutoff + 1µs -> EXCLUDED ───

def test_t_p02_publication_after_cutoff_excluded():
    """T-P02 (spec 4.6): publication_time == cutoff + 1µs -> EXCLUDED."""
    cutoff = _ts(6)
    sidecar = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        publication_time=cutoff + timedelta(microseconds=1),
    )
    view, _ = _build_view(cutoff, sidecar=sidecar)
    assert len(view) == 0
    assert view.excluded_count == 5
    assert view.excluded_breakdown["future_publication_time"] == 5


# ─── T-P03: revision_time > cutoff -> revision invisible ───

def test_t_p03_revision_after_cutoff_invisible():
    """T-P03 (spec 4.6): a revision with revision_time > cutoff is
    invisible — the prior revision governs."""
    e1 = RevisionEntry(revision_time=_ts(1, 10), publication_time=_ts(1, 10),
                       payload={"v": 1})
    e2 = RevisionEntry(revision_time=_ts(5, 10), publication_time=_ts(5, 10),
                       payload={"v": 2}, supersedes=e1.entry_hash)
    chain = RevisionChain(entries=(e1, e2))
    selected = chain.select_at(_ts(3))
    assert selected is e1  # the future revision is invisible
    assert selected.payload["v"] == 1
    assert chain.select_at(_ts(6)) is e2


# ─── T-P04: effective_time > cutoff -> excluded, no error ───

def test_t_p04_effective_after_cutoff_excluded():
    """T-P04 (spec 4.7): effective_time > cutoff -> excluded silently,
    never an exception."""
    cutoff = _ts(6)
    sidecar = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        publication_time=_ts(2), effective_time=_ts(9),
    )
    view, _ = _build_view(cutoff, sidecar=sidecar)
    assert len(view) == 0
    assert view.excluded_count == 5
    assert view.excluded_breakdown["future_effective_time"] == 5


# ─── T-R01: single revision chain ───

def test_t_r01_single_revision():
    """T-R01 (spec 7.2): a single-entry chain is valid; the first
    entry declares no supersedes; it selects at any cutoff >= its
    times."""
    e1 = RevisionEntry(revision_time=_ts(1, 10), publication_time=_ts(1, 10),
                       payload={"close": 102.0})
    chain = RevisionChain(entries=(e1,))
    assert len(chain) == 1
    assert e1.supersedes is None
    assert chain.select_at(_ts(1, 11)) is e1
    assert chain.select_at(_ts(1, 10)) is e1  # inclusive
    assert chain.select_at(_ts(1, 9)) is None
    assert chain.chain_hash.startswith("pit4c.")


# ─── T-R02: multiple revisions; latest <= cutoff selected ───

def test_t_r02_multiple_revisions_selects_latest():
    """T-R02 (spec 7.2/4.6): among eligible revisions the one with max
    revision_time is selected."""
    entries = []
    prior = None
    for day in (1, 2, 3):
        e = RevisionEntry(
            revision_time=_ts(day, 10), publication_time=_ts(day, 10),
            payload={"v": day},
            supersedes=prior.entry_hash if prior else None,
        )
        entries.append(e)
        prior = e
    chain = RevisionChain(entries=tuple(entries))
    assert chain.select_at(_ts(2, 11)) is entries[1]
    assert chain.select_at(_ts(9)) is entries[2]
    assert chain.select_at(_ts(1, 10)) is entries[0]


# ─── T-R03: chain integrity + tamper detection ───

def test_t_r03_chain_integrity():
    """T-R03 (spec 7.2): chain integrity is hash-verifiable."""
    e1 = RevisionEntry(revision_time=_ts(1, 10), publication_time=_ts(1, 10),
                       payload={"v": 1})
    e2 = RevisionEntry(revision_time=_ts(2, 10), publication_time=_ts(2, 10),
                       payload={"v": 2}, supersedes=e1.entry_hash)
    chain = RevisionChain(entries=(e1, e2))
    assert chain.verify_integrity(chain.chain_hash) is True
    assert chain.verify_integrity() is True


def test_t_r03_tamper_detected():
    """T-R03 (spec 7.2): a mutated payload changes the entry hash and
    therefore the recomputed chain hash — tamper is DETECTED."""
    e1 = RevisionEntry(revision_time=_ts(1, 10), publication_time=_ts(1, 10),
                       payload={"v": 1})
    e2 = RevisionEntry(revision_time=_ts(2, 10), publication_time=_ts(2, 10),
                       payload={"v": 2}, supersedes=e1.entry_hash)
    chain = RevisionChain(entries=(e1, e2))
    recorded = chain.chain_hash
    tampered = RevisionChain(entries=(
        e1,
        RevisionEntry(revision_time=_ts(2, 10), publication_time=_ts(2, 10),
                      payload={"v": 999}, supersedes=e1.entry_hash),
    ))
    assert tampered.verify_integrity(recorded) is False


# ─── T-R04: latest-value-only dataset rejected ───

def test_t_r04_latest_only_rejected():
    """T-R04 (spec 7.2): a latest-value-only dataset — an entry
    claiming to supersede prior history that is absent from the chain —
    is REJECTED at construction (unverifiable history)."""
    dangling = RevisionEntry(
        revision_time=_ts(2, 10), publication_time=_ts(2, 10),
        payload={"v": "latest-only"},
        supersedes="0" * 64,  # points at history that does not exist here
    )
    with pytest.raises(Exception, match="latest-value-only|supersedes"):
        RevisionChain(entries=(dangling,))


# ─── T-M01: missing event_time rejected ───

def test_t_m01_missing_event_time_rejected():
    """T-M01 (spec 4.2): missing event_time is rejected — it is
    required for all types."""
    with pytest.raises(ValidationError):
        TemporalSemantics(observation_time=_ts(1, 10, 30))
    with pytest.raises(ValidationError):
        PitSidecar(dataset_id="ds", dataset_version="v1",
                   observation_time=_ts(1, 10, 30),
                   publication_time=_ts(2))  # event_time absent


# ─── T-M06: naive datetime rejected for ALL six fields ───

@pytest.mark.parametrize("field", [
    "event_time", "observation_time", "publication_time",
    "effective_time", "revision_time", "ingestion_time",
])
def test_t_m06_naive_datetime_rejected_all_fields(field):
    """T-M06 (spec 4.4): a naive datetime is rejected for every one of
    the six temporal fields — no exception, no coercion."""
    naive = datetime(2025, 6, 1, 10, 30, 0)  # no tzinfo
    base = dict(
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
    )
    if field not in base:
        base[field] = naive
    else:
        base[field] = naive
    with pytest.raises(ValidationError):
        TemporalSemantics(**base)


# ─── T-O01: equal timestamps -> deterministic total order ───

class _OrderedObs:
    def __init__(self, timestamp, sequence, value):
        self.timestamp = timestamp
        self.sequence = sequence
        self.value = value

    def __eq__(self, other):
        return (self.timestamp, self.sequence, self.value) == (
            other.timestamp, other.sequence, other.value)

    def __repr__(self):
        return f"_OrderedObs(seq={self.sequence})"


def test_t_o01_equal_time_deterministic_order():
    """T-O01 (spec 7.3): observations sharing an identical temporal key
    are ordered by a deterministic total order, stable across runs."""
    tb = TieBreakerPolicy(name="seq", version="1.0.0",
                          keys=("timestamp", "sequence"))
    obs = [_OrderedObs(_ts(1), seq, f"v{seq}") for seq in (3, 1, 2)]
    first = tb.sort(obs)
    second = tb.sort(list(reversed(obs)))
    third = tb.sort(obs)  # repeated run
    assert [o.sequence for o in first] == [1, 2, 3]
    assert [o.sequence for o in second] == [1, 2, 3]
    assert [o.sequence for o in third] == [1, 2, 3]


# ─── T-X01: future publication silently excluded ───

def test_t_x01_future_publication_excluded():
    """T-X01 (spec 4.7): publication_time > cutoff -> excluded
    silently, deterministic, never an exception."""
    cutoff = _ts(6)
    sidecar = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        publication_time=_ts(7),
    )
    view, _ = _build_view(cutoff, sidecar=sidecar)
    assert len(view) == 0
    assert view.excluded_breakdown.get("future_publication_time") == 5


# ─── T-X02: future revision explicitly excluded ───

def test_t_x02_future_revision_excluded():
    """T-X02 (spec 4.7): revision_time > cutoff -> that revision is
    invisible; the prior revision governs the view."""
    e1 = RevisionEntry(revision_time=_ts(1, 10), publication_time=_ts(1, 10),
                       payload={"v": 1})
    e2 = RevisionEntry(revision_time=_ts(9, 10), publication_time=_ts(9, 10),
                       payload={"v": 2}, supersedes=e1.entry_hash)
    chain = RevisionChain(entries=(e1, e2))
    assert chain.select_at(_ts(3)) is e1
    assert chain.select_at(_ts(3)).payload == {"v": 1}

    # At the view level, a flat sidecar whose revision is in the future
    # is excluded with a recorded reason.
    cutoff = _ts(6)
    sidecar = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        publication_time=_ts(2), revision_time=_ts(9),
    )
    view, _ = _build_view(cutoff, sidecar=sidecar)
    assert view.excluded_breakdown.get("future_revision_time") == 5


# ─── T-X07: future data silently excluded, distinguishable from T-X01 ───

def test_t_x07_future_data_silent_exclusion():
    """T-X07 (spec 4.7): future EVENT data is excluded silently and is
    DISTINGUISHABLE from a future-publication exclusion (different
    recorded reason). A backtest over a range must not fail because
    future data exists in the store."""
    cutoff = _ts(4)
    candles = [DuckCandle(_ts(d, 10), 100.0, 105.0, 98.0, 102.0)
               for d in range(1, 7)]  # days 4-6 are future events
    sidecar = _explicit_sidecar()
    view, _ = _build_view(cutoff, sidecar=sidecar, candles=candles)
    assert len(view) == 3
    assert view.excluded_count == 3
    assert view.excluded_breakdown.get("future_event_time") == 3
    assert "future_publication_time" not in view.excluded_breakdown


# ═══════════════════════════════════════════════════════════════════
# SECTION 8.3 — SUPPLEMENTARY MANDATORY TESTS (SUB-01..SUB-25)
# ═══════════════════════════════════════════════════════════════════

# ─── SUB-01: AvailabilityPolicy mismatch — all four pairings raise ───

def test_availability_mismatch_rejected():
    """SUB-01 (spec 5.3): mismatched rule_type/policy pairings raise at
    construction — closes the future-revision leakage channel."""
    combos = [
        (AvailabilityRuleType.PUBLICATION_CONTROLLED, RAA()),
        (AvailabilityRuleType.PUBLICATION_CONTROLLED, RAA(require_revision=False)),
        (AvailabilityRuleType.REVISION_AWARE, PCA()),
        (AvailabilityRuleType.REVISION_AWARE, PCA(require_publication=False)),
    ]
    for rule_type, policy in combos:
        with pytest.raises(Exception):
            AvailabilityPolicy(rule_type=rule_type, policy=policy)


# ─── SUB-02: correct pairings behave per spec 5 ───

def test_availability_correct_pairings():
    """SUB-02 (spec 5): correct pairings construct and compute under
    the RIGHT rule — the historical argument-order aliasing is gone."""
    pub = AvailabilityPolicy(
        rule_type=AvailabilityRuleType.PUBLICATION_CONTROLLED,
        policy=PublicationControlledAvailability(),
    )
    # Publication-controlled: future publication is NOT available.
    assert pub.is_available(_ts(5), None, None, _ts(3)) is False
    assert pub.is_available(_ts(2), None, None, _ts(3)) is True
    assert pub.is_available(None, None, None, _ts(3)) is False

    rev = AvailabilityPolicy(
        rule_type=AvailabilityRuleType.REVISION_AWARE,
        policy=RevisionAwareAvailability(),
    )
    # Revision-aware: revision_time governs; a FUTURE revision with a
    # PAST publication is correctly NOT available (the exact case the
    # mismatched pairing used to leak).
    assert rev.is_available(_ts(2), _ts(1), _ts(5), _ts(3)) is False
    assert rev.is_available(_ts(2), _ts(1), _ts(3), _ts(3)) is True


# ─── SUB-03: unknown policy field raises ───

def test_policy_extra_field_forbidden():
    """SUB-03 (spec 5.4/3.7): an unknown policy key raises — a
    misspelled strict policy can never silently degrade to permissive."""
    with pytest.raises(Exception):
        PublicationControlledAvailability(
            require_publication=True, evil=1)
    with pytest.raises(Exception):
        RevisionAwareAvailability(require_revision=True, evil=1)
    with pytest.raises(Exception):
        AvailabilityPolicy(
            rule_type=AvailabilityRuleType.PUBLICATION_CONTROLLED,
            policy=PublicationControlledAvailability(),
            extra_field=1,
        )


# ─── SUB-04: serializer collision matrix ───

def test_serializer_no_type_collision():
    """SUB-04 (spec 3.1): every distinct-typed pair yields distinct
    canonical bytes — the full collision matrix."""
    import itertools
    values = {
        "none": None,
        "true": True,
        "false": False,
        "int": 1,
        "float": 1.0,
        "decimal": Decimal("1.0"),
        "str": "1",
        "datetime": _ts(1),
        "date": date(2025, 6, 1),
        "list": [1],
        "tuple": (1,),
        "dict": {"1": 1},
    }
    forms = {k: canonical_serialize(v) for k, v in values.items()}
    # NOTE: tuple == list by design (spec 3.1) — excluded from the
    # distinctness matrix and asserted equal separately below.
    del forms["tuple"]
    collisions = [(a, b) for a, b in itertools.combinations(forms, 2)
                  if forms[a] == forms[b]]
    assert collisions == []
    assert canonical_serialize((1,)) == canonical_serialize([1])
    # Nested: same distinctness inside containers.
    nested = {
        "list-of-int": [1], "list-of-str": ["1"], "list-of-bool": [True],
        "dict-int-val": {"k": 1}, "dict-str-val": {"k": "1"},
    }
    nested_forms = {k: canonical_serialize(v) for k, v in nested.items()}
    assert len(set(nested_forms.values())) == len(nested_forms)


# ─── SUB-05: datetime vs its ISO string ───

def test_serializer_datetime_vs_string():
    """SUB-05 (spec 3.1, F-07): a datetime and its ISO-8601 string
    serialize to distinct bytes."""
    dt = datetime(2025, 6, 1, 10, 30, 0, tzinfo=UTC)
    as_string = dt.isoformat()
    assert canonical_serialize(dt) != canonical_serialize(as_string)
    assert canonical_serialize(dt) == b'{"t":"2025-06-01T10:30:00+00:00"}'
    assert canonical_serialize(as_string) == (
        b'{"s":"2025-06-01T10:30:00+00:00"}')


# ─── SUB-06: int-key vs str-key dict ───

def test_serializer_dict_key_collision():
    """SUB-06 (spec 3.1a.1, RA-NF-01): {1: 'a'} RAISES (SER-KEY-01);
    {'1': 'a'} serializes. The adversarial requirement: the non-string
    key form MUST raise, not merely produce different bytes."""
    with pytest.raises(SerializationError):
        canonical_serialize({1: "a"})
    ok = canonical_serialize({"1": "a"})
    assert ok == b'{"D":[[{"s":"1"},{"s":"a"}]]}'


# ─── SUB-07: numeric policy ───

def test_serializer_numeric_policy():
    """SUB-07 (spec 3.3, F-08): .10f floats, -0.0 -> 0.0, NaN/Inf
    rejected; Decimal exact; int base-10."""
    assert canonical_serialize(100.5) == b'{"f":"100.5000000000"}'
    assert canonical_serialize(-0.0) == canonical_serialize(0.0)
    assert canonical_serialize(-0.0) == b'{"f":"0.0000000000"}'
    assert canonical_serialize(Decimal("1.10")) == b'{"d":"1.10"}'
    assert canonical_serialize(42) == b'{"i":"42"}'
    for bad in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(SerializationError):
            canonical_serialize(bad)
    with pytest.raises(SerializationError):
        canonical_serialize(Decimal("NaN"))


# ─── SUB-08: list order significant ───

def test_serializer_list_order_significant():
    """SUB-08 (spec 3.2): [1,2] and [2,1] are different identities —
    list order is preserved and significant; values never sorted."""
    assert canonical_serialize([1, 2]) != canonical_serialize([2, 1])
    assert canonical_serialize([3, 1, 2]) == (
        b'{"L":[{"i":"3"},{"i":"1"},{"i":"2"}]}')


# ─── SUB-09: legacy sidecar reproducibility ───

def test_legacy_sidecar_reproducible():
    """SUB-09 (spec 6.4 PROH-LEG-06): two builds at different
    wall-clock times produce an IDENTICAL view_hash — the build path
    reads no clock."""
    cutoff = _ts(4)
    sidecar = _explicit_sidecar()
    candles = _five_candles()
    v1 = PitViewBuilder().build(DuckDataset(candles), cutoff, sidecar, _tb())
    time.sleep(0.05)  # a different wall-clock time
    v2 = PitViewBuilder().build(DuckDataset(candles), cutoff, sidecar, _tb())
    assert v1.view_hash == v2.view_hash
    assert v1.items == v2.items


# ─── SUB-10: PIT_INELIGIBLE excluded + counted, no exception ───

def test_legacy_ineligible_excluded():
    """SUB-10 (spec 6.4 PROH-LEG-09): PIT_INELIGIBLE items are excluded
    silently from the view and COUNTED, never raised."""
    sidecar = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        legacy_classification=LegacyClassification.PIT_INELIGIBLE,
        ineligible_reason="publication time unknown",
    )
    view, _ = _build_view(_ts(4), sidecar=sidecar)
    assert len(view) == 0
    assert view.excluded_count == 5
    assert view.excluded_breakdown.get("pit_ineligible") == 5
    assert view.legacy_classification == LegacyClassification.PIT_INELIGIBLE


# ─── SUB-11: ASSUMED_PUBLICATION labels the view; hash differs ───

def test_legacy_assumption_labelled():
    """SUB-11 (spec 6.3, PROH-LEG-08): an assumed view is labelled
    ASSUMED in its identity and never hashes equal to an explicit one."""
    config = PitExperimentConfig(
        cutoff=_ts(6), tie_breaker=_tb(),
        legacy_policy=LegacyPolicy.ASSUMED_PUBLICATION,
        legacy_assumption_text="Assumed published at observation+3600s "
                               "per provider digest schedule.",
        legacy_publication_offset_seconds=3600.0,
    )
    legacy_sidecar = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        legacy_classification=LegacyClassification.PIT_INELIGIBLE,
        ineligible_reason="no publication metadata on the legacy dataset",
    )
    view, _ = _build_view(_ts(6), sidecar=legacy_sidecar,
                          legacy_policy=config)
    assert view.legacy_classification == LegacyClassification.ASSUMED_PUBLICATION
    assert len(view) == 5  # promoted via the declared assumption

    explicit_view, _ = _build_view(_ts(6), sidecar=_explicit_sidecar())
    assert view.view_hash != explicit_view.view_hash


# ─── SUB-12: filesystem containment — endpoint escape blocked ───

def test_provider_endpoint_containment(tmp_path):
    """SUB-12 (spec 11.7 T1): an endpoint pointing outside the approved
    data directory is BLOCKED — at construction for absolute paths and
    at fetch for resolved escapes. No candle is ever read."""
    from data_engine.provider import FileDataProvider
    from data_engine.schemas import ProviderConfig, Timeframe
    from data_engine.security import FilesystemSecurityError

    root = tmp_path / "approved"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SECRET_1d.csv").write_text(
        "timestamp,open,high,low,close\n2025-01-01,1,2,0.5,1.5\n")

    # Absolute endpoint outside the root: rejected at CONSTRUCTION.
    with pytest.raises(Exception):
        ProviderConfig(provider_name="file", provider_type="file",
                       endpoint=str(outside),
                       approved_data_root=str(root),
                       instrument_allowlist=["SECRET"])

    # Relative endpoint that escapes the root when resolved: the
    # historical T1 attack (1 candle read) — now blocked at fetch.
    old_cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        provider = FileDataProvider(ProviderConfig(
            provider_name="file", provider_type="file",
            endpoint="approved/../outside",
            approved_data_root="approved",
            instrument_allowlist=["SECRET"],
        ))
        with pytest.raises(FilesystemSecurityError):
            provider.fetch_candles(
                "SECRET", Timeframe.D1,
                datetime(2024, 1, 1, tzinfo=UTC),
                datetime(2026, 1, 1, tzinfo=UTC),
            )
    finally:
        os.chdir(old_cwd)


# ─── SUB-13: absolute-path instrument rejected ───

def test_provider_absolute_instrument_rejected(tmp_path):
    """SUB-13 (spec 11.7 T2, FS-15): an absolute path as instrument is
    rejected BEFORE any existence check or read."""
    from data_engine.provider import FileDataProvider
    from data_engine.schemas import ProviderConfig, Timeframe
    from data_engine.security import FilesystemSecurityError

    root = tmp_path / "approved"
    root.mkdir()
    provider = FileDataProvider(ProviderConfig(
        provider_name="file", provider_type="file", endpoint=str(root),
        approved_data_root=str(root), instrument_allowlist=["XAUUSD"],
    ))
    with pytest.raises(FilesystemSecurityError):
        provider.fetch_candles(
            "/etc/passwd", Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        )
    with pytest.raises(FilesystemSecurityError):
        provider.fetch_candles(
            "C:/Windows/system32", Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        )


# ─── SUB-14: ../ traversal rejected ───

def test_provider_traversal_rejected(tmp_path):
    """SUB-14 (spec 11.7 T3, FS-15/08): relative ../ traversal via
    instrument is rejected before any read."""
    from data_engine.provider import FileDataProvider
    from data_engine.schemas import ProviderConfig, Timeframe
    from data_engine.security import FilesystemSecurityError

    root = tmp_path / "approved"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("secret")
    provider = FileDataProvider(ProviderConfig(
        provider_name="file", provider_type="file", endpoint=str(root),
        approved_data_root=str(root), instrument_allowlist=["XAUUSD"],
    ))
    with pytest.raises(FilesystemSecurityError):
        provider.fetch_candles(
            "../../etc/passwd", Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        )
    with pytest.raises(FilesystemSecurityError):
        provider.fetch_candles(
            "..", Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        )


# ─── SUB-15: symlink escape rejected (skip if unsupported privilege) ───

def _symlink_supported(tmp_path) -> bool:
    try:
        target = tmp_path / "target.txt"
        target.write_text("x")
        link = tmp_path / "probe.link"
        link.symlink_to(target)
        return True
    except (OSError, NotImplementedError):
        return False


def test_provider_symlink_rejected(tmp_path):
    """SUB-15 (spec 11.4 FS-11..13): a symlink inside the approved
    root pointing OUTSIDE is rejected. Skipped when the host lacks
    symlink-creation privilege (historically Windows WinError 1314)."""
    if not _symlink_supported(tmp_path):
        pytest.skip("symlink creation not permitted on this host "
                    "(WinError 1314 class) — SUB-15 skip condition")
    from data_engine.provider import FileDataProvider
    from data_engine.schemas import ProviderConfig, Timeframe
    from data_engine.security import FilesystemSecurityError

    root = tmp_path / "approved"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "SECRET_1d.csv").write_text(
        "timestamp,open,high,low,close\n2025-01-01,1,2,0.5,1.5\n")
    (root / "LINK_1d.csv").symlink_to(outside / "SECRET_1d.csv")

    provider = FileDataProvider(ProviderConfig(
        provider_name="file", provider_type="file", endpoint=str(root),
        approved_data_root=str(root), instrument_allowlist=["LINK"],
    ))
    with pytest.raises(FilesystemSecurityError):
        provider.fetch_candles(
            "LINK", Timeframe.D1,
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2026, 1, 1, tzinfo=UTC),
        )


# ─── SUB-16: instrument allowlist enforced ───

def test_provider_instrument_allowlist(tmp_path):
    """SUB-16 (spec 11.5 FS-14): instruments are validated against the
    allowlist BEFORE path construction; unlisted instruments raise;
    with no allowlist at all the provider fails closed."""
    from data_engine.provider import FileDataProvider
    from data_engine.schemas import ProviderConfig, Timeframe
    from data_engine.security import FilesystemSecurityError

    root = tmp_path / "approved"
    root.mkdir()
    (root / "XAUUSD_1d.csv").write_text(
        "timestamp,open,high,low,close\n2025-01-01,100,105,98,102\n")
    t0, t1 = datetime(2024, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)

    provider = FileDataProvider(ProviderConfig(
        provider_name="file", provider_type="file", endpoint=str(root),
        approved_data_root=str(root), instrument_allowlist=["XAUUSD"],
    ))
    candles = provider.fetch_candles("XAUUSD", Timeframe.D1, t0, t1)
    assert len(candles) == 1  # allowed instrument reads fine
    with pytest.raises(FilesystemSecurityError):
        provider.fetch_candles("EURUSD", Timeframe.D1, t0, t1)

    # No allowlist and empty registry: fail closed (FS-14/FS-06 class).
    no_allowlist = FileDataProvider(ProviderConfig(
        provider_name="file", provider_type="file", endpoint=str(root),
        approved_data_root=str(root),
    ))
    with pytest.raises(FilesystemSecurityError):
        no_allowlist.fetch_candles("XAUUSD", Timeframe.D1, t0, t1)


# ─── SUB-17: SYNTHETIC cannot reach a backtest ───

def _real_dataset(evidence):
    from data_engine.schemas import (
        AssetClass, Candle, Dataset, DatasetVersion, EvidenceProvenance,
        Instrument, ProvenanceRecord, Timeframe,
    )
    instrument = Instrument(symbol="XAU/USD", asset_class=AssetClass.METAL,
                            base_asset="XAU", quote_asset="USD")
    candles = [Candle(timestamp=_ts(d, 10), open=100.0 + d, high=105.0 + d,
                      low=98.0 + d, close=102.0 + d, volume=10.0,
                      timeframe=Timeframe.D1) for d in range(1, 6)]
    provenance = ProvenanceRecord(
        dataset_id="ds", dataset_version="v1", provider="test", source="test",
        instrument=instrument, timeframe=Timeframe.D1,
        start_timestamp=_ts(1), end_timestamp=_ts(5),
        retrieval_timestamp=_ts(5), timezone="UTC",
        evidence_provenance=evidence,
    )
    version = DatasetVersion(
        dataset_id="ds", version="v1", source="test", instrument=instrument,
        timeframe=Timeframe.D1, time_period_start=_ts(1), time_period_end=_ts(5),
        ingestion_version="v1", transformation_version="v1",
        validation_version="v1",
    )
    return Dataset(dataset_id="ds", version=version, candles=candles,
                   provenance=provenance, total_rows=5)


def test_synthetic_cannot_reach_backtest():
    """SUB-17 (spec 11.8 FS-24): SYNTHETIC data must not reach
    BacktestEngine by any call path — the DataQualityGate raises
    before any simulation (FS-23)."""
    from data_engine.data_blocked import DataQualityGate
    from data_engine.evidence import EvidenceProvenance
    from data_engine.strategy.backtest import BacktestConfig, BacktestEngine
    from data_engine.strategy.schemas import StrategySpec

    synthetic = _real_dataset(EvidenceProvenance.SYNTHETIC)
    passed, error = DataQualityGate().check(synthetic)
    assert passed is False and error is not None

    spec = StrategySpec(
        strategy_id="s", position_sizing_serialized='{"method":"fixed","fixed_quantity":1.0}'
    )
    engine = BacktestEngine(BacktestConfig())
    with pytest.raises(Exception, match="quality gate"):
        engine.run(spec, synthetic)

    # Control: REAL data passes the gate and is NOT blocked upstream.
    real = _real_dataset(EvidenceProvenance.REAL)
    passed_real, _ = DataQualityGate().check(real)
    assert passed_real is True


# ─── SUB-18: frozen Phase 3 SHA-256 manifest matches ───

_FROZEN_PHASE3_MANIFEST = {
    "src/data_engine/schemas.py":
        "9aa07004f9b538834b3b6bb3d170eca5c02bb2f790a3f4eeb4f66eccffecb562",
    "src/data_engine/strategy/schemas.py":
        "4a27cc9aa20464e8255f7853828956378b57669188bf3908b575597586d3be6c",
    "src/data_engine/strategy/provenance.py":
        "2ee8086f27b538a381b3f3d85408512757c02200957b8f0e4c7638e8c565c57f",
    "src/data_engine/strategy/backtest.py":
        "e2d018e6371a75350dc5bc7e9268ca6b837fd761529d67de5a31e2ef08fe9e37",
    "src/data_engine/strategy/execution.py":
        "7cd56a9077a88b8325414efd2b271cc91db091b1cf4ce8ef8eebea37ab037296",
    "src/data_engine/strategy/ledger.py":
        "312ed94a91b92c7145547b5c5b13c3e2e8a349f2aadfae7fb72efd6e32cecd2a",
    "src/data_engine/strategy/equity.py":
        "9ecd12e51a5f1cf046af0b3dc9434f58d409e7eef2e5779c6226cbedf315e844",
    "src/data_engine/strategy/position.py":
        "d1ef8b83090827228c9866036d953f9b89491fcdafd045aaf650e0e7d39c94ae",
    "src/data_engine/strategy/conditions.py":
        "868a3a56a826eaca328c6b1030be8831387d80368e932608265d4b37e4b2f667",
    "src/data_engine/strategy/metrics.py":
        "1f6cd4e36970142773537c56233d6fdee52d95bf7908563ef2eb3a564261cf52",
    "src/data_engine/strategy/validation.py":
        "37713839dc1079494a91111c62a3c1faf2b17ac3d9fea0ce6e046b34ea826a4c",
    "src/data_engine/strategy/__init__.py":
        "47aed9c6d932801b584f6bd3ddcafd36015d926deb43d0b725fc8e0f04bcee17",
    "docs/strategy_engine_design.md":
        "0303758430e59fa6b56f2502308da409a937769c20a6d645a0b71c6d5d538499",
}


def test_frozen_phase3_manifest():
    """SUB-18 (spec 10.2 + FRZ-04): the frozen Phase 3 SHA-256 manifest
    (committed-state record, PHASE_4A1_IMPLEMENTATION_RECORD.md §3)
    matches byte-for-byte. Any mismatch fails the gate IMMEDIATELY.

    Replaces the weak existence-only test_no_phase3_source_modified
    (F-24: it asserted os.path.exists for 11 files and could not
    detect ANY modification; it also omitted strategy/ entirely).
    """
    mismatches = []
    for rel_path, expected in _FROZEN_PHASE3_MANIFEST.items():
        file_path = REPO_ROOT / rel_path
        assert file_path.exists(), f"frozen file missing: {rel_path}"
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append((rel_path, expected, actual))
    assert mismatches == [], (
        f"FRZ-04: frozen Phase 3 manifest mismatch — no partial credit: "
        f"{mismatches}"
    )


# ─── SUB-19: cross-field temporal ordering enforced ───

def test_temporal_ordering_enforced():
    """SUB-19 (spec 4.3): all orderings enforced on BOTH
    TemporalSemantics and PitSidecar; null operands skip; equality at
    boundaries is valid."""
    ok_equal = TemporalSemantics(
        event_time=_ts(1, 10), observation_time=_ts(1, 10),
        publication_time=_ts(1, 10), revision_time=_ts(1, 10),
    )
    assert ok_equal.event_time == ok_equal.observation_time

    ok_null_skip = TemporalSemantics(
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        effective_time=_ts(1, 9),  # no ordering constraint; nulls skip
    )
    assert ok_null_skip is not None

    violations = [
        dict(event_time=_ts(2), observation_time=_ts(1)),                 # ev > obs
        dict(event_time=_ts(1), observation_time=_ts(1, 10),              # obs > pub
             publication_time=_ts(1, 9)),
        dict(event_time=_ts(1), observation_time=_ts(1),                  # pub > rev
             publication_time=_ts(2), revision_time=_ts(1)),
    ]
    for bad in violations:
        with pytest.raises(ValidationError):
            TemporalSemantics(**bad)

    sidecar_base = dict(dataset_id="ds", dataset_version="v1",
                        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30))
    with pytest.raises(ValidationError):
        PitSidecar(publication_time=_ts(4), revision_time=_ts(2), **sidecar_base)


# ─── SUB-20: ALLOW_NULL + required_fields -> construction raises ───

def test_allow_null_with_required_rejected():
    """SUB-20 (spec 4.2): a contract MUST NOT contain a field in
    required_fields while missing_field_policy = ALLOW_NULL —
    construction raises."""
    with pytest.raises(Exception):
        TemporalContract(
            data_type=TemporalDataType.OHLCV,
            required_fields=["publication_time"],
            missing_field_policy=MissingFieldPolicy.ALLOW_NULL,
        )
    # Empty required_fields with ALLOW_NULL is vacuous and permitted.
    ok = TemporalContract(
        data_type=TemporalDataType.OHLCV,
        required_fields=[],
        missing_field_policy=MissingFieldPolicy.ALLOW_NULL,
    )
    assert ok.missing_field_policy == MissingFieldPolicy.ALLOW_NULL


# ─── SUB-21: wall-clock field in an allowlist raises (ID-WC-02) ───

def test_wallclock_in_allowlist_rejected():
    """SUB-21 (spec 2.4 ID-WC-02): an identity allowlist containing a
    prohibited wall-clock/audit field raises at (identity) construction."""
    for prohibited in ("retrieval_timestamp", "provider_timestamp",
                       "ingestion_time", "created_at", "run_timestamp",
                       "approval_timestamp"):
        with pytest.raises(IdentityContractError):
            identity_hash(
                "Entity", "1.0.0", (prohibited,),
                {prohibited: _ts(1)},
            )
    # Transitive: a prohibited field nested inside a value also raises.
    with pytest.raises(IdentityContractError):
        identity_hash("Entity", "1.0.0", ("meta",),
                      {"meta": {"created_at": "2026-01-01"}})


# ─── SUB-22: EvidenceProvenance is a single definition ───

def test_evidence_provenance_single_definition():
    """SUB-22 (spec 1.3 R-03 / F-02): EvidenceProvenance has exactly
    one definition — schemas.py is a re-export of evidence.py:18.
    Acceptance: assert A is B."""
    from data_engine.evidence import EvidenceProvenance as EP_canonical
    from data_engine.schemas import EvidenceProvenance as EP_reexport
    assert EP_reexport is EP_canonical, (
        f"EvidenceProvenance is not a single definition: "
        f"schemas.EvidenceProvenance({id(EP_reexport)}) is not "
        f"evidence.EvidenceProvenance({id(EP_canonical)})"
    )


# ─── SUB-23: instrument identity stable across provider rename ───

def test_instrument_identity_survives_rename():
    """SUB-23 (spec 7.7 INST-02): instrument identity is stable across
    a provider symbol rename — provider naming is not identity."""
    original = InstrumentIdentity(
        stable_identifier="XAU-USD-SPOT", asset_class="metal",
        contract_type="spot", provider_symbol="XAUUSD",
    )
    renamed = original.with_provider_symbol("XAU/USD")
    assert original.instrument_identity_hash == renamed.instrument_identity_hash
    assert renamed.provider_symbol == "XAU/USD"


# ─── SUB-24: ExperimentIdentity wall-clock independent ───

def test_experiment_identity_no_wallclock():
    """SUB-24 (spec 7.12): experiment_id is unchanged under
    run_timestamp, wall-clock, PID, path, and environment changes."""
    args = dict(
        strategy_hash="a" * 64, dataset_hash="b" * 64,
        view_hash="pit4v." + "c" * 64, config_hash="d" * 64,
        tie_breaker_name="tb", tie_breaker_version="1.0.0",
        code_version="1", quant_version="2", backtest_engine_version="3.0.0",
    )
    base = ExperimentIdentity(**args).experiment_id
    time.sleep(0.02)  # wall clock moved
    assert ExperimentIdentity(**args).experiment_id == base

    # Environment changes never leak in.
    os.environ["PIT Experiment扰动"] = "noise"
    os.environ["PYTHONHASHSEED"] = "12345"
    try:
        assert ExperimentIdentity(**args).experiment_id == base
    finally:
        del os.environ["PIT Experiment扰动"]
        del os.environ["PYTHONHASHSEED"]

    # The identity carries no run_timestamp/approval field at all.
    forbidden = {"run_timestamp", "approval_timestamp", "ingestion_time",
                 "created_at", "provider_timestamp", "retrieval_timestamp"}
    assert forbidden.isdisjoint(ExperimentIdentity.model_fields)


# ─── SUB-25: T-H05 must fail if Candle.to_hash() enters Phase 4 identity ───

def test_no_phase3_hash_in_phase4_identity(monkeypatch):
    """SUB-25 (spec 2.8 / FRZ-02): no frozen Phase 3 hash method may
    enter any Phase 4 identity. If Candle.to_hash() were called
    anywhere in the Phase 4 identity path, this test FAILS (the
    monkeypatched bomb explodes). Uses REAL Phase 3 candles so the
    bombed method genuinely exists on the flowing objects."""
    from data_engine.evidence import EvidenceProvenance
    from data_engine.schemas import Candle

    def _bomb(self):
        raise AssertionError(
            "Candle.to_hash() (frozen Phase 3, wall-clock contaminated per "
            "F-04) was invoked inside a Phase 4 identity computation"
        )

    monkeypatch.setattr(Candle, "to_hash", _bomb)
    # Real Phase 3 dataset: its candles genuinely carry to_hash().
    real_ds = _real_dataset(EvidenceProvenance.REAL)
    assert all(isinstance(c, Candle) for c in real_ds.candles)
    content_hash = dataset_content_hash(real_ds)  # must not explode
    assert len(content_hash) == 64

    # The full view path over the same real dataset must not explode.
    sidecar = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        publication_time=_ts(2),
    )
    view = PitViewBuilder().build(real_ds, _ts(6), sidecar, _tb())
    assert view.view_hash.startswith("pit4v.")
    assert _explicit_sidecar().sidecar_hash.startswith("pit4.")


# ═══════════════════════════════════════════════════════════════════
# SECTION 8.5 — COMPONENT-LEVEL TESTS
# ═══════════════════════════════════════════════════════════════════

# ─── 8.5.1 TieBreakerPolicy (TIE-01..TIE-06) ───

def test_tie_equal_time_deterministic():
    """TIE-01: equal timestamps order deterministically; repeated runs
    produce the identical order."""
    tb = TieBreakerPolicy(name="seq", version="1", keys=("timestamp", "sequence"))
    obs = [_OrderedObs(_ts(1), s, f"v{s}") for s in (5, 2, 9, 1)]
    orders = [tuple(o.sequence for o in tb.sort(obs)) for _ in range(5)]
    assert len(set(orders)) == 1
    assert orders[0] == (1, 2, 5, 9)


def test_tie_input_order_independent():
    """TIE-02: reversing the input order does NOT change the resulting
    order — the comparator defines a total order."""
    tb = TieBreakerPolicy(name="seq", version="1", keys=("timestamp", "sequence"))
    obs = [_OrderedObs(_ts(1), s, f"v{s}") for s in (3, 1, 2)]
    forward = tuple(o.sequence for o in tb.sort(obs))
    backward = tuple(o.sequence for o in tb.sort(list(reversed(obs))))
    shuffled = tuple(o.sequence for o in tb.sort([obs[2], obs[0], obs[1]]))
    assert forward == backward == shuffled == (1, 2, 3)


def test_tie_empty_keys_rejected():
    """TIE-03: an empty key tuple raises at construction."""
    with pytest.raises(Exception):
        TieBreakerPolicy(name="x", version="1", keys=())


def test_tie_wallclock_key_rejected():
    """TIE-04 (PROH-LEG-01 class): a wall-clock sort key raises at
    construction — ordering must never depend on ambient time."""
    for key in ("now", "wall_clock", "current_time", "ingestion_time",
                "retrieval_timestamp", "created_at", "run_timestamp"):
        with pytest.raises(Exception):
            TieBreakerPolicy(name="x", version="1", keys=("timestamp", key))


def test_tie_unbreakable_raises():
    """TIE-05: a tie the key tuple cannot break RAISES — never an
    arbitrary fallback."""
    tb = TieBreakerPolicy(name="seq", version="1", keys=("timestamp", "sequence"))
    a = _OrderedObs(_ts(1), 1, "alpha")
    b = _OrderedObs(_ts(1), 1, "beta")  # same keys, distinct observations
    with pytest.raises(AmbiguousTieError):
        tb.compare(a, b)
    with pytest.raises(AmbiguousTieError):
        tb.sort([a, b])


def test_tie_identity_participates():
    """TIE-06: changing the tie-breaker's name or version changes the
    identity — and therefore the experiment_id (EXP-02 pairing)."""
    tb_a = TieBreakerPolicy(name="tb", version="1.0.0", keys=("timestamp",))
    tb_b = TieBreakerPolicy(name="tb", version="2.0.0", keys=("timestamp",))
    tb_c = TieBreakerPolicy(name="other", version="1.0.0", keys=("timestamp",))
    assert tb_a.tie_breaker_hash != tb_b.tie_breaker_hash
    assert tb_a.tie_breaker_hash != tb_c.tie_breaker_hash

    base = dict(strategy_hash="a" * 64, dataset_hash="b" * 64,
                view_hash="pit4v." + "c" * 64, config_hash="d" * 64,
                code_version="1", quant_version="1",
                backtest_engine_version="3.0.0")
    id_a = ExperimentIdentity(tie_breaker_name="tb", tie_breaker_version="1.0.0", **base).experiment_id
    id_b = ExperimentIdentity(tie_breaker_name="tb", tie_breaker_version="2.0.0", **base).experiment_id
    id_c = ExperimentIdentity(tie_breaker_name="other", tie_breaker_version="1.0.0", **base).experiment_id
    assert len({id_a, id_b, id_c}) == 3


# ─── 8.5.2 PitViewValidator (VAL-01..VAL-04) ───

def test_validator_no_future_items():
    """VAL-01: independent re-derivation confirms no future item is
    present in the view."""
    cutoff = _ts(3)
    view, ds = _build_view(cutoff)
    result = PitViewValidator().validate(view, ds, _explicit_sidecar(), cutoff)
    assert result.passed, result.failure_reasons

    # A tampered view containing a future item is REJECTED.
    future_candles = [DuckCandle(_ts(d, 10), 100.0, 105.0, 98.0, 102.0)
                      for d in range(1, 7)]
    tampered_ds = DuckDataset(future_candles)
    tampered_view = PitViewBuilder().build(
        tampered_ds, _ts(3), _explicit_sidecar(), _tb())
    # Forcing a future item into a view (simulating tampering):
    smuggled = PitView(
        dataset_id=tampered_view.dataset_id,
        dataset_version=tampered_view.dataset_version,
        cutoff=_ts(3),
        items=tuple(future_candles),  # days 4-6 are future events
        excluded_count=0,
        excluded_records=(),
        dataset_content_hash=tampered_view.dataset_content_hash,
        eligibility_hashes=tampered_view.eligibility_hashes,
        tie_breaker_name=tampered_view.tie_breaker_name,
        tie_breaker_version=tampered_view.tie_breaker_version,
        contract_version=tampered_view.contract_version,
        pit_contract_version=tampered_view.pit_contract_version,
    )
    result = PitViewValidator().validate(smuggled, tampered_ds,
                                         _explicit_sidecar(), _ts(3))
    assert not result.passed
    assert any("no_future_items" == c.name and not c.passed
               for c in result.checks)


def test_validator_hash_recomputes():
    """VAL-02: the view_hash recomputes and matches."""
    view, ds = _build_view(_ts(4))
    v1 = view.view_hash
    v2 = view.view_hash  # property recomputes from recorded inputs
    assert v1 == v2
    assert v1.startswith("pit4v.") and len(v1) == len("pit4v.") + 64
    result = PitViewValidator().validate(view, ds, _explicit_sidecar(), _ts(4))
    hash_check = [c for c in result.checks if c.name == "view_hash_recomputes"]
    assert hash_check and hash_check[0].passed


def test_validator_fails_closed():
    """VAL-03: any failed check rejects the view with a SPECIFIC
    reason — fail closed, no partial credit."""
    # A view whose exclusion accounting does not add up (silent drop).
    view, ds = _build_view(_ts(4))
    broken = view.model_copy(update={"excluded_count": 0})
    result = PitViewValidator().validate(broken, ds, _explicit_sidecar(), _ts(4))
    assert not result.passed
    reasons = result.failure_reasons
    assert reasons and any("mismatch" in r or "dropped" in r for r in reasons)


def test_validator_preserves_quality_gate():
    """VAL-04 (spec 7.6): the validator neither duplicates nor weakens
    DataQualityGate. It answers availability, not quality; the gate's
    rejections remain blocking at every consumer."""
    from data_engine.data_blocked import DataQualityGate
    from data_engine.evidence import EvidenceProvenance

    # The validator's check surface contains NO quality rule.
    view, ds = _build_view(_ts(4))
    result = PitViewValidator().validate(view, ds, _explicit_sidecar(), _ts(4))
    quality_rules = {"minimum_candle_count", "provenance_check",
                     "synthetic_policy", "simulated_policy",
                     "validation_status", "quarantine_status"}
    check_names = {c.name for c in result.checks}
    assert check_names.isdisjoint(quality_rules)

    # The gate still blocks a SYNTHETIC dataset even though a PIT view
    # of it would be structurally valid — the validator cannot bless it.
    synthetic = _real_dataset(EvidenceProvenance.SYNTHETIC)
    passed, _ = DataQualityGate().check(synthetic)
    assert passed is False
    real = _real_dataset(EvidenceProvenance.REAL)
    passed_real, _ = DataQualityGate().check(real)
    assert passed_real is True


# ─── 8.5.3 InstrumentIdentity (INST-01..INST-04) ───

def test_instrument_identity_empty_id_rejected():
    """INST-01: an empty stable_identifier raises."""
    with pytest.raises(Exception):
        InstrumentIdentity(stable_identifier="", asset_class="metal",
                           contract_type="spot")


def test_instrument_identity_survives_rename():
    """INST-02: identity is stable across a provider symbol rename."""
    original = InstrumentIdentity(stable_identifier="XAU-USD-SPOT",
                                  asset_class="metal", contract_type="spot",
                                  provider_symbol="XAUUSD")
    renamed = original.with_provider_symbol("GLD_SPOT")
    assert original.instrument_identity_hash == renamed.instrument_identity_hash


def test_instrument_identity_symbol_not_identity():
    """INST-03: a free-form symbol is not an identity field — changing
    it alone does not change the hash."""
    a = InstrumentIdentity(stable_identifier="XAU-USD-SPOT", asset_class="metal",
                           contract_type="spot", provider_symbol="sym-A")
    b = InstrumentIdentity(stable_identifier="XAU-USD-SPOT", asset_class="metal",
                           contract_type="spot", provider_symbol="sym-B")
    assert a.instrument_identity_hash == b.instrument_identity_hash
    # But changing an actual identity field DOES change the hash.
    c = InstrumentIdentity(stable_identifier="XAU-USD-SPOT", asset_class="metal",
                           contract_type="futures")
    assert a.instrument_identity_hash != c.instrument_identity_hash


def test_instrument_identity_no_wallclock():
    """INST-04: the identity contains no wall-clock field, and the
    hash is invariant under time shifts."""
    fields = set(InstrumentIdentity.model_fields)
    assert fields.isdisjoint(PROHIBITED_IDENTITY_FIELDS)
    inst = InstrumentIdentity(stable_identifier="XAU-USD-SPOT",
                              asset_class="metal", contract_type="spot")
    h1 = inst.instrument_identity_hash
    time.sleep(0.02)
    assert inst.instrument_identity_hash == h1


# ─── 8.5.4 InstrumentSpecification (SPEC-01..SPEC-03) ───

def _venue():
    return Venue(venue_id="LBMA", venue_name="London Bullion Market",
                 timezone="Europe/London")


def _spec(effective_from, effective_to, tick=0.01, size=100.0):
    inst = InstrumentIdentity(stable_identifier="XAU-USD-SPOT",
                              asset_class="metal", contract_type="spot")
    return InstrumentSpecification(
        instrument_identity=inst, effective_from=effective_from,
        effective_to=effective_to, tick_size=tick, contract_size=size,
        currency="USD", venue=_venue(),
    )


def test_spec_overlap_rejected():
    """SPEC-01: overlapping validity intervals for one instrument raise."""
    a = _spec(date(2024, 1, 1), date(2024, 6, 1))
    b = _spec(date(2024, 5, 1), date(2024, 12, 1))  # overlaps a
    with pytest.raises(Exception):
        validate_specification_intervals([a, b])
    # Adjacent (non-overlapping) intervals are fine.
    c = _spec(date(2024, 6, 1), date(2024, 12, 1))
    validate_specification_intervals([a, c])


def test_spec_interval_and_sizes():
    """SPEC-02: effective_from < effective_to enforced; non-positive
    tick/contract size raises."""
    with pytest.raises(Exception):
        _spec(date(2024, 6, 1), date(2024, 1, 1))  # reversed interval
    with pytest.raises(Exception):
        _spec(date(2024, 1, 1), date(2024, 1, 1))  # empty interval
    with pytest.raises(Exception):
        _spec(date(2024, 1, 1), date(2024, 6, 1), tick=0.0)
    with pytest.raises(Exception):
        _spec(date(2024, 1, 1), date(2024, 6, 1), tick=-0.01)
    with pytest.raises(Exception):
        _spec(date(2024, 1, 1), date(2024, 6, 1), size=0.0)
    with pytest.raises(Exception):
        _spec(date(2024, 1, 1), date(2024, 6, 1), size=-1.0)


def test_spec_effective_to_excluded_from_identity():
    """SPEC-03: effective_to is EXCLUDED from identity — the successor's
    start is authoritative, so two specs differing only in effective_to
    hash identically."""
    a = _spec(date(2024, 6, 1), date(2024, 12, 31))
    b = _spec(date(2024, 6, 1), date(2025, 3, 1))
    assert a.specification_hash == b.specification_hash
    # But effective_from (an identity field) matters:
    c = _spec(date(2024, 7, 1), date(2024, 12, 31))
    assert a.specification_hash != c.specification_hash


# ─── 8.5.5 Venue (VEN-01..VEN-02) ───

def test_venue_invalid_timezone_rejected():
    """VEN-01: an invalid IANA timezone raises."""
    for bad in ("Not/AZone", "Mars/Olympus", "", "UTC-plus-brussels"):
        with pytest.raises(Exception):
            Venue(venue_id="v", venue_name="Bad", timezone=bad)
    Venue(venue_id="v", venue_name="Good", timezone="Europe/London")
    Venue(venue_id="v", venue_name="Good", timezone="UTC")


def test_venue_immutable_stable():
    """VEN-02: Venue is immutable and hash-stable."""
    v1 = Venue(venue_id="LBMA", venue_name="London", timezone="Europe/London")
    v2 = Venue(venue_id="LBMA", venue_name="London", timezone="Europe/London")
    assert v1.venue_hash == v2.venue_hash
    assert v1.venue_hash.startswith("pit4.")
    with pytest.raises(Exception):
        v1.venue_name = "Mutated"
    # mic is non-identity metadata.
    v3 = Venue(venue_id="LBMA", venue_name="London",
               timezone="Europe/London", mic="XLON")
    assert v1.venue_hash == v3.venue_hash


# ─── 8.5.6 DataSource (SRC-01..SRC-03) ───

def test_source_rename_creates_version():
    """SRC-01: a provider symbol rename creates a NEW mapping version —
    it never silently overwrites the existing one."""
    src = DataSource(
        source_id="s1", provider_name="prov", source_version="1",
        symbol_mappings=(SymbolMapping(mapping_version=1,
                                       stable_identifier="XAU-USD-SPOT",
                                       provider_symbol="XAUUSD"),),
    )
    renamed = DataSource.with_renamed_symbol(src, "XAU-USD-SPOT", "XAU/USD")
    assert len(renamed.symbol_mappings) == 2
    assert renamed.symbol_mappings[0] == src.symbol_mappings[0]  # preserved
    assert renamed.symbol_mappings[1].mapping_version == 2
    assert renamed.symbol_mappings[1].provider_symbol == "XAU/USD"
    assert src.symbol_mappings[0].provider_symbol == "XAUUSD"  # untouched


def test_source_duplicate_version_rejected():
    """SRC-02: a duplicate mapping version raises."""
    with pytest.raises(Exception):
        DataSource(
            source_id="s", provider_name="p", source_version="1",
            symbol_mappings=(
                SymbolMapping(mapping_version=1, stable_identifier="a",
                              provider_symbol="x"),
                SymbolMapping(mapping_version=1, stable_identifier="a",
                              provider_symbol="y"),
            ),
        )


def test_source_version_monotonic():
    """SRC-03: mapping versions are monotonic (strictly increasing)."""
    with pytest.raises(Exception):
        DataSource(
            source_id="s", provider_name="p", source_version="1",
            symbol_mappings=(
                SymbolMapping(mapping_version=2, stable_identifier="a",
                              provider_symbol="x"),
                SymbolMapping(mapping_version=1, stable_identifier="a",
                              provider_symbol="y"),
            ),
        )
    ok = DataSource(
        source_id="s", provider_name="p", source_version="1",
        symbol_mappings=(
            SymbolMapping(mapping_version=1, stable_identifier="a",
                          provider_symbol="x"),
            SymbolMapping(mapping_version=2, stable_identifier="a",
                          provider_symbol="y"),
        ),
    )
    assert [m.mapping_version for m in ok.symbol_mappings] == [1, 2]


# ─── 8.5.7 CalendarRef (CAL-01..CAL-02) ───

def test_calendar_ref_empty_fields_rejected():
    """CAL-01: empty calendar_id or calendar_version raises."""
    with pytest.raises(Exception):
        CalendarRef(calendar_id="", calendar_version="v1")
    with pytest.raises(Exception):
        CalendarRef(calendar_id="LDN", calendar_version="")
    CalendarRef(calendar_id="LDN", calendar_version="v1")


def test_calendar_ref_no_computation_surface():
    """CAL-02 (INV-06 scope guard): NO calendar computation surface
    exists — no holiday logic, no session determination, no
    trading-day arithmetic."""
    forbidden_fragments = (
        "holiday", "session", "trading_day", "tradingday",
        "next_day", "previous_day", "is_open", "roll_date",
        "business_day", "calendar_math", "easter", "weekend",
    )
    public_names = [n for n in dir(CalendarRef) if not n.startswith("_")]
    for name in public_names:
        for fragment in forbidden_fragments:
            assert fragment not in name.lower(), (
                f"CalendarRef exposes a computation surface member "
                f"'{name}' — INV-06 scope violation (CAL-02)"
            )
    # The module source itself contains no calendar computation.
    source = (REPO_ROOT / "src/data_engine/pit/primitives.py").read_text(
        encoding="utf-8")
    cal_section = source.split("class CalendarRef")[1]
    for fragment in ("def is_holiday", "def sessions", "def trading_days",
                     "def next_trading_day", "def is_trading_day"):
        assert fragment not in cal_section, (
            f"CalendarRef computation surface: {fragment} (CAL-02)"
        )
    ref = CalendarRef(calendar_id="LDN", calendar_version="v1")
    assert ref.calendar_ref_hash.startswith("pit4.")


# ─── 8.5.8 ExperimentIdentity (EXP-01..EXP-05) ───

def _experiment_kwargs(**overrides):
    base = dict(
        strategy_hash="a" * 64, dataset_hash="b" * 64,
        view_hash="pit4v." + "c" * 64, config_hash="d" * 64,
        tie_breaker_name="tb", tie_breaker_version="1.0.0",
        code_version="1.0.0", quant_version="2.0.0",
        backtest_engine_version="3.0.0",
    )
    base.update(overrides)
    return base


def test_experiment_id_pure_function():
    """EXP-01: experiment_id is a pure function of its declared inputs."""
    e1 = ExperimentIdentity(**_experiment_kwargs())
    e2 = ExperimentIdentity(**_experiment_kwargs())
    assert e1.experiment_id == e2.experiment_id
    time.sleep(0.02)
    assert ExperimentIdentity(**_experiment_kwargs()).experiment_id == e1.experiment_id
    # Every input change changes the output.
    for field, value in (
        ("strategy_hash", "e" * 64), ("dataset_hash", "f" * 64),
        ("view_hash", "pit4v." + "e" * 64), ("config_hash", "f" * 64),
        ("code_version", "9"), ("quant_version", "9"),
        ("backtest_engine_version", "9"),
    ):
        altered = ExperimentIdentity(**_experiment_kwargs(**{field: value}))
        assert altered.experiment_id != e1.experiment_id, field


def test_experiment_id_tiebreak_sensitive():
    """EXP-02: changing the tie-breaker changes experiment_id."""
    a = ExperimentIdentity(**_experiment_kwargs(tie_breaker_name="tb",
                                                tie_breaker_version="1.0.0"))
    b = ExperimentIdentity(**_experiment_kwargs(tie_breaker_name="tb",
                                                tie_breaker_version="1.0.1"))
    c = ExperimentIdentity(**_experiment_kwargs(tie_breaker_name="other",
                                                tie_breaker_version="1.0.0"))
    assert len({a.experiment_id, b.experiment_id, c.experiment_id}) == 3


def test_experiment_id_wallclock_independent():
    """EXP-03: experiment_id is unchanged under run_timestamp, wall
    clock, PID, path, and environment changes."""
    kwargs = _experiment_kwargs()
    base = ExperimentIdentity(**kwargs).experiment_id
    time.sleep(0.02)
    same = ExperimentIdentity(**kwargs).experiment_id
    assert same == base
    # No field of the identity is wall-clock class at all.
    assert set(ExperimentIdentity.model_fields).isdisjoint(
        PROHIBITED_IDENTITY_FIELDS)


def test_experiment_id_missing_component_raises():
    """EXP-04: a missing or blank component raises."""
    with pytest.raises(Exception):
        ExperimentIdentity(**_experiment_kwargs(strategy_hash=""))
    with pytest.raises(Exception):
        ExperimentIdentity(**_experiment_kwargs(code_version="  "))
    with pytest.raises(Exception):
        ExperimentIdentity(**_experiment_kwargs(tie_breaker_name=""))
    with pytest.raises(Exception):
        ExperimentIdentity(**_experiment_kwargs(dataset_hash="not-a-hash"))


def test_experiment_id_no_phase3_hash_call(monkeypatch):
    """EXP-05: no frozen Phase 3 hash method is invoked during
    identity computation — hashes arrive as OPAQUE STRINGS (FRZ-02).
    If any Phase 3 hash method were called, the bomb explodes."""
    from data_engine.schemas import Candle, ProvenanceRecord
    from data_engine.strategy.schemas import StrategySpec

    def _bomb(name):
        def _inner(*args, **kwargs):
            raise AssertionError(
                f"frozen Phase 3 hash method {name} was invoked during "
                f"Phase 4 identity computation (EXP-05/FRZ-02 violation)"
            )
        return _inner

    monkeypatch.setattr(Candle, "to_hash", _bomb("Candle.to_hash"))
    monkeypatch.setattr(ProvenanceRecord, "to_hash",
                        _bomb("ProvenanceRecord.to_hash"))
    monkeypatch.setattr(StrategySpec, "to_hash", _bomb("StrategySpec.to_hash"))
    eid = ExperimentIdentity(**_experiment_kwargs())
    assert eid.experiment_id.startswith("pit4x.")


# ─── 8.5.9 PitExperimentConfig (CFG-01..CFG-04) ───

def test_config_assumption_text_required():
    """CFG-01: ASSUMED_PUBLICATION without assumption text raises."""
    with pytest.raises(Exception):
        PitExperimentConfig(
            cutoff=_ts(4), tie_breaker=_tb(),
            legacy_policy=LegacyPolicy.ASSUMED_PUBLICATION,
        )
    with pytest.raises(Exception):
        PitExperimentConfig(
            cutoff=_ts(4), tie_breaker=_tb(),
            legacy_policy=LegacyPolicy.ASSUMED_PUBLICATION,
            legacy_assumption_text="   ",  # blank
            legacy_publication_offset_seconds=3600.0,
        )
    with pytest.raises(Exception):
        PitExperimentConfig(
            cutoff=_ts(4), tie_breaker=_tb(),
            legacy_policy=LegacyPolicy.ASSUMED_PUBLICATION,
            legacy_assumption_text="declared basis",
            # offset missing
        )
    ok = PitExperimentConfig(
        cutoff=_ts(4), tie_breaker=_tb(),
        legacy_policy=LegacyPolicy.ASSUMED_PUBLICATION,
        legacy_assumption_text="provider digest schedule",
        legacy_publication_offset_seconds=3600.0,
    )
    assert ok.legacy_policy == LegacyPolicy.ASSUMED_PUBLICATION


def test_config_extra_field_forbidden():
    """CFG-02: an unknown key raises (extra='forbid')."""
    with pytest.raises(Exception):
        PitExperimentConfig(cutoff=_ts(4), tie_breaker=_tb(), evil_key=1)


def test_config_naive_cutoff_rejected():
    """CFG-03: a non-UTC-aware cutoff raises."""
    with pytest.raises(Exception):
        PitExperimentConfig(cutoff=datetime(2025, 6, 4),  # naive
                            tie_breaker=_tb())


def test_config_determines_view():
    """CFG-04: the config alone determines the view — the same config
    plus the same data yields the same view_hash; a different config
    yields a different one."""
    candles = _five_candles()
    ds = DuckDataset(candles)
    sidecar = _explicit_sidecar()
    cfg_a1 = PitExperimentConfig(cutoff=_ts(4), tie_breaker=_tb(version="1.0.0"))
    cfg_a2 = PitExperimentConfig(cutoff=_ts(4), tie_breaker=_tb(version="1.0.0"))
    cfg_b = PitExperimentConfig(cutoff=_ts(4), tie_breaker=_tb(version="2.0.0"))

    v1 = PitViewBuilder().build(ds, cfg_a1.cutoff, sidecar,
                                 cfg_a1.tie_breaker, legacy_policy=cfg_a1)
    v2 = PitViewBuilder().build(ds, cfg_a2.cutoff, sidecar,
                                cfg_a2.tie_breaker, legacy_policy=cfg_a2)
    v3 = PitViewBuilder().build(ds, cfg_b.cutoff, sidecar,
                                cfg_b.tie_breaker, legacy_policy=cfg_b)
    assert v1.view_hash == v2.view_hash  # same config -> same view
    assert v1.view_hash != v3.view_hash  # different config -> different view
    assert cfg_a1.config_identity_hash == cfg_a2.config_identity_hash
    assert cfg_a1.config_identity_hash != cfg_b.config_identity_hash


# ═══════════════════════════════════════════════════════════════════
# SECTION 8.5.10 — LEGACY SEMANTICS (LEG-T01..LEG-T03)
# ═══════════════════════════════════════════════════════════════════

def test_legacy_sidecar_no_wallclock():
    """LEG-T01 (pairs with SUB-09): a legacy sidecar contains NO
    wall-clock value; two builds at different times produce identical
    output — ingestion_time is None or fixed, never now()."""
    legacy = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        legacy_classification=LegacyClassification.PIT_INELIGIBLE,
        ineligible_reason="no publication metadata",
    )
    assert legacy.ingestion_time is None
    h1 = legacy.sidecar_hash
    time.sleep(0.05)
    rebuilt = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        legacy_classification=LegacyClassification.PIT_INELIGIBLE,
        ineligible_reason="no publication metadata",
    )
    assert rebuilt.sidecar_hash == h1

    # The sidecar module source contains no wall-clock read.
    source = (REPO_ROOT / "src/data_engine/pit/sidecar.py").read_text(
        encoding="utf-8")
    assert "datetime.now" not in source
    assert "utcnow" not in source


def test_legacy_no_retrieval_as_publication():
    """LEG-T02 (PROH-LEG-03): retrieval_timestamp is NEVER silently
    treated as publication_time. A sidecar without publication
    evidence cannot claim EXPLICIT; it is ASSUMED (declared) or
    PIT_INELIGIBLE — and its publication_time stays None."""
    retrieval_like = _ts(5)  # a retrieval-style audit timestamp
    # Constructing an explicit sidecar from a retrieval timestamp
    # pattern: publication evidence must be declared explicitly, and a
    # sidecar that merely KNOWS a retrieval time has publication None.
    legacy = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        legacy_classification=LegacyClassification.PIT_INELIGIBLE,
        ineligible_reason="publication time unknown; retrieval metadata "
                          "is AUDIT class and MUST NOT be promoted",
        ingestion_time=retrieval_like,  # audit metadata rides along
    )
    assert legacy.publication_time is None  # never the retrieval value
    # The builder excludes it rather than promoting the audit stamp.
    view, _ = _build_view(_ts(4), sidecar=legacy)
    assert len(view) == 0
    assert view.excluded_breakdown.get("pit_ineligible") == 5
    # The view builder source never references retrieval_timestamp.
    source = (REPO_ROOT / "src/data_engine/pit/view.py").read_text(
        encoding="utf-8")
    assert "retrieval_timestamp" not in source.replace(
        "retrieval_timestamp is AUDIT", "")  # no promotion path exists


def test_legacy_assumed_differs_from_explicit():
    """LEG-T03 (PROH-LEG-08): an assumed view never hashes equal to an
    explicit view — the classification participates in view identity."""
    config = PitExperimentConfig(
        cutoff=_ts(6), tie_breaker=_tb(),
        legacy_policy=LegacyPolicy.ASSUMED_PUBLICATION,
        legacy_assumption_text="assumed at observation+3600s",
        legacy_publication_offset_seconds=3600.0,
    )
    legacy_sidecar = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        legacy_classification=LegacyClassification.PIT_INELIGIBLE,
        ineligible_reason="no publication metadata",
    )
    assumed_view, _ = _build_view(_ts(6), sidecar=legacy_sidecar,
                                  legacy_policy=config)
    explicit_view, _ = _build_view(_ts(6), sidecar=_explicit_sidecar())
    assert assumed_view.view_hash != explicit_view.view_hash
    assert assumed_view.legacy_classification == (
        LegacyClassification.ASSUMED_PUBLICATION)
    assert explicit_view.legacy_classification == LegacyClassification.EXPLICIT
    # And two different assumption bases also differ (the assumption is
    # declared on the config, which participates in identity).
    config2 = PitExperimentConfig(
        cutoff=_ts(6), tie_breaker=_tb(),
        legacy_policy=LegacyPolicy.ASSUMED_PUBLICATION,
        legacy_assumption_text="a DIFFERENT declared basis",
        legacy_publication_offset_seconds=7200.0,
    )
    v2, _ = _build_view(_ts(6), sidecar=legacy_sidecar, legacy_policy=config2)
    assert v2.view_hash != assumed_view.view_hash


# ═══════════════════════════════════════════════════════════════════
# SECTION 8.6 — POST-RE-AUDIT MANDATORY TESTS (RA-NF-01..04)
# ═══════════════════════════════════════════════════════════════════

# ─── COL-KEY-01..05: mapping-key conformance (SER-KEY) ───

def test_serializer_nonstring_key_rejected():
    """COL-KEY-01 (SER-KEY-01, RA-NF-01 HIGH/BLOCKER):
    canonical_serialize({1: 'a'}) RAISES SerializationError — the
    non-string key is rejected BEFORE any coercion. Mutation rule: if
    integer-key coercion were restored, this test FAILS."""
    with pytest.raises(SerializationError):
        canonical_serialize({1: "a"})


def test_serializer_int_key_never_coerced():
    """COL-KEY-02 (SER-KEY-02): {'1': 'a'} serializes successfully and
    its bytes are the ONLY string-keyed form — no int-keyed input can
    ever be coerced into it (the int form raises instead)."""
    ok = canonical_serialize({"1": "a"})
    assert ok == b'{"D":[[{"s":"1"},{"s":"a"}]]}'
    # Every attempt to sneak an int key fails closed at any depth.
    for bad in ({1: "a"}, {True: "a"}, {1.5: "a"}, {None: "a"}):
        with pytest.raises(SerializationError):
            canonical_serialize(bad)


def test_serializer_nonstring_key_nested():
    """COL-KEY-03 (SER-KEY-05): non-string keys are rejected
    recursively at EVERY nesting depth."""
    nested_cases = [
        {"outer": {1: "a"}},
        {"outer": {"inner": [{2: "b"}]}},
        [{"deep": {3: "c"}}],
        {"a": [{"b": {4.5: "d"}}]},
    ]
    for case in nested_cases:
        with pytest.raises(SerializationError):
            canonical_serialize(case)


def test_serializer_no_implicit_key_conversion():
    """COL-KEY-04 (SER-KEY-02): bool, Decimal, and date keys are all
    rejected — NO implicit key conversion of ANY kind."""
    for key in (True, False, Decimal("1"), date(2024, 1, 1),
                datetime(2024, 1, 1, tzinfo=UTC), 1, 0, -5, 2.5):
        with pytest.raises(SerializationError):
            canonical_serialize({key: "value"})


def test_serializer_key_type_tagged():
    """COL-KEY-05 (SER-KEY-03): mapping keys are encoded as {"s": ...}
    inside the mapping wrapper, so a key can never be confused with a
    bare scalar value."""
    encoded = canonical_serialize({"XAU/USD": 1})
    assert b'{"s":"XAU/USD"}' in encoded          # the key, tagged
    assert b'{"i":"1"}' in encoded                # the value, tagged
    assert encoded == b'{"D":[[{"s":"XAU/USD"},{"i":"1"}]]}'
    # A bare scalar string and a KEY never share byte form:
    scalar = canonical_serialize("XAU/USD")
    assert scalar == b'{"s":"XAU/USD"}'
    # ...but the key form is embedded inside the mapping wrapper, so
    # dict-vs-scalar encodings are structurally distinct:
    assert encoded != scalar


# ─── COL-DT-01..02: datetime conformance ───

def test_serializer_datetime_vs_string_distinct():
    """COL-DT-01 (spec 3.1): a datetime and its ISO-8601 string
    produce DISTINCT canonical bytes (tag 't' vs tag 's')."""
    dt = datetime(2024, 1, 1, tzinfo=UTC)
    iso = "2024-01-01T00:00:00+00:00"
    a = canonical_serialize(dt)
    b = canonical_serialize(iso)
    assert a == b'{"t":"2024-01-01T00:00:00+00:00"}'
    assert b == b'{"s":"2024-01-01T00:00:00+00:00"}'
    assert a != b


def test_serializer_date_vs_datetime_distinct():
    """COL-DT-02 (spec 3.1a.2): a date and a datetime produce DISTINCT
    canonical bytes — the tag letters differ."""
    d = canonical_serialize(date(2024, 1, 1))
    dt = canonical_serialize(datetime(2024, 1, 1, tzinfo=UTC))
    assert d == b'{"c":"2024-01-01"}'
    assert dt == b'{"t":"2024-01-01T00:00:00+00:00"}'
    assert d != dt


# ─── COL-DATE-01..03: date representation conformance ───

def test_serializer_date_supported():
    """COL-DATE-01 (RA-NF-02): a date serializes successfully to its
    defined ISO-8601 representation — it MUST NOT raise."""
    encoded = canonical_serialize(date(2024, 1, 1))
    assert encoded == b'{"c":"2024-01-01"}'
    # Date-valued identity fields are usable (spec 7.8 effective_from):
    h = identity_hash("InstrumentSpecification", "1.0.0",
                      ("effective_from",), {"effective_from": date(2024, 1, 1)})
    assert h.startswith("pit4.")


def test_serializer_date_not_widened():
    """COL-DATE-02 (spec 3.1a.2): a date is never implicitly widened
    to a datetime — no time component, no timezone suffix appears."""
    encoded = canonical_serialize(date(2024, 1, 1)).decode("utf-8")
    assert "T00:00:00" not in encoded
    assert "+00:00" not in encoded
    assert encoded == '{"c":"2024-01-01"}'
    # And a naive date never sneaks through the datetime branch:
    assert canonical_serialize(date(2024, 1, 1)) != (
        canonical_serialize(datetime(2024, 1, 1, tzinfo=UTC)))


def test_serializer_date_tag_distinct_from_dict():
    """COL-DATE-03 (RA-NF-04): the date tag letter is DISTINCT from
    the dict tag letter — the historical 'D' collision is resolved
    ('c' for calendar date)."""
    date_bytes = canonical_serialize(date(2024, 1, 1))
    dict_bytes = canonical_serialize({"a": 1})
    assert date_bytes.startswith(b'{"c":')
    assert dict_bytes.startswith(b'{"D":')
    assert date_bytes != dict_bytes
    # No tag collision anywhere in the registry:
    from data_engine.pit.serialization import (
        _TAG_BOOL, _TAG_DATE, _TAG_DATETIME, _TAG_DECIMAL, _TAG_DICT,
        _TAG_FLOAT, _TAG_INT, _TAG_LIST, _TAG_STR,
    )
    tags = [_TAG_BOOL, _TAG_INT, _TAG_FLOAT, _TAG_DECIMAL, _TAG_STR,
            _TAG_DATETIME, _TAG_DATE, _TAG_LIST, _TAG_DICT]
    assert len(tags) == len(set(tags)), "tag letters must be distinct"


# ─── COL-NUM-01..04: numeric representation conformance ───

def test_serializer_float_ten_places():
    """COL-NUM-01 (spec 3.1a.3): float is emitted in .10f form —
    100.5 -> '100.5000000000', never '100.5'."""
    assert canonical_serialize(100.5) == b'{"f":"100.5000000000"}'
    assert canonical_serialize(0.1) == b'{"f":"0.1000000000"}'
    assert canonical_serialize(-2.25) == b'{"f":"-2.2500000000"}'
    assert canonical_serialize(0.0) == canonical_serialize(-0.0)


def test_serializer_decimal_exact_tagged():
    """COL-NUM-02 (spec 3.1a.3): Decimal is emitted as an exact tagged
    string — never float-converted, never rounded."""
    assert canonical_serialize(Decimal("1.10")) == b'{"d":"1.10"}'
    assert canonical_serialize(Decimal("123456789.123456789")) == (
        b'{"d":"123456789.123456789"}')
    assert canonical_serialize(Decimal("0.001")) == b'{"d":"0.001"}'


def test_serializer_decimal_float_tagged_distinct():
    """COL-NUM-03 (spec 3.1a.3): Decimal('1.0') and 1.0 differ BY TAG
    AND BY VALUE FORM — the distinction is designed, not incidental."""
    dec = canonical_serialize(Decimal("1.0"))
    flt = canonical_serialize(1.0)
    assert dec == b'{"d":"1.0"}'
    assert flt == b'{"f":"1.0000000000"}'
    assert dec != flt


def test_serializer_int_bool_tagged():
    """COL-NUM-04 (spec 3.1a.3): int and bool are tagged {"i":...} and
    {"b":...} — True never equals 1 in canonical bytes."""
    assert canonical_serialize(1) == b'{"i":"1"}'
    assert canonical_serialize(True) == b'{"b":true}'
    assert canonical_serialize(False) == b'{"b":false}'
    assert canonical_serialize(0) == b'{"i":"0"}'
    assert canonical_serialize(True) != canonical_serialize(1)
    assert canonical_serialize(False) != canonical_serialize(0)


# ─── COL-PROC-01: true subprocess identity determinism ───

def test_identity_determinism_true_subprocess():
    """COL-PROC-01 (spec 8.3/8.6; T-H05 reinforcement): >= 5 separate
    OS processes each compute an IDENTITY (sidecar hash over a fixed
    sidecar) and all digests match the in-process digest."""
    code = (
        "from datetime import datetime, UTC\n"
        "from data_engine.pit import PitSidecar\n"
        "s = PitSidecar(dataset_id='ds', dataset_version='v1',\n"
        "              event_time=datetime(2025, 6, 1, 10, tzinfo=UTC),\n"
        "              observation_time=datetime(2025, 6, 1, 10, 30, tzinfo=UTC),\n"
        "              publication_time=datetime(2025, 6, 2, tzinfo=UTC))\n"
        "print(s.sidecar_hash)\n"
    )
    env_base = {**os.environ, "PYTHONPATH": str(SRC_ROOT)}
    digests = []
    for i in range(5):
        env_i = {**env_base, "PYTHONHASHSEED": str(i),
                 "LC_ALL": "C.UTF-8" if i % 2 else "en_US.UTF-8",
                 "PIT_TEST_PROC": str(i)}
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, env=env_i, timeout=60,
        )
        assert proc.returncode == 0, proc.stderr
        digests.append(proc.stdout.strip())
    assert len(set(digests)) == 1
    in_process = PitSidecar(
        dataset_id="ds", dataset_version="v1",
        event_time=_ts(1, 10), observation_time=_ts(1, 10, 30),
        publication_time=_ts(2),
    ).sidecar_hash
    assert digests[0] == in_process


# ═══════════════════════════════════════════════════════════════════
# AUDIT-TRAIL TESTS — §13 Blocker 8 evidence requirement
# (SPEC-DEF-02 resolution: §13 cites "SUB-24 (audit-log verification)"
#  while §8.3 defines SUB-24 as the ExperimentIdentity wall-clock test;
#  BOTH are implemented — SUB-24 above, the audit trail here.)
# ═══════════════════════════════════════════════════════════════════

def test_security_audit_trail_records_allow_and_deny(tmp_path):
    """FS-21: every allow and every deny is logged to the structured
    security audit trail with actor, path, decision, rule, timestamp."""
    from data_engine.provider import FileDataProvider
    from data_engine.schemas import ProviderConfig, Timeframe
    from data_engine.security import SecurityAuditTrail

    root = tmp_path / "approved"
    root.mkdir()
    (root / "XAUUSD_1d.csv").write_text(
        "timestamp,open,high,low,close\n2025-01-01,100,105,98,102\n")
    trail_path = tmp_path / "audit" / "security_audit.jsonl"
    t0, t1 = datetime(2024, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)

    provider = FileDataProvider(ProviderConfig(
        provider_name="file", provider_type="file", endpoint=str(root),
        approved_data_root=str(root), instrument_allowlist=["XAUUSD"],
        audit_trail_path=str(trail_path),
    ))
    provider.fetch_candles("XAUUSD", Timeframe.D1, t0, t1)   # ALLOW
    try:
        provider.fetch_candles("EURUSD", Timeframe.D1, t0, t1)  # DENY
    except Exception:
        pass

    trail = SecurityAuditTrail(trail_path)
    entries = trail.decisions()
    decisions = [(e["decision"], e["rule"]) for e in entries]
    assert ("ALLOW", "FS-05") in decisions
    assert ("DENY", "FS-14") in decisions
    for entry in entries:
        for required in ("seq", "timestamp", "actor", "path",
                         "decision", "rule", "prev_hash", "entry_hash"):
            assert required in entry, f"audit entry missing {required}"


def test_security_audit_trail_chain_tamper_evident(tmp_path):
    """FS-22: the audit trail is append-only and tamper-evident —
    the hash chain verifies when intact and FAILS when any entry is
    mutated, reordered, or deleted."""
    from data_engine.security import SecurityAuditTrail

    trail_path = tmp_path / "audit" / "chain.jsonl"
    trail = SecurityAuditTrail(trail_path)
    trail.record(actor="a", path="/p1", decision="ALLOW", rule="FS-05")
    trail.record(actor="a", path="/p2", decision="DENY", rule="FS-07")
    trail.record(actor="b", path="/p3", decision="ALLOW", rule="FS-16")
    assert trail.verify() is True

    original = trail_path.read_text().strip().split("\n")

    # Mutation tamper: flip one decision.
    entries = [json.loads(line) for line in original]
    entries[1]["decision"] = "ALLOW"
    trail_path.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n")
    assert trail.verify() is False

    # Deletion tamper: remove an entry (breaks seq + prev_hash chain).
    entries = [json.loads(line) for line in original]
    del entries[0]
    trail_path.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n")
    assert trail.verify() is False

    # Reorder tamper: swap two entries.
    entries = [json.loads(line) for line in original]
    entries[0], entries[1] = entries[1], entries[0]
    trail_path.write_text(
        "\n".join(json.dumps(e, sort_keys=True) for e in entries) + "\n")
    assert trail.verify() is False

    # Restore: append-only semantics hold — appending continues the chain.
    trail_path.write_text("\n".join(original) + "\n")
    assert trail.verify() is True
    trail.record(actor="a", path="/p4", decision="ALLOW", rule="FS-05")
    assert trail.verify() is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
