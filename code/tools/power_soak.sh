#!/bin/bash
# Smart cane - power soak test for Phase 1 Step 1.2, run ON THE PI.
#
# Runs a sequence of load phases and logs, once a second, everything Step 1.2
# must measure: EXT5V input voltage, the firmware's throttle/under-voltage
# flags, SoC temperature and clock, PMIC rail power, load, Wi-Fi reachability
# and vision liveness (CPU time used by detect.py). A second
# logger follows the kernel log and records every under-voltage, Hailo, USB,
# MMC and filesystem event with its time.
#
# Phases (each "name:seconds"):
#   idle      smartcane.service stopped, nothing running
#   service   smartcane.service running (camera + Hailo + ESP32 + audio)
#   bench     service stopped, continuous Hailo benchmark (max AI load)
#   bench_cpu bench plus all 4 CPU cores busy
#   svc_cpu   service running plus all 4 CPU cores busy (worst realistic case)
#
#   bash power_soak.sh OUTDIR "idle:120 service:180 bench:120" [--abort-on-uv]
#
# --abort-on-uv stops the load at the first NEW under-voltage event, then
# idles for 60 s and restores the service. Use it on a supply that is known
# to sag, so a test cannot push the Hailo into the 2 Oct failure state.
#
# Run detached, because SSH has dropped on this Pi under load:
#   nohup bash power_soak.sh ~/soak/<name> "<phases>" > /dev/null 2>&1 &
# Done when terminal_output.txt ends with "SOAK DONE". The service is always
# restarted from an EXIT trap, so a failed run cannot leave the cane off.

set -u
OUT=${1:?usage: power_soak.sh OUTDIR "phase:sec ..." [--abort-on-uv]}
PHASES=${2:?usage: power_soak.sh OUTDIR "phase:sec ..." [--abort-on-uv]}
ABORT_UV=0; [ "${3:-}" = "--abort-on-uv" ] && ABORT_UV=1
HEF=/usr/share/hailo-models/yolov8s_h8l.hef
GW=$(ip route | awk '/^default/ {print $3; exit}')
mkdir -p "$OUT"
exec >> "$OUT/terminal_output.txt" 2>&1

log() { echo "=== $(date +%T.%3N)  $*"; }
uv()  { sudo journalctl -k -b --no-pager | grep -c "Undervoltage detected"; }
svc() { systemctl --user "$1" smartcane.service; }
echo "$(date +%T) start" > "$OUT/phase_now"

# --- kernel event logger -----------------------------------------------------
sudo journalctl -k -f -n 0 --no-pager -o short-precise \
  | grep --line-buffered -v "Modules linked in" \
  | grep --line-buffered -iE "undervoltage|voltage normalised|hailo.*(disconnect|error|fail|timeout)|usb .*disconnect|new .*usb device|mmc|ext4-fs (error|warning)|i/o error|cp210x ttyusb|throttl|out of memory" \
  > "$OUT/kernel_events.log" &
KLOG=$!

# --- 1 s sampler -------------------------------------------------------------
# pmic_w: sum of V x I over the PMIC rails. It covers the SoC, RAM and on-board
# rails only, not USB devices or the Hailo HAT, so it is a lower bound, not the
# input power. Step 1.3 measures the real input with a meter.
# detect_cpu: CPU seconds detect.py used since the last sample. speak_detect.py
# consumes detect.py's reports through a pipe and does not log them, so this is
# the liveness signal. In the 2 Oct failure detect.py hung inside hailo.run, so
# a running service with detect_cpu near 0 means vision is stuck. "-" = not running.
CLK=$(getconf CLK_TCK)
cpu_ticks() { local p; p=$(pgrep -f "smartcane/[d]etect.py" | head -1); [ -n "$p" ] && awk '{print $14+$15}' /proc/$p/stat 2>/dev/null; }
(
  echo "time,mono_s,phase,temp_c,ext5v_v,throttled,arm_hz,pmic_w,load1,gw_ping_ms,detect_cpu"
  prev=""
  while true; do
    adc=$(vcgencmd pmic_read_adc)
    ext=$(echo "$adc" | awk -F= '/EXT5V_V/ {sub("V","",$2); print $2}')
    pw=$(echo "$adc" | awk -F'[=()]' '
      / current\(/ {sub("A","",$4); n=$1; sub(/_A.*/,"",n); gsub(/ /,"",n); a[n]=$4}
      / volt\(/    {sub("V","",$4); n=$1; sub(/_V.*/,"",n); gsub(/ /,"",n); v[n]=$4}
      END {s=0; for (k in a) if (k in v) s+=a[k]*v[k]; printf "%.3f", s}')
    ping_ms=$(ping -c1 -W1 "$GW" 2>/dev/null | awk -F'time=' '/time=/ {split($2,x," "); print x[1]}')
    now_t=$(cpu_ticks); vis="-"
    if [ -n "$now_t" ] && [ -n "$prev" ] && [ "$now_t" -ge "$prev" ]; then vis=$(awk -v a="$now_t" -v b="$prev" -v c="$CLK" 'BEGIN {printf "%.2f", (a-b)/c}'); fi
    prev=$now_t
    echo "$(date +%T),$(cut -d' ' -f1 /proc/uptime),$(cut -d' ' -f2 "$OUT/phase_now"),$(vcgencmd measure_temp | grep -oE '[0-9.]+'),$ext,$(vcgencmd get_throttled | cut -d= -f2),$(vcgencmd measure_clock arm | cut -d= -f2),$pw,$(cut -d' ' -f1 /proc/loadavg),${ping_ms:-LOST},$vis"
    sleep 1
  done
) > "$OUT/soak_log.csv" &
SAMPLER=$!

LOADS=()
stop_load() {
  for p in "${LOADS[@]:-}"; do [ -n "$p" ] && kill "$p" 2>/dev/null; done
  pkill -f "[h]ailortcli benchmark" 2>/dev/null
  LOADS=()
}
cpu_burn() { for i in 1 2 3 4; do (while :; do :; done) & LOADS+=($!); done; }
bench()    { (while :; do timeout 600 hailortcli benchmark -t 300 $HEF > /dev/null 2>&1 || sleep 2; done) & LOADS+=($!); }

RESULT=PASS
finish() {
  stop_load
  log "restore: start smartcane.service"
  svc start; sleep 30
  systemctl --user show smartcane.service -p ActiveState -p NRestarts
  log "end: under-voltage events this boot $(uv), $(vcgencmd get_throttled)"
  kill $SAMPLER $KLOG 2>/dev/null
  sudo pkill -f "[j]ournalctl -k -f -n 0" 2>/dev/null
  log "RESULT $RESULT"
  log "SOAK DONE"
}
trap finish EXIT

log "SOAK START  boot $(uptime -s), supply max_current $(od -An -tu4 --endian=big /proc/device-tree/chosen/power/max_current | tr -d ' ') mA, usb_max_current_enable $(vcgencmd get_config usb_max_current_enable | cut -d= -f2), under-voltage events $(uv), $(vcgencmd get_throttled), abort_on_uv=$ABORT_UV"
UV0=$(uv)

for ph in $PHASES; do
  name=${ph%%:*}; secs=${ph##*:}
  echo "$(date +%T) $name" > "$OUT/phase_now"
  log "phase $name for $secs s"
  case $name in
    idle)      svc stop ;;
    service)   svc start ;;
    bench)     svc stop; sleep 2; bench ;;
    bench_cpu) svc stop; sleep 2; bench; cpu_burn ;;
    svc_cpu)   svc start; cpu_burn ;;
    *) log "unknown phase $name"; RESULT=ERROR; exit 1 ;;
  esac
  end=$(( $(date +%s) + secs ))
  while [ "$(date +%s)" -lt "$end" ]; do
    sleep 2
    if [ "$(uv)" -gt "$UV0" ]; then
      log "UNDER-VOLTAGE during phase $name ($(uv) events this boot, was $UV0)"
      RESULT=FAIL
      if [ $ABORT_UV = 1 ]; then
        stop_load; svc stop
        echo "$(date +%T) aborted_idle" > "$OUT/phase_now"
        log "aborted: load stopped, idling 60 s"
        sleep 60
        exit 0
      fi
      UV0=$(uv)
    fi
  done
  stop_load
  log "phase $name done, under-voltage events $(uv), $(vcgencmd get_throttled)"
done
