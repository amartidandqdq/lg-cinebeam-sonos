"""0.3.0: faster first retry, tolerant Yes press, no redundant output write, quieter WS log."""
import json

import pytest
from test_main_loop import FakeWS, sim  # noqa: F401  (fixture reuse)


@pytest.fixture
def luna(watcher, monkeypatch, tmp_path):
    st = {"out": "tv_speaker", "pressed": [], "writes": [], "press_errors": 0, "popup": "YES_FOCUSED"}
    monkeypatch.setattr(watcher, "PAUSE_FILE", tmp_path / "paused")
    monkeypatch.setattr(watcher, "LOG_FILE", tmp_path / "w.log")
    monkeypatch.setattr(watcher.time, "sleep", lambda s: None)
    monkeypatch.setattr(watcher, "sound_output", lambda ws, n: st["out"])
    monkeypatch.setattr(watcher, "popup_state", lambda ws, n: st["popup"])

    def call(ws, n, uri, payload=None, t=5):
        if uri.endswith("changeSoundOutput"):
            st["writes"].append(t)
        return json.dumps({"payload": {"alertId": "a"}})

    def press(ws, n, key):
        if st["press_errors"]:
            st["press_errors"] -= 1
            raise TimeoutError
        st["pressed"].append(key)
        st["out"] = "bt_soundbar"

    monkeypatch.setattr(watcher, "call", call)
    monkeypatch.setattr(watcher, "press", press)
    return st


def test_first_retry_comes_quickly(watcher):
    assert watcher.retry_delay(1) == 15
    assert watcher.fmt_delay(15) == "15 s"
    assert watcher.fmt_delay(600) == "10 min"


def test_pointer_timeout_is_retried_while_popup_is_shown(watcher, luna):
    luna["press_errors"] = 1
    watcher.luna_connect(None, 1)
    assert luna["pressed"] == ["ENTER"]
    assert "appui Yes impossible (TimeoutError)" in (watcher.LOG_FILE.read_text())


def test_no_output_write_when_popup_already_selected_target(watcher, luna):
    watcher.luna_connect(None, 1)
    assert luna["writes"] == []


def test_output_write_uses_longer_timeout_when_still_on_default(watcher, luna):
    luna["popup"] = "ABSENT"
    watcher.luna_connect(None, 1)
    assert luna["writes"] == [watcher.CHANGE_OUTPUT_TIMEOUT]


def test_no_output_write_after_manual_change(watcher, luna):
    luna["popup"] = "ABSENT"
    luna["out"] = "external_arc"
    watcher.luna_connect(None, 1)
    assert luna["writes"] == []


def test_rollback_retries_after_short_pause(watcher, monkeypatch):
    reads = iter(["tv_speaker", "tv_speaker", "tv_speaker", "bt_soundbar", "bt_soundbar", "bt_soundbar"])
    sleeps = []
    monkeypatch.setattr(watcher, "PAUSE_FILE", watcher.pathlib.Path("/nonexistent/paused"))
    monkeypatch.setattr(watcher, "LOG_FILE", watcher.pathlib.Path("/dev/null"))
    monkeypatch.setattr(watcher.time, "sleep", sleeps.append)
    monkeypatch.setattr(watcher, "sound_output", lambda ws, n: next(reads))
    monkeypatch.setattr(watcher, "luna_connect", lambda ws, n: None)
    result, _ = watcher.connect_round(None, 0, ["luna", "luna"])
    assert result.route_stable
    # post-command 2 s, rollback pause, post-command 2 s, then two stability waits
    assert sleeps[:3] == [2, watcher.ROLLBACK_PAUSE, 2]


def test_ws_outage_logged_once_then_recovery(sim, watcher, monkeypatch):  # noqa: F811
    class Down(FakeWS):
        def recv(self, timeout=None):
            raise TimeoutError

    state = {"fails": 4}

    def open_ws():
        if state["fails"]:
            state["fails"] -= 1
            return Down()
        return FakeWS()

    monkeypatch.setattr(watcher, "open_ws", open_ws)
    sim["start_cycle"] = False
    sim["limit"] = 200
    sim["run"]()
    text = watcher.LOG_FILE.read_text()
    assert text.count("WS indisponible") == 1
    assert text.count("WS retabli") == 1
