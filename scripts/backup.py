"""Backup de l'inventaire du projecteur LG (etape 1 de cleanyourtv, adapté webOS).
Lecture seule. Utilise la client-key sauvegardee dans backup/client-key.txt.
Usage: python lg-projecteur/scripts/backup.py
Sortie: lg-projecteur/backup/inventaire-<date>.json
"""
import json
import ssl
import sys
import time
import pathlib
from datetime import datetime

from websockets.sync.client import connect

sys.stdout.reconfigure(errors="replace")

HOST = "192.168.1.2"
ROOT = pathlib.Path(__file__).resolve().parent.parent
CK_FILE = ROOT / "backup" / "client-key.txt"

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
    ck = CK_FILE.read_text().strip()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    inv = {"date": datetime.now().isoformat(timespec="seconds"), "host": HOST, "apps": None,
           "foreground": None, "inputs": None, "settings": None, "notes": []}

    ws = connect(f"wss://{HOST}:3001/ssap/local", ssl=ctx, origin=None, open_timeout=15)
    ws.send(json.dumps({
        "type": "register", "id": "r",
        "payload": {"forcePairing": False, "pairingType": "PROMPT",
                    "manifest": {"manifestVersion": 1, "appVersion": "1.1",
                                 "permissions": PERMISSIONS},
                    "client-key": ck},
    }))
    try:
        r = ws.recv(timeout=8)
    except TimeoutError:
        r = None
    if r and b'"registered"' not in r.encode("utf-8", "ignore"):
        raise SystemExit(f"register refuse: {r}")
    print("[backup] appaire.")

    def call(i, uri):
        ws.send(json.dumps({"type": "request", "id": f"c{i}", "uri": uri,
                            "payload": {}}))

    results = []

    def drain(timeout=4):
        try:
            results.append(ws.recv(timeout=timeout))
        except TimeoutError:
            pass
        return results[-1] if results else None

    call(1, "ssap://com.webos.applicationManager/getForegroundAppInfo")
    time.sleep(0.8)
    inv["foreground"] = drain()

    call(2, "ssap://com.webos.applicationManager/listApps")
    time.sleep(1.5)
    inv["apps_raw"] = drain()

    call(3, "ssap://com.webos.applicationManager/listLaunchPoints")
    time.sleep(1.5)
    inv["launchpoints_raw"] = drain()

    for n, uri in enumerate(("ssap://com.webos.settingsservice/getSystemSettings",
                             "ssap://com.webos.service.system/getSystemInfo",
                             "ssap://com.webos.config/getAppInfoList"), 10):
        call(n, uri)
        time.sleep(1)
        inv["notes"].append((uri, drain()))

    ws.close()
    out = ROOT / "backup" / f"inventaire-{inv['date'].replace(':', '-')}.json"
    out.write_text(json.dumps(inv, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[backup] ecrit -> {out}")


if __name__ == "__main__":
    main()