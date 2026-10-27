# LG CineBeam Q → Sonos Arc Ultra, reconnected automatically

[![gitleaks](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/workflows/gitleaks.yml/badge.svg)](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/workflows/gitleaks.yml)
![Dependabot](https://img.shields.io/badge/dependabot-enabled-025E8C?logo=dependabot)
![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![webOS](https://img.shields.io/badge/webOS-24-A50034)
[![ci](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/workflows/ci.yml/badge.svg)](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/workflows/ci.yml)
![License](https://img.shields.io/badge/license-MIT-green)

Turn the projector on. About 40 seconds later, the sound plays on the Sonos.
No root, no developer mode, no remote in hand, no "Yes" to click.

> **The problem.** The LG CineBeam Q (HU710QKE, webOS 24) forgets its Bluetooth soundbar on every
> cold boot. Getting it back takes six clicks in the menus plus a confirmation popup, every time.
>
> **The fix.** A ~250-line Python watcher on any always-on Linux box on the LAN. It notices the
> projector powering on and reconnects the Sonos through the projector's own local API (SSAP).

## How it works

```mermaid
flowchart LR
    A[Projector powers on] --> B[Port 3001 answers<br/>wait 25 s]
    B --> C{Output already<br/>bt_*?}
    C -- yes --> Z[Nothing to do]
    C -- no --> D[luna a2dp/connect<br/>via createAlert trick]
    D --> E[Screenshot:<br/>Yes/No popup?]
    E -- seen --> F[Press ENTER]
    F --> G[changeSoundOutput<br/>bt_soundbar]
    E -- not seen --> G
    G --> H{Sound on Sonos?}
    H -- yes --> Z
    H -- "no (after 2 tries)" --> I[Fallback: replay<br/>remote keys in Settings]
    I --> H
```

| Step | What happens | SSAP call |
|------|--------------|-----------|
| Detect | TCP probe on the projector every 15 s | none |
| Check | Read the current sound output | `ssap://audio/getStatus` |
| Connect | Open the A2DP link to the Sonos | `luna://com.webos.service.bluetooth2/a2dp/connect` |
| Accept | Find the "wants to connect" popup on a screenshot, press ENTER | `ssap://tv/executeOneShot` + pointer input socket |
| Route | Send the audio to the soundbar | `ssap://com.webos.service.apiadapter/audio/changeSoundOutput` |
| Fallback | Settings → Sound → Sound Out → Wireless Speaker → Sonos → Connect | `system.launcher/launch` + remote keys |

It observes an already-running projector at service startup. Automatic reconnect is permitted after the configured off/on detection; TCP reachability is a heuristic, not proof of electrical power state.

### Safety rules

- A **short LAN drop is not a power-off**: the projector is declared off only after 4 failed probes in a row.
- Ambiguous short interruptions are observation-only by default. `AUTO_RECOVER_BLIPS=1` permits Luna-only recovery if the exact target route was active before the interruption and the default speaker route is observed afterwards. This opt-in may override a manual speaker selection made during the interruption.
- Menu navigation is disabled by default. Set `MENU_FALLBACK=1` and `MENU_PROFILE=hu710qke-webos24` only on the measured firmware. At most one menu sequence is permitted after a detected off/on cycle, never on retry or service startup. Popup ENTER requires a matching focused Yes signature; this is a firmware-specific visual heuristic, not semantic recognition.
- After a failed round: up to 3 retries (2, 10, 30 min), invisible `luna` only. Then it gives up until the next power-on.
- Retries stop when another output such as HDMI/ARC is observed. Selecting `tv_speaker` by hand is indistinguishable from the projector's default after a failed BT connection, so that choice cannot cancel retries reliably.
- Only the exact `bt_soundbar` route is the target; another BT route is preserved. Route selection does not establish device identity or audible audio.

## Quick start

**You need:** the projector and a Linux box on the same LAN, Python 3.11+, and the Sonos already
paired once over Bluetooth from the projector menu.

1. **Install**

   ```sh
   git clone https://github.com/amartidandqdq/lg-cinebeam-sonos && cd lg-cinebeam-sonos
   python3 -m venv ~/.venvs/sonos-watcher
   ~/.venvs/sonos-watcher/bin/pip install -r requirements.txt
   mkdir -p ~/sonos-watcher && cp watcher/sonos-watcher.py ~/sonos-watcher/
   ```

2. **Pair with the projector (once).** With the projector on, run the command below and accept the
   prompt on screen within 60 s. The key lands in `~/sonos-watcher/client-key.txt`.

   ```sh
   ~/.venvs/sonos-watcher/bin/python tools/pair.py 192.168.1.2
   ```

3. **Configure.** Create `~/sonos-watcher/watcher.env` from `watcher/watcher.env.example`:

   | Variable | Set it to | Default |
   |----------|-----------|---------|
   | `LG_HOST` | Projector LAN IP (reserve it in your router) | `192.168.1.2` |
   | `SONOS_BT` | Sonos Bluetooth address (same as its Wi-Fi MAC on the Arc Ultra). **Required**: the service refuses to start without it | none |
   | `MENU_KEYS` | Comma-separated key path of the fallback, if your menu differs | webOS 24 path |
   | `WARMUP` | Seconds to wait after power-on | `25` |

   `TARGET` (`bt_soundbar`) and the retry timings are constants at the top of the script.

4. **Run as a user service**

   ```sh
   mkdir -p ~/.config/systemd/user
   cp watcher/sonos-watcher.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now sonos-watcher
   loginctl enable-linger "$USER"   # keep it running after logout
   ```

5. **Check.** Power-cycle the projector, then:

   ```sh
   tail -f ~/sonos-watcher/watcher.log
   ```

   ```text
   projecteur detecte — warmup 25 s...
   sortie actuelle tv_speaker -> connexion Sonos...
     popup de connexion detecte -> Yes
     tentative 1/2 (luna): SORTIE BT ACTIVE
   ```

   Log lines are in French. Uninstall with `systemctl --user disable --now sonos-watcher`.

## The luna trick

SSAP clients cannot call `luna://` services directly. webOS will, however, run the URI attached to a
system alert's `onclose` when that alert is closed. So the watcher:

1. creates an alert whose `onclose`, `onfail` and button all point to the luna call;
2. closes it straight away with `closeAlert`.

The call runs blind (no response comes back), so the watcher checks the result through
`audio/getStatus`. Credit for the technique:
[brunofgmag/lgtv-control-mcp](https://github.com/brunofgmag/lgtv-control-mcp).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Output says `bt_soundbar` but sound stays on the projector | The Yes/No popup was not accepted | Check the `POPUP` pixel signature against a fresh capture (`tools/popup.py`) |
| `echec definitif` | Sonos off, asleep or out of range | Wake the Sonos; it retries at the next power-on |
| Fallback opens the wrong menu | Menu order differs, or the Sonos is not the first registered device | Adjust `MENU_KEYS` in `watcher.env` while watching `tools/nav.py` screenshots |
| `WS indisponible` in a loop | Wrong `HOST` or a revoked `client-key` | Fix the IP, pair again |
| Sound drops when you start Sonos radio | Sonos leaves BT for the new source | Expected; the watcher only acts once per power-on |

## Repository layout

| Path | Contents |
|------|----------|
| `watcher/` | The service and its systemd unit |
| `tools/` | `pair.py` (one-time pairing), plus debug helpers: `nav.py` (keys and screenshots), `luna.py` (raw luna call), `a2dp.py` (connect test), `popup.py` (popup detection), `sonosctl.py` (Sonos UPnP state) |
| `tests/` | `pytest` suite: power-off hysteresis, bounded retries, a simulated `main()` loop, `/etc/hosts` rollback |
| `scripts/`, `PLAN.md`, `trouvailles.md` | The original debloat plan (separate, experimental, reversible with `restore-root.sh`) and the full investigation log (French; §10–12 cover the reconnect) |
| `legacy/` | Superseded experiments. Do not use |
| `backup/` | Read-only snapshot of the projector's app inventory |

## Limitations

- Tested on one setup: HU710QKE, webOS 24, Sonos Arc Ultra.
- A firmware update may move the popup or reorder the menus. Both are one constant to update.
- The `client-key` grants control of the projector. It is git-ignored (and written `0600`); keep it that
  way. MACs and Sonos IDs in this repo are placeholders.
- TLS certificate checks are off: the projector presents a self-signed certificate. Keep port 3001 on
  your LAN only.
- The pairing manifest asks for broad SSAP permissions (copied from the key that is known to work).
  Narrowing them is untested.

## Development

```sh
pip install -r requirements.txt -r requirements-dev.txt
ruff check . && python -m pytest -q
```

Version history: [CHANGELOG.md](CHANGELOG.md). Licensed under [MIT](LICENSE).

## Thanks

- [brunofgmag/lgtv-control-mcp](https://github.com/brunofgmag/lgtv-control-mcp) for the `createAlert`
  → `luna://` technique. Without it, this would still be a remote-key macro.
- The webOS homebrew and SSAP community, whose reverse-engineering notes made the local API usable.
- [websockets](https://github.com/python-websockets/websockets) and
  [Pillow](https://github.com/python-pillow/Pillow), the only two dependencies.

## Disclaimer

Personal project, not affiliated with LG Electronics or Sonos. It uses the projector's local
API only; nothing leaves your LAN.

### Connection evidence

`BT_ROUTE_STABLE` means three exact `bt_soundbar` readings over at least ten seconds (`STABILITY_SECONDS`, default 10). Device identity, A2DP link and audible audio remain unverified. A transient route or status timeout is not success. Sonos UPnP media status was observed to report a stopped radio while Bluetooth audio was heard; it is not used as a Bluetooth proof.

Popup tests use synthetic layouts. No private screenshots are committed; alternate themes and changed firmware require local capture validation before enabling UI fallback.

### Transport policy (next version)

Supply `TLS_FINGERPRINT` as a SHA256 certificate fingerprint independently checked on your projector. No automatic first-use trust is stored. A changed certificate fails closed before SSAP registration; investigate firmware/reset before updating the pin. To retain the previous trusted-home-LAN compromise explicitly set `ALLOW_INSECURE_TLS=1`. Without a pin or that opt-in startup fails. Never expose these ports outside your LAN.

Screenshot URLs must point to the configured projector, with an allowed HTTP(S) port; redirects, credentials, oversized images and unexpected destinations are rejected. HTTP screenshots require the explicit insecure-LAN opt-in, even with a WSS certificate pin. The screenshot and pointer endpoints must be checked on hardware before adopting strict mode.

Pairing permissions are intentionally unchanged: reducing them without device tests could revoke working functionality. Existing keys are preserved; minimal-permission experiments remain a separate local hardware task.
