# Design

Keep the existing SSAP/Luna protocol and PowerTracker. Startup is observation; four missed TCP probes permit recovery on return but remain a heuristic, not proof of power state. Only tv_speaker is an eligible default route; other routes are preserved. Ambiguous short outages do not authorize mutations unless explicitly opted in.

Use exact bt_soundbar route and three spaced readings spanning at least ten seconds. Evidence never exceeds BT_ROUTE_STABLE without a separately validated signal. Previously observed Sonos UPnP media state did not track audible Bluetooth and is unsuitable as independent proof.

Preserve the known popup signature as a firmware-specific heuristic, isolate image recognition, return explicit unknown on unreadable screenshots, and permit at most one menu fallback. No private screen captures in Git; synthetic fixtures test algorithms, not hardware recognition accuracy.

All SSAP waits use an absolute deadline and validate registration. TLS uses a locally supplied SHA256 certificate pin, or explicitly opted-in insecure LAN mode; do not silently trust first contact. Validate screenshot/pointer destinations, prohibit redirects and bound downloads. Pairing permissions remain unchanged pending separate hardware experiments; retain existing keys and fail safely rather than claiming minimal permissions.

Use stdlib file controls, bounded log rotation and JSON diagnostics; no daemon, database or mandatory platform integration. Never publish client keys, real device identifiers or captured private content. Tests simulate both positive and negative boundaries; actual firmware/TLS/pairing/endurance validation stays pending.

The user uses Bluetooth only; HDMI/manual-output guards protect the public project, while hardware validation focuses on boot, Sonos availability, popup and endurance. Five PRs may depend sequentially on earlier slices because the watcher is shared.
