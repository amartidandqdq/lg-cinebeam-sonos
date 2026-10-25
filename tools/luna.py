"""python luna.py <service/method> '<json params>' : appel luna:// via createAlert/closeAlert"""
import json
import sys

import lgctl

ws = lgctl.session()
uri = "luna://" + sys.argv[1]
params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
created = lgctl.call(ws, "ssap://system.notifications/createAlert", {
    "message": " ", "buttons": [{"label": "", "onClick": uri, "params": params}],
    "onclose": {"uri": uri, "params": params}, "onfail": {"uri": uri, "params": params}})
print("createAlert:", created)
if created.get("alertId"):
    print("closeAlert:", lgctl.call(ws, "ssap://system.notifications/closeAlert", {"alertId": created["alertId"]}))
