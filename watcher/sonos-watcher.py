#!/usr/bin/env python3
"""Watcher Sonos : reconnecte automatiquement le LG CineBeam a la barre BT des qu'il s'allume.

Tourne sur m720q (Debian) comme service utilisateur systemd.
Logique :
  - surveille le port WSS 3001 du projecteur (allume = joignable)
  - quand il redevient joignable, attend que les services webOS soient prets
  - lit la sortie audio ; si ce n'est pas bt_*, connexion A2DP via luna (secours : menu)
    (une fois par allumage : un choix manuel ensuite est respecte)
  - confirme ; note tout dans ~/sonos-watcher.log
Reversible : systemctl --user stop sonos-watcher (et disable) suffit.
"""
import io
import json
import socket
import urllib.request
import ssl
import sys
import time
import pathlib
from datetime import datetime

from PIL import Image
from websockets.sync.client import connect

HOST = "192.168.1.2"          # IP LAN du projecteur (reserver sur la box)
FALLBACK_HOSTS = ["m720q-tv", "192.168.1.2"]
PORT = 3001
CK_FILE = pathlib.Path.home() / "sonos-watcher" / "client-key.txt"
LOG_FILE = pathlib.Path.home() / "sonos-watcher" / "watcher.log"
TARGET = "bt_soundbar"  # nom qui reconnecte la Sonos (bt_audio est annule)
ATTEMPTS = 4      # essais de reconnexion par cycle
POLL = 10          # s entre deux sondes quand le projecteur est joignable
SCAN = 15          # s entre deux scans quand il est eteint
WARMUP = 25        # s d'attente apres l'allumage (services webOS)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def reachable():
    s = socket.socket()
    s.settimeout(2.0)
    try:
        return s.connect_ex((HOST, PORT)) == 0
    finally:
        s.close()


def open_ws():
    return connect(f"wss://{HOST}:{PORT}/ssap/local", ssl=ctx, origin=None, open_timeout=8)


def call(ws, n, uri, payload=None, t=5):
    try:
        ws.send(json.dumps({"type": "request", "id": f"w{n}", "uri": uri,
                            "payload": payload or {}}))
        while True:  # ignore les reponses en retard d'appels precedents
            r = ws.recv(timeout=t)
            if json.loads(r).get("id") == f"w{n}":
                return r
    except Exception:
        return None


# Settings -> Sound -> Sound Out -> Use Wireless Speaker -> (options) -> 1er appareil enregistre
# (Living Room SONOS XXXX) -> Connect. Releve a l'ecran le 2026-10-25 sur webOS 24.
MENU_KEYS = ["DOWN", "ENTER", "RIGHT", "DOWN", "ENTER", "DOWN", "DOWN", "ENTER",
             "RIGHT", "ENTER", "DOWN", "ENTER", "DOWN", "ENTER"]


def menu_connect(ws, n):
    call(ws, n, "ssap://system.launcher/launch", {"id": "com.palm.app.settings"})
    time.sleep(7)  # 1er lancement apres boot lent : 3 s ne suffisaient pas
    path = json.loads(call(ws, n + 1, "ssap://com.webos.service.networkinput/getPointerInputSocket"))["payload"]["socketPath"]
    with connect(path, ssl=ctx, origin=None, open_timeout=8) as sp:
        for key in MENU_KEYS:
            sp.send(f"type:button\nname:{key}\n\n")
            time.sleep(1.2)
        time.sleep(6)
        sp.send("type:button\nname:EXIT\n\n")


SONOS_BT = "aa:bb:cc:00:00:a9"  # adresse BT de l'Arc Ultra (= MAC Wi-Fi, verifie 2026-10-25)


def luna_connect(ws, n):
    """Connexion A2DP directe, invisible a l'ecran (astuce lgtv-control-mcp :
    un luna:// place dans le onclose d'une alerte s'execute quand on la ferme)."""
    uri = "luna://com.webos.service.bluetooth2/a2dp/connect"
    params = {"address": SONOS_BT}
    alert = json.loads(call(ws, n, "ssap://system.notifications/createAlert", {
        "message": " ", "buttons": [{"label": "", "onClick": uri, "params": params}],
        "onclose": {"uri": uri, "params": params}, "onfail": {"uri": uri, "params": params}}))
    call(ws, n + 1, "ssap://system.notifications/closeAlert", {"alertId": alert["payload"]["alertId"]})
    # La Sonos repond par une demande que le projecteur affiche en popup Yes/No (focus sur Yes).
    # Sans validation le son reste sur le projecteur : on detecte le popup et on appuie sur OK.
    for k in range(8):
        time.sleep(2)
        if popup_visible(ws, n + 10 + k):
            log("  popup de connexion detecte -> Yes")
            press(ws, n + 30, "ENTER")
            time.sleep(3)
            break
    call(ws, n + 2, "ssap://com.webos.service.apiadapter/audio/changeSoundOutput", {"output": TARGET})


# (x, y) -> couleur attendue sur une capture 960x540 du popup "<Sonos> wants to connect"
POPUP = {(640, 428): (125, 132, 140), (735, 428): (125, 132, 140),   # bouton No
         (645, 378): (230, 230, 230), (735, 392): (230, 230, 230),   # bouton Yes (focus)
         (205, 440): (202, 203, 205), (760, 360): (203, 204, 206)}   # fond du popup


def popup_visible(ws, n):
    try:
        uri = json.loads(call(ws, n, "ssap://tv/executeOneShot"))["payload"]["imageUri"]
        im = Image.open(io.BytesIO(urllib.request.urlopen(uri, context=ctx, timeout=10).read())).convert("RGB")
        im = im.resize((960, 540))
        return all(max(abs(a - b) for a, b in zip(im.getpixel(p), c)) <= 15 for p, c in POPUP.items())
    except Exception:
        return False


def press(ws, n, key):
    path = json.loads(call(ws, n, "ssap://com.webos.service.networkinput/getPointerInputSocket"))["payload"]["socketPath"]
    with connect(path, ssl=ctx, origin=None, open_timeout=8) as sp:
        sp.send(f"type:button\nname:{key}\n\n")
        time.sleep(0.5)


def main():
    log(f"=== watcher demarre (cible {TARGET} sur {HOST}) ===")
    if not CK_FILE.exists():
        log(f"FATAL: {CK_FILE} absent — copier la cle client depuis le PC")
        sys.exit(1)
    ck = CK_FILE.read_text().strip()

    was_online = True   # on suppose demarrage avec projecteur deja allume
    n = 0
    handled = False     # une seule reconnexion par allumage

    while True:
        # --- attendre l'allumage ---
        if not reachable():
            if was_online:
                log("projecteur eteint — surveillance du reseau...")
                was_online = False
            handled = False
            time.sleep(SCAN)
            continue

        if not was_online:
            log(f"projecteur detecte — warmup {WARMUP} s...")
            time.sleep(WARMUP)
        was_online = True

        # --- tenter une session ---
        try:
            ws = open_ws()
            ws.send(json.dumps({"type": "register", "id": "r", "payload": {"client-key": ck}}))
            time.sleep(1.2)
            ws.recv(timeout=4)
        except Exception as e:
            log(f"WS indisponible ({e.__class__.__name__}) — nouvelle tentative dans {SCAN}s")
            time.sleep(SCAN)
            continue

        n += 1
        r = call(ws, n, "ssap://audio/getStatus")
        try:
            out = json.loads(r)["payload"]["volumeStatus"]["soundOutput"]
        except Exception:
            log("lecture etat impossible — reessai plus tard")
            try:
                ws.close()
            except Exception:
                pass
            time.sleep(SCAN)
            continue

        if out.startswith("bt_"):
            if not handled:
                log("sortie audio deja sur la Sonos — rien a faire")
            handled = True
            try:
                ws.close()
            except Exception:
                pass
            time.sleep(POLL)
            continue

        if handled:
            # deja traite depuis l'allumage : on respecte un choix manuel de sortie
            try:
                ws.close()
            except Exception:
                pass
            time.sleep(POLL)
            continue

        log(f"sortie actuelle {out} -> connexion Sonos...")
        # changeSoundOutput ne fait que changer le reglage : apres un boot a froid le lien BT
        # n'existe pas et le projecteur annule. On ouvre d'abord le lien A2DP via luna
        # (invisible) ; en secours on rejoue le menu Sound Out -> Connect a la telecommande.
        connected = False
        for attempt in range(ATTEMPTS):
            how = "luna" if attempt < 2 else "menu"
            try:
                (luna_connect if how == "luna" else menu_connect)(ws, n)
            except Exception as e:
                log(f"  tentative {attempt + 1}/{ATTEMPTS} ({how}): echec ({e.__class__.__name__})")
            n += 100
            for _ in range(6):
                time.sleep(2)
                n += 1
                try:
                    cur = json.loads(call(ws, n, "ssap://audio/getStatus"))["payload"]["volumeStatus"]["soundOutput"]
                except Exception:
                    continue
                if cur.startswith("bt_"):
                    connected = True
                    break
            log(f"  tentative {attempt + 1}/{ATTEMPTS} ({how}): {'SONOS CONNECTEE' if connected else 'pas de connexion'}")
            if connected:
                break
            time.sleep(5)
        handled = True
        if not connected:
            log(f"echec apres {ATTEMPTS} tentatives — Sonos eteinte ou hors de portee ? (reessai au prochain allumage)")
        try:
            ws.close()
        except Exception:
            pass
        time.sleep(POLL)


if __name__ == "__main__":
    main()