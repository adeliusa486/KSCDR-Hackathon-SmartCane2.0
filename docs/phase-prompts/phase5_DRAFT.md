# PHASE 5 PROMPT (DRAFT): consumer product validation

> **DRAFT, written 2 Oct 2026 at Adeel's request, before the Phase 1 to 4
> gates.** State on that date: Step 1.1 PASS, Step 1.2 BLOCKED, everything
> after it not started. This draft is the furthest from real data. Expect to
> rewrite most numbers at the Phase 4 gate.
>
> Tags as in `phase3_DRAFT.md`: *(Step 1.x)* measured, *(code)* read from the
> code on 2 Oct, *(Pi)* read from the Pi on 2 Oct, *(MEMORY)* recorded in
> `MEMORY.md`, *(verify)* third-party fact or rule not checked today,
> *(gate)* and *(Phase N)* to be filled from those gates.
>
> Do not start Phase 5 from this draft. Rename it `phase5.md` only after the
> Phase 4 gate passes and every placeholder is filled in.

You are continuing the smart cane consumer-readiness work. The master prompt
is `docs/consumer-readiness-plan.md`. Its ABSOLUTE RULE, engineering
principles, section 12 release report and section 13 decision rule apply in
full. This prompt replaces only the master's Phase 5 section.

Phase 5 validates **the product that will ship**, not the bench prototype.
Every result is tied to a hardware revision, a firmware build, a software
commit and a model HEF, and is void if any of those change.

## How every step is recorded

`experiments/phase5/step5_N_<name>/`, same files as before. Tag
`known-good-phase-4` before the first change. Field and human trials also
keep: route description, weather and light, ground-truth video, the sync
event that aligns video to logs, and the trial log.

## Preconditions

Product decisions Adeel must make and write down before Step 5.1. Each one
changes what Phase 5 tests.

| Decision | Why it matters |
|---|---|
| **One-piece cane, or two parts** (chest clip with camera and compute, cane handle with ESP32, ToF, IMU and motor), as chosen in MEMORY.md section 8 | Two parts means the Pi-to-ESP32 link becomes wireless and the handle needs its own battery. Every link result from Phases 1 to 4 (USB serial at 19.87 Hz, stale burst, reconnect) must then be redone on the wireless link |
| **Shipping compute platform** | MEMORY.md section 10 plans a move to a K230 or RK3588 class custom board for cost. If the product does not ship on Pi 5 + Hailo-8L, Phases 3 and 4 run again on the new platform first. Phase 5 never validates a platform that will not ship |
| **Audio hardware** | Phase 4's measured choice *(Phase 4)*. Wired is the plan. An I2S DAC is blocked by the AI HAT+ header *(MEMORY, 2 Oct step 3b)* |
| **Battery and charger** | From Step 1.3's measured power budget *(gate)* |
| **Haptic actuator** | Today an ERM motor through a driver module on GPIO 13. MEMORY.md section 3 lists a DRV2605L with an LRA. Changing it means redoing Step 5.7 |

Gates: Phase 1 to 4 gates passed *(gate)*. Phase 4's fault matrix has no
silent failures *(Phase 4)*.

## Known facts carried into Phase 5

1. **The safety layer is powered by the Pi** *(MEMORY, 2 Oct step 3d)*. The
   ESP32 runs from the Pi's USB port. It survives a Pi software crash, but a
   Pi power loss, shutdown or low-battery cut-off also switches the safety
   layer off. Step 1.5 tests "reboot Pi" and measures what happens to the
   ESP32 *(gate)*. The product's power design must give the safety layer its
   own path, and it must be the last thing to lose power.

2. **Power** *(Step 1.2)*. The UPS feed into the 5V header pin failed:
   11 under-voltage events in 9.5 min at normal service load. 1 Hz EXT5V
   samples never fell below 4.749 V while the kernel flagged under-voltage,
   so the dips last under a second. Judge every supply by the kernel event
   count. Without USB-PD at 5 A the Pi firmware reports `max_current 3000` and
   limits all USB ports to 600 mA together *(Step 1.1)*.

3. **The battery tells the Pi nothing** *(MEMORY)*. A USB power bank gives no
   state of charge. "Battery low" is in the critical vocabulary, but today the
   first sign of a flat battery is an under-voltage event. The product needs
   a fuel gauge or a battery with a data line.

4. **Runtime is unknown**. "About 2.5 h on the 6000 mAh bank" in MEMORY.md is
   an estimate, never measured.

5. **SD card and logs** *(Pi, Step 1.2 G7)*. No overlayfs, so a power cut can
   corrupt the card. Logs live in a 128 MB log2ram tmpfs and reach the card
   only daily or at clean shutdown. A read-only root and "keep the logs that
   explain a crash" pull against each other. Step 5.9 must settle both.

6. **Boot and ready times** *(Step 1.1, 1.2)*. Pi boot 7.0 to 11.1 s, cause of
   the spread unknown. ESP32 reset to first sensor report 858 ms, about 400 ms
   of it the blocking "alive" buzz.

7. **Wiring has failed before** *(MEMORY, Step 1.1)*. Joints soldered to the
   Pi header tore off. ToF 2 lost contact on its ESP32 wiring on 2 Oct and
   was still absent at the baseline. Dupont crimps and splices today. Strain relief and connectors are a Step 5.1 requirement, not
   polish.

8. **Security exposure today** *(Pi, Step 1.1)*:
   - `sshd` on 0.0.0.0:22, password login not disabled (Debian default)
   - `icecast2` on 0.0.0.0:8000, a leftover from an old project
   - `avahi-daemon` on UDP 5353
   - Bluetooth `AlwaysPairable = true`, `PairableTimeout = 0`
   - the ESP32 serial protocol accepts `A0` and `B0,5000` from any process
     on the Pi, with no check *(code)*
   - no OTA mechanism, no signed firmware

9. **Privacy** *(code, Pi)*. The service does not store frames. Test frames
   (`test.jpg`, `test2.jpg`, `test3.jpg`) sit in `~/smartcane`. Phase 3 field
   recordings contain people. India's Digital Personal Data Protection Act
   2023 applies to any personal data the product or the project keeps
   *(verify)*.

10. **Product targets on record** *(MEMORY)*. Retail ₹15,000 to 25,000. The
    WeWALK handle weighs 152 g. The compute board alone (Pi 5 + AI HAT+ +
    camera) cost about $185 in parts.

---

## STEP 5.1: final hardware prototype

Move from Dupont wires, splices and loose boards to screw terminals or JST
connectors, strain relief, a custom PCB, protected connectors, secured
wiring and a proper enclosure.

- Power architecture: the safety layer (ESP32, ToF, IMU, motor) on its own
  regulated path that outlives the Pi (fact 1). The Pi gets a supply proven
  in Step 1.2 to give 0 under-voltage events at worst-case load.
- Enclosure: compare PETG and ASA (and any other practical material) for UV,
  heat, impact and printability. Target IP54 or better where realistic. Do
  not claim IP54 before it is tested.
- Sensor windows: a cover over the VL53L0X changes its readings through
  crosstalk *(verify, ST application notes)*. Re-run the Step 2.1 range table
  through the final window.
- Weigh the handle and the whole device. Record against the 152 g WeWALK
  handle.

## STEP 5.2: mechanical reliability

Drop tests, handle impact, connector pull, cable bending, repeated cane
swings, motor vibration, button endurance, USB connector endurance, camera
mount and sensor mount vibration. Write the cycle counts that stand for
"months of ordinary use" into `test_plan.md` before testing, with the
reasoning (swings per minute, minutes per day, days).

After each test: ToF IDs and range check, camera focus and FOV check, a full
Phase 4 health report. A part that still powers on but reads 10 % off has
failed.

## STEP 5.3: battery and thermal

Measure runtime for idle, normal walking, continuous detection, maximum load
and audio-heavy use. Measure cold start, low-battery behaviour and shutdown.

Low-battery order is a safety requirement: speech and vision shut down first,
with a spoken and felt warning, and the ESP32 safety layer keeps running on a
reserve for a stated time. Measure that reserve.

Log Pi, Hailo, battery, enclosure and ESP32 temperatures, plus voltage,
current and power, at 1 s or faster. Include a run inside the closed
enclosure in direct sun. Never quote runtime from capacity arithmetic.

## STEP 5.4: long-duration reliability

8 h, 12 h and 24 h runs. Track reboots, sensor drops, Hailo crashes,
memory growth, CPU growth, audio failures, serial errors, filesystem errors,
false alarms and missed events.

Track the counters this project already knows drift or recur, so a change is
noticed:

```text
detect.py RSS (520 MB on 2 Oct)
hailo_pci find_vma warnings per boot (about 1,230 on 2 Oct)
kernel under-voltage count (must stay 0)
ESP32 E lines and re-inits per hour
journal size against its storage
```

Investigate every unexplained event.

## STEP 5.5: real walking trials

Routes A to H from the master: indoor corridor, sidewalk, uneven pavement,
traffic-heavy road, market or crowd, stairs and kerbs, bright sunlight, low
light or night.

- Sighted testers first, eyes open, then with vision occluded and a spotter
  at arm's length. No blind participant walks a route before this.
- Ground truth from video, aligned to the device log by a sync event (a
  logged LED flash or beep at the start of each trial).
- Measure true and false positive rates, false negatives, time and distance
  at warning, speech and haptic latency, missed obstacles, wrong labels,
  ground hazards found and missed, sensor failures, and battery used per
  route.

## STEP 5.6: blind-user testing

Do not start with an unvalidated prototype. The Phase 4 gate and Step 5.5
are the engineering safety baseline.

Before the first participant:

- ethics approval from an institutional ethics committee, following the
  ICMR national ethical guidelines for research with human participants
  *(verify which apply)*
- consent material in accessible form (audio and Braille), the right to stop
  at any time, and insurance for participants
- written stop criteria, a safety observer within arm's reach on every
  trial, routes closed to traffic for first sessions
- partner organisations from MEMORY.md: NAB, Saksham, blind schools

10 to 20 participants. Measure task completion, warning understanding,
reaction time, false-alarm annoyance, trust, comfort, weight, audio
comprehension, vibration comprehension, fatigue and walking confidence.
Ask the MEMORY.md questions too: which three features they would pay for,
and whether they would wear a chest clip at all.

User satisfaction never replaces the objective safety measurements.

## STEP 5.7: human factors

Test that users can tell apart every pattern the product uses, while walking:

```text
obstacle: continuous 100 %, 85 % 120/180 ms, 60 % 100/600 ms
ground hazard: 3 x 300 ms on / 150 ms off
Pi sync buzz (if it survives Phase 4)
sensor fault, vision fault and audio fault patterns (Phases 2 and 4)
```

Report a confusion matrix per pair of patterns. Also: drop warning,
left and right words, distance words, fault recognition, button use without
looking, and recovery from a fault. Repeat with gloves, wet hands, walking,
standing, different grips and cane angles. A pattern pair confused more often
than the limit written in `test_plan.md` gets redesigned.

## STEP 5.8: abuse and environment

Dust, rain, humidity, heat, cold, sunlight, sweat, mud, minor impact and
repeated vibration. Include camera lens fogging and water on the ToF windows.
After every exposure, rerun the sensor checks from Step 5.2.

## STEP 5.9: software robustness

Implement and test: watchdogs (ESP32 from Step 1.5, the Pi's hardware
watchdog through systemd *(verify the Pi 5 setup)*, the Phase 4 monitor),
service restart, safe start-up, safe shutdown, a read-only root with overlayfs,
log rotation, storage monitoring, configuration validation (thresholds,
sensor roles in ESP32 NVS, model and label files), recovery from a corrupted
config, automatic health checks, factory reset and a diagnostic mode.

Settle fact 5: decide where crash logs go so they survive a power cut on a
read-only system. Then cut power 50 times at random points under load. The
device must boot, the card must pass `fsck`, and the log of the cut must be
readable.

## STEP 5.10: security

Start from fact 8. At minimum check default passwords, SSH exposure, unused
services, open ports, Bluetooth pairing exposure, OTA authentication,
firmware authenticity (ESP32 secure boot and flash encryption *(verify)*),
configuration protection, user data, GPS and privacy data, log privacy and
cloud credentials. Decide whether the ESP32 must reject safety-relevant
commands from the Pi at all (Phase 4 fact 2).

The offline safety core must work with no network, no phone and no cloud.

## STEP 5.11: compliance research for India

Answer each question from current official sources, with the source and
date recorded. Claim nothing without an approval in hand.

```text
BIS Compulsory Registration Scheme: does the product, its charger, its
  battery pack or its cells fall under a listed standard? (cells: IS 16046 (verify))
WPC Equipment Type Approval for the Bluetooth / Wi-Fi radios, and whether
  module approvals (Raspberry Pi, ESP32 module) carry over (verify)
battery transport: UN 38.3 test summary for the pack
laser: VL53L0X Class 1 under IEC 60825-1, labelling (verify, ST datasheet)
EMC / EMI requirements for the device class
E-Waste (Management) Rules and Battery Waste Management Rules: EPR registration
CDSCO Medical Devices Rules 2017: is an electronic mobility aid a medical device?
ADIP scheme listing requirements
labelling (Legal Metrology), user documentation, warranty, product liability
```

## FINAL RELEASE GATE

Produce `SMART CANE — ENGINEERING RELEASE REPORT` with every section of the
master's section 12, plus:

```text
Platform validated = platform shipped: hardware rev, firmware build, commit, HEF
Weight: handle, total (against 152 g WeWALK handle)
Bill of materials cost (against the ₹15,000-25,000 retail target)
Licences: model, datasets, software stack
Every haptic pattern and its measured discrimination rate
Safety layer power: what keeps it alive, and for how long, when the Pi is off
```

List every unresolved problem. No hidden known problems.

Classify the system as exactly one of: PROTOTYPE ONLY, FIELD-TEST READY,
CONTROLLED PILOT READY, PRE-PRODUCTION READY, NOT READY — SAFETY BLOCKER. A
consumer-ready verdict needs evidence from hardware, power, sensor
reliability, AI, latency, haptics, audio, fault handling, thermal, battery,
mechanical, environmental, human testing, security and compliance research.
