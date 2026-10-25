import sys
import time

import lgctl
import sonosctl

ws = lgctl.session()
for target in sys.argv[1:]:
    r = lgctl.call(ws, "ssap://com.webos.service.apiadapter/audio/changeSoundOutput", {"output": target})
    print(target, r.get("returnValue"), r.get("errorText", ""))
    for k in range(9):
        time.sleep(2)
        print(f"  +{2 * (k + 1)}s proj={lgctl.output(ws)} sonos={sonosctl.state()}")
