#!/usr/bin/env python3
"""Q1 discrimination battery CLI (root plan, step 3 gate) — thin wrapper over the watcher.

Run it while `a2dp/getStatus` answers 106 ("Device with supplied address is not
available") to tell apart, without touching audio:
- link down but still paired           -> a2dp/connect may repair it,
- bluetooth2 adapter reset / powered off,
- unpaired device or changed address   -> 106 is permanent, re-pair is needed.

Read-only by default. `--repair` additionally sends a2dp/connect and re-reads the
link; it is only meaningful (and cannot cut any audio) while the link is already
dead. The deployed watcher runs the same battery automatically on every link
episode and files the evidence under `~/sonos-watcher/q1-captures/`.

Key material is never printed (presence and size only).

Usage:
  q1_battery.py [--repair] [--host H] [--bt AA:BB:CC:DD:EE:FF]
Environment: LG_HOST, SONOS_BT, ROOT_SSH_KEY, ROOT_KNOWN_HOSTS (as the watcher).
"""
import argparse
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_watcher():
    spec = importlib.util.spec_from_file_location("sonos_watcher", ROOT / "watcher" / "sonos-watcher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    parser = argparse.ArgumentParser(description="Q1 discrimination battery (read-only unless --repair)")
    parser.add_argument("--repair", action="store_true",
                        help="after the reads, send a2dp/connect and re-read the link")
    parser.add_argument("--host", default=None, help="default: LG_HOST env")
    parser.add_argument("--bt", default=None, help="default: SONOS_BT env")
    args = parser.parse_args()

    watcher = load_watcher()
    watcher.validate_config()  # same env contract as the service; exits with a clean error
    probe = watcher.RootProbe(args.host or watcher.HOST, watcher.ROOT_SSH_KEY, watcher.ROOT_KNOWN_HOSTS)
    if not probe.probe():
        print(json.dumps({"error": "root_unavailable", "detail": probe.reason_detail}), file=sys.stderr)
        return 2

    replies = watcher.q1_battery(probe, watcher.SONOS_BT)
    report = {"bt": watcher.SONOS_BT, "verdict": watcher.q1_verdict(replies),
              "replies": watcher.q1_masked(replies)}
    if args.repair:
        if replies["a2dp_getStatus"].get("returnValue"):
            report["repair"] = "skipped: link is already up"
        else:
            connect = probe.luna("luna://com.webos.service.bluetooth2/a2dp/connect",
                                 {"address": watcher.SONOS_BT}, t=15)
            report["repair"] = {"connect": watcher.q1_masked({"connect": connect})["connect"],
                                "link_after": probe.link_status(),
                                "note": ("131 already connected or returnValue true: check link_after"
                                         if connect.get("returnValue") or connect.get("errorCode") == 131
                                         else "connect refused or failed; link_after recorded as evidence")}
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
