import ssl
import time
import urllib.request

import lgctl

ws = lgctl.session()
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE


def luna(uri, params):
    a = lgctl.call(ws, "ssap://system.notifications/createAlert", {
        "message": " ", "buttons": [{"label": "", "onClick": "luna://" + uri, "params": params}],
        "onclose": {"uri": "luna://" + uri, "params": params}, "onfail": {"uri": "luna://" + uri, "params": params}})
    lgctl.call(ws, "ssap://system.notifications/closeAlert", {"alertId": a["alertId"]})


def shot(name):
    uri = lgctl.call(ws, "ssap://tv/executeOneShot")["imageUri"]
    open(f"/tmp/{name}.jpg", "wb").write(urllib.request.urlopen(uri, context=ctx, timeout=10).read())


luna("com.webos.service.bluetooth2/a2dp/disconnect", {"address": "aa:bb:cc:00:00:a9"})
time.sleep(8)
print("after disconnect:", lgctl.output(ws))
shot("p0")
luna("com.webos.service.bluetooth2/a2dp/connect", {"address": "aa:bb:cc:00:00:a9"})
for i in range(1, 5):
    time.sleep(1.5)
    shot(f"p{i}")
time.sleep(1)
lgctl.call(ws, "ssap://com.webos.service.apiadapter/audio/changeSoundOutput", {"output": "bt_soundbar"})
for i in range(5, 8):
    time.sleep(1.5)
    shot(f"p{i}")
print("final:", lgctl.output(ws))
