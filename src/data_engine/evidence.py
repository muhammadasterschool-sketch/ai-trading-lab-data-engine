"""Evidence integrity module for the AI Trading Lab Data Engine.

Every dataset must explicitly identify its provenance:
- REAL: documented source provenance
- SYNTHETIC: generated data, must not be represented as REAL
- SIMULATED: simulated data
- UNKNOWN: unknown provenance, cannot be treated as strong evidence

The LLM must NOT change provenance labels.
"""

from enum import Enum
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, UTC
from typing import Optional, List, Dict


class EvidenceProvenance(str, Enum):
    REAL = "REAL"
    SYNTHETIC = "SYNTHETIC"
    SIMULATED = "SIMULATED"
    UNKNOWN = "UNKNOWN"

    def is_strong_evidence(self) -> bool:
        """Only REAL with documented source is strong evidence."""
        return self == EvidenceProvenance.REAL

    def is_valid_for_research(self) -> bool:
        """UNKNOWN cannot be treated as strong research evidence."""
        return self != EvidenceProvenance.UNKNOWN

    def is_fabrication_risk(self) -> bool:
        """SYNTHETIC and SIMULATED must not be represented as REAL."""
        return self in (EvidenceProvenance.SYNTHETIC, EvidenceProvenance.SIMULATED)


class EvidenceLabel(BaseModel):
    """Explicit evidence label for a dataset."""
    provenance: EvidenceProvenance
    source_documentation: Optional[str] = None
    labeling_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    labeled_by: str = "system"
    notes: Optional[str] = None
    is_override: bool = False  # Can LLM override this? NO.

    @field_validator("provenance", mode="before")
    @classmethod
    def validate_provenance(cls, v):
        if isinstance(v, str):
            return EvidenceProvenance(v)
        return v

    def assert_not_fabrication(self):
        """Raise if provenance indicates potential fabrication."""
        if self.provenance == EvidenceProvenance.SYNTHETIC:
            raise ValueError(
                "SYNTHETIC data must not be represented as REAL market data. "
                "Label this dataset as SYNTHETIC and treat accordingly."
            )

    def assert_strong_evidence(self):
        """Raise if provenance does not support strong evidence claims."""
        if not self.provenance.is_strong_evidence():
            raise ValueError(
                f"Provenance {self.provenance.value} cannot be treated as strong evidence. "
                f"Only REAL with documented source qualifies."
            )

    def to_dict(self) -> Dict:
        return {
            "provenance": self.provenance.value,
            "source_documentation": self.source_documentation,
            "labeling_timestamp": self.labeling_timestamp.isoformat(),
            "labeled_by": self.labeled_by,
            "notes": self.notes,
            "is_override": self.is_override,
        }


# Evidence propagation rules
EVIDENCE_PROPAGATION_RULES = {
    "dataset": "provenance",
    "backtest": "dataset_provenance",
    "research_report": "dataset_provenance",
    "quant_result": "dataset_provenance",
    "strategy_evaluation": "dataset_provenance",
}


def propagate_evidence(source_label: EvidenceLabel, operation: str) -> EvidenceLabel:
    """Propagate evidence provenance to downstream operations.

    The provenance cannot be upgraded. It can only stay the same or be
    explicitly flagged with additional context.
    """
    # Provenance cannot be changed by downstream operations
    if source_label.provenance == EvidenceProvenance.SYNTHETIC and operation != "synthetic_test":
        raise ValueError(
            f"Cannot propagate SYNTHETIC data to {operation}. "
            f"Synthetic data must remain labeled as SYNTHETIC."
        )
    if source_label.provenance == EvidenceProvenance.UNKNOWN:
        return EvidenceLabel(
            provenance=EvidenceProvenance.UNKNOWN,
            source_documentation=source_label.source_documentation,
            labeled_by="downstream_system",
            notes=f"UNKNOWN provenance propagated through {operation}. "
                  f"Cannot be treated as strong evidence.",
        )
    return source_label


def check_evidence_integrity(datasets: list) -> list:
    """Check evidence integrity across multiple datasets.

    Returns list of integrity violations.
    """
    violations = []
    for dataset in datasets:
        prov = getattr(dataset, "provenance", None)
        if prov and prov.evidence_provenance == EvidenceProvenance.UNKNOWN:
            violations.append(
                f"Dataset {dataset.dataset_id}: UNKNOWN provenance. "
                f"Cannot be treated as strong research evidence."
            )
        if prov and prov.evidence_provenance == EvidenceProvenance.SYNTHETIC:
            violations.append(
                f"Dataset {dataset.dataset_id}: SYNTHETIC provenance. "
                f"Must not be represented as REAL."
            )
    return violations
