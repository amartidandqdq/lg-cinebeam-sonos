import json

import pytest


@pytest.mark.parametrize('during_capture', [False, True])
def test_output_change_during_luna_wait_prevents_enter(watcher, monkeypatch, tmp_path, during_capture):
    out = ['tv_speaker']
    pressed = []
    monkeypatch.setattr(watcher, 'PAUSE_FILE', tmp_path/'paused')
    monkeypatch.setattr(watcher.time, 'sleep', lambda seconds: None if during_capture
                        else out.__setitem__(0, 'external_arc'))
    monkeypatch.setattr(watcher, 'sound_output', lambda *a: out[0])
    monkeypatch.setattr(watcher, 'call', lambda *a: json.dumps({'payload': {'alertId': 'test'}}))
    def capture(*args):
        if during_capture:
            out[0] = 'external_arc'
        return 'YES_FOCUSED'
    monkeypatch.setattr(watcher, 'popup_state', capture)
    monkeypatch.setattr(watcher, 'press', lambda ws, n, key: pressed.append(key))
    watcher.luna_connect(None, 1)
    assert pressed == []


def test_latest_failed_attempt_replaces_old_success(watcher, monkeypatch, tmp_path):
    log = tmp_path/'watcher.log'
    log.write_text('attempt=1 method=luna evidence=BT_ROUTE_STABLE reason=identity_and_audio_unverified\n')
    monkeypatch.setattr(watcher, 'LOG_FILE', log)
    monkeypatch.setattr(watcher, 'PAUSE_FILE', tmp_path/'paused')
    monkeypatch.setattr(watcher, 'sound_output', lambda *a: 'tv_speaker')
    def failure(*a):
        raise watcher.SessionError('private-value-must-not-appear')
    monkeypatch.setattr(watcher, 'luna_connect', failure)
    result, _ = watcher.connect_round(None, 1, ['luna'])
    assert result.evidence == 'UNKNOWN'
    assert watcher.last_attempt()['reason'] == 'command_failed'
    assert 'private-value' not in log.read_text()


def test_screenshot_total_deadline_rejects_slow_body(watcher, monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(watcher.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(watcher, 'ALLOW_INSECURE_TLS', True)
    monkeypatch.setattr(watcher, 'TLS_FINGERPRINT', '')
    class Response:
        status = 200
        def getheader(self, name):
            return None
        def read(self, size):
            clock[0] += 28
            return b'data'
        def read1(self, size):
            clock[0] += 7
            return b'x'
    class Socket:
        def settimeout(self, timeout):
            pass
        def shutdown(self, how):
            pass
        def close(self):
            pass
    class Connection:
        sock = Socket()
        def __init__(self, *a, **kw):
            pass
        def connect(self):
            pass
        def request(self, *a):
            pass
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(watcher.http.client, 'HTTPConnection', Connection)
    with pytest.raises((TimeoutError, watcher.SessionError)):
        watcher.screenshot_bytes('http://192.168.1.2:3000/image')


@pytest.mark.parametrize('change', ['output', 'pause'])
def test_pointer_setup_change_prevents_button(watcher, monkeypatch, tmp_path, change):
    pause = tmp_path/'paused'
    out = ['tv_speaker']
    sent = []
    monkeypatch.setattr(watcher, 'PAUSE_FILE', pause)
    monkeypatch.setattr(watcher, 'sound_output', lambda *a: out[0])
    def pointer(*args):
        if change == 'output':
            out[0] = 'external_arc'
        else:
            pause.touch()
        return json.dumps({'payload': {'socketPath': 'wss://test/'}})
    class Pointer:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def send(self, content):
            sent.append(content)
    monkeypatch.setattr(watcher, 'call', pointer)
    monkeypatch.setattr(watcher, 'secure_connect', lambda *a: Pointer())
    watcher.press(None, 1, 'ENTER')
    assert sent == []


@pytest.mark.parametrize('change', ['output_during_launch', 'pause_before_exit'])
def test_menu_respects_changes_during_waits(watcher, monkeypatch, tmp_path, change):
    pause = tmp_path/'paused'
    out = ['tv_speaker']
    sent = []
    monkeypatch.setattr(watcher, 'PAUSE_FILE', pause)
    monkeypatch.setattr(watcher, 'sound_output', lambda *a: out[0])
    monkeypatch.setattr(watcher, 'call', lambda *a: '{"payload":{"socketPath":"wss://test/"}}')
    def sleep(seconds):
        if seconds == 7 and change == 'output_during_launch':
            out[0] = 'external_arc'
        if seconds == 6 and change == 'pause_before_exit':
            pause.touch()
    class Pointer:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def send(self, content):
            sent.append(content)
    monkeypatch.setattr(watcher.time, 'sleep', sleep)
    monkeypatch.setattr(watcher, 'secure_connect', lambda *a: Pointer())
    watcher.menu_connect(None, 1)
    assert not any('name:EXIT' in content for content in sent)
    if change == 'output_during_launch':
        assert sent == []
