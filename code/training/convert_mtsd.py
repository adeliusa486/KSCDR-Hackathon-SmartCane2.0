#!/usr/bin/env python3
"""Smart cane - convert the Mapillary Traffic Sign Dataset (fully annotated) to YOLO.

MTSD labels every sign in the photo with its exact type, split into design
variants and values: "regulatory--yield--g1", "regulatory--maximum-speed-
limit-40--g3". This converter:

  * folds variants onto the sign types in classes_v2.yaml ("mapillary-mtsd:
    regulatory--yield" takes every regulatory--yield--gN, the speed-limit
    entry takes every value), by prefix,
  * labels every other sign as "any-other-sign", which classes_v2.yaml maps to
    the general "traffic sign" class. Dropping them would teach the model
    that those signs are background,
  * drops boxes narrower than --min-px at the training width: a 30 px sign in
    a 4160 px photo is 5 px at 640, nothing a model can learn from.

Only signs are labelled in MTSD. Cars, people and poles in the same photos
are not: run pseudo_label.py on the merged set.

    python convert_mtsd.py --root "D:/smart cane 2.0/datasets/raw/mapillary_mtsd" \
        --out "D:/smart cane 2.0/datasets/mtsd_yolo"
"""
import argparse
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def mtsd_types(classes_file):
    cfg = yaml.safe_load(Path(classes_file).read_text())
    out = []
    for c in cfg["classes"]:
        for s in c["src"]:
            ds, _, label = s.partition(":")
            if ds == "mapillary-mtsd" and label != "any-other-sign":
                out.append(label)
    return sorted(out, key=len, reverse=True)      # longest prefix first


def fold(label, types):
    """Exact type, or a design variant of it ("--gN"). Only the speed-limit
    type also takes a value after a single dash ("-40--g1", "-led-100--g1"),
    so "yield" can never swallow a different sign that merely starts the same."""
    for t in types:
        if label == t or label.startswith(t + "--"):
            return t
        if t.endswith("speed-limit") and label.startswith(t + "-"):
            return t
    return "any-other-sign"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="folder with the unpacked MTSD zips")
    ap.add_argument("--out", required=True)
    ap.add_argument("--classes", default=str(HERE / "classes_v2.yaml"))
    ap.add_argument("--min-px", type=float, default=8, help="minimum box width at --train-width")
    ap.add_argument("--train-width", type=int, default=640)
    args = ap.parse_args()

    root, out = Path(args.root), Path(args.out)
    types = mtsd_types(args.classes)
    names = types + ["any-other-sign"]
    ann_dir = next(root.rglob("annotations"))
    images = {p.stem: p for p in root.rglob("*.jpg")}
    counts, dropped_small, missing = Counter(), 0, 0
    for split in ("train", "val"):
        keys = next(root.rglob(f"splits/{split}.txt")).read_text().split()
        (out / "images" / split).mkdir(parents=True, exist_ok=True)
        (out / "labels" / split).mkdir(parents=True, exist_ok=True)
        for key in keys:
            img = images.get(key)
            ann = ann_dir / f"{key}.json"
            if img is None or not ann.exists():
                missing += 1
                continue
            d = json.loads(ann.read_text())
            W, H = d["width"], d["height"]
            lines = []
            for o in d.get("objects", []):
                b = o["bbox"]
                w, h = (b["xmax"] - b["xmin"]) / W, (b["ymax"] - b["ymin"]) / H
                if w * args.train_width < args.min_px:
                    dropped_small += 1
                    continue
                cx, cy = (b["xmin"] + b["xmax"]) / 2 / W, (b["ymin"] + b["ymax"]) / 2 / H
                t = fold(o["label"], types)
                counts[t] += 1
                lines.append(f"{names.index(t)} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
            dst = out / "images" / split / img.name
            if not dst.exists():
                try:
                    os.link(img, dst)
                except OSError:
                    shutil.copy2(img, dst)
            (out / "labels" / split / f"{key}.txt").write_text("\n".join(lines) + ("\n" if lines else ""))
    (out / "data.yaml").write_text(yaml.safe_dump({"names": names}))
    print("boxes per type:", dict(counts))
    print(f"dropped as too small: {dropped_small}, images or annotations missing: {missing}")


if __name__ == "__main__":
    main()
