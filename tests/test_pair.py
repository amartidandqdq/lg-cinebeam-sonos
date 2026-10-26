import importlib.util
import pathlib

import pytest


def test_existing_pair_key_is_never_replaced_on_refusal(tmp_path, monkeypatch):
    source = pathlib.Path(__file__).resolve().parents[1]/'tools/pair.py'
    spec = importlib.util.spec_from_file_location('pair_tool', source)
    pair = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pair)
    key = tmp_path/'client-key.txt'
    key.write_text('private-existing-key')
    key.chmod(0o600)
    class Socket:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    class Core:
        SessionError = RuntimeError
        def validate_tls_policy(self):
            pass
        def secure_connect(self, url):
            return Socket()
        def read_key(self):
            return key.read_text()
        def register(self, ws, saved):
            raise RuntimeError('registration_refused')
    monkeypatch.setattr(pair, 'load_watcher', lambda: Core())
    with pytest.raises(RuntimeError):
        pair.pair('192.0.2.2', key)
    assert key.read_text() == 'private-existing-key'
