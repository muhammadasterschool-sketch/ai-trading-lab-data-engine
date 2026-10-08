"""Runtime observability metrics (mandate §26 / Workstream P).

DESIGN RULES (fail-closed, deterministic, secret-safe)
=======================================================
- Every counter is a KNOWN name (validated tuple below) — unknown
  counters raise, mirroring the ledger/gate fail-closed convention.
- ``snapshot_hash`` is computed over the COUNTERS ONLY, in sorted
  canonical order: two sessions with identical event sequences
  produce identical hashes (replay-safe evidence).
- LATENCY GAUGES ARE DELIBERATELY EXCLUDED from the hash: they are
  wall-clock measurements (time.perf_counter) which are legitimate
  OBSERVABILITY but forbidden identity inputs (INV-01). Gauges are
  never persisted, never exported into runtime identity, and never
  influence any decision.
- No labels, no free-form tag maps: metrics content is counts and
  numbers only — structurally unable to carry secrets.
- Metrics are NOT part of EXECUTION_STATE_SCHEMA persistence (they
  are re-derivable from the authoritative ledgers/memory); this
  keeps the persistence schema and its replay identity unchanged.
"""

import hashlib
import json
from typing import Mapping, Optional

from data_engine.runtime.contracts import RuntimeContractError


class MetricsError(RuntimeContractError):
    """Raised on metrics contract violations."""


#: The known counter vocabulary (fail-closed on unknown names).
COUNTER_NAMES = (
    "bars_processed",
    "bars_refused",
    "bad_bars",
    "warmup_bars",
    "decisions_trade",
    "decisions_hold",
    "no_trade_total",
    "orders_created",
    "orders_risk_rejected",
    "fills",
    "partial_fill_events",
    "kill_switch_trips",
    "halts",
    "reconciliation_mismatches",
    "recovery_events",
    "audit_memory_records",
    "ledger_events",
    "rl_proposals",
    "rl_proposals_vetoed",
    "rl_proposals_ood",
)

#: The known gauge vocabulary (latency observability, unhashed).
GAUGE_NAMES = (
    "cycle_latency_seconds",
    "cycle_latency_seconds_max",
)


class RuntimeMetrics:
    """Deterministic counter registry + unhashed latency gauges."""

    def __init__(self) -> None:
        self._counters: dict = {name: 0 for name in COUNTER_NAMES}
        self._no_trade_reasons: dict = {}
        self._gauges: dict = {name: 0.0 for name in GAUGE_NAMES}

    # ------------------------------------------------------------------
    def increment(self, counter: str, amount: int = 1) -> None:
        if counter not in self._counters:
            raise MetricsError(
                f"unknown counter {counter!r} (allowed: {sorted(COUNTER_NAMES)})"
            )
        if not isinstance(amount, int) or amount < 0:
            raise MetricsError("counter increments must be non-negative ints")
        self._counters[counter] += amount

    def count_no_trade_reason(self, reason: str) -> None:
        """NO_TRADE reason histogram (bounded vocabulary by nature:
        reasons are produced by the decision engine's fixed gate
        set, not free user text)."""
        if not isinstance(reason, str) or not reason.strip():
            raise MetricsError("no-trade reason must be a non-empty string")
        key = reason.strip()[:120]
        self._no_trade_reasons[key] = self._no_trade_reasons.get(key, 0) + 1
        self._counters["no_trade_total"] += 1

    def set_gauge(self, gauge: str, value: float) -> None:
        if gauge not in self._gauges:
            raise MetricsError(
                f"unknown gauge {gauge!r} (allowed: {sorted(GAUGE_NAMES)})"
            )
        if value is None or value != value or value < 0:
            return  # non-finite/negative latency is dropped, not stored
        self._gauges[gauge] = float(value)
        if gauge == "cycle_latency_seconds":
            current_max = self._gauges["cycle_latency_seconds_max"]
            self._gauges["cycle_latency_seconds_max"] = max(current_max, float(value))

    # ------------------------------------------------------------------
    @property
    def counters(self) -> Mapping:
        return dict(self._counters)

    @property
    def no_trade_reasons(self) -> Mapping:
        return dict(self._no_trade_reasons)

    @property
    def gauges(self) -> Mapping:
        return dict(self._gauges)

    def get(self, counter: str) -> int:
        if counter not in self._counters:
            raise MetricsError(f"unknown counter {counter!r}")
        return self._counters[counter]

    # ------------------------------------------------------------------
    def snapshot(self) -> dict:
        """Full observability snapshot (counters + reasons + gauges).

        Deterministic ordering everywhere (sorted keys) so that two
        equal snapshots compare equal as plain dicts.
        """
        return {
            "counters": {k: self._counters[k] for k in sorted(self._counters)},
            "no_trade_reasons": {
                k: self._no_trade_reasons[k]
                for k in sorted(self._no_trade_reasons)
            },
            "gauges": {k: self._gauges[k] for k in sorted(self._gauges)},
        }

    @property
    def snapshot_hash(self) -> str:
        """Deterministic hash over COUNTERS ONLY (replay evidence).

        Gauges are excluded BY DESIGN: latency is wall-clock
        observability, never identity (INV-01). no_trade_reasons are
        included — they are decision-engine gate vocabulary, not
        timing data.
        """
        payload = {
            "counters": {k: self._counters[k] for k in sorted(self._counters)},
            "no_trade_reasons": {
                k: self._no_trade_reasons[k]
                for k in sorted(self._no_trade_reasons)
            },
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"RuntimeMetrics(hash={self.snapshot_hash[:12]}...)"


__all__ = [
    "MetricsError",
    "COUNTER_NAMES",
    "GAUGE_NAMES",
    "RuntimeMetrics",
]
