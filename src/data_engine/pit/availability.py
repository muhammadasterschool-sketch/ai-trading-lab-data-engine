"""Phase 4A.1 — Declarative Availability Policy Definitions.

Availability policies are declarative, immutable data structures.
They must NOT contain arbitrary Python callbacks, lambda functions,
or dynamically supplied callables.

Policy semantics are representable as immutable configuration data.
Supports:
- publication-controlled availability
- revision-aware availability
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from enum import Enum
from typing import Optional
from datetime import datetime, UTC


class AvailabilityRuleType(str, Enum):
    """Types of declarative availability rules."""
    PUBLICATION_CONTROLLED = "publication_controlled"
    REVISION_AWARE = "revision_aware"


class PublicationControlledAvailability(BaseModel):
    """Publication-controlled availability policy.

    A data item is available for PIT research if and only if
    its publication_time is at or before the query time.
    This is a declarative rule — no executable code is involved.

    Attributes:
        require_publication: Whether publication_time is required for availability.
        max_delay_seconds: Maximum allowed delay between publication_time
            and effective_time. None means no limit.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    require_publication: bool = Field(True, description="Publication time required")
    max_delay_seconds: Optional[float] = Field(
        None, ge=0, description="Max delay between publication and effective"
    )

    def is_available(self, publication_time: Optional[datetime],
                      effective_time: Optional[datetime],
                      query_time: datetime) -> bool:
        """Check availability against query_time using immutable policy rules.

        Args:
            publication_time: The data's publication timestamp (UTC-aware).
            effective_time: The data's effective timestamp (UTC-aware).
            query_time: The time at which availability is being checked (UTC-aware).

        Returns:
            True if the data item is available per this policy.
        """
        if self.require_publication and publication_time is None:
            return False
        if publication_time is not None and publication_time > query_time:
            return False
        if self.max_delay_seconds is not None:
            if publication_time is not None and effective_time is not None:
                delay = (effective_time - publication_time).total_seconds()
                if delay > self.max_delay_seconds:
                    return False
        return True

    def to_dict(self) -> dict:
        """Return immutable policy configuration as a dict."""
        return {
            "rule_type": self.__class__.__name__,
            "require_publication": self.require_publication,
            "max_delay_seconds": self.max_delay_seconds,
        }


class RevisionAwareAvailability(BaseModel):
    """Revision-aware availability policy.

    A data item is available for PIT research if and only if
    its revision_time is at or before the query time, AND the
    revision has not been superseded by a newer publication.

    Attributes:
        require_revision: Whether revision_time is required for availability.
        max_revision_age_seconds: Maximum age of revision before it
            is considered stale. None means no limit.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    require_revision: bool = Field(True, description="Revision time required")
    max_revision_age_seconds: Optional[float] = Field(
        None, ge=0, description="Max age before revision is stale"
    )

    def is_available(self, revision_time: Optional[datetime],
                      publication_time: Optional[datetime],
                      query_time: datetime) -> bool:
        """Check availability against query_time using immutable policy rules.

        Args:
            revision_time: The data's revision timestamp (UTC-aware).
            publication_time: The data's publication timestamp (UTC-aware).
            query_time: The time at which availability is being checked (UTC-aware).

        Returns:
            True if the data item is available per this policy.
        """
        if self.require_revision and revision_time is None:
            return False
        if revision_time is not None and revision_time > query_time:
            return False
        if self.max_revision_age_seconds is not None and revision_time is not None:
            age = (query_time - revision_time).total_seconds()
            if age > self.max_revision_age_seconds:
                return False
        return True

    def to_dict(self) -> dict:
        """Return immutable policy configuration as a dict."""
        return {
            "rule_type": self.__class__.__name__,
            "require_revision": self.require_revision,
            "max_revision_age_seconds": self.max_revision_age_seconds,
        }


class AvailabilityPolicy(BaseModel):
    """Top-level declarative availability policy for PIT data.

    Contains the policy definition and provides the unified
    availability check. Policy is immutable and contains no
    executable code.

    Attributes:
        rule_type: The type of availability rule to apply.
        policy: The specific policy configuration.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_type: AvailabilityRuleType = Field(..., description="Type of availability rule")
    policy: PublicationControlledAvailability | RevisionAwareAvailability = Field(
        ..., description="Declarative availability policy configuration"
    )

    @model_validator(mode="after")
    def _validate_rule_type_matches_policy(self) -> "AvailabilityPolicy":
        """Enforce the discriminated-union pairing (spec 5.2/5.3, F-16).

        A mismatched rule_type/policy combination MUST raise at
        construction. Without this, a mismatched pairing silently
        computes under the wrong rule and leaks future revisions —
        the exact defect PIT exists to prevent.
        """
        if self.rule_type == AvailabilityRuleType.PUBLICATION_CONTROLLED \
                and not isinstance(self.policy, PublicationControlledAvailability):
            raise ValueError(
                f"AvailabilityPolicy pairing violation (spec 5.2): "
                f"rule_type=PUBLICATION_CONTROLLED requires "
                f"PublicationControlledAvailability, got "
                f"{type(self.policy).__name__}."
            )
        if self.rule_type == AvailabilityRuleType.REVISION_AWARE \
                and not isinstance(self.policy, RevisionAwareAvailability):
            raise ValueError(
                f"AvailabilityPolicy pairing violation (spec 5.2): "
                f"rule_type=REVISION_AWARE requires "
                f"RevisionAwareAvailability, got "
                f"{type(self.policy).__name__}."
            )
        return self

    def is_available(self, publication_time: Optional[datetime],
                      effective_time: Optional[datetime],
                      revision_time: Optional[datetime],
                      query_time: datetime) -> bool:
        """Check if data is available at query_time per this policy.

        Args:
            publication_time: Data's publication timestamp (UTC-aware, optional).
            effective_time: Data's effective timestamp (UTC-aware, optional).
            revision_time: Data's revision timestamp (UTC-aware, optional).
            query_time: The time at which availability is being checked (UTC-aware).

        Returns:
            True if the data item is available per this policy.
        """
        if self.rule_type == AvailabilityRuleType.PUBLICATION_CONTROLLED:
            return self.policy.is_available(publication_time, effective_time, query_time)
        elif self.rule_type == AvailabilityRuleType.REVISION_AWARE:
            return self.policy.is_available(revision_time, publication_time, query_time)
        return False

    def to_dict(self) -> dict:
        """Return immutable policy configuration as a dict."""
        return {
            "rule_type": self.rule_type.value,
            "policy": self.policy.to_dict(),
        }
