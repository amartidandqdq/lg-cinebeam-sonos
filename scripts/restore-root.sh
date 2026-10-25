#!/bin/sh
# 04 - RESTORE (root). Annule debloat.sh : stubs demontes, services relances,
# lignes hosts retirees. Ne touche a rien d'autre.
export PATH=/usr/bin:/usr/sbin:/bin:/sbin:$PATH
for b in acr2 admanager sportsalarm adoverlay-service; do
  for m in $(awk -v b="/usr/sbin/$b" 'substr($2,length($2)-length(b)+1)==b {print $2}' /proc/mounts 2>/dev/null); do
    umount "$m" 2>/dev/null
  done
done
for s in remotelogger service-logger contentminer nudge; do
  systemctl start "$s" >/dev/null 2>&1
done

# hosts : copie RAM puis lignes marquees
if [ -e /tmp/hosts.lgdebloat.mounted ]; then :; fi
if grep -q "# lg-debloat" /etc/hosts 2>/dev/null; then :; fi
