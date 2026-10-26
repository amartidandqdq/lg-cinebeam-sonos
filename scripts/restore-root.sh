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

# hosts : demonter la copie RAM (bind mount) puis retirer les lignes marquees
HOSTS_FILE=${HOSTS_FILE:-/etc/hosts}
if [ -e /tmp/hosts.lgdebloat.mounted ]; then
  umount "$HOSTS_FILE" 2>/dev/null && rm -f /tmp/hosts.lgdebloat /tmp/hosts.lgdebloat.mounted
fi
if grep -q "# lg-debloat" "$HOSTS_FILE" 2>/dev/null; then
  # cat > plutot que mv : conserve l'inode (le fichier peut etre un point de montage)
  grep -v "# lg-debloat" "$HOSTS_FILE" > "/tmp/hosts.restore.$$" && cat "/tmp/hosts.restore.$$" > "$HOSTS_FILE"
  rm -f "/tmp/hosts.restore.$$"
fi
