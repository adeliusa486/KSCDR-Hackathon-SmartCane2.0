#!/bin/bash
# Flash fw 2026-10-08c: every buzz at full power, longer pulses. Run ON THE PI, detached.
set -u
OUT=$HOME/flash_2026-10-08c
mkdir -p "$OUT"; exec >> "$OUT/log.txt" 2>&1
B=$HOME/smartcane/esp32/build_2026-10-08b
NEW=$HOME/smartcane/esp32/build_2026-10-08c/cane_safety.ino.bin
ESP="$HOME/.arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool --chip esp32 --port /dev/ttyUSB0 --baud 460800 --after no-reset"
log() { echo "=== $(date +%T) $*"; }
log "1. running app == known-good build (rollback copy)?"
if ! $ESP verify-flash 0x10000 $B/cane_safety.ino.bin; then log "ABORT: running firmware is not the known-good build, nothing written"; echo RESULT=ABORT; exit 1; fi
log "2. write new app"
if ! $ESP write-flash 0x10000 "$NEW"; then
  log "write failed, restoring known-good app"; $ESP write-flash 0x10000 $B/cane_safety.ino.bin; $ESP verify-flash 0x10000 $B/cane_safety.ino.bin && echo RESULT=ROLLED_BACK || echo RESULT=ROLLBACK_FAILED; exit 1; fi
log "3. verify new app on chip"
if ! $ESP verify-flash 0x10000 "$NEW"; then
  log "verify failed, restoring known-good app"; $ESP write-flash 0x10000 $B/cane_safety.ino.bin; $ESP verify-flash 0x10000 $B/cane_safety.ino.bin && echo RESULT=ROLLED_BACK || echo RESULT=ROLLBACK_FAILED; exit 1; fi
log "4. reset, boot report, sensor IDs and status"
python3 $HOME/smartcane/tools/esp32_capture.py --reset --seconds 12 --send S --send P --send T --out "$OUT/boot"
echo RESULT=OK
