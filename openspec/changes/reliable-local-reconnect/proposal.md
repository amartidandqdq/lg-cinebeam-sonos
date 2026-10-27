# Proposal

## Why
The working Bluetooth reconnect must avoid taking over an existing audio choice, and report only evidence actually measured. Authentication, screenshots and installation need bounded, testable failure handling.

## What Changes
- **BREAKING**: observe on service startup and ambiguous network interruptions by default; optional recovery is explicit.
- Classify exact output routes and observe stability without claiming speaker identity or audible audio.
- One optional menu fallback, bounded popup handling, strict SSAP registration and safe screenshot transport.
- Explicit TLS policy, configuration validation, read-only diagnostics, controls and documented rollback.
- Five reviewable delivery slices; no hardware deployment in this change.

## Capabilities
### New Capabilities
- `local-audio-recovery`: conservative recovery, evidence, bounded I/O, operational controls.
### Modified Capabilities
None.

## Impact
Watcher, pairing/diagnostic tools, tests, service unit, CI and docs. No new mandatory production dependency. Existing on-device version remains unchanged until a separate deployment instruction. Hardware-only acceptance remains open.
