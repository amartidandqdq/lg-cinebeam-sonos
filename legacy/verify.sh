#!/bin/sh
# 02/05 - VERIFY. Instantane de l'etat : lancer avant ET apres. Ne change rien.
export PATH=/usr/bin:/usr/sbin:/bin:/sbin:$PATH

echo '===== '$(date -u)
echo '== app au premier plan'
luna-send -n 1 -w 3000 -f luna://com.webos.applicationManager/getForegroundAppInfo '{}' </dev/null 2>&1 | head -5

echo '== services pub/telemetrie actifs'
ps 2>/dev/null | grep -iE 'acr2|admanager|nudge|contentminer|sportsalarm|adoverlay|remotelogger|service-logger' | grep -v grep
echo '== stubs montes (0 = rien)'
grep -c 'cleanup/stub-noop' /proc/mounts 2>/dev/null
echo '== hosts : lignes marquees'
grep -c 'lg-cleanup' /etc/hosts 2>/dev/null
echo '===== FIN ====='
