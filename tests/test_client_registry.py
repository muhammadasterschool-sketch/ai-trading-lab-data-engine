"""v1.0.0 owner-mandate tests — ClientRegistry (who is connected /
who ever registered) + durable registration ledger.

Pins:
- observe() upserts sessions keyed by (kind, name, email) and bumps
  request counters;
- the ONLINE verdict follows the injectable window;
- the registration ledger records FIRST contact exactly once per
  identity and SURVIVES a process restart (durable registrations.json);
- self-reported identity material is stripped and length-capped
  (a hostile/broken client cannot grow records without bound);
- unknown kinds collapse to "other"; anonymous clients are still
  observed (IP-keyed noise the owner can SEE);
- evictions keep the ledger bounded at max_records.
"""

import threading

import pytest

from data_engine.runtime.registry import (
    ClientRegistry,
    ClientRegistryError,
)


class TestObserveAndUsers:
    def test_observe_upserts_and_counts_requests(self, tmp_path):
        registry = ClientRegistry(tmp_path, clock=lambda: 1000.0)
        registry.observe(
            client_ip="192.168.0.10",
            name="owner-phone",
            email="owner@gmail.com",
            kind="monitor",
            device="Pixel",
            now=1000.0,
        )
        registry.observe(
            client_ip="192.168.0.10",
            name="owner-phone",
            email="owner@gmail.com",
            kind="monitor",
            device="Pixel",
            now=1010.0,
        )
        users = registry.users(now=1011.0)
        assert len(users) == 1
        row = users[0]
        assert row["name"] == "owner-phone"
        assert row["email"] == "owner@gmail.com"
        assert row["kind"] == "monitor"
        assert row["requests"] == 2
        assert row["online"] is True
        assert row["seconds_since_seen"] == 1.0

    def test_online_window_is_injectable(self, tmp_path):
        registry = ClientRegistry(
            tmp_path, online_window_seconds=30.0, clock=lambda: 2000.0
        )
        registry.observe(
            client_ip="10.0.0.1",
            name="stale-client",
            email="",
            kind="monitor",
            device="",
            now=2000.0,
        )
        users = registry.users(now=2029.0)
        assert users[0]["online"] is True
        users = registry.users(now=2031.0)
        assert users[0]["online"] is False

    def test_distinct_identities_are_distinct_rows(self, tmp_path):
        registry = ClientRegistry(tmp_path, clock=lambda: 3000.0)
        for index in range(3):
            registry.observe(
                client_ip="10.0.0.9",
                name=f"client-{index}",
                email=f"c{index}@lab.test",
                kind="monitor",
                device="",
                now=3000.0 + index,
            )
        assert len(registry.users(now=3001.0)) == 3

    def test_users_sorted_newest_seen_first(self, tmp_path):
        registry = ClientRegistry(tmp_path, clock=lambda: 5000.0)
        registry.observe(
            client_ip="10.0.0.1", name="old", email="", kind="monitor",
            device="", now=5000.0,
        )
        registry.observe(
            client_ip="10.0.0.2", name="new", email="", kind="monitor",
            device="", now=5050.0,
        )
        users = registry.users(now=5051.0)
        assert users[0]["name"] == "new"
        assert users[1]["name"] == "old"


class TestIdentityHygiene:
    def test_fields_are_stripped_and_capped(self, tmp_path):
        registry = ClientRegistry(tmp_path, clock=lambda: 1000.0)
        registry.observe(
            client_ip="10.0.0.1",
            name="  " + "x" * 500 + "  ",
            email="a@b.c",
            kind="monitor",
            device="d" * 500,
            now=1000.0,
        )
        row = registry.users(now=1001.0)[0]
        assert row["name"] == "x" * 128
        assert row["device"] == "d" * 128

    def test_unknown_kind_collapses_to_other(self, tmp_path):
        registry = ClientRegistry(tmp_path, clock=lambda: 1000.0)
        registry.observe(
            client_ip="10.0.0.1", name="weird", email="", kind="root-kit",
            device="", now=1000.0,
        )
        assert registry.users(now=1001.0)[0]["kind"] == "other"

    def test_anonymous_client_still_observed(self, tmp_path):
        registry = ClientRegistry(tmp_path, clock=lambda: 1000.0)
        registry.observe(
            client_ip="10.0.0.77", name="", email="", kind="", device="",
            now=1000.0,
        )
        row = registry.users(now=1001.0)[0]
        assert row["name"] == ""
        assert row["ip"] == "10.0.0.77"


class TestRegistrationLedger:
    def test_first_contact_recorded_once_and_durable(self, tmp_path):
        registry = ClientRegistry(tmp_path, clock=lambda: 1000.0)
        for _ in range(3):
            registry.observe(
                client_ip="10.0.0.1", name="owner", email="o@l.t",
                kind="monitor", device="P", now=1000.0,
            )
        assert len(registry.registrations()) == 1
        registry.flush()
        revived = ClientRegistry(tmp_path, clock=lambda: 2000.0)
        rows = revived.registrations()
        assert len(rows) == 1
        assert rows[0]["name"] == "owner"
        assert rows[0]["kind"] == "monitor"

    def test_registrations_newest_first(self, tmp_path):
        registry = ClientRegistry(tmp_path, clock=lambda: 1000.0)
        registry.observe(
            client_ip="10.0.0.1", name="first", email="", kind="monitor",
            device="", now=1000.0,
        )
        registry.observe(
            client_ip="10.0.0.2", name="second", email="", kind="admin",
            device="", now=2000.0,
        )
        rows = registry.registrations()
        assert rows[0]["name"] == "second"

    def test_ledger_bounded_by_max_records(self, tmp_path):
        registry = ClientRegistry(
            tmp_path, max_records=5, flush_interval_seconds=1.0,
            clock=lambda: 1000.0,
        )
        for index in range(12):
            registry.observe(
                client_ip="10.0.0.1", name=f"c{index}", email="",
                kind="monitor", device="", now=1000.0 + index,
            )
            registry.flush()
        assert len(registry.registrations()) == 5


class TestContract:
    def test_invalid_construction_refused(self, tmp_path):
        with pytest.raises(ClientRegistryError):
            ClientRegistry(tmp_path, online_window_seconds=0)
        with pytest.raises(ClientRegistryError):
            ClientRegistry(tmp_path, flush_interval_seconds=-1)
        with pytest.raises(ClientRegistryError):
            ClientRegistry(tmp_path, max_records=0)

    def test_concurrent_observation_is_thread_safe(self, tmp_path):
        registry = ClientRegistry(tmp_path, clock=lambda: 1000.0)

        def worker(index: int) -> None:
            for round_index in range(20):
                registry.observe(
                    client_ip="10.0.0.1",
                    name=f"c{index}",
                    email="",
                    kind="monitor",
                    device="",
                    now=1000.0 + round_index,
                )

        threads = [
            threading.Thread(target=worker, args=(i,)) for i in range(8)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert len(registry.users(now=2000.0)) == 8
        assert sum(r["requests"] for r in registry.users(now=2000.0)) == 160
