"""Exact symbol-map tests — observed metadata only, digest re-checks."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import SecretStr

from fake_mt5_lab import FakeMT5Module
from data_engine.platform.mt5_symbol_map import (
    MT5SymbolMap,
    MT5SymbolMapError,
    SymbolMapEntry,
    spec_digest,
)
from data_engine.platform.mt5_terminal import (
    MT5TerminalConfig,
    RealMT5Terminal,
)

NOW = datetime(2026, 10, 23, 12, 0, 0, tzinfo=UTC)


def make_terminal(fake: FakeMT5Module | None = None) -> RealMT5Terminal:
    fake = fake or FakeMT5Module()
    config = MT5TerminalConfig(
        login=88012345,
        password=SecretStr("dummy-pass-not-real"),
        server="Exness-MT5Trial8",
    )
    return RealMT5Terminal(config, module=fake)


PROPOSALS = (
    SymbolMapEntry(canonical="EURUSD", broker_symbol="EURUSDm"),
    SymbolMapEntry(canonical="GOLD", broker_symbol="XAUUSD"),
)


class TestValidation:
    def test_happy_path_builds_digest_stamped_entries(self):
        terminal = make_terminal()
        mapping = MT5SymbolMap.validate(PROPOSALS, terminal, NOW)
        assert len(mapping) == 2
        entry = mapping.resolve("EURUSD")
        assert entry.broker_symbol == "EURUSDm"
        assert entry.observed.digits == 5
        assert entry.observed.trade_contract_size == 100000.0
        assert len(entry.spec_sha256) == 64
        assert entry.verified_at == NOW

    def test_unobserved_broker_symbol_refused(self):
        terminal = make_terminal()
        with pytest.raises(MT5SymbolMapError) as excinfo:
            MT5SymbolMap.validate(
                (SymbolMapEntry(canonical="US500", broker_symbol="US500"),),
                terminal,
                NOW,
            )
        assert "NOT observed" in str(excinfo.value)
        assert "never assume" in str(excinfo.value)

    def test_identity_mapping_allowed_via_observation(self):
        terminal = make_terminal()  # XAUUSD exists unsuffixed
        mapping = MT5SymbolMap.validate(
            (SymbolMapEntry(canonical="XAUUSD", broker_symbol="XAUUSD"),),
            terminal,
            NOW,
        )
        assert mapping.broker_symbol("XAUUSD") == "XAUUSD"

    def test_identity_mapping_refused_when_not_observed(self):
        terminal = make_terminal()  # EURUSD (unsuffixed) absent
        with pytest.raises(MT5SymbolMapError):
            MT5SymbolMap.validate(
                (SymbolMapEntry(canonical="EURUSD", broker_symbol="EURUSD"),),
                terminal,
                NOW,
            )

    def test_duplicate_canonical_refused(self):
        terminal = make_terminal()
        with pytest.raises(MT5SymbolMapError) as excinfo:
            MT5SymbolMap.validate(
                PROPOSALS
                + (SymbolMapEntry(canonical="EURUSD", broker_symbol="GBPUSDm"),),
                terminal,
                NOW,
            )
        assert "duplicate canonical" in str(excinfo.value)

    def test_ambiguous_broker_symbol_refused(self):
        terminal = make_terminal()
        with pytest.raises(MT5SymbolMapError) as excinfo:
            MT5SymbolMap.validate(
                (
                    SymbolMapEntry(canonical="A", broker_symbol="EURUSDm"),
                    SymbolMapEntry(canonical="B", broker_symbol="EURUSDm"),
                ),
                terminal,
                NOW,
            )
        assert "more than one canonical" in str(excinfo.value)

    def test_empty_proposal_refused(self):
        terminal = make_terminal()
        with pytest.raises(MT5SymbolMapError):
            MT5SymbolMap.validate((), terminal, NOW)

    def test_empty_map_refused(self):
        with pytest.raises(MT5SymbolMapError):
            MT5SymbolMap(())

    def test_incomplete_observation_refused(self):
        fake = FakeMT5Module()
        broken = fake._catalogue["US30"]
        fake._catalogue["US30"] = {
            k: v for k, v in broken.items() if k != "digits"
        }
        terminal = make_terminal(fake)
        with pytest.raises(MT5SymbolMapError) as excinfo:
            MT5SymbolMap.validate(
                (SymbolMapEntry(canonical="US30", broker_symbol="US30"),),
                terminal,
                NOW,
            )
        assert "incomplete observation" in str(excinfo.value)


class TestRecheck:
    def test_recheck_passes_when_specs_unchanged(self):
        terminal = make_terminal()
        mapping = MT5SymbolMap.validate(PROPOSALS, terminal, NOW)
        mapping.recheck(terminal)  # must not raise

    def test_spec_drift_refused(self):
        fake = FakeMT5Module()
        terminal = make_terminal(fake)
        mapping = MT5SymbolMap.validate(PROPOSALS, terminal, NOW)
        # broker-side contract-size change (e.g. account family switch)
        fake._catalogue["EURUSDm"]["trade_contract_size"] = 1000.0
        with pytest.raises(MT5SymbolMapError) as excinfo:
            mapping.recheck(terminal)
        assert "CHANGED" in str(excinfo.value)
        assert "re-validates" in str(excinfo.value)

    def test_symbol_removal_refused(self):
        fake = FakeMT5Module()
        terminal = make_terminal(fake)
        mapping = MT5SymbolMap.validate(PROPOSALS, terminal, NOW)
        del fake._catalogue["XAUUSD"]
        with pytest.raises(MT5SymbolMapError) as excinfo:
            mapping.recheck(terminal)
        assert "no longer observed" in str(excinfo.value)

    def test_digest_is_sensitive_to_observed_fields(self):
        from data_engine.platform.mt5_symbol_map import ObservedSymbolSpec

        base = ObservedSymbolSpec(
            name="EURUSDm",
            digits=5,
            point=0.00001,
            trade_contract_size=100000.0,
            currency_profit="USD",
            path="Forex\\Majors",
            description="Euro vs US Dollar",
        )
        changed = base.model_copy(update={"digits": 4})
        assert spec_digest(base) != spec_digest(changed)
        # deterministic: identical observation → identical digest
        assert spec_digest(base) == spec_digest(
            ObservedSymbolSpec(
                name="EURUSDm",
                digits=5,
                point=0.00001,
                trade_contract_size=100000.0,
                currency_profit="USD",
                path="Forex\\Majors",
                description="Euro vs US Dollar",
            )
        )


class TestPersistence:
    def test_json_round_trip_preserves_digests(self):
        terminal = make_terminal()
        mapping = MT5SymbolMap.validate(PROPOSALS, terminal, NOW)
        text = mapping.to_json()
        loaded = MT5SymbolMap.load_json(text)
        assert len(loaded) == 2
        assert (
            loaded.resolve("EURUSD").spec_sha256
            == mapping.resolve("EURUSD").spec_sha256
        )
        # a loaded map still re-verifies against the live terminal
        loaded.recheck(terminal)

    def test_invalid_json_refused(self):
        with pytest.raises(MT5SymbolMapError):
            MT5SymbolMap.load_json("{not json")

    def test_invalid_entries_refused(self):
        with pytest.raises(MT5SymbolMapError):
            MT5SymbolMap.load_json('{"entries": [{"nope": 1}]}')

    def test_proposal_loader(self):
        import json

        text = json.dumps(
            {
                "entries": [
                    {"canonical": "EURUSD", "broker_symbol": "EURUSDm"}
                ]
            }
        )
        proposals = MT5SymbolMap.proposals_from_json(text)
        assert proposals[0].broker_symbol == "EURUSDm"

    def test_proposal_loader_rejects_garbage(self):
        with pytest.raises(MT5SymbolMapError):
            MT5SymbolMap.proposals_from_json("[]")
        with pytest.raises(MT5SymbolMapError):
            MT5SymbolMap.proposals_from_json('{"entries": [{"x": 1}]}')


class TestResolve:
    def test_unknown_canonical_lists_known(self):
        terminal = make_terminal()
        mapping = MT5SymbolMap.validate(PROPOSALS, terminal, NOW)
        with pytest.raises(MT5SymbolMapError) as excinfo:
            mapping.resolve("US30")
        assert "US30" in str(excinfo.value)
        assert "EURUSD" in str(excinfo.value)
