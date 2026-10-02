#!/bin/bash
# Smart cane - Hailo and vision re-measure, run ON THE PI.
#
# The vision half of baseline_window.sh, without the ESP32 steps. Used to
# re-measure after a power cycle (Phase 1 Step 1.1 close-out) and reusable
# after any change that could affect the NPU or the camera.
#
# Stops smartcane.service, runs the Hailo identify + benchmark, the camera
# probe and two 30 s vision loops, then starts the service again from an EXIT
# trap, so a failed measurement cannot leave the cane switched off.
#
# Run detached, because SSH has dropped on this Pi under load:
#   nohup bash vision_retest.sh ~/baseline_run/<name> > /dev/null 2>&1 &
# Done when terminal_output.txt ends with "RETEST DONE".

set -u
OUT=${1:?usage: vision_retest.sh OUTDIR}
SC=/home/pi/smartcane
T=$SC/tools
HEF=/usr/share/hailo-models/yolov8s_h8l.hef
mkdir -p "$OUT"
exec >> "$OUT/terminal_output.txt" 2>&1

log() { echo; echo "=== $(date +%T.%3N)  $*"; }
uv()  { sudo journalctl -k -b --no-pager | grep -c "Undervoltage detected"; }
hd()  { sudo journalctl -k -b --no-pager | grep -ci "hailo.*disconnect"; }
lines() { grep -c "fps\]" "$1"; }

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
  log "end: under-voltage events this boot $(uv), hailo disconnect lines $(hd), $(vcgencmd get_throttled)"
  kill $LOGGER 2>/dev/null
  log "RETEST DONE"
}
trap finish EXIT

log "RETEST START  boot $(uptime -s), under-voltage events $(uv), hailo disconnect lines $(hd), $(vcgencmd get_throttled)"
systemd-analyze
log "stop smartcane.service"
systemctl --user stop smartcane.service
sleep 2

log "hailo: identify"
timeout 30 hailortcli fw-control identify
log "hailo: benchmark 15 s"
timeout 90 hailortcli benchmark -t 15 --csv "$OUT/hailo_benchmark.csv" $HEF
log "under-voltage after benchmark: $(uv)"

log "camera: probe with detect.py settings (fps 15, ev 0.7)"
timeout 60 python3 $T/camera_probe.py --frames 90 --out "$OUT/camera_fps15"

log "vision loop 30 s, service arguments (fps 15)"
timeout -s INT 30 python3 -u $SC/detect.py --interval 0.3 --conf 0.25 --fps 15 --ev 0.7 --all-classes > "$OUT/detect_fps15_30s.txt" 2>&1
log "report lines fps15: $(lines "$OUT/detect_fps15_30s.txt")"
log "vision loop 30 s, fps 30"
timeout -s INT 30 python3 -u $SC/detect.py --interval 0.3 --conf 0.25 --fps 30 --ev 0.7 --all-classes > "$OUT/detect_fps30_30s.txt" 2>&1
log "report lines fps30: $(lines "$OUT/detect_fps30_30s.txt")"
log "under-voltage after vision runs: $(uv)"
