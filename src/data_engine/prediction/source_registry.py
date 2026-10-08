"""Governed data-source registry (closure mandate §6, §18.1).

Every candidate real-data source must be DECLARED here before any
acquisition, with: source identity, type, license/usage basis,
coverage, granularity, expected limitations, revision behavior,
corporate-action behavior, provenance mechanism, verification status,
and approved usage scope.

Hard rules:
- NO credentials in this registry — no API keys, tokens, or secrets.
  ``extra="forbid"`` structurally prevents credential fields; the
  credential interface is environment variables only
  (``DATA_SOURCE_CREDENTIAL_<SOURCE>``), read at acquisition time by
  the (future, human-approved) acquisition runner — never stored here.
- Source approval is a HUMAN DECISION (mandate §18.1): AI/agent
  approvals are structurally rejected, mirroring the model registry.
- A source that is not approved for a usage scope cannot authorize
  evaluation data — ``usage_authorized`` is the fail-closed check.
"""

from enum import Enum
from typing import Optional, Tuple

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.prediction.contracts import PredictionContractError
from data_engine.prediction.identity import (
    SOURCE_CATALOG_PREFIX,
    prefixed_hash,
)

#: Usage scopes a source can be approved for (closed vocabulary).
USAGE_SCOPES: Tuple[str, ...] = (
    "contract-testing",       # deterministic fixtures only
    "empirical-evaluation",   # may back §26 empirical validation
    "production-ingestion",   # may feed live (future, never auto-granted)
)


class SourceVerificationStatus(str, Enum):
    """Human-governed verification ladder for data sources."""

    UNVETTED = "UNVETTED"
    VETTED = "VETTED"
    APPROVED_FOR_TESTING = "APPROVED_FOR_TESTING"
    APPROVED_FOR_PRODUCTION = "APPROVED_FOR_PRODUCTION"
    REJECTED = "REJECTED"


class SourceApprovalRecord(BaseModel):
    """One human approval decision on a data source (mandate §18.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    approver: str
    approver_kind: str  # "human" | "ai" — ai is rejected at submission
    decision_id: str
    recorded_at: str  # logical, caller-supplied

    @field_validator("approver", "approver_kind", "decision_id",
                     "recorded_at")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise PredictionContractError(
                "approval fields must be non-empty strings"
            )
        return v


class DataSourceRecord(BaseModel):
    """One declared data source (mandate §6 field set)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_name: str
    source_type: str  # "exchange-api" | "archive-download" | "macro-api" | ...
    license_basis: str  # honest basis; "UNKNOWN" until vetted
    coverage: str  # human-readable coverage description
    granularity: str  # "daily-OHLCV" | "hourly" | ...
    expected_limitations: Tuple[str, ...] = ()
    revision_behavior: str
    corporate_action_behavior: str
    provenance_mechanism: str  # checksums? versioned archives? none?
    verification_status: SourceVerificationStatus = (
        SourceVerificationStatus.UNVETTED
    )
    approved_usage_scopes: Tuple[str, ...] = ()
    approval: Optional[SourceApprovalRecord] = None
    notes: Tuple[str, ...] = ()

    @field_validator("source_name", "source_type", "license_basis",
                     "coverage", "granularity", "revision_behavior",
                     "corporate_action_behavior", "provenance_mechanism")
    @classmethod
    def _validate_text(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise PredictionContractError(
                "source fields must be non-empty strings"
            )
        return v

    @field_validator("approved_usage_scopes")
    @classmethod
    def _validate_scopes(cls, v: Tuple[str, ...]) -> Tuple[str, ...]:
        for scope in v:
            if scope not in USAGE_SCOPES:
                raise PredictionContractError(
                    f"unknown usage scope {scope!r} — closed vocabulary "
                    f"{USAGE_SCOPES}"
                )
        return v

    @property
    def record_hash(self) -> str:
        return prefixed_hash(
            SOURCE_CATALOG_PREFIX,
            {
                "kind": "data_source_record",
                "source_name": self.source_name,
                "source_type": self.source_type,
                "license_basis": self.license_basis,
                "coverage": self.coverage,
                "granularity": self.granularity,
                "expected_limitations": list(self.expected_limitations),
                "revision_behavior": self.revision_behavior,
                "corporate_action_behavior": (
                    self.corporate_action_behavior
                ),
                "provenance_mechanism": self.provenance_mechanism,
                "verification_status": self.verification_status.value,
                "approved_usage_scopes": list(self.approved_usage_scopes),
                "approval": (
                    None
                    if self.approval is None
                    else {
                        "approver": self.approval.approver,
                        "approver_kind": self.approval.approver_kind,
                        "decision_id": self.approval.decision_id,
                        "recorded_at": self.approval.recorded_at,
                    }
                ),
            },
        )


class SourceApprovalDecision(BaseModel):
    """Outcome of a source-approval submission."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: bool
    source_name: str
    approver: str
    approver_kind: str
    reason: str
    decision_id: str


class DataSourceRegistry:
    """In-memory governed source catalog (mandate §6).

    Registration is open (declaring a candidate is research); APPROVAL
    is human-only (mandate §18.1). Duplicate source names are rejected.
    """

    def __init__(self) -> None:
        self._records: dict[str, DataSourceRecord] = {}

    def register(self, record: DataSourceRecord) -> DataSourceRecord:
        if record.source_name in self._records:
            raise PredictionContractError(
                f"duplicate source name rejected: {record.source_name!r}"
            )
        if (
            record.verification_status
            is not SourceVerificationStatus.UNVETTED
            and record.approval is None
        ):
            raise PredictionContractError(
                "a source cannot enter the registry above UNVETTED "
                "without a recorded approval decision (mandate §18.1)"
            )
        self._records[record.source_name] = record
        return record

    def get(self, source_name: str) -> DataSourceRecord:
        try:
            return self._records[source_name]
        except KeyError as exc:
            raise PredictionContractError(
                f"unknown data source {source_name!r}"
            ) from exc

    def list_records(self) -> Tuple[DataSourceRecord, ...]:
        return tuple(
            self._records[name] for name in sorted(self._records)
        )

    def submit_approval(
        self,
        source_name: str,
        approver: str,
        *,
        approver_kind: str,
        target_status: SourceVerificationStatus = (
            SourceVerificationStatus.APPROVED_FOR_TESTING
        ),
        approved_usage_scopes: Tuple[str, ...] = (),
        recorded_at: str = "UNRECORDED",
    ) -> SourceApprovalDecision:
        """Record (or structurally REJECT) a source approval.

        AI/agent approvals never change a source's status — the
        rejection is recorded in the decision and the record notes.
        """
        record = self.get(source_name)
        decision_id = prefixed_hash(
            SOURCE_CATALOG_PREFIX,
            {
                "kind": "source_approval_decision",
                "source_name": source_name,
                "approver": approver,
                "approver_kind": approver_kind,
                "target_status": target_status.value,
                "recorded_at": recorded_at,
            },
        )
        if approver_kind != "human":
            updated = record.model_copy(
                update={
                    "notes": record.notes
                    + (
                        f"APPROVAL_REJECTED({approver_kind}:{approver})",
                    )
                }
            )
            self._records[source_name] = updated
            return SourceApprovalDecision(
                accepted=False,
                source_name=source_name,
                approver=approver,
                approver_kind=approver_kind,
                reason=(
                    "AI/agent source approval is structurally rejected — "
                    "data-source approval is a HUMAN DECISION (mandate "
                    "§18.1)"
                ),
                decision_id=decision_id,
            )
        for scope in approved_usage_scopes:
            if scope not in USAGE_SCOPES:
                raise PredictionContractError(
                    f"unknown usage scope {scope!r}"
                )
        approval = SourceApprovalRecord(
            approver=approver,
            approver_kind="human",
            decision_id=decision_id,
            recorded_at=recorded_at,
        )
        updated = record.model_copy(
            update={
                "verification_status": target_status,
                "approved_usage_scopes": approved_usage_scopes,
                "approval": approval,
            }
        )
        self._records[source_name] = updated
        return SourceApprovalDecision(
            accepted=True,
            source_name=source_name,
            approver=approver,
            approver_kind="human",
            reason="human source approval recorded",
            decision_id=decision_id,
        )

    def usage_authorized(
        self,
        source_name: str,
        usage: str,
    ) -> bool:
        """Fail-closed usage check: approved status AND scope membership."""
        if usage not in USAGE_SCOPES:
            raise PredictionContractError(
                f"unknown usage scope {usage!r}"
            )
        record = self._records.get(source_name)
        if record is None or record.approval is None:
            return False
        if record.approval.approver_kind != "human":
            return False
        if record.verification_status not in (
            SourceVerificationStatus.APPROVED_FOR_TESTING,
            SourceVerificationStatus.APPROVED_FOR_PRODUCTION,
        ):
            return False
        return usage in record.approved_usage_scopes


def candidate_source_matrix() -> Tuple[DataSourceRecord, ...]:
    """The candidate real-data source matrix (mandate §18 preparation).

    Every candidate is UNVETTED with an honest license basis and
    declared limitations. This matrix is a RECOMMENDATION for human
    review — no approval is implied or fabricated. All candidates
    require: license confirmation, coverage verification, and a
    provenance mechanism before any dataset they produce could verify
    REAL_VERIFIED.
    """
    return (
        DataSourceRecord(
            source_name="stooq-daily-ohlcv",
            source_type="archive-download",
            license_basis="UNKNOWN — free public archives; terms must be "
                          "confirmed before use",
            coverage="Equities/indices/commodities, daily OHLCV, "
                     "multi-decade for major instruments (to verify)",
            granularity="daily-OHLCV",
            expected_limitations=(
                "no intraday data",
                "corporate-action treatment per instrument must be "
                "verified, not assumed",
                "unofficial redistribution restrictions possible",
                "revision behavior undocumented",
            ),
            revision_behavior="UNKNOWN — must be probed empirically "
                              "before trusting point-in-time claims",
            corporate_action_behavior="adjusted prices present; split "
                                      "policy must be verified per symbol",
            provenance_mechanism="download archive + SHA-256 over the "
                                 "payload; acquisition timestamp recorded "
                                 "at download",
            notes=(
                "no credentials required — public downloads",
                "candidate for 10y+ daily OHLCV once vetted",
            ),
        ),
        DataSourceRecord(
            source_name="fred-macro-series",
            source_type="macro-api",
            license_basis="public domain (U.S. federal open data) — "
                          "verify per series",
            coverage="Macro series (VIXCLS, unemployment, rates), daily "
                     "to monthly",
            granularity="daily/monthly point series",
            expected_limitations=(
                "macro series only — not tradeable OHLCV",
                "revisions ARE published (vintage discipline required)",
                "point-in-time semantics need vintage dates",
            ),
            revision_behavior="releases revised series — FIRST ARRIVALS "
                              "must be snapshotted to preserve PIT truth",
            corporate_action_behavior="not-applicable (macro)",
            provenance_mechanism="vintage-date snapshot + payload hash",
            notes=("no credentials required for public series",),
        ),
        DataSourceRecord(
            source_name="binance-public-klines",
            source_type="exchange-api",
            license_basis="exchange terms of use — verify before "
                          "commercial use",
            coverage="crypto pairs, 1m..1d klines, full history",
            granularity="OHLCV klines",
            expected_limitations=(
                "crypto only — not equities",
                "no survivorship problem within a pair, but exchange "
                "delistings exist",
                "API rate limits",
            ),
            revision_behavior="klines are append-only in practice — "
                              "verify",
            corporate_action_behavior="not-applicable (crypto)",
            provenance_mechanism="API pagination + payload hash + "
                                 "acquisition timestamp",
            notes=(
                "no credentials required for public endpoints",
                "good crisis-period coverage (2018/2020/2022 drawdowns)",
            ),
        ),
        DataSourceRecord(
            source_name="alpha-vantage-free-tier",
            source_type="vendor-api",
            license_basis="vendor free-tier terms — API key required, "
                          "rate-limited",
            coverage="Equities daily/adjusted, limited history on free "
                     "tier",
            granularity="daily-OHLCV",
            expected_limitations=(
                "free tier: 25 requests/day — multi-decade multi-symbol "
                "acquisition infeasible without paid tier",
                "adjusted-close policy must be verified",
                "revision behavior undocumented",
            ),
            revision_behavior="UNKNOWN",
            corporate_action_behavior="adjusted series offered; policy "
                                      "must be verified",
            provenance_mechanism="API response hash + acquisition "
                                 "timestamp",
            notes=(
                "REQUIRES an API key — credential via environment "
                "variable only (never committed)",
            ),
        ),
        DataSourceRecord(
            source_name="yfinance-unofficial",
            source_type="unofficial-client",
            license_basis="UNKNOWN — unofficial client for a private "
                          "API; usage basis must be reviewed",
            coverage="Equities/indices daily OHLCV with history",
            granularity="daily-OHLCV",
            expected_limitations=(
                "unofficial — no contract, breaking changes likely",
                "redistribution terms unclear",
                "corporate-action adjustment switchable but default "
                "behavior must be pinned",
            ),
            revision_behavior="UNKNOWN — treats Yahoo as source of "
                              "record; revisions possible",
            corporate_action_behavior="auto-adjusted and unadjusted "
                                      "endpoints both exist — must pin "
                                      "one",
            provenance_mechanism="response hash + acquisition timestamp",
            notes=(
                "recommended LAST — prefer governed archives first",
                "no credentials required",
            ),
        ),
    )


__all__ = [
    "USAGE_SCOPES",
    "SourceVerificationStatus",
    "SourceApprovalRecord",
    "DataSourceRecord",
    "SourceApprovalDecision",
    "DataSourceRegistry",
    "candidate_source_matrix",
]
