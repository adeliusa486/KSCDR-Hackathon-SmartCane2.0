#!/bin/bash
# Smart cane - prove which firmware the ESP32 runs, back it up, prove the
# backup restores. Run ON THE PI.
#
#   nohup bash esp32_backup.sh OUTDIR [BAUD] > /dev/null 2>&1 &
#
# Why not just dump the whole 4 MB flash: on 2 Oct 2026 a full read-flash
# failed twice at exactly the same address (0x2A000, 4.1%), at both 921600 and
# 460800 baud, each time with "cp210x ttyUSB0: failed set request 0x12 status:
# -110" in the kernel log. Same address at two speeds means it depends on the
# data, not on timing, and the bulk read path ESP32 -> Pi stalls the CP2102.
# Writing works (the firmware was flashed from this Pi). So:
#
#   1. verify-flash: the chip hashes each region itself (MD5) and compares
#      with the build artifacts. Proves the running firmware IS the build,
#      with no bulk read.
#   2. read 0x0-0x10000 twice (bootloader, partition table, NVS with the saved
#      sensor roles, otadata). 64 KB, well below the failing address. The two
#      reads must match.
#   3. ROLLBACK TEST: write that 64 KB + the app back, verify-flash again.
#
# Any failure aborts before the write. The EXIT trap always resets the ESP32
# into normal mode, times its boot and restarts smartcane.service.

set -u
OUT=${1:?usage: esp32_backup.sh OUTDIR [BAUD]}
BAUD=${2:-460800}
SC=/home/pi/smartcane
T=$SC/tools
B=$SC/esp32/build                       # artifacts of the 19:22 flash
ESPTOOL=$HOME/.arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool
ESP="$ESPTOOL --chip esp32 --port /dev/ttyUSB0 --baud $BAUD --after no-reset"
# Addresses from the build's flash_args.
IMAGES="0x1000 $B/cane_safety.ino.bootloader.bin 0x8000 $B/cane_safety.ino.partitions.bin 0xe000 $B/boot_app0_flashed.bin 0x10000 $B/cane_safety.ino.bin"
mkdir -p "$OUT"
exec >> "$OUT/terminal_output.txt" 2>&1

log()  { echo; echo "=== $(date +%T.%3N)  $*"; }
fail() { log "ABORT: $*"; exit 1; }

finish() {
  log "reset ESP32 into normal mode, time the boot"
  python3 $T/esp32_capture.py --reset --seconds 12 --send T --send S --out "$OUT/esp32_boot"
  log "start smartcane.service"
  systemctl --user start smartcane.service
  log "DONE"
}
trap finish EXIT

log "stop smartcane.service (frees the port)"
systemctl --user stop smartcane.service
sleep 1

log "1. verify-flash: running firmware vs build artifacts (on-chip MD5)"
$ESP verify-flash $IMAGES || fail "running firmware differs from the build artifacts"
log "1. FIRMWARE IDENTITY VERIFIED"

log "2. read 0x0-0x10000 twice"
$ESP read-flash 0 0x10000 "$OUT/esp32_low64k.bin" || fail "read 1 failed"
$ESP read-flash 0 0x10000 "$OUT/esp32_low64k_read2.bin" || fail "read 2 failed"
cmp "$OUT/esp32_low64k.bin" "$OUT/esp32_low64k_read2.bin" || fail "reads differ"
cp $B/cane_safety.ino.bin $B/cane_safety.ino.bootloader.bin \
   $B/cane_safety.ino.partitions.bin $B/boot_app0_flashed.bin "$OUT/"
log "2. low 64 KB stable, backup set copied"

log "3. ROLLBACK TEST: write low 64 KB + app back"
$ESP write-flash 0x0 "$OUT/esp32_low64k.bin" 0x10000 "$OUT/cane_safety.ino.bin" \
  || fail "write failed - re-flash: esptool write-flash 0x0 esp32_low64k.bin 0x10000 cane_safety.ino.bin"
# Two calls: the low 64 KB overlaps the bootloader/partition/otadata images.
$ESP verify-flash 0x0 "$OUT/esp32_low64k.bin" || fail "low 64 KB after restore differs from backup"
$ESP verify-flash $IMAGES || fail "firmware after restore differs from the build"
log "3. ROLLBACK TEST PASSED"
sha256sum "$OUT"/*.bin
