import importlib.util
import pathlib

import pytest


@pytest.mark.parametrize('name,value', [('LG_HOST', 'https://wrong/a'), ('WARMUP', '-1'),
                                      ('STABILITY_SECONDS', '2'), ('WARMUP', 'bad'),
                                      ('MENU_KEYS', 'ENTER,FORMAT_DISK'), ('AUTO_RECOVER_BLIPS', 'yes')])
def test_invalid_configuration_has_clean_error(watcher, monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    monkeypatch.setenv('SONOS_BT', '12:34:56:78:9a:bc')
    monkeypatch.setenv('ALLOW_INSECURE_TLS', '1')
    with pytest.raises(ValueError):
        watcher.validate_config()


def test_diagnose_does_not_connect_audio(watcher, monkeypatch, tmp_path):
    class Socket:
        closed = False
        def close(self):
            self.closed = True
    socket = Socket()
    key = tmp_path/'key'
    key.write_text('private-test-key')
    key.chmod(0o600)
    monkeypatch.setattr(watcher, 'CK_FILE', key)
    monkeypatch.setattr(watcher, 'PAUSE_FILE', tmp_path/'paused')
    monkeypatch.setattr(watcher, 'reachable', lambda: True)
    monkeypatch.setattr(watcher, 'open_ws', lambda: socket)
    monkeypatch.setattr(watcher, 'register', lambda ws, key: None)
    monkeypatch.setattr(watcher, 'sound_output', lambda ws, n: 'bt_soundbar')
    monkeypatch.setattr(watcher, 'connect_round', lambda *a: pytest.fail('diagnostic mutated audio'))
    result = watcher.diagnose()
    assert result['evidence'] == 'BT_ROUTE_SELECTED'
    assert result['identity'] == 'unverified'
    assert 'private-test-key' not in str(result)
    assert socket.closed


def test_pause_resume_only_changes_control_file(watcher, monkeypatch, tmp_path):
    control = tmp_path/'paused'
    monkeypatch.setattr(watcher, 'PAUSE_FILE', control)
    watcher.set_paused(True)
    assert control.exists()
    watcher.set_paused(False)
    assert not control.exists()


def test_installer_preserves_key_and_env_and_backs_up_code(tmp_path):
    source = pathlib.Path(__file__).resolve().parents[1]/'tools/install.py'
    spec = importlib.util.spec_from_file_location('installer', source)
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    target = tmp_path/'sonos-watcher'
    target.mkdir()
    (target/'client-key.txt').write_text('private-key')
    (target/'watcher.env').write_text('existing-config')
    (target/'sonos-watcher.py').write_text('old-code')
    installer.install(tmp_path)
    assert (target/'client-key.txt').read_text() == 'private-key'
    assert (target/'watcher.env').read_text() == 'existing-config'
    assert list(target.glob('backup-*/sonos-watcher.py'))[0].read_text() == 'old-code'
    assert (tmp_path/'.config/systemd/user/sonos-watcher.service').is_file()
