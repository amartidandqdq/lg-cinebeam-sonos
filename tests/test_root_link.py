"""Root transport steps 1-2: luna reply contract, link states, bt_link_lost, warmup skip."""
import json
import subprocess
import sys

import pytest
from test_main_loop import sim  # noqa: F401  (fixture reuse)


@pytest.fixture
def rec(watcher, monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "LOG_FILE", tmp_path / "w.log")
    for name in ("AUTO_RECOVER_BLIPS", "AUTO_RECOVER_DROPS", "MENU_FALLBACK"):
        monkeypatch.setattr(watcher, name, False)
    return watcher.Recovery()


@pytest.fixture
def probe(watcher, monkeypatch):
    monkeypatch.setattr(watcher, "SONOS_BT", "12:34:56:78:9a:bc")
    return watcher.RootProbe("192.0.2.1", "/dev/null", "/dev/null")


def canned(stdout, rc=0):
    def run(cmd, capture_output=True, timeout=None, check=False):
        return subprocess.CompletedProcess(cmd, rc, stdout, b"")
    return run


# --- the luna reply contract: never trust rc=0, parse the last JSON line ---

def test_run_extracts_last_json_line_from_pty_noise(probe, monkeypatch):
    out = b'banner\r\n{"returnValue":true,"connected":false,"connecting":false}\r\n'
    monkeypatch.setattr(subprocess, "run", canned(out))
    assert json.loads(probe._run("cmd", 5))["connected"] is False


def test_run_rejects_empty_output_even_with_rc_zero(probe, watcher, monkeypatch):
    # the 2026-11-09 finding: luna-send without a PTY returns rc=0 and no output
    monkeypatch.setattr(subprocess, "run", canned(b""))
    with pytest.raises(watcher.RootError) as exc:
        probe._run("cmd", 5)
    assert exc.value.reason == "empty_output"


def test_run_maps_ssh_failure_and_timeout(probe, watcher, monkeypatch):
    monkeypatch.setattr(subprocess, "run", canned(b"", rc=255))
    with pytest.raises(watcher.RootError) as exc:
        probe._run("cmd", 5)
    assert exc.value.reason == "ssh_failed"

    def slow(cmd, capture_output=True, timeout=None, check=False):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=1)

    monkeypatch.setattr(subprocess, "run", slow)
    with pytest.raises(watcher.RootError) as exc:
        probe._run("cmd", 5)
    assert exc.value.reason == "ssh_timeout"


def test_luna_quotes_payload_and_budgets_ms_before_subprocess(probe, monkeypatch):
    seen = {}

    def fake_run(remote, timeout):
        seen["remote"], seen["timeout"] = remote, timeout
        return '{"returnValue":true}'

    monkeypatch.setattr(probe, "_run", fake_run)
    probe.luna("luna://x", {"address": "aa bb"}, t=6)
    assert seen["remote"].startswith("luna-send -n 1 -w 6000 ")
    assert '"aa bb"' in seen["remote"]
    assert seen["timeout"] == 10  # -w (6 s) strictly below the subprocess budget


def test_luna_returns_business_errors_as_data_not_transport_failures(probe, monkeypatch):
    monkeypatch.setattr(probe, "_run", lambda remote, timeout:
                        '{"errorCode":131,"returnValue":false,"errorText":"Already connected"}')
    assert probe.luna("luna://x")["errorCode"] == 131


# --- link state mapping: 106 is 'unavailable', not 'down' ---

def test_link_status_mapping(probe, monkeypatch):
    cases = [
        ('{"returnValue":true,"connected":true,"connecting":false,"playing":true}', "connected"),
        ('{"returnValue":true,"connected":false,"connecting":true}', "connecting"),
        ('{"returnValue":true,"connected":false,"connecting":false}', "down"),
        ('{"errorCode":106,"returnValue":false,"errorText":"Device with supplied address'
         ' is not available"}', "unavailable"),
        ('{"errorCode":105,"returnValue":false}', "unknown"),
    ]
    for line, expected in cases:
        monkeypatch.setattr(probe, "_run", lambda remote, timeout, _line=line: _line)
        assert probe.link_status() == expected, line


# --- Recovery.on_link: make the 19:52 case visible, act later (step 3) ---

def target_route(rec):
    rec.power_on()
    rec.on_reading("tv_speaker")  # would start a round in the real loop; ignored here
    rec.on_reading("bt_soundbar")
    assert rec.last_bt


def test_bt_link_lost_needs_confirmation_then_is_flagged_once(rec, watcher):
    target_route(rec)
    rec.on_link("down")
    assert rec.link_flag is False and rec.reason != "bt_link_lost"
    rec.on_link("down")
    assert rec.link_flag and rec.reason == "bt_link_lost" and rec.link_episodes == 1
    assert rec.phase is watcher.Phase.WATCH  # step 1 is visibility only: no round, no writes
    rec.on_link("down")  # same episode: no repeated alarm
    assert watcher.LOG_FILE.read_text().count("route BT affichee mais lien A2DP mort") == 1
    rec.on_link("connected")
    assert rec.link_flag is False and rec.link_reads == 0
    assert "lien A2DP retabli" in watcher.LOG_FILE.read_text()


def test_link_down_without_target_route_is_respected(rec, watcher):
    rec.power_on()
    rec.on_reading("tv_speaker")
    rec.on_link("down")
    rec.on_link("down")
    assert rec.link_flag is False and rec.link_episodes == 0


def test_unavailable_106_never_counts_toward_bt_link_lost(rec, watcher):
    target_route(rec)
    for _ in range(5):
        rec.on_link("unavailable")
    assert rec.link_flag is True  # logged once for visibility
    assert rec.link_episodes == 0 and rec.reason != "bt_link_lost"
    assert "discrimination requise" in watcher.LOG_FILE.read_text()


def test_power_cycle_resets_link_episode(rec, watcher):
    target_route(rec)
    rec.on_link("down")
    rec.on_link("down")
    rec.power_off()
    rec.power_on()
    assert (rec.link, rec.link_flag, rec.link_episodes) == ("unknown", False, 0)


def test_snapshot_carries_link_state(rec):
    target_route(rec)
    rec.on_link("down")
    assert rec.snapshot(0.0)["link"] == "down"


# --- config validation ---

def test_validate_config_rejects_bad_root_mode(watcher, monkeypatch):
    monkeypatch.setattr(watcher, "ALLOW_INSECURE_TLS", True)
    monkeypatch.setattr(watcher, "SONOS_BT", "12:34:56:78:9a:bc")
    monkeypatch.setattr(watcher, "ROOT_MODE", "sometimes")
    with pytest.raises(ValueError, match="ROOT_MODE"):
        watcher.validate_config()


def test_validate_config_rejects_out_of_range_link_poll(watcher, monkeypatch):
    monkeypatch.setattr(watcher, "ALLOW_INSECURE_TLS", True)
    monkeypatch.setattr(watcher, "SONOS_BT", "12:34:56:78:9a:bc")
    monkeypatch.setenv("LINK_POLL", "5")
    with pytest.raises(ValueError, match="LINK_POLL"):
        watcher.validate_config()


# --- diagnose tri-state ---

def test_root_diagnose_is_inert_in_ssap(watcher, monkeypatch):
    monkeypatch.setattr(watcher, "ROOT_MODE", "ssap")
    assert watcher.root_diagnose() == {"mode": "ssap", "available": False}


def test_root_diagnose_reports_all_layers(watcher, monkeypatch):
    class FakeProbe:
        def __init__(self, *args):
            self.available, self.reason, self.reason_detail = False, "ok", ""
            self.link_detail = {"connected": True}

        def probe(self):
            self.available = True
            return True

        def link_status(self):
            return "connected"

        def uptime(self):
            return 123.0

    monkeypatch.setattr(watcher, "ROOT_MODE", "root")
    monkeypatch.setattr(watcher, "RootProbe", FakeProbe)
    info = watcher.root_diagnose()
    assert info["available"] and info["luna"] == "ok" and info["uptime"] == 123.0
    assert info["link"]["state"] == "connected"


# --- Q1 battery: masking and verdicts ---

def test_q1_mask_hides_str_and_byte_list_keys(watcher):
    replies = {"getLinkKey": {"returnValue": True, "linkKey": [1, 2, 3, 4]},
               "connect": {"returnValue": False, "errorText": "no secret here"},
               "note": "plain"}
    masked = watcher.q1_masked(replies)
    assert masked["getLinkKey"]["linkKey"] == "<present: 4 bytes>"
    assert masked["connect"]["errorText"] == "no secret here"
    assert watcher.q1_masked({"getLinkKey": {"linkKey": "abcd"}})["getLinkKey"]["linkKey"] == "<present: 4 chars>"


def test_q1_verdict_healthy_link_is_a_reference_snapshot(watcher):
    assert "link_up" in watcher.q1_verdict({"a2dp_getStatus": {"returnValue": True}})


def test_q1_verdict_106_with_link_key_is_repairable(watcher):
    replies = {"a2dp_getStatus": {"errorCode": 106, "returnValue": False},
               "adapter_getStatus": {"returnValue": True, "powered": True},
               "getLinkKey": {"returnValue": True, "linkKey": [1]}}
    assert "link down but still paired" in watcher.q1_verdict(replies)


def test_q1_verdict_106_without_link_key_is_permanent(watcher):
    replies = {"a2dp_getStatus": {"errorCode": 106, "returnValue": False},
               "adapter_getStatus": {"returnValue": True, "powered": True},
               "getLinkKey": {"returnValue": True}}
    assert "permanent" in watcher.q1_verdict(replies)


def test_q1_verdict_106_with_adapter_down(watcher):
    replies = {"a2dp_getStatus": {"errorCode": 106, "returnValue": False},
               "adapter_getStatus": {"returnValue": True, "powered": False},
               "getLinkKey": {"returnValue": True, "linkKey": [1]}}
    assert "adapter down or reset" in watcher.q1_verdict(replies)


# --- step 2: /proc/uptime decides blip vs reboot before the warmup ---

class FakeProbe:
    def __init__(self, next_uptime):
        self.available, self.reason, self.reason_detail = True, "ok", ""
        self.link_detail = {}
        self.last_uptime = 1000.0  # reference d'avant la coupure (pre-outage sample)
        self._next = next_uptime

    def probe(self):
        self.uptime()  # like the real probe: a successful probe includes an uptime read
        self.available = True
        return True

    def uptime(self):
        return self._next

    def link_status(self):
        self.link_detail = {"connected": True}
        return "connected"


def test_warmup_skipped_when_uptime_continues(sim, watcher, monkeypatch):  # noqa: F811
    monkeypatch.setattr(watcher, "ROOT_MODE", "auto")
    monkeypatch.setattr(watcher, "RootProbe", lambda *a: FakeProbe(1060.0))
    sim["start_cycle"] = False
    sim["script"] = [False] * 4 + [True]  # confirmed outage then return: no reboot
    sim["run"]()
    log = watcher.LOG_FILE.read_text()
    assert "root actif" in log
    assert "coupure reseau sans reboot, warmup saute" in log


def test_warmup_kept_after_real_reboot(sim, watcher, monkeypatch):  # noqa: F811
    monkeypatch.setattr(watcher, "ROOT_MODE", "auto")
    monkeypatch.setattr(watcher, "RootProbe", lambda *a: FakeProbe(40.0))  # uptime restarted
    sim["start_cycle"] = False
    sim["script"] = [False] * 4 + [True]
    sim["run"]()
    log = watcher.LOG_FILE.read_text()
    assert "warmup 25.0 s" in log
    assert "warmup saute" not in log


# --- review 0.4.0 fixes: B1 re-probe, B2 capture cap, M2 clean cli, M3 spawn safety ---

def test_power_on_reprobes_when_root_was_lost(sim, watcher, monkeypatch):  # noqa: F811
    class FlakyStartup(FakeProbe):
        def __init__(self):
            super().__init__(500.0)
            self.probe_calls = 0

        def probe(self):
            self.probe_calls += 1
            self.available = self.probe_calls >= 2  # fails at startup, ok afterwards
            return self.available

    p = FlakyStartup()
    monkeypatch.setattr(watcher, "ROOT_MODE", "auto")
    monkeypatch.setattr(watcher, "RootProbe", lambda *a: p)
    monkeypatch.setattr(watcher, "spawn_q1_capture", lambda *a: None)
    sim["start_cycle"] = False
    sim["script"] = [False] * 4 + [True]
    sim["run"]()
    assert p.probe_calls >= 2  # the power_on re-evaluated the root transport
    log = watcher.LOG_FILE.read_text()
    assert "root indisponible" in log
    assert "warmup" in log


def test_root_lost_at_power_on_recovers_after_warmup(sim, watcher, monkeypatch):  # noqa: F811
    class FlakyUptime(FakeProbe):
        def __init__(self):
            super().__init__(500.0)
            self.uptime_calls = 0
            self.probe_calls = 0

        def probe(self):
            self.probe_calls += 1
            self.uptime()  # like the real probe
            self.available = True
            return True

        def uptime(self):
            self.uptime_calls += 1
            if self.uptime_calls == 2:  # startup ok, power_on fails (slow sshd at boot)
                raise watcher.RootError("ssh_timeout")
            return 600.0

    p = FlakyUptime()
    monkeypatch.setattr(watcher, "ROOT_MODE", "auto")
    monkeypatch.setattr(watcher, "RootProbe", lambda *a: p)
    monkeypatch.setattr(watcher, "spawn_q1_capture", lambda *a: None)
    sim["start_cycle"] = False
    sim["script"] = [False] * 4 + [True]
    sim["run"]()
    log = watcher.LOG_FILE.read_text()
    assert "root perdu" in log
    assert "root actif apres warmup" in log  # second chance after the warmup, not next power-on
    assert p.available is True


def test_q1_captures_capped_across_unavailable_flaps(sim, watcher, monkeypatch):  # noqa: F811
    spawns = []
    monkeypatch.setattr(watcher, "spawn_q1_capture", lambda state: spawns.append(state))
    monkeypatch.setattr(watcher, "root_connect", lambda *a: None)
    monkeypatch.setattr(watcher, "luna_connect", lambda *a: None)
    monkeypatch.setattr(watcher, "observe_route",
                        lambda ws, n: (watcher.RouteResult("BT_ROUTE_STABLE",
                                                           "identity_and_audio_unverified",
                                                           "bt_soundbar"), n + 3))

    class FlapProbe(FakeProbe):
        def __init__(self):
            super().__init__(500.0)
            self.n = 0

        def link_status(self):
            self.n += 1
            self.link_detail = {}
            return "unavailable" if self.n % 2 else "connected"

    p = FlapProbe()
    monkeypatch.setattr(watcher, "ROOT_MODE", "auto")
    monkeypatch.setattr(watcher, "RootProbe", lambda *a: p)
    monkeypatch.setattr(watcher, "sound_output",
                        lambda ws, n: "tv_speaker" if n <= 2 else "bt_soundbar")
    sim["start_cycle"] = False
    sim["script"] = [False] * 4 + [True]
    sim["run"]()
    # 106 flapping must not bypass the cap: unavailable episodes consume the same budget
    assert len(spawns) == watcher.Q1_MAX_CAPTURES
    assert set(spawns) == {"unavailable"}


def test_spawn_q1_capture_swallows_oserror(watcher, monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "LOG_FILE", tmp_path / "w.log")

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(watcher.subprocess, "Popen", boom)
    assert watcher.spawn_q1_capture("down") is None
    assert "capture Q1 impossible" in watcher.LOG_FILE.read_text()


def test_spawn_q1_capture_happy_path(watcher, monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "LOG_FILE", tmp_path / "w.log")
    calls = []
    monkeypatch.setattr(watcher.subprocess, "Popen", lambda cmd, stdout=None, stderr=None: calls.append(cmd))
    capture = watcher.spawn_q1_capture("down")
    assert capture is not None and capture.name.endswith("-down.json")
    assert "--q1-capture" in [str(arg) for arg in calls[0]]
    assert capture.with_suffix(".err").exists()
    assert "capture Q1" in watcher.LOG_FILE.read_text()


def test_cli_q1_capture_failure_is_clean(watcher, monkeypatch, tmp_path, capsys):
    class HalfDeadProbe:
        def __init__(self, *args):
            self.available, self.reason, self.reason_detail = True, "ok", ""
            self.link_detail = {}

        def probe(self):
            self.available = True
            return True

        def uptime(self):
            raise watcher.RootError("ssh_failed", "boom")

    monkeypatch.setattr(watcher, "RootProbe", HalfDeadProbe)
    monkeypatch.setattr(watcher, "ROOT_MODE", "root")
    monkeypatch.setenv("SONOS_BT", "12:34:56:78:9a:bc")
    monkeypatch.setenv("ALLOW_INSECURE_TLS", "1")
    monkeypatch.setattr(sys, "argv", ["sonos-watcher.py", "--q1-capture", str(tmp_path / "x.json")])
    assert watcher.cli() == 2
    assert "Traceback" not in capsys.readouterr().err


def test_luna_bad_json_redacts_key_material(probe, watcher, monkeypatch):
    monkeypatch.setattr(probe, "_run", lambda remote, timeout: '{"linkKey": [1,2,3,')
    with pytest.raises(watcher.RootError) as exc:
        probe.luna("luna://x", {"address": "aa"})
    assert "linkKey" not in str(exc.value)
    assert "redacted" in str(exc.value)


# --- adaptive polling (step 4 option c): calm 300 s when stable, hot 30 s on transitions ---

def _link_reads(sim, watcher, monkeypatch, states, limit=4000.0):  # noqa: F811
    reads = []

    class SeqProbe(FakeProbe):
        def __init__(self):
            super().__init__(500.0)
            self.n = 0

        def link_status(self):
            state = states[min(self.n, len(states) - 1)]
            self.n += 1
            self.link_detail = {}
            reads.append(state)
            return state

    p = SeqProbe()
    monkeypatch.setattr(watcher, "ROOT_MODE", "auto")
    monkeypatch.setattr(watcher, "RootProbe", lambda *a: p)
    monkeypatch.setattr(watcher, "spawn_q1_capture", lambda *a: None)
    monkeypatch.setattr(watcher, "root_connect", lambda *a: None)
    monkeypatch.setattr(watcher, "LINK_POLL_CALM", 300.0)
    monkeypatch.setattr(watcher, "LINK_POLL_HOT", 30.0)
    sim["limit"] = limit
    sim["start_cycle"] = False
    # off/on cycle: without it the watcher observes tv_speaker and never reaches the
    # TARGET route, which is the only state where link reads happen.
    sim["script"] = [False] * 4 + [True]
    sim["run"]()
    return len(reads)


def test_calm_regime_polls_slowly_when_stable(sim, watcher, monkeypatch):  # noqa: F811
    reads = _link_reads(sim, watcher, monkeypatch, ["connected"])
    # 900 s hot (30 s) after the route settles, then 300 s calm: ~41 reads over 4000 s
    assert reads < 60


def test_hot_regime_polls_fast_while_transitions_continue(sim, watcher, monkeypatch):  # noqa: F811
    reads = _link_reads(sim, watcher, monkeypatch, ["down", "connected"] * 60)
    # every read is a transition, the hot regime never expires: ~30 s cadence over 4000 s
    assert reads > 100


def test_validate_config_rejects_hot_above_calm(watcher, monkeypatch):
    monkeypatch.setattr(watcher, "ALLOW_INSECURE_TLS", True)
    monkeypatch.setattr(watcher, "SONOS_BT", "12:34:56:78:9a:bc")
    monkeypatch.setenv("LINK_POLL_HOT", "500")  # above the 300 s calm cadence
    with pytest.raises(ValueError, match="LINK_POLL_HOT"):
        watcher.validate_config()


# --- step 3: root connect + route write (validated by hand on 2026-11-09) ---

def test_methods_root_first_when_available(watcher, monkeypatch):
    assert watcher.methods_for(0, True, True) == ["root", "luna"]
    assert watcher.methods_for(0, True, False) == ["luna", "luna"]
    monkeypatch.setattr(watcher, "MENU_FALLBACK", True)
    monkeypatch.setattr(watcher, "MENU_PROFILE", "hu710qke-webos24")
    assert watcher.methods_for(0, False, True) == ["root", "luna", "menu"]
    assert watcher.methods_for(0, False, False) == ["luna", "luna", "menu"]


def test_connect_bt_treats_131_as_noop_and_other_as_error(probe, watcher, monkeypatch):
    cases = [
        ({"returnValue": True}, None),
        ({"errorCode": 131, "returnValue": False}, None),
        ({"errorCode": 105, "returnValue": False}, "a2dp_connect_failed"),
    ]
    for reply, expected in cases:
        monkeypatch.setattr(probe, "luna", lambda uri, payload=None, t=15, _reply=reply: _reply)
        if expected is None:
            assert probe.connect_bt() == reply
        else:
            with pytest.raises(watcher.RootError, match=expected):
                probe.connect_bt()


def test_root_connect_writes_route_only_when_needed(probe, watcher, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(probe, "connect_bt", lambda: calls.append("connect"))
    monkeypatch.setattr(probe, "set_route", lambda: calls.append("route"))
    monkeypatch.setattr(watcher, "confirm_popup", lambda ws, n: calls.append("popup"))
    monkeypatch.setattr(watcher, "LOG_FILE", tmp_path / "w.log")
    monkeypatch.setattr(watcher, "sound_output", lambda ws, n: "tv_speaker")
    watcher.root_connect(probe, None, 1)
    assert calls == ["connect", "route", "popup"]
    monkeypatch.setattr(watcher, "sound_output", lambda ws, n: "bt_soundbar")
    watcher.root_connect(probe, None, 1)
    assert calls == ["connect", "route", "popup", "connect", "popup"]  # route already on target


def test_confirm_popup_presses_yes_when_focused(watcher, monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "LOG_FILE", tmp_path / "w.log")
    monkeypatch.setattr(watcher, "PAUSE_FILE", tmp_path / "paused")
    monkeypatch.setattr(watcher, "sound_output", lambda ws, n: "bt_soundbar")
    monkeypatch.setattr(watcher, "popup_state", lambda ws, n: "YES_FOCUSED")
    pressed = []
    monkeypatch.setattr(watcher, "press", lambda ws, n, key: pressed.append(key))
    monkeypatch.setattr(watcher.time, "sleep", lambda s: None)
    assert watcher.confirm_popup(None, 1) is True
    assert pressed == ["ENTER"]
    assert "popup de connexion detecte" in watcher.LOG_FILE.read_text()


def test_confirm_popup_absent_means_no_press(watcher, monkeypatch, tmp_path):
    monkeypatch.setattr(watcher, "LOG_FILE", tmp_path / "w.log")
    monkeypatch.setattr(watcher, "PAUSE_FILE", tmp_path / "paused")
    monkeypatch.setattr(watcher, "sound_output", lambda ws, n: "bt_soundbar")
    monkeypatch.setattr(watcher, "popup_state", lambda ws, n: "ABSENT")
    pressed = []
    monkeypatch.setattr(watcher, "press", lambda ws, n, key: pressed.append(key))
    monkeypatch.setattr(watcher.time, "sleep", lambda s: None)
    assert watcher.confirm_popup(None, 1) is False
    assert pressed == []


def test_connect_round_dispatches_root_method(watcher, monkeypatch, tmp_path):
    dispatched = []
    monkeypatch.setattr(watcher, "root_connect", lambda probe, ws, n: dispatched.append(probe))
    monkeypatch.setattr(watcher, "sound_output", lambda ws, n: "tv_speaker")
    monkeypatch.setattr(watcher, "observe_route",
                        lambda ws, n: (watcher.RouteResult("BT_ROUTE_STABLE",
                                                           "identity_and_audio_unverified",
                                                           "bt_soundbar"), n))
    monkeypatch.setattr(watcher, "PAUSE_FILE", tmp_path / "paused")
    monkeypatch.setattr(watcher.time, "sleep", lambda s: None)

    class FakeWS:
        def close(self):
            pass

    marker = object()
    result, _ = watcher.connect_round(FakeWS(), 1, ["root"], marker)
    assert dispatched == [marker]
    assert result.route_stable


def test_probe_arms_snoop_once_per_root_gain(probe, monkeypatch):
    arms = []

    def fake_luna(uri, payload=None, t=6):
        arms.append(uri.rsplit("/", 1)[-1])
        return {"returnValue": True}

    monkeypatch.setattr(probe, "_run", lambda remote, timeout: "500.0 100.0")
    monkeypatch.setattr(probe, "luna", fake_luna)
    assert probe.probe() is True
    assert arms == ["setTrace"]              # first root gain: snoop armed
    assert probe.probe() is True
    assert arms == ["setTrace"]              # root still up: no re-arm
    probe.available = False                  # root lost: the projector may have rebooted
    assert probe.probe() is True
    assert arms == ["setTrace", "setTrace"]  # re-armed after the loss
