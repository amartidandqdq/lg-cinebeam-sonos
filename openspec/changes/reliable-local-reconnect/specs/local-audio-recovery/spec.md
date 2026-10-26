## ADDED Requirements

### Requirement: Conservative audio recovery
The service SHALL observe on startup, preserve non-default outputs and avoid ambiguous short-outage recovery unless explicitly enabled.
#### Scenario: Startup with an existing audio choice
- **WHEN** the service starts with the projector already reachable
- **THEN** it issues no connection or remote-key commands
#### Scenario: Detected off/on cycle
- **WHEN** four consecutive probes fail then reachability returns with tv_speaker selected
- **THEN** bounded reconnect attempts are permitted after warmup

### Requirement: Honest connection evidence
The service SHALL report stable exact-target routing separately from Bluetooth identity, link and audible audio.
#### Scenario: Transient route
- **WHEN** bt_soundbar rolls back before three readings spanning ten seconds
- **THEN** no stable success is reported

### Requirement: Bounded trusted transport and UI actions
The service SHALL validate registration, bound I/O, restrict screenshot destinations and require a recognized focused popup before confirmation.
#### Scenario: Refused registration
- **WHEN** SSAP returns an error during registration
- **THEN** the socket closes and no audio commands are issued
#### Scenario: Unreadable screenshot
- **WHEN** a screenshot cannot be safely retrieved or decoded
- **THEN** no confirmation key is sent

### Requirement: Reviewable operation
The service SHALL provide read-only diagnostics, explicit controls, reproducible installation and hardware-validation records distinguishing pending work.
#### Scenario: Diagnostic request
- **WHEN** diagnostic mode runs
- **THEN** it reports observed state without changing playback, volume, output or settings
