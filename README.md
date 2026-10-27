# LG CineBeam → Sonos Bluetooth recovery

[![CI](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/workflows/ci.yml/badge.svg)](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/workflows/ci.yml)
[![Gitleaks](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/workflows/gitleaks.yml/badge.svg)](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/workflows/gitleaks.yml)
![Python 3.11–3.13](https://img.shields.io/badge/Python-3.11–3.13-blue)
![MIT](https://img.shields.io/badge/license-MIT-green)

A small local Python service reconnects a paired Sonos after the projector returns from a detected off/on cycle. No root on the projector, cloud service, Docker, MQTT or Home Assistant is required.

**Compatibility measured historically:** LG HU710QKE / webOS 24 and Sonos Arc Ultra. The deployed v0.2.2 completed one recorded power-cycle test with automatic popup acceptance and human-confirmed Sonos audio on 2026-10-26. **The 0.3.0 release candidate changes below have not been deployed or hardware-validated.** See [validation records](docs/validation.md).

## Behavior

1. Observe at service startup. Starting/restarting the service on an already-running projector changes no audio settings.
2. Require four failed probes before an off/on transition. This is a network heuristic, not proof of electrical power state.
3. Wait the configured warmup. Only the default `tv_speaker` output is eligible for automatic recovery; other outputs are preserved from the first reading.
4. Request A2DP via the existing Luna alert-close technique. Confirm the popup only if the known focused-Yes visual signature matches. No blind ENTER.
5. Require three exact `bt_soundbar` readings spanning at least ten seconds. Report `BT_ROUTE_STABLE`; device identity, A2DP link and audible sound remain unverified.
6. Retry failed rounds after 2, 10 and 30 minutes, Luna only; then stop until the next detected cycle. Recheck the output before each method.

The Luna technique comes from [lgtv-control-mcp](https://github.com/brunofgmag/lgtv-control-mcp): closing an alert triggers its internal `luna://com.webos.service.bluetooth2/a2dp/connect` URI. That protocol is preserved.

### Choices and ambiguity

- Short interruptions are observation-only by default. `AUTO_RECOVER_BLIPS=1` opts into Luna-only recovery when the target route was present before interruption and the default speaker route appears afterwards. This is useful for Bluetooth-only installations but can override a manual speaker choice made during the outage.
- `tv_speaker` selected manually is indistinguishable from the default after a failed BT connection. Use `--pause` before a deliberate speaker session.
- Another `bt_*` output is not treated as proof of Sonos identity and is not taken over.
- Menu fallback is off by default. `MENU_FALLBACK=1` plus `MENU_PROFILE=hu710qke-webos24` allows **one** sequence on the first round after a detected cycle. Never on startup or retry. Firmware/theme changes require local visual validation.
- Popup recognition uses median color patches, not semantic text recognition. Synthetic tests prove algorithm behavior; they do not prove recognition on arbitrary themes or firmware.

## Install

Use a Linux host on the same trusted LAN, Python 3.11–3.13 and a Sonos already paired to the projector through its Bluetooth menu.

```sh
git clone https://github.com/amartidandqdq/lg-cinebeam-sonos
cd lg-cinebeam-sonos
# Until merged: check out the reviewed release-candidate branch explicitly.
# git switch feat/diagnostics-and-operations
python3 -m venv ~/.venvs/sonos-watcher
~/.venvs/sonos-watcher/bin/pip install -r requirements.txt
python3 tools/install.py
```

The installer copies code and the systemd unit, backs up replaced code/unit files to `~/sonos-watcher/backup-*`, creates a private config template only if missing, and **never starts the service**. Existing configuration and client keys are preserved. Installation is tested in a temporary home directory.

Edit `~/sonos-watcher/watcher.env` before pairing or starting. Set the real address and a TLS policy; the template intentionally cannot run unchanged.

| Variable | Default | Meaning |
|---|---|---|
| `LG_HOST` | `192.168.1.2` | Projector IPv4 address or hostname, no URL/port |
| `SONOS_BT` | required | Real paired Sonos BT address; placeholders rejected |
| `TLS_FINGERPRINT` | unset | Independently verified SHA256 certificate pin |
| `ALLOW_INSECURE_TLS` | `0` | Explicit trusted-LAN exception if no verified pin; also required for HTTP screenshots |
| `WARMUP` | `25` | 0–300 seconds after detected off/on |
| `STABILITY_SECONDS` | `10` | 10–60 seconds spanning three exact-route readings |
| `AUTO_RECOVER_BLIPS` | `0` | Opt-in aggressive ambiguous-outage recovery |
| `MENU_FALLBACK` | `0` | Opt-in visible UI fallback |
| `MENU_PROFILE` | unset | Must be `hu710qke-webos24` when menu fallback enabled |
| `MENU_KEYS` | measured layout | Comma-separated UP/DOWN/LEFT/RIGHT/ENTER/EXIT/BACK/HOME |

Use `0` or `1` for boolean options. Invalid configuration exits with status 2; systemd does not restart that error in a loop.

### Pair and start

Load the private environment for interactive commands; systemd loads the same file automatically.

```sh
chmod 600 ~/sonos-watcher/watcher.env
set -a
. ~/sonos-watcher/watcher.env
set +a
~/.venvs/sonos-watcher/bin/python ~/sonos-watcher/pair.py "$LG_HOST"
# Accept the pairing prompt only if a new key is being created.
chmod 600 ~/sonos-watcher/client-key.txt
~/.venvs/sonos-watcher/bin/python ~/sonos-watcher/sonos-watcher.py --diagnose
systemctl --user daemon-reload
systemctl --user enable --now sonos-watcher
loginctl enable-linger "$USER"
```

Existing keys are reused and never overwritten on refusal. Pairing uses the same TLS policy. Permissions retain the historically working manifest: their minimal subset has not been validated on hardware. A separate experimental key can use `pair.py HOST NEW_KEY --permissions-file permissions.json`; do not replace the working key or claim a reduced manifest is verified without testing all required operations.

## Operate and diagnose

After loading `watcher.env` as above:

```sh
PY=~/.venvs/sonos-watcher/bin/python
WATCHER=~/sonos-watcher/sonos-watcher.py
"$PY" "$WATCHER" --diagnose       # read-only JSON; no audio mutations or key disclosure
"$PY" "$WATCHER" --pause          # persistent local pause flag
"$PY" "$WATCHER" --resume         # remove pause; does not force a reconnect
# For an explicit reconnect: pause and stop the daemon first, avoiding two active controllers.
"$PY" "$WATCHER" --pause
systemctl --user stop sonos-watcher
"$PY" "$WATCHER" --resume
"$PY" "$WATCHER" --reconnect-now  # Luna only, preserves other audio outputs
systemctl --user start sonos-watcher
journalctl --user -u sonos-watcher --since today
```

Diagnostics establish TCP reachability, authenticated SSAP, output route and last logged attempt. `BT_ROUTE_SELECTED` is a single setting read; `BT_ROUTE_STABLE` is three readings. Neither means `BT_LINK_CONFIRMED` or `AUDIO_VERIFIED`. A human confirmed audio on the deployed old version, not permanently for every future connection. Sonos UPnP media state was seen reporting a stopped radio while Bluetooth sound was heard; it is not used as independent BT proof.

Log lines include attempt/method/evidence/reason. The local log rotates at roughly 1 MB with three backups; journald retention is controlled by the host. No screenshots are saved by the watcher. Legacy debug tools may capture content: use them locally and never publish private captures.

| Symptom | Action |
|---|---|
| No reconnect immediately after service startup | Expected observation mode; use an explicit reconnect or the next detected off/on cycle |
| Stable route but no sound | Check the real speaker/popup; route stability cannot prove audible audio |
| Registration refused | Preserve the key; diagnose the projector pairing before explicitly creating a separate new key |
| Screenshot UNKNOWN | Check local endpoint, size, TLS policy and firmware appearance; no blind ENTER is sent |
| Certificate mismatch | Stop and independently check the certificate/firmware before updating the pin |
| Sonos unavailable | Bounded retries; check availability, then use the explicit reconnect procedure |

## Transport and secrets

Choose a locally verified SHA256 pin or explicitly accept `ALLOW_INSECURE_TLS=1` on a trusted home LAN. There is no silent TOFU acceptance. Verify a certificate through an independent trusted local channel before pinning it; merely querying an untrusted network endpoint is not proof of identity. A mismatch fails before SSAP registration. Strict pin mode has **not** been checked on the projector; screenshot and WSS services may use different certificates.

Screenshot destinations must match `LG_HOST`, use HTTP(S), no credentials/fragment, and allowed ports 80/443/3000/3001. Redirects, excessive encoded size (4 MB) and image dimensions (>8.5 MP) are rejected. A short-lived local Python worker is killed and reaped at the eight-second timeout, covering DNS, TCP, TLS, headers and body together (plus OS cleanup overhead). It receives only screenshot endpoint/policy options, never the SSAP key. HTTP screenshots require explicit insecure mode. Pointer sockets require WSS on the configured host/port. Do not expose the projector ports to the internet. Keys/config must remain private; runtime key permissions are checked on Linux.

## Upgrade, rollback and uninstall

See [operations](docs/operations.md) for exact commands. Do not deploy a candidate merely because CI is green. The historical rollback target is `v0.2.2` / `daf39f76b5349f65b98a5a288ff06ae35b2eac59`; keep your private env/key and use the matching old service unit and dependencies. Never restore an example Bluetooth address over live configuration.

## Development and release

```sh
python -m pip install -r requirements.txt -r requirements-dev.txt
ruff check .
python -m pytest -q
openspec validate reliable-local-reconnect --strict
```

CI runs on Python 3.11, 3.12 and 3.13. Tests simulate projector/clock and exercise transport, non-interference, stability, popup focus, pairing refusal, installer preservation and isolated `/etc/hosts` rollback. No test drives physical equipment. The 30-cycle and 48-hour targets are still pending for the candidate, not inferred from fake time.

`VERSION` identifies the candidate. Cut a stable tag only after review, merge and the accepted hardware campaign. The active OpenSpec change remains open until those validation tasks are complete.

| Path | Purpose |
|---|---|
| `watcher/`, `tools/pair.py`, `tools/install.py` | Supported recovery service, pairing and installer |
| `tests/`, `openspec/`, `docs/` | Automated checks, behavioral contract and operations/validation records |
| `scripts/`, `PLAN.md`, `trouvailles.md`, `legacy/` | Project history: the initial goal (cleaning ads and telemetry off the projector, which needs root) was dropped, and the project became the Sonos reconnect. Not required for recovery |

**The early root-level cleanup scripts in `legacy/` are abandoned and outside the supported watcher.** Root is not available on this firmware, so they were never applied to the projector. `legacy/restore-root.sh` keeps an isolated hosts-file regression test; nothing there is hardware-validated. Do not run them. MIT licensed.
