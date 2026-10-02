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
    args = ap.parse_args()

    cfg = yaml.safe_load(Path(args.file).read_text())
    classes = cfg["classes"]
    oiv7 = set(json.loads(Path(args.oiv7).read_text()))
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
            elif ds == "oiv7":
                checked += 1
                if label not in oiv7:
                    errors.append(f"{c['name']}: {s} is not an Open Images V7 class")
        if not checked and not c.get("confirm"):
            errors.append(f"{c['name']}: no checkable source, so it must say confirm: true")

    print(f"{len(classes)} classes (expected {args.expect})")
    print("by group :", dict(Counter(c["group"] for c in classes)))
    print("by danger:", dict(Counter(c["danger"] for c in classes)))
    ready = [c["name"] for c in classes if not c.get("confirm")]
    print(f"data available now (COCO / Open Images): {len(ready)}")
    print(f"waiting on accounts or downloads (confirm): {len(classes) - len(ready)}")
    print(f"region classes (poor fit for boxes): {[c['name'] for c in classes if c.get('region')]}")
    if len(classes) != args.expect:
        errors.append(f"expected {args.expect} classes, found {len(classes)}")
    for e in errors:
        print("ERROR", e)
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
