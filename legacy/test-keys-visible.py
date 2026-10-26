"""Test : les touches du pointer socket arrivent-elles vraiment au projecteur ?
Envoie des touches visibles (HOME, volume up/down) et observe le resultat.
"""
import json
import ssl
import sys
import time
import pathlib
from websockets.sync.client import connect

sys.stdout.reconfigure(errors="replace")
HOST = "192.168.1.2"
CK = pathlib.Path("lg-projecteur/backup/client-key.txt").read_text().strip()
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

ws = connect(f"wss://{HOST}:3001/ssap/local", ssl=ctx, origin=None, open_timeout=10)
ws.send(json.dumps({"type": "register", "id": "r", "payload": {"client-key": CK}}))
time.sleep(1.2)
try:
    ws.recv(timeout=3)
except TimeoutError:
    pass

ws.send(json.dumps({"type": "request", "id": "sock",
                    "uri": "ssap://com.webos.service.networkinput/getPointerInputSocket"}))
time.sleep(1)
sock_path = json.loads(ws.recv(timeout=5))["payload"]["socketPath"]
sp = connect(sock_path, ssl=ctx, origin=None, open_timeout=8)

def call(i, uri, payload=None):
    ws.send(json.dumps({"type": "request", "id": f"c{i}", "uri": uri, "payload": payload or {}}))
    time.sleep(0.7)
    try:
        return ws.recv(timeout=4)
    except TimeoutError:
        return None

vol_avant = call(1, "ssap://audio/getVolume")
print("volume avant :", vol_avant[:200])

# envoyer volume up x2 via le socket
sp.send("type:button\nname:VOLUMEUP\n\n")
time.sleep(1)
sp.send("type:button\nname:VOLUMEUP\n\n")
time.sleep(2)

vol_apres = call(2, "ssap://audio/getVolume")
print("volume apres 2x VOLUMEUP :", vol_apres[:200])
sp.close()
ws.close()
