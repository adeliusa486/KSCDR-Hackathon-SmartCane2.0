#!/usr/bin/env python3
"""Smart cane - pull the Open Images V7 classes the class list needs, in YOLO format.

Open Images V7 is free with no account. The full set is about 560 GB, so this
pulls only the labels named as "oiv7:<Label>" in classes_v2.yaml, with a cap
per class.

Two things the 19 Sept version got wrong, fixed here:

  * The cap was on the total, so common classes (Person, Car, Building)
    filled it and rare ones (Camel, Kettle) got almost nothing. Now each
    label is fetched on its own with its own cap, then merged.
  * The export used the reduced class list, which drops every other label in
    a photo. Now every Open Images box is exported with the full 601-name
    list, and build_dataset.py does all remapping in one place.

Open Images boxes are incomplete: a photo fetched for "Bench" may show an
unlabelled car. Fill those gaps before training (pseudo-labels from a
teacher model), or the model learns that unlabelled cars are background.

    python fetch_openimages.py --out E:/smartcane-data/oiv7 --per-class 1500
    python fetch_openimages.py --list
"""
import argparse
import json
import os
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent


def wanted_labels(classes_file):
    cfg = yaml.safe_load(Path(classes_file).read_text())
    labels = []
    for c in cfg["classes"]:
        for s in c["src"]:
            ds, _, label = s.partition(":")
            if ds == "oiv7" and label not in labels:
                labels.append(label)
    return labels


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, help="export folder (YOLO layout)")
    ap.add_argument("--classes", default=str(HERE / "classes_v2.yaml"))
    ap.add_argument("--all-names", default="C:/ml/oiv7_classes.json",
                    help="the full Open Images V7 class list, export order")
    ap.add_argument("--per-class", type=int, default=1500)
    ap.add_argument("--val-per-class", type=int, default=150)
    ap.add_argument("--zoo-dir", default=None,
                    help="FiftyOne download cache (default: next to --out)")
    ap.add_argument("--list", action="store_true", help="print the labels and exit")
    ap.add_argument("--labels", help="comma-separated subset, for a smoke test")
    args = ap.parse_args()

    labels = wanted_labels(args.classes)
    if args.labels:
        subset = [l.strip() for l in args.labels.split(",")]
        unknown = [l for l in subset if l not in labels]
        if unknown:
            raise SystemExit(f"not in the class list: {unknown}")
        labels = subset
    if args.list:
        print(f"{len(labels)} Open Images labels from {args.classes}:")
        print(", ".join(labels))
        return

    out = Path(args.out)
    os.environ.setdefault("FIFTYONE_DATASET_ZOO_DIR",
                          args.zoo_dir or str(out.parent / "fiftyone-zoo"))
    import fiftyone as fo
    import fiftyone.zoo as foz

    all_names = json.loads(Path(args.all_names).read_text())
    for split, cap in (("validation", args.val_per_class), ("train", args.per_class)):
        merged = fo.Dataset(f"smartcane_oiv7_{split}", overwrite=True)
        for i, label in enumerate(labels, 1):
            print(f"[{split} {i}/{len(labels)}] {label}: up to {cap}", flush=True)
            part = foz.load_zoo_dataset(
                "open-images-v7", split=split, label_types=["detections"],
                classes=[label], max_samples=cap, shuffle=True, seed=51,
                dataset_name=f"oiv7_{split}_{label}", drop_existing_dataset=True)
            merged.merge_samples(part, key_field="filepath")
            print(f"    {len(part)} images, merged total {len(merged)}", flush=True)
        yolo_split = "val" if split == "validation" else "train"
        merged.export(export_dir=str(out), dataset_type=fo.types.YOLOv5Dataset,
                      label_field="ground_truth", split=yolo_split, classes=all_names)
        print(f"exported {len(merged)} {split} images to {out}", flush=True)
    print("done. next: build_dataset.py with --classes classes_v2.yaml")


if __name__ == "__main__":
    main()
