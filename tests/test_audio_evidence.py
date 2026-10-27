import pytest


@pytest.mark.parametrize('outputs,expected', [
    (['bt_soundbar'] * 3, 'BT_ROUTE_STABLE'),
    (['bt_soundbar', 'tv_speaker'], 'FAILED'),
    (['bt_headphones'], 'UNKNOWN'),
])
def test_route_evidence_requires_exact_stable_target(watcher, monkeypatch, outputs, expected):
    clock = [0.0]
    readings = iter(outputs)
    monkeypatch.setattr(watcher.time, 'sleep', lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(watcher, 'sound_output', lambda ws, n: next(readings))
    result, _ = watcher.observe_route(None, 0)
    assert result.evidence == expected
    assert not result.link_confirmed
    assert not result.audio_verified
    if expected == 'BT_ROUTE_STABLE':
        assert clock[0] >= 10


def test_route_timeout_never_reports_audio(watcher, monkeypatch):
    def timeout(ws, n):
        raise TimeoutError
    monkeypatch.setattr(watcher, 'sound_output', timeout)
    result, _ = watcher.observe_route(None, 0)
    assert result.evidence == 'UNKNOWN'
    assert result.reason == 'status_timeout'
