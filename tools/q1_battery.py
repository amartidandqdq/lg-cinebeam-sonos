#!/usr/bin/env python3
"""Q1 discrimination battery for a2dp getStatus errorCode 106 (root plan, step 3 gate).

Run it while `a2dp/getStatus` answers 106 ("Device with supplied address is not
available") to tell apart, without touching audio:
- link down but still paired           -> a2dp/connect may repair it,
- bluetooth2 adapter reset / powered off,
- unpaired device or changed address   -> 106 is permanent, re-pair is needed.

Read-only by default. `--repair` additionally sends a2dp/connect and re-reads the
link; it is only meaningful (and cannot cut any audio) while the link is already
dead. Run it twice — once while the link is healthy to keep a reference snapshot.

Output is JSON on stdout. The link key is never printed (presence and length only).

Usage:
  q1_battery.py [--repair] [--host H] [--bt AA:BB:CC:DD:EE:FF]
Environment: LG_HOST, SONOS_BT, ROOT_SSH_KEY, ROOT_KNOWN_HOSTS (as the watcher).
"""
import argparse
import importlib.util
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent


def load_watcher():
    spec = importlib.util.spec_from_file_location("sonos_watcher", ROOT / "watcher" / "sonos-watcher.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def masked(reply):
    """Copy of a luna reply with any key material replaced by its size (str or byte list)."""
    out = {}
    for key, value in reply.items():
        if "key" in key.lower() and value:
            if isinstance(value, list):
                out[key] = f"<present: {len(value)} bytes>"
            elif isinstance(value, str):
                out[key] = f"<present: {len(value)} chars>"
            else:
                out[key] = value
        else:
            out[key] = value
    return out


def verdict(replies):
    status = replies["a2dp_getStatus"]
    if status.get("returnValue"):
        return "link_up: no discrimination needed; keep this snapshot as the healthy reference"
    if status.get("errorCode") != 106:
        return f"unexpected errorCode {status.get('errorCode')}: extend the battery before acting"
    adapter = replies["adapter_getStatus"]
    linkkey = replies["getLinkKey"]
    if not adapter.get("returnValue") or adapter.get("powered") is False:
        return "106 with adapter down or reset: a2dp/connect cannot repair; re-check the adapter first"
    if not linkkey.get("returnValue") or not linkkey.get("linkKey"):
        return "106 with adapter up and no link key: unpaired or address changed; 106 is permanent, re-pair"
    return ("106 with adapter up and link key present: link down but still paired; "
            "a2dp/connect is expected to repair (run again with --repair)")


def main():
    parser = argparse.ArgumentParser(description="Q1 discrimination battery (read-only unless --repair)")
    parser.add_argument("--repair", action="store_true",
                        help="after the reads, send a2dp/connect and re-read the link")
    parser.add_argument("--host", default=os.environ.get("LG_HOST", "192.168.1.2"))
    parser.add_argument("--bt", default=os.environ.get("SONOS_BT", ""))
    args = parser.parse_args()

    watcher = load_watcher()
    bt = watcher.validate_bt(args.bt or "")
    probe = watcher.RootProbe(args.host, watcher.ROOT_SSH_KEY, watcher.ROOT_KNOWN_HOSTS)
    if not probe.probe():
        print(json.dumps({"error": "root_unavailable", "detail": probe.reason_detail}), file=sys.stderr)
        return 2

    replies = {
        "uptime": probe.uptime(),
        "a2dp_getStatus": probe.luna("luna://com.webos.service.bluetooth2/a2dp/getStatus", {"address": bt}),
        "adapter_getStatus": probe.luna("luna://com.webos.service.bluetooth2/adapter/getStatus"),
        "getLinkKey": probe.luna("luna://com.webos.service.bluetooth2/device/internal/getLinkKey", {"address": bt}),
        "avrcp_getStatus": probe.luna("luna://com.webos.service.bluetooth2/avrcp/getStatus", {"address": bt}),
    }
    report = {"bt": bt, "verdict": verdict(replies), "replies": {k: masked(v) if isinstance(v, dict) else v
                                                               for k, v in replies.items()}}
    if args.repair:
        status = replies["a2dp_getStatus"]
        if status.get("returnValue"):
            report["repair"] = "skipped: link is already up"
        else:
            connect = probe.luna("luna://com.webos.service.bluetooth2/a2dp/connect", {"address": bt}, t=15)
            report["repair"] = {"connect": masked(connect),
                                "link_after": probe.link_status(),
                                "note": ("131 already connected or returnValue true: check link_after"
                                         if connect.get("returnValue") or connect.get("errorCode") == 131
                                         else "connect refused or failed; link_after recorded as evidence")}
    print(json.dumps(report, indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
