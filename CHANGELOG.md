# Changelog

## 0.4.0 — 2026-11-09
- Optional read-only root transport (`ROOT_MODE=auto|ssap|root`): the watcher reads the real
  A2DP link state (`bluetooth2/a2dp/getStatus`) and `/proc/uptime` over SSH instead of inferring
  from `soundOutput`. Steps 1-2 of the root plan: visibility only, no writes — `connect`, popup
  and output writes stay SSAP. Measured on firmware 03.00.27: `luna-send` requires a PTY
  (`ssh -tt`), returns rc=0 with no output otherwise, and the reply contract parses the last
  JSON line and treats rc=0 + empty output as a transport error.
- New `bt_link_lost` visibility: the measured failure where the route claims the BT target while
  the A2DP link is down (2026-11-09 19:52) is now detected, confirmed on two reads, logged once
  per episode and published in `state.json` (`link`). The ambiguous `errorCode 106` maps to
  `unavailable` and never triggers action pending discrimination (reset bluetooth2 vs unpair vs
  address change).
- The 25 s warmup is skipped when uptime proves the projector did not reboot (network blip);
  kept after a real reboot. Root is probed at startup and re-probed at each power-on and always
  degrades silently to SSAP (the projector cuts its Wi-Fi in standby; a failed startup probe is
  normal, never fatal).
- `--diagnose` gains a `root` tri-state (`ssh` / `luna` / `link`), consulted even while the WS
  is down. SSH host keys are pinned on first connection (`ROOT_KNOWN_HOSTS`, accept-new): a host
  key change becomes a hard error instead of a silent prompt.
- New env: `ROOT_MODE` (default auto), `ROOT_SSH_KEY`, `ROOT_KNOWN_HOSTS`, `LINK_POLL`
  (default 60 s, bounded 20-600). Without SSH the behavior is unchanged (existing suite green;
  new coverage in `tests/test_root_link.py`).

## 0.3.3 — 2026-11-08
- Make the main loop's recovery lifecycle explicit: a `Phase` enum (`STARTUP_OBSERVE`, `OFF`,
  `RECOVER`, `RETRY_WAIT`, `WATCH`) and a `Recovery` class replace ten interacting flags.
  Behavior is unchanged (existing suite untouched; old/new loops identical on 3000 randomized
  simulated scenarios). See docs/state-machine.md.
- Log each phase change once as `state=OLD->NEW reason=...`.
- `--diagnose` now reports the daemon's phase, reason, retry/drop counters and next retry time
  under `watcher`, read from `~/sonos-watcher/state.json` (written only on change, no secrets).

## 0.3.2 — 2026-11-07
- Fix (found by Codex review of #17): after a failed drop or blip recovery, the next retry
  re-ran the startup observation and was counted as a new drop, resetting the retry ladder.
  Retries now advance 15 s → 2 → 10 → 30 min and stop; the startup observation runs once.

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
