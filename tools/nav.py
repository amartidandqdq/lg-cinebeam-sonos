"""python nav.py [launch:<appId>[:<json params>]] KEY KEY ... -> keys then screenshot to /tmp/cap.jpg"""
import json
import ssl
import sys
import time
import urllib.request

from websockets.sync.client import connect

import lgctl

ws = lgctl.session()
sp = connect(lgctl.call(ws, "ssap://com.webos.service.networkinput/getPointerInputSocket")["socketPath"],
             ssl=lgctl.ctx, origin=None, open_timeout=8)
for a in sys.argv[1:]:
    if a.startswith("launch:"):
        _, app, *p = a.split(":", 2)
        print(lgctl.call(ws, "ssap://system.launcher/launch", {"id": app, **({"params": json.loads(p[0])} if p else {})}))
        time.sleep(3)
    elif a.startswith("wait"):
        time.sleep(float(a[4:] or 2))
    else:
        sp.send(f"type:button\nname:{a}\n\n")
        time.sleep(1.2)
time.sleep(1)
uri = lgctl.call(ws, "ssap://tv/executeOneShot")["imageUri"]
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
open("/tmp/cap.jpg", "wb").write(urllib.request.urlopen(uri, context=ctx, timeout=10).read())
print("out:", lgctl.output(ws), "fg:", lgctl.call(ws, "ssap://com.webos.applicationManager/getForegroundAppInfo").get("appId"))
