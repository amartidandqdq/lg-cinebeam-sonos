#!/bin/sh
# 01 - RECON (lecture seule). Rien ne change sur le projecteur.
# Root + SSH :   ssh root@IP 'sh -s' < scripts/recon.sh > backup/avant.txt
# Sans root   :  les commandes luna passent aussi via ares-shell (dev mode).
export PATH=/usr/bin:/usr/sbin:/bin:/sbin:$PATH

say() { echo; echo "===== $* ====="; }

say "Identite"
uname -a
cat /proc/version 2>/dev/null
cat /etc/version 2>/dev/null
echo "uptime: $(cut -d' ' -f1 /proc/uptime 2>/dev/null) s"

say "Modele / firmware / OTAID"
for f in /proc/deviceinfo/*; do echo "$f: $(cat "$f" 2>/dev/null)"; done
luna() { luna-send -n 1 -w 3000 -f "luna://$1" "${2:-{}}" </dev/null 2>&1; }
luna com.webos.service.tv/getTVInfo
luna com.webos.service.support/getSystemInfo

say "systemd ?"
command -v systemctl || echo "PAS de systemd"

say "Services pub/telemetrie"
ps 2>/dev/null | grep -iE 'acr2|admanager|nudge|contentminer|sportsalarm|adoverlay|remotelogger|service-logger' | grep -v grep

say "Applications"
ls /usr/palm/applications 2>/dev/null
luna com.webos.applicationManager/listApps | head -60

say "hosts"
cat /etc/hosts

echo; echo "===== FIN ====="