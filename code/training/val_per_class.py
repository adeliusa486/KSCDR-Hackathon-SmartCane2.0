#!/usr/bin/env python3
"""Smart cane - per-class validation of a trained model.

Training reports one mAP for all 152 classes. A blind user needs to know
which objects the cane names reliably and which it does not, so this runs
Ultralytics validation and writes precision, recall, mAP50 and mAP50-95 for
every class, plus box and image counts.

    python val_per_class.py --model models/smartcane152_v3/smartcane152_v3_best.pt \
        --data "D:/smart cane 2.0/datasets/merged_v2/smartcane.yaml" --out docs/results/v3_per_class.csv
"""
import argparse
import csv
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True, help="CSV path")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--project", default=None, help="Ultralytics output folder")
    args = ap.parse_args()

    from ultralytics import YOLO
    m = YOLO(args.model)
    r = m.val(data=args.data, imgsz=640, batch=args.batch, device=0,
              project=args.project, name="val_per_class", plots=True,
              verbose=False)
    names = r.names
    box = r.box
    stats = {int(c): i for i, c in enumerate(box.ap_class_index)}
    nt = getattr(r, "nt_per_class", None)
    ni = getattr(r, "nt_per_image", None)
    with open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["id", "class", "val_images", "val_boxes", "precision",
                    "recall", "mAP50", "mAP50_95"])
        for c in range(len(names)):
            i = stats.get(c)
            row = [c, names[c],
                   int(ni[c]) if ni is not None else "",
                   int(nt[c]) if nt is not None else ""]
            if i is None:
                row += ["", "", "", ""]
            else:
                row += [f"{box.p[i]:.3f}", f"{box.r[i]:.3f}",
                        f"{box.ap50[i]:.3f}", f"{box.ap[i]:.3f}"]
            w.writerow(row)
    with open(args.out.replace(".csv", "_summary.json"), "w") as fh:
        json.dump({"precision": float(box.mp), "recall": float(box.mr),
                   "mAP50": float(box.map50), "mAP50_95": float(box.map)}, fh,
                  indent=1)
    print(f"mAP50 {box.map50:.3f}  mAP50-95 {box.map:.3f}  -> {args.out}")


if __name__ == "__main__":
    main()
