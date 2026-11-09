#!/usr/bin/env python3
"""Conservative local Bluetooth recovery for the measured LG HU710QKE / webOS 24.
Observe at startup; recover default output after a detected off/on cycle. Exact route
stability does not prove device identity, A2DP connection or audible audio. See README;
the main-loop phases (class Recovery) are documented in docs/state-machine.md.
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
import shlex
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime
from enum import Enum
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
RETRY_DELAYS = (15, 120, 600, 1800)  # s avant chaque reprise apres un echec ; ensuite on abandonne
ROLLBACK_PAUSE = 2  # s entre deux essais luna quand la sortie est revenue sur tv_speaker
CHANGE_OUTPUT_TIMEOUT = 10  # s : le projecteur repond lentement juste apres la connexion BT
STABILITY_SECONDS = os.environ.get("STABILITY_SECONDS", 10)
MENU_FALLBACK = os.environ.get("MENU_FALLBACK", "0") == "1"
MENU_PROFILE = os.environ.get("MENU_PROFILE", "")
AUTO_RECOVER_BLIPS = os.environ.get("AUTO_RECOVER_BLIPS", "0") == "1"
# Reconnexion quand la route BT retombe sur tv_speaker projecteur allume (Sonos decrochee).
AUTO_RECOVER_DROPS = os.environ.get("AUTO_RECOVER_DROPS", "0") == "1"
DROP_CONFIRM_READS = 2   # lectures tv_speaker consecutives (>= 1 POLL) avant d'agir
MAX_DROP_RECOVERIES = 5  # par allumage : au-dela, on laisse la sortie telle quelle
ROOT_MODE = os.environ.get("ROOT_MODE", "auto")  # auto|ssap|root : lecture du lien A2DP par SSH root
ROOT_SSH_KEY = os.environ.get("ROOT_SSH_KEY", str(pathlib.Path.home() / ".ssh" / "id_ed25519"))
ROOT_KNOWN_HOSTS = os.environ.get("ROOT_KNOWN_HOSTS", str(pathlib.Path.home() / ".ssh" / "known_hosts.cinebeam"))
LINK_POLL = float(os.environ.get("LINK_POLL", 60))  # s entre deux lectures du lien quand la route est cible
LINK_CONFIRM_READS = 2  # lectures lien non connecte consecutives avant de declarer bt_link_lost


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


def fmt_delay(seconds):
    return f"{seconds} s" if seconds < 60 else f"{seconds // 60} min"


def retry_delay(failed_rounds):
    """Delai avant la reprise suivante (failed_rounds >= 1), None = abandon jusqu'au prochain allumage."""
    return RETRY_DELAYS[failed_rounds - 1] if failed_rounds <= len(RETRY_DELAYS) else None


class Phase(str, Enum):
    """Recovery phase for the current power-on. Diagram and transition table: docs/state-machine.md."""
    STARTUP_OBSERVE = "STARTUP_OBSERVE"  # service started on a running projector: read once, never act
    OFF = "OFF"                          # OFF_AFTER consecutive probes missed
    RECOVER = "RECOVER"                  # next output reading may start a connect round
    RETRY_WAIT = "RETRY_WAIT"            # a round failed; nothing until next_try (monotonic)
    WATCH = "WATCH"                      # settled for this power-on; only drops/blips can reopen it


class Recovery:
    """Decisions of the main loop, without I/O: main() probes, reads and connects; this class decides.
    Every phase change goes through _enter(), which logs `state=OLD->NEW reason=...`."""

    def __init__(self):
        self.phase = Phase.STARTUP_OBSERVE
        self.reason = "service_start"
        self.since = datetime.now().isoformat(timespec="seconds")
        self.luna_only = True   # no menu keys: startup, blip/drop recovery (only a real power-on allows them)
        self.failed_rounds = 0
        self.next_try = 0.0     # monotonic : pas de reprise avant cet instant
        self.had_miss = False   # une sonde a rate depuis la derniere lecture de la sortie
        self.last_bt = False    # derniere sortie lue = bt_* (permet de reperer un cycle plus court que OFF_AFTER)
        self.drop_reads = 0     # lectures tv_speaker consecutives alors que la route BT etait active
        self.drops = 0          # reconnexions apres perte de route pour cet allumage
        self.link_down = False  # WS deja signale indisponible : on ne le relogue pas a chaque essai
        self.link = "unknown"   # dernier etat du lien A2DP lu par le root (state.json / --diagnose)
        self.link_reads = 0     # lectures lien non connecte consecutives (confirmation bt_link_lost)
        self.link_flag = False  # episode bt_link_lost en cours : log unique jusqu'au retablissement
        self.link_episodes = 0  # episodes bt_link_lost depuis l'allumage

    def _enter(self, phase, reason):
        if phase is not self.phase:
            log(f"state={self.phase.value}->{phase.value} reason={reason}")
            self.since = datetime.now().isoformat(timespec="seconds")
        self.phase, self.reason = phase, reason

    # --- power and link events (PowerTracker / session) ---
    def power_off(self):
        self.failed_rounds, self.next_try, self.link_down = 0, 0.0, False
        self._enter(Phase.OFF, "power_off")

    def power_on(self):
        self.luna_only, self.had_miss, self.last_bt, self.drop_reads, self.drops = False, False, False, 0, 0
        self.link, self.link_reads, self.link_flag, self.link_episodes = "unknown", 0, False, 0
        self._enter(Phase.RECOVER, "power_on")

    def probe_missed(self):
        self.had_miss = True

    def waiting(self, now):
        """True while a retry is scheduled; once due, the phase moves to RECOVER."""
        if self.phase is not Phase.RETRY_WAIT:
            return False
        if now < self.next_try:
            return True
        self._enter(Phase.RECOVER, f"retry_{self.failed_rounds}_due")
        return False

    def session_failed(self):
        """True only on the first failure, so an outage is logged once."""
        first, self.link_down = not self.link_down, True
        return first

    def session_restored(self):
        restored, self.link_down = self.link_down, False
        return restored

    # --- output readings ---
    def on_reading(self, out):
        """Process one output reading; True when a connect round must run now."""
        kind = classify_output(out)
        if self.phase is Phase.STARTUP_OBSERVE:
            log(f"observation au demarrage: {kind}; identite BT non verifiee")
            self._enter(Phase.WATCH, "startup_observation")
        if self.phase is Phase.WATCH:
            trigger = self._watch(kind)
            if trigger is None:
                return False
            self.failed_rounds, self.next_try, self.luna_only = 0, 0.0, True
            self._enter(Phase.RECOVER, trigger)
        self.had_miss = False
        if kind == "TARGET":
            log("route BT cible selectionnee; identite non verifiee")
            self.last_bt = True
            self._enter(Phase.WATCH, "bt_route_selected")
            return False
        if kind != "DEFAULT_FALLBACK":
            log(f"sortie changee a la main ({out}) — reprises annulees")
            self._enter(Phase.WATCH, "other_output_respected")
            return False
        log(f"sortie actuelle {out} -> connexion Sonos...")
        return True

    def _watch(self, kind):
        """WATCH: returns the reason to reopen recovery, or None to keep watching."""
        if AUTO_RECOVER_BLIPS and self.had_miss and self.last_bt and kind == "DEFAULT_FALLBACK":
            # BT actif avant la coupure, autre sortie au retour : cela peut etre un redemarrage
            # plus court que OFF_AFTER. On reconnecte par luna seul, sans navigation dans les menus.
            log("sortie BT perdue apres une coupure — reconnexion (luna seul)")
            return "blip_lost_bt"
        if AUTO_RECOVER_DROPS and not self.had_miss and self.last_bt and kind == "DEFAULT_FALLBACK":
            # Projecteur reste allume, Sonos decrochee : on confirme puis on reconnecte (luna seul).
            self.drop_reads += 1
            if self.drop_reads < DROP_CONFIRM_READS:
                return None
            self.drop_reads = 0
            if self.drops >= MAX_DROP_RECOVERIES:
                log(f"route BT perdue {self.drops + 1} fois depuis l'allumage — sortie laissee telle quelle")
                self.last_bt = False
                self.reason = "drop_cap_reached"
                return None
            self.drops += 1
            log("route BT perdue projecteur allume — reconnexion (luna seul)")
            return "bt_route_dropped"
        self.drop_reads = 0
        self.last_bt, self.had_miss = kind == "TARGET", False
        return None

    def on_link(self, state):
        """Enregistre un etat du lien A2DP lu par le root (appele en WATCH sur route cible).
        Etape 1 : rendre la panne visible (route TARGET + lien mort, le cas du 2026-11-09 19:52) ;
        aucune reprise ici, l'ecriture est l'etape 3. 'unavailable' (106) est ambigu
        (reset bluetooth2, desappairage, adresse changee) : discrimination requise, pas d'action."""
        previous, self.link = self.link, state
        if state in ("connected", "connecting"):
            self.link_reads = 0
            if self.link_flag:
                log("lien A2DP retabli")
                self.link_flag = False
            return
        if state != "down":
            if not self.link_flag or previous != state:
                log(f"lien A2DP {state} — cas ambigu (106 ?), discrimination requise avant toute action")
                self.link_flag = True
            return
        if not self.last_bt:
            return  # route non cible : un lien mort sans route BT est un etat respecte
        self.link_reads += 1
        if self.link_reads < LINK_CONFIRM_READS:
            return
        self.link_reads = 0
        if not self.link_flag:
            self.link_flag = True
            self.link_episodes += 1
            self.reason = "bt_link_lost"
            log(f"route BT affichee mais lien A2DP mort — panne visible (root, episode {self.link_episodes})")

    def methods(self):
        return methods_for(self.failed_rounds, self.luna_only)

    def on_round(self, result, now):
        if result.route_stable:
            self.last_bt = True
            self._enter(Phase.WATCH, "bt_route_stable")
        elif result.reason == "other_or_unknown_output":
            self._enter(Phase.WATCH, "other_output_respected")
        else:
            self.failed_rounds += 1
            delay = retry_delay(self.failed_rounds)
            if delay is None:
                log("echec definitif — Sonos eteinte ou hors de portee ? (reessai au prochain allumage)")
                self.last_bt = False
                self._enter(Phase.WATCH, "retries_exhausted")
            else:
                log(f"echec — reprise (luna seul) dans {fmt_delay(delay)}")
                self.next_try = now + delay
                self._enter(Phase.RETRY_WAIT, result.reason)

    def snapshot(self, now):
        """JSON-safe view for --diagnose; no secrets, addresses or outputs."""
        state = {"phase": self.phase.value, "reason": self.reason, "since": self.since,
                 "failed_rounds": self.failed_rounds, "drops": self.drops, "max_drops": MAX_DROP_RECOVERIES,
                 "session": "down" if self.link_down else "up", "link": self.link}
        if self.phase is Phase.RETRY_WAIT:
            at = datetime.now().timestamp() + max(0.0, self.next_try - now)
            state["next_retry_at"] = datetime.fromtimestamp(at).isoformat(timespec="seconds")
        return state


def state_file():
    return LOG_FILE.parent / "state.json"


def save_state(state):
    """Atomic best-effort write; a missing or read-only directory never stops the watcher."""
    path = state_file()
    try:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(dict(state, pid=os.getpid()), sort_keys=True), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


def load_state():
    try:
        state = json.loads(state_file().read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            return None
    except (OSError, ValueError):
        return None
    pid = state.get("pid")
    if isinstance(pid, int) and pid > 0:
        try:
            os.kill(pid, 0)
            state["pid_alive"] = True
        except PermissionError:
            state["pid_alive"] = True
        except OSError:
            state["pid_alive"] = False
    return state


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


class RootError(RuntimeError):
    """Echec du transport root. Contrat : jamais un succes sans preuve — rc=0 sans sortie
    est une erreur, pas un succes (constat 2026-11-09 : luna-send sans PTY renvoie rc=0 muet)."""

    def __init__(self, reason, detail=""):
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason


class RootProbe:
    """Lectures root par SSH. -tt obligatoire : sans PTY, luna-send renvoie rc=0 sans aucune
    sortie — mecanisme intrinseque au PTY, verifie le 2026-11-09 (4 bras : -T direct, login
    shell, XDG_RUNTIME_DIR exporte : tous muets ; -tt : OK). Lecture seule : a2dp/getStatus
    et /proc/uptime. Les ecritures (connect, popup, sortie audio) restent SSAP — etape 3."""

    def __init__(self, host, key, known_hosts):
        self.host = host
        self.key = key
        self.known_hosts = known_hosts
        self.available = False
        self.reason = "not_probed"
        self.reason_detail = ""  # str(RootError) du dernier echec : reason + queue de stderr
        self.last_uptime = None  # dernier echantillon ; sert de reference pour blip vs reboot
        self.link = "unknown"
        self.link_detail = {}

    @staticmethod
    def _stderr_tail(result, limit=140):
        text = result.stderr.decode("utf-8", errors="replace").strip().replace("\n", " ")
        return text[-limit:]

    def _run(self, remote, timeout):
        # -F /dev/null : ignore les configs ssh systeme et utilisateur. Obligatoire sous
        # PrivateTmp (l'unite) : la resolution userns y fait apparaitre /etc/ssh/ssh_config.d
        # en nobody:nogroup et ssh refuse le fichier ("Bad owner or permissions"). Toutes les
        # options utiles sont passees en -o : le transport devient deterministe.
        options = ["-F", "/dev/null", "-tt", "-o", "BatchMode=yes", "-o", "LogLevel=ERROR",
                   "-o", "ConnectTimeout=2", "-i", self.key,
                   # Cle epinglee a la premiere connexion (accept-new) : un changement de host key
                   # devient une erreur franche (MITM potentiel), pas un prompt silencieux.
                   "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={self.known_hosts}"]
        try:
            result = subprocess.run(["ssh"] + options + [f"root@{self.host}", remote],
                                    capture_output=True, timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise RootError("ssh_timeout") from None
        except OSError as exc:
            raise RootError("ssh_unavailable", exc.__class__.__name__) from None
        if result.returncode != 0:
            raise RootError("ssh_failed", self._stderr_tail(result))
        lines = [ln.strip() for ln in result.stdout.decode("utf-8", errors="replace")
                 .replace("\r", "\n").splitlines() if ln.strip()]
        if not lines:
            raise RootError("empty_output", self._stderr_tail(result))
        return lines[-1]  # derniere ligne non vide : insensible aux bannieres/eventuels \r de PTY

    def luna(self, uri, payload=None, t=6):
        """Appel luna one-shot. Erreur metier (errorCode) renvoyee telle quelle a l'appelant ;
        echec de transport -> RootError. Budgets : -w en ms < timeout subprocess."""
        remote = f"luna-send -n 1 -w {int(t * 1000)} {shlex.quote(uri)}"
        if payload is not None:
            remote += " " + shlex.quote(json.dumps(payload))
        line = self._run(remote, t + 4)
        try:
            reply = json.loads(line)
        except ValueError:
            raise RootError("bad_json", line[:60]) from None
        if not isinstance(reply, dict):
            raise RootError("bad_json", "not_an_object")
        return reply

    def probe(self):
        """Detection bornee : /proc/uptime lisible = transport root operationnel."""
        try:
            self.uptime()
            self.available, self.reason = True, "ok"
        except RootError as exc:
            self.available, self.reason = False, exc.reason
            self.reason_detail = str(exc)
        return self.available

    def uptime(self):
        line = self._run("cat /proc/uptime", 6)
        try:
            value = float(line.split()[0])
        except (IndexError, ValueError):
            raise RootError("bad_uptime", line[:40]) from None
        self.last_uptime = value
        return value

    def link_status(self):
        """connected / connecting / down / unavailable / unknown. Un lien coupe mais appaire
        devrait repondre connected:false ; 106 signale plutot un reset bluetooth2, un
        desappairage ou une adresse changee — d'ou 'unavailable', distinct de 'down'."""
        reply = self.luna("luna://com.webos.service.bluetooth2/a2dp/getStatus", {"address": SONOS_BT})
        if not reply.get("returnValue"):
            code = reply.get("errorCode")
            self.link_detail = {"errorCode": code}
            self.link = "unavailable" if code == 106 else "unknown"
            return self.link
        connected, connecting = bool(reply.get("connected")), bool(reply.get("connecting"))
        self.link_detail = {k: reply.get(k) for k in ("connected", "connecting", "playing")}
        self.link = "connected" if connected else ("connecting" if connecting else "down")
        return self.link


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
            try:
                press(ws, n + 30 + k, "ENTER")
            except (OSError, TimeoutError) as exc:
                # Socket pointeur lent juste apres l'allumage : le popup reste affiche, on reessaie
                # au tour suivant sans abandonner la session principale.
                log(f"  appui Yes impossible ({exc.__class__.__name__}) — nouvel essai")
                continue
            time.sleep(3)
            break
    if PAUSE_FILE.exists():
        return
    out = sound_output(ws, n + 3)
    if out == TARGET:
        return  # le popup a suffi : inutile de reecrire la sortie sur un projecteur encore occupe
    if not PAUSE_FILE.exists() and classify_output(out) == "DEFAULT_FALLBACK":
        call(ws, n + 2, "ssap://com.webos.service.apiadapter/audio/changeSoundOutput", {"output": TARGET},
             t=CHANGE_OUTPUT_TIMEOUT)


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
            if response.isclosed():
                return bytes(content)
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
        time.sleep(ROLLBACK_PAUSE if result.reason == "output_rolled_back" else 5)
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
    if os.environ.get("ROOT_MODE", ROOT_MODE) not in ("auto", "ssap", "root"):
        raise ValueError("ROOT_MODE must be auto, ssap or root")
    values["ROOT_MODE"] = os.environ.get("ROOT_MODE", ROOT_MODE)
    values["ROOT_SSH_KEY"] = os.environ.get("ROOT_SSH_KEY", ROOT_SSH_KEY)
    values["ROOT_KNOWN_HOSTS"] = os.environ.get("ROOT_KNOWN_HOSTS", ROOT_KNOWN_HOSTS)
    try:
        link_poll = float(os.environ.get("LINK_POLL", LINK_POLL))
    except (TypeError, ValueError):
        raise ValueError("LINK_POLL must be numeric") from None
    if not 20 <= link_poll <= 600:
        raise ValueError("LINK_POLL must be between 20 and 600 seconds")
    values["LINK_POLL"] = link_poll
    keys = parse_keys(os.environ.get("MENU_KEYS", ",".join(MENU_KEYS)))
    if len(keys) > 32:
        raise ValueError("MENU_KEYS must contain at most 32 keys")
    if any(key not in {"UP", "DOWN", "LEFT", "RIGHT", "ENTER", "EXIT", "BACK", "HOME"} for key in keys):
        raise ValueError("MENU_KEYS contains an unsupported key")
    values["MENU_KEYS"] = keys
    for name in ("AUTO_RECOVER_BLIPS", "AUTO_RECOVER_DROPS", "MENU_FALLBACK", "ALLOW_INSECURE_TLS"):
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


def root_diagnose():
    """Tri-etat root : ssh (probe bornee), luna, lien. Strictement lecteur et independant
    du SSAP — consulte meme si le WS est tombe, precisement le cas ou le root sert."""
    if ROOT_MODE == "ssap":
        return {"mode": "ssap", "available": False}
    probe = RootProbe(HOST, ROOT_SSH_KEY, ROOT_KNOWN_HOSTS)
    info = {"mode": ROOT_MODE, "available": probe.probe(),
            "ssh": probe.reason_detail or probe.reason}
    if info["available"]:
        try:
            info["link"] = dict(state=probe.link_status(), **probe.link_detail)
            info["luna"] = "ok"
        except RootError as exc:
            info["luna"] = exc.reason
        try:
            info["uptime"] = probe.uptime()
        except RootError as exc:
            info["uptime_error"] = exc.reason
    return info


def diagnose():
    result = {"reachable": reachable(), "paired": False, "paused": PAUSE_FILE.exists(),
              "evidence": "UNKNOWN", "identity": "unverified", "audio": "unverified",
              "last_attempt": last_attempt(), "watcher": load_state(),
              "root": root_diagnose()}
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

    probe = None
    if ROOT_MODE != "ssap":
        # Detection bornee (2 s) ; jamais d'exit : le projecteur coupe son Wi-Fi en veille, un
        # demarrage sans SSH est normal. Re-evaluation a chaque allumage (root et auto).
        probe = RootProbe(HOST, ROOT_SSH_KEY, ROOT_KNOWN_HOSTS)
        if probe.probe():
            log(f"root actif (uptime {probe.last_uptime:.0f} s) — lien A2DP lisible")
        else:
            log(f"root indisponible ({probe.reason_detail}) — lectures SSAP seules, re-evaluation au prochain allumage")

    tracker = PowerTracker()
    recovery = Recovery()
    n = 0
    saved = None
    next_link_read = 0.0

    def publish():  # state.json for --diagnose, rewritten only when the snapshot changes
        nonlocal saved
        state = recovery.snapshot(time.monotonic())
        if state != saved:
            save_state(state)
            saved = state

    while True:
        publish()
        event = tracker.update(reachable())
        if event == "off":
            log("projecteur eteint — surveillance du reseau...")
            recovery.power_off()
        elif event == "on":
            warm = WARMUP
            if probe is not None and probe.available:
                # Etape 2 : l'uptime tranche blip vs reboot. Reference = dernier echantillon
                # d'avant la coupure ; uptime qui continue = meme boot, pas de WARMUP.
                try:
                    previous, current = probe.last_uptime, probe.uptime()
                except RootError as exc:
                    probe.available, probe.reason = False, exc.reason
                    probe.reason_detail = str(exc)
                    log(f"root perdu ({exc}) — re-evaluation au prochain allumage")
                    log(f"projecteur detecte — warmup {WARMUP} s...")
                else:
                    if previous is not None and current >= previous:
                        warm = 0.0
                        log(f"uptime continu ({current:.0f} s) — coupure reseau sans reboot, warmup saute")
                    else:
                        log(f"projecteur detecte — warmup {WARMUP} s (uptime {current:.0f} s)")
            else:
                log(f"projecteur detecte — warmup {WARMUP} s...")
            recovery.power_on()
            publish()
            time.sleep(warm)
        if PAUSE_FILE.exists():
            time.sleep(POLL)
            continue
        if not tracker.online:
            time.sleep(SCAN)
            continue
        if tracker.misses:  # sonde ratee mais pas encore "eteint" : coupure breve, on ne touche a rien
            recovery.probe_missed()
            time.sleep(BLIP_POLL)
            continue
        if recovery.waiting(time.monotonic()):
            time.sleep(POLL)
            continue

        # --- tenter une session ---
        ws = None
        try:
            ws = open_ws()
            register(ws, ck)
        except Exception as e:
            close(ws)
            if recovery.session_failed():
                log(f"WS indisponible ({e.__class__.__name__}) — nouvelles tentatives toutes les {SCAN}s")
            if probe is not None and probe.available and time.monotonic() >= next_link_read:
                # Le root garde la visibilite pendant une panne SSAP : lecture seule, aucune
                # action possible sans session (popup, route, ecriture restent SSAP).
                next_link_read = time.monotonic() + LINK_POLL
                try:
                    recovery.link = probe.link_status()
                    log(f"WS tombe — lien A2DP (root): {recovery.link}")
                except RootError as exc:
                    probe.available, probe.reason = False, exc.reason
                    probe.reason_detail = str(exc)
                    log(f"WS tombe — lien A2DP illisible ({exc})")
            time.sleep(SCAN)
            continue
        if recovery.session_restored():
            log("WS retabli")

        n += 1
        try:
            out = sound_output(ws, n)
        except Exception:
            log("lecture etat impossible — reessai plus tard")
            close(ws)
            time.sleep(SCAN)
            continue

        if recovery.on_reading(out):
            result, n = connect_round(ws, n, recovery.methods())
            recovery.on_round(result, time.monotonic())
        elif (probe is not None and probe.available and recovery.phase is Phase.WATCH
              and classify_output(out) == "TARGET" and time.monotonic() >= next_link_read):
            # Cadence bornee : lecture du lien uniquement route cible + phase stable, toutes
            # les LINK_POLL secondes (pas un ssh par tour de boucle).
            next_link_read = time.monotonic() + LINK_POLL
            try:
                state = probe.link_status()
            except RootError as exc:
                probe.available, probe.reason = False, exc.reason
                probe.reason_detail = str(exc)
                log(f"lecture lien root impossible ({exc}) — re-evaluation au prochain allumage")
            else:
                recovery.on_link(state)
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
