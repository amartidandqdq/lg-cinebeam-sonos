"""Recovery is the main loop's explicit state machine: pure transitions, no network or clock."""
import json

import pytest
from test_main_loop import sim  # noqa: F401  (fixture reuse)


@pytest.fixture
def rec(watcher, monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "LOG_FILE", tmp_path / "w.log")
    for name in ("AUTO_RECOVER_BLIPS", "AUTO_RECOVER_DROPS", "MENU_FALLBACK"):
        monkeypatch.setattr(watcher, name, False)
    return watcher.Recovery()


def failed(watcher):
    return watcher.RouteResult("FAILED", "output_rolled_back", "tv_speaker")


def test_startup_observes_once_and_never_connects(watcher, rec):
    assert rec.phase is watcher.Phase.STARTUP_OBSERVE
    assert rec.on_reading("tv_speaker") is False
    assert (rec.phase, rec.reason) == (watcher.Phase.WATCH, "startup_observation")
    assert rec.on_reading("tv_speaker") is False


def test_power_cycle_recovers_then_retry_ladder_then_gives_up(watcher, rec):
    rec.power_off()
    assert rec.phase is watcher.Phase.OFF
    rec.power_on()
    assert rec.phase is watcher.Phase.RECOVER and not rec.luna_only
    now = 0.0
    for delay in watcher.RETRY_DELAYS:
        assert rec.on_reading("tv_speaker") is True
        rec.on_round(failed(watcher), now)
        assert rec.phase is watcher.Phase.RETRY_WAIT
        assert rec.waiting(now + delay - 1)
        now += delay
        assert not rec.waiting(now) and rec.phase is watcher.Phase.RECOVER
    assert rec.on_reading("tv_speaker") is True
    rec.on_round(failed(watcher), now)
    assert (rec.phase, rec.reason) == (watcher.Phase.WATCH, "retries_exhausted")
    assert rec.on_reading("tv_speaker") is False


def test_other_output_is_respected_from_any_recovery_phase(watcher, rec):
    rec.power_on()
    assert rec.on_reading("external_arc") is False
    assert (rec.phase, rec.reason) == (watcher.Phase.WATCH, "other_output_respected")


def test_confirmed_drop_reopens_recovery_luna_only(watcher, rec, monkeypatch):
    monkeypatch.setattr(watcher, "AUTO_RECOVER_DROPS", True)
    rec.power_on()
    rec.on_reading("bt_soundbar")
    assert rec.phase is watcher.Phase.WATCH
    assert rec.on_reading("tv_speaker") is False  # first read only suspects a drop
    assert rec.on_reading("tv_speaker") is True
    assert (rec.phase, rec.reason, rec.luna_only, rec.drops) == (watcher.Phase.RECOVER, "bt_route_dropped", True, 1)
    assert rec.methods() == ["luna", "luna"]


def test_transitions_are_logged_once_per_change(watcher, rec):
    rec.on_reading("bt_soundbar")
    rec.on_reading("bt_soundbar")
    rec.power_off()
    log = watcher.LOG_FILE.read_text()
    assert log.count("state=STARTUP_OBSERVE->WATCH reason=startup_observation") == 1
    assert log.count("state=WATCH->OFF reason=power_off") == 1
    assert log.count("state=") == 2


def test_snapshot_reports_retry_time_without_private_values(watcher, rec):
    rec.power_on()
    rec.on_reading("tv_speaker")
    rec.on_round(failed(watcher), 0.0)
    state = rec.snapshot(5.0)
    assert state["phase"] == "RETRY_WAIT" and state["failed_rounds"] == 1 and "next_retry_at" in state
    assert "tv_speaker" not in json.dumps(state)


def test_main_publishes_state_for_diagnose(sim, watcher, monkeypatch):  # noqa: F811
    sim["script"] = [True, True]
    sim["run"]()
    state = json.loads(watcher.state_file().read_text())
    assert state["phase"] == "WATCH" and state["reason"] == "bt_route_stable"
    monkeypatch.setattr(watcher, "reachable", lambda: False)
    report = watcher.diagnose()
    assert report["watcher"]["phase"] == "WATCH"
    assert report["watcher"]["pid_alive"] is True  # this test process wrote it


def test_missing_or_corrupt_state_is_reported_as_none(watcher, monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "LOG_FILE", tmp_path / "w.log")
    assert watcher.load_state() is None
    watcher.state_file().write_text("[not, json")
    assert watcher.load_state() is None
