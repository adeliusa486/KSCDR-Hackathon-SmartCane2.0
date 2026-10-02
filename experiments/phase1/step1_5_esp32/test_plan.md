# Step 1.5 test plan: validate the ESP32 safety layer

**Prepared 2 Oct 2026, before the step starts.** Steps 1.2 to 1.4 must pass
first. The code is on branch `prep/step1.5-esp32-safety`, compiled on the
laptop with 0 warnings in our files, not yet flashed or run on the cane. The
pass limits below are fixed now, before any measurement.

## What changes

Firmware `cane_safety 1.5-prep` (`code/esp32/cane_safety/`):

- task watchdog, 2 s, on the loop task
- reset reason at boot plus reset counters in NVS (boots, watchdog,
  brownout, panic), version line, `S` reports them
- boot self-test: init result and ID registers of both ToF
- boot "alive" pulses no longer block the loop for about 400 ms
- safety patterns always beat a Pi request (`safety_logic.h`, unit tested):
  `B` plays only when no obstacle or ground pattern runs, `A0` mutes
  obstacle buzzing for at most 60 s and never mutes the ground alarm
- Pi heartbeat: any line counts, `P` every 0.5 s. Pi silent 3 s means the
  Pi's buzz is dropped and the ESP32 un-mutes
- `D` line gets a sequence number as an 8th field

Pi side (`code/esp32_link.py`): reopens the port after an error or 2 s of
silence (G4), drops repeated `D` lines (F5), sends the heartbeat to 1.5
firmware only. `speak_detect.py` is unchanged.

## Before flashing

1. `code/tools/esp32_backup.sh` on the current firmware: verify, back up,
   rollback test. Must pass, as on 2 Oct.
2. Laptop: `test_safety_logic.cpp` and `code/tests/test_esp32_link.py` pass.
3. Flash from the Pi, `verify-flash` against the new build.

## Tests and pass criteria

Every test at least 5 times unless stated. Timing from `esp32_capture.py`
logs (Pi monotonic clock) and ESP32 `millis` in the `D` lines. Motor state
from a logged GPIO 13 tap on a second ESP32 pin or a logic analyser if one
is available, otherwise from the firmware's own log. Say which in the
results.

| # | Test | Pass if |
|---|---|---|
| T1 | Boot, 10 cold power-ons | `I version`, `I reset poweron`, `I selftest` for both sensors, first `D` line within 600 ms of reset release (was 858 ms) |
| T2 | Watchdog: test build, send `X` | reboot within 2.5 s, next boot reports `reset task-watchdog`, `wdt` counter +1, 5 of 5 |
| T3 | `B0,5000` with an object at 30 cm | obstacle pattern continues unchanged, 5 of 5 |
| T4 | `B0,5000` and `A0`, then trigger a drop | ground alarm's 3 pulses play, 5 of 5 |
| T5 | `A0`, then wait | obstacle buzz returns after 60 s ±1 s, `I auto on (A0 lapsed)` |
| T6 | Sync buzz with nothing in front | `B85,250` plays as requested |
| T7 | Kill `speak_detect.py` during `A0` | `I pi link lost` after 3 s ±0.2 s, obstacle buzz back at once |
| T8 | Unplug ToF 1, then ToF 2 | `E` line within 300 ms + 1 retry cycle, Pi warning within 3 s, re-init on reconnect |
| T9 | Unplug the Pi USB (ESP32 then unpowered, see Phase 5 fact 1) | record what the user feels. No pass limit: this measures the power dependency |
| T10 | Reboot the Pi | record whether the ESP32 loses power or resets, reset reason, time to first `D` |
| T11 | Stop the service, start it again | ESP32 not reset (`boots` unchanged), link back within 3 s, 0 repeated lines accepted |
| T12 | Pull the ESP32 USB for 5 s, put it back, service running | link reopens without a service restart (G4), within 5 s of the ESP32's first `D` line |
| T13 | Force a sensor timeout: test build, `K1` then `K2` (holds that sensor's XSHUT low), `K0` to release | `ok=0` and an `E` line within 400 ms, Pi warning within 3 s, sensor back within 2 s of `K0` |
| T14 | 1 h soak, service running, no faults injected | 0 resets, 0 `E` lines, report interval P99 under 70 ms |

T9 and T10 have no limit because the hardware does not allow one yet: the
ESP32 runs from the Pi's USB port. Their numbers go into the Phase 5 power
design.

## Fail and diagnose

- Any reset during T11 or T14: read `S` (reset reason, counters) first.
- T3 or T4 failing means the arbiter on the chip differs from the unit test.
  Diff the flashed build against the branch and rerun the unit test.
- T12 failing: check `dmesg` for `cp210x` errors (F3, G5) before blaming the
  reader.
- Roll back with `baseline/README.md` section 2 if the cane must keep
  working while a failure is investigated.
