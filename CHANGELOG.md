# Changelog

## Unreleased — lot 1
- Observe at startup; preserve every non-default output from the first reading.
- Default to no action after ambiguous short outages; aggressive recovery is opt-in.
- Classify exact target, fallback, other and unknown routes. No BT identity claim.


## 0.2.2 - 2026-10-26

### Fixed
- Close an opened WebSocket when registration fails before retrying; repeated authentication
  timeouts no longer leave those connections open.
- Clarify that manual `tv_speaker` selection cannot be distinguished from a failed BT connection.

### Tests
- Cover one, two and three missed probes, repeated short power cycles, cancelling retries
  after an HDMI/ARC selection, and connection cleanup on registration timeout.

## 0.2.1 - 2026-10-26

### Fixed
- Short power cycles could be missed by the power-off hysteresis, leaving audio on the projector.
  Recheck the output after missed probes and reconnect with `luna` only if previously active BT
  was lost. Preserve manual output changes observed before a network interruption.
- Probe every 5 seconds after a failed online probe, while keeping the 4-probe power-off threshold.
- Add regression checks for short power cycles and network blips with BT still active.

### Validation
- Deployed on the HU710QKE on 2026-10-26: a real power cycle restored `bt_soundbar` on
  the first `luna` attempt and automatically accepted the connection popup. Audio heard
  at the speaker still requires user confirmation; sub-threshold cycles are covered by simulation.

## 0.2.0 - 2026-10-26

Hardening after a technical audit. **Not yet validated on hardware** (test planned on a real
power cycle); 0.1.0 is the version proven on the HU710QKE.

### Changed
- Power-off is only concluded after 4 consecutive failed probes, so a short LAN drop no longer
  looks like a power cycle and no longer triggers a reconnect.
- After a failed round the watcher retries up to 3 times (2, 10, 30 min), **luna only**: remote
  keys are never replayed on a retry.
- Restarting the service on an already-powered projector never sends remote keys.
- Retries stop if the user switched the sound output by hand.
- Log line `SONOS CONNECTEE` is now `SORTIE BT ACTIVE`: the projector reports the output, not
  the audio actually heard.
- Configuration moved to environment variables (`watcher.env`): `LG_HOST`, `SONOS_BT`,
  `MENU_KEYS`, `WARMUP`. The service refuses to start with a missing or placeholder `SONOS_BT`.

### Fixed
- `scripts/restore-root.sh` now really reverts the `/etc/hosts` changes of `debloat.sh`
  (it only contained no-op placeholders).

### Removed
- Unused `FALLBACK_HOSTS`.
- Obsolete experiments moved to `legacy/` (one of them targeted the wrong output, `bt_audio`).
- Third-party developer emails scrubbed from the app inventory snapshot.

### Added
- `tools/pair.py`, MIT license, tests (`pytest`), CI (`ruff` + `pytest`).

## 0.1.0 - 2026-10-25

First public version: luna A2DP connect, popup acceptance, menu fallback.
