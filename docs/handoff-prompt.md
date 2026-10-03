# Handoff prompt for a new chat (3 Oct 2026, 13:05)

Paste everything below the line into a new AI assistant chat opened in
`E:\Work\new smart cane 2.0`.

---

You are continuing work on my smart cane for blind and visually impaired
users. It is becoming a professional prototype for a presentation, so accuracy
and honesty matter more than speed: never invent measurements, never call
something done unless it was tested, and say plainly when something failed.
Explain things to me in plain English. I am Adeel.

## Read these first, in this order

1. `MEMORY.md` in the project root: the single source of truth. Read all of
   section 14 (session log), especially every entry dated 2 and 3 October
   2026. Append every session there before you finish.
2. `docs/consumer-readiness-plan.md`: the master 5-phase plan, verbatim. Its
   ABSOLUTE RULE applies: no step starts before the previous one is tested,
   measured and recorded under `experiments/`.
3. `docs/phase-prompts/`: draft prompts for Phases 2 to 5. After each phase
   gate, produce the next phase's prompt revised with what was measured.
4. `docs/research/`: Hailo-8L compatibility and licences, haptics upgrade.

## Working rules I have set

- Work in the plan's order. While a step is blocked on hardware, prepare
  later steps on git branches (`prep/...`), but never deploy prep work to the
  cane before its step. Code lives in git; commit with clear messages.
- Ask me before anything that changes the cane in a hard-to-undo way or
  costs money. I approved the HailoRT 4.23 upgrade (done). The Ultralytics
  Platform sign-up is NOT approved yet (price unknown).
- No model licence needed for now (presentation prototype). Revisit before
  any sale (Step 5.11).
- Target environment: USA and Gulf roads and sidewalks plus general objects.
  Speech in English with US terms (sidewalk, curb, crosswalk, trash can).

## Hardware and access

- Raspberry Pi 5 (2 GB) + AI HAT+ (Hailo-8L) + IMX708 camera on CAM0, ESP32
  DevKit V1 on `/dev/ttyUSB0` driving two VL53L0X ToF sensors and the motor.
- SSH: `ssh -i ~/.ssh/pi_solver_key pi@192.168.3.51`. Code in
  `/home/pi/smartcane/`, tools in `/home/pi/smartcane/tools/`.
- The Pi now runs **HailoRT 4.23.0** built from Hailo's open-source repos
  (not apt). Rollback: `~/smartcane/tools/hailort_rollback.sh`. **Do not run
  `apt upgrade` or change the kernel**: the 4.23 driver is built for kernel
  6.12.109+rpt-rpi-2712 and must be rebuilt after any kernel change.
- Power is still the weak UPS feed into the 5V header pin: under-voltage
  under load (Step 1.2 blocked). `smartcane.service` is enabled but should be
  kept stopped until the 5 V / 5 A USB-C supply is fitted.
- Every SSH logout restarts PulseAudio: never judge audio over SSH.
- The laptop: RTX 4060 8 GB, Python venv `C:\ml\venv` (torch + ultralytics),
  WSL2 Ubuntu with arduino-cli 1.5.1 and esp32 core 3.3.12 for firmware builds.
  Roboflow API key is in the Windows user environment variable
  `ROBOFLOW_API_KEY` (never write it into files).

## Where things stand

Phase 1:
- Step 1.1 baseline: PASS. SD image in `backups/`.
- Step 1.2 power: BLOCKED on the USB-C supply. Journal fix applied and
  tested (J1, J2 pass, J3 fails with a ~3 s log blind window).
- Step 1.3 power measurement: needs a USB-C power meter.
- Step 1.4: **ToF 2 (downward ground sensor) does not work**: it answers the
  boot scan once, then drops off the bus. Weak VCC/GND contact most likely. I
  am rewiring it. Recheck with
  `python3 ~/smartcane/tools/esp32_capture.py --seconds 20 --send T --send S --out /tmp/x`
  (service stopped). Healthy = `tof2 id EE AA 10`.
- Step 1.5 ESP32 safety layer: firmware and Pi link prepared on branch
  `prep/step1.5-esp32-safety` (compiled, unit-tested, NOT flashed). Test plan
  `experiments/phase1/step1_5_esp32/test_plan.md`. It fixes the Pi being
  able to silence the safety vibration (B0,5000 / A0).
- Measured: the ESP32 restarts with the Pi on every Pi reset (11 of 11).

AI model (Phase 3 prep, branch `prep/phase3-150-classes`):
- 152 classes in `code/training/classes_v2.yaml`, every one with verified
  training data (`check_classes.py --expect 152`). Covers 93 % of countable
  street objects in Mapillary Vistas validation photos.
- Merged training set built: `D:\smartcane-data\merged_v2` (235,951 train,
  ~28,000 val images; COCO capped 40k, Open Images 117k, Vistas 20k, MTSD 30k,
  20 Roboflow sets). Original labels backed up in `merged_v2\labels_human`.
  Thin classes (< 300 boxes): bus stop sign, kiosk, pillar, sidewalk closed
  sign, crosswalk button, trailer, construction sign.
- **Running at handoff time** (a background job from the old chat, keeps
  running on the laptop): pseudo-labelling with teachers yolo11m (COCO) and
  yolov8m-oiv7, then training YOLO11s, 152 classes, 40 epochs, batch 12, run
  name `smartcane152_v2`, outputs in `D:\smartcane-data\runs\detect\`.
  Logs: `D:\smartcane-data\pipeline.log`, `pseudo_v2.log`, `train_v2.log`.
  Training needs about 1.5 days. Check `nvidia-smi` and the logs first.
- After training: evaluate per class on the validation split, then build the
  simulation I asked for: run real street photos through the cane's own
  decision code (`speak_detect.py` logic) and score what it would say (name,
  "obstacle", direction) against ground truth. Distances cannot be simulated,
  they need my tape-measure tests (`~/smartcane/tools/tof_check.py`).
- Converting the model for the Hailo-8L: I cannot get the Hailo Dataflow
  Compiler (needs a work email). Route found: Ultralytics Platform managed
  Hailo export (DFC 3.33), whose files need HailoRT 4.23 (now installed).
  Needs my approval and a sign-up.

## What I need to do with my hands

ToF 2 rewiring, the 5 V / 5 A USB-C adapter, a tape measure for distance
tests, and optionally a DRV2605L haptic driver plus an LRA vibration motor
(`docs/research/haptics-upgrade-2026-10-02.md`).

## Lessons from the last chat (do not repeat these)

- Roboflow exports: hidden augmented copies (dedupe them), polygon labels
  (convert to boxes), label names differ from the API list (use the export's
  data.yaml), file names longer than Windows allows.
- Check results, not exit codes. Two downloaders on one file corrupted it.
- Copying hundreds of thousands of small files with Python is very slow on
  Windows. Use `robocopy /MT:32`.
- `pkill -f name` over SSH can kill the SSH session itself. Use
  `pgrep -f "[n]ame"`.

Start by reading MEMORY.md, then check the training job and tell me in plain
English where everything stands.
