"""Phase 9 — AI model/provider abstraction (blueprint 5.40).

Free-first, provider-swappable model abstraction with ZERO network
capability in this package:

- ``ModelProvider`` protocol: ``complete(prompt, context) -> str``.
- ``ModelRouter``: routes requests to registered providers by
  preference order (free providers first — the blueprint's
  free-first construction strategy). Unregistered providers cannot
  be constructed into the router.
- ``DeterministicTestProvider``: a pure provider whose responses are
  a deterministic function of the prompt — used for tests and as the
  reference semantics of the protocol.

The production LLM adapters (HTTP clients) are deployment concerns of
the operator's environment; this package defines the contracts and
the deterministic routing logic only. No agent code can reach a
network through anything in this module.
"""

from typing import Any, Callable, Mapping, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from data_engine.pit.hashing import deterministic_hash

#: Phase 9 contract version.
PHASE_9_CONTRACT_VERSION = "1.0.0"


class ModelAbstractionError(ValueError):
    """Raised on model-abstraction contract violations."""


class ModelResponse(BaseModel):
    """One model completion with provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider_id: str
    model_id: str
    prompt_hash: str
    response_text: str

    @field_validator("provider_id", "model_id", "prompt_hash")
    @classmethod
    def _validate_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("model response fields must be non-empty")
        return v

    @property
    def response_hash(self) -> str:
        return "her9." + deterministic_hash(
            {
                "contract_version": PHASE_9_CONTRACT_VERSION,
                "provider_id": self.provider_id,
                "model_id": self.model_id,
                "prompt_hash": self.prompt_hash,
                "response_text": self.response_text,
            }
        )


class ModelProvider(Protocol):
    """The provider protocol: a pure completion function."""

    provider_id: str

    def complete(self, prompt: str, context: Optional[Mapping[str, Any]] = None) -> str:
        ...


class DeterministicTestProvider:
    """Deterministic provider: response = f(prompt).

    The response is the SHA-256 of the prompt prefixed with the
    provider/model ids — identical prompts ALWAYS yield identical
    responses, in any process. This is the reference semantics for
    the protocol and the testing double for orchestration logic.
    """

    def __init__(self, provider_id: str = "deterministic-test") -> None:
        if not provider_id.strip():
            raise ModelAbstractionError("provider_id must be non-empty")
        self.provider_id = provider_id.strip()

    def complete(
        self, prompt: str, context: Optional[Mapping[str, Any]] = None
    ) -> str:
        if not isinstance(prompt, str) or not prompt:
            raise ModelAbstractionError("prompt must be a non-empty string")
        digest = deterministic_hash(
            {"provider": self.provider_id, "prompt": prompt}
        )
        return f"[{self.provider_id}] {digest}"


class ModelRouter:
    """Free-first provider routing.

    Providers are registered in preference order (free first). The
    router walks the list and returns the first provider that
    satisfies the request's optional model constraint. A router with
    zero providers refuses every request — fail closed.
    """

    def __init__(self, providers: Sequence[ModelProvider]) -> None:
        if not providers:
            raise ModelAbstractionError(
                "a router needs at least one registered provider "
                "(fail closed, never route to nothing)"
            )
        seen: set[str] = set()
        for provider in providers:
            pid = getattr(provider, "provider_id", None)
            if not pid:
                raise ModelAbstractionError(
                    "every provider must expose a provider_id"
                )
            if pid in seen:
                raise ModelAbstractionError(
                    f"duplicate provider registration: {pid}"
                )
            if not callable(getattr(provider, "complete", None)):
                raise ModelAbstractionError(
                    f"provider {pid} does not implement complete()"
                )
            seen.add(pid)
        self._providers: tuple[ModelProvider, ...] = tuple(providers)

    @property
    def provider_ids(self) -> tuple[str, ...]:
        return tuple(p.provider_id for p in self._providers)

    def route(
        self, provider_id: Optional[str] = None
    ) -> ModelProvider:
        """Select a provider: explicit id or the first (free-first)."""
        if provider_id is None:
            return self._providers[0]
        for provider in self._providers:
            if provider.provider_id == provider_id:
                return provider
        raise ModelAbstractionError(
            f"provider {provider_id!r} not registered "
            f"(available: {list(self.provider_ids)})"
        )

    def complete(
        self,
        prompt: str,
        provider_id: Optional[str] = None,
        model_id: str = "default",
    ) -> ModelResponse:
        provider = self.route(provider_id)
        response_text = provider.complete(prompt)
        return ModelResponse(
            provider_id=provider.provider_id,
            model_id=model_id,
            prompt_hash=deterministic_hash(prompt),
            response_text=response_text,
        )


__all__ = [
    "ModelAbstractionError",
    "ModelResponse",
    "ModelProvider",
    "DeterministicTestProvider",
    "ModelRouter",
    "PHASE_9_CONTRACT_VERSION",
]
