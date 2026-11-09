"""Root transport steps 1-2: luna reply contract, link states, bt_link_lost, warmup skip."""
import json
import subprocess

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


# --- step 2: /proc/uptime decides blip vs reboot before the warmup ---

class FakeProbe:
    def __init__(self, next_uptime):
        self.available, self.reason, self.link_detail = True, "ok", {}
        self.last_uptime = 1000.0
        self._next = next_uptime

    def probe(self):
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
