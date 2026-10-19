# CUSTOM BROKER ADAPTER — PLUGIN INTERFACE (Stage G, Part 9B G5)

How to add a NEW broker to the AI Trading Lab data engine via
configuration + a documented adapter class. The discipline is
MOCK-FIRST, FAIL-CLOSED, and UNKNOWN = BLOCKED.

> LIVE TRADING REMAINS NOT AUTHORIZED. A "custom broker" in this
> repository is a MOCK/DETERMINISTIC venue (or a paper adapter). A
> REAL execution-mode adapter requires the separate, operator-
> authorized review path (see §5) — it CANNOT be enabled through
> this plugin interface.

## 1. The interface (implement these)

Subclass `data_engine.brokers.interface.BrokerAdapter`
(`src/data_engine/brokers/interface.py`):

| Member | Contract |
| --- | --- |
| `broker_id` (property) | stable unique venue identifier |
| `capabilities` (property) | a `BrokerCapabilities` descriptor — the SINGLE source of truth for what the venue supports |
| `connect(credential)` | bind to EXACTLY ONE account; reject other account ids afterwards; never leak credential material |
| `disconnect()` | idempotent; subsequent calls fail closed |
| `health()` | `ConnectionState`; never raises |
| `account_info()` | normalized info for the CONNECTED account |
| `instrument_spec(symbol)` | normalized `InstrumentSpec`; unknown symbols fail closed (typed error — never a guessed spec) |
| `list_symbols()` | canonical symbols currently served |
| `submit_order(request)` / `cancel_order(...)` / order queries | per `brokers/errors.py`: definitive rejections are REJECTED acks; transport failures raise typed errors; UNKNOWN outcomes raise `UnknownOrderStateError` (journal UNKNOWN + reconcile before retry) |
| idempotency | the same `client_order_id` twice returns the SAME ack, never executes twice |

The fastest path: subclass `DeterministicMockVenue`
(`brokers/adapters/_mock_core.py`) — it implements the whole
deterministic venue engine (journals, fills, rate limits, precision
checks); you supply the capability descriptor + instruments +
venue-specific rejection codes. See `brokers/adapters/paper.py`
(the reference adapter, ~90 lines) and the per-broker mocks
(`binance_mock.py`, `mt5_mock.py`, ...).

## 2. The capability descriptor (declare, never assume)

`BrokerCapabilities` (`brokers/capabilities.py`, frozen pydantic
model): broker_id, execution_mode (MUST be `MOCK_DETERMINISTIC` in
this repository), order_kinds, time_in_force, sl_tp semantics,
position_mode, idempotency mechanism, supports_reduce_only,
account_modes, rate_limit policy, reconciliation style.

Validation is fail-closed at THREE layers (all test-pinned in
`tests/test_paper_mode_selection_proof.py`):
1. the pydantic model refuses REAL execution-mode + REAL account
   descriptors at construction;
2. `DeterministicMockVenue` refuses non-`MOCK_DETERMINISTIC`
   capabilities;
3. `BrokerSession` refuses REAL execution-mode adapters — "live
   trading is NOT AUTHORIZED".

## 3. Registration (the ONLY way a venue becomes routable)

Register the descriptor in a `CapabilityRegistry`
(`brokers/capabilities.py::CapabilityRegistry`):
- registration is startup-only and immutable;
- re-registering the same broker_id with a DIFFERENT descriptor is
  REFUSED (capability drift must be an explicit versioned change);
- an UNREGISTERED broker id is UNKNOWN and therefore BLOCKED:
  `route_order` (brokers/allocation.py, G4) refuses any allocation
  config referencing it; `discover_instruments` refuses catalog
  drift; the OMS venue boundary refuses to attach it.

To register via configuration, add the descriptor module to the
engine's startup registry assembly and register it before the
composition root runs — e.g. extend `default_registry()` or
construct a private registry in your composition and pass it to
`route_order` / session construction. There is NO runtime
self-registration path (an adapter that appears after startup is
UNKNOWN until the next explicit, reviewed startup change).

## 4. Mock-first testing path (MANDATORY for every new adapter)

Ship the adapter with the same test families the existing venues
carry (see `tests/test_broker_session_guards.py`,
`tests/test_broker_adapter_contract.py`,
`tests/test_broker_neutral_core.py`):
1. **contract tests**: capability descriptor matches the actual
   behavior (order kinds, TIF, reduce-only, SL/TP semantics);
2. **guard tests**: absent risk/kill-switch gates refuse everything;
   account isolation; idempotency across restarts; bounded retry;
   UNKNOWN-outcome degradation;
3. **selection-proof membership**: the new adapter appears in the
   vocabulary audit (all shipped adapters MOCK_DETERMINISTIC);
4. **allocation routing**: capability-aware routing includes/excludes
   the venue correctly (extend `test_g4_broker_allocation.py`);
5. **instrument discovery**: catalog + registry sync honors the
   fail-closed contracts (extend `test_broker_instrument_discovery.py`).

## 5. The REAL-adapter review path (out of scope — documented only)

A REAL execution-mode descriptor is structurally refused everywhere
today. Enabling one requires, at minimum: an explicit owner decision
record; a separately-reviewed adapter implementation with
credential custody through the operator channel; TLS-only transport;
venue-side rate-limit reconciliation; and an amendment to the
session construction guard — each its own audited change. NONE of
that exists in this repository, and this plugin interface does not
provide it.

## 6. Worked example (paper-venue style)

```python
# my_broker_mock.py — a new deterministic mock venue
from datetime import datetime
from decimal import Decimal

from data_engine.brokers.adapters._mock_core import DeterministicMockVenue
from data_engine.brokers.capabilities import (
    BrokerCapabilities, ExecutionMode, OrderKind, TimeInForce,
)
from data_engine.brokers.models import InstrumentSpec

MY_BROKER_CAPABILITIES = BrokerCapabilities(
    broker_id="my-broker-mock",
    display_name="My Broker (deterministic mock)",
    execution_mode=ExecutionMode.MOCK_DETERMINISTIC,
    order_kinds=(OrderKind.MARKET, OrderKind.LIMIT),
    time_in_force=(OrderKind.GTC and (TimeInForce.GTC,)) or (TimeInForce.GTC,),
    supports_reduce_only=False,
    account_modes=(AccountMode.DEMO,),
)

class MyBrokerMockAdapter(DeterministicMockVenue):
    def __init__(self, clock):
        super().__init__(
            capabilities=MY_BROKER_CAPABILITIES,
            instruments=(InstrumentSpec(...),),
            initial_balances={"USD": Decimal("100000")},
            currency="USD",
            clock=clock,
        )

    # venue-native rejection codes (optional override)
    def _unknown_symbol_code(self) -> str:
        return "MY_BROKER_UNKNOWN_SYMBOL"
```

Then: register `MY_BROKER_CAPABILITIES` in your registry at startup;
add it to an `AllocationConfig` entry (weights sum to exactly 1);
write the five test families from §4; run the FULL suite.
