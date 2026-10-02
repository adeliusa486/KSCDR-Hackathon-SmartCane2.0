# Step 1.1 failure and anomaly log (2 Oct 2026)

Step 1.1 freezes the system as found. Nothing below was fixed in this step
except the measurement tools themselves. Each entry names the step that owns
the fix.

## F1. Vision has been dead since 18:19:49 and the user was never told (CRITICAL)

Evidence:

- 19 kernel under-voltage events, 18:03:46 to 18:19:42.
- Last sentence that came from the camera: 18:19:49 ("obstacle right, far").
  Every SPEAKING line after that is the forward ToF ("obstacle ahead, N
  centimetres") or a warning.
- From 18:20:21, 33 kernel lines `hailo 0001:01:00.0: Device disconnected while
  opening device`. A PCI rescan ran at 18:29:25 (previous session's recovery
  procedure).
- After the rescan the Hailo answers control requests (`fw-control identify`
  reports HAILO8L, firmware 4.20.0) but runs no inference:
  `hailortcli benchmark` showed `FPS: 0.00` for the full 15 s and ended in
  `HAILO_TIMEOUT(4)`. detect.py printed zero report lines in 30 s at fps 15
  and again at fps 30, where it should print one every 0.3 s.
- `smartcane.service` stayed `active (running)` with `NRestarts=0` the whole
  time. The cane warned about nothing.

Root cause: the supply (UPS into the Pi's 5V header pin) sags under load. The
data path of the Hailo does not survive the PCIe disconnect plus rescan.

Impact: about 1 h 46 min of operation with no vision and no fault warning.
This is the silent-failure class from Principle 1.

Owner: power fix in Step 1.2. A power cycle restores the device for the
Step 1.1 close-out measurement. Detection of "Hailo alive but not inferring"
belongs in Step 4.8 (health monitor). Consider pulling a minimal vision
watchdog forward, because the same silent outage can return any time.

## F2. Every SSH logout restarts PulseAudio

- 134 PulseAudio starts this boot against 355 SSH sessions.
- Since 19:47, 12 of 12 SSH session closes were followed by a PulseAudio
  start 1 to 3 s later. No restarts between 19:26:51 and 19:47:23, when no
  one was logged in.
- The service logged 89 `AUDIO DEAD` (default sink `auto_null`) events, each
  healed by `AudioLink` within about 2 s.

Mechanism not proven. PulseAudio shuts down in an orderly way ("After module
unload, module 'module-null-sink' was still loaded!"), and its unit runs in
`session.slice`. Field use has no SSH sessions, so this is a bench artifact,
but it invalidates any audio measurement taken while someone is SSH'd in.

Owner: Step 4.5. Until then, audio tests run with no SSH session open.

## F3. Full ESP32 flash read fails at the same address every time

`read-flash 0 0x400000` failed at 0x0002A000 (4.1%) at 921600 baud and again
at 460800 baud with "No more data to read from the serial port". The kernel
logged `cp210x ttyUSB0: failed set request 0x12 status: -110` each time. Same
address at two speeds means the trigger depends on the data, not on timing.
Writes work (the firmware was flashed from this Pi at 19:22).

Workaround used: `verify-flash` (MD5 on the chip, no bulk read) plus a 64 KB
read of the low flash. Not blocking. Owner: Step 1.5 (serial link).

## F4. Tooling incident: unguarded flash write step

The first version of `baseline_window.sh` dumped and wrote the ESP32 flash
inline with no checks between steps. When the read failed (F3), the write
step still ran. esptool refused it because the dump file did not exist, so
nothing was written. The ESP32 stayed in its ROM bootloader from 19:59:52 to
about 20:01:16, so the bench safety loop was down for about 85 s.

A second slip: `pkill -f baseline_window.sh` matched the SSH command line
that contained it and killed that session before the second `pkill` ran.

Fix: the flash work moved to `esp32_backup.sh`, which verifies before it
writes and always resets the ESP32 and restarts the service on exit. Process
lookups now use a bracket pattern (`pgrep -f "[e]sptool"`).

## F5. Duplicate stale readings when the serial port opens

Within 90 ms of opening the port (after `reset_input_buffer()`), 2,676 D
lines arrived carrying only two distinct readings (ESP32 time 2092145 and
2092195). That is about 680 KB/s, far above the 11.5 KB/s a 115200-baud UART
carries, so the bytes did not come over the wire. They came from a buffer on
the Pi side. Steady state afterwards was clean: 19.87 Hz, interval P50
50.0 ms, P99 60.0 ms, max 60.1 ms.

`esp32_link.py` opens the port the same way, so the service may act on stale
distances for its first ~90 ms. Owner: Step 1.5 (stale-data detection).

## F6. Downward ToF (ToF 2) is not working

Boot scan finds 0x29 on bus 2, init fails, then bus 2 is empty for the rest of
the run. 61 `E tof2 init failed` lines in 60 s. `T` reads `EE AA 10` on ToF 1
and nothing on ToF 2. Known loose wire (MEMORY.md step 3g). Owner: Step 1.4.

## F7. Camera field of view is 98 degrees, not 120

Picamera2 selects sensor mode 1536x864, a centre crop of 3072x1728 (two
thirds of the sensor width). Rectilinear estimate of the horizontal FOV:
98.2 degrees. `detect.py` computes bearings with `--hfov 120`, so its ±10
degree "ahead" corridor covers about ±6.7 degrees in reality. The 16:9 crop
is also scaled into a 640x640 square, which squeezes every object
horizontally by 1.78x before YOLO sees it.

Same probe, bench lighting: exposure pinned at the 66.2 ms limit, analogue
gain 11.64, 42 lux. Owner: Step 3.4 (camera pipeline). The bearing error
affects every left/ahead/right word the cane speaks.

## F8. Boot took 9.39 s, not 6.8 s

`systemd-analyze`: 5.823 s kernel + 3.571 s userspace = 9.394 s, against
6.787 s on 19 September. The first under-voltage event of this boot is at
18:03:46, the boot itself. Cause not established. Re-measure after the
close-out power cycle and again in Step 1.2.

## F9. Snapshot tooling bugs (fixed)

- `journalctl --user` finds no files on this Pi, so the first snapshot showed
  0 for PulseAudio starts and service events. Fixed: system journal with
  `_SYSTEMD_USER_UNIT=`.
- The power logger's `grep` matched the "5V" inside `EXT5V`, splitting each
  CSV row in two. Data recovered into `power_thermal_log_fixed.csv`, logger
  fixed.
- `modinfo` is not on the non-root PATH. Fixed to `/usr/sbin/modinfo`. The
  driver version was added to the baseline Hailo report as a marked addendum.

## F10. Leftovers relevant to later steps

- `icecast2` listens on 0.0.0.0:8000. MEMORY.md flagged it on 19 September.
  Owner: Step 5.10 (security), or remove earlier.
- ESP32 boot spends about 400 ms in the blocking "alive" double buzz before
  `loop()` starts. First distance report 858 ms after reset release (3 of 3
  trials). Owner: Step 1.5 (boot self-test).
- An EN-pin reset reports `rst:0x1 (POWERON_RESET)`, so reset-reason logging
  cannot tell it from a real power-on. Owner: Step 1.5.
- Pi powered through the 5V header pin: firmware reports `max_current 3000`,
  `usb_max_current_enable 0`, so all USB ports share 600 mA, and the ESP32
  plus motor sit on that budget. Owner: Step 1.2.
