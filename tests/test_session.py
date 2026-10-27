import hashlib
import json

import pytest


class WS:
    def __init__(self, messages):
        self.messages = iter(messages)
        self.sent = []

    def send(self, message):
        self.sent.append(json.loads(message))

    def recv(self, timeout=None):
        return json.dumps(next(self.messages))


@pytest.mark.parametrize('message', [
    {'type': 'error', 'error': 'refused'},
    {'type': 'registered', 'payload': {}},
    {'type': 'registered', 'payload': {'client-key': 123}},
])
def test_registration_refusal_or_malformed_fails(watcher, message):
    with pytest.raises(watcher.SessionError):
        watcher.register(WS([message]), 'test-key')


def test_registration_ignores_prompt_then_requires_registered(watcher):
    ws = WS([{'type': 'response'}, {'type': 'registered', 'payload': {'client-key': 'test-key'}}])
    watcher.register(ws, 'test-key')
    assert len(ws.sent) == 1


def test_call_bounds_unrelated_messages(watcher, monkeypatch):
    clock = iter([0, 1, 3, 6])
    monkeypatch.setattr(watcher.time, 'monotonic', lambda: next(clock))
    with pytest.raises(watcher.SessionError, match='timeout'):
        watcher.call(WS([{'id': 'other'}] * 10), 1, 'ssap://audio/getStatus', t=5)


@pytest.mark.parametrize('url', ['https://outside.invalid/a', 'file:///etc/passwd',
                                  'http://user:pass@192.168.1.2/a', 'http://192.168.1.2:99/a'])
def test_screenshot_rejects_untrusted_destination(watcher, url):
    with pytest.raises(ValueError):
        watcher.validate_screenshot_url(url)


def test_pin_mismatch_and_explicit_insecure_policy(watcher, monkeypatch):
    monkeypatch.setattr(watcher, 'TLS_FINGERPRINT', hashlib.sha256(b'cert').hexdigest())
    watcher.verify_certificate(b'cert')
    with pytest.raises(ValueError, match='certificate'):
        watcher.verify_certificate(b'wrong')
    monkeypatch.setattr(watcher, 'TLS_FINGERPRINT', '')
    monkeypatch.setattr(watcher, 'ALLOW_INSECURE_TLS', False)
    with pytest.raises(ValueError, match='TLS'):
        watcher.validate_tls_policy()


def test_screenshot_rejects_redirect_and_oversize(watcher, monkeypatch):
    monkeypatch.setattr(watcher, 'ALLOW_INSECURE_TLS', True)
    monkeypatch.setattr(watcher, 'TLS_FINGERPRINT', '')
    class Response:
        status = 302
        def read(self, size):
            return b''
        def getheader(self, name):
            return '0'
    class Connection:
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
    with pytest.raises(ValueError):
        watcher._download_screenshot('http://192.168.1.2:3000/a')
    Response.status = 200
    Response.getheader = lambda self, name: str(watcher.MAX_SCREENSHOT_BYTES + 1)
    with pytest.raises(ValueError):
        watcher._download_screenshot('http://192.168.1.2:3000/a')
