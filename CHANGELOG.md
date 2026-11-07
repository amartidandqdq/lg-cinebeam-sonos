# Changelog

## 0.3.1 — 2026-11-07
- Add opt-in `AUTO_RECOVER_DROPS`: when the target BT route falls back to the projector
  speaker while the projector stays on (observed 2026-11-07 around 12:50), reconnect with
  Luna only after two consecutive readings, at most 5 times per power-on, never at startup.
- A definitive failure clears the BT memory so retries stop until the next power-on.

## 0.3.0 — 2026-11-07
Promoted from 0.3.0-rc.1 by owner decision on ten days of daily field use (see
docs/validation.md, "Field use"); the formal 30/30 campaign and 48 h endurance rows stay open.
- Retry a failed round after 15 s first (then 2, 10, 30 min): a single slow first attempt no
  longer delays Sonos sound by several minutes.
- Tolerate a pointer-socket timeout when accepting the Bluetooth popup: the press is retried
  on the next popup check instead of abandoning the round.
- Skip the final `changeSoundOutput` when the popup already selected the target route, and
  give it a 10 s deadline otherwise (the projector answers slowly right after BT connect).
- After `output_rolled_back`, start the next Luna attempt after 2 s instead of 5 s.
- Log a websocket outage once and its recovery once, instead of every 15 s while watching.

## Earlier unreleased changes (shipped in 0.3.0)
- Stabilize the loopback TLS integration test: the test server now negotiates TLS 1.2, avoiding an
  intermittent websockets handshake timeout in CI while still exercising real certificate pinning.
- Refocus the repository on the Sonos reconnect: removed the unrelated projector-cleanup plan, scripts,
  blocklist and app inventory.
- Add free public-repo tooling: CodeRabbit and Greptile repository configs, native CodeQL
  static analysis, OpenSSF Scorecard and Dependabot workflows.
- Deployed candidate 0.3.0-rc.1 on the reference host (2026-10-28): one acoustic-confirmed
  automatic recovery, a 5/5 consecutive rapid-cycle campaign, and an opened 48-hour
  endurance window; the stable release remains gated on the hardware campaign.

## 0.3.0-rc.1 — deployed 2026-10-28
- Accept completed Content-Length screenshots when HTTP/1.0 or Connection: close has
  closed the socket; cover length, EOF and chunked loopback responses.
- Final boundary regressions: recheck pause after the last route read; bound DNS/TCP/TLS
  together with screenshot I/O using a killable, reaped local worker.
- Independent review: recheck output before popup confirmation, enforce a total screenshot
  deadline and record terminal evidence consistently after failed attempts.
- Add a loopback TLS/websocket integration test using the pinned production dependency.
- Add explicit pause/resume/reconnect controls and read-only JSON diagnostics.
- Validate configuration and private key permissions; rotate local logs.
- Install code/unit with backups while preserving existing key and config.
- Reuse TLS policy for pairing; preserve existing key on refusal.
- Add Python 3.11–3.13 CI, operational rollback and hardware-validation record.
- Hardware-only release gates remain open; no candidate deployment is claimed.


## Unreleased — lot 4
- Validate registration and bound SSAP response waits by absolute deadlines.
- Require a verified certificate pin or explicit insecure-LAN opt-in.
- Check screenshot and pointer destinations; reject redirects and bound screenshot bytes/pixels.
- Keep existing SSAP permissions pending hardware validation.


## Unreleased — lot 3
- Recognize focused popup with median pixel patches; unreadable capture is UNKNOWN.
- Disable menu fallback by default; explicitly enabled known profile allows one sequence.
- Test synthetic positive, blank, wrong-focus, corrupt and isolated-pixel screenshots.


## Unreleased — lot 2
- Require three exact-target readings over at least ten seconds.
- Report stable route separately from unverified device identity, link and audio.
- Recheck current output before every connection method and stop on another output.


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

### Removed
- Unused `FALLBACK_HOSTS`.
- Obsolete experiments moved to `legacy/` (one of them targeted the wrong output, `bt_audio`).
- Third-party developer emails scrubbed from the app inventory snapshot.

### Added
- `tools/pair.py`, MIT license, tests (`pytest`), CI (`ruff` + `pytest`).

## 0.1.0 - 2026-10-25

First public version: luna A2DP connect, popup acceptance, menu fallback.
