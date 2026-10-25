# LG CineBeam Q → Sonos Arc Ultra: Bluetooth auto-reconnect

LG CineBeam Q (HU710QKE, webOS 24) forgets its Bluetooth soundbar after every cold boot.
`watcher/sonos-watcher.py` runs on a Linux box on the LAN and reconnects the Sonos as soon as
the projector powers on: no root, no developer mode, no manual click.

## How it works

1. Polls the projector's SSAP port (3001). On power-on, waits 25 s for webOS to settle.
2. Opens the A2DP link with `luna://com.webos.service.bluetooth2/a2dp/connect`. The call is
   tunnelled through SSAP: a `createAlert` whose `onclose` points to the luna URI, then
   `closeAlert` (trick from `brunofgmag/lgtv-control-mcp`).
3. The Sonos answers with a "wants to connect… Yes/No" popup. The watcher detects it on an
   `ssap://tv/executeOneShot` screenshot (pixel signature) and presses ENTER via the pointer
   input socket.
4. Sets `changeSoundOutput` to `bt_soundbar`.
5. Fallback: replays remote keys through Settings → Sound → Sound Out → Use Wireless Speaker →
   Sonos → Connect.

Runs once per power-on, so a later manual choice of sound output is respected.

## Install (Debian, user service)

```sh
python3 -m venv --without-pip ~/.venvs/sonos-watcher   # then add websockets + pillow
mkdir -p ~/sonos-watcher && cp watcher/sonos-watcher.py ~/sonos-watcher/
# pair once (accept the prompt on the projector) and store the key in ~/sonos-watcher/client-key.txt
cp watcher/sonos-watcher.service ~/.config/systemd/user/
systemctl --user enable --now sonos-watcher
```

Edit `HOST`, `SONOS_BT` and `MENU_KEYS` at the top of the script for another setup.
`client-key.txt` is a secret and is git-ignored.

## Layout

- `watcher/`: the service and its systemd unit.
- `tools/`: debugging helpers. `nav.py` sends keys and takes a screenshot, `luna.py` makes a raw
  luna call, `a2dp.py` runs a connect test, `sonosctl.py` reads the Sonos UPnP state.
- `scripts/`, `PLAN.md`, `trouvailles.md`: the original debloat plan and the full investigation
  log (in French; §10–12 cover the reconnect).
- `backup/`: the projector app inventory (read-only snapshot).
