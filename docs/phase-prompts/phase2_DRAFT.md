# PHASE 2 PROMPT (DRAFT): sensor validation, IMU and real-world geometry

> **DRAFT, written 2 Oct 2026 before the Phase 1 gate, at Adeel's request.**
> Revised the same day after a check against `cane_safety.ino`,
> `speak_detect.py`, `detect.py` and the Step 1.1 records.
> Only Step 1.1 of Phase 1 is done. Steps 1.2 to 1.5 (power, power
> measurement, ToF 2 repair, ESP32 safety layer) are still open. Every fact
> below marked *(Step 1.1)* was measured. Facts marked *(code)* were read from
> the firmware or Pi code on 2 Oct and must be rechecked if Phase 1 changes
> that code. Everything marked *(gate)* must be replaced with the Phase 1
> gate's numbers before this prompt is used. Do not start Phase 2 from this
> draft: rename it `phase2.md` only after the Phase 1 gate passes and every
> *(gate)* item is filled in.

You are continuing the smart cane consumer-readiness work. The master prompt
is `docs/consumer-readiness-plan.md`. Its ABSOLUTE RULE, engineering
principles and section 2 safety behaviour still apply in full. This prompt
replaces only the master's Phase 2 section, revised with what Phase 1
measured.

## How every step is recorded

Same as Phase 1. One folder per step, `experiments/phase2/step2_N_<name>/`,
holding `README.md`, `test_plan.md`, `results.json`, `raw_results.csv`,
`terminal_output.txt`, `before/`, `after/`, `failure_log.md`. Run
`code/tools/snapshot_pi.sh` before and after every step. Append every session
to section 14 of `MEMORY.md`. Never start the next step until the current one
is tested, measured and recorded.

Write every pass limit into `test_plan.md` before the first measurement. A
limit chosen after seeing the data does not count.

## Preconditions: the Phase 1 gate

Phase 2 may start only when all of these hold. Fill in the evidence.

| Gate item | Status on 2 Oct 2026 | Evidence needed |
|---|---|---|
| Power is stable | **Open.** UPS into the 5V header pin sags. 19 under-voltage events and a Hailo outage on 2 Oct. EXT5V dipped to 4.769 V under Hailo load *(Step 1.1)* | 30 min, 60 min and 2 h load runs on the 5 V / 5 A USB-C supply with 0 under-voltage events *(gate)* |
| Hailo stays connected | Restored by a power cycle: 58.17 FPS, 13.14 ms *(Step 1.1)* | 0 disconnects across the Step 1.2 runs *(gate)* |
| ToF 1 stable | 1,152 samples, 0 dropouts, mean 90.3 mm, stdev 1.04 mm, bench only *(Step 1.1)* | 1 h continuous ranging *(gate)* |
| ToF 2 stable | **Open.** Not on its bus at all *(Step 1.1)* | rewired, 1 h continuous ranging, wire-movement and motor tests *(gate)* |
| ESP32 survives fault tests, watchdog verified | **Open** | Step 1.5 results *(gate)* |
| Rollback available | Done: git tag, ESP32 firmware, config tarball, SD image *(Step 1.1)* | refresh the SD image after Phase 1 changes, and keep one copy off the laptop |
| Battery runtime known | **Open** | Step 1.3 power budget *(gate)*. Outdoor steps below need the cane untethered |

## Known facts and defects carried into Phase 2

These change how Phase 2 must measure. Do not rediscover them.

1. **Camera field of view is narrower than 120 degrees, by an unknown
   amount** *(Step 1.1)*. Picamera2 selects sensor mode 1536x864, a centre
   crop (768,432,3072,1728) covering 2/3 of the sensor width. `detect.py`
   still passes `--hfov 120`, so every spoken bearing is wrong. The figures
   "about 98 degrees" and "the ±10 degree corridor is really about ±6.7
   degrees" are **estimates**. They assume the 120 degree rating is
   horizontal across the full sensor and that the lens is rectilinear.
   Neither is confirmed. `detect.py` itself notes the M12 lens has real
   barrel distortion. If the vendor's 120 is diagonal, the crop is narrower
   still (roughly 80 degrees and ±4.8 degrees). The 16:9 frame is squeezed
   into 640x640, 1.78x horizontally. Measure and fix in Step 2.2.
2. **Vision can die silently** *(Step 1.1, F1)*. After under-voltage the Hailo
   answered `identify` but ran no inference for 1 h 46 min. The service stayed
   `active`, and the cane gave no warning. Unless Phase 1 adds a vision
   watchdog, any Phase 2 field session can run blind without anyone knowing.
   Before each field session, confirm vision is alive (report lines arriving)
   and log it.
3. **"Nothing in range" sets off the drop alarm, and it has several causes**
   *(code)*. Firmware: `drop = (mm < 0) || (mm > baseline + DROP_MM)`. The
   VL53L0X returns 8190/8191 (stored as -1) when it gets no usable return.
   That happens for a real deep drop (drain, stair edge), but also for sun
   saturation, a dark or shiny surface, or a steep angle to the ground. All
   of these produce the same "drop" alarm. A sensor that **stops answering**
   is different. `watchGround()` only runs when `ok` is true and a fresh
   reading arrived, so a dead sensor never raises a drop alarm. After 300 ms
   (`STALE_MS`) the ESP32 sets `ok=0` and sends an `E` line. The Pi then
   says "Warning, ground sensor not working" once `ok=0` has lasted more than
   3 s, repeated every 60 s (`speak_detect.py`). The ESP32 has **no haptic
   fault signal of its own**. If the Pi is dead or frozen, or the earbuds are
   disconnected, a dead ground sensor gives the user nothing. Steps 2.4 and
   2.5 must deal with both problems.
4. **A long hazard switches ground watching off** *(code)*. After
   `RELEARN_MS = 2000` off-band, the firmware throws the baseline away and
   relearns from the next 10 **valid** readings. Invalid readings are skipped
   while learning. Three consequences:
   - A user who stops at a kerb or stair edge for 2 s stops being warned
     about it.
   - If that drop reads as "nothing in range", the relearn never completes.
     Ground watching stays off, with no hazard and no fault warning, until
     valid readings come back.
   - Each relearn leaves a blind window of at least 10 valid readings (about
     330 ms at the 33 ms timing budget) in which no ground hazard can fire.

   Also, a hazard fires once, when the streak reaches `CONFIRM_READS`. It is
   not repeated while the hazard lasts, and drop and step share the 2.5 s
   holdoff. Test all of this in Step 2.3.
5. **Current ground thresholds are first guesses.** `DROP_MM = 150`,
   `STEP_MM = 120`, `CONFIRM_READS = 2` on top of a median of 3,
   `BASE_ALPHA = 0.05`, `HAZARD_HOLDOFF_MS = 2500`, `STALE_MS = 300`. The
   firmware comment says so.
6. **The ESP32 report is filtered and resampled** *(Step 1.1, code)*. The
   `D` line to the Pi runs at 19.87 Hz, not 20. Interval P50 50.0 ms, P99
   60.0 ms, max 60.1 ms *(Step 1.1)*. Each `D` line carries the
   **median of the last 3 readings**, not a raw reading. Both sensors run
   with a 33 ms timing budget, so they produce about 30 readings a second
   *(code, not yet measured)*. The 20 Hz report repeats some readings and
   skips others. Reads that fail (`last_status != 0`, timeout) are dropped
   without any trace. Sample-count and latency budgets for the Pi side use
   the 19.87 Hz figures. Sensor statistics must not be computed from `D`
   lines (see Step 2.1).
7. **The two ToF sensors run in different modes** *(code)*. The forward
   sensor runs in long-range mode (signal limit 0.1 MCPS, VCSEL 18/14),
   about 2 m indoors and much less in sun. The down sensor runs in default
   mode, about 1.2 m. Characterize each sensor in the mode it actually runs.
   If Step 2.4 shows the down sensor needs more range, changing its mode is
   a firmware change and must be tested as one.
8. **Opening the serial port delivered 2,676 duplicate stale readings in
   90 ms** *(Step 1.1, F5, owned by Step 1.5)*. A Phase 2 data logger must
   discard them, or the dataset starts with fake data. Confirm the Step 1.5
   fix *(gate)*.
9. **The Pi's clock is probably not trustworthy at boot.** The SD image shows
   the root filesystem's last mount (the 2 Oct 18:04 boot) recorded as
   13:25 UTC (16:25 local), about 1 h 40 min early. The `/dev/i2c-*` nodes
   from that boot carry the same 16:25 time. That points to a stale clock
   until network sync. Confirm on the next boot. Outdoors with no Wi-Fi it
   may never sync. Log `time.monotonic()` plus the NTP sync state, and never
   align sensors by wall clock alone.
10. **Every SSH logout restarts PulseAudio** *(Step 1.1, F2)*. Never judge
    what the user hears while an SSH session is open or closing. Use a local
    log, not live SSH, during audio and failure tests.
11. **The earbuds do not always reconnect** after a service restart
    (`br-connection-profile-unavailable`, 2 Oct 21:02). Check `Connected: yes`
    before any test that depends on speech.
12. **Boot time varies between 7.0 s and 11.1 s** *(Step 1.1, Step 1.2)*.
    11.1 s was on a boot with repeated under-voltage. Cause unknown. Recheck
    on the new supply *(gate)*. Record boot time in every snapshot.
13. **I2C layout on the ESP32** *(code)*, using the firmware's own names:
    bus 0 (`Wire`) SDA 21 / SCL 22 for ToF 1, XSHUT 26. Bus 1 (`Wire1`)
    SDA 18 / SCL 19 for ToF 2, XSHUT 27. Both at 400 kHz, both sensors at
    0x29. Motor on GPIO 13. Sensors moved to the ESP32 because wiring to the
    Pi kept ripping off.

---

## STEP 2.1: characterize both ToF sensors

Do not rely on the old 92.4 mm bench figure or the Step 1.1 mean of 90.3 mm.
Neither was checked against a true distance.

### First: a raw logging mode (fact 6)

The `D` line cannot be used for characterization. Its median hides single
invalid readings, its resampling repeats or skips readings, and failed reads
leave no trace. Standard deviation, invalid rate and dropout rate computed
from it would all be too low.

Add a raw logging mode to the firmware, switched by a serial command and off
by default. In this mode the ESP32 prints one line per sensor read attempt:

```text
sensor id, per-sensor sequence number, ESP32 millis,
raw mm (before the median), VL53L0X range status register,
I2C status, timeout flag
```

Rules:

- It must not change the safety logic, thresholds or `D` line when off.
  Prove that with a before/after `D` line comparison and the Step 1.5 fault
  tests.
- Flash it using the Step 1.1 rollback procedure, with the firmware backup
  verified first.
- Measure the real reading rate of each sensor from the sequence numbers.
  The ~30 Hz figure is from the config, not measured.

Definitions, fixed before measuring:

- **invalid reading**: the sensor answered but gave no usable range (8190/
  8191, or a non-zero range status). Record which status.
- **dropout**: a read attempt that failed (I2C error, timeout), or an
  expected reading that never arrived (a sequence gap or a gap longer than
  2x the measured reading interval).

### Forward sensor (ToF 1, long-range mode)

Measure true distance with a reference (tape measure or laser rangefinder,
recorded with its own error) at:

```text
10 cm  20 cm  30 cm  40 cm  50 cm  75 cm  1 m  1.25 m  1.5 m  1.75 m  2 m
```

using these targets:

```text
white wall
grey object
dark object
black object
person/clothing
metallic surface
glass
irregular object
```

under these conditions:

```text
indoor normal lighting
bright indoor lighting
shade
outdoor
bright daylight
sun-facing
```

For each cell calculate mean, median, standard deviation, absolute error,
relative error, invalid-reading rate and dropout rate from raw readings. Use
at least 600 raw read attempts per cell (about 20 s at 30 Hz, to be confirmed
by the measured rate). Also compute the same statistics after a median of 3,
so the effect of the filter the cane actually uses is visible.

The full grid is 11 x 8 x 6 = 528 cells, about 4.4 h of recording before
setup time. To keep it doable:

- Write the "usable" criterion into `test_plan.md` before measuring. Starting
  point: invalid rate at most 5 % and median absolute error at most the
  larger of 30 mm or 5 %.
- Pruning rule: once a target and condition pair fails the usable criterion
  at two consecutive distances, skip the further distances for that pair and
  record them as "beyond usable range". Always measure 2 m for white wall
  and black object in every condition, so the table has its two extremes.

### Down sensor (ToF 2, default mode)

Characterize ToF 2 once Step 1.4 has repaired it, with the same raw logging
and the same statistics, but for its real job:

- Mount it on the cane at its real angle, or a jig that copies it. Record the
  angle.
- Distances along its beam: 5 cm steps from the closest it will be in use to
  the point where invalid readings exceed 50 %. Find that point. It is the
  start of "nothing in range", which fact 3 turns into a drop alarm.
- Surfaces: indoor floor, tiles, smooth pavement, rough pavement, asphalt,
  grass, wet pavement, a dark mat, a shiny or wet floor.
- Lighting: indoor, shade, bright daylight, sun on the surface.
- Angles: the mounting angle, and that angle ±15 degrees, to cover how the
  cane is held.

Pass: a full table for both sensors from raw readings, the measured reading
rate of each, and an explicit usable-range statement per condition. For the
down sensor, also the distance, surface and lighting at which it starts
returning "nothing in range" on ground that is really there.

---

## STEP 2.2: add an IMU, and fix camera geometry

### IMU selection

Evaluate at least MPU6050 and ICM-42688. Compare noise, sampling rate,
library reliability on the ESP32 Arduino core 3.3.x, power, availability
(the MPU6050 is end-of-life and widely cloned, so check what you can actually
buy), temperature stability, drift, integration difficulty, size and cost.
Do not pick a part because it is popular.

Mount it on the ESP32, not the Pi. Consider both ways to connect it:

- **SPI** (ICM-42688 supports it, MPU6050 does not). This keeps both ToF I2C
  buses untouched.
- **Sharing an I2C bus** (bus 0 or bus 1, fact 13). Neither candidate's
  address (0x68/0x69) clashes with the VL53L0X at 0x29.

Decide by measured effect on ToF read timing, using the raw logging mode from
Step 2.1. The ToF reading rate and the ESP32 report rate (about 20 Hz) must
not drop, and no new gaps may appear.

### What the IMU must do

Forward camera:

```text
estimate roll and pitch
determine whether the camera is tilted
```

Downward ToF:

```text
estimate cane angle
estimate sensor angle
estimate walking swing
```

The IMU must help tell a real ground discontinuity from normal cane movement.

### Camera geometry (new in this revision)

1. Find out whether the vendor's 120 degree rating is horizontal or diagonal,
   and record the source. Then measure the real horizontal and vertical field
   of view of the pipeline's actual sensor mode, with a target of known width
   at a known distance. The 98 degree figure is an estimate (fact 1).
2. Decide on the sensor mode: keep the 1536x864 crop (narrower, faster) or
   use the full 2304x1296 mode (wider, 56 fps max). Measure the effect on
   frame interval and inference.
3. Measure the lens distortion. A single `--hfov` value in the straight-lens
   `bearing()` formula cannot be right everywhere on a barrel-distorted lens.
   Either calibrate the lens (checkerboard, OpenCV camera calibration) and
   undistort the box centre before computing the bearing, or build a measured
   pixel-to-angle lookup table. Record which and why.
4. Correct the bearing and the corridor so that "ahead" means what it says.
   Measure bearing error at 5 known angles: 0, about ±20 degrees, and close
   to each edge of the field of view.
5. Record the aspect squeeze (16:9 into 640x640) as an input to Phase 3.

Pass: IMU integrated with measured noise and drift. Camera FOV and distortion
measured. Bearing error within ±5 degrees at all 5 angles, unless
`test_plan.md` argues for a different limit before testing. Objects exactly
at the corridor edge classified as left, ahead or right as intended.

---

## STEP 2.3: build ground-profile calibration

Do not keep `DROP_MM = 150` and `STEP_MM = 120` just because they exist.

Collect real data on:

```text
smooth pavement   rough pavement   sidewalk   stairs   kerb   ramp
pothole   drain   road edge   grass   tiles   indoor floor   uneven pavement
```

Record, synchronized by the ESP32's own millisecond clock and the Pi's
monotonic clock (not wall time, see fact 9):

```text
timestamp
forward ToF (raw and median)
downward ToF (raw and median, with range status)
IMU
camera frame timestamp
ground classification
actual hazard type
cane angle
walking speed
```

Say how walking speed and the actual hazard type are measured (for example a
measured course length and a stopwatch, plus video or a labelled log). The
IMU alone is not a trusted walking-speed reference.

Build a ground-event dataset.

### Relearn behaviour (fact 4)

Stand at a kerb, a stair edge, and a drop deep enough to read "nothing in
range" (use the down sensor's limit from Step 2.1). Hold each for 1, 2, 3 and
5 s, 5 times each. For every trial record:

- how many hazard alerts fired (buzz and speech)
- whether the baseline was relearned, and to what value
- whether ground watching came back, and after how long
- for the out-of-range drop: whether ground watching stayed off, and for how
  long the user had no ground protection and no fault warning
- the blind window after each relearn, from the raw log

Use a sighted tester for all of this. Kerb, stair and drop trials need a
spotter, and a real edge is never approached by someone relying on the cane.

Pass: dataset covering every surface, labelled, with the stale-burst filter
confirmed. Relearn behaviour measured, with a written decision on whether it
is safe. "Ground watching off with no warning" is not acceptable for a
consumer product. Either fix it or justify it in writing.

---

## STEP 2.4: determine minimum useful hazard sizes

Measure the real detection thresholds for:

```text
small step   large step   small drop   large drop
pothole   kerb   open drain   road edge
```

Measure minimum detectable depth, minimum detectable width, maximum reliable
detection distance, false alarm rate and miss rate.

Separately, take apart "nothing in range" (fact 3):

- How often does a real deep drop read as "nothing in range" rather than as
  a distance?
- How often does a working sensor read "nothing in range" on ground that is
  really there, per surface, lighting and cane angle? Use the Step 2.1 table.
- Which range status codes go with each cause? Can range status, the IMU
  angle and the recent history together separate "deep drop" from "sun",
  "dark or shiny surface" and "steep angle"?

The firmware must be able to tell these causes apart, as far as the data
allows, before Step 2.5. Where they cannot be told apart, the cane must stay
conservative (warn), and that must be recorded as a known limit.

Do not optimize for the number of detected events. Minimize dangerous misses
while keeping nuisance alarms under control.

---

## STEP 2.5: test sensor failure and disagreement

Create each case and define exactly what the user hears and feels:

```text
camera sees object, ToF sees nothing
camera sees nothing, ToF sees obstacle
ToF invalid, camera sees obstacle
ground sensor invalid, IMU valid
IMU invalid, ground sensor valid
both ToF invalid
ESP32 disconnected, Pi still running
Pi dead or frozen, ESP32 still running
down sensor stops answering, Pi and earbuds working
down sensor stops answering, Pi dead or earbuds disconnected
down sensor answers but returns only "nothing in range"
ground watching off after a relearn on an out-of-range drop (fact 4)
vision dead silently: Hailo identify OK, no inference (the real 2 Oct fault)
camera disconnected
earbuds disconnected
```

Philosophy:

```text
sensor disagreement           -> conservative obstacle warning
critical safety sensor failure -> explicit fault warning
```

A fault warning that only exists as speech is lost when the Pi or the
earbuds are down. Today a dead down sensor in that state gives no signal at
all (fact 3). Decide whether the ESP32 needs its own haptic fault pattern,
distinct from the obstacle and hazard patterns, and test it.

Reproduce "vision dead silently" on purpose (for example, stop inference
while the service keeps running). The user must get an explicit warning
within a stated time. On 2 Oct they got none for 1 h 46 min. Measure the
current time to the "ground sensor not working" warning as well (more than
3 s by design, plus speech).

Run every case at least 5 times. Judge audio from a local log, never over
SSH (fact 10).

### PHASE 2 GATE

Do not continue to Phase 3 until:

* ToF characterization exists for both sensors, from raw readings, against
  true distance
* the downward sensor is stable
* the IMU is integrated
* camera FOV, distortion and bearings are measured and corrected
* cane motion does not produce unacceptable false ground alarms
* real pavement tests have been performed
* the causes of "nothing in range" are separated as far as the data allows,
  and the remaining limits are recorded
* ground watching cannot be switched off without the user being told
* a dead safety sensor is signalled to the user even when the Pi or the
  earbuds are down
* sensor failure behaviour is deterministic, including silent vision death

After the gate, write `docs/phase-prompts/phase3.md` from the master Phase 3
section, revised with Phase 2's measurements.
