# Step 1.1 test plan: freeze and back up the working prototype

## What is being tested

That the prototype as it runs on 2 Oct 2026 is (a) fully described, (b) backed
up, and (c) restorable, before Phase 1 changes anything. Step 1.1 does not
judge whether the system is healthy. A faulty part is recorded as a baseline
finding, not fixed here.

## Why it matters

Every later step changes hardware, firmware or software. Without an exact
record of the starting point, a regression cannot be told apart from a
pre-existing fault, and without a tested rollback a bad change can strand the
only working copy.

## Method

1. `code/tools/snapshot_pi.sh` with the service running: read-only reports on
   system, Hailo, sensors, service and versions.
2. Byte comparison of every deployed file in `/home/pi/smartcane` and the
   installed unit against the laptop copy.
3. `code/tools/baseline_window.sh`, detached on the Pi: stop the service, then
   - ESP32 stream 60 s without reset, commands `T` (bus scan + ID) and `S`
   - camera list and probe with detect.py's exact settings
   - `hailortcli fw-control identify` and a 15 s benchmark
   - detect.py 30 s at fps 15 (service settings) and 30 s at fps 30
   - ESP32 4 MB flash dump, write it back, read again, compare (rollback test)
   - ESP32 reset with boot timing, `T` and `S` again

   **Deviation during the run:** the 4 MB read failed twice at the same
   address (failure_log F3). The firmware check moved to
   `code/tools/esp32_backup.sh`: on-chip `verify-flash` against the build
   artifacts, two reads of the low 64 KB, then write-back and verify again.
   P3 and P4 are judged on that method.
   - restart the service and check it recovers
   - 1 Hz power/thermal log for the whole window
4. Git: commit the as-found code, then the records, tag
   `consumer-baseline-before-phase1`.
5. Pi config tarball and package manifests copied off the device.
6. Offline SD card image (needs Adeel: power off, card into laptop).

## Pass criteria

| # | Criterion | Pass if |
|---|---|---|
| P1 | All items from the plan's record list are captured | each has a non-empty section in `baseline/` |
| P2 | Deployed Pi code equals the repo | sha256 equal for every file and the unit |
| P3 | Running ESP32 firmware equals a known build | app region of the flash dump is byte-equal to `cane_safety.ino.bin` |
| P4 | ESP32 firmware rollback works | dump written back, re-read, sha256 equal, ESP32 boots and reports |
| P5 | Git baseline exists | tag `consumer-baseline-before-phase1`, clean tree |
| P6 | Pi configuration is off-device | tarball + manifests on the laptop, sha256 recorded, archive lists cleanly |
| P7 | Full OS rollback is possible | SD image on the laptop, sha256 recorded, partition table and ext4/vfat signatures check out |
| P8 | The baseline exercise did no harm | service active again, speaks, ESP32 link alive, no new under-voltage or Hailo disconnect caused by the window |
| P9 | Current performance is measured, not assumed | Hailo identify/link, camera mode, vision FPS, ESP32 rate and intervals, ToF IDs and stats recorded with numbers |

P9 records numbers. It does not compare them with targets. A number that
disagrees with the plan's section 1 baseline is reported as a correction.

## Fail / blocked

- Any of P1–P6 or P8 not met → FAIL, fix and redo.
- P7 not done → BLOCKED: everything except the OS image can be rolled back.

## Diagnosing failures

- Snapshot command shows `(exit N)`: read the section. A missing tool or an
  expected empty grep is benign, anything else gets investigated.
- ESP32 dump mismatch: re-read twice. A differing NVS region alone can mean
  the firmware wrote preferences between reads, which it should not do while
  held in the bootloader.
- Service fails to come back: `journalctl _SYSTEMD_USER_UNIT=smartcane.service`
  (the per-user journal is not persisted on this Pi, use the system journal).
