"""Phase 4A.1 — TemporalContract for PIT data validation.

Defines the temporal contract that all PIT data items must satisfy.
The contract specifies required temporal fields, eligible fields,
non-eligible fields, availability controls, missing-field policies,
and timezone requirements.

The trusted research boundary must reject missing required timestamps.
No Phase 3 model (Candle, etc.) is modified by this contract.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator
from enum import Enum
from typing import Optional, Literal
from datetime import datetime, UTC
from data_engine.pit.temporal import TemporalDataType
from data_engine.pit.serialization import canonical_serialize
from data_engine.pit.hashing import deterministic_hash
from data_engine.pit.availability import AvailabilityPolicy


class MissingFieldPolicy(str, Enum):
    """How to handle missing temporal fields."""
    REJECT = "reject"       # Raise validation error
    ALLOW_NULL = "allow_null"  # Allow None values
    REQUIRE_NON_NULL = "require_non_null"  # Must have a value


class TemporalContract(BaseModel):
    """Temporal contract defining required and eligible temporal fields.

    The contract is immutable (frozen) and defines what temporal
    fields are required, eligible, non-eligible, and how availability
    is controlled for a given TemporalDataType.

    Attributes:
        data_type: The canonical data type category.
        required_fields: Fields that MUST be present and non-null.
        eligible_fields: Fields that MAY be present and participate
            in PIT eligibility calculations.
        non_eligible_fields: Fields that MUST NOT participate in
            PIT eligibility or hash computation.
        availability_control: Declarative policy governing availability.
        missing_field_policy: How to handle missing required fields.
        timezone_requirement: Must be "UTC" for all trusted PIT timestamps.
    """
    model_config = ConfigDict(frozen=True)

    data_type: TemporalDataType = Field(..., description="Canonical data type category")
    required_fields: list[str] = Field(
        default_factory=list,
        description="Fields that MUST be present and non-null",
    )
    eligible_fields: list[str] = Field(
        default_factory=list,
        description="Fields that MAY participate in PIT eligibility",
    )
    non_eligible_fields: list[str] = Field(
        default_factory=list,
        description="Fields that MUST NOT participate in PIT eligibility or hashes",
    )
    availability_control: Optional[AvailabilityPolicy] = Field(
        None, description="Declarative availability policy"
    )
    missing_field_policy: MissingFieldPolicy = Field(
        default=MissingFieldPolicy.REJECT,
        description="How to handle missing required fields",
    )
    timezone_requirement: Literal["UTC"] = Field(
        default="UTC", description="Required timezone for all timestamps"
    )

    @field_validator("required_fields", "eligible_fields", "non_eligible_fields",
                     mode="after")
    @classmethod
    def _validate_field_names(cls, v: list[str]) -> list[str]:
        """Validate field names are known temporal field names."""
        valid_names = {
            "event_time", "observation_time", "publication_time",
            "effective_time", "revision_time", "ingestion_time",
        }
        for field in v:
            if field not in valid_names:
                raise ValueError(
                    f"Unknown temporal field: {field}. "
                    f"Valid names: {valid_names}"
                )
        return v

    @field_validator("timezone_requirement", mode="after")
    @classmethod
    def _validate_timezone(cls, v: str) -> str:
        """Ensure timezone requirement is UTC."""
        if v != "UTC":
            raise ValueError(f"Only UTC timezone is supported for PIT timestamps, got: {v}")
        return v

    def validate_required_fields_present(self, temporal_fields: dict[str, Optional[datetime]]) -> None:
        """Validate that all required temporal fields are present and non-null.

        Args:
            temporal_fields: Dict of field_name -> datetime (or None).

        Raises:
            ValueError: If a required field is missing or None
                and missing_field_policy is REJECT or REQUIRE_NON_NULL.
        """
        for field in self.required_fields:
            val = temporal_fields.get(field)
            if val is None and self.missing_field_policy in (
                MissingFieldPolicy.REJECT, MissingFieldPolicy.REQUIRE_NON_NULL
            ):
                raise ValueError(
                    f"Required temporal field '{field}' is missing or null. "
                    f"Contract requires: {self.required_fields}"
                )

    def is_eligible_field(self, field_name: str) -> bool:
        """Check if a field is eligible for PIT calculations."""
        if field_name in self.non_eligible_fields:
            return False
        return field_name in self.eligible_fields

    def get_contract_hash(self) -> str:
        """Return deterministic hash of this contract configuration.

        Uses canonical serialization of the contract fields only.
        """
        data = {
            "data_type": self.data_type.value,
            "required_fields": sorted(self.required_fields),
            "eligible_fields": sorted(self.eligible_fields),
            "non_eligible_fields": sorted(self.non_eligible_fields),
            "missing_field_policy": self.missing_field_policy.value,
            "timezone_requirement": self.timezone_requirement,
            "availability_control": self.availability_control.to_dict()
                if self.availability_control else None,
        }
        return deterministic_hash(data)

    def to_dict(self) -> dict:
        """Return contract as a mutable dict representation."""
        result = {
            "data_type": self.data_type.value,
            "required_fields": list(self.required_fields),
            "eligible_fields": list(self.eligible_fields),
            "non_eligible_fields": list(self.non_eligible_fields),
            "missing_field_policy": self.missing_field_policy.value,
            "timezone_requirement": self.timezone_requirement,
        }
        if self.availability_control:
            result["availability_control"] = self.availability_control.to_dict()
        return result
