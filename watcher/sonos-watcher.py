#!/usr/bin/env python3
"""Conservative local Bluetooth recovery for the measured LG HU710QKE / webOS 24.
Observe at startup; recover default output after a detected off/on cycle. Exact route
stability does not prove device identity, A2DP connection or audible audio. See README.
"""
import argparse
import hashlib
import hmac
import http.client
import io
import json
import logging
import os
import pathlib
import re
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import NamedTuple

from PIL import Image, ImageStat
from websockets.sync.client import connect

HOST = os.environ.get("LG_HOST", "192.168.1.2")  # IP LAN du projecteur (reserver sur la box)
PORT = 3001
CK_FILE = pathlib.Path.home() / "sonos-watcher" / "client-key.txt"
LOG_FILE = pathlib.Path.home() / "sonos-watcher" / "watcher.log"
PAUSE_FILE = LOG_FILE.parent / "paused"
TARGET = "bt_soundbar"  # nom qui reconnecte la Sonos (bt_audio est annule)
POLL = 10          # s entre deux sondes quand le projecteur est joignable
SCAN = 15          # s entre deux scans quand il est eteint
WARMUP = os.environ.get("WARMUP", 25)  # s d'attente apres l'allumage (services webOS)
OFF_AFTER = 4      # sondes ratees d'affilee avant de conclure "eteint" (coupure LAN != extinction)
BLIP_POLL = 5      # s entre deux sondes quand une sonde vient d'echouer
RETRY_DELAYS = (120, 600, 1800)  # s avant chaque reprise apres un echec ; ensuite on abandonne
STABILITY_SECONDS = os.environ.get("STABILITY_SECONDS", 10)
MENU_FALLBACK = os.environ.get("MENU_FALLBACK", "0") == "1"
MENU_PROFILE = os.environ.get("MENU_PROFILE", "")
AUTO_RECOVER_BLIPS = os.environ.get("AUTO_RECOVER_BLIPS", "0") == "1"


def classify_output(output):
    if output == TARGET:
        return "TARGET"
    if output == "tv_speaker":
        return "DEFAULT_FALLBACK"
    return "OTHER_USER_OUTPUT" if isinstance(output, str) and output else "UNKNOWN"

# ponytail: TLS non verifie, le projecteur presente un certificat auto-signe. Risque accepte sur
# un LAN domestique ; ne pas exposer le port 3001 hors du reseau local.
TLS_FINGERPRINT = os.environ.get("TLS_FINGERPRINT", "").replace(":", "").lower()
ALLOW_INSECURE_TLS = os.environ.get("ALLOW_INSECURE_TLS", "0") == "1"
MAX_SCREENSHOT_BYTES = 4 * 1024 * 1024
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
    if failed_rounds == 0 and not adopted and MENU_FALLBACK and MENU_PROFILE == "hu710qke-webos24":
        return ["luna", "luna", "menu"]
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
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8", delay=True)
    try:
        handler.emit(logging.LogRecord("sonos", logging.INFO, "", 0, line, (), None))
    except OSError:
        pass
    finally:
        handler.close()


def reachable():
    s = socket.socket()
    s.settimeout(2.0)
    try:
        return s.connect_ex((HOST, PORT)) == 0
    finally:
        s.close()


class SessionError(RuntimeError):
    pass


def validate_tls_policy():
    if TLS_FINGERPRINT and not re.fullmatch(r"[0-9a-f]{64}", TLS_FINGERPRINT):
        raise ValueError("TLS_FINGERPRINT must contain a SHA256 fingerprint")
    if not TLS_FINGERPRINT and not ALLOW_INSECURE_TLS:
        raise ValueError("TLS requires a verified TLS_FINGERPRINT or explicit ALLOW_INSECURE_TLS=1")


def verify_certificate(certificate):
    if TLS_FINGERPRINT and not hmac.compare_digest(hashlib.sha256(certificate).hexdigest(), TLS_FINGERPRINT):
        raise ValueError("certificate fingerprint mismatch")


def secure_connect(url):
    validate_tls_policy()
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "wss" or parsed.hostname != HOST or parsed.username or parsed.password
            or parsed.port not in (None, 3001)):
        raise ValueError("untrusted websocket destination")
    ws = connect(url, ssl=ctx, origin=None, open_timeout=8, legacy=True)
    try:
        if TLS_FINGERPRINT:
            verify_certificate(ws.socket.getpeercert(binary_form=True))
    except Exception:
        close(ws)
        raise
    return ws


def open_ws():
    return secure_connect(f"wss://{HOST}:{PORT}/ssap/local")


def register(ws, key, timeout=8):
    ws.send(json.dumps({"type": "register", "id": "r", "payload": {"client-key": key}}))
    deadline = time.monotonic() + timeout
    for _ in range(64):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        try:
            message = json.loads(ws.recv(timeout=remaining))
            if not isinstance(message, dict):
                raise SessionError("registration_invalid")
            if message.get("type") == "error":
                raise SessionError("registration_refused")
            if message.get("type") == "registered":
                received = message.get("payload", {}).get("client-key")
                if not isinstance(received, str) or not received or received != key:
                    raise SessionError("registration_invalid")
                return
        except (TypeError, ValueError, TimeoutError, OSError) as exc:
            raise SessionError("registration_invalid_or_timeout") from exc
    raise SessionError("registration_timeout")


def call(ws, n, uri, payload=None, t=5):
    deadline = time.monotonic() + t
    try:
        ws.send(json.dumps({"type": "request", "id": f"w{n}", "uri": uri, "payload": payload or {}}))
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise SessionError("status_timeout")
            response = ws.recv(timeout=remaining)
            message = json.loads(response)
            if not isinstance(message, dict):
                raise SessionError("invalid_payload")
            if message.get("id") == f"w{n}":
                if message.get("type") == "error":
                    raise SessionError("request_refused")
                return response
    except SessionError:
        raise
    except Exception as exc:
        raise SessionError("request_invalid_or_disconnected") from exc


# Settings -> Sound -> Sound Out -> Use Wireless Speaker -> (options) -> 1er appareil enregistre
# (Living Room SONOS XXXX) -> Connect. Releve a l'ecran le 2026-10-25 sur webOS 24.
DEFAULT_MENU_KEYS = ["DOWN", "ENTER", "RIGHT", "DOWN", "ENTER", "DOWN", "DOWN", "ENTER",
                     "RIGHT", "ENTER", "DOWN", "ENTER", "DOWN", "ENTER"]
MENU_KEYS = parse_keys(os.environ.get("MENU_KEYS", ""))


def audio_action_allowed(ws, n):
    if PAUSE_FILE.exists():
        return False
    kind = classify_output(sound_output(ws, n))
    return not PAUSE_FILE.exists() and kind in ("TARGET", "DEFAULT_FALLBACK")


def menu_connect(ws, n):
    if not audio_action_allowed(ws, n + 2):
        return
    call(ws, n, "ssap://system.launcher/launch", {"id": "com.palm.app.settings"})
    time.sleep(7)  # 1er lancement apres boot lent : 3 s ne suffisaient pas
    if not audio_action_allowed(ws, n + 3):
        return
    path = json.loads(call(ws, n + 1, "ssap://com.webos.service.networkinput/getPointerInputSocket"))["payload"]["socketPath"]
    with secure_connect(path) as sp:
        for index, key in enumerate(MENU_KEYS):
            if not audio_action_allowed(ws, n + 4 + index):
                return
            sp.send(f"type:button\nname:{key}\n\n")
            time.sleep(1.2)
        time.sleep(6)
        if audio_action_allowed(ws, n + 40):
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
        if PAUSE_FILE.exists() or classify_output(sound_output(ws, n + 40 + k)) not in ("TARGET", "DEFAULT_FALLBACK"):
            return
        state = popup_state(ws, n + 10 + k)
        if state == "UNKNOWN":
            log("method=luna reason=screenshot_unavailable")
        if state == "YES_FOCUSED":
            # Capturing the screen can take seconds: recheck immediately before confirmation.
            if (PAUSE_FILE.exists()
                    or classify_output(sound_output(ws, n + 50 + k)) not in ("TARGET", "DEFAULT_FALLBACK")):
                return
            log("  popup de connexion detecte -> Yes")
            press(ws, n + 30, "ENTER")
            time.sleep(3)
            break
    if audio_action_allowed(ws, n + 3):
        call(ws, n + 2, "ssap://com.webos.service.apiadapter/audio/changeSoundOutput", {"output": TARGET})


# (x, y) -> couleur attendue sur une capture 960x540 du popup "<Sonos> wants to connect"
POPUP = {(640, 428): (125, 132, 140), (735, 428): (125, 132, 140),   # bouton No
         (645, 378): (230, 230, 230), (735, 392): (230, 230, 230),   # bouton Yes (focus)
         (205, 440): (202, 203, 205), (760, 360): (203, 204, 206)}   # fond du popup


def validate_screenshot_url(uri):
    parsed = urllib.parse.urlsplit(uri)
    if (parsed.scheme not in ("http", "https") or parsed.hostname != HOST
            or parsed.username or parsed.password or parsed.fragment
            or parsed.port not in (None, 80, 443, 3000, 3001)):
        raise ValueError("untrusted screenshot destination")
    if parsed.scheme == "http" and not ALLOW_INSECURE_TLS:
        raise ValueError("HTTP screenshot requires explicit insecure LAN mode")
    return parsed


def screenshot_bytes(uri):
    """A killable worker bounds DNS, TCP, TLS, headers and body together."""
    validate_tls_policy()
    validate_screenshot_url(uri)
    options = {"uri": uri, "host": HOST, "pin": TLS_FINGERPRINT, "insecure": ALLOW_INSECURE_TLS}
    try:
        result = subprocess.run(
            [sys.executable, str(pathlib.Path(__file__).resolve()), "--capture-worker"],
            input=json.dumps(options).encode(), capture_output=True, timeout=8, check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # run() kills and reaps the worker, including any stalled resolver/TLS operation.
        raise TimeoutError("screenshot total deadline") from exc
    if result.returncode or len(result.stdout) > MAX_SCREENSHOT_BYTES:
        raise ValueError("screenshot worker failed or exceeded size limit")
    return result.stdout


def capture_worker():
    global HOST, TLS_FINGERPRINT, ALLOW_INSECURE_TLS
    try:
        options = json.load(sys.stdin)
        HOST, TLS_FINGERPRINT = options["host"], options["pin"]
        ALLOW_INSECURE_TLS = options["insecure"]
        sys.stdout.buffer.write(_download_screenshot(options["uri"]))
        return 0
    except Exception:
        return 2  # No endpoint URLs, certificates, private content or exception details on stderr.


def _download_screenshot(uri):
    validate_tls_policy()
    parsed = validate_screenshot_url(uri)
    https = parsed.scheme == "https"
    factory = http.client.HTTPSConnection if https else http.client.HTTPConnection
    kwargs = {"context": ctx} if https else {}
    connection = factory(parsed.hostname, parsed.port, timeout=8, **kwargs)
    deadline = time.monotonic() + 8
    timer = None
    try:
        connection.connect()
        transport_socket = getattr(connection, "sock", None)

        def abort_download():
            if transport_socket is not None:
                try:
                    transport_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("screenshot total deadline")
        # HTTP header parsing also performs multiple reads: interrupt the actual socket at deadline.
        timer = threading.Timer(remaining, abort_download)
        timer.daemon = True
        timer.start()
        if https and TLS_FINGERPRINT:
            verify_certificate(connection.sock.getpeercert(binary_form=True))
        connection.request("GET", urllib.parse.urlunsplit(("", "", parsed.path or "/", parsed.query, "")))
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError("screenshot HTTP status or redirect rejected")
        length = response.getheader("Content-Length")
        if length and int(length) > MAX_SCREENSHOT_BYTES:
            raise ValueError("screenshot too large")
        content = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("screenshot total deadline")
            if transport_socket is not None:
                transport_socket.settimeout(remaining)
            chunk = response.read1(min(65536, MAX_SCREENSHOT_BYTES + 1 - len(content)))
            if time.monotonic() >= deadline:
                raise TimeoutError("screenshot total deadline")
            if not chunk:
                return bytes(content)
            content.extend(chunk)
            if len(content) > MAX_SCREENSHOT_BYTES:
                raise ValueError("screenshot too large")
    finally:
        if timer is not None:
            timer.cancel()
        connection.close()


def popup_match(image):
    image = image.convert("RGB").resize((960, 540))
    # Median patches reject isolated matching pixels; this remains a firmware-specific heuristic.
    for (x, y), color in POPUP.items():
        median = ImageStat.Stat(image.crop((x - 2, y - 2, x + 3, y + 3))).median
        if max(abs(a - b) for a, b in zip(median, color)) > 15:
            return False
    return True


def popup_state(ws, n):
    try:
        uri = json.loads(call(ws, n, "ssap://tv/executeOneShot"))["payload"]["imageUri"]
        with Image.open(io.BytesIO(screenshot_bytes(uri))) as image:
            if image.width * image.height > 8_500_000:
                raise ValueError("screenshot dimensions too large")
            return "YES_FOCUSED" if popup_match(image) else "ABSENT"
    except SessionError:
        raise
    except Exception:
        return "UNKNOWN"


def popup_visible(ws, n):
    return popup_state(ws, n) == "YES_FOCUSED"


def press(ws, n, key):
    if PAUSE_FILE.exists():
        return
    path = json.loads(call(ws, n, "ssap://com.webos.service.networkinput/getPointerInputSocket"))["payload"]["socketPath"]
    with secure_connect(path) as sp:
        if audio_action_allowed(ws, n + 1):
            sp.send(f"type:button\nname:{key}\n\n")
            time.sleep(0.5)


def close(ws):
    try:
        ws.close()
    except Exception:
        pass


def sound_output(ws, n):
    output = json.loads(call(ws, n, "ssap://audio/getStatus"))["payload"]["volumeStatus"]["soundOutput"]
    if not isinstance(output, str) or not re.fullmatch(r"[a-zA-Z0-9_]{1,64}", output):
        raise SessionError("invalid_output_payload")
    return output


class RouteResult(NamedTuple):
    evidence: str
    reason: str
    last_output: str | None = None
    link_confirmed: bool = False
    audio_verified: bool = False

    @property
    def route_stable(self):
        return self.evidence == "BT_ROUTE_STABLE"


def observe_route(ws, n):
    """Three exact-route readings spanning at least ten seconds. Identity is not proved."""
    out = None
    for sample in range(3):
        if sample:
            time.sleep(max(10, STABILITY_SECONDS) / 2)
        n += 1
        try:
            out = sound_output(ws, n)
        except Exception:
            return RouteResult("UNKNOWN", "status_timeout"), n
        if out != TARGET:
            reason = "output_rolled_back" if out == "tv_speaker" else "other_or_unknown_output"
            return RouteResult("FAILED" if out == "tv_speaker" else "UNKNOWN", reason, out), n
    return RouteResult("BT_ROUTE_STABLE", "identity_and_audio_unverified", out), n


def connect_round(ws, n, methods):
    result = RouteResult("UNKNOWN", "no_attempt")
    for i, how in enumerate(methods, 1):
        if PAUSE_FILE.exists():
            return RouteResult("UNKNOWN", "paused"), n
        n += 1
        try:
            out = sound_output(ws, n)
        except Exception:
            return RouteResult("UNKNOWN", "status_timeout"), n
        if classify_output(out) not in ("TARGET", "DEFAULT_FALLBACK"):
            return RouteResult("UNKNOWN", "other_or_unknown_output", out), n
        if out != TARGET:
            try:
                (luna_connect if how == "luna" else menu_connect)(ws, n + 1)
            except Exception as e:
                log(f"attempt={i} method={how} evidence=UNKNOWN reason=command_failed detail={e.__class__.__name__}")
                # A failed session must not be reused for further mutations.
                return RouteResult("UNKNOWN", "command_failed"), n + 100
        n += 100
        time.sleep(2)
        result, n = observe_route(ws, n)
        log(f"attempt={i} method={how} evidence={result.evidence} reason={result.reason}")
        if result.route_stable or result.reason in ("other_or_unknown_output", "status_timeout"):
            return result, n
        time.sleep(5)
    return result, n


def validate_config():
    values = {}
    host = os.environ.get("LG_HOST", HOST)
    if (len(host) > 253 or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", part)
                               for part in host.split("."))):
        raise ValueError("LG_HOST must be a host name or IPv4 address, without scheme or port")
    values["HOST"] = host
    values["SONOS_BT"] = validate_bt(os.environ.get("SONOS_BT", SONOS_BT))
    for name, current, minimum, maximum in (("WARMUP", WARMUP, 0, 300),
                                            ("STABILITY_SECONDS", STABILITY_SECONDS, 10, 60)):
        try:
            value = float(os.environ.get(name, current))
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be numeric") from None
        if not minimum <= value <= maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        values[name] = value
    keys = parse_keys(os.environ.get("MENU_KEYS", ",".join(MENU_KEYS)))
    if len(keys) > 32:
        raise ValueError("MENU_KEYS must contain at most 32 keys")
    if any(key not in {"UP", "DOWN", "LEFT", "RIGHT", "ENTER", "EXIT", "BACK", "HOME"} for key in keys):
        raise ValueError("MENU_KEYS contains an unsupported key")
    values["MENU_KEYS"] = keys
    for name in ("AUTO_RECOVER_BLIPS", "MENU_FALLBACK", "ALLOW_INSECURE_TLS"):
        text = os.environ.get(name, "1" if globals()[name] else "0")
        if text not in ("0", "1"):
            raise ValueError(f"{name} must be 0 or 1")
        values[name] = text == "1"
    fingerprint = os.environ.get("TLS_FINGERPRINT", TLS_FINGERPRINT).replace(":", "").lower()
    if fingerprint and not re.fullmatch(r"[0-9a-f]{64}", fingerprint):
        raise ValueError("TLS_FINGERPRINT must be SHA256")
    if not fingerprint and not values["ALLOW_INSECURE_TLS"]:
        raise ValueError("TLS pin or explicit insecure-LAN opt-in required")
    values["TLS_FINGERPRINT"] = fingerprint
    values["MENU_PROFILE"] = os.environ.get("MENU_PROFILE", MENU_PROFILE)
    if values["MENU_FALLBACK"] and values["MENU_PROFILE"] != "hu710qke-webos24":
        raise ValueError("MENU_FALLBACK requires the measured MENU_PROFILE")
    globals().update(values)


def read_key():
    if os.name != "nt" and CK_FILE.stat().st_mode & 0o077:
        raise ValueError("client-key.txt must have permissions 0600")
    key = CK_FILE.read_text().strip()
    if not key:
        raise ValueError("client-key.txt is empty")
    return key


def set_paused(paused):
    if paused:
        PAUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
        PAUSE_FILE.touch(mode=0o600, exist_ok=True)
    else:
        PAUSE_FILE.unlink(missing_ok=True)


def last_attempt():
    try:
        # Bounded input even if an older unrotated log exists.
        with LOG_FILE.open("rb") as stream:
            stream.seek(max(0, LOG_FILE.stat().st_size - 65536))
            lines = stream.read(65536).decode("utf-8", errors="replace").splitlines()
        for line in reversed(lines):
            match = re.search(r"attempt=(\d+) method=(luna|menu) evidence=([A-Z_]+) reason=([a-z_]+)", line)
            if match:
                return dict(zip(("attempt", "method", "evidence", "reason"), match.groups()))
    except OSError:
        pass
    return None


def diagnose():
    result = {"reachable": reachable(), "paired": False, "paused": PAUSE_FILE.exists(),
              "evidence": "UNKNOWN", "identity": "unverified", "audio": "unverified",
              "last_attempt": last_attempt()}
    if not result["reachable"]:
        return result
    ws = None
    try:
        key = read_key()
        ws = open_ws()
        register(ws, key)
        result["paired"] = True
        output = sound_output(ws, 1)
        result["output"] = output
        result["evidence"] = "BT_ROUTE_SELECTED" if output == TARGET else "UNKNOWN"
    except Exception as exc:
        result["reason"] = exc.__class__.__name__
    finally:
        close(ws)
    return result


def main():
    try:
        validate_config()
    except ValueError as e:
        log(f"FATAL: {e}")
        sys.exit(2)
    log(f"=== watcher demarre (cible {TARGET} sur {HOST}) ===")
    if not CK_FILE.exists():
        log(f"FATAL: {CK_FILE} absent — lancer tools/pair.py")
        sys.exit(1)
    try:
        ck = read_key()
    except (OSError, ValueError) as exc:
        log(f"FATAL: key_invalid ({exc.__class__.__name__})")
        sys.exit(2)

    tracker = PowerTracker()
    adopted = True      # projecteur deja allume au demarrage du service : jamais de touches
    had_miss = False    # une sonde a rate depuis la derniere lecture de la sortie
    last_bt = False     # derniere sortie lue = bt_* (permet de reperer un cycle plus court que OFF_AFTER)
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
            adopted, had_miss, last_bt = False, False, False
            time.sleep(WARMUP)
        if PAUSE_FILE.exists():
            time.sleep(POLL)
            continue
        if not tracker.online:
            time.sleep(SCAN)
            continue
        if tracker.misses:  # sonde ratee mais pas encore "eteint" : coupure breve, on ne touche a rien
            had_miss = True
            time.sleep(BLIP_POLL)
            continue
        if not handled and time.monotonic() < next_try:
            time.sleep(POLL)
            continue

        # --- tenter une session ---
        ws = None
        try:
            ws = open_ws()
            register(ws, ck)
        except Exception as e:
            close(ws)
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

        kind = classify_output(out)
        is_bt = kind == "TARGET"
        if adopted and not handled:
            log(f"observation au demarrage: {kind}; identite BT non verifiee")
            handled = True
        if handled:
            if AUTO_RECOVER_BLIPS and had_miss and last_bt and kind == "DEFAULT_FALLBACK":
                # BT actif avant la coupure, autre sortie au retour : cela peut etre un redemarrage
                # plus court que OFF_AFTER. On reconnecte par luna seul, sans navigation dans les menus.
                log("sortie BT perdue apres une coupure — reconnexion (luna seul)")
                handled, failed_rounds, next_try, adopted = False, 0, 0.0, True
            else:
                last_bt, had_miss = is_bt, False
                close(ws)
                time.sleep(POLL)
                continue
        had_miss = False
        if is_bt:
            log("route BT cible selectionnee; identite non verifiee")
            handled, last_bt = True, True
        elif kind != "DEFAULT_FALLBACK":
            log(f"sortie changee a la main ({out}) — reprises annulees")
            handled = True
        else:
            log(f"sortie actuelle {out} -> connexion Sonos...")
            result, n = connect_round(ws, n, methods_for(failed_rounds, adopted))
            if result.route_stable:
                handled, last_bt = True, True
            elif result.reason == "other_or_unknown_output":
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


def cli():
    parser = argparse.ArgumentParser(description="Local Sonos recovery; diagnostics never mutate audio")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--diagnose", action="store_true")
    group.add_argument("--pause", action="store_true")
    group.add_argument("--resume", action="store_true")
    group.add_argument("--reconnect-now", action="store_true")
    args = parser.parse_args()
    if args.pause or args.resume:
        set_paused(args.pause)
        return 0
    try:
        validate_config()
        if args.diagnose:
            print(json.dumps(diagnose(), sort_keys=True))
            return 0
        if args.reconnect_now:
            if PAUSE_FILE.exists():
                raise ValueError("resume before reconnect-now")
            ws = None
            try:
                ws = open_ws()
                register(ws, read_key())
                result, _ = connect_round(ws, 1, ["luna", "luna"])
                print(json.dumps(result._asdict()))
                return 0 if result.route_stable else 1
            finally:
                close(ws)
        main()
        return 0
    except (OSError, ValueError, SessionError):
        print("Configuration, key or session invalid; use --help and the operations guide.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(capture_worker() if sys.argv[1:] == ["--capture-worker"] else cli())
