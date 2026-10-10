"""BUG-008 residual closure tests (operator decision GOV-B08-001,
2026-10-10 — permanent acceptance of the runtime-boundary adapter).

The accepted contract (BUG008_RESIDUAL_RESOLUTION_RECORD.md §3):

1. The 13 deferred mutable fields (9 strategy-domain + 4
   manifest-pinned schemas.py fields — documented in the P2 re-audit)
   stay mutable inside the frozen domain BY RULE; the acceptance
   NEVER alters the frozen files (byte-identity still proven).
2. The runtime NEVER mutates them: strategy-domain objects crossing
   into the runtime are deep-copied into read-only snapshots by
   ``freeze_strategy_boundary``.
3. The runtime package is structurally DECOUPLED from the frozen
   strategy domain — no runtime module imports it at all (the
   vocabulary bridge is the sanctioned translation surface, and it
   translates via paper models, not frozen models).

These tests pin all three properties with regression force:

- ``TestDeferredFieldEnumeration`` — dynamically DISCOVERS the
  mutable-container fields across the frozen domain and pins the exact
  13-element set. If anyone edits a frozen file to make a field
  immutable (a frozen-contract violation), or adds a new mutable
  field without governance, this pin breaks.
- ``TestBoundaryIsolation`` — mutation isolation in BOTH directions
  through ``freeze_strategy_boundary``.
- ``TestRuntimeDecoupling`` — source-scan: no runtime module imports
  ``data_engine.strategy`` or ``data_engine.schemas``; the frozen
  files remain byte-identical to their pinned references.
"""

import importlib
import inspect
import pkgutil
import subprocess
from pathlib import Path

import pytest

from data_engine.runtime import freeze_strategy_boundary

REPO = Path(__file__).resolve().parents[1]


# ════════════════════════════════════════════════════════════════════
# 1. The 13 deferred fields — dynamically discovered, exactly pinned
# ════════════════════════════════════════════════════════════════════

def _discover_mutable_fields():
    """Recursive discovery of mutable-container fields on pydantic
    models across the frozen domain (strategy package + schemas.py).

    Enum/frozenset annotations are excluded (immutable by type). The
    result is the regression pin — it must equal the documented 13
    (P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md BUG-008 row:
    strategy x9 + schemas.py x4)."""
    from pydantic import BaseModel

    seen, found = set(), {}

    def is_mutable_container(finfo):
        ann = str(finfo.annotation).lower()
        if "enum" in ann or "frozenset" in ann:
            return False
        return ("dict" in ann or "list" in ann or "set[" in ann
                or "mapping" in ann or "sequence" in ann)

    def scan_model(cls, path):
        if cls in seen:
            return
        seen.add(cls)
        for fname, finfo in cls.model_fields.items():
            ann = finfo.annotation
            if (isinstance(ann, type) and issubclass(ann, BaseModel)
                    and ann is not cls):
                scan_model(ann, f"{path}.{fname}")
            if is_mutable_container(finfo):
                found[f"{path}.{fname}"] = str(finfo.annotation)
            for arg in (getattr(ann, "__args__", None) or ()):
                if isinstance(arg, type) and issubclass(arg, BaseModel):
                    scan_model(arg, f"{path}.{fname}")

    def scan_module(module_name):
        module = importlib.import_module(module_name)
        for _name, obj in inspect.getmembers(module, inspect.isclass):
            if (isinstance(obj, type) and issubclass(obj, BaseModel)
                    and obj.__module__ == module_name):
                scan_model(obj, f"{module_name}::{obj.__name__}")

    import data_engine.strategy as strategy_pkg
    for mod in pkgutil.iter_modules(strategy_pkg.__path__):
        scan_module(f"data_engine.strategy.{mod.name}")
    scan_module("data_engine.schemas")
    return found


#: The documented deferred-field set (P2 BUG-008 row: 9 + 4 = 13).
DOCUMENTED_DEFERRED_FIELDS = frozenset({
    # schemas.py x4 (SUB-18 manifest-pinned)
    "data_engine.schemas::Dataset.candles",
    "data_engine.schemas::Dataset.provenance.transformation_history",
    "data_engine.schemas::ProviderConfig.instrument_allowlist",
    "data_engine.schemas::ValidationResult.details",
    # frozen strategy domain x9
    "data_engine.strategy.backtest::BacktestResult.config",
    "data_engine.strategy.backtest::BacktestResult.equity_curve.equity_curve",
    "data_engine.strategy.backtest::BacktestResult.provenance.cost_parameters",
    "data_engine.strategy.backtest::BacktestResult.provenance.position_sizing_parameters",
    "data_engine.strategy.backtest::BacktestResult.provenance.slippage_parameters",
    "data_engine.strategy.backtest::BacktestResult.trades.trades",
    "data_engine.strategy.conditions::Signal.conditions_met",
    "data_engine.strategy.schemas::StrategySpec.required_indicators",
    "data_engine.strategy.validation::ValidationIssue.details",
})


class TestDeferredFieldEnumeration:
    def test_discovered_set_equals_documented_thirteen(self):
        discovered = _discover_mutable_fields()
        assert set(discovered) == set(DOCUMENTED_DEFERRED_FIELDS), (
            "The frozen-domain mutable-field profile CHANGED — either a "
            "frozen file was modified (violation) or the enumeration "
            f"drifted. Discovered: {sorted(discovered)}"
        )
        assert len(DOCUMENTED_DEFERRED_FIELDS) == 13

    def test_deferred_fields_remain_mutable_by_rule(self):
        """The accepted containment explicitly does NOT freeze these
        fields in place — mutating a constructed frozen-domain model
        must still WORK (the runtime just never does it). This pins the
        rule-deferred state honestly (no hidden frozen-file edit)."""
        from data_engine.strategy.conditions import Signal
        signal = Signal(timestamp=1.0, signal_type="ENTRY",
                        conditions_met=["c1"])
        signal.conditions_met.append("c2")  # still mutable — BY RULE
        assert signal.conditions_met == ["c1", "c2"]


# ════════════════════════════════════════════════════════════════════
# 2. Boundary isolation (the accepted containment mechanism)
# ════════════════════════════════════════════════════════════════════

class TestBoundaryIsolation:
    def _frozen_domain_object(self):
        from data_engine.schemas import Dataset, DatasetVersion
        return Dataset(
            version=DatasetVersion(),
            candles=[],  # populated via model_construct-free path
        )

    def test_snapshot_is_deep_isolated_from_original(self):
        original = {"meta": {"nested": [1, 2, 3]},
                    "fields": {"a": {"deep": True}}}
        snapshot = freeze_strategy_boundary(original)
        # Mutating the SNAPSHOT never reaches the original.
        snapshot["meta"]["nested"].append(99)
        snapshot["fields"]["a"]["deep"] = False
        assert original["meta"]["nested"] == [1, 2, 3]
        assert original["fields"]["a"]["deep"] is True

    def test_mutating_original_never_reaches_snapshot(self):
        original = {"meta": {"nested": [1, 2, 3]}}
        snapshot = freeze_strategy_boundary(original)
        original["meta"]["nested"].append(99)
        assert snapshot["meta"]["nested"] == [1, 2, 3]

    def test_pydantic_model_snapshot_carries_deferred_fields(self):
        from data_engine.strategy.conditions import Signal
        signal = Signal(timestamp=1.0, signal_type="ENTRY",
                        conditions_met=["c1"])
        snapshot = freeze_strategy_boundary(signal)
        # The deferred mutable field rides along in the snapshot...
        assert snapshot["conditions_met"] == ["c1"]
        # ...and mutating the snapshot cannot touch the frozen-domain
        # object.
        snapshot["conditions_met"].append("c2")
        assert signal.conditions_met == ["c1"]

    def test_boundary_requires_a_model(self):
        from data_engine.runtime.vocabulary import VocabularyError
        with pytest.raises(VocabularyError):
            freeze_strategy_boundary(None)


# ════════════════════════════════════════════════════════════════════
# 3. Structural decoupling + frozen byte-identity
# ════════════════════════════════════════════════════════════════════

class TestRuntimeDecoupling:
    def test_no_runtime_module_imports_frozen_domain(self):
        """The runtime package is structurally decoupled from the
        frozen strategy domain — the sanctioned crossing surface is
        the vocabulary bridge (which translates via paper models) and
        freeze_strategy_boundary (which deep-copies). No runtime
        module may import the frozen models directly."""
        runtime_dir = REPO / "src/data_engine/runtime"
        offenders = []
        for path in runtime_dir.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            for forbidden in (
                "from data_engine.strategy",
                "import data_engine.strategy",
                "from data_engine.schemas",
                "import data_engine.schemas",
            ):
                if forbidden in source:
                    offenders.append(f"{path.name}: {forbidden}")
        assert not offenders, (
            "runtime modules must not import the frozen strategy "
            f"domain directly: {offenders}"
        )

    def test_frozen_strategy_package_byte_identical_to_reference(self):
        """The whole frozen strategy package is byte-identical to the
        frozen reference commit (the acceptance altered nothing)."""
        result = subprocess.run(
            ["git", "diff", "--quiet", "13fdc7e", "--",
             "src/data_engine/strategy"],
            cwd=str(REPO), capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            "src/data_engine/strategy differs from the frozen reference "
            "13fdc7e — frozen-contract violation"
        )

    def test_schemas_py_matches_sub18_manifest_pin(self):
        """schemas.py is pinned by the SUB-18 manifest (not by the
        13fdc7e reference) — verify its sha256 against the manifest
        recorded in PHASE_4A1_IMPLEMENTATION_RECORD.md."""
        import hashlib
        import re
        record = (REPO / "PHASE_4A1_IMPLEMENTATION_RECORD.md").read_text(
            encoding="utf-8")
        manifest_block = re.search(
            r"```(?:\w+)?\n([0-9a-f]{64}  [^\n]+\n)+```", record)
        assert manifest_block, "SUB-18 manifest block not found"
        pinned = None
        for line in manifest_block.group(0).splitlines():
            match = re.match(r"^([0-9a-f]{64})  (\S+)$", line.strip())
            if match and match.group(2).endswith("schemas.py") \
                    and "strategy" not in match.group(2):
                pinned = match.group(1)
        assert pinned, "schemas.py not found in SUB-18 manifest"
        actual = hashlib.sha256(
            (REPO / "src/data_engine/schemas.py").read_bytes()
        ).hexdigest()
        assert actual == pinned, (
            "src/data_engine/schemas.py sha256 drifted from the SUB-18 "
            "manifest pin — frozen-contract violation"
        )
