"""Credential redaction for the broker-neutral layer (multi-broker
mandate, Phase M1).

Rules (repository security discipline, hardened for the day real
credentials exist):

- Credential material lives ONLY inside :class:`BrokerCredential`
  opaque holders. ``__repr__``/``__str__`` ALWAYS render the secret as
  ``<redacted>`` — accidental logging of a holder is structurally
  uninformative.
- Holders are per-account by construction (``account_id`` is bound at
  creation); a holder never crosses accounts.
- Nothing in this package serializes, journals, hashes-for-storage or
  otherwise persists secret material. The session journal stores
  NOTHING about the credential beyond the account id.
- :func:`scrub_secrets` / :func:`find_secret_leak` exist as the second
  lock on the door: defense-in-depth scrubbing for diagnostics, and a
  test-facing scanner proving serialized outputs are clean.

These are MOCK-phase credentials (arbitrary non-empty strings): the
four Phase M1 adapters are deterministic in-memory venues that perform
NO authentication. The machinery exists so the future real adapters
inherit a boundary that is already redaction-safe — never the other
way around.
"""

from typing import Any, Iterable, List, Mapping, Sequence

from data_engine.brokers.errors import REDACTED_PLACEHOLDER


class CredentialError(ValueError):
    """Raised on credential contract violations."""


class BrokerCredential:
    """Opaque per-account credential holder (secret never renders).

    ``__slots__`` keeps the secret out of ``__dict__``-style dumps;
    the redacted ``__repr__``/``__str__`` keep it out of logs; the
    absence of ``__eq__`` over the secret keeps it out of diff-style
    comparisons (equality compares ACCOUNT only — two holders for the
    same account are interchangeable handles, and that is all anyone
    outside this class may know).
    """

    __slots__ = ("_account_id", "_secret")

    def __init__(self, account_id: str, secret: str) -> None:
        if not isinstance(account_id, str) or not account_id.strip():
            raise CredentialError("credential account_id must be a non-empty string")
        if not isinstance(secret, str) or not secret.strip():
            raise CredentialError("credential secret must be a non-empty string")
        if "\x00" in secret:
            raise CredentialError("credential secret must not contain NUL bytes")
        self._account_id = account_id.strip()
        self._secret = secret

    @property
    def account_id(self) -> str:
        return self._account_id

    def matches_account(self, account_id: str) -> bool:
        return isinstance(account_id, str) and account_id.strip() == self._account_id

    def reveal_length(self) -> int:
        """Secret LENGTH only (never the value) — for redaction-test
        fixtures that need a realistic scan target size."""
        return len(self._secret)

    def __repr__(self) -> str:
        return (
            f"BrokerCredential(account_id={self._account_id!r}, "
            f"secret={REDACTED_PLACEHOLDER!r})"
        )

    def __str__(self) -> str:
        return f"BrokerCredential(account_id={self._account_id}, secret={REDACTED_PLACEHOLDER})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BrokerCredential):
            return NotImplemented
        return self._account_id == other._account_id

    def __hash__(self) -> int:
        return hash(("BrokerCredential", self._account_id))


def scrub_secrets(text: str, secrets: Iterable[str]) -> str:
    """Replace every occurrence of every secret in ``text``.

    Re-exported surface of :mod:`data_engine.brokers.errors.scrub_text`
    under the redaction module (callers should not need to know which
    module owns the placeholder).
    """
    if not isinstance(text, str):
        return text
    out = text
    for secret in secrets:
        if isinstance(secret, str) and secret:
            out = out.replace(secret, REDACTED_PLACEHOLDER)
    return out


def redact_mapping(obj: Mapping, secrets: Iterable[str]) -> dict:
    """Deep-copy a mapping with every secret string replaced."""
    from data_engine.brokers.errors import redact_mapping as _redact
    return _redact(obj, secrets)


def find_secret_leak(
    candidates: Iterable[str],
    secrets: Iterable[str],
) -> List[str]:
    """Return the list of leaked (candidate, secret) pairs.

    The redaction test harness feeds serialized journal entries, error
    messages, ``repr``/``str`` of holders and acks through this scanner
    and asserts the result is EMPTY. Fail-closed helper: it reports,
    never repairs.
    """
    secret_list = [s for s in secrets if isinstance(s, str) and s]
    leaks: List[str] = []
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        for secret in secret_list:
            if secret in candidate:
                leaks.append(candidate)
                break
    return leaks


def assert_no_secret_material(
    outputs: Sequence[Any],
    secrets: Iterable[str],
) -> None:
    """Raise :class:`CredentialError` if any secret appears in any
    serialized output (recursive over str/Mapping/Sequence)."""
    secret_list = [s for s in secrets if isinstance(s, str) and s]
    stack: List[Any] = list(outputs)
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            for secret in secret_list:
                if secret in item:
                    raise CredentialError(
                        "SECRET MATERIAL LEAKED into a serialized output — "
                        "this is a hard defect (redaction boundary breach)"
                    )
        elif isinstance(item, Mapping):
            stack.extend(item.values())
        elif isinstance(item, (list, tuple, set, frozenset)):
            stack.extend(item)
    return None


__all__ = [
    "CredentialError",
    "BrokerCredential",
    "scrub_secrets",
    "redact_mapping",
    "find_secret_leak",
    "assert_no_secret_material",
]
