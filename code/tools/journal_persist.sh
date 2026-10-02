#!/bin/bash
# Smart cane - make the journal survive a power cut. Run ON THE PI.
#
# Step 1.2 G7: /var/log is a log2ram tmpfs. The "persistent" journal lived in
# RAM and reached the SD card only once a day or at clean shutdown, so a
# brownout lost exactly the logs needed to explain it. For the development
# phases this switches log2ram off and lets journald write to the card,
# syncing every 15 s. CRIT and worse are written at once. The product's log
# strategy (read-only root, overlayfs) is decided in Step 5.9.
#
#   sudo bash journal_persist.sh apply    # then reboot
#   sudo bash journal_persist.sh verify   # after the reboot
#   sudo bash journal_persist.sh mark     # write markers, then cut the power
#   sudo bash journal_persist.sh check    # after power returns: find the markers
#   sudo bash journal_persist.sh undo     # back to log2ram, then reboot

set -u
CONF=/etc/systemd/journald.conf.d/50-smartcane-persistent.conf
MARKS=/var/lib/smartcane-journal-marks

case "${1:-}" in
apply)
  mkdir -p "$(dirname $CONF)"
  [ -f "$CONF" ] && cp "$CONF" "$CONF.bak-$(date +%F)"
  cat > "$CONF" <<'EOF'
# Phase 1 Step 1.2 (G7): logs must survive a power cut so under-voltage
# resets can be diagnosed. Was Storage=volatile in journald.conf, then
# persistent-but-in-RAM under log2ram. See code/tools/journal_persist.sh.
[Journal]
Storage=persistent
SystemMaxUse=200M
SyncIntervalSec=15s
EOF
  systemctl disable log2ram.service log2ram-daily.timer 2>&1
  echo "applied. Reboot now: log2ram syncs RAM to the card on the way down,"
  echo "and /var/log is on the SD card after the reboot."
  ;;
verify)
  fail=0
  fs=$(findmnt -n -o FSTYPE /var/log)
  if [ -z "$fs" ] || [ "$fs" = "ext4" ]; then echo "OK   /var/log on the SD card"
  else echo "FAIL /var/log is $fs"; fail=1; fi
  systemctl is-enabled log2ram.service >/dev/null 2>&1 && { echo "FAIL log2ram still enabled"; fail=1; } \
    || echo "OK   log2ram disabled"
  if [ -d /var/log/journal ] && journalctl --header -q 2>/dev/null | grep -q "/var/log/journal"; then
    echo "OK   journal files in /var/log/journal"
  else echo "FAIL journal not writing to /var/log/journal"; fail=1; fi
  systemd-analyze cat-config systemd/journald.conf | grep -E "^(Storage|SyncIntervalSec|SystemMaxUse)="
  journalctl --list-boots --no-pager | tail -3
  exit $fail
  ;;
mark)
  id=$(date +%s)
  mkdir -p "$MARKS"
  logger -p user.notice "SMARTCANE-MARK-NOTICE-$id"
  logger -p user.crit "SMARTCANE-MARK-CRIT-$id"
  echo "$id" > "$MARKS/last"
  sync -f "$MARKS/last"
  echo "markers $id written. Wait 20 s (one sync interval plus margin),"
  echo "then cut the power WITHOUT shutting down."
  ;;
check)
  id=$(cat "$MARKS/last" 2>/dev/null) || { echo "no marker id stored"; exit 1; }
  fail=0
  for kind in NOTICE CRIT; do
    if journalctl -b -1 --no-pager | grep -q "SMARTCANE-MARK-$kind-$id"; then
      echo "OK   $kind marker $id is in the previous boot's journal"
    else echo "FAIL $kind marker $id lost"; fail=1; fi
  done
  echo "last lines before the cut:"
  journalctl -b -1 --no-pager -n 5
  exit $fail
  ;;
undo)
  rm -f "$CONF"
  systemctl enable log2ram.service log2ram-daily.timer 2>&1
  echo "undone. Reboot to bring log2ram back."
  ;;
*)
  sed -n '2,16p' "$0"; exit 2 ;;
esac
