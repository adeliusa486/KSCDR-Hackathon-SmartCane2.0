# Step 1.2 test plan: fix Raspberry Pi power before optimizing AI

## What is being tested

That the Pi 5, with the Hailo HAT, camera, ESP32, audio and motor attached,
runs without under-voltage or any device loss on a proper 5 V / 5 A USB-C
supply, under every load the cane can produce, for 30 min, 60 min and 2 h.

## Why it matters

On 2 Oct the UPS feeding the 5V header pin sagged: 19 under-voltage events
from 18:03 to 18:19, then a Hailo PCIe failure that left vision dead for
1 h 46 min with no warning (Step 1.1, F1). Another under-voltage event
happened at 21:03:16 on the restored system, about 50 s after the service
started. Nothing measured on this supply can be trusted, and no AI work is
worth doing until power is fixed.

## Two parts

**Part A, before: the current UPS supply.** A short load ladder with
`--abort-on-uv`, so the first new under-voltage event stops the load before
it can push the Hailo into the F1 state. It shows which load level the
current supply fails at, which is the number the new supply must beat. Part A
cannot pass Step 1.2. It is the comparison.

```text
idle:120  service:180  bench:120  bench_cpu:120  svc_cpu:180   --abort-on-uv
```

**Part B, the step itself: the 5 V / 5 A USB-C supply.** Needs Adeel: plug the
supply into the Pi's USB-C port and remove the UPS feed from the 5V header pin
(never both at once, two sources back-feed each other). Then:

1. Check the supply negotiated 5 A: `/proc/device-tree/chosen/power/max_current`
   reads 5000, and `vcgencmd get_throttled` sticky bits are clear after boot.
2. Short ladder, same phases as Part A, without abort, to confirm every load
   level before the long runs.
3. Three continuous runs at the worst realistic load (`svc_cpu`: camera,
   Hailo, ESP32, audio, all 4 CPU cores busy): 30 min, 60 min, 2 h.
4. One 30 min run at maximum AI load (`bench_cpu`).

All runs use `code/tools/power_soak.sh`, detached, 1 s sampling. A snapshot
(`code/tools/snapshot_pi.sh`) before Part A and after Part B.

## What is logged

Every second: EXT5V input voltage, `get_throttled` flags, SoC temperature,
ARM clock, PMIC rail power (lower bound on board power), 1 min load, gateway
ping (Wi-Fi), CPU time used by detect.py since the last sample. Continuously: every
kernel line about under-voltage, Hailo, USB, MMC, ext4 or I/O errors.

## Pass criteria (Part B only, fixed before measuring)

| # | Criterion | Pass if |
|---|---|---|
| P1 | Supply negotiated | `max_current` 5000 mA |
| P2 | No under-voltage | 0 `Undervoltage detected` events and `get_throttled` bit 16 never set, across all runs |
| P3 | Hailo stays up | 0 Hailo disconnect or error lines, benchmark FPS in the last minute of each run within 5 % of its first minute |
| P4 | Vision alive | in `svc_cpu`, detect.py CPU time never below 0.02 s per 1 s sample for more than 5 s in a row (a proxy, see README) |
| P5 | No unexpected reboot | `uptime -s` unchanged across each run |
| P6 | USB and camera stay | 0 USB disconnect lines, ESP32 link never silent (no "ESP32 LINK SILENT" in the service log), camera never lost |
| P7 | No filesystem errors | 0 MMC, ext4 or I/O error lines |
| P8 | No service crash | `NRestarts` unchanged, service `active` at the end |
| P9 | No thermal throttling | `get_throttled` bits 1/17 and 2/18 never set, temperature peak recorded |
| P10 | Wi-Fi / SSH stable | gateway ping lost in under 1 % of samples, each SSH check during the run succeeds |
| P11 | Minimum input voltage recorded | min EXT5V reported. Informational, the pass test is P2 |

Any one failure means Step 1.2 FAILS. Per the ABSOLUTE RULE: stop,
investigate, fix, rerun the full set.

## Not in this step

Real input current and power. The PMIC sum misses the USB devices and the
Hailo HAT. Step 1.3 measures input power with an inline USB-C meter.

## Addendum, 2 Oct 2026 (late), before Part B: logs must survive a power cut

Added after G7 (`failure_log.md`): the persistent journal sat in the
log2ram tmpfs. Part B runs for about 4 h, and an under-voltage reset in that
time must leave a readable log.

Order: apply `code/tools/journal_persist.sh apply` and reboot right after
the USB-C supply is fitted, before the first load run.

Pass, fixed before testing:

| # | Criterion | Pass if |
|---|---|---|
| J1 | `/var/log` on the SD card | `journal_persist.sh verify` exits 0 |
| J2 | A notice-level line written 20 s before a power cut survives | `check` finds it, 3 of 3 cuts |
| J3 | A crit-level line written just before a power cut survives | `check` finds it, 3 of 3 cuts |
| J4 | The card survives the cuts | no ext4 errors in the next boot's kernel log, `fsck` clean on the next SD image |

A power cut is pulling the USB-C plug with the system running. Three cuts
on purpose is a small risk to the card, which is why the SD image from
Step 1.1 exists.
