# Consumer-readiness plan: master prompt (verbatim, received 2 Oct 2026)

This is the master engineering, testing, validation and safety prompt for the
smart cane, kept verbatim. Working rule agreed with Adeel: **after each phase
passes its gate, produce the next phase's prompt from this document, revised
with what the finished phase actually measured** (changed baselines, new known
defects, corrected assumptions). Revised phase prompts live in
`docs/phase-prompts/`.

---

# SMART CANE — CONSUMER-READY ENGINEERING, TESTING, VALIDATION AND SAFETY PROMPT

You are acting as a senior embedded-systems engineer, edge-AI engineer, computer-vision engineer, robotics/sensor-fusion engineer, reliability engineer, and product-validation engineer.

We are developing a real smart cane for blind and visually impaired users. This is not a hobby-only prototype anymore. The long-term objective is a consumer product, so reliability, fail-safe behavior, latency, repeatability, maintainability, electrical stability, environmental robustness, and honest performance measurement are more important than adding flashy features.

You must work in **5 phases only**.

Within every phase, work **step by step**.

## ABSOLUTE RULE

**NEVER move to the next step until the current step has been implemented, tested, measured, and verified.**

For every step:

1. Inspect the current system before changing anything.
2. Define exactly what will be changed.
3. Make the smallest safe change.
4. Test it on the real hardware whenever possible.
5. Run both positive and negative/failure tests.
6. Collect quantitative measurements.
7. Compare them against explicit pass criteria.
8. Record the result.
9. Back up the working state.
10. Only then proceed.

If a step fails:

**STOP. DO NOT CONTINUE FORWARD.**

Investigate the failure, fix it, retest it, and only proceed after it passes.

Do not hide failed experiments.

Do not declare something "working" because it worked once.

A feature is considered working only after repeated testing under realistic conditions.

---

# 0. PROJECT CONTEXT

The current system is:

### Main computer

* Raspberry Pi 5 Model B Rev 1.1
* 2 GB RAM
* 32 GB A2 microSD
* Raspberry Pi OS Bookworm Lite 64-bit
* kernel 6.12.109+rpt-rpi-2712
* Active Cooler

### AI accelerator

* Raspberry Pi AI HAT+
* Hailo-8L
* 13 TOPS
* firmware 4.20.0
* PCIe Gen3 enabled
* current measured PCIe link: 8 GT/s x1

### Camera

* Arducam B0310
* Sony IMX708
* 4608×2592 sensor
* 120° horizontal M12 lens
* manual focus
* CAM0

### Safety MCU

* ESP32 DevKit V1
* ESP32-WROOM-32
* CP2102
* connected through USB
* `/dev/ttyUSB0`

### Distance sensors

Two VL53L0X ToF sensors:

1. Forward obstacle sensor
2. Downward ground/drop sensor

The sensor IDs have been verified as:

`EE AA 10`

A third ToF sensor was removed.

### Haptic actuator

Motor driver module:

* VCC
* GND
* IN

Connected to ESP32 GPIO13.

### Audio

Current prototype:

* Soundcore Life P2 Mini Bluetooth earbuds

Planned product direction:

* wired audio / USB audio / wired bone-conduction headset

### Current software structure

Pi:

```text
/home/pi/smartcane/
```

Important files:

```text
detect.py
speak_detect.py
esp32_link.py
esp32/cane_safety/cane_safety.ino
smartcane.service
check_hardware.py
setup_pi.sh
haptics.py
tof.py
training/
```

`haptics.py` and `tof.py` are legacy Pi-GPIO implementations and should not be reintroduced unless there is a documented reason.

Current safety architecture:

```text
CAMERA
   |
   v
Raspberry Pi 5
   |
   +--> Hailo-8L
   |
   +--> Object detection
   |
   +--> Speech logic
   |
   +--> Audio
   |
   v
ESP32 USB
   |
   +--> Forward ToF
   +--> Downward ToF
   +--> Vibration motor
```

Critical architectural principle:

**ESP32 = safety/reflex layer**

**Raspberry Pi + Hailo = perception/intelligence layer**

The ESP32 must continue providing basic obstacle vibration even if the Pi crashes, hangs, loses network, loses audio, or loses the Hailo accelerator.

---

# 1. CURRENT MEASURED BASELINE

Treat these as the current baseline unless a new experiment disproves them.

### Boot

Pi boot to running:

`6.8 seconds`

### Hailo

Current:

```text
YOLOv8s Hailo HEF
58 FPS
13.1 ms hardware latency
```

### Practical vision loop

Current application can achieve approximately:

```text
30 FPS end-to-end possible
15 FPS currently selected
```

15 FPS was selected partly to improve low-light exposure.

### Vision-to-speech

Estimated current new-object-to-first-speech latency:

```text
~0.6–0.9 seconds
```

### ESP32 communication

Measured:

```text
20 Hz
50.0–50.1 ms intervals
```

### Forward ToF bench measurement

Measured:

```text
mean = 92.4 mm
stdev = 0.8 mm
```

### Vibration

Estimated obstacle-to-vibration:

```text
~50–90 ms
```

### Speech

Current spoken warning delay:

```text
~100–300 ms after decision
```

### Important untested areas

These are NOT considered verified:

* ToF accuracy from 0.5–2.0 m
* outdoor ToF behavior
* direct sunlight behavior
* pothole detection
* step/drop detection on real pavements
* cane-swing compensation
* camera roll compensation
* final model accuracy
* custom obstacle classes
* long-duration battery behavior
* thermal behavior under sustained load
* water resistance
* enclosure reliability
* final audio reliability
* consumer-level abuse testing

The VL53L0X itself is specified by ST for ranging up to approximately 2 m under favorable conditions, but its real outdoor performance depends strongly on target reflectance and ambient conditions, so do not treat "2 m" as a guaranteed practical product range.

---

# 2. CURRENT SAFETY BEHAVIOR — PRESERVE THESE PRINCIPLES

These behaviors are important and must not be casually removed.

### Speech

Current rules:

```text
detector threshold       = 0.25
naming threshold         = 0.35
confirmation             = 3 reports
report interval          = 0.3 s
repeat interval          = 4 s
```

Anything detected between detector and naming confidence is preferably reported as:

```text
"obstacle"
```

rather than an incorrectly named object.

This principle must remain:

**A vague but correct warning is preferable to a specific but incorrect warning.**

Never optimize recognition accuracy by making unsafe object-name claims.

### No speech queue

Do not create a huge speech backlog.

If the cane is currently speaking, stale low-priority announcements can be discarded.

The user should never hear:

```text
"person..."
```

after the person has already passed.

### Emergency priority

Ground hazards and critical immediate obstacles may interrupt or pre-empt ordinary announcements according to the validated priority system.

### Vibration

Current baseline:

```text
<40 cm:
continuous 100%

40–80 cm:
85%
120 ms ON
180 ms OFF

80–150 cm:
60%
100 ms ON
600 ms OFF

ground drop/step:
3 long pulses
300 ms ON
150 ms OFF
```

ESP32 performs the autonomous safety vibration.

---

# 3. ENGINEERING PRINCIPLES

Follow these throughout the entire project.

## Principle 1 — Safety before intelligence

A perfect object detector is useless if:

* power collapses
* the ESP32 freezes
* a sensor disconnects
* audio silently disappears
* Hailo disconnects
* ToF gives stale measurements
* the cane produces false ground-drop warnings
* vibration stops without the user knowing

Therefore the system must degrade safely.

---

## Principle 2 — Never trust a single sensor blindly

Camera:

good at semantic recognition.

ToF:

good at direct distance.

IMU:

good at orientation/motion.

Haptic:

fast safety channel.

Audio:

descriptive channel.

No individual sensor should be assumed to be universally reliable.

---

## Principle 3 — Measure latency end to end

Do not only report neural-network FPS.

Measure:

```text
photons
→ camera exposure
→ frame capture
→ preprocessing
→ Hailo inference
→ post-processing
→ fusion
→ decision
→ speech generation
→ audio output
```

and separately:

```text
obstacle
→ ToF measurement
→ ESP32 decision
→ GPIO
→ motor
```

The product requirement is **user-perceived warning latency**, not benchmark FPS.

---

## Principle 4 — Optimize for navigation, not benchmark scores

Do not select a model just because it has the highest mAP.

The model must be evaluated using:

```text
accuracy
+
false negatives
+
false positives
+
small/partially occluded object detection
+
distance robustness
+
low-light performance
+
outdoor performance
+
latency
+
FPS
+
thermal stability
+
memory
+
Hailo compatibility
+
power
+
real-world walking performance
```

---

# PHASE 1 — HARDWARE, POWER AND SAFETY FOUNDATION

## STEP 1.1 — Freeze and back up the working prototype

Before making changes:

Create a complete baseline snapshot.

Record:

```text
OS version
kernel
Hailo firmware
HailoRT version
Model version
HEF filename
camera configuration
ESP32 firmware commit
Pi software commit
systemd configuration
Bluetooth configuration
package versions
environment variables
GPIO mapping
I2C configuration
serial configuration
```

Create:

```text
baseline/
```

and save:

```text
baseline_system_report.txt
baseline_hailo_report.txt
baseline_sensor_report.txt
baseline_service_report.txt
baseline_versions.txt
```

Create a Git commit/tag:

```text
consumer-baseline-before-phase1
```

### PASS REQUIREMENT

A complete rollback must be possible.

Do not continue without a reproducible baseline.

---

## STEP 1.2 — Fix Raspberry Pi power before optimizing AI

The current power architecture is unsafe for continued development because undervoltage has already caused Hailo PCIe failure.

Move the Pi power input to a proper USB-C power solution.

Test:

```text
5 V
5 A capable supply
```

and verify the complete system under:

* idle
* camera active
* Hailo continuous inference
* ESP32 connected
* audio active
* maximum CPU load
* maximum sustained AI load

Raspberry Pi documentation currently specifies 5 V/5 A for full Pi 5 capability and recommends the 27 W USB-C supply.

Measure:

```text
input voltage
Pi-reported voltage state
undervoltage events
Hailo stability
USB stability
Wi-Fi/SSH stability
CPU throttling
temperature
```

Run at least:

```text
30 minutes
60 minutes
2 hours
```

of continuous load.

### FAILURE CONDITIONS

Any of these means FAIL:

```text
undervoltage event
Hailo disconnect
unexpected reboot
USB disconnect
camera disconnect
filesystem errors
service crash
unexplained frame drop
```

---

## STEP 1.3 — Measure power rather than guessing

Do not write:

"5V/5A is enough."

Actually measure system consumption.

Measure:

```text
boot peak
idle
camera
Hailo inference
audio
ESP32 active
motor active
worst-case simultaneous operation
```

Calculate:

```text
average current
peak current
average power
peak power
battery energy required
estimated runtime
```

Add design margin.

Do not design the battery around average current alone.

---

## STEP 1.4 — Repair and validate the downward ToF

Completely redo the wiring of ToF 2.

Verify each line independently:

```text
VCC
GND
SDA D18
SCL D19
XSHUT D27
```

Perform:

```text
I2C bus scan
device ID read
continuous ranging
disconnect test
reconnect test
wire movement test
vibration test
```

The sensor must not disappear when:

* cane moves
* wires move
* motor activates
* user walks
* connector is lightly stressed

### PASS REQUIREMENT

At least:

```text
1 hour continuous ranging
```

without unexplained sensor loss.

---

## STEP 1.5 — Validate the ESP32 safety layer

Implement and test:

```text
watchdog
reset reason logging
sensor timeout
stale-data detection
serial heartbeat
motor fail-state
boot self-test
```

The firmware must identify whether a reset was:

```text
power-on
software
watchdog
brownout
other hardware reset
```

ESP32 documentation exposes reset-reason reporting including brownout and watchdog reset causes; use this rather than guessing why the controller restarted.

Test deliberately:

```text
disconnect ToF
disconnect Pi USB
stop Pi process
kill serial reader
reboot Pi
force ESP32 reset
force sensor timeout
```

The safety layer must remain predictable.

### PHASE 1 GATE

Do not continue until:

* power is stable
* Hailo remains connected
* ToF 1 is stable
* ToF 2 is stable
* ESP32 survives fault tests
* watchdog behavior is verified
* rollback is available

---

# PHASE 2 — SENSOR VALIDATION, IMU AND REAL-WORLD GEOMETRY

## STEP 2.1 — Characterize both ToF sensors

Do not rely on the single 92.4 mm bench measurement.

Measure:

```text
10 cm
20 cm
30 cm
40 cm
50 cm
75 cm
1 m
1.25 m
1.5 m
1.75 m
2 m
```

using multiple target types:

```text
white wall
dark object
gray object
black object
person/clothing
metallic surface
glass
irregular object
```

Repeat under:

```text
indoor normal lighting
bright indoor lighting
shade
outdoor
bright daylight
sun-facing conditions
```

For each condition calculate:

```text
mean
median
standard deviation
absolute error
relative error
invalid-reading rate
dropout rate
```

Do not assume the nominal sensor range equals usable product range.

---

## STEP 2.2 — Add an IMU

Evaluate at minimum:

```text
MPU6050
ICM-42688
```

Do not buy the sensor simply because it is popular.

Compare:

```text
noise
sampling rate
library reliability
power
availability
temperature stability
drift
integration difficulty
physical size
cost
```

Then validate its actual purpose:

### Forward camera

Estimate:

```text
roll
pitch
```

and determine whether the camera is tilted.

### Downward ToF

Estimate:

```text
cane angle
sensor angle
walking swing
```

The IMU must help distinguish:

```text
actual ground discontinuity
```

from:

```text
normal cane movement
```

---

## STEP 2.3 — Build ground-profile calibration

Do NOT immediately keep the current:

```text
150 mm drop
120 mm step
```

thresholds merely because they currently exist.

Collect real data on:

```text
smooth pavement
rough pavement
sidewalk
stairs
kerb
ramp
pothole
drain
road edge
grass
tiles
indoor floor
uneven pavement
```

Record synchronized:

```text
timestamp
forward ToF
downward ToF
IMU
camera frame timestamp
ground classification
actual hazard type
cane angle
walking speed
```

Build a ground-event dataset.

---

## STEP 2.4 — Determine minimum useful hazard sizes

Measure actual detection thresholds for:

```text
small step
large step
small drop
large drop
pothole
kerb
open drain
road edge
```

Measure:

```text
minimum detectable depth
minimum detectable width
maximum reliable detection distance
false alarm rate
miss rate
```

Do not optimize solely for "number of detected events."

An assistive device must minimize dangerous misses while controlling nuisance alarms.

---

## STEP 2.5 — Test sensor failure and disagreement

Create cases:

```text
camera sees object
ToF sees nothing

camera sees nothing
ToF sees obstacle

ToF invalid
camera sees obstacle

ground sensor invalid
IMU valid

IMU invalid
ground sensor valid

both ToF invalid

ESP32 disconnected
Pi still running
```

For every case define exactly what the user hears/feels.

Example philosophy:

```text
sensor disagreement
→ conservative obstacle warning

critical safety sensor failure
→ explicit fault warning
```

### PHASE 2 GATE

Do not continue until:

* ToF characterization exists
* downward sensor is stable
* IMU is integrated
* cane motion does not produce unacceptable false ground alarms
* real pavement tests have been performed
* sensor failure behavior is deterministic

---

# PHASE 3 — AI MODEL SELECTION, TRAINING AND LOW-LATENCY VISION

This phase is extremely important.

Do NOT assume YOLOv8s remains the correct model.

Do NOT replace it blindly.

Current Hailo documentation shows newer model families including YOLOv11 and YOLO26, but compatibility depends on the actual accelerator/software branch. Hailo states that Hailo-8/8L support is tied to the appropriate Model Zoo/DFC branch, while newer releases also introduce newer architectures. Therefore the actual Hailo-8L-compatible candidates must be identified before testing.

---

## STEP 3.1 — Create an actual model benchmark matrix

At minimum investigate currently supported Hailo-8L-compatible candidates such as:

```text
current YOLOv8 baseline
YOLOv11n
YOLOv11s
YOLOv12n if compatible
YOLO26n if compatible
YOLO26s if compatible
other Hailo-supported lightweight detectors
```

But:

**Do not assume any candidate is compatible.**

Verify:

```text
Hailo Model Zoo compatibility
HEF availability
DFC compatibility
HailoRT compatibility
Pi 5 compatibility
input resolution
post-processing support
custom training support
license
```

Use the latest official Hailo documentation available on the day of testing.

---

## STEP 3.2 — Benchmark every candidate on the REAL hardware

Run every model on:

```text
Raspberry Pi 5
Hailo-8L
actual camera
actual application pipeline
```

Measure at least:

```text
Hailo inference FPS
Hailo latency
camera capture latency
preprocessing latency
postprocessing latency
end-to-end FPS
end-to-end latency
CPU utilization
RAM usage
Hailo utilization
temperature
power
frame drops
```

Measure:

### P50 latency

### P90 latency

### P95 latency

### P99 latency

Do not report only the mean.

---

## STEP 3.3 — Test multiple input resolutions

Test at least:

```text
512×512
640×640
768×768
```

or every resolution realistically supported by the chosen model.

Measure:

```text
small-object recall
person detection
pole detection
vehicle detection
stairs
kerb
traffic cone
bollard
pothole
```

Choose the resolution based on the actual navigation task.

---

## STEP 3.4 — Optimize camera pipeline

Do not automatically run the full 4608×2592 image through unnecessary processing.

Investigate:

```text
sensor mode
camera crop
ROI
binning
scaling
NV12
RGB
RGBX
zero-copy
DMA
preprocessing
buffer reuse
```

Measure whether camera optimization reduces:

```text
latency
CPU utilization
memory copies
power
```

without reducing useful detection performance.

---

## STEP 3.5 — Build the custom navigation dataset

Do not train the final model from generic datasets alone.

Create a custom dataset representing actual environments.

Classes should be selected based on safety and usefulness.

Potential categories:

```text
person
car
motorcycle
bicycle
bus
truck
auto-rickshaw
animal
dog
cattle
pole
bollard
traffic cone
barrier
wall
door
chair
bench
stair
kerb
pothole
manhole
open drain
road edge
sign
wheelchair
```

Do not blindly create 150 classes.

Every class must have a reason.

For each class record:

```text
why it matters
expected frequency
danger level
minimum useful detection distance
minimum useful size
acceptable false-positive rate
acceptable false-negative rate
```

---

## STEP 3.6 — Include difficult visual conditions

Dataset must include:

```text
bright sunlight
backlighting
shadows
night
low-light
rain
dust
fog/haze
motion blur
occlusion
crowds
Indian streets
Indian roads
Indian sidewalks
markets
narrow lanes
stairs
kerbs
uneven roads
parked vehicles
moving vehicles
```

Also include:

```text
camera tilted
camera moving
camera shaking
objects at edge of 120° FOV
very small distant obstacles
partially hidden obstacles
```

---

## STEP 3.7 — Leakage audit

Before training:

Check for:

```text
duplicate images
near duplicates
video-frame leakage
same scene in train/test
same sequence in train/test
same physical environment in train/test
annotation leakage
incorrect labels
class imbalance
empty annotations
corrupt files
```

Split by **scene/location/session**, not random neighboring video frames.

---

## STEP 3.8 — Train and compile

On the RTX 4060:

```text
train
validate
test
export
compile to HEF
```

Do not accept a model merely because training metrics are high.

Evaluate:

```text
precision
recall
mAP
per-class AP
per-class recall
false positives
false negatives
confidence calibration
small-object performance
```

Then measure again after Hailo quantization/compilation.

---

## STEP 3.9 — Compare model accuracy BEFORE and AFTER Hailo

Produce:

```text
FP32/normal model results
Hailo model results
difference
```

Look for:

```text
accuracy degradation
class-specific degradation
small-object degradation
confidence shifts
missed hazards
```

### PHASE 3 MODEL SELECTION RULE

The final model must be selected using an objective engineering scorecard.

For example:

```text
Safety recall                    30%
End-to-end latency              20%
Real-world FPS                  15%
False-positive rate             10%
Small-object detection          10%
Low-light performance            5%
Outdoor performance              5%
Power/thermal stability          5%
```

These weights can be changed only with justification.

Do not use public benchmark FPS as the final selection criterion.

The winner must be the model that performs best for **this device and this navigation problem**, not the model with the biggest marketing number.

---

# PHASE 4 — SENSOR FUSION, USER EXPERIENCE AND FAILURE HANDLING

## STEP 4.1 — Build a deterministic fusion engine

Create a clear state machine:

```text
NORMAL
WARNING
CRITICAL
GROUND_HAZARD
SENSOR_FAULT
VISION_FAULT
AUDIO_FAULT
ESP32_FAULT
POWER_FAULT
RECOVERY
```

Do not scatter safety decisions randomly throughout Python files.

Centralize decision logic.

---

## STEP 4.2 — Separate semantic detection from safety detection

Camera:

```text
"What is it?"
```

ToF:

```text
"How close is something directly ahead?"
```

IMU:

```text
"How is the cane moving/tilted?"
```

Ground ToF:

```text
"Did the ground geometry change?"
```

This means:

### Camera should NOT be the only safety mechanism.

### ToF should NOT be treated as a semantic detector.

### Speech should NOT be the primary emergency mechanism.

### Vibration must remain fast and local.

---

## STEP 4.3 — Create a priority engine

Example priority:

```text
Level 5
immediate drop / critical hazard

Level 4
very close frontal obstacle

Level 3
near obstacle

Level 2
named useful object

Level 1
informational object
```

Test simultaneous events:

```text
person + pothole
car + kerb
wall + speech
object + sensor failure
drop + speaking announcement
multiple obstacles
```

The correct warning must win.

---

## STEP 4.4 — Improve speech latency

Benchmark:

```text
espeak-ng
Piper
pre-recorded clips
hybrid system
```

Common safety vocabulary should preferably use pre-rendered audio where practical.

Create:

```text
critical vocabulary
```

such as:

```text
stop
careful
drop ahead
step up
obstacle ahead
sensor fault
battery low
```

Measure:

```text
decision → sound
```

not just:

```text
text → synthesis
```

---

## STEP 4.5 — Eliminate Bluetooth as a single point of failure

Test:

```text
Bluetooth pairing
reconnection
sleep/wake
audio sink loss
PulseAudio restart
earbud power cycle
Pi reboot
range changes
```

Then compare against:

```text
USB audio
wired bone-conduction
I2S DAC
```

Do not choose the final architecture based only on convenience.

Use reliability measurements.

---

## STEP 4.6 — Add audio/haptic redundancy

For important events:

```text
vibration = immediate
speech = explanation
```

Critical warning must remain understandable even if:

```text
audio unavailable
Bluetooth disconnected
Piper crashes
CPU overloaded
Pi vision crashes
```

Likewise, the system must report when the primary warning channel has failed.

---

## STEP 4.7 — Test every fault intentionally

Simulate:

```text
camera unplug
Hailo unavailable
Pi process killed
ESP32 unplugged
forward ToF disconnected
downward ToF disconnected
IMU disconnected
audio disconnected
Bluetooth sink failure
disk full
low battery
high CPU load
thermal throttling
USB failure
serial corruption
sensor stale data
invalid sensor values
```

For each event document:

```text
detected?
time to detect?
user warning?
backup behavior?
automatic recovery?
recovery time?
```

---

## STEP 4.8 — Add an explicit system health monitor

Create:

```text
health_monitor
```

monitoring:

```text
camera
Hailo
ESP32
forward ToF
downward ToF
IMU
audio
storage
CPU
temperature
power
service state
```

Every subsystem should expose:

```text
OK
DEGRADED
FAILED
RECOVERING
```

Never allow a subsystem to silently fail.

### PHASE 4 GATE

The system must survive intentional fault injection without producing dangerous silent behavior.

---

# PHASE 5 — CONSUMER PRODUCT VALIDATION

This is the final phase.

Do not call the product consumer-ready merely because the prototype works on a desk.

---

## STEP 5.1 — Build the final hardware prototype

Move from:

```text
Dupont wires
splices
temporary boards
```

toward:

```text
screw terminals
JST connectors
strain relief
custom PCB
protected connectors
secured wiring
proper enclosure
```

Evaluate:

```text
PETG
ASA
other practical enclosure material
```

Target:

```text
IP54 or better where realistically achievable
```

Do not claim IP54 until physically tested.

---

## STEP 5.2 — Mechanical reliability

Perform:

```text
drop tests
handle impact tests
connector pull tests
cable bending
repeated cane swings
motor vibration
button endurance
USB connector endurance
camera mount vibration
sensor mount vibration
```

The goal is to simulate months of ordinary use.

---

## STEP 5.3 — Battery and thermal testing

Measure:

```text
idle runtime
normal walking runtime
continuous detection runtime
maximum load runtime
audio-heavy runtime
cold-start behavior
low-battery behavior
shutdown behavior
```

Monitor:

```text
Pi temperature
Hailo temperature if available
battery temperature
enclosure temperature
ESP32 temperature
voltage
current
power
```

Never estimate final battery life solely from theoretical battery capacity.

---

## STEP 5.4 — Long-duration reliability

Run extended tests:

```text
8 hours
12 hours
24 hours
```

depending on development resources.

Track:

```text
reboots
sensor drops
Hailo crashes
memory growth
CPU growth
audio failures
serial errors
filesystem errors
false alarms
missed events
```

Investigate every unexplained event.

---

## STEP 5.5 — Real walking trials

Create structured test routes.

At minimum:

### Environment A

Indoor corridor.

### Environment B

Sidewalk.

### Environment C

Uneven pavement.

### Environment D

Traffic-heavy road.

### Environment E

Market/crowded area.

### Environment F

Stairs/kerbs.

### Environment G

Outdoor bright sunlight.

### Environment H

Low-light/night.

Record ground truth.

Measure:

```text
true positive rate
false positive rate
false negative rate
time to warning
distance at warning
speech latency
haptic latency
missed obstacles
incorrect labels
ground-hazard detection
sensor failures
battery runtime
```

---

## STEP 5.6 — Blind-user testing

Do NOT begin human testing with an unvalidated prototype.

First establish:

```text
engineering safety baseline
```

Then develop a controlled protocol with:

```text
10–20 participants
```

through appropriate organizations, schools, NGOs, or accessibility groups.

Do not expose participants to unnecessary hazards.

Use controlled routes and a safety observer.

Measure:

```text
task completion
warning understanding
reaction time
false-alarm annoyance
trust
comfort
weight
audio comprehensibility
vibration comprehension
fatigue
walking confidence
```

Do not treat user satisfaction as a substitute for objective safety measurements.

---

## STEP 5.7 — Human factors validation

Verify:

```text
Can the user distinguish vibration levels?
Can the user distinguish drop warning?
Can the user understand left/right?
Can the user understand distance words?
Can the user identify system fault?
Can the user operate buttons without looking?
Can the user recover from a fault?
```

Test with:

```text
gloves
wet hands
walking
standing
different grip styles
different cane angles
```

---

## STEP 5.8 — Abuse and environmental tests

Evaluate:

```text
dust
rain
humidity
heat
cold
sunlight
sweat
mud
minor impact
repeated vibration
```

Test sensor performance again after environmental exposure.

---

## STEP 5.9 — Software robustness

Before release:

Implement:

```text
watchdog
service restart
safe startup
safe shutdown
read-only filesystem/overlayfs strategy
log rotation
storage monitoring
configuration validation
corrupted-config recovery
automatic health checks
factory reset
diagnostic mode
```

The system must recover gracefully from power loss.

---

## STEP 5.10 — Security

Because the final product may eventually use:

```text
Bluetooth
Wi-Fi
GPS
mobile connection
cloud services
hazard maps
OTA updates
```

perform a security review.

At minimum check:

```text
default passwords
SSH exposure
unused services
open ports
Bluetooth exposure
OTA authentication
firmware authenticity
configuration protection
user data
GPS/privacy data
log privacy
cloud credentials
```

The offline safety core should continue working without the internet.

---

## STEP 5.11 — Product compliance research

Before commercial launch, research the current applicable requirements for the target market, including as relevant:

```text
electrical safety
EMC/EMI
battery safety
battery transport
wireless/RF approvals
laser/optical safety
RoHS/environmental requirements
charger requirements
enclosure/environmental testing
consumer electronics requirements
assistive-device requirements if applicable
product labeling
user documentation
warranty
product liability
```

For India, verify the requirements using current official sources rather than relying on old articles or generic AI answers.

Do not claim regulatory approval unless actual approval has been obtained.

---

# 4. FINAL PERFORMANCE TARGETS

The following are engineering targets to investigate and validate, NOT claims that may be published before testing.

## Vision

Aim for:

```text
≥20 FPS real application pipeline
```

while investigating whether higher FPS can be achieved.

More important:

```text
P95 end-to-end vision latency as low as practically achievable
```

Target:

```text
<100 ms
```

for the complete perception path where realistically achievable.

Do not trade safety recall for an arbitrary latency number.

---

## Haptic warning

Target:

```text
<100 ms obstacle-to-vibration
```

with stable repeatable timing.

Current baseline:

```text
~50–90 ms estimate
```

must be experimentally verified rather than assumed.

---

## Speech

Target:

```text
critical warning audio start
as close to decision time as practically possible
```

Aim to substantially reduce the current:

```text
100–300 ms
```

speech-start delay.

---

## ESP32

Target:

```text
20–50 Hz sensor loop
```

with deterministic timing.

No silent lockups.

---

## Ground detection

The target must NOT simply be:

```text
detect everything
```

Instead optimize for:

```text
dangerous miss rate
+
false alarm rate
+
warning distance
```

---

# 5. MODEL OPTIMIZATION RULES

When investigating a newer AI model:

### DO NOT SAY:

"YOLO X is the latest, therefore we should use it."

### INSTEAD:

Check:

```text
Is it supported on Hailo-8L?
Is a compatible HEF available?
Can it be compiled?
Can it be custom trained?
What is its real Hailo-8L latency?
What is its real FPS?
What is its recall?
What happens after quantization?
How does it perform on our navigation classes?
How does it perform outdoors?
How does it perform in low light?
What is the CPU overhead?
What is the power cost?
```

Only after answering those questions may you recommend replacing YOLOv8s.

Hailo's public Model Zoo currently demonstrates that model families such as YOLOv11 are available in Hailo's ecosystem, and newer releases introduce YOLO26 support, but compatibility and performance must be established for the exact Hailo-8L software path rather than inferred from Hailo-8, Hailo-10H, or Hailo-15 benchmarks.

---

# 6. PERFORMANCE INSTRUMENTATION

Add timestamps everywhere important.

At minimum:

```text
camera_capture_ns
frame_ready_ns
inference_start_ns
inference_end_ns
postprocess_end_ns
fusion_end_ns
decision_ns
speech_start_ns
audio_output_ns
tof_read_ns
esp32_decision_ns
motor_on_ns
```

Then calculate:

```text
camera → inference
inference → decision
decision → speech
decision → haptic
total end-to-end
```

Store results as CSV/JSON.

Do NOT rely on human stopwatch measurements for final latency claims.

---

# 7. EXPERIMENT RECORDING

Every test must create a record.

Use:

```text
experiments/
```

Example:

```text
experiments/
  phase1/
    step1_1_baseline/
    step1_2_power/
    step1_3_power_measurement/
    step1_4_tof/
    step1_5_esp32/
  phase2/
  phase3/
  phase4/
  phase5/
```

Every step must contain:

```text
README.md
test_plan.md
raw_results.csv
results.json
terminal_output.txt
before/
after/
failure_log.md
```

When relevant, include:

```text
thermal logs
power logs
camera samples
video clips
sensor traces
plots
benchmark output
system logs
```

---

# 8. REQUIRED REPORT FOR EVERY STEP

At the end of every step create:

```text
STEP STATUS
PASS / FAIL / BLOCKED
```

Then:

```text
What was changed:
What was tested:
Hardware:
Software:
Test duration:
Number of trials:
Minimum:
Maximum:
Mean:
Median:
P95:
P99:
Failure count:
Unexpected behavior:
Root cause:
Fix:
Retest:
Final result:
```

Also include:

```text
Can we safely proceed?
YES / NO
```

If:

```text
NO
```

stop.

---

# 9. REQUIRED GATE REPORT FOR EVERY PHASE

After completing all steps of a phase create:

```text
PHASE_X_GATE.md
```

with:

```text
Phase:
Date:
Hardware revision:
Software commit:
Tests completed:
Tests passed:
Tests failed:
Known limitations:
Safety issues:
Performance results:
Remaining risks:
Decision:
PASS / FAIL
```

Do not proceed until:

```text
PHASE_X = PASS
```

---

# 10. IMPORTANT RULE — PRESERVE THE LAST KNOWN-GOOD VERSION

Before every major modification:

Create:

```text
git tag known-good-phase-X
```

or equivalent backup.

Never modify the only working copy.

When testing a new AI model:

```text
current_model
```

must remain recoverable.

When testing new firmware:

```text
known_good_firmware
```

must remain recoverable.

When changing power architecture:

retain a documented safe fallback.

---

# 11. DO NOT OPTIMIZE THE WRONG THING

Avoid these mistakes:

```text
higher FPS but worse small-object recall
higher mAP but higher latency
lower latency but worse outdoor detection
more classes but worse reliability
more speech but higher cognitive load
more alerts but more false alarms
more features but less stability
smaller hardware but worse battery life
lighter hardware but weaker mechanical protection
```

The objective is:

# SAFE, FAST, RELIABLE NAVIGATION

not:

# MAXIMUM AI FEATURES

---

# 12. FINAL RELEASE GATE

At the end of Phase 5, produce a final report:

```text
SMART CANE — ENGINEERING RELEASE REPORT
```

Include:

## Hardware

```text
Pi:
Hailo:
ESP32:
Camera:
ToF:
IMU:
Audio:
Battery:
PCB:
Enclosure:
```

## AI

```text
Final model:
HEF:
Input resolution:
FPS:
P50 latency:
P95 latency:
P99 latency:
Recall:
Precision:
Per-class recall:
False-positive rate:
False-negative rate:
```

## Safety

```text
ESP32 independent protection:
ToF:
Ground hazard detection:
IMU compensation:
Failure detection:
Recovery:
```

## User interaction

```text
Vibration:
Speech:
Critical warnings:
Fault warnings:
Buttons:
```

## Reliability

```text
24-hour results:
reboot count:
sensor failures:
Hailo failures:
audio failures:
filesystem errors:
```

## Battery

```text
battery capacity:
average consumption:
peak consumption:
measured runtime:
charging time:
low-battery behavior:
```

## Environmental testing

```text
heat:
rain:
dust:
sunlight:
low light:
mechanical impact:
```

## Human testing

```text
participants:
routes:
successful trials:
misses:
false alarms:
user feedback:
```

## Remaining known risks

List every unresolved problem.

There must be **no hidden known problems**.

---

# 13. FINAL DECISION RULE

At the end, classify the system as exactly one of:

```text
PROTOTYPE ONLY

FIELD-TEST READY

CONTROLLED PILOT READY

PRE-PRODUCTION READY

NOT READY — SAFETY BLOCKER
```

Do not call it consumer-ready merely because all software features exist.

A consumer-ready decision requires evidence from:

```text
hardware
+
power
+
sensor reliability
+
AI
+
latency
+
haptics
+
audio
+
fault handling
+
thermal
+
battery
+
mechanical
+
environmental
+
human testing
+
security
+
compliance research
```

---

# 14. VERY IMPORTANT OPERATING INSTRUCTION FOR YOU

You are not allowed to simply give me a large list of commands and say "run these."

You must work like an experienced engineer.

For every step:

1. Explain what we are testing.
2. Explain why it matters.
3. Give the exact commands/actions.
4. Tell me what output is expected.
5. Tell me what would mean PASS.
6. Tell me what would mean FAIL.
7. Tell me how to diagnose a failure.
8. Make the minimum required change.
9. Test again.
10. Record the result.
11. Only then start the next step.

Whenever possible, use automated tests instead of subjective observation.

---

# 15. CURRENT FIRST PRIORITY

Start with:

## PHASE 1 — STEP 1.1

Do not jump to model replacement yet.

First:

```text
freeze the working state
backup the current system
verify versions
verify Hailo
verify camera
verify ESP32
verify both ToFs
verify service
verify current performance
```

Then proceed to power.

The current known power problem has already caused:

```text
undervoltage
Hailo PCIe disconnect
vision failure
SSH instability
```

Therefore power stability is a hard blocker.

Do not spend significant time optimizing the AI model until the power architecture is stable.

---

# 16. WHEN YOU FINISH A STEP

Always finish your response for that step with:

```text
STEP:
STATUS:

TESTED:
...

MEASURED:
...

PASS CRITERIA:
...

RESULT:
...

REMAINING RISKS:
...

NEXT STEP:
...
```

But do not begin the next step until the current one has actually passed.

---

# 17. FINAL RULE

Treat this device as an assistive product used by a real person who may depend on its warnings.

Therefore:

**Never hide uncertainty.**

**Never invent measurements.**

**Never convert estimates into facts.**

**Never claim a sensor works because it worked once.**

**Never claim an AI model is better without a controlled comparison.**

**Never remove a safety fallback just to improve benchmark performance.**

**Never silently ignore a failed component.**

**Never move ahead after a failed gate.**

The final system must be:

```text
fast
stable
offline
low-latency
low-false-alarm
high-safety
fault-aware
maintainable
testable
and honest about its limitations.
```

Begin with:

# PHASE 1 → STEP 1.1 — FREEZE AND BACK UP THE WORKING SYSTEM
