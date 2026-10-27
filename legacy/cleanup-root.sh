#!/bin/sh
# 03 - CLEANUP (necessite root + SSH). Chaque action est journalisee dans
# /media/developer/cleanup/undo.log pour que restore-root.sh puisse tout annuler.
# Principe cleanyourtv : rien n'est supprime, tout est en RAM ou marque.
export PATH=/usr/bin:/usr/sbin:/bin:/sbin:$PATH
D=/media/developer/cleanup
mkdir -p "$D" 2>/dev/null
LOG="$D/undo.log"
log() { echo "$*" | tee -a "$LOG"; }

# 1. services pub/telemetrie (systemd ; absents en webOS <= 4)
for s in remotelogger service-logger contentminer nudge; do
  if systemctl list-unit-files 2>/dev/null | grep -q "^$s"; then
    systemctl stop "$s.service" >/dev/null 2>&1
    log "service:$s"
  fi
done

# 2. services luna lances a la demande : stub inerte monte dessus
printf '#!/bin/sh\nexit 0\n' > "$D/stub-noop"
chmod +x "$D/stub-noop" 2>/dev/null
for b in acr2 admanager sportsalarm adoverlay-service; do
  [ -e "/usr/sbin/$b" ] || continue
  if ! grep -q " /usr/sbin/$b " /proc/mounts 2>/dev/null; then
    mount --bind "$D/stub-noop" "/usr/sbin/$b" && log "stub:$b"
  fi
  pkill -9 -f "^/usr/sbin/$b" >/dev/null 2>&1
done

echo "Journal : $LOG"
# 3. domaines pub -> 127.0.0.1 : marques "# lg-cleanup" (retires par restore)
HOSTS='eic.ads.lgtvcommon.com nl.ad.lgsmartad.com nl.info.lgsmartad.com'
if grep -q "# lg-cleanup" /etc/hosts 2>/dev/null; then
  echo "hosts: deja bloque"
else
  if [ -w /etc/hosts ] && printf '127.0.0.1 %s # lg-cleanup\n::1 %s # lg-cleanup\n' "$HOSTS" "$HOSTS" >> /etc/hosts 2>/dev/null; then
    log "hosts:ecrit"
  else
    cp /etc/hosts /tmp/hosts.lgcleanup
    printf '127.0.0.1 %s # lg-cleanup\n'  "$HOSTS" >> /tmp/hosts.lgcleanup
    mount --bind /tmp/hosts.lgcleanup /etc/hosts && touch /tmp/hosts.lgcleanup.mounted
    log "hosts:ram"
  fi
fi
