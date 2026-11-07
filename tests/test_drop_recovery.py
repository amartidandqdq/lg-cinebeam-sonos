"""AUTO_RECOVER_DROPS: BT route falls back to tv_speaker while the projector stays on."""
import pytest
from test_main_loop import sim  # noqa: F401  (fixture reuse)

DROP = {"out": "tv_speaker"}


@pytest.fixture
def drops_on(watcher, monkeypatch):
    monkeypatch.setattr(watcher, "AUTO_RECOVER_DROPS", True)


def test_drop_is_ignored_by_default(sim):  # noqa: F811
    sim["script"] = [True, True, DROP, True, True, True]
    assert sim["run"]() == ["luna"]


def test_confirmed_drop_reconnects_luna_only(sim, drops_on, watcher):  # noqa: F811
    sim["script"] = [True, True, DROP, True, True]
    assert sim["run"]() == ["luna", "luna"]
    assert "route BT perdue projecteur allume" in watcher.LOG_FILE.read_text()


def test_single_transient_read_does_not_reconnect(sim, drops_on):  # noqa: F811
    sim["script"] = [True, True, DROP, {"out": "bt_soundbar"}, True, True]
    assert sim["run"]() == ["luna"]


def test_manual_switch_to_other_output_is_respected(sim, drops_on):  # noqa: F811
    sim["script"] = [True, True, {"out": "external_arc"}, True, True, True]
    assert sim["run"]() == ["luna"]


def test_drop_recoveries_are_capped_per_power_on(sim, drops_on, watcher):  # noqa: F811
    sim["script"] = [True] + [True, DROP, True] * (watcher.MAX_DROP_RECOVERIES + 3)
    calls = sim["run"]()
    assert calls == ["luna"] * (1 + watcher.MAX_DROP_RECOVERIES)


def test_failed_drop_recovery_follows_retry_ladder_then_stops(sim, drops_on, watcher):  # noqa: F811
    sim["script"] = [True, True, {"out": "tv_speaker", "connect_works": False}, True]
    calls = sim["run"]()
    assert calls == ["luna"] + ["luna", "luna"] * 5  # first round + 4 bounded retries, then stop
    log = watcher.LOG_FILE.read_text()
    assert log.count("route BT perdue projecteur allume") == 1  # retries are not new drops
    assert [d in log for d in ("dans 15 s", "dans 2 min", "dans 10 min", "dans 30 min")] == [True] * 4
    assert "echec definitif" in log
    assert log.count("observation au demarrage") == 0


def test_startup_on_tv_speaker_stays_observation(sim, drops_on):  # noqa: F811
    sim["start_cycle"] = False
    sim["script"] = [True, True, True]
    assert sim["run"]() == []
