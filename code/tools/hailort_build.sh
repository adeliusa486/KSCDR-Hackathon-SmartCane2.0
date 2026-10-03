#!/bin/bash
# Smart cane - build HailoRT 4.23.0 for the Hailo-8L from Hailo's open-source
# repos (hailo-ai/hailort and hailo-ai/hailort-drivers, tag v4.23.0, MIT/GPL).
# Run ON THE PI, detached:
#   nohup bash hailort_build.sh > ~/hailort423/build.log 2>&1 &
#
# BUILD ONLY. Nothing is installed: the cane keeps HailoRT 4.20 until
# hailort_install.sh runs after this succeeds. Why 4.23: HEFs from the
# Ultralytics Platform (DFC 3.33) need it, and Raspberry Pi's apt stops at 4.20.
#
# Gentle on power: 2 cores, low priority. The Pi is still on the UPS feed that
# browns out under load (Step 1.2), so a watchdog kills the build at the first
# new under-voltage event rather than risk the SD card.

set -u
V=4.23.0
W=$HOME/hailort423
mkdir -p "$W"; cd "$W"
log() { echo "=== $(date +%T) $*"; }
uv() { sudo journalctl -k -b --no-pager | grep -c "Undervoltage detected"; }
UV0=$(uv)

( while sleep 5; do
    if [ "$(uv)" -gt "$UV0" ]; then
      echo "=== $(date +%T) UNDER-VOLTAGE during build: stopping it"
      pkill -f "[c]make --build"; pkill -f "[m]ake -j"; pkill -f "[c]c1plus"; exit
    fi
  done ) &
WATCH=$!
trap 'kill $WATCH 2>/dev/null' EXIT

log "clone v$V (shallow)"
[ -d hailort ] || git clone -q --depth 1 --branch v$V https://github.com/hailo-ai/hailort.git || exit 1
[ -d hailort-drivers ] || git clone -q --depth 1 --branch v$V https://github.com/hailo-ai/hailort-drivers.git || exit 1

log "driver: hailo_pci for $(uname -r)"
( cd hailort-drivers/linux/pcie && nice -n 19 make -j2 all ) || { log "DRIVER BUILD FAILED"; exit 1; }
find hailort-drivers -name "hailo_pci.ko" -exec ls -l {} \;

log "firmware"
( cd hailort-drivers && bash ./download_firmware.sh ) || { log "FIRMWARE DOWNLOAD FAILED"; exit 1; }
ls -l hailort-drivers/hailo8_fw.*.bin

log "libhailort, hailortcli, hailort_service, Python binding"
cmake -S hailort -B hailort/build -DCMAKE_BUILD_TYPE=Release \
      -DHAILO_BUILD_PYBIND=1 -DPYBIND11_PYTHON_VERSION=3.11 > cmake_config.log 2>&1 \
  || { log "CMAKE CONFIGURE FAILED"; tail -30 cmake_config.log; exit 1; }
nice -n 19 cmake --build hailort/build --config release -j2 || { log "BUILD FAILED"; exit 1; }
find hailort/build -name "libhailort.so*" -o -name "hailortcli" -o -name "hailort_service" -o -name "_pyhailort*.so" | xargs ls -l

log "UV events during build: $(( $(uv) - UV0 ))"
log "BUILD OK, nothing installed yet"
