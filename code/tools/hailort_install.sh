#!/bin/bash
# Smart cane - install the HailoRT 4.23.0 stack built by hailort_build.sh, then
# test it. Run ON THE PI with sudo rights, after the build and pybind succeeded:
#   bash hailort_install.sh 2>&1 | tee ~/hailort423/install.log
#
# Installs next to the apt 4.20 packages, which stay in place:
#   driver    /lib/modules/<kernel>/extra/hailo_pci.ko   (DKMS 4.20 module removed)
#   firmware  /lib/firmware/hailo/hailo8_fw.bin          (4.20 copy kept as .4.20)
#   library   /usr/local/lib/libhailort.so.4.23.0
#   cli       /usr/local/bin/hailortcli                  (shadows /usr/bin)
#   python    hailo_platform 4.23.0 via pip --no-deps    (shadows the apt one)
# hailort.service (the 4.20 multi-process service) is disabled: the cane runs
# one vision process and needs no service, and a 4.20 service must not talk
# to a 4.23 driver.
#
# Test: identify must report firmware 4.23.0, the benchmark of the current
# yolov8s_h8l.hef must run, and detect.py must produce report lines. If any
# test fails, hailort_rollback.sh runs automatically.
#
# NOTE: the 4.23 module is built for one kernel. After a kernel upgrade it
# must be rebuilt (hailort_build.sh) or the cane has no NPU driver.

set -u
W=$HOME/hailort423
T=$HOME/smartcane/tools
K=$(uname -r)
log() { echo "=== $(date +%T) $*"; }
fail() { log "TEST FAILED: $* -> rolling back"; bash $T/hailort_rollback.sh; exit 1; }

WHL=$(ls $W/hailort/hailort/libhailort/bindings/python/platform/dist/hailort-4.23.0-*.whl 2>/dev/null | head -1)
for f in $W/hailort-drivers/linux/pcie/hailo_pci.ko $W/hailort-drivers/hailo8_fw.4.23.0.bin \
         $W/hailort/build/hailort/libhailort/src/libhailort.so.4.23.0 \
         $W/hailort/build/hailort/hailortcli/hailortcli "$WHL"; do
  [ -f "$f" ] || { log "missing build output: $f (nothing installed)"; exit 1; }
done

log "stop users of the NPU"
systemctl --user stop smartcane.service
sudo systemctl disable --now hailort.service
sudo modprobe -r hailo_pci

log "driver 4.23.0 for $K"
sudo /usr/sbin/dkms remove hailo_pci/4.20.0 -k "$K" 2>&1 | tail -1
sudo install -D -m 644 $W/hailort-drivers/linux/pcie/hailo_pci.ko /lib/modules/$K/extra/hailo_pci.ko
sudo depmod -a "$K"

log "firmware 4.23.0"
[ -f /lib/firmware/hailo/hailo8_fw.bin.4.20 ] || sudo cp /lib/firmware/hailo/hailo8_fw.bin /lib/firmware/hailo/hailo8_fw.bin.4.20
sudo install -m 644 $W/hailort-drivers/hailo8_fw.4.23.0.bin /lib/firmware/hailo/hailo8_fw.bin

log "libhailort 4.23.0 and hailortcli"
sudo install -m 755 $W/hailort/build/hailort/libhailort/src/libhailort.so.4.23.0 /usr/local/lib/
sudo ln -sf libhailort.so.4.23.0 /usr/local/lib/libhailort.so
sudo ldconfig
sudo install -m 755 $W/hailort/build/hailort/hailortcli/hailortcli /usr/local/bin/hailortcli
hash -r

log "Python binding 4.23.0"
sudo pip3 install --no-deps --break-system-packages --force-reinstall "$WHL" 2>&1 | tail -1

log "load driver"
sudo modprobe hailo_pci || fail "modprobe hailo_pci"
sleep 3
/usr/sbin/modinfo hailo_pci | grep -E "^(filename|version)"
sudo dmesg | grep -i hailo | tail -4

log "TEST 1: identify"
ID=$(hailortcli fw-control identify 2>&1); echo "$ID"
echo "$ID" | grep -q "Firmware Version: 4.23.0" || fail "identify does not report firmware 4.23.0"

log "TEST 2: Python binding"
python3 -c "import hailo_platform, sys; print('hailo_platform', hailo_platform.__version__, hailo_platform.__file__)" \
  || fail "import hailo_platform"
python3 -c "import hailo_platform; assert hailo_platform.__version__.startswith('4.23')" || fail "python sees an old hailo_platform"

log "TEST 3: benchmark the current model (HEF from the 4.20 era) on 4.23"
UV0=$(sudo journalctl -k -b --no-pager | grep -c "Undervoltage detected")
hailortcli benchmark -t 15 /usr/share/hailo-models/yolov8s_h8l.hef 2>&1 | tail -6 | tee $W/bench423.txt
grep -qE "FPS.*[1-9]" $W/bench423.txt || fail "benchmark produced no FPS"

log "TEST 4: detect.py with the camera, 30 s"
timeout -s INT 30 python3 -u $HOME/smartcane/detect.py --interval 0.3 --conf 0.25 --fps 15 --ev 0.7 --all-classes > $W/detect423.txt 2>&1
N=$(grep -c "fps\]" $W/detect423.txt); echo "report lines: $N (about 80 expected)"
[ "$N" -ge 40 ] || fail "detect.py produced $N report lines"
log "under-voltage during tests: $(( $(sudo journalctl -k -b --no-pager | grep -c 'Undervoltage detected') - UV0 ))"

log "INSTALL OK: HailoRT 4.23.0 active. smartcane.service left stopped (power supply, Step 1.2)."
