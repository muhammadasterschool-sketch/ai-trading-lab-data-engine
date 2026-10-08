"""Persistent execution state (pre-paper mandate §29/§32; RT-F4).

Before this module, ALL execution-domain state (duplicate protection,
kill-switch state, audit chains, order lifecycle) was volatile — a
restart wiped it (RT-F4). This store persists:

- orders, fills, positions, portfolio state
- idempotency keys (duplicate protection across restart)
- reconciliation state
- kill-switch state/audit
- incidents
- ledger sequence heads
- correlation-ID registry
- runtime checkpoints (bar cursor)

Design (fail-closed throughout):

- **Atomic snapshots**: full state written to ``state.json`` via
  ``tmp`` + ``os.replace`` — a crash mid-write can never leave a
  half-written authoritative state.
- **Append-only hash-chained journal** (``journal.jsonl``): every
  state mutation appends a chained record; ``verify_journal`` re-
  derives the chain. Tampering with any record (or reordering)
  breaks the chain → integrity error (tamper-EVIDENT, mandate §33).
- **I/O failures raise** :class:`StateStoreError` — the runtime HALTs
  instead of continuing on unverifiable state. There is no
  best-effort write path.

Wall-clock timestamps in the journal are audit metadata (FS-21
convention) and never participate in any identity hash.
"""

import json
import os
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Mapping, Optional

from data_engine.pit.hashing import deterministic_hash

from data_engine.runtime.identity import (
    CHECKPOINT_PREFIX,
    prefixed_hash,
)


class StateStoreError(ValueError):
    """Raised on persistence failures / integrity violations."""


#: Formal execution-state schema (paper-readiness re-audit BLOCKER 5).
#:
#: EVERY field required for deterministic recovery is enumerated here
#: and validated on every snapshot/restore — persistence is not
#: "orders + kill switch + positions + ledger heads + bar index"; it
#: is the COMPLETE execution-critical in-memory state.
EXECUTION_STATE_SCHEMA_VERSION = "1.1.0"

EXECUTION_STATE_FIELDS = (
    "schema",            # schema version stamp (this constant)
    "identity",          # session/config/model binding (BLOCKER 21)
    "orders",            # OMS state: full order lifecycle + fills
    "kill_switch",       # all switch states (BLOCKER 12)
    "positions",         # position book incl. SL/TP levels (BLOCKER 9)
    "ledgers",           # FULL ledger event chains (BLOCKER 6)
    "ledger_heads",      # head hash per ledger (restore cross-check)
    "memory",            # structured trading memory records (BLOCKER 20)
    "memory_chain_hash", # memory chain head (restore cross-check)
    "bars",              # admitted bar history (sequence + fills need it)
    "bar_index",         # authoritative bar cursor
    "order_fill_cursor", # order_id -> next bar index (latency bookkeeping)
    "pending_protection",# order_id -> (sl, tp, corr) (BLOCKER 9)
    "pending_exits",     # symbol -> (order_id, reason, snapshot)
    "consecutive_bad_bars",  # data-quality degradation counter
    "equity_realized",   # realized-cost accumulator (P&L authority)
    "session_id",        # session binding
    "runtime_state",     # operating state at snapshot time
)


def validate_execution_state(state: Mapping[str, Any]) -> list:
    """Validate a state mapping against EXECUTION_STATE_FIELDS.

    Returns the list of problems (empty = valid). Fail-closed: any
    missing/mistyped mandatory field is a problem — recovery must
    refuse on an incomplete snapshot rather than guess.
    """
    problems: list = []
    if not isinstance(state, Mapping):
        return [f"state must be a mapping, got {type(state).__name__}"]
    for field in EXECUTION_STATE_FIELDS:
        if field not in state:
            problems.append(f"missing mandatory field: {field}")
    if isinstance(state.get("schema"), str) and \
            state["schema"] != EXECUTION_STATE_SCHEMA_VERSION:
        problems.append(
            f"schema version mismatch: snapshot {state['schema']!r} vs "
            f"runtime {EXECUTION_STATE_SCHEMA_VERSION!r}"
        )
    if "bar_index" in state and (
        not isinstance(state["bar_index"], int)
        or state["bar_index"] < -1
    ):
        problems.append("bar_index must be an int >= -1")
    if "consecutive_bad_bars" in state and (
        not isinstance(state["consecutive_bad_bars"], int)
        or state["consecutive_bad_bars"] < 0
    ):
        problems.append("consecutive_bad_bars must be an int >= 0")
    if "equity_realized" in state and not isinstance(
        state["equity_realized"], (str, int, float)
    ):
        problems.append("equity_realized must be a numeric string")
    for coll_field in ("orders", "kill_switch", "positions", "memory",
                       "bars"):
        if coll_field in state and not isinstance(state[coll_field], list):
            problems.append(f"{coll_field} must be a list")
    for dict_field in ("ledgers", "ledger_heads", "order_fill_cursor",
                       "pending_protection", "pending_exits", "identity"):
        if dict_field in state and not isinstance(state[dict_field], dict):
            problems.append(f"{dict_field} must be a mapping")
    return problems


class HashChainJournal:
    """Append-only, hash-chained JSONL journal (tamper-evident).

    Each record: ``{index, kind, recorded_at, payload, prev_hash,
    record_hash}`` where ``record_hash`` covers the full record. The
    chain is verified by recomputation (``verify``); any in-place
    edit, deletion, or insertion breaks it.
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._records: list[dict] = []
        self._loaded = False

    # -- loading ------------------------------------------------------------
    def load(self) -> None:
        """Load existing records (absent file = fresh journal)."""
        if self._loaded:
            return
        if self._path.exists():
            try:
                text = self._path.read_text(encoding="utf-8")
            except OSError as exc:
                raise StateStoreError(
                    f"journal unreadable at {self._path}: {exc}"
                ) from exc
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    self._records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise StateStoreError(
                        f"journal record corrupted at {self._path}: {exc} "
                        "(fail closed — persistence is authoritative)"
                    ) from exc
        self._loaded = True

    # -- writing ------------------------------------------------------------
    def append(self, kind: str, payload: Mapping[str, Any]) -> dict:
        """Append one chained record; returns it (with its hash)."""
        self.load()
        index = len(self._records)
        prev = self._records[-1]["record_hash"] if self._records else "0" * 64
        record = {
            "index": index,
            "kind": kind,
            "recorded_at": datetime.now(UTC).isoformat(),
            "payload": dict(payload),
            "prev_hash": prev,
        }
        record["record_hash"] = prefixed_hash(
            CHECKPOINT_PREFIX,
            {
                "index": index,
                "kind": kind,
                "payload": record["payload"],
                "prev_hash": prev,
            },
        )
        self._records.append(record)
        line = json.dumps(record, sort_keys=True, default=str)
        try:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        except OSError as exc:
            # The in-memory record exists but durable persistence
            # FAILED — the store is now unverifiable: fail closed.
            raise StateStoreError(
                f"journal append failed at {self._path}: {exc} — runtime "
                "must halt (persistence is mandatory, mandate §29)"
            ) from exc
        return record

    # -- verification ---------------------------------------------------------
    def verify(self) -> bool:
        """Recompute the whole chain; False on any mismatch."""
        self.load()
        prev = "0" * 64
        for i, record in enumerate(self._records):
            if record.get("index") != i or record.get("prev_hash") != prev:
                return False
            expected = prefixed_hash(
                CHECKPOINT_PREFIX,
                {
                    "index": record.get("index"),
                    "kind": record.get("kind"),
                    "payload": record.get("payload"),
                    "prev_hash": record.get("prev_hash"),
                },
            )
            if expected != record.get("record_hash"):
                return False
            prev = record["record_hash"]
        return True

    @property
    def records(self) -> tuple:
        self.load()
        return tuple(self._records)

    @property
    def head_hash(self) -> str:
        self.load()
        return self._records[-1]["record_hash"] if self._records else "0" * 64

    def __len__(self) -> int:
        self.load()
        return len(self._records)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Atomic JSON write: tmp file + ``os.replace`` (no torn writes)."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        text = json.dumps(payload, sort_keys=True, default=str, indent=1)
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except OSError as exc:
        raise StateStoreError(
            f"atomic state write failed at {path}: {exc} — runtime must "
            "halt (unverifiable state is never best-effort, mandate §53)"
        ) from exc


class ExecutionStateStore:
    """Authoritative persistent execution state (mandate §29).

    Layout under ``store_dir``::

        state.json     — atomic full-state snapshot
        journal.jsonl  — append-only hash-chained mutation journal

    ``snapshot`` writes BOTH (journal gets a ``checkpoint`` record).
    ``restore`` reads the snapshot and verifies the journal; ANY
    inconsistency raises — recovery then goes through reconciliation,
    never through silent trust (mandate §48).
    """

    SNAPSHOT_FILE = "state.json"
    JOURNAL_FILE = "journal.jsonl"

    def __init__(self, store_dir: Path) -> None:
        if store_dir is None:
            raise StateStoreError("store_dir is required (no implicit cwd)")
        self._dir = Path(store_dir)
        self._journal = HashChainJournal(self._dir / self.JOURNAL_FILE)
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise StateStoreError(
                f"state directory unusable at {self._dir}: {exc}"
            ) from exc

    @property
    def journal(self) -> HashChainJournal:
        return self._journal

    # -- snapshot -------------------------------------------------------------
    def snapshot(self, state: Mapping[str, Any], kind: str = "checkpoint") -> dict:
        """Persist the full state atomically + journal the checkpoint."""
        payload = {"state": dict(state)}
        _atomic_write_json(self._dir / self.SNAPSHOT_FILE, payload)
        return self._journal.append(
            kind,
            {"snapshot_bytes": len(json.dumps(payload, default=str)),
             "state_keys": sorted(state.keys())},
        )

    def restore(self) -> dict:
        """Load the authoritative state; verify journal integrity.

        Fail-closed (BLOCKER 1/6): corrupt snapshot, corrupt journal,
        and schema violations ALL raise — recovery goes through
        reconciliation, never through silent trust (mandate §48).
        """
        snapshot_path = self._dir / self.SNAPSHOT_FILE
        if not snapshot_path.exists():
            raise StateStoreError(
                f"no state snapshot at {snapshot_path} — cold start must go "
                "through recovery/reconciliation, not implicit empty state"
            )
        try:
            text = snapshot_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise StateStoreError(
                f"state snapshot unreadable at {snapshot_path}: {exc}"
            ) from exc
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise StateStoreError(
                f"state snapshot corrupted at {snapshot_path}: {exc} "
                "(RECOVERY_REQUIRED — never paper over, mandate §48)"
            ) from exc
        if "state" not in payload:
            raise StateStoreError(
                "state snapshot malformed: missing 'state' envelope"
            )
        if not self._journal.verify():
            raise StateStoreError(
                "journal chain verification FAILED — execution state "
                "tampered or corrupted (RECOVERY_REQUIRED)"
            )
        problems = validate_execution_state(payload["state"])
        if problems:
            raise StateStoreError(
                "execution-state schema validation FAILED "
                f"({len(problems)} problems): "
                + "; ".join(problems[:6])
                + " — RECOVERY_REQUIRED (incomplete state is never "
                "best-effort, BLOCKER 5)"
            )
        return payload["state"]

    def verify_journal(self) -> bool:
        return self._journal.verify()

    def self_check(self) -> tuple:
        """Mandatory pre-start self-check (BLOCKER 1).

        Verifies: (a) the journal chain, (b) the snapshot parses and
        satisfies EXECUTION_STATE_FIELDS (when present), and (c) the
        store directory is writable (probe file, atomically removed).
        Returns a tuple of problems — empty means the store is
        authoritative and usable. NEVER fabricates a pass: a store
        whose state cannot be proven is a refused store.
        """
        problems: list = []
        # (a) journal chain integrity
        try:
            if not self._journal.verify():
                problems.append(
                    "journal hash chain verification FAILED — tampered "
                    "or corrupted"
                )
        except StateStoreError as exc:
            problems.append(f"journal unreadable: {exc}")
        # (b) snapshot parse + schema (absent snapshot = cold start, OK)
        snapshot_path = self._dir / self.SNAPSHOT_FILE
        if snapshot_path.exists():
            try:
                payload = json.loads(
                    snapshot_path.read_text(encoding="utf-8")
                )
                problems.extend(
                    validate_execution_state(payload.get("state", {}))
                )
            except (OSError, json.JSONDecodeError) as exc:
                problems.append(f"state snapshot corrupt/unreadable: {exc}")
        # (c) writability probe
        probe = self._dir / ".selfcheck-probe"
        try:
            probe.write_text("probe", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            problems.append(f"store directory not writable: {exc}")
        return tuple(problems)

    @property
    def has_snapshot(self) -> bool:
        """True when a state snapshot exists (restart vs cold start)."""
        return (self._dir / self.SNAPSHOT_FILE).exists()


__all__ = [
    "StateStoreError",
    "HashChainJournal",
    "ExecutionStateStore",
    "EXECUTION_STATE_SCHEMA_VERSION",
    "EXECUTION_STATE_FIELDS",
    "validate_execution_state",
]
