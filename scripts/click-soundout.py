"""Clic direct sur la carte Sound Out de l'ecran Home (via pointer socket).
La photo de l'utilisateur montre la carte Sound Out en bas a droite du Home
(environ 80% de la largeur, 67% de la hauteur en 1080p).
On envoie HOME d'abord, puis on clique sur la carte, et on lit l'etat audio.
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

    def call(i, uri, payload=None, t=4):
        ws.send(json.dumps({"type": "request", "id": f"c{i}", "uri": uri,
                            "payload": payload or {}}))
        time.sleep(0.7)
        try:
            return ws.recv(timeout=t)
        except TimeoutError:
            return None

    # etat initial
    fg = call(1, "ssap://com.webos.applicationManager/getForegroundAppInfo")
    print("foreground:", fg[:150] if fg else "?")
    vol = call(2, "ssap://audio/getStatus")
    if vol:
        print("sortie:", json.loads(vol)["payload"]["volumeStatus"]["soundOutput"])

    # socket input
    ws.send(json.dumps({"type": "request", "id": "sock",
                        "uri": "ssap://com.webos.service.networkinput/getPointerInputSocket"}))
    time.sleep(1)
    sock_path = json.loads(ws.recv(timeout=5))["payload"]["socketPath"]
    sp = connect(sock_path, ssl=ctx, origin=None, open_timeout=8)

    def btn(name, pause=0.8):
        sp.send(f"type:button\nname:{name}\n\n")
        time.sleep(pause)

    def click(x, y, pause=1.2):
        # curseur: deplacement absolu puis clic
        sp.send(f"type:move\nx:{x}\ny:{y}\n\n")
        time.sleep(0.3)
        sp.send(f"type:click\nx:{x}\ny:{y}\n\n")
        time.sleep(pause)
        print(f"  clic ({x},{y})")

    # 1. HOME pour etre sur l'ecran d'accueil
    btn("HOME", 2.0)

    # 2. clic sur la carte Sound Out (estimation d'apres photo : ~80% largeur, ~67% hauteur)
    click(1545, 724)

    # 3. lire l'etat
    time.sleep(1)
    vol = call(9, "ssap://audio/getStatus")
    if vol:
        print("sortie apres clic:", json.loads(vol)["payload"]["volumeStatus"]["soundOutput"])

    sp.close()
    ws.close()


if __name__ == "__main__":
    main()
