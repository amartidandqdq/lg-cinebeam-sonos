"""Exercise the pinned websocket dependency against an ephemeral loopback TLS server."""
import hashlib
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import time

import pytest
from websockets.sync.server import serve


@pytest.mark.skipif(shutil.which('openssl') is None, reason='requires openssl; exercised by Linux CI')
def test_real_tls_websocket_pin_before_auth(watcher, monkeypatch, tmp_path):
    cert, key = tmp_path/'cert.pem', tmp_path/'key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                    '-keyout', str(key), '-out', str(cert), '-subj', '/CN=localhost', '-days', '1'],
                   check=True, capture_output=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    received = []
    def handler(ws):
        try:
            received.append(ws.recv(timeout=3))
            ws.send('ok')
        except Exception:
            pass
    with serve(handler, '127.0.0.1', 0, ssl=context) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        port = server.socket.getsockname()[1]
        # Keep the production host/port guard; map its accepted endpoint to this ephemeral server.
        original_connect = watcher.connect
        def local_connect(url, **kwargs):
            return original_connect(f'wss://127.0.0.1:{port}', **kwargs)
        monkeypatch.setattr(watcher, 'connect', local_connect)
        monkeypatch.setattr(watcher, 'HOST', '127.0.0.1')
        monkeypatch.setattr(watcher, 'ALLOW_INSECURE_TLS', False)
        der = ssl.PEM_cert_to_DER_cert(cert.read_text())
        monkeypatch.setattr(watcher, 'TLS_FINGERPRINT', hashlib.sha256(der).hexdigest())
        with watcher.open_ws() as ws:
            ws.send('test-auth')
            assert ws.recv(timeout=3) == 'ok'
        monkeypatch.setattr(watcher, 'TLS_FINGERPRINT', '0' * 64)
        with pytest.raises(ValueError, match='certificate'):
            watcher.open_ws()
        server.shutdown()
        thread.join(timeout=3)
    assert received == ['test-auth']


def test_screenshot_deadline_includes_resolver_and_stalled_tls(watcher, monkeypatch):
    """Real child resolver delay + real TLS socket stall must be terminated together."""
    monkeypatch.setattr(watcher, 'HOST', '127.0.0.1')
    monkeypatch.setattr(watcher, 'ALLOW_INSECURE_TLS', True)
    monkeypatch.setattr(watcher, 'TLS_FINGERPRINT', '')
    listener = socket.socket()
    listener.bind(('127.0.0.1', 0))
    listener.listen(1)
    listener.settimeout(12)
    port = listener.getsockname()[1]
    accepted = []
    stop = threading.Event()
    def stall():
        try:
            connection, _ = listener.accept()
            accepted.append(connection)
            stop.wait(12)
            connection.close()
        except OSError:
            pass
    thread = threading.Thread(target=stall, daemon=True)
    thread.start()
    bootstrap = '''
import importlib.util, json, socket, sys, time
spec = importlib.util.spec_from_file_location("capture_test", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
options = json.load(sys.stdin)
module.HOST = options["host"]
module.TLS_FINGERPRINT = options["pin"]
module.ALLOW_INSECURE_TLS = options["insecure"]
original_resolve, original_connect = socket.getaddrinfo, socket.create_connection
def delayed_resolve(*args, **kwargs):
    time.sleep(2)
    return original_resolve(*args, **kwargs)
def local_connect(address, *args, **kwargs):
    return original_connect(("127.0.0.1", int(sys.argv[2])), *args, **kwargs)
socket.getaddrinfo, socket.create_connection = delayed_resolve, local_connect
module._download_screenshot(options["uri"])
'''
    real_run = subprocess.run
    def injected_worker(command, **options):
        return real_run([sys.executable, '-c', bootstrap, watcher.__file__, str(port)], **options)
    monkeypatch.setattr(watcher.subprocess, 'run', injected_worker)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match='total deadline'):
            watcher.screenshot_bytes('https://127.0.0.1:3001/image')
        elapsed = time.monotonic() - started
        assert 7.5 <= elapsed < 9.5
        assert accepted
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=3)
