# Operations and rollback

## Upgrade after review and explicit deployment instruction

```sh
cd ~/lg-cinebeam-sonos
git fetch origin --tags
git switch main
git pull --ff-only
# Check VERSION and the reviewed commit before continuing.
systemctl --user stop sonos-watcher
~/.venvs/sonos-watcher/bin/pip install -r requirements.txt
python3 tools/install.py
# Preserve existing env/key. Add the explicit TLS policy before restart.
chmod 600 ~/sonos-watcher/watcher.env ~/sonos-watcher/client-key.txt
systemctl --user daemon-reload
systemctl --user start sonos-watcher
systemctl --user status sonos-watcher --no-pager
```

The installer backs up code and the service unit before replacing them. It never copies keys or live env into the repository. Systemd must load an existing EnvironmentFile. Environment modifications apply only after restart. A service restart observes current audio; it does not reconnect.

## Rollback to the physically exercised baseline

```sh
cd ~/lg-cinebeam-sonos
git fetch origin --tags
systemctl --user stop sonos-watcher
git checkout daf39f76b5349f65b98a5a288ff06ae35b2eac59
~/.venvs/sonos-watcher/bin/pip install -r requirements.txt
cp watcher/sonos-watcher.py ~/sonos-watcher/sonos-watcher.py
cp watcher/sonos-watcher.service ~/.config/systemd/user/sonos-watcher.service
# Remove candidate's local pause flag only if you want baseline automation enabled.
rm -f ~/sonos-watcher/paused
printf '0.2.2\n' > ~/sonos-watcher/VERSION
systemctl --user daemon-reload
systemctl --user start sonos-watcher
```

Keep the existing client key and real SONOS_BT. The baseline ignores candidate TLS settings and uses its historical permissive LAN TLS behavior. Its startup and short-outage recovery are more aggressive; rollback changes behavior as well as code. Alternatively restore the exact code/unit from your installer `backup-*` directory. Rollback commands are documented, not claimed as executed on the projector for this candidate.

## Uninstall without discarding the key

```sh
systemctl --user disable --now sonos-watcher
rm -f ~/.config/systemd/user/sonos-watcher.service
systemctl --user daemon-reload
```

Retain `~/sonos-watcher` and the venv until you decide whether to discard private pairing/config/backups. No root, network, projector or physical-device cleanup is required. Disabling user lingering may affect other services, so it is not done automatically.

## Local permission and popup experiments

Stop/pause the watcher first and use a **separate** client-key file for permission experiments. Record firmware build, requested permissions, authenticated operations and the result before proposing any manifest reduction. New pairing may display a prompt and requires a separate hardware-test instruction. Never publish keys, private screenshot content, MACs or room identifiers. Synthetic popup fixtures in CI are not substitutes for local reference captures on the actual firmware.
