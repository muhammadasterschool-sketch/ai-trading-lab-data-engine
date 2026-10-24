"""Exact canonical→broker symbol mapping — OBSERVED metadata only.

The genuine Exness MT5 feed must never assume broker symbol names or
contract specifications (Exness account families use different symbol
suffixes; other MT5 brokers differ again). This module therefore makes
an assumption IMPOSSIBLE:

- The operator authors a *proposal* list of
  :class:`SymbolMapEntry` (canonical → broker_symbol) — typically after
  inspecting the live catalogue via ``data-engine mt5-probe
  --dump-catalogue``.
- :meth:`MT5SymbolMap.validate` accepts a proposal ONLY when every
  broker symbol is POSITIVELY observed through the connected
  terminal's ``symbol_info`` — the validated entry records the observed
  specification (digits, point, trade_contract_size, description,
  path, currency_profit) plus a SHA-256 digest of that observation.
- At every feed connect the validated map is RE-CHECKED against the
  live terminal: any observed-spec drift (digest mismatch) refuses the
  feed until the operator re-validates. A broker-side symbol change
  can never silently flow into the paper runtime.
- Identity mappings (canonical == broker symbol) are allowed but pass
  through exactly the same positive observation — no bypass.

Map files live OUTSIDE the repository (operator artifacts); nothing in
this module reads or writes credentials.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Optional, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "MT5SymbolMapError",
    "SymbolMapEntry",
    "ObservedSymbolSpec",
    "ValidatedSymbolEntry",
    "MT5SymbolMap",
    "spec_digest",
]

#: Observed symbol_info fields pinned into a validated entry (digest
#: input). Deliberately SMALL and stable — identity/quality fields, not
#: everything the broker returns.
_DIGEST_FIELDS = (
    "name",
    "digits",
    "point",
    "trade_contract_size",
    "currency_profit",
    "path",
    "description",
)


class MT5SymbolMapError(RuntimeError):
    """Symbol mapping invalid/refused (fail closed)."""

    code = "MT5_E_SYMBOL_MAP_INVALID"


def spec_digest(observed: "ObservedSymbolSpec") -> str:
    """Deterministic SHA-256 over the pinned observed-spec fields."""
    payload = json.dumps(
        {
            "name": observed.name,
            "digits": observed.digits,
            "point": observed.point,
            "trade_contract_size": observed.trade_contract_size,
            "currency_profit": observed.currency_profit,
            "path": observed.path,
            "description": observed.description,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class ObservedSymbolSpec(BaseModel):
    """Symbol specification OBSERVED from a connected terminal."""

    model_config = ConfigDict(frozen=True)

    name: str
    digits: int
    point: float
    trade_contract_size: float
    currency_profit: str = ""
    path: str = ""
    description: str = ""


class SymbolMapEntry(BaseModel):
    """Operator-proposed mapping (NOT trusted until validated)."""

    model_config = ConfigDict(frozen=True)

    canonical: str = Field(..., min_length=1)
    broker_symbol: str = Field(..., min_length=1)


class ValidatedSymbolEntry(BaseModel):
    """A mapping positively verified against observed terminal metadata."""

    model_config = ConfigDict(frozen=True)

    canonical: str
    broker_symbol: str
    observed: ObservedSymbolSpec
    spec_sha256: str
    verified_at: datetime


class _TerminalLike(Protocol):
    """The terminal surface the map needs (narrow, read-only)."""

    def symbol_info(self, symbol: str) -> Optional[dict[str, Any]]: ...


def _observed_from_info(broker_symbol: str, info: dict[str, Any]) -> ObservedSymbolSpec:
    """Build an ObservedSymbolSpec from a symbol_info dict.

    Missing optional fields are empty, never invented; missing REQUIRED
    numeric fields refuse validation.
    """
    missing = [
        f
        for f in ("name", "digits", "point", "trade_contract_size")
        if info.get(f) is None
    ]
    if missing:
        raise MT5SymbolMapError(
            f"MT5_E_SYMBOL_MAP_INVALID: symbol_info for "
            f"{broker_symbol!r} lacks required field(s) {missing} — "
            f"refusing to validate a mapping from incomplete observation"
        )
    return ObservedSymbolSpec(
        name=str(info["name"]),
        digits=int(info["digits"]),
        point=float(info["point"]),
        trade_contract_size=float(info["trade_contract_size"]),
        currency_profit=str(info.get("currency_profit", "") or ""),
        path=str(info.get("path", "") or ""),
        description=str(info.get("description", "") or ""),
    )


class MT5SymbolMap:
    """Validated canonical→broker symbol map (immutable once built)."""

    def __init__(self, entries: tuple[ValidatedSymbolEntry, ...]) -> None:
        if not entries:
            raise MT5SymbolMapError(
                "MT5_E_SYMBOL_MAP_INVALID: an empty symbol map is not a "
                "valid map — declare at least one observed mapping"
            )
        by_canonical: dict[str, ValidatedSymbolEntry] = {}
        by_broker: dict[str, ValidatedSymbolEntry] = {}
        for entry in entries:
            if entry.canonical in by_canonical:
                raise MT5SymbolMapError(
                    f"MT5_E_SYMBOL_MAP_INVALID: duplicate canonical "
                    f"{entry.canonical!r} in map"
                )
            if entry.broker_symbol in by_broker:
                raise MT5SymbolMapError(
                    f"MT5_E_SYMBOL_MAP_INVALID: broker symbol "
                    f"{entry.broker_symbol!r} maps to more than one "
                    f"canonical identity — refusing ambiguity"
                )
            by_canonical[entry.canonical] = entry
            by_broker[entry.broker_symbol] = entry
        self._entries = entries
        self._by_canonical = by_canonical
        self._by_broker = by_broker

    # -- construction ------------------------------------------------------
    @classmethod
    def validate(
        cls,
        proposals: Sequence[SymbolMapEntry],
        terminal: _TerminalLike,
        verified_at: datetime,
    ) -> "MT5SymbolMap":
        """Validate a proposal against OBSERVED terminal metadata.

        Every broker symbol must be positively returned by
        ``terminal.symbol_info``; anything else is a structured refusal.
        """
        if not proposals:
            raise MT5SymbolMapError(
                "MT5_E_SYMBOL_MAP_INVALID: empty proposal — nothing to "
                "validate (declare canonical→broker pairs after "
                "inspecting the live catalogue)"
            )
        validated: list[ValidatedSymbolEntry] = []
        for proposal in proposals:
            canonical = proposal.canonical.strip()
            broker = proposal.broker_symbol.strip()
            if not canonical or not broker:
                raise MT5SymbolMapError(
                    "MT5_E_SYMBOL_MAP_INVALID: blank canonical or broker "
                    "symbol in proposal"
                )
            info = terminal.symbol_info(broker)
            if not info:
                raise MT5SymbolMapError(
                    f"MT5_E_SYMBOL_MAP_INVALID: broker symbol "
                    f"{broker!r} (canonical {canonical!r}) was NOT "
                    f"observed on the connected terminal — never assume "
                    f"a symbol exists; inspect the live catalogue and "
                    f"fix the map"
                )
            observed = _observed_from_info(broker, info)
            validated.append(
                ValidatedSymbolEntry(
                    canonical=canonical,
                    broker_symbol=broker,
                    observed=observed,
                    spec_sha256=spec_digest(observed),
                    verified_at=verified_at,
                )
            )
        return cls(tuple(validated))

    # -- queries ------------------------------------------------------------
    def resolve(self, canonical: str) -> ValidatedSymbolEntry:
        entry = self._by_canonical.get(canonical)
        if entry is None:
            raise MT5SymbolMapError(
                f"MT5_E_SYMBOL_MAP_INVALID: canonical {canonical!r} is "
                f"not in the validated map (known: "
                f"{sorted(self._by_canonical)}) — refusing to guess a "
                f"broker symbol"
            )
        return entry

    def broker_symbol(self, canonical: str) -> str:
        return self.resolve(canonical).broker_symbol

    def entries(self) -> tuple[ValidatedSymbolEntry, ...]:
        return self._entries

    def __len__(self) -> int:
        return len(self._entries)

    # -- re-verification ------------------------------------------------------
    def recheck(self, terminal: _TerminalLike) -> None:
        """Re-validate every entry against the LIVE terminal.

        Called at every feed connect: broker-side spec drift (digits,
        point, contract size, name/path changes…) refuses the feed
        until the operator re-validates. This is what makes the mapping
        *exact* rather than assumed.
        """
        for entry in self._entries:
            info = terminal.symbol_info(entry.broker_symbol)
            if not info:
                raise MT5SymbolMapError(
                    f"MT5_E_SYMBOL_MAP_INVALID: previously validated "
                    f"broker symbol {entry.broker_symbol!r} (canonical "
                    f"{entry.canonical!r}) is no longer observed on the "
                    f"terminal — refusing to fetch; re-validate the map"
                )
            observed = _observed_from_info(entry.broker_symbol, info)
            current_digest = spec_digest(observed)
            if current_digest != entry.spec_sha256:
                raise MT5SymbolMapError(
                    f"MT5_E_SYMBOL_MAP_INVALID: observed specification "
                    f"of {entry.broker_symbol!r} CHANGED since "
                    f"validation (expected digest {entry.spec_sha256[:12]}…, "
                    f"observed {current_digest[:12]}…) — refusing until "
                    f"the operator re-validates the symbol map"
                )

    # -- persistence (operator artifacts OUTSIDE the repo) ---------------------
    def to_json(self) -> str:
        return json.dumps(
            {
                "map_version": 1,
                "entries": [e.model_dump(mode="json") for e in self._entries],
            },
            indent=2,
            sort_keys=True,
        )

    @classmethod
    def load_json(cls, text: str) -> "MT5SymbolMap":
        """Load a previously VALIDATED map file (digests preserved).

        The loaded map is still re-checked against the live terminal at
        connect — the file is a carrier, not a source of trust.
        """
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MT5SymbolMapError(
                f"MT5_E_SYMBOL_MAP_INVALID: map file is not valid JSON: "
                f"{exc}"
            ) from exc
        try:
            entries = tuple(
                ValidatedSymbolEntry.model_validate(e)
                for e in payload.get("entries", [])
            )
        except Exception as exc:  # noqa: BLE001 — pydantic errors surfaced
            raise MT5SymbolMapError(
                f"MT5_E_SYMBOL_MAP_INVALID: map file entries invalid: {exc}"
            ) from exc
        return cls(entries)

    @classmethod
    def proposals_from_json(cls, text: str) -> tuple[SymbolMapEntry, ...]:
        """Load an operator-authored PROPOSAL file (canonical/broker)."""
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MT5SymbolMapError(
                f"MT5_E_SYMBOL_MAP_INVALID: proposal file is not valid "
                f"JSON: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise MT5SymbolMapError(
                "MT5_E_SYMBOL_MAP_INVALID: proposal file must be a JSON "
                "object with an 'entries' list"
            )
        raw_entries = payload.get("entries", payload)
        if not isinstance(raw_entries, list):
            raise MT5SymbolMapError(
                "MT5_E_SYMBOL_MAP_INVALID: proposal file must hold an "
                "'entries' list"
            )
        try:
            return tuple(
                SymbolMapEntry.model_validate(e) for e in raw_entries
            )
        except Exception as exc:  # noqa: BLE001
            raise MT5SymbolMapError(
                f"MT5_E_SYMBOL_MAP_INVALID: proposal entries invalid: {exc}"
            ) from exc
