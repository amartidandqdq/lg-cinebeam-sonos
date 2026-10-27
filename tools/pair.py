"""Pair with the projector once and save the SSAP client-key.

Usage: python pair.py <projector-ip> [key-file]   (default: ~/sonos-watcher/client-key.txt)
Accept the prompt on the projector screen within 60 s. If the key file already exists,
its key is reused and no prompt is shown.
"""
import argparse
import importlib.util
import json
import os
import pathlib
import time

# Broad manifest, copied from the key known to work with the watcher. Narrowing it is untested.
PERMISSIONS = [
    "LAUNCH", "LAUNCH_WEBAPP", "APP_TO_APP", "CLOSE", "TEST_OPEN", "TEST_PROTECTED", "CONTROL_AUDIO",
    "CONTROL_DISPLAY", "CONTROL_INPUT_JOYSTICK", "CONTROL_INPUT_MEDIA_RECORDING",
    "CONTROL_INPUT_MEDIA_PLAYBACK", "CONTROL_INPUT_TV", "CONTROL_POWER", "CONTROL_TV_SCREEN",
    "READ_APP_STATUS", "READ_CURRENT_CHANNEL", "READ_INPUT_DEVICE_LIST", "READ_NETWORK_STATE",
    "READ_RUNNING_APPS", "READ_TV_CHANNEL_LIST", "WRITE_NOTIFICATION_TOAST", "READ_POWER_STATE",
    "READ_COUNTRY_INFO", "CONTROL_INPUT_TEXT", "CONTROL_MOUSE_AND_KEYBOARD", "READ_INSTALLED_APPS",
    "READ_SETTINGS", "READ_STORAGE_DEVICE_LIST",
]


def load_watcher():
    candidates = [pathlib.Path(__file__).resolve().parents[1]/'watcher/sonos-watcher.py',
                  pathlib.Path(__file__).resolve().parent/'sonos-watcher.py']
    source = next(path for path in candidates if path.is_file())
    spec = importlib.util.spec_from_file_location('pair_watcher', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pair(host, key_file, permissions=None):
    core = load_watcher()
    core.HOST = host
    core.CK_FILE = key_file
    core.validate_tls_policy()
    with core.secure_connect(f'wss://{host}:3001/ssap/local') as ws:
        if key_file.exists():
            core.register(ws, core.read_key())
            return 'Existing key accepted; unchanged.'
        payload = {'forcePairing': False, 'pairingType': 'PROMPT',
                   'manifest': {'manifestVersion': 1, 'appVersion': '1.1',
                                'permissions': permissions if permissions is not None else PERMISSIONS}}
        ws.send(json.dumps({'type': 'register', 'id': 'r', 'payload': payload}))
        print('Accept the pairing prompt on the projector within 60 seconds.')
        deadline = time.monotonic() + 60
        for _ in range(64):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            message = json.loads(ws.recv(timeout=remaining))
            if message.get('type') == 'error':
                raise core.SessionError('registration_refused')
            if message.get('type') == 'registered':
                key = message.get('payload', {}).get('client-key')
                if not isinstance(key, str) or not key:
                    raise core.SessionError('registration_invalid')
                key_file.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
                    stream.write(key)
                return 'Paired. Key saved privately.'
        raise core.SessionError('registration_timeout')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host')
    parser.add_argument('key_file', nargs='?', type=pathlib.Path,
                        default=pathlib.Path.home()/'sonos-watcher/client-key.txt')
    parser.add_argument('--permissions-file', type=pathlib.Path,
                        help='Experimental JSON list; use a separate key file, never overwrite a working key')
    args = parser.parse_args()
    permissions = json.loads(args.permissions_file.read_text()) if args.permissions_file else None
    if permissions is not None and (not isinstance(permissions, list)
                                   or not all(isinstance(item, str) for item in permissions)):
        parser.error('permissions file must contain a JSON list of strings')
    try:
        print(pair(args.host, args.key_file, permissions))
    except Exception as exc:
        parser.exit(2, f'Pairing failed ({exc.__class__.__name__}); existing key preserved.\n')
