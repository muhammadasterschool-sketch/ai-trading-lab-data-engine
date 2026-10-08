"""Prediction Intelligence acceptance tests — scenarios, risk
integration, systemic risk, stress, microstructure, frozen Phase 3.

Mandate test-matrix coverage (§47):

- T-PRED-025  scenario isolation (scenarios are not forecasts)
- T-PRED-026  risk integration (hard limits never exceeded)
- T-PRED-027  kill-switch interaction
- T-PRED-028  frozen Phase 3 protection (13-file manifest + H-1
              independence of the prediction layer)
"""

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from data_engine.prediction.crash import CrashRiskAssessment
from data_engine.prediction.microstructure import (
    microstructure_availability,
)
from data_engine.prediction.risk_integration import (
    prediction_risk_decision,
)
from data_engine.risk.engine import RiskLimits
from data_engine.prediction.scenarios import (
    ScenarioDefinition,
    ScenarioEngine,
)
from data_engine.prediction.stress import classify_market_stress
from data_engine.prediction.systemic import (
    correlation_matrix,
    systemic_risk_reading,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


# ─── T-PRED-025: scenario isolation ───


def make_scenario():
    return ScenarioDefinition(
        scenario_id="SCN-GAPDOWN-1",
        kind="GAP_DOWN",
        assumptions=("overnight gap of >= 10% on the index",),
        affected_assets=("EQUITY_INDEX",),
        estimated_impact=(("EQUITY_INDEX", -0.10), ("BOND_FUTURES", 0.02)),
        uncertainty="impact magnitude estimated from historical gaps",
        limitations=("single-factor estimate; no liquidity cascade modeled",),
        inputs=(("gap_magnitude", 0.10),),
    )


def test_t_pred_025_scenario_run_is_isolated_and_pure():
    engine = ScenarioEngine()
    exposures = {"EQUITY_INDEX": 1000.0, "BOND_FUTURES": 500.0}
    snapshot = dict(exposures)
    result = engine.run(make_scenario(), exposures)
    # the caller's mapping is untouched (isolation, §24/T-PRED-025)
    assert exposures == snapshot
    # pure function: repeated run is identical
    assert engine.run(make_scenario(), exposures) == result


def test_t_pred_025_scenario_results_are_not_forecasts():
    result = ScenarioEngine().run(
        make_scenario(), {"EQUITY_INDEX": 1000.0, "BOND_FUTURES": 500.0}
    )
    assert result.is_forecast is False
    assert "NOT forecasts" in result.disclaimer
    assert result.estimated_exposures == (
        ("BOND_FUTURES", 510.0),
        ("EQUITY_INDEX", 900.0),
    )
    assert result.total_estimated_exposure == pytest.approx(1410.0)


def test_t_pred_025_scenario_contracts_fail_closed():
    with pytest.raises(ValueError):
        ScenarioDefinition(
            scenario_id="X", kind="NOT_A_KIND",
            assumptions=("a",), affected_assets=("A",),
            estimated_impact=(("A", -0.1),), uncertainty="u",
            limitations=("l",),
        )
    with pytest.raises(ValueError):
        ScenarioDefinition(
            scenario_id="X", kind="GAP_DOWN",
            assumptions=(),  # hidden assumptions are forbidden (§24)
            affected_assets=("A",),
            estimated_impact=(("A", -0.1),), uncertainty="u",
            limitations=("l",),
        )
    with pytest.raises(Exception):
        ScenarioEngine().run(make_scenario(), {})


# ─── T-PRED-026: risk integration ───


LIMITS = RiskLimits(
    max_position_units=Decimal("100"),
    max_leverage=Decimal("2"),
    max_single_asset_weight=Decimal("0.20"),
    max_sector_weight=Decimal("0.40"),
    max_portfolio_heat=Decimal("0.02"),
)


def assessment_with(status: str, probability=0.3) -> CrashRiskAssessment:
    return CrashRiskAssessment(
        prediction_id="pred." + "0" * 64,
        status=status,
        probability=probability,
        horizon_bars=20,
        severity_threshold=0.20,
        confidence="calibrated",
        evidence_score=0.8,
        evidence_status="OK",
        regime="NORMAL",
        label_definition_id="predl." + "0" * 64,
        model_id="M",
        model_version="1",
        pit_cutoff="2020-01-01T00:00:00+00:00",
        prediction_time="2020-01-02T00:00:00+00:00",
    )


def test_t_pred_026_hard_limits_are_never_exceeded():
    for status in ("LOW_RISK", "ELEVATED_RISK", "HIGH_RISK", "EXTREME_RISK"):
        decision = prediction_risk_decision(
            assessment_with(status), LIMITS
        )
        assert decision.proposed_max_position_units <= LIMITS.max_position_units
        assert decision.proposed_risk_budget_fraction <= LIMITS.max_portfolio_heat
        assert decision.authority == "RISK_ENGINE"
        assert decision.source == "PREDICTION"


def test_t_pred_026_sizing_scales_with_risk_level():
    low = prediction_risk_decision(assessment_with("LOW_RISK"), LIMITS)
    extreme = prediction_risk_decision(assessment_with("EXTREME_RISK"), LIMITS)
    assert low.sizing_multiplier == Decimal("1.00")
    assert extreme.sizing_multiplier == Decimal("0.25")
    assert extreme.proposed_max_position_units == Decimal("25")


def test_t_pred_026_refused_predictions_produce_no_sizing_input():
    for status in ("PREDICTION_BLOCKED", "MODEL_UNCERTAIN",
                   "EVIDENCE_INSUFFICIENT"):
        decision = prediction_risk_decision(
            assessment_with(status), LIMITS
        )
        assert decision.action == "NO_TRADE"
        assert decision.proposed_max_position_units == Decimal("0")
        assert decision.proposed_risk_budget_fraction == Decimal("0")
        assert decision.suppressed_reason is not None


# ─── T-PRED-027: kill-switch interaction ───


def test_t_pred_027_kill_switch_suppresses_all_prediction_input():
    decision = prediction_risk_decision(
        assessment_with("LOW_RISK"), LIMITS, kill_switch_active=True
    )
    assert decision.action == "NO_TRADE"
    assert decision.suppressed is True
    assert decision.proposed_max_position_units == Decimal("0")
    assert decision.proposed_risk_budget_fraction == Decimal("0")
    assert "kill switch" in (decision.suppressed_reason or "")


def test_t_pred_027_kill_switch_wins_even_at_extreme_risk():
    decision = prediction_risk_decision(
        assessment_with("EXTREME_RISK", probability=0.9),
        LIMITS,
        kill_switch_active=True,
    )
    assert decision.suppressed is True
    assert decision.proposed_max_position_units == Decimal("0")


# ─── systemic risk / stress / microstructure (§22, §25, §4E) ───


def _independent_series(seed, n=50):
    import random

    rng = random.Random(seed)
    return [rng.random() - 0.5 for _ in range(n)]


def _correlated_series(common, seeds, noise_scale=0.01):
    """Series driven by one common market factor + tiny idiosyncratic
    noise -> pairwise correlations near 1 (a stress/correlation regime)."""
    import random

    out = {}
    for symbol_seed in seeds:
        rng = random.Random(symbol_seed)
        out[f"SYM{symbol_seed}"] = [
            factor + noise_scale * (rng.random() - 0.5)
            for factor in common
        ]
    return out


def test_correlation_matrix_is_symmetric_and_bounded():
    returns = {
        "AAA": _independent_series(1),
        "BBB": _independent_series(1),   # identical series -> rho = 1
        "CCC": _independent_series(2),
    }
    matrix = correlation_matrix(returns)
    pairs = {(a, b): rho for a, b, rho in matrix}
    assert pairs[("AAA", "BBB")] == pytest.approx(1.0)
    for rho in pairs.values():
        assert -1.0000001 <= rho <= 1.0000001


def test_systemic_reading_measures_and_disclaims_causality():
    stressed = _correlated_series(
        _independent_series(9), seeds=(1, 2, 3, 4)
    )
    calm = {f"CALM{i}": _independent_series(100 + i) for i in range(4)}
    reading = systemic_risk_reading(
        stressed, baseline_returns_by_symbol=calm, spike_margin=0.15
    )
    assert reading.average_correlation == pytest.approx(1.0, abs=0.01)
    assert reading.correlation_spike is True
    assert reading.label in {"HIGH_RISK", "EXTREME_RISK"}
    assert "not causation" in reading.epistemic_note


def test_zero_variance_series_is_rejected_not_guessed():
    with pytest.raises(Exception):
        correlation_matrix(
            {"FLAT": [0.5] * 10, "OTHER": _independent_series(3)}
        )


def test_market_stress_classification_bands():
    assert classify_market_stress(vol_20=0.045, dd_depth=0.25).state == "EXTREME"
    assert classify_market_stress(vol_20=0.020, dd_depth=0.16).state == "SEVERE"
    assert classify_market_stress(vol_20=0.031, dd_depth=0.05).state == "STRESSED"
    assert classify_market_stress(vol_20=0.021, dd_depth=0.04).state == "ELEVATED"
    assert classify_market_stress(vol_20=0.010, dd_depth=0.01).state == "NORMAL"
    assert classify_market_stress(vol_20=None, dd_depth=0.1).state == "UNKNOWN"


def test_microstructure_unavailable_is_explicit():
    reading = microstructure_availability(order_book_data_present=False)
    assert reading.status == "MICROSTRUCTURE_UNAVAILABLE"
    assert "never synthesized" in reading.reason


# ─── T-PRED-028: frozen Phase 3 protection ───

#: Mirrors the SUB-18 committed-state manifest (tests/test_pit_view.py).
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


def test_t_pred_028_frozen_phase3_manifest_unchanged():
    """T-PRED-028: the frozen Phase 3 manifest (SUB-18 pins) is
    byte-identical after the prediction-intelligence construction. The
    prediction layer is additive only — no frozen file was touched."""
    mismatches = []
    for rel_path, expected in _FROZEN_PHASE3_MANIFEST.items():
        file_path = REPO_ROOT / rel_path
        assert file_path.exists(), f"frozen file missing: {rel_path}"
        actual = hashlib.sha256(file_path.read_bytes()).hexdigest()
        if actual != expected:
            mismatches.append(rel_path)
    assert mismatches == [], f"frozen Phase 3 modified: {mismatches}"


def test_t_pred_028_prediction_package_is_additive_only():
    """No prediction-layer file is part of the frozen manifest, and the
    prediction layer never calls a frozen Phase 3 hash method (H-1
    independence, mandate §53)."""
    prediction_dir = REPO_ROOT / "src" / "data_engine" / "prediction"
    files = sorted(prediction_dir.glob("*.py"))
    assert len(files) >= 20, "prediction package incomplete"
    for file_path in files:
        rel = file_path.relative_to(REPO_ROOT).as_posix()
        assert rel not in _FROZEN_PHASE3_MANIFEST, (
            f"prediction file unexpectedly frozen: {rel}"
        )
        source = file_path.read_text()
        assert ".to_hash(" not in source, (
            f"{rel} must not invoke frozen Phase 3 hash methods (H-1)"
        )
