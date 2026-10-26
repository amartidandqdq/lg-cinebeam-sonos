"""Exercise the pinned websocket dependency against an ephemeral loopback TLS server."""
import hashlib
import shutil
import ssl
import subprocess
import threading

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
