"""Drive main() with a fake projector and a fake clock; no network, no sleeping."""
import pytest


class Stop(Exception):
    pass


class FakeWS:
    def send(self, _):
        pass

    def recv(self, timeout=None):
        return "{}"

    def close(self):
        pass


@pytest.fixture
def sim(watcher, monkeypatch, tmp_path):
    clock = [0.0]
    st = {"out": "tv_speaker", "calls": [], "connect_works": True, "script": [], "limit": 5000.0}

    def reachable():
        if clock[0] > st["limit"]:
            raise Stop
        item = st["script"].pop(0) if st["script"] else True
        if item == "manual":  # utilisateur choisit une autre sortie a la main
            st["out"] = "tv_speaker"
            return True
        return item

    def connector(how):
        def fn(ws, n):
            st["calls"].append(how)
            if st["connect_works"]:
                st["out"] = "bt_soundbar"
        return fn

    ck = tmp_path / "ck.txt"
    ck.write_text("key")
    monkeypatch.setattr(watcher.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(watcher.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(watcher, "reachable", reachable)
    monkeypatch.setattr(watcher, "open_ws", lambda: FakeWS())
    monkeypatch.setattr(watcher, "sound_output", lambda ws, n: st["out"])
    monkeypatch.setattr(watcher, "luna_connect", connector("luna"))
    monkeypatch.setattr(watcher, "menu_connect", connector("menu"))
    monkeypatch.setattr(watcher, "CK_FILE", ck)
    monkeypatch.setattr(watcher, "LOG_FILE", tmp_path / "w.log")
    monkeypatch.setattr(watcher, "SONOS_BT", "c4:38:75:1c:7d:a9")

    def run():
        with pytest.raises(Stop):
            watcher.main()
        return st["calls"]

    st["run"] = run
    return st


def test_service_restart_on_running_projector_never_presses_remote_keys(sim):
    sim["connect_works"] = False
    calls = sim["run"]()
    assert "menu" not in calls
    assert len(calls) == 2 * 4  # 1er tour + 3 reprises, 2 luna chacun, puis abandon


def test_fresh_power_on_replays_menu_once_then_luna_only_retries(sim):
    sim["connect_works"] = False
    sim["script"] = [False] * 4 + [True]  # extinction confirmee puis allumage
    calls = sim["run"]()
    assert calls[:4] == ["luna", "luna", "menu", "menu"]
    assert calls.count("menu") == 2
    assert len(calls) == 4 + 3 * 2


def test_lan_blip_does_not_trigger_a_new_reconnect(sim):
    sim["script"] = [True, "manual", False, True]  # connecte, choix manuel, 1 sonde ratee
    assert sim["run"]() == ["luna"]


def test_real_power_cycle_reconnects_again(sim):
    sim["script"] = [True, "manual", False, False, False, False, True]
    calls = sim["run"]()
    assert calls == ["luna", "luna"]  # 1 reconnexion au demarrage + 1 apres le vrai cycle
