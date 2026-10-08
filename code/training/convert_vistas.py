#!/usr/bin/env python3
"""Smart cane - Mapillary Vistas v2.0 polygons to YOLO boxes, plus a coverage report.

Vistas labels every pixel of 25,000 street photos from six continents, so it
answers two questions:

  1. Training data: every object whose label appears as "mapillary:<label>" in
     classes_v2.yaml becomes a box (the extremes of its polygon). Boxes
     narrower than --min-px at the training width are dropped.
  2. Coverage (--coverage): of all countable objects in the validation photos
     (labels Vistas marks as instances, plus potholes), what share falls into
     one of our classes? This is the "do we cover 80 % of objects" number.
     It counts object instances, weighted by how often they occur on real
     streets, not label types.

    python convert_vistas.py --root "D:/smart cane 2.0/datasets/raw/mapillary_vistas" \
        --out "D:/smart cane 2.0/datasets/vistas_yolo"
    python convert_vistas.py --root ... --coverage
"""
import argparse
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SPLITS = {"training": "train", "validation": "val"}


def our_labels(classes_file):
    cfg = yaml.safe_load(Path(classes_file).read_text())
    return {s.partition(":")[2]: c["name"] for c in cfg["classes"]
            for s in c["src"] if s.startswith("mapillary:")}


def box(poly, W, H):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    x0, x1 = max(0.0, min(xs)), min(float(W), max(xs))
    y0, y1 = max(0.0, min(ys)), min(float(H), max(ys))
    return (x0 + x1) / 2 / W, (y0 + y1) / 2 / H, (x1 - x0) / W, (y1 - y0) / H


def coverage(root, mapping, cfg):
    countable = {l["name"] for l in cfg["labels"] if l.get("instances")} | {"object--pothole"}
    countable = {l for l in countable if not l.startswith("marking")}
    total, covered, missing = 0, 0, Counter()
    for f in (root / "validation" / "v2.0" / "polygons").glob("*.json"):
        for o in json.loads(f.read_text())["objects"]:
            if o["label"] in countable:
                total += 1
                if o["label"] in mapping:
                    covered += 1
                else:
                    missing[o["label"]] += 1
    print(f"countable objects in Vistas validation: {total}")
    print(f"covered by our classes: {covered} ({covered / total:.1%})")
    print("most frequent uncovered:")
    for label, n in missing.most_common(15):
        print(f"  {n:7d}  {n / total:6.2%}  {label}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out")
    ap.add_argument("--classes", default=str(HERE / "classes_v2.yaml"))
    ap.add_argument("--min-px", type=float, default=8)
    ap.add_argument("--train-width", type=int, default=640)
    ap.add_argument("--coverage", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    mapping = our_labels(args.classes)
    cfg = json.loads((root / "config_v2.0.json").read_text())
    if args.coverage:
        coverage(root, mapping, cfg)
        return

    out = Path(args.out)
    names = sorted(mapping)
    counts, small = Counter(), 0
    for vsplit, ysplit in SPLITS.items():
        (out / "images" / ysplit).mkdir(parents=True, exist_ok=True)
        (out / "labels" / ysplit).mkdir(parents=True, exist_ok=True)
        for f in sorted((root / vsplit / "v2.0" / "polygons").glob("*.json")):
            img = root / vsplit / "images" / f"{f.stem}.jpg"
            if not img.exists():
                continue
            d = json.loads(f.read_text())
            lines = []
            for o in d["objects"]:
                if o["label"] not in mapping or len(o["polygon"]) < 3:
                    continue
                cx, cy, w, h = box(o["polygon"], d["width"], d["height"])
                if w * args.train_width < args.min_px or h <= 0:
                    small += 1
                    continue
                counts[mapping[o["label"]]] += 1
                lines.append(f"{names.index(o['label'])} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            dst = out / "images" / ysplit / img.name
            if not dst.exists():
                try:
                    os.link(img, dst)
                except OSError:
                    shutil.copy2(img, dst)
            (out / "labels" / ysplit / f"{f.stem}.txt").write_text(
                "\n".join(lines) + ("\n" if lines else ""))
    (out / "data.yaml").write_text(yaml.safe_dump({"names": names}))
    print("boxes per class:", dict(counts.most_common()))
    print(f"dropped as too small: {small}")


if __name__ == "__main__":
    main()
