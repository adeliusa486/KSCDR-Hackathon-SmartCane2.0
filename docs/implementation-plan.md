# Implementation plan (from the 8 October 2026 review)

Every problem reported on 8 October, what caused it, what is already fixed, and what comes next. Each open item has a test that decides when it is done. Work goes in order: an item is closed only when its test passes on the cane.

## Problems reported, and their causes

| Reported | Cause found | Status |
|---|---|---|
| Detects only "person", not tables or chairs | Three causes stacked. (1) Picamera2's `RGB888` gave the model blue and red swapped. (2) The 16:9 frame was squeezed 1.78x into the square input. Together these cost 15 points of naming (40 % to 55 %). (3) Some furniture classes are weak in the model itself: desk recall 0.27, cabinet 0.09. Also: with the person always ranked first and one repeat timer for the whole sentence, other objects rarely got their turn | (1), (2) fixed. Per-object turns fixed. (3) open, item C2 |
| Says "right" when I am in front | (1) Directions are the camera's: someone facing the cane hears their own left called "right". (2) The code assumed a 120° view, the sensor mode gives 98.2°, so the "ahead" zone was only ±6.7° wide, about the middle 10 % of the picture. (3) The box centre decided, so a person filling half the frame counted as "right" | (2), (3) fixed: real FOV from the sensor, ±15° zone, and any box crossing the centre line is "ahead". (1) is how a cane must work, documented |
| ToF does not measure distance properly | The serial link from the ESP32 delivered nothing for whole sessions (3.5 h on 7 Oct, 10 h on 8 Oct), so every distance spoken was the camera's size word | Fixed: the port reopens after 3 s of silence and a missing ESP32 is retried. Verified: "chair ahead, 1.3 meters" from the ToF |
| Distances in centimetres | `spoken_distance()` said "60 centimetres" | Fixed: "0.6 meters", "1.2 meters". Camera estimates "about 2.5 meters" |
| ToF 2 does not catch potholes or drops | (1) No link, so no speech, and the ESP32's own pulse was too weak to feel. (2) If the ground is out of range (aim too shallow, dark asphalt) the ground is never learned and nothing is ever reported, silently. (3) The thresholds are guesses never tuned on a walk | (1) fixed. (2) fixed: spoken warning "Ground sensor cannot see the ground" after 20 s. (3) open, item B4 |
| Vibration nearly negligible | Far obstacles buzzed 100 ms at 60 %, the speech buzz 150 ms at 60 %: a coin motor barely spins up in that time. Motor placement inside the housing absorbs the rest | Firmware 2026-10-08: 40 ms full-power kick on every buzz, 80 to 100 % strength, 150 ms pulses. Still "very low" in the cane body, so firmware 2026-10-08c: every buzz at full power, 250 ms obstacle pulses, 700 ms ground pulse, speech buzz 300 to 500 ms. Hardware placement open, item B2 |
| Power bank: amber, red, off | The bank cannot hold 5 V through the boot peak of Pi + Hailo + camera | Explained in [power.md](power.md). Open, item B1 |
| Disk space | 425 GB of datasets on D:, 28 GB WSL and 15 GB of training caches on C: | Labels and models moved into this repository, data consolidated under `D:\smart cane 2.0` |

Other faults found during the review and fixed the same day: `detect.py` errors went to `/dev/null` (four boots on 7 Oct showed "vision stopped, exit 1" with no reason), "sensors not responding" was spoken at every start-up, identical phrases were spoken twice ("person right, close. person right, close"), the same object could be named twice by two classes (table and desk), the assistant's snapshot was not turned upright, and the dashboard was on by default at 73 % of a CPU core. Firmware 2026-10-08 also rejects readings the sensor flags as hardware or phase failures and adds offset calibration.

## B. Hardware and field work (needs the cane in hand)

### B1. Power that holds 5 V

1. Read the bank's label. If it has no USB-C PD output with 5V⎓3A, replace it.
2. Short USB-C to USB-C cable rated 3 A or 5 A, bank fully charged.
3. If it still dips: PD trigger at 9 V into a 5.1 V / 5 A buck converter, or a Pi 5 UPS board rated 5 A.
4. Measure the real draw with an inline USB-C power meter, to replace the runtime estimate.

**Pass:** cold boot on battery 5 times in a row, then 30 minutes with the service running and the cane moving: `vcgencmd get_throttled` stays `0x0`, `EXT5V_V` never below 4.9 V.

### B2. Vibration you can feel

1. Run the ladder `B60,150`, `B80,200`, `B100,300`, `B100,1000` (`python3 esp32_link.py --send B100,1000`) while holding the cane as when walking, and note the weakest one you feel every time.
2. Mount the motor directly against the inside wall of the grip, under the index finger or palm, with hot glue or foam tape. A motor floating inside the housing loses most of its feel.
3. If 100 % for 300 ms is still faint: a larger ERM (10 x 3 mm coin motors are the weakest kind), or the planned DRV2605L with an LRA, which gives sharp, distinct patterns.
4. Add a 100 to 470 µF capacitor across the motor module's supply, close to the module. Motor current spikes on the USB 5 V line are a candidate cause of the CP2102 stalls behind the dead serial link (item B8).

**Pass:** all four alert types (far, near, very close, ground drop) felt and told apart in 10 of 10 tries, while walking.

### B3. Forward ToF accuracy

1. With nothing within 2 m of the sensor, read `python3 esp32_link.py --send Q1 --seconds 5`. Anything under 300 mm means the beam is hitting the housing or the cane: open the window or move the sensor forward.
2. Calibrate against a white wall at exactly 500 mm: `--send C1,500`. Check at 1,000 mm. The offset is stored in the ESP32.
3. Check `S` for range-status counts after a walk. If weak-signal readings (status 4) are frequent, decide with that data whether to reject them too (`badStatus()` in the firmware).

**Pass:** within ±3 cm at 0.5 m and ±5 cm at 1.0 m on a white target, no phantom readings with nothing ahead.

### B4. Drop-off and pothole detection that works on a walk

The physics first: at the 110 cm mount and 40° grip the beam reaches the ground about 147 cm away with a spot about 65 cm across. A hole much smaller than the spot hardly changes the reading, and on dark asphalt 147 cm is near the VL53L0X's limit.

1. **Record before tuning.** Walk with `Q1` on and log everything (`tools/esp32_capture.py`) over: flat floor, a step down, a kerb up and down, a drain or pothole, and stairs going down. Mark the times.
2. **Build a replay tool**: a Python copy of `watchGround()` that runs on the recorded raw readings, so thresholds can be tried on the laptop instead of re-flashing for every change.
3. Tune `DROP_MM`, `STEP_MM`, `CONFIRM_READS`, `RELEARN_MS` and `BASE_ALPHA` on those recordings.
4. If the ground is often out of range, aim ToF 2 steeper (10° instead of 15° forward of the shaft) for a shorter, more reliable path.
5. **Add an IMU** (MPU6050 or ICM-42688 on the ESP32's I2C bus). With the cane's tilt known, the expected ground distance can be computed for every reading instead of learned, which removes most false alarms from swinging the cane and lets the camera picture be levelled.
6. The camera already names stairs (mAP50 0.60), potholes (0.50), open holes (0.82) and manholes (0.23). Fuse it: a camera drop-off class ahead plus a ToF 2 change within 1 s is a confirmed hazard.

**Pass:** 9 of 10 real drops and kerbs detected while walking normally, at most 1 false ground alarm per minute on flat ground.

### B5. Direction and camera aim

1. The cane held to walk gives an upright picture, so `--rotate 0` stays. Re-check with `tools/vision_probe.py --orient` if the camera is ever re-mounted.
2. Frames show a lot of floor and cut off the tops of chairs: tilt the camera 5 to 10° further up.
3. Walk past known objects at 1, 2 and 4 m on each side.

**Pass:** direction correct in 9 of 10 trials for objects at 1 to 4 m.

### B6. Motion blur and low light

Indoors the camera ran at 5 to 23 lux with exposure pinned at 66 ms, so every swing blurs the picture. Try `AeExposureMode` short (more gain, less blur) as an A/B on a walk, and a small white or IR LED next to the lens.

**Pass:** more named objects per minute of walking than the current setting, same false-name rate.

### B7. Wired audio

The earbuds dropped out many times per session (`AUDIO DEAD` in every log reviewed). Move to a USB audio adapter or the planned I2S DAC with a wired bone-conduction headset. This also removes 100 to 200 ms of Bluetooth latency.

**Pass:** zero `AUDIO DEAD` events in a 1-hour session.

### B8. Serial link root cause

The reopen fix keeps the cane working, but the CP2102 control-request timeouts have a cause. Candidates: motor noise on the USB 5 V line (item B2.4), a marginal USB cable, or the Pi's 600 mA USB limit on a weak supply. Watch the `ESP32 ... reopening the port` lines in the journal after each change.

**Pass:** zero reopens in a 1-hour session.

## C. Model work (laptop)

| Item | What | Pass |
|---|---|---|
| C1 | Recompile the HEF with letterboxed calibration images, matching what the cane now feeds the model | Named % on `hazard_eval.py --aspect 16:9 --fit letterbox` not lower than 55 % |
| C2 | More data for weak classes: desk (0.43), cabinet (0.23), curb (0.24), crosswalk (0.22), manhole (0.23), pole (0.32), door (0.44), shelf (0.20), fence (0.14), storm drain (0.14). Best source: photos from the cane's own camera at its own height in the places it will be used, labelled and added to merged_v2, then fine-tune v4 from v3 at a low learning rate | Each target class +0.10 mAP50, overall mAP50 not lower |
| C3 | Per-class naming thresholds from the precision curves instead of one 0.35 for all | Fewer wrong names at the same recall in `hazard_eval.py` |
| C4 | A simple tracker across frames (IoU matching) for stable directions and "person approaching" | Direction flips per minute halved on a recorded walk |
| C5 | Indian street classes (auto-rickshaw, cattle on roads, open drains) if the cane is used there | Field test |

## D. Towards a product

Enclosure CAD published with the repository, IP54 sealing, weight target near 150 g for the handle (WeWALK is 152 g), read-only root filesystem (overlayfs) so a power cut cannot corrupt the SD card, a waterproof power button on the Pi 5's J2 header, and testing with 10 to 20 blind users before adding features.
