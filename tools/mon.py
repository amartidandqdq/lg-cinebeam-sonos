import time

import lgctl
import sonosctl

ws = lgctl.session()
for k in range(100):
    out = lgctl.output(ws)
    print(f"+{3 * k}s proj={out} sonos={sonosctl.state()[0][:40]}", flush=True)
    if out.startswith("bt"):
        time.sleep(15)
        print("after 15s:", lgctl.output(ws), sonosctl.state()[0][:60], flush=True)
        break
    time.sleep(3)
