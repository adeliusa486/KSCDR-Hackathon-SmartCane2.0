#!/bin/bash
# Smart cane - undo hailort_install.sh: back to the apt HailoRT 4.20 stack.
# Run ON THE PI. Safe to run more than once.
set -u
K=$(uname -r)
log() { echo "=== $(date +%T) rollback: $*"; }

systemctl --user stop smartcane.service 2>/dev/null
sudo modprobe -r hailo_pci 2>/dev/null

log "remove 4.23 files"
sudo rm -f /lib/modules/$K/extra/hailo_pci.ko /usr/local/lib/libhailort.so.4.23.0 \
           /usr/local/lib/libhailort.so /usr/local/bin/hailortcli
sudo ldconfig
sudo pip3 uninstall -y --break-system-packages hailort 2>&1 | tail -1
[ -f /lib/firmware/hailo/hailo8_fw.bin.4.20 ] && sudo cp /lib/firmware/hailo/hailo8_fw.bin.4.20 /lib/firmware/hailo/hailo8_fw.bin

log "reinstall apt 4.20 (rebuilds the DKMS driver)"
sudo apt-get install -y --reinstall hailo-dkms hailort hailofw python3-hailort 2>&1 | tail -2
sudo /usr/sbin/dkms install hailo_pci/4.20.0 -k "$K" 2>&1 | tail -1
sudo depmod -a "$K"
sudo modprobe hailo_pci
sudo systemctl enable --now hailort.service
hash -r
log "check"
hailortcli fw-control identify 2>&1 | grep -E "Firmware|Architecture"
python3 -c "import hailo_platform; print('hailo_platform', hailo_platform.__version__)"
