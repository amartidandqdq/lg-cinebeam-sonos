"""Reconnexion Sonos en Bluetooth — 1 clic depuis le PC.
Usage : python lg-projecteur/scripts/reconnect-sonos.py
Le jumelage doit exister (fait une fois dans les menus du projecteur).
"""
import json
import ssl
import sys
import time
import pathlib
from datetime import datetime

from websockets.sync.client import connect

sys.stdout.reconfigure(errors="replace")

HOST = "192.168.1.2"          # IP du projecteur (a ajuster si DHCP change)
CK_FILE = pathlib.Path(__file__).resolve().parent.parent / "backup" / "client-key.txt"
TARGET = "bt_audio"        # nom interne de la sortie BT du projecteur
TIMEOUT = 45                  # secondes d'attente de la connexion

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def ts():
    return datetime.now().strftime("%H:%M:%S")


def main():
    if not CK_FILE.exists():
        sys.exit("Pas de cle d'appairage (backup/client-key.txt absent) — refaire le jumelage.")
    ck = CK_FILE.read_text().strip()

    try:
        ws = connect(f"wss://{HOST}:3001/ssap/local", ssl=ctx, origin=None, open_timeout=8)
    except OSError as e:
        sys.exit(f"Projecteur introuvable sur {HOST} — il est allume ? ({e})")

    ws.send(json.dumps({"type": "register", "id": "r", "payload": {"client-key": ck}}))
    time.sleep(1.2)
    try:
        ws.recv(timeout=4)
    except TimeoutError:
        pass
    print(f"[{ts()}] connecte au projecteur.")

    def call(i, uri, payload=None):
        ws.send(json.dumps({"type": "request", "id": f"c{i}", "uri": uri,
                            "payload": payload or {}}))
        time.sleep(1.0)
        try:
            return ws.recv(timeout=5)
        except TimeoutError:
            return None

    # etat actuel
    r = call(1, "ssap://audio/getStatus")
    out = json.loads(r)["payload"]["volumeStatus"]["soundOutput"]
    if out == TARGET:
        print(f"[{ts()}] deja sur la Sonos, rien a faire.")
        ws.close()
        return
    print(f"[{ts()}] sortie actuelle : {out} -> je declenche la connexion BT...")

    # declencher la bascule vers la sortie BT (tentative de connexion au dernier appareil)
    r = call(2, "ssap://audio/changeSoundOutput", {"output": TARGET})
    print(f"[{ts()}] reponse du projecteur : {(r or 'PAS DE REPONSE')[:120]}")
    if "returnValue\":true" not in (r or ""):
        print(f"[{ts()}] la bascule a ete refusee — verifie l'ecran du projecteur.")

    # surveiller le resultat
    t0 = time.time()
    while time.time() - t0 < TIMEOUT:
        time.sleep(3)
        try:
            r = call(9, "ssap://audio/getStatus")
            cur = json.loads(r)["payload"]["volumeStatus"]["soundOutput"]
            if cur == TARGET:
                print(f"[{ts()}] SONOS CONNECTEE ({int(time.time()-t0)} s) — bon son !")
                ws.close()
                return
            print(f"[{ts()}] en cours... ({cur})")
        except Exception as e:
            print(f"[{ts()}] reconnexion WS ({e}) — nouvelle tentative")
            try:
                ws = connect(f"wss://{HOST}:3001/ssap/local", ssl=ctx, origin=None, open_timeout=8)
                ws.send(json.dumps({"type": "register", "id": "r2", "payload": {"client-key": ck}}))
                time.sleep(1.0)
                try: ws.recv(timeout=3)
                except TimeoutError: pass
            except OSError:
                print(f"[{ts()}] projecteur injoignable")
    print(f"[{ts()}] pas connecte apres {TIMEOUT} s — si une popup est a l'ecran, accepte-la.")
    ws.close()


if __name__ == "__main__":
    main()