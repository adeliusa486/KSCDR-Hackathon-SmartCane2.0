# PHASE 4 PROMPT (DRAFT): sensor fusion, user experience and failure handling

> **DRAFT, written 2 Oct 2026 at Adeel's request, before the Phase 1, 2 and
> 3 gates.** State on that date: Step 1.1 PASS, Step 1.2 BLOCKED, everything
> after it not started. Checked against `cane_safety.ino`, `speak_detect.py`,
> `detect.py`, `esp32_link.py`, `smartcane.service` and the Pi's logging and
> audio configuration.
>
> Tags as in `phase3_DRAFT.md`: *(Step 1.x)* measured, *(code)* read from the
> code on 2 Oct, *(Pi)* read from the Pi's configuration on 2 Oct, *(verify)*
> third-party fact not checked today, *(gate)*, *(Phase 2)*, *(Phase 3)* to be
> filled from those gates. Several facts below may be fixed earlier, in Step
> 1.5 or Phase 2. If so, replace them with the test result that proved the
> fix.
>
> Do not start Phase 4 from this draft. Rename it `phase4.md` only after the
> Phase 3 gate passes and every placeholder is filled in.

You are continuing the smart cane consumer-readiness work. The master prompt
is `docs/consumer-readiness-plan.md`. Its ABSOLUTE RULE, engineering
principles and section 2 safety behaviour apply in full. The section 2 rules
"a vague but correct warning beats a specific wrong one", "no speech queue"
and "the ESP32 does the autonomous safety vibration" are requirements here,
not background. This prompt replaces only the master's Phase 4 section.

## How every step is recorded

`experiments/phase4/step4_N_<name>/`, same files as before. Tag
`known-good-phase-3` before the first change. Every change to
`cane_safety.ino` goes through the Step 1.1 firmware rollback procedure
(`baseline/README.md`), with the current build verified on the chip first.

**Never judge what the user hears while an SSH session is open or closing**
(fact 9). Run audio and fault tests from a script that logs locally, start it,
log out, and read the log afterwards.

## Preconditions

| Item | Evidence needed |
|---|---|
| Phase 1 gate: power, Hailo, both ToF, ESP32 watchdog and fault tests | *(gate)* |
| Phase 2 gate: the failure and disagreement table from Step 2.5, with what the user hears and feels in each case | *(Phase 2)*. Phase 4 implements that table. It does not reinvent it |
| Phase 2: ESP32 haptic fault pattern decided and tested | *(Phase 2)* |
| Phase 3 gate: chosen model, re-derived thresholds, one `PRIORITY` list, every class speakable | *(Phase 3)* |
| Phase 3: per-stage latency trace (Step 3.0) | *(Phase 3)*. Phase 4 extends it to decision, speech and audio |
| Audio hardware for the product decided or shortlisted | Adeel. Wired is the plan (MEMORY.md section 3). See fact 11 |

## Known facts and defects carried into Phase 4

1. **Decision logic lives in three places** *(code)*. Firmware: obstacle
   bands, ground watch, hazard pattern. `detect.py`: bearing, corridor,
   box-height distance, ranking. `speak_detect.py`: `resolve()`,
   `Confirmer`, `SensorWatch`, the speaker's drop and wait rules, the sync
   buzz. `detect.py` and `speak_detect.py` each have a `PRIORITY` list, and
   they disagree.

2. **The Pi can switch off or weaken the ESP32's safety vibration** *(code)*.
   In `updateMotor()`, `if (now < manualUntil) return;` runs before the
   ground-hazard pattern. Any `B<duty>,<ms>` from the Pi wins for up to
   5,000 ms, including `B0,5000`, which is 5 s of silence. `A0` sets
   `autoBuzz = false`, which stops obstacle buzzing and the hazard pattern
   until the ESP32 resets. The serial protocol has no check on who sends
   what. This breaks the master's architecture rule that the ESP32 is an
   independent safety layer. Step 1.5 ("motor fail-state") should fix it. If
   it does not, Step 4.2 must.

3. **The sync buzz replaces the ESP32's own pattern** *(code)*. When a
   sentence starts, the Pi sends `B100,400`, `B85,250` or `B60,150` by
   distance band. During that window the ESP32's obstacle pattern is
   suppressed (fact 2). A "far" sync buzz (60 %, 150 ms) can briefly replace
   a "close" continuous 100 % buzz.

4. **Urgent speech cannot interrupt** *(code)*. A ground hazard
   (`urgent=True`) waits up to 2 s for the current sentence to finish, then
   is dropped with `(urgent dropped, speech stuck)`. `paplay` is never
   stopped. An ordinary report that arrives while speech plays is dropped (by
   design, no queue). So "Careful, drop ahead" can start up to 2 s late or
   not at all.

5. **The speech chain** *(code)*. Decision, then `pactl info` (a subprocess,
   to check the sink), then `espeak-ng` writes `/tmp/cane_speech.wav`
   (timeout 10 s), then the sync buzz, then `paplay` (timeout 15 s), then
   PulseAudio, then Bluetooth A2DP. No step is timed. The plan's "100 to
   300 ms after decision" and "Bluetooth adds 100 to 200 ms" are estimates.

6. **Fault warnings exist only as speech** *(code)*. "Warning, distance
   sensors not responding" after 2 s of ESP32 silence, repeated every 30 s.
   "Warning, ground / obstacle sensor not working" after 3 s of `ok=0`,
   repeated every 60 s. Nothing at all for dead vision (1 h 46 min on 2 Oct,
   *Step 1.1 F1*). A dead audio path is logged as `AUDIO DEAD` and cannot be
   announced by audio. The ESP32 has no haptic fault signal *(Phase 2 may
   change this)*.

7. **A hung vision process is invisible** *(code, Step 1.1)*.
   `speak_detect.py` reads `detect.py`'s stdout. If `detect.py` exits, the
   loop ends, the service exits and systemd restarts it after 5 s (40
   "starting vision" lines in one boot). If `detect.py` hangs inside
   `hailo.run`, nothing happens. Step 1.2 added a CPU-time proxy to a test
   tool, not to the product.

8. **The ESP32 link does not recover from a USB loss** *(Step 1.2, G4)*. The
   reader thread never reopens the port. After the 21:26 boot it stayed
   "ESP32 LINK SILENT" for 80 s while the ESP32 was sending, until the
   service restarted. Opening the port also delivers a burst of stale
   duplicate lines *(Step 1.1 F5, Step 1.2 G5)*. Owner Step 1.5. Confirm the
   fix *(gate)*.

9. **Every SSH logout restarts PulseAudio** *(Step 1.1 F2)*. 12 of 12 since
   19:47 on 2 Oct, 134 starts against 355 SSH sessions in one boot, 89
   `AUDIO DEAD` events healed in about 2 s each. The unit runs in
   `session.slice` *(Pi)*. Mechanism not proven. In the field there is no
   SSH, but it shows that the audio stack hangs off a login session.

10. **The earbuds do not always come back** *(Step 1.1, Step 1.2 G6)*.
    `br-connection-profile-unavailable` at 20:00, 20:02, 21:02 and 21:26 on
    2 Oct. They are now bonded with a stored link key. `AlwaysPairable =
    true` and `PairableTimeout = 0` were set in `/etc/bluetooth/main.conf`
    to get bonding working *(Pi)*. That leaves the cane open to pairing
    requests (security, Step 5.10).

11. **An I2S DAC on the Pi is blocked by the AI HAT+** *(MEMORY.md 2 Oct
    step 3b)*. The HAT has no pass-through pins, so the PCM5102A plan needs
    the 40-pin header the HAT covers. On this hardware the practical wired
    paths are a USB audio adapter, or a DAC on a stacking header if one fits
    under the Active Cooler. The Pi 5 has no 3.5 mm jack.

12. **Logs do not survive a power cut** *(Pi, Step 1.2 G7)*. `/var/log` is a
    128 MB log2ram tmpfs, synced to the SD card daily and at clean shutdown.
    The journal was set to `Storage=persistent` with `SystemMaxUse=200M`,
    which is bigger than the tmpfs. A brownout loses the logs that explain
    it. Owner Step 1.2 Part B. Confirm the fix *(gate)*.

13. **No buttons exist yet** *(code)*. MEMORY.md section 4.2 plans two
    shape-coded buttons on the ESP32 (GPIO 33 and 32). The firmware reads
    none. Acknowledging a fault, changing verbosity or asking for a scene
    description has no input today.

14. **English only** *(code)*. `espeak-ng -v en-us -s 165`. The project goal
    includes Indian languages (MEMORY.md section 1).

15. **Measured timing to build on** *(Step 1.1)*. ESP32 report 19.87 Hz,
    interval P50 50.0 ms, P99 60.0 ms. ESP32 reset to first report 858 ms,
    about 400 ms of it the blocking "alive" buzz. Pi boot 7.0 to 11.1 s.

---

## STEP 4.1: one deterministic decision engine

Build the state machine the master asks for:

```text
NORMAL  WARNING  CRITICAL  GROUND_HAZARD
SENSOR_FAULT  VISION_FAULT  AUDIO_FAULT  ESP32_FAULT  POWER_FAULT  RECOVERY
```

- Move every Pi-side decision from fact 1 into one module with one
  priority list. `detect.py` reports facts (class, score, box, timestamp). It
  decides nothing.
- Write down which states the ESP32 owns. The ESP32 keeps its own reflex
  state machine and must behave correctly with the Pi absent.
- Every transition is logged with a monotonic timestamp and its inputs.
- Build an offline replay harness: feed recorded traces from Phases 2 and 3
  (ToF, IMU, detections) into the engine on the laptop and compare its
  output with an expected table. Same input, same output, every time.

Pass: replay of all Phase 2 and 3 traces gives identical decisions on 3 runs,
and every state is reached by at least one recorded or synthetic trace.

## STEP 4.2: separate semantic detection from safety detection

Camera says what it is. Forward ToF says how close something is straight
ahead. IMU says how the cane moves. Ground ToF says whether the ground
changed. The camera is not the only safety mechanism, ToF is not a semantic
detector, speech is not the primary emergency channel, and vibration stays
fast and local.

Concrete requirements from the code:

- **The Pi must not be able to silence or weaken an ESP32 safety pattern**
  (facts 2 and 3). Rule to implement and test: the motor output is the
  stronger of the ESP32's own pattern and the Pi's request, never the Pi's
  request alone. `A0` is removed from production firmware or limited to a
  diagnostic mode that times out and announces itself.
- Test with the Pi sending `B0,5000` and `A0` while an obstacle sits at
  30 cm and while a drop fires. The ESP32 pattern must not change.
- Measure obstacle to motor-on with a logged GPIO edge and an external
  reference (a target dropped into the beam, or a light gate), not by feel.
  Target under 100 ms. Today's 50 to 90 ms is an estimate.

## STEP 4.3: priority engine

Levels as in the master:

```text
5  immediate drop or critical hazard
4  very close frontal obstacle
3  near obstacle
2  named useful object
1  information
```

New requirement: **level 5 and 4 pre-empt speech already playing** (fact 4).
Stop the current playback and start the warning, or play warnings on a path
that does not wait for the speech lock. Measure "hazard event to warning
audible" with speech in progress, 20 trials.

Test the master's combinations (person + pothole, car + kerb, wall +
speech, object + sensor failure, drop during an announcement, several
obstacles). The higher level must win every time.

## STEP 4.4: speech latency

Benchmark espeak-ng, Piper, pre-recorded clips and a hybrid. Measure
**decision to sound at the ear**, not text to synthesis:

- Timestamps from the Step 4.1 decision log.
- Sound onset from a microphone at the earpiece or a loopback capture,
  aligned to the same clock with a logged sync click. No stopwatch figures.
- Report P50, P95 and P99 per engine and per audio path (Bluetooth now,
  wired candidates from Step 4.5).
- Include the cost of the `pactl info` check before every phrase (fact 5).

Pre-render the critical vocabulary:

```text
stop  careful  drop ahead  step up  obstacle ahead
sensor fault  vision fault  battery low  audio check
```

Decide the language scope (fact 14) before rendering. Each added language
multiplies the clips and the comprehension tests in Step 5.7.

Check Piper's memory and CPU against the Phase 3 budget. The 2 GB Pi runs
the model too.

## STEP 4.5: remove Bluetooth as a single point of failure

Reproduce the known failures first, with no SSH session open (fact 9):
PulseAudio restart, earbud power cycle, earbuds in their case,
`br-connection-profile-unavailable` after a service restart (fact 10), sleep
and wake, range, Pi reboot.

Find out why a login session can restart the audio server. A product audio
path must not depend on a user session. Evaluate a system-level audio service
or direct ALSA output for the wired path.

Then compare against a USB audio adapter with a wired bone-conduction
headset, and an I2S DAC only if it can physically connect (fact 11). Measure
failures per hour, recovery time and decision-to-sound latency for each.
Choose on those numbers.

## STEP 4.6: audio and haptic redundancy

Vibration is immediate, speech explains. A critical warning must still get
through when audio is down, Bluetooth is gone, Piper crashes, the CPU is
overloaded or Pi vision has crashed.

- The ESP32 fault pattern from Phase 2 covers sensor faults with the Pi
  down.
- **Audio failure must be signalled by vibration**, because it cannot be
  spoken (fact 6). Define the pattern and test that users tell it apart
  (Step 5.7).
- Vision failure must be signalled by speech and by vibration.

## STEP 4.7: inject every fault on purpose

The master's list, plus the faults this project has already had:

```text
camera unplugged                 Hailo unavailable
Hailo alive but not inferring (the 2 Oct fault, F1)
Pi process killed                speak_detect.py hung
ESP32 unplugged                  ESP32 USB re-enumerated (fact 8)
forward ToF disconnected         downward ToF disconnected
IMU disconnected                 audio disconnected
PulseAudio restarted             earbuds not reconnecting (fact 10)
Bluetooth sink fell back to auto_null
Pi sends B0,5000 or A0 during a hazard (fact 2)
serial corruption                stale or duplicate serial data (F5)
sensor stale data                invalid sensor values
disk full                        /var/log tmpfs full (fact 12)
low battery                      under-voltage (old UPS feed, supervised)
high CPU load                    thermal throttling
no network, clock not synced
power cut, then: are the logs from before the cut there? (fact 12)
```

For each: detected or not, time to detect, what the user hears, what the user
feels, backup behaviour, automatic recovery, recovery time. At least 5 trials
each. Read results from the local log, never live over SSH.

## STEP 4.8: health monitor

Create `health_monitor` covering camera, Hailo, ESP32, forward ToF, downward
ToF, IMU, audio, storage, CPU, temperature, power and service state. Each
reports OK, DEGRADED, FAILED or RECOVERING.

Liveness must test the function, not the process:

- vision: the inference counter increases and frame timestamps are fresh. A
  CPU-time proxy does not count (fact 7).
- ESP32: age and sequence of the last `D` line, after the stale burst is
  dropped.
- audio: the sink is real **and** the last playback finished. A null sink
  returns success, which is how this project lost audio silently on 19 Sept.
- power: kernel under-voltage count and `vcgencmd get_throttled` bits, read
  every second.
- storage: free space on `/` and on the `/var/log` tmpfs.

Run the monitor under systemd with `WatchdogSec` and `sd_notify`, so a hung
monitor is itself detected.

### PHASE 4 GATE

Do not continue to Phase 5 until:

* every Step 4.7 fault is detected, and the user is told within a time
  written in `test_plan.md` before testing, through a channel that still
  works in that fault
* no silent failure remains in the Step 4.7 matrix
* the Pi cannot silence or weaken an ESP32 safety pattern (tested, fact 2)
* level 5 and 4 warnings pre-empt speech, with measured latency
* decision to sound P50, P95 and P99 are measured for the critical vocabulary
  on the chosen audio path
* obstacle to motor-on is measured against an external reference
* the audio path chosen for the product does not depend on a login session
* logs survive a power cut (fact 12), tested by cutting power

After the gate, write `docs/phase-prompts/phase5.md` from
`phase5_DRAFT.md`, revised with Phase 4's measurements.
