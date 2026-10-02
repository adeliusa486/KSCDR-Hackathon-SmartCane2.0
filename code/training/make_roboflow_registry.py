#!/usr/bin/env python3
"""Write roboflow_sources.yaml: exact project, version and label names of every
Roboflow Universe set classes_v2.yaml uses, read from the Roboflow API.
Needs ROBOFLOW_API_KEY. Rerun when a source is added or changed."""
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from roboflow_fetch import inspect  # noqa: E402

REGISTRY = {
    "starvision": "malzag3-uic-edu/starvision",
    "sideguide": "scottsdale/sideguide",
    "strollers1": "furnitureselectronics/ultimite_strollers_detection",
    "strollers2": "thales-a5kye/stroller_final",
    "escooter": "kdigital/electric-scooter-cd7hw",
    "etg": "etg-ik2gp/electric_scooter",
    "exit": "emergency-exit-signs/emergency-exit-signs",
    "wetfloor": "lena-f7w17/wet-floor-detection1",
    "underground": "labelimg-djgsu/underground-pnj5a",
    "esera": "esera/bollards-crosswalk-stairs",
    "bump1": "speed-bump-detection/speed-bump-detection-se0eh",
    "bump2": "detection-system/humps-bumps-potholes-detection",
    "tactile": "susam/tactile-pavement",
    "atm": "mehant-kammakomati/atm-dataset",
    "openhole": "northeastern-4sfxe/construction-safety-open-hole-excavation-detection",
    "pillar": "adli/pillar",
    "risk": "pbl5mu/risk-detection-1",
    "obstacle": "visually-impaired-obstacle-detection-uxdze/obstacle-detection-yeuzf",
    "aid": "kartezyencorp/aid-for-the-blind",
    "blind725": "obstacles-for-blind-zjnnn/obstacles-for-blind",
}

out = {}
for short, slug in REGISTRY.items():
    r = inspect(slug)
    if "error" in r:
        sys.exit(f"{slug}: {r['error']}")
    out[f"rf-{short}"] = {"project": slug, "version": r["latest"], "images": r["images"],
                          "license": r["license"], "labels": sorted((r["classes"] or {}).keys())}
    print(f"rf-{short}: v{r['latest']}, {r['images']} images, {r['license']}")
header = ("# Roboflow Universe sources for classes_v2.yaml, read from the Roboflow API.\n"
          "# Written by make_roboflow_registry.py. roboflow_fetch.py downloads these,\n"
          "# check_classes.py validates every rf- source against the labels here.\n")
(HERE / "roboflow_sources.yaml").write_text(
    header + yaml.safe_dump(out, sort_keys=True, allow_unicode=True), encoding="utf-8")
