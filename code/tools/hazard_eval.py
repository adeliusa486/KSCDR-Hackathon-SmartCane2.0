#!/usr/bin/env python3
"""Smart cane - run real labelled photos through the Hailo, per safety class.

The closest thing to walking the cane past every hazard without leaving the
room. Each photo goes through the same path as the camera's lores frame
(plain resize to the model input, RGB) and the same decoder as detect.py.

For each labelled object it asks two questions, the two that matter to a
blind user:
  named:    was it detected with the RIGHT name at the naming threshold?
  noticed:  was ANYTHING detected on it at the detection threshold? The cane
            says "obstacle" for those, so the user is still warned.

    python3 tools/hazard_eval.py --model models/smartcane152_v3_h8l.hef \
        --labels smartcane152.txt --images ~/hazard_eval
"""
import argparse
import glob
import json
import os
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from detect import extract_detections, load_labels   # noqa: E402


def iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--labels", required=True)
    ap.add_argument("--images", required=True)
    ap.add_argument("--conf", type=float, default=0.25, help="detection threshold (service)")
    ap.add_argument("--name-conf", type=float, default=0.35, help="naming threshold (service)")
    ap.add_argument("--iou", type=float, default=0.3)
    ap.add_argument("--min-size", type=float, default=0.02,
                    help="ignore labelled objects smaller than this fraction of "
                         "the frame height: too far away to matter to a walker")
    ap.add_argument("--json", help="write per-class results here")
    args = ap.parse_args()

    from picamera2.devices import Hailo
    labels = load_labels(args.labels)
    index = json.load(open(os.path.join(args.images, "_index.json")))
    want = set(index["per_class"])

    stats = {c: {"objects": 0, "named": 0, "noticed": 0} for c in want}
    times = []
    files = sorted(f for f in glob.glob(os.path.join(args.images, "*"))
                   if f.lower().endswith((".jpg", ".jpeg", ".png")))
    with Hailo(args.model) as hailo:
        h, w, _ = hailo.get_input_shape()
        for f in files:
            img = Image.open(f).convert("RGB").resize((w, h), Image.BILINEAR)
            t0 = time.perf_counter()
            raw = hailo.run(np.array(img))     # writable copy, HailoRT needs it
            times.append(time.perf_counter() - t0)
            dets = extract_detections(raw, labels, 1.0, 1.0, args.conf)
            gt_path = os.path.splitext(f)[0] + ".txt"
            for row in open(gt_path).read().split("\n"):
                if not row.strip():
                    continue
                c, cx, cy, bw, bh = row.split()[:5]
                name = labels[int(c)]
                if name not in want or float(bh) < args.min_size:
                    continue
                cx, cy, bw, bh = map(float, (cx, cy, bw, bh))
                box = (cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2)
                s = stats[name]
                s["objects"] += 1
                hits = [d for d in dets if iou(box, (d.x0, d.y0, d.x1, d.y1)) >= args.iou]
                if hits:
                    s["noticed"] += 1
                if any(d.label == name and d.score >= args.name_conf for d in hits):
                    s["named"] += 1

    print(f"{len(files)} photos, Hailo inference median "
          f"{1000 * sorted(times)[len(times) // 2]:.1f} ms\n")
    print(f"{'object':22s} {'count':>5s} {'named':>7s} {'noticed':>8s}")
    tot = {"objects": 0, "named": 0, "noticed": 0}
    for c in sorted(stats, key=lambda c: -stats[c]["noticed"] / max(1, stats[c]["objects"])):
        s = stats[c]
        for k in tot:
            tot[k] += s[k]
        n = max(1, s["objects"])
        print(f"{c:22s} {s['objects']:5d} {100 * s['named'] / n:6.0f}% {100 * s['noticed'] / n:7.0f}%")
    n = max(1, tot["objects"])
    print(f"{'ALL':22s} {tot['objects']:5d} {100 * tot['named'] / n:6.0f}% {100 * tot['noticed'] / n:7.0f}%")
    if args.json:
        json.dump({"stats": stats, "median_ms": 1000 * sorted(times)[len(times) // 2]},
                  open(args.json, "w"), indent=1)


if __name__ == "__main__":
    main()
