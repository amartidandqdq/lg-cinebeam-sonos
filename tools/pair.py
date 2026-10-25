"""Pair with the projector once and save the SSAP client-key.

Usage: python pair.py <projector-ip> [key-file]   (default: ~/sonos-watcher/client-key.txt)
Accept the prompt on the projector screen within 60 s. If the key file already exists,
its key is reused and no prompt is shown.
"""
import json
import pathlib
import ssl
import sys

from websockets.sync.client import connect

# Same manifest as scripts/backup.py: the key it produced runs everything the watcher needs.
PERMISSIONS = [
    "LAUNCH", "LAUNCH_WEBAPP", "APP_TO_APP", "CLOSE", "TEST_OPEN", "TEST_PROTECTED", "CONTROL_AUDIO",
    "CONTROL_DISPLAY", "CONTROL_INPUT_JOYSTICK", "CONTROL_INPUT_MEDIA_RECORDING",
    "CONTROL_INPUT_MEDIA_PLAYBACK", "CONTROL_INPUT_TV", "CONTROL_POWER", "CONTROL_TV_SCREEN",
    "READ_APP_STATUS", "READ_CURRENT_CHANNEL", "READ_INPUT_DEVICE_LIST", "READ_NETWORK_STATE",
    "READ_RUNNING_APPS", "READ_TV_CHANNEL_LIST", "WRITE_NOTIFICATION_TOAST", "READ_POWER_STATE",
    "READ_COUNTRY_INFO", "CONTROL_INPUT_TEXT", "CONTROL_MOUSE_AND_KEYBOARD", "READ_INSTALLED_APPS",
    "READ_SETTINGS", "READ_STORAGE_DEVICE_LIST",
]


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    host = sys.argv[1]
    key_file = pathlib.Path(sys.argv[2] if len(sys.argv) > 2
                            else pathlib.Path.home() / "sonos-watcher" / "client-key.txt")
    payload = {"forcePairing": False, "pairingType": "PROMPT",
               "manifest": {"manifestVersion": 1, "appVersion": "1.1", "permissions": PERMISSIONS}}
    if key_file.exists():
        payload["client-key"] = key_file.read_text().strip()

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with connect(f"wss://{host}:3001/ssap/local", ssl=ctx, origin=None, open_timeout=10) as ws:
        ws.send(json.dumps({"type": "register", "id": "r", "payload": payload}))
        print("Accept the pairing prompt on the projector...")
        while True:
            msg = json.loads(ws.recv(timeout=60))
            if msg.get("type") == "error":
                sys.exit(f"Pairing refused: {msg.get('error')}")
            if msg.get("type") == "registered":
                break

    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(msg["payload"]["client-key"])
    key_file.chmod(0o600)
    print(f"Paired. Key saved to {key_file}")


if __name__ == "__main__":
    main()
