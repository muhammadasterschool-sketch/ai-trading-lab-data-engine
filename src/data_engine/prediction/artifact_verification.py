"""Independent external-artifact verification (PRED-F3 closure, §14).

Prior defect (PRED-F3): the estimator hardcoded
``model_artifact_hash_match=True`` / ``input_hash_match=True`` —
caller-asserted flags that were never re-verified inside ``assess()``.

This module closes that gap. Verification is RECOMPUTED here from the
live artifact — a caller-provided ``verified=True`` is never trusted:

- artifact existence       — the object and its identity fields exist
- artifact hash            — recomputed from the artifact content and
                             compared against BOTH the declared hash and
                             any expected (registry) hash
- serialization integrity  — artifact survives a JSON round-trip with
                             an unchanged hash
- model/schema compatibility — feature-arity matches the schema the
                             estimator will feed (unconditional baselines
                             are compatible by contract)
- provenance metadata      — model identity fields are real, non-empty
- dataset compatibility    — declared dataset identity matches the
                             expected dataset identity when supplied
- model version            — non-empty, non-placeholder
- declared verification state — RE-DERIVED, never accepted

When the model exposes no ``artifact()`` method, independent
recomputation is architecturally impossible — the report records that
fact and ``verified`` is False (fail-closed) with the reason. That is
the documented boundary case the mandate allows ("formally document
why and implement the strongest possible boundary verification").
"""

from typing import Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.identity import (
    VERIFICATION_PREFIX,
    prefixed_hash,
)
from data_engine.prediction.models import ModelArtifact

#: Dataset-id placeholders that fail dataset-compatibility checks.
_DATASET_PLACEHOLDERS = frozenset({"", "DS-UNRECORDED", "UNRECORDED"})


class ArtifactVerificationReport(BaseModel):
    """Recomputed verification evidence for one model artifact (§14)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_exists: bool
    artifact_hash_recomputed: Optional[str] = None
    artifact_hash_declared: Optional[str] = None
    artifact_hash_expected: Optional[str] = None
    hash_self_consistent: Optional[bool] = None
    expected_hash_match: Optional[bool] = None
    serialization_integrity: Optional[bool] = None
    schema_compatible: Optional[bool] = None
    schema_detail: str = ""
    provenance_complete: bool = False
    dataset_compatible: Optional[bool] = None
    model_version_valid: bool = False
    failures: Tuple[str, ...] = ()
    notes: Tuple[str, ...] = ()

    @property
    def verified(self) -> bool:
        """True only when every recomputed check passed."""
        return (
            self.artifact_exists
            and self.hash_self_consistent is True
            and self.expected_hash_match is not False
            and self.serialization_integrity is True
            and self.schema_compatible is not False
            and self.provenance_complete
            and self.dataset_compatible is not False
            and self.model_version_valid
            and not self.failures
        )

    @property
    def verification_hash(self) -> str:
        return prefixed_hash(
            VERIFICATION_PREFIX,
            {
                "kind": "artifact_verification",
                "artifact_exists": self.artifact_exists,
                "artifact_hash_recomputed": self.artifact_hash_recomputed,
                "artifact_hash_declared": self.artifact_hash_declared,
                "artifact_hash_expected": self.artifact_hash_expected,
                "hash_self_consistent": self.hash_self_consistent,
                "expected_hash_match": self.expected_hash_match,
                "serialization_integrity": self.serialization_integrity,
                "schema_compatible": self.schema_compatible,
                "provenance_complete": self.provenance_complete,
                "dataset_compatible": self.dataset_compatible,
                "model_version_valid": self.model_version_valid,
                "failures": list(self.failures),
            },
        )


def verify_model_artifact(
    model,
    *,
    expected_hash: Optional[str] = None,
    expected_feature_count: Optional[int] = None,
    expected_dataset_id: Optional[str] = None,
    declared_dataset_id: Optional[str] = None,
) -> ArtifactVerificationReport:
    """Independently re-verify a model artifact from its live content.

    ``model`` must satisfy the estimator's duck-typed contract
    (``model_id`` / ``model_version`` / ``model_hash``); models that
    additionally expose ``artifact()`` get FULL recomputation
    (hash + serialization + schema). Models without ``artifact()``
    cannot be independently verified — the report says so and
    ``verified`` is False (fail-closed).
    """
    failures: list[str] = []
    notes: list[str] = []

    # 1. Existence ---------------------------------------------------------
    exists = (
        model is not None
        and hasattr(model, "model_id")
        and hasattr(model, "model_version")
        and hasattr(model, "model_hash")
    )
    if not exists:
        failures.append(
            "model artifact does not satisfy the identity contract "
            "(model_id/model_version/model_hash)"
        )
        return ArtifactVerificationReport(
            artifact_exists=False,
            failures=tuple(failures),
        )

    model_id = getattr(model, "model_id")
    model_version = getattr(model, "model_version")
    declared_hash = getattr(model, "model_hash")

    # 2. Provenance metadata -------------------------------------------------
    provenance_complete = (
        isinstance(model_id, str) and model_id.strip() != ""
        and isinstance(model_version, str) and model_version.strip() != ""
        and isinstance(declared_hash, str) and declared_hash.strip() != ""
    )
    if not provenance_complete:
        failures.append(
            f"model identity fields incomplete: id={model_id!r} "
            f"version={model_version!r} hash={declared_hash!r}"
        )

    # 3. Version validity -----------------------------------------------------
    version_valid = (
        isinstance(model_version, str)
        and model_version.strip() != ""
        and model_version not in _DATASET_PLACEHOLDERS
    )
    if not version_valid:
        failures.append(f"model version invalid: {model_version!r}")

    # 4. Hash recomputation (only possible with an artifact()) ----------------
    recomputed: Optional[str] = None
    hash_self_consistent: Optional[bool] = None
    serialization_integrity: Optional[bool] = None
    schema_compatible: Optional[bool] = None
    schema_detail = ""
    artifact_method = getattr(model, "artifact", None)
    if artifact_method is None or not callable(artifact_method):
        failures.append(
            "model exposes no artifact() — independent hash "
            "recomputation is architecturally impossible; refusing to "
            "trust the declared hash (fail-closed)"
        )
        notes.append(
            "documented boundary: without artifact() the strongest "
            "possible verification is identity-field validation, which "
            "does not establish content integrity"
        )
    else:
        try:
            artifact: ModelArtifact = artifact_method()
        except Exception as exc:  # noqa: BLE001 — fail-closed by design
            failures.append(f"artifact() raised {exc!r}")
            artifact = None  # type: ignore[assignment]
        if artifact is not None:
            try:
                recomputed = artifact.model_hash
            except Exception as exc:  # noqa: BLE001
                failures.append(f"artifact hash recomputation failed: {exc!r}")
                recomputed = None
            if recomputed is not None:
                hash_self_consistent = recomputed == declared_hash
                if not hash_self_consistent:
                    failures.append(
                        "declared model_hash does not match the "
                        "recomputed artifact hash — tampered or stale "
                        "artifact"
                    )

                # 5. Serialization integrity (JSON round-trip) ---------------
                try:
                    round_tripped = ModelArtifact.model_validate_json(
                        artifact.model_dump_json()
                    )
                    serialization_integrity = (
                        round_tripped.model_hash == recomputed
                    )
                    if not serialization_integrity:
                        failures.append(
                            "artifact failed the JSON round-trip with a "
                            "stable hash — serialization ambiguity"
                        )
                except Exception as exc:  # noqa: BLE001
                    serialization_integrity = False
                    failures.append(
                        f"artifact serialization round-trip failed: {exc!r}"
                    )

                # 6. Schema compatibility ------------------------------------
                n_features = len(artifact.feature_names)
                if expected_feature_count is None:
                    schema_compatible = True
                    schema_detail = "no expected schema supplied"
                elif n_features == 0:
                    schema_compatible = True
                    schema_detail = (
                        "unconditional baseline (consumes no features) — "
                        "compatible by contract"
                    )
                elif n_features == expected_feature_count:
                    schema_compatible = True
                    schema_detail = (
                        f"artifact consumes {n_features} features, "
                        f"matching the expected schema"
                    )
                else:
                    schema_compatible = False
                    schema_detail = (
                        f"artifact consumes {n_features} features, "
                        f"estimator will supply {expected_feature_count}"
                    )
                    failures.append(
                        "model/schema incompatibility: " + schema_detail
                    )

    # 7. Expected-hash match (registry-bound artifacts) ------------------------
    expected_hash_match: Optional[bool] = None
    if expected_hash is not None:
        reference = recomputed if recomputed is not None else declared_hash
        expected_hash_match = reference == expected_hash
        if not expected_hash_match:
            failures.append(
                f"expected model hash {expected_hash!r} does not match "
                f"the artifact ({reference!r}) — stale or substituted "
                "artifact"
            )

    # 8. Dataset compatibility --------------------------------------------------
    dataset_compatible: Optional[bool] = None
    if expected_dataset_id is not None:
        dataset_compatible = declared_dataset_id == expected_dataset_id
        if not dataset_compatible:
            failures.append(
                f"model declares dataset {declared_dataset_id!r} but the "
                f"expected dataset is {expected_dataset_id!r} — "
                "model/data version mismatch"
            )

    return ArtifactVerificationReport(
        artifact_exists=True,
        artifact_hash_recomputed=recomputed,
        artifact_hash_declared=(
            declared_hash if isinstance(declared_hash, str) else None
        ),
        artifact_hash_expected=expected_hash,
        hash_self_consistent=hash_self_consistent,
        expected_hash_match=expected_hash_match,
        serialization_integrity=serialization_integrity,
        schema_compatible=schema_compatible,
        schema_detail=schema_detail,
        provenance_complete=provenance_complete,
        dataset_compatible=dataset_compatible,
        model_version_valid=version_valid,
        failures=tuple(failures),
        notes=tuple(notes),
    )


def verify_input_snapshot(
    closes: Sequence[float],
    dropped_future_bars: int,
    dropped_revision_bars: int,
    *,
    expected_hash: Optional[str] = None,
) -> ArtifactVerificationReport:
    """Re-verify the estimator's input snapshot hash (boundary check).

    The snapshot payload is recomputed INDEPENDENTLY twice (two
    construction passes) — divergence is a determinism failure. When an
    ``expected_hash`` is supplied (e.g. recorded by a prior run) the
    recomputation must match it exactly.
    """
    def _snapshot_payload() -> dict:
        return {
            "kind": "input_snapshot",
            "closes": [round(float(c), 12) for c in closes],
            "dropped_future_bars": dropped_future_bars,
            "dropped_revision_bars": dropped_revision_bars,
        }

    failures: list[str] = []
    recomputed = prefixed_hash("predv.", _snapshot_payload())
    recomputed_again = prefixed_hash("predv.", _snapshot_payload())
    self_consistent = recomputed == recomputed_again
    if not self_consistent:
        failures.append(
            "input snapshot hash is non-deterministic across two "
            "independent computations"
        )
    expected_match: Optional[bool] = None
    if expected_hash is not None:
        expected_match = recomputed == expected_hash
        if not expected_match:
            failures.append(
                f"input snapshot hash {recomputed!r} does not match the "
                f"expected {expected_hash!r} — input substitution"
            )
    return ArtifactVerificationReport(
        artifact_exists=True,
        artifact_hash_recomputed=recomputed,
        hash_self_consistent=self_consistent,
        expected_hash_match=expected_match,
        serialization_integrity=True,
        schema_compatible=None,
        schema_detail="input snapshot",
        provenance_complete=True,
        model_version_valid=True,
        failures=tuple(failures),
        notes=("recomputed from visible bars inside assess()",),
    )


__all__ = [
    "ArtifactVerificationReport",
    "verify_model_artifact",
    "verify_input_snapshot",
]
