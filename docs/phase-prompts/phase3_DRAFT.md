# PHASE 3 PROMPT (DRAFT): AI model selection, training and low-latency vision

> **DRAFT, written 2 Oct 2026 at Adeel's request, before the Phase 1 and
> Phase 2 gates.** State on that date: Step 1.1 PASS, Step 1.2 BLOCKED (the
> UPS supply failed at normal load, the USB-C supply is not fitted yet),
> Steps 1.3 to 1.5 and all of Phase 2 not started. Checked against
> `detect.py`, `speak_detect.py`, `code/training/*`, the Step 1.1 and 1.2
> records, and the laptop's training setup.
>
> Tags: *(Step 1.1)*, *(Step 1.2)* measured in that step. *(code)* read from
> the code on 2 Oct, recheck if Phases 1 and 2 change it. *(laptop)* checked
> on the development laptop on 2 Oct. *(verify)* a statement about a third
> party (Hailo, Raspberry Pi, a licence) that was not checked against the
> official source today. Check it before relying on it. *(gate)* and
> *(Phase 2)* must be filled from those gates before this prompt is used.
>
> Do not start Phase 3 from this draft. Rename it `phase3.md` only after the
> Phase 2 gate passes and every *(gate)* and *(Phase 2)* item is filled in.

You are continuing the smart cane consumer-readiness work. The master prompt
is `docs/consumer-readiness-plan.md`. Its ABSOLUTE RULE, engineering
principles, section 2 safety behaviour, section 5 model optimisation rules and
section 6 instrumentation rules still apply in full. This prompt replaces only
the master's Phase 3 section.

## How every step is recorded

Same as Phases 1 and 2: `experiments/phase3/step3_N_<name>/` with
`README.md`, `test_plan.md`, `results.json`, `raw_results.csv`,
`terminal_output.txt`, `before/`, `after/`, `failure_log.md`. Snapshot before
and after with `code/tools/snapshot_pi.sh`. Append each session to section 14
of `MEMORY.md`. Write every pass limit into `test_plan.md` before the first
measurement.

Tag `known-good-phase-2` before the first change. The current model must stay
one command away: keep `yolov8s_h8l.hef` and `coco.txt` untouched and switch
models only through `--model` and `--labels`.

## Preconditions

| Item | Status on 2 Oct 2026 | Evidence needed |
|---|---|---|
| Phase 1 gate: power stable | **Open.** UPS feed: 11 under-voltage events in 9.5 min at normal service load *(Step 1.2)* | 0 under-voltage events in the 2 h worst-case run on the USB-C supply *(gate)* |
| Phase 1 gate: Hailo stays connected | 58.17 FPS, 13.14 ms after a power cycle *(Step 1.1)* | 0 disconnects through Phase 1 and 2 *(gate)* |
| Silent vision death is detected | **Open.** Vision ran dead for 1 h 46 min with no warning *(Step 1.1, F1)* | the Step 2.5 result: an explicit warning within a stated time *(Phase 2)* |
| Camera geometry frozen | **Open.** FOV is an estimate, bearings use 120 degrees *(Step 1.1)* | sensor mode, measured FOV, distortion model, bearing error *(Phase 2, Step 2.2)* |
| Camera mount position decided | **Open.** MEMORY.md section 8 chose a chest or shoulder clip. The bench rig is neither | Adeel's decision, written down. The dataset (Step 3.5) is worthless if the mount height changes afterwards |
| IMU tilt available per frame | **Open** | *(Phase 2, Step 2.2)*. Needed to label "camera tilted" data in Step 3.6 |
| Training data available | **Open.** `C:\ml\smartcane` holds 90 KB. No dataset downloaded *(laptop)* | Roboflow key, manual downloads (MEMORY.md 19 Sept list), Hailo Developer Zone account for the compiler |

## Known facts and defects carried into Phase 3

1. **Current model and runtime** *(Step 1.1)*. `yolov8s_h8l.hef`, sha256
   `a051fc15...ba3c9`, input 640x640x3 UINT8 NHWC, on-chip NMS by class (80
   classes, at most 100 boxes per class). HailoRT 4.20.0, firmware 4.20.0,
   `hailo_pci` 4.20.0 through DKMS, PCIe Gen3 x1. `hailortcli benchmark`:
   58.17 FPS, 13.14 ms. These numbers have no camera, no Python
   post-processing and no speech in them.

2. **The pipeline has no timestamps** *(code)*. `detect.py` calls
   `capture_array("lores")` and then a synchronous `hailo.run(frame)`, one
   frame in flight. It prints a text report every `--interval` (0.3 s) with
   at most `--limit` 4 detections. `speak_detect.py` parses that text through
   a pipe and never logs it. No stage records a time. The plan's figures
   "30 FPS end-to-end" and "0.6 to 0.9 s to first speech" are estimates. The
   report count (81 and 83 lines in 30 s at fps 15 and 30, *Step 1.1*) is the
   `--interval` cap, not the vision rate.

3. **The model sees a squeezed image** *(Step 1.1)*. The lores stream is
   640x640, scaled from a 16:9 sensor crop, so every object is squeezed 1.78x
   horizontally. YOLO is trained on aspect-correct, letterboxed images. The
   accuracy cost is not measured. Narrow objects (poles, bollards, people side
   on) are the likely losers.

4. **Possible colour-channel swap** *(verify)*. Picamera2 documents
   `"RGB888"` as pixels stored in [B, G, R] order. `detect.py` asks for
   `"RGB888"` and feeds the array straight to the HEF. Check what channel
   order the HEF expects, then measure accuracy both ways on the same frames.

5. **Low light** *(Step 1.1)*. At fps 15 the exposure sits at its 66.2 ms
   ceiling with analogue gain 11.64 at 42 lux indoors. 66 ms smears a walking
   scene. fps 15 was chosen for brightness. The blur against noise trade-off
   has never been measured.

6. **Labels must match the HEF exactly, or classes vanish silently**
   *(code)*. `extract_detections()` maps class index `i` to line `i` of the
   label file and skips any index past the end of the file
   (`if class_id >= len(labels): continue`). A 93-class HEF run with
   `coco.txt` loses its 13 hazard classes with no error.

7. **A new class is never spoken by name unless the code is changed**
   *(code)*. `resolve()` names a detection only if its class is in the
   hard-coded `RELEVANT` set (COCO names). `pothole`, `bollard` or `stairs`
   would always come out as "obstacle". `detect.py` and `speak_detect.py`
   also carry two different `PRIORITY` lists. `speak_detect.py` lists `pole`,
   which COCO does not have.

8. **The thresholds belong to the current model** *(code)*. Detector
   threshold 0.25, naming threshold 0.35 (the service passes 0.35, the code
   default is 0.55), confirmation 3 reports with a one-report grace, repeat
   4 s. A different model, or the same model after quantisation, has a
   different score distribution. Re-derive both thresholds per model (Step
   3.9). Never carry them over.

9. **Distance for left and right objects comes from box height only**
   *(code)*. `nearness()`: close above 0.55 of frame height, near above 0.25,
   else far. Only objects "ahead" get the ToF distance. "Minimum useful
   detection distance" in Step 3.5 needs real distances, so measure them on
   the test routes. Do not infer them from box size.

10. **The training data pipeline is unfinished** *(code)*.
    `prepare_datasets.py` downloads sources and writes `smartcane.yaml`
    pointing at `images/train` and `images/val`, but nothing fills those
    folders. `LABEL_ALIASES` is defined and never applied. No code merges,
    remaps or splits images. Train and validation splits come from each
    source's own split (`fetch_openimages.py` takes Open Images' train and
    validation sets as they are). For dashcam sets like BharatPothole, that
    puts neighbouring video frames on both sides of the split, which Step 3.7
    forbids.

11. **Class list: 150 classes for US and Gulf streets** *(Adeel, 2 Oct
    2026; branch `prep/phase3-150-classes`)*. Target environment changed from
    India to **USA and Gulf roads and sidewalks plus general objects**, spoken
    in **English with US terms** (sidewalk, curb, crosswalk, trash can).
    `code/training/classes_v2.yaml` has 150 classes, each with spoken name,
    danger level, reason and data sources. 104 have data now (COCO, Open
    Images), 46 wait on Mapillary Vistas, the Mapillary Traffic Sign Dataset
    and Roboflow (Adeel is creating the accounts). Curb, crosswalk, fence and
    rail track are surfaces, a poor fit for boxes: candidates for a
    segmentation model or the ground ToF. The old `classes.yaml` (93,
    India-focused, header says 88) and its targets are superseded. Replace the
    targets with the Step 3.5 table and the scorecard.

    Merged datasets leave objects unlabelled (an Open Images photo fetched
    for "bench" may show an unlabelled car). Pseudo-label the gaps with
    teacher models before training: COCO weights for the COCO classes and
    `C:\ml\yolov8s-oiv7.pt` (601 Open Images classes) for the rest.
    Otherwise the model learns that unlabelled cars are background.

12. **Training and compile environment** *(laptop)*. Windows venv
    `C:\ml\venv`: torch 2.5.1+cu121, ultralytics 8.4.155 (19 Sept). **WSL2
    Ubuntu now starts** (kernel 6.18.33, x86_64) and sees the RTX 4060
    (driver 595.79). MEMORY.md still lists WSL as blocked, which is out of
    date. Inside WSL: Python 3.14.4, no torch, no Hailo Dataflow Compiler.
    DFC wheels are built for specific Python versions. Plan a pinned
    environment for the DFC release you choose.

13. **The compiler must match the runtime on the Pi** *(Step 1.1, research
    2 Oct)*. The Pi runs HailoRT 4.20.0 and TAPPAS 3.31.0, exactly Hailo's
    2025-01 suite: **DFC 3.30.0, Model Zoo v2.14**. HEFs from a newer compiler
    fail on an older runtime. Model Zoo v2.14 already has compiled Hailo-8L
    HEFs for YOLOv8 n/s/m, YOLOv10 n/s/b, YOLO11 n/s/m, YOLOX, NanoDet,
    DAMO-YOLO and more. YOLO26 arrived in Model Zoo v2.18, and Ultralytics'
    direct HEF export is validated on HailoRT 4.23, so both need a runtime
    upgrade on the Pi. That upgrade is its own tested step with an SD image
    first: a DKMS rebuild against the wrong kernel broke the driver on
    19 Sept. Details and sources:
    `docs/research/hailo8l-models-and-licences-2026-10-02.md`.

14. **Class count can break the compile** *(MEMORY.md 19 Sept)*. A 600-class
    Open Images YOLOv8 is reported to fail on Hailo-8 with
    `BackendAllocatorException`. The 8L has fewer resources. Record compile
    success or failure per candidate and class count.

15. **Benchmark hygiene** *(Step 1.1, Step 1.2)*. `hailortcli benchmark`
    returns `HAILO_TIMEOUT` and 0.00 FPS both when another process holds the
    device and after a power-state fault. Stop the service, confirm
    `identify`, run each benchmark twice. Log the kernel under-voltage count,
    Hailo disconnect lines and temperature before and after every run. A run
    with a new under-voltage event is void. The kernel event count, not the
    1 Hz EXT5V sample, decides (Step 1.2: sub-second dips never showed in the
    1 Hz samples).

16. **Memory budget** *(Step 1.1)*. 2 GB RAM. `detect.py` RSS 520 MB, about
    1.2 GB available with the service running, swap 512 MB. Phase 4 may add
    Piper TTS. Measure RSS for each candidate.

17. **Driver noise** *(Step 1.1)*. About 1,230 `find_vma` WARNING stack
    traces per boot from `hailo_pci` on kernel 6.12.109. Inference works.
    Count them in every run so a change in rate is noticed.

18. **Close-range misreads are known** *(MEMORY.md 19 Sept)*. A face at 20 cm
    was called dog or horse. At 2 to 4 m the same model was correct. Evaluate
    at the distances and mount height the product will see.

---

## STEP 3.0 (new): instrument the vision path first

The master's section 6 asks for timestamps everywhere. None exist (fact 2).
No candidate can be compared on latency until they do.

- Write one record per frame, not per text report: sensor timestamp from the
  Picamera2 request metadata (check what the field measures, start of
  exposure or readout), frame-ready time, inference start and end,
  post-processing end, report time. Use `time.monotonic_ns()` and record the
  offset to the sensor clock.
- On the speech side, log decision time, speech start and audio start (Phase
  4 measures the audio end properly).
- Measure capture latency once from photons: film a screen showing a
  millisecond counter, or flash an LED driven by a logged GPIO edge.
- Measure the logging overhead. It must cost under 1 % of frame rate.

Pass: per-stage P50, P90, P95 and P99 for the current model at fps 15 and 30,
over at least 10 min each, and the photon-to-frame figure.

## STEP 3.1: build the candidate matrix

Candidates, none assumed compatible:

```text
yolov8s_h8l (current baseline, on disk)
yolov6n_h8l, yolox_s_leaky_h8l_rpi (already on disk, free to test)
yolov8n, yolov8m
YOLOv11 n / s / m
YOLOv12n, YOLO26 n / s, only if built for the Hailo-8L line
other lightweight detectors in Hailo's Model Zoo for hailo8l
```

For each, record: Model Zoo entry for `hailo8l`, ready HEF or not, DFC
version that builds it, loads on HailoRT 4.20 (fact 13), input size,
post-processing on chip or on CPU, custom training supported, **licence of
the model code and weights**, and licence of every dataset it would be
trained on.

Licence: Ultralytics states that YOLOv8, YOLO11 and YOLO26 need its
Enterprise licence for "any commercial product" and "embedded deployments",
unless the whole project is open-sourced under AGPL-3.0
(ultralytics.com/license, read 2 Oct 2026). **Adeel's decision, 2 Oct 2026:
no licence for now, the cane is a professional prototype for presentation,
not a product on sale.** So the licence is not a gate in Phase 3. Still record
each candidate's licence from its repository, because Step 5.11 must settle
it before any sale.

Start with what runs without touching the Pi: Model Zoo v2.14 HEFs (fact
13). A runtime upgrade for YOLO26 or the Ultralytics export is worth doing
only if the v2.14 candidates fall short on the scorecard.

Use Hailo's documentation from the day of testing and write its version and
date into the record.

## STEP 3.2: benchmark every candidate on the real device

On the Pi, the real camera and the instrumented pipeline (Step 3.0), measure
for each candidate: Hailo FPS and latency (`hailortcli`), capture,
pre-processing, post-processing, end-to-end FPS and latency, CPU, RAM (RSS),
temperature, frame drops, and power (Step 1.3 meter).

Report P50, P90, P95 and P99, never the mean alone.

Two kinds of run:

- **Timing runs** on the live camera, 10 min each after a 5 min warm-up, so
  thermal effects show.
- **Accuracy runs** on a fixed set of recorded frames from the cane camera,
  fed through the same pre-processing into `hailo.run`. Live scenes are not
  repeatable, so they cannot compare models.

Apply fact 15 to every run.

## STEP 3.3: input resolution and aspect

Test 512x512, 640x640 and 768x768 where the candidate compiles. Add a
rectangular input matched to the camera's aspect (for example 640x352 or
640x384) and train for it. It removes both the squeeze (fact 3) and the dead
letterbox area.

Measure small-object recall, and recall for person, pole, vehicle, stairs,
kerb, traffic cone, bollard and pothole, at the distances fixed in Step 3.5.
Choose by navigation performance, not by mAP.

## STEP 3.4: camera pipeline

Start from the Phase 2 sensor-mode decision *(Phase 2)*. Then compare:

- squeeze (today), letterbox, centre crop, rectangular model input
- colour order (fact 4)
- fps 15 against fps 30 with a capped exposure: blur against noise, measured
  as recall on walking footage, not judged by eye
- ISP scaling to the lores stream (PiSP hardware) against CPU resizing
- buffer copies, `capture_array` against request buffers, zero-copy where
  Picamera2 allows

Measure latency, CPU, memory copies and power, with recall held equal or
better.

## STEP 3.5: the custom navigation dataset

Fix the camera mount first (preconditions). Record with the cane camera in
its final mode and position.

Start from the 13 classes in `classes.yaml` and the master's list (person,
car, motorcycle, bicycle, bus, truck, auto-rickshaw, animal, dog, cattle,
pole, bollard, traffic cone, barrier, wall, door, chair, bench, stair, kerb,
pothole, manhole, open drain, road edge, sign, wheelchair). Every class needs
a written reason. For each class record:

```text
why it matters
expected frequency on the test routes
danger level
minimum useful detection distance (measured, fact 9)
minimum useful size in pixels at that distance
acceptable false-positive rate
acceptable false-negative rate
how it is spoken (name, or "obstacle")
```

Decide which hazards the camera owns and which the ground ToF owns (Phase 2
measured what the ToF can find). A pothole the down sensor already catches
reliably may not need a camera class. One it misses does.

People appear in street footage. Check what India's Digital Personal Data
Protection Act 2023 requires for storing and sharing it *(verify)*, and blur
faces in anything that leaves the laptop.

## STEP 3.6: difficult conditions

Everything in the master's list (sunlight, backlight, shadows, night, low
light, rain, dust, haze, motion blur, occlusion, crowds, Indian streets,
roads, sidewalks, markets, narrow lanes, stairs, kerbs, uneven roads, parked
and moving vehicles, tilted, moving and shaking camera, objects at the edge
of the real FOV, small distant obstacles, partly hidden obstacles).

Store per frame: exposure, analogue gain and lux from the Picamera2
metadata, and IMU roll and pitch *(Phase 2)*. Then low light and tilt are
measured strata, not guesses.

## STEP 3.7: leakage audit

Before any training, write the split code that does not exist yet (fact 10).
Split by session, location and source video, never by random frame.
Then check for duplicates, near duplicates (perceptual hash), video-frame
leakage, the same scene, sequence or physical place on both sides, label
errors, class imbalance, empty labels and corrupt files.

The test set comes only from cane-camera recordings that no training source
contains. Public datasets may go into training and validation, never into the
final test set.

## STEP 3.8: train and compile

Train on the RTX 4060. Validate, test, export, compile to HEF in WSL (fact
12). Record DFC version, optimisation level, compression level and compile
time.

The quantisation calibration set comes from the cane camera, in the final
mode, with the same pre-processing and a mix of lighting. Training images
from other cameras give the quantiser the wrong statistics.

Evaluate precision, recall, mAP, per-class AP and recall, false positives,
false negatives, confidence calibration and small-object performance. High
training metrics alone accept nothing.

## STEP 3.9: before and after Hailo, then integrate

Run the same test frames through the FP32 model and the HEF. Report the
difference per class, for small objects, for confidence shift and for missed
hazards.

Then, per model:

- Re-derive the detector threshold and the naming threshold from the
  calibration curves on the test set (fact 8). Write the rule before looking:
  for example "naming threshold = lowest score at which named-label precision
  is at least 0.95 for every safety class".
- Integration test: label file order equals HEF class order (fact 6), every
  class reaches `resolve()` and can be spoken by name (fact 7), one
  `PRIORITY` list, and a rollback to `yolov8s_h8l.hef` with `coco.txt`,
  tested by switching back and running the service.

### PHASE 3 MODEL SELECTION RULE

Hard gates first. A candidate that fails one is out, whatever its score:

```text
licence allows shipping (Step 3.1)
compiles, and loads on the Pi's HailoRT (fact 13)
fits the memory budget with Phase 4's speech stack (fact 16)
no under-voltage, disconnect or silent stall in a 2 h run
```

Then the scorecard, on our test set:

```text
Safety recall (per safety class, at the Step 3.5 distances)   30%
End-to-end latency P95 (Step 3.0 trace)                       20%
Real application FPS                                          15%
False-positive rate                                           10%
Small-object detection                                        10%
Low-light performance                                          5%
Outdoor performance                                            5%
Power and thermal stability                                    5%
```

Change a weight only with a written reason. Public benchmark FPS is not a
criterion.

### PHASE 3 GATE

Do not continue to Phase 4 until:

* the vision path is instrumented, with per-stage P50 to P99
* every candidate has a licence answer and a compatibility answer
* a model is chosen by the hard gates and the scorecard, on cane-camera data
* FP32 against HEF differences are measured per class
* thresholds are re-derived for the chosen model and written into the
  service unit
* the label file, `RELEVANT` and `PRIORITY` match the chosen HEF, and every
  class can be spoken by name
* the squeeze and colour-order questions are measured and settled
* a 2 h run with the chosen model shows 0 under-voltage events, 0 Hailo
  disconnects and no silent vision stall
* switching back to `yolov8s_h8l.hef` is tested
* the perception path P95 is reported against the master's 100 ms target,
  with what "perception path" includes stated in the record

After the gate, write `docs/phase-prompts/phase4.md` from
`phase4_DRAFT.md`, revised with Phase 3's measurements.
