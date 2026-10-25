"""Navigation telecommande via le socket specialise + sequence vers Sortie sonore.
Prerequis : le projecteur est allume, sur l'ecran Home. Le script :
  1. ouvre le panneau reglages rapides (bouton settings du pointer socket)
  2. navigue avec les fleches vers Son -> Sortie sonore -> Sonos
Test en conditions reelles : a lancer quand tu veux.
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


def main():
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
    r = ws.recv(timeout=5)
    sock_path = json.loads(r).get("payload", {}).get("socketPath")
    if not sock_path:
        sys.exit("pas de socket input")
    sp = connect(sock_path, ssl=ctx, origin=None, open_timeout=8)

    def btn(name, pause=0.7):
        sp.send(f"type:button\nname:{name}\n\n")
        time.sleep(pause)
        print("  touche :", name)

    def status():
        ws.send(json.dumps({"type": "request", "id": "st", "uri": "ssap://audio/getStatus"}))
        time.sleep(0.6)
        try:
            j = json.loads(ws.recv(timeout=4))
            return j["payload"]["volumeStatus"]["soundOutput"]
        except Exception:
            return "?"

    print("sortie avant :", status())

    # Ouvrir le panneau de reglages rapides
    btn("SETTINGS", 1.5)
    # Le panneau LG : fleche bas vers "Son", OK, puis "Sortie sonore"
    for key in ["DOWN", "DOWN", "DOWN", "DOWN", "ENTER"]:
        btn(key, 0.9)
    time.sleep(1.5)
    print("sortie apres settings :", status())

    sp.close()
    ws.close()


if __name__ == "__main__":
    main()