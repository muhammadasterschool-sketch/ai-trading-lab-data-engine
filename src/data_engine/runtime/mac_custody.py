"""Keyed-MAC ledger custody (operator mandate 2026-10-10 §1.5; P2
open-blocker KEYED-MAC closure: "human decision record + keyed-chain
implementation + tests").

THREAT MODEL (P2_INDEPENDENT_CORRECTION_RE_AUDIT_REPORT.md, KEYED-MAC
row): the unkeyed audit chain is tamper-EVIDENT against partial edits
but re-forgeable end-to-end — an attacker able to rewrite the FULL
history can recompute every hash link. Keying each event's hash with
HMAC-SHA256 under a secret held in proper custody removes that path: a
full-history rewrite now requires the key.

CUSTODY RULES (operator §1.5 — never violated here):

- The repository NEVER contains key material. Keys enter ONLY through
  the ``RUNTIME_LEDGER_MAC_KEY`` environment variable (hex or raw) or
  ``RUNTIME_LEDGER_MAC_KEY_FILE`` (absolute path to a key file OUTSIDE
  the repository), read at composition time by the operator-controlled
  launcher — never by tests, never committed, never logged.
- No key material ever appears in ``repr``/``str``/ledger events/
  exports/logs. Only a ``key_id`` FINGERPRINT (SHA-256 of the key,
  truncated) is recorded, so rotations remain attributable.
- Rotation: a new key becomes CURRENT; the previous key stays
  registered for VERIFICATION ONLY (retired grace). Events record the
  key id they were signed under, so mixed-key histories verify.
- Operational honesty: custody is OPERATIONAL only when a genuine key
  was provisioned through the environment channel by the operator.
  Test fixtures construct keys EXPLICITLY and are marked TEST_FIXTURE.

Fail-closed integration (see ``ledgers.py``):

- custody present  + event without ``mac_key_id``  => verify FAILS
  (a downgrade to unkeyed inside a keyed session is tampering);
- custody absent  + event with    ``mac_key_id``  => verify FAILS
  (keyed events cannot be verified without custody);
- custody absent  + all events unkeyed            => legacy unkeyed
  chain (byte-identical to the pre-keyed behavior — backward
  compatible with every existing persisted state and test).

This module reads the environment ONLY inside
:func:`MacCustody.from_environment` (the operator provisioning
channel). The readiness gates and every other runtime component remain
environment-free (structural tests hold).
"""

import hashlib
import hmac
import os
from pathlib import Path
from typing import Optional

from data_engine.pit.serialization import canonical_serialize
from data_engine.runtime.contracts import RuntimeContractError

#: Environment channel for direct key provisioning (hex or raw bytes).
#: NEVER a default value — absence raises (no silent unkeyed fallback
#: inside an explicitly-requested operational custody).
ENV_KEY_VAR = "RUNTIME_LEDGER_MAC_KEY"

#: Environment channel for indirect provisioning: absolute path to a
#: key file OUTSIDE the repository (custody transfer by file).
ENV_KEY_FILE_VAR = "RUNTIME_LEDGER_MAC_KEY_FILE"

#: Minimum decoded key length (bytes) — HMAC-SHA256 strength floor.
MIN_KEY_BYTES = 32

#: Fingerprint length (hex chars) of the key id.
_KEY_ID_LEN = 16

#: MAC output: 64 lowercase hex chars (same width as SHA-256 — the
#: genesis "0" * 64 convention and every length assertion holds).
MAC_HEX_LEN = 64


class MacCustodyError(RuntimeContractError):
    """Raised on keyed-MAC custody contract violations."""


def _fingerprint(material: bytes) -> str:
    """Stable, non-secret key id: truncated SHA-256 of the key bytes."""
    return "mackey-" + hashlib.sha256(material).hexdigest()[:_KEY_ID_LEN]


class _MacKey:
    """One secret key. NEVER exposes material via repr/str."""

    __slots__ = ("_material", "_key_id", "_status")

    def __init__(self, material: bytes, status: str) -> None:
        if not isinstance(material, (bytes, bytearray)) or len(material) < MIN_KEY_BYTES:
            raise MacCustodyError(
                f"MAC key material must be at least {MIN_KEY_BYTES} bytes "
                f"(got {len(material) if isinstance(material, (bytes, bytearray)) else type(material).__name__})"
            )
        self._material = bytes(material)
        self._key_id = _fingerprint(self._material)
        self._status = status

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def status(self) -> str:
        return self._status

    def sign(self, data: bytes) -> str:
        """HMAC-SHA256 over ``data`` with this key (hex digest)."""
        return hmac.new(self._material, data, hashlib.sha256).hexdigest()

    def verify(self, data: bytes, mac: str) -> bool:
        """Constant-time MAC verification (``hmac.compare_digest``)."""
        if not isinstance(mac, str) or len(mac) != MAC_HEX_LEN:
            return False
        expected = self.sign(data)
        return hmac.compare_digest(expected, mac)

    def __repr__(self) -> str:  # pragma: no cover - safety surface
        return f"_MacKey(key_id={self._key_id!r}, material=MASKED, status={self._status!r})"

    __str__ = __repr__


class MacCustody:
    """Keyed-MAC custody: current key + retired keys (verification
    only) + rotation. The single signing authority for keyed chains."""

    def __init__(self, current: _MacKey, retired: tuple = ()) -> None:
        for key in retired:
            if not isinstance(key, _MacKey):
                raise MacCustodyError("retired keys must be _MacKey instances")
        ids = [current.key_id] + [k.key_id for k in retired]
        if len(set(ids)) != len(ids):
            raise MacCustodyError("duplicate key ids in custody registry")
        self._current = current
        self._retired = tuple(retired)

    # -- construction channels ------------------------------------------------

    @classmethod
    def from_environment(cls) -> "MacCustody":
        """Operator provisioning channel — the ONLY env-reading path.

        Reads ``RUNTIME_LEDGER_MAC_KEY`` (hex or raw) or, failing that,
        ``RUNTIME_LEDGER_MAC_KEY_FILE`` (absolute path outside the repo
        whose file contains the key). Raises :class:`MacCustodyError`
        when neither is set — an explicitly-requested operational
        custody NEVER silently falls back to unkeyed mode.

        SECURITY: the variable VALUE (the key) is never included in the
        exception, log, or any artifact — only its presence/absence.
        """
        raw = os.environ.get(ENV_KEY_VAR)
        if raw is not None and raw.strip():
            material = cls._decode(raw.strip())
            return cls(_MacKey(material, status="OPERATIONAL"))
        path_str = os.environ.get(ENV_KEY_FILE_VAR)
        if path_str is not None and path_str.strip():
            path = Path(path_str.strip())
            if not path.is_absolute():
                raise MacCustodyError(
                    "key file path must be ABSOLUTE (custody channel "
                    "policy) — relative paths could resolve inside the "
                    "repository"
                )
            try:
                material = cls._decode(path.read_text(encoding="utf-8").strip())
            except OSError as exc:
                raise MacCustodyError(
                    "key file unreadable — custody provisioning FAILED "
                    "(fail closed)"
                ) from exc
            return cls(_MacKey(material, status="OPERATIONAL"))
        raise MacCustodyError(
            f"keyed-MAC custody requested but no key provisioned: set "
            f"{ENV_KEY_VAR} or {ENV_KEY_FILE_VAR} through the operator "
            "secure channel (never in chat, never committed)"
        )

    @staticmethod
    def _decode(text: str) -> bytes:
        """Decode hex key text; fall back to raw UTF-8 bytes."""
        try:
            material = bytes.fromhex(text)
            if len(material) >= MIN_KEY_BYTES:
                return material
            # Short hex — treat as raw text only if it would then qualify.
            raw = text.encode("utf-8")
            if len(raw) >= MIN_KEY_BYTES:
                return raw
            raise MacCustodyError(
                f"key material below the {MIN_KEY_BYTES}-byte minimum"
            )
        except ValueError:
            raw = text.encode("utf-8")
            if len(raw) < MIN_KEY_BYTES:
                raise MacCustodyError(
                    f"key material below the {MIN_KEY_BYTES}-byte minimum"
                ) from None
            return raw

    @classmethod
    def from_test_key(cls, material: bytes) -> "MacCustody":
        """TEST-FIXTURE construction — explicitly NOT operational.

        Marks every key ``TEST_FIXTURE`` so no test path can be mistaken
        for genuine custody (operator §1.5: never claim custody is
        operational until real provisioning is verified).
        """
        return cls(_MacKey(material, status="TEST_FIXTURE"))

    # -- signing / verification -------------------------------------------------

    @property
    def current_key_id(self) -> str:
        return self._current.key_id

    @property
    def status(self) -> str:
        return self._current.status

    def sign(self, data: bytes) -> tuple:
        """Sign with the CURRENT key; returns ``(mac_hex, key_id)``."""
        return self._current.sign(data), self._current.key_id

    def key_for(self, key_id: str) -> Optional[_MacKey]:
        for key in (self._current, *self._retired):
            if key.key_id == key_id:
                return key
        return None

    def verify(self, data: bytes, mac: str, key_id: str) -> bool:
        """Constant-time verification under the key identified by
        ``key_id`` (current OR retired — rotation grace)."""
        key = self.key_for(key_id)
        if key is None:
            return False
        return key.verify(data, mac)

    # -- rotation -----------------------------------------------------------------

    def rotate(self, material: bytes) -> str:
        """Promote new key material to CURRENT; demote the previous
        current to retired (verification-only grace). Returns the new
        current key id. The new key inherits the current status."""
        new_key = _MacKey(material, status=self._current.status)
        if new_key.key_id == self._current.key_id:
            raise MacCustodyError(
                "rotation to the same key is a no-op — refused"
            )
        self._retired = (self._current, *self._retired)
        self._current = new_key
        return new_key.key_id

    # -- introspection (no secrets) -------------------------------------------------

    @property
    def key_ids(self) -> tuple:
        """(current, retired...) key ids — fingerprints only."""
        return (self._current.key_id,) + tuple(k.key_id for k in self._retired)

    def __repr__(self) -> str:  # pragma: no cover - safety surface
        return (
            f"MacCustody(current={self._current.key_id!r}, "
            f"retired={list(self.key_ids[1:])!r}, "
            f"status={self._current.status!r})"
        )

    __str__ = __repr__


def keyed_event_mac(
    custody: MacCustody, event_fields: dict
) -> tuple:
    """Compute the keyed event hash over the CANONICAL event fields.

    Mirrors ``ledgers._event_hash``'s field set exactly (ledger,
    event_type, sequence, correlation_id, parent_id, actor,
    payload_hash, prev_hash + the runtime contract version injected by
    the unkeyed path) but signs the canonical bytes with HMAC-SHA256
    under the custody's CURRENT key. Returns ``(mac_hex, key_id)``.
    """
    mac_hex = event_fields_mac(custody._current, event_fields)
    return mac_hex, custody._current.key_id


def event_fields_mac(key, event_fields: dict) -> str:
    """HMAC-SHA256 over the canonical event fields under ONE specific
    key — used both for signing (current key) and for VERIFICATION
    (the key identified by each event's ``mac_key_id``, which may be a
    retired rotation key)."""
    body = dict(event_fields)
    from data_engine.runtime.identity import RUNTIME_CONTRACT_VERSION
    body["contract_version"] = RUNTIME_CONTRACT_VERSION
    return key.sign(canonical_serialize(body))


__all__ = [
    "ENV_KEY_VAR",
    "ENV_KEY_FILE_VAR",
    "MIN_KEY_BYTES",
    "MAC_HEX_LEN",
    "MacCustodyError",
    "MacCustody",
    "keyed_event_mac",
    "event_fields_mac",
]
