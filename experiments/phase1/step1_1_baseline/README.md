# Phase 1, Step 1.1: freeze and back up the working prototype

**STEP STATUS: PASS** (closed 2 Oct 2026, 21:03)

The two blocked items closed in one power-down on the unchanged supply. The
SD card is imaged and verified (P7). After the power cycle the Hailo runs at
58.2 FPS, 13.1 ms, and the vision loop reports again (P9). See "Close-out
result" at the end of this file.

Can we safely proceed to Step 1.2? **YES.** Full rollback (code, ESP32
firmware, Pi config, whole SD card) is available.

## Pass criteria (from test_plan.md)

| # | Criterion | Result | Evidence |
|---|---|---|---|
| P1 | Every record-list item captured | PASS | `baseline/` five reports + dpkg lists. Driver version added later as a marked addendum |
| P2 | Deployed code equals the repo | PASS | 9 of 9 files byte-identical, unit identical |
| P3 | Running ESP32 firmware equals a known build | PASS | on-chip `verify-flash`, 4 of 4 regions match the 19:22 build |
| P4 | ESP32 rollback works | PASS | low 64 KB + app written back, `verify-flash` again, boots and reports |
| P5 | Git baseline exists | PASS | commit `6d928cc` (as found), tag `consumer-baseline-before-phase1` |
| P6 | Pi configuration off-device | PASS | 84 MB tarball, 5,261 entries, 3 files extracted and byte-compared with the repo |
| P7 | Full OS rollback possible | PASS | `backups/sd_2026-10-02.img`, 31,914,983,424 B, sha256 `ceeda806...60cb`, read hash = file hash, partition table and both filesystems check clean (`data/sd_image/`) |
| P8 | The exercise did no harm | PASS | service active, `NRestarts=0`, 92 sentences spoken after restart, earbuds on the A2DP sink, under-voltage count unchanged at 19, Hailo disconnect count unchanged at 33 |
| P9 | Current performance measured | PASS | ESP32, ToF 1, camera, power recorded before the power cycle. Hailo and vision after it: 58.2 FPS, 13.1 ms, 81 and 83 report lines in 30 s (`data/retest_after_power_cycle/`) |

## Required report

**What was changed:** nothing on the running system. Added measurement tools
in `code/tools/` and copied them to `~/smartcane/tools/` on the Pi. Created
the git repository. The ESP32 flash was rewritten with its own verified
contents as the rollback test. The service was stopped for measurements and
restarted four times (19:57, 20:00, 20:02, 20:06).

**What was tested:** system inventory, code identity, firmware identity,
firmware restore, config backup integrity, Hailo identify and benchmark,
vision loop at fps 15 and 30, camera mode and timing, ESP32 serial stream,
ToF IDs, ESP32 boot time, service recovery, power and temperature during the
window.

**Hardware:** Pi 5 2 GB rev 1.1, AI HAT+ Hailo-8L (fw 4.20.0, PCIe 8 GT/s
x1), Arducam B0310 IMX708 on CAM0, ESP32-D0WD-V3 rev 3.1 DevKit V1 with
CP2102, ToF 1 forward and ToF 2 down (VL53L0X), motor on GPIO13, Soundcore
Life P2 Mini over Bluetooth. Pi powered by a UPS through the 5V header pin.

**Software:** Debian 12.15, kernel 6.12.109+rpt-rpi-2712, firmware
2026/05/26, HailoRT 4.20.0, hailo_pci 4.20.0 (DKMS), picamera2 0.3.31,
libcamera 0.5.2, yolov8s_h8l.hef (sha256 `a051fc15...`), ESP32 app sha256
`12a2c90d...`, git `6d928cc`.

**Test duration:** 19:47 to 20:10 on 2 Oct 2026. Service-stopped window
19:57:15 to 20:00:18, firmware work 20:01 to 20:06.

**Number of trials:** ESP32 boot 3, firmware verify 2 (before and after
restore), low-flash read 2, vision loop 2 runs of 30 s, Hailo benchmark 1 run
of 15 s, camera probe 90 frames, ESP32 stream 60 s (1,152 steady rows).

**Measurements:**

| Quantity | Min | Max | Mean | Median | P95 | P99 | n |
|---|---|---|---|---|---|---|---|
| ESP32 report interval, ms | 44.8 | 60.1 | | 50.0 | 51.3 | 60.0 | 1,151 |
| ToF 1 distance, mm (bench object, true distance not measured) | 85 | 93 | 90.3 | 90 | 92 | 93 | 1,152 |
| Camera frame interval, ms | 66.65 | 66.66 | 66.66 | | | | 89 |
| EXT5V during window, V (light load) | 4.868 | 5.006 | | 4.982 | | | 180 |
| Pi temperature during window, C | 45.0 | 49.4 | | | | | 180 |

Single values: ESP32 rate 19.87 Hz. ESP32 boot to first report 857.8 ms
(3 of 3 trials, identical to 0.1 ms). Hailo benchmark 0.00 FPS. Vision loop 0
report lines in 30 s at fps 15 and at fps 30, against about 100 expected.
Camera exposure 66.2 ms at gain 11.64, 42 lux. Effective horizontal FOV about
98 degrees. Boot time 9.394 s.

**Failure count:** 10 entries in `failure_log.md`. Critical: F1 (vision dead,
silently). Blocking later steps: F6 (ToF 2 absent). Tooling incident: F4.

**Unexpected behavior:** vision dead for 1 h 46 min with no warning (F1).
PulseAudio restarts on every SSH logout (F2). Full ESP32 flash read fails at
0x2A000 (F3). 2,676 duplicate stale readings on serial open (F5). FOV 98
degrees, not 120 (F7). Boot 9.39 s, not 6.8 s (F8).

**Root cause:** F1 is under-voltage from the UPS feed through the header pin.
F2, F3, F5 and F8 are not yet established. Details in `failure_log.md`.

**Fix:** none applied to the system in this step, by design. Tool bugs fixed
(F4, F9).

**Retest:** firmware restore retested and passed. Hailo and vision retest
waits for the power cycle.

**Final result:** baseline captured faithfully, code and firmware rollback
proven, config backup proven. The baseline shows a cane running without
vision.

## Corrections to the plan's section 1 baseline

| Plan says | Measured 2 Oct 2026 |
|---|---|
| Boot 6.8 s | 9.394 s on the 18:04 boot, 6.995 s on the 20:59 boot. Varies by 2.4 s between boots, cause not known |
| Hailo 58 FPS, 13.1 ms | Confirmed after the power cycle: 58.17 FPS, 13.14 ms. Before it: 0.00 FPS, HAILO_TIMEOUT |
| 30 FPS possible, 15 selected | Confirmed after the power cycle: loop median 15.0 fps at `--fps 15`, 30.0 at `--fps 30`. Camera delivers 15.00 fps (66.66 ms, stdev 0.001 ms) |
| ESP32 20 Hz, 50.0 to 50.1 ms | 19.87 Hz, P50 50.0 ms, P99 60.0 ms, max 60.1 ms. The 50.0 to 50.1 ms range was a short sample |
| Forward ToF mean 92.4 mm, stdev 0.8 mm | mean 90.3 mm, stdev 1.04 mm, same bench, object not re-measured |
| 120 degree lens | about 98 degrees seen by the pipeline (sensor mode crop) |
| ToF IDs EE AA 10 for both | ToF 1 only. ToF 2 does not answer |

## Close-out procedure (one power-down)

Keep the power supply exactly as it is. Step 1.2 changes it, so Step 1.1
must measure on the old supply.

1. Shut the Pi down: `sudo shutdown -h now`. Wait for the green LED to stop.
2. Remove power, take out the SD card, put it in the laptop's card reader.
3. Image it to `E:\Work\new smart cane 2.0\backups\sd_2026-10-02.img`
   (about 30 GB, the laptop has 240 GB free). Either use Win32 Disk Imager
   ("Read"), or tell the assistant the card is in: a raw read from Git Bash works if
   VS Code runs as administrator. Reading never writes to the card.
4. Put the card back, power on as before.
5. The assistant then checks the image's partition table and filesystem signatures,
   re-runs the Hailo benchmark, the two vision loops and the snapshot, and
   records boot time. If the Hailo infers again, F1 is confirmed as a
   power-state fault and Step 1.1 closes.

## Close-out result (2 Oct 2026, 20:22 to 21:03)

**SD image (P7).** Adeel shut the Pi down and moved the card to the laptop.
`code/tools/sd_image.ps1` read it elevated, with a read-only handle, in
1,897 s (16 MB/s, USB card reader). 31,914,983,424 bytes, sha256
`ceeda80651b3510b41bcd2d9409a7fb5c2f2a8188efb9adf497663593a0960cb`, computed
from the card stream and again from the saved file: equal.
`code/tools/sd_image_check.py` passes every check: MBR disk signature
`4cd0d5a4` equals the PARTUUID in `cmdline.txt`, p1 FAT32 536,870,912 B with
the clean-shutdown bit set, p2 ext4 31,369,723,904 B with the journal
recovery flag clear and 0 errors. Evidence in `data/sd_image/`. The only copy
sits on the laptop's single SSD, so a copy on a separate device is still to do.

**Hailo and vision after the power cycle (P9).** Same UPS supply, booted
20:59:02 in 6.995 s. `code/tools/vision_retest.sh`, 21:00:14 to 21:03:05:

| Quantity | Before power cycle | After |
|---|---|---|
| Hailo identify | OK | OK |
| Hailo benchmark, hw-only / streaming | 0.00 FPS, HAILO_TIMEOUT | 58.17 / 58.18 FPS |
| Hailo hw latency | n/a | 13.14 ms |
| detect.py report lines in 30 s, fps 15 / 30 | 0 / 0 | 81 / 83 |
| detect.py loop fps median, fps 15 / 30 | n/a | 15.0 / 30.0 |
| Under-voltage events this boot | 19 | 0 |
| Hailo disconnect lines this boot | 33 | 0 |
| EXT5V min during window | 4.868 V (light load) | 4.769 V (21:00:54, Hailo benchmark) |
| Temperature max | 49.4 C | 41.1 C |

About 5 s of each 30 s vision run is model load and camera start, so ~83
lines is the ceiling at `--interval 0.3`. The "about 100 expected" figure
above ignored start-up.

**F1 confirmed as a power-state fault.** A power cycle on the same supply
restores inference fully. The chip is not damaged. The supply still sags
0.10 V further under Hailo load than at light load, so Step 1.2 stays the fix.

**Not checked:** speech after the retest. The earbuds did not connect
(`br-connection-profile-unavailable`, `Connected: no`), so the service runs
with `AUDIO DEAD`. Most likely the earbuds are off or in their case. Not a
Step 1.1 criterion.
