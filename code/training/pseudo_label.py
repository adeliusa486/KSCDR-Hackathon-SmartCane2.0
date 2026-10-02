#!/usr/bin/env python3
"""Smart cane - fill unlabelled objects in a merged dataset with teacher models.

Every source labels only some objects. An Open Images photo fetched for
"bench" may show an unlabelled car, and a COCO photo has no "palm tree"
boxes at all. Trained as is, the model learns that those cars and palm trees
are background. This step runs strong existing detectors (teachers) over the
train and val images and adds their confident boxes where the photo has no
box of that class already.

Rules:
  * Never touches the test split. Test labels stay human-made.
  * A teacher box is added only above --conf, and only if no existing box of
    the same class overlaps it (IoU >= --iou). Existing labels always win.
  * Teacher class names map to our classes through the coco: and oiv7:
    entries in classes_v2.yaml, so "Man" from the Open Images teacher and
    "person" from the COCO teacher both become person.
  * Every added box is listed in pseudo_labels.csv for audit, and the label
    files are backed up to labels_human/ before the first change.

    python pseudo_label.py --data E:/smartcane-data/merged \
        --teacher coco=yolo11x.pt --teacher oiv7=yolov8x-oiv7.pt
"""
import argparse
import csv
import shutil
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def iou(a, b):
    """Boxes as (cx, cy, w, h), normalised."""
    ax0, ay0, ax1, ay1 = a[0] - a[2] / 2, a[1] - a[3] / 2, a[0] + a[2] / 2, a[1] + a[3] / 2
    bx0, by0, bx1, by1 = b[0] - b[2] / 2, b[1] - b[3] / 2, b[0] + b[2] / 2, b[1] + b[3] / 2
    iw = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    ih = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = iw * ih
    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def merge_boxes(existing, proposals, iou_thr, cross_thr=0.6):
    """existing: [(cls, box)]. proposals: [(cls, box, conf)].
    Returns the proposals to add, best first. A proposal is dropped if it
    overlaps a kept box of the same class (IoU >= iou_thr), or almost any
    kept box of another class (IoU >= cross_thr). The second rule exists
    because a teacher that never saw a class names it as the nearest one it
    knows: the COCO teacher called labelled camels cow, horse and sheep
    (smoke test, 2 Oct 2026)."""
    kept = list(existing)
    added = []
    for cls, box, conf in sorted(proposals, key=lambda p: -p[2]):
        if any((c == cls and iou(box, b) >= iou_thr) or iou(box, b) >= cross_thr
               for c, b in kept):
            continue
        kept.append((cls, box))
        added.append((cls, box, conf))
    return added


def class_map(classes_file, dataset):
    cfg = yaml.safe_load(Path(classes_file).read_text())
    names = [c["name"] for c in cfg["classes"]]
    out = {}
    for c in cfg["classes"]:
        for s in c["src"]:
            ds, _, label = s.partition(":")
            if ds == dataset:
                out[label] = names.index(c["name"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, help="build_dataset.py output folder")
    ap.add_argument("--classes", default=str(HERE / "classes_v2.yaml"))
    ap.add_argument("--teacher", action="append", required=True,
                    help="dataset=weights, dataset is coco or oiv7")
    ap.add_argument("--conf", type=float, default=0.5)
    ap.add_argument("--iou", type=float, default=0.5)
    ap.add_argument("--splits", default="train,val")
    ap.add_argument("--batch", type=int, default=16)
    args = ap.parse_args()

    from ultralytics import YOLO
    root = Path(args.data)
    splits = [s for s in args.splits.split(",") if s != "test"]
    backup = root / "labels_human"
    if not backup.exists():
        shutil.copytree(root / "labels", backup)

    teachers = []
    for t in args.teacher:
        ds, _, weights = t.partition("=")
        model = YOLO(weights)
        cmap = class_map(args.classes, ds)
        # teacher class index -> our class index, only classes we keep
        tmap = {i: cmap[n] for i, n in model.names.items() if n in cmap}
        print(f"teacher {weights} ({ds}): {len(tmap)} of its classes map onto ours")
        teachers.append((weights, model, tmap))

    log = open(root / "pseudo_labels.csv", "a", newline="")
    w = csv.writer(log)
    if log.tell() == 0:
        w.writerow(["split", "image", "class", "conf", "cx", "cy", "w", "h", "teacher"])
    total = 0
    for split in splits:
        images = sorted((root / "images" / split).glob("*"))
        for start in range(0, len(images), args.batch):
            chunk = images[start:start + args.batch]
            proposals = {p: [] for p in chunk}
            for weights, model, tmap in teachers:
                for p, r in zip(chunk, model.predict([str(p) for p in chunk], conf=args.conf,
                                                     verbose=False, device=0)):
                    for cls, conf, box in zip(r.boxes.cls.tolist(), r.boxes.conf.tolist(),
                                              r.boxes.xywhn.tolist()):
                        if int(cls) in tmap:
                            proposals[p].append((tmap[int(cls)], tuple(box), conf, weights))
            for p in chunk:
                lbl = root / "labels" / split / (p.stem + ".txt")
                existing = []
                if lbl.exists():
                    for line in lbl.read_text().split("\n"):
                        if line.strip():
                            c, *b = line.split()
                            existing.append((int(c), tuple(float(v) for v in b)))
                src = {(c, b): t for c, b, _, t in proposals[p]}
                added = merge_boxes(existing, [(c, b, s) for c, b, s, _ in proposals[p]], args.iou)
                if added:
                    with open(lbl, "a") as f:
                        for c, b, s in added:
                            f.write(f"{c} " + " ".join(f"{v:.6f}" for v in b) + "\n")
                            w.writerow([split, p.name, c, round(s, 3), *[round(v, 6) for v in b],
                                        src[(c, b)]])
                    total += len(added)
            print(f"{split}: {min(start + args.batch, len(images))}/{len(images)} images, "
                  f"{total} boxes added so far", flush=True)
    log.close()
    print(f"done: {total} pseudo-labelled boxes, listed in {root / 'pseudo_labels.csv'}")


if __name__ == "__main__":
    main()
