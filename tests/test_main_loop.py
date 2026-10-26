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
    st = {"out": "tv_speaker", "calls": [], "connect_works": True, "script": [], "limit": 5000.0,
          "start_cycle": True}

    def reachable():
        if clock[0] > st["limit"]:
            raise Stop
        item = st["script"].pop(0) if st["script"] else True
        if isinstance(item, dict):
            st.update(item)
            return True
        if item == "manual":  # utilisateur choisit une autre sortie a la main
            st["out"] = "tv_speaker"
            return True
        if item == "reboot":  # cycle d'alimentation plus court que l'hysterese : le lien BT est perdu
            st["out"] = "tv_speaker"
            return False
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
    monkeypatch.setattr(watcher, "SONOS_BT", "12:34:56:78:9a:bc")
    monkeypatch.setattr(watcher, "AUTO_RECOVER_BLIPS", False)

    def run():
        if st["start_cycle"]:
            st["script"] = [False] * 4 + st["script"]
        with pytest.raises(Stop):
            watcher.main()
        return st["calls"]

    st["run"] = run
    return st


def test_service_restart_on_running_projector_never_presses_remote_keys(sim):
    sim["start_cycle"] = False
    sim["connect_works"] = False
    calls = sim["run"]()
    assert "menu" not in calls
    assert calls == []


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


def test_short_power_cycle_under_the_hysteresis_still_reconnects(sim):
    sim["script"] = [True, "reboot", True]  # BT perdu pendant la coupure -> reconnexion (luna seul)
    assert sim["run"]() == ["luna"]  # ambiguous cycle is observation by default


def test_blip_with_bt_still_active_does_nothing(sim):
    sim["script"] = [True, False, True]
    assert sim["run"]() == ["luna"]


@pytest.mark.parametrize("misses", [1, 2, 3])
def test_subthreshold_cycles_reconnect_without_menu(sim, misses):
    sim["script"] = [True, "reboot"] + [False] * (misses - 1) + [True]
    assert sim["run"]() == ["luna"]


def test_repeated_short_cycles_reconnect_once_each(sim):
    sim["script"] = [True, "reboot", True, "reboot", True]
    assert sim["run"]() == ["luna"]


def test_manual_hdmi_during_retry_wait_cancels_retries(sim):
    sim["connect_works"] = False
    sim["script"] = [True, {"out": "external_arc"}]
    assert sim["run"]() == ["luna", "luna", "menu", "menu"]


def test_registration_failure_closes_socket_before_retry(sim, watcher, monkeypatch):
    class FailedRegistration(FakeWS):
        closed = 0

        def recv(self, timeout=None):
            raise TimeoutError

        def close(self):
            self.closed += 1

    connections = []

    def open_ws():
        ws = FailedRegistration()
        connections.append(ws)
        return ws

    monkeypatch.setattr(watcher, "open_ws", open_ws)
    sim["limit"] = 30
    assert sim["run"]() == []
    assert connections
    assert all(ws.closed == 1 for ws in connections)


@pytest.mark.parametrize("output", ["tv_speaker", "external_arc", "bt_headphones", "bt_soundbar", None])
def test_startup_is_observation_only(sim, output):
    sim["start_cycle"] = False
    sim["out"] = output
    assert sim["run"]() == []


def test_first_read_after_cycle_preserves_external_output(sim):
    sim["out"] = "external_arc"
    sim["script"] = [False] * 4 + [True]
    assert sim["run"]() == []


def test_ambiguous_outage_does_not_take_output_back(sim):
    sim["script"] = [False] * 4 + [True, "reboot", True]
    assert sim["run"]() == ["luna"]


def test_explicit_blip_recovery_is_luna_only(sim, watcher, monkeypatch):
    monkeypatch.setattr(watcher, "AUTO_RECOVER_BLIPS", True)
    sim["script"] = [True, "reboot", True]
    assert sim["run"]() == ["luna", "luna"]
