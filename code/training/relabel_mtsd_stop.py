#!/usr/bin/env python3
"""Smart cane - give MTSD stop signs the "stop sign" class in a built dataset.

classes_v2.yaml (up to 3 Oct 2026) had no mapillary-mtsd source for stop
sign, so convert_mtsd.py folded every regulatory--stop--gN box into
"any-other-sign", i.e. the general "traffic sign" class. COCO and Open Images
call the same object "stop sign": 824 usable MTSD stop signs against 983
labelled ones, two answers for one object. This fixes merged_v2 in place
without rebuilding it. classes_v2.yaml now lists the source, so later builds
get it right from the start.

For each mtsd__<split>__<key> image it reads the MTSD annotation, and changes
the traffic sign line that matches each stop sign box (best IoU, at least
--min-iou) to stop sign. Nothing else is touched. Every change is logged to
mtsd_stop_relabel.csv with the old class, so it can be reversed. Safe to run
twice: an already-changed line is counted, not changed again.

    python relabel_mtsd_stop.py --data "D:/smart cane 2.0/datasets/merged_v2" \
        --mtsd "D:/smart cane 2.0/datasets/raw/mapillary_mtsd"             # dry run
    python relabel_mtsd_stop.py ... --apply
"""
import argparse
import csv
import json
from pathlib import Path

import yaml


def iou(a, b):
    """Boxes as (cx, cy, w, h), normalised."""
    ax0, ay0, ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx0, by0, bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def stop_boxes(ann):
    d = json.loads(ann.read_text())
    W, H = d["width"], d["height"]
    out = []
    for o in d.get("objects", []):
        if o["label"].startswith("regulatory--stop--"):
            b = o["bbox"]
            out.append(((b["xmin"] + b["xmax"]) / 2 / W, (b["ymin"] + b["ymax"]) / 2 / H,
                        (b["xmax"] - b["xmin"]) / W, (b["ymax"] - b["ymin"]) / H))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="built dataset folder (merged_v2)")
    ap.add_argument("--mtsd", required=True, help="folder with the unpacked MTSD annotations")
    ap.add_argument("--names", default="", help="dataset yaml with names (default: data/smartcane.yaml or .hold)")
    ap.add_argument("--min-iou", type=float, default=0.9)
    ap.add_argument("--apply", action="store_true", help="change files (default: dry run)")
    args = ap.parse_args()

    root = Path(args.data)
    names_file = Path(args.names) if args.names else next(
        p for p in (root / "smartcane.yaml", root / "smartcane.yaml.hold") if p.exists())
    names = {v: int(k) for k, v in yaml.safe_load(names_file.read_text())["names"].items()}
    SIGN, STOP = names["traffic sign"], names["stop sign"]
    ann_dir = next(Path(args.mtsd).rglob("annotations"))

    changed = already = unmatched = images = 0
    log = []
    for lbl in sorted((root / "labels").glob("*/mtsd__*.txt")):
        key = lbl.stem.split("__", 2)[2]
        ann = ann_dir / f"{key}.json"
        if not ann.exists():
            continue
        stops = stop_boxes(ann)
        if not stops:
            continue
        images += 1
        lines = lbl.read_text().splitlines()
        parsed = [(i, l.split()) for i, l in enumerate(lines)]
        parsed = [(i, int(f[0]), tuple(float(v) for v in f[1:5])) for i, f in parsed if len(f) == 5]
        taken = set()
        dirty = False
        for s in stops:
            best = max(((iou(s, b), i, c) for i, c, b in parsed
                        if c in (SIGN, STOP) and i not in taken), default=(0, None, None))
            score, i, c = best
            if i is None or score < args.min_iou:
                unmatched += 1          # convert_mtsd.py dropped it as too small
                continue
            taken.add(i)
            if c == STOP:
                already += 1
                continue
            f = lines[i].split()
            lines[i] = " ".join([str(STOP)] + f[1:])
            changed += 1
            dirty = True
            log.append({"split": lbl.parent.name, "label_file": lbl.name, "line": i + 1,
                        "old_class": SIGN, "new_class": STOP, "iou": round(score, 4),
                        "cx": f[1], "cy": f[2], "w": f[3], "h": f[4]})
        if dirty and args.apply:
            lbl.write_text("".join(l + "\n" for l in lines))

    print(f"MTSD images with a stop sign in the dataset: {images}")
    print(f"traffic sign -> stop sign {'changed' if args.apply else 'to change'}: {changed}")
    print(f"already stop sign: {already}")
    print(f"no matching box (dropped as too small at conversion): {unmatched}")
    if args.apply and log:
        path = root / "mtsd_stop_relabel.csv"
        new = not path.exists()
        with open(path, "a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(log[0]))
            if new:
                w.writeheader()
            w.writerows(log)
        print(f"logged to {path}")
    if not args.apply:
        print("dry run, nothing changed. Add --apply to change files.")


if __name__ == "__main__":
    main()
