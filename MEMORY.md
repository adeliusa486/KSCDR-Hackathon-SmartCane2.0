# MEMORY.md — Smart Cane / Assistive Navigation Project

Context file for the visually-impaired navigation device project.
Carry this into new chats so the assistant has full background.

---

## 1. Project goal

Build an affordable assistive navigation device for blind and visually impaired
users that provides:

- Offline object detection (target: 300+ objects)
- Offline Indian currency recognition
- Drop-off / pothole / open-drain detection
- Obstacle alerts via vibration and speech
- Scene description and voice assistant (offline where possible, cloud optional)
- Support for Indian languages
- No mandatory subscription
- Target mass-production price: ₹15,000–25,000

---

## 2. Hardware already purchased (prototype brain)

| # | Part | Job | Price |
|---|---|---|---|
| 1 | Raspberry Pi 5, 2GB | Main computer | ~$45 |
| 2 | AI HAT+ (Hailo-8L, 13 TOPS) | Runs YOLO | ~$87 |
| 3 | Active cooler for Pi 5 | Prevents throttling | ~$3 |
| 4 | High-endurance A2 microSD 32GB | Storage | ~$14 |
| 5 | Arducam B0310 — Sony **IMX708**, 4608×2592, 120°(H) M12 lens, manual focus | Camera | ~$53 |
| 6 | 2× **VL53L0X** ToF (already owned; earlier listed as VL53L1X, corrected 2 Oct 2026 by reading the chip ID) | Drop-off + forward detection | $0 |
| 7 | 6000mAh power bank | Power (~2.5h runtime) | owned |

**Decision:** keep the Pi + Hailo for the prototype. Move to a cheaper custom
board only after features are proven.

---

## 3. Remaining parts list

| # | Part | Job | Price |
|---|---|---|---|
| 1 | VL53L8CX ToF (forward, 8x8 zones) | Obstacle distance + direction | ~$22 |
| 2 | A02YYUW ultrasonic (UART, waterproof) | Glass / backup detection | ~$15 |
| 3 | DRV2605L + LRA vibration motor | Instant obstacle alert | ~$9 |
| 4 | PCM5102A I²S DAC | Audio output | ~$8 |
| 5 | Wired bone-conduction headset | Speech, low latency | ~$40 |
| 6 | 2× 12mm waterproof push buttons + shaped caps | Power / assistant | ~$4 |
| 7 | Capacitive rain sensor | Wet-condition warning | ~$7 |
| 8 | SHT31 humidity sensor (optional) | Enclosure leak detection | ~$5 |
| 9 | **ESP32-C3/S3 or RP2040** | Dedicated safety co-processor | ~$4 |
| 10 | **IMU (MPU6050 / ICM-42688)** | Tilt correction + fall detection | ~$3 |
| 11 | Breadboard + jumper wires | Prototyping | ~$8 |
| 12 | PETG/ASA filament | Enclosure | ~$25 |

Approx. remaining spend: **$140–180**

---

## 4. Key architecture decisions

### 4.1 Separate safety co-processor (important)
Put the ToF + ultrasonic + vibration loop on a **separate ESP32/RP2040**, not the Pi.

- Obstacle vibration works within ~1 second of power-on, while the Pi is still booting.
- Keeps working if the AI software crashes.
- Safety loop latency target: **under 50 ms**, camera and AI not involved.

### 4.2 Buttons
- 12mm waterproof momentary push buttons, panel mount, **shape-coded caps**
  (one flat round, one raised cross) — NOT braille text.
- Spaced at least 20 mm apart, fixed relative layout.

| Button | Shape | Function |
|---|---|---|
| Power / mode | Flat round | Long-press power, short-press cycle verbosity |
| Assistant | Raised cross | Short-press = describe scene, long-press = ask question |

### 4.3 Wiring
- **Shared I²C bus:** VL53L8CX, VL53L1X, DRV2605L, SHT31, IMU
  (reassign ToF addresses at boot — they share a default address).
- **Dedicated pins:** buttons, ultrasonic (UART), I²S audio.
- Pi 5 **J2 power-button connector** can be wired to the waterproof power button.

### 4.4 Fast boot on the Pi (OS cannot be skipped, only hidden)
- Raspberry Pi OS **Lite** (no desktop), disable unused services.
- **systemd service** auto-starts the Python app at boot, no login/screen.
- Boot to ready: **~8–15 s (estimate)**.
- Play a sound/vibration when ready.
- Models stay loaded after boot, so the assistant button responds instantly.
- Enable **PCIe Gen3** — Hailo runs roughly twice as fast as on Gen2.

---

## 5. Performance reference

| | Pi 5 + Hailo-8L | RK3588 board | CanMV K230 |
|---|---|---|---|
| Boot to ready (est.) | 8–15 s | 15–30 s | 2–5 s |
| YOLOv8n speed | fastest (~8–17 ms inference) | ~53 fps real-world | ~15–30 fps (estimate) |
| Offline small LLM | CPU only, very slow | yes (10–15 tok/s, 1.1B) | no |
| Board cost | ~$135 | ~$70–110 | ~$50 |

**End-to-end latency (all boards):** camera frame ~33 ms → NPU inference
10–60 ms → sentence building → speech start 100–300 ms.
**Total ~0.2–0.5 s.** Speech is the slowest step, not the AI.

### ToF sensor behaviour
- **VL53L8CX (forward):** up to ~4 m, 8×8 zones @ ~15 Hz, 4×4 @ ~60 Hz.
  Grid tells left / center / right.
- **VL53L1X (angled down):** learns baseline ground distance; a sudden longer
  reading = hole / step / drop-off. ~33 ms per reading.
- **Limits:** strong sunlight shortens ToF range; cane swing changes angle
  (IMU needed for tilt correction); glass and water can fool ToF — ultrasonic
  stays as backup.

---

## 6. Competitor research (verified)

### Torchit (India)
- **Saarthi cane:** sonar/ultrasonic only, **no camera, no AI**. Three ranges
  (indoor 2 ft, outdoor 4 ft, open 8 ft), vibration + sound modes, battery up
  to 30 days / 100 hours. That battery life confirms a tiny MCU, no AI chip.
  Estimated parts cost: **$3–6**.
- **Jyoti AI Glasses:** OCR multi-language, currency + colour recognition,
  obstacle ID, scene description. **Product page states "cloud-native" and
  built on large-language-model APIs** → scene description is most likely
  cloud-based, not offline. Only the *Jyoti AI Reader* is stated to work
  offline. Priced around ₹25,000 (~$280), not under $100.
- Sold bundled in the *Saksharta Kit* (Saarthi + Jyoti glasses + more).
- Exact chips are not published — would need a teardown or BIS/FCC filing.

### WeWALK Smart Cane 2
- Ultrasonic only (overhead obstacle detection), flashlight, phone navigation.
- £599, or £849 with AI assistant; AI is an **annual subscription (~£109)**.
- Handle weighs **152 g** — weight is the key design bar to beat.
- No camera-based object recognition.

### Glidance "Glide"
- Wheeled robot base with stereo-depth cameras; alerts for doors, stairs,
  elevators, curbs. **~$1,500** ($1,799 with subscription).

### Others to study
- Biped NOA, .lumen glasses (wearables with camera AI, expensive).
- Stanford "augmented cane" — motorized wheel at the cane tip that steers the user.

---

## 7. Our competitive advantages

1. **Offline camera AI in the device** — no phone, no internet, no subscription.
2. **Drop-off / pothole / open-drain detection** — critical on Indian roads,
   missed by ultrasonic-only canes.
3. **Indian currency + Indian languages offline.**
4. **Price:** ₹15,000–25,000 vs WeWALK's ~₹70,000+.
5. **No mandatory subscription** — cloud AI optional only.

| | WeWALK | Glide | Saarthi | Ours |
|---|---|---|---|---|
| Offline object recognition | No | Limited | No | Yes |
| Drop-off detection | No | Yes | No | Yes |
| Bus numbers / road crossing | No | No | No | Yes |
| Shared hazard map | No | No | No | Yes |
| Works on rough Indian roads | Yes | Weak | Yes | Yes |
| Subscription needed | For AI | Yes | No | No |

---

## 8. Chosen product concept

**Two-part system + shared hazard map.**

Rationale: a cane swings and points at the ground, so a cane-mounted camera
gets a shaky, low view. The "eyes" belong somewhere stable.

1. **Chest / shoulder clip — eyes and brain**
   - Camera, Pi + Hailo (later a custom board), battery.
   - Stable height, sees people, vehicles, signs, doors.
   - Keeps the cane light.
2. **Cane handle — reflexes**
   - ToF (down + forward), ultrasonic, IMU, vibration motor, ESP32.
   - Instant hazard alerts; **works standalone if the clip is not worn**.
   - Bluetooth link between the two parts.
3. **Crowdsourced hazard map — the moat**
   - Any user's device auto-saves GPS locations of potholes, open drains,
     broken steps.
   - Other users get advance warning: "Open drain in 20 metres, on your left."
   - Hardware can be copied; a map built by thousands of users cannot.

### Priority features
- Named obstacles in speech ("car ahead", "stairs down", "open drain") — not just beeps.
- Stair / curb / wet-surface warnings (ToF + IMU + rain sensor combined).
- **Bus number reading** via offline OCR — a major daily problem in India.
- **Road-crossing help:** signals, zebra crossings, "vehicle approaching from right".
- **Directional vibration** (left/right patterns), not just "stop".
- **Fall detection + SOS** with location to family.
- GPS navigation via phone app.
- Optional online mode for rich scene description and Q&A.
- Find-my-cane beeper, battery-level announcement.

---

## 9. Honest technical limits

- **No bare-metal MCU can run true offline scene description or an AI assistant.**
  Those need vision-language models with billions of parameters.
- Cheap devices fake it with **template sentences** built from object detection
  results ("a person ahead on the left, a door on the right"). This is
  acceptable and cheap, and should be the offline fallback.
- Real offline Q&A needs RK3588-class hardware at minimum, and is still slow.
- Standard YOLO knows 80 classes. Reaching 300+ requires training a custom
  model (Open Images has hundreds of classes) and converting it for the NPU.
- Indian currency detection requires a custom-trained model.

---

## 10. Roadmap

### Phase 1 — Prototype (now)
- Pi 5 + Hailo as the vision brain; ESP32 + IMU for the safety loop.
- Get all core features working reliably.

### Phase 2 — User testing
- **Test with 10–20 real blind users early** via NGOs, blind schools,
  NAB, Saksham.
- Ask: which three features would you pay for? Would you wear a chest clip?
  (Some users reject wearables — the cane must work alone.)
- Measure: outdoor detection accuracy, false-alarm rate, battery hours,
  handle weight, water resistance (target IP54+).

### Phase 3 — Productization
- Move the vision system to a **K230 or RK3588-class chip on a custom PCB**
  to cut cost and weight.
- Injection-molded enclosure designed for manufacturing.
- Certifications: BIS/CE for electronics, lithium battery safety testing.
- Consider patenting the specific combination (e.g. drop-off detection with
  IMU tilt correction) — check novelty with a patent attorney.

### Phase 4 — Funding and distribution
- Government **ADIP scheme** listing.
- CSR partnerships.
- Startup grants: BIRAC, Startup India, assistive-tech programs.

### Later / optional
- **Motorized wheel tip** (Stanford-style) that gently steers the user — folds
  like a normal cane, guides like a robot. Big differentiator over WeWALK.
- Full guide robot as a separate indoor product (malls, airports, hospitals).

---

## 11. Standing risks to watch

- **Weight and bulk** — users reject a heavy cane no matter how smart it is.
- **Boot time** — solved by the separate safety chip.
- **Safety liability** — steering or guidance errors near traffic are serious;
  keep the passive cane function always intact.
- **Battery runtime** — currently ~2.5 h on a 6000mAh bank; needs improvement
  for all-day use.
- Verify AI HAT+ variant (13 vs 26 TOPS) and that the power bank does 5V/3A+.

---

## 12. Working rules for this project

- **Everything done in any chat gets written into this MEMORY.md file**, in the
  folder `new smart cane 2.0`. New work goes under the Session log (section 14).
- Code lives in `code/`, step-by-step guides live in `docs/`.
- Prices in USD, retail target in INR.

---

## 13. Repository layout

```
new smart cane 2.0/
  MEMORY.md                         <- this file, the single source of truth
  docs/
    01-pi-ai-hat-camera-setup.md    <- step-by-step bring-up guide
    smart-cane-prompt.md            <- full-context prompt to paste into a new AI chat (2 Oct 2026)
  code/
    setup_pi.sh                     <- one-shot installer to run on the Pi
    check_hardware.py               <- verifies Hailo + camera are alive
    detect.py                       <- camera -> Hailo YOLO -> spoken-style output
    coco.txt                        <- 80 class labels for the stock YOLO models
    speak_detect.py                 <- detect.py -> speech + vibration (the service)
    smartcane.service               <- systemd user unit, autostart at boot
    haptics.py                      <- vibration motor patterns, PWM on GPIO18
    tof.py                          <- two VL53L0X, XSHUT GPIO23/24 -> 0x30/0x31
    training/                       <- dataset prep + training scripts (laptop)
    tools/                          <- measurement tools (2 Oct 2026, Phase 1):
                                       snapshot_pi.sh, esp32_capture.py,
                                       camera_probe.py, baseline_window.sh,
                                       esp32_backup.sh
  docs/consumer-readiness-plan.md   <- 5-phase master plan, verbatim (2 Oct 2026)
  docs/phase-prompts/               <- revised prompt for each next phase
  baseline/                         <- frozen pre-Phase-1 state + rollback steps
  experiments/phase1/...            <- one folder per step, report + raw data
  backups/                          <- NOT in git: Pi config tarball, SD image
```

The project is a git repository since 2 Oct 2026 (branch `main`). Tag
`consumer-baseline-before-phase1` marks the frozen baseline.

---

## 14. Session log

### 19 September 2026 — Step 1: Pi 5 + AI HAT+ + camera bring-up

**Decision:** bring the three purchased parts up together first (Pi 5, AI HAT+
with Hailo-8L, Arducam B0310) before touching any ToF or vibration hardware.
Reason: the vision path is the long pole, and the safety loop lives on a
separate MCU anyway, so the two can be built in parallel later.

**Software stack chosen for the Pi:**

| Layer | Choice | Why |
|---|---|---|
| OS | Raspberry Pi OS **Bookworm 64-bit** (Desktop while developing, Lite for the final build) | Hailo packages are built for 64-bit Bookworm |
| NPU driver + runtime | `hailo-all` apt package (PCIe driver, HailoRT, TAPPAS core, model zoo HEFs) | One package, matched versions, no manual compiling |
| Camera stack | `libcamera` / `rpicam-apps` + **Picamera2** | Native Pi 5 stack; Picamera2 ships a `Hailo` helper class |
| Model | `/usr/share/hailo-models/yolov8s_h8l.hef` (80 COCO classes) | Ships with `hailo-all`, good accuracy/speed balance on the 8L |
| Glue | Python 3 using **system site packages** (no plain venv, or a venv created with `--system-site-packages`) | `picamera2` and `hailo_platform` are apt packages, not on PyPI |

**Configuration facts recorded so they are not rediscovered:**

- PCIe Gen3 must be enabled by hand in `/boot/firmware/config.txt`:
  `dtparam=pciex1_gen=3`. Roughly doubles Hailo throughput. Technically out of
  spec, but it is the documented Raspberry Pi setting.
- The AI HAT+ uses **both the 40-pin GPIO header and the PCIe FPC ribbon** —
  GPIO for mechanical support and power, PCIe for data. It is not a PCIe-only
  board. Box contents: 4 threaded spacers, 4 long screws, 4 short screws, a GPIO
  stacking header, a ribbon cable. Mount order: Active Cooler, then spacers
  (long screws), then GPIO stacking header, then ribbon, then the HAT itself
  (short screws). Pi powered off throughout. A 5V/5A (25W) supply is strongly preferred.
  The 6000mAh bank may brown out under camera + NPU load at the same time —
  this is a live risk to test, not a solved problem.
- The Pi 5 has **two camera connectors (CAM0 and CAM1)** using the narrower
  22-pin FPC. Contacts face the board on the Pi end. Use CAM0.
- `rpicam-hello --list-cameras` is the single test for camera detection.

**Camera identified (was an open item, now closed):** the **Arducam B0310 is a
Sony IMX708**, 4608×2592, behind a **120°(H) M12 lens**, manual focus by turning
the lens barrel. It is the same sensor as the official Raspberry Pi Camera
Module 3. Consequences:

- **No `config.txt` edit is needed.** IMX708 is natively supported on Bookworm
  and `camera_auto_detect=1` finds it. The fallback, if ever needed, is
  `camera_auto_detect=0` plus `dtoverlay=imx708`.
- **The B0310 ships with both a 15-22pin and a 15-15pin cable**, so the Pi 5
  cable is already in the box. No adapter needs buying. (An earlier note in this
  file said an adapter was required — that was wrong and has been corrected.)
- **Focus is manual and must be set once, deliberately.** There is no autofocus
  motor on this M12 variant, so Picamera2's `AfMode` controls do not apply.
  Set focus outdoors on something 2–4 m away, the band that matters for walking,
  then lock it with a ring or a dab of paint so it cannot drift in the pocket.
- **The 120° lens changes how direction is computed.** See the note on bearings
  below.
- `check_hardware.py` now asserts `imx708` and warns loudly if it sees anything
  else, since a different lens would silently invalidate the direction output.
- `hailortcli fw-control identify` is the single test for the NPU, and it prints
  the device architecture, which confirms whether the board is the
  **13 TOPS (HAILO8L)** or **26 TOPS (HAILO8)** variant. That settles the open
  question in section 11.

**Detection output format decided:** the detector does not just print class
names. For each detection it computes a horizontal zone (**left / ahead /
right**) and a coarse distance proxy (**close / near / far**) from box height.
That gives sentences like "person ahead, close" with no extra sensor, using the
same sentence-template approach recorded in section 9 as the offline fallback.

**Direction is computed as a bearing in degrees, not as a fraction of frame
width.** This is a direct consequence of the 120° lens and is worth remembering,
because the naive version is wrong in a dangerous direction:

- A "middle quarter of the frame = ahead" rule spans about **±22.6°** on a 120°
  lens. That is wide enough to announce a car in the next lane as "ahead", which
  is exactly the false alarm that makes users switch a device off.
- `detect.py` therefore converts the box centre to an angle
  (`bearing()`, rectilinear `atan` model) and splits on `--corridor`, default
  **±10°**, which is roughly the middle 10% of the frame. Verified numerically:
  frame fraction 0.46 → −7.9° → "ahead"; 0.60 → +19.1° → "right".
- `--hfov` defaults to **120**. If the M12 lens is ever swapped, this must be
  changed or every direction call becomes wrong.
- The `atan` model ignores the real barrel distortion of a cheap 120° M12 lens,
  so edge bearings are optimistic. It does not matter for a three-way split, but
  it would matter if we ever announce precise angles.
- The wide lens also makes the box-height distance proxy **pessimistic**: at
  120° objects subtend fewer pixels, so they read as further away than they are.
  Another reason the real distance must come from the ToF sensor in step 2.

**Files written this session:** `docs/01-pi-ai-hat-camera-setup.md`,
`code/setup_pi.sh`, `code/check_hardware.py`, `code/detect.py`, `code/coco.txt`.

**Next steps once this hardware is confirmed working:**
1. Run `check_hardware.py` on the Pi, paste the output back, record the real NPU
   variant (HAILO8L vs HAILO8) in this file. The camera is already identified.
2. Measure actual FPS and end-to-end latency, compare against section 5.
3. Measure current draw and runtime on the 6000mAh bank under load.
4. Set and lock the manual focus, and confirm it stays sharp across 1–5 m. The
   120° M12 lens has a deep depth of field, so one setting should cover the
   whole walking range, but confirm it rather than assume it.
5. Tune `--corridor` on a real pavement. Default ±10°; widen if too much gets
   pushed to left/right, narrow if things in the next lane read as "ahead".
6. Then add the VL53L1X over I²C and fuse ToF distance with the vision output.

**Open items still outstanding:** AI HAT+ variant (13 vs 26 TOPS), real FPS,
real power draw, whether the 6000mAh bank browns out under load.

---

### 19 September 2026 — Step 1a: Pi 5 live, camera confirmed, boot time halved

**The Pi 5 is up and reachable over SSH** at `192.168.3.51`, user `pi`, using the
key `~/.ssh/pi_solver_key` already present on the Windows laptop. Verified from
the laptop, not assumed.

**No reflash was needed and none was done.** The card already carried exactly the
target stack, so an earlier plan to wipe and reinstall was abandoned as pure
waste. Recorded so it is not proposed again:

| | Found on the card | Target per this file |
|---|---|---|
| Model | Raspberry Pi 5 Model B Rev 1.1 | Pi 5 |
| OS | Debian 12 Bookworm | Bookworm |
| Arch | arm64 / aarch64 | 64-bit, mandatory for Hailo |
| Variant | Lite | Lite |
| Card | 29.7 GB, 24 GB free | 32 GB A2 |

Two facts worth keeping, because both caused confusion this session:

- **Raspberry Pi OS images are model-agnostic.** One image carries kernels and
  device trees for every Pi and selects at boot. A card flashed on any other Pi
  boots on the Pi 5 unchanged, provided it is 64-bit Bookworm.
- **A running system cannot erase the card it booted from.** Wiping an SD card
  always needs a second machine holding it, via a card reader or `rpiboot` in
  mass-storage-gadget mode. There is no SSH route to a reflash.

**Camera confirmed working, end to end.** `rpicam-hello --list-cameras` reports
`imx708 [4608x2592 10-bit RGGB]` on CAM0, and a real 2304x1296 JPEG was captured
with `rpicam-jpeg` and pulled back to the laptop. Ribbon orientation and CAM0
choice are correct. Available modes measured on this unit: 1536x864 @120fps,
2304x1296 @56fps, 4608x2592 @14.35fps.

**The test frame is badly out of focus.** Expected, since the M12 barrel has
never been set. Confirms the manual-focus task in the previous session's next
steps is real and still outstanding.

**AI HAT+ is NOT attached yet.** `lspci` shows only the BCM2712 bridge and the
RP1 south bridge. All six failures in `check_hardware.py` are Hailo-related and
are explained entirely by the absent board, not by any fault. The Active Cooler
has now arrived and is fitted. Idle temp 49.9 C, `get_throttled` 0x0.

**Assembly note carried forward:** the HAT was seated directly on the Pi's
built-in GPIO pins. With the Active Cooler now fitted the stack is taller, so
the four spacers and the GPIO stacking header must be used on reassembly. The
HAT reportedly has pass-through male pins on its top face, which if confirmed
means Pi GPIO stays reachable with the HAT installed. Verify before planning
sensor wiring against it.

**Boot time cut from 13.4 s to 5.9 s**, beating the 8-15 s estimate in section
4.4. Measured with `systemd-analyze` before and after.

| | Before | After |
|---|---|---|
| Kernel | 4.127 s | 2.646 s |
| Userspace | 9.296 s | 3.276 s |
| **Total** | **13.423 s** | **5.923 s** |

Disabled to get there: `NetworkManager-wait-online` (6.15 s on its own, the
single biggest win), `ModemManager`, `rpi-display-backlight`, `triggerhappy`,
`udisks2`. Kept on purpose: `log2ram` (logs to RAM, reduces SD wear, worth its
370 ms) and `hciuart` (Bluetooth, needed for the cane-to-clip link in section 8).

**1-2 second boot is not achievable on Linux and should stop being a goal for
the Pi.** Roughly 2.6 s of the remaining time is kernel and storage bring-up that
no distribution choice removes. This is the concrete justification for the
section 4.1 decision to put the safety loop on a separate ESP32/RP2040, which
wakes in about a second. Pothole and drop-off detection via ToF remains a
headline feature. The only open question is which chip the ToF hangs off, and
the answer is the ESP32, because a pothole warning that arrives 6 s after
power-on is worse than useless.

**Old project removed.** `pi-solver.service` disabled and its unit file deleted,
`~/pi_solver` backed up to `~/pi_solver_backup_2026-09-19.tar.gz` and moved to
`~/_old_projects/`. Under 1 MB total, so this was housekeeping, not a reason to
reflash.

**Installed and verified:** `python3-picamera2` 0.3.31, `python3-opencv` 4.6.0,
`numpy` 1.24.2, `rpicam-apps` 1.9.0. Project code copied to `/home/pi/smartcane/`.
`hailo-all` deliberately NOT installed yet, and `dtparam=pciex1_gen=3` deliberately
NOT added, both waiting on the HAT being physically fitted.

**Still to do, in order:**
1. Fit the Active Cooler, spacers, stacking header, PCIe ribbon, then the HAT.
2. Run `setup_pi.sh` to install `hailo-all` and set PCIe Gen3, then reboot.
3. Confirm `hailortcli fw-control identify` and record HAILO8L vs HAILO8.
4. Set and lock the manual focus on something 2-4 m away.
5. Measure FPS, end-to-end latency and power draw.
6. Disable `icecast2.service` (335 ms, another leftover) if nothing needs it.

---

### 19 September 2026 — Step 1c: AI HAT+ fitted, full vision pipeline running

**The NPU variant question from section 11 is CLOSED.** `hailortcli fw-control
identify` reports:

```
Board Name:           Hailo-8
Device Architecture:  HAILO8L      <- 13 TOPS, not 26
Firmware Version:     4.20.0
```

Note the trap: `lspci` shows "Hailo-8 AI Processor" for both variants, so it is
not a reliable way to tell them apart. Only `hailortcli` gives the real answer.
**We have the 13 TOPS board.** Section 5's performance table should be read
against the Hailo-8L column from here on.

**PCIe Gen3 confirmed working.** `dtparam=pciex1_gen=3` was added by
`setup_pi.sh` and the kernel now reports `link up, 8.0 GT/s PCIe x1` for the
Hailo bus, against 5.0 GT/s before. This is the documented roughly-2x throughput
setting.

**MEASURED PERFORMANCE (first real numbers on our hardware).**

| Measurement | Result |
|---|---|
| `hailortcli benchmark yolov8s_h8l.hef`, FPS hw_only | **58.11** |
| same, streaming FPS | 57.98 |
| same, hardware latency | **13.13 ms** |
| `detect.py` end to end, camera to named object | **30 FPS** |
| Idle temp with HAT fitted | 49.9-51.6 C |
| Throttle flags | 0x0 (clean) |

The 13.13 ms hardware latency lands inside the 10-60 ms band section 5
predicted. End-to-end runs at 30 FPS, which is camera-pipeline limited (1536x864
sensor mode feeding a 640x640 model input), not NPU limited. The NPU has roughly
2x headroom spare at this model size.

**This settles the "why not just use a Pi Zero 2 W" question with data.** 13 ms
of inference at 15% CPU, versus a CPU-only board where detection consumes the
entire compute budget. The headroom is what pays for speech, ToF fusion, OCR and
GPS running at the same time.

**`check_hardware.py` now reports 13 passed, 0 failed.**

**GOTCHA WORTH REMEMBERING: DKMS kernel mismatch.** `setup_pi.sh` runs
`apt full-upgrade` before installing `hailo-all`. The upgrade pulled a new
kernel (6.12.75 -> 6.12.109+rpt-rpi-2712), but `hailo-dkms` built `hailo_pci`
against the then-running kernel and the `-v8` variant, not the `-2712` variant
the Pi 5 actually boots. Result after reboot:

```
hailortcli: HAILO_DRIVER_NOT_INSTALLED(64)
modprobe:   Module hailo_pci not found
```

The hardware was fine the whole time. Fix:

```bash
sudo apt-get install -y "linux-headers-$(uname -r)"
sudo /usr/sbin/dkms autoinstall -k $(uname -r)
sudo modprobe hailo_pci
```

Note `dkms` is not on the default PATH, it lives at `/usr/sbin/dkms`. Consider
reordering `setup_pi.sh` so the full-upgrade and its reboot happen *before*
`hailo-all` is installed, which avoids this entirely.

**Models that ship with `hailo-all`** in `/usr/share/hailo-models/` (205 MB
total). The `_h8l` suffix files are the ones that match our board:

`yolov8s_h8l.hef` (35M, our default), `yolov6n_h8l.hef`, `yolov5s_personface_h8l.hef`,
`yolov8s_pose_h8l_pi.hef`, `yolov5n_seg_h8l_mz.hef`, `yolox_s_leaky_h8l_rpi.hef`,
`resnet_v1_50_h8l.hef`, `scrfd_2.5g_h8l.hef`. The `_h8` variants are for the
26 TOPS board and are not usable here.

**Bluetooth audio working.** Soundcore Life P2 Mini paired, trusted and
connected, sink `bluez_sink.B0_38_E2_19_DC_CC.a2dp_sink` set as default. Trusted
means it auto-reconnects on boot. Keep the section 3 decision to use a **wired**
bone-conduction headset in the shipping product, since Bluetooth adds 100-200 ms
to every spoken warning. Bluetooth is for bench work only.

**First live detection output, and why it was wrong.** `detect.py` ran clean and
produced correctly formatted sentences with bearing and distance proxy
("dog left, close"), but misclassified a human face as dog/horse. Cause was the
input, not the model: the camera was held roughly 20 cm from a face, tilted, in
dim indoor light, so the subject filled the frame with no body context. COCO
training data has people at conversational-to-street distance. **Not a defect.**
Needs retesting at a realistic 2-4 m standing distance before drawing any
accuracy conclusions.

Also confirmed: `detect.py` buffers stdout when redirected, so it must be run
with `python3 -u` when piping to a file or the output never appears.

**Camera focus is fine and should not be touched.** The earlier blurry test
frame was caused by the lens protector still being fitted. With it removed, the
ceiling grid and fabric texture resolve sharply. The M12 barrel is already set
usefully for the 1-5 m walking band. Lock it with paint before enclosure work.

**Frame tilt is a real and visible issue.** Test frames show the horizon running
diagonally. Since `detect.py` derives left/ahead/right from horizontal position,
camera roll corrupts direction output. This is concrete justification for the
IMU tilt correction in section 4.1 and a constraint on the chest-clip mount design.

### Research findings, 19 September 2026 (verified by search, not assumed)

**The 300+ class plan has a chip-specific blocker.** Compiling YOLOv8m trained on
Open Images (600 classes) for Hailo-8 is reported to fail at the final HEF build
with a `BackendAllocatorException`, while the same model on COCO (80 classes)
compiles fine. The detection head output scales with class count and exhausts the
on-chip allocator. Workarounds: smaller backbone (yolov8n/s), or a **curated
40-80 class set**, which is the recommended path anyway since a blind user does
not benefit from hearing about houseplants and picture frames.
Source: [Hailo community thread](https://community.hailo.ai/t/help-yolov8-openimages-hef-compilation-fails-gives-map-at-error/16390)

**Pothole and drain training data already exists, including Indian roads.** This
removes weeks of data collection that section 9 and section 10 assumed:

| Dataset | Content | Relevance |
|---|---|---|
| **BharatPothole** | 7,000+ annotated frames, dashcam footage from **Indian roads** | directly our use case |
| **RDD2022** | 47,420 images, 6 countries incl. India, 8 categories incl. potholes and manhole covers | breadth |
| **Intel Unnati pothole set** | 3,770 images: potholes + **manholes + sewer covers** | our "open drain" feature |
| Roboflow Universe | multiple ready-trained YOLOv8 pothole models | test today |

There is also a published paper covering exactly our hazard classes:
[YOLOv8-Based Visual Detection of Road Hazards: Potholes, Sewer Covers, and Manholes](https://arxiv.org/pdf/2311.00073).
**Correction to section 9:** potholes and drains no longer require custom data
collection, only training and HEF compilation. Indian currency and bus-number
OCR remain genuinely custom.

**Ultralytics now exports directly to HEF.** This did not exist when section 14's
first entry was written. The old `.pt -> .onnx -> Dataflow Compiler -> .hef`
chain collapses to a single export step. Still requires an **x86_64 Linux
machine** (not the Pi) and can take hours even on a good GPU, so a training
machine or cloud VM needs planning into the budget.
Source: [Ultralytics Hailo export docs](https://docs.ultralytics.com/integrations/hailo)

**Competitor/prior-art note for section 6.** The [iWatchRoad paper](https://arxiv.org/pdf/2508.10945)
publishes scalable pothole detection with geospatial visualisation for smart
cities, which is close to our section 8 crowdsourced hazard map. It does not
invalidate the moat, but the concept is not novel in research. Our differentiator
is that the map is built by **blind pedestrians walking footpaths**, capturing
hazards no dashcam-based system ever sees.

**Boot time after the HAT and Hailo stack:** 6.851 s (3.186 kernel + 3.665
userspace), up slightly from 5.923 s because of the new kernel and the Hailo
driver. Still well under the 8-15 s estimate in section 4.4.

**Next steps:**
1. Re-run `detect.py` on a person standing 2-4 m away and judge real accuracy.
2. Confirm `hailo_pci` auto-loads after a cold boot, now that DKMS is fixed.
3. Reorder `setup_pi.sh` so the kernel upgrade precedes `hailo-all`.
4. Tune `--corridor` on a real pavement (default +/-10 deg).
5. Measure power draw and runtime on the 6000mAh bank under camera + NPU load.
6. Add the VL53L1X over I2C and fuse ToF distance with the vision output.
7. Decide the curated class list (target 40-80) before any custom training.

**Open items still outstanding:** real power draw, whether the 6000mAh bank
browns out under load, detection accuracy at realistic distances, whether the
AI HAT+ top-face pins are truly pass-through GPIO.

---

### 19 September 2026 — Step 1d: speech working, autostart service, first end-to-end demo

**The device now works end to end, unattended.** Power on, wait ~7 seconds, and
it speaks named objects with direction into a headset with no login, no terminal
and no human action.

**Speech layer added: `code/speak_detect.py`.** It wraps `detect.py` as a
subprocess rather than modifying it, so the vision path and the speech path stay
independently testable and replaceable. Two design rules are load-bearing:

- **Never repeat.** Each phrase is muted for `--repeat-after` seconds (default
  4.0) after being spoken. Without this the device says "person ahead" many times
  a second and is unusable.
- **Never queue.** If speech is still playing, new reports are dropped rather
  than stacked. Queuing means the user hears warnings about obstacles they
  already walked past.

It also ranks phrases by a `PRIORITY` list (vehicles, then people and animals,
then street furniture) and speaks only the top `--max-objects` (default 2).

TTS engine is **espeak-ng**, chosen for zero install friction. It is robotic.
Piper is the upgrade path for a natural voice when we get there.

**Autostart service added: `code/smartcane.service`.** Installed to
`~/.config/systemd/user/smartcane.service`.

It is a **user service, not a system service, and that is deliberate.** Speech
goes through PulseAudio, which lives in the user session. A root system service
cannot reach the user audio sink without fragile workarounds. Running as `pi`
makes audio work with no special handling. This requires:

```bash
sudo loginctl enable-linger pi     # user session starts at boot, no login needed
systemctl --user enable smartcane.service
```

The unit has `ExecStartPre=/bin/sleep 8` plus a `bluetoothctl connect`, because
the trusted headset reconnects on its own but not instantly, and the first
spoken line would otherwise be lost. `Restart=always` because a cane that goes
silent after a crash is worse than one that stutters.

**Verified across a full reboot:**

| Check | Result |
|---|---|
| Boot time | 6.787 s |
| `hailo_pci` auto-loads | yes (DKMS fix persisted) |
| Bluetooth headset auto-connects | yes |
| `smartcane.service` auto-starts | yes, active (running) |
| Spoke "Smart cane ready" unprompted | yes |

**Detection accuracy at realistic distance is confirmed good.** With the subject
standing back from the camera rather than 20 cm from it, output was a clean and
repeated `person left, close`. The earlier dog/horse misclassification was
purely an artifact of an extreme close-up. Closes that open item.

### The 300+ class question is settled, and the answer is no

Checked Hailo's own HAILO8L object detection catalogue directly. **Every single
prebuilt model for this chip is COCO, 80 classes. There are zero models with more
than 80 classes, for any Hailo device.** Combined with the documented
`BackendAllocatorException` when compiling OpenImages 600-class models, the
conclusion is firm:

> There is no 300-class model to download and install. It does not exist for
> anyone. The only route is training a custom model on a curated class list and
> compiling it on an x86_64 Linux machine.

**Recommended target is roughly 100-120 curated classes**, not 300: the 80 COCO
classes plus about 20-40 hazards COCO never had (potholes, open drains, stairs,
curbs, poles, Indian signage). Aiming at 300 adds household clutter that a blind
pedestrian does not need and makes the HEF harder to compile on a 13 TOPS board.

**Why the big models are slow on our board** (measured/published figures):

| Model | mAP | FPS on HAILO8L |
|---|---|---|
| yolov8s (current) | ~44 | 58.1 measured |
| yolov7 | 50.6 | 36.7 |
| yolov8x | 53.5 | 16.2 |
| yolov10x | 53.7 | 14.3 |
| yolov11x | 54.1 | 12.7 |

The `x` variants are roughly 5x the parameter count of `s` and were designed for
large accelerators. Our board is the **13 TOPS Hailo-8L, half the 26 TOPS
Hailo-8**, so they run at a quarter the speed for about 10 points of mAP. The
sweet spot for a cane is likely `yolov8m` or `yolov11s`, not `x`. Untested so far.

### Additional datasets found for the curated class list

Beyond the pothole datasets recorded earlier:

| Resource | Content |
|---|---|
| [Obstacle-Dataset (TW0521)](https://github.com/TW0521/Obstacle-Dataset.git) | outdoor obstacles on blind sidewalks, with trained detection models |
| [Crucial Object Recognition for BLV individuals](https://arxiv.org/pdf/2407.16777) | which objects blind and low-vision people actually need identified — should directly drive our class list |
| [Object Detection with Vocal Feedback](https://arxiv.org/pdf/2401.01362) | 2,200 images, 4 obstacle classes incl. doors and stairs |
| [Indoor Objects Detection](https://arxiv.org/pdf/2501.18444) | 7,331 labeled objects, 10 indoor classes, for visually impaired navigation |
| [Construction site detection for assistive tech](https://arxiv.org/pdf/2503.04139) | scaffolding poles and horizontal scaffolding, YOLOv8 |

The BLV crucial-object paper is the most valuable of these. It answers "which
classes" with user research rather than guesswork, which is exactly the input
needed before committing to a custom training run.

### SD card corruption on sudden power loss — real risk, not yet mitigated

Yanking the power mid-write can corrupt the card. ext4 journaling and `log2ram`
reduce the exposure but do not remove it. **Not yet fixed.** Two things to do:

1. **The Pi 5 has a built-in power button** next to the USB-C port. Short press
   while running triggers a clean shutdown. Short press while halted powers it
   back on. Holding it about 5 seconds forces power off (use only if hung).
   This is the correct way to switch the device off today.
2. **Enable overlayfs before shipping** (read-only root with a RAM overlay), so
   power loss cannot corrupt anything. Deliberately NOT enabled now because it
   makes changes non-persistent, which would break development. Revisit at
   productization.

The external waterproof power button planned in section 4.3 wires to the Pi 5
**J2 header**, which duplicates that same onboard button.

**Next steps:** wire the VL53L1X (deferred to 20 September by request), test
`yolov8m`/`yolov11s` for the accuracy-speed sweet spot, decide the curated class
list using the BLV crucial-object paper, plan an x86 training machine.

### 19 September 2026 — Reliability bug: silent audio death (FIXED)

**Symptom:** the device appeared to "crash" and stop naming objects. It had not
crashed. `systemctl` showed `Result=success`, `NRestarts=0`, uptime minutes, and
the log was still printing `SPEAKING: person right, near` the whole time.

**Root cause:** PulseAudio's `module-suspend-on-idle` suspended the Bluetooth
sink during gaps in speech. Suspending the sink tore down the A2DP transport,
which disconnected the earbuds, after which PulseAudio silently fell back to
`auto_null`. **A null sink swallows audio and returns success**, so nothing in
the stack reported an error. The cane was talking into a black hole.

This is the most dangerous class of bug for this product: everything reports
healthy while the user gets nothing. Worth watching for again in the ToF and
vibration paths.

**Fixes applied, all three needed:**

1. `pactl unload-module module-suspend-on-idle`, plus commented out in
   `~/.config/pulse/default.pa` so it does not come back on reboot. This was the
   actual cause.
2. `speak_detect.py` rewritten with an `AudioLink` class that checks the default
   sink **before every phrase**. If it is `auto_null` it refuses to consume the
   repeat-mute timer, logs `AUDIO DEAD`, and triggers a throttled
   `bluetoothctl connect` plus `pactl set-default-sink`. A background watchdog
   thread does the same check every 5 s.
3. A near-silent 0.3 s blip every `--keepalive-after` seconds (now 20) so idle
   earbuds do not fall asleep in the first place.

**Also fixed a latent deadlock in the same file:** `espeak-ng` and `paplay` had
no timeouts. A `paplay` hung against a half-dead Bluetooth link would hold the
speech lock forever, and the cane would go permanently silent while still
looking healthy. Both calls now have hard timeouts (10 s and 15 s) and the lock
release is in a `finally`.

**Verified:** 90 seconds of continuous operation, **zero `AUDIO DEAD` events**,
continuous correct output with direction tracking as the subject moved
(`person ahead` / `person left` / `person right`).

**Standing conclusion: Bluetooth audio is the least reliable part of this
system.** Section 3's choice of a **wired** bone-conduction headset was made for
latency. Reliability is now a second and stronger reason. Note the **Pi 5 has no
3.5 mm jack**, so wired audio needs either the planned PCM5102A I2S DAC or a
cheap USB audio adapter. A USB audio dongle would remove this entire class of
failure immediately and is worth buying for bench work.

### Training machine: already owned, needs unblocking

Checked the development laptop. It is much more capable than the roadmap assumed:

| | |
|---|---|
| GPU | **NVIDIA GeForce RTX 4060 Laptop** |
| CPU | Intel i9-13900H |
| RAM | 47.6 GB |
| Free disk | 240 GB |
| WSL | Ubuntu registered, WSL2 default |

**This removes the "we need to buy or rent an x86 Linux machine" item.** Training
and HEF compilation can both happen locally through WSL2 Ubuntu with CUDA.

**Two blockers before that work can start:**

1. **WSL will not launch.** `Wsl/Service/CreateInstance/CreateVm/HCS/HCS_E_SERVICE_NOT_AVAILABLE`
   means the Virtual Machine Platform Windows feature is off. Fix needs an
   elevated shell and a **reboot of the laptop**:
   ```
   dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
   dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
   ```
2. **Hailo Dataflow Compiler needs a free Hailo Developer Zone account.** The
   `.whl` is behind a login and cannot be fetched automatically. Adeel must
   register and download it by hand.

**Honest scope correction on "300 objects":** a genuine 300-class model is the
wrong target for a 13 TOPS Hailo-8L. The documented `BackendAllocatorException`
on 600-class OpenImages compiles is an on-chip memory limit that gets tighter as
class count rises, and accuracy per class dilutes as the head grows. The
realistic and better target remains **roughly 120-150 curated classes**: the 80
COCO classes plus the hazard classes that actually matter, drawn from the
datasets listed above.

### 19 September 2026 — Step 2: obstacle fallback, training pipeline built

**"Obstacle" fallback shipped.** `speak_detect.py` no longer drops detections it
cannot name usefully. Anything outside the relevant class set is announced as
`"obstacle <direction>, <distance>"` instead of being silently discarded.
Rationale: COCO has 80 labels and the world has millions of things, so silence
about a real physical object is the dangerous choice. Unknowns in the same
direction collapse into one phrase so a cluttered pavement does not produce
"obstacle left. obstacle left. obstacle left."

**This fallback is what makes a short curated class list safe.** Classes we
choose not to train are still reported by position. That argument should be
reused whenever the class-count question comes up again.

**Flicker suppression shipped** (`Confirmer` class, `--confirm`, default 2). A
class must appear in two consecutive reports before it is spoken. Costs ~1.5 s
latency, removes nearly all one-frame false labels. This is the fix for the
spurious "dog"/"cat" reports. Misses are forgiven once so a single dropped frame
does not reset a streak.

**Diagnosis of the reported accuracy problems, in order of real cause:**

1. **"wrong positions" is almost certainly camera roll, not the model.** Every
   test frame shows a diagonal horizon. `detect.py` derives left/ahead/right
   from horizontal position, so roll corrupts direction directly. Fix is a level
   mount now and IMU tilt correction later. Do not chase this in software first.
2. **"says dog or cat" is single-frame flicker**, now suppressed.
3. Testing has been indoors, handheld, dim, at ~20 cm. That is the worst case
   for a COCO model. Real evaluation must be outdoors, daylight, chest height.

**99% accuracy is not achievable and should stop being a target.** Best published
COCO mAP50-95 is ~54. The right targets for this product are high recall on
dangerous classes, low false-alarm rate, and correct direction. Reliability comes
from model + temporal voting + ToF fusion stacked, not from one very accurate
model. Targets are written into `code/training/classes.yaml`.

### Training environment: working, on Windows, no WSL needed to train

**Key finding that changes the plan: WSL is only needed for the final HEF
compile, not for training.** Training and ONNX export both run natively on
Windows.

| Step | Where | Status |
|---|---|---|
| Train | Windows + CUDA | **ready** |
| Export ONNX | Windows | ready |
| Compile .hef | WSL2 Linux only | blocked |

**Environment built at `C:\ml\venv`** (deliberately a short path). torch
2.5.1+cu121, CUDA available, RTX 4060 Laptop detected, ultralytics 8.4.155.

**Gotcha: do not pip install into the Microsoft Store Python.** It lives under
`AppData\Local\Packages\PythonSoftwareFoundation...`, and a torch upgrade failed
with `[WinError 206] filename or extension is too long`, leaving a half-removed
torch (`No module named torch._C`). The venv at `C:\ml\venv` avoids this.

**Files written:** `code/training/classes.yaml`, `code/training/prepare_datasets.py`,
`code/training/train.py`.

**Class list is now 93** (80 COCO + 13 added), up from 88 after inspecting the
Obstacle-Dataset README.

Added: pothole, manhole, open drain, stairs, curb, pole, scaffolding, door,
**traffic cone, bollard, trash bin, roadblock, tricycle**.

**Obstacle-Dataset OD turned out to be the best per-image find so far.** The
GitHub repo is a README only, the 7,915 images are on Google Drive. It ships in
both VOC XML and YOLO txt, and five of its fifteen classes are street furniture
COCO has no label for at all: `reflective_cone`, `warning_column` (bollard),
`ashcan`, `spherical_roadblock`, `tricycle`. Tricycle matters especially, since
three-wheelers are among the most common moving vehicles on Indian streets and
COCO cannot see them as anything.

`prepare_datasets.py` carries a `LABEL_ALIASES` map because every dataset names
things differently (`pothole` / `potholes` / `D40` / `pot hole` all collapse to
one class, `motorbike` folds into COCO's `motorcycle`).

**Blocked on Adeel, cannot proceed without:**

1. **Free Roboflow API key** (`setx ROBOFLOW_API_KEY ...`) for intel_unnati and
   roboflow_pothole.
2. **Manual downloads** into `C:/ml/smartcane/data/raw/<name>/`: rdd2022
   (largest and most valuable), bharat_pothole, obstacle_dataset (Google Drive),
   construction_site, vocal_feedback, indoor_objects.
3. **Free Hailo Developer Zone account** for the Dataflow Compiler.
4. **Enable WSL** (admin + reboot) for the HEF compile step.

**Also outstanding:** the camera has been pointed at a dark empty wall, so the
before/after accuracy comparison for the flicker fix has not been run on a real
scene yet. Only the "before" case produced evidence (spurious `cat`).

**Bluetooth deliberately disconnected and untrusted** at Adeel's request.
Note `bluetoothctl untrust` also cleared the pairing, so reconnecting means
pairing again, not just connecting. Since re-paired, trusted and connected again
on request, with `pactl set-card-profile <card> a2dp_sink` to force the high
quality stereo profile rather than the mono headset one.

### 19 September 2026 — Two-tier confidence: high recall and trustworthy names

**The request "never miss any object" and "highest accuracy" are in direct
tension.** Lowering the threshold catches more real objects and also more
nonsense. Raising it does the reverse. Resolved by splitting the two decisions
apart rather than picking a compromise threshold:

```
   detector threshold  --conf 0.25       low  -> almost nothing is missed
   naming threshold    --name-conf 0.55  high -> names are trustworthy
   the gap between them            -> announced as "obstacle <direction>"
```

`detect.py` now appends the confidence to every fragment as `@0.87`, and
`resolve()` in `speak_detect.py` decides per detection whether to say the class
name or fall back to "obstacle". Nothing physical is ever silently dropped, and
a name is only spoken when the model actually believes it.

**Live evidence of why this matters**, captured from the device at `--conf 0.2`:

```
[ 29.9 fps]  dog right, near @0.28
```

A 0.28-confidence "dog" in an empty room. Under the old single-threshold design
that was either dropped entirely (at 0.4) or spoken as "dog" (at 0.25). Now it
becomes "obstacle right, near", and flicker suppression discards it anyway since
it appeared in only one report. This single line is the whole argument for the
design.

**Guiding principle worth keeping: a wrong name erodes trust in the device,
"obstacle" never does.** Prefer the vaguer true statement over the specific
false one.

Service defaults updated: `--interval 1.2 --conf 0.25 --name-conf 0.55
--confirm 2 --max-objects 2 --repeat-after 4.0`. Verified running after restart,
including one automatic audio self-heal on startup.

### Open Images V7 is the unblock for "more objects", no account needed

**`yolov8s-oiv7.pt` (601 classes) downloads freely from Ultralytics**, and the
Open Images V7 dataset itself is public with no API key, no login and no licence
gate. This removes the dependency on Adeel for the broad city class layer.
The specialist hazard datasets are still blocked on him.

`code/training/fetch_openimages.py` written. It uses FiftyOne to pull only a
curated subset rather than the ~560 GB full set, and exports YOLO labels.

**93 city classes curated from the 601.** Selection rule: anything a walking
person can collide with, trip over, needs to find, or needs warning about.
Excluded ~500 classes of food, kitchen tools and musical instruments, which cost
accuracy on the classes that matter and are covered by the "obstacle" fallback
anyway.

Classes this adds that COCO simply does not have: **Traffic sign, Street light,
Building, Office building, Skyscraper, House, Window, Door, Door handle, Stairs,
Ladder, Porch, Tree, Palm tree, Waste container, Billboard, Poster, Barrel,
Fountain, Tower, Van, Taxi, Ambulance, Limousine, Wheelchair, Segway, Cart,
Tent, Plastic bag, Tire, Wheel, Monkey, Pig, Mule, Goat, Cattle,
Vehicle registration plate.**

**Open Images has NO pothole, NO open drain, NO kerb, NO bollard.** Those remain
dependent on RDD2022, BharatPothole, Intel Unnati and Obstacle-Dataset, which all
need a Roboflow key or a manual download. So the broad city model can be trained
without Adeel, but the hazard layer, which is the product's main differentiator,
cannot.

Download of the validation split started first deliberately, to prove the
pipeline before pulling tens of gigabytes.

---

### 2 October 2026 — Step 3: two ToF sensors + vibration wired to the Pi, camera lost

Adeel wired two ToF sensors and the vibration module to the Pi (via the AI HAT+
pass-through header) and asked for everything to be configured. Checked over SSH.

| Part | Result |
|---|---|
| AI HAT+ (Hailo-8L) | OK. `hailortcli` identifies HAILO8L, PCIe Gen3 still set |
| Camera (IMX708, CAM0) | **NOT DETECTED.** `rpicam-hello --list-cameras` says "No cameras available", and there is no imx708 line in `dmesg` at all, so the firmware found nothing at boot. Worked on 19 Sept. Almost certainly the ribbon was disturbed while wiring the sensors. Needs a physical reseat (power off, contacts facing the board on the Pi end) |
| Vibration motor | Software side OK. `haptics.py --test` ran all five patterns on GPIO18 (pin 12) via `gpiochip15`. Whether the motor physically buzzed needs Adeel to confirm |
| ToF sensors | Both found and identified. **Unstable when both are powered**, see below |

**The two ToF sensors are VL53L0X, not VL53L1X.** Identified by reading registers
0xC0..0xC2 = `EE AA 10`. This matters: the L0X uses 8-bit register addresses
(VL53L1X code sends 16-bit indexes and gets garbage back), and its range is about
1.2 m in default mode against roughly 4 m for the L1X. Section 2 is corrected.

**XSHUT wiring found by probing, not told:** GPIO23 (pin 16) and GPIO24 (pin 18).
Method worth reusing: set every unused GPIO to input with internal pull-down. A
pin that still reads high has an external pull-up, which is what a breakout's
XSHUT line looks like. Then hold each low in turn and rescan. Both low gives an
empty bus. Either high gives `0x29`. SDA/SCL on GPIO2/3 as normal.

**Driver:** `code/tof.py`, copied to `~/smartcane/`. Holds both in reset, wakes
each in turn, moves them to `0x30` (GPIO23, default role "forward") and `0x31`
(GPIO24, default role "down"), single-shot ranging, and re-runs the whole
bring-up if a read fails so a dead sensor is never silent. Uses
`adafruit-circuitpython-vl53l0x` 3.6.19 + Blinka in a new venv
`~/smartcane/venv` (created with `--system-site-packages`, so picamera2 and
hailo still import from it). Roles are a `--sensors` flag because which sensor
points where depends on the mount, which is not yet known.

**The ToF fault, measured:**

| Test | Result |
|---|---|
| GPIO23 sensor alone, single-shot, 40 reads | 0 errors (72 mm) |
| GPIO24 sensor alone, single-shot, 40 reads | 0 errors (37-40 mm) |
| One sensor alone, **continuous** mode | resets after 1 read (falls from 0x30 back to 0x29) |
| Raise second XSHUT without init | first sensor survives |
| Init second sensor while first is at 0x30 | first sensor resets, both collide at 0x29 |
| Both, `tof.py` 20 s | 392 errors in 242 reads |
| Repeat with longer delays | even a single sensor's init failed once |

A sensor dropping back to `0x29` is only possible on a power cycle, and the
failures grow with load (laser firing). The Pi side is healthy: 3V3_SYS 3.29 V,
EXT5V 4.97 V, throttled 0x0. Conclusion: **a loose or high-resistance VIN/GND
connection to the sensor boards**, made worse by intermittency. Software cannot
fix this. To do: reseat or solder VIN/GND, give each sensor its own GND wire, try
VIN on 5 V if the breakouts carry a regulator (GY-530 style boards do), and add
a 10-100 µF capacitor across VIN/GND near the sensors.

**Hailo driver kernel warnings:** `dmesg` fills with `WARNING ... find_vma ...
hailo_vdma_buffer_map [hailo_pci]` stack traces whenever HailoRT runs. It is an
mmap-lock assertion in the out-of-tree driver against kernel 6.12.109. Inference
still works. Noisy, not a fault, but watch for a `hailo-all` update that fixes it.

**`smartcane.service` left stopped.** Without a camera it was restart-looping
every ~15 s ("starting vision... stopped."). It will start again on next boot.
The Bluetooth headset also failed to connect (`br-connection-profile-unavailable`),
probably just switched off.

**Next steps:**
1. Reseat the camera ribbon, confirm with `rpicam-hello --list-cameras`.
2. Fix ToF power wiring, then `venv/bin/python tof.py --seconds 30` should show
   0 errors and 0 re-inits.
3. Confirm the motor physically buzzes on `python3 haptics.py --test`.
4. Decide which sensor is forward and which is down, then fuse ToF into
   `speak_detect.py` (switch the service to `venv/bin/python`).

### 2 October 2026 — Step 3a: after reseating

Adeel confirmed the AI HAT+ **needs the GPIO header**: the PCIe ribbon carries
data only, while 5 V power and the HAT+ ID EEPROM (which auto-enables PCIe) come
through the 40-pin header. Use the tall stacking header and spacers because of
the Active Cooler. The stacking header also passes GPIO through for the sensors,
so a badly seated header is a candidate cause for the ToF power faults.

| Part | Result after reseat |
|---|---|
| AI HAT+ | OK, HAILO8L |
| Camera | **Back.** imx708 on CAM0, `rpicam-jpeg` captured a frame. Frame is hazy and soft, so check for the lens film, a fingerprint, or a disturbed focus ring |
| `smartcane.service` | Running again, end to end: `SPEAKING: person ahead, close`, audio self-healed from `auto_null` to the headset |
| Vibration motor | Adeel reports **no vibration**. Pi side verified: GPIO18 driven solid high for 3 s (`pinctrl get` = `op dh hi`), then the PWM pattern. So the fault is downstream: module power, signal on the wrong header pin, or a bare motor with no driver |
| ToF sensors | **Now nothing answers on I2C at all**, not even 0x29. SDA/SCL idle high. XSHUT 23/24 still read high against pull-downs. `dmesg` shows ~1200 `i2c_designware ... lost arbitration` errors, all at the moments XSHUT was driven high and none on a quiet scan |

Reading of the ToF symptoms: arbitration loss means something pulls the bus the
wrong way mid-transfer, which a merely absent device never does. Appearing only
when XSHUT is driven high fits a sensor with **no VIN or no GND**, which gets
weak power through the XSHUT pin and then misbehaves on the bus. SDA/SCL swapped
is the other candidate. Needs the wiring checked by eye or with a meter.

Pin-name trap worth remembering: **physical pin 18 is GPIO24, and GPIO18 is
physical pin 12.** Mixing "pin" and "GPIO" numbering would put the motor on a
ToF XSHUT line and explain both faults at once.

### 2 October 2026 — Step 3b: wiring keeps ripping off, move sensors to ESP32

Root cause of the ToF and motor faults: Adeel had **soldered the sensor and
motor wires straight onto the Pi 5 header pins**, and the joints kept tearing
off. No header extender on hand. Soldering to the header also risks heat damage
and solder bridges, and a bridge could explain the I2C arbitration errors.

**Recommendation given: move ToF + motor to the ESP32 now, linked to the Pi by
one USB cable.** This is not a workaround. It is the section 4.1 architecture
(safety loop on a separate MCU, alive ~1 s after power-on, survives a Pi crash),
just brought forward. USB serial replaces every wire on the Pi header, powers the
ESP32, and is mechanically robust. Sensors go on a breadboard with the ESP32, so
no soldering to the Pi at all. Pending: which ESP32 board Adeel has, and whether
he has a breadboard and jumpers.

**Confirmed: the AI HAT+ top has no usable pass-through pins.** The header pins
are short and end inside the HAT, so with the HAT fitted there is no GPIO access
from above. This settles the open item from 19 Sept and removes "jumpers on top
of the HAT" as an option.

**Full GPIO probe, 2 Oct 2026, after Adeel added two buttons** (each pin read
with internal pull-up, then pull-down):

| Pin | Reading | Meaning |
|---|---|---|
| GPIO23, GPIO24 | high under both pulls | ToF XSHUT still attached |
| GPIO17 (phys 11) | **low under both pulls** | tied to GND. Likely a button wired across two legs that are always connected inside a 4-leg tactile switch, or a short |
| all others 4-27 | open | nothing, or an unpressed button |
| I2C bus 1 | empty, 224 `lost arbitration` errors during boot | ToF SDA/SCL still faulty |

A 60 s watch (30 s pull-up, 30 s pull-down) while asking for button presses saw
**no pin change at all**. Second button not found.

Recommendation stands and is now stronger: **put ToF x2, motor and both buttons
on the ESP32, with only USB to the Pi.** Pi 5 power button stays on the J2 header.

### 2 October 2026 — Step 3c: real wiring map received, two mysteries solved

Adeel shared the pin map he actually wired (wire colours in brackets):

| Pi pin | Connection |
|---|---|
| 1 (3V3) | all 3 ToF VCC (grey) |
| 2 (5V) | **UPS+** (red), so the Pi is powered from a UPS through the 5V pin |
| 3 / 5 | ToF SDA (dark yellow) / SCL (white) |
| 6 | GND rail (black) |
| 11 (GPIO17) | vibration module IN (blue) |
| 15 / 16 / 18 (GPIO22/23/24) | ToF 1/2/3 XSHUT (green / yellow / orange) |
| 31 (GPIO6) | AI assistant button (purple) |
| 29 (GPIO5) | reserved, unused |

**There are THREE ToF sensors, not two.** **The motor is on GPIO17, not
GPIO18.** Together these explain everything measured earlier today:

- Motor never buzzed because `haptics.py` and the service drive GPIO18.
- GPIO17 "stuck low under both pulls" was the motor module's input stage, not a
  button.
- ToF 1's XSHUT (GPIO22) probed as unconnected, so ToF 1 sat permanently awake at
  0x29 and collided with whichever sensor was being brought up. That is the
  "first sensor resets when the second wakes" result.

Retest with the right pins: GPIO17 driven high 2 s plus 3 pulses (result needs
Adeel's confirmation). No ToF answers with any single XSHUT raised, so the bus
wiring has come off. GPIO6 reads open (button unpressed or detached).

**Decision: everything except UPS power moves to the ESP32**, which connects to
the Pi by USB. Plan:

| Wire | ESP32 (DevKit V1 assumed, board not yet confirmed) |
|---|---|
| ToF VCC / GND | 3V3 / GND |
| ToF SDA / SCL | GPIO21 / GPIO22 |
| ToF 1/2/3 XSHUT | GPIO25 / 26 / 27 |
| Motor IN / VCC | GPIO13 / VIN (5V from USB) |
| Assistant button | GPIO33 to GND, internal pull-up |
| Mode button (optional) | GPIO32 to GND |

Avoid ESP32 strapping pins 0, 2, 5, 12, 15 and input-only 34-39. Firmware to be
Arduino C++ with the Pololu VL53L0X library, flashed **from the Pi over the same
USB cable** with arduino-cli, so nothing needs installing on the laptop.

Latency estimate for this design: ToF 3 sensors in parallel continuous mode
~33 ms (20 ms budget possible), ESP32 decision <1 ms, ERM motor spin-up
~30-50 ms, so **obstacle to felt vibration ~50-90 ms, with no Pi involved**.
ESP32 to Pi over USB serial adds ~2-10 ms. Speech remains the slow part
(espeak + Bluetooth, 100-300 ms+).

**Update: ToF 1 (green, XSHUT GPIO22 on the Pi) removed by Adeel.** Two ToF
sensors remain: ToF 2 (yellow) -> ESP32 GPIO26, ToF 3 (orange) -> ESP32 GPIO27.
GPIO25 is now free.

Adeel read the 100-300 ms figure as ESP32 latency. It is not: it is **speech**
(espeak synthesis + Bluetooth A2DP buffering), and it is identical whether the
sensors hang off the Pi or the ESP32. Pi-only vibration would be ~65-90 ms once
booted (Linux/Python jitter, nothing after a crash, nothing for the first ~7 s),
against ~50-90 ms on the ESP32. The ways to cut speech latency are: wired audio
(USB dongle or I2S DAC) instead of Bluetooth, and pre-rendered audio clips for
the common phrases so playback starts with no synthesis step.

**ESP32 board confirmed as DevKit V1.** Adeel will not use a breadboard (wants a
professional build) and cannot risk more failed solder joints. Advice given:
every signal wire comes off the Pi (ToF, motor, button), only UPS 5V + GND stay.
Connect to the DevKit's male header pins with **female Dupont crimps, no
soldering on the ESP32**, or a screw-terminal ESP32 expansion board. Joints
failed for lack of strain relief, not because soldering is wrong: use stranded
wire, heat-shrink, and anchor wires (zip tie / hot glue) so a pull lands on the
anchor, not the joint. Shared ToF lines (VCC, GND, SDA, SCL) are spliced once,
then a single wire goes to the ESP32. Final product: custom PCB with JST
connectors (section 10, phase 3).

Power check: Pi 5 fed through the 5V pin limits USB to 600 mA total. ESP32
(~100-250 mA) + motor (~80-100 mA) + 2 ToF (~40 mA) is about 400 mA, inside it.

**Revised ESP32 plan: each ToF on its own I2C bus.** Adeel wired ToF 1 to the
ESP32 and separated ToF 2 onto its own wires rather than sharing a bus. The ESP32
has two I2C controllers, so ToF 2 gets its own SDA/SCL (GPIO18/19). This removes
the SDA/SCL splices and the address juggling: both sensors can stay at 0x29.
XSHUT is kept for reset-recovery only.

| | ToF 1 | ToF 2 | Motor | Button |
|---|---|---|---|---|
| VCC | 3V3 | 3V3 (shared, splice) | VIN | - |
| GND | GND | GND | GND (shared, splice) | GPIO32 driven LOW as its ground |
| SDA / SCL | GPIO21 / 22 | GPIO18 / 19 | - | - |
| XSHUT / signal | GPIO26 | GPIO27 | GPIO13 | GPIO33 |

DevKit V1 30-pin has one 3V3 and two GND pins, so 3V3 and GND still need one
splice each (two wires in one female Dupont, a Y-splice under heat-shrink, or a
lever connector). The button "ground" GPIO trick avoids a third GND.

### 2 October 2026 — Step 3d: ESP32 on USB, undervoltage takes out the Hailo

**ESP32 detected by the Pi**: CP2102 bridge (`10c4:ea60`), `/dev/ttyUSB0`, `pi`
is in `dialout`. Firmware written: `code/esp32/cane_safety/cane_safety.ino`
(two VL53L0X on separate I2C buses, parking-sensor style auto vibration, serial
protocol `D <ms> <mm1> <mm2> <ok1> <ok2>`). Pi side: `code/esp32_link.py`, which
opens the port with DTR/RTS held low, because on a DevKit V1 those lines reset the
ESP32 and the safety loop would go dark every time the Pi software restarted.
Toolchain: `arduino-cli` in `~/.local/bin`, ESP32 core and the Pololu `VL53L0X`
library. The core is about 1.5 GB because it bundles toolchains for every ESP32
family. **Run long installs detached (`nohup ... &`)**: the first attempt died
when the SSH session dropped.

**"Why is the cane silent?" had two causes:**

1. **Undervoltage knocked the Hailo off PCIe.** `dmesg` shows dozens of
   `hwmon: Undervoltage detected!` from ~8.5 min after boot, then at 15.7 min
   `hailo 0001:01:00.0: Device disconnected while opening device`. The service
   crash-looped with `HAILO_DRIVER_OPERATION_FAILED(36)`. The Pi is fed by a UPS
   through the 5V pin, and that supply cannot hold up the Pi + Hailo + camera +
   ESP32 under load. **Recovery without a reboot** (works, run it detached):
   ```bash
   sudo systemctl stop hailort.service; sudo pkill -f hailort_service
   sudo rmmod hailo_pci
   echo 1 | sudo tee /sys/bus/pci/devices/0001:01:00.0/remove
   echo 1 | sudo tee /sys/bus/pci/rescan
   sudo modprobe hailo_pci; sudo systemctl start hailort.service
   ```
   **Real fix outstanding: a supply that holds 5 V at 5 A** (official 27 W USB-C
   PSU, or a UPS rated for it, into the USB-C port). Until then the Hailo can drop
   at any moment. Same class of bug as the Bluetooth null sink: the device looks
   on, but it is blind.
2. **The earbuds had lost their pairing** (`Paired: no`), probably after being
   paired to a phone. Re-paired with a detached script (remove, scan, pair, trust,
   connect, force `a2dp_sink`). Result: connected, A2DP, `AUDIO OK`, test phrase
   spoken. Shows `Bonded: no`, so the pairing may not survive a reboot. Check after
   the next reboot.

### 2 October 2026 — Step 3e: ESP32 safety loop flashed and verified

Compiled on the Pi (`arduino-cli compile --fqbn esp32:esp32:esp32`, 309 KB,
23% flash) and uploaded over the same USB cable. Hash verified. **Run compile and
upload detached**: SSH drops under heavy CPU on this Pi, probably the same
undervoltage hitting WiFi.

| Check | Result |
|---|---|
| Boot report | `bus1 scan: 0x29`, `bus2 scan: 0x29`, `ready tof1=1 tof2=1` |
| ToF stability, 20 s | **0 errors, 0 re-inits**. ToF 1 112-118 mm, ToF 2 42-48 mm on the bench |
| Motor commands B100/B60/B85/B100 | accepted by firmware. Whether Adeel felt them is not yet confirmed |
| Link rate | 20 Hz, gaps 50.0-50.1 ms, i.e. no added jitter |

**Three Pi-side link bugs found and fixed in `esp32_link.py`, all measured:**

1. `ser.read(256)` waited for the timeout to fill its buffer, so readings arrived
   in ~0.2 s batches. That is up to **200 ms of hidden lag**, against the 2-10 ms
   claimed. Fixed with `read(in_waiting or 1)`.
2. Setting `dtr=False` then `rts=False` before open (the common advice) **reset
   the ESP32 on every open**: the two writes pass through RTS-on/DTR-off, which
   is the auto-reset state. A plain default open reset it 0 times in 3. So do
   NOT set DTR/RTS.
3. On open, **~1,100 stale readings** buffered while the port was closed arrived
   in one burst. Fixed with `reset_input_buffer()` right after open.

Firmware behaviour to remember: auto vibration is ON at every ESP32 boot. On the
bench, with both sensors seeing something under 400 mm, the motor runs solid.
That is the designed "very close" alert, not a fault. `A0` over serial turns it
off until the next reset.

### 2 October 2026 — Step 3f: forward + downward ToF roles, distance in speech

Adeel: one ToF measures obstacle distance, the other points down for potholes.
Default roles **ToF 1 (D21/D22) = forward, ToF 2 (D18/D19) = down**, switchable
with serial `R1`/`R2`, saved in ESP32 flash (Preferences). Not yet confirmed
against the physical mount.

**ESP32 firmware now:**
- Auto vibration from the **forward sensor only**. The down sensor always sees
  the ground, so using "nearest of both" would buzz forever.
- **Ground watch on the down sensor**: learns the normal ground distance from the
  median of 10 readings, then follows slow drift (EMA 0.05, only while in band).
  Alarm when 3 consecutive readings (~100 ms) are > baseline +150 mm (or
  nothing in range = ground fell away) -> `H drop`, or < baseline -120 mm ->
  `H step`. 2.5 s hold-off. A change lasting > 2 s is treated as a new grip
  angle and relearned. Thresholds are guesses until tested on a real pavement.
  Without an IMU, cane swing will cause false drops. That is the known limit.
- **Ground alarm feels different from an obstacle**: 3 long hard pulses (300 on /
  150 off) that override the obstacle pattern.
- Serial `D` line is now `D <ms> <fwd> <down> <fok> <dok> <ground>`.

**`speak_detect.py` now:**
- Objects **"ahead"** get the measured ToF distance ("person ahead, 60
  centimetres"). Left/right objects keep the camera's word, because the ~25° ToF
  cone is not measuring them.
- The repeat timer is keyed on a **distance band** (close < 0.5 m, near < 1 m,
  far), so an approaching object is re-announced but 1.1 -> 1.0 m is not.
- `SensorWatch` thread: speaks "Careful, drop ahead" / "Step up ahead" as
  **urgent** (waits up to 2 s for current speech instead of dropping it),
  "obstacle ahead, N" for ToF hits the camera has not named in 2.5 s (glass,
  poles, walls), and **"Warning, distance sensors not responding"** if the ESP32
  goes quiet for 2 s.
- Pi-side GPIO haptics disabled when the ESP32 is present: two masters for one
  motor would fight.

**Verified on the bench (dry run):** forward 97 mm -> `WOULD SAY: obstacle ahead,
10 centimetres`, ground learned 69 mm, 0 errors, 0 re-inits.

**Earbud pairing does not persist.** The pairing script used `bluetoothctl pair`
with no agent, which gave `Paired: yes, Bonded: no`, i.e. no stored link key, so
it was lost on the next disconnect. New script `/tmp/bt_bond.sh` pairs with
`--agent NoInputNoOutput`, stops the service during pairing (its reconnect loop
raced the pair), and checks for `LinkKey` in `/var/lib/bluetooth`. First run
timed out with the earbuds not in pairing mode.

**Real root cause of "Bonded: no": the adapter had `Pairable: no`.** BlueZ then
does a non-bonding pairing: it works, but no link key is stored, so the earbuds
are forgotten at the next disconnect. The agent made no difference
(`Pairing successful` and still `NO_LINKKEY`). Fixed with `bluetoothctl pairable
on` now, plus `AlwaysPairable = true` and `PairableTimeout = 0` under
`[General]` in `/etc/bluetooth/main.conf` (backup `main.conf.bak-2026-10-02`).
**The current pairing was made before the fix, so it is still unbonded.** One
more pairing (run `/tmp/bt_bond.sh`, earbuds in pairing mode) is needed to make
it permanent.

Speech confirmed working after re-pair: `AUDIO OK`, then `SPEAKING: obstacle
ahead, 10 centimetres` from the forward ToF, repeated every 4 s while the
obstacle stays put.

### 2 October 2026 — Step 3g: camera + ToF sync, faster announcements, faults spoken

**Sync:** when a sentence starts playing, the Pi sends the ESP32 a buzz matched
to the nearest distance band (close `B100,400`, near `B85,250`, far `B60,150`).
It fires from `Speaker._play` **after** espeak synthesis, right before
`paplay`, so feel and voice start together rather than the buzz arriving
~150 ms early. Things "ahead" use the ToF band, others the camera's word.

**Latency fix:** `--interval 1.2 --confirm 2` meant an object was first spoken
1.2-2.4 s after it appeared. Now `--interval 0.3 --confirm 3`, so ~0.6-0.9 s,
with three agreeing reports instead of two to keep flicker out.

**Forward ToF in long-range mode** (signal rate 0.1 MCPS, VCSEL 18/14): ~2 m
indoors instead of ~1.2 m, shorter in sun. Untested at range so far. Both
sensors now report a **median of 3** readings. Measured on the bench: forward
mean 92.4 mm, stdev 0.8 mm, range 91-96. Forward vibration band extended to
1.5 m. Ground confirm reduced to 2 filtered reads (~130 ms).

**AI HAT utilisation, measured:** model `yolov8s_h8l.hef` (80 COCO classes),
PCIe Gen3 8 GT/s x1 (x1 is the Pi 5 maximum, "downgraded" in lspci is normal).
detect.py infers every camera frame at 15 fps, against 58 FPS capacity, so the
NPU is about **26% used**. That headroom is deliberate (15 fps for low light)
and is what a second model (potholes) or a bigger one would use. A rerun of
`hailortcli benchmark` timed out (`HAILO_TIMEOUT`) while the old service process
still held the device. The Hailo itself identified fine.

**Bugs found and fixed:**
- **Service would not start with the earbuds off.** `ExecStartPre=bluetoothctl
  connect` hung until systemd's start timeout killed the unit. Now wrapped in
  `timeout 10`. Earbuds being off must never stop the cane.
- **A dead single sensor was silent.** The Pi only warned if the whole ESP32
  went quiet. Now "Warning, ground sensor not working" / "obstacle sensor not
  working" after 3 s of failure, repeated every 60 s. Verified live.
- `R1`/`R2` now re-initialise both sensors, so long-range mode follows the
  forward role.
- New ESP32 command **`T`**: per-bus scan plus ID registers (expect `EE AA 10`).

**ToF 2 (down) has a loose wire.** At boot it answered the bus scan but failed
init. Minutes later it was absent from bus 2 entirely. Fails in both roles, so
it is not the long-range change. `T` shows tof1 `EE AA 10`, tof2 nothing. Needs
its VCC/GND/SDA (D18)/SCL (D19) connections redone.

**Earbuds dropped again at 19:19** as predicted (pairing made before the
`Pairable` fix, so unbonded). They reconnected on service restart. One more
pairing is still needed to make it permanent.

### 2 October 2026: Consumer-readiness plan adopted, Phase 1 Step 1.1 (baseline)

Adeel handed over a 5-phase consumer-readiness plan (power and safety
foundation, sensor validation + IMU, model selection, fusion and fault
handling, product validation). Saved verbatim in
`docs/consumer-readiness-plan.md`. Rules that now govern all work: never move
to the next step until the current one is tested and passes, record every
step under `experiments/`, tag known-good states. **After each phase passes
its gate, write the next phase's prompt from the plan, revised with what the
phase measured, into `docs/phase-prompts/`.**

Step 1.1 froze the system. Full record in
`experiments/phase1/step1_1_baseline/` (README, failure_log, results.json).
Status **BLOCKED** on one power-down: SD card image plus a Hailo re-measure.

**The project folder is now a git repo.** Commit `6d928cc` is the code as
found, byte-identical to the Pi's `/home/pi/smartcane` (9 of 9 files and the
unit). Tag `consumer-baseline-before-phase1`.

**CRITICAL: vision had been dead for 1 h 46 min with no warning.** 19
under-voltage events from 18:03 to 18:19, last camera-derived speech 18:19:49,
then 33 Hailo `Device disconnected` lines and a PCI rescan at 18:29. After
the rescan `hailortcli fw-control identify` works but the benchmark runs at
**0.00 FPS** (`HAILO_TIMEOUT`) and detect.py hangs in `hailo.run`. The service
stayed `active`, `NRestarts=0`, and spoke only ToF warnings. **A PCI rescan
is not a recovery: identify passing does not mean inference works.** The
ground-sensor fault is announced ("Warning, ground sensor not working"), the
vision fault is not. Power is the cause, so Step 1.2 is the fix.

Other measured facts worth keeping:

- **Camera FOV is about 98 degrees, not 120.** Picamera2 picks sensor mode
  1536x864, a centre crop (768,432,3072,1728) of the sensor. detect.py's
  `--hfov 120` makes the ±10 degree "ahead" corridor about ±6.7 degrees in
  reality. The 16:9 crop is squeezed into 640x640, 1.78x horizontally. Indoor
  bench: exposure pinned at 66.2 ms, gain 11.6, 42 lux.
- **Every SSH logout restarts PulseAudio** (12 of 12 since 19:47, 134 starts
  vs 355 SSH sessions this boot, 89 `AUDIO DEAD` events healed in ~2 s).
  Bench artifact, but never measure audio with an SSH session open.
- **`journalctl --user` finds nothing on this Pi.** Read user units with
  `sudo journalctl _SYSTEMD_USER_UNIT=smartcane.service`.
- **Full ESP32 `read-flash` fails at 0x2A000** at 921600 and 460800 baud,
  with `cp210x ... failed set request 0x12 status: -110`. Use `verify-flash`
  (MD5 on chip) to prove firmware identity. Running firmware verified equal
  to the 19:22 build (app sha256 `12a2c90d...`). Rollback written back and
  verified. Files and restore commands in `baseline/`.
- ESP32 link steady state 19.87 Hz, interval P50 50.0 / P99 60.0 / max
  60.1 ms. ESP32 reset to first report 858 ms (3 trials), of which ~400 ms is
  the blocking "alive" double buzz. EN reset reports as `POWERON_RESET`.
- Opening the serial port delivered 2,676 duplicate stale D lines in 90 ms
  even after `reset_input_buffer()`. Too fast for the UART, so a Pi-side
  buffer. Open item for Step 1.5.
- ToF 2 still absent (loose wire). ToF 1 mean 90.3 mm, stdev 1.04 mm, 1,152
  samples, 0 dropouts.
- Boot this time 9.394 s (5.823 kernel), not 6.8 s. Cause not known.
- Power: firmware sees `max_current 3000`, `usb_max_current_enable 0`, so the
  USB ports (ESP32 + motor) share 600 mA. EXT5V 4.868 to 5.006 V during a
  light-load window.
- Earbuds now `Bonded: yes` with a stored link key, so the pairing problem
  from step 3f is fixed.
- `icecast2` still listens on port 8000.

**Tooling lesson:** the first measurement script wrote the ESP32 flash with
no check that the read had succeeded. The read failed, esptool refused the
missing file, nothing was written, but the bench ESP32 sat in its bootloader
for ~85 s. Flash work now goes only through `code/tools/esp32_backup.sh`,
which verifies before it writes. Also: `pkill -f <name>` over SSH kills the
SSH session itself when the command line contains `<name>`. Use
`pgrep -f "[n]ame"`.

**Next:** Adeel powers down, images the SD card, powers up on the same
supply. Then re-measure Hailo and vision, close Step 1.1, and start Step 1.2
(USB-C 5 V / 5 A supply). Ask Adeel whether he has the official 27 W supply
and an inline USB-C power meter for Step 1.3.

---

*Last updated: 2 October 2026*
