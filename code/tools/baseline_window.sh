#!/bin/bash
# Smart cane - Phase 1 Step 1.1 measurement window, run ON THE PI.
#
# Stops smartcane.service, measures everything that needs exclusive access to
# the camera, the Hailo or the ESP32 port, then starts the service again. The
# service restart is in an EXIT trap, so a failed measurement cannot leave the
# cane switched off.
#
# Run detached, because SSH has dropped on this Pi under load:
#   nohup bash baseline_window.sh ~/baseline_run/<ts> > /dev/null 2>&1 &
#
# The ESP32 steps reset the ESP32 (chip info needs the ROM bootloader), then
# reset it back into normal mode and time the boot. The flash backup and its
# rollback test are a separate, guarded script: esp32_backup.sh.

set -u
OUT=${1:?usage: baseline_window.sh OUTDIR}
SC=/home/pi/smartcane
T=$SC/tools
HEF=/usr/share/hailo-models/yolov8s_h8l.hef
ESPTOOL=$HOME/.arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool
ESP="$ESPTOOL --chip esp32 --port /dev/ttyUSB0 --baud 921600"
mkdir -p "$OUT"
exec >> "$OUT/terminal_output.txt" 2>&1

log() { echo; echo "=== $(date +%T.%3N)  $*"; }
uv()  { sudo journalctl -k -b --no-pager | grep -c "Undervoltage detected"; }

# 1 Hz power/thermal log for the whole window.
(
  echo "time,temp_c,ext5v_v,throttled,arm_hz"
  while true; do
    echo "$(date +%T),$(vcgencmd measure_temp | grep -oE '[0-9.]+'),$(vcgencmd pmic_read_adc EXT5V_V | grep -oE '=[0-9.]+' | tr -d =),$(vcgencmd get_throttled | cut -d= -f2),$(vcgencmd measure_clock arm | cut -d= -f2)"
    sleep 1
  done
) > "$OUT/power_thermal_log.csv" &
LOGGER=$!

finish() {
  log "start smartcane.service"
  systemctl --user start smartcane.service
  sleep 40
  systemctl --user show smartcane.service -p ActiveState -p SubState -p NRestarts -p ExecMainStartTimestamp
  sudo journalctl --no-pager --since "-45s" _SYSTEMD_USER_UNIT=smartcane.service | tail -25
  log "under-voltage events this boot at end: $(uv)   throttled: $(vcgencmd get_throttled)"
  kill $LOGGER 2>/dev/null
  log "WINDOW DONE"
}
trap finish EXIT

log "WINDOW START  under-voltage events so far: $(uv)   $(vcgencmd get_throttled)"
log "stop smartcane.service"
systemctl --user stop smartcane.service
sleep 2

log "ESP32: 60 s stream, no reset, commands T and S"
python3 $T/esp32_capture.py --seconds 60 --send T --send S --out "$OUT/esp32_stream_60s"

log "camera: list"
rpicam-hello --list-cameras
log "camera: probe with detect.py settings (fps 15, ev 0.7)"
python3 $T/camera_probe.py --frames 90 --out "$OUT/camera_fps15"

log "hailo: identify"
hailortcli fw-control identify
log "hailo: benchmark 15 s"
hailortcli benchmark -t 15 --csv "$OUT/hailo_benchmark.csv" $HEF
log "under-voltage after benchmark: $(uv)"

log "vision loop 30 s, service arguments (fps 15)"
timeout -s INT 30 python3 -u $SC/detect.py --interval 0.3 --conf 0.25 --fps 15 --ev 0.7 --all-classes > "$OUT/detect_fps15_30s.txt" 2>&1
log "vision loop 30 s, fps 30"
timeout -s INT 30 python3 -u $SC/detect.py --interval 0.3 --conf 0.25 --fps 30 --ev 0.7 --all-classes > "$OUT/detect_fps30_30s.txt" 2>&1
log "under-voltage after vision runs: $(uv)"

# The ESP32 flash backup and rollback test live in esp32_backup.sh, NOT here.
# The first version of this script dumped and wrote the flash inline with no
# checks between the steps. On 2 Oct 2026 the 921600-baud read failed at 4%
# and the write step still ran, against a dump file that did not exist. esptool
# rejected it, so nothing was written, but a partial file would have been
# flashed. Never write ESP32 flash without the guards in esp32_backup.sh.
log "ESP32: chip info"
$ESP --after no-reset chip-id
$ESP --after no-reset flash-id

log "ESP32: reset, time the boot, then T and S"
python3 $T/esp32_capture.py --reset --seconds 12 --send T --send S --out "$OUT/esp32_boot"
