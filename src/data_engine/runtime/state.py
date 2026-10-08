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
        """Load the authoritative state; verify journal integrity."""
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
        return payload["state"]

    def verify_journal(self) -> bool:
        return self._journal.verify()


__all__ = [
    "StateStoreError",
    "HashChainJournal",
    "ExecutionStateStore",
]
