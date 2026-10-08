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
  folder `D:\smart cane 2.0` (moved there from `E:\Work\new smart cane 2.0` on
  8 Oct 2026). New work goes under the Session log (section 14).
- **Everything for the project lives in `D:\smart cane 2.0`**: the git repo,
  `datasets\` (merged_v2, runs, Hailo build files), `envs\` (training venv,
  WSL distro with the Hailo compiler), `backups\` (SD image). Nothing anywhere
  else (Adeel, 8 Oct 2026).
- **Public repo**: https://github.com/adeliusa486/KSCDR-Hackathon-SmartCane2.0.
  No AI co-author lines or credits in commits, PRs or files (Adeel, 8 Oct 2026).
- Code lives in `code/`, step-by-step guides live in `docs/`.
- Prices in USD, retail target in INR.

---

## 13. Repository layout

Current layout: see the "Repository layout" section of README.md (8 Oct 2026).
The tree below is the 2 Oct 2026 state, kept for history.

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

### 2 October 2026: Step 1.1 closed (PASS), SD card imaged, Hailo back

**SD card image done.** `backups/sd_2026-10-02.img`, 31,914,983,424 B, sha256
`ceeda806...60cb` (full value in `baseline/README.md`). Read in 32 min at
16 MB/s through the laptop's USB card reader, with the read-only script
`code/tools/sd_image.ps1`, launched elevated from a non-admin VS Code via
`Start-Process -Verb RunAs` (Adeel clicks one UAC prompt, no VS Code
restart needed). `code/tools/sd_image_check.py` checks MBR, FAT32 and ext4
headers without mounting. The laptop has ONE physical SSD: C:, D: and E:
are partitions of it, so the image still needs a copy on a separate device.

**Hailo restored by a power cycle on the same UPS supply.** 58.17 FPS,
13.14 ms, 0 disconnect lines. detect.py 81 / 83 report lines in 30 s at
fps 15 / 30 (about 5 s of each run is start-up, so ~83 is the ceiling at
`--interval 0.3`). F1 is a power-state fault, not chip damage. EXT5V dipped
to 4.769 V during the benchmark vs 4.868 V at light load. No under-voltage in
the 3 min window, but the margin is thin. Retest tool:
`code/tools/vision_retest.sh` (the vision half of `baseline_window.sh`).

Boot this time 6.995 s (3.398 kernel + 3.597 userspace), against 9.394 s on
the 18:04 boot. Boot time varies by 2.4 s, cause unknown.

After the retest the earbuds did not reconnect
(`br-connection-profile-unavailable`), so the service ran with AUDIO DEAD.

**Next:** Step 1.2 (5 V / 5 A USB-C supply, 30 min / 60 min / 2 h load runs).
Needs from Adeel: the supply, and ideally an inline USB-C power meter for
Step 1.3. Phase 1 still has Steps 1.2 to 1.5 before its gate. A DRAFT Phase 2
prompt was written early at Adeel's request (`docs/phase-prompts/phase2_DRAFT.md`)
and must be revised at the Phase 1 gate.

### 2 October 2026 (evening): Phase 2 draft fixed, Step 1.2 Part A (BLOCKED)

**Phase 2 draft revised** (`docs/phase-prompts/phase2_DRAFT.md`) after a check
against the code. Corrections that matter beyond Phase 2:

- A down ToF that **stops answering** never raises the drop alarm
  (`watchGround()` only runs on fresh, ok readings). The Pi says "Warning,
  ground sensor not working" after 3 s of `ok=0`, but **the ESP32 has no
  haptic fault signal**, so with the Pi or the earbuds down the user gets
  nothing.
- The relearn (`RELEARN_MS`) at a drop that reads "nothing in range" never
  completes: ground watching stays off with no warning.
- The `D` line is a median of 3 resampled from ~30 Hz to 20 Hz, and failed
  reads leave no trace. Sensor characterization needs a raw logging mode.
- The down ToF runs in default mode (~1.2 m), the forward one in long-range.
- The 98 degree FOV is straight-lens arithmetic on a barrel-distorted lens. An
  estimate only.

**Step 1.2 Part A: the UPS supply fails at normal load.** Record in
`experiments/phase1/step1_2_power/`. The load ladder hit under-voltage 43 s
into the plain service phase. **11 under-voltage events in 9.5 min** on the
21:26 boot with nothing heavier than the service. 1 Hz EXT5V never read below
4.749 V, so the dips are under 1 s: judge a supply by the kernel event count.

**The Pi dropped off the network at ~21:20** and came back on a new boot at
21:26:23. Cause unknown, because the journal was `Storage=volatile`. The
journal is now persistent (`/etc/systemd/journald.conf.d/50-smartcane-persistent.conf`,
200 MB cap). Boot took 11.1 s.

**After that boot the service's ESP32 link stayed dead** ("ESP32 LINK SILENT",
no recovery in 80 s) while the ESP32 was sending. A restart fixed it. The
reader thread never reopens the port. Also `cp210x ... failed set request
0x12 status: -110` (probably the purge from `reset_input_buffer()`), which
may be behind the F5 stale burst. Both for Step 1.5.

**`smartcane.service` left STOPPED** at 21:37 so the bench Pi stops browning
out. `systemctl --user start smartcane.service` to bring it back.

Tools: `code/tools/power_soak.sh` (1 s logger + load phases + abort on
under-voltage, deployed to `~/smartcane/tools/`), `code/tools/soak_summary.py`.
Lessons: Python `write_text` on Windows writes CRLF, which breaks bash on the
Pi. `pgrep -f detect.py` also matches `speak_detect.py`, use
`smartcane/[d]etect.py`. `speak_detect.py` never logs detect.py's reports.

**Next (needs Adeel):** power down, remove the UPS feed from the 5V header pin,
plug a 5 V / 5 A USB-C PD supply into the Pi's USB-C port, power up. Then
Step 1.2 Part B runs remotely (~4 h). Steps 1.3 (inline USB-C power meter)
and 1.4 (ToF 2 rewiring) also need hands on the hardware.

### 2 October 2026 (late): draft prompts for Phases 3, 4 and 5

Adeel asked for the Phase 3 and remaining prompts before the Phase 1 gate.
Written as drafts in `docs/phase-prompts/` (`phase3_DRAFT.md`,
`phase4_DRAFT.md`, `phase5_DRAFT.md`), same format and tags as the Phase 2
draft. Each is finalised only at the gate before it.

Found while checking the code for the drafts:

- **The Pi can silence the ESP32's safety vibration.** In `updateMotor()` a
  manual `B` buzz is checked before the ground-hazard pattern, so `B0,5000`
  gives 5 s of silence. `A0` turns off obstacle and hazard buzzing until
  reset. Breaks "ESP32 = independent safety layer". Owner Step 1.5, else 4.2.
- **The ESP32 is powered from the Pi's USB port**, so a Pi power loss,
  shutdown or low-battery cut-off takes the safety layer down with it.
  Step 1.5's "reboot Pi" test must measure this.
- **Custom classes would never be spoken by name.** `resolve()` names only
  classes in the hard-coded `RELEVANT` set (COCO). And `extract_detections()`
  silently drops class indexes beyond the label file, so a 93-class HEF with
  `coco.txt` loses its 13 hazard classes with no error.
- **Urgent speech cannot interrupt.** A ground warning waits up to 2 s for the
  current sentence, then is dropped.
- **The training pipeline has no data step.** `prepare_datasets.py` never
  applies `LABEL_ALIASES` and never fills `images/train` or `images/val`.
  `C:\ml\smartcane` holds 90 KB, no dataset downloaded. `classes.yaml` has
  93 classes, its header still says 88.
- **WSL2 now works** (correction to the 19 Sept entry): Ubuntu starts, kernel
  6.18.33, sees the RTX 4060 (driver 595.79). Inside it: Python 3.14.4, no
  torch, no Hailo DFC.
- **The persistent journal is in RAM.** `/var/log` is a 128 MB log2ram
  tmpfs, synced daily (23:55) and at clean shutdown, so a brownout still
  loses the logs. `SystemMaxUse=200M` exceeds the tmpfs. Logged as G7 in
  `experiments/phase1/step1_2_power/failure_log.md`.
- SSH password login is not disabled (Debian default). For Step 5.10.
- picamera2 documents `"RGB888"` as [B, G, R] byte order. detect.py feeds it
  to the HEF as is. Not verified which order the HEF wants. Phase 3 item.

### 2 October 2026 (night): "run all these", Pi offline, prep on branches

Adeel asked to run all phase prompts. **The Pi was off the network**
(no ARP reply at 192.168.3.51 from about 22:00). Adeel says it should be on,
so it probably browned out or lost Wi-Fi on the UPS feed again. Needs a
power cycle. With the journal still in log2ram RAM (G7), the log of the
event is likely lost.

Adeel chose **prep in parallel**: later-step software built and tested on
the laptop in git branches, nothing deployed to the cane until its step's
turn, each step still run and recorded in order. Branches (not merged):

| Branch | What | Tested how |
|---|---|---|
| `prep/step1.5-esp32-safety` | firmware 1.5-prep (watchdog, reset reason + counters, Pi cannot silence safety patterns, A0 lapses after 60 s, Pi heartbeat, D-line seq, non-blocking boot buzz, self-test), `esp32_link.py` (reopen G4, drop repeats F5, heartbeat), test plan T1-T14 | unit test of `safety_logic.h` incl. a mutation check, link tests on a pty, clean ESP32 build with 0 warnings in our files. Not flashed |
| `prep/step3.0-trace` | `detect.py --trace / --frames`, `tools/trace_summary.py` | runs the real detect.py against stand-in picamera2/Hailo modules (`code/tests/fakes`) |
| `prep/phase3-data-pipeline` | `training/build_dataset.py`: merge, alias remap, split by group with duplicates joined, public data kept out of test, audit | synthetic sources with planted problems, 18 checks |

On `main`: `code/tools/journal_persist.sh` and the G7 pass criteria in the
Step 1.2 test plan (apply right after the USB-C supply, before the soak), and
`docs/research/hailo8l-models-and-licences-2026-10-02.md`.

Research findings (sources in that file):

- **The Pi is exactly on Hailo's 2025-01 suite**: HailoRT 4.20.0 + TAPPAS
  3.31.0 match the row DFC 3.30.0 / Model Zoo v2.14. Model Zoo v2.14 already
  has Hailo-8L HEFs for YOLOv8 n/s/m, YOLOv10, YOLO11 n/s/m, YOLOX, NanoDet,
  DAMO-YOLO. The Zoo lists yolov8s at 88 FPS, this Pi measured 58.17.
- HEFs from a newer compiler do not load on an older runtime. YOLO26 (Model
  Zoo 2.18) and Ultralytics' `format="hailo"` export (validated on HailoRT
  4.23) need a runtime upgrade on the Pi.
- **Licence: Ultralytics YOLOv8 (the current model), YOLO11 and YOLO26 need
  an Enterprise licence in a commercial product unless the project is
  AGPL-3.0.** Decision for Adeel before Phase 3 training.
- **Microchip completed its acquisition of Hailo on 21 Sept 2026.** Archive
  the exact compiler, runtime and Model Zoo used for any shipped HEF.

Laptop toolchain now in WSL: arduino-cli 1.5.1, `esp32:esp32` 3.3.12, Pololu
VL53L0X 1.3.1 (same as the Pi), g++ 15.2, venv `~/smartcane-test-venv` with
pyserial 3.5. A baseline build on the laptop is 16 bytes larger than the
Pi's: ESP32 images embed build date and paths, so builds never match byte
for byte across machines. Compare with `verify-flash`, not by hash.

Lessons: the first toolchain install "succeeded" (exit 0) while the ESP32
core download had failed with "connection reset by peer", because the
script's last command was an `echo`. Check the result, not the exit code. A
cached arduino-cli build prints no warnings, so warning counts need
`--clean`.

**Next, needs Adeel:** power-cycle the Pi. Then, in order: Step 1.2 Part B
(fit the 5 V / 5 A USB-C supply, apply `journal_persist.sh`, soak runs),
Step 1.3 (power meter), Step 1.4 (ToF 2 rewiring), Step 1.5 (flash the
prepared firmware, T1-T14). Decide the model licence route before Phase 3.

### 2 October 2026 (late night): Pi back, journal fix tested, new direction from Adeel

**Outage explained (G8), my earlier reading corrected.** wtmp and the synced
journals show the Pi did not crash: "Power key pressed short" at 22:09:17 and
22:45:46 (clean shutdowns), power-on 22:53. Only 21:51 to 22:09 is
unexplained: associated to Wi-Fi, no under-voltage, but no ARP reply. Wi-Fi
power save suspected, not proven. Also: the Pi WAS reachable 22:09 to 22:45
(an SSH login of mine at 22:24 succeeded silently), so "Pi offline" in the
previous entry was only partly true.

**G7 journal fix applied** (Step 1.2, still on the UPS supply, service kept
stopped). log2ram off, journal on the SD card, `SyncIntervalSec=15s`, and
**`SplitMode=none`**: with the default per-user split, every line from user
`pi` (smartcane.service) was lost after a crash, 4 of 4. J1 pass, J2 pass 3/3,
J3 fail (log blind window ~3 s before a crash, even for CRIT lines), J4 0 ext4
errors in 11 crash-reboots (sysrq proxy, real plug pulls still to do).
**The ESP32 restarted with the Pi in 11 of 11 Pi resets** (Step 1.5 T10).

**Adeel's decisions:**

- **No model licence for now**: the cane is a professional prototype for
  presentation. Revisit before any sale (Step 5.11).
- **Target environment: USA and Gulf roads and sidewalks, plus general
  objects.** Replaces the India focus.
- **Speech: English with US terms** (sidewalk, curb, crosswalk, trash can).
- **150 object classes.** Adeel will create Hailo Developer Zone, Mapillary
  and Roboflow accounts.
- Wants ToF 1 distance accuracy and ToF 2 ground-hazard accuracy checked, and
  professional vibration hardware.

**Done:**

- `code/training/classes_v2.yaml` (branch `prep/phase3-150-classes`): 150
  classes with spoken US names, danger, reason, sources. 104 have data now,
  46 need the Mapillary/Roboflow accounts, 4 are surfaces (curb, crosswalk,
  fence, rail track). `check_classes.py` validates source names.
- Open Images pipeline proven end to end on 18 real photos. **Full download
  started**: 115 labels, up to 1,500 train + 150 val images each, to
  `E:\smartcane-data\oiv7`, log `E:\smartcane-data\oiv7_fetch.log`. FiftyOne
  cache in `E:\smartcane-data\fiftyone-zoo` (2.8 GB of annotation files).
- `code/tools/tof_check.py` on main and the Pi: guided distance check against
  a tape-measured target, fixed pass limit. ToF 1 now reads 143 mm on the
  bench (was 90 mm, the bench changed). ToF 2 still needs rewiring (Step 1.4).
- `docs/research/haptics-upgrade-2026-10-02.md`: TI DRV2605L + LRA, first in
  PWM input mode on GPIO 13 so firmware and tests stay valid.

**Next:** Open Images download finishes. Adeel sends the Roboflow key,
downloads Mapillary Vistas + MTSD and the Hailo Dataflow Compiler 3.30.0 wheel
(matches HailoRT 4.20 on the Pi). Then pseudo-label the gaps, train, compile.
Hardware steps unchanged: USB-C supply, ToF 2 rewiring, tape-measure ToF 1.

### 3 October 2026 (night): no Hailo compiler access, legitimate route found

Adeel cannot register at the Hailo Developer Zone (work email required, his
university email was refused too). Unofficial GitHub copies of the Dataflow
Compiler were ruled out: licence breach, and an untrusted compiler would build
the file that runs on the cane.

**Route chosen instead (all official, no Hailo account):**

1. **Ultralytics Platform managed Hailo export**: "no local Hailo account or
   DFC installation is required", `hailo8l` target, custom class counts
   supported (docs.ultralytics.com/integrations/hailo). Its output is
   validated on **DFC 3.33 / HailoRT 4.23**. Pricing not checked yet.
2. That HEF will not load on the Pi's **HailoRT 4.20**, and Raspberry Pi's
   bookworm apt repo stops at 4.20 (checked 3 Oct). But **HailoRT and its PCIe
   driver are open source (MIT) on GitHub**, branch `hailo8` for Hailo-8/8L,
   tags `v4.23.0` in both `hailo-ai/hailort` and `hailo-ai/hailort-drivers`.
   The driver repo's `download_firmware.sh` fetches the chip firmware from
   Hailo's public S3. So the Pi can be upgraded to 4.23 from source. A tested
   change with the SD image as rollback (DKMS broke once, 19 Sept).

Adeel also wants **more than 150 classes** ("about 80 % of objects"). Agreed
approach: measure, don't guess. Use exhaustively labelled street photos
(Mapillary Vistas val) to measure what share of objects the list covers, add
the most frequent missing kinds, and test-compile larger class counts on the
Platform to find the Hailo-8L limit. Note for Adeel: covering 80 % of object
kinds is not the same as naming 80 % correctly. More classes usually lowers
per-class accuracy. Both get measured.

Downloads running overnight: Open Images (E:\smartcane-data\oiv7), Mapillary
Vistas v2.0 (browser, auto-moved to D:\smartcane-data\raw\mapillary_vistas),
MTSD fully annotated (D:\smartcane-data\raw\mapillary_mtsd, md5-checked).
Roboflow key saved as Windows user env var ROBOFLOW_API_KEY (not in git).

### 3 October 2026 (00:15 to 02:10): data assembled, overnight pipeline running

Adeel asked for the highest accuracy ("no mistake is acceptable") and for
everything to run unattended until morning. Told him plainly: no detector is
mistake-free. The design answer: never guess a name (say "obstacle"), keep
safety on the ToF/ESP32, and measure per-class accuracy before presenting.

All on branch `prep/phase3-150-classes` (not merged, not deployed):

- **Class list now 152, every class with verified training data**
  (`check_classes.py --expect 152`: 152 of 152). Every source label name is
  checked against the real lists: COCO, Open Images, Mapillary Vistas
  `config_v2.0.json`, MTSD annotations, Roboflow registry. The Vistas check
  caught two wrong names (crosswalk zebra, billboard) that would have given
  those classes no data.
- **Coverage measured: 93.0 %** of 117,974 countable objects in 2,000
  exhaustively labelled Vistas street photos fall in our classes (target 80 %).
  Biggest gaps: shop signs, banners, CCTV, left out on purpose. Streets only.
- Classes with no usable data anywhere were replaced, not kept weak: parking
  block, vending machine, scaffolding, handrail, glass door (56 images), bus
  shelter OUT. Sidewalk sign (A-frame, 2,926), kiosk, sidewalk closed sign,
  crosswalk button, coffee table, nightstand, chest of drawers, wardrobe IN.
- **Roboflow sets checked through the API before use** (`roboflow_sources.yaml`,
  20 sets, ~58k images, CC BY 4.0 / public domain). Rejected after checking:
  "elevator" = buttons, scooter set with nonsense labels, vending = drink
  products, scaffolding = parts, glass-door project deleted.
- **Roboflow exports contain augmented copies** of each photo across splits:
  adli/pillar v4 = 17,450 files for 298 photos. `dedupe_roboflow.py` keeps one
  per original. Without it, test accuracy would be inflated by copies.
- Windows 260-char path limit broke one Roboflow set; names are now shortened
  without breaking image/label pairing.
- **MTSD**: two downloaders ran at once by accident (a stopped task kept
  running), corrupting train.0 and train.1: caught by md5, re-downloaded,
  train.0 verified OK, train.1 in progress. Also: Edge saved Vistas under a
  CDN hash name, so the watcher never fired; found and moved by hand.

Data on disk: Open Images `E:\smartcane-data\oiv7` (still fetching),
Vistas `D:\smartcane-data\raw\mapillary_vistas` (CRC OK, unpacked) and
`D:\smartcane-data\vistas_yolo`, MTSD `D:\smartcane-data\raw\mapillary_mtsd`,
Roboflow `D:\smartcane-data\raw\roboflow`, COCO `D:\smartcane-data\raw\coco`.

**Overnight pipeline running** from a frozen copy
`D:\smartcane-data\pipeline_code` (commit 336019d), log
`D:\smartcane-data\pipeline.log`. It waits for each download, then MTSD
convert, Open Images extra classes, Roboflow re-fetch, COCO layout,
`build_dataset.py` (caps: COCO 40k, MTSD 30k) with leakage audit, stops if any
class has no boxes, pseudo-labels with yolo11m + yolov8m-oiv7, then trains
YOLO11s on 152 classes, 40 epochs, batch 12, run `smartcane152_v1`.
Expected: training starts around 9-10 a.m. on 3 Oct, about 1.5 days to finish.

Not done without Adeel: no change to the cane (HailoRT 4.23 upgrade, firmware),
no Ultralytics Platform sign-up (cost unknown).

### 3 October 2026 (morning): HailoRT 4.23.0 installed on the cane (Adeel approved)

Built from Hailo's open-source repos (hailort + hailort-drivers, tag v4.23.0)
on the Pi with `code/tools/hailort_build.sh`: 14 min, 2 cores, 0 under-voltage.
The Python binding is a separate CMake project: build it with
`LIBHAILORT_PATH` and `HAILORT_INCLUDE_DIR` set **as environment variables**
for `setup.py bdist_wheel`, or the packaging step fails (it runs its own cmake).
`hailort_service` was not built (needs gRPC, an hour of CPU on the weak supply)
and is not needed: the cane runs one vision process. The 4.20
`hailort.service` is disabled.

Installed with `hailort_install.sh` (tests + automatic rollback): driver in
`/lib/modules/<kernel>/extra/` (DKMS 4.20 module removed), firmware 4.23 with
the 4.20 copy kept as `hailo8_fw.bin.4.20`, `libhailort.so.4.23.0` and
`hailortcli` in `/usr/local`, `hailo_platform` 4.23.0 via pip --no-deps.
Rollback: `hailort_rollback.sh` (reinstalls apt 4.20). 4.20 files also in
`backups/hailo420_files.tgz`.

Results: identify = firmware 4.23.0 HAILO8L. Current `yolov8s_h8l.hef`
benchmark 58.74 FPS / 12.98 ms (58.17 / 13.14 on 4.20). detect.py 71 report
lines in 30 s (81 on 4.20, within start-up variation, watch it). **1
under-voltage event during the tests** (UPS supply). After a reboot: driver
auto-loads, firmware 4.23.0, Python 4.23.0, benchmark 58.42 FPS.

**After any kernel upgrade the 4.23 module must be rebuilt**, or the cane has
no NPU driver. Do not run `apt full-upgrade` without that in mind.

### 3 October 2026 (13:05): training set v2 built, pseudo-labelling on GPU, handoff

`merged_v2` built 09:30 to 12:38 after fixing the v1 data loss (polygon
labels, export label names): all 152 classes have boxes, 235,951 train images.
Pseudo-labelling first spent 22 min on Python's one-by-one backup of 263,857
label files (86,523 done); stopped, finished with `robocopy /MT:32` in 24 s,
resumed. pseudo_label.py now decodes once on 8 threads with FP16 real
batches: GPU 73 %. Training (YOLO11s, 152 classes, 40 epochs, run
`smartcane152_v2`) starts automatically after it, from a background job.

Adeel moved to a new chat: `docs/handoff-prompt.md` has the full prompt.

### 3 October 2026 (13:05): new chat, status check only

Read the handoff, plan, phase drafts and research. Nothing changed on the
cane or in the pipeline.

- **Pseudo-labelling running** (PID 86780, started 13:01:05, the copy in
  `pipeline_code` matches commit 5b7ac95). Measured 37 images/s (4,480 at
  13:03:14, 6,560 at 13:04:10) over 263,857 images (235,951 train + 27,906
  val). If the speed holds it finishes around 15:00. Training then starts on
  its own: the old chat's PowerShell command chains `train.py ... --name
  smartcane152_v2` after a successful pseudo-label exit (read from that
  chat's transcript). `yolo11s.pt` is not on disk, Ultralytics downloads it.
- **Laptop limits the GPU**: on AC, but power limit 35 W (board max 110 W),
  SM clock 1530 of 3105 MHz, Windows plan Balanced. The vendor power mode
  likely sets this. Performance mode would speed up both jobs (not measured).
  Sleep and hibernate are off on AC and battery, so the run will not pause.
- **Risk**: the job is a child of the old chat's shell. Closing that VS Code
  window or chat may kill it.
- **Cane (read-only check, 13:04)**: up 5 h 07 min, `throttled=0x0`, 0
  under-voltage events this boot, `smartcane.service` stopped (enabled),
  Hailo firmware 4.23.0 HAILO8L, kernel 6.12.109+rpt-rpi-2712, ESP32 on
  `/dev/ttyUSB0`. Idle, so this says nothing about the supply under load.

### 3 October 2026 (13:50 to 15:05): pseudo-labels checked, two bad kinds removed before training

Adeel asked "is it working correctly". Checked results, not just the process.

- **Files are correct.** All 46,516 label files changed by 13:55: 0
  malformed lines, human labels never altered (human file is always an exact
  prefix), every file has human + added lines exactly. A 3,000-file sample
  later gave the same.
- **Most added boxes are real objects** the sources left out (8 random
  images drawn and looked at: buses, cars, traffic lights, trees, birds).
  Median teacher confidence 0.693.
- **Two kinds are wrong:**
  - **Dashcam bonnet called "car"**: on MTSD photos the COCO teacher boxes the
    recording car's bonnet or dashboard. Wide (w > 0.6) car boxes touching
    the bottom edge: 2,419, and 8 of 9 random ones were the bonnet.
  - **"stop sign" on non-stop signs**: 16 random ones were ~4 stop-sign
    faces, ~5 backs of signs, ~7 plainly wrong (VW logo, "76" sign,
    "PREMIER", backs of round signs, a European no-left-turn sign).
- **Adeel chose: clean, then train.** `code/training/clean_pseudo.py`
  (branch `prep/phase3-150-classes`, commit cda9a40) removes only boxes listed
  in `pseudo_labels.csv`, matching from the end of each file so a human box
  is never removed, logs them to `pseudo_removed.csv`. Unit test passes. Dry
  run at 14:35: 2,419 bonnet + 539 stop sign, all found in the files.
- **Hand-over mechanism**: `merged_v2\smartcane.yaml` renamed to
  `smartcane.yaml.hold` at 15:01, so the old chain's `train.py` exits at once
  with "no dataset descriptor" (before any run folder is made).
  `pipeline_code\after_pseudo.ps1` (PID 7512, started through WMI so it is
  not tied to any chat) waits for that, cleans, checks a second dry run
  finds 0, restores the yaml and starts the same training
  (`--model yolo11s.pt --epochs 40 --batch 12 --name smartcane152_v2`). It
  does nothing if pseudo-labelling fails. Tested on fake folders: the test
  caught a bug (PowerShell variables ignore case, `$code` overwrote `$Code`).
- **Speed is falling**: 37 images/s at 13:04, 24 at 14:03, 20 by 15:01
  (159,328 of 235,951 train). If 20/s holds, pseudo-labelling ends about
  16:30 and training starts a few minutes later. GPU now draws up to 84 W
  at ~2,520 MHz (was capped at 35 W), but swings 0 to 99 % busy: the
  per-batch Python work between GPU calls is the limit now. Not changed
  mid-run.

**15:10: Pi shut down cleanly** at Adeel's request (`sudo shutdown -h now`
after checking the service was stopped and no install or build was running).
It stopped answering ping 20 s later. The ESP32 is powered from the Pi, so it
is off too. Not needed until a hardware step (USB-C supply, ToF 2 rewiring,
tape-measure test) or until a converted model is ready to test.

**15:18 progress check**: 177,792 of 235,951 train images at 18.6 images/s
(val, 27,906, still to do). Estimated end ~16:35, then cleaning and
training. Spot check of 20 random added boxes on Open Images photos: 16
clearly right, 1 clearly wrong (an archer's bow called umbrella), 3 doubtful
(loose papers called book, a dark chair, a blurred far person). No model
accuracy exists yet: that comes from training.

**16:00 to 16:35: MTSD stop signs were labelled "traffic sign".** Human stop
sign boxes in merged_v2: 983 train + 113 val, all from COCO and Open Images.
MTSD has 824 usable stop signs (727 train + 97 val, 731 photos), but
`classes_v2.yaml` had no MTSD source for stop sign, so `convert_mtsd.py`
folded them into "traffic sign": two answers for one object. Adeel chose to
fix before training. `relabel_mtsd_stop.py` (commit on
`prep/phase3-150-classes`) changes the matching traffic sign line (IoU >= 0.9
with the MTSD box) to stop sign, logs to `mtsd_stop_relabel.csv`. Dry run:
573 to change in 899 photos, 466 too small to have been kept. Unit test and
a fake-folder run of the full watcher pass. `classes_v2.yaml` now lists
`mapillary-mtsd:regulatory--stop` (check_classes 152/152). Watcher replaced
at 16:32 (PID 62040, via WMI): cleanup, relabel, second dry runs must find
0, then training. Pseudo-labelling at val 10,048 / 27,906 at 16:32, end
expected ~16:50.

**16:55 to 17:08: data steps done, first training launch died, relaunched.**
Pseudo-labelling finished 16:55 (517,087 boxes added). The watcher then
removed 3,756 bad boxes (bonnet + stop sign) and relabelled 573 MTSD stop
signs. Second dry runs: 0 left for both. Training started 16:58 and **died
silently at the label scan (~16:59) together with the watcher**: no Python
error, no "train exited" line, nothing in the System or Application logs.
Most likely cause (not proven, no quota event logged): processes started
through WMI `Win32_Process.Create` run under the WMI provider host job,
`MemoryPerHost` 512 MB, and training needs GBs. The relaunch holds 1.6 GB
and lives. **Lesson: never start long or heavy jobs through WMI. Use Task
Scheduler.** Relaunched 17:02 as scheduled task `SmartcaneTrainV2`
(`pipeline_code	rain_v2.ps1`, battery stop off, no time limit, normal
priority), after removing the empty partial run folder so the name stays
`smartcane152_v2`. Failed log kept as `train_v2_wmi_died.log`. At 17:07 the
label scan was 29 % (~285 images/s, 3,328 background images, 0 corrupt).

**17:36 to 19:42: training far slower than estimated, three restarts.**
Measured, not the old 1.5-day guess:

| Setting | CPU perf | images/s | 40 epochs |
|---|---|---|---|
| batch 12, MuSGD, Balanced fan mode | 50-59 % | 19.6 | ~5.5 days |
| batch 12, MuSGD, MyASUS Performance (Adeel set it) | 88 % | 36 | ~3 days |
| batch 24, MuSGD, Performance | ~43 % | ~21 | ~5 days |
| batch 24, SGD, Performance (running) | ~42 % | ~27 | ~4-4.5 days |

- **Bottleneck: the main training process is single-core bound** (1.0 core,
  8 dataloader workers mostly idle, GPU 3-60 % busy at 14-45 W). py-spy
  (installed in `C:\mlenv`): ~35 % model forward, ~30 % optimizer step.
  Ultralytics 8.4.155 picks **MuSGD** for `optimizer=auto` on long runs; its
  Newton-Schulz step is many tiny GPU calls.
- **The laptop (ASUS Zenbook UX6404VV, i9-13900H) holds the CPU at ~43 % of
  base speed under sustained load**, even with MyASUS on Performance (Adeel
  confirmed) and Windows Best performance (tried, no change, reverted to
  Balanced). 78 C, no ACPI passive limit. The 88 % reading at 19:05 did not
  last. Batch 24 gave no gain per unit of CPU speed because the optimizer
  cost is per image. Nominal batch 64 (accumulation) either way.
- Adeel approved batch 24 and SGD (not fewer epochs). `train.py` gained
  `--optimizer`. Run `smartcane152_v2` restarted 19:32 (scheduled task
  `SmartcaneTrainV2`). Stopped runs kept: `smartcane152_v2_b12_stopped`,
  `smartcane152_v2_b24_musgd_stopped`, with their logs.
- Slip: the first batch-24 restart ran the old script because the repo was on
  `main`, not the branch with `train_v2.ps1`. Stopped within 5 s (exit -1),
  no run folder made. Check deployed files after copying.


### 3 October 2026 (21:05): ToF 2 rewired by Adeel, first check passes

Pi powered back on by Adeel, now **from the laptop's USB-C port**. The Pi
reads `max_current` 3000 mA from it (`usb_max_current_enable=0`), so USB
peripherals share 600 mA. **2 under-voltage events in the first 90 s**
(23.7 s and 86.3 s, `throttled=0x50000`) with `smartcane.service` starting
at boot, EXT5V 4.978 V at idle afterwards. A laptop port is not a fix for
Step 1.2: it still needs the 5 V / 5 A USB-C PD supply. Service stopped
again (it is enabled and starts at every boot).

ToF 2 after rewiring (service stopped, `esp32_capture.py`):

| Check | Result |
|---|---|
| `T` scan + ID | bus1 0x29, tof1 `EE AA 10`; bus2 0x29, **tof2 `EE AA 10`** (absent before) |
| `S` status | tof1 forward ok=1, tof2 down ok=1, reinits=0 both, ground learned 87 mm |
| 20 s, 400 D lines at 20.0 Hz | forward 400/400 ok, 113.2 mm mean, stdev 0.97, 110-116; **down 400/400 ok, 86.9 mm mean, stdev 1.17, 84-91** |

One `E unknown command` with garbage bytes on the first capture (the `T`
was mangled, `S` right after it was fine, `T` alone on a rerun was fine).
Same family as the port-open problems logged for Step 1.5, not a sensor
fault. This is a 20 s check, not Step 1.4's pass test (1 hour continuous,
wire-move, motor, disconnect and reconnect tests), and Step 1.2 is still
blocked, so by the plan's rule Step 1.4 has not formally started.


### 3 October 2026 (21:10 to 21:25): camera dark, new vibration patterns flashed

**"Camera not detecting"**: hardware fine (imx708 listed, Hailo fw 4.23.0
identifies). It was silent because `smartcane.service` was stopped (by me,
for the weak supply). A direct check: picamera2 metadata **0.9 lux**,
exposure 66.7 ms and gain 16 both at maximum, FocusFoM 7, photo almost
black. detect.py 30 s: no detections. The room was dark or the lens covered.
The service log of this boot also showed "distance sensors not responding"
(ESP32 resets with the Pi and the reader never reopens: G4, Step 1.5).

**Haptic change requested by Adeel** (out of the plan's order: this is
Phase 4 haptics work, done at his direct instruction):
- ESP32 firmware: ground alarm (ToF 2) **2 long pulses** (300 on / 150 off)
  instead of 3. Forward obstacle buzz (ToF 1 only) **smooth scale**: 60 %
  duty, 100 ms on / 600 ms off at 1.5 m, to 100 % solid at 0.4 m (was three
  steps). `S` now reports `motor=<duty>`.
- `speak_detect.py`: the sentence-start buzz takes its strength only from
  ToF 1 (`tof_buzz`: B60,150 at 1.5 m up to B100,400 at 0.4 m); objects ToF 1
  is not measuring get a fixed light `B60,150`. Unit-checked on the laptop.
- Flashed via `~/smartcane/tools/flash_2026-10-03.sh`: verify-flash of the
  running app against `~/smartcane/esp32/build` (rollback copy) passed, new
  app written to 0x10000 and verified on chip, boot 0.8 s, both IDs
  `EE AA 10`. New build in `~/smartcane/esp32/build_2026-10-03/`. Old
  speak_detect backed up as `speak_detect.py.bak-2026-10-03`.
- `tools/haptic_check.py`: reads the commanded duty at 20 Hz. Smoke test:
  ToF 1 at ~108 mm -> 100 % solid, correct.
- **Not yet tested**: the distance scale and the 2 pulses with a hand / a
  lifted cane, whether Adeel feels them, and speech + buzz end to end (needs
  the service, light, and the weak supply). The `prep/step1.5-esp32-safety`
  firmware must take these changes before it is flashed.
- Note: the boot "alive" signal is also two pulses (150 ms, shorter).


### 3 October 2026 (21:35 to 21:45): ToF 2 at 110 cm, one pulse, ground only

Adeel: both ToF sensors will sit **~110 cm up a 124 cm cane** (standard
length). ToF 2 "did not vibrate as you said". Asked: ToF 2 vibrates **once**
for a pothole or any ground change, **never for obstacles**. ToF 1 unchanged.

**Most likely reason it stayed silent (from the code, not yet seen on the
cane):** ToF 2 ran in default mode (~1.2 m at best, less on dark ground). At
110 cm the ground is at or past that range, so readings were "nothing in
range", the ground was never learned (needs 10 real readings), and no alarm
can fire before it is learned. Bench check before the change: down 66 mm,
ground learned, 0 H lines (the sensors were on the bench, not on the cane).

**Firmware changes** (`cane_safety.ino`):
- **Both sensors in long-range mode** (~2 m indoors). `R1`/`R2` no longer
  restart the sensors to move long-range mode.
- **Ground alarm = one 500 ms pulse at 100 %** (was 2 x 300 ms). 2.5 s
  hold-off unchanged, so sweeping back over the same hole within 2.5 s gives
  no second pulse. Sweeping over it again later does pulse again.
- **ToF 2 ignores obstacles**: a "rise" nearer than 0.7 x ground distance (at
  1.1 m: taller than ~30 cm) or any rise while ToF 1 sees something within
  1.5 m is treated as something standing in the beam: no alarm, no learning.
  Blocked 5 s = relearn. Drops are never ignored. Known gap: a real kerb
  while ToF 1 sees something ahead gets no ToF 2 pulse (ToF 1 is buzzing).
- **No second pulse when the cane comes back**: after a 2 s relearn (held
  over a drop), returning to the old ground within 10 s restores it silently
  (`I ground back to N mm`).
- Pi `speak_detect.py`: comment only. It speaks hazards without its own buzz.

Compiled on the Pi (320,827 bytes, 24 %), flashed with
`~/smartcane/tools/flash_2026-10-03b.sh` (running app verified against
`build_2026-10-03` first, which stays the rollback copy). New app in
`~/smartcane/esp32/build_2026-10-03b/`. Verified on chip, boot 0.4 s, both
IDs `EE AA 10`, ground learned 62 mm on the bench.

**Not yet tested**: anything at 110 cm. Need a capture with the cane held at
the real height (is the ground in range, how noisy, does a kerb edge give one
pulse). Mount note for Adeel: ToF 2 must point at the ground ahead of the tip,
not along the shaft, or the beam hits the cane itself. At 1.1 m the beam spot
is ~50 cm wide, so holes much smaller than that may not show. The
`prep/step1.5-esp32-safety` firmware must take these changes too.


### 3 October 2026 (21:50): mount angles recommended (geometry, not measured)

Adeel's mount: 127 cm cane, ToF 2 at 110 cm up the shaft looking down at
the road ahead, ToF 1 at ~115 cm aligned with the camera. Asked for the
angles. Assumed a normal walking grip: cane ~40 deg from vertical (range
30-50). At 40 deg ToF 2 sits 84 cm above the ground, ToF 1 88 cm.

| Sensor | Recommended aim (fixed on the shaft) | Result at 40 deg grip |
|---|---|---|
| ToF 2 | top face of the shaft, **15 deg further forward than the shaft line** | beam ~147 cm, lands ~50 cm past the tip, spot ~65 cm wide |
| ToF 1 + camera | **55 deg up from the shaft line** (5 deg above level when walking) | at 1.5 m the cone covers 68-135 cm height, ground never in the cone |

Why 15 deg: the 25 deg cone (12.5 deg half angle) must clear the shaft and
the white tip, or ToF 2 reads the cane (constant ~110 cm) and learns that as
"ground". 10 deg is inside the cone edge. 20 deg reaches 1.7 m, past what the
VL53L0X reliably gets from grey pavement. 147 cm is already near its limit
outdoors. The firmware learns whatever ground distance it sees, so the exact
number does not matter, only that it is steady and in range.

Check to run with the cane in hand (live capture): ToF 2 steady around
1,300-1,500 mm = good. Constant ~1,100 mm whatever the floor = seeing the
cane, tilt further. Frequent -1 = too far, tilt back to ~12 deg.


### 3 October 2026 (21:57 to 22:05): low-power profile for a 5 V / 3 A supply

Adeel: the UPS is 5 V / 3 A, or a 10,000 mAh power bank for the demo. Run
the camera and AI HAT on it. (The Pi was still on whatever fed it at 21:05,
the laptop USB-C by the last log, `max_current` 3000. Not confirmed.)

**Applied (backups `config.txt.bak-2026-10-03`,
`smartcane.service.bak-2026-10-03`):**
- CPU capped at **1.8 GHz**: `arm_freq=1800` in `/boot/firmware/config.txt`
  (from next boot) and `scaling_max_freq` 1800000 now. detect.py uses ~10-13 %
  of a core, so the cap costs nothing measurable.
- Camera **10 fps** (was 15) in `smartcane.service` (repo + Pi). The Hailo
  runs once per frame, so a third less AI load. Reports still every 0.3 s.
- Service started (`smartcane.service` active, detect.py running).

**Measured (`~/soak/lowpower_2026-10-03`, idle 30 s + service, abort on UV):**
SoC rails 1.8-2.0 W idle, 1.9-3.3 W with the service (rails only, no Hailo,
camera or USB). 1 Hz EXT5V 4.85-4.97 V. **One under-voltage event 13 s after
the service started** (22:00:38, normalised 22:00:40), the moment detect.py
opened the camera and Hailo. Wi-Fi ping lost for that second. Soak aborted
as designed and restarted the service at 22:01:43. **No further events** in
the steady state afterwards. No Hailo disconnect. The average load is far
below 15 W. The fault is a sub-second dip at start-up peaks, so the supply
path (supply response, cable, GPIO-pin feed) is the problem, not capacity.

**Hailo driver WARNING is old, not power**: `rwsem.h:80 find_vma` from
`hailo_vdma_buffer_map` comes in a burst of ~120 at every Hailo start, every
boot since the 4.23 driver (258 / 263 / 506 per boot). Kernel tainted W. No
disconnects. Belongs with the 4.23 driver on kernel 6.12. Watch, not urgent.

Earbuds flapped (AUDIO DEAD auto_null twice, reconnected in 1 s each) at
22:02.

**Next:** run a 15 min soak on the real battery (power bank USB-C PD 5 V
3 A, short 3 A USB-C to USB-C cable, into the Pi's USB-C port). If the UPS
only feeds the 5 V pin, use 2 x 5 V (pins 2, 4) + 2 x GND (6, 14) with short
thick wires. Dupont jumpers drop a few tenths of a volt at 2 A peaks.


### 3 October 2026 (22:10): end of session, Pi and PC shut down

- **Pi shut down cleanly** (service stopped, sync, `shutdown -h now`, off
  ping within 5 s). ESP32 is off with it. Everything from today is on the
  Pi: firmware `build_2026-10-03b`, 1.8 GHz cap, 10 fps unit. The service is
  enabled and starts at the next power-on.
- **Training stopped by the PC shutdown** (Adeel's choice). Run
  `smartcane152_v2`: epoch 1 of 40 done 21:30 (6,696 s, ~1.9 h per epoch,
  mAP50 0.386, mAP50-95 0.258 after 1 epoch), checkpoint
  `D:\smartcane-data\runs\detect\smartcane152_v2\weights\last.pt`. ~40 min of
  epoch 2 lost. **To continue: `pipeline_code\train_v2_resume.ps1`** (new,
  not in git; header has the Task Scheduler commands). Do not rerun
  `train_v2.ps1`, it starts from scratch. Remaining ~39 epochs is ~3 days at
  this speed.
- Nothing else was running.
- **22:15: Adeel asked to stop training now.** Task `SmartcaneTrainV2` stopped,
  all python processes ended, last.pt (21:30, epoch 1) intact. Resume as above.


### 4 October 2026: v2 training fell, v3 2-day fine-tune with watchdog

v2 resumed 10:31 (first resume used batch 12: Ultralytics takes batch from
the command line on resume, `train_v2_resume.ps1` now passes `--batch 24
--optimizer SGD`). mAP50 by epoch: 0.386, 0.398, 0.360, **0.225** (epoch 4,
right after warm-up ended at lr0 0.01). Adeel: done within 2 days, avoid bad
results, model must stay small for the cane.

**v3 (started 18:20, task `SmartcaneTrainV3`, `pipeline_code	rain_v3.ps1`):**
YOLO11s from v2 `best.pt` (epoch 2), SGD batch 24, lr0 0.002 cosine to 5 %,
warm-up 0.5 epoch, close_mosaic 4, patience 8, Ultralytics `time` 45.25 h
(deadline 6 Oct 16:20). Watchdog every 5 min: after 3+ epochs, last < 80 %
and previous < 90 % of the run's best mAP50 -> stop, retry from that best.pt
with half the lr (max 3 attempts, never past the deadline). train.py gained
`--lr0 --lrf --cos-lr --warmup-epochs --close-mosaic --patience --time`
(backup `train.py.bak-2026-10-04`). Progress is in
`train_smartcane152_v3.log` (stdout), not the .err.log. Laptop sleep and
hibernate on AC set to never. First line 18:3x: epoch 1, 2.7 it/s, ~1 h
per epoch shown at start (v2 epochs took ~2 h).

Pretrained alternatives re-checked for Adeel: no ready model covers street
hazards and runs on the Hailo-8L (COCO 80 / OIV7 600 / Objects365 / single
hazard models / open-vocabulary). v3 is already transfer learning from COCO.


### 6 October 2026: v3 done, Hailo compile, AI assistant (Gemini) live

**v3 result:** 25 epochs (restarted once at epoch 13 from best.pt). Best
epoch 24: mAP50 **0.536**, mAP50-95 0.376, precision 0.65, recall 0.49 on
27,906 val images (v2 best 0.398). Per-class numbers not measured yet.

**Hailo compile (PC, WSL Ubuntu):** DFC 3.34.0 in `~/hailo_dfc` (Python 3.10
via uv, `tensorflow[and-cuda]==2.18.0` added so TF sees the RTX 4060). DFC
5.4.0 wheel deleted: 5.x is Hailo-10H only. Files in `D:\smartcane-data\hailo\`:
`smartcane152_v3.pt/.onnx` (opset 11, 640), `_parsed.har`, `nms_config.json`,
`smartcane152_v3.alls`, `smartcane152.txt` (152 labels). End nodes
`/model.23/cv2|cv3.{0,1,2}.2/Conv` -> conv51/54, 62/65, 77/80, same as the
model zoo yolov11s. **On-chip NMS fails for meta_arch yolov8 on hailo8l**
(UnsupportedMetaArchError), so NMS is `engine=cpu` (HailoRT on the Pi, same
by-class output detect.py reads). optimization_level 2, 1,024 calibration
images (val, plain 640 resize, matches the Pi's lores stream). QFT ~12 s/step,
4 x 128 steps. Output will be `smartcane152_v3_h8l.hef`. **Risk:** DFC 3.34
may target HailoRT newer than the Pi's 4.23. Check the HEF loads before use.

**Pi IP:** first scan found nothing at .51 (Pi was booting). It came up at
192.168.3.51 as usual. 192.168.3.9 has SSH too but is an old device
(diffie-hellman-group1 only), not the Pi.

**AI assistant (Adeel: online only, free, Gemini):**
- `code/assistant.py` (new): short press = describe, hold = ask (records the
  earbud mic in headset profile while held, max 10 s, audio goes straight to
  Gemini). Models tried in order `gemini-flash-lite-latest`,
  `gemini-flash-latest`, `gemini-3.8-flash`, each with thinkingLevel minimal
  first. Flash-Lite ~2-10 s, Flash 20-30 s and often 503 today.
  `gemini-2.5-flash` is closed to new keys. One retry on 503.
- Key on the Pi only: `~/.config/smartcane/gemini_key` (600). Never in git.
- `detect.py`: SIGUSR1 -> full-res JPEG at `/dev/shm/cane_snapshot.jpg`.
- `esp32_link.py`: `on_button(pressed)` for `K down` / `K up`.
- `speak_detect.py`: wires the assistant, `--model` / `--labels` passthrough,
  `say_blocking()`, paplay timeout 30 s, PRIORITY now drop-offs first.
- Firmware `build_2026-10-06`: button D33 to GND, INPUT_PULLUP, 30 ms
  debounce, sends `K down` / `K up`. Flashed, runs.
- Pi backup of the old files: `~/smartcane/backup_2026-10-06/`.
- Verified: live snapshot -> Gemini -> reply ("too dark", lens was covered).
  **Not verified:** physical button (wiring unknown), earbud mic (earbuds
  were off, br-connection-page-timeout).

**22:31 HEF built and live.** `smartcane152_v3_h8l.hef` 25.7 MB, 5 contexts,
NMS by class (152 x 30), score th 0.2. **Loads on HailoRT 4.23** (no runtime
upgrade needed). `hailortcli benchmark` 38.7 FPS (old yolov8s 58). Service
now passes `--model ~/smartcane/models/smartcane152_v3_h8l.hef --labels
~/smartcane/models/smartcane152.txt`. Live camera 30 s: steady 10.0 fps.
Remove those two lines to return to COCO.

**Bug found and fixed before it shipped:** `RELEVANT` in speak_detect.py
held only COCO names, so with the new model stairs, curbs, potholes, open
holes, crosswalks etc. would all have been spoken as "obstacle". Added the
new street classes; detect.py PRIORITY gets drop-offs first.

**Text reading (OCR):** double press. Gemini reads a blurred bus-stop sign
word-perfect in 2.0 s. Offline fallback is Tesseract 5.3 (already on the Pi),
0.5 s, misread 10 as 40 on the blurred test sign.

**Tests:** `code/tests/test_cane.py`, 31 simulated scenarios (names for 27
safety classes, urgency order, flicker, obstacle fallback, ToF distance,
real Esp32Link on a pty with H drop/step and K down/up, sensor-dead warning,
every assistant path and failure). **31/31 pass on the Pi.**

**Real-photo hazard test** (`code/tools/hazard_eval.py`, 408 val photos,
2,964 objects, Hailo on the Pi, 30 ms per photo, single frame):
named 57 %, noticed (named or "obstacle") 68 %. Strong: wet floor sign,
e-scooter, dog, car, person, traffic light (80-95 % noticed), stairs 79 %,
pothole 76 %, open hole 76 %. Weak: pole 34 %, crosswalk 35 %, curb 35 %,
rail track 35 %, bollard 39 %, barrier 42 %. Poles, bollards and barriers
are what the forward ToF catches; curbs and drops are what the down ToF
catches. Child usually named "person" (15 % named, 92 % noticed). Construction
and bus stop signs rarely named (4 % / 0 %): double press reads them.
**Open question:** `--confirm 3` needs 3 reports in a row with the same
class, which hurts weak classes. Test lowering to 2 on a walk.

**Power:** `get_throttled` 0x50000 after the benchmark (under-voltage and
throttling happened since boot, 0x0 earlier). Demo needs the 27 W supply.
**Camera** saw only darkness all evening (lens covered or facing a dark
surface). SD: 32 GB card, 13 GB used, 15 GB free; cane code 150 MB, Hailo
models 205 MB + 26 MB new HEF; `~/hazard_eval` 161 MB (test photos, can go).

### 6 October 2026 (late, Pi off): investor demo dashboard

Pi shut down 23:3x at Adeel's request (assembly into the 3D-printed body
tomorrow, then test). Built offline, **not yet run on the Pi**:
- `code/demo_view.py`: with `detect.py --stream-file`, draws boxes (red
  drop-off, orange vehicle, yellow person/animal, purple obstacle, cyan
  other) and the ahead-corridor lines on a 960x540 copy of the main frame,
  writes `/dev/shm/cane_view.jpg` + `.json` each frame. Wrapped in try, so it
  can never stop detection.
- `code/demo_server.py` + `code/demo_dashboard.html`: `speak_detect.py
  --demo-port 8080` serves `/` (dashboard), `/stream.mjpg`, `/events` (SSE, 4/s:
  detections, fps, Hailo ms, ToF, ground state, temp, transcript). Stdlib
  only, no internet. Speaker.on_speak feeds the transcript (speech / hazard /
  assistant). Service file now has `--demo-port 8080`.
- Verified on the PC with fake detections and a real street photo
  (screenshot good). Tests: 33 (2 new dashboard), all pass on the PC
  (4 pty tests skip there, they passed on the Pi).
- **Tomorrow:** deploy, check the CPU cost (~20 ms per frame estimated) and
  temperature with the dashboard on, open http://smartcane.local:8080.
  At the venue, Pi and laptop on the same phone hotspot (add its SSID to
  the Pi beforehand with nmcli).

### 7 October 2026 (not logged at the time, reconstructed 8 Oct)

The cane was assembled into the 3D-printed body. Code changed and deployed
but never committed or logged: a second button on D32 (`J down/up`, reads
text), `P` (raw button pins), and speak_detect.py keeping the ESP32, buttons
and Bluetooth up while detect.py is restarted every 10 s. Firmware
`build_2026-10-07` flashed. Committed on 8 Oct from the Pi's backup copies.
Journal: boots at 20:29 to 21:30 all ended with a short press of the power
button. Four of them had "vision stopped (exit 1)" with the reason hidden
(stderr went to /dev/null). Power-bank attempts left no journal at all.

### 8 October 2026: deep review, vision and link fixes, public repo, one project folder

Adeel reported: only "person" detected (not tables, chairs), "person right"
when he stood in front, ToF distances wrong, wants meters, ToF 2 misses
drops, vibration nearly negligible, power bank (amber, red, off), and disk
space (C: 260 to ~113 GB free, ~400 GB on D:/E:). Asked for a deep plan,
fixes, a public repo and everything in one folder `D:\smart cane 2.0`.

**Root causes found (measured, details in docs/results.md):**
- **Serial link dead for whole sessions**: 3.5 h (7 Oct) and 10 h (8 Oct)
  with no D line reaching the Pi while the ESP32 ran (its uptime proved no
  reset). Kernel: `cp210x ttyUSB0: failed set request 0x12 status: -110`.
  Reopening the port fixed it at once. So every spoken distance was the
  camera's size word. **Fix:** esp32_link.py reopens after 3 s of silence,
  looks the CP2102 up again by id, and keeps looking if absent at boot.
- **Picamera2 "RGB888" = B,G,R bytes** (correlation -1.00 against the ISP
  JPEG, +1.00 for "BGR888"). The model trained on RGB got swapped colours.
- **16:9 squeezed 1.78x** into 640x640. Now 640x360 lores, letterboxed.
- A/B on 408 photos cropped to 16:9 on the cane's Hailo: old path 40 %
  named / 53 % noticed, new 55 % / 66 %. Camera turned 90 deg: 6 % / 13 %.
- **FOV**: code assumed 120, sensor mode crop gives 98.2, so "ahead" was
  +-6.7 deg. Now FOV from ScalerCrop, +-15 deg, or any box over the centre.
- Orientation: lying on the floor the picture is 90 deg turned (that is what
  the first snapshot showed). Held to walk it is upright: `--rotate 0`.
- Model weakness, separate from the bugs: desk recall 0.27, cabinet 0.09,
  curb mAP50 0.24, crosswalk 0.22, manhole 0.23 (per-class val today).
- Vibration: far pulses 100 ms at 60 % never spun the coin motor up.

**Deployed and verified on the cane (backups in ~/smartcane/backup_2026-10-08):**
detect.py (letterbox, BGR888, --rotate, FOV, +-15 deg, distance estimate
in m from box height for 60 classes, cross-class dedupe, upright snapshots,
one input buffer), speak_detect.py (meters: "1.2 meters", camera "about 2.5
meters"; ToF given to an object only if the camera estimate agrees within
2x; per-object repeat timers, duplicates once; detect.py stderr to the
journal; 3 s start-up grace; "Ground sensor cannot see the ground" after
20 s; buzz floor B80,200), esp32_link.py, demo_view.py (portrait),
tools/vision_probe.py, tools/hazard_eval.py (A/B options). Service: explicit
`--rotate 0`, **dashboard off by default** (it took detect.py from ~12 % to
73 % of a core). Tests 46/46 on the Pi. Dry run: "chair ahead, 1.3 meters"
(ToF) and "chair right, about 2 meters" (camera).

**Firmware 2026-10-08** flashed with `tools/flash_2026-10-08.sh` (verify
running == build_2026-10-07, write, verify, boot report): 40 ms full-power
kick per buzz, obstacle scale 80-100 % with 150 ms pulses, range-status
filter (rejects 1, 2, 3, 6, 9), `C<tof>,<mm>` offset calibration, `F0/F1`,
`Q0/Q1` raw stream, status counts and `fw=` in `S`. 1,514 + 1,515 readings
all status 11. Boot to ready 0.40 s. Held to walk: ground learned 1,407 mm.

**Lessons:** `pkill -f <pattern>` over SSH killed my own SSH session twice
(the note from 2 Oct still applies: use `pgrep -f "[n]ame"` or an anchored
pattern). Two copies of hazard_eval on the Hailo at once segfault. HailoRT
segfaults in a native thread when the Hailo context closes, so tools must
write results inside the `with Hailo` block. On this laptop one small file
takes ~17 ms to open (56 files/s); 32 threads read 884 files/s.

**Power bank:** amber then red = the Pi started and its power controller cut
out, a 5 V dip at the boot peak. Fix in docs/power.md (USB-C PD 5V 3A+,
short cable, or PD trigger 9 V + 5.1 V 5 A buck, or a 5 A UPS board).

**Public repo** https://github.com/adeliusa486/KSCDR-Hackathon-SmartCane2.0,
built in `D:\smart cane 2.0` from a clone of this repo. History rewritten to
drop the AI co-author trailers (Adeel: no AI attribution in any
commit) and a stock yolo11m.pt. Merged prep/phase3-150-classes (training
pipeline), training scripts as run for v3, models (HEF identical to the cane
by MD5, best.pt, ONNX), all merged_v2 labels as tar.xz, class and source
counts, docs (README, hardware, software, training, objects, results, power,
implementation plan), figures (sensor geometry, exploded view, cross-section,
schematic), MIT licence, data licences (Vistas CC BY-NC-SA 4.0, MTSD research
terms). Per-class validation: mAP50 0.535, mAP50-95 0.376.

**Disk (one physical SSD, C:/D:/E: are partitions):** project data was
D:\smartcane-data 425 GB (raw 168, merged_v1 88, merged_v2 88, MTSD/Vistas
conversions 50, hardlinked to raw), E:\smartcane-data 75.5 GB (FiftyOne cache
41, oiv7 export 33.5), repo backups 29.8 GB (SD image), WSL Ubuntu 27.9 GB,
C:\ml\venv 5.5 GB, pip cache 4.2 GB, fiftyone 3.4 GB. Adeel chose: delete
merged_v1, raw and the conversions, the OIV7 downloads, the training venv
and the pip cache, move WSL to D:, everything else into `D:\smart cane 2.0`.
The rest of C:'s growth is not this project (e.g. a 16.9 GB Kali VM in
Downloads, 33 GB of Windows update files in C:\$WINDOWS.~BT).

**Cleanup done (after the labels were pushed):** deleted merged_v1, raw,
mtsd_yolo, vistas_yolo, E:\smartcane-data, C:\Users\adeel\fiftyone,
C:\ml\venv, pip cache. WSL Ubuntu moved to `envs\wsl-ubuntu` (`wsl --manage
--move` moved the vhdx and then failed with E_ACCESSDENIED, registration
fixed by hand in HKCU Lxss BasePath, backup `envs\wsl-ubuntu-registry-backup.reg`,
tested: starts, ~/hailo_dfc 6.2 GB). The distro also holds Adeel's other
projects. D:\smartcane-data is now `datasets\` (merged_v2.yaml path
updated), SD image in `backups\` (sha256 verified), DFC wheel in `envs\`,
C:\ml leftovers in `datasets\from_c_ml` (a few KB of read-only .git files
stay in C:\ml\smartcane). Free space: C: 113 -> 157 GB, D: 531 -> 730 GB,
E: 175 -> 281 GB. The training venv must be recreated in `envs\venv`
(docs/training.md) before the next training run.
`E:\Work\new smart cane 2.0` is now a stale copy without backups: delete it
after VS Code is reopened at `D:\smart cane 2.0`.

### 8 October 2026 (afternoon): one-button assistant, live dashboard over the internet, website

**Button 2 = the assistant (D33 to GND, the only button).** Short press:
online, Gemini describes the scene, one buzz, listens 5 s for a question
(answered from a fresh photo). Offline: the cane's own detector summary, then
Tesseract reads any text. Hold 1 s: read text (Gemini online, Tesseract
offline). Internet checked on every press. Verified on the cane with the
earbuds off (earbud mic still untested).

**Why the public dashboard "did not work":** through a Cloudflare quick
tunnel the long-lived streams were held back. Measured from the laptop:
/events 0 bytes in 6 s, /stream.mjpg in 256 KB blocks, while single requests
(/state.json, /frame.jpg) passed in about 1 s. Same streams on the LAN: 35 KB
and 560 KB in 5 s. Fix: the dashboard now polls /state.json 4 times a second
and /frame.jpg on two staggered lanes. A synthetic-data probe server confirmed
it is the tunnel, not the cane's server.

**Dashboard always on.** `--demo-port 8080` is now in the service. The view
is drawn only while a request arrived in the last 5 s (demo_server touches
/dev/shm/cane_view.jpg.watch, demo_view.Viewer.due() checks it): detect.py
10 % of a core unwatched, 30 % watched. With no token file the cane creates
one (0600) and never serves the camera open. cloudflared 2026.10.0 installed
on the Pi. `tools/go_live.sh` waits until the new address answers (DNS takes
15 to 30 s, once more than 60 s) and keeps cloudflared's log in
~/.cache/smartcane/cloudflared.log.

**Verified through the public tunnel:** /health ok, 403 without or with a
wrong token, and the GitHub Pages live.html showed LIVE with camera, three
chairs with bearings (one ~3.9 m), ground 1.87 m vs 1.88 m learned. The
speech panel stayed empty because the earbuds were off (sink auto_null).
Every tunnel was closed after its test. Headless Edge screenshots fire at the
load event, before the first state arrives through a tunnel: wrap the page
in a frame whose load is delayed to capture real data.

**Recording:** 30 s, 100 frames, Adeel holding the cane at a room scene
(chairs, a wall unit labelled "tv", a wall labelled "bathtub" in 14 frames).
In `web/replay/`, played by live.html when no cane is connected; `?at=15`
starts at 15 s. Cane held up, so the down ToF saw ~1.9 m and said "drop
ahead" several times. Re-record at walking angle in a clearer scene.

**Website and CI/CD:** GitHub Pages enabled (source: GitHub Actions) at
https://adeliusa486.github.io/KSCDR-Hackathon-SmartCane2.0/ with live.html.
CI (62 tests, training tests, firmware compile, website build) and the Pages
deploy both pass. README rewritten with the live dashboard links and the four
charts. At Adeel's request: no "build it yourself" on the website or README,
nothing on the website or repo suggests it was made with an AI tool, the
AI-chat prompt files (handoff-prompt.md, smart-cane-prompt.md, phase-prompts/)
untracked and kept locally only (they remain in older commits), and the
exploded view taken off the README, website and hardware.md until Adeel
supplies a new image (prompt given to him).

**Open:** licence is still MIT while Adeel wants nobody else to build the
cane (his decision), docs/hardware.md and software.md still hold the full
assembly and setup steps, re-record the demo, earbud mic test.

### 8 October 2026 (16:30 to 16:45): "the live dashboard sticks on the chair"

Adeel: the live dashboard stays on the chair and does not move when the cane
moves. **Cause: the page was not connected to the cane at all.** It was
playing the 30 s chair recording (web/replay, 15:31) in a loop, the
website's fallback when no cane answers. Proof: the cane touches
/dev/shm/cane_view.jpg.watch on every dashboard request, and its last touch
was 16:20:57 (the earlier session's own test). No request for 12 minutes.
No tunnel was running, and the https website cannot reach the cane's
http://...:8080 on the LAN (browsers block that). The cane itself was fine:
frames advancing about 4 a second, boxes moving. The only label was the small
amber "Recording 2026-10-08" pill, easy to read as live.

**Fix in code/demo_dashboard.html:** the recording says "Recording from
<date time>, not live" on the picture and in the pill, with a note to connect.
Opening the page tries the last saved cane address first (/health, 4 s) and
plays the recording only if it does not answer. Connect live clears the
recording's picture and panels. A cane that stops answering greys the picture
with "Lost the cane. This picture is frozen until it answers again."
Tested in headless Chrome with a fake cane (recording, connect, picture
changes, lost, back, reopen with saved cane, reopen with cane off: all as
expected) and against the real cane on the LAN (Live, 10.6 fps, picture
changed 5 times in 3 s). Copied to the cane (old page in
~/smartcane/backup_2026-10-08b). The server reads the page per request, so no
restart.

**To watch live:** same Wi-Fi: http://192.168.3.51:8080/?token=<token>
(token in ~/.config/smartcane/demo_token on the Pi). Anywhere else: run
tools/go_live.sh on the Pi and open the link it prints.

Noted, not changed: the model calls the plain wall "bathtub" at 0.6 to 0.8
in this room. (`systemctl is-active smartcane` says inactive because it is a
user service: use `systemctl --user`. It was active since 15:57.)

---

*Last updated: 8 October 2026*
