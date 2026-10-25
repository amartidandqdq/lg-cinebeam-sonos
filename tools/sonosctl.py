"""Minimal Sonos UPnP helper (stdlib only)."""
import re
import sys
import time
import urllib.request

IP = "192.168.1.139"
RID = "RINCON_aabbcc0000a901400"
AV = "/MediaRenderer/AVTransport/Control"


def soap(path, svc, action, args=""):
    body = ('<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
            f'<u:{action} xmlns:u="urn:schemas-upnp-org:service:{svc}:1">{args}</u:{action}>'
            '</s:Body></s:Envelope>')
    req = urllib.request.Request(f"http://{IP}:1400{path}", body.encode(), {
        "Content-Type": 'text/xml; charset="utf-8"',
        "SOAPACTION": f'"urn:schemas-upnp-org:service:{svc}:1#{action}"'})
    try:
        return urllib.request.urlopen(req, timeout=5).read().decode()
    except urllib.error.HTTPError as e:
        return f"ERR {e.code} {e.read()[:300]!r}"


def field(xml, tag):
    m = re.search(f"<{tag}>(.*?)</{tag}>", xml, re.S)
    return m.group(1) if m else None


def state():
    m = soap(AV, "AVTransport", "GetMediaInfo", "<InstanceID>0</InstanceID>")
    t = soap(AV, "AVTransport", "GetTransportInfo", "<InstanceID>0</InstanceID>")
    z = soap("/DeviceProperties/Control", "DeviceProperties", "GetZoneInfo")
    return field(m, "CurrentURI"), field(t, "CurrentTransportState"), field(z, "HTAudioIn")


def to_tv():
    print(soap(AV, "AVTransport", "SetAVTransportURI",
               f"<InstanceID>0</InstanceID><CurrentURI>x-sonos-htastream:{RID}:spdif</CurrentURI>"
               "<CurrentURIMetaData></CurrentURIMetaData>")[-120:])
    print(soap(AV, "AVTransport", "Play", "<InstanceID>0</InstanceID><Speed>1</Speed>")[-120:])


if __name__ == "__main__":
    if "tv" in sys.argv[1:]:
        to_tv()
    for _ in range(int(sys.argv[-1]) if sys.argv[-1].isdigit() else 1):
        print(*state())
        time.sleep(2)
