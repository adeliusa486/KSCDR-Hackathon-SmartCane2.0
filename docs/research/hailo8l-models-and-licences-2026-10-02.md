# Hailo-8L model compatibility and licences (research, 2 Oct 2026)

Prep for Phase 3 Step 3.1, done while Phase 1 waits on hardware. Desk
research only: nothing here was compiled or run. Each claim names its source
and how strong that source is. Step 3.1 must recheck all of it against
Hailo's own documentation on the day the step runs.

## Findings

**1. The Pi sits exactly on Hailo's 2025-01 software suite.** Hailo's
compatibility table row: suite 2025-01 = Dataflow Compiler v3.30.0, HailoRT
v4.20.0, Integration Tool v1.20.0, **Model Zoo v2.14.0**, TAPPAS v3.31.0.
The Pi runs HailoRT 4.20.0 and `hailo-tappas-core` 3.31.0
(`baseline_versions.txt`), so the matching compiler is DFC 3.30.0 and the
matching Model Zoo is v2.14. *Source: Hailo community thread quoting the
table, which lives in the Developer Zone user guide. Strength: secondary,
but two independent version numbers on the Pi match the same row.*

**1b. Model Zoo v2.14 already has the candidates Step 3.1 needs, for
Hailo-8L, with compiled HEFs.** From its `HAILO8L_object_detection` table:

| Model | mAP (COCO) | Zoo FPS, batch 1 |
|---|---|---|
| yolov8n / s / m | 37.0 / 44.6 / 49.9 | 194 / 88 / 50 |
| yolov10n / s / b | 38.5 / 45.9 / 52.0 | 128 / 63 / 23 |
| yolov11n / s / m | 39.0 / 46.3 / 51.1 | 124 / 64 / 34 |
| YOLOv5, v6, v7, YOLOX, NanoDet, DAMO-YOLO, SSD MobileNet | 23 to 51 | 20 to 356 |

All 640x640 except some YOLOX, NanoDet and SSD variants. The Zoo's FPS is
not this Pi's FPS: it lists yolov8s at 88, the Pi measured 58.17 *(Step
1.1)*, most likely because the Pi 5 gives the HAT a single PCIe lane.
Benchmark every candidate on the Pi (Step 3.2). *Source: hailo_model_zoo
v2.14 docs on GitHub. Strength: vendor documentation.*

**2. HEF files do not work on an older runtime.** A HEF from a newer
compiler fails on an older HailoRT ("Unsupported hef version"). Hailo staff
answers pair them one to one (HailoRT 4.17 with DFC 3.27, 4.18 with 3.28).
*Source: several Hailo community threads. Strength: consistent forum
reports.* Consequence: every HEF the cane runs must come from DFC 3.30, or
the Pi's HailoRT must be upgraded first.

**3. Hailo-8 and 8L stay on their own software line.** Ultralytics' Hailo
page states "Hailo-8 / Hailo-8L use DFC v3.x". Hailo-10H and 15 use the 5.x
line, and the Model Zoo keeps a v2.x branch for Hailo-8/8L. *Source:
docs.ultralytics.com/integrations/hailo, plus an analysis article. Strength:
vendor documentation.*

**4. YOLO26 reached the Model Zoo in v2.18** (Hailo community post, 3 Apr
2026). The post names precompiled HEFs for Hailo-8. It does not mention
Hailo-8L or which runtime v2.18 needs. *Inference, unverified:* v2.18 is
newer than the 2025-01 suite, so its HEFs will not load on HailoRT 4.20
(finding 2).

**5. Ultralytics exports HEF directly** since ultralytics 8.4.97:
`model.export(format="hailo")`. YOLOv8 and YOLO11 detection are validated on
Hailo-8L and YOLO26 is supported. Validation reference: **HailoRT 4.23**.
It needs Linux x86_64 and the DFC wheel. At least 1,024 varied calibration
images are recommended. *Source: Ultralytics docs. Strength: vendor
documentation.* The laptop has ultralytics 8.4.155, new enough, and WSL2
now works (MEMORY.md, 2 Oct).

**6. Licence: every Ultralytics model, including the one the cane runs
today, is AGPL-3.0 or needs an Enterprise licence.** Ultralytics states that
an Enterprise licence is required for "any commercial product or service"
and "embedded deployments" unless the whole project is open-sourced under
AGPL-3.0. That covers YOLOv8 (the current `yolov8s_h8l.hef`), YOLO11 and
YOLO26. *Source: ultralytics.com/license. Strength: the licensor's own
page.* This is a product decision, not an engineering detail (see below).

**7. Hailo now belongs to Microchip.** Microchip completed the acquisition
on 21 Sept 2026 and says it will keep supporting Hailo's existing products,
software and customers. *Source: Microchip press release via Nasdaq and MFN.
Strength: primary.* An analysis piece (beri.net, opinion) points out that
Microchip's product-longevity pledge covers chips, not compilers or SDKs,
that the DFC licence is "revocable", and that nothing public commits to the
Hailo-8/8L branch. *Strength: opinion, but the licence wording it quotes can
be checked in the DFC licence itself.*

## What this means for the plan

- **Two ways into Phase 3.** (a) Stay on HailoRT 4.20, take ready HEFs from
  Model Zoo v2.14 for benchmarking, and compile custom models with DFC 3.30.
  This already covers YOLOv8, YOLOv10, YOLO11, YOLOX, NanoDet and DAMO-YOLO
  (finding 1b) with no change to the Pi. (b) Upgrade the Pi to the runtime that
  current tools validate against (HailoRT 4.23 per Ultralytics), with the
  matching driver and firmware, as its own tested step with the SD image as
  rollback. Option (b) opens YOLO26 and the direct Ultralytics export. It
  repeats the DKMS risk seen on 19 Sept. First check what Raspberry Pi's apt
  repository offers: `apt-cache policy hailo-all hailort hailo-dkms`.
- **The licence decision comes before any training.** Choices: open-source
  the project under AGPL-3.0 (which fits an assistive device funded through
  grants and NGOs, but exposes the code and models), buy an Ultralytics
  Enterprise licence, or use permissively licensed detectors from the Model
  Zoo. Not checked today, from memory only, so read each repository's
  LICENSE file before relying on it: YOLOX, NanoDet and DAMO-YOLO are
  usually listed as Apache-2.0, YOLOv6 and YOLOv7 as GPL-3.0, YOLOv5 and
  YOLOv10 as AGPL-3.0. Until the decision, treat a model's licence as a hard
  gate in the scorecard (`phase3_DRAFT.md`).
- **Freeze the toolchain.** Archive the exact DFC wheel, HailoRT packages,
  Model Zoo commit and calibration set used for the shipped HEF, as far as
  the DFC licence allows. A product must be rebuildable after a vendor
  changes its plans.

## Sources

- Hailo community, compatibility table row for suite 2025-01: https://community.hailo.ai/t/yolov8-custom-model-hef-compilation-error-on-hailo-8-with-hailort-4-20-0/19032
- Hailo Model Zoo v2.14, Hailo-8L detection models: https://github.com/hailo-ai/hailo_model_zoo/blob/v2.14/docs/public_models/HAILO8L/HAILO8L_object_detection.rst
- Hailo community, HEF from newer DFC on older HailoRT: https://community.hailo.ai/t/custom-yolov8-hef-compiled-with-dfc-5-3-0-not-loading-on-hailo-15h-hailort-4-20-1-version-mismatch/19390
- Hailo community, DFC for older HailoRT: https://community.hailo.ai/t/where-can-i-get-dfc-v3-25-0-for-hailort-4-15/19297
- Hailo community, YOLO26 in Model Zoo 2.18: https://community.hailo.ai/t/yolo-26-support-for-hef-in-hailo-8/19034/2
- Ultralytics Hailo integration: https://docs.ultralytics.com/integrations/hailo
- Ultralytics licensing: https://ultralytics.com/license
- Microchip completes Hailo acquisition: https://www.nasdaq.com/articles/microchip-technology-completes-acquisition-hailo
- Analysis (opinion): https://www.beri.net/article/microchip-hailo-acquisition-closed-product-longevity-pledge-dataflow-compiler-license
