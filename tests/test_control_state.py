"""v1.0.0 owner-mandate tests — DurableKillSwitch (the REAL STOP
control behind the phone's kill-switch button).

Pins:
- default state is an honest INACTIVE (never a fabricated halt);
- activate() persists ACTIVE + actor + reason and SURVIVES a
  process restart (that is the whole point of "durable");
- an empty reason is refused (the monitoring API already enforces
  this at the boundary — the store enforces it again);
- reset() is the PC-side human path (never reachable from the
  monitoring API) and restores the honest INACTIVE state;
- torn/corrupt state files fail safe to INACTIVE (a crash mid-write
  can never fake an ACTIVE or hide a real one by accident).
"""

import pytest

from data_engine.runtime.control_state import (
    DurableKillSwitch,
    KillSwitchStoreError,
)


class TestStates:
    def test_default_state_is_honest_inactive(self, tmp_path):
        state = DurableKillSwitch(tmp_path / "ks.json").state()
        assert state["state"] == "INACTIVE"
        assert "monitor-only" in state["detail"]

    def test_activate_persists_and_survives_restart(self, tmp_path):
        path = tmp_path / "ks.json"
        store = DurableKillSwitch(path)
        result = store.activate(
            actor="monitoring-client@192.168.0.10",
            reason="owner stop from phone",
        )
        assert result["state"] == "ACTIVE"
        assert result["reason"] == "owner stop from phone"
        assert result["activated_by"] == "monitoring-client@192.168.0.10"
        assert result["activated_at"]
        revived = DurableKillSwitch(path)
        assert revived.state()["state"] == "ACTIVE"
        assert revived.state()["reason"] == "owner stop from phone"

    def test_empty_reason_refused(self, tmp_path):
        store = DurableKillSwitch(tmp_path / "ks.json")
        with pytest.raises(KillSwitchStoreError):
            store.activate(actor="a", reason="   ")
        assert store.state()["state"] == "INACTIVE"

    def test_reason_capped(self, tmp_path):
        store = DurableKillSwitch(tmp_path / "ks.json")
        result = store.activate(actor="a" * 500, reason="r" * 999)
        assert len(result["reason"]) == 256
        assert len(result["activated_by"]) == 128

    def test_reset_restores_inactive(self, tmp_path):
        path = tmp_path / "ks.json"
        store = DurableKillSwitch(path)
        store.activate(actor="phone", reason="stop")
        reset = DurableKillSwitch(path).reset(actor="owner-on-pc")
        assert reset["state"] == "INACTIVE"
        assert reset["activated_by"] == "owner-on-pc"
        assert DurableKillSwitch(path).state()["state"] == "INACTIVE"


class TestFailSafeFiles:
    def test_corrupt_state_file_fails_safe_to_inactive(self, tmp_path):
        path = tmp_path / "ks.json"
        path.write_text("{not json at all", encoding="utf-8")
        assert DurableKillSwitch(path).state()["state"] == "INACTIVE"

    def test_unknown_state_value_fails_safe_to_inactive(self, tmp_path):
        path = tmp_path / "ks.json"
        path.write_text('{"state": "MAYBE"}', encoding="utf-8")
        assert DurableKillSwitch(path).state()["state"] == "INACTIVE"

    def test_missing_directory_created_on_demand(self, tmp_path):
        store = DurableKillSwitch(tmp_path / "deep" / "nested" / "ks.json")
        store.activate(actor="a", reason="r")
        assert (
            DurableKillSwitch(
                tmp_path / "deep" / "nested" / "ks.json"
            ).state()["state"]
            == "ACTIVE"
        )
