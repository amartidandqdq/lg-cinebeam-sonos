#!/usr/bin/env python3
"""Watcher Sonos : reconnecte automatiquement le LG CineBeam a la barre BT des qu'il s'allume.

Tourne sur m720q (Debian) comme service utilisateur systemd.
Logique :
  - surveille le port WSS 3001 du projecteur (allume = joignable)
  - quand il redevient joignable, attend que les services webOS soient prets
  - lit la sortie audio ; si ce n'est pas bt_*, connexion A2DP via luna (secours : menu)
    (une fois par allumage : un choix manuel ensuite est respecte)
  - confirme ; note tout dans ~/sonos-watcher/watcher.log
Garde-fous : une coupure reseau breve n'est pas une extinction (OFF_AFTER sondes ratees
d'affilee), les reprises apres echec sont bornees et sans menu, et un redemarrage du
service sur un projecteur deja allume n'envoie jamais de touches a la telecommande.
Config : variables d'environnement LG_HOST, SONOS_BT (obligatoire), MENU_KEYS, WARMUP
(voir watcher.env.example). Reversible : systemctl --user disable --now sonos-watcher.
"""
import io
import json
import os
import pathlib
import re
import socket
import ssl
import sys
import time
import urllib.request
from datetime import datetime

from PIL import Image
from websockets.sync.client import connect

HOST = os.environ.get("LG_HOST", "192.168.1.2")  # IP LAN du projecteur (reserver sur la box)
PORT = 3001
CK_FILE = pathlib.Path.home() / "sonos-watcher" / "client-key.txt"
LOG_FILE = pathlib.Path.home() / "sonos-watcher" / "watcher.log"
TARGET = "bt_soundbar"  # nom qui reconnecte la Sonos (bt_audio est annule)
POLL = 10          # s entre deux sondes quand le projecteur est joignable
SCAN = 15          # s entre deux scans quand il est eteint
WARMUP = int(os.environ.get("WARMUP", "25"))  # s d'attente apres l'allumage (services webOS)
OFF_AFTER = 4      # sondes ratees d'affilee avant de conclure "eteint" (coupure LAN != extinction)
RETRY_DELAYS = (120, 600, 1800)  # s avant chaque reprise apres un echec ; ensuite on abandonne

# ponytail: TLS non verifie, le projecteur presente un certificat auto-signe. Risque accepte sur
# un LAN domestique ; ne pas exposer le port 3001 hors du reseau local.
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


class PowerTracker:
    """Allume/eteint avec hysteresis : 'off' seulement apres `off_after` sondes ratees d'affilee."""

    def __init__(self, off_after=OFF_AFTER):
        self.off_after = off_after
        self.online = True  # on suppose le projecteur allume au demarrage du service
        self.misses = 0

    def update(self, reachable):
        if reachable:
            self.misses = 0
            if not self.online:
                self.online = True
                return "on"
            return None
        self.misses += 1
        if self.online and self.misses >= self.off_after:
            self.online = False
            return "off"
        return None


def methods_for(failed_rounds, adopted):
    """Methodes a essayer. Le menu rejoue des touches visibles a l'ecran : uniquement au 1er tour
    apres un vrai allumage, jamais en reprise ni sur un projecteur deja allume (`adopted`)."""
    if failed_rounds == 0 and not adopted:
        return ["luna", "luna", "menu", "menu"]
    return ["luna", "luna"]


def retry_delay(failed_rounds):
    """Delai avant la reprise suivante (failed_rounds >= 1), None = abandon jusqu'au prochain allumage."""
    return RETRY_DELAYS[failed_rounds - 1] if failed_rounds <= len(RETRY_DELAYS) else None


def validate_bt(addr):
    """Adresse BT bien formee et pas le placeholder du depot."""
    addr = addr.strip().lower()
    if not re.fullmatch(r"([0-9a-f]{2}:){5}[0-9a-f]{2}", addr) or addr.startswith("aa:bb:cc:"):
        raise ValueError("SONOS_BT absent ou invalide (attendu aa:bb:cc:dd:ee:ff, voir watcher.env.example)")
    return addr


def parse_keys(text):
    return [k.strip().upper() for k in text.split(",") if k.strip()] or DEFAULT_MENU_KEYS


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
DEFAULT_MENU_KEYS = ["DOWN", "ENTER", "RIGHT", "DOWN", "ENTER", "DOWN", "DOWN", "ENTER",
                     "RIGHT", "ENTER", "DOWN", "ENTER", "DOWN", "ENTER"]
MENU_KEYS = parse_keys(os.environ.get("MENU_KEYS", ""))


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


SONOS_BT = os.environ.get("SONOS_BT", "")  # adresse BT de l'Arc Ultra (= MAC Wi-Fi)


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


def close(ws):
    try:
        ws.close()
    except Exception:
        pass


def sound_output(ws, n):
    return json.loads(call(ws, n, "ssap://audio/getStatus"))["payload"]["volumeStatus"]["soundOutput"]


def connect_round(ws, n, methods):
    """Un tour de reconnexion. Retourne (sortie_bt_active, n)."""
    # changeSoundOutput ne fait que changer le reglage : apres un boot a froid le lien BT
    # n'existe pas et le projecteur annule. On ouvre d'abord le lien A2DP via luna
    # (invisible) ; en secours on rejoue le menu Sound Out -> Connect a la telecommande.
    for i, how in enumerate(methods, 1):
        try:
            (luna_connect if how == "luna" else menu_connect)(ws, n)
        except Exception as e:
            log(f"  tentative {i}/{len(methods)} ({how}): echec ({e.__class__.__name__})")
        n += 100
        active = False
        for _ in range(6):
            time.sleep(2)
            n += 1
            try:
                active = sound_output(ws, n).startswith("bt_")
            except Exception:
                continue
            if active:
                break
        # Le projecteur annonce la sortie, pas l'audio reellement entendu : d'ou "sortie BT active".
        log(f"  tentative {i}/{len(methods)} ({how}): {'SORTIE BT ACTIVE' if active else 'pas de connexion'}")
        if active:
            return True, n
        time.sleep(5)
    return False, n


def main():
    try:
        global SONOS_BT
        SONOS_BT = validate_bt(SONOS_BT)
    except ValueError as e:
        log(f"FATAL: {e}")
        sys.exit(1)
    log(f"=== watcher demarre (cible {TARGET} sur {HOST}) ===")
    if not CK_FILE.exists():
        log(f"FATAL: {CK_FILE} absent — lancer tools/pair.py")
        sys.exit(1)
    ck = CK_FILE.read_text().strip()

    tracker = PowerTracker()
    adopted = True      # projecteur deja allume au demarrage du service : jamais de touches
    n = 0
    handled = False     # traite pour cet allumage (connecte, choix manuel respecte ou abandon)
    failed_rounds = 0
    next_try = 0.0      # monotonic : pas de reprise avant cet instant

    while True:
        event = tracker.update(reachable())
        if event == "off":
            log("projecteur eteint — surveillance du reseau...")
            handled, failed_rounds, next_try = False, 0, 0.0
        elif event == "on":
            log(f"projecteur detecte — warmup {WARMUP} s...")
            adopted = False
            time.sleep(WARMUP)
        if not tracker.online:
            time.sleep(SCAN)
            continue
        if tracker.misses:  # sonde ratee mais pas encore "eteint" : coupure breve, on ne touche a rien
            time.sleep(POLL)
            continue
        if handled or time.monotonic() < next_try:
            time.sleep(POLL)
            continue

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
        try:
            out = sound_output(ws, n)
        except Exception:
            log("lecture etat impossible — reessai plus tard")
            close(ws)
            time.sleep(SCAN)
            continue

        if out.startswith("bt_"):
            log("sortie audio deja sur la Sonos — rien a faire")
            handled = True
        elif failed_rounds and out != "tv_speaker":
            log(f"sortie changee a la main ({out}) — reprises annulees")
            handled = True
        else:
            log(f"sortie actuelle {out} -> connexion Sonos...")
            connected, n = connect_round(ws, n, methods_for(failed_rounds, adopted))
            if connected:
                handled = True
            else:
                failed_rounds += 1
                delay = retry_delay(failed_rounds)
                if delay is None:
                    log("echec definitif — Sonos eteinte ou hors de portee ? (reessai au prochain allumage)")
                    handled = True
                else:
                    log(f"echec — reprise (luna seul) dans {delay // 60} min")
                    next_try = time.monotonic() + delay
        close(ws)
        time.sleep(POLL)


if __name__ == "__main__":
    main()
