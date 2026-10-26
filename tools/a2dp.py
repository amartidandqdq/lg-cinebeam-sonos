import sys
import time

import lgctl

ws = lgctl.session()


def luna(uri, params):
    a = lgctl.call(ws, "ssap://system.notifications/createAlert", {
        "message": " ", "buttons": [{"label": "", "onClick": "luna://" + uri, "params": params}],
        "onclose": {"uri": "luna://" + uri, "params": params}, "onfail": {"uri": "luna://" + uri, "params": params}})
    lgctl.call(ws, "ssap://system.notifications/closeAlert", {"alertId": a["alertId"]})


print("start:", lgctl.output(ws))
for addr in sys.argv[1:]:
    luna("com.webos.service.bluetooth2/a2dp/connect", {"address": addr.lower()})
    time.sleep(6)
    lgctl.call(ws, "ssap://com.webos.service.apiadapter/audio/changeSoundOutput", {"output": "bt_soundbar"})
    outs = []
    for _ in range(6):
        time.sleep(2)
        outs.append(lgctl.output(ws))
    print(addr, outs, flush=True)
    if outs[-1].startswith("bt_"):
        print("CONNECTED with", addr)
        break
