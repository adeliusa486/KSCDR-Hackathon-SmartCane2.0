#!/usr/bin/env python3
"""Check classes_v2.yaml: count, duplicates, and that every coco: and oiv7:
source label really exists. Mapillary, Roboflow, OD and RDD labels cannot be
checked offline, so a class that relies only on them must say confirm: true.

    python check_classes.py [classes_v2.yaml] [--oiv7 C:/ml/oiv7_classes.json]
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prepare_datasets import COCO  # noqa: E402

CHECKABLE = {"coco", "oiv7"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file", nargs="?", default=str(Path(__file__).parent / "classes_v2.yaml"))
    ap.add_argument("--oiv7", default="C:/ml/oiv7_classes.json")
    ap.add_argument("--expect", type=int, default=150)
    ap.add_argument("--mtsd", default="D:/smart cane 2.0/datasets/raw/mapillary_mtsd/mtsd_fully_annotated_annotation.zip",
                    help="MTSD annotation zip, checks mapillary-mtsd: sources if present")
    ap.add_argument("--vistas", default="D:/smart cane 2.0/datasets/raw/mapillary_vistas/config_v2.0.json",
                    help="Vistas config, checks mapillary: sources if present")
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.file).read_text())
    classes = cfg["classes"]
    oiv7 = set(json.loads(Path(args.oiv7).read_text()))
    reg_file = Path(__file__).resolve().parent / "roboflow_sources.yaml"
    rf = yaml.safe_load(reg_file.read_text(encoding="utf-8")) if reg_file.exists() else {}
    vistas = None
    if Path(args.vistas).exists():
        vistas = {l["name"] for l in json.loads(Path(args.vistas).read_text())["labels"]}
    mtsd = None
    if Path(args.mtsd).exists():
        import zipfile
        z = zipfile.ZipFile(args.mtsd)
        mtsd = {o["label"] for n in z.namelist() if n.endswith(".json") and "/annotations/" in n
                for o in json.loads(z.read(n)).get("objects", [])}
    errors = []

    names = [c["name"] for c in classes]
    for n, k in Counter(names).items():
        if k > 1:
            errors.append(f"duplicate class name: {n}")
    owner = {}
    for c in classes:
        for key in ("name", "say", "group", "danger", "why", "src"):
            if key not in c:
                errors.append(f"{c.get('name')}: missing {key}")
        if c.get("danger") not in ("high", "medium", "low"):
            errors.append(f"{c['name']}: danger must be high, medium or low")
        checked = 0
        for s in c["src"]:
            ds, _, label = s.partition(":")
            if s in owner:
                errors.append(f"source label {s} used by both {owner[s]} and {c['name']}")
            owner[s] = c["name"]
            if ds == "coco":
                checked += 1
                if label not in COCO:
                    errors.append(f"{c['name']}: {s} is not a COCO class")
            elif ds.startswith("rf-"):
                checked += 1
                if ds not in rf:
                    errors.append(f"{c['name']}: {ds} is not in roboflow_sources.yaml")
                elif label not in rf[ds]["labels"]:
                    errors.append(f"{c['name']}: {s} is not a label of {rf[ds]['project']}")
            elif ds == "mapillary" and vistas is not None:
                checked += 1
                if label not in vistas:
                    errors.append(f"{c['name']}: {s} is not a Mapillary Vistas v2.0 label")
            elif ds == "mapillary-mtsd" and mtsd is not None:
                checked += 1
                if label != "any-other-sign" and not any(m == label or m.startswith(label + "-") for m in mtsd):
                    errors.append(f"{c['name']}: {s} matches no MTSD label")
            elif ds == "oiv7":
                checked += 1
                if label not in oiv7:
                    errors.append(f"{c['name']}: {s} is not an Open Images V7 class")
        if not checked and not c.get("confirm"):
            errors.append(f"{c['name']}: no checkable source, so it must say confirm: true")

    print(f"{len(classes)} classes (expected {args.expect})")
    print("by group :", dict(Counter(c["group"] for c in classes)))
    print("by danger:", dict(Counter(c["danger"] for c in classes)))
    ready = [c["name"] for c in classes if not c.get("confirm") or
             (mtsd is not None and any(s.startswith("mapillary-mtsd:") for s in c["src"])) or
             (vistas is not None and any(s.startswith("mapillary:") for s in c["src"])) or
             any(s.split(":")[0] in rf for s in c["src"])]
    print(f"data available now (COCO / Open Images / Mapillary / Roboflow): {len(ready)}")
    print(f"waiting on accounts or downloads (confirm): {len(classes) - len(ready)}")
    print(f"region classes (poor fit for boxes): {[c['name'] for c in classes if c.get('region')]}")
    if len(classes) != args.expect:
        errors.append(f"expected {args.expect} classes, found {len(classes)}")
    for e in errors:
        print("ERROR", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
