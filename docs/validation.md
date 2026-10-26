# Validation record — 2026-10-26

## Proven historical baseline, not candidate results

Revision `daf39f76b5349f65b98a5a288ff06ae35b2eac59` (v0.2.2) is deployed on the user's Linux host. Earlier short-cycle fix: detected off at 19:00:17 CET, return at 19:00:32, focused popup accepted 19:01:04, bt_soundbar at 19:01:09 on first Luna attempt. Later socket-cleanup revision restarted 19:10:04 and observed the existing BT route without reconnecting. Read-only final check at 19:19:06: bt_soundbar, no popup, active service, zero automatic restarts. User explicitly confirmed sound heard on Sonos while projector content played.

Hardware: HU710QKE / Sonos Arc Ultra. Firmware family previously reported webOS 24; exact build was not recorded. Sonos version/build not recorded. This is one recorded working off/on scenario, not 30 consecutive candidate successes.

## Candidate 0.3.0-rc.1

Not deployed. No physical test result is claimed. The user's actual setup uses Bluetooth only; HDMI/manual-output protections are tested in simulation for the public project. No blind or repeated physical cycles were scheduled.

At source revision `df9a6b3070026569e5b52515342c0110d0d375de`, CI recorded **73 passed**
on each of Python 3.11, 3.12 and 3.13, including the loopback TLS/websocket integration.
[CI run](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/runs/40381770933)
and [Gitleaks](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/runs/40381771236)
are green. These are automated candidate results, not physical-device evidence.
Pending hardware acceptance is tracked separately in
[issue #11](https://github.com/amartidandqdq/lg-cinebeam-sonos/issues/11).

### Final software acceptance

Source revision `73c1731a859308d785a10271281f92f6bd487680` passes **81 tests on each of
Python 3.11, 3.12 and 3.13** with the pinned production dependencies, including the
OpenSSL/loopback TLS and POSIX-shell tests skipped on the local Windows environment.
[Final source CI](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/runs/40384523964)
and [Gitleaks](https://github.com/amartidandqdq/lg-cinebeam-sonos/actions/runs/40384523915)
passed. Ruff and strict OpenSpec validation passed as well.

Independent read-only review returned **ship** for this source revision: no remaining
blocker within the requested software scope. Earlier findings were reproduced and fixed:
output/pause changes during UI setup, final-read pause handling, end-to-end capture timeout,
stale diagnostic evidence and completion of connection-close HTTP bodies. The final review
also exercised 20 additional HTTP completion/size/deadline/cleanup checks. These supplementary
checks are reviewer evidence, not added to the 81-test repository count.

Software acceptance does not waive hardware acceptance. The five PRs remain a reviewable
chain; no merge, stable 0.3.0 tag or candidate deployment is asserted by this record.

| Scenario | Automated evidence | Candidate hardware status |
|---|---|---|
| Startup observation on tv_speaker / ARC / other BT | Simulated, zero mutation | Pending |
| Detected off/on, default route | Simulated reconnect allowed | 0/30; pending |
| 1–3 failed probes and repeated short cycles | Conservative default and explicit recovery opt-in simulated | Pending |
| Sonos unavailable and later returns | Bounded retries simulated | Pending |
| Output changed during retry | ARC guard simulated; manual tv_speaker ambiguity documented | Pending |
| Route transient/stable/status timeout | Exact-route stability simulated | Pending |
| Popup yes focus / blank / wrong focus / unreadable | Synthetic images; no private captures | Real reference-capture validation pending |
| Registration refusal/invalid payload, pin mismatch | Mocks with no device commands | Pending |
| Strict screenshot/WSS certificate policy | Unit boundaries and ephemeral loopback TLS test | Endpoint certificate compatibility pending |
| Pair permissions | Existing manifest preserved; refusal preserves key | Minimal subset pending, no working-key replacement |
| Install, key/config preservation, backup | Temporary home-directory regression | Real candidate upgrade/rollback pending |
| 48-hour resource/log endurance | Log size bounded; no inference from fake clock | 0 hours; pending |

The proposed 30/30, 20/20 and 48 h thresholds are acceptance goals, not measurements. For the Bluetooth-only installation, irrelevant physical manual-output scenarios can be waived explicitly while their simulation guards remain. No release claim of 10/10 until applicable thresholds are accepted and measured.

## Campaign entry template

Record date/time, script commit/VERSION, exact projector and speaker firmware builds, initial route/source, scenario, elapsed time, API evidence level, visible popup result, human acoustic confirmation, result and residual uncertainty. Never record secrets or private screen content. For endurance, record baseline/end service PID, restart count, RSS, log sizes and elapsed real time; do not equate a stable PID with no leak.

## Release gate

Five reviewable PR slices, focused tests, Ruff, Gitleaks and Python 3.11/3.12/3.13 CI are required. Hardware-only rows remain open until executed under explicit deployment/test instructions. Tag stable 0.3.0 only afterwards. The active OpenSpec change tracks the remaining campaign.
