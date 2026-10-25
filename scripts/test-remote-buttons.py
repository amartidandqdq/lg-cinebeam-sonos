"""Essai : boutons telecommande via le socket specialise (pointer input).
Le but : simuler l'appui utilisateur qui fait marcher la connexion BT dans les menus.
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

# 1. demander le socket d'input
ws.send(json.dumps({"type": "request", "id": "sock",
                    "uri": "ssap://com.webos.service.networkinput/getPointerInputSocket"}))
time.sleep(1)
r = ws.recv(timeout=5)
print("getPointerInputSocket:", r[:220])
sock_path = json.loads(r).get("payload", {}).get("socketPath")
print("socketPath:", sock_path)

if sock_path:
    sp = connect(sock_path, ssl=ctx, origin=None, open_timeout=8)

    def btn(name):
        # format lgtv2 : type:button\nname:XXX\n\n
        msg = f"type:button\nname:{name}\n\n"
        sp.send(msg)
        time.sleep(0.4)

    print("envoi boutons : HOME puis SEQUENCES sortie sonore")
    # sequence : home, settings (bouton settings n'existe pas toujours)...
    for b in ["HOME"]:
        btn(b)
        print("  ->", b)
    time.sleep(2)
sp.close()
ws.close()
