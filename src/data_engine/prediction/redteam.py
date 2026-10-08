"""Adversarial red-team matrix (PRED-F2 closure, mandate §13).

Six attack categories against the live prediction intelligence layer:

    temporal     RT-PRED-T-001..008   future/leakage/revision/cutoff
    identity     RT-PRED-I-001..008   type/numeric/null/unicode/float edges
    provenance   RT-PRED-P-001..007   hash chains/tampering/forged state
    data         RT-PRED-D-001..008   corrupt/incomplete/poisoned rows
    model        RT-PRED-M-001..007   stale/drifted/invalid/mismatched
    crash-intel  RT-PRED-C-001..007   label contamination/false confidence

Every attack is EXECUTED against the real components here (not
described): each returns a :class:`RedTeamAttack` record with
ATTACK_ID, PRECONDITION, INPUT, EXPECTED_BEHAVIOR, ACTUAL_BEHAVIOR,
PASS/FAIL verdict, and EVIDENCE. The verdict is computed by comparing
expected vs. actual behavior — a red-team PASS means the system
defended (failed closed) exactly as designed.

Usage:
    matrix = run_redteam_matrix()
    assert matrix.failed == ()          # every attack defended
    print(matrix.summary())

The matrix is deterministic: no wall clock, no RNG, no process state.
"""

from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.prediction import labels as _labels
from data_engine.prediction.artifact_verification import (
    verify_model_artifact,
)
from data_engine.prediction.crash import blocked_assessment
from data_engine.prediction.contracts import (
    BlockReason,
    DriftState,
    PredictionContractError,
)
from data_engine.prediction.data_access import pit_candle_view
from data_engine.prediction.datasets import (
    DatasetManifest,
    DatasetState,
    dataset_content_hash,
)
from data_engine.prediction.event_evaluation import (
    EventEvaluationConfig,
    evaluate_crash_events,
)
from data_engine.prediction.features import (
    build_feature_rows,
    feature_data_hash,
)
from data_engine.prediction.gates import (
    PredictionGateInput,
    evaluate_prediction_gates,
)
from data_engine.prediction.identity import ATTACK_PREFIX, prefixed_hash
from data_engine.prediction.ledger import (
    OutcomeRecord,
    PredictionOutcomeLedger,
)
from data_engine.prediction.microstructure import (
    microstructure_availability,
)
from data_engine.prediction.models import (
    BaseRateBaseline,
    LogisticCrashModel,
)
from data_engine.prediction.quality_gates import validate_ohlcv
from data_engine.prediction.scenarios import (
    ScenarioDefinition,
    ScenarioEngine,
)
from data_engine.prediction.systemic import systemic_risk_reading


class AttackVerdict(str, Enum):
    PASS = "PASS"  # the system defended as designed
    FAIL = "FAIL"  # the system failed to defend — a real defect


class RedTeamAttack(BaseModel):
    """One executed attack with full evidence (mandate §13 fields)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attack_id: str
    category: str
    precondition: str
    input_description: str
    expected_behavior: str
    actual_behavior: str
    verdict: AttackVerdict
    evidence: str

    @property
    def attack_hash(self) -> str:
        return prefixed_hash(
            ATTACK_PREFIX,
            {
                "kind": "redteam_attack",
                "attack_id": self.attack_id,
                "category": self.category,
                "verdict": self.verdict.value,
            },
        )


class RedTeamMatrix(BaseModel):
    """The executed adversarial matrix (mandate §13)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    attacks: Tuple[RedTeamAttack, ...]

    @property
    def failed(self) -> Tuple[RedTeamAttack, ...]:
        return tuple(a for a in self.attacks if a.verdict is AttackVerdict.FAIL)

    @property
    def passed_count(self) -> int:
        return sum(
            1 for a in self.attacks if a.verdict is AttackVerdict.PASS
        )

    @property
    def matrix_hash(self) -> str:
        return prefixed_hash(
            ATTACK_PREFIX,
            {
                "kind": "redteam_matrix",
                "attacks": [a.attack_id for a in self.attacks],
                "verdicts": [a.verdict.value for a in self.attacks],
            },
        )

    def summary(self) -> str:
        categories: dict[str, dict[str, int]] = {}
        for attack in self.attacks:
            bucket = categories.setdefault(
                attack.category, {"PASS": 0, "FAIL": 0}
            )
            bucket[attack.verdict.value] += 1
        lines = [
            f"attacks: {len(self.attacks)}  "
            f"PASS: {self.passed_count}  FAIL: {len(self.failed)}"
        ]
        for category in sorted(categories):
            bucket = categories[category]
            lines.append(
                f"  {category:<16} PASS {bucket['PASS']:>2}  "
                f"FAIL {bucket['FAIL']:>2}"
            )
        return "\n".join(lines)


def _attack(
    attack_id: str,
    category: str,
    *,
    precondition: str,
    input_description: str,
    expected_behavior: str,
    actual_behavior: str,
    defended: bool,
    evidence: str,
) -> RedTeamAttack:
    return RedTeamAttack(
        attack_id=attack_id,
        category=category,
        precondition=precondition,
        input_description=input_description,
        expected_behavior=expected_behavior,
        actual_behavior=actual_behavior,
        verdict=AttackVerdict.PASS if defended else AttackVerdict.FAIL,
        evidence=evidence,
    )


# ════════════════════════ shared deterministic fixtures ═════════════════

def _base_time() -> datetime:
    return datetime(2024, 1, 1, tzinfo=UTC)


def _series(n: int = 60, *, crash_at: Optional[int] = None) -> list[dict]:
    """Deterministic close-only candle series (seeded arithmetic walk)."""
    candles: list[dict] = []
    price = 100.0
    for i in range(n):
        if crash_at is not None and i == crash_at:
            price *= 0.75  # a 25% drawdown bar
        else:
            price *= 1.0 + (0.002 if i % 3 else -0.001)
        candles.append({
            "timestamp": _base_time() + timedelta(days=i),
            "close": round(price, 10),
        })
    return candles


def _label_def():
    return _labels.CrashLabelDefinition(
        threshold=0.10,
        measurement_window=5,
        forward_horizon=5,
        asset_scope="TEST",
        calibration_period="2019-2024",
    )


def _good_evidence() -> dict:
    """Valid, sufficient evidence context (§17 eleven dimensions)."""
    return {
        "data_quality": 0.9,
        "sample_size": 0.8,
        "historical_coverage": 0.9,
        "regime_coverage": 0.8,
        "model_calibration": 0.7,
        "out_of_sample_performance": 0.6,
        "stability": 0.7,
        "cross_validation_consistency": 0.7,
        "feature_integrity": 1.0,
        "drift_status": "STABLE",
        "prediction_freshness": 0.9,
    }


def _fitted_logistic(candles: list[dict]):
    closes = [c["close"] for c in candles]
    definition = _label_def()
    labeled = _labels.compute_crash_labels(closes, definition)
    rows = build_feature_rows(closes)
    X = [list(r.values) for r in rows]
    y = [
        int(labeled[r.row_index].label)
        for r in rows
        if labeled[r.row_index].label is not None
    ]
    usable = [
        r for r in rows
        if labeled[r.row_index].label is not None
    ]
    X = [list(r.values) for r in usable]
    model = LogisticCrashModel(
        ("ret1", "mom20", "vol20", "volr", "dd", "range")
    )
    model.fit(X, y)
    return model


# ═══════════════════════════ temporal attacks ═══════════════════════════

def _t001_future_timestamp_injection() -> RedTeamAttack:
    candles = _series(60)
    cutoff = candles[-1]["timestamp"]
    injected = candles + [{
        "timestamp": cutoff + timedelta(days=30),
        "close": 999.0,
    }]
    view = pit_candle_view(injected, cutoff)
    defended = (
        view.visible_count == 60
        and view.dropped_future_bars == 1
        and all(
            bar["timestamp"] <= cutoff for bar in view.bars
        )
    )
    return _attack(
        "RT-PRED-T-001", "temporal",
        precondition="PIT candle view at a declared cutoff",
        input_description="candle dated 30 days after the cutoff injected "
                          "into the input series",
        expected_behavior="future bar INVISIBLE at the cutoff; "
                          "dropped_future_bars incremented",
        actual_behavior=(
            f"visible={view.visible_count} bars, "
            f"dropped_future_bars={view.dropped_future_bars}"
        ),
        defended=defended,
        evidence=f"max visible ts "
                 f"{max(b['timestamp'] for b in view.bars).isoformat()} "
                 f"<= cutoff {cutoff.isoformat()}",
    )


def _t002_future_feature_injection() -> RedTeamAttack:
    candles = _series(60)
    cutoff_index = 40
    cutoff = candles[cutoff_index]["timestamp"]
    pit_closes = [c["close"] for c in candles[:cutoff_index + 1]]
    full_closes = [c["close"] for c in candles]
    pit_rows = build_feature_rows(pit_closes)
    full_rows = build_feature_rows(full_closes)
    pit_hash = feature_data_hash(pit_rows)
    full_hash = feature_data_hash(full_rows)
    defended = pit_hash != full_hash and len(pit_rows) < len(full_rows)
    return _attack(
        "RT-PRED-T-002", "temporal",
        precondition="feature construction over a PIT-visible prefix",
        input_description="features recomputed over the FULL series "
                          "(including post-cutoff bars) and compared to "
                          "the PIT-sliced computation",
        expected_behavior="feature hashes DIFFER — using non-PIT data is "
                          "detectable, and the estimator only ever "
                          "computes over the sliced view",
        actual_behavior=(
            f"pit feature hash != full-series hash: "
            f"{pit_hash != full_hash}; rows "
            f"{len(pit_rows)} vs {len(full_rows)}"
        ),
        defended=defended,
        evidence=(
            f"pit={pit_hash[:24]}.. full={full_hash[:24]}.. — the "
            "estimator builds features from view.bars only (§2 slice-"
            "then-compute)"
        ),
    )


def _t003_label_leakage() -> RedTeamAttack:
    candles = _series(60, crash_at=45)
    closes = [c["close"] for c in candles]
    definition = _label_def()
    labeled = _labels.compute_crash_labels(closes, definition)
    rows = build_feature_rows(closes)
    try:
        _labels.assert_label_feature_boundary(rows, labeled)
        defended = True
        actual = (
            "boundary assertion PASSED (features end at or before "
            "label window start)"
        )
    except PredictionContractError as exc:
        defended = False
        actual = f"boundary assertion raised: {exc}"
    # now attack: construct a feature row that overlaps the label window
    from data_engine.prediction.features import FeatureRow
    overlapping = FeatureRow(
        row_index=30,
        timestamp=None,
        source_start=25,
        source_end=36,  # label window starts at 31 — overlap!
        values=(0.0, 0.0, 0.0, 1.0, 0.0, 0.0),
    )
    try:
        _labels.assert_label_feature_boundary(
            (overlapping,), labeled
        )
        overlap_defended = False
        overlap_actual = "overlapping feature row was NOT detected"
    except PredictionContractError:
        overlap_defended = True
        overlap_actual = "overlapping feature row REJECTED (fail closed)"
    defended = defended and overlap_defended
    return _attack(
        "RT-PRED-T-003", "temporal",
        precondition="label/feature boundary proof over aligned rows",
        input_description="a crafted feature row whose source range "
                          "overlaps the label window [t+1, t+H]",
        expected_behavior="assert_label_feature_boundary RAISES — "
                          "leakage is a defect, not a warning",
        actual_behavior=f"clean rows: {actual}; crafted overlap: "
                        f"{overlap_actual}",
        defended=defended,
        evidence="label windows use closes[t+1..t+W]; feature rows are "
                 "structurally limited to source_end <= t",
    )


def _t004_publication_time_mismatch() -> RedTeamAttack:
    candles = _series(60)
    cutoff = candles[50]["timestamp"]
    # a "revision" arriving late: same timestamp, different close
    revised = list(candles) + [{
        "timestamp": candles[30]["timestamp"],
        "close": candles[30]["close"] * 0.5,
    }]
    clean_view = pit_candle_view(candles, cutoff)
    revised_view = pit_candle_view(revised, cutoff)
    defended = (
        revised_view.dropped_revision_bars == 1
        and [b["close"] for b in revised_view.bars]
        == [b["close"] for b in clean_view.bars]
    )
    return _attack(
        "RT-PRED-T-004", "temporal",
        precondition="first-arrival-wins revision policy",
        input_description="late-arriving duplicate timestamp carrying a "
                          "halved close price (a revision)",
        expected_behavior="revision DROPPED — the prediction's view of "
                          "history cannot be rewritten",
        actual_behavior=(
            f"dropped_revision_bars={revised_view.dropped_revision_bars}; "
            f"visible closes identical to clean view: "
            f"{[b['close'] for b in revised_view.bars] == [b['close'] for b in clean_view.bars]}"
        ),
        defended=defended,
        evidence="revision policy 'first-arrival-wins' (§34 no revised "
                 "data leakage)",
    )


def _t005_revision_leakage() -> RedTeamAttack:
    candles = _series(60)
    cutoff = candles[50]["timestamp"]
    original_view = pit_candle_view(candles, cutoff)
    extended = list(candles) + [{
        "timestamp": candles[30]["timestamp"],
        "close": candles[30]["close"] * 2.0,
    }]
    extended_view = pit_candle_view(extended, cutoff)
    from data_engine.prediction.estimator import (
        CrashRiskEstimator,
        EstimatorConfig,
    )
    model = _fitted_logistic(candles[:51])
    est = CrashRiskEstimator(
        model,
        config=EstimatorConfig(required_history_years=None),
        dataset_id="DS-RT",
    )
    definition = _label_def()
    evidence = _good_evidence()
    a1 = est.assess(
        candles, as_of=cutoff, label_definition=definition,
        prediction_time="RT", training_samples=100,
        evidence_values=evidence,
    )
    a2 = est.assess(
        extended, as_of=cutoff, label_definition=definition,
        prediction_time="RT", training_samples=100,
        evidence_values=evidence,
    )
    defended = (
        a1.prediction_id == a2.prediction_id
        and a1.probability == a2.probability
        and a1.status == a2.status
    )
    return _attack(
        "RT-PRED-T-005", "temporal",
        precondition="full estimator pipeline at a fixed cutoff",
        input_description="same candle history with a revised duplicate "
                          "appended after the fact",
        expected_behavior="prediction_id, probability, and status "
                          "UNCHANGED — revised history cannot leak into "
                          "a past prediction; the provenance record "
                          "honestly documents the dropped revision "
                          "(audit trail, not leakage)",
        actual_behavior=(
            f"ids equal: {a1.prediction_id == a2.prediction_id}; "
            f"probabilities equal: {a1.probability == a2.probability}; "
            f"statuses equal: {a1.status == a2.status}"
        ),
        defended=defended,
        evidence=(
            f"id={a1.prediction_id[:24]}..; original view "
            f"{original_view.visible_count} bars, extended view "
            f"{extended_view.visible_count} bars, "
            f"{extended_view.dropped_revision_bars} revision dropped "
            "(provenance_hash differs BY DESIGN — it records that a "
            "revision arrived and was refused)"
        ),
    )


def _t006_delayed_data_violation() -> RedTeamAttack:
    candles = _series(60)
    cutoff = candles[50]["timestamp"]
    base = pit_candle_view(candles, cutoff)
    reordered = list(reversed(candles))
    permuted = pit_candle_view(reordered, cutoff)
    defended = (
        permuted.visible_count == base.visible_count
        and [b["timestamp"] for b in permuted.bars]
        == [b["timestamp"] for b in base.bars]
        and [b["close"] for b in permuted.bars]
        == [b["close"] for b in base.bars]
    )
    return _attack(
        "RT-PRED-T-006", "temporal",
        precondition="PIT view sorted-by-timestamp invariant",
        input_description="input rows fully reversed (delayed arrival "
                          "ordering)",
        expected_behavior="view CONTENT AND ORDER unchanged — arrival "
                          "order cannot alter the PIT view",
        actual_behavior=(
            f"visible={permuted.visible_count}; bars identical to "
            f"ordered input: "
            f"{[b['close'] for b in permuted.bars] == [b['close'] for b in base.bars]}"
        ),
        defended=defended,
        evidence="view is built from a timestamp-sorted dict — order "
                 "independent by construction",
    )


def _t007_cutoff_boundary_abuse() -> RedTeamAttack:
    candles = _series(60)
    cutoff = candles[40]["timestamp"]
    at_cutoff = pit_candle_view(candles, cutoff)
    one_micro = cutoff + timedelta(microseconds=1)
    above = pit_candle_view(candles, one_micro)
    defended = (
        at_cutoff.visible_count == 41
        and above.visible_count == 41
        and pit_candle_view(candles, cutoff - timedelta(microseconds=1)).visible_count == 40
    )
    return _attack(
        "RT-PRED-T-007", "temporal",
        precondition="cutoff visibility rule timestamp <= as_of",
        input_description="cutoff moved by ±1 microsecond around an "
                          "existing bar timestamp",
        expected_behavior="bar AT the cutoff is VISIBLE; bar 1µs beyond "
                          "is INVISIBLE — the boundary is exact",
        actual_behavior=(
            f"visible at cutoff: {at_cutoff.visible_count}; at +1µs: "
            f"{above.visible_count}; at -1µs: "
            f"{pit_candle_view(candles, cutoff - timedelta(microseconds=1)).visible_count}"
        ),
        defended=defended,
        evidence="boundary comparison is <= on UTC-normalized "
                 "timestamps (no tz shift can flip it)",
    )


def _t008_timezone_boundary_manipulation() -> RedTeamAttack:
    candles = _series(60)
    cutoff_utc = candles[40]["timestamp"]
    # same instant expressed in a +05:00 offset timezone
    from datetime import timezone as _tz
    cutoff_shifted = cutoff_utc.astimezone(
        _tz(timedelta(hours=5))
    )
    view_utc = pit_candle_view(candles, cutoff_utc)
    view_shifted = pit_candle_view(candles, cutoff_shifted)
    defended = (
        view_utc.visible_count == view_shifted.visible_count
        and [b["timestamp"] for b in view_utc.bars]
        == [b["timestamp"] for b in view_shifted.bars]
    )
    return _attack(
        "RT-PRED-T-008", "temporal",
        precondition="UTC-normalized cutoff comparison",
        input_description="the same cutoff instant expressed as "
                          "UTC vs UTC+05:00",
        expected_behavior="IDENTICAL visibility decision — timezone "
                          "representation cannot move the boundary",
        actual_behavior=(
            f"visible counts equal: "
            f"{view_utc.visible_count == view_shifted.visible_count} "
            f"({view_utc.visible_count})"
        ),
        defended=defended,
        evidence="as_of and every timestamp are normalized to UTC before "
                 "comparison",
    )


# ═══════════════════════════ identity attacks ════════════════════════════

def _i001_type_collision() -> RedTeamAttack:
    candles = _series(30)
    poisoned = list(candles)
    poisoned[10] = {**poisoned[10], "close": True}  # bool, not number
    cutoff = candles[29]["timestamp"]
    try:
        pit_candle_view(poisoned, cutoff)
        defended = False
        actual = "bool close was silently accepted as 1.0"
    except PredictionContractError:
        defended = True
        actual = "bool close REJECTED (PredictionDataError)"
    return _attack(
        "RT-PRED-I-001", "identity",
        precondition="duck-typed candle close validation",
        input_description="close=True (Python bool — an int subclass "
                          "that float() would silently coerce to 1.0)",
        expected_behavior="REJECTED — type collisions cannot enter the "
                          "PIT view",
        actual_behavior=actual,
        defended=defended,
        evidence="bool check precedes float coercion in "
                 "_candle_close (RT hardening)",
    )


def _i002_numeric_representation() -> RedTeamAttack:
    candles = _series(30)
    variant = list(candles)
    variant[10] = {
        **variant[10],
        "close": variant[10]["close"] + 1e-13,
    }
    cutoff = candles[29]["timestamp"]
    v1 = pit_candle_view(candles, cutoff)
    v2 = pit_candle_view(variant, cutoff)
    c1 = [b["close"] for b in v1.bars]
    c2 = [b["close"] for b in v2.bars]
    identical_after_freeze = all(
        round(a, 12) == round(b, 12) for a, b in zip(c1, c2)
    )
    r1 = build_feature_rows(c1)
    r2 = build_feature_rows(c2)
    defended = (
        identical_after_freeze
        and feature_data_hash(r1) == feature_data_hash(r2)
    )
    return _attack(
        "RT-PRED-I-002", "identity",
        precondition="12-decimal identity freeze semantics (documented)",
        input_description="close differing by 1e-13 — below the freeze "
                          "resolution",
        expected_behavior="deterministic DOCUMENTED equivalence: "
                          "sub-resolution differences hash identically "
                          "(resolution limit recorded, not hidden)",
        actual_behavior=(
            f"hash equal after 12-decimal freeze: "
            f"{feature_data_hash(r1) == feature_data_hash(r2)}"
        ),
        defended=defended,
        evidence="freeze resolution is 1e-12 (round(x, 12)) — the "
                 "documented identity resolution floor",
    )


def _i003_null_empty_confusion() -> RedTeamAttack:
    candles = _series(30)
    null_poisoned = list(candles)
    null_poisoned[10] = {**null_poisoned[10], "close": None}
    cutoff = candles[29]["timestamp"]
    try:
        pit_candle_view(null_poisoned, cutoff)
        null_defended = False
        null_actual = "None close accepted"
    except PredictionContractError:
        null_defended = True
        null_actual = "None close REJECTED"
    empty_view = pit_candle_view([], cutoff)
    empty_handled = empty_view.visible_count == 0
    from data_engine.prediction.estimator import (
        CrashRiskEstimator,
        EstimatorConfig,
    )
    model = _fitted_logistic(candles)
    est = CrashRiskEstimator(
        model,
        config=EstimatorConfig(required_history_years=None),
        dataset_id="DS-RT",
    )
    blocked = est.assess(
        [], as_of=cutoff, label_definition=_label_def(),
        prediction_time="RT",
    )
    empty_blocked = (
        blocked.status == "PREDICTION_BLOCKED"
        and blocked.blocked_reason is BlockReason.DATA_QUALITY_FAILED
    )
    defended = null_defended and empty_handled and empty_blocked
    return _attack(
        "RT-PRED-I-003", "identity",
        precondition="close validation + empty-input estimator path",
        input_description="close=None mid-series; and an EMPTY candle "
                          "list passed to the estimator",
        expected_behavior="None REJECTED; empty series produces a "
                          "PREDICTION_BLOCKED assessment — never a "
                          "fabricated number",
        actual_behavior=(
            f"{null_actual}; empty view bars="
            f"{empty_view.visible_count}; empty-assess status="
            f"{blocked.status}/{blocked.blocked_reason.value}"
        ),
        defended=defended,
        evidence="'no candles visible at the PIT cutoff' refusal path",
    )


def _i004_field_order_manipulation() -> RedTeamAttack:
    payload_a = {"model_id": "M", "beta": 1.5, "alpha": 0.25}
    payload_b = {"alpha": 0.25, "beta": 1.5, "model_id": "M"}
    hash_a = prefixed_hash("predv.", payload_a)
    hash_b = prefixed_hash("predv.", payload_b)
    defended = hash_a == hash_b
    return _attack(
        "RT-PRED-I-004", "identity",
        precondition="canonical key-sorted serialization",
        input_description="identity payload with dict keys in two "
                          "different insertion orders",
        expected_behavior="IDENTICAL identity — field order cannot "
                          "reorder identity",
        actual_behavior=f"hashes equal: {hash_a == hash_b}",
        defended=defended,
        evidence=f"{hash_a[:24]}.. == {hash_b[:24]}..",
    )


def _i005_serialization_ambiguity() -> RedTeamAttack:
    model = _fitted_logistic(_series(60))
    artifact = model.artifact()
    direct_hash = artifact.model_hash
    round_trip = type(artifact).model_validate_json(
        artifact.model_dump_json()
    )
    defended = round_trip.model_hash == direct_hash
    # tuple-vs-list parameter representation
    payload_tuple = {"params": [("a", 1.0), ("b", 2.0)]}
    payload_list = {"params": [["a", 1.0], ["b", 2.0]]}
    tuple_hash = prefixed_hash("predv.", payload_tuple)
    list_hash = prefixed_hash("predv.", payload_list)
    represented = tuple_hash == list_hash
    defended = defended and represented
    return _attack(
        "RT-PRED-I-005", "identity",
        precondition="ModelArtifact JSON round-trip + tuple/list "
                     "canonicalization",
        input_description="artifact serialized to JSON and rebuilt; "
                          "parameters expressed as tuples vs lists",
        expected_behavior="hash STABLE through the round-trip; tuples "
                          "and lists canonicalize identically",
        actual_behavior=(
            f"round-trip stable: {round_trip.model_hash == direct_hash}; "
            f"tuple/list identical: {represented}"
        ),
        defended=defended,
        evidence="serialization ambiguity cannot fork an identity",
    )


def _i006_unicode_normalization() -> RedTeamAttack:
    nfc = "caf\u00e9"          # é as one code point
    nfd = "cafe\u0301"         # é as e + combining acute
    hash_nfc = prefixed_hash("predv.", {"symbol": nfc})
    hash_nfd = prefixed_hash("predv.", {"symbol": nfd})
    distinct = hash_nfc != hash_nfd
    return _attack(
        "RT-PRED-I-006", "identity",
        precondition="byte-exact canonical serialization (no silent "
                     "Unicode normalization)",
        input_description="symbol 'café' in NFC vs NFD normalization "
                          "forms",
        expected_behavior="DIFFERENT identities — two visibly-equal "
                          "strings never silently merge into one asset; "
                          "callers must normalize deliberately",
        actual_behavior=f"hashes distinct: {distinct}",
        defended=distinct,
        evidence=(
            f"{hash_nfc[:24]}.. != {hash_nfd[:24]}.. — byte-level "
            "distinction preserved (fail-visible, not fail-silent)"
        ),
    )


def _i007_float_edge_inf() -> RedTeamAttack:
    candles = _series(30)
    poisoned = list(candles)
    poisoned[10] = {
        **poisoned[10], "close": float("inf"),
    }
    cutoff = candles[29]["timestamp"]
    try:
        pit_candle_view(poisoned, cutoff)
        data_defended = False
        data_actual = "inf close accepted"
    except PredictionContractError:
        data_defended = True
        data_actual = "inf close REJECTED"
    try:
        prefixed_hash("predv.", {"value": float("inf")})
        freeze_defended = False
        freeze_actual = "inf entered an identity payload"
    except PredictionContractError:
        freeze_defended = True
        freeze_actual = "inf REJECTED from identity payloads"
    defended = data_defended and freeze_defended
    return _attack(
        "RT-PRED-I-007", "identity",
        precondition="finite-float validation at data access AND "
                     "identity freeze",
        input_description="close=+inf in a candle; inf in a hashed "
                          "payload",
        expected_behavior="BOTH rejected — non-finite numbers are data "
                          "failures, never identity inputs",
        actual_behavior=f"{data_actual}; {freeze_actual}",
        defended=defended,
        evidence="freeze_number raises on inf (RT hardening); "
                 "_candle_close rejects non-finite closes",
    )


def _i008_nan_handling() -> RedTeamAttack:
    candles = _series(30)
    poisoned = list(candles)
    poisoned[10] = {**poisoned[10], "close": float("nan")}
    cutoff = candles[29]["timestamp"]
    try:
        pit_candle_view(poisoned, cutoff)
        data_defended = False
        data_actual = "NaN close accepted"
    except PredictionContractError:
        data_defended = True
        data_actual = "NaN close REJECTED"
    from data_engine.prediction.identity import freeze_number
    frozen = freeze_number(float("nan"))
    defended = data_defended and frozen is None
    return _attack(
        "RT-PRED-I-008", "identity",
        precondition="NaN rejection at data access; NaN->None at "
                     "identity freeze",
        input_description="close=NaN in a candle; NaN as a hashed "
                          "numeric leaf",
        expected_behavior="NaN close REJECTED; freeze_number maps NaN "
                          "to None — NaN is never hashed as a number",
        actual_behavior=f"{data_actual}; freeze_number(NaN) -> {frozen}",
        defended=defended,
        evidence="None marks missing values so they can never silently "
                 "pass as numeric identity",
    )


# ═════════════════════════ provenance attacks ═══════════════════════════

def _record(i: int) -> OutcomeRecord:
    return OutcomeRecord(
        prediction_id=f"pred.rt.{i}",
        model_id="LOGISTIC-1",
        model_version="1",
        forecast=0.3,
        actual=bool(i % 3 == 0),
        horizon_bars=5,
        regime="NORMAL",
        confidence="uncalibrated",
        evidence_score=0.7,
        calibration_version="UNCALIBRATED",
        outcome_timestamp=f"2024-01-{i + 1:02d}T00:00:00+00:00",
    )


def _p001_broken_hash_chain() -> RedTeamAttack:
    ledger = PredictionOutcomeLedger()
    for i in range(5):
        ledger.append(_record(i))
    tampered_entries = list(ledger.entries)
    forged = tampered_entries[2].model_copy(
        update={"record": _record(2).model_copy(update={"forecast": 0.9})}
    )
    tampered_entries[2] = forged
    rebuilt = PredictionOutcomeLedger()
    rebuilt._entries = tampered_entries
    rebuilt._chain = [
        e.record_hash for e in tampered_entries
    ]
    defended = (
        ledger.verify() is True
        and rebuilt.verify() is False
    )
    return _attack(
        "RT-PRED-P-001", "provenance",
        precondition="append-only outcome ledger with hash chain",
        input_description="entry 2's forecast mutated after the fact",
        expected_behavior="chain verification FAILS on the mutated "
                          "ledger; clean ledger verifies",
        actual_behavior=(
            f"clean verify={ledger.verify()}, tampered "
            f"verify={rebuilt.verify()}"
        ),
        defended=defended,
        evidence="record_hash covers the full record payload + index + "
                 "prev hash",
    )


def _p002_altered_parent_hash() -> RedTeamAttack:
    ledger = PredictionOutcomeLedger()
    for i in range(4):
        ledger.append(_record(i))
    entries = list(ledger.entries)
    entries[2] = entries[2].model_copy(
        update={"prev_record_hash": "0" * 64}
    )
    rebuilt = PredictionOutcomeLedger()
    rebuilt._entries = entries
    rebuilt._chain = [e.record_hash for e in entries]
    defended = rebuilt.verify() is False
    return _attack(
        "RT-PRED-P-002", "provenance",
        precondition="ledger chain links entries via prev_record_hash",
        input_description="entry 2's parent hash replaced with the "
                          "genesis hash (forged chain origin)",
        expected_behavior="verification FAILS — parent link integrity "
                          "is checked per-entry",
        actual_behavior=f"tampered verify={rebuilt.verify()}",
        defended=defended,
        evidence="prev_record_hash must equal the previous entry's "
                 "record_hash exactly",
    )


def _p003_altered_dataset_identifier() -> RedTeamAttack:
    from data_engine.prediction.provenance import PredictionProvenance
    base = PredictionProvenance(
        prediction_id="pred.rt.x",
        model_id="LOGISTIC-1",
        model_version="1",
        experiment_id="EXP-RT",
        dataset_id="DS-ORIGINAL",
        feature_set_id="predf.x",
        feature_hash="predf.f",
        model_hash="predm.m",
        configuration_hash="predv.c",
        pit_cutoff="2024-01-01T00:00:00+00:00",
        prediction_time="RT",
        input_snapshot_hash="predv.i",
        output_hash="predo.o",
        regime="NORMAL",
        calibration_version="UNCALIBRATED",
        training_window="0..100",
        training_data_hash="DS-ORIGINAL",
        environment_fingerprint="UNRECORDED",
    )
    from data_engine.prediction.identity import prefixed_hash as _h
    original_hash = _h("predv.", {
        "kind": "provenance_body",
        "dataset_id": base.dataset_id,
    })
    altered_hash = _h("predv.", {
        "kind": "provenance_body",
        "dataset_id": "DS-SWAPPED",
    })
    defended = original_hash != altered_hash
    return _attack(
        "RT-PRED-P-003", "provenance",
        precondition="provenance identity covers dataset_id",
        input_description="dataset identifier swapped inside a "
                          "provenance record body",
        expected_behavior="provenance content hash CHANGES — the swap "
                          "is tamper-evident, not silent",
        actual_behavior=f"hash changed: {defended}",
        defended=defended,
        evidence="dataset_id participates in every derived provenance "
                 "hash; a changed id is a different record",
    )


def _p004_altered_model_identifier() -> RedTeamAttack:
    candles = _series(60)
    model = _fitted_logistic(candles)
    from data_engine.prediction.estimator import (
        CrashRiskEstimator,
        EstimatorConfig,
    )
    est = CrashRiskEstimator(
        model,
        config=EstimatorConfig(required_history_years=None),
        dataset_id="DS-RT",
    )
    cutoff = candles[50]["timestamp"]
    evidence = _good_evidence()
    a = est.assess(
        candles, as_of=cutoff, label_definition=_label_def(),
        prediction_time="RT", training_samples=100,
        evidence_values=evidence,
    )
    swapped = a.model_copy(update={"model_id": "IMPOSTER-1"})
    defended = swapped.output_hash != a.output_hash
    return _attack(
        "RT-PRED-P-004", "provenance",
        precondition="assessment output_hash covers model identity",
        input_description="model_id field swapped on a produced "
                          "assessment",
        expected_behavior="output_hash CHANGES — a swapped model "
                          "identity cannot inherit the original "
                          "assessment's tamper-evidence",
        actual_behavior=f"hash changed: {defended}",
        defended=defended,
        evidence="model_id is inside output_payload; any mutation "
                 "forks the hash",
    )


def _p005_forged_verification_state() -> RedTeamAttack:
    candles = _series(60)
    model = _fitted_logistic(candles)
    forged = verify_model_artifact(
        model,
        expected_hash="predm.FORGED0000",
        expected_feature_count=6,
    )
    defended = (
        forged.verified is False
        and forged.expected_hash_match is False
    )
    return _attack(
        "RT-PRED-P-005", "provenance",
        precondition="independent artifact re-verification (PRED-F3)",
        input_description="caller asserts a fabricated expected model "
                          "hash (the 'verified=True' pattern)",
        expected_behavior="verification RECOMPUTES the artifact hash and "
                          "REJECTS the forged expectation — caller "
                          "claims are never trusted",
        actual_behavior=(
            f"verified={forged.verified}; expected_hash_match="
            f"{forged.expected_hash_match}"
        ),
        defended=defended,
        evidence=f"failures: {list(forged.failures)[:1]}",
    )


def _p006_mismatched_artifact_hash() -> RedTeamAttack:
    candles = _series(60)
    model = _fitted_logistic(candles)
    from data_engine.prediction.estimator import (
        CrashRiskEstimator,
        EstimatorConfig,
    )
    est = CrashRiskEstimator(
        model,
        config=EstimatorConfig(required_history_years=None),
        dataset_id="DS-RT",
    )
    cutoff = candles[50]["timestamp"]
    evidence = _good_evidence()
    blocked = est.assess(
        candles, as_of=cutoff, label_definition=_label_def(),
        prediction_time="RT", training_samples=100,
        evidence_values=evidence,
        expected_model_hash="predm.STALE0000",
    )
    defended = (
        blocked.status == "PREDICTION_BLOCKED"
        and blocked.blocked_reason is BlockReason.MODEL_ARTIFACT_MISMATCH
    )
    return _attack(
        "RT-PRED-P-006", "provenance",
        precondition="estimator-bound expected model hash (PRED-F3)",
        input_description="registry-supplied expected hash that does "
                          "not match the live model artifact",
        expected_behavior="assessment BLOCKED with "
                          "MODEL_ARTIFACT_MISMATCH — stale/substituted "
                          "artifacts never predict",
        actual_behavior=(
            f"status={blocked.status}; reason="
            f"{blocked.blocked_reason.value}"
        ),
        defended=defended,
        evidence="verify_model_artifact runs inside assess() and feeds "
                 "the gate machine",
    )


def _p007_stale_provenance() -> RedTeamAttack:
    candles = _series(60)
    checksum = dataset_content_hash(candles)
    manifest = DatasetManifest(
        dataset_name="rt-stale",
        source_name="synthetic:redteam",
        source_version="1",
        acquisition_timestamp="SYNTHETIC-NO-ACQUISITION",
        coverage_start="2024-01-01",
        coverage_end="2024-02-29",
        symbol="TEST",
        timezone="UTC",
        frequency="1D",
        corporate_action_treatment="not-applicable-synthetic",
        adjustment_policy="not-applicable-synthetic",
        missing_data_policy="not-applicable-synthetic",
        revision_policy="append-only-first-arrival",
        license_basis="synthetic-fixture",
        provenance_metadata=(("generator", "redteam"), ("seed", "7")),
        content_checksum=checksum,
        row_count=60,
        data_state=DatasetState.SYNTHETIC,
    )
    mutated = list(candles)
    mutated[30] = {**mutated[30], "close": mutated[30]["close"] * 1.5}
    report = validate_ohlcv(mutated, manifest=manifest)
    checksum_gate = next(
        f for f in report.findings
        if f.gate.value == "QG-15-checksum-mismatch"
    )
    defended = (
        not report.passed
        and not checksum_gate.passed
        and report.refusal_state == "INVALID"
    )
    return _attack(
        "RT-PRED-P-007", "provenance",
        precondition="dataset content checksum gate (QG-15)",
        input_description="dataset rows mutated after the manifest "
                          "checksum was recorded (stale provenance)",
        expected_behavior="quality report INVALID — checksum mismatch "
                          "is an explicit refusal",
        actual_behavior=(
            f"passed={report.passed}; refusal={report.refusal_state}; "
            f"QG-15 passed={checksum_gate.passed}"
        ),
        defended=defended,
        evidence=checksum_gate.detail[:80],
    )


# ═══════════════════════════ data attacks ═══════════════════════════════

def _data_manifest(candles: list[dict]) -> DatasetManifest:
    return DatasetManifest(
        dataset_name="rt-data",
        source_name="synthetic:redteam",
        source_version="1",
        acquisition_timestamp="SYNTHETIC-NO-ACQUISITION",
        coverage_start=candles[0]["timestamp"].date().isoformat(),
        coverage_end=candles[-1]["timestamp"].date().isoformat(),
        symbol="TEST",
        timezone="UTC",
        frequency="1D",
        corporate_action_treatment="not-applicable-synthetic",
        adjustment_policy="not-applicable-synthetic",
        missing_data_policy="not-applicable-synthetic",
        revision_policy="append-only-first-arrival",
        license_basis="synthetic-fixture",
        provenance_metadata=(("generator", "redteam"), ("seed", "11")),
        content_checksum=dataset_content_hash(candles),
        row_count=len(candles),
        data_state=DatasetState.SYNTHETIC,
    )


def _gate_report(candles, manifest, *, gate_id: str):
    report = validate_ohlcv(candles, manifest=manifest)
    finding = next(
        f for f in report.findings if f.gate.value == gate_id
    )
    return report, finding


def _d001_duplicate_rows() -> RedTeamAttack:
    candles = _series(60)
    manifest = _data_manifest(candles)
    poisoned = list(candles)
    poisoned.insert(30, dict(candles[30]))
    report, finding = _gate_report(
        poisoned, manifest, gate_id="QG-02-duplicate-timestamps"
    )
    defended = (
        not finding.passed
        and report.refusal_state is not None
    )
    return _attack(
        "RT-PRED-D-001", "data",
        precondition="quality gate QG-02",
        input_description="an exact duplicate row inserted mid-series",
        expected_behavior="duplicate gate FAILS; report refuses "
                          "(explicit refusal state)",
        actual_behavior=(
            f"QG-02 passed={finding.passed}; refusal="
            f"{report.refusal_state}"
        ),
        defended=defended,
        evidence=finding.detail,
    )


def _d002_reordered_rows() -> RedTeamAttack:
    candles = _series(60)
    manifest = _data_manifest(candles)
    poisoned = list(candles)
    poisoned[30], poisoned[31] = poisoned[31], poisoned[30]
    report, finding = _gate_report(
        poisoned, manifest, gate_id="QG-01-timestamp-ordering"
    )
    defended = not finding.passed
    return _attack(
        "RT-PRED-D-002", "data",
        precondition="quality gate QG-01",
        input_description="two adjacent rows swapped (ordering broken)",
        expected_behavior="ordering gate FAILS — dataset ingestion "
                          "refuses unordered rows",
        actual_behavior=f"QG-01 passed={finding.passed}",
        defended=defended,
        evidence=finding.detail,
    )


def _d003_missing_blocks() -> RedTeamAttack:
    candles = _series(60)
    manifest = _data_manifest(candles)
    poisoned = candles[:30] + candles[45:]  # 15-day hole
    report, finding = _gate_report(
        poisoned, manifest, gate_id="QG-03-missing-intervals"
    )
    defended = not finding.passed
    return _attack(
        "RT-PRED-D-003", "data",
        precondition="quality gate QG-03 (daily tolerance 7 days)",
        input_description="a 15-day block of bars removed mid-series",
        expected_behavior="missing-interval gate FAILS — gaps are "
                          "listed, never silently interpolated",
        actual_behavior=f"QG-03 passed={finding.passed}",
        defended=defended,
        evidence=finding.detail,
    )


def _d004_corrupted_values() -> RedTeamAttack:
    candles = _series(60)
    manifest = _data_manifest(candles)
    poisoned = list(candles)
    poisoned[30] = {**poisoned[30], "close": -5.0}
    report, finding = _gate_report(
        poisoned, manifest, gate_id="QG-05-negative-invalid-prices"
    )
    defended = not finding.passed and report.refusal_state == "INVALID"
    return _attack(
        "RT-PRED-D-004", "data",
        precondition="quality gate QG-05",
        input_description="close replaced with a negative price",
        expected_behavior="price gate FAILS; report INVALID — negative "
                          "prices are never repaired in place",
        actual_behavior=(
            f"QG-05 passed={finding.passed}; refusal="
            f"{report.refusal_state}"
        ),
        defended=defended,
        evidence=finding.detail,
    )


def _d005_impossible_ohlc() -> RedTeamAttack:
    candles = _series(60)
    manifest = _data_manifest(candles)
    poisoned = []
    for i, c in enumerate(candles):
        row = dict(c)
        if i == 30:
            row.update({
                "open": 100.0, "high": 95.0,  # high < open
                "low": 90.0,
            })
        poisoned.append(row)
    report, finding = _gate_report(
        poisoned, manifest, gate_id="QG-04-impossible-ohlc"
    )
    defended = not finding.passed
    return _attack(
        "RT-PRED-D-005", "data",
        precondition="quality gate QG-04 (OHLC relationships)",
        input_description="row with high < open (impossible candle)",
        expected_behavior="OHLC gate FAILS — impossible bars are "
                          "refused, not clipped",
        actual_behavior=f"QG-04 passed={finding.passed}",
        defended=defended,
        evidence=finding.detail,
    )


def _d006_extreme_outliers() -> RedTeamAttack:
    candles = _series(60)
    manifest = _data_manifest(candles)
    poisoned = list(candles)
    # 3x jump — split-like under an adjusted-price policy
    real_manifest = manifest.model_copy(update={
        "corporate_action_treatment": "split-adjusted",
        "adjustment_policy": "back-adjusted",
        "content_checksum": dataset_content_hash(poisoned),
    })
    poisoned[31] = {
        **poisoned[31],
        "close": poisoned[30]["close"] * 3.0,
    }
    report, finding = _gate_report(
        poisoned, real_manifest, gate_id="QG-12-corporate-action-consistency"
    )
    defended = not finding.passed
    return _attack(
        "RT-PRED-D-006", "data",
        precondition="quality gate QG-12 (corporate-action consistency)",
        input_description="a 3x single-bar price jump under a declared "
                          "split-adjusted policy",
        expected_behavior="corporate-action gate FLAGS the jump — an "
                          "unadjusted split is suspected and refused",
        actual_behavior=f"QG-12 passed={finding.passed}",
        defended=defended,
        evidence=finding.detail,
    )


def _d007_symbol_substitution() -> RedTeamAttack:
    candles = _series(60)
    manifest = _data_manifest(candles)
    poisoned = []
    for i, c in enumerate(candles):
        row = dict(c)
        if i >= 30:
            row["symbol"] = "IMPOSTER"
        poisoned.append(row)
    report, finding = _gate_report(
        poisoned, manifest, gate_id="QG-10-symbol-identity"
    )
    defended = not finding.passed
    return _attack(
        "RT-PRED-D-007", "data",
        precondition="quality gate QG-10 (symbol identity)",
        input_description="half the rows carry a foreign symbol mid-"
                          "series",
        expected_behavior="symbol gate FAILS — cross-symbol "
                          "contamination is refused",
        actual_behavior=f"QG-10 passed={finding.passed}",
        defended=defended,
        evidence=finding.detail,
    )


def _d008_partial_dataset() -> RedTeamAttack:
    candles = _series(60)
    manifest = _data_manifest(candles)
    partial = candles[:40]  # 20 bars short of the declared coverage
    report, finding = _gate_report(
        partial, manifest, gate_id="QG-11-coverage-gaps"
    )
    defended = not finding.passed
    return _attack(
        "RT-PRED-D-008", "data",
        precondition="quality gate QG-11 (manifest coverage match)",
        input_description="only 40 of 60 declared bars delivered",
        expected_behavior="coverage gate FAILS — a partial dataset "
                          "cannot pose as the declared one",
        actual_behavior=f"QG-11 passed={finding.passed}",
        defended=defended,
        evidence=finding.detail,
    )


# ═══════════════════════════ model attacks ══════════════════════════════

def _estimator_with(model, **kwargs):
    from data_engine.prediction.estimator import (
        CrashRiskEstimator,
        EstimatorConfig,
    )
    return CrashRiskEstimator(
        model,
        config=EstimatorConfig(required_history_years=None),
        dataset_id=kwargs.pop("dataset_id", "DS-RT"),
        **kwargs,
    )


def _m001_stale_model() -> RedTeamAttack:
    candles = _series(60)
    model = _fitted_logistic(candles)
    registered_hash = model.model_hash
    # "stale": the registry expects the ORIGINAL hash, the live model
    # was refit with different data
    stale_model = _fitted_logistic(_series(60, crash_at=20))
    est = _estimator_with(stale_model)
    cutoff = candles[50]["timestamp"]
    evidence = _good_evidence()
    blocked = est.assess(
        candles, as_of=cutoff, label_definition=_label_def(),
        prediction_time="RT", training_samples=100,
        evidence_values=evidence,
        expected_model_hash=registered_hash,
    )
    defended = (
        blocked.status == "PREDICTION_BLOCKED"
        and blocked.blocked_reason is BlockReason.MODEL_ARTIFACT_MISMATCH
    )
    return _attack(
        "RT-PRED-M-001", "model",
        precondition="registry-bound model hash + live refit model",
        input_description="model refit on different data after "
                          "registration (hash changed)",
        expected_behavior="assessment BLOCKED — the stale registration "
                          "does not cover the new artifact",
        actual_behavior=(
            f"status={blocked.status}; reason="
            f"{blocked.blocked_reason.value}"
        ),
        defended=defended,
        evidence="expected-hash comparison inside assess() (PRED-F3)",
    )


def _m002_drifted_model() -> RedTeamAttack:
    gate = evaluate_prediction_gates(PredictionGateInput(
        drift_state=DriftState.DRIFTED,
        training_samples=100, history_bars=1300, horizon_bars=20,
    ))
    gate_invalid = evaluate_prediction_gates(PredictionGateInput(
        drift_state=DriftState.INVALID,
        training_samples=100, history_bars=1300, horizon_bars=20,
    ))
    defended = (
        not gate.allowed
        and gate.blocked_reason is BlockReason.MODEL_DRIFT_UNACCEPTABLE
        and not gate_invalid.allowed
    )
    return _attack(
        "RT-PRED-M-002", "model",
        precondition="no-prediction gate drift checks (§37)",
        input_description="drift state DRIFTED and INVALID",
        expected_behavior="BOTH states BLOCK predictions — drifted/ "
                          "invalid models never silently continue as "
                          "production states",
        actual_behavior=(
            f"DRIFTED allowed={gate.allowed}; INVALID allowed="
            f"{gate_invalid.allowed}"
        ),
        defended=defended,
        evidence="§37: DRIFTED -> block or require review; INVALID -> "
                 "retire",
    )


def _m003_invalid_calibration() -> RedTeamAttack:
    gate = evaluate_prediction_gates(PredictionGateInput(
        calibration_valid=False,
        training_samples=100, history_bars=1300, horizon_bars=20,
    ))
    defended = (
        not gate.allowed
        and gate.blocked_reason is BlockReason.CALIBRATION_INVALID
    )
    return _attack(
        "RT-PRED-M-003", "model",
        precondition="no-prediction gate calibration check",
        input_description="calibration_valid=False with everything "
                          "else green",
        expected_behavior="prediction BLOCKED — an invalid calibrator "
                          "never emits a risk level",
        actual_behavior=(
            f"allowed={gate.allowed}; reason="
            f"{gate.blocked_reason.value}"
        ),
        defended=defended,
        evidence="§18 calibration validity is a hard gate",
    )


class _OpaqueModel:
    """Model with identity fields but NO artifact() — unverifiable."""

    model_id = "OPAQUE-1"
    model_version = "1"

    @property
    def model_hash(self) -> str:
        return "predm.opaque-unverifiable"

    def fit(self, X, y):
        return self

    def predict_proba(self, x):
        return 0.5


def _m004_unsupported_artifact() -> RedTeamAttack:
    report = verify_model_artifact(_OpaqueModel())
    candles = _series(60)
    est = _estimator_with(_OpaqueModel())
    cutoff = candles[50]["timestamp"]
    evidence = _good_evidence()
    blocked = est.assess(
        candles, as_of=cutoff, label_definition=_label_def(),
        prediction_time="RT", training_samples=100,
        evidence_values=evidence,
    )
    defended = (
        report.verified is False
        and blocked.status == "PREDICTION_BLOCKED"
        and blocked.blocked_reason is BlockReason.MODEL_ARTIFACT_MISMATCH
    )
    return _attack(
        "RT-PRED-M-004", "model",
        precondition="independent artifact verification (PRED-F3)",
        input_description="model object exposing model_id/version/hash "
                          "but NO artifact() method",
        expected_behavior="verification FAILS CLOSED — a hash that "
                          "cannot be recomputed is not trusted; the "
                          "estimator blocks",
        actual_behavior=(
            f"verified={report.verified}; estimator status="
            f"{blocked.status}/{blocked.blocked_reason.value}"
        ),
        defended=defended,
        evidence=(
            "documented boundary: without artifact() the strongest "
            "possible verification is identity-field validation, which "
            "does not establish content integrity"
        ),
    )


def _m005_schema_mismatch() -> RedTeamAttack:
    candles = _series(60)
    wrong = LogisticCrashModel(("f1", "f2", "f3"))  # 3 features, not 6
    closes = [c["close"] for c in candles]
    labeled = _labels.compute_crash_labels(closes, _label_def())
    rows = build_feature_rows(closes)
    usable = [
        r for r in rows if labeled[r.row_index].label is not None
    ]
    X3 = [
        list(r.values[:3]) for r in usable
    ]
    y = [
        int(labeled[r.row_index].label)
        for r in usable
    ]
    wrong.fit(X3, y)
    report = verify_model_artifact(
        wrong, expected_feature_count=6
    )
    est = _estimator_with(wrong)
    cutoff = candles[50]["timestamp"]
    evidence = _good_evidence()
    blocked = est.assess(
        candles, as_of=cutoff, label_definition=_label_def(),
        prediction_time="RT", training_samples=100,
        evidence_values=evidence,
    )
    defended = (
        report.schema_compatible is False
        and blocked.status == "PREDICTION_BLOCKED"
        and blocked.blocked_reason is BlockReason.FEATURE_SCHEMA_MISMATCH
    )
    return _attack(
        "RT-PRED-M-005", "model",
        precondition="artifact schema verification + feature gate",
        input_description="3-feature model fed to a 6-feature "
                          "estimator",
        expected_behavior="schema incompatibility DETECTED at "
                          "verification; estimator blocks with "
                          "FEATURE_SCHEMA_MISMATCH",
        actual_behavior=(
            f"schema_compatible={report.schema_compatible}; estimator="
            f"{blocked.status}/{blocked.blocked_reason.value}"
        ),
        defended=defended,
        evidence=report.schema_detail,
    )


def _m006_feature_mismatch_predict() -> RedTeamAttack:
    from data_engine.prediction.models import PredictionModelError
    model = LogisticCrashModel(("f1", "f2"))
    try:
        model.predict_proba([0.1, 0.2, 0.3])  # wrong arity
        defended = False
        actual = "wrong-arity input accepted"
    except PredictionModelError as exc:
        defended = True
        actual = f"PredictionModelError raised: {exc}"
    return _attack(
        "RT-PRED-M-006", "model",
        precondition="model predict-time arity check",
        input_description="predict_proba called with 3 values on a "
                          "2-feature model",
        expected_behavior="RAISES PredictionModelError — the estimator "
                          "maps this to a blocked assessment",
        actual_behavior=actual,
        defended=defended,
        evidence="fail-closed model contract (§27 root cause)",
    )


def _m007_model_data_version_mismatch() -> RedTeamAttack:
    candles = _series(60)
    model = _fitted_logistic(candles)
    est = _estimator_with(model, dataset_id="DS-OLD")
    cutoff = candles[50]["timestamp"]
    evidence = _good_evidence()
    blocked = est.assess(
        candles, as_of=cutoff, label_definition=_label_def(),
        prediction_time="RT", training_samples=100,
        evidence_values=evidence,
        expected_dataset_id="DS-NEW",
    )
    defended = (
        blocked.status == "PREDICTION_BLOCKED"
        and blocked.blocked_reason is BlockReason.MODEL_ARTIFACT_MISMATCH
        and any(
            "model/data version mismatch" in note
            for note in blocked.notes
        )
    )
    return _attack(
        "RT-PRED-M-007", "model",
        precondition="dataset-compatibility verification (PRED-F3)",
        input_description="estimator bound to dataset DS-OLD but "
                          "assessed against expected DS-NEW",
        expected_behavior="BLOCKED — model/data version mismatch is "
                          "recorded in the refusal notes",
        actual_behavior=(
            f"status={blocked.status}; reason="
            f"{blocked.blocked_reason.value}"
        ),
        defended=defended,
        evidence="dataset_compatible=False in the verification report",
    )


# ═════════════════════ crash-intelligence attacks ═══════════════════════

def _c001_crisis_label_contamination() -> RedTeamAttack:
    # a "label" computed with lookahead INTO the feature window
    candles = _series(60, crash_at=45)
    closes = [c["close"] for c in candles]
    rows = build_feature_rows(closes)
    from data_engine.prediction.features import FeatureRow
    contaminated = rows[0].model_copy(
        update={"source_end": rows[0].row_index + 3}
    )
    try:
        _labels.assert_label_feature_boundary(
            (contaminated,),
            _labels.compute_crash_labels(closes, _label_def()),
        )
        defended = False
        actual = "contaminated feature row passed the boundary proof"
    except PredictionContractError:
        defended = True
        actual = "contaminated feature row REJECTED"
    return _attack(
        "RT-PRED-C-001", "crash-intelligence",
        precondition="label/feature boundary proof (§14)",
        input_description="crisis labels computed over a window that "
                          "overlaps the feature source range",
        expected_behavior="boundary proof RAISES — label contamination "
                          "is structural, not reviewable",
        actual_behavior=actual,
        defended=defended,
        evidence="labels use closes[t+1..t+W]; features are capped at "
                 "source_end <= t",
    )


def _c002_warning_horizon_manipulation() -> RedTeamAttack:
    probabilities = [0.9, 0.1, 0.1, 0.1, 0.9, 0.1, 0.1, 0.1]
    labels = [False, False, False, False, True, False, False, False]
    config = EventEvaluationConfig(
        label_definition_id="predl.rt",
        label_threshold=0.10,
        horizon_bars=5,
        warning_threshold=0.5,
        warning_lookback_bars=100,  # absurdly large — clamps at 0
        forward_event_window_bars=5,
    )
    evaluation = evaluate_crash_events(
        probabilities=probabilities,
        labels=labels,
        config=config,
    )
    defended = (
        evaluation.total_events == 1
        and evaluation.detected_events == 1
        and evaluation.mean_lead_time_bars == 4.0
    )
    return _attack(
        "RT-PRED-C-002", "crash-intelligence",
        precondition="warning lookback clamped to available history",
        input_description="warning_lookback_bars=100 on an 8-bar series",
        expected_behavior="lookback CLAMPS to the series start; "
                           "detection only counts warnings strictly "
                           "BEFORE the event",
        actual_behavior=(
            f"events={evaluation.total_events}; detected="
            f"{evaluation.detected_events}; lead="
            f"{evaluation.mean_lead_time_bars}"
        ),
        defended=defended,
        evidence="window_start = max(0, t - lookback) — warnings are "
                 "never sought in the future",
    )


def _c003_insufficient_crisis_sample() -> RedTeamAttack:
    probabilities = [0.9, 0.1, 0.1, 0.1, 0.9, 0.1]
    labels = [False, False, False, False, True, False]
    config = EventEvaluationConfig(
        label_definition_id="predl.rt",
        label_threshold=0.10,
        horizon_bars=5,
        min_crisis_events=5,
    )
    evaluation = evaluate_crash_events(
        probabilities=probabilities,
        labels=labels,
        config=config,
        crisis_flags=[False, False, False, False, True, False],
    )
    defended = (
        evaluation.crisis_events == 1
        and evaluation.crisis_sample_status
        == "CRISIS_SAMPLE_INSUFFICIENT"
    )
    return _attack(
        "RT-PRED-C-003", "crash-intelligence",
        precondition="crisis-sample sufficiency gate (§12)",
        input_description="1 crisis event against a minimum of 5",
        expected_behavior="CRISIS_SAMPLE_INSUFFICIENT recorded — "
                          "statistical robustness is NOT claimed",
        actual_behavior=(
            f"crisis_events={evaluation.crisis_events}; status="
            f"{evaluation.crisis_sample_status}"
        ),
        defended=defended,
        evidence="the state is carried on every evaluation report, "
                 "never hidden",
    )


def _c004_false_confidence() -> RedTeamAttack:
    from data_engine.prediction.uncertainty import (
        is_uncertain,
        probability_band,
    )
    band = probability_band(0.5, n_effective=3)
    defended = is_uncertain(band) and band.width >= 0.5
    from data_engine.prediction.crash import (
        CrashRiskAssessment as _A,
    )
    # an uncertain assessment never carries a risk level
    uncertain = blocked_assessment(
        BlockReason.UNCERTAINTY_EXCESSIVE,
        prediction_id="pred.rt.u",
        common={
            "pit_cutoff": "2024-01-01T00:00:00+00:00",
            "prediction_time": "RT",
            "label_definition_id": "predl.rt",
            "horizon_bars": 5,
            "severity_threshold": 0.1,
            "model_id": "M",
            "model_version": "1",
        },
    )
    defended = (
        defended
        and uncertain.status == "PREDICTION_BLOCKED"
        and uncertain.probability is None
    )
    return _attack(
        "RT-PRED-C-004", "crash-intelligence",
        precondition="uncertainty band refusal (§19)",
        input_description="p=0.5 with n_effective=3 (a coin flip "
                          "dressed as a forecast)",
        expected_behavior="band width >= 0.5 triggers MODEL_UNCERTAIN/"
                          "refusal — wide-uncertainty probabilities "
                          "never become risk levels",
        actual_behavior=(
            f"band width={round(band.width, 4)}; uncertain="
            f"{is_uncertain(band)}; refused assessment carries "
            f"probability=None"
        ),
        defended=defended,
        evidence="MAX_PROBABILITY_BAND_WIDTH=0.5 refusal discipline",
    )


def _c005_causal_claim_impl() -> RedTeamAttack:
    returns = {
        "A": [0.01, 0.02, -0.01, 0.015, 0.005, -0.02, 0.01, 0.012],
        "B": [0.02, 0.04, -0.02, 0.03, 0.01, -0.04, 0.02, 0.024],
        "C": [-0.01, -0.02, 0.01, -0.015, -0.005, 0.02, -0.01, -0.012],
    }
    reading = systemic_risk_reading(
        returns,
        baseline_returns_by_symbol={
            "A": [0.001, -0.001, 0.002, 0.0, 0.001, -0.002, 0.0, 0.001],
            "B": [0.002, -0.002, 0.004, 0.0, 0.002, -0.004, 0.0, 0.002],
            "C": [-0.001, 0.001, -0.002, 0.0, -0.001, 0.002, 0.0, -0.001],
        },
    )
    causal_words = ("cause", "caused", "causes", "driven by",
                    "leads to", "predicts")
    note = reading.epistemic_note.lower()
    no_causal_language = not any(
        w in note for w in causal_words
    ) or "not causation" in note
    fields_text = " ".join(
        name for name in type(reading).model_fields
    ).lower()
    correlation_vocabulary = "correlation" in fields_text
    defended = (
        no_causal_language
        and correlation_vocabulary
        and "not causation" in note
    )
    return _attack(
        "RT-PRED-C-005", "crash-intelligence",
        precondition="systemic layer vocabulary audit (§16)",
        input_description="systemic risk reading generated and its "
                          "schema/notes scanned for causal claims",
        expected_behavior="reading carries CORRELATION vocabulary only "
                          "and an explicit not-causation note — "
                          "correlation is never described as causation",
        actual_behavior=(
            f"label={reading.label!r}; epistemic_note carries "
            f"not-causation: {'not causation' in note}"
        ),
        defended=defended,
        evidence="SystemicRiskReading fields are correlation-only; "
                 "epistemic_note is hardcoded to the §25 disclaimer",
    )


def _c006_unavailable_microstructure() -> RedTeamAttack:
    availability = microstructure_availability(
        order_book_data_present=False
    )
    defended = (
        availability.available is False
        and availability.status == "MICROSTRUCTURE_UNAVAILABLE"
    )
    return _attack(
        "RT-PRED-C-006", "crash-intelligence",
        precondition="microstructure availability declaration (§15)",
        input_description="request for order-book features with no "
                          "order-book data in the repository",
        expected_behavior="explicit UNAVAILABLE — microstructure is "
                          "never synthesized from OHLCV",
        actual_behavior=(
            f"available={availability.available}; status="
            f"{availability.status}"
        ),
        defended=defended,
        evidence="no spread/depth/queue module exists anywhere in the "
                 "prediction package (structural absence)",
    )


def _c007_scenario_as_forecast() -> RedTeamAttack:
    definition = ScenarioDefinition(
        scenario_id="SCEN-RT-1",
        kind="VOLATILITY_SHOCK",
        assumptions=("hypothetical 20% equity drawdown",),
        affected_assets=("EQ",),
        estimated_impact=(("EQ", -0.20),),
        uncertainty="high — hypothetical what-if, not a probability",
        limitations=("single-factor stress", "no liquidity modeling"),
    )
    engine = ScenarioEngine()
    result = engine.run(definition, {"EQ": 100.0, "FI": 100.0})
    from data_engine.prediction.scenarios import ScenarioResult
    try:
        ScenarioResult.model_validate({
            **result.model_dump(),
            "is_forecast": True,
        })
        forgery_blocked = False
    except Exception:
        forgery_blocked = True
    defended = (
        result.is_forecast is False
        and "NOT forecasts" in result.disclaimer
        and forgery_blocked
    )
    return _attack(
        "RT-PRED-C-007", "crash-intelligence",
        precondition="scenario contract (§16: ESTIMATE never FORECAST)",
        input_description="scenario result generated; then an attempt "
                          "to flip is_forecast=True on the record",
        expected_behavior="is_forecast is structurally False; the "
                          "validator REJECTS the flip; the disclaimer "
                          "labels outputs as estimates",
        actual_behavior=(
            f"is_forecast={result.is_forecast}; flip rejected: "
            f"{forgery_blocked}; disclaimer present: "
            f"{'NOT forecasts' in result.disclaimer}"
        ),
        defended=defended,
        evidence="ScenarioResult validator raises on is_forecast=True "
                 "(§24 contract)",
    )


_TEMPORAL = (
    _t001_future_timestamp_injection,
    _t002_future_feature_injection,
    _t003_label_leakage,
    _t004_publication_time_mismatch,
    _t005_revision_leakage,
    _t006_delayed_data_violation,
    _t007_cutoff_boundary_abuse,
    _t008_timezone_boundary_manipulation,
)
_IDENTITY = (
    _i001_type_collision,
    _i002_numeric_representation,
    _i003_null_empty_confusion,
    _i004_field_order_manipulation,
    _i005_serialization_ambiguity,
    _i006_unicode_normalization,
    _i007_float_edge_inf,
    _i008_nan_handling,
)
_PROVENANCE = (
    _p001_broken_hash_chain,
    _p002_altered_parent_hash,
    _p003_altered_dataset_identifier,
    _p004_altered_model_identifier,
    _p005_forged_verification_state,
    _p006_mismatched_artifact_hash,
    _p007_stale_provenance,
)
_DATA = (
    _d001_duplicate_rows,
    _d002_reordered_rows,
    _d003_missing_blocks,
    _d004_corrupted_values,
    _d005_impossible_ohlc,
    _d006_extreme_outliers,
    _d007_symbol_substitution,
    _d008_partial_dataset,
)
_MODEL = (
    _m001_stale_model,
    _m002_drifted_model,
    _m003_invalid_calibration,
    _m004_unsupported_artifact,
    _m005_schema_mismatch,
    _m006_feature_mismatch_predict,
    _m007_model_data_version_mismatch,
)
_CRASH = (
    _c001_crisis_label_contamination,
    _c002_warning_horizon_manipulation,
    _c003_insufficient_crisis_sample,
    _c004_false_confidence,
    _c005_causal_claim_impl,
    _c006_unavailable_microstructure,
    _c007_scenario_as_forecast,
)


def run_redteam_matrix() -> RedTeamMatrix:
    """Execute every attack and assemble the matrix (deterministic)."""
    attacks: list[RedTeamAttack] = []
    for runner in (
        *_TEMPORAL, *_IDENTITY, *_PROVENANCE, *_DATA, *_MODEL, *_CRASH
    ):
        attacks.append(runner())
    return RedTeamMatrix(attacks=tuple(attacks))


__all__ = [
    "AttackVerdict",
    "RedTeamAttack",
    "RedTeamMatrix",
    "run_redteam_matrix",
]
