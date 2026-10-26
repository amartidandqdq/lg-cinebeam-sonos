"""Minimal LG SSAP helper: python lgctl.py <uri> [json-payload]"""
import json
import pathlib
import ssl
import sys

from websockets.sync.client import connect

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
CK = (pathlib.Path(__file__).parent / "client-key.txt").read_text().strip()


def session():
    ws = connect("wss://192.168.1.2:3001/ssap/local", ssl=ctx, origin=None, open_timeout=8)
    ws.send(json.dumps({"type": "register", "id": "r", "payload": {"client-key": CK}}))
    while json.loads(ws.recv(timeout=6)).get("type") != "registered":
        pass
    return ws


def call(ws, uri, payload=None, i=[0]):
    i[0] += 1
    rid = f"q{i[0]}"
    ws.send(json.dumps({"type": "request", "id": rid, "uri": uri, "payload": payload or {}}))
    while True:
        m = json.loads(ws.recv(timeout=8))
        if m.get("id") == rid:
            return m.get("payload", m)


def output(ws):
    return call(ws, "ssap://audio/getStatus")["volumeStatus"]["soundOutput"]


if __name__ == "__main__":
    ws = session()
    print(json.dumps(call(ws, sys.argv[1], json.loads(sys.argv[2]) if len(sys.argv) > 2 else None), ensure_ascii=False)[:3000])
