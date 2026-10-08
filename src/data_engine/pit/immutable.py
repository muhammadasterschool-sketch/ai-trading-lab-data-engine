"""Deep-immutability containers for frozen record models (BUG-008).

The pre-paper forensic AST sweep (``pp_frozen_mutable_sweep.py``)
found mutable ``dict``/``list`` fields inside ``frozen=True`` pydantic
models across the non-frozen packages: ``model_config = frozen`` only
pins attribute REASSIGNMENT — the containers themselves stayed
mutable, so external mutation of returned records was possible with
no integrity alarm.

This module closes that gap for the migrated record models. It lives
inside the PIT package deliberately: PIT is the foundational
correctness layer (the layering guard ``test_no_phase3_imports_in_pit``
permits pit modules to import only from ``data_engine.pit``), and the
frozen containers protect identity-bearing payload data — a
point-in-time correctness primitive.

The containers are dict/list SUBCLASSES whose mutating methods raise
``TypeError``, which means:

- full read API compatibility (indexing, iteration, ``len``,
  ``in``, slicing, ``.get``/``.keys``/``.items``/``.values``);
- equality against plain dicts/lists is preserved (inherited
  ``__eq__``);
- serialization is unchanged — ``json.dumps`` and the PIT
  ``canonical_serialize`` treat them identically to plain containers,
  so every existing hash (``know42.``/``expo8.``/``port8.``/``pred.``)
  is byte-stable across the migration (verified in the P1 suite);
- construction deep-copies the caller's container (and recursively
  freezes nested containers), so caller-reference mutation and nested
  in-place mutation both fail closed.

Deliberate exclusions (recorded in the correction-window report):
frozen Phase-3 ``strategy/`` fields (frozen contract — adapters will
wrap them at the runtime boundary) and the four ``schemas.py`` fields
pinned by the SUB-18 manifest (the P1 authorization forbids manifest
changes). Fields annotated ``frozenset``/enum types were sweep
false positives — they are already immutable.
"""

from typing import Any


def _immutable(self: Any, *args: Any, **kwargs: Any) -> Any:
    raise TypeError(
        f"{type(self).__name__} is immutable (BUG-008 deep-immutability): "
        "record containers of frozen models cannot be mutated in place"
    )


class FrozenDict(dict):
    """A dict whose mutation methods raise ``TypeError``.

    Reads behave exactly like ``dict`` (including equality with plain
    dicts and JSON/canonical serialization). All writes raise.
    """

    __slots__ = ()

    __setitem__ = _immutable
    __delitem__ = _immutable
    pop = _immutable
    popitem = _immutable
    clear = _immutable
    update = _immutable
    setdefault = _immutable


class FrozenList(list):
    """A list whose mutation methods raise ``TypeError``.

    Reads behave exactly like ``list`` (including equality with plain
    lists and JSON/canonical serialization). All writes raise.
    """

    __slots__ = ()

    __setitem__ = _immutable
    __delitem__ = _immutable
    append = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    clear = _immutable
    sort = _immutable
    reverse = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable


def freeze(value: Any) -> Any:
    """Recursively convert plain dicts/lists to frozen containers.

    ``dict`` -> :class:`FrozenDict`, ``list`` -> :class:`FrozenList`,
    applied recursively through nested containers; every other value
    (``tuple``, scalar, model, enum, ...) passes through unchanged —
    tuples are already immutable shells and non-container values are
    none of this function's business. The result never shares a
    mutable container with the input.
    """
    if isinstance(value, dict):
        return FrozenDict({k: freeze(v) for k, v in value.items()})
    if isinstance(value, list):
        return FrozenList([freeze(v) for v in value])
    return value


__all__ = ["FrozenDict", "FrozenList", "freeze"]
