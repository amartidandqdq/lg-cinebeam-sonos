# legacy/

Early experiments kept for the investigation log (`trouvailles.md`). **Do not use them**: they
predate the watcher, and some are wrong (`reconnect-sonos.py` targets `bt_audio`, which the
projector cancels; the correct output is `bt_soundbar`). Use `watcher/sonos-watcher.py`.

`cleanup-root.sh`, `restore-root.sh` and `verify.sh` belong to the first goal of the project
(removing ads and telemetry from the projector with root). Root is not available on this firmware,
so they were never applied. Only `restore-root.sh` is still covered by a test (its `/etc/hosts` part).
