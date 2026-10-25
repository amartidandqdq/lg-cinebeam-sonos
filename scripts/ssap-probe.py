"""Interrogation SSAP (WebSocket luna) d'un appareil webOS — lecture seule."""
import json
import socket
import base64
import sys
import time

# evite les crashes d'encodage de la console Windows (cp1252)
sys.stdout.reconfigure(errors="replace")

HOST = "192.168.1.2"
PORT = 3000


def ws_handshake(sock):
    key = base64.b64encode(b"0123456789abcdef").decode()
    req = (
        "GET /ssap/local HTTP/1.1\r\n"
        f"Host: {HOST}:{PORT}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n"
        "Origin: http://127.0.0.1\r\n\r\n"
    )
    sock.sendall(req.encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("handshake echoue")
        resp += chunk
    return resp.split(b"\r\n\r\n", 1)


def ws_send(sock, obj):
    payload = json.dumps(obj).encode()
    mask = b"\x00\x00\x00\x00"
    header = b"\x81"
    n = len(payload)
    if n < 126:
        header += bytes([0x80 | n])
    elif n < 65536:
        header += bytes([0x80 | 126]) + n.to_bytes(2, "big")
    else:
        header += bytes([0x80 | 127]) + n.to_bytes(8, "big")
    sock.sendall(header + mask + payload)


def ws_recv(sock, timeout=3.0):
    sock.settimeout(timeout)
    try:
        h = sock.recv(2)
        if not h or len(h) < 2:
            return None
        op = h[0] & 0x0F
        n = h[1] & 0x7F
        if n == 126:
            n = int.from_bytes(sock.recv(2), "big")
        elif n == 127:
            n = int.from_bytes(sock.recv(8), "big")
        data = b""
        while len(data) < n:
            chunk = sock.recv(n - len(data))
            if not chunk:
                break
            data += chunk
        if op == 0x9:  # ping -> pong
            sock.sendall(b"\x8a\x00")
            return None
        if op in (0x2, 0x8):
            return None
        return data.decode("utf-8", "replace")
    except socket.timeout:
        return None


def main():
    s = socket.create_connection((HOST, PORT), timeout=5)
    print(ws_handshake(s))
    cmds = [
        ("com.webos.service.tv/getTVInfo", {}),
        ("com.webos.service.support/getSystemInfo", {}),
        ("com.webos.service.system/getSystemInfo", {}),
        ("com.webos.applicationManager/listApps", {}),
        ("com.webos.settingsservice/getSystemSettings", {"category": "general"}),
        ("com.webos.service.ads/getAdState", {}),
    ]
    for i, (uri, payload) in enumerate(cmds, 1):
        ws_send(s, {
            "type": "luna",
            "id": f"probe{i}",
            "uri": f"luna://{uri}" if not uri.startswith("luna://") else uri,
            "payload": payload,
        })
        got = None
        for _ in range(6):
            got = ws_recv(s, timeout=2.5)
            if got:
                break
        print(f"--- {uri}")
        print((got or "PAS DE REPONSE")[:700].encode("ascii", "replace").decode())
    s.close()


if __name__ == "__main__":
    main()