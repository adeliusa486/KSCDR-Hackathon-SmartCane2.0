# Baseline before Phase 1 (2 Oct 2026)

This folder freezes the smart cane as it ran on 2 Oct 2026, before any
Phase 1 change. Git tag: `consumer-baseline-before-phase1`. The code under
`code/` at commit `6d928cc` is byte-identical to `/home/pi/smartcane` on the
Pi (9 of 9 source files, plus the installed `smartcane.service`).

The baseline is not a healthy system. At capture time the Hailo ran no
inference (dead since 18:19:49 after under-voltage), the downward ToF was
absent, and PulseAudio restarted on every SSH logout. See
`experiments/phase1/step1_1_baseline/failure_log.md`.

## Files

| File | Content |
|---|---|
| `baseline_system_report.txt` | board, OS, kernel, firmware, bootloader, config.txt, power rails, under-voltage history, PCIe, USB, GPIO (`pinctrl`), I2C, serial, network, systemd, boot time |
| `baseline_hailo_report.txt` | `fw-control identify`, HailoRT and driver versions, DKMS, model in use, HEF sha256 and `parse-hef`, kernel Hailo events |
| `baseline_sensor_report.txt` | camera list, camera settings, ESP32 serial device, Bluetooth adapter and headset, link key present, PulseAudio state |
| `baseline_service_report.txt` | unit file, state, processes, detect.py environment, journal counts |
| `baseline_versions.txt` | key packages, Python modules, venv, arduino-cli, ESP32 core, VL53L0X library, esptool, deployed file sha256 |
| `dpkg_full.txt`, `apt_manual.txt` | every installed package with version, and the manually installed set |
| `esp32/` | the firmware the ESP32 runs, verified on the chip (see below) |

These are the 19:55 snapshot taken with the service running and untouched.
The same snapshot plus a post-measurement one sit in
`experiments/phase1/step1_1_baseline/before/` and `after/`.
`code/tools/snapshot_pi.sh` regenerates them.

## Rollback

### 1. Pi software

```bash
git checkout consumer-baseline-before-phase1 -- code/
scp -i ~/.ssh/pi_solver_key code/*.py code/coco.txt code/setup_pi.sh pi@192.168.3.51:smartcane/
scp -i ~/.ssh/pi_solver_key code/smartcane.service pi@192.168.3.51:.config/systemd/user/
ssh -i ~/.ssh/pi_solver_key pi@192.168.3.51 'systemctl --user daemon-reload && systemctl --user restart smartcane.service'
```

Check: `sha256sum` on the Pi matches the "deployed files sha256" section of
`baseline_versions.txt`.

### 2. ESP32 firmware (tested 2 Oct 2026, PASS)

On the Pi, with the service stopped so the port is free:

```bash
cd <repo copy of baseline/esp32>
E=~/.arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool
$E --chip esp32 -p /dev/ttyUSB0 -b 460800 write-flash 0x0 esp32_low64k.bin 0x10000 cane_safety.ino.bin
$E --chip esp32 -p /dev/ttyUSB0 -b 460800 verify-flash 0x1000 cane_safety.ino.bootloader.bin \
   0x8000 cane_safety.ino.partitions.bin 0xe000 boot_app0_flashed.bin 0x10000 cane_safety.ino.bin
```

`esp32_low64k.bin` is flash 0x0 to 0x10000: bootloader, partition table, NVS
(holds the saved sensor roles, R1) and otadata. Two reads matched. Do not
rely on a full 4 MB `read-flash`: it fails at 0x2A000 on this USB bridge.

| sha256 | file |
|---|---|
| `12a2c90dfb79648843f3eb6a4de2a3c5c1eca80c8e8321abaf3b3a54f3b3f042` | `cane_safety.ino.bin` (app, built 19:22 from `code/esp32/cane_safety/cane_safety.ino`) |
| `47bbbfca119fe87190f63a67af9d85adff6433bcf3812ec92a9b9c9416a53ad1` | `cane_safety.ino.bootloader.bin` |
| `148b959cbff1c38aa8e1d5c0ba9d612c54997b945e56a63f41223eef650653a1` | `cane_safety.ino.partitions.bin` |
| `f94c5d786a7a8fab06ac5d10e33bf37711a6697636dc037559ea19cc410a17f0` | `boot_app0_flashed.bin` |
| `01b7a1b869e6539cf28e76ea7204c6de5bc5d2606ba39ac179b3343a1b625374` | `esp32_low64k.bin` |

Toolchain that built it: arduino-cli 1.5.1, core `esp32:esp32` 3.3.12,
Pololu VL53L0X 1.3.1, FQBN `esp32:esp32:esp32`, flash dio 80 MHz 4 MB.

### 3. Pi configuration

`backups/pi_config_2026-10-02.tar.gz` (not in git), sha256
`0361d3365debe9e8775c1d0abd78f9a7b2f381b9e5517efa26c2cdd737f021d2`,
5,261 entries: `/etc`, `/boot/firmware`, `/var/lib/bluetooth`, `/usr/local`,
`/home/pi` without `.arduino15`, `.cache` and `baseline_run`. Restore single
files with `tar -xzf ... path/inside/archive`.

It holds secrets: the Wi-Fi password, Bluetooth link keys and SSH host keys.
Keep `backups/` off any shared drive.

### 4. Whole OS (tested 2 Oct 2026, PASS)

`backups/sd_2026-10-02.img` (not in git), raw image of the whole 32 GB SD
card, taken 20:22 to 20:54 with the Pi cleanly shut down.

| | |
|---|---|
| bytes | 31,914,983,424 (equal to `mmcblk0`) |
| sha256 | `ceeda80651b3510b41bcd2d9409a7fb5c2f2a8188efb9adf497663593a0960cb` |
| MBR disk signature | `4cd0d5a4` (the `root=PARTUUID=4cd0d5a4-02` in `cmdline.txt`) |
| p1 | FAT32 `bootfs`, 536,870,912 B, clean |
| p2 | ext4 `rootfs`, 31,369,723,904 B, clean, journal recovery flag clear |

Made with `code/tools/sd_image.ps1` (read-only, elevated), checked with
`code/tools/sd_image_check.py`. Check before any restore:

    Get-FileHash backups\sd_2026-10-02.img -Algorithm SHA256
    python code	ools\sd_image_check.py backups\sd_2026-10-02.img

Restore: write the image to a card of at least 31,914,983,424 bytes with
Raspberry Pi Imager ("Use custom") or Win32 Disk Imager ("Write"). A card that
is nominally 32 GB can be a few MB smaller, so check the size first. The image
holds the same secrets as the config tarball.

The only copy is on the laptop's single SSD (C:, D: and E: are one physical
disk). Copy it to a separate device.
