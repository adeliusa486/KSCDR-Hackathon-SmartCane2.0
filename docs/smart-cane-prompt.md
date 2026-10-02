# Smart cane project: full context prompt

Paste everything below this line into a new AI chat.

---

You are helping me build a smart cane for blind and visually impaired people in India. Below is the full state of the project as of 2 October 2026: the goal, the hardware, the wiring, the software, what works, what is broken, and what I need next. Treat every number here as measured on my hardware unless it says "estimate" or "untested". Do not suggest anything that contradicts a measured result without explaining why.

## 1. Goal

An affordable assistive navigation device that:

- detects objects offline with a camera and says what they are and where they are ("person ahead, 60 centimetres")
- measures real distance to obstacles with a ToF sensor
- detects potholes, open drains, kerbs and steps with a downward ToF sensor
- warns through vibration first (fast) and speech second (descriptive)
- works with no internet, no phone and no subscription
- later supports Indian languages, Indian currency recognition and bus-number reading
- sells for ₹15,000 to ₹25,000 at mass production

Competitors: WeWALK (ultrasonic only, £599, AI needs a ~£109/year subscription, 152 g handle), Torchit Saarthi (ultrasonic only, no camera), Torchit Jyoti glasses (cloud-based scene description, ~₹25,000), Glide (~$1,500 wheeled robot). Our edge is offline camera AI, drop-off detection on Indian roads, and no subscription.

## 2. Architecture

Two computers, joined by one USB cable:

- **Raspberry Pi 5 + AI HAT+** is the "eyes and brain": camera, object detection, speech.
- **ESP32 DevKit V1** is the "reflexes": both ToF sensors and the vibration motor. It buzzes on its own, so obstacle alerts work about 1 s after power-on (the Pi takes ~7 s to boot) and keep working if the Pi software crashes. The Pi only listens to the ESP32 and adds speech.

Long-term product concept: a chest or shoulder clip holds the camera and Pi, and the cane handle holds the ToF sensors, ESP32 and motor and must work alone if the clip is not worn. A crowdsourced map of hazards (potholes, open drains) recorded by users' devices is the planned long-term moat.

## 3. Hardware, as built today

| Part | Details |
|---|---|
| Main computer | Raspberry Pi 5 Model B Rev 1.1, 2 GB RAM, 32 GB A2 microSD, Active Cooler |
| OS | Raspberry Pi OS Bookworm Lite 64-bit, kernel 6.12.109+rpt-rpi-2712, hostname `smartcane` |
| AI accelerator | Raspberry Pi AI HAT+ with **Hailo-8L, 13 TOPS** (not the 26 TOPS Hailo-8). Firmware 4.20.0. PCIe Gen3 enabled (`dtparam=pciex1_gen=3`), link 8 GT/s x1 |
| Camera | Arducam B0310, Sony IMX708, 4608×2592, **120° horizontal M12 lens, manual focus**, on CAM0 |
| Safety MCU | ESP32 DevKit V1 (ESP32-WROOM-32, 30 pins, CP2102 USB chip), appears on the Pi as `/dev/ttyUSB0` |
| ToF sensors | 2× **VL53L0X** (not VL53L1X, confirmed by ID registers `EE AA 10`). A third one was removed |
| Vibration | Motor driver module (VCC, GND, IN), not a bare motor |
| Audio | Soundcore Life P2 Mini Bluetooth earbuds, MAC `B0:38:E2:19:DC:CC`, A2DP profile, PulseAudio |
| Power | A UPS board feeding the Pi through the **5V GPIO pin (pin 2)**. This is not enough. See problems |
| Assistant button | Planned, not wired yet |

The AI HAT+ needs the 40-pin GPIO header for power and its ID EEPROM. The PCIe ribbon carries data only. With the HAT fitted, there are no usable GPIO pins on top, which is why every sensor moved to the ESP32.

## 4. Wiring

**Raspberry Pi 5:** only power. Red UPS+ to pin 2 (5V), black to GND. ESP32 by USB to any Pi USB port. Nothing else on the Pi header.

**ESP32 DevKit V1:**

| Wire | ESP32 pin |
|---|---|
| ToF 1 (forward) VCC / GND | 3V3 / GND |
| ToF 1 SDA / SCL / XSHUT | D21 / D22 / D26 (I²C bus 0) |
| ToF 2 (down) VCC / GND | 3V3 (shared splice) / second GND |
| ToF 2 SDA / SCL / XSHUT | D18 / D19 / D27 (I²C bus 1) |
| Motor module IN / VCC / GND | D13 / VIN (5V) / GND (shared splice) |
| Assistant button (planned) | D33, with D32 driven LOW as its ground |

Each ToF sits on its own I²C bus, so both keep the default address 0x29 and need no readdressing. Strapping pins (0, 2, 5, 12, 15) and input-only pins (34 to 39) are avoided. No breadboard: connections are female Dupont crimps and splices, because I want a professional build.

## 5. Software

Code lives in `/home/pi/smartcane/` on the Pi and in `code/` on my laptop.

| File | Job |
|---|---|
| `detect.py` | Camera → Hailo YOLO → text lines like `person ahead, close @0.87`. Computes direction as a bearing on the 120° lens (±10° corridor = "ahead"), distance as a coarse close/near/far from box height |
| `speak_detect.py` | Runs `detect.py`, decides what to say, speaks with espeak-ng, merges ToF distance, sends sync buzzes to the ESP32 |
| `esp32_link.py` | Pi side of the USB serial link |
| `esp32/cane_safety/cane_safety.ino` | ESP32 firmware (Arduino, Pololu VL53L0X library) |
| `smartcane.service` | systemd **user** service (not root, so PulseAudio works), autostarts at boot with `loginctl enable-linger pi` |
| `check_hardware.py`, `setup_pi.sh` | Bring-up checks and installer |
| `haptics.py`, `tof.py` | Older Pi-GPIO versions of the motor and ToF drivers, replaced by the ESP32 |
| `training/` | Dataset prep and training scripts for a custom model (laptop) |

**Vision:** model `/usr/share/hailo-models/yolov8s_h8l.hef`, 80 COCO classes. Camera at 15 fps on purpose, for longer exposure in dim light. Inference on every frame.

**Service settings:** `--interval 0.3 --conf 0.25 --name-conf 0.35 --confirm 3 --max-objects 2 --repeat-after 4.0 --keepalive-after 20 --retry-every 10 --all-classes --fps 15 --ev 0.7`.

**ESP32 build:** `arduino-cli` on the Pi in `~/.local/bin`, board `esp32:esp32:esp32`. The Pi compiles and flashes the ESP32 over the same USB cable.

## 6. How it behaves

**Speech rules (load-bearing, keep them):**

- Detector threshold low (0.25), naming threshold high (0.35). Anything in between is called "obstacle". A wrong name destroys trust, "obstacle" never does.
- An object must appear in 3 consecutive reports (0.3 s apart) before it is spoken. This kills one-frame false labels.
- Never queue speech. If speech is playing, new reports are dropped, so the user never hears about something already passed.
- Never repeat the same thing within 4 s. The repeat timer is keyed on a distance band (close < 0.5 m, near < 1 m, far), so an approaching object is announced again.
- About 40 COCO classes relevant to walking are named. The rest become "obstacle".
- Objects **ahead** get the measured ToF distance ("person ahead, 1.2 metres"). Left and right objects keep the camera's word, because the ToF cone (~25°) only covers straight ahead.
- If the forward ToF sees something under 1 m that the camera has not named, the cane says "obstacle ahead, 80 centimetres". This catches glass, poles and walls.
- Ground hazards are spoken as urgent: "Careful, drop ahead" or "Step up ahead". Urgent speech waits up to 2 s for current speech instead of being dropped.
- Faults are spoken. "Warning, distance sensors not responding" if the ESP32 goes quiet for 2 s. "Warning, ground sensor not working" or "obstacle sensor not working" if one sensor fails for 3 s.
- Audio is checked before every phrase. If PulseAudio has fallen back to `auto_null` (a sink that silently swallows sound), the service reconnects the earbuds instead of "speaking" into nothing.

**Vibration (all done by the ESP32):**

| Forward distance | Feel |
|---|---|
| under 40 cm | continuous 100% |
| 40 to 80 cm | 85%, 120 ms on / 180 ms off |
| 80 to 150 cm | 60%, 100 ms on / 600 ms off |
| ground drop or step | 3 long hard pulses (300 ms on / 150 ms off), overrides everything |
| at boot | 2 short pulses = "ESP32 alive" |

When a sentence starts playing, the Pi sends a sync buzz matched to distance (close 100%/400 ms, near 85%/250 ms, far 60%/150 ms). It fires after speech synthesis, right as audio starts, so the buzz and the words land together.

**Forward ToF:** long-range mode (signal rate 0.1 MCPS, VCSEL periods 18/14), rated ~2 m indoors, shorter in sunlight. Median of 3 readings.

**Downward ToF (ground watch):** default mode. Learns normal ground distance from the median of 10 readings, follows slow drift. Alarm when 2 consecutive filtered readings are more than 150 mm further (drop) or more than 120 mm closer (step). "Nothing in range" counts as a drop. A change lasting over 2 s is treated as a new cane angle and relearned. 2.5 s hold-off between alarms.

**Serial protocol** (115200 baud, one line per message):

```
ESP32 -> Pi   D <ms> <fwd_mm> <down_mm> <fwd_ok> <down_ok> <ground_mm>   (20 Hz, -1 = nothing)
              H drop <mm> <ground>      H step <mm> <ground>
              I <info>                  E <error>
Pi -> ESP32   A0 / A1      auto vibration off / on
              B<duty>,<ms> one buzz
              R1 / R2      ToF 1 forward + ToF 2 down (default), or swapped. Saved in flash
              S            status
              T            wiring test: bus scan + ID registers (healthy = EE AA 10)
```

The Pi opens the port with default DTR/RTS. Setting `dtr=False` then `rts=False` (common advice) passes through the DevKit's auto-reset state and reboots the ESP32 on every open. The Pi also flushes the input buffer on open, because about 1,100 stale readings had piled up while the port was closed.

## 7. Measured performance

| Measurement | Result |
|---|---|
| Pi boot to running | 6.8 s (was 13.4 s before trimming services) |
| Hailo-8L, yolov8s, hardware only | 58 FPS, 13.1 ms latency |
| Hailo use in practice | 15 inferences/s of 58, about 26% |
| detect.py end to end | 30 FPS possible, run at 15 FPS for low light |
| New object to first speech | ~0.6 to 0.9 s (estimate from interval × confirm), was 1.2 to 2.4 s |
| ESP32 → Pi link | 20 Hz, gaps 50.0 to 50.1 ms, no added jitter |
| Forward ToF on the bench | mean 92.4 mm, stdev 0.8 mm |
| Obstacle → vibration | ~50 to 90 ms (estimate: 33 ms ToF + motor spin-up) |
| Spoken warning | 100 to 300 ms after the decision (espeak + Bluetooth buffering) |

Long-range accuracy at 0.5 m to 2 m is **untested**. So are the pothole thresholds on a real pavement.

## 8. Open problems, most serious first

1. **Power.** The UPS through the 5V pin cannot hold the Pi + Hailo + camera + ESP32. The Pi logged dozens of "Undervoltage detected" warnings, then the Hailo dropped off PCIe ("Device disconnected while opening device") and vision went dead. SSH also drops under load. Needs a steady 5V at 5A into the USB-C port (official 27 W supply, or a UPS rated for it). Recovery without reboot: stop `hailort.service`, `rmmod hailo_pci`, remove and rescan PCI device `0001:01:00.0`, `modprobe hailo_pci`.
2. **ToF 2 (downward) has a loose wire.** It drops off its I²C bus entirely. Pothole detection is offline until VCC, GND, SDA (D18) and SCL (D19) are redone.
3. **Earbud pairing is not saved.** The Pi's adapter had `Pairable: no`, so pairing worked but no link key was stored. Fixed with `AlwaysPairable = true` and `PairableTimeout = 0` in `/etc/bluetooth/main.conf`, but the earbuds need pairing once more to get a saved key.
4. **No IMU.** Cane swing changes the downward sensor's angle, which will cause false "drop" alarms. Camera roll also corrupts left/right direction (test frames show a tilted horizon).
5. **Bluetooth audio is the least reliable part.** It has failed silently twice (sink suspend, lost pairing). The product should use wired audio: a USB sound card or a PCM5102A I²S DAC with a wired bone-conduction headset. The Pi 5 has no 3.5 mm jack.
6. The camera's last test frame looked hazy. Check the lens film, a fingerprint, or the focus ring. Focus is manual and should be locked with paint once set for 1 to 5 m.
7. The `hailo_pci` driver floods `dmesg` with harmless `find_vma` WARN traces on this kernel.
8. A static obstacle is repeated every 4 s. Safe while walking, annoying on a desk.

## 9. What I need next

**Hardware to buy or fix:**

- 5V/5A power supply or a UPS that delivers it through USB-C
- Rewire ToF 2
- IMU (MPU6050 or ICM-42688) on the ESP32 for tilt correction and fall detection
- USB audio dongle now, PCM5102A I²S DAC + wired bone-conduction headset for the product
- Two 12 mm waterproof push buttons with shape-coded caps (flat round = power/mode, raised cross = assistant)
- A02YYUW waterproof ultrasonic as backup for glass and water, which fool ToF
- ESP32 screw-terminal board, then a custom PCB with JST connectors
- PETG or ASA enclosure, target IP54

**Software:**

- Assistant button: short press = describe the scene, long press = ask a question
- Pre-rendered audio clips for common warnings, so speech starts with no synthesis delay
- A natural voice (Piper) and Indian languages
- Tune drop and step thresholds on a real pavement, add IMU tilt compensation
- Custom detection model: about 93 to 150 curated classes (80 COCO + potholes, manholes, open drains, stairs, kerbs, poles, bollards, traffic cones, auto-rickshaws, cattle). Datasets found: RDD2022, BharatPothole, Intel Unnati, Obstacle-Dataset, Open Images V7 subset. Train on my laptop (RTX 4060, Windows, venv at `C:\ml\venv`), compile to `.hef` with the Hailo Dataflow Compiler in WSL2 (needs a Hailo Developer Zone account)
- Indian currency recognition and bus-number OCR (custom data needed)
- Read-only root filesystem (overlayfs) before shipping, so power loss cannot corrupt the SD card
- GPS logging and the shared hazard map

**Testing:** 10 to 20 blind users through NGOs, blind schools, NAB or Saksham. Measure outdoor detection accuracy, false alarm rate, battery hours, handle weight and water resistance.

## 10. Hard limits to respect

- A 300-class model is the wrong target. Every prebuilt Hailo-8L detection model is 80-class COCO, and 600-class Open Images models are reported to fail HEF compilation with `BackendAllocatorException`. Unknown objects are covered by the "obstacle" fallback.
- 99% accuracy is not a real target. Reliability comes from model + 3-report confirmation + ToF fusion together.
- True offline scene description or Q&A needs a vision-language model this hardware cannot run. Offline "scene description" is template sentences built from detections. Rich description is an optional online mode.
- Linux will not boot in 1 to 2 s. That is why the safety loop lives on the ESP32.

## 11. Working rules

- Measure before claiming. Every number in a status update comes from a test on the device.
- A silent failure is the worst failure. Any part that stops working must be announced to the user by voice.
- Vibration first, speech second. Vibration says how urgent, speech says what.
- Prefer the vaguer true statement ("obstacle") over a specific false one ("dog").
- Long installs and flashes on the Pi run detached (`nohup`), because SSH drops under load.
- Prices in USD for parts, INR for retail.

Pi access for an agent with shell access: `ssh -i ~/.ssh/pi_solver_key pi@192.168.3.51` (local network only).
