#!/bin/bash
# Smart cane - read-only snapshot of the Pi's state.
#
# Writes five reports into OUT (default ~/snapshots/<timestamp>):
#   system_report.txt   board, OS, boot config, power, PCIe, GPIO, I2C, serial
#   hailo_report.txt    NPU identity, driver, runtime, model in use
#   sensor_report.txt   camera, ESP32 serial device, Bluetooth, audio
#   service_report.txt  systemd units, process state, journal counts
#   versions.txt        package and Python versions, deployed file hashes
# plus dpkg_full.txt and apt_manual.txt.
#
# It changes nothing, so run it before and after every experiment and diff the
# two directories. It does NOT open /dev/ttyUSB0: the service holds that port,
# and a second reader would steal its bytes. ESP32 data comes from
# esp32_capture.py with the service stopped.
#
#   bash snapshot_pi.sh                    # -> ~/snapshots/<timestamp>
#   bash snapshot_pi.sh /path/to/out

OUT=${1:-$HOME/snapshots/$(date +%F_%H%M%S)}
SC=/home/pi/smartcane
BT_MAC=B0:38:E2:19:DC:CC
mkdir -p "$OUT"

# Run one command under a header. Never abort: a missing tool is a finding,
# not a reason to lose the rest of the snapshot.
sec() { echo; echo "### $1"; shift; "$@" 2>&1 || echo "(exit $?)"; }
sh_() { bash -c "$1"; }

svc_pid() { systemctl --user show smartcane.service -p MainPID --value; }
det_pid() { pgrep -f "smartcane/detect.py" | head -1; }

# ---------------------------------------------------------------- system
{
  echo "SYSTEM REPORT  $(date -Is)  host=$(hostname)"
  sec "uptime" uptime
  sec "model" sh_ 'tr -d "\0" < /proc/device-tree/model; echo'
  sec "os-release" cat /etc/os-release
  sec "debian_version" cat /etc/debian_version
  sec "rpi-issue (image build)" cat /etc/rpi-issue
  sec "uname" uname -a
  sec "firmware (vcgencmd version)" vcgencmd version
  sec "bootloader (rpi-eeprom-update)" sudo rpi-eeprom-update
  sec "kernel cmdline" cat /proc/cmdline
  sec "config.txt (active lines)" sh_ 'grep -vE "^\s*(#|$)" /boot/firmware/config.txt'
  sec "cmdline.txt" cat /boot/firmware/cmdline.txt
  sec "memory" free -m
  sec "disk" df -h / /boot/firmware
  sec "block devices" lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT
  sec "SD card identity" sh_ 'cd /sys/block/mmcblk0/device && for f in name manfid oemid date type; do echo "$f=$(cat $f 2>/dev/null)"; done'

  echo; echo "### POWER"
  sec "get_throttled" vcgencmd get_throttled
  sec "throttled decoded" sh_ '
    v=$(vcgencmd get_throttled | cut -d= -f2); v=$((v))
    for b in 0:"under-voltage NOW" 1:"freq capped NOW" 2:"throttled NOW" 3:"soft temp limit NOW" \
             16:"under-voltage has occurred" 17:"freq capping has occurred" \
             18:"throttling has occurred" 19:"soft temp limit has occurred"; do
      bit=${b%%:*}; (( v >> bit & 1 )) && echo "  bit $bit SET  ${b#*:}"
    done; echo "  (raw $v)"'
  sec "PMIC ADC (all rails)" vcgencmd pmic_read_adc
  sec "PSU as seen by firmware (/proc/device-tree/chosen/power)" sh_ '
    for f in /proc/device-tree/chosen/power/*; do
      printf "%s = %d\n" "$(basename $f)" "0x$(od -An -tx1 $f | tr -d " \n")"; done'
  sec "usb_max_current_enable" vcgencmd get_config usb_max_current_enable
  sec "temperature" vcgencmd measure_temp
  sec "arm clock" vcgencmd measure_clock arm
  sec "under-voltage events this boot (kernel journal)" sh_ '
    n=$(sudo journalctl -k -b --no-pager | grep -c "Undervoltage detected")
    echo "count=$n"
    sudo journalctl -k -b --no-pager | grep "Undervoltage detected" | sed -n "1p;\$p"'

  echo; echo "### PCIe / USB"
  sec "lspci" lspci
  sec "Hailo PCIe link" sh_ 'sudo lspci -vv -s 0001:01:00.0 | grep -E "LnkCap:|LnkSta:"'
  sec "lsusb" lsusb
  sec "lsusb tree" lsusb -t

  echo; echo "### GPIO (pinctrl, all pins)"
  sec "pinctrl get" sudo pinctrl get
  echo; echo "### I2C"
  sec "i2c device nodes" sh_ 'ls -l /dev/i2c* 2>&1'
  sec "i2c modules" sh_ 'lsmod | grep -i i2c'
  sec "i2c dtparams" sh_ 'grep -nE "i2c" /boot/firmware/config.txt'
  echo; echo "### SERIAL"
  sec "tty devices" sh_ 'ls -l /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/* 2>&1'
  sec "ESP32 USB bridge (udev)" sh_ 'udevadm info -q property -n /dev/ttyUSB0 | grep -E "ID_(VENDOR|MODEL|SERIAL|USB_DRIVER|PATH)="'
  sec "serial protocol (from code)" echo "115200 8N1, default DTR/RTS (see esp32_link.py), port /dev/ttyUSB0"
  sec "pi groups" id pi

  echo; echo "### NETWORK"
  sec "interfaces" ip -br addr
  sec "listening sockets" sudo ss -tulpn
  sec "rfkill" rfkill list

  echo; echo "### SYSTEMD"
  sec "boot time" systemd-analyze
  sec "boot blame (top 15)" sh_ 'systemd-analyze blame | head -15'
  sec "failed units" systemctl --failed --no-pager
  sec "enabled system units" systemctl list-unit-files --state=enabled --no-pager
  sec "time sync" timedatectl
} > "$OUT/system_report.txt"

# ----------------------------------------------------------------- hailo
{
  echo "HAILO REPORT  $(date -Is)"
  sec "fw-control identify" hailortcli fw-control identify
  sec "hailortcli version" hailortcli --version
  sec "hailo packages" sh_ 'dpkg -l | grep -iE "hailo|tappas"'
  sec "hailo_pci module" sh_ '/usr/sbin/modinfo hailo_pci | grep -E "^(filename|version|srcversion|vermagic)"'
  sec "loaded" sh_ 'lsmod | grep hailo'
  sec "dkms status" sudo /usr/sbin/dkms status
  sec "hailort.service" systemctl show hailort.service -p ActiveState -p SubState -p ExecMainStartTimestamp -p NRestarts
  sec "hailort_service binary" sh_ 'ls -l /usr/local/bin/hailort_service; dpkg -S /usr/local/bin/hailort_service 2>&1'
  sec "PCIe link" sh_ 'sudo lspci -vv -s 0001:01:00.0 | grep -E "LnkCap:|LnkSta:"'
  sec "config.txt PCIe lines" sh_ 'grep -nE "pciex1|pcie" /boot/firmware/config.txt'
  sec "model selected by detect.py" sh_ "cd $SC && python3 -c 'import detect; print(detect.pick_model(None))'"
  sec "installed models" ls -l /usr/share/hailo-models/
  sec "model sha256" sha256sum /usr/share/hailo-models/yolov8s_h8l.hef
  sec "parse-hef" hailortcli parse-hef /usr/share/hailo-models/yolov8s_h8l.hef
  sec "kernel: hailo events this boot" sh_ '
    j=$(sudo journalctl -k -b --no-pager)
    echo "Device disconnected : $(grep -c "hailo.*Device disconnected" <<<"$j")"
    echo "find_vma WARNINGs   : $(grep -c "hailo_vdma_buffer_map" <<<"$j")"
    grep -i "hailo" <<<"$j" | grep -v -e "Call trace" -e "hailo_vdma" | tail -8'
} > "$OUT/hailo_report.txt"

# ---------------------------------------------------------------- sensors
{
  echo "SENSOR REPORT  $(date -Is)"
  echo "ESP32 ToF data is captured separately by esp32_capture.py (service stopped)."
  sec "cameras" rpicam-hello --list-cameras
  sec "kernel: camera" sh_ 'sudo journalctl -k -b --no-pager | grep -iE "imx708|rp1-cfe|unicam" | tail -5'
  sec "camera settings used by the service" sh_ "
    systemctl --user show smartcane.service -p ExecStart --value | tr ' ' '\n' | grep -A1 -E -- '--(fps|ev)' | paste - - -d' '
    grep -nE 'add_argument\(\"--(width|height|fps|ev|hfov|corridor)\"' $SC/detect.py
    grep -nE 'XRGB8888|RGB888|NoiseReductionMode|AeExposureMode' $SC/detect.py"
  sec "ESP32 serial device" sh_ 'ls -l /dev/serial/by-id/'
  echo; echo "### BLUETOOTH"
  sec "adapter" bluetoothctl show
  sec "headset $BT_MAC" bluetoothctl info $BT_MAC
  sec "link key stored? (key itself not printed)" sh_ "
    f=\$(sudo find /var/lib/bluetooth -path '*$BT_MAC/info' 2>/dev/null | head -1)
    [ -n \"\$f\" ] && sudo grep -c '^\[LinkKey\]' \"\$f\" || echo 'no pairing record'"
  sec "/etc/bluetooth/main.conf (active lines)" sh_ 'grep -vE "^\s*(#|$)" /etc/bluetooth/main.conf'
  echo; echo "### AUDIO"
  sec "pactl info" pactl info
  sec "sinks" pactl list short sinks
  sec "suspend module loaded? (must be empty)" sh_ 'pactl list short modules | grep suspend'
  sec "user default.pa vs system" sh_ 'diff /etc/pulse/default.pa ~/.config/pulse/default.pa'
  # The per-user journal is not persisted on this Pi (journalctl --user finds
  # no files), so user units are read from the system journal. Every SSH
  # logout restarts PulseAudio (measured 2 Oct 2026), so compare the two counts.
  sec "pulseaudio starts vs SSH sessions this boot" sh_ '
    echo "pulseaudio starts : $(sudo journalctl -b --no-pager | grep -c "Started pulseaudio.service")"
    echo "ssh sessions      : $(sudo journalctl -b --no-pager -t sshd | grep -c "session opened")"'
  sec "speech engine" sh_ 'espeak-ng --version; command -v paplay'
} > "$OUT/sensor_report.txt"

# --------------------------------------------------------------- service
{
  echo "SERVICE REPORT  $(date -Is)"
  sec "unit file" systemctl --user cat smartcane.service
  sec "state" systemctl --user show smartcane.service -p ActiveState -p SubState -p Result \
       -p NRestarts -p MainPID -p ExecMainStartTimestamp -p UnitFileState
  sec "linger" loginctl show-user pi -p Linger
  sec "processes" sh_ 'ps -o pid,ppid,pcpu,rss,etime,args -C python3,hailort_service,pulseaudio,bluetoothd,paplay'
  sec "detect.py environment (secrets filtered)" sh_ "
    p=\$(pgrep -f smartcane/detect.py | head -1)
    [ -n \"\$p\" ] && tr '\0' '\n' < /proc/\$p/environ | grep -viE 'key|token|pass|secret' | sort"
  sec "smartcane journal counts this boot" sh_ '
    j=$(sudo journalctl -b --no-pager _SYSTEMD_USER_UNIT=smartcane.service)
    for k in "SPEAKING" "AUDIO OK" "AUDIO DEAD" "Warning" "not responding" \
             "Traceback" "HAILO_" "starting vision" "stopped"; do
      printf "%-18s %s\n" "$k" "$(grep -c "$k" <<<"$j")"; done
    # Vision health proxy: the last sentence that came from the camera rather
    # than the forward ToF ("obstacle ahead, N centimetres") or a warning.
    # A vision outage on 2 Oct 2026 went unnoticed for 1 h 46 min.
    last=$(grep "SPEAKING" <<<"$j" | grep -vE "obstacle ahead, [0-9]+ (centi|metre)|Warning|ready|drop ahead|Step up" | tail -1 | cut -c1-15)
    echo "last camera-derived speech: ${last:-none this boot}"'
  sec "smartcane journal (last 30)" sh_ 'sudo journalctl -b --no-pager -n 30 _SYSTEMD_USER_UNIT=smartcane.service'
  sec "related system services" systemctl is-active hailort bluetooth log2ram
  sec "errors this boot (prio err)" sh_ 'n=$(sudo journalctl -b -p err --no-pager | wc -l); echo "lines=$n"; sudo journalctl -b -p err --no-pager | grep -v hailo_vdma | tail -15'
} > "$OUT/service_report.txt"

# -------------------------------------------------------------- versions
dpkg-query -W -f='${Package} ${Version}\n' > "$OUT/dpkg_full.txt"
apt-mark showmanual > "$OUT/apt_manual.txt"
{
  echo "VERSIONS  $(date -Is)"
  sec "key packages" sh_ 'dpkg-query -W -f="\${Package} \${Version}\n" 2>/dev/null | grep -E "^(hailo|python3-hailort|python3-picamera2|libcamera0|libcamera-ipa|rpicam-apps|python3-opencv|python3-numpy|python3-serial|pulseaudio |pulseaudio-module-bluetooth|bluez |espeak-ng |linux-image-rpi-2712|rpi-eeprom|raspi-firmware|log2ram|systemd )"'
  sec "python" python3 --version
  sec "python modules (system interpreter used by the service)" python3 -c '
import importlib
for m in ["picamera2","numpy","cv2","serial","hailo_platform","libcamera"]:
    try:
        mod = importlib.import_module(m); print(m, getattr(mod, "__version__", "?"))
    except Exception as e:
        print(m, "IMPORT FAILED", e)'
  sec "venv pip freeze ($SC/venv)" $SC/venv/bin/pip freeze
  sec "arduino-cli" sh_ '~/.local/bin/arduino-cli version; ~/.local/bin/arduino-cli core list; ~/.local/bin/arduino-cli lib list'
  sec "esptool" ~/.arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool version
  sec "deployed files sha256" sh_ "cd $SC && find . -type f \( -name '*.py' -o -name '*.ino' -o -name '*.sh' -o -name '*.txt' \) \
      -not -path './venv/*' -not -path '*/build/*' -not -path '*/__pycache__/*' | sort | xargs sha256sum"
  sec "installed unit sha256" sha256sum ~/.config/systemd/user/smartcane.service
  sec "flashed ESP32 app (build artifact)" sha256sum $SC/esp32/build/cane_safety.ino.bin
  sec "dpkg package count" sh_ "wc -l < '$OUT/dpkg_full.txt'"
} > "$OUT/versions.txt"

echo "snapshot written to $OUT"
ls -l "$OUT"
