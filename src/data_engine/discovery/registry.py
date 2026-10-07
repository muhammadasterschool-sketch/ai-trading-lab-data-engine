"""Append-only strategy-candidate registry (blueprint 5.18 semantics).

Governance invariants:

- Append-only: ``register`` returns a NEW registry (immutability).
- Duplicate protection: a candidate_id or candidate_hash already
  present is REJECTED (raises) — the same discovery evidence can never
  register twice.
- Tamper evidence: every registry carries a hash chain over the
  recorded candidate hashes; ``verify_integrity`` re-derives it.
- Governance view: ``validated_only()`` exposes only VALIDATED
  candidates — REJECTED/DRAFT records remain as evidence but never
  feed backtesting. This is the "no generated strategy may bypass
  governance" guarantee at the registry layer.
"""

import hashlib
from typing import Iterable, Optional

from pydantic import BaseModel, ConfigDict

from data_engine.discovery.models import (
    CandidateStatus,
    StrategyCandidate,
)


class DiscoveryRegistryError(ValueError):
    """Raised on duplicate registration or integrity violations."""


class _RegistryState(BaseModel):
    """Internal immutable state (records + chain)."""

    model_config = ConfigDict(frozen=True)

    records: tuple[StrategyCandidate, ...] = ()
    chain_hash: str = "genesis"


class DiscoveryRegistry:
    """Append-only, duplicate-rejecting, tamper-evident registry."""

    def __init__(self, state: Optional[_RegistryState] = None) -> None:
        self._state = state or _RegistryState()

    # -- read API -----------------------------------------------------------

    @property
    def records(self) -> tuple[StrategyCandidate, ...]:
        return self._state.records

    @property
    def chain_hash(self) -> str:
        return self._state.chain_hash

    def validated_only(self) -> tuple[StrategyCandidate, ...]:
        """The governance view: only VALIDATED candidates."""
        return tuple(
            r for r in self._state.records
            if r.status is CandidateStatus.VALIDATED
        )

    def rejected(self) -> tuple[StrategyCandidate, ...]:
        """Evidence view: REJECTED candidates with their reasons."""
        return tuple(
            r for r in self._state.records
            if r.status is CandidateStatus.REJECTED
        )

    def get(self, candidate_id: str) -> StrategyCandidate:
        for record in self._state.records:
            if record.candidate_id == candidate_id:
                return record
        raise DiscoveryRegistryError(
            f"unknown candidate {candidate_id!r}"
        )

    # -- write API ----------------------------------------------------------

    def register(
        self,
        candidate: StrategyCandidate,
    ) -> "DiscoveryRegistry":
        """Return a new registry with ``candidate`` appended.

        Raises:
            DiscoveryRegistryError: on duplicate candidate_id, duplicate
                candidate_hash, or a REJECTED candidate re-registering
                under a healed status.
        """
        existing_ids = {r.candidate_id for r in self._state.records}
        if candidate.candidate_id in existing_ids:
            raise DiscoveryRegistryError(
                f"duplicate candidate_id {candidate.candidate_id!r} — "
                "discovery evidence cannot register twice"
            )
        existing_hashes = {r.candidate_hash for r in self._state.records}
        if candidate.candidate_hash in existing_hashes:
            raise DiscoveryRegistryError(
                "duplicate candidate identity (same template/hypothesis/"
                "dataset/seed/spec) — already registered"
            )
        new_chain = self._extend_chain(self._state.chain_hash, candidate)
        new_state = _RegistryState(
            records=self._state.records + (candidate,),
            chain_hash=new_chain,
        )
        return DiscoveryRegistry(new_state)

    def register_all(
        self, candidates: Iterable[StrategyCandidate]
    ) -> "DiscoveryRegistry":
        registry = self
        for candidate in candidates:
            registry = registry.register(candidate)
        return registry

    # -- integrity ----------------------------------------------------------

    def verify_integrity(self) -> None:
        """Re-derive the hash chain; raise on any tamper.

        A tampered record (mutated status, edited reason) changes its
        candidate_hash input or ordering and breaks the chain.
        """
        chain = "genesis"
        seen_hashes: set[str] = set()
        for record in self._state.records:
            if record.candidate_hash in seen_hashes:
                raise DiscoveryRegistryError(
                    "integrity failure: duplicate candidate hash in chain"
                )
            seen_hashes.add(record.candidate_hash)
            chain = self._extend_chain(chain, record)
        if chain != self._state.chain_hash:
            raise DiscoveryRegistryError(
                "integrity failure: chain hash mismatch — registry tampered"
            )

    @staticmethod
    def _extend_chain(prev: str, candidate: StrategyCandidate) -> str:
        digest = hashlib.sha256(
            (prev + "|" + candidate.record_digest).encode("utf-8")
        ).hexdigest()
        return "chain20." + digest
