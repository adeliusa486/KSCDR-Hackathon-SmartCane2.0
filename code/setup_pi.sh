#!/usr/bin/env bash
# Smart cane - step 1 installer.
# Run on the Raspberry Pi 5 (Raspberry Pi OS Bookworm, 64-bit).
#   chmod +x setup_pi.sh && ./setup_pi.sh
set -euo pipefail

CONFIG=/boot/firmware/config.txt

say() { printf '\n=== %s ===\n' "$1"; }

say "Checking we are on a 64-bit Bookworm Pi"
arch=$(uname -m)
if [ "$arch" != "aarch64" ]; then
    echo "This is $arch, not aarch64. The Hailo packages are 64-bit only."
    echo "Reflash with Raspberry Pi OS (64-bit) Bookworm and start again."
    exit 1
fi
grep -q bookworm /etc/os-release || echo "WARNING: this does not look like Bookworm. Continuing anyway."

say "Updating the system (this is slow the first time)"
sudo apt update
sudo apt full-upgrade -y

say "Updating the bootloader/EEPROM"
# The PCIe connector needs recent firmware before the AI HAT+ will enumerate.
sudo rpi-eeprom-update -a || echo "EEPROM update reported an issue, continuing."

say "Installing the Hailo stack (driver, HailoRT, TAPPAS core, models, Python bindings)"
sudo apt install -y hailo-all

say "Installing the camera stack"
sudo apt install -y python3-picamera2 rpicam-apps python3-opencv python3-numpy

say "Enabling PCIe Gen3 for the AI HAT+"
# Gen3 roughly doubles NPU throughput. Officially out of spec but this is the
# setting Raspberry Pi documents for the AI HAT+.
if grep -q '^dtparam=pciex1_gen=3' "$CONFIG"; then
    echo "Already set."
else
    # Remove any Gen1/Gen2 line first so we do not end up with two.
    sudo sed -i '/^dtparam=pciex1_gen=/d' "$CONFIG"
    echo 'dtparam=pciex1_gen=3' | sudo tee -a "$CONFIG" >/dev/null
    echo "Added dtparam=pciex1_gen=3 to $CONFIG"
fi

say "Installed versions"
hailortcli --version 2>/dev/null || echo "hailortcli not on PATH yet (normal before reboot)"
dpkg -l | grep -E 'hailo|picamera2' | awk '{print $2, $3}' || true

cat <<'DONE'

=== Done. Reboot now. ===

    sudo reboot

After the reboot, verify in this order:

    hailortcli fw-control identify          # NPU alive, prints HAILO8L or HAILO8
    rpicam-hello --list-cameras             # camera alive, prints the sensor name
    python3 check_hardware.py               # our own combined check
    python3 detect.py                       # camera -> Hailo -> named objects

Record the printed device architecture and sensor name in MEMORY.md.
DONE
